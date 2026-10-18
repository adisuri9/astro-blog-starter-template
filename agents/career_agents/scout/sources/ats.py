"""Public job-board APIs of applicant tracking systems (Greenhouse, Lever, Ashby, SmartRecruiters, Workday).

These are the endpoints companies' own career pages call; they need no login or key. Each fetcher
screens titles from the listing first and only fetches full descriptions for plausible matches.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

import requests

from ...text import html_to_text, iso_date
from ..models import Job

TIMEOUT = 25
HEADERS = {"User-Agent": "Mozilla/5.0 (career-agents personal job search)", "Accept": "application/json"}

# wants(title, location) -> bool : cheap pre-screen before fetching job details
Wants = Callable[[str, str], bool]


def _get(session: requests.Session, url: str, **params) -> dict | list:
    resp = session.get(url, params=params or None, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def greenhouse(session: requests.Session, company: dict, wants: Wants, terms: Iterable[str] = ()) -> list[Job]:
    token = company["slug"]
    base = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    jobs = []
    for item in _get(session, base)["jobs"]:
        location = (item.get("location") or {}).get("name", "")
        if not wants(item["title"], location):
            continue
        detail = _get(session, f"{base}/{item['id']}")
        jobs.append(
            Job(
                source="greenhouse",
                native_id=f"{token}:{item['id']}",
                company=company["name"],
                title=item["title"].strip(),
                location=location,
                url=item.get("absolute_url", ""),
                description=html_to_text(detail.get("content")),
                posted_at=iso_date(item.get("first_published") or item.get("updated_at")),
            )
        )
    return jobs


def lever(session: requests.Session, company: dict, wants: Wants, terms: Iterable[str] = ()) -> list[Job]:
    host = "api.eu.lever.co" if company.get("region") == "eu" else "api.lever.co"
    jobs = []
    for post in _get(session, f"https://{host}/v0/postings/{company['slug']}", mode="json"):
        cats = post.get("categories") or {}
        location = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        if not wants(post["text"], location):
            continue
        sections = [post.get("descriptionPlain", "")]
        sections += [f"{s.get('text', '')}\n{html_to_text(s.get('content'))}" for s in post.get("lists") or []]
        sections.append(post.get("additionalPlain", ""))
        pay = post.get("salaryRange") or {}
        salary = (
            f"{pay.get('min')}-{pay.get('max')} {pay.get('currency', '')} {pay.get('interval', '')}".strip()
            if pay.get("min")
            else None
        )
        jobs.append(
            Job(
                source="lever",
                native_id=f"{company['slug']}:{post['id']}",
                company=company["name"],
                title=post["text"].strip(),
                location=location,
                url=post.get("hostedUrl", ""),
                description="\n\n".join(s for s in sections if s).strip(),
                posted_at=iso_date(post.get("createdAt")),
                salary=salary,
            )
        )
    return jobs


def ashby(session: requests.Session, company: dict, wants: Wants, terms: Iterable[str] = ()) -> list[Job]:
    data = _get(
        session,
        f"https://api.ashbyhq.com/posting-api/job-board/{company['slug']}",
        includeCompensation="true",
    )
    jobs = []
    for post in data.get("jobs", []):
        if post.get("isListed") is False:
            continue
        places = [post.get("location") or ""] + [s.get("location", "") for s in post.get("secondaryLocations") or []]
        location = " / ".join(p for p in places if p)
        if post.get("isRemote"):
            location = f"{location} (Remote)".strip()
        if not wants(post["title"], location):
            continue
        comp = post.get("compensation") or {}
        jobs.append(
            Job(
                source="ashby",
                native_id=f"{company['slug']}:{post['id']}",
                company=company["name"],
                title=post["title"].strip(),
                location=location,
                url=post.get("jobUrl", ""),
                description=post.get("descriptionPlain") or html_to_text(post.get("descriptionHtml")),
                posted_at=iso_date(post.get("publishedAt")),
                salary=comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary"),
            )
        )
    return jobs


def smartrecruiters(session: requests.Session, company: dict, wants: Wants, terms: Iterable[str] = ()) -> list[Job]:
    slug = company["slug"]
    base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    jobs, seen = [], set()
    for term in terms:
        for post in _get(session, base, q=term, limit=100).get("content", []):
            if post["id"] in seen:
                continue
            seen.add(post["id"])
            loc = post.get("location") or {}
            location = loc.get("fullLocation") or ", ".join(
                p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p
            )
            if loc.get("remote"):
                location = f"{location} (Remote)".strip()
            if not wants(post["name"], location):
                continue
            detail = _get(session, f"{base}/{post['id']}")
            sections = (detail.get("jobAd") or {}).get("sections") or {}
            description = "\n\n".join(
                html_to_text((sections.get(key) or {}).get("text"))
                for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation")
            ).strip()
            jobs.append(
                Job(
                    source="smartrecruiters",
                    native_id=f"{slug}:{post['id']}",
                    company=company["name"],
                    title=post["name"].strip(),
                    location=location,
                    url=detail.get("postingUrl") or f"https://jobs.smartrecruiters.com/{slug}/{post['id']}",
                    description=description,
                    posted_at=iso_date(post.get("releasedDate")),
                )
            )
    return jobs


def workday(session: requests.Session, company: dict, wants: Wants, terms: Iterable[str] = ()) -> list[Job]:
    wd = company["workday"]
    base = f"https://{wd['host']}/wday/cxs/{wd['tenant']}/{wd['site']}"
    jobs, seen = [], set()
    for term in terms:
        for offset in range(0, 200, 20):  # Workday pages are capped at 20; broad terms need several
            resp = session.post(
                f"{base}/jobs",
                json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            postings = resp.json().get("jobPostings") or []
            for post in postings:
                path = post.get("externalPath")
                if not path or path in seen:
                    continue
                seen.add(path)
                if not wants(post.get("title", ""), post.get("locationsText", "")):
                    continue
                info = _get(session, f"{base}{path}").get("jobPostingInfo") or {}
                places = [info.get("location") or post.get("locationsText", "")] + list(
                    info.get("additionalLocations") or []
                )
                jobs.append(
                    Job(
                        source="workday",
                        native_id=f"{wd['tenant']}:{path}",
                        company=company["name"],
                        title=(info.get("title") or post["title"]).strip(),
                        location=" / ".join(p for p in places if p),
                        url=info.get("externalUrl") or f"https://{wd['host']}/{wd['site']}{path}",
                        description=html_to_text(info.get("jobDescription")),
                        posted_at=iso_date(info.get("startDate")),
                    )
                )
            if len(postings) < 20:
                break
    return jobs


FETCHERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "smartrecruiters": smartrecruiters,
    "workday": workday,
}


def probe(session: requests.Session, company: dict) -> int:
    """Fetch only the listing for a company's board; returns the number of open postings (for `scout doctor`)."""
    ats = company["ats"]
    if ats == "greenhouse":
        return len(_get(session, f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs")["jobs"])
    if ats == "lever":
        host = "api.eu.lever.co" if company.get("region") == "eu" else "api.lever.co"
        return len(_get(session, f"https://{host}/v0/postings/{company['slug']}", mode="json"))
    if ats == "ashby":
        return len(_get(session, f"https://api.ashbyhq.com/posting-api/job-board/{company['slug']}").get("jobs", []))
    if ats == "smartrecruiters":
        url = f"https://api.smartrecruiters.com/v1/companies/{company['slug']}/postings"
        return int(_get(session, url, limit=1).get("totalFound", 0))
    if ats == "workday":
        wd = company["workday"]
        resp = session.post(
            f"https://{wd['host']}/wday/cxs/{wd['tenant']}/{wd['site']}/jobs",
            json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return int(resp.json().get("total", 0))
    raise ValueError(f"no public API for ats={ats!r}")
