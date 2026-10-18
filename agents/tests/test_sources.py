from career_agents.scout.sources import amazon, ats, posts

from .conftest import FakeSession

ACCEPT_ALL = lambda title, location: "product" in title.lower()  # noqa: E731


def test_greenhouse_fetches_details_only_for_wanted_titles():
    session = FakeSession({
        ("GET", "https://boards-api.greenhouse.io/v1/boards/acme/jobs"): {"jobs": [
            {"id": 1, "title": "Director of Product", "absolute_url": "https://acme/1", "location": {"name": "Seattle"},
             "first_published": "2026-09-30T00:00:00Z"},
            {"id": 2, "title": "Recruiter", "absolute_url": "https://acme/2", "location": {"name": "Seattle"}},
        ]},
        ("GET", "https://boards-api.greenhouse.io/v1/boards/acme/jobs/1"): {"content": "&lt;p&gt;Lead consumer&lt;/p&gt;"},
    })
    jobs = ats.greenhouse(session, {"name": "Acme", "slug": "acme"}, ACCEPT_ALL)
    assert [(j.title, j.description, j.posted_at) for j in jobs] == [("Director of Product", "Lead consumer", "2026-09-30")]
    assert len(session.calls) == 2


def test_lever_ashby_smartrecruiters_and_workday_parse():
    session = FakeSession({
        ("GET", "https://api.lever.co/v0/postings/acme"): [
            {"id": "L1", "text": "Head of Product", "hostedUrl": "https://lever/L1", "createdAt": 1790000000000,
             "categories": {"location": "Singapore"}, "descriptionPlain": "About",
             "lists": [{"text": "You will", "content": "<li>Own P&amp;L</li>"}],
             "salaryRange": {"min": 300000, "max": 400000, "currency": "SGD", "interval": "per-year-salary"}},
        ],
        ("GET", "https://api.ashbyhq.com/posting-api/job-board/acme"): {"jobs": [
            {"id": "A1", "title": "VP Product", "location": "New York", "isRemote": False, "jobUrl": "https://ashby/A1",
             "descriptionPlain": "Consumer app", "publishedAt": "2026-10-01T00:00:00Z",
             "compensation": {"compensationTierSummary": "$300K – $350K"}},
            {"id": "A2", "title": "Hidden product role", "isListed": False},
        ]},
        ("GET", "https://api.smartrecruiters.com/v1/companies/Acme/postings/S1"): {
            "jobAd": {"sections": {"jobDescription": {"text": "<p>Own growth</p>"}}}},
        ("GET", "https://api.smartrecruiters.com/v1/companies/Acme/postings"): {"content": [
            {"id": "S1", "name": "Director Product", "location": {"city": "Dubai", "country": "ae"},
             "releasedDate": "2026-09-29T08:00:00.000Z"}]},
        ("POST", "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Ext/jobs"): {"jobPostings": [
            {"title": "Director, Product", "externalPath": "/job/Seattle/Director_JR1", "locationsText": "2 Locations"}]},
        ("GET", "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Ext/job/Seattle/Director_JR1"): {"jobPostingInfo": {
            "title": "Director, Product", "jobDescription": "<p>Lead</p>", "location": "Seattle, WA",
            "additionalLocations": ["Bellevue, WA"], "externalUrl": "https://acme.wd5/job/1", "startDate": "2026-09-28"}},
    })
    company = {"name": "Acme", "slug": "acme"}
    (lev,) = ats.lever(session, company, ACCEPT_ALL)
    assert lev.salary == "300000-400000 SGD per-year-salary" and "Own P&L" in lev.description
    (ash,) = ats.ashby(session, company, ACCEPT_ALL)
    assert ash.salary == "$300K – $350K" and ash.posted_at == "2026-10-01"
    (sr,) = ats.smartrecruiters(session, {"name": "Acme", "slug": "Acme"}, ACCEPT_ALL, ["product"])
    assert sr.location == "Dubai, ae" and sr.description == "Own growth"
    (wd,) = ats.workday(session, {"name": "Acme", "workday": {"host": "acme.wd5.myworkdayjobs.com", "tenant": "acme", "site": "Ext"}},
                        ACCEPT_ALL, ["product"])
    assert wd.location == "Seattle, WA / Bellevue, WA" and wd.url == "https://acme.wd5/job/1"


def test_amazon_dedupes_across_queries():
    payload = {"jobs": [{"id_icims": "3012345", "title": "Director, Product Management", "company_name": "Amazon.com Services LLC",
                         "normalized_location": "Seattle, WA, USA", "job_path": "/en/jobs/3012345/director",
                         "description": "Lead Fresh", "basic_qualifications": "10+ years", "preferred_qualifications": "MBA",
                         "posted_date": "September 30, 2026"}]}
    session = FakeSession({("GET", "https://www.amazon.jobs/en/search.json"): payload})
    jobs = amazon.fetch(session, ["director", "head of"], ["USA"], ACCEPT_ALL)
    assert len(jobs) == 1
    assert session.calls[0][2]["params"]["country"] == "USA"
    assert jobs[0].url == "https://www.amazon.jobs/en/jobs/3012345/director" and jobs[0].posted_at == "2026-09-30"


def test_posts_keep_only_urls_seen_in_search_results():
    seen = {posts._canonical("https://www.linkedin.com/posts/jane_hiring-activity-1/")}
    reported = [
        {"url": "https://linkedin.com/posts/jane_hiring-activity-1", "role": "Head of Product"},
        {"url": "https://www.linkedin.com/posts/jane_hiring-activity-1/?utm=x", "role": "duplicate"},
        {"url": "https://www.linkedin.com/posts/made-up-2", "role": "Invented"},
    ]
    kept = posts.verified_posts(reported, seen)
    assert [p["role"] for p in kept] == ["Head of Product"]
