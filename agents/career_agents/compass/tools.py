"""Tools Compass can call. Deterministic maths lives in calculators.py; Claude only interprets."""

from __future__ import annotations

import json
from datetime import datetime

from anthropic import beta_tool

from .. import config
from ..scout.store import Store
from . import calculators

NOTES_FILE = "compass_notes.jsonl"


@beta_tool
def compare_locations(weights: str = "") -> str:
    """Rank candidate cities on a weighted scorecard (comp, career, startup ecosystem, parents, residency, schools, healthcare, nature, safety, proximity to India), with estimated take-home pay, family living cost and yearly savings at each city's typical comp for Director/Head-level roles.

    Args:
        weights: Optional overrides such as "parents=0.3,comp=0.15". Unlisted criteria keep their defaults; weights are re-normalised to sum to 1.
    """
    rows = calculators.compare(calculators.parse_weights(weights))
    return calculators.render_comparison(rows)


@beta_tool
def evaluate_offer(city: str, base_salary: float, currency: str = "", bonus_pct: float = 0.0,
                   annual_equity: float = 0.0, sign_on: float = 0.0, nl_expat_ruling: bool = True) -> str:
    """Estimate take-home pay, effective tax, family living cost and yearly savings for a job offer, compared with the user's current package and their total-comp target.

    Args:
        city: City key or name, e.g. "seattle", "bay_area", "new_york", "singapore", "dubai", "amsterdam", "toronto", "vancouver", "london", "zurich", "bengaluru".
        base_salary: Annual base salary in the offer's currency.
        currency: ISO currency code of the offer (USD, EUR, SGD, CAD, GBP, AED, INR, CHF). Defaults to the city's local currency.
        bonus_pct: Target annual bonus as a percent of base, e.g. 15 for 15%.
        annual_equity: Equity value vesting per year, in the offer currency.
        sign_on: One-time sign-on bonus in the offer currency.
        nl_expat_ruling: Netherlands only: apply the expat tax ruling (27% tax-free allowance from 2027).
    """
    result = calculators.evaluate_offer(city, base_salary, currency or None, bonus_pct, annual_equity, sign_on,
                                        nl_ruling=nl_expat_ruling)
    return calculators.render_offer(result)


@beta_tool
def location_details(city: str) -> str:
    """Knowledge-base facts for one city: work visa routes, permanent-residency path, options for dependent parents, schools, healthcare, nature, typical comp, family cost and major consumer-tech employers. Dated; verify time-sensitive rules with web search.

    Args:
        city: City key or name, e.g. "singapore" or "Seattle".
    """
    key, loc = calculators.find_location(city)
    return json.dumps({"key": key, "as_of": config.locations().get("as_of"), **loc}, indent=1, default=str)


@beta_tool
def job_pipeline(min_score: int = 0, status: str = "", limit: int = 15) -> str:
    """Opportunities found by Scout (the job-search agent), best first, with Claude's fit assessment and the user's application status.

    Args:
        min_score: Only include jobs with at least this fit score (0-100).
        status: Filter by status: new, shortlisted, applied, interviewing, offer, rejected, archived. Empty for all.
        limit: Maximum number of jobs to return.
    """
    path = config.DATA_DIR / "scout.db"
    if not path.exists():
        return "Scout hasn't run yet - no pipeline data. Suggest running `scout run`."
    rows = Store(path).query(status=status or None, min_score=min_score or None, limit=limit)
    out = []
    for row in rows:
        assessment = json.loads(row["assessment"]) if row["assessment"] else {}
        out.append({
            "id": row["uid"], "title": row["title"], "company": row["company"], "location": row["location"],
            "fit": row["fit_score"], "tier": row["tier"], "status": row["status"], "url": row["url"],
            "comp": assessment.get("est_total_comp_usd"), "visa": assessment.get("visa_path"),
            "why": assessment.get("why"), "red_flags": assessment.get("red_flags"), "notes": row["notes"],
        })
    return json.dumps(out, indent=1) if out else "No jobs match those filters."


@beta_tool
def save_note(topic: str, note: str) -> str:
    """Remember a decision, commitment, goal update or fact across sessions.

    Args:
        topic: Short category, e.g. "decision", "goal", "relocation", "parents", "interview", "finance".
        note: The note itself, specific and dated if relevant.
    """
    path = config.data_path(NOTES_FILE)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now().isoformat(timespec="minutes"), "topic": topic, "note": note}) + "\n")
    return "Saved."


@beta_tool
def read_notes(topic: str = "") -> str:
    """Read notes saved in earlier sessions, oldest first.

    Args:
        topic: Only return notes with this topic. Empty for all.
    """
    path = config.DATA_DIR / NOTES_FILE
    if not path.exists():
        return "No notes yet."
    notes = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    notes = [n for n in notes if not topic or n["topic"] == topic]
    return "\n".join(f"[{n['at']}] ({n['topic']}) {n['note']}" for n in notes) or "No notes on that topic."


CLIENT_TOOLS = [compare_locations, evaluate_offer, location_details, job_pipeline, save_note, read_notes]
SERVER_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 6},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 4},
]
