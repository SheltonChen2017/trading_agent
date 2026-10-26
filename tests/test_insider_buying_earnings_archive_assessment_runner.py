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
                 "reserved_at_utc": child["completed_at_utc"], "maximum_attempts": 1}
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


@pytest.mark.parametrize("alias", ["literal", "symlink", "case"])
def test_fixture_lane_alias_refused_before_any_callback_or_output(retained, tmp_path, monkeypatch, alias):
    if alias == "literal":
        root = m.LANE_ROOT
    elif alias == "symlink":
        root = tmp_path / "lane-alias"
        root.symlink_to(m.LANE_ROOT, target_is_directory=True)
    else:
        root = m.LANE_ROOT.with_name(m.LANE_ROOT.name.upper())
        if not root.exists() or not root.samefile(m.LANE_ROOT):
            pytest.skip("actual volume does not expose this case alias")

    touched = []

    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("fixture reached callback, source selection, or output")

    monkeypatch.setattr(m, "_archive_selection", forbidden)
    monkeypatch.setattr(m, "_Chain", forbidden)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="fixture_root"):
        run(retained, root=root, identity=forbidden)
    assert touched == []


def test_actual_route_has_no_fixture_callback_or_anchor_override():
    import inspect
    assert tuple(inspect.signature(m.run_actual_assessment).parameters) == (
        "audit_id", "expected_head", "expected_v2_complete_sha256", "expected_v3_complete_sha256",
        "expected_partial_witness_sha256", "expected_v4_complete_sha256",
        "expected_partial4_witness_sha256", "expected_v5_complete_sha256")


def retain_partial(retained, generation=3):
    """Invented valid sealed metadata plus deliberately opaque sixth metadata."""
    root = retained["root"]
    if generation == 3:
        item = three_campaigns(third_refusal=5)[2]
        parts, campaign_id, witness_parts, sealed, consumed, suffix = m.V3_PARTS, m.V3_ID, m.PARTIAL_WITNESS_PARTS, 5, 6, m.assessment.V4_SUPPORT_WINDOWS
        witness_schema, leaf_key = "independent-partial-calendar-v3-custody-witness-candidate-v1", "journal_leaf_sha256_and_bytes"
    else:
        item = campaign(m.assessment.V4_SUPPORT_WINDOWS, schema=m.assessment.CONTINUATION4_SCHEMA, name=m.V4_ID,
                        registered="2026-10-13T00:06:00Z", refusal=11)
        parts, campaign_id, witness_parts, sealed, consumed, suffix = m.V4_PARTS, m.V4_ID, m.PARTIAL4_WITNESS_PARTS, 11, 12, m.assessment.V5_SUPPORT_WINDOWS
        witness_schema, leaf_key = "independent-partial-calendar-v4-custody-observation-candidate-v1", "journal_leaf_sha256_bytes_versions"
    manifest = json.loads(item.manifest_raw)
    previous = {"complete_sha256": retained["v2"].complete_sha256, "manifest_sha256": retained["v2"].manifest_sha256,
        "genesis_campaign_anchor": {"complete_sha256": retained["first"].complete_sha256}}
    manifest["campaign_id"] = campaign_id; manifest["previous_campaign_anchor"] = previous
    manifest_raw = enc(manifest); manifest_sha = sha(manifest_raw)
    evidence = []
    for old in item.windows:
        child = json.loads(old.complete_raw); child["manifest_sha256"] = manifest_sha
        child_raw = enc(child); evidence.append(replace(old, complete_raw=child_raw, complete_sha256=sha(child_raw)))
    complete = json.loads(item.complete_raw); complete["campaign_id"] = campaign_id
    complete["manifest_sha256"] = manifest_sha; complete["previous_campaign_anchor"] = previous
    complete["window_results"] = [{"index": i, "window": json.loads(e.complete_raw)["window"],
        "receipt": json.loads(e.complete_raw)["receipt"], "complete_sha256": e.complete_sha256} for i,e in enumerate(evidence)]
    complete_raw = enc(complete)
    item = replace(item, manifest_raw=manifest_raw, manifest_sha256=manifest_sha,
        complete_raw=complete_raw, complete_sha256=sha(complete_raw), windows=tuple(evidence))
    item = retain_campaign(root, parts, campaign_id, item)
    source = root.joinpath(*parts, "campaigns", campaign_id)
    (source / "complete.json").unlink(); (source / f"window-{sealed:04d}-complete.json").unlink()
    private_file(source / f"window-{sealed:04d}-response.json", b"opaque consumed body; not JSON")
    private_file(source / f"window-{sealed:04d}-metadata.json", b"opaque consumed metadata; not JSON")
    if generation == 4:
        private_file(source / "failure.json", enc({"kind": "invented_sanitized_stage_failure"}))
    leaves = {path.name: {"bytes": path.stat().st_size, "sha256": sha(path.read_bytes())} for path in source.iterdir()}
    scopes = {path.name: sha(path.read_bytes()) for path in root.joinpath(*parts, "scopes").iterdir()}
    counts = [{"index": i, "window": json.loads(e.complete_raw)["window"], "complete_sha256": e.complete_sha256,
        **{key: json.loads(e.complete_raw)["receipt"][key] for key in ("sample_rows", "metadata_accepted_rows", "quarantined_rows")}}
        for i,e in enumerate(item.windows[:sealed])]
    witness = {"schema": witness_schema, "campaign_id": campaign_id,
        "manifest_sha256": item.manifest_sha256, "execution_head": manifest["identity"]["head"],
        "source_inventory_sha256": manifest["identity"]["source_inventory_sha256"], "campaign_completion_present": False,
        "aggregate_completion_manufactured": False, leaf_key: leaves, "consumed_scope_sha256": scopes,
        "sealed_window_counts": counts, "sealed_window_count": sealed, "consumed_scope_count": consumed,
        "unsealed_started_window_count": 1, "unattempted_suffix_windows": len(suffix),
        "next_unattempted_window": list(suffix[0]), "last_unattempted_window": list(suffix[-1]),
        "observed_at_utc": "2026-10-13T00:06:00Z" if generation == 3 else "2026-10-13T00:08:00Z",
        "observed_failure_cause": "not_established_by_retained_controls", "historical_custody_change_cause_established": False}
    raw = enc(witness); private_file(root.joinpath(*witness_parts, "witness.json"), raw)
    return sha(raw)


def test_partial_live_observer_hashes_unsealed_metadata_without_interpreting_it(retained):
    pin = retain_partial(retained)
    result = run(retained, expected_partial_witness_sha256=pin)
    body = json.loads(retained["root"].joinpath(*m.OUTPUT_PARTS, retained["output_id"], "assessment.json").read_bytes())
    assert body["campaigns"][2]["complete_sha256"] is None
    assert body["campaigns"][2]["producer_aggregate_completion_present"] is False
    assert any(item["status"] == "UNSEALED_CONSUMED_START" for item in body["window_accounting"])
    receipt = json.loads(retained["root"].joinpath(*m.OUTPUT_PARTS, retained["output_id"], "complete.json").read_bytes())
    assert receipt["expected_partial_witness_sha256"] == pin and receipt["expected_v3_complete_sha256"] is None
    assert any(key.endswith("window-0005-metadata.json") for key in receipt["input_sha256"])
    assert not (retained["root"].joinpath(*m.V3_PARTS, "campaigns", m.V3_ID, "complete.json")).exists()
    assert result["fixture_only"] is True


@pytest.mark.parametrize("leaf", ["window-0000-metadata.json", "window-0005-response.json", "window-0005-metadata.json"])
def test_partial_live_changed_consumed_bytes_are_not_ignored(retained, leaf):
    pin = retain_partial(retained)
    path = retained["root"].joinpath(*m.V3_PARTS, "campaigns", m.V3_ID, leaf)
    path.write_bytes(b"corrupt invented value")
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="external_input_hash_mismatch"):
        run(retained, expected_partial_witness_sha256=pin)


def test_partial_live_cannot_sneak_in_an_original_aggregate_completion(retained):
    pin = retain_partial(retained)
    private_file(retained["root"].joinpath(*m.V3_PARTS, "campaigns", m.V3_ID, "complete.json"), b"{}")
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="input_directory_inventory"):
        run(retained, expected_partial_witness_sha256=pin)


def test_partial_and_aggregate_anchors_are_mutually_exclusive(retained):
    pin = retain_partial(retained)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="exclusive"):
        run(retained, expected_partial_witness_sha256=pin, expected_v3_complete_sha256="a"*64)


def test_appearing_v4_root_requires_external_pin_even_with_partial_witness(retained):
    pin = retain_partial(retained)
    retained["root"].joinpath(*m.V4_PARTS).mkdir(mode=0o700)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="retained_v4_requires"):
        run(retained, expected_partial_witness_sha256=pin)


def test_v4_live_collection_preserves_all_unavailable_predecessor_windows(retained):
    pin = retain_partial(retained)
    fourth = campaign(m.assessment.V4_SUPPORT_WINDOWS, schema=m.assessment.CONTINUATION4_SCHEMA,
        name=m.V4_ID, registered="2026-10-13T00:06:00Z")
    manifest = json.loads(fourth.manifest_raw); manifest["previous_campaign_anchor"] = {"partial_witness_sha256": pin}
    manifest_raw = enc(manifest); manifest_sha = sha(manifest_raw)
    evidence = []
    for item in fourth.windows:
        child = json.loads(item.complete_raw); child["manifest_sha256"] = manifest_sha; raw = enc(child)
        evidence.append(replace(item, complete_raw=raw, complete_sha256=sha(raw)))
    complete = json.loads(fourth.complete_raw); complete["manifest_sha256"] = manifest_sha
    complete["previous_campaign_anchor"] = manifest["previous_campaign_anchor"]
    raw = enc(complete)
    fourth = replace(fourth, manifest_raw=manifest_raw, manifest_sha256=manifest_sha,
        complete_raw=raw, complete_sha256=sha(raw), windows=tuple(evidence))
    fourth = retain_campaign(retained["root"], m.V4_PARTS, m.V4_ID, fourth)
    result = run(retained, expected_partial_witness_sha256=pin, expected_v4_complete_sha256=fourth.complete_sha256)
    assert result["unavailable_window_count"] == 153  # fixture v2 intentionally refused its first window
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, retained["output_id"])
    body = json.loads((output / "assessment.json").read_bytes())
    assert len(body["campaigns"]) == 4
    assert len([item for item in body["window_accounting"] if item.get("campaign_schema") == m.assessment.CONTINUATION4_SCHEMA]) == 89
    assert body["campaigns"][2]["complete_sha256"] is None
    receipt = json.loads((output / "complete.json").read_bytes())
    assert receipt["expected_v4_complete_sha256"] == fourth.complete_sha256
    assert receipt["raw_financial_bodies_decoded"] is False


def test_partial_external_witness_cannot_be_substituted_for_actual(retained):
    pin = retain_partial(retained)
    inputs = m._Inputs(retained["root"])
    try:
        with pytest.raises(m.ArchiveAssessmentRunnerError, match="actual_partial_external"):
            m._load_partial_campaign(inputs, pin, fixture_only=False)
    finally:
        inputs.close()


def test_both_partial_generations_bind_every_unsealed_leaf_but_decode_neither(retained):
    third_pin = retain_partial(retained)
    fourth_pin = retain_partial(retained, generation=4)
    result = run(retained, expected_partial_witness_sha256=third_pin, expected_partial4_witness_sha256=fourth_pin)
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, retained["output_id"])
    body = json.loads((output / "assessment.json").read_bytes()); receipt = json.loads((output / "complete.json").read_bytes())
    assert len(body["campaigns"]) == 4
    assert sum(row.get("status") == "UNSEALED_CONSUMED_START" for row in body["window_accounting"]) == 2
    assert body["campaigns"][2]["complete_sha256"] is body["campaigns"][3]["complete_sha256"] is None
    assert receipt["expected_partial4_witness_sha256"] == fourth_pin
    assert receipt["expected_v4_complete_sha256"] is receipt["expected_v5_complete_sha256"] is None
    assert any(key.endswith("window-0011-metadata.json") for key in receipt["input_sha256"])
    assert result["fixture_only"] is True


@pytest.mark.parametrize("leaf", ["window-0011-response.json", "window-0011-metadata.json", "failure.json"])
def test_partial_v4_changed_unsealed_or_failure_bytes_are_not_ignored(retained, leaf):
    third_pin = retain_partial(retained); fourth_pin = retain_partial(retained, generation=4)
    retained["root"].joinpath(*m.V4_PARTS, "campaigns", m.V4_ID, leaf).write_bytes(b"private corrupt fixture")
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="external_input_hash_mismatch"):
        run(retained, expected_partial_witness_sha256=third_pin, expected_partial4_witness_sha256=fourth_pin)


def test_partial_v4_requires_v3_witness_and_cannot_accept_aggregate_override(retained):
    third_pin = retain_partial(retained); fourth_pin = retain_partial(retained, generation=4)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="two_retained_partial"):
        run(retained, expected_partial4_witness_sha256=fourth_pin)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="exclusive"):
        run(retained, expected_partial_witness_sha256=third_pin, expected_partial4_witness_sha256=fourth_pin,
            expected_v4_complete_sha256="f"*64)


def test_appearing_v5_cannot_be_silently_ignored_after_both_partial_witnesses(retained):
    third_pin = retain_partial(retained); fourth_pin = retain_partial(retained, generation=4)
    retained["root"].joinpath(*m.V5_PARTS).mkdir(mode=0o700)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="retained_v5_requires"):
        run(retained, expected_partial_witness_sha256=third_pin, expected_partial4_witness_sha256=fourth_pin)


def test_completed_v5_uses_both_partial_pins_without_relabeling_old_unsealed_rows(retained):
    third_pin = retain_partial(retained); fourth_pin = retain_partial(retained, generation=4)
    fifth = campaign(m.assessment.V5_SUPPORT_WINDOWS, schema=m.assessment.CONTINUATION5_SCHEMA,
        name=m.V5_ID, registered="2026-10-13T00:08:00Z")
    manifest = json.loads(fifth.manifest_raw); manifest["previous_campaign_anchor"] = {"partial_witness_sha256": fourth_pin}
    manifest_raw = enc(manifest); manifest_sha = sha(manifest_raw)
    evidence = []
    for item in fifth.windows:
        child = json.loads(item.complete_raw); child["manifest_sha256"] = manifest_sha; raw = enc(child)
        evidence.append(replace(item, complete_raw=raw, complete_sha256=sha(raw)))
    complete = json.loads(fifth.complete_raw); complete["manifest_sha256"] = manifest_sha
    complete["previous_campaign_anchor"] = manifest["previous_campaign_anchor"]
    raw = enc(complete)
    fifth = replace(fifth, manifest_raw=manifest_raw, manifest_sha256=manifest_sha,
        complete_raw=raw, complete_sha256=sha(raw), windows=tuple(evidence))
    fifth = retain_campaign(retained["root"], m.V5_PARTS, m.V5_ID, fifth)
    result = run(retained, expected_partial_witness_sha256=third_pin, expected_partial4_witness_sha256=fourth_pin,
                 expected_v5_complete_sha256=fifth.complete_sha256)
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, retained["output_id"])
    body = json.loads((output / "assessment.json").read_bytes()); receipt = json.loads((output / "complete.json").read_bytes())
    assert len(body["campaigns"]) == 5 and result["unavailable_window_count"] == 154
    assert sum(row.get("campaign_schema") == m.assessment.CONTINUATION5_SCHEMA for row in body["window_accounting"]) == 77
    assert body["campaigns"][2]["complete_sha256"] is body["campaigns"][3]["complete_sha256"] is None
    assert receipt["expected_partial_witness_sha256"] == third_pin
    assert receipt["expected_partial4_witness_sha256"] == fourth_pin
    assert receipt["expected_v5_complete_sha256"] == fifth.complete_sha256
    assert receipt["expected_v3_complete_sha256"] is receipt["expected_v4_complete_sha256"] is None


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


@pytest.mark.parametrize("mutation", ["body_fixture", "body_count", "body_count_bool", "body_authority",
        "declared_count_bool", "result_count_bool", "actual_network", "actual_fork", "actual_outside_write", "actual_output_scope"])
def test_parent_rejects_rehashed_body_scope_counts_authority_and_actual_isolation(retained, mutation):
    """Invented outputs only: a matching digest is not semantic validation."""
    result = run(retained)
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, retained["output_id"])
    body = json.loads((output / "assessment.json").read_bytes())
    receipt = json.loads((output / "complete.json").read_bytes())
    actual = mutation.startswith("actual_")
    if actual:
        # Isolate each actual isolation assertion from the fixture guard.
        # This does NOT run the actual route or use an actual capture root.
        result["fixture_only"] = receipt["fixture_only"] = body["fixture_only"] = False
        receipt.update(effective_process_tree_network_denial=True, effective_process_fork_denial=True,
            effective_outside_output_write_denial=True, writes_confined_to_fresh_output_by_launcher=True)
        target = {"actual_network": "effective_process_tree_network_denial",
            "actual_fork": "effective_process_fork_denial", "actual_outside_write": "effective_outside_output_write_denial",
            "actual_output_scope": "writes_confined_to_fresh_output_by_launcher"}[mutation]
        receipt[target] = False
    elif mutation == "body_fixture":
        body["fixture_only"] = False
    elif mutation == "body_count":
        body["source_filings"] += 1
    elif mutation == "body_count_bool":
        body["source_metadata_rows"] = True  # True == 1 must not pass integer counts.
    elif mutation == "body_authority":
        body["authority"]["backtesting_ready"] = True
    elif mutation == "declared_count_bool":
        receipt["counts"]["source_metadata_rows"] = True
        result["counts"] = dict(receipt["counts"])
    elif mutation == "result_count_bool":
        result["counts"] = dict(receipt["counts"])
        assert result["counts"]["source_metadata_rows"] == 1
        result["counts"]["source_metadata_rows"] = True
    raw = enc(body); private_file(output / "assessment.json", raw)
    result["assessment_sha256"] = receipt["assessment_sha256"] = sha(raw)
    receipt["assessment_bytes"] = len(raw)
    receipt_raw = enc(receipt); private_file(output / "complete.json", receipt_raw)
    result["complete_sha256"] = sha(receipt_raw)
    with pytest.raises(m.ArchiveAssessmentRunnerError, match="receipt_binding"):
        m._verify_worker_publication(root=retained["root"], audit_id=retained["output_id"],
            identity=retained["identity"], v2_complete_sha=retained["v2"].complete_sha256,
            result=result, fixture_only=not actual)


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


# Section 194 (Claude review): the worker's interpreter flags compile the bound source,
# not a stale __pycache__ entry whose header matches the source's mtime and size.
def test_worker_interpreter_flags_ignore_a_forged_bytecode_cache(tmp_path):
    import os as _os, py_compile as _py_compile, subprocess as _subprocess, sys as _sys
    package = tmp_path / "probe";package.mkdir()
    source = package / "target.py";source.write_text("VALUE = 'source'\n")
    forged = tmp_path / "forged.py";forged.write_text("VALUE = 'cache1'\n")  # same size as the source
    info = source.stat();_os.utime(forged, ns=(info.st_atime_ns, info.st_mtime_ns))
    assert forged.stat().st_size == info.st_size and forged.stat().st_mtime_ns == info.st_mtime_ns
    _py_compile.compile(str(forged), cfile=str(package / "__pycache__" / f"target.{_sys.implementation.cache_tag}.pyc"),
                        doraise=True, invalidation_mode=_py_compile.PycInvalidationMode.TIMESTAMP)
    probe = "import target; print(target.VALUE)"
    environment = {"PATH": "/usr/bin:/bin"}
    plain = _subprocess.run([_sys.executable, "-B", "-c", probe], cwd=package, env=environment,
                            capture_output=True, text=True, check=True)
    fenced = _subprocess.run([_sys.executable, *m.WORKER_INTERPRETER_FLAGS, "-c", probe], cwd=package, env=environment,
                             capture_output=True, text=True, check=True)
    assert plain.stdout.strip() == "cache1"  # the hazard: -B alone still loads the forged cache
    assert fenced.stdout.strip() == "source"
