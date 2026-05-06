from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


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
