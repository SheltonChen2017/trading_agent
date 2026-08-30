from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext, localcontext, setcontext
from pathlib import Path

import pytest

from data.exchange_calendar import resolve_nth_session_after, session_open_instant
import research.analyst_revisions_v2.stock_evaluation_contract as contract_module
from research.analyst_revisions_v2.stock_controls import (
    BINARY_COLUMNS,
    CONTINUOUS_COLUMNS,
    CONTROL_COLUMNS,
    PreopenControlEvidenceRow,
    StructuralFoldBoundary,
    StockControlError,
    apply_structural_stock_control_model,
    build_preopen_control_cross_section,
    fit_structural_stock_control_model,
)
from research.analyst_revisions_v2.stock_evaluation_contract import (
    StockEvaluationContractError,
    build_stock_report_plan,
    load_stock_evaluation_contract,
)
from research.analyst_revisions_v2.stock_signal import (
    RESIDUALIZATION_BLOCK,
    STRUCTURAL_ONLY_AUTHORITY,
    STRUCTURAL_STOCK_SCORE_SCHEMA,
    StockRawState,
    StockScoreRow,
    StructuralStockScoreCandidate,
)


ROOT = Path(__file__).resolve().parents[2]
SPEC = (
    ROOT
    / "research"
    / "analyst_revisions_v2"
    / "specs"
    / "arv2_stock_historical.structural.json"
)
QC_PLAN = SPEC.with_name("arv2_qc_first.draft.json")
SECTION_NAMES = (
    "control_definition",
    "global_benchmark_definition",
    "history_definition",
    "analysis_definition",
    "power_definition",
    "economic_definition",
    "report_definition",
    "disposition_definition",
    "downstream_definition",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _rehash(raw: dict[str, object]) -> None:
    raw["section_hashes"] = {
        name: hashlib.sha256(_canonical(raw[name])).hexdigest()
        for name in SECTION_NAMES
    }
    raw["spec_id"] = None
    raw["spec_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    raw["spec_hash"] = digest
    raw["spec_id"] = f"arv2-stock-historical-{digest[:16]}"


def _write_spec(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "arv2_stock_historical.structural.json"
    path.write_bytes(
        (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    path.with_name("arv2_qc_first.draft.json").write_bytes(QC_PLAN.read_bytes())
    path.with_name("arv2_round0.draft.json").write_bytes(
        QC_PLAN.with_name("arv2_round0.draft.json").read_bytes()
    )
    return path


def _load(path: Path = SPEC):
    return load_stock_evaluation_contract(path, qc_first_plan_path=QC_PLAN)


def _fold() -> StructuralFoldBoundary:
    return StructuralFoldBoundary.create(
        fold_id="fixture-fold-001",
        horizon_sessions=20,
        purge_sessions=20,
        embargo_sessions=20,
        train_start="2019-11-01",
        train_end_exclusive="2020-01-03",
        validation_start="2020-02-03",
        validation_end_exclusive="2020-03-02",
        test_start="2020-03-30",
        test_end_exclusive="2020-04-01",
    )


def test_repository_stock_evaluation_contract_is_complete_but_powerless() -> None:
    spec = _load()
    assert spec.spec_id == "arv2-stock-historical-dcc30556b6fb582b"
    assert spec.parent_plan_id == "arv2-qc-first-plan-36e455e72b8750fe"
    assert spec.sections["history_definition"]["horizons_sessions"] == (
        1,
        5,
        20,
        60,
    )
    assert spec.sections["analysis_definition"]["primary_gate_logic"].startswith(
        "intersection_union_conjunction"
    )
    assert spec.sections["global_benchmark_definition"]["primary_metric"] == (
        "paired_walk_forward_test_date_20_session_spearman_ic_on_identical_rows"
    )
    assert spec.sections["global_benchmark_definition"]["fold_scope"] == (
        "walk_forward_test_dates_only"
    )
    assert spec.sections["report_definition"]["secondary_can_rescue"] is False
    analysis = spec.sections["analysis_definition"]
    report_definition = spec.sections["report_definition"]
    assert analysis["primary_gate_ids"] == report_definition["PRIMARY"]
    assert analysis["role"] == "development_stop_go_not_prospective_confirmation"
    assert analysis["confirmatory_claim_permitted"] is False
    assert analysis["fama_macbeth"]["dependent_variable"].startswith(
        "gross_security_total_return_minus"
    )
    assert analysis["fama_macbeth"]["outcome_clock"].endswith(
        "horizon_session_open"
    )
    assert "centered_two_sided" in analysis["fama_macbeth"][
        "development_pass_rule"
    ]
    assert spec.sections["power_definition"]["required_fields"][-1] == (
        "underfill_disposition"
    )
    assert spec.sections["economic_definition"]["primary_cost_bps_per_side"] == 10
    assert spec.sections["economic_definition"][
        "economic_gate_execution_definition_sha256"
    ] is None
    assert spec.sections["economic_definition"]["leverage"] is False
    assert spec.sections["downstream_definition"]["topology_hierarchy"] == (
        "stock",
        "industry",
        "etf",
    )
    assert spec.sections["downstream_definition"][
        "holdings_lag_sensitivity_sessions"
    ] == (0, 1, 5)
    assert all(value is None for value in spec.external_bindings.values())
    assert spec.source_access_available is False
    assert spec.outcome_access_available is False
    assert spec.qc_action_available is False
    assert spec.result_disposition_available is False
    assert spec.deployment_available is False
    assert spec.orders_available is False
    report = build_stock_report_plan(spec)
    assert report.primary_output_ids == (
        "bullish_20_session_fama_macbeth",
        "net_20_session_sleeve",
        "firm_specific_vs_global_map_paired_20_session_ic",
    )
    assert report.outcome_rows_consumed == 0
    assert report.contains_results is False
    assert report.result_sha256 is None
    assert report.promotion_available is False
    assert "plot_data_drawdown_and_time_underwater" in report.required_report_ids
    with pytest.raises(TypeError):
        spec.sections["history_definition"]["primary_horizon_sessions"] = 5
    with pytest.raises(TypeError):
        contract_module.CONTROL_DEFINITION["outcomes_used"] = True


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda raw: raw.update(status="owner_frozen"), "status"),
        (lambda raw: raw.update(authority="full_qc_authority"), "authority"),
        (lambda raw: raw.update(parent_plan_hash="a" * 64), "parent_plan_hash"),
        (
            lambda raw: raw["capabilities"].update(qc_launch=True),
            "capabilities",
        ),
        (
            lambda raw: raw["external_bindings"].update(dataset_id="synthetic"),
            "external_bindings",
        ),
        (
            lambda raw: raw["global_benchmark_definition"].update(
                primary_metric="raw_scale_dependent_beta"
            ),
            "global_benchmark_definition",
        ),
        (
            lambda raw: raw["economic_definition"].update(
                primary_cost_bps_per_side=0
            ),
            "economic_definition",
        ),
        (
            lambda raw: raw["report_definition"].update(secondary_can_rescue=True),
            "report_definition",
        ),
        (
            lambda raw: raw["downstream_definition"].update(
                topology_hierarchy=["stock", "etf"]
            ),
            "downstream_definition",
        ),
    ],
)
def test_correctly_rehashed_contract_weakening_refuses(
    tmp_path: Path, mutate, match: str
) -> None:
    raw = copy.deepcopy(json.loads(SPEC.read_text(encoding="utf-8")))
    mutate(raw)
    _rehash(raw)
    path = _write_spec(tmp_path, raw)
    with pytest.raises(StockEvaluationContractError, match=match):
        load_stock_evaluation_contract(
            path,
            qc_first_plan_path=path.with_name("arv2_qc_first.draft.json"),
        )


def test_contract_rejects_duplicate_float_nonfinite_and_unstable_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = SPEC.read_text(encoding="utf-8")
    cases = {
        "duplicate": text.replace(
            '"authority":', '"authority": "forged",\n  "authority":', 1
        ),
        "float": text.replace('"primary_cost_bps_per_side": 10', '"primary_cost_bps_per_side": 10.0', 1),
        "nonfinite": text.replace('"primary_cost_bps_per_side": 10', '"primary_cost_bps_per_side": NaN', 1),
    }
    for name, payload in cases.items():
        path = tmp_path / f"{name}.json"
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(StockEvaluationContractError):
            load_stock_evaluation_contract(path, qc_first_plan_path=QC_PLAN)
    bom_path = tmp_path / "bom.json"
    bom_path.write_bytes(b"\xef\xbb\xbf" + SPEC.read_bytes())
    with pytest.raises(StockEvaluationContractError, match="BOM"):
        load_stock_evaluation_contract(bom_path, qc_first_plan_path=QC_PLAN)

    path = _write_spec(
        tmp_path, json.loads(SPEC.read_text(encoding="utf-8"))
    )
    original = Path.read_bytes
    resolved = path.resolve(strict=True)
    calls = 0

    def unstable(candidate: Path) -> bytes:
        nonlocal calls
        payload = original(candidate)
        if candidate.resolve(strict=False) == resolved:
            calls += 1
            if calls == 2:
                return payload + b" "
        return payload

    monkeypatch.setattr(Path, "read_bytes", unstable)
    with pytest.raises(StockEvaluationContractError, match="changed while being read"):
        load_stock_evaluation_contract(
            path,
            qc_first_plan_path=path.with_name("arv2_qc_first.draft.json"),
        )


def test_contract_recomputes_horizon_maturity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = contract_module.resolve_nth_session_after

    def wrong_for_twenty(anchor: str, count: int) -> str:
        if count == 20:
            return "2026-08-27"
        return original(anchor, count)

    monkeypatch.setattr(contract_module, "resolve_nth_session_after", wrong_for_twenty)
    with pytest.raises(StockEvaluationContractError, match="maturity"):
        _load()


def test_contract_refuses_noncanonical_encodings_and_whitespace(tmp_path: Path) -> None:
    payload = SPEC.read_bytes()
    cases = {
        "utf16": SPEC.read_text(encoding="utf-8").encode("utf-16"),
        "crlf": payload.replace(b"\n", b"\r\n"),
        "leading": b" " + payload,
        "trailing": payload + b" ",
    }
    for name, forged in cases.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(forged)
        match = "BOM" if name == "utf16" else "canonical"
        with pytest.raises(StockEvaluationContractError, match=match):
            load_stock_evaluation_contract(path, qc_first_plan_path=QC_PLAN)


def test_contract_loader_provenance_is_required_and_reauthenticated() -> None:
    contract = _load()
    forged_copy = copy.copy(contract)
    assert forged_copy is not contract
    with pytest.raises(StockEvaluationContractError, match="loader authority"):
        build_stock_report_plan(forged_copy)
    with pytest.raises(TypeError):
        dataclasses.replace(contract, spec_hash="a" * 64)

    object.__setattr__(contract, "spec_hash", "a" * 64)
    with pytest.raises(StockEvaluationContractError, match="changed after authentication"):
        build_stock_report_plan(contract)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _raw_continuous(row: int, column: int, *, rank_deficient: bool) -> Decimal:
    if rank_deficient:
        return Decimal(row + 1)
    modulus = 101 + 2 * column
    return Decimal(pow(row + 2, column + 1, modulus))


def _candidate_and_evidence(
    *,
    session: str,
    count: int = 72,
    zero_security: int | None = None,
    zero_score: Decimal = Decimal(0),
    constant_column: str | None = None,
    rank_deficient: bool = False,
    industry_override: str | None = None,
    industry_overrides: dict[int, str] | None = None,
    available_at: str | None = None,
    policy_sha256: str = "1" * 64,
) -> tuple[StructuralStockScoreCandidate, tuple[PreopenControlEvidenceRow, ...]]:
    available_at = available_at or f"{session}T13:00:00.000000Z"
    security_ids = tuple(f"sec-{index:03d}" for index in range(count))
    first_values = [
        _raw_continuous(index, 0, rank_deficient=rank_deficient)
        for index in range(count)
    ]
    median = _median(first_values)
    mad = _median([abs(value - median) for value in first_values])
    scores: list[StockScoreRow] = []
    evidence: list[PreopenControlEvidenceRow] = []
    for index, security_id in enumerate(security_ids):
        raw_state = (
            StockRawState.STRUCTURAL_ZERO
            if zero_security == index
            else StockRawState.ACTIVE
        )
        if raw_state is StockRawState.STRUCTURAL_ZERO:
            score = zero_score
        else:
            with localcontext() as context:
                context.prec = 50
                z_value = (first_values[index] - median) / (mad * Decimal("1.4826"))
                score = Decimal(2) + Decimal(3) * z_value
        scores.append(
            StockScoreRow(
                security_id=security_id,
                sector_id="sector-main",
                raw_state=raw_state,
                raw_score=Decimal(0) if raw_state is StockRawState.STRUCTURAL_ZERO else score,
                sector_z=Decimal(0) if raw_state is StockRawState.STRUCTURAL_ZERO else score,
                institution_effective_n=Decimal(0) if raw_state is StockRawState.STRUCTURAL_ZERO else Decimal(1),
                catalyst_effective_n=Decimal(0) if raw_state is StockRawState.STRUCTURAL_ZERO else Decimal(1),
                independent_effective_n=Decimal(0) if raw_state is StockRawState.STRUCTURAL_ZERO else Decimal(1),
                q_data=Decimal(1),
                reliability=Decimal(0) if raw_state is StockRawState.STRUCTURAL_ZERO else Decimal(1),
                pdf_reliable_score=score,
            )
        )
        values: list[tuple[str, object]] = []
        for column_index, name in enumerate(CONTINUOUS_COLUMNS):
            value = _raw_continuous(
                index,
                column_index,
                rank_deficient=rank_deficient,
            )
            if name == constant_column:
                value = Decimal(1)
            values.append((name, value))
        for binary_index, name in enumerate(BINARY_COLUMNS):
            bit = ((index + 1) >> binary_index) & 1
            values.append((name, bit if not rank_deficient else index % 2))
        industry = (
            (industry_overrides or {}).get(index)
            or industry_override
            or ("industry-a" if index < count // 2 else "industry-b")
        )
        evidence.append(
            PreopenControlEvidenceRow(
                security_id=security_id,
                industry_id=industry,
                decision_session=session,
                available_at=available_at,
                source_evidence_sha256=hashlib.sha256(
                    f"{session}:{security_id}".encode()
                ).hexdigest(),
                values=tuple(values),
            )
        )
    candidate = StructuralStockScoreCandidate(
        schema=STRUCTURAL_STOCK_SCORE_SCHEMA,
        authority=STRUCTURAL_ONLY_AUTHORITY,
        decision_session=session,
        decision_at=session_open_instant(session).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        policy_sha256=policy_sha256,
        upstream_identity_result_sha256="2" * 64,
        structural_evidence_sha256="3" * 64,
        universe_security_ids=security_ids,
        contributions=(),
        sector_normalizations=(),
        scores=tuple(scores),
        refusals=(),
        residualization_state=RESIDUALIZATION_BLOCK,
    )
    return candidate, tuple(evidence)


def test_train_only_control_fit_and_frozen_apply_are_structural() -> None:
    contract = _load()
    candidate, evidence = _candidate_and_evidence(
        session="2020-01-02", zero_security=71
    )
    training = build_preopen_control_cross_section(contract, candidate, evidence)
    fold = _fold()
    model = fit_structural_stock_control_model(contract, fold, (training,))
    assert model.reference_industry == "industry-a"
    assert model.active_training_rows == 71
    assert model.final_executable_available is False

    validation_candidate, validation_evidence = _candidate_and_evidence(
        session="2020-02-03", zero_security=71
    )
    validation = build_preopen_control_cross_section(
        contract, validation_candidate, validation_evidence
    )
    result = apply_structural_stock_control_model(
        contract, model, fold, "validation", (validation,)
    )
    zero_row = next(row for row in result.rows if row.security_id == "sec-071")
    assert zero_row.adjusted_score == 0
    active_values = [
        row.adjusted_score
        for row in result.rows
        if row.raw_state is StockRawState.ACTIVE
    ]
    assert all(Decimal("-4") <= value <= Decimal("4") for value in active_values)
    assert result.final_executable_available is False
    assert len(result.batch_sha256) == 64


def test_structural_zero_is_excluded_and_must_arrive_as_exact_zero() -> None:
    contract = _load()
    first_candidate, first_evidence = _candidate_and_evidence(
        session="2020-01-02", zero_security=71
    )
    first = build_preopen_control_cross_section(contract, first_candidate, first_evidence)
    first_model = fit_structural_stock_control_model(contract, _fold(), (first,))
    assert first_model.active_training_rows == 71

    forged_candidate, forged_evidence = _candidate_and_evidence(
        session="2020-01-02", zero_security=71, zero_score=Decimal("999999")
    )
    with pytest.raises(StockControlError, match="source scores"):
        build_preopen_control_cross_section(
            contract, forged_candidate, forged_evidence
        )


def test_control_evidence_refuses_outcome_columns_lateness_and_zero_mad() -> None:
    candidate, evidence = _candidate_and_evidence(session="2020-01-02")
    values = list(evidence[0].values)
    values.append(
        ("absolute_contribution_weighted_publication_to_entry_jump", Decimal(1))
    )
    with pytest.raises(StockControlError, match="outcome-only"):
        PreopenControlEvidenceRow(
            security_id="sec-forged",
            industry_id="industry-a",
            decision_session="2020-01-02",
            available_at="2020-01-02T13:00:00.000000Z",
            source_evidence_sha256="4" * 64,
            values=tuple(values),
        )

    contract = _load()
    late_candidate, late_evidence = _candidate_and_evidence(
        session="2020-01-02",
        available_at="2020-01-02T14:30:00.000000Z",
    )
    with pytest.raises(StockControlError, match="coverage is underfilled"):
        build_preopen_control_cross_section(contract, late_candidate, late_evidence)

    constant_candidate, constant_evidence = _candidate_and_evidence(
        session="2020-01-02", constant_column=CONTINUOUS_COLUMNS[3]
    )
    with pytest.raises(StockControlError, match="zero same-date MAD"):
        build_preopen_control_cross_section(
            contract, constant_candidate, constant_evidence
        )


def test_fit_refuses_row_floor_rank_deficiency_and_underfilled_application() -> None:
    contract = _load()
    small_candidate, small_evidence = _candidate_and_evidence(
        session="2020-01-02", count=40
    )
    small = build_preopen_control_cross_section(contract, small_candidate, small_evidence)
    with pytest.raises(StockControlError, match="too few active rows"):
        fit_structural_stock_control_model(contract, _fold(), (small,))

    rank_candidate, rank_evidence = _candidate_and_evidence(
        session="2020-01-02", rank_deficient=True
    )
    rank = build_preopen_control_cross_section(contract, rank_candidate, rank_evidence)
    with pytest.raises(StockControlError, match="rank deficient"):
        fit_structural_stock_control_model(contract, _fold(), (rank,))

    near_candidate, near_evidence = _candidate_and_evidence(session="2020-01-02")
    near_rows: list[PreopenControlEvidenceRow] = []
    for index, row in enumerate(near_evidence):
        values = list(row.values)
        first_value = values[0][1]
        values[1] = (
            CONTINUOUS_COLUMNS[1],
            first_value + (Decimal("1e-40") if index % 2 else Decimal(0)),
        )
        near_rows.append(dataclasses.replace(row, values=tuple(values)))
    near = build_preopen_control_cross_section(
        contract,
        near_candidate,
        tuple(near_rows),
    )
    with pytest.raises(StockControlError, match="rank deficient"):
        fit_structural_stock_control_model(contract, _fold(), (near,))

    train_candidate, train_evidence = _candidate_and_evidence(session="2020-01-02")
    train = build_preopen_control_cross_section(contract, train_candidate, train_evidence)
    fold = _fold()
    model = fit_structural_stock_control_model(contract, fold, (train,))
    unseen_candidate, unseen_evidence = _candidate_and_evidence(
        session="2020-02-03", industry_override="industry-c"
    )
    unseen = build_preopen_control_cross_section(
        contract, unseen_candidate, unseen_evidence
    )
    with pytest.raises(StockControlError, match="application date coverage"):
        apply_structural_stock_control_model(
            contract, model, fold, "validation", (unseen,)
        )


def test_fold_boundaries_bind_exact_per_horizon_nyse_gaps() -> None:
    for horizon in (1, 5, 20, 60):
        train_end = "2020-01-03"
        validation_start = resolve_nth_session_after(train_end, horizon)
        validation_end = resolve_nth_session_after(validation_start, 2)
        test_start = resolve_nth_session_after(validation_end, horizon)
        test_end = resolve_nth_session_after(test_start, 2)
        fold = StructuralFoldBoundary.create(
            fold_id=f"fixture-fold-{horizon}",
            horizon_sessions=horizon,
            purge_sessions=horizon,
            embargo_sessions=horizon,
            train_start="2019-11-01",
            train_end_exclusive=train_end,
            validation_start=validation_start,
            validation_end_exclusive=validation_end,
            test_start=test_start,
            test_end_exclusive=test_end,
        )
        assert fold.derived_sha256 == fold.structural_fold_sha256

    with pytest.raises(StockControlError, match="must equal the horizon"):
        StructuralFoldBoundary.create(
            fold_id="overlarge-gap-claim",
            horizon_sessions=20,
            purge_sessions=21,
            embargo_sessions=20,
            train_start="2019-11-01",
            train_end_exclusive="2020-01-03",
            validation_start="2020-02-04",
            validation_end_exclusive="2020-03-02",
            test_start="2020-03-30",
            test_end_exclusive="2020-04-01",
        )
    with pytest.raises(StockControlError, match="gap is not exact"):
        StructuralFoldBoundary.create(
            fold_id="adjacent-gap",
            horizon_sessions=20,
            purge_sessions=20,
            embargo_sessions=20,
            train_start="2019-11-01",
            train_end_exclusive="2020-01-03",
            validation_start="2020-01-03",
            validation_end_exclusive="2020-03-02",
            test_start="2020-03-30",
            test_end_exclusive="2020-04-01",
        )
    with pytest.raises(StockControlError, match="gap is not exact"):
        StructuralFoldBoundary.create(
            fold_id="off-by-one-gap",
            horizon_sessions=20,
            purge_sessions=20,
            embargo_sessions=20,
            train_start="2019-11-01",
            train_end_exclusive="2020-01-03",
            validation_start="2020-02-04",
            validation_end_exclusive="2020-03-02",
            test_start="2020-03-30",
            test_end_exclusive="2020-04-01",
        )


def test_preopen_controls_name_refusals_and_enforce_each_date_coverage() -> None:
    contract = _load()
    candidate, evidence = _candidate_and_evidence(session="2020-01-02")

    missing = build_preopen_control_cross_section(contract, candidate, evidence[:-1])
    assert missing.eligible_census_count == 72
    assert missing.accepted_control_count == 71
    assert len(missing.rows) == 71
    assert tuple(item.reason for item in missing.refusals) == (
        "missing_control_evidence",
    )

    late_last = dataclasses.replace(
        evidence[-1],
        available_at=candidate.decision_at,
    )
    late = build_preopen_control_cross_section(
        contract,
        candidate,
        (*evidence[:-1], late_last),
    )
    assert late.refusals[0].reason == "not_available_strictly_before_open"
    assert late.cross_section_sha256 != missing.cross_section_sha256

    with pytest.raises(StockControlError, match="coverage is underfilled"):
        build_preopen_control_cross_section(contract, candidate, evidence[:-4])
    incomplete_candidate = dataclasses.replace(
        candidate,
        scores=candidate.scores[:-1],
    )
    with pytest.raises(StockControlError, match="complete eligible universe"):
        build_preopen_control_cross_section(
            contract,
            incomplete_candidate,
            evidence[:-1],
        )


def test_control_transform_is_independent_of_ambient_decimal_precision() -> None:
    contract = _load()
    candidate, evidence = _candidate_and_evidence(session="2020-01-02")
    original_context = getcontext().copy()
    try:
        getcontext().prec = 10
        getcontext().rounding = ROUND_DOWN
        getcontext().Emin = -99
        getcontext().Emax = 99
        low_precision = build_preopen_control_cross_section(
            contract,
            candidate,
            evidence,
        )
        getcontext().prec = 80
        getcontext().rounding = ROUND_UP
        getcontext().Emin = -999999
        getcontext().Emax = 999999
        high_precision = build_preopen_control_cross_section(
            contract,
            candidate,
            evidence,
        )
    finally:
        setcontext(original_context)
    assert low_precision == high_precision
    assert low_precision.cross_section_sha256 == high_precision.cross_section_sha256


def _fit_fixture_model():
    contract = _load()
    candidate, evidence = _candidate_and_evidence(session="2020-01-02")
    training = build_preopen_control_cross_section(contract, candidate, evidence)
    fold = _fold()
    model = fit_structural_stock_control_model(contract, fold, (training,))
    return contract, fold, model


def test_model_fit_has_independent_golden_coefficients_and_rejects_tampering() -> None:
    contract, fold, model = _fit_fixture_model()
    coefficient_by_name = dict(zip(model.columns, model.coefficients, strict=True))
    assert abs(coefficient_by_name["intercept"] - Decimal(2)) < Decimal("1e-40")
    assert abs(coefficient_by_name[CONTINUOUS_COLUMNS[0]] - Decimal(3)) < Decimal(
        "1e-40"
    )
    for name, value in coefficient_by_name.items():
        if name not in ("intercept", CONTINUOUS_COLUMNS[0]):
            assert abs(value) < Decimal("1e-40")

    validation_candidate, validation_evidence = _candidate_and_evidence(
        session="2020-02-03"
    )
    validation = build_preopen_control_cross_section(
        contract,
        validation_candidate,
        validation_evidence,
    )
    original_coefficients = model.coefficients
    object.__setattr__(
        model,
        "coefficients",
        (original_coefficients[0] + Decimal(1), *original_coefficients[1:]),
    )
    with pytest.raises(StockControlError, match="identity"):
        apply_structural_stock_control_model(
            contract,
            model,
            fold,
            "validation",
            (validation,),
        )


def test_held_out_application_subtracts_frozen_training_prediction_without_refit() -> None:
    contract, fold, model = _fit_fixture_model()
    candidate, evidence = _candidate_and_evidence(session="2020-02-03")
    model_identity = (model.model_hash, model.coefficients)
    unperturbed = build_preopen_control_cross_section(contract, candidate, evidence)
    unperturbed_result = apply_structural_stock_control_model(
        contract,
        model,
        fold,
        "validation",
        (unperturbed,),
    )
    assert all(
        abs(item.adjusted_score) < Decimal("1e-40")
        for item in unperturbed_result.rows
    )
    scores = list(candidate.scores)
    target = scores[10]
    with localcontext() as context:
        context.prec = 50
        perturbed_score = target.pdf_reliable_score + Decimal(1)
    scores[10] = dataclasses.replace(
        target,
        pdf_reliable_score=perturbed_score,
    )
    perturbed_candidate = dataclasses.replace(candidate, scores=tuple(scores))
    validation = build_preopen_control_cross_section(
        contract,
        perturbed_candidate,
        evidence,
    )
    result = apply_structural_stock_control_model(
        contract,
        model,
        fold,
        "validation",
        (validation,),
    )
    target_result = next(item for item in result.rows if item.security_id == "sec-010")
    control_result = next(item for item in result.rows if item.security_id == "sec-011")
    assert abs(target_result.adjusted_score - Decimal(1)) < Decimal("1e-40")
    assert abs(control_result.adjusted_score) < Decimal("1e-40")
    assert (model.model_hash, model.coefficients) == model_identity


def test_candidate_policy_fold_and_partition_lineage_are_fail_closed() -> None:
    contract, fold, model = _fit_fixture_model()
    different_policy_candidate, evidence = _candidate_and_evidence(
        session="2020-02-03",
        policy_sha256="2" * 64,
    )
    different_policy = build_preopen_control_cross_section(
        contract,
        different_policy_candidate,
        evidence,
    )
    with pytest.raises(StockControlError, match="candidate policy"):
        apply_structural_stock_control_model(
            contract,
            model,
            fold,
            "validation",
            (different_policy,),
        )
    with pytest.raises(StockControlError, match="validation or test"):
        apply_structural_stock_control_model(
            contract,
            model,
            fold,
            "train",
            (different_policy,),
        )

    object.__setattr__(fold, "validation_start", "2020-02-04")
    with pytest.raises(StockControlError, match="gap is not exact"):
        apply_structural_stock_control_model(
            contract,
            model,
            fold,
            "validation",
            (different_policy,),
        )


def test_unseen_industry_is_named_per_row_and_structural_zero_stays_zero() -> None:
    contract, fold, model = _fit_fixture_model()
    candidate, evidence = _candidate_and_evidence(
        session="2020-02-03",
        industry_overrides={0: "industry-c"},
    )
    cross_section = build_preopen_control_cross_section(contract, candidate, evidence)
    result = apply_structural_stock_control_model(
        contract,
        model,
        fold,
        "validation",
        (cross_section,),
    )
    assert result.eligible_input_rows == 72
    assert result.adjusted_row_count == 71
    assert tuple((item.security_id, item.reason) for item in result.refusals) == (
        ("sec-000", "unseen_training_industry"),
    )

    zero_candidate, zero_evidence = _candidate_and_evidence(
        session="2020-02-03",
        zero_security=0,
        industry_overrides={0: "industry-c"},
    )
    zero_cross_section = build_preopen_control_cross_section(
        contract,
        zero_candidate,
        zero_evidence,
    )
    zero_result = apply_structural_stock_control_model(
        contract,
        model,
        fold,
        "validation",
        (zero_cross_section,),
    )
    first = next(item for item in zero_result.rows if item.security_id == "sec-000")
    assert first.adjusted_score == 0
    assert not zero_result.refusals


def test_application_coverage_is_enforced_after_unseen_industry_refusals() -> None:
    contract, fold, model = _fit_fixture_model()
    candidate, evidence = _candidate_and_evidence(
        session="2020-02-03",
        industry_overrides={0: "industry-c"},
    )
    threshold_cross_section = build_preopen_control_cross_section(
        contract,
        candidate,
        evidence[:-3],
    )
    assert threshold_cross_section.accepted_control_count == 69
    with pytest.raises(StockControlError, match="application date coverage"):
        apply_structural_stock_control_model(
            contract,
            model,
            fold,
            "validation",
            (threshold_cross_section,),
        )


def test_adjusted_batch_rejects_forged_interval_and_out_of_range_rows() -> None:
    contract, fold, model = _fit_fixture_model()
    candidate, evidence = _candidate_and_evidence(session="2020-02-03")
    cross_section = build_preopen_control_cross_section(contract, candidate, evidence)
    result = apply_structural_stock_control_model(
        contract,
        model,
        fold,
        "validation",
        (cross_section,),
    )
    with pytest.raises(StockControlError, match="escaped its partition"):
        dataclasses.replace(
            result,
            partition_interval=("2020-03-30", "2020-04-01"),
        )
    forged_first = dataclasses.replace(
        result.rows[0],
        decision_session="2020-03-30",
    )
    forged_rows = (forged_first, *result.rows[1:])
    with pytest.raises(StockControlError):
        dataclasses.replace(result, rows=forged_rows)
