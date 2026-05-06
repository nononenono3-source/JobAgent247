from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from ..state.models import Category, Job


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
    title = _safe_text(item.get("title"), "No title provided")
    company = _safe_get(item, ["company", "display_name"], default="").strip() or "Unknown"
    location = _safe_get(item, ["location", "display_name"], default="").strip() or "Unknown"
    description = _safe_text(item.get("description"), "No description provided")
    url = _safe_text(item.get("redirect_url") or item.get("adref"))

    salary_min = _safe_float(item.get("salary_min"))
    salary_max = _safe_float(item.get("salary_max"))
    salary_currency = _safe_text(item.get("salary_currency")) or None

    is_remote = detect_remote(location, description)
    category = categorize_job(title=title, description=description)

    return Job(
        category=category,
        title=title or "No title provided",
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
