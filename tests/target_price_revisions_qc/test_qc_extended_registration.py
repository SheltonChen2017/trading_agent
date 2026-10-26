"""Prospective extended-study identities; no private inputs or outcomes."""
import hashlib
import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[2]
FREEZE_HASH = "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067"
CALENDAR_HASH = "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d"
PREFIX = ROOT / "research" / "target_price_revisions_qc"


def _bound(name, expected_hash):
    raw = (PREFIX / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_hash, "exact extended artifact"
    body = json.loads(raw)
    assert (json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode() == raw
    return body


def test_joint_extended_freeze_preserves_economics_and_old_counts():
    body = _bound("extended_study_freeze.json", FREEZE_HASH)
    assert body["study_id"] == "TPR-CAP-TILT-EXT26-20261010-v1"
    assert body["dates"]["first_session"] == "2021-01-04"
    assert body["dates"]["end"] == "2026-10-09"
    assert body["dates"]["signal_warmup_start"] == "2020-09-01"
    assert [(row["candidate_id"], row["arm"], row["capacity"], row["max_qc_attempts"])
            for row in body["candidates"]] == [
        ("TPR-CAP-TILT-EXT26-ON-BASE-v1", "tpr_on", "0.20", 3),
        ("TPR-CAP-TILT-EXT26-OFF-BASE-v1", "tpr_off", "0", 3),
    ]
    assert tuple(row["etf"] for row in body["universes"]) == (
        "SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX")
    assert body["construction"]["base_slot"] == "1/60"
    assert body["construction"]["sleeve_budget"] == "1/6"
    assert body["execution"]["capital_usd"] == "100000"
    assert body["execution"]["fees_usd_per_share"] == "0.01"
    assert body["execution"]["slippage_per_side"] == "0.001"
    assert body["execution"]["prior_session_volume_limit"] == "0.01"
    assert body["execution"]["buy_cash_fraction"] == "0.97"
    assert body["execution"]["decision_ny"] == "09:20"
    assert body["execution"]["cancel_ny"] == "09:35"
    assert body["history"]["old_cap_on_attempts"] == 3
    assert body["history"]["old_cap_off_attempts"] == 1
    assert body["history"]["prior_observed_looks"] == 16
    assert body["history"]["new_looks_at_freeze"] == 0
    assert body["operations"]["old_receipts_reused"] is False
    assert body["operations"]["d0_reopened"] is False
    assert body["comparisons"]["no_after_outcome_tuning"] is True
    assert body["comparisons"]["formal_alpha"] == "0"


def test_calendar_has_complete_continuous_weekly_cutoffs_and_no_holdout():
    body = _bound("extended_calendar.json", CALENDAR_HASH)
    assert body["study_freeze_sha256"] == FREEZE_HASH
    assert body["calendar_sources"] == {
        "exchange_calendars": "4.13.2", "pandas_market_calendars": "5.4.0",
        "session_open_close_parity": True,
    }
    sessions = body["warmup_sessions"] + body["valuation_sessions"]
    assert sessions == sorted(set(sessions))
    assert len(body["warmup_sessions"]) == 85
    assert len(body["valuation_sessions"]) == body["valuation_count"] == 1449
    assert body["valuation_sessions"][0] == "2021-01-04"
    assert body["valuation_sessions"][-1] == "2026-10-09"
    weeks = {}
    for day in body["valuation_sessions"]:
        stamp = datetime.strptime(day, "%Y-%m-%d").date()
        weeks.setdefault(stamp.isocalendar()[:2], day)
    assert [row["session"] for row in body["decisions"]] == list(weeks.values())
    assert len(body["decisions"]) == body["decision_count"] == 301
    ny = ZoneInfo("America/New_York")
    for row in body["decisions"]:
        assert row["prior_session"] == sessions[sessions.index(row["session"]) - 1]
        cutoff = datetime.fromisoformat(row["cutoff"])
        assert cutoff.astimezone(ny).date().isoformat() == row["prior_session"]
        assert cutoff.astimezone(ny).timetz().replace(tzinfo=None) == time(18)
        assert cutoff < datetime.combine(
            datetime.strptime(row["session"], "%Y-%m-%d").date(), time(9, 20), ny)
    assert body["no_market_outcomes"] is True
    assert all(day < "2027-09-01" for day in sessions)


def test_probe_is_seven_fixed_samples_not_full_capture_or_outcome_access():
    body = _bound("extended_study_freeze.json", FREEZE_HASH)
    probe = body["availability_probe"]
    assert probe["windows"] == [
        ["2020-09-01", "2020-12-31"], ["2021-01-01", "2021-12-31"],
        ["2022-01-01", "2022-12-31"], ["2023-01-01", "2023-12-31"],
        ["2024-01-01", "2024-12-31"], ["2025-01-01", "2025-12-31"],
        ["2026-01-01", "2026-10-09"],
    ]
    assert probe["max_requests"] == 7
    assert probe["query"] == {"limit": "1", "sort": "date.asc"}
    assert probe["max_response_bytes_each"] == 65536
    assert probe["request_seconds"] == 30
    assert (probe["retries"], probe["redirects"], probe["pagination"]) == (0, 0, 0)
    assert probe["claim_before_credentials"] is True
    assert probe["outcome_access"] is False


@pytest.mark.parametrize("name,expected", [
    ("extended_study_freeze.json", FREEZE_HASH),
    ("extended_calendar.json", CALENDAR_HASH),
])
def test_identity_check_refuses_valid_json_semantic_substitution(monkeypatch, name, expected):
    _bound(name, expected)
    original = Path.read_bytes
    raw = original(PREFIX / name)
    assert b'"2026-10-09"' in raw
    changed = raw.replace(b'"2026-10-09"', b'"2027-09-01"', 1)
    monkeypatch.setattr(Path, "read_bytes", lambda path:
        changed if path == PREFIX / name else original(path))
    with pytest.raises(AssertionError, match="exact extended artifact"):
        _bound(name, expected)
