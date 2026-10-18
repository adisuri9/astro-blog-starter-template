"""One Scout run: collect -> screen -> de-duplicate -> store -> score with Claude -> digest -> notify."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from .. import config, llm
from . import digest, notify
from .filters import Filter, dedupe
from .models import Job
from .scorer import assess_many
from .sources import amazon, ats, boards, posts
from .store import Store

ALL_SOURCES = ("ats", "amazon", "boards", "posts")


def enabled_sources(cfg: dict) -> set[str]:
    return {name for name in ALL_SOURCES if cfg.get("sources", {}).get(name, {}).get("enabled", True)}


def collect(sources: set[str], cfg: dict, flt: Filter, log: Callable[[str], None], roles: list[str] | None = None):
    jobs: list[Job] = []
    counts: Counter = Counter()
    terms = cfg.get("keyword_search_terms", [])

    if "ats" in sources:
        companies = [c for c in config.companies() if c.get("ats") in ats.FETCHERS]

        def crawl(company: dict):
            with requests.Session() as session:
                try:
                    return company, ats.FETCHERS[company["ats"]](session, company, flt.wants, terms), None
                except Exception as exc:
                    return company, [], exc

        with ThreadPoolExecutor(max_workers=8) as pool:
            for company, found, exc in pool.map(crawl, companies):
                if exc:
                    log(f"ats: {company['name']} ({company['ats']}/{company.get('slug', '')}): {exc}")
                jobs += found
                counts[company["ats"]] += len(found)

    if "amazon" in sources:
        countries = list(dict.fromkeys(r["amazon_country"] for r in cfg["regions"] if r.get("amazon_country")))
        amazon_terms = cfg.get("sources", {}).get("amazon", {}).get("search_terms") or ["director", "head of"]
        try:
            with requests.Session() as session:
                found = amazon.fetch(session, amazon_terms, countries, flt.wants)
            jobs += found
            counts["amazon"] += len(found)
        except Exception as exc:
            log(f"amazon: {exc}")

    if "boards" in sources:
        found = boards.fetch(cfg, log)
        jobs += found
        counts.update(job.source for job in found)

    if "posts" in sources:
        if llm.has_credentials():
            found = posts.fetch(cfg, log, roles)
            jobs += found
            counts["linkedin-post"] += len(found)
        else:
            log("posts: skipped (no Claude credentials; set ANTHROPIC_API_KEY)")

    return jobs, dict(counts)


def run(sources: set[str], use_llm: bool, send: bool, log: Callable[[str], None] = print) -> dict:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cfg = config.search_config()
    profile = config.profile()
    flt = Filter(cfg, config.companies(), profile.get("exclude_companies") or [])
    errors: list[str] = []

    def log_error(message: str) -> None:
        errors.append(message)
        log(f"  ! {message}")

    log(f"Scout: collecting from {', '.join(sorted(sources))} ...")
    fetched, counts = collect(sources, cfg, flt, log_error, (profile.get("targets") or {}).get("titles"))
    screened = dedupe([job for job in fetched if flt.accept(job)])
    store = Store(config.data_path("scout.db"))
    new = store.upsert(screened)
    stats = {"fetched": len(fetched), "screened": len(screened), "new": len(new), "by_source": counts, "errors": errors}
    log(f"  {len(fetched)} postings fetched, {len(screened)} match your roles and regions, {len(new)} new")

    scored_uids: list[str] = []
    if use_llm and llm.has_credentials():
        scoring = cfg.get("scoring", {})
        todo = store.unscored(scoring.get("min_rule_score", 30), scoring.get("max_per_run", 150))
        if todo:
            log(f"  scoring {len(todo)} with {llm.model()} ...")
        results = assess_many(todo, scoring.get("effort", "medium"), scoring.get("concurrency", 4), log_error)
        for uid, assessment in results.items():
            store.save_assessment(uid, assessment.model_dump())
        scored_uids = list(results)
        stats["scored"] = len(results)
    elif use_llm:
        log("  no Claude credentials found: skipping scoring (set ANTHROPIC_API_KEY or run `ant auth login`)")

    rows = {row["uid"]: row for row in store.query(since=started, limit=2000)}
    rows.update({row["uid"]: row for row in store.get(scored_uids)})
    opts = cfg.get("digest", {})
    markdown, html_body = digest.build(list(rows.values()), stats, opts.get("min_fit_score", 50), opts.get("max_items", 40))
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    path = config.data_path("digests", f"scout-{stamp}.md")
    path.write_text(markdown, encoding="utf-8")
    path.with_suffix(".html").write_text(html_body, encoding="utf-8")
    stats["digest"] = str(path)
    log(f"  digest: {path}")

    if send:
        subject = f"Scout: {stats['new']} new roles ({datetime.now():%d %b})"
        best = sorted(rows.values(), key=lambda r: -(r["fit_score"] if r["fit_score"] is not None else -1))
        try:
            sent = [name for name, ok in (
                ("email", notify.email(subject, markdown, html_body)),
                ("telegram", notify.telegram(best, subject)),
            ) if ok]
            log(f"  sent via {', '.join(sent)}" if sent else "  no notifier configured (see .env.example)")
        except Exception as exc:
            log_error(f"notify: {exc}")

    store.log_run(started, stats)
    return stats
