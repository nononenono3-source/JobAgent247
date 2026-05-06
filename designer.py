from __future__ import annotations

import argparse
import os
import re
import textwrap
from datetime import datetime, timezone
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from file_utils import safe_path
from log_utils import get_logger
from models import Category, Job, read_jobs_json


logger = get_logger("designer")


def _pick_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Prefer a system font if available; fallback to PIL's default bitmap font.
    """
    candidates: list[str] = []
    win_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    if win_fonts and os.path.isdir(win_fonts):
        if bold:
            candidates += [
                os.path.join(win_fonts, "arialbd.ttf"),
                os.path.join(win_fonts, "calibrib.ttf"),
                os.path.join(win_fonts, "segoeuib.ttf"),
            ]
        candidates += [
            os.path.join(win_fonts, "arial.ttf"),
            os.path.join(win_fonts, "calibri.ttf"),
            os.path.join(win_fonts, "segoeui.ttf"),
        ]

    for p in candidates:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _font_line_height(font: ImageFont.ImageFont) -> int:
    try:
        if hasattr(font, "size") and isinstance(font.size, int):
            return max(font.size, 16)
    except Exception:
        pass
    try:
        bbox = font.getbbox("Ag")
        return max(int(bbox[3] - bbox[1]), 16)
    except Exception:
        return 24


def _format_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "Salary: Not disclosed"
    cur = job.salary_currency or ""
    if job.salary_min is not None and job.salary_max is not None:
        return f"Salary: {cur}{int(job.salary_min):,} – {cur}{int(job.salary_max):,}"
    if job.salary_min is not None:
        return f"Salary: {cur}{int(job.salary_min):,}+"
    return f"Salary: up to {cur}{int(job.salary_max):,}"


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = " ".join(cur + [w])
        w_px = draw.textlength(trial, font=font)
        if w_px <= max_width or not cur:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines


def _rounded_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _badge(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    text: str,
    fill: str,
    font: ImageFont.ImageFont,
    pad_x: int = 18,
    pad_y: int = 10,
    radius: int = 16,
    text_fill: str = "white",
) -> tuple[int, int, int, int]:
    w = int(draw.textlength(text, font=font))
    line_height = _font_line_height(font)
    left, top = x, y
    right, bottom = x + w + pad_x * 2, y + line_height + pad_y * 2
    _rounded_rect(draw, (left, top, right, bottom), radius=radius, fill=fill)
    draw.text((left + pad_x, top + pad_y), text, font=font, fill=text_fill)
    return (left, top, right, bottom)


def _pin(draw: ImageDraw.ImageDraw, *, x: int, y: int, color: str) -> None:
    """
    Simple "pin" mark: circle + triangle.
    """
    r = 10
    draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
    tri = [(x, y + r + 18), (x - 10, y + r - 2), (x + 10, y + r - 2)]
    draw.polygon(tri, fill=color)


def _draw_flow_connector(draw: ImageDraw.ImageDraw, *, w: int, h: int, idx: int, total: int) -> None:
    """
    Seamless carousel connector: a line exits right edge with an arrow,
    and re-enters from left edge on subsequent slides.
    """
    y = int(h * 0.72)
    stroke = 10
    color = "#FFFFFF"
    # left "incoming" segment (not on first slide)
    if idx > 1:
        draw.line([(0, y), (140, y)], fill=color, width=stroke)
        draw.polygon([(140, y), (118, y - 14), (118, y + 14)], fill=color)
    # right "outgoing" segment (not on last slide)
    if idx < total:
        draw.line([(w - 140, y), (w, y)], fill=color, width=stroke)
        draw.polygon([(w - 140, y), (w - 118, y - 14), (w - 118, y + 14)], fill=color)


def _bg(size: tuple[int, int], *, theme: Literal["fresher", "pro", "neutral"]) -> Image.Image:
    w, h = size
    base = Image.new("RGB", size, (10, 12, 20))
    top = Image.new("RGB", size, (10, 12, 20))
    if theme == "fresher":
        top = Image.new("RGB", size, (16, 62, 255))
    elif theme == "pro":
        top = Image.new("RGB", size, (255, 64, 140))
    else:
        top = Image.new("RGB", size, (40, 44, 60))
    # vertical gradient
    mask = Image.linear_gradient("L").resize((1, h)).resize((w, h))
    return Image.composite(top, base, mask)


def _draw_footer(draw: ImageDraw.ImageDraw, *, w: int, h: int, idx: int, total: int) -> None:
    small = _pick_font(28)
    label = f"{idx}/{total}  •  Save for later"
    tw = int(draw.textlength(label, font=small))
    draw.text((w - tw - 36, h - 54), label, font=small, fill="#E7E9FF")


def _hook_slide(
    *,
    size: tuple[int, int],
    idx: int,
    total: int,
    audience: Literal["fresher", "pro"],
    jobs: list[Job],
    brand: str = "JobAgent247",
) -> Image.Image:
    w, h = size
    img = _bg(size, theme=audience)
    draw = ImageDraw.Draw(img)

    title_font = _pick_font(72, bold=True)
    subtitle_font = _pick_font(40, bold=False)
    card_title_font = _pick_font(34, bold=True)
    card_meta_font = _pick_font(28, bold=False)

    if audience == "fresher":
        headline = "FRESHERS: Hiring Now"
        sub = "0–1 yrs • Entry-level roles you can apply today"
        accent = "#00E5FF"
    else:
        headline = "PROS: Recruiter Radar"
        sub = "3+ yrs • Mid/Senior roles with strong upside"
        accent = "#FFE44D"

    draw.text((60, 64), headline, font=title_font, fill="white")
    draw.text((60, 152), sub, font=subtitle_font, fill="#F4F6FF")

    # CTA chip
    chip_font = _pick_font(30, bold=True)
    _badge(draw, x=60, y=220, text="SAVE THIS POST", fill="#111827", font=chip_font)
    _badge(draw, x=360, y=220, text="APPLY FAST", fill=accent, font=chip_font, text_fill="#111827")

    # Top picks cards
    top = jobs[:3]
    card_x, card_y = 60, 320
    card_w, card_h = w - 120, 150
    for i, j in enumerate(top):
        y0 = card_y + i * (card_h + 26)
        draw.rounded_rectangle((card_x, y0, card_x + card_w, y0 + card_h), radius=26, fill="#0B1220")
        _pin(draw, x=card_x + 34, y=y0 + 42, color=accent)

        t_lines = _wrap(draw, j.title or "Untitled", card_title_font, max_width=card_w - 120)
        draw.text((card_x + 70, y0 + 22), (t_lines[0][:90] if t_lines else ""), font=card_title_font, fill="white")
        meta = f"{(j.company or 'Unknown')[:40]}  •  {(j.location or 'Unknown')[:40]}"
        draw.text((card_x + 70, y0 + 74), meta, font=card_meta_font, fill="#C7D2FE")

        # mini badges
        badge_font = _pick_font(24, bold=True)
        bx = card_x + 70
        by = y0 + 108
        _badge(draw, x=bx, y=by, text="SALARY", fill="#059669", font=badge_font)
        _badge(draw, x=bx + 140, y=by, text="LOCATION", fill="#2563EB", font=badge_font)
        if j.is_remote:
            _badge(draw, x=bx + 320, y=by, text="REMOTE", fill="#F97316", font=badge_font)

    _draw_flow_connector(draw, w=w, h=h, idx=idx, total=total)
    _draw_footer(draw, w=w, h=h, idx=idx, total=total)
    return img


def _job_slide(
    *,
    size: tuple[int, int],
    idx: int,
    total: int,
    job: Job,
    brand: str = "JobAgent247",
) -> Image.Image:
    w, h = size
    theme: Literal["fresher", "pro", "neutral"] = "neutral"
    if job.category == "fresher":
        theme = "fresher"
    elif job.category == "pro":
        theme = "pro"

    img = _bg(size, theme=theme)
    draw = ImageDraw.Draw(img)

    title_font = _pick_font(58, bold=True)
    meta_font = _pick_font(34, bold=False)
    body_font = _pick_font(30, bold=False)
    badge_font = _pick_font(28, bold=True)

    # Header block
    draw.rounded_rectangle((50, 48, w - 50, 350), radius=32, fill="#0B1220")
    _pin(draw, x=86, y=92, color="#FFFFFF")
    t_lines = _wrap(draw, job.title or "Untitled", title_font, max_width=w - 160)
    draw.text((120, 70), (t_lines[0] if t_lines else ""), font=title_font, fill="white")
    if len(t_lines) > 1:
        draw.text((120, 130), t_lines[1][:40], font=title_font, fill="white")

    company = (job.company or "Unknown")[:60]
    loc = (job.location or "Unknown")[:60]
    draw.text((120, 220), f"{company}", font=meta_font, fill="#C7D2FE")
    draw.text((120, 265), f"{loc}", font=meta_font, fill="#C7D2FE")

    # Badges row (Badge & Pin system)
    bx, by = 70, 380
    _badge(draw, x=bx, y=by, text=_format_salary(job), fill="#059669", font=badge_font)
    _badge(draw, x=bx, y=by + 74, text=f"Location: {loc}", fill="#2563EB", font=badge_font)
    _badge(
        draw,
        x=bx,
        y=by + 148,
        text=("Remote/WFH: Yes" if job.is_remote else "Remote/WFH: No"),
        fill=("#F97316" if job.is_remote else "#334155"),
        font=badge_font,
    )

    # Description preview panel
    draw.rounded_rectangle((50, 580, w - 50, h - 110), radius=32, fill="#0B1220")
    preview = (job.description or "").strip()
    preview = re_sub_whitespace(preview)
    preview = preview[:520] + ("…" if len(preview) > 520 else "")
    lines = textwrap.wrap(preview, width=48)
    y = 610
    for line in lines[:8]:
        draw.text((70, y), line, font=body_font, fill="#E5E7EB")
        y += 38

    # Tiny URL hint
    url_font = _pick_font(22)
    draw.text((70, h - 92), "Link in PDF / description • Save for later", font=url_font, fill="#A5B4FC")

    _draw_flow_connector(draw, w=w, h=h, idx=idx, total=total)
    _draw_footer(draw, w=w, h=h, idx=idx, total=total)
    return img


def re_sub_whitespace(s: str) -> str:
    return " ".join((s or "").split())


def _fallback_slide(*, size: tuple[int, int], idx: int, total: int, message: str) -> Image.Image:
    w, h = size
    img = _bg(size, theme="neutral")
    draw = ImageDraw.Draw(img)
    title_font = _pick_font(54, bold=True)
    body_font = _pick_font(30)
    draw.rounded_rectangle((60, 120, w - 60, h - 140), radius=32, fill="#0B1220")
    draw.text((100, 180), "JobAgent247", font=title_font, fill="white")
    lines = textwrap.wrap(re_sub_whitespace(message) or "Content unavailable.", width=34)
    y = 290
    for line in lines[:8]:
        draw.text((100, y), line, font=body_font, fill="#E5E7EB")
        y += 42
    _draw_footer(draw, w=w, h=h, idx=idx, total=total)
    return img


def build_carousel(
    *,
    jobs: list[Job],
    out_dir: str,
    max_per_category: int = 5,
    size: tuple[int, int] = (1080, 1080),
) -> list[str]:
    fresher = [j for j in jobs if j.category == "fresher"][:max_per_category]
    pro = [j for j in jobs if j.category == "pro"][:max_per_category]
    # Fill if one category has fewer items
    if len(fresher) < max_per_category:
        fresher += [j for j in jobs if j.category == "uncategorized"][: (max_per_category - len(fresher))]
    if len(pro) < max_per_category:
        pro += [j for j in jobs if j.category == "uncategorized"][max_per_category : max_per_category + (max_per_category - len(pro))]

    slides: list[Image.Image] = []
    total = 2 + len(fresher) + len(pro)
    try:
        slides.append(_hook_slide(size=size, idx=1, total=total, audience="fresher", jobs=fresher))
    except Exception as exc:
        logger.warning("Failed to build fresher hook slide: %s", exc)
        slides.append(_fallback_slide(size=size, idx=1, total=total, message="Freshers jobs are temporarily unavailable. Check the PDF for details."))
    try:
        slides.append(_hook_slide(size=size, idx=2, total=total, audience="pro", jobs=pro))
    except Exception as exc:
        logger.warning("Failed to build pro hook slide: %s", exc)
        slides.append(_fallback_slide(size=size, idx=2, total=total, message="Pro jobs are temporarily unavailable. Check the PDF for details."))

    idx = 3
    for j in fresher:
        try:
            slides.append(_job_slide(size=size, idx=idx, total=total, job=j))
        except Exception as exc:
            logger.warning("Failed to build fresher slide %s: %s", idx, exc)
            slides.append(_fallback_slide(size=size, idx=idx, total=total, message=f"Job slide unavailable for {j.title or 'this role'}. Check the PDF for full details."))
        idx += 1
    for j in pro:
        try:
            slides.append(_job_slide(size=size, idx=idx, total=total, job=j))
        except Exception as exc:
            logger.warning("Failed to build pro slide %s: %s", idx, exc)
            slides.append(_fallback_slide(size=size, idx=idx, total=total, message=f"Job slide unavailable for {j.title or 'this role'}. Check the PDF for full details."))
        idx += 1

    safe_path(out_dir)
    paths: list[str] = []
    for i, img in enumerate(slides, start=1):
        p = os.path.join(out_dir, f"slide_{i:02d}.png")
        try:
            img.save(p, format="PNG", optimize=True)
        except Exception as exc:
            logger.warning("Failed to save slide %s: %s", i, exc)
            fallback = _fallback_slide(size=size, idx=i, total=total, message="A slide could not be rendered. Check the PDF for full details.")
            fallback.save(p, format="PNG", optimize=True)
        paths.append(p)
    return paths


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate seamless Instagram carousel from jobs JSON.")
    p.add_argument("--in", dest="in_path", default=os.path.join("data", "jobs.json"), help="Input jobs.json")
    p.add_argument("--out-dir", default="", help="Output directory for slides (default: assets/carousels/<timestamp>)")
    p.add_argument("--max-per-category", type=int, default=5, help="How many jobs per category to include.")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    _, jobs = read_jobs_json(args.in_path)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir or os.path.join("assets", "carousels", ts)
    paths = build_carousel(jobs=jobs, out_dir=out_dir, max_per_category=args.max_per_category)
    logger.info("Generated %s slides in %s", len(paths), out_dir)


if __name__ == "__main__":
    main()

