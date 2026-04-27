"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no test inadvertently picks up a real ANAKIN_API_KEY from the host."""
    monkeypatch.delenv("ANAKIN_API_KEY", raising=False)
