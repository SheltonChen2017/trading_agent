"""Synthetic-only publisher ordering/output guards; never production sources."""
from contextlib import contextmanager
from copy import deepcopy
import dataclasses
import os
from pathlib import Path
import signal
import stat
import sys
from types import MappingProxyType, SimpleNamespace

import pytest

from scripts import publish_arv2_identity_continuity_v4 as tool

REAL_ROOT, REAL_OUTPUT = tool.ROOT, tool.OUTPUT


def forbidden(*_args, **_kwargs):
    raise AssertionError("forbidden source/native/build/load boundary")


@pytest.fixture(autouse=True)
def tripwires(monkeypatch):
    opening = tool.audit._open_absolute_directory
    source_open = tool.builder.source._open_directory_path

    def checked(path):
        assert not path.is_relative_to(REAL_ROOT / "artifacts")
        return opening(path)

    def checked_source(path, *args, **kwargs):
        assert not Path(path).is_relative_to(REAL_ROOT / "artifacts")
        return source_open(path, *args, **kwargs)

    monkeypatch.setattr(tool.audit, "_open_absolute_directory", checked)
    monkeypatch.setattr(tool.builder.source, "_open_directory_path", checked_source)
    for module, name in ((tool.builder, "_build"), (tool.builder, "_load"),
                         (tool.v4.policy.legacy, "_native"),
                         (tool.v1, "_load_sources")):
        monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(tool.builder, "_provenance_presence", lambda *_a, **_k: False)


def documents():
    builder = tool.builder
    manifest = dict.fromkeys(builder._PUBLICATION_MANIFEST_KEYS, None)
    manifest.update(schema=builder.SCHEMA, artifact_id=tool.OUTPUT.name,
        diagnostic_purpose="current_public_QC_roundtrip_with_qualified_vendor_vintage_continuity",
        source_mode="production_source_bytes_offline", requested_name_count=7,
        private_host_qualifications_only=True, original_full_identity_binder_unchanged=True,
        **dict.fromkeys(builder.FALSE_FLAGS, False))
    lineage = {"public_reference_sha256": tool.v1.MANIFESTS[tool.v1.PUBLIC],
               "price_manifest_sha256": tool.v1.MANIFESTS[tool.v1.PRICES],
               "sharadar_identity_manifest_sha256": tool.v1.MANIFESTS[tool.v1.CURRENT],
               "vintage_manifest_sha256": tool.v1.MANIFESTS[tool.v1.VINTAGE]}
    manifest.update(lineage)
    rows, selected = [], []
    for number, ticker in enumerate(builder.public.TICKERS):
        role = "stock" if ticker == "QCOM" else "fund"
        row = dict.fromkeys(builder._PUBLICATION_ROW_KEYS, None)
        row.update(ticker=ticker, role=role, diagnostic_status="continuity_qualified_not_admitted",
                   **dict.fromkeys(builder.FALSE_FLAGS, False))
        for flag in ("public_figi_equals_actual_vintage_figi", "vendor_permanent_id_continuity_equal",
                     "category_role_currency_continuity_equal", "current_price_range_covers_bound_close"):
            row[flag] = True
        rows.append(row)
        selected.append(dict(ticker=ticker, role=role, composite_figi=f"BBG{number:09d}"))
    manifest["rows"] = rows
    manifest_raw = builder.canonical_json_bytes(manifest)
    input_raw = builder.canonical_json_bytes(dict(schema=builder.INPUT_SCHEMA, rows=selected,
        continuity_manifest_sha256=tool._sha(manifest_raw), **lineage))
    return manifest_raw, input_raw


@pytest.fixture
def scope(tmp_path, monkeypatch):
    if sys.platform != "darwin" or not hasattr(os.stat_result, "st_flags"):
        pytest.skip("fixed Darwin/APFS synthetic output integration")
    root = tmp_path / "lane"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    parent = root
    for name in REAL_OUTPUT.parent.relative_to(REAL_ROOT).parts:
        parent = parent / name
        parent.mkdir(mode=0o700)
    output = parent / REAL_OUTPUT.name
    for module in (tool, tool.v4, tool.v1, tool.verifier):
        monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(tool, "OUTPUT", output)
    monkeypatch.setattr(tool, "__file__", str(root / "scripts" / "publisher.py"))
    monkeypatch.setattr(tool.v4.policy, "PROSPECTIVE_DEVICE", root.stat().st_dev)
    monkeypatch.setattr(tool.builder, "VINTAGE_PINS", dataclasses.replace(
        tool.builder.VINTAGE_PINS, artifact_path=root / tool.v1.VINTAGE))
    monkeypatch.setattr(tool, "CODE_PINS", MappingProxyType({}))
    monkeypatch.setattr(tool.v4, "profile_sha256", lambda: tool.V4_PROFILE_SHA256)
    monkeypatch.setattr(tool.v1, "_require_supported_platform", lambda: None)
    monkeypatch.chdir(root)
    events = []
    expected = {f"synthetic/{n}": {"metadata": {"synthetic": n}} for n in range(15)}
    inventory = {str((root / key).relative_to(root.parent)): {"metadata": value["metadata"]}
                 for key, value in expected.items()}
    raw = documents()

    def empty(event):
        assert output.is_dir() and list(output.iterdir()) == []
        events.append(event)

    def reports(_root):
        empty("history")
        return {}, {}

    def preflight():
        empty("preflight")
        return {"inventory": deepcopy(inventory)}

    def create(**kwargs):
        empty("documents")
        assert kwargs == dict(public_artifact_path=root / tool.v1.PUBLIC,
            expected_public_manifest_sha256=tool.v1.MANIFESTS[tool.v1.PUBLIC],
            current_artifact_path=root / tool.v1.CURRENT,
            expected_current_manifest_sha256=tool.v1.MANIFESTS[tool.v1.CURRENT],
            price_artifact_path=root / tool.v1.PRICES,
            expected_price_manifest_sha256=tool.v1.MANIFESTS[tool.v1.PRICES],
            vintage_pins=tool.builder.VINTAGE_PINS, output_name=output.name, synthetic=False)
        return raw

    def guard(_root, _expected, consume, _snapshot):
        empty("guard_enter")
        result = consume()
        empty("guard_final_checks")
        return dict(loader_results=result, file_count=15, directory_count=12)

    original_publish = tool._publish_leaf

    def writer(fd, name, payload, **kwargs):
        assert events[-1] in {"guard_final_checks", "input.json", "manifest.sha256"}
        events.append(name)
        return original_publish(fd, name, payload, **kwargs)

    monkeypatch.setattr(tool.v1, "_read_pinned_reports", reports)
    monkeypatch.setattr(tool.v1, "_scope", lambda *_a: expected)
    monkeypatch.setattr(tool.v4, "_project_sources", lambda value: (value, {}))
    monkeypatch.setattr(tool.v4, "preflight_scope", preflight)
    monkeypatch.setattr(tool.verifier, "_validate_preflight", lambda _value: None)
    monkeypatch.setattr(tool.v4, "_guarded_consume", guard)
    monkeypatch.setattr(tool.builder, "_documents", create)
    monkeypatch.setattr(tool, "_publish_leaf", writer)
    return SimpleNamespace(root=root, output=output, events=events, raw=raw,
                           expected=expected, inventory=inventory, guard=guard)


def publish(scope):
    return tool.publish(tool.profile_sha256())


def authenticate(scope, exit_code=0):
    return tool.authenticate(tool.profile_sha256(), tool._sha(scope.raw[0]), tool._sha(scope.raw[1]), exit_code)


def test_success_orders_guard_return_before_all_payloads_and_auth_is_output_only(scope, monkeypatch):
    result = publish(scope)
    assert scope.events == ["history", "preflight", "guard_enter", "documents", "documents",
                            "guard_final_checks", "input.json", "manifest.sha256", "manifest.json"]
    assert set(path.name for path in scope.output.iterdir()) == set(tool.FILES)
    assert all(result[flag] is False for flag in tool.FALSE_FLAGS)
    assert "rows" not in result
    for module, name in ((tool.v1, "_read_pinned_reports"), (tool.v4, "preflight_scope"),
                         (tool.v4, "_guarded_consume"), (tool.builder, "_documents")):
        monkeypatch.setattr(module, name, forbidden)
    assert authenticate(scope) == result


def test_outer_refusal_after_both_documents_never_publishes(scope, monkeypatch):
    def refuse(*args):
        scope.guard(*args)
        raise tool.audit.Refusal("synthetic_outer_refusal")
    monkeypatch.setattr(tool.v4, "_guarded_consume", refuse)
    with pytest.raises(tool.audit.Refusal, match="synthetic_outer_refusal"):
        publish(scope)
    assert scope.events.count("documents") == 2
    assert list(scope.output.iterdir()) == []


@pytest.mark.parametrize("boundary", ["history", "preflight", "projection", "documents"])
def test_source_failures_leave_empty_spent_claim(scope, monkeypatch, boundary):
    def refuse(*_args, **_kwargs):
        raise tool.audit.Refusal("synthetic_source_refusal")
    module, name = {"history": (tool.v1, "_read_pinned_reports"),
                    "preflight": (tool.v4, "preflight_scope"),
                    "projection": (tool.v4, "_project_sources"),
                    "documents": (tool.builder, "_documents")}[boundary]
    monkeypatch.setattr(module, name, refuse)
    with pytest.raises(tool.audit.Refusal, match="synthetic_source_refusal"):
        publish(scope)
    assert list(scope.output.iterdir()) == []
    with pytest.raises(FileExistsError):
        publish(scope)


def test_second_source_buffer_change_refuses_before_publication(scope, monkeypatch):
    calls = iter((scope.raw, (scope.raw[0], scope.raw[1] + b" ")))
    monkeypatch.setattr(tool.builder, "_documents", lambda **_kwargs: next(calls))
    with pytest.raises(tool.audit.Refusal, match="publication_source_documents_changed"):
        publish(scope)
    assert list(scope.output.iterdir()) == []


@pytest.mark.parametrize("index", range(15))
def test_every_projected_metadata_row_is_compared(scope, monkeypatch, index):
    scope.expected[f"synthetic/{index}"]["metadata"] = {"synthetic": index + 1}
    with pytest.raises(tool.audit.Refusal, match="publication_preflight_metadata"):
        publish(scope)
    assert "guard_enter" not in scope.events and list(scope.output.iterdir()) == []


@pytest.mark.parametrize("exit_code", [None, 1, -1, True, "0"])
def test_nonzero_unknown_or_inexact_publisher_exit_rejects_without_observations(scope, monkeypatch, exit_code):
    monkeypatch.setattr(tool, "_contract", forbidden)
    monkeypatch.setattr(tool, "_authenticate", forbidden)
    with pytest.raises(tool.audit.Refusal, match="successful_publisher_exit_required"):
        authenticate(scope, exit_code)
    assert not scope.output.exists()


def test_late_auth_failure_retains_complete_package_but_failed_exit_cannot_accept(scope, monkeypatch):
    original = tool._authenticate
    monkeypatch.setattr(tool, "_authenticate", lambda *_a, **_k: (_ for _ in ()).throw(
        tool.audit.Refusal("synthetic_late_failure")))
    with pytest.raises(tool.audit.Refusal, match="synthetic_late_failure"):
        publish(scope)
    assert set(path.name for path in scope.output.iterdir()) == set(tool.FILES)
    monkeypatch.setattr(tool, "_authenticate", original)
    with pytest.raises(tool.audit.Refusal, match="successful_publisher_exit_required"):
        authenticate(scope, 1)


@pytest.mark.parametrize("name", ["input.json", "manifest.sha256", "manifest.json"])
def test_write_failure_retains_pending_evidence_and_never_retries(scope, monkeypatch, name):
    original = tool._publish_leaf
    def fail(fd, current, raw):
        if current == name:
            claim = tool.audit._claim_report(fd, current)
            os.close(claim[0])
            raise tool.audit.Refusal("synthetic_pending_failure")
        return original(fd, current, raw)
    monkeypatch.setattr(tool, "_publish_leaf", fail)
    with pytest.raises(tool.audit.Refusal, match="synthetic_pending_failure"):
        publish(scope)
    assert (scope.output / (name + ".pending")).exists()
    with pytest.raises(FileExistsError):
        publish(scope)


@pytest.mark.parametrize("kind", ["directory", "symlink", "file"])
def test_claim_never_reuses_existing_leaf(scope, kind):
    if kind == "directory":
        scope.output.mkdir(mode=0o700)
    elif kind == "symlink":
        scope.output.symlink_to(scope.output.parent)
    else:
        scope.output.write_bytes(b"retained")
    with pytest.raises(FileExistsError):
        publish(scope)
    assert scope.events == []


@pytest.mark.parametrize("tamper", ["extra", "pending", "input", "marker", "mode", "hardlink", "symlink"])
def test_output_envelope_rejects_tampering(scope, tamper):
    publish(scope)
    path = scope.output / "input.json"
    if tamper in {"extra", "pending"}:
        (scope.output / ("manifest.json.pending" if tamper == "pending" else "extra")).write_bytes(b"x")
    elif tamper == "input":
        path.write_bytes(path.read_bytes() + b" ")
    elif tamper == "marker":
        (scope.output / "manifest.sha256").write_bytes(b"0" * 64 + b"\n")
    elif tamper == "mode":
        path.chmod(0o644)
    elif tamper == "hardlink":
        os.link(path, scope.output.parent / "synthetic-link")
    else:
        path.unlink()
        path.symlink_to(scope.output / "manifest.json")
    with pytest.raises((tool.audit.Refusal, tool.builder.IdentityContinuityError)):
        authenticate(scope)


def test_same_byte_replacement_during_inner_validator_fails_outer_held_binding(scope, monkeypatch):
    publish(scope)
    original = tool.builder.authenticated_identity_continuity_input
    @contextmanager
    def replace(*args, **kwargs):
        with original(*args, **kwargs) as raw:
            yield raw
        path = scope.output / "input.json"
        replacement = scope.output / "swap"
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o600)
        replacement.replace(path)
    monkeypatch.setattr(tool.builder, "authenticated_identity_continuity_input", replace)
    with pytest.raises(tool.audit.Refusal, match="publication_output_changed"):
        authenticate(scope)


def test_final_directory_drift_refused_even_if_files_match(scope, monkeypatch):
    publish(scope)
    original = tool.builder.authenticated_identity_continuity_input
    @contextmanager
    def change(*args, **kwargs):
        with original(*args, **kwargs) as raw:
            yield raw
        scope.output.chmod(0o755)
    monkeypatch.setattr(tool.builder, "authenticated_identity_continuity_input", change)
    with pytest.raises(tool.audit.Refusal, match="publication_directory_security"):
        authenticate(scope)


def test_claim_metadata_drift_during_guard_prevents_payloads(scope, monkeypatch):
    def drift(*args):
        result = scope.guard(*args)
        scope.output.chmod(0o755)
        return result
    monkeypatch.setattr(tool.v4, "_guarded_consume", drift)
    with pytest.raises(tool.audit.Refusal, match="publication_directory_security"):
        publish(scope)
    assert list(scope.output.iterdir()) == []


def test_contract_change_before_payloads_refuses(scope, monkeypatch):
    calls = 0
    original = tool._contract
    def changed(pin):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise tool.audit.Refusal("publication_profile_changed")
        original(pin)
    monkeypatch.setattr(tool, "_contract", changed)
    with pytest.raises(tool.audit.Refusal, match="publication_profile_changed"):
        publish(scope)
    assert list(scope.output.iterdir()) == []


def test_periodic_timer_refusal_is_before_claim_and_timer_preserved(scope, monkeypatch):
    monkeypatch.setattr(signal, "getitimer", lambda *_a: (20, 20))
    monkeypatch.setattr(signal, "setitimer", forbidden)
    with pytest.raises(tool.audit.Refusal, match="periodic_alarm_not_supported"):
        publish(scope)
    assert not scope.output.exists()


def test_budget_exit_failure_retains_complete_package_without_success(scope, monkeypatch):
    @contextmanager
    def late(_seconds):
        yield
        raise tool.audit.Refusal("synthetic_budget_return_failure")
    monkeypatch.setattr(tool.v4, "_budget", late)
    with pytest.raises(tool.audit.Refusal, match="synthetic_budget_return_failure"):
        publish(scope)
    assert set(path.name for path in scope.output.iterdir()) == set(tool.FILES)


def test_cli_mixed_mode_refuses_before_source_or_claim(scope):
    with pytest.raises(tool.audit.Refusal, match="publication_cli_mode"):
        tool.main(["--publish", "--expected-profile-sha256", tool.profile_sha256(), "--publisher-exit", "0"])
    assert not scope.output.exists()


def test_false_profile_flags_and_fixed_new_leaf():
    value = tool.profile()
    assert value["output"] == str(REAL_OUTPUT)
    assert value["independent_review_required"] is True
    assert value["separate_run_freeze_required"] is True
    assert all(value[flag] is False for flag in tool.FALSE_FLAGS)
    assert "late_failure" in value
    assert value["code_pins"]["scripts/arv2_relocation_security.py"] == (
        "3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30")


def test_original_parent_metadata_drift_after_auth_is_not_rebaselined(scope, monkeypatch):
    original = tool._authenticate
    def change(*args, **kwargs):
        original(*args, **kwargs)
        parent = scope.output.parent
        now = parent.stat()
        os.utime(parent, ns=(now.st_atime_ns, now.st_mtime_ns + 1000000))
    monkeypatch.setattr(tool, "_authenticate", change)
    with pytest.raises(tool.audit.Refusal, match="publication_original_parent_changed"):
        publish(scope)
    assert set(path.name for path in scope.output.iterdir()) == set(tool.FILES)


def test_changed_selected_dependency_pin_refuses_before_claim(scope, monkeypatch):
    code = scope.root / "scripts"
    code.mkdir(mode=0o700)
    path = code / "arv2_relocation_security.py"
    path.write_bytes(b"synthetic original dependency")
    monkeypatch.setattr(tool, "CODE_PINS", MappingProxyType({
        "scripts/arv2_relocation_security.py": tool._sha(path.read_bytes())}))
    pin = tool.profile_sha256()
    tool._contract(pin)
    path.write_bytes(b"synthetic changed dependency")
    with pytest.raises(tool.audit.Refusal, match="publication_code_pin"):
        tool.publish(pin)
    assert not scope.output.exists()


@pytest.mark.parametrize("tamper", ["oversize", "replacement", "grow"])
def test_publication_readback_is_bounded_and_rejects_drift(scope, monkeypatch, tamper):
    original_read = tool._read_output_leaf
    original_os_read = os.read
    reads = []
    def observe_read(fd, size):
        reads.append(size)
        if tamper == "grow":
            return b"x" * size
        return original_os_read(fd, size)
    def tampered(output, name, maximum, stack, expected_metadata=None):
        assert maximum == tool.FILES[name]
        if name == "input.json":
            assert expected_metadata is not None
            path = scope.output / name
            if tamper == "oversize":
                path.write_bytes(b"x" * (maximum + 1))
            elif tamper == "replacement":
                replacement = scope.output / "replacement"
                replacement.write_bytes(path.read_bytes())
                replacement.chmod(0o600)
                replacement.replace(path)
            monkeypatch.setattr(os, "read", observe_read)
        return original_read(output, name, maximum, stack, expected_metadata)
    monkeypatch.setattr(tool, "_read_output_leaf", tampered)
    with pytest.raises(tool.audit.Refusal, match="publication_(output_file_security|readback_replaced|output_grew)"):
        publish(scope)
    assert (scope.output / "input.json").exists()
    assert not (scope.output / "manifest.json").exists()
    assert all(size <= tool.FILES["input.json"] + 1 for size in reads)
    if tamper in {"oversize", "replacement"}:
        assert reads == []


def test_oversize_writer_buffer_refuses_before_claim(scope, monkeypatch):
    monkeypatch.setattr(tool.audit, "_claim_report", forbidden)
    scope.events.append("guard_final_checks")
    with pytest.raises(tool.audit.Refusal, match="publication_payload_bound"):
        tool._publish_leaf(-1, "input.json", b"x" * (tool.FILES["input.json"] + 1))


def test_link_time_mtime_drift_refuses_without_clearing_evidence(scope, monkeypatch):
    original = os.link
    def changed(src, dst, *args, **kwargs):
        result = original(src, dst, *args, **kwargs)
        path = scope.output / dst
        now = path.stat()
        os.utime(path, ns=(now.st_atime_ns, now.st_mtime_ns + 1000000))
        return result
    monkeypatch.setattr(os, "link", changed)
    with pytest.raises(tool.audit.Refusal, match="publication_link_changed"):
        publish(scope)
    assert (scope.output / "input.json").exists()
    assert not (scope.output / "manifest.json").exists()


@pytest.mark.parametrize("kind", ["lineage", "false_flag", "source_mode", "schema"])
def test_self_consistent_external_hashes_do_not_override_frozen_semantics(scope, kind):
    publish(scope)
    manifest = tool.builder.require_canonical_json_bytes(scope.raw[0], "test")
    value = tool.builder.require_canonical_json_bytes(scope.raw[1], "test")
    if kind == "lineage":
        manifest["public_reference_sha256"] = value["public_reference_sha256"] = "a" * 64
    elif kind == "false_flag":
        manifest[tool.builder.FALSE_FLAGS[0]] = True
    elif kind == "source_mode":
        manifest["source_mode"] = "offline_test_double"
    else:
        manifest["schema"] = "changed"
    manifest_raw = tool.builder.canonical_json_bytes(manifest)
    value["continuity_manifest_sha256"] = tool._sha(manifest_raw)
    scope.raw = manifest_raw, tool.builder.canonical_json_bytes(value)
    for name, raw in (("manifest.json", scope.raw[0]), ("input.json", scope.raw[1]),
                      ("manifest.sha256", (tool._sha(manifest_raw) + "\n").encode())):
        (scope.output / name).write_bytes(raw)
    with pytest.raises((tool.audit.Refusal, tool.builder.IdentityContinuityError)):
        authenticate(scope)


@pytest.mark.parametrize("tamper", ["replacement", "mtime"])
@pytest.mark.parametrize("later", ["manifest.sha256", "manifest.json"])
def test_original_input_allocation_remains_bound_while_later_files_publish(scope, monkeypatch, tamper, later):
    original = tool._publish_leaf
    def change(fd, name, raw):
        held = original(fd, name, raw)
        if name == later:
            path = scope.output / "input.json"
            if tamper == "replacement":
                replacement = scope.output / "same-byte-replacement"
                replacement.write_bytes(path.read_bytes())
                replacement.chmod(0o600)
                replacement.replace(path)
            else:
                now = path.stat()
                os.utime(path, ns=(now.st_atime_ns, now.st_mtime_ns + 1000000))
        return held
    monkeypatch.setattr(tool, "_publish_leaf", change)
    with pytest.raises(tool.audit.Refusal, match="publication_original_leaf_changed"):
        publish(scope)
    assert set(path.name for path in scope.output.iterdir()) == set(tool.FILES)


def test_original_input_allocation_rechecked_after_final_auth(scope, monkeypatch):
    original = tool._authenticate
    def change(*args, **kwargs):
        original(*args, **kwargs)
        path = scope.output / "input.json"
        now = path.stat()
        os.utime(path, ns=(now.st_atime_ns, now.st_mtime_ns + 1000000))
    monkeypatch.setattr(tool, "_authenticate", change)
    with pytest.raises(tool.audit.Refusal, match="publication_original_leaf_changed"):
        publish(scope)


def test_authentication_enforces_supplied_original_allocation_metadata(scope):
    publish(scope)
    expected = {name: tool.audit._metadata((scope.output / name).stat()) for name in tool.FILES}
    expected["input.json"]["ino"] += 1
    with pytest.raises(tool.audit.Refusal, match="publication_readback_replaced"):
        tool._authenticate(tool._sha(scope.raw[0]), tool._sha(scope.raw[1]), expected_metadata=expected)
