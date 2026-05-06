from __future__ import annotations

import argparse
import os
import re
import shutil
import textwrap
from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

from fpdf import FPDF

from file_utils import copy_file_safe, safe_path, write_text_atomic
from log_utils import get_logger
from models import Category, Job, read_jobs_json, safe_text


_TEXT_REPLACEMENTS = str.maketrans(
    {
        "\u2022": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
)
_MAX_UNBROKEN_CHARS = 50
_MAX_DESCRIPTION_CHARS = 2000
_PAGE_BOTTOM_GUARD_MM = 16

logger = get_logger("pdf_generator")


def _strip_control_chars(text: str) -> str:
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def _fmt_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "Not disclosed"
    cur = job.salary_currency or ""
    if job.salary_min is not None and job.salary_max is not None:
        return f"{cur}{int(job.salary_min):,} – {cur}{int(job.salary_max):,}"
    if job.salary_min is not None:
        return f"{cur}{int(job.salary_min):,}+"
    return f"Up to {cur}{int(job.salary_max):,}"


def _break_long_tokens(text: str, *, max_chars: int = _MAX_UNBROKEN_CHARS) -> str:
    """
    Insert spaces into oversized non-whitespace tokens so FPDF can wrap them.
    """
    parts = re.split(r"(\s+)", text)
    wrapped: list[str] = []
    for part in parts:
        if not part or part.isspace() or len(part) <= max_chars:
            wrapped.append(part)
            continue
        wrapped.append(" ".join(part[i : i + max_chars] for i in range(0, len(part), max_chars)))
    return "".join(wrapped)


def clean_text(value: Any, *, max_length: Optional[int] = None) -> str:
    """
    Normalize common Unicode punctuation from job feeds into ASCII-safe text for FPDF
    and force wrap opportunities into very long unbroken strings.
    """
    text = safe_text(value)
    text = text.translate(_TEXT_REPLACEMENTS)
    text = _strip_control_chars(text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_length and len(text) > max_length:
        text = text[: max_length - 3].rstrip() + "..."
    text = _break_long_tokens(text)
    return text.encode("latin-1", "replace").decode("latin-1")


def _wrap_pdf_text(text: str, *, width: int) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return [""]
    return textwrap.wrap(
        cleaned,
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=False,
    ) or [cleaned]


def _ensure_vertical_space(pdf: FPDF, required_height: float) -> None:
    if pdf.get_y() + required_height > pdf.h - max(pdf.b_margin, _PAGE_BOTTOM_GUARD_MM):
        pdf.add_page()


def _write_lines(pdf: FPDF, lines: list[str], *, line_height: float) -> None:
    for line in lines:
        _ensure_vertical_space(pdf, line_height)
        pdf.cell(0, line_height, line, new_x="LMARGIN", new_y="NEXT")


def _write_wrapped(pdf: FPDF, text: str, *, line_height: float, width: int, max_length: Optional[int] = None) -> None:
    lines = _wrap_pdf_text(clean_text(text, max_length=max_length), width=width)
    _write_lines(pdf, lines, line_height=line_height)


def _estimate_job_height(job: Job) -> float:
    title_lines = len(_wrap_pdf_text(job.title or "Untitled", width=70))
    meta_lines = sum(
        len(_wrap_pdf_text(value, width=95))
        for value in [
            f"Company: {job.company or 'Unknown'}",
            f"Category: {job.category}",
            f"Location: {job.location or 'Unknown'}",
            f"Remote/WFH: {'Yes' if job.is_remote else 'No'}",
            f"Salary: {_fmt_salary(job)}",
            f"URL: {job.url or 'N/A'}",
        ]
    )
    desc_lines = len(
        _wrap_pdf_text(
            clean_text(" ".join((job.description or "").split()), max_length=_MAX_DESCRIPTION_CHARS) or "N/A",
            width=100,
        )
    )
    return (title_lines * 7) + (meta_lines * 6) + 20 + (desc_lines * 5.5) + 18


def _write_fallback_pdf(*, out_path: str, generated_at: str, job_count: int, error_message: str) -> None:
    safe_path(out_path, create_parent=True)
    pdf = JobsPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    _write_wrapped(pdf, "JobAgent247 PDF generation hit a recoverable error.", line_height=7, width=80)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 11)
    _write_wrapped(pdf, f"Generated at (UTC): {generated_at or datetime.now(timezone.utc).isoformat()}", line_height=6, width=90)
    _write_wrapped(pdf, f"Jobs fetched: {job_count}", line_height=6, width=90)
    _write_wrapped(pdf, f"Details: {clean_text(error_message, max_length=800)}", line_height=6, width=90)
    pdf.output(out_path)


class JobsPDF(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(20, 24, 40)
        self.cell(0, 10, clean_text("JobAgent247 - Daily Job Digest"), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        self.set_draw_color(220, 225, 240)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(100, 110, 140)
        self.cell(0, 10, clean_text(f"Page {self.page_no()}"), align="C")


def generate_pdf(*, generated_at: str, jobs: list[Job], out_path: str) -> None:
    safe_path(out_path, create_parent=True)
    stamp = generated_at or datetime.now(timezone.utc).isoformat()
    try:
        pdf = JobsPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=14)
        pdf.add_page()

        pdf.set_font("Helvetica", "", 12)
        pdf.set_text_color(40, 44, 60)
        _write_wrapped(pdf, f"Generated at (UTC): {stamp}", line_height=6, width=90)
        pdf.ln(3)

        by_cat = {
            "fresher": sum(1 for j in jobs if j.category == "fresher"),
            "pro": sum(1 for j in jobs if j.category == "pro"),
            "uncategorized": sum(1 for j in jobs if j.category == "uncategorized"),
        }
        pdf.set_font("Helvetica", "B", 12)
        _write_wrapped(
            pdf,
            f"Jobs: {len(jobs)}   -   Freshers: {by_cat['fresher']}   -   Pros: {by_cat['pro']}",
            line_height=7,
            width=75,
        )
        pdf.ln(2)

        for i, job in enumerate(jobs, start=1):
            try:
                _ensure_vertical_space(pdf, max(_estimate_job_height(job), 28))
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(15, 23, 42)
                _write_wrapped(pdf, f"{i}. {job.title or 'No title provided'}", line_height=7, width=70, max_length=300)

                pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(60, 70, 95)
                meta = [
                    f"Company: {job.company or 'Unknown'}",
                    f"Category: {job.category}",
                    f"Location: {job.location or 'Unknown'}",
                    f"Remote/WFH: {'Yes' if job.is_remote else 'No'}",
                    f"Salary: {_fmt_salary(job)}",
                    f"URL: {job.url or 'N/A'}",
                ]
                for m in meta:
                    _write_wrapped(pdf, m, line_height=6, width=95, max_length=600)

                pdf.ln(1)
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(15, 23, 42)
                _write_wrapped(pdf, "Description:", line_height=6, width=95)

                pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(35, 40, 55)
                desc = clean_text(" ".join((job.description or "").split()), max_length=_MAX_DESCRIPTION_CHARS) or "N/A"
                _write_wrapped(pdf, desc, line_height=5.5, width=100)

                pdf.ln(6)
                pdf.set_draw_color(230, 235, 248)
                y = pdf.get_y()
                pdf.line(10, y, 200, y)
                pdf.ln(7)
            except Exception:
                logger.exception("Skipping PDF entry for job #%s due to rendering failure.", i)
                continue

        pdf.output(out_path)
    except Exception as exc:
        logger.exception("Primary PDF generation failed; writing fallback PDF.")
        _write_fallback_pdf(out_path=out_path, generated_at=stamp, job_count=len(jobs), error_message=str(exc))


def update_docs_index(*, docs_dir: str, created_pdf_filename: str) -> str:
    """
    Writes/updates docs/index.html with a minimal listing of PDFs.
    Returns index file path.
    """
    safe_path(docs_dir)
    pdfs = sorted([f for f in os.listdir(docs_dir) if f.lower().endswith(".pdf")])
    newest = created_pdf_filename
    items = "\n".join(
        f'<li><a href="{escape(f)}">{escape(f)}</a></li>' for f in reversed(pdfs)
    )
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>JobAgent247 Docs</title>
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 40px; color: #0f172a; }}
      .card {{ max-width: 860px; padding: 24px; border: 1px solid #e2e8f0; border-radius: 16px; }}
      a {{ color: #2563eb; text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
      code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>JobAgent247 PDFs</h1>
      <p>Latest: <a href="{escape(newest)}"><code>{escape(newest)}</code></a></p>
      <p>Stable link (for YouTube/Instagram): <a href="latest-jobs.pdf"><code>latest-jobs.pdf</code></a></p>
      <h2>All files</h2>
      <ul>
        {items}
      </ul>
    </div>
  </body>
</html>
"""
    index_path = os.path.join(docs_dir, "index.html")
    write_text_atomic(index_path, html)
    return index_path


def write_latest_alias(*, docs_dir: str, pdf_filename: str) -> str:
    """
    Copies the generated PDF to docs/latest-jobs.pdf so external links stay stable.
    Returns latest path.
    """
    src = os.path.join(docs_dir, pdf_filename)
    dst = os.path.join(docs_dir, "latest-jobs.pdf")
    copy_file_safe(src, dst)
    return dst


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate a detailed PDF of job descriptions into /docs for GitHub Pages.")
    p.add_argument("--in", dest="in_path", default=os.path.join("data", "jobs.json"), help="Input jobs.json")
    p.add_argument("--docs-dir", default="docs", help="Docs output directory (GitHub Pages root)")
    p.add_argument("--name", default="", help="Output PDF filename (default: jobs-<timestamp>.pdf)")
    p.add_argument("--limit", type=int, default=0, help="Optional limit of jobs in PDF (0 = all).")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    try:
        generated_at, jobs = read_jobs_json(args.in_path)
        if args.limit and args.limit > 0:
            jobs = jobs[: args.limit]
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        name = args.name or f"jobs-{ts}.pdf"
        out_path = os.path.join(args.docs_dir, name)
        generate_pdf(generated_at=generated_at, jobs=jobs, out_path=out_path)
        write_latest_alias(docs_dir=args.docs_dir, pdf_filename=name)
        update_docs_index(docs_dir=args.docs_dir, created_pdf_filename=name)
        logger.info("Wrote PDF to %s", out_path)
    except Exception:
        logger.exception("pdf_generator main() failed.")


if __name__ == "__main__":
    main()

