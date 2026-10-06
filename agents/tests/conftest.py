import os
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Point the agents at a temp data dir and the example profile, and clear config caches."""
    from career_agents import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    (tmp_path / "config").mkdir()
    for name in ("search.yaml", "companies.yaml"):
        (tmp_path / "config" / name).write_text((AGENTS / "config" / name).read_text())
    (tmp_path / "config" / "profile.yaml").write_text((AGENTS / "config" / "profile.example.yaml").read_text())
    for fn in (config.profile, config.search_config, config.companies, config.locations):
        fn.cache_clear()
    yield
    for fn in (config.profile, config.search_config, config.companies, config.locations):
        fn.cache_clear()


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    """Routes GET/POST by URL prefix to canned JSON; records calls."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _match(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for (m, prefix), payload in sorted(self.routes.items(), key=lambda kv: -len(kv[0][1])):
            if m == method and url.startswith(prefix):
                return FakeResponse(payload(kwargs) if callable(payload) else payload)
        return FakeResponse({}, 404)

    def get(self, url, **kwargs):
        return self._match("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._match("POST", url, **kwargs)
