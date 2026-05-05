from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from designer import build_carousel, _read_jobs_json as read_jobs_for_design
from pdf_generator import _read_jobs_json as read_jobs_for_pdf, generate_pdf, update_docs_index, write_latest_alias
from scraper import fetch_jobs, write_json


def build_caption(*, pages_pdf_url: str) -> str:
    return (
        "SAVE for later ✅\n\n"
        "Freshers (0–1 yrs) + Pros (3+ yrs): today’s best roles.\n"
        "Recruiters: share this with your team.\n\n"
        f"Full descriptions + links (PDF): {pages_pdf_url}\n\n"
        "#jobs #hiring #freshers #careers #softwarejobs"
    )


def ensure_pages_url() -> str:
    """
    Stable URL to docs/latest-jobs.pdf. Prefer env override in Actions.
    """
    v = os.getenv("GITHUB_PAGES_PDF_URL", "").strip()
    if v:
        return v
    return "https://[your-username].github.io/[repo-name]/docs/latest-jobs.pdf"


def ensure_pages_base_url() -> str:
    """
    Base URL where your GitHub Pages site is served.
    Example: https://<user>.github.io/<repo>
    """
    v = os.getenv("GITHUB_PAGES_BASE_URL", "").strip()
    if v:
        return v.rstrip("/")
    return "https://[your-username].github.io/[repo-name]"


def run_scrape(*, country: str, pages: int, results_per_page: int, query: str) -> str:
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
    jobs = read_jobs_for_design(jobs_json)
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
        im = Image.open(src).convert("RGB")
        im.save(dst, format="JPEG", quality=92, optimize=True, progressive=True)
        out_names.append(out_name)

    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "slides": out_names}
    with open(os.path.join(docs_assets_dir, "manifest.json"), "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)

    return out_names


def run_pdf(*, jobs_json: str) -> str:
    generated_at, jobs = read_jobs_for_pdf(jobs_json)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"jobs-{ts}.pdf"
    out_path = os.path.join("docs", name)
    generate_pdf(generated_at=generated_at, jobs=jobs, out_path=out_path)
    write_latest_alias(docs_dir="docs", pdf_filename=name)
    update_docs_index(docs_dir="docs", created_pdf_filename=name)
    return os.path.join("docs", "latest-jobs.pdf")


def run_youtube_video(*, jobs_json: str, carousel_dir: str) -> tuple[str, str]:
    from video_maker import (
        _list_slide_images,
        build_voiceover_script,
        edge_tts_to_file,
        make_thumbnail,
        make_video_from_slides,
        _read_jobs_json,
    )
    import asyncio

    pages_url = ensure_pages_url()
    _, jobs = _read_jobs_json(jobs_json)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join("assets", "videos", ts)
    os.makedirs(out_dir, exist_ok=True)

    slides = _list_slide_images(carousel_dir)
    voice_path = os.path.join(out_dir, "voiceover.mp3")
    script = build_voiceover_script(jobs, pages_url=pages_url)
    voice = os.getenv("EDGE_TTS_VOICE", "en-US-JennyNeural").strip() or "en-US-JennyNeural"
    asyncio.run(edge_tts_to_file(text=script, out_path=voice_path, voice=voice))

    thumb_path = os.path.join(out_dir, "thumbnail.png")
    make_thumbnail(jobs=jobs, out_path=thumb_path)

    video_path = os.path.join(out_dir, "shorts.mp4")
    make_video_from_slides(slide_paths=slides, voice_path=voice_path, out_path=video_path, duration_s=60.0)

    return video_path, thumb_path


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="JobAgent247 Orchestrator")
    p.add_argument("--mode", choices=["instagram", "instagram-upload", "youtube"], required=True)
    p.add_argument("--country", default=os.getenv("ADZUNA_COUNTRY", "in"))
    p.add_argument("--pages", type=int, default=int(os.getenv("ADZUNA_PAGES", "2")))
    p.add_argument("--results-per-page", type=int, default=int(os.getenv("ADZUNA_RESULTS_PER_PAGE", "25")))
    p.add_argument("--query", default=os.getenv("ADZUNA_QUERY", "software engineer"))
    p.add_argument("--upload", action=argparse.BooleanOptionalAction, default=True, help="Disable to run generation only.")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    pages_url = ensure_pages_url()
    pages_base = ensure_pages_base_url()

    if args.mode == "instagram-upload":
        if not args.upload:
            print("instagram-upload: upload disabled.")
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
        print(f"Instagram published media id: {ig_id}")
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
            print("Instagram mode: generation complete (upload disabled).")
            return
        print("Instagram generation complete. Run `--mode instagram-upload` after GitHub Pages deploy.")
        return

    if args.mode == "youtube":
        video_path, thumb_path = run_youtube_video(jobs_json=jobs_json, carousel_dir=carousel_dir)
        if not args.upload:
            print("YouTube mode: generation complete (upload disabled).")
            print(video_path)
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
            print(f"Uploaded YouTube videoId: {vid}")
        except Exception as e:
            print(f"YouTube upload skipped/failed: {e}")
        return


if __name__ == "__main__":
    main()

