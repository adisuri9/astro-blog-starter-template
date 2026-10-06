"""LinkedIn posts where someone says they're hiring, found with Claude's web search tool.

Claude searches (restricted to linkedin.com), then reports matches through a strict tool. Only URLs
that actually appeared in the search results are kept, so a reported post can't be invented.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from ... import llm
from ..models import Job

REPORT_TOOL = {
    "name": "report_hiring_posts",
    "description": (
        "Record LinkedIn posts in which someone says they are hiring for a role matching the brief. "
        "Call once, at the end, with every qualifying post (an empty list if none qualify)."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "posts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Exact post URL from the search results"},
                        "author": {"type": "string", "description": "Name and headline of the poster"},
                        "company": {"type": "string"},
                        "role": {"type": "string", "description": "Role being hired for"},
                        "location": {"type": "string"},
                        "posted": {"type": "string", "description": "Date or age shown, or 'unknown'"},
                        "summary": {"type": "string", "description": "One or two sentences on the role and ask"},
                        "consumer_b2c": {"type": "boolean"},
                    },
                    "required": ["url", "author", "company", "role", "location", "posted", "summary", "consumer_b2c"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["posts"],
        "additionalProperties": False,
    },
}

PROMPT = """Find LinkedIn posts from roughly the last {lookback} days in which a founder, executive, hiring manager or recruiter says they are hiring for a senior product or business leadership role.

Roles that count: {roles}.
Location: {region} (any of: {aliases}), or remote roles explicitly open to that location.
Strongly prefer consumer / B2C companies: consumer apps, marketplaces, e-commerce, quick commerce, gaming, consumer fintech, consumer AI. Skip pure B2B/enterprise SaaS, staffing-agency spam, and posts by job seekers.

Search LinkedIn posts with varied phrasings, for example "hiring Head of Product", "we're looking for a Director of Product", "#hiring VP Product", "looking for a GM". Use at most {max_searches} searches.

Then call report_hiring_posts once with every qualifying post. Copy each URL exactly as it appears in the search results; never construct or guess a URL."""


def _canonical(url: str) -> str:
    parts = urlsplit(url.strip())
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}"


def _search_result_urls(content) -> set[str]:
    urls = set()
    for block in content:
        if block.type == "web_search_tool_result" and isinstance(block.content, list):
            urls.update(_canonical(result.url) for result in block.content if getattr(result, "url", None))
    return urls


def verified_posts(reported: list[dict], seen_urls: set[str]) -> list[dict]:
    """Keep reported posts whose URL was actually returned by a search, de-duplicated."""
    kept, used = [], set()
    for post in reported:
        key = _canonical(post.get("url", ""))
        if key in seen_urls and key not in used:
            used.add(key)
            kept.append(post)
    return kept


def search_region(region: dict, roles: list[str], opts: dict, log: Callable[[str], None]) -> list[Job]:
    client = llm.client()
    prompt = PROMPT.format(
        lookback=opts.get("lookback_days", 14),
        roles=", ".join(roles),
        region=region["name"],
        aliases=", ".join(region["aliases"]),
        max_searches=opts.get("max_searches_per_region", 5),
    )
    tools = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": opts.get("max_searches_per_region", 5),
            "allowed_domains": ["linkedin.com"],
        },
        REPORT_TOOL,
    ]
    messages: list[dict] = [{"role": "user", "content": prompt}]
    seen_urls: set[str] = set()
    reported: list[dict] = []

    for _ in range(8):  # pause_turn continuations + the report call
        response = client.beta.messages.create(
            model=llm.model(),
            max_tokens=16000,
            tools=tools,
            messages=messages,
            output_config={"effort": "medium"},
            **llm.FALLBACK_KWARGS,
        )
        llm.check_refusal(response)
        seen_urls |= _search_result_urls(response.content)
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "pause_turn":  # server-side search loop paused; resend to resume
            continue
        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            break
        results = []
        for call in calls:
            if call.name == REPORT_TOOL["name"]:
                reported.extend(call.input.get("posts", []))
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": "Recorded."})
            else:
                results.append(
                    {"type": "tool_result", "tool_use_id": call.id, "content": "Unknown tool.", "is_error": True}
                )
        messages.append({"role": "user", "content": results})

    kept = verified_posts(reported, seen_urls)
    if len(kept) < len(reported):
        log(f"posts: {region['key']}: dropped {len(reported) - len(kept)} post(s) whose URL wasn't in search results")
    return [
        Job(
            source="linkedin-post",
            native_id=_canonical(post["url"]),
            company=post["company"],
            title=post["role"],
            location=post["location"],
            url=post["url"],
            description=f"{post['summary']}\n\nPosted by: {post['author']} ({post['posted']})",
            kind="post",
            extra={"consumer_b2c": post["consumer_b2c"], "author": post["author"]},
        )
        for post in kept
    ]


DEFAULT_ROLES = ["Head of Product", "Director of Product", "VP Product", "Head of Business", "General Manager"]


def fetch(cfg: dict, log: Callable[[str], None], roles: list[str] | None = None) -> list[Job]:
    opts = cfg["sources"]["posts"]
    wanted = set(opts.get("regions") or [])
    roles = roles or DEFAULT_ROLES
    jobs = []
    for region in cfg["regions"]:
        if wanted and region["key"] not in wanted:
            continue
        try:
            jobs.extend(search_region(region, roles, opts, log))
        except Exception as exc:
            log(f"posts: {region['key']} failed: {exc}")
    return jobs
