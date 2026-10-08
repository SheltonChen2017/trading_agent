"""Private fixture bundles prove look admission; no actual bundle is created."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket

import pytest

from research.target_price_revisions_development import raw_run as controller

NOW = datetime(2026, 10, 7, 8, tzinfo=timezone.utc)
_REAL_VERIFY_CODE = controller._verify_code
_REAL_LOAD_CANDIDATE = controller._load_candidate
_REAL_PREPARE_STRUCTURE = controller._prepare_structure


def rights():
    return {"schema": "tpr-raw-rights-v1", "candidate_id": controller.CANDIDATE_ID,
        "personal_only": True, "quantconnect": False,
        "grants": [{"provider_dataset": dataset, "local_retention": True, "derived_processing": True,
            "evidence_sha256": "e" * 64, "evidence_classification":
                "account-specific-agreement" if dataset.startswith("Massive:") else "vendor-published-terms"}
            for dataset in controller._RIGHTS_DATASETS]}


def owner_waiver():
    instruction = "other lanes have been using those data. skip the rights part. start backtesting immediately"
    return {"schema": "tpr-raw-owner-waiver-v1", "candidate_id": controller.CANDIDATE_ID,
        "owner_decision": "TPR-OWN-36", "owner_instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
        "personal_only": True, "quantconnect": False, "canonical_admission": False,
        "contractual_rights_verified": False, "datasets": list(controller._RIGHTS_DATASETS)}


def structure():
    return {"schema": "tpr-raw-structure-v1", "capture_utc": NOW.isoformat(), "calendar": [
        {"session_date": "2024-12-31", "open_utc": "2024-12-31T14:30:00Z", "close_utc": "2024-12-31T21:00:00Z"},
        {"session_date": "2025-01-02", "open_utc": "2025-01-02T14:30:00Z", "close_utc": "2025-01-02T21:00:00Z"}],
        "ratings": [], "identities": [], "actions": [], "action_inventory_complete": True}


@pytest.fixture(autouse=True)
def no_external_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("unexpected actual process or network access")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(controller.subprocess, "run", forbidden)
    monkeypatch.setattr(controller, "_now", lambda: NOW)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    bodies = {"rights.json": rights(), "structure.json": structure(),
        "outcomes.json": {"schema": "tpr-raw-outcomes-v1", "sessions": []}}
    for name, body in bodies.items():
        path = root / name
        path.write_bytes(controller._canonical(body))
        path.chmod(0o600)
    monkeypatch.setattr(controller, "_verify_code", lambda _: None)
    # Admission unit tests isolate the filesystem state machine. The connected
    # candidate test below restores both exact code and pure source validation.
    monkeypatch.setattr(controller, "_prepare_structure", lambda _: None)
    monkeypatch.setattr(controller, "_load_candidate", lambda: lambda structure, outcomes: {
        "schema": "synthetic-test-result", "complete": True, "source_rows": len(structure["ratings"]),
        "sessions": len(outcomes["sessions"])})
    return root


def spec(root, **changes):
    values = dict(structure_sha256=hashlib.sha256((root / "structure.json").read_bytes()).hexdigest(),
        outcomes_sha256=hashlib.sha256((root / "outcomes.json").read_bytes()).hexdigest(),
        rights_sha256=hashlib.sha256((root / "rights.json").read_bytes()).hexdigest(),
        code_hashes={name: "a" * 64 for name in controller.CODE_FILES},
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")
    values.update(changes)
    return controller.freeze_run_spec(**values)


def replace_body(root, name, change):
    body = json.loads((root / name).read_bytes())
    change(body)
    (root / name).write_bytes(controller._canonical(body))


def test_reservation_is_durable_before_any_outcome_read_hash_parse_runner_load_or_dispatch(bundle, monkeypatch):
    frozen = spec(bundle)
    sequence = []
    real_read, real_decode = controller._read_file, controller._decode
    def read(directory_fd, name, *args):
        sequence.append(name)
        if name == "outcomes.json":
            reservation = json.loads((bundle / (controller.CANDIDATE_ID + ".spent.json")).read_bytes())
            assert reservation["config"]["view"] == "censored"
            assert reservation["config"]["development_looks"] == 1
            assert reservation["development_look_reserved"] == 0 and reservation["fixture_runs"] == 1
            assert reservation["outcomes_sha256"] == json.loads(frozen)["outcomes_sha256"]
        return real_read(directory_fd, name, *args)
    def load():
        assert sequence == ["rights.json", "structure.json", "outcomes.json"]
        sequence.append("runner_load")
        def run(structure, outcomes):
            sequence.append("dispatch")
            assert outcomes["schema"] == "tpr-raw-outcomes-v1"
            return {"complete": True}
        return run
    monkeypatch.setattr(controller, "_read_file", read)
    monkeypatch.setattr(controller, "_load_candidate", load)
    result = controller._execute_fixture_run(frozen, bundle)
    assert sequence == ["rights.json", "structure.json", "outcomes.json", "runner_load", "dispatch"]
    assert result.status == "COMPLETED"
    assert result.report_sha256 == hashlib.sha256(result.report_path.read_bytes()).hexdigest()
    terminal = real_decode(result.terminal_path.read_bytes(), 65536)
    assert terminal["development_look_spent"] == 0
    assert terminal["fixture_runs"] == 1
    assert terminal["quantconnect_attempts"] == 0 and terminal["canonical_admission"] is False
    for path in bundle.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600


def test_changed_spec_hash_does_not_rearm_fixed_candidate(bundle, monkeypatch):
    first = spec(bundle)
    controller._execute_fixture_run(first, bundle)
    second = spec(bundle, expires_utc=(NOW + timedelta(hours=25)).isoformat())
    assert first != second
    real_read = controller._read_file
    def read(fd, name, *args):
        assert name != "outcomes.json"
        return real_read(fd, name, *args)
    monkeypatch.setattr(controller, "_read_file", read)
    with pytest.raises(controller.RawRunError, match="already spent"):
        controller._execute_fixture_run(second, bundle)


@pytest.mark.parametrize("mutation", [
    lambda body: body["grants"][0].update(evidence_classification="vendor-published-terms"),
    lambda body: body.update(personal_only=1),
    lambda body: body.update(quantconnect=True),
    lambda body: body["grants"].pop(),
    lambda body: body["grants"][0].update(derived_processing=False),
    lambda body: body["grants"][0].update(provider_dataset="Sharadar:TICKERS"),
    lambda body: body["grants"][0].update(evidence_sha256="invalid"),
])
def test_missing_or_inapplicable_rights_refuse_before_reservation_and_outcomes(bundle, monkeypatch, mutation):
    replace_body(bundle, "rights.json", mutation)
    frozen = spec(bundle)
    real_read = controller._read_file
    def read(fd, name, *args):
        assert name == "rights.json"
        return real_read(fd, name, *args)
    monkeypatch.setattr(controller, "_read_file", read)
    with pytest.raises(controller.RawRunError):
        controller._execute_fixture_run(frozen, bundle)
    assert not (bundle / (controller.CANDIDATE_ID + ".spent.json")).exists()


@pytest.mark.parametrize("mutation", [
    lambda body: body.update(extra=True),
    lambda body: body.update(calendar=[]),
    lambda body: body.update(ratings=[{"ticker": "SYNTHETIC"}]),
    lambda body: body["calendar"][0].update(session_date="2024-07-31"),
    lambda body: body["calendar"][0].update(session_date="2025-04-01"),
    lambda body: body["calendar"][0].update(open_utc="2024-12-31T22:30:00Z"),
    lambda body: body.update(action_inventory_complete="yes"),
    lambda body: body.update(capture_utc=(NOW + timedelta(hours=1)).isoformat()),
])
def test_structure_refusal_does_not_spend_or_open_outcomes(bundle, monkeypatch, mutation):
    replace_body(bundle, "structure.json", mutation)
    frozen = spec(bundle)
    real_read = controller._read_file
    def read(fd, name, *args):
        assert name != "outcomes.json"
        return real_read(fd, name, *args)
    monkeypatch.setattr(controller, "_read_file", read)
    with pytest.raises(controller.RawRunError):
        controller._execute_fixture_run(frozen, bundle)
    assert not (bundle / (controller.CANDIDATE_ID + ".spent.json")).exists()


def test_outcome_hash_mismatch_is_spent_and_terminal_without_candidate_import(bundle, monkeypatch):
    frozen = spec(bundle, outcomes_sha256="b" * 64)
    monkeypatch.setattr(controller, "_load_candidate", lambda: pytest.fail("import after wrong outcome hash"))
    result = controller._execute_fixture_run(frozen, bundle)
    assert result.status == "FAILED" and result.report_path is None
    terminal = json.loads(result.terminal_path.read_bytes())
    assert terminal["failure"] == "candidate_failed" and terminal["development_look_spent"] == 0
    with pytest.raises(controller.RawRunError, match="already spent"):
        controller._execute_fixture_run(spec(bundle), bundle)


@pytest.mark.parametrize("failure", [RuntimeError("PRIVATE licensed row"), KeyboardInterrupt("PRIVATE secret")])
def test_failed_and_interrupted_runs_have_sanitized_terminal_and_cannot_repeat(bundle, monkeypatch, failure):
    def runner(*_args):
        raise failure
    monkeypatch.setattr(controller, "_load_candidate", lambda: runner)
    frozen = spec(bundle)
    if isinstance(failure, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt, match="look remains spent"):
            controller._execute_fixture_run(frozen, bundle)
        expected = "INTERRUPTED"
    else:
        assert controller._execute_fixture_run(frozen, bundle).status == "FAILED"
        expected = "FAILED"
    terminal = (bundle / (controller.CANDIDATE_ID + ".terminal.json")).read_bytes()
    assert b"PRIVATE" not in terminal and json.loads(terminal)["status"] == expected
    with pytest.raises(controller.RawRunError, match="already spent"):
        controller._execute_fixture_run(frozen, bundle)


@pytest.mark.parametrize("name", ["rights.json", "structure.json", "outcomes.json"])
def test_incorrect_private_file_permissions_refuse(bundle, name):
    frozen = spec(bundle)
    (bundle / name).chmod(0o644)
    if name == "outcomes.json":
        assert controller._execute_fixture_run(frozen, bundle).status == "FAILED"
    else:
        with pytest.raises(controller.RawRunError, match="custody"):
            controller._execute_fixture_run(frozen, bundle)


def test_symlinked_input_and_parent_paths_refuse_without_following(bundle):
    frozen = spec(bundle)
    original = bundle / "rights.json"
    destination = bundle / "renamed-rights.json"
    original.rename(destination)
    original.symlink_to(destination)
    with pytest.raises(controller.RawRunError, match="input unavailable"):
        controller._execute_fixture_run(frozen, bundle)
    link = bundle.parent / "linked"
    link.symlink_to(bundle, target_is_directory=True)
    with pytest.raises(controller.RawRunError, match="private run root"):
        controller._execute_fixture_run(frozen, link)


@pytest.mark.parametrize("payload", [b'{"schema":"x","schema":"x"}\n',
    b'{"number":1.5}\n', b'{"number":NaN}\n', b'{"number": 1}\n'])
def test_strict_json_refuses_duplicates_floats_constants_and_noncanonical_encoding(payload):
    with pytest.raises(controller.RawRunError):
        controller._decode(payload, 65536)


@pytest.mark.parametrize("changes", [
    {"rights_sha256": True}, {"mode": "unknown"},
    {"expires_utc": NOW.isoformat()}, {"expires_utc": (NOW + timedelta(hours=49)).isoformat()},
    {"code_hashes": {"raw_candidate.py": "a" * 64}},
])
def test_invalid_run_spec_refuses(bundle, changes):
    with pytest.raises(controller.RawRunError):
        spec(bundle, **changes)


def test_spec_policy_cannot_be_mutated_even_if_json_is_canonical(bundle):
    body = json.loads(spec(bundle))
    body["config"]["view"] = "current"
    with pytest.raises(controller.RawRunError, match="fixed candidate policy"):
        controller._execute_fixture_run(controller._canonical(body), bundle)
    assert not (bundle / (controller.CANDIDATE_ID + ".spent.json")).exists()


def test_preflight_does_not_read_data_and_presence_does_not_assert_ready(bundle, monkeypatch):
    monkeypatch.setattr(controller, "_read_file", lambda *_: pytest.fail("preflight input read"))
    monkeypatch.setattr(controller, "_load_candidate", lambda: pytest.fail("preflight candidate import"))
    result = controller.preflight(bundle, mode="offline-fixture")
    assert result["ready"] is False and result["outcomes_read"] is False
    assert result["development_looks"] == 0
    assert set(result["inputs"].values()) == {"present_unverified"}
    (bundle / "rights.json").unlink()
    assert controller.preflight(bundle, mode="offline-fixture")["inputs"]["rights.json"] == "missing"


def test_offline_mode_cannot_use_production_directory_before_open(monkeypatch):
    with pytest.raises(controller.RawRunError, match="mode disagree"):
        controller._open_root(controller.PRODUCTION_ROOT, "offline-fixture")


def test_immutable_report_publication_never_replaces_existing_file(bundle):
    descriptor = controller._open_root(bundle, "offline-fixture")
    try:
        controller._publish(descriptor, "fixed.json", b"first")
        with pytest.raises(controller.RawRunError, match="publication failed"):
            controller._publish(descriptor, "fixed.json", b"second")
    finally:
        os.close(descriptor)
    assert (bundle / "fixed.json").read_bytes() == b"first"
    assert not list(bundle.glob(".raw-pending-*"))


def test_each_provider_evidence_classification_is_specific_and_hash_bound(bundle):
    source = rights()
    controller._rights(source)
    source["grants"][0]["evidence_classification"] = "written-vendor-clarification"
    controller._rights(source)
    source["grants"][0]["evidence_classification"] = "vendor-published-terms"
    with pytest.raises(controller.RawRunError, match="agreement applicability"):
        controller._rights(source)


def test_owner_waiver_is_explicit_in_result_and_receipts_not_a_contractual_grant(bundle):
    (bundle / "rights.json").write_bytes(controller._canonical(owner_waiver()))
    frozen = spec(bundle)
    result = controller._execute_fixture_run(frozen, bundle)
    assert result.status == "COMPLETED"
    assert result.source_admission == "explicit-owner-waiver"
    assert result.owner_decision == "TPR-OWN-36"
    assert result.contractual_rights_verified is False
    for name in (controller.CANDIDATE_ID + ".spent.json", controller.CANDIDATE_ID + ".terminal.json"):
        receipt = json.loads((bundle / name).read_bytes())
        assert receipt["source_admission"] == {"basis": "explicit-owner-waiver", "owner_decision": "TPR-OWN-36",
            "contractual_rights_verified": False}
    with pytest.raises(controller.RawRunError, match="already spent"):
        controller._execute_fixture_run(frozen, bundle)


@pytest.mark.parametrize("mutation", [
    lambda body: body.update(owner_decision="TPR-OWN-35"),
    lambda body: body.update(owner_instruction_sha256="a" * 64),
    lambda body: body.update(candidate_id="another-candidate"),
    lambda body: body.update(personal_only=1),
    lambda body: body.update(quantconnect=0),
    lambda body: body.update(quantconnect=True),
    lambda body: body.update(canonical_admission=True),
    lambda body: body.update(contractual_rights_verified=True),
    lambda body: body["datasets"].pop(),
    lambda body: body["datasets"].append("Massive:earnings"),
    lambda body: body["datasets"].__setitem__(0, "Sharadar:TICKERS"),
    lambda body: body.update(grants=[]),
])
def test_invalid_owner_waiver_refuses_before_source_or_outcomes_or_claim(bundle, monkeypatch, mutation):
    body = owner_waiver()
    mutation(body)
    (bundle / "rights.json").write_bytes(controller._canonical(body))
    frozen = spec(bundle)
    real_read = controller._read_file
    def read(fd, name, *args):
        assert name == "rights.json"
        return real_read(fd, name, *args)
    monkeypatch.setattr(controller, "_read_file", read)
    with pytest.raises(controller.RawRunError):
        controller._execute_fixture_run(frozen, bundle)
    assert not (bundle / (controller.CANDIDATE_ID + ".spent.json")).exists()


def test_owner_waiver_never_passes_the_unchanged_evidence_manifest_validator():
    with pytest.raises(controller.RawRunError, match="source rights"):
        controller._rights(owner_waiver())


def test_owner_waiver_cannot_replace_a_different_hash_bound_manifest(bundle):
    frozen = spec(bundle)
    (bundle / "rights.json").write_bytes(controller._canonical(owner_waiver()))
    with pytest.raises(controller.RawRunError, match="input identity mismatch"):
        controller._execute_fixture_run(frozen, bundle)
    assert not (bundle / (controller.CANDIDATE_ID + ".spent.json")).exists()


@pytest.mark.parametrize("stage", ["reservation", "outcomes"])
def test_failed_waiver_run_retains_waiver_provenance_and_spent_identity(bundle, monkeypatch, stage):
    (bundle / "rights.json").write_bytes(controller._canonical(owner_waiver()))
    frozen = spec(bundle, outcomes_sha256="b" * 64)
    if stage == "reservation":
        original = controller._write
        writes = []
        def fail_once(fd, payload):
            writes.append(True)
            if len(writes) == 1:
                raise OSError("PRIVATE")
            return original(fd, payload)
        monkeypatch.setattr(controller, "_write", fail_once)
    result = controller._execute_fixture_run(frozen, bundle)
    assert result.status == "FAILED" and result.source_admission == "explicit-owner-waiver"
    terminal = json.loads(result.terminal_path.read_bytes())
    assert terminal["source_admission"]["owner_decision"] == "TPR-OWN-36"
    assert terminal["source_admission"]["contractual_rights_verified"] is False
    assert terminal["development_look_spent"] == 0 and terminal["fixture_runs"] == 1
    with pytest.raises(controller.RawRunError, match="already spent"):
        controller._execute_fixture_run(spec(bundle), bundle)


def test_existing_evidence_path_remains_distinct_and_does_not_claim_legal_verification(bundle):
    result = controller._execute_fixture_run(spec(bundle), bundle)
    assert result.source_admission == "source-evidence-manifest"
    assert result.owner_decision is None and result.contractual_rights_verified is False
    assert json.loads(result.terminal_path.read_bytes())["source_admission"]["basis"] == "source-evidence-manifest"


def test_preflight_describes_waiver_option_without_reading_or_accepting_it(bundle, monkeypatch):
    (bundle / "rights.json").write_bytes(controller._canonical(owner_waiver()))
    monkeypatch.setattr(controller, "_read_file", lambda *_: pytest.fail("preflight read a manifest"))
    result = controller.preflight(bundle, mode="offline-fixture")
    assert result["source_admission"] == "unverified"
    assert result["contractual_rights_verified"] is False
    assert result["accepted_admission_schemas"] == ["tpr-raw-rights-v1", "tpr-raw-owner-waiver-v1"]
    assert result["ready"] is False and result["development_looks"] == 0


@pytest.mark.parametrize("failure", [OSError("PRIVATE filesystem message"), KeyboardInterrupt("PRIVATE interruption")])
def test_incomplete_reservation_burns_candidate_and_writes_terminal_before_any_outcome_access(bundle, monkeypatch, failure):
    frozen = spec(bundle)
    real_write, real_read = controller._write, controller._read_file
    attempts = []
    def write(fd, payload):
        if not attempts:
            attempts.append("reservation")
            raise failure
        return real_write(fd, payload)
    def read(fd, name, *args):
        assert name != "outcomes.json"
        return real_read(fd, name, *args)
    monkeypatch.setattr(controller, "_write", write)
    monkeypatch.setattr(controller, "_read_file", read)
    if isinstance(failure, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt, match="look remains spent"):
            controller._execute_fixture_run(frozen, bundle)
    else:
        assert controller._execute_fixture_run(frozen, bundle).status == "FAILED"
    terminal = (bundle / (controller.CANDIDATE_ID + ".terminal.json")).read_bytes()
    assert json.loads(terminal)["failure"] == "reservation_incomplete"
    assert b"PRIVATE" not in terminal
    with pytest.raises(controller.RawRunError, match="already spent"):
        controller._execute_fixture_run(frozen, bundle)


def test_missing_bundle_preflight_never_creates_directory_or_permission(tmp_path):
    root = tmp_path / "absent"
    result = controller.preflight(root, mode="offline-fixture")
    assert result["reason"] == "source_admission_missing"
    assert result["ready"] is False and result["outcomes_read"] is False
    assert not root.exists()


def test_oversize_input_is_refused_before_reading_any_of_its_bytes(bundle, monkeypatch):
    frozen = spec(bundle)
    path = bundle / "rights.json"
    with path.open("ab") as stream:
        stream.truncate(controller.MAX_RIGHTS_BYTES + 1)
    monkeypatch.setattr(controller.os, "read", lambda *_: pytest.fail("oversize read"))
    with pytest.raises(controller.RawRunError, match="custody or size"):
        controller._execute_fixture_run(frozen, bundle)


def test_exact_source_file_hashes_are_checked_not_caller_flags(bundle, monkeypatch):
    code_root = controller.LANE_ROOT / "research" / "target_price_revisions_development"
    hashes = {name: hashlib.sha256((code_root / name).read_bytes()).hexdigest() for name in controller.CODE_FILES}
    _REAL_VERIFY_CODE(hashes)
    hashes["raw_candidate.py"] = "0" * 64
    monkeypatch.setattr(controller, "_verify_code", _REAL_VERIFY_CODE)
    frozen = spec(bundle, code_hashes=hashes)
    monkeypatch.setattr(controller, "_read_file", lambda *_: pytest.fail("input read after wrong code hash"))
    with pytest.raises(controller.RawRunError, match="code identity mismatch"):
        controller._execute_fixture_run(frozen, bundle)
    assert not (bundle / (controller.CANDIDATE_ID + ".spent.json")).exists()


@pytest.mark.parametrize("waiver", [False, True])
def test_private_controller_connects_actual_candidate_on_synthetic_inputs(bundle, monkeypatch, waiver):
    from tests.target_price_revisions_development.test_raw_candidate import inputs
    supplied_structure, supplied_outcomes = inputs()
    supplied_structure["capture_utc"] = NOW.isoformat()
    if waiver:
        (bundle / "rights.json").write_bytes(controller._canonical(owner_waiver()))
    for name, body in (("structure.json", supplied_structure), ("outcomes.json", supplied_outcomes)):
        (bundle / name).write_bytes(controller._canonical(body))
    code_root = controller.LANE_ROOT / "research" / "target_price_revisions_development"
    hashes = {name: hashlib.sha256((code_root / name).read_bytes()).hexdigest() for name in controller.CODE_FILES}
    monkeypatch.setattr(controller, "_verify_code", _REAL_VERIFY_CODE)
    monkeypatch.setattr(controller, "_load_candidate", _REAL_LOAD_CANDIDATE)
    monkeypatch.setattr(controller, "_prepare_structure", _REAL_PREPARE_STRUCTURE)
    result = controller._execute_fixture_run(spec(bundle, code_hashes=hashes), bundle)
    assert result.status == "COMPLETED"
    report = json.loads(result.report_path.read_bytes())
    assert report["candidate_id"] == controller.CANDIDATE_ID
    assert report["backtest"]["complete"] is True
    assert report["backtest"]["orders"] and report["backtest"]["fills"]
    assert report["policy"]["view"] == "censored"
    assert report["canonical_admission"] is False and report["quantconnect_attempts"] == 0


@pytest.mark.parametrize("mutation", [
    lambda body: body.update(action_inventory_complete=False),
    lambda body: body["calendar"].pop(),
    lambda body: body["actions"].append({"ticker": "ZZTEST0", "date": "2025-01-10", "action": "split"}),
    lambda body: body["ratings"][0].update(price_target="100"),
    lambda body: body["ratings"][0].update(last_updated="not-a-clock"),
])
def test_known_source_rejection_or_zero_target_refuses_before_look_or_any_outcome_access(bundle, monkeypatch, mutation):
    from tests.target_price_revisions_development.test_raw_candidate import inputs
    supplied, _ = inputs()
    supplied["capture_utc"] = NOW.isoformat()
    mutation(supplied)
    (bundle / "structure.json").write_bytes(controller._canonical(supplied))
    frozen = spec(bundle)
    monkeypatch.setattr(controller, "_prepare_structure", _REAL_PREPARE_STRUCTURE)
    real_read = controller._read_file
    def read(fd, name, *args):
        if name == "outcomes.json":
            pytest.fail("outcomes touched for structurally rejected candidate")
        return real_read(fd, name, *args)
    monkeypatch.setattr(controller, "_read_file", read)
    with pytest.raises(controller.RawRunError, match="candidate source|positive proxy"):
        controller._execute_fixture_run(frozen, bundle)
    assert not (bundle / (controller.CANDIDATE_ID + ".spent.json")).exists()


def test_public_executor_rejects_offline_mode_before_any_file_open_or_code_execution(bundle, monkeypatch):
    frozen = spec(bundle)
    monkeypatch.setattr(controller, "_open_root", lambda *_: pytest.fail("public offline root opened"))
    monkeypatch.setattr(controller, "_load_candidate", lambda: pytest.fail("public offline candidate loaded"))
    with pytest.raises(controller.RawRunError, match="production-only"):
        controller.execute_run(frozen, bundle)


def test_private_fixture_seam_cannot_select_production_identity(bundle, monkeypatch):
    frozen = spec(bundle, mode="production")
    monkeypatch.setattr(controller, "_open_root", lambda *_: pytest.fail("private production root opened"))
    with pytest.raises(controller.RawRunError, match="offline-fixture identity"):
        controller._execute_fixture_run(frozen, bundle)


@pytest.mark.parametrize("arguments", [[], ["--preflight"]])
def test_cli_default_and_explicit_preflight_never_open_spec_or_claim(monkeypatch, capsys, arguments):
    observed = {"ready": False, "reason": "rights_missing", "outcomes_read": False}
    monkeypatch.setattr(controller, "preflight", lambda: observed)
    monkeypatch.setattr(controller, "_read_file", lambda *_: pytest.fail("preflight opened spec or input"))
    monkeypatch.setattr(controller, "execute_run", lambda *_: pytest.fail("preflight executed run"))
    assert controller.main(arguments) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == observed and captured.err == ""


@pytest.mark.parametrize("arguments", [
    ["--run"], ["--spec-sha256", "a" * 64],
    ["--run", "--preflight", "--spec-sha256", "a" * 64],
    ["--run", "--mode", "PRIVATE", "--spec-sha256", "a" * 64],
    ["--root", "PRIVATE"], ["--path", "PRIVATE"], ["--unknown", "PRIVATE"],
    ["--run", "--spec-sha256", "PRIVATE"],
])
def test_cli_has_no_offline_mode_or_arbitrary_path_and_never_echoes_arguments(monkeypatch, capsys, arguments):
    monkeypatch.setattr(controller, "_verify_lane", lambda: pytest.fail("bad arguments reached lane check"))
    monkeypatch.setattr(controller, "preflight", lambda: pytest.fail("bad arguments reached preflight"))
    assert controller.main(arguments) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "REFUSED"
    assert "PRIVATE" not in captured.out + captured.err and captured.err == ""


def test_cli_run_opens_only_hash_bound_fixed_spec_then_public_production_executor(monkeypatch, capsys):
    trace, expected = [], "a" * 64
    monkeypatch.setattr(controller, "_verify_lane", lambda: trace.append("lane"))
    def open_root(root, mode):
        assert root == controller.PRODUCTION_ROOT and mode == "production"
        trace.append("root")
        return 918273
    def read(fd, name, maximum, identity):
        assert (fd, name, maximum, identity) == (918273, "run-spec.json", 65536, expected)
        trace.append("spec")
        return b"SYNTHETIC-SPEC"
    def execute(payload, root):
        assert payload == b"SYNTHETIC-SPEC" and root == controller.PRODUCTION_ROOT
        assert trace == ["lane", "root", "spec", "close"]
        trace.append("execute")
        return controller.RawRunResult("COMPLETED", "b" * 64, Path("PRIVATE_REPORT"), Path("PRIVATE_TERMINAL"))
    monkeypatch.setattr(controller, "_open_root", open_root)
    monkeypatch.setattr(controller, "_read_file", read)
    monkeypatch.setattr(controller.os, "close", lambda fd: trace.append("close") if fd == 918273 else pytest.fail("wrong fd"))
    monkeypatch.setattr(controller, "execute_run", execute)
    assert controller.main(["--run", "--spec-sha256", expected]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "COMPLETED", "report_sha256": "b" * 64}
    assert "PRIVATE" not in captured.out + captured.err


@pytest.mark.parametrize("failure, expected_status, expected_code", [
    (controller.RawRunError("PRIVATE source value"), "REFUSED", 2),
    (RuntimeError("PRIVATE source value"), "FAILED", 1),
    (KeyboardInterrupt("PRIVATE source value"), "INTERRUPTED", 130),
])
def test_cli_refusals_and_failures_are_closed_safe_json(monkeypatch, capsys, failure, expected_status, expected_code):
    def fail():
        raise failure
    monkeypatch.setattr(controller, "preflight", fail)
    assert controller.main([]) == expected_code
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == expected_status
    assert "PRIVATE" not in captured.out + captured.err and captured.err == ""
