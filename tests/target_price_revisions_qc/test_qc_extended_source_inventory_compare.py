"""Only public/synthetic receipts; actual retained captures/effects are denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import http.client
import os
from pathlib import Path
import stat
import subprocess

import pytest

from research.target_price_revisions_qc import extended_source_inventory_compare as c

e = c.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in c.SOURCE_PATHS}
NOW = datetime(2026, 10, 22, 2, tzinfo=timezone.utc)
PRIVATE_TEXT = "SYNTHETIC_PRIVATE_CONTENT_MUST_NOT_APPEAR"


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kwargs): raise AssertionError("actual private/provider/credential/subprocess forbidden")
    monkeypatch.setattr(c.m.ops, "credential", deny)
    monkeypatch.setattr(c.m.ops, "read_private", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    original = c.files._directory
    def safe(path, *, private):
        if private and path.is_relative_to(c.LANE): deny()
        return original(path, private=private)
    monkeypatch.setattr(c.files, "_directory", safe)


def payload(index):
    operation = c.RECEIPTS[index]["operation_id"]
    inventory = {name: {"bytes": 64, "sha256": c._sha(name.encode())} for name in c.INVENTORY_KEYS}
    inventory["main.py"] = dict(c.MAIN)
    expected = {name: dict(inventory[name]) for name in c.m.EXPECTED_FILES}
    expected["main.py"] = {"bytes": 59931, "sha256": "e"*64}
    body = {name: False for name in c.TOP}
    body.update(schema="tpr-ext26-mia-source-receipt-v1", operation_id=operation, action="baseline-source",
        project_id=c.m.PROJECT, candidate_id=c.m.CANDIDATE, git_head="a"*40,
        source_hashes={name: c._sha(raw) for name, raw in SOURCES.items() if name in c.m.SOURCE_PATHS},
        owner_instruction_sha256="b"*64, plan_sha256="c"*64, baseline_reference=None,
        status="BASELINE_MISMATCH", scope_spent=True, read_attempts=2, received_bytes=4000,
        baseline_read_bytes=0, failed_read_body_bytes_unknown=False, inventory=inventory,
        stable_source_inventory=True, baseline_expected_files_equal=False, expected_files=expected,
        missing_expected_files=[], different_expected_files=["main.py"], changes=None, complete_private_diff=None,
        request_bound_to_fixed_project=True, new_codex_attempts=0, codex_attempts_consumed=3, new_looks=0,
        licensed_input_reads=0, provider_reads=0, ended_utc=NOW.isoformat())
    body["requests"] = [{"request_index": number, "status": "succeeded", "response_bytes": 2000,
        "http_status": 200, "returned_project_present_and_matching": False,
        "projection": {"name": operation+f".read{number}.projection.json", "bytes": 2500, "sha256": "d"*64}}
        for number in (1, 2)]
    body["source_archives"] = [{"name": operation+f".read{number}.sources.json", "bytes": 268675, "sha256": "f"*64}
        for number in (1, 2)]
    body["unexpected_files"] = [{"name_sha256": digest, "classification": "unrecognized_source",
        **inventory["unrecognized-name-sha256-"+digest]} for digest in sorted(c.OTHER_HASHES)]
    return body


def fixture(tmp_path, mutate=None):
    root = (tmp_path / "synthetic-receipts").resolve(); root.mkdir(mode=0o700)
    bodies = [payload(index) for index in (0, 1)]
    if mutate: mutate(bodies)
    raws = [e.canonical(body) for body in bodies]
    assert all(len(raw) <= c.MAX_EACH for raw in raws)
    directory = c.files._directory(root, private=True)
    try:
        for ref, raw in zip(c.RECEIPTS, raws):
            c.m._publish(directory, ref["operation_id"]+".result.json", raw)
    finally: os.close(directory)
    plan = c._plan(git_head="a"*40, source_hashes={name: c._sha(raw) for name, raw in SOURCES.items()},
        owner_instruction_sha256="b"*64, created_utc=(NOW-timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=599)).isoformat(), mode="offline-fixture",
        fixture_descriptors=[{"bytes": len(raw), "sha256": c._sha(raw)} for raw in raws])
    return plan, dict(SOURCES), root


def execute(values, **kwargs):
    plan, sources, root = values
    raw = c.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: NOW), **kwargs)
    assert len(raw) <= c.MAX_RESULT
    return e.parse_json(raw)


def test_pure_closed_inventory_equality_is_not_source_or_backtest_acceptance():
    result = c.compare_receipts(*(e.canonical(payload(index)) for index in (0, 1)))
    assert result["files_each"] == 16 and result["all_16_equal"] is True
    assert result["registered_main_identity_verified"] is True and result["registered_main"] == c.MAIN
    assert result["before_inventory_sha256"] == result["after_inventory_sha256"]
    assert result["saved_inventory_metadata_only"] is True
    for name in ("source_archives_reopened", "historical_compiled_source_proven", "native_accounting_verified",
            "economics_accepted", "off_baseline_valid", "on_launch_authorized", "canonical_admission"):
        assert result[name] is False
    assert result["accepted_metrics"] is None


def test_valid_inventory_drift_is_reported_without_acceptance():
    before, after = payload(0), payload(1)
    after["inventory"]["main.py"] = {"bytes": c.MAIN["bytes"]+1, "sha256": "1"*64}
    result = c.compare_receipts(e.canonical(before), e.canonical(after))
    assert result["all_16_equal"] is False and result["changed_inventory_entries"] == 1
    assert result["registered_main_identity_verified"] is False and result["off_baseline_valid"] is False


@pytest.mark.parametrize("location", ["root", "inventory", "identity", "source_hashes", "request", "descriptor", "unexpected"])
@pytest.mark.parametrize("fault", ["extra", "missing"])
def test_valid_hashes_do_not_admit_nonmetadata_or_open_schemas(location, fault):
    bodies = [payload(0), payload(1)]
    target = {"root": bodies[0], "inventory": bodies[0]["inventory"], "identity": bodies[0]["inventory"]["main.py"],
        "source_hashes": bodies[0]["source_hashes"], "request": bodies[0]["requests"][0],
        "descriptor": bodies[0]["source_archives"][0], "unexpected": bodies[0]["unexpected_files"][0]}[location]
    if fault == "extra": target["source_content"] = PRIVATE_TEXT
    else: target.pop(next(iter(target)))
    with pytest.raises(ValueError): c.compare_receipts(*(e.canonical(body) for body in bodies))


@pytest.mark.parametrize("field,value", [
    ("operation_id", "foreign"), ("project_id", True), ("project_id", 1), ("candidate_id", "foreign"),
    ("status", "FAILED_OR_UNCERTAIN"), ("status", []), ("stable_source_inventory", False), ("scope_spent", False),
    ("read_attempts", 1), ("read_attempts", True), ("new_codex_attempts", 1), ("new_looks", 1),
    ("economics_accepted", True), ("performance_accepted", True), ("canonical_admission", True),
    ("licensed_input_reads", 1), ("provider_reads", 1), ("object_export", True), ("trading", True),
    ("baseline_read_bytes", 1), ("received_bytes", 3999), ("different_expected_files", []),
    ("baseline_expected_files_equal", True), ("missing_expected_files", ["main.py"]),
])
def test_each_receipt_identity_success_scope_and_no_authority_fact_is_checked(field, value):
    bodies = [payload(0), payload(1)]; bodies[0][field] = value
    with pytest.raises(ValueError): c.compare_receipts(*(e.canonical(body) for body in bodies))


@pytest.mark.parametrize("fault", ["duplicate_json", "nonfinite", "oversize", "wrong_type", "unknown_file", "wrong_hash", "negative_bytes", "bool_bytes", "unexpected_repeat"])
def test_resource_numeric_and_filename_faults_refuse(fault):
    before, after = payload(0), payload(1)
    raw = e.canonical(before)
    if fault == "duplicate_json": raw = raw.rstrip()[:-1] + b',"project_id":37650980}'
    elif fault == "nonfinite": raw = raw.replace(b'"read_attempts":2', b'"read_attempts":NaN')
    elif fault == "oversize": raw = b" "*(c.MAX_EACH+1)
    elif fault == "wrong_type": raw = bytearray(raw)
    elif fault == "unknown_file":
        before["inventory"][PRIVATE_TEXT] = before["inventory"].pop("main.py"); raw = e.canonical(before)
    elif fault == "wrong_hash": before["inventory"]["main.py"]["sha256"] = "not-a-hash"; raw = e.canonical(before)
    elif fault == "negative_bytes": before["inventory"]["main.py"]["bytes"] = -1; raw = e.canonical(before)
    elif fault == "bool_bytes": before["inventory"]["main.py"]["bytes"] = True; raw = e.canonical(before)
    else: before["unexpected_files"][-1] = deepcopy(before["unexpected_files"][0]); raw = e.canonical(before)
    with pytest.raises(ValueError): c.compare_receipts(raw, e.canonical(after))


def test_exact_two_fd_reads_after_claim_access_and_own_lock_with_no_archives(tmp_path, monkeypatch):
    values = fixture(tmp_path); plan, sources, root = values
    names = []; original = c.files._read
    def observed(directory, name, **kwargs):
        names.append(name)
        assert name in {ref["name"] for ref in plan["receipts"]}
        for suffix in (".claim.spent.json", ".access.json"):
            assert (root/(c.OPERATION+suffix)).is_file()
            assert stat.S_IMODE((root/(c.OPERATION+suffix)).stat().st_mode) == 0o600
        assert (root/"controller.lock").is_file()
        return original(directory, name, **kwargs)
    monkeypatch.setattr(c.files, "_read", observed)
    result = execute(values)
    assert result["status"] == "COMPLETED_METADATA_COMPARISON" and len(names) == 2
    assert result["private_read_attempts"].fraction() == 2
    assert result["private_read_bytes"].fraction() == sum(ref["bytes"] for ref in plan["receipts"])
    assert result["comparison"]["all_16_equal"] is True
    assert result["api_requests"].fraction() == result["credential_reads"].fraction() == result["source_archive_reads"].fraction() == 0
    assert not (root/"controller.lock").exists()
    with pytest.raises(FileExistsError): execute(values)


@pytest.mark.parametrize("fault", ["body", "symlink", "mode", "hardlink", "missing"])
def test_private_fd_hash_mode_path_and_presence_guards_stop_before_second_read(tmp_path, fault):
    values = fixture(tmp_path); plan, sources, root = values
    first = root/plan["receipts"][0]["name"]
    if fault == "body": first.write_bytes(first.read_bytes().replace(b'"project_id":37650980', b'"project_id":37650981'))
    elif fault == "symlink":
        target = root/"synthetic-target"; first.rename(target); first.symlink_to(target.name)
    elif fault == "mode": first.chmod(0o644)
    elif fault == "hardlink": os.link(first, root/"synthetic-hardlink")
    else: first.unlink()
    result = execute(values)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["comparison"] is None
    assert result["private_read_attempts"].fraction() == 1 and result["private_read_bytes"].fraction() == 0
    assert not (root/"controller.lock").exists()


def test_schema_refusal_after_first_valid_hash_read_does_not_read_second(tmp_path):
    def malformed(bodies): bodies[0]["source_content"] = PRIVATE_TEXT
    result = execute(fixture(tmp_path, malformed))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["comparison"] is None
    assert result["private_read_attempts"].fraction() == 1 and result["private_read_bytes"].fraction() > 0
    assert PRIVATE_TEXT not in e.canonical(result).decode()


def test_busy_controller_is_retained_with_zero_reads(tmp_path):
    values = fixture(tmp_path); root = values[2]
    directory = c.files._directory(root, private=True)
    try: c.m._publish(directory, "controller.lock", b"SYNTHETIC OTHER CONTROLLER")
    finally: os.close(directory)
    result = execute(values)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["private_read_attempts"].fraction() == 0
    assert (root/"controller.lock").read_bytes() == b"SYNTHETIC OTHER CONTROLLER"


def test_cancellation_ends_scope_without_second_read_and_retains_result(tmp_path, monkeypatch):
    values = fixture(tmp_path)
    def stop(*_args, **_kwargs): raise KeyboardInterrupt()
    monkeypatch.setattr(c.files, "_read", stop)
    result = execute(values)
    assert result["status"] == "CANCELLED" and result["private_read_attempts"].fraction() == 1
    assert result["comparison"] is None and not (values[2]/"controller.lock").exists()


def test_expiry_after_first_read_stops_second_read(tmp_path, monkeypatch):
    values = fixture(tmp_path); calls = []; original = c.files._read
    def read(*args, **kwargs):
        calls.append(None); return original(*args, **kwargs)
    monkeypatch.setattr(c.files, "_read", read)
    result = execute(values, clock=lambda: NOW+timedelta(hours=1) if calls else NOW)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["private_read_attempts"].fraction() == 1


def test_oversized_result_becomes_body_free_failure_receipt(tmp_path, monkeypatch):
    values = fixture(tmp_path)
    monkeypatch.setattr(c, "compare_receipts", lambda *_args: {"body": PRIVATE_TEXT*200})
    result = execute(values)
    assert result["status"] == "RESULT_BOUND_REFUSED" and result["comparison"] is None
    assert PRIVATE_TEXT not in e.canonical(result).decode()


@pytest.mark.parametrize("field,value", [("max_reads", 3), ("source_archive_reads", 1), ("api_requests", 1),
    ("on_launch_authorized", True), ("mode", "production")])
def test_plan_shape_or_effect_widening_refuses_before_private_scope(tmp_path, field, value):
    values = fixture(tmp_path); values[0][field] = value
    with pytest.raises(ValueError): execute(values)
    assert not (values[2]/(c.OPERATION+".claim.spent.json")).exists()


def test_production_fixed_references_and_short_scope_cannot_use_fixture_descriptors():
    arguments = dict(git_head="a"*40, source_hashes={name: c._sha(raw) for name, raw in SOURCES.items()},
        owner_instruction_sha256="b"*64, created_utc=NOW.isoformat(), expires_utc=(NOW+timedelta(seconds=600)).isoformat())
    plan = c._plan(**arguments)
    assert plan["receipts"] == [dict(ref, name=ref["operation_id"]+".result.json") for ref in c.RECEIPTS]
    assert plan["max_total_read_bytes"] == 16106 and plan["max_result_bytes"] == 4096
    with pytest.raises(ValueError): c._plan(**arguments, fixture_descriptors=[{"bytes": 1, "sha256": "c"*64}]*2)
    arguments["expires_utc"] = (NOW+timedelta(seconds=601)).isoformat()
    with pytest.raises(ValueError): c._plan(**arguments)


def test_production_seam_rejects_injected_guard_clock_and_fixture_root_before_io(tmp_path):
    values = fixture(tmp_path)
    plan = c._plan(git_head="a"*40, source_hashes=values[0]["source_hashes"], owner_instruction_sha256="b"*64,
        created_utc=values[0]["created_utc"], expires_utc=values[0]["expires_utc"])
    with pytest.raises(ValueError): c._execute(plan, values[1], values[2], guard=lambda _: None, clock=lambda: NOW, monotonic=lambda: 0)
    with pytest.raises(ValueError): c.execute_fixture(plan, values[1], values[2], clock=lambda: NOW)


@pytest.mark.parametrize("seam", ["guard", "clock", "monotonic", "root"])
def test_each_production_identity_guard_is_reached_in_a_valid_synthetic_clock_window(tmp_path, monkeypatch, seam):
    values = fixture(tmp_path)
    plan = c._plan(git_head="a"*40, source_hashes=values[0]["source_hashes"], owner_instruction_sha256="b"*64,
        created_utc=values[0]["created_utc"], expires_utc=values[0]["expires_utc"])
    def trusted_guard(_head): return None
    def trusted_clock(): return NOW
    def trusted_monotonic(): return 0.0
    reached = []
    def stop_at_directory(*_args, **_kwargs):
        reached.append(None)
        raise AssertionError("synthetic production boundary reached; no directory opened")
    monkeypatch.setattr(c, "_guard", trusted_guard)
    monkeypatch.setattr(c, "_now", trusted_clock)
    monkeypatch.setattr(c.time, "monotonic", trusted_monotonic)
    monkeypatch.setattr(c.files, "_directory", stop_at_directory)
    arguments = dict(guard=trusted_guard, clock=trusted_clock, monotonic=trusted_monotonic)
    with pytest.raises(AssertionError, match="synthetic production boundary reached"):
        c._execute(plan, values[1], c.PRIVATE_ROOT, **arguments)
    assert len(reached) == 1  # A real clock/window refusal cannot mask a removed seam guard.
    root = c.PRIVATE_ROOT
    if seam == "guard": arguments["guard"] = lambda _head: None
    elif seam == "clock": arguments["clock"] = lambda: NOW
    elif seam == "monotonic": arguments["monotonic"] = lambda: 0.0
    else: root = values[2]
    with pytest.raises(ValueError): c._execute(plan, values[1], root, **arguments)
    assert len(reached) == 1


@pytest.mark.parametrize("fault", ["source", "expired", "deadline"])
def test_source_change_expired_scope_or_elapsed_budget_refuses_before_claim(tmp_path, fault):
    values = fixture(tmp_path)
    arguments = {}
    if fault == "source": values[1][c.MODULE] += b" "
    elif fault == "expired": arguments["clock"] = lambda: NOW+timedelta(hours=1)
    else:
        times = iter((0.0, 120.0))
        arguments["monotonic"] = lambda: next(times)
    with pytest.raises(ValueError): execute(values, **arguments)
    assert not (values[2]/(c.OPERATION+".claim.spent.json")).exists()
