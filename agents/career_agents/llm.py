"""Claude settings shared by both agents."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"

# Server-side refusal fallback: if a safety classifier declines a request, the API re-runs it on
# Anthropic's recommended fallback model instead of returning the refusal. Used with client.beta.messages.
FALLBACK_KWARGS = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


class Refused(RuntimeError):
    """Claude and its fallback model declined the request."""


def model() -> str:
    return os.environ.get("CAREER_AGENTS_MODEL") or DEFAULT_MODEL


def has_credentials() -> bool:
    """Best-effort check so the agents can skip Claude features instead of failing mid-run."""
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_PROFILE")
        or (Path.home() / ".config" / "anthropic").is_dir()
    )


@lru_cache
def client() -> anthropic.Anthropic:
    return anthropic.Anthropic(max_retries=4)


def text_of(message) -> str:
    return "\n".join(block.text for block in message.content if block.type == "text").strip()


def check_refusal(message) -> None:
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        raise Refused(getattr(details, "explanation", None) or "request declined")
