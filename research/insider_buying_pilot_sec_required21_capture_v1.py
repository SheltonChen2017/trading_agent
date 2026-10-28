"""One fresh required21 original quality sample, not a campaign continuation.

Only run_actual grants transport authority after genuine complete25 selection,
held current/old inputs and durable reservation/claim/start records. Native
source and response workers deny network/fork/all writes/security exec and keep
the existing real VM/RSS guard through stdout. A privacy-cleared original may
be retained on structural quarantine; that stops the sample and never admits
it. Acceptance remains a source declaration/model, not historical known-by.
"""
from __future__ import annotations

import argparse
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import threading
import time
import weakref

from research import insider_buying_sec_feed_nc_source_binding_observe_v1 as source
from research import insider_buying_pilot_sec_required21_selection_v1 as selection
from research.insider_buying.sec_complete_submission import SecCompleteSubmissionTarget, project_sec_complete_submission

previous, base = source.previous, source.source_runner
batch, first = previous.batch, previous.batch.first
archive, privacy, contact_io = batch.archive, source.privacy, source.contact_io
SCHEMA = "insider-pilot-required21-original-quality-v1"
SELF_PATH = "research/insider_buying_pilot_sec_required21_capture_v1.py"
TEST_PATH = "tests/test_insider_buying_pilot_sec_required21_capture_v1.py"
PURE_PATH = "research/insider_buying_pilot_sec_required21_selection_v1.py"
PURE_TEST_PATH = "tests/test_insider_buying_pilot_sec_required21_selection_v1.py"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "pilot_sec_required21_v1")
AUDIT_ID = "ib-sec-required21-originals-quality-20261028-once-v1"
LANE_ROOT, LANE_BRANCH, EMPTY_CACHE_PREFIX = source.LANE_ROOT, source.LANE_BRANCH, source.EMPTY_CACHE_PREFIX
MAX_CONTROL, MAX_PARENT_BYTES, WORKER_SECONDS = 8*1024**2, 8*1024**2, 900
MIN_FREE_BYTES, SPACING_NS, TRANSPORT_SECONDS = 8*1024**3, 500000000, 30
LOCK_BYTES = b"INSETF-required21-original-quality-once-v1\n"
_raw, _sha = source._raw, source._sha
_TOKEN = object()
_AUTH = weakref.WeakKeyDictionary()
_DISPATCH = weakref.WeakKeyDictionary()
_CODES = frozenset({"arguments_refused", "source_changed", "native_refused", "inputs_changed", "selection_refused",
    "namespace_consumed", "output_changed", "capacity_refused", "private_contact_refused", "genuine_dispatch_required",
    "durable_start_required", "spacing_refused", "transport_ambiguous", "transport_deadline", "HTTP_non200",
    "HTTP_framing_refused", "finite_privacy_refused", "original_structure_refused", "inspection_refused", "cleanup_refused"})


class Required21CaptureError(ValueError):
    """Only finite own codes cross the boundary."""


class _Deadline(Exception):
    pass


def _need(ok, code):
    if not ok:
        raise Required21CaptureError(code)


def _safe(error):
    if type(error) is selection.Required21SelectionError:return "selection_refused"
    return str(error) if type(error) is Required21CaptureError and str(error) in _CODES else "native_refused"


def _decode(raw):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_CONTROL, "inputs_changed")
    value = batch.campaign._decode(raw)
    _need(_raw(value) == raw, "inputs_changed")
    return value


def _private_line():
    raw = sys.stdin.buffer.readline(MAX_CONTROL+1)
    _need(raw.endswith(b"\n") and len(raw) <= MAX_CONTROL, "inputs_changed")
    return _decode(raw[:-1])


def _authority():
    return {"historical_public_known_by_verified": False, "source_authenticated": False, "point_in_time_data": False,
        "rights_verified": False, "canonical_admitted": False, "complete_required21_corpus": False,
        "backtesting_ready": False, "qc_jobs": 0, "outcome_looks": 0, "backtests": 0}


def registration():
    return {"schema": SCHEMA+"/registration", "audit_id": AUDIT_ID, "required_periods": list(selection.REQUIRED_PERIODS),
        "context_periods": list(selection.CONTEXT_PERIODS), "maximum_fresh_originals": 8,
        "known_consumed_count": 20044, "known_consumed_index_sha256": previous.CONSUMED_PINS["consumed-index.json"],
        "maximum_parent_bytes": MAX_PARENT_BYTES, "transport_wall_seconds": TRANSPORT_SECONDS,
        "transport_idle_seconds": 15, "minimum_finish_to_next_start_ns": SPACING_NS,
        "minimum_disk_reserve_bytes": MIN_FREE_BYTES, "source_worker_seconds": WORKER_SECONDS,
        "memory_policy": previous._memory_policy(), "redirects_retries_aliases_or_pagination": False,
        "existing_campaign_controller_EX_held_not_machinewide_rate_enforcement": True,
        "privacy_cleared_structural_quarantines_retained": True, "first_refusal_stops_sample": True,
        "acceptance_clock_basis": "SEC_ACCEPTANCE_MODEL", "authority": _authority()}


def _current(identity):
    source._current(identity)
    names = (SELF_PATH, TEST_PATH, PURE_PATH, PURE_TEST_PATH)
    _need(set(names) <= set(identity["source_sha256"]), "source_changed")
    _need(base.custody._source_bytes(LANE_ROOT, names) == {name:identity["source_sha256"][name] for name in names}, "source_changed")


def _identity(head):
    _need(Path(__file__).resolve() == LANE_ROOT/SELF_PATH, "source_changed")
    identity = source._identity(head)
    own = base.custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH, PURE_PATH, PURE_TEST_PATH))
    for path, digest in own.items():
        _need(_sha(base.custody._git(LANE_ROOT, "show", head+":"+path)) == digest, "source_changed")
    sources = {**identity["source_sha256"], **own}
    identity = {**identity, "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    _current(identity)
    return identity


def _derive_selection(held):
    """Only the native worker opens source bodies; all25 finish before seal."""
    holds = []; intake = None
    try:
        holds, exposure_raw, snapshot, candidates = base.exposure.observe_exposures(base.exposure.actual_roots(), fixture_only=False)
        old = held.old.plan
        _need(_sha(exposure_raw) == old["base_consumption"]["old_exposure_inventory_sha256"]
            and _sha(snapshot) == old["base_consumption"]["old_exposure_snapshot_sha256"], "inputs_changed")
        candidates = base.exposure.hash_candidate_bodies(holds, candidates)
        builder = selection.Required21SelectionBuilder(consumed_accessions=tuple(sorted(held.consumed)),
            consumption_sha256=previous.CONSUMED_PINS["consumed-index.json"])
        masters = next(item for item in holds if item.spec.root_id == "masters-v3")
        compiler = base.compiler.PilotSecParentAuditCompiler(exposure_raw=exposure_raw,
            expected_exposure_sha256=_sha(exposure_raw), candidates_raw=candidates,
            expected_candidates_sha256=_sha(candidates), master_for_period=lambda period:base._master(masters.tree, period),
            emit_row=builder.consume)
        intake = base.selector._HeldIntake(); held.intake.match_genuine(intake)
        roster = base.roster.derive_pilot_sec_roster(intake_manifest_raw=intake.manifest_raw,
            expected_manifest_sha256=intake.context["manifest_sha256"], selection_raw=held.selection,
            expected_selection_sha256=source.prior.ACTUAL_ANCHORS.selection,
            quarter_inputs=base.roster.held_context_quarters(intake), consume_row=compiler.consume, fixture_only=False)
        audit = compiler.finish(roster)
        _need(_raw(roster.to_payload()) == _raw(old["source_roster"])
              and _raw(audit.to_payload()) == _raw(old["parent_audit"]), "inputs_changed")
        result = builder.finish(source_roster=roster, parent_audit=audit,
            expected_roster_sha256=_sha(_raw(old["source_roster"])), expected_audit_sha256=_sha(_raw(old["parent_audit"])))
        intake.recheck(); held.intake.match_genuine(intake); held.check()
        for item in holds:item.recheck()
        return result.to_payload()
    finally:
        base.selector._close_all((intake, *reversed(holds)), phase="required21_source_cleanup")


def _project(raw, request):
    target = SecCompleteSubmissionTarget(**{key:request[key] for key in ("period", "accession_number", "form_type", "filing_date")},
        issuer_cik=request["issuer_cik"].zfill(10), quarterly_index_sha256=request["master_decoded_sha256"],
        complete_submission_url=request["url"])
    projected = project_sec_complete_submission(target, raw); body = projected.to_payload()
    header, xml = projected.header_bytes, projected.xml_bytes
    _need(raw.count(header) == raw.count(xml) == 1, "original_structure_refused")
    return {"version":body["version"], "projection_sha256":projected.sha256,
        "accepted_at_raw_uninterpreted":projected.accepted_at_raw,
        "header":{"offset":raw.find(header), "bytes":len(header), "sha256":_sha(header)},
        "primary_xml":{"offset":raw.find(xml), "bytes":len(xml), "sha256":_sha(xml)},
        "reporting_owner_count":len(projected.header_owner_ciks), "header_xml_owner_sets_agree":True,
        "issuer_crosschecked_against_source":True, "amendment_lineage_inferred":False}


def _inspect(raw, headers, contact, request):
    """Full privacy precedes every original-derived hash and projection."""
    result = {"schema": SCHEMA+"/inspection", "privacy_cleared": False, "structure_bound": False,
        "code": "HTTP_framing_refused", "body_sha256": None, "body_bytes": None, "headers_sha256": None,
        "projection": None, "authority": _authority()}
    try:
        first._strict_selected_response(first.SecHttpResult(200, headers, raw), max_bytes=MAX_PARENT_BYTES)
    except (ValueError, TypeError, KeyError, UnicodeError):return result
    try:
        for pair in headers:
            for value in pair:first.custody._screen_contact_echo(value, contact)
        screen = batch.fast_privacy._TextScreen(contact)
        for offset in range(0, len(raw), 65536):screen.feed(raw[offset:offset+65536])
        screen.feed(b"", final=True)
    except (ValueError, TypeError, UnicodeError):return {**result, "code": "finite_privacy_refused"}
    result.update(privacy_cleared=True, body_sha256=_sha(raw), body_bytes=len(raw), headers_sha256=_sha(_raw(headers)),
                  code="original_structure_refused")
    try:
        projection = _project(raw, request)
        result.update(structure_bound=True, code="none", projection=projection)
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):pass
    return result


def _inspection_valid(value, raw, headers):
    expected = {"schema", "privacy_cleared", "structure_bound", "code", "body_sha256", "body_bytes", "headers_sha256", "projection", "authority"}
    _need(type(value) is dict and set(value) == expected and value["schema"] == SCHEMA+"/inspection"
          and type(value["privacy_cleared"]) is type(value["structure_bound"]) is bool
          and _raw(value["authority"]) == _raw(_authority()), "inspection_refused")
    if value["privacy_cleared"]:
        _need(type(raw) is bytes and 0 < len(raw) <= MAX_PARENT_BYTES and type(value["body_bytes"]) is int
            and value["body_bytes"] == len(raw) and value["body_sha256"] == _sha(raw)
            and value["headers_sha256"] == _sha(_raw(headers)), "inspection_refused")
        _need((value["structure_bound"] and value["code"] == "none" and type(value["projection"]) is dict)
            or (not value["structure_bound"] and value["code"] == "original_structure_refused" and value["projection"] is None), "inspection_refused")
        if value["structure_bound"]:
            projected = value["projection"]
            _need(set(projected) == {"version", "projection_sha256", "accepted_at_raw_uninterpreted", "header", "primary_xml",
                "reporting_owner_count", "header_xml_owner_sets_agree", "issuer_crosschecked_against_source", "amendment_lineage_inferred"}
                and projected["version"] == "INSETF-SEC-COMPLETE-SUBMISSION-v1"
                and type(projected["projection_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", projected["projection_sha256"])
                and type(projected["accepted_at_raw_uninterpreted"]) is str and re.fullmatch(r"[0-9]{14}", projected["accepted_at_raw_uninterpreted"])
                and type(projected["reporting_owner_count"]) is int and 1 <= projected["reporting_owner_count"] <= 256
                and projected["header_xml_owner_sets_agree"] is projected["issuer_crosschecked_against_source"] is True
                and projected["amendment_lineage_inferred"] is False, "inspection_refused")
            spans = []
            for name in ("header", "primary_xml"):
                child = projected[name]
                _need(type(child) is dict and set(child) == {"offset", "bytes", "sha256"}
                    and type(child["offset"]) is type(child["bytes"]) is int and child["offset"] >= 0 and child["bytes"] > 0
                    and child["offset"]+child["bytes"] <= len(raw), "inspection_refused")
                image = raw[child["offset"]:child["offset"]+child["bytes"]]
                _need(_sha(image) == child["sha256"] and raw.count(image) == 1, "inspection_refused")
                spans.append((child["offset"], child["offset"]+child["bytes"]))
            _need(spans[0][1] <= spans[1][0], "inspection_refused")
    else:
        _need(value["structure_bound"] is False and value["projection"] is None
            and value["code"] in {"HTTP_framing_refused", "finite_privacy_refused"}
            and all(value[key] is None for key in ("body_sha256", "body_bytes", "headers_sha256")), "inspection_refused")
    return value


def _worker(role, identity, *, publish=False):
    previous._isolated(); base._prove_isolation(); memory = previous._WorkerMemoryGuard(); held = None
    try:
        _current(identity); source.capture._compile_sources(identity); _current(identity); memory.check()
        if role == "select":
            supplied = _private_line()
            held = source._SourceInputs(LANE_ROOT)
            _need(_raw(supplied) == _raw(held.metadata), "inputs_changed")
            selected = _derive_selection(held)
            value = {"schema":SCHEMA+"/selected", "execution_identity":identity,
                "input_metadata_sha256":_sha(_raw(held.metadata)), "selection":selected}
        elif role == "inspect":
            supplied = _private_line()
            _need(set(supplied) == {"contact", "request", "headers", "bytes"} and type(supplied["bytes"]) is int
                  and 0 < supplied["bytes"] <= MAX_PARENT_BYTES, "inspection_refused")
            request = batch.campaign._request(supplied["request"])
            contact = first.custody._contact(supplied["contact"], observed=True)
            raw = sys.stdin.buffer.read(supplied["bytes"]+1)
            _need(len(raw) == supplied["bytes"], "inspection_refused")
            value = _inspect(raw, tuple(tuple(row) for row in supplied["headers"]), contact, request)
        elif role == "readback":
            supplied = _private_line()
            _need(set(supplied) == {"complete_sha256"}, "inputs_changed")
            value = _readback(LANE_ROOT.joinpath(*ARTIFACT_PARTS), supplied["complete_sha256"], fixture=False)
        else:raise Required21CaptureError("arguments_refused")
        if held:held.check()
        _current(identity); memory.check(); result = {"ok":True, "value":value}
    except Exception as error:result = {"ok":False, "code":_safe(error)}
    try:
        if not publish:return result
        wire = _raw(result); _need(len(wire) <= MAX_CONTROL, "capacity_refused")
        memory.check(); sys.stdout.buffer.write(wire+b"\n"); sys.stdout.buffer.flush(); memory.check()
    finally:base.selector._close_all((held, memory), phase="required21_worker_cleanup")


def _command(role, identity):
    _need(role in {"select", "inspect", "readback"}, "arguments_refused")
    code = "import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_pilot_sec_required21_capture_v1 as m;identity=json.loads("+repr(_raw(identity).decode())+");\ntry:m._worker("+repr(role)+",identity,publish=True)\nexcept Exception:print('{\"ok\":false,\"code\":\"native_refused\"}')"
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix="+EMPTY_CACHE_PREFIX, "-c", code)


def _child(role, identity, payload):
    try:result = batch.campaign._run_child(_command(role, identity), payload, timeout=WORKER_SECONDS if role != "inspect" else 90)
    except Exception:raise Required21CaptureError("native_refused") from None
    _need(type(result) is dict and type(result.get("ok")) is bool, "native_refused")
    if not result["ok"]:
        _need(set(result) == {"ok", "code"} and result["code"] in _CODES, "native_refused")
        raise Required21CaptureError(result["code"])
    _need(set(result) == {"ok", "value"}, "native_refused")
    return result["value"]


class _Namespace:
    def __init__(self, path):
        self.path, self.folders, self.lock = Path(path), [], None
        self.expected, self.claims_expected, self.objects_expected = set(), set(), set()
        parent = None
        try:
            parent = first.custody._Directory(self.path.parent)
            try:os.mkdir(self.path.name, 0o700, dir_fd=parent.fd)
            except FileExistsError:raise Required21CaptureError("namespace_consumed") from None
            os.fsync(parent.fd)
            self.top = first._NewDirectory(self.path); self.folders.append(self.top)
            for name in ("claims", "objects"):
                os.mkdir(name, 0o700, dir_fd=self.top.fd); os.fsync(self.top.fd)
                folder = first._NewDirectory(self.path/name); self.folders.append(folder); setattr(self, name, folder)
            self.expected.update({"claims", "objects"})
            self.top.publish("scope.lock", LOCK_BYTES); self.expected.add("scope.lock")
            self.lock = os.open("scope.lock", os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=self.top.fd)
            fcntl.flock(self.lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.lock_version = first._version(os.fstat(self.lock)); self.check()
        except BaseException:self.close(); raise
        finally:
            if parent:parent.close()

    def check(self):
        for folder in self.folders:folder.check()
        _need(set(os.listdir(self.top.fd)) == self.expected and set(os.listdir(self.claims.fd)) == self.claims_expected
            and set(os.listdir(self.objects.fd)) == self.objects_expected, "output_changed")
        if self.lock is not None:
            _need(first._version(os.fstat(self.lock)) == self.lock_version == first._version(
                os.stat("scope.lock", dir_fd=self.top.fd, follow_symlinks=False)), "output_changed")

    def publish(self, name, value):
        self.check(); pin = self.top.publish(name, _raw(value), cap=MAX_CONTROL)
        self.expected.add(name); self.check(); return pin

    def claim(self, name, value):
        self.check(); pin = self.claims.publish(name, _raw(value), cap=MAX_CONTROL)
        self.claims_expected.add(name); self.check(); return pin

    def body(self, raw, pin):
        name = pin+".bin"; self.check()
        if name in self.objects_expected:_need(self.objects.read(name, cap=MAX_PARENT_BYTES) == raw, "output_changed")
        else:self.objects.publish(name, raw, cap=MAX_PARENT_BYTES); self.objects_expected.add(name)
        self.check(); return name

    def close(self):
        base.selector._close_all((archive.SimpleCloseFD(self.lock), *reversed(self.folders)), phase="required21_output_cleanup")
        self.lock, self.folders = None, []


class _Authorization:
    def __init__(self, identity, plan, guard):
        self.identity, self.plan, self.guard = identity, plan, guard
        self.plan_sha256 = _sha(_raw(plan)); self.requests = tuple(_raw(row["request"]) for row in plan["requests"])
        self.attempted = set()


def _authorized(value):
    _need(type(value) is _Authorization and _AUTH.get(value) == (id(value.identity), id(value.plan), id(value.guard), value.plan_sha256)
        and value.plan_sha256 == _sha(_raw(value.plan)), "genuine_dispatch_required")
    return value


class _Dispatch:
    def __init__(self, authorization, ordinal, request, headers, guard, prove_start):
        self.authorization, self.ordinal, self.request, self.headers = authorization, ordinal, request, headers
        self.guard, self.prove_start, self.invoked = guard, prove_start, False
        self.http_status = None


def _transport(context):
    _need(type(context) is _Dispatch and not context.invoked, "genuine_dispatch_required")
    auth = _authorized(context.authorization); ordinal = context.ordinal
    _need(type(ordinal) is int and 0 <= ordinal < len(auth.requests) and ordinal not in auth.attempted
        and _raw(context.request) == auth.requests[ordinal] and _DISPATCH.get(context) ==
        (id(auth), ordinal, id(context.request), _raw(context.headers), id(context.guard), id(context.prove_start)), "genuine_dispatch_required")
    request = batch.campaign._request(context.request)
    context.guard(); context.prove_start(); batch._lane_boundary(auth.identity)
    _need(threading.current_thread() is threading.main_thread() and signal.getitimer(signal.ITIMER_REAL) == (0., 0.), "genuine_dispatch_required")
    previous_handler = signal.getsignal(signal.SIGALRM); connection = None; begun = time.monotonic()
    def expired(*args):raise _Deadline()
    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, TRANSPORT_SECONDS); context.invoked = True; auth.attempted.add(ordinal)
        connection = http.client.HTTPSConnection("www.sec.gov", timeout=15)
        connection.request("GET", request["url"].removeprefix("https://www.sec.gov"), headers=context.headers)
        response = connection.getresponse(); _need(type(response.status) is int and 100 <= response.status <= 599, "HTTP_framing_refused")
        context.http_status = response.status
        if response.status != 200:return first.SecHttpResult(response.status, (), b"")
        headers = tuple(response.getheaders())
        try:mode, size = archive._framing(headers, MAX_PARENT_BYTES)
        except (ValueError, TypeError):raise Required21CaptureError("HTTP_framing_refused") from None
        _need(mode != "chunked" or response.chunked is True, "HTTP_framing_refused")
        raw = response.read(size if mode == "length" else MAX_PARENT_BYTES+1)
        _need(mode != "chunked" or response.read(1) == b"" and response.isclosed(), "HTTP_framing_refused")
        result = first.SecHttpResult(200, headers, raw)
        try:first._strict_selected_response(result, max_bytes=MAX_PARENT_BYTES)
        except (ValueError, TypeError):raise Required21CaptureError("HTTP_framing_refused") from None
        _need(time.monotonic()-begun <= TRANSPORT_SECONDS, "transport_deadline")
        return result
    except _Deadline:raise Required21CaptureError("transport_deadline") from None
    finally:
        primary = sys.exc_info()[0] is not None; failure = False
        for cleanup in (lambda:signal.setitimer(signal.ITIMER_REAL, 0), lambda:signal.signal(signal.SIGALRM, previous_handler),
                        *((connection.close,) if connection else ())):
            try:cleanup()
            except BaseException:failure = True
        if failure and not primary:raise Required21CaptureError("cleanup_refused")


def _result_valid(value, row, ordinal, claim_sha256, start_sha256):
    _need(type(value) is dict and set(value) == {"schema", "ordinal", "attempt", "request_sha256", "claim_sha256", "start_sha256", "http_status",
        "transport_invocations", "remote_request_count_measured", "code", "inspection", "body_object", "finished_utc", "finished_monotonic_ns"}
        and value["schema"] == SCHEMA+"/result" and type(value["ordinal"]) is type(value["attempt"]) is int
        and value["ordinal"] == ordinal and value["attempt"] == 1 and value["request_sha256"] == row["request_sha256"]
        and value["claim_sha256"] == claim_sha256 and value["start_sha256"] == start_sha256
        and type(value["transport_invocations"]) is int and value["transport_invocations"] in {0, 1}
        and value["remote_request_count_measured"] is False and type(value["finished_monotonic_ns"]) is int
        and value["finished_monotonic_ns"] >= 0 and type(value["finished_utc"]) is str
        and first.custody._stamp(lambda:value["finished_utc"]) == value["finished_utc"], "inputs_changed")
    status, checked, code = value["http_status"], value["inspection"], value["code"]
    if status is None:
        # Section 342 (Claude review): a framing refusal raised before the status
        # is observed (e.g. outside 100..599) is still a received response.
        _need(checked is None and value["body_object"] is None
            and code in {"transport_ambiguous", "transport_deadline", "cleanup_refused", "HTTP_framing_refused"}
            and (code != "HTTP_framing_refused" or value["transport_invocations"] == 1), "inputs_changed")
    else:
        _need(type(status) is int and 100 <= status <= 599 and value["transport_invocations"] == 1, "inputs_changed")
        if status != 200:
            _need(checked is None and value["body_object"] is None and code == "HTTP_non200", "inputs_changed")
        elif checked is None:
            _need(value["body_object"] is None and code in {"inspection_refused", "HTTP_framing_refused"}, "inputs_changed")
        else:
            _need(type(checked) is dict and code == checked.get("code") and type(checked.get("privacy_cleared")) is bool, "inputs_changed")
            if checked["privacy_cleared"]:
                _need(type(checked.get("body_sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", checked["body_sha256"])
                    and value["body_object"] == checked["body_sha256"]+".bin"
                    and ((checked.get("structure_bound") is True and code == "none")
                         or (checked.get("structure_bound") is False and code == "original_structure_refused")), "inputs_changed")
            else:
                _inspection_valid(checked, b"", ()); _need(value["body_object"] is None, "inputs_changed")
    return value


def _consumption_base_bound(plan, registered):
    """Section 342 (Claude review): bind the plan's consumption base to the
    registered index rather than to the plan's own consumed list."""
    _need(plan["consumption_sha256"] == registered["known_consumed_index_sha256"]
        and len(plan["consumed_accessions"]) == registered["known_consumed_count"], "inputs_changed")


def _capture(ns, plan, identity, *, fixture, contact, guard, inspect, transport, authorization=None,
             clock=first.custody._utc, monotonic_ns=time.monotonic_ns, sleep=time.sleep, free_bytes=None):
    selection.validate_selection_payload(plan)
    _need(type(fixture) is bool and plan["fixture_only"] is fixture and 0 < plan["selected_count"] <= 8, "selection_refused")
    if fixture:
        first._fixture_root(ns.path); first._native_fixture_denial()
        _need(transport is not _transport and contact is not contact_io._stdin_contact, "genuine_dispatch_required")
    else:
        auth = _authorized(authorization)
        _need(auth.identity is identity and auth.plan is plan and transport is _transport and contact is contact_io._stdin_contact
            and inspect is None, "genuine_dispatch_required")
    guard(); ns.check(); rows = plan["requests"]
    capacity = free_bytes if free_bytes is not None else lambda:os.fstatvfs(ns.top.fd).f_bavail*os.fstatvfs(ns.top.fd).f_frsize
    _need(type(capacity()) is int and capacity() >= MIN_FREE_BYTES+len(rows)*MAX_PARENT_BYTES+4*MAX_CONTROL, "capacity_refused")
    private = first.custody._contact(contact(), observed=not fixture)
    ns.publish("contact-validated.json", {"schema":SCHEMA+"/contact", "contact_present":True, "contact_stored_or_hashed":False})
    consumed = set(plan["consumed_accessions"]); results = []; previous_finish = monotonic_ns()
    _need(type(previous_finish) is int and previous_finish >= 0, "spacing_refused")
    ns.publish("rate-origin.json", {"schema":SCHEMA+"/rate-origin", "origin_monotonic_ns":previous_finish})
    for ordinal, row in enumerate(rows):
        guard(); ns.check(); request = row["request"]; accession = request["accession_number"]
        _need(accession not in consumed and request["period"] in selection.REQUIRED_PERIODS, "genuine_dispatch_required")
        _need(type(capacity()) is int and capacity() >= MIN_FREE_BYTES+(len(rows)-ordinal)*MAX_PARENT_BYTES, "capacity_refused")
        claim = {"schema":SCHEMA+"/claim", "ordinal":ordinal, "attempt":1, "plan_sha256":_sha(_raw(plan)),
            "request_sha256":row["request_sha256"], "request":request, "claimed_utc":first.custody._stamp(clock)}
        cname = _sha(accession.encode())+".json"; csha = ns.claim(cname, claim); consumed.add(accession)
        now = monotonic_ns(); _need(type(now) is int and now >= previous_finish, "spacing_refused")
        if now-previous_finish < SPACING_NS:sleep((SPACING_NS-now+previous_finish)/1e9)
        started = monotonic_ns(); _need(type(started) is int and started-previous_finish >= SPACING_NS, "spacing_refused")
        start = {"schema":SCHEMA+"/start", "ordinal":ordinal, "attempt":1, "claim_sha256":csha,
            "request_sha256":row["request_sha256"], "started_utc":first.custody._stamp(clock), "started_monotonic_ns":started}
        sname = f"request-{ordinal:03d}-start.json"; ssha = ns.publish(sname, start)
        def prove_start():
            guard(); ns.check()
            _need(ns.top.read(sname) == _raw(start) and ns.claims.read(cname) == _raw(claim), "durable_start_required")
        headers = {"User-Agent":"InsiderBuyingResearch-Required21/1.0 ("+private+")", "Accept":"*/*", "Accept-Encoding":"identity", "Connection":"close"}
        response = context = None; invoked = 0; code = "transport_ambiguous"; checked = None
        try:
            if fixture:prove_start(); invoked = 1; response = transport(request["url"], headers, MAX_PARENT_BYTES)
            else:
                context = _Dispatch(authorization, ordinal, request, headers, guard, prove_start)
                _DISPATCH[context] = (id(authorization), ordinal, id(request), _raw(headers), id(guard), id(prove_start))
                response = _transport(context); invoked = int(context.invoked)
        except Exception as error:
            invoked = int(context.invoked) if context else invoked
            code = str(error) if type(error) is Required21CaptureError and str(error) in {"transport_deadline", "HTTP_framing_refused", "cleanup_refused"} else "transport_ambiguous"
        guard(); ns.check(); status = context.http_status if context and code == "HTTP_framing_refused" else None; body_name = None
        if response is not None:
            _need(type(response) is first.SecHttpResult and type(response.status) is int and 100 <= response.status <= 599, "HTTP_framing_refused")
            status = response.status; code = "HTTP_non200"
            if status != 200:_need(response.body == b"", "HTTP_framing_refused")
            else:
                try:
                    checked = inspect(response.body, response.headers, private, request) if fixture else _child("inspect", identity,
                        _raw({"contact":private, "request":request, "headers":response.headers, "bytes":len(response.body)})+b"\n"+response.body)
                    _inspection_valid(checked, response.body, response.headers); code = checked["code"]
                except Exception:checked = None; code = "inspection_refused"
                if checked and checked["privacy_cleared"]:
                    body_name = ns.body(response.body, checked["body_sha256"])
                    ns.publish(f"request-{ordinal:03d}-headers.json", {"headers":response.headers})
        finished = monotonic_ns(); _need(type(finished) is int and finished >= started, "spacing_refused"); previous_finish = finished
        result = {"schema":SCHEMA+"/result", "ordinal":ordinal, "attempt":1, "request_sha256":row["request_sha256"],
            "claim_sha256":csha, "start_sha256":ssha, "http_status":status, "transport_invocations":invoked,
            "remote_request_count_measured":False, "code":code, "inspection":checked, "body_object":body_name,
            "finished_utc":first.custody._stamp(clock), "finished_monotonic_ns":finished}
        _result_valid(result, row, ordinal, csha, ssha)
        leaf = f"request-{ordinal:03d}-result.json"; pin = ns.publish(leaf, result)
        results.append({"accession_number":accession, "claim_name":cname, "claim_sha256":csha,
            "start_name":sname, "start_sha256":ssha, "result_name":leaf, "result_sha256":pin})
        if not checked or not checked["structure_bound"]:break
    index = {"schema":SCHEMA+"/consumed-index", "accessions":sorted(consumed), "previous_index_sha256":plan["consumption_sha256"],
        "plan_sha256":_sha(_raw(plan)), "unknown_prior_archive_memberships_remain_unknown":True}
    index_sha = ns.publish("consumed-index.json", index)
    final = {"schema":SCHEMA+"/complete", "audit_id":AUDIT_ID, "fixture_only":fixture, "execution_identity":identity,
        "registration_sha256":_sha(_raw(registration())), "reservation_sha256":_sha(ns.top.read("reservation.json")),
        "plan_sha256":_sha(_raw(plan)), "index_sha256":index_sha, "planned":len(rows), "started":len(results),
        "unattempted":len(rows)-len(results), "results":results,
        "completed_without_refusal":len(results) == len(rows) and code == "none", "authority":_authority()}
    complete_sha = ns.publish("complete.json", final); guard(); ns.check()
    return {"schema":SCHEMA+"/public", "audit_id":AUDIT_ID, "complete_sha256":complete_sha, "index_sha256":index_sha,
        "plan_sha256":final["plan_sha256"], "planned":final["planned"], "started":final["started"],
        "unattempted":final["unattempted"], "completed_without_refusal":final["completed_without_refusal"], "authority":_authority()}


def run_actual(*, expected_head):
    """Exactly one source derivation, then at most eight separately claimed GETs."""
    identity = _identity(expected_head); sources = inputs = prior = ns = controller = authorization = None
    try:
        controller = batch.campaign.Controller(LANE_ROOT, create=False)
        sources = batch.SourceHold(identity); inputs = source._SourceInputs(LANE_ROOT)
        prior = first._PriorRoots({"exposure_inventory_sha256":inputs.old.plan["base_consumption"]["old_exposure_inventory_sha256"]})
        _need(prior.exposed_accessions <= set(inputs.consumed) and len(inputs.consumed) == 20044, "inputs_changed")
        def guard():controller.check(); sources.recheck(); inputs.check(); prior.recheck()
        guard(); ns = _Namespace(LANE_ROOT.joinpath(*ARTIFACT_PARTS))
        ns.publish("reservation.json", {"schema":SCHEMA+"/reservation", "audit_id":AUDIT_ID, "execution_identity":identity,
            "registration":registration(), "input_metadata_sha256":_sha(_raw(inputs.metadata)), "authority":_authority()})
        ns.publish("selection-started.json", {"schema":SCHEMA+"/selection-started", "source_worker_invocations":1})
        observed = _child("select", identity, _raw(inputs.metadata)+b"\n")
        _need(type(observed) is dict and set(observed) == {"schema", "execution_identity", "input_metadata_sha256", "selection"}
            and observed["schema"] == SCHEMA+"/selected" and _raw(observed["execution_identity"]) == _raw(identity)
            and observed["input_metadata_sha256"] == _sha(_raw(inputs.metadata)), "selection_refused")
        plan = selection.validate_selection_payload(observed["selection"])
        _need(plan["fixture_only"] is False and plan["consumption_sha256"] == previous.CONSUMED_PINS["consumed-index.json"]
            and plan["consumed_accessions"] == sorted(inputs.consumed)
            and plan["source_roster_sha256"] == _sha(_raw(inputs.old.plan["source_roster"]))
            and plan["parent_audit_sha256"] == _sha(_raw(inputs.old.plan["parent_audit"]))
            and 0 < plan["selected_count"] <= 8, "selection_refused")
        ns.publish("plan.json", plan); ns.publish("selection-complete.json", observed)
        previous._source_git(inputs.metadata["selector_execution_identity"])
        previous._source_git(inputs.metadata["consumed_execution_identity"])
        batch.campaign.verify_plan_producer(inputs.metadata["consumed_planner_receipt"])
        guard(); sources.recheck(full=True); _need(_identity(expected_head) == identity, "source_changed")
        authorization = _Authorization(identity, plan, guard)
        _AUTH[authorization] = (id(identity), id(plan), id(guard), authorization.plan_sha256)
        result = _capture(ns, plan, identity, fixture=False, contact=contact_io._stdin_contact,
            guard=guard, inspect=None, transport=_transport, authorization=authorization)
        guard(); sources.recheck(full=True); _need(_identity(expected_head) == identity, "source_changed")
        return result
    except Exception as error:
        if ns is not None and "failure.json" not in ns.expected:
            ns.publish("failure.json", {"schema":SCHEMA+"/failure", "code":_safe(error), "authority":_authority()})
        raise Required21CaptureError(_safe(error)) from None
    finally:
        if authorization:_AUTH.pop(authorization, None)
        base.selector._close_all((ns, prior, inputs, sources, controller), phase="required21_capture_cleanup")


def run_invented(selection_result, *, root, transport, contact="invented@unit.test", guard=lambda:None,
                 inspect=_inspect, clock=first.custody._utc, monotonic_ns=time.monotonic_ns, sleep=time.sleep, free_bytes=lambda:2**50):
    root = Path(root)
    _need(root.is_absolute() and root.resolve() == root, "genuine_dispatch_required")
    first._fixture_root(root.parent); first._native_fixture_denial()
    plan = selection.validate_required21_selection(selection_result)
    _need(plan["fixture_only"] is True, "genuine_dispatch_required")
    ns = None
    try:
        ns = _Namespace(root); identity = {"fixture_only":True}
        ns.publish("reservation.json", {"schema":SCHEMA+"/reservation", "fixture_only":True, "authority":_authority()})
        ns.publish("plan.json", plan)
        reader = contact if callable(contact) else lambda:contact
        return _capture(ns, plan, identity, fixture=True, contact=reader, guard=guard, inspect=inspect, transport=transport,
            clock=clock, monotonic_ns=monotonic_ns, sleep=sleep, free_bytes=free_bytes)
    finally:
        if ns:ns.close()


def _readback(root, complete_sha256, *, fixture):
    """Strict old-file custody/body/structure replay, never privacy rescreen."""
    _need(type(complete_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", complete_sha256), "inputs_changed")
    if fixture:first._fixture_root(Path(root)); first._native_fixture_denial()
    else:_need(root == LANE_ROOT.joinpath(*ARTIFACT_PARTS), "inputs_changed")
    folders = []; lock = None; pins = []
    try:
        for name in ("", "claims", "objects"):
            folder = first.custody._Directory(Path(root)/name); folders.append(folder)
        top, claims, objects = folders
        initial_names = [set(os.listdir(folder.fd)) for folder in folders]
        def read(folder, name, cap=MAX_CONTROL):
            before = base.custody._version(os.stat(name, dir_fd=folder.fd, follow_symlinks=False))
            raw = folder.read(name, cap=cap)
            _need(base.custody._version(os.stat(name, dir_fd=folder.fd, follow_symlinks=False)) == before, "inputs_changed")
            pins.append((folder, name, before, _sha(raw), len(raw)))
            return raw
        _need(read(top, "scope.lock") == LOCK_BYTES, "inputs_changed")
        lock = os.open("scope.lock", os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=top.fd)
        fcntl.flock(lock, fcntl.LOCK_SH|fcntl.LOCK_NB); lock_version = base.custody._version(os.fstat(lock))
        raw = read(top, "complete.json"); _need(_sha(raw) == complete_sha256, "inputs_changed"); final = _decode(raw)
        _need(set(final) == {"schema", "audit_id", "fixture_only", "execution_identity", "registration_sha256", "reservation_sha256",
            "plan_sha256", "index_sha256", "planned", "started", "unattempted", "results", "completed_without_refusal", "authority"}
            and final["schema"] == SCHEMA+"/complete" and final["audit_id"] == AUDIT_ID and final["fixture_only"] is fixture
            and final["registration_sha256"] == _sha(_raw(registration())) and _raw(final["authority"]) == _raw(_authority()), "inputs_changed")
        reservation_raw = read(top, "reservation.json"); reservation = _decode(reservation_raw)
        _need(_sha(reservation_raw) == final["reservation_sha256"] and reservation["schema"] == SCHEMA+"/reservation", "inputs_changed")
        plan_raw = read(top, "plan.json"); plan = selection.validate_selection_payload(_decode(plan_raw))
        _need(_sha(plan_raw) == final["plan_sha256"] and plan["fixture_only"] is fixture
            and type(final["planned"]) is type(final["started"]) is type(final["unattempted"]) is int
            and final["planned"] == len(plan["requests"]) and 0 < final["started"] <= final["planned"] <= 8
            and final["unattempted"] == final["planned"]-final["started"] and len(final["results"]) == final["started"], "inputs_changed")
        expected = {"claims", "objects", "scope.lock", "reservation.json", "plan.json", "contact-validated.json", "rate-origin.json", "consumed-index.json", "complete.json"}
        if not fixture:
            source.publication._source_identity(final["execution_identity"], required_paths=(SELF_PATH, TEST_PATH, PURE_PATH, PURE_TEST_PATH))
            _need(reservation["execution_identity"] == final["execution_identity"] and reservation["registration"] == registration(), "inputs_changed")
            _consumption_base_bound(plan, reservation["registration"])
            started_selection = _decode(read(top, "selection-started.json")); selected = _decode(read(top, "selection-complete.json"))
            _need(started_selection == {"schema":SCHEMA+"/selection-started", "source_worker_invocations":1}
                and selected["execution_identity"] == final["execution_identity"] and selected["selection"] == plan
                and selected["input_metadata_sha256"] == reservation["input_metadata_sha256"], "inputs_changed")
            expected.update({"selection-started.json", "selection-complete.json"})
        _need(_decode(read(top, "contact-validated.json")) == {"schema":SCHEMA+"/contact", "contact_present":True, "contact_stored_or_hashed":False}, "inputs_changed")
        origin = _decode(read(top, "rate-origin.json")); previous_finish = origin["origin_monotonic_ns"]
        _need(set(origin) == {"schema", "origin_monotonic_ns"} and origin["schema"] == SCHEMA+"/rate-origin"
            and type(previous_finish) is int and previous_finish >= 0, "inputs_changed")
        consumed = set(plan["consumed_accessions"]); claim_names = set(); object_names = set(); retained = structured = 0
        for ordinal, descriptor in enumerate(final["results"]):
            _need(set(descriptor) == {"accession_number", "claim_name", "claim_sha256", "start_name", "start_sha256", "result_name", "result_sha256"}, "inputs_changed")
            row = plan["requests"][ordinal]; request = row["request"]; accession = request["accession_number"]
            cname, sname, rname = _sha(accession.encode())+".json", f"request-{ordinal:03d}-start.json", f"request-{ordinal:03d}-result.json"
            _need(descriptor["accession_number"] == accession and accession not in consumed and descriptor["claim_name"] == cname
                and descriptor["start_name"] == sname and descriptor["result_name"] == rname, "inputs_changed")
            cr, sr, rr = read(claims, cname), read(top, sname), read(top, rname)
            for raw_control, key in ((cr, "claim_sha256"), (sr, "start_sha256"), (rr, "result_sha256")):
                _need(_sha(raw_control) == descriptor[key], "inputs_changed")
            claim, start, result = _decode(cr), _decode(sr), _decode(rr)
            _result_valid(result, row, ordinal, _sha(cr), _sha(sr))
            _need(set(claim) == {"schema", "ordinal", "attempt", "plan_sha256", "request_sha256", "request", "claimed_utc"}
                and set(start) == {"schema", "ordinal", "attempt", "claim_sha256", "request_sha256", "started_utc", "started_monotonic_ns"}
                and set(result) == {"schema", "ordinal", "attempt", "request_sha256", "claim_sha256", "start_sha256", "http_status",
                    "transport_invocations", "remote_request_count_measured", "code", "inspection", "body_object", "finished_utc", "finished_monotonic_ns"}, "inputs_changed")
            _need(claim["schema"] == SCHEMA+"/claim" and start["schema"] == SCHEMA+"/start" and result["schema"] == SCHEMA+"/result"
                and _raw(claim["request"]) == _raw(request) and claim["plan_sha256"] == final["plan_sha256"]
                and all(type(v["ordinal"]) is type(v["attempt"]) is int and v["ordinal"] == ordinal and v["attempt"] == 1
                        and v["request_sha256"] == row["request_sha256"] for v in (claim, start, result))
                and start["claim_sha256"] == result["claim_sha256"] == _sha(cr) and result["start_sha256"] == _sha(sr)
                and result["remote_request_count_measured"] is False and type(result["transport_invocations"]) is int
                and result["transport_invocations"] in {0, 1}, "inputs_changed")
            for record, field in ((claim, "claimed_utc"), (start, "started_utc")):
                _need(type(record[field]) is str and first.custody._stamp(lambda:record[field]) == record[field], "inputs_changed")
            _need(claim["claimed_utc"] <= start["started_utc"] <= result["finished_utc"], "inputs_changed")
            _need(type(start["started_monotonic_ns"]) is type(result["finished_monotonic_ns"]) is int
                and start["started_monotonic_ns"]-previous_finish >= SPACING_NS
                and result["finished_monotonic_ns"] >= start["started_monotonic_ns"], "inputs_changed")
            previous_finish = result["finished_monotonic_ns"]; consumed.add(accession); claim_names.add(cname); expected.update({sname, rname})
            checked = result["inspection"]
            if checked is not None and checked.get("privacy_cleared") is True:
                oname = checked["body_sha256"]+".bin"; _need(result["http_status"] == 200 and result["body_object"] == oname, "inputs_changed")
                body = read(objects, oname, MAX_PARENT_BYTES); hname = f"request-{ordinal:03d}-headers.json"
                hcontrol = _decode(read(top, hname)); _need(set(hcontrol) == {"headers"}, "inputs_changed")
                headers = tuple(tuple(pair) for pair in hcontrol["headers"])
                first._strict_selected_response(first.SecHttpResult(200, headers, body), max_bytes=MAX_PARENT_BYTES)
                _inspection_valid(checked, body, headers)
                try:projected = _project(body, request)
                except (ValueError, TypeError, KeyError, AttributeError):
                    _need(checked["structure_bound"] is False, "inputs_changed")
                else:_need(checked["structure_bound"] is True and _raw(projected) == _raw(checked["projection"]), "inputs_changed")
                object_names.add(oname); expected.add(hname); retained += 1; structured += int(checked["structure_bound"])
                _need(result["code"] == checked["code"], "inputs_changed")
            else:
                # The common terminal validator above owns every no-body
                # status/code/inspection relation, including cleanup refusal.
                _need(result["body_object"] is None, "inputs_changed")
            if ordinal+1 < len(final["results"]):_need(checked is not None and checked["structure_bound"] is True, "inputs_changed")
            stopped = not (checked is not None and checked.get("structure_bound") is True)
        # Claude review section 341: as the first64 and batch readbacks do, a
        # short result list must end in its stopping refusal.
        _need(len(final["results"]) == len(plan["requests"]) or stopped, "inputs_changed")
        index_raw = read(top, "consumed-index.json"); index = _decode(index_raw)
        _need(_sha(index_raw) == final["index_sha256"] and index == {"schema":SCHEMA+"/consumed-index", "accessions":sorted(consumed),
            "previous_index_sha256":plan["consumption_sha256"], "plan_sha256":final["plan_sha256"], "unknown_prior_archive_memberships_remain_unknown":True}
            and type(final["completed_without_refusal"]) is bool
            and final["completed_without_refusal"] is (len(final["results"]) == retained == structured == len(plan["requests"])), "inputs_changed")
        _need(initial_names == [expected, claim_names, object_names], "inputs_changed")
        for folder, name, version, pin, size in pins:
            _need(base.custody._version(os.stat(name, dir_fd=folder.fd, follow_symlinks=False)) == version
                and _sha(folder.read(name, cap=size)) == pin, "inputs_changed")
        _need(initial_names == [set(os.listdir(folder.fd)) for folder in folders]
            and base.custody._version(os.fstat(lock)) == lock_version == base.custody._version(os.stat("scope.lock", dir_fd=top.fd, follow_symlinks=False)), "inputs_changed")
        return {"schema":SCHEMA+"/readback", "complete_sha256":complete_sha256, "producer_execution_identity":final["execution_identity"],
            "planned":final["planned"], "started":final["started"], "unattempted":final["unattempted"],
            "retained_bodies":retained, "structurally_bound_bodies":structured, "completed_without_refusal":final["completed_without_refusal"],
            "original_contact_privacy_rescreened":False, "new_requests":0, "authority":_authority()}
    finally:base.selector._close_all((archive.SimpleCloseFD(lock), *reversed(folders)), phase="required21_readback_cleanup")


def verify_actual(*, expected_head, complete_sha256):
    identity = _identity(expected_head)
    result = _child("readback", identity, _raw({"complete_sha256":complete_sha256})+b"\n")
    _need(type(result) is dict and set(result) == {"schema", "complete_sha256", "producer_execution_identity", "planned", "started",
        "unattempted", "retained_bodies", "structurally_bound_bodies", "completed_without_refusal", "original_contact_privacy_rescreened",
        "new_requests", "authority"} and result["schema"] == SCHEMA+"/readback" and result["complete_sha256"] == complete_sha256
        and _raw(result["authority"]) == _raw(_authority()) and result["original_contact_privacy_rescreened"] is False
        and type(result["new_requests"]) is int and result["new_requests"] == 0
        and all(type(result[key]) is int for key in ("planned", "started", "unattempted", "retained_bodies", "structurally_bound_bodies"))
        and 0 <= result["structurally_bound_bodies"] <= result["retained_bodies"] <= result["started"] <= result["planned"] <= 8
        and result["started"] > 0
        and result["unattempted"] == result["planned"]-result["started"]
        and type(result["completed_without_refusal"]) is bool
        and result["completed_without_refusal"] is (result["planned"] == result["started"] == result["retained_bodies"] == result["structurally_bound_bodies"]), "inputs_changed")
    previous._source_git(result["producer_execution_identity"])
    _need(_identity(expected_head) == identity, "source_changed")
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):raise Required21CaptureError("arguments_refused")


def main(argv=None):
    saved = contact_io._protect_stdin_echo()
    try:
        parser = _Parser(); parser.add_argument("--expected-head", required=True); parser.add_argument("--contact-stdin", action="store_true")
        args = parser.parse_args(argv); _need(args.contact_stdin, "arguments_refused")
        print(_raw(run_actual(expected_head=args.expected_head)).decode()); return 0
    except Exception as error:
        print(_raw({"schema":SCHEMA+"/refused", "code":_safe(error), "authority":_authority()}).decode()); return 2
    finally:contact_io._restore_stdin_echo(saved)


if __name__ == "__main__":raise SystemExit(main())
