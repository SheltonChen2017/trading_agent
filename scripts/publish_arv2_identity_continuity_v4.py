"""Unreviewed, uninvoked fixed-leaf publication candidate; not run authority.

Source guards must RETURN before any payload publication. A late failure can
leave all three files present: retain them, but a nonzero/unknown publisher
exit makes that package inadmissible. Never retry, clean up, or call the old
builder's _build/_load (the latter reconstructs sources after publication).
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import dataclasses
import hashlib
import os
from pathlib import Path
import stat
import sys
from types import MappingProxyType

from scripts import assess_arv2_relocated_sources_v4 as v4
from scripts import build_arv2_identity_continuity as builder
from scripts import verify_arv2_v4_assessment as verifier

audit, v1 = v4.audit, v4.v1
_require = v1._require
ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
OUTPUT = ROOT / "artifacts/analyst_revisions_v2/identity_continuity/R284A1-20261008-C"
SCHEMA = "arv2-guarded-identity-publication-v4"
V4_PROFILE_SHA256 = "63e286099b822faa5c33fb7ed46ce26bce80deb4152af438f104e260e1967319"
SECONDS = 60
CODE_PINS = MappingProxyType({
    "scripts/arv2_relocation_security.py": "3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30",
    "scripts/arv2_relocation_security_v4.py": "3d20990b1df38f6aac04990c01c4fa752af6bc8b14b0bf0b8372b0daa0047fa7",
    "scripts/assess_arv2_relocated_sources_v4.py": "8b3f92ec5db2d1e509d9b3314b6377efdb533b2bf9bec0790f4d2b10a4e9b2d3",
    "scripts/assess_arv2_relocated_sources.py": "85d853a103f47959506cad84e087819f9cc41c3fb57de53c9e121609596c9e5e",
    "scripts/audit_arv2_relocation.py": "6e411fca07ca4a2904a1de9337876fcac560cf38cbaf9f3501b00a57c8d117a3",
    "scripts/build_arv2_identity_continuity.py": "f05e3b0828ef460d65cb0d728aec2bffdd69c617a5427e884d124f642a4b2484",
    "scripts/capture_arv2_sharadar.py": "17e516b4cc721c7f97c4690f54dfcc9d2d11d8cebd413100f2e2ffa68e663ca2",
    "scripts/capture_arv2_openfigi_identity.py": "1dfa3d4a617f43fffc08e2ee68f130534defb1cc5f872edb747e2bbb2e2dccc7",
    "scripts/capture_arv2_sharadar_identities.py": "b307d102588c33002868e9d29d87a028046336442f314c7d6ef4041c65dba9e4",
    "scripts/capture_arv2_sharadar_prices.py": "e33ba763d1c4d8249ebbf8d8e77a5d91069f9f9bf533fb3eee34114157badf9a",
    "scripts/verify_arv2_v4_assessment.py": "79447dc23883e5bc264d8ddb91b6198d5b82a36f75b9578bf0af51ea7c2eb19b",
})
FALSE_FLAGS = frozenset(builder.FALSE_FLAGS) | {
    "historical_audit_accepted", "historical_security_equivalence",
    "continuous_stability_proven", "formal_admission", "provider_or_qc_contact",
    "output_acl_xattr_envelope_proven", "r284_preparation_authorized",
    "independent_review_completed", "run_authority_established",
}
FILES = MappingProxyType({"input.json": builder.MAX_INPUT_BYTES,
                         "manifest.json": builder.MAX_MANIFEST_BYTES, "manifest.sha256": 65})


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def profile():
    vintage = dataclasses.asdict(builder.VINTAGE_PINS)
    vintage["artifact_path"] = str(vintage["artifact_path"])
    return {"schema": SCHEMA, "root": str(ROOT), "output": str(OUTPUT),
        "code_pins": dict(CODE_PINS), "source_contract": v4.profile(),
        "source_profile_sha256": V4_PROFILE_SHA256, "vintage_pins": vintage,
        "publication_schema": builder.SCHEMA, "input_schema": builder.INPUT_SCHEMA,
        "files": dict(FILES), "seconds": SECONDS,
        "source_protocol": "exclusive-fsynced-empty-claim-history-projection-one-preflight-two-equal-documents-outer-guard-return-before-payloads",
        "publication_protocol": "private-exclusive-pending-link-unlink-no-retry-no-cleanup-output-only-authentication",
        "acceptance": "actual-publisher-exit-zero-and-external-input-manifest-pins-and-strict-three-file-authentication",
        "late_failure": "complete-package-may-remain-but-nonzero-or-unknown-exit-is-inadmissible",
        "budget_kind": "cooperative-signal-and-return-check-not-hard-native-interruption",
        "independent_review_required": True, "separate_run_freeze_required": True,
        **dict.fromkeys(FALSE_FLAGS, False)}


def profile_sha256():
    return _sha(audit._json_bytes(profile()))


def _contract(expected_profile):
    _require(profile_sha256() == expected_profile and v4.profile_sha256() == V4_PROFILE_SHA256,
             "publication_profile_changed")
    # Selected directly consumed code pins, not a whole interpreter/import
    # closure. Bounded code reads are not original evidence/native observations.
    for relative, digest in CODE_PINS.items():
        path = ROOT / relative
        fd = audit._open_absolute_directory(path.parent)
        try:
            row, _ = audit._read_regular(fd, path.name, relative, b"", maximum=512 * 1024)
            _require(row["sha256"] == digest, "publication_code_pin")
        finally:
            os.close(fd)


def _directory(fd, path):
    meta = audit._metadata(os.fstat(fd))
    _require(all(type(item) is int for item in meta.values())
             and meta["dev"] == v4.policy.PROSPECTIVE_DEVICE
             and v4._directory_secure(meta, path), "publication_directory_security")
    return meta


def _named_directory(path):
    fd = audit._open_absolute_directory(path)
    try:
        return _directory(fd, path)
    finally:
        os.close(fd)


def _open_parent():
    # Resolve all absolute components no-follow, and check every lane component
    # against the fixed device/owner/mode contract, without creating parents.
    fd = audit._open_absolute_directory(ROOT)
    try:
        path = ROOT
        _directory(fd, path)
        for name in OUTPUT.parent.relative_to(ROOT).parts:
            child = os.open(name, audit._directory_flags(), dir_fd=fd)
            os.close(fd)
            fd, path = child, path / name
            _directory(fd, path)
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def _claim():
    parent, output = _open_parent(), None
    try:
        os.mkdir(OUTPUT.name, 0o700, dir_fd=parent)  # Existing paths are spent.
        output = os.open(OUTPUT.name, audit._directory_flags(), dir_fd=parent)
        allocated = _directory(output, OUTPUT)
        os.fsync(output)
        os.fsync(parent)
        parent_meta = _directory(parent, OUTPUT.parent)
        _require(allocated == _directory(output, OUTPUT) == _named_directory(OUTPUT),
                 "publication_claim_changed")
        _require(os.listdir(output) == [], "publication_claim_not_empty")
        yield parent, output, parent_meta, allocated
    finally:
        if output is not None:
            os.close(output)
        os.close(parent)


def _documents():
    pins = dict(public_artifact_path=ROOT / v1.PUBLIC,
        expected_public_manifest_sha256=v1.MANIFESTS[v1.PUBLIC],
        current_artifact_path=ROOT / v1.CURRENT,
        expected_current_manifest_sha256=v1.MANIFESTS[v1.CURRENT],
        price_artifact_path=ROOT / v1.PRICES,
        expected_price_manifest_sha256=v1.MANIFESTS[v1.PRICES],
        vintage_pins=builder.VINTAGE_PINS, output_name=OUTPUT.name, synthetic=False)
    first = builder._documents(**pins)
    second = builder._documents(**pins)
    _require(type(first) is tuple and len(first) == 2
             and all(type(raw) is bytes for raw in first)
             and type(second) is tuple and all(type(raw) is bytes for raw in second)
             and first == second, "publication_source_documents_changed")
    _require(0 < len(first[0]) <= FILES["manifest.json"]
             and 0 < len(first[1]) <= FILES["input.json"], "publication_document_bounds")
    return first


def _source_documents():
    before, after = v1._read_pinned_reports(ROOT)
    expected, _receipt = v4._project_sources(v1._scope(before, after))
    observed = v4.preflight_scope()
    verifier._validate_preflight(observed)
    _require(len(expected) == 15, "publication_source_count")
    for relative, row in expected.items():
        key = str((ROOT / relative).relative_to(ROOT.parent))
        _require(audit._json_bytes(observed["inventory"][key]["metadata"])
                 == audit._json_bytes(row["metadata"]), "publication_preflight_metadata")
    guarded = v4._guarded_consume(ROOT, expected, _documents, v4.policy.snapshot)
    _require(guarded["file_count"] == 15 and guarded["directory_count"] == 12,
             "publication_guard_scope")
    return guarded["loader_results"]  # Outer guard has now RETURNED.


def _summary(expected_profile, manifest_sha, input_sha):
    return {"schema": SCHEMA, "profile_sha256": expected_profile,
            "manifest_sha256": manifest_sha, "input_sha256": input_sha,
            "bound_source_file_count": 15, "bound_source_directory_count": 12,
            "output_file_count": 3, "requested_name_count": 7,
            **dict.fromkeys(FALSE_FLAGS, False)}


def _read_output_leaf(output, name, maximum, stack, expected_metadata=None):
    named = audit._metadata(os.stat(name, dir_fd=output, follow_symlinks=False))
    _require(named["dev"] == v4.policy.PROSPECTIVE_DEVICE
             and v1._private_file(named) and 0 < named["size"] <= maximum,
             "publication_output_file_security")
    if expected_metadata is not None:
        _require(named == expected_metadata, "publication_readback_replaced")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=output)
    stack.callback(os.close, fd)
    _require(named == audit._metadata(os.fstat(fd)), "publication_output_postopen")
    chunks, count = [], 0
    while True:
        part = os.read(fd, min(65536, maximum + 1 - count))
        if not part:
            break
        count += len(part)
        _require(count <= maximum, "publication_output_grew")
        chunks.append(part)
    _require(count == named["size"] and named == audit._metadata(os.fstat(fd))
             == audit._metadata(os.stat(name, dir_fd=output, follow_symlinks=False)),
             "publication_output_initial_read")
    return b"".join(chunks), (fd, named)


def _publish_leaf(output, name, raw):
    """Bounded local writer; failure retains every pending/published byte."""
    _require(name in FILES and type(raw) is bytes and 0 < len(raw) <= FILES[name],
             "publication_payload_bound")
    pending = name + ".pending"
    fd, info = audit._claim_report(output, name)
    try:
        allocated = audit._metadata(info)
        _require(allocated["dev"] == v4.policy.PROSPECTIVE_DEVICE and v1._private_file(allocated)
                 and allocated["size"] == 0 and allocated == audit._metadata(os.fstat(fd))
                 == audit._metadata(os.stat(pending, dir_fd=output, follow_symlinks=False)),
                 "publication_pending_claim")
        remaining = memoryview(raw)
        while remaining:
            written = os.write(fd, remaining)
            _require(written > 0, "publication_write_stalled")
            remaining = remaining[written:]
        os.fsync(fd)
        held = audit._metadata(os.fstat(fd))
        _require(held == audit._metadata(os.stat(pending, dir_fd=output, follow_symlinks=False))
                 and all(held[key] == allocated[key] for key in audit.DIRECTORY_FIELDS)
                 and v1._private_file(held) and held["size"] == len(raw),
                 "publication_pending_changed")
        os.link(pending, name, src_dir_fd=output, dst_dir_fd=output, follow_symlinks=False)
        os.unlink(pending, dir_fd=output)
        os.fsync(output)
        published = audit._metadata(os.fstat(fd))
        _require(v1._private_file(published)
                 and all(published[key] == held[key] for key in audit.DIRECTORY_FIELDS)
                 and published["size"] == len(raw) and published["mtime_ns"] == held["mtime_ns"],
                 "publication_link_changed")
        with ExitStack() as stack:
            captured, _ = _read_output_leaf(output, name, FILES[name], stack, published)
            _require(captured == raw, "publication_readback_bytes")
        _require(published == audit._metadata(os.fstat(fd))
                 == audit._metadata(os.stat(name, dir_fd=output, follow_symlinks=False)),
                 "publication_original_leaf_changed_during_readback")
        # Caller owns this original-allocation descriptor through all remaining
        # writes and final authentication, preventing inode-reuse ambiguity.
        return os.dup(fd), published
    finally:
        os.close(fd)


def _published_files_unchanged(output, held):
    for name, (fd, meta) in held.items():
        _require(meta == audit._metadata(os.fstat(fd))
                 == audit._metadata(os.stat(name, dir_fd=output, follow_symlinks=False)),
                 "publication_original_leaf_changed")


def _authenticate(manifest_sha, input_sha, *, expected_bytes=None, expected_metadata=None):
    """Output-only held/named ten-field envelope; does not establish run exit."""
    builder.require_sha256(manifest_sha, "externally emitted manifest pin")
    builder.require_sha256(input_sha, "externally emitted input pin")
    with ExitStack() as stack:
        parent = _open_parent()
        stack.callback(os.close, parent)
        parent_meta = _directory(parent, OUTPUT.parent)
        output = os.open(OUTPUT.name, audit._directory_flags(), dir_fd=parent)
        stack.callback(os.close, output)
        allocated = _directory(output, OUTPUT)
        _require(allocated == _named_directory(OUTPUT), "publication_output_named_directory")
        _require(set(os.listdir(output)) == set(FILES), "publication_output_inventory")
        captured, held = {}, {}
        for name, maximum in FILES.items():
            captured[name], held[name] = _read_output_leaf(output, name, maximum, stack,
                None if expected_metadata is None else expected_metadata[name])
        _require(_sha(captured["manifest.json"]) == manifest_sha
                 and _sha(captured["input.json"]) == input_sha
                 and captured["manifest.sha256"] == (manifest_sha + "\n").encode("ascii"),
                 "publication_output_pins")
        if expected_bytes is not None:
            _require((captured["manifest.json"], captured["input.json"]) == expected_bytes,
                     "publication_output_buffers")
        manifest = builder.require_canonical_json_bytes(captured["manifest.json"], "continuity manifest")
        lineage = {"public_reference_sha256": v1.MANIFESTS[v1.PUBLIC],
                   "price_manifest_sha256": v1.MANIFESTS[v1.PRICES],
                   "sharadar_identity_manifest_sha256": v1.MANIFESTS[v1.CURRENT],
                   "vintage_manifest_sha256": v1.MANIFESTS[v1.VINTAGE]}
        _require(all(manifest.get(key) == value for key, value in lineage.items()),
                 "publication_output_lineage")
        with builder.authenticated_identity_continuity_input(OUTPUT / "input.json", input_sha,
                manifest_sha, expected_source_mode="production_source_bytes_offline") as raw:
            _require(raw == captured["input.json"], "publication_output_input_changed")
        for name, (fd, meta) in held.items():
            _require(meta == audit._metadata(os.fstat(fd))
                     == audit._metadata(os.stat(name, dir_fd=output, follow_symlinks=False)),
                     "publication_output_changed")
            _require(v1._digest_held(fd, meta["size"]) == _sha(captured[name]),
                     "publication_output_final_digest")
            _require(meta == audit._metadata(os.fstat(fd))
                     == audit._metadata(os.stat(name, dir_fd=output, follow_symlinks=False)),
                     "publication_output_final_metadata")
        _require(set(os.listdir(output)) == set(FILES), "publication_output_final_inventory")
        _require(allocated == _directory(output, OUTPUT) == _named_directory(OUTPUT),
                 "publication_output_final_directory")
        _require(parent_meta == _directory(parent, OUTPUT.parent) == _named_directory(OUTPUT.parent),
                 "publication_output_final_parent")


def publish(expected_profile):
    with v4._budget(SECONDS):
        _contract(expected_profile)
        with _claim() as (parent, output, parent_meta, allocated), ExitStack() as original_files:
            manifest, input_raw = _source_documents()
            _contract(expected_profile)
            _require(parent_meta == _directory(parent, OUTPUT.parent) == _named_directory(OUTPUT.parent),
                     "publication_parent_changed_across_sources")
            _require(allocated == _directory(output, OUTPUT) == _named_directory(OUTPUT)
                     and os.listdir(output) == [], "publication_claim_changed_across_sources")
            manifest_sha, input_sha = _sha(manifest), _sha(input_raw)
            # Exact-inventory consumers reject all intermediate/pending states.
            held = {}
            for name, raw in (("input.json", input_raw),
                              ("manifest.sha256", (manifest_sha + "\n").encode("ascii")),
                              ("manifest.json", manifest)):
                fd, metadata = _publish_leaf(output, name, raw)
                original_files.callback(os.close, fd)
                held[name] = (fd, metadata)
            stable = {key: allocated[key] for key in audit.DIRECTORY_FIELDS}
            stable["nlink"] += 3  # Fixed Darwin/APFS leaf-count semantics.
            named = _named_directory(OUTPUT)
            _require(stable == audit._directory_metadata(os.fstat(output))
                     == {key: named[key] for key in audit.DIRECTORY_FIELDS},
                     "publication_directory_changed_during_writes")
            _published_files_unchanged(output, held)
            _authenticate(manifest_sha, input_sha, expected_bytes=(manifest, input_raw),
                          expected_metadata={name: meta for name, (_fd, meta) in held.items()})
            _contract(expected_profile)
            _published_files_unchanged(output, held)
            _require(parent_meta == _directory(parent, OUTPUT.parent) == _named_directory(OUTPUT.parent),
                     "publication_original_parent_changed")
            named = _named_directory(OUTPUT)
            _require(stable == audit._directory_metadata(os.fstat(output))
                     == {key: named[key] for key in audit.DIRECTORY_FIELDS},
                     "publication_original_output_changed")
        result = _summary(expected_profile, manifest_sha, input_sha)
    # A budget exit failure above can leave three files: no cleanup/acceptance.
    return result


def authenticate(expected_profile, manifest_sha, input_sha, publisher_exit):
    _require(type(publisher_exit) is int and publisher_exit == 0, "successful_publisher_exit_required")
    with v4._budget(SECONDS):
        _contract(expected_profile)
        _authenticate(manifest_sha, input_sha)
        _contract(expected_profile)
        result = _summary(expected_profile, manifest_sha, input_sha)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--authenticate", action="store_true")
    parser.add_argument("--expected-profile-sha256", required=True)
    parser.add_argument("--publisher-exit", type=int)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--input-sha256")
    args = parser.parse_args(argv)
    _require(Path.cwd() == ROOT and Path(__file__).resolve().parents[1] == ROOT
             and v4.ROOT == v1.ROOT == verifier.ROOT == ROOT
             and builder.VINTAGE_PINS.artifact_path == ROOT / v1.VINTAGE,
             "fixed_root_required")
    v1._require_supported_platform()
    if args.publish:
        _require(args.publisher_exit is None and args.manifest_sha256 is None
                 and args.input_sha256 is None, "publication_cli_mode")
        result = publish(args.expected_profile_sha256)
    else:
        result = authenticate(args.expected_profile_sha256, args.manifest_sha256,
                              args.input_sha256, args.publisher_exit)
    print(audit._json_bytes(result).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("fixed publication/authentication refused; any evidence retained and inadmissible", file=sys.stderr)
        raise SystemExit(1)
