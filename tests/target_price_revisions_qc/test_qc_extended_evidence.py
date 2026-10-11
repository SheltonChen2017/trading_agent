"""Pure synthetic evidence/attempt proofs; no private data or cloud access."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_evidence as e

ON, OFF = tuple(e.CANDIDATES)


def raw(body):
    return e.canonical(body)


def envelope(request, response):
    endpoint, stage = (("backtests/create", "backtest_launch") if "backtestName" in request else
        ("compile/read", "compile_status") if "compileId" in request else
        ("backtests/read", "backtest_status") if "backtestId" in request else ("files/read", "source_readback"))
    return raw({"schema": "tpr-ext26-request-response-v1", "endpoint": endpoint, "stage": stage,
                "request": request, "response": response})


def fixture(candidate=ON, attempt=1, *, compile_state="BuildSuccess"):
    config = {"schema": "tpr-ext26-config-v1", "study_id": e.STUDY_ID,
        "candidate_id": candidate, "arm": e.CANDIDATES[candidate], "freeze_sha256": e.FREEZE_SHA256,
        "input_hashes": {"calendar.json": "b" * 64, "shard-index.json": "c" * 64}}
    config_raw = raw(config)
    files = {"main.py": "# Synthetic future entrypoint only\n",
             "extended_config.py": "CONFIG_JSON = " + repr(config_raw.decode()) + "\n",
             "extended_signal.py": "# Synthetic new shard consumer only\n"}
    manifest = {"schema": "tpr-ext26-execution-manifest-v1", "study_id": e.STUDY_ID,
        "freeze_sha256": e.FREEZE_SHA256, "candidate_id": candidate, "arm": e.CANDIDATES[candidate],
        "project_id": 123, "baseline_git_head": "d" * 40, "config_sha256": e.digest(config_raw),
        "source_hashes": {name: e.digest(text.encode()) for name, text in files.items()},
        "input_hashes": config["input_hashes"], "max_attempts": 3}
    manifest_raw = raw(manifest)
    manifest_hash = e.digest(manifest_raw)
    reservation = {"schema": "tpr-ext26-attempt-reservation-v1", "study_id": e.STUDY_ID,
        "candidate_id": candidate, "attempt": attempt, "manifest_sha256": manifest_hash,
        "project_id": 123, "config_sha256": manifest["config_sha256"], "freeze_sha256": e.FREEZE_SHA256,
        "source_hashes": manifest["source_hashes"], "input_hashes": manifest["input_hashes"], "state": "reserved"}
    reservation_raw = raw(reservation)
    compile_raw = envelope({"projectId": 123, "compileId": "compile-synthetic"},
        {"success": True, "projectId": 123, "compileId": "compile-synthetic", "state": compile_state})
    readback = envelope({"projectId": 123}, {"success": True,
        "files": [{"name": name, "content": text} for name, text in files.items()]})
    receipt = {"schema": "tpr-ext26-verified-compile-v1", "manifest_sha256": manifest_hash,
        "reservation_sha256": e.digest(reservation_raw), "compile_response_sha256": e.digest(compile_raw),
        "source_readback_sha256": e.digest(readback), "project_id": 123, "compile_id": "compile-synthetic"}
    launch = envelope({"projectId": 123, "compileId": "compile-synthetic",
        "backtestName": candidate + "-attempt-" + str(attempt)},
        {"success": True, "backtest": {"backtestId": "backtest-synthetic", "projectId": 123,
                                       "compileId": "compile-synthetic"}})
    return {"manifest_raw": manifest_raw, "expected_manifest_sha256": manifest_hash,
        "config_raw": config_raw, "reservation_raw": reservation_raw, "compile_response_raw": compile_raw,
        "compile_receipt_raw": raw(receipt), "readback_raw": readback, "launch_raw": launch}


def binding(args):
    values = dict(args)
    manifest = values.pop("manifest_raw")
    return e.validate_execution_binding(manifest, **values)


def change(args, field, transform):
    body = e.parse_json(args[field])
    transform(body)
    args[field] = raw(body)
    return args


def closed_attempt(candidate=ON, attempt=1, *, failure=False):
    args = fixture(candidate, attempt, compile_state="BuildError" if failure else "BuildSuccess")
    terminal = envelope({"projectId": 123, "backtestId": "backtest-synthetic"},
        {"success": True, "backtest": {"projectId": 123, "backtestId": "backtest-synthetic",
            "completed": True, "progress": 1, "status": "Completed.", "error": None}})
    closure = {"schema": "tpr-ext26-closed-attempt-v1", "candidate_id": candidate,
        "attempt": attempt, "manifest_sha256": args["expected_manifest_sha256"],
        "reservation_sha256": e.digest(args["reservation_raw"]),
        "outcome": "compile_failure" if failure else "backtest_terminal",
        "compile_response_sha256": e.digest(args["compile_response_raw"]),
        "launch_sha256": None if failure else e.digest(args["launch_raw"]),
        "backtest_response_sha256": None if failure else e.digest(terminal)}
    return {"manifest": args["manifest_raw"], "reservation": args["reservation_raw"],
        "closure": raw(closure), "compile_response": args["compile_response_raw"],
        "launch": None if failure else args["launch_raw"], "backtest_response": None if failure else terminal}


def next_for(rows, candidate=ON, *, count=None, expected=None):
    return e.next_attempt(rows, candidate_id=candidate, consumed_count=len(rows) if count is None else count,
        expected_ledger_sha256=e.ledger_identity(rows) if expected is None else expected)


@pytest.mark.parametrize("token", ["0.123456789012345678901234567890", "1e+2", "-0", "-0.000", "1.00", "100000000000000000000000000000"])
def test_original_numeric_lexemes_and_exact_values_survive(token):
    parsed = e.parse_json(('{"number":' + token + '}').encode())
    assert type(parsed["number"]) is e.JsonNumber
    assert parsed["number"].lexeme == token
    assert parsed["number"].fraction() == Fraction(Decimal(token))
    assert e.canonical(parsed) == ('{"number":' + token + '}\n').encode()


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "01", "+1", "1e129", "1e-129"])
def test_invalid_nonfinite_or_unbounded_wire_numbers_refuse(token):
    with pytest.raises(e.EvidenceError):
        e.parse_json(('{"value":' + token + '}').encode())


@pytest.mark.parametrize("value", [1.0, float("nan"), float("inf"), Decimal("1.1"), {1: "wrong key"}, (1, 2)])
def test_authoritative_canonicalization_never_accepts_float_or_implicit_types(value):
    with pytest.raises(e.EvidenceError):
        e.canonical(value)


@pytest.mark.parametrize("wire", [b'{"same":1,"same":2}', b'{"x":true,}', b'\xff', b'', b'[' * 40 + b'0' + b']' * 40])
def test_bad_or_excessive_json_structure_refuses(wire):
    with pytest.raises(e.EvidenceError):
        e.parse_json(wire)


def test_structural_pii_redaction_does_not_corrupt_unrelated_numeric_identity():
    wire = b'{"userId":123456,"metadata":{"email":"synthetic@example.invalid"},"projects":[{"collaborators":[{"uid":123456,"name":"Synthetic owner","owner":true}]}],"orders":[{"id":9912345677,"uid":"9912345677","name":"order name","quantity":1.2300}]}'
    original = e.parse_json(wire)
    before = deepcopy(original)
    result = e.project_wire(wire)
    projected = result["projection"]
    assert original == before
    assert projected["userId"] == projected["metadata"]["email"] == "[redacted]"
    collaborator = projected["projects"][0]["collaborators"][0]
    assert collaborator == {"uid": "[redacted]", "name": "[redacted]", "owner": True}
    assert projected["orders"] == original["orders"]
    assert result["original_wire_sha256"] == e.digest(wire)
    assert result["projection_sha256"] == e.digest(e.canonical(projected))
    assert result["original_wire_sha256"] != result["projection_sha256"]
    assert projected["orders"][0]["quantity"].lexeme == "1.2300"


@pytest.mark.parametrize("wire", [b'{"error":"TOKEN_SYNTHETIC"}', b'{"error":"TOKEN_\\u0053YNTHETIC"}', b'{"TOKEN_SYNTHETIC":0}'])
def test_credential_echo_refuses_before_hashing_or_projection(wire, monkeypatch):
    calls = []
    monkeypatch.setattr(e, "digest", lambda raw: calls.append(raw))
    with pytest.raises(e.EvidenceError, match="echo refused"):
        e.project_wire(wire, credential="TOKEN_SYNTHETIC")
    assert calls == []


@pytest.mark.parametrize("candidate", [ON, OFF])
def test_exact_concrete_execution_binding_is_positive_but_not_provider_or_strategy_attestation(candidate):
    args = fixture(candidate)
    original = deepcopy(args)
    result = binding(args)
    assert args == original
    assert result["binding_validated"] is True
    assert result["backtest_id"] == "backtest-synthetic"
    assert result["remote_authenticity_attested"] is result["canonical_admission"] is False
    assert result["source_hashes"] == e.parse_json(args["manifest_raw"])["source_hashes"]


@pytest.mark.parametrize("field,transform", [
    ("manifest_raw", lambda b: b.update(freeze_sha256="0" * 64)),
    ("manifest_raw", lambda b: b.update(candidate_id="TPR-CAP-TILT-ON-BASE-v1")),
    ("manifest_raw", lambda b: b.update(max_attempts=4)),
    ("reservation_raw", lambda b: b.update(attempt=True)),
    ("reservation_raw", lambda b: b.update(project_id=True)),
    ("reservation_raw", lambda b: b.update(source_hashes={"main.py": "a" * 64})),
    ("reservation_raw", lambda b: b.update(input_hashes={"foreign.json": "a" * 64})),
    ("compile_receipt_raw", lambda b: b.update(compile_response_sha256="0" * 64)),
    ("compile_receipt_raw", lambda b: b.update(source_readback_sha256="0" * 64)),
    ("compile_receipt_raw", lambda b: b.update(reservation_sha256="0" * 64)),
    ("compile_receipt_raw", lambda b: b.update(build_success=True)),
    ("compile_response_raw", lambda b: b["response"].update(state="BuildError")),
    ("compile_response_raw", lambda b: b["response"].update(compileId="foreign-compile")),
    ("compile_response_raw", lambda b: b["request"].update(projectId=True)),
    ("compile_response_raw", lambda b: b["response"].update(projectId=456)),
    ("compile_response_raw", lambda b: b["response"].update(success=1)),
    ("compile_response_raw", lambda b: b.update(endpoint="backtests/create")),
    ("compile_response_raw", lambda b: b.update(stage="backtest_launch")),
    ("compile_response_raw", lambda b: b["response"].update(state=[])),
    ("readback_raw", lambda b: b["response"]["files"][0].update(content="# changed\n")),
    ("readback_raw", lambda b: b["response"]["files"].append(dict(b["response"]["files"][0]))),
    ("readback_raw", lambda b: b["request"].update(projectId=456)),
    ("launch_raw", lambda b: b["request"].update(compileId="foreign-compile")),
    ("launch_raw", lambda b: b["request"].update(backtestName="foreign-study")),
    ("launch_raw", lambda b: b["response"]["backtest"].update(projectId=True)),
    ("launch_raw", lambda b: b["response"]["backtest"].update(compileId="foreign-compile")),
    ("launch_raw", lambda b: b["response"]["backtest"].update(backtestId=True)),
])
def test_material_mixed_or_boolean_authority_evidence_refuses(field, transform):
    args = fixture()
    assert binding(args)["binding_validated"]
    change(args, field, transform)
    with pytest.raises(e.EvidenceError):
        binding(args)


def test_substituted_well_shaped_source_inventory_does_not_pass_real_readback():
    args = fixture()
    changed = e.parse_json(args["manifest_raw"])
    changed["source_hashes"]["main.py"] = "a" * 64
    args["manifest_raw"] = raw(changed)
    args["expected_manifest_sha256"] = e.digest(args["manifest_raw"])
    change(args, "reservation_raw", lambda b: b.update(manifest_sha256=args["expected_manifest_sha256"], source_hashes=changed["source_hashes"]))
    change(args, "compile_receipt_raw", lambda b: b.update(manifest_sha256=args["expected_manifest_sha256"],
        reservation_sha256=e.digest(args["reservation_raw"])))
    with pytest.raises(e.EvidenceError, match="cloud content"):
        binding(args)


def test_concrete_failed_compile_never_passes_even_with_matching_receipt_hashes():
    args = fixture(compile_state="BuildError")
    with pytest.raises(e.EvidenceError, match="BuildSuccess"):
        binding(args)


def test_cloud_configuration_literal_must_match_independent_config_bytes():
    args = fixture()
    readback = e.parse_json(args["readback_raw"])
    readback["response"]["files"][1]["content"] = 'CONFIG_JSON = "{}"\n'
    manifest = e.parse_json(args["manifest_raw"])
    manifest["source_hashes"]["extended_config.py"] = e.digest(readback["response"]["files"][1]["content"].encode())
    args.update(manifest_raw=raw(manifest), readback_raw=raw(readback))
    args["expected_manifest_sha256"] = e.digest(args["manifest_raw"])
    change(args, "reservation_raw", lambda b: b.update(manifest_sha256=args["expected_manifest_sha256"], source_hashes=manifest["source_hashes"]))
    with pytest.raises(e.EvidenceError, match="cloud content"):
        binding(args)


def test_omitted_response_project_id_still_requires_typed_request_identity():
    args = fixture()
    for field in ("compile_response_raw", "launch_raw"):
        change(args, field, lambda b: b["response"].pop("projectId", None))
    change(args, "compile_receipt_raw", lambda b: b.update(compile_response_sha256=e.digest(args["compile_response_raw"])))
    assert binding(args)["project_id"] == 123
    change(args, "readback_raw", lambda b: b["request"].pop("projectId"))
    with pytest.raises(e.EvidenceError):
        binding(args)


@pytest.mark.parametrize("candidate", [ON, OFF])
def test_fresh_and_known_closed_attempts_advance_without_refunds(candidate):
    assert next_for([], candidate) == 1
    rows = [closed_attempt(candidate, 1, failure=True)]
    assert next_for(rows, candidate) == 2
    rows.append(closed_attempt(candidate, 2))
    assert next_for(rows, candidate) == 3
    rows.append(closed_attempt(candidate, 3))
    with pytest.raises(e.EvidenceError, match="three attempts consumed"):
        next_for(rows, candidate)


@pytest.mark.parametrize("key", ["closure", "compile_response", "launch", "backtest_response"])
def test_reserved_or_partially_known_predecessor_blocks_retry(key):
    row = closed_attempt()
    row[key] = None
    with pytest.raises(e.EvidenceError):
        next_for([row])


def test_buildsuccess_without_known_backtest_never_closes_compile_failure():
    row = closed_attempt(failure=True)
    compile_body = e.parse_json(row["compile_response"])
    compile_body["response"]["state"] = "BuildSuccess"
    row["compile_response"] = raw(compile_body)
    closure = e.parse_json(row["closure"])
    closure["compile_response_sha256"] = e.digest(row["compile_response"])
    row["closure"] = raw(closure)
    with pytest.raises(e.EvidenceError, match="compile failure without launch"):
        next_for([row])


def test_compile_failure_cannot_hide_contradictory_launch_evidence():
    row = closed_attempt(failure=True)
    row["launch"] = fixture()["launch_raw"]
    with pytest.raises(e.EvidenceError):
        next_for([row])


@pytest.mark.parametrize("changed", [{"completed": 1}, {"completed": False}, {"status": "In Progress..."},
    {"status": "Completed.."}, {"progress": True}, {"progress": "1"}, {"progress": 0},
    {"backtestId": "foreign-job"}, {"projectId": True}, {"projectId": 456}, {"compileId": "foreign-compile"}, {"status": []},
    {"error": ""}])
def test_unknown_or_misbound_terminal_cannot_allow_new_attempt(changed):
    row = closed_attempt()
    body = e.parse_json(row["backtest_response"])
    body["response"]["backtest"].update(changed)
    row["backtest_response"] = raw(body)
    closure = e.parse_json(row["closure"])
    closure["backtest_response_sha256"] = e.digest(row["backtest_response"])
    row["closure"] = raw(closure)
    with pytest.raises(e.EvidenceError):
        next_for([row])


def test_known_runtime_failure_closes_but_keeps_consumed_attempt():
    row = closed_attempt()
    body = e.parse_json(row["backtest_response"])
    body["response"]["backtest"].update(status="Runtime Error", error="Synthetic error", progress=e.JsonNumber("0.25"))
    row["backtest_response"] = raw(body)
    closure = e.parse_json(row["closure"])
    closure["backtest_response_sha256"] = e.digest(row["backtest_response"])
    row["closure"] = raw(closure)
    assert next_for([row]) == 2


@pytest.mark.parametrize("count", [True, 1, 3, 4, -1])
def test_missing_or_boolean_consumed_census_is_refused(count):
    with pytest.raises(e.EvidenceError):
        next_for([], count=count)


def test_retained_census_hash_prevents_rebinding_selected_ledger_rows():
    original = [closed_attempt()]
    retained = e.ledger_identity(original)
    changed = deepcopy(original)
    # Same valid semantics but different concrete closure bytes: only the
    # independently retained census identity can detect this substitution.
    changed[0]["closure"] += b" "
    with pytest.raises(e.EvidenceError, match="ledger identity"):
        next_for(changed, expected=retained)


def test_noncontiguous_or_other_candidate_history_does_not_reset_count():
    for rows in ([closed_attempt(attempt=2)], [closed_attempt(OFF)]):
        with pytest.raises(e.EvidenceError):
            next_for(rows)


def test_freeze_hash_and_import_boundary_are_prospective_not_runtime_completion():
    freeze = Path("research/target_price_revisions_qc/extended_study_freeze.json").read_bytes()
    assert e.digest(freeze) == e.FREEZE_SHA256
    source = Path(e.__file__).read_text()
    assert "http.client" not in source and "subprocess" not in source and "os.environ" not in source
    assert "cap_tilt_operations" not in source and "assistant" not in source
