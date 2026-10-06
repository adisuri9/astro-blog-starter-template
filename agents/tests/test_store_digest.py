from career_agents import config
from career_agents.scout import digest
from career_agents.scout.models import Job
from career_agents.scout.store import Store


def _job(source, native, company="Airbnb", title="Head of Product", location="San Francisco, CA"):
    return Job(source, native, company, title, location, url=f"https://x/{native}", rule_score=70)


def test_upsert_detects_new_and_cross_source_duplicates():
    store = Store(config.data_path("scout.db"))
    assert len(store.upsert([_job("greenhouse", "1")])) == 1
    assert store.upsert([_job("greenhouse", "1")]) == []
    assert store.upsert([_job("linkedin", "li-9")]) == []  # same company/title/city via another source
    assert len(store.upsert([_job("linkedin", "li-10", title="VP Product")])) == 1


def test_scoring_round_trip_status_and_digest():
    store = Store(config.data_path("scout.db"))
    (job,) = store.upsert([_job("greenhouse", "1")])
    (pending,) = store.unscored(min_rule_score=30, limit=10)
    assert pending.uid == job.uid
    store.save_assessment(job.uid, {
        "fit_score": 88, "tier": "A", "consumer_b2c": True, "business_model": "travel marketplace",
        "level_vs_candidate": "match", "owns_pnl": True, "est_total_comp_usd": "$450-600K",
        "meets_comp_target": "likely", "visa_path": "H-1B (Level IV) or O-1A", "why": ["Marketplace P&L"],
        "red_flags": ["Relocation timing"], "pitch": "I tripled a consumer P&L.",
    })
    assert store.unscored(30, 10) == []
    assert store.set_status(job.uid, "applied", "Referred by X")
    (row,) = store.query(status="applied")
    assert row["notes"] == "Referred by X"
    markdown, html = digest.build([row], {"new": 1, "fetched": 10}, min_fit=50, max_items=10)
    assert "## Apply this week (A)" in markdown and "$450-600K" in markdown
    assert "Head of Product" in html
