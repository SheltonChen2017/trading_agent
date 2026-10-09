"""Synthetic recovery collector evidence; no account, packet or network I/O."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json

import pytest

from research.target_price_revisions_qc import mia_recovery as m


def specification():
    now = datetime.now(timezone.utc)
    cases, files = [], {}
    for candidate in sorted(m.ops.CANDIDATES):
        policy = {"schema": "tpr-qc-matched-config-v1", "study_id": m.ops.STUDY,
            "freeze_sha256": m.ops.FREEZE_HASH, "candidate_id": candidate,
            "arm": "tpr_on" if "-ON-" in candidate else "tpr_off" if "-OFF-" in candidate else "etf_basket",
            "cost": "adverse" if "-ADVERSE-" in candidate else "baseline",
            "slippage": "0.0015" if "-ADVERSE-" in candidate else "0.001"}
        config = m.ops.canonical(policy).decode()
        source = {"main.py": "# synthetic reviewed main\n", "proxy_core.py": "# immutable synthetic\n",
                  "signal_packet.py": "# immutable synthetic packet parser\n",
                  "matched_config.py": "CONFIG_JSON = " + repr(config) + "\n"}
        files[candidate] = source
        cases.append({"candidate_id": candidate, "project_name": candidate + "-private",
                      "config_sha256": m.ops.digest(config.encode()),
                      "source_hashes": {name: m.ops.digest(text.encode()) for name, text in source.items()}})
    op = {"schema": "tpr-qc-operations-manifest-v2", "study_id": m.ops.STUDY,
        "operation_id": "TPR-MIA-SYNTHETIC-001", "created_utc": (now - timedelta(minutes=1)).isoformat(),
        "expires_utc": (now + timedelta(hours=1)).isoformat(), "baseline_git_head": m.ops.BASELINE,
        "freeze_sha256": m.ops.FREEZE_HASH, "repository_source_hashes": {
            m.ops.MODULE_PATH: "a" * 64, m.ops.FREEZE_PATH: m.ops.FREEZE_HASH,
            m.MODULE_PATH: "b" * 64, "research/target_price_revisions_qc/matched_audit_v3.py": "c" * 64},
        "input_hashes": {"signal-packet.json": m.ops.PACKET_HASH}, "packet_path": m.ops.PACKET_PATH,
        "packet_sha256": m.ops.PACKET_HASH, "candidates": cases, "max_requests": 1000,
        "max_response_bytes": 16777216, "request_timeout_seconds": 30,
        "max_attempts_per_candidate": 3, "log_prefix": "MATCHED_"}
    on = next(row for row in cases if row["candidate_id"] == m.CANDIDATE)
    wrapper = {"schema": "tpr-mia-readonly-recovery-manifest-v1", "operations_manifest": op,
        "project_id": m.PROJECT_ID, "candidate_id": m.CANDIDATE, "reviewed_preview_sha256": "d" * 64,
        "source_hashes": on["source_hashes"], "notebook_sha256": m.NOTEBOOK_HASH,
        "original_notebook_sha256": m.OLD_NOTEBOOK_HASH, "config_sha256": on["config_sha256"],
        "max_mia_jobs": 1, "codex_attempts_consumed": 3,
        "private_packet_key": f"tpr-matched/{m.ops.STUDY}/{m.ops.PACKET_HASH}.json"}
    return wrapper, files


class Cloud:
    def __init__(self, source):
        self.calls = []
        self.source = {**source, "research.ipynb": "{\"cells\":[]}"}
        self.compile_id = "mia-compile-synthetic"
        self.backtest_id = "mia-backtest-synthetic"
        self.compile_state = "BuildSuccess"
        self.result = {"backtestId": self.backtest_id, "completed": True, "progress": 1,
                       "status": "Completed.", "error": None, "statistics": {}}
        self.orders = [{"id": value, "status": 3} for value in range(104)]
        self.logs = ["MATCHED_NAV {}", "MATCHED_COVERAGE {}", "MATCHED_SUMMARY {}"]
        self.loading = None
        self.after_source_changed = False

    def __call__(self, endpoint, raw, content_type):
        self.calls.append(endpoint)
        payload = json.loads(raw)
        assert payload["projectId"] == m.PROJECT_ID
        if endpoint == "files/read":
            return {"success": True, "files": [{"name": name, "content": text} for name, text in self.source.items()]}
        if endpoint == "compile/read":
            return {"success": True, "compileId": self.compile_id, "state": self.compile_state}
        assert payload["backtestId"] == self.backtest_id
        if endpoint == "backtests/read":
            return {"success": True, "backtest": deepcopy(self.result)}
        if endpoint == self.loading:
            return {"success": True, "status": "loading", "error": "synthetic waiting"}
        if endpoint == "backtests/orders/read":
            return {"success": True, "orders": self.orders[payload["start"]:payload["end"]], "length": len(self.orders)}
        if endpoint == "backtests/read/log":
            if self.after_source_changed:
                self.source["proxy_core.py"] += "# forbidden concurrent edit\n"
            return {"success": True, "logs": self.logs[payload["start"]:payload["end"]], "length": len(self.logs)}
        raise AssertionError("effectful endpoint reached synthetic transport")


@pytest.fixture
def environment(tmp_path, monkeypatch):
    body, source = specification()
    cloud = Cloud(source[m.CANDIDATE])
    monkeypatch.setattr(m, "NOTEBOOK_HASH", m.ops.digest(cloud.source["research.ipynb"].encode()))
    body["notebook_sha256"] = m.NOTEBOOK_HASH
    recovery = m.Recovery(body, manifest_sha256=m.ops.digest(m.ops.canonical(body)),
                         _fixture_root=tmp_path / "private", _fixture_transport=cloud)
    recovery.ops.prepare_access()
    recovery.ops.exclusive(m.CANDIDATE + ".project.json", {"candidate_id": m.CANDIDATE,
        "project_id": m.PROJECT_ID, "name": m.CANDIDATE + "-private", "owner": True,
        "max_file_size": 64000, "organization_id": "synthetic-org"})
    recovery.ops.exclusive(m.CANDIDATE + ".mia-recovery.spent.json", {
        "recovery_manifest_sha256": recovery.manifest_sha256, "candidate_id": m.CANDIDATE,
        "project_id": m.PROJECT_ID, "codex_attempts_consumed": 3, "max_mia_jobs": 1})
    return recovery, cloud


def ready(environment):
    recovery, cloud = environment
    assert recovery.verify_compile(cloud.compile_id)["state"] == "BuildSuccess"
    ui = {"schema": "tpr-mia-ui-job-claim-v1", "project_id": m.PROJECT_ID, "candidate_id": m.CANDIDATE,
        "compile_id": cloud.compile_id, "backtest_id": cloud.backtest_id,
        "source_hashes": recovery.manifest["source_hashes"], "at": m.ops.utc(), "launch_via_mia": True}
    name = "synthetic-ui-job.json"
    sha = recovery.ops.exclusive(name, ui)
    return recovery, cloud, {"ui_claim": name, "ui_claim_sha256": sha}


def test_closed_recovery_manifest_control():
    body, _ = specification()
    assert m.validate_manifest(body, m.ops.digest(m.ops.canonical(body))) == body


def preview_environment(tmp_path, monkeypatch, *, padded=False):
    body, files = specification()
    private = tmp_path / m.ops.STUDY
    seed = m.ops.Operations(body["operations_manifest"],
        manifest_sha256=m.ops.digest(m.ops.canonical(body["operations_manifest"])),
        _fixture_root=private, _fixture_transport=lambda *args: pytest.fail("prepare network"))
    seed.exclusive(m.CANDIDATE + ".project.json", {"candidate_id": m.CANDIDATE,
        "project_id": m.PROJECT_ID, "name": m.CANDIDATE + "-private", "owner": True,
        "max_file_size": 64000, "organization_id": "synthetic-org"})
    for number in (1, 2, 3):
        middle = f"{number:04d}" if padded else str(number)
        seed.exclusive(m.CANDIDATE + f".attempt.{middle}.reserved.json", {
            "candidate_id": m.CANDIDATE, "project_id": m.PROJECT_ID, "attempt": number})
    seed.exclusive("packet-upload.completed.json", {"packet_sha256": m.ops.PACKET_HASH,
        "key": f"tpr-matched/{m.ops.STUDY}/{m.ops.PACKET_HASH}.json"})
    current = '{"cells":[],"metadata":{}}'
    old = json.dumps(json.loads(current), indent=1, sort_keys=True, ensure_ascii=True) + "\n"
    monkeypatch.setattr(m, "NOTEBOOK_HASH", m.ops.digest(current.encode()))
    monkeypatch.setattr(m, "OLD_NOTEBOOK_HASH", m.ops.digest(old.encode()))
    rendered = {"cases": [{**row, "files": deepcopy(files[row["candidate_id"]])}
                          for row in body["operations_manifest"]["candidates"]]}
    reviewed = {**files[m.CANDIDATE], "main.py": "# additive synthetic instrumentation\n",
                "research.ipynb": current}
    preview = {"schema": "tpr-mia-reviewed-cloud-preview-v1", "project_id": m.PROJECT_ID,
               "candidate_id": m.CANDIDATE, "files": reviewed, "original_notebook_content": old}
    name = "synthetic-reviewed-preview.json"
    sha = seed.exclusive(name, preview)
    monkeypatch.setattr(m.ops, "PRIVATE_PARENT", tmp_path)
    monkeypatch.setattr(m.driver, "render_sources", lambda: deepcopy(rendered))
    original = m.Recovery
    def make(manifest, *, manifest_sha256):
        return original(manifest, manifest_sha256=manifest_sha256,
            _fixture_root=private, _fixture_transport=lambda *args: pytest.fail("prepare network"))
    monkeypatch.setattr(m, "Recovery", make)
    return seed, name, sha, preview, rendered


def test_prepare_reads_actual_unpadded_attempt_receipts_and_never_private_packet(tmp_path, monkeypatch):
    seed, name, sha, _, _ = preview_environment(tmp_path, monkeypatch)
    original_read = m.ops._read
    observed = []
    def no_packet(directory, filename, maximum):
        observed.append(filename)
        assert not filename.startswith("signal-packet")
        assert filename != "fixture-packet.json"
        return original_read(directory, filename, maximum)
    monkeypatch.setattr(m.ops, "_read", no_packet)
    result = m.prepare("TPR-MIA-SYNTHETIC-NEW", name, sha)
    assert result["new_codex_attempts"] == 0 and result["max_mia_jobs"] == 1
    assert all(m.CANDIDATE + f".attempt.{n}.reserved.json" in observed for n in (1, 2, 3))
    assert not any(".attempt.000" in name for name in observed)
    assert seed._value(m.CANDIDATE + ".mia-recovery.spent.json")["codex_attempts_consumed"] == 3


def test_padded_fake_attempts_do_not_replace_real_receipt_shape(tmp_path, monkeypatch):
    _, name, sha, _, _ = preview_environment(tmp_path, monkeypatch, padded=True)
    with pytest.raises(m.ops.Refusal, match="private read"):
        m.prepare("TPR-MIA-SYNTHETIC-NEW", name, sha)


def test_new_operation_name_cannot_reset_single_mia_look(tmp_path, monkeypatch):
    seed, name, sha, _, _ = preview_environment(tmp_path, monkeypatch)
    m.prepare("TPR-MIA-SYNTHETIC-NEW", name, sha)
    with pytest.raises(m.ops.Refusal, match="scope-renaming"):
        m.prepare("TPR-MIA-SYNTHETIC-NEXT", name, sha)
    assert not (seed.root / "access.TPR-MIA-SYNTHETIC-NEXT.json").exists()


@pytest.mark.parametrize("name", ["proxy_core.py", "signal_packet.py", "matched_config.py", "research.ipynb"])
def test_preview_foreign_source_or_non_format_notebook_changes_are_refused(name, tmp_path, monkeypatch):
    _, _, _, preview, rendered = preview_environment(tmp_path, monkeypatch)
    preview["files"][name] += "\n# foreign source\n"
    raw = m.ops.canonical(preview)
    with pytest.raises(m.ops.Refusal):
        m._preview(raw, m.ops.digest(raw), rendered)


def test_complete_original_notebook_identity_is_not_caller_selected():
    assert m.OLD_NOTEBOOK_HASH == "212a51a9f8eb8c29ef77442c5b3db3cc0fe308d7c18f9f2c6ecf7ed86186778e"
    assert m.NOTEBOOK_HASH == "af27200522531d426185f4daa25d23610c164134e3ab7fdf38919616d0d5b344"


@pytest.mark.parametrize("field,value", [
    ("max_mia_jobs", 2), ("max_mia_jobs", True), ("codex_attempts_consumed", 2),
    ("codex_attempts_consumed", True), ("project_id", 37547068), ("project_id", True),
    ("candidate_id", "TPR-MATCHED-OFF-BASE-v1"), ("notebook_sha256", "0" * 64),
    ("reviewed_preview_sha256", "bad"), ("private_packet_key", "foreign/key"),
    ("schema", "foreign"), ("source_hashes", {}), ("config_sha256", "0" * 64),
])
def test_closed_recovery_manifest_refuses_scope_changes(field, value):
    body, _ = specification()
    body[field] = value
    with pytest.raises(m.ops.Refusal):
        m.validate_manifest(body, m.ops.digest(m.ops.canonical(body)))


def test_source_inventory_must_bind_collector_and_pure_auditor():
    for relative in (m.MODULE_PATH, "research/target_price_revisions_qc/matched_audit_v3.py"):
        body, _ = specification()
        del body["operations_manifest"]["repository_source_hashes"][relative]
        with pytest.raises(m.ops.Refusal):
            m.validate_manifest(body, m.ops.digest(m.ops.canonical(body)))


@pytest.mark.parametrize("endpoint", sorted(m.ops.ENDPOINTS - m.READ_ENDPOINTS))
def test_transport_rejects_every_non_read_endpoint_before_network(endpoint, environment):
    recovery, cloud = environment
    with pytest.raises(m.ops.Refusal, match="read-only"):
        recovery.ops._request(endpoint, {})
    assert cloud.calls == []


def test_compile_is_read_only_bound_and_immutable(environment):
    recovery, cloud = environment
    result = recovery.verify_compile(cloud.compile_id)
    assert result == {"compile_id": cloud.compile_id, "state": "BuildSuccess", "new_codex_attempts": 0}
    assert cloud.calls == ["files/read", "compile/read", "files/read"]
    assert recovery._compile()["source_hashes"] == recovery.manifest["source_hashes"]
    with pytest.raises(m.ops.Refusal, match="replace"):
        recovery.verify_compile("different-compile")
    assert cloud.calls == ["files/read", "compile/read", "files/read"]


@pytest.mark.parametrize("state", ["BuildError", "InQueue", "Unknown"])
def test_compile_not_success_never_admits_job(state, environment):
    recovery, cloud = environment
    cloud.compile_state = state
    assert recovery.verify_compile(cloud.compile_id)["state"] == state
    with pytest.raises(m.ops.Refusal):
        recovery.bind_job(cloud.backtest_id)
    assert "backtests/read" not in cloud.calls


def test_compile_failure_is_retainable_and_explicit_reverification_not_new_attempt(environment):
    recovery, cloud = environment
    cloud.compile_state = "InQueue"
    recovery.verify_compile(cloud.compile_id)
    cloud.compile_state = "BuildSuccess"
    recovery.verify_compile(cloud.compile_id)
    assert recovery._compile()["compile_id"] == cloud.compile_id
    assert recovery.ops._value(recovery.prefix + ".compile.0001.wire.json")["state"] == "InQueue"
    assert set(cloud.calls) <= m.READ_ENDPOINTS


@pytest.mark.parametrize("name", sorted(m.ops.SOURCE_FILES | {"research.ipynb"}))
def test_each_reviewed_cloud_source_must_remain_exact(name, environment):
    recovery, cloud = environment
    cloud.source[name] += "\n# changed\n"
    with pytest.raises(m.ops.Refusal, match="changed"):
        recovery.verify_compile(cloud.compile_id)
    assert "compile/read" not in cloud.calls


def test_no_arbitrary_job_without_explicit_trusted_ui_binding(environment):
    recovery, cloud = environment
    recovery.verify_compile(cloud.compile_id)
    with pytest.raises(m.ops.Refusal, match="UI job claim"):
        recovery.poll(cloud.backtest_id)
    assert "backtests/read" not in cloud.calls


@pytest.mark.parametrize("old_id", sorted(m.PRIOR_CODEX_JOBS))
def test_old_codex_job_cannot_be_relabelled_as_the_mia_recovery_look(old_id, environment):
    recovery, cloud, claim = ready(environment)
    with pytest.raises(m.ops.Refusal, match="Mia backtest"):
        recovery.bind_job(old_id, **claim)
    assert "backtests/read" not in cloud.calls


@pytest.mark.parametrize("field,value", [
    ("launch_via_mia", False), ("compile_id", "foreign"), ("backtest_id", "foreign"),
    ("project_id", 1), ("candidate_id", "TPR-MATCHED-OFF-BASE-v1"),
    ("source_hashes", {}), ("at", "2020-01-01T00:00:00Z"),
])
def test_ui_claim_cannot_supply_wrong_source_job_or_scope_clock(field, value, environment):
    recovery, cloud, claim = ready(environment)
    raw = recovery.ops._value(claim["ui_claim"])
    raw[field] = value
    name = "synthetic-bad-ui.json"
    sha = recovery.ops.exclusive(name, raw)
    with pytest.raises(m.ops.Refusal, match="differs"):
        recovery.poll(cloud.backtest_id, ui_claim=name, ui_claim_sha256=sha)
    assert "backtests/read" not in cloud.calls


def test_missing_native_compile_id_requires_ui_claim_and_same_job_never_changes(environment):
    recovery, cloud, claim = ready(environment)
    assert "compileId" not in cloud.result
    assert recovery.poll(cloud.backtest_id, **claim)["completed"] is True
    assert recovery.poll(cloud.backtest_id)["new_development_looks"] == 0
    with pytest.raises(m.ops.Refusal, match="only once"):
        recovery.poll("different-job")


@pytest.mark.parametrize("field,value", [("compileId", "wrong"), ("projectId", 1), ("backtestId", "wrong")])
def test_native_result_identity_conflicts_are_refused(field, value, environment):
    recovery, cloud, claim = ready(environment)
    cloud.result[field] = value
    with pytest.raises(m.ops.Refusal, match="does not match"):
        recovery.poll(cloud.backtest_id, **claim)


@pytest.mark.parametrize("action", ["poll", "collect"])
@pytest.mark.parametrize("shape", ["loading", "foreign_job", "foreign_compile"])
def test_original_result_wire_is_retained_before_loading_or_identity_refusal(action, shape, environment):
    recovery, cloud, claim = ready(environment)
    if shape == "loading":
        response = {"success": True, "status": "Loading", "message": "Synthetic own result still loading"}
    else:
        native = deepcopy(cloud.result)
        native["backtestId" if shape == "foreign_job" else "compileId"] = "foreign-native-identity"
        response = {"success": True, "backtest": native}
    original = recovery.ops.transport
    def transport(endpoint, raw, content_type):
        if endpoint == "backtests/read":
            cloud.calls.append(endpoint)
            return deepcopy(response)
        return original(endpoint, raw, content_type)
    recovery.ops.transport = transport
    if action == "poll":
        with pytest.raises(m.ops.Refusal, match="does not match"):
            recovery.poll(cloud.backtest_id, **claim)
        filename = recovery.prefix + ".poll.0001.result-wire.json"
    else:
        collected = recovery.collect(cloud.backtest_id, **claim)
        assert collected["collection_errors"] and "audit" not in collected
        filename = recovery.prefix + ".collection.0001.result-wire.json"
    assert recovery.ops._value(filename) == response
    assert cloud.calls.count("backtests/read") == 1
    assert "backtests/orders/read" not in cloud.calls
    assert set(cloud.calls) <= m.READ_ENDPOINTS


def test_compile_response_hash_corruption_refuses_without_job_read(environment):
    recovery, cloud, claim = ready(environment)
    verified = recovery.ops._value(recovery.prefix + ".compile.verified.json")
    (recovery.ops.root / verified["compile_response_file"]).write_bytes(m.ops.canonical({"state": "BuildSuccess"}))
    with pytest.raises(m.ops.Refusal, match="verification"):
        recovery.poll(cloud.backtest_id, **claim)
    assert "backtests/read" not in cloud.calls


def test_success_collection_forwards_exact_evidence_and_keeps_delisting_diagnostic(environment, monkeypatch):
    recovery, cloud, claim = ready(environment)
    from research.target_price_revisions_qc import matched_audit_v3 as audit
    def pure(result, logs, pages, receipt, policy):
        assert result["backtest"]["status"] == "Completed."
        assert len(pages) == 2 and sum(len(page["orders"]) for page in pages) == 104
        assert receipt["evidence_hashes"] == {"result": m.ops.digest(m.ops.canonical(result)),
            "logs": m.ops.digest(m.ops.canonical(logs)),
            "order_pages": [m.ops.digest(m.ops.canonical(page)) for page in pages]}
        assert receipt["source_hashes"] == recovery.manifest["source_hashes"]
        assert policy["candidate_id"] == m.CANDIDATE and policy["slippage"] == "0.001"
        return {"meaningful_execution": False, "diagnostic_reasons": ["unexplained_delisting"]}
    monkeypatch.setattr(audit, "audit_result", pure)
    result = recovery.collect(cloud.backtest_id, **claim)
    assert result["collection_errors"] == []
    assert result["audit"]["meaningful_execution"] is False
    assert result["audit"]["diagnostic_reasons"] == ["unexplained_delisting"]
    assert cloud.calls.count("compile/read") == 3
    assert set(cloud.calls) <= m.READ_ENDPOINTS
    index = recovery.ops._value(recovery.prefix + ".collection.0001.evidence-index.json")
    for entry in index["files"]:
        assert entry["sha256"] == m.ops.digest(recovery.ops.read_private(entry["name"]))


@pytest.mark.parametrize("endpoint", ["backtests/orders/read", "backtests/read/log"])
def test_loading_retained_as_diagnostic_not_empty_data_or_implicit_retry(endpoint, environment):
    recovery, cloud, claim = ready(environment)
    cloud.loading = endpoint
    result = recovery.collect(cloud.backtest_id, **claim)
    assert result["collection_errors"] and "audit" not in result
    kind = "orders" if endpoint.endswith("orders/read") else "logs"
    path = recovery.prefix + f".collection.0001.{kind}.00000.wire.json"
    assert recovery.ops._value(path)["status"] == "loading"
    assert cloud.calls.count(endpoint) == 1


def test_post_job_cloud_change_withholds_audit_and_retains_order_evidence(environment):
    recovery, cloud, claim = ready(environment)
    cloud.after_source_changed = True
    result = recovery.collect(cloud.backtest_id, **claim)
    assert result["collection_errors"] and "audit" not in result
    assert recovery.ops._value(recovery.prefix + ".collection.0001.error.json")["stage"] == "source_after"
    assert recovery.ops._value(recovery.prefix + ".collection.0001.orders.00000.wire.json")["length"] == 104


def test_five_explicit_same_job_collection_cap_never_launches_or_resets(environment):
    recovery, cloud, claim = ready(environment)
    cloud.loading = "backtests/orders/read"
    for number in range(1, 6):
        assert recovery.collect(cloud.backtest_id, **claim)["collection_round"] == number
    before = len(cloud.calls)
    with pytest.raises(m.ops.Refusal, match="five"):
        recovery.collect(cloud.backtest_id)
    assert len(cloud.calls) == before and set(cloud.calls) <= m.READ_ENDPOINTS


@pytest.mark.parametrize("bad", [True, "1", None])
def test_order_identity_exact_int_census_required(bad, environment):
    recovery, cloud, claim = ready(environment)
    cloud.orders[0]["id"] = bad
    result = recovery.collect(cloud.backtest_id, **claim)
    assert result["collection_errors"] and "audit" not in result


def test_import_and_cli_have_no_effectful_or_implicit_identity_path(monkeypatch):
    monkeypatch.setattr(m.ops.http.client, "HTTPSConnection", lambda *args, **kwargs: pytest.fail("network on import"))
    original_get = m.ops.os.environ.get
    def guarded_get(key, *args, **kwargs):
        if key in {"QC_USER_ID", "QC_API_TOKEN"}:
            pytest.fail("credential on import")
        return original_get(key, *args, **kwargs)
    monkeypatch.setattr(m.ops.os.environ, "get", guarded_get)
    importlib.reload(m)
    monkeypatch.setattr(m.driver, "preflight", lambda: {})
    for action in ("compile", "launch", "create", "packet-upload", "source-upload"):
        with pytest.raises(SystemExit):
            m.main([action, "--operation", "synthetic"])
    with pytest.raises(SystemExit):
        m.main(["poll", "--operation", "synthetic"])
