"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a tiny synthetic repo directory for tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "example.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    return repo
