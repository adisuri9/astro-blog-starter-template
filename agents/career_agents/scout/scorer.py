"""Claude assesses each screened job against the user's profile and returns structured output."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field

from .. import config, llm
from .models import Job

MAX_DESCRIPTION_CHARS = 20000


class JobAssessment(BaseModel):
    fit_score: int = Field(description="0-100 overall fit for this candidate's goals")
    tier: Literal["A", "B", "C", "skip"]
    consumer_b2c: bool
    business_model: str = Field(description="e.g. 'consumer marketplace', 'B2B SaaS', 'consumer gaming'")
    level_vs_candidate: Literal["below", "match", "stretch"]
    owns_pnl: bool = Field(description="Does the role own a P&L or an entire business line?")
    est_total_comp_usd: str = Field(description="Estimated total annual comp range in USD, or 'unknown'")
    meets_comp_target: Literal["likely", "possible", "unlikely", "unknown"]
    visa_path: str = Field(description="Realistic work-authorisation route for this candidate, or the blocker")
    why: list[str] = Field(description="Up to 3 reasons this fits")
    red_flags: list[str] = Field(description="Up to 3 concerns")
    pitch: str = Field(description="1-2 sentence opener for a message to the recruiter or hiring manager")


SYSTEM = """You are a sharp executive recruiter and career strategist screening openings for one candidate. Judge each role against the candidate's profile and goals below. Be blunt: most roles are not worth their time.

fit_score (0-100):
- 85+: consumer/B2C company with large user scale; role at or one level above the candidate (Director / Head / VP / GM); real ownership (a P&L or a whole product line); a target location with a credible work-authorisation path; total comp plausibly at or above the candidate's target.
- 70-84: strong on most of the above with one real gap.
- 50-69: only worth it if the pipeline is thin.
- Below 50: wrong level, wrong business model (pure B2B/enterprise), no plausible visa path, or comp far below target.
Tier: A = apply this week (80+), B = consider (65-79), C = long shot (50-64), skip = below 50.

Comp: estimate total annual comp (base + bonus + equity) in USD from the posting's band if given, otherwise from what you know of that company's levels in that city. Say "unknown" rather than inventing precision.
Visa path: the realistic route for an Indian citizen living in India - e.g. "H-1B (wage level IV) or O-1A", "L-1A after 12 months in the company's India or Singapore office", "Singapore Employment Pass", "Dutch highly skilled migrant", "UAE employer visa", "Canada work permit then PR via the senior-managers draw". Flag postings that rule out sponsorship or require existing work authorisation.
Pitch: tie the candidate's specific track record to this role in one or two plain sentences. No flattery, no buzzwords.
A "post" is someone announcing on LinkedIn that they're hiring; assess it the same way from the little it says.

<candidate_profile>
{profile}
</candidate_profile>"""


def _render(job: Job) -> str:
    description = job.description or "(no description)"
    if len(description) > MAX_DESCRIPTION_CHARS:
        description = description[:MAX_DESCRIPTION_CHARS] + "\n[description truncated]"
    return (
        f"<{job.kind}>\nTitle: {job.title}\nCompany: {job.company}\nLocation: {job.location or 'unknown'}\n"
        f"Source: {job.source}\nPosted: {job.posted_at or 'unknown'}\nSalary as posted: {job.salary or 'not stated'}\n"
        f"URL: {job.url}\n\nDescription:\n{description}\n</{job.kind}>\n\nAssess this for the candidate."
    )


def assess(job: Job, effort: str = "medium") -> JobAssessment:
    response = llm.client().beta.messages.parse(
        model=llm.model(),
        max_tokens=16000,
        system=[
            {
                "type": "text",
                "text": SYSTEM.format(profile=config.profile_yaml()),
                "cache_control": {"type": "ephemeral"},  # identical for every job in the run
            }
        ],
        messages=[{"role": "user", "content": _render(job)}],
        output_format=JobAssessment,
        output_config={"effort": effort},
        **llm.FALLBACK_KWARGS,
    )
    llm.check_refusal(response)
    if response.parsed_output is None:
        raise RuntimeError(f"no structured output (stop_reason={response.stop_reason})")
    return response.parsed_output


def assess_many(
    jobs: list[Job], effort: str, concurrency: int, log: Callable[[str], None]
) -> dict[str, JobAssessment]:
    def one(job: Job):
        try:
            return job.uid, assess(job, effort)
        except Exception as exc:
            log(f"score: {job.company} / {job.title}: {exc}")
            return job.uid, None

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return {uid: result for uid, result in pool.map(one, jobs) if result is not None}
