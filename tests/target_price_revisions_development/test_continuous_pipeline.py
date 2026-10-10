"""End-to-end synthetic software proof, never an empirical strategy run."""
from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from research.target_price_revisions_development.events import normalize_fixture_events
from research.target_price_revisions_development import readiness, scoring, simulation

DECISION = "2026-10-05T22:00:00Z"
ORIGINAL_DECISION = "2026-10-01T22:00:00Z"


def pipeline_inputs():
    """Sixty-four complete binary controls, one interaction residual, no data."""
    universe, raw_versions = [], []
    for index in range(64):
        binary = [1 if index & (1 << bit) else -1 for bit in range(6)]
        response = 2 * binary[0] + 3 * binary[1] + binary[0] * binary[1]
        controls = binary[:-1] + [binary[-1] + 2]
        security = f"SYNTHETIC-SEC-{index}"
        universe.append({
            "security_id": security, "instrument_type": "common_stock", "venue": "XNYS",
            "primary_listing": True, "basis_id": "SYNTHETIC-BASIS", "adr_ratio": None,
            "underlying_id": None, "industry_id": "SYNTHETIC-INDUSTRY", "sector_id": "SYNTHETIC-SECTOR",
            "available_at_utc": "2026-10-01T20:00:00Z", "effective_session_index": 99,
            "controls": {"values": dict(zip(scoring.CONTROL_NAMES, map(str, controls))),
                         "available_at_utc": "2026-10-02T20:00:00Z", "effective_session_index": 100,
                         "complete": True, "evidence_id": "SYNTHETIC-CONTROLS", "price": "10",
                         "adv": "1000", "spread_fraction": "0.01", "capacity_fraction": "0.01",
                         "rating_state": "SYNTHETIC-NO-ACCEPTED-RATING-EVENT",
                         "catalyst_state": "SYNTHETIC-NO-COMMON-CATALYST",
                         "rating_inventory_complete": True, "catalyst_inventory_complete": True},
        })
        raw_versions.append({
            "event_id": f"SYNTHETIC-LINEAGE-{index}", "version_id": "SYNTHETIC-VERSION-1",
            "version_available_at_utc": "2026-10-01T16:00:00Z",
            "payload": {
                "effective_date": "2026-10-01", "public_precision": "instant",
                "public_available_at_utc": "2026-10-01T15:00:00Z", "public_available_date": None,
                "public_evidence_id": "SYNTHETIC-PUBLIC-EVIDENCE",
                "compatibility_evidence_id": "SYNTHETIC-COMPATIBILITY-EVIDENCE",
                "ingested_at_utc": "2026-10-01T16:10:00Z",
                "action": "raises" if response > 0 else "lowers" if response < 0 else "maintains",
                "new_target": str(100 + 10 * response), "prior_target": "100",
                "new_security_id": security, "prior_security_id": security,
                "new_share_class_id": "SYNTHETIC-CLASS", "prior_share_class_id": "SYNTHETIC-CLASS",
                "new_currency": "USD", "prior_currency": "USD", "new_horizon": "SYNTHETIC-12-MONTH",
                "prior_horizon": "SYNTHETIC-12-MONTH", "new_basis": "raw", "prior_basis": "raw",
                "new_adjustment_vintage": "SYNTHETIC-NO-ADJUSTMENT",
                "prior_adjustment_vintage": "SYNTHETIC-NO-ADJUSTMENT",
            },
        })
    normalized = normalize_fixture_events(
        raw_versions, decision_cutoff_utc=ORIGINAL_DECISION,
        sessions=({"session_date": "2026-10-02", "open_utc": "2026-10-02T13:30:00Z"},),
    )
    assert len(normalized.selected_events) == 64
    assert {event.eligible_open_utc for event in normalized.selected_events} == {"2026-10-02T13:30:00+00:00"}
    enriched = tuple({
        "lineage_id": event.event_id, "version_id": event.version_id, "security_id": event.security_id,
        "institution_id": "SYNTHETIC-INSTITUTION", "catalyst_id": "SYNTHETIC-CATALYST",
        "eligible_session_index": 100, "available_at_utc": event.ingested_at_utc,
        "payload": {"new_target": event.new_target, "prior_target": event.prior_target,
                    "pre_event_price": "10", "target_basis_id": "SYNTHETIC-BASIS",
                    "price_basis_id": "SYNTHETIC-BASIS", "price_available_at_utc": "2026-09-30T20:00:00Z",
                    "information_at_utc": event.public_available_at_utc,
                    "price_session_index": 98, "information_session_index": 99},
    } for event in normalized.selected_events)
    config = {"clip_absolute": "10", "industry_min_total": 3, "industry_min_active": 2,
              "sector_min_total": 3, "sector_min_active": 2, "min_price": "1", "min_adv": "100",
              "max_spread_fraction": "0.02", "max_capacity_fraction": "0.1"}
    return universe, enriched, config


def continuous_targets(reverse=False):
    universe, enriched, config = pipeline_inputs()
    stocks = scoring.score_fixture_stocks(
        tuple(reversed(universe)) if reverse else universe,
        tuple(reversed(enriched)) if reverse else enriched,
        cutoff_utc=DECISION, decision_session_index=101, config=config, inventory_complete=True,
    )
    ranked = scoring.residualize_fixture_scores(stocks)
    assert all(row.score is not None for row in ranked.rows)
    assert {row.percentile for row in ranked.rows} == {"1/4", "3/4"}
    projection = scoring.project_fixture_etf({
        "etf_id": "SYNTHETIC-ETF-A", "product_type": "unlevered_equity_etf", "complete": True,
        "available_at_utc": "2026-10-02T20:00:00Z", "captured_at_utc": "2026-10-02T20:01:00Z",
        "effective_session_index": 100, "cash_weight": "0.01", "residual_weight": "0",
        "cash_evidence_id": "SYNTHETIC-CASH", "residual_evidence_id": "SYNTHETIC-RESIDUAL",
        "holdings": ({"security_id": "SYNTHETIC-SEC-0", "weight": "0.99", "mapped": True,
                      "mapping_evidence_id": "SYNTHETIC-MAPPING"},),
    }, ranked, cutoff_utc=DECISION, decision_session_index=101, max_age_sessions=5)
    assert projection.state == "VALID_NONZERO"
    targets = scoring.build_fixture_targets(
        ({"etf_id": projection.etf_id, "state": projection.state, "desired_weight": "0.2",
          "sector_id": "SYNTHETIC-SECTOR", "peer_id": "SYNTHETIC-PEER"},),
        ({"etf_id": "SYNTHETIC-ETF-OLD", "weight": "0.1"},),
        cutoff_utc=DECISION, decision_session_index=101, max_names=2,
        name_cap="0.3", sector_cap="0.5", peer_cap="0.5", additions_cap="0.2",
    )
    return stocks, ranked, projection, targets


def test_original_d1_eligibility_flows_through_scoring_projection_and_targets():
    stocks, ranked, projection, targets = continuous_targets()
    assert {event.age_sessions for event in stocks.versions} == {1}
    assert projection.mapped_weight == "1" and projection.observed_weight == "0.99"
    assert Decimal(projection.raw_score) > 0
    assert dict((row.etf_id, row.weight) for row in targets.targets) == {
        "SYNTHETIC-ETF-A": "0.2", "SYNTHETIC-ETF-OLD": "0",
    }
    assert targets.cash_weight == "0.8"
    for result in (stocks, ranked, projection, targets):
        assert all(flag is False for _, flag in result.authority)


def test_continuous_pipeline_is_order_and_decimal_context_invariant():
    with localcontext() as ctx:
        ctx.prec = 7
        first = continuous_targets()
    with localcontext() as ctx:
        ctx.prec = 110
        second = continuous_targets(reverse=True)
    assert first == second
    assert scoring.fixture_target_sha256(first[-1]) == scoring.fixture_target_sha256(second[-1])


def test_complete_synthetic_pipeline_cannot_grant_real_backtest_readiness():
    targets = continuous_targets()[-1]
    identity = scoring.fixture_target_sha256(targets)
    frozen = readiness.freeze_fixture_run_spec({
        "schema": "tpr-synthetic-run-spec-v1", "run_id": "SYNTHETIC-CONTINUOUS-RUN",
        "target": "synthetic-local-order-based", "created_at_utc": "2026-10-06T00:00:00Z",
        "expires_at_utc": "2026-10-12T00:00:00Z",
        "lineage": {name: identity for name in ("candidate_sha256", "code_sha256", "data_sha256", "config_sha256", "fold_sha256")},
        "plan_sha256": readiness.D0_PLAN_SHA256, "d0_report_sha256": readiness.D0_REPORT_SHA256,
        "synthetic_outcome_window": {"start": "2020-01-01", "end": "2020-12-31"},
        "accepted_risks": list(readiness.REQUIRED_RISKS),
        "authority": dict.fromkeys(readiness.AUTHORITY_KEYS, False), "d0_audit": "spent-not-renewable",
        "evaluation_policy": {"mode": "order-based", "max_qc_attempts": 3, "after_three_unsuccessful": "mia-recovery-required"},
    })
    inventory = tuple({"requirement_id": name, "fixture_id": "SYNTHETIC-PIPELINE", "fixture_sha256": identity}
                      for name in readiness.REQUIREMENTS)
    report = readiness.evaluate_fixture_readiness(
        frozen, inventory, as_of_utc="2026-10-06T00:00:00Z",
        software_review_policy=readiness.SOFTWARE_REVIEW_OWNER_WAIVED,
    )
    assert report.real_backtest_ready is False
    assert report.actual_qc_attempts == report.actual_outcome_reads == 0
    assert report.independent_review_required is False
    assert all(row.status == "synthetic-not-admission" for row in report.requirements
               if row.requirement_id != "reviewed_candidate")
    assert "current_fixture_scope_excludes_data_outcomes_qc" in report.blockers
    assert "independent_software_review_required" not in report.blockers


def execute_continuous(targets, portfolio=None):
    if portfolio is None:
        portfolio = simulation.freeze_fixture_portfolio(
            "900", ({"etf_id": "SYNTHETIC-ETF-OLD", "shares": 10},),
        )
    return simulation.execute_fixture_open(
        portfolio, targets,
        quotes={name: {"price": "10", "observed_at_utc": "2026-10-06T13:30:00Z"}
                for name in ("SYNTHETIC-ETF-A", "SYNTHETIC-ETF-OLD")},
        open_utc="2026-10-06T13:30:00Z", open_session_index=102,
        expected_target_sha256=scoring.fixture_target_sha256(targets),
        expected_state_sha256=portfolio.sha256,
        fee_per_order="1", slippage_bps="100", name_cap="0.3",
    )


def test_precomputed_target_packet_completes_a_synthetic_order_transition_once():
    targets = continuous_targets()[-1]
    result = execute_continuous(targets)
    assert result.replayed is False and result.real_backtest_ready is False
    assert [fill.side for fill in result.fills] == ["sell", "buy"]
    assert result.fills[0].etf_id == "SYNTHETIC-ETF-OLD" and result.fills[0].shares == 10
    cash = Fraction(900)
    for fill in result.fills:
        if fill.side == "sell":
            cash += fill.shares * Fraction(fill.unit_price) - Fraction(fill.fee)
        else:
            cash -= fill.shares * Fraction(fill.unit_price) + Fraction(fill.fee)
    assert Fraction(result.portfolio.cash) == cash and cash >= 0
    assert dict((row.etf_id, row.shares) for row in result.portfolio.positions)["SYNTHETIC-ETF-OLD"] == 0
    replay = execute_continuous(targets, result.portfolio)
    assert replay.replayed is True and replay.fills == ()
    assert replay.portfolio == result.portfolio and replay.receipt == result.receipt
    assert all(flag is False for _, flag in result.authority)


def test_full_fixture_pipeline_has_no_file_network_or_operator_dependency(monkeypatch):
    import builtins
    import io
    import os
    import socket

    def refuse(*args, **kwargs):
        pytest.fail("synthetic pipeline attempted I/O")

    for module, name in ((builtins, "open"), (io, "open"), (os, "open"), (socket, "socket")):
        monkeypatch.setattr(module, name, refuse)
    targets = continuous_targets()[-1]
    result = execute_continuous(targets)
    assert result.real_backtest_ready is False and result.fills


@pytest.mark.parametrize("binding", ["sector", "peer", "names"])
def test_each_group_or_name_count_cap_binds_independently(binding):
    """Other caps are deliberately looser; don't prove one with another."""
    candidates = tuple({
        "etf_id": "SYNTHETIC-ETF-" + name, "state": "VALID_NONZERO", "desired_weight": "0.4",
        "sector_id": "SYNTHETIC-SECTOR" + ("" if binding == "sector" else "-" + name),
        "peer_id": "SYNTHETIC-PEER" + ("" if binding == "peer" else "-" + name),
    } for name in ("A", "B"))
    result = scoring.build_fixture_targets(
        candidates, (), cutoff_utc=DECISION, decision_session_index=101,
        max_names=1 if binding == "names" else 2, name_cap="1", additions_cap="1",
        sector_cap="0.6" if binding == "sector" else "1",
        peer_cap="0.6" if binding == "peer" else "1",
    )
    weights = dict((row.etf_id, row.weight) for row in result.targets)
    assert weights == {"SYNTHETIC-ETF-A": "0.4", "SYNTHETIC-ETF-B": "0" if binding == "names" else "0.2"}
    assert result.cash_weight == ("0.6" if binding == "names" else "0.4")
