"""Only synthetic source bodies; no account, credentials or real private reads."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import stat

import pytest

from research.target_price_revisions_qc import extended_mia_capture as c

e = c.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in c.SOURCE_PATHS}
PUBLIC_OFF = next(row["files"] for row in e.parse_json(SOURCES[c.BUNDLE])["candidates"]
    if row["candidate_id"] == c.CANDIDATE)


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("actual account/private/credential/network/subprocess forbidden")
    monkeypatch.setattr(c.ops, "credential", denied)
    monkeypatch.setattr(c.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(c.subprocess, "run", denied)
    directory = c.files._directory
    def safe_directory(path, *, private):
        if private and path.is_relative_to(c.LANE):
            denied()
        return directory(path, private=private)
    monkeypatch.setattr(c.files, "_directory", safe_directory)


def fixture(tmp_path, *, action="baseline-source", reference=None, suffix="SYNTHETIC-001", root=None):
    now = datetime.now(timezone.utc)
    if root is None:
        root = tmp_path / "synthetic-mia-source"
        root.mkdir(mode=0o700)
    prefix = "TPR-EXT26-MIA-SOURCE-BASELINE-" if action == "baseline-source" else "TPR-EXT26-MIA-SOURCE-POST-"
    plan = c._plan(action=action, operation_id=prefix + suffix,
        git_head="a" * 40, source_hashes={name: c._sha(raw) for name, raw in SOURCES.items()},
        owner_instruction_sha256="b" * 64, created_utc=(now - timedelta(seconds=1)).isoformat(),
        expires_utc=(now + timedelta(hours=3)).isoformat(), baseline_reference=reference, mode="offline-fixture")
    return plan, deepcopy(SOURCES), root, now


def cloud(source=None, *, mutate=None, status=200, token="SYNTHETIC-TOKEN"):
    calls = []
    source = deepcopy(source if source is not None else {**PUBLIC_OFF, "research.ipynb": '{"cells":[]}\n'})
    def transport(payload, seconds):
        calls.append((deepcopy(payload), seconds))
        response = {"success": True, "projectId": c.PROJECT,
            "files": [{"name": name, "content": text} for name, text in source.items()]}
        if mutate is not None:
            mutate(response, len(calls))
        return e.canonical(response), status, token
    return transport, calls


def execute(values, transport, **arguments):
    plan, sources, root, now = values
    raw = c._execute_fixture(plan, sources, root, clock=arguments.pop("clock", lambda: now),
        transport=transport, **arguments)
    return e.parse_json(raw), raw


def baseline(tmp_path):
    values = fixture(tmp_path)
    transport, calls = cloud()
    result, raw = execute(values, transport)
    assert result["status"] == "COMPLETED" and len(calls) == 2
    source_archive = result["source_archives"][-1]
    reference = {"operation_id": values[0]["operation_id"], "receipt_bytes": len(raw),
        "receipt_sha256": c._sha(raw), "sources_bytes": int(source_archive["bytes"].fraction()),
        "sources_sha256": source_archive["sha256"]}
    return values, result, reference


def test_fixed_scope_and_immutable_off_source_bytes():
    assert c.PROJECT == 37650980 and c.CANDIDATE == "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
    assert c.ENDPOINT == "files/read" and c.MAX_FILES == 16
    assert (c.MAX_FILE, c.MAX_RESPONSE, c.MAX_TOTAL, c.MAX_SECONDS, c.REQUEST_SECONDS) == (
        1048576, 4194304, 8388608, 120, 40)
    assert len(PUBLIC_OFF) == 10 and len(PUBLIC_OFF["main.py"].encode()) == 59931
    assert c._sha(SOURCES[c.BUNDLE]) == c.BUNDLE_SHA256
    assert c.EXPECTED_FILES == set(PUBLIC_OFF)


def test_baseline_is_stable_exact_and_retains_all_notebook_and_extra_source(tmp_path):
    values = fixture(tmp_path)
    source = {**PUBLIC_OFF, "research.ipynb": '{"cells":[]}', "diagnostic_note.py": "# SYNTHETIC-PRIVATE-CONTENT\n"}
    transport, calls = cloud(source)
    result, raw = execute(values, transport)
    assert result["status"] == "COMPLETED" and result["stable_source_inventory"] is True
    assert result["baseline_expected_files_equal"] is True
    assert result["unexpected_files"][0]["name_sha256"] == c._sha(b"diagnostic_note.py")
    assert len(result["inventory"]) == len(source) and len(calls) == 2
    assert calls == [({"projectId": c.PROJECT}, 40), ({"projectId": c.PROJECT}, 40)]
    for artifact in result["source_archives"]:
        path = values[2] / artifact["name"]
        assert e.parse_json(path.read_bytes())["files"] == source
        assert path.stat().st_mode & 0o777 == 0o600
        assert c._sha(path.read_bytes()) == artifact["sha256"]
    assert b"SYNTHETIC-PRIVATE-CONTENT" not in raw and b"CONFIG_JSON" not in raw and b"diagnostic_note.py" not in raw
    for key in ("economics_accepted", "performance_accepted", "compiled_job_binding_verified", "mia_message_or_job",
                "candidate_mutation", "automatic_retry", "object_export", "trading"):
        assert result[key] is False
    assert result["new_codex_attempts"].fraction() == result["new_looks"].fraction() == 0
    assert result["codex_attempts_consumed"].fraction() == 3
    assert not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError):
        execute(values, transport)
    assert len(calls) == 2


def test_post_mia_retains_all_changes_without_accepting_them(tmp_path):
    old, old_result, reference = baseline(tmp_path)
    values = fixture(tmp_path, action="post-mia-source", reference=reference, root=old[2])
    source = {**PUBLIC_OFF, "research.ipynb": '{"cells":[]}', "mia_observer.py": "# SYNTHETIC-MIA-CHANGE\n"}
    source["main.py"] += "# no newline"
    del source["cap_observer.py"]
    transport, calls = cloud(source)
    result, raw = execute(values, transport)
    assert result["status"] == "COMPLETED" and result["stable_source_inventory"] is True
    assert result["baseline_expected_files_equal"] is False
    assert result["missing_expected_files"] == ["cap_observer.py"]
    assert result["different_expected_files"] == ["main.py"]
    assert {row["name"]: row["kind"] for row in result["changes"] if "name" in row} == {
        "cap_observer.py": "removed", "main.py": "changed", "research.ipynb": "changed"}
    assert next(row for row in result["changes"] if "name_sha256" in row)["name_sha256"] == c._sha(b"mia_observer.py")
    private = e.parse_json((values[2] / result["complete_private_diff"]["name"]).read_bytes())
    changed_main = next(row for row in private["changes"] if row["name"] == "main.py")
    assert changed_main["before"] == PUBLIC_OFF["main.py"] and changed_main["after"] == source["main.py"]
    assert private["all_changed_file_bytes_retained"] is True and private["economics_accepted"] is False
    assert b"SYNTHETIC-MIA-CHANGE" not in raw and b"mia_observer.py" not in raw and len(calls) == 2
    assert result["baseline_read_bytes"].fraction() == reference["receipt_bytes"] + reference["sources_bytes"]


def test_source_change_or_expected_missing_is_archived_not_silently_admitted(tmp_path):
    values = fixture(tmp_path)
    source = {**PUBLIC_OFF, "main.py": "# entirely changed\n"}
    del source["extended_config.py"]
    transport, _ = cloud(source)
    result, _ = execute(values, transport)
    assert result["status"] == "BASELINE_MISMATCH" and result["stable_source_inventory"] is True
    assert result["baseline_expected_files_equal"] is False
    assert result["different_expected_files"] == ["main.py"]
    assert result["missing_expected_files"] == ["extended_config.py"] and len(result["source_archives"]) == 2


def test_source_drift_retains_both_full_snapshots_and_stops(tmp_path):
    def mutate(response, number):
        if number == 2:
            response["files"][0]["content"] += "# SYNTHETIC-DRIFT"
    transport, calls = cloud(mutate=mutate)
    result, _ = execute(fixture(tmp_path), transport)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 2
    assert len(result["source_archives"]) == 2 and result["stable_source_inventory"] is False


@pytest.mark.parametrize("fault", ["project", "row_project", "duplicate", "traversal", "newline_name", "wrong_type", "too_many", "too_large", "not_success"])
def test_closed_inventory_identifier_identity_and_size_refusals(tmp_path, fault):
    def mutate(response, number):
        if fault == "project": response["projectId"] = 1
        if fault == "row_project": response["files"][0]["projectId"] = 1
        if fault == "duplicate": response["files"].append(deepcopy(response["files"][0]))
        if fault == "traversal": response["files"][0]["name"] = "../source.py"
        if fault == "newline_name": response["files"][0]["name"] = "name\n.py"
        if fault == "wrong_type": response["files"][0]["content"] = None
        if fault == "too_many": response["files"] = [{"name": f"f{number}.py", "content": ""} for number in range(17)]
        if fault == "too_large": response["files"][0]["content"] = "x" * (c.MAX_FILE + 1)
        if fault == "not_success": response["success"] = False
    transport, calls = cloud(mutate=mutate)
    values = fixture(tmp_path)
    result, raw = execute(values, transport)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["inventory"] is None and result["requests"][0]["status"] == "failed_or_unknown"
    assert (values[2] / (values[0]["operation_id"] + ".read1.projection.json")).exists()
    assert result["automatic_retry"] is False and b"../source.py" not in raw


def test_absent_returned_project_is_request_bound_only(tmp_path):
    transport, _ = cloud(mutate=lambda response, _: response.pop("projectId"))
    result, _ = execute(fixture(tmp_path), transport)
    assert result["status"] == "COMPLETED" and result["request_bound_to_fixed_project"] is True
    assert all(row["returned_project_present_and_matching"] is False for row in result["requests"])
    assert result["provider_authenticity_attested"] is False


@pytest.mark.parametrize("status", [302, 401, 500])
def test_non_200_has_no_redirect_or_retry_even_with_plausible_source(tmp_path, status):
    transport, calls = cloud(status=status)
    result, _ = execute(fixture(tmp_path), transport)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["requests"][0]["http_status"].fraction() == status
    assert result["automatic_retry"] is False and not result["source_archives"]


@pytest.mark.parametrize("fault", ["wire_bytes", "empty", "credential_echo", "malformed"])
def test_response_budget_and_secret_refusals_before_archive(tmp_path, fault):
    values = fixture(tmp_path)
    calls = []
    def transport(payload, seconds):
        calls.append(payload)
        raw = (b"x" * (c.MAX_RESPONSE + 1) if fault == "wire_bytes" else b"" if fault == "empty"
            else b'{"success":true,"private":"SYNTHETIC-TOKEN"}' if fault == "credential_echo" else b"not-json")
        return raw, 200, "SYNTHETIC-TOKEN"
    result, _ = execute(values, transport)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert not list(values[2].glob("*.projection.json")) and not result["source_archives"]
    assert result["requests"][0]["status"] == "failed_or_unknown"


def test_existing_lock_is_not_removed_and_scope_is_spent(tmp_path):
    values = fixture(tmp_path)
    locked = values[2] / "controller.lock"
    locked.write_bytes(b"synthetic other process"); locked.chmod(0o600)
    result, _ = execute(values, lambda *args: pytest.fail("transport must not run"))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["read_attempts"].fraction() == 0
    assert locked.read_bytes() == b"synthetic other process"
    assert (values[2] / (values[0]["operation_id"] + ".claim.spent.json")).exists()


def test_expiry_and_current_source_hash_refuse_before_any_claim(tmp_path):
    values = fixture(tmp_path)
    with pytest.raises(c.Refusal):
        execute(values, lambda *args: pytest.fail("transport"), clock=lambda: c._clock(values[0]["expires_utc"]))
    assert not list(values[2].iterdir())
    values[1][c.MODULE] += b"# tampered"
    with pytest.raises(c.Refusal):
        execute(values, lambda *args: pytest.fail("transport"))
    assert not list(values[2].iterdir())


@pytest.mark.parametrize("budget", ["clock", "monotonic"])
def test_budget_during_requests_prevents_second_read_retains_unknown(tmp_path, budget):
    values = fixture(tmp_path)
    transport, calls = cloud()
    arguments = {"clock": lambda: c._clock(values[0]["expires_utc"]) if calls else values[3]} if budget == "clock" else {
        "monotonic": lambda: float(c.MAX_SECONDS * len(calls))}
    result, _ = execute(values, transport, **arguments)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert (values[2] / (values[0]["operation_id"] + ".read1.terminal.json")).exists()


@pytest.mark.parametrize("fault", ["receipt_hash", "source_hash", "receipt_mode", "source_link", "wrong_reference", "producer_hash"])
def test_post_baseline_custody_hash_and_ownership_refusals_before_network(tmp_path, fault):
    old, _, reference = baseline(tmp_path)
    root, operation = old[2], reference["operation_id"]
    if fault == "receipt_hash": reference["receipt_sha256"] = "f" * 64
    if fault == "source_hash": reference["sources_sha256"] = "f" * 64
    if fault == "receipt_mode": (root / (operation + ".result.json")).chmod(0o644)
    if fault == "source_link": os.link(root / (operation + ".read2.sources.json"), root / "synthetic.extra.link")
    if fault == "wrong_reference": reference["operation_id"] += "-FOREIGN"
    values = fixture(tmp_path, action="post-mia-source", reference=reference, root=root)
    if fault == "producer_hash":
        body = e.parse_json((root / (operation + ".result.json")).read_bytes())
        body["source_hashes"][c.MODULE] = "f" * 64
        raw = e.canonical(body); path = root / (operation + ".result.json")
        path.write_bytes(raw); reference.update(receipt_bytes=len(raw), receipt_sha256=c._sha(raw))
        values = (c._plan(**{key: reference if key == "baseline_reference" else values[0][key] for key in c._ARGUMENTS}), *values[1:])
    result, _ = execute(values, lambda *args: pytest.fail("no network"))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["read_attempts"].fraction() == 0
    assert result["scope_spent"] is True


@pytest.mark.parametrize("fault", ["action", "project", "endpoint", "attempt", "extra", "bundle", "expiry", "operation", "reference"])
def test_closed_plan_rejects_effect_and_scope_widening(tmp_path, fault):
    values = fixture(tmp_path)
    plan = values[0]
    if fault == "action": plan["action"] = "launch"
    if fault == "project": plan["project_id"] = 1
    if fault == "endpoint": plan["endpoint"] = "backtests/create"
    if fault == "attempt": plan["new_codex_attempts"] = 1
    if fault == "extra": plan["arbitrary_path"] = "/private"
    if fault == "bundle": plan["source_hashes"][c.BUNDLE] = "f" * 64
    if fault == "expiry": plan["expires_utc"] = (values[3] + timedelta(hours=5)).isoformat()
    if fault == "operation": plan["operation_id"] = "TPR-EXT26-MIA-SOURCE-POST-FOREIGN"
    if fault == "reference": plan["baseline_reference"] = {"path": "/private"}
    with pytest.raises(c.Refusal):
        execute(values, lambda *args: pytest.fail("transport"))
    assert not list(values[2].iterdir())


def test_production_rejects_fixture_transport_root_guard_and_clock(tmp_path):
    values = fixture(tmp_path)
    plan = c._plan(**{key: "production" if key == "mode" else values[0][key] for key in c._ARGUMENTS})
    with pytest.raises(c.Refusal):
        c._execute(plan, values[1], values[2], guard=lambda _: None, clock=lambda: values[3],
            monotonic=lambda: 0, transport=lambda *args: pytest.fail("transport"))
    with pytest.raises(c.Refusal):
        c._execute_fixture(plan, values[1], values[2], clock=lambda: values[3], transport=lambda *args: None)
    assert not list(values[2].iterdir())


def test_new_module_has_no_effect_route_or_old_mia_recovery_dependency():
    source = SOURCES[c.MODULE].decode()
    for forbidden in ("/api/v2/backtests/create", "/api/v2/files/update", "/api/v2/files/create", "/api/v2/object/", "mia_recovery"):
        assert forbidden not in source
    assert '"/api/v2/files/read"' in source
    assert "files._guard" not in source and "ops.Operations" not in source
    assert c.MODULE in c.SOURCE_PATHS and "research/__init__.py" in c.SOURCE_PATHS


def test_native_transport_refuses_foreign_payload_and_time_before_credentials():
    for payload, seconds in (({"projectId": 1}, 1), ({"projectId": c.PROJECT, "effect": True}, 1),
                             ({"projectId": c.PROJECT}, 0), ({"projectId": c.PROJECT}, 41)):
        with pytest.raises(c.Refusal):
            c._native_request(payload, seconds)


def test_import_closure_refuses_an_alternate_initializer(monkeypatch):
    c._imports()
    import research
    monkeypatch.setattr(research, "__file__", "/synthetic/foreign/research/__init__.py")
    with pytest.raises(c.Refusal):
        c._imports()


def test_full_diff_preserves_unicode_empty_content_and_final_newline_exactly():
    before = {"main.py": "old\n", "unicode.py": "αβ\n", "empty.py": ""}
    after = {"main.py": "new", "unicode.py": "αβ\nγ\n", "added.py": ""}
    changes, raw = c._diff(before, after)
    value = e.parse_json(raw)
    assert value["diff_format"] == "complete-whole-file-before-after-v1"
    for row in value["changes"]:
        assert row["before"] == before.get(row["name"]) and row["after"] == after.get(row["name"])
    assert b"unicode.py" not in e.canonical(changes) and b"added.py" not in e.canonical(changes)


def test_transport_exception_retains_uncertain_read_and_never_retries(tmp_path):
    values = fixture(tmp_path)
    calls = []
    def transport(payload, seconds):
        calls.append(payload)
        raise RuntimeError("SYNTHETIC-PRIVATE-ERROR")
    result, raw = execute(values, transport)
    assert len(calls) == 1 and result["status"] == "FAILED_OR_UNCERTAIN"
    assert result["failed_read_body_bytes_unknown"] is True
    assert result["requests"][0]["status"] == "failed_or_unknown"
    assert b"SYNTHETIC-PRIVATE-ERROR" not in raw


def test_post_refuses_forged_baseline_equality_even_if_hashes_are_supplied(tmp_path):
    old, receipt, reference = baseline(tmp_path)
    root, operation = old[2], reference["operation_id"]
    source_path = root / (operation + ".read2.sources.json")
    body = e.parse_json(source_path.read_bytes())
    body["files"]["main.py"] = "# not the frozen economics\n"
    raw_source = c._archive(operation, 2, body["files"])
    source_path.write_bytes(raw_source)
    receipt["source_archives"][-1] = {"name": source_path.name, "bytes": len(raw_source), "sha256": c._sha(raw_source)}
    receipt["inventory"] = c._public_inventory(c._inventory(body["files"]))
    raw_receipt = e.canonical(receipt)
    (root / (operation + ".result.json")).write_bytes(raw_receipt)
    reference.update(receipt_bytes=len(raw_receipt), receipt_sha256=c._sha(raw_receipt),
        sources_bytes=len(raw_source), sources_sha256=c._sha(raw_source))
    values = fixture(tmp_path, action="post-mia-source", reference=reference, root=root)
    result, _ = execute(values, lambda *args: pytest.fail("no network before proven baseline"))
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["read_attempts"].fraction() == 0


def test_scope_access_and_each_request_claim_exist_before_transport(tmp_path, monkeypatch):
    """Both effects observe claims and file+directory durability barriers first."""
    values = fixture(tmp_path)
    operation, root = values[0]["operation_id"], values[2]
    native, calls = cloud()
    observed, barriers, active = [], {}, []
    publish, sync = c._publish, c.os.fsync
    def observe_sync(fd):
        if active:
            kind = "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
            barriers[active[-1]].append(kind)
        return sync(fd)
    def observe_publish(directory, name, raw):
        barriers[name] = []
        active.append(name)
        try:
            return publish(directory, name, raw)
        finally:
            active.pop()
    monkeypatch.setattr(c.os, "fsync", observe_sync)
    monkeypatch.setattr(c, "_publish", observe_publish)
    def transport(payload, seconds):
        number = len(calls) + 1
        names = (operation + ".claim.spent.json", operation + ".access.json",
            operation + ".read" + str(number) + ".request.spent.json", "controller.lock")
        assert all((root / name).is_file() for name in names), "claims must precede transport"
        assert all((root / name).stat().st_mode & 0o777 == 0o600 for name in names)
        assert all(barriers[name] == ["file", "directory"] for name in names[:-1]), "durability must precede transport"
        scope = e.parse_json((root / names[0]).read_bytes())
        access = e.parse_json((root / names[1]).read_bytes())
        request = e.parse_json((root / names[2]).read_bytes())
        assert scope["operation_id"] == operation and scope["action"] == "baseline-source"
        assert access["plan_sha256"] == request["plan_sha256"] == c._sha(e.canonical(values[0]))
        assert request["endpoint"] == "files/read" and e.canonical(request["payload"]) == e.canonical(payload)
        observed.append(number)
        return native(payload, seconds)
    result, _ = execute(values, transport)
    assert result["status"] == "COMPLETED" and observed == [1, 2] and len(calls) == 2
