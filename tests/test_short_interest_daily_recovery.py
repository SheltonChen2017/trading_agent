"""Fictional original receipts and wire only; no private capture/key/network."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import json
import socket
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_daily_recovery as m
from scripts import capture_short_interest_daily_recovery as driver
from scripts import capture_short_interest_native_daily_active as producer
from scripts import capture_short_interest_native_daily_operational as operational
from scripts import continue_short_interest_native_identity as custody
from scripts import short_interest_keychain as keys
from test_short_interest_native_daily_active_capture import setup, run, EMPTY
from test_short_interest_native_daily_operational import control


@pytest.fixture(autouse=True)
def no_live_access(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("actual network/key access denied")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(keys, "read_named_keychain", denied)
    monkeypatch.setattr(producer, "read_named_keychain", denied)


def encoded(value): return canonical_json(value).encode()


def file_manifest(files):
    return encoded([{"name": name, "sha256": hash_bytes(raw), "bytes": len(raw)} for name, raw in sorted(files.items())])


def original(monkeypatch):
    """Explicit small original fixture: completed1,3; partial2; noninvoked4."""
    case = setup(monkeypatch); plan, index = case[:2]
    files = {}; code = {m.ROOT + f"fictional-{n:02d}.py": hash_bytes(str(n).encode()) for n in range(42)}
    source_code = hash_payload(code); monkeypatch.setattr(m, "SOURCE_CODE_SHA256", source_code)
    marker = {"registered_head": m.SOURCE_HEAD, "registered_remote": m.SOURCE_HEAD,
        "complete_current_code_manifest_sha256": source_code}
    def save(name, value):
        files[name] = value if type(value) is bytes else encoded(dict(value, runtime_registration=marker,
            stable_budget_protocol_sha256=m.SOURCE_OPERATIONAL))
    clock = datetime(2026, 10, 14, tzinfo=timezone.utc)
    def at(number): return (clock + timedelta(seconds=number)).isoformat().replace("+00:00", "Z")
    attempts = []; by_day = {}; total_bytes = rows = observed = invoked = 0
    for number, (day, page, state) in enumerate(((1, 1, "good"), (2, 1, "partial"),
            (2, 2, "unknown"), (3, 1, "good"), (4, 1, "not_invoked")), 1):
        prefix = f"day-{day:04d}-page-{page:02d}"
        url = m.daily.first_url(plan, day) if page == 1 else m.daily.ENDPOINT + "?cursor=fictional-continuation"
        start = {"schema": "si-daily-active-request-start-v1", "attempt": number, "day_ordinal": day,
            "query_date": plan.sessions()[day - 1], "page_ordinal": page, "request": {"method": "GET", "url": url,
            "authentication": "Bearer_header_not_recorded"}, "request_sha256": m.daily.page_request_sha256(url),
            "plan_sha256": plan.sha256, "code_head": m.SOURCE_HEAD, "request_started_at": at(number * 3),
            "global_attempts_claimed": number, "whole_page_bytes_reserved": m.daily.MAXIMUM_RESPONSE_BYTES,
            "whole_page_rows_reserved": 1000, "cumulative_bytes_charged_before": total_bytes,
            "inflight_bytes_reserved_after": m.daily.MAXIMUM_RESPONSE_BYTES,
            "cumulative_rows_charged_before": rows, "inflight_rows_reserved_after": 1000}
        save(prefix + ".started.json", start)
        has_raw = state in {"good", "partial"}; used_http = state != "not_invoked"
        receipt = {"schema": "si-daily-active-page-refusal-v1" if state == "unknown" else "si-daily-active-page-received-v1",
            "attempt": number, "day_ordinal": day, "query_date": plan.sessions()[day - 1], "page_ordinal": page,
            "request_sha256": start["request_sha256"], "request_started_at": start["request_started_at"],
            "received_at": at(number * 3 + 1), "http_invoked": used_http, "http_status": 200 if has_raw else None,
            "body_observed": has_raw, "raw_path": prefix + ".raw" if has_raw else None, "raw_sha256": None,
            "raw_bytes": None, "content_type": "application/json" if has_raw else None,
            "code": "received" if has_raw else "daily_active_page_or_chain_refused" if used_http else "cooperative_fatal_before_HTTP"}
        if has_raw:
            raw = EMPTY if state == "good" else encoded({"status": "OK", "results": [],
                "next_url": m.daily.ENDPOINT + "?cursor=fictional-continuation"})
            save(prefix + ".raw", raw); receipt.update(raw_sha256=hash_bytes(raw), raw_bytes=len(raw))
            total_bytes += len(raw)
        elif used_http:
            total_bytes += m.daily.MAXIMUM_RESPONSE_BYTES; rows += 1000
        invoked += int(used_http)
        save(prefix + (".refused.json" if state == "unknown" else ".received.json"), receipt)
        attempts.append(receipt); by_day.setdefault(day, []).append(receipt)
    results = []
    for day, receipts in sorted(by_day.items()):
        start, end = at(0), receipts[-1]["received_at"]
        save(f"day-{day:04d}.started.json", {"schema": "si-daily-active-day-start-v1", "day_ordinal": day,
            "query_date": plan.sessions()[day - 1], "started_at": start, "plan_sha256": plan.sha256})
        complete = day in {1, 3}
        result = {"schema": "si-daily-active-day-result-v1", "day_ordinal": day,
            "query_date": plan.sessions()[day - 1], "started_at": start, "retrieved_at": end,
            "pages_received": sum(row["raw_path"] is not None for row in receipts),
            "complete_advertised_chain": complete, "qualification_path": None, "qualification_sha256": None,
            "source_admitted": False}
        if complete:
            row = receipts[0]; raw = files[row["raw_path"]]
            page = m.daily.CapturedDailyActiveReferencePage(plan.sessions()[day - 1], 1, m.daily.first_url(plan, day),
                raw, row["request_started_at"], row["received_at"], 200, "application/json")
            report = m.daily.qualify_daily_active_reference(plan, day, (page,), index, started_at=start, retrieved_at=end)
            result.update(qualification_path=f"day-{day:04d}.qualified.private.json", qualification_sha256=report.sha256)
            save(result["qualification_path"], report.to_bytes())
        else: result["code"] = "halted_incomplete_or_refused_day_chain"
        save(f"day-{day:04d}." + ("completed.json" if complete else "refused.json"), result); results.append(result)
    observation = {"pending_receipt_slots": 0, "round_complete": False}
    inventory = {"schema": "si-daily-active-capture-inventory-prototype-v1", "plan_sha256": plan.sha256,
        "protocol_sha256": m.SOURCE_PROTOCOL, "started_at": at(0), "retrieved_at": at(20),
        "planned_days": 1169, "days_started": 4, "days_returned": 4, "attempts_claimed": 5,
        "http_invocations": invoked, "charged_bytes": total_bytes, "charged_rows": rows, "rows": observed,
        "attempts": attempts, "days": results, "halted": True, "publication_failed": False,
        "complete_frozen_sequence": False, "source_sequence_reported_complete": False,
        "source_admitted": False, "outcome_looks": 0, "qc_attempts": 0, "final_remote_observation": observation}
    save("inventory.private.json", inventory)
    save("round.closed.json", {"plan_sha256": plan.sha256, "round_closure_status": "refused",
        "complete_frozen_sequence": False, "source_admitted": False, "outcome_looks": 0, "qc_attempts": 0,
        "final_remote_observation": observation})
    claim = {"schema": "si-daily-active-spent-whole-round-prototype-v1", "plan_sha256": plan.sha256,
        "protocol_sha256": m.SOURCE_PROTOCOL, "stable_budget_protocol_sha256": m.SOURCE_OPERATIONAL,
        "started_at": at(0), "maximum_attempts": m.daily.MAXIMUM_REQUESTS,
        "maximum_total_bytes": m.daily.MAXIMUM_TOTAL_BYTES, "maximum_total_rows": m.daily.MAXIMUM_ROWS,
        "restart_or_resumption_allowed": False, "runtime_registration": dict(marker, complete_current_code_manifest=code)}
    claim_raw = encoded(claim)
    monkeypatch.setattr(m, "SOURCE_PINS", {name: hash_bytes(files[name]) for name in ("inventory.private.json", "round.closed.json")}
        | {"claim": hash_bytes(claim_raw)})
    monkeypatch.setattr(m, "SOURCE_COUNTS", {"files": len(files), "complete_days": 2,
        **{name: inventory[name] for name in ("attempts_claimed", "http_invocations", "days_started", "days_returned",
            "charged_bytes", "charged_rows", "rows")}})
    kwargs = {"manifest_raw": file_manifest(files), "read": lambda name, maximum: files[name], "claim_raw": claim_raw,
        "historical_code": lambda head, name: str(int(name.split("-")[1].split(".")[0])).encode(), "boundary": lambda: None}
    return case, files, kwargs


def scope_from(fixture):
    case, files, kwargs = fixture
    return m.audit_refused_parent(case[0], case[1], **kwargs)


def test_original_nonprefix_completion_and_all_unknown_spend_are_retained(monkeypatch):
    fixture = original(monkeypatch); scope = scope_from(fixture); payload = scope.payload()
    assert payload["completed_days"] == [1, 3]
    assert payload["selected_days"][:3] == [2, 4, 5] and len(payload["selected_days"]) == 1167
    assert scope.page_limit(2) == 62 and scope.page_limit(4) == 63
    assert payload["maximum_total_bytes"] == m.daily.MAXIMUM_TOTAL_BYTES - m.SOURCE_COUNTS["charged_bytes"]
    assert payload["maximum_total_rows"] == m.daily.MAXIMUM_ROWS - 1000
    assert payload["original_debits"]["attempts_claimed"] == 5 and payload["original_debits"]["http_invocations"] == 4
    assert [report.to_payload()["day_ordinal"] for report in scope.original_reports()] == [1, 3]


@pytest.mark.parametrize("member", ["day-0002-page-02.refused.json", "day-0004-page-01.started.json",
    "day-0001-page-01.raw", "day-0003.qualified.private.json", "round.closed.json"])
def test_any_original_negative_positive_or_claim_control_change_refuses(monkeypatch, member):
    fixture = original(monkeypatch); fixture[1][member] += b" "
    with pytest.raises(m.DailyRecoveryRefusal): scope_from(fixture)


def test_complete_original_day_cannot_be_replaced_with_saved_flag(monkeypatch):
    fixture = original(monkeypatch); files = fixture[1]
    name = "day-0003.qualified.private.json"; files[name] = b'{"complete":true}'
    fixture[2]["manifest_raw"] = file_manifest(files)
    with pytest.raises(m.DailyRecoveryRefusal, match="typed_day_replay"): scope_from(fixture)


def capture_child(monkeypatch):
    fixture = original(monkeypatch); scope = scope_from(fixture); case = fixture[0]; claims = []
    case[2]["recovery_scope"] = scope
    def claim(value): case[4].append("whole-claim"); claims.append(value)
    case[2]["claim_budget"] = claim
    value = run(case)
    return fixture, scope, claims[0], value


def test_selected_whole_chains_start_fresh_and_never_complete_original(monkeypatch):
    fixture, scope, claim, value = capture_child(monkeypatch)
    assert value["complete_recovery_scope"] is True and value["complete_frozen_sequence"] is False
    assert value["http_invocations"] == value["days_returned"] == 1167
    assert [row["day_ordinal"] for row in value["days"]] == list(scope.days(*fixture[0][:2]))
    assert all("fictional-continuation" not in request.full_url for request in fixture[0][5])
    assert claim["maximum_total_bytes"] == scope.limits()[1]
    assert all(not name.startswith(("day-0001", "day-0003")) for name in fixture[0][3])


def test_arbitrary_selected_list_is_not_a_factory_or_a_key_authority(monkeypatch):
    fixture = original(monkeypatch); case = fixture[0]
    case[2]["recovery_scope"] = {"days": [2, 4], "complete": True}
    with pytest.raises(m.daily.DailyActiveReferenceError, match="audited_recovery"): run(case)
    assert case[4] == case[5] == []
    with pytest.raises(m.DailyRecoveryRefusal): m.DailyRecoveryScope()


def publisher_case(monkeypatch, tmp_path):
    fixture = original(monkeypatch); scope = scope_from(fixture)
    prior, _, advanced = control(); plan, index = fixture[0][:2]
    registration = operational.RuntimeRegistration(head="a" * 40, remote="b" * 40,
        code_manifest={name: "c" * 64 for name in operational.required_code_paths()})
    gate = operational.DailyHTTPBatchGate(prior.guard, plan, lambda: None, index, registration)
    tmp_path.chmod(0o700); directory = tmp_path / "output"; directory.mkdir(mode=0o700)
    owned = custody._OwnedOutput(directory, lambda: None)
    publisher = driver.RecoveryPublisher(owned, gate, scope, directory, registration,
        dict(registration.binding()[2]) | {str(driver.ROOT / "scripts/capture_short_interest_daily_recovery.py"): "d" * 64})
    return publisher, owned, advanced


def test_existing_complete_day_is_not_permitted_in_child_output(monkeypatch, tmp_path):
    publisher, owned, _ = publisher_case(monkeypatch, tmp_path)
    try:
        with pytest.raises(m.DailyRecoveryRefusal, match="registered_recovery_days"):
            publisher.json(publisher.directory, "day-0001.started.json", {})
        assert list(publisher.directory.iterdir()) == []
    finally: owned.close()


def test_unverified_caller_success_flag_does_not_complete_child(monkeypatch, tmp_path):
    publisher, owned, _ = publisher_case(monkeypatch, tmp_path)
    try:
        publisher.inventory = encoded({"complete_recovery_scope": True, "halted": False, "publication_failed": False,
            "days_returned": 1167, "http_invocations": 0})
        closed = publisher.finish()
        assert closed["complete_recovery_scope"] is False and closed["round_closure_status"] == "refused"
    finally: owned.close()


def test_postpublication_remote_drift_creates_dominant_negative(monkeypatch, tmp_path):
    publisher, owned, advanced = publisher_case(monkeypatch, tmp_path)
    publisher.json(publisher.directory, "inventory.private.json", completed_cache_fixture(publisher))
    old = custody._OwnedOutput.publish
    def changed(self, name, raw, **kwargs):
        old(self, name, raw, **kwargs)
        if name == "round.closed.json": advanced[0] = True
    monkeypatch.setattr(custody._OwnedOutput, "publish", changed)
    try:
        closed = publisher.finish()
        assert closed["round_closure_status"] == "refused" and closed["code"] == "post_publication_remote_refused"
        assert json.loads((publisher.directory / "round.closed.json").read_bytes())["complete_recovery_scope"] is True
        assert (publisher.directory / "round.post-publication-refused.json").exists()
        assert not (publisher.directory / "round.post-publication-audit.json").exists()
    finally: owned.close()


def test_negative_child_sibling_prevents_replay_before_positive_claim(monkeypatch):
    scope = scope_from(original(monkeypatch))
    raw = file_manifest({"round.post-publication-refused.json": b"{}"})
    with pytest.raises(m.DailyRecoveryRefusal, match="negative_overrides"):
        next(m.combined_reports(scope, child_manifest_raw=raw, child_manifest_sha256=hash_bytes(raw),
            read=lambda *args: (_ for _ in ()).throw(AssertionError("must refuse before reading positive")),
            child_claim_raw=b"{}", expected_registration={}, historical_code=lambda *args: b"", boundary=lambda: None))


def test_final_audit_publication_drift_cannot_return_completed_child(monkeypatch, tmp_path):
    publisher, owned, advanced = publisher_case(monkeypatch, tmp_path)
    publisher.json(publisher.directory, "inventory.private.json", completed_cache_fixture(publisher))
    old = custody._OwnedOutput.publish
    def changed(self, name, raw, **kwargs):
        old(self, name, raw, **kwargs)
        if name == "round.post-publication-audit.json": advanced[0] = True
    monkeypatch.setattr(custody._OwnedOutput, "publish", changed)
    try:
        result = publisher.finish()
        assert result["complete_recovery_scope"] is False
        assert (publisher.directory / "round.post-publication-refused.json").exists()
    finally:
        owned.close()


def completed_cache_fixture(publisher):
    """Closure-only fixture: emulate an already-qualified cache, never source evidence."""
    selected = set(publisher.scope.days(publisher.gate.plan, publisher.gate.index))
    publisher.gate._closed_days = selected
    publisher.gate._qualified = {day: "f" * 64 for day in selected}
    return {"schema": "si-daily-recovery-capture-inventory-v1", "recovery_scope_sha256": publisher.scope.sha256,
        "complete_frozen_sequence": False, "complete_recovery_scope": True, "halted": False,
        "publication_failed": False, "days_returned": len(selected), "http_invocations": 0}


def test_failed_inventory_write_cannot_complete_from_memory(monkeypatch, tmp_path):
    publisher, owned, _ = publisher_case(monkeypatch, tmp_path)
    value = completed_cache_fixture(publisher)
    old = custody._OwnedOutput.publish
    def failed(self, name, raw, **kwargs):
        if name == "inventory.private.json": raise OSError("fabricated single publication failure")
        old(self, name, raw, **kwargs)
    monkeypatch.setattr(custody._OwnedOutput, "publish", failed)
    try:
        with pytest.raises(OSError): publisher.json(publisher.directory, "inventory.private.json", value)
        result = publisher.finish()
        assert result["complete_recovery_scope"] is False
        assert not (publisher.directory / "inventory.private.json").exists()
    finally: owned.close()


def test_clean_durable_inventory_and_postpublication_check_close_child_only(monkeypatch, tmp_path):
    publisher, owned, _ = publisher_case(monkeypatch, tmp_path)
    try:
        publisher.json(publisher.directory, "inventory.private.json", completed_cache_fixture(publisher))
        result = publisher.finish()
        assert result["complete_recovery_scope"] is True and result["complete_frozen_sequence"] is False
        assert (publisher.directory / "round.post-publication-audit.json").exists()
    finally: owned.close()


def test_registered_runtime_raises_after_durable_negative_without_source_calls(monkeypatch, tmp_path):
    publisher, owned, _ = publisher_case(monkeypatch, tmp_path)
    owned.close()
    scope, gate, registration = publisher.scope, publisher.gate, publisher.registration
    @contextmanager
    def bundle(*args):
        yield gate.guard, SimpleNamespace(plan=gate.plan, index=gate.index), registration, lambda: None
    @contextmanager
    def original_scope(*args): yield scope
    monkeypatch.setattr(driver, "_bundle", bundle)
    monkeypatch.setattr(driver, "_original_scope", original_scope)
    monkeypatch.setattr(driver, "DIRECTORY", tmp_path / "new-child")
    monkeypatch.setattr(producer, "capture_with_seams", lambda *args, **kwargs: None)
    with pytest.raises(m.DailyRecoveryRefusal, match="closed_negative"):
        driver.run_registered(head="a" * 40, remote="b" * 40, code_manifest=publisher.complete_manifest,
            manifest_raw=b"fictional-manifest-not-read", expected_scope_sha256=scope.sha256,
            expected_protocol_sha256=hash_payload(driver.protocol(scope)))
    assert json.loads((driver.DIRECTORY / "round.closed.json").read_bytes())["complete_recovery_scope"] is False


@pytest.mark.parametrize("reason", ["remote", "producer_error"])
def test_preclosure_drift_or_producer_error_cannot_complete_cached_qualified_days(monkeypatch, tmp_path, reason):
    publisher, owned, advanced = publisher_case(monkeypatch, tmp_path)
    try:
        publisher.json(publisher.directory, "inventory.private.json", completed_cache_fixture(publisher))
        advanced[0] = reason == "remote"
        result = publisher.finish(force_refused=reason == "producer_error")
        assert result["complete_recovery_scope"] is False and result["round_closure_status"] == "refused"
    finally: owned.close()


def test_original_per_day_START_debits_reduce_child_page_budget(monkeypatch):
    monkeypatch.setattr(m.daily, "MAXIMUM_DAY_CHAINS", 1)  # Explicit serial fictional scheduler.
    fixture = original(monkeypatch); scope = scope_from(fixture); case = fixture[0]
    case[2]["recovery_scope"] = scope
    case[2]["claim_budget"] = lambda value: case[4].append("whole-claim")
    def wire(opener, request, maximum):
        case[5].append(request)
        return encoded({"status": "OK", "results": [],
            "next_url": m.daily.ENDPOINT + "?cursor=fictional-" + str(len(case[5]))}), "application/json", 200
    monkeypatch.setattr(producer, "_http", wire)
    result = run(case)
    assert len(case[5]) == 62 and result["complete_recovery_scope"] is False
    assert result["halted"] is True and result["days_started"] == 1
    assert "day-0002.completed.json" not in case[3]


def child_replay_fixture(monkeypatch):
    fixture, scope, claim, value = capture_child(monkeypatch)
    code = {name: hash_bytes(b"fictional-child-code") for name in driver.required_code_paths()}
    registration = {"head": "b" * 40, "remote": "c" * 40, "code_manifest": code,
        "code_manifest_sha256": hash_payload(code), "scope_sha256": scope.sha256,
        "protocol_sha256": hash_payload(driver.protocol(scope))}
    marker = {"registered_head": "b" * 40, "registered_remote": "c" * 40,
        "complete_current_code_manifest_sha256": hash_payload({name: sha for name, sha in code.items()
            if name != m.ROOT + "scripts/capture_short_interest_daily_recovery.py"})}
    files = {name: item if type(item) is bytes else encoded(dict(item, runtime_registration=marker,
        stable_budget_protocol_sha256=m.SOURCE_OPERATIONAL)) for name, item in fixture[0][3].items()}
    files["inventory.private.json"] = encoded(dict(value, recovery_registration=registration))
    closed = {"schema": "si-daily-recovery-authoritative-close-v1", "recovery_registration": registration,
        "audit_started_at": "2026-10-14T02:00:00Z", "audit_received_at": "2026-10-14T02:00:01Z",
        "round_closure_status": "completed_child_scope", "complete_recovery_scope": True,
        "complete_frozen_sequence": False, "matching_remote_equal": True, "pending_slots": 0,
        "http_invocations": value["http_invocations"], "source_admitted": False, "outcome_looks": 0, "qc_attempts": 0}
    files["round.closed.json"] = encoded(closed)
    files["round.post-publication-audit.json"] = encoded({"schema": "si-daily-recovery-post-publication-audit-v1",
        "recovery_registration": registration, "closure_sha256": hash_payload(closed),
        "matching_remote_equal": True, "complete_recovery_scope": True,
        "audit_started_at": "2026-10-14T02:00:02Z", "audit_received_at": "2026-10-14T02:00:03Z"})
    raw = file_manifest(files)
    kwargs = {"child_manifest_raw": raw, "child_manifest_sha256": hash_bytes(raw),
        "read": lambda name, maximum: files[name], "child_claim_raw": encoded(dict(claim, recovery_registration=registration)),
        "expected_registration": registration, "historical_code": lambda *args: b"fictional-child-code", "boundary": lambda: None}
    return scope, files, kwargs


def test_whole_chain_combination_exhausts_all1169_and_does_not_change_parent(monkeypatch):
    scope, files, kwargs = child_replay_fixture(monkeypatch)
    actual = [report.to_payload()["day_ordinal"] for report in m.combined_reports(scope, **kwargs)]
    assert actual == list(range(1, 1170))
    assert scope.payload()["parent_status"] == "refused_original_claim_stays_spent"


def test_missing_child_day_cannot_be_stitched_from_original_partial_pages(monkeypatch):
    scope, files, kwargs = child_replay_fixture(monkeypatch)
    del files["day-0002.completed.json"]
    kwargs["child_manifest_raw"] = file_manifest(files)
    kwargs["child_manifest_sha256"] = hash_bytes(kwargs["child_manifest_raw"])
    with pytest.raises(m.DailyRecoveryRefusal, match="complete_child_member_set"):
        list(m.combined_reports(scope, **kwargs))
