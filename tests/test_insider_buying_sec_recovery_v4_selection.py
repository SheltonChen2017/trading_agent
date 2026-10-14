"""Invented prefixes and denied toy workers; no retained-root replay or SEC."""
import base64
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from research import insider_buying_sec_recovery_v4_selection as m


HEAD = "a" * 40


def request(index=1):
    accession = f"0000001234-22-{index:06d}"
    archive = f"edgar/data/5678/{accession}.txt"
    return {"period": "2022Q4", "accession_number": accession, "form_type": "4", "filing_date": "2022-11-17",
        "issuer_cik": "1234", "archive_path": archive, "submission_row_id": "b" * 64,
        "parsed_lineage_hash": "c" * 64, "master_source_sha256": "d" * 64,
        "url": "https://www.sec.gov/Archives/" + archive}


def invented(count=3):
    return m.make_invented_test_selection(tuple(request(index) for index in range(1, count + 1)))


def mutated_rows(change):
    rows = invented().to_payload()["requests"]
    change(rows)
    return rows


@pytest.mark.parametrize("count", (1, 2, 3, 63, 64))
def test_exact_invented_prefix_is_detached_bounded_inert_and_not_observed(count):
    supplied = tuple(request(index) for index in range(1, count + 1))
    result = m.make_invented_test_selection(supplied, repository_head=HEAD)
    assert type(result) is m.InventedV4Selection and type(result) is not m.FreshV4Selection
    payload = result.to_payload()
    assert payload["scope"] == "invented_test_only" and payload["maximum_requests"] == count
    assert payload["total_parents"] == count and payload["source_bound_count"] == 0
    assert payload["isolation"] == {"observed_worker_execution": False}
    assert payload["historical_files"] == payload["historical_function_paths"] == payload["executed_modules"] == []
    assert payload["historical_commit"] is payload["source_view"] is None
    assert payload["selected_prefix_sha256"] == m._hash(payload["requests"])
    assert result.sha256 == hashlib.sha256(result._raw).hexdigest()
    for row, original in zip(payload["requests"], supplied, strict=True):
        assert row["source_class"] == "originally_unattempted" and row["request"] == original
        assert row["request_sha256"] == m._hash(original)
    assert all(value is False if type(value) is bool else value == 0 for value in payload["authority"].values())
    supplied[0]["issuer_cik"] = "9999"
    payload["requests"][0]["request"]["issuer_cik"] = "8888"
    assert result.to_payload()["requests"][0]["request"]["issuer_cik"] == "1234"


def test_archive_owner_cik_is_not_forced_to_equal_source_issuer_cik():
    item = request()
    assert item["issuer_cik"] != item["archive_path"].split("/")[2]
    assert m.make_invented_test_selection((item,)).to_payload()["requests"][0]["request"] == item


def test_q1_form4_amendment_is_valid_inside_frozen_source_window():
    item = request()
    item.update(period="2023Q1", filing_date="2023-03-31", form_type="4/A")
    assert m.make_invented_test_selection((item,)).to_payload()["requests"][0]["request"] == item


@pytest.mark.parametrize("value", ((), [request()], None, True, tuple(request(i) for i in range(1, 66))))
def test_invented_request_inventory_requires_exact_tuple_and_one_through_64(value):
    with pytest.raises(m.FreshV4SelectionError):
        m.make_invented_test_selection(value)


@pytest.mark.parametrize("field,value", [
    ("accession_number", "0000001234-22-00001"), ("accession_number", True),
    ("issuer_cik", "0"), ("issuer_cik", "12345678901"), ("issuer_cik", "-1"),
    ("issuer_cik", 1234), ("form_type", "3"), ("form_type", "4-A"),
    ("period", "2022Q3"), ("period", "2023Q2"), ("period", []),
    ("submission_row_id", "A" * 64), ("parsed_lineage_hash", "bad"), ("master_source_sha256", None),
    ("archive_path", "edgar/data/0/0000001234-22-000001.txt"),
    ("archive_path", "edgar/data/5678/0000001234-22-000002.txt"),
    ("archive_path", "../edgar/data/5678/0000001234-22-000001.txt"),
    ("url", "http://www.sec.gov/Archives/edgar/data/5678/0000001234-22-000001.txt"),
    ("url", "https://www.sec.gov.evil.invalid/Archives/edgar/data/5678/0000001234-22-000001.txt"),
    ("url", "https://www.sec.gov/Archives/edgar/data/5678/0000001234-22-000001.txt?extra=1"),
    ("url", "https://www.sec.gov/Archives/edgar/data/5678/0000001234-22-000001.txt#x"),
    ("filing_date", "2023-04-01"), ("filing_date", "2022-09-30"), ("filing_date", "2022-11-17T12:00:00Z"),
    ("filing_date", "not-a-date"), ("filing_date", "2022-02-30"),
])
def test_source_identity_date_and_exact_locator_failures_are_sanitized(field, value):
    item = request()
    item[field] = value
    with pytest.raises(m.FreshV4SelectionError):
        m.make_invented_test_selection((item,))


@pytest.mark.parametrize("mutation", ("extra", "missing", "subclass", "nonmapping"))
def test_request_boundary_is_exact_not_loosely_coercible(mutation):
    item = request()
    if mutation == "extra": item["caller_authorized"] = "true"
    if mutation == "missing": del item["url"]
    if mutation == "subclass": item = type("LooseRequest", (dict,), {})(item)
    if mutation == "nonmapping": item = list(item.items())
    with pytest.raises(m.FreshV4SelectionError):
        m.make_invented_test_selection((item,))


@pytest.mark.parametrize("count", (0, 65, True, False, 1.0, "3", None))
def test_row_cardinality_requires_exact_int_one_through_64(count):
    with pytest.raises(m.FreshV4SelectionError):
        m._rows(invented().to_payload()["requests"], count)


@pytest.mark.parametrize("mutation", ("reverse", "same-ordinal", "negative-ordinal", "too-large-ordinal", "bool-ordinal",
    "source-bound-class", "ambiguous-class", "missing-hash", "mismatched-hash", "duplicate-accession", "extra", "missing-row"))
def test_selected_rows_preserve_order_unique_accessions_exact_hashes_and_originally_unattempted_class(mutation):
    rows = invented().to_payload()["requests"]
    if mutation == "reverse": rows.reverse()
    if mutation == "same-ordinal": rows[1]["global_index"] = rows[0]["global_index"]
    if mutation == "negative-ordinal": rows[0]["global_index"] = -1
    if mutation == "too-large-ordinal": rows[-1]["global_index"] = 99394
    if mutation == "bool-ordinal": rows[0]["global_index"] = True
    if mutation == "source-bound-class": rows[0]["source_class"] = "v3_completed"
    if mutation == "ambiguous-class": rows[0]["source_class"] = "accepted_ambiguous_diagnostic"
    if mutation == "missing-hash": del rows[0]["request_sha256"]
    if mutation == "mismatched-hash": rows[0]["request_sha256"] = "e" * 64
    if mutation == "duplicate-accession": rows[1].update(request=deepcopy(rows[0]["request"]), request_sha256=rows[0]["request_sha256"])
    if mutation == "extra": rows[0]["caller_dispatch_grant"] = True
    if mutation == "missing-row": rows.pop()
    with pytest.raises(m.FreshV4SelectionError):
        m._rows(rows, 3)


@pytest.mark.parametrize("field", ("_raw", "_factory_raw", "_token"))
def test_invented_selection_seal_detects_single_field_mutation(field):
    result = invented()
    with pytest.raises(FrozenInstanceError):
        setattr(result, field, b"{}")
    object.__setattr__(result, field, b"{}" if field != "_token" else object())
    with pytest.raises(m.FreshV4SelectionError):
        result.to_payload()


def test_invented_selection_factory_anchor_cannot_be_rebound_together_with_raw():
    result = invented()
    replacement = result.to_payload()
    replacement["requests"][0]["request"]["issuer_cik"] = "9999"
    replacement["requests"][0]["request_sha256"] = m._hash(replacement["requests"][0]["request"])
    replacement["selected_prefix_sha256"] = m._hash(replacement["requests"])
    rebound = m._canonical(replacement)
    assert rebound != result._raw
    object.__setattr__(result, "_raw", rebound)
    object.__setattr__(result, "_factory_raw", rebound)
    with pytest.raises(m.FreshV4SelectionError):
        result.to_payload()


def test_invented_bytes_cannot_enter_observed_selection_even_with_wrongly_reused_private_factory_token():
    fixture = invented()
    with pytest.raises(m.FreshV4SelectionError):
        m.FreshV4Selection(fixture._raw, m._TOKEN, fixture._raw).to_payload()
    with pytest.raises(m.FreshV4SelectionError):
        m.FreshV4Selection(fixture._raw, object(), fixture._raw).to_payload()
    with pytest.raises(m.FreshV4SelectionError):
        m._validate_body(fixture.to_payload(), observed=True)


@pytest.mark.parametrize("kind", ("sealed-invented", "detached-dict", "unrelated-object"))
def test_invented_or_unsealed_inputs_cannot_enter_observed_capture_before_journal_or_transport(monkeypatch, kind):
    from research import insider_buying_sec_recovery_v4_capture as capture
    supplied = invented()
    if kind == "detached-dict": supplied = supplied.to_payload()
    if kind == "unrelated-object": supplied = object()
    monkeypatch.setattr(capture, "_capture", lambda *_args, **_kwargs: pytest.fail("real journal/transport boundary reached"))
    with pytest.raises(capture.FreshV4CaptureError, match="genuinely replayed observed selection required"):
        capture.run_observed_fresh_v4_capture(supplied, "invented-refusal", expected_head=HEAD,
            contact_email="invented@unit.test")


@pytest.mark.parametrize("mutation", ("wrong-scope", "wrong-kind", "wrong-digest", "unknown-field", "missing-field",
    "bool-isolation", "worker-isolation", "authority-int", "authority-true", "head-format", "head-type"))
def test_invented_payload_cannot_infer_authority_worker_observation_or_drift_its_bound_shape(mutation):
    payload = invented().to_payload()
    if mutation == "wrong-scope": payload["scope"] = "observed_isolated_retained_root_replay"
    if mutation == "wrong-kind": payload["kind"] = "other"
    if mutation == "wrong-digest": payload["selected_prefix_sha256"] = "e" * 64
    if mutation == "unknown-field": payload["actually_source_authenticated"] = True
    if mutation == "missing-field": del payload["source_view"]
    if mutation == "bool-isolation": payload["isolation"] = {"observed_worker_execution": 0}
    if mutation == "worker-isolation": payload["isolation"] = {"observed_worker_execution": True}
    if mutation == "authority-int": payload["authority"]["point_in_time_data"] = 0
    if mutation == "authority-true": payload["authority"]["dispatch_enabled"] = True
    if mutation == "head-format": payload["repository_head"] = "bad"
    if mutation == "head-type": payload["repository_head"] = True
    with pytest.raises(m.FreshV4SelectionError):
        m._validate_body(payload, observed=False)


@pytest.mark.parametrize("status", ("?? unrelated.py\n", "R  old.py -> new.py\n", "C  source.py -> copy.py\n", "x\n", " M ../escape.py\n"))
def test_unexpected_context_refuses_before_git_blob_preparation_or_worker(monkeypatch, status):
    base = m._base()
    monkeypatch.setattr(base, "_repository_snapshot", lambda: (HEAD, status))
    monkeypatch.setattr(base, "_git", lambda *_: pytest.fail("prepared historical Git bytes after context refusal"))
    monkeypatch.setattr(m, "_run_isolated_worker", lambda *_: pytest.fail("worker launched after context refusal"))
    with pytest.raises(m.FreshV4SelectionError):
        m.replay_observed_first_v4_requests(expected_head=HEAD)


@pytest.mark.parametrize("status", ("", "?? tests/test_insider_buying_sec_recovery_v4_selection.py\n", " M research/insider_buying_sec_recovery_v4_capture.py\n",
    ' M "docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md"\n'))
def test_only_declared_lane_local_context_paths_are_admitted(status):
    assert m._context((HEAD, status), HEAD) is None


@pytest.mark.parametrize("count", (0, 65, True, 1.0, "64", None))
def test_public_first_prefix_bound_refuses_before_any_repo_or_worker_access(monkeypatch, count):
    monkeypatch.setattr(m._base(), "_repository_snapshot", lambda: pytest.fail("repository preparation was reached"))
    with pytest.raises(m.FreshV4SelectionError):
        m.replay_observed_first_v4_requests(expected_head=HEAD, maximum_requests=count)


def test_missing_required_sandbox_cannot_fall_back_to_undeniable_execution(monkeypatch):
    original = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda path: False if str(path) == "/usr/bin/sandbox-exec" else original(path))
    monkeypatch.setattr(m._base(), "_repository_snapshot", lambda: pytest.fail("repository access after sandbox absence"))
    with pytest.raises(m.FreshV4SelectionError, match="sandbox unavailable"):
        m.replay_observed_first_v4_requests(expected_head=HEAD)


@pytest.mark.parametrize("timeout", (0, 601, True, False, 1.0, "1", None))
def test_invalid_worker_timeout_refuses_before_spawn(monkeypatch, timeout):
    monkeypatch.setattr(m.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("invalid-timeout worker spawned"))
    with pytest.raises(m.FreshV4SelectionError, match="timeout differs"):
        m._run_isolated_worker(b"{}", timeout)


@pytest.mark.parametrize("raw", (b"", bytearray(b"{}"), "{}", None))
def test_invalid_worker_input_refuses_before_spawn(monkeypatch, raw):
    monkeypatch.setattr(m.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("invalid-input worker spawned"))
    with pytest.raises(m.FreshV4SelectionError, match="input exceeds cap"):
        m._run_isolated_worker(raw, 1)


def toy_bundle(worker_source, *, guarded=False):
    # This is source code only, never a retained root or source-data read.
    base_source = ((Path(__file__).resolve().parents[1] / m.BASE_PATH).read_bytes()
        if guarded else b"def _audit_event(event, args):\n    pass\n")
    return m._canonical({"current_sources": [{"path": m.BASE_PATH, "sha256": m._sha(base_source),
                "source_b64": base64.b64encode(base_source).decode()}],
        "base_source_sha256": m._sha(base_source), "worker_source_sha256": m._sha(worker_source),
        "worker_source_b64": base64.b64encode(worker_source).decode()})


@pytest.fixture
def invented_child_under_inherited_network_denial(monkeypatch):
    # macOS refuses another sandbox inside the already OS-network-denied test
    # parent. As in the accepted replay tests, strip ONLY that nested launcher
    # for invented children. The child inherits OS network denial; the actual
    # worker profile is asserted here, not relabeled as independently executed.
    real_popen = subprocess.Popen
    captures = []
    def spawn(command, **kwargs):
        assert command[:2] == ("/usr/bin/sandbox-exec", "-p")
        assert command[2] == m._base()._worker_policy()
        assert command[3] == str(Path(sys.executable).resolve())
        assert command[4:8] == ("-I", "-S", "-B", "-c")
        assert kwargs["cwd"] == m._base().LANE_ROOT
        assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        captures.append(command)
        return real_popen(command[3:], **kwargs)
    monkeypatch.setattr(m.subprocess, "Popen", spawn)
    return captures


def test_worker_policy_requires_os_network_write_fork_and_exec_denial():
    policy = m._base()._worker_policy()
    assert policy.startswith("(version 1)(allow default)(deny network*)(deny file-write*)"
        "(deny process-fork)(deny process-exec)")
    assert f'(allow process-exec (literal "{Path(sys.executable).resolve()}"))' in policy


def test_real_toy_worker_inherited_os_network_denial_without_python_guard(invented_child_under_inherited_network_denial):
    source = ("import sys,socket\ndef _worker_main(bundle):\n"
        "    try:\n        s=socket.socket();s.connect(('127.0.0.1',9));sys.stdout.write('NETWORK-ALLOWED')\n"
        "    except OSError:\n        sys.stdout.write('network-denied')\n").encode()
    result = m._run_isolated_worker(toy_bundle(source), 5)
    assert result.returncode == 0 and result.stdout == b"network-denied"
    assert len(invented_child_under_inherited_network_denial) == 1


def test_real_toy_worker_installs_captured_audit_guards_before_payload_without_retained_roots(tmp_path,
        invented_child_under_inherited_network_denial):
    target = str(tmp_path / "must-not-be-written")
    source = ("import sys,os,socket\ndef _worker_main(bundle):\n"
        "    result=[]\n"
        "    try:\n        s=socket.socket();s.connect(('127.0.0.1',9));result.append('NETWORK-ALLOWED')\n"
        "    except Exception:\n        result.append('network-denied')\n"
        f"    try:\n        open({target!r},'wb').write(b'bad');result.append('WRITE-ALLOWED')\n"
        "    except Exception:\n        result.append('write-denied')\n"
        "    try:\n        pid=os.fork();result.append('FORK-ALLOWED')\n"
        "    except Exception:\n        result.append('fork-denied')\n"
        "    sys.stdout.write(','.join(result))\n").encode()
    result = m._run_isolated_worker(toy_bundle(source, guarded=True), 5)
    assert result.returncode == 0 and result.stdout == b"network-denied,write-denied,fork-denied"
    assert not Path(target).exists()


def test_real_toy_worker_overflow_is_refused_and_killed_without_roots(invented_child_under_inherited_network_denial):
    source = f"import sys\ndef _worker_main(bundle):\n    sys.stdout.buffer.write(b'x'*{m.MAX_OUTPUT_BYTES + 1});sys.stdout.flush()\n".encode()
    with pytest.raises(m.FreshV4SelectionError, match="output exceeded cap"):
        m._run_isolated_worker(toy_bundle(source), 5)


def test_real_toy_worker_timeout_is_refused_and_killed_without_roots(invented_child_under_inherited_network_denial):
    source = b"def _worker_main(bundle):\n    while True: pass\n"
    with pytest.raises(m.FreshV4SelectionError, match="timed out"):
        m._run_isolated_worker(toy_bundle(source), 1)


def test_real_toy_worker_invalid_bootstrap_source_hash_never_runs_payload(invented_child_under_inherited_network_denial):
    body = json.loads(toy_bundle(b"def _worker_main(bundle):\n    raise AssertionError('must not execute')\n"))
    body["worker_source_sha256"] = "e" * 64
    result = m._run_isolated_worker(m._canonical(body), 5)
    assert result.returncode == 2 and result.stdout == b""
