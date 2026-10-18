"""Rule-based screening: role titles, target regions, freshness, exclusions, and a 0-100 pre-score."""

from __future__ import annotations

import re
from datetime import date, timedelta

from ..text import norm
from .models import Job

_AMBIGUOUS_LOCATION = re.compile(r"^\s*$|^\d+\s+locations?$|multiple locations", re.I)
_YEARS = re.compile(r"(?<![\d.$])(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?\+?\s*years?", re.I)


def required_years(text: str) -> int | None:
    """The largest 'N+ years' / 'N-M years' minimum a posting states (values above 25 are ignored)."""
    values = [int(m.group(1)) for m in _YEARS.finditer(text or "")]
    values = [v for v in values if 1 <= v <= 25]
    return max(values) if values else None


class Filter:
    def __init__(self, cfg: dict, companies: tuple[dict, ...] | list[dict], exclude_companies: list[str] = ()):
        roles = cfg["roles"]
        self.include = [re.compile(p, re.I) for p in roles["include"]]
        self.exclude_always = [re.compile(p, re.I) for p in roles.get("exclude_always", [])]
        self.exclude = [re.compile(p, re.I) for p in roles.get("exclude", [])]
        self.keep_if = [re.compile(p, re.I) for p in roles.get("keep_if", [])]
        self.experience_titles = [re.compile(p, re.I) for p in cfg.get("experience_titles", [])]
        years = cfg.get("experience_years") or {}
        self.min_years, self.max_years = years.get("min", 6), years.get("max", 20)
        core = cfg.get("core_functions") or {}
        self.core_pattern = re.compile(core["pattern"], re.I) if core.get("pattern") else None
        self.core_points = core.get("points", 0)
        self.seniority = [(re.compile(s["pattern"], re.I), s["points"]) for s in cfg.get("seniority", [])]
        self.regions = cfg["regions"]
        self._region_patterns = [
            (r, re.compile(r"\b(" + "|".join(re.escape(a) for a in r["aliases"]) + r")\b", re.I))
            for r in self.regions
        ]
        signals = cfg.get("b2c_signals", {})
        self.consumer_signals = [re.compile(p, re.I) for p in signals.get("consumer", [])]
        self.business_signals = [re.compile(p, re.I) for p in signals.get("business", [])]
        self.max_age_days = cfg.get("max_age_days", 30)
        self.known = {norm(c["name"]): c for c in companies}
        self.blocked = {norm(c) for c in list(cfg.get("exclude_companies") or []) + list(exclude_companies)}

    # --- individual checks -------------------------------------------------
    def title_level(self, title: str) -> str | None:
        """'senior': the title alone qualifies. 'experience': qualifies if the posting asks for 6-20 years.

        Senior titles in an excluded function survive when they also match `keep_if` (e.g. "Director,
        Product - Engineering Tools"); experience-track titles in an excluded function never do.
        """
        if any(p.search(title) for p in self.exclude_always):
            return None
        excluded = any(p.search(title) for p in self.exclude)
        if any(p.search(title) for p in self.include):
            return None if excluded and not any(p.search(title) for p in self.keep_if) else "senior"
        if not excluded and any(p.search(title) for p in self.experience_titles):
            return "experience"
        return None

    def title_ok(self, title: str) -> bool:
        return self.title_level(title) is not None

    def region_for(self, location: str) -> dict | None:
        """The highest-priority target region the location mentions (multi-location postings list several)."""
        matches = [r for r, pattern in self._region_patterns if pattern.search(location or "")]
        return min(matches, key=lambda r: r.get("priority", 9)) if matches else None

    def company_info(self, company: str) -> dict | None:
        key = norm(company)
        if key in self.known:
            return self.known[key]
        # "Amazon Web Services", "Google LLC", "Meta Platforms" -> known parent
        return next((info for name, info in self.known.items() if name and key.startswith(name + " ")), None)

    def is_blocked(self, company: str) -> bool:
        key = norm(company)
        return any(key == b or key.startswith(b + " ") for b in self.blocked if b)

    def is_fresh(self, posted_at: str | None, today: date | None = None) -> bool:
        if not posted_at:
            return True
        today = today or date.today()
        try:
            return date.fromisoformat(posted_at) >= today - timedelta(days=self.max_age_days)
        except ValueError:
            return True

    # --- used by sources before fetching full descriptions -----------------
    def wants(self, title: str, location: str) -> bool:
        if not self.title_ok(title):
            return False
        return bool(_AMBIGUOUS_LOCATION.search(location or "")) or self.region_for(location) is not None

    # --- final decision ----------------------------------------------------
    def accept(self, job: Job) -> bool:
        """Screen a job; on success sets job.region and job.rule_score."""
        if self.is_blocked(job.company) or not self.is_fresh(job.posted_at):
            return False
        region = self.region_for(job.location)
        if job.kind == "post":  # Claude already matched role and region; trust a missing location
            job.region = region["key"] if region else None
            job.rule_score = self.score(job, region)
            return True
        level = self.title_level(job.title)
        if level is None or region is None:
            return False
        years = required_years(job.description)
        job.extra["years"] = years
        if level == "experience" and not (years and self.min_years <= years <= self.max_years):
            return False
        if region.get("require_us_mnc") and not (self.company_info(job.company) or {}).get("us_mnc"):
            return False
        job.region = region["key"]
        job.rule_score = self.score(job, region)
        return True

    def score(self, job: Job, region: dict | None) -> int:
        points = next((pts for pattern, pts in self.seniority if pattern.search(job.title)), 15)
        if self.core_pattern and self.core_pattern.search(job.title):
            points += self.core_points
        if job.extra.get("years") and 8 <= job.extra["years"] <= 15:  # right in the candidate's band
            points += 5
        priority = (region or {}).get("priority", 3)
        points += max(0, 30 - 8 * (priority - 1))
        text = f"{job.title}\n{job.description}"
        consumer = sum(1 for p in self.consumer_signals if p.search(text))
        business = sum(1 for p in self.business_signals if p.search(text))
        if self.company_info(job.company) or job.extra.get("consumer_b2c"):
            points += 20
        points += max(-10, min(10, 3 * (consumer - business)))
        if job.posted_at and self.is_fresh(job.posted_at) and job.posted_at >= (date.today() - timedelta(days=7)).isoformat():
            points += 10
        return max(0, min(100, points))


def dedupe(jobs: list[Job]) -> list[Job]:
    """Collapse the same opening seen on several sources, preferring the company's own ATS listing."""
    preference = {"greenhouse": 0, "lever": 0, "ashby": 0, "smartrecruiters": 0, "workday": 0, "amazon": 0}
    best: dict[str, Job] = {}
    for job in jobs:
        key = job.match_key if job.kind == "job" else f"post|{job.native_id}"
        current = best.get(key)
        if current is None or (preference.get(job.source, 1), -len(job.description)) < (
            preference.get(current.source, 1),
            -len(current.description),
        ):
            best[key] = job
    return list(best.values())
