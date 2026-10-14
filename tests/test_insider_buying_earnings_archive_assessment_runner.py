"""Invented private metadata roots only, under parent OS network denial."""
from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: custody observer requires supported macOS/POSIX controls")

from research import insider_buying_earnings_archive_assessment_runner as m
from test_insider_buying_earnings_archive_cohort_assessment import campaign, inventory, enc, sha, row, three_campaigns


def private_file(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(parent.name == "artifacts" for parent in path.parents):
        for parent in path.parents:
            if parent.name == "artifacts":
                break
            parent.chmod(0o700)
    else:
        path.parent.chmod(0o700)
    path.write_bytes(raw); path.chmod(0o600)


def retain_campaign(root, parts, identity, item):
    directory = root.joinpath(*parts, "campaigns", identity)
    private_file(directory / "manifest.json", item.manifest_raw)
    private_file(root.joinpath(*parts, "campaign.lock"), b"")
    scopes = root.joinpath(*parts, "scopes")
    scopes.mkdir(mode=0o700, exist_ok=True)
    manifest = json.loads(item.manifest_raw)
    complete = json.loads(item.complete_raw)
    new_results, evidence = [], []
    for index, existing in enumerate(item.windows):
        child = json.loads(existing.complete_raw)
        window = manifest["windows"][index]
        scope = {"schema": manifest["schema"], "scope": m._scope(window), "campaign_id": identity,
                 "reserved_at_utc": manifest["registered_at_utc"], "maximum_attempts": 1}
        scope_raw = enc(scope); scope_sha = sha(scope_raw)
        scope_name = sha(enc(m._scope(window))) + ".json"
        private_file(scopes / scope_name, scope_raw)
        start = {"schema": manifest["schema"], "window": window, "index": index,
                 "started_at_utc": child["completed_at_utc"], "manifest_sha256": item.manifest_sha256,
                 "scope_reservation_sha256": scope_sha, "maximum_attempts": 1}
        start_raw = enc(start)
        prefix = f"window-{index:04d}"
        private_file(directory / (prefix + "-started.json"), start_raw)
        child["scope_reservation_sha256"] = scope_sha; child["started_sha256"] = sha(start_raw)
        child["receipt"].update({flag: False for flag in m.FALSE_FLAGS})
        metadata_raw = existing.metadata_raw
        if child["receipt"]["calendar_window_observed"]:
            raw_body = b"opaque invented source; never decode this as JSON"
            child["receipt"]["body_sha256"] = sha(raw_body)
            child["receipt"]["body_size_bytes"] = len(raw_body)
            metadata = json.loads(metadata_raw); metadata["body_sha256"] = sha(raw_body)
            metadata_raw = enc(metadata)
            if manifest["schema"] in m.assessment.QUARANTINED_SCHEMAS:
                child["receipt"]["metadata_sha256"] = sha(metadata_raw)
            private_file(directory / (prefix + "-response.json"), raw_body)
            private_file(directory / (prefix + "-metadata.json"), metadata_raw)
        child_raw = enc(child); child_sha = sha(child_raw)
        private_file(directory / (prefix + "-complete.json"), child_raw)
        new_results.append({"index": index, "window": window, "receipt": child["receipt"], "complete_sha256": child_sha})
        evidence.append(replace(existing, complete_raw=child_raw, complete_sha256=child_sha,
                                metadata_raw=metadata_raw, metadata_sha256=sha(metadata_raw) if metadata_raw else None))
    complete["window_results"] = new_results
    complete_raw = enc(complete); private_file(directory / "complete.json", complete_raw)
    return replace(item, complete_raw=complete_raw, complete_sha256=sha(complete_raw), windows=tuple(evidence))


@pytest.fixture
def retained(tmp_path):
    root = tmp_path.resolve()
    source = b"# invented observer source only\n"
    private_file(root / "fixture_source.py", source)
    source_identity = {"root": str(root), "branch": m.LANE_BRANCH, "head": "a" * 40,
        "clean": True, "source_sha256": {"fixture_source.py": sha(source)}}
    source_identity["source_inventory_sha256"] = sha(enc(source_identity["source_sha256"]))
    census = enc(inventory())
    complete = enc({"schema": "insider-2006q1-metadata-observer-completion-v1", "fixture_only": True,
        "inventory_sha256": sha(census), "inventory_bytes": len(census), "accounting": inventory()["accounting"]})
    private_file(root.joinpath(*m.CENSUS_PARTS, "inventory.json"), census)
    private_file(root.joinpath(*m.CENSUS_PARTS, "complete.json"), complete)
    first = retain_campaign(root, m.V1_PARTS, m.V1_ID,
                           campaign(name=m.V1_ID, refusal=1, rows={"2005-12-01": [row("ABC.US", "2005-12-15")]}))
    second = retain_campaign(root, m.V2_PARTS, m.V2_ID,
        campaign(m.assessment.SUPPORT_WINDOWS[2:], name=m.V2_ID, schema=m.assessment.CONTINUATION_SCHEMA,
                 registered="2026-10-13T00:02:00Z", refusal=0))
    anchors = m.FixtureAnchors(sha(census), sha(complete), first.complete_sha256, first.manifest_sha256,
                              first.windows[0].metadata_sha256)
    return {"root": root, "identity": source_identity, "anchors": anchors, "v2": second,
            "first": first, "output_id": "ib-earnings-assessment-invented"}


def run(retained, **changes):
    args = {"root": retained["root"], "audit_id": retained["output_id"], "expected_head": "a" * 40,
        "expected_v2_complete_sha256": retained["v2"].complete_sha256,
        "anchors": retained["anchors"], "identity": lambda _: retained["identity"]}
    args.update(changes)
    return m.run_fixture_assessment(**args)


def test_offline_partial_roots_publish_hash_bound_unknown_coverage_counts_only(retained):
    result = run(retained)
    assert result["fixture_only"] is True
    assert result["counts"]["source_filings"] == 4
    assert result["counts"]["source_metadata_rows"] == 1
    assert result["unavailable_window_count"] == 247
    assert not any(result[flag] for flag in m.FALSE_FLAGS)
    out = retained["root"].joinpath(*m.OUTPUT_PARTS, retained["output_id"])
    assert set(os.listdir(out)) == {"assessment.json", "complete.json"}
    receipt = json.loads((out / "complete.json").read_bytes())
    assert sha((out / "assessment.json").read_bytes()) == receipt["assessment_sha256"] == result["assessment_sha256"]
    assert sha((out / "complete.json").read_bytes()) == result["complete_sha256"]
    assert receipt["raw_financial_bodies_decoded"] is receipt["credential_read"] is False
    assert receipt["writes_confined_to_fresh_output_by_launcher"] is False
    assert receipt["effective_process_tree_network_denial"] is True
    assert receipt["effective_process_fork_denial"] is False
    assert (out / "assessment.json").stat().st_mode & 0o777 == 0o600
    assert out.stat().st_mode & 0o777 == 0o700


def test_v2_external_completion_anchor_is_required_not_self_hashed(retained):
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="hash_mismatch|offline_input"):
        run(retained, expected_v2_complete_sha256="f" * 64)


def test_census_external_hash_disagreement_refuses(retained):
    anchors = replace(retained["anchors"], inventory_sha256="f" * 64)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="hash_mismatch|offline_input"):
        run(retained, anchors=anchors)


def test_one_output_cannot_resume_even_after_success(retained):
    run(retained)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="cannot_resume"):
        run(retained)


@pytest.mark.parametrize("name", ["manifest.json", "complete.json", "window-0000-started.json", "window-0000-complete.json",
                                 "window-0000-response.json", "window-0000-metadata.json"])
def test_v1_leaf_content_tamper_refuses(retained, name):
    path = retained["root"].joinpath(*m.V1_PARTS, "campaigns", m.V1_ID, name)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(m.ArchiveAssessmentRunnerError):
        run(retained)


@pytest.mark.parametrize("form", ["symlink", "hardlink", "mode", "fifo"])
def test_private_regular_leaf_custody_refuses(retained, form):
    path = retained["root"].joinpath(*m.CENSUS_PARTS, "inventory.json")
    if form == "mode":
        path.chmod(0o644)
    else:
        other = path.parent / "saved-inventory"
        path.rename(other)
        if form == "symlink":
            path.symlink_to(other)
        elif form == "hardlink":
            os.link(other, path)
        else:
            os.mkfifo(path, 0o600)
    with pytest.raises(m.ArchiveAssessmentRunnerError):
        run(retained)


def test_unexpected_input_leaf_refuses_not_ignores(retained):
    private_file(retained["root"].joinpath(*m.V1_PARTS, "campaigns", m.V1_ID, "hidden.json"), b"{}")
    with pytest.raises(m.ArchiveAssessmentRunnerError):
        run(retained)


def test_refused_january_cannot_gain_an_unbound_response_leaf(retained):
    private_file(retained["root"].joinpath(*m.V1_PARTS, "campaigns", m.V1_ID, "window-0001-response.json"), b"invented")
    with pytest.raises(m.ArchiveAssessmentRunnerError):
        run(retained)


def test_source_code_inventory_rechecked_before_inputs(retained):
    (retained["root"] / "fixture_source.py").write_bytes(b"changed")
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="source_inventory_changed"):
        run(retained)


def test_fixture_root_cannot_be_the_actual_lane(retained):
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="fixture_root"):
        run(retained, root=m.LANE_ROOT)


def test_actual_route_has_no_fixture_callback_or_anchor_override():
    import inspect
    assert tuple(inspect.signature(m.run_actual_assessment).parameters) == (
        "audit_id", "expected_head", "expected_v2_complete_sha256", "expected_v3_complete_sha256")


def test_runner_has_no_acquisition_or_credential_calls():
    tree = ast.parse(Path(m.__file__).read_text())
    forbidden = {"_credential_file", "load_keychain", "probe_provider_metadata", "_default_transport", "urlopen", "build_opener"}
    assert not any(isinstance(node, ast.Call) and (
        isinstance(node.func, ast.Name) and node.func.id in forbidden or
        isinstance(node.func, ast.Attribute) and node.func.attr in forbidden) for node in ast.walk(tree))


def test_network_guard_requires_actual_os_permission_refusal(monkeypatch):
    class NotDenied:
        def settimeout(self, _): pass
        def connect(self, _): raise ConnectionRefusedError(61, "invented")
        def close(self): pass
    monkeypatch.setattr(m.socket, "socket", lambda *_: NotDenied())
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="os_network_denial"):
        m._effective_denial(require_fork=False)


def test_named_directory_replacement_detected(retained):
    chain = m._Chain(retained["root"], m.CENSUS_PARTS)
    source = retained["root"].joinpath(*m.CENSUS_PARTS)
    try:
        source.rename(source.with_name("replaced")); source.mkdir(mode=0o700)
        with pytest.raises(m.ArchiveAssessmentRunnerError, match="directory_custody"):
            chain.recheck()
    finally:
        chain.close()


def test_internal_import_closure_includes_indirect_local_source(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    private_file(root / "entry.py", b"from helper import value\n")
    private_file(root / "helper.py", b"from hidden import marker\nvalue=1\n")
    private_file(root / "hidden.py", b"marker=1\n")
    monkeypatch.setattr(m, "REQUIRED_SOURCES", ("entry.py",))
    assert m._internal_source_paths(root) == ("entry.py", "helper.py", "hidden.py")


@pytest.mark.parametrize("parts", [m.CENSUS_PARTS, (*m.V1_PARTS, "campaigns", m.V1_ID), (*m.V2_PARTS, "scopes")])
def test_directory_inventory_rechecked_after_pure_assessment(retained, monkeypatch, parts):
    real = m.assessment.assess_earnings_archive_cohort
    def changed(**kwargs):
        result = real(**kwargs)
        private_file(retained["root"].joinpath(*parts, "unexpected.json"), b"{}")
        return result
    monkeypatch.setattr(m.assessment, "assess_earnings_archive_cohort", changed)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="inventory|offline_input"):
        run(retained)


def test_policy_denies_network_fork_all_writes_except_exact_fresh_output(tmp_path):
    output = tmp_path.resolve() / 'exact output "quoted"'
    assert m._policy(output) == (
        '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)'
        '(allow file-write* (subpath ' + json.dumps(str(output)) + '))')


def test_outside_write_probe_requires_permission_denial(retained, monkeypatch):
    real = m.os.open
    def fault(path, flags, mode=0o777, **kwargs):
        if str(path).endswith(".probe"):
            raise FileNotFoundError(2, "invented")
        return real(path, flags, mode, **kwargs)
    monkeypatch.setattr(m.os, "open", fault)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="write_denial_not_observed"):
        m._outside_write_denied(retained["root"], retained["output_id"])


def test_parent_independently_binds_worker_response_to_private_outputs(retained):
    result = run(retained)
    args = {"root": retained["root"], "audit_id": retained["output_id"], "identity": retained["identity"],
            "v2_complete_sha": retained["v2"].complete_sha256, "fixture_only": True}
    m._verify_worker_publication(**args, result=result)
    changed = {**result, "assessment_sha256": "f" * 64}
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="receipt_binding"):
        m._verify_worker_publication(**args, result=changed)


def test_parent_does_not_relabel_fixture_publication_as_actual(retained):
    result = run(retained)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="receipt_binding"):
        m._verify_worker_publication(root=retained["root"], audit_id=retained["output_id"],
            identity=retained["identity"], v2_complete_sha=retained["v2"].complete_sha256, result=result)


@pytest.fixture
def retained_three(retained):
    _, second, third = three_campaigns(third_rows={"2018-09-01": [row("ABC.US", "2018-09-15")]})
    def named(item, identity):
        manifest = json.loads(item.manifest_raw); manifest["campaign_id"] = identity
        manifest_raw = enc(manifest); manifest_digest = sha(manifest_raw)
        windows = []
        complete = json.loads(item.complete_raw); complete["campaign_id"] = identity; complete["manifest_sha256"] = manifest_digest
        for index, original in enumerate(item.windows):
            body = json.loads(original.complete_raw); body["manifest_sha256"] = manifest_digest
            raw = enc(body); digest = sha(raw)
            windows.append(replace(original, complete_raw=raw, complete_sha256=digest))
            complete["window_results"][index]["complete_sha256"] = digest
        raw = enc(complete)
        return replace(item, manifest_raw=manifest_raw, manifest_sha256=manifest_digest,
                       complete_raw=raw, complete_sha256=sha(raw), windows=tuple(windows))
    second = retain_campaign(retained["root"], m.V2_PARTS, m.V2_ID, named(second, m.V2_ID))
    third = retain_campaign(retained["root"], m.V3_PARTS, m.V3_ID, named(third, m.V3_ID))
    retained["v2"] = second; retained["v3"] = third
    return retained


def test_three_epoch_actual_style_fixture_retains_two_unavailable_months(retained_three):
    result = run(retained_three, expected_v3_complete_sha256=retained_three["v3"].complete_sha256)
    assert result["unavailable_window_count"] == 2
    assert result["counts"]["source_metadata_rows"] == 3
    output = retained_three["root"].joinpath(*m.OUTPUT_PARTS, retained_three["output_id"])
    receipt = json.loads((output / "complete.json").read_bytes())
    assert receipt["expected_v3_complete_sha256"] == retained_three["v3"].complete_sha256
    assert receipt["raw_financial_bodies_decoded"] is False
    m._verify_worker_publication(root=retained_three["root"], audit_id=retained_three["output_id"],
        identity=retained_three["identity"], v2_complete_sha=retained_three["v2"].complete_sha256,
        v3_complete_sha=retained_three["v3"].complete_sha256, result=result, fixture_only=True)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="receipt_binding"):
        m._verify_worker_publication(root=retained_three["root"], audit_id=retained_three["output_id"],
            identity=retained_three["identity"], v2_complete_sha=retained_three["v2"].complete_sha256,
            v3_complete_sha="f" * 64, result=result, fixture_only=True)


def test_v3_retained_root_cannot_be_skipped_without_external_anchor(retained_three):
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="v3_requires_external"):
        run(retained_three)


def test_v3_external_completion_hash_cannot_be_self_attested(retained_three):
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="hash_mismatch|offline_input"):
        run(retained_three, expected_v3_complete_sha256="f" * 64)


def test_v3_external_anchor_cannot_represent_nonexistent_root(retained):
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="requires_retained_root"):
        run(retained, expected_v3_complete_sha256="f" * 64)


def test_added_v3_root_during_assessment_cannot_be_ignored(retained, monkeypatch):
    real = m.assessment.assess_earnings_archive_cohort
    def appeared(**kwargs):
        result = real(**kwargs)
        retained["root"].joinpath(*m.V3_PARTS).mkdir(mode=0o700)
        return result
    monkeypatch.setattr(m.assessment, "assess_earnings_archive_cohort", appeared)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="v3_requires_external"):
        run(retained)


def test_optional_v3_source_is_inventoried_only_when_present(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    private_file(root / "entry.py", b"# fixture entry\n")
    monkeypatch.setattr(m, "REQUIRED_SOURCES", ("entry.py",))
    monkeypatch.setattr(m, "OPTIONAL_SOURCES", ("continuation3.py",))
    assert m._internal_source_paths(root) == ("entry.py",)
    private_file(root / "continuation3.py", b"import helper\n")
    private_file(root / "helper.py", b"# independently inventoried fixture dependency\n")
    assert m._internal_source_paths(root) == ("continuation3.py", "entry.py", "helper.py")


def test_new_source_file_is_not_an_actual_capture_trigger(tmp_path):
    private_file(tmp_path / "research" / "insider_buying_eodhd_earnings_continuation3.py", b"# fixture source only\n")
    assert m._v3_selection(tmp_path.resolve(), None) is None


@pytest.mark.parametrize("mutate", [None, "complete_sha256", "manifest_sha256", "execution_head", "source_inventory_sha256",
    "journal_leaf_sha256", "scope_sha256", "registered_unattempted_windows", "genesis_campaign_anchor", "old_root_resumed_or_written"])
def test_observer_binds_v3_predecessor_claims_to_independently_read_chain(monkeypatch, mutate):
    _, second, third = three_campaigns()
    prior_manifest = json.loads(second.manifest_raw); prior_complete = json.loads(second.complete_raw)
    identity = {"head": "a" * 40, "source_inventory_sha256": "b" * 64}
    prior_manifest.update(identity=identity, previous_campaign_anchor={"invented_genesis": "c" * 64})
    prior_complete["identity"] = identity
    prior_raw, prior_complete_raw = enc(prior_manifest), enc(prior_complete)
    second = replace(second, manifest_raw=prior_raw, manifest_sha256=sha(prior_raw),
                     complete_raw=prior_complete_raw, complete_sha256=sha(prior_complete_raw))
    monkeypatch.setattr(m, "V2_PRECEDING_COMPLETE_SHA256", second.complete_sha256)
    leaves = {"manifest.json": second.manifest_sha256, "complete.json": second.complete_sha256}
    scopes = {"d" * 64 + ".json": "e" * 64}
    hashes = {"/".join((*m.V2_PARTS, "campaigns", m.V2_ID, name)): digest for name, digest in leaves.items()}
    hashes.update({"/".join((*m.V2_PARTS, "scopes", name)): digest for name, digest in scopes.items()})
    previous = {"campaign_id": m.V2_ID, "complete_sha256": second.complete_sha256, "manifest_sha256": second.manifest_sha256,
        "execution_head": identity["head"], "source_inventory_sha256": identity["source_inventory_sha256"],
        "journal_leaf_sha256": leaves, "scope_sha256": scopes,
        "registered_unattempted_windows": [list(window) for window in m.assessment.V3_SUPPORT_WINDOWS],
        "genesis_campaign_anchor": prior_manifest["previous_campaign_anchor"], "old_root_resumed_or_written": False,
        "old_raw_financial_values_decoded": False}
    if mutate:
        previous[mutate] = True if mutate == "old_root_resumed_or_written" else "f" * 64
    manifest, complete = json.loads(third.manifest_raw), json.loads(third.complete_raw)
    manifest["previous_campaign_anchor"] = complete["previous_campaign_anchor"] = previous
    manifest_raw, complete_raw = enc(manifest), enc(complete)
    third = replace(third, manifest_raw=manifest_raw, manifest_sha256=sha(manifest_raw),
                    complete_raw=complete_raw, complete_sha256=sha(complete_raw))
    if mutate:
        with pytest.raises(m.ArchiveAssessmentRunnerError, match="observed_predecessor_chain"):
            m._bind_actual_v3_predecessor(SimpleNamespace(hashes=hashes), second, third)
    else:
        m._bind_actual_v3_predecessor(SimpleNamespace(hashes=hashes), second, third)
