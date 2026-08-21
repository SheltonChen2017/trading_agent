"""Refusal-direction tests for the Benzinga ratings vendor-audit tool.

The audit's evidentiary value rests on immutable, internally consistent
snapshots and stable row identities. These tests drive the dangerous
directions: overwrite, corruption, incomplete pagination, altered metadata,
row-count drift, duplicate or missing ids, timestamp-format confusion, and
credential leakage.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.audit_benzinga_ratings import (
    _last_updated_date_facts,
    _load_rows,
    _strip_key,
    compare,
    download,
)


def _write_snapshot(
    root: Path,
    *,
    name: str = "benzinga-ratings-test",
    complete: bool = True,
    corrupt: bool = False,
    rows: list[dict] | None = None,
    declared_page_rows: int | None = None,
) -> Path:
    snap = root / name
    raw = snap / "raw"
    raw.mkdir(parents=True)
    snapshot_rows = rows or [{"benzinga_id": "x1", "date": "2020-01-02"}]
    payload = json.dumps({"results": snapshot_rows}).encode()
    (raw / "2020-p0000.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    if corrupt:
        (raw / "2020-p0000.json").write_bytes(payload + b" ")
    page_rows = len(snapshot_rows) if declared_page_rows is None else declared_page_rows
    manifest = {
        "complete": complete,
        "partitions": [
            {
                "year": 2020,
                "rows": page_rows,
                "terminated_naturally": complete,
                "pages": [
                    {
                        "file": "2020-p0000.json",
                        "sha256": digest,
                        "rows": page_rows,
                    }
                ],
            }
        ],
    }
    manifest_bytes = json.dumps(manifest).encode()
    (snap / "manifest.json").write_bytes(manifest_bytes)
    (snap / "manifest.sha256").write_text(
        hashlib.sha256(manifest_bytes).hexdigest() + "\n", encoding="utf-8"
    )
    return snap


def test_download_refuses_an_existing_snapshot_directory(tmp_path, monkeypatch):
    """Snapshot immutability: restatement measurement dies if A is clobbered."""
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key-never-used")

    import datetime as real_datetime

    import scripts.audit_benzinga_ratings as mod

    # Capture the real class BEFORE patching: the module attribute being
    # patched is the shared datetime module, so a late import inside the
    # fake would resolve to the fake itself.
    frozen = real_datetime.datetime(2020, 1, 1, tzinfo=real_datetime.timezone.utc)

    class _FakeDatetime:
        @staticmethod
        def now(tz=None):
            return frozen

    monkeypatch.setattr(mod.dt, "datetime", _FakeDatetime)
    existing = tmp_path / "benzinga-ratings-20200101T000000Z"
    existing.mkdir(parents=True)
    with pytest.raises(SystemExit, match="REFUSED"):
        download(tmp_path)
    # The pre-existing directory was not touched.
    assert list(existing.iterdir()) == []


def test_analysis_refuses_a_hash_mismatch(tmp_path):
    """A corrupted or edited page must refuse, never silently analyse."""
    snap = _write_snapshot(tmp_path, corrupt=True)
    with pytest.raises(SystemExit, match="hash mismatch"):
        _load_rows(snap, allow_incomplete=False)


def test_analysis_refuses_a_manifest_hash_mismatch(tmp_path):
    """Completeness metadata cannot be edited without invalidating the snapshot."""
    snap = _write_snapshot(tmp_path)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    manifest["partitions"] = []
    (snap / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit, match="manifest hash mismatch"):
        _load_rows(snap, allow_incomplete=False)


def test_analysis_refuses_manifest_page_row_count_drift(tmp_path):
    """A hash-valid manifest still has to agree with the hashed page contents."""
    snap = _write_snapshot(tmp_path, declared_page_rows=2)
    with pytest.raises(SystemExit, match="row-count mismatch"):
        _load_rows(snap, allow_incomplete=False)


def test_analysis_refuses_an_incomplete_snapshot_without_override(tmp_path):
    """A truncated download must not masquerade as the full history."""
    snap = _write_snapshot(tmp_path, complete=False)
    with pytest.raises(SystemExit, match="incomplete"):
        _load_rows(snap, allow_incomplete=False)
    # The explicit override still works, for diagnosing partial downloads.
    assert _load_rows(snap, allow_incomplete=True)


def test_recorded_urls_never_carry_a_credential():
    for url in (
        "https://api.example.com/x?apiKey=SECRET&cursor=abc",
        "https://api.example.com/x?cursor=abc&api_key=SECRET",
        "https://api.example.com/x?token=SECRET",
    ):
        assert "SECRET" not in _strip_key(url)


@pytest.mark.parametrize(
    "bad_rows, message",
    [
        ([{"benzinga_id": "same"}, {"benzinga_id": "same"}], "duplicate"),
        ([{"benzinga_id": ""}], "no benzinga_id"),
    ],
)
def test_snapshot_comparison_refuses_unstable_identity_keys(
    tmp_path, capsys, bad_rows, message
):
    """Snapshot B cannot hide rows through dict overwrite or missing-id drops."""
    a = _write_snapshot(tmp_path, name="a", rows=[{"benzinga_id": "a1"}])
    b = _write_snapshot(tmp_path, name="b", rows=bad_rows)
    with pytest.raises(SystemExit, match=message):
        compare(a, b, allow_incomplete=False)
    assert "modified:" not in capsys.readouterr().out


def test_last_updated_facts_parse_legacy_and_iso_without_lexical_comparison():
    rows = [
        {
            "date": "2020-01-02",
            "last_updated": "01/02/2020 08:30:00",
        },
        {
            "date": "2020-01-02",
            "last_updated": "2020-01-03T01:00:00Z",
        },
        {
            "date": "2020-01-02",
            "last_updated": "05/01/2020 00:00:00",
        },
        {
            "date": "2020-01-02",
            "last_updated": "01/01/2020 23:59:59",
        },
    ]
    facts = _last_updated_date_facts(rows)
    assert facts == {
        "parsed": 4,
        "same_action_date": 1,
        "after_action_date": 2,
        "more_than_90_days_after": 1,
        "before_action_date": 1,
    }
