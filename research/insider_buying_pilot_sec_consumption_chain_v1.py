"""Selected-control consumption chain; not original replay or dispatch authority.

The fixed prior index and four required21 controls authenticate a monotonic
exclusion set. Claim/result hashes remain producer assertions: their leaves,
original bodies and the full roots are deliberately NOT replayed here. The
old campaign's unchained-later-capture stop is untouched. Actual custody is
available only inside a separately qualified native worker at the fixed root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import weakref

from research import insider_buying_pilot_sec_required21_selection_v1 as selection
from research import insider_buying_pilot_sec_required21_capture_v1 as producer

SCHEMA = "insider-pilot-sec-selected-consumption-chain-v1"
SELF_PATH = "research/insider_buying_pilot_sec_consumption_chain_v1.py"
TEST_PATH = "tests/test_insider_buying_pilot_sec_consumption_chain_v1.py"
LANE_ROOT, LANE_BRANCH = producer.LANE_ROOT, producer.LANE_BRANCH
PRODUCER_HEAD = "5f4988f4294eb23f603ea94d0f4eaca962ba03c1"
ROOT_PARTS = producer.ARTIFACT_PARTS
PRIOR_PARTS = (*producer.batch.ARTIFACT_PARTS, "batches", "batch-000001")
MAX_CONTROL = 8 * 1024 * 1024
CONTROL_PINS = {
    "reservation.json": (23055, "501f33d8497ea3d33ac7d6e88690beb821ab3642dd7645e9883f4462f8984f7d"),
    "plan.json": (516504, "79ee10366391b2a0a735f2d5127d583c17bf5d4c12f93871e110de9a1fe0fdf4"),
    "consumed-index.json": (461511, "fc60ac0f83c6e1509cc45e2acf277f7d587906799187b99ca02493cbab66ed59"),
    "complete.json": (24680, "9a0fdbb8c4154d6199c50f8d9625671cef4ac6a8138b10f42c0e9b28b74b0a1c"),
    "previous-index.json": (None, "d501e30d5ce1e9b90cd8738251036fa5f0dbf0a16bba65d6c5d66fa83af4f664"),
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = object()
_SEALS = weakref.WeakKeyDictionary()
_raw, _sha = selection._raw, selection._sha


class ConsumptionChainError(ValueError):
    """Fixed finite refusals; no private supplied values or exception text."""


def _need(ok, code):
    if not ok:
        raise ConsumptionChainError(code)


def _decode(raw):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_CONTROL, "control_bytes_refused")
    try:
        def pairs(items):
            value = {}
            for key, item in items:
                _need(key not in value, "control_schema_refused")
                value[key] = item
            return value
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_float=lambda _: _need(False, "control_schema_refused"),
            parse_constant=lambda _: _need(False, "control_schema_refused"))
        _need(type(value) is dict and _raw(value) == raw, "control_schema_refused")
        return value
    except ConsumptionChainError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ConsumptionChainError("control_schema_refused") from None


def _accessions(values):
    _need(type(values) is list, "consumption_set_refused")
    try:
        return selection._consumed(tuple(values))
    except (ValueError, TypeError):
        raise ConsumptionChainError("consumption_set_refused") from None


def _checked_controls(raws, pins, *, fixture):
    _need(type(fixture) is bool and (fixture or pins is CONTROL_PINS), "actual_pin_scope_refused")
    _need(type(raws) is dict and type(pins) is dict
        and set(raws) == set(pins) == set(CONTROL_PINS), "control_inventory_refused")
    for name, raw in raws.items():
        pin = pins[name]
        _need(type(pin) is tuple and len(pin) == 2 and (pin[0] is None or type(pin[0]) is int)
            and type(pin[1]) is str and _SHA.fullmatch(pin[1]) is not None,
            "external_pin_refused")
        _need(type(raw) is bytes and 0 < len(raw) <= MAX_CONTROL and (pin[0] is None or len(raw) == pin[0])
            and _sha(raw) == pin[1], "external_pin_refused")
    try:
        values = {name: _decode(raw) for name, raw in raws.items()}
        prior, reservation, plan, index, complete = (values[name] for name in
            ("previous-index.json", "reservation.json", "plan.json", "consumed-index.json", "complete.json"))
        plan = selection.validate_selection_payload(plan)
        old = _accessions(prior["accessions"])
        following = _accessions(index["accessions"])
        registered = producer.registration()
        if fixture:
            registered["known_consumed_count"] = len(old)
            registered["known_consumed_index_sha256"] = _sha(raws["previous-index.json"])
        _need(set(prior) == {"schema", "generation", "accessions", "plan_sha256", "predecessor_index_sha256",
            "base_consumption", "archive_exposures", "archive_membership_known", "authority"}
            and prior["schema"] == producer.batch.campaign.SCHEMA + "/consumed-index"
            and type(prior["generation"]) is int and prior["generation"] == 1
            and prior["archive_membership_known"] is False
            and _raw(prior["authority"]) == _raw(producer.batch.AUTHORITY), "prior_index_refused")
        _need(tuple(plan["consumed_accessions"]) == old
            and plan["consumption_sha256"] == _sha(raws["previous-index.json"]),
            "prior_consumption_differs")
        expected_keys = {"schema", "audit_id", "fixture_only", "execution_identity", "registration_sha256",
            "reservation_sha256", "plan_sha256", "index_sha256", "planned", "started", "unattempted",
            "results", "completed_without_refusal", "authority"}
        _need(set(complete) == expected_keys and complete["schema"] == producer.SCHEMA + "/complete"
            and complete["audit_id"] == producer.AUDIT_ID and complete["fixture_only"] is fixture
            and plan["fixture_only"] is fixture and _raw(complete["authority"]) == _raw(producer._authority()),
            "completion_schema_refused")
        _need(complete["reservation_sha256"] == _sha(raws["reservation.json"])
            and complete["plan_sha256"] == _sha(raws["plan.json"])
            and complete["index_sha256"] == _sha(raws["consumed-index.json"])
            and complete["registration_sha256"] == _sha(_raw(registered)),
            "control_crosslinks_refused")
        _need(set(reservation) == {"schema", "audit_id", "execution_identity", "registration", "input_metadata_sha256", "authority"}
            and reservation["schema"] == producer.SCHEMA + "/reservation"
            and reservation["audit_id"] == producer.AUDIT_ID
            and _raw(reservation["execution_identity"]) == _raw(complete["execution_identity"])
            and _raw(reservation["registration"]) == _raw(registered)
            and _raw(reservation["authority"]) == _raw(producer._authority())
            and type(reservation["input_metadata_sha256"]) is str
            and _SHA.fullmatch(reservation["input_metadata_sha256"]) is not None,
            "reservation_crosslinks_refused")
        if fixture:
            _need(_raw(complete["execution_identity"]) == _raw({"fixture_only": True}), "fixture_identity_refused")
        else:
            identity = complete["execution_identity"]
            producer.source.publication._source_identity(identity,
                required_paths=(producer.SELF_PATH, producer.TEST_PATH, producer.PURE_PATH, producer.PURE_TEST_PATH))
            _need(identity["head"] == PRODUCER_HEAD and identity["root"] == str(LANE_ROOT)
                and identity["branch"] == LANE_BRANCH and identity["clean"] is True,
                "producer_identity_refused")
            _need(len(old) == 20044 and len(following) == 20052
                and complete["planned"] == complete["started"] == 8
                and complete["unattempted"] == 0 and complete["completed_without_refusal"] is True,
                "recorded_count_refused")
        planned, started, unattempted = (complete[key] for key in ("planned", "started", "unattempted"))
        _need(type(planned) is type(started) is type(unattempted) is int
            and planned == len(plan["requests"]) and 0 < started <= planned <= 8
            and unattempted == planned - started and type(complete["completed_without_refusal"]) is bool
            and (not complete["completed_without_refusal"] or started == planned)
            and type(complete["results"]) is list and len(complete["results"]) == started,
            "started_count_refused")
        added = []
        for ordinal, descriptor in enumerate(complete["results"]):
            accession = plan["requests"][ordinal]["request"]["accession_number"]
            expected = {"accession_number", "claim_name", "claim_sha256", "start_name", "start_sha256", "result_name", "result_sha256"}
            _need(type(descriptor) is dict and set(descriptor) == expected
                and descriptor["accession_number"] == accession
                and descriptor["claim_name"] == _sha(accession.encode()) + ".json"
                and descriptor["start_name"] == f"request-{ordinal:03d}-start.json"
                and descriptor["result_name"] == f"request-{ordinal:03d}-result.json"
                and all(type(descriptor[key]) is str and _SHA.fullmatch(descriptor[key]) is not None
                    for key in ("claim_sha256", "start_sha256", "result_sha256")),
                "started_descriptor_refused")
            added.append(accession)
        _need(len(set(added)) == len(added) and not set(added) & set(old)
            and tuple(sorted((*old, *added))) == following,
            "monotonic_consumption_refused")
        _need(_raw(index) == _raw({"schema": producer.SCHEMA + "/consumed-index", "accessions": list(following),
            "previous_index_sha256": _sha(raws["previous-index.json"]),
            "plan_sha256": _sha(raws["plan.json"]), "unknown_prior_archive_memberships_remain_unknown": True}),
            "index_crosslinks_refused")
        return old, following, added
    except ConsumptionChainError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ConsumptionChainError("control_crosslinks_refused") from None


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class ConsumptionChain:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) is ConsumptionChain and self._token is _TOKEN and _SEALS.get(self) == self._bytes,
            "genuine_chain_required")
        return self._bytes

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def _seal(raws, pins, *, fixture, selected_metadata_custody_verified):
    _need(type(selected_metadata_custody_verified) is bool
        and (not fixture or not selected_metadata_custody_verified), "fixture_custody_scope_refused")
    old, following, added = _checked_controls(raws, pins, fixture=fixture)
    value = {"schema": SCHEMA, "fixture_only": fixture,
        "control_sha256": {name: _sha(raw) for name, raw in sorted(raws.items())},
        "prior_count": len(old), "started_added_count": len(added), "consumed_count": len(following),
        "accessions": list(following), "consumed_accessions_sha256": _sha(_raw(list(following))),
        "selected_metadata_custody_verified": selected_metadata_custody_verified,
        "full_root_inventory_verified": False, "claim_start_result_leaves_replayed": False,
        "original_bodies_replayed": False, "producer_git_images_verified_here": False,
        "archive_membership_known": False, "unknown_prior_archive_memberships_remain_unknown": True,
        "new_source_requests": 0, "original_body_reads": 0, "credential_reads": 0,
        "qc_accesses": 0, "outcome_looks": 0, "backtests": 0, "authority": producer._authority()}
    chain = ConsumptionChain(_raw(value), _TOKEN)
    _SEALS[chain] = chain._bytes
    return chain


def qualify_invented_controls(raws, *, expected_pins):
    """Invented canonical metadata only; never creates an actual chain seal."""
    return _seal(raws, expected_pins, fixture=True, selected_metadata_custody_verified=False)


def _payload(chain):
    _need(type(chain) is ConsumptionChain, "genuine_chain_required")
    return _decode(chain.canonical_bytes())


def public_summary(chain):
    """Detached counts/hashes/flags only; accession identities stay private."""
    value = _payload(chain)
    del value["accessions"]
    return {**value, "chain_sha256": chain.sha256}


def consumed_accessions(chain):
    """Explicit private consumer API; never use this in public IPC or logs."""
    return _accessions(_payload(chain)["accessions"])


class _SelectionAdapter:
    def __init__(self, chain, limit):
        self.chain = chain
        self.builder = selection.Required21SelectionBuilder(consumed_accessions=consumed_accessions(chain),
            consumption_sha256=chain.sha256, limit=limit)

    def consume(self, row):
        return self.builder.consume(row)

    def finish(self, **arguments):
        result = self.builder.finish(**arguments)
        _need(result.to_payload()["fixture_only"] is _payload(self.chain)["fixture_only"],
            "chain_source_scope_differs")
        return result


def required21_selection_builder(chain, *, limit=selection.MAX_SELECTED):
    """Retains genuine full25/restricted21 selection and false dispatch flags."""
    _payload(chain)
    return _SelectionAdapter(chain, limit)


def _version(info):
    # Darwin tracking may change ctime alone during a read. Final byte hashes
    # remain binding; do not claim an atomic snapshot against arbitrary writers.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_uid, info.st_size, info.st_mtime_ns)


class _SelectedHold:
    """Held no-follow ancestry/selected leaves, not exhaustive root inventory."""
    def __init__(self, root, parts, *, lock_bytes):
        self.fds, self.leaves, self.lock = [], {}, None
        try:
            path = Path(root)
            _need(path.is_absolute() and all(part not in {"", ".", ".."} for part in parts), "custody_refused")
            fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append((fd, None, None, _version(os.fstat(fd))))
            for part in (*path.parts[1:], *parts):
                parent = self.fds[-1][0]
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                self.fds.append((fd, parent, part, _version(os.fstat(fd))))
            self.fd = self.fds[-1][0]
            info = os.fstat(self.fd)
            _need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, "custody_refused")
            self.lock = os.open("scope.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
            fcntl.flock(self.lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.lock_version = _version(os.fstat(self.lock))
            _need(self.read("scope.lock", cap=4096) == lock_bytes, "custody_refused")
        except BaseException:
            self.close()
            raise

    def read(self, name, *, cap=MAX_CONTROL):
        _need(type(name) is str and "/" not in name and name not in {"", ".", ".."}, "custody_refused")
        before = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid()
            and stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= cap, "custody_refused")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            version = _version(before)
            _need(_version(os.fstat(fd)) == version, "custody_refused")
            chunks, size = [], 0
            while chunk := os.read(fd, min(65536, cap + 1 - size)):
                size += len(chunk)
                _need(size <= cap, "custody_refused")
                chunks.append(chunk)
            raw = b"".join(chunks)
            _need(size == before.st_size and _version(os.fstat(fd)) == version
                == _version(os.stat(name, dir_fd=self.fd, follow_symlinks=False)), "custody_refused")
        finally:
            os.close(fd)
        pin = version, _sha(raw), len(raw)
        _need(name not in self.leaves or self.leaves[name] == pin, "custody_refused")
        self.leaves[name] = pin
        return raw

    def recheck(self):
        for index, (fd, parent, name, version) in enumerate(self.fds):
            current = _version(os.fstat(fd))
            # Shared ancestors need identity, owner and mode, not an assertion
            # that another lane cannot add an unrelated sibling directory.
            _need((current[0], current[1], current[2], current[4])
                == (version[0], version[1], version[2], version[4]), "custody_refused")
            if parent is not None:
                linked = _version(os.stat(name, dir_fd=parent, follow_symlinks=False))
                _need((linked[0], linked[1], linked[2], linked[4])
                    == (version[0], version[1], version[2], version[4]), "custody_refused")
            if index == len(self.fds) - 1:
                _need(current == version, "custody_refused")
        _need(_version(os.fstat(self.lock)) == self.lock_version
            == _version(os.stat("scope.lock", dir_fd=self.fd, follow_symlinks=False)), "custody_refused")
        for name, (version, digest, size) in tuple(self.leaves.items()):
            _need(self.read(name, cap=size) is not None and self.leaves[name] == (version, digest, size), "custody_refused")
        # A new entry arriving while selected files were hashed still changes
        # this root version. This does not enumerate/validate existing extras.
        _need(_version(os.fstat(self.fd)) == self.fds[-1][3], "custody_refused")

    def close(self):
        primary, failed = sys.exc_info()[0] is not None, False
        for fd in ([self.lock] if self.lock is not None else []) + [item[0] for item in reversed(self.fds)]:
            try:
                os.close(fd)
            except OSError:
                failed = True
        self.lock, self.fds = None, []
        if failed and not primary:
            raise ConsumptionChainError("cleanup_refused")


def read_actual_chain(*, memory):
    """Fixed actual roots inside a qualified native worker; selected files only.

    Caller must keep the REAL memory guard alive through result serialization,
    stdout/flush and a final sample. This function checks it before inputs and
    after held-file rechecks; it performs no Git, process launch or publication.
    """
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH
        and sys.flags.isolated == sys.flags.no_site == sys.flags.no_user_site == sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == producer.EMPTY_CACHE_PREFIX, "native_refused")
    native = producer.previous
    _need(type(memory) is native._WorkerMemoryGuard, "native_refused")
    producer.base._prove_isolation()
    memory.check()
    required = prior = None
    try:
        required = _SelectedHold(LANE_ROOT, ROOT_PARTS, lock_bytes=producer.LOCK_BYTES)
        prior = _SelectedHold(LANE_ROOT, PRIOR_PARTS, lock_bytes=producer.batch.LOCK_BYTES)
        raws = _actual_raws(required, prior)
        chain = _seal(raws, CONTROL_PINS, fixture=False, selected_metadata_custody_verified=True)
        required.recheck()
        prior.recheck()
        memory.check()
        return chain
    except ConsumptionChainError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ConsumptionChainError("custody_refused") from None
    finally:
        producer.base.selector._close_all((prior, required), phase="consumption_chain_cleanup")


def _actual_raws(required, prior):
    """Each external pin precedes the next selected control's read/decoding."""
    raws = {}
    for name in ("complete.json", "reservation.json", "plan.json", "consumed-index.json", "previous-index.json"):
        hold, leaf = (prior, "consumed-index.json") if name == "previous-index.json" else (required, name)
        size, digest = CONTROL_PINS[name]
        raw = hold.read(leaf, cap=size or MAX_CONTROL)
        _need(type(raw) is bytes and (size is None or len(raw) == size) and _sha(raw) == digest,
            "external_pin_refused")
        raws[name] = raw
    return raws
