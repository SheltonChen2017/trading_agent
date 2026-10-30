"""Fabricated completion replay only; no actual paths, secrets or providers."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.continue_short_interest_native_identity as capture

sys.path.insert(0, str(Path(__file__).parent))
HELPERS = importlib.util.spec_from_file_location("completed_continuation_fabricated_helpers",
        Path(__file__).with_name("test_short_interest_native_identity_continuation.py"))
# The physical lane root is a fixed ancestor, never an actual capture directory.
helpers = importlib.util.module_from_spec(HELPERS)
sys.modules[HELPERS.name] = helpers
HELPERS.loader.exec_module(helpers)
import scripts.verify_short_interest_native_identity_continuation as m


def encoded(value):
    return canonical_json(value).encode()


def fixture():
    h = helpers.Harness()
    code = hash_payload({"git_commit": helpers.NEW_HEAD, "files": [
        {"path": name, "sha256": hash_bytes(helpers.historical(helpers.NEW_HEAD, name))}
        for name in capture.CODE_FILES]})
    h.run(code_identity_sha256=code)
    state = h.source.payload()
    budget = {**h.claims[0][1], "schema": "si-native-identity-manual-continuation-budget-v1",
            "run_id": "fabricated-child", "remote_head": "1" * 40,
            "source_inventory_sha256": state["source_inventory_sha256"],
            "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
            "credential_item": capture.freeze_protocol(h.source)["credential_item"],
            "unused_parent_slots_repurposable": False}
    args = {"budget_raw": encoded(budget), "budget_sha256": hash_bytes(encoded(budget)),
            "expected_head": helpers.NEW_HEAD,
            "expected_protocol_sha256": hash_payload(capture.freeze_protocol(h.source)),
            "expected_code_identity_sha256": code, "historical_code": helpers.historical,
            "local_guard": lambda: None, "expected_run_id": "fabricated-child", "expected_remote_head": "1" * 40}
    return h, repin(h.saved, args)


def repin(files, args):
    args = dict(args)
    args["byte_pins"] = {name: hash_bytes(raw) for name, raw in files.items()}
    args["inventory_sha256"] = hash_payload([{"name": name, "sha256": args["byte_pins"][name], "bytes": len(files[name])}
                                             for name in sorted(files)])
    return args


def mutate(files, name, change):
    value = json.loads(files[name])
    change(value)
    files[name] = encoded(value)
    if name == "inventory.private.json":
        complete = json.loads(files["completed.json"])
        complete["inventory_bytes_sha256"] = hash_bytes(files[name])
        complete["inventory_payload_sha256"] = hash_payload(value)
        files["completed.json"] = encoded(complete)


def verify(h, args):
    return m.verify_completed_continuation(h.source, h.saved, **args)


def test_complete_child_replays_original_parent_reports_and_partial_origin_without_recapture():
    h, args = fixture()
    result = verify(h, args)
    value = result.payload()
    assert len(value["old_reports"]) == 1 and len(value["new_reports"]) == 2
    assert value["old_reports"] == h.source.payload()["completed_reports"]
    assert value["new_attempts"] == 4 and value["cumulative_attempts"] == 8
    assert len(list(result.iter_new_reports())) == 2
    assert list(result.iter_new_reports())[0][1] == h.saved["date-002.qualified.private.json"]
    assert value["source_admitted"] is False and value["ready_for_empirical_backtest"] is False
    assert value["outcome_looks"] == value["qc_attempts"] == 0
    assert json.loads(list(result.iter_new_reports())[0][1])["started_at"] == helpers.NOW


@pytest.mark.parametrize("name,change", [
    ("date-002-active-page-02.started.json", lambda v: v["request"].update(url=capture.initial_url(helpers.DATES[1], True))),
    ("date-002-active-page-02.started.json", lambda v: v.update(new_attempt=2)),
    ("date-002-active-page-02.started.json", lambda v: v.update(started_at="2026-10-14T02:00:00Z")),
    ("date-002-active-page-02.received.json", lambda v: v.update(received_at="2026-10-14T03:59:59Z")),
    ("date-002-active-page-02.received.json", lambda v: v.update(raw_path="another.raw")),
    ("date-002-active-page-02.received.json", lambda v: v.update(http_status=404)),
    ("date-002-active-page-02.received.json", lambda v: v.update(content_type="text/html")),
    ("date-002.qualified.private.json", lambda v: v.update(started_at="2026-10-14T04:00:00Z")),
    ("inventory.private.json", lambda v: v["dates"][0].update(retrieved_at="2026-10-14T04:00:00Z")),
    ("inventory.private.json", lambda v: v.update(new_attempts_consumed=3)),
    ("inventory.private.json", lambda v: v.update(cumulative_attempts_consumed=7)),
    ("inventory.private.json", lambda v: v.update(new_raw_bytes=1)),
    ("inventory.private.json", lambda v: v.update(new_decoded_rows=1)),
    ("inventory.private.json", lambda v: v.update(source_admitted=True)),
    ("inventory.private.json", lambda v: v.update(completed_at=helpers.NOW)),
    ("completed.json", lambda v: v.update(completed_at=helpers.NOW)),
    ("completed.json", lambda v: v.update(qc_attempts=1)),
    ("started.json", lambda v: v.update(code_head="b" * 40)),
    ("protocol.private.json", lambda v: v.update(automatic_retries=1)),
])
def test_semantic_mutations_refuse_even_with_new_byte_and_inventory_pins(name, change):
    h, args = fixture()
    mutate(h.saved, name, change)
    with pytest.raises((m.CompletedIdentityRefusal, capture.ContinuationRefusal, ValueError)):
        verify(h, repin(h.saved, args))


@pytest.mark.parametrize("change", [lambda v: v.update(automatic_retries=1),
        lambda v: v.update(maximum_new_attempts=99999), lambda v: v.update(parent_attempts_consumed=0),
        lambda v: v.update(unused_parent_slots_repurposable=True),
        lambda v: v.update(failed_start_bytes_sha256="b" * 64),
        lambda v: v.update(run_id="another-child"), lambda v: v.update(remote_head="2" * 40)])
def test_spent_child_budget_cannot_be_reset_or_rebound_after_repin(change):
    h, args = fixture()
    value = json.loads(args["budget_raw"])
    change(value)
    args.update(budget_raw=encoded(value), budget_sha256=hash_bytes(encoded(value)))
    with pytest.raises(m.CompletedIdentityRefusal):
        verify(h, args)


@pytest.mark.parametrize("change", ["remove", "extra", "refused", "unregistered_raw", "repinned_next_cursor"])
def test_inventory_or_raw_chain_corruption_cannot_complete(change):
    h, args = fixture()
    name = "date-002-active-page-02.raw"
    if change == "remove":
        del h.saved[name]
    elif change in ("extra", "refused"):
        h.saved["another.raw" if change == "extra" else "refused.json"] = b"{}"
    else:
        h.saved[name] = helpers.body(capture.initial_url(helpers.DATES[1], True))
        if change == "repinned_next_cursor":
            mutate(h.saved, "date-002-active-page-02.received.json",
                   lambda v: v.update(raw_sha256=hash_bytes(h.saved[name]), raw_bytes=len(h.saved[name])))
    with pytest.raises((m.CompletedIdentityRefusal, capture.ContinuationRefusal, ValueError)):
        verify(h, args if change == "unregistered_raw" else repin(h.saved, args))


def test_historical_binary_code_is_not_working_file_or_author_name_authority():
    h, args = fixture()
    args["historical_code"] = lambda head, name: b"changed committed code"
    with pytest.raises(m.CompletedIdentityRefusal):
        verify(h, args)


@pytest.mark.parametrize("name,change", [
    ("completed.json", lambda v: v.update(qc_attempts=False)),
    ("inventory.private.json", lambda v: v.update(source_admitted=0)),
    ("date-002-active-page-02.started.json", lambda v: v.update(active_panel=1)),
    ("date-002-inactive-page-01.received.json", lambda v: v.update(ordinal=1.0)),
])
def test_JSON_numeric_equality_cannot_substitute_counter_or_authority_types(name, change):
    h, args = fixture()
    mutate(h.saved, name, change)
    with pytest.raises(m.CompletedIdentityRefusal):
        verify(h, repin(h.saved, args))


def test_streaming_replay_and_postconstruction_read_pin_recheck():
    h, args = fixture()
    streamed = helpers.lazy_files(h.saved)
    result = m.verify_completed_continuation(h.source, streamed, **args)
    assert result.payload()["new_attempts"] == 4
    h.saved["date-002.qualified.private.json"] += b" "
    with pytest.raises((m.CompletedIdentityRefusal, capture.ContinuationRefusal)):
        list(result.iter_new_reports())


@pytest.mark.parametrize("field", ["_metadata", "_source", "_read", "_anchor"])
def test_sealed_replay_reflection_cannot_redirect_saved_receipts(field):
    h, args = fixture()
    result = verify(h, args)
    object.__setattr__(result, field, object())
    with pytest.raises(m.CompletedIdentityRefusal):
        result.payload()
