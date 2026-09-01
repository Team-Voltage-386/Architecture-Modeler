"""Shared pytest fixtures for the whole test suite."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Redirect Path.home() to a throwaway directory for every test.

    MainWindow persists the last-opened-model pointer via RecentModelStore, which
    defaults to the real user's home directory. Without this, running the suite would
    read and overwrite the developer's actual ~/.architecture_model.json.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
