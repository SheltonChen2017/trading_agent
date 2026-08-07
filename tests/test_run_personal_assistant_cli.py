"""
Tests for scripts/run_personal_assistant.py's argument parser (focused on
--stale-after-seconds -- GPT review, 2026-07-29: the CLI accepted zero or
negative values with no validation at all, which would let a user reclaim
a genuinely active reconciliation immediately; the service-level check in
assistant.execution_service.recover_stale_reconciliation() is the
authoritative guard, this is only a usability check at the CLI layer) and
_print_briefing()'s user-facing evidence display (GPT review, 2026-07-30).

Run with: python -m pytest tests/test_run_personal_assistant_cli.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.run_personal_assistant as personal_assistant_cli
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.schemas import DecisionPacket, FindingProvenance, MarketRegime, EvidenceStatus, SignalEvidence
from assistant.storage import AssistantStore
from scripts.run_personal_assistant import _print_briefing, build_parser, command_risk_check


def test_top_level_help_renders_without_percent_format_errors():
    help_text = build_parser().format_help()
    assert "falls 10%" in help_text
    assert "monitor-orders" in help_text
    assert "cancel-order" in help_text
    assert "cancel-all-orders" in help_text
    assert "readiness" in help_text
    assert "ledger-reconcile" in help_text
    assert "ledger-bind-account" in help_text
    assert "ledger-dividend" in help_text
    assert "ledger-split" in help_text
    assert "ledger-transfer" in help_text
    assert "ledger-fee" in help_text
    assert "operations-check" in help_text
    assert "operations-cycle" in help_text
    assert "paper-epoch-start" in help_text
    assert "paper-observation" in help_text
    assert "promotion-status" in help_text
    assert "--database" in help_text


def test_recover_stale_accepts_a_positive_stale_after_seconds():
    args = build_parser().parse_args(["recover-stale", "tp_123", "--stale-after-seconds", "600"])
    assert args.stale_after_seconds == 600


def test_recover_stale_defaults_to_300():
    args = build_parser().parse_args(["recover-stale", "tp_123"])
    assert args.stale_after_seconds == 300


def test_recover_stale_rejects_zero():
    try:
        build_parser().parse_args(["recover-stale", "tp_123", "--stale-after-seconds", "0"])
        assert False, "expected argparse to reject zero"
    except SystemExit as exc:
        assert exc.code != 0


def test_recover_stale_rejects_negative():
    try:
        build_parser().parse_args(["recover-stale", "tp_123", "--stale-after-seconds", "-5"])
        assert False, "expected argparse to reject a negative value"
    except SystemExit as exc:
        assert exc.code != 0


def test_recover_stale_rejects_non_integer():
    try:
        build_parser().parse_args(["recover-stale", "tp_123", "--stale-after-seconds", "abc"])
        assert False, "expected argparse to reject a non-integer value"
    except SystemExit as exc:
        assert exc.code != 0


def test_production_foundation_commands_parse():
    assert (
        build_parser().parse_args(
            ["ledger-bootstrap", "--confirm", "bootstrap"]
        ).confirm
        == "bootstrap"
    )
    assert build_parser().parse_args(["ledger-reconcile"]).no_sync is False
    assert (
        build_parser().parse_args(
            ["ledger-bind-account", "--confirm", "bind account"]
        ).confirm
        == "bind account"
    )
    dividend = build_parser().parse_args(
        [
            "ledger-dividend",
            "--external-id",
            "aapl-div-1",
            "--ticker",
            "AAPL",
            "--gross-amount",
            "5.00",
            "--occurred-at",
            "2026-08-01T14:00:00+00:00",
            "--ex-date",
            "2026-07-10",
            "--amount-per-share",
            "0.25",
        ]
    )
    assert dividend.gross_amount == "5.00"
    split = build_parser().parse_args(
        [
            "ledger-split",
            "--external-id",
            "aapl-split-1",
            "--ticker",
            "AAPL",
            "--ratio",
            "4",
            "--occurred-at",
            "2026-08-01T14:00:00+00:00",
        ]
    )
    assert split.ratio == "4"
    transfer = build_parser().parse_args(
        [
            "ledger-transfer",
            "--external-id",
            "deposit-1",
            "--amount",
            "1000.00",
            "--occurred-at",
            "2026-08-01T14:00:00+00:00",
            "--description",
            "Broker cash deposit",
        ]
    )
    assert transfer.amount == "1000.00"
    fee = build_parser().parse_args(
        [
            "ledger-fee",
            "--external-id",
            "reg-fee-1",
            "--amount",
            "0.03",
            "--occurred-at",
            "2026-08-01T14:00:00+00:00",
            "--description",
            "Regulatory fee",
        ]
    )
    assert fee.amount == "0.03"
    cancel = build_parser().parse_args(
        ["cancel-order", "tp-1", "--confirm", "cancel"]
    )
    assert cancel.proposal_id == "tp-1"
    cancel_all = build_parser().parse_args(
        [
            "cancel-all-orders",
            "--confirm",
            "cancel all open orders",
            "--reason",
            "operator drill",
        ]
    )
    assert cancel_all.reason == "operator drill"
    promotion = build_parser().parse_args(
        ["promotion-status", "report.json", "--evidence-epoch", "paper-v1"]
    )
    assert promotion.evidence_epoch == "paper-v1"
    epoch = build_parser().parse_args(
        [
            "paper-epoch-start",
            "paper-v1",
            "--strategy-id",
            "scanner",
            "--strategy-version",
            "1.0.0",
            "--model-id",
            "deterministic-no-model",
        ]
    )
    assert epoch.evidence_epoch == "paper-v1"


def test_active_epoch_rejects_changed_runtime_lineage(tmp_path, monkeypatch):
    args = build_parser().parse_args(
        [
            "paper-epoch-start",
            "paper-v1",
            "--strategy-id",
            "scanner",
            "--strategy-version",
            "1.0.0",
            "--model-id",
            "deterministic-no-model",
        ]
    )
    store = AssistantStore(tmp_path / "assistant.db")
    monkeypatch.setattr(
        personal_assistant_cli,
        "_current_commit",
        lambda *, require_clean: "a" * 40,
    )
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(
        personal_assistant_cli,
        "get_account",
        lambda: {"paper": True, "account_id": "paper-account-1"},
    )
    personal_assistant_cli.command_paper_epoch_start(args, store)
    monkeypatch.setattr(
        personal_assistant_cli,
        "_current_commit",
        lambda *, require_clean: "b" * 40,
    )

    with pytest.raises(SystemExit, match="differs from the current runtime"):
        personal_assistant_cli._active_runtime_lineage(store, args)


def test_ledger_split_reconciles_broker_and_syncs_fills_before_mutation(
    monkeypatch,
):
    calls = []
    args = SimpleNamespace(
        policy="policy.json",
        external_id="split-1",
        ticker="AAPL",
        ratio="4",
        occurred_at="2026-07-31T13:30:00+00:00",
    )
    store = object()
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(
        personal_assistant_cli,
        "load_policy",
        lambda path: SimpleNamespace(max_order_age_minutes=30.0),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "reconcile_nonterminal_orders",
        lambda actual_store, **kwargs: (
            calls.append(("orders", actual_store)),
            {"checked": 0},
        )[1],
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "sync_app_fills",
        lambda actual_store: (
            calls.append(("fills", actual_store)),
            {"inserted": 0},
        )[1],
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "record_split",
        lambda actual_store, **kwargs: (
            calls.append(("split", actual_store)),
            True,
        )[1],
    )

    personal_assistant_cli.command_ledger_split(args, store)

    assert calls == [
        ("orders", store),
        ("fills", store),
        ("split", store),
    ]


def test_ledger_split_refuses_incomplete_broker_reconciliation(monkeypatch):
    calls = []
    args = SimpleNamespace(
        policy="policy.json",
        external_id="split-1",
        ticker="AAPL",
        ratio="4",
        occurred_at="2026-07-31T13:30:00+00:00",
    )
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(
        personal_assistant_cli,
        "load_policy",
        lambda path: SimpleNamespace(max_order_age_minutes=30.0),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "reconcile_nonterminal_orders",
        lambda store, **kwargs: {
            "errors": ["broker lookup timed out"],
            "skipped_too_recent": 0,
        },
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "sync_app_fills",
        lambda store: calls.append("fills"),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "record_split",
        lambda store, **kwargs: calls.append("split"),
    )

    with pytest.raises(SystemExit, match="reconciliation was incomplete"):
        personal_assistant_cli.command_ledger_split(args, object())

    assert calls == []


# --- _print_briefing() user-facing evidence display (GPT review,
# 2026-07-30): this CLI briefing was the last remaining consumer still
# printing the raw `status` value directly -- the Streamlit UI and the
# now-removed legacy run_morning_briefing.py were already corrected to
# use display_status.

def _packet_with_unreproduced_confirmed_finding(underfilled: bool = False):
    from assistant.portfolio_analytics import compute_portfolio_analytics

    snapshot = build_portfolio_snapshot([], cash=10_000.0)
    provenance_kwargs = dict(
        actual_start_date="2019-07-22", actual_end_date="2026-07-28", actual_row_count=1764,
        entry_timing="next_open", data_fetched_at="2026-07-28T00:00:00+00:00",
        reproduced_after_data_loader_fix=False,
    )
    if underfilled:
        provenance_kwargs["requested_lookback_sessions"] = 1764
        provenance_kwargs["actual_lookback_sessions"] = 907
    finding = SignalEvidence(
        label="Test finding", claim="Beats a baseline", status=EvidenceStatus.CONFIRMED,
        detail="...", source="test", relevant_tickers=[],
        provenance=FindingProvenance(**provenance_kwargs),
    )
    packet = DecisionPacket(
        generated_at="2026-01-01T00:00:00Z", portfolio=snapshot, risk=build_risk_exposure(snapshot),
        regime=MarketRegime(benchmark_ticker="QQQ", trend=None, volatility_regime=None,
                             trailing_volatility_pct=None, as_of="2026-01-01"),
        signals=[finding], upcoming_events=[], warnings=[],
        analytics=compute_portfolio_analytics(snapshot),
    )
    return packet


def _captured_stdout(fn, *args, **kwargs) -> str:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        fn(*args, **kwargs)
    return buffer.getvalue()


def test_print_briefing_never_shows_a_bare_confirmed_for_an_unreproduced_finding():
    packet = _packet_with_unreproduced_confirmed_finding()
    out = _captured_stdout(_print_briefing, packet)
    assert "NOT CURRENTLY PRODUCTION-AUTHORITATIVE" in out
    assert "[confirmed]" not in out


def test_print_briefing_surfaces_underfilled_dataset_warning():
    packet = _packet_with_unreproduced_confirmed_finding(underfilled=True)
    out = _captured_stdout(_print_briefing, packet)
    assert "907" in out
    assert "1764" in out


# --- risk-check subcommand (assistant/risk_copilot.py wiring)

def test_risk_check_parses_basket_only():
    args = build_parser().parse_args(["risk-check", "--basket", "tech"])
    assert args.basket == "tech"
    assert args.benchmark is None
    assert args.move_pct is None


def test_risk_check_parses_benchmark_and_move_pct_together():
    args = build_parser().parse_args(["risk-check", "--benchmark", "SPY", "--move-pct", "-10"])
    assert args.benchmark == "SPY"
    assert args.move_pct == -10.0


def test_risk_check_defaults_to_no_args():
    args = build_parser().parse_args(["risk-check"])
    assert args.basket is None
    assert args.benchmark is None
    assert args.move_pct is None


class _StubArgs:
    def __init__(self, basket=None, benchmark=None, move_pct=None):
        self.basket = basket
        self.benchmark = benchmark
        self.move_pct = move_pct


def test_command_risk_check_rejects_benchmark_without_move_pct():
    # Must raise BEFORE building a packet (no network/store access needed
    # to catch this) -- passing store=None would crash on any attempt to
    # proceed past the validation guard.
    try:
        command_risk_check(_StubArgs(benchmark="SPY", move_pct=None), store=None)
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_command_risk_check_rejects_move_pct_without_benchmark():
    try:
        command_risk_check(_StubArgs(benchmark=None, move_pct=-10.0), store=None)
        assert False, "expected SystemExit"
    except SystemExit:
        pass


if __name__ == "__main__":
    test_recover_stale_accepts_a_positive_stale_after_seconds()
    test_recover_stale_defaults_to_300()
    test_recover_stale_rejects_zero()
    test_recover_stale_rejects_negative()
    test_recover_stale_rejects_non_integer()
    test_print_briefing_never_shows_a_bare_confirmed_for_an_unreproduced_finding()
    test_print_briefing_surfaces_underfilled_dataset_warning()
    test_risk_check_parses_basket_only()
    test_risk_check_parses_benchmark_and_move_pct_together()
    test_risk_check_defaults_to_no_args()
    test_command_risk_check_rejects_benchmark_without_move_pct()
    test_command_risk_check_rejects_move_pct_without_benchmark()
    print("All run_personal_assistant CLI tests passed.")
