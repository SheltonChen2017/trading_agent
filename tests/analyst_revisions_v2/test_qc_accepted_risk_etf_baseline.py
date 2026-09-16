import hashlib
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_etf_baseline_evaluator as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_etf_baseline_qc_runtime as qc_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_qc_projection as projection,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as stock,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_submission_adapter as adapter,
)


def _sessions():
    result = []
    current = date(2013, 1, 2)
    end = date(2026, 4, 30)
    while current <= end:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return tuple(result)


def _input():
    sessions = _sessions()
    session_rows = tuple(
        {
            "schema": stock.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )
    memberships = tuple(
        stock.build_membership_record(
            security_id=f"perm-security-{index:02d}",
            first_session_index=0,
            last_session_index_exclusive=len(sessions),
            sector_id="sector-technology",
        )
        for index in range(20)
    )
    eligible = sessions.index("2020-11-30")
    contributions = []
    for view in stock.SOURCE_VIEW_IDS:
        for index in range(20):
            action = "downgrades" if index < 10 else "upgrades"
            delta = Fraction(index - 10 if index < 10 else index - 9, 10)
            contributions.append(
                stock.build_contribution_record(
                    source_view_id=view,
                    security_id=f"perm-security-{index:02d}",
                    eligible_session_index=eligible,
                    institution_id=f"firm-{index:02d}",
                    common_event_id=f"event-{index:02d}",
                    rating_action=action,
                    firm_delta=delta,
                    global_delta=delta / 2,
                    source_row_sha256=hashlib.sha256(
                        f"source-{view}-{index}".encode("ascii")
                    ).hexdigest(),
                )
            )
    lineage = {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in stock._SOURCE_LINEAGE_FIELDS
    }
    manifest = stock.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=session_rows,
        membership_records=memberships,
        contribution_records=tuple(contributions),
        source_lineage_sha256s=lineage,
        history_batch_security_count=64,
        scoring_sessions_per_callback=5,
        signal_seed_contributions_per_callback=20000,
    )
    return stock.load_preliminary_rating_input(
        manifest,
        session_rows,
        memberships,
        tuple(contributions),
    )


def _snapshot(ticker, session, *, total=Decimal("1"), offset=0):
    per_name = total / Decimal(5)
    return subject.EtfHoldingsSnapshot(
        ticker,
        session,
        tuple(
            sorted(
                (
                    subject.ConstituentWeight(
                        f"QC SID {(offset + index) % 20:02d}", per_name
                    )
                    for index in range(5)
                ),
                key=lambda row: row.qc_security_id,
            )
        ),
    )


def test_profile_freezes_unlevered_supported_sleeve_and_result_inventory():
    profile = subject.require_etf_baseline_profile(subject.PROFILE_ID)

    assert len(subject.CANDIDATE_ETFS) == 54
    assert subject.CANDIDATE_ETFS == tuple(sorted(subject.CANDIDATE_ETFS))
    assert profile["leverage"] is False
    assert profile["orders"] is False
    assert profile["trading"] is False
    assert profile["holdings_lag_sessions"] == 1
    assert profile["holdings_staleness_rule"] == (
        "exact_previous_authenticated_session"
    )
    assert profile["minimum_mapped_weight"] == "0.99"
    assert profile["entry_percentile"] == "90"
    assert profile["exit_percentile"] == "70"
    assert profile["maximum_holdings"] == 5
    assert profile["sector_cap_basis"] == "mapped_constituent_look_through"
    assert profile["overlap_cluster_method"] == (
        "transitive_connected_components"
    )
    assert profile["turnover_basis"] == "drift_adjusted_open_to_open_weights"
    assert profile["cost_bps_scenarios"] == [0, 5, 10, 20]
    assert all(
        token not in subject.CANDIDATE_ETFS
        for token in ("TQQQ", "SOXL", "SPXL", "SQQQ")
    )
    assert len(subject.expected_custom_summary_statistic_names()) == 8
    with pytest.raises(subject.AcceptedRiskEtfBaselineError, match="exact frozen"):
        subject.require_etf_baseline_profile("another-profile")


def test_holdings_guards_isolate_completeness_and_ninety_nine_percent_mapping():
    scores = {f"perm-security-{index:02d}": Decimal(index) for index in range(20)}
    mapping = {f"QC SID {index:02d}": f"perm-security-{index:02d}" for index in range(20)}
    sectors = {
        f"perm-security-{index:02d}": "sector-" + str(index % 4)
        for index in range(20)
    }

    with pytest.raises(subject.AcceptedRiskEtfBaselineError, match="completeness band"):
        subject._score_etf(
            _snapshot("AIQ", "2021-01-04", total=Decimal("0.94")),
            scores,
            mapping,
            sectors,
        )

    missing = dict(mapping)
    del missing["QC SID 00"]
    with pytest.raises(subject.AcceptedRiskEtfBaselineError, match="ninety-nine"):
        subject._score_etf(
            _snapshot("AIQ", "2021-01-04"),
            scores,
            missing,
            sectors,
        )

    mapped_weight = Decimal(
        "0.989999999999999999999999999999999999999999999999999999999999"
    )
    unmapped_weight = Decimal(
        "0.010000000000000000000000000000000000000000000000000000000001"
    )
    rounded_boundary = subject.EtfHoldingsSnapshot(
        "AIQ",
        "2021-01-04",
        (
            subject.ConstituentWeight("QC SID 00", mapped_weight),
            subject.ConstituentWeight("QC SID XX", unmapped_weight),
        ),
    )
    with pytest.raises(
        subject.EtfMappingCoverageError,
        match="ninety-nine",
    ):
        subject._score_etf(
            rounded_boundary,
            scores,
            {"QC SID 00": "perm-security-00"},
            sectors,
        )


def test_rank_hysteresis_hard_caps_and_overlap_cluster_are_behavioral():
    tickers = subject.CANDIDATE_ETFS[:20]
    scores = {ticker: Decimal(index) for index, ticker in enumerate(tickers)}
    disjoint = {
        ticker: {f"sid-{index}": Decimal(1)}
        for index, ticker in enumerate(tickers)
    }
    sectors = {
        ticker: {f"sector-{index}": Decimal(1)}
        for index, ticker in enumerate(tickers)
    }
    weights, percentiles = subject._target_weights(
        scores, disjoint, sectors, frozenset()
    )

    assert len(weights) <= 5
    assert set(weights).issubset(
        ticker for ticker in tickers if percentiles[ticker] >= Decimal(90)
    )
    assert set(weights.values()) <= {Decimal("0.20")}
    look_through = {
        ticker: {"same-sector": Decimal(1)}
        if ticker in tickers[-3:]
        else sectors[ticker]
        for ticker in tickers
    }
    sector_capped, _ = subject._target_weights(
        scores,
        disjoint,
        look_through,
        frozenset(tickers[-3:]),
    )
    assert len(set(tickers[-3:]) & set(sector_capped)) <= 2

    overlapping = dict(disjoint)
    overlapping[tickers[-3]] = {
        "common": Decimal("0.2"),
        "left": Decimal("0.8"),
    }
    overlapping[tickers[-2]] = {
        "common": Decimal("0.2"),
        "left": Decimal("0.4"),
        "right": Decimal("0.4"),
    }
    overlapping[tickers[-1]] = {
        "common": Decimal("0.2"),
        "right": Decimal("0.8"),
    }
    clustered, _ = subject._target_weights(
        scores,
        overlapping,
        sectors,
        frozenset(tickers[-3:]),
    )
    assert len(set(tickers[-3:]) & set(clustered)) == 1


def test_projection_has_one_compact_etf_entry_and_no_order_surface():
    source = projection._etf_main_source(
        activation_key="arv2/test/transport-manifest.json",
        activation_sha256="a" * 64,
        activation_bytes=123,
    )
    validated = projection._validate_source("main.py", source)
    paths = projection.project_source_paths_for_profile(subject.PROFILE_ID)

    assert validated.source_bytes == source
    assert b"AcceptedRiskEtfBaselineQcDriver" in source
    assert b"universe.etf" in source
    assert b"set_holdings" not in source
    assert b"market_order" not in source
    assert b"from __future__" not in source
    assert paths[-2:] == (
        "accepted_risk_etf_baseline_evaluator.py",
        "accepted_risk_etf_baseline_qc_runtime.py",
    )


def test_h1_snapshot_guard_and_snapshot_monotonicity_are_isolated():
    value = _input()
    mapping = {
        f"QC SID {index:02d}": f"perm-security-{index:02d}"
        for index in range(20)
    }
    runtime = subject.AcceptedRiskEtfBaselineRuntime(
        value,
        qc_sid_to_security_id=mapping,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
    )
    for ticker in subject.CANDIDATE_ETFS:
        runtime._liquidity[ticker] = [Decimal("6000000")] * 20
    runtime._available_snapshots["AIQ"] = _snapshot(
        "AIQ", "2020-12-31"
    )

    runtime._decision(subject.DECISION_START_SESSION)

    assert runtime._stale_holdings_snapshot_refusal_count == 1
    assert runtime._holdings_snapshot_refusal_count == len(
        subject.CANDIDATE_ETFS
    )
    assert runtime._score_history[subject.DECISION_START_SESSION] is None

    monotone = subject.AcceptedRiskEtfBaselineRuntime(
        value,
        qc_sid_to_security_id=mapping,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
    )
    monotone.accept_holdings_snapshot(_snapshot("AIQ", "2021-01-01"))
    with pytest.raises(subject.AcceptedRiskEtfBaselineError, match="advance strictly"):
        monotone.accept_holdings_snapshot(_snapshot("AIQ", "2020-12-31"))


def test_unchanged_target_still_charges_drift_rebalancing_turnover():
    value = _input()
    runtime = subject.AcceptedRiskEtfBaselineRuntime(
        value,
        qc_sid_to_security_id={},
        package_id="arv2-test-package",
        package_sha256="a" * 64,
    )
    runtime._previous_opens = {"AIQ": Decimal("100"), "SPY": Decimal("100")}
    runtime._active_weights = {"AIQ": Decimal("0.20")}
    runtime._pending_weights = {"AIQ": Decimal("0.20")}

    runtime._record_portfolio_return(
        "2021-01-05",
        {"AIQ": Decimal("200"), "SPY": Decimal("100")},
    )

    assert runtime._turnover_sum > 0
    assert runtime._invested_return_session_count == 1
    assert runtime._active_weights == {"AIQ": Decimal("0.20")}


def test_qc_driver_accepts_constituent_and_tradebar_envelopes():
    class FakeRuntime:
        def __init__(self):
            self.snapshots = []
            self.sessions = []

        def accept_holdings_snapshot(self, value):
            self.snapshots.append(value)

        def process_session(self, session, rows):
            self.sessions.append((session, rows))

    algorithm = SimpleNamespace(
        time=SimpleNamespace(date=lambda: date(2021, 1, 4))
    )
    symbols = {ticker: ticker for ticker in subject.CANDIDATE_ETFS}
    driver = qc_runtime.AcceptedRiskEtfBaselineQcDriver(
        algorithm,
        activation_manifest_key="arv2/test/transport-manifest.json",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=123,
        benchmark_symbol="SPY",
        etf_symbols=symbols,
    )
    fake = FakeRuntime()
    driver._runtime = fake
    constituent = SimpleNamespace(
        weight=Decimal("1"),
        symbol=SimpleNamespace(id="QC SID 00"),
    )
    assert driver.accept_constituents("AIQ", (constituent,)) == ()
    bar = SimpleNamespace(open=100, close=101, volume=1_000_000)
    driver.on_data(SimpleNamespace(bars={"SPY": bar, "AIQ": bar}))

    assert len(fake.snapshots) == 1
    assert fake.snapshots[0].observed_session == "2021-01-04"
    assert fake.sessions[0][0] == "2021-01-04"
    assert tuple(row.ticker for row in fake.sessions[0][1]) == ("AIQ", "SPY")


def test_etf_run_spec_and_look_accounting_are_frozen_before_outcomes():
    spec = adapter._run_spec(subject.PROFILE_ID)
    accounting = adapter._look_accounting(
        evaluation_profile_id=subject.PROFILE_ID
    )

    assert spec.ledger_entry_id == "R-060"
    assert spec.run_level_looks_before == 59
    assert spec.run_level_looks_after == 60
    assert spec.development_evaluations_before == 6
    assert spec.development_evaluations_after == 7
    assert spec.cell_count == 7
    assert spec.lifetime_alpha_cell_floor_after == 571
    assert accounting["run_level_looks_after"] == 59
    assert accounting["planned_run_level_looks_after_launch"] == 60
    assert accounting["aggregate_result_authenticated"] is False
    assert adapter._expected_result_names(subject.PROFILE_ID) == (
        qc_runtime.expected_custom_summary_statistic_names()
    )


@pytest.fixture(scope="module")
def completed_runtime():
    value = _input()
    mapping = {
        f"QC SID {index:02d}": f"perm-security-{index:02d}"
        for index in range(20)
    }
    runtime = subject.AcceptedRiskEtfBaselineRuntime(
        value,
        qc_sid_to_security_id=mapping,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
    )
    prices = {ticker: Decimal(100) for ticker in (*subject.CANDIDATE_ETFS, "SPY")}
    prior_session = None
    for session in value.session_axis:
        if session < subject.WARMUP_START_SESSION:
            continue
        if session > subject.OUTCOME_MATURITY_END_SESSION:
            break
        if prior_session is not None:
            for index, ticker in enumerate(subject.CANDIDATE_ETFS):
                runtime.accept_holdings_snapshot(
                    _snapshot(ticker, session, offset=index % 16)
                )
        bars = []
        for index, ticker in enumerate((*subject.CANDIDATE_ETFS, "SPY")):
            drift = Decimal(index % 9 - 4) / Decimal("100000")
            prices[ticker] = prices[ticker] * (Decimal(1) + drift)
            bars.append(
                subject.EtfDailyBar(
                    ticker,
                    session,
                    prices[ticker],
                    prices[ticker],
                    Decimal("1000000"),
                )
            )
        runtime.process_session(
            session, tuple(sorted(bars, key=lambda row: row.ticker))
        )
        prior_session = session
    runtime.complete()
    return value, runtime


@pytest.fixture(scope="module")
def all_cash_runtime():
    value = _input()
    runtime = subject.AcceptedRiskEtfBaselineRuntime(
        value,
        qc_sid_to_security_id={},
        package_id="arv2-test-package",
        package_sha256="a" * 64,
    )
    prices = {
        ticker: Decimal(100)
        for ticker in (*subject.CANDIDATE_ETFS, "SPY")
    }
    for session in value.session_axis:
        if session < subject.WARMUP_START_SESSION:
            continue
        if session > subject.OUTCOME_MATURITY_END_SESSION:
            break
        bars = []
        for ticker in (*subject.CANDIDATE_ETFS, "SPY"):
            bars.append(
                subject.EtfDailyBar(
                    ticker,
                    session,
                    prices[ticker],
                    prices[ticker],
                    Decimal("1000000"),
                )
            )
        runtime.process_session(
            session, tuple(sorted(bars, key=lambda row: row.ticker))
        )
    runtime.complete()
    return runtime


def test_all_cash_run_is_underfilled_and_ic_census_is_exhaustive(
    all_cash_runtime,
):
    summary = all_cash_runtime.aggregate_summary()

    assert summary["selected_decision_session_count"] == 0
    assert summary["invested_return_session_count"] == 0
    assert all(
        cell["valid_ic_date_count"] == 0
        and cell["invalid_ic_date_count"]
        == summary["decision_session_count"]
        for cell in summary["ic_cells"]
    )
    assert all(
        cell["status"] == "INCONCLUSIVE_UNDERFILLED"
        and cell["cumulative_return"] == "0"
        for cell in summary["portfolio_cells"]
    )


def test_end_to_end_runtime_emits_tangible_bounded_unlevered_evidence(
    completed_runtime,
):
    _value, runtime = completed_runtime
    summary = runtime.aggregate_summary()
    statistics = runtime.custom_summary_statistics()

    assert runtime.completed is True
    assert summary["economic_portfolio_evaluation"] is True
    assert summary["leverage"] is False
    assert summary["orders"] is False
    assert summary["trading"] is False
    assert summary["decision_session_count"] > 1_000
    assert summary["portfolio_return_session_count"] > 1_000
    assert summary["invested_return_session_count"] >= 50
    assert summary["selected_decision_session_count"] >= 50
    assert summary["mean_eligible_etf_count"] != "0"
    assert len(summary["ic_cells"]) == 3
    assert all(cell["valid_ic_date_count"] >= 50 for cell in summary["ic_cells"])
    assert all(
        cell["valid_ic_date_count"] + cell["invalid_ic_date_count"]
        == summary["decision_session_count"]
        for cell in summary["ic_cells"]
    )
    assert len(summary["portfolio_cells"]) == 4
    returns = {
        cell["cost_bps_per_side"]: Decimal(cell["cumulative_return"])
        for cell in summary["portfolio_cells"]
    }
    assert returns[0] >= returns[5] >= returns[10] >= returns[20]
    assert tuple(statistics) == subject.expected_custom_summary_statistic_names()
    assert all(len(value) <= 4096 for value in statistics.values())


def test_host_validator_accepts_exact_etf_summary_and_rejects_one_guard(
    completed_runtime, monkeypatch
):
    value, runtime = completed_runtime
    records = {
        name: adapter._strict_object(text.encode("ascii"), name)
        for name, text in runtime.custom_summary_statistics().items()
    }
    records["ARV2_RUNTIME_META"] = {
        "schema": "arv2-accepted-risk-etf-sector-qc-runtime-meta-v1",
        "status": "PRELIMINARY_ACCEPTED_RISK_UNLEVERED_ETF_BASELINE_COMPLETED",
        "profile_id": subject.PROFILE_ID,
        "profile_sha256": subject.require_etf_baseline_profile(
            subject.PROFILE_ID
        )["profile_sha256"],
        "package_id": "arv2-test-package",
        "package_sha256": "a" * 64,
        "activation_manifest_sha256": "b" * 64,
        "symbol_resolution_id": "arv2-test-resolution",
        "symbol_resolution_sha256": "c" * 64,
        "resolved_security_count": 20,
        "named_security_refusal_count": 0,
        "candidate_etf_count": 54,
        "result_transport": "aggregate_only_custom_summary_statistics",
        "host_object_store_export_required": False,
        "preliminary": True,
        "point_in_time": False,
        "formal": False,
        "control_residualized": False,
        "economic_portfolio": True,
        "etf": True,
        "leverage": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    plan = SimpleNamespace(
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        activation_manifest_sha256="b" * 64,
        evaluator_manifest_id=value.manifest_id,
        evaluator_manifest_sha256=value.manifest_sha256,
        package=SimpleNamespace(runtime_symbol_binding_count=20),
    )
    monkeypatch.setattr(
        adapter,
        "_authenticated_evaluator_manifest",
        lambda _plan: {
            "manifest_id": value.manifest_id,
            "manifest_sha256": value.manifest_sha256,
        },
    )
    adapter._validate_etf_aggregate_records(records, plan)

    records["ARV2_RUNTIME_META"]["leverage"] = True
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="runtime metadata changed",
    ):
        adapter._validate_etf_aggregate_records(records, plan)
    records["ARV2_RUNTIME_META"]["leverage"] = False

    meta = records["ARV2_ETF_2021_2025_META"]
    original_selected = meta["mean_selected_etf_count"]
    meta["mean_selected_etf_count"] = "6"
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="mean count",
    ):
        adapter._validate_etf_aggregate_records(records, plan)
    meta["mean_selected_etf_count"] = original_selected

    ic = records["ARV2_ETF_IC_H5"]
    ic["invalid_ic_date_count"] += 1
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="IC cell semantics",
    ):
        adapter._validate_etf_aggregate_records(records, plan)
    ic["invalid_ic_date_count"] -= 1

    portfolio = records["ARV2_ETF_PORTFOLIO_COST_10"]
    portfolio["status"] = "INCONCLUSIVE_UNDERFILLED"
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="portfolio cell semantics",
    ):
        adapter._validate_etf_aggregate_records(records, plan)
