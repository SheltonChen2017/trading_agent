"""Exact six-cell retrospective QC lifecycle; no operation runs on import.

Preparation is offline. Each public remote action consumes a durable local
intent before dispatch; lost responses are ambiguous, never invitations to
retry. Selected source pins and private held/named files are scoped integrity
checks, not a same-user sandbox or exactly-once network protocol.
"""
from __future__ import annotations

import dataclasses
import hashlib
import http.client
import json
import os
import re
import stat
import time
import weakref
from contextlib import contextmanager
from pathlib import Path

from research.quantconnect import API_BASE, QuantConnectClient, build_auth_headers
from . import accepted_risk_october_order_package as october
from . import accepted_risk_preliminary_package as compact
from . import formal_qc_transport as transport
from . import newrule_comparison_projection as projection
from . import newrule_comparison_qc_runtime as runtime
from . import six_universe_coverage_submission as coverage

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
CONTROL = ROOT / "artifacts/analyst_revisions_v2/newrule_comparison_qc/R298-R303-20261013"
SCHEMA = "arv2-newrule-six-cell-submission-v1"
PACKAGE_SHA256 = "411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad"
LINEAGE_SHA256 = "e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9"
ACTIVATION_KEY = "arv2/preliminary-rating/27645603c1a6e0fc9fa81655/transport-manifest.json"
ACTIVATION_SHA256 = "70f64450a44bedfa8ea371ac74a00e2134045fb79b433b93f0114be652bc6147"
ACTIVATION_BYTES = 4631
UPLOAD_BYTES = 2776584
REFERENCE_PROJECT = 37165262
CELLS = tuple((f"R{298 + index}", size, arm)
              for index, (size, arm) in enumerate((
                  (6, 0), (6, 100), (6, 200), (8, 0), (8, 100), (8, 200))))
MAX_CONTROL_BYTES = 512 * 1024
MAX_CONTROL_FILES = 18000
COMPILE_INTERVAL, COMPILE_POLLS = 10, 60
STATUS_INTERVAL, STATUS_POLLS = 60, 240
HOST_SOURCE_NAMES = (
    "research/quantconnect.py",
    "research/analyst_revisions_v2_qc/formal_qc_transport.py",
    "research/analyst_revisions_v2_qc/six_universe_coverage_submission.py",
    "research/analyst_revisions_v2_qc/accepted_risk_preliminary_package.py",
    "research/analyst_revisions_v2_qc/accepted_risk_october_order_package.py",
    "research/analyst_revisions_v2_qc/newrule_comparison_projection.py",
    "research/analyst_revisions_v2_qc/newrule_comparison_qc_runtime.py",
    "research/analyst_revisions_v2_qc/newrule_comparison_submission.py",
)
PROFILE = {"schema": SCHEMA, "candidates": [list(row) for row in CELLS],
    "package_sha256": PACKAGE_SHA256, "lineage_sha256": LINEAGE_SHA256,
    "attempt_limit": 3, "compile_poll_interval_seconds": COMPILE_INTERVAL,
    "compile_poll_limit": COMPILE_POLLS, "status_poll_interval_seconds": STATUS_INTERVAL,
    "status_poll_limit": STATUS_POLLS, "request_timeout_seconds": 30,
    "shared_look_per_attempt": 1, "development_look_per_attempt": 1,
    "infrastructure_look_per_attempt": 0, "auto_retry": False,
    "terminal_success": "Completed.", "aggregate_reads_per_attempt": 1,
    "paper_or_live_ready": False, "formal_forward_ready": False}


class NewruleSubmissionError(ValueError):
    """Finite lifecycle refusal; never contains provider payloads or secrets."""


FINITE_REFUSAL_CODES = frozenset("""
aggregate_bound already_terminal another_attempt_active_or_ambiguous attempt_claim attempt_spent
backtest_census backtest_missing backtest_status bounded_client candidate_attempt canonical_control
capacity_nodes capacity_shape capacity_wait cloud_id compile_binding compile_not_ready compile_project
compile_status compile_terminal control_bound control_changed control_inventory control_json control_name
control_readback control_scope control_write created_backtest created_project_count directory_replaced
duplicate_cloud_file duplicate_json_key endpoint exact_october_input family_already_prepared family_bound
family_changed file_binding file_inventory first_attempt fresh_project_files fresh_upload_inventory
family_geometry
genuine_family_required host_source_file host_source_inventory host_source_pin inputs_not_uploaded
json_constant launch_binding launch_name multipart_collision multiple_cell_results not_completed
object_request object_request_ambiguous object_response organization_binding organization_project
organization_shape plan_types poll_budget positive_integer prepared_family prepared_projection
prior_not_failed prior_poll_ambiguous prior_run_census prior_run_changed prior_run_missing private_control
private_directory private_owned_project profile_canonical project_count project_shape projection_input
projection_types request_ambiguous response_refused result_changed result_identity result_receipt
result_statistics result_validator_unavailable retry_requires_failed_prior saved_project sha256
unsafe_http_environment upload_changed upload_inventory upload_payload upload_postcheck uploaded_metadata
uploaded_source_mismatch wait_before_poll
""".split())


def finite_failure(error):
    if type(error) is NewruleSubmissionError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and len(args[0]) <= 64 and args[0] in FINITE_REFUSAL_CODES:
            return args[0]
    return "operation_refused"


# Static public source literals only. This finite diagnostic inventory is not
# an authenticated cause, not complete exception coverage, and never a log.
FINITE_RUNTIME_CODES = frozenset("""
active_membership_collision aggregate_account_geometry aggregate_elapsed_days aggregate_fee
aggregate_positive_nav arm backtest_only between_decision_execution_drift book book_reason
callback_clock_reversal clock_bar_binding clock_type close_clock close_pending_orders cohort
common_source_universes configured_fee_mismatch cross_book_economic_facts_conflict
cross_book_identity_collision decimal decision_clock decision_once digest duplicate_callback_sid
duplicate_economic_id duplicate_order_event duplicate_qc_sid duplicate_split_occurrence duplicate_ticket
engine_order_binding execution_clock execution_once execution_price_not_current_minute
figi_identity_collision fill_cash_or_holdings_reconciliation fill_clock fill_quantity_or_fee
first_decision_cash_only gross_conservation held_split_units_not_observed identity_text
incomplete_terminal_geometry initial_holdings intent_order_id loaded_package_binding
loaded_profile_axis market_ticket_not_complete member missing_clock_bar
missing_genuine_preopen_frontier missing_prior_close_sizing_nav mixed_source_end_times
negative_reported_weight nonfill_quantity nonterminal_or_partial_order order_bound_or_live
order_event_ids order_intent_binding order_quantity order_status own_etf_collision
own_etf_identity_collision pending_orders preopen_frontier_order prior_close_sizing_nav profile_axis
profile_binding runtime_book_binding same_end_time_revision session_axis session_canonical
session_text short_holdings source_census source_end_after_callback source_pins source_rows
split_callback_history_conflict split_callback_kind split_event_clock split_history_batch_bound
split_history_batch_clock split_history_call_bound split_history_census split_history_duplicate
split_history_event_clock split_history_identity split_history_kind split_history_row_bound
split_history_sid_collision split_history_total_bound split_not_predecision split_price_units
split_sid starting_cash statistic_bound status_numbers stock_cap stock_own_etf_collision
target_binding terminal_clock terminal_order_or_history_census tilt_conservation total_source_rows
unexecuted_decision universe unmapped_score weekly_geometry
""".split())


def _failure_evidence(response, kind):
    codes, categories = set(), set()
    values = [response.get("error"), response.get("errorMessage")]
    extra = response.get("errors")
    if type(extra) is list and len(extra) <= 8:
        values.extend(extra)
    for value in values:
        if type(value) is not str or not 0 < len(value) <= 512:
            continue
        for prefix in ("", "NewruleError: ", "Runtime Error: NewruleError: "):
            candidate = value[len(prefix):] if value.startswith(prefix) else None
            if type(candidate) is str and len(candidate) <= 64 and candidate in FINITE_RUNTIME_CODES:
                codes.add(candidate)
        for category in ("SyntaxError", "IndentationError", "ImportError", "ModuleNotFoundError", "NameError", "TypeError"):
            if value.startswith(category + ": "):
                categories.add(category)
    code = next(iter(codes)) if len(codes) == 1 else None
    return {"terminal_category": kind, "known_runtime_code": code,
        "known_runtime_code_sha256": _sha(code.encode("ascii")) if code else None,
        "python_error_category": next(iter(categories)) if len(categories) == 1 else None,
        "raw_error_retained": False, "cause_authenticated": False}


def _require(value, code):
    if not value:
        raise NewruleSubmissionError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _same(left, right):
    """Canonical equality preserves JSON boolean/integer/float distinctions."""
    return _canonical(left) == _canonical(right)


PROFILE_SHA256 = _sha(_canonical(PROFILE))


def _digest(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "sha256")
    return value


def _number(value):
    _require(type(value) is int and value > 0, "positive_integer")
    return value


def _id(value):
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value), "cloud_id")
    return value


def _parse(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: _require(False, "json_constant"))
        _require(type(value) is dict and _canonical(value) == raw, "canonical_control")
        return value
    except (UnicodeError, ValueError, TypeError):
        raise NewruleSubmissionError("control_json") from None


def _metadata(info):
    return tuple(getattr(info, key, None) for key in (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
        "st_size", "st_mtime_ns", "st_ctime_ns", "st_flags"))


class _Directory:
    def __init__(self, create=False):
        _require(Path.cwd() == ROOT and CONTROL.is_relative_to(ROOT / "artifacts")
                 and ".." not in CONTROL.parts, "control_scope")
        self.fd, self.chain = None, []
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if create and here.is_relative_to(ROOT / "artifacts"):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        _require(here != CONTROL, "family_already_prepared")
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                info = os.fstat(fd)
                self.chain.append((info.st_dev, info.st_ino))
            info = os.fstat(fd)
            _require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, "private_directory")
            self.fd = fd
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def verify(self):
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part, identity in zip(CONTROL.parts[1:], self.chain):
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                info = os.fstat(fd)
                _require((info.st_dev, info.st_ino) == identity, "directory_replaced")
            info, held = os.fstat(fd), os.fstat(self.fd)
            _require((held.st_dev, held.st_ino) == self.chain[-1]
                     and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                     "private_directory")
        finally:
            os.close(fd)

    def names(self):
        self.verify()
        names = tuple(os.listdir(self.fd))
        _require(len(names) <= MAX_CONTROL_FILES and all(
            re.fullmatch(r"[A-Za-z0-9_.-]+\.json", name) for name in names), "control_inventory")
        return names

    def read(self, name):
        self.verify()
        _require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]+\.json", name), "control_name")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                     and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
                     and 0 < before.st_size <= MAX_CONTROL_BYTES, "private_control")
            raw = bytearray()
            while len(raw) <= MAX_CONTROL_BYTES:
                chunk = os.read(fd, min(65536, MAX_CONTROL_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            _require(len(raw) == before.st_size and _metadata(before) == _metadata(os.fstat(fd))
                     == _metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False)), "control_changed")
        finally:
            os.close(fd)
        self.verify()
        return _parse(bytes(raw))

    def write(self, name, value):
        self.verify()
        _require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]+\.json", name), "control_name")
        raw = _canonical(value)
        _require(type(value) is dict and 0 < len(raw) <= MAX_CONTROL_BYTES, "control_bound")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                _require(count > 0, "control_write")
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        _require(_same(self.read(name), value), "control_readback")


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FamilyPlan:
    family_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    _input: object = dataclasses.field(repr=False)
    _projections: tuple = dataclasses.field(repr=False)
    _host_pins: tuple = dataclasses.field(repr=False)


_PLANS = {}


def _fingerprint(value):
    _require(type(value.record_bytes) is bytes and type(value._projections) is tuple
             and type(value._host_pins) is tuple, "plan_types")
    for item in value._projections:
        _require(type(item) is projection.Projection and type(item.record_bytes) is bytes
                 and type(item.profile_bytes) is bytes and type(item.source_files) is tuple
                 and all(type(entry) is projection.SourceFile and type(entry.project_path) is str
                         and type(entry.source_bytes) is bytes for entry in item.source_files), "projection_types")
    return (value.family_sha256, value.record_bytes, id(value._input),
            value._host_pins, tuple((item.record_bytes, item.profile_bytes,
                tuple((f.project_path, f.source_bytes) for f in item.source_files)) for item in value._projections))


def _sources(pins):
    _require(type(pins) is dict and set(pins) == set(HOST_SOURCE_NAMES), "host_source_inventory")
    for relative, digest in pins.items():
        _digest(digest)
        path = ROOT / relative
        _require(path.is_file() and not path.is_symlink(), "host_source_file")
        raw = path.read_bytes()
        _require(len(raw) <= 2 * 1024 * 1024 and _sha(raw) == digest, "host_source_pin")


def _input(value):
    october.require_october_order_input_package(value)
    package = compact.require_accepted_risk_preliminary_package(value.package)
    last = package.upload_objects[-1]
    _require(package.package_sha256 == PACKAGE_SHA256 and value.lineage_sha256 == LINEAGE_SHA256
             and (last.object_store_key, last.content_sha256, last.byte_count, last.activation_manifest)
             == (ACTIVATION_KEY, ACTIVATION_SHA256, ACTIVATION_BYTES, True)
             and package.total_upload_byte_count == UPLOAD_BYTES, "exact_october_input")
    return package


def _inventory(package):
    rows = []
    for descriptor, payload in compact.iter_accepted_risk_preliminary_upload_objects(package):
        transport._safe_key(descriptor.object_store_key)
        _require(type(payload) is bytes and 0 < len(payload) <= compact.MAX_UPLOAD_OBJECT_BYTES
                 and descriptor.byte_count == len(payload) and descriptor.content_sha256 == _sha(payload)
                 and type(descriptor.activation_manifest) is bool, "upload_payload")
        rows.append([descriptor.object_store_key, _sha(payload), len(payload), descriptor.activation_manifest])
    _require(0 < len(rows) <= 128 and len({row[0] for row in rows}) == len(rows)
             and rows[-1] == [ACTIVATION_KEY, ACTIVATION_SHA256, ACTIVATION_BYTES, True]
             and all(row[3] is False for row in rows[:-1])
             and sum(row[2] for row in rows) == UPLOAD_BYTES, "upload_inventory")
    return rows


def _profile(item):
    value = json.loads(item.profile_bytes)
    _require(type(value) is dict and runtime.targets.canonical(value) == item.profile_bytes, "profile_canonical")
    return value


def _build(value, new_pins, host_pins):
    _sources(host_pins)
    package = _input(value)
    inventory = _inventory(package)
    projected, cells, geometries = [], [], set()
    for candidate, size, arm in CELLS:
        item = projection.build_projection(value, expected_package_sha256=PACKAGE_SHA256,
            expected_lineage_sha256=LINEAGE_SHA256, expected_new_source_pins=new_pins,
            universe_count=size, ar_percent=arm)
        record = item.to_record()
        profile = _profile(item)
        _require(record["package_sha256"] == PACKAGE_SHA256 and record["lineage_sha256"] == LINEAGE_SHA256
                 and record["activation_manifest_sha256"] == ACTIVATION_SHA256
                 and profile["universe_count"] == size and profile["ar_percent"] == arm,
                 "projection_input")
        name = f"ARV2 {candidate} NEWRULE {'SIX' if size == 6 else 'EIGHT'} {'OFF' if arm == 0 else 'AR' + str(arm)} 2021 OCT2026"
        geometry = _sha(_canonical({key: profile[key] for key in (
            "session_axis_sha256", "session_count", "evaluation_sessions", "decision_sessions", "clock", "terminal")}))
        geometries.add(geometry)
        cells.append({"candidate_id": candidate, "project_name": name,
            "projection_sha256": item.projection_sha256, "profile_sha256": profile["profile_sha256"],
            "evaluation_geometry_sha256": geometry,
            "source_files": record["source_files"]})
        projected.append(item)
    _require(len(geometries) == 1, "family_geometry")
    record = {"schema": SCHEMA, "submission_profile_sha256": PROFILE_SHA256,
        "organization_reference_project_id": REFERENCE_PROJECT,
        "package_sha256": PACKAGE_SHA256, "lineage_sha256": LINEAGE_SHA256,
        "activation_manifest_sha256": ACTIVATION_SHA256, "activation_manifest_key": ACTIVATION_KEY,
        "activation_manifest_byte_count": ACTIVATION_BYTES, "upload_inventory": inventory,
        "upload_inventory_sha256": _sha(_canonical(inventory)), "cells": cells,
        "new_source_pins": dict(sorted(new_pins.items())), "host_source_pins": dict(sorted(host_pins.items())),
        "paper_or_live_ready": False, "formal_forward_ready": False}
    raw = _canonical(record)
    _require(len(raw) <= MAX_CONTROL_BYTES, "family_bound")
    plan = FamilyPlan(_sha(raw), raw, value, tuple(projected), tuple(sorted(host_pins.items())))
    key = id(plan)
    _PLANS[key] = (weakref.ref(plan, lambda _, key=key: _PLANS.pop(key, None)), _fingerprint(plan))
    return plan


def require_family(plan, expected_family_sha256):
    _digest(expected_family_sha256)
    _require(type(plan) is FamilyPlan and id(plan) in _PLANS, "genuine_family_required")
    reference, fingerprint = _PLANS[id(plan)]
    _require(reference() is plan and _fingerprint(plan) == fingerprint
             and plan.family_sha256 == expected_family_sha256 == _sha(plan.record_bytes), "family_changed")
    _sources(dict(plan._host_pins))
    _input(plan._input)
    return _parse(plan.record_bytes)


def prepare_family(october_input, *, expected_new_source_pins, expected_host_source_pins):
    """One exclusive OFFLINE preparation; no credential or network access."""
    plan = _build(october_input, expected_new_source_pins, expected_host_source_pins)
    with _Directory(create=True) as directory:
        directory.write("preparation-claim.json", {"schema": SCHEMA, "family_sha256": plan.family_sha256})
        for (candidate, _, _), item in zip(CELLS, plan._projections):
            directory.write(candidate + "-profile.json", _profile(item))
            directory.write(candidate + "-projection.json", item.to_record())
        directory.write("family.json", _parse(plan.record_bytes))
    return plan


def load_family(october_input, *, expected_family_sha256,
                expected_new_source_pins, expected_host_source_pins):
    plan = _build(october_input, expected_new_source_pins, expected_host_source_pins)
    record = require_family(plan, expected_family_sha256)
    with _Directory() as directory:
        _bound(directory, plan, record)
    return plan


def _bound(directory, plan, record):
    _require(_canonical(directory.read("family.json")) == plan.record_bytes
             and _same(directory.read("preparation-claim.json"),
                       {"schema": SCHEMA, "family_sha256": plan.family_sha256}), "prepared_family")
    for (candidate, _, _), item in zip(CELLS, plan._projections):
        _require(_same(directory.read(candidate + "-profile.json"), _profile(item))
                 and _same(directory.read(candidate + "-projection.json"), item.to_record()), "prepared_projection")


def _safe_environment():
    _require("SSLKEYLOGFILE" not in os.environ and http.client.HTTPConnection.debuglevel == 0
             and http.client.HTTPSConnection.debuglevel == 0, "unsafe_http_environment")


def _client():
    _safe_environment()
    api = coverage.production_client()
    _require(type(api) is QuantConnectClient and api._base_url == API_BASE
             and api._transport is coverage._bounded_transport and api._timeout == 30, "bounded_client")
    return api


@contextmanager
def _session(plan, digest):
    record = require_family(plan, digest)
    with _Directory() as directory:
        _bound(directory, plan, record)
        yield directory, record


_ENDPOINTS = frozenset(("authenticate", "projects/read", "projects/create", "projects/nodes/read",
    "files/read", "files/delete", "files/update", "files/create", "compile/create", "compile/read",
    "backtests/create", "backtests/list", "backtests/read"))


def _rpc(directory, plan, api, marker, endpoint, payload):
    _require(endpoint in _ENDPOINTS, "endpoint")
    _safe_environment()
    directory.write(marker + "-intent.json", {"family_sha256": plan.family_sha256,
        "endpoint": endpoint, "request_sha256": _sha(_canonical(payload)), "epoch": int(time.time())})
    try:
        result = api.request(endpoint, payload)
    except Exception:
        raise NewruleSubmissionError("request_ambiguous") from None
    _require(type(result) is dict and result.get("success") is True, "response_refused")
    directory.write(marker + "-observed.json", {"family_sha256": plan.family_sha256,
        "response_sha256": _sha(_canonical(result)), "epoch": int(time.time())})
    return result


def _object(directory, plan, api, marker, endpoint, body, content_type):
    _require(endpoint in {"object/set", "object/properties"} and type(body) is bytes
             and len(body) <= compact.MAX_UPLOAD_OBJECT_BYTES + 4096, "object_request")
    _safe_environment()
    directory.write(marker + "-intent.json", {"family_sha256": plan.family_sha256,
        "endpoint": endpoint, "request_sha256": _sha(body), "epoch": int(time.time())})
    headers = build_auth_headers(api._credentials, api._clock())
    headers["Content-Type"] = content_type
    try:
        status, raw = api._transport(API_BASE + "/" + endpoint, body, headers, api._timeout)
        result = json.loads(raw)
    except Exception:
        raise NewruleSubmissionError("object_request_ambiguous") from None
    _require(type(status) is int and 200 <= status < 300 and type(result) is dict
             and result.get("success") is True, "object_response")
    directory.write(marker + "-observed.json", {"family_sha256": plan.family_sha256,
        "response_sha256": _sha(_canonical(result)), "epoch": int(time.time())})
    return result


def upload_inputs(plan, *, expected_family_sha256):
    with _session(plan, expected_family_sha256) as (directory, record):
        package = _input(plan._input)
        organization = _organization(directory, plan)
        _require(_inventory(package) == record["upload_inventory"], "fresh_upload_inventory")
        directory.write("upload-claim.json", {"family_sha256": plan.family_sha256})
        api = _client()
        _rpc(directory, plan, api, "upload-authenticate", "authenticate", {})
        for index, (descriptor, payload) in enumerate(compact.iter_accepted_risk_preliminary_upload_objects(package)):
            row = record["upload_inventory"][index]
            _require([descriptor.object_store_key, _sha(payload), len(payload), descriptor.activation_manifest] == row,
                     "upload_changed")
            boundary = transport._multipart_boundary(payload)
            _require(("\r\n--" + boundary).encode("ascii") not in payload, "multipart_collision")
            head = (f'--{boundary}\r\nContent-Disposition: form-data; name="organizationId"\r\n\r\n{organization}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="key"\r\n\r\n{row[0]}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="object.bin"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode("ascii")
            _object(directory, plan, api, f"upload-{index:03d}", "object/set",
                    head + payload + f"\r\n--{boundary}--\r\n".encode("ascii"), "multipart/form-data; boundary=" + boundary)
            observed = _object(directory, plan, api, f"upload-{index:03d}-properties", "object/properties",
                              _canonical({"organizationId": organization, "key": row[0]}), "application/json")
            metadata = observed.get("metadata")
            _require(type(metadata) is dict and metadata.get("key") == row[0]
                     and type(metadata.get("size")) is int and metadata["size"] == row[2]
                     and type(metadata.get("md5")) is str and metadata["md5"].lower()
                     == hashlib.md5(payload, usedforsecurity=False).hexdigest(), "uploaded_metadata")
        _require(_inventory(package) == record["upload_inventory"], "upload_postcheck")
        receipt = {"family_sha256": plan.family_sha256, "upload_inventory_sha256": record["upload_inventory_sha256"]}
        directory.write("upload-valid.json", receipt)
        return receipt


def _uploaded(directory, plan, record):
    _require(_same(directory.read("upload-claim.json"), {"family_sha256": plan.family_sha256})
             and _same(directory.read("upload-valid.json"), {"family_sha256": plan.family_sha256,
                "upload_inventory_sha256": record["upload_inventory_sha256"]}), "inputs_not_uploaded")


def _cell(plan, record, candidate, attempt):
    _require(type(candidate) is str and candidate in {row[0] for row in CELLS}
             and type(attempt) is int and 1 <= attempt <= 3, "candidate_attempt")
    index = next(i for i, row in enumerate(CELLS) if row[0] == candidate)
    return record["cells"][index], plan._projections[index], f"{candidate}-A{attempt}"


def _project(row, organization, cell=None, project_id=None, *, idle=True):
    _require(type(row) is dict, "project_shape")
    actual = _number(row.get("projectId"))
    _require((project_id is None or actual == project_id) and row.get("organizationId") == organization
             and (cell is None or row.get("name") == cell["project_name"])
             and row.get("language") == "Py" and row.get("owner") is True
             and row.get("public", False) is False and (not idle or row.get("codeRunning") is False)
             and type(row.get("collaborators")) is list and len(row["collaborators"]) <= 1
             and all(type(item) is dict and item.get("owner") is True for item in row["collaborators"]), "private_owned_project")
    return actual


def _read_project(directory, plan, api, marker, project_id, cell=None, *, idle=True):
    rows = _rpc(directory, plan, api, marker, "projects/read", {"projectId": project_id}).get("projects")
    _require(type(rows) is list and len(rows) == 1, "project_count")
    return _project(rows[0], _organization(directory, plan), cell, project_id, idle=idle)


def _organization(directory, plan):
    claim = directory.read("organization-claim.json")
    value = directory.read("organization.json")
    _require(_same(claim, {"family_sha256": plan.family_sha256, "reference_project_id": REFERENCE_PROJECT})
             and set(value) == {"family_sha256", "reference_project_id", "organization_id", "organization_sha256"}
             and value["family_sha256"] == plan.family_sha256
             and type(value["reference_project_id"]) is int and value["reference_project_id"] == REFERENCE_PROJECT
             and type(value["organization_id"]) is str
             and re.fullmatch(r"[0-9a-f]{32}", value["organization_id"])
             and value["organization_sha256"] == _sha(value["organization_id"].encode("ascii")), "organization_binding")
    return value["organization_id"]


def discover_organization(plan, *, expected_family_sha256):
    """One bounded read of the fixed owned reference, never account enumeration."""
    with _session(plan, expected_family_sha256) as (directory, _):
        binding = {"family_sha256": plan.family_sha256, "reference_project_id": REFERENCE_PROJECT}
        directory.write("organization-claim.json", binding)
        api = _client()
        _rpc(directory, plan, api, "organization-authenticate", "authenticate", {})
        rows = _rpc(directory, plan, api, "organization-project", "projects/read", {"projectId": REFERENCE_PROJECT}).get("projects")
        _require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, "organization_project")
        organization = rows[0].get("organizationId")
        _require(type(organization) is str and re.fullmatch(r"[0-9a-f]{32}", organization), "organization_shape")
        _project(rows[0], organization, project_id=REFERENCE_PROJECT, idle=False)
        digest = _sha(organization.encode("ascii"))
        directory.write("organization.json", {**binding, "organization_id": organization, "organization_sha256": digest})
        return {**binding, "organization_sha256": digest}


def _capacity(response):
    nodes, auto = response.get("nodes"), response.get("autoSelectNode")
    _require(type(nodes) is dict and type(auto) is bool, "capacity_shape")
    rows = nodes.get("backtest")
    _require(type(rows) is list and len(rows) <= 64 and all(type(row) is dict
        and type(row.get("busy")) is bool and type(row.get("active")) is bool for row in rows), "capacity_nodes")
    return {"node_count": len(rows), "busy_count": sum(row["busy"] for row in rows),
        "selected_count": sum(row["active"] for row in rows), "auto_select": auto,
        "available_count": sum(not row["busy"] and (auto or row["active"]) for row in rows)}


def _next(directory, stem, interval, maximum):
    names = directory.names()
    used = sorted(name for name in names if re.fullmatch(re.escape(stem) + r"-\d{3}-intent\.json", name))
    _require(len(used) < maximum and used == [f"{stem}-{index:03d}-intent.json" for index in range(1, len(used) + 1)], "poll_budget")
    if used:
        last = directory.read(used[-1])
        _require(used[-1].replace("-intent", "-observed") in names
                 and used[-1].replace("-intent", "-valid") in names, "prior_poll_ambiguous")
        _require(type(last.get("epoch")) is int and time.time() - last["epoch"] >= interval, "wait_before_poll")
    return f"{stem}-{len(used) + 1:03d}"


def capacity_once(plan, *, expected_family_sha256):
    """One bounded read-only observation; occupied capacity returns WAIT."""
    with _session(plan, expected_family_sha256) as (directory, record):
        _uploaded(directory, plan, record)
        marker = _next(directory, "capacity", STATUS_INTERVAL, STATUS_POLLS)
        api = _client()
        _read_project(directory, plan, api, marker + "-project", REFERENCE_PROJECT, idle=False)
        value = _capacity(_rpc(directory, plan, api, marker, "projects/nodes/read", {"projectId": REFERENCE_PROJECT}))
        directory.write(marker + "-valid.json", {"family_sha256": plan.family_sha256, **value})
        return {**value, "state": "available" if value["available_count"] else "wait"}


def _active(directory, *, exclude=None):
    for name in directory.names():
        if re.fullmatch(r"R30[0-3]-A[1-3]-claim\.json|R29[89]-A[1-3]-claim\.json", name):
            stem = name[:-len("-claim.json")]
            if stem != exclude:
                _require(stem + "-terminal.json" in directory.names(), "another_attempt_active_or_ambiguous")
                terminal = directory.read(stem + "-terminal.json")
                _require(terminal.get("status") in {"Completed.", "Runtime Error", "BuildError"}, "another_attempt_active_or_ambiguous")


def _files(directory, plan, api, marker, project_id, item):
    rows = _rpc(directory, plan, api, marker, "files/read", {"projectId": project_id}).get("files")
    _require(type(rows) is list and len(rows) <= 32, "file_inventory")
    observed = {}
    for row in rows:
        _require(type(row) is dict and type(row.get("projectId")) is int and row["projectId"] == project_id
                 and type(row.get("name")) is str and row["name"] not in observed
                 and type(row.get("content")) is str, "file_binding")
        observed[row["name"]] = row["content"]
    expected = {entry.project_path: entry.source_bytes.decode("ascii") for entry in item.source_files}
    _require(observed == expected, "uploaded_source_mismatch")


def _identity(plan, cell, stem):
    return {"schema": SCHEMA, "family_sha256": plan.family_sha256, "attempt_id": stem,
        "candidate_id": cell["candidate_id"], "projection_sha256": cell["projection_sha256"],
        "profile_sha256": cell["profile_sha256"], "shared_look": 1, "development_look": 1,
        "infrastructure_look": 0, "result_cell": 0}


def _prior_inventory(directory, plan, api, marker, cell, project_id, attempt):
    known = {}
    for prior in range(1, attempt):
        stem = f"{cell['candidate_id']}-A{prior}"
        terminal = directory.read(stem + "-terminal.json")
        _require(terminal.get("status") in {"Runtime Error", "BuildError"}, "prior_not_failed")
        if terminal["status"] == "Runtime Error":
            launch = directory.read(stem + "-launch.json")
            known[launch["backtest_id"]] = launch["backtest_name"]
    response = _rpc(directory, plan, api, marker, "backtests/list", {"projectId": project_id, "includeStatistics": False})
    rows = response.get("backtests")
    _require(type(rows) is list and type(response.get("count")) is int
             and response["count"] == len(rows) == len(known), "prior_run_census")
    for row in rows:
        _require(type(row) is dict and type(row.get("projectId")) is int and row["projectId"] == project_id
                 and row.get("backtestId") in known and row.get("name") == known.pop(row["backtestId"])
                 and row.get("status") == "Runtime Error", "prior_run_changed")
    _require(not known, "prior_run_missing")


def begin_attempt(plan, candidate_id, attempt, *, expected_family_sha256,
                  prior_failure_sha256=None, retry_justification_sha256=None):
    """One mutation/compile dispatch; a claim conservatively spends one look."""
    with _session(plan, expected_family_sha256) as (directory, record):
        _uploaded(directory, plan, record)
        cell, item, stem = _cell(plan, record, candidate_id, attempt)
        _active(directory)
        names = directory.names()
        _require(stem + "-claim.json" not in names, "attempt_spent")
        if attempt == 1:
            _require(prior_failure_sha256 is None and retry_justification_sha256 is None
                     and candidate_id + "-project.json" not in names, "first_attempt")
        else:
            _digest(prior_failure_sha256)
            _digest(retry_justification_sha256)
            prior = directory.read(f"{candidate_id}-A{attempt - 1}-terminal.json")
            _require(prior.get("status") in {"Runtime Error", "BuildError"}
                     and _sha(_canonical(prior)) == prior_failure_sha256, "retry_requires_failed_prior")
        api = _client()
        marker = _next(directory, stem + "-capacity", STATUS_INTERVAL, STATUS_POLLS)
        _read_project(directory, plan, api, marker + "-reference", REFERENCE_PROJECT, idle=False)
        capacity = _capacity(_rpc(directory, plan, api, marker, "projects/nodes/read", {"projectId": REFERENCE_PROJECT}))
        directory.write(marker + "-valid.json", {"family_sha256": plan.family_sha256, **capacity})
        _require(capacity["available_count"] > 0, "capacity_wait")
        claim = {**_identity(plan, cell, stem), "prior_failure_sha256": prior_failure_sha256,
                 "retry_justification_sha256": retry_justification_sha256}
        directory.write(stem + "-claim.json", claim)
        if attempt == 1:
            rows = _rpc(directory, plan, api, stem + "-create-project", "projects/create",
                {"name": cell["project_name"], "language": "Py", "organizationId": _organization(directory, plan)}).get("projects")
            _require(type(rows) is list and len(rows) == 1, "created_project_count")
            project_id = _project(rows[0], _organization(directory, plan), cell)
            directory.write(candidate_id + "-project.json", {"family_sha256": plan.family_sha256,
                "candidate_id": candidate_id, "project_id": project_id})
        else:
            saved = directory.read(candidate_id + "-project.json")
            _require(saved.get("family_sha256") == plan.family_sha256 and saved.get("candidate_id") == candidate_id, "saved_project")
            project_id = _number(saved.get("project_id"))
        _read_project(directory, plan, api, stem + "-owned-project", project_id, cell)
        _prior_inventory(directory, plan, api, stem + "-prior-runs", cell, project_id, attempt)
        if attempt == 1:
            rows = _rpc(directory, plan, api, stem + "-initial-files", "files/read", {"projectId": project_id}).get("files")
            _require(type(rows) is list and len(rows) <= 2 and all(type(row) is dict
                and type(row.get("projectId")) is int and row["projectId"] == project_id
                and row.get("name") in {"main.py", "research.ipynb"} for row in rows), "fresh_project_files")
            existing = [row["name"] for row in rows]
            _require(len(existing) == len(set(existing)), "duplicate_cloud_file")
            if "research.ipynb" in existing:
                _rpc(directory, plan, api, stem + "-delete-default-notebook", "files/delete", {"projectId": project_id, "name": "research.ipynb"})
            for index, entry in enumerate(item.source_files):
                _rpc(directory, plan, api, f"{stem}-source-{index:02d}",
                    "files/update" if entry.project_path in existing else "files/create",
                    {"projectId": project_id, "name": entry.project_path, "content": entry.source_bytes.decode("ascii")})
        _files(directory, plan, api, stem + "-source-readback", project_id, item)
        created = _rpc(directory, plan, api, stem + "-compile-create", "compile/create", {"projectId": project_id})
        compile_id = _id(created.get("compileId"))
        _require(type(created.get("projectId", project_id)) is int
                 and created.get("projectId", project_id) == project_id, "compile_project")
        receipt = {**_identity(plan, cell, stem), "project_id": project_id, "compile_id": compile_id}
        directory.write(stem + "-compile.json", receipt)
        return receipt


def _attempt(directory, plan, record, candidate, attempt):
    cell, item, stem = _cell(plan, record, candidate, attempt)
    claim = directory.read(stem + "-claim.json")
    identity = _identity(plan, cell, stem)
    _require(all(claim.get(key) == value and type(claim.get(key)) is type(value) for key, value in identity.items()), "attempt_claim")
    compile_record = directory.read(stem + "-compile.json")
    _require(set(compile_record) == set(identity) | {"project_id", "compile_id"}
             and all(compile_record.get(key) == value and type(compile_record.get(key)) is type(value)
                     for key, value in identity.items()), "compile_binding")
    _number(compile_record.get("project_id"))
    _id(compile_record.get("compile_id"))
    return cell, item, stem, compile_record


def poll_compile_once(plan, candidate_id, attempt, *, expected_family_sha256):
    with _session(plan, expected_family_sha256) as (directory, record):
        cell, _, stem, compiled = _attempt(directory, plan, record, candidate_id, attempt)
        _require(stem + "-compile-ready.json" not in directory.names() and stem + "-terminal.json" not in directory.names(), "compile_terminal")
        marker = _next(directory, stem + "-compile-poll", COMPILE_INTERVAL, COMPILE_POLLS)
        response = _rpc(directory, plan, _client(), marker, "compile/read",
            {"projectId": compiled["project_id"], "compileId": compiled["compile_id"]})
        state = response.get("state")
        _require(response.get("compileId") == compiled["compile_id"] and state in {"InQueue", "Building", "BuildSuccess", "BuildError"}, "compile_status")
        result = {**compiled, "status": state}
        directory.write(marker + "-valid.json", result)
        if state == "BuildSuccess":
            directory.write(stem + "-compile-ready.json", result)
        elif state == "BuildError":
            result["failure_evidence"] = _failure_evidence(response, "compile_error")
            directory.write(stem + "-terminal.json", result)
        return result


def launch_compiled(plan, candidate_id, attempt, *, expected_family_sha256):
    with _session(plan, expected_family_sha256) as (directory, record):
        cell, item, stem, compiled = _attempt(directory, plan, record, candidate_id, attempt)
        _active(directory, exclude=stem)
        _require(_same(directory.read(stem + "-compile-ready.json"), {**compiled, "status": "BuildSuccess"})
                 and stem + "-terminal.json" not in directory.names(), "compile_not_ready")
        api = _client()
        marker = _next(directory, stem + "-launch-capacity", STATUS_INTERVAL, STATUS_POLLS)
        _read_project(directory, plan, api, marker + "-project", compiled["project_id"], cell)
        _files(directory, plan, api, marker + "-files", compiled["project_id"], item)
        capacity = _capacity(_rpc(directory, plan, api, marker, "projects/nodes/read", {"projectId": compiled["project_id"]}))
        directory.write(marker + "-valid.json", {"family_sha256": plan.family_sha256, **capacity})
        _require(capacity["available_count"] > 0, "capacity_wait")
        name = f"{cell['project_name']} A{attempt} {cell['projection_sha256'][:8]}"
        result = _rpc(directory, plan, api, stem + "-backtest-create", "backtests/create",
            {"projectId": compiled["project_id"], "compileId": compiled["compile_id"], "backtestName": name}).get("backtest")
        _require(type(result) is dict and type(result.get("projectId")) is int
                 and result["projectId"] == compiled["project_id"] and result.get("name") == name
                 and result.get("status") in {"InQueue", "InProgress"}, "created_backtest")
        receipt = {**compiled, "backtest_id": _id(result.get("backtestId")), "backtest_name": name}
        directory.write(stem + "-launch.json", receipt)
        return receipt


def _launch(directory, compiled, stem):
    value = directory.read(stem + "-launch.json")
    _require(set(value) == set(compiled) | {"backtest_id", "backtest_name"}
             and all(value[key] == content and type(value[key]) is type(content) for key, content in compiled.items()), "launch_binding")
    _id(value["backtest_id"])
    _require(type(value["backtest_name"]) is str, "launch_name")
    return value


def poll_status_once(plan, candidate_id, attempt, *, expected_family_sha256):
    with _session(plan, expected_family_sha256) as (directory, record):
        _, _, stem, compiled = _attempt(directory, plan, record, candidate_id, attempt)
        launch = _launch(directory, compiled, stem)
        _require(stem + "-terminal.json" not in directory.names(), "already_terminal")
        marker = _next(directory, stem + "-status", STATUS_INTERVAL, STATUS_POLLS)
        response = _rpc(directory, plan, _client(), marker, "backtests/list", {"projectId": launch["project_id"], "includeStatistics": False})
        rows = response.get("backtests")
        _require(type(rows) is list and type(response.get("count")) is int
                 and response["count"] == len(rows) <= 3, "backtest_census")
        known = {}
        for prior in range(1, attempt + 1):
            prior_name = f"{candidate_id}-A{prior}-launch.json"
            if prior_name in directory.names():
                saved = directory.read(prior_name)
                known[saved["backtest_id"]] = saved["backtest_name"]
        _require(len(rows) == len(known), "backtest_census")
        seen = set()
        for entry in rows:
            _require(type(entry) is dict and type(entry.get("projectId")) is int
                     and entry["projectId"] == launch["project_id"] and entry.get("backtestId") in known
                     and entry["backtestId"] not in seen and entry.get("name") == known[entry["backtestId"]]
                     and (entry["backtestId"] == launch["backtest_id"] or entry.get("status") == "Runtime Error"),
                     "backtest_census")
            seen.add(entry["backtestId"])
        matching = [row for row in rows if type(row) is dict and row.get("backtestId") == launch["backtest_id"]]
        _require(len(matching) == 1, "backtest_missing")
        row = matching[0]
        _require(type(row.get("projectId")) is int and row["projectId"] == launch["project_id"]
                 and row.get("name") == launch["backtest_name"]
                 and row.get("status") in {"InQueue", "InProgress", "Completed.", "Runtime Error"}, "backtest_status")
        result = {**launch, "status": row["status"]}
        if row["status"] == "Runtime Error":
            result["failure_evidence"] = _failure_evidence(row, "runtime_error")
        directory.write(marker + "-valid.json", result)
        if row["status"] in {"Completed.", "Runtime Error"}:
            directory.write(stem + "-terminal.json", result)
        return result


def read_result_once(plan, candidate_id, attempt, *, expected_family_sha256):
    with _session(plan, expected_family_sha256) as (directory, record):
        cell, item, stem, compiled = _attempt(directory, plan, record, candidate_id, attempt)
        launch = _launch(directory, compiled, stem)
        _require(_same(directory.read(stem + "-terminal.json"), {**launch, "status": "Completed."}), "not_completed")
        _require(callable(getattr(runtime, "validate_result_statistics", None)), "result_validator_unavailable")
        directory.write(stem + "-result-read-claim.json", {**launch, "status": "Completed."})
        api = _client()
        _read_project(directory, plan, api, stem + "-result-project", launch["project_id"], cell)
        _files(directory, plan, api, stem + "-result-source", launch["project_id"], item)
        row = _rpc(directory, plan, api, stem + "-aggregate-read", "backtests/read",
                   {"projectId": launch["project_id"], "backtestId": launch["backtest_id"]}).get("backtest")
        _require(type(row) is dict and type(row.get("projectId")) is int
                 and row["projectId"] == launch["project_id"] and row.get("backtestId") == launch["backtest_id"]
                 and row.get("name") == launch["backtest_name"] and row.get("status") == "Completed.", "result_identity")
        stats = row.get("statistics")
        _require(type(stats) is dict, "result_statistics")
        selected = {name: stats.get(name) for name in (runtime.META_STATISTIC, runtime.MONTHLY_STATISTIC)}
        _require(all(type(value) is str and 0 < len(value.encode("utf-8")) <= runtime.MAX_STATISTIC_BYTES
                     for value in selected.values()), "aggregate_bound")
        directory.write(stem + "-retained-statistics.json", {"family_sha256": plan.family_sha256, "statistics": selected})
        validated = runtime.validate_result_statistics(selected, expected_profile=_profile(item))
        result = {**launch, "status": "Completed.", "cell_completed": True,
                  "family_comparable": False, "result_cell": 1, "statistics": validated}
        directory.write(stem + "-result.json", result)
        return result


def summarize_family(plan, *, expected_family_sha256):
    """Local-only; completed cells are not a matched family until all agree."""
    with _session(plan, expected_family_sha256) as (directory, record):
        completed, paths, geometry = [], set(), set()
        for candidate, _, _ in CELLS:
            results = [name for name in directory.names() if re.fullmatch(candidate + r"-A[1-3]-result\.json", name)]
            _require(len(results) <= 1, "multiple_cell_results")
            if not results:
                continue
            value = directory.read(results[0])
            attempt = int(results[0].split("-A")[1][0])
            _, item, stem, compiled = _attempt(directory, plan, record, candidate, attempt)
            launch = _launch(directory, compiled, stem)
            _require(all(value.get(key) == content and type(value.get(key)) is type(content)
                         for key, content in launch.items() if key != "result_cell")
                     and value.get("cell_completed") is True and type(value.get("result_cell")) is int
                     and value.get("result_cell") == 1, "result_receipt")
            retained = directory.read(stem + "-retained-statistics.json")
            stats = runtime.validate_result_statistics(retained["statistics"], expected_profile=_profile(item))
            _require(_same(value.get("statistics"), stats), "result_changed")
            meta = stats["meta"]
            paths.add(meta["common_source_path_sha256"])
            geometry.add((meta["package_sha256"], meta["lineage_sha256"], meta["decision_count"], meta["evaluation_session_count"]))
            completed.append(candidate)
        comparable = len(completed) == 6 and len(paths) == len(geometry) == 1
        return {"family_sha256": plan.family_sha256, "completed_cells": completed,
                "family_complete": len(completed) == 6, "family_comparable": comparable,
                "comparability_mismatch": len(paths) > 1 or len(geometry) > 1,
                "actual_action_exit_confirmation_required": True,
                "paper_or_live_ready": False, "formal_forward_ready": False}
