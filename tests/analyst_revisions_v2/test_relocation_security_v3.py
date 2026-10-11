"""Synthetic ABI/object adversaries only; never open the retained vintage path."""
import ctypes
import errno
import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from scripts import arv2_relocation_security_v3 as policy
from scripts import arv2_relocation_security_v2 as prior
from scripts import audit_arv2_relocation as real_audit


@pytest.fixture(autouse=True)
def no_retained_artifact_open(monkeypatch):
    # Guard the original module too: an in-memory mutation with detached
    # globals must not bypass the per-test synthetic policy.audit substitute.
    opener = real_audit._open_absolute_directory
    artifact_root = Path(__file__).resolve().parents[2] / "artifacts"

    def guarded(path):
        candidate = Path(path)
        if candidate == artifact_root or artifact_root in candidate.parents:
            raise AssertionError("retained artifact opener forbidden in synthetic tests")
        return opener(path)

    monkeypatch.setattr(real_audit, "_open_absolute_directory", guarded)


def test_canonical_artifact_opener_tripwire_refuses_before_open():
    with pytest.raises(AssertionError, match="retained artifact opener forbidden"):
        real_audit._open_absolute_directory(policy.VINTAGE_PATH)


class Native:
    def __init__(self, values):
        self.values = values
        self.names = b"\0".join(sorted(values)) + b"\0"
        self.calls, self.list_results, self.get_results, self.acl_errors = [], [], [], []
        self.after_get = lambda: None

    def acl_get_fd_np(self, fd, kind):
        self.calls.append(("acl", fd, kind))
        error = self.acl_errors.pop(0) if self.acl_errors else errno.ENOENT
        ctypes.set_errno(error)
        return None

    def flistxattr(self, fd, buffer, size, options):
        self.calls.append(("list", fd, size, options))
        raw = self.list_results.pop(0) if self.list_results else self.names
        if not isinstance(raw, bytes):
            return raw
        ctypes.memmove(buffer, raw, min(size, len(raw)))
        return len(raw)

    def fgetxattr(self, fd, name, buffer, size, position, options):
        self.calls.append(("get", fd, name, size, position, options))
        value = self.values[name]
        ctypes.memmove(buffer, value, min(size, len(value)))
        self.after_get()
        return self.get_results.pop(0) if self.get_results else len(value)


@pytest.fixture
def model(monkeypatch):
    # Only synthetic values are used. The production fingerprints below are
    # independently asserted; no actual private value is reconstructed/read.
    values = {name: bytes([65 + i]) * size
              for i, (name, size, _digest) in enumerate(policy.XATTR_PINS)}
    pins = tuple((name, len(value), hashlib.sha256(value).hexdigest())
                 for name, value in values.items())
    monkeypatch.setattr(policy, "XATTR_PINS", pins)
    native = Native(values)
    pinned = policy._pinned_metadata()
    state = SimpleNamespace(metadata={41: pinned, 42: pinned, 43: (
        pinned[0], pinned[1] + 1, stat.S_IFREG | 0o600, 501, 20, 1, 10, 20, 30, 0)},
        opened=[], closed=[], native=native, values=values, pins=pins,
        named_error=None, on_open=lambda: None)

    def metadata(fd):
        return state.metadata[fd]

    def opening(path):
        state.opened.append(path)
        assert path == policy.VINTAGE_PATH
        state.on_open()
        if state.named_error:
            raise state.named_error
        return 42

    monkeypatch.setattr(policy, "_metadata", metadata)
    monkeypatch.setattr(policy.legacy, "_metadata", metadata)
    monkeypatch.setattr(policy.legacy, "_native", lambda: native)
    monkeypatch.setattr(policy, "audit", SimpleNamespace(
        _open_absolute_directory=opening, Refusal=policy.audit.Refusal))
    monkeypatch.setattr(policy, "os", SimpleNamespace(close=state.closed.append))
    return state


def changed(values, index):
    result = list(values)
    result[index] += 1 if index != 2 else 0o20
    return tuple(result)


def test_static_owner_candidate_pins_and_fresh_policy_record():
    assert str(policy.VINTAGE_PATH) == (
        "/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/artifacts/"
        "analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z")
    assert dict(policy.VINTAGE_METADATA) == {
        "dev": 16777231, "ino": 8124879, "mode": 16832, "uid": 501, "gid": 20,
        "nlink": 7, "size": 224, "mtime_ns": 1789346095000000000,
        "ctime_ns": 1791348969446992676, "flags": 32768}
    assert policy.XATTR_PINS == (
        (b"com.apple.fileprovider.dir#N", 1, "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"),
        (b"com.apple.macl", 72, "38b3d95534bbdeb72e84fe595e13501eaff68b0d4fcd615e51fc4e0b1194375a"),
        (b"com.apple.provenance", 11, "07ccfbc460d4b2eb75da90b5f2d84baf64b4dbf0059bdc6cd4c93d39d3baa4c7"),
        (b"com.apple.quarantine", 15, "c8aeee7d17eb7062492cdd12a92c6e3d471b00dd006fc1174a7dcee37609c18a"))
    record = policy.policy_record()
    record["vintage_metadata"]["ino"] = 0
    record["xattr_pins"]["com.apple.macl"]["sha256"] = "0" * 64
    assert policy.policy_record()["vintage_metadata"]["ino"] == 8124879
    assert policy.policy_record()["xattr_pins"]["com.apple.macl"]["sha256"].startswith("38b3")
    with pytest.raises(TypeError):
        policy.VINTAGE_METADATA["ino"] = 0
    assert json.loads(json.dumps(policy.policy_record())) == policy.policy_record()


def test_exact_vintage_only_returns_fingerprints(model):
    result = policy.snapshot(41)
    assert result == {"acl_empty": True, "policy_id": policy.POLICY_ID,
                      "xattrs": {name.decode(): {"size": size, "sha256": digest}
                                 for name, size, digest in model.pins}}
    assert model.opened == [policy.VINTAGE_PATH] * 2
    assert model.closed == [42, 42]
    assert [call[0] for call in model.native.calls] == [
        "acl", "list", "get", "get", "get", "get", "list", "acl"]
    gets = [call for call in model.native.calls if call[0] == "get"]
    assert [call[3] for call in gets] == [65536, 65535, 65463, 65452]
    assert all(call[-2:] == (0, policy.legacy.XATTR_SHOWCOMPRESSION) for call in gets)
    assert b"B" * 72 not in json.dumps(result).encode()


@pytest.mark.parametrize("index", range(10))
def test_each_initial_named_metadata_pin_is_required(model, index):
    model.metadata[42] = changed(model.metadata[42], index)
    with pytest.raises(policy.Refusal, match="named_metadata"):
        policy.snapshot(41)
    assert not model.native.calls
    assert model.closed == [42]


@pytest.mark.parametrize("index", range(10))
def test_each_initial_held_metadata_pin_is_required(model, index):
    model.metadata[41] = changed(model.metadata[41], index)
    with pytest.raises(policy.legacy.Refusal):
        policy.snapshot(41)
    assert not any(call[0] == "get" for call in model.native.calls)


@pytest.mark.parametrize("index", range(10))
def test_each_final_held_metadata_pin_is_required(model, index):
    def drift():
        model.metadata[41] = changed(model.metadata[41], index)
        model.native.after_get = lambda: None
    model.native.after_get = drift
    with pytest.raises(policy.Refusal, match="held_metadata"):
        policy.snapshot(41)


@pytest.mark.parametrize("index", range(10))
def test_each_final_named_metadata_pin_is_required(model, index):
    def drift():
        model.metadata[42] = changed(model.metadata[42], index)
        model.native.after_get = lambda: None
    model.native.after_get = drift
    with pytest.raises(policy.Refusal, match="named_metadata"):
        policy.snapshot(41)
    assert model.closed == [42, 42]


@pytest.mark.parametrize("mode", [stat.S_IFREG | 0o700, stat.S_IFLNK | 0o700])
def test_same_device_inode_does_not_allow_non_directory(model, mode):
    values = list(model.metadata[41])
    values[2] = mode
    model.metadata[41] = tuple(values)
    with pytest.raises(policy.Refusal, match="held_metadata"):
        policy.snapshot(41)
    assert not model.native.calls


@pytest.mark.parametrize("kind", ["symlink", "missing", "permission", "invalid"])
def test_named_path_refuses_without_values_and_redacts_exception(model, kind):
    model.named_error = (policy.audit.Refusal("PRIVATE") if kind == "invalid"
                         else OSError("PRIVATE-" + kind))
    with pytest.raises(policy.Refusal, match="^vintage_named_path_unavailable$"):
        policy.snapshot(41)
    assert not model.native.calls


@pytest.mark.parametrize("raw", [b"", b"com.apple.provenance\0",
    b"com.apple.fileprovider.dir#N\0com.apple.macl\0com.apple.quarantine\0",
    b"com.apple.fileprovider.dir#N\0com.apple.macl\0com.apple.provenance\0com.apple.quarantine\0extra\0"])
def test_missing_or_extra_names_refuse_before_any_value(model, raw):
    model.native.names = raw
    with pytest.raises(policy.Refusal, match="names_not_exact"):
        policy.snapshot(41)
    assert not any(call[0] == "get" for call in model.native.calls)


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("change", ["size", "digest"])
def test_each_value_length_and_hash_pin_is_required(model, index, change):
    name = model.pins[index][0]
    model.native.values[name] = (b"z" * len(model.values[name]) if change == "digest"
                                  else model.values[name] + b"z")
    with pytest.raises(policy.Refusal, match="fingerprint_changed"):
        policy.snapshot(41)


@pytest.mark.parametrize("count", [-1, 65537, True, None])
def test_native_value_errors_and_bounds_fail_closed(model, count):
    model.native.get_results = [count]
    with pytest.raises(policy.Refusal, match="value unavailable"):
        policy.snapshot(41)
    assert len([call for call in model.native.calls if call[0] == "get"]) == 1


def test_remaining_total_bound_not_reset_between_values(model):
    model.native.get_results = [1, 65536]
    with pytest.raises(policy.Refusal, match="value unavailable"):
        policy.snapshot(41)


def test_names_drift_after_values_refuses(model):
    model.native.list_results = [model.native.names, b"com.apple.provenance\0"]
    with pytest.raises(policy.Refusal, match="names changed"):
        policy.snapshot(41)


@pytest.mark.parametrize("at_end", [False, True])
def test_legacy_acl_guard_runs_at_both_endpoints(model, at_end):
    model.native.acl_errors = [errno.ENOENT, errno.EACCES] if at_end else [errno.EACCES]
    with pytest.raises(policy.legacy.Refusal, match="ACL unavailable"):
        policy.snapshot(41)
    assert any(call[0] == "get" for call in model.native.calls) is at_end


@pytest.mark.parametrize("directory", [False, True])
def test_other_leaf_or_directory_cannot_receive_exception(model, directory):
    if directory:
        values = list(model.metadata[43])
        values[2] = stat.S_IFDIR | 0o700
        model.metadata[43] = tuple(values)
    with pytest.raises(policy.legacy.Refusal, match="unapproved"):
        policy.snapshot(43)
    assert not any(call[0] == "get" for call in model.native.calls)
    assert policy.legacy.ALLOWED_XATTRS == frozenset({b"com.apple.provenance"})


def test_other_objects_delegate_to_original_provenance_observer(model):
    model.native.names = b"com.apple.provenance\0"
    result = policy.snapshot(43)
    assert result == {"acl_empty": True, "xattrs": {"com.apple.provenance": {
        "size": 11, "sha256": hashlib.sha256(model.values[b"com.apple.provenance"]).hexdigest()}}}
    assert model.opened == [policy.VINTAGE_PATH] * 2
    assert "policy_id" not in result


def test_replaced_vintage_cannot_fall_through_to_provenance_only(model):
    model.metadata[42] = model.metadata[43]
    model.native.names = b"com.apple.provenance\0"
    with pytest.raises(policy.Refusal, match="named_metadata"):
        policy.snapshot(43)
    assert not model.native.calls


def test_original_policy_still_refuses_vintage_extra_names(model):
    with pytest.raises(policy.legacy.Refusal, match="unapproved"):
        policy.legacy.snapshot(41)
    assert not any(call[0] == "get" for call in model.native.calls)


@pytest.mark.parametrize("raw", [b"no-terminator", b"\0", b"a\0a\0", b"a\0\0", b"x" * 128 + b"\0"])
def test_names_only_census_refuses_malformed_names(model, raw):
    model.native.names = raw
    with pytest.raises(policy.Refusal, match="malformed"):
        policy._names(model.native, 41)


@pytest.mark.parametrize("count", [-1, 8193, True, None])
def test_names_only_census_refuses_native_errors_and_bounds(model, count):
    model.native.list_results = [count]
    with pytest.raises(policy.Refusal, match="name census"):
        policy._names(model.native, 41)
    assert not any(call[0] == "get" for call in model.native.calls)


def test_names_only_census_is_non_admitting_and_bounded(model):
    model.native.names = b"unknown\0com.apple.macl\0"
    assert policy._names(model.native, 41) == (b"com.apple.macl", b"unknown")
    assert [call[0] for call in model.native.calls] == ["list"]


@pytest.mark.parametrize("which", ["leaf", "ancestor"])
def test_real_component_opener_refuses_synthetic_symlink(tmp_path, monkeypatch, which):
    # Exercise the real component-wise no-follow opener only on newly created
    # test paths. Metadata is synthetic, and no native security API is called.
    target = tmp_path / "target"
    target.mkdir()
    (target / "leaf").mkdir()
    link = tmp_path / "link"
    link.symlink_to(target / "leaf" if which == "leaf" else target, target_is_directory=True)
    monkeypatch.setattr(policy, "VINTAGE_PATH", link if which == "leaf" else link / "leaf")
    monkeypatch.setattr(policy, "_metadata", lambda _fd: policy._pinned_metadata())
    with pytest.raises(policy.Refusal, match="named_path_unavailable"):
        policy._check_named_vintage()


def test_real_component_opener_checks_synthetic_named_directory(tmp_path, monkeypatch):
    path = tmp_path / "named-synthetic-directory"
    path.mkdir()
    monkeypatch.setattr(policy, "VINTAGE_PATH", path)
    monkeypatch.setattr(policy, "_metadata", lambda _fd: policy._pinned_metadata())
    policy._check_named_vintage()


@pytest.mark.parametrize("fd", [True, -1, "41", None])
def test_invalid_descriptor_refuses_before_path_or_native_api(model, fd):
    with pytest.raises(policy.Refusal, match="valid held descriptor"):
        policy.snapshot(fd)
    assert model.opened == model.native.calls == []


def test_no_mutation_network_or_global_policy_patch():
    import ast
    tree = ast.parse(Path(policy.__file__).read_text())
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attrs & {"setxattr", "fsetxattr", "removexattr", "fremovexattr", "chmod",
        "chown", "chflags", "acl_set_fd_np", "acl_set_file", "socket", "connect",
        "requests", "urlopen", "unlink", "write", "ALLOWED_XATTRS"}
    assert policy.Refusal("PRIVATE").code == "security_observation_refused"


def test_only_declared_device_differs_from_prior_vintage_baseline():
    assert policy.POLICY_ID == "arv2-relocated-source-security-v3"
    assert policy.HISTORICAL_DEVICE == prior.VINTAGE_METADATA["dev"] == 16777232
    assert policy.PROSPECTIVE_DEVICE == policy.VINTAGE_METADATA["dev"] == 16777231
    assert policy.VINTAGE_PATH == prior.VINTAGE_PATH
    assert policy.XATTR_PINS == prior.XATTR_PINS
    assert {key: value for key, value in policy.VINTAGE_METADATA.items()
            if key != "dev"} == {
        key: value for key, value in prior.VINTAGE_METADATA.items() if key != "dev"}
    expected = {
        "historical_device": 16777232,
        "prospective_device": 16777231,
        "scope": "all-held-objects-in-fixed-assessment-scope",
        "historical_device_continuity_proven": False,
        "other_metadata_waived": False}
    assert policy.policy_record()["prospective_device_baseline"] == expected
    record = policy.policy_record()
    record["prospective_device_baseline"]["prospective_device"] = 0
    assert policy.policy_record()["prospective_device_baseline"] == expected


@pytest.mark.parametrize("fd", [41, 43])
@pytest.mark.parametrize("device", [
    16777232, 16777230, 0, -1, True, None, "16777231", 16777231.0])
def test_exact_prospective_device_required_before_any_observation(model, fd, device):
    values = list(model.metadata[fd])
    values[0] = device
    model.metadata[fd] = tuple(values)
    with pytest.raises(policy.Refusal, match="^prospective_device_not_exact$"):
        policy.snapshot(fd)
    assert model.opened == model.native.calls == []


def test_prior_policy_still_refuses_new_device_without_native_values(model, monkeypatch):
    monkeypatch.setattr(prior, "_metadata", lambda fd: model.metadata[fd])
    monkeypatch.setattr(prior, "audit", policy.audit)
    monkeypatch.setattr(prior, "os", policy.os)
    with pytest.raises(prior.Refusal, match="^vintage_named_metadata_changed$"):
        prior.snapshot(41)
    assert prior.VINTAGE_METADATA["dev"] == 16777232
    assert model.closed == [42]
    assert not model.native.calls


@pytest.mark.parametrize("index", range(10))
def test_fallback_preserves_every_final_held_field(model, index):
    model.native.names = b"com.apple.provenance\0"

    def drift():
        model.metadata[43] = changed(model.metadata[43], index)
        model.native.after_get = lambda: None
    model.native.after_get = drift
    with pytest.raises(policy.legacy.Refusal, match="metadata changed"):
        policy.snapshot(43)
    assert any(call[0] == "get" for call in model.native.calls)


def test_final_named_check_still_required_for_provenance_fallback(model):
    model.native.names = b"com.apple.provenance\0"

    def drift():
        model.metadata[42] = changed(model.metadata[42], 0)
        model.native.after_get = lambda: None
    model.native.after_get = drift
    with pytest.raises(policy.Refusal, match="named_metadata"):
        policy.snapshot(43)
    assert any(call[0] == "get" for call in model.native.calls)


@pytest.mark.parametrize("device", [True, None, "16777231", 16777231.0])
def test_named_device_type_is_not_numeric_equivalence(model, device):
    values = list(model.metadata[42])
    values[0] = device
    model.metadata[42] = tuple(values)
    with pytest.raises(policy.Refusal, match="named_metadata"):
        policy.snapshot(41)
    assert model.closed == [42]
    assert not model.native.calls
