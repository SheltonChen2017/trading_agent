"""One fixed offline relocation census; never moves or repairs any evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


OLD_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__analyst_revisions_v2")
NEW_ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
OUTPUT = "artifacts/analyst_revisions_v2/relocation_trial/R272-20261009-A"
SCHEMA = "arv2-whole-worktree-relocation-census-v1"
CHUNK_BYTES = 1024 * 1024
MAX_BASELINE_BYTES = 512 * 1024 * 1024
DIRECTORY_FIELDS = ("dev", "ino", "mode", "uid", "gid", "nlink", "flags")


class Refusal(Exception):
    def __init__(self, code, relative_path=None):
        self.code = code
        self.relative_path = relative_path
        super().__init__(code)


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                       ensure_ascii=True) + "\n").encode("ascii")


def _metadata(info):
    return {"dev": info.st_dev, "ino": info.st_ino, "size": info.st_size,
            "mode": info.st_mode, "uid": info.st_uid, "gid": info.st_gid,
            "nlink": info.st_nlink, "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns, "flags": getattr(info, "st_flags", None)}


def _directory_metadata(info):
    full = _metadata(info)
    return {key: full[key] for key in DIRECTORY_FIELDS}


def _directory_flags():
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_absolute_directory(path):
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts[1:]):
        raise Refusal("absolute_directory_required")
    fd = os.open("/", _directory_flags())
    try:
        for component in path.parts[1:]:
            child = os.open(component, _directory_flags(), dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _assert_root(root, fd):
    check = _open_absolute_directory(root)
    try:
        if _directory_metadata(os.fstat(check)) != _directory_metadata(os.fstat(fd)):
            raise Refusal("root_identity_changed")
    finally:
        os.close(check)


def _read_regular(parent, name, relative, literal, *, collect=False, maximum=None):
    named = _metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
    if not stat.S_ISREG(named["mode"]):
        raise Refusal("regular_file_required", relative)
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        held = _metadata(os.fstat(fd))
        if held != named or not stat.S_ISREG(held["mode"]):
            raise Refusal("file_identity_changed_before_read", relative)
        digest, count, found, tail = hashlib.sha256(), 0, False, b""
        chunks = [] if collect else None
        while True:
            chunk = os.read(fd, CHUNK_BYTES)
            if not chunk:
                break
            count += len(chunk)
            if maximum is not None and count > maximum:
                raise Refusal("file_size_limit", relative)
            digest.update(chunk)
            if literal:
                combined = tail + chunk
                found = found or literal in combined
                tail = combined[-(len(literal) - 1):] if len(literal) > 1 else b""
            if chunks is not None:
                chunks.append(chunk)
        after = _metadata(os.fstat(fd))
        named_after = _metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
        if held != after or held != named_after or count != held["size"]:
            raise Refusal("file_changed_during_read", relative)
        row = {"kind": "file", "metadata": held, "sha256": digest.hexdigest(),
               "contains_old_root_literal": found}
        return row, b"".join(chunks) if chunks is not None else None
    finally:
        os.close(fd)


def _excluded(relative):
    return relative == ".git" or relative == OUTPUT or relative.startswith(OUTPUT + "/")


def _census(root, root_fd, literal):
    entries = {}

    def visit(fd, relative):
        before = _directory_metadata(os.fstat(fd))
        names = sorted(os.listdir(fd))
        entries[relative or "."] = {"kind": "directory", "metadata": before}
        for name in names:
            child_relative = f"{relative}/{name}" if relative else name
            if _excluded(child_relative):
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            metadata = _metadata(info)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, _directory_flags(), dir_fd=fd)
                try:
                    initial = _directory_metadata(info)
                    if initial != _directory_metadata(os.fstat(child)):
                        raise Refusal("directory_identity_changed", child_relative)
                    visit(child, child_relative)
                    if initial != _directory_metadata(os.fstat(child)) or initial != _directory_metadata(
                            os.stat(name, dir_fd=fd, follow_symlinks=False)):
                        raise Refusal("directory_identity_changed", child_relative)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                row, _raw = _read_regular(fd, name, child_relative, literal)
                if row["metadata"] != metadata:
                    raise Refusal("file_identity_changed_before_read", child_relative)
                entries[child_relative] = row
            elif stat.S_ISLNK(info.st_mode):
                target = os.readlink(name, dir_fd=fd)
                if metadata != _metadata(os.stat(name, dir_fd=fd, follow_symlinks=False)) or target != os.readlink(name, dir_fd=fd):
                    raise Refusal("symlink_changed_during_read", child_relative)
                entries[child_relative] = {"kind": "symlink", "metadata": metadata, "target": target}
            elif any(check(info.st_mode) for check in (stat.S_ISFIFO, stat.S_ISSOCK, stat.S_ISCHR, stat.S_ISBLK)):
                # Test caches may retain FIFOs or sockets. Inventory their
                # identities without opening a blocking or device endpoint.
                metadata["rdev"] = info.st_rdev
                after_info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if metadata != {**_metadata(after_info), "rdev": after_info.st_rdev}:
                    raise Refusal("special_entry_changed", child_relative)
                entries[child_relative] = {"kind": "special", "metadata": metadata}
            else:
                raise Refusal("unsupported_filesystem_entry", child_relative)
        if names != sorted(os.listdir(fd)) or before != _directory_metadata(os.fstat(fd)):
            raise Refusal("directory_changed_during_census", relative or ".")

    _assert_root(root, root_fd)
    visit(root_fd, "")
    _assert_root(root, root_fd)
    files = [row for row in entries.values() if row["kind"] == "file"]
    artifacts = [row for name, row in entries.items()
                 if name.startswith("artifacts/analyst_revisions_v2/") and row["kind"] == "file"]
    return {"entries": entries, "entry_count": len(entries), "regular_file_count": len(files),
            "regular_file_bytes": sum(row["metadata"]["size"] for row in files),
            "artifact_regular_file_count": len(artifacts),
            "old_root_literal_file_count": sum(row["contains_old_root_literal"] for row in files),
            "artifact_old_root_literal_file_count": sum(row["contains_old_root_literal"] for row in artifacts),
            "symlink_count": sum(row["kind"] == "symlink" for row in entries.values()),
            "old_root_literal_symlink_target_count": sum(
                row["kind"] == "symlink" and literal.decode() in row["target"] for row in entries.values()),
            "special_entry_count": sum(row["kind"] == "special" for row in entries.values())}


def _open_output(root_fd, *, create):
    fd = os.dup(root_fd)
    try:
        parts = OUTPUT.split("/")
        for index, name in enumerate(parts):
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:
                    if index == len(parts) - 1:
                        raise Refusal("trial_path_already_spent") from None
            child = os.open(name, _directory_flags(), dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise Refusal("report_directory_not_private")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _assert_output(root_fd, output_fd):
    check = _open_output(root_fd, create=False)
    try:
        if _directory_metadata(os.fstat(check)) != _directory_metadata(os.fstat(output_fd)):
            raise Refusal("report_directory_identity_changed")
    finally:
        os.close(check)


def _claim_report(output, name):
    # Claim before observing a stage. An interrupted census must not become a
    # fresh attempt simply because no completed report reached publication.
    pending = name + ".pending"
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=output)
    try:
        allocated = os.fstat(fd)
        if allocated.st_uid != os.getuid() or stat.S_IMODE(allocated.st_mode) != 0o600 or allocated.st_nlink != 1:
            raise Refusal("report_allocation_not_private")
        os.fsync(fd)
        os.fsync(output)
        return fd, allocated
    except BaseException:
        os.close(fd)
        raise


def _publish_report(output, name, raw, *, claim=None):
    # Callers with an early claim retain ownership of its held descriptor.
    # Any failure leaves the exclusive pending leaf; no cleanup or retry.
    owned = claim is None
    fd, allocated = _claim_report(output, name) if owned else claim
    pending = name + ".pending"
    try:
        held = _metadata(os.fstat(fd))
        named = _metadata(os.stat(pending, dir_fd=output, follow_symlinks=False))
        if held != _metadata(allocated) or held != named or held["size"] != 0:
            raise Refusal("report_claim_changed")
        remaining = memoryview(raw)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise Refusal("report_write_failed")
            remaining = remaining[written:]
        os.fsync(fd)
        held = _metadata(os.fstat(fd))
        named = _metadata(os.stat(pending, dir_fd=output, follow_symlinks=False))
        if (held != named or (held["dev"], held["ino"], held["gid"]) != (allocated.st_dev, allocated.st_ino, allocated.st_gid)
                or held["uid"] != allocated.st_uid or held["mode"] != allocated.st_mode
                or held["flags"] != getattr(allocated, "st_flags", None)
                or held["nlink"] != 1 or held["size"] != len(raw)):
            raise Refusal("report_allocation_changed")
        os.link(pending, name, src_dir_fd=output, dst_dir_fd=output, follow_symlinks=False)
        os.unlink(pending, dir_fd=output)
        os.fsync(output)
    finally:
        if owned:
            os.close(fd)
    row, actual = _read_regular(output, name, name, b"", collect=True, maximum=MAX_BASELINE_BYTES)
    if actual != raw or stat.S_IMODE(row["metadata"]["mode"]) != 0o600 or row["metadata"]["nlink"] != 1:
        raise Refusal("report_readback_changed")
    return hashlib.sha256(raw).hexdigest()


def _compare(before, after):
    old, new = before["entries"], after["entries"]
    mismatches = []
    for name in sorted(set(old) | set(new)):
        if name not in old:
            mismatches.append({"path": name, "difference": "added"})
        elif name not in new:
            mismatches.append({"path": name, "difference": "removed"})
        elif old[name] != new[name]:
            mismatches.append({"path": name, "difference": "changed",
                               "fields": sorted(key for key in set(old[name]) | set(new[name])
                                                if old[name].get(key) != new[name].get(key))})
    return mismatches


def _run(stage, old_root, new_root, expected_before_sha256=None):
    root = old_root if stage == "before" else new_root
    if stage not in ("before", "after") or Path.cwd() != root:
        raise Refusal("wrong_stage_or_working_directory")
    if stage == "after" and (not isinstance(expected_before_sha256, str) or
                             re.fullmatch("[0-9a-f]{64}", expected_before_sha256) is None):
        raise Refusal("externally_pinned_before_digest_required")
    root_fd = _open_absolute_directory(root)
    output_fd = None
    claim = None
    try:
        output_fd = _open_output(root_fd, create=stage == "before")
        name = stage + ".json"
        existing = set(os.listdir(output_fd))
        if name in existing or name + ".pending" in existing or "before.json.pending" in existing:
            raise Refusal("report_or_pending_already_spent")
        claim = _claim_report(output_fd, name)
        report = {"schema": SCHEMA, "stage": stage, "old_root": str(old_root), "new_root": str(new_root),
                  "excluded_relative_paths": [".git", OUTPUT], "directory_times_compared": False,
                  "symlink_policy": "targets_recorded_verbatim_not_followed_or_rebased",
                  "symlink_target_resolution": False, "symlink_target_compatibility_established": False,
                  "source_loader_authentication": False, "provider_or_qc_contact": False,
                  "proves_continuous_stability": False, "complete": False}
        try:
            before = None
            if stage == "after":
                row, raw = _read_regular(output_fd, "before.json", OUTPUT + "/before.json", b"",
                                         collect=True, maximum=MAX_BASELINE_BYTES)
                if row["sha256"] != expected_before_sha256:
                    raise Refusal("before_digest_mismatch")
                if stat.S_IMODE(row["metadata"]["mode"]) != 0o600 or row["metadata"]["uid"] != os.getuid() or row["metadata"]["nlink"] != 1:
                    raise Refusal("before_report_not_private")
                before = json.loads(raw)
                if (before.get("schema") != SCHEMA or before.get("stage") != "before" or
                        before.get("complete") is not True or before.get("old_root") != str(old_root) or
                        before.get("new_root") != str(new_root) or
                        before.get("excluded_relative_paths") != [".git", OUTPUT]):
                    raise Refusal("before_report_contract_mismatch")
                report["before_report_sha256"] = expected_before_sha256
            report["census"] = _census(root, root_fd, str(old_root).encode())
            if before is not None:
                report["mismatches"] = _compare(before["census"], report["census"])
                report["matches_before"] = not report["mismatches"]
            report["complete"] = True
        except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
            report["refusal"] = {"code": error.code if isinstance(error, Refusal) else "census_operation_refused",
                                 "path": error.relative_path if isinstance(error, Refusal) else None}
        _assert_root(root, root_fd)
        _assert_output(root_fd, output_fd)
        digest = _publish_report(output_fd, name, _json_bytes(report), claim=claim)
        _assert_output(root_fd, output_fd)
        _assert_root(root, root_fd)
        return report, digest
    finally:
        if claim is not None:
            os.close(claim[0])
        if output_fd is not None:
            os.close(output_fd)
        os.close(root_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("before", "after"))
    parser.add_argument("--expected-before-sha256")
    args = parser.parse_args(argv)
    try:
        report, digest = _run(args.stage, OLD_ROOT, NEW_ROOT, args.expected_before_sha256)
        counts = report.get("census", {})
        print(f"stage={args.stage} complete={str(report['complete']).lower()} "
              f"regular_files={counts.get('regular_file_count', 0)} "
              f"artifact_files={counts.get('artifact_regular_file_count', 0)} "
              f"old_root_literal_files={counts.get('old_root_literal_file_count', 0)} "
              f"artifact_old_root_literal_files={counts.get('artifact_old_root_literal_file_count', 0)} "
              f"symlinks={counts.get('symlink_count', 0)} special_entries={counts.get('special_entry_count', 0)} "
              f"mismatches={len(report.get('mismatches', []))} report_sha256={digest}")
        return 0 if report["complete"] and report.get("matches_before", True) else 1
    except (Refusal, OSError, ValueError, KeyError, TypeError):
        print("relocation census refused; allocated evidence retained", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
