"""The ADR-required CLI `review unavailable` surface for committee reviews.

Every failure mode must produce one unmistakable
"Review unavailable (<code>): ..." line and exit 2 — never a traceback,
never a partial review — and an accepted review must be printed with its
citations, audit-persisted, and remain purely advisory (the proposal row is
untouched). No test contacts a real provider: gates and the provider are
monkeypatched at the CLI module's own names.

Run with: python -m pytest tests/test_committee_cli.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import scripts.run_personal_assistant as cli
from assistant.storage import AssistantStore
from test_committee_foundation import (  # noqa: E402
    _FakeProvider,
    _packet,
    _valid_raw_review,
)

_BASE_TIME = datetime(2026, 8, 4, 18, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path):
    return AssistantStore(tmp_path / "committee-cli.db")


def _seed_sell_proposal(store, proposal_id="tp_cli", *, side="sell", before=50.0, after=25.0):
    proposal = {
        "proposal_id": proposal_id,
        "created_at": _BASE_TIME.isoformat(),
        "expires_at": (_BASE_TIME + timedelta(hours=4)).isoformat(),
        "status": "proposed",
        "idempotency_key": f"idem-{proposal_id}",
        "evidence_status": "deterministic_risk_policy",
        "intent": {
            "ticker": "NVDA",
            "side": side,
            "shares": 5,
            "order_type": "market",
            "rationale": "risk reduction",
        },
        "reference_price": 200.0,
        "expected_impact": {
            "trade_value": 1_000.0,
            "position_weight_before_pct": before,
            "position_weight_after_pct": after,
            "cash_before": 2_000.0,
            "cash_after": 3_000.0,
            "invested_pct_after": 25.0,
        },
    }
    store.save_proposal(proposal)
    return proposal


def _args(proposal_id="tp_cli", timeout_seconds=30.0):
    return type(
        "Args", (), dict(proposal_id=proposal_id, no_events=True, timeout_seconds=timeout_seconds)
    )()


def _enable_gates(monkeypatch, provider):
    monkeypatch.setattr(cli, "is_anthropic_committee_configured", lambda: True)
    monkeypatch.setattr(cli, "is_anthropic_committee_experiment_enabled", lambda: True)
    monkeypatch.setattr(cli, "AnthropicCommitteeProvider", lambda: provider)
    monkeypatch.setattr(cli, "_packet", lambda include_events=True: _packet())


def _unavailable_line(capsys) -> str:
    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("Review unavailable (")
    ]
    assert len(lines) == 1, "exactly one unmistakable unavailable line"
    return lines[0]


def test_missing_api_key_is_a_clear_unavailable_state(store, monkeypatch, capsys):
    monkeypatch.setattr(cli, "is_anthropic_committee_configured", lambda: False)
    with pytest.raises(SystemExit) as excinfo:
        cli.command_committee_review(_args(), store)
    assert excinfo.value.code == 2
    line = _unavailable_line(capsys)
    assert "(not_configured)" in line
    assert "no provider call was made" in line


def test_experiment_gate_off_is_a_clear_unavailable_state(store, monkeypatch, capsys):
    monkeypatch.setattr(cli, "is_anthropic_committee_configured", lambda: True)
    monkeypatch.setattr(
        cli, "is_anthropic_committee_experiment_enabled", lambda: False
    )
    with pytest.raises(SystemExit) as excinfo:
        cli.command_committee_review(_args(), store)
    assert excinfo.value.code == 2
    line = _unavailable_line(capsys)
    assert "(experiment_disabled)" in line
    assert "ENABLE_EXPERIMENTAL_COMMITTEE=1" in line


def test_unknown_proposal_is_a_clear_unavailable_state(store, monkeypatch, capsys):
    _enable_gates(monkeypatch, _FakeProvider(_valid_raw_review()))
    with pytest.raises(SystemExit):
        cli.command_committee_review(_args("tp_missing"), store)
    assert "(unknown_proposal)" in _unavailable_line(capsys)


def test_projection_refusal_is_a_clear_unavailable_state(store, monkeypatch, capsys):
    """A buy can never even reach the provider: the projection refusal is
    surfaced as review-unavailable, and the provider is never called."""
    provider = _FakeProvider(_valid_raw_review())
    _enable_gates(monkeypatch, provider)
    _seed_sell_proposal(store, side="buy")
    with pytest.raises(SystemExit):
        cli.command_committee_review(_args(), store)
    line = _unavailable_line(capsys)
    assert "(projection_refused)" in line
    assert provider.calls == 0


def test_provider_failure_is_a_clear_unavailable_state_with_audit(
    store, monkeypatch, capsys
):
    _enable_gates(monkeypatch, _FakeProvider(error=TimeoutError("late")))
    _seed_sell_proposal(store)
    with pytest.raises(SystemExit):
        cli.command_committee_review(_args(), store)
    assert "(provider_error)" in _unavailable_line(capsys)
    runs = store.list_ai_runs(function_name="run_committee_review")
    assert len(runs) == 1 and not runs[0]["success"]


def test_validation_rejection_lists_issue_codes(store, monkeypatch, capsys):
    bad = _valid_raw_review()
    bad["summary"]["text"] = "NVDA weight is 99 percent."
    _enable_gates(monkeypatch, _FakeProvider(bad))
    _seed_sell_proposal(store)
    with pytest.raises(SystemExit):
        cli.command_committee_review(_args(), store)
    line = _unavailable_line(capsys)
    assert "(validation_rejected)" in line
    assert "unsupported_number" in line


def test_accepted_review_prints_citations_audits_and_stays_advisory(
    store, monkeypatch, capsys
):
    _enable_gates(monkeypatch, _FakeProvider(_valid_raw_review()))
    _seed_sell_proposal(store)

    cli.command_committee_review(_args(), store)

    out = capsys.readouterr().out
    assert "Committee review ACCEPTED" in out
    assert "advisory only, not a trade instruction" in out
    assert "verdict: support_with_caution" in out
    assert "sources: metric.leveraged_etf_exposure_pct" in out
    assert "exact human approval and deterministic revalidation" in out

    runs = store.list_ai_runs(function_name="run_committee_review")
    assert len(runs) == 1 and runs[0]["success"]
    # Advisory only: the stored proposal is byte-identical afterwards.
    assert store.get_proposal("tp_cli")["status"] == "proposed"


def test_audit_write_failure_makes_the_review_unavailable(store, monkeypatch, capsys):
    """The ADR makes the audit row mandatory: a review whose audit cannot
    be persisted must not be displayed as accepted."""
    _enable_gates(monkeypatch, _FakeProvider(_valid_raw_review()))
    _seed_sell_proposal(store)

    def _refuse_audit(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "record_ai_run", _refuse_audit)
    with pytest.raises(SystemExit):
        cli.command_committee_review(_args(), store)
    out_line = _unavailable_line(capsys)
    assert "(audit_persistence_failed)" in out_line
