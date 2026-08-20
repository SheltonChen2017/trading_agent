"""Refusal-direction tests for the Benzinga ratings vendor-audit tool.

The audit's evidentiary value rests on three refusals: an existing snapshot
is never overwritten, a corrupted page is never silently analysed, and an
incomplete download is never analysed as if it were complete. Each is tested
in the dangerous direction. A fourth test pins the credential-stripping
helper so a recorded URL can never carry a key.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.audit_benzinga_ratings import _load_rows, _strip_key, download


def _write_snapshot(root: Path, *, complete: bool = True, corrupt: bool = False) -> Path:
    snap = root / "benzinga-ratings-test"
    raw = snap / "raw"
    raw.mkdir(parents=True)
    payload = json.dumps({"results": [{"benzinga_id": "x1", "date": "2020-01-02"}]}).encode()
    (raw / "2020-p0000.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    if corrupt:
        (raw / "2020-p0000.json").write_bytes(payload + b" ")
    manifest = {
        "complete": complete,
        "partitions": [
            {
                "year": 2020,
                "rows": 1,
                "terminated_naturally": complete,
                "pages": [{"file": "2020-p0000.json", "sha256": digest, "rows": 1}],
            }
        ],
    }
    (snap / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
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
