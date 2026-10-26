"""Synthetic verification only; never invoke a real source precheck or report."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

from scripts import verify_arv2_v4_assessment as tool

REAL_ROOT = tool.ROOT
REAL_OUTPUT = tool.OUTPUT


@pytest.fixture(autouse=True)
def original_evidence_tripwire(monkeypatch, tmp_path):
    # These tests never exercise broker/runtime authority. Keep the shared
    # teardown in-root in integrated runs, without importing execution code in
    # the focused --confcutdir run, which excludes unrelated root fixtures.
    if (dispatch_fence := sys.modules.get("assistant.dispatch_fence")) is not None:
        monkeypatch.setattr(dispatch_fence, "_canonical_runtime_root", lambda: tmp_path / "runtime")
    opener = tool.audit._open_absolute_directory

    def guarded(path):
        assert path != REAL_ROOT and not path.is_relative_to(REAL_ROOT / "artifacts"), "real evidence opened"
        return opener(path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("unsubstituted source/native operation")

    monkeypatch.setattr(tool.audit, "_open_absolute_directory", guarded)
    monkeypatch.setattr(tool.v1, "_read_pinned_reports", forbidden)
    monkeypatch.setattr(tool.v1, "_load_sources", forbidden)
    monkeypatch.setattr(tool.v4, "preflight_scope", forbidden)
    monkeypatch.setattr(tool.v4.policy.legacy, "_native", forbidden)
    monkeypatch.setattr(tool.v4.policy, "snapshot", forbidden)


def metadata(*, directory=False, root=False):
    return {"dev": tool.v4.policy.PROSPECTIVE_DEVICE, "ino": 12345,
            "mode": (stat.S_IFDIR | (0o755 if root else 0o700)) if directory else stat.S_IFREG | 0o600,
            "uid": os.getuid(), "gid": 20, "nlink": 3 if directory else 1,
            "size": 96 if directory else 48, "mtime_ns": 100, "ctime_ns": 200, "flags": 0}


def make_preflight(projected):
    directories, files = tool._scope_keys()
    inventory = {}
    for key, path in directories.items():
        vintage = path == tool.v4.policy.VINTAGE_PATH
        inventory[key] = {"metadata": dict(tool.v4.policy.VINTAGE_METADATA) if vintage
                          else metadata(directory=True, root=path == tool.ROOT),
                          "names": [name.decode("ascii") for name, _n, _h in tool.v4.policy.XATTR_PINS]
                          if vintage else ["com.apple.provenance"]}
    for key, path in files.items():
        inventory[key] = {"metadata": deepcopy(projected[str(path.relative_to(tool.ROOT))]["metadata"]),
                          "names": ["com.apple.provenance"]}
    return {"schema": tool.v4.PREFLIGHT_SCHEMA, "profile_sha256": tool.PROFILE_SHA256,
            "policy_id": tool.v4.policy.POLICY_ID, "directory_count": 12, "file_count": 15,
            "inventory": inventory, "elapsed_seconds": 0.25,
            "vintage_security": {"acl_empty": True, "policy_id": tool.v4.policy.POLICY_ID,
                                 "xattrs": tool.v4.policy.policy_record()["xattr_pins"]},
            **{key: False for key in tool.PREFLIGHT_FALSE}}


@pytest.fixture
def model(monkeypatch):
    historical = {key: {"kind": "file", "metadata": metadata(), "sha256": "a" * 64}
                  for key in sorted(tool.v4._source_keys())}
    for key, row in historical.items():
        row["metadata"]["dev"] = tool.v4.policy.HISTORICAL_DEVICE
        if key in tool.v4.CTIME_PROJECTION:
            row["metadata"]["ctime_ns"] = tool.v4.CTIME_PROJECTION[key][0]
    projected, receipt = tool.v4._project_sources(historical)
    observed = make_preflight(projected)
    events = []

    def reports(root):
        assert root == REAL_ROOT
        events.append("reports")
        return tuple({"census": {"entries": deepcopy(historical)}} for _i in range(2))

    def preflight():
        events.append("preflight")
        return deepcopy(observed)

    monkeypatch.setattr(tool.v1, "_read_pinned_reports", reports)
    monkeypatch.setattr(tool.v4, "preflight_scope", preflight)
    return SimpleNamespace(historical=historical, projected=projected, receipt=receipt,
                           observed=observed, events=events)


def make_report(model, *, success=True):
    report = {"schema": tool.v4.SCHEMA, "profile_sha256": tool.PROFILE_SHA256,
              "policy_id": tool.v4.policy.POLICY_ID, "policy": tool.v4.policy.policy_record(),
              "source_metadata_projection_contract": tool.v4._projection_contract(),
              "before_report_sha256": tool.v1.BEFORE_SHA, "after_report_sha256": tool.v1.AFTER_SHA,
              "complete": success, "source_reauthenticated": success,
              **{key: False for key in tool.FALSE_FLAGS}}
    if not success:
        return {**report, "refusal_type": "Refusal", "refusal_code": "source_preopen_identity"}
    directories, files = tool._scope_keys()
    report.update(preflight=deepcopy(model.observed), source_metadata_projection=deepcopy(model.receipt),
                  file_count=15, directory_count=12,
                  directory_metadata={key: deepcopy(model.observed["inventory"][key]["metadata"])
                                      for key in directories},
                  security_observations={key: deepcopy(model.observed["vintage_security"])
                                         if path == tool.v4.policy.VINTAGE_PATH else {"acl_empty": True, "xattrs": {}}
                                         for key, path in directories.items()},
                  file_security_observations={key: {"acl_empty": True, "xattrs": {}}
                                              for key in tool.v4._source_keys()},
                  loader_results={**{key: 1 for key in tool.LOADER_COUNTS}, "current_refusals": {},
                                  "vintage_refusals": {}, "manifest_pins": dict(tool.v1.MANIFESTS)})
    return report


@pytest.fixture
def envelope(tmp_path, monkeypatch, model):
    output = tmp_path / "synthetic-output"
    output.mkdir(mode=0o700)
    path = output / "report.json"
    report = make_report(model)
    path.write_bytes(tool.audit._json_bytes(report))
    path.chmod(0o600)
    monkeypatch.setattr(tool, "OUTPUT", output)
    original_metadata = tool.audit._metadata

    def synthetic_device(info):
        result = original_metadata(info)
        result["dev"] = tool.v4.policy.PROSPECTIVE_DEVICE
        return result

    monkeypatch.setattr(tool.audit, "_metadata", synthetic_device)

    def publish(value):
        raw = value if type(value) is bytes else tool.audit._json_bytes(value)
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    return SimpleNamespace(output=output, path=path, report=report, publish=publish,
                           digest=hashlib.sha256(path.read_bytes()).hexdigest())


def test_precheck_one_observation_no_allocation_or_row_output(model, monkeypatch):
    with monkeypatch.context() as guarded:
        guarded.setattr(tool.os, "mkdir", lambda *_a, **_k: pytest.fail("allocated"))
        result = tool.precheck()
    assert model.events == ["reports", "preflight"]
    assert result["projected_metadata_match"] is True
    assert result["assessment_allocated"] is result["source_reauthenticated"] is False
    assert result["file_count"] == 15 and result["directory_count"] == 12
    assert result["prospective_rows_sha256"] == model.receipt["prospective_rows_sha256"]
    assert "inventory" not in result and "loader_results" not in result
    assert b"artifacts/" not in tool.audit._json_bytes(result)


@pytest.mark.parametrize("index", range(15))
@pytest.mark.parametrize("field", sorted(tool.v4.METADATA_FIELDS - {"dev", "mode", "uid", "nlink", "flags"}))
def test_precheck_compares_each_leaf_full_metadata(model, index, field):
    relative = sorted(model.projected)[index]
    key = str((tool.ROOT / relative).relative_to(tool.ROOT.parent))
    model.observed["inventory"][key]["metadata"][field] += 1
    with pytest.raises(tool.audit.Refusal, match="^preflight_projected_metadata$"):
        tool.precheck()
    assert model.events == ["reports", "preflight"]


def test_historical_projection_failure_precedes_preflight(model):
    relative = next(iter(tool.v4.CTIME_PROJECTION))
    model.historical[relative]["metadata"]["ctime_ns"] += 1
    with pytest.raises(tool.audit.Refusal, match="historical_projection_ctime"):
        tool.precheck()
    assert model.events == ["reports"]


@pytest.mark.parametrize("change", ["missing", "extra", "directory_count", "file_count", "true_flag", "profile", "vintage"])
def test_preflight_shape_and_pins_fail_closed(model, change):
    row = model.observed
    if change == "missing":
        row["inventory"].pop(next(iter(row["inventory"])))
    elif change == "extra":
        row["inventory"]["extra"] = {}
    elif change in ("directory_count", "file_count"):
        row[change] = True
    elif change == "true_flag":
        row["source_contents_read"] = True
    elif change == "profile":
        row["profile_sha256"] = "0" * 64
    else:
        row["vintage_security"]["xattrs"]["com.apple.macl"]["size"] += 1
    with pytest.raises(tool.audit.Refusal):
        tool.precheck()


def test_report_reader_success_never_reads_original_sources_or_native(envelope, monkeypatch):
    def forbidden(*_a, **_k):
        pytest.fail("source or native observation")
    monkeypatch.setattr(tool.v1, "_read_pinned_reports", forbidden)
    monkeypatch.setattr(tool.v4, "preflight_scope", forbidden)
    result = tool.authenticate_report(envelope.digest, 0)
    assert result["report_authenticated"] is result["assessment_accepted"] is True
    assert result["report_size"] == envelope.path.stat().st_size
    assert result["file_count"] == 15
    assert result["output_acl_xattr_envelope_proven"] is False
    assert "loader_results" not in result


@pytest.mark.parametrize("exit_code", [1, -9, 137])
def test_complete_report_after_failed_exit_is_not_success(envelope, exit_code):
    result = tool.authenticate_report(envelope.digest, exit_code)
    assert result["report_authenticated"] is True
    assert result["complete"] is True
    assert result["assessment_accepted"] is False


@pytest.mark.parametrize("stages", [0, 1, 2, 3])
def test_authenticated_refusal_is_not_success_even_with_zero_exit(envelope, model, stages):
    report = make_report(model, success=False)
    if stages >= 1:
        report["preflight"] = deepcopy(model.observed)
    if stages >= 2:
        report["source_metadata_projection"] = deepcopy(model.receipt)
    if stages >= 3:
        success = make_report(model)
        report.update({key: success[key] for key in tool.CONSUMPTION_KEYS})
        report["refusal_code"] = "profile_changed_across_assessment"
    result = tool.authenticate_report(envelope.publish(report), 0)
    assert result["report_authenticated"] is True
    assert result["assessment_accepted"] is False
    assert result["refusal_code"] == report["refusal_code"]


@pytest.mark.parametrize("field", sorted(tool.FALSE_FLAGS))
@pytest.mark.parametrize("value", [True, 0])
def test_all_restrictive_flags_are_exact_false(envelope, field, value):
    report = envelope.report
    report[field] = value
    with pytest.raises(tool.audit.Refusal, match="^report_flags$"):
        tool.authenticate_report(envelope.publish(report), 0)


@pytest.mark.parametrize("field", ["schema", "profile_sha256", "policy_id", "before_report_sha256", "after_report_sha256"])
def test_all_report_pins_checked(envelope, field):
    envelope.report[field] = "wrong"
    with pytest.raises(tool.audit.Refusal, match="^report_pins$"):
        tool.authenticate_report(envelope.publish(envelope.report), 0)


@pytest.mark.parametrize("change", ["extra", "missing", "refusal", "partial", "receipt", "hash", "manifest", "boolean_count", "security", "completion"])
def test_success_contract_rejects_malformed_claims(envelope, change):
    report = envelope.report
    if change == "extra":
        report["extra"] = False
    elif change == "missing":
        report.pop("preflight")
    elif change == "refusal":
        report["refusal_code"] = "failure"
    elif change == "partial":
        report.pop("file_count")
    elif change == "receipt":
        report["source_metadata_projection"]["source_count"] = 14
    elif change == "hash":
        report["source_metadata_projection"]["historical_rows_sha256"] = "x"
    elif change == "manifest":
        report["loader_results"]["manifest_pins"][tool.v1.PUBLIC] = "0" * 64
    elif change == "boolean_count":
        report["loader_results"]["public_rows"] = True
    elif change == "completion":
        report["complete"] = 1
    else:
        report["file_security_observations"][next(iter(tool.v4._source_keys()))]["acl_empty"] = False
    with pytest.raises(tool.audit.Refusal):
        tool.authenticate_report(envelope.publish(report), 0)


@pytest.mark.parametrize("section", ["directory_metadata", "security_observations", "file_security_observations"])
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_exact_consumption_keysets(envelope, section, change):
    rows = envelope.report[section]
    if change == "missing":
        rows.pop(next(iter(rows)))
    else:
        rows["extra"] = {}
    with pytest.raises(tool.audit.Refusal):
        tool.authenticate_report(envelope.publish(envelope.report), 0)


@pytest.mark.parametrize("raw,code", [(b'{"x":1,"x":2}\n', "report_duplicate_key"),
    (b'{"x":NaN}\n', "report_nonfinite"), (b'{"x":Infinity}\n', "report_nonfinite"),
    (b'{ "x":1}\n', "report_noncanonical"), (b'{"x":1e999}\n', "report_json_invalid"),
    (b'not json', "report_json_invalid")])
def test_strict_json(envelope, raw, code):
    with pytest.raises(tool.audit.Refusal, match="^" + code + "$"):
        tool.authenticate_report(envelope.publish(raw), 0)


def test_hash_authenticates_before_json_parser(envelope, monkeypatch):
    monkeypatch.setattr(tool, "_strict_json", lambda _raw: pytest.fail("parsed unauthenticated bytes"))
    with pytest.raises(tool.audit.Refusal, match="^report_digest_mismatch$"):
        tool.authenticate_report("0" * 64, 0)


@pytest.mark.parametrize("change", ["directory_mode", "file_mode", "hardlink", "extra", "pending", "empty", "oversize", "symlink"])
def test_output_envelope_refuses_before_read(envelope, monkeypatch, change):
    if change == "directory_mode":
        envelope.output.chmod(0o750)
    elif change == "file_mode":
        envelope.path.chmod(0o640)
    elif change == "hardlink":
        os.link(envelope.path, envelope.output.parent / "second-link")
    elif change in ("extra", "pending"):
        (envelope.output / ("report.json.pending" if change == "pending" else "extra")).write_bytes(b"x")
    elif change == "empty":
        envelope.path.write_bytes(b"")
    elif change == "oversize":
        envelope.path.write_bytes(b"x" * (tool.MAX_REPORT_BYTES + 1))
    else:
        moved = envelope.output.parent / "target"
        envelope.path.rename(moved)
        envelope.path.symlink_to(moved)
    monkeypatch.setattr(tool.os, "read", lambda *_a: pytest.fail("invalid envelope read"))
    with pytest.raises(tool.audit.Refusal):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("object_kind,field", [("file", "uid"), ("file", "dev"), ("directory", "uid"), ("directory", "dev")])
def test_output_owner_and_device_are_bound(envelope, monkeypatch, object_kind, field):
    original = tool.audit._metadata
    target = (envelope.path if object_kind == "file" else envelope.output).stat().st_ino

    def changed(info):
        row = original(info)
        if info.st_ino == target:
            row[field] += 1
        return row

    monkeypatch.setattr(tool.audit, "_metadata", changed)
    with pytest.raises(tool.audit.Refusal):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("object_kind", ["file", "directory"])
def test_output_metadata_drift_after_read_refuses(envelope, monkeypatch, object_kind):
    original_read, original_metadata = tool.os.read, tool.audit._metadata
    target = (envelope.path if object_kind == "file" else envelope.output).stat().st_ino
    read = False

    def observed(fd, count):
        nonlocal read
        result = original_read(fd, count)
        read = True
        return result

    def changed(info):
        row = original_metadata(info)
        if read and info.st_ino == target:
            row["ctime_ns"] += 1
        return row

    monkeypatch.setattr(tool.os, "read", observed)
    monkeypatch.setattr(tool.audit, "_metadata", changed)
    with pytest.raises(tool.audit.Refusal, match="report_(file|directory)_changed"):
        tool.authenticate_report(envelope.digest, 0)


def test_report_open_identity_guard_precedes_read(envelope, monkeypatch):
    original = tool.os.fstat
    target = envelope.path.stat().st_ino
    original_metadata = tool.audit._metadata

    def changed(fd):
        info = original(fd)
        if info.st_ino == target:
            return SimpleNamespace(**{key: getattr(info, key) for key in (
                "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size",
                "st_mtime_ns", "st_ctime_ns", "st_flags")}, marker=True)
        return info

    def metadata_changed(info):
        result = original_metadata(info)
        if getattr(info, "marker", False):
            result["ino"] += 1
        return result

    monkeypatch.setattr(tool.os, "fstat", changed)
    monkeypatch.setattr(tool.audit, "_metadata", metadata_changed)
    monkeypatch.setattr(tool.os, "read", lambda *_a: pytest.fail("read mismatched opened file"))
    with pytest.raises(tool.audit.Refusal, match="^report_open_identity$"):
        tool.authenticate_report(envelope.digest, 0)


def test_cli_requires_modes_and_evidence_arguments():
    for args in ([], ["--precheck"], ["--report", "--expected-profile-sha256", tool.PROFILE_SHA256],
                 ["--precheck", "--expected-profile-sha256", tool.PROFILE_SHA256, "--assessment-exit-code", "0"]):
        with pytest.raises(SystemExit) as error:
            tool.main(args)
        assert error.value.code == 2


def test_cli_refusal_exit_status_and_redacted_summary(envelope, monkeypatch, capsys):
    monkeypatch.setattr(tool, "_gate", lambda _pin: None)
    args = ["--report", "--expected-profile-sha256", tool.PROFILE_SHA256,
            "--expected-report-sha256", envelope.digest, "--assessment-exit-code", "1"]
    assert tool.main(args) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["assessment_accepted"] is False


@pytest.mark.parametrize("change", ["cwd", "module", "v4_root", "v1_root", "output", "policy", "profile", "fixed_pin"])
def test_entry_gate_before_io(monkeypatch, change):
    monkeypatch.setattr(Path, "cwd", lambda: REAL_ROOT)
    if change == "cwd":
        monkeypatch.setattr(Path, "cwd", lambda: REAL_ROOT.parent)
    elif change == "module":
        monkeypatch.setattr(tool, "__file__", str(REAL_ROOT.parent / "scripts" / "other.py"))
    elif change == "v4_root":
        monkeypatch.setattr(tool.v4, "ROOT", REAL_ROOT.parent)
    elif change == "v1_root":
        monkeypatch.setattr(tool.v1, "ROOT", REAL_ROOT.parent)
    elif change == "output":
        monkeypatch.setattr(tool.v4, "OUTPUT", REAL_OUTPUT.parent)
    elif change == "policy":
        monkeypatch.setattr(tool.v4.policy, "VINTAGE_PATH", REAL_ROOT)
    elif change == "profile":
        monkeypatch.setattr(tool.v4, "profile_sha256", lambda: "0" * 64)
    pin = "0" * 64 if change == "fixed_pin" else tool.PROFILE_SHA256
    with pytest.raises(tool.audit.Refusal, match="verification_(fixed_root|profile)"):
        tool.main(["--precheck", "--expected-profile-sha256", pin])


def test_canonical_real_artifact_opener_tripwire():
    from scripts import audit_arv2_relocation as canonical
    with pytest.raises(AssertionError, match="real evidence opened"):
        canonical._open_absolute_directory(REAL_OUTPUT)


@pytest.mark.parametrize("error,expected", [
    (tool.audit.Refusal("preflight_projected_metadata"), "preflight_projected_metadata"),
    (tool.audit.Refusal("/private/path/secret"), "verification_operation_refused"),
    (OSError("secret native attribute value"), "verification_operation_refused"),
])
def test_entrypoint_emits_bounded_code_without_private_exception_text(monkeypatch, capsys, error, expected):
    def failing(_args):
        raise error
    monkeypatch.setattr(tool, "main", failing)
    assert tool._entrypoint([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    result = json.loads(captured.err)
    assert result["refusal_code"] == expected
    assert result["evidence_retained"] is True
    assert "secret" not in captured.err


def test_precheck_profile_drift_is_not_accepted(model, monkeypatch):
    monkeypatch.setattr(tool.v4, "profile_sha256", lambda: "0" * 64)
    with pytest.raises(tool.audit.Refusal, match="^precheck_profile_changed$"):
        tool.precheck()


def test_report_profile_drift_is_not_accepted(envelope, monkeypatch):
    monkeypatch.setattr(tool.v4, "profile_sha256", lambda: "0" * 64)
    with pytest.raises(tool.audit.Refusal, match="^report_profile_changed$"):
        tool.authenticate_report(envelope.digest, 0)


@pytest.mark.parametrize("relative", sorted(tool.v4.CTIME_PROJECTION))
def test_success_preflight_binds_twelve_known_accepted_ctimes(envelope, relative):
    key = str((tool.ROOT / relative).relative_to(tool.ROOT.parent))
    envelope.report["preflight"]["inventory"][key]["metadata"]["ctime_ns"] += 1
    with pytest.raises(tool.audit.Refusal, match="^report_success_preflight_ctime$"):
        tool.authenticate_report(envelope.publish(envelope.report), 0)


def test_refusal_preflight_may_record_the_actual_unaccepted_ctime(envelope, model):
    report = make_report(model, success=False)
    report["preflight"] = deepcopy(model.observed)
    relative = next(iter(tool.v4.CTIME_PROJECTION))
    key = str((tool.ROOT / relative).relative_to(tool.ROOT.parent))
    report["preflight"]["inventory"][key]["metadata"]["ctime_ns"] += 1
    result = tool.authenticate_report(envelope.publish(report), 1)
    assert result["report_authenticated"] is True and result["assessment_accepted"] is False
