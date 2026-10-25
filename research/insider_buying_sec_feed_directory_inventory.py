"""One SEC Feed directory index, never an archive or filing acquisition.

The JSON profile below is a CANDIDATE, not an observed SEC format. A safe,
complete HTTP200 response is preserved before profile parsing, so a format
refusal never justifies requesting this consumed URL again. Directory metadata
does not establish accession coverage, acceptance, publication or readiness.
"""
from __future__ import annotations

import argparse
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time
import weakref

from research import insider_buying_pilot_sec_parent_capture as publication
from research import insider_buying_sec_2006q1_parent_capture_v1 as contact_io
from research import insider_buying_sec_recovery_v4_capture as privacy
from research import insider_buying_pilot_sec_parent_audit_runner as source_runner
from research import insider_buying_earnings_archive_assessment_runner as custody
from research.insider_buying_sec_complete_acquisition import SecHttpResult
from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport, _strict_selected_response


SCHEMA = "insider-sec-feed-directory-inventory-v1"
SELF_PATH = "research/insider_buying_sec_feed_directory_inventory.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_directory_inventory.py"
LANE_ROOT, LANE_BRANCH = custody.LANE_ROOT, custody.LANE_BRANCH
ARTIFACT_PARTS = ("artifacts", "insider_buying", "sec_feed_directory_inventory_v1")
AUDIT_ID = "ib-sec-feed-directory-2021q1-20261025-once"
URL = "https://www.sec.gov/Archives/edgar/Feed/2021/QTR1/index.json"
DIRECTORY = "/Archives/edgar/Feed/2021/QTR1"
PARENT_DIRECTORY = "/Archives/edgar/Feed/2021"
PROFILE = "unobserved-strict-sec-directory-items-v1"
EMPTY_CACHE_PREFIX = "/var/empty/insider-sec-feed-directory-no-bytecode"
MAX_RESPONSE_BYTES, MAX_CONTROL_BYTES = 512 * 1024, 256 * 1024
TRANSPORT_WALL_SECONDS = 30
MIN_FREE_BYTES = 16 * 1024 * 1024
LOCK_BYTES = b"INSETF-one-shot-SEC-Feed-directory-URL-claim-v1\n"
_SHA, _HEAD = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[0-9a-f]{40}\Z")
_FILENAME = re.compile(r"(2021[0-9]{4})\.nc\.tar\.gz\Z")
_RAW_TRANSPORT = _selected_sec_transport
_TOKEN = object()
_CONTEXTS = weakref.WeakKeyDictionary()
_raw, _sha = publication._raw, publication._sha


class FeedDirectoryError(ValueError):
    """Fixed refusal codes only; no contact, headers or remote exception text."""


class _DeadlineExceeded(Exception):
    pass


class _JsonInteger(str):
    """Preserve foreign JSON numeric lexemes until the metadata schema passes."""


def _need(value, code):
    if not value:
        raise FeedDirectoryError(code)


def _authority():
    return {**publication.audit._AUTHORITY, "archive_download_authorized": False,
        "accession_coverage_established": False, "directory_is_complete_filing_population": False}


def _decode(raw, *, canonical=False):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_RESPONSE_BYTES, "bounded_json_bytes_required")
    def pairs(items):
        value = {}
        for key, item in items:
            _need(key not in value, "duplicate_json_key")
            value[key] = item
        return value
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_int=int if canonical else _JsonInteger,
            parse_float=lambda _: _need(False, "floating_json_refused"),
            parse_constant=lambda _: _need(False, "nonfinite_json_refused"))
        pending, count = [(value, 0)], 0
        while pending:
            item, depth = pending.pop(); count += 1
            _need(count <= 4096 and depth <= 24, "json_resource_bound_refused")
            if type(item) is dict:
                _need(len(item) <= 32, "json_resource_bound_refused")
                pending.extend((child, depth+1) for child in item.values())
                _need(all(type(key) is str and len(key) <= 128 for key in item), "json_key_bound_refused")
            elif type(item) is list:
                _need(len(item) <= 256, "json_resource_bound_refused")
                pending.extend((child, depth+1) for child in item)
            elif isinstance(item, str):
                _need(len(item) <= 16384, "json_string_bound_refused")
        _need(type(value) is dict and (not canonical or _raw(value) == raw), "json_object_required")
        return value
    except FeedDirectoryError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise FeedDirectoryError("json_schema_refused") from None


def parse_directory_inventory(raw):
    """Candidate metadata profile; source bytes and advertised order unchanged."""
    value = _decode(raw)
    _need(set(value) == {"directory"} and type(value["directory"]) is dict, "directory_envelope_refused")
    directory = value["directory"]
    _need(set(directory) == {"name", "parent-dir", "item"}
        and directory["name"] == DIRECTORY and directory["parent-dir"] == PARENT_DIRECTORY
        and type(directory["item"]) is list and 1 <= len(directory["item"]) <= 90,
        "directory_profile_refused")
    rows, seen = [], set()
    for ordinal, item in enumerate(directory["item"], 1):
        _need(type(item) is dict and set(item) == {"name", "type", "size", "last-modified"}
            and item["type"] == "file" and type(item["name"]) is str, "directory_item_refused")
        match = _FILENAME.fullmatch(item["name"])
        _need(match is not None and item["name"] not in seen, "directory_filename_refused")
        try: day = date.fromisoformat(match.group(1)[:4]+"-"+match.group(1)[4:6]+"-"+match.group(1)[6:])
        except ValueError: raise FeedDirectoryError("directory_date_refused") from None
        _need(date(2021, 1, 1) <= day <= date(2021, 3, 31), "directory_date_refused")
        size, modified = item["size"], item["last-modified"]
        _need(type(size) in {str, _JsonInteger} and re.fullmatch(r"0|[1-9][0-9]{0,19}", size)
            and type(modified) is str and 0 < len(modified) <= 64 and modified.isascii()
            and all(32 <= ord(char) < 127 for char in modified), "directory_advertisement_refused")
        seen.add(item["name"])
        rows.append({"source_ordinal": ordinal, "filename": item["name"], "archive_date": day.isoformat(),
            "advertised_size_text": str(size), "advertised_size_representation": "json-integer" if type(size) is _JsonInteger else "string",
            "advertised_size_numeric": int(size), "advertised_size_unit": "unknown",
            "last_modified_display_text": modified, "last_modified_timezone": "unknown",
            "archive_url": "https://www.sec.gov"+DIRECTORY+"/"+item["name"], "archive_followed": False})
    return {"schema": SCHEMA+"/candidate-inventory", "profile": PROFILE, "period": "2021Q1",
        "directory": DIRECTORY, "parent_directory": PARENT_DIRECTORY, "entries": rows,
        "entry_count": len(rows), "ordered_entries_sha256": _sha(_raw(rows)),
        "total_advertised_size_numeric": sum(row["advertised_size_numeric"] for row in rows),
        "advertised_size_unit": "unknown", "advertised_archive_bytes_measured": False,
        "missing_directory_dates_do_not_establish_absent_filings": True, "authority": _authority()}


def _scope():
    return {"schema": SCHEMA+"/scope", "audit_id": AUDIT_ID, "method": "GET", "url": URL,
        "maximum_transport_invocations": 1, "maximum_response_bytes": MAX_RESPONSE_BYTES,
        "absolute_transport_wall_seconds": TRANSPORT_WALL_SECONDS, "redirects": False,
        "retries": False, "proxies": False, "fallbacks": False, "archive_follows": False,
        "safe_complete_200_retained_before_profile_parse": True, "candidate_profile": PROFILE,
        "contact_value_stored_or_hashed": False, "authority": _authority()}


def _source_identity(value, *, root):
    _need(type(value) is dict and set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
        and value["root"] == str(root) and value["branch"] == LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and _HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and {SELF_PATH, TEST_PATH} <= set(value["source_sha256"])
        and all(type(name) is str and not Path(name).is_absolute() and ".." not in Path(name).parts
            and type(digest) is str and _SHA.fullmatch(digest) for name, digest in value["source_sha256"].items())
        and value["source_inventory_sha256"] == _sha(_raw(value["source_sha256"])), "source_identity_refused")
    return value


def _isolated():
    _need(sys.flags.isolated == sys.flags.no_site == sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "isolated_source_interpreter_required")


def _identity(head):
    _isolated()
    _need(Path(__file__).resolve() == LANE_ROOT/SELF_PATH, "inactive_source_refused")
    identity = custody._identity(head)
    own = custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH))
    for name, digest in own.items():
        _need(_sha(custody._git(LANE_ROOT, "show", head+":"+name)) == digest, "uncommitted_source_refused")
    inventory = {**identity["source_sha256"], **own}
    _need(custody._source_bytes(LANE_ROOT, tuple(source_runner.FROZEN)) == source_runner.FROZEN, "frozen_source_changed")
    return _source_identity({**identity, "source_sha256": inventory, "source_inventory_sha256": _sha(_raw(inventory))}, root=LANE_ROOT)


def _screen_body(raw, contact):
    # Screening views only. Unknown/non-UTF8 text stays byte-for-byte opaque;
    # Unicode/hex/HTML/percent echoes are checked by the existing bounded
    # decoder. These finite views are not a claim about arbitrary encodings.
    for view in (raw.decode("latin1"), raw.decode("utf-8", errors="replace")):
        privacy._screen_contact_echo(view, contact)
    for encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
        try: view = raw.decode(encoding)
        except UnicodeError: continue
        privacy._screen_contact_echo(view, contact)


class _Context:
    def __init__(self, token, root, identity, guard, run, claims, start_sha, claim_sha, headers):
        _need(token is _TOKEN, "genuine_context_required")
        self.root, self.identity, self.guard = root, identity, guard
        self.run, self.claims, self.start_sha, self.claim_sha, self.headers = run, claims, start_sha, claim_sha, headers
        self.attempted = self.raw_transport_invoked = False
        _CONTEXTS[self] = (id(guard), id(run), id(claims), start_sha, claim_sha)

    def check(self):
        _need(type(self) is _Context and _CONTEXTS.get(self) ==
            (id(self.guard), id(self.run), id(self.claims), self.start_sha, self.claim_sha), "genuine_context_required")
        _need(_identity(self.identity["head"]) == self.identity, "production_source_changed")
        self.guard(); self.run.check(); self.claims.check()
        start = _decode(self.run.read("request-start.json"), canonical=True)
        claim = _decode(self.claims.read(_claim_name()), canonical=True)
        reservation = _decode(self.run.read("reservation.json"), canonical=True)
        contact = _decode(self.run.read("contact-validated.json"), canonical=True)
        _need(_sha(_raw(start)) == self.start_sha and _sha(_raw(claim)) == self.claim_sha
            and _raw(start) == _raw({"schema": SCHEMA+"/start", "scope_sha256": _sha(_raw(_scope())),
                "reservation_sha256": _sha(_raw(reservation)), "claim_sha256": self.claim_sha, "attempt": 1})
            and _raw(claim) == _raw({"schema": SCHEMA+"/url-claim", "method": "GET", "url": URL,
                "scope_sha256": _sha(_raw(_scope())), "reservation_sha256": _sha(_raw(reservation))})
            and _raw(reservation) == _raw(_reservation(self.identity, False))
            and _raw(contact) == _raw({"schema": SCHEMA+"/contact", "reservation_sha256": _sha(_raw(reservation)),
                "contact_present": True, "contact_value_stored_or_hashed": False}), "durable_start_context_refused")


def _production_transport(context):
    _need(type(context) is _Context and context.root == LANE_ROOT and not context.attempted,
        "fixed_production_context_required")
    _need(threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer")
        and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "absolute_deadline_unavailable")
    # Custody refusal before this point is local, not a measured invocation of
    # the raw HTTP transport. The absolute alarm bounds open and every read.
    context.check()
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_): raise _DeadlineExceeded()
    signal.signal(signal.SIGALRM, expired)
    begun = time.monotonic()
    try:
        signal.setitimer(signal.ITIMER_REAL, TRANSPORT_WALL_SECONDS)
        context.attempted = True; context.raw_transport_invoked = True
        response = _RAW_TRANSPORT(URL, context.headers, MAX_RESPONSE_BYTES)
        _need(time.monotonic()-begun <= TRANSPORT_WALL_SECONDS, "transport_deadline_refused")
        return response
    except _DeadlineExceeded:
        raise FeedDirectoryError("transport_deadline_refused") from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def _claim_name():
    return _sha(b"GET\x00"+URL.encode("ascii"))+".json"


def _reservation(identity, fixture):
    return {"schema": SCHEMA+"/reservation", "audit_id": AUDIT_ID, "fixture_only": fixture,
        "scope": _scope(), "scope_sha256": _sha(_raw(_scope())), "execution_identity": identity}


def _run(*, root, identity, guard, contact, transport, fixture):
    _need(type(fixture) is bool and callable(guard) and callable(contact), "mode_callbacks_required")
    if fixture:
        publication._fixture_root(root)
        _need(callable(transport) and transport is not _RAW_TRANSPORT and transport is not _production_transport
            and contact not in {contact_io._stdin_contact, contact_io._getpass_contact}, "invented_callbacks_required")
        publication._native_fixture_denial()
    else:
        _need(root == LANE_ROOT and transport is _production_transport
            and contact in {contact_io._stdin_contact, contact_io._getpass_contact}, "fixed_production_front_required")
        _need(_identity(identity["head"]) == identity, "production_source_changed")
    _source_identity(identity, root=root); guard()
    folders, lock_fd, locked = [], None, False
    try:
        base = publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS), create=True); folders.append(base)
        claims = publication._NewDirectory(base.path/"claims", create=True); folders.append(claims)
        runs = publication._NewDirectory(base.path/"runs", create=True); folders.append(runs)
        if not base.tree.exists("scope.lock"): base.publish("scope.lock", LOCK_BYTES)
        lock_fd = os.open("scope.lock", os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=base.fd)
        lock_version = publication._version(os.fstat(lock_fd)); fcntl.flock(lock_fd, fcntl.LOCK_EX|fcntl.LOCK_NB); locked = True
        _need(base.read("scope.lock") == LOCK_BYTES and set(os.listdir(base.fd)) == {"scope.lock", "claims", "runs"}
            and not os.listdir(claims.fd) and not os.listdir(runs.fd), "one_shot_scope_cannot_resume")
        capacity = os.fstatvfs(base.fd)
        _need(capacity.f_bavail*capacity.f_frsize >= MIN_FREE_BYTES+MAX_RESPONSE_BYTES, "publication_disk_reserve_refused")
        os.mkdir(AUDIT_ID, 0o700, dir_fd=runs.fd); os.fsync(runs.fd)
        run = publication._NewDirectory(runs.path/AUDIT_ID); folders.append(run)
        expected_run, expected_claims = set(), set()
        def check():
            guard()
            _need(publication._version(os.fstat(lock_fd)) == lock_version ==
                publication._version(os.stat("scope.lock", dir_fd=base.fd, follow_symlinks=False)), "scope_lock_changed")
            for folder in folders: folder.check()
            _need(set(os.listdir(base.fd)) == {"scope.lock", "claims", "runs"}
                and set(os.listdir(runs.fd)) == {AUDIT_ID} and set(os.listdir(run.fd)) == expected_run
                and set(os.listdir(claims.fd)) == expected_claims, "scope_inventory_changed")
        def publish(name, value):
            digest = run.publish(name, _raw(value), cap=MAX_CONTROL_BYTES); expected_run.add(name); check(); return digest
        reservation_sha = publish("reservation.json", _reservation(identity, fixture))
        contact_value = privacy._contact(contact(), observed=not fixture)
        publish("contact-validated.json", {"schema": SCHEMA+"/contact", "reservation_sha256": reservation_sha,
            "contact_present": True, "contact_value_stored_or_hashed": False})
        claim_sha = claims.publish(_claim_name(), _raw({"schema": SCHEMA+"/url-claim", "method": "GET", "url": URL,
            "scope_sha256": _sha(_raw(_scope())), "reservation_sha256": reservation_sha}))
        expected_claims.add(_claim_name()); check()
        start_sha = publish("request-start.json", {"schema": SCHEMA+"/start", "scope_sha256": _sha(_raw(_scope())),
            "reservation_sha256": reservation_sha, "claim_sha256": claim_sha, "attempt": 1})
        headers = {"User-Agent": "InsiderBuyingResearch-FeedDirectory/1.0 ("+contact_value+")",
            "Accept": "application/json", "Accept-Encoding": "identity", "Connection": "close"}
        response = None; context = None
        try:
            if fixture: response = transport(URL, headers, MAX_RESPONSE_BYTES)
            else:
                context = _Context(_TOKEN, root, identity, check, run, claims, start_sha, claim_sha, headers)
                response = _production_transport(context)
        except Exception:
            if not fixture and (context is None or not context.raw_transport_invoked):
                raise FeedDirectoryError("transport_front_refused_before_raw_invocation") from None
        check()
        status = response_sha = response_bytes = header_sha = inventory_sha = None
        inventory = None; disposition = "ambiguous_transport_failure_no_retry"; retained = False
        if response is not None:
            _need(type(response) is SecHttpResult and type(response.status) is int and 100 <= response.status <= 599,
                "transport_response_metadata_refused")
            status = response.status; disposition = "http_refused_no_body_no_retry"
            if status == 200:
                try:
                    _need(type(response.headers) is tuple and len(response.headers) <= 64
                        and all(type(pair) is tuple and len(pair) == 2 and all(type(v) is str for v in pair) for pair in response.headers)
                        and len(_raw(response.headers)) <= 16384, "response_header_bounds_refused")
                    for pair in response.headers:
                        for field in pair: privacy._screen_contact_echo(field, contact_value)
                    body = _strict_selected_response(response, max_bytes=MAX_RESPONSE_BYTES)
                    _screen_body(body, contact_value)
                    header_sha = _sha(_raw(response.headers))
                except Exception:
                    disposition = "response_privacy_or_framing_refused_no_retry"
                else:
                    # Publication is outside the privacy/parse exception handler:
                    # local custody failure is never relabelled a remote refusal.
                    response_sha = run.publish("response.bin", body, cap=MAX_RESPONSE_BYTES)
                    expected_run.add("response.bin"); check(); response_bytes = len(body); retained = True
                    publish("response-headers.json", {"headers": response.headers})
                    try: inventory = parse_directory_inventory(body)
                    except FeedDirectoryError:
                        disposition = "opaque_response_retained_inventory_unqualified"
                    else:
                        inventory_sha = publish("inventory.json", inventory)
                        disposition = "directory_inventory_candidate_profile_accepted"
        result = {"schema": SCHEMA+"/result", "reservation_sha256": reservation_sha, "claim_sha256": claim_sha,
            "start_sha256": start_sha, "http_status": status, "transport_invocations": 1,
            "disposition": disposition, "response_retained": retained, "response_sha256": response_sha,
            "response_bytes": response_bytes, "response_headers_sha256": header_sha,
            "inventory_sha256": inventory_sha, "inventory_qualified": inventory is not None,
            "archive_requests": 0, "accession_requests": 0, "contact_value_stored_or_hashed": False}
        result_sha = publish("request-result.json", result)
        complete = {"schema": SCHEMA+"/complete", "audit_id": AUDIT_ID, "fixture_only": fixture,
            "execution_identity": identity, "scope_sha256": _sha(_raw(_scope())), "reservation_sha256": reservation_sha,
            "result_sha256": result_sha, "result": result, "directory_inventory_completed": inventory is not None,
            "archive_requests": 0, "accession_requests": 0, "credential_reads": 0, "qc_accesses": 0,
            "outcome_looks": 0, "backtests": 0, "authority": _authority()}
        complete_sha = publish("complete.json", complete); check()
        return {"audit_id": AUDIT_ID, "report_sha256": complete_sha, "disposition": disposition,
            "directory_inventory_completed": inventory is not None, "transport_invocations": 1,
            "http_status": status, "response_retained": retained, "response_sha256": response_sha,
            "response_bytes": response_bytes, "inventory_sha256": inventory_sha,
            "archive_requests": 0, "accession_requests": 0, "authority": _authority()}
    finally:
        publication._close_all(folders, None, lock_fd, locked)


def run_actual_probe(expected_head, *, contact_mode="stdin"):
    _need(contact_mode in {"stdin", "getpass"}, "private_contact_mode_refused")
    before = _identity(expected_head)
    def guard(): _need(_identity(expected_head) == before, "committed_source_changed")
    return _run(root=LANE_ROOT, identity=before, guard=guard,
        contact=contact_io._stdin_contact if contact_mode == "stdin" else contact_io._getpass_contact,
        transport=_production_transport, fixture=False)


def _run_invented_probe(*, root, transport, contact=lambda: "invented@unit.test", guard=lambda: None):
    publication._fixture_root(root)
    _need(callable(transport) and transport is not _RAW_TRANSPORT and transport is not _production_transport
        and contact not in {contact_io._stdin_contact, contact_io._getpass_contact}, "invented_callbacks_required")
    publication._native_fixture_denial()
    sources = {SELF_PATH: "a"*64, TEST_PATH: "b"*64}
    identity = {"root": str(root), "branch": LANE_BRANCH, "head": "a"*40, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    return _run(root=root, identity=identity, guard=guard, contact=contact, transport=transport, fixture=True)


def _verify(root, expected_report_sha256, fixture, identity=None):
    _need(type(expected_report_sha256) is str and _SHA.fullmatch(expected_report_sha256), "report_digest_required")
    folders = []
    try:
        base = publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS)); folders.append(base)
        claims = publication._NewDirectory(base.path/"claims"); folders.append(claims)
        runs = publication._NewDirectory(base.path/"runs"); folders.append(runs)
        run = publication._NewDirectory(runs.path/AUDIT_ID); folders.append(run)
        _need(set(os.listdir(base.fd)) == {"scope.lock", "claims", "runs"} and base.read("scope.lock") == LOCK_BYTES
            and set(os.listdir(runs.fd)) == {AUDIT_ID} and set(os.listdir(claims.fd)) == {_claim_name()}, "readback_scope_refused")
        complete_raw = run.read("complete.json"); _need(_sha(complete_raw) == expected_report_sha256, "report_pin_refused")
        complete = _decode(complete_raw, canonical=True); result_raw = run.read("request-result.json")
        result = _decode(result_raw, canonical=True); reservation_raw = run.read("reservation.json")
        reservation = _decode(reservation_raw, canonical=True); actual_identity = reservation.get("execution_identity")
        _source_identity(actual_identity, root=root)
        _need(identity is None or actual_identity == identity, "readback_execution_identity_refused")
        _need(reservation_raw == _raw(_reservation(actual_identity, fixture)), "readback_reservation_refused")
        claim_raw = claims.read(_claim_name()); claim = _decode(claim_raw, canonical=True)
        start_raw = run.read("request-start.json"); start = _decode(start_raw, canonical=True)
        _need(claim_raw == _raw({"schema": SCHEMA+"/url-claim", "method": "GET", "url": URL,
                "scope_sha256": _sha(_raw(_scope())), "reservation_sha256": _sha(reservation_raw)})
            and start_raw == _raw({"schema": SCHEMA+"/start", "scope_sha256": _sha(_raw(_scope())),
                "reservation_sha256": _sha(reservation_raw), "claim_sha256": _sha(claim_raw), "attempt": 1})
            and run.read("contact-validated.json") == _raw({"schema": SCHEMA+"/contact",
                "reservation_sha256": _sha(reservation_raw), "contact_present": True,
                "contact_value_stored_or_hashed": False}), "readback_claim_start_refused")
        _need(set(result) == {"schema", "reservation_sha256", "claim_sha256", "start_sha256", "http_status", "transport_invocations",
            "disposition", "response_retained", "response_sha256", "response_bytes", "response_headers_sha256", "inventory_sha256",
            "inventory_qualified", "archive_requests", "accession_requests", "contact_value_stored_or_hashed"}
            and result["schema"] == SCHEMA+"/result" and result["reservation_sha256"] == _sha(reservation_raw)
            and result["claim_sha256"] == _sha(claim_raw) and result["start_sha256"] == _sha(start_raw)
            and type(result["transport_invocations"]) is int and result["transport_invocations"] == 1
            and result["contact_value_stored_or_hashed"] is False, "readback_result_refused")
        for key in ("archive_requests", "accession_requests"):
            _need(type(result[key]) is int and result[key] == 0, "readback_access_refused")
        _need(type(result["response_retained"]) is bool and type(result["inventory_qualified"]) is bool
            and (result["http_status"] is None or type(result["http_status"]) is int and 100 <= result["http_status"] <= 599),
            "readback_result_types_refused")
        expected = {"reservation.json", "contact-validated.json", "request-start.json", "request-result.json", "complete.json"}
        inventory = None
        if result["response_retained"]:
            raw = run.read("response.bin", cap=MAX_RESPONSE_BYTES); expected.add("response.bin")
            headers = _decode(run.read("response-headers.json"), canonical=True); expected.add("response-headers.json")
            _need(set(headers) == {"headers"} and type(headers["headers"]) is list and len(headers["headers"]) <= 64
                and all(type(pair) is list and len(pair) == 2 and all(type(v) is str for v in pair) for pair in headers["headers"]),
                "readback_headers_refused")
            pairs = tuple(tuple(pair) for pair in headers["headers"])
            _need(result["http_status"] == 200 and type(result["response_bytes"]) is int and len(raw) == result["response_bytes"]
                and _sha(raw) == result["response_sha256"] and type(result["response_headers_sha256"]) is str
                and _sha(_raw(pairs)) == result["response_headers_sha256"]
                and _strict_selected_response(SecHttpResult(200, pairs, raw), max_bytes=MAX_RESPONSE_BYTES) == raw,
                "readback_response_refused")
            try: inventory = parse_directory_inventory(raw)
            except FeedDirectoryError: pass
            _need(result["inventory_qualified"] is (inventory is not None), "readback_profile_refused")
            if inventory is not None:
                inventory_raw = run.read("inventory.json"); expected.add("inventory.json")
                _need(inventory_raw == _raw(inventory) and _sha(inventory_raw) == result["inventory_sha256"]
                    and result["disposition"] == "directory_inventory_candidate_profile_accepted", "readback_inventory_refused")
            else:
                _need(result["inventory_sha256"] is None and result["disposition"] ==
                    "opaque_response_retained_inventory_unqualified", "readback_opaque_refused")
        else:
            _need(result["response_sha256"] is result["response_bytes"] is result["response_headers_sha256"] is result["inventory_sha256"] is None
                and result["inventory_qualified"] is False and result["disposition"] ==
                    ("ambiguous_transport_failure_no_retry" if result["http_status"] is None else
                     "response_privacy_or_framing_refused_no_retry" if result["http_status"] == 200 else "http_refused_no_body_no_retry"),
                "readback_unretained_refused")
        expected_complete = {"schema": SCHEMA+"/complete", "audit_id": AUDIT_ID, "fixture_only": fixture,
            "execution_identity": actual_identity, "scope_sha256": _sha(_raw(_scope())), "reservation_sha256": _sha(reservation_raw),
            "result_sha256": _sha(result_raw), "result": result, "directory_inventory_completed": inventory is not None,
            "archive_requests": 0, "accession_requests": 0, "credential_reads": 0, "qc_accesses": 0,
            "outcome_looks": 0, "backtests": 0, "authority": _authority()}
        _need(complete_raw == _raw(expected_complete) and set(os.listdir(run.fd)) == expected, "readback_complete_refused")
        for folder in folders: folder.check()
        return {"audit_id": AUDIT_ID, "report_sha256": expected_report_sha256,
            "directory_inventory_completed": inventory is not None, "disposition": result["disposition"],
            "response_sha256": result["response_sha256"], "response_bytes": result["response_bytes"],
            "transport_invocations": 1, "archive_requests": 0, "accession_requests": 0, "authority": _authority()}
    finally: publication._close_all(folders, None, None, False)


def verify_invented_probe(root, expected_report_sha256):
    publication._fixture_root(root); publication._native_fixture_denial()
    return _verify(root, expected_report_sha256, True)


def verify_actual_probe(*, expected_report_sha256, execution_identity):
    _isolated(); source_runner._prove_isolation()
    identity = _source_identity(execution_identity, root=LANE_ROOT)
    def current():
        _need(custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"]
            and custody._source_bytes(LANE_ROOT, tuple(source_runner.FROZEN)) == source_runner.FROZEN,
            "readback_current_or_frozen_source_changed")
    current(); result = _verify(LANE_ROOT, expected_report_sha256, False, identity); current()
    return {**result, "native_network_fork_allwrite_securityexec_denial": True,
        "source_identity_semantics": "trusted_launcher_git_identity_independent_child_current_and_frozen_bytes",
        "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--expected-head", required=True)
    parser.add_argument("--contact-mode", choices=("stdin", "getpass"), default="stdin")
    args = parser.parse_args(argv); saved = contact_io._protect_stdin_echo()
    try:
        result = run_actual_probe(args.expected_head, contact_mode=args.contact_mode)
        print(_raw(result).decode()); return 0 if result["directory_inventory_completed"] else 2
    except Exception:
        sys.stderr.write("REFUSED: directory probe stopped; preserve its URL claim and original response\n"); return 2
    finally: contact_io._restore_stdin_echo(saved)


if __name__ == "__main__":
    raise SystemExit(main())
