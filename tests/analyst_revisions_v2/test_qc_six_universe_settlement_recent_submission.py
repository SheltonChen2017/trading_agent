"""Isolating tests for the separately frozen six-universe recent window."""

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import six_universe_cap90_submission as cap90
from research.analyst_revisions_v2_qc import six_universe_recent_settlement_submission as subject
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_recent_qc_projection as projector
from tests.analyst_revisions_v2 import test_qc_six_universe_settlement_submission as legacy


GEOMETRY = ("2025-08-01", "2026-09-25", 290, 61)


def test_actual_input_binding_uses_authenticated_activation_descriptor():
    root = Path("artifacts/analyst_revisions_v2/accepted_risk_latest_order_package_20260925_01")
    package_path = root / "arv2-preliminary-qc-package-2649577ac55ac39de37a4a70"
    if not package_path.is_dir():
        pytest.skip("local ignored exact latest package unavailable")
    value = subject.latest_builder.load_latest_order_input_package(
        package_path, expected_package_sha256=subject.PINNED_PACKAGE_SHA256,
        lineage_path=root / ("arv2-latest-lineage-" + subject.PINNED_LINEAGE_SHA256) / "lineage.json",
        expected_lineage_sha256=subject.PINNED_LINEAGE_SHA256)
    assert subject._package(value) is value.package
    manifest = subject._upload_manifest(value.package)
    assert len(manifest) == 6
    assert manifest[-1][1] == subject.PINNED_ACTIVATION_MANIFEST_SHA256
    assert manifest[-1][3] is True
    assert sum(row[2] for row in manifest) == 2_771_341


def _recent_base_aggregate():
    aggregate, _candidate = legacy._aggregate("R195")
    aggregate["account"].update({
        "first_observation_session": GEOMETRY[0],
        "last_observation_session": GEOMETRY[1],
        "observation_count": GEOMETRY[2],
    })
    aggregate["execution"]["decision_count"] = GEOMETRY[3]
    for row in aggregate["sleeve_diagnostics"]["rows"]:
        row[2] = GEOMETRY[3]
    aggregate["fallback_counts"] = {
        key: (6 * GEOMETRY[3] if index == 0 else 0)
        for index, key in enumerate(aggregate["fallback_counts"])
    }
    return {key: aggregate[key] for key in cap90._AGGREGATE_FIELDS}


def test_recent_geometry_is_separate_from_unchanged_default():
    aggregate = _recent_base_aggregate()
    projected = cap90._project_aggregate(aggregate, expected_geometry=GEOMETRY)
    assert projected["account"]["observation_count"] == 290
    assert projected["account"]["first_observation_session"] == GEOMETRY[0]
    assert projected["account"]["last_observation_session"] == GEOMETRY[1]
    with pytest.raises(cap90.Cap90QcSubmissionError, match="nested aggregate"):
        cap90._project_aggregate(aggregate)
    prior_aggregate, _candidate = legacy._aggregate("R195")
    old_base = {key: prior_aggregate[key] for key in cap90._AGGREGATE_FIELDS}
    assert cap90._project_aggregate(old_base)["account"]["observation_count"] == 1255
    with pytest.raises(cap90.Cap90QcSubmissionError, match="nested aggregate"):
        cap90._project_aggregate(old_base, expected_geometry=GEOMETRY)


@pytest.mark.parametrize("geometry", (
    ("2025-08-01", "2026-09-25", 289, 61),
    ("2025-08-01", "2026-09-24", 290, 61),
    ("2025-08-01", "2026-09-25", 290, True),
    ["2025-08-01", "2026-09-25", 290, 61],
    ("2025-08-01", "2026-09-25", 290),
))
def test_recent_geometry_cannot_be_caller_authored(geometry):
    with pytest.raises(cap90.Cap90QcSubmissionError, match="authorized literal window"):
        cap90._project_aggregate(_recent_base_aggregate(), expected_geometry=geometry)


@pytest.mark.parametrize("defect", (
    "first", "last", "observations", "decisions", "sleeve_decisions", "fallback_census",
))
def test_recent_geometry_reader_isolates_each_required_census(defect):
    aggregate = copy.deepcopy(_recent_base_aggregate())
    if defect == "first":
        aggregate["account"]["first_observation_session"] = "2021-01-04"
    elif defect == "last":
        aggregate["account"]["last_observation_session"] = "2025-12-31"
    elif defect == "observations":
        aggregate["account"]["observation_count"] = 289
    elif defect == "decisions":
        aggregate["execution"]["decision_count"] = 60
    elif defect == "sleeve_decisions":
        aggregate["sleeve_diagnostics"]["rows"][0][2] = 60
    elif defect == "fallback_census":
        key = next(iter(aggregate["fallback_counts"]))
        aggregate["fallback_counts"][key] -= 1
    with pytest.raises(cap90.Cap90QcSubmissionError):
        cap90._project_aggregate(aggregate, expected_geometry=GEOMETRY)


def _offline_upload(monkeypatch, tmp_path):
    """Small exact byte inventory; no real package or network authority."""
    payloads = (b"offline row", b"offline activation")
    descriptors = tuple(SimpleNamespace(
        object_store_key=f"arv2/offline-upload/{index}.json",
        content_sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw), activation_manifest=index == 1,
    ) for index, raw in enumerate(payloads))
    manifest = tuple((item.object_store_key, item.content_sha256, item.byte_count,
                      item.activation_manifest) for item in descriptors)
    for name, value in {
        "PINNED_PACKAGE_SHA256": "a" * 64,
        "PINNED_LINEAGE_SHA256": "b" * 64,
        "PINNED_ACTIVATION_MANIFEST_SHA256": descriptors[-1].content_sha256,
        "UPLOAD_MANIFEST_SHA256": hashlib.sha256(common._canonical(manifest)).hexdigest(),
        "UPLOAD_OBJECT_COUNT": 2,
        "MATCHED_BASELINE_PROFILE_SHA256": "c" * 64,
        "TRUSTED_CANDIDATES": {
            candidate_id: dataclasses.replace(common._CANDIDATES["R195"], candidate_id=candidate_id)
            for candidate_id in common._RECENT_PERCENTS
        },
    }.items():
        monkeypatch.setattr(subject, name, value)
    plan = common.SettlementQcPlan(
        "R203", "a" * 32, subject.PINNED_PACKAGE_SHA256,
        subject.PINNED_ACTIVATION_MANIFEST_SHA256, tmp_path / "control")
    inventory = list(zip(descriptors, payloads))
    monkeypatch.setattr(subject, "_package", lambda _value: object())
    monkeypatch.setattr(subject.package_builder,
                        "iter_accepted_risk_preliminary_upload_objects",
                        lambda _package: iter(inventory))
    monkeypatch.setattr(common, "_client", lambda _api: None)
    calls = []

    def request(_api, endpoint, body, content_type):
        calls.append((endpoint, body, content_type))
        if endpoint == "object/set":
            return {"success": True}
        key = json.loads(body)["key"]
        index = next(i for i, item in enumerate(descriptors)
                     if item.object_store_key == key)
        return {"success": True, "metadata": {
            "key": key, "size": len(payloads[index]),
            "md5": hashlib.md5(payloads[index], usedforsecurity=False).hexdigest(),
            "preview": "ignored private data",
        }}

    monkeypatch.setattr(subject, "_object_request", request)
    return plan, inventory, calls


def test_exact_input_upload_verifies_bytes_and_publishes_activation_last(monkeypatch, tmp_path):
    plan, inventory, calls = _offline_upload(monkeypatch, tmp_path)
    identity = subject.upload_exact_inputs(
        plan, object(), object(), owner_waiver_id=subject._INPUT_WAIVER_ID)
    assert [item[0] for item in calls] == [
        "object/set", "object/properties", "object/set", "object/properties"]
    assert inventory[0][1] in calls[0][1]
    assert inventory[1][1] in calls[2][1]
    assert identity == subject._upload_identity(plan)
    subject.require_uploaded_inputs(plan)
    subject.require_uploaded_inputs(dataclasses.replace(plan, candidate_id="R208"))
    with pytest.raises(common.SixUniverseSettlementSubmissionError, match="already claimed"):
        subject.upload_exact_inputs(
            plan, object(), object(), owner_waiver_id=subject._INPUT_WAIVER_ID)
    assert len(calls) == 4


@pytest.mark.parametrize("defect", ("bytes", "order", "count", "waiver", "activation"))
def test_input_upload_refuses_each_changed_authority_before_io(monkeypatch, tmp_path, defect):
    plan, inventory, calls = _offline_upload(monkeypatch, tmp_path)
    claim_path = subject._upload_path(plan, "claim")
    waiver = subject._INPUT_WAIVER_ID
    if defect == "bytes":
        inventory[0] = inventory[0][0], b"changed"
    elif defect == "order":
        inventory.reverse()
    elif defect == "count":
        monkeypatch.setattr(subject, "UPLOAD_OBJECT_COUNT", 3)
    elif defect == "waiver":
        waiver = "wrong"
    else:
        plan = dataclasses.replace(plan, activation_manifest_sha256="f" * 64)
    with pytest.raises(common.SixUniverseSettlementSubmissionError):
        subject.upload_exact_inputs(plan, object(), object(), owner_waiver_id=waiver)
    assert calls == []
    assert not claim_path.exists()


def test_bad_uploaded_metadata_never_publishes_activation_or_valid_receipt(monkeypatch, tmp_path):
    plan, _inventory, calls = _offline_upload(monkeypatch, tmp_path)
    original = subject._object_request

    def request(*args):
        result = original(*args)
        if args[1] == "object/properties":
            result["metadata"]["size"] += 1
        return result

    monkeypatch.setattr(subject, "_object_request", request)
    with pytest.raises(common.SixUniverseSettlementSubmissionError, match="metadata"):
        subject.upload_exact_inputs(
            plan, object(), object(), owner_waiver_id=subject._INPUT_WAIVER_ID)
    assert len(calls) == 2
    assert subject._upload_path(plan, "claim").is_file()
    assert not subject._upload_path(plan, "valid").exists()
    with pytest.raises(common.SixUniverseSettlementSubmissionError, match="complete"):
        subject.require_uploaded_inputs(plan)


@pytest.mark.parametrize("defect", ("endpoint", "body_type", "body_size"))
def test_input_http_bounds_refuse_before_authentication(monkeypatch, defect):
    monkeypatch.setattr(common, "_client", lambda _api: None)
    endpoint, body = "object/set", b"safe"
    if defect == "endpoint":
        endpoint = "live/create"
    elif defect == "body_type":
        body = "unsafe"
    else:
        body = b"x" * (subject.transport.MAX_OBJECT_BYTES + 4097)
    with pytest.raises(common.SixUniverseSettlementSubmissionError):
        subject._object_request(object(), endpoint, body, "application/json")


@pytest.fixture(scope="module")
def offline_recent_projections():
    """Executable source identities, with a test-only historical input fixture.

    No synthetic pin is installed in the application process or on disk.
    Actual production input/source pins have separate public-builder checks.
    """
    if not legacy.PACKAGE_PATH.is_dir():
        pytest.skip("local ignored delta package fixture unavailable")
    prior = delta.load_accepted_risk_delta_order_package(
        legacy.PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256)
    activation = SimpleNamespace(object_store_key="arv2/offline-fixture/manifest.json",
                                 content_sha256="f" * 64, byte_count=4016)
    result = {}
    for percent in projector.CANDIDATE_IDS:
        predecessor = projector._prior.build_tilt_floor_projection(prior, percent)
        files = tuple(projector._base._source_file(item.project_path,
            projector._candidate_source(item.project_path,
                item.source_bytes.decode("ascii"), percent,
                predecessor, activation).encode("ascii"))
            for item in predecessor.source_files)
        profile = projector.require_tilt_recent_profile(percent)
        value = dataclasses.replace(predecessor,
            schema=projector.PROJECTION_SCHEMAS[percent],
            role=projector.TILT_ROLES[percent], variant=projector.TILT_VARIANTS[percent],
            profile_id=projector.PROFILE_IDS[percent], profile_sha256=profile["profile_sha256"],
            activation_manifest_key=activation.object_store_key,
            activation_manifest_sha256=activation.content_sha256,
            activation_manifest_byte_count=activation.byte_count,
            source_files=files, total_source_byte_count=sum(item.byte_count for item in files))
        semantic = {key: item for key, item in value.to_record().items()
                    if key not in ("projection_id", "projection_sha256")}
        digest = hashlib.sha256(common._canonical(semantic)).hexdigest()
        result[projector.CANDIDATE_IDS[percent]] = dataclasses.replace(value,
            projection_sha256=digest,
            projection_id=projector.PROJECTION_ID_PREFIXES[percent] + digest[:24])
    return result


def _install_offline_candidates(monkeypatch, projections):
    first = projections["R203"]
    candidates = {}
    for candidate_id, projection in projections.items():
        percent = common._RECENT_PERCENTS[candidate_id]
        manifest = hashlib.sha256(common._canonical(tuple(
            (item.project_path, item.content_sha256, item.byte_count)
            for item in projection.source_files))).hexdigest()
        candidates[candidate_id] = common._Candidate(
            candidate_id,
            f"{125 + (percent - 100) // 20} ARV2 SIX CAP90 SETTLED TILT{percent} {candidate_id} 202508 NOW",
            projection.role, projection.variant, projection.schema,
            projection.projection_sha256, projection.profile_sha256, manifest,
            16, projection.total_source_byte_count, projector.SUMMARY_SCHEMAS[percent],
            f"ARV2-OWNER-2026-09-25-{candidate_id}A1-TILT{percent}-RECENT-EXPLORATORY-SIGNATURE-WAIVER")
    for name, value in {
        "PINNED_PACKAGE_SHA256": first.package_sha256,
        "PINNED_LINEAGE_SHA256": first.package_lineage_sha256,
        "PINNED_ACTIVATION_MANIFEST_SHA256": first.activation_manifest_sha256,
        "UPLOAD_MANIFEST_SHA256": "e" * 64,
        "UPLOAD_OBJECT_COUNT": 2,
        "MATCHED_BASELINE_PROFILE_SHA256": projector.MATCHED_BASELINE_PROFILE_SHA256,
        "TRUSTED_CANDIDATES": candidates,
        "PROJECTION_ID_PREFIXES": dict(projector.PROJECTION_ID_PREFIXES),
    }.items():
        monkeypatch.setattr(subject, name, value)


def _prepared(monkeypatch, tmp_path, projection):
    candidate_id = projector.CANDIDATE_IDS[
        next(percent for percent in projector.CANDIDATE_IDS
             if projector.TILT_ROLES[percent] == projection.role)]
    plan = subject.build_plan(candidate_id, "a" * 32, tmp_path / "control")
    if not plan.control_directory.exists():
        legacy._predecessors(monkeypatch, plan)
    identity = subject._upload_identity(plan)
    for suffix in ("claim", "valid"):
        path = subject._upload_path(plan, suffix)
        if not path.exists():
            common._write(path, identity)
    return plan


def _recent_statistics(plan, launch, *, target_path="d" * 64, defect=None):
    values = legacy.r185_tests._statistics(plan, launch)
    candidate = common._candidate(plan)
    aggregate = json.loads(values[common.base_runtime.AGGREGATES_STATISTIC_NAME])
    aggregate.pop("order_event_cash_nonnegative")
    aggregate.update({
        "schema": candidate.summary_schema, "role": candidate.role,
        "minimum_observed_order_event_cash": "-25",
        "transient_negative_order_event_count": 1,
        "unexplained_negative_order_event_count": 0,
        "negative_cash_requires_pending_sell_moo": True,
        "settled_cash_nonnegative": True,
        "matched_baseline_profile_sha256": subject.MATCHED_BASELINE_PROFILE_SHA256,
        "matched_baseline_target_path_sha256": target_path,
        "maximum_stock_weight_change_fraction": common._TILT_FRACTIONS[plan.candidate_id],
    })
    aggregate["account"].update({
        "first_observation_session": GEOMETRY[0],
        "last_observation_session": GEOMETRY[1], "observation_count": GEOMETRY[2]})
    aggregate["execution"].update({
        "decision_count": 61, "submitted_rebalance_count": 61,
        "completed_rebalance_count": 61, "submitted_order_count": 61,
        "filled_order_count_sum": 61, "execution_failure": False})
    for row in aggregate["sleeve_diagnostics"]["rows"]:
        row[2] = 61
    aggregate["fallback_counts"] = {
        key: (366 if index == 0 else 0)
        for index, key in enumerate(aggregate["fallback_counts"])}
    if defect == "old_geometry":
        aggregate["account"]["observation_count"] = 1255
    elif defect == "invalid_order":
        aggregate["execution"]["invalid_order_count_sum"] = 1
    elif defect == "canceled_order":
        aggregate["execution"]["canceled_order_count_sum"] = 1
    elif defect == "missing_fill":
        aggregate["execution"]["filled_order_count_sum"] = 60
    elif defect == "old_baseline":
        aggregate["matched_baseline_profile_sha256"] = common._MATCHED_SETTLEMENT_PROFILE_SHA256
    elif defect == "wrong_tilt":
        aggregate["maximum_stock_weight_change_fraction"] = "0.80"
    raw = common._canonical(aggregate)
    meta = json.loads(values[common.base_runtime.META_STATISTIC_NAME])
    meta.update({"aggregate_schema": candidate.summary_schema,
                 "aggregate_sha256": hashlib.sha256(raw).hexdigest()})
    if defect == "old_package":
        meta["package_sha256"] = "f" * 64
    return {
        common.base_runtime.META_STATISTIC_NAME: common._canonical(meta).decode("ascii"),
        common.base_runtime.AGGREGATES_STATISTIC_NAME: raw.decode("ascii"),
        "Net Profit": "999%",  # Standard QC fields are deliberately discarded.
    }


@pytest.mark.parametrize("candidate_id", tuple(common._RECENT_PERCENTS))
def test_recent_six_candidates_launch_once_and_read_only_exact_geometry(
    offline_recent_projections, monkeypatch, tmp_path, candidate_id,
):
    _install_offline_candidates(monkeypatch, offline_recent_projections)
    projection = offline_recent_projections[candidate_id]
    plan = _prepared(monkeypatch, tmp_path, projection)
    identity = subject.preview(plan, projection)
    assert identity["projection_sha256"] == projection.projection_sha256
    waiver = json.loads(subject.render_owner_waiver_payload(plan, projection))
    assert waiver["comparison_reference_candidate_id"] == "R203"
    assert waiver["evaluation_session_count"] == 290
    assert waiver["decision_count"] == 61
    assert waiver["maximum_result_reads"] == 1
    assert "r195" not in " ".join(waiver)
    calls, state = legacy._fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(plan, projection, object(),
                             owner_waiver_id=common._candidate(plan).waiver_id)
    assert calls.count("backtests/create") == 1
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _recent_statistics(plan, launch)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    assert result["comparison_valid"] is False  # No independently read R203 anchor.
    assert result["aggregates"]["account"]["observation_count"] == 290
    assert result["aggregates"]["execution"]["completed_rebalance_count"] == 61
    assert "999%" not in json.dumps(result)
    before = len(calls)
    with pytest.raises(common.SixUniverseSettlementSubmissionError, match="already claimed"):
        subject.read_aggregates_once(plan, launch, object())
    with pytest.raises(common.SixUniverseSettlementSubmissionError, match="already claimed"):
        subject.launch_a1(plan, projection, object(),
                          owner_waiver_id=common._candidate(plan).waiver_id)
    assert len(calls) == before


@pytest.mark.parametrize("defect", (
    "old_geometry", "invalid_order", "canceled_order", "missing_fill",
    "old_baseline", "wrong_tilt", "old_package",
))
def test_recent_result_each_changed_binding_is_refused_without_valid_receipt(
    offline_recent_projections, monkeypatch, tmp_path, defect,
):
    _install_offline_candidates(monkeypatch, offline_recent_projections)
    projection = offline_recent_projections["R203"]
    plan = _prepared(monkeypatch, tmp_path, projection)
    calls, state = legacy._fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(plan, projection, object(),
                             owner_waiver_id=common._candidate(plan).waiver_id)
    subject.poll_status(plan, launch, object())
    state["statistics"] = _recent_statistics(plan, launch, defect=defect)
    with pytest.raises(common.SixUniverseSettlementSubmissionError):
        subject.read_aggregates_once(plan, launch, object())
    assert common._control_path(plan, "result-read-claim").is_file()
    assert not common._control_path(plan, "result-valid").exists()


@pytest.mark.parametrize("matching_path", (True, False))
def test_recent_comparison_only_uses_authenticated_r203_same_window_anchor(
    offline_recent_projections, monkeypatch, tmp_path, matching_path,
):
    _install_offline_candidates(monkeypatch, offline_recent_projections)
    plans = {}
    for candidate_id in ("R203", "R204"):
        projection = offline_recent_projections[candidate_id]
        plan = _prepared(monkeypatch, tmp_path, projection)
        calls, state = legacy._fake_qc(monkeypatch, plan, projection)
        launch = subject.launch_a1(plan, projection, object(),
                                 owner_waiver_id=common._candidate(plan).waiver_id)
        subject.poll_status(plan, launch, object())
        path = "d" * 64 if candidate_id == "R203" or matching_path else "e" * 64
        state["statistics"] = _recent_statistics(plan, launch, target_path=path)
        result = subject.read_aggregates_once(plan, launch, object())
        plans[candidate_id] = plan
    assert result["comparison_valid"] is matching_path
    comparison = subject.compare_valid_receipts(plans["R204"])
    assert comparison["comparison_valid"] is matching_path
    assert comparison["r203_anchor_attempt"] == 1
    assert "r195_anchor_attempt" not in comparison
    # Even a historical valid-looking result cannot substitute for this anchor.
    common._control_path(plans["R203"], "result-valid").unlink()
    old_receipt = tmp_path / "control" / "R195-A1-result-valid.json"
    common._write(old_receipt, {"run_valid": True, "matched_baseline_target_path_sha256": "d" * 64})
    assert subject.compare_valid_receipts(plans["R204"])["comparison_valid"] is False


@pytest.mark.parametrize("defect", (
    "source", "profile_floor", "profile_start", "profile_decisions",
    "package", "upload_receipt", "waiver",
))
def test_recent_changed_launch_binding_refuses_before_any_qc_or_attempt_claim(
    offline_recent_projections, monkeypatch, tmp_path, defect,
):
    _install_offline_candidates(monkeypatch, offline_recent_projections)
    projection = offline_recent_projections["R203"]
    plan = _prepared(monkeypatch, tmp_path, projection)
    claim_path = common._control_path(plan, "claim")
    calls, _state = legacy._fake_qc(monkeypatch, plan, projection)
    waiver = common._candidate(plan).waiver_id
    if defect == "source":
        item = projection.source_files[0]
        changed = item.source_bytes + b"# changed\n"
        item = dataclasses.replace(item, source_bytes=changed, byte_count=len(changed),
                                  content_sha256=hashlib.sha256(changed).hexdigest())
        projection = dataclasses.replace(projection,
            source_files=(item,) + projection.source_files[1:],
            total_source_byte_count=projection.total_source_byte_count + len(b"# changed\n"))
    elif defect.startswith("profile_"):
        profile = subject.require_profile(100)
        key, value = {
            "profile_floor": ("minimum_stock_and_sleeve_residual_weight", "0"),
            "profile_start": ("evaluation_start_session", "2021-01-04"),
            "profile_decisions": ("decision_count", 261),
        }[defect]
        monkeypatch.setattr(subject, "require_profile", lambda _percent: dict(profile, **{key: value}))
    elif defect == "package":
        plan = dataclasses.replace(plan, package_sha256="f" * 64)
    elif defect == "upload_receipt":
        subject._upload_path(plan, "valid").unlink()
    else:
        waiver = "wrong"
    with pytest.raises(common.SixUniverseSettlementSubmissionError):
        subject.launch_a1(plan, projection, object(), owner_waiver_id=waiver)
    assert calls == []
    assert not claim_path.exists()


def _failed_a1(monkeypatch, tmp_path, projections):
    _install_offline_candidates(monkeypatch, projections)
    monkeypatch.setattr(subject, "_A2_PROJECT_ID", 111)
    monkeypatch.setattr(subject, "_A1_BACKTEST_ID", "tilt40-a1")
    projection = projections["R203"]
    plan = _prepared(monkeypatch, tmp_path, projection)
    calls, state = legacy._fake_qc(monkeypatch, plan, projection)
    original = common._post
    active = {"a2": False}

    def post(api, endpoint, payload):
        result = original(api, endpoint, payload)
        if endpoint == "backtests/create" and payload["backtestName"] != plan.backtest_name:
            active["a2"] = True
        if endpoint in {"backtests/create", "backtests/read"} and active["a2"]:
            result["backtest"].update({"backtestId": "visibility-a2",
                                      "name": plan.backtest_name.replace("R203A1", "R203A2")})
        if endpoint == "backtests/list":
            result["backtests"][0]["status"] = "Completed." if active["a2"] else "Runtime Error"
            if active["a2"]:
                result["backtests"][0].update({"backtestId": "visibility-a2",
                    "name": plan.backtest_name.replace("R203A1", "R203A2")})
        return result

    monkeypatch.setattr(common, "_post", post)
    launch = subject.launch_a1(plan, projection, object(),
                             owner_waiver_id=common._candidate(plan).waiver_id)
    assert subject.poll_status(plan, launch, object()) == "Runtime Error"
    evidence = {
        "schema": "arv2-r203-worker-visibility-retry-evidence-v1",
        "candidate_id": "R203", "failed_attempt": 1, "project_id": 111,
        "backtest_id": "tilt40-a1",
        "organization_id_sha256": hashlib.sha256(plan.organization_id.encode("ascii")).hexdigest(),
        "package_sha256": subject.PINNED_PACKAGE_SHA256,
        "activation_manifest_sha256": subject.PINNED_ACTIVATION_MANIFEST_SHA256,
        "source_files_sha256": common._candidate(plan).source_files_sha256,
        "api_same_org_exact_manifest_metadata_verified": True,
        "project_context_manifest_byte_count": 4523,
        "project_context_evaluator_manifest_readable": True,
        "input_loader_matches_successful_prior_sources": True,
        "initialization_ast_unchanged": True,
        "engine_contains_key_return_unmeasured": True,
        "root_cause_known": False, "source_or_economics_changed": False,
        "retry_hypothesis": "unresolved_transient_worker_visibility",
    }
    common._write(common._control_path(plan, "visibility-evidence"), evidence)
    digest = hashlib.sha256(common._canonical(evidence)).hexdigest()
    return dataclasses.replace(plan, attempt=2), projection, digest, calls, state


def test_visibility_hypothesis_a2_reuses_exact_source_project_and_has_one_read(
    offline_recent_projections, monkeypatch, tmp_path,
):
    plan, projection, digest, calls, state = _failed_a1(monkeypatch, tmp_path, offline_recent_projections)
    waiver = json.loads(subject.render_visibility_a2_waiver(
        plan, projection, visibility_evidence_sha256=digest))
    assert waiver["project_id"] == 111 and waiver["attempt"] == 2
    assert waiver["root_cause_known"] is False
    assert waiver["source_or_economics_changed"] is False
    assert waiver["mutating_endpoint_budget"] == {"compile/create": 1, "backtests/create": 1}
    before = len(calls)
    launch = subject.launch_visibility_a2(plan, projection, object(),
        owner_waiver_id=subject._A2_WAIVER_ID, visibility_evidence_sha256=digest)
    subsequent = calls[before:]
    assert subsequent.count("compile/create") == subsequent.count("backtests/create") == 1
    assert not set(subsequent) & {"projects/create", "files/create", "files/update", "files/delete"}
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _recent_statistics(plan, launch)
    assert subject.read_aggregates_once(plan, launch, object())["run_valid"] is True
    assert subject._valid_comparison_anchor(plan) == (2, "d" * 64)
    with pytest.raises(common.SixUniverseSettlementSubmissionError, match="already claimed"):
        subject.launch_visibility_a2(plan, projection, object(),
            owner_waiver_id=subject._A2_WAIVER_ID, visibility_evidence_sha256=digest)
    with pytest.raises(common.SixUniverseSettlementSubmissionError):
        subject.preview(dataclasses.replace(plan, attempt=3), projection)


@pytest.mark.parametrize("defect", ("evidence", "terminal", "prior_valid", "source", "inventory", "waiver"))
def test_a2_refuses_changed_evidence_predecessor_or_source_without_spending_attempt(
    offline_recent_projections, monkeypatch, tmp_path, defect,
):
    plan, projection, digest, calls, state = _failed_a1(monkeypatch, tmp_path, offline_recent_projections)
    waiver = subject._A2_WAIVER_ID
    a1 = dataclasses.replace(plan, attempt=1)
    if defect == "evidence":
        digest = "0" * 64
    elif defect == "terminal":
        monkeypatch.setattr(common, "_read", lambda _path: {})
    elif defect == "prior_valid":
        common._write(common._control_path(a1, "result-valid"), {"run_valid": True})
    elif defect in {"source", "inventory"}:
        original = common._post

        def post(api, endpoint, payload):
            result = original(api, endpoint, payload)
            if endpoint == "files/read" and defect == "source":
                result["files"][0]["content"] += "# edited"
            if endpoint == "backtests/list" and defect == "inventory":
                result["backtests"].append(dict(result["backtests"][0], backtestId="unexpected"))
                result["count"] = 2
            return result

        monkeypatch.setattr(common, "_post", post)
    else:
        waiver = "wrong"
    before = len(calls)
    with pytest.raises(common.SixUniverseSettlementSubmissionError):
        subject.launch_visibility_a2(plan, projection, object(),
            owner_waiver_id=waiver, visibility_evidence_sha256=digest)
    assert not set(calls[before:]) & {"compile/create", "backtests/create", "files/update"}
    assert not common._control_path(plan, "claim").exists()
