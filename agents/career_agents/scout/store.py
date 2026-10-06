"""SQLite store: remembers every job seen, Claude's assessment, and your application status."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

STATUSES = ("new", "shortlisted", "applied", "interviewing", "offer", "rejected", "archived")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid TEXT PRIMARY KEY,
    match_key TEXT,
    kind TEXT, source TEXT, company TEXT, title TEXT, location TEXT, region TEXT,
    url TEXT, posted_at TEXT, salary TEXT, description TEXT,
    first_seen TEXT, last_seen TEXT,
    rule_score INTEGER, fit_score INTEGER, tier TEXT, assessment TEXT,
    status TEXT NOT NULL DEFAULT 'new', notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS jobs_match_key ON jobs(match_key);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, stats TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def upsert(self, jobs: list[Job]) -> list[Job]:
        """Insert unseen jobs and refresh last_seen on known ones. Returns only the new jobs."""
        new, now = [], _now()
        with self.db:
            for job in jobs:
                known = self.db.execute(
                    "SELECT uid FROM jobs WHERE uid = ? OR (match_key = ? AND kind = 'job')",
                    (job.uid, job.match_key),
                ).fetchone()
                if known:
                    self.db.execute("UPDATE jobs SET last_seen = ? WHERE uid = ?", (now, known["uid"]))
                    continue
                self.db.execute(
                    """INSERT INTO jobs (uid, match_key, kind, source, company, title, location, region, url,
                       posted_at, salary, description, first_seen, last_seen, rule_score)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (job.uid, job.match_key, job.kind, job.source, job.company, job.title, job.location,
                     job.region, job.url, job.posted_at, job.salary, job.description, now, now, job.rule_score),
                )
                new.append(job)
        return new

    def unscored(self, min_rule_score: int, limit: int) -> list[Job]:
        rows = self.db.execute(
            """SELECT * FROM jobs WHERE fit_score IS NULL AND rule_score >= ? AND status = 'new'
               ORDER BY rule_score DESC, first_seen DESC LIMIT ?""",
            (min_rule_score, limit),
        ).fetchall()
        return [_to_job(r) for r in rows]

    def save_assessment(self, uid: str, assessment: dict) -> None:
        with self.db:
            self.db.execute(
                "UPDATE jobs SET fit_score = ?, tier = ?, assessment = ? WHERE uid = ?",
                (assessment["fit_score"], assessment["tier"], json.dumps(assessment), uid),
            )

    def set_status(self, uid: str, status: str, note: str = "") -> bool:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        with self.db:
            cur = self.db.execute(
                """UPDATE jobs SET status = ?,
                   notes = CASE WHEN ? = '' THEN notes ELSE trim(notes || char(10) || ?, char(10)) END
                   WHERE uid = ?""",
                (status, note, note, uid),
            )
        return cur.rowcount > 0

    def query(self, *, since: str | None = None, status: str | None = None, min_score: int | None = None,
              tier: str | None = None, limit: int = 50) -> list[sqlite3.Row]:
        clauses, args = [], []
        if since:
            clauses.append("first_seen >= ?")
            args.append(since)
        if status:
            clauses.append("status = ?")
            args.append(status)
        if min_score is not None:
            clauses.append("fit_score >= ?")
            args.append(min_score)
        if tier:
            clauses.append("tier = ?")
            args.append(tier)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.db.execute(
            f"SELECT * FROM jobs {where} ORDER BY COALESCE(fit_score, -1) DESC, rule_score DESC LIMIT ?",
            (*args, limit),
        ).fetchall()

    def get(self, uids: list[str]) -> list[sqlite3.Row]:
        if not uids:
            return []
        marks = ",".join("?" * len(uids))
        return self.db.execute(f"SELECT * FROM jobs WHERE uid IN ({marks})", uids).fetchall()

    def log_run(self, started: str, stats: dict) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO runs (started, finished, stats) VALUES (?, ?, ?)", (started, _now(), json.dumps(stats))
            )


def _to_job(row: sqlite3.Row) -> Job:
    return Job(
        source=row["source"], native_id=row["uid"], company=row["company"], title=row["title"],
        location=row["location"] or "", url=row["url"] or "", description=row["description"] or "",
        posted_at=row["posted_at"], salary=row["salary"], kind=row["kind"], region=row["region"],
        rule_score=row["rule_score"] or 0, extra={"uid": row["uid"]},
    )
