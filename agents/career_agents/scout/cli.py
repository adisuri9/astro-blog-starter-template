"""`scout` command line."""

from __future__ import annotations

import argparse
import json
import sys

import requests

from .. import config, llm
from . import pipeline
from .models import Job
from .scorer import assess
from .sources import ats
from .store import STATUSES, Store


def _store() -> Store:
    return Store(config.data_path("scout.db"))


def cmd_run(args) -> None:
    cfg = config.search_config()
    sources = set(args.sources.split(",")) if args.sources else pipeline.enabled_sources(cfg)
    unknown = sources - set(pipeline.ALL_SOURCES)
    if unknown:
        sys.exit(f"unknown source(s): {', '.join(sorted(unknown))}; choose from {', '.join(pipeline.ALL_SOURCES)}")
    pipeline.run(sources, use_llm=not args.no_llm, send=args.notify)


def cmd_list(args) -> None:
    rows = _store().query(status=args.status, min_score=args.min_score, tier=args.tier, limit=args.limit)
    if not rows:
        print("Nothing matches. Run `scout run` first, or loosen the filters.")
    for row in rows:
        score = row["fit_score"] if row["fit_score"] is not None else f"~{row['rule_score']}"
        print(f"{row['uid']}  {str(score):>4}  {row['tier'] or '-':4} {row['status']:12} "
              f"{row['title'][:48]:48}  {row['company'][:22]:22}  {(row['location'] or '')[:28]}")


def cmd_show(args) -> None:
    rows = _store().get([args.uid])
    if not rows:
        sys.exit(f"no job with id {args.uid}")
    row = rows[0]
    print(f"{row['title']} — {row['company']}\n{row['location']}\n{row['url']}\nstatus: {row['status']}\n")
    if row["assessment"]:
        print(json.dumps(json.loads(row["assessment"]), indent=2, ensure_ascii=False))
    if row["notes"]:
        print(f"\nNotes:\n{row['notes']}")
    if args.description:
        print(f"\n{row['description']}")


def cmd_mark(args) -> None:
    if not _store().set_status(args.uid, args.status, args.note or ""):
        sys.exit(f"no job with id {args.uid}")
    print(f"{args.uid} -> {args.status}")


def cmd_add(args) -> None:
    """Add a role found elsewhere (a referral, a LinkedIn alert email) and optionally score it."""
    job = Job("manual", args.url, args.company, args.title, args.location or "", url=args.url,
              description=args.description or "")
    store = _store()
    if not store.upsert([job]):
        sys.exit("Already in your pipeline.")
    print(f"added {job.uid}")
    if args.score:
        if not llm.has_credentials():
            sys.exit("Scoring needs ANTHROPIC_API_KEY.")
        assessment = assess(job, config.search_config().get("scoring", {}).get("effort", "medium"))
        store.save_assessment(job.uid, assessment.model_dump())
        print(f"fit {assessment.fit_score} (tier {assessment.tier}): {assessment.pitch}")


def cmd_doctor(args) -> None:
    """Check each company's job-board slug so broken entries in companies.yaml are easy to fix."""
    broken = 0
    with requests.Session() as session:
        for company in config.companies():
            if company.get("ats") not in ats.FETCHERS:
                continue
            try:
                print(f"  ok    {company['name']:22} {company['ats']:15} {ats.probe(session, company)} open roles")
            except Exception as exc:
                broken += 1
                print(f"  FAIL  {company['name']:22} {company['ats']:15} {exc}")
    print(f"\n{broken} broken board(s). Fix the slug in config/companies.yaml or set `ats: none`." if broken else "\nAll boards OK.")


def main(argv: list[str] | None = None) -> None:
    config.load_env_file()
    parser = argparse.ArgumentParser(prog="scout", description="Find senior consumer-tech roles and rank them for you.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="crawl, screen, score with Claude and write a digest")
    p.add_argument("--sources", help=f"comma-separated subset of: {','.join(pipeline.ALL_SOURCES)}")
    p.add_argument("--no-llm", action="store_true", help="skip Claude scoring (rule-based ranking only)")
    p.add_argument("--notify", action="store_true", help="send the digest by email / Telegram")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("list", help="list stored jobs, best first")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--tier", choices=["A", "B", "C", "skip"])
    p.add_argument("--min-score", type=int)
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show one job with Claude's assessment")
    p.add_argument("uid")
    p.add_argument("--description", action="store_true", help="also print the full description")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("mark", help="update a job's status in your pipeline")
    p.add_argument("uid")
    p.add_argument("status", choices=STATUSES)
    p.add_argument("--note")
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("add", help="add a role you found elsewhere (referral, alert email)")
    p.add_argument("--company", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--location")
    p.add_argument("--description", help="paste the job description for a better assessment")
    p.add_argument("--score", action="store_true", help="have Claude assess it now")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("doctor", help="check that every company's job-board slug works")
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
