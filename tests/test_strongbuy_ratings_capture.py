"""SBR-1 regressions: the Strong-Buy ratings capture runtime.

Dangerous directions per the frozen capture preregistration: a failed
ticker silently dropped, a month relabeled across the UTC/ET boundary,
a crash between the snapshot and manifest writes papered over, boolean
or negative counts coerced into data, and a second same-month capture
rewriting history.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from scripts.capture_analyst_ratings import (
    RatingsCaptureError,
    capture,
    load_config,
)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 19, 21, 15, tzinfo=UTC)   # 17:15 ET


def _config(universe=("AAA", "BBB")) -> dict:
    return {"stream_name": "strongbuy-ratings", "universe": list(universe)}


def _fetch_ok(ticker: str) -> dict:
    return {"strongBuy": 10, "buy": 5, "hold": 3, "sell": 1, "strongSell": 0}


def test_capture_writes_canonical_rows_and_manifest_hash(tmp_path: Path):
    message = capture(_config(), tmp_path, NOW, fetch_fn=_fetch_ok)
    assert message == "captured snapshot-2026-08.jsonl: 2/2 available"
    body = (tmp_path / "snapshot-2026-08.jsonl").read_text(encoding="utf-8")
    lines = body.strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["ticker"] == "AAA" and first["available"] is True
    assert first["total"] == 19 and first["strongBuy"] == 10
    assert first["month"] == "2026-08"
    # Canonical: sorted keys, no whitespace.
    assert lines[0] == json.dumps(first, sort_keys=True,
                                  separators=(",", ":"))
    manifest = json.loads((tmp_path / "manifest.json").read_text("utf-8"))
    entry = manifest["snapshots"]["snapshot-2026-08.jsonl"]
    assert entry["sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert entry["tickers"] == 2 and entry["available"] == 2


def test_failed_ticker_is_recorded_not_dropped(tmp_path: Path):
    def flaky(ticker):
        if ticker == "BBB":
            raise ConnectionError("provider down")
        return _fetch_ok(ticker)

    message = capture(_config(), tmp_path, NOW, fetch_fn=flaky)
    assert message.endswith("1/2 available")
    rows = [json.loads(line) for line in
            (tmp_path / "snapshot-2026-08.jsonl").read_text("utf-8")
            .strip().split("\n")]
    assert len(rows) == 2                       # never dropped
    failed = rows[1]
    assert failed["ticker"] == "BBB"
    assert failed["available"] is False
    assert failed["error_class"] == "ConnectionError"
    assert "strongBuy" not in failed            # no fabricated counts


@pytest.mark.parametrize("bad", [
    {"strongBuy": -1, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0},
    {"strongBuy": True, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0},
    {"strongBuy": 1.5, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0},
    {"buy": 0, "hold": 0, "sell": 0, "strongSell": 0},
])
def test_invalid_counts_become_per_ticker_failures(tmp_path: Path, bad):
    capture(_config(("AAA",)), tmp_path, NOW, fetch_fn=lambda t: bad)
    row = json.loads((tmp_path / "snapshot-2026-08.jsonl")
                     .read_text("utf-8").strip())
    assert row["available"] is False
    assert row["error_class"] == "RatingsCaptureError"


def test_second_capture_in_the_same_month_is_a_noop(tmp_path: Path):
    capture(_config(), tmp_path, NOW, fetch_fn=_fetch_ok)
    body_before = (tmp_path / "snapshot-2026-08.jsonl").read_bytes()

    def must_not_be_called(ticker):
        raise AssertionError("no re-fetch on an up-to-date month")

    message = capture(_config(), tmp_path, NOW + dt.timedelta(days=3),
                      fetch_fn=must_not_be_called)
    assert message.startswith("up to date")
    assert (tmp_path / "snapshot-2026-08.jsonl").read_bytes() == body_before


def test_month_is_labeled_in_market_time_not_utc(tmp_path: Path):
    # 2026-09-01 00:30 UTC is still August 31 20:30 in New York.
    boundary = dt.datetime(2026, 9, 1, 0, 30, tzinfo=UTC)
    capture(_config(("AAA",)), tmp_path, boundary, fetch_fn=_fetch_ok)
    assert (tmp_path / "snapshot-2026-08.jsonl").exists()
    assert not (tmp_path / "snapshot-2026-09.jsonl").exists()


def test_naive_timestamp_is_refused(tmp_path: Path):
    with pytest.raises(RatingsCaptureError, match="timezone-aware"):
        capture(_config(), tmp_path, dt.datetime(2026, 8, 19, 21, 15),
                fetch_fn=_fetch_ok)
    assert not any(tmp_path.iterdir())          # nothing written


def test_orphan_snapshot_without_manifest_entry_refuses(tmp_path: Path):
    (tmp_path / "snapshot-2026-08.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(RatingsCaptureError, match="without a manifest entry"):
        capture(_config(), tmp_path, NOW, fetch_fn=_fetch_ok)


def test_hash_mismatch_refuses_instead_of_continuing(tmp_path: Path):
    capture(_config(), tmp_path, NOW, fetch_fn=_fetch_ok)
    path = tmp_path / "snapshot-2026-08.jsonl"
    path.write_text(path.read_text("utf-8") + "tampered\n", encoding="utf-8")
    with pytest.raises(RatingsCaptureError, match="does not match"):
        capture(_config(), tmp_path, NOW, fetch_fn=_fetch_ok)


def test_manifest_entry_with_missing_file_refuses(tmp_path: Path):
    capture(_config(), tmp_path, NOW, fetch_fn=_fetch_ok)
    (tmp_path / "snapshot-2026-08.jsonl").unlink()
    with pytest.raises(RatingsCaptureError, match="file is missing"):
        capture(_config(), tmp_path, NOW, fetch_fn=_fetch_ok)


def test_config_refusals(tmp_path: Path):
    good = {"stream_name": "s", "universe": ["AAA"]}
    path = tmp_path / "config.json"

    for broken, message in [
        ({**good, "universe": []}, "non-empty"),
        ({**good, "universe": ["AAA", "AAA"]}, "duplicate"),
        ({**good, "universe": ["aaa"]}, "malformed"),
        ({**good, "universe": ["TOOLONG"]}, "malformed"),
        ({"universe": ["AAA"]}, "stream_name"),
    ]:
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(RatingsCaptureError, match=message):
            load_config(path)
    path.write_text(json.dumps(good), encoding="utf-8")
    assert load_config(path)["universe"] == ["AAA"]


def test_committed_config_is_loadable_and_frozen_shape():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "docs" / "operations"
                         / "strongbuy_ratings_config.json")
    assert config["stream_name"] == "strongbuy-ratings"
    assert len(config["universe"]) == 102
    assert len(set(config["universe"])) == 102


def test_capture_never_imports_evaluation_machinery():
    """Preregistration section 6: joining snapshots to prices is an
    evaluation look. The capture runtime must not even import price,
    backtest, or analyser machinery."""
    import ast
    source = (Path(__file__).resolve().parents[1] / "scripts"
              / "capture_analyst_ratings.py").read_text(encoding="utf-8")
    forbidden = ("backtest", "market_analytics", "analyse_qc",
                 "strategies", "signals", "execution", "ml")
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            root_name = name.split(".")[0]
            assert root_name not in forbidden, name
