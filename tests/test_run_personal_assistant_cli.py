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
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.run_personal_assistant as personal_assistant_cli
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.schemas import DecisionPacket, FindingProvenance, MarketRegime, EvidenceStatus, SignalEvidence
from assistant.storage import AssistantStore
from assistant.temporal_integrity import (
    MAX_MONITOR_INTERVAL_SECONDS,
    MAX_RECOVERY_WINDOW_SECONDS,
)
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


def test_activity_review_opens_the_operator_database_read_only():
    args = build_parser().parse_args(["ledger-activity-review"])
    assert args.read_only_store is True


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


@pytest.mark.parametrize("command", ["recover-stale", "recover-stale-claim"])
def test_recovery_cli_uses_the_canonical_maximum(command):
    maximum = str(int(MAX_RECOVERY_WINDOW_SECONDS))
    accepted = build_parser().parse_args(
        [command, "tp_123", "--stale-after-seconds", maximum]
    )
    assert accepted.stale_after_seconds == int(maximum)

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                command,
                "tp_123",
                "--stale-after-seconds",
                str(int(maximum) + 1),
            ]
        )


def test_monitor_poll_cli_uses_the_canonical_maximum():
    maximum = str(int(MAX_MONITOR_INTERVAL_SECONDS))
    accepted = build_parser().parse_args(
        ["monitor-orders", "--poll-seconds", maximum]
    )
    assert accepted.poll_seconds == int(maximum)

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["monitor-orders", "--poll-seconds", str(int(maximum) + 1)]
        )


@pytest.mark.parametrize("bad_limit", ["0", "-1"])
def test_list_limit_rejects_non_positive_values(bad_limit):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["list", "--limit", bad_limit])


def test_list_limit_accepts_a_positive_value():
    assert build_parser().parse_args(["list", "--limit", "1"]).limit == 1


def test_tax_report_year_rejects_negative_and_uses_non_negative_guard():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["tax-report", "--year", "-1"])
    assert build_parser().parse_args(
        ["tax-report", "--year", "0"]
    ).year == 0


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


def test_print_briefing_does_not_turn_an_unavailable_order_book_into_zero():
    packet = _packet_with_unreproduced_confirmed_finding()
    packet.portfolio.open_orders_available = False
    packet.analytics["open_order_count"] = None

    out = _captured_stdout(_print_briefing, packet)

    assert "open orders=unavailable" in out
    assert "open orders=0" not in out


def test_print_briefing_withholds_portfolio_values_when_risk_is_unavailable():
    packet = _packet_with_unreproduced_confirmed_finding()
    packet.risk.available = False
    packet.risk.unavailable_reason = "Portfolio integrity unavailable"
    packet.analytics["invested_pct"] = 99.9
    packet.analytics["unrealized_pnl"] = 12345.67

    out = _captured_stdout(_print_briefing, packet)

    assert "equity=unavailable" in out
    assert "cash=unavailable" in out
    assert "invested=unavailable" in out
    assert "unrealized P&L=unavailable" in out
    assert "99.9%" not in out
    assert "$12,345.67" not in out


def test_print_briefing_withholds_portfolio_values_when_analytics_are_unavailable():
    packet = _packet_with_unreproduced_confirmed_finding()
    packet.analytics.update(
        available=False,
        unavailable_reason="Portfolio analytics unavailable",
        position_count=None,
        invested_pct=None,
        unrealized_pnl=None,
    )

    out = _captured_stdout(_print_briefing, packet)

    assert "equity=unavailable" in out
    assert "cash=unavailable" in out
    assert "Positions=unavailable" in out
    assert "invested=unavailable" in out
    assert "unrealized P&L=unavailable" in out


def test_command_briefing_skips_portfolio_side_effects_when_evidence_unavailable(
    monkeypatch,
    capsys,
    tmp_path,
):
    import assistant.sleeve_notifications as sleeve_notifications
    import assistant.sleeve_reinvest as sleeve_reinvest

    packet = _packet_with_unreproduced_confirmed_finding()
    packet.risk.available = False
    packet.risk.unavailable_reason = "Portfolio integrity unavailable"
    packet.analytics.update(
        available=False,
        unavailable_reason="Portfolio analytics unavailable",
        position_count=None,
        invested_pct=None,
        unrealized_pnl=None,
    )
    calls = []

    class FakeStore:
        path = tmp_path / "assistant.db"

        def save_decision_packet(self, actual_packet):
            calls.append(("decision_packet", actual_packet))
            return 7

    monkeypatch.setattr(personal_assistant_cli, "_print_batched_warnings", lambda store: None)
    monkeypatch.setattr(personal_assistant_cli, "_packet", lambda **kwargs: packet)
    monkeypatch.setattr(
        sleeve_notifications,
        "run_sleeve_notification_cycle",
        lambda *args, **kwargs: calls.append(("sleeve", args, kwargs)),
    )
    monkeypatch.setattr(
        sleeve_reinvest,
        "reconcile_dividend_earmarks",
        lambda store: [],
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "capture_briefing_equity_snapshot",
        lambda *args, **kwargs: calls.append(("history_capture", args, kwargs)),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "portfolio_performance_report",
        lambda *args, **kwargs: calls.append(("history_report", args, kwargs)),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "build_descriptive_macro_context",
        lambda: {"available": False, "reason": "test fixture"},
    )

    personal_assistant_cli.command_briefing(
        SimpleNamespace(no_events=True),
        FakeStore(),
    )

    assert [call[0] for call in calls] == ["decision_packet"]
    output = capsys.readouterr().out
    assert "Sleeve engine notifications unavailable" in output
    assert "Portfolio history unavailable" in output
    assert "Persisted decision packet #7" in output


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


def test_command_risk_check_suppresses_derived_facts_when_risk_unavailable(
    monkeypatch,
    capsys,
):
    packet = _packet_with_unreproduced_confirmed_finding()
    packet.risk.available = False
    packet.risk.unavailable_reason = "Portfolio integrity unavailable"
    prohibited = []

    monkeypatch.setattr(personal_assistant_cli, "_packet", lambda **kwargs: packet)
    monkeypatch.setattr(personal_assistant_cli, "load_policy", lambda path: object())
    monkeypatch.setattr(
        personal_assistant_cli,
        "check_policy_compliance",
        lambda portfolio, policy: ["Portfolio integrity unavailable"],
    )
    for name in (
        "check_concentration",
        "find_correlated_clusters",
        "portfolio_risk_decomposition",
        "estimate_stress_impact",
    ):
        monkeypatch.setattr(
            personal_assistant_cli,
            name,
            lambda *args, _name=name, **kwargs: prohibited.append(_name),
        )

    command_risk_check(
        _StubArgs(benchmark="SPY", move_pct=-10.0),
        store=object(),
    )

    assert prohibited == []
    output = capsys.readouterr().out
    assert "POLICY VIOLATION: Portfolio integrity unavailable" in output
    assert "Portfolio risk analyses unavailable" in output
    assert "Estimated impact" not in output


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


# --- broker-activity ingestion ordering (2026-08-10): CAT fees arrive as
# non-trade account activities, which nothing ingested, so the nightly
# reconciliation drifted 1 cent per fee day and failed forever. These
# tests pin the repaired pipeline order: broker orders reconcile, app
# fills sync, broker activities sync, and only THEN is the snapshot
# reconciled -- so the reconciliation judges books that already contain
# every fee the broker deducted.


def test_ledger_reconcile_syncs_fills_and_activities_before_reconciling(
    monkeypatch, capsys
):
    calls = []
    store = object()
    args = SimpleNamespace(no_sync=False)
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(
        personal_assistant_cli,
        "sync_app_fills",
        lambda actual_store: calls.append(("fills", actual_store)),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "_sync_broker_activities_from_alpaca",
        lambda actual_store: calls.append(("activities", actual_store)),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "build_portfolio_snapshot_from_alpaca",
        lambda: calls.append(("snapshot", None)) or "snapshot",
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "reconcile_snapshot",
        lambda actual_store, snapshot: (
            calls.append(("reconcile", actual_store)),
            {"matched": True},
        )[1],
    )

    personal_assistant_cli.command_ledger_reconcile(args, store)

    assert calls == [
        ("fills", store),
        ("activities", store),
        ("snapshot", None),
        ("reconcile", store),
    ]


def test_ledger_reconcile_no_sync_skips_both_syncs(monkeypatch, capsys):
    calls = []
    args = SimpleNamespace(no_sync=True)
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(
        personal_assistant_cli,
        "sync_app_fills",
        lambda actual_store: calls.append("fills"),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "_sync_broker_activities_from_alpaca",
        lambda actual_store: calls.append("activities"),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "build_portfolio_snapshot_from_alpaca",
        lambda: "snapshot",
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "reconcile_snapshot",
        lambda actual_store, snapshot: {"matched": True},
    )

    personal_assistant_cli.command_ledger_reconcile(args, object())

    assert calls == []


def test_sync_broker_activities_from_alpaca_windows_the_fetch(monkeypatch):
    # Alpaca documents `after` as an exclusive created-after filter. Start
    # exactly at bootstrap so pre-bootstrap dividends and transfers cannot
    # block the first reconciliation even though opening cash contains them.
    captured = {}

    class FakeStore:
        def get_system_state(self, key, default=None):
            assert key == "ledger_bootstrap"
            return {"bootstrapped_at": "2026-08-05T18:22:58+00:00"}

    # Counter-review BAACR-001 moved the account-binding guard into this
    # helper. This test pins the FETCH WINDOW, so stub the guard rather than
    # re-testing it here; `test_scheduled_activity_sync_requires_account_binding`
    # covers the guard itself on every write path.
    monkeypatch.setattr(
        personal_assistant_cli, "_require_activity_account_binding",
        lambda store: None,
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "list_account_activities",
        lambda *, after=None: captured.setdefault("after", after) and []
        or [],
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "sync_broker_activities",
        lambda store, activities, *, created_after=None: {
            "inserted": 0,
            "activities": activities,
            "created_after": created_after,
        },
    )

    result = personal_assistant_cli._sync_broker_activities_from_alpaca(
        FakeStore()
    )
    assert captured["after"] == "2026-08-05T18:22:58+00:00"
    assert result["inserted"] == 0
    assert result["created_after"].isoformat() == captured["after"]


def test_operations_cycle_preserves_backup_and_health_after_activity_failure(
    monkeypatch, tmp_path
):
    calls = []
    activity_error = RuntimeError("unsupported DIV activity")

    class FakeStore:
        def upsert_operational_alert(self, **kwargs):
            calls.append("alert")
            return kwargs

    args = SimpleNamespace(
        cancel_stale=False,
        backup_directory=tmp_path / "backups",
        backup_max_age_hours=24,
        alerts_jsonl=None,
        policy=None,
    )
    policy = SimpleNamespace(max_order_age_minutes=60)
    monkeypatch.setattr(personal_assistant_cli.config, "PAPER_TRADING", True)
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(personal_assistant_cli, "load_policy", lambda path: policy)
    monkeypatch.setattr(
        personal_assistant_cli,
        "record_operational_policy_heartbeat",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "reconcile_nonterminal_orders",
        lambda *args, **kwargs: calls.append("orders") or {},
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "sync_app_fills",
        lambda store: calls.append("fills") or {},
    )

    def fail_activity_sync(store):
        calls.append("activities")
        raise activity_error

    monkeypatch.setattr(
        personal_assistant_cli,
        "_sync_broker_activities_from_alpaca",
        fail_activity_sync,
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "build_portfolio_snapshot_from_alpaca",
        lambda: calls.append("snapshot") or object(),
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "reconcile_snapshot",
        lambda *args: calls.append("reconcile") or {"matched": False},
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "ensure_recent_database_backup",
        lambda *args, **kwargs: calls.append("backup") or {},
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "run_operational_check",
        lambda *args, **kwargs: calls.append("health")
        or {"healthy": False, "alerts": []},
    )

    with pytest.raises(RuntimeError, match="unsupported DIV") as raised:
        personal_assistant_cli.command_operations_cycle(args, FakeStore())

    assert raised.value is activity_error
    assert calls == [
        "orders",
        "fills",
        "activities",
        "snapshot",
        "reconcile",
        "backup",
        "health",
        "alert",
    ]


# --- broker-activity acknowledgement review (2026-08-11) -----------------


def _acknowledgement_cli_store(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    store.set_system_state(
        "ledger_bootstrap",
        {
            "source": "alpaca",
            "account_id": "paper-account-1",
            "bootstrapped_at": "2026-08-05T18:22:58+00:00",
        },
    )
    return store


def _cli_activity(activity_id, activity_type, net_amount, **overrides):
    activity = {
        "id": activity_id,
        "activity_type": activity_type,
        "created_at": "2026-08-05T19:00:00+00:00",
        "date": "2026-08-05",
        "net_amount": net_amount,
        "status": "executed",
        "currency": "USD",
    }
    activity.update(overrides)
    return activity


def _patch_matching_broker(monkeypatch, activities):
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(
        personal_assistant_cli,
        "get_account",
        lambda: {"account_id": "paper-account-1"},
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "list_account_activities",
        lambda *, after=None: list(activities),
    )


def test_activity_review_is_read_only_and_lists_exact_refusals(
    tmp_path, monkeypatch, capsys
):
    store = _acknowledgement_cli_store(tmp_path)
    fee = _cli_activity("fee-1", "FEE", "-0.01", description="CAT fee")
    refused = _cli_activity("interest-1", "INT", "1.25")
    _patch_matching_broker(monkeypatch, [fee, refused])
    before = store.list_journal_postings()
    backup_state_before = store.get_system_state("last_database_backup")

    personal_assistant_cli.command_ledger_activity_review(SimpleNamespace(), store)

    payload = json.loads(capsys.readouterr().out)
    assert store.list_journal_postings() == before
    assert store.get_system_state("last_database_backup") == backup_state_before
    assert payload["refused_count"] == 1
    assert payload["refused"] == [
        {
            "activity_type": "INT",
            "date": "2026-08-05",
            "id": "interest-1",
            "net_amount": "1.25",
            "reason": "unhandled activity type INT",
        }
    ]


def test_activity_commands_refuse_a_different_broker_account_before_fetch(
    tmp_path, monkeypatch
):
    store = _acknowledgement_cli_store(tmp_path)
    calls = []
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(
        personal_assistant_cli,
        "get_account",
        lambda: {"account_id": "other-account"},
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "list_account_activities",
        lambda *, after=None: calls.append(after) or [],
    )

    with pytest.raises(SystemExit, match="does not match the ledger"):
        personal_assistant_cli.command_ledger_activity_review(
            SimpleNamespace(), store
        )
    assert calls == []


@pytest.mark.parametrize(
    "bootstrap",
    [
        None,
        {
            "source": "manual",
            "bootstrapped_at": "2026-08-05T18:22:58+00:00",
        },
    ],
)
def test_activity_commands_require_an_alpaca_bootstrap_before_broker_fetch(
    tmp_path, monkeypatch, bootstrap
):
    store = AssistantStore(tmp_path / "assistant.db")
    if bootstrap is not None:
        store.set_system_state("ledger_bootstrap", bootstrap)
    calls = []
    monkeypatch.setattr(personal_assistant_cli, "is_configured", lambda: True)
    monkeypatch.setattr(
        personal_assistant_cli,
        "get_account",
        lambda: calls.append("account") or {"account_id": "paper-account-1"},
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "list_account_activities",
        lambda *, after=None: calls.append("activities") or [],
    )

    with pytest.raises(SystemExit, match="Alpaca-bootstrapped"):
        personal_assistant_cli.command_ledger_activity_review(
            SimpleNamespace(), store
        )
    assert calls == []


def test_activity_acknowledge_only_accepts_a_currently_refused_row(
    tmp_path, monkeypatch
):
    store = _acknowledgement_cli_store(tmp_path)
    handled_fee = _cli_activity("fee-1", "FEE", "-0.01")
    _patch_matching_broker(monkeypatch, [handled_fee])
    args = SimpleNamespace(
        activity_id="fee-1",
        treatment="cash_transfer",
        operator="op",
        rationale="incorrect override",
        ticker=None,
    )

    with pytest.raises(SystemExit, match="not currently refused"):
        personal_assistant_cli.command_ledger_activity_acknowledge(args, store)
    assert store.list_broker_activity_acknowledgements() == []
    assert store.list_journal_postings() == []


def test_activity_acknowledge_records_but_does_not_post(
    tmp_path, monkeypatch, capsys
):
    store = _acknowledgement_cli_store(tmp_path)
    refused = _cli_activity("interest-1", "INT", "1.25")
    _patch_matching_broker(monkeypatch, [refused])
    args = SimpleNamespace(
        activity_id="interest-1",
        treatment="cash_transfer",
        operator="op",
        rationale="confirmed cash interest; temporary treatment",
        ticker=None,
    )

    personal_assistant_cli.command_ledger_activity_acknowledge(args, store)

    payload = json.loads(capsys.readouterr().out)
    assert payload["inserted"] is True
    assert store.get_broker_activity_acknowledgement("interest-1") is not None
    assert store.list_journal_postings() == []


def test_scheduled_activity_sync_requires_account_binding(monkeypatch):
    """BAACR-001: the guard belongs at the choke point, not only on the
    two standalone commands.

    `ledger-reconcile`, `paper-observation`, and `operations-cycle` all call
    `_sync_broker_activities_from_alpaca` BEFORE `reconcile_snapshot`, which
    was where the account binding was first checked. Mismatched credentials
    would therefore have written another account's fees, dividends, and
    transfers into this append-only journal and only then been refused --
    and the two scheduled callers run unattended every 10 minutes and
    nightly, so this is the higher-traffic path.

    The broker must not even be asked for activities once the binding fails.
    """
    fetched = []
    monkeypatch.setattr(
        personal_assistant_cli,
        "list_account_activities",
        lambda *, after=None: fetched.append(after) or [],
    )
    monkeypatch.setattr(
        personal_assistant_cli,
        "sync_broker_activities",
        lambda *a, **k: pytest.fail("must not journal on a binding failure"),
    )

    def refuse(store):
        raise SystemExit("Current Alpaca account does not match the ledger")

    monkeypatch.setattr(
        personal_assistant_cli, "_require_activity_account_binding", refuse
    )
    with pytest.raises(SystemExit, match="does not match the ledger"):
        personal_assistant_cli._sync_broker_activities_from_alpaca(object())
    assert fetched == [], "the activity endpoint was called despite a mismatch"


def test_the_binding_guard_runs_before_the_activity_fetch_on_every_write_path():
    """Source-level: each caller that journals activities must be covered.

    A behavioural test only covers the callers it names. This fails if a NEW
    path calls the sync helper, or if the guard is moved back out of it.
    """
    source = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "run_personal_assistant.py"
    ).read_text(encoding="utf-8")
    helper_start = source.index("def _sync_broker_activities_from_alpaca")
    helper_end = source.index("def command_ledger_bootstrap")
    helper_body = source[helper_start:helper_end]
    assert "_require_activity_account_binding(store)" in helper_body, (
        "the account-binding guard must run inside the single helper that "
        "turns broker activities into journal entries"
    )
    assert helper_body.index("_require_activity_account_binding") < helper_body.index(
        "list_account_activities"
    ), "the guard must run BEFORE the activity fetch"
