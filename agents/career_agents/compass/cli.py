"""`compass` command line."""

from __future__ import annotations

import argparse
import sys
from datetime import date

import anthropic

from .. import config, llm
from . import calculators

WEEKLY_PROMPT = """Run my weekly review.
1. Read my notes and Scout's pipeline (job_pipeline, min_score 65).
2. Check for any immigration or visa changes in the last few weeks that affect my plan (US H-1B/L-1/O-1 and the visa bulletin for India, Singapore EP/LTVP, Canada Express Entry, UAE) and cite sources.
3. Give me: (a) where I stand against my 1/3/5/7-year goals, (b) the 5 highest-leverage actions for this week (specific roles to apply to and people to contact, with the pitch angle), (c) the relocation decision status and what would change it, (d) the single biggest risk to address.
Save any new commitments as notes."""


def _agent(effort: str):
    if not llm.has_credentials():
        sys.exit("Compass needs Claude: set ANTHROPIC_API_KEY in agents/.env (or run `ant auth login`).")
    from .agent import Compass

    return Compass(effort=effort, on_tool=lambda name: print(f"  · {name}", file=sys.stderr))


def cmd_chat(args) -> None:
    agent = _agent(args.effort)
    print("Compass — ask about offers, cities, visas, parents, your plan. Ctrl-D to exit.\n")
    while True:
        try:
            question = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not question:
            continue
        try:
            print(f"\ncompass › {agent.ask(question)}\n")
        except llm.Refused as exc:
            print(f"\n(declined: {exc})\n")
        except anthropic.APIError as exc:
            print(f"\n(API error: {exc})\n")


def cmd_ask(args) -> None:
    print(_agent(args.effort).ask(" ".join(args.question)))


def cmd_weekly(args) -> None:
    answer = _agent(args.effort).ask(WEEKLY_PROMPT)
    path = config.data_path("reviews", f"weekly-{date.today():%Y-%m-%d}.md")
    path.write_text(answer, encoding="utf-8")
    print(answer)
    print(f"\n(saved to {path})", file=sys.stderr)


def cmd_compare(args) -> None:
    rows = calculators.compare(calculators.parse_weights(args.weights or ""))
    print(calculators.render_comparison(rows))
    print("\nScores are 0-10 judgments in knowledge/locations.yaml; money columns are planning estimates in USD.")


def cmd_offer(args) -> None:
    result = calculators.evaluate_offer(args.city, args.base, args.currency, args.bonus_pct, args.equity,
                                        args.sign_on, nl_ruling=not args.no_ruling)
    print(calculators.render_offer(result))


def main(argv: list[str] | None = None) -> None:
    config.load_env_file()
    parser = argparse.ArgumentParser(prog="compass", description="Career, relocation and family strategist.")
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"],
                        help="Claude effort level for chat/ask/weekly (default: high)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("chat", help="interactive conversation").set_defaults(func=cmd_chat)

    p = sub.add_parser("ask", help="one question, one answer")
    p.add_argument("question", nargs="+")
    p.set_defaults(func=cmd_ask)

    sub.add_parser("weekly", help="weekly review of goals, pipeline and immigration news").set_defaults(func=cmd_weekly)

    p = sub.add_parser("compare", help="rank cities on the weighted scorecard (no API key needed)")
    p.add_argument("--weights", help='e.g. "parents=0.3,comp=0.15"')
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("offer", help="take-home and savings for an offer (no API key needed)")
    p.add_argument("--city", required=True)
    p.add_argument("--base", type=float, required=True, help="annual base salary")
    p.add_argument("--currency", help="offer currency (default: the city's)")
    p.add_argument("--bonus-pct", type=float, default=0.0)
    p.add_argument("--equity", type=float, default=0.0, help="equity vesting per year")
    p.add_argument("--sign-on", type=float, default=0.0)
    p.add_argument("--no-ruling", action="store_true", help="Netherlands: without the expat tax ruling")
    p.set_defaults(func=cmd_offer)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
