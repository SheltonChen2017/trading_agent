"""Invented operational controls only; OS network denial is external."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
import fcntl
import stat
from dataclasses import replace
import subprocess
import sys
import io


if os.name != "posix":
    pytest.skip("IBWIN-CR01: POSIX custody supported; Windows port deferred", allow_module_level=True)

import research.insider_buying_sec_2006q1_parent_bootstrap as bootstrap
from test_insider_buying_sec_2006q1_parent_locators import _assess, _master, _path, _row


def _raw(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def test_worker_cli_canonical_summary_is_accepted_by_its_actual_parent_decoder(monkeypatch, capsys):
    invented = {"fixture_only": True, "counts": {"selected_prefix": 2}, "audit_id": "invented-wire-only"}
    monkeypatch.setattr(bootstrap, "_required_identity", lambda *args: None)
    monkeypatch.setattr(bootstrap, "_worker", lambda **kwargs: invented)
    monkeypatch.setattr(bootstrap.sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    assert bootstrap.main(["--worker", "--audit-id", "ib-2006q1-parent-bootstrap-wire-invented",
        "--expected-head", "a" * 40, "--expected-exposure-snapshot-sha256", "b" * 64]) == 0
    assert bootstrap._json(capsys.readouterr().out.encode()) == invented


def _file(root, name, raw, mode=0o600):
    path = root / name
    current = root
    for part in Path(name).parts[:-1]:
        current /= part
        current.mkdir(exist_ok=True, mode=0o700)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def _request(ordinal=1):
    accession = f"0000000123-06-{ordinal:06d}"
    return {"accession_number": accession,
            "url": "https://www.sec.gov/Archives/edgar/data/123/" + accession + ".txt"}


def _simple(tmp_path, events, *, root_id="invented-root", inventory=None):
    root = tmp_path / root_id
    root.mkdir(mode=0o700)
    _file(root, "inventory.json", _raw({"requests": []} if inventory is None else inventory))
    journal = b"".join(_raw(event) + b"\n" for event in events)
    _file(root, "attempts.jsonl", journal)
    report = _raw({"kind": "invented-report"})
    _file(root, "report.json", report)
    _file(root, "commit.json", _raw({"report_name": "report.json", "report_sha256": _sha(report),
                                    "attempt_journal_sha256": _sha(journal)}))
    return bootstrap.RootSpec(root_id, root, "simple-jsonl")


def _observe(specs):
    trees, exposure, snapshot = bootstrap.bootstrap_exposures(tuple(specs))
    try:
        return json.loads(exposure), json.loads(snapshot)
    finally:
        for tree in reversed(trees):
            tree.close()


def test_real_legacy_root_id_with_underscores_is_supported(tmp_path):
    spec = _simple(tmp_path, [{"kind": "pilot-finished"}], root_id="invented_legacy_root")
    exposure, _ = _observe([spec])
    assert exposure["records"] == []


@pytest.mark.parametrize("prefix", ["/Archives/", "https://www.sec.gov/Archives/"])
def test_exact_original_xml_archive_path_exposes_accession(prefix):
    assert bootstrap._accession_url(prefix + "edgar/data/123/000000012306000001/index.json") == "0000000123-06-000001"


def test_ordinal_linked_simple_terminal_is_not_left_ambiguous(tmp_path):
    request = _request()
    spec = _simple(tmp_path, [{"kind": "attempt-start", "ordinal": 1, "url": request["url"]},
        {"kind": "attempt-finish", "ordinal": 1, "outcome": "http_status"}])
    exposure, snapshot = _observe([spec])
    assert {row["state"] for row in exposure["records"][0]["evidence"]} == {"started"}
    assert snapshot["roots"][0]["pending_parent_accessions"] == []


def test_planned_inventory_never_becomes_exposure(tmp_path):
    spec = _simple(tmp_path, [{"kind": "pilot-finished"}], inventory={"requests": [_request()]})
    exposure, snapshot = _observe([spec])
    assert exposure["records"] == []
    assert snapshot["roots"][0]["plan_requests_are_dispatch_evidence"] is False


def test_exact_v3_rows_request_hash_is_resolved_without_dispatch():
    request = _request()
    raw = _raw({"rows": [{"global_index": 7, "source_class": "unattempted", "request": request}]})
    assert bootstrap._request_lookup({"shard-0001/inventory.json": raw})[_sha(_raw(request))] == {request["accession_number"]}


def test_finished_without_matching_reserved_ordinal_is_refused(tmp_path):
    spec = _simple(tmp_path, [{"kind": "attempt-finish", "ordinal": 3, "outcome": "http_status"}])
    with pytest.raises(bootstrap.ParentBootstrapError, match="terminal_without_reserved_start"):
        _observe([spec])


def _chain(tmp_path, events=(), *, root_id="invented-chain", requests=None, rows=None):
    root = tmp_path / root_id
    root.mkdir(mode=0o700)
    inventory = {"requests": [] if requests is None else requests} if rows is None else {"rows": rows}
    inventory_raw = _raw(inventory)
    _file(root, "inventory.json", inventory_raw)
    tail, pieces = _sha(inventory_raw), []
    for ordinal, item in enumerate(events, 1):
        raw = _raw({**item, "prev_sha256": tail}) + b"\n"
        tail = _sha(raw)
        _file(root, f"event-{ordinal:06d}-{tail}.json", raw)
        pieces.append(raw)
    _file(root, "attempts.jsonl", b"".join(pieces))
    report = _raw({"kind": "invented-report"})
    _file(root, "report.json", report)
    _file(root, "commit.json", _raw({"report_name": "report.json", "report_sha256": _sha(report),
        "inventory_sha256": _sha(inventory_raw), "attempt_journal_sha256": _sha(b"".join(pieces))}))
    return bootstrap.RootSpec(root_id, root, "event-chain")


def _claim(tmp_path, *, start=False, terminal=False, root_id="invented-claims"):
    root = tmp_path / root_id
    root.mkdir(mode=0o700)
    _file(root, "capture.lock", b"INVENTED GLOBAL CLAIM LOCK\n")
    capture_id = "ib-invented-capture"
    request = _request()
    row = {"request": request, "request_sha256": _sha(_raw(request)), "global_index": 1}
    reservation = {"selection": {"requests": [row]}, "selection_sha256": "a" * 64,
                   "reserved_utc": "2026-10-01T00:00:00Z"}
    reservation_raw = _raw(reservation)
    _file(root, f"runs/{capture_id}/reservation.json", reservation_raw)
    claim = {"request": row, "capture_id": capture_id, "reservation_sha256": _sha(reservation_raw),
             "selection_sha256": "a" * 64}
    claim_raw = _raw(claim)
    claim_name = bootstrap.locators.accession_key(request["accession_number"]) + ".json"
    _file(root, "claims/" + claim_name, claim_raw)
    start_raw = _raw({"claim_sha256": _sha(claim_raw), "request_sha256": row["request_sha256"],
        "reservation_sha256": _sha(reservation_raw), "ordinal": 0, "started_utc": "2026-10-01T00:00:01Z"})
    if start:
        _file(root, f"runs/{capture_id}/request-000-start.json", start_raw)
    if terminal:
        _file(root, f"runs/{capture_id}/request-000-result.json", _raw({"start_sha256": _sha(start_raw),
            "request_sha256": row["request_sha256"], "ordinal": 0, "finished_utc": "2026-10-01T00:00:02Z"}))
    return bootstrap.RootSpec(root_id, root, "global-claims")


@pytest.mark.parametrize("start,terminal,states,pending", [
    (False, False, {"reserved"}, 1), (True, False, {"reserved", "started", "ambiguous"}, 1),
    (True, True, {"reserved", "started"}, 0),
])
def test_permanent_claim_consumed_even_without_start_or_completion(tmp_path, start, terminal, states, pending):
    exposure, snapshot = _observe([_claim(tmp_path, start=start, terminal=terminal)])
    assert {e["state"] for e in exposure["records"][0]["evidence"]} == states
    assert len(snapshot["roots"][0]["pending_parent_accessions"]) == pending
    assert snapshot["roots"][0]["consumed_reservation_records"] == 1


def test_claim_terminal_without_start_refuses_instead_of_releasing_claim(tmp_path):
    with pytest.raises(bootstrap.ParentBootstrapError, match="terminal_without_start"):
        _observe([_claim(tmp_path, terminal=True)])


@pytest.mark.parametrize("mutation", ["name", "request_sha", "reservation_sha", "selection_sha"])
def test_claim_external_request_and_reservation_linkage_are_binding(tmp_path, mutation):
    spec = _claim(tmp_path)
    leaf = next((spec.path / "claims").iterdir())
    body = json.loads(leaf.read_bytes())
    if mutation == "name":
        leaf.rename(leaf.with_name("f" * 64 + ".json"))
    else:
        if mutation == "request_sha":
            body["request"]["request_sha256"] = "f" * 64
        else:
            body[mutation + "256"] = "f" * 64
        leaf.write_bytes(_raw(body))
    with pytest.raises(bootstrap.ParentBootstrapError):
        _observe([spec])


def test_selected_completed_and_reused_both_remain_consumed(tmp_path):
    requests = [_request(1), _request(2)]
    spec = _chain(tmp_path, [{"kind": "item-complete", "source": source,
                            "accession_number": request["accession_number"]}
                           for source, request in zip(("acquired", "reused"), requests)], requests=requests)
    exposure, snapshot = _observe([spec])
    assert [e["evidence"][0]["state"] for e in exposure["records"]] == ["completed", "reused"]
    assert snapshot["roots"][0]["completed_item_records"] == snapshot["roots"][0]["reused_records"] == 1


def test_unfinished_individual_event_chain_is_consumed_without_aggregate_commit(tmp_path):
    request = _request()
    spec = _chain(tmp_path, [{"kind": "attempt-start", "ordinal": 1, **request}], requests=[request])
    (spec.path / "attempts.jsonl").unlink()
    (spec.path / "commit.json").unlink()
    exposure, snapshot = _observe([spec])
    assert {e["state"] for e in exposure["records"][0]["evidence"]} == {"started", "ambiguous"}
    assert snapshot["roots"][0]["pending_parent_accessions"] == [request["accession_number"]]


@pytest.mark.parametrize("mutation", ["chain", "journal", "report", "sequence", "unknown_kind"])
def test_event_integrity_refuses_disagreement(tmp_path, mutation):
    spec = _chain(tmp_path, [{"kind": "item-complete", "source": "reused", "accession_number": _request()["accession_number"]}])
    leaf = next(spec.path.glob("event-*.json"))
    if mutation == "chain":
        d = json.loads(leaf.read_bytes());d["prev_sha256"] = "f" * 64
        leaf.write_bytes(_raw(d) + b"\n")
    elif mutation == "journal":
        (spec.path / "attempts.jsonl").write_bytes(b"{}\n")
    elif mutation == "report":
        (spec.path / "report.json").write_bytes(b"{}")
    elif mutation == "sequence":
        leaf.rename(leaf.with_name(leaf.name.replace("000001", "000002")))
    else:
        spec = _chain(tmp_path, [{"kind": "new-unknown-request-event"}], root_id="second-chain")
    with pytest.raises(bootstrap.ParentBootstrapError):
        _observe([spec])


def test_all_journal_clock_ordinals_retained_and_old_missing_clock_not_backdated(tmp_path):
    spec = _simple(tmp_path, [{"kind": "attempt-reserved", "ordinal": 1,
        "path": "/Archives/edgar/data/123/000000012306000001/index.json"},
        {"kind": "attempt-response", "ordinal": 1},
        {"kind": "attempt-start", "ordinal": 2, "url": _request(2)["url"], "started_utc": "2026-10-01T00:00:01Z"},
        {"kind": "attempt-finish", "ordinal": 2, "finished_utc": "2026-10-01T00:00:02Z"}])
    _, snapshot = _observe([spec])
    r = snapshot["roots"][0]
    assert sorted(r["control_clocks"]) == ["attempts.jsonl:line-000003", "attempts.jsonl:line-000004"]
    assert r["exposure_controls"][0]["clock"] is None
    assert r["clock_missing_is_not_backdated"] is True


@pytest.mark.parametrize("clock", [True, "2026-10-01", "2026-10-01T00:00:00+01:00", "bad"])
def test_non_utc_or_untyped_clock_is_refused(clock):
    with pytest.raises(bootstrap.ParentBootstrapError):
        bootstrap._clocks({"started_utc": clock})


@pytest.mark.parametrize("mode", [0o644, 0o666, 0o400])
def test_private_leaf_requires600_without_exact_legacy_exception(tmp_path, mode):
    spec = _simple(tmp_path, [{"kind": "pilot-finished"}])
    (spec.path / "inventory.json").chmod(mode)
    with pytest.raises(bootstrap.ParentBootstrapError, match="private_leaf_mode"):
        _observe([spec])


def test_exact_legacy644_exception_requires_external_bytes_and_is_recorded(tmp_path, monkeypatch):
    spec = _simple(tmp_path, [{"kind": "pilot-finished"}])
    leaf = spec.path / "inventory.json";leaf.chmod(0o644)
    monkeypatch.setattr(bootstrap, "LEGACY_PUBLIC_METADATA_SHA256", {(spec.root_id, "inventory.json"): _sha(leaf.read_bytes())})
    _, snapshot = _observe([spec])
    assert snapshot["roots"][0]["legacy_public_metadata_modes"] == {"inventory.json": 0o644}
    leaf.write_bytes(b"{}")
    with pytest.raises(bootstrap.ParentBootstrapError, match="legacy_public_metadata_external_hash"):
        _observe([spec])


@pytest.mark.parametrize("attack", ["symlink", "hardlink", "root_symlink", "root_mode"])
def test_named_ancestry_leaf_links_and_private_mode_are_binding(tmp_path, attack):
    spec = _simple(tmp_path, [{"kind": "pilot-finished"}])
    if attack == "symlink":
        q = spec.path / "inventory.json";saved = q.with_name("saved.bin");q.rename(saved);q.symlink_to(saved)
    elif attack == "hardlink":
        os.link(spec.path / "inventory.json", spec.path / "linked.bin")
    elif attack == "root_symlink":
        link = tmp_path / "symlink-root";link.symlink_to(spec.path)
        spec = bootstrap.RootSpec("symlink-root", link, spec.profile)
    else:
        spec.path.chmod(0o755)
    with pytest.raises((bootstrap.ParentBootstrapError, bootstrap.custody.ArchiveAssessmentRunnerError,
                        bootstrap.custody.EodhdDemoError, OSError)):
        _observe([spec])


def test_shared_lock_refuses_a_concurrent_writer(tmp_path):
    spec = _simple(tmp_path, [{"kind": "pilot-finished"}])
    leaf = _file(spec.path, "run.lock", b"")
    fd = os.open(leaf, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            _observe([spec])
    finally:
        os.close(fd)


def test_custody_rechecks_existing_control_substitution(tmp_path):
    spec = _simple(tmp_path, [{"kind": "pilot-finished"}])
    trees, _, _ = bootstrap.bootstrap_exposures((spec,))
    try:
        (spec.path / "inventory.json").write_bytes(b"{}")
        with pytest.raises(bootstrap.ParentBootstrapError, match="source_leaf_changed"):
            trees[0].recheck()
    finally:
        trees[0].close()


@pytest.mark.parametrize("payload", [b"bad", b'\x1f\x8b', gzip.compress(b"test")[:-1], gzip.compress(b"test") + b"trailing",
    gzip.compress(b"a") + gzip.compress(b"b")])
def test_master_gzip_crc_framing_truncation_and_trailing_refused(payload):
    with pytest.raises(bootstrap.ParentBootstrapError):
        bootstrap._decompress_master(payload)


def test_master_gzip_fully_streamed_and_expansion_bound(monkeypatch):
    raw = b"invented public metadata\n" * 20_000
    assert bootstrap._decompress_master(gzip.compress(raw)) == raw
    monkeypatch.setattr(bootstrap, "MAX_MASTER_BYTES", 10)
    with pytest.raises(bootstrap.ParentBootstrapError, match="expansion_bound"):
        bootstrap._decompress_master(gzip.compress(raw))


def _fixture(tmp_path):
    rows = [_row(i, DOCUMENT_TYPE=form) for i, form in enumerate(bootstrap.locators.FORMS, 1)]
    inventory_raw = _assess(rows).canonical_bytes()
    inventory = json.loads(inventory_raw)
    complete_raw = _raw({"schema": "insider-2006q1-metadata-observer-completion-v1", "fixture_only": True,
        "inventory_sha256": _sha(inventory_raw), "inventory_bytes": len(inventory_raw), "accounting": inventory["accounting"]})
    census = "/".join(bootstrap.custody.CENSUS_PARTS)
    _file(tmp_path, census + "/inventory.json", inventory_raw)
    _file(tmp_path, census + "/complete.json", complete_raw)
    master = _master(_path(3), _path(4, form="4/A"))
    parsed = bootstrap.locators.parse_sec_quarter_master_index(master, year=2006, quarter=1)
    compressed = gzip.compress(master, mtime=0)
    spec = _chain(tmp_path, root_id="fixture-master")
    report = _raw({"master_indexes": [{"period": "2006Q1", "source_url": bootstrap._MASTER_URL,
        "raw_object": {"sha256": _sha(compressed), "relative_path": "objects/" + _sha(compressed) + ".bin", "size_bytes": len(compressed)},
        "receipt": {"decoded_sha256": _sha(master), "decoded_size_bytes": len(master), "master_receipt_sha256": parsed.receipt_sha256}}]})
    _file(spec.path, "report.json", report)
    _file(spec.path, "objects/" + _sha(compressed) + ".bin", compressed)
    commit = json.loads((spec.path / "commit.json").read_bytes());commit["report_sha256"] = _sha(report)
    commit_raw = _raw(commit);_file(spec.path, "commit.json", commit_raw)
    anchors = bootstrap.FixtureAnchors(_sha(inventory_raw), _sha(complete_raw), _sha(commit_raw), _sha(report),
        _sha(compressed), _sha(master), parsed.receipt_sha256)
    _, snapshot = _observe([spec])
    return {"root": tmp_path, "roots": (spec,), "master_root": spec.path,
        "audit_id": "ib-2006q1-parent-bootstrap-invented", "identity": lambda: {"source_sha256": {}},
        "anchors": anchors, "expected_snapshot_sha256": _sha(_raw(snapshot))}


def test_real_shape_offline_fixture_reconciles_all_forms_without_admission(tmp_path):
    kwargs = _fixture(tmp_path)
    result = bootstrap.run_fixture_bootstrap(**kwargs)
    output = tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"])
    receipt = json.loads((output / "complete.json").read_bytes())
    accounting = json.loads((output / "locator-accounting.json").read_bytes())
    assert result["counts"] == {"source_filings": 6, "fresh_locator_count": 2, "selected_prefix": 2, "global_exposed_accessions": 0}
    assert receipt["fixture_only"] is True and receipt["effective_process_tree_network_denial"] is True
    assert receipt["effective_process_fork_denial"] is receipt["effective_outside_output_write_denial"] is False
    assert receipt["exposure_scope"] == "explicit_known_operational_roots_not_proof_of_no_unjournaled_access"
    assert all(value is False for value in receipt["authority"].values())
    assert all(value is False for value in accounting["authority"].values())
    assert accounting["source_filings"] == 6
    assert accounting["counts"]["context_filings"] == 4
    assert [row["source_record_ordinal"] for row in accounting["filing_accounting"]] == list(range(1, 7))
    assert accounting["maximum_prefix"] == 64
    assert set(p.name for p in output.iterdir()) == {"complete.json", "exposure.json", "exposure-snapshot.json", "locator-accounting.json"}
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in output.iterdir())


@pytest.mark.parametrize("field", list(bootstrap.FixtureAnchors.__dataclass_fields__))
def test_all_independent_source_anchors_are_required_and_mismatch_preserves_output(tmp_path, field):
    kwargs = _fixture(tmp_path)
    kwargs["anchors"] = replace(kwargs["anchors"], **{field: "f" * 64})
    with pytest.raises((bootstrap.ParentBootstrapError, bootstrap.locators.ParentLocatorError)):
        bootstrap.run_fixture_bootstrap(**kwargs)
    output = tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"])
    assert output.is_dir() and list(output.iterdir()) == []


def test_external_global_exposure_snapshot_is_not_self_attested(tmp_path):
    kwargs = _fixture(tmp_path);kwargs["expected_snapshot_sha256"] = "f" * 64
    with pytest.raises(bootstrap.ParentBootstrapError, match="external_exposure_snapshot_hash"):
        bootstrap.run_fixture_bootstrap(**kwargs)


def test_output_is_exclusive_cannot_resume_or_replace_completed_fixture(tmp_path):
    kwargs = _fixture(tmp_path)
    bootstrap.run_fixture_bootstrap(**kwargs)
    output = tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"])
    previous = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(bootstrap.custody.ArchiveAssessmentRunnerError, match="cannot_resume_or_overwrite"):
        bootstrap.run_fixture_bootstrap(**kwargs)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == previous


def test_fixture_route_refuses_any_real_root_before_output(tmp_path):
    kwargs = _fixture(tmp_path)
    kwargs["roots"] = (bootstrap.RootSpec("real-root", bootstrap.custody.LANE_ROOT, "simple-jsonl"),)
    with pytest.raises(bootstrap.ParentBootstrapError, match="fixture_root_only"):
        bootstrap.run_fixture_bootstrap(**kwargs)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{}  ', b'[]', b'\xff'])
def test_source_json_duplicate_nonfinite_and_noncanonical_refusal_sanitized(raw):
    with pytest.raises(bootstrap.ParentBootstrapError) as exc:
        bootstrap._json(raw)
    assert "x" not in str(exc.value)


def test_output_publication_byte_bound_and_exclusive(tmp_path):
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        with pytest.raises(bootstrap.ParentBootstrapError, match="output_byte_bound"):
            bootstrap._publish(fd, "out.json", b"long", 1)
        bootstrap._publish(fd, "out.json", b"{}", 2)
        with pytest.raises(FileExistsError):
            bootstrap._publish(fd, "out.json", b"[]", 2)
        assert (tmp_path / "out.json").read_bytes() == b"{}"
    finally:
        os.close(fd)


def _identity():
    inventory = {name: "a" * 64 for name in (
        "research/insider_buying_sec_2006q1_parent_bootstrap.py", "research/insider_buying_sec_2006q1_parent_locators.py",
        "research/insider_buying/sec_quarter_master_index.py", "research/insider_buying/sec_edgar_acceptance_snapshot.py")}
    return {"root": str(bootstrap.custody.LANE_ROOT), "branch": bootstrap.custody.LANE_BRANCH, "head": "a" * 40,
            "clean": True, "source_sha256": inventory, "source_inventory_sha256": _sha(_raw(inventory))}


@pytest.mark.parametrize("mutation", ["root", "branch", "head", "clean", "source_inventory_sha256", "source_sha256"])
def test_worker_identity_cannot_skip_current_source_self_and_import_closure(mutation):
    identity = _identity();identity[mutation] = {} if mutation == "source_sha256" else False
    with pytest.raises(bootstrap.ParentBootstrapError, match="parent_identity_refused"):
        bootstrap._required_identity(identity, "a" * 40)


@pytest.mark.parametrize("value", ["../bad", "ib-2006q1-parent-bootstrap-", "ib-2006q1-parent-bootstrap-x/y", True])
def test_exact_fresh_audit_id_required(value):
    with pytest.raises(bootstrap.ParentBootstrapError, match="audit_id_refused"):
        bootstrap._id(value)


def test_actual_worker_profile_denies_tree_network_fork_and_limits_output_writes(tmp_path):
    # macOS refuses a nested sandbox_apply from an already sandboxed pytest.
    # The measured production-profile probe is therefore a separate isolated
    # invocation. This regression still binds its exact profile construction.
    output = tmp_path / "fresh"
    profile = bootstrap.custody._policy(output)
    assert "(deny network*)" in profile and "(deny process-fork)" in profile
    assert "(deny file-write*)" in profile
    assert '(allow file-write* (subpath ' + json.dumps(str(output)) + '))' in profile


def _verify_fixture(kwargs, observed):
    return bootstrap._verify_publication(root=kwargs["root"], audit_id=kwargs["audit_id"], identity=kwargs["identity"](),
        expected_snapshot_sha256=kwargs["expected_snapshot_sha256"], observed=observed, fixture_only=True)


def test_parent_reopens_and_verifies_every_output_file(tmp_path):
    kwargs = _fixture(tmp_path);observed = bootstrap.run_fixture_bootstrap(**kwargs)
    _verify_fixture(kwargs, observed)
    output = tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"])
    _file(output, "unregistered.json", b"{}")
    with pytest.raises(bootstrap.ParentBootstrapError, match="output_inventory"):
        _verify_fixture(kwargs, observed)


@pytest.mark.parametrize("mutation", ["receipt", "locator", "snapshot", "exposure"])
def test_parent_rejects_changed_output_bytes(tmp_path, mutation):
    kwargs = _fixture(tmp_path);observed = bootstrap.run_fixture_bootstrap(**kwargs)
    name = {"receipt": "complete.json", "locator": "locator-accounting.json", "snapshot": "exposure-snapshot.json", "exposure": "exposure.json"}[mutation]
    output = tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"])
    (output / name).write_bytes(b"{}")
    with pytest.raises(bootstrap.ParentBootstrapError):
        _verify_fixture(kwargs, observed)


@pytest.mark.parametrize("mutation", ["identity", "network", "fork", "outside", "financial", "authority", "counts", "external_snapshot", "plans"])
def test_parent_does_not_accept_self_rehashed_false_receipt_claims(tmp_path, mutation):
    kwargs = _fixture(tmp_path);observed = bootstrap.run_fixture_bootstrap(**kwargs)
    output = tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"])
    receipt = json.loads((output / "complete.json").read_bytes())
    if mutation == "identity":
        receipt["execution_identity"] = {}
    elif mutation == "network":
        receipt["effective_process_tree_network_denial"] = False
    elif mutation in {"fork", "outside"}:
        key = "effective_process_fork_denial" if mutation == "fork" else "effective_outside_output_write_denial"
        receipt[key] = True  # The fixture cannot pretend it observed actual isolation.
    elif mutation == "financial":
        receipt["parent_financial_bodies_decoded"] = True
    elif mutation == "authority":
        receipt["authority"]["backtesting_ready"] = True
    elif mutation == "counts":
        receipt["counts"]["source_filings"] = True;observed["counts"] = receipt["counts"]
    elif mutation == "external_snapshot":
        receipt["expected_exposure_snapshot_sha256"] = "f" * 64
    else:
        receipt["plans_are_dispatch_evidence"] = True
    raw = _raw(receipt);(output / "complete.json").write_bytes(raw);observed["complete_sha256"] = _sha(raw)
    with pytest.raises(bootstrap.ParentBootstrapError):
        _verify_fixture(kwargs, observed)


def test_counts_only_worker_summary_rejects_unregistered_extra_fields(tmp_path):
    kwargs = _fixture(tmp_path);observed = bootstrap.run_fixture_bootstrap(**kwargs)
    observed["unregistered_source_text"] = "INVENTED-SECRET-NEVER-LOG"
    with pytest.raises(bootstrap.ParentBootstrapError, match="binding_refused") as exc:
        _verify_fixture(kwargs, observed)
    assert "INVENTED" not in str(exc.value)


def test_parent_rejects_same_content_nonprivate_output_leaf(tmp_path):
    kwargs = _fixture(tmp_path);observed = bootstrap.run_fixture_bootstrap(**kwargs)
    output = tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"])
    (output / "complete.json").chmod(0o644)
    with pytest.raises(bootstrap.ParentBootstrapError, match="private_output_leaf"):
        _verify_fixture(kwargs, observed)


def _diagnostic(tmp_path, *, completed=False):
    root = tmp_path / "invented-diagnostic";root.mkdir(mode=0o700)
    manifest = _raw({"ambiguous_request_sha256": _sha(_raw(_request()))})
    start = _raw({"manifest_sha256": _sha(manifest), "started_utc": "2026-10-01T00:00:00Z"})
    _file(root, "manifest.json", manifest)
    _file(root, "attempt-start.json", start)
    if completed:
        report = _raw({"attempt_start_sha256": _sha(start), "manifest_sha256": _sha(manifest),
                       "finished_utc": "2026-10-01T00:00:01Z"})
        _file(root, "report.json", report)
        _file(root, "commit.json", _raw({"manifest_sha256": _sha(manifest), "report_name": "report.json", "report_sha256": _sha(report)}))
    return bootstrap.RootSpec("invented-diagnostic", root, "diagnostic")


@pytest.mark.parametrize("completed", [False, True])
def test_diagnostic_resolves_only_hash_bound_request_not_root_name(tmp_path, completed):
    plan = _simple(tmp_path, [{"kind": "pilot-finished"}], inventory={"requests": [_request()]})
    diagnostic = _diagnostic(tmp_path, completed=completed)
    exposure, snapshot = _observe([plan, diagnostic])
    assert len(exposure["records"]) == 1
    assert exposure["records"][0]["accession_number"] == _request()["accession_number"]
    assert exposure["records"][0]["evidence"][0]["root_id"] == "invented-diagnostic"
    assert len(snapshot["roots"][1]["pending_parent_accessions"]) == (0 if completed else 1)


def test_separate_completed_diagnostic_cannot_resolve_original_unmatched_start(tmp_path):
    original = _simple(tmp_path, [{"kind": "attempt-start", "ordinal": 1, "url": _request()["url"]}],
                       inventory={"requests": [_request()]})
    diagnostic = _diagnostic(tmp_path, completed=True)
    exposure, snapshot = _observe([original, diagnostic])
    assert len(exposure["records"]) == 1
    assert snapshot["roots"][0]["pending_parent_accessions"] == [_request()["accession_number"]]
    assert snapshot["roots"][1]["pending_parent_accessions"] == []
    assert any(e["root_id"] == original.root_id and e["state"] == "ambiguous" for e in exposure["records"][0]["evidence"])


def test_diagnostic_without_exact_historical_request_linkage_refuses(tmp_path):
    with pytest.raises(bootstrap.ParentBootstrapError, match="exact_request_linkage_missing"):
        _observe([_diagnostic(tmp_path)])


def test_public_result_boolean_zero_count_does_not_match_strict_receipt_integer(tmp_path):
    kwargs = _fixture(tmp_path);observed = bootstrap.run_fixture_bootstrap(**kwargs)
    output = tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"])
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    assert json.loads(before["complete.json"])["counts"]["global_exposed_accessions"] == 0
    observed["counts"]["global_exposed_accessions"] = False
    with pytest.raises(bootstrap.ParentBootstrapError, match="parent_counts_refused"):
        _verify_fixture(kwargs, observed)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


@pytest.mark.parametrize("mutation", ["negative", "missing", "extra", "float"])
def test_public_count_keys_types_and_nonnegative_bounds_are_exact(tmp_path, mutation):
    kwargs = _fixture(tmp_path);observed = bootstrap.run_fixture_bootstrap(**kwargs)
    if mutation == "missing":
        observed["counts"].pop("global_exposed_accessions")
    elif mutation == "extra":
        observed["counts"]["extra"] = 0
    else:
        observed["counts"]["global_exposed_accessions"] = -1 if mutation == "negative" else 0.0
    with pytest.raises(bootstrap.ParentBootstrapError, match="parent_counts_refused"):
        _verify_fixture(kwargs, observed)


@pytest.mark.parametrize("key", ["source_filings", "fresh_locator_count", "prior_exposure_input_records", "global_exposed_accessions"])
def test_scalar_accounting_and_snapshot_zero_cannot_be_boolean(key):
    accounting = {"source_filings": 0, "fresh_locator_count": 0, "prior_exposure_input_records": 0}
    snapshot = {"global_exposed_accessions": 0}
    bootstrap._typed_payload_counts(accounting, snapshot)
    (snapshot if key == "global_exposed_accessions" else accounting)[key] = False
    with pytest.raises(bootstrap.ParentBootstrapError, match="parent_payload_counts_refused"):
        bootstrap._typed_payload_counts(accounting, snapshot)


@pytest.mark.parametrize("finish_second", [False, True])
def test_overlapping_same_accession_ordinals_cannot_erase_unmatched_start(tmp_path, finish_second):
    events = [
        {"kind": "attempt-start", "ordinal": 1, **_request()},
        {"kind": "attempt-start", "ordinal": 2, **_request()},
        {"kind": "attempt-finish", "ordinal": 1, "accession_number": _request()["accession_number"]},
    ]
    if finish_second:
        events.append({"kind": "attempt-finish", "ordinal": 2, "accession_number": _request()["accession_number"]})
    spec = _chain(tmp_path, events)
    before = {path.name: path.read_bytes() for path in spec.path.iterdir()}
    exposure, snapshot = _observe([spec])
    assert snapshot["roots"][0]["pending_parent_accessions"] == ([] if finish_second else [_request()["accession_number"]])
    assert snapshot["roots"][0]["consumed_start_records"] == 2
    assert snapshot["roots"][0]["terminal_records"] == (2 if finish_second else 1)
    assert {item["state"] for item in exposure["records"][0]["evidence"]} == ({"started"} if finish_second else {"started", "ambiguous"})
    assert {path.name: path.read_bytes() for path in spec.path.iterdir()} == before


def test_sequential_same_accession_history_remains_consumed_without_pending(tmp_path):
    spec = _chain(tmp_path, [
        {"kind": "attempt-start", "ordinal": 1, **_request()},
        {"kind": "attempt-finish", "ordinal": 1, "accession_number": _request()["accession_number"]},
        {"kind": "attempt-start", "ordinal": 2, **_request()},
        {"kind": "attempt-finish", "ordinal": 2, "accession_number": _request()["accession_number"]},
    ])
    exposure, snapshot = _observe([spec])
    assert len(exposure["records"]) == 1
    assert snapshot["roots"][0]["consumed_start_records"] == 2
    assert snapshot["roots"][0]["terminal_records"] == 2
    assert snapshot["roots"][0]["pending_parent_accessions"] == []


@pytest.mark.parametrize("alias", ["literal", "case", "ancestor"])
def test_fixture_actual_lane_alias_refused_before_output_identity_or_worker(tmp_path, monkeypatch, alias):
    kwargs = _fixture(tmp_path)
    actual = bootstrap.custody.LANE_ROOT
    root = actual if alias == "literal" else actual.parent if alias == "ancestor" else actual.with_name(actual.name.upper())
    if alias == "case" and (not root.exists() or not root.samefile(actual)):
        pytest.skip("case alias requires case-insensitive filesystem")
    kwargs.update(root=root, roots=(), master_root=root / "never-opened-master",
        identity=lambda: pytest.fail("identity callback must not run"))
    monkeypatch.setattr(bootstrap.custody, "_Chain", lambda *a, **k: pytest.fail("output/source must not open"))
    monkeypatch.setattr(bootstrap, "_worker", lambda **k: pytest.fail("worker must not run"))
    with pytest.raises(bootstrap.ParentBootstrapError, match="fixture_root_only_required"):
        bootstrap.run_fixture_bootstrap(**kwargs)


@pytest.mark.parametrize("attack", ["external_master", "symlink_exposure", "actual_custody_root"])
def test_fixture_external_input_aliases_refused_before_output_or_callbacks(tmp_path, monkeypatch, attack):
    kwargs = _fixture(tmp_path)
    if attack == "external_master":
        kwargs["master_root"] = bootstrap.custody.LANE_ROOT.parent.joinpath(*bootstrap.MASTER_ROOT_PARTS)
    elif attack == "symlink_exposure":
        alias = tmp_path / "invented-exposure-alias"; alias.symlink_to(bootstrap.custody.LANE_ROOT, target_is_directory=True)
        kwargs["roots"] = (bootstrap.RootSpec("invented-alias", alias, "simple-jsonl"),)
        kwargs["master_root"] = alias
    else:
        real = bootstrap.custody.LANE_ROOT.parent.joinpath(*bootstrap.MASTER_ROOT_PARTS)
        kwargs.update(root=real, roots=(bootstrap.RootSpec("invented-real-master", real, "event-chain"),), master_root=real)
    kwargs["identity"] = lambda: pytest.fail("identity callback must not run")
    monkeypatch.setattr(bootstrap.custody, "_Chain", lambda *a, **k: pytest.fail("output/source must not open"))
    monkeypatch.setattr(bootstrap, "_worker", lambda **k: pytest.fail("worker must not run"))
    with pytest.raises(bootstrap.ParentBootstrapError, match="fixture_root_only_required"):
        bootstrap.run_fixture_bootstrap(**kwargs)


def test_publication_disk_floor_refuses_before_worker_inputs_or_callback(tmp_path, monkeypatch):
    kwargs = _fixture(tmp_path)
    class Info:
        f_frsize = 1
        f_bavail = 4 * 1024**3 + 512 * 1024**2 - 1
    monkeypatch.setattr(bootstrap.os, "fstatvfs", lambda fd: Info())
    kwargs["identity"] = lambda: pytest.fail("resource refusal must precede identity callback")
    monkeypatch.setattr(bootstrap, "_worker", lambda **k: pytest.fail("resource refusal must precede source inputs"))
    with pytest.raises(bootstrap.ParentBootstrapError, match="publication_disk_reserve_insufficient"):
        bootstrap.run_fixture_bootstrap(**kwargs)


def test_publication_finite_reserve_passes_exact_boundary_and_refuses_one_byte_short(tmp_path, monkeypatch):
    class Info:
        f_frsize = 1
        f_bavail = 4 * 1024**3 + 512 * 1024**2
    class Output:
        fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        def recheck(self): pass
    monkeypatch.setattr(bootstrap.os, "fstatvfs", lambda fd: Info())
    output = Output()
    try:
        observed = bootstrap._publication_disk_reserve(output)
        assert observed == {"maximum_publication_bytes": 512 * 1024**2,
            "minimum_remaining_free_bytes": 4 * 1024**3, "available_bytes_at_preflight": Info.f_bavail}
        bootstrap._verify_disk_receipt(observed)
        Info.f_bavail -= 1
        with pytest.raises(bootstrap.ParentBootstrapError, match="publication_disk_reserve_insufficient"):
            bootstrap._publication_disk_reserve(output)
    finally: os.close(output.fd)


@pytest.mark.parametrize("block_size,available", [(True, 2**64), (0, 2**64), (-1, 2**64),
    (1, True), (1, -1), (1.0, 2**64), (1, 5.0)])
def test_publication_resource_stats_are_exact_nonnegative_integers(tmp_path, monkeypatch, block_size, available):
    class Info:
        f_frsize = block_size
        f_bavail = available
    class Output:
        fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        def recheck(self): pass
    monkeypatch.setattr(bootstrap.os, "fstatvfs", lambda fd: Info())
    output = Output()
    try:
        with pytest.raises(bootstrap.ParentBootstrapError, match="publication_disk_stat_refused"):
            bootstrap._publication_disk_reserve(output)
    finally: os.close(output.fd)


def test_disk_rechecked_before_first_publication_after_source_inputs(tmp_path, monkeypatch):
    kwargs = _fixture(tmp_path); calls = [0]
    class Info:
        f_frsize = 1
        f_bavail = 4 * 1024**3 + 512 * 1024**2
    def capacity(fd):
        calls[0] += 1
        result = Info()
        if calls[0] >= 3: result.f_bavail -= 1
        return result
    monkeypatch.setattr(bootstrap.os, "fstatvfs", capacity)
    with pytest.raises(bootstrap.ParentBootstrapError, match="publication_disk_reserve_insufficient"):
        bootstrap.run_fixture_bootstrap(**kwargs)
    assert calls[0] == 3
    assert list(tmp_path.joinpath(*bootstrap.OUTPUT_PARTS, kwargs["audit_id"]).iterdir()) == []


@pytest.mark.parametrize("key", ["maximum_publication_bytes", "minimum_remaining_free_bytes", "available_bytes_at_preflight"])
def test_parent_resource_receipt_rejects_boolean_integer_equivalence(key):
    receipt = {"maximum_publication_bytes": 512 * 1024**2, "minimum_remaining_free_bytes": 4 * 1024**3,
        "available_bytes_at_preflight": 4 * 1024**3 + 512 * 1024**2}
    receipt[key] = True
    with pytest.raises(bootstrap.ParentBootstrapError, match="publication_disk_receipt_refused"):
        bootstrap._verify_disk_receipt(receipt)


def test_direct_private_fixture_worker_cannot_skip_real_root_fence(tmp_path, monkeypatch):
    kwargs = _fixture(tmp_path)
    kwargs.update(root=bootstrap.custody.LANE_ROOT, roots=(), master_root=bootstrap.custody.LANE_ROOT,
                  identity={})
    monkeypatch.setattr(bootstrap, "_pre_input_disk_reserve", lambda *a: pytest.fail("output preflight must not run"))
    with pytest.raises(bootstrap.ParentBootstrapError, match="fixture_root_only_required"):
        bootstrap._worker(**kwargs, fixture_only=True)


def test_full_disk_reserve_precedes_every_one_of_four_publications(tmp_path, monkeypatch):
    kwargs = _fixture(tmp_path); reserves, publications = [], []
    reserve, publish = bootstrap._publication_disk_reserve, bootstrap._publish
    def reserved(output):
        observed = reserve(output); reserves.append(len(publications)); return observed
    def published(fd, name, raw, cap):
        assert reserves[-1] == len(publications)
        publications.append(name)
        return publish(fd, name, raw, cap)
    monkeypatch.setattr(bootstrap, "_publication_disk_reserve", reserved)
    monkeypatch.setattr(bootstrap, "_publish", published)
    bootstrap.run_fixture_bootstrap(**kwargs)
    assert publications == ["exposure.json", "exposure-snapshot.json", "locator-accounting.json", "complete.json"]
    assert reserves == [0, 0, 0, 1, 2, 3]
