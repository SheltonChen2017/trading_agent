"""Exact single-file count controls; no provider or budget-settlement grant.

Only genuine registered operations can spend a new role. Claim/START controls
are small; final controls use a distinct bounded metadata scope. Old synthetic
capabilities are never cast or minted as these semantic control capabilities.
"""
from contextlib import contextmanager
import fcntl
import json
import os
import re
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_body_receipt_custody as kernel
from scripts import short_interest_count_durable_budget as budget

creator, cache, immutable, _OwnedOutput = kernel.creator, kernel.cache, kernel.immutable, kernel._OwnedOutput
MAXIMUM_SMALL_BYTES, MAXIMUM_FINAL_BYTES = 1024, 2 * 1024 ** 2
MAXIMUM_SECONDS, MAXIMUM_SAMPLES, SAMPLE_SECONDS, QUIET_SECONDS = 8.0, 16, .25, 1.0
_NAMES = (("claim", "claim.spent.json"), ("start", "START.spent.json"), ("received", "received.private.json"),
    ("inventory", "inventory.private.json"), ("provisional", "provisional.json"),
    ("closed", "closed.json"), ("manifest", "manifest.private.json"))
_CAPS, _STATES, _SHADOWS, _CHOICES, _HELD, _ISSUED, _VOLUMES = {}, {}, {}, {}, {}, {}, {}
_FAILED, _USED, _SETTER_USED, _SEAL_USED = set(), set(), set(), set()
_CODES = frozenset("""count_control_policy_changed count_control_factory_required
count_control_binding_changed count_control_refused count_control_not_closed count_control_not_live
count_control_role_spent count_control_role_changed count_control_operation_changed
count_control_directory_changed count_control_membership_changed count_control_payload_changed
count_control_bounds_changed count_control_clock_changed count_control_window_exhausted
count_control_samples_exhausted count_control_seal_once count_control_write_progress
count_control_initial_flags_changed count_control_original_seal_changed""".split())


class CountControlRefusal(ValueError): pass


def require(value, code):
    if not value: raise CountControlRefusal("REFUSED: " + code)


def failure_summary(error):
    if type(error) is not CountControlRefusal: return kernel.failure_summary(error)
    args = BaseException.args.__get__(error, BaseException)
    code = next((name for name in _CODES if type(args) is tuple and len(args) == 1
        and type(args[0]) is str and args[0] == "REFUSED: " + name), None)
    return {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}


def authority():
    return {"custody_only": True, "count_control_only": True, "dispatch_authority": False,
        "budget_release_authority": False, "source_admitted": False,
        "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0}


def policy():
    return {"schema": "si-count-control-custody-policy-v1", "names": [list(row) for row in _NAMES],
        "maximum_small_bytes": MAXIMUM_SMALL_BYTES, "maximum_final_bytes": MAXIMUM_FINAL_BYTES,
        "per_file_seconds": MAXIMUM_SECONDS, "samples": MAXIMUM_SAMPLES,
        "sample_seconds": SAMPLE_SECONDS, "quiet_seconds": QUIET_SECONDS,
        "initial_flags": [0, 64], "expected_flags": [2, 66],
        "kernel_policy_sha256": hash_payload(immutable.policy()),
        "typed_semantics": "original_operation_claim_start_candidate_only_no_caller_JSON",
        "creation": "one_fresh_O_EXCL0600_singlelink_role_spent_before_first_attempt",
        "closure": "original_HeldFiles_reader_close_then_original_named9seal_and_full_postclose_audit",
        "callbacks": "serialized_by_original_operation_RLock", "authority": authority()}


def _policy():
    actual = (MAXIMUM_SMALL_BYTES, MAXIMUM_FINAL_BYTES, MAXIMUM_SECONDS, MAXIMUM_SAMPLES, SAMPLE_SECONDS, QUIET_SECONDS)
    expected = (1024, 2097152, 8.0, 16, .25, 1.0)
    names = (("claim", "claim.spent.json"), ("start", "START.spent.json"), ("received", "received.private.json"),
        ("inventory", "inventory.private.json"), ("provisional", "provisional.json"),
        ("closed", "closed.json"), ("manifest", "manifest.private.json"))
    require(all(type(a) is type(b) and a == b for a, b in zip(actual, expected))
        and type(_NAMES) is tuple and len(_NAMES) == len(names)
        and all(type(row) is tuple and len(row) == 2 and all(type(value) is str for value in row)
            and row == wanted for row, wanted in zip(_NAMES, names))
        and hash_payload(policy()) == _POLICY_SHA, "count_control_policy_changed")
    immutable._platform()


def _transport():
    from scripts import short_interest_count_durable_transport
    return short_interest_count_durable_transport


def _operation(operation, *, active=False):
    transport = _transport()
    original = (transport.active_operation_binding if active else transport.operation_binding)(operation)
    require(type(original) is tuple and len(original) == 14 and original[0] is operation,
        "count_control_operation_changed")
    return original


def _latch(cap):
    if cap in _CAPS: _FAILED.add(cap)


def _state(cap):
    current, original = _STATES.get(cap), _SHADOWS.get(cap)
    require(type(current) is dict and type(original) is tuple
        and tuple(current) == tuple(name for name, unused in original)
        and all(current[name] is saved for name, saved in original), "count_control_binding_changed")
    return current


def _update(cap, **values):
    state = _state(cap); state.update(values); _SHADOWS[cap] = tuple(state.items())


def _canonical(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, "count_control_bounds_changed")
    try:
        value = json.loads(raw, parse_constant=lambda unused: (_ for _ in ()).throw(ValueError()))
        require(type(value) is dict and canonical_json(value).encode() == raw, "count_control_payload_changed")
    except (ValueError, TypeError, UnicodeError):
        raise CountControlRefusal("REFUSED: count_control_payload_changed") from None
    return value


class _Control:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountControlRefusal("REFUSED: count_control_factory_required")
    def __repr__(self): return "<CountControl redacted>"
    def _binding(self):
        original = _CAPS.get(self) if type(self) in (CountClaim, CountStart, CountReceived, CountFinalControl) else None
        try:
            require(type(original) is tuple and len(original) == 9
                and self._anchor is self._identity is original[0], "count_control_binding_changed")
            require(self not in _FAILED, "count_control_refused")
            _policy(); _operation(original[1]); state = _state(self)
            transport = _transport()
            require(transport.volume_for_operation(original[1]) is _VOLUMES.get(self), "count_control_operation_changed")
            transport._control_volume_binding(original[1], live=state["phase"] != "CLOSED")
            require((state["phase"] == "CLOSED") is (self in _ISSUED)
                and state["choice"] is _CHOICES.get(self)
                and (state["held"] is None or state["held"] is _HELD.get(self)), "count_control_binding_changed")
            return original, state
        except BaseException: _latch(self); raise
    def _tick(self):
        original, state = self._binding(); origin = original[0]; now = origin[13]()
        require(creator._valid_tick(now) and now >= state["last_tick"], "count_control_clock_changed")
        require(now - origin[12] <= MAXIMUM_SECONDS, "count_control_window_exhausted")
        _update(self, last_tick=now); return now
    def _boundary(self):
        original, state = self._binding(); origin = original[0]; op = _operation(original[1])
        with op[11]:
            require(origin[0]._anchor is origin[1], "count_control_directory_changed")
            origin[0].check(); origin[11](); origin[0].check()
            _operation(original[1])
        if state["phase"] in ("UNSEALED", "SEALING"): self._tick()
    def _strict(self):
        original, state = self._binding(); origin = original[0]; self._boundary()
        require(state["choice"] is not None, "count_control_not_live")
        kernel._pair(origin, state["choice"]); kernel._read_original(origin, origin[7], state["choice"])
        kernel._pair(origin, state["choice"])
    def seal_once(self):
        try:
            original, state = self._binding(); origin = original[0]
            require(self not in _SEAL_USED and state["phase"] == "UNSEALED", "count_control_seal_once")
            _SEAL_USED.add(self); prior, quiet_at = None, None
            for number in range(1, MAXIMUM_SAMPLES + 1):
                if number > 1: origin[14](SAMPLE_SECONDS); self._tick()
                self._boundary(); before = kernel._pair(origin)
                kernel._read_original(origin, origin[7], before[0], allow_ctime=True, creation_tick=self._tick)
                after = kernel._pair(origin); now = self._tick(); candidate = after[-1]
                stable = all(item == candidate for item in (*before, *after))
                if not stable or candidate != prior: quiet_at = now if stable else None
                quiet = 0 if quiet_at is None else now - quiet_at
                _update(self, samples=(*state["samples"], (number, stable))); prior = candidate
                if stable and quiet >= QUIET_SECONDS:
                    _CHOICES[self] = candidate; _update(self, choice=candidate, phase="SEALING")
                    held = cache.HeldFiles((origin[1][0] / origin[3],), protected=True, boundary=self._strict)
                    _HELD[self] = held; _update(self, held=held)
                    require(held._anchor[1][0][3] == (candidate[0], candidate[1], candidate[5], candidate[6], candidate[7])
                        and held._anchor[1][0][4:6] == candidate[2:4], "count_control_original_seal_changed")
                    _update(self, phase="SEALED"); self.check(); self._tick(); return
            raise CountControlRefusal("REFUSED: count_control_samples_exhausted")
        except BaseException: _latch(self); raise
    def check(self):
        try:
            original, state = self._binding()
            require(state["phase"] == "SEALED", "count_control_not_live")
            self._strict(); state["held"].check()
            require(state["held"].read(original[0][1][0] / original[0][3], len(original[0][4])) == original[0][4],
                "count_control_payload_changed")
            self._strict()
        except BaseException: _latch(self); raise
    def read(self):
        original, state = self._binding()
        if state["phase"] == "CLOSED": self.check_after_close()
        else: self.check()
        return original[0][4]
    def check_after_close(self):
        try:
            original, state = self._binding()
            require(state["phase"] == "CLOSED" and _ISSUED.get(self) is original, "count_control_not_closed")
            _audit_closed(original[0], _CHOICES[self])
        except BaseException: _latch(self); raise
    def observation(self):
        original, state = self._binding(); origin = original[0]
        return {"role": original[4], "bytes": len(origin[4]), "raw_sha256": origin[5],
            "seal_stamp_sha256": None if state["choice"] is None else hash_payload(state["choice"]),
            "closed": state["phase"] == "CLOSED", "authority": authority()}


class CountClaim(_Control): __slots__ = ()
class CountStart(_Control): __slots__ = ()
class CountReceived(_Control): __slots__ = ()
class CountFinalControl(_Control): __slots__ = ()


def _audit_closed(origin, expected):
    anchor, descriptors = origin[1], []
    directory, parent = anchor[:2]
    try:
        require(directory.resolve() == directory and parent.resolve() == parent
            and _OwnedOutput._stamp(parent.lstat()) == anchor[5]
            and _OwnedOutput._stamp(directory.lstat()) == anchor[4], "count_control_directory_changed")
        pfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); descriptors.append(pfd)
        require(_OwnedOutput._stamp(os.fstat(pfd)) == anchor[5], "count_control_directory_changed")
        dfd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=pfd); descriptors.append(dfd)
        require(_OwnedOutput._stamp(os.fstat(dfd)) == anchor[4]
            and cache._inventory_names(dfd, boundary=lambda: None) == (origin[3],), "count_control_membership_changed")
        fd = os.open(origin[3], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd); descriptors.append(fd)
        replacement = (*origin[:6], dfd, *origin[7:])
        kernel._read_original(replacement, fd, expected)
        require(immutable._stamp(os.stat(origin[3], dir_fd=dfd, follow_symlinks=False)) == expected
            and cache._inventory_names(dfd, boundary=lambda: None) == (origin[3],), "count_control_original_seal_changed")
    finally: kernel._close_all(descriptors)
    require(_OwnedOutput._stamp(parent.lstat()) == anchor[5] and _OwnedOutput._stamp(directory.lstat()) == anchor[4]
        and immutable._stamp((directory / origin[3]).lstat()) == expected
        and tuple(sorted(os.listdir(directory))) == (origin[3],), "count_control_original_seal_changed")
    require(_OwnedOutput._stamp(parent.lstat()) == anchor[5] and _OwnedOutput._stamp(directory.lstat()) == anchor[4],
        "count_control_directory_changed")


def _closed(cap, cls):
    require(type(cap) is cls, "count_control_binding_changed")
    cap.check_after_close(); return _CAPS[cap]


def claim_binding(claim):
    original = _closed(claim, CountClaim); origin, operation, unused_ticket, unused_claim, unused_role, started, nonce, unused_candidate, unused_observation = original
    op = _operation(operation)
    return claim, operation, op[1], op[2], op[4], op[5], origin[5], op[6], origin, _CHOICES[claim], started, nonce


def start_binding(start):
    original = _closed(start, CountStart); origin, operation, ticket, claim, unused_role, started, nonce, unused_candidate, unused_observation = original
    op = _operation(operation); ticket_parts = budget.ticket_binding(ticket); bound_claim = claim_binding(claim)
    return start, operation, ticket, claim, origin[5], ticket_parts[8], op[5], bound_claim[6], started, origin, _CHOICES[start], nonce


def final_control_binding(control):
    original = _closed(control, CountFinalControl); origin, operation, unused_ticket, unused_claim, role, unused_started, nonce, candidate, unused_observation = original
    return control, operation, role, origin[5], origin, _CHOICES[control], candidate, nonce


def received_binding(received):
    original = _closed(received, CountReceived)
    origin, operation, ticket, claim, unused_role, unused_started, nonce, unused_candidate, observation = original
    bound = _transport().http_observation_binding(observation)
    require(bound[1] is operation and bound[2] is ticket and bound[3] is claim, "count_control_binding_changed")
    return received, operation, ticket, observation, claim, bound[4], origin[5], origin, _CHOICES[received], bound[12], bound[7], nonce


@contextmanager
def _prepare_control(owned, operation, role, *, ticket=None, claim=None, candidate=None,
        observation=None, boundary, monotonic, sleep):
    began, last = monotonic(), [None]
    require(creator._valid_tick(began), "count_control_clock_changed")
    _policy(); op = _operation(operation, active=True); transport = _transport()
    require(type(role) is str and role in dict(_NAMES), "count_control_role_changed")
    with op[11]:
        _operation(operation, active=True)
        transport._control_volume_binding(operation, live=True)
        volume = transport.volume_for_operation(operation)
        if role == "received":
            observed = transport.http_observation_binding(observation)
            require(type(observed) is tuple and len(observed) == 16 and observed[1] is operation,
                "count_control_binding_changed")
            ticket, claim = observed[2:4]
        require(role not in ("start", "received") or type(ticket) is budget.CountAttemptTicket, "count_control_binding_changed")
        if role == "start": transport.start_permission_binding(operation, ticket)
        key = (operation, role, ticket) if role in ("start", "received") else (operation, role)
        require(key not in _USED, "count_control_role_spent"); _USED.add(key)
        started = kernel._utc_now(); kernel._clock(started)
        if role == "claim":
            require(ticket is claim is candidate is None, "count_control_binding_changed")
            raw = canonical_json({"schema": "si-count-spent-claim-v1", "spent": True, "chunk": op[4],
                "operator_protocol_sha256": op[5], "registration_sha256": op[6], "plan_sha256": op[10],
                "runtime_head": op[8], "actual_remote": op[9], "started_at": started,
                "dispatch_authority": False, "source_admitted": False}).encode(); cls = CountClaim
        elif role == "start":
            parts = budget.active_ticket_binding(ticket); bound = claim_binding(claim)
            require(parts[1] is op[1] and parts[2] is op[2] and parts[3] == op[4] and bound[1] is operation,
                "count_control_binding_changed")
            raw = canonical_json({"schema": "si-count-spent-START-v1", "spent": True, "chunk": op[4],
                "reservation_sha256": parts[9], "request_sha256": parts[8], "ordinal": parts[4],
                "lifetime_try": parts[7], "claim_sha256": bound[6], "operator_protocol_sha256": op[5],
                "started_at": started, "dispatch_authority": False}).encode(); cls = CountStart
        elif role == "received":
            parts = budget.active_ticket_binding(ticket); bound = claim_binding(claim); start = start_binding(observed[4])
            require(parts[1] is op[1] and parts[2] is op[2] and parts[3] == op[4]
                and start[1] is operation and start[2] is ticket and start[3] is claim
                and observed[5] == parts[8] and observed[6] == start[4] and observed[7] == op[5],
                "count_control_binding_changed")
            raw = canonical_json({"schema": "si-count-received-v1", "ordinal": parts[4],
                "reservation_sha256": parts[9], "request_sha256": observed[5], "START_sha256": observed[6],
                "operator_protocol_sha256": observed[7], "observation_sha256": observed[14],
                "http_invoked": observed[8], "http_status": observed[9],
                "body_sha256": None if observed[10] is None else hash_bytes(observed[10]),
                "body_bytes": None if observed[10] is None else len(observed[10]),
                "received_at": observed[12], "diagnostic": observed[13],
                "budget_release_authority": False}).encode(); cls = CountReceived
        else:
            require(type(candidate) is transport.ProvisionalRootClosureCandidate and ticket is claim is None,
                "count_control_binding_changed")
            raw = transport._final_control_payload(operation, candidate, role); cls = CountFinalControl
        maximum = MAXIMUM_SMALL_BYTES if role in ("claim", "start", "received") else MAXIMUM_FINAL_BYTES
        parsed = _canonical(raw, maximum)
        if cls is CountFinalControl:
            fields = {"schema", "role", "chunk", "operator_protocol_sha256", "registration_sha256", "candidate_sha256",
                "payload", "source_admitted", "budget_release_authority"}
            require(set(parsed) == fields and parsed["schema"] == "si-count-final-control-v1" and parsed["role"] == role
                and type(parsed["chunk"]) is int and parsed["chunk"] == op[4] and parsed["operator_protocol_sha256"] == op[5]
                and parsed["registration_sha256"] == op[6] and type(parsed["payload"]) is dict
                and type(parsed["candidate_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", parsed["candidate_sha256"])
                and parsed["source_admitted"] is False and parsed["budget_release_authority"] is False,
                "count_control_payload_changed")
        expected_directory = transport._control_directory(operation, role, ticket=ticket)
    name = dict(_NAMES)[role]
    def tick():
        now = monotonic()
        require(creator._valid_tick(now) and began <= now and (last[0] is None or last[0] <= now), "count_control_clock_changed")
        require(now - began <= MAXIMUM_SECONDS, "count_control_window_exhausted"); last[0] = now
    cap, origin, writer, reader, held = None, None, None, None, None
    def guarded_boundary():
        with op[11]:
            require(_operation(operation) is op, "count_control_operation_changed")
            boundary(); require(_operation(operation) is op, "count_control_operation_changed")
        if cap is not None:
            require(cap._binding()[0][0] is origin, "count_control_binding_changed")
            if _state(cap)["flag_set"]: kernel._pair(origin, _CHOICES.get(cap))
        if cap is None or _state(cap)["phase"] in ("UNSEALED", "SEALING"): tick()
    try:
        require(type(owned) is _OwnedOutput and owned._anchor[0] == expected_directory,
            "count_control_directory_changed")
        with op[11]:
            owned.check(); guarded_boundary()
            require(not cache._inventory_names(owned._anchor[2], boundary=owned.check), "count_control_membership_changed")
        anchor, dirfd = owned._anchor, owned._anchor[2]
        writer = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dirfd)
        os.fchmod(writer, 0o600); tick(); created = creator._stamp(os.fstat(writer)); offset = 0
        while offset < len(raw):
            with op[11]: owned.check(); guarded_boundary()
            for info in (os.fstat(writer), os.stat(name, dir_fd=dirfd, follow_symlinks=False)):
                creator._protected(info, created); require(info.st_size == offset, "count_control_write_progress")
            amount = os.write(writer, memoryview(raw)[offset:]); tick()
            require(type(amount) is int and 0 < amount <= len(raw) - offset, "count_control_write_progress"); offset += amount
        os.fsync(writer); os.fsync(dirfd); tick(); creation = creator._stamp(os.fstat(writer))
        reader = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
        require(fcntl.fcntl(reader, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, "count_control_binding_changed")
        for info in (os.fstat(reader), os.stat(name, dir_fd=dirfd, follow_symlinks=False)):
            creator._protected(info, creation); require(creator._stamp(info)[5:7] == creation[5:7], "count_control_write_progress")
        os.close(writer); writer = None; tick()
        flags = immutable._flags(os.fstat(reader)), immutable._flags(os.stat(name, dir_fd=dirfd, follow_symlinks=False))
        require(flags[0] == flags[1] and flags[0] in (0, 64), "count_control_initial_flags_changed")
        initial = flags[0]; cap = object.__new__(cls)
        origin = owned, anchor, role, name, raw, hash_bytes(raw), dirfd, reader, creation, initial, initial | 2, guarded_boundary, began, monotonic, sleep
        cap._anchor = cap._identity = origin
        original = origin, operation, ticket, claim, role, started, object(), candidate, observation
        _CAPS[cap] = original; state = {"phase": "UNSEALED", "choice": None, "held": None, "last_tick": last[0], "samples": (), "flag_set": False}
        _VOLUMES[cap] = volume
        _STATES[cap] = state; _SHADOWS[cap] = tuple(state.items())
        kernel._read_original(origin, reader, (*creation, initial), allow_ctime=True, creation_tick=cap._tick)
        cap._tick()
        for info in (os.fstat(reader), os.stat(name, dir_fd=dirfd, follow_symlinks=False)):
            require(creator._stamp(info)[:7] == creation[:7] and immutable._flags(info) == initial, "count_control_initial_flags_changed")
        require(cap not in _SETTER_USED, "count_control_seal_once"); _SETTER_USED.add(cap)
        immutable._native_set(reader, initial_flags=initial); _update(cap, flag_set=True)
        cap.seal_once(); held = _HELD[cap]
        yield cap
        cap.check(); held.close(); held = None
        closing, reader = reader, None; os.close(closing)
        with op[11]:
            owned.check(); boundary(); require(_operation(operation) is op, "count_control_operation_changed")
            transport._control_volume_binding(operation, live=True)
        require(immutable._stamp(os.stat(name, dir_fd=dirfd, follow_symlinks=False)) == _CHOICES[cap]
            and cache._inventory_names(dirfd, boundary=lambda: None) == (name,), "count_control_original_seal_changed")
        _audit_closed(origin, _CHOICES[cap])
        _ISSUED[cap] = original; _update(cap, phase="CLOSED")
    except BaseException:
        if cap is not None: _latch(cap)
        raise
    finally:
        try:
            if held is None and cap in _HELD and cap not in _ISSUED: held = _HELD[cap]
            if held is not None: held.close()
        finally:
            try: kernel._close_all([fd for fd in (writer, reader) if fd is not None])
            except BaseException:
                if cap is not None: _latch(cap)
                raise


def prepare_owned_count_claim(owned, operation, *, boundary, monotonic=time.monotonic, sleep=time.sleep):
    return _prepare_control(owned, operation, "claim", boundary=boundary, monotonic=monotonic, sleep=sleep)


def prepare_owned_count_start(owned, operation, ticket, claim, *, boundary, monotonic=time.monotonic, sleep=time.sleep):
    _transport().start_permission_binding(operation, ticket)  # Before entering the unchanged creator timer/inode path.
    return _prepare_control(owned, operation, "start", ticket=ticket, claim=claim, boundary=boundary, monotonic=monotonic, sleep=sleep)


def prepare_owned_count_final_control(owned, operation, candidate, *, role, boundary, monotonic=time.monotonic, sleep=time.sleep):
    return _prepare_control(owned, operation, role, candidate=candidate, boundary=boundary, monotonic=monotonic, sleep=sleep)


def prepare_owned_count_received(owned, operation, observation, *, boundary, monotonic=time.monotonic, sleep=time.sleep):
    return _prepare_control(owned, operation, "received", observation=observation, boundary=boundary, monotonic=monotonic, sleep=sleep)


_POLICY_SHA = hash_payload(policy())
