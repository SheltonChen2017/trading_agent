"""Synthetic output-reader tests; no actual R272 observation or native query."""
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from scripts import verify_arv2_publication_probe as tool

REAL_ROOT, REAL_OUTPUT = tool.ROOT, tool.OUTPUT


@pytest.fixture(autouse=True)
def artifact_native_tripwires(monkeypatch):
    opener = tool.audit._open_absolute_directory

    def guarded(path):
        assert path != REAL_ROOT and not path.is_relative_to(REAL_ROOT / "artifacts"), "real artifact opened"
        return opener(path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("real probe, source or native operation")

    monkeypatch.setattr(tool.audit, "_open_absolute_directory", guarded)
    monkeypatch.setattr(tool.producer, "_run", forbidden)
    monkeypatch.setattr(tool.producer, "_establish", forbidden)
    monkeypatch.setattr(tool.producer.probe, "_provenance", forbidden)
    monkeypatch.setattr(tool.producer.probe.private, "_open_directory_path", forbidden)
    monkeypatch.setattr(tool.producer.probe.subprocess, "run", forbidden)
    for name in ("listxattr", "getxattr", "setxattr", "removexattr"):
        if hasattr(tool.os, name):
            monkeypatch.setattr(tool.os, name, forbidden)


def metadata(ino=100):
    return {"dev": tool.DEVICE, "ino": ino, "size": 48, "mtime_ns": 1000, "ctime_ns": 2000,
            "mode": 0o600, "uid": os.getuid(), "gid": 20, "nlink": 1, "regular": True,
            "flags": 0, "birthtime_ns": None, "birthtime_seconds": 1.0}


def sample_for(baseline, allocation, *, baseline_ok=True, row=None):
    row = deepcopy(row if row is not None else baseline["held"])
    sample = {key: deepcopy(row) for key in tool.ROWS}
    refresh_sample(sample, baseline, allocation, baseline_ok=baseline_ok)
    return sample


def refresh_sample(sample, baseline, allocation, *, baseline_ok=True):
    # Deliberately mirror the producer's equality and insertion ordering, not
    # the verifier functions, so weakening the verifier is independently tested.
    def changed(left, right):
        return [key for key in tool.SAMPLE_FIELDS if left[key] != right[key]]

    sample.update(held_changed=changed(baseline["held"], sample["held_after_read"]),
                  named_changed=changed(baseline["named"], sample["named_after_read"]),
                  during_read_held_changed=changed(sample["held"], sample["held_after_read"]),
                  during_read_named_changed=changed(sample["named"], sample["named_after_read"]),
                  held_named_mismatch=changed(sample["held_after_read"], sample["named_after_read"]))
    sample.setdefault("readback_sha256", tool.producer.PROFILE["fixture_sha256"])
    matches = sample["readback_sha256"] == tool.producer.PROFILE["fixture_sha256"]
    sample["readback_matches"] = matches

    def safe(row):
        return (all(row[key] == allocation[key] for key in ("dev", "ino", "gid"))
                and row["regular"] and row["mode"] == 0o600 and row["uid"] == os.getuid()
                and row["nlink"] == 1 and row["size"] == 48)

    sample["integrity_unchanged"] = (baseline_ok and matches and baseline["held"] == baseline["named"]
        and all(safe(row) for row in (*baseline.values(), *(sample[key] for key in tool.ROWS)))
        and not any(sample[key] for key in tool.CHANGES))


def report_for(fixtures=None):
    fixtures = fixtures or {name: metadata(100 + i) for i, name in enumerate(tool.CASES)}
    cases = []
    for i, name in enumerate(tool.CASES):
        row = fixtures[name]
        baseline = {key: deepcopy(row) for key in ("held", "named")}
        allocation = {key: row[key] for key in ("dev", "ino", "gid")}
        observations = [{**sample_for(baseline, allocation), "offset_seconds": offset,
            "elapsed_seconds": offset + 0.001 * (i + 1), "global_elapsed_seconds": offset + 1 + 0.001 * (i + 1),
            "within_deadline": True} for offset in tool.OFFSETS]
        cases.append({"case": name, "allocation": allocation, "baseline": baseline,
            "initial_verification": sample_for(baseline, allocation), "baseline_integrity_unchanged": True,
            "observations": observations, "baseline_reset": False})
    return {"schema": "arv2-authorized-relocation-flags-v1", "source_profile": deepcopy(tool.producer.RELOCATION_PROFILE),
        "source_profile_sha256": tool.PROFILE_SHA256, "fixture_mode": "authorized_relocation_synthetic_diagnostic",
        "cases": cases, "case_count": 2, "observation_count": 22, "initial_verification_count": 2,
        "refused_initial_integrity_count": 0, "refused_integrity_observation_count": 0,
        "complete": True, "elapsed_seconds": 31.1, "maximum_seconds": 45, "flags_available": True,
        "synthetic_only": True, **{key: False for key in tool.FALSE_FLAGS}}


def fixtures_for(report):
    return {case["case"]: deepcopy(case["baseline"]["held"]) for case in report["cases"]}


@pytest.fixture
def model():
    report = report_for()
    return SimpleNamespace(report=report, fixtures=fixtures_for(report))


@pytest.fixture
def envelope(tmp_path, monkeypatch):
    output = tmp_path / "synthetic-output"
    output.mkdir(mode=0o700)
    audit_metadata, sample_metadata = tool.audit._metadata, tool.producer._metadata

    def simulated_device(converter):
        def convert(info):
            result = converter(info)
            result["dev"] = tool.DEVICE
            return result
        return convert

    monkeypatch.setattr(tool.audit, "_metadata", simulated_device(audit_metadata))
    monkeypatch.setattr(tool.producer, "_metadata", simulated_device(sample_metadata))
    fixtures, paths = {}, {}
    for case in tool.CASES:
        child = output / case
        child.mkdir(mode=0o700)
        path = child / "final.json"
        path.write_bytes(tool.producer.probe.PAYLOAD)
        path.chmod(0o600)
        fixtures[case] = tool.producer._metadata(path.stat())
        paths[case] = path
    report = report_for(fixtures)
    report_path = output / "report.json"
    report_path.write_bytes(tool.audit._json_bytes(report))
    report_path.chmod(0o600)
    monkeypatch.setattr(tool, "OUTPUT", output)

    def publish(value):
        raw = value if type(value) is bytes else tool.audit._json_bytes(value)
        report_path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    return SimpleNamespace(output=output, paths=paths, path=report_path, report=report,
        fixtures=fixtures, publish=publish, digest=hashlib.sha256(report_path.read_bytes()).hexdigest())


def test_import_only_profile_pin():
    assert tool.producer.RELOCATION_PROFILE_SHA256 == tool.PROFILE_SHA256
    assert hashlib.sha256(tool.audit._json_bytes(tool.producer.RELOCATION_PROFILE)).hexdigest() == tool.PROFILE_SHA256
    assert len(tool.producer.probe.PAYLOAD) == 48


def test_valid_producer_shaped_report_recomputes_all_24_checks(model):
    result = tool._validate_report(model.report, model.fixtures, 0)
    assert result["diagnostic_accepted"] is True
    assert result["integrity_check_count"] == 24
    assert result["initial_verification_count"] == 2 and result["observation_count"] == 22


def test_reader_output_only_positive_and_redacted(envelope):
    result = tool.authenticate_report(envelope.digest, 0)
    assert result["report_authenticated"] is result["diagnostic_accepted"] is True
    assert result["report_sha256"] == envelope.digest
    assert result["production_publication_clearance"] is result["continuous_stability_proven"] is False
    assert result["native_attributes_authenticated"] is result["source_objects_read"] is False
    raw = tool.audit._json_bytes(result)
    for forbidden in (b"artifacts/", b"mtime_ns", b"ctime_ns", b"allocation", b"birthtime", b"uid"):
        assert forbidden not in raw


@pytest.mark.parametrize("changed", [False, True])
def test_original_producer_sample_with_substituted_io(model, monkeypatch, changed):
    case = model.report["cases"][0]
    row = deepcopy(case["baseline"]["held"])
    if changed:
        row["ctime_ns"] += 1
        row["flags"] = 64
    with monkeypatch.context() as isolated:
        isolated.setattr(tool.producer, "_metadata", lambda value: deepcopy(value))
        isolated.setattr(tool.producer.os, "fstat", lambda _fd: deepcopy(row))
        isolated.setattr(tool.producer.os, "stat", lambda *_a, **_k: deepcopy(row))
        isolated.setattr(tool.producer.os, "lseek", lambda *_a: None)
        isolated.setattr(tool.producer.os, "read", lambda _fd, bound: tool.producer.probe.PAYLOAD
                        if bound == 49 else pytest.fail("unbounded producer fixture read"))
        observed = tool.producer._sample(101, 102, case["baseline"],
                                        tuple(case["allocation"][key] for key in ("dev", "ino", "gid")))
    result, fields = tool._check_sample(observed, case["baseline"], case["allocation"])
    assert result is (not changed)
    assert fields == ({"ctime_ns", "flags"} if changed else set())


@pytest.mark.parametrize("case_index", range(2))
@pytest.mark.parametrize("check_index", range(12))
def test_each_integrity_claim_is_independently_recomputed(model, case_index, check_index):
    case = model.report["cases"][case_index]
    check = case["initial_verification"] if check_index == 0 else case["observations"][check_index - 1]
    check["integrity_unchanged"] = False
    with pytest.raises(tool.audit.Refusal, match="sample_integrity_claim"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("field", tool.SAMPLE_FIELDS)
@pytest.mark.parametrize("row_name", tool.ROWS)
def test_every_metadata_field_and_row_drift_cannot_keep_green_claim(model, field, row_name):
    sample = model.report["cases"][0]["observations"][0]
    value = sample[row_name][field]
    sample[row_name][field] = (not value if type(value) is bool else 7 if value is None else value + 1)
    with pytest.raises(tool.audit.Refusal):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("field,value", [("dev", tool.DEVICE + 1), ("ino", 999), ("gid", 999)])
def test_allocation_triplet_cannot_be_rebased(model, field, value):
    model.report["cases"][0]["allocation"][field] = value
    with pytest.raises(tool.audit.Refusal):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("field,value", [("uid", os.getuid() + 1), ("mode", 0o644),
    ("nlink", 2), ("size", 49), ("regular", False), ("ino", 9999), ("gid", 9999)])
def test_consistent_unsafe_metadata_is_not_an_unchanged_safe_baseline(model, field, value):
    case = model.report["cases"][0]
    for row in case["baseline"].values():
        row[field] = value
    for sample in [case["initial_verification"], *case["observations"]]:
        for row_name in tool.ROWS:
            sample[row_name][field] = value
    model.fixtures["direct_final"][field] = value
    # All held/named/baseline fields agree and all change lists are empty; only
    # the independent allocation/private-field predicates make the claim false.
    with pytest.raises(tool.audit.Refusal, match="sample_integrity_claim"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("field", tool.SAMPLE_FIELDS)
def test_every_current_fixture_baseline_field_is_required(model, field):
    value = model.fixtures["direct_final"][field]
    model.fixtures["direct_final"][field] = (not value if type(value) is bool else 7 if value is None else value + 1)
    assert tool._validate_report(model.report, model.fixtures, 0)["diagnostic_accepted"] is False


@pytest.mark.parametrize("field,value", [("uid", -1), ("size", True), ("regular", 1), ("mode", "600"),
    ("flags", "0"), ("birthtime_ns", True), ("birthtime_seconds", float("nan")), ("dev", 1.0)])
def test_metadata_shape_type_refusals(model, field, value):
    model.report["cases"][0]["baseline"]["held"][field] = value
    with pytest.raises(tool.audit.Refusal):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("key", tool.CHANGES)
def test_changed_field_claims_exact_and_ordered(model, key):
    model.report["cases"][0]["observations"][0][key] = ["ctime_ns"]
    with pytest.raises(tool.audit.Refusal, match="sample_changed_fields"):
        tool._validate_report(model.report, model.fixtures, 0)


def make_refused(report):
    case = report["cases"][0]
    for sample in case["observations"][3:]:
        for key in tool.ROWS:
            sample[key]["ctime_ns"] += 1
            sample[key]["flags"] = 64
        refresh_sample(sample, case["baseline"], case["allocation"])
    report["refused_integrity_observation_count"] = 8


def test_complete_internally_refused_report_is_authenticated_not_accepted(envelope):
    make_refused(envelope.report)
    digest = envelope.publish(envelope.report)
    result = tool.authenticate_report(digest, 1)
    assert result["report_authenticated"] is True and result["complete"] is True
    assert result["diagnostic_accepted"] is False
    assert result["refused_integrity_observation_count"] == 8
    assert result["changed_fields"]["direct_final"] == ["ctime_ns", "flags"]


def test_changed_field_producer_order_not_canonical_order(model):
    make_refused(model.report)
    sample = model.report["cases"][0]["observations"][3]
    assert sample["held_changed"] == ["ctime_ns", "flags"]
    # mode is inserted before flags by the producer, after flags alphabetically.
    for key in tool.ROWS:
        sample[key]["mode"] = 0o640
    refresh_sample(sample, model.report["cases"][0]["baseline"], model.report["cases"][0]["allocation"])
    assert sample["held_changed"] == ["ctime_ns", "mode", "flags"]
    assert tool._validate_report(model.report, model.fixtures, 1)["diagnostic_accepted"] is False
    sample["held_changed"].sort()
    with pytest.raises(tool.audit.Refusal, match="sample_changed_fields"):
        tool._validate_report(model.report, model.fixtures, 1)


def test_failed_initial_check_remains_spent_for_all_later_samples(model):
    case = model.report["cases"][0]
    initial = case["initial_verification"]
    initial["readback_sha256"] = "a" * 64
    refresh_sample(initial, case["baseline"], case["allocation"])
    case["baseline_integrity_unchanged"] = False
    model.report["refused_initial_integrity_count"] = 1
    for sample in case["observations"]:
        refresh_sample(sample, case["baseline"], case["allocation"], baseline_ok=False)
    model.report["refused_integrity_observation_count"] = 11
    assert tool._validate_report(model.report, model.fixtures, 1)["diagnostic_accepted"] is False
    case["observations"][0]["integrity_unchanged"] = True
    with pytest.raises(tool.audit.Refusal, match="sample_integrity_claim"):
        tool._validate_report(model.report, model.fixtures, 1)


@pytest.mark.parametrize("field,value", [("readback_matches", False), ("readback_sha256", "a" * 64),
                                      ("readback_sha256", "A" * 64), ("integrity_unchanged", 1)])
def test_payload_and_integrity_claims(model, field, value):
    model.report["cases"][0]["initial_verification"][field] = value
    with pytest.raises(tool.audit.Refusal):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("field", ["case_count", "observation_count", "initial_verification_count",
                                  "refused_initial_integrity_count", "refused_integrity_observation_count"])
def test_counts_exact_not_only_flags(model, field):
    model.report[field] += 1
    with pytest.raises(tool.audit.Refusal, match="report_counts"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("field", ["case_count", "observation_count", "initial_verification_count",
                                  "refused_initial_integrity_count", "refused_integrity_observation_count"])
def test_count_booleans_never_counts(model, field):
    model.report[field] = False
    with pytest.raises(tool.audit.Refusal, match="report_counts"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("field", tool.FALSE_FLAGS)
def test_false_boundaries_stay_false(model, field):
    model.report[field] = True
    with pytest.raises(tool.audit.Refusal, match="report_flags"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("change", ["schema", "fixture_mode", "source_profile_sha256", "source_profile"])
def test_report_pins_exact(model, change):
    if change == "source_profile":
        model.report[change]["metadata_changes_permitted"] = True
    else:
        model.report[change] = "wrong"
    with pytest.raises(tool.audit.Refusal, match="report_profile"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("target", ["report", "case", "baseline", "sample", "sample_metadata", "allocation"])
def test_exact_keysets(model, target):
    case = model.report["cases"][0]
    subject = {"report": model.report, "case": case, "baseline": case["baseline"],
        "sample": case["initial_verification"], "sample_metadata": case["initial_verification"]["held"],
        "allocation": case["allocation"]}[target]
    subject["surprise"] = True
    with pytest.raises(tool.audit.Refusal):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("value", [True, -1, 256, "0", None])
def test_actual_exit_shape(model, value):
    with pytest.raises(tool.audit.Refusal, match="probe_exit_code"):
        tool._validate_report(model.report, model.fixtures, value)


@pytest.mark.parametrize("exit_code", [1, 2, 137, 255])
def test_actual_failed_exit_never_accepted(model, exit_code):
    assert tool._validate_report(model.report, model.fixtures, exit_code)["diagnostic_accepted"] is False


@pytest.mark.parametrize("index", range(11))
def test_each_schedule_offset_pinned(model, index):
    model.report["cases"][0]["observations"][index]["offset_seconds"] = -1
    with pytest.raises(tool.audit.Refusal, match="sample_timing"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("change", ["baseline_reset", "baseline_claim", "missing_case", "missing_sample", "case_order"])
def test_no_reset_and_exact_inventory_claims(model, change):
    case = model.report["cases"][0]
    if change == "baseline_reset":
        case["baseline_reset"] = True
    elif change == "baseline_claim":
        case["baseline_integrity_unchanged"] = False
    elif change == "missing_case":
        model.report["cases"].pop()
    elif change == "missing_sample":
        case["observations"].pop()
    else:
        model.report["cases"].reverse()
    with pytest.raises(tool.audit.Refusal):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("field,value", [("elapsed_seconds", -1), ("elapsed_seconds", True),
    ("elapsed_seconds", float("inf")), ("global_elapsed_seconds", -1), ("within_deadline", 1)])
def test_invalid_sample_timing(model, field, value):
    model.report["cases"][0]["observations"][0][field] = value
    with pytest.raises(tool.audit.Refusal, match="sample_timing"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("change", ["report_deadline", "sample_deadline", "flags_missing", "complete_false", "final_drift"])
def test_authenticated_negative_conditions_never_accepted(model, change):
    if change == "report_deadline":
        model.report["elapsed_seconds"] = 45.1
    elif change == "sample_deadline":
        model.report["cases"][0]["observations"][-1]["within_deadline"] = False
        model.report["complete"] = False
    elif change == "complete_false":
        model.report["complete"] = False
    elif change == "final_drift":
        model.fixtures["direct_final"]["ctime_ns"] += 1
    else:
        for case in model.report["cases"]:
            for row in case["baseline"].values():
                row["flags"] = None
            for sample in [case["initial_verification"], *case["observations"]]:
                for row_name in tool.ROWS:
                    sample[row_name]["flags"] = None
        model.report["flags_available"] = False
    assert tool._validate_report(model.report, model.fixtures, 0)["diagnostic_accepted"] is False


def test_false_flags_available_claim(model):
    model.report["flags_available"] = False
    with pytest.raises(tool.audit.Refusal, match="report_flags_available_claim"):
        tool._validate_report(model.report, model.fixtures, 0)


def test_round_robin_timing(model):
    model.report["cases"][1]["observations"][0]["global_elapsed_seconds"] = 1
    with pytest.raises(tool.audit.Refusal, match="sample_round_robin_timing"):
        tool._validate_report(model.report, model.fixtures, 0)


@pytest.mark.parametrize("raw,code", [(b'{"x":1,"x":2}\n', "duplicate"), (b'{"x":NaN}\n', "nonfinite"),
    (b'{"x":Infinity}\n', "nonfinite"), (b'{"x":1e999}\n', "json_invalid"),
    (b'{ "x":1}\n', "noncanonical"), (b'not json', "json_invalid")])
def test_canonical_json_and_duplicate_nonfinite_refusals(envelope, raw, code):
    with pytest.raises(tool.audit.Refusal, match=code):
        tool.authenticate_report(envelope.publish(raw), 0)


def test_digest_precedes_json_and_fixture_read(envelope, monkeypatch):
    envelope.publish(b'not json')
    reader = tool._read_file
    def guarded(*args, **kwargs):
        assert not kwargs.get("fixture"), "fixture read before hash check"
        return reader(*args, **kwargs)
    monkeypatch.setattr(tool, "_read_file", guarded)
    with pytest.raises(tool.audit.Refusal, match="digest_mismatch"):
        tool.authenticate_report("a" * 64, 0)


@pytest.mark.parametrize("target", ["root", "direct_final", "pending_link", "report", "fixture"])
def test_private_modes(envelope, target):
    path = {"root": envelope.output, "direct_final": envelope.output / "direct_final",
        "pending_link": envelope.output / "pending_link", "report": envelope.path,
        "fixture": envelope.paths["direct_final"]}[target]
    path.chmod(0o755 if path.is_dir() else 0o644)
    with pytest.raises(tool.audit.Refusal, match="security"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("target", ["root", "direct_final", "pending_link"])
def test_extra_inventory_spends_envelope(envelope, target):
    directory = envelope.output if target == "root" else envelope.output / target
    (directory / "unexpected.pending").write_bytes(b"retained")
    with pytest.raises(tool.audit.Refusal, match="inventory"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("target", ["report", "direct_final", "pending_link"])
def test_hardlinked_files_refused(envelope, target, tmp_path):
    path = envelope.path if target == "report" else envelope.paths[target]
    os.link(path, tmp_path / "extra-link")
    with pytest.raises(tool.audit.Refusal, match="file_security"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("target", ["report", "direct_final", "pending_link"])
def test_leaf_symlinks_refused(envelope, target, tmp_path):
    path = envelope.path if target == "report" else envelope.paths[target]
    moved = tmp_path / "retained-leaf"
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises((tool.audit.Refusal, OSError)):
        tool.authenticate_report(envelope.digest, 0)


def test_component_symlink_refused(envelope, tmp_path, monkeypatch):
    alias = tmp_path / "alias"
    alias.symlink_to(envelope.output, target_is_directory=True)
    monkeypatch.setattr(tool, "OUTPUT", alias)
    with pytest.raises(OSError):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("length", [0, tool.MAX_REPORT_BYTES + 1])
def test_report_size_bounds(envelope, length):
    with pytest.raises(tool.audit.Refusal, match="file_security"):
        tool.authenticate_report(envelope.publish(b"x" * length), 0)


@pytest.mark.parametrize("payload", [b"a" * 47, b"a" * 48, b"a" * 49])
def test_fixed_fixture_bytes(envelope, payload):
    envelope.paths["direct_final"].write_bytes(payload)
    with pytest.raises(tool.audit.Refusal):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("field", sorted(tool.ENVELOPE_FIELDS))
def test_every_held_metadata_field_is_pinned(envelope, monkeypatch, field):
    original = tool._envelope_metadata
    calls = 0
    def drift(info):
        nonlocal calls
        row = original(info)
        if stat.S_ISREG(info.st_mode) and info.st_size == envelope.path.stat().st_size:
            calls += 1
            if calls >= 2:
                row[field] += 1
        return row
    monkeypatch.setattr(tool, "_envelope_metadata", drift)
    with pytest.raises(tool.audit.Refusal, match="identity|changed"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("field", sorted(tool.ENVELOPE_FIELDS))
def test_every_directory_metadata_field_is_pinned(envelope, monkeypatch, field):
    original = tool._named_directory
    def drift(path):
        row = original(path)
        row[field] += 1
        return row
    monkeypatch.setattr(tool, "_named_directory", drift)
    with pytest.raises(tool.audit.Refusal, match="identity"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("target", ["root", "direct_final", "pending_link"])
@pytest.mark.parametrize("at_call", [2, 3])
@pytest.mark.parametrize("field", sorted(tool.ENVELOPE_FIELDS))
def test_late_directory_full_metadata_rechecks(envelope, monkeypatch, target, at_call, field):
    original = tool._named_directory
    calls = 0
    path = envelope.output if target == "root" else envelope.output / target
    def drift(named_path):
        nonlocal calls
        row = original(named_path)
        if named_path == path:
            calls += 1
            if calls >= at_call:
                row[field] += 1
        return row
    monkeypatch.setattr(tool, "_named_directory", drift)
    with pytest.raises(tool.audit.Refusal, match="directory_changed"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("target", ["report", "direct_final", "pending_link"])
@pytest.mark.parametrize("field", sorted(tool.ENVELOPE_FIELDS))
def test_late_file_full_metadata_rechecks(envelope, monkeypatch, target, field):
    original = tool._envelope_metadata
    path = envelope.path if target == "report" else envelope.paths[target]
    target_inode = path.stat().st_ino
    calls = 0
    def drift(info):
        nonlocal calls
        row = original(info)
        if info.st_ino == target_inode:
            calls += 1
            if calls >= 5:
                row[field] += 1
        return row
    monkeypatch.setattr(tool, "_envelope_metadata", drift)
    with pytest.raises(tool.audit.Refusal, match="output_file_changed"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("target", ["root", "direct_final", "pending_link"])
def test_late_inventory_recheck(envelope, monkeypatch, target):
    original = tool.os.listdir
    path = envelope.output if target == "root" else envelope.output / target
    inode = path.stat().st_ino
    calls = 0
    def drift(fd):
        nonlocal calls
        result = original(fd)
        if type(fd) is int and tool.os.fstat(fd).st_ino == inode:
            calls += 1
            if calls >= 2:
                return result + ["retained.pending"]
        return result
    monkeypatch.setattr(tool.os, "listdir", drift)
    with pytest.raises(tool.audit.Refusal, match="inventory"):
        tool.authenticate_report(envelope.digest, 0)


def test_device_exact_not_discovered_from_host(envelope, monkeypatch):
    original = tool.audit._metadata
    def drift(info):
        row = original(info)
        row["dev"] += 1
        return row
    monkeypatch.setattr(tool.audit, "_metadata", drift)
    with pytest.raises(tool.audit.Refusal, match="output_metadata_device"):
        tool.authenticate_report(envelope.digest, 0)


def test_payload_read_is_bounded(envelope, monkeypatch):
    original = tool.os.read
    requested = []
    def bounded(fd, size):
        requested.append(size)
        assert 0 < size <= 65536
        return original(fd, size)
    monkeypatch.setattr(tool.os, "read", bounded)
    assert tool.authenticate_report(envelope.digest, 0)["diagnostic_accepted"]
    assert requested.count(49) == 2


def test_mid_read_size_growth_refuses(envelope, monkeypatch):
    monkeypatch.setattr(tool.os, "read", lambda _fd, size: b"x" * size)
    with pytest.raises(tool.audit.Refusal, match="output_read_size"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("digest", ["", "g" * 64, "A" * 64, True, None])
def test_expected_hash_shape_before_open(monkeypatch, digest):
    monkeypatch.setattr(tool.audit, "_open_absolute_directory", lambda _p: pytest.fail("opened before digest check"))
    with pytest.raises(tool.audit.Refusal, match="expected_digest"):
        tool.authenticate_report(digest, 0)


def test_fixed_root_and_profile_gate_without_evidence(monkeypatch):
    tool._gate(tool.PROFILE_SHA256)
    with pytest.raises(tool.audit.Refusal, match="profile"):
        tool._gate("a" * 64)
    monkeypatch.setattr(tool, "ROOT", Path("/unapproved"))
    with pytest.raises(tool.audit.Refusal, match="fixed_root"):
        tool._gate(tool.PROFILE_SHA256)


def test_cli_budget_and_actual_exit(monkeypatch, capsys):
    events = []
    monkeypatch.setattr(tool, "_budget", lambda: nullcontext())
    monkeypatch.setattr(tool, "_gate", lambda profile: events.append(profile))
    def authenticate(digest, exit_code):
        events.append((digest, exit_code))
        return {"diagnostic_accepted": False, "report_authenticated": True}
    monkeypatch.setattr(tool, "authenticate_report", authenticate)
    assert tool.main(["--expected-profile-sha256", tool.PROFILE_SHA256,
                      "--expected-report-sha256", "a" * 64, "--probe-exit-code", "1"]) == 1
    assert events == [tool.PROFILE_SHA256, ("a" * 64, 1)]
    assert json.loads(capsys.readouterr().out)["report_authenticated"] is True


@pytest.mark.parametrize("error,code", [(OSError("secret/native"), "verification_operation_refused"),
    (tool.audit.Refusal("bad/path"), "verification_operation_refused"),
    (tool.audit.Refusal("report_digest_mismatch"), "report_digest_mismatch")])
def test_entrypoint_redacts_exception_text(monkeypatch, capsys, error, code):
    def fail(_argv):
        raise error
    monkeypatch.setattr(tool, "main", fail)
    assert tool._entrypoint([]) == 1
    result = json.loads(capsys.readouterr().err)
    assert result["refusal_code"] == code and result["evidence_retained"] is True
    assert result["report_authenticated"] is result["production_publication_clearance"] is False


def test_cooperative_budget_installs_and_restores_timer(monkeypatch):
    installed, handlers = [], []
    monkeypatch.setattr(tool.signal, "getsignal", lambda _s: "prior")
    monkeypatch.setattr(tool.signal, "getitimer", lambda _s: (0.0, 0.0))
    monkeypatch.setattr(tool.signal, "signal", lambda signal, handler: handlers.append((signal, handler)))
    monkeypatch.setattr(tool.signal, "setitimer", lambda signal, seconds: installed.append((signal, seconds)))
    with tool._budget():
        with pytest.raises(tool.audit.Refusal, match="deadline"):
            handlers[0][1](None, None)
    assert [seconds for _s, seconds in installed] == [60, 0]
    assert handlers[-1][1] == "prior"


def test_existing_timer_is_not_overwritten(monkeypatch):
    monkeypatch.setattr(tool.signal, "getitimer", lambda _s: (1.0, 0.0))
    monkeypatch.setattr(tool.signal, "signal", lambda *_a: pytest.fail("overwrote timer"))
    with pytest.raises(tool.audit.Refusal, match="existing_timer"):
        with tool._budget():
            pytest.fail("entered")


@pytest.mark.parametrize("elapsed", [60, 60.001])
def test_cooperative_budget_checks_late_native_return_and_equal_boundary(monkeypatch, elapsed):
    values = iter((100.0, 100.0 + elapsed))
    timers, handlers = [], []
    monkeypatch.setattr(tool.time, "monotonic", lambda: next(values))
    monkeypatch.setattr(tool.signal, "getsignal", lambda _s: "prior")
    monkeypatch.setattr(tool.signal, "getitimer", lambda _s: (0.0, 0.0))
    monkeypatch.setattr(tool.signal, "signal", lambda signal, handler: handlers.append((signal, handler)))
    monkeypatch.setattr(tool.signal, "setitimer", lambda signal, seconds: timers.append((signal, seconds)))
    with pytest.raises(tool.audit.Refusal, match="deadline"):
        with tool._budget():
            pass
    assert [seconds for _s, seconds in timers] == [60, 0]
    assert handlers[-1][1] == "prior"
