"""Synthetic Mia reads only: real account, private root and network forbidden."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_mia_result_capture as m

e, c = m.e, m.capture
ROOT = Path(__file__).resolve().parents[2]
SOURCES = {name: (ROOT / name).read_bytes() for name in m.SOURCE_PATHS}
FROZEN = next(row for row in e.parse_json(SOURCES[c.BUNDLE])["candidates"] if row["candidate_id"] == m.CANDIDATE)
NOTEBOOK = '{"cells":[]}\n'
REPAIR = '''from extended_compressed_store import CompressedAuditStore
class AuditKeyRecoveryStore(CompressedAuditStore):
    def _key(self, key):
        return super()._key(key).replace('.json.gz', '_json.gz')
    def _sidecar(self):
        raise ValueError('SYNTHETIC NOT EXECUTED')
'''

# Plausible complete Mia source for DISCLOSURE only; never executed and not
# evidence of repaired economics, native compatibility or collision safety.
MIA_LIKE = '''from __future__ import annotations
import re
from extended_compressed_store import CompressedAuditStore as _Base, canonical, encode_gzip, decode_gzip, sha256, MAX_METADATA, _fail
_MAX_CHUNKS = 1024
_PATH_RE = re.compile(r"^\\.?[^.]+(?:\\.[A-Za-z0-9]+)?$", re.ASCII)
_SUFFIXES = ("index.json", "storage_json.gz")
class CompressedAuditStore(_Base):
    def __init__(self, native_store, binding):
        super().__init__(native_store, binding)
        self._validate_full_key(self.prefix + 'storage_json.gz')
        self._mapping = self._build_physical_mapping()
        self._collision_sweep()
    @staticmethod
    def _validate_full_key(key):
        if not isinstance(key, str) or key.count('/') > 100 or _PATH_RE.fullmatch(key) is None:
            _fail()
        return key
    def _build_physical_mapping(self):
        mapping = {self.prefix + 'chunks' + str(number) + '.json': self.prefix + 'chunks' + str(number) + '_json.gz' for number in range(_MAX_CHUNKS)}
        return dict(mapping)
    def _sweep_keys(self):
        keys = tuple(self._mapping.values())
        if len(set(keys)) != len(keys):
            _fail()
        return keys
    def _collision_sweep(self):
        if any(self.native.contains_key(key) for key in self._sweep_keys()):
            _fail()
    def _key(self, key):
        self._validate_full_key(key)
        result = self._mapping.get(key)
        if result is None:
            _fail()
        return result
    def contains_key(self, key):
        physical = self._key(key)
        return self.native.contains_key(key) or self.native.contains_key(physical) or self.native.contains_key(key + '.gz')
    def _sidecar(self):
        raw = canonical(self.storage_declaration)
        encoded = encode_gzip(raw, maximum=MAX_METADATA)
        key = self._validate_full_key(self.prefix + 'storage_json.gz')
        self._collision_sweep()
        if self.native.save_bytes(key, encoded) is not True:
            _fail()
        if decode_gzip(self.native.read_bytes(key), plain_bytes=len(raw), plain_sha256=sha256(raw), maximum=MAX_METADATA) != raw:
            _fail()
'''


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("actual credential/API/private/subprocess forbidden")
    monkeypatch.setattr(m.ops, "credential", denied)
    monkeypatch.setattr(m.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(m.subprocess, "run", denied)
    monkeypatch.setattr(m, "NOTEBOOK_SHA256", m._sha(NOTEBOOK.encode()))
    original = m.files._directory
    def safe(path, *, private):
        if private and path.is_relative_to(m.LANE): denied()
        return original(path, private=private)
    monkeypatch.setattr(m.files, "_directory", safe)


def publish(root, name, raw):
    directory = m.files._directory(root, private=True)
    try: c._publish(directory, name, raw)
    finally: os.close(directory)


def fixture(tmp_path, action="source-inspect", *, source_mutate=None, diff_mutate=None):
    root = tmp_path / "synthetic-mia-evidence"; root.mkdir(mode=0o700)
    now = datetime.now(timezone.utc)
    post_op = "TPR-EXT26-MIA-SOURCE-POST-SYNTHETIC-003"
    before = {**FROZEN["files"], "research.ipynb": NOTEBOOK}
    source = {**before, m.REPAIR: REPAIR}
    source["main.py"] = source["main.py"].replace(
        "from extended_compressed_store import CompressedInputStore, CompressedAuditStore",
        "from extended_compressed_store import CompressedInputStore\nfrom audit_key_recovery import AuditKeyRecoveryStore as CompressedAuditStore")
    if source_mutate: source_mutate(source)
    changes, delta_raw = c._diff(before, source)
    if diff_mutate:
        delta = e.parse_json(delta_raw); diff_mutate(delta); delta_raw = e.canonical(delta)
    archive_raw = c._archive(post_op, 2, source)
    archive_desc = {"name": post_op + ".read2.sources.json", "bytes": len(archive_raw), "sha256": m._sha(archive_raw)}
    diff_desc = {"name": post_op + ".diff.json", "bytes": len(delta_raw), "sha256": m._sha(delta_raw)}
    receipt = {"schema": "tpr-ext26-mia-source-receipt-v1", "operation_id": post_op,
        "action": "post-mia-source", "status": "COMPLETED", "stable_source_inventory": True, "scope_spent": True,
        "project_id": m.PROJECT, "candidate_id": m.CANDIDATE,
        "source_hashes": {name: m._sha(SOURCES[name]) for name in c.SOURCE_PATHS},
        "complete_private_diff": diff_desc, "ended_utc": (now - timedelta(seconds=2)).isoformat(),
        "inventory": c._public_inventory(c._inventory(source)), "source_archives": [{"name": "synthetic1"}, archive_desc], "changes": changes}
    receipt_raw = e.canonical(receipt)
    post = {"operation_id": post_op, "receipt_bytes": len(receipt_raw), "receipt_sha256": m._sha(receipt_raw),
        "sources_bytes": len(archive_raw), "sources_sha256": m._sha(archive_raw), "diff_bytes": len(delta_raw), "diff_sha256": m._sha(delta_raw)}
    for suffix, raw in ((".result.json", receipt_raw), (".read2.sources.json", archive_raw), (".diff.json", delta_raw)):
        publish(root, post_op + suffix, raw)
    mia, ledger = None, None
    if action != "source-inspect":
        mia = {"actor": m.ACTOR, "operation_id": "TPR-EXT26-MIA-RECOVERY-SYNTHETIC-001", "compile_id": "synthetic-mia-compile",
            "backtest_id": "synthetic-mia-job", "source_hashes": {name: m._sha(text.encode()) for name, text in source.items()},
            "source_post_operation": post_op, "source_post_receipt_sha256": post["receipt_sha256"],
            "baseline_operation": "TPR-EXT26-MIA-SOURCE-BASELINE-SYNTHETIC-003", "baseline_receipt_sha256": "d" * 64,
            "legacy_attempt": 3, "codex_attempts_consumed": 3, "observed_looks_before": 19, "look_ordinal": 20, "mia_look_sha256": "e" * 64}
        raw = e.canonical({"schema": "tpr-ext26-mia-ui-ledger-v1", "project_id": m.PROJECT, "candidate_id": m.CANDIDATE,
            "mia": mia, "launch_via_mia": True, "compiled_source_proven": False})
        publish(root, mia["operation_id"] + ".ui-ledger.json", raw)
        ledger = {"bytes": len(raw), "sha256": m._sha(raw)}
    plan = m._plan(action=action, operation_id="TPR-EXT26-MIA-RESULT-SYNTHETIC-001", git_head="a" * 40,
        source_hashes={name: m._sha(raw) for name, raw in SOURCES.items()}, owner_instruction_sha256="b" * 64,
        created_utc=(now - timedelta(seconds=1)).isoformat(), expires_utc=(now + timedelta(hours=2)).isoformat(),
        post_reference=post, mia=mia, ui_ledger=ledger, mode="offline-fixture")
    return plan, deepcopy(SOURCES), root, now


def transport(*, running=False, runtime_error=False, fault=None):
    calls = []
    def read(plan, endpoint, payload, seconds, claim):
        calls.append((endpoint, deepcopy(payload)))
        row = {"backtestId": plan["mia"]["backtest_id"], "projectId": m.PROJECT,
            "compileId": plan["mia"]["compile_id"], "completed": not running, "progress": 1,
            "status": "Running" if running else "Runtime Error" if runtime_error else "Completed",
            "error": "SYNTHETIC PRIVATE ERROR" if runtime_error else None}
        response = {"success": True, "projectId": m.PROJECT, "backtestId": plan["mia"]["backtest_id"]}
        if endpoint == "backtests/read": response["backtest"] = row
        elif endpoint == "backtests/read/log": response.update(logs=[], length=0)
        elif endpoint == "backtests/chart/read": response.update(status="loading")
        elif endpoint == "backtests/orders/read": response.update(orders=[], length=0)
        if fault: fault(response, len(calls))
        return e.canonical(response), 200, "SYNTHETIC-TOKEN"
    return read, calls


def execute(values, reading=None, **kwargs):
    plan, sources, root, now = values
    if reading is None:
        def reading(*_args): raise AssertionError("source inspection cannot touch transport")
    return e.parse_json(m.execute_fixture(plan, sources, root, clock=kwargs.pop("clock", lambda: now),
        transport=reading, **kwargs))


def test_exact_source_inspection_three_bodies_only_no_execution_or_other_source_disclosure(tmp_path):
    values = fixture(tmp_path); result = execute(values)
    assert result["status"] == "COMPLETED_CAPTURE" and result["private_read_attempts"].fraction() == 3
    assert result["source_inspection"]["permitted_repair_source"] == REPAIR
    assert result["source_inspection"]["complete_before_after_diff_verified"] is True
    assert result["source_inspection"]["general_secret_or_covert_data_absence_proven"] is False
    assert "CONFIG_JSON" not in e.canonical(result).decode() and not (values[2] / "controller.lock").exists()
    with pytest.raises(FileExistsError): execute(values)


@pytest.mark.parametrize("fault", ["writer", "notebook", "economics", "extra", "removed", "malicious", "bad_diff"])
def test_rebound_source_receipt_still_refuses_unapproved_changed_bodies(tmp_path, fault):
    def alter(source):
        if fault == "writer": source["extended_compressed_store.py"] += "# altered"
        if fault == "notebook": source["research.ipynb"] += " "
        if fault == "economics": source["main.py"] += "# economic change"
        if fault == "extra": source["unreviewed.py"] = "# not disclosed"
        if fault == "removed": del source["extended_core.py"]
        if fault == "malicious": source[m.REPAIR] += "import os\n"
    values = fixture(tmp_path, source_mutate=alter,
        diff_mutate=(lambda d: d.update(economics_accepted=True)) if fault == "bad_diff" else None)
    result = execute(values)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["source_inspection"] is None
    assert "permitted_repair_source" not in e.canonical(result).decode()
    assert (values[2] / (values[0]["operation_id"] + ".claim.spent.json")).exists()


@pytest.mark.parametrize("change", ["actor", "attempt", "look", "old_job", "foreign_post", "missing_source"])
def test_mia_scope_never_invents_fourth_attempt_or_relabels_old_jobs(tmp_path, change):
    values = fixture(tmp_path, "status"); plan = values[0]; mia = deepcopy(plan["mia"])
    if change == "actor": mia["actor"] = "generic-codex-agent"
    if change == "attempt": mia["legacy_attempt"] = 4
    if change == "look": mia["look_ordinal"] = 19
    if change == "old_job": mia["backtest_id"] = next(iter(m.PRIOR_JOBS))
    if change == "foreign_post": mia["source_post_operation"] = "other"
    if change == "missing_source": mia["source_hashes"].pop("extended_core.py")
    with pytest.raises(ValueError): m._mia(mia, plan["post_reference"])


def test_running_native_collection_stops_after_one_read_and_requires_fresh_later_scope(tmp_path):
    values = fixture(tmp_path, "collect-native"); read, calls = transport(running=True)
    result = execute(values, read)
    assert result["status"] == "NOT_TERMINAL" and len(calls) == 1 and result["native_census"] is None
    assert result["new_codex_attempts"].fraction() == result["new_looks"].fraction() == 0
    with pytest.raises(FileExistsError): execute(values, read)
    assert len(calls) == 1


@pytest.mark.parametrize("error", [False, True])
def test_terminal_collection_zero_orders_loading_missing_audit_stays_honest_diagnostic(tmp_path, error):
    values = fixture(tmp_path, "collect-native"); read, calls = transport(runtime_error=error)
    result = execute(values, read)
    assert result["status"] == "COMPLETED_CAPTURE" and len(calls) == 6
    census = result["native_census"]
    assert census["order_count"].fraction() == 0 and census["validated_compact_aggregates"] is False
    assert census["account_nav"]["classification"] == "diagnostic_loading_chart"
    assert result["accepted_metrics"] is None and result["compiled_source_proven"] is False
    assert result["declared_gui_mia_provenance_verified"] is True and result["authenticated_api_request_scope"] is False
    assert "SYNTHETIC PRIVATE ERROR" not in e.canonical(result).decode()


@pytest.mark.parametrize("fault", ["wrong_job", "wrong_compile", "false_success", "credential_echo", "loading_orders"])
def test_native_bad_or_missing_identity_and_sensitive_bodies_remain_failed(tmp_path, fault):
    values = fixture(tmp_path, "collect-native" if fault == "loading_orders" else "status")
    def alter(response, number):
        if fault == "wrong_job": response["backtest"]["backtestId"] = "other-job"
        if fault == "wrong_compile": response["backtest"]["compileId"] = "other-compile"
        if fault == "false_success": response["success"] = False
        if fault == "credential_echo": response["private"] = "SYNTHETIC-TOKEN"
        if fault == "loading_orders" and number == 6: response.pop("orders")
    read, calls = transport(fault=alter); result = execute(values, read)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["accepted_metrics"] is None
    assert len(calls) == (6 if fault == "loading_orders" else 1)


def test_exclusive_claim_access_and_request_exist_before_transport(tmp_path):
    values = fixture(tmp_path, "status"); original, calls = transport()
    def read(*arguments):
        operation = values[0]["operation_id"]
        assert all((values[2] / (operation + suffix)).exists() for suffix in
            (".claim.spent.json", ".access.json", ".read001.request.spent.json"))
        return original(*arguments)
    result = execute(values, read)
    assert result["status"] == "COMPLETED_CAPTURE" and len(calls) == 1


def test_existing_controller_lock_retained_claim_spent_and_no_private_body(tmp_path):
    values = fixture(tmp_path); publish(values[2], "controller.lock", b"preserve")
    result = execute(values)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["private_read_bytes"].fraction() == 0
    assert (values[2] / "controller.lock").read_bytes() == b"preserve"


def test_expired_and_changed_source_refuse_before_claim_or_private_body(tmp_path):
    values = fixture(tmp_path)
    with pytest.raises(ValueError): execute(values, clock=lambda: values[3] + timedelta(hours=3))
    values[1][m.MODULE] += b"# changed"
    with pytest.raises(ValueError): execute(values)
    assert not (values[2] / (values[0]["operation_id"] + ".claim.spent.json")).exists()


@pytest.mark.parametrize("endpoint", ["compile/create", "backtests/create", "object/get", "object/set", "files/update", "projects/read", "live/create"])
def test_restricted_endpoint_refuses_before_credentials(tmp_path, endpoint):
    plan = fixture(tmp_path, "status")[0]
    with pytest.raises(ValueError): m._native_request(plan, endpoint, {"projectId": m.PROJECT}, 30, {"bytes": 1, "sha256": "a" * 64})


@pytest.mark.parametrize("fault", ["path", "transport", "guard", "clock"])
def test_production_never_accepts_fixture_injection(tmp_path, fault):
    values = fixture(tmp_path, "status"); plan = dict(values[0]); plan["mode"] = "production"
    root = values[2] if fault == "path" else m.PRIVATE_ROOT
    kwargs = {"guard": m._guard, "clock": m._now, "monotonic": m.time.monotonic, "transport": m._native_request}
    if fault == "transport": kwargs["transport"] = lambda *_: None
    if fault == "guard": kwargs["guard"] = lambda _: None
    if fault == "clock": kwargs["clock"] = lambda: values[3]
    with pytest.raises(ValueError): m._execute(plan, values[1], root, **kwargs)


def test_transport_failure_keeps_one_unknown_receipt_without_retry(tmp_path):
    values = fixture(tmp_path, "status"); calls = []
    def broken(*_args): calls.append(True); raise TimeoutError("private exception never printed")
    result = execute(values, broken)
    assert len(calls) == 1 and result["status"] == "FAILED_OR_UNCERTAIN"
    assert result["failed_response_bytes_unknown"] is True
    assert "private exception" not in e.canonical(result).decode()


def test_fixed_scope_has_no_launch_attempt_reset_or_old_controller_dependency():
    assert set(m.READ_LIMITS) == {"backtests/read", "backtests/read/log", "backtests/chart/read", "backtests/orders/read"}
    text = SOURCES[m.MODULE].decode()
    assert "extended_driver" not in text and "mia_recovery" not in text
    assert m.MAX_PAGES == 128 and m.PAGE_SIZE == 99 and m.MAX_TOTAL == 64 * 1024 * 1024


@pytest.mark.parametrize("fault", ["ledger_hash", "ledger_body", "archive_size", "archive_hash", "symlink", "expiry"])
def test_private_descriptor_custody_and_ledger_never_grant_effect_scope(tmp_path, fault):
    values = fixture(tmp_path, "status" if fault.startswith("ledger") else "source-inspect")
    plan, _, root, now = values
    if fault == "ledger_hash": plan["ui_ledger"]["sha256"] = "f" * 64
    elif fault == "ledger_body":
        name = plan["mia"]["operation_id"] + ".ui-ledger.json"
        raw = (root / name).read_bytes().replace(b'"launch_via_mia":true', b'"launch_via_mia":false')
        (root / name).write_bytes(raw)
        plan["ui_ledger"] = {"bytes": len(raw), "sha256": m._sha(raw)}
    elif fault == "archive_size": plan["post_reference"]["sources_bytes"] += 1
    elif fault == "archive_hash": plan["post_reference"]["sources_sha256"] = "f" * 64
    elif fault == "symlink":
        name = plan["post_reference"]["operation_id"] + ".read2.sources.json"
        (root / name).rename(root / "synthetic-preserved")
        (root / name).symlink_to(root / "synthetic-preserved")
    reading, calls = transport()
    if fault == "expiry":
        with pytest.raises(ValueError): execute(values, reading, clock=lambda: now + timedelta(hours=3))
    else:
        result = execute(values, reading)
        assert result["status"] == "FAILED_OR_UNCERTAIN"
    assert not calls


@pytest.mark.parametrize("fault", ["http", "oversized", "deadline", "foreign_project", "boolean_progress"])
def test_bounded_native_failure_retains_single_spent_read(tmp_path, fault):
    values = fixture(tmp_path, "status"); inner, calls = transport()
    elapsed = [0.0]
    def reading(*args):
        raw, status, token = inner(*args)
        if fault == "http": status = 503
        elif fault == "oversized": raw = b"x" * (m.READ_LIMITS["backtests/read"] + 1)
        elif fault == "deadline": elapsed[0] = 601
        else:
            body = e.parse_json(raw)
            if fault == "foreign_project": body["projectId"] = 999
            if fault == "boolean_progress": body["backtest"]["progress"] = True
            raw = e.canonical(body)
        return raw, status, token
    result = execute(values, reading, monotonic=lambda: elapsed[0])
    assert result["status"] == "FAILED_OR_UNCERTAIN" and len(calls) == 1
    assert result["accepted_metrics"] is None


@pytest.mark.parametrize("source", [
    REPAIR.replace("def _key", "def on_data"), REPAIR.replace("ValueError(", "open("),
    REPAIR + "SECRET = 'not admissible'\n", REPAIR.replace("super()._key(key)", "self.native.delete(key)"),
    REPAIR.replace("super()._key(key)", "self.other.delete(key)"),
])
def test_source_disclosure_method_and_call_closure_refuses_unapproved_code(source):
    with pytest.raises(ValueError): m._repair_source(source)


def test_native_direct_signer_refuses_missing_claim_before_real_credentials(tmp_path):
    plan = fixture(tmp_path, "status")[0]
    plan["mode"] = "production"
    with pytest.raises(ValueError): m._native_request(plan, "backtests/read",
        {"projectId": m.PROJECT, "backtestId": plan["mia"]["backtest_id"]}, 30, None)


def test_all1449_exact_clock_nav_and_two99_order_pages_observed_not_accepted(tmp_path):
    values = fixture(tmp_path, "collect-native"); original, calls = transport()
    sessions = e.parse_json(SOURCES[c.PREFIX + "extended_calendar.json"])["valuation_sessions"]
    def read(plan, endpoint, payload, seconds, claim):
        wire, status, token = original(plan, endpoint, payload, seconds, claim)
        response = e.parse_json(wire)
        if endpoint == "backtests/chart/read" and payload["name"] == "EXT26 Account NAV":
            points = []
            for day in sessions:
                instant = datetime.fromisoformat(day + "T16:01:00").replace(tzinfo=m.ops.NY)
                points.append([int(instant.timestamp()), e.JsonNumber("100000.00000000000000001")])
            response.pop("status")
            response["chart"] = {"name": "EXT26 Account NAV", "series": {"NAV": {
                "name": "NAV", "unit": "$", "seriesType": 0, "values": points}}}
        if endpoint == "backtests/orders/read":
            response["length"] = 100
            response["orders"] = [{"id": index + 1, "status": 5, "quantity": 10,
                "time": "2021-01-04T14:30:00Z", "price": 0, "priceCurrency": "", "events": []}
                for index in range(payload["start"], min(100, payload["end"]))]
        return e.canonical(response), status, token
    result = execute(values, read)
    assert result["status"] == "COMPLETED_CAPTURE" and len(calls) == 7
    census = result["native_census"]
    assert census["account_nav"]["observations"].fraction() == 1449
    assert census["account_nav"]["complete_daily_account_nav"] is True
    assert census["order_count"].fraction() == 100 and census["order_pages"].fraction() == 2
    assert census["orders_missing_fill_observations"].fraction() == 100
    assert census["orders_missing_fee_observations"].fraction() == 100 and census["cost_values"] is None
    assert result["accepted_metrics"] is None and result["strategy_accepted"] is False


@pytest.mark.parametrize("change", ["cap", "duplicate", "changed_length", "partial"])
def test_order_pagination_caps_and_completeness_cannot_be_relabelled(tmp_path, change):
    values = fixture(tmp_path, "collect-native"); original, calls = transport()
    def read(plan, endpoint, payload, seconds, claim):
        raw, status, token = original(plan, endpoint, payload, seconds, claim)
        body = e.parse_json(raw)
        if endpoint == "backtests/orders/read":
            if change == "changed_length":
                body["length"] = 100 if payload["start"] == 0 else 101
                body["orders"] = [{"id": number + 1} for number in range(payload["start"], min(100, payload["end"]))]
                return e.canonical(body), status, token
            body["length"] = m.MAX_PAGES * m.PAGE_SIZE + 1 if change == "cap" else 2
            body["orders"] = [{"id": 1}, {"id": 1 if change == "duplicate" else 2}]
            if change == "partial": body["orders"].pop()
        return e.canonical(body), status, token
    result = execute(values, read)
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["accepted_metrics"] is None
    assert len(calls) == (7 if change == "changed_length" else 6)


@pytest.mark.parametrize("style", ["exported_class", "export_alias", "numeric_path_checks"])
def test_narrow_base_alias_export_and_standard_path_validation_source_admitted(style):
    source = REPAIR
    if style == "exported_class":
        source = source.replace("import CompressedAuditStore", "import CompressedAuditStore as _Base")
        source = source.replace("class AuditKeyRecoveryStore(CompressedAuditStore)", "class CompressedAuditStore(_Base)")
    if style == "export_alias": source += "CompressedAuditStore = AuditKeyRecoveryStore\n"
    if style == "numeric_path_checks":
        source = "import re\n" + source.replace("return super()._key(key)", "match = re.fullmatch(r'([0-9]+)', key)\n        if match is not None and int(match.group(1)) < 1024 and key.count('/') <= 100:\n            return super()._key(key)")
    assert m._repair_source(source) == source


@pytest.mark.parametrize("export", [False, True])
def test_main_import_cannot_accidentally_import_the_unchanged_base_writer(tmp_path, export):
    def alter(source):
        source["main.py"] = source["main.py"].replace("AuditKeyRecoveryStore as CompressedAuditStore", "CompressedAuditStore")
        source[m.REPAIR] = "_MAX_CHUNKS = 1024\n" + source[m.REPAIR]
        if export: source[m.REPAIR] += "CompressedAuditStore = AuditKeyRecoveryStore\n"
    result = execute(fixture(tmp_path, source_mutate=alter))
    assert result["status"] == ("COMPLETED_CAPTURE" if export else "FAILED_OR_UNCERTAIN")


def test_realistic_bounded_mia_source_disclosure_and_import_delta_without_execution(tmp_path):
    assert m._repair_source(MIA_LIKE) == MIA_LIKE
    def alter(source):
        source[m.REPAIR] = MIA_LIKE
        source["main.py"] = source["main.py"].replace("AuditKeyRecoveryStore as CompressedAuditStore", "CompressedAuditStore")
    result = execute(fixture(tmp_path, source_mutate=alter))
    assert result["status"] == "COMPLETED_CAPTURE"
    assert result["source_inspection"]["permitted_repair_source"] == MIA_LIKE
    assert result["source_inspection"]["source_executed"] is False
    assert result["source_inspection"]["economics_accepted"] is False


@pytest.mark.parametrize("fault", ["constant_call", "huge_constant", "rows", "regex_call", "future_import",
                                  "native_get", "native_delete", "native_account", "economic_method", "duplicate_constant"])
def test_realistic_mia_grammar_stays_closed_against_injection(fault):
    source = MIA_LIKE
    if fault == "constant_call": source = source.replace("_MAX_CHUNKS = 1024", "_MAX_CHUNKS = open('private')")
    if fault == "huge_constant": source = source.replace("_MAX_CHUNKS = 1024", "_MAX_CHUNKS = 999999999999")
    if fault == "rows": source = source.replace("_MAX_CHUNKS = 1024", "_ROWS = [{'licensed': 1}]")
    if fault == "regex_call": source = source.replace("re.compile(r", "other.compile(r")
    if fault == "future_import": source = source.replace("__future__ import annotations", "__future__ import division")
    if fault in {"native_get", "native_delete", "native_account"}:
        method = {"native_get": "get", "native_delete": "delete", "native_account": "read_account"}[fault]
        source = source.replace("self.native.contains_key(key)", "self.native." + method + "(key)")
    if fault == "economic_method": source = source.replace("def _collision_sweep", "def on_data")
    if fault == "duplicate_constant": source = source.replace("_MAX_CHUNKS = 1024", "_MAX_CHUNKS = 1024\n_MAX_CHUNKS = 2")
    with pytest.raises(ValueError): m._repair_source(source)


@pytest.mark.parametrize("job", ["34e0636f373c5ed9ee97387335b52454", "f79d3ff02644ec81f20da5cc6ca7440a", "d7c76b7c4936c814f125a2b9a8cc2896"])
def test_all_three_original_off_jobs_cannot_be_relabelled_mia(tmp_path, job):
    values = fixture(tmp_path, "status"); plan = values[0]; mia = deepcopy(plan["mia"])
    mia["backtest_id"] = job
    with pytest.raises(ValueError): m._mia(mia, plan["post_reference"])


def test_aggregate_reserves_full_fixed_response_bound_before_next_transport(tmp_path, monkeypatch):
    # Smaller synthetic budget exercises a nonzero already-received frontier:
    # terminal plus two logs fit; the next fixed 2MiB chart allowance does not.
    monkeypatch.setattr(m, "MAX_TOTAL", 2 * 1024 * 1024 + 1)
    values = fixture(tmp_path, "collect-native"); read, calls = transport()
    result = execute(values, read)
    assert result["status"] == "FAILED_OR_UNCERTAIN"
    assert len(calls) == 3 and result["request_attempts"].fraction() == 3
    assert result["received_bytes"].fraction() < values[0]["max_received_bytes"]
    assert result["failed_response_bytes_unknown"] is False
    assert not list(values[2].glob(values[0]["operation_id"] + ".read004.*"))


@pytest.mark.parametrize("action", ["source-inspect", "status", "collect-native"])
def test_parsed_cli_plan_nested_exact_numbers_normalize_before_private_effects(tmp_path, action):
    values = list(fixture(tmp_path, action))
    parsed = e.parse_json(e.canonical(values[0]))
    # Mirror only the top-level/actor conversions performed by the CLI. Private
    # source and UI-ledger descriptors intentionally still carry JsonNumbers.
    for key in ("legacy_attempt", "codex_attempts_consumed", "observed_looks_before", "look_ordinal"):
        if parsed.get("mia"): parsed["mia"][key] = c._integer(parsed["mia"][key], 20)
    for key in ("max_seconds", "max_received_bytes", "request_seconds", "max_order_pages", "new_codex_attempts", "new_looks"):
        parsed[key] = c._integer(parsed[key], m.MAX_TOTAL)
    assert type(parsed["post_reference"]["receipt_bytes"]) is e.JsonNumber
    if action != "source-inspect": assert type(parsed["ui_ledger"]["bytes"]) is e.JsonNumber
    values[0] = parsed
    reading, calls = transport()
    result = execute(values, reading if action != "source-inspect" else None)
    assert result["status"] == "COMPLETED_CAPTURE"
    assert result["plan_sha256"] == m._sha(e.canonical(parsed))
    assert result["private_read_attempts"].fraction() == (3 if action == "source-inspect" else 1)
    assert result["private_read_bytes"].fraction() > 0
    assert len(calls) == (0 if action == "source-inspect" else 1 if action == "status" else 6)
    with pytest.raises(FileExistsError): execute(values, reading if action != "source-inspect" else None)
    assert len(calls) == (0 if action == "source-inspect" else 1 if action == "status" else 6)


@pytest.mark.parametrize("change", ["bounds", "extra"])
def test_rebuilt_plan_normalization_does_not_accept_canonical_scope_drift(tmp_path, change):
    values = list(fixture(tmp_path))
    values[0] = e.parse_json(e.canonical(values[0]))
    if change == "bounds": values[0]["max_order_pages"] = e.JsonNumber("129")
    else: values[0]["extra_authority"] = True
    with pytest.raises(ValueError): execute(values)
    assert not (values[2] / (values[0]["operation_id"] + ".claim.spent.json")).exists()


@pytest.mark.parametrize("action", ["source-inspect", "status", "collect-native"])
def test_actual_cli_parser_normalizes_via_fixture_only_runtime_boundary(tmp_path, monkeypatch, capsys, action):
    values = fixture(tmp_path, action); original_raw = e.canonical(values[0])
    reading, calls = transport(); supplied = []
    def safe_execute(plan):
        assert plan["mode"] == "offline-fixture"
        assert type(plan["post_reference"]["receipt_bytes"]) is e.JsonNumber
        if action != "source-inspect": assert type(plan["ui_ledger"]["bytes"]) is e.JsonNumber
        supplied.append(plan)
        return m.execute_fixture(plan, values[1], values[2], clock=lambda: values[3],
            transport=reading if action != "source-inspect" else lambda *_: pytest.fail("source inspection cannot call transport"))
    monkeypatch.setattr(m, "execute_plan", safe_execute)
    code = m.main(["--plan-json", original_raw.decode(), "--plan-sha256", m._sha(original_raw)])
    assert code == 0 and len(supplied) == 1
    result = e.parse_json(capsys.readouterr().out.encode())
    assert result["status"] == "COMPLETED_CAPTURE" and result["plan_sha256"] == m._sha(original_raw)
    assert len(calls) == (0 if action == "source-inspect" else 1 if action == "status" else 6)


# TPR-CR26 regressions: a status defect and three guards the received suite
# never exercised. Each is red when the named line is removed or restored.


def test_not_terminal_status_does_not_survive_a_failed_final_check(tmp_path):
    """TPR-CR26-001: a refusal at the final check after a running-job read is FAILED_OR_UNCERTAIN, not NOT_TERMINAL."""
    (tmp_path / "first").mkdir(); (tmp_path / "second").mkdir()
    counted = []
    values = fixture(tmp_path / "first", "collect-native"); read, calls = transport(running=True)
    happy = execute(values, read, guard=lambda _: counted.append(1))
    assert happy["status"] == "NOT_TERMINAL" and len(calls) == 1
    final_check = len(counted)  # the last guard call is the final check after NOT_TERMINAL is set
    seen = []
    def refuse_at_final_check(_head):
        seen.append(1)
        if len(seen) == final_check: raise ValueError("synthetic refusal at the final check")
    plan, sources, root, now = fixture(tmp_path / "second", "collect-native"); read, calls = transport(running=True)
    result = execute((plan, sources, root, now), read, guard=refuse_at_final_check)
    assert len(calls) == 1 and len(seen) == final_check
    assert result["status"] == "FAILED_OR_UNCERTAIN" and result["native_census"] is None
    assert result["new_looks"].fraction() == 0 and (root / (plan["operation_id"] + ".result.json")).exists()


@pytest.mark.parametrize("seam", ["lane_root", "private_root"])
def test_fixture_mode_refuses_lane_or_private_roots_before_any_directory_open(tmp_path, seam):
    """Fixture execution can never be pointed at the lane tree or the private root."""
    plan, sources, _root, now = fixture(tmp_path, "status"); read, calls = transport()
    root = m.PRIVATE_ROOT if seam == "private_root" else m.LANE / "artifacts" / "synthetic-never-created"
    with pytest.raises(ValueError):
        m.execute_fixture(plan, sources, root, clock=lambda: now, transport=read)
    assert not calls and not root.exists() if seam == "lane_root" else not calls


@pytest.mark.parametrize("offset", ["naive", "plus_five"])
def test_fixture_clock_must_be_an_aware_utc_datetime(tmp_path, offset):
    """The clock seam is checked for type and zero UTC offset before the claim is spent."""
    plan, sources, root, now = fixture(tmp_path, "status"); read, calls = transport()
    bad = now.replace(tzinfo=None) if offset == "naive" else now.astimezone(timezone(timedelta(hours=5)))
    with pytest.raises(ValueError):
        execute((plan, sources, root, now), read, clock=lambda: bad)
    assert not calls and not (root / (plan["operation_id"] + ".claim.spent.json")).exists()


def test_terminal_error_status_without_error_text_is_refused(tmp_path):
    """A Runtime Error terminal that carries no error text is not a usable terminal."""
    def strip(response, _count):
        if "backtest" in response: response["backtest"]["error"] = None
    values = fixture(tmp_path, "status"); read, calls = transport(runtime_error=True, fault=strip)
    result = execute(values, read)
    assert len(calls) == 1 and result["status"] == "FAILED_OR_UNCERTAIN" and result["terminal"] is None
