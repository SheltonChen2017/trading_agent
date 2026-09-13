from __future__ import annotations

import dataclasses
import gc
import hashlib
import inspect
import json
import os
import sys
import types
import weakref
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.power_calibration_protocol import (
    ProvisionalPowerDisposition,
)
from research.analyst_revisions_v2.production_input_pipeline import SignalArm
from research.analyst_revisions_v2.production_scoring import (
    FinalDecisionInput,
    FoldPartition,
    ScoreState,
    formal_horizon_fold_boundary,
)
from research.analyst_revisions_v2_qc import formal_input_bundle
from research.analyst_revisions_v2_qc import formal_submission_adapter as formal_submit
from research.analyst_revisions_v2_qc import power_calibration_bridge as bridge
from research.analyst_revisions_v2_qc import power_calibration_runtime as runtime
from research.analyst_revisions_v2_qc import power_calibration_submission_adapter as submit
from research.analyst_revisions_v2_qc import power_calibration_worker as worker
from research.analyst_revisions_v2_qc.formal_run_protocol import PowerFloorBinding


def _closure_cell(value: object):
    def capture():
        return value

    assert capture.__closure__ is not None
    return capture.__closure__[0]


def _with_closure_value(function, name: str, value: object):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    rebound = types.FunctionType(
        function.__code__,
        function.__globals__,
        function.__name__,
        function.__defaults__,
        tuple(
            _closure_cell(value) if freevar == name else cells[freevar]
            for freevar in function.__code__.co_freevars
        ),
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _with_global_values(function, **replacements):
    namespace = dict(function.__globals__)
    namespace.update(replacements)
    rebound = types.FunctionType(
        function.__code__,
        namespace,
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _closure_function(function, name: str):
    """Find one named function reachable through ordinary closure reflection."""

    pending = [function]
    observed: set[int] = set()
    while pending:
        candidate = pending.pop()
        if id(candidate) in observed:
            continue
        observed.add(id(candidate))
        if candidate.__closure__ is None:
            continue
        for freevar, cell in zip(
            candidate.__code__.co_freevars,
            candidate.__closure__,
            strict=True,
        ):
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if freevar == name and type(value) is types.FunctionType:
                return value
            if type(value) is types.FunctionType:
                pending.append(value)
    raise AssertionError(f"closure function {name!r} was not found")


def _direct_closure_value(function, name: str):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    return cells[name].cell_contents


def _install_offline_power_action_binding_guards(monkeypatch) -> None:
    """Install a test-local return authority invisible to production requires."""

    offline_guard = lambda _operation: None
    offline_pid = os.getpid()
    offline_records = {}

    def public_registry(kind):
        return (
            submit._LAUNCH_AUTHORITIES
            if kind == "launch"
            else submit._TERMINAL_AUTHORITIES
        )

    def store(kind, value, *lineage):
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda _ref, category=kind, key=identity: offline_records.pop(
                (category, key), None
            ),
        )
        entry = (reference, *lineage, offline_pid)
        offline_records[(kind, identity)] = entry
        public_registry(kind)[identity] = entry

    def current(kind, value):
        identity = id(value)
        entry = offline_records.get((kind, identity))
        if (
            os.getpid() != offline_pid
            or entry is None
            or entry[0]() is not value
            or public_registry(kind).get(identity) is not entry
        ):
            offline_records.pop((kind, identity), None)
            public_registry(kind).pop(identity, None)
            return None
        return entry

    def register_launch(
        value, *, plan, permit, review_claim, owner_signature,
    ):
        store(
            "launch",
            value,
            plan,
            permit,
            review_claim,
            owner_signature,
            canonical_json_bytes(submit._launch_record(value)),
        )

    def register_terminal(
        value, *, plan, launch, permit, review_claim, owner_signature,
    ):
        store(
            "terminal",
            value,
            plan,
            launch,
            permit,
            review_claim,
            owner_signature,
            canonical_json_bytes(submit._terminal_record(value)),
        )

    production_execute = submit.execute_power_calibration_submission_once
    production_inspect = submit.inspect_power_calibration_terminal_status
    production_require_launch = submit.require_power_calibration_launch_receipt
    production_require_terminal = submit.require_power_calibration_terminal_status

    require_launch = _with_closure_value(
        production_require_launch,
        "current_launch",
        lambda value: current("launch", value),
    )
    require_launch = _with_closure_value(
        require_launch, "binding_guard", offline_guard
    )
    require_terminal_impl = _direct_closure_value(
        production_require_terminal, "require_terminal_impl"
    )
    require_terminal_impl = types.FunctionType(
        require_terminal_impl.__code__,
        {
            **require_terminal_impl.__globals__,
            "require_power_calibration_launch_receipt": require_launch,
        },
        require_terminal_impl.__name__,
        require_terminal_impl.__defaults__,
        require_terminal_impl.__closure__,
    )
    require_terminal_impl.__kwdefaults__ = (
        _direct_closure_value(
            production_require_terminal, "require_terminal_impl"
        ).__kwdefaults__
    )
    require_terminal = _with_closure_value(
        production_require_terminal,
        "require_terminal_impl",
        require_terminal_impl,
    )
    require_terminal = _with_closure_value(
        require_terminal,
        "current_terminal",
        lambda value: current("terminal", value),
    )
    require_terminal = _with_closure_value(
        require_terminal, "binding_guard", offline_guard
    )

    execute = _with_closure_value(
        production_execute, "register_launch", register_launch
    )
    execute = _with_closure_value(execute, "binding_guard", offline_guard)
    inspect_action = _with_closure_value(
        production_inspect, "register_terminal", register_terminal
    )
    inspect_action = _with_closure_value(
        inspect_action, "binding_guard", offline_guard
    )

    monkeypatch.setattr(
        submit, "execute_power_calibration_submission_once", execute
    )
    monkeypatch.setattr(
        submit, "inspect_power_calibration_terminal_status", inspect_action
    )
    monkeypatch.setattr(
        submit, "require_power_calibration_launch_receipt", require_launch
    )
    monkeypatch.setattr(
        submit, "require_power_calibration_terminal_status", require_terminal
    )

    monkeypatch.setattr(
        submit,
        "persist_power_calibration_output",
        _with_closure_value(
            submit.persist_power_calibration_output,
            "binding_guard",
            offline_guard,
        ),
    )


@pytest.mark.parametrize(
    "name",
    (
        "_transport_capability_minter",
        "_execute_power_calibration_submission_once_impl",
        "_inspect_power_calibration_terminal_status_impl",
        "_persist_power_calibration_output_impl",
    ),
)
def test_power_transport_authority_primitives_are_not_module_addressable(name):
    assert not hasattr(submit, name)


def test_power_transport_minter_cannot_escalate_to_formal_result_scope():
    function = submit.execute_power_calibration_submission_once
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    with pytest.raises(
        formal_submit.FormalQcSubmissionError,
        match="caller changed",
    ):
        cells["transport_capability_minter"].cell_contents(
            transport=object(),
            scope="result_read",
            binding_record={"schema": "forbidden"},
            call_budget={"backtests/read": 1},
        )


def _hashed_session(
    *,
    disposition: str,
    decisions: list[dict[str, object]],
    component_count: int,
) -> dict[str, object]:
    seed: dict[str, object] = {
        "schema": bridge.INPUT_ROW_SCHEMA,
        "decision_session": "2018-01-31",
        "session_position": 0,
        "horizon_sessions": 20,
        "exit_session": "2018-03-01",
        "benchmark_security_id": "SPY SID",
        "preoutcome_disposition": disposition,
        "preoutcome_refusal_sha256s": (
            ["f" * 64] if disposition == "refused" else []
        ),
        "connected_component_count": component_count,
        "security_terminal_count": len(decisions),
        "minute_requirement_count": 0,
        "decisions": decisions,
    }
    return {
        **seed,
        "input_session_sha256": hashlib.sha256(
            worker._canonical(seed)
        ).hexdigest(),
    }


def _decision(
    index: int,
    *,
    terminal: dict[str, object] | None = None,
    structural_zero: bool = True,
) -> dict[str, object]:
    return {
        "security_id": f"security-{index:03d}",
        "decision_lineage_sha256": f"{index % 16:x}" * 64,
        "industry_id": "industry-a",
        "common_event_component_id": f"component-{index:03d}",
        "structural_zero": structural_zero,
        "firm_specific_score": "0" if structural_zero else "0.5",
        "continuous_controls": ["0"] * 19,
        "binary_controls": [0] * 6,
        "contributions": [],
        "terminal_disposition": terminal,
    }


class _NoMarketReads(dict):
    def get(self, *_args, **_kwargs):  # pragma: no cover - failure path only
        raise AssertionError("terminal refusal touched a numeric market value")


def test_exact_axis_and_output_dataclass_field_inventory() -> None:
    axis = bridge.calibration_axis()
    assert len(axis) == 483
    assert axis[0] == "2018-01-31"
    assert axis[-1] == "2019-12-31"
    assert hashlib.sha256(
        json.dumps(
            axis,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest() == bridge.CALIBRATION_AXIS_SHA256

    output_fields = tuple(
        item.name
        for item in dataclasses.fields(bridge.AcceptedRiskPowerCalibrationOutput)
    )
    assert output_fields == (
        "output_id", "output_sha256", "input_id", "input_sha256",
        "protocol_id", "protocol_sha256", "calibration_input",
        "terminal_receipt", "records", "manifest_path", "shard_paths",
        "file_fingerprints", "valid_date_count", "missing_date_count",
        "refused_date_count", "component_instance_count", "complete_axis",
        "qc_result_statistics_read", "formal_outcome_evaluation",
    )
    assert len(output_fields) == len(set(output_fields))


def test_formal_power_census_uses_exact_h20_fold_axes() -> None:
    session_count = 0
    for year in range(2020, 2026):
        boundary = formal_horizon_fold_boundary(f"arv2-wf-test-{year}", 20)
        sessions = tuple(
            item
            for item in bridge.trading_sessions(
                bridge.date.fromisoformat(boundary[6]),
                bridge.date.fromisoformat(boundary[7]),
            )
            if item.isoformat() < boundary[7]
        )
        session_count += len(sessions)
    assert session_count == bridge.TEST_SESSION_CAPACITY == 1388
    assert "_build_authenticated_formal_test_power_census_impl" not in vars(bridge)
    assert "_power_authority_register_census" not in vars(bridge)


def _fake_power_coverage(
    *, fold_id: str, source_view_id: str,
    counts: tuple[int, int, int, int],
) -> object:
    candidate, capable, both_constant, score_refused = counts
    return types.SimpleNamespace(
        source_view_id=source_view_id,
        fold_ids=(fold_id,),
        ledgers=(types.SimpleNamespace(
            ledger_id="score_capable_dates",
            numerator=capable,
            denominator=candidate,
        ),),
        date_diagnostic_counts=(
            ("both_arms_constant_dates", both_constant),
            ("score_refused_candidate_dates", score_refused),
            ("preoutcome_candidate_dates", candidate),
        ),
    )


def _fake_power_fold_commitment(
    *, fold_id: str,
    current_counts: tuple[int, int, int, int],
    censored_counts: tuple[int, int, int, int],
) -> object:
    return types.SimpleNamespace(
        fold_id=fold_id,
        global_comparator_coverages=(
            _fake_power_coverage(
                fold_id=fold_id,
                source_view_id=formal_input_bundle.CURRENT_VIEW_LABEL,
                counts=current_counts,
            ),
            _fake_power_coverage(
                fold_id=fold_id,
                source_view_id=formal_input_bundle.CENSORED_VIEW_LABEL,
                counts=censored_counts,
            ),
        ),
    )


def _fake_power_view_counts(
    geometries: tuple[tuple[object, ...], ...],
    *, accepted_index: int, refused_index: int,
) -> tuple[int, int, int, int]:
    candidate = capable = both_constant = score_refused = 0
    for geometry in geometries:
        accepted = geometry[accepted_index]
        refused = geometry[refused_index]
        if not accepted and not refused:
            continue
        candidate += 1
        if refused:
            score_refused += 1
            continue
        firm_scores = {item.firm_specific_score for item in accepted}
        global_scores = {item.global_score for item in accepted}
        if len(firm_scores) == 1 and len(global_scores) == 1:
            both_constant += 1
        else:
            capable += 1
    return candidate, capable, both_constant, score_refused


def _mock_formal_power_census(
    monkeypatch, *, mode: str, coverage_capable_delta: int = 0,
):
    from research.analyst_revisions_v2_qc import formal_streaming_input as stream

    class Artifact:
        pass

    def accepted_rows(
        *, constant: bool = False, component_prefix: str = "component"
    ):
        return tuple(
            types.SimpleNamespace(
                security_id=f"security-{index:02d}",
                common_event_component_id=f"{component_prefix}-{index:02d}",
                firm_specific_score=(Decimal(0) if constant else Decimal(index)),
                global_score=(Decimal(0) if constant else Decimal(-index)),
            )
            for index in range(20)
        )

    def refused_rows():
        return tuple(
            types.SimpleNamespace(security_id=f"security-{index:02d}")
            for index in range(20)
        )

    builder = object()
    state = types.SimpleNamespace(
        next_fold_index=0, active_fold=False, finalized=False
    )
    artifact = Artifact()
    artifact.artifact_id = f"formal-scoring-{mode}"
    artifact.artifact_sha256 = hashlib.sha256(mode.encode("ascii")).hexdigest()
    artifact.fold_commitments = ()
    fold_commitments: list[object] = []
    fold_index = 0
    monkeypatch.setattr(
        stream, "require_streamed_production_scoring_builder", lambda value: value
    )
    monkeypatch.setattr(stream, "_state", lambda value: state)

    def iter_fold(value):
        nonlocal fold_index
        assert value is builder
        fold_id = f"arv2-wf-test-{2020 + fold_index}"
        fold_index += 1
        h20 = formal_horizon_fold_boundary(fold_id, 20)
        sessions = tuple(
            item
            for item in bridge.trading_sessions(
                bridge.date.fromisoformat(h20[6]),
                bridge.date.fromisoformat(h20[7]),
            )
            if item.isoformat() < h20[7]
        )
        if mode == "all_empty":
            geometries = ((sessions[0], (), (), (), ()),)
        elif mode == "all_refused":
            refusals = refused_rows()
            geometries = ((sessions[0], (), refusals, (), refusals),)
        elif mode == "current_valid_censored_refused":
            accepted = accepted_rows()
            refusals = refused_rows()
            geometries = ((sessions[0], accepted, (), (), refusals),)
        elif mode == "current_refused_censored_valid":
            accepted = accepted_rows()
            refusals = refused_rows()
            geometries = ((sessions[0], (), refusals, accepted, ()),)
        elif mode == "current_valid_censored_constant":
            geometries = ((
                sessions[0], accepted_rows(), (),
                accepted_rows(constant=True), (),
            ),)
        elif mode == "current_constant_censored_valid":
            geometries = ((
                sessions[0], accepted_rows(constant=True), (),
                accepted_rows(), (),
            ),)
        elif mode == "component_mismatch":
            geometries = ((
                sessions[0], accepted_rows(), (),
                accepted_rows(component_prefix="censored-component"), (),
            ),)
        elif mode == "mixed_admissible":
            accepted = accepted_rows()
            refusals = refused_rows()
            geometries = tuple(
                (session, accepted, (), accepted, ())
                for session in sessions[:10]
            ) + ((sessions[10], (), refusals, (), refusals),)
        else:  # pragma: no cover - test helper is closed over exact modes.
            raise AssertionError(mode)
        fold_commitments.append(_fake_power_fold_commitment(
            fold_id=fold_id,
            current_counts=_fake_power_view_counts(
                geometries, accepted_index=1, refused_index=2
            ),
            censored_counts=_fake_power_view_counts(
                geometries, accepted_index=3, refused_index=4
            ),
        ))
        return iter(tuple(
            types.SimpleNamespace(
                fold_id=fold_id,
                decision_session=session,
                current_accepted=current_accepted,
                current_refused=current_refused,
                censored_accepted=censored_accepted,
                censored_refused=censored_refused,
            )
            for (
                session, current_accepted, current_refused,
                censored_accepted, censored_refused,
            ) in geometries
        ))

    monkeypatch.setattr(stream, "iter_streamed_production_scoring_fold", iter_fold)
    def finish(value):
        assert value is builder
        if coverage_capable_delta:
            coverage = fold_commitments[0].global_comparator_coverages[0]
            score_capable = coverage.ledgers[0]
            coverage.ledgers = (types.SimpleNamespace(
                ledger_id=score_capable.ledger_id,
                numerator=score_capable.numerator + coverage_capable_delta,
                denominator=score_capable.denominator,
            ),)
        artifact.fold_commitments = tuple(fold_commitments)
        return artifact

    monkeypatch.setattr(stream, "finish_streamed_production_scoring", finish)
    monkeypatch.setattr(
        stream, "require_streamed_production_scoring_artifact", lambda value: value
    )
    return bridge.build_authenticated_formal_test_power_census(builder)


@pytest.mark.parametrize(
    "mode",
    (
        "current_valid_censored_refused",
        "current_refused_censored_valid",
        "current_valid_censored_constant",
        "current_constant_censored_valid",
    ),
)
def test_formal_power_census_requires_both_views_score_capable(
    monkeypatch, mode: str,
) -> None:
    census = _mock_formal_power_census(monkeypatch, mode=mode)
    assert census.h20_test_session_capacity == 1388
    assert census.preoutcome_candidate_date_count == 6
    assert census.valid_h20_test_session_count == 0
    assert census.refused_h20_test_session_count == 6
    assert census.missing_h20_test_session_count == 1382
    assert census.connected_component_instance_count == 0


def test_formal_power_census_counts_only_exact_common_component_topologies(
    monkeypatch,
) -> None:
    census = _mock_formal_power_census(monkeypatch, mode="component_mismatch")
    assert census.valid_h20_test_session_count == 6
    assert census.connected_component_instance_count == 0


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("census_id", "arv2-formal-test-power-census-forged"),
        ("census_sha256", "f" * 64),
    ),
)
def test_formal_power_census_rejects_rewritten_identity(
    monkeypatch, field: str, replacement: str,
) -> None:
    census = _mock_formal_power_census(monkeypatch, mode="mixed_admissible")
    object.__setattr__(census, field, replacement)
    with pytest.raises(bridge.AcceptedRiskPowerCalibrationError):
        bridge.require_authenticated_formal_test_power_census(census)


def test_formal_power_census_rejects_authenticated_coverage_count_mismatch(
    monkeypatch,
) -> None:
    with pytest.raises(
        bridge.AcceptedRiskPowerCalibrationError,
        match="authenticated coverage ledger",
    ):
        _mock_formal_power_census(
            monkeypatch, mode="mixed_admissible", coverage_capable_delta=-1
        )


@pytest.mark.parametrize(
    ("mode", "candidate_dates", "refused_dates"),
    (("all_empty", 0, 0), ("all_refused", 6, 6)),
)
def test_empty_or_all_refused_formal_census_cannot_open_power_floor(
    monkeypatch, mode: str, candidate_dates: int, refused_dates: int,
) -> None:
    census = _mock_formal_power_census(monkeypatch, mode=mode)
    assert census.preoutcome_candidate_date_count == candidate_dates
    assert census.valid_h20_test_session_count == 0
    assert census.refused_h20_test_session_count == refused_dates
    assert census.connected_component_instance_count == 0
    receipt, _successor, _old_census, _scoring = _unregistered_power_parents()
    monkeypatch.setattr(
        bridge, "require_accepted_risk_power_calibration_receipt",
        lambda value: value if value is receipt else (_ for _ in ()).throw(
            bridge.AcceptedRiskPowerCalibrationError("receipt substitute")
        ),
    )
    successor = bridge.build_accepted_risk_stock_power_successor(receipt)
    monkeypatch.setattr(
        bridge, "require_authenticated_formal_test_power_census",
        lambda value: value if value is census else (_ for _ in ()).throw(
            bridge.AcceptedRiskPowerCalibrationError("census substitute")
        ),
    )
    with pytest.raises(
        bridge.AcceptedRiskPowerCalibrationError, match="does not meet"
    ):
        bridge.build_authenticated_power_floor_binding(
            receipt=receipt, successor=successor, formal_census=census
        )


def test_only_mixed_common_valid_dates_and_components_open_power_floor(
    monkeypatch,
) -> None:
    census = _mock_formal_power_census(monkeypatch, mode="mixed_admissible")
    assert census.preoutcome_candidate_date_count == 66
    assert census.valid_h20_test_session_count == 60
    assert census.refused_h20_test_session_count == 6
    assert census.missing_h20_test_session_count == 1322
    assert census.connected_component_instance_count == 1200
    receipt, _successor, _old_census, _scoring = _unregistered_power_parents()
    monkeypatch.setattr(
        bridge, "require_accepted_risk_power_calibration_receipt",
        lambda value: value,
    )
    successor = bridge.build_accepted_risk_stock_power_successor(receipt)
    monkeypatch.setattr(
        bridge, "require_authenticated_formal_test_power_census",
        lambda value: value,
    )
    floor = bridge.build_authenticated_power_floor_binding(
        receipt=receipt, successor=successor, formal_census=census
    )
    assert floor.observed_valid_dates == 60
    assert floor.observed_connected_components == 1200
    assert floor.h20_test_session_capacity == 1388
    assert floor.preoutcome_candidate_date_count == 66
    assert floor.valid_h20_test_session_count == 60
    assert floor.refused_h20_test_session_count == 6
    assert floor.missing_h20_test_session_count == 1322
    assert floor.connected_component_instance_count == 1200


def test_formal_power_census_consumes_but_excludes_h1_only_sessions(
    monkeypatch,
) -> None:
    from research.analyst_revisions_v2_qc import formal_streaming_input as stream

    class Artifact:
        pass

    builder = object()
    state = types.SimpleNamespace(
        next_fold_index=0, active_fold=False, finalized=False
    )
    artifact = Artifact()
    artifact.artifact_id = "formal-scoring-artifact"
    artifact.artifact_sha256 = "a" * 64
    artifact.fold_commitments = ()
    fold_commitments: list[object] = []
    fold_index = 0

    monkeypatch.setattr(
        stream, "require_streamed_production_scoring_builder", lambda value: value
    )
    monkeypatch.setattr(stream, "_state", lambda value: state)

    def iter_fold(value):
        nonlocal fold_index
        assert value is builder
        year = 2020 + fold_index
        fold_index += 1
        fold_id = f"arv2-wf-test-{year}"
        h1 = formal_horizon_fold_boundary(fold_id, 1)
        h20 = formal_horizon_fold_boundary(fold_id, 20)
        early = types.SimpleNamespace(
            fold_id=fold_id,
            decision_session=bridge.date.fromisoformat(h1[6]),
            current_accepted=tuple(
                types.SimpleNamespace(common_event_component_id=f"early-{index}")
                for index in range(10)
            ),
            current_refused=(),
            censored_accepted=(),
            censored_refused=(),
        )
        included_rows = tuple(
            types.SimpleNamespace(
                security_id=f"included-{index:02d}",
                common_event_component_id=f"component-{index:02d}",
                firm_specific_score=Decimal(index),
                global_score=Decimal(-index),
            )
            for index in range(20)
        )
        included = types.SimpleNamespace(
            fold_id=fold_id,
            decision_session=bridge.date.fromisoformat(h20[6]),
            current_accepted=included_rows,
            current_refused=(),
            censored_accepted=included_rows,
            censored_refused=(),
        )
        fold_commitments.append(_fake_power_fold_commitment(
            fold_id=fold_id,
            current_counts=(1, 1, 0, 0),
            censored_counts=(1, 1, 0, 0),
        ))
        return iter((early, included))

    monkeypatch.setattr(stream, "iter_streamed_production_scoring_fold", iter_fold)
    def finish(value):
        assert value is builder
        artifact.fold_commitments = tuple(fold_commitments)
        return artifact

    monkeypatch.setattr(stream, "finish_streamed_production_scoring", finish)
    monkeypatch.setattr(
        stream, "require_streamed_production_scoring_artifact", lambda value: value
    )
    census = bridge.build_authenticated_formal_test_power_census(builder)
    assert census.h20_test_session_capacity == 1388
    assert census.preoutcome_candidate_date_count == 6
    assert census.valid_h20_test_session_count == 6
    assert census.refused_h20_test_session_count == 0
    assert census.missing_h20_test_session_count == 1382
    assert census.connected_component_instance_count == 120
    assert bridge.require_authenticated_formal_test_power_census(census) is census
    if hasattr(os, "fork"):
        read_descriptor, write_descriptor = os.pipe()
        child = os.fork()
        if child == 0:  # pragma: no cover - result is reported through the pipe
            os.close(read_descriptor)
            try:
                bridge.require_authenticated_formal_test_power_census(census)
            except bridge.AcceptedRiskPowerCalibrationError:
                result = b"refused"
            else:
                result = b"accepted"
            os.write(write_descriptor, result)
            os.close(write_descriptor)
            os._exit(0)
        os.close(write_descriptor)
        outcome = os.read(read_descriptor, 32)
        os.close(read_descriptor)
        _, child_status = os.waitpid(child, 0)
        assert os.WIFEXITED(child_status) and os.WEXITSTATUS(child_status) == 0
        assert outcome == b"refused"
        assert bridge.require_authenticated_formal_test_power_census(census) is census


def test_bridge_and_qc_worker_stable_sum_keep_exact_wide_magnitude_order() -> None:
    values = (
        Decimal("1E-52"),
        Decimal("-1." + "0" * 49 + "02"),
        Decimal("1." + "0" * 49 + "01"),
    )
    with localcontext(bridge._context()):
        expected = Decimal("-2E-51")
        assert bridge._stable_sum(values) == expected
        assert worker._stable_sum(values) == expected
        rounded = Decimal(0)
        for value in sorted(values, key=lambda item: (abs(item), item)):
            rounded += value
    assert rounded == Decimal("1E-51")


def test_closed_hac_matches_the_frozen_worker() -> None:
    from research.analyst_revisions_v2 import power_calibration_receipt as frozen

    values = tuple(
        (Decimal(index % 23) - Decimal(11)) / Decimal(1000)
        for index in range(483)
    )
    assert bridge._hac(values) == frozen._hac(values)


@pytest.mark.parametrize(
    ("disposition", "expected_state", "expected_reason"),
    (
        ("missing", "missing", "empty_preoutcome_cross_section"),
        ("refused", "refused", "preoutcome_named_refusal_present"),
    ),
)
def test_worker_preserves_preoutcome_missing_and_refused_slots(
    disposition: str,
    expected_state: str,
    expected_reason: str,
) -> None:
    result = worker.evaluate_calibration_session(
        _hashed_session(
            disposition=disposition, decisions=[], component_count=0
        ),
        _NoMarketReads(),
        _NoMarketReads(),
    )
    assert result["state"] == expected_state
    assert result["reason"] == expected_reason
    assert result["beta_value"] is None


def test_named_terminal_refusal_precedes_existing_end_bars() -> None:
    terminal = {
        "disposition": "named_terminal_refusal",
        "stock_return": None,
        "reason": "crsp_equivalent_terminal_payoff_unavailable",
        "terminal_lineage_sha256": "a" * 64,
        "available_at_utc": "2026-09-12T00:00:00.000000Z",
    }
    row = _hashed_session(
        disposition="ready",
        decisions=[_decision(1, terminal=terminal)],
        component_count=1,
    )
    result = worker.evaluate_calibration_session(
        row, _NoMarketReads(), _NoMarketReads()
    )
    assert result["state"] == "refused"
    assert result["reason"] == "crsp_equivalent_terminal_payoff_unavailable"


def test_preoutcome_refusal_does_not_inflate_terminal_slot_census() -> None:
    refusal = types.SimpleNamespace(refusal_sha256="a" * 64)
    row = bridge._calibration_session_record(
        session="2018-01-31",
        position=0,
        accepted=(),
        refused=(refusal,),
        benchmark_security_id="SPY SID",
        terminal_by_slot={},
    )
    assert row["preoutcome_disposition"] == "refused"
    assert row["preoutcome_refusal_sha256s"] == ["a" * 64]
    assert row["security_terminal_count"] == 0


def test_missing_benchmark_is_a_missing_beta_state() -> None:
    row = _hashed_session(
        disposition="ready", decisions=[_decision(1)], component_count=1
    )
    result = worker.evaluate_calibration_session(row, {}, {})
    assert result["state"] == "missing"
    assert result["reason"] == "missing_benchmark_total_return_open"


def test_rank_deficient_cross_section_is_a_named_refusal() -> None:
    decisions = [_decision(index) for index in range(51)]
    row = _hashed_session(
        disposition="ready", decisions=decisions, component_count=51
    )
    daily = {
        ("SPY SID", "2018-01-31"): "100",
        ("SPY SID", "2018-03-01"): "101",
    }
    for decision in decisions:
        daily[(decision["security_id"], "2018-01-31")] = "10"
        daily[(decision["security_id"], "2018-03-01")] = "11"
    result = worker.evaluate_calibration_session(row, daily, {})
    assert result["state"] == "refused"
    assert result["reason"] == "rank_deficient_design"


def test_calibration_projection_is_no_orders_total_return_and_strict_prepublication() -> None:
    fake_input = types.SimpleNamespace(
        manifest_sha256="a" * 64,
        manifest_bytes=b"{}\n",
        input_id="calibration-input",
        input_sha256="b" * 64,
    )
    source = runtime._entry_source(
        fake_input,
        input_manifest_key="arv2/power-calibration/input/manifest.json",
        output_manifest_key="arv2/power-calibration/output/manifest.json",
    )
    compile(source, "main.py", "exec")
    text = source.decode("utf-8")
    assert "DataNormalizationMode.TOTAL_RETURN" in text
    assert "item[0] < instant" in text
    assert 'if row["preoutcome_disposition"] != "ready"' in text
    named_refusal_guard = text.index('== "named_terminal_refusal"')
    first_daily_requirement = text.index("daily_required.add")
    assert named_refusal_guard < first_daily_requirement
    assert text.index("save_bytes(key, compressed)") < text.index(
        "save_bytes(OUTPUT_MANIFEST_KEY, payload)"
    )
    assert "market_order" not in text.casefold()
    assert "set_holdings" not in text.casefold()
    with pytest.raises(runtime.PowerCalibrationRuntimeProjectionError, match="order"):
        runtime._source("main.py", b"def f(x):\n    x.market_order('SPY', 1)\n")
    with pytest.raises(runtime.PowerCalibrationRuntimeProjectionError, match="capacity"):
        runtime._source("main.py", b"#" * (runtime.MAX_SOURCE_BYTES + 1))


def test_current_view_projection_excludes_global_and_censored_scores() -> None:
    fields = dict(
        signal_arm=SignalArm.CURRENT_VINTAGE,
        fold_id="arv2-wf-test-2020",
        partition=FoldPartition.VALIDATION,
        decision_session="2018-01-31",
        security_id="security-001",
        issuer_id="issuer-001",
        share_class_id="share-001",
        listing_id="listing-001",
        historical_ticker="AAA",
        sector_id="sector-001",
        industry_id="industry-001",
        state=ScoreState.STRUCTURAL_ZERO,
        firm_specific_score=Decimal(0),
        global_score=Decimal(0),
        transformed_controls=(Decimal(0),) * 25,
        realized_volatility_60d=Decimal(0),
        earnings_anchor_signed_session_distance=None,
        common_event_component_id="component-001",
        contributing_c2_row_sha256s=(),
        contributions=(),
        precontrol_row_sha256="1" * 64,
        firm_model_sha256="2" * 64,
        global_model_sha256="3" * 64,
    )
    semantic = {
        "signal_arm": "current_vintage",
        "fold_id": fields["fold_id"],
        "partition": "validation",
        "decision_session": fields["decision_session"],
        "security_id": fields["security_id"],
        "issuer_id": fields["issuer_id"],
        "share_class_id": fields["share_class_id"],
        "listing_id": fields["listing_id"],
        "historical_ticker": fields["historical_ticker"],
        "sector_id": fields["sector_id"],
        "industry_id": fields["industry_id"],
        "state": "structural_zero",
        "firm_specific_score": "0",
        "global_score": "0",
        "transformed_controls": ["0"] * 25,
        "realized_volatility_60d": "0",
        "earnings_anchor_signed_session_distance": None,
        "common_event_component_id": fields["common_event_component_id"],
        "contributing_c2_row_sha256s": [],
        "contributions": [],
        "precontrol_row_sha256": fields["precontrol_row_sha256"],
        "firm_model_sha256": fields["firm_model_sha256"],
        "global_model_sha256": fields["global_model_sha256"],
    }
    zero = FinalDecisionInput(
        **fields,
        row_sha256=hashlib.sha256(canonical_json_bytes(semantic)).hexdigest(),
    )
    projected = bridge._decision_record(zero, None)
    assert projected["firm_specific_score"] == "0"
    assert "global_score" not in projected
    assert "signal_arm" not in projected
    builder_source = inspect.getsource(
        bridge.build_accepted_risk_power_calibration_input
    )
    assert "SignalArm.CURRENT_VINTAGE" in builder_source
    assert "SignalArm.CONSERVATIVE_CENSORED" not in builder_source
    assert "_run_accepted_risk_power_calibration_stream" in builder_source
    for removed_transition in (
        "_acquire_stream_builder", "_require_stream_lease",
        "_complete_external_stream_builder", "_poison_stream_builder",
    ):
        assert removed_transition not in builder_source


def _unregistered_power_parents():
    receipt = object.__new__(bridge.AcceptedRiskPowerCalibrationReceipt)
    receipt_fields = {
        "receipt_id": "accepted-risk-receipt",
        "receipt_hash": "1" * 64,
        "protocol_id": "protocol",
        "protocol_hash": "2" * 64,
        "manifest_id": "manifest",
        "manifest_content_sha256": "3" * 64,
        "valid_beta_date_count": 100,
        "lag_pair_counts_0_through_20": (100,) * 21,
        "long_run_variance": Decimal("0.01"),
        "component_count_census_sha256": "4" * 64,
        "component_count_census_session_count": 483,
        "q05_components_per_date": 100,
        "raw_required_valid_dates": 50,
        "required_valid_dates": 50,
        "required_connected_components": 50,
        "fixed_h20_test_session_capacity": 1388,
        "disposition": (
            ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
        ),
        "accepted_risk_policy_id": "accepted-risk",
        "output_id": "output",
        "output_sha256": "5" * 64,
        "output": object(),
        "protocol": object(),
    }
    for name, value in receipt_fields.items():
        object.__setattr__(receipt, name, value)
    successor = object.__new__(bridge.AcceptedRiskStockPowerSuccessor)
    for name, value in {
        "successor_id": "stock-power-successor",
        "successor_sha256": "6" * 64,
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.receipt_hash,
        "required_valid_dates": 50,
        "required_connected_components": 50,
        "disposition": receipt.disposition.value,
        "outcome_access": False,
        "qc_action": False,
        "deployment": False,
        "orders": False,
    }.items():
        object.__setattr__(successor, name, value)
    scoring = types.SimpleNamespace(
        artifact_id="formal-scoring", artifact_sha256="7" * 64
    )
    census = object.__new__(bridge.AuthenticatedFormalTestPowerCensus)
    for name, value in {
        "census_id": "formal-test-census",
        "census_sha256": "8" * 64,
        "scoring_artifact": scoring,
        "scoring_artifact_id": scoring.artifact_id,
        "scoring_artifact_sha256": scoring.artifact_sha256,
        "h20_test_session_capacity": 1388,
        "preoutcome_candidate_date_count": 100,
        "valid_h20_test_session_count": 100,
        "refused_h20_test_session_count": 0,
        "missing_h20_test_session_count": 1288,
        "connected_component_instance_count": 100,
        "complete_axis": True,
    }.items():
        object.__setattr__(census, name, value)
    return receipt, successor, census, scoring


@pytest.fixture
def authenticated_power_floor(monkeypatch):
    receipt, _unregistered_successor, census, scoring = _unregistered_power_parents()
    monkeypatch.setattr(
        bridge, "require_accepted_risk_power_calibration_receipt",
        lambda value: value if value is receipt else (_ for _ in ()).throw(
            bridge.AcceptedRiskPowerCalibrationError("receipt substitute")
        ),
    )
    successor = bridge.build_accepted_risk_stock_power_successor(receipt)
    monkeypatch.setattr(
        bridge, "require_authenticated_formal_test_power_census",
        lambda value: value if value is census else (_ for _ in ()).throw(
            bridge.AcceptedRiskPowerCalibrationError("census substitute")
        ),
    )
    value = bridge.build_authenticated_power_floor_binding(
        receipt=receipt, successor=successor, formal_census=census
    )
    return value, receipt, successor, census, scoring


def test_authenticated_floor_owns_parents_and_matches_formal_binding(
    authenticated_power_floor,
) -> None:
    value, receipt, successor, census, scoring = authenticated_power_floor
    references = tuple(
        weakref.ref(item) for item in (receipt, successor, census, value.formal_power)
    )
    del receipt, successor, census, scoring
    gc.collect()
    assert all(reference() is not None for reference in references)
    assert bridge.require_authenticated_power_floor_binding(value) is value
    assert value.formal_power.receipt_id == value.receipt.receipt_id
    assert value.power_floor is not None
    assert type(value.power_floor) is PowerFloorBinding


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_power_and_formal_binding_authorities_do_not_cross_fork(
    authenticated_power_floor,
) -> None:
    value, _receipt, successor, _census, _scoring = authenticated_power_floor
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - assertions are reported through the pipe
        os.close(read_descriptor)
        refused = 0
        for operation in (
            lambda: bridge.require_accepted_risk_stock_power_successor(successor),
            lambda: bridge.require_authenticated_power_floor_binding(value),
            lambda: formal_input_bundle.require_formal_power_calibration_binding(
                value.formal_power
            ),
        ):
            try:
                operation()
            except (bridge.AcceptedRiskPowerCalibrationError, ValueError):
                refused += 1
        os.write(write_descriptor, str(refused).encode("ascii"))
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 16)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"3"
    assert bridge.require_accepted_risk_stock_power_successor(successor) is successor
    assert bridge.require_authenticated_power_floor_binding(value) is value
    assert (
        formal_input_bundle.require_formal_power_calibration_binding(
            value.formal_power
        )
        is value.formal_power
    )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_every_power_process_registry_is_cleared_in_child_and_preserved_in_parent() -> None:
    class Token:
        pass

    registry_names = (
        "_INPUTS", "_OUTPUTS", "_RECEIPTS", "_SUCCESSORS",
        "_FORMAL_CENSUSES", "_POWER_FLOORS", "_QC_TERMINALS",
    )
    tokens = tuple(Token() for _ in registry_names)
    with bridge._LOCK:
        for name, token in zip(registry_names, tokens, strict=True):
            getattr(bridge, name)[id(token)] = (token, os.getpid())
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - result is reported through the pipe
        os.close(read_descriptor)
        empty = all(not getattr(bridge, name) for name in registry_names)
        acquired = bridge._LOCK.acquire(timeout=1)
        if acquired:
            bridge._LOCK.release()
        os.write(write_descriptor, f"{empty},{acquired}".encode("ascii"))
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 32)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"True,True"
    with bridge._LOCK:
        assert all(
            id(token) in getattr(bridge, name)
            for name, token in zip(registry_names, tokens, strict=True)
        )
        for name, token in zip(registry_names, tokens, strict=True):
            getattr(bridge, name).pop(id(token), None)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("receipt", None),
        ("successor", None),
        ("formal_census", None),
        ("scoring_artifact_id", "different-formal-scoring"),
        ("h20_test_session_capacity", 1387),
        ("preoutcome_candidate_date_count", 99),
        ("valid_h20_test_session_count", 99),
        ("refused_h20_test_session_count", 1),
        ("missing_h20_test_session_count", 1287),
        ("connected_component_instance_count", 99),
        ("observed_connected_components", 99),
    ),
)
def test_authenticated_floor_rejects_parent_or_census_substitution(
    authenticated_power_floor, field: str, replacement: object
) -> None:
    value = authenticated_power_floor[0]
    object.__setattr__(value, field, replacement)
    with pytest.raises(bridge.AcceptedRiskPowerCalibrationError):
        bridge.require_authenticated_power_floor_binding(value)


def test_formal_submission_helper_rejects_raw_floor_before_runtime_access() -> None:
    raw = object.__new__(PowerFloorBinding)
    with pytest.raises(formal_submit.FormalQcSubmissionError, match="authenticated"):
        formal_submit._require_streamed_authenticated_power_floor(
            raw, object()
        )


def test_plan_uploads_shards_before_manifest(monkeypatch, tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    shard_path = tmp_path / "input.jsonl.gz"
    shard_path.write_bytes(b"compressed-input")
    shard_path.chmod(0o600)
    descriptor = bridge.CalibrationShardDescriptor(
        ordinal=0,
        object_store_key="arv2/power-calibration/input/content/hash.jsonl.gz",
        content_sha256="1" * 64,
        compressed_sha256=hashlib.sha256(shard_path.read_bytes()).hexdigest(),
        row_count=1,
        uncompressed_byte_count=1,
        compressed_byte_count=shard_path.stat().st_size,
        first_session="2018-01-31",
        last_session="2018-01-31",
    )
    calibration_input = types.SimpleNamespace(
        input_id="input-id",
        input_sha256="2" * 64,
        manifest_bytes=b'{"schema":"input"}\n',
        shard_paths=(shard_path,),
        shard_descriptors=(descriptor,),
    )
    source = runtime.PowerCalibrationProjectSource(
        project_path="main.py",
        content_sha256=hashlib.sha256(b"pass\n").hexdigest(),
        byte_count=5,
        content=b"pass\n",
    )
    projection = runtime.PowerCalibrationQcProjection(
        projection_id="projection-id",
        projection_sha256="3" * 64,
        input_id=calibration_input.input_id,
        input_sha256=calibration_input.input_sha256,
        input_manifest_key="arv2/power-calibration/input/manifest.json",
        output_manifest_key="arv2/power-calibration/output/manifest.json",
        project_name=bridge.PROJECT_NAME,
        backtest_name=bridge.BACKTEST_NAME,
        sources=(source,),
        daily_history_call_limit=1,
        minute_history_call_limit=1,
        formal_outcome_evaluation=False,
        orders_authorized=False,
    )
    monkeypatch.setattr(
        submit, "require_accepted_risk_power_calibration_input", lambda value: value
    )
    monkeypatch.setattr(
        submit, "require_power_calibration_qc_projection", lambda value: value
    )
    plan = submit.build_power_calibration_submission_plan(
        calibration_input=calibration_input,
        projection=projection,
        organization_id="organization-id",
        review_directory=tmp_path,
        archive_directory=tmp_path / "archive",
    )
    assert tuple(item.role for item in plan.uploads) == (
        "input_shard", "input_manifest"
    )
    assert plan.uploads[-1].payload == calibration_input.manifest_bytes
    assert submit.require_power_calibration_submission_plan(plan) is plan


def _power_submission_fixture(monkeypatch, tmp_path):
    tmp_path.chmod(0o700)
    shard_path = tmp_path / "input-shard.jsonl.gz"
    shard_path.write_bytes(b"compressed-input")
    shard_path.chmod(0o600)
    descriptor = bridge.CalibrationShardDescriptor(
        ordinal=0,
        object_store_key="arv2/power-calibration/input/content/hash.jsonl.gz",
        content_sha256="1" * 64,
        compressed_sha256=hashlib.sha256(shard_path.read_bytes()).hexdigest(),
        row_count=1,
        uncompressed_byte_count=1,
        compressed_byte_count=shard_path.stat().st_size,
        first_session="2018-01-31",
        last_session="2018-01-31",
    )
    calibration_input = types.SimpleNamespace(
        input_id="input-id",
        input_sha256="2" * 64,
        manifest_bytes=b'{"schema":"input"}\n',
        shard_paths=(shard_path,),
        shard_descriptors=(descriptor,),
    )
    source = runtime.PowerCalibrationProjectSource(
        project_path="main.py",
        content_sha256=hashlib.sha256(b"pass\n").hexdigest(),
        byte_count=5,
        content=b"pass\n",
    )
    projection = runtime.PowerCalibrationQcProjection(
        projection_id="projection-id",
        projection_sha256="3" * 64,
        input_id=calibration_input.input_id,
        input_sha256=calibration_input.input_sha256,
        input_manifest_key="arv2/power-calibration/input/manifest.json",
        output_manifest_key="arv2/power-calibration/output/manifest.json",
        project_name=bridge.PROJECT_NAME,
        backtest_name=bridge.BACKTEST_NAME,
        sources=(source,),
        daily_history_call_limit=1,
        minute_history_call_limit=1,
        formal_outcome_evaluation=False,
        orders_authorized=False,
    )
    monkeypatch.setattr(
        submit, "require_accepted_risk_power_calibration_input", lambda value: value
    )
    monkeypatch.setattr(
        submit, "require_power_calibration_qc_projection", lambda value: value
    )
    plan = submit.build_power_calibration_submission_plan(
        calibration_input=calibration_input,
        projection=projection,
        organization_id="organization-id",
        review_directory=tmp_path,
        archive_directory=tmp_path / "archive",
    )
    review_path = tmp_path / submit.REVIEW_FILENAME
    review_path.write_bytes(
        submit.render_power_calibration_review_claim_candidate(plan)
    )
    review_path.chmod(0o600)
    claim = submit.load_power_calibration_review_claim(plan)
    signature = types.SimpleNamespace(authority_sha256="4" * 64)
    monkeypatch.setattr(submit, "_preflight", lambda *_args: b"authority")
    _install_offline_power_action_binding_guards(monkeypatch)
    return plan, claim, signature


def _registered_power_action_receipts(monkeypatch, tmp_path):
    plan, claim, signature = _power_submission_fixture(monkeypatch, tmp_path)
    _install_power_submission_transport(monkeypatch, plan)
    permit, launch = submit.execute_power_calibration_submission_once(
        plan=plan,
        review_claim=claim,
        owner_signature=signature,
        client=object(),
        started_at_utc="2026-09-12T12:00:00.000000Z",
    )
    terminal = submit.inspect_power_calibration_terminal_status(
        plan=plan,
        review_claim=claim,
        owner_signature=signature,
        permit=permit,
        launch=launch,
        client=object(),
    )
    return plan, claim, signature, permit, launch, terminal


def test_power_offline_action_receipts_remain_rejected_after_restore(
    tmp_path,
) -> None:
    with pytest.MonkeyPatch.context() as patch:
        plan, claim, signature, permit, launch, terminal = (
            _registered_power_action_receipts(patch, tmp_path)
        )
    current_launch = _direct_closure_value(
        submit.require_power_calibration_launch_receipt, "current_launch"
    )
    current_terminal = _direct_closure_value(
        submit.require_power_calibration_terminal_status, "current_terminal"
    )
    assert current_launch(launch) is None
    assert current_terminal(terminal) is None


def test_cloned_power_action_refuses_before_transport(
    monkeypatch, tmp_path,
) -> None:
    public = submit.execute_power_calibration_submission_once
    plan, claim, signature = _power_submission_fixture(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        formal_submit, "_require_concrete_transport", lambda value: value
    )
    monkeypatch.setattr(
        submit,
        "_call",
        lambda *_args, **_kwargs: calls.append((_args, _kwargs)),
    )
    implementation = _direct_closure_value(public, "execute_impl")
    cloned_implementation = _with_global_values(
        implementation,
        _preflight=lambda *_args, **_kwargs: b"cloned-preflight",
    )
    cloned_public = _with_closure_value(
        public, "execute_impl", cloned_implementation
    )
    cloned_public = _with_closure_value(
        cloned_public, "binding_guard", lambda _operation: None
    )
    with pytest.raises(
        formal_submit.FormalQcSubmissionError,
        match="capability caller changed",
    ):
        cloned_public(
            plan=plan,
            review_claim=claim,
            owner_signature=signature,
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert calls == []


def _install_power_submission_transport(
    monkeypatch, plan, *, changed_source_readback: bool = False,
):
    calls = []
    file_reads = 0

    monkeypatch.setattr(formal_submit, "_require_concrete_transport", lambda value: value)
    test_minter = lambda **_kwargs: object()
    for name in (
        "execute_power_calibration_submission_once",
        "inspect_power_calibration_terminal_status",
        "persist_power_calibration_output",
    ):
        monkeypatch.setattr(
            submit,
            name,
            _with_closure_value(
                getattr(submit, name),
                "transport_capability_minter",
                test_minter,
            ),
        )
    monkeypatch.setattr(submit.time, "sleep", lambda _seconds: None)

    def call(_client, _capability, method, *args):
        nonlocal file_reads
        calls.append((method, args))
        if method == "_set_object_multipart":
            return None
        if method == "_read_object_properties":
            key = args[1]
            entry = next(item for item in plan.uploads if item.object_store_key == key)
            return {
                "success": True,
                "metadata": {
                    "key": key,
                    "size": entry.byte_count,
                    "md5": entry.content_md5,
                },
            }
        assert method == "_request_json"
        endpoint, request = args
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read" and request == {}:
            return {"success": True, "projects": []}
        if endpoint == "projects/create":
            return {
                "success": True,
                "projects": [{
                    "projectId": 123,
                    "name": plan.project_name,
                    "language": "Py",
                }],
            }
        if endpoint == "projects/read":
            return {
                "success": True,
                "projects": [{
                    "projectId": 123,
                    "organizationId": plan.organization_id,
                    "name": plan.project_name,
                    "language": "Py",
                    "owner": True,
                    "codeRunning": False,
                    "collaborators": [],
                }],
            }
        if endpoint == "files/read":
            file_reads += 1
            if file_reads == 1:
                return {
                    "success": True,
                    "files": [{"name": "main.py", "content": ""}],
                }
            content = plan.source_files[0].content.decode("utf-8")
            if changed_source_readback:
                content += "# changed after upload\n"
            return {
                "success": True,
                "files": [{"name": "main.py", "content": content}],
            }
        if endpoint in {"files/create", "files/update"}:
            return {"success": True}
        if endpoint == "compile/create":
            return {"success": True, "compileId": "compile-test"}
        if endpoint == "compile/read":
            return {
                "success": True,
                "compileId": "compile-test",
                "state": "BuildSuccess",
            }
        if endpoint == "backtests/create":
            return {
                "success": True,
                "backtest": {
                    "backtestId": "backtest-test",
                    "name": plan.backtest_name,
                    "projectId": 123,
                    "status": "In Queue...",
                },
            }
        if endpoint == "backtests/list":
            return {
                "success": True,
                "count": 1,
                "backtests": [{
                    "backtestId": "backtest-test",
                    "name": plan.backtest_name,
                    "projectId": 123,
                    "status": "Completed.",
                }],
            }
        raise AssertionError((method, args))

    monkeypatch.setattr(submit, "_call", call)
    return calls


def test_power_submission_uploads_manifest_last_and_reads_sources_exactly(
    monkeypatch, tmp_path,
) -> None:
    plan, claim, signature = _power_submission_fixture(monkeypatch, tmp_path)
    calls = _install_power_submission_transport(monkeypatch, plan)
    permit, launch = submit.execute_power_calibration_submission_once(
        plan=plan,
        review_claim=claim,
        owner_signature=signature,
        client=object(),
        started_at_utc="2026-09-12T12:00:00.000000Z",
    )
    assert launch.backtest_id == "backtest-test"
    assert submit.require_power_calibration_launch_receipt(
        launch,
        plan=plan,
        permit=permit,
        review_claim=claim,
        owner_signature=signature,
    ) is launch
    uploaded_keys = tuple(
        args[1]
        for method, args in calls
        if method == "_set_object_multipart"
    )
    assert uploaded_keys == tuple(item.object_store_key for item in plan.uploads)
    assert plan.uploads[-1].role == "input_manifest"
    endpoints = tuple(
        args[0] for method, args in calls if method == "_request_json"
    )
    assert endpoints.count("compile/create") == 1
    assert endpoints.count("backtests/create") == 1


def test_power_submission_source_readback_mismatch_locks_and_cannot_retry(
    monkeypatch, tmp_path,
) -> None:
    plan, claim, signature = _power_submission_fixture(monkeypatch, tmp_path)
    calls = _install_power_submission_transport(
        monkeypatch, plan, changed_source_readback=True
    )
    with pytest.raises(submit.PowerCalibrationSubmissionLocked):
        submit.execute_power_calibration_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=signature,
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    endpoints = tuple(
        args[0] for method, args in calls if method == "_request_json"
    )
    assert "compile/create" not in endpoints
    action_count = len(calls)
    with pytest.raises(submit.PowerCalibrationSubmissionLocked, match="already spent"):
        submit.execute_power_calibration_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=signature,
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert len(calls) == action_count


def test_power_output_post_archive_failure_is_always_locked(
    monkeypatch, tmp_path,
) -> None:
    plan, claim, signature, permit, launch, terminal = (
        _registered_power_action_receipts(monkeypatch, tmp_path)
    )
    monkeypatch.setattr(
        submit,
        "_call",
        lambda *_args: {
            "success": True,
            "object": {
                "key": plan.output_manifest_key,
                "objectData": "e30K",  # canonical decoded object lacks its schema
            },
        },
    )
    with pytest.raises(submit.PowerCalibrationSubmissionLocked):
        submit.persist_power_calibration_output(
            plan=plan,
            review_claim=claim,
            owner_signature=signature,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
            client=object(),
        )
    assert plan.archive_directory.is_dir()


def test_power_terminal_transport_or_parser_failure_is_always_locked(
    monkeypatch, tmp_path,
) -> None:
    plan, claim, signature, permit, launch, _terminal = (
        _registered_power_action_receipts(monkeypatch, tmp_path)
    )
    monkeypatch.setattr(
        submit,
        "_call",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("ambiguous response")),
    )
    with pytest.raises(submit.PowerCalibrationSubmissionLocked, match="ambiguous"):
        submit.inspect_power_calibration_terminal_status(
            plan=plan,
            review_claim=claim,
            owner_signature=signature,
            permit=permit,
            launch=launch,
            client=object(),
        )


def test_power_action_receipts_are_process_return_authorities(
    monkeypatch, tmp_path
) -> None:
    plan, claim, signature, permit, launch, terminal = (
        _registered_power_action_receipts(monkeypatch, tmp_path)
    )
    assert submit.require_power_calibration_launch_receipt(
        launch, plan=plan, permit=permit, review_claim=claim,
        owner_signature=signature,
    ) is launch
    assert submit.require_power_calibration_terminal_status(
        terminal, plan=plan, launch=launch, permit=permit,
        review_claim=claim, owner_signature=signature,
    ) is terminal
    with pytest.raises(submit.PowerCalibrationSubmissionError, match="process-return"):
        submit.require_power_calibration_launch_receipt(
            dataclasses.replace(launch), plan=plan, permit=permit,
            review_claim=claim, owner_signature=signature,
        )
    with pytest.raises(submit.PowerCalibrationSubmissionError, match="process-return"):
        submit.require_power_calibration_terminal_status(
            dataclasses.replace(terminal), plan=plan, launch=launch,
            permit=permit, review_claim=claim, owner_signature=signature,
        )


@pytest.mark.parametrize("registry_name", ("_LAUNCH_AUTHORITIES", "_TERMINAL_AUTHORITIES"))
def test_copying_a_calibration_return_authority_revokes_not_reseals(
    monkeypatch, tmp_path, registry_name: str,
) -> None:
    plan, claim, signature, permit, launch, terminal = (
        _registered_power_action_receipts(monkeypatch, tmp_path)
    )
    value = launch if registry_name == "_LAUNCH_AUTHORITIES" else terminal
    registry = getattr(submit, registry_name)
    original = registry[id(value)]
    registry[id(value)] = tuple(item for item in original)
    assert registry[id(value)] is not original
    with pytest.raises(submit.PowerCalibrationSubmissionError, match="process-return"):
        if value is launch:
            submit.require_power_calibration_launch_receipt(
                launch, plan=plan, permit=permit, review_claim=claim,
                owner_signature=signature,
            )
        else:
            submit.require_power_calibration_terminal_status(
                terminal, plan=plan, launch=launch, permit=permit,
                review_claim=claim, owner_signature=signature,
            )
    assert id(value) not in registry


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_power_action_receipts_do_not_cross_fork(
    monkeypatch, tmp_path
) -> None:
    plan, claim, signature, permit, launch, terminal = (
        _registered_power_action_receipts(monkeypatch, tmp_path)
    )
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - result is reported through the pipe
        os.close(read_descriptor)
        operations = (
            lambda: submit.require_power_calibration_launch_receipt(
                launch, plan=plan, permit=permit, review_claim=claim,
                owner_signature=signature,
            ),
            lambda: submit.require_power_calibration_terminal_status(
                terminal, plan=plan, launch=launch, permit=permit,
                review_claim=claim, owner_signature=signature,
            ),
        )
        refused = 0
        for operation in operations:
            try:
                operation()
            except (submit.PowerCalibrationSubmissionError, ValueError):
                refused += 1
        os.write(write_descriptor, str(refused).encode("ascii"))
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 16)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"2"
    assert submit.require_power_calibration_launch_receipt(
        launch, plan=plan, permit=permit, review_claim=claim,
        owner_signature=signature,
    ) is launch


def test_power_artifact_authority_mutators_and_terminal_minter_are_not_exposed() -> None:
    for name in (
        "_make_power_artifact_authority",
        "_seal_power_artifact_builder_callers",
        "_seal_power_launch_builder_callers",
        "_power_artifact_register_input",
        "_power_artifact_current_input",
        "_power_artifact_register_output",
        "_power_artifact_current_output",
        "_power_artifact_register_receipt",
        "_power_artifact_current_receipt",
        "_power_artifact_register_successor",
        "_power_artifact_current_successor",
        "_power_artifact_current_terminal",
        "_claim_power_calibration_terminal_minter",
        "_build_accepted_risk_power_calibration_input_impl",
        "_load_accepted_risk_power_calibration_output_impl",
        "_compute_accepted_risk_power_calibration_receipt_impl",
    ):
        assert name not in vars(bridge)
    for name in (
        "_mint_terminal_receipt",
        "_power_terminal_minter",
        "_bind_terminal_persistence",
        "_persist_power_calibration_output_impl",
        "_register_launch_authority",
        "_register_terminal_authority",
        "_make_submission_return_authority",
        "_seal_submission_return_builder_callers",
        "_return_authority_register_launch",
        "_return_authority_register_terminal",
        "_execute_power_calibration_submission_once_impl",
        "_inspect_power_calibration_terminal_status_impl",
        "_make_power_action_global_binding_guard",
        "_seal_power_action_global_bindings",
        "_require_power_action_global_bindings",
    ):
        assert name not in vars(submit)


def test_power_public_actions_and_return_requires_refuse_rebound_globals(
    monkeypatch, tmp_path,
) -> None:
    production_execute = submit.execute_power_calibration_submission_once
    production_require_launch = submit.require_power_calibration_launch_receipt
    plan, claim, signature, permit, launch, _terminal = (
        _registered_power_action_receipts(monkeypatch, tmp_path)
    )

    # The offline fixture intentionally replaces validators, transport helpers,
    # and public wrappers.  A retained production wrapper must refuse that
    # namespace before any external action or return-authority lookup.
    with pytest.raises(
        submit.PowerCalibrationSubmissionError,
        match="action global authority changed",
    ):
        production_execute(
            plan=plan,
            review_claim=claim,
            owner_signature=signature,
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    with pytest.raises(
        submit.PowerCalibrationSubmissionError,
        match="action global authority changed",
    ):
        production_require_launch(
            launch,
            plan=plan,
            permit=permit,
            review_claim=claim,
            owner_signature=signature,
        )


def test_power_global_seal_pins_public_authority_mirror_root(monkeypatch) -> None:
    production_require = submit.require_power_calibration_launch_receipt
    monkeypatch.setattr(submit, "_LAUNCH_AUTHORITIES", {})
    with pytest.raises(
        submit.PowerCalibrationSubmissionError,
        match="action global authority changed",
    ):
        production_require(
            object(),
            plan=object(),
            permit=object(),
            review_claim=object(),
            owner_signature=object(),
        )


@pytest.mark.parametrize(
    "name",
    (
        "_preflight",
        "PowerCalibrationLaunchReceipt",
        "canonical_json_bytes",
        "globals",
        "type",
        "_unexpected_power_action_global",
    ),
)
def test_power_submission_refuses_rebound_helper_or_constructor_before_mint(
    monkeypatch, name: str,
) -> None:
    production_execute = submit.execute_power_calibration_submission_once
    prior = tuple(submit._LAUNCH_AUTHORITIES.items())
    monkeypatch.setattr(submit, name, object(), raising=False)
    with pytest.raises(
        submit.PowerCalibrationSubmissionError,
        match="action global authority changed",
    ):
        production_execute(
            plan=object(),
            review_claim=object(),
            owner_signature=object(),
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert tuple(submit._LAUNCH_AUTHORITIES.items()) == prior


def test_power_submission_refuses_rebound_transport_dependency_before_mint(
    monkeypatch,
) -> None:
    production_execute = submit.execute_power_calibration_submission_once
    prior = tuple(submit._LAUNCH_AUTHORITIES.items())
    monkeypatch.setattr(submit.formal, "_created_project", object())
    with pytest.raises(
        submit.PowerCalibrationSubmissionError,
        match="action dependency authority changed",
    ):
        production_execute(
            plan=object(),
            review_claim=object(),
            owner_signature=object(),
            client=object(),
            started_at_utc="2026-09-12T12:00:00.000000Z",
        )
    assert tuple(submit._LAUNCH_AUTHORITIES.items()) == prior


@pytest.mark.parametrize(
    ("namespace", "name", "replacement"),
    (
        (bridge.os, "open", None),
        (bridge.os, "O_EXCL", 0),
        (bridge.json, "loads", None),
        (bridge.gzip, "decompress", None),
        (bridge.json.JSONDecoder, "__init__", None),
    ),
)
def test_power_persistence_refuses_rebound_bridge_io_before_action(
    monkeypatch, tmp_path, namespace, name, replacement,
) -> None:
    production_persist = submit.persist_power_calibration_output
    callbacks = []
    archive_directory = tmp_path / "archive"

    def hostile(*args, **values):
        callbacks.append((args, values))
        raise AssertionError("hostile calibration persistence I/O executed")

    monkeypatch.setattr(
        namespace,
        name,
        hostile if replacement is None else replacement,
    )
    with pytest.raises(
        submit.PowerCalibrationSubmissionError,
        match="action dependency authority changed",
    ):
        production_persist(
            plan=types.SimpleNamespace(archive_directory=archive_directory),
            review_claim=object(),
            owner_signature=object(),
            permit=object(),
            launch=object(),
            terminal_status=object(),
            client=object(),
        )
    assert callbacks == []
    assert not archive_directory.exists()


def test_power_authority_closures_expose_no_mutable_state_container() -> None:
    """Ordinary closure reflection cannot reach an injectable vault object."""

    operations = (
        bridge.build_accepted_risk_power_calibration_input,
        bridge.require_accepted_risk_power_calibration_input,
        bridge.load_accepted_risk_power_calibration_output,
        bridge.require_accepted_risk_power_calibration_output,
        bridge.compute_accepted_risk_power_calibration_receipt,
        bridge.require_accepted_risk_power_calibration_receipt,
        bridge.build_accepted_risk_stock_power_successor,
        bridge.require_accepted_risk_stock_power_successor,
        bridge.build_authenticated_formal_test_power_census,
        bridge.require_authenticated_formal_test_power_census,
        bridge.build_authenticated_power_floor_binding,
        bridge.require_authenticated_power_floor_binding,
        bridge.require_power_calibration_qc_terminal_receipt,
        submit.execute_power_calibration_submission_once,
        submit.require_power_calibration_launch_receipt,
        submit.inspect_power_calibration_terminal_status,
        submit.require_power_calibration_terminal_status,
        submit.persist_power_calibration_output,
    )
    mutable_cells: list[tuple[str, str, str]] = []
    observed: set[int] = set()
    pending = list(operations)
    while pending:
        function = pending.pop()
        if id(function) in observed:
            continue
        observed.add(id(function))
        if function.__closure__ is None:
            continue
        for name, cell in zip(
            function.__code__.co_freevars,
            function.__closure__,
            strict=True,
        ):
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if type(value) in {dict, list, set}:
                # Exact mutable namespace objects are verification anchors,
                # never receipt or authority vaults.
                if name == "module_globals" and value is function.__globals__:
                    continue
                if name == "module_registry" and value is sys.modules:
                    continue
                if name == "bridge_module_globals" and value is vars(bridge):
                    continue
                mutable_cells.append(
                    (function.__name__, name, type(value).__name__)
                )
            if type(value) is types.FunctionType:
                pending.append(value)
    assert mutable_cells == []


def test_extracted_power_artifact_registrars_cannot_mint_directly() -> None:
    attempts = (
        (
            bridge.build_accepted_risk_power_calibration_input,
            "register_input",
            bridge.AcceptedRiskPowerCalibrationInput,
            (object(), object(), object(), object(), b"candidate", ()),
        ),
        (
            bridge.load_accepted_risk_power_calibration_output,
            "register_output",
            bridge.AcceptedRiskPowerCalibrationOutput,
            (object(), object(), ()),
        ),
        (
            bridge.compute_accepted_risk_power_calibration_receipt,
            "register_receipt",
            bridge.AcceptedRiskPowerCalibrationReceipt,
            (object(), object(), b"candidate", "0" * 64, ()),
        ),
        (
            bridge.build_accepted_risk_stock_power_successor,
            "register_successor",
            bridge.AcceptedRiskStockPowerSuccessor,
            (object(), b"candidate"),
        ),
        (
            bridge.build_authenticated_formal_test_power_census,
            "register_census",
            bridge.AuthenticatedFormalTestPowerCensus,
            (object(), {}),
        ),
        (
            bridge.build_authenticated_power_floor_binding,
            "register_floor",
            bridge.AuthenticatedPowerFloorBinding,
            (object(), object(), object(), object(), object(), {}),
        ),
    )
    for root, registrar_name, value_type, arguments in attempts:
        registrar = _closure_function(root, registrar_name)
        value = object.__new__(value_type)
        with pytest.raises(
            bridge.AcceptedRiskPowerCalibrationError,
            match="registration caller changed",
        ):
            registrar(value, *arguments)


def test_extracted_power_terminal_minter_and_registrar_cannot_mint_directly() -> None:
    minter = _direct_closure_value(
        submit.persist_power_calibration_output,
        "terminal_minter",
    )
    with pytest.raises(
        bridge.AcceptedRiskPowerCalibrationError,
        match="persistence-private",
    ):
        minter(
            plan_id="candidate-plan",
            plan_sha256="0" * 64,
            calibration_input=object(),
            project_id="candidate-project",
            backtest_id="candidate-backtest",
            output_manifest_key="candidate/output/manifest.json",
        )

    registrar = _closure_function(minter, "register_terminal")
    value = object.__new__(bridge.PowerCalibrationQcTerminalReceipt)
    with pytest.raises(
        bridge.AcceptedRiskPowerCalibrationError,
        match="registration caller changed",
    ):
        registrar(value, object(), b"candidate")


def test_extracted_power_return_registrars_cannot_mint_directly() -> None:
    launch_registrar = _direct_closure_value(
        submit.execute_power_calibration_submission_once,
        "register_launch",
    )
    launch = object.__new__(submit.PowerCalibrationLaunchReceipt)
    with pytest.raises(
        submit.PowerCalibrationSubmissionError,
        match="registration caller changed",
    ):
        launch_registrar(
            launch,
            plan=object(),
            permit=object(),
            review_claim=object(),
            owner_signature=object(),
        )

    terminal_registrar = _direct_closure_value(
        submit.inspect_power_calibration_terminal_status,
        "register_terminal",
    )
    terminal = object.__new__(submit.PowerCalibrationTerminalStatus)
    with pytest.raises(
        submit.PowerCalibrationSubmissionError,
        match="registration caller changed",
    ):
        terminal_registrar(
            terminal,
            plan=object(),
            launch=object(),
            permit=object(),
            review_claim=object(),
            owner_signature=object(),
        )


@pytest.mark.parametrize(
    ("value_type", "registry_name", "require_name"),
    (
        (
            bridge.AcceptedRiskPowerCalibrationInput,
            "_INPUTS",
            "require_accepted_risk_power_calibration_input",
        ),
        (
            bridge.AcceptedRiskPowerCalibrationOutput,
            "_OUTPUTS",
            "require_accepted_risk_power_calibration_output",
        ),
        (
            bridge.AcceptedRiskPowerCalibrationReceipt,
            "_RECEIPTS",
            "require_accepted_risk_power_calibration_receipt",
        ),
        (
            bridge.AcceptedRiskStockPowerSuccessor,
            "_SUCCESSORS",
            "require_accepted_risk_stock_power_successor",
        ),
        (
            bridge.PowerCalibrationQcTerminalReceipt,
            "_QC_TERMINALS",
            "require_power_calibration_qc_terminal_receipt",
        ),
        (
            bridge.AuthenticatedFormalTestPowerCensus,
            "_FORMAL_CENSUSES",
            "require_authenticated_formal_test_power_census",
        ),
        (
            bridge.AuthenticatedPowerFloorBinding,
            "_POWER_FLOORS",
            "require_authenticated_power_floor_binding",
        ),
    ),
)
def test_public_power_registry_injection_cannot_mint_authority(
    value_type: type, registry_name: str, require_name: str,
) -> None:
    value = object.__new__(value_type)
    registry = getattr(bridge, registry_name)
    registry[id(value)] = (weakref.ref(value), b"caller-composed", os.getpid())
    with pytest.raises(bridge.AcceptedRiskPowerCalibrationError):
        getattr(bridge, require_name)(value)
    assert id(value) not in registry


def test_copying_a_legitimate_public_successor_entry_revokes_not_reseals(
    authenticated_power_floor,
) -> None:
    successor = authenticated_power_floor[2]
    original = bridge._SUCCESSORS[id(successor)]
    bridge._SUCCESSORS[id(successor)] = tuple(item for item in original)
    assert bridge._SUCCESSORS[id(successor)] is not original
    with pytest.raises(bridge.AcceptedRiskPowerCalibrationError, match="authority"):
        bridge.require_accepted_risk_stock_power_successor(successor)
    assert id(successor) not in bridge._SUCCESSORS


def test_copying_a_builder_derived_receipt_entry_revokes_not_reseals(
    monkeypatch,
) -> None:
    class Parent:
        pass

    protocol = Parent()
    protocol.protocol_id = "power-protocol"
    protocol.protocol_hash = "1" * 64
    output = Parent()
    output.protocol_id = protocol.protocol_id
    output.protocol_sha256 = protocol.protocol_hash
    output.output_id = "power-output"
    output.output_sha256 = "2" * 64
    output.valid_date_count = bridge.CALIBRATION_SESSION_COUNT
    output.records = tuple(
        types.SimpleNamespace(
            state=bridge.CalibrationBetaState.VALID,
            beta_value=Decimal((index % 17) + 1) / Decimal(1000),
            decision_session=session,
            connected_component_count=20,
        )
        for index, session in enumerate(bridge.calibration_axis())
    )
    provisional = types.SimpleNamespace(
        q05_components_per_date=20,
        raw_required_valid_dates=50,
        required_valid_dates=50,
        required_connected_components=1000,
        disposition=(
            ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
        ),
    )
    monkeypatch.setattr(
        bridge, "require_loaded_power_calibration_protocol", lambda value: value
    )
    monkeypatch.setattr(
        bridge, "require_accepted_risk_power_calibration_output", lambda value: value
    )
    monkeypatch.setattr(
        bridge, "derive_provisional_power_requirement", lambda *_args, **_kwargs: provisional
    )
    receipt = bridge.compute_accepted_risk_power_calibration_receipt(
        protocol=protocol,
        output=output,
        accepted_risk_policy_id="accepted-risk-test",
    )
    original = bridge._RECEIPTS[id(receipt)]
    bridge._RECEIPTS[id(receipt)] = tuple(item for item in original)
    assert bridge._RECEIPTS[id(receipt)] is not original
    with pytest.raises(bridge.AcceptedRiskPowerCalibrationError, match="authority"):
        bridge.require_accepted_risk_power_calibration_receipt(receipt)
    assert id(receipt) not in bridge._RECEIPTS
