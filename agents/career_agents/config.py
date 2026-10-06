"""Paths, YAML loading and the user profile shared by both agents."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("CAREER_AGENTS_HOME") or Path(__file__).resolve().parent.parent)
CONFIG_DIR = ROOT / "config"
KNOWLEDGE_DIR = ROOT / "knowledge"
DATA_DIR = Path(os.environ.get("CAREER_AGENTS_DATA") or ROOT / "data")


def load_env_file(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from agents/.env; variables already set in the environment win."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache
def profile() -> dict:
    path = CONFIG_DIR / "profile.yaml"
    if not path.exists():
        raise SystemExit(
            f"No profile at {path}.\n"
            "Copy config/profile.example.yaml to config/profile.yaml and fill it in."
        )
    return load_yaml(path)


def profile_yaml() -> str:
    return yaml.safe_dump(profile(), sort_keys=False, allow_unicode=True, width=110)


@lru_cache
def search_config() -> dict:
    return load_yaml(CONFIG_DIR / "search.yaml")


@lru_cache
def companies() -> tuple[dict, ...]:
    return tuple(load_yaml(CONFIG_DIR / "companies.yaml").get("companies", []))


@lru_cache
def locations() -> dict:
    return load_yaml(KNOWLEDGE_DIR / "locations.yaml")


def knowledge_text(name: str) -> str:
    return (KNOWLEDGE_DIR / name).read_text(encoding="utf-8")


def data_path(*parts: str) -> Path:
    """A path under the data directory, creating parent folders as needed."""
    path = DATA_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
