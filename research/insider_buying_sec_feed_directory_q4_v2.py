"""One NEW 2020Q4 SEC Feed JSON listing, never an archive acquisition.

All earlier Q1/Q2 requests and namespaces remain consumed and untouched.
The five-string JSON/href/KB profile was previously qualified on retained Q2
bytes; its Q4 applicability is prospective. A safe,
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
import stat
import sys
import threading
import time
import weakref

from research import insider_buying_pilot_sec_parent_capture as publication
from research import insider_buying_sec_feed_directory_inventory as foreign_json
from research import insider_buying_sec_feed_directory_stopped_controls as control_codec
from research import insider_buying_sec_2006q1_parent_capture_v1 as contact_io
from research import insider_buying_sec_recovery_v4_capture as privacy
from research import insider_buying_pilot_sec_parent_audit_runner as source_runner
from research import insider_buying_earnings_archive_assessment_runner as custody
from research.insider_buying_sec_complete_acquisition import SecHttpResult
from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport, _strict_selected_response


SCHEMA = "insider-sec-feed-directory-q4-v2"
SELF_PATH = "research/insider_buying_sec_feed_directory_q4_v2.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_directory_q4_v2.py"
LANE_ROOT, LANE_BRANCH = custody.LANE_ROOT, custody.LANE_BRANCH
ARTIFACT_PARTS = ("artifacts", "insider_buying", "sec_feed_directory_q4_v2")
AUDIT_ID = "ib-sec-feed-directory-2020q4-20261025-once"
URL = "https://www.sec.gov/Archives/edgar/Feed/2020/QTR4/index.json"
DIRECTORY = "/Archives/edgar/Feed/2020/QTR4"
PARENT_DIRECTORY = "/Archives/edgar/Feed/2020"
PROFILE = "retained-q2-five-string-href-KB-profile-applied-to-q4-v2"
EMPTY_CACHE_PREFIX = "/var/empty/insider-sec-feed-directory-q4-v2-no-bytecode"
MAX_RESPONSE_BYTES, MAX_CONTROL_BYTES = 512 * 1024, 256 * 1024
TRANSPORT_WALL_SECONDS = 30
MIN_FREE_BYTES = 16 * 1024 * 1024
REUSED_HELPER_SHA256 = {
    foreign_json.SELF_PATH: control_codec.FAILED_SOURCE_SHA256,
    foreign_json.TEST_PATH: control_codec.FAILED_TEST_SHA256,
    control_codec.SELF_PATH: "d2f95bff32c9fa38b0fac9a944e621522f8591dff29d46b04f8e7fce0c165b4b",
    control_codec.TEST_PATH: "9868b4d12f2b19dbb9392f0d763a9b2c28bffa347682c7a64c9efadac695ebb4",
}
LOCK_BYTES = b"INSETF-one-shot-SEC-Feed-directory-2020Q4-URL-claim-v2\n"
_SHA, _HEAD = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[0-9a-f]{40}\Z")

_RAW_TRANSPORT = _selected_sec_transport
_TOKEN = object()
_CONTEXTS = weakref.WeakKeyDictionary()
_ACTIVATIONS = weakref.WeakKeyDictionary()
_raw, _sha = publication._raw, publication._sha


class FeedDirectoryError(ValueError):
    """Fixed refusal codes only; no contact, headers or remote exception text."""


_STAGES = frozenset({"arguments", "source_identity", "native_source_preflight", "activation", "capture",
    "namespace", "scope_lock", "capacity", "reservation", "contact_validation", "url_claim", "durable_start",
    "transport", "post_transport_custody", "response_validation", "response_publication", "profile_parse",
    "inventory_publication", "result_publication", "complete_publication", "final_custody", "cleanup"})
_PUBLIC_CODES = frozenset({"private_arguments_refused", "private_contact_mode_refused", "source_identity_refused",
    "native_source_preflight_refused", "trusted_actual_activation_required", "committed_source_changed",
    "current_or_frozen_source_changed", "source_roster_refused", "loaded_source_uninventoried", "frozen_source_changed",
    "reused_helper_source_changed", "inactive_source_refused", "isolated_source_interpreter_required",
    "precontact_control_roundtrip_refused", "one_shot_scope_cannot_resume", "publication_disk_reserve_refused",
    "scope_lock_changed", "scope_inventory_changed", "transport_front_refused_before_raw_invocation",
    "transport_deadline_refused", "deadline_cleanup_refused", "canonical_control_refused", "fresh_namespace_already_exists", "local_operation_refused"})


def _classified(stage, exc):
    # Foreign messages/args are never rendered. Even an own exception must
    # carry an exact allowlisted code; this is a finite diagnostic, not a trace.
    inherited = getattr(exc, "stage", None) if type(exc) is FeedDirectoryError else None
    stage = inherited if type(inherited) is str and inherited in _STAGES else stage if type(stage) is str and stage in _STAGES else "capture"
    code = exc.args[0] if type(exc) is FeedDirectoryError and len(exc.args) == 1 and type(exc.args[0]) is str else None
    value = FeedDirectoryError(code if code in _PUBLIC_CODES else "local_operation_refused")
    value.stage = stage
    return value


class _DeadlineExceeded(Exception):
    pass


_JsonInteger = foreign_json._JsonInteger

def _need(value, code):
    if not value:
        raise FeedDirectoryError(code)


def _authority():
    return {**publication.audit._AUTHORITY, "archive_download_authorized": False,
        "accession_coverage_established": False, "directory_is_complete_filing_population": False}


def _decode(raw, *, canonical=False):
    # Distinct qualified codecs, never the foreign 32-key bound for controls.
    try:
        return control_codec._decode_control(raw) if canonical else foreign_json._decode(raw)
    except (control_codec.StoppedControlError, foreign_json.FeedDirectoryError):
        raise FeedDirectoryError("canonical_control_refused" if canonical else "foreign_json_refused") from None


def parse_directory_inventory(raw):
    """Qualified five-string profile, prospectively applied to ONE Q4 listing.

    Lookup identity is the fixed HTTP URL, never the opaque display strings.
    KB magnitudes are lexical advertisements, not measured payload byte sizes.
    """
    value = _decode(raw)
    _need(set(value) == {"directory"} and type(value["directory"]) is dict, "directory_envelope_refused")
    directory = value["directory"]
    _need(set(directory) == {"name", "parent-dir", "item"}
        and type(directory["name"]) is type(directory["parent-dir"]) is str
        and len(directory["name"]) <= 1024 and len(directory["parent-dir"]) <= 1024
        and type(directory["item"]) is list and 1 <= len(directory["item"]) <= 92, "directory_profile_refused")
    entries, seen = [], set()
    for ordinal, item in enumerate(directory["item"], 1):
        _need(type(item) is dict and set(item) == {"href", "last-modified", "name", "size", "type"}
            and all(type(child) is str for child in item.values()) and item["type"] == "file", "directory_item_refused")
        name, href = item["name"], item["href"]
        match = re.fullmatch(r"(2020[0-9]{4})\.nc\.tar\.gz", name)
        _need(match is not None and name not in seen, "directory_filename_refused")
        try: day = date.fromisoformat(name[:4]+"-"+name[4:6]+"-"+name[6:8])
        except ValueError: raise FeedDirectoryError("directory_date_refused") from None
        _need(date(2020, 10, 1) <= day <= date(2020, 12, 31), "directory_date_refused")
        forms = {name:"relative-filename", "./"+name:"dot-relative-filename",
            DIRECTORY+"/"+name:"absolute-path", URL.removesuffix("index.json")+name:"absolute-https-www-sec"}
        _need(href in forms, "directory_same_item_href_refused")
        size = re.fullmatch(r"(?P<magnitude>(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,6})?) KB", item["size"])
        _need(size is not None and any(c in "123456789" for c in size["magnitude"]), "directory_advertised_KB_lexeme_refused")
        modified = item["last-modified"]
        _need(len(modified) <= 128 and modified.isascii() and all(32 <= ord(c) < 127 for c in modified),
            "directory_modified_display_refused")
        seen.add(name)
        entries.append({"source_ordinal":ordinal, "listed_name":name, "archive_date":day.isoformat(),
            "listed_href":href, "href_form":forms[href], "qualified_archive_url":URL.removesuffix("index.json")+name,
            "advertised_size_text":item["size"], "advertised_magnitude_text":size["magnitude"], "advertised_unit":"KB",
            "advertised_unit_base_qualified":False, "advertised_rounding_qualified":False, "actual_archive_bytes_known":False,
            "last_modified_display_text":modified, "last_modified_timezone_qualified":False,
            "source_item_canonical_sha256":_sha(_raw({"source_ordinal":ordinal,"item":item})), "archive_followed":False})
    return {"schema":SCHEMA+"/candidate-inventory", "profile":PROFILE, "period":"2020Q4",
        "lookup_request_url":URL, "lookup_directory_url":URL.removesuffix("index.json"),
        "lookup_identity_basis":"fixed hash-bound request URL, not directory display strings",
        "directory_display_strings_used_for_identity":False, "entries":entries, "entry_count":len(entries),
        "ordered_entries_sha256":_sha(_raw(entries)),
        "source_item_hash_semantics":"canonical ordinal and exact parsed five-string advertisement; not raw JSON substring",
        "advertised_size_is_not_measured_payload_bytes":True, "advertised_KB_base_qualified":False,
        "advertised_rounding_qualified":False, "missing_directory_dates_do_not_establish_absent_filings":True,
        "archive_selected":False, "authority":_authority()}


def _scope():
    return {"schema": SCHEMA+"/scope", "audit_id": AUDIT_ID, "method": "GET", "url": URL,
        "maximum_transport_invocations": 1, "maximum_response_bytes": MAX_RESPONSE_BYTES,
        "absolute_transport_wall_seconds": TRANSPORT_WALL_SECONDS, "redirects": False,
        "retries": False, "proxies": False, "fallbacks": False, "archive_follows": False,
        "safe_complete_200_retained_before_profile_parse": True, "candidate_profile": PROFILE,
        "listing_representation":"JSON only; no HTML alias fallback", "archive_selection_authorized":False,
        "contact_value_stored_or_hashed": False,
        "canonical_control_codec": "separate-own-controls-2048-keys-8192-nodes-256KiB",
        "precontact_full_identity_control_roundtrip": True,
        "exclusive_fresh_final_namespace_required": True,
        "earlier_q1_q2_scopes_preserved_not_resumed": True, "authority": _authority()}


def _source_identity(value, *, root):
    _need(type(value) is dict and set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
        and value["root"] == str(root) and value["branch"] == LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and _HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and {SELF_PATH, TEST_PATH} <= set(value["source_sha256"])
        and all(type(name) is str and re.fullmatch(r"(?:[A-Za-z_][A-Za-z_0-9]*/)*[A-Za-z_][A-Za-z_0-9]*\.py", name)
            and type(digest) is str and _SHA.fullmatch(digest) for name, digest in value["source_sha256"].items())
        and 1 <= len(value["source_sha256"]) <= 2048
        and all(len(name) <= 512 and all(part not in {"", ".", ".."} for part in name.split("/")) for name in value["source_sha256"])
        and value["source_inventory_sha256"] == _sha(_raw(value["source_sha256"])), "source_identity_refused")
    return value


def _isolated():
    _need(sys.flags.isolated == sys.flags.no_site == sys.flags.no_user_site == sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "isolated_source_interpreter_required")


def _identity(head):
    _isolated()
    _need(Path(__file__).resolve() == LANE_ROOT/SELF_PATH, "inactive_source_refused")
    identity = custody._identity(head)
    own = custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH, *REUSED_HELPER_SHA256))
    for name, digest in own.items():
        _need(_sha(custody._git(LANE_ROOT, "show", head+":"+name)) == digest, "uncommitted_source_refused")
    inventory = {**identity["source_sha256"], **own}
    _need(custody._source_bytes(LANE_ROOT, tuple(source_runner.FROZEN)) == source_runner.FROZEN, "frozen_source_changed")
    _need(custody._source_bytes(LANE_ROOT, tuple(REUSED_HELPER_SHA256)) == REUSED_HELPER_SHA256, "reused_helper_source_changed")
    return _source_identity({**identity, "source_sha256": inventory, "source_inventory_sha256": _sha(_raw(inventory))}, root=LANE_ROOT)


def _current(identity):
    _source_identity(identity, root=LANE_ROOT)
    _need({SELF_PATH, TEST_PATH, *REUSED_HELPER_SHA256} <= set(identity["source_sha256"]), "source_roster_refused")
    _need(custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"]
        and custody._source_bytes(LANE_ROOT, tuple(source_runner.FROZEN)) == source_runner.FROZEN
        and custody._source_bytes(LANE_ROOT, tuple(REUSED_HELPER_SHA256)) == REUSED_HELPER_SHA256,
        "current_or_frozen_source_changed")
    for module in tuple(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if type(path) is str and Path(path).suffix == ".py" and Path(path).is_relative_to(LANE_ROOT):
            _need(str(Path(path).relative_to(LANE_ROOT)) in identity["source_sha256"], "loaded_source_uninventoried")


def _preflight_worker(identity):
    _isolated(); source_runner._prove_isolation(); _current(identity)
    controls = _preflight_controls(identity, False, root=LANE_ROOT)
    _current(identity)
    return {"schema": SCHEMA+"/source-preflight", "source_inventory_sha256": identity["source_inventory_sha256"],
        "control_sizes": {name: len(raw) for name, raw in controls.items()},
        "native_network_fork_allwrite_securityexec_denial": True, "provider_requests": 0, "contact_reads": 0}


def _preflight_command(identity):
    code = ("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;"
        "from research import insider_buying_sec_feed_directory_q4_v2 as m;identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._preflight_worker(identity)\nexcept Exception: print('{\"refused\":true}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix="+EMPTY_CACHE_PREFIX, "-c", code)


def _native_preflight(identity):
    _current(identity)
    expected = {"schema": SCHEMA+"/source-preflight", "source_inventory_sha256": identity["source_inventory_sha256"],
        "control_sizes": {name: len(raw) for name, raw in _preflight_controls(identity, False, root=LANE_ROOT).items()},
        "native_network_fork_allwrite_securityexec_denial": True, "provider_requests": 0, "contact_reads": 0}
    child = source_runner.launcher.run_child(_preflight_command(identity), cwd=LANE_ROOT, env=None, timeout=60, cap=MAX_CONTROL_BYTES)
    _need(child.returncode == 0 and child.stderr == b"" and child.stdout == _raw(expected)+b"\n", "native_source_preflight_refused")
    _current(identity)


class _Activation:
    def __init__(self, identity, guard):
        self.identity, self.guard = identity, guard


def _activated(value, identity):
    _need(type(value) is _Activation and _ACTIVATIONS.get(value) == (_raw(identity), id(value.guard))
        and _raw(value.identity) == _raw(identity), "trusted_actual_activation_required")
    value.guard()


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
    def __init__(self, token, root, identity, guard, run, claims, start_sha, claim_sha, headers, activation=None):
        _need(token is _TOKEN, "genuine_context_required")
        self.root, self.identity, self.guard = root, identity, guard
        self.run, self.claims, self.start_sha, self.claim_sha, self.headers = run, claims, start_sha, claim_sha, headers
        self.attempted = self.raw_transport_invoked = False
        self.activation = activation

    def check(self):
        _need(type(self) is _Context and _CONTEXTS.get(self) ==
            (id(self.activation), id(self.guard), id(self.run), id(self.claims), self.start_sha, self.claim_sha, _raw(self.headers)), "genuine_context_required")
        _activated(self.activation, self.identity)
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
        active, failed = sys.exc_info()[0] is not None, False
        try: signal.setitimer(signal.ITIMER_REAL, 0)
        except BaseException: failed = True
        try: signal.signal(signal.SIGALRM, previous)
        except BaseException: failed = True
        if failed and not active: raise FeedDirectoryError("deadline_cleanup_refused")


def _claim_name():
    return _sha(b"GET\x00"+URL.encode("ascii"))+".json"


def _reservation(identity, fixture):
    return {"schema": SCHEMA+"/reservation", "audit_id": AUDIT_ID, "fixture_only": fixture,
        "scope": _scope(), "scope_sha256": _sha(_raw(_scope())), "execution_identity": identity}


def _complete_control(identity, fixture, reservation_sha, result, result_sha, qualified):
    return {"schema": SCHEMA+"/complete", "audit_id": AUDIT_ID, "fixture_only": fixture,
        "execution_identity": identity, "scope_sha256": _sha(_raw(_scope())), "reservation_sha256": reservation_sha,
        "result_sha256": result_sha, "result": result, "directory_inventory_completed": qualified,
        "archive_requests": 0, "accession_requests": 0, "credential_reads": 0, "qc_accesses": 0,
        "outcome_looks": 0, "backtests": 0, "authority": _authority()}


def _preflight_controls(identity, fixture, *, root):
    """Validate full production-sized local controls before any namespace/contact."""
    _need(type(fixture) is bool, "preflight_fixture_mode_required")
    _source_identity(identity, root=root)
    forms = {"identity": identity, "reservation": _reservation(identity, fixture)}
    reservation_sha = _sha(_raw(forms["reservation"]))
    forms["claim"] = {"schema": SCHEMA+"/url-claim", "method": "GET", "url": URL,
        "scope_sha256": _sha(_raw(_scope())), "reservation_sha256": reservation_sha}
    forms["start"] = {"schema": SCHEMA+"/start", "scope_sha256": _sha(_raw(_scope())),
        "reservation_sha256": reservation_sha, "claim_sha256": _sha(_raw(forms["claim"])), "attempt": 1}
    forms["contact"] = {"schema": SCHEMA+"/contact", "reservation_sha256": reservation_sha,
        "contact_present": True, "contact_value_stored_or_hashed": False}
    # Unpublished capacity templates, NOT a request/result/receipt observation.
    # Their exact wrapper constructor is also used after real execution and
    # independent readback, including the entire production-sized identity.
    forms["capacity_result"] = {"schema": SCHEMA+"/result", "reservation_sha256": reservation_sha,
        "claim_sha256": _sha(_raw(forms["claim"])), "start_sha256": _sha(_raw(forms["start"])),
        "http_status": 200, "transport_invocations": 1, "disposition": "directory_inventory_candidate_profile_accepted",
        "response_retained": True, "response_sha256": "0"*64, "response_bytes": MAX_RESPONSE_BYTES,
        "response_headers_sha256": "0"*64, "inventory_sha256": "0"*64, "inventory_qualified": True,
        "archive_requests": 0, "accession_requests": 0, "contact_value_stored_or_hashed": False}
    forms["capacity_complete"] = _complete_control(identity, fixture, reservation_sha, forms["capacity_result"],
        _sha(_raw(forms["capacity_result"])), True)
    raw_forms = {}
    for name, value in forms.items():
        raw = _raw(value)
        _need(0 < len(raw) <= MAX_CONTROL_BYTES and _raw(_decode(raw, canonical=True)) == raw,
            "precontact_control_roundtrip_refused")
        raw_forms[name] = raw
    return raw_forms


def _run(*, root, identity, guard, contact, transport, fixture, activation=None):
    _need(type(fixture) is bool and callable(guard) and callable(contact), "mode_callbacks_required")
    if fixture:
        publication._fixture_root(root)
        _need(callable(transport) and transport is not _RAW_TRANSPORT and transport is not _production_transport
            and contact not in {contact_io._stdin_contact, contact_io._getpass_contact}, "invented_callbacks_required")
        publication._native_fixture_denial()
    else:
        _need(root == LANE_ROOT and transport is _production_transport
            and contact is contact_io._stdin_contact, "fixed_production_front_required")
        _activated(activation, identity)
    _source_identity(identity, root=root); guard()
    preflight = _preflight_controls(identity, fixture, root=root); guard()
    folders, lock_fd, locked, fresh = [], None, False, None
    phase = "namespace"
    try:
        try: fresh = custody._Chain(root, ARTIFACT_PARTS, create=True, exclusive_last=True)
        except custody.ArchiveAssessmentRunnerError as exc:
            if exc.args == ("output_cannot_resume_or_overwrite",):
                raise FeedDirectoryError("fresh_namespace_already_exists") from None
            raise
        fresh.recheck()
        base = publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS)); folders.append(base)
        claims = publication._NewDirectory(base.path/"claims", create=True); folders.append(claims)
        runs = publication._NewDirectory(base.path/"runs", create=True); folders.append(runs)
        phase = "scope_lock"
        if not base.tree.exists("scope.lock"): base.publish("scope.lock", LOCK_BYTES)
        lock_fd = os.open("scope.lock", os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=base.fd)
        lock_version = publication._version(os.fstat(lock_fd)); fcntl.flock(lock_fd, fcntl.LOCK_EX|fcntl.LOCK_NB); locked = True
        _need(base.read("scope.lock") == LOCK_BYTES and set(os.listdir(base.fd)) == {"scope.lock", "claims", "runs"}
            and not os.listdir(claims.fd) and not os.listdir(runs.fd), "one_shot_scope_cannot_resume")
        phase = "capacity"
        capacity = os.fstatvfs(base.fd)
        _need(capacity.f_bavail*capacity.f_frsize >= MIN_FREE_BYTES+MAX_RESPONSE_BYTES, "publication_disk_reserve_refused")
        os.mkdir(AUDIT_ID, 0o700, dir_fd=runs.fd); os.fsync(runs.fd)
        run = publication._NewDirectory(runs.path/AUDIT_ID); folders.append(run)
        expected_run, expected_claims = set(), set()
        def check():
            guard(); fresh.recheck()
            _need(publication._version(os.fstat(lock_fd)) == lock_version ==
                publication._version(os.stat("scope.lock", dir_fd=base.fd, follow_symlinks=False)), "scope_lock_changed")
            for folder in folders: folder.check()
            _need(set(os.listdir(base.fd)) == {"scope.lock", "claims", "runs"}
                and set(os.listdir(runs.fd)) == {AUDIT_ID} and set(os.listdir(run.fd)) == expected_run
                and set(os.listdir(claims.fd)) == expected_claims, "scope_inventory_changed")
        def publish(name, value):
            digest = run.publish(name, _raw(value), cap=MAX_CONTROL_BYTES); expected_run.add(name); check(); return digest
        phase = "reservation"
        reservation_sha = publish("reservation.json", _decode(preflight["reservation"], canonical=True))
        phase = "contact_validation"
        contact_value = privacy._contact(contact(), observed=not fixture)
        publish("contact-validated.json", {"schema": SCHEMA+"/contact", "reservation_sha256": reservation_sha,
            "contact_present": True, "contact_value_stored_or_hashed": False})
        phase = "url_claim"
        claim_sha = claims.publish(_claim_name(), _raw({"schema": SCHEMA+"/url-claim", "method": "GET", "url": URL,
            "scope_sha256": _sha(_raw(_scope())), "reservation_sha256": reservation_sha}))
        expected_claims.add(_claim_name()); check()
        phase = "durable_start"
        start_sha = publish("request-start.json", {"schema": SCHEMA+"/start", "scope_sha256": _sha(_raw(_scope())),
            "reservation_sha256": reservation_sha, "claim_sha256": claim_sha, "attempt": 1})
        headers = {"User-Agent": "InsiderBuyingResearch-FeedDirectoryQ4/2.0 ("+contact_value+")",
            "Accept": "application/json", "Accept-Encoding": "identity", "Connection": "close"}
        response = None; context = None; phase = "transport"
        try:
            if fixture: response = transport(URL, headers, MAX_RESPONSE_BYTES)
            else:
                _activated(activation, identity)
                context = _Context(_TOKEN, root, identity, check, run, claims, start_sha, claim_sha, headers, activation)
                _CONTEXTS[context] = (id(activation), id(check), id(run), id(claims), start_sha, claim_sha, _raw(headers))
                response = _production_transport(context)
        except Exception:
            if not fixture and (context is None or not context.raw_transport_invoked):
                raise FeedDirectoryError("transport_front_refused_before_raw_invocation") from None
        phase = "post_transport_custody"; check()
        status = response_sha = response_bytes = header_sha = inventory_sha = None
        inventory = None; disposition = "ambiguous_transport_failure_no_retry"; retained = False
        if response is not None:
            phase = "response_validation"
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
                    phase = "response_publication"
                    response_sha = run.publish("response.bin", body, cap=MAX_RESPONSE_BYTES)
                    expected_run.add("response.bin"); check(); response_bytes = len(body); retained = True
                    publish("response-headers.json", {"headers": response.headers})
                    phase = "profile_parse"
                    try: inventory = parse_directory_inventory(body)
                    except FeedDirectoryError:
                        disposition = "opaque_response_retained_inventory_unqualified"
                    else:
                        phase = "inventory_publication"
                        inventory_sha = publish("inventory.json", inventory)
                        disposition = "directory_inventory_candidate_profile_accepted"
        result = {"schema": SCHEMA+"/result", "reservation_sha256": reservation_sha, "claim_sha256": claim_sha,
            "start_sha256": start_sha, "http_status": status, "transport_invocations": 1,
            "disposition": disposition, "response_retained": retained, "response_sha256": response_sha,
            "response_bytes": response_bytes, "response_headers_sha256": header_sha,
            "inventory_sha256": inventory_sha, "inventory_qualified": inventory is not None,
            "archive_requests": 0, "accession_requests": 0, "contact_value_stored_or_hashed": False}
        phase = "result_publication"
        result_sha = publish("request-result.json", result)
        complete = _complete_control(identity, fixture, reservation_sha, result, result_sha, inventory is not None)
        phase = "complete_publication"
        complete_sha = publish("complete.json", complete)
        phase = "final_custody"; check()
        return {"audit_id": AUDIT_ID, "report_sha256": complete_sha, "disposition": disposition,
            "directory_inventory_completed": inventory is not None, "transport_invocations": 1,
            "http_status": status, "response_retained": retained, "response_sha256": response_sha,
            "response_bytes": response_bytes, "inventory_sha256": inventory_sha,
            "candidate_inventory": inventory,
            "archive_requests": 0, "accession_requests": 0, "authority": _authority()}
    except Exception as exc:
        raise _classified(phase, exc) from None
    finally:
        try: publication._close_all(folders, fresh, lock_fd, locked)
        except Exception as exc: raise _classified("cleanup", exc) from None


def run_actual_probe(expected_head, *, contact_mode="stdin"):
    phase, activation = "arguments", None
    try:
        _need(contact_mode == "stdin", "private_contact_mode_refused")
        phase = "source_identity"; before = _identity(expected_head)
        def guard(): _need(_identity(expected_head) == before, "committed_source_changed")
        phase = "native_source_preflight"; _native_preflight(before); guard()
        phase = "activation"; activation = _Activation(before, guard)
        _ACTIVATIONS[activation] = (_raw(before), id(guard))
        phase = "capture"
        return _run(root=LANE_ROOT, identity=before, guard=guard, contact=contact_io._stdin_contact,
            transport=_production_transport, fixture=False, activation=activation)
    except Exception as exc: raise _classified(phase, exc) from None
    finally:
        if activation is not None: _ACTIVATIONS.pop(activation, None)


def _run_invented_probe(*, root, transport, contact=lambda: "invented@unit.test", guard=lambda: None):
    publication._fixture_root(root)
    _need(callable(transport) and transport is not _RAW_TRANSPORT and transport is not _production_transport
        and contact not in {contact_io._stdin_contact, contact_io._getpass_contact}, "invented_callbacks_required")
    publication._native_fixture_denial()
    sources = {SELF_PATH: "a"*64, TEST_PATH: "b"*64,
        **{f"research/invented_source_{index:03}.py": "c"*64 for index in range(102)}}
    identity = {"root": str(root), "branch": LANE_BRANCH, "head": "a"*40, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    return _run(root=root, identity=identity, guard=guard, contact=contact, transport=transport, fixture=True)


class _ReadbackDirectory:
    """Strict old-input versions (including ctime) and full hashes on every check."""
    def __init__(self, path):
        self.path = Path(path); self.tree = privacy._Directory(path)
        self.fd = self.tree.fd; self.pins = {}
        try:
            self.inventory = set(os.listdir(self.fd))
            self.versions = {name: privacy._file_version(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                for name in self.inventory}
        except BaseException:
            try: self.tree.close()
            except BaseException: pass
            raise

    def _versions(self):
        self.tree.check()
        _need(set(os.listdir(self.fd)) == self.inventory and all(privacy._file_version(
            os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == version for name, version in self.versions.items()),
            "old_readback_inventory_or_version_changed")

    def read(self, name, *, cap=MAX_CONTROL_BYTES):
        self._versions()
        _need(name in self.versions, "old_readback_name_refused")
        raw = self.tree.read(name, cap=cap)
        self._versions()
        pin = (_sha(raw), len(raw))
        _need(name not in self.pins or self.pins[name] == pin, "old_readback_content_changed")
        self.pins[name] = pin
        return raw

    def check(self):
        self._versions()
        for name, (digest, size) in tuple(self.pins.items()):
            raw = self.tree.read(name, cap=size)
            _need(len(raw) == size and _sha(raw) == digest, "old_readback_content_changed")
        self._versions()

    def close(self): self.tree.close()


def _verify(root, expected_report_sha256, fixture, identity=None):
    _need(type(expected_report_sha256) is str and _SHA.fullmatch(expected_report_sha256), "report_digest_required")
    if fixture:
        publication._fixture_root(root); publication._native_fixture_denial()
    else:
        _isolated(); source_runner._prove_isolation(); _current(identity)
        _need(root == LANE_ROOT, "readback_fixed_root_required")
    folders, lock_fd, locked = [], None, False
    try:
        base = _ReadbackDirectory(root.joinpath(*ARTIFACT_PARTS)); folders.append(base)
        lock_fd = os.open("scope.lock", os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=base.fd)
        lock_version = privacy._file_version(os.fstat(lock_fd))
        _need(lock_version == base.versions.get("scope.lock"), "readback_lock_substitution")
        fcntl.flock(lock_fd, fcntl.LOCK_SH|fcntl.LOCK_NB); locked = True
        claims = _ReadbackDirectory(base.path/"claims"); folders.append(claims)
        runs = _ReadbackDirectory(base.path/"runs"); folders.append(runs)
        run = _ReadbackDirectory(runs.path/AUDIT_ID); folders.append(run)
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
        expected_complete = _complete_control(actual_identity, fixture, _sha(reservation_raw), result,
            _sha(result_raw), inventory is not None)
        _need(complete_raw == _raw(expected_complete) and set(os.listdir(run.fd)) == expected, "readback_complete_refused")
        for folder in folders: folder.check()
        _need(lock_version == privacy._file_version(os.fstat(lock_fd)) == privacy._file_version(
            os.stat("scope.lock", dir_fd=base.fd, follow_symlinks=False)), "readback_lock_changed")
        if not fixture: _current(identity)
        return {"audit_id": AUDIT_ID, "report_sha256": expected_report_sha256,
            "directory_inventory_completed": inventory is not None, "disposition": result["disposition"],
            "response_sha256": result["response_sha256"], "response_bytes": result["response_bytes"],
            "candidate_inventory": inventory,
            "transport_invocations": 1, "archive_requests": 0, "accession_requests": 0, "authority": _authority()}
    finally: publication._close_all(folders, None, lock_fd, locked)


def verify_invented_probe(root, expected_report_sha256):
    publication._fixture_root(root); publication._native_fixture_denial()
    return _verify(root, expected_report_sha256, True)


def verify_actual_probe(*, expected_report_sha256, execution_identity):
    _isolated(); source_runner._prove_isolation()
    identity = _source_identity(execution_identity, root=LANE_ROOT)
    _current(identity); result = _verify(LANE_ROOT, expected_report_sha256, False, identity); _current(identity)
    return {**result, "native_network_fork_allwrite_securityexec_denial": True,
        "source_identity_semantics": "trusted_launcher_git_identity_independent_child_current_and_frozen_bytes",
        "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0}


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message): raise FeedDirectoryError("private_arguments_refused")


def main(argv=None):
    saved = contact_io._protect_stdin_echo()
    try:
        parser = _PrivateParser(); parser.add_argument("--expected-head", required=True)
        parser.add_argument("--contact-mode", choices=("stdin",), default="stdin")
        args = parser.parse_args(argv)
        result = run_actual_probe(args.expected_head, contact_mode=args.contact_mode)
        print(_raw(result).decode()); return 0 if result["directory_inventory_completed"] else 2
    except Exception as exc:
        refusal = _classified("arguments", exc)
        sys.stderr.write("REFUSED: q4_directory stage="+refusal.stage+" code="+refusal.args[0]
            +"; preserve any URL claim and original response\n"); return 2
    finally: contact_io._restore_stdin_echo(saved)


if __name__ == "__main__":
    raise SystemExit(main())

