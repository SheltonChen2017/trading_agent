"""One fixed, offline fresh-use assessment; never accepts the failed move audit."""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from scripts import audit_arv2_relocation as audit
from scripts import arv2_relocation_security as security

ROOT = audit.NEW_ROOT
OUTPUT = ROOT / "artifacts/analyst_revisions_v2/relocation_trial/R273-20261009-A"
BEFORE_SHA = "bd0931f9e9cac824ad394ecdc032b7c563e4b5eb92cf529e325edd3b712bbc82"
AFTER_SHA = "ca02a94e03eb67c8502e18103a8c471b72e44801b4c7ed62e28ca379b3e6236f"
PREFIX = "artifacts/analyst_revisions_v2/"
PUBLIC = PREFIX + "openfigi_identity_capture/arv2-openfigi-identities-20261008T051923284895Z"
PRICES = PREFIX + "sharadar_price_capture/arv2-sharadar-prices-20261007T164730430845Z"
CURRENT = PREFIX + "sharadar_identity_capture/arv2-sharadar-identities-20261008T052336423396Z"
VINTAGE = PREFIX + "sharadar_capture/arv2-sharadar-source-20260914T003329843989Z"
PACKAGES = {PUBLIC: ("manifest.json", "manifest.sha256", "batch01.json", "batch02.json"),
            PRICES: ("manifest.json", "manifest.sha256", "stocks.csv", "funds.csv"),
            CURRENT: ("manifest.json", "manifest.sha256", "stocks.csv", "funds.csv"),
            VINTAGE: ("manifest.json", "manifest.sha256", "01-tickers-years-full.zip")}
MANIFESTS = {PUBLIC: "75ce7cba40d063d227c0f273593c54622eb612144e9733c57335b31a00e7cb18",
             PRICES: "2f5d71683a43d1118420c52677fcbb6bdd539c7c621004b4632beed9b03f6702",
             CURRENT: "7dc79cfe045b857e7751dcfee72a73b56b93417a7712672be1395f18704b2bff",
             VINTAGE: "94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b"}
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_REPORT_BYTES = 128 * 1024


def _require(ok, code):
    if not ok:
        raise audit.Refusal(code)


def _read_pinned_reports(root):
    fd = audit._open_absolute_directory(root / audit.OUTPUT)
    try:
        reports = []
        for stage, pin in (("before", BEFORE_SHA), ("after", AFTER_SHA)):
            row, raw = audit._read_regular(fd, stage + ".json", stage, b"", collect=True,
                                           maximum=audit.MAX_BASELINE_BYTES)
            _require(row["sha256"] == pin, "historical_report_digest")
            report = json.loads(raw)
            _require(report["schema"] == audit.SCHEMA and report["stage"] == stage
                     and report["complete"] is True, "historical_report_contract")
            reports.append(report)
        _require(reports[1]["matches_before"] is False, "historical_refusal_must_remain")
        return reports
    finally:
        os.close(fd)


def _scope(before, after):
    result = {}
    for package, leaves in PACKAGES.items():
        for leaf in leaves:
            key = package + "/" + leaf
            old = before["census"]["entries"][key]
            new = after["census"]["entries"][key]
            _require(old["kind"] == new["kind"] == "file" and old["sha256"] == new["sha256"],
                     "historical_source_bytes")
            _require({k: v for k, v in old["metadata"].items() if k != "ctime_ns"}
                     == {k: v for k, v in new["metadata"].items() if k != "ctime_ns"}
                     and new["metadata"]["ctime_ns"] >= old["metadata"]["ctime_ns"],
                     "historical_source_metadata")
            _require(0 < new["metadata"]["size"] <= MAX_SOURCE_BYTES, "source_byte_limit")
            result[key] = new
    return result


def _private_file(meta):
    return (stat.S_ISREG(meta["mode"]) and stat.S_IMODE(meta["mode"]) == 0o600
            and meta["uid"] == os.getuid() and meta["nlink"] == 1
            and type(meta["flags"]) is int and not meta["flags"] & ~(stat.UF_TRACKED | stat.UF_HIDDEN))


def _digest_held(fd, expected_size):
    os.lseek(fd, 0, os.SEEK_SET)
    digest, count = hashlib.sha256(), 0
    while True:
        part = os.read(fd, min(1024 * 1024, expected_size + 1 - count))
        if not part:
            break
        count += len(part)
        _require(count <= expected_size, "source_grew")
        digest.update(part)
    _require(count == expected_size, "source_size_changed")
    return digest.hexdigest()


def _guarded_consume(root, expected, consume, snapshot):
    """Pin current objects across unmodified fresh loaders, never reuse old buffers."""
    with ExitStack() as stack:
        held_dirs = {}
        # The owner-held Code directory is the prospective discretionary-access
        # anchor. Resolve every component no-follow; do not assume old ACLs.
        directories = {root.parent, root}
        for relative in expected:
            path = (root / relative).parent
            while path != root:
                directories.add(path)
                path = path.parent
        for path in sorted(directories, key=lambda p: (len(p.parts), str(p))):
            fd = audit._open_absolute_directory(path)
            stack.callback(os.close, fd)
            meta = audit._metadata(os.fstat(fd))
            _require(stat.S_ISDIR(meta["mode"]) and meta["uid"] == os.getuid()
                     and stat.S_IMODE(meta["mode"]) == (0o755 if path == root else 0o700)
                     and type(meta["flags"]) is int
                     and not meta["flags"] & ~(stat.UF_TRACKED | stat.UF_HIDDEN), "current_directory_security")
            secured = snapshot(fd)
            _require(meta == audit._metadata(os.fstat(fd)), "directory_changed_during_security_read")
            held_dirs[path] = (fd, meta, secured)

        held_files = {}
        for relative, prior in sorted(expected.items()):
            path = root / relative
            parent = held_dirs[path.parent][0]
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            stack.callback(os.close, fd)
            meta = audit._metadata(os.fstat(fd))
            _require(meta == prior["metadata"] and _private_file(meta), "current_source_metadata_changed")
            _require(meta == audit._metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                     "current_source_named_identity")
            secured = snapshot(fd)
            _require(_digest_held(fd, meta["size"]) == prior["sha256"], "current_source_hash")
            _require(meta == audit._metadata(os.fstat(fd)), "source_changed_during_initial_read")
            held_files[relative] = (fd, meta, secured)

        result = consume()  # Uses original manifest pins and fresh parser-consumed bytes.

        for relative, (fd, meta, secured) in held_files.items():
            path = root / relative
            parent = held_dirs[path.parent][0]
            _require(meta == audit._metadata(os.fstat(fd))
                     == audit._metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                     "source_changed_across_consumer")
            _require(secured == snapshot(fd), "source_security_changed_across_consumer")
            _require(_digest_held(fd, meta["size"]) == expected[relative]["sha256"], "source_hash_after_consumer")
            _require(meta == audit._metadata(os.fstat(fd))
                     == audit._metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                     "source_changed_during_final_read")
        for path, (fd, meta, secured) in reversed(tuple(held_dirs.items())):
            check = audit._open_absolute_directory(path)
            try:
                _require(meta == audit._metadata(os.fstat(fd)) == audit._metadata(os.fstat(check)),
                         "directory_changed_across_consumer")
                _require(secured == snapshot(fd), "directory_security_changed_across_consumer")
                _require(meta == audit._metadata(os.fstat(fd)), "directory_changed_during_final_security")
            finally:
                os.close(check)
        return {"loader_results": result, "file_count": len(held_files), "directory_count": len(held_dirs),
                "directory_metadata": {str(path.relative_to(root.parent)): meta
                                       for path, (_fd, meta, _secure) in held_dirs.items()},
                "security_observations": {str(path.relative_to(root.parent)): secure
                                          for path, (_fd, _meta, secure) in held_dirs.items()},
                "file_security_observations": {path: secure for path, (_fd, _meta, secure) in held_files.items()}}


def _load_sources():
    from scripts import capture_arv2_openfigi_identity as public
    from scripts import capture_arv2_sharadar_prices as prices
    from scripts import capture_arv2_sharadar_identities as current
    from scripts import build_arv2_identity_continuity as continuity
    _require(public.source.REPOSITORY_ROOT == ROOT and continuity.VINTAGE_PINS.artifact_path == ROOT / VINTAGE,
             "fresh_module_root")
    p = public.load_openfigi_identity_capture(ROOT / PUBLIC, expected_manifest_sha256=MANIFESTS[PUBLIC])
    v = prices.load_sharadar_price_capture(ROOT / PRICES, expected_manifest_sha256=MANIFESTS[PRICES])
    c = current.load_sharadar_identity_capture(ROOT / CURRENT, expected_manifest_sha256=MANIFESTS[CURRENT],
                                             price_artifact_path=ROOT / PRICES)
    d, rows, excluded, meta = continuity._vintage_rows(continuity.VINTAGE_PINS, synthetic=False)
    return {"public_rows": len(p.identities), "price_rows": sum(r.row_count for r in v.responses),
            "current_rows": len(c.identities), "vintage_rows": len(d),
            "vintage_member_rows": meta["member_row_count"], "vintage_selected_rows": len(rows),
            "vintage_excluded_rows": sum(excluded.values()),
            "current_refusals": dict(Counter(code for row in c.identities for code in row.refusal_codes)),
            "vintage_refusals": dict(Counter(code for row in d for code in row.refusal_codes)),
            "manifest_pins": MANIFESTS}


def main():
    _require(Path.cwd() == ROOT and Path(__file__).resolve().parents[1] == ROOT, "fixed_root_required")
    parent = audit._open_absolute_directory(OUTPUT.parent)
    output = None
    try:
        os.mkdir(OUTPUT.name, 0o700, dir_fd=parent)  # One exclusive assessment, including failed ones.
        output = os.open(OUTPUT.name, audit._directory_flags(), dir_fd=parent)
        allocated = audit._directory_metadata(os.fstat(output))
        _require(allocated["uid"] == os.getuid() and stat.S_IMODE(allocated["mode"]) == 0o700,
                 "assessment_directory_security")
        report = {"schema": "arv2-relocated-source-fresh-use-v1", "historical_audit_accepted": False,
                  "historical_security_equivalence": False, "continuous_stability_proven": False,
                  "all_worktree_artifacts_executable": False, "formal_admission": False,
                  "production_publication_authorized": False, "provider_or_qc_contact": False,
                  "before_report_sha256": BEFORE_SHA, "after_report_sha256": AFTER_SHA,
                  "source_reauthenticated": False, "complete": False}
        try:
            before, after = _read_pinned_reports(ROOT)
            expected = _scope(before, after)
            report.update(_guarded_consume(ROOT, expected, _load_sources, security.snapshot))
            report.update(source_reauthenticated=True, complete=True)
        except Exception as error:
            report["refusal_type"] = type(error).__name__  # No private exception text or raw attribute values.
            report["refusal_code"] = error.code if isinstance(error, (audit.Refusal, security.Refusal)) else "current_security_or_source_refused"
        raw = audit._json_bytes(report)
        _require(len(raw) <= MAX_REPORT_BYTES, "assessment_report_size")
        audit._assert_root(OUTPUT.parent, parent)
        _require(allocated == audit._directory_metadata(os.fstat(output))
                 == audit._directory_metadata(os.stat(OUTPUT.name, dir_fd=parent, follow_symlinks=False)),
                 "assessment_directory_changed")
        _require(os.listdir(output) == [], "assessment_directory_not_empty")
        digest = audit._publish_report(output, "report.json", raw)
        audit._assert_root(OUTPUT.parent, parent)
        # On this fixed APFS lane, the one net-new report increases the
        # directory link count by one. No other identity/security field is
        # waived; exact names exclude an additional leaf or retained pending.
        published = {**allocated, "nlink": allocated["nlink"] + 1}
        _require(published == audit._directory_metadata(os.fstat(output))
                 == audit._directory_metadata(os.stat(OUTPUT.name, dir_fd=parent, follow_symlinks=False)),
                 "assessment_directory_changed")
        _require(os.listdir(output) == ["report.json"], "assessment_directory_extra_entry")
        print(f"complete={str(report['complete']).lower()} sources_reauthenticated={str(report['source_reauthenticated']).lower()} report_sha256={digest}")
        return 0 if report["complete"] else 1
    finally:
        if output is not None:
            os.close(output)
        os.close(parent)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("fixed relocation fresh-use assessment refused; allocated evidence retained", file=sys.stderr)
        raise SystemExit(1)
