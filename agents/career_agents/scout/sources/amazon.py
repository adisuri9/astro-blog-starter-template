"""amazon.jobs search API (the JSON endpoint behind the public search page)."""

from __future__ import annotations

import requests

from ...text import html_to_text, iso_date
from ..models import Job
from .ats import HEADERS, TIMEOUT, Wants


def fetch(session: requests.Session, terms: list[str], locations: list[str], wants: Wants) -> list[Job]:
    jobs, seen = [], set()
    for location in locations:
        for term in terms:
            resp = session.get(
                "https://www.amazon.jobs/en/search.json",
                params={"base_query": term, "loc_query": location, "result_limit": 100, "sort": "recent"},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            for post in resp.json().get("jobs", []):
                job_id = str(post.get("id_icims") or post.get("id"))
                if job_id in seen:
                    continue
                seen.add(job_id)
                where = post.get("normalized_location") or post.get("location", "")
                if not wants(post.get("title", ""), where):
                    continue
                sections = [
                    post.get("description", ""),
                    "Basic qualifications:\n" + post.get("basic_qualifications", ""),
                    "Preferred qualifications:\n" + post.get("preferred_qualifications", ""),
                ]
                jobs.append(
                    Job(
                        source="amazon",
                        native_id=job_id,
                        company=post.get("company_name") or "Amazon",
                        title=post["title"].strip(),
                        location=where,
                        url="https://www.amazon.jobs" + post.get("job_path", ""),
                        description=html_to_text("<br/>".join(sections)),
                        posted_at=iso_date(post.get("posted_date")),
                    )
                )
    return jobs
