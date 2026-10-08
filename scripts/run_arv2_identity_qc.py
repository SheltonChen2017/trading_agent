"""R284 current-identity infrastructure diagnostic; no I/O on import.

Only independently public OpenFIGI reference strings enter the fresh QC
project. Sharadar rows/prices do not. Seven FIGI/SID/reverse-FIGI matches are
checked inside QC; mapped values and their hashes never leave the cloud.
This does not authenticate historical identity, first availability or any
formal readiness gate. Production actions require an explicitly pinned,
offline-prepared package and spend durable claims before contact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

from research.analyst_revisions_v2_qc import six_universe_coverage_submission as boundary
from research.quantconnect import API_BASE, QuantConnectClient


class IdentityQcError(ValueError):
    """A pinned identity, local control or bounded remote result refused."""


CANDIDATE_ID = "R284"
SESSION = "2026-10-07"
REFERENCE_PROJECT_ID = 37165262
PROJECT_NAME = "ARV2 R284 PUBLIC SEVEN IDENTITY 20261007"
BACKTEST_NAME = "ARV2 R284A1 public FIGI identity only 20261007"
META_NAME = "ARV2_R284_PUBLIC_IDENTITY_META"
INPUT_SCHEMA = "arv2-seven-public-figi-identity-input-v1"
CONTINUITY_INPUT_SCHEMA = "arv2-seven-public-figi-continuity-input-v2"
PREPARED_SCHEMA = "arv2-r284-prepared-identity-diagnostic-v1"
META_SCHEMA = "arv2-r284-public-identity-meta-v1"
OBSERVATION_SCHEMA = "arv2-r284-response-observation-v1"
TICKERS = ("QCOM", "SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
ROLES = {ticker: "stock" if ticker == "QCOM" else "fund" for ticker in TICKERS}
ARTIFACT_ROOT = Path(__file__).absolute().parents[1] / "artifacts" / "analyst_revisions_v2" / "identity_qc"
MAX_FILE_BYTES = 256 * 1024
MAX_META_BYTES = 8 * 1024
MAX_COMPILE_POLLS = 20
MAX_STATUS_POLLS = 60
MAX_OBSERVATIONS = 256
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_FIGI = re.compile(r"[A-Z0-9]{12}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_INPUT_KEYS = {"schema", "rows", "price_manifest_sha256", "public_reference_sha256", "sharadar_identity_manifest_sha256"}
_CONTINUITY_INPUT_KEYS = _INPUT_KEYS | {"continuity_manifest_sha256", "vintage_manifest_sha256"}
_FALSE_FLAGS = {"point_in_time": False, "independently_reviewed": False, "decision_ready": False,
                "paper_authorized": False, "orders_authorized": False, "formal_source_admitted": False}
_QUALIFICATION_FALSE_FLAGS = {"complete_price_identity_binding": False,
                            "historical_identity_authenticated": False,
                            "independent_price_identity_binding_authenticated": False,
                            "cusip_corroboration_complete": False,
                            "vintage_price_range_admitted": False}
_RUNTIME_FALSE_FLAGS = {**_FALSE_FLAGS, **_QUALIFICATION_FALSE_FLAGS}
_REASONS = {"matched", "resolution_unavailable", "not_usa_equity", "reverse_figi_mismatch", "sid_collision", "mapping_exception"}
_SOURCE_TEMPLATE_TOKEN = "__R284_SOURCE_TEMPLATE_SHA256__"
PROFILE = {"schema": "arv2-r284-public-seven-identity-profile-v1", "candidate_id": CANDIDATE_ID,
           "attempt": 1, "session": SESSION, "reference_project_id": REFERENCE_PROJECT_ID,
           "project_name": PROJECT_NAME, "backtest_name": BACKTEST_NAME,
           "mode": "research_only_no_order_identity_infrastructure", "input_count": 7,
           "market_subscriptions": False, "history_calls": 0, "orders": False,
           "object_store": False, "cloud_mapping_export": False,
           "maximum_compile_polls": MAX_COMPILE_POLLS, "maximum_status_polls": MAX_STATUS_POLLS,
           **_FALSE_FLAGS}


def _fail(code):
    raise IdentityQcError("R284 refused: " + code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail("canonical_encoding")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_input(value):
    """Match the research binders: compact ASCII JSON plus exactly one LF."""
    return canonical(value) + b"\n"


PROFILE_SHA256 = sha(canonical(PROFILE))
CONTINUITY_PROFILE = {**PROFILE, "schema": "arv2-r284-public-seven-continuity-profile-v2",
                      "input_schema": CONTINUITY_INPUT_SCHEMA,
                      "mode": "research_only_no_order_qualified_vintage_current_continuity",
                      "source_binding_semantics": "qualified_continuity_not_complete_price_identity",
                      "source_qualifications_retained_private_host_only": True,
                      "current_vendor_figi_missing_refusal_preserved": True,
                      **_QUALIFICATION_FALSE_FLAGS}
CONTINUITY_PROFILE_SHA256 = sha(canonical(CONTINUITY_PROFILE))


def _input_keys(schema):
    if type(schema) is not str:
        _fail("input_schema")
    if schema == INPUT_SCHEMA:
        return _INPUT_KEYS
    if schema == CONTINUITY_INPUT_SCHEMA:
        return _CONTINUITY_INPUT_KEYS
    _fail("input_schema")


def _input_hashes(value):
    return {key: value[key] for key in sorted(_input_keys(value["schema"]) - {"schema", "rows"})}


def _profile(schema):
    _input_keys(schema)
    profile = PROFILE if schema == INPUT_SCHEMA else CONTINUITY_PROFILE
    return profile, sha(canonical(profile))


def _hash(value, name):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _fail(name + "_hash")
    return value


def _same(value, expected):
    """JSON type-sensitive equality (False is not 0; True is not 1)."""
    return canonical(value) == canonical(expected)


def _bound(value, expected):
    return type(value) is dict and _same({key: value.get(key) for key in expected}, expected)


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail("duplicate_json_key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("ascii"), object_pairs_hook=pairs,
                           parse_constant=lambda value: _fail("nonfinite_json"))
    except (ValueError, UnicodeError, RecursionError):
        _fail("json_encoding")
    if canonical(value) != raw:
        _fail("noncanonical_json")
    return value


def validate_input(raw, expected_sha256):
    _hash(expected_sha256, "input")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_FILE_BYTES or sha(raw) != expected_sha256:
        _fail("input_bytes")
    # Inputs have the research canonical terminal LF. Internal controls,
    # response hashes and cloud metadata deliberately remain strict no-LF.
    # Authenticate supplied bytes first; never normalize or silently repin.
    if not raw.endswith(b"\n"):
        _fail("input_canonical_linefeed")
    value = _json(raw[:-1])
    if type(value) is not dict or set(value) != _input_keys(value.get("schema")):
        _fail("input_schema")
    for key, digest in _input_hashes(value).items():
        _hash(digest, key)
    rows = value["rows"]
    if type(rows) is not list or len(rows) != 7:
        _fail("input_census")
    seen, figis = set(), set()
    for row in rows:
        if type(row) is not dict or set(row) != {"ticker", "role", "composite_figi"}:
            _fail("input_row_schema")
        ticker = row["ticker"]
        figi = row["composite_figi"]
        if type(ticker) is not str or ticker not in ROLES or ticker in seen or row["role"] != ROLES[ticker]:
            _fail("input_role_identity")
        if type(figi) is not str or _FIGI.fullmatch(figi) is None or figi in figis:
            _fail("public_figi_identity")
        seen.add(ticker)
        figis.add(figi)
    if seen != set(TICKERS):
        _fail("input_census")
    return value


def render_source(value, input_sha256):
    """Pure one-file public-reference source projection; no market rows."""
    validate_input(canonical_input(value), input_sha256)
    profile, profile_sha256 = _profile(value["schema"])
    rows_by_ticker = {row["ticker"]: row for row in value["rows"]}
    refs = [(ticker, ROLES[ticker], rows_by_ticker[ticker]["composite_figi"]) for ticker in TICKERS]
    # This dictionary is embedded with repr, not canonical JSON. Its order
    # must be independent of the per-process Python hash seed.
    bindings = _input_hashes(value)
    bindings.update({"input_sha256": input_sha256, "input_schema": value["schema"],
                     "source_binding_mode": profile["mode"], "profile_sha256": profile_sha256})
    # A source cannot embed its own byte hash. Its digest with this one
    # manifest field replaced by a declared sentinel binds the runtime
    # projection; exact host upload/readback receipts bind complete bytes.
    bindings["source_template_sha256"] = _SOURCE_TEMPLATE_TOKEN
    template = ('''from AlgorithmImports import *
import json

class ARV2PublicSevenIdentity(QCAlgorithm):
    def initialize(self):
        if self.live_mode:
            raise ValueError("R284 live mode refused")
        self.set_time_zone("America/New_York")
        self.set_start_date(2026, 10, 7)
        self.set_end_date(2026, 10, 7)
        self.set_cash(1000000)
        self.set_benchmark(lambda instant: 1)
        self.settings.seed_initial_prices = False
        refs = ''' + repr(refs) + '''
        self._r284_rows = []
        candidates = []
        for ticker, role, expected_figi in refs:
            reason = "resolution_unavailable"
            sid = None
            try:
                symbol = self.composite_figi(expected_figi)
                if symbol is not None:
                    if symbol.security_type != SecurityType.EQUITY or symbol.id.market != Market.USA:
                        reason = "not_usa_equity"
                    elif self.composite_figi(symbol) != expected_figi:
                        reason = "reverse_figi_mismatch"
                    elif symbol.id is not None:
                        sid = symbol.id
                        reason = "matched"
            except Exception:
                # Never render a remote exception or resolved identifier.
                sid = None
                reason = "mapping_exception"
            self._r284_rows.append({"ticker": ticker, "role": role, "matched": reason == "matched", "reason": reason})
            candidates.append(sid)
        for index, sid in enumerate(candidates):
            if sid is not None:
                try:
                    unique = candidates.count(sid) == 1
                    refusal = "sid_collision"
                except Exception:
                    unique = False
                    refusal = "mapping_exception"
                if not unique:
                    self._r284_rows[index]["matched"] = False
                    self._r284_rows[index]["reason"] = refusal
        self._r284_initialized = True

    def on_end_of_algorithm(self):
        if not getattr(self, "_r284_initialized", False):
            raise ValueError("R284 identity initialization did not complete")
        matched = sum(row["matched"] for row in self._r284_rows)
        meta = ''' + repr({"schema": META_SCHEMA, "candidate_id": CANDIDATE_ID, "attempt": 1,
                           "session": SESSION, **bindings, **_RUNTIME_FALSE_FLAGS}) + '''
        meta.update({"input_count": 7, "matched_count": matched, "refused_count": 7 - matched, "rows": self._r284_rows})
        self.set_summary_statistic("''' + META_NAME + '''", json.dumps(meta, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
''').encode("ascii")
    return template.replace(_SOURCE_TEMPLATE_TOKEN.encode("ascii"), sha(template).encode("ascii"))


def source_template_sha256(source):
    """Authenticate the one explicit self-reference-free template field."""
    marker = re.compile(rb"'source_template_sha256': '([0-9a-f]{64})'")
    matches = list(marker.finditer(source))
    if len(matches) != 1:
        _fail("source_template_field")
    match = matches[0]
    template = source[:match.start(1)] + _SOURCE_TEMPLATE_TOKEN.encode("ascii") + source[match.end(1):]
    actual = sha(template)
    if match.group(1).decode("ascii") != actual:
        _fail("source_template_hash")
    return actual


def _metadata(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink, info.st_size, info.st_mtime_ns


class _Directory:
    """Held no-follow private leaf; every named file is single-linked."""
    def __init__(self, path, create=False):
        if type(path) is not type(Path()) or not path.is_absolute() or ".." in path.parts:
            _fail("control_path")
        root = ARTIFACT_ROOT
        if not path.is_relative_to(root) or path == root:
            _fail("control_root")
        self.path, self.fd = path, None
        self.ancestors = []
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(path.parts[1:], 1):
                if create and Path(*path.parts[:index + 1]).is_relative_to(root):
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = nxt
                part_info = os.fstat(descriptor)
                self.ancestors.append((part_info.st_dev, part_info.st_ino))
            info = os.fstat(descriptor)
            if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
                _fail("private_control_directory")
            self.fd = descriptor
            self.identity = info.st_dev, info.st_ino
        except (OSError, ValueError):
            os.close(descriptor)
            _fail("control_directory")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def _verify(self):
        descriptor = None
        try:
            descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
            for part, identity in zip(self.path.parts[1:], self.ancestors):
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = nxt
                current = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) != identity:
                    _fail("control_directory_changed")
            info = os.fstat(descriptor)
            if (not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != self.identity
                    or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid()
                    or (os.fstat(self.fd).st_dev, os.fstat(self.fd).st_ino) != self.identity):
                _fail("control_directory_changed")
        except OSError:
            _fail("control_directory_changed")
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def names(self):
        self._verify()
        return tuple(os.listdir(self.fd))

    def read(self, name):
        self._verify()
        if type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None:
            _fail("control_name")
        try:
            before = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600
                    or before.st_uid != os.getuid() or before.st_nlink != 1 or not 0 < before.st_size <= MAX_FILE_BYTES):
                _fail("private_file")
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
            try:
                if _metadata(os.fstat(fd)) != _metadata(before):
                    _fail("file_identity_changed")
                raw = bytearray()
                while len(raw) <= MAX_FILE_BYTES:
                    chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                if (len(raw) != before.st_size or _metadata(os.fstat(fd)) != _metadata(before)
                        or _metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) != _metadata(before)):
                    _fail("file_identity_changed")
            finally:
                os.close(fd)
        except OSError:
            _fail("control_read")
        self._verify()
        return bytes(raw)

    def write(self, name, raw):
        self._verify()
        if type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None:
            _fail("control_name")
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_FILE_BYTES:
            _fail("control_write_bound")
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
            try:
                view = memoryview(raw)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        _fail("control_write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(self.fd)
        except OSError:
            _fail("one_use_control_spent_or_write_failed")
        if self.read(name) != raw:
            _fail("control_write_readback")

    def json(self, name):
        return _json(self.read(name))


def prepare(input_path, input_sha256, control_directory):
    """Offline publication; no credentials, clock, provider or QC calls."""
    try:
        before = input_path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= MAX_FILE_BYTES:
            _fail("input_file")
        fd = os.open(input_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if _metadata(os.fstat(fd)) != _metadata(before):
                _fail("input_file_changed")
            raw = os.read(fd, MAX_FILE_BYTES + 1)
            if (len(raw) != before.st_size or _metadata(os.fstat(fd)) != _metadata(before)
                    or _metadata(input_path.lstat()) != _metadata(before)):
                _fail("input_file_changed")
        finally:
            os.close(fd)
    except OSError:
        _fail("input_file")
    value = validate_input(raw, input_sha256)
    profile, profile_sha256 = _profile(value["schema"])
    source = render_source(value, input_sha256)
    prepared = {"schema": PREPARED_SCHEMA, "candidate_id": CANDIDATE_ID, "attempt": 1,
                "control_directory": str(control_directory),
                "input_schema": value["schema"], "profile": profile, "profile_sha256": profile_sha256, "input_sha256": input_sha256,
                "source_sha256": sha(source), "source_byte_count": len(source),
                "source_template_sha256": source_template_sha256(source),
                **_input_hashes(value), **_RUNTIME_FALSE_FLAGS}
    prepared_raw = canonical(prepared)
    with _Directory(control_directory, create=True) as directory:
        if directory.names():
            _fail("prepare_directory_not_empty")
        directory.write("input.json", raw)
        directory.write("main.py", source)
        directory.write("prepared.json", prepared_raw)
        directory.write("prepared.sha256", sha(prepared_raw).encode("ascii"))
        directory.write("prepared-complete.json", canonical({"prepared_sha256": sha(prepared_raw)}))
    return prepared


def _prepared(directory, expected_sha256):
    _hash(expected_sha256, "prepared")
    raw = directory.read("prepared.json")
    if sha(raw) != expected_sha256 or directory.read("prepared.sha256") != expected_sha256.encode("ascii"):
        _fail("prepared_hash")
    if directory.json("prepared-complete.json") != {"prepared_sha256": expected_sha256}:
        _fail("prepared_completion")
    value = _json(raw)
    if type(value) is not dict or value.get("schema") != PREPARED_SCHEMA:
        _fail("prepared_schema")
    input_value = validate_input(directory.read("input.json"), value.get("input_sha256"))
    profile, profile_sha256 = _profile(input_value["schema"])
    source = render_source(input_value, value["input_sha256"])
    expected = {"schema": PREPARED_SCHEMA, "candidate_id": CANDIDATE_ID, "attempt": 1,
                "control_directory": str(directory.path),
                "input_schema": input_value["schema"], "profile": profile, "profile_sha256": profile_sha256, "input_sha256": value["input_sha256"],
                "source_sha256": sha(source), "source_byte_count": len(source),
                "source_template_sha256": source_template_sha256(source),
                **_input_hashes(input_value), **_RUNTIME_FALSE_FLAGS}
    if not _same(value, expected) or directory.read("main.py") != source:
        _fail("prepared_source_or_profile_changed")
    return value, source


def _api(api):
    if api is None:
        api = boundary.production_client()
    boundary._client(api)
    if (type(api) is not QuantConnectClient or api._base_url != API_BASE
            or "request" in vars(api) or api.request.__func__ is not QuantConnectClient.request):
        _fail("client_override")
    return api


def _instant():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _utc(value):
    if type(value) is not str:
        _fail("client_clock")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail("client_clock")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("client_clock")
    return parsed


def _post(directory, api, endpoint, payload, binding):
    """Persist sanitized observations before exposing any fresh response."""
    allowed = {"authenticate", "projects/read", "projects/create", "files/read", "files/delete", "files/update",
               "compile/create", "compile/read", "backtests/create", "backtests/list", "backtests/read"}
    if endpoint not in allowed:
        _fail("endpoint_not_allowed")
    names = directory.names()
    observations = [name for name in names if re.fullmatch(r"observation-\d{3}\.json", name)]
    if len(observations) >= MAX_OBSERVATIONS:
        _fail("observation_budget")
    start, tick = _instant(), time.monotonic_ns()
    start_clock = _utc(start)
    if type(tick) is not int:
        _fail("monotonic_interval")
    response = boundary._post(api, endpoint, payload)
    end, stop = _instant(), time.monotonic_ns()
    if (type(tick) is not int or type(stop) is not int or stop < tick
            or _utc(end) < start_clock):
        _fail("monotonic_interval")
    parsed = canonical(response)
    observation = {"schema": OBSERVATION_SCHEMA, **binding,
                   "endpoint": endpoint, "client_start_utc": start, "client_end_utc": end,
                   "monotonic_elapsed_ns": stop - tick, "wall_clock_ordered": True,
                   "request_sha256": sha(canonical(payload)), "parsed_response_sha256": sha(parsed),
                   "response_hash_encoding": "sorted_compact_ascii_json_strict_v1",
                   "server_time_authenticated": False, "operator_authenticated": False}
    for key in ("projectId", "compileId", "backtestId"):
        if key in payload:
            observation[key] = payload[key]
    directory.write(f"observation-{len(observations) + 1:03d}.json", canonical(observation))
    return response


def _project(response, project_id, name=None, organization=None, fresh=False):
    rows = response.get("projects")
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        _fail("project_response")
    row = rows[0]
    actual_id = row.get("projectId")
    org = row.get("organizationId")
    if (type(actual_id) is not int or actual_id <= 0 or (project_id is not None and actual_id != project_id)
            or type(org) is not str or re.fullmatch(r"[0-9a-f]{32}", org) is None
            or row.get("owner") is not True or (name is not None and row.get("name") != name)
            or (organization is not None and org != organization)):
        _fail("project_identity")
    if fresh:
        collaborators = row.get("collaborators")
        if (row.get("codeRunning") is not False or type(collaborators) is not list or len(collaborators) > 1
                or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)):
            _fail("project_private_idle")
    return actual_id, org


def _files(response):
    rows = response.get("files")
    if type(rows) is not list or any(type(row) is not dict or type(row.get("name")) is not str for row in rows):
        _fail("file_inventory")
    if len({row["name"] for row in rows}) != len(rows):
        _fail("file_inventory")
    return {row["name"]: row.get("content") for row in rows}


def _bind(prepared, prepared_sha256):
    profile, profile_sha256 = _profile(prepared["input_schema"])
    return {"candidate_id": CANDIDATE_ID, "attempt": 1, "prepared_sha256": prepared_sha256,
            "input_schema": prepared["input_schema"], "source_binding_mode": profile["mode"],
            "input_sha256": prepared["input_sha256"], "source_sha256": prepared["source_sha256"],
            "source_template_sha256": prepared["source_template_sha256"],
            "profile_sha256": profile_sha256,
            **{key: prepared[key] for key in sorted(_input_keys(prepared["input_schema"]) - {"schema", "rows"})},
            **_RUNTIME_FALSE_FLAGS}


def launch(control_directory, prepared_sha256, api=None):
    """One attempt; compile/transport ambiguity leaves its claim spent."""
    with _Directory(control_directory) as directory:
        prepared, source = _prepared(directory, prepared_sha256)
        binding = _bind(prepared, prepared_sha256)
        directory.write("attempt-claim.json", canonical({**binding, "claimed_at_utc": _instant()}))
        api = _api(api)
        _post(directory, api, "authenticate", {}, binding)
        _, organization = _project(_post(directory, api, "projects/read", {"projectId": REFERENCE_PROJECT_ID}, binding), REFERENCE_PROJECT_ID)
        project_id, _ = _project(_post(directory, api, "projects/create", {"name": PROJECT_NAME, "language": "Py", "organizationId": organization}, binding), None, PROJECT_NAME, organization)
        if project_id == REFERENCE_PROJECT_ID:
            _fail("new_project_reused_reference_id")
        directory.write("project-created.json", canonical({**binding, "project_id": project_id, "organization_id": organization}))
        _project(_post(directory, api, "projects/read", {"projectId": project_id}, binding), project_id, PROJECT_NAME, organization, fresh=True)
        initial = _files(_post(directory, api, "files/read", {"projectId": project_id}, binding))
        if "main.py" not in initial or set(initial) - {"main.py", "research.ipynb"}:
            _fail("new_project_defaults")
        if "research.ipynb" in initial:
            _post(directory, api, "files/delete", {"projectId": project_id, "name": "research.ipynb"}, binding)
        _post(directory, api, "files/update", {"projectId": project_id, "name": "main.py", "content": source.decode("ascii")}, binding)
        if _files(_post(directory, api, "files/read", {"projectId": project_id}, binding)) != {"main.py": source.decode("ascii")}:
            _fail("cloud_source_readback")
        compile_response = _post(directory, api, "compile/create", {"projectId": project_id}, binding)
        compile_id = compile_response.get("compileId")
        if (type(compile_id) is not str or _ID.fullmatch(compile_id) is None
                or type(compile_response.get("projectId")) is not int or compile_response["projectId"] != project_id):
            _fail("compile_id")
        directory.write("compile-created.json", canonical({**binding, "project_id": project_id, "compile_id": compile_id}))
        for ordinal in range(MAX_COMPILE_POLLS):
            response = _post(directory, api, "compile/read", {"projectId": project_id, "compileId": compile_id}, binding)
            if (("projectId" in response and (type(response["projectId"]) is not int or response["projectId"] != project_id)) or response.get("compileId") != compile_id
                    or response.get("state") not in {"InQueue", "BuildSuccess", "BuildError"}):
                _fail("compile_response_identity")
            if response["state"] == "BuildError":
                directory.write("compile-failure.json", canonical({**binding, "project_id": project_id, "compile_id": compile_id, "status": "BuildError"}))
                _fail("compile_failed")
            if response["state"] == "BuildSuccess":
                break
            if ordinal + 1 < MAX_COMPILE_POLLS:
                time.sleep(2)
        else:
            _fail("compile_poll_budget")
        # A fresh owned project is still subject to concurrent owner edits.
        # Refuse visible source changes after compilation, before launch.
        if _files(_post(directory, api, "files/read", {"projectId": project_id}, binding)) != {"main.py": source.decode("ascii")}:
            _fail("cloud_source_changed_after_compile")
        directory.write("backtest-create-claim.json", canonical({**binding, "project_id": project_id, "compile_id": compile_id}))
        response = _post(directory, api, "backtests/create", {"projectId": project_id, "compileId": compile_id, "backtestName": BACKTEST_NAME}, binding)
        row = response.get("backtest")
        if (type(row) is not dict or type(row.get("projectId")) is not int or row.get("projectId") != project_id or row.get("name") != BACKTEST_NAME
                or type(row.get("backtestId")) is not str or _ID.fullmatch(row["backtestId"]) is None
                or row.get("status") not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}):
            _fail("backtest_create_identity")
        receipt = {**binding, "project_id": project_id, "compile_id": compile_id,
                   "backtest_id": row["backtestId"], "backtest_name": BACKTEST_NAME}
        directory.write("launch.json", canonical(receipt))
        return receipt


def _launch(directory, prepared, prepared_sha256):
    binding = _bind(prepared, prepared_sha256)
    claim = directory.json("attempt-claim.json")
    receipt = directory.json("launch.json")
    if (not _bound(claim, binding) or set(claim) != set(binding) | {"claimed_at_utc"}
            or type(claim["claimed_at_utc"]) is not str):
        _fail("attempt_claim_binding")
    if (type(receipt) is not dict or set(receipt) != set(binding) | {"project_id", "compile_id", "backtest_id", "backtest_name"}
            or not _bound(receipt, binding) or receipt["backtest_name"] != BACKTEST_NAME
            or type(receipt["project_id"]) is not int or receipt["project_id"] <= 0
            or any(type(receipt[key]) is not str or _ID.fullmatch(receipt[key]) is None for key in ("compile_id", "backtest_id"))):
        _fail("launch_binding")
    created = directory.json("project-created.json")
    compiled = directory.json("compile-created.json")
    backtest_claim = directory.json("backtest-create-claim.json")
    if (type(created) is not dict or set(created) != set(binding) | {"project_id", "organization_id"}
            or type(created.get("project_id")) is not int or created.get("project_id") != receipt["project_id"]
            or type(created.get("organization_id")) is not str or re.fullmatch(r"[0-9a-f]{32}", created["organization_id"]) is None
            or not _bound(created, binding)
            or not _same(compiled, {**binding, "project_id": receipt["project_id"], "compile_id": receipt["compile_id"]})
            or not _same(backtest_claim, compiled)):
        _fail("launch_source_chain")
    return receipt


def status(control_directory, prepared_sha256, api=None):
    """One bounded statistics-disabled observation, or cached terminal."""
    with _Directory(control_directory) as directory:
        prepared, _ = _prepared(directory, prepared_sha256)
        receipt = _launch(directory, prepared, prepared_sha256)
        if "terminal.json" in directory.names():
            terminal = directory.json("terminal.json")
            if (type(terminal) is not dict or not _same(terminal, {**receipt, "status": terminal.get("status")})
                    or terminal["status"] not in {"Completed.", "Runtime Error"}):
                _fail("terminal_binding")
            return terminal
        polls = [name for name in directory.names() if re.fullmatch(r"status-claim-\d{3}\.json", name)]
        if len(polls) >= MAX_STATUS_POLLS:
            _fail("status_poll_budget")
        directory.write(f"status-claim-{len(polls) + 1:03d}.json", canonical(receipt))
        api = _api(api)
        response = _post(directory, api, "backtests/list", {"projectId": receipt["project_id"], "includeStatistics": False}, _bind(prepared, prepared_sha256))
        rows = response.get("backtests")
        if (type(rows) is not list or len(rows) != 1 or any(type(row) is not dict for row in rows)
                or ("count" in response and (type(response["count"]) is not int or response["count"] != len(rows)))):
            _fail("status_inventory")
        matches = [row for row in rows if row.get("backtestId") == receipt["backtest_id"]]
        if len(matches) != 1:
            _fail("status_run_identity")
        row = matches[0]
        if (row.get("name") != BACKTEST_NAME or ("projectId" in row and (type(row["projectId"]) is not int or row["projectId"] != receipt["project_id"]))
                or row.get("status") not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}):
            _fail("status_run_identity")
        result = {**receipt, "status": row["status"]}
        if row["status"] in {"Completed.", "Runtime Error"}:
            directory.write("terminal.json", canonical(result))
        return result


def validate_meta(raw, prepared):
    if type(raw) is not str or not raw.isascii() or not 0 < len(raw) <= MAX_META_BYTES:
        _fail("metadata_bytes")
    value = _json(raw.encode("ascii"))
    profile, profile_sha256 = _profile(prepared["input_schema"])
    expected = {"schema": META_SCHEMA, "candidate_id": CANDIDATE_ID, "attempt": 1, "session": SESSION,
                "input_sha256": prepared["input_sha256"], "input_schema": prepared["input_schema"],
                "source_binding_mode": profile["mode"], "profile_sha256": profile_sha256,
                "source_template_sha256": prepared["source_template_sha256"],
                **{key: prepared[key] for key in sorted(_input_keys(prepared["input_schema"]) - {"schema", "rows"})}, **_RUNTIME_FALSE_FLAGS}
    if (type(value) is not dict or set(value) != set(expected) | {"input_count", "matched_count", "refused_count", "rows"}
            or not _bound(value, expected) or value["input_count"] != 7
            or any(type(value[key]) is not int or not 0 <= value[key] <= 7 for key in ("input_count", "matched_count", "refused_count"))):
        _fail("metadata_binding")
    rows = value["rows"]
    if type(rows) is not list or len(rows) != 7:
        _fail("metadata_census")
    for index, row in enumerate(rows):
        if (type(row) is not dict or set(row) != {"ticker", "role", "matched", "reason"}
                or row["ticker"] != TICKERS[index] or row["role"] != ROLES[TICKERS[index]]
                or type(row["matched"]) is not bool or type(row["reason"]) is not str or row["reason"] not in _REASONS
                or row["matched"] != (row["reason"] == "matched")):
            _fail("metadata_row")
    count = sum(row["matched"] for row in rows)
    if value["matched_count"] != count or value["refused_count"] != 7 - count:
        _fail("metadata_counts")
    return value


def read(control_directory, prepared_sha256, api=None):
    """Exactly one custom-metadata read; every failure spends its claim."""
    with _Directory(control_directory) as directory:
        prepared, _ = _prepared(directory, prepared_sha256)
        receipt = _launch(directory, prepared, prepared_sha256)
        if not _same(directory.json("terminal.json"), {**receipt, "status": "Completed."}):
            _fail("result_not_completed")
        directory.write("result-read-claim.json", canonical(receipt))
        api = _api(api)
        response = _post(directory, api, "backtests/read", {"projectId": receipt["project_id"], "backtestId": receipt["backtest_id"]}, _bind(prepared, prepared_sha256))
        row = response.get("backtest")
        if (type(row) is not dict or type(row.get("projectId")) is not int or row.get("projectId") != receipt["project_id"]
                or row.get("backtestId") != receipt["backtest_id"] or row.get("name") != BACKTEST_NAME
                or row.get("status") != "Completed." or row.get("hasInitializeError", False) is not False
                or row.get("completed", True) is not True or row.get("error", "") not in ("", None)
                or type(row.get("statistics")) is not dict):
            _fail("result_run_identity")
        meta = validate_meta(row["statistics"].get(META_NAME), prepared)
        result = {**receipt, "metadata": meta, "metadata_sha256": sha(canonical(meta)), **_RUNTIME_FALSE_FLAGS}
        directory.write("result.json", canonical(result))
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "launch", "status", "read"))
    parser.add_argument("--control-directory", required=True, type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--input-sha256")
    parser.add_argument("--prepared-sha256")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            if args.input is None or args.input_sha256 is None or args.prepared_sha256 is not None:
                _fail("prepare_arguments")
            value = prepare(args.input, args.input_sha256, args.control_directory)
            output = {"candidate_id": CANDIDATE_ID, "prepared_sha256": sha(canonical(value)),
                      "source_sha256": value["source_sha256"], "input_count": 7,
                      "input_schema": value["input_schema"], "profile_sha256": value["profile_sha256"],
                      "source_binding_mode": value["profile"]["mode"], **_RUNTIME_FALSE_FLAGS}
        else:
            if args.prepared_sha256 is None or args.input is not None or args.input_sha256 is not None:
                _fail("action_arguments")
            value = {"launch": launch, "status": status, "read": read}[args.action](args.control_directory, args.prepared_sha256)
            output = {key: value[key] for key in ("candidate_id", "attempt", "project_id", "compile_id", "backtest_id")}
            output.update({key: value[key] for key in ("input_schema", "profile_sha256", "source_binding_mode")})
            output.update(_RUNTIME_FALSE_FLAGS)
            if "status" in value:
                output["status"] = value["status"]
            if "metadata" in value:
                output.update({key: value["metadata"][key] for key in ("matched_count", "refused_count", "rows")})
                output["metadata_sha256"] = value["metadata_sha256"]
        print(canonical(output).decode("ascii"))
        return 0
    except IdentityQcError as error:
        # All refusal codes originate locally, not from platform messages.
        message = str(error)
        if re.fullmatch(r"R284 refused: [a-z0-9_]+", message) is None:
            message = "R284 operation refused"
        print(message + "; existing one-use claims remain spent")
        return 2
    except Exception:
        # Do not render provider exceptions, payloads, raw identifiers, API
        # headers, credentials or licensed values in an operator traceback.
        print("R284 operation refused; existing one-use claims remain spent")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
