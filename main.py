from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from designer import build_carousel
from log_utils import get_logger
from models import read_jobs_json
from pdf_generator import generate_pdf, update_docs_index, write_latest_alias
from scraper import fetch_jobs, normalize_adzuna_country, write_json


logger = get_logger("main")


def build_caption(*, pages_pdf_url: str) -> str:
    return (
        "SAVE for later ✅\n\n"
        "Freshers (0–1 yrs) + Pros (3+ yrs): today’s best roles.\n"
        "Recruiters: share this with your team.\n\n"
        f"Full descriptions + links (PDF): {pages_pdf_url}\n\n"
        "#jobs #hiring #freshers #careers #softwarejobs"
    )


def _normalize_pages_base_url(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    if not path.endswith("/docs"):
        path = f"{path}/docs" if path else "/docs"
    return urlunparse(parsed._replace(path=path))


def _normalize_pages_pdf_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    if path.endswith("/latest-jobs.pdf") and "/docs/" not in f"{path}/":
        base_path = path[: -len("/latest-jobs.pdf")]
        path = f"{base_path}/docs/latest-jobs.pdf" if base_path else "/docs/latest-jobs.pdf"
    elif not path.endswith(".pdf"):
        if path.endswith("/docs"):
            path = f"{path}/latest-jobs.pdf"
        else:
            path = f"{path}/docs/latest-jobs.pdf" if path else "/docs/latest-jobs.pdf"
    return urlunparse(parsed._replace(path=path))


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using %s.", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float for %s=%r; using %s.", name, raw, default)
        return default


def ensure_pages_url() -> str:
    """
    Stable URL to docs/latest-jobs.pdf. Prefer env override in Actions.
    """
    v = os.getenv("GITHUB_PAGES_PDF_URL", "").strip()
    if v:
        return _normalize_pages_pdf_url(v)
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()  # owner/repo (available on Actions)
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/docs/latest-jobs.pdf"
    owner = os.getenv("GITHUB_OWNER", "").strip()
    name = os.getenv("GITHUB_REPO", "").strip()
    if owner and name:
        return f"https://{owner}.github.io/{name}/docs/latest-jobs.pdf"
    return "https://YOUR_USERNAME.github.io/YOUR_REPO/docs/latest-jobs.pdf"


def ensure_pages_base_url() -> str:
    """
    Base URL where your GitHub Pages site is served.
    For this repo deployment layout (upload-pages-artifact path: .), social assets
    are under /docs/assets, so base should include /docs.
    Example: https://<user>.github.io/<repo>/docs
    """
    v = os.getenv("GITHUB_PAGES_BASE_URL", "").strip()
    if v:
        return _normalize_pages_base_url(v)
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/docs"
    owner = os.getenv("GITHUB_OWNER", "").strip()
    name = os.getenv("GITHUB_REPO", "").strip()
    if owner and name:
        return f"https://{owner}.github.io/{name}/docs"
    return "https://YOUR_USERNAME.github.io/YOUR_REPO/docs"


def run_scrape(*, country: str, pages: int, results_per_page: int, query: str) -> str:
    country = normalize_adzuna_country(country)
    jobs = fetch_jobs(
        country=country,
        pages=pages,
        results_per_page=results_per_page,
        query=query,
        where=None,
        remote=None,
        max_days_old=10,
    )
    out = os.path.join("data", "jobs.json")
    write_json(out, jobs)
    return out


def run_carousel(*, jobs_json: str) -> str:
    _, jobs = read_jobs_json(jobs_json)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join("assets", "carousels", ts)
    build_carousel(jobs=jobs, out_dir=out_dir, max_per_category=5)
    return out_dir


def export_instagram_slides_to_docs_assets(
    *,
    carousel_dir: str,
    docs_assets_dir: str = os.path.join("docs", "assets"),
) -> list[str]:
    """
    Convert local PNG slides to public JPGs under docs/assets with stable filenames.
    Creates docs/assets/manifest.json listing slide files in order.
    """
    from PIL import Image

    os.makedirs(docs_assets_dir, exist_ok=True)
    pngs = [f for f in os.listdir(carousel_dir) if f.lower().endswith(".png") and f.startswith("slide_")]
    pngs.sort()
    if not pngs:
        raise RuntimeError(f"No slide PNGs found in {carousel_dir}")

    out_names: list[str] = []
    for i, f in enumerate(pngs, start=1):
        src = os.path.join(carousel_dir, f)
        out_name = f"slide_{i:02d}.jpg"
        dst = os.path.join(docs_assets_dir, out_name)
        try:
            with Image.open(src) as im:
                im.convert("RGB").save(dst, format="JPEG", quality=92, optimize=True, progressive=True)
        except Exception as exc:
            logger.warning("Failed to export slide to docs/assets (%s): %s", src, exc)
            continue
        out_names.append(out_name)
    if not out_names:
        raise RuntimeError(f"No slide JPGs could be exported from {carousel_dir}")
    while len(out_names) < 2:
        duplicate_name = f"slide_{len(out_names) + 1:02d}.jpg"
        shutil.copyfile(
            os.path.join(docs_assets_dir, out_names[0]),
            os.path.join(docs_assets_dir, duplicate_name),
        )
        logger.warning("Duplicated %s as %s to preserve a valid Instagram carousel.", out_names[0], duplicate_name)
        out_names.append(duplicate_name)

    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "slides": out_names}
    with open(os.path.join(docs_assets_dir, "manifest.json"), "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)

    return out_names


def run_pdf(*, jobs_json: str) -> str:
    generated_at, jobs = read_jobs_json(jobs_json)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"jobs-{ts}.pdf"
    out_path = os.path.join("docs", name)
    generate_pdf(generated_at=generated_at, jobs=jobs, out_path=out_path)
    write_latest_alias(docs_dir="docs", pdf_filename=name)
    update_docs_index(docs_dir="docs", created_pdf_filename=name)
    return os.path.join("docs", "latest-jobs.pdf")


def run_youtube_video(*, jobs_json: str, carousel_dir: str) -> tuple[str, str]:
    """
    Generates voiceover, thumbnail, and a 60s Shorts video by calling the same
    underlying functions used by `video_maker.py`.
    Returns (video_path, thumbnail_path).
    """
    from video_maker import (
        _list_slide_images,
        build_voiceover_script,
        edge_tts_to_file,
        make_thumbnail,
        make_video_from_slides,
    )

    import asyncio

    pages_url = ensure_pages_url()
    _, jobs = read_jobs_json(jobs_json)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join("assets", "videos", ts)
    os.makedirs(out_dir, exist_ok=True)

    try:
        slides = _list_slide_images(carousel_dir)
    except Exception as exc:
        logger.warning("Video generation skipped because slides were unavailable: %s", exc)
        return "", ""

    # voiceover
    voice_path = os.path.join(out_dir, "voiceover.mp3")
    script = build_voiceover_script(jobs, pages_url=pages_url)
    voice = os.getenv("EDGE_TTS_VOICE", "en-US-JennyNeural").strip() or "en-US-JennyNeural"
    try:
        asyncio.run(edge_tts_to_file(text=script, out_path=voice_path, voice=voice))
    except Exception as exc:
        logger.warning("Voiceover generation failed; continuing without audio: %s", exc)
        voice_path = ""

    # thumbnail
    thumb_path = os.path.join(out_dir, "thumbnail.png")
    try:
        make_thumbnail(jobs=jobs, out_path=thumb_path)
    except Exception as exc:
        logger.warning("Thumbnail generation failed: %s", exc)
        thumb_path = ""

    # video
    video_path = os.path.join(out_dir, "shorts.mp4")
    rendered_video = make_video_from_slides(
        slide_paths=slides,
        voice_path=voice_path or None,
        out_path=video_path,
        duration_s=_env_float("YT_SHORTS_DURATION_S", 60.0),
    )

    return rendered_video or "", thumb_path


def run_full_pipeline(*, country: str, pages: int, results_per_page: int, query: str) -> None:
    jobs_json = run_scrape(country=country, pages=pages, results_per_page=results_per_page, query=query)
    carousel_dir = run_carousel(jobs_json=jobs_json)
    run_pdf(jobs_json=jobs_json)
    export_instagram_slides_to_docs_assets(carousel_dir=carousel_dir)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="JobAgent247 Orchestrator")
    p.add_argument("--mode", choices=["instagram", "instagram-upload", "youtube"], required=True)
    # ADZUNA_COUNTRY can be set but empty (e.g. repo var); getenv default does not apply then.
    p.add_argument(
        "--country",
        default=normalize_adzuna_country(os.getenv("ADZUNA_COUNTRY")),
        help="Adzuna country code (e.g. in, us, gb). Default: in if missing/blank.",
    )
    p.add_argument("--pages", type=int, default=_env_int("ADZUNA_PAGES", 2))
    p.add_argument("--results-per-page", type=int, default=_env_int("ADZUNA_RESULTS_PER_PAGE", 25))
    p.add_argument("--query", default=os.getenv("ADZUNA_QUERY", "software engineer"))
    p.add_argument("--upload", action=argparse.BooleanOptionalAction, default=True, help="Disable to run generation only.")
    return p


def main() -> None:
    # Load .env for local testing
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    args = build_arg_parser().parse_args()
    pages_url = ensure_pages_url()
    pages_base = ensure_pages_base_url()

    if args.mode == "instagram-upload":
        if not args.upload:
            logger.info("instagram-upload: upload disabled.")
            return
        manifest_path = os.path.join("docs", "assets", "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as fp:
            manifest = json.load(fp)
        slides = manifest.get("slides") or []
        if not slides:
            raise SystemExit("No slides found in docs/assets/manifest.json")
        os.environ.setdefault("GITHUB_PAGES_BASE_URL", pages_base)
        from uploader import post_instagram_carousel_from_pages_assets

        caption = build_caption(pages_pdf_url=pages_url)
        ig_id = post_instagram_carousel_from_pages_assets(slide_filenames=slides, caption=caption)
        logger.info("Instagram published media id: %s", ig_id)
        return

    jobs_json = run_scrape(
        country=args.country,
        pages=args.pages,
        results_per_page=args.results_per_page,
        query=args.query,
    )
    carousel_dir = run_carousel(jobs_json=jobs_json)
    export_instagram_slides_to_docs_assets(carousel_dir=carousel_dir)
    run_pdf(jobs_json=jobs_json)

    if args.mode == "instagram":
        if not args.upload:
            logger.info("Instagram mode: generation complete (upload disabled).")
            return
        logger.info("Instagram generation complete. Run `--mode instagram-upload` after GitHub Pages deploy.")
        return

    if args.mode == "youtube":
        video_path, thumb_path = run_youtube_video(jobs_json=jobs_json, carousel_dir=carousel_dir)
        if not video_path:
            logger.warning("YouTube generation skipped video output; continuing workflow without upload.")
            return
        if not args.upload:
            logger.info("YouTube mode: generation complete (upload disabled).")
            logger.info("Video path: %s", video_path)
            return
        try:
            from uploader import upload_youtube_video

            title = os.getenv("YT_TITLE", "Hiring Now | Freshers + Pros | Save for later").strip() or "Hiring Now | Freshers + Pros | Save for later"
            description = (
                "Save for later ✅\n\n"
                "Today’s top jobs for Freshers (0–1 yrs) and Pros (3+ yrs).\n\n"
                f"Full PDF (links + descriptions): {pages_url}\n"
            )
            vid = upload_youtube_video(
                video_path=video_path,
                title=title,
                description=description,
                tags=["jobs", "hiring", "freshers", "careers", "shorts"],
                privacy_status=os.getenv("YT_PRIVACY", "public"),
                thumbnail_path=thumb_path,
            )
            logger.info("Uploaded YouTube videoId: %s", vid)
        except Exception:
            logger.exception("YouTube upload skipped/failed.")
        return


if __name__ == "__main__":
    # If run without CLI args, execute the full generation pipeline (no uploads).
    # If run with args, use the orchestrator CLI.
    if len(sys.argv) == 1:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:
            pass
        run_full_pipeline(
            country=normalize_adzuna_country(os.getenv("ADZUNA_COUNTRY")),
            pages=_env_int("ADZUNA_PAGES", 2),
            results_per_page=_env_int("ADZUNA_RESULTS_PER_PAGE", 25),
            query=os.getenv("ADZUNA_QUERY", "software engineer"),
        )
    else:
        main()
