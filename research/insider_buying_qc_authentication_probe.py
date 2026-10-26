"""One official QC authentication POST; no account, data, project or job API.

Only a strict boolean auth-status response may be retained. Credentials and
their transient protocol signatures are never printed, persisted or given a
persistent fingerprint. Authentication is not an entitlement/readiness proof.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import errno
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time
import weakref

from research import quantconnect as qc
from research import insider_buying_pilot_sec_parent_capture as publication
from research import insider_buying_sec_feed_directory_stopped_controls as controls
from research import insider_buying_sec_recovery_v4_capture as privacy
from research import insider_buying_pilot_sec_parent_audit_runner as sources
from research.insider_buying_sec_selected_parent_runner import _selected_framing, _strict_selected_response
from research.insider_buying_sec_complete_acquisition import SecHttpResult


SCHEMA = "insider-qc-authentication-probe-v1"
SELF_PATH = "research/insider_buying_qc_authentication_probe.py"
TEST_PATH = "tests/test_insider_buying_qc_authentication_probe.py"
LANE_ROOT, LANE_BRANCH = sources.LANE_ROOT, sources.LANE_BRANCH
ARTIFACT_PARTS = ("artifacts", "insider_buying", "qc_authentication_probe_v1")
AUDIT_ID = "ib-qc-authentication-20261025-once"
URL = "https://www.quantconnect.com/api/v2/authenticate"
HOST, PATH = "www.quantconnect.com", "/api/v2/authenticate"
EMPTY_CACHE_PREFIX = "/var/empty/insider-qc-authentication-no-bytecode"
MAX_BODY_BYTES, MAX_CONTROL_BYTES = 16 * 1024, 256 * 1024
WALL_SECONDS = 15
LOCK_BYTES = b"INSETF-QC-authentication-exclusive-one-POST-v1\n"
ENV_NAMES = ("QC_USER_ID", "QC_API_TOKEN")
_SHA, _HEAD = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[0-9a-f]{40}\Z")
_TOKEN, _CONTEXTS = object(), weakref.WeakKeyDictionary()
_raw, _sha = publication._raw, publication._sha


class AuthenticationProbeError(ValueError):
    """Fixed codes only; no credential, header or remote-exception text."""


class _DeadlineExceeded(Exception):
    pass


@dataclass(frozen=True)
class AuthenticationHttpResult:
    status: int
    headers: tuple = field(repr=False)
    body: bytes = field(repr=False)


def _need(value, code):
    if not value:
        raise AuthenticationProbeError(code)


def _authority():
    return {**publication.audit._AUTHORITY, "account_details_requested": False,
        "platform_data_requested": False, "storage_entitlement_established": False,
        "notebook_access_established": False, "backtesting_ready": False}


def _decode(raw):
    try:
        return controls._decode_control(raw)
    except controls.StoppedControlError:
        raise AuthenticationProbeError("own_control_codec_refused") from None


def parse_authentication_status(raw):
    """Documented success boolean; optional EMPTY errors/warnings only.

    Warnings is a conservative empty-field compatibility allowance, not an
    assertion that the authentication documentation requires this property.
    Unknown fields and even an error string are not account-data permission.
    """
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES, "auth_body_bound")
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "auth_duplicate_key")
            result[key] = value
        return result
    def no_number(_):
        raise AuthenticationProbeError("auth_numeric_field_refused")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=pairs, parse_int=no_number,
            parse_float=no_number, parse_constant=no_number)
        _need(type(value) is dict and "success" in value and set(value) <= {"success", "errors", "warnings"}
            and type(value["success"]) is bool, "auth_status_schema_refused")
        _need(all(type(value[k]) is list and not value[k] for k in ("errors", "warnings") if k in value),
            "auth_nonempty_or_untyped_messages_refused")
        return {"schema": SCHEMA + "/status", "success": value["success"],
            "optional_empty_fields": [k for k in ("errors", "warnings") if k in value],
            "authentication_is_not_entitlement": True}
    except AuthenticationProbeError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise AuthenticationProbeError("auth_status_schema_refused") from None


def _scope():
    return {"schema": SCHEMA + "/scope", "audit_id": AUDIT_ID, "method": "POST", "url": URL,
        "payload": {}, "maximum_transport_invocations": 1, "maximum_from_env_invocations": 1,
        "environment_names": list(ENV_NAMES), "maximum_body_bytes": MAX_BODY_BYTES,
        "absolute_wall_seconds": WALL_SECONDS, "redirects": False, "retries": False,
        "proxies": False, "fallbacks": False, "non200_body_read": False,
        "only_strict_auth_status_may_be_retained": True, "credential_fingerprint_persisted": False,
        "transient_documented_signature_only": True, "authority": _authority()}


def _source_identity(value, root):
    _need(type(value) is dict and set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
        and value["root"] == str(root) and value["branch"] == LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and _HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and {SELF_PATH, TEST_PATH} <= set(value["source_sha256"])
        and 1 <= len(value["source_sha256"]) <= 2048
        and value["source_inventory_sha256"] == _sha(_raw(value["source_sha256"])), "source_identity_refused")
    for name, digest in value["source_sha256"].items():
        _need(type(name) is str and 0 < len(name) <= 512 and not name.startswith("/")
            and all(p not in {"", ".", ".."} for p in name.split("/"))
            and type(digest) is str and _SHA.fullmatch(digest), "source_entry_refused")
    return value


def _isolated():
    _need(sys.flags.isolated == sys.flags.no_site == sys.flags.no_user_site == sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "isolated_auth_interpreter_required")


def _keychain_exec_denied():
    try:
        os.execve("/usr/bin/security", ["security", "help"], {"PATH": "/usr/bin:/bin"})
    except OSError as exc:
        _need(exc.errno in {errno.EPERM, errno.EACCES}, "keychain_exec_denial_required")
    else:
        raise AuthenticationProbeError("keychain_exec_denial_required")


def _identity(head):
    _isolated()
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "fixed_auth_source_required")
    identity = sources.custody._identity(head)
    own = sources.custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH))
    for name, digest in own.items():
        _need(_sha(sources.custody._git(LANE_ROOT, "show", head + ":" + name)) == digest, "uncommitted_auth_source")
    inventory = {**identity["source_sha256"], **own}
    _need(sources.custody._source_bytes(LANE_ROOT, tuple(sources.FROZEN)) == sources.FROZEN, "frozen_source_changed")
    return _source_identity({**identity, "source_sha256": inventory, "source_inventory_sha256": _sha(_raw(inventory))}, LANE_ROOT)


def _read_credentials():
    """Exactly one from_env invocation, only after durable read intent."""
    return qc.QuantConnectCredentials.from_env()


def _validate_credentials(credentials):
    _need(type(credentials) is qc.QuantConnectCredentials
        and re.fullmatch(r"[1-9][0-9]{0,19}", credentials.user_id)
        and 0 < len(credentials.api_token) <= 2048
        and all(33 <= ord(c) <= 126 for c in credentials.api_token), "configured_credential_shape_refused")
    return credentials


def _credential_headers(credentials, timestamp):
    _validate_credentials(credentials)
    _need(type(timestamp) is int and timestamp > 0, "auth_timestamp_refused")
    auth = qc.build_auth_headers(credentials, timestamp)
    headers = {**auth, "Content-Type": "application/json", "Accept": "application/json",
        "Accept-Encoding": "identity", "Connection": "close"}
    encoded = auth["Authorization"].removeprefix("Basic ")
    decoded = base64.b64decode(encoded, validate=True).decode("ascii")
    # Protocol signatures are transient secrets too; never return this tuple
    # outside the acquisition control flow or give it a persistent fingerprint.
    needles = (credentials.user_id, credentials.api_token, auth["Authorization"], encoded,
        decoded, decoded.split(":", 1)[1], credentials.api_token + ":" + str(timestamp))
    return headers, needles


def _screen(raw, headers, needles):
    _need(type(raw) is bytes and len(raw) <= MAX_BODY_BYTES and type(headers) is tuple and len(headers) <= 64
        and all(type(p) is tuple and len(p) == 2 and all(type(v) is str for v in p) for p in headers)
        and len(_raw(headers)) <= 16384, "auth_response_bounds_refused")
    views = [raw.decode("latin1"), raw.decode("utf-8", errors="replace")]
    for encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
        try:
            views.append(raw.decode(encoding))
        except UnicodeError:
            pass
    views.extend(v for pair in headers for v in pair)
    for view in views:
        for secret in needles:
            privacy._screen_contact_echo(view, secret)


def _framing_subset(headers):
    _selected_framing(headers, MAX_BODY_BYTES)
    # Original arbitrary HTTP headers are NEVER retained or hashed. This
    # response framing projection contains no server/cookie/account values.
    return tuple((k, v) for k, v in headers if k.lower() in {"content-length", "transfer-encoding", "content-encoding"})


def _https_authenticate(headers):
    connection = http.client.HTTPSConnection(HOST, timeout=WALL_SECONDS)
    try:
        connection.request("POST", PATH, body=b"{}", headers=headers)
        response = connection.getresponse()
        _need(type(response.status) is int and 100 <= response.status <= 599, "auth_http_status_refused")
        if response.status != 200:
            return AuthenticationHttpResult(response.status, (), b"")  # deliberately no read/getheaders
        headers = tuple(response.getheaders())
        try:
            mode, size = _selected_framing(headers, MAX_BODY_BYTES)
        except ValueError:
            return AuthenticationHttpResult(200, headers, b"")
        if mode == "chunked":
            _need(response.chunked is True, "auth_framing_decoder_disagreement")
            body = response.read(MAX_BODY_BYTES + 1)
            _need(len(body) <= MAX_BODY_BYTES and response.read(1) == b"" and response.isclosed(), "auth_complete_body_refused")
        else:
            body = response.read(size)
            _need(len(body) == size, "auth_complete_body_refused")
        return AuthenticationHttpResult(200, headers, body)
    finally:
        connection.close()


class _Context:
    def __init__(self, token, identity, guard, run, start_sha, credentials):
        _need(token is _TOKEN, "genuine_auth_context_required")
        self.identity, self.guard, self.run, self.start_sha = identity, guard, run, start_sha
        self.credentials, self.headers, self.needles = credentials, None, None
        self.attempted = self.raw_transport_invoked = False
        _CONTEXTS[self] = (id(guard), id(run), start_sha, id(credentials))

    def check(self):
        _need(type(self) is _Context and _CONTEXTS.get(self) ==
            (id(self.guard), id(self.run), self.start_sha, id(self.credentials)), "genuine_auth_context_required")
        _validate_credentials(self.credentials)
        _need(_identity(self.identity["head"]) == self.identity, "production_auth_source_changed")
        self.guard(); self.run.check()
        reservation = self.run.read("reservation.json")
        intent = self.run.read("credential-read-intent.json")
        validated = self.run.read("credential-read-complete.json")
        start = self.run.read("request-start.json")
        _need(reservation == _raw(_reservation(self.identity, False))
            and intent == _raw(_intent(_sha(reservation)))
            and validated == _raw(_credential_complete(_sha(intent)))
            and start == _raw(_start(_sha(reservation), _sha(intent), _sha(validated)))
            and _sha(start) == self.start_sha, "durable_auth_start_refused")


def _production_transport(context):
    _need(type(context) is _Context and not context.attempted, "fixed_auth_transport_required")
    _need(threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer")
        and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "auth_absolute_deadline_unavailable")
    context.check()
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise _DeadlineExceeded()
    signal.signal(signal.SIGALRM, expired)
    began = time.monotonic()
    try:
        signal.setitimer(signal.ITIMER_REAL, WALL_SECONDS)
        # Full source/custody checks may be slow. Generate the documented
        # transient signature only after those checks and the durable start,
        # immediately before the opener; never reread the environment.
        context.headers, context.needles = _credential_headers(context.credentials, int(time.time()))
        context.attempted = context.raw_transport_invoked = True
        response = _https_authenticate(context.headers)
        _need(time.monotonic() - began <= WALL_SECONDS, "auth_transport_deadline_refused")
        return response
    except _DeadlineExceeded:
        raise AuthenticationProbeError("auth_transport_deadline_refused") from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _reservation(identity, fixture):
    return {"schema": SCHEMA + "/reservation", "audit_id": AUDIT_ID, "fixture_only": fixture,
        "scope": _scope(), "scope_sha256": _sha(_raw(_scope())), "execution_identity": identity}


def _intent(reservation_sha):
    return {"schema": SCHEMA + "/credential-read-intent", "reservation_sha256": reservation_sha,
        "environment_names": list(ENV_NAMES), "maximum_from_env_invocations": 1, "keychain_or_dotenv_access": False}


def _credential_complete(intent_sha):
    return {"schema": SCHEMA + "/credential-read-complete", "intent_sha256": intent_sha,
        "from_env_invocations": 1, "credential_values_or_fingerprints_retained": False}


def _start(reservation_sha, intent_sha, validated_sha):
    return {"schema": SCHEMA + "/request-start", "reservation_sha256": reservation_sha,
        "intent_sha256": intent_sha, "credential_read_complete_sha256": validated_sha,
        "scope_sha256": _sha(_raw(_scope())), "attempt": 1}


def _complete(identity, fixture, reservation_sha, result, result_sha):
    return {"schema": SCHEMA + "/complete", "audit_id": AUDIT_ID, "fixture_only": fixture,
        "execution_identity": identity, "reservation_sha256": reservation_sha,
        "scope_sha256": _sha(_raw(_scope())), "result_sha256": result_sha, "result": result,
        "credential_reads": 1, "raw_transport_invocations": 1, "project_or_job_requests": 0,
        "platform_data_requests": 0, "outcome_looks": 0, "backtests": 0, "authority": _authority()}


def _preflight(identity, fixture, root):
    _source_identity(identity, root)
    reservation = _reservation(identity, fixture); intent = _intent(_sha(_raw(reservation)))
    validated = _credential_complete(_sha(_raw(intent)))
    result = {"schema": SCHEMA + "/result", "reservation_sha256": _sha(_raw(reservation)),
        "start_sha256": "0" * 64, "http_status": 200, "raw_transport_invocations": 1,
        "disposition": "strict_authentication_status_retained", "body_retained": True,
        "body_sha256": "0" * 64, "body_bytes": MAX_BODY_BYTES,
        "framing_sha256": "0" * 64, "status_sha256": "0" * 64,
        "authentication_success": True, "auth_status_qualified": True}
    forms = {"identity": identity, "reservation": reservation, "intent": intent, "validated": validated,
        "start": _start(_sha(_raw(reservation)), _sha(_raw(intent)), _sha(_raw(validated))),
        "capacity_result": result, "capacity_complete": _complete(identity, fixture, _sha(_raw(reservation)), result, _sha(_raw(result)))}
    for value in forms.values():
        raw = _raw(value)
        _need(0 < len(raw) <= MAX_CONTROL_BYTES and _raw(_decode(raw)) == raw, "precredential_control_roundtrip_refused")
    return forms


def _run(*, root, identity, guard, credential_reader, transport, fixture, clock):
    _need(type(fixture) is bool and callable(guard) and callable(clock), "auth_mode_required")
    if fixture:
        publication._fixture_root(root); publication._native_fixture_denial()
        _need(callable(credential_reader) and credential_reader is not _read_credentials
            and callable(transport) and transport not in {_production_transport, _https_authenticate}, "invented_auth_callbacks_required")
    else:
        _need(root == LANE_ROOT and credential_reader is _read_credentials and transport is _production_transport
            and clock is time.time, "production_auth_front_required")
        _keychain_exec_denied()
        _need(_identity(identity["head"]) == identity, "production_auth_source_changed")
    guard(); forms = _preflight(identity, fixture, root); guard()
    folders, lock_fd, locked = [], None, False
    try:
        folder = publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS), create=True); folders.append(folder)
        _need(not os.listdir(folder.fd), "authentication_scope_already_consumed")
        folder.publish("scope.lock", LOCK_BYTES)
        lock_fd = os.open("scope.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder.fd)
        lock_version = publication._version(os.fstat(lock_fd)); fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB); locked = True
        expected = {"scope.lock"}
        def check():
            guard(); folder.check()
            _need(set(os.listdir(folder.fd)) == expected and publication._version(os.fstat(lock_fd)) == lock_version ==
                publication._version(os.stat("scope.lock", dir_fd=folder.fd, follow_symlinks=False)), "authentication_scope_changed")
        def publish(name, value):
            digest = folder.publish(name, _raw(value), cap=MAX_CONTROL_BYTES); expected.add(name); check(); return digest
        reservation_sha = publish("reservation.json", forms["reservation"])
        intent_sha = publish("credential-read-intent.json", forms["intent"])
        try:
            credentials = credential_reader()
            _validate_credentials(credentials)
        except Exception:
            raise AuthenticationProbeError("configured_credentials_unavailable_or_invalid") from None
        validated_sha = publish("credential-read-complete.json", _credential_complete(intent_sha))
        start_sha = publish("request-start.json", _start(reservation_sha, intent_sha, validated_sha))
        response = None; context = None; headers = needles = None
        try:
            if fixture:
                headers, needles = _credential_headers(credentials, int(clock()))
                response = transport(URL, b"{}", headers, MAX_BODY_BYTES)
            else:
                context = _Context(_TOKEN, identity, check, folder, start_sha, credentials)
                response = _production_transport(context)
        except Exception:
            if not fixture and (context is None or not context.raw_transport_invoked):
                raise AuthenticationProbeError("authentication_front_refused_before_raw_invocation") from None
        finally:
            # Best-effort reference release, not a claim about Python zeroization.
            if context is not None:
                needles = context.needles
                context.credentials = None
            credentials = headers = None
        check()
        status = body_sha = body_bytes = framing_sha = parsed_sha = None
        success = None; retained = qualified = False; disposition = "ambiguous_authentication_transport_failure_no_retry"
        if response is not None:
            _need(type(response) is AuthenticationHttpResult and type(response.status) is int and 100 <= response.status <= 599,
                "authentication_transport_metadata_refused")
            status = response.status; disposition = "authentication_http_refused_unread_body_no_retry"
            if status == 200:
                try:
                    _screen(response.body, response.headers, needles)
                    body = _strict_selected_response(SecHttpResult(200, response.headers, response.body), max_bytes=MAX_BODY_BYTES)
                    parsed = parse_authentication_status(body)
                    framing = _framing_subset(response.headers)
                except Exception:
                    disposition = "authentication_privacy_framing_or_schema_refused_no_retry"
                else:
                    body_sha = folder.publish("response.bin", body, cap=MAX_BODY_BYTES); expected.add("response.bin"); check()
                    body_bytes, retained, qualified, success = len(body), True, True, parsed["success"]
                    framing_sha = publish("response-framing.json", {"headers": framing})
                    parsed_sha = publish("status.json", parsed)
                    disposition = "strict_authentication_status_retained"
        needles = response = context = None
        result = {"schema": SCHEMA + "/result", "reservation_sha256": reservation_sha, "start_sha256": start_sha,
            "http_status": status, "raw_transport_invocations": 1, "disposition": disposition,
            "body_retained": retained, "body_sha256": body_sha, "body_bytes": body_bytes,
            "framing_sha256": framing_sha, "status_sha256": parsed_sha,
            "authentication_success": success, "auth_status_qualified": qualified}
        result_sha = publish("result.json", result)
        complete = _complete(identity, fixture, reservation_sha, result, result_sha)
        complete_sha = publish("complete.json", complete); check()
        return {"audit_id": AUDIT_ID, "report_sha256": complete_sha, "http_status": status,
            "authentication_success": success, "auth_status_qualified": qualified, "disposition": disposition,
            "credential_reads": 1, "raw_transport_invocations": 1, "body_sha256": body_sha, "body_bytes": body_bytes,
            "project_or_job_requests": 0, "platform_data_requests": 0, "outcome_looks": 0, "backtests": 0,
            "authority": _authority()}
    finally:
        publication._close_all(folders, None, lock_fd, locked)


def run_actual_probe(expected_head):
    before = _identity(expected_head)
    def guard():
        _need(_identity(expected_head) == before, "committed_auth_source_changed")
    return _run(root=LANE_ROOT, identity=before, guard=guard, credential_reader=_read_credentials,
        transport=_production_transport, fixture=False, clock=time.time)


def _run_invented_probe(*, root, credential_reader, transport, guard=lambda: None, clock=lambda: 1700000000):
    sources_map = {SELF_PATH: "a" * 64, TEST_PATH: "b" * 64,
        **{f"research/invented_{i:03}.py": "c" * 64 for i in range(104)}}
    identity = {"root": str(root), "branch": LANE_BRANCH, "head": "a" * 40, "clean": True,
        "source_sha256": sources_map, "source_inventory_sha256": _sha(_raw(sources_map))}
    return _run(root=root, identity=identity, guard=guard, credential_reader=credential_reader,
        transport=transport, fixture=True, clock=clock)


def _verify(root, report_sha, fixture, identity=None):
    _need(type(report_sha) is str and _SHA.fullmatch(report_sha), "auth_report_pin_required")
    folder = publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS))
    try:
        complete_raw = folder.read("complete.json"); _need(_sha(complete_raw) == report_sha, "auth_report_changed")
        complete = _decode(complete_raw); reservation_raw = folder.read("reservation.json")
        reservation = _decode(reservation_raw); observed_identity = _source_identity(reservation.get("execution_identity"), root)
        _need(identity is None or _raw(observed_identity) == _raw(identity), "auth_readback_identity_changed")
        _need(reservation_raw == _raw(_reservation(observed_identity, fixture)) and folder.read("scope.lock") == LOCK_BYTES,
            "auth_readback_reservation_changed")
        intent_raw = folder.read("credential-read-intent.json"); validated_raw = folder.read("credential-read-complete.json")
        start_raw = folder.read("request-start.json")
        _need(intent_raw == _raw(_intent(_sha(reservation_raw)))
            and validated_raw == _raw(_credential_complete(_sha(intent_raw)))
            and start_raw == _raw(_start(_sha(reservation_raw), _sha(intent_raw), _sha(validated_raw))), "auth_readback_start_changed")
        result_raw = folder.read("result.json"); result = _decode(result_raw)
        _need(type(result) is dict and set(result) == {"schema", "reservation_sha256", "start_sha256", "http_status",
            "raw_transport_invocations", "disposition", "body_retained", "body_sha256", "body_bytes", "framing_sha256",
            "status_sha256", "authentication_success", "auth_status_qualified"}
            and result["schema"] == SCHEMA + "/result" and result["reservation_sha256"] == _sha(reservation_raw)
            and result["start_sha256"] == _sha(start_raw) and type(result["raw_transport_invocations"]) is int
            and result["raw_transport_invocations"] == 1 and type(result["body_retained"]) is bool
            and type(result["auth_status_qualified"]) is bool
            and (result["http_status"] is None or type(result["http_status"]) is int and 100 <= result["http_status"] <= 599),
            "auth_readback_result_refused")
        expected = {"scope.lock", "reservation.json", "credential-read-intent.json", "credential-read-complete.json",
            "request-start.json", "result.json", "complete.json"}
        success = None
        if result["body_retained"]:
            body = folder.read("response.bin", cap=MAX_BODY_BYTES)
            framing_raw = folder.read("response-framing.json"); framing = _decode(framing_raw)
            _need(set(framing) == {"headers"} and type(framing["headers"]) is list
                and all(type(p) is list and len(p) == 2 and all(type(v) is str for v in p) for p in framing["headers"]),
                "auth_readback_framing_refused")
            pairs = tuple(tuple(p) for p in framing["headers"])
            _need(pairs == _framing_subset(pairs) and _strict_selected_response(SecHttpResult(200, pairs, body), max_bytes=MAX_BODY_BYTES) == body,
                "auth_readback_framing_refused")
            parsed = parse_authentication_status(body); parsed_raw = folder.read("status.json"); success = parsed["success"]
            _need(type(result["body_bytes"]) is int and len(body) == result["body_bytes"]
                and result["body_sha256"] == _sha(body) and result["framing_sha256"] == _sha(framing_raw)
                and result["status_sha256"] == _sha(parsed_raw) and parsed_raw == _raw(parsed)
                and result["http_status"] == 200 and result["authentication_success"] is success
                and result["auth_status_qualified"] is True and result["disposition"] == "strict_authentication_status_retained",
                "auth_readback_status_changed")
            expected |= {"response.bin", "response-framing.json", "status.json"}
        else:
            _need(result["body_sha256"] is result["body_bytes"] is result["framing_sha256"] is result["status_sha256"] is None
                and result["authentication_success"] is None and result["auth_status_qualified"] is False
                and result["disposition"] == ("ambiguous_authentication_transport_failure_no_retry" if result["http_status"] is None
                    else "authentication_privacy_framing_or_schema_refused_no_retry" if result["http_status"] == 200
                    else "authentication_http_refused_unread_body_no_retry"), "auth_readback_refusal_changed")
        _need(complete_raw == _raw(_complete(observed_identity, fixture, _sha(reservation_raw), result, _sha(result_raw)))
            and set(os.listdir(folder.fd)) == expected, "auth_readback_complete_changed")
        folder.check()
        return {"audit_id": AUDIT_ID, "report_sha256": report_sha, "http_status": result["http_status"],
            "authentication_success": success, "auth_status_qualified": result["auth_status_qualified"],
            "disposition": result["disposition"], "credential_reads_in_original_operation": 1,
            "raw_transport_invocations_in_original_operation": 1, "body_sha256": result["body_sha256"], "body_bytes": result["body_bytes"],
            "new_provider_requests": 0, "credential_reads": 0, "project_or_job_requests": 0,
            "platform_data_requests": 0, "outcome_looks": 0, "backtests": 0, "authority": _authority()}
    finally:
        publication._close_all((folder,), None, None, False)


def verify_invented_probe(root, report_sha):
    publication._fixture_root(root); publication._native_fixture_denial()
    return _verify(root, report_sha, True)


def verify_actual_probe(*, expected_report_sha256, execution_identity):
    _isolated(); sources._prove_isolation()
    identity = _source_identity(execution_identity, LANE_ROOT)
    def current():
        required = set(sources.custody._internal_source_paths(LANE_ROOT)) | {SELF_PATH, TEST_PATH}
        _need(required <= set(identity["source_sha256"]), "auth_readback_source_closure_incomplete")
        _need(sources.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"]
            and sources.custody._source_bytes(LANE_ROOT, tuple(sources.FROZEN)) == sources.FROZEN, "auth_readback_sources_changed")
    current(); result = _verify(LANE_ROOT, expected_report_sha256, False, identity); current()
    return {**result, "native_network_fork_allwrite_securityexec_denial": True}


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # A mistaken --api-token argument must not be echoed by argparse.
        self.exit(2, "REFUSED: unsupported authentication control arguments\n")


def main(argv=None):
    parser = _ArgumentParser(description=__doc__); parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_actual_probe(args.expected_head)
        print(_raw(result).decode())
        return 0 if result["authentication_success"] is True else 2
    except Exception:
        sys.stderr.write("REFUSED: authentication control stopped; preserve its consumed scope\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
