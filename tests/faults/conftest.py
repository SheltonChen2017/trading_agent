"""Pytest wiring for the GR-3 fault drills: fixtures only.

All harness machinery lives in ``fault_harness`` (a plain module with a
unique name so same-directory imports cannot shadow the repository's
root test conftest)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from assistant.policy import load_policy
from assistant.storage import AssistantStore


@pytest.fixture()
def store(tmp_path):
    return AssistantStore(tmp_path / "faults.db")


@pytest.fixture()
def policy():
    return load_policy()
