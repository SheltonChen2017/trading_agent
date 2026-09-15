from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import os
import sys
import types
import base64
import weakref
from pathlib import Path

import pytest
import research.analyst_revisions_v2_qc.preopen_control_stage as stage_module
import research.analyst_revisions_v2_qc.preopen_quality_worker as quality_module
import research.analyst_revisions_v2_qc.preopen_control_submission_adapter as submission
import research.analyst_revisions_v2_qc.formal_qc_transport as transport_module
import research.analyst_revisions_v2.preopen_control_acquisition as acquisition_core
import research.analyst_revisions_v2_qc.preopen_control_acquisition_io as acquisition_io

from research.analyst_revisions_v2.preopen_control_acquisition import (
    CONTRACT_SHA256,
    CONTROL_SESSION_COMMITMENT_SCHEMA,
    REVIEW_RECEIPT_SCHEMA,
    UNIVERSE_SESSION_COMMITMENT_SCHEMA,
    PreopenControlAcquisitionError,
    acquisition_qc_sid_mapping_binding_record,
    acquisition_q_data_measurement_projection_record,
    acquisition_receipt_artifact_binding_record,
    load_reviewed_preopen_control_acquisition_receipt,
    require_reviewed_preopen_control_acquisition_receipt,
)
from research.analyst_revisions_v2_qc.preopen_control_acquisition_io import (
    PreopenControlAcquisitionIoError,
    load_physically_reviewed_preopen_control_acquisition_receipt,
    render_preopen_control_external_review_pin_candidate,
    render_preopen_qc_execution_receipt,
)
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    EARNINGS_INPUT_SCHEMA,
    FUNDAMENTAL_INPUT_SCHEMA,
    GUIDANCE_INPUT_SCHEMA,
    RATING_INPUT_SCHEMA,
    SID_MAPPING_INPUT_SCHEMA,
    UNIVERSE_INPUT_SCHEMA,
    activate_preopen_input_manifest_bytes,
    build_preopen_control_qc_projection,
    build_preopen_input_manifest_bytes,
    build_preopen_input_shard,
    build_preopen_output_manifest_bytes,
    build_preopen_output_shard,
    canonical_json_bytes,
    load_preopen_control_run_authority,
    normalize_lean_bar_end_utc_text,
    render_preopen_control_run_authority_candidate,
)


_PRODUCTION_PREOPEN_ACTIONS = {
    name: getattr(submission, name)
    for name in (
        "execute_preopen_qc_submission_once",
        "inspect_preopen_qc_terminal_status",
        "retrieve_preopen_qc_terminal_package",
        "download_and_load_preopen_qc_terminal_archive",
    )
}


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


def _closure_value(function, name: str):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    return cells[name].cell_contents


def _offline_owner_signature() -> OwnerSignatureAuthority:
    value = object.__new__(OwnerSignatureAuthority)
    object.__setattr__(value, "authority_sha256", "a" * 64)
    return value


_OFFLINE_PREOPEN_AUTHORITIES: dict[
    int, tuple[int, tuple[object, tuple[object, ...]]]
] = {}


def _offline_preopen_requirer(value):
    record = _OFFLINE_PREOPEN_AUTHORITIES.get(id(value))
    authority = None if record is None or record[0] != os.getpid() else record[1]
    production_cells = dict(zip(
        require_reviewed_preopen_control_acquisition_receipt.__code__.co_freevars,
        require_reviewed_preopen_control_acquisition_receipt.__closure__,
        strict=True,
    ))
    return production_cells["require_implementation"].cell_contents(
        value,
        authority,
    )


def _offline_signed_acquisition_loader():
    """Exercise physical validation but mint only test-local receipt authority."""

    def require_typed_owner_signature(value, *, authority_payload):
        assert type(value) is OwnerSignatureAuthority
        assert type(authority_payload) is bytes and authority_payload
        return value

    production_loader = load_physically_reviewed_preopen_control_acquisition_receipt
    loader_cells = dict(zip(
        production_loader.__code__.co_freevars,
        production_loader.__closure__,
        strict=True,
    ))
    implementation = loader_cells["implementation"].cell_contents
    production_minter = loader_cells["receipt_minter"].cell_contents
    minter_cells = dict(zip(
        production_minter.__code__.co_freevars,
        production_minter.__closure__,
        strict=True,
    ))
    raw_mint = minter_cells["mint_implementation"].cell_contents
    fingerprint = minter_cells["fingerprint"].cell_contents

    def load(**kwargs):
        verified = implementation(
            **kwargs,
            require_owner_signature=require_typed_owner_signature,
        )
        value = raw_mint(
            output_manifest_bytes=verified[0],
            independent_review_receipt_bytes=verified[1],
            qc_execution_receipt_id=verified[2],
            qc_execution_receipt_sha256=verified[3],
            external_review_pin_id=verified[4],
            external_review_pin_sha256=verified[5],
            output_shard_payload_projection_sha256=verified[6],
        )
        reference = weakref.ref(
            value,
            lambda _ref, key=id(value): _OFFLINE_PREOPEN_AUTHORITIES.pop(
                key, None
            ),
        )
        _OFFLINE_PREOPEN_AUTHORITIES[id(value)] = (
            os.getpid(),
            (reference, fingerprint(value)),
        )
        return _offline_preopen_requirer(value)

    return load


@pytest.mark.parametrize(
    "name",
    (
        "_transport_capability_minter",
        "_execute_preopen_qc_submission_once_impl",
        "_inspect_preopen_qc_terminal_status_impl",
        "_retrieve_preopen_qc_terminal_package_impl",
        "_download_and_load_preopen_qc_terminal_archive_impl",
        "_bind_transport_capability_consumers",
    ),
)
def test_preopen_transport_authority_primitives_are_not_module_addressable(name):
    assert not hasattr(submission, name)


def test_reflected_preopen_transport_minter_cannot_self_mint():
    function = submission.execute_preopen_qc_submission_once
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    with pytest.raises(
        submission.formal.FormalQcSubmissionError,
        match="caller changed",
    ):
        cells["minter"].cell_contents(
            transport=object(),
            scope="result_read",
            binding_record={"schema": "forbidden"},
            call_budget={"backtests/read": 1},
        )


ROOT = Path(__file__).resolve().parents[2]
REAL_PREOPEN_EXECUTION_TRUST_GATE = submission._require_external_execution_trust_root
WORKER_PATH = (
    ROOT / "research" / "analyst_revisions_v2_qc" / "preopen_control_worker.py"
)
QUALITY_WORKER_PATH = (
    ROOT / "research" / "analyst_revisions_v2_qc" / "preopen_quality_worker.py"
)
RUNTIME_PATH = (
    ROOT / "research" / "analyst_revisions_v2_qc" / "preopen_control_runtime.py"
)
SHA = "a" * 64
OPEN = "2021-01-04T14:30:00.000000Z"
OBSERVED = "2021-01-04T14:29:00.000000Z"


def _q_data_measurement(
    security_id: str = "sid-one", session: str = "2021-01-04",
) -> dict[str, object]:
    components = []
    for index, (kind, value) in enumerate((
        ("timestamp_quality", "0.8"),
        ("firm_label_mapping_quality", "0.9"),
        ("security_entity_mapping_quality", "0.95"),
    )):
        component = {
            "kind": kind, "value": value,
            "source_id": f"quality-source-{index}",
            "source_sha256": hashlib.sha256(f"source-{index}".encode()).hexdigest(),
            "payload_sha256": hashlib.sha256(f"payload-{index}".encode()).hexdigest(),
            "available_at": "2021-01-04T13:00:00.000000Z",
            "point_in_time": index != 0,
            "accepted_risk_non_pristine": index == 0,
        }
        component["evidence_sha256"] = hashlib.sha256(
            canonical_json_bytes(component)
        ).hexdigest()
        components.append(component)
    result = {
        "security_id": security_id, "measured_session": session,
        "source_id": "quality-aggregate-source",
        "source_sha256": hashlib.sha256(b"quality-aggregate-source").hexdigest(),
        "components": components,
        "measurement_method_id": "arv2-qdata-conservative-min-v1",
        "q_data": "0.8", "available_at": "2021-01-04T13:00:00.000000Z",
        "point_in_time": True,
    }
    result["evidence_sha256"] = hashlib.sha256(
        canonical_json_bytes(result)
    ).hexdigest()
    return result


def _sid_mapping_row(
    *, security_id: str = "sid-one", issuer_id: str = "sharadar-permaticker-1",
    share_class_id: str = "figi-one", listing_id: str = "listing-one",
    historical_ticker: str = "ONE", qc_security_id: str = "qc-sid-one",
    cusip: str | None = None,
) -> dict[str, object]:
    cusip = cusip or hashlib.sha256(security_id.encode()).hexdigest()[:9].upper()
    row = {
        "schema": SID_MAPPING_INPUT_SCHEMA,
        "security_id": security_id,
        "qc_security_id": qc_security_id,
        "cusip": cusip,
        "issuer_id": issuer_id,
        "share_class_id": share_class_id,
        "listing_id": listing_id,
        "historical_ticker": historical_ticker,
        "first_session": "2021-01-04",
        "last_session": "2021-01-04",
        "available_at": "2021-01-04T13:00:00.000000Z",
        "security_master_artifact_id": "source-security_master",
        "security_master_artifact_sha256": SHA,
        "mapping_status": "reviewed_qc_fundamental_discovery_exact_cusip_join",
        "qc_discovery_terminal_sha256": hashlib.sha256(
            f"discovery-{security_id}".encode()
        ).hexdigest(),
        "current_ticker_matches": True,
        "ticker_interval_evidence_sha256": hashlib.sha256(
            f"interval-{security_id}".encode()
        ).hexdigest(),
        "source_row_sha256": hashlib.sha256(
            f"source-{security_id}".encode()
        ).hexdigest(),
    }
    row["row_sha256"] = hashlib.sha256(canonical_json_bytes(row)).hexdigest()
    return row


def _seed() -> dict[str, object]:
    measurement = _q_data_measurement()
    return {
        "schema": UNIVERSE_INPUT_SCHEMA,
        "disposition": "accepted",
        "decision_session": "2021-01-04",
        "decision_session_ordinal": 1000,
        "decision_open_utc": OPEN,
        "security_id": "sid-one",
        "qc_security_id": "qc-sid-one",
        "issuer_id": "sharadar-permaticker-1",
        "share_class_id": "figi-one",
        "listing_id": "listing-one",
        "historical_ticker": "ONE",
        "sector_id": "technology",
        "industry_id": "software",
        "security_master_row_sha256": SHA,
        "qc_sid_mapping_row_sha256": _sid_mapping_row()["row_sha256"],
        "q_data": "0.8",
        "source_id": "universe-source-1",
        "source_sha256": SHA,
        "identity_evidence_sha256": "b" * 64,
        "identity_available_at": "2021-01-04T13:00:00.000000Z",
        "classification_evidence_sha256": "c" * 64,
        "classification_available_at": "2021-01-04T13:00:00.000000Z",
        "q_data_evidence_sha256": measurement["evidence_sha256"],
        "q_data_available_at": "2021-01-04T13:00:00.000000Z",
        "q_data_measurement": measurement,
    }


def _market() -> list[dict[str, object]]:
    rows = []
    for offset in range(253):
        available = f"2020-01-{1 + offset % 28:02d}T22:00:00.000000Z"
        rows.extend(
            [
                {
                    "schema": "arv2-preopen-control-market-observation-v1",
                    "security_id": "sid-one",
                    "kind": "total_return",
                    "session_ordinal": 700 + offset,
                    "available_at": available,
                    "close": str(100 + offset),
                    "volume": None,
                },
                {
                    "schema": "arv2-preopen-control-market-observation-v1",
                    "security_id": "spy-sid",
                    "kind": "benchmark_total_return",
                    "session_ordinal": 700 + offset,
                    "available_at": available,
                    "close": str(200 + offset * 2 + (offset % 3)),
                    "volume": None,
                },
            ]
        )
        if offset >= 193:
            rows.append(
                {
                    "schema": "arv2-preopen-control-market-observation-v1",
                    "security_id": "sid-one",
                    "kind": "raw",
                    "session_ordinal": 700 + offset,
                    "available_at": available,
                    "close": str(50 + offset),
                    "volume": str(1_000_000 + offset),
                }
            )
    return rows


def _worker():
    sys.modules["preopen_quality_worker"] = quality_module
    source = WORKER_PATH.read_text(encoding="utf-8").replace(
        "__ARV2_PREOPEN_CONTROL_CONTRACT_SHA256__", CONTRACT_SHA256
    )
    namespace: dict[str, object] = {}
    exec(compile(source, str(WORKER_PATH), "exec"), namespace)
    return namespace


def _worker_inputs() -> dict[str, object]:
    worker = _worker()
    market_rows = _market()
    market_summaries, market_lineages = worker[
        "build_market_control_summaries"
    ](
        universe_rows=[_seed()],
        stock_market_rows=[
            row for row in market_rows if row["security_id"] == "sid-one"
        ],
        benchmark_market_rows=[
            row for row in market_rows if row["security_id"] == "spy-sid"
        ],
        benchmark_security_id="spy-sid",
    )
    inputs = {
        "universe_rows": [_seed()],
        "market_control_summaries": market_summaries,
        "market_lineages": market_lineages,
        "benchmark_security_id": "spy-sid",
        "fundamental_rows": [
            {
                "schema": FUNDAMENTAL_INPUT_SCHEMA,
                "security_id": "sid-one",
                "period_end": "2020-09-30",
                "available_at": "2020-11-01T13:00:00.000000Z",
                "shares_outstanding": "10000000",
                "book_equity_usd": "500000000",
                "revenue_ttm_usd": "1200000000",
                "prior_fiscal_year_revenue_ttm_usd": "1000000000",
            }
        ],
        "earnings_rows": [
            {
                "schema": EARNINGS_INPUT_SCHEMA,
                "security_id": "sid-one",
                "report_session_ordinal": 998,
                "available_at": "2020-12-31T12:00:00.000000Z",
            }
        ],
        "guidance_rows": [
            {
                "schema": GUIDANCE_INPUT_SCHEMA,
                "security_id": "sid-one",
                "eligible_session_ordinal": 999,
                "available_at": "2021-01-04T13:00:00.000000Z",
            }
        ],
        "rating_rows": [
            {
                "schema": RATING_INPUT_SCHEMA,
                "security_id": "sid-one",
                "source_view_id": (
                    "conservative_censored_current_vintage_non_pristine_pit"
                ),
                "admitted": True,
                "eligible_session_ordinal": 990,
                "available_at": "2020-12-15T15:00:00.000000Z",
                "analyst_id": "analyst-one",
                "institution_id": "firm-one",
                "common_event_id": "common-one",
            }
        ],
        "observed_at_utc": OBSERVED,
        "rating_source_complete": True,
        "earnings_source_complete": True,
        "guidance_source_complete": True,
        "input_roots": {},
    }
    inputs["input_roots"] = {
        "universe": SHA,
        "sid_mapping": "f" * 64,
        "fundamentals": "b" * 64,
        "earnings": "c" * 64,
        "guidance": "d" * 64,
        "ratings": "e" * 64,
        "market_observations": hashlib.sha256(canonical_json_bytes(
            sorted(inputs["market_lineages"], key=canonical_json_bytes)
        )).hexdigest(),
    }
    return inputs


def test_worker_builds_exact_25_control_scoring_ready_terminal():
    inputs = _worker_inputs()
    terminal = _worker()["build_session_terminals"](**inputs)[0]
    assert terminal["disposition"] == "accepted"
    eligible = terminal["eligible_security_session"]
    assert [item[0] for item in eligible["controls"]] == list(
        _worker()["CONTROL_NAMES"]
    )
    assert len(eligible["controls"]) == 25
    assert eligible["controls"][-5][1] == 1
    assert eligible["controls"][-1][1] == 1
    assert eligible["control_available_at"] < OPEN
    assert eligible["earnings_anchor_signed_session_distance"] == 2
    assert eligible["security_id"] == "sid-one"
    assert terminal["qc_security_id"] == "qc-sid-one"
    assert eligible["issuer_id"] == "sharadar-permaticker-1"
    assert eligible["control_vector_sha256"] == hashlib.sha256(
        canonical_json_bytes(eligible["controls"])
    ).hexdigest()


def test_worker_report_earnings_anchor_uses_nearest_with_earlier_tie_break():
    inputs = _worker_inputs()
    inputs["earnings_rows"] = [
        *inputs["earnings_rows"],
        {
            "schema": EARNINGS_INPUT_SCHEMA,
            "security_id": "sid-one",
            "report_session_ordinal": 1002,
            "available_at": "2020-12-31T15:00:00.000000Z",
        },
    ]
    terminal = _worker()["build_session_terminals"](**inputs)[0]
    eligible = terminal["eligible_security_session"]
    # Both reports are two sessions away; the earlier report wins and the
    # signed distance is positive after earnings.
    assert eligible["earnings_anchor_signed_session_distance"] == 2
    controls = dict(eligible["controls"])
    # Model controls retain their separately frozen future-first anchor.
    assert controls["pre_earnings"] == 1


def test_worker_future_rows_cannot_change_prior_preopen_terminal():
    worker = _worker()["build_session_terminals"]
    inputs = _worker_inputs()
    original = worker(**inputs)
    later = dict(inputs)
    later["fundamental_rows"] = [
        *inputs["fundamental_rows"],
        {
            "schema": FUNDAMENTAL_INPUT_SCHEMA,
            "security_id": "sid-one",
            "period_end": "2020-12-31",
            "available_at": "2021-01-04T15:00:00.000000Z",
            "shares_outstanding": "1",
            "book_equity_usd": "1",
            "revenue_ttm_usd": "1",
            "prior_fiscal_year_revenue_ttm_usd": "1",
        },
    ]
    later["earnings_rows"] = [
        *inputs["earnings_rows"],
        {
            "schema": EARNINGS_INPUT_SCHEMA,
            "security_id": "sid-one",
            "report_session_ordinal": 1000,
            "available_at": "2021-01-04T15:00:00.000000Z",
        },
    ]
    assert worker(**later) == original


def test_worker_unknown_guidance_or_earnings_is_refusal_never_zero():
    worker = _worker()["build_session_terminals"]
    for gate, reason in (
        ("guidance_source_complete", "missing_or_unresolved_guidance_input"),
        ("earnings_source_complete", "missing_or_incomplete_earnings_archive"),
    ):
        inputs = _worker_inputs()
        inputs[gate] = False
        terminal = worker(**inputs)[0]
        assert terminal["disposition"] == "named_refusal"
        assert terminal["detail_reason"] == reason
        assert terminal["eligible_security_session"] is None


def test_worker_refuses_post_open_callback_and_accepts_distinct_logical_and_qc_ids():
    worker = _worker()["build_session_terminals"]
    inputs = _worker_inputs()
    inputs["observed_at_utc"] = OPEN
    with pytest.raises(ValueError, match="strictly pre-open"):
        worker(**inputs)
    inputs = _worker_inputs()
    inputs["universe_rows"] = [{**_seed(), "qc_security_id": "different-sid"}]
    terminal = worker(**inputs)[0]
    assert terminal["disposition"] == "accepted"
    assert terminal["qc_security_id"] == "different-sid"


def _input_shards():
    roles = {
        "universe": [_seed()],
        "sid_mapping": [_sid_mapping_row()],
        "fundamentals": [
            {"schema": FUNDAMENTAL_INPUT_SCHEMA, "security_id": "sid-one"}
        ],
        "earnings": [{"schema": EARNINGS_INPUT_SCHEMA, "security_id": "sid-one"}],
        "guidance": [{"schema": GUIDANCE_INPUT_SCHEMA, "security_id": "sid-one"}],
        "ratings": [{"schema": RATING_INPUT_SCHEMA, "security_id": "sid-one"}],
    }
    return tuple(
        build_preopen_input_shard(
            role=role, security_batch_ordinal=0, ordinal=0,
            partition_first_session="2021-01-04",
            partition_last_session="2021-01-04", rows=rows,
        )
        for role, rows in roles.items()
    )


def _truth_source_bindings():
    kinds = (
        "accepted_risk_capture", "eligible_universe", "security_master",
        "firm_ontology", "common_event", "sector_classification",
        "preopen_control", "data_quality",
    )
    return tuple({
        "kind": kind,
        "artifact_id": "universe-source-1" if kind == "eligible_universe"
        else "source-" + kind,
        "artifact_sha256": SHA,
    } for kind in kinds)


def _input_manifest(*, guidance_complete: bool = True) -> bytes:
    return build_preopen_input_manifest_bytes(
        shards=_input_shards(),
        benchmark_security_id="spy-sid",
        benchmark_ticker="SPY",
        first_session="2021-01-04",
        last_session="2021-01-04",
        calculation_session="2026-09-10",
        rating_source_complete=True,
        earnings_source_complete=True,
        guidance_source_complete=guidance_complete,
        earnings_pit_policy_id="owner-accepted-current-row-risk-v1",
        guidance_clock_policy_id=(
            "massive_guidance_date_only_three_session_lag_prior_date_censor-v1"
            if guidance_complete
            else "unresolved-guidance-clock-refusal-v1"
        ),
        eligible_universe_artifact_id="universe-source-1",
        eligible_universe_artifact_sha256=SHA,
        eligible_universe_artifact_byte_count=123,
        truth_source_bindings=_truth_source_bindings(),
    )


def _activated_manifest(tmp_path):
    closed = _input_manifest()
    candidate = json.loads(render_preopen_control_run_authority_candidate(closed))
    candidate["status"] = (
        "independently_reviewed_private_preopen_construction_authority"
    )
    candidate["target_qc_capacity_reviewed"] = True
    candidate["qc_sid_mapping_reviewed"] = True
    seed = dict(candidate)
    seed["pin_id"] = None
    seed["pin_sha256"] = None
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    candidate["pin_id"] = f"arv2-preopen-run-authority-{digest[:24]}"
    candidate["pin_sha256"] = digest
    pin_path = tmp_path / "preopen-run-authority.json"
    pin_path.write_bytes(canonical_json_bytes(candidate))
    pin_path.chmod(0o600)
    authority = load_preopen_control_run_authority(closed, pin_path)
    return activate_preopen_input_manifest_bytes(closed, authority), authority


def test_public_run_candidate_cannot_self_authorize(tmp_path):
    closed = _input_manifest()
    pin_path = tmp_path / "unreviewed-run-candidate.json"
    pin_path.write_bytes(render_preopen_control_run_authority_candidate(closed))
    pin_path.chmod(0o600)
    with pytest.raises(
        stage_module.PreopenControlStageError,
        match="independent private review",
    ):
        load_preopen_control_run_authority(closed, pin_path)


def test_projection_is_content_addressed_small_and_has_no_forbidden_api_calls(tmp_path):
    manifest_bytes, authority = _activated_manifest(tmp_path)
    projection = build_preopen_control_qc_projection(
        input_manifest_bytes=manifest_bytes,
        worker_source_bytes=WORKER_PATH.read_bytes(),
        quality_worker_source_bytes=QUALITY_WORKER_PATH.read_bytes(),
        runtime_source_bytes=RUNTIME_PATH.read_bytes(),
        run_authority=authority,
    )
    assert len(projection.source_files) == 4
    assert all(item.character_count < 60_000 for item in projection.source_files)
    assert projection.places_orders is projection.reads_outcomes_or_results is False
    assert projection.requires_separate_reviewed_run_authority is True
    assert CONTRACT_SHA256.encode() in projection.source_files[1].content
    forbidden = {
        "market_order", "set_holdings", "liquidate", "order", "debug", "log",
        "read_backtest", "result", "portfolio",
    }
    for source in projection.source_files:
        tree = ast.parse(source.content.decode("utf-8"))
        names = {
            node.attr.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        assert not (names & forbidden)
    entry = projection.source_files[0].content.decode("utf-8")
    runtime = projection.source_files[3].content.decode("utf-8")
    assert "DataNormalizationMode.TOTAL_RETURN" in runtime
    assert "DataNormalizationMode.RAW" in runtime
    assert "future bar escaped full-sample history bound" in runtime
    assert "set_summary_statistic" in runtime
    initialize = next(
        node for node in ast.walk(ast.parse(entry))
        if isinstance(node, ast.FunctionDef) and node.name == "initialize"
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr.lower() == "history"
        for node in ast.walk(initialize)
    )
    assert "algorithm.history[TradeBar](" in runtime
    manifest = json.loads(manifest_bytes)
    census = manifest["resource_census"]
    assert census["projected_batched_history_call_count"] == 5
    assert census["maximum_buffered_market_observation_count"] < 250_000
    assert census["full_terminal_set_retained_in_memory"] is False
    assert census["qc_runtime_full_input_set_retained_in_memory"] is False
    assert census["projected_total_market_observation_count"] <= (
        census["maximum_projected_market_observation_count"]
    )
    assert census["projected_output_uncompressed_byte_upper_bound"] <= (
        census["maximum_projected_output_uncompressed_bytes"]
    )
    run_authority = manifest["construction_gate"][
        "external_private_run_authority"
    ]
    assert run_authority["target_qc_capacity_reviewed"] is True
    assert run_authority["qc_sid_mapping_reviewed"] is True


def test_lean_naive_bar_end_uses_new_york_winter_and_summer_offsets():
    from datetime import datetime

    assert normalize_lean_bar_end_utc_text(
        datetime(2021, 1, 4, 16, 0)
    ) == "2021-01-04T21:00:00.000000Z"
    assert normalize_lean_bar_end_utc_text(
        datetime(2021, 7, 6, 16, 0)
    ) == "2021-07-06T20:00:00.000000Z"


def test_projected_lean_history_localizes_naive_equity_bar_end(
    monkeypatch, tmp_path
):
    from datetime import datetime, timezone

    manifest_bytes, authority = _activated_manifest(tmp_path)
    projection = build_preopen_control_qc_projection(
        input_manifest_bytes=manifest_bytes,
        worker_source_bytes=WORKER_PATH.read_bytes(),
        quality_worker_source_bytes=QUALITY_WORKER_PATH.read_bytes(),
        runtime_source_bytes=RUNTIME_PATH.read_bytes(),
        run_authority=authority,
    )
    imports = types.ModuleType("AlgorithmImports")
    imports.QCAlgorithm = type("QCAlgorithm", (), {})
    imports.TradeBar = type("TradeBar", (), {})
    imports.DataNormalizationMode = types.SimpleNamespace(
        TOTAL_RETURN="total-return", RAW="raw"
    )
    imports.Resolution = types.SimpleNamespace(DAILY="daily")
    imports.TimeZones = types.SimpleNamespace(NEW_YORK="New York")
    monkeypatch.setitem(sys.modules, "AlgorithmImports", imports)
    quality_worker_module = types.ModuleType("preopen_quality_worker")
    exec(projection.source_files[2].content, quality_worker_module.__dict__)
    monkeypatch.setitem(sys.modules, "preopen_quality_worker", quality_worker_module)
    worker_module = types.ModuleType("preopen_control_worker")
    exec(projection.source_files[1].content, worker_module.__dict__)
    monkeypatch.setitem(sys.modules, "preopen_control_worker", worker_module)
    runtime_module = types.ModuleType("preopen_control_runtime")
    exec(projection.source_files[3].content, runtime_module.__dict__)
    monkeypatch.setitem(sys.modules, "preopen_control_runtime", runtime_module)
    namespace: dict[str, object] = {}
    exec(projection.source_files[0].content, namespace)

    class History:
        def __getitem__(self, _kind):
            return lambda *_args, **_kwargs: [
                types.SimpleNamespace(
                    symbol=types.SimpleNamespace(id="sid-one"),
                    end_time=datetime(2021, 1, 4, 16, 0),
                    close=101,
                    volume=1234,
                )
            ]

    algorithm = object.__new__(
        namespace["AnalystRevisionsV2PreopenControlConstruction"]
    )
    algorithm.history = History()
    rows = runtime_module._history_rows(
        algorithm,
        [object()],
        datetime(2020, 12, 1, tzinfo=timezone.utc),
        datetime(2021, 1, 5, tzinfo=timezone.utc),
        "raw",
        "raw",
    )
    assert rows[0]["available_at"] == "2021-01-04T21:00:00.000000Z"
    assert rows[0]["volume"] == "1234"


def test_five_thousand_security_universe_streams_bounded_market_batches():
    universe = []
    sid_mappings = []
    for index in range(5_001):
        security_id = f"sid-{index:04d}"
        mapping = _sid_mapping_row(
            security_id=security_id,
            issuer_id=f"permaticker-{index:04d}",
            share_class_id=f"figi-{index:04d}",
            listing_id=f"listing-{index:04d}",
            qc_security_id=f"qc-sid-{index:04d}",
        )
        sid_mappings.append(mapping)
        measurement = _q_data_measurement(security_id)
        universe.append({
            **_seed(),
            "security_id": security_id,
            "qc_security_id": f"qc-sid-{index:04d}",
            "issuer_id": f"permaticker-{index:04d}",
            "share_class_id": f"figi-{index:04d}",
            "listing_id": f"listing-{index:04d}",
            "qc_sid_mapping_row_sha256": mapping["row_sha256"],
            "q_data_measurement": measurement,
            "q_data_evidence_sha256": measurement["evidence_sha256"],
        })
    shards = []
    for batch, offset in enumerate(range(0, len(universe), 48)):
        rows_by_role = {
            "universe": universe[offset:offset + 48],
            "sid_mapping": sid_mappings[offset:offset + 48],
            "fundamentals": [], "earnings": [], "guidance": [], "ratings": [],
        }
        shards.extend(
            build_preopen_input_shard(
                role=role, security_batch_ordinal=batch, ordinal=0,
                partition_first_session="2021-01-04",
                partition_last_session="2021-01-04", rows=rows,
            )
            for role, rows in rows_by_role.items()
        )
    manifest = json.loads(build_preopen_input_manifest_bytes(
        shards=tuple(shards),
        benchmark_security_id="spy-sid",
        benchmark_ticker="SPY",
        first_session="2021-01-04",
        last_session="2021-01-04",
        calculation_session="2026-09-10",
        rating_source_complete=True,
        earnings_source_complete=True,
        guidance_source_complete=True,
        earnings_pit_policy_id="owner-accepted-current-row-risk-v1",
        guidance_clock_policy_id=(
            "massive_guidance_date_only_three_session_lag_prior_date_censor-v1"
        ),
        eligible_universe_artifact_id="universe-source-1",
        eligible_universe_artifact_sha256=SHA,
        eligible_universe_artifact_byte_count=123,
        truth_source_bindings=_truth_source_bindings(),
    ))
    census = manifest["resource_census"]
    assert census["security_batch_count"] == 105
    assert census["projected_batched_history_call_count"] == 421
    assert census["projected_total_market_observation_count"] == (
        5_001 * 4 * 431 + 431
    )
    assert census["maximum_buffered_market_observation_count"] == 97 * 431
    assert census["maximum_derived_market_summary_count"] == 48
    assert census["maximum_logical_merge_cursor_count"] == 105
    assert census["peer_group_state_count"] == 2
    assert census["projected_output_shard_count"] == 105


def test_total_repeated_history_and_output_storage_bounds_are_load_bearing(
    monkeypatch,
):
    monkeypatch.setattr(stage_module, "MAX_PROJECTED_MARKET_OBSERVATION_COUNT", 1)
    with pytest.raises(stage_module.PreopenControlStageError, match="repeated-history"):
        _input_manifest()
    monkeypatch.setattr(
        stage_module, "MAX_PROJECTED_MARKET_OBSERVATION_COUNT", 100_000_000
    )
    monkeypatch.setattr(stage_module, "MAX_PROJECTED_OUTPUT_UNCOMPRESSED_BYTES", 1)
    with pytest.raises(stage_module.PreopenControlStageError, match="output storage"):
        _input_manifest()


def test_qc_sid_mapping_artifact_census_is_not_a_row_assertion():
    shards = list(_input_shards())
    mapping_index = next(
        index for index, shard in enumerate(shards) if shard.role == "sid_mapping"
    )
    shards[mapping_index] = build_preopen_input_shard(
        role="sid_mapping", security_batch_ordinal=0, ordinal=0,
        partition_first_session="2021-01-04",
        partition_last_session="2021-01-04", rows=[],
    )
    kwargs = {
            "shards": tuple(shards),
            "benchmark_security_id": "spy-sid",
            "benchmark_ticker": "SPY",
        "first_session": "2021-01-04",
        "last_session": "2021-01-04",
        "calculation_session": "2026-09-10",
        "rating_source_complete": True,
        "earnings_source_complete": True,
        "guidance_source_complete": True,
        "earnings_pit_policy_id": "owner-accepted-current-row-risk-v1",
        "guidance_clock_policy_id": (
            "massive_guidance_date_only_three_session_lag_prior_date_censor-v1"
        ),
        "eligible_universe_artifact_id": "universe-source-1",
        "eligible_universe_artifact_sha256": SHA,
        "eligible_universe_artifact_byte_count": 123,
        "truth_source_bindings": _truth_source_bindings(),
    }
    with pytest.raises(stage_module.PreopenControlStageError, match="lacks its canonical"):
        build_preopen_input_manifest_bytes(**kwargs)


def _reviewed_receipt(tmp_path, monkeypatch=None):
    inputs, authority = _activated_manifest(tmp_path)
    terminal = _worker()["build_session_terminals"](**_worker_inputs())[0]
    shard = build_preopen_output_shard(ordinal=0, terminal_rows=[terminal])
    projection = build_preopen_control_qc_projection(
        input_manifest_bytes=inputs, worker_source_bytes=WORKER_PATH.read_bytes(),
        quality_worker_source_bytes=QUALITY_WORKER_PATH.read_bytes(),
        runtime_source_bytes=RUNTIME_PATH.read_bytes(),
        run_authority=authority,
    )
    leaf = hashlib.sha256(canonical_json_bytes({
        "domain": "arv2-terminal-leaf-v1",
        "record": {
            "terminal": "accepted",
            "value": terminal["eligible_security_session"],
        },
    })).hexdigest()
    control_leaf = hashlib.sha256(canonical_json_bytes({
        "domain": "arv2-terminal-leaf-v1", "record": terminal
    })).hexdigest()
    universe = [{
        "schema": UNIVERSE_SESSION_COMMITMENT_SCHEMA,
        "decision_session": "2021-01-04",
        "accepted_count": 1,
        "refusal_count": 0,
        "terminal_count": 1,
        "terminal_merkle_root": leaf,
    }]
    controls = [{
        "schema": CONTROL_SESSION_COMMITMENT_SCHEMA,
        "decision_session": "2021-01-04",
        "accepted_count": 1,
        "refusal_count": 0,
        "terminal_count": 1,
        "terminal_merkle_root": control_leaf,
        "market_observation_count": len(_market()),
        "market_observation_sha256": terminal["input_roots"][
            "market_observations"
        ],
    }]
    measurement = terminal["q_data_measurement"]
    measurement_projection_sha256 = hashlib.sha256(canonical_json_bytes({
        "schema": "arv2-qdata-physical-measurement-projection-v1",
        "measurements": [measurement],
    })).hexdigest()
    output = build_preopen_output_manifest_bytes(
        input_manifest_bytes=inputs,
        input_manifest_id=projection.input_manifest_id,
        project_source_set_sha256=projection.project_source_set_sha256,
        output_shards=(shard,),
        universe_sessions=universe,
        control_sessions=controls,
        construction_intermediates={
            "schema": (
                "arv2-preopen-control-construction-intermediate-commitment-v1"
            ),
            "peer_aggregate_record_count": 2,
            "peer_aggregate_projection_sha256": "1" * 64,
            "market_session_commitment_count": 1,
            "market_session_projection_sha256": "2" * 64,
            "physical_terminal_shard_count": 1,
            "logical_terminal_order": "decision_session_then_security_id",
            "q_data_measurement_count": 1,
            "q_data_measurement_projection_sha256": (
                measurement_projection_sha256
            ),
        },
    )
    output_hash = hashlib.sha256(output).hexdigest()
    parsed = json.loads(output)
    review = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "output_manifest": {
            "artifact_id": f"arv2-preopen-control-output-{output_hash[:24]}",
            "content_sha256": output_hash,
            "artifact_sha256": output_hash,
            "byte_count": len(output),
        },
        "input_source_inventory_sha256": parsed["input_source_inventory_sha256"],
        "project_source_set_sha256": parsed["project_source_set_sha256"],
        "output_shard_inventory_sha256": parsed["output_shard_inventory_sha256"],
        "universe_terminal_projection_sha256": parsed[
            "universe_terminal_projection_sha256"
        ],
        "control_terminal_projection_sha256": parsed[
            "control_terminal_projection_sha256"
        ],
        "review_receipt_id": None,
        "review_receipt_sha256": None,
        "complete_source_inventory_verified": True,
        "per_session_universe_terminal_completeness_verified": True,
        "control_formula_equivalence_verified": True,
        "strict_preopen_timing_verified": True,
        "no_outcomes_verified": True,
        "object_store_persistence_verified": True,
        "formal_runtime_direct_consumption_verified": True,
    }
    digest = hashlib.sha256(canonical_json_bytes(review)).hexdigest()
    review["review_receipt_id"] = f"arv2-preopen-control-review-{digest[:24]}"
    review["review_receipt_sha256"] = digest
    review_bytes = canonical_json_bytes(review)
    summary = canonical_json_bytes({
        "schema": "arv2-preopen-control-summary-receipt-v1",
        "manifest_sha256": output_hash,
        "manifest_byte_count": len(output),
        "source_set_sha256": projection.project_source_set_sha256,
        "terminal_count": 1,
        "accepted_count": 1,
        "refusal_count": 0,
        "shard_count": 1,
    })
    execution = render_preopen_qc_execution_receipt(
        project_id="qc-project-one", compile_id="qc-compile-one",
        backtest_id="qc-backtest-one",
        input_manifest_sha256=hashlib.sha256(inputs).hexdigest(),
        project_source_set_sha256=projection.project_source_set_sha256,
        output_manifest_sha256=output_hash,
        summary_receipt_sha256=hashlib.sha256(summary).hexdigest(),
    )
    pin = render_preopen_control_external_review_pin_candidate(
        output_manifest_bytes=output, output_shard_payloads=(shard.payload,),
        independent_review_receipt_bytes=review_bytes,
        qc_execution_receipt_bytes=execution, summary_receipt_bytes=summary,
    )
    pin_path = tmp_path / "preopen-acquisition-pin.json"
    pin_path.write_bytes(pin)
    pin_path.chmod(0o600)
    receipt = _offline_signed_acquisition_loader()(
        output_manifest_bytes=output,
        output_shard_payloads=(item for item in (shard.payload,)),
        independent_review_receipt_bytes=review_bytes,
        qc_execution_receipt_bytes=execution, summary_receipt_bytes=summary,
        external_review_pin_path=pin_path,
        owner_signature=_offline_owner_signature(),
    )
    if monkeypatch is not None:
        for module_name in (
            "research.analyst_revisions_v2.preopen_control_acquisition",
            "research.analyst_revisions_v2.production_evidence_acquisition",
            "research.analyst_revisions_v2.production_truth_gate",
            "research.analyst_revisions_v2_qc.formal_input_composer",
            "research.analyst_revisions_v2_qc.formal_streaming_input",
            "research.analyst_revisions_v2_qc.preopen_control_submission_adapter",
            "research.analyst_revisions_v2_qc.production_evidence_composer",
        ):
            target = sys.modules.get(module_name)
            if target is not None and hasattr(
                target,
                "require_reviewed_preopen_control_acquisition_receipt",
            ):
                monkeypatch.setattr(
                    target,
                    "require_reviewed_preopen_control_acquisition_receipt",
                    _offline_preopen_requirer,
                )
    return receipt, {
        "output": output, "review": review_bytes, "payload": shard.payload,
        "execution": execution, "summary": summary, "pin_path": pin_path,
    }


def test_independent_receipt_binds_exact_source_sessions_and_output_shards(
    tmp_path, monkeypatch,
):
    receipt, _ = _reviewed_receipt(tmp_path, monkeypatch)
    assert _offline_preopen_requirer(receipt) is receipt
    with pytest.raises(
        PreopenControlAcquisitionError, match="loader-authenticated"
    ):
        require_reviewed_preopen_control_acquisition_receipt(receipt)
    assert acquisition_receipt_artifact_binding_record(receipt) == {
        "artifact_id": receipt.artifact_id,
        "content_sha256": receipt.content_sha256,
        "artifact_sha256": receipt.artifact_sha256,
        "byte_count": receipt.byte_count,
    }
    sid_mapping = acquisition_qc_sid_mapping_binding_record(receipt)
    assert sid_mapping["artifact_id"].startswith("arv2-qc-sid-mapping-")
    assert sid_mapping["content_sha256"] == sid_mapping["artifact_sha256"]
    assert sid_mapping["byte_count"] > 0
    assert sid_mapping["row_count"] == 1
    quality = acquisition_q_data_measurement_projection_record(receipt)
    assert quality["measurement_count"] == 1
    assert quality["projection_sha256"] == receipt.q_data_measurement_projection_sha256
    copied = copy.copy(receipt)
    with pytest.raises(PreopenControlAcquisitionError, match="loader-authenticated"):
        require_reviewed_preopen_control_acquisition_receipt(copied)


def test_unsigned_or_globally_rebound_review_cannot_mint_acquisition(
    tmp_path, monkeypatch,
):
    _, material = _reviewed_receipt(tmp_path)
    kwargs = {
        "output_manifest_bytes": material["output"],
        "output_shard_payloads": (material["payload"],),
        "independent_review_receipt_bytes": material["review"],
        "qc_execution_receipt_bytes": material["execution"],
        "summary_receipt_bytes": material["summary"],
        "external_review_pin_path": material["pin_path"],
        "owner_signature": None,
    }
    with pytest.raises(
        PreopenControlAcquisitionIoError,
        match="lacks exact owner-signature authority",
    ):
        load_physically_reviewed_preopen_control_acquisition_receipt(**kwargs)

    calls = []
    monkeypatch.setattr(
        acquisition_io,
        "require_preopen_acquisition_review_owner_signature",
        lambda *args, **values: calls.append((args, values)),
        raising=False,
    )
    with pytest.raises(
        PreopenControlAcquisitionIoError,
        match="physical loader authority changed",
    ):
        acquisition_io.load_physically_reviewed_preopen_control_acquisition_receipt(
            **kwargs
        )
    assert calls == []


def test_cloned_preopen_acquisition_loader_cannot_rebind_signature_authority(
    tmp_path, monkeypatch,
):
    _, material = _reviewed_receipt(tmp_path)
    signer_callbacks = []
    read_callbacks = []
    module_callbacks = []

    def require_typed_owner_signature(value, *, authority_payload):
        signer_callbacks.append((value, authority_payload))
        assert type(value) is OwnerSignatureAuthority
        assert type(authority_payload) is bytes and authority_payload
        return value

    production_loader = (
        acquisition_io.load_physically_reviewed_preopen_control_acquisition_receipt
    )
    clone = _with_closure_value(
        production_loader,
        "owner_signature_requirer",
        require_typed_owner_signature,
    )
    kwargs = {
        "output_manifest_bytes": material["output"],
        "output_shard_payloads": (material["payload"],),
        "independent_review_receipt_bytes": material["review"],
        "qc_execution_receipt_bytes": material["execution"],
        "summary_receipt_bytes": material["summary"],
        "external_review_pin_path": material["pin_path"],
        "owner_signature": _offline_owner_signature(),
    }
    loader_cells = dict(zip(
        production_loader.__code__.co_freevars,
        production_loader.__closure__,
        strict=True,
    ))
    minter = loader_cells["receipt_minter"].cell_contents
    minter_cells = dict(zip(
        minter.__code__.co_freevars,
        minter.__closure__,
        strict=True,
    ))
    records_before = minter_cells["records"].cell_contents
    with pytest.raises(
        PreopenControlAcquisitionIoError,
        match="physical loader authority changed",
    ):
        clone(**kwargs)
    assert signer_callbacks == []
    assert minter_cells["records"].cell_contents is records_before

    def unexpected_read(*args, **values):
        read_callbacks.append((args, values))
        raise AssertionError("physical read executed")

    with monkeypatch.context() as patch:
        patch.setattr(acquisition_io, "_read_private", unexpected_read)
        patch.setattr(acquisition_io, "any", lambda _values: False, raising=False)
        patch.setattr(
            acquisition_io,
            "_unexpected_physical_loader_global",
            object(),
            raising=False,
        )
        with pytest.raises(
            PreopenControlAcquisitionIoError,
            match="physical loader authority changed",
        ):
            clone(**kwargs)
    assert signer_callbacks == []
    assert read_callbacks == []
    assert minter_cells["records"].cell_contents is records_before

    class HostileModule:
        def __getattr__(self, name):
            module_callbacks.append(name)
            raise AssertionError("hostile module callback executed")

    monkeypatch.setitem(
        sys.modules,
        production_loader.__module__,
        HostileModule(),
    )
    with pytest.raises(
        PreopenControlAcquisitionIoError,
        match="physical loader authority changed",
    ):
        clone(**kwargs)
    assert signer_callbacks == []
    assert read_callbacks == []
    assert module_callbacks == []
    assert minter_cells["records"].cell_contents is records_before


def test_preopen_physical_loader_refuses_transitive_dependency_rebind_first(
    tmp_path, monkeypatch,
):
    _, material = _reviewed_receipt(tmp_path)
    callbacks = []

    def hostile_manifest(*args, **values):
        callbacks.append((args, values))
        raise AssertionError("hostile manifest verifier executed")

    kwargs = {
        "output_manifest_bytes": material["output"],
        "output_shard_payloads": (material["payload"],),
        "independent_review_receipt_bytes": material["review"],
        "qc_execution_receipt_bytes": material["execution"],
        "summary_receipt_bytes": material["summary"],
        "external_review_pin_path": material["pin_path"],
        "owner_signature": None,
    }
    with monkeypatch.context() as patch:
        patch.setattr(acquisition_io.core, "_validate_manifest", hostile_manifest)
        with pytest.raises(
            PreopenControlAcquisitionIoError,
            match="physical loader authority changed",
        ):
            acquisition_io.load_physically_reviewed_preopen_control_acquisition_receipt(
                **kwargs
            )
    assert callbacks == []

    class_callbacks = []

    def hostile_decoder(*args, **values):
        class_callbacks.append((args, values))
        raise AssertionError("hostile JSON decoder executed")

    with monkeypatch.context() as patch:
        patch.setattr(acquisition_io.json.JSONDecoder, "__init__", hostile_decoder)
        with pytest.raises(
            PreopenControlAcquisitionIoError,
            match="physical loader authority changed",
        ):
            acquisition_io.load_physically_reviewed_preopen_control_acquisition_receipt(
                **kwargs
            )
    assert class_callbacks == []


def test_preopen_acquisition_authority_is_private_and_fork_local(
    tmp_path, monkeypatch,
):
    receipt, _ = _reviewed_receipt(tmp_path, monkeypatch)
    for name in (
        "_PREOPEN_ACQUISITION_AUTHORITIES",
        "_PREOPEN_ACQUISITION_AUTHORITIES_LOCK",
        "_claim_preopen_acquisition_receipt_minter",
        "_mint_physically_reviewed_preopen_control_acquisition_receipt",
        "_mint_physically_reviewed_preopen_control_acquisition_receipt_implementation",
        "_make_preopen_acquisition_receipt_authority",
    ):
        assert not hasattr(acquisition_core, name)

    if not hasattr(os, "fork"):
        pytest.skip("fork is unavailable")
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_descriptor)
        try:
            _offline_preopen_requirer(receipt)
        except PreopenControlAcquisitionError:
            result = b"refused"
        else:
            result = b"accepted"
        os.write(write_descriptor, result)
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    result = os.read(read_descriptor, 32)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert result == b"refused"
    assert _offline_preopen_requirer(receipt) is receipt
    with pytest.raises(PreopenControlAcquisitionError):
        require_reviewed_preopen_control_acquisition_receipt(receipt)


def test_extracted_preopen_minter_cannot_bypass_physical_signed_loader(
    tmp_path, monkeypatch,
):
    receipt, material = _reviewed_receipt(tmp_path, monkeypatch)
    loader = acquisition_io.load_physically_reviewed_preopen_control_acquisition_receipt
    cells = dict(zip(loader.__code__.co_freevars, loader.__closure__, strict=True))
    minter = cells["receipt_minter"].cell_contents
    minter_cells = dict(
        zip(minter.__code__.co_freevars, minter.__closure__, strict=True)
    )
    assert type(minter_cells["records"].cell_contents) is tuple

    with pytest.raises(
        PreopenControlAcquisitionError,
        match="mint is loader-private",
    ):
        minter(
            output_manifest_bytes=material["output"],
            independent_review_receipt_bytes=material["review"],
            qc_execution_receipt_id=receipt.qc_execution_receipt_id,
            qc_execution_receipt_sha256=receipt.qc_execution_receipt_sha256,
            external_review_pin_id=receipt.external_review_pin_id,
            external_review_pin_sha256=receipt.external_review_pin_sha256,
            output_shard_payload_projection_sha256=(
                receipt.output_shard_payload_projection_sha256
            ),
        )

    assert _offline_preopen_requirer(receipt) is receipt
    with pytest.raises(PreopenControlAcquisitionError):
        require_reviewed_preopen_control_acquisition_receipt(receipt)


def test_review_receipt_rejects_omission_even_when_attacker_rehashes_manifest(tmp_path):
    _, material = _reviewed_receipt(tmp_path)
    parsed = json.loads(material["output"])
    parsed["universe_sessions"][0]["accepted_count"] = 0
    parsed["universe_sessions"][0]["terminal_count"] = 0
    parsed["census"]["universe_terminal_count"] = 0
    rehashed = canonical_json_bytes(parsed)
    with pytest.raises(PreopenControlAcquisitionError):
        load_physically_reviewed_preopen_control_acquisition_receipt(
            output_manifest_bytes=rehashed,
            output_shard_payloads=(material["payload"],),
            independent_review_receipt_bytes=material["review"],
            qc_execution_receipt_bytes=material["execution"],
            summary_receipt_bytes=material["summary"],
            external_review_pin_path=material["pin_path"],
            owner_signature=None,
        )


def test_canonical_true_booleans_cannot_self_mint_acquisition():
    with pytest.raises(PreopenControlAcquisitionError, match="physical output shards"):
        load_reviewed_preopen_control_acquisition_receipt(
            output_manifest_bytes=b"{}\n",
            independent_review_receipt_bytes=b"{}\n",
        )


def test_physical_output_allows_explicit_zero_terminal_session(tmp_path):
    _, material = _reviewed_receipt(tmp_path)
    parsed = json.loads(material["output"])
    empty = hashlib.sha256(canonical_json_bytes({
        "domain": "arv2-empty-terminal-set-v1"
    })).hexdigest()
    parsed["universe_sessions"].append({
        "schema": UNIVERSE_SESSION_COMMITMENT_SCHEMA,
        "decision_session": "2021-01-05", "accepted_count": 0,
        "refusal_count": 0, "terminal_count": 0,
        "terminal_merkle_root": empty,
    })
    parsed["control_sessions"].append({
        "schema": CONTROL_SESSION_COMMITMENT_SCHEMA,
        "decision_session": "2021-01-05", "accepted_count": 0,
        "refusal_count": 0, "terminal_count": 0,
        "terminal_merkle_root": empty, "market_observation_count": 0,
        "market_observation_sha256": "9" * 64,
    })
    parsed["construction_intermediates"][
        "market_session_commitment_count"
    ] = 2
    parsed["universe_terminal_projection_sha256"] = hashlib.sha256(
        canonical_json_bytes({
            "domain": "arv2-preopen-universe-session-projection-v1",
            "records": parsed["universe_sessions"],
        })
    ).hexdigest()
    parsed["control_terminal_projection_sha256"] = hashlib.sha256(
        canonical_json_bytes({
            "domain": "arv2-preopen-control-session-projection-v1",
            "records": parsed["control_sessions"],
        })
    ).hexdigest()
    manifest, _, _ = acquisition_core._validate_manifest(
        canonical_json_bytes(parsed)
    )
    _, totals = acquisition_io._validated_batch_major_output_payloads(
        manifest, (material["payload"],)
    )
    assert totals == {
        "terminal_count": 1, "accepted_count": 1, "refusal_count": 0,
    }


class _PreopenQcBackend:
    def __init__(self, events, package_bytes, permit_directory):
        self.events = events
        self.package_bytes = package_bytes
        self.permit_directory = permit_directory
        self.objects = {}
        self.files = {}
        self.created = False
        self.status_reads = 0
        self.fail_authenticate = False
        self.inject_statistics = False

    def project(self):
        return {
            "projectId": 321,
            "organizationId": "preopen-test-organization",
            "name": "ARV2_PREOPEN_CONTROL_CONSTRUCTION_20260911",
            "language": "Py", "owner": True, "codeRunning": False,
            "collaborators": [{"owner": True}], "libraries": [],
        }

    def request(self, path, payload):
        self.events.append(path)
        assert (self.permit_directory / submission.PERMIT_FILENAME).exists()
        if path == "authenticate":
            if self.fail_authenticate:
                raise RuntimeError("ambiguous authentication")
            return {"success": True}
        if path == "projects/read":
            return {"success": True, "projects": [self.project()] if self.created else []}
        if path == "projects/create":
            self.created = True
            return {"success": True, "projects": [self.project()]}
        if path == "files/read":
            return {"success": True, "files": [
                {"name": name, "content": content}
                for name, content in sorted(self.files.items())
            ]}
        if path == "files/create":
            self.files[payload["name"]] = payload["content"]
            return {"success": True}
        if path == "compile/create":
            return {
                "success": True,
                "compileId": "preopen-compile",
                "state": "InQueue",
                "parameters": [],
                "projectId": 321,
                "signature": "fixture-signature",
                "signatureOrder": [],
            }
        if path == "compile/read":
            return {
                "success": True,
                "compileId": "preopen-compile",
                "state": "BuildSuccess",
                "logs": ["discard-only compile fixture"],
            }
        if path == "backtests/create":
            return {"success": True, "backtest": {
                "backtestId": "preopen-backtest", "name": payload["backtestName"],
                "projectId": 321, "status": "In Queue...",
            }}
        if path == "backtests/list":
            self.status_reads += 1
            result = {"success": True, "count": 1, "backtests": [{
                "backtestId": "preopen-backtest",
                "name": "ARV2 pre-open controls outcome-free construction",
                "projectId": 321, "status": "Completed.",
            }]}
            if self.inject_statistics:
                result["backtests"][0]["statistics"] = {"Sharpe Ratio": "forbidden"}
            return result
        if path == "object/read":
            return {"success": True, "object": {
                "key": payload["key"],
                "objectData": base64.b64encode(self.package_bytes).decode("ascii"),
            }}
        raise AssertionError(path)


def _preopen_fake_client(backend):
    def http(url, body, headers, timeout):
        del timeout
        assert "Authorization" in headers
        path = url.split("/api/v2/", 1)[1]
        if path == "object/set":
            boundary = headers["Content-Type"].split("boundary=", 1)[1]
            key = body.split(b'name="key"\r\n\r\n', 1)[1].split(
                b"\r\n--" + boundary.encode(), 1
            )[0].decode()
            marker = (
                b'name="objectData"; filename="object.bin"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
            )
            backend.objects[key] = body.split(marker, 1)[1].rsplit(
                b"\r\n--" + boundary.encode() + b"--\r\n", 1
            )[0]
            backend.events.append(path)
            result = {"success": True}
        else:
            payload = json.loads(body)
            if path == "object/properties":
                stored = backend.objects[payload["key"]]
                backend.events.append(path)
                result = {"success": True, "metadata": {
                    "key": payload["key"], "size": len(stored),
                    "md5": hashlib.md5(stored, usedforsecurity=False).hexdigest(),
                }}
            else:
                result = backend.request(path, payload)
        return 200, json.dumps(result, separators=(",", ":")).encode()

    return transport_module.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )


def _submission_context(monkeypatch, tmp_path):
    tmp_path.chmod(0o700)
    inputs, authority = _activated_manifest(tmp_path)
    projection = build_preopen_control_qc_projection(
        input_manifest_bytes=inputs, worker_source_bytes=WORKER_PATH.read_bytes(),
        quality_worker_source_bytes=QUALITY_WORKER_PATH.read_bytes(),
        runtime_source_bytes=RUNTIME_PATH.read_bytes(), run_authority=authority,
    )
    plan = submission.build_preopen_qc_submission_plan(
        projection=projection, input_manifest_bytes=inputs,
        input_shards=_input_shards(), run_authority=authority,
        organization_id="preopen-test-organization",
    )
    package = canonical_json_bytes({
        "schema": "arv2-preopen-control-terminal-package-v1",
        "contract_id": "arv2-preopen-control-contract-" + CONTRACT_SHA256[:16],
        "contract_sha256": CONTRACT_SHA256,
        "input_manifest": {
            "artifact_id": projection.input_manifest_id,
            "content_sha256": projection.input_manifest_sha256,
            "artifact_sha256": projection.input_manifest_sha256,
            "byte_count": projection.input_manifest_byte_count,
        },
        "project_source_set_sha256": projection.project_source_set_sha256,
        "output_manifest": {
            "artifact_id": "arv2-preopen-control-output-" + "b" * 24,
            "content_sha256": "b" * 64, "artifact_sha256": "b" * 64,
            "byte_count": 1000,
            "object_store_key": "arv2/preopen/output/manifests/" + "b" * 64 + ".json",
        },
        "output_shard_inventory_sha256": "c" * 64,
        "universe_terminal_projection_sha256": "d" * 64,
        "control_terminal_projection_sha256": "e" * 64,
        "q_data_measurement_projection_sha256": "f" * 64,
        "census": {
            "universe_terminal_count": 1, "control_accepted_count": 1,
            "control_refusal_count": 0, "control_terminal_count": 1,
        },
        "outcome_statistics_log_order_accessed": False,
    })
    events = []
    backend = _PreopenQcBackend(events, package, tmp_path)
    client = _preopen_fake_client(backend)
    monkeypatch.setattr(
        submission, "_require_external_execution_trust_root",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(submission.formal, "_require_concrete_transport", lambda value: value)
    monkeypatch.setattr(submission, "_wait", lambda _seconds: None)
    def offline_minter(*, transport, scope, binding_record, call_budget):
        return transport_module._mint_offline_test_capability(
            transport,
            scope=scope,
            binding_record=binding_record,
            call_budget=call_budget,
        )

    offline_records = {}
    offline_pid = os.getpid()

    def public_registry(kind):
        return (
            submission._LAUNCH_RECEIPT_AUTHORITIES
            if kind == "launch"
            else submission._TERMINAL_RECEIPT_AUTHORITIES
            if kind == "terminal"
            else submission._OUTPUT_RECEIPT_AUTHORITIES
        )

    def offline_register(kind, value):
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda _ref, key=identity: offline_records.pop(key, None),
        )
        entry = (reference, value.receipt_sha256, offline_pid)
        offline_records[identity] = entry
        public_registry(kind)[identity] = entry
        return value

    def offline_current(kind, value):
        identity = id(value)
        entry = offline_records.get(identity)
        if (
            os.getpid() != offline_pid
            or entry is None
            or entry[0]() is not value
            or public_registry(kind).get(identity) is not entry
        ):
            offline_records.pop(identity, None)
            public_registry(kind).pop(identity, None)
            return None
        return entry

    register_launch = _with_global_values(
        submission._register_launch_process_return,
        _process_receipt_authority_register=offline_register,
    )
    register_terminal = _with_global_values(
        submission._register_terminal_process_return,
        _process_receipt_authority_register=offline_register,
    )
    register_output = _with_global_values(
        submission._register_output_process_return,
        _process_receipt_authority_register=offline_register,
    )
    require_launch = _with_global_values(
        submission._require_launch_receipt,
        _process_receipt_authority_current=offline_current,
    )
    require_terminal = _with_global_values(
        submission._require_terminal_receipt,
        _process_receipt_authority_current=offline_current,
        _require_launch_receipt=require_launch,
    )
    require_output = _with_global_values(
        submission.require_preopen_qc_output_package_receipt,
        _process_receipt_authority_current=offline_current,
    )

    originals = {
        name: getattr(submission, name)
        for name in (
            "execute_preopen_qc_submission_once",
            "inspect_preopen_qc_terminal_status",
            "retrieve_preopen_qc_terminal_package",
            "download_and_load_preopen_qc_terminal_archive",
        )
    }
    execute_impl = _with_global_values(
        _closure_value(originals["execute_preopen_qc_submission_once"], "execute_impl"),
        _register_launch_process_return=register_launch,
    )
    inspect_impl = _with_global_values(
        _closure_value(originals["inspect_preopen_qc_terminal_status"], "inspect_impl"),
        _require_launch_receipt=require_launch,
        _register_terminal_process_return=register_terminal,
    )
    retrieve_impl = _with_global_values(
        _closure_value(originals["retrieve_preopen_qc_terminal_package"], "retrieve_impl"),
        _require_terminal_receipt=require_terminal,
        _register_output_process_return=register_output,
        require_preopen_qc_output_package_receipt=require_output,
    )
    download_impl = _with_global_values(
        _closure_value(
            originals["download_and_load_preopen_qc_terminal_archive"],
            "download_impl",
        ),
        _require_launch_receipt=require_launch,
        _require_terminal_receipt=require_terminal,
        require_preopen_qc_output_package_receipt=require_output,
    )
    implementations = {
        "execute_preopen_qc_submission_once": ("execute_impl", execute_impl),
        "inspect_preopen_qc_terminal_status": ("inspect_impl", inspect_impl),
        "retrieve_preopen_qc_terminal_package": ("retrieve_impl", retrieve_impl),
        "download_and_load_preopen_qc_terminal_archive": (
            "download_impl",
            download_impl,
        ),
    }

    offline_binding_guard = lambda _operation: None
    for name, (implementation_name, implementation) in implementations.items():
        action = _with_closure_value(
            originals[name],
            implementation_name,
            implementation,
        )
        action = _with_closure_value(action, "minter", offline_minter)
        action = _with_closure_value(
            action, "binding_guard", offline_binding_guard
        )
        monkeypatch.setattr(
            submission,
            name,
            action,
        )
    monkeypatch.setattr(submission, "_require_launch_receipt", require_launch)
    monkeypatch.setattr(submission, "_require_terminal_receipt", require_terminal)
    monkeypatch.setattr(
        submission,
        "require_preopen_qc_output_package_receipt",
        require_output,
    )
    return plan, client, backend, events


def test_preopen_qc_adapter_one_use_status_and_named_output_only(monkeypatch, tmp_path):
    plan, client, backend, events = _submission_context(monkeypatch, tmp_path)
    permit, launch = submission.execute_preopen_qc_submission_once(
        plan=plan, client=client, ledger_directory=tmp_path,
        started_at_utc="2026-09-12T12:00:00.000000Z",
        owner_signature=None,
    )
    terminal = submission.inspect_preopen_qc_terminal_status(
        plan=plan, permit=permit, launch=launch, client=client,
        owner_signature=None,
    )
    output = submission.retrieve_preopen_qc_terminal_package(
        plan=plan, permit=permit, launch=launch, terminal=terminal, client=client,
        owner_signature=None,
    )
    assert output.package_key == plan.terminal_package_key
    assert output.object_read_count == 1
    assert output.outcome_statistics_log_order_accessed is False
    assert events.count("backtests/create") == 1
    assert events.count("object/read") == 1
    assert "backtests/read" not in events
    assert "projects/delete" not in events
    assert len(backend.objects) == len(plan.upload_entries)
    assert set(backend.files) == {item.project_path for item in plan.source_files}


def _genuine_preopen_process_receipts(monkeypatch, tmp_path):
    plan, client, _backend, _events = _submission_context(monkeypatch, tmp_path)
    permit, launch = submission.execute_preopen_qc_submission_once(
        plan=plan,
        client=client,
        ledger_directory=tmp_path,
        started_at_utc="2026-09-12T12:00:00.000000Z",
        owner_signature=None,
    )
    terminal = submission.inspect_preopen_qc_terminal_status(
        plan=plan,
        permit=permit,
        launch=launch,
        client=client,
        owner_signature=None,
    )
    output = submission.retrieve_preopen_qc_terminal_package(
        plan=plan,
        permit=permit,
        launch=launch,
        terminal=terminal,
        client=client,
        owner_signature=None,
    )
    return plan, permit, launch, terminal, output


def test_reflected_preopen_process_register_cannot_self_mint():
    value = object.__new__(submission.PreopenQcLaunchReceipt)
    with pytest.raises(
        submission.PreopenQcSubmissionError, match="register caller changed"
    ):
        submission._process_receipt_authority_register("launch", value)


def test_reflected_preopen_internal_launch_producer_cannot_mint_process_receipt(
    monkeypatch, tmp_path,
):
    plan, client, _backend, _events = _submission_context(monkeypatch, tmp_path)
    public = _PRODUCTION_PREOPEN_ACTIONS["execute_preopen_qc_submission_once"]
    execute_impl = _closure_value(public, "execute_impl")
    minter = _closure_value(
        submission.execute_preopen_qc_submission_once,
        "minter",
    )

    with pytest.raises(submission.PreopenQcSubmissionLocked) as caught:
        execute_impl(
            plan=plan,
            client=client,
            ledger_directory=tmp_path,
            started_at_utc="2026-09-12T12:00:00.000000Z",
            owner_signature=None,
            _transport_capability_minter=minter,
        )
    assert isinstance(caught.value.__cause__, submission.PreopenQcSubmissionError)
    assert "launch receipt register caller changed" in str(caught.value.__cause__)


def test_reflected_preopen_internal_terminal_and_output_producers_cannot_mint(
    monkeypatch, tmp_path,
):
    plan, client, _backend, _events = _submission_context(monkeypatch, tmp_path)
    permit, launch = submission.execute_preopen_qc_submission_once(
        plan=plan,
        client=client,
        ledger_directory=tmp_path,
        started_at_utc="2026-09-12T12:00:00.000000Z",
        owner_signature=None,
    )

    terminal_public = _PRODUCTION_PREOPEN_ACTIONS[
        "inspect_preopen_qc_terminal_status"
    ]
    terminal_impl = _closure_value(terminal_public, "inspect_impl")
    minter = _closure_value(
        submission.inspect_preopen_qc_terminal_status,
        "minter",
    )
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="terminal receipt register caller changed",
    ):
        terminal_impl(
            plan=plan,
            permit=permit,
            launch=launch,
            client=client,
            owner_signature=None,
            _transport_capability_minter=minter,
        )
    terminal = submission.inspect_preopen_qc_terminal_status(
        plan=plan,
        permit=permit,
        launch=launch,
        client=client,
        owner_signature=None,
    )
    output_public = _PRODUCTION_PREOPEN_ACTIONS[
        "retrieve_preopen_qc_terminal_package"
    ]
    output_impl = _closure_value(output_public, "retrieve_impl")
    output_minter = _closure_value(
        submission.retrieve_preopen_qc_terminal_package,
        "minter",
    )
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="output receipt register caller changed",
    ):
        output_impl(
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
            client=client,
            owner_signature=None,
            _transport_capability_minter=output_minter,
        )
def test_reflected_preopen_process_private_registries_are_immutable():
    register = submission._process_receipt_authority_register
    private_entry = _closure_value(register, "private_entry")
    private_registry = _closure_value(private_entry, "private_registry")
    state = _closure_value(private_registry, "private_registries")
    assert type(state) is tuple
    assert not hasattr(state, "append")


def test_preopen_receipt_constructors_cannot_mint_process_authority(
    monkeypatch, tmp_path,
):
    plan, permit, launch, terminal, output = _genuine_preopen_process_receipts(
        monkeypatch, tmp_path
    )
    direct_launch = submission._launch(
        plan,
        permit,
        launch.project_id,
        launch.compile_id,
        launch.backtest_id,
        launch.initial_status,
    )
    with pytest.raises(submission.PreopenQcSubmissionError, match="launch receipt changed"):
        submission._require_launch_receipt(direct_launch, plan, permit)

    direct_terminal = submission._terminal_receipt(
        plan=plan,
        permit=permit,
        launch=launch,
        status=terminal.terminal_status,
        count=terminal.status_poll_count,
    )
    with pytest.raises(
        submission.PreopenQcSubmissionError, match="terminal status receipt changed"
    ):
        submission._require_terminal_receipt(
            direct_terminal, plan, permit, launch
        )

    direct_output = submission._build_output_package_receipt(
        plan=plan,
        permit=permit,
        launch=launch,
        terminal=terminal,
        package_bytes=output.package_bytes,
    )
    with pytest.raises(
        submission.PreopenQcSubmissionError, match="process-return authority"
    ):
        submission.require_preopen_qc_output_package_receipt(
            direct_output,
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
        )


def test_preopen_offline_process_receipts_remain_rejected_after_restore(
    tmp_path,
):
    with pytest.MonkeyPatch.context() as patch:
        plan, permit, launch, terminal, output = (
            _genuine_preopen_process_receipts(patch, tmp_path)
        )
    with pytest.raises(submission.PreopenQcSubmissionError):
        submission._require_launch_receipt(launch, plan, permit)
    with pytest.raises(submission.PreopenQcSubmissionError):
        submission._require_terminal_receipt(terminal, plan, permit, launch)
    with pytest.raises(submission.PreopenQcSubmissionError):
        submission.require_preopen_qc_output_package_receipt(
            output,
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
        )


def test_cloned_preopen_action_refuses_before_transport(monkeypatch, tmp_path):
    public = _PRODUCTION_PREOPEN_ACTIONS[
        "execute_preopen_qc_submission_once"
    ]
    plan, client, _backend, events = _submission_context(monkeypatch, tmp_path)
    implementation = _closure_value(public, "execute_impl")
    cloned_implementation = _with_global_values(
        implementation,
        _require_external_execution_trust_root=lambda *_args, **_kwargs: None,
    )
    cloned_public = _with_closure_value(
        public,
        "execute_impl",
        cloned_implementation,
    )
    cloned_public = _with_closure_value(
        cloned_public, "binding_guard", lambda _operation: None
    )
    with pytest.raises(
        submission.formal.FormalQcSubmissionError,
        match="capability caller changed",
    ):
        cloned_public(
            plan=plan,
            client=client,
            ledger_directory=tmp_path,
            started_at_utc="2026-09-12T12:00:00.000000Z",
            owner_signature=None,
        )
    assert events == []


def test_preopen_public_receipt_mirrors_cannot_reseal_private_authority(
    monkeypatch, tmp_path,
):
    plan, permit, launch, terminal, output = _genuine_preopen_process_receipts(
        monkeypatch, tmp_path
    )
    cases = (
        (
            submission._OUTPUT_RECEIPT_AUTHORITIES,
            output,
            lambda: submission.require_preopen_qc_output_package_receipt(
                output,
                plan=plan,
                permit=permit,
                launch=launch,
                terminal=terminal,
            ),
        ),
        (
            submission._TERMINAL_RECEIPT_AUTHORITIES,
            terminal,
            lambda: submission._require_terminal_receipt(
                terminal, plan, permit, launch
            ),
        ),
        (
            submission._LAUNCH_RECEIPT_AUTHORITIES,
            launch,
            lambda: submission._require_launch_receipt(
                launch, plan, permit
            ),
        ),
    )
    for registry, value, require in cases:
        with submission._PROCESS_RECEIPT_AUTHORITY_LOCK:
            entry = registry[id(value)]
            replacement = tuple(list(entry))
            assert replacement is not entry
            registry[id(value)] = replacement
        with pytest.raises(submission.PreopenQcSubmissionError):
            require()
        assert id(value) not in registry
        with submission._PROCESS_RECEIPT_AUTHORITY_LOCK:
            registry[id(value)] = entry
        with pytest.raises(submission.PreopenQcSubmissionError):
            require()
        assert id(value) not in registry


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_preopen_process_receipts_refuse_in_fork_child_and_remain_valid_in_parent(
    monkeypatch, tmp_path,
):
    plan, permit, launch, terminal, output = _genuine_preopen_process_receipts(
        monkeypatch, tmp_path
    )
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - assertions are reported through pipe
        os.close(read_descriptor)
        results = []
        for callback in (
            lambda: submission.require_preopen_qc_output_package_receipt(
                output,
                plan=plan,
                permit=permit,
                launch=launch,
                terminal=terminal,
            ),
            lambda: submission._require_terminal_receipt(
                terminal, plan, permit, launch
            ),
            lambda: submission._require_launch_receipt(launch, plan, permit),
        ):
            try:
                callback()
            except submission.PreopenQcSubmissionError:
                results.append("refused")
            else:
                results.append("accepted")
        os.write(write_descriptor, ",".join(results).encode("ascii"))
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 1024)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert status == 0
    assert outcome == b"refused,refused,refused"
    assert submission._require_launch_receipt(launch, plan, permit) is launch
    assert (
        submission._require_terminal_receipt(terminal, plan, permit, launch)
        is terminal
    )
    assert submission.require_preopen_qc_output_package_receipt(
        output,
        plan=plan,
        permit=permit,
        launch=launch,
        terminal=terminal,
    ) is output


def test_preopen_qc_adapter_trust_gate_precedes_permit_and_credentials(monkeypatch, tmp_path):
    plan, client, _backend, events = _submission_context(monkeypatch, tmp_path)
    execute_impl = _closure_value(
        submission.execute_preopen_qc_submission_once, "execute_impl"
    )
    monkeypatch.setitem(
        execute_impl.__globals__, "_require_external_execution_trust_root",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            submission.PreopenQcSubmissionError("closed")
        ),
    )
    with pytest.raises(submission.PreopenQcSubmissionError, match="closed"):
        submission.execute_preopen_qc_submission_once(
            plan=plan, client=client, ledger_directory=tmp_path,
            started_at_utc="2026-09-12T12:00:00.000000Z",
            owner_signature=None,
        )
    assert not (tmp_path / submission.PERMIT_FILENAME).exists()
    assert events == []


@pytest.mark.parametrize(
    "name",
    (
        "require_preopen_execution_owner_signature",
        "globals",
        "type",
        "_unexpected_preopen_action_global",
    ),
)
def test_preopen_global_census_refuses_before_permit_and_transport(
    monkeypatch, tmp_path, name,
):
    with pytest.MonkeyPatch.context() as setup_patch:
        plan, client, _backend, events = _submission_context(
            setup_patch, tmp_path
        )
    permit_path = tmp_path / submission.PERMIT_FILENAME
    monkeypatch.setattr(submission, name, object(), raising=False)
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="action global authority changed",
    ):
        submission.execute_preopen_qc_submission_once(
            plan=plan,
            client=client,
            ledger_directory=tmp_path,
            started_at_utc="2026-09-12T12:00:00.000000Z",
            owner_signature=None,
        )
    assert not permit_path.exists()
    assert events == []


@pytest.mark.parametrize(
    ("namespace", "name"),
    (
        (submission.sys, "_getframe"),
        (submission.os.path, "realpath"),
        (submission.Path, "is_symlink"),
        (submission.os, "O_EXCL"),
        (submission.json.JSONDecoder, "decode"),
    ),
)
def test_preopen_frame_dependency_rebind_refuses_before_permit_and_transport(
    monkeypatch, tmp_path, namespace, name,
):
    with pytest.MonkeyPatch.context() as setup_patch:
        plan, client, _backend, events = _submission_context(
            setup_patch, tmp_path
        )
    permit_path = tmp_path / submission.PERMIT_FILENAME
    callbacks = []

    def hostile(*args, **values):
        callbacks.append((args, values))
        raise AssertionError("hostile frame dependency executed")

    with monkeypatch.context() as patch:
        patch.setattr(namespace, name, hostile)
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match="action dependency authority changed",
        ):
            submission.execute_preopen_qc_submission_once(
                plan=plan,
                client=client,
                ledger_directory=tmp_path,
                started_at_utc="2026-09-12T12:00:00.000000Z",
                owner_signature=None,
            )
    assert callbacks == []
    assert not permit_path.exists()
    assert events == []


def test_preopen_exact_signed_authority_candidate_and_empty_registry_stay_closed(
    monkeypatch, tmp_path,
):
    plan, client, _backend, events = _submission_context(monkeypatch, tmp_path)
    payload = submission.render_preopen_qc_execution_authority_candidate(plan)
    parsed = json.loads(payload)
    assert parsed["schema"] == "arv2-preopen-qc-execution-authority-v1"
    assert parsed["plan_sha256"] == plan.plan_sha256
    assert parsed["actions"] == list(submission.PREOPEN_EXECUTION_ACTIONS)
    assert parsed["outcome_result_statistics_log_order_access"] is False
    assert [item["path"] for item in parsed["host_closure"]["sources"]] == list(
        submission.PREOPEN_REQUIRED_HOST_CODE_PATHS
    )
    assert "research/analyst_revisions_v2_qc/formal_submission_adapter.py" in (
        submission.PREOPEN_REQUIRED_HOST_CODE_PATHS
    )
    assert "research/analyst_revisions_v2_qc/formal_qc_transport.py" in (
        submission.PREOPEN_REQUIRED_HOST_CODE_PATHS
    )
    execute_impl = _closure_value(
        submission.execute_preopen_qc_submission_once, "execute_impl"
    )
    monkeypatch.setitem(
        execute_impl.__globals__, "_require_external_execution_trust_root",
        REAL_PREOPEN_EXECUTION_TRUST_GATE,
    )

    with pytest.raises(submission.PreopenQcSubmissionError, match="trust root is unavailable"):
        submission.execute_preopen_qc_submission_once(
            plan=plan,
            client=client,
            ledger_directory=tmp_path,
            started_at_utc="2026-09-12T12:00:00.000000Z",
            owner_signature=None,
        )

    assert not (tmp_path / submission.PERMIT_FILENAME).exists()
    assert events == []


def test_every_preopen_transitive_host_dependency_change_precedes_transport(monkeypatch):
    closure = submission.build_preopen_qc_host_closure_binding()
    calls = []
    monkeypatch.setattr(
        submission.formal, "_transport_call",
        lambda *_args, **_kwargs: calls.append((_args, _kwargs)),
    )
    for index, source in enumerate(closure.sources):
        changed = dataclasses.replace(source, content_sha256="0" * 64)
        observed = closure.sources[:index] + (changed,) + closure.sources[index + 1:]
        monkeypatch.setattr(
            submission, "_read_preopen_host_sources",
            lambda observed=observed: observed,
        )
        with pytest.raises(submission.PreopenQcSubmissionError, match="live pre-open"):
            submission._preopen_transport_call(
                closure, object(), object(), "_request_json", "authenticate", {}
            )

    assert calls == []


def test_preopen_qc_ambiguous_submission_spends_permit_and_forbids_retry(monkeypatch, tmp_path):
    plan, client, backend, events = _submission_context(monkeypatch, tmp_path)
    backend.fail_authenticate = True
    with pytest.raises(submission.PreopenQcSubmissionLocked, match="remains consumed"):
        submission.execute_preopen_qc_submission_once(
            plan=plan, client=client, ledger_directory=tmp_path,
            started_at_utc="2026-09-12T12:00:00.000000Z",
            owner_signature=None,
        )
    before = len(events)
    with pytest.raises(submission.PreopenQcSubmissionLocked, match="already spent"):
        submission.execute_preopen_qc_submission_once(
            plan=plan, client=client, ledger_directory=tmp_path,
            started_at_utc="2026-09-12T12:01:00.000000Z",
            owner_signature=None,
        )
    assert len(events) == before


def test_preopen_qc_status_discards_documented_statistics_without_result_read(
    monkeypatch, tmp_path,
):
    plan, client, backend, events = _submission_context(monkeypatch, tmp_path)
    permit, launch = submission.execute_preopen_qc_submission_once(
        plan=plan, client=client, ledger_directory=tmp_path,
        started_at_utc="2026-09-12T12:00:00.000000Z",
        owner_signature=None,
    )
    backend.inject_statistics = True
    terminal = submission.inspect_preopen_qc_terminal_status(
        plan=plan, permit=permit, launch=launch, client=client,
        owner_signature=None,
    )
    assert terminal.terminal_status == "Completed."
    assert terminal.statistics_requested is False
    assert terminal.result_log_order_accessed is False
    assert "object/read" not in events
    assert "backtests/read" not in events


def test_preopen_qc_output_refuses_forged_terminal_before_object_read(
    monkeypatch, tmp_path,
):
    plan, client, _backend, events = _submission_context(monkeypatch, tmp_path)
    permit, launch = submission.execute_preopen_qc_submission_once(
        plan=plan, client=client, ledger_directory=tmp_path,
        started_at_utc="2026-09-12T12:00:00.000000Z",
        owner_signature=None,
    )
    terminal = submission.inspect_preopen_qc_terminal_status(
        plan=plan, permit=permit, launch=launch, client=client,
        owner_signature=None,
    )
    forged = dataclasses.replace(terminal, receipt_sha256="a" * 64)
    with pytest.raises(submission.PreopenQcSubmissionError, match="receipt changed"):
        submission.retrieve_preopen_qc_terminal_package(
            plan=plan, permit=permit, launch=launch,
            terminal=forged, client=client,
            owner_signature=None,
        )
    assert "object/read" not in events


def test_preopen_qc_output_refuses_rebound_manifest_identity(monkeypatch, tmp_path):
    plan, client, backend, events = _submission_context(monkeypatch, tmp_path)
    permit, launch = submission.execute_preopen_qc_submission_once(
        plan=plan, client=client, ledger_directory=tmp_path,
        started_at_utc="2026-09-12T12:00:00.000000Z",
        owner_signature=None,
    )
    terminal = submission.inspect_preopen_qc_terminal_status(
        plan=plan, permit=permit, launch=launch, client=client,
        owner_signature=None,
    )
    package = json.loads(backend.package_bytes)
    package["output_manifest"]["artifact_id"] = (
        "arv2-preopen-control-output-" + "a" * 24
    )
    backend.package_bytes = canonical_json_bytes(package)
    with pytest.raises(submission.PreopenQcSubmissionError, match="identity changed"):
        submission.retrieve_preopen_qc_terminal_package(
            plan=plan, permit=permit, launch=launch,
            terminal=terminal, client=client,
            owner_signature=None,
        )
    assert events.count("object/read") == 1
    assert "backtests/read" not in events
