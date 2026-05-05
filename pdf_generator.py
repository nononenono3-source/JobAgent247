from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Any, Literal, Optional

from fpdf import FPDF


Category = Literal["fresher", "pro", "uncategorized"]


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
_MAX_UNBROKEN_CHARS = 60


@dataclass(frozen=True)
class Job:
    category: Category
    title: str
    company: str
    location: str
    is_remote: bool
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: Optional[str]
    url: str
    description: str
    source: str
    country: str


def _read_jobs_json(path: str) -> tuple[str, list[Job]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    generated_at = str(payload.get("generated_at", "")).strip()
    jobs_raw = payload.get("jobs", payload)
    jobs: list[Job] = []
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        jobs.append(
            Job(
                category=item.get("category", "uncategorized"),
                title=str(item.get("title", "")).strip(),
                company=str(item.get("company", "")).strip(),
                location=str(item.get("location", "")).strip(),
                is_remote=bool(item.get("is_remote", False)),
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                salary_currency=item.get("salary_currency"),
                url=str(item.get("url", "")).strip(),
                description=str(item.get("description", "")).strip(),
                source=str(item.get("source", "")).strip(),
                country=str(item.get("country", "")).strip(),
            )
        )
    return generated_at, jobs


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


def clean_text(value: Any) -> str:
    """
    Normalize common Unicode punctuation from job feeds into ASCII-safe text for FPDF
    and force wrap opportunities into very long unbroken strings.
    """
    text = str(value or "")
    text = text.translate(_TEXT_REPLACEMENTS)
    text = _break_long_tokens(text)
    return text.encode("latin-1", "replace").decode("latin-1")


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
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    pdf = JobsPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(40, 44, 60)
    stamp = generated_at or datetime.now(timezone.utc).isoformat()
    pdf.multi_cell(0, 6, clean_text(f"Generated at (UTC): {stamp}"))
    pdf.ln(3)

    # Summary counts
    by_cat = {
        "fresher": sum(1 for j in jobs if j.category == "fresher"),
        "pro": sum(1 for j in jobs if j.category == "pro"),
        "uncategorized": sum(1 for j in jobs if j.category == "uncategorized"),
    }
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(
        0,
        7,
        clean_text(f"Jobs: {len(jobs)}   -   Freshers: {by_cat['fresher']}   -   Pros: {by_cat['pro']}"),
    )
    pdf.ln(2)

    for i, job in enumerate(jobs, start=1):
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(0, 7, clean_text(f"{i}. {job.title or 'Untitled'}"))

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
            pdf.multi_cell(0, 6, clean_text(m))

        pdf.ln(1)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(0, 6, clean_text("Description:"))

        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(35, 40, 55)
        desc = clean_text(" ".join((job.description or "").split()))
        pdf.multi_cell(0, 5.5, desc if desc else "N/A")

        pdf.ln(6)
        pdf.set_draw_color(230, 235, 248)
        y = pdf.get_y()
        pdf.line(10, y, 200, y)
        pdf.ln(7)

    pdf.output(out_path)


def update_docs_index(*, docs_dir: str, created_pdf_filename: str) -> str:
    """
    Writes/updates docs/index.html with a minimal listing of PDFs.
    Returns index file path.
    """
    os.makedirs(docs_dir, exist_ok=True)
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
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    return index_path


def write_latest_alias(*, docs_dir: str, pdf_filename: str) -> str:
    """
    Copies the generated PDF to docs/latest-jobs.pdf so external links stay stable.
    Returns latest path.
    """
    src = os.path.join(docs_dir, pdf_filename)
    dst = os.path.join(docs_dir, "latest-jobs.pdf")
    shutil.copyfile(src, dst)
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
    generated_at, jobs = _read_jobs_json(args.in_path)
    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = args.name or f"jobs-{ts}.pdf"
    out_path = os.path.join(args.docs_dir, name)
    generate_pdf(generated_at=generated_at, jobs=jobs, out_path=out_path)
    write_latest_alias(docs_dir=args.docs_dir, pdf_filename=name)
    update_docs_index(docs_dir=args.docs_dir, created_pdf_filename=name)
    print(f"Wrote PDF: {out_path}")


if __name__ == "__main__":
    main()

