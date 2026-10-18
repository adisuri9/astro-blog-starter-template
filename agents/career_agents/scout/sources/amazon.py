"""amazon.jobs search API (the JSON endpoint behind the public search page).

The endpoint ignores free-text locations and treats multi-word queries as narrow phrases, so Scout
searches broad single keywords per country and leaves title/city matching to the filter.
"""

from __future__ import annotations

import requests

from ...text import html_to_text, iso_date
from ..models import Job
from .ats import HEADERS, TIMEOUT, Wants

PAGE = 100
MAX_PER_QUERY = 500


def fetch(session: requests.Session, terms: list[str], countries: list[str], wants: Wants) -> list[Job]:
    jobs, seen = [], set()
    for country in countries:
        for term in terms:
            offset, hits = 0, 1
            while offset < min(hits, MAX_PER_QUERY):
                resp = session.get(
                    "https://www.amazon.jobs/en/search.json",
                    params={"base_query": term, "country": country, "result_limit": PAGE, "offset": offset,
                            "sort": "recent"},
                    headers=HEADERS,
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                hits, page = int(data.get("hits") or 0), data.get("jobs") or []
                for post in page:
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
                if len(page) < PAGE:
                    break
                offset += PAGE
    return jobs
