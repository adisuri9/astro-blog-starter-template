# Career agents: Scout and Compass

Two Claude-powered agents for a senior product/business leader planning a move abroad.

- **Scout** finds Director / Head / VP / GM roles at consumer-tech companies across company career sites,
  job boards and LinkedIn "we're hiring" posts. Claude scores each role against your profile and writes a
  daily digest.
- **Compass** is a candid strategist for the big decisions: which city, which offer, which visa route,
  how to look after your parents and young child, and how to sequence the next seven years. It has
  calculators for take-home pay and savings, a dated knowledge base on immigration routes, live web search
  for rule changes, Scout's pipeline, and a memory of your decisions.

> **Privacy.** This repository is public. Your profile (`config/profile.yaml`), API keys (`.env`) and
> everything Scout and Compass store (`data/`) are gitignored. Keep it that way, or make the repo private.

## Setup

```bash
cd agents
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[boards,dev]"          # drop "boards" to skip LinkedIn/Indeed/Glassdoor scraping
cp .env.example .env                     # add ANTHROPIC_API_KEY (and optional email/Telegram settings)
cp config/profile.example.yaml config/profile.yaml   # then fill it in (skip if you already have one)
scout doctor                             # checks every company job-board slug in companies.yaml
```

Python 3.10+. Claude features use `claude-opus-5-5` by default; set `CAREER_AGENTS_MODEL` to change it.
Requests opt into server-side refusal fallback (`fallbacks: "default"`), so a rare false-positive safety
decline is retried on a fallback model instead of failing.

## Scout

```bash
scout run                    # crawl -> screen -> score with Claude -> digest in data/digests/
scout run --notify           # ...and email / Telegram it
scout run --sources ats,amazon --no-llm    # quick run, rule-based ranking only, no API cost
scout list --tier A          # best roles so far
scout show <id>              # Claude's full assessment and pitch
scout mark <id> applied --note "Referred by <name>"   # statuses: new shortlisted applied interviewing offer rejected archived
scout add --company Uber --title "Director, Product" --url <link> --score    # a role you found elsewhere
```

| Source | What it covers | How |
|---|---|---|
| `ats` | ~40 consumer companies (Airbnb, DoorDash, Instacart, Pinterest, Reddit, Spotify, OpenAI, Walmart, PayPal, ...) | Public Greenhouse, Lever, Ashby, SmartRecruiters and Workday APIs, the same ones their career pages call |
| `amazon` | amazon.jobs in every target city | amazon.jobs search JSON |
| `boards` | LinkedIn Jobs, Indeed, Glassdoor, Google Jobs, Naukri | [python-jobspy](https://github.com/speedyapply/JobSpy) |
| `posts` | LinkedIn posts by founders, execs and recruiters saying they're hiring | Claude's web search, restricted to linkedin.com; only URLs that appear in search results are kept |

Screening (all in `config/search.yaml`):
1. **Title**: any senior title in any business function (Head of X, Director, VP/AVP, GM, Chief/CxO,
   President, Co-founder/Founding, Amazon's Principal PM / Sr. Manager Product). Dropped: interns,
   assistants, site operations (store, warehouse), and functions you wouldn't move into (engineering,
   legal, finance, HR, design...) unless the title also mentions product, business, strategy, sales, growth
   or GM. Product, business, GM, strategy and category roles get a ranking boost.
   Titles that don't sound senior but often are (Product Lead, Senior/Staff/Principal PM, Strategy & Ops,
   BizOps, BD, Partnerships, Growth/Category Lead, Senior Manager...) count when the posting asks for
   6-20 years of experience (`experience_years` in `search.yaml`).
2. **City**: target regions with priorities (Bay Area, Seattle, Singapore first; NYC, Vancouver, Dubai next;
   Toronto, London, Amsterdam after that). India roles are kept only at US multinationals, as a launchpad
   for an L-1A transfer.
3. **Freshness, de-duplication** across sources, and an exclusion list (put your current employer in
   `exclude_companies` in your profile).
4. **Claude assessment** of each new role: fit score, tier (A/B/C/skip), consumer vs B2B, level, P&L
   ownership, estimated comp vs your target, realistic visa route, red flags, and an opening line for your
   outreach.

### Running it daily

Run Scout from your own machine. LinkedIn and Glassdoor block cloud/datacenter IP addresses, and a public
repository's CI logs would expose your search. Example cron entry (07:10 every day):

```cron
10 7 * * * cd ~/astro-blog-starter-template/agents && .venv/bin/scout run --notify >> data/scout.log 2>&1
```

On macOS you can use `launchd`, or just run `scout run` with your morning coffee.

### LinkedIn

LinkedIn's terms restrict automated access. The `boards` source reads public job-search pages at low
volume, and the `posts` source uses a search engine, not LinkedIn itself. To stay fully clear of scraping
LinkedIn, remove `linkedin` from the `sites` lists in `search.yaml` and add LinkedIn job alerts for the same
titles. LinkedIn emails those to you; add the good ones to Scout's pipeline with
`scout add --company ... --title ... --url ... --score`. Never automate actions on your logged-in LinkedIn
account.

### Cost

Each role Claude scores costs roughly $0.03–0.06 at the default `medium` effort. The `posts` search costs
about $0.10–0.30 per region (web search is $10 per 1,000 searches, plus tokens). A typical daily run is a few
dollars. To spend less, lower `scoring.effort`, cap `scoring.max_per_run`, or raise `scoring.min_rule_score`.

## Compass

```bash
compass chat                                   # conversation with tools, memory and web search
compass ask "Singapore at S$480K or Seattle at $430K? Parents matter a lot."
compass weekly                                 # weekly review -> data/reviews/
compass compare                                # city scorecard, no API key needed
compass compare --weights "parents=0.3,comp=0.15"
compass offer --city seattle --base 260000 --bonus-pct 20 --equity 180000
compass offer --city singapore --base 450000 --currency SGD --bonus-pct 20
```

Compass's tools:

| Tool | Does |
|---|---|
| `evaluate_offer` | Take-home pay, effective tax, family living cost and yearly savings for an offer, compared with your current package and your comp target |
| `compare_locations` | Weighted city scorecard (comp, career, startups, parents, residency, schools, healthcare, nature, safety, distance from India) with money estimates |
| `location_details` | Visa routes, residency path, parent options, schools, healthcare and employers per city |
| `job_pipeline` | Scout's best opportunities and your application status |
| `save_note` / `read_notes` | Remembers decisions and commitments across sessions |
| `web_search`, `web_fetch` | Checks current immigration rules, visa bulletins and news |

The tax maths in `career_agents/compass/calculators.py` uses simplified 2026 rules: wages only, RSUs taxed
as salary, standard deductions. It covers US federal plus CA, WA and NY/NYC; Ontario and BC; the
Netherlands with the 27% expat ruling; Singapore, UK, UAE, India (new regime) and Zurich (approximate).
Treat the results as planning estimates.

## Knowledge base

- `knowledge/relocation.md`: visa, residency, parent and quality-of-life notes per country, dated
  **October 2026**, with sources. Compass reads it every session and checks time-sensitive facts with web
  search.
- `knowledge/locations.yaml`: per-city scores, comp bands, family-cost estimates, FX rates and the default
  weights. Edit them to match your own judgment.

## Development

```bash
pytest          # offline tests: sources run against canned API payloads, no network or API key needed
```
