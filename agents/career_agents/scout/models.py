"""The job record every source produces."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from ..text import norm


@dataclass
class Job:
    source: str  # greenhouse, lever, linkedin, linkedin-post, ...
    native_id: str  # the source's own id; stable across runs
    company: str
    title: str
    location: str = ""
    url: str = ""
    description: str = ""
    posted_at: str | None = None  # YYYY-MM-DD when the source reports it
    salary: str | None = None
    kind: str = "job"  # "job" or "post" (someone announcing they're hiring)
    region: str | None = None  # region key, set by the filter
    rule_score: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        if "uid" in self.extra:  # reloaded from the store
            return self.extra["uid"]
        return hashlib.sha1(f"{self.source}:{self.native_id}".encode()).hexdigest()[:10]

    @property
    def match_key(self) -> str:
        """Identifies the same opening seen on different sources (e.g. LinkedIn and the company ATS)."""
        city = norm(self.location.split(",")[0]) if self.location else ""
        return f"{norm(self.company)}|{norm(self.title)}|{city}"
