from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from PIL import Image, ImageDraw, ImageFont

from file_utils import safe_path
from log_utils import get_logger
from models import Category, Job, read_jobs_json


logger = get_logger("video_maker")


def _pick_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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


def _latest_carousel_dir(root: str = os.path.join("assets", "carousels")) -> str:
    if not os.path.isdir(root):
        raise FileNotFoundError(f"No carousels directory found at {root}. Run designer.py first.")
    subdirs = [
        os.path.join(root, d)
        for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d))
    ]
    if not subdirs:
        raise FileNotFoundError(f"No carousel batches found under {root}. Run designer.py first.")
    return max(subdirs, key=lambda p: os.path.getmtime(p))


def _list_slide_images(carousel_dir: str) -> list[str]:
    files = [f for f in os.listdir(carousel_dir) if f.lower().endswith(".png") and f.startswith("slide_")]
    files.sort()
    paths = [os.path.join(carousel_dir, f) for f in files]
    if not paths:
        raise FileNotFoundError(f"No slide_XX.png files found in {carousel_dir}")
    return paths


def _fmt_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return ""
    cur = job.salary_currency or ""
    if job.salary_max is not None:
        return f"{cur}{int(job.salary_max):,}"
    if job.salary_min is not None:
        return f"{cur}{int(job.salary_min):,}+"
    return ""


def _top_jobs_for_script(jobs: list[Job], n: int = 5) -> list[Job]:
    def score(j: Job) -> float:
        s = 0.0
        if isinstance(j.salary_max, (int, float)):
            s += float(j.salary_max)
        elif isinstance(j.salary_min, (int, float)):
            s += float(j.salary_min) * 0.8
        if j.is_remote:
            s += 500  # small remote bonus
        if j.category == "pro":
            s += 250
        if j.category == "fresher":
            s += 150
        return s

    return sorted(jobs, key=score, reverse=True)[:n]


def _warn(message: str) -> None:
    logger.warning(message)


def build_voiceover_script(jobs: list[Job], *, pages_url: str) -> str:
    top = _top_jobs_for_script(jobs, n=5)
    lines: list[str] = [
        "Here are today’s top hiring picks. Save this video and apply fast.",
    ]
    for i, j in enumerate(top, start=1):
        salary = _fmt_salary(j)
        bits = [j.title or "Role", "at", j.company or "a top company"]
        if salary:
            bits += ["with pay up to", salary]
        if j.is_remote:
            bits += ["and remote or hybrid options."]
        else:
            bits += ["."]
        lines.append(f"{i}. " + " ".join(bits))
    lines += [
        "For all job links and full descriptions, open the PDF in the description.",
        f"PDF: {pages_url}",
    ]
    return " ".join(lines)


async def edge_tts_to_file(*, text: str, out_path: str, voice: str = "en-US-JennyNeural", rate: str = "+0%") -> None:
    import edge_tts  # lazy import

    safe_path(out_path, create_parent=True)
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(out_path)


def make_thumbnail(
    *,
    jobs: list[Job],
    out_path: str,
    title: str = "HIRING NOW",
) -> str:
    safe_path(out_path, create_parent=True)
    img = Image.new("RGB", (1280, 720), (8, 12, 26))
    draw = ImageDraw.Draw(img)

    # Choose a "headline" job: max salary max, else first
    def sal_key(j: Job) -> float:
        if isinstance(j.salary_max, (int, float)):
            return float(j.salary_max)
        if isinstance(j.salary_min, (int, float)):
            return float(j.salary_min)
        return 0.0

    head = max(jobs, key=sal_key) if jobs else None
    company = (head.company if head else "Top Companies") or "Top Companies"
    role = (head.title if head else "New Roles") or "New Roles"
    salary = _fmt_salary(head) if head else ""

    # High-contrast blocks
    draw.rounded_rectangle((60, 60, 1220, 660), radius=44, fill=(15, 23, 42))
    draw.rounded_rectangle((80, 80, 1200, 210), radius=34, fill=(255, 229, 77))

    font_big = _pick_font(86, bold=True)
    font_mid = _pick_font(54, bold=True)
    font_small = _pick_font(34, bold=False)

    draw.text((110, 108), title, font=font_mid, fill=(15, 23, 42))

    # "Logo": generated badge with initials (offline + zero-cost)
    initials = "".join([p[0] for p in company.split()[:2] if p])[:2].upper() or "JO"
    draw.ellipse((100, 260, 270, 430), fill=(37, 99, 235))
    init_font = _pick_font(76, bold=True)
    tw = draw.textlength(initials, font=init_font)
    draw.text((185 - tw / 2, 305), initials, font=init_font, fill="white")

    # Main text
    draw.text((310, 265), company[:28], font=font_mid, fill="white")
    draw.text((310, 340), role[:36], font=font_small, fill=(199, 210, 254))

    if salary:
        draw.rounded_rectangle((310, 410, 930, 520), radius=30, fill=(5, 150, 105))
        draw.text((340, 440), f"UP TO {salary}", font=font_mid, fill="white")
    else:
        draw.text((310, 420), "SALARY: NOT DISCLOSED", font=font_small, fill=(229, 231, 235))

    draw.text((310, 560), "Save for later • Apply fast • Links in PDF", font=font_small, fill=(165, 180, 252))

    img.save(out_path, format="PNG", optimize=True)
    return out_path


def make_video_from_slides(
    *,
    slide_paths: list[str],
    voice_path: Optional[str],
    out_path: str,
    duration_s: float = 60.0,
    fps: int = 30,
) -> Optional[str]:
    # Lazy imports: MoviePy is heavy
    try:
        from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
        from moviepy.audio.AudioClip import AudioClip, concatenate_audioclips
        import numpy as np
    except Exception as exc:
        _warn(f"MoviePy/FFmpeg dependencies unavailable; skipping video render: {exc}")
        return None

    safe_path(out_path, create_parent=True)
    if not slide_paths:
        _warn("No slides were available for video rendering.")
        return None

    per = max(1.5, duration_s / max(1, len(slide_paths)))
    clips = []
    for path in slide_paths:
        try:
            clips.append(ImageClip(path).set_duration(per).resize((1080, 1920)))
        except Exception as exc:
            _warn(f"Skipping unreadable slide for video render ({path}): {exc}")
    if not clips:
        _warn("All slide inputs failed to load; skipping video render.")
        return None

    # Vertical short: pad/crop slides to 9:16 by centering on a blurred background
    # Simpler zero-cost approach: just fit (can letterbox)
    base = None
    audio = None
    audio_final = None

    try:
        base = concatenate_videoclips(clips, method="compose").set_duration(duration_s)
        # Audio is optional; render silent video if TTS failed upstream.
        if voice_path and os.path.exists(voice_path):
            audio = AudioFileClip(voice_path)
            if audio.duration >= duration_s:
                audio_final = audio.subclip(0, duration_s)
            else:
                silence_dur = duration_s - audio.duration

                def make_silence(t: float) -> np.ndarray:
                    return np.zeros((1,), dtype=np.float32)

                silence = AudioClip(make_silence, duration=silence_dur, fps=44100)
                audio_final = concatenate_audioclips([audio, silence])
        else:
            _warn("Voiceover file missing; rendering silent video instead.")

        final = base.set_audio(audio_final) if audio_final is not None else base
        final.write_videofile(
            out_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
        )
    except Exception as exc:
        _warn(f"Video rendering failed; continuing without Shorts output: {exc}")
        return None
    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
        for asset in [audio_final, audio, base]:
            try:
                if asset is not None:
                    asset.close()
            except Exception:
                pass
        try:
            if "final" in locals():
                final.close()
        except Exception:
            pass

    return out_path


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate 60s YouTube Shorts video from carousel + edge-tts voiceover.")
    p.add_argument("--jobs", default=os.path.join("data", "jobs.json"), help="Input jobs.json")
    p.add_argument("--carousel-dir", default="", help="Carousel directory (default: latest under assets/carousels)")
    p.add_argument("--out-dir", default="", help="Output directory (default: assets/videos/<timestamp>)")
    p.add_argument("--pages-url", default=os.getenv("GITHUB_PAGES_PDF_URL", ""), help="Public URL to docs/latest-jobs.pdf")
    p.add_argument("--voice", default=os.getenv("EDGE_TTS_VOICE", "en-US-JennyNeural"), help="edge-tts voice name")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    generated_at, jobs = read_jobs_json(args.jobs)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir or os.path.join("assets", "videos", ts)
    safe_path(out_dir)

    try:
        carousel_dir = args.carousel_dir or _latest_carousel_dir()
        slides = _list_slide_images(carousel_dir)
    except Exception as exc:
        _warn(f"Video generation skipped because slides were unavailable: {exc}")
        slides = []

    pages_url = args.pages_url or "https://[your-username].github.io/[repo-name]/docs/latest-jobs.pdf"
    script = build_voiceover_script(jobs, pages_url=pages_url)

    voice_path = os.path.join(out_dir, "voiceover.mp3")
    try:
        asyncio.run(edge_tts_to_file(text=script, out_path=voice_path, voice=args.voice))
    except Exception as exc:
        _warn(f"Voiceover generation failed; proceeding without audio: {exc}")
        voice_path = ""

    thumb_path = os.path.join(out_dir, "thumbnail.png")
    try:
        make_thumbnail(jobs=jobs, out_path=thumb_path)
    except Exception as exc:
        _warn(f"Thumbnail generation failed: {exc}")
        thumb_path = ""

    video_path = os.path.join(out_dir, "shorts.mp4")
    rendered_video = make_video_from_slides(slide_paths=slides, voice_path=voice_path or None, out_path=video_path, duration_s=60.0)

    logger.info("Video: %s", rendered_video or 'skipped')
    logger.info("Thumbnail: %s", thumb_path or 'skipped')
    logger.info("Voiceover: %s", voice_path or 'skipped')


if __name__ == "__main__":
    main()

