"""Prospectively bounded provider/control corroboration; no outcomes or QC.

The live entry point accepts only an existing committed lane HEAD. Retained
original controls are derived inside native offline workers. Provider bodies
are screened/projected in those workers and never written to disk. Receipts
describe today's observed capability, not historical publication or PIT data.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import ssl
import stat
import sys
import threading
import time
from urllib import error, parse, request

from research import insider_buying_pilot_firstrate_qualification_v1 as ipc
from research import insider_buying_pilot_provider_controls_v1 as controls
from research import insider_buying_pilot_fmp_eod_projection_v1 as projection
from research.insider_buying_keychain_credentials import KeychainCredential, read_keychain_credential
from research.insider_buying_sharadar_reference_qualification import _screen_credential

native, custody = ipc.native, ipc.native.custody
LANE_ROOT, LANE_BRANCH = native.LANE_ROOT, native.LANE_BRANCH
SELF_PATH = "research/insider_buying_pilot_fmp_eod_qualification_v1.py"
TEST_PATH = "tests/test_insider_buying_pilot_fmp_eod_qualification_v1.py"
OWN_PATHS = (SELF_PATH, TEST_PATH,
    "research/insider_buying_pilot_provider_controls_v1.py",
    "tests/test_insider_buying_pilot_provider_controls_v1.py",
    "research/insider_buying_pilot_fmp_eod_projection_v1.py",
    "tests/test_insider_buying_pilot_fmp_eod_projection_v1.py")
SCHEMA = "insider-pilot-fmp-eod-retained-control-qualification-v1"
OUTPUT_PARTS = ("artifacts", "insider_buying", "pilot_fmp_eod_qualification_v1")
AUDIT_ID = "ib-fmp-eod-retained-control-qualification-20261103-once-v1"
RECENT_ROOT = LANE_ROOT.parent / "insider_buying_sec_complete_16_9ab2ed0"
MAX_BODY = 128 * 1024
MAX_CONTROL = 2 * 1024 * 1024
MAX_INPUT_METADATA = 128 * 1024
LIMIT = 100
HTTP_SECONDS, SOURCE_SECONDS, PROJECT_SECONDS = 15, 120, 30
CLOSE_SECONDS = 1
SPACING_NS = 1_000_000_000
_HEAD, _SHA = re.compile(r"[0-9a-f]{40}\Z"), re.compile(r"[0-9a-f]{64}\Z")
_ACTUAL = object()
_CODES = frozenset({"arguments_refused", "identity_refused", "namespace_consumed", "custody_refused",
    "output_changed", "publication_refused", "controls_refused", "worker_refused", "credential_refused",
    "request_refused", "started_journal_required", "deadline_unavailable", "transport_timeout",
    "transport_error", "http_refused", "redirect_refused", "framing_refused", "oversized_response",
    "partial_response", "credential_or_metadata_refused", "projection_refused", "provider_scope_refused", "qualification_stopped"})


class ProviderQualificationError(ValueError):
    """Finite own codes only; never format foreign exceptions or source data."""


def _need(ok, code):
    if not ok:
        raise ProviderQualificationError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def safe_failure(exc):
    return str(exc) if type(exc) is ProviderQualificationError and str(exc) in _CODES else "qualification_stopped"


def authority():
    return {"source_authenticated": False, "historical_public_known_by_verified": False,
        "historical_identity_verified": False, "point_in_time_data": False, "rights_verified": False,
        "canonical_admitted": False, "full_population_complete": False, "backtesting_ready": False,
        "qc_jobs": 0, "outcome_looks": 0, "backtests": 0}


def registration():
    return {"schema": SCHEMA + "/registration", "audit_id": AUDIT_ID,
        "required_filing_window": ["2020-10-01", "2025-12-31"],
        "warmup_controls": 8, "recent_selected_positions": [0, 5, 8, 14],
        "maximum_controls": 12, "maximum_unique_requests": 36,
        "rows_per_request": LIMIT, "maximum_response_bytes": MAX_BODY,
        "credential_reads_per_provider": 1, "maximum_attempts_per_request": 1,
        "http_open_read_wall_seconds": HTTP_SECONDS, "http_close_wall_seconds": CLOSE_SECONDS,
        "http_total_wall_seconds": HTTP_SECONDS + CLOSE_SECONDS, "source_worker_seconds": SOURCE_SECONDS,
        "projection_worker_seconds": PROJECT_SECONDS, "finish_to_next_start_ns": SPACING_NS,
        "redirect_retry_paging_fallback_or_resume_permitted": False,
        "paid_era_controls_before_warmup_within_provider": True,
        "http_402_403_stop_family_not_prove_providerwide_failure": True,
        "raw_or_normalized_provider_rows_retained": False,
        "receipt_cannot_reparse_unretained_provider_body": True,
        "insider_date_filter_semantics_preasserted": False, "authority": authority()}


def _identity(head):
    _need(type(head) is str and _HEAD.fullmatch(head) and Path.cwd() == LANE_ROOT
        and Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "identity_refused")
    value = native._identity(head)
    own = custody._source_bytes(LANE_ROOT, OWN_PATHS)
    for name, digest in own.items():
        _need(_sha(custody._git(LANE_ROOT, "show", head + ":" + name)) == digest, "identity_refused")
    sources = {**value["source_sha256"], **own}
    value = {**value, "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    _current(value)
    return value


def _current(identity):
    native._current(identity)
    _need(set(OWN_PATHS) <= set(identity["source_sha256"])
        and custody._source_bytes(LANE_ROOT, OWN_PATHS) == {
            p: identity["source_sha256"][p] for p in OWN_PATHS}, "identity_refused")


def _parent_current(identity):
    """Parent-only live Git check; fork-denied workers use source checks."""
    _current(identity)
    _need(Path.cwd() == LANE_ROOT, "identity_refused")
    status = custody._git(LANE_ROOT, "status", "--porcelain=v2", "--branch", "--untracked-files=all").decode("utf-8")
    lines = status.splitlines()
    _need("# branch.oid " + identity["head"] in lines
        and "# branch.head " + LANE_BRANCH in lines
        and all(line.startswith("# ") for line in lines), "identity_refused")


def _case_list(cases):
    _need(type(cases) is list and 1 <= len(cases) <= 12, "controls_refused")
    seen = set()
    for row in cases:
        _need(type(row) is dict and set(row) == {"case_id", "cik", "accession", "form_type", "filing_date",
            "acceptance_digits", "source_symbol", "body_sha256"}, "controls_refused")
        _need(type(row["case_id"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,48}", row["case_id"])
            and row["case_id"] not in seen and type(row["cik"]) is str
            and re.fullmatch(r"[0-9]{10}", row["cik"]) and int(row["cik"]) > 0
            and type(row["accession"]) is str and re.fullmatch(r"[0-9]{18}", row["accession"])
            and type(row["filing_date"]) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["filing_date"])
            and "2020-10-01" <= row["filing_date"] <= "2025-12-31"
            and type(row["acceptance_digits"]) is str and re.fullmatch(r"[0-9]{14}", row["acceptance_digits"])
            and row["form_type"] in {"3", "3/A", "4", "4/A", "5", "5/A"}
            and (row["source_symbol"] is None or type(row["source_symbol"]) is str and len(row["source_symbol"]) <= 64)
            and type(row["body_sha256"]) is str and _SHA.fullmatch(row["body_sha256"]), "controls_refused")
        # Date validity is checked independently of lexical ordering.
        datetime.strptime(row["filing_date"], "%Y-%m-%d")
        seen.add(row["case_id"])
    return cases


def build_requests(cases):
    """A finite metadata plan; this pure factory grants no transport authority."""
    cases = sorted(_case_list(cases), key=lambda r: (r["filing_date"] < "2021-01-01", r["case_id"]))
    result = []
    for family in ("fmp_sec", "fmp_insider", "eod_mapping"):
        grouped = {}
        for case in cases:
            key = (case["cik"], case["filing_date"]) if family == "fmp_sec" else (case["filing_date"],) if family == "fmp_insider" else (case["cik"],)
            grouped.setdefault(key, []).append(case["case_id"])
        for key, ids in grouped.items():
            if family == "fmp_sec":
                endpoint = "https://financialmodelingprep.com/stable/sec-filings-search/cik"
                query = [["cik", key[0]], ["from", key[1]], ["to", key[1]], ["page", "0"], ["limit", str(LIMIT)]]
            elif family == "fmp_insider":
                endpoint = "https://financialmodelingprep.com/stable/insider-trading/latest"
                query = [["date", key[0]], ["page", "0"], ["limit", str(LIMIT)]]
            else:
                endpoint = "https://eodhd.com/api/id-mapping"
                query = [["filter[cik]", key[0]], ["page[limit]", str(LIMIT)], ["page[offset]", "0"], ["fmt", "json"]]
            item = {"provider": "eodhd" if family == "eod_mapping" else "fmp", "family": family,
                "method": "GET", "endpoint": endpoint, "query": query, "case_ids": ids}
            item["fingerprint"] = _sha(_raw({k: v for k, v in item.items() if k != "case_ids"}))
            result.append(item)
    dates = {v["case_id"]: v["filing_date"] for v in cases}
    # Test both paid-era FMP families before an old-depth refusal can stop one.
    result.sort(key=lambda item: (item["provider"] == "eodhd",
        not any(dates[c] >= "2021-01-01" for c in item["case_ids"]),
        {"fmp_sec": 0, "fmp_insider": 1, "eod_mapping": 2}[item["family"]]))
    _need(len(result) <= 36 and len({v["fingerprint"] for v in result}) == len(result), "request_refused")
    return result


def _validate_item(item):
    _need(type(item) is dict and set(item) == {"provider", "family", "method", "endpoint", "query", "case_ids", "fingerprint"}, "request_refused")
    profiles = {
        "fmp_sec": ("fmp", "https://financialmodelingprep.com/stable/sec-filings-search/cik", ["cik", "from", "to", "page", "limit"]),
        "fmp_insider": ("fmp", "https://financialmodelingprep.com/stable/insider-trading/latest", ["date", "page", "limit"]),
        "eod_mapping": ("eodhd", "https://eodhd.com/api/id-mapping", ["filter[cik]", "page[limit]", "page[offset]", "fmt"])}
    _need(item["family"] in profiles, "request_refused")
    provider, endpoint, keys = profiles[item["family"]]
    _need(item["provider"] == provider and item["method"] == "GET" and item["endpoint"] == endpoint
        and type(item["query"]) is list and len(item["query"]) == len(keys)
        and all(type(v) is list and len(v) == 2 and all(type(s) is str for s in v) for v in item["query"])
        and [v[0] for v in item["query"]] == keys
        and type(item["case_ids"]) is list and 1 <= len(item["case_ids"]) <= 12
        and len(set(item["case_ids"])) == len(item["case_ids"])
        and all(type(v) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,48}", v) for v in item["case_ids"]), "request_refused")
    query = dict(item["query"])
    if provider == "fmp":
        _need(query["page"] == "0" and query["limit"] == str(LIMIT), "request_refused")
        day = query["from"] if item["family"] == "fmp_sec" else query["date"]
        _need(type(day) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day)
            and "2020-10-01" <= day <= "2025-12-31", "request_refused")
        try: datetime.strptime(day, "%Y-%m-%d")
        except ValueError: raise ProviderQualificationError("request_refused") from None
        if item["family"] == "fmp_sec":
            _need(query["from"] == query["to"] and re.fullmatch(r"[0-9]{10}", query["cik"])
                and int(query["cik"]) > 0, "request_refused")
    else:
        _need(re.fullmatch(r"[0-9]{10}", query["filter[cik]"]) and int(query["filter[cik]"]) > 0
            and query["page[limit]"] == str(LIMIT) and query["page[offset]"] == "0" and query["fmt"] == "json", "request_refused")
    _need(item["fingerprint"] == _sha(_raw({k: v for k, v in item.items() if k not in {"case_ids", "fingerprint"}})), "request_refused")
    return item


def _validate_projection(value, cases):
    keys = {"schema", "family", "scoped", "metadata_clean", "response_rows_retained", "response_body_retained",
        "metadata_evidence_can_independently_reparse_response", "credential_screening_is_external_required_control",
        "body_pin", "counts", "case_checks", "filing_date_bounds", "pagination", "all_six_form_coverage_verified",
        "current_label_agreement_is_historical_identity", "naive_acceptance_is_publication_or_timezone_evidence",
        "latest_date_filter_semantics_verified", "financial_values_interpreted", "authority"}
    _need(type(value) is dict and set(value) == keys and value["schema"] == projection.SCHEMA
        and value["family"] in {"fmp_sec_search", "fmp_insider_latest", "eod_current_mapping"}
        and type(value["scoped"]) is type(value["metadata_clean"]) is bool
        and _raw(value["authority"]) == _raw(authority()), "projection_refused")
    for key in ("response_rows_retained", "response_body_retained", "metadata_evidence_can_independently_reparse_response",
        "all_six_form_coverage_verified", "current_label_agreement_is_historical_identity",
        "naive_acceptance_is_publication_or_timezone_evidence", "latest_date_filter_semantics_verified", "financial_values_interpreted"):
        _need(value[key] is False, "projection_refused")
    _need(value["credential_screening_is_external_required_control"] is True, "projection_refused")
    pin = value["body_pin"]
    if value["scoped"] and value["metadata_clean"]:
        _need(type(pin) is dict and set(pin) == {"bytes", "sha256"} and type(pin["bytes"]) is int
            and 0 < pin["bytes"] <= MAX_BODY and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"]), "projection_refused")
    else: _need(pin is None, "projection_refused")
    _need(type(value["case_checks"]) is dict and set(value["case_checks"]) <= {c["case_id"] for c in cases}
        and (value["scoped"] or value["case_checks"] == {}), "projection_refused")
    # No source strings/rows are permitted in these finite derived counters.
    def counters(tree, depth=0):
        _need(type(tree) is dict and len(tree) <= 128 and depth <= 4, "projection_refused")
        for key, child in tree.items():
            _need(type(key) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", key), "projection_refused")
            if type(child) is dict: counters(child, depth+1)
            else: _need(type(child) in {int, bool} and (type(child) is bool or 0 <= child <= 1_000_000_000), "projection_refused")
    counters(value["counts"]); counters(value["case_checks"]); counters(value["pagination"])
    dates = value["filing_date_bounds"]
    _need(dates is None or type(dates) is list and len(dates) == 2 and all(type(v) is str
        and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v) and "2020-10-01" <= v <= "2025-12-31" for v in dates), "projection_refused")
    return value


def _policy(paths):
    allowed = set()
    for item in paths:
        path = Path(item)
        _need(path.is_absolute() and ".." not in path.parts
            and (path.is_relative_to(LANE_ROOT / "artifacts") or path.is_relative_to(RECENT_ROOT)), "controls_refused")
        allowed.add(path)
        allowed.update(p for p in path.parents if p.is_relative_to(LANE_ROOT / "artifacts") or p.is_relative_to(RECENT_ROOT))
    choices = "(require-any " + " ".join("(literal " + json.dumps(str(p)) + ")" for p in sorted(allowed)) + ")" if allowed else None
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    for root in (LANE_ROOT / "artifacts", RECENT_ROOT):
        policy += '(deny file-read* ' + ('(require-all (subpath ' + json.dumps(str(root)) + ') (require-not ' + choices + '))' if choices else '(subpath ' + json.dumps(str(root)) + ')') + ')'
    for private in (Path("/Volumes"), Path(pwd.getpwuid(os.geteuid()).pw_dir) / "Library" / "Keychains"):
        policy += '(deny file-read* (subpath ' + json.dumps(str(private)) + '))'
    return policy


def _screen(raw, credential):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, "credential_or_metadata_refused")
    try:
        _screen_credential(raw, {"opaque": raw.decode("utf-8")}, credential)
        def pairs(items):
            value = {}
            for key, child in items:
                _need(key not in value, "credential_or_metadata_refused"); value[key] = child
            return value
        body = json.loads(raw, object_pairs_hook=pairs, parse_int=str, parse_float=str,
            parse_constant=lambda _: _need(False, "credential_or_metadata_refused"))
        _screen_credential(raw, {"source": body}, credential)
    except Exception:
        raise ProviderQualificationError("credential_or_metadata_refused") from None


def _project(raw, cases, item):
    query = dict(item["query"])
    if item["family"] == "fmp_sec":
        value = projection.project_sec_search(raw, cases, queried_cik=query["cik"],
            from_date=query["from"], to_date=query["to"], page=0, limit=LIMIT)
    elif item["family"] == "fmp_insider":
        value = projection.project_insider_latest(raw, cases, requested_date=query["date"], page=0, limit=LIMIT)
    else:
        value = projection.project_eod_mapping(raw, cases, requested_ciks=(query["filter[cik]"],), offset=0, limit=LIMIT)
    return projection.public_payload(value)


def _worker(role, identity):
    guard = None
    try:
        native._isolated(); native.batch.campaign.base._prove_isolation()
        guard = native._WorkerMemoryGuard(); _current(identity)
        raw = sys.stdin.buffer.read(ipc.MAX_IPC_INPUT + 1)
        _need(len(raw) <= ipc.MAX_IPC_INPUT, "worker_refused")
        supplied = json.loads(raw) if raw else {}
        if role == "health":
            _need(supplied == {}, "worker_refused")
            value = {"passed": True, "source_only": True, "source_files_opened": False,
                "native_controls": True, "authority": authority()}
        elif role == "metadata":
            _need(supplied == {}, "worker_refused")
            value = controls.metadata_actual(memory=guard)
            _need(len(_raw(value)) <= MAX_INPUT_METADATA, "controls_refused")
        elif role == "bodies":
            value = controls.derive_actual(supplied, memory=guard)
            _case_list(value["cases"])
        elif role == "project":
            _need(set(supplied) == {"raw_base64", "cases", "item", "credential"}, "worker_refused")
            _need(type(supplied["raw_base64"]) is str and len(supplied["raw_base64"]) <= 4*((MAX_BODY+2)//3), "worker_refused")
            source = base64.b64decode(supplied["raw_base64"], validate=True)
            cred = supplied["credential"]
            _need(type(cred) is dict and set(cred) == {"provider", "value"}
                and cred["provider"] in {"fmp", "eodhd"} and type(cred["value"]) is str
                and re.fullmatch(r"[!-~]{1,4096}", cred["value"]), "worker_refused")
            credential = KeychainCredential(cred["provider"], cred["value"])
            _screen(source, credential)
            try:
                projected = _project(source, _case_list(supplied["cases"]), supplied["item"])
                value = {"passed": True, "projection": projected}
            except projection.ProjectionError:
                value = {"passed": False, "code": "projection_refused", "projection": None}
        else:
            raise ProviderQualificationError("worker_refused")
        _current(identity); guard.check()
        wire = _raw({"ok": True, "value": value})
        _need(len(wire) <= MAX_CONTROL, "worker_refused")
    except Exception:
        wire = _raw({"ok": False, "code": "native_refused"})
    try:
        if guard is not None: guard.check()
        sys.stdout.buffer.write(wire+b"\n"); sys.stdout.buffer.flush()
        if guard is not None: guard.check()
    finally:
        if guard is not None: guard.close()


def _child(role, identity, supplied=None, *, paths=()):
    _need(role in {"health", "metadata", "bodies", "project"}, "worker_refused")
    code = "import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_pilot_fmp_eod_qualification_v1 as m;m._worker("+repr(role)+",json.loads("+repr(_raw(identity).decode())+"))"
    policy = _policy(paths)
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix="+native.EMPTY_CACHE_PREFIX, "-c", code)
    payload = b"" if supplied is None else _raw(supplied)
    _need(len(payload) <= ipc.MAX_IPC_INPUT, "worker_refused")
    try:
        value = ipc._launch(command, payload, timeout=PROJECT_SECONDS if role == "project" else SOURCE_SECONDS)
    except Exception:
        raise ProviderQualificationError("worker_refused") from None
    _need(len(_raw(value)) <= MAX_CONTROL, "worker_refused")
    return value


class _Context:
    def __init__(self, root, identity, *, fixture=False, checker=None):
        _need(type(root) is Path or isinstance(root, Path), "arguments_refused")
        _need((fixture and not root.resolve().is_relative_to(LANE_ROOT) and callable(checker))
            or (not fixture and root == LANE_ROOT and checker is None), "arguments_refused")
        self.root, self.identity, self.fixture = root, identity, fixture
        self.checker = checker if fixture else lambda: _parent_current(identity)
        self.parent = self.directory = None
        self.pins, self.versions, self.latch, self.active = {}, {}, None, None
        self.dispatched = set()
        self.token = None if fixture else _ACTUAL
        try:
            self.parent = custody._Chain(root, OUTPUT_PARTS, create=True)
            _need(not os.listdir(self.parent.fd), "namespace_consumed")
            self.latch = self._write(self.parent.fd, "scope-reservation.json", _raw({
                "registration": registration(), "execution_identity": identity, "fixture_only": fixture}))
            self.directory = custody._Chain(root, (*OUTPUT_PARTS, AUDIT_ID), create=True, exclusive_last=True)
            self.check()
        except BaseException:
            self.close(); raise

    @staticmethod
    def _write(fd, name, raw):
        _need(type(raw) is bytes and 0 < len(raw) <= MAX_CONTROL
            and type(name) is str and re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,99}", name), "publication_refused")
        leaf = os.open(name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600, dir_fd=fd)
        with os.fdopen(leaf, "wb") as stream:
            _need(stream.write(raw) == len(raw), "publication_refused")
            stream.flush(); os.fsync(stream.fileno())
            version = custody._version(os.fstat(stream.fileno()))
        os.fsync(fd)
        return {"bytes": len(raw), "sha256": _sha(raw), "version": version}

    @staticmethod
    def _verify(fd, name, pin):
        before = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _need(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_uid == os.geteuid() and before.st_nlink == 1
            and custody._version(before) == pin["version"], "output_changed")
        raw = custody._read_leaf(fd, name, limit=MAX_CONTROL)
        after = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _need(custody._version(after) == pin["version"] and len(raw) == pin["bytes"]
            and _sha(raw) == pin["sha256"], "output_changed")

    def check(self):
        self.checker(); self.parent.recheck(); self.directory.recheck()
        _need(set(os.listdir(self.parent.fd)) == {"scope-reservation.json", AUDIT_ID}
            and set(os.listdir(self.directory.fd)) == set(self.pins), "output_changed")
        for folder in (self.parent, self.directory):
            info = os.fstat(folder.fd)
            _need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, "custody_refused")
        self._verify(self.parent.fd, "scope-reservation.json", self.latch)
        for name, pin in self.pins.items(): self._verify(self.directory.fd, name, pin)
        self.parent.recheck(); self.directory.recheck()

    def publish(self, name, value):
        self.check()
        self.pins[name] = self._write(self.directory.fd, name, _raw(value))
        self.check()
        return self.pins[name]["sha256"]

    def read(self, name):
        self.check()
        _need(name in self.pins, "output_changed")
        return json.loads(custody._read_leaf(self.directory.fd, name, limit=MAX_CONTROL))

    def close(self):
        failed, primary = False, sys.exc_info()[0] is not None
        for name in ("directory", "parent"):
            held = getattr(self, name, None); setattr(self, name, None)
            if held is not None:
                try: held.close()
                except Exception: failed = True
        _need(primary or not failed, "custody_refused")


@dataclass(frozen=True, slots=True, repr=False)
class _Reply:
    status: int | None
    body: bytes = field(repr=False)
    code: str | None = None


class _DenyRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class _Deadline:
    def __enter__(self):
        _need(threading.current_thread() is threading.main_thread()
            and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "deadline_unavailable")
        self.old = signal.getsignal(signal.SIGALRM)
        def expired(_sig, _frame): raise TimeoutError
        signal.signal(signal.SIGALRM, expired)
        try:
            signal.setitimer(signal.ITIMER_REAL, HTTP_SECONDS)
        except BaseException:
            try: signal.setitimer(signal.ITIMER_REAL, 0)
            finally: signal.signal(signal.SIGALRM, self.old)
            raise ProviderQualificationError("deadline_unavailable") from None
        return self

    def arm_cleanup(self):
        # The open/read alarm is one-shot. It may already have fired before
        # finally enters close, so close needs its own finite cleanup alarm.
        try: signal.setitimer(signal.ITIMER_REAL, CLOSE_SECONDS)
        except BaseException:
            raise ProviderQualificationError("deadline_unavailable") from None

    def __exit__(self, *_exc):
        try: signal.setitimer(signal.ITIMER_REAL, 0)
        finally: signal.signal(signal.SIGALRM, self.old)


def _read_response(stream, status):
    # Non-200 bodies (which may contain credentials) are never read or hashed.
    if status != 200:
        return _Reply(status, b"", "redirect_refused" if 300 <= status < 400 else "http_refused")
    _need(callable(getattr(stream.headers, "get_all", None)), "framing_refused")
    enc, lengths, transfer = (stream.headers.get_all(k, []) for k in ("Content-Encoding", "Content-Length", "Transfer-Encoding"))
    _need(all(type(v) is list and all(type(x) is str for x in v) for v in (enc, lengths, transfer)), "framing_refused")
    _need(len(enc) <= 1 and (not enc or enc[0].strip().lower() == "identity") and len(lengths) <= 1
        and len(transfer) <= 1 and (not transfer or not lengths and transfer[0].strip().lower() == "chunked"), "framing_refused")
    length = None
    if lengths:
        _need(re.fullmatch(r"[0-9]{1,20}", lengths[0]), "framing_refused")
        length = int(lengths[0]); _need(length <= MAX_BODY, "oversized_response")
    chunks, size = [], 0
    while size <= MAX_BODY:
        chunk = stream.read(MAX_BODY + 1 - size)
        _need(type(chunk) is bytes and len(chunk) <= MAX_BODY + 1 - size, "partial_response")
        if not chunk:
            _need(length is None or size == length, "partial_response")
            return _Reply(status, b"".join(chunks))
        size += len(chunk); chunks.append(chunk)
    raise ProviderQualificationError("oversized_response")


def _credential(value, provider, *, fixture=False):
    _need(type(value) is KeychainCredential and value.provider == provider
        and value.fixture_only is fixture and type(value.value) is str
        and re.fullmatch(r"[!-~]{1,4096}", value.value)
        and value.value.lower() not in {"demo", "test-api-key"}, "credential_refused")
    return value


def _live_url(item, credential):
    _validate_item(item)
    expected = "eodhd" if item["family"] == "eod_mapping" else "fmp"
    _credential(credential, expected)
    field = "api_token" if expected == "eodhd" else "apikey"
    return item["endpoint"] + "?" + parse.urlencode([*map(tuple, item["query"]), (field, credential.value)])


def _transport(context, item, credential):
    _need(type(context) is _Context and context.fixture is False and context.token is _ACTUAL
        and context.root == LANE_ROOT and context.active is not None, "started_journal_required")
    context.check()
    plan, started = context.read("request-plan.json"), context.read(context.active)
    bound = context.read("controls.json"); cases = _case_list(bound["cases"])
    _validate_item(item)
    _need(plan == {"schema": SCHEMA+"/plan", "requests": build_requests(cases),
        "control_sha256": _sha(_raw(cases)), "fixture_only": False, "registration": registration()}
        and type(started["request_index"]) is int and 0 <= started["request_index"] < len(plan["requests"])
        and plan["requests"][started["request_index"]] == item and started["fingerprint"] == item["fingerprint"]
        and started["maximum_attempts"] == 1 and started["reservation_sha256"] == context.pins["request-plan.json"]["sha256"], "started_journal_required")
    _need(item["fingerprint"] not in context.dispatched, "started_journal_required")
    context.dispatched.add(item["fingerprint"])
    url = _live_url(item, credential); parsed = parse.urlsplit(url)
    _need(parsed.scheme == "https" and parsed.netloc in {"financialmodelingprep.com", "eodhd.com"}
        and not parsed.fragment and not parsed.username and not parsed.password
        and url == _live_url(item, credential), "request_refused")
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(), request.HTTPSHandler(context=ssl.create_default_context()))
    req = request.Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity"}, method="GET")
    stream = None
    try:
        with _Deadline() as deadline:
            context.check(); _need(req.full_url == _live_url(item, credential), "request_refused")
            try:
                try: stream = opener.open(req, timeout=HTTP_SECONDS)
                except error.HTTPError as exc: stream = exc
                status = stream.getcode()
                _need(type(status) is int and 100 <= status <= 599 and stream.geturl() == url, "framing_refused")
                return _read_response(stream, status)
            finally:
                if stream is not None:
                    deadline.arm_cleanup()
                    stream.close()
    except TimeoutError: return _Reply(None, b"", "transport_timeout")
    except ProviderQualificationError as exc: return _Reply(None, b"", safe_failure(exc))
    except Exception: return _Reply(None, b"", "transport_error")


def _drive(context, cases, identity, *, fixture=False, credential_reader=None, transport=None, project=None):
    _need(context.fixture is fixture and (not fixture and all(v is None for v in (credential_reader, transport, project))
        or fixture and all(callable(v) for v in (credential_reader, transport, project))), "arguments_refused")
    requests = build_requests(cases)
    plan_sha = context.publish("request-plan.json", {"schema": SCHEMA+"/plan", "requests": requests,
        "control_sha256": _sha(_raw(cases)), "fixture_only": fixture, "registration": registration()})
    reader = credential_reader if fixture else read_keychain_credential
    credential_cache, stopped_providers, stopped_families, receipts = {}, set(), set(), []
    previous_finish = None
    for i, item in enumerate(requests):
        provider, family = item["provider"], item["family"]
        if provider in stopped_providers or family in stopped_families:
            receipts.append({"request_index": i, "family": family, "attempted": False, "code": "prior_provider_or_family_refusal"})
            continue
        if provider not in credential_cache:
            context.publish(provider+"-credential-started.json", {"provider": provider, "maximum_reads": 1, "plan_sha256": plan_sha})
            credential = None
            try: credential = _credential(reader(provider), provider, fixture=fixture)
            except Exception: pass
            context.publish(provider+"-credential-completed.json", {"provider": provider,
                "read_observed": credential is not None, "secret_stored_or_hashed": False})
            credential_cache[provider] = credential
            if credential is None:
                stopped_providers.add(provider)
                receipts.append({"request_index": i, "family": family, "attempted": False, "code": "credential_refused"})
                continue
        credential = credential_cache[provider]
        if previous_finish is not None:
            remaining = SPACING_NS - (time.monotonic_ns() - previous_finish)
            if remaining > 0: time.sleep(remaining / 1_000_000_000)
        name = f"request-{i:03d}-started.json"
        context.publish(name, {"schema": SCHEMA+"/request-started", "request_index": i,
            "fingerprint": item["fingerprint"], "maximum_attempts": 1,
            "reservation_sha256": plan_sha, "started_utc": _now()})
        context.active = name; context.check()
        response = transport(item, credential) if fixture else _transport(context, item, credential)
        previous_finish = time.monotonic_ns(); context.active = None; context.check()
        _need(type(response) is _Reply and (response.status is None or type(response.status) is int
            and 100 <= response.status <= 599) and type(response.body) is bytes
            and len(response.body) <= MAX_BODY and (response.code is None or response.code in _CODES), "request_refused")
        observed = None; code = response.code
        if response.status == 200 and code is None:
            relevant = [v for v in cases if v["case_id"] in item["case_ids"]]
            try:
                if fixture: observed = project(response.body, relevant, item, credential)
                else:
                    value = _child("project", identity, {"raw_base64": base64.b64encode(response.body).decode(),
                        "cases": relevant, "item": item, "credential": {"provider": provider, "value": credential.value}})
                    _need(value.get("passed") is True and type(value.get("projection")) is dict, "projection_refused")
                    observed = value["projection"]
                _validate_projection(observed, relevant)
                _need(len(_raw(observed)) <= MAX_INPUT_METADATA, "projection_refused")
                if observed["scoped"] is False: code = "provider_scope_refused"
            except Exception:
                code = "projection_refused"; observed = None
        else: code = code or "http_refused"
        if code is not None:
            if response.status in {401, 429} or response.status is None or (response.status is not None and response.status >= 500):
                stopped_providers.add(provider)
            else: stopped_families.add(family)
        record = {"schema": SCHEMA+"/request-completed", "request_index": i, "family": family,
            "attempted": True, "fingerprint": item["fingerprint"], "http_status": response.status,
            "code": code or "metadata_projected", "projection": observed, "raw_response_retained": False,
            "error_or_refused_body_hashed_or_retained": False, "finished_utc": _now()}
        context.publish(f"request-{i:03d}-completed.json", record); receipts.append(record)
    return {"schema": SCHEMA+"/complete", "fixture_only": fixture, "execution_head": identity["head"],
        "planned_requests": len(requests), "transport_invocation_count": sum(v["attempted"] for v in receipts),
        "unattempted_requests": sum(not v["attempted"] for v in receipts),
        "credential_reads_observed": sum(v is not None for v in credential_cache.values()),
        "credential_read_attempts": len(credential_cache),
        "projected_responses": sum(v.get("projection") is not None for v in receipts),
        "scoped_responses": sum(v.get("projection") is not None and v["projection"]["scoped"] for v in receipts),
        "clean_scoped_responses": sum(v.get("projection") is not None and v["projection"]["scoped"] and v["projection"]["metadata_clean"] for v in receipts),
        "receipts": receipts, "authority": authority(), "raw_response_retained": False,
        "remote_request_count_measured": False, "completed_utc": _now()}


def preflight_actual(expected_head):
    identity = _identity(expected_head)
    value = _child("health", identity)
    _need(value == {"passed": True, "source_only": True, "source_files_opened": False,
        "native_controls": True, "authority": authority()}, "worker_refused")
    _current(identity)
    return {"source_only": True, "source_images": len(identity["source_sha256"]),
        "source_inventory_sha256": identity["source_inventory_sha256"], **value}


def run_actual(expected_head):
    identity = _identity(expected_head); context = None; stage = "reservation"
    try:
        context = _Context(LANE_ROOT, identity)
        stage = "controls_metadata"
        context.publish("controls-metadata-started.json", {"worker_invocations": 1})
        metadata = _child("metadata", identity, paths=controls.metadata_paths())
        _need(len(_raw(metadata)) <= MAX_INPUT_METADATA, "controls_refused")
        context.publish("controls-metadata.json", metadata)
        stage = "controls_bodies"
        context.publish("controls-bodies-started.json", {"worker_invocations": 1, "metadata_sha256": _sha(_raw(metadata))})
        bound = _child("bodies", identity, metadata, paths=controls.body_paths(metadata))
        cases = _case_list(bound["cases"]); _need(len(cases) == 12, "controls_refused")
        context.publish("controls.json", bound)
        stage = "provider_qualification"
        result = _drive(context, cases, identity)
        result.update(scope_reservation_sha256=context.latch["sha256"],
            control_evidence_sha256=context.pins["controls.json"]["sha256"],
            request_plan_sha256=context.pins["request-plan.json"]["sha256"],
            published_leaf_pins={name: {"bytes": pin["bytes"], "sha256": pin["sha256"]}
                for name, pin in context.pins.items()})
        context.publish("complete.json", result); context.check()
        return public_summary(result)
    except Exception:
        if context is not None:
            try: context.publish("failure.json", {"schema": SCHEMA+"/failure", "stage": stage,
                "code": "qualification_stopped", "authority": authority()})
            except Exception: pass
        raise ProviderQualificationError("qualification_stopped") from None
    finally:
        if context is not None: context.close()


def public_summary(result):
    _need(type(result) is dict and result.get("schema") == SCHEMA+"/complete", "arguments_refused")
    return {k: result[k] for k in ("schema", "fixture_only", "execution_head", "planned_requests",
        "transport_invocation_count", "unattempted_requests", "credential_reads_observed", "credential_read_attempts",
        "projected_responses", "scoped_responses", "clean_scoped_responses", "authority", "raw_response_retained", "remote_request_count_measured")}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--expected-head", required=True)
    cli.add_argument("--health", action="store_true")
    args = cli.parse_args(argv)
    try: value = preflight_actual(args.expected_head) if args.health else run_actual(args.expected_head)
    except Exception as exc:
        print(_raw({"refused": safe_failure(exc)}).decode()); return 2
    print(_raw(value).decode())
    return 0 if args.health or value["clean_scoped_responses"] == value["planned_requests"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
