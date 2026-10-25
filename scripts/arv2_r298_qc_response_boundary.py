"""Offline R298 QC response-observation seam, not an operational recovery.

The sole safe entry takes an already supplied exact shared client; this module
does not construct credentials, read an environment, claim an attempt or launch
anything. Future use requires a separately authorized/frozen caller binding the
delegate to unchanged coverage._bounded_transport, source/access state, claim,
deadline and output validation. An injected callback is never that authority.

The selected bounded transport refuses non-2xx and oversized bodies before this
seam sees them; those failures retain no numeric status/body here. A one-use
entry and one delegate dispatch do not measure provider requests or write effect.
This seam is single-thread/serialized only, not a thread-safe or durable claim.
"""
from __future__ import annotations

import hashlib
import json

from research import quantconnect as shared
from scripts import arv2_r298_qc_response_evidence as evidence

SCHEMA = 'arv2-r298-qc-response-boundary-v1'
ENDPOINT = 'files/update'
PROJECT_ID = 38364439
TARGET_NAME = 'accepted_risk_order_level_input_runtime.py'
CODE_SOURCE_ID = 'Codex ARV2 R298 A5 20261024'
SOURCE_BYTES = 23055
SOURCE_SHA256 = 'c34e42d894dc88e74ce37899622a7f728bafdac9320ce2775736ba06b7ad463e'
MAX_EVIDENCE_BYTES = 64 * 1024
SOURCE_PINS = {
    'research/quantconnect.py': '7a12fdb68194ee10f6e8c3d7c0fc49c08b34166d056bd5ea2a72937dd03be373',
    'research/analyst_revisions_v2_qc/six_universe_coverage_submission.py': 'e511e04eeadb5a667b7ecee361dcac3de31d6323a0d64b1ea0b42f2879aab62b',
    'research/analyst_revisions_v2_qc/formal_qc_transport.py': 'b8c332eda827aeaee23f0dbbddcc96dbd269c82c996812a8a31fe2a4fec62ac4',
    'scripts/arv2_r298_qc_response_evidence.py': 'd8088312fac7879e3489780429c5a2e1247cd3a237ed6e331a51df134e0804f3',
}
FINITE_CODES = frozenset(('callbacks', 'entry_used', 'client', 'payload',
    'safe_entry_required', 'transport_used', 'request_binding', 'transport_refused',
    'transport_contract', 'projection_refused', 'evidence_bound', 'sink_refused',
    'sink_result', 'response_not_object', 'shared_request_refused', 'shared_result'))
_SHARED_REQUEST = shared.QuantConnectClient.request


class BoundaryError(RuntimeError):
    """Finite category only; never carries shared/provider exceptions."""
    def __init__(self, code):
        super().__init__(code if type(code) is str and code in FINITE_CODES else 'shared_request_refused')


def finite_error(error):
    if type(error) is BoundaryError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE_CODES:
            return {'code': args[0]}
    return {'code': 'shared_request_refused'}


def _require(condition, code):
    if not condition:
        raise BoundaryError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii') + b'\n'


def profile_record():
    return {'schema': SCHEMA, 'project_id': PROJECT_ID, 'endpoint': ENDPOINT,
        'target_name': TARGET_NAME, 'source_bytes': SOURCE_BYTES, 'source_sha256': SOURCE_SHA256,
        'code_source_id_sha256': hashlib.sha256(CODE_SOURCE_ID.encode('ascii')).hexdigest(),
        'selected_source_pins': dict(SOURCE_PINS), 'evidence_profile_sha256': evidence.PROFILE_SHA256,
        'max_entry_calls': 1, 'max_delegate_dispatches': 1, 'request_timeout_seconds': 30,
        'single_thread_serialized_only': True,
        'max_evidence_bytes': MAX_EVIDENCE_BYTES, 'sink_receives_immutable_bytes': True,
        'non_object_observation_stops_before_shared_parse': True,
        'non_2xx_refused_by_upstream_bounded_transport': True,
        'shared_success_true_with_nonempty_errors_semantics_preserved': True,
        'source_authentication_implemented': False, 'durable_claim_implemented': False,
        'credentials_reader_implemented': False, 'operational_caller_implemented': False,
        'deadline_implemented': False, 'current_access_accepted': False,
        'a7_authorized': False, 'retry_authority': False, 'remote_effect_known': False,
        'provider_request_count': None}


def _payload(value):
    _require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == {'projectId', 'name', 'content', 'codeSourceId'}, 'payload')
    _require(type(value['projectId']) is int and value['projectId'] == PROJECT_ID
        and type(value['name']) is str and value['name'] == TARGET_NAME
        and type(value['codeSourceId']) is str and value['codeSourceId'] == CODE_SOURCE_ID
        and type(value['content']) is str and len(value['content']) == SOURCE_BYTES
        and value['content'].isascii()
        and hashlib.sha256(value['content'].encode('ascii')).hexdigest() == SOURCE_SHA256, 'payload')
    return dict(value)  # Same exact immutable scalar values; never rewrite payload.


class OneResponseBoundary:
    """One safe shared request, one transport dispatch, one immutable observation.

    delegate(url, body, headers, timeout) is an injection seam, not an authority.
    Its operational binding must separately be the frozen bounded transport.
    sink(bytes) must durably accept exactly once and return None. No raw body,
    headers, request content or exception enters the sink or retained snapshot.
    """
    __slots__ = ('__delegate', '__sink', '__used', '__active', '__transport_used',
        '__request_body', '__snapshot', '__dispatch_count')

    def __init__(self, delegate, sink):
        _require(callable(delegate) and callable(sink), 'callbacks')
        self.__delegate, self.__sink = delegate, sink
        self.__used, self.__active, self.__transport_used = False, False, False
        self.__request_body, self.__snapshot, self.__dispatch_count = None, None, 0

    def __repr__(self):
        return '<R298QcResponseBoundary>'

    @property
    def entry_consumed(self):
        return self.__used

    @property
    def application_dispatch_count(self):
        return self.__dispatch_count

    @property
    def snapshot(self):
        return self.__snapshot  # bytes or None: immutable, no response object retained.

    def _transport(self, url, body, headers, timeout):
        _require(self.__active and self.__used, 'safe_entry_required')
        _require(not self.__transport_used, 'transport_used')
        self.__transport_used = True  # Invalid/ambiguous transport cannot be replayed.
        _require(type(url) is str and url == shared.API_BASE + '/' + ENDPOINT
            and type(body) is bytes and body == self.__request_body
            and type(headers) is dict and all(type(key) is str for key in headers)
            and set(headers) == {'Authorization', 'Timestamp', 'Content-Type'}
            and all(type(item) is str for item in headers.values())
            and headers['Content-Type'] == 'application/json'
            and type(timeout) in (int, float) and timeout == 30, 'request_binding')
        self.__dispatch_count += 1
        failure = None
        try:
            original = self.__delegate(url, body, headers, timeout)
        except BaseException:
            failure = 'transport_refused'
        if failure is not None:
            raise BoundaryError(failure)  # Outside except: no raw context/cause.
        _require(type(original) is tuple and len(original) == 2, 'transport_contract')
        status, raw = original
        _require(type(status) is int and 200 <= status < 300
            and type(raw) is bytes and len(raw) <= evidence.MAX_RESPONSE_BYTES, 'transport_contract')
        try:
            projected = evidence.project_response(status, raw)
            evidence.validate_evidence(projected)
            snapshot = _canonical(projected)
        except BaseException:
            failure = 'projection_refused'
        if failure is not None:
            raise BoundaryError(failure)
        _require(len(snapshot) <= MAX_EVIDENCE_BYTES, 'evidence_bound')
        self.__snapshot = snapshot
        try:
            returned = self.__sink(snapshot)
        except BaseException:
            failure = 'sink_refused'
        if failure is not None:
            raise BoundaryError(failure)
        _require(returned is None, 'sink_result')
        _require(projected['outcome'] == 'object', 'response_not_object')
        return original  # Exact original tuple/body: shared success checks remain unchanged.

    def __call__(self, url, body, headers, timeout):
        failure = None
        try:
            result = self._transport(url, body, headers, timeout)
        except BaseException as error:
            failure = finite_error(error)['code']
        if failure is not None:
            url = body = headers = timeout = None
            raise BoundaryError(failure)
        return result

    def observed_request(self, client, payload):
        """Return shared response in memory only, or a context-free finite error.

        A positive shared response is not verified write effect, source
        completion, access approval, permission to retry or launch authority.
        The shared parser can return success=True with nonempty errors;
        this seam does not reinterpret that as verified write success.
        Only finite_error(error) may be persisted: traceback inspection is
        not a process-wide secrecy guarantee for supplied clients/callbacks.
        """
        failure = None
        try:
            _require(not self.__used, 'entry_used')
            self.__used = True
            _require(type(client) is shared.QuantConnectClient
                and 'request' not in vars(client) and type(client).request is _SHARED_REQUEST
                and type(client._base_url) is str and client._base_url == shared.API_BASE
                and client._transport is self
                and type(client._timeout) in (int, float) and client._timeout == 30, 'client')
            copied = _payload(payload)
            # Match the unchanged shared serializer. A changed body refuses
            # before the delegate and no request bytes are persisted.
            self.__request_body = json.dumps(copied).encode('utf-8')
            self.__active = True
            result = client.request(ENDPOINT, copied)
            _require(self.__dispatch_count == 1 and self.__snapshot is not None
                and type(result) is dict and result.get('success') is True, 'shared_result')
        except BaseException as error:
            failure = finite_error(error)['code']
        finally:
            self.__active = False
            self.__request_body = None
        if failure is not None:
            client = payload = copied = result = None
            raise BoundaryError(failure)
        return result
