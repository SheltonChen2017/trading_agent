"""Finite read-only USB byte inspection, never protected-source custody.

The ExFAT input is deliberately not passed to HeldFiles(protected=True).  Its
original descriptor/name stamps and byte pins must survive the whole observed
read; that observation grants no immutable-source or later input authority.
No report/journal file, source request, credential or capture claim is created.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from types import ModuleType

from data.hashing import hash_payload


ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
USB = Path("/Volumes/SANDISK/firstrate")
DRIVER = "scripts/inspect_short_interest_usb_archive.py"
MODEL = "research/short_interest_etf/firstrate_short_interest_inspection.py"
MAX_SECONDS = 180
CODE_FILES = (
    "data/__init__.py", "data/hashing.py", MODEL, DRIVER,
)
INPUTS = (
    ("full", "fundamentals/Short_Interest/Full_Dataset.zip", 34319601,
     "08f019c20384bde811b10d1674dc5067cfded4e4c0097fc8c383649c528429c8"),
    ("year", "fundamentals/Short_Interest/2026_data_only.zip", 9660009,
     "3a8a07dec5c91f4e54cda396d9b1483895769d6ecac1a8d1a15a64e873fa191a"),
    ("manifest", "manifest.json", 327907,
     "c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8"),
    ("readme", "fundamentals/Short_Interest/Read_Me_Documentation.txt", 1051,
     "bbcddf477ba3ffacb4b0116e9d3f6c2c2a864576ae748abc8daa825602a16ecf"),
)
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CODES = frozenset("""read_arguments clock_nonfinite clock_or_deadline
regular_bounded_single_link read_byte_bound read_failure_latched
original_directory_changed original_file_stamp_changed original_file_bytes_changed
descriptor_close_failed closed_original_required post_close_original_changed
exact_git_hashes_required designated_physical_root lane_snapshot_changed
matching_remote_changed working_code_differs_from_commit fixed_usb_input_changed
terminal_code_changed exact_head_remote_arguments_required model_namespace_occupied
""".split())


class UsbInspectionRefusal(ValueError):
    """Fixed safe contract codes; external exception strings never escape."""


def require(value, code):
    if not value:
        raise UsbInspectionRefusal(code)


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, "st_flags", 0))


class _Clock:
    def __init__(self):
        self.start = self.last = time.monotonic()
        require(math.isfinite(self.start), "clock_nonfinite")

    def check(self):
        now = time.monotonic()
        require(math.isfinite(now) and self.last <= now
                and 0 <= now - self.start <= MAX_SECONDS, "clock_or_deadline")
        self.last = now


class _Read:
    """Original RO descriptor and original path-chain observations; no reseal."""

    def __init__(self, path, maximum, clock, *, minimum=1):
        self.path = Path(path)
        require(self.path.is_absolute() and maximum > 0
                and type(minimum) is int and minimum in (0, 1), "read_arguments")
        self.maximum, self.clock, self.fds, self.directories = maximum, clock, [], []
        self.minimum = minimum
        self.failed = False
        try:
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(fd)
            self.root_original = _stamp(os.fstat(fd))
            for name in self.path.parts[1:-1]:
                clock.check()
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=fd)
                self.fds.append(child)
                original = _stamp(os.fstat(child))
                self.directories.append((fd, name, child, original))
                fd = child
            self.parent, self.name = fd, self.path.name
            self.fd = os.open(self.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                              dir_fd=self.parent)
            self.fds.append(self.fd)
            info = os.fstat(self.fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and minimum <= info.st_size <= maximum, "regular_bounded_single_link")
            self.original = _stamp(info)
            self.raw = self._read()
            self.digest = hashlib.sha256(self.raw).hexdigest()
            self.audit()
        except BaseException:
            self.failed = True
            self._close()
            raise

    def _read(self):
        self.clock.check()
        os.lseek(self.fd, 0, os.SEEK_SET)
        result = bytearray()
        while True:
            self.clock.check()
            part = os.read(self.fd, min(1024 * 1024, self.maximum + 1 - len(result)))
            if not part:
                break
            result.extend(part)
            require(len(result) <= self.maximum, "read_byte_bound")
        return bytes(result)

    def audit(self):
        require(not self.failed, "read_failure_latched")
        try:
            self.clock.check()
            require(_stamp(os.fstat(self.fds[0])) == self.root_original
                    and _stamp(os.stat("/", follow_symlinks=False)) == self.root_original,
                    "original_directory_changed")
            for parent, name, fd, original in self.directories:
                require(_stamp(os.fstat(fd)) == original
                        and _stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == original,
                        "original_directory_changed")
            require(_stamp(os.fstat(self.fd)) == self.original
                    and _stamp(os.stat(self.name, dir_fd=self.parent,
                                       follow_symlinks=False)) == self.original,
                    "original_file_stamp_changed")
            raw = self._read()
            require(raw == self.raw and hashlib.sha256(raw).hexdigest() == self.digest,
                    "original_file_bytes_changed")
            require(_stamp(os.fstat(self.fd)) == self.original
                    and _stamp(os.stat(self.name, dir_fd=self.parent,
                                       follow_symlinks=False)) == self.original,
                    "original_file_stamp_changed")
        except BaseException:
            self.failed = True
            raise

    def _close(self):
        error = None
        while self.fds:
            try:
                os.close(self.fds.pop())
            except OSError as exc:
                error = exc
        if error is not None:
            self.failed = True
            raise UsbInspectionRefusal("descriptor_close_failed") from None

    def close(self):
        try:
            # Preserve an original exception already in flight; a failed read
            # still closes every owned FD and can never yield a result.
            if not self.failed:
                self.audit()
        finally:
            self._close()

    def after_close(self):
        try:
            require(not self.failed and not self.fds, "closed_original_required")
            # A new read is compared to the ORIGINAL observation, never adopted.
            fresh = _Read(self.path, self.maximum, self.clock, minimum=self.minimum)
            try:
                require(fresh.original == self.original and fresh.raw == self.raw
                        and fresh.digest == self.digest
                        and fresh.root_original == self.root_original
                        and [row[3] for row in fresh.directories]
                        == [row[3] for row in self.directories],
                        "post_close_original_changed")
            finally:
                fresh.close()
            # The last fresh data/parent handles are now CLOSED. This is a
            # named comparison against the ORIGINAL stamps, not a new baseline.
            require(_stamp(os.stat("/", follow_symlinks=False)) == self.root_original,
                    "post_close_original_changed")
            current = Path("/")
            for unused_parent, name, unused_fd, original in self.directories:
                current /= name
                require(_stamp(os.stat(current, follow_symlinks=False)) == original,
                        "post_close_original_changed")
            require(_stamp(os.stat(self.path, follow_symlinks=False)) == self.original,
                    "post_close_original_changed")
            self.clock.check()
        except BaseException:
            self.failed = True
            raise


def _inspect_pair(model_bytes, **blobs):
    """Execute only already-held, committed MODEL code, never archive bytes.

    Importing the research package would initialize unrelated calendar/pandas
    code. This explicit four-file inspection closure avoids that side effect
    without changing the shared package or pretending to cover those imports.
    """
    name = "_si_usb_registered_byte_inspector"
    require(name not in sys.modules, "model_namespace_occupied")
    module = ModuleType(name)
    module.__file__ = str(ROOT / MODEL)
    sys.modules[name] = module
    try:
        exec(compile(model_bytes, module.__file__, "exec"), module.__dict__)
        report = module.inspect_registered_pair(**blobs)
        return report.to_payload(), hash_payload(module.inspection_policy())
    finally:
        del sys.modules[name]


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT,
                                   stderr=subprocess.PIPE, timeout=20)


def _guard(head, remote):
    require(type(head) is str and _GIT_SHA.fullmatch(head)
            and type(remote) is str and _GIT_SHA.fullmatch(remote), "exact_git_hashes_required")
    require(Path.cwd().resolve() == ROOT and ROOT.resolve() == ROOT,
            "designated_physical_root")
    require(_git("rev-parse", "--show-toplevel").decode().strip() == str(ROOT)
            and _git("branch", "--show-current").decode().strip() == "codex/strategy-short-interest"
            and _git("rev-parse", "HEAD").decode().strip() == head
            and not _git("status", "--porcelain=v1", "--untracked-files=normal").strip(),
            "lane_snapshot_changed")
    require(_git("rev-parse", "refs/remotes/origin/codex/strategy-short-interest").decode().strip() == remote
            and _git("ls-remote", "--exit-code", "--refs", "origin",
                     "refs/heads/codex/strategy-short-interest").decode().split()
            == [remote, "refs/heads/codex/strategy-short-interest"], "matching_remote_changed")


def inspect_registered(head, remote):
    """Observe the fixed external bytes once; returns no source capability."""
    clock = _Clock()
    _guard(head, remote)
    codes, sources = [], []
    with ExitStack() as stack:
        for rel in CODE_FILES:
            # Empty committed Python package initializers are valid CODE.
            # The four external source roles retain minimum=1 and exact pins.
            item = _Read(ROOT / rel, 1024 * 1024, clock, minimum=0)
            stack.callback(item.close)
            require(item.raw == _git("show", head + ":" + rel), "working_code_differs_from_commit")
            codes.append(item)
        blobs = {}
        for role, rel, length, digest in INPUTS:
            item = _Read(USB / rel, length, clock)
            stack.callback(item.close)
            require(len(item.raw) == length and item.digest == digest, "fixed_usb_input_changed")
            sources.append(item)
            blobs[role] = item.raw
        clock.check()
        model_bytes = codes[CODE_FILES.index(MODEL)].raw
        provisional, policy_sha = _inspect_pair(model_bytes, **blobs)
        clock.check()
        for item in codes + sources:
            item.audit()
    # No success escapes until every original close and fresh committed-code
    # check succeeds, followed by named reads against original source stamps.
    _guard(head, remote)
    for rel, item in zip(CODE_FILES, codes):
        item.after_close()
        require(item.raw == _git("show", head + ":" + rel), "terminal_code_changed")
    for item in sources:
        item.after_close()
    _guard(head, remote)
    clock.check()
    payload = {
        "schema": "si-usb-external-byte-inspection-observation-v1",
        "status": "closed_external_byte_inspection_not_custody",
        "runtime_head": head, "matching_remote": remote,
        "policy_sha256": policy_sha,
        "code_mapping_sha256": hash_payload(dict(zip(CODE_FILES, (x.digest for x in codes)))),
        "original_input_stamps_sha256": hash_payload([list(x.original) for x in sources]),
        "all_original_read_contexts_closed": True,
        "protected_source_custody_verified": False,
        "new_provider_HTTP": 0, "credential_reads": 0, "new_claims": 0,
        "new_STARTs": 0, "new_charged_bytes": 0,
        "inspection": provisional,
    }
    payload["observation_sha256"] = hash_payload(payload)
    return payload


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        require(len(args) == 2, "exact_head_remote_arguments_required")
        result = inspect_registered(*args)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
        return 0
    except Exception as exc:
        # Fixed local codes only; no path, source values or exception text.
        code = (exc.args[0] if type(exc) is UsbInspectionRefusal and len(exc.args) == 1
                and type(exc.args[0]) is str and exc.args[0] in _CODES
                else "unexpected_local_refusal")
        print(json.dumps({"status": "refused_external_byte_inspection", "code": code,
                          "custody_qualified": False, "source_admitted": False}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
