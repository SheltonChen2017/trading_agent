"""One immutable EODHD historical-price DATE-only capability probe.

The fixed filter=last_date request must return only one ISO date. Financial
arrays/objects/numbers are refused lexically, never JSON-decoded. The symbol
is a present provider discovery control, not a historical identity assertion.
No earnings endpoint, missing earnings window, price value, return, QC or
backtest is accessed by this profile. Production requires a clean committed
designated lane and the owner's separately recorded activation.
"""
from __future__ import annotations

import argparse
from datetime import date
import errno
import json
import os
from pathlib import Path
import re
import signal
import ssl
import subprocess
import sys
import threading
from urllib import error, parse, request

from research import insider_buying_earnings_archive_assessment_runner as custody
from research import insider_buying_sharadar_price_coverage_capture as publication
from research.insider_buying_eodhd_earnings_demo import FALSE_FLAGS
from research.insider_buying_keychain_credentials import KeychainCredential, read_keychain_credential
from research.insider_buying_provider_metadata_audit import _now
from research.insider_buying_provider_metadata_transport import ProviderMetadataResponse, _DenyRedirect
from research.insider_buying_sharadar_reference_qualification import _screen_credential


LANE_ROOT = custody.LANE_ROOT
LANE_BRANCH = custody.LANE_BRANCH
SELF_PATH = "research/insider_buying_eodhd_price_date_probe.py"
SCHEMA = "insider-eodhd-historical-price-date-probe-v1"
PROFILE = "eodhd-a-us-20050101-20060131-last-date-only-v1"
OWNER_DIRECTION = "owner:2026-10-24:owned-source-coverage-qualification-no-qc"
OUTPUT_PARTS = ("artifacts", "insider_buying", "eodhd_price_date_probe_v1")
AUDIT_ID = "ib-eodhd-price-date-2006-capability-20261024-once"
ENDPOINT = "https://eodhd.com/api/eod/A.US"
REDACTED_URL = (ENDPOINT + "?from=2005-01-01&to=2006-01-31&period=d&order=a"
                "&filter=last_date&fmt=json&api_token=<redacted>")
FROM = "2005-01-01"
TO = "2006-01-31"
MAX_BODY_BYTES = 4096
MAX_CONTROL_BYTES = 256 * 1024
TIMEOUT_SECONDS = 15
EMPTY_CACHE_PREFIX = "/var/empty/insider-eodhd-price-date-no-bytecode"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_SCALAR = re.compile(rb'(?:"([0-9]{4}-[0-9]{2}-[0-9]{2})"|([0-9]{4}-[0-9]{2}-[0-9]{2}))\n?\Z')
_TRANSPORT_CODES = frozenset({"unsupported-content-encoding", "invalid-content-length", "oversized-response",
    "truncated-response", "partial-read", "redirect-refused", "invalid-http-status",
    "response-origin-mismatch", "transport-timeout", "transport-error"})


class PriceDateProbeError(ValueError):
    """Fixed refusal codes only; never URL, credential, source or exception text."""


def _need(condition, code):
    if not condition:
        raise PriceDateProbeError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return publication._sha(raw)


def _request_profile():
    return {"method": "GET", "endpoint": ENDPOINT, "symbol": "A.US", "from": FROM, "to": TO,
            "period": "d", "order": "a", "filter": "last_date", "fmt": "json",
            "maximum_attempts": 1, "maximum_credential_reads": 1,
            "maximum_response_bytes": MAX_BODY_BYTES, "timeout_seconds": TIMEOUT_SECONDS}


def _identity(expected_head, *, root=LANE_ROOT):
    _need(root == LANE_ROOT, "designated_lane_required")
    _need(sys.flags.isolated == 1 and sys.flags.no_user_site == 1 and sys.flags.no_site == 1
          and sys.flags.dont_write_bytecode == 1 and sys.pycache_prefix == EMPTY_CACHE_PREFIX,
          "isolated_source_interpreter_required")
    value = custody._identity(expected_head)
    _need(SELF_PATH in value["source_sha256"]
          and "research/insider_buying_keychain_credentials.py" in value["source_sha256"]
          and "research/insider_buying_sharadar_reference_qualification.py" in value["source_sha256"]
          and "research/insider_buying_sharadar_price_coverage_capture.py" in value["source_sha256"],
          "source_closure_incomplete")
    return value


def _validate_identity(value, expected_head, root):
    _need(type(expected_head) is str and _HEAD.fullmatch(expected_head) is not None
          and type(value) is dict and set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
          and value["root"] == str(root) and value["branch"] == LANE_BRANCH
          and value["head"] == expected_head and value["clean"] is True,
          "exact_clean_identity_required")
    sources = value["source_sha256"]
    _need(type(sources) is dict and 0 < len(sources) <= 4096
          and all(type(name) is str and name.endswith(".py") and not Path(name).is_absolute()
                  and ".." not in Path(name).parts and type(digest) is str
                  and _SHA.fullmatch(digest) is not None for name, digest in sources.items())
          and value["source_inventory_sha256"] == _sha(_canonical(sources)), "identity_source_inventory_refused")
    return value


def _credential(value, fixture):
    _need(type(value) is KeychainCredential and value.provider == "eodhd"
          and type(value.fixture_only) is bool and value.fixture_only is fixture
          and type(value.value) is str and re.fullmatch(r"[!-~]{1,4096}", value.value) is not None
          and value.value.casefold() not in {"demo", "test-api-key"}, "credential_read_refused")
    return value


def _live_url(credential):
    return ENDPOINT + "?" + parse.urlencode((("from", FROM), ("to", TO), ("period", "d"), ("order", "a"),
                                           ("filter", "last_date"), ("fmt", "json"), ("api_token", credential.value)))


def _validate_live_url(url, credential):
    # Independently enforce the endpoint and exact ordered finite query. A URL
    # from the request object is checked again immediately before opener.open.
    parts = parse.urlsplit(url)
    _need(parts.scheme == "https" and parts.netloc == "eodhd.com" and parts.path == "/api/eod/A.US"
          and not parts.fragment and not parts.username and not parts.password
          and parse.parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=7)
          == [("from", "2005-01-01"), ("to", "2006-01-31"), ("period", "d"), ("order", "a"),
              ("filter", "last_date"), ("fmt", "json"), ("api_token", credential.value)]
          and url == _live_url(credential), "fixed_transport_profile_refused")


def _scalar_projection(raw, credential):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES, "date_scalar_resource_refused")
    try:
        # UTF-8 and bounded percent-decoding are credential screening only.
        # No JSON parser is called, even if a server ignores the last_date filter.
        _screen_credential(raw, {"opaque_body": raw.decode("utf-8")}, credential)
    except (ValueError, UnicodeError):
        raise PriceDateProbeError("credential_echo_or_encoding_refused") from None
    match = _SCALAR.fullmatch(raw)
    _need(match is not None, "date_only_scalar_required")
    text = (match.group(1) or match.group(2)).decode("ascii")
    try:
        value = date.fromisoformat(text)
    except ValueError:
        raise PriceDateProbeError("date_only_scalar_required") from None
    _need(FROM <= value.isoformat() <= TO, "date_scalar_outside_requested_window")
    return {"schema": SCHEMA + "/metadata", "symbol": "A.US", "last_observed_source_date": text,
            "scalar_encoding": "json-string" if match.group(1) else "plain-date",
            "response_body_sha256": _sha(raw), "response_body_bytes": len(raw),
            "date_within_declared_window": True, "present_symbol_discovery_only": True,
            "historical_identity_verified": False, "full_price_history_verified": False,
            "delisted_coverage_verified": False, "price_or_return_values_interpreted": False}


def _json(raw):
    def unique(pairs):
        body = {}
        for name, value in pairs:
            _need(name not in body, "duplicate_control_key_refused")
            body[name] = value
        return body
    try:
        body = json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: _need(False, "nonfinite_control_refused"))
        _need(type(body) is dict and _canonical(body) == raw, "canonical_control_required")
        return body
    except (UnicodeError, json.JSONDecodeError, TypeError, RecursionError, OverflowError):
        raise PriceDateProbeError("control_json_refused") from None


class _Context:
    def __init__(self, root, fixture, expected_head, identity, baseline):
        self.root, self.fixture, self.expected_head = root, fixture, expected_head
        self.identity, self.baseline = identity, baseline
        self.parent = self.directory = None
        self.published, self.versions = {}, {}
        try:
            self.parent = custody._Chain(root, OUTPUT_PARTS, create=True)
            _need(os.fstat(self.parent.fd).st_uid == os.geteuid() and not os.listdir(self.parent.fd),
                  "consumed_or_ambiguous_scope_refused")
            self.latch_sha, self.latch_version = publication._publish_raw(self.parent.fd, "scope-reservation.json", _canonical({
                "schema": SCHEMA, "audit_id": AUDIT_ID, "profile": PROFILE, "url": REDACTED_URL,
                "request": _request_profile(), "retry_resume_redirect_paging_permitted": False}))
            os.mkdir(AUDIT_ID, 0o700, dir_fd=self.parent.fd); os.fsync(self.parent.fd)
            self.directory = custody._Chain(root, (*OUTPUT_PARTS, AUDIT_ID))
            self.check()
        except BaseException:
            self.close(); raise

    def check(self):
        _need(_validate_identity(self.identity(self.expected_head, root=self.root), self.expected_head, self.root)
              == self.baseline, "lane_changed_during_probe")
        self.parent.recheck(); self.directory.recheck()
        _need(set(os.listdir(self.parent.fd)) == {"scope-reservation.json", AUDIT_ID}
              and set(os.listdir(self.directory.fd)) == set(self.published)
              and os.fstat(self.directory.fd).st_uid == os.geteuid(), "output_inventory_changed")
        raw, version = publication._leaf(self.parent.fd, "scope-reservation.json", MAX_CONTROL_BYTES)
        _need(_sha(raw) == self.latch_sha and version == self.latch_version, "scope_reservation_changed")
        for name, digest in self.published.items():
            raw, version = publication._leaf(self.directory.fd, name, MAX_CONTROL_BYTES)
            _need(_sha(raw) == digest and version == self.versions[name], "published_output_changed")
        self.parent.recheck(); self.directory.recheck()

    def publish(self, name, body, *, raw=False):
        self.check()
        encoded = body if raw else _canonical(body)
        _need(type(encoded) is bytes and 0 < len(encoded) <= (MAX_BODY_BYTES if raw else MAX_CONTROL_BYTES),
              "publication_resource_refused")
        self.published[name], self.versions[name] = publication._publish_raw(self.directory.fd, name, encoded)
        self.check()

    def close(self):
        active_primary = sys.exc_info()[0] is not None
        failed = False
        for name in ("directory", "parent"):
            held = getattr(self, name, None)
            setattr(self, name, None)
            if held is not None:
                try:
                    held.close()
                except BaseException:
                    failed = True
        if failed and not active_primary:
            raise PriceDateProbeError("context_cleanup_refused") from None


class _Deadline:
    """One main-thread wall-clock alarm bounds open AND all response reads."""
    def __enter__(self):
        _need(threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer")
              and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "transport_deadline_unavailable")
        self.previous = signal.getsignal(signal.SIGALRM)
        def expired(_number, _frame):
            raise PriceDateProbeError("transport-timeout")
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, TIMEOUT_SECONDS)
        return self

    def __exit__(self, *_exc):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous)


def _read_bounded(stream, status):
    try:
        _need(callable(getattr(stream.headers, "get_all", None)), "partial-read")
        enc = stream.headers.get_all("Content-Encoding", [])
        lengths = stream.headers.get_all("Content-Length", [])
        transfers = stream.headers.get_all("Transfer-Encoding", [])
        _need(all(type(items) is list and all(type(value) is str for value in items)
                  for items in (enc, lengths, transfers)), "partial-read")
        _need(len(enc) <= 1 and (not enc or enc[0].strip().lower() == "identity"), "unsupported-content-encoding")
        _need(len(lengths) <= 1, "invalid-content-length")
        _need(len(transfers) <= 1 and (not transfers or not lengths and transfers[0].strip().lower() == "chunked"), "partial-read")
        length = None
        if lengths:
            _need(re.fullmatch(r"[0-9]{1,20}", lengths[0]) is not None, "invalid-content-length")
            length = int(lengths[0]); _need(length <= MAX_BODY_BYTES, "oversized-response")
        chunks, count = [], 0
        while count <= MAX_BODY_BYTES:
            requested = MAX_BODY_BYTES + 1 - count
            chunk = stream.read(requested)
            _need(type(chunk) is bytes and len(chunk) <= requested, "partial-read")
            if not chunk:
                _need(length is None or count == length, "truncated-response")
                return ProviderMetadataResponse(status, b"".join(chunks), True)
            chunks.append(chunk); count += len(chunk)
        raise PriceDateProbeError("oversized-response")
    except PriceDateProbeError as exc:
        return ProviderMetadataResponse(status, b"", False, str(exc))
    except Exception:
        return ProviderMetadataResponse(status, b"", False, "partial-read")


def _default_transport(redacted_url, credential, *, context):
    _need(type(context) is _Context and context.root == LANE_ROOT and context.fixture is False,
          "real_probe_context_required")
    _credential(credential, False)
    _need(redacted_url == REDACTED_URL, "fixed_transport_profile_refused")
    context.check()
    _need(set(context.published) == {"reservation.json", "credential-read-started.json",
          "credential-read-completed.json", "01-date-started.json"}, "observed_started_journal_required")
    reservation = _json(publication._leaf(context.directory.fd, "reservation.json", MAX_CONTROL_BYTES)[0])
    started = _json(publication._leaf(context.directory.fd, "01-date-started.json", MAX_CONTROL_BYTES)[0])
    read_start = _json(publication._leaf(context.directory.fd, "credential-read-started.json", MAX_CONTROL_BYTES)[0])
    read = _json(publication._leaf(context.directory.fd, "credential-read-completed.json", MAX_CONTROL_BYTES)[0])
    _need(reservation == _reservation(context.baseline, False)
          and started == _started(context.published["reservation.json"])
          and read_start == {"schema": SCHEMA, "maximum_credential_reads": 1,
              "reservation_sha256": context.published["reservation.json"]}
          and read == {"schema": SCHEMA, "fixture_only": False,
              "started_sha256": context.published["credential-read-started.json"],
              "credential_read_observed": True, "disposition": "configured-keychain-credential-read"},
          "observed_started_journal_required")
    context.check()
    url = _live_url(credential)
    _validate_live_url(url, credential)
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                  request.HTTPSHandler(context=ssl.create_default_context()))
    item = request.Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity"}, method="GET")
    stream = None
    try:
        with _Deadline():
            # Last pre-opener custody/source identity check occurs after request
            # construction. Nothing carrying the live URL is journaled/logged.
            context.check(); _validate_live_url(item.full_url, credential)
            try:
                stream = opener.open(item, timeout=TIMEOUT_SECONDS)
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
    except (TimeoutError, PriceDateProbeError) as exc:
        if type(exc) is PriceDateProbeError and str(exc) != "transport-timeout":
            raise
        return ProviderMetadataResponse(None, b"", False, "transport-timeout")
    except Exception:
        return ProviderMetadataResponse(None, b"", False, "transport-error")
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def _reservation(identity, fixture):
    return {"schema": SCHEMA, "audit_id": AUDIT_ID, "profile": PROFILE, "owner_direction": OWNER_DIRECTION,
            "identity": identity, "fixture_only": fixture, "url": REDACTED_URL, "request": _request_profile(),
            "retry_resume_redirect_paging_permitted": False, "price_volume_or_return_values_requested": False,
            **{name: False for name in FALSE_FLAGS}}


def _started(reservation_sha):
    return {"schema": SCHEMA, "profile": PROFILE, "method": "GET", "url": REDACTED_URL,
            "maximum_attempts": 1, "reservation_sha256": reservation_sha}


def _fixture_denial():
    custody._effective_denial(require_fork=False)
    try:
        subprocess.run(("/usr/bin/security", "-h"), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=2, check=False)
    except OSError as exc:
        _need(exc.errno in {errno.EPERM, errno.EACCES}, "fixture_keychain_exec_denial_required")
    else:
        raise PriceDateProbeError("fixture_keychain_exec_denial_required")


def run_probe(expected_head, *, root=LANE_ROOT, identity=_identity, credential_reader=None,
              transport=None, clock=_now):
    fixture = (root != LANE_ROOT or identity is not _identity or credential_reader is not None
               or transport is not None or clock is not _now)
    _need(isinstance(root, Path) and root.is_absolute(), "absolute_probe_root_required")
    _need(not fixture or publication._outside_lane(root) and root.resolve() == root
          and callable(identity) and identity is not _identity
          and callable(credential_reader) and credential_reader is not read_keychain_credential
          and callable(transport) and transport is not _default_transport,
          "invented_outside_lane_callbacks_required")
    context = None
    try:
        if fixture:
            _fixture_denial()
        baseline = _validate_identity(identity(expected_head, root=root), expected_head, root)
        context = _Context(root, fixture, expected_head, identity, baseline)
        context.publish("reservation.json", _reservation(baseline, fixture))
        context.publish("credential-read-started.json", {"schema": SCHEMA, "maximum_credential_reads": 1,
            "reservation_sha256": context.published["reservation.json"]})
        reader = credential_reader if fixture else read_keychain_credential
        credential, observed = None, False
        try:
            credential = _credential(reader("eodhd"), fixture)
            observed = True
        except Exception:
            credential = None
        context.publish("credential-read-completed.json", {"schema": SCHEMA, "fixture_only": fixture,
            "started_sha256": context.published["credential-read-started.json"], "credential_read_observed": observed,
            "disposition": "configured-keychain-credential-read" if observed else "credential_read_refused"})
        response = metadata = None
        calls, disposition = 0, "credential_read_refused"
        if credential is not None:
            context.publish("01-date-started.json", _started(context.published["reservation.json"]))
            context.check(); calls = 1
            try:
                response = (transport(REDACTED_URL, credential) if fixture else
                            _default_transport(REDACTED_URL, credential, context=context))
            except PriceDateProbeError:
                if not fixture:
                    raise
                response = ProviderMetadataResponse(None, b"", False, "transport-error")
            except Exception:
                response = ProviderMetadataResponse(None, b"", False, "transport-error")
            context.check()
            _need(type(response) is ProviderMetadataResponse and type(response.body) is bytes
                  and type(response.body_complete) is bool
                  and (response.status is None or type(response.status) is int and 100 <= response.status <= 599)
                  and (response.disposition is None or response.disposition in _TRANSPORT_CODES), "transport_result_refused")
            disposition = response.disposition
            if response.status != 200:
                disposition = disposition or "http_refused"
            elif disposition is None:
                disposition = "partial-read" if not response.body_complete else "oversized-response" if len(response.body) > MAX_BODY_BYTES else None
                if disposition is None:
                    try:
                        metadata = _scalar_projection(response.body, credential)
                        disposition = "date-only-capability-observed"
                    except PriceDateProbeError as exc:
                        disposition = str(exc)
            if metadata is not None:
                context.publish("01-date-response.txt", response.body, raw=True)
                context.publish("01-date-metadata.json", metadata)
            context.publish("01-date-completed.json", {"schema": SCHEMA,
                "started_sha256": context.published["01-date-started.json"], "http_status": response.status,
                "disposition": disposition, "metadata_observed": metadata is not None,
                "response_body_retained": metadata is not None,
                "body_sha256": _sha(response.body) if metadata is not None else None,
                "body_size_bytes": len(response.body) if metadata is not None else None,
                "untrusted_error_body_hashed_or_retained": False})
        result = {"schema": SCHEMA, "audit_id": AUDIT_ID, "fixture_only": fixture,
            "completed_at_utc": clock(), "owner_direction": OWNER_DIRECTION, "identity": baseline,
            "planned_requests": 1, "credential_read_observed": observed, "transport_invocation_count": calls,
            "http_status": None if response is None else response.status, "disposition": disposition,
            "status": "completed-date-metadata-probe" if metadata is not None else "stopped-date-metadata-probe",
            "metadata": metadata, "published_leaf_sha256": dict(context.published),
            "scope_reservation_sha256": context.latch_sha, "price_volume_or_return_values_read": False,
            "full_study_population_coverage_verified": False, "paid_bulk_entitlement_verified": False,
            "research_looks": 0, "qc_jobs": 0, "backtests": 0, **{name: False for name in FALSE_FLAGS}}
        context.publish("complete.json", result)
        return result
    except PriceDateProbeError:
        raise
    except Exception:
        raise PriceDateProbeError("probe_custody_or_identity_refused") from None
    finally:
        if context is not None:
            context.close()


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--expected-head", required=True)
    args = cli.parse_args(argv)
    try:
        result = run_probe(args.expected_head)
    except PriceDateProbeError as exc:
        print(json.dumps({"probe_refused": str(exc)}, sort_keys=True)); return 2
    print(json.dumps({name: result[name] for name in ("status", "http_status", "disposition",
        "transport_invocation_count", "research_looks", "qc_jobs", "backtests")}, sort_keys=True))
    return 0 if result["status"] == "completed-date-metadata-probe" else 2


if __name__ == "__main__":
    raise SystemExit(main())
