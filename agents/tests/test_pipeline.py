import sys
import types

import pandas as pd

from career_agents import config
from career_agents.scout import pipeline
from career_agents.scout.models import Job
from career_agents.scout.sources import boards


def test_boards_maps_jobspy_rows(monkeypatch):
    calls = []

    def scrape_jobs(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame([{
            "id": "li-42", "site": "linkedin", "job_url": "https://www.linkedin.com/jobs/view/42", "job_url_direct": None,
            "title": "Director of Product", "company": "Uber", "location": "Seattle, WA", "date_posted": "2026-10-01",
            "description": "Rides and Eats", "min_amount": 250000.0, "max_amount": float("nan"), "currency": "USD",
            "interval": "yearly",
        }])

    monkeypatch.setitem(sys.modules, "jobspy", types.SimpleNamespace(scrape_jobs=scrape_jobs))
    monkeypatch.setattr(boards.time, "sleep", lambda s: None)
    cfg = config.search_config()
    cfg["regions"] = [r for r in cfg["regions"] if r["key"] == "seattle"]
    cfg["sources"]["boards"]["search_terms"] = ["Director of Product"]
    (job,) = boards.fetch(cfg, print)
    assert (job.source, job.url, job.salary, job.posted_at) == (
        "linkedin", "https://www.linkedin.com/jobs/view/42", "250,000+ USD yearly", "2026-10-01")
    assert calls[0]["fetch_description"] is True and calls[0]["country_indeed"] == "usa"


def test_run_without_llm_writes_digest(monkeypatch):
    jobs = [
        Job("greenhouse", "a:1", "Airbnb", "Head of Product, Hosts", "San Francisco, CA", url="https://a/1"),
        Job("greenhouse", "a:2", "Airbnb", "Software Engineer", "San Francisco, CA", url="https://a/2"),
        Job("linkedin", "li-1", "Airbnb", "Head of Product, Hosts", "San Francisco, California", url="https://li/1"),
    ]
    monkeypatch.setattr(pipeline, "collect", lambda *a, **k: (jobs, {"greenhouse": 2, "linkedin": 1}))
    stats = pipeline.run({"ats"}, use_llm=False, send=False, log=lambda m: None)
    assert (stats["fetched"], stats["screened"], stats["new"]) == (3, 1, 1)
    text = open(stats["digest"]).read()
    assert "Head of Product, Hosts" in text and "Software Engineer" not in text
    assert pipeline.run({"ats"}, use_llm=False, send=False, log=lambda m: None)["new"] == 0
