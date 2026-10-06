"""Markdown and HTML digests of a run's best new opportunities."""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import date

TIER_HEADINGS = [
    ("A", "Apply this week"),
    ("B", "Worth considering"),
    ("C", "Long shots"),
]


def _assessment(row: sqlite3.Row) -> dict:
    return json.loads(row["assessment"]) if row["assessment"] else {}


def build(rows: list[sqlite3.Row], stats: dict, min_fit: int, max_items: int) -> tuple[str, str]:
    """Return (markdown, html) for the given job rows."""
    scored = [r for r in rows if r["fit_score"] is not None and r["fit_score"] >= min_fit and r["tier"] != "skip"]
    unscored = [r for r in rows if r["fit_score"] is None]
    scored.sort(key=lambda r: -r["fit_score"])
    unscored.sort(key=lambda r: -(r["rule_score"] or 0))

    md = [f"# Scout digest — {date.today():%d %b %Y}", ""]
    md.append(
        f"{stats.get('new', 0)} new matches from {stats.get('fetched', 0)} postings scanned; "
        f"{len(scored)} scored ≥ {min_fit}."
    )
    shown = 0
    for tier, heading in TIER_HEADINGS:
        items = [r for r in scored if r["tier"] == tier][: max(0, max_items - shown)]
        if not items:
            continue
        md += ["", f"## {heading} ({tier})", ""]
        for row in items:
            md += _item_md(row)
        shown += len(items)
    if unscored and shown < max_items:
        md += ["", "## Not yet scored by Claude (rule-based order)", ""]
        for row in unscored[: max_items - shown]:
            md.append(f"- **{row['title']}** — {row['company']} · {row['location']} · pre-score {row['rule_score']} · "
                      f"[link]({row['url']}) · `{row['uid']}`")
    if stats.get("errors"):
        md += ["", "<details><summary>Source errors</summary>", ""]
        md += [f"- {e}" for e in stats["errors"]]
        md += ["", "</details>"]
    md += ["", "Update a job: `scout mark <id> applied --note \"...\"`", ""]
    markdown = "\n".join(md)
    return markdown, _to_html(scored[:max_items], unscored[: max(0, max_items - len(scored))], stats, min_fit)


def _item_md(row: sqlite3.Row) -> list[str]:
    a = _assessment(row)
    tag = "📣 post" if row["kind"] == "post" else row["source"]
    lines = [
        f"### {row['fit_score']} · {row['title']} — {row['company']}",
        f"{row['location'] or 'location n/a'} · {tag} · comp {a.get('est_total_comp_usd', '?')} "
        f"({a.get('meets_comp_target', '?')} to meet target) · visa: {a.get('visa_path', '?')} · `{row['uid']}`",
        "",
    ]
    lines += [f"- ✅ {w}" for w in a.get("why", [])]
    lines += [f"- ⚠️ {f}" for f in a.get("red_flags", [])]
    if a.get("pitch"):
        lines.append(f"- 💬 _{a['pitch']}_")
    lines += [f"- [Open posting]({row['url']})", ""]
    return lines


def _to_html(scored, unscored, stats, min_fit) -> str:
    esc = html.escape
    parts = [
        "<html><body style='font-family:-apple-system,Segoe UI,sans-serif;max-width:720px;margin:auto;color:#1a1a1a'>",
        f"<h2>Scout digest — {date.today():%d %b %Y}</h2>",
        f"<p>{stats.get('new', 0)} new matches from {stats.get('fetched', 0)} postings; "
        f"{len(scored)} scored ≥ {min_fit}.</p>",
    ]
    for row in scored:
        a = _assessment(row)
        why = "".join(f"<li>{esc(w)}</li>" for w in a.get("why", []))
        flags = "".join(f"<li style='color:#a15c00'>{esc(f)}</li>" for f in a.get("red_flags", []))
        parts.append(
            "<div style='border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin:12px 0'>"
            f"<div style='font-size:13px;color:#666'>Tier {esc(row['tier'] or '')} · fit {row['fit_score']} · "
            f"{esc(row['location'] or '')} · {esc(row['source'])}</div>"
            f"<div style='font-size:17px;font-weight:600;margin:4px 0'><a href='{esc(row['url'])}'>{esc(row['title'])}</a>"
            f" — {esc(row['company'])}</div>"
            f"<div style='font-size:13px'>Comp: {esc(a.get('est_total_comp_usd', '?'))} · Visa: {esc(a.get('visa_path', '?'))}</div>"
            f"<ul style='font-size:14px'>{why}{flags}</ul>"
            f"<div style='font-size:14px;font-style:italic'>{esc(a.get('pitch', ''))}</div>"
            f"<div style='font-size:12px;color:#888'>id {esc(row['uid'])}</div></div>"
        )
    if unscored:
        items = "".join(
            f"<li><a href='{esc(r['url'])}'>{esc(r['title'])}</a> — {esc(r['company'])} · {esc(r['location'] or '')}</li>"
            for r in unscored
        )
        parts.append(f"<h3>Not yet scored</h3><ul>{items}</ul>")
    parts.append("</body></html>")
    return "".join(parts)
