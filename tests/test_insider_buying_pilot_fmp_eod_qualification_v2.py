"""Invented v2 source bindings and callbacks; no actual data/account access."""
from copy import deepcopy
import base64
import json
from pathlib import Path

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX custody qualification")
from research import insider_buying_pilot_fmp_eod_qualification_v2 as m
from research import insider_buying_pilot_fmp_eod_qualification_v1 as old
from research import insider_buying_pilot_stable_custody_v2 as stable


SECRET = "INVENTED-V2-KEY+_DO-NOT-RETAIN"
STORAGE_SHA = "4" * 64
IDENTITY = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": "1" * 40,
    "clean": True, "source_sha256": {}, "source_inventory_sha256": m._sha(b"{}")}


def _case(case_id="recent01", day="2023-02-06", cik="0000001234", ordinal=1):
    return {"case_id": case_id, "cik": cik, "accession": f"000000123423{ordinal:06d}",
        "form_type": "4", "filing_date": day,
        "acceptance_digits": day.replace("-", "") + "160102",
        "source_symbol": "INVENTED-CONTROL-SYMBOL", "body_sha256": "a" * 64}


def _cases():
    return [_case("warm01", "2020-10-02", "0000009876", 3), _case(),
        _case("recent02", ordinal=2)]


def _binding_value(context, cases):
    return {"schema": m.SCHEMA + "/input-bindings", "code_identity": deepcopy(IDENTITY),
        "storage_qualification_sha256": STORAGE_SHA,
        "storage_receipt_copy_sha256": context.pins["storage-qualification.json"]["sha256"],
        "snapshot_sha256": context.pins["failed-predecessor-snapshot.json"]["sha256"],
        "control_evidence_sha256": context.pins["controls.json"]["sha256"],
        "control_sha256": m._sha(m._raw(cases)), "fixture_only": True}


def _context(tmp_path, cases=None, *, binding_fault=None, registration_fault=None):
    cases = _cases() if cases is None else cases
    root = tmp_path / "invented-private-data"; root.mkdir(mode=0o700)
    registration = m.registration(STORAGE_SHA)
    if registration_fault:
        key, value = {"purpose": ("purpose", "storage_qualification"), "audit_id": ("audit_id", "different-audit"),
            "storage_receipt_sha256": ("storage_receipt_sha256", "5" * 64),
            "attempt_boolean": ("maximum_attempts_per_request", True),
            "fresh_numeric": ("fresh_operation_not_continuation", 1)}[registration_fault]
        registration[key] = value
    context = stable.Epoch(IDENTITY, registration, fixture=True, fixture_root=root, checker=lambda: None)
    context.publish("storage-qualification.json", {"fixture_only": True, "marker": "invented-storage-proof",
        "storage_identity": context.storage_identity})
    context.publish("failed-predecessor-snapshot.json", {"fixture_only": True,
        "previous_operations_successful": False, "candidate_controls_promoted": False,
        "provider_request_journals_present": False})
    context.publish("controls.json", {"fixture_only": True, "cases": deepcopy(cases)})
    if binding_fault:
        value = _binding_value(context, cases)
        if binding_fault == "fixture_numeric": value["fixture_only"] = 1
        elif binding_fault == "fixture_only": value[binding_fault] = False
        elif binding_fault == "code_identity": value[binding_fault]["head"] = "2" * 40
        elif binding_fault == "schema": value[binding_fault] = "foreign/input-bindings"
        else: value[binding_fault] = "6" * 64
        context.publish("input-bindings.json", value)
    else:
        m._bind_inputs(context, cases, IDENTITY, STORAGE_SHA)
    return context, cases


def _credential(provider):
    return m.KeychainCredential(provider, SECRET, fixture_only=True)


def _body(item):
    return m._raw({"data": [], "meta": {"total": 0, "limit": 100, "offset": 0},
        "links": {"next": None}}) if item["provider"] == "eodhd" else b"[]"


def _project(raw, cases, item, credential):
    old._screen(raw, credential)
    return old._project(raw, cases, item)


def _drive(context, cases, monkeypatch, *, response=None, reader=None, project=_project, clock_step=None):
    calls, reads, sleeps = [], [], []
    clock = [0]
    def ticks():
        result = clock[0]
        clock[0] += 2 * m.SPACING_NS if clock_step is None else clock_step
        return result
    monkeypatch.setattr(m.time, "monotonic_ns", ticks)
    monkeypatch.setattr(m.time, "sleep", lambda seconds: sleeps.append(seconds))
    def credentials(provider):
        reads.append(provider)
        assert context.read(provider + "-credential-started.json")["maximum_reads"] == 1
        assert context.read("request-plan.json")["bindings_sha256"] == context.pins["input-bindings.json"]["sha256"]
        return _credential(provider) if reader is None else reader(provider)
    def transport(item, credential):
        assert context.fixture is True and context.is_actual() is False
        assert context.active is not None and credential.fixture_only is True
        assert m._binding(context, item, credential)["fixture_only"] is True
        start = context.read(context.active)
        assert start["maximum_attempts"] == 1
        assert start["input_bindings_sha256"] == context.pins["input-bindings.json"]["sha256"]
        assert start["request_plan_sha256"] == context.pins["request-plan.json"]["sha256"]
        calls.append(deepcopy(item))
        return m._Reply(200, _body(item)) if response is None else response(item, credential, len(calls))
    result = m._drive(context, cases, IDENTITY, fixture=True, credential_reader=credentials,
        transport=transport, project=project)
    return result, calls, reads, sleeps


def _plan(context, cases, *, fault=None):
    plan = {"schema": m.SCHEMA + "/plan", "requests": m.build_requests(cases),
        "control_sha256": m._sha(m._raw(cases)), "fixture_only": True,
        "registration": m.registration(STORAGE_SHA),
        "bindings_sha256": context.pins["input-bindings.json"]["sha256"]}
    if fault == "registration": plan["registration"]["purpose"] = "storage_qualification"
    elif fault == "registration_numeric": plan["registration"]["maximum_attempts_per_request"] = True
    elif fault == "requests": plan["requests"] = plan["requests"][1:]
    elif fault == "fixture_only": plan["fixture_only"] = False
    elif fault == "fixture_numeric": plan["fixture_only"] = 1
    elif fault: plan[fault] = "7" * 64
    context.publish("request-plan.json", plan)
    return plan


def _started(context, plan, *, fault=None):
    item = plan["requests"][0]
    value = {"schema": m.SCHEMA + "/request-started", "request_index": 0,
        "fingerprint": item["fingerprint"], "maximum_attempts": 1,
        "request_plan_sha256": context.pins["request-plan.json"]["sha256"],
        "input_bindings_sha256": context.pins["input-bindings.json"]["sha256"],
        "started_utc": "2026-11-03T00:00:00.000000Z"}
    if fault == "request_index": value[fault] = True
    elif fault == "maximum_attempts": value[fault] = 2
    elif fault == "attempt_boolean": value["maximum_attempts"] = True
    elif fault: value[fault] = "8" * 64
    context.publish("request-000-started.json", value)
    context.active = "request-000-started.json"
    return item


def test_registration_freezes_existing_plan_bounds_and_no_readiness_promotion():
    value = m.registration(STORAGE_SHA)
    assert value["purpose"] == "provider_control_qualification" and value["audit_id"] == m.AUDIT_ID
    assert value["storage_receipt_sha256"] == STORAGE_SHA and value["storage_probe_id"] == m.PROBE_ID
    assert value["maximum_controls"] == 12 and value["maximum_unique_requests"] == 36
    assert value["maximum_attempts_per_request"] == value["credential_reads_per_provider"] == 1
    assert value["rows_per_request"] == 100 and value["maximum_response_bytes"] == 128 * 1024
    assert value["http_open_read_seconds"] == 15 and value["http_close_seconds"] == 1
    assert value["required_filing_window"] == ["2020-10-01", "2025-12-31"]
    assert value["raw_or_normalized_provider_rows_retained"] is False
    assert value["redirect_retry_paging_fallback_or_resume_permitted"] is False
    assert value["fresh_operation_not_continuation"] is value["prior_provider_use_must_be_zero"] is True
    assert value["authority"] == m.authority() and not any(m.authority().values())
    probe = m.probe_registration()
    assert probe["purpose"] == "storage_qualification" and probe["minimum_observed_seconds"] >= 70
    assert probe["minimum_post_publication_seconds"] >= 70
    assert probe["synthetic_only"] is True and probe["provider_invocations"] == probe["credential_reads"] == 0


@pytest.mark.parametrize("sha", (None, True, "bad", "A" * 64, "0" * 63, "0" * 65))
def test_registration_refuses_unbound_external_storage_receipt(sha):
    with pytest.raises(m.QualificationError, match="storage_unqualified"): m.registration(sha)


def test_all_clean_empty_responses_complete_capability_accounting_without_coverage_authority(tmp_path, monkeypatch):
    context, cases = _context(tmp_path)
    try:
        result, calls, reads, sleeps = _drive(context, cases, monkeypatch)
        assert result["schema"] == m.SCHEMA + "/complete" and result["fixture_only"] is True
        assert result["planned_requests"] == result["transport_invocation_count"] == len(calls) == 6
        assert result["unattempted_requests"] == 0
        assert len({v["fingerprint"] for v in calls}) == 6 and reads == ["fmp", "eodhd"]
        assert result["credential_read_attempts"] == result["credential_reads_observed"] == 2
        assert result["projected_responses"] == result["scoped_responses"] == result["clean_scoped_responses"] == 6
        assert not sleeps and result["authority"] == m.authority()
        assert result["remote_request_count_measured"] is result["raw_response_retained"] is False
        assert all(v["projection"]["authority"] == m.authority() for v in result["receipts"])
        encoded = m._raw(result)
        assert SECRET.encode() not in encoded and b"INVENTED-CONTROL-SYMBOL" not in encoded
        assert all(v["projection"]["response_body_retained"] is False for v in result["receipts"])
        summary = m.public_summary(result)
        assert "receipts" not in summary and "authority" in summary
        before = len(calls)
        with pytest.raises(stable.CustodyError):
            _drive(context, cases, monkeypatch)
        assert len(calls) == before
    finally: context.close()


@pytest.mark.parametrize("fault", ("schema", "code_identity", "storage_qualification_sha256",
    "storage_receipt_copy_sha256", "snapshot_sha256", "control_evidence_sha256", "control_sha256", "fixture_only"))
def test_coherent_but_wrong_input_bindings_refuse_before_any_credential_or_transport(tmp_path, monkeypatch, fault):
    context, cases = _context(tmp_path, binding_fault=fault)
    try:
        with pytest.raises(m.QualificationError, match="source_bindings_required"):
            m._drive(context, cases, IDENTITY, fixture=True,
                credential_reader=lambda *_: pytest.fail("credential before source binding"),
                transport=lambda *_: pytest.fail("transport before source binding"),
                project=lambda *_: pytest.fail("projection before source binding"))
        assert "request-plan.json" not in context.pins
    finally: context.close()


@pytest.mark.parametrize("fault", ("purpose", "audit_id", "storage_receipt_sha256"))
def test_registration_identity_cannot_be_replaced_by_another_purpose_or_storage_proof(tmp_path, fault):
    context, cases = _context(tmp_path, registration_fault=fault)
    try:
        with pytest.raises(m.QualificationError, match="source_bindings_required"):
            m._validated_bindings(context, cases, IDENTITY)
    finally: context.close()


def test_caller_case_mutation_after_binding_refuses_without_rebinding(tmp_path):
    context, cases = _context(tmp_path)
    try:
        cases[0]["body_sha256"] = "b" * 64
        with pytest.raises(m.QualificationError, match="source_bindings_required"):
            m._validated_bindings(context, cases, IDENTITY)
        assert context.read("controls.json")["cases"][0]["body_sha256"] == "a" * 64
    finally: context.close()


@pytest.mark.parametrize("fault", ("binding_fixture", "plan_fixture", "plan_registration", "start_attempt", "registration_attempt", "registration_fresh"))
def test_json_boolean_number_aliases_cannot_change_frozen_binding_plan_or_attempt_types(tmp_path, fault):
    context, cases = _context(tmp_path,
        binding_fault="fixture_numeric" if fault == "binding_fixture" else None,
        registration_fault={"registration_attempt": "attempt_boolean", "registration_fresh": "fresh_numeric"}.get(fault))
    try:
        if fault in {"binding_fixture", "registration_attempt", "registration_fresh"}:
            with pytest.raises(m.QualificationError, match="source_bindings_required"):
                m._validated_bindings(context, cases, IDENTITY)
        else:
            plan = _plan(context, cases, fault={"plan_fixture": "fixture_numeric", "plan_registration": "registration_numeric"}.get(fault))
            item = _started(context, plan, fault="attempt_boolean" if fault == "start_attempt" else None)
            with pytest.raises(m.QualificationError, match="started_journal_required"):
                m._binding(context, item, _credential(item["provider"]))
    finally: context.close()


def test_pure_binding_accepts_genuine_fixture_journals_without_minting_live_permission(tmp_path):
    context, cases = _context(tmp_path)
    try:
        item = _started(context, _plan(context, cases))
        before = set(context.dispatched)
        assert m._binding(context, item, _credential(item["provider"])) == context.read("input-bindings.json")
        assert context.is_actual() is False and context.dispatched == before
    finally: context.close()


@pytest.mark.parametrize("fault", ("registration", "requests", "control_sha256", "bindings_sha256", "fixture_only"))
def test_pure_binding_rejects_coherently_published_wrong_plan(tmp_path, fault):
    context, cases = _context(tmp_path)
    try:
        expected_item = m.build_requests(cases)[0]
        _started(context, _plan(context, cases, fault=fault))
        with pytest.raises(m.QualificationError, match="started_journal_required"):
            m._binding(context, expected_item, _credential(expected_item["provider"]))
        assert not context.dispatched
    finally: context.close()


@pytest.mark.parametrize("fault", ("request_index", "fingerprint", "maximum_attempts", "request_plan_sha256", "input_bindings_sha256", "active", "already_dispatched"))
def test_pure_binding_rejects_wrong_start_or_previous_dispatch(tmp_path, fault):
    context, cases = _context(tmp_path)
    try:
        item = _started(context, _plan(context, cases), fault=None if fault in {"active", "already_dispatched"} else fault)
        if fault == "active": context.active = None
        if fault == "already_dispatched": context.dispatched.add(item["fingerprint"])
        with pytest.raises(m.QualificationError, match="started_journal_required"):
            m._binding(context, item, _credential(item["provider"]))
    finally: context.close()


@pytest.mark.parametrize("fault", ("wrong_type", "fixture", "wrong_credential_provider"))
def test_actual_transport_rejects_fixture_or_foreign_context_before_opener(tmp_path, monkeypatch, fault):
    context, cases = _context(tmp_path)
    try:
        item = m.build_requests(cases)[0]
        supplied = object() if fault == "wrong_type" else context
        credential = _credential("eodhd" if fault == "wrong_credential_provider" else "fmp")
        monkeypatch.setattr(m.request, "build_opener", lambda *_a, **_k: pytest.fail("opener for unqualified fixture"))
        with pytest.raises(m.QualificationError, match="started_journal_required"):
            m._transport(supplied, item, credential)
        assert context.is_actual() is False and not context.dispatched
    finally: context.close()


@pytest.mark.parametrize("status", (401, 429, 500, None))
def test_provider_wide_refusal_defers_remaining_provider_queries_without_retry(tmp_path, monkeypatch, status):
    context, cases = _context(tmp_path)
    def response(item, credential, ordinal):
        if item["provider"] == "fmp": return m._Reply(status, b"", "transport_error" if status is None else "http_refused")
        return m._Reply(200, _body(item))
    try:
        result, calls, reads, _ = _drive(context, cases, monkeypatch, response=response)
        assert [v["provider"] for v in calls] == ["fmp", "eodhd", "eodhd"]
        assert result["planned_requests"] == 6 and result["transport_invocation_count"] == 3
        assert result["unattempted_requests"] == 3 and reads == ["fmp", "eodhd"]
        assert len({v["fingerprint"] for v in calls}) == len(calls)
    finally: context.close()


@pytest.mark.parametrize("status", (402, 403, 404))
def test_family_refusal_does_not_guess_providerwide_expiry_or_retry_the_query(tmp_path, monkeypatch, status):
    context, cases = _context(tmp_path)
    def response(item, credential, ordinal):
        return m._Reply(status, b"", "http_refused") if item["family"] == "fmp_sec" else m._Reply(200, _body(item))
    try:
        result, calls, reads, _ = _drive(context, cases, monkeypatch, response=response)
        assert [v["family"] for v in calls] == ["fmp_sec", "fmp_insider", "fmp_insider", "eod_mapping", "eod_mapping"]
        assert result["transport_invocation_count"] == 5 and result["unattempted_requests"] == 1
        assert reads == ["fmp", "eodhd"] and len({v["fingerprint"] for v in calls}) == 5
        assert result["receipts"][0]["http_status"] == status and result["authority"] == m.authority()
    finally: context.close()


def test_failed_credential_is_counted_once_and_never_serialized(tmp_path, monkeypatch):
    context, cases = _context(tmp_path)
    def reader(provider):
        if provider == "fmp": raise RuntimeError(SECRET)
        return _credential(provider)
    try:
        result, calls, reads, _ = _drive(context, cases, monkeypatch, reader=reader)
        assert reads == ["fmp", "eodhd"] and all(v["provider"] == "eodhd" for v in calls)
        assert result["credential_read_attempts"] == 2 and result["credential_reads_observed"] == 1
        assert result["transport_invocation_count"] == 2 and result["unattempted_requests"] == 4
        assert SECRET.encode() not in m._raw(result)
    finally: context.close()


def test_credential_echo_refuses_before_body_hash_or_retention(tmp_path, monkeypatch):
    context, cases = _context(tmp_path)
    def response(item, credential, ordinal):
        return m._Reply(200, m._raw({"opaque": SECRET})) if item["family"] == "fmp_sec" else m._Reply(200, _body(item))
    try:
        result, calls, _, _ = _drive(context, cases, monkeypatch, response=response)
        refused = result["receipts"][0]
        assert refused["code"] == "projection_refused" and refused["projection"] is None
        assert refused["error_or_refused_body_hashed_or_retained"] is False
        assert SECRET.encode() not in m._raw(result)
        assert len(calls) == 5 and result["unattempted_requests"] == 1
    finally: context.close()


def test_nonzero_spacing_and_refused_projection_do_not_duplicate_a_query(tmp_path, monkeypatch):
    context, cases = _context(tmp_path)
    def projected(raw, relevant, item, credential):
        if item["family"] == "fmp_sec": raise old.ProviderQualificationError("projection_refused")
        return _project(raw, relevant, item, credential)
    try:
        result, calls, _, sleeps = _drive(context, cases, monkeypatch, project=projected, clock_step=0)
        assert sleeps and all(value == 1.0 for value in sleeps)
        assert result["unattempted_requests"] == 1 and len({v["fingerprint"] for v in calls}) == len(calls)
    finally: context.close()


@pytest.mark.parametrize("role", ("health", "metadata", "bodies", "project", "snapshot"))
def test_offline_policy_denies_new_private_store_and_native_network_fork_writes(role):
    policy = m._policy(role)
    assert '(deny network*)' in policy and '(deny process-fork)' in policy and '(deny file-write*)' in policy
    assert '(deny process-exec (literal "/usr/bin/security"))' in policy
    assert '(deny file-read* (subpath ' + json.dumps(str(stable.PRIVATE_CUSTODY_ROOT)) + '))' in policy


def test_snapshot_policy_allows_all_three_required_directory_literals_but_no_broad_old_audit_read():
    policy = m._policy("snapshot", stable.snapshot_paths())
    for folder in (stable.LEGACY_AUDIT, stable.LEGACY_SECOND, stable.LEGACY_THIRD):
        path = stable.LEGACY_ROOT / folder
        assert '(literal ' + json.dumps(str(path)) + ')' in policy
        assert '(subpath ' + json.dumps(str(path)) + ')' not in policy
    for path in stable.snapshot_paths():
        assert '(literal ' + json.dumps(str(path)) + ')' in policy
    assert '(deny file-write*)' in policy and '(deny process-fork)' in policy


def test_child_credentials_are_only_in_anonymous_input_and_detail_failure_survives(monkeypatch):
    observed = []
    detail = {"code": "output_changed", "artifact_role": "controls", "changed_fields": ["ctime"], "stage": "bodies"}
    def launch(command, payload, *, timeout):
        assert SECRET not in " ".join(command) and b"--api" not in payload
        assert "-I" in command and "-S" in command and "-B" in command
        assert timeout == 30 and SECRET.encode() in payload
        observed.append((command, payload))
        return {"passed": False, "failure": detail}
    monkeypatch.setattr(m.legacy.ipc, "_launch", launch)
    supplied = {"raw_base64": base64.b64encode(b"[]").decode(), "cases": [_case()],
        "item": m.build_requests([_case()])[0], "credential": {"provider": "fmp", "value": SECRET}}
    with pytest.raises(m.QualificationError) as caught: m._child("project", IDENTITY, supplied)
    assert caught.value.details == detail and len(observed) == 1
    assert m.failure_info(caught.value, "arguments")["stage"] == "bodies"


def test_failure_info_never_formats_foreign_exception_or_path():
    assert SECRET not in m._raw(m.failure_info(RuntimeError(SECRET), "unknown" )).decode()
    error = stable.CustodyError("output_changed", "controls", ("ctime", SECRET))
    assert m.failure_info(error, "control-bodies") == {"code": "output_changed", "artifact_role": "controls",
        "changed_fields": ["ctime"], "stage": "control-bodies"}


def test_run_failure_preserves_stage_and_custody_detail_even_without_failure_leaf(monkeypatch):
    events, receivers = [], []
    storage_identity = {"fixture_only": True, "device": 1, "inode": 2}
    class RefusingReceiver:
        def __init__(self): self.storage_identity = storage_identity
        def publish(self, name, value):
            events.append(name)
            if name == "controls-metadata-started.json":
                raise stable.CustodyError("output_changed", "source_metadata", ("ctime",))
            return m._sha(m._raw(value))
        def close(self): events.append("closed")
    def receiver(identity, registration):
        assert identity == IDENTITY and registration == m.registration(STORAGE_SHA)
        value = RefusingReceiver(); receivers.append(value); return value
    def child(role, identity, supplied=None, **kwargs):
        events.append("child-" + role)
        if role == "proof": return {"storage_identity": storage_identity}
        if role == "snapshot": return {"fixture_only": False, "invented_snapshot": True}
        pytest.fail("later source stage after custody refusal")
    monkeypatch.setattr(m, "_identity", lambda head: deepcopy(IDENTITY))
    monkeypatch.setattr(m.stable, "Epoch", receiver)
    monkeypatch.setattr(m.stable, "validate_snapshot", lambda value, *, fixture: None)
    monkeypatch.setattr(m, "_child", child)
    monkeypatch.setattr(m, "read_keychain_credential", lambda *_: pytest.fail("credential after custody refusal"))
    monkeypatch.setattr(m, "_drive", lambda *_a, **_k: pytest.fail("provider after custody refusal"))
    with pytest.raises(m.QualificationError) as caught:
        m.run_actual(IDENTITY["head"], STORAGE_SHA)
    assert m.failure_info(caught.value, "arguments") == {"code": "output_changed", "artifact_role": "source_metadata",
        "changed_fields": ["ctime"], "stage": "control-metadata"}
    assert events[-1] == "closed" and "failure.json" not in events
    assert m._ARMED.get(receivers[0]) is None


def test_controller_success_returns_external_complete_pin_and_revokes_arm_without_any_actual_access(monkeypatch):
    receivers, events = [], []
    storage_identity = {"controller_only": True, "device": 1, "inode": 2}
    cases = [_case(f"invented-{i:02d}", ordinal=i) for i in range(1, 13)]
    class DummyReceiver:
        """Not an Epoch and has no live receiver permission or filesystem."""
        fixture = False
        def __init__(self, identity, registration):
            self.identity, self.registration = deepcopy(identity), deepcopy(registration)
            self.storage_identity, self.closed = storage_identity, False
            self.records = {}
            reservation = m._raw({"controller_only": True})
            self.latch = {"bytes": len(reservation), "sha256": m._sha(reservation)}
            self.pins = {"reservation.json": self.latch.copy()}
        def publish(self, name, value):
            assert name not in self.records
            raw = m._raw(value); self.records[name] = deepcopy(value)
            self.pins[name] = {"bytes": len(raw), "sha256": m._sha(raw)}
            events.append(name)
            return self.pins[name]["sha256"]
        def read(self, name): return deepcopy(self.records[name])
        def check(self): events.append("checked")
        def close(self): self.closed = True; events.append("closed")
    def receiver(identity, registration):
        assert identity == IDENTITY and registration == m.registration(STORAGE_SHA)
        context = DummyReceiver(identity, registration); receivers.append(context); return context
    def child(role, identity, supplied=None, **kwargs):
        assert identity == IDENTITY
        if role == "proof": return {"storage_identity": storage_identity, "receipt_sha256": STORAGE_SHA}
        if role == "snapshot": return {"controller_only": True, "fixture_only": False}
        if role == "metadata": return {"controller_only": True}
        if role == "bodies": return {"cases": deepcopy(cases), "fixture_only": False,
            "warmup_full_readback_verified": True, "recent_selected_parent_count": 4}
        pytest.fail("unexpected native or provider operation")
    def no_api_drive(context, bound_cases, identity):
        assert bound_cases == cases and identity == IDENTITY
        assert m._ARMED.get(context) == context.pins["input-bindings.json"]["sha256"]
        assert m._validated_bindings(context, cases, identity)["code_identity"] == IDENTITY
        return {"schema": m.SCHEMA + "/complete", "fixture_only": False, "execution_head": identity["head"],
            "planned_requests": 0, "transport_invocation_count": 0, "unattempted_requests": 0,
            "credential_reads_observed": 0, "credential_read_attempts": 0, "projected_responses": 0,
            "scoped_responses": 0, "clean_scoped_responses": 0, "authority": m.authority(),
            "raw_response_retained": False, "remote_request_count_measured": False, "receipts": []}
    monkeypatch.setattr(m, "_identity", lambda head: deepcopy(IDENTITY))
    monkeypatch.setattr(m.stable, "Epoch", receiver)
    monkeypatch.setattr(m.stable, "validate_snapshot", lambda value, *, fixture: None)
    monkeypatch.setattr(m.stable, "snapshot_paths", lambda: ())
    monkeypatch.setattr(m.legacy.controls, "metadata_paths", lambda: ())
    monkeypatch.setattr(m.legacy.controls, "body_paths", lambda metadata: ())
    monkeypatch.setattr(m, "_child", child)
    monkeypatch.setattr(m, "_drive", no_api_drive)
    monkeypatch.setattr(m, "read_keychain_credential", lambda *_: pytest.fail("actual credential read"))
    monkeypatch.setattr(m, "_transport", lambda *_: pytest.fail("actual transport"))
    result = m.run_actual(IDENTITY["head"], STORAGE_SHA)
    context = receivers[0]
    expected_pin = m._sha(m._raw(context.records["complete.json"]))
    assert result["complete_receipt_sha256"] == expected_pin == context.pins["complete.json"]["sha256"]
    assert {k: v for k, v in result.items() if k != "complete_receipt_sha256"} == m.public_summary(context.records["complete.json"])
    assert "complete_receipt_sha256" not in m.public_summary(context.records["complete.json"])
    assert context.closed is True and m._ARMED.get(context) is None
    assert events[-3:] == ["complete.json", "checked", "closed"]


def _storage_readback(identity):
    storage_identity = {"schema": stable.SCHEMA + "/storage-identity", "root_kind": "fixed_user_application_support",
        "device": 1, "inode": 2, "owner": 1000, "group": 1000, "mode": 448}
    controls = {f"synthetic-{i:03d}.json": {"schema": m.SCHEMA + "/synthetic", "ordinal": i, "payload": "X" * 20800}
        for i in range(m.PROBE_FILES)}
    controls["reservation.json"] = {"fixture_only": False, "registration": m.probe_registration()}
    pins = {name: {"bytes": len(m._raw(value)), "sha256": m._sha(m._raw(value))} for name, value in controls.items()}
    receipt = {"schema": m.SCHEMA + "/storage-qualification", "audit_id": m.PROBE_ID,
        "purpose": "storage_qualification", "passed": True, "synthetic_only": True, "fixture_only": False,
        "execution_identity": deepcopy(identity), "registration": m.probe_registration(),
        "storage_identity": storage_identity, "post_publication_observed_seconds": m.PROBE_SECONDS + 1,
        "observed_seconds": m.PROBE_SECONDS + 1, "minimum_observed_seconds": m.PROBE_SECONDS,
        "synthetic_file_count": m.PROBE_FILES, "repeated_strict_checks": 5,
        "native_network_denied": True, "live_memory_guard": True, "source_data_reads": 0,
        "credential_reads": 0, "provider_invocations": 0, "authority": m.authority(),
        "published_leaf_pins": deepcopy(pins)}
    controls["complete.json"] = receipt
    pins["complete.json"] = {"bytes": len(m._raw(receipt)), "sha256": STORAGE_SHA}
    return {"controls": controls, "pins": pins, "storage_identity": storage_identity}


def test_bound_storage_proof_reads_only_fixed_ten_leaf_set_and_external_hash(monkeypatch):
    readback = _storage_readback(IDENTITY); calls = []
    def read(audit_id, names, pins, *, memory):
        calls.append((audit_id, names, pins, memory)); return deepcopy(readback)
    monkeypatch.setattr(m.stable, "read_epoch_controls", read)
    guard = object()
    result = m._proof(IDENTITY, {"sha256": STORAGE_SHA}, guard)
    assert result["passed"] is True and result["receipt_sha256"] == STORAGE_SHA
    assert result["authority"] == m.authority() and result["fixture_only"] is False
    assert calls == [(m.PROBE_ID, ["reservation.json", *(f"synthetic-{i:03d}.json" for i in range(8)), "complete.json"],
        {"complete.json": {"bytes": None, "sha256": STORAGE_SHA}}, guard)]


@pytest.mark.parametrize("fault", ("passed", "synthetic_only", "fixture_only", "head", "seconds", "count", "network", "memory", "provider", "rights", "pins", "body"))
def test_wrong_storage_evidence_cannot_authorize_new_provider_epoch(monkeypatch, fault):
    readback = _storage_readback(IDENTITY); receipt = readback["controls"]["complete.json"]
    if fault in {"passed", "synthetic_only"}: receipt[fault] = False
    if fault == "fixture_only": receipt[fault] = True
    if fault == "head": receipt["execution_identity"]["head"] = "2" * 40
    if fault == "seconds": receipt["observed_seconds"] = m.PROBE_SECONDS - 1
    if fault == "count": receipt["synthetic_file_count"] -= 1
    if fault == "network": receipt["native_network_denied"] = False
    if fault == "memory": receipt["live_memory_guard"] = False
    if fault == "provider": receipt["provider_invocations"] = 1
    if fault == "rights": receipt["authority"]["rights_verified"] = True
    if fault == "pins": receipt["published_leaf_pins"]["reservation.json"]["sha256"] = "8" * 64
    if fault == "body": readback["controls"]["synthetic-000.json"]["payload"] += "X"
    monkeypatch.setattr(m.stable, "read_epoch_controls", lambda *_a, **_k: deepcopy(readback))
    with pytest.raises(m.QualificationError, match="storage_unqualified"):
        m._proof(IDENTITY, {"sha256": STORAGE_SHA}, object())


@pytest.mark.parametrize("field,value", (("audit_id", "foreign-storage-probe"),
    ("purpose", "provider_control_qualification")))
def test_storage_receipt_top_level_identity_and_purpose_are_binding(monkeypatch, field, value):
    readback = _storage_readback(IDENTITY)
    readback["controls"]["complete.json"][field] = value
    monkeypatch.setattr(m.stable, "read_epoch_controls", lambda *_a, **_k: deepcopy(readback))
    with pytest.raises(m.QualificationError, match="storage_unqualified"):
        m._proof(IDENTITY, {"sha256": STORAGE_SHA}, object())


@pytest.mark.parametrize("fault", ("post_short", "post_nonfinite", "elapsed_nonfinite", "post_exceeds_total",
    "boolean_checks", "boolean_source_reads", "boolean_credential_reads", "boolean_provider_count",
    "floating_file_count", "unknown_receipt_field", "storage_identity"))
def test_storage_proof_requires_finite_typed_counts_consistent_aged_files_and_exact_schema(monkeypatch, fault):
    readback = _storage_readback(IDENTITY); receipt = readback["controls"]["complete.json"]
    if fault == "post_short": receipt["post_publication_observed_seconds"] = m.PROBE_SECONDS - 1
    if fault == "post_nonfinite": receipt["post_publication_observed_seconds"] = float("inf")
    if fault == "elapsed_nonfinite": receipt["observed_seconds"] = float("inf")
    if fault == "post_exceeds_total": receipt["post_publication_observed_seconds"] = receipt["observed_seconds"] + 1
    if fault == "boolean_checks": receipt["repeated_strict_checks"] = True
    if fault == "boolean_source_reads": receipt["source_data_reads"] = False
    if fault == "boolean_credential_reads": receipt["credential_reads"] = False
    if fault == "boolean_provider_count": receipt["provider_invocations"] = False
    if fault == "floating_file_count": receipt["synthetic_file_count"] = float(m.PROBE_FILES)
    if fault == "unknown_receipt_field": receipt["unregistered"] = "invented-extra"
    if fault == "storage_identity": receipt["storage_identity"] = {**receipt["storage_identity"], "inode": 3}
    monkeypatch.setattr(m.stable, "read_epoch_controls", lambda *_a, **_k: deepcopy(readback))
    with pytest.raises(m.QualificationError, match="storage_unqualified"):
        m._proof(IDENTITY, {"sha256": STORAGE_SHA}, object())


def test_invented_slow_publication_does_not_consume_required_post_publication_observation(monkeypatch):
    clock, checked, captured, last_file = [0.0], [], {}, [None]
    class SyntheticReceiver:
        def __init__(self, identity, registration):
            assert identity == IDENTITY and registration == m.probe_registration()
            self.pins = {"reservation.json": {"bytes": 1, "sha256": "a" * 64}}
            self.storage_identity = _storage_readback(IDENTITY)["storage_identity"]
        def publish(self, name, value):
            if name.startswith("synthetic-"):
                clock[0] += 10.0
                last_file[0] = clock[0]
            if name == "complete.json": captured.update(deepcopy(value))
            digest = m._sha(m._raw(value)); self.pins[name] = {"bytes": len(m._raw(value)), "sha256": digest}
            return digest
        def check(self): checked.append(clock[0])
        def close(self): captured["closed"] = True
    monkeypatch.setattr(m.stable, "Epoch", SyntheticReceiver)
    monkeypatch.setattr(m.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(m.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    result = m._probe(IDENTITY)
    assert result["passed"] is True and captured["closed"] is True
    assert clock[0] - last_file[0] >= m.PROBE_SECONDS
    assert captured["post_publication_observed_seconds"] >= m.PROBE_SECONDS
    assert captured["observed_seconds"] >= m.PROBE_SECONDS + 80
    assert len([t for t in checked if t >= last_file[0]]) >= 70
    assert captured["source_data_reads"] == captured["credential_reads"] == captured["provider_invocations"] == 0


@pytest.mark.parametrize("field", ("code", "artifact_role", "changed_fields", "stage"))
def test_untrusted_child_failure_values_cannot_become_public_diagnostic(monkeypatch, field):
    detail = {"code": "output_changed", "artifact_role": "controls", "changed_fields": ["ctime"], "stage": "bodies"}
    detail[field] = [SECRET] if field == "changed_fields" else SECRET
    monkeypatch.setattr(m.legacy.ipc, "_launch", lambda *_a, **_k: {"passed": False, "failure": deepcopy(detail)})
    with pytest.raises(m.QualificationError) as caught:
        m._child("health", IDENTITY)
    assert SECRET.encode() not in m._raw(m.failure_info(caught.value, "arguments"))


def test_second_drive_cannot_read_credentials_or_dispatch_after_epoch_plan_is_claimed(tmp_path, monkeypatch):
    context, cases = _context(tmp_path)
    try:
        _drive(context, cases, monkeypatch)
        with pytest.raises(stable.CustodyError, match="namespace_consumed"):
            m._drive(context, cases, IDENTITY, fixture=True,
                credential_reader=lambda *_: pytest.fail("credential reread after claimed plan"),
                transport=lambda *_: pytest.fail("dispatch after claimed plan"),
                project=lambda *_: pytest.fail("projection after claimed plan"))
    finally: context.close()


def test_pure_binding_requires_credential_provider_to_match_fixed_request(tmp_path):
    context, cases = _context(tmp_path)
    try:
        item = _started(context, _plan(context, cases))
        with pytest.raises(old.ProviderQualificationError, match="credential_refused"):
            m._binding(context, item, _credential("eodhd"))
        assert context.is_actual() is False and not context.dispatched
    finally: context.close()


def test_cli_requires_explicit_live_receipt_and_routes_health_and_storage_only(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(m, "preflight_actual", lambda head: calls.append(("health", head)) or {"health": True})
    monkeypatch.setattr(m, "run_storage_qualification", lambda head: calls.append(("storage", head)) or {"storage": True})
    monkeypatch.setattr(m, "run_actual", lambda head, sha: calls.append(("live", head, sha)) or
        {"clean_scoped_responses": 0, "planned_requests": 1})
    assert m.main(["--expected-head", "1" * 40, "--health"]) == 0
    assert m.main(["--expected-head", "1" * 40, "--storage-qualification"]) == 0
    assert m.main(["--expected-head", "1" * 40, "--storage-receipt-sha256", STORAGE_SHA]) == 2
    assert calls == [("health", "1" * 40), ("storage", "1" * 40), ("live", "1" * 40, STORAGE_SHA)]
    assert m.main(["--expected-head", "1" * 40]) == 2
    assert m.main(["--expected-head", "1" * 40, "--health", "--storage-receipt-sha256", STORAGE_SHA]) == 2
    assert len(calls) == 3 and "storage_unqualified" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        m.main(["--expected-head", "1" * 40, "--health", "--storage-qualification"])
