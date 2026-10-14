"""Exact original-parent prefix custody, not XML/identity/PIT admission.

Production requires SELF_PATH and a clean committed designated lane image.
The collector never finds a contact or credential.
Private fixture entry points cannot invoke the real transport or lane root.
Starts and JIT global accession claims are irreversible; plans are not claims.
Complete HTTP response custody, header qualification and full XML/IB1C
admission are separate facts. Context forms stay accounted, not requested.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import argparse
import errno
import fcntl
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import termios
import time

from research import insider_buying_sec_2006q1_parent_bootstrap as bootstrap
from research import insider_buying_sec_recovery_v4_capture as custody
from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport, _strict_selected_response
from research.insider_buying_sec_complete_acquisition import SecHttpResult
from research.insider_buying_sec_all_form4_parent_campaign import _validate_parent_header


SCHEMA = "insider-2006q1-original-parent-initial64-capture-v1"
SELF_PATH = "research/insider_buying_sec_2006q1_parent_capture_v1.py"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "sec_2006q1_parent_capture_v1")
MAX_REQUESTS = 64
MAX_PARENT_BYTES = 8 * 1024 * 1024
MAX_CONTROL_BYTES = 1024 * 1024
MIN_FREE_BYTES = 8 * 1024 * 1024 * 1024
MIN_COMPLETION_INTERVAL_NS = 500_000_000
LOCK_BYTES = b"INSETF-2006Q1-v1-global-accession-claim-lock\n"
_ID = re.compile(r"ib-sec-2006q1-initial64-[a-z0-9-]{1,60}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_PATH = re.compile(r"edgar/data/([0-9]{1,10})/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt\Z")
_CLAIM = re.compile(r"[0-9a-f]{64}\.json\Z")
_REQUEST_KEYS = frozenset({"period", "accession_number", "form_type", "filing_date", "issuer_cik", "archive_path", "url",
    "source_record_ordinal", "accession_key_sha256", "filing_metadata_sha256", "submission_inventory_sha256",
    "quarterly_zip_sha256", "submission_member_sha256", "master_decoded_sha256", "master_receipt_sha256"})
_TOKEN = object()


class EarlyParentCaptureError(ValueError):
    """Fixed refusals only; no contact, body, URL, exception text or headers."""


_FAILURE_PHASES = frozenset({"preflight", "verifier", "verifier_worker", "capture",
    "prior_snapshot_validation", "namespace_reservation_validation", "reservation_publication",
    "post_reservation_check", "private_contact_validation", "contact_validation_publication",
    "pre_request_check", "claim_publication", "attempt_start_publication", "pre_dispatch_check",
    "transport_dispatch", "post_dispatch_check", "response_custody", "attempt_result_publication",
    "post_result_check", "terminal_publication", "final_journal_check"})


def _failure_diagnostic(exc, fallback):
    """Only fixed categories: never exception text, arbitrary args or paths."""
    phase = getattr(exc, "_early_capture_failure_phase", None)
    if type(phase) is not str or phase not in _FAILURE_PHASES:
        phase = fallback if fallback in _FAILURE_PHASES else "preflight"
    classes = ((EarlyParentCaptureError, "EarlyParentCaptureError"),
        (bootstrap.ParentBootstrapError, "ParentBootstrapError"),
        (bootstrap.custody.ArchiveAssessmentRunnerError, "ArchiveAssessmentRunnerError"),
        (bootstrap.custody.EodhdDemoError, "EodhdDemoError"),
        (custody.FreshV4CaptureError, "FreshV4CaptureError"), (OSError, "OSError"),
        (ValueError, "ValueError"), (TypeError, "TypeError"), (KeyError, "KeyError"),
        (subprocess.SubprocessError, "SubprocessError"))
    category = next((name for kind, name in classes if isinstance(exc, kind)), "other_refusal")
    number = exc.errno if isinstance(exc, OSError) else None
    if type(number) is not int or number not in errno.errorcode:
        number = None
    return {"disposition": "early_parent_capture_or_verifier_refused_existing_claims_preserved",
            "failure_phase": phase, "failure_class": category, "os_errno": number}


def _need(value, code):
    if not value:
        raise EarlyParentCaptureError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    return bootstrap._json(raw, newline=False)


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value), "external_digest_required")
    return value


def _authority():
    return {name: False for name in ("source_authenticated", "official_acceptance_verified", "publication_time_verified",
        "historical_identity_verified", "point_in_time_verified", "rights_verified", "complete_corpus", "canonical_ready",
        "qc_entitlement_verified", "outcome_access_authorized", "backtesting_ready", "execution_authorized",
        "context_forms_admitted", "full_xml_projection_complete")}


def _request(row):
    _need(type(row) is dict and set(row) == _REQUEST_KEYS, "prefix_request_shape_refused")
    _need(row.get("period") == "2006Q1" and row.get("form_type") in {"4", "4/A"}
          and type(row.get("accession_number")) is str and _ACCESSION.fullmatch(row["accession_number"])
          and type(row.get("source_record_ordinal")) is int and 1 <= row["source_record_ordinal"] <= bootstrap.locators.MAX_FILINGS
          and type(row.get("issuer_cik")) is str and re.fullmatch(r"[0-9]{10}", row["issuer_cik"])
          and int(row["issuer_cik"]) > 0, "prefix_identity_or_context_refused")
    try:
        filed = date.fromisoformat(row["filing_date"])
    except (TypeError, ValueError):
        raise EarlyParentCaptureError("prefix_filing_date_refused") from None
    _need(filed.isoformat() == row["filing_date"] and date(2006, 1, 1) <= filed <= date(2006, 3, 31), "prefix_window_refused")
    _need(type(row.get("archive_path")) is str, "prefix_locator_refused")
    match = _PATH.fullmatch(row["archive_path"])
    _need(match and int(match.group(1)) > 0 and match.group(2) == row["accession_number"]
          and row.get("url") == "https://www.sec.gov/Archives/" + row["archive_path"], "prefix_locator_refused")
    for key in _REQUEST_KEYS:
        if key.endswith("sha256"):
            _digest(row[key])
    _need(row["accession_key_sha256"] == bootstrap.locators.accession_key(row["accession_number"]), "prefix_accession_key_refused")
    return row


@dataclass(frozen=True, slots=True)
class ObservedEarlySelection:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def canonical_bytes(self):
        _need(type(self) in {ObservedEarlySelection, InventedEarlySelection} and self._token is _TOKEN
              and self._bytes == self._factory_bytes, "genuine_unchanged_selection_required")
        return self._bytes

    def to_payload(self):
        return _json(self.canonical_bytes())

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


@dataclass(frozen=True, slots=True)
class InventedEarlySelection(ObservedEarlySelection):
    """Cannot use real lane, prior roots or transport."""


def _seal(value, observed):
    result = (ObservedEarlySelection if observed else InventedEarlySelection)(_raw(value), _TOKEN)
    object.__setattr__(result, "_factory_bytes", result._bytes)
    return result


def _selection(accounting, *, head, bootstrap_id, bootstrap_complete_sha256, accounting_sha256,
               snapshot_sha256, bootstrap_execution_head, observed, execution_identity=None):
    _need(type(accounting) is dict and accounting.get("schema") == bootstrap.locators.SCHEMA
          and accounting.get("authority") == bootstrap.locators._authority()
          and type(accounting.get("prefix")) is list and len(accounting["prefix"]) == MAX_REQUESTS
          and accounting.get("maximum_prefix") == MAX_REQUESTS
          and accounting.get("prefix_sha256") == _sha(_raw(accounting["prefix"]))
          and type(head) is str and _HEAD.fullmatch(head)
          and type(bootstrap_execution_head) is str and _HEAD.fullmatch(bootstrap_execution_head), "fixed_prefix_selection_refused")
    for digest in (bootstrap_complete_sha256, accounting_sha256, snapshot_sha256):
        _digest(digest)
    rows, previous, seen = [], None, set()
    for ordinal, row in enumerate(accounting["prefix"]):
        _request(row)
        ordering = (row["filing_date"], row["accession_number"], row["source_record_ordinal"])
        _need(previous is None or previous < ordering, "prefix_order_refused")
        _need(row["accession_number"] not in seen, "prefix_duplicate_accession_refused")
        seen.add(row["accession_number"]);previous = ordering
        rows.append({"prefix_ordinal": ordinal, "request_sha256": _sha(_raw(row)), "request": row})
    if observed:
        _need(type(execution_identity) is dict and execution_identity.get("head") == head
              and execution_identity.get("root") == str(bootstrap.custody.LANE_ROOT)
              and execution_identity.get("branch") == bootstrap.custody.LANE_BRANCH
              and execution_identity.get("clean") is True
              and SELF_PATH in execution_identity.get("source_sha256", {}), "observed_execution_identity_required")
        _need(accounting.get("retained_source_hashes_match") is True and accounting.get("source_filings") == 83_657
              and accounting.get("counts", {}).get("target_filings") == 71_679
              and accounting.get("counts", {}).get("context_filings") == 11_978
              and accounting.get("submission_inventory_sha256") == bootstrap.custody.INVENTORY_SHA256
              and accounting.get("master_decoded_sha256") == bootstrap.locators.RETAINED_MASTER_SHA256,
              "actual_source_population_binding_refused")
    return _seal({"schema": SCHEMA + "/selection", "fixture_only": not observed, "repository_head": head,
        "execution_identity": execution_identity if observed else {"fixture_only": True, "head": head,
            "source_sha256": {}, "source_inventory_sha256": _sha(_raw({}))},
        "bootstrap_id": bootstrap_id, "bootstrap_execution_head": bootstrap_execution_head,
        "bootstrap_complete_sha256": bootstrap_complete_sha256, "accounting_sha256": accounting_sha256,
        "prior_exposure_snapshot_sha256": snapshot_sha256,
        "prior_exposure_inventory_sha256": accounting["prior_exposure_inventory_sha256"],
        "source_filings": accounting["source_filings"], "target_filings": accounting["counts"]["target_filings"],
        "context_filings": accounting["counts"]["context_filings"], "form_counts": accounting["form_counts"],
        "selected_prefix_sha256": accounting["prefix_sha256"], "requests": rows,
        "authority": _authority(), "request_form_scope": ["4", "4/A"], "context_forms_stay_accounted": True}, observed)


def build_invented_selection(accounting_raw, *, expected_accounting_sha256, head="a" * 40):
    _need(type(accounting_raw) is bytes and _sha(accounting_raw) == _digest(expected_accounting_sha256), "fixture_accounting_hash_refused")
    return _selection(_json(accounting_raw), head=head, bootstrap_id="invented-fixture", bootstrap_complete_sha256="b" * 64,
        accounting_sha256=expected_accounting_sha256, snapshot_sha256="c" * 64, bootstrap_execution_head="d" * 40, observed=False)


def _committed_identity(head):
    _need(Path(__file__).resolve() == bootstrap.custody.LANE_ROOT / SELF_PATH, "inactive_draft_not_production_source")
    identity = bootstrap.custody._identity(head)
    _need(SELF_PATH in identity["source_sha256"], "committed_capture_source_required")
    return identity


def _load_bootstrap(bootstrap_id, complete_sha, accounting_sha, snapshot_sha):
    bootstrap._id(bootstrap_id)
    for digest in (complete_sha, accounting_sha, snapshot_sha):
        _digest(digest)
    root = bootstrap.custody.LANE_ROOT.joinpath(*bootstrap.OUTPUT_PARTS, bootstrap_id)
    tree = bootstrap._Tree(bootstrap.RootSpec("retained-early-bootstrap", root, "bootstrap-publication"))
    try:
        receipt_raw = tree.read((), "complete.json", expected=complete_sha)
        receipt = _json(receipt_raw)
        accounting_raw = tree.read((), "locator-accounting.json", cap=bootstrap.locators.MAX_OUTPUT_BYTES, expected=accounting_sha)
        tree.read((), "exposure-snapshot.json", cap=bootstrap.MAX_SNAPSHOT_BYTES, expected=snapshot_sha)
        observed = {"audit_id": bootstrap_id, "fixture_only": False, "complete_sha256": complete_sha,
            "locator_accounting_sha256": accounting_sha, "exposure_snapshot_sha256": snapshot_sha,
            "counts": receipt.get("counts"), "source_authenticated": False, "backtest_ready": False, "dispatch_enabled": False}
        identity = receipt.get("execution_identity")
        _need(type(identity) is dict and type(identity.get("head")) is str and _HEAD.fullmatch(identity["head"]), "bootstrap_execution_lineage_refused")
        bootstrap._required_identity(identity, identity["head"])
        bootstrap._verify_publication(root=bootstrap.custody.LANE_ROOT, audit_id=bootstrap_id, identity=identity,
            expected_snapshot_sha256=snapshot_sha, observed=observed, fixture_only=False)
        for name, digest in identity["source_sha256"].items():
            _need(_sha(bootstrap.custody._git(bootstrap.custody.LANE_ROOT, "show", identity["head"] + ":" + name)) == digest,
                  "bootstrap_historical_committed_source_differs")
        tree.recheck()
        return tree, _json(accounting_raw), identity["head"]
    except BaseException:
        tree.close();raise


def build_observed_selection(bootstrap_id, *, expected_bootstrap_complete_sha256, expected_accounting_sha256,
                             expected_snapshot_sha256, expected_head):
    before = _committed_identity(expected_head)
    tree, accounting, execution_head = _load_bootstrap(bootstrap_id, expected_bootstrap_complete_sha256,
                                                       expected_accounting_sha256, expected_snapshot_sha256)
    try:
        result = _selection(accounting, head=expected_head, bootstrap_id=bootstrap_id,
            bootstrap_complete_sha256=expected_bootstrap_complete_sha256, accounting_sha256=expected_accounting_sha256,
            snapshot_sha256=expected_snapshot_sha256, bootstrap_execution_head=execution_head, observed=True, execution_identity=before)
        tree.recheck()
        _need(_committed_identity(expected_head) == before, "capture_source_changed")
        return result
    finally:
        tree.close()


def _claim_inventory(claims):
    names = sorted(os.listdir(claims.fd))
    _need(len(names) <= bootstrap.locators.MAX_PRIOR_ACCESSIONS and all(_CLAIM.fullmatch(n) for n in names), "new_claim_inventory_refused")
    result = {}
    for name in names:
        raw = claims.read(name, cap=MAX_CONTROL_BYTES);body = _json(raw)
        request = body.get("request", {}).get("request")
        _request(request)
        _need(name == request["accession_key_sha256"] + ".json"
              and body.get("request", {}).get("request_sha256") == _sha(_raw(request)), "new_claim_request_binding_refused")
        result[name] = _sha(raw)
    return result


def _envelope_and_header(raw, row):
    """Use frozen metadata helpers without interpreting XML/financial bodies."""
    from research.insider_buying.sec_complete_submission import _split_lines
    _, lines = _split_lines(raw)
    _need(lines[-1] == b"</SEC-DOCUMENT>" and raw.count(b"<SEC-DOCUMENT>") == 1
          and raw.count(b"</SEC-DOCUMENT>") == 1, "source_sec_document_envelope_refused")
    adapted = {**row, "master_source_sha256": row["master_decoded_sha256"]}
    _validate_parent_header(raw, adapted)


def _fixture_root(root):
    # Textual containment alone is insufficient on case-insensitive volumes.
    try:
        _need(isinstance(root, Path) and root.is_absolute() and root.resolve() == root
              and not bootstrap.custody._fixture_root_is_lane(root), "fixture_root_transport_required")
        known = [bootstrap.custody.LANE_ROOT, *(spec.path for spec in bootstrap.actual_roots())]
        for real in known:
            resolved = real.resolve()
            _need(not root.is_relative_to(resolved) and not resolved.is_relative_to(root),
                  "fixture_root_transport_required")
            if real.exists():
                _need(all(not parent.samefile(real) for parent in (root, *root.parents))
                      and all(not root.samefile(parent) for parent in real.parents),
                      "fixture_root_transport_required")
    except (OSError, RuntimeError, bootstrap.custody.ArchiveAssessmentRunnerError):
        raise EarlyParentCaptureError("fixture_root_transport_required") from None


def _capture(selection, capture_id, contact, *, root, observed, transport, guard, prior_open,
             clock=custody._utc, monotonic_ns=time.monotonic_ns, sleep=time.sleep, free_bytes=None):
    _need(type(selection) is (ObservedEarlySelection if observed else InventedEarlySelection), "actual_fixture_selection_boundary_refused")
    _need(type(capture_id) is str and _ID.fullmatch(capture_id), "capture_id_refused")
    if observed:
        _need(root == bootstrap.custody.LANE_ROOT and transport is _selected_sec_transport,
              "actual_fixed_root_transport_required")
        _committed_identity(selection.to_payload()["repository_head"])
        _need(selection.to_payload().get("execution_identity") == _committed_identity(selection.to_payload()["repository_head"]),
              "observed_execution_source_identity_changed")
    else:
        _fixture_root(root)
        _need(transport is not _selected_sec_transport, "fixture_root_transport_required")
        bootstrap.custody._effective_denial(require_fork=False)
    body = selection.to_payload()
    _need(body.get("fixture_only") is (not observed) and body.get("authority") == _authority()
          and len(body.get("requests", [])) == MAX_REQUESTS, "selection_mode_or_scope_refused")
    _need(not observed or contact in {_stdin_contact, _getpass_contact}, "fixed_private_contact_reader_required")
    for item in body["requests"]:
        _request(item["request"])
        _need(item["request_sha256"] == _sha(_raw(item["request"])), "selection_request_hash_refused")
    guard()
    prior_context = prior_open()
    folders, lock_fd, locked = [], None, False
    failure_phase = "prior_snapshot_validation"
    try:
        prior_check = prior_context["recheck"]
        _need(callable(prior_check) and prior_context["snapshot_sha256"] == body["prior_exposure_snapshot_sha256"]
              and prior_context["exposure_sha256"] == body["prior_exposure_inventory_sha256"], "actual_prior_snapshot_changed")
        exposures = set(prior_context["exposed_accessions"])
        _need(not any(row["request"]["accession_number"] in exposures for row in body["requests"]), "prefix_already_prior_exposed")
        failure_phase = "namespace_reservation_validation"
        path = root.joinpath(*ARTIFACT_PARTS)
        namespace = custody._Directory(path, create=True);folders.append(namespace)
        claims = custody._Directory(path / "claims", create=True);folders.append(claims)
        runs = custody._Directory(path / "runs", create=True);folders.append(runs)
        if not namespace.exists("capture.lock"):
            namespace.publish("capture.lock", LOCK_BYTES)
        lock_fd = os.open("capture.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=namespace.fd)
        lock_before = os.fstat(lock_fd)
        _need(stat.S_ISREG(lock_before.st_mode) and lock_before.st_nlink == 1 and lock_before.st_uid == os.geteuid()
              and stat.S_IMODE(lock_before.st_mode) == 0o600, "global_claim_lock_refused")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB);locked = True
        _need(namespace.read("capture.lock", cap=1024) == LOCK_BYTES
              and set(os.listdir(namespace.fd)) == {"claims", "runs", "capture.lock"}, "global_namespace_refused")
        known_claims, known_runs = _claim_inventory(claims), set(os.listdir(runs.fd))
        _need(all(_ID.fullmatch(name) for name in known_runs), "known_run_inventory_refused")
        _need(capture_id not in known_runs and not any(item["request"]["accession_key_sha256"] + ".json" in known_claims
              for item in body["requests"]), "permanent_claim_or_capture_already_exists")
        info = os.fstatvfs(namespace.fd)
        capacity = free_bytes() if free_bytes is not None else info.f_bavail * info.f_frsize
        _need(type(capacity) is int and capacity >= MIN_FREE_BYTES + MAX_REQUESTS * MAX_PARENT_BYTES, "capture_disk_reserve_refused")
        failure_phase = "reservation_publication"
        os.mkdir(capture_id, 0o700, dir_fd=runs.fd);os.fsync(runs.fd)
        run = custody._Directory(path / "runs" / capture_id);folders.append(run)
        objects = custody._Directory(run.path / "objects", create=True);folders.append(objects)
        reservation = {"schema": SCHEMA + "/reservation", "capture_id": capture_id, "fixture_only": not observed,
            "capture_execution_head": body["repository_head"], "selection_sha256": selection.sha256, "selection": body,
            "execution_identity": body["execution_identity"],
            "reserved_at_utc": custody._stamp(clock), "contact_present": False, "planned_prefix": MAX_REQUESTS,
            "contact_input_mode": "deferred_private_reader" if observed else "invented_fixture_only",
            "maximum_attempts_per_request": 1, "maximum_body_bytes": MAX_PARENT_BYTES,
            "minimum_completion_spacing_ns": MIN_COMPLETION_INTERVAL_NS, "claim_policy": "just_in_time_permanent_accession",
            "prior_claim_inventory": known_claims, "prior_run_inventory": sorted(known_runs),
            "old_roots_written": False, "authority": _authority()}
        reservation_sha = run.publish("reservation.json", _raw(reservation), cap=MAX_CONTROL_BYTES)
        retained = [(run, "reservation.json", reservation_sha, MAX_CONTROL_BYTES)]
        allowed_run, allowed_objects = {"reservation.json", "objects"}, set()
        expected_claims, expected_runs = dict(known_claims), known_runs | {capture_id}
        def check():
            prior_check();guard()
            for folder in folders:
                folder.check()
            named = os.stat("capture.lock", dir_fd=namespace.fd, follow_symlinks=False)
            _need(custody._file_version(named) == custody._file_version(os.fstat(lock_fd)) == custody._file_version(lock_before), "global_claim_lock_changed")
            _need(_claim_inventory(claims) == expected_claims and set(os.listdir(runs.fd)) == expected_runs
                  and set(os.listdir(run.fd)) == allowed_run and set(os.listdir(objects.fd)) == allowed_objects
                  and set(os.listdir(namespace.fd)) == {"claims", "runs", "capture.lock"}, "current_journal_inventory_changed")
            for directory, name, digest, cap in retained:
                _need(_sha(directory.read(name, cap=cap)) == digest, "current_journal_leaf_changed")
        failure_phase = "post_reservation_check"
        check()
        failure_phase = "private_contact_validation"
        contact = custody._contact(contact() if callable(contact) else contact, observed=observed)
        contact_control = {"schema": SCHEMA + "/contact-validation", "reservation_sha256": reservation_sha,
            "contact_present": True, "validated_at_utc": custody._stamp(clock), "contact_value_stored_or_hashed": False}
        failure_phase = "contact_validation_publication"
        contact_sha = run.publish("contact-validated.json", _raw(contact_control), cap=MAX_CONTROL_BYTES)
        retained.append((run, "contact-validated.json", contact_sha, MAX_CONTROL_BYTES));allowed_run.add("contact-validated.json")
        headers = {"User-Agent": f"InsiderBuyingResearch-2006Q1-initial64/1.0 ({contact})",
                   "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close"}
        results, completed, qualified, total_bytes, previous_finish = [], 0, 0, 0, None
        for ordinal, item in enumerate(body["requests"]):
            failure_phase = "pre_request_check"
            check()
            info = os.fstatvfs(namespace.fd)
            capacity = free_bytes() if free_bytes is not None else info.f_bavail * info.f_frsize
            _need(type(capacity) is int and capacity >= MIN_FREE_BYTES + (MAX_REQUESTS - ordinal) * MAX_PARENT_BYTES,
                  "remaining_capture_disk_reserve_refused")
            name = item["request"]["accession_key_sha256"] + ".json"
            _need(name not in expected_claims and item["request"]["accession_number"] not in exposures, "request_already_consumed")
            failure_phase = "claim_publication"
            claim = {"schema": SCHEMA + "/request-claim", "capture_id": capture_id, "reservation_sha256": reservation_sha,
                     "selection_sha256": selection.sha256, "request": item, "claimed_at_utc": custody._stamp(clock)}
            claim_sha = claims.publish(name, _raw(claim), cap=MAX_CONTROL_BYTES)
            expected_claims[name] = claim_sha;retained.append((claims, name, claim_sha, MAX_CONTROL_BYTES))
            failure_phase = "attempt_start_publication"
            if previous_finish is not None:
                now = monotonic_ns()
                _need(type(now) is int and now >= previous_finish, "monotonic_clock_refused")
                if now - previous_finish < MIN_COMPLETION_INTERVAL_NS:
                    sleep((MIN_COMPLETION_INTERVAL_NS - now + previous_finish) / 1_000_000_000)
            started = monotonic_ns()
            _need(type(started) is int and started >= 0 and (previous_finish is None or
                  started - previous_finish >= MIN_COMPLETION_INTERVAL_NS), "completion_spacing_refused")
            start = {"schema": SCHEMA + "/attempt-start", "ordinal": ordinal, "attempt": 1,
                "request_sha256": item["request_sha256"], "claim_sha256": claim_sha, "reservation_sha256": reservation_sha,
                "started_utc": custody._stamp(clock), "started_monotonic_ns": started}
            start_name = f"request-{ordinal:03d}-start.json"
            start_sha = run.publish(start_name, _raw(start), cap=MAX_CONTROL_BYTES)
            retained.append((run, start_name, start_sha, MAX_CONTROL_BYTES));allowed_run.add(start_name)
            failure_phase = "pre_dispatch_check"
            check()
            response = None
            failure_phase = "transport_dispatch"
            try:
                response = transport(item["request"]["url"], headers, MAX_PARENT_BYTES)
            except Exception:
                pass  # Ambiguous fsynced start is permanently consumed, never retried.
            failure_phase = "post_dispatch_check"
            check()  # No response/body/result publication under a changed source/custody image.
            status, raw_sha, raw_size, header_sha, framing = None, None, None, None, None
            retained_body, header_bound = False, False
            disposition, stop = "ambiguous_transport_failure_no_retry", True
            failure_phase = "response_custody"
            if response is not None:
                try:
                    _need(type(response) is SecHttpResult and type(response.status) is int and 100 <= response.status <= 599
                          and type(response.headers) is tuple and len(response.headers) <= 64
                          and all(type(pair) is tuple and len(pair) == 2 and all(type(v) is str for v in pair) for pair in response.headers)
                          and len(_raw(response.headers)) <= 16 * 1024 and type(response.body) is bytes
                          and len(response.body) <= MAX_PARENT_BYTES, "response_shape_refused")
                    status = response.status
                    custody._screen_contact_echo(_raw(response.headers).decode(), contact)
                    header_sha = _sha(_raw(response.headers))
                    framing = [list(pair) for pair in response.headers if pair[0].lower() in {
                        "content-length", "content-encoding", "transfer-encoding", "content-type"}]
                    if status != 200:
                        disposition = "http_refused_no_retry"
                    else:
                        raw = _strict_selected_response(response, max_bytes=MAX_PARENT_BYTES)
                        custody._screen_contact_echo(raw.decode("utf-8", "replace"), contact)
                        raw_sha, raw_size = _sha(raw), len(raw)
                        _need(total_bytes + raw_size <= MAX_REQUESTS * MAX_PARENT_BYTES, "total_body_bound_refused")
                        object_name = raw_sha + ".bin"
                        if object_name in allowed_objects:
                            _need(objects.read(object_name, cap=MAX_PARENT_BYTES) == raw, "duplicate_body_object_changed")
                        else:
                            object_sha = objects.publish(object_name, raw, cap=MAX_PARENT_BYTES)
                            retained.append((objects, object_name, object_sha, MAX_PARENT_BYTES));allowed_objects.add(object_name)
                        retained_body = True;completed += 1;total_bytes += raw_size
                        try:
                            _envelope_and_header(raw, item["request"])
                        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                            disposition = "complete_raw_response_retained_header_quarantined"
                        else:
                            disposition = "complete_raw_response_retained_header_bound";header_bound = True;qualified += 1
                        stop = False  # Raw custody does not silently become XML/PIT/canonical admission.
                except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OSError):
                    disposition = "response_privacy_framing_or_custody_refused_no_retry";stop = True
            previous_finish = monotonic_ns()
            _need(type(previous_finish) is int and previous_finish >= started, "completion_clock_refused")
            result = {"schema": SCHEMA + "/attempt-result", "ordinal": ordinal, "attempt": 1,
                "request_sha256": item["request_sha256"], "start_sha256": start_sha, "status": status,
                "response_headers_sha256": header_sha, "body_sha256": raw_sha, "body_size_bytes": raw_size,
                "observed_framing_headers": framing,
                "body_retained": retained_body, "header_identity_bound": header_bound, "disposition": disposition,
                "finished_utc": custody._stamp(clock), "finished_monotonic_ns": previous_finish, "authority": _authority()}
            result_name = f"request-{ordinal:03d}-result.json"
            failure_phase = "attempt_result_publication"
            result_sha = run.publish(result_name, _raw(result), cap=MAX_CONTROL_BYTES)
            retained.append((run, result_name, result_sha, MAX_CONTROL_BYTES));allowed_run.add(result_name)
            results.append({"result_name": result_name, "result_sha256": result_sha})
            failure_phase = "post_result_check"
            check()
            if stop:
                break
        report = {"schema": SCHEMA + "/complete", "capture_id": capture_id, "fixture_only": not observed,
            "capture_execution_head": body["repository_head"], "bootstrap_execution_head": body["bootstrap_execution_head"],
            "reservation_sha256": reservation_sha, "selection_sha256": selection.sha256,
            "contact_validation_sha256": contact_sha,
            "selected_prefix_sha256": body["selected_prefix_sha256"], "completed_at_utc": custody._stamp(clock),
            "planned_prefix": MAX_REQUESTS, "permanent_claims_created": len(expected_claims) - len(known_claims),
            "started_requests": len(results), "terminal_result_records": len(results), "raw_bodies_retained": completed,
            "header_bound_bodies": qualified, "header_quarantined_bodies": completed - qualified,
            "retained_body_bytes": total_bytes, "planned_unclaimed_unattempted": MAX_REQUESTS - len(results),
            "scope_terminal_accounting_complete": len(results) == MAX_REQUESTS, "results": results,
            "all_six_form_census_preserved": True, "context_filings_not_requested": body["context_filings"],
            "full_xml_projection_attempts": 0, "source_authenticated": False, "old_roots_written": False, "authority": _authority()}
        failure_phase = "terminal_publication"
        report_sha = run.publish("complete.json", _raw(report), cap=MAX_CONTROL_BYTES)
        retained.append((run, "complete.json", report_sha, MAX_CONTROL_BYTES));allowed_run.add("complete.json")
        failure_phase = "final_journal_check"
        check()
        return {"capture_id": capture_id, "fixture_only": not observed, "report_sha256": report_sha,
            "planned_prefix": MAX_REQUESTS, "started_requests": len(results), "raw_bodies_retained": completed,
            "header_bound_bodies": qualified, "planned_unclaimed_unattempted": MAX_REQUESTS - len(results),
            "scope_terminal_accounting_complete": len(results) == MAX_REQUESTS, "authority": _authority()}
    except BaseException as exc:
        # Re-raise the same exception. Diagnostics cannot change claims, retry
        # semantics or cleanup, and never copy exception arguments or messages.
        try:
            exc._early_capture_failure_phase = failure_phase
        except (AttributeError, TypeError):
            pass
        raise
    finally:
        if lock_fd is not None:
            try:
                if locked:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        for folder in reversed(folders):
            folder.close()
        prior_context["close"]()


def run_invented_capture(selection, capture_id, *, root, transport, prior_open, contact="invented@unit.test",
                          guard=lambda: None, **kwargs):
    return _capture(selection, capture_id, contact, root=root, observed=False, transport=transport,
                    guard=guard, prior_open=prior_open, **kwargs)


def run_observed_capture(selection, capture_id, *, contact_mode="stdin"):
    _need(type(selection) is ObservedEarlySelection, "genuine_observed_selection_required")
    body = selection.to_payload();identity = _committed_identity(body["repository_head"])
    rebuilt = build_observed_selection(body["bootstrap_id"], expected_bootstrap_complete_sha256=body["bootstrap_complete_sha256"],
        expected_accounting_sha256=body["accounting_sha256"], expected_snapshot_sha256=body["prior_exposure_snapshot_sha256"],
        expected_head=body["repository_head"])
    _need(rebuilt.canonical_bytes() == selection.canonical_bytes(), "observed_selection_replay_differs")
    def guard():
        _need(_committed_identity(body["repository_head"]) == identity, "capture_source_changed")
    def prior_open():
        source, _, _ = _load_bootstrap(body["bootstrap_id"], body["bootstrap_complete_sha256"],
                                     body["accounting_sha256"], body["prior_exposure_snapshot_sha256"])
        trees = []
        try:
            trees, exposure, snapshot = bootstrap.bootstrap_exposures(bootstrap.actual_roots())
            return {"snapshot_sha256": _sha(snapshot), "exposure_sha256": _sha(exposure),
                "exposed_accessions": [record["accession_number"] for record in _json(exposure)["records"]],
                "recheck": lambda: (source.recheck(), *(tree.recheck() for tree in trees)),
                "close": lambda: (source.close(), *(tree.close() for tree in reversed(trees)))}
        except BaseException:
            source.close()
            for tree in reversed(trees):
                tree.close()
            raise
    _need(contact_mode in {"stdin", "getpass"}, "private_contact_mode_refused")
    reader = _stdin_contact if contact_mode == "stdin" else _getpass_contact
    return _capture(selection, capture_id, reader, root=bootstrap.custody.LANE_ROOT, observed=True,
                    transport=_selected_sec_transport, guard=guard, prior_open=prior_open)


def _protect_stdin_echo():
    """Protect queued input before preflight without consuming any contact."""
    if not sys.stdin.isatty():
        return None
    descriptor = sys.stdin.fileno()
    saved = termios.tcgetattr(descriptor)
    protected = list(saved);protected[3] &= ~termios.ECHO
    termios.tcsetattr(descriptor, termios.TCSANOW, protected)
    return descriptor, saved


def _restore_stdin_echo(saved):
    if saved is not None:
        descriptor, mode = saved
        termios.tcsetattr(descriptor, termios.TCSANOW, mode)


def _stdin_contact():
    # Also protect direct caller use; the CLI protects the entire preflight.
    saved = _protect_stdin_echo()
    try:
        raw = sys.stdin.readline(257)
        _need(type(raw) is str and raw.endswith("\n") and len(raw) <= 255, "bounded_private_contact_input_required")
        return raw[:-1]
    finally:
        _restore_stdin_echo(saved)


def _getpass_contact():
    return getpass.getpass("SEC identifying contact (not echoed): ")


def verify_invented_capture(capture_id, *, root, expected_report_sha256):
    _fixture_root(root)
    bootstrap.custody._effective_denial(require_fork=False)
    return _verify_capture(capture_id, root=root, expected_report_sha256=expected_report_sha256, fixture_only=True)


def verify_observed_capture(capture_id, *, expected_report_sha256, expected_head):
    before = _committed_identity(expected_head)
    _digest(expected_report_sha256)
    _verify_original_committed_sources(capture_id, expected_report_sha256)
    policy = "(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)"
    command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-B", "-m", "research.insider_buying_sec_2006q1_parent_capture_v1", "--verify-worker",
        "--capture-id", capture_id, "--expected-report-sha256", expected_report_sha256, "--expected-head", expected_head]
    completed = subprocess.run(command, cwd=bootstrap.custody.LANE_ROOT, input=_raw(before), capture_output=True, check=False, timeout=1800)
    _need(_committed_identity(expected_head) == before, "verifier_source_changed")
    _need(completed.returncode == 0 and not completed.stderr and len(completed.stdout) <= MAX_CONTROL_BYTES,
          "isolated_capture_verifier_refused")
    result = _json(completed.stdout.rstrip(b"\n"))
    _need(result.get("fixture_only") is False and result.get("report_sha256") == expected_report_sha256
          and result.get("authority") == _authority() and result.get("parent_xml_projection_performed") is False,
          "isolated_capture_verifier_result_binding_refused")
    return result


def _verify_original_committed_sources(capture_id, expected_report_sha256):
    path = bootstrap.custody.LANE_ROOT.joinpath(*ARTIFACT_PARTS, "runs", capture_id)
    directory = custody._Directory(path)
    try:
        report_raw = directory.read("complete.json", cap=MAX_CONTROL_BYTES)
        _need(_sha(report_raw) == expected_report_sha256, "external_capture_report_hash_differs")
        report = _json(report_raw);reservation_raw = directory.read("reservation.json", cap=MAX_CONTROL_BYTES)
        _need(report.get("reservation_sha256") == _sha(reservation_raw), "original_execution_reservation_binding_refused")
        identity = _json(reservation_raw).get("execution_identity")
        _need(type(identity) is dict and identity.get("root") == str(bootstrap.custody.LANE_ROOT)
              and identity.get("branch") == bootstrap.custody.LANE_BRANCH and identity.get("clean") is True
              and type(identity.get("head")) is str and _HEAD.fullmatch(identity["head"])
              and type(identity.get("source_sha256")) is dict and SELF_PATH in identity["source_sha256"]
              and identity.get("source_inventory_sha256") == _sha(_raw(identity["source_sha256"])),
              "original_committed_execution_identity_refused")
        for name, digest in identity["source_sha256"].items():
            _digest(digest)
            _need(type(name) is str and not Path(name).is_absolute() and ".." not in Path(name).parts
                  and _sha(bootstrap.custody._git(bootstrap.custody.LANE_ROOT, "show", identity["head"] + ":" + name)) == digest,
                  "original_committed_capture_source_differs")
        directory.check()
    finally:
        directory.close()


def _verify_selection_payload(selection, *, fixture_only):
    _need(type(selection) is dict and selection.get("schema") == SCHEMA + "/selection"
          and selection.get("fixture_only") is fixture_only and selection.get("authority") == _authority()
          and selection.get("request_form_scope") == ["4", "4/A"]
          and selection.get("context_forms_stay_accounted") is True,
          "capture_selection_context_refused")
    forms = selection.get("form_counts")
    _need(type(forms) is dict and set(forms) == {"3", "3/A", "4", "4/A", "5", "5/A"}
          and all(type(n) is int and n >= 0 for n in forms.values())
          and all(type(selection.get(key)) is int and selection[key] >= 0
                  for key in ("source_filings", "target_filings", "context_filings"))
          and selection["source_filings"] == sum(forms.values())
          and selection["target_filings"] == forms["4"] + forms["4/A"]
          and selection["context_filings"] == sum(forms[key] for key in ("3", "3/A", "5", "5/A")),
          "capture_selection_context_refused")
    rows = selection.get("requests")
    _need(type(rows) is list and len(rows) == MAX_REQUESTS <= selection["target_filings"],
          "capture_selection_context_refused")
    previous, seen, prefix = None, set(), []
    for ordinal, item in enumerate(rows):
        _need(type(item) is dict and set(item) == {"prefix_ordinal", "request_sha256", "request"}
              and type(item["prefix_ordinal"]) is int and item["prefix_ordinal"] == ordinal,
              "capture_selection_context_refused")
        request = _request(item["request"])
        order = (request["filing_date"], request["accession_number"], request["source_record_ordinal"])
        _need(item["request_sha256"] == _sha(_raw(request)) and (previous is None or previous < order)
              and request["accession_number"] not in seen
              and request["source_record_ordinal"] <= selection["source_filings"],
              "capture_selection_context_refused")
        previous = order;seen.add(request["accession_number"]);prefix.append(request)
    _need(selection.get("selected_prefix_sha256") == _sha(_raw(prefix)), "capture_selection_context_refused")


def _verify_terminal(result, *, last):
    status, kind = result.get("status"), result.get("disposition")
    _need(status is None or type(status) is int and 100 <= status <= 599, "capture_terminal_policy_refused")
    if result["body_retained"]:
        expected = "complete_raw_response_retained_header_" + ("bound" if result["header_identity_bound"] else "quarantined")
        _need(kind == expected and status == 200, "capture_terminal_policy_refused")
        return
    _need(last and kind in {"ambiguous_transport_failure_no_retry", "http_refused_no_retry",
          "response_privacy_framing_or_custody_refused_no_retry"}, "capture_terminal_policy_refused")
    if kind == "ambiguous_transport_failure_no_retry":
        _need(all(result.get(key) is None for key in ("status", "response_headers_sha256", "body_sha256",
              "body_size_bytes", "observed_framing_headers")), "capture_terminal_policy_refused")
    elif kind == "http_refused_no_retry":
        _need(status is not None and status != 200 and result.get("body_sha256") is None
              and result.get("body_size_bytes") is None, "capture_terminal_policy_refused")
        _digest(result.get("response_headers_sha256"))


def _verify_capture(capture_id, *, root, expected_report_sha256, fixture_only):
    _need(type(capture_id) is str and _ID.fullmatch(capture_id), "capture_id_refused")
    _digest(expected_report_sha256)
    folders, lock_fd = [], None
    try:
        path = root.joinpath(*ARTIFACT_PARTS)
        namespace = custody._Directory(path);folders.append(namespace)
        claims = custody._Directory(path / "claims");folders.append(claims)
        runs = custody._Directory(path / "runs");folders.append(runs)
        run = custody._Directory(path / "runs" / capture_id);folders.append(run)
        objects = custody._Directory(run.path / "objects");folders.append(objects)
        lock_fd = os.open("capture.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=namespace.fd)
        lock_stat = os.fstat(lock_fd)
        _need(stat.S_ISREG(lock_stat.st_mode) and lock_stat.st_uid == os.geteuid() and lock_stat.st_nlink == 1
              and stat.S_IMODE(lock_stat.st_mode) == 0o600 and namespace.read("capture.lock", cap=1024) == LOCK_BYTES,
              "global_claim_lock_refused")
        fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        report_raw = run.read("complete.json", cap=MAX_CONTROL_BYTES)
        _need(_sha(report_raw) == expected_report_sha256, "external_capture_report_hash_differs")
        report = _json(report_raw)
        reservation_raw = run.read("reservation.json", cap=MAX_CONTROL_BYTES);reservation = _json(reservation_raw)
        contact_raw = run.read("contact-validated.json", cap=MAX_CONTROL_BYTES);contact_control = _json(contact_raw)
        _need(report.get("contact_validation_sha256") == _sha(contact_raw)
              and contact_control == {"schema": SCHEMA + "/contact-validation", "reservation_sha256": _sha(reservation_raw),
                  "contact_present": True, "validated_at_utc": contact_control.get("validated_at_utc"), "contact_value_stored_or_hashed": False}
              and bootstrap._utc(reservation.get("reserved_at_utc")) <= bootstrap._utc(contact_control.get("validated_at_utc")),
              "deferred_contact_validation_binding_refused")
        _need(report.get("schema") == SCHEMA + "/complete" and report.get("capture_id") == capture_id
              and report.get("fixture_only") is fixture_only and report.get("authority") == _authority()
              and report.get("reservation_sha256") == _sha(reservation_raw)
              and reservation.get("schema") == SCHEMA + "/reservation" and reservation.get("capture_id") == capture_id
              and reservation.get("fixture_only") is fixture_only and reservation.get("authority") == _authority()
              and reservation.get("selection_sha256") == report.get("selection_sha256")
              and reservation.get("execution_identity") == reservation.get("selection", {}).get("execution_identity")
              and report.get("capture_execution_head") == reservation.get("capture_execution_head")
              == reservation.get("selection", {}).get("repository_head")
              and report.get("bootstrap_execution_head") == reservation.get("selection", {}).get("bootstrap_execution_head")
              and _sha(_raw(reservation.get("selection"))) == report.get("selection_sha256")
              and reservation.get("claim_policy") == "just_in_time_permanent_accession"
              and reservation.get("contact_present") is False
              and reservation.get("contact_input_mode") == ("invented_fixture_only" if fixture_only else "deferred_private_reader")
              and reservation.get("maximum_attempts_per_request") == 1
              and reservation.get("maximum_body_bytes") == MAX_PARENT_BYTES
              and reservation.get("minimum_completion_spacing_ns") == MIN_COMPLETION_INTERVAL_NS,
              "capture_reservation_or_authority_binding_refused")
        selection = reservation["selection"];rows = selection.get("requests");results = report.get("results")
        _need(type(rows) is list and len(rows) == MAX_REQUESTS and type(results) is list and len(results) <= MAX_REQUESTS
              and selection.get("fixture_only") is fixture_only and selection.get("authority") == _authority()
              and selection.get("request_form_scope") == ["4", "4/A"], "capture_selection_inventory_refused")
        _verify_selection_payload(selection, fixture_only=fixture_only)
        _need(report.get("context_filings_not_requested") == selection["context_filings"]
              and report.get("selected_prefix_sha256") == selection["selected_prefix_sha256"],
              "capture_selection_context_refused")
        for key in ("planned_prefix", "permanent_claims_created", "started_requests", "terminal_result_records", "raw_bodies_retained",
                    "header_bound_bodies", "header_quarantined_bodies", "retained_body_bytes", "planned_unclaimed_unattempted",
                    "context_filings_not_requested", "full_xml_projection_attempts"):
            _need(type(report.get(key)) is int and report[key] >= 0, "capture_count_type_refused")
        prior_claims = reservation.get("prior_claim_inventory");prior_runs = reservation.get("prior_run_inventory")
        _need(type(prior_claims) is dict and type(prior_runs) is list
              and prior_runs == sorted(set(prior_runs)) and all(type(name) is str and _ID.fullmatch(name) for name in prior_runs),
              "prior_new_namespace_inventory_refused")
        retained = [(run, "complete.json", expected_report_sha256, MAX_CONTROL_BYTES),
                    (run, "reservation.json", _sha(reservation_raw), MAX_CONTROL_BYTES),
                    (run, "contact-validated.json", _sha(contact_raw), MAX_CONTROL_BYTES)]
        expected_claims = dict(prior_claims);allowed_run = {"reservation.json", "complete.json", "contact-validated.json", "objects"};allowed_objects = set()
        retained_count, bound_count, total_bytes, previous_finish, previous_utc = 0, 0, 0, None, None
        for ordinal, descriptor in enumerate(results):
            item = rows[ordinal];request = _request(item.get("request"))
            _need(item.get("prefix_ordinal") == ordinal and type(item.get("prefix_ordinal")) is int
                  and item.get("request_sha256") == _sha(_raw(request)), "selection_request_hash_refused")
            claim_name = request["accession_key_sha256"] + ".json"
            claim_raw = claims.read(claim_name, cap=MAX_CONTROL_BYTES);claim = _json(claim_raw)
            _need(claim.get("schema") == SCHEMA + "/request-claim" and claim.get("capture_id") == capture_id
                  and claim.get("request") == item and claim.get("reservation_sha256") == _sha(reservation_raw)
                  and claim.get("selection_sha256") == report["selection_sha256"], "global_claim_reservation_binding_refused")
            expected_claims[claim_name] = _sha(claim_raw);retained.append((claims, claim_name, _sha(claim_raw), MAX_CONTROL_BYTES))
            start_name, result_name = f"request-{ordinal:03d}-start.json", f"request-{ordinal:03d}-result.json"
            _need(type(descriptor) is dict and set(descriptor) == {"result_name", "result_sha256"}
                  and descriptor["result_name"] == result_name, "result_descriptor_order_refused")
            start_raw, result_raw = run.read(start_name, cap=MAX_CONTROL_BYTES), run.read(result_name, cap=MAX_CONTROL_BYTES)
            _need(_sha(result_raw) == descriptor["result_sha256"], "result_external_hash_differs")
            start, result = _json(start_raw), _json(result_raw)
            _need(start.get("schema") == SCHEMA + "/attempt-start" and result.get("schema") == SCHEMA + "/attempt-result"
                  and type(start.get("ordinal")) is int and start["ordinal"] == ordinal
                  and type(result.get("ordinal")) is int and result["ordinal"] == ordinal
                  and type(start.get("attempt")) is int and start["attempt"] == 1
                  and type(result.get("attempt")) is int and result["attempt"] == 1
                  and start.get("reservation_sha256") == _sha(reservation_raw)
                  and start.get("claim_sha256") == _sha(claim_raw)
                  and start.get("request_sha256") == item["request_sha256"] == result.get("request_sha256")
                  and result.get("start_sha256") == _sha(start_raw) and result.get("authority") == _authority(),
                  "attempt_claim_start_result_binding_refused")
            started, finished = start.get("started_monotonic_ns"), result.get("finished_monotonic_ns")
            _need(type(started) is int and type(finished) is int and 0 <= started <= finished
                  and (previous_finish is None or started - previous_finish >= MIN_COMPLETION_INTERVAL_NS),
                  "capture_completion_spacing_refused")
            started_utc, finished_utc = bootstrap._utc(start.get("started_utc")), bootstrap._utc(result.get("finished_utc"))
            _need(bootstrap._utc(claim.get("claimed_at_utc")) <= started_utc <= finished_utc
                  and (previous_utc is None or previous_utc <= started_utc), "capture_clock_order_refused")
            previous_finish, previous_utc = finished, finished_utc
            _need(type(result.get("body_retained")) is bool and type(result.get("header_identity_bound")) is bool
                  and (not result["header_identity_bound"] or result["body_retained"]), "capture_retention_flag_refused")
            _verify_terminal(result, last=ordinal == len(results) - 1)
            if result["body_retained"]:
                _need(type(result.get("body_size_bytes")) is int and 0 < result["body_size_bytes"] <= MAX_PARENT_BYTES
                      and type(result.get("status")) is int and result["status"] == 200,
                      "retained_response_size_status_refused")
                name = _digest(result.get("body_sha256")) + ".bin"
                raw = objects.read(name, cap=MAX_PARENT_BYTES)
                _need(len(raw) == result["body_size_bytes"] and _sha(raw) == result["body_sha256"], "retained_body_hash_or_size_differs")
                framing = result.get("observed_framing_headers")
                _need(type(framing) is list and all(type(pair) is list and len(pair) == 2 and all(type(v) is str for v in pair)
                      and pair[0].lower() in {"content-length", "content-encoding", "transfer-encoding", "content-type"} for pair in framing),
                      "observed_response_framing_shape_refused")
                _strict_selected_response(SecHttpResult(200, tuple(tuple(pair) for pair in framing), raw), max_bytes=MAX_PARENT_BYTES)
                if result["header_identity_bound"]:
                    _envelope_and_header(raw, request);bound_count += 1
                retained_count += 1;total_bytes += len(raw);allowed_objects.add(name)
                retained.append((objects, name, result["body_sha256"], MAX_PARENT_BYTES))
            allowed_run.update((start_name, result_name))
            retained.extend(((run, start_name, _sha(start_raw), MAX_CONTROL_BYTES),
                             (run, result_name, _sha(result_raw), MAX_CONTROL_BYTES)))
        _need(report["planned_prefix"] == MAX_REQUESTS and report["permanent_claims_created"] == len(results)
              and report["started_requests"] == report["terminal_result_records"] == len(results)
              and report["raw_bodies_retained"] == retained_count and report["header_bound_bodies"] == bound_count
              and report["header_quarantined_bodies"] == retained_count - bound_count
              and report["retained_body_bytes"] == total_bytes and report["planned_unclaimed_unattempted"] == MAX_REQUESTS - len(results)
              and report.get("scope_terminal_accounting_complete") is (len(results) == MAX_REQUESTS)
              and report["full_xml_projection_attempts"] == 0 and report.get("source_authenticated") is False
              and report.get("old_roots_written") is False and report.get("all_six_form_census_preserved") is True,
              "aggregate_capture_accounting_refused")
        _need(_claim_inventory(claims) == expected_claims and set(os.listdir(runs.fd)) == set(prior_runs) | {capture_id}
              and set(os.listdir(run.fd)) == allowed_run and set(os.listdir(objects.fd)) == allowed_objects
              and set(os.listdir(namespace.fd)) == {"claims", "runs", "capture.lock"}, "complete_capture_inventory_refused")
        for folder, name, digest, cap in retained:
            _need(_sha(folder.read(name, cap=cap)) == digest, "capture_changed_during_verification")
        _need(custody._file_version(os.fstat(lock_fd)) == custody._file_version(lock_stat)
              == custody._file_version(os.stat("capture.lock", dir_fd=namespace.fd, follow_symlinks=False)), "global_claim_lock_changed")
        for folder in folders:
            folder.check()
        return {"fixture_only": fixture_only, "report_sha256": expected_report_sha256,
                "started_requests": len(results), "raw_bodies_retained": retained_count, "header_bound_bodies": bound_count,
                "parent_xml_projection_performed": False, "authority": _authority()}
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        for folder in reversed(folders):
            folder.close()


def _verify_worker(args):
    _need(Path(__file__).resolve() == bootstrap.custody.LANE_ROOT / SELF_PATH
          and Path.cwd() == bootstrap.custody.LANE_ROOT, "inactive_draft_not_production_source")
    identity = _json(sys.stdin.buffer.read(4 * MAX_CONTROL_BYTES))
    bootstrap._required_identity(identity, args.expected_head)
    _need(SELF_PATH in identity["source_sha256"], "committed_capture_source_required")
    bootstrap.custody._effective_denial(require_fork=True)
    probe = bootstrap.custody.LANE_ROOT.joinpath(*ARTIFACT_PARTS, "isolation-" + args.capture_id + ".probe")
    try:
        fd = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        _need(exc.errno in {errno.EPERM, errno.EACCES}, "effective_verifier_write_denial_not_observed")
    else:
        os.close(fd);raise EarlyParentCaptureError("effective_verifier_write_denial_not_observed")
    _need(bootstrap.custody._source_bytes(bootstrap.custody.LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"],
          "verifier_current_source_changed")
    result = _verify_capture(args.capture_id, root=bootstrap.custody.LANE_ROOT,
                             expected_report_sha256=args.expected_report_sha256, fixture_only=False)
    _need(bootstrap.custody._source_bytes(bootstrap.custody.LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"],
          "verifier_current_source_changed")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--capture", action="store_true")
    modes.add_argument("--verify-only", action="store_true")
    modes.add_argument("--verify-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--capture-id", required=True);parser.add_argument("--expected-head", required=True)
    parser.add_argument("--bootstrap-id");parser.add_argument("--expected-bootstrap-complete-sha256")
    parser.add_argument("--expected-accounting-sha256");parser.add_argument("--expected-snapshot-sha256")
    parser.add_argument("--expected-report-sha256")
    contacts = parser.add_mutually_exclusive_group()
    contacts.add_argument("--read-contact-from-stdin", action="store_true")
    contacts.add_argument("--getpass-contact", action="store_true")
    args = parser.parse_args(argv)
    saved_echo = None
    failure_phase = "preflight"
    try:
        if args.verify_worker:
            failure_phase = "verifier_worker"
            result = _verify_worker(args)
        elif args.verify_only:
            failure_phase = "verifier"
            result = verify_observed_capture(args.capture_id, expected_report_sha256=args.expected_report_sha256,
                                             expected_head=args.expected_head)
        else:
            _need(args.read_contact_from_stdin or args.getpass_contact, "explicit_private_contact_mode_required")
            if args.read_contact_from_stdin:
                saved_echo = _protect_stdin_echo()
            selected = build_observed_selection(args.bootstrap_id,
                expected_bootstrap_complete_sha256=args.expected_bootstrap_complete_sha256,
                expected_accounting_sha256=args.expected_accounting_sha256, expected_snapshot_sha256=args.expected_snapshot_sha256,
                expected_head=args.expected_head)
            failure_phase = "capture"
            result = run_observed_capture(selected, args.capture_id, contact_mode="stdin" if args.read_contact_from_stdin else "getpass")
        print(_raw(result).decode());return 0
    except (EarlyParentCaptureError, bootstrap.ParentBootstrapError, bootstrap.custody.ArchiveAssessmentRunnerError,
            bootstrap.custody.EodhdDemoError, custody.FreshV4CaptureError, OSError, ValueError, TypeError, KeyError,
            subprocess.SubprocessError) as exc:
        print(_raw(_failure_diagnostic(exc, failure_phase)).decode());return 2
    finally:
        _restore_stdin_echo(saved_echo)


if __name__ == "__main__":
    raise SystemExit(main())
