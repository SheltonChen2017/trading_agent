"""Only synthetic source bodies; no account, credentials or real private reads."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import stat
import sys

import pytest

from research.target_price_revisions_qc import extended_mia_capture_notebook_successor as c

e = c.e
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in c.SOURCE_PATHS}
PUBLIC_OFF = next(row["files"] for row in e.parse_json(SOURCES[c.BUNDLE])["candidates"]
    if row["candidate_id"] == c.CANDIDATE)
MAC_CUSTODY_REASON = (
    "Owner-selected Mac-only native custody: POSIX no-follow/UID/mode/directory-fsync "
    "and exact working-byte source pins are not Windows custody evidence"
)


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
    if sys.platform != "darwin":
        pytest.skip(MAC_CUSTODY_REASON)
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


def test_fixed_scope_and_public_off_inventory_are_portable():
    assert c.PROJECT == 37650980 and c.CANDIDATE == "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
    assert c.ENDPOINT == "files/read" and c.MAX_FILES == 17
    assert (c.MAX_FILE, c.MAX_RESPONSE, c.MAX_TOTAL, c.MAX_SECONDS, c.REQUEST_SECONDS) == (
        1048576, 4194304, 8388608, 120, 40)
    assert len(PUBLIC_OFF) == 10 and len(PUBLIC_OFF["main.py"].encode()) == 59931
    assert c.EXPECTED_FILES == set(PUBLIC_OFF)


@pytest.mark.skipif(sys.platform != "darwin", reason=MAC_CUSTODY_REASON)
def test_native_working_off_bundle_is_exact_frozen_byte_anchor():
    # Preserve the original byte anchor without normalizing a Windows checkout.
    assert c._sha(SOURCES[c.BUNDLE]) == c.BUNDLE_SHA256


def test_non_mac_fixture_skips_before_plan_or_directory_and_restores_seams(tmp_path, monkeypatch):
    platform, plan, mkdir = sys.platform, c._plan, Path.mkdir
    def denied(*args, **kwargs):
        raise AssertionError("native fixture effects must not run on an unsupported host")
    with monkeypatch.context() as patch:
        patch.setattr(sys, "platform", "win32")
        patch.setattr(c, "_plan", denied)
        patch.setattr(Path, "mkdir", denied)
        with pytest.raises(pytest.skip.Exception, match="Owner-selected Mac-only native custody"):
            fixture(tmp_path)
    assert sys.platform == platform and c._plan is plan and Path.mkdir is mkdir
    assert not (tmp_path / "synthetic-mia-source").exists()


@pytest.mark.parametrize("member", [c.BUNDLE, c.PREFIX + "extended_study_freeze.json",
                                    c.PREFIX + "extended_calendar.json"])
def test_pure_plan_refuses_tampered_public_hash_without_custody_or_effects(member, monkeypatch):
    # This synthetic map tests immutable public identifiers, not working bytes.
    hashes = dict.fromkeys(c.SOURCE_PATHS, "a" * 64)
    hashes.update({c.BUNDLE: c.BUNDLE_SHA256,
                   c.PREFIX + "extended_study_freeze.json": e.FREEZE_SHA256,
                   c.PREFIX + "extended_calendar.json": c.ops.CALENDAR_SHA256})
    def denied(*args, **kwargs):
        raise AssertionError("pure public plan must not enter native custody or publication")
    monkeypatch.setattr(c.files, "_directory", denied)
    monkeypatch.setattr(c, "_publish", denied)
    arguments = dict(action="baseline-source", operation_id="TPR-EXT26-MIA-SOURCE-BASELINE-SYNTHETIC-PUBLIC",
        git_head="a" * 40, source_hashes=hashes, owner_instruction_sha256="b" * 64,
        created_utc="2026-10-12T00:00:00Z", expires_utc="2026-10-12T01:00:00Z", mode="offline-fixture")
    control = c._plan(**arguments)
    assert control["new_looks"] == control["new_codex_attempts"] == 0
    assert control["mia_message_or_job"] is control["automatic_retry"] is False
    corrupted = {**hashes, member: "f" * 64}
    with pytest.raises(c.Refusal):
        c._plan(**{**arguments, "source_hashes": corrupted})
    assert arguments["source_hashes"] == hashes and control["source_hashes"] == hashes


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
        if fault == "too_many": response["files"] = [{"name": f"f{number}.py", "content": ""} for number in range(c.MAX_FILES + 1)]
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


@pytest.mark.skipif(sys.platform != "darwin", reason=MAC_CUSTODY_REASON)
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


REGISTERED_DIAGNOSTIC_NOTEBOOK = "tpr_ext26_witness_read_20261022_001.ipynb"


def test_identified_successor_changes_only_self_identity_and_inventory_capacity():
    """Byte comparison pins every unchanged predecessor boundary, not a wrapper."""
    predecessor = (ROOT / c.PREFIX / "extended_mia_capture.py").read_text()
    old_intro = "\"\"\"Two fixed EXT26 OFF source archives, never a Mia message or launch.\n"
    new_intro = "\"\"\"Identified notebook-capacity successor of the fixed EXT26 OFF capture.\n\nOnly the module identity and all-file inventory cap change from the preserved\npredecessor: 17 files may now include the separately registered research-only\ndiagnostic notebook. Unexpected files remain privately archived and hash-only\nin public receipts; neither notebook contents nor strategy economics execute.\n\nTwo fixed EXT26 OFF source archives, never a Mia message or launch.\n"
    assert predecessor.startswith(old_intro)
    expected = predecessor.replace(old_intro, new_intro, 1).replace(
        'MODULE = PREFIX + "extended_mia_capture.py"',
        'MODULE = PREFIX + "extended_mia_capture_notebook_successor.py"', 1).replace(
        "MAX_FILES, MAX_FILE = 16, 1024 * 1024",
        "MAX_FILES, MAX_FILE = 17, 1024 * 1024", 1).replace(
        '                request.update(response_bytes=len(raw), http_status=status)\n'
        '                check(); projection = e.project_wire(raw, credential=token)\n',
        '                request.update(response_bytes=len(raw), http_status=status)\n'
        '                # An unusable echo credential must refuse before any projection is retained.\n'
        '                if type(token) is not str or re.fullmatch(r"[!-~]{1,256}", token) is None:\n'
        '                    _fail()\n'
        '                check(); projection = e.project_wire(raw, credential=token)\n', 1).replace(
        '        raw_report = e.canonical(report)\n        if len(raw_report) > MAX_RECEIPT:\n            _fail()\n',
        '        raw_report = e.canonical(report)\n        if len(raw_report) > MAX_RECEIPT:\n'
        '            # The disclosure is refused, but the spent scope still gets a receipt.\n'
        '            for key in ("inventory", "changes", "complete_private_diff"):\n                report[key] = None\n'
        '            for key in ("missing_expected_files", "different_expected_files", "unexpected_files"):\n                report[key] = []\n'
        '            report["status"] = "FAILED_OR_UNCERTAIN"; report["public_size_refused"] = True\n            raw_report = e.canonical(report)\n            if len(raw_report) > MAX_RECEIPT:\n                _fail()\n', 1)
    # TPR-CR29: the two safety blocks above are the only other permitted differences.
    assert SOURCES[c.MODULE].decode() == expected
    assert c.MODULE == c.PREFIX + "extended_mia_capture_notebook_successor.py"
    assert c.MODULE in c.SOURCE_PATHS
    assert c.PREFIX + "extended_mia_capture.py" not in c.SOURCE_PATHS
    assert (c.MAX_RESPONSE, c.MAX_TOTAL, c.MAX_ARCHIVE, c.MAX_SECONDS, c.REQUEST_SECONDS) == (
        4 * 1024 * 1024, 8 * 1024 * 1024, 16 * 1024 * 1024, 120, 40)


def test_seventeenth_registered_notebook_is_retained_twice_as_unexpected_private_source(tmp_path):
    """Capacity permits custody only, never execution or economics acceptance."""
    values = fixture(tmp_path)
    notebook = '{"cells":[{"cell_type":"markdown","source":["SYNTHETIC-ONLY α\\n"]}]}\\n'
    source = {**PUBLIC_OFF, "research.ipynb": '{"cells":[]}\\n',
        **{f"extra{number}.py": "# SYNTHETIC-PRESERVED\\n" for number in range(5)},
        REGISTERED_DIAGNOSTIC_NOTEBOOK: notebook}
    assert len(source) == c.MAX_FILES == 17
    transport, calls = cloud(source)
    result, raw = execute(values, transport)
    assert result["status"] == "COMPLETED" and len(calls) == 2
    assert result["stable_source_inventory"] is True
    assert result["baseline_expected_files_equal"] is True
    assert len(result["inventory"]) == 17
    notebook_hash = c._sha(REGISTERED_DIAGNOSTIC_NOTEBOOK.encode())
    metadata = result["inventory"]["unrecognized-name-sha256-" + notebook_hash]
    assert metadata["bytes"].fraction() == len(notebook.encode())
    assert metadata["sha256"] == c._sha(notebook.encode())
    unexpected = next(row for row in result["unexpected_files"] if row.get("name_sha256") == notebook_hash)
    assert unexpected["classification"] == "unrecognized_source"
    assert len(result["unexpected_files"]) == 6
    assert REGISTERED_DIAGNOSTIC_NOTEBOOK.encode() not in raw and b"SYNTHETIC-ONLY" not in raw
    assert len(result["source_archives"]) == 2
    for artifact in result["source_archives"]:
        path = values[2] / artifact["name"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert e.parse_json(path.read_bytes())["files"] == source
        assert c._sha(path.read_bytes()) == artifact["sha256"]
    for key in ("economics_accepted", "performance_accepted", "compiled_job_binding_verified",
                "candidate_mutation", "mia_message_or_job", "canonical_admission", "trading"):
        assert result[key] is False
    assert result["new_codex_attempts"].fraction() == result["new_looks"].fraction() == 0


# TPR-CR28 regression: every production seam is checked on its own, with the
# real clock held in-window so only the seam under test can refuse.


@pytest.mark.parametrize("fault", ["root", "transport", "guard", "clock", "monotonic"])
def test_each_production_seam_refuses_a_fixture_substitution_on_its_own(tmp_path, monkeypatch, fault):
    values = fixture(tmp_path)
    plan = c._plan(**{key: "production" if key == "mode" else values[0][key] for key in c._ARGUMENTS})
    monkeypatch.setattr(c, "_production_clock", lambda: values[3])
    # The real guard is replaced by a sentinel so that reaching it (instead of
    # refusing at the seam check) is a failure wherever pytest runs from.
    def reached_guard(_head): raise AssertionError("seam check did not refuse before the guard")
    monkeypatch.setattr(c, "_guard", reached_guard)
    kwargs = {"guard": c._guard, "clock": c._production_clock, "monotonic": c.time.monotonic, "transport": c._native_request}
    root = c.PRIVATE_ROOT
    if fault == "root": root = values[2]
    elif fault == "transport": kwargs["transport"] = lambda *args: pytest.fail("transport")
    elif fault == "guard": kwargs["guard"] = lambda _: None
    elif fault == "clock": kwargs["clock"] = lambda: values[3]
    else: kwargs["monotonic"] = lambda: 0
    with pytest.raises(c.Refusal):
        c._execute(plan, values[1], root, **kwargs)
    assert not list(values[2].iterdir())


# TPR-CR29 regressions: an unusable echo credential refuses before projection, and an
# oversized public receipt leaves a body-free failure receipt instead of no receipt.


@pytest.mark.parametrize("token", ["", " ", "x" * 257, None])
def test_unusable_echo_credential_refuses_before_any_projection_is_retained(tmp_path, token):
    values = fixture(tmp_path); transport, calls = cloud(token=token)
    result, _raw = execute(values, transport)
    assert len(calls) == 1 and result["status"] == "FAILED_OR_UNCERTAIN"
    assert result["requests"][0]["status"] == "failed_or_unknown" and result["requests"][0]["projection"] is None
    assert not list(values[2].glob("*.projection.json"))


def test_oversized_public_receipt_is_refused_with_a_body_free_receipt(tmp_path, monkeypatch):
    (tmp_path / "full").mkdir(); (tmp_path / "small").mkdir()
    transport, _calls = cloud()
    _full_result, full = execute(fixture(tmp_path / "full"), transport)
    monkeypatch.setattr(c, "MAX_RECEIPT", len(full) - 1)
    values = fixture(tmp_path / "small")
    result, _raw = execute(values, cloud()[0])
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["public_size_refused"] is True
    assert result["inventory"] is None and result["read_attempts"].fraction() == 2
    assert (values[2] / (values[0]["operation_id"] + ".result.json")).exists()
