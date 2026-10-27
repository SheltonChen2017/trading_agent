"""Source-only count operator core; unregistered production paths fail closed.

HTTP observations are issued only by the fixed original GET path after a
genuine claim and START. No public payload, status or completion flag can mint
wire truth, chunk closure, source admission or a budget settlement witness.
"""
from contextlib import contextmanager
import _thread
import importlib
import json
import http.client
from pathlib import Path
import re
import time
from functools import wraps

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_dated_class_reference as references
from scripts import short_interest_count_durable_budget as accounting
from scripts import short_interest_recovery_transport as wire
from scripts import capture_short_interest_native_reported_count_round as legacy
from scripts import short_interest_recovery_diagnostics as diagnostics
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain

ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
PROTOCOL_SHA256, SOURCE_AUTHORITY_SHA256 = "PENDING", "PENDING"
MAXIMUM_INFLIGHT, MAXIMUM_SECONDS, MAXIMUM_RESPONSE_BYTES = 8, 3600, 2 * 1024 ** 2
FINAL_ROLES = ("inventory", "provisional", "closed", "manifest")
_OPERATIONS, _FAILED, _OBSERVATIONS, _TERMINALS = {}, set(), {}, {}
_CANDIDATES, _RESPONSE_CAPS, _FINAL_CAPS, _WINDOWS = {}, {}, {}, {}
_VOLUMES, _RECEIVED_CAPS = {}, {}
_DRAINED = {}
_DOWNGRADES, _DRAIN_ORIGINS = {}, {}
_OBS_COMPLETED = {}
_WIRE_RESULTS = {}
_CODES = frozenset("""count_operator_factory_required count_operator_registration_pending
count_operator_source_not_registered count_operator_storage_not_registered
count_operator_binding_changed count_operator_latched_failure count_operator_not_live
count_operator_ticket_changed count_operator_claim_changed count_operator_START_changed
count_operator_dispatch_reused count_operator_inflight_cap count_operator_clock_refused
count_operator_window_exhausted count_operator_response_refused count_operator_echo_refused
count_operator_observation_required count_operator_observation_changed count_operator_final_incomplete
count_operator_final_role count_operator_not_closed count_operator_terminal_changed
count_operator_candidate_required count_operator_candidate_changed count_operator_retry_chain_refused
count_operator_retry_backoff_refused count_operator_wire_origin_refused""".split())


class CountTransportRefusal(ValueError): pass


def require(value, code):
    if not value: raise CountTransportRefusal("REFUSED: " + code)


def authority():
    return {"source_only": True, "source_admitted": False, "denominator_admitted": False,
        "actual_input_execution_admitted": False, "ready_for_backtest": False,
        "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


def policy():
    return {"schema": "si-durable-count-operator-policy-v1", "source_authority_sha256": SOURCE_AUTHORITY_SHA256,
        "root": str(ROOT), "maximum_inflight": MAXIMUM_INFLIGHT, "maximum_seconds": MAXIMUM_SECONDS,
        "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES, "hidden_retries": 0,
        "source_request": "original_native_query_descriptor_SHA_excludes_Authorization_and_secret",
        "HTTP": "fixed_protected_GET_at_most_reserved_bytes_prefix_preserved_200_JSON_only_404_negative",
        "body_limit": "no_MAX_plus_one_MAX_requires_strict_original_Content_Length_and_successful_close",
        "retry": "classification_only_allowlisted_statusless_open_transients_each_new_ticket_and_START",
        "retry_chain": "original_same_query_previous_completed_OPEN_transient_only_no_parallel_position_2_10_seconds",
        "final_roles": list(FINAL_ROLES), "closure": "original_outer_context_exit_and_postclose_witness_only",
        "authority": authority()}


def failure_summary(error):
    if type(error) is CountTransportRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = (next((name for name in _CODES if args[0] == "REFUSED: " + name), None)
            if type(args) is tuple and len(args) == 1 and type(args[0]) is str else None)
        return {"category": "local_contract_refusal", "contract_code": code, "errno_name": None}
    return diagnostics.fixed_local_failure(error)


def _controls(): return importlib.import_module("scripts.short_interest_count_control_custody")
def _responses(): return importlib.import_module("scripts.short_interest_count_response_custody")
def _coordinator(): return importlib.import_module("scripts.capture_short_interest_durable_counts")
def _volume_module(): return importlib.import_module("scripts.short_interest_count_response_volume")


def _registered(root, budget, head, remote, manifest):
    require(root == ROOT and root.resolve() == root and Path.cwd().resolve() == ROOT
        and type(budget) is accounting.DurableCountBudget
        and all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) for value in (head, remote))
        and type(manifest) is dict and bool(manifest)
        and all(type(key) is str and type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in manifest.items())
        and re.fullmatch(r"[0-9a-f]{64}", SOURCE_AUTHORITY_SHA256)
        and re.fullmatch(r"[0-9a-f]{64}", PROTOCOL_SHA256)
        and hash_payload(policy()) == PROTOCOL_SHA256
        and (MAXIMUM_INFLIGHT, MAXIMUM_SECONDS, MAXIMUM_RESPONSE_BYTES) == (8, 3600, 2097152),
        "count_operator_registration_pending")


@contextmanager
def _registered_source_scope(root, budget, head, remote, manifest):
    # A real source/code/claim policy is a separate future registration. This
    # bounded core never adopts caller contexts, callbacks or a complete flag.
    raise CountTransportRefusal("REFUSED: count_operator_source_not_registered")
    yield


def _source_check(lease):
    return _coordinator().source_lease_live_binding(lease)


def _source_closed(lease):
    return _coordinator().source_lease_terminal_binding(lease)


def _closed_storage(operation, bundle):
    # Only a registered storage implementation may supply the complete FINAL
    # recursive member/capability set and original closed-volume witness.
    raise CountTransportRefusal("REFUSED: count_operator_storage_not_registered")


def _latch(operation):
    if type(operation) is CountCaptureOperation: _FAILED.add(operation)


def _permanent(function):
    @wraps(function)
    def checked(self, *args, **kwargs):
        try: return function(self, *args, **kwargs)
        except BaseException: _latch(self); raise
    return checked


def _window(operation):
    began, previous = _WINDOWS[operation]
    now = time.monotonic()
    require(type(now) in (int, float) and 0 <= began <= previous <= now <= 2 ** 53,
        "count_operator_clock_refused")
    require(now - began <= MAXIMUM_SECONDS, "count_operator_window_exhausted")
    _WINDOWS[operation] = began, now


def bind_registered_operation(source_lease, budget):
    """Only Main's exact registered original source factory can bind an op."""
    coordinator = _coordinator()
    require(type(source_lease) is coordinator.CountSourceLease
        and type(budget) is accounting.DurableCountBudget, "count_operator_source_not_registered")
    source = coordinator.source_lease_live_binding(source_lease)
    require(type(source) is tuple and len(source) == 16 and source[0] is source_lease
        and source[1] == ROOT and source[4] is budget.plan and source[5] is budget
        and source[9] == SOURCE_AUTHORITY_SHA256 and source[10] == PROTOCOL_SHA256
        and type(source[11]) is type(ROOT) and source[11].is_absolute(), "count_operator_registration_pending")
    manifest = dict(source[7]); _registered(source[1], budget, source[2], source[3], manifest)
    value = object.__new__(CountCaptureOperation)
    chunk = budget.public_summary()["current_chunk"]
    registration = hash_payload({"plan_sha256": source[4].sha256, "chunk": chunk,
        "protocol_sha256": PROTOCOL_SHA256, "head": source[2], "remote": source[3],
        "code_identity_sha256": source[8], "code_manifest_sha256": hash_payload(manifest)})
    anchor = (value, budget, source[4], budget.budget_identity, chunk, PROTOCOL_SHA256, registration,
        source[1], source[2], source[3], source[4].sha256, source[12], source_lease, object())
    value._anchor = value._identity = anchor
    _OPERATIONS[value] = anchor, ("LIVE", (), (), (), None, None)
    _RESPONSE_CAPS[value], _RECEIVED_CAPS[value], _FINAL_CAPS[value] = (), (), ()
    _WINDOWS[value] = source[14], source[14]
    return value


def operation_binding(operation):
    """Original14: op,budget,plan,budgetid,chunk,protocol,registration,root,
    HEAD,remote,planSHA,RLock,sourcelease,nonce. Read-only worker authentication.
    """
    record = _OPERATIONS.get(operation) if type(operation) is CountCaptureOperation else None
    try:
        anchor = object.__getattribute__(operation, "_anchor")
        require(type(record) is tuple and len(record) == 2 and record[0] is anchor
            and object.__getattribute__(operation, "_identity") is anchor
            and type(anchor) is tuple and len(anchor) == 14 and anchor[0] is operation
            and operation not in _FAILED, "count_operator_binding_changed")
        with anchor[11]:
            require(anchor[5] == PROTOCOL_SHA256 and hash_payload(policy()) == anchor[5],
                "count_operator_binding_changed")
            return anchor
    except BaseException:
        _latch(operation); raise


def active_operation_binding(operation):
    anchor = operation_binding(operation)
    with anchor[11]:
        # Fixed budget native lock permits immutable worker authentication;
        # coordinator-only public mutation/read APIs are never called here.
        with accounting._lock(anchor[1]):
            plan, state = anchor[1]._guard(owner=False)
            require(_OPERATIONS[operation][1][0] == "LIVE" and plan is anchor[2]
                and anchor[1]._anchor[3] is anchor[3] and state[0] == anchor[4], "count_operator_not_live")
        return anchor


def _update(operation, state):
    anchor = operation_binding(operation)
    _OPERATIONS[operation] = anchor, state


def _query_for_ticket(ticket):
    original = accounting.active_ticket_binding(ticket)
    plan = original[2]; source_plan = plan._parts[1]._parts[1].query_plan
    selected = references.freeze_native_class_query_plan(source_plan._matrix,
        mode="explicit_anchors", selected_query_ordinals=(original[6],))
    query = next(selected.iter_queries())
    require(query.to_payload()["request_sha256"] == original[8], "count_operator_ticket_changed")
    return query


def _clock(): return legacy._utc_now()


class _WireResult:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountTransportRefusal("REFUSED: count_operator_wire_origin_refused")
    def __repr__(self): return "<fixed count WireResult redacted>"


def _wire_result_binding(value, opener, request):
    original = _WIRE_RESULTS.get(value) if type(value) is _WireResult else None
    require(type(original) is tuple and len(original) == 10 and original[0] is value
        and value._anchor is value._identity is original and original[1] is opener and original[2] is request,
        "count_operator_wire_origin_refused")
    return original


def _bounded_get(opener, request, maximum):
    """One GET; never request a byte outside the original page reservation.

    Returned bytes, including a genuine IncompleteRead partial, remain in an
    opaque private result on read/close failure. They never become qualified
    source or retry evidence. This changes no historical transport helper.
    """
    wire._require_capture_platform()
    require(type(maximum) is int and 1 <= maximum <= MAXIMUM_RESPONSE_BYTES,
        "count_operator_response_refused")
    response, status, media, failure = None, None, None, None
    phase, parts, length, positive, preserve = "open", [], 0, False, False
    try:
        response = opener.open(request, timeout=30); phase = "response"
        status = wire._status(response.status)
        if status != 200:
            raise wire.RecoveryTransportFailure("http_not_200", phase=phase, failure_class="http_status", status=status)
        media = response.headers.get("Content-Type", "")
        if type(media) is not str or len(media) > 256 or wire._JSON_MEDIA.fullmatch(media) is None:
            raise wire.RecoveryTransportFailure("content_type", phase=phase, failure_class="content_type", status=status)
        declared = response.headers.get("Content-Length")
        transfer = response.headers.get("Transfer-Encoding")
        if declared is not None:
            if (type(declared) is not str or re.fullmatch(r"0|[1-9][0-9]{0,9}", declared) is None
                    or int(declared) > maximum or transfer is not None):
                raise wire.RecoveryTransportFailure("response_size_limit", phase=phase, failure_class="response_size", status=status)
            declared = int(declared)
        phase = "read"; eof = False
        while length < maximum and (declared is None or length < declared):
            requested = min(65536, maximum - length, maximum if declared is None else declared - length)
            piece = response.read(requested)
            if type(piece) is not bytes:
                preserve = True
                raise wire.RecoveryTransportFailure("response_contract_refused", phase=phase, failure_class="response_contract", status=status)
            # A conforming original HTTPResponse never returns more than the
            # requested bound. Preserve a violating return, and refuse it.
            if piece: parts.append(piece); length += len(piece)
            else: eof = True; break
            if len(piece) > requested:
                preserve = True
                raise wire.RecoveryTransportFailure("response_size_limit", phase=phase, failure_class="response_size", status=status)
        complete = (declared is not None and length == declared) or (declared is None and eof and length < maximum)
        if not complete:
            preserve = True
            raise wire.RecoveryTransportFailure("response_size_limit" if length == maximum else "response_contract_refused",
                phase=phase, failure_class="response_size" if length == maximum else "response_contract", status=status)
        positive = True
    except wire.RecoveryTransportFailure as error:
        failure = error
        if status is None: status = error.http_status
        if phase == "read": preserve = True
    except BaseException as error:
        if type(error) is http.client.IncompleteRead:
            partial = object.__getattribute__(error, "__dict__").get("partial")
            if type(partial) is bytes:
                parts.append(partial); length += len(partial)
        if isinstance(error, wire.urllib.error.HTTPError):
            if response is None: response, status = error, wire._http_error_status(error)
            failure = wire.RecoveryTransportFailure("http_not_200", phase=phase, failure_class="http_status", status=status)
        else: failure = wire._network_failure(error, phase, status)
        preserve = preserve or phase == "read"
    finally:
        if response is not None:
            try: response.close()
            except BaseException as error:
                preserve = True; positive = False
                if failure is None: failure = wire._network_failure(error, "response", status)
    raw = b"".join(parts) if parts or positive else None
    if failure is not None: positive = False
    value = object.__new__(_WireResult)
    anchor = value, opener, request, raw, media, status, None if failure is None else tuple(failure.diagnostic().items()), positive, preserve, object()
    value._anchor = value._identity = anchor; _WIRE_RESULTS[value] = anchor
    return value


def _check_position_chain(operation, ticket, state):
    """Dispatch gate, independent of the coordinator's scheduling decisions."""
    original = accounting.active_ticket_binding(ticket)
    previous = tuple(item for item in state[1] if accounting.ticket_binding(item)[5] == original[5])
    require(not any(accounting.ticket_binding(item)[5] == original[5] for item in state[2]),
        "count_operator_retry_chain_refused")
    if not previous: return
    prior = previous[-1]
    obs = next((value for value in state[3] if type(value) is HttpObservation
        and _OBSERVATIONS.get(value, (None, None, None))[2] is prior), None)
    require(obs is not None and len(previous) < 3, "count_operator_retry_chain_refused")
    bound = http_observation_binding(obs); detail = dict(bound[13] or ())
    require(accounting.ticket_binding(prior)[8] == original[8] and bound[8] is True
        and bound[9] is None and bound[10] is None and set(detail) == {
            "code", "phase", "failure_class", "http_status", "retryable", "errno_name"}
        and detail["code"] == "network_failure" and detail["phase"] == "open"
        and type(detail["failure_class"]) is str and detail["failure_class"] in wire._TRANSIENT_CLASSES
        and detail["http_status"] is None and detail["retryable"] is True,
        "count_operator_retry_chain_refused")
    completed = _OBS_COMPLETED.get(obs); now = _WINDOWS[operation][1]
    require(type(completed) in (int, float) and completed <= now
        and now - completed >= (2 if len(previous) == 1 else 10), "count_operator_retry_backoff_refused")


class HttpObservation:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountTransportRefusal("REFUSED: count_operator_observation_required")
    def __repr__(self): return "<HttpObservation redacted>"


class UnqualifiedHttpObservation:
    """Already-dispatched wire bytes retained in RAM; no publication authority."""
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountTransportRefusal("REFUSED: count_operator_observation_required")
    def __repr__(self): return "<UnqualifiedHttpObservation redacted; preservation required>"


def drained_http_observation_binding(observation):
    """Negative preservation only. Never accepted by qualified custody/reader."""
    original = _DRAINED.get(observation) if type(observation) is UnqualifiedHttpObservation else None
    require(type(original) is tuple and len(original) == 16 and original[0] is observation
        and observation._anchor is observation._identity is original, "count_operator_observation_changed")
    record = _OPERATIONS.get(original[1])
    require(type(record) is tuple and record[0][0] is original[1]
        and any(original[2] is ticket for ticket in record[1][1]), "count_operator_observation_changed")
    if observation in _DRAIN_ORIGINS:
        source, source_tuple, anchor = _DRAIN_ORIGINS[observation]
        require(type(source) is HttpObservation and _OBSERVATIONS.get(source) is source_tuple
            and source._anchor is source._identity is source_tuple
            and record[0] is anchor and original[1]._anchor is original[1]._identity is anchor
            and original[1] in _FAILED and _DOWNGRADES.get(source) is observation
            and all(left is right for left, right in zip(original[1:15], source_tuple[1:15])),
            "count_operator_observation_changed")
    return original


def downgrade_http_observation_for_preservation(observation):
    """Retain a prior genuine result after failure; grants no persistence authority.

    This deliberately authenticates the original registry and operation anchor,
    not the failed qualification path. It never reopens a source, changes a
    failure latch, or accepts caller bytes/status/claims.
    """
    original = _OBSERVATIONS.get(observation) if type(observation) is HttpObservation else None
    require(type(original) is tuple and len(original) == 16 and original[0] is observation
        and observation._anchor is observation._identity is original, "count_operator_observation_changed")
    operation = original[1]; record = _OPERATIONS.get(operation)
    require(type(record) is tuple and len(record) == 2 and type(record[0]) is tuple
        and len(record[0]) == 14 and record[0][0] is operation
        and operation._anchor is operation._identity is record[0], "count_operator_binding_changed")
    anchor = record[0]
    with anchor[11]:
        require(_OPERATIONS.get(operation)[0] is anchor and operation in _FAILED
            and any(item is observation for item in _OPERATIONS[operation][1][3])
            and any(item is original[2] for item in _OPERATIONS[operation][1][1]),
            "count_operator_observation_changed")
        if observation in _DOWNGRADES:
            value = _DOWNGRADES[observation]; drained_http_observation_binding(value); return value
        value = object.__new__(UnqualifiedHttpObservation)
        parts = (value, *original[1:15], object())
        value._anchor = value._identity = parts
        _DRAINED[value] = parts
        _DRAIN_ORIGINS[value] = observation, original, anchor
        _DOWNGRADES[observation] = value
        drained_http_observation_binding(value)
        return value


def http_observation_binding(observation):
    original = _OBSERVATIONS.get(observation) if type(observation) is HttpObservation else None
    require(type(original) is tuple and len(original) == 16 and original[0] is observation
        and observation._anchor is observation._identity is original, "count_operator_observation_changed")
    operation_binding(original[1]); accounting.ticket_binding(original[2])
    return original


def received_custody_binding(capability):
    """Typed positive-body or negative-receipt authentication, never a cast."""
    responses = _responses()
    if type(capability) is responses.CountResponseCustody:
        return responses.response_binding(capability)
    controls = _controls()
    if hasattr(controls, "CountReceived") and type(capability) is controls.CountReceived:
        return controls.received_binding(capability)
    raise CountTransportRefusal("REFUSED: count_operator_observation_changed")


class CountCaptureOperation:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountTransportRefusal("REFUSED: count_operator_factory_required")
    def __repr__(self): return "<CountCaptureOperation redacted>"

    @_permanent
    def bind_volume(self, volume):
        anchor = active_operation_binding(self)
        with anchor[11]:
            module = _volume_module()
            require(type(volume) is module.CountResponseVolume and self not in _VOLUMES,
                "count_operator_storage_not_registered")
            bound = module.volume_binding(volume, live=True)
            source = _coordinator().source_lease_binding(anchor[12])
            require(type(bound) is tuple and len(bound) == 9 and bound[0] is volume and bound[1] is self
                and bound[2] / "capture" == source[11] and bound[3] == anchor[4] and bound[4] == anchor[10]
                and bound[5] == anchor[5], "count_operator_storage_not_registered")
            _VOLUMES[self] = volume

    @_permanent
    def dispatch(self, ticket, claim, start):
        """Exactly one protected original GET; classification grants no retry."""
        anchor = active_operation_binding(self)
        controls = _controls(); started = controls.start_binding(start); claimed = controls.claim_binding(claim)
        original = accounting.active_ticket_binding(ticket)
        require(len(claimed) == len(started) == 12 and claimed[0] is claim and claimed[1] is self
            and claimed[2] is anchor[1] and claimed[3] is anchor[2] and claimed[4] == anchor[4]
            and claimed[5] == anchor[5] and claimed[7] == anchor[6]
            and started[0] is start and started[1] is self and started[2] is ticket and started[3] is claim
            and started[5] == original[8] and started[6] == anchor[5] and started[7] == claimed[6]
            and original[1] is anchor[1] and original[2] is anchor[2] and original[3] == anchor[4],
            "count_operator_START_changed")
        with anchor[11]:
            _window(self)
            state = _OPERATIONS[self][1]
            require(not any(ticket is previous for previous in state[1]), "count_operator_dispatch_reused")
            require(len(state[2]) < MAXIMUM_INFLIGHT, "count_operator_inflight_cap")
            _check_position_chain(self, ticket, state)
            _update(self, (state[0], (*state[1], ticket), (*state[2], ticket), state[3], state[4], state[5]))
        raw = media = status = None; invoked = False; detail = None
        try:
            with anchor[11]:
                require(self not in _FAILED, "count_operator_latched_failure")
                _source_check(anchor[12])
            secret = read_named_keychain("massive")
            require(type(secret) is KeychainSecret, "count_operator_response_refused")
            query = _query_for_ticket(ticket)
            request = legacy._wire_request(query, secret)
            opener = legacy.transport.build_protected_opener(); legacy.transport._opener(opener)
            with anchor[11]:
                require(self not in _FAILED, "count_operator_latched_failure")
                _window(self); _source_check(anchor[12]); controls.start_binding(start); controls.claim_binding(claim)
                invoked = True  # Original outbound-attempt acceptance precedes unlocking.
            result = _wire_result_binding(_bounded_get(opener, request, MAXIMUM_RESPONSE_BYTES), opener, request)
            raw, media, status, detail = result[3:7]
            if result[8]: _latch(self)
            if result[7]:
                require(type(raw) is bytes and len(raw) <= MAXIMUM_RESPONSE_BYTES and type(media) is str
                    and type(status) is int and status == 200 and legacy._json_media(media), "count_operator_response_refused")
                require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "count_operator_echo_refused")
        except wire.RecoveryTransportFailure as error:
            raw = media = None; status = error.http_status
            detail = tuple(error.diagnostic().items())
        except BaseException as error:
            _latch(self); detail = tuple(failure_summary(error).items())
        finally:
            with anchor[11]:
                state = _OPERATIONS[self][1]
                # Drain bookkeeping against the ORIGINAL record even after a
                # permanent failure; a refused operation cannot suppress cleanup.
                _OPERATIONS[self] = anchor, (state[0], state[1], tuple(item for item in state[2] if item is not ticket), state[3], state[4], state[5])
        received = None
        try:
            received = _clock()
            require(legacy.parallel.clock(started[8]) <= legacy.parallel.clock(received), "count_operator_clock_refused")
        except BaseException as error:
            _latch(self); detail = tuple(failure_summary(error).items())
        with anchor[11]:
            if self not in _FAILED:
                try: _window(self); _source_check(anchor[12]); _window(self)
                except BaseException as error:
                    _latch(self); detail = tuple(failure_summary(error).items())
            qualified = self not in _FAILED
            value = object.__new__(HttpObservation if qualified else UnqualifiedHttpObservation)
            descriptor = {"request_sha256": original[8], "START_sha256": started[4], "protocol_sha256": anchor[5],
                "http_invoked": invoked, "http_status": status, "body_sha256": None if raw is None else hash_bytes(raw),
                "body_bytes": None if raw is None else len(raw), "received_at": received, "diagnostic": detail}
            parts = (value, self, ticket, claim, start, original[8], started[4], anchor[5], invoked,
                status, raw, media, received, detail, hash_payload(descriptor), object())
            value._anchor = value._identity = parts
            if qualified:
                _OBSERVATIONS[value] = parts
                _OBS_COMPLETED[value] = _WINDOWS[self][1]
            else: _DRAINED[value] = parts
            state = _OPERATIONS[self][1]
            _OPERATIONS[self] = anchor, (state[0], state[1], state[2], (*state[3], value), state[4], state[5])
            return value

    @_permanent
    def accept_closed_response(self, capability):
        anchor = active_operation_binding(self)
        with anchor[11]:
            original = _responses().response_binding(capability)
            require(type(original) is tuple and original[0] is capability and original[1] is self
                and any(original[3] is item for item in _OPERATIONS[self][1][3])
                and not any(original[2] is received_custody_binding(item)[2]
                    for item in _RESPONSE_CAPS[self]), "count_operator_observation_changed")
            _RESPONSE_CAPS[self] = (*_RESPONSE_CAPS[self], capability)

    @_permanent
    def accept_received_control(self, capability):
        anchor = active_operation_binding(self)
        with anchor[11]:
            original = _controls().received_binding(capability)
            require(type(original) is tuple and len(original) == 12 and original[0] is capability
                and original[1] is self and any(original[3] is obs for obs in _OPERATIONS[self][1][3])
                and not any(_controls().received_binding(cap)[2] is original[2] for cap in _RECEIVED_CAPS[self]),
                "count_operator_observation_changed")
            _RECEIVED_CAPS[self] = (*_RECEIVED_CAPS[self], capability)

    @_permanent
    def freeze_provisional_root(self):
        anchor = active_operation_binding(self)
        with anchor[11]:
            state = _OPERATIONS[self][1]; roster = anchor[1].current_tickets()
            require(not state[2] and len(state[3]) == len(roster) == len(_RECEIVED_CAPS[self]) > 0,
                "count_operator_final_incomplete")
            observations = tuple(next((item for item in state[3] if http_observation_binding(item)[2] is ticket), None)
                for ticket in roster)
            require(all(item is not None for item in observations), "count_operator_final_incomplete")
            caps = tuple((next((cap for cap in _RECEIVED_CAPS[self] if _controls().received_binding(cap)[2] is ticket), None),
                next((cap for cap in _RESPONSE_CAPS[self] if _responses().response_binding(cap)[2] is ticket), None))
                for ticket in roster)
            for obs, pair in zip(observations, caps):
                received = _controls().received_binding(pair[0]); observed = http_observation_binding(obs)
                require(received[3] is obs and received[10] == anchor[5], "count_operator_observation_changed")
                if type(observed[10]) is bytes and observed[10]:
                    require(pair[1] is not None and _responses().response_binding(pair[1])[3] is obs,
                        "count_operator_final_incomplete")
                else: require(pair[1] is None, "count_operator_observation_changed")
            covered = tuple(sorted({accounting.ticket_binding(ticket)[5] for ticket, obs in zip(roster, observations)
                if http_observation_binding(obs)[9] == 200 and type(http_observation_binding(obs)[10]) is bytes
                and len(http_observation_binding(obs)[10]) > 0}))
            require(covered == anchor[2].chunk_positions(anchor[4]), "count_operator_final_incomplete")
            metadata = {"registration_sha256": anchor[6], "plan_sha256": anchor[10], "chunk": anchor[4],
                "ticket_sha256s": [accounting.ticket_binding(ticket)[9] for ticket in roster],
                "observation_sha256s": [http_observation_binding(obs)[14] for obs in observations],
                "covered_positions": list(covered), "authority": authority()}
            raw = canonical_json(metadata).encode(); value = object.__new__(ProvisionalRootClosureCandidate)
            original = value, self, anchor, roster, observations, caps, covered, hash_bytes(raw), raw
            value._anchor = value._identity = original; _CANDIDATES[value] = original
            return value

    @_permanent
    def accept_final_control(self, capability):
        anchor = active_operation_binding(self)
        with anchor[11]:
            original = _controls().final_control_binding(capability)
            require(original[0] is capability and original[1] is self
                and original[2] == FINAL_ROLES[len(_FINAL_CAPS[self])], "count_operator_final_role")
            _FINAL_CAPS[self] = (*_FINAL_CAPS[self], capability)

    def bind_closed_storage(self, bundle):
        anchor = active_operation_binding(self)
        with anchor[11]:
            state = _OPERATIONS[self][1]
            require(state[4] is None, "count_operator_terminal_changed")
            # This fixed semantic validator is intentionally unavailable until
            # the actual storage/control policy is separately registered.
            _closed_storage(self, bundle)
            _update(self, (*state[:4], bundle, state[5]))

    def closed_chunk(self):
        anchor = operation_binding(self)
        with anchor[11]:
            state = _OPERATIONS[self][1]
            require(state[0] == "CLOSED" and state[5] is not None, "count_operator_not_closed")
            return state[5]


class ProvisionalRootClosureCandidate:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountTransportRefusal("REFUSED: count_operator_candidate_required")


def provisional_candidate_binding(candidate):
    original = _CANDIDATES.get(candidate) if type(candidate) is ProvisionalRootClosureCandidate else None
    require(type(original) is tuple and len(original) == 9 and original[0] is candidate
        and candidate._anchor is candidate._identity is original, "count_operator_candidate_changed")
    require(operation_binding(original[1]) is original[2]
        and hash_bytes(original[8]) == original[7], "count_operator_candidate_changed")
    for obs in original[4]: http_observation_binding(obs)
    for received, pair in original[5]:
        _controls().received_binding(received)
        if pair is not None: _responses().response_binding(pair)
    return original


def volume_for_operation(operation):
    operation_binding(operation)
    volume = _VOLUMES.get(operation)
    require(volume is not None and _volume_module().volume_binding(volume)[1] is operation,
        "count_operator_storage_not_registered")
    return volume


def _control_volume_binding(operation, *, live=False):
    volume = volume_for_operation(operation)
    return _volume_module().volume_binding(volume, live=live)


def _control_directory(operation, role, ticket=None):
    anchor = operation_binding(operation)
    source = _coordinator().source_lease_binding(anchor[12]); base = source[11]
    if role == "claim": return base.parent / "claim"
    if role in {"start", "received"}:
        original = accounting.ticket_binding(ticket)
        require(original[1] is anchor[1] and original[3] == anchor[4], "count_operator_ticket_changed")
        return base / ("starts" if role == "start" else "received") / f"{original[4]:06d}"
    require(type(role) is str and role in FINAL_ROLES, "count_operator_final_role")
    return base / ("final_" + role)


def _final_control_payload(operation, candidate, role):
    anchor = active_operation_binding(operation); original = provisional_candidate_binding(candidate)
    require(type(role) is str and role in FINAL_ROLES, "count_operator_final_role")
    require(original[1] is operation and role == FINAL_ROLES[len(_FINAL_CAPS[operation])], "count_operator_final_role")
    previous = tuple(_controls().final_control_binding(cap) for cap in _FINAL_CAPS[operation])
    payload = (json.loads(original[8]) if role == "inventory" else
        {"previous_control_sha256s": [row[3] for row in previous]})
    if role == "manifest": payload = {"members": _coordinator().final_member_rows(operation, candidate)}
    raw = canonical_json({"schema": "si-count-final-control-v1", "role": role, "chunk": anchor[4],
        "operator_protocol_sha256": anchor[5], "registration_sha256": anchor[6],
        "candidate_sha256": original[7], "payload": payload,
        "source_admitted": False, "budget_release_authority": False}).encode()
    require(len(raw) <= MAXIMUM_RESPONSE_BYTES, "count_operator_final_incomplete")
    return raw


@contextmanager
def open_registered_operation(root, *, budget, runtime_head, actual_remote, complete_code_manifest):
    _registered(root, budget, runtime_head, actual_remote, complete_code_manifest)
    # Main owns the genuine SourceLease and all outer context exits. A generic
    # context/callback supplied through this lower-level API is never adopted.
    raise CountTransportRefusal("REFUSED: count_operator_source_not_registered")
    yield


def _terminal_binding(operation, candidate):
    provisional_candidate_binding(candidate)
    return _coordinator().terminal_chunk_binding(operation, candidate)
