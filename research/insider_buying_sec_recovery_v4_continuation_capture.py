"""Separately versioned, one-shot capture after genuine combined-v4 replay.

Import-inert. The original first-prefix selector/capture is not changed or
relabelled. One fixed shared claim namespace consumes every reserved accession
permanently, including failures and not-yet-attempted members. No retry/resume,
provider fallback, corpus/PIT/rights/QC/backtest/trading promotion exists here.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time


VERSION = "INSETF-IB1B-COMBINED-V4-CONTINUATION-CAPTURE-v1"
SELF_PATH = "research/insider_buying_sec_recovery_v4_continuation_capture.py"
COMBINED_PATH = "research/insider_buying_sec_recovery_v4_combined.py"
MAX_REQUESTS = 256
MAX_METADATA_BYTES = 1024 * 1024
MAX_PARENT_BYTES = 8 * 1024 * 1024
MAX_BATCH_BODY_BYTES = MAX_REQUESTS * MAX_PARENT_BYTES
MIN_FREE_BYTES = 8 * 1024**3
MIN_COMPLETION_INTERVAL_NS = 500_000_000
LOCK_BYTES = b"INSETF-v4-global-claim-lock\n"
_ID = re.compile(r"[a-z][a-z0-9-]{0,79}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CLAIM = re.compile(r"[0-9a-f]{64}\.json\Z")
_OWN_FILES = (SELF_PATH, COMBINED_PATH,
    "tests/test_insider_buying_sec_recovery_v4_continuation_capture.py",
    "tests/test_insider_buying_sec_recovery_v4_combined.py")


class ContinuationCaptureError(ValueError):
    pass


def _refuse(reason):
    raise ContinuationCaptureError("REFUSED: " + reason)


def _custody_module():
    return importlib.import_module("research.insider_buying_sec_recovery_v4_capture")


def _combined():
    return importlib.import_module("research.insider_buying_sec_recovery_v4_combined")


def _base():
    return importlib.import_module("research.insider_buying_sec_recovery_v4_selection")._base()


def _raw(body):
    return _base()._canonical(body) + b"\n"


def _digest(body):
    return _base()._digest(body)


def _authority(observed):
    return {"bounded_named_source_acquisition_scope": observed,
        "source_authenticated": False, "official_acceptance_verified": False,
        "publication_time_verified": False, "point_in_time_data": False,
        "rights_verified": False, "canonical_evidence": False, "complete_corpus": False,
        "union_promotion_performed": False, "qc_authorized": False,
        "backtest_authorized": False, "execution_authorized": False,
        "outcome_looks": 0, "qc_jobs": 0, "backtests": 0}


def _exact_authority(value, observed):
    expected = _authority(observed)
    return (type(value) is dict and set(value) == set(expected) and value == expected
            and all(type(value[key]) is type(item) for key, item in expected.items()))


def _selection_body(selection, observed):
    combined = _combined()
    family = combined.CombinedV4Selection if observed else combined.InventedCombinedV4Selection
    if type(selection) is not family:
        _refuse("exact separately versioned combined selection required")
    body = selection.to_payload()
    _validate_selection(body, observed=observed)
    if selection.sha256 != _digest(body):
        _refuse("combined selection image recipe differs")
    return body


def _validate_selection(body, *, observed):
    # The combined verifier owns this version's full lineage/authority schema.
    body = _combined().validate_combined_v4_selection_payload(body, observed=observed)
    rows, count = body["requests"], body["maximum_requests"]
    if type(count) is not int or not 1 <= count <= MAX_REQUESTS or type(rows) is not list or len(rows) != count:
        _refuse("bounded continuation cardinality differs")
    if body["selected_prefix_sha256"] != _digest(rows):
        _refuse("exact continuation prefix differs")
    inventory = body["claim_inventory"]
    if (type(inventory) is not list or type(body["claim_inventory_count"]) is not int
            or len(inventory) != body["claim_inventory_count"]
            or body["claim_inventory_sha256"] != _digest(inventory)):
        _refuse("combined claim inventory differs")
    previous = ""
    for item in inventory:
        if (type(item) is not dict or set(item) != {"name", "sha256"}
                or type(item["name"]) is not str or _CLAIM.fullmatch(item["name"]) is None
                or not previous < item["name"] or type(item["sha256"]) is not str
                or _SHA.fullmatch(item["sha256"]) is None):
            _refuse("combined claim inventory shape/order differs")
        previous = item["name"]
    runs = body["known_run_inventory"]
    if (type(runs) is not list or any(type(name) is not str or _ID.fullmatch(name) is None for name in runs)
            or runs != sorted(set(runs))):
        _refuse("combined known run inventory differs")
    return body


class _CommitGuard:
    """Commit blobs once initially/finally; exact live context each boundary."""
    def __init__(self, selection, expected_head):
        self.body = _selection_body(selection, True)
        self.head = expected_head
        base = _base()
        if (self.body["repository_head"] != expected_head
                or Path(__file__).resolve() != base.LANE_ROOT / SELF_PATH):
            _refuse("exact committed continuation lane required")
        self.sources = base._source_snapshot()
        if self.body["current_source_inventory_sha256"] != _digest(
                [{"path": path, "sha256": base._sha(raw)} for path, raw in self.sources]):
            _refuse("combined replay source inventory differs")
        self.check(final=True)

    def check(self, *, final=False):
        base = _base()
        head, status = base._repository_snapshot()
        if head != self.head or status or base._source_snapshot() != self.sources:
            _refuse("lane HEAD/status/source inventory changed")
        if final:
            for path, raw in self.sources:
                if base._git("cat-file", "blob", f"{self.head}:{path}") != raw:
                    _refuse("current source is not exact committed bytes")
            for path in _OWN_FILES:
                if base._git("cat-file", "blob", f"{self.head}:{path}") != (base.LANE_ROOT / path).read_bytes():
                    _refuse("continuation code/tests are not committed")


def _claim_inventory(claims):
    names = sorted(os.listdir(claims.fd))
    if len(names) > 79868 or any(_CLAIM.fullmatch(name) is None for name in names):
        _refuse("unknown/unbounded global claim namespace")
    return [{"name": name, "sha256": _base()._sha(claims.read(name, cap=MAX_METADATA_BYTES))} for name in names]


def _validate_result_disposition(result):
    values = tuple(result[key] for key in ("status", "body_size_bytes", "body_sha256", "response_headers_sha256"))
    status, size, body_sha, headers_sha = values
    unmeasured = all(value is None for value in values)
    measured = (type(status) is int and type(size) is int and type(body_sha) is str and type(headers_sha) is str)
    disposition = result["disposition"]
    if disposition == "ambiguous_transport_failure": valid = unmeasured
    elif disposition == "http-refused-no-retry":
        valid = measured and status != 200 and size == 0 and body_sha == _base()._sha(b"")
    elif disposition == "invalid-response-no-retry": valid = measured and status != 200 and size > 0
    elif disposition == "invalid-response-or-parent-no-retry": valid = unmeasured or measured and status == 200
    else: valid = measured and status == 200 and size > 0
    if not valid: _refuse("result disposition contradicts measured response metadata")


def _capture(selection, capture_id, expected_head, contact_email, *, root, transport,
        observed=False, guard=lambda: None, final_guard=lambda: None, clock=None,
        monotonic_ns=time.monotonic_ns, sleep=time.sleep, free_bytes=None):
    custody, base = _custody_module(), _base()
    from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport, _strict_selected_response
    from research.insider_buying_sec_complete_acquisition import SecHttpResult, SecCompleteAcquisitionError
    from research.insider_buying_sec_all_form4_parent_campaign import CampaignError, _validate_parent_header
    if type(observed) is not bool or type(capture_id) is not str or _ID.fullmatch(capture_id) is None:
        _refuse("continuation capture identity differs")
    if observed and (Path(root) != base.LANE_ROOT or transport is not _selected_sec_transport):
        _refuse("real continuation requires fixed root/transport")
    if not observed and transport is _selected_sec_transport:
        _refuse("invented continuation cannot use SEC transport")
    body = _selection_body(selection, observed)
    if body["repository_head"] != expected_head:
        _refuse("combined selection HEAD differs")
    contact_email = custody._contact(contact_email, observed=observed)
    clock = custody._utc if clock is None else clock
    rows = body["requests"]
    guard()
    folders, lock_fd, locked = [], None, False
    try:
        anchor = custody._Directory(Path(root), private=False); folders.append(anchor)
        path = Path(root).joinpath(*custody.ARTIFACT_PARTS)
        namespace = custody._Directory(path, create=True); folders.append(namespace)
        claims = custody._Directory(path / "claims", create=True); folders.append(claims)
        runs = custody._Directory(path / "runs", create=True); folders.append(runs)
        if not namespace.exists("capture.lock"):
            namespace.publish("capture.lock", LOCK_BYTES)
        lock_fd = os.open("capture.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=namespace.fd)
        lock_stat = os.fstat(lock_fd)
        if (not stat.S_ISREG(lock_stat.st_mode) or stat.S_IMODE(lock_stat.st_mode) != 0o600
                or lock_stat.st_nlink != 1 or lock_stat.st_uid != os.geteuid()):
            _refuse("global claim lock custody differs")
        try: fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: _refuse("another capture owns the global claim lock")
        locked = True
        if namespace.read("capture.lock", cap=64) != LOCK_BYTES:
            _refuse("global claim lock bytes differ")
        if (set(os.listdir(namespace.fd)) != {"claims", "runs", "capture.lock"}
                or _claim_inventory(claims) != body["claim_inventory"]
                or sorted(os.listdir(runs.fd)) != body["known_run_inventory"]):
            _refuse("combined global claim/run snapshot changed")
        if capture_id in body["known_run_inventory"] or runs.exists(capture_id):
            _refuse("existing/ambiguous capture cannot resume")
        names = [custody._claim_name(row) for row in rows]
        if len(set(names)) != len(names) or any(claims.exists(name) for name in names):
            _refuse("selected accession is already permanently claimed")
        info = os.fstatvfs(namespace.fd)
        capacity = free_bytes() if free_bytes is not None else info.f_bavail * info.f_frsize
        if type(capacity) is not int or capacity < MIN_FREE_BYTES + len(rows) * MAX_PARENT_BYTES:
            _refuse("continuation disk/body reserve is insufficient")
        os.mkdir(capture_id, 0o700, dir_fd=runs.fd); os.fsync(runs.fd)
        run = custody._Directory(path / "runs" / capture_id); folders.append(run)
        objects = custody._Directory(run.path / "objects", create=True); folders.append(objects)
        reservation = {"kind": VERSION + "/reservation", "capture_id": capture_id,
            "capture_git_commit": expected_head, "selection_sha256": selection.sha256, "selection": body,
            "contact_present": True, "maximum_sec_dispatches": len(rows), "maximum_attempts_per_request": 1,
            "completion_spacing_ns": MIN_COMPLETION_INTERVAL_NS, "maximum_parent_bytes": MAX_PARENT_BYTES,
            "maximum_batch_body_bytes": len(rows) * MAX_PARENT_BYTES, "authority": _authority(observed)}
        reservation_sha = run.publish("reservation.json", _raw(reservation), cap=MAX_METADATA_BYTES)
        retained = [(claims, item["name"], item["sha256"], MAX_METADATA_BYTES) for item in body["claim_inventory"]]
        retained.append((run, "reservation.json", reservation_sha, MAX_METADATA_BYTES))
        claim_shas = []
        for row, name in zip(rows, names, strict=True):
            claim = {"kind": VERSION + "/request-claim", "capture_id": capture_id,
                "reservation_sha256": reservation_sha, "selection_sha256": selection.sha256,
                "combined_partition_sha256": body["combined_partition_sha256"],
                "prior_claim_inventory_sha256": body["claim_inventory_sha256"], "request": row}
            sha = claims.publish(name, _raw(claim), cap=MAX_METADATA_BYTES)
            retained.append((claims, name, sha, MAX_METADATA_BYTES)); claim_shas.append(sha)
        expected_claims = set(names) | {item["name"] for item in body["claim_inventory"]}
        expected_runs = sorted([*body["known_run_inventory"], capture_id])
        allowed_run, allowed_objects = {"reservation.json", "objects"}, set()
        def check_custody():
            for folder in folders: folder.check()
            named = os.stat("capture.lock", dir_fd=namespace.fd, follow_symlinks=False)
            current = os.fstat(lock_fd)
            if (custody._file_version(named) != custody._file_version(current)
                    or custody._file_version(current) != custody._file_version(lock_stat)):
                _refuse("global claim lock changed")
            if (set(os.listdir(claims.fd)) != expected_claims or sorted(os.listdir(runs.fd)) != expected_runs
                    or set(os.listdir(run.fd)) != allowed_run or set(os.listdir(objects.fd)) != allowed_objects
                    or set(os.listdir(namespace.fd)) != {"claims", "runs", "capture.lock"}):
                _refuse("journal/global namespace inventory changed")
            for folder, name, sha, cap in retained:
                if base._sha(folder.read(name, cap=cap)) != sha:
                    _refuse("durable continuation/claim bytes changed")
        headers = {"User-Agent": f"InsiderBuyingResearch-v4-continuation/1.0 ({contact_email})",
            "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close"}
        results, completed, total_bytes, last_finish = [], 0, 0, None
        for ordinal, row in enumerate(rows):
            check_custody(); guard()
            if last_finish is not None:
                now = monotonic_ns()
                if type(now) is not int or now < last_finish: _refuse("monotonic completion clock differs")
                if now - last_finish < MIN_COMPLETION_INTERVAL_NS:
                    sleep((MIN_COMPLETION_INTERVAL_NS - now + last_finish) / 1_000_000_000)
            started = monotonic_ns()
            if (type(started) is not int or started < 0
                    or last_finish is not None and started - last_finish < MIN_COMPLETION_INTERVAL_NS):
                _refuse("completion spacing was not observed")
            start = {"kind": VERSION + "/attempt-start", "ordinal": ordinal, "attempt": 1,
                "global_index": row["global_index"], "request_sha256": row["request_sha256"],
                "reservation_sha256": reservation_sha, "claim_sha256": claim_shas[ordinal],
                "started_monotonic_ns": started, "started_utc": custody._stamp(clock)}
            start_name = f"request-{ordinal:03d}-start.json"
            start_sha = run.publish(start_name, _raw(start), cap=MAX_METADATA_BYTES)
            retained.append((run, start_name, start_sha, MAX_METADATA_BYTES)); allowed_run.add(start_name)
            check_custody(); guard()
            outcome, status, size, body_sha, headers_sha = "ambiguous_transport_failure", None, None, None, None
            try: response = transport(row["request"]["url"], headers, MAX_PARENT_BYTES)
            except Exception: pass  # The consumed fsynced start is never retried.
            else:
                accepted = None
                try:
                    if (type(response) is not SecHttpResult or type(response.status) is not int or not 100 <= response.status <= 599
                            or type(response.headers) is not tuple or len(response.headers) > 64
                            or any(type(pair) is not tuple or len(pair) != 2 or any(type(v) is not str for v in pair) for pair in response.headers)
                            or len(_raw(response.headers)) > 16 * 1024
                            or type(response.body) is not bytes or len(response.body) > MAX_PARENT_BYTES):
                        _refuse("response metadata differs")
                    status, headers_sha = response.status, base._sha(_raw(response.headers))
                    size, body_sha = len(response.body), base._sha(response.body)
                    if status != 200:
                        outcome = "http-refused-no-retry" if not response.body else "invalid-response-no-retry"
                    else:
                        raw = _strict_selected_response(response, max_bytes=MAX_PARENT_BYTES)
                        custody._screen_contact_echo(raw.decode("utf-8", "replace"), contact_email)
                        _validate_parent_header(raw, row["request"])
                        if total_bytes + len(raw) > len(rows) * MAX_PARENT_BYTES: _refuse("batch body cap exceeded")
                        accepted = raw
                except (ContinuationCaptureError, custody.FreshV4CaptureError, SecCompleteAcquisitionError,
                        CampaignError, UnicodeError, ValueError, TypeError, KeyError, RecursionError):
                    outcome = "invalid-response-or-parent-no-retry"
                if accepted is not None:
                    sha = objects.publish(body_sha + ".bin", accepted, cap=MAX_PARENT_BYTES)
                    retained.append((objects, body_sha + ".bin", sha, MAX_PARENT_BYTES)); allowed_objects.add(body_sha + ".bin")
                    completed += 1; total_bytes += len(accepted); outcome = "request-bound-parent-retained"
            last_finish = monotonic_ns()
            if type(last_finish) is not int or last_finish < started: _refuse("completion clock differs")
            result = {"kind": VERSION + "/attempt-result", "ordinal": ordinal, "attempt": 1,
                "global_index": row["global_index"], "request_sha256": row["request_sha256"],
                "start_sha256": start_sha, "disposition": outcome, "status": status,
                "body_size_bytes": size, "body_sha256": body_sha, "response_headers_sha256": headers_sha,
                "body_retained": outcome == "request-bound-parent-retained",
                "finished_monotonic_ns": last_finish, "finished_utc": custody._stamp(clock)}
            result_name = f"request-{ordinal:03d}-result.json"
            result_sha = run.publish(result_name, _raw(result), cap=MAX_METADATA_BYTES)
            retained.append((run, result_name, result_sha, MAX_METADATA_BYTES)); allowed_run.add(result_name)
            results.append({"result_name": result_name, "result_sha256": result_sha})
            check_custody(); guard()
            if outcome != "request-bound-parent-retained": break
        report = {"kind": VERSION + "/report", "scope": "observed_combined_continuation" if observed else "invented_test_only",
            "capture_id": capture_id, "capture_git_commit": expected_head, "reservation_sha256": reservation_sha,
            "selection_sha256": selection.sha256, "selected_prefix_sha256": body["selected_prefix_sha256"],
            "combined_partition_sha256": body["combined_partition_sha256"], "prior_claim_inventory_sha256": body["claim_inventory_sha256"],
            "reserved_requests": len(rows), "sec_dispatches": len(results), "reserved_not_attempted": len(rows) - len(results),
            "completed_request_bound_bodies": completed, "retained_body_bytes": total_bytes,
            "batch_completed": completed == len(rows), "results": results,
            "stopped_v3_not_written_by_capture": True, "authority": _authority(observed)}
        report_sha = run.publish("complete.json", _raw(report), cap=MAX_METADATA_BYTES)
        retained.append((run, "complete.json", report_sha, MAX_METADATA_BYTES)); allowed_run.add("complete.json")
        check_custody(); guard(); final_guard()
        return {key: report[key] for key in ("capture_id", "scope", "selection_sha256", "selected_prefix_sha256",
            "combined_partition_sha256", "sec_dispatches", "reserved_requests", "reserved_not_attempted",
            "completed_request_bound_bodies", "retained_body_bytes", "batch_completed", "authority")} | {"report_sha256": report_sha}
    finally:
        if lock_fd is not None:
            try:
                if locked: fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally: os.close(lock_fd)
        for folder in reversed(folders): folder.close()


def run_observed_continuation_capture(selection, capture_id, *, expected_head, contact_email):
    """No root/transport/guard override at the genuine public boundary."""
    from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport
    _selection_body(selection, True)
    try:
        context = _CommitGuard(selection, expected_head)
        return _capture(selection, capture_id, expected_head, contact_email, root=_base().LANE_ROOT,
            transport=_selected_sec_transport, observed=True, guard=context.check,
            final_guard=lambda: context.check(final=True))
    except ContinuationCaptureError: raise
    except Exception:
        raise ContinuationCaptureError("REFUSED: continuation failed; preserve all permanent claims/starts") from None


def _run_invented_capture(selection, capture_id, *, root, transport, contact_email="invented@unit.test", **kwargs):
    body = _selection_body(selection, False)
    return _capture(selection, capture_id, body["repository_head"], contact_email, root=Path(root),
        transport=transport, observed=False, free_bytes=kwargs.pop("free_bytes", lambda: 1 << 50), **kwargs)


def _verify_capture(capture_id, report_sha, *, root, observed, project_retained=False):
    """Exact externally anchored journal replay, never a dispatch selection."""
    custody, base = _custody_module(), _base()
    from research.insider_buying_sec_all_form4_parent_campaign import _validate_parent_header
    if (type(capture_id) is not str or _ID.fullmatch(capture_id) is None
            or type(report_sha) is not str or _SHA.fullmatch(report_sha) is None or type(observed) is not bool
            or type(project_retained) is not bool):
        _refuse("read-only continuation anchor differs")
    folders = []
    try:
        root = Path(root)
        anchor = custody._Directory(root, private=False); folders.append(anchor)
        path = root.joinpath(*custody.ARTIFACT_PARTS)
        namespace = custody._Directory(path); folders.append(namespace)
        claims = custody._Directory(path / "claims"); folders.append(claims)
        runs = custody._Directory(path / "runs"); folders.append(runs)
        run = custody._Directory(path / "runs" / capture_id); folders.append(run)
        objects = custody._Directory(run.path / "objects"); folders.append(objects)
        lock_version = custody._file_version(os.stat("capture.lock", dir_fd=namespace.fd, follow_symlinks=False))
        if namespace.read("capture.lock", cap=64) != LOCK_BYTES:
            _refuse("global claim lock bytes differ")
        report_raw = run.read("complete.json", cap=MAX_METADATA_BYTES)
        if base._sha(report_raw) != report_sha: _refuse("continuation report hash differs")
        report = custody._decode(report_raw)
        report_keys = {"kind", "scope", "capture_id", "capture_git_commit", "reservation_sha256", "selection_sha256",
            "selected_prefix_sha256", "combined_partition_sha256", "prior_claim_inventory_sha256", "reserved_requests",
            "sec_dispatches", "reserved_not_attempted", "completed_request_bound_bodies", "retained_body_bytes",
            "batch_completed", "results", "stopped_v3_not_written_by_capture", "authority"}
        if (set(report) != report_keys or report["kind"] != VERSION + "/report" or report["capture_id"] != capture_id
                or report["scope"] != ("observed_combined_continuation" if observed else "invented_test_only")
                or report["stopped_v3_not_written_by_capture"] is not True or not _exact_authority(report["authority"], observed)):
            _refuse("continuation report scope/authority differs")
        reservation_raw = run.read("reservation.json", cap=MAX_METADATA_BYTES)
        if base._sha(reservation_raw) != report["reservation_sha256"]: _refuse("reservation hash differs")
        reservation = custody._decode(reservation_raw)
        reservation_keys = {"kind", "capture_id", "capture_git_commit", "selection_sha256", "selection", "contact_present",
            "maximum_sec_dispatches", "maximum_attempts_per_request", "completion_spacing_ns", "maximum_parent_bytes",
            "maximum_batch_body_bytes", "authority"}
        if (set(reservation) != reservation_keys or reservation["kind"] != VERSION + "/reservation"
                or reservation["capture_id"] != capture_id or reservation["contact_present"] is not True
                or not _exact_authority(reservation["authority"], observed)):
            _refuse("reservation scope/authority differs")
        body = _validate_selection(reservation["selection"], observed=observed)
        rows = body["requests"]
        if (reservation["capture_git_commit"] != body["repository_head"]
                or report["capture_git_commit"] != body["repository_head"]
                or reservation["selection_sha256"] != _digest(body) or report["selection_sha256"] != _digest(body)
                or report["selected_prefix_sha256"] != body["selected_prefix_sha256"]
                or report["combined_partition_sha256"] != body["combined_partition_sha256"]
                or report["prior_claim_inventory_sha256"] != body["claim_inventory_sha256"]
                or any(type(reservation[key]) is not int or reservation[key] != value for key, value in (
                    ("maximum_sec_dispatches", len(rows)), ("maximum_attempts_per_request", 1),
                    ("completion_spacing_ns", MIN_COMPLETION_INTERVAL_NS), ("maximum_parent_bytes", MAX_PARENT_BYTES),
                    ("maximum_batch_body_bytes", len(rows) * MAX_PARENT_BYTES)))
                or type(report["reserved_requests"]) is not int or report["reserved_requests"] != len(rows)
                or type(report["sec_dispatches"]) is not int or not 1 <= report["sec_dispatches"] <= len(rows)
                or type(report["results"]) is not list or len(report["results"]) != report["sec_dispatches"]):
            _refuse("selection lineage/denominator/profile differs")
        retained = [(run, "complete.json", report_sha, MAX_METADATA_BYTES),
                    (run, "reservation.json", report["reservation_sha256"], MAX_METADATA_BYTES),
                    (namespace, "capture.lock", base._sha(LOCK_BYTES), 64)]
        own_names, claim_shas = set(), []
        for row in rows:
            name = custody._claim_name(row); own_names.add(name)
            raw = claims.read(name, cap=MAX_METADATA_BYTES); claim = custody._decode(raw)
            expected = {"kind": VERSION + "/request-claim", "capture_id": capture_id,
                "reservation_sha256": report["reservation_sha256"], "selection_sha256": report["selection_sha256"],
                "combined_partition_sha256": body["combined_partition_sha256"],
                "prior_claim_inventory_sha256": body["claim_inventory_sha256"], "request": row}
            if claim != expected or _raw(expected) != raw: _refuse("permanent continuation claim differs")
            sha = base._sha(raw); claim_shas.append(sha); retained.append((claims, name, sha, MAX_METADATA_BYTES))
        for item in body["claim_inventory"]:
            if item["name"] in own_names: _refuse("continuation overlaps a prior claim")
            retained.append((claims, item["name"], item["sha256"], MAX_METADATA_BYTES))
        expected_claims = own_names | {item["name"] for item in body["claim_inventory"]}
        expected_runs = sorted([*body["known_run_inventory"], capture_id])
        allowed_run, allowed_objects = {"objects", "reservation.json", "complete.json"}, set()
        completed, total, previous = 0, 0, None
        projection_rows, projected, quarantined = [], 0, 0
        result_keys = {"kind", "ordinal", "attempt", "global_index", "request_sha256", "start_sha256", "disposition",
            "status", "body_size_bytes", "body_sha256", "response_headers_sha256", "body_retained", "finished_monotonic_ns", "finished_utc"}
        start_keys = {"kind", "ordinal", "attempt", "global_index", "request_sha256", "reservation_sha256", "claim_sha256",
            "started_monotonic_ns", "started_utc"}
        dispositions = {"request-bound-parent-retained", "ambiguous_transport_failure", "http-refused-no-retry",
                        "invalid-response-no-retry", "invalid-response-or-parent-no-retry"}
        for ordinal, descriptor in enumerate(report["results"]):
            row = rows[ordinal]
            start_name, result_name = f"request-{ordinal:03d}-start.json", f"request-{ordinal:03d}-result.json"
            if (type(descriptor) is not dict or set(descriptor) != {"result_name", "result_sha256"}
                    or descriptor["result_name"] != result_name): _refuse("ordered result descriptor differs")
            start_raw, result_raw = run.read(start_name, cap=MAX_METADATA_BYTES), run.read(result_name, cap=MAX_METADATA_BYTES)
            start, result = custody._decode(start_raw), custody._decode(result_raw)
            if (base._sha(result_raw) != descriptor["result_sha256"] or set(start) != start_keys or set(result) != result_keys
                    or start["kind"] != VERSION + "/attempt-start" or result["kind"] != VERSION + "/attempt-result"
                    or result["start_sha256"] != base._sha(start_raw) or start["reservation_sha256"] != report["reservation_sha256"]
                    or start["claim_sha256"] != claim_shas[ordinal]
                    or any(type(container[key]) is not int or container[key] != value for container in (start, result)
                        for key, value in (("ordinal", ordinal), ("attempt", 1), ("global_index", row["global_index"])))
                    or any(container["request_sha256"] != row["request_sha256"] for container in (start, result))
                    or type(start["started_monotonic_ns"]) is not int or start["started_monotonic_ns"] < 0
                    or type(result["finished_monotonic_ns"]) is not int or result["finished_monotonic_ns"] < start["started_monotonic_ns"]
                    or previous is not None and start["started_monotonic_ns"] - previous < MIN_COMPLETION_INTERVAL_NS
                    or type(result["disposition"]) is not str or result["disposition"] not in dispositions
                    or type(result["body_retained"]) is not bool
                    or result["body_retained"] is not (result["disposition"] == "request-bound-parent-retained")
                    or result["status"] is not None and (type(result["status"]) is not int or not 100 <= result["status"] <= 599)
                    or result["body_size_bytes"] is not None and (type(result["body_size_bytes"]) is not int or not 0 <= result["body_size_bytes"] <= MAX_PARENT_BYTES)
                    or any(result[key] is not None and (type(result[key]) is not str or _SHA.fullmatch(result[key]) is None)
                        for key in ("body_sha256", "response_headers_sha256"))):
                _refuse("single-attempt/request/spacing/result profile differs")
            custody._stamp(lambda: start["started_utc"]); custody._stamp(lambda: result["finished_utc"])
            _validate_result_disposition(result)
            previous = result["finished_monotonic_ns"]
            if result["body_retained"]:
                if (result["status"] != 200 or type(result["body_size_bytes"]) is not int or result["body_size_bytes"] <= 0
                        or type(result["body_sha256"]) is not str or type(result["response_headers_sha256"]) is not str):
                    _refuse("retained parent result differs")
                name = result["body_sha256"] + ".bin"
                raw = objects.read(name, cap=MAX_PARENT_BYTES)
                if len(raw) != result["body_size_bytes"] or base._sha(raw) != result["body_sha256"]:
                    _refuse("retained parent hash/size differs")
                _validate_parent_header(raw, row["request"])
                if project_retained:
                    from research.insider_buying.sec_complete_submission import (
                        SecCompleteSubmissionError, SecCompleteSubmissionTarget, project_sec_complete_submission)
                    request = row["request"]
                    target = SecCompleteSubmissionTarget(period=request["period"], accession_number=request["accession_number"],
                        form_type=request["form_type"], filing_date=request["filing_date"],
                        issuer_cik=request["issuer_cik"].zfill(10), quarterly_index_sha256=request["master_source_sha256"],
                        complete_submission_url=request["url"])
                    projection_row = {"global_index": row["global_index"], "request_sha256": row["request_sha256"],
                                      "raw_parent_sha256": result["body_sha256"]}
                    try:
                        projection = project_sec_complete_submission(target, raw)
                        payload = projection.to_payload()
                        if payload["raw_parent"]["sha256"] != result["body_sha256"]:
                            _refuse("projection parent binding differs")
                        projection_row.update({"disposition": "complete_parent_projected_noncanonical",
                            "projection_sha256": projection.sha256,
                            "header_sha256": payload["children"]["header"]["sha256"],
                            "primary_xml_sha256": payload["children"]["primary_xml"]["sha256"],
                            "accepted_at_raw": payload["source_fields"]["accepted_at_raw"],
                            "header_owner_cik_count": len(payload["source_fields"]["header_owner_ciks"])})
                        projected += 1
                        del projection, payload
                    except SecCompleteSubmissionError:
                        projection_row.update({"disposition": "complete_parent_grammar_quarantine",
                            "quarantine_code": "unsupported_complete_submission_grammar"})
                        quarantined += 1
                    projection_rows.append(projection_row)
                    del target, projection_row
                completed += 1; total += len(raw); allowed_objects.add(name)
                retained.append((objects, name, result["body_sha256"], MAX_PARENT_BYTES))
                del raw
            elif ordinal != len(report["results"]) - 1:
                _refuse("capture continued after failure or ambiguity")
            allowed_run.update((start_name, result_name))
            retained.extend(((run, start_name, base._sha(start_raw), MAX_METADATA_BYTES),
                             (run, result_name, descriptor["result_sha256"], MAX_METADATA_BYTES)))
        if (any(type(report[key]) is not int or report[key] != value for key, value in (
                ("reserved_not_attempted", len(rows) - len(report["results"])),
                ("completed_request_bound_bodies", completed), ("retained_body_bytes", total)))
                or report["batch_completed"] is not (completed == len(rows))):
            _refuse("continuation final counts differ")
        def namespace_check():
            for folder in folders: folder.check()
            if custody._file_version(os.stat("capture.lock", dir_fd=namespace.fd, follow_symlinks=False)) != lock_version:
                _refuse("global claim lock identity changed")
            if (set(os.listdir(namespace.fd)) != {"claims", "runs", "capture.lock"}
                    or set(os.listdir(claims.fd)) != expected_claims or sorted(os.listdir(runs.fd)) != expected_runs
                    or set(os.listdir(run.fd)) != allowed_run or set(os.listdir(objects.fd)) != allowed_objects):
                _refuse("complete global/journal leaf inventory differs")
        namespace_check()
        for folder, name, sha, cap in retained:
            if base._sha(folder.read(name, cap=cap)) != sha: _refuse("journal/claim changed during independent replay")
        namespace_check()
        return {key: report[key] for key in ("capture_id", "scope", "selection_sha256", "selected_prefix_sha256",
            "combined_partition_sha256", "sec_dispatches", "reserved_requests", "reserved_not_attempted",
            "completed_request_bound_bodies", "retained_body_bytes", "batch_completed", "authority")} | {
                "report_sha256": report_sha, "independent_readonly_journal_replay": True,
                "complete_parent_projection_evaluated": project_retained,
                "projection_counts": {"header_bound_retained": completed, "complete_parent_projected": projected,
                    "complete_parent_grammar_quarantined": quarantined} if project_retained else None,
                "projection_rows": projection_rows if project_retained else None,
                "projection_rows_sha256": _digest(projection_rows) if project_retained else None}
    finally:
        for folder in reversed(folders): folder.close()


def verify_observed_continuation_capture(capture_id, *, expected_report_sha256, project_retained=False):
    try:
        return _verify_capture(capture_id, expected_report_sha256, root=_base().LANE_ROOT, observed=True,
                               project_retained=project_retained)
    except ContinuationCaptureError: raise
    except Exception:
        raise ContinuationCaptureError("REFUSED: independent continuation replay failed") from None


def selection_summary(selection):
    body = _selection_body(selection, True)
    return {"kind": VERSION + "/selection-summary", "selection_sha256": selection.sha256,
        "repository_head": body["repository_head"], "current_source_inventory_sha256": body["current_source_inventory_sha256"],
        "combined_partition_sha256": body["combined_partition_sha256"], "remaining_inventory_sha256": body["remaining_inventory_sha256"],
        "claim_inventory_sha256": body["claim_inventory_sha256"], "claim_inventory_count": body["claim_inventory_count"],
        "selected_prefix_sha256": body["selected_prefix_sha256"], "selected_count": len(body["requests"]),
        "first_global_index": body["requests"][0]["global_index"], "last_global_index": body["requests"][-1]["global_index"],
        "combined_class_counts": body["combined_class_counts"],
        "total_parents": body["total_parents"], "remaining_unattempted_count": body["remaining_unattempted_count"],
        "combined_request_bound_custody_count": body["combined_request_bound_custody_count"], "sec_dispatches": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description="One-shot combined-v4 next-prefix capture")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--maximum-requests", type=int, default=64)
    args = parser.parse_args(argv)
    selected = _combined().run_isolated_combined_v4(expected_head=args.expected_head, maximum_requests=args.maximum_requests)
    context = _CommitGuard(selected, args.expected_head)
    sys.stdout.buffer.write(_raw(selection_summary(selected))); sys.stdout.buffer.flush()
    contact = _custody_module()._private_contact()
    from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport
    result = _capture(selected, args.capture_id, args.expected_head, contact,
        root=_base().LANE_ROOT, transport=_selected_sec_transport, observed=True,
        guard=context.check, final_guard=lambda: context.check(final=True))
    sys.stdout.buffer.write(_raw(result)); sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try: raise SystemExit(main())
    except Exception:
        sys.stderr.write("REFUSED: combined continuation did not complete; preserve claims and starts\n")
        raise SystemExit(1) from None
