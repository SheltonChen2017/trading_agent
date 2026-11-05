"""Protected, read-only adapter for the one completed registered child run.

Historical metadata anchors are independently registered in the lane record. No credentials, HTTP, source writes or economic joins.
The contextmanager keeps original source directory FDs alive during replay.
"""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from types import MappingProxyType

from data.hashing import hash_bytes
import scripts.continue_short_interest_native_identity as capture

import scripts.verify_short_interest_native_identity_continuation as replay

ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
HEAD = "64f372ea8bfbcc542e87356a5e3e58fe07da1c27"
REMOTE = "1f90c626328a236c51e78f57e0fe301e0412aabf"
RUN_ID = "native-identity-continuation-20261014T021244Z"
CHILD = capture.PARENT / RUN_ID
FILE_COUNT = 2619
# Main independently verified protected custody at exact HEAD before these
# source-only anchors were supplied; saved completion flags are still replayed.
ANCHORS = {
    "aggregate_inventory_sha256": "92f3eccbfb8985256a35364c4bf6739483e8fbbe41d563d5df2a0ed0954dd5b8",
    "budget_bytes_sha256": "f58314801ad84ddbd0f0de203efecf18a693ebc44dc089d4bcc15751c72a064e",
    "code_identity_sha256": "00fd3e26b30ee6227eb734ee8afe66ceb8dd93f1b027c90bc7c4f1dd78ab55ca",
    "protocol_bytes_sha256": "feebd180007f8c6fc07e1b5f55fc61131bfc8431ba1775d75063de6114cf045d",
    "started_bytes_sha256": "37379cc10e00c9c88aabf33de2498a6486c6f12d2a9f2185dafaf92714c8fa79",
    "completed_bytes_sha256": "4e00eea1b206990164e3463533947d1ba73b0da09935e58ae26c89c3ecce46ea",
    "inventory_bytes_sha256": "09b63be5420d7ecfef4b5c42bcff12d7721ed715457feaf9d681764d48338e39",
}


def maximum(name):
    if re.fullmatch(r"date-[0-9]{3}-(active|inactive)-page-[0-9]{2}\.raw", name):
        return capture.identity.MAXIMUM_RESPONSE_BYTES
    if re.fullmatch(r"date-[0-9]{3}\.qualified\.private\.json", name):
        return capture.identity.MAXIMUM_DATE_REPORT_BYTES
    replay.require(name in {"protocol.private.json", "started.json", "completed.json", "inventory.private.json"}
            or re.fullmatch(r"date-[0-9]{3}-(active|inactive)-page-[0-9]{2}\.(started|received)\.json", name),
            "closed_child_filename")
    return 8 * 1024 * 1024 if name in {"protocol.private.json", "inventory.private.json"} else 65536


def read_owned_source(owned, name, limit, *, parent=False):
    """Read without following mutable paths or accepting another file inode."""
    owned.check()
    replay.require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", name)
            and name not in {".", ".."} and type(limit) is int and limit > 0
            and type(parent) is bool, "protected_child_read_descriptor")
    directory_fd = owned._anchor[3 if parent else 2]
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        def check_file():
            owned.check()
            info, named = os.fstat(fd), os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            for value in (info, named):
                replay.require(stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid()
                        and stat.S_IMODE(value.st_mode) == 0o600 and value.st_nlink == 1
                        and value.st_size <= limit, "protected_child_file_protection")
            def stamp(value):
                return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns
            replay.require(stamp(info) == stamp(named), "protected_child_file_inode_changed")
            return stamp(info)
        original = check_file()
        chunks, length = [], 0
        while True:
            replay.require(check_file() == original, "protected_child_changed_while_reading")
            chunk = os.read(fd, min(65536, limit + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
            replay.require(length <= limit, "protected_child_response_limit")
        replay.require(check_file() == original and length == original[2], "protected_child_final_read_binding")
        return b"".join(chunks)
    finally:
        os.close(fd)


@contextmanager
def load_protected_completed(root, *, head, remote):
    capture._require_capture_platform()  # Unsupported hosts refuse before private source access.
    replay.require(root == ROOT and head == HEAD and remote == REMOTE, "fixed_completed_identity_lane")
    capture._local(root, head)
    replay.require(type(ANCHORS) is dict and set(ANCHORS) == {"aggregate_inventory_sha256", "budget_bytes_sha256",
            "code_identity_sha256", "protocol_bytes_sha256", "started_bytes_sha256", "completed_bytes_sha256",
            "inventory_bytes_sha256"} and all(replay.digest(value) for value in ANCHORS.values()),
            "completed_identity_anchors_unregistered")
    registered = dict(ANCHORS)
    capture._guard_remote(root, remote)
    source = capture.load_parent(root, head=head)
    capture._local(root, head)
    with capture._OwnedOutput(root / CHILD, lambda: capture._local(root, head)) as owned:
        owned.check()
        names = tuple(sorted(os.listdir(owned._anchor[2])))
        replay.require(len(names) == FILE_COUNT, "exact_closed_child_file_count")
        entries = {}
        anchor_names = {"protocol.private.json": "protocol_bytes_sha256", "started.json": "started_bytes_sha256",
                "completed.json": "completed_bytes_sha256", "inventory.private.json": "inventory_bytes_sha256"}
        for name in names:
            raw = read_owned_source(owned, name, maximum(name))
            sha = hash_bytes(raw)
            replay.require(name not in anchor_names or sha == registered[anchor_names[name]],
                    "registered_child_anchor_bytes")
            entries[name] = (sha, len(raw))
        files = object.__new__(capture._ParentFiles)
        reader = lambda name: read_owned_source(owned, name, maximum(name))
        anchor = (MappingProxyType(entries), reader)
        for name, value in (("_entries", anchor[0]), ("_reader", reader), ("_anchor", anchor), ("_anchor_identity", anchor)):
            object.__setattr__(files, name, value)
        replay.require(files.inventory_sha256() == registered["aggregate_inventory_sha256"],
                "registered_child_all_file_inventory")
        state = source.payload()
        claim_id = capture.hash_payload({"source_inventory_sha256": state["source_inventory_sha256"],
                "failed_request_sha256": state["failed_request_sha256"],
                "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
                "purpose": "single_explicit_native_identity_manual_continuation"})
        budget = read_owned_source(owned, "budget-" + claim_id + ".json", 65536, parent=True)

        def historical(commit, name):
            owned.check()
            replay.require(commit == HEAD and name in capture.CODE_FILES, "fixed_completed_child_code_path")
            result = subprocess.run(["git", "show", commit + ":" + name], cwd=root,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            owned.check()
            replay.require(result.returncode == 0 and type(result.stdout) is bytes, "historical_child_code_unavailable")
            return result.stdout

        result = replay.verify_completed_continuation(source, files, byte_pins=files.pins(),
                inventory_sha256=registered["aggregate_inventory_sha256"], budget_raw=budget,
                budget_sha256=registered["budget_bytes_sha256"], expected_head=HEAD,
                expected_protocol_sha256=capture.EXPECTED_PROTOCOL_SHA256,
                expected_code_identity_sha256=registered["code_identity_sha256"], historical_code=historical,
                local_guard=owned.check, expected_run_id=RUN_ID, expected_remote_head=REMOTE)
        owned.check()
        replay.require(ANCHORS == registered and tuple(sorted(os.listdir(owned._anchor[2]))) == names,
                "registered_child_descriptor_changed")
        capture._guard_remote(root, remote)
        yield result
        owned.check()
