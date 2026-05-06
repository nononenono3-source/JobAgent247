from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

from ..state.models import Job
from ..utils.logging import get_logger
from .cleaning import normalize_adzuna_result


logger = get_logger(__name__)


DEFAULT_ADZUNA_COUNTRY = "in"


def normalize_adzuna_country(code: str | None) -> str:
    """
    Adzuna paths use /jobs/{country}/search/... Empty or whitespace breaks the URL.

    Env var ADZUNA_COUNTRY can be present but blank (GitHub Variables / dotenv).
    Using os.getenv("X", default) alone does NOT fall back when X is empty string.
    """
    c = (code or "").strip().lower()
    return c if c else DEFAULT_ADZUNA_COUNTRY


class AdzunaClient:
    def __init__(
        self,
        *,
        app_id: str,
        app_key: str,
        session: Optional[requests.Session] = None,
        timeout_s: int = 30,
        user_agent: str = "JobAgent247/1.0 (+https://github.com/)",
    ) -> None:
        self.app_id = app_id
        self.app_key = app_key
        self.session = session or requests.Session()
        self.timeout_s = timeout_s
        self.session.headers.update({"User-Agent": user_agent})

    def search(
        self,
        *,
        country: str,
        page: int,
        results_per_page: int,
        what: str,
        where: str | None = None,
        remote: bool | None = None,
        sort_by: str = "date",
        max_days_old: int | None = 10,
    ) -> dict[str, Any]:
        """
        Adzuna Search endpoint:
        https://developer.adzuna.com/activedocs#!/adzuna/search
        """
        country = normalize_adzuna_country(country)
        base = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        params: dict[str, Any] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": results_per_page,
            "what": what,
            "sort_by": sort_by,
            "content-type": "application/json",
        }
        if where:
            params["where"] = where
        if max_days_old is not None:
            params["max_days_old"] = max_days_old
        # Adzuna doesn't have a universal "remote" flag across all markets.
        # We approximate by injecting remote terms into search query.
        if remote is True:
            params["what"] = f"{what} remote OR wfh OR work from home"
        elif remote is False:
            pass

        resp = self.session.get(base, params=params, timeout=self.timeout_s)
        resp.raise_for_status()
        return resp.json()


def fetch_jobs(
    *,
    country: str,
    pages: int,
    results_per_page: int,
    query: str,
    where: str | None,
    remote: bool | None,
    max_days_old: int | None,
    rate_limit_s: float = 1.0,
    max_retries: int = 3,
    retry_delay_s: float = 2.0,
) -> list[Job]:
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise SystemExit(
            "Missing Adzuna credentials. Set env vars ADZUNA_APP_ID and ADZUNA_APP_KEY."
        )

    country = normalize_adzuna_country(country)
    client = AdzunaClient(app_id=app_id, app_key=app_key)
    jobs: list[Job] = []

    for page in range(1, pages + 1):
        for attempt in range(max_retries):
            try:
                payload = client.search(
                    country=country,
                    page=page,
                    results_per_page=results_per_page,
                    what=query,
                    where=where,
                    remote=remote,
                    max_days_old=max_days_old,
                )
                break  # Success, exit retry loop
            except requests.RequestException as exc:
                logger.warning(f"Adzuna page {page} fetch failed (attempt {attempt + 1}/{max_retries}): {exc}")
                if attempt + 1 == max_retries:
                    # If it's the last attempt, we'll just continue to the next page
                    payload = None
                else:
                    time.sleep(retry_delay_s)
            except ValueError as exc:
                logger.warning(f"Adzuna page {page} returned invalid JSON: {exc}")
                payload = None
                break  # Don't retry on JSON error

        if not payload:
            continue

        if not isinstance(payload, dict):
            logger.warning(f"Adzuna page {page} returned unexpected payload type: {type(payload).__name__}")
            time.sleep(rate_limit_s)
            continue

        results = payload.get("results", []) or []
        if not isinstance(results, list):
            logger.warning(f"Adzuna page {page} results payload was not a list.")
            time.sleep(rate_limit_s)
            continue

        for item in results:
            if not isinstance(item, dict):
                continue
            job = normalize_adzuna_result(country, item)
            if job.url:
                jobs.append(job)

        time.sleep(rate_limit_s)

    return jobs
