"""LinkedIn, Indeed, Glassdoor, Google Jobs and Naukri via python-jobspy.

JobSpy reads public search pages, which these sites' terms restrict. Keep volumes low (the defaults
in search.yaml make a few dozen requests a day), run from a home connection, and treat a 429 as a
signal to back off. If you'd rather avoid scraping LinkedIn entirely, drop it from `sites` and rely
on LinkedIn's own job-alert emails plus the `posts` source.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ...text import clean, iso_date
from ..models import Job


def _salary(row: dict) -> str | None:
    low, high = (clean(row.get(k)) for k in ("min_amount", "max_amount"))
    low, high = (f"{float(v):,.0f}" if v else "" for v in (low, high))
    if not (low or high):
        return None
    span = f"{low}-{high}" if low and high else f"{low or high}+" if low else f"up to {high}"
    return f"{span} {clean(row.get('currency'))} {clean(row.get('interval'))}".strip()


def fetch(cfg: dict, log: Callable[[str], None]) -> list[Job]:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        log('boards: python-jobspy is not installed - run: pip install -e ".[boards]"')
        return []

    opts = cfg["sources"]["boards"]
    jobs: list[Job] = []
    for region in cfg["regions"]:
        board = region.get("boards")
        if not board:
            continue
        for term in opts["search_terms"]:
            try:
                frame = scrape_jobs(
                    site_name=board["sites"],
                    search_term=term,
                    google_search_term=f"{term} jobs in {board['location']} since last week",
                    location=board["location"],
                    country_indeed=board.get("country_indeed", "usa"),
                    results_wanted=opts.get("results_per_query", 25),
                    hours_old=opts.get("hours_old", 72),
                    fetch_description=True,
                    verbose=0,
                )
            except Exception as exc:  # one blocked site shouldn't stop the run
                log(f"boards: {region['key']} / {term!r} failed: {exc}")
                continue
            for row in frame.to_dict("records"):
                url = clean(row.get("job_url"))
                jobs.append(
                    Job(
                        source=clean(row.get("site")) or "board",
                        native_id=clean(row.get("id")) or url,
                        company=clean(row.get("company")),
                        title=clean(row.get("title")),
                        location=clean(row.get("location")),
                        url=clean(row.get("job_url_direct")) or url,
                        description=clean(row.get("description")),
                        posted_at=iso_date(row.get("date_posted")),
                        salary=_salary(row),
                    )
                )
            time.sleep(opts.get("pause_seconds", 4))
    return jobs
