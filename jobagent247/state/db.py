from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .models import Job


def save_jobs(*, jobs: list[Job], path: str) -> None:
    """
    Saves a list of Job objects to a JSON file.
    """
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


def load_jobs(*, path: str) -> list[Job]:
    """
    Loads a list of Job objects from a JSON file.
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    jobs_raw = payload.get("jobs", payload) if isinstance(payload, dict) else payload
    jobs: list[Job] = []
    for item in jobs_raw if isinstance(jobs_raw, list) else []:
        if not isinstance(item, dict):
            continue
        jobs.append(
            Job(
                category=_safe_text(item.get("category"), "uncategorized"),
                title=_safe_text(item.get("title"), "No title provided"),
                company=_safe_text(item.get("company")),
                location=_safe_text(item.get("location")),
                is_remote=bool(item.get("is_remote", False)),
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                salary_currency=item.get("salary_currency"),
                url=_safe_text(item.get("url")),
                description=_safe_text(item.get("description"), "No description provided"),
                source=_safe_text(item.get("source")),
                country=_safe_text(item.get("country")),
            )
        )
    return jobs


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default
