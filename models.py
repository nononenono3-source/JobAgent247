from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Optional


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


Category = Literal["fresher", "pro", "uncategorized"]


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


def read_jobs_json(path: str) -> tuple[str, list[Job]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    generated_at = str(payload.get("generated_at", "")).strip() if isinstance(payload, dict) else ""
    jobs_raw = payload.get("jobs", payload) if isinstance(payload, dict) else payload
    jobs: list[Job] = []
    for item in jobs_raw if isinstance(jobs_raw, list) else []:
        if not isinstance(item, dict):
            continue
        jobs.append(
            Job(
                category=safe_text(item.get("category"), "uncategorized"),
                title=safe_text(item.get("title"), "No title provided"),
                company=safe_text(item.get("company")),
                location=safe_text(item.get("location")),
                is_remote=bool(item.get("is_remote", False)),
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                salary_currency=item.get("salary_currency"),
                url=safe_text(item.get("url")),
                description=safe_text(item.get("description"), "No description provided"),
                source=safe_text(item.get("source")),
                country=safe_text(item.get("country")),
            )
        )
    return generated_at, jobs
