"""One registered Sharadar stock-date metadata slice; never prices or returns.

The owner authorized price/delisting coverage qualification, with QC held.
Only ticker/date/lastupdated are requested for the immutable offline probe
plan's finite symbols and the declared 2005-01-01..2026-06-30 availability
window. This is not a change to the frozen study window, a price archive,
paid bulk entitlement proof, PIT admission, an outcome look or readiness.

Production anchors must be populated from the actual prior offline run and
committed before this CLI is activated. The fixed namespace cannot resume,
retry or rename a consumed scope. Tests require process-tree network denial
and invented outside-lane credential readers and transports.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import re
import ssl
import stat
from urllib import error, parse, request

from research import insider_buying_earnings_archive_assessment_runner as custody
from research.insider_buying_eodhd_earnings_demo import FALSE_FLAGS
from research.insider_buying_keychain_credentials import KeychainCredential, read_keychain_credential
from research.insider_buying_provider_metadata_audit import _now
from research.insider_buying_provider_metadata_transport import ProviderMetadataResponse, _DenyRedirect
from research.insider_buying_sharadar_reference_qualification import _screen_credential


LANE_ROOT = custody.LANE_ROOT
LANE_BRANCH = custody.LANE_BRANCH
SCHEMA = "insider-sharadar-stock-date-metadata-capture-v1"
PROFILE = "sharadar-stocks-frozen-probe-plan-date-metadata-v1"
OWNER_DIRECTION = "owner:2026-10-24:sharadar-price-delisting-and-retained-earnings-qualification-no-qc"
OUTPUT_PARTS = ("artifacts", "insider_buying", "sharadar_price_coverage_v1")
AUDIT_ID = "ib-sharadar-price-metadata-coverage-20261024-once"
PLAN_PARTS = ("artifacts", "insider_buying", "sharadar_delisting_qualification_v1",
              "ib-sharadar-delisting-qualification-20261024-once")
PLAN_SCHEMA = "insider-sharadar-sep-dates-probe-plan-v1"
PLAN_AUDIT_ID = PLAN_PARTS[-1]
OFFLINE_SCHEMA = "insider-sharadar-delisting-qualification-v1"
CAPTURE_MANIFEST_SHA256 = "94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b"
# MAIN must replace all three None values with the observed, byte-bound
# offline completion/plan/qualification hashes before real activation.
PLAN_SHA256 = None
OFFLINE_COMPLETE_SHA256 = None
QUALIFICATION_SHA256 = None
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_PLAN_BYTES = 4 * 1024 * 1024
MAX_QUALIFICATION_BYTES = 512 * 1024 * 1024
TIMEOUT_SECONDS = 15
ROW_LIMIT = 100000
FROM = "2005-01-01"
TO = "2026-06-30"
COLUMNS = ("ticker", "date", "lastupdated")
CASE_ORDER = ("active_common", "delisted_common", "secondary_common", "ticker_reuse_related")
CASE_LABELS = frozenset(CASE_ORDER)
PRICE_TABLES = frozenset({"stocks", "SEP"})
READINESS_KEYS = tuple(dict.fromkeys((*FALSE_FLAGS, "backtesting_ready", "pit_identity_verified")))
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-^/=]{0,63}\Z")
_CODES = frozenset({"unsupported-content-encoding", "invalid-content-length", "oversized-response",
    "truncated-response", "partial-read", "redirect-refused", "invalid-http-status",
    "response-origin-mismatch", "transport-timeout", "transport-error"})


class PriceCoverageError(ValueError):
    """Fixed refusal codes only; never source/credential/HTTP/OS text."""


def _need(condition, code):
    if not condition:
        raise PriceCoverageError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, "input_anchor_required")
    return value


def _json(raw):
    def unique(items):
        body = {}
        for key, value in items:
            _need(key not in body, "duplicate_input_key")
            body[key] = value
        return body
    try:
        body = json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: _need(False, "nonfinite_input"))
        _need(type(body) is dict and _canonical(body) == raw, "canonical_input_required")
        return body
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, OverflowError):
        raise PriceCoverageError("input_json_refused") from None


def _version(info):
    # macOS can update ctime for UF_TRACKED after creation. Every check below
    # instead rehashes all held leaves, while binding inode/mode/owner/mtime.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_size, info.st_mtime_ns)


def _leaf(directory, name, cap):
    before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    _need(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
          and before.st_nlink == 1 and before.st_uid == os.geteuid()
          and 0 < before.st_size <= cap, "private_leaf_custody_refused")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        _need(_version(before) == _version(os.fstat(stream.fileno())), "private_leaf_substituted")
        raw = stream.read(cap + 1)
        _need(len(raw) == before.st_size and _version(before) == _version(os.fstat(stream.fileno()))
              and _version(before) == _version(os.stat(name, dir_fd=directory, follow_symlinks=False)),
              "private_leaf_changed")
    return raw, _version(before)


def _stream_leaf_digest(directory, name, cap):
    """Bind the private quality report without decoding or retaining its rows."""
    before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    _need(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
          and before.st_nlink == 1 and before.st_uid == os.geteuid()
          and 0 < before.st_size <= cap, "private_leaf_custody_refused")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        version = _version(before)
        _need(version == _version(os.fstat(stream.fileno())), "private_leaf_substituted")
        digest, count = hashlib.sha256(), 0
        while part := stream.read(1024 * 1024):
            count += len(part)
            _need(count <= cap and count <= before.st_size, "private_leaf_changed")
            digest.update(part)
        _need(count == before.st_size and version == _version(os.fstat(stream.fileno()))
              and version == _version(os.stat(name, dir_fd=directory, follow_symlinks=False)),
              "private_leaf_changed")
    return digest.hexdigest(), version


@dataclass(frozen=True, slots=True)
class FixtureAnchors:
    plan_sha256: str
    complete_sha256: str
    qualification_sha256: str


def _production_anchors():
    return FixtureAnchors(_digest(PLAN_SHA256), _digest(OFFLINE_COMPLETE_SHA256),
                          _digest(QUALIFICATION_SHA256))


def _identity(expected_head, *, root=LANE_ROOT):
    _need(root == LANE_ROOT, "designated_lane_required")
    value = custody._identity(expected_head)
    _need("research/insider_buying_sharadar_price_coverage_capture.py" in value["source_sha256"]
          and "research/insider_buying_keychain_credentials.py" in value["source_sha256"],
          "source_closure_incomplete")
    return value


def _false_readiness(value):
    _need(type(value) is dict and set(value) == set(READINESS_KEYS)
          and all(type(item) is bool and item is False for item in value.values()),
          "input_readiness_refused")


def _request_profile(tickers):
    return {"dataset": "stocks", "format": "csv", "ticker": ",".join(tickers),
        "date_gte": FROM, "date_lte": TO, "fields": list(COLUMNS), "sort": "date.asc",
        "limit": ROW_LIMIT, "maximum_attempts": 1}


def _url(tickers):
    return "https://api.sharadar.com/v1.0/data/stocks?" + parse.urlencode({
        "format": "csv", "ticker": ",".join(tickers), "from": FROM, "to": TO,
        "fields": ",".join(COLUMNS), "sort": "date.asc", "limit": str(ROW_LIMIT)}, safe=",")


def _validate_plan(plan, complete, qualification_sha, fixture):
    _need(set(plan) == {"schema", "audit_id", "execution_identity", "source_inventory_sha256",
        "capture_manifest_sha256", "source_archives", "cases", "unavailable_cases", "requested_tickers",
        "request", "metadata_discovery_only", "early_buffer_is_availability_probe_only", "readiness"},
        "probe_plan_schema_refused")
    _need(set(complete) == {"schema", "audit_id", "fixture_only", "execution_identity",
        "source_inventory_sha256", "capture_manifest_sha256", "source_archives", "qualification_sha256",
        "plan_sha256", "counts", "effective_process_tree_network_denial", "effective_process_fork_denial",
        "effective_keychain_exec_denial", "writes_confined_to_fresh_output_by_launcher", "provider_dispatches", "credential_reads",
        "fundamentals_decoded", "price_or_return_values_read", "looks_jobs_backtests", "readiness"},
        "offline_completion_schema_refused")
    _need(plan["schema"] == PLAN_SCHEMA and plan["audit_id"] == PLAN_AUDIT_ID
          and complete["schema"] == OFFLINE_SCHEMA and complete["audit_id"] == PLAN_AUDIT_ID
          and complete["fixture_only"] is fixture and plan["metadata_discovery_only"] is True
          and plan["early_buffer_is_availability_probe_only"] is True
          and complete["qualification_sha256"] == qualification_sha, "offline_profile_refused")
    _need(complete["effective_process_tree_network_denial"] is True, "offline_isolation_not_observed")
    for name in ("effective_process_fork_denial", "effective_keychain_exec_denial",
                 "writes_confined_to_fresh_output_by_launcher"):
        _need(complete[name] is (not fixture), "offline_isolation_not_observed")
    _need(type(complete["provider_dispatches"]) is int and complete["provider_dispatches"] == 0
          and type(complete["credential_reads"]) is int and complete["credential_reads"] == 0
          and complete["fundamentals_decoded"] is False and complete["price_or_return_values_read"] is False
          and complete["looks_jobs_backtests"] == [0, 0, 0]
          and all(type(value) is int for value in complete["looks_jobs_backtests"]), "offline_exclusions_refused")
    _false_readiness(plan["readiness"]); _false_readiness(complete["readiness"])
    _need(plan["capture_manifest_sha256"] == complete["capture_manifest_sha256"] == CAPTURE_MANIFEST_SHA256
          and plan["execution_identity"] == complete["execution_identity"]
          and plan["source_archives"] == complete["source_archives"]
          and plan["source_inventory_sha256"] == complete["source_inventory_sha256"], "offline_binding_refused")
    identity = plan["execution_identity"]
    _need(type(identity) is dict and set(identity) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
          and identity["root"] == str(LANE_ROOT) and identity["branch"] == LANE_BRANCH
          and identity["clean"] is True and type(identity["head"]) is str
          and re.fullmatch(r"[0-9a-f]{40}", identity["head"]) is not None
          and type(identity["source_sha256"]) is dict and identity["source_sha256"], "offline_identity_refused")
    _need(all(type(name) is str and name.endswith(".py") and not Path(name).is_absolute()
              and ".." not in Path(name).parts and _digest(digest) for name, digest in identity["source_sha256"].items())
          and _sha(_canonical(identity["source_sha256"])) == identity["source_inventory_sha256"]
          == plan["source_inventory_sha256"], "offline_source_inventory_refused")
    archives = plan["source_archives"]
    _need(type(archives) is dict and set(archives) == {"tickers", "actions"}, "offline_archives_refused")
    for item in archives.values():
        _need(type(item) is dict and set(item) == {"archive_sha256", "archive_bytes", "member_sha256", "member_bytes", "source_row_count"},
              "offline_archives_refused")
        _digest(item["archive_sha256"]); _digest(item["member_sha256"])
        _need(all(type(item[name]) is int and 0 < item[name] <= 16 * 1024**3
                  for name in ("archive_bytes", "member_bytes"))
              and type(item["source_row_count"]) is int and 0 < item["source_row_count"] <= 2_000_000,
              "offline_archives_refused")
    tickers, cases = plan["requested_tickers"], plan["cases"]
    _need(type(tickers) is list and 1 <= len(tickers) <= 6
          and all(type(value) is str and _SYMBOL.fullmatch(value) is not None for value in tickers)
          and tickers == sorted(set(tickers)) and type(cases) is list and 1 <= len(cases) <= 6,
          "finite_probe_symbols_required")
    labels = []
    for case in cases:
        _need(type(case) is dict and set(case) == {"case_label", "current_ticker", "permaticker", "source_row_ordinal", "table"}
              and case["case_label"] in CASE_LABELS and case["current_ticker"] in tickers
              and type(case["permaticker"]) is str and re.fullmatch(r"[0-9]{1,20}", case["permaticker"]) is not None
              and int(case["permaticker"]) > 0
              and type(case["source_row_ordinal"]) is int and 0 < case["source_row_ordinal"] <= archives["tickers"]["source_row_count"]
              and case["table"] in PRICE_TABLES, "probe_case_schema_refused")
        labels.append(case["case_label"])
    _need(len(labels) == len(set(labels)) and labels == [label for label in CASE_ORDER if label in labels]
          and tickers == sorted({case["current_ticker"] for case in cases})
          and type(plan["unavailable_cases"]) is list
          and all(type(label) is str for label in plan["unavailable_cases"])
          and plan["unavailable_cases"] == [label for label in CASE_ORDER if label not in labels]
          and type(plan["request"]) is dict
          and type(plan["request"].get("maximum_attempts")) is int
          and type(plan["request"].get("limit")) is int
          and plan["request"] == _request_profile(tickers), "probe_case_request_binding_refused")
    counts = complete["counts"]
    _need(type(counts) is dict and set(counts) == {"ticker_rows", "ticker_refusal_rows", "action_rows",
              "numeric_values_validated", "unresolved_election_rows", "planned_tickers"}
          and all(type(value) is int and 0 <= value <= 2_000_000 for value in counts.values())
          and counts["ticker_rows"] == archives["tickers"]["source_row_count"]
          and counts["action_rows"] == archives["actions"]["source_row_count"]
          and counts["ticker_refusal_rows"] <= counts["ticker_rows"]
          and counts["numeric_values_validated"] <= counts["action_rows"]
          and counts["unresolved_election_rows"] <= counts["action_rows"]
          and counts["planned_tickers"] == len(tickers), "offline_counts_refused")
    return tickers


class _Plan:
    def __init__(self, root, anchors, fixture):
        _need(type(anchors) is FixtureAnchors, "input_anchor_required")
        self.expected = {"probe-plan.json": (_digest(anchors.plan_sha256), MAX_PLAN_BYTES),
            "complete.json": (_digest(anchors.complete_sha256), MAX_PLAN_BYTES),
            "qualification.json": (_digest(anchors.qualification_sha256), MAX_QUALIFICATION_BYTES)}
        self.chain = custody._Chain(root, PLAN_PARTS)
        self.versions = {}
        try:
            self.check()
            self.plan = _json(_leaf(self.chain.fd, "probe-plan.json", MAX_PLAN_BYTES)[0])
            complete = _json(_leaf(self.chain.fd, "complete.json", MAX_PLAN_BYTES)[0])
            _need(complete.get("plan_sha256") == anchors.plan_sha256, "offline_plan_hash_mismatch")
            self.tickers = _validate_plan(self.plan, complete, anchors.qualification_sha256, fixture)
            self.binding = {"plan_sha256": anchors.plan_sha256, "complete_sha256": anchors.complete_sha256,
                "qualification_sha256": anchors.qualification_sha256,
                "capture_manifest_sha256": self.plan["capture_manifest_sha256"],
                "source_inventory_sha256": self.plan["source_inventory_sha256"],
                "source_archives": self.plan["source_archives"], "execution_identity": self.plan["execution_identity"],
                "custody_versions": {name: list(version) for name, version in self.versions.items()}}
            self.check()
        except BaseException:
            self.chain.close(); raise

    def check(self):
        self.chain.recheck()
        info = os.fstat(self.chain.fd)
        _need(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid()
              and set(os.listdir(self.chain.fd)) == set(self.expected), "offline_directory_custody_refused")
        for name, (digest, cap) in self.expected.items():
            if name == "qualification.json":
                observed, version = _stream_leaf_digest(self.chain.fd, name, cap)
            else:
                raw, version = _leaf(self.chain.fd, name, cap)
                observed = _sha(raw)
            _need(observed == digest and (name not in self.versions or self.versions[name] == version),
                  "offline_input_changed")
            self.versions[name] = version
        self.chain.recheck()

    def close(self):
        self.chain.close()


def _publish_raw(directory, name, raw):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES, "publication_bound_refused")
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as stream:
        _need(stream.write(raw) == len(raw), "publication_short_write")
        stream.flush(); os.fsync(stream.fileno())
        version = _version(os.fstat(stream.fileno()))
    os.fsync(directory)
    _need(version == _version(os.stat(name, dir_fd=directory, follow_symlinks=False)),
          "published_leaf_substituted")
    return _sha(raw), version


class _Context:
    def __init__(self, root, fixture, expected_head, identity, baseline, inputs):
        self.root, self.fixture, self.expected_head = root, fixture, expected_head
        self.identity, self.baseline, self.inputs = identity, baseline, inputs
        self.parent = self.directory = None
        self.published, self.versions = {}, {}
        self.url = _url(inputs.tickers)
        try:
            self.parent = custody._Chain(root, OUTPUT_PARTS, create=True)
            _need(os.fstat(self.parent.fd).st_uid == os.geteuid() and not os.listdir(self.parent.fd),
                  "consumed_or_ambiguous_scope_refused")
            self.latch_sha, self.latch_version = _publish_raw(self.parent.fd, "scope-reservation.json", _canonical({
                "schema": SCHEMA, "audit_id": AUDIT_ID, "profile": PROFILE, "method": "GET", "url": self.url,
                "maximum_attempts": 1, "retry_resume_redirect_paging_permitted": False}))
            os.mkdir(AUDIT_ID, 0o700, dir_fd=self.parent.fd); os.fsync(self.parent.fd)
            self.directory = custody._Chain(root, (*OUTPUT_PARTS, AUDIT_ID))
            self.check()
        except BaseException:
            self.close(); raise

    def check(self):
        _need(self.identity(self.expected_head, root=self.root) == self.baseline, "lane_changed_during_capture")
        self.inputs.check(); self.parent.recheck(); self.directory.recheck()
        _need(set(os.listdir(self.parent.fd)) == {"scope-reservation.json", AUDIT_ID}
              and set(os.listdir(self.directory.fd)) == set(self.published)
              and os.fstat(self.directory.fd).st_uid == os.geteuid(), "output_inventory_changed")
        raw, version = _leaf(self.parent.fd, "scope-reservation.json", MAX_PLAN_BYTES)
        _need(_sha(raw) == self.latch_sha and version == self.latch_version, "scope_reservation_changed")
        for name, digest in self.published.items():
            raw, version = _leaf(self.directory.fd, name, MAX_BODY_BYTES)
            _need(_sha(raw) == digest and version == self.versions[name], "published_output_changed")
        self.parent.recheck(); self.directory.recheck()

    def publish(self, name, body, *, raw=False):
        self.check()
        encoded = body if raw else _canonical(body)
        self.published[name], self.versions[name] = _publish_raw(self.directory.fd, name, encoded)
        self.check()

    def close(self):
        if self.directory is not None:
            self.directory.close(); self.directory = None
        if self.parent is not None:
            self.parent.close(); self.parent = None


def _read_bounded(stream, status):
    try:
        _need(callable(getattr(stream.headers, "get_all", None)), "partial-read")
        enc = stream.headers.get_all("Content-Encoding", [])
        lengths = stream.headers.get_all("Content-Length", [])
        transfers = stream.headers.get_all("Transfer-Encoding", [])
        _need(all(type(items) is list and all(type(item) is str for item in items)
                  for items in (enc, lengths, transfers)), "partial-read")
        _need(len(enc) <= 1 and (not enc or enc[0].strip().lower() == "identity"), "unsupported-content-encoding")
        _need(len(lengths) <= 1, "invalid-content-length")
        _need(len(transfers) <= 1 and (not transfers or not lengths and transfers[0].strip().lower() == "chunked"), "partial-read")
        length = None
        if lengths:
            _need(re.fullmatch(r"[0-9]{1,20}", lengths[0]) is not None, "invalid-content-length")
            length = int(lengths[0]); _need(length <= MAX_BODY_BYTES, "oversized-response")
        pieces, count = [], 0
        while count <= MAX_BODY_BYTES:
            requested = min(65536, MAX_BODY_BYTES + 1 - count)
            part = stream.read(requested)
            _need(type(part) is bytes and len(part) <= requested, "partial-read")
            if not part:
                _need(length is None or count == length, "truncated-response")
                return ProviderMetadataResponse(status, b"".join(pieces), True)
            pieces.append(part); count += len(part)
        raise PriceCoverageError("oversized-response")
    except PriceCoverageError as exc:
        return ProviderMetadataResponse(status, b"", False, str(exc))
    except Exception:
        return ProviderMetadataResponse(status, b"", False, "partial-read")


def _default_transport(url, credential, *, context):
    _need(type(context) is _Context and context.root == LANE_ROOT and context.fixture is False,
          "real_capture_context_required")
    _need(type(credential) is KeychainCredential and credential.provider == "sharadar"
          and credential.fixture_only is False and url == context.url == _url(context.inputs.tickers),
          "fixed_transport_profile_refused")
    context.check()
    _need(set(context.published) == {"reservation.json", "credential-read-started.json",
        "credential-read-completed.json", "01-stocks-started.json"}, "observed_start_journal_required")
    reservation = _json(_leaf(context.directory.fd, "reservation.json", MAX_BODY_BYTES)[0])
    started = _json(_leaf(context.directory.fd, "01-stocks-started.json", MAX_BODY_BYTES)[0])
    read = _json(_leaf(context.directory.fd, "credential-read-completed.json", MAX_BODY_BYTES)[0])
    _need(reservation["schema"] == SCHEMA and reservation["fixture_only"] is False
          and reservation["identity"] == context.baseline and reservation["inputs"] == context.inputs.binding
          and reservation["url"] == url and reservation["maximum_attempts"] == 1
          and started == {"schema": SCHEMA, "profile": PROFILE, "method": "GET", "url": url,
              "maximum_attempts": 1, "reservation_sha256": context.published["reservation.json"]}
          and read["schema"] == SCHEMA and read["credential_read_observed"] is True
          and read["fixture_only"] is False and read["started_sha256"] == context.published["credential-read-started.json"],
          "observed_start_journal_required")
    context.check()
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                  request.HTTPSHandler(context=ssl.create_default_context()))
    stream = None
    try:
        try:
            stream = opener.open(request.Request(url, headers={"Accept": "text/csv", "Accept-Encoding": "identity",
                "x-api-key": credential.value}, method="GET"), timeout=TIMEOUT_SECONDS)
        except error.HTTPError as exc:
            stream = exc
        status = stream.getcode()
        if type(status) is not int or not 100 <= status <= 599:
            return ProviderMetadataResponse(None, b"", False, "invalid-http-status")
        if stream.geturl() != url:
            return ProviderMetadataResponse(status, b"", False, "response-origin-mismatch")
        if status != 200:
            return ProviderMetadataResponse(status, b"", False,
                "redirect-refused" if 300 <= status < 400 else None)
        return _read_bounded(stream, status)
    except TimeoutError:
        return ProviderMetadataResponse(None, b"", False, "transport-timeout")
    except error.URLError as exc:
        return ProviderMetadataResponse(None, b"", False,
            "transport-timeout" if isinstance(exc.reason, TimeoutError) else "transport-error")
    except Exception:
        return ProviderMetadataResponse(None, b"", False, "transport-error")
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def _csv_projection(raw, tickers, credential):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES, "csv_resource_refused")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise PriceCoverageError("csv_decode_refused") from None
    try:
        _screen_credential(raw, {"body": text}, credential)
    except ValueError:
        raise PriceCoverageError("credential_echo_refused") from None
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        _need(next(reader) == list(COLUMNS), "csv_columns_refused")
        counts = {ticker: 0 for ticker in tickers}
        first = {ticker: None for ticker in tickers}; last = dict(first)
        seen, prior, count = set(), None, 0
        for row in reader:
            count += 1
            _need(count < ROW_LIMIT, "row_limit_ambiguous")
            _need(len(row) == 3 and all(len(value) <= 64 and "\x00" not in value for value in row), "csv_row_schema_refused")
            ticker, day, updated = row
            _need(ticker in counts and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day) is not None
                  and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", updated) is not None, "csv_row_schema_refused")
            observed, revised = date.fromisoformat(day), date.fromisoformat(updated)
            _need(FROM <= day <= TO and observed <= revised and (prior is None or prior <= day), "csv_date_or_order_refused")
            _need((ticker, day) not in seen, "duplicate_stock_date_refused")
            seen.add((ticker, day)); prior = day; counts[ticker] += 1
            first[ticker] = first[ticker] or day; last[ticker] = day
        return {"columns": list(COLUMNS), "row_count": count, "per_symbol_row_counts": counts,
            "first_observed_date": first, "last_observed_date": last,
            "symbols_without_rows": [ticker for ticker in tickers if not counts[ticker]],
            "metadata_rows_observed": count > 0, "only_declared_metadata_slice_measured": True,
            "lastupdated_is_not_first_public_availability": True}
    except PriceCoverageError:
        raise
    except (csv.Error, StopIteration, ValueError, OverflowError):
        raise PriceCoverageError("csv_schema_refused") from None


def _outside_lane(root):
    try:
        other, lane = str(Path(root).resolve()).casefold(), str(LANE_ROOT.resolve()).casefold()
        return other != lane and not other.startswith(lane + "/") and not lane.startswith(other + "/")
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def run_capture(expected_head, *, root=LANE_ROOT, identity=_identity, credential_reader=None,
                transport=None, clock=_now, anchors=None):
    fixture = root != LANE_ROOT or identity is not _identity or credential_reader is not None or transport is not None or clock is not _now or anchors is not None
    _need(not fixture or credential_reader is not None and transport is not None and anchors is not None,
          "fixture_callbacks_and_anchors_required")
    _need(not fixture or credential_reader is not read_keychain_credential and transport is not _default_transport,
          "fixture_real_callback_refused")
    _need(not fixture or _outside_lane(root), "fixture_root_overlaps_lane_refused")
    inputs = context = None
    try:
        actual_anchors = anchors if fixture else _production_anchors()
        baseline = identity(expected_head, root=root)
        inputs = _Plan(root, actual_anchors, fixture)
        _need(identity(expected_head, root=root) == baseline, "lane_changed_during_capture")
        context = _Context(root, fixture, expected_head, identity, baseline, inputs)
        authority = {name: False for name in FALSE_FLAGS}
        context.publish("reservation.json", {"schema": SCHEMA, "audit_id": AUDIT_ID, "profile": PROFILE,
            "owner_direction": OWNER_DIRECTION, "identity": baseline, "inputs": inputs.binding,
            "fixture_only": fixture, "method": "GET", "url": context.url, "request": inputs.plan["request"],
            "maximum_attempts": 1, "maximum_credential_reads": 1, "retry_resume_redirect_paging_permitted": False,
            "source_price_volume_fundamental_or_outcome_values_requested": False, **authority})
        context.publish("credential-read-started.json", {"schema": SCHEMA, "maximum_credential_reads": 1,
            "reservation_sha256": context.published["reservation.json"]})
        reader = read_keychain_credential if credential_reader is None else credential_reader
        credential, credential_observed = None, False
        try:
            credential = reader("sharadar")
            _need(type(credential) is KeychainCredential and credential.provider == "sharadar"
                  and type(credential.fixture_only) is bool and (fixture or credential.fixture_only is False)
                  and type(credential.value) is str and re.fullmatch(r"[!-~]{1,4096}", credential.value) is not None
                  and credential.value.casefold() != "test-api-key", "credential_read_refused")
            credential_observed = True
        except Exception:
            credential = None
        context.publish("credential-read-completed.json", {"schema": SCHEMA, "fixture_only": fixture,
            "started_sha256": context.published["credential-read-started.json"], "credential_read_observed": credential_observed,
            "disposition": "configured-keychain-credential-read" if credential_observed else "credential_read_refused"})
        projection, response, calls = None, None, 0
        disposition = "credential_read_refused"
        if credential is not None:
            context.publish("01-stocks-started.json", {"schema": SCHEMA, "profile": PROFILE, "method": "GET", "url": context.url,
                "maximum_attempts": 1, "reservation_sha256": context.published["reservation.json"]})
            context.check(); calls = 1
            try:
                response = (transport(context.url, credential) if fixture else
                            _default_transport(context.url, credential, context=context))
            except PriceCoverageError:
                if not fixture:
                    raise
                response = ProviderMetadataResponse(None, b"", False, "transport-error")
            except Exception:
                response = ProviderMetadataResponse(None, b"", False, "transport-error")
            context.check()
            _need(type(response) is ProviderMetadataResponse and type(response.body) is bytes
                  and type(response.body_complete) is bool and (response.status is None or type(response.status) is int and 100 <= response.status <= 599)
                  and (response.disposition is None or response.disposition in _CODES), "transport_result_refused")
            disposition = response.disposition
            if response.status != 200:
                disposition = disposition or "http_refused"
            elif disposition is None:
                disposition = "partial-read" if not response.body_complete else "oversized-response" if len(response.body) > MAX_BODY_BYTES else None
                if disposition is None:
                    try:
                        projection = _csv_projection(response.body, inputs.tickers, credential)
                        disposition = "declared-stock-date-metadata-observed"
                    except PriceCoverageError as exc:
                        disposition = str(exc)
            if projection is not None:
                context.publish("01-stocks-response.csv", response.body, raw=True)
                context.publish("01-stocks-metadata.json", projection)
            context.publish("01-stocks-completed.json", {"schema": SCHEMA, "started_sha256": context.published["01-stocks-started.json"],
                "http_status": response.status, "disposition": disposition, "metadata_observed": projection is not None,
                "response_body_retained": projection is not None, "body_sha256": _sha(response.body) if projection is not None else None,
                "body_size_bytes": len(response.body) if projection is not None else None,
                "untrusted_error_body_hashed_or_retained": False})
        complete = {"schema": SCHEMA, "audit_id": AUDIT_ID, "fixture_only": fixture, "completed_at_utc": clock(),
            "owner_direction": OWNER_DIRECTION, "identity": baseline, "inputs": inputs.binding,
            "planned_requests": 1, "credential_read_observed": credential_observed, "transport_invocation_count": calls,
            "http_status": None if response is None else response.status, "disposition": disposition,
            "status": "completed-metadata-capture" if projection is not None else "stopped-metadata-capture",
            "metadata": projection, "published_leaf_sha256": dict(context.published), "scope_reservation_sha256": context.latch_sha,
            "price_volume_fundamental_or_return_values_read": False, "full_study_population_coverage_verified": False,
            "paid_bulk_entitlement_verified": False, "research_looks": 0, "qc_jobs": 0, "backtests": 0, **authority}
        context.publish("complete.json", complete)
        return complete
    except PriceCoverageError:
        raise
    except Exception:
        raise PriceCoverageError("capture_custody_or_input_refused") from None
    finally:
        if context is not None:
            context.close()
        if inputs is not None:
            inputs.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_capture(args.expected_head)
    except PriceCoverageError as exc:
        print(json.dumps({"capture_refused": str(exc)}, sort_keys=True)); return 2
    # Keep even metadata ticker rows private; stdout has no supplier body,
    # credential, signed URL or source symbol list.
    print(json.dumps({"schema": SCHEMA, "audit_id": AUDIT_ID, "status": result["status"],
        "http_status": result["http_status"], "disposition": result["disposition"],
        "transport_invocation_count": result["transport_invocation_count"], "qc_jobs": 0, "backtests": 0}, sort_keys=True))
    return 0 if result["status"] == "completed-metadata-capture" else 2


if __name__ == "__main__":
    raise SystemExit(main())
