"""Invented unsealed source roots only; native process-tree network denial."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from urllib import request

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: retained custody uses supported macOS/POSIX controls")

from research import insider_buying_retained_earnings_supplement as m
from test_insider_buying_earnings_archive_assessment_runner import (
    retained as old_retained_fixture, retain_partial, private_file, enc, sha,
)


@pytest.fixture(autouse=True)
def no_provider_fallthrough(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("invented tests must never reach provider transport")
    monkeypatch.setattr(request, "urlopen", refused)
    monkeypatch.setattr(request.OpenerDirector, "open", refused)


def _invented_source(window):
    return enc({"type": "Earnings", "description": "Historical and upcoming Earnings",
                "from": window[0], "to": window[1], "earnings": [
        {"code": "INVENTED.US", "report_date": window[0][:7] + "-14",
         "date": window[0][:4] + "-01-31", "before_after_market": "BeforeMarket",
         "currency": "USD", "actual": 1.25, "estimate": 1, "difference": .25, "percent": 25},
        {"code": "INVENTED.L", "report_date": window[0][:7] + "-15",
         "date": window[0][:4] + "-01-31", "before_after_market": None,
         "currency": None, "actual": None, "estimate": None, "difference": 0, "percent": None},
        [],
    ]})


def _reanchor(retained):
    root = retained["root"]
    windows, witness_pins, input_hashes = [], [], {}
    for item in m.ACTUAL_ANCHORS.windows:
        parts, prefix = m._where(item)
        source = root.joinpath(*parts)
        witness_parts = m.custody.PARTIAL_WITNESS_PARTS if item.generation == 3 else m.custody.PARTIAL4_WITNESS_PARTS
        witness_path = root.joinpath(*witness_parts, "witness.json")
        witness = json.loads(witness_path.read_bytes())
        leaf_key = "journal_leaf_sha256_and_bytes" if item.generation == 3 else "journal_leaf_sha256_bytes_versions"
        for leaf in source.iterdir():
            raw = leaf.read_bytes()
            witness[leaf_key][leaf.name] = {"bytes": len(raw), "sha256": sha(raw)}
            input_hashes["/".join((*parts, leaf.name))] = sha(raw)
        witness_raw = enc(witness)
        private_file(witness_path, witness_raw)
        witness_pins.append(sha(witness_raw))
        start_raw = (source / (prefix + "-started.json")).read_bytes()
        start = json.loads(start_raw)
        body = (source / (prefix + "-response.json")).read_bytes()
        metadata = (source / (prefix + "-metadata.json")).read_bytes()
        windows.append(m.WindowAnchor(item.generation, item.index, item.window,
            sha((source / "manifest.json").read_bytes()), sha(start_raw), start["scope_reservation_sha256"],
            sha(body), len(body), sha(metadata), len(metadata)))
    previous = {"schema": m.custody.SCHEMA, "fixture_only": True,
        "expected_partial_witness_sha256": witness_pins[0],
        "expected_partial4_witness_sha256": witness_pins[1], "input_sha256": input_hashes,
        "looks_jobs_backtests": [0, 0, 0], "raw_financial_bodies_decoded": False,
        "counts": {"source_metadata_rows": 1}, "unavailable_window_count": 4,
        **{flag: False for flag in m.FALSE_FLAGS}}
    raw = enc(previous)
    private_file(root.joinpath(*m.PRIOR_PARTS, "complete.json"), raw)
    private_file(root.joinpath(*m.PRIOR_PARTS, "assessment.json"), b"invented prior assessment; not decoded")
    retained["supplement_anchors"] = m.SupplementAnchors(*witness_pins, sha(raw), len(raw), tuple(windows))
    return retained["supplement_anchors"]


@pytest.fixture
def retained(tmp_path):
    retained = old_retained_fixture.__wrapped__(tmp_path)
    retain_partial(retained, generation=3)
    retain_partial(retained, generation=4)
    for item in m.ACTUAL_ANCHORS.windows:
        parts, prefix = m._where(item)
        source = retained["root"].joinpath(*parts)
        raw = _invented_source(item.window)
        projector = m.third if item.generation == 3 else m.fourth
        metadata = {"schema": projector.SCHEMA, "body_sha256": sha(raw),
            "rows": projector._projection(raw, item.window, token=None),
            "metadata_acceptance_is_source_coverage_or_identity_admission": False}
        private_file(source / (prefix + "-response.json"), raw)
        private_file(source / (prefix + "-metadata.json"), enc(metadata))
    _reanchor(retained)
    return retained


def _run(retained, **changes):
    args = {"root": retained["root"], "expected_head": "a" * 40,
            "anchors": retained["supplement_anchors"], "identity": lambda _: retained["identity"]}
    args.update(changes)
    return m.run_fixture(**args)


def test_two_unsealed_windows_are_additive_metadata_not_producer_completion(retained):
    result = _run(retained)
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    body = json.loads((output / "complete.json").read_bytes())
    assert result["fixture_only"] is True
    assert result["qualified_windows"] == 2
    assert result["counts"][0] == result["counts"][1]
    assert result["counts"][0]["source_metadata_rows"] == 3
    assert result["counts"][0]["metadata_accepted_rows"] == 1
    assert result["counts"][0]["quarantined_metadata_rows"] == 2
    assert result["counts"][0]["reported_rows"] == 1
    assert result["counts"][0]["unknown_status_rows"] == 2
    assert result["counts"][0]["timing_unknown_rows"] == 2
    assert set(os.listdir(output)) == {"isolation.json", "complete.json", "window-201902-metadata.json", "window-202002-metadata.json"}
    assert body["producer_http_status"] is None
    assert body["producer_roots_repaired"] is body["producer_window_seals_present"] is body["producer_aggregate_completions_present"] is False
    assert body["raw_json_structurally_reprojected"] is True
    assert body["financial_numeric_values_interpreted"] is False
    assert body["looks_jobs_backtests"] == [0, 0, 0]
    assert all(body[flag] is result[flag] is False for flag in m.FALSE_FLAGS)
    assert body["isolation"]["effective_process_tree_network_denial"] is True
    for item in retained["supplement_anchors"].windows:
        parts, prefix = m._where(item)
        assert not retained["root"].joinpath(*parts, prefix + "-complete.json").exists()
        assert not retained["root"].joinpath(*parts, "complete.json").exists()
        metadata = json.loads((output / m._metadata_name(item)).read_bytes())
        assert metadata["producer_http_status"] is None
        assert metadata["producer_window_seal_present"] is metadata["producer_aggregate_completion_present"] is False
        assert [row["source_row_ordinal"] for row in metadata["rows"]] == [0, 1, 2]
        assert metadata["rows"][1]["code"] == "INVENTED.L"  # No .US inference.
        assert "actual" not in metadata["rows"][0]
        assert "estimate" not in metadata["rows"][0]
        assert (output / m._metadata_name(item)).stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("generation", [3, 4])
@pytest.mark.parametrize("leaf_suffix", ["response.json", "metadata.json", "started.json"])
def test_changed_retained_bytes_cannot_escape_witness_and_predecessor(retained, generation, leaf_suffix):
    item = next(item for item in retained["supplement_anchors"].windows if item.generation == generation)
    parts, prefix = m._where(item)
    path = retained["root"].joinpath(*parts, prefix + "-" + leaf_suffix)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((m.RetainedSupplementError, m.custody.ArchiveAssessmentRunnerError)):
        _run(retained)


@pytest.mark.parametrize("generation", [3, 4])
def test_coherently_reanchored_metadata_must_match_raw_projection(retained, generation):
    item = next(item for item in retained["supplement_anchors"].windows if item.generation == generation)
    parts, prefix = m._where(item)
    path = retained["root"].joinpath(*parts, prefix + "-metadata.json")
    body = json.loads(path.read_bytes()); body["rows"][0]["code"] = "DIFFERENT.US"
    private_file(path, enc(body)); _reanchor(retained)
    with pytest.raises(m.RetainedSupplementError, match="raw_metadata_reprojection_disagreement"):
        _run(retained)


@pytest.mark.parametrize("generation", [3, 4])
def test_appearing_producer_seal_is_not_a_supplement(retained, generation):
    item = next(item for item in retained["supplement_anchors"].windows if item.generation == generation)
    parts, prefix = m._where(item)
    private_file(retained["root"].joinpath(*parts, prefix + "-complete.json"), b"{}")
    with pytest.raises((m.RetainedSupplementError, m.custody.ArchiveAssessmentRunnerError)):
        _run(retained)


def test_changed_original_assessment_completion_refuses(retained):
    path = retained["root"].joinpath(*m.PRIOR_PARTS, "complete.json")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(m.custody.ArchiveAssessmentRunnerError, match="external_input_hash"):
        _run(retained)


def test_dirty_identity_refuses_before_creating_output(retained):
    identity = dict(retained["identity"], clean=False)
    with pytest.raises(m.RetainedSupplementError, match="source_identity_envelope"):
        _run(retained, identity=lambda _: identity)
    assert not retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID).exists()


def test_successful_namespace_cannot_be_resumed_or_renamed(retained):
    _run(retained)
    with pytest.raises(m.custody.ArchiveAssessmentRunnerError, match="cannot_resume"):
        _run(retained)


def test_fixture_rejects_production_root_before_callback():
    def not_called(_):
        raise AssertionError("production alias must fail before fixture identity")
    with pytest.raises(m.RetainedSupplementError, match="fixture_root"):
        m.run_fixture(root=m.LANE_ROOT, expected_head="a" * 40,
                      anchors=m.ACTUAL_ANCHORS, identity=not_called)


def test_fixture_rejects_production_callback_without_calling_it(retained):
    with pytest.raises(m.RetainedSupplementError, match="fixture_root"):
        _run(retained, identity=m._identity)
    assert not retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID).exists()


@pytest.mark.parametrize("field,value", [("producer_http_status", 200), ("producer_roots_repaired", True),
    ("producer_window_seals_present", True), ("financial_numeric_values_interpreted", True),
    ("backtesting_ready", True), ("provider_dispatches", True)])
def test_parent_refuses_coherently_rehashed_false_producer_or_authority_claim(retained, field, value):
    result = _run(retained)
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    path = output / "complete.json"
    body = json.loads(path.read_bytes()); body[field] = value
    raw = enc(body); private_file(path, raw)
    result = dict(result, complete_sha256=sha(raw))
    with pytest.raises(m.RetainedSupplementError, match="parent_authority"):
        m._verify_publication(retained["root"], retained["identity"], retained["supplement_anchors"], result, fixture_only=True)


def test_parent_compares_coherently_rehashed_output_rows_to_source(retained):
    result = _run(retained)
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    name = "window-201902-metadata.json"
    metadata = json.loads((output / name).read_bytes()); metadata["rows"][0]["code"] = "REHASHED.US"
    raw = enc(metadata); private_file(output / name, raw)
    summary = json.loads((output / "complete.json").read_bytes())
    summary["published_leaf_sha256"][name] = summary["windows"][0]["metadata_sha256"] = sha(raw)
    raw = enc(summary); private_file(output / "complete.json", raw)
    result = dict(result, complete_sha256=sha(raw))
    with pytest.raises(m.RetainedSupplementError, match="parent_metadata_reprojection"):
        m._verify_publication(retained["root"], retained["identity"], retained["supplement_anchors"], result, fixture_only=True)


def test_counts_independently_refuse_changed_ordinals_quarantine_and_timing():
    window = ("2019-02-01", "2019-02-28")
    rows = m.third._projection(_invented_source(window), window, token=None)
    assert m._counts(rows, window)["source_metadata_rows"] == 3
    for change in ({"source_row_ordinal": True}, {"metadata_accepted": True}, {"before_after_market": "invented"}):
        modified = json.loads(enc(rows)); modified[1].update(change)
        with pytest.raises(m.RetainedSupplementError):
            m._counts(modified, window)


def test_finite_window_scope_cannot_be_widened(retained):
    anchors = retained["supplement_anchors"]
    changed = replace(anchors.windows[0], window=("2019-01-01", "2019-02-28"))
    with pytest.raises(m.RetainedSupplementError, match="fixed_window_scope"):
        _run(retained, anchors=replace(anchors, windows=(changed, anchors.windows[1])))


def test_native_worker_policy_observes_network_fork_security_and_output_only_writes(tmp_path):
    if os.environ.get("IB_RUN_NATIVE_RETAINED_SUPPLEMENT") != "1":
        pytest.skip("native initial-profile proof is separate; macOS refuses nested Seatbelt installation")
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        pytest.skip("native Seatbelt proof requires supported macOS host")
    root = tmp_path.resolve()
    output = m.custody._Chain(root, (*m.OUTPUT_PARTS, m.AUDIT_ID), create=True, exclusive_last=True)
    output.close()
    code = ("import sys;sys.path.insert(0," + repr(str(m.LANE_ROOT)) + ");"
            "from pathlib import Path;from research import insider_buying_retained_earnings_supplement as m;"
            "r=Path(" + repr(str(root)) + ");o=m.custody._Chain(r,(*m.OUTPUT_PARTS,m.AUDIT_ID));"
            "m._isolation(r,o,False);o.close();print('invented-native-isolation-observed')")
    command = ["/usr/bin/sandbox-exec", "-p", m._policy(root.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)),
               sys.executable, *m.WORKER_FLAGS,
               "-c", code]
    result = subprocess.run(command, cwd=m.LANE_ROOT, capture_output=True, input=b"", timeout=20,
                            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"invented-native-isolation-observed\n"
    proof = json.loads(root.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "isolation.json").read_bytes())
    assert proof["fixture_only"] is False  # Only the isolation probe, never actual source data.
    assert all(proof[name] is True for name in ("effective_process_tree_network_denial",
        "effective_process_fork_denial", "effective_keychain_exec_denial",
        "effective_outside_output_write_denial", "fresh_output_write_observed"))
    assert not root.joinpath(*m.OUTPUT_PARTS, "isolation-" + m.AUDIT_ID + ".probe").exists()


@pytest.mark.parametrize("target", ["counts", "windows", "looks"])
def test_parent_requires_typed_counts_and_zero_look_integers(retained, target):
    result = _run(retained)
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    path = output / "complete.json"
    body = json.loads(path.read_bytes())
    if target == "counts":
        result["counts"][0]["metadata_accepted_rows"] = True
    elif target == "windows":
        body["windows"][0]["counts"]["metadata_accepted_rows"] = True
    else:
        body["looks_jobs_backtests"] = result["looks_jobs_backtests"] = [False, 0, 0]
    raw = enc(body); private_file(path, raw); result["complete_sha256"] = sha(raw)
    with pytest.raises(m.RetainedSupplementError, match="parent_window|parent_authority"):
        m._verify_publication(retained["root"], retained["identity"], retained["supplement_anchors"], result, fixture_only=True)


def test_parent_refuses_unknown_completion_field_even_if_rehashed(retained):
    result = _run(retained)
    path = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "complete.json")
    body = json.loads(path.read_bytes()); body["unregistered_field"] = "invented"
    raw = enc(body); private_file(path, raw); result["complete_sha256"] = sha(raw)
    with pytest.raises(m.RetainedSupplementError, match="parent_completion"):
        m._verify_publication(retained["root"], retained["identity"], retained["supplement_anchors"], result, fixture_only=True)


def test_parent_readback_never_calls_raw_projection_but_still_checks_source_hashes(retained, monkeypatch):
    result = _run(retained)
    def no_raw_projection(*args, **kwargs):
        raise AssertionError("parent must not structurally decode financial source JSON")
    monkeypatch.setattr(m.third, "_projection", no_raw_projection)
    monkeypatch.setattr(m.fourth, "_projection", no_raw_projection)
    monkeypatch.setattr(m, "_qualify", no_raw_projection)
    m._verify_publication(retained["root"], retained["identity"], retained["supplement_anchors"], result, fixture_only=True)
    item = retained["supplement_anchors"].windows[0]
    parts, prefix = m._where(item)
    path = retained["root"].joinpath(*parts, prefix + "-response.json")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(m.custody.ArchiveAssessmentRunnerError, match="external_input_hash"):
        m._verify_publication(retained["root"], retained["identity"], retained["supplement_anchors"], result, fixture_only=True)


def test_actual_dirty_identity_fails_before_any_production_input(monkeypatch):
    def source_identity(_):
        return {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": "a" * 40, "clean": False}
    def no_inputs(*args, **kwargs):
        raise AssertionError("dirty identity must precede production inputs")
    monkeypatch.setattr(m, "_identity", source_identity)
    monkeypatch.setattr(m, "_load_inputs", no_inputs)
    with pytest.raises(m.RetainedSupplementError, match="source_identity_envelope"):
        m.run_actual(expected_head="a" * 40)


def test_private_ownership_is_explicit_not_only_permission_bits(retained, monkeypatch):
    current = os.geteuid()
    monkeypatch.setattr(os, "geteuid", lambda: current + 1)
    with pytest.raises(m.RetainedSupplementError, match="private_directory_owner"):
        _run(retained)


def test_production_raw_projection_rechecks_denial_before_any_body_read(monkeypatch):
    calls = []
    def deny(*, require_fork):
        assert require_fork is True
        calls.append("denial")
        raise m.RetainedSupplementError("invented_denial_not_observed")
    def no_body(*args, **kwargs):
        raise AssertionError("body read must follow effective denial")
    monkeypatch.setattr(m.custody, "_effective_denial", deny)
    monkeypatch.setattr(m, "_held_raw", no_body)
    with pytest.raises(m.RetainedSupplementError, match="invented_denial_not_observed"):
        m._qualify(SimpleNamespace(root=m.LANE_ROOT), m.ACTUAL_ANCHORS.windows[0], False)
    assert calls == ["denial"]


def test_actual_command_clears_environment_and_disables_all_site_and_bytecode_hooks(monkeypatch):
    calls = []
    baseline = {"head": "a" * 40, "invented": True}
    class Inputs:
        def recheck(self): calls.append("recheck")
        def close(self): calls.append("close")
    class Output:
        def __init__(self, root, parts, **kwargs):
            assert root == m.LANE_ROOT and parts == (*m.OUTPUT_PARTS, m.AUDIT_ID)
            assert kwargs == {"create": True, "exclusive_last": True}
        def close(self): pass
    monkeypatch.setattr(m, "_identity", lambda _: baseline)
    monkeypatch.setattr(m, "_identity_envelope", lambda *args: calls.append("identity"))
    monkeypatch.setattr(m, "_load_inputs", lambda *args: Inputs())
    monkeypatch.setattr(m.custody, "_Chain", Output)
    monkeypatch.setattr(m, "_verify_publication", lambda *args, **kwargs: calls.append("verify"))
    def launch(command, **kwargs):
        assert command[:4] == ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec"]
        assert all(flag in command for flag in ("-I", "-S", "-B", "-X", "pycache_prefix=" + m.EMPTY_CACHE_PREFIX))
        assert repr(str(m.LANE_ROOT)) in command[command.index("-c") + 1]
        assert kwargs["cwd"] == m.LANE_ROOT and kwargs["timeout"] == m.TIMEOUT_SECONDS
        assert kwargs["input"] == enc(baseline)
        assert "deny network*" in command[5] and "deny process-fork" in command[5]
        assert 'deny process-exec (literal "/usr/bin/security")' in command[5]
        calls.append("launch")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"{}\n")
    monkeypatch.setattr(m.subprocess, "run", launch)
    assert m.run_actual(expected_head="a" * 40) == {}
    assert calls.index("launch") < calls.index("verify") < calls.index("close")


@pytest.mark.parametrize("changed", ["isolated", "no_user_site", "no_site", "dont_write_bytecode", "cache"])
def test_worker_interpreter_guard_refuses_before_stdin_or_input_access(monkeypatch, capsys, changed):
    def no_stdin(*args):
        raise AssertionError("invalid worker interpreter must refuse before reading stdin")
    flags = dict(isolated=1, no_user_site=1, no_site=1, dont_write_bytecode=1)
    cache = m.EMPTY_CACHE_PREFIX
    if changed == "cache": cache = "/invented/nonempty-cache"
    else: flags[changed] = 0
    runtime = SimpleNamespace(flags=SimpleNamespace(**flags), pycache_prefix=cache,
                              stdin=SimpleNamespace(buffer=SimpleNamespace(read=no_stdin)))
    monkeypatch.setattr(m, "sys", runtime)
    assert m.main(["--worker", "--expected-head", "a" * 40]) == 2
    assert "retained_earnings_supplement_refused_outputs_preserved" in capsys.readouterr().out


def test_valid_worker_interpreter_reaches_pre_stdin_positive_control(monkeypatch):
    class ReachedInput(Exception): pass
    def reached(*args): raise ReachedInput
    runtime = SimpleNamespace(flags=SimpleNamespace(isolated=1, no_user_site=1, no_site=1, dont_write_bytecode=1),
        pycache_prefix=m.EMPTY_CACHE_PREFIX, stdin=SimpleNamespace(buffer=SimpleNamespace(read=reached)))
    monkeypatch.setattr(m, "sys", runtime)
    with pytest.raises(ReachedInput):
        m.main(["--worker", "--expected-head", "a" * 40])


def test_parent_rehashes_previously_read_output_even_when_size_and_mtime_are_restored(retained, monkeypatch):
    result = _run(retained)
    path = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "complete.json")
    original = m._metadata_from_retained
    changed = []
    def change_after_completion_read(*args, **kwargs):
        answer = original(*args, **kwargs)
        if not changed:
            info = path.stat(); raw = path.read_bytes()
            altered = raw.replace(b'"provider_dispatches":0', b'"provider_dispatches":1')
            assert altered != raw and len(altered) == len(raw)
            path.write_bytes(altered)
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
            changed.append(True)
        return answer
    monkeypatch.setattr(m, "_metadata_from_retained", change_after_completion_read)
    with pytest.raises(m.RetainedSupplementError, match="parent_output_content_changed"):
        m._verify_publication(retained["root"], retained["identity"], retained["supplement_anchors"], result, fixture_only=True)
    assert changed == [True]


def test_new_publication_hold_accepts_ctime_only_change_with_unchanged_bytes(retained, monkeypatch):
    result = _run(retained)
    path = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "complete.json")
    original = m._metadata_from_retained
    changed = []
    def change_after_completion_read(*args, **kwargs):
        answer = original(*args, **kwargs)
        if not changed:
            before = path.stat(); original_bytes = path.read_bytes()
            os.chmod(path, 0o600)
            after = path.stat()
            assert before.st_mtime_ns == after.st_mtime_ns and before.st_size == after.st_size
            assert before.st_ctime_ns != after.st_ctime_ns
            assert path.read_bytes() == original_bytes
            changed.append(True)
        return answer
    monkeypatch.setattr(m, "_metadata_from_retained", change_after_completion_read)
    m._verify_publication(retained["root"], retained["identity"], retained["supplement_anchors"], result, fixture_only=True)
    assert changed == [True]
