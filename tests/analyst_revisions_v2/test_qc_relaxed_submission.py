"""Focused fake-cloud red/green checks; no credentials, network or outcomes."""

import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as sut


ORG = "a" * 32


def canonical(value):
    return sut.common._canonical(value)


class Projection:
    def __init__(self, raw=b"x = 1\n"):
        digest = hashlib.sha256(raw).hexdigest()
        self.source_files = (SimpleNamespace(project_path="main.py", source_bytes=raw,
            byte_count=len(raw), content_sha256=digest),)
        self.schema = "test-projection-v1"
        self.profile_id, self.profile_sha256 = "test-profile", "b" * 64
        self.package_sha256, self.activation_manifest_sha256 = "c" * 64, "d" * 64
        self.total_source_byte_count = len(raw)
        self.projection_id = "test-projection"
        self.projection_sha256 = sut._sha(self.semantic())

    def semantic(self):
        return {"schema": self.schema, "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256, "package_sha256": self.package_sha256,
            "activation_manifest_sha256": self.activation_manifest_sha256,
            "total_source_byte_count": self.total_source_byte_count,
            "source_files": [[item.project_path, item.content_sha256, item.byte_count]
                             for item in self.source_files]}

    def to_record(self):
        return {**self.semantic(), "projection_id": self.projection_id,
                "projection_sha256": self.projection_sha256}


class Fake:
    def __init__(self):
        self.calls, self.files, self.created = [], {}, False
        self.compile_state, self.status = "BuildSuccess", "In Progress..."
        self.collaborators = [{"owner": True}]
        self.statistics = {}
        self.runs = []

    def post(self, api, endpoint, body):
        self.calls.append((endpoint, body))
        if endpoint == "authenticate":
            return {}
        if endpoint == "projects/create":
            self.created = True
            self.name = body["name"]
            self.files = {"main.py": "default = 1\n", "research.ipynb": "{}"}
            return {"projects": [{"projectId": 123}]}
        if endpoint == "projects/read":
            rows = ([{"projectId": 123, "name": self.name, "organizationId": ORG,
                "language": "Py", "owner": True, "codeRunning": False,
                "collaborators": self.collaborators}] if self.created else [])
            return {"projects": rows}
        if endpoint == "files/read":
            return {"files": [{"projectId": 123, "name": name, "content": raw}
                              for name, raw in self.files.items()]}
        if endpoint == "files/delete":
            del self.files[body["name"]]
            return {}
        if endpoint in {"files/update", "files/create"}:
            self.files[body["name"]] = body["content"]
            return {}
        if endpoint == "compile/create":
            return {"compileId": "compile-1"}
        if endpoint == "compile/read":
            return {"compileId": "compile-1", "state": self.compile_state}
        if endpoint == "backtests/create":
            self.backtest_name = body["backtestName"]
            self.runs.append({"projectId": 123, "backtestId": "run-1",
                "name": self.backtest_name, "status": self.status})
            return {"backtest": {"projectId": 123, "backtestId": "run-1",
                "name": self.backtest_name, "status": self.status}}
        if endpoint == "backtests/list":
            assert body["includeStatistics"] is False
            return {"count": len(self.runs), "backtests": [{**row, "status": self.status} for row in self.runs]}
        if endpoint == "backtests/read":
            return {"backtest": {"projectId": 123, "backtestId": "run-1",
                "name": self.backtest_name, "status": self.status,
                "statistics": self.statistics, "orders": "NOT RETAINED"}}
        raise AssertionError(endpoint)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    projection = Projection()
    row = {"candidate_id": "R209", "project_name": "131 ARV2 TEST COVERAGE",
        "backtest_name": "ARV2 R209 coverage", "kind": "coverage", "role": "coverage",
        "projection_schema": projection.schema, "projection_sha256": projection.projection_sha256,
        "profile_id": projection.profile_id, "profile_sha256": projection.profile_sha256,
        "source_file_count": 1, "total_source_bytes": projection.total_source_byte_count,
        "source_files_sha256": sut._sha(projection.semantic()["source_files"]),
        "statistic_names": ["ARV2_SIX_COVERAGE_META"] + ["ARV2_SIX_COVERAGE_" + ticker for ticker in sut._TICKERS],
        "meta_schema": "test-meta-v1", "sleeve_schema": "test-sleeve-v1", "summary_schema": "test"}
    manifest = {"schema": "test-family-v1", "package_sha256": projection.package_sha256,
        "activation_manifest_sha256": projection.activation_manifest_sha256,
        "input_control_directory": str(tmp_path), "candidates": [row]}
    path = tmp_path / "manifest.json"
    path.write_bytes(canonical(manifest))
    monkeypatch.setattr(sut, "MANIFEST_PATH", path)
    monkeypatch.setattr(sut, "FROZEN_MANIFEST_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(sut, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(sut.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(sut.common, "_post", fake.post)
    plan = sut.build_plan("R209", ORG, tmp_path / "control")
    return plan, projection, fake, row


def coverage_stats(row):
    sleeves = [{"schema": row["sleeve_schema"], "universe_id": ticker,
        "totals": {"decision_count": 61}, "years": [{"year": 2025, "decision_count": 22},
            {"year": 2026, "decision_count": 39}]} for ticker in sut._TICKERS]
    meta = {"schema": row["meta_schema"], "profile_id": row["profile_id"],
        "profile_sha256": row["profile_sha256"], "package_sha256": "c" * 64,
        "activation_manifest_sha256": "d" * 64, "decision_count": 61,
        "sleeve_decision_count": 366, "raw_rows_or_identifiers_emitted": False,
        "price_or_return_access": False, "orders": False, "backtest_only": True,
        "sleeve_sha256s": {ticker: sut._sha(sleeve) for ticker, sleeve in zip(sut._TICKERS, sleeves)},
        "aggregate_sha256": sut._sha(sleeves)}
    return {"ARV2_SIX_COVERAGE_META": canonical(meta).decode("ascii"),
        **{"ARV2_SIX_COVERAGE_" + ticker: canonical(sleeve).decode("ascii")
           for ticker, sleeve in zip(sut._TICKERS, sleeves)}}


def test_launch_claim_precedes_first_mutation_and_persists_project(frozen, monkeypatch):
    plan, projection, fake, row = frozen
    real = fake.post
    def checked(api, endpoint, body):
        if endpoint in {"projects/create", "files/delete", "files/create", "files/update", "compile/create", "backtests/create"}:
            assert sut._path(plan, "claim").exists()
        if endpoint in {"files/delete", "files/create", "files/update", "compile/create", "backtests/create"}:
            assert sut._path(plan, "project").exists()
        return real(api, endpoint, body)
    monkeypatch.setattr(sut.common, "_post", checked)
    launch = sut.launch(plan, projection, fake)
    assert launch["project_id"] == 123
    assert fake.files == {"main.py": "x = 1\n"}
    with pytest.raises(sut.RelaxedQcSubmissionError, match="consumed"):
        sut.launch(plan, projection, fake)


@pytest.mark.parametrize("attempt", [0, 4, True])
def test_attempt_bound(frozen, attempt):
    plan, _, _, _ = frozen
    with pytest.raises(sut.RelaxedQcSubmissionError, match="bound"):
        sut._candidate(dataclasses.replace(plan, attempt=attempt))


def test_future_import_fails_before_any_api(frozen, monkeypatch):
    plan, _, fake, row = frozen
    projection = Projection(b"from __future__ import annotations\n")
    family = json.loads(sut.MANIFEST_PATH.read_bytes())
    row = family["candidates"][0]
    row.update(projection_sha256=projection.projection_sha256,
        source_files_sha256=sut._sha(projection.semantic()["source_files"]),
        total_source_bytes=projection.total_source_byte_count)
    sut.MANIFEST_PATH.write_bytes(canonical(family))
    monkeypatch.setattr(sut, "FROZEN_MANIFEST_SHA256", hashlib.sha256(sut.MANIFEST_PATH.read_bytes()).hexdigest())
    with pytest.raises(sut.RelaxedQcSubmissionError, match="prelude"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_manifest_corruption_refused(frozen):
    plan, projection, fake, _ = frozen
    sut.MANIFEST_PATH.write_bytes(b"{}")
    with pytest.raises(sut.RelaxedQcSubmissionError, match="manifest"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_compile_failure_spends_slot_and_retry_reuses_project(frozen):
    plan, projection, fake, _ = frozen
    fake.compile_state = "BuildError"
    with pytest.raises(sut.RelaxedQcSubmissionError, match="compile failed"):
        sut.launch(plan, projection, fake)
    assert sut._path(plan, "claim").exists()
    fake.compile_state = "BuildSuccess"
    second = dataclasses.replace(plan, attempt=2)
    launch = sut.launch(second, projection, fake)
    assert launch["project_id"] == 123
    assert sum(endpoint == "projects/create" for endpoint, _ in fake.calls) == 1


def test_nonterminal_retry_refused(frozen):
    plan, projection, fake, _ = frozen
    sut.launch(plan, projection, fake)
    before = len(fake.calls)
    with pytest.raises(sut.common.SixUniverseSettlementSubmissionError):
        sut.launch(dataclasses.replace(plan, attempt=2), projection, fake)
    assert len(fake.calls) == before


def test_collaborator_refused_after_atomic_project_receipt(frozen):
    plan, projection, fake, _ = frozen
    fake.collaborators.append({"owner": False})
    with pytest.raises(sut.RelaxedQcSubmissionError, match="private"):
        sut.launch(plan, projection, fake)
    assert sut._path(plan, "project").exists()
    assert not any(endpoint == "compile/create" for endpoint, _ in fake.calls)


def test_result_one_read_bounded_custom_only(frozen):
    plan, projection, fake, row = frozen
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    assert sut.poll_status(plan, launch, fake) == "Completed."
    fake.statistics = {**coverage_stats(row), "Net Profit": "DO NOT RETAIN"}
    result = sut.read_result_once(plan, launch, fake)
    assert result["run_valid"] is True
    assert "Net Profit" not in str(result)
    assert "NOT RETAINED" not in str(result)
    with pytest.raises(sut.common.SixUniverseSettlementSubmissionError):
        sut.read_result_once(plan, launch, fake)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1


def test_source_changed_refuses_before_outcome_read(frozen):
    plan, projection, fake, row = frozen
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    fake.files["main.py"] += "x = 2\n"
    with pytest.raises(sut.RelaxedQcSubmissionError, match="bytes"):
        sut.read_result_once(plan, launch, fake)
    assert not any(endpoint == "backtests/read" for endpoint, _ in fake.calls)


def test_bad_digest_still_consumes_one_read(frozen):
    plan, projection, fake, row = frozen
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    fake.statistics = coverage_stats(row)
    meta = json.loads(fake.statistics["ARV2_SIX_COVERAGE_META"])
    meta["aggregate_sha256"] = "e" * 64
    fake.statistics["ARV2_SIX_COVERAGE_META"] = canonical(meta).decode("ascii")
    with pytest.raises(sut.RelaxedQcSubmissionError, match="digest"):
        sut.read_result_once(plan, launch, fake)
    assert sut._path(plan, "read-claim").exists()
    assert sut._path(plan, "raw-custom").exists()


@pytest.mark.parametrize("value", ["{} ", "[]", "{\"x\":NaN}", "é", " " * 8193])
def test_noncanonical_or_oversized_statistic_refused(value):
    with pytest.raises((sut.RelaxedQcSubmissionError, ValueError)):
        sut._statistic(value)


def test_new_named_diagnostics_bound_without_legacy_global_mutation(monkeypatch):
    new_status = "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK"
    new_reason = "KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM"
    aggregate = {key: None for key in sut.cap._AGGREGATE_FIELDS}
    aggregate["fallback_counts"] = {new_status: 366}
    aggregate["sleeve_diagnostics"] = {"rows": [
        [ticker, ticker, 61, 1, 60, 0, 1, 1, "0.1", "0", {new_reason: 60}, {new_status: 61}]
        for ticker in sut._TICKERS]}
    original_statuses, original_reasons = sut.cap._SELECTION_STATUSES, sut.cap._COVERAGE_REASONS
    def validator(base, *, expected_geometry):
        assert new_status not in base["fallback_counts"]
        assert base["fallback_counts"]["PARTIAL_STOCK_SLOTS_WITH_ETF_FALLBACK"] == 366
        for row in base["sleeve_diagnostics"]["rows"]:
            assert row[10] == {"MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM": 60}
            assert row[11] == {"PARTIAL_STOCK_SLOTS_WITH_ETF_FALLBACK": 61}
        return base
    monkeypatch.setattr(sut.cap, "_project_aggregate", validator)
    retained = sut._bounded_order_base(aggregate)
    assert retained["fallback_counts"] == {new_status: 366}
    assert retained["sleeve_diagnostics"]["rows"][0][10] == {new_reason: 60}
    assert sut.cap._SELECTION_STATUSES is original_statuses
    assert sut.cap._COVERAGE_REASONS is original_reasons
    assert aggregate["fallback_counts"] == {new_status: 366}
    aggregate["fallback_counts"] = {"UNKNOWN_ARBITRARY_STATUS": 366}
    with pytest.raises(sut.RelaxedQcSubmissionError, match="named state"):
        sut._bounded_order_base(aggregate)


def test_stage_two_preserves_exact_stage_one_candidate_claim(frozen, monkeypatch):
    plan, projection, fake, row = frozen
    launch = sut.launch(plan, projection, fake)
    old_pin = sut.FROZEN_MANIFEST_SHA256
    family = json.loads(sut.MANIFEST_PATH.read_bytes())
    family["candidates"].extend([{**row, "candidate_id": "R" + str(number)} for number in range(210, 220)])
    sut.MANIFEST_PATH.write_bytes(canonical(family))
    monkeypatch.setattr(sut, "PREDECESSOR_MANIFEST_SHA256", old_pin)
    monkeypatch.setattr(sut, "FROZEN_MANIFEST_SHA256", hashlib.sha256(sut.MANIFEST_PATH.read_bytes()).hexdigest())
    assert sut._receipt(plan, launch)["manifest_sha256"] == old_pin
    family["candidates"][0]["profile_sha256"] = "f" * 64
    sut.MANIFEST_PATH.write_bytes(canonical(family))
    monkeypatch.setattr(sut, "FROZEN_MANIFEST_SHA256", hashlib.sha256(sut.MANIFEST_PATH.read_bytes()).hexdigest())
    with pytest.raises(sut.RelaxedQcSubmissionError, match="claim"):
        sut._receipt(plan, launch)


def order_fixture():
    from tests.analyst_revisions_v2 import test_qc_six_universe_settlement_submission as legacy
    aggregate, _ = legacy._aggregate("R195")
    aggregate.update(schema="relaxed-summary", role="matched_revision_tilt20_relaxed_recent",
        profile_id="relaxed-profile", profile_sha256="a" * 64,
        maximum_stock_weight_change_fraction="0.20", matched_baseline_profile_sha256="b" * 64)
    aggregate["account"].update(first_observation_session=sut._GEOMETRY[0],
        last_observation_session=sut._GEOMETRY[1], observation_count=290)
    aggregate["execution"].update(decision_count=61, submitted_rebalance_count=61,
        completed_rebalance_count=61, submitted_order_count=61, filled_order_count_sum=61)
    aggregate["fallback_counts"] = {"PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK": 366}
    for row in aggregate["sleeve_diagnostics"]["rows"]:
        row[2] = 61
        row[10] = {"KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM": 61}
        row[11] = {"PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK": 61}
    candidate = {"role": aggregate["role"], "summary_schema": aggregate["schema"],
        "profile_id": aggregate["profile_id"], "profile_sha256": aggregate["profile_sha256"],
        "tilt_fraction": "0.20", "matched_baseline_profile_sha256": "b" * 64,
        "statistic_names": ["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES"],
        "meta_schema": "test-order-meta"}
    meta = {key: None for key in sut.cap._META_FIELDS}
    meta.update(schema=candidate["meta_schema"], role=candidate["role"],
        profile_id=candidate["profile_id"], profile_sha256=candidate["profile_sha256"],
        package_sha256="c" * 64, activation_manifest_sha256="d" * 64,
        aggregate_schema=candidate["summary_schema"],
        result_transport="two_bounded_custom_summary_statistics",
        raw_provider_rows=False, raw_price_rows=False, raw_order_rows=False,
        formal=False, trading=False, preliminary=True, backtest_only=True)
    return aggregate, candidate, meta


@pytest.mark.parametrize("defect", [None, "invalid_order", "tracking", "negative_cash",
    "event_count", "event_minimum", "missing_fill", "wrong_tilt", "wrong_hash"])
def test_real_order_parser_isolates_new_generation_cash_execution_and_digest(monkeypatch, defect):
    aggregate, row, meta = order_fixture()
    if defect == "invalid_order":
        aggregate["execution"]["invalid_order_count_sum"] = 1
    elif defect == "tracking":
        aggregate["execution"]["mean_target_weight_l1_error"] = "0.03"
    elif defect == "negative_cash":
        aggregate["minimum_end_day_cash"] = "-1"
    elif defect == "event_count":
        aggregate["order_event_cash_observation_count"] = True
    elif defect == "event_minimum":
        aggregate["minimum_observed_order_event_cash"] = "25"
    elif defect == "missing_fill":
        aggregate["execution"]["filled_order_count_sum"] = 60
    elif defect == "wrong_tilt":
        aggregate["maximum_stock_weight_change_fraction"] = "0.40"
    raw = canonical(aggregate).decode("ascii")
    meta["aggregate_sha256"] = "0" * 64 if defect == "wrong_hash" else hashlib.sha256(raw.encode("ascii")).hexdigest()
    stats = {"ARV2_SIX_GATE_ORDER_META": canonical(meta).decode("ascii"),
             "ARV2_SIX_GATE_ORDER_AGGREGATES": raw}
    monkeypatch.setattr(sut, "_candidate", lambda plan: row)
    monkeypatch.setattr(sut, "_manifest", lambda: {"package_sha256": "c" * 64, "activation_manifest_sha256": "d" * 64})
    if defect:
        with pytest.raises((sut.RelaxedQcSubmissionError, sut.cap.Cap90QcSubmissionError)):
            sut._parse_order(object(), stats)
    else:
        result = sut._parse_order(object(), stats)
        assert result["run_valid"] is True
        assert result["aggregates"]["fallback_counts"] == aggregate["fallback_counts"]


def test_seven_maximum_custom_strings_fit_private_artifact(tmp_path):
    raw = canonical({"p": "\\" * 4092}).decode("ascii")
    assert len(raw) == 8192
    value = {"statistics": {str(index): raw for index in range(7)}}
    assert len(canonical(value)) > 16 * 1024
    path = tmp_path / "custom.json"
    sut._write_artifact(path, value)
    assert sut._read_artifact(path) == value
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(sut.RelaxedQcSubmissionError, match="spent"):
        sut._write_artifact(path, value)


def test_private_artifact_inclusive_boundary_and_symlink_refusal(tmp_path):
    exact = {"p": "x" * (sut.MAXIMUM_ARTIFACT_BYTES - len(canonical({"p": ""})))}
    path = tmp_path / "exact.json"
    sut._write_artifact(path, exact)
    assert len(path.read_bytes()) == sut.MAXIMUM_ARTIFACT_BYTES
    assert sut._read_artifact(path) == exact
    with pytest.raises(sut.RelaxedQcSubmissionError, match="oversized"):
        sut._write_artifact(tmp_path / "too-big.json", {"p": exact["p"] + "x"})
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="unavailable"):
        sut._read_artifact(link)


def test_r209_transport_recovery_is_exact_one_time_without_relaunch(frozen, monkeypatch):
    plan, projection, fake, row = frozen
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    expected = sut.common._read(sut._path(plan, "terminal"))
    sut.common._write(sut._path(plan, "read-claim"), expected)
    fake.statistics = coverage_stats(row)
    monkeypatch.setattr(sut, "_R209_RECOVERY_IDENTITY", (123, "run-1"))
    result = sut.read_result_once(plan, launch, fake, recover_r209_transport=True)
    assert result["run_valid"] is True
    assert sut.common._read(sut._path(plan, "read-claim")) == expected
    assert sut._path(plan, "recovery-read-claim").exists()
    with pytest.raises(sut.RelaxedQcSubmissionError, match="recovery"):
        sut.read_result_once(plan, launch, fake, recover_r209_transport=True)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1
    assert sum(endpoint == "backtests/create" for endpoint, _ in fake.calls) == 1


def test_retry_census_refuses_untracked_manual_or_mia_run(frozen):
    plan, projection, fake, _ = frozen
    fake.compile_state = "BuildError"
    with pytest.raises(sut.RelaxedQcSubmissionError, match="compile failed"):
        sut.launch(plan, projection, fake)
    fake.runs.append({"projectId": 123, "backtestId": "owner-manual-run", "name": "owner run", "status": "Completed."})
    with pytest.raises(sut.RelaxedQcSubmissionError, match="untracked"):
        sut.launch(dataclasses.replace(plan, attempt=2), projection, fake)
    assert not sut._path(dataclasses.replace(plan, attempt=2), "claim").exists()


def test_frozen_manifest_hash_binds_every_byte_not_only_shape(frozen):
    """A shape-identical manifest whose bytes differ from the frozen digest
    must refuse before any QC call. The census check alone would admit an
    edited row, which is the attempt-renaming escape the freeze closes."""

    plan, projection, fake, row = frozen
    value = json.loads(sut.MANIFEST_PATH.read_bytes())
    value["candidates"][0]["project_name"] = row["project_name"] + " EDITED"
    sut.MANIFEST_PATH.write_bytes(canonical(value))
    with pytest.raises(sut.RelaxedQcSubmissionError, match="frozen manifest"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []
