"""Fixed private data custody, separate from the unchanged repository identity.

No provider or credential operation occurs here. Old failed claims are read-only
transition evidence; an authenticated snapshot never promotes their candidates.
The new receiver still binds content, identity and every version field, including
ctime. A stable directory must be qualified prospectively before provider use.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from research import insider_buying_pilot_firstrate_qualification_v1 as source
from research import insider_buying_pilot_publication_seal_v1 as seal

native, custody = source.native, source.native.custody
LANE_ROOT, LANE_BRANCH = native.LANE_ROOT, native.LANE_BRANCH
SELF_PATH = "research/insider_buying_pilot_stable_custody_v2.py"
TEST_PATH = "tests/test_insider_buying_pilot_stable_custody_v2.py"
PRIVATE_CUSTODY_ROOT = Path("/Users/sheltonchen/Library/Application Support/trading_agent/insider_buying/custody")
DATA_ROOT = PRIVATE_CUSTODY_ROOT
_HOME = Path("/Users/sheltonchen")
_MANAGED_PARTS = ("Library", "Application Support", "trading_agent", "insider_buying", "custody")
SCHEMA = "insider-pilot-stable-private-custody-v2"
MAX_BYTES, MAX_LEAVES, MAX_EPOCH_BYTES = 2 * 1024 * 1024, 128, 16 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z0-9][a-z0-9.-]{0,99}\Z")
_AUDIT = re.compile(r"[a-z0-9][a-z0-9-]{0,95}\Z")
_ACTUAL = object()
_CODES = frozenset({"arguments_refused", "native_refused", "identity_refused", "namespace_consumed",
    "custody_refused", "output_changed", "publication_refused", "snapshot_refused", "cleanup_refused", "seal_refused"})
_ROLES = frozenset({"arguments", "native", "identity", "storage_root", "epoch", "reservation", "snapshot",
    "source_metadata", "source_bodies", "controls", "request_plan", "credential_started", "credential_completed",
    "request_started", "request_completed", "complete", "failure", "leaf", "cleanup", "storage_qualification",
    "input_bindings", "synthetic"})
_FIELDS = ("device", "inode", "mode", "links", "size", "mtime", "ctime")
_DIFF_FIELDS = frozenset((*_FIELDS, "owner", "group", "content", "inventory", "type", "identity", "flags"))

LEGACY_ROOT = LANE_ROOT / "artifacts" / "insider_buying" / "pilot_fmp_eod_qualification_v1"
LEGACY_AUDIT = "ib-fmp-eod-retained-control-qualification-20261103-once-v1"
LEGACY_SECOND = LEGACY_AUDIT + "-preinput-continuation-2"
LEGACY_THIRD = LEGACY_AUDIT + "-publication-corrected-3"
LEGACY_HEADS = (
    "650cd9ba4569f6ef059246944a62fcd107d0de29",
    "743aea5a6555a1a4c062f16e485751b7f6a7b6b1",
    "d7b6c3cfba751c17b63c477a998bfa7f0b9ff699",
)
SNAPSHOT_PINS = {
    "scope-reservation.json": {"bytes": 20994, "sha256": "faef6d685ed93f9d225abe94c9377df93bd3c0031547d46335c05ddfeef7b299"},
    "scope-continuation-2.json": {"bytes": 21397, "sha256": "778467039348084e28bc9495c56af7c23da861890494b7e4ce34e70d9f11fefe"},
    "scope-publication-corrected-3.json": {"bytes": 21989, "sha256": "dc641f994605e258efc54210dcacf5866e0521c798e99ba70dd760dcb5ecfb3e"},
    LEGACY_THIRD + "/controls-metadata-started.json": {"bytes": 24, "sha256": "4555edb83c54af4c261f82425dea483184c020b64be91cb7531774c4e2872b69"},
    LEGACY_THIRD + "/controls-metadata.json": {"bytes": 26001, "sha256": "bb64d96721f2eb0657dd47c27a58684fc5634bb2d1151a2614f610c1d27a4749"},
    LEGACY_THIRD + "/controls-bodies-started.json": {"bytes": 109, "sha256": "66c465b432534b2be9471cea6a3b9119e0d8d04d9a20462683ea280cecd6249e"},
    LEGACY_THIRD + "/controls.json": {"bytes": 18297, "sha256": "c48c892c83ac241246663cbeb2e5c68199342e4063899a22c50cbe2b9f69b658"},
}
_TOP_NAMES = frozenset({*list(SNAPSHOT_PINS)[:3], LEGACY_AUDIT, LEGACY_SECOND, LEGACY_THIRD})
_THIRD_NAMES = frozenset(p.split("/", 1)[1] for p in SNAPSHOT_PINS if "/" in p)


class CustodyError(ValueError):
    """Finite code/role/field names only; no foreign values or paths."""
    def __init__(self, code, role="leaf", changed_fields=()):
        self.code = code if type(code) is str and code in _CODES else "custody_refused"
        self.role = role if type(role) is str and role in _ROLES else "leaf"
        selected = changed_fields if type(changed_fields) in {tuple, list, set, frozenset} else ()
        self.changed_fields = tuple(sorted({v for v in selected if type(v) is str} & _DIFF_FIELDS))
        super().__init__(self.code)


def safe_failure(error):
    if type(error) is CustodyError:
        return {"code": error.code, "role": error.role, "changed_fields": list(error.changed_fields)}
    return {"code": "custody_refused", "role": "leaf", "changed_fields": []}


def _need(ok, code="custody_refused", role="leaf", fields=()):
    if not ok:
        raise CustodyError(code, role, fields)


def _role(name):
    if name == "reservation.json": return "reservation"
    if name == "request-plan.json": return "request_plan"
    if name == "controls.json": return "controls"
    if name.startswith("controls-metadata"): return "source_metadata"
    if name.startswith("controls-bodies"): return "source_bodies"
    if name in {"complete.json", "failure.json"}: return name[:-5]
    if name in {"snapshot.json", "failed-predecessor-snapshot.json"}: return "snapshot"
    if name == "storage-qualification.json": return "storage_qualification"
    if name == "input-bindings.json": return "input_bindings"
    if re.fullmatch(r"synthetic-[0-9]{3}\.json", name): return "synthetic"
    for provider in ("fmp", "eodhd"):
        for suffix in ("started", "completed"):
            if name == f"{provider}-credential-{suffix}.json": return "credential_" + suffix
    for suffix in ("started", "completed"):
        if re.fullmatch(r"request-[0-9]{3}-" + suffix + r"\.json", name): return "request_" + suffix
    return "leaf"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _raw(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise CustodyError("arguments_refused", "arguments") from None
    _need(0 < len(raw) <= MAX_BYTES, "arguments_refused", "arguments")
    return raw


def _decode(raw):
    def pairs(items):
        value = {}
        for key, child in items:
            _need(key not in value, "custody_refused")
            value[key] = child
        return value
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: _need(False, "custody_refused"))
        _need(_raw(value) == raw, "custody_refused")
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise CustodyError("custody_refused") from None


def _copy(value):
    return _decode(_raw(value))


def _private_directory(chain, role="epoch"):
    chain.recheck(); info = os.fstat(chain.fd)
    _need(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
        and info.st_uid == os.geteuid(), "custody_refused", role)


def _managed(chain):
    chain.recheck()
    app = os.fstat(chain.links[-3][2])
    _need(stat.S_ISDIR(app.st_mode) and app.st_uid == os.geteuid()
        and not stat.S_IMODE(app.st_mode) & 0o022, "custody_refused", "storage_root")
    for _, _, child, _ in chain.links[-2:]:
        info = os.fstat(child)
        _need(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
            and info.st_uid == os.geteuid(), "custody_refused", "storage_root")
    _private_directory(chain, "storage_root")


def _storage_identity(chain, *, fixture):
    _private_directory(chain, "storage_root"); info = os.fstat(chain.fd)
    return {"schema": SCHEMA + "/storage-identity", "root_kind": "invented_fixture" if fixture else "fixed_user_application_support",
        "device": info.st_dev, "inode": info.st_ino, "mode": stat.S_IMODE(info.st_mode),
        "owner": info.st_uid, "group": info.st_gid}


def _close_chains(chains, *, primary=False):
    failed = False
    for chain in reversed(tuple(chains)):
        if chain is None: continue
        for fd in reversed(tuple(chain.fds)):
            try: os.close(fd)
            except OSError: failed = True
        chain.fds = []
    _need(primary or not failed, "cleanup_refused", "cleanup")


class _HeldChain(custody._Chain):
    """Keep the qualified ancestry checks, exhaust cleanup on constructor error."""
    def close(self):
        _close_chains((self,), primary=sys.exc_info()[0] is not None)


def prepare_actual_root():
    """Create only fixed data directories; preserve existing ancestor modes."""
    chains = []
    try:
        base = _HeldChain(_HOME, _MANAGED_PARTS[:2]); chains.append(base)
        for _, _, fd, _ in base.links[-3:]:
            info = os.fstat(fd)
            _need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and not stat.S_IMODE(info.st_mode) & 0o022, "custody_refused", "storage_root")
        parent = base
        for count in (3, 4, 5):
            parent.recheck(); name = _MANAGED_PARTS[count-1]
            try: os.mkdir(name, 0o700, dir_fd=parent.fd); os.fsync(parent.fd)
            except FileExistsError: pass
            info = os.stat(name, dir_fd=parent.fd, follow_symlinks=False)
            _need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and (stat.S_IMODE(info.st_mode) == 0o700 if count >= 4 else not stat.S_IMODE(info.st_mode) & 0o022),
                "custody_refused", "storage_root")
            current = _HeldChain(_HOME, _MANAGED_PARTS[:count]); chains.append(current)
            parent.recheck(); parent = current
        _managed(parent)
        return PRIVATE_CUSTODY_ROOT
    except CustodyError: raise
    except (OSError, ValueError):
        raise CustodyError("custody_refused", "storage_root") from None
    finally:
        _close_chains(chains, primary=sys.exc_info()[0] is not None)


def production_parent_current(identity):
    """Parent-only live Git read without an optional index-refresh write."""
    from research import insider_buying_pilot_fmp_eod_qualification_v1 as legacy
    try:
        legacy._current(identity)
        _need(Path.cwd() == LANE_ROOT, "identity_refused", "identity")
        lines = custody._git(LANE_ROOT, "--no-optional-locks", "status", "--porcelain=v2", "--branch",
            "--untracked-files=all").decode("utf-8").splitlines()
        _need("# branch.oid " + identity["head"] in lines
            and "# branch.head " + LANE_BRANCH in lines
            and all(line.startswith("# ") for line in lines), "identity_refused", "identity")
    except CustodyError: raise
    except Exception:
        raise CustodyError("identity_refused", "identity") from None


def _fixture_root(root):
    _need(type(root) is str or isinstance(root, Path), "arguments_refused", "arguments")
    p = Path(root)
    _need(p.is_absolute() and ".." not in p.parts
        and not p.is_relative_to(LANE_ROOT) and not p.is_relative_to(PRIVATE_CUSTODY_ROOT)
        and not p.is_relative_to(LANE_ROOT.parent / "insider_buying_sec_complete_16_9ab2ed0")
        and not p.is_relative_to(Path("/Volumes"))
        and not p.is_relative_to(_HOME / "Library" / "Keychains"), "arguments_refused", "arguments")
    try: _need(p.resolve() == p, "arguments_refused", "arguments")
    except (OSError, ValueError): raise CustodyError("arguments_refused", "arguments") from None
    return p


def _private_leaf(info, role):
    fields = []
    if not stat.S_ISREG(info.st_mode): fields.append("type")
    if stat.S_IMODE(info.st_mode) != 0o600: fields.append("mode")
    if info.st_uid != os.geteuid(): fields.append("owner")
    if info.st_nlink != 1: fields.append("links")
    if not 0 < info.st_size <= MAX_BYTES: fields.append("size")
    _need(not fields, "custody_refused", role, fields)


def _different(expected, observed):
    return tuple(name for name, a, b in zip(_FIELDS, expected, observed) if a != b)


def _read_leaf(fd, name, pin=None):
    """Reject a replaced/privacy-invalid leaf before reading or hashing it."""
    role = _role(name); leaf = None
    try:
        before = os.stat(name, dir_fd=fd, follow_symlinks=False); _private_leaf(before, role)
        version = custody._version(before)
        if pin is not None:
            _need(type(pin) is dict and {"bytes", "sha256"} <= set(pin) <= {"bytes", "sha256", "version"}
                and (pin["bytes"] is None or type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_BYTES)
                and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"]), "arguments_refused", role)
            _need(pin["bytes"] is None or before.st_size == pin["bytes"], "output_changed", role, ("size",))
        if pin is not None and "version" in pin:
            _need(version == pin["version"], "output_changed", role, _different(pin["version"], version))
        leaf = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        opened = os.fstat(leaf); _private_leaf(opened, role)
        _need(custody._version(opened) == version and opened.st_uid == before.st_uid
            and opened.st_gid == before.st_gid, "output_changed", role,
            (*_different(version, custody._version(opened)), "identity"))
        raw = os.pread(leaf, MAX_BYTES + 1, 0)
        after = os.fstat(leaf); named = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _private_leaf(after, role); _private_leaf(named, role)
        _need(custody._version(after) == version == custody._version(named)
            and after.st_uid == named.st_uid == before.st_uid and after.st_gid == named.st_gid == before.st_gid,
            "output_changed", role, (*_different(version, custody._version(after)),
            *_different(version, custody._version(named)), "identity"))
        _need(len(raw) == before.st_size, "output_changed", role, ("size",))
        digest = _sha(raw)
        if pin is not None:
            _need((pin["bytes"] is None or len(raw) == pin["bytes"]) and digest == pin["sha256"],
                "output_changed", role, ("content",))
        result = {"bytes": len(raw), "sha256": digest, "version": version}
    except CustodyError: raise
    except (OSError, ValueError, TypeError):
        raise CustodyError("custody_refused", role) from None
    finally:
        primary = sys.exc_info()[0] is not None
        if leaf is not None:
            try: os.close(leaf)
            except OSError:
                if not primary: raise CustodyError("cleanup_refused", role) from None
    # The close itself is inside our observation interval.
    try: final = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except OSError: raise CustodyError("custody_refused", role) from None
    _private_leaf(final, role)
    _need(custody._version(final) == version, "output_changed", role, _different(version, custody._version(final)))
    return raw, result


def _pin_copy(pin):
    return {"bytes": pin["bytes"], "sha256": pin["sha256"], "version": tuple(pin["version"])}


class Epoch:
    def __init__(self, identity, registration, *, fixture=False, fixture_root=None, checker=None):
        _need(type(fixture) is bool and type(identity) is dict and type(registration) is dict,
            "arguments_refused", "arguments")
        _need(type(registration.get("audit_id")) is str and _AUDIT.fullmatch(registration["audit_id"]),
            "arguments_refused", "arguments")
        _need((fixture and fixture_root is not None and callable(checker))
            or (not fixture and fixture_root is None and checker is None), "arguments_refused", "arguments")
        self.root, self.fixture = LANE_ROOT, fixture
        self.storage_root = _fixture_root(fixture_root) if fixture else PRIVATE_CUSTODY_ROOT
        self._storage_bound, self._fixture_bound = self.storage_root, fixture
        self.identity, self.registration = _copy(identity), _copy(registration)
        self._identity_raw, self._registration_raw = _raw(self.identity), _raw(self.registration)
        self.audit_id = self.registration["audit_id"]
        self._audit_bound = self.audit_id
        self.active, self.dispatched = None, set()
        self._permission = None if fixture else _ACTUAL
        self._checker = checker if fixture else lambda: production_parent_current(self.identity)
        self.parent = self.directory = None; self._pins = {}; self._latch = None
        try:
            self._checker()
            self.parent = _HeldChain(self.storage_root, ())
            if fixture: _private_directory(self.parent, "storage_root")
            else: _managed(self.parent)
            self._storage_identity_bound = _storage_identity(self.parent, fixture=fixture)
            _need(self.audit_id not in os.listdir(self.parent.fd), "namespace_consumed", "epoch")
            self.directory = _HeldChain(self.storage_root, (self.audit_id,), create=True, exclusive_last=True)
            _private_directory(self.directory)
            reservation = {"schema": SCHEMA + "/reservation", "code_identity": self.identity,
                "registration": self.registration, "fixture_only": fixture,
                "storage": {"root_kind": "invented_fixture" if fixture else "fixed_user_application_support",
                    "policy": SCHEMA, "audit_id": self.audit_id, "identity": self._storage_identity_bound}}
            self._latch = self._write("reservation.json", _raw(reservation))
            self._pins["reservation.json"] = self._latch
            self.check()
        except BaseException as error:
            self.close()
            if isinstance(error, Exception) and type(error) is not CustodyError:
                raise CustodyError("custody_refused", "epoch") from None
            raise

    @property
    def pins(self):
        return {name: _pin_copy(pin) for name, pin in self._pins.items()}

    @property
    def latch(self):
        return _pin_copy(self._latch) if self._latch is not None else None

    @property
    def storage_identity(self):
        try:
            current = _storage_identity(self.parent, fixture=self.fixture)
            _need(current == self._storage_identity_bound, "identity_refused", "storage_root", ("identity",))
            return _copy(current)
        except CustodyError: raise
        except Exception: raise CustodyError("custody_refused", "storage_root") from None

    def is_actual(self):
        return type(self) is Epoch and self.fixture is False and self._permission is _ACTUAL \
            and self.root == LANE_ROOT and self.storage_root == PRIVATE_CUSTODY_ROOT

    def _write(self, name, raw):
        _need(type(name) is str and _NAME.fullmatch(name) and type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,
            "arguments_refused", "arguments")
        role = _role(name); leaf = None
        try:
            leaf = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600, dir_fd=self.directory.fd)
            initial = os.fstat(leaf)
            _need(stat.S_ISREG(initial.st_mode) and stat.S_IMODE(initial.st_mode) == 0o600
                and initial.st_uid == os.geteuid() and initial.st_nlink == 1, "custody_refused", role)
            count = 0
            while count < len(raw):
                wrote = os.write(leaf, memoryview(raw)[count:]); _need(type(wrote) is int and wrote > 0, "publication_refused", role)
                count += wrote
            os.fsync(leaf); creator = custody._version(os.fstat(leaf))
        except CustodyError: raise
        except (OSError, ValueError, TypeError):
            raise CustodyError("publication_refused", role) from None
        finally:
            primary = sys.exc_info()[0] is not None
            if leaf is not None:
                try: os.close(leaf)
                except OSError:
                    if not primary: raise CustodyError("cleanup_refused", role) from None
        try:
            os.fsync(self.directory.fd)
            if self.fixture:
                pin = {"bytes": len(raw), "sha256": _sha(raw), "version": creator}
            else:
                pin = seal.seal_written(self.directory.fd, name, raw)
                _need(tuple(pin["version"][:6]) == creator[:6], "output_changed", role,
                    _different(creator, tuple(pin["version"])))
            _read_leaf(self.directory.fd, name, pin)
            return _pin_copy(pin)
        except CustodyError: raise
        except seal.PublicationSealError:
            raise CustodyError("seal_refused", role) from None
        except (OSError, ValueError, TypeError, KeyError):
            raise CustodyError("publication_refused", role) from None

    def check(self):
        try:
            _need(_raw(self.identity) == self._identity_raw and _raw(self.registration) == self._registration_raw
                and self.root == LANE_ROOT and self.storage_root == self._storage_bound
                and self.fixture is self._fixture_bound and self.audit_id == self._audit_bound,
                "identity_refused", "reservation", ("identity",))
            self._checker(); self.parent.recheck(); _private_directory(self.directory)
            if self.fixture: _private_directory(self.parent, "storage_root")
            else: _managed(self.parent)
            self.storage_identity
            _need(set(os.listdir(self.directory.fd)) == set(self._pins), "output_changed", "epoch", ("inventory",))
            _need(len(self._pins) <= MAX_LEAVES and sum(p["bytes"] for p in self._pins.values()) <= MAX_EPOCH_BYTES,
                "custody_refused", "epoch", ("size",))
            for name, pin in self._pins.items(): _read_leaf(self.directory.fd, name, pin)
            self.parent.recheck(); self.directory.recheck()
        except CustodyError: raise
        except Exception:
            raise CustodyError("custody_refused", "epoch") from None

    def publish(self, name, value):
        _need(type(name) is str and _NAME.fullmatch(name), "arguments_refused", "arguments")
        self.check()
        _need(name not in self._pins and name != "reservation.json", "namespace_consumed", _role(name))
        raw = _raw(value)
        _need(len(self._pins) < MAX_LEAVES and sum(p["bytes"] for p in self._pins.values()) + len(raw) <= MAX_EPOCH_BYTES,
            "publication_refused", _role(name), ("size",))
        self._pins[name] = self._write(name, raw)
        self.check()
        return self._pins[name]["sha256"]

    def read(self, name):
        _need(type(name) is str and _NAME.fullmatch(name), "arguments_refused", "arguments")
        self.check(); _need(name in self._pins, "custody_refused", _role(name))
        raw, _ = _read_leaf(self.directory.fd, name, self._pins[name])
        return _decode(raw)

    def close(self):
        primary = sys.exc_info()[0] is not None
        chains = (self.parent, self.directory)
        self.parent = self.directory = None
        _close_chains(chains, primary=primary)


def _native(memory):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH and type(memory) is native._WorkerMemoryGuard,
        "native_refused", "native")
    native._isolated(); native.batch.campaign.base._prove_isolation(); memory.check()


def snapshot_paths():
    return tuple(LEGACY_ROOT / name for name in SNAPSHOT_PINS)


def _snapshot(root, pins, *, fixture, memory):
    _need(type(pins) is dict and set(pins) == set(SNAPSHOT_PINS), "snapshot_refused", "snapshot")
    chains, values, observed = [], {}, {}
    try:
        parent = _HeldChain(root, ()); chains.append(parent); _private_directory(parent)
        holders = {"": parent}
        for folder in (LEGACY_AUDIT, LEGACY_SECOND, LEGACY_THIRD):
            chain = _HeldChain(root, (folder,)); chains.append(chain); _private_directory(chain); holders[folder] = chain
        def inventories():
            _need(set(os.listdir(parent.fd)) == _TOP_NAMES
                and not os.listdir(holders[LEGACY_AUDIT].fd) and not os.listdir(holders[LEGACY_SECOND].fd)
                and set(os.listdir(holders[LEGACY_THIRD].fd)) == _THIRD_NAMES,
                "snapshot_refused", "snapshot", ("inventory",))
        inventories()
        for relative, pin in pins.items():
            memory.check()
            _need(type(pin) is dict and set(pin) == {"bytes", "sha256"}
                and type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_BYTES
                and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"]), "snapshot_refused", "snapshot")
            folder, name = relative.split("/", 1) if "/" in relative else ("", relative)
            raw, observation = _read_leaf(holders[folder].fd, name, pin)
            values[relative] = _decode(raw); observed[relative] = observation
        for name, head in zip(list(SNAPSHOT_PINS)[:3], LEGACY_HEADS):
            _need(type(values[name]) is dict and values[name].get("fixture_only") is fixture
                and type(values[name].get("execution_identity")) is dict
                and values[name]["execution_identity"].get("head") == head, "snapshot_refused", "snapshot")
        for relative, pin in observed.items():
            folder, name = relative.split("/", 1) if "/" in relative else ("", relative)
            _read_leaf(holders[folder].fd, name, pin)
        inventories()
        for chain in chains: chain.recheck()
        memory.check()
        value = {"schema": SCHEMA + "/failed-predecessor-snapshot", "fixture_only": fixture,
            "pins": {name: {"bytes": pin["bytes"], "sha256": pin["sha256"]} for name, pin in observed.items()},
            "root_entries": 6, "empty_preinput_audits": 2, "third_candidate_control_leaves": 4,
            "previous_operations_successful": False, "candidate_controls_promoted": False,
            "provider_request_plan_present": False, "credential_journals_present": False,
            "provider_request_journals_present": False, "old_bytes_changed": False,
            "prior_provider_invocations_proved_zero": True, "prior_credential_reads_proved_zero": True}
        return validate_snapshot(value, fixture=fixture)
    except CustodyError: raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise CustodyError("snapshot_refused", "snapshot") from None
    finally: _close_chains(chains, primary=sys.exc_info()[0] is not None)


def snapshot_actual(*, memory):
    _native(memory)
    return _snapshot(LEGACY_ROOT, SNAPSHOT_PINS, fixture=False, memory=memory)


def snapshot_invented(root, *, pins, memory):
    _native(memory)
    return _snapshot(_fixture_root(root), pins, fixture=True, memory=memory)


def validate_snapshot(value, *, fixture=False):
    """Pure shape/pin validation; caller flags alone create no provenance."""
    keys = {"schema", "fixture_only", "pins", "root_entries", "empty_preinput_audits", "third_candidate_control_leaves",
        "previous_operations_successful", "candidate_controls_promoted", "provider_request_plan_present",
        "credential_journals_present", "provider_request_journals_present", "old_bytes_changed",
        "prior_provider_invocations_proved_zero", "prior_credential_reads_proved_zero"}
    _need(type(fixture) is bool and type(value) is dict and set(value) == keys
        and value["schema"] == SCHEMA + "/failed-predecessor-snapshot"
        and value["fixture_only"] is fixture and type(value["pins"]) is dict
        and set(value["pins"]) == set(SNAPSHOT_PINS), "snapshot_refused", "snapshot")
    for name, pin in value["pins"].items():
        _need(type(pin) is dict and set(pin) == {"bytes", "sha256"}
            and type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_BYTES
            and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"])
            and (fixture or pin == SNAPSHOT_PINS[name]), "snapshot_refused", "snapshot")
    for name, number in (("root_entries", 6), ("empty_preinput_audits", 2), ("third_candidate_control_leaves", 4)):
        _need(type(value[name]) is int and value[name] == number, "snapshot_refused", "snapshot")
    for name in ("previous_operations_successful", "candidate_controls_promoted", "provider_request_plan_present",
        "credential_journals_present", "provider_request_journals_present", "old_bytes_changed"):
        _need(value[name] is False, "snapshot_refused", "snapshot")
    _need(value["prior_provider_invocations_proved_zero"] is True
        and value["prior_credential_reads_proved_zero"] is True, "snapshot_refused", "snapshot")
    return _copy(value)


def _read_epoch_controls(root, audit_id, names, external_pins, *, memory, fixture):
    _need(type(audit_id) is str and _AUDIT.fullmatch(audit_id) and type(names) in {tuple, list}
        and 0 < len(names) <= MAX_LEAVES and len(set(names)) == len(names)
        and all(type(n) is str and _NAME.fullmatch(n) for n in names)
        and type(external_pins) is dict and (set(external_pins) == set(names)
            or "complete.json" in names and set(external_pins) == {"complete.json"}), "arguments_refused", "arguments")
    parent = directory = None
    try:
        parent = _HeldChain(root, ())
        if fixture: _private_directory(parent, "storage_root")
        else: _managed(parent)
        directory = _HeldChain(root, (audit_id,)); _private_directory(directory)
        storage_identity = _storage_identity(parent, fixture=fixture)
        _need(set(os.listdir(directory.fd)) == set(names), "custody_refused", "epoch", ("inventory",))
        controls, pins = {}, {}
        def valid_pin(pin, *, complete=False):
            _need(type(pin) is dict and set(pin) == {"bytes", "sha256"}
                and (complete and pin["bytes"] is None or type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_BYTES)
                and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"]), "arguments_refused", "arguments")
        bound = _copy(external_pins)
        if "complete.json" in names:
            _need("complete.json" in bound, "arguments_refused", "complete")
            valid_pin(bound["complete.json"], complete=True)
            raw, pins["complete.json"] = _read_leaf(directory.fd, "complete.json", bound["complete.json"])
            complete = _decode(raw)
            _need(type(complete) is dict and type(complete.get("published_leaf_pins")) is dict
                and set(complete["published_leaf_pins"]) == set(names)-{"complete.json"},
                "custody_refused", "complete", ("inventory",))
            if "storage_identity" in complete:
                _need(complete["storage_identity"] == storage_identity, "identity_refused", "storage_root", ("identity",))
            for name, pin in complete["published_leaf_pins"].items():
                valid_pin(pin)
                _need(name not in bound or bound[name] == pin, "custody_refused", "complete", ("content",))
                bound[name] = pin
            controls["complete.json"] = complete
        _need(set(bound) == set(names), "custody_refused", "complete", ("inventory",))
        for name, pin in bound.items(): valid_pin(pin, complete=name == "complete.json")
        _need(sum((p["bytes"] or pins["complete.json"]["bytes"]) for p in bound.values()) <= MAX_EPOCH_BYTES,
            "custody_refused", "epoch", ("size",))
        for name in names:
            if name == "complete.json": continue
            memory.check(); pin = bound[name]; valid_pin(pin)
            raw, pins[name] = _read_leaf(directory.fd, name, pin); controls[name] = _decode(raw)
        _need(sum(p["bytes"] for p in pins.values()) <= MAX_EPOCH_BYTES, "custody_refused", "epoch", ("size",))
        for name, pin in pins.items(): _read_leaf(directory.fd, name, pin)
        _need(set(os.listdir(directory.fd)) == set(names), "custody_refused", "epoch", ("inventory",))
        parent.recheck(); directory.recheck(); memory.check()
        _need(_storage_identity(parent, fixture=fixture) == storage_identity,
            "identity_refused", "storage_root", ("identity",))
        return {"schema": SCHEMA + "/readback", "audit_id": audit_id, "controls": controls,
            "pins": {n: {"bytes": p["bytes"], "sha256": p["sha256"]} for n, p in pins.items()},
            "storage_identity": storage_identity}
    except CustodyError: raise
    except (OSError, ValueError, TypeError, KeyError):
        raise CustodyError("custody_refused", "epoch") from None
    finally: _close_chains((parent, directory), primary=sys.exc_info()[0] is not None)


def read_epoch_controls(audit_id, names, external_pins, *, memory):
    """Native read-only proof reader: no namespace creation or own self-pin trust."""
    _native(memory)
    return _read_epoch_controls(PRIVATE_CUSTODY_ROOT, audit_id, names, external_pins, memory=memory, fixture=False)


def read_epoch_controls_invented(root, audit_id, names, external_pins, *, memory):
    _native(memory)
    return _read_epoch_controls(_fixture_root(root), audit_id, names, external_pins, memory=memory, fixture=True)
