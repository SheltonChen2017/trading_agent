"""Invented retained inputs only, under effective process-tree native denial."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: macOS/POSIX custody support", allow_module_level=True)

from research import insider_buying_pilot_massive_evidence_readback_v1 as m

HEAD = "a" * 40
TOKEN = "invented_only_massive_readback_key+/!"
p = m.producer


def _body(ordinal):
    if ordinal == 1:
        row = {"ticker": "AAPL", "cik": "0000320193", "locale": "us", "market": "stocks", "active": True,
            "name": "Invented issuer", "type": "CS", "primary_exchange": "XNAS", "share_class_figi": "BBG000B9XRY4",
            "last_updated_utc": "2026-10-20T00:00:00Z"}
    else:
        accession = "0000320193-20-000099" if ordinal == 2 else "0000320193-20-000101"
        row = {"accession_number": accession, "cik": "0000320193", "form_type": "4", "filing_date": "2020-10-08",
            "filing_url": "https://www.sec.gov/Archives/edgar/data/320193/" + accession + ".txt", "issuer_name": "Invented issuer"}
        if ordinal == 2:
            row["ticker"] = "AAPL"
        else:
            row["issuer_cik"] = row.pop("cik")
            row.update(tickers=["AAPL"], transaction_value=123456.125, transaction_shares=50,
                transaction_price_per_share=2469.1225, transaction_date="2020-10-07", owner_cik="0000000001",
                aff_10b5_one=False, date_of_original_submission=None,
                footnotes=[{"id": "F1", "description": "Invented source note"}])
    return {"status": "OK", "request_id": "invented", "results": [row]}


def _capture(root, *, stop=False):
    sources = {"invented.py": "b" * 64}
    identity = {"root": str(root), "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}
    def transport(url, credential):
        ordinal = next(i for i, (_, expected) in enumerate(p.REQUESTS, 1) if url == expected)
        raw = m._raw(_body(ordinal))
        return p.prior.date_probe.ProviderMetadataResponse(403 if stop else 200, raw, True)
    p.run_probe(HEAD, root=root, identity=lambda head, root: deepcopy(identity),
        credential_reader=lambda _: p.prior.KeychainCredential("massive", TOKEN, True), transport=transport,
        clock=lambda: "2026-10-27T00:00:00Z")
    return _pin(root)


def _directory(root):
    return root.joinpath(*p.OUTPUT_PARTS, p.AUDIT_ID)


def _pin(root):
    return m._sha((_directory(root) / "complete.json").read_bytes())


def _read(root, pin=None):
    return m.read_invented(root, complete_sha256=pin or _pin(root))


def _json(path):
    return json.loads(path.read_bytes())


def _write(path, value):
    path.write_bytes(m._raw(value))


def _refresh(root, change=None):
    """Refresh only untrusted outer links so inner guards must detect damage."""
    directory = _directory(root)
    final = _json(directory / "complete.json")
    final["published_leaf_sha256"] = {name: m._sha((directory / name).read_bytes()) for name in sorted(m._NAMES - {"complete.json"})}
    final["scope_reservation_sha256"] = m._sha((directory.parent / "scope-reservation.json").read_bytes())
    final["results"] = [_json(directory / f"{i:02d}-completed.json") for i in range(1, 4)]
    if change:
        change(final)
    _write(directory / "complete.json", final)
    return _pin(root)


def _snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
        for path in root.rglob("*") if path.is_file()}


def test_complete_custody_schema_readback_is_readonly_and_not_key_or_provider_replay(tmp_path, monkeypatch):
    pin = _capture(tmp_path)
    before = _snapshot(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("readback must not acquire, read a key or invent a key privacy replay")
    for obj, name in ((p, "run_probe"), (p, "_default_transport"), (p.prior, "read_keychain_credential"),
                      (p.prior, "_screen_credential"), (p, "_projection")):
        monkeypatch.setattr(obj, name, forbidden)
    result = _read(tmp_path, pin)
    assert result["private_leaves_revalidated"] == 17 and result["retained_success_bodies"] == 3
    assert result["producer_journal_transport_invocations"] == 3
    assert result["retained_success_body_bytes"] == sum(len(m._raw(_body(i))) for i in range(1, 4))
    assert result["fixture_only"] is True and result["complete_sha256"] == pin
    assert result["producer_head"] == HEAD
    assert result["new_requests"] == result["credential_reads"] == result["qc_jobs"] == result["outcome_looks"] == result["backtests"] == 0
    assert result["current_key_privacy_rescreened"] is result["historical_code_executed"] is False
    assert all(result[flag] is False for flag in p.FALSE_FLAGS)
    assert set(result).isdisjoint({"producer_identity", "source_identity", "results", "identity"})
    assert b"0000320193-20-000099" not in m._raw(result) and b"123456" not in m._raw(result)
    assert _snapshot(tmp_path) == before


def test_wrong_external_complete_pin_stops_before_any_success_body(tmp_path, monkeypatch):
    _capture(tmp_path)
    original = m.publication._leaf
    def no_body(fd, name, cap):
        assert not name.endswith("-response.json")
        return original(fd, name, cap)
    monkeypatch.setattr(m.publication, "_leaf", no_body)
    with pytest.raises(m.MassiveReadbackError, match="controls_refused"):
        _read(tmp_path, "c" * 64)


@pytest.mark.parametrize("field,value", [("planned_requests", True), ("transport_invocation_count", 2),
    ("unattempted_requests", False), ("credential_read_observed", False), ("fixture_only", False),
    ("status", "stopped-capability-probe"), ("current_extra_field", False), ("historical_public_known_by_verified", True),
    ("completed_at_utc", "not-a-clock")])
def test_rehashed_terminal_cannot_invent_counts_authority_scope_or_completion(tmp_path, field, value):
    _capture(tmp_path)
    pin = _refresh(tmp_path, lambda final: final.__setitem__(field, value))
    with pytest.raises(m.MassiveReadbackError):
        _read(tmp_path, pin)


@pytest.mark.parametrize("name,field,value", [("credential-read-started.json", "maximum_credential_reads", True),
    ("credential-read-completed.json", "credential_read_observed", False),
    ("credential-read-completed.json", "started_sha256", "d" * 64),
    ("02-started.json", "ordinal", 1), ("03-started.json", "reservation_sha256", "e" * 64),
    ("02-metadata.json", "result_count", True), ("03-metadata.json", "historical_body_version_verified", True),
    ("01-completed.json", "http_status", 403), ("02-completed.json", "body_size_bytes", True),
    ("03-completed.json", "untrusted_error_body_hashed_or_retained", True)])
def test_rehashed_inner_journals_metadata_and_start_crosslinks_still_refuse(tmp_path, name, field, value):
    _capture(tmp_path)
    path = _directory(tmp_path) / name
    value_before = _json(path)
    value_before[field] = value
    _write(path, value_before)
    with pytest.raises(m.MassiveReadbackError):
        _read(tmp_path, _refresh(tmp_path))


@pytest.mark.parametrize("raw", [b'{"schema":"x","schema":"x"}', b'{"value":NaN}', b'{"schema": "spaced"}', b'[]'])
def test_duplicate_nonfinite_and_noncanonical_controls_refuse(tmp_path, raw):
    _capture(tmp_path)
    (_directory(tmp_path) / "credential-read-started.json").write_bytes(raw)
    with pytest.raises(m.MassiveReadbackError):
        _read(tmp_path, _refresh(tmp_path))


@pytest.mark.parametrize("ordinal,change", [(1, lambda body: body["results"][0].update(cik="999")),
    (2, lambda body: body["results"][0].update(filing_date="2021-01-01")),
    (3, lambda body: body["results"][0].update(transaction_shares="50")),
    (3, lambda body: body["results"][0].update(unknown_financial_field=123)),
    (2, lambda body: body.update(count=True)),
    (2, lambda body: body.update(next_url="https://foreign.invalid/stocks/filings/vX/index?cursor=x")),
    (2, lambda body: body.update(next_url="https://api.massive.com:bad/stocks/filings/vX/index?cursor=x"))])
def test_current_schema_projection_refuses_wrong_identity_dates_types_and_cursor(ordinal, change):
    body = _body(ordinal)
    change(body)
    with pytest.raises(m.MassiveReadbackError, match="projection_refused"):
        m._project(m._raw(body), ordinal)


def test_opaque_numbers_stay_opaque_and_differing_discovery_accessions_are_valid():
    raw = m._raw(_body(3)).replace(b'"transaction_value":123456.125', b'"transaction_value":1e999')
    result = m._project(raw, 3)
    assert result["numeric_financial_fields_interpreted"] is False
    assert b"1e999" not in m._raw(result)
    assert m._project(m._raw(_body(2)), 2)["source_identity"]["accession_number"] != result["source_identity"]["accession_number"]


@pytest.mark.parametrize("mutation", ["missing", "extra", "symlink", "hardlink", "mode", "directory_mode", "scope"])
def test_exact_private_inventory_and_modes_links_are_binding(tmp_path, mutation):
    pin = _capture(tmp_path)
    directory = _directory(tmp_path)
    leaf = directory / "02-response.json"
    if mutation == "missing": leaf.unlink()
    elif mutation == "extra": (directory / "foreign.json").write_bytes(b"{}")
    elif mutation == "symlink":
        saved = tmp_path / "saved-body"
        leaf.rename(saved)
        leaf.symlink_to(saved)
    elif mutation == "hardlink": os.link(leaf, tmp_path / "linked-body")
    elif mutation == "mode": leaf.chmod(0o644)
    elif mutation == "directory_mode": directory.chmod(0o755)
    else:
        scope = directory.parent / "scope-reservation.json"
        value = _json(scope)
        value["maximum_attempts"] = 4
        _write(scope, value)
    with pytest.raises(m.MassiveReadbackError):
        _read(tmp_path, pin)


@pytest.mark.parametrize("mutation", ["bytes_with_restored_mtime", "inode", "directory"])
def test_changes_after_first_read_refuse_at_final_held_recheck(tmp_path, monkeypatch, mutation):
    pin = _capture(tmp_path)
    directory = _directory(tmp_path)
    original, changed = m.publication._leaf, False
    def raced(fd, name, cap):
        nonlocal changed
        value = original(fd, name, cap)
        if name == "02-response.json" and not changed:
            changed = True
            leaf = directory / name
            info = leaf.stat()
            if mutation == "bytes_with_restored_mtime":
                leaf.write_bytes(value[0].replace(b"Invented issuer", b"Tampered issuer"))
                os.utime(leaf, ns=(info.st_atime_ns, info.st_mtime_ns))
            elif mutation == "inode":
                leaf.rename(tmp_path / "original-body-inode-held")
                leaf.write_bytes(value[0])
                leaf.chmod(0o600)
                os.utime(leaf, ns=(info.st_atime_ns, info.st_mtime_ns))
            else:
                old = directory.parent / "old-directory"
                directory.rename(old)
                shutil.copytree(old, directory)
        return value
    monkeypatch.setattr(m.publication, "_leaf", raced)
    with pytest.raises(m.MassiveReadbackError, match="retained_custody_refused"):
        _read(tmp_path, pin)
    assert changed


def test_stopped_capture_cannot_be_relabelled_as_completed_readback(tmp_path):
    pin = _capture(tmp_path, stop=True)
    with pytest.raises(m.MassiveReadbackError):
        _read(tmp_path, pin)


@pytest.mark.parametrize("root", [m.LANE_ROOT, m.LANE_ROOT.parent, m.LANE_ROOT / "child"])
def test_invented_surface_never_opens_lane_or_ancestor(root, monkeypatch):
    monkeypatch.setattr(m, "_Held", lambda *_: pytest.fail("must refuse before custody opens"))
    with pytest.raises(m.MassiveReadbackError, match="arguments_refused"):
        m.read_invented(root, complete_sha256="a" * 64)


def test_actual_surface_rejects_foreign_root_before_open(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_Held", lambda *_: pytest.fail("must refuse before custody opens"))
    with pytest.raises(m.MassiveReadbackError, match="arguments_refused"):
        m._readback(tmp_path, m.COMPLETE_SHA256, fixture=False)


def test_actual_command_is_fixed_isolated_and_native_readonly_without_credentials():
    identity = {"head": HEAD}
    command = m._command(identity)
    assert command[:3] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin")
    assert "/usr/bin/sandbox-exec" in command
    policy = command[command.index("-p") + 1]
    for rule in ("(deny network*)", "(deny process-fork)", "(deny file-write*)", '(deny process-exec (literal "/usr/bin/security"))'):
        assert rule in policy
    assert all(flag in command for flag in ("-I", "-S", "-B", "-X", "pycache_prefix=" + m.EMPTY_CACHE_PREFIX))
    assert "m._worker(identity,role=\'readback\')" in command[-1]
    assert TOKEN not in repr(command)


def test_final_git_and_public_receipt_validation_is_not_an_identity_self_assertion(monkeypatch):
    sources = {f"source{i}.py": "b" * 64 for i in range(50)}
    old = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": m.PRODUCER_HEAD, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}
    monkeypatch.setattr(m, "PRODUCER_INVENTORY", old["source_inventory_sha256"])
    identity = {"current": True}
    monkeypatch.setattr(m, "_identity", lambda _: deepcopy(identity))
    receipt = m._receipt(old, m.COMPLETE_SHA256, False, m.OBSERVED_TOTAL_BYTES)
    monkeypatch.setattr(m, "_launch", lambda *args, **kw: {"ok": True, "value": {"producer_identity": old, "receipt": receipt}})
    monkeypatch.setattr(m.custody, "_git", lambda *_: b"foreign Git bytes")
    with pytest.raises(m.MassiveReadbackError, match="producer_identity_refused"):
        m.verify_actual(expected_head=HEAD)


def test_extra_leaf_cannot_be_adopted_between_initial_inventory_and_saved_baseline(tmp_path, monkeypatch):
    pin = _capture(tmp_path)
    original, calls = m.os.listdir, 0
    def raced(fd):
        nonlocal calls
        calls += 1
        if calls == 3:
            path = _directory(tmp_path).parent / "foreign.json"
            path.write_bytes(b"{}")
            path.chmod(0o600)
        return original(fd)
    monkeypatch.setattr(m.os, "listdir", raced)
    with pytest.raises(m.MassiveReadbackError, match="retained_custody_refused"):
        _read(tmp_path, pin)
    assert calls >= 3


def test_inventory_is_rechecked_after_last_leaf_hash_not_only_before_it(tmp_path, monkeypatch):
    pin = _capture(tmp_path)
    original, reads = m.publication._leaf, 0
    def raced(fd, name, cap):
        nonlocal reads
        value = original(fd, name, cap)
        if name == "reservation.json":
            reads += 1
            if reads == 2:
                extra = _directory(tmp_path).parent / "late-foreign.json"
                extra.write_bytes(b"{}")
                extra.chmod(0o600)
        return value
    monkeypatch.setattr(m.publication, "_leaf", raced)
    with pytest.raises(m.MassiveReadbackError, match="retained_custody_refused"):
        _read(tmp_path, pin)
    assert reads == 2


def _fake_parent(monkeypatch):
    historical = b"invented historical Git image"
    sources = {f"source{i}.py": m._sha(historical) for i in range(50)}
    old = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": m.PRODUCER_HEAD, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}
    current_sources = {"current.py": "d" * 64}
    current = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
        "source_sha256": current_sources, "source_inventory_sha256": m._sha(m._raw(current_sources))}
    monkeypatch.setattr(m, "PRODUCER_INVENTORY", old["source_inventory_sha256"])
    monkeypatch.setattr(m, "_identity", lambda _: deepcopy(current))
    receipt = m._receipt(old, m.COMPLETE_SHA256, False, m.OBSERVED_TOTAL_BYTES)
    result = {"ok": True, "value": {"producer_identity": old, "receipt": receipt}}
    monkeypatch.setattr(m, "_launch", lambda *args, **kw: deepcopy(result))
    calls = []
    def git(root, command, image):
        assert root == m.LANE_ROOT and command == "show" and image.startswith(m.PRODUCER_HEAD + ":source")
        calls.append(image)
        return historical
    monkeypatch.setattr(m.custody, "_git", git)
    return result, old, current, calls


def test_parent_verifies_every_historical_git_image_and_emits_no_private_identity(monkeypatch):
    result, old, current, calls = _fake_parent(monkeypatch)
    receipt = m.verify_actual(expected_head=HEAD)
    assert len(calls) == 50
    assert receipt["readback_head"] == HEAD and receipt["producer_head"] == m.PRODUCER_HEAD
    assert receipt["readback_source_inventory_sha256"] == current["source_inventory_sha256"]
    assert receipt["readback_source_images"] == 1
    assert receipt["producer_journal_credential_reads"] == 1 and receipt["credential_reads"] == 0
    assert receipt["current_key_privacy_rescreened"] is receipt["original_key_privacy_screen_reexecuted"] is False
    assert not any(key in receipt for key in ("producer_identity", "identity", "source_sha256", "source_identity"))


@pytest.mark.parametrize("field,value", [("retained_success_bodies", True), ("retained_success_body_bytes", 1),
    ("credential_reads", 1), ("historical_public_known_by_verified", True), ("current_key_privacy_rescreened", True),
    ("extra", False)])
def test_parent_rejects_malformed_or_authority_promoting_worker_receipt(monkeypatch, field, value):
    result, _, _, _ = _fake_parent(monkeypatch)
    result["value"]["receipt"][field] = value
    with pytest.raises(m.MassiveReadbackError):
        m.verify_actual(expected_head=HEAD)


def test_parent_rechecks_current_identity_after_historical_verification(monkeypatch):
    _, _, current, _ = _fake_parent(monkeypatch)
    calls = 0
    def changing(_):
        nonlocal calls
        calls += 1
        value = deepcopy(current)
        if calls == 2:
            value["head"] = "f" * 40
        return value
    monkeypatch.setattr(m, "_identity", changing)
    with pytest.raises(m.MassiveReadbackError, match="controls_refused"):
        m.verify_actual(expected_head=HEAD)
    assert calls == 2


def test_worker_proves_native_denial_before_inputs_and_guards_through_stdout(monkeypatch):
    events = []
    class Guard:
        def __init__(self): events.append("guard-start")
        def check(self): events.append("sample")
        def close(self): events.append("guard-close")
    class Buffer:
        def write(self, raw):
            events.append("stdout-write")
            assert raw.endswith(b"\n")
        def flush(self): events.append("stdout-flush")
    class Stdout:
        buffer = Buffer()
    def readback(*args, **kwargs):
        events.append("inputs")
        assert events.index("native-proof") < events.index("guard-start") < events.index("inputs")
        return {"producer_identity": {"invented": True}, "receipt": {"invented": True}}
    original_raw = m._raw
    def raw(value):
        events.append("serialization")
        return original_raw(value)
    monkeypatch.setattr(m.native, "_isolated", lambda: events.append("flags"))
    monkeypatch.setattr(m.native.batch.campaign.base, "_prove_isolation", lambda: events.append("native-proof"))
    monkeypatch.setattr(m.native, "_WorkerMemoryGuard", Guard)
    monkeypatch.setattr(m, "_current", lambda _: events.append("current"))
    monkeypatch.setattr(m, "_readback", readback)
    monkeypatch.setattr(m, "_raw", raw)
    monkeypatch.setattr(m.sys, "stdout", Stdout())
    m._worker({"invented": True})
    assert events.index("inputs") < events.index("serialization") < events.index("stdout-write") < events.index("stdout-flush")
    assert events[-2:] == ["sample", "guard-close"]
    assert events.count("current") == 2 and events.count("sample") == 3


def test_worker_failed_native_proof_never_opens_private_inputs(monkeypatch):
    def refused(): raise m.MassiveReadbackError("native_refused")
    monkeypatch.setattr(m.native, "_isolated", lambda: None)
    monkeypatch.setattr(m.native.batch.campaign.base, "_prove_isolation", refused)
    monkeypatch.setattr(m.native, "_WorkerMemoryGuard", lambda: pytest.fail("no guard before proof"))
    monkeypatch.setattr(m, "_readback", lambda *args, **kwargs: pytest.fail("no inputs before proof"))
    with pytest.raises(m.MassiveReadbackError, match="native_refused"):
        m._worker({"invented": True})


@pytest.mark.parametrize("ordinal,field,value", [(2, "filing_date", "2021-01-01"),
    (2, "unknown_financial_field", 123), (3, "transaction_shares", "50")])
def test_rehashed_body_and_claimed_metadata_cannot_bypass_source_schema(tmp_path, ordinal, field, value):
    _capture(tmp_path)
    directory = _directory(tmp_path)
    prefix = f"{ordinal:02d}"
    body = _body(ordinal)
    body["results"][0][field] = value
    raw = m._raw(body)
    (directory / (prefix + "-response.json")).write_bytes(raw)
    metadata_path = directory / (prefix + "-metadata.json")
    metadata = _json(metadata_path)
    metadata["response_body_sha256"] = m._sha(raw)
    metadata["response_body_bytes"] = len(raw)
    metadata["row_field_names"] = sorted(body["results"][0])
    if field == "filing_date":
        metadata["source_identity"]["filing_date"] = value
    _write(metadata_path, metadata)
    completed_path = directory / (prefix + "-completed.json")
    completed = _json(completed_path)
    completed.update(metadata=metadata, body_sha256=m._sha(raw), body_size_bytes=len(raw))
    _write(completed_path, completed)
    with pytest.raises(m.MassiveReadbackError, match="projection_refused"):
        _read(tmp_path, _refresh(tmp_path))


@pytest.mark.parametrize("ordinal", [2, 3])
def test_recorded_cursor_is_not_reclassified_as_a_complete_source(ordinal):
    body = _body(ordinal)
    endpoint = p.REQUESTS[ordinal - 1][1].split("?", 1)[0]
    body["next_url"] = endpoint + "?cursor=invented"
    metadata = m._project(m._raw(body), ordinal)
    assert metadata["has_unfollowed_next_page"] is True
    assert metadata["full_pilot_coverage_verified"] is False
    assert metadata["historical_public_known_by_verified"] is False


def test_scope_mismatch_refuses_before_any_success_body(tmp_path, monkeypatch):
    _capture(tmp_path)
    pin = _refresh(tmp_path, lambda final: final.__setitem__("fixture_only", False))
    original = m.publication._leaf
    def no_body(fd, name, cap):
        assert not name.endswith("-response.json")
        return original(fd, name, cap)
    monkeypatch.setattr(m.publication, "_leaf", no_body)
    with pytest.raises(m.MassiveReadbackError, match="controls_refused"):
        _read(tmp_path, pin)


def test_runtime_health_worker_never_opens_inputs_and_keeps_guard_through_stdout(monkeypatch):
    events, output = [], bytearray()
    identity = {"head": HEAD, "source_inventory_sha256": "c" * 64, "source_sha256": {"invented.py": "d" * 64}}
    class Guard:
        def __init__(self): events.append("guard")
        def check(self): events.append("sample")
        def close(self): events.append("closed")
    class Buffer:
        def write(self, raw): events.append("write"); output.extend(raw)
        def flush(self): events.append("flush")
    class Stdout:
        buffer = Buffer()
    def forbidden(*args, **kwargs): pytest.fail("runtime health must not open retained inputs")
    monkeypatch.setattr(m.native, "_isolated", lambda: events.append("flags"))
    monkeypatch.setattr(m.native.batch.campaign.base, "_prove_isolation", lambda: events.append("proof"))
    monkeypatch.setattr(m.native, "_WorkerMemoryGuard", Guard)
    monkeypatch.setattr(m, "_current", lambda _: events.append("current"))
    monkeypatch.setattr(m, "_readback", forbidden)
    monkeypatch.setattr(m, "_Held", forbidden)
    monkeypatch.setattr(m.sys, "stdout", Stdout())
    m._worker(identity, role="health")
    value = json.loads(output)
    assert value == {"ok": True, "value": m._health(identity)}
    assert events[:4] == ["flags", "proof", "guard", "current"]
    assert events[-3:] == ["flush", "sample", "closed"]
    assert value["value"]["retained_inputs_opened"] is False
    assert value["value"]["new_requests"] == value["value"]["credential_reads"] == 0


def test_preflight_runs_fixed_health_only_before_any_namespace_or_retained_input(tmp_path, monkeypatch):
    _, _, identity, _ = _fake_parent(monkeypatch)
    calls = []
    def launch(command):
        calls.append(command)
        assert "role='health'" in command[-1]
        return {"ok": True, "value": m._health(identity)}
    monkeypatch.setattr(m, "_launch", launch)
    monkeypatch.setattr(m, "_readback", lambda *args, **kwargs: pytest.fail("preflight opened input"))
    receipt = m.preflight_actual(expected_head=HEAD)
    assert receipt == m._health(identity) and len(calls) == 1
    assert list(tmp_path.iterdir()) == []
    assert receipt["retained_inputs_opened"] is False


@pytest.mark.parametrize("entry", ["preflight_actual", "verify_actual"])
@pytest.mark.parametrize("code", ["current_source_refused", "projection_refused", "native_sandbox_launch_refused"])
def test_validated_worker_refusals_keep_their_finite_code(entry, code, monkeypatch):
    _fake_parent(monkeypatch)
    monkeypatch.setattr(m, "_launch", lambda *_: {"ok": False, "code": code})
    with pytest.raises(m.MassiveReadbackError, match="^" + code + "$"):
        getattr(m, entry)(expected_head=HEAD)


@pytest.mark.parametrize("exit_code", [0, 2])
def test_child_finite_refusal_message_is_preserved(exit_code):
    wire = m._raw({"ok": False, "code": "current_source_refused"}) + b"\n"
    with pytest.raises(m.MassiveReadbackError, match="^current_source_refused$"):
        m._child_result(wire, b"", exit_code)


def test_exact_source_only_nested_sandbox_signature_has_a_distinct_finite_refusal():
    with pytest.raises(m.MassiveReadbackError, match="^native_sandbox_launch_refused$"):
        m._child_result(b"", b"sandbox-exec: sandbox_apply: Operation not permitted\n", 71)


@pytest.mark.parametrize("stdout,stderr,code", [(b"", b"sandbox_apply: Operation not permitted\n", 71),
    (b"marker", b"sandbox-exec: sandbox_apply: Operation not permitted\n", 71),
    (b"", b"sandbox-exec: sandbox_apply: Operation not permitted\n", 70),
    (b"", b"untrusted provider detail", 2),
    (b'{"ok":true,"value":{}}\n', b"", 2),
    (b'{"ok":false,"code":"untrusted arbitrary detail"}\n', b"", 0),
    (b'{"ok":false,"code":"native_refused","extra":1}\n', b"", 0),
    (b'{"ok":1,"value":{}}\n', b"", 0),
    (b'{"ok":true,"ok":true,"value":{}}\n', b"", 0),
    (b'{"ok":true,"value":{}}', b"", 0),
    (b'{"ok":true,"value":{}}\n{}\n', b"", 0),
    (b"x" * (m.MAX_CONTROL + 2), b"", 0), (b"", b"x" * 4097, 71)])
def test_process_and_ipc_refusals_never_echo_untrusted_details(stdout, stderr, code):
    with pytest.raises(m.MassiveReadbackError) as captured:
        m._child_result(stdout, stderr, code)
    assert str(captured.value) in m._CODES
    assert str(captured.value) != "native_sandbox_launch_refused"
    assert "detail" not in str(captured.value)


def test_health_payload_cannot_promote_inputs_or_authority(monkeypatch):
    _, _, identity, _ = _fake_parent(monkeypatch)
    value = m._health(identity)
    value["retained_inputs_opened"] = True
    monkeypatch.setattr(m, "_launch", lambda *_: {"ok": True, "value": value})
    with pytest.raises(m.MassiveReadbackError, match="controls_refused"):
        m.preflight_actual(expected_head=HEAD)


@pytest.mark.parametrize("close_failure,wait_failure", [(False, False), (True, False), (False, True)])
def test_cleanup_kills_group_for_exited_leader_reaps_bounded_and_closes_every_handle(monkeypatch, close_failure, wait_failure):
    events = []
    class Stream:
        def __init__(self, name): self.name = name
        def close(self):
            events.append(self.name)
            if close_failure and self.name == "stdout": raise OSError("invented close failure")
    class Process:
        pid = 987654
        stdout, stderr = Stream("stdout"), Stream("stderr")
        def poll(self): return 0
        def wait(self, *, timeout):
            events.append(("wait", timeout))
            if wait_failure: raise m.subprocess.TimeoutExpired("invented", timeout)
    class Poll:
        def close(self): events.append("poll")
    monkeypatch.setattr(m.os, "killpg", lambda pid, sig: events.append(("killpg", pid, sig)))
    clean = m._cleanup(Process(), Poll(), failed=True)
    assert events[0] == ("killpg", Process.pid, m.signal.SIGKILL)
    assert events[1] == ("wait", m.CLEANUP_SECONDS)
    assert events[-3:] == ["stdout", "stderr", "poll"]
    assert clean is (not close_failure and not wait_failure)


def test_launcher_preserves_primary_refusal_when_cleanup_also_fails(monkeypatch):
    monkeypatch.setattr(m.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("untrusted launch detail")))
    monkeypatch.setattr(m, "_cleanup", lambda *args, **kwargs: False)
    with pytest.raises(m.MassiveReadbackError, match="^native_child_process_refused$"):
        m._launch(("invented",))


@pytest.mark.skipif(m.sys.platform != "darwin" or os.environ.get("INSIDER_MASSIVE_NESTED_HEALTH_PROBE") != "1",
    reason="explicit source-only nested-sandbox diagnostic requires the documented matching parent fence")
def test_native_nested_launch_is_refused_before_python_without_opening_inputs():
    """Opt-in matched-profile diagnostic, not a universal Darwin invariant.

    Run separately with parent fork allowed; all artifact reads stay denied.

    The child command is the genuine fixed HEALTH role, which cannot open
    retained inputs. Its invented identity is never used: native nesting is
    refused before Python starts. This supplies no actual readback result.
    """
    with pytest.raises(m.MassiveReadbackError, match="^native_sandbox_launch_refused$"):
        m._launch(m._command({"head": HEAD}, role="health"))


@pytest.mark.parametrize("result", [{"ok": False, "code": "untrusted arbitrary detail"},
    {"ok": False, "code": "native_refused", "extra": 1}, {"ok": 1, "value": {}},
    {"ok": True, "value": {}, "extra": 1}])
def test_canonical_worker_messages_still_require_exact_finite_protocol(result):
    with pytest.raises(m.MassiveReadbackError, match="^native_child_ipc_refused$"):
        m._child_result(m._raw(result) + b"\n", b"", 0)


def test_canonical_successful_child_ipc_round_trip():
    result = {"ok": True, "value": {"invented": True}}
    assert m._child_result(m._raw(result) + b"\n", b"", 0) == result


def test_health_command_kernel_denies_all_lane_artifacts_and_actual_owner_keychains():
    health = m._command({"head": HEAD}, role="health")
    policy = health[health.index("-p") + 1]
    for private in (m.LANE_ROOT / "artifacts", Path(m.pwd.getpwuid(os.geteuid()).pw_dir) / "Library" / "Keychains"):
        assert "(deny file-read* (subpath " + json.dumps(str(private)) + "))" in policy
    assert "role='health'" in health[-1]
    readback = m._command({"head": HEAD}, role="readback")
    assert "deny file-read*" not in readback[readback.index("-p") + 1]
