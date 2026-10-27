"""Finite new APFS image for a synthetic custody proof, never source storage.

No existing evidence is copied, mounted, adopted, unlocked or removed.  The
backing image is a mutable container, NOT an immutable evidence inode.  Its
identity/protection are checked independently of every inner-file seal.  A
SPARSE image is an intermediate proof target, not durable production storage.
"""
from contextlib import contextmanager
import ctypes
import errno
import json
import math
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import time

from data.hashing import canonical_json, hash_bytes, hash_payload

ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
PARENT = Path("artifacts/short_interest/native_reported_counts")
NAMESPACE = "isolated-custody-20261027-v6"
IMAGE_NAME, MOUNT_NAME = "backing.sparseimage", "mount"
HDIUTIL, LIBRARY = "/usr/bin/hdiutil", "/usr/lib/libSystem.B.dylib"
VIRTUAL_BYTES = 8 * 1024 ** 3
MAXIMUM_SECONDS, SUBPROCESS_SECONDS = 300, 120
MAXIMUM_PLIST_BYTES, MAXIMUM_IMAGES, MAXIMUM_ENTITIES = 4 * 1024 ** 2, 256, 64
MNT_RDONLY, MNT_LOCAL = 0x00000001, 0x00001000
MNT_DONTBROWSE, MNT_IGNORE_OWNERSHIP = 0x00100000, 0x00200000
_MINTED, _ISSUED, _FAILED = {}, {}, set()
_FROZEN, _CLOCKS, _COMMANDS = {}, {}, {}
_ORIGIN_ISSUED, _STATE_ORIGINS, _ASSOCIATION_ISSUED = {}, {}, {}
_ROOT_ENFORCEMENTS = {}
_LAST_ASSOCIATION = None
_USED = False
_CODES = frozenset("""isolated_platform_refused isolated_native_unavailable isolated_native_result_refused
isolated_native_string_refused isolated_root_changed isolated_policy_changed isolated_deadline
isolated_clock_refused isolated_directory_protection isolated_directory_changed isolated_backing_protection
isolated_backing_changed isolated_namespace_exists isolated_namespace_changed isolated_mount_preexists
isolated_parent_filesystem_refused isolated_host_capacity_refused isolated_command_refused
isolated_command_failed isolated_command_timeout isolated_plist_refused isolated_image_association_refused
isolated_attach_association_refused isolated_mount_association_refused isolated_mount_filesystem_refused
isolated_mount_capacity_refused isolated_factory_required isolated_capability_changed isolated_failure_latched
isolated_not_live isolated_not_closed isolated_already_used isolated_close_failed isolated_phase_changed
isolated_mount_not_apfs isolated_mount_owner_refused
isolated_mount_not_local isolated_mount_browse_refused isolated_mount_ownership_ignored
isolated_mount_readonly isolated_mount_name_changed isolated_mount_device_changed
isolated_mount_native_identity_changed isolated_origin_refused isolated_descriptor_refused
isolated_device_node_refused isolated_device_node_changed isolated_new_root_mode_refused
isolated_new_root_identity_changed isolated_new_root_enforcement_repeated""".split())
_ERRNOS = {getattr(errno, name): name for name in (
    "EACCES", "EPERM", "EEXIST", "ENOENT", "ENOSPC", "EIO", "EBADF", "EINVAL", "ENOTSUP")
    if hasattr(errno, name)}


class IsolatedVolumeRefusal(ValueError):
    def __init__(self, code, number=None):
        code = code if type(code) is str and code in _CODES else "isolated_capability_changed"
        self._errno_name = _ERRNOS.get(number) if type(number) is int else None
        super().__init__("REFUSED: " + code)


def require(value, code):
    if not value: raise IsolatedVolumeRefusal(code)


def failure_summary(error):
    code, number = None, None
    if type(error) is IsolatedVolumeRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = next((item for item in _CODES if type(args) is tuple and len(args) == 1
            and type(args[0]) is str and args[0] == "REFUSED: " + item), None)
        try: number = object.__getattribute__(error, "_errno_name")
        except AttributeError: pass
    return {"category": "local_contract_refusal" if type(error) is IsolatedVolumeRefusal else
        "unknown_local_error", "contract_code": code,
        "errno_name": number if type(number) is str and number in _ERRNOS.values() else None}


def authority():
    return {"synthetic_proof_only": True, "persistent_production_storage_admitted": False,
        "source_admitted": False, "provider_HTTP": 0, "credential_reads": 0,
        "new_source_claims": 0, "source_STARTs": 0, "source_bytes": 0,
        "historical_actor": "UNKNOWN", "historical_repair_established": False,
        "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


def policy():
    require(VIRTUAL_BYTES == 8 * 1024 ** 3 and MAXIMUM_SECONDS == 300 and SUBPROCESS_SECONDS == 120
        and MAXIMUM_PLIST_BYTES == 4 * 1024 ** 2 and MAXIMUM_IMAGES == 256 and MAXIMUM_ENTITIES == 64
        and HDIUTIL == "/usr/bin/hdiutil" and LIBRARY == "/usr/lib/libSystem.B.dylib"
        and PARENT == Path("artifacts/short_interest/native_reported_counts")
        and NAMESPACE == "isolated-custody-20261027-v6" and IMAGE_NAME == "backing.sparseimage"
        and MOUNT_NAME == "mount"
        and (MNT_RDONLY, MNT_LOCAL, MNT_DONTBROWSE, MNT_IGNORE_OWNERSHIP)
            == (0x00000001, 0x00001000, 0x00100000, 0x00200000), "isolated_policy_changed")
    return {"schema": "si-isolated-custody-volume-policy-v6", "root": str(ROOT),
        "parent": str(PARENT), "namespace": NAMESPACE, "image": IMAGE_NAME, "mount": MOUNT_NAME,
        "virtual_bytes": VIRTUAL_BYTES, "filesystem": "APFS", "image_type": "SPARSE",
        "purpose": "finite_synthetic_intermediate_only_not_durable_production_storage",
        "spotlight_index_creation": False,
        "volume_name": "SI_OFFLINE_CUSTODY_V6", "failed_v1_namespace_retired_even_if_absent": True,
        "failed_v2_image_and_mount_never_modified_or_adopted": True,
        "failed_v3_flagged_inode_image_mount_never_modified_or_adopted": True,
        "failed_v4_flagged_inode_image_mount_never_modified_or_adopted": True,
        "failed_v5_flagged_inode_image_mount_never_modified_or_adopted": True,
        "maximum_seconds": MAXIMUM_SECONDS, "subprocess_seconds": SUBPROCESS_SECONDS,
        "maximum_plist_bytes": MAXIMUM_PLIST_BYTES, "maximum_images": MAXIMUM_IMAGES,
        "plist_limit_kind": "post_capture_acceptance_not_hard_capture_memory_bound",
        "output_origin": "fixed_local_hdiutil_commands_only_no_shell_or_provider_response",
        "maximum_entities": MAXIMUM_ENTITIES, "hdiutil": HDIUTIL,
        "mount_masks": {"readonly": MNT_RDONLY, "local": MNT_LOCAL,
            "dontbrowse": MNT_DONTBROWSE, "ignore_ownership": MNT_IGNORE_OWNERSHIP},
        "native": "SDK_statfs64_size2168_fixed_libSystem_fstatfs64_int_int_pointer",
        "ownership": "fresh_root_UID_native_identity_and_blocknode_before_one_original_FD_fchmod0700_then_original_pin",
        "mount": "fixed_nobrowse_noautoopen_local_APFS_original_device_fsid_and_root_identity",
        "device_node": "nofollow_block_device_original_dev_ino_rdev_mode_uid_gid_rdev_equals_mount_dev_never_open_device",
        "cross_origin_association": "exact_unique_device_mount_join_with_native_APFS_blocknode_witness_not_optional_vendor_text_equality",
        "mounted_content_hints": [None, "Apple_APFS", "Apple_APFS_Volume",
            "41504653-0000-11AA-AA11-00306543ECAC", "7C3457EF-0000-11AA-AA11-00306543ECAC"],
        "hint_GUID_case": "ASCII_hex_case_only", "mounted_volume_kinds": [None, "apfs"],
        "origin_custody": "both_original_full_raw_outputs_and_parsed_tuples_retained_later_selected_info_raw_identity_exact",
        "association_projection": "original_issued_canonical_bytes_hashes_counts_booleans_fixed_field_names_only_false_authority",
        "fresh_root_initial_modes": [0o700, 0o755], "fresh_root_mode_enforcements": 1,
        "backing": "current_uid_0600_singlelink_original_inode_mutable_container_size_times_not_evidence_seal",
        "inner_evidence": "all_original_checks_unchanged_no_adoption_reseal_or_flag_clearing",
        "creation": "new_namespace_and_backing_only_no_overwrite_retry_shadow_copy_or_cleanup",
        "closure": "original_FDs_close_then_readonly_original_pin_audit_factory_issued_witness",
        "authority": authority()}


class _StatFS64(ctypes.Structure):
    # Installed Darwin SDK sys/mount.h __DARWIN_STRUCT_STATFS64; fsid_t is two int32s.
    _fields_ = [("f_bsize", ctypes.c_uint32), ("f_iosize", ctypes.c_int32),
        ("f_blocks", ctypes.c_uint64), ("f_bfree", ctypes.c_uint64),
        ("f_bavail", ctypes.c_uint64), ("f_files", ctypes.c_uint64),
        ("f_ffree", ctypes.c_uint64), ("f_fsid", ctypes.c_int32 * 2),
        ("f_owner", ctypes.c_uint32), ("f_type", ctypes.c_uint32),
        ("f_flags", ctypes.c_uint32), ("f_fssubtype", ctypes.c_uint32),
        ("f_fstypename", ctypes.c_char * 16), ("f_mntonname", ctypes.c_char * 1024),
        ("f_mntfromname", ctypes.c_char * 1024), ("f_flags_ext", ctypes.c_uint32),
        ("f_reserved", ctypes.c_uint32 * 7)]


def _platform():
    require(sys.platform == "darwin" and os.name == "posix" and ctypes.sizeof(ctypes.c_void_p) == 8
        and ctypes.sizeof(_StatFS64) == 2168 and _StatFS64.f_fsid.offset == 48
        and _StatFS64.f_flags.offset == 64 and _StatFS64.f_fstypename.offset == 72
        and _StatFS64.f_mntonname.offset == 88 and _StatFS64.f_mntfromname.offset == 1112
        and _StatFS64.f_flags_ext.offset == 2136 and os.open in os.supports_dir_fd
        and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"), "isolated_platform_refused")


def _native_statfs(fd):
    _platform()
    require(type(fd) is int and fd >= 0, "isolated_native_result_refused")
    try:
        operation = ctypes.CDLL(LIBRARY, use_errno=True).fstatfs64
        operation.argtypes, operation.restype = (ctypes.c_int, ctypes.POINTER(_StatFS64)), ctypes.c_int
        value = _StatFS64(); ctypes.set_errno(0)
        result = operation(fd, ctypes.byref(value)); number = ctypes.get_errno()
    except (AttributeError, OSError):
        raise IsolatedVolumeRefusal("isolated_native_unavailable") from None
    require(type(result) is int and result in (0, -1), "isolated_native_result_refused")
    if result != 0: raise IsolatedVolumeRefusal("isolated_native_result_refused", number)
    def text(raw, maximum):
        try: decoded = raw.decode("utf-8")
        except UnicodeError: raise IsolatedVolumeRefusal("isolated_native_string_refused") from None
        require(type(raw) is bytes and 0 < len(raw) < maximum and "\0" not in decoded,
            "isolated_native_string_refused")
        return decoded
    return {"bsize": value.f_bsize, "blocks": value.f_blocks, "bavail": value.f_bavail,
        "fsid": tuple(value.f_fsid), "owner": value.f_owner, "flags": value.f_flags,
        "flags_ext": value.f_flags_ext, "type": value.f_type, "subtype": value.f_fssubtype,
        "fstype": text(value.f_fstypename, 16), "mounted_on": text(value.f_mntonname, 1024),
        "mounted_from": text(value.f_mntfromname, 1024)}


def _directory(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o700, "isolated_directory_protection")
    return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)


def _backing(info):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
        and type(info.st_size) is int and 0 < info.st_size <= VIRTUAL_BYTES + 64 * 1024 ** 2,
        "isolated_backing_protection")
    # Growth/size/mtime/ctime are not an inner evidence seal. Identity is immutable.
    return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode), info.st_nlink


def _mount_identity(native):
    return tuple(native[key] for key in ("fsid", "owner", "flags", "flags_ext", "type", "subtype",
        "fstype", "mounted_on", "mounted_from"))


def _fixed_state(state):
    return {"policy": state["policy"], "image": str(state["image"]), "mount": str(state["mount"]),
        "directories": [(str(path), fd, pin) for path, fd, pin in state["directories"]],
        "namespace_fd": state["namespace_fd"], "host_device": state["host_device"],
        "backing_fd": state["backing_fd"], "backing_pin": state["backing_pin"],
        "under_mount_fd": state["under_mount_fd"], "under_mount_pin": state["under_mount_pin"],
        "device": state["device"], "attach_entities": state["attach_entities"],
        "mount_fd": state["mount_fd"], "mount_pin": state["mount_pin"],
        "mount_native": state["mount_native"], "info_entities": state["info_entities"],
        "device_node_pin": state["device_node_pin"], "root_creation_pin": state["root_creation_pin"],
        "root_mode_enforced": state["root_mode_enforced"],
        "root_enforcement_record": _root_enforcement_record(state),
        "attach_origin": _origin_pin(state, state["attach_origin"], "attach"),
        "info_origin": _origin_pin(state, state["info_origin"], "info"),
        "selected_info_identity": state["selected_info_identity"]}


def _original_state(state):
    original = _FROZEN.get(id(state))
    require(type(original) is tuple and len(original) == 2 and original[0] is state
        and original[1] == hash_payload(_fixed_state(state)), "isolated_capability_changed")


def _tick(state):
    original = _CLOCKS.get(id(state))
    require(type(original) is tuple and len(original) == 5 and original[0] is state
        and original[1] == state["begin"] and original[2] == state["last"]
        and original[3] is state["monotonic"] and original[4] is state["boundary"], "isolated_clock_refused")
    current = original[3]()
    require(type(current) in (int, float) and not isinstance(current, bool) and math.isfinite(current)
        and state["begin"] <= state["last"] <= current, "isolated_clock_refused")
    require(current - state["begin"] <= MAXIMUM_SECONDS, "isolated_deadline")
    state["last"] = current
    _CLOCKS[id(state)] = state, original[1], current, original[3], original[4]
    return current


def _boundary(state):
    _tick(state); state["boundary"](); _tick(state)
    require(state["policy"] == hash_payload(policy()), "isolated_policy_changed")


def _arguments(state, verb):
    image, mount = str(state["image"]), str(state["mount"])
    if verb == "create":
        return [HDIUTIL, "create", "-type", "SPARSE", "-size", "8g", "-fs", "APFS",
            "-uid", str(os.getuid()), "-gid", str(os.getgid()), "-mode", "0700",
            "-volname", "SI_OFFLINE_CUSTODY_V6", "-nospotlight", "-plist", image]
    if verb == "attach":
        return [HDIUTIL, "attach", "-mountpoint", mount, "-mount", "required", "-nobrowse",
            "-owners", "on", "-noautoopen", "-noautoopenro", "-noautoopenrw", "-plist", image]
    require(verb == "info", "isolated_command_refused")
    return [HDIUTIL, "info", "-plist"]


def _run(state, verb):
    _boundary(state)
    remaining = MAXIMUM_SECONDS - (_tick(state) - state["begin"])
    require(remaining > 0, "isolated_deadline")
    try:
        result = subprocess.run(_arguments(state, verb), cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
            timeout=min(SUBPROCESS_SECONDS, remaining), env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except subprocess.TimeoutExpired:
        raise IsolatedVolumeRefusal("isolated_command_timeout") from None
    except OSError as error:
        raise IsolatedVolumeRefusal("isolated_command_failed", error.errno) from None
    _boundary(state)
    require(type(result.returncode) is int and result.returncode == 0, "isolated_command_failed")
    require(type(result.stdout) is bytes and 0 < len(result.stdout) <= MAXIMUM_PLIST_BYTES,
        "isolated_plist_refused")
    try: payload = plistlib.loads(result.stdout)
    except (ValueError, TypeError, OverflowError, plistlib.InvalidFileException):
        raise IsolatedVolumeRefusal("isolated_plist_refused") from None
    original = _COMMANDS.get(id(state))
    require(type(original) is tuple and len(original) == 2 and original[0] is state
        and tuple(state["commands"]) == original[1], "isolated_capability_changed")
    state["commands"].append(verb)
    _COMMANDS[id(state)] = state, (*original[1], verb)
    token = object()
    _ORIGIN_ISSUED[token] = state, verb, result.stdout, hash_payload(_arguments(state, verb))
    existing = _STATE_ORIGINS.get(id(state), (state, ()))
    require(existing[0] is state, "isolated_origin_refused")
    _STATE_ORIGINS[id(state)] = state, (*existing[1], token)
    state["last_origin"] = token
    return payload


def _origin_data(state, token, verb):
    row, original = _ORIGIN_ISSUED.get(token), _STATE_ORIGINS.get(id(state))
    require(type(row) is tuple and len(row) == 4 and row[0] is state and row[1] == verb
        and type(row[2]) is bytes and 0 < len(row[2]) <= MAXIMUM_PLIST_BYTES
        and type(original) is tuple and original[0] is state and token in original[1], "isolated_origin_refused")
    return row


def _origin_pin(state, token, verb):
    row = _origin_data(state, token, verb)
    return row[1], hash_bytes(row[2]), row[3]


def association_diagnostic():
    """Copy of an ORIGINAL privately issued observation, never caller payload."""
    if _LAST_ASSOCIATION is None:
        return {"schema": "si-isolated-association-diagnostic-v1", "status": "not_observed",
            "authority": authority()}
    row = _ASSOCIATION_ISSUED.get(_LAST_ASSOCIATION)
    require(type(row) is tuple and len(row) == 2 and row[0] is _LAST_ASSOCIATION
        and type(row[1]) is bytes, "isolated_origin_refused")
    return json.loads(row[1])


def _issue_association(state, info_origin=None):
    """Project the actual original two command outputs BEFORE any join refusal."""
    global _LAST_ASSOCIATION
    attach_raw = _origin_data(state, state["attach_origin"], "attach")[2]
    attach_payload = plistlib.loads(attach_raw)
    info_raw = None if info_origin is None else _origin_data(state, info_origin, "info")[2]
    info_payload = None if info_raw is None else plistlib.loads(info_raw)
    mismatch, attach, selected, matching = set(), None, None, []
    try: attach = _entities(attach_payload)
    except IsolatedVolumeRefusal: mismatch.add("system-entities")
    valid_images = (type(info_payload) is dict and type(info_payload.get("images")) is list
        and len(info_payload["images"]) <= MAXIMUM_IMAGES)
    if valid_images:
        matching = [item for item in info_payload["images"] if type(item) is dict
            and item.get("image-path") == str(state["image"])]
        if len(matching) == 1:
            try: selected = _entities(matching[0])
            except IsolatedVolumeRefusal: mismatch.add("system-entities")
            if any(key in matching[0] for key in ("shadow-path", "shadow-file")): mismatch.add("shadow")
        else: mismatch.add("image-path")
    elif info_origin is not None: mismatch.add("images")
    attached_mounts = () if attach is None else tuple(row for row in attach if row[3] is not None)
    info_mounts = () if selected is None else tuple(row for row in selected if row[3] is not None)
    one_each = len(attached_mounts) == len(info_mounts) == 1
    if one_each:
        for index, name in enumerate(("dev-entry", "content-hint", "volume-kind", "mount-point")):
            if attached_mounts[0][index] != info_mounts[0][index]: mismatch.add(name)
    report = {"schema": "si-isolated-association-diagnostic-v1", "status": "original_origins_observed",
        "attach_raw_sha256": hash_bytes(attach_raw),
        "info_raw_sha256": None if info_raw is None else hash_bytes(info_raw),
        "attach_parsed_sha256": None if attach is None else hash_payload(attach),
        "info_parsed_sha256": None if selected is None else hash_payload(selected),
        "attach_entity_count": None if attach is None else len(attach),
        "info_entity_count": None if selected is None else len(selected),
        "matching_image_count": len(matching) if valid_images else None,
        "original_shapes_valid": attach is not None and selected is not None,
        "attach_devices_subset": attach is not None and selected is not None
            and {row[0] for row in attach} <= {row[0] for row in selected},
        "unique_mounted_origins": one_each,
        "mounted_devices_equal": one_each and attached_mounts[0][0] == info_mounts[0][0],
        "mount_points_equal": one_each and attached_mounts[0][3] == info_mounts[0][3],
        "fixed_mount_matches": one_each and attached_mounts[0][3] == info_mounts[0][3] == str(state["mount"]),
        "vendor_text_equal": one_each and attached_mounts[0][1:3] == info_mounts[0][1:3],
        "mismatching_field_names": sorted(mismatch), "authority": authority()}
    token = object(); _ASSOCIATION_ISSUED[token] = token, canonical_json(report).encode()
    _LAST_ASSOCIATION = token


def _entities(value):
    require(type(value) is dict and type(value.get("system-entities")) is list
        and 1 <= len(value["system-entities"]) <= MAXIMUM_ENTITIES, "isolated_attach_association_refused")
    result = []
    for item in value["system-entities"]:
        require(type(item) is dict and type(item.get("dev-entry")) is str
            and re.fullmatch(r"/dev/disk[0-9]+(?:s[0-9]+)*", item["dev-entry"]),
            "isolated_attach_association_refused")
        row = tuple(item.get(key) for key in ("dev-entry", "content-hint", "volume-kind", "mount-point"))
        require(all(part is None or (type(part) is str and 0 < len(part) <= 1024 and "\0" not in part)
            for part in row), "isolated_attach_association_refused")
        result.append(row)
    require(len({row[0] for row in result}) == len(result), "isolated_attach_association_refused")
    return tuple(sorted(result, key=lambda row: row[0]))


def _selected_image(state, *, absent=False):
    payload = _run(state, "info")
    if "attach_origin" in state and "info_origin" not in state:
        _issue_association(state, state["last_origin"])
    require(type(payload) is dict and type(payload.get("images")) is list
        and len(payload["images"]) <= MAXIMUM_IMAGES, "isolated_image_association_refused")
    matching = []
    for image in payload["images"]:
        require(type(image) is dict and type(image.get("image-path")) is str
            and 0 < len(image["image-path"]) <= 4096 and "\0" not in image["image-path"],
            "isolated_image_association_refused")
        if image["image-path"] == str(state["image"]): matching.append(image)
    require(len(matching) == (0 if absent else 1), "isolated_image_association_refused")
    if absent: return None
    image = matching[0]
    # Any alternate writable overlay would invalidate backing-image attribution.
    require(not any(key in image for key in ("shadow-path", "shadow-file")), "isolated_image_association_refused")
    identity = hash_bytes(plistlib.dumps(image, fmt=plistlib.FMT_BINARY, sort_keys=True))
    if "selected_info_identity" in state:
        require(identity == state["selected_info_identity"], "isolated_image_association_refused")
    state["last_selected_info_identity"] = identity
    return _entities(image)


def _mounted_descriptor(row):
    hint, kind = row[1:3]
    known = hint is None or hint in {"Apple_APFS", "Apple_APFS_Volume"}
    if type(hint) is str and re.fullmatch(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", hint):
        known = hint.upper() in {"41504653-0000-11AA-AA11-00306543ECAC", "7C3457EF-0000-11AA-AA11-00306543ECAC"}
    require(known and kind in (None, "apfs"), "isolated_descriptor_refused")


def _device_node_stat(device):
    """Metadata only. NEVER open or read a block device."""
    require(type(device) is str and re.fullmatch(r"/dev/disk[0-9]+(?:s[0-9]+)*", device),
        "isolated_device_node_refused")
    return Path(device).lstat()


def _node_pin(device, mount_device):
    info = _device_node_stat(device)
    values = info.st_dev, info.st_ino, info.st_rdev, info.st_mode, info.st_uid, info.st_gid
    require(stat.S_ISBLK(info.st_mode) and all(type(value) is int and value >= 0 for value in values)
        and info.st_rdev == mount_device, "isolated_device_node_refused")
    return values


def _native_contract(state, native):
    require(native["fstype"] == "apfs", "isolated_mount_not_apfs")
    require(native["owner"] == os.getuid(), "isolated_mount_owner_refused")
    require(native["flags"] & MNT_LOCAL, "isolated_mount_not_local")
    require(native["flags"] & MNT_DONTBROWSE, "isolated_mount_browse_refused")
    require(not native["flags"] & MNT_IGNORE_OWNERSHIP, "isolated_mount_ownership_ignored")
    require(not native["flags"] & MNT_RDONLY, "isolated_mount_readonly")
    require(native["mounted_on"] == str(state["mount"]), "isolated_mount_name_changed")
    require(native["mounted_from"] == state["device"], "isolated_mount_device_changed")
    require(_mount_identity(native) == state["mount_native"], "isolated_mount_native_identity_changed")


def _fresh_root_identity(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) in (0o700, 0o755), "isolated_new_root_mode_refused")
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid


def _root_enforcement_record(state):
    row = _ROOT_ENFORCEMENTS.get(id(state))
    require(type(row) is tuple and len(row) == 3 and row[0] is state
        and row[1] == state["mount_fd"] and row[2] == state["root_creation_pin"][:4],
        "isolated_new_root_identity_changed")
    return row[1], row[2]


def _enforce_new_root(state, fd):
    # This is construction of THIS invocation's fresh mounted root, never a
    # permission correction of an old image, failed proof, source or claim.
    require(id(state) not in _ROOT_ENFORCEMENTS, "isolated_new_root_enforcement_repeated")
    before, named = os.fstat(fd), state["mount"].lstat()
    original = _fresh_root_identity(before)
    require(_fresh_root_identity(named) == original and before.st_dev != state["host_device"]
        and state["mount"].resolve() == state["mount"], "isolated_new_root_identity_changed")
    native = _native_statfs(fd); _native_contract(state, native)
    node = _node_pin(state["device"], before.st_dev)
    _check_parents(state)
    require(_selected_image(state) == state["info_entities"], "isolated_image_association_refused")
    require(_fresh_root_identity(os.fstat(fd)) == _fresh_root_identity(state["mount"].lstat()) == original,
        "isolated_new_root_identity_changed")
    _native_contract(state, _native_statfs(fd))
    require(_node_pin(state["device"], before.st_dev) == node, "isolated_device_node_changed")
    # Exactly ONE real original-FD mode operation, before the caller receives
    # a capability or can create even the synthetic probe on the mounted FS.
    _ROOT_ENFORCEMENTS[id(state)] = state, fd, original
    os.fchmod(fd, 0o700); os.fsync(fd)
    require(_directory(os.fstat(fd)) == _directory(state["mount"].lstat())
        and _fresh_root_identity(os.fstat(fd)) == original, "isolated_new_root_identity_changed")
    require(_mount_identity(_native_statfs(fd)) == _mount_identity(native),
        "isolated_mount_native_identity_changed")
    require(_node_pin(state["device"], before.st_dev) == node, "isolated_device_node_changed")
    state.update(device_node_pin=node, root_creation_pin=(*original, stat.S_IMODE(before.st_mode)),
        root_mode_enforced=True, mount_pin=_directory(os.fstat(fd)))


def _check_parents(state):
    _boundary(state)
    require(Path.cwd().resolve() == ROOT and ROOT.resolve() == ROOT, "isolated_root_changed")
    for path, fd, pin in state["directories"]:
        require(path.resolve() == path and _directory(path.lstat()) == _directory(os.fstat(fd)) == pin,
            "isolated_directory_changed")
    require(tuple(sorted(os.listdir(state["namespace_fd"]))) == (IMAGE_NAME, MOUNT_NAME),
        "isolated_namespace_changed")
    named = os.stat(IMAGE_NAME, dir_fd=state["namespace_fd"], follow_symlinks=False)
    require(_backing(named) == _backing(os.fstat(state["backing_fd"])) == state["backing_pin"],
        "isolated_backing_changed")
    require(_directory(os.fstat(state["under_mount_fd"])) == state["under_mount_pin"],
        "isolated_directory_changed")


def _check_mount(state, fd, *, info=False):
    native = _native_statfs(fd)
    named = state["mount"].lstat()
    require(state["mount"].resolve() == state["mount"] and _directory(named)
        == _directory(os.fstat(fd)) == state["mount_pin"]
        and named.st_dev != state["host_device"], "isolated_mount_association_refused")
    require(_fresh_root_identity(os.fstat(fd)) == _fresh_root_identity(named)
        == state["root_creation_pin"][:4], "isolated_new_root_identity_changed")
    _native_contract(state, native)
    require(_node_pin(state["device"], named.st_dev) == state["device_node_pin"], "isolated_device_node_changed")
    if info:
        require(_selected_image(state) == state["info_entities"], "isolated_image_association_refused")
    _boundary(state)


def _readonly_original_check(state):
    """Reopen only against original pins, never install a new baseline."""
    _original_state(state)
    descriptors = []
    try:
        for path, unused, pin in state["directories"]:
            require(path.resolve() == path and _directory(path.lstat()) == pin, "isolated_directory_changed")
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); descriptors.append(fd)
            require(_directory(os.fstat(fd)) == pin, "isolated_directory_changed")
        namespace_fd = descriptors[-1]
        require(tuple(sorted(os.listdir(namespace_fd))) == (IMAGE_NAME, MOUNT_NAME), "isolated_namespace_changed")
        fd = os.open(IMAGE_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=namespace_fd)
        descriptors.append(fd)
        require(_backing(os.fstat(fd)) == _backing(os.stat(IMAGE_NAME, dir_fd=namespace_fd,
            follow_symlinks=False)) == state["backing_pin"], "isolated_backing_changed")
        mount_fd = os.open(MOUNT_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=namespace_fd)
        descriptors.append(mount_fd); _check_mount(state, mount_fd, info=True)
        for path, unused, pin in state["directories"]:
            require(_directory(path.lstat()) == pin, "isolated_directory_changed")
        require(_backing(os.stat(IMAGE_NAME, dir_fd=namespace_fd, follow_symlinks=False))
            == state["backing_pin"], "isolated_backing_changed")
        _boundary(state)
    finally:
        for descriptor in reversed(descriptors): os.close(descriptor)


class IsolatedCustodyVolume:
    __slots__ = ("_anchor", "_identity")

    def __init__(self): raise IsolatedVolumeRefusal("isolated_factory_required")
    def __repr__(self): return "<IsolatedCustodyVolume redacted>"

    def _binding(self):
        entry = _MINTED.get(id(self)) if type(self) is IsolatedCustodyVolume else None
        try: anchor, identity = self._anchor, self._identity
        except AttributeError: anchor, identity = None, None
        require(type(entry) is tuple and len(entry) == 3 and entry[0] is self
            and entry[1] is anchor is identity and type(anchor) is tuple and len(anchor) == 1,
            "isolated_capability_changed")
        require(id(self) not in _FAILED, "isolated_failure_latched")
        _original_state(entry[2])
        return entry[2]

    def _guarded(self, action):
        try: return action(self._binding())
        except BaseException:
            if _MINTED.get(id(self), (None,))[0] is self: _FAILED.add(id(self))
            raise

    @property
    def mountpoint(self):
        self.check(); return self._binding()["mount"]

    def check(self):
        def check(state):
            require(state["phase"] == "LIVE", "isolated_not_live")
            _check_parents(state); _check_mount(state, state["mount_fd"])
        return self._guarded(check)

    def observation(self):
        def report(state):
            require(state["phase"] == "LIVE", "isolated_not_live"); self.check()
            return _summary(state, "live_provisional_synthetic_volume")
        return self._guarded(report)

    def check_after_close(self):
        def check(state):
            require(state["phase"] == "CLOSED" and id(self) in _ISSUED, "isolated_not_closed")
            _readonly_original_check(state)
        return self._guarded(check)

    def closed_summary(self):
        def report(state):
            issued = _ISSUED.get(id(self))
            require(state["phase"] == "CLOSED" and type(issued) is tuple and len(issued) == 3
                and issued[0] is self and issued[1] is self._anchor, "isolated_not_closed")
            self.check_after_close(); return json.loads(issued[2])
        return self._guarded(report)


def _summary(state, status):
    _original_state(state)
    original = _COMMANDS.get(id(state))
    require(type(original) is tuple and len(original) == 2 and original[0] is state
        and tuple(state["commands"]) == original[1], "isolated_capability_changed")
    return {"schema": "si-isolated-custody-volume-observation-v6", "status": status,
        "policy_sha256": state["policy"], "virtual_bytes": VIRTUAL_BYTES,
        "filesystem_APFS": True, "owners_honored": True, "local_filesystem": True,
        "nobrowse": True, "separate_host_device": True, "root_protection_verified": True,
        "backing_identity_sha256": hash_payload(state["backing_pin"]),
        "mount_identity_sha256": hash_payload(state["mount_pin"]),
        "filesystem_identity_sha256": hash_payload(state["mount_native"]),
        "attach_entities_sha256": hash_payload(state["attach_entities"]),
        "info_entities_sha256": hash_payload(state["info_entities"]),
        "attach_original_raw_sha256": _origin_pin(state, state["attach_origin"], "attach")[1],
        "info_original_raw_sha256": _origin_pin(state, state["info_origin"], "info")[1],
        "selected_info_original_identity_sha256": state["selected_info_identity"],
        "device_node_original_identity_sha256": hash_payload(state["device_node_pin"]),
        "root_creation_identity_sha256": hash_payload(state["root_creation_pin"]),
        "root_mode_enforced_before_probe": state["root_mode_enforced"],
        "commands": list(state["commands"]), "container_is_immutable_evidence": False,
        "authority": authority()}


@contextmanager
def prepare_registered_volume(root, *, boundary, monotonic=time.monotonic):
    """Create/attach once; preserve all artifacts and mount on every outcome.

    The caller nests all code and inner-file contexts inside this context.
    Neither context exit nor any failure detaches, clears flags or removes data.
    """
    global _USED, _LAST_ASSOCIATION
    _platform(); require(type(root) is type(ROOT) and root == ROOT and root.is_absolute()
        and root.resolve() == root and Path.cwd().resolve() == root, "isolated_root_changed")
    require(callable(boundary) and callable(monotonic), "isolated_capability_changed")
    require(not _USED, "isolated_already_used"); _USED = True
    _LAST_ASSOCIATION = None
    begin = monotonic()
    require(type(begin) in (int, float) and not isinstance(begin, bool) and math.isfinite(begin),
        "isolated_clock_refused")
    parent, namespace = root / PARENT, root / PARENT / NAMESPACE
    state = {"begin": begin, "last": begin, "monotonic": monotonic, "boundary": boundary,
        "policy": hash_payload(policy()), "image": namespace / IMAGE_NAME, "mount": namespace / MOUNT_NAME,
        "commands": [], "directories": [], "phase": "CREATING"}
    _CLOCKS[id(state)] = state, begin, begin, monotonic, boundary
    _COMMANDS[id(state)] = state, ()
    descriptors, capability = [], None
    try:
        _boundary(state)
        require(parent.resolve() == parent, "isolated_root_changed")
        parent_pin = _directory(parent.lstat())
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); descriptors.append(parent_fd)
        require(_directory(os.fstat(parent_fd)) == parent_pin, "isolated_directory_changed")
        host = _native_statfs(parent_fd)
        require(host["flags"] & MNT_LOCAL and not host["flags"] & MNT_IGNORE_OWNERSHIP,
            "isolated_parent_filesystem_refused")
        require(type(host["bsize"]) is int and host["bsize"] > 0 and type(host["bavail"]) is int
            and host["bavail"] * host["bsize"] >= VIRTUAL_BYTES + 1024 ** 3,
            "isolated_host_capacity_refused")
        try: os.stat(NAMESPACE, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise IsolatedVolumeRefusal("isolated_namespace_exists")
        os.mkdir(NAMESPACE, 0o700, dir_fd=parent_fd)
        namespace_fd = os.open(NAMESPACE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        descriptors.append(namespace_fd); os.fchmod(namespace_fd, 0o700)
        namespace_pin = _directory(os.fstat(namespace_fd))
        require(_directory(namespace.lstat()) == namespace_pin and not os.listdir(namespace_fd),
            "isolated_namespace_changed")
        state.update(namespace_fd=namespace_fd, host_device=parent_pin[0],
            directories=[(parent, parent_fd, parent_pin), (namespace, namespace_fd, namespace_pin)])
        _selected_image(state, absent=True)
        _run(state, "create")
        require(tuple(os.listdir(namespace_fd)) == (IMAGE_NAME,), "isolated_namespace_changed")
        backing_fd = os.open(IMAGE_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=namespace_fd)
        descriptors.append(backing_fd)
        original_backing = os.fstat(backing_fd)
        require(stat.S_ISREG(original_backing.st_mode) and original_backing.st_uid == os.getuid()
            and original_backing.st_nlink == 1, "isolated_backing_protection")
        # Permission correction belongs only to this successful fresh creation.
        os.fchmod(backing_fd, 0o600)
        state.update(backing_fd=backing_fd, backing_pin=_backing(os.fstat(backing_fd)))
        require(_backing(os.stat(IMAGE_NAME, dir_fd=namespace_fd, follow_symlinks=False))
            == state["backing_pin"], "isolated_backing_changed")
        os.mkdir(MOUNT_NAME, 0o700, dir_fd=namespace_fd)
        under_fd = os.open(MOUNT_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=namespace_fd)
        descriptors.append(under_fd); os.fchmod(under_fd, 0o700)
        state.update(under_mount_fd=under_fd, under_mount_pin=_directory(os.fstat(under_fd)))
        require(not os.listdir(under_fd), "isolated_mount_preexists")
        _check_parents(state); _selected_image(state, absent=True)
        attached_payload = _run(state, "attach")
        state["attach_origin"] = state["last_origin"]
        _issue_association(state)
        attached = _entities(attached_payload)
        mounted = tuple(row for row in attached if row[3] is not None)
        require(len(mounted) == 1 and mounted[0][3] == str(state["mount"]),
            "isolated_attach_association_refused")
        state.update(device=mounted[0][0], attach_entities=attached)
        info_entities = _selected_image(state)
        state.update(info_origin=state["last_origin"], selected_info_identity=state["last_selected_info_identity"])
        info_mounted = tuple(row for row in info_entities if row[3] is not None)
        require({row[0] for row in attached} <= {row[0] for row in info_entities}
            and len(info_mounted) == 1 and info_mounted[0][0] == mounted[0][0]
            and info_mounted[0][3] == mounted[0][3],
            "isolated_image_association_refused")
        _mounted_descriptor(mounted[0]); _mounted_descriptor(info_mounted[0])
        require(_entities(plistlib.loads(_origin_data(state, state["attach_origin"], "attach")[2])) == attached,
            "isolated_origin_refused")
        mount_fd = os.open(MOUNT_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=namespace_fd)
        descriptors.append(mount_fd)
        native = _native_statfs(mount_fd)
        require(type(native["bsize"]) is int and native["bsize"] > 0 and type(native["blocks"]) is int
            and 4 * 1024 ** 3 <= native["blocks"] * native["bsize"] <= VIRTUAL_BYTES
            and type(native["bavail"]) is int and native["bavail"] * native["bsize"] >= 4 * 1024 ** 3,
            "isolated_mount_capacity_refused")
        state.update(mount_fd=mount_fd, mount_native=_mount_identity(native), info_entities=info_entities)
        _enforce_new_root(state, mount_fd)
        _check_parents(state); _check_mount(state, mount_fd)
        _FROZEN[id(state)] = state, hash_payload(_fixed_state(state))
        capability = object.__new__(IsolatedCustodyVolume); anchor = (object(),)
        capability._anchor = capability._identity = anchor
        _MINTED[id(capability)] = capability, anchor, state
        state["phase"] = "LIVE"; capability.check()
        yield capability
        capability.check(); _check_mount(state, mount_fd, info=True)
        state["phase"] = "CLOSING"
        closing = list(reversed(descriptors)); descriptors.clear()
        close_failed = False
        for fd in closing:
            try: os.close(fd)
            except OSError: close_failed = True
        require(not close_failed, "isolated_close_failed")
        _readonly_original_check(state)
        require(id(capability) not in _FAILED and state["phase"] == "CLOSING", "isolated_phase_changed")
        state["phase"] = "CLOSED"
        raw = canonical_json(_summary(state, "closed_synthetic_isolated_volume_only")).encode()
        _ISSUED[id(capability)] = capability, anchor, raw
    except BaseException:
        state["phase"] = "REFUSED"
        if capability is not None: _FAILED.add(id(capability)); _ISSUED.pop(id(capability), None)
        raise
    finally:
        close_failed = False
        for descriptor in reversed(descriptors):
            try: os.close(descriptor)
            except OSError: close_failed = True
        if close_failed:
            if capability is not None: _FAILED.add(id(capability)); _ISSUED.pop(id(capability), None)
            raise IsolatedVolumeRefusal("isolated_close_failed")
