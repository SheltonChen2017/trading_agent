from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import research.analyst_revisions_v2.legacy_reproduction as legacy_module
from research.analyst_revisions_v2.legacy_reproduction import (
    LegacyReproductionBlocked,
    quarantine_legacy_runner,
)


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "script_name",
    [
        "run_analyst_target_significance_check",
        "run_execution_timing_revalidation",
    ],
)
def test_default_legacy_runner_refuses_before_fetch(monkeypatch, script_name: str) -> None:
    module = _load_script(script_name)
    touched = False

    def forbidden_fetch(*args, **kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("network/outcome fetch ran before quarantine")

    monkeypatch.setattr(module, "fetch_historical", forbidden_fetch)
    if hasattr(module, "fetch_price_target_history"):
        monkeypatch.setattr(module, "fetch_price_target_history", forbidden_fetch)
    with pytest.raises(LegacyReproductionBlocked, match="quarantined"):
        module.main([])
    assert not touched


def test_unregistered_reproduction_refuses_before_reading_dataset(tmp_path: Path) -> None:
    frozen = tmp_path / "frozen.bin"
    frozen.write_bytes(b"outcomes")
    with pytest.raises(LegacyReproductionBlocked, match="absent"):
        quarantine_legacy_runner(
            script_name="run_analyst_target_significance_check.py",
            argv=[
                "--reproduction-id",
                "legacy-reproduction-not-registered",
                "--frozen-dataset",
                str(frozen),
            ],
        )


def test_registered_missing_dataset_uses_named_quarantine_refusal(
    monkeypatch, tmp_path: Path
) -> None:
    entry = {
        "reproduction_id": "legacy-reproduction-registered",
        "script_name": "legacy.py",
        "frozen_dataset_sha256": "a" * 64,
        "producing_commit": "b" * 40,
        "classification": "historical_non_new_non_v2",
        "network_access": False,
        "may_update_active_findings": False,
        "owner_authorized": True,
    }
    monkeypatch.setattr(legacy_module, "_load_registry", lambda: (entry,))
    with pytest.raises(LegacyReproductionBlocked, match="missing or unreadable"):
        quarantine_legacy_runner(
            script_name="legacy.py",
            argv=[
                "--reproduction-id",
                "legacy-reproduction-registered",
                "--frozen-dataset",
                str(tmp_path / "missing.bin"),
            ],
        )
