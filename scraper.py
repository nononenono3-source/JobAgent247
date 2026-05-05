from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional

import requests


DEFAULT_ADZUNA_COUNTRY = "in"

Category = Literal["fresher", "pro", "uncategorized"]


def normalize_adzuna_country(code: str | None) -> str:
    """
    Adzuna paths use /jobs/{country}/search/... Empty or whitespace breaks the URL.

    Env var ADZUNA_COUNTRY can be present but blank (GitHub Variables / dotenv).
    Using os.getenv("X", default) alone does NOT fall back when X is empty string.
    """
    c = (code or "").strip().lower()
    return c if c else DEFAULT_ADZUNA_COUNTRY


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


_YEAR_PATTERNS: list[re.Pattern[str]] = [
    # "3+ years", "3 years", "3 yrs"
    re.compile(r"(?<!\d)(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE),
    # "minimum 3 years", "at least 3 years"
    re.compile(r"(?:minimum|at\s+least)\s*(\d{1,2})\s*(?:years?|yrs?)\b", re.IGNORECASE),
]


def estimate_years_experience(text: str) -> Optional[int]:
    """
    Heuristic extraction from description/title; returns minimal required years if found.
    """
    if not text:
        return None
    for pat in _YEAR_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
    return None


def is_entry_level(title: str, description: str) -> bool:
    blob = f"{title}\n{description}".lower()
    entry_terms = [
        "entry level",
        "entry-level",
        "graduate",
        "fresher",
        "junior",
        "intern",
        "trainee",
        "associate",
        "no experience",
        "0-1 year",
        "0 to 1 year",
    ]
    return any(t in blob for t in entry_terms)


def is_senior_level(title: str, description: str) -> bool:
    blob = f"{title}\n{description}".lower()
    senior_terms = [
        "senior",
        "lead",
        "principal",
        "staff",
        "architect",
        "manager",
        "head of",
        "director",
        "mid-senior",
        "mid senior",
    ]
    return any(t in blob for t in senior_terms)


def detect_remote(location: str, description: str) -> bool:
    blob = f"{location}\n{description}".lower()
    return any(
        t in blob
        for t in [
            "remote",
            "work from home",
            "wfh",
            "hybrid",
            "telecommute",
        ]
    )


def categorize_job(*, title: str, description: str) -> Category:
    years = estimate_years_experience(f"{title}\n{description}")

    # Hard rules from years when present
    if years is not None:
        if years <= 1:
            return "fresher"
        if years >= 3:
            return "pro"

    # Title/keyword heuristics
    if is_entry_level(title, description):
        return "fresher"
    if is_senior_level(title, description):
        return "pro"

    return "uncategorized"


def _safe_get(obj: dict[str, Any], path: Iterable[str], default: str = "") -> str:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur if isinstance(cur, str) else default


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def normalize_adzuna_result(country: str, item: dict[str, Any]) -> Job:
    title = _safe_text(item.get("title"), "Untitled")
    company = _safe_get(item, ["company", "display_name"], default="").strip() or "Unknown"
    location = _safe_get(item, ["location", "display_name"], default="").strip() or "Unknown"
    description = _safe_text(item.get("description"), "Description not provided.")
    url = _safe_text(item.get("redirect_url") or item.get("adref"))

    salary_min = _safe_float(item.get("salary_min"))
    salary_max = _safe_float(item.get("salary_max"))
    salary_currency = _safe_text(item.get("salary_currency")) or None

    is_remote = detect_remote(location, description)
    category = categorize_job(title=title, description=description)

    return Job(
        category=category,
        title=title or "Untitled",
        company=company,
        location=location,
        is_remote=is_remote,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        url=url,
        description=description,
        source="adzuna",
        country=country,
    )


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
        except requests.RequestException as exc:
            print(f"Warning: Adzuna page {page} fetch failed: {exc}")
            time.sleep(rate_limit_s)
            continue
        except ValueError as exc:
            print(f"Warning: Adzuna page {page} returned invalid JSON: {exc}")
            time.sleep(rate_limit_s)
            continue

        if not isinstance(payload, dict):
            print(f"Warning: Adzuna page {page} returned unexpected payload type: {type(payload).__name__}")
            time.sleep(rate_limit_s)
            continue

        results = payload.get("results", []) or []
        if not isinstance(results, list):
            print(f"Warning: Adzuna page {page} results payload was not a list.")
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


def write_json(path: str, jobs: list[Job]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(jobs),
        "by_category": {
            "fresher": sum(1 for j in jobs if j.category == "fresher"),
            "pro": sum(1 for j in jobs if j.category == "pro"),
            "uncategorized": sum(1 for j in jobs if j.category == "uncategorized"),
        },
        "jobs": [asdict(j) for j in jobs],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch and categorize global jobs via Adzuna.")
    p.add_argument("--country", default="in", help="Adzuna country code (e.g. in, us, gb).")
    p.add_argument("--pages", type=int, default=2, help="How many pages to fetch.")
    p.add_argument("--results-per-page", type=int, default=25, help="Jobs per page.")
    p.add_argument("--query", default="software engineer", help="Search query for roles.")
    p.add_argument("--where", default=None, help="Optional location filter (city/region).")
    p.add_argument(
        "--remote",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Approximate remote jobs (injects remote keywords).",
    )
    p.add_argument("--max-days-old", type=int, default=10, help="Only jobs newer than N days.")
    p.add_argument("--out", default=os.path.join("data", "jobs.json"), help="Output JSON path.")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    jobs = fetch_jobs(
        country=normalize_adzuna_country(args.country),
        pages=args.pages,
        results_per_page=args.results_per_page,
        query=args.query,
        where=args.where,
        remote=args.remote,
        max_days_old=args.max_days_old,
    )
    write_json(args.out, jobs)
    print(f"Wrote {len(jobs)} jobs to {args.out}")


if __name__ == "__main__":
    main()

