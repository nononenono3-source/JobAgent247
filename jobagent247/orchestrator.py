from __future__ import annotations

import argparse
import os

from .ingestion.adzuna import fetch_jobs, normalize_adzuna_country
from .state.db import save_jobs
from .utils.logging import get_logger

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"Warning: invalid integer for {name}={raw!r}; using {default}.")
        return default


def run_ingestion_pipeline(*, country: str, pages: int, results_per_page: int, query: str) -> None:
    """
    Runs the full data ingestion pipeline: fetch -> clean -> save.
    """
    logger.info("Starting ingestion pipeline...")
    jobs = fetch_jobs(
        country=country,
        pages=pages,
        results_per_page=results_per_page,
        query=query,
        where=None,
        remote=None,
        max_days_old=10,
    )
    logger.info(f"Fetched {len(jobs)} jobs.")

    out_path = os.path.join("data", "jobs.json")
    save_jobs(jobs=jobs, path=out_path)
    logger.info(f"Saved jobs to {out_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="JobAgent247 Orchestrator")
    p.add_argument(
        "--country",
        default=normalize_adzuna_country(os.getenv("ADZUNA_COUNTRY")),
        help="Adzuna country code (e.g. in, us, gb). Default: in if missing/blank.",
    )
    p.add_argument("--pages", type=int, default=_env_int("ADZUNA_PAGES", 2))
    p.add_argument("--results-per-page", type=int, default=_env_int("ADZUNA_RESULTS_PER_PAGE", 25))
    p.add_argument("--query", default=os.getenv("ADZUNA_QUERY", "software engineer"))
    return p


def main() -> None:
    # Load .env for local testing
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    args = build_arg_parser().parse_args()
    run_ingestion_pipeline(
        country=args.country,
        pages=args.pages,
        results_per_page=args.results_per_page,
        query=args.query,
    )


if __name__ == "__main__":
    main()
