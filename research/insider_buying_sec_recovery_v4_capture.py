"""Fresh, separately journaled first <=64 SEC originals; never stopped-v3 resume.

Import-inert. Real dispatch requires a genuine sealed isolated selection and
clean exact committed source. Fixed shared claims survive failures/crashes and
different capture IDs; no request is retried or silently skipped. Contact is
ephemeral runtime input, never an argument/log/journal/environment variable.
All corpus/PIT/rights/canonical/QC/backtest/trading claims remain false.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import getpass
import hashlib
import html
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from urllib.parse import unquote


VERSION = "INSETF-IB1B-FRESH-FIRST-PREFIX-CAPTURE-v4"
SELF_PATH = "research/insider_buying_sec_recovery_v4_capture.py"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "sec_recovery_v4")
MAX_PARENT_BYTES = 8 * 1024 * 1024
MAX_REQUESTS = 64
MAX_BATCH_BODY_BYTES = MAX_REQUESTS * MAX_PARENT_BYTES
MIN_FREE_BYTES = 8 * 1024**3
MIN_COMPLETION_INTERVAL_NS = 500_000_000
_ID = re.compile(r"[a-z][a-z0-9-]{0,79}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CONTACT = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+)\Z")
_ECHO_ESCAPE = re.compile(r"\\(?:u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8})|x([0-9a-fA-F]{2}))")
MAX_ECHO_DECODE_LAYERS = 8
_OWN_FILES = (SELF_PATH, "research/insider_buying_sec_recovery_v4_selection.py",
              "tests/test_insider_buying_sec_recovery_v4_capture.py", "tests/test_insider_buying_sec_recovery_v4_selection.py")


class FreshV4CaptureError(ValueError):
    pass


def _refuse(reason):
    raise FreshV4CaptureError("REFUSED: " + reason)


def _canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii") + b"\n"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _contact(value, *, observed):
    if type(value) is not str or not value.isascii() or not 3 <= len(value) <= 254:
        _refuse("runtime SEC contact is invalid")
    match = _CONTACT.fullmatch(value)
    if match is None or len(value.split("@", 1)[0]) > 64 or ".." in value:
        _refuse("runtime SEC contact is invalid")
    domain = match.group(1).lower()
    labels = domain.split(".")
    if (len(labels) < 2 or not 2 <= len(labels[-1]) <= 63 or not labels[-1].isalpha()
            or any(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", item) is None for item in labels)
            or observed and (domain in {"example.com", "example.net", "example.org"}
                or domain.endswith((".example", ".test", ".invalid", ".localhost")))):
        _refuse("runtime SEC contact is invalid")
    return value


def _echo_decode_layer(value):
    # Screening view only: retained SEC bytes are never rewritten. Decode
    # standard Unicode/hex, HTML and percent escapes with bounded convergence.
    # Unsupported deeper nesting refuses retention rather than silently passes.
    def character(match):
        try: return chr(int(next(item for item in match.groups() if item is not None), 16))
        except ValueError: _refuse("contact echo screening encoding is unsupported")
    return unquote(html.unescape(_ECHO_ESCAPE.sub(character, value)), errors="strict")


def _screen_contact_echo(decoded, contact):
    needles, value = {contact.lower()}, contact
    for _ in range(MAX_ECHO_DECODE_LAYERS):
        next_value = _echo_decode_layer(value)
        needles.add(next_value.lower())
        if next_value == value: break
        value = next_value
    else: _refuse("contact echo screening encoding depth exceeded")
    value = decoded
    for _ in range(MAX_ECHO_DECODE_LAYERS):
        # Check before decoding too: a literal '%' in the valid email must not
        # disappear from the response before it is compared with that email.
        if any(needle in value.lower() for needle in needles):
            _refuse("contact echo cannot be retained")
        next_value = _echo_decode_layer(value)
        if next_value == value: return
        value = next_value
    _refuse("contact echo screening encoding depth exceeded")


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _stamp(clock):
    value = clock()
    if type(value) is not str:
        _refuse("journal clock is invalid")
    try: stamp = datetime.fromisoformat(value)
    except ValueError: _refuse("journal clock is invalid")
    if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
        _refuse("journal clock is not aware UTC")
    return stamp.isoformat(timespec="microseconds")


def _file_version(value):
    # Reading legitimately changes atime; immutable content/custody does not.
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class _Directory:
    """FD-relative private leaves; recheck the complete named ancestor chain."""
    def __init__(self, path, *, create=False, private=True):
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts or path != Path(os.path.abspath(path)):
            _refuse("journal path is not canonical absolute")
        self.path, self.chain, self.fd = path, [], None
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
        current = os.open("/", flags)
        self.chain.append((None, None, current, os.fstat(current)))
        try:
            for part in path.parts[1:]:
                parent = current
                try: current = os.open(part, flags, dir_fd=parent)
                except FileNotFoundError:
                    if not create: raise
                    try: os.mkdir(part, 0o700, dir_fd=parent); os.fsync(parent)
                    except FileExistsError: pass
                    current = os.open(part, flags, dir_fd=parent)
                self.chain.append((parent, part, current, os.fstat(current)))
            self.fd = current
            self.private = private
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        for parent, name, fd, original in self.chain:
            current = os.fstat(fd)
            named = current if parent is None else os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISDIR(named.st_mode) or not stat.S_ISDIR(current.st_mode)
                    or (named.st_dev, named.st_ino) != (original.st_dev, original.st_ino)
                    or (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino)):
                _refuse("journal ancestor identity changed")
        if self.private and (stat.S_IMODE(current.st_mode) != 0o700 or current.st_uid != os.geteuid()):
            _refuse("journal directory is not private owner custody")

    def exists(self, name):
        self.check()
        try: os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError: return False
        return True

    def publish(self, name, raw, *, cap=256 * 1024):
        self.check()
        if type(name) is not str or "/" in name or name in {"", ".", ".."} or type(raw) is not bytes or not 0 < len(raw) <= cap:
            _refuse("immutable journal leaf differs")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=self.fd)
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0: _refuse("journal write made no progress")
                offset += written
            os.fsync(fd)
            actual = os.fstat(fd); named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if (not stat.S_ISREG(actual.st_mode) or stat.S_IMODE(actual.st_mode) != 0o600
                    or actual.st_nlink != 1 or actual.st_uid != os.geteuid() or actual.st_size != len(raw)
                    or (actual.st_dev, actual.st_ino) != (named.st_dev, named.st_ino)):
                _refuse("immutable journal leaf changed")
        finally: os.close(fd)
        os.fsync(self.fd)
        self.check()
        return _sha(raw)

    def read(self, name, *, cap=256 * 1024):
        self.check()
        named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1 or stat.S_IMODE(named.st_mode) != 0o600
                or named.st_uid != os.geteuid() or not 0 < named.st_size <= cap):
            _refuse("journal leaf is not bounded private regular custody")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            if _file_version(before) != _file_version(named): _refuse("journal leaf was substituted")
            raw = bytearray()
            while True:
                chunk = os.read(fd, min(65536, cap + 1 - len(raw)))
                if not chunk: break
                raw.extend(chunk)
                if len(raw) > cap: _refuse("journal leaf exceeds bound")
            after = os.fstat(fd); named_after = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if (_file_version(before) != _file_version(after) or _file_version(after) != _file_version(named_after)
                    or after.st_nlink != 1 or len(raw) != after.st_size):
                _refuse("journal leaf changed while reading")
        finally: os.close(fd)
        self.check()
        return bytes(raw)

    def close(self):
        for _, _, fd, _ in reversed(self.chain):
            try: os.close(fd)
            except OSError: pass
        self.chain = []


def _decode(raw):
    def unique(pairs):
        body = {}
        for key, value in pairs:
            if key in body: _refuse("journal JSON repeats a key")
            body[key] = value
        return body
    try: body = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: _refuse("journal JSON is nonfinite"))
    except (ValueError, UnicodeError, RecursionError): _refuse("journal JSON is malformed")
    if type(body) is not dict or _canonical(body) != raw: _refuse("journal JSON is not canonical")
    return body


def _claim_name(row):
    # Accession remains globally unique even if a future locator alias changes.
    return _sha(row["request"]["accession_number"].encode("ascii")) + ".json"


def _guard_committed(selection, expected_head):
    from research import insider_buying_sec_recovery_v4_selection as select
    base = select._base()
    body = selection.to_payload()
    head, status = base._repository_snapshot()
    if (head != expected_head or body["repository_head"] != expected_head or status
            or Path(__file__).resolve() != base.LANE_ROOT / SELF_PATH):
        _refuse("exact clean committed selection/capture lane is required")
    sources = base._source_snapshot()
    if body["current_source_inventory_sha256"] != select._hash([{"path": p, "sha256": select._sha(raw)} for p, raw in sources]):
        _refuse("current source inventory differs from genuine replay")
    for path, raw in sources:
        if base._git("cat-file", "blob", f"{expected_head}:{path}") != raw:
            _refuse("replayed source is not exact committed code")
    for path in _OWN_FILES:
        if base._git("cat-file", "blob", f"{expected_head}:{path}") != (base.LANE_ROOT / path).read_bytes():
            _refuse("capture/selection code or tests are not committed")


def _authority(observed):
    return {"bounded_named_source_acquisition_scope": observed, "source_authenticated": False,
        "official_acceptance_verified": False, "publication_time_verified": False, "point_in_time_data": False,
        "rights_verified": False, "canonical_evidence": False, "complete_corpus": False,
        "qc_authorized": False, "backtest_authorized": False, "execution_authorized": False,
        "outcome_looks": 0, "qc_jobs": 0, "backtests": 0}


def _capture(selection, capture_id, expected_head, contact_email, *, root, transport,
             guard, clock=_utc, monotonic_ns=time.monotonic_ns, sleep=time.sleep,
             free_bytes=None, observed=False):
    from research import insider_buying_sec_recovery_v4_selection as select
    from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport, _strict_selected_response
    from research.insider_buying_sec_complete_acquisition import SecHttpResult
    from research.insider_buying_sec_complete_acquisition import SecCompleteAcquisitionError
    from research.insider_buying_sec_all_form4_parent_campaign import CampaignError, _validate_parent_header
    if type(observed) is not bool or type(capture_id) is not str or _ID.fullmatch(capture_id) is None:
        _refuse("capture identity differs")
    if observed:
        if type(selection) is not select.FreshV4Selection or transport is not _selected_sec_transport or root != select._base().LANE_ROOT:
            _refuse("real capture requires fixed genuine selection/transport/root")
    elif type(selection) is not select.InventedV4Selection or transport is _selected_sec_transport:
        _refuse("invented capture cannot use production selection or SEC transport")
    contact_email = _contact(contact_email, observed=observed)
    body = selection.to_payload()
    if body["repository_head"] != expected_head: _refuse("selection repository HEAD differs")
    rows = body["requests"]
    guard()
    root = Path(root)
    anchor = _Directory(root, private=False)
    base = claims = runs = run = objects = None
    lock_fd, lock_owned = None, False
    try:
        base_path = root.joinpath(*ARTIFACT_PARTS)
        base = _Directory(base_path, create=True)
        claims = _Directory(base_path / "claims", create=True)
        runs = _Directory(base_path / "runs", create=True)
        anchor.check(); base.check()
        if not base.exists("capture.lock"): base.publish("capture.lock", b"INSETF-v4-global-claim-lock\n")
        lock_fd = os.open("capture.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=base.fd)
        lock_stat = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1 or stat.S_IMODE(lock_stat.st_mode) != 0o600:
            _refuse("global capture lock custody differs")
        try: fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: _refuse("another fresh v4 capture owns the global claims lock")
        lock_owned = True
        if runs.exists(capture_id): _refuse("completed or ambiguous capture root already exists")
        if any(claims.exists(_claim_name(row)) for row in rows):
            _refuse("an originally-unattempted request is already reserved by a fresh capture")
        capacity = free_bytes() if free_bytes is not None else os.fstatvfs(base.fd).f_bavail * os.fstatvfs(base.fd).f_frsize
        if type(capacity) is not int or capacity < MIN_FREE_BYTES + len(rows) * MAX_PARENT_BYTES:
            _refuse("fresh capture capacity reserve is insufficient")
        os.mkdir(capture_id, 0o700, dir_fd=runs.fd); os.fsync(runs.fd); runs.check()
        run = _Directory(base_path / "runs" / capture_id)
        objects = _Directory(run.path / "objects", create=True)
        reservation = {"kind": VERSION + "/reservation", "capture_id": capture_id, "capture_git_commit": expected_head,
            "selection_sha256": selection.sha256, "selection": body, "contact_present": True,
            "maximum_sec_dispatches": len(rows), "maximum_attempts_per_request": 1,
            "completion_spacing_ns": MIN_COMPLETION_INTERVAL_NS, "maximum_parent_bytes": MAX_PARENT_BYTES,
            "maximum_batch_body_bytes": len(rows) * MAX_PARENT_BYTES, "claims_namespace": "/".join(ARTIFACT_PARTS) + "/claims",
            "authority": _authority(observed)}
        reservation_sha = run.publish("reservation.json", _canonical(reservation))
        retained = [(run, "reservation.json", reservation_sha, 256 * 1024)]
        claim_shas = []
        for row in rows:
            claim = {"kind": VERSION + "/request-claim", "capture_id": capture_id, "reservation_sha256": reservation_sha,
                "selection_sha256": selection.sha256, "selected_prefix_sha256": body["selected_prefix_sha256"],
                "replay_anchors": body["replay_anchors"], "request": row}
            name = _claim_name(row); digest = claims.publish(name, _canonical(claim))
            retained.append((claims, name, digest, 256 * 1024)); claim_shas.append(digest)
        def custody():
            anchor.check(); base.check(); runs.check(); run.check(); objects.check(); claims.check()
            named = os.stat("capture.lock", dir_fd=base.fd, follow_symlinks=False)
            if (named.st_dev, named.st_ino) != (lock_stat.st_dev, lock_stat.st_ino) or named.st_nlink != 1:
                _refuse("global claims lock was substituted")
            for folder, name, digest, cap in retained:
                if _sha(folder.read(name, cap=cap)) != digest: _refuse("durable capture or claim bytes changed")
        headers = {"User-Agent": f"InsiderBuyingResearch-v4-first64/1.0 ({contact_email})",
                   "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close"}
        results, completed, total_bytes, last_finish = [], 0, 0, None
        for ordinal, row in enumerate(rows):
            custody(); guard()
            if last_finish is not None:
                now = monotonic_ns()
                if type(now) is not int or now < last_finish: _refuse("monotonic completion clock differs")
                if now - last_finish < MIN_COMPLETION_INTERVAL_NS:
                    sleep((MIN_COMPLETION_INTERVAL_NS - (now - last_finish)) / 1_000_000_000)
                after = monotonic_ns()
                if type(after) is not int or after - last_finish < MIN_COMPLETION_INTERVAL_NS:
                    _refuse("required completion spacing was not observed")
            started_ns = monotonic_ns()
            if (type(started_ns) is not int or started_ns < 0
                    or last_finish is not None and started_ns - last_finish < MIN_COMPLETION_INTERVAL_NS):
                _refuse("dispatch monotonic clock or completion spacing differs")
            start = {"kind": VERSION + "/attempt-start", "ordinal": ordinal, "attempt": 1,
                "request_sha256": row["request_sha256"], "global_index": row["global_index"],
                "reservation_sha256": reservation_sha, "claim_sha256": claim_shas[ordinal],
                "started_monotonic_ns": started_ns, "started_utc": _stamp(clock)}
            start_name = f"request-{ordinal:03d}-start.json"
            start_sha = run.publish(start_name, _canonical(start)); retained.append((run, start_name, start_sha, 256 * 1024))
            custody(); guard()
            outcome, status, body_size, body_sha, headers_sha = "ambiguous_transport_failure", None, None, None, None
            try:
                response = transport(row["request"]["url"], headers, MAX_PARENT_BYTES)
            except Exception:
                pass  # Exact fsynced start/claim remain consumed, never retried.
            else:
                accepted_raw = None
                try:
                    if (type(response) is not SecHttpResult or type(response.status) is not int or not 100 <= response.status <= 599
                            or type(response.headers) is not tuple or len(response.headers) > 64
                            or any(type(pair) is not tuple or len(pair) != 2 or any(type(v) is not str for v in pair)
                                   for pair in response.headers) or len(_canonical(response.headers)) > 16 * 1024
                            or type(response.body) is not bytes or len(response.body) > MAX_PARENT_BYTES):
                        _refuse("response metadata differs")
                    status, headers_sha = response.status, _sha(_canonical(response.headers))
                    body_size, body_sha = len(response.body), _sha(response.body)
                    if status != 200:
                        outcome = "http-refused-no-retry" if not response.body else "invalid-response-no-retry"
                    else:
                        raw = _strict_selected_response(response, max_bytes=MAX_PARENT_BYTES)
                        decoded = raw.decode("utf-8", "replace")
                        _screen_contact_echo(decoded, contact_email)
                        _validate_parent_header(raw, row["request"])
                        if total_bytes + len(raw) > len(rows) * MAX_PARENT_BYTES: _refuse("batch body cap exceeded")
                        accepted_raw = raw
                except (FreshV4CaptureError, SecCompleteAcquisitionError, CampaignError, UnicodeError, ValueError, TypeError, KeyError, RecursionError):
                    outcome = "invalid-response-or-parent-no-retry"
                if accepted_raw is not None:
                    # A persistence failure is not an invalid source response.
                    # It leaves an incomplete consumed start/claim and escapes.
                    digest = objects.publish(body_sha + ".bin", accepted_raw, cap=MAX_PARENT_BYTES)
                    retained.append((objects, body_sha + ".bin", digest, MAX_PARENT_BYTES))
                    total_bytes += len(accepted_raw); completed += 1; outcome = "request-bound-parent-retained"
            last_finish = monotonic_ns()
            if type(last_finish) is not int or last_finish < started_ns: _refuse("completion clock differs")
            result = {"kind": VERSION + "/attempt-result", "ordinal": ordinal, "attempt": 1,
                "start_sha256": start_sha, "request_sha256": row["request_sha256"], "global_index": row["global_index"],
                "disposition": outcome, "status": status, "response_headers_sha256": headers_sha,
                "body_size_bytes": body_size, "body_sha256": body_sha,
                "body_retained": outcome == "request-bound-parent-retained",
                "finished_monotonic_ns": last_finish, "finished_utc": _stamp(clock)}
            result_name = f"request-{ordinal:03d}-result.json"
            result_sha = run.publish(result_name, _canonical(result)); retained.append((run, result_name, result_sha, 256 * 1024))
            results.append({"result_name": result_name, "result_sha256": result_sha})
            custody(); guard()
            if outcome != "request-bound-parent-retained": break
        report = {"kind": VERSION + "/report", "capture_id": capture_id, "reservation_sha256": reservation_sha,
            "selection_sha256": selection.sha256, "selected_prefix_sha256": body["selected_prefix_sha256"],
            "scope": "observed_first_originally_unattempted_prefix" if observed else "invented_test_only",
            "sec_dispatches": len(results), "reserved_requests": len(rows), "reserved_not_attempted": len(rows) - len(results),
            "completed_request_bound_bodies": completed, "retained_body_bytes": total_bytes, "results": results,
            "batch_completed": completed == len(rows), "stopped_v3_not_written_by_capture": True,
            "original_frozen_source_bound_count": 19526 if observed else 0, "union_promotion_performed": False,
            "authority": _authority(observed)}
        report_sha = run.publish("complete.json", _canonical(report))
        retained.append((run, "complete.json", report_sha, 256 * 1024))
        custody(); guard()
        return {"capture_id": capture_id, "report_sha256": report_sha, "selection_sha256": selection.sha256,
                "selected_prefix_sha256": body["selected_prefix_sha256"], "sec_dispatches": len(results),
                "completed_request_bound_bodies": completed, "retained_body_bytes": total_bytes,
                "batch_completed": completed == len(rows), "scope": report["scope"], "authority": _authority(observed)}
    finally:
        if lock_fd is not None:
            try:
                if lock_owned: fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally: os.close(lock_fd)
        for folder in (objects, run, runs, claims, base, anchor):
            if folder is not None: folder.close()


def run_observed_fresh_v4_capture(selection, capture_id, *, expected_head, contact_email):
    """Explicit real boundary. No transport/root override or resume exists."""
    from research import insider_buying_sec_recovery_v4_selection as select
    from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport
    if type(selection) is not select.FreshV4Selection: _refuse("genuinely replayed observed selection required")
    try:
        return _capture(selection, capture_id, expected_head, contact_email, root=select._base().LANE_ROOT,
            transport=_selected_sec_transport, guard=lambda: _guard_committed(selection, expected_head), observed=True)
    except FreshV4CaptureError:
        raise
    except Exception:
        raise FreshV4CaptureError("REFUSED: fresh capture failed; existing claims/starts stay consumed") from None


def _run_invented_capture(selection, capture_id, *, root, transport, contact_email="invented@unit.test", **kwargs):
    """Private test seam; source acquisition scope stays false."""
    return _capture(selection, capture_id, selection.to_payload()["repository_head"], contact_email,
        root=Path(root), transport=transport, guard=kwargs.pop("guard", lambda: None),
        free_bytes=kwargs.pop("free_bytes", lambda: 1 << 50), observed=False, **kwargs)


def _verify_capture(capture_id, expected_report_sha256, *, root, observed):
    """Read-only private-byte replay; does not mint a dispatch selection."""
    from research import insider_buying_sec_recovery_v4_selection as select
    from research.insider_buying_sec_all_form4_parent_campaign import _validate_parent_header
    if (type(capture_id) is not str or _ID.fullmatch(capture_id) is None
            or type(expected_report_sha256) is not str or _SHA.fullmatch(expected_report_sha256) is None
            or type(observed) is not bool):
        _refuse("read-only capture anchor differs")
    folders = []
    try:
        root = Path(root)
        anchor = _Directory(root, private=False); folders.append(anchor)
        base_path = root.joinpath(*ARTIFACT_PARTS)
        base = _Directory(base_path); folders.append(base)
        claims = _Directory(base_path / "claims"); folders.append(claims)
        runs = _Directory(base_path / "runs"); folders.append(runs)
        run = _Directory(runs.path / capture_id); folders.append(run)
        objects = _Directory(run.path / "objects"); folders.append(objects)
        report_raw = run.read("complete.json")
        if _sha(report_raw) != expected_report_sha256: _refuse("capture report hash differs")
        report = _decode(report_raw)
        report_keys = {"kind", "capture_id", "reservation_sha256", "selection_sha256", "selected_prefix_sha256", "scope",
            "sec_dispatches", "reserved_requests", "reserved_not_attempted", "completed_request_bound_bodies",
            "retained_body_bytes", "results", "batch_completed", "stopped_v3_not_written_by_capture",
            "original_frozen_source_bound_count", "union_promotion_performed", "authority"}
        if (set(report) != report_keys or report["kind"] != VERSION + "/report" or report["capture_id"] != capture_id
                or report["scope"] != ("observed_first_originally_unattempted_prefix" if observed else "invented_test_only")
                or report["stopped_v3_not_written_by_capture"] is not True or report["union_promotion_performed"] is not False
                or report["authority"] != _authority(observed)
                or any(type(report["authority"][k]) is not type(v) for k, v in _authority(observed).items())):
            _refuse("capture report scope or authority differs")
        reservation_raw = run.read("reservation.json")
        if _sha(reservation_raw) != report["reservation_sha256"]: _refuse("reservation hash differs")
        reservation = _decode(reservation_raw)
        reservation_keys = {"kind", "capture_id", "capture_git_commit", "selection_sha256", "selection", "contact_present",
            "maximum_sec_dispatches", "maximum_attempts_per_request", "completion_spacing_ns", "maximum_parent_bytes",
            "maximum_batch_body_bytes", "claims_namespace", "authority"}
        if (set(reservation) != reservation_keys or reservation["kind"] != VERSION + "/reservation"
                or reservation["capture_id"] != capture_id or reservation["contact_present"] is not True
                or reservation["claims_namespace"] != "/".join(ARTIFACT_PARTS) + "/claims"
                or reservation["authority"] != report["authority"]
                or any(type(reservation[k]) is not int or reservation[k] != v for k, v in (
                    ("maximum_attempts_per_request", 1), ("completion_spacing_ns", MIN_COMPLETION_INTERVAL_NS),
                    ("maximum_parent_bytes", MAX_PARENT_BYTES)))):
            _refuse("reservation scope or fixed request profile differs")
        selected = select._validate_body(reservation["selection"], observed=observed)
        rows = selected["requests"]
        if (reservation["capture_git_commit"] != selected["repository_head"]
                or reservation["selection_sha256"] != select._hash(selected)
                or report["selection_sha256"] != reservation["selection_sha256"]
                or report["selected_prefix_sha256"] != selected["selected_prefix_sha256"]
                or any(type(container[k]) is not int or container[k] != v for container, k, v in (
                    (reservation, "maximum_sec_dispatches", len(rows)),
                    (reservation, "maximum_batch_body_bytes", len(rows) * MAX_PARENT_BYTES),
                    (report, "reserved_requests", len(rows)),
                    (report, "original_frozen_source_bound_count", 19526 if observed else 0)))
                or type(report["sec_dispatches"]) is not int or not 1 <= report["sec_dispatches"] <= len(rows)
                or type(report["results"]) is not list or len(report["results"]) != report["sec_dispatches"]):
            _refuse("selection/hash/denominator differs")
        retained = [(run, "complete.json", expected_report_sha256, 256 * 1024),
                    (run, "reservation.json", report["reservation_sha256"], 256 * 1024)]
        claim_hashes = []
        for row in rows:
            name = _claim_name(row); raw = claims.read(name); claim = _decode(raw)
            if claim != {"kind": VERSION + "/request-claim", "capture_id": capture_id,
                "reservation_sha256": report["reservation_sha256"], "selection_sha256": report["selection_sha256"],
                "selected_prefix_sha256": report["selected_prefix_sha256"], "replay_anchors": selected["replay_anchors"], "request": row}:
                _refuse("global request claim differs")
            digest = _sha(raw); claim_hashes.append(digest); retained.append((claims, name, digest, 256 * 1024))
        allowed_run, allowed_objects = {"reservation.json", "complete.json", "objects"}, set()
        completed, total, previous = 0, 0, None
        dispositions = {"request-bound-parent-retained", "ambiguous_transport_failure", "http-refused-no-retry",
                        "invalid-response-no-retry", "invalid-response-or-parent-no-retry"}
        for ordinal, descriptor in enumerate(report["results"]):
            row = rows[ordinal]
            start_name, result_name = f"request-{ordinal:03d}-start.json", f"request-{ordinal:03d}-result.json"
            if (type(descriptor) is not dict or set(descriptor) != {"result_name", "result_sha256"}
                    or descriptor["result_name"] != result_name): _refuse("ordered result descriptor differs")
            start_raw, result_raw = run.read(start_name), run.read(result_name)
            start, result = _decode(start_raw), _decode(result_raw)
            if _sha(result_raw) != descriptor["result_sha256"]: _refuse("attempt result hash differs")
            if (set(start) != {"kind", "ordinal", "attempt", "request_sha256", "global_index", "reservation_sha256",
                    "claim_sha256", "started_monotonic_ns", "started_utc"}
                    or set(result) != {"kind", "ordinal", "attempt", "start_sha256", "request_sha256", "global_index",
                    "disposition", "status", "response_headers_sha256", "body_size_bytes", "body_sha256",
                    "body_retained", "finished_monotonic_ns", "finished_utc"}
                    or start["kind"] != VERSION + "/attempt-start" or result["kind"] != VERSION + "/attempt-result"
                    or result["start_sha256"] != _sha(start_raw) or start["claim_sha256"] != claim_hashes[ordinal]
                    or start["reservation_sha256"] != report["reservation_sha256"]
                    or any(type(container[k]) is not int or container[k] != v for container in (start, result)
                        for k, v in (("ordinal", ordinal), ("attempt", 1), ("global_index", row["global_index"])))
                    or any(container["request_sha256"] != row["request_sha256"] for container in (start, result))
                    or type(start["started_monotonic_ns"]) is not int or start["started_monotonic_ns"] < 0
                    or type(result["finished_monotonic_ns"]) is not int or result["finished_monotonic_ns"] < start["started_monotonic_ns"]
                    or previous is not None and start["started_monotonic_ns"] - previous < MIN_COMPLETION_INTERVAL_NS
                    or result["disposition"] not in dispositions
                    or type(result["body_retained"]) is not bool
                    or result["body_retained"] is not (result["disposition"] == "request-bound-parent-retained")
                    or result["status"] is not None and (type(result["status"]) is not int or not 100 <= result["status"] <= 599)
                    or result["body_size_bytes"] is not None and (type(result["body_size_bytes"]) is not int or not 0 <= result["body_size_bytes"] <= MAX_PARENT_BYTES)
                    or any(result[k] is not None and (type(result[k]) is not str or _SHA.fullmatch(result[k]) is None)
                           for k in ("response_headers_sha256", "body_sha256"))):
                _refuse("attempt/claim identity, single-attempt or spacing differs")
            _stamp(lambda: start["started_utc"]); _stamp(lambda: result["finished_utc"])
            previous = result["finished_monotonic_ns"]
            if result["body_retained"]:
                if (type(result["status"]) is not int or result["status"] != 200 or type(result["body_size_bytes"]) is not int
                        or not 0 < result["body_size_bytes"] <= MAX_PARENT_BYTES or type(result["body_sha256"]) is not str
                        or _SHA.fullmatch(result["body_sha256"]) is None): _refuse("retained parent descriptor differs")
                name = result["body_sha256"] + ".bin"; raw = objects.read(name, cap=MAX_PARENT_BYTES)
                if len(raw) != result["body_size_bytes"] or _sha(raw) != result["body_sha256"]: _refuse("retained parent bytes differ")
                _validate_parent_header(raw, row["request"])
                retained.append((objects, name, result["body_sha256"], MAX_PARENT_BYTES)); allowed_objects.add(name)
                completed += 1; total += len(raw)
            elif ordinal != len(report["results"]) - 1:
                _refuse("capture continued after refusal or ambiguity")
            allowed_run.update((start_name, result_name))
            retained.extend(((run, start_name, _sha(start_raw), 256 * 1024),
                             (run, result_name, descriptor["result_sha256"], 256 * 1024)))
        if (set(os.listdir(run.fd)) != allowed_run or set(os.listdir(objects.fd)) != allowed_objects
                or any(type(report[k]) is not int or report[k] != v for k, v in (
                    ("reserved_not_attempted", len(rows) - len(report["results"])),
                    ("completed_request_bound_bodies", completed), ("retained_body_bytes", total)))
                or report["batch_completed"] is not (completed == len(rows))):
            _refuse("report counts or complete journal leaf inventory differs")
        for folder, name, digest, cap in retained:
            if _sha(folder.read(name, cap=cap)) != digest: _refuse("journal changed during independent replay")
        for folder in folders: folder.check()
        return {"capture_id": capture_id, "report_sha256": expected_report_sha256, "selection_sha256": report["selection_sha256"],
            "selected_prefix_sha256": report["selected_prefix_sha256"], "sec_dispatches": len(report["results"]),
            "completed_request_bound_bodies": completed, "retained_body_bytes": total, "batch_completed": completed == len(rows),
            "scope": report["scope"], "independent_readonly_journal_replay": True, "authority": _authority(observed)}
    finally:
        for folder in reversed(folders): folder.close()


def verify_observed_fresh_v4_capture(capture_id, *, expected_report_sha256):
    """No network/write; expected final report hash is an external custody anchor."""
    from research import insider_buying_sec_recovery_v4_selection as select
    try:
        return _verify_capture(capture_id, expected_report_sha256, root=select._base().LANE_ROOT, observed=True)
    except FreshV4CaptureError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise FreshV4CaptureError("REFUSED: independent fresh capture replay failed") from None


def _private_contact():
    # A pipe does not echo its input; an interactive terminal uses getpass.
    if sys.stdin.isatty(): return getpass.getpass("SEC contact (not echoed): ")
    raw = sys.stdin.readline(257)
    if not raw.endswith("\n") or len(raw) > 255: _refuse("bounded private contact input required")
    return raw[:-1]


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        parser = argparse.ArgumentParser(description="Fresh one-shot v4 first-prefix SEC capture")
        parser.add_argument("--expected-head", required=True)
        parser.add_argument("--capture-id", required=True)
        parser.add_argument("--maximum-requests", type=int, default=64)
        args = parser.parse_args()
        from research.insider_buying_sec_recovery_v4_selection import replay_observed_first_v4_requests
        selection = replay_observed_first_v4_requests(expected_head=args.expected_head, maximum_requests=args.maximum_requests)
        result = run_observed_fresh_v4_capture(selection, args.capture_id,
            expected_head=args.expected_head, contact_email=_private_contact())
        print(_canonical(result).decode("ascii"), end="")
    except Exception:
        sys.stderr.write("REFUSED: fresh v4 capture did not complete; preserve all claims and starts\n")
        raise SystemExit(1) from None
