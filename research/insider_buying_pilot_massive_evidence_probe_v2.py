"""Fixed three-request capability qualification, not historical admission.

The two Apple Form-4 discovery requests and one dated AAPL reference request
are fresh, separately claimed scopes. No SEC link, cursor, retry or fallback
is followed. Source numeric lexemes remain opaque; only identity/date/field
metadata is projected. A current response cannot prove historical public
known-by, original body/version lineage, full coverage, QC SID or rights.
Importing this module performs no I/O. Actual use requires a clean committed
source closure and the isolated interpreter, not the invented fixture path.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import ssl
import sys
from urllib import error, parse, request

from research import insider_buying_pilot_massive_reference_probe as prior


LANE_ROOT, LANE_BRANCH = prior.LANE_ROOT, prior.LANE_BRANCH
SELF_PATH = "research/insider_buying_pilot_massive_evidence_probe_v2.py"
SCHEMA = "insider-pilot-massive-evidence-capability-probe-v2"
PROFILE = "massive-apple-2020q4-filings-aapl-20210104-reference-v2"
OWNER_DIRECTION = "owner:2026-10-27:existing-subscriptions-parent-pit-availability-no-qc"
OUTPUT_PARTS = ("artifacts", "insider_buying", "pilot_massive_evidence_v2")
AUDIT_ID = "ib-pilot-massive-evidence-20261027-once-v2"
EMPTY_CACHE_PREFIX = "/var/empty/insider-pilot-massive-evidence-v2-no-bytecode"
MAX_BODY_BYTES = MAX_CONTROL_BYTES = 256 * 1024
TIMEOUT_SECONDS = 15
REQUESTS = (
    ("reference", "https://api.massive.com/v3/reference/tickers?ticker=AAPL&market=stocks&active=true&date=2021-01-04&sort=ticker&order=asc&limit=1"),
    ("index", "https://api.massive.com/stocks/filings/vX/index?cik=0000320193&form_type=4&filing_date.gte=2020-10-01&filing_date.lte=2020-12-31&limit=1&sort=filing_date.asc"),
    ("form4", "https://api.massive.com/stocks/filings/vX/form-4?issuer_cik=0000320193&form_type=4&filing_date.gte=2020-10-01&filing_date.lte=2020-12-31&limit=1&sort=filing_date.asc"),
)
_INDEX_KEYS = frozenset({"accession_number", "cik", "ticker", "form_type", "filing_date", "issuer_name", "filing_url"})
_NUMBER_KEYS = frozenset({"exercise_price", "shares_owned_following_transaction", "transaction_price_per_share",
    "transaction_shares", "transaction_value", "underlying_security_shares"})
_BOOL_KEYS = frozenset({"aff_10b5_one", "equity_swap_involved", "is_director", "is_officer", "is_other",
    "is_ten_percent_owner", "not_subject_to_section_16"})
_DATE_KEYS = frozenset({"date_of_original_submission", "deemed_execution_date", "exercise_date", "expiration_date",
    "period_of_report", "transaction_date"})
_TEXT_KEYS = frozenset({"direct_or_indirect", "issuer_name", "nature_of_ownership", "officer_title", "owner_cik",
    "owner_name", "record_type", "remarks", "security_title", "security_type", "transaction_acquired_disposed",
    "transaction_code", "transaction_timeliness", "underlying_security_title"})
_FORM_KEYS = frozenset({"accession_number", "issuer_cik", "form_type", "filing_date", "filing_url", "footnotes", "tickers"}) | _NUMBER_KEYS | _BOOL_KEYS | _DATE_KEYS | _TEXT_KEYS
FALSE_FLAGS = tuple(dict.fromkeys((*prior.FALSE_FLAGS, "historical_public_known_by_verified", "original_parent_bytes_verified",
    "historical_body_version_verified", "all_six_form_population_verified", "processing_rights_verified")))


class MassiveEvidenceProbeError(ValueError):
    """Finite sanitized refusals, never private/provider exception text."""


def _need(ok, code):
    if not ok:
        raise MassiveEvidenceProbeError(code)


def _raw(value):
    return prior._raw(value)


def _sha(raw):
    return prior._sha(raw)


def _profiles():
    return [{"ordinal": n, "kind": kind, "method": "GET", "url": url, "maximum_attempts": 1,
        "maximum_response_bytes": MAX_BODY_BYTES, "timeout_seconds": TIMEOUT_SECONDS}
        for n, (kind, url) in enumerate(REQUESTS, 1)]


def _identity(expected_head, *, root=LANE_ROOT):
    _need(root == LANE_ROOT and Path(__file__).resolve() == LANE_ROOT / SELF_PATH,
          "designated_committed_source_required")
    _need(sys.flags.isolated == sys.flags.no_user_site == sys.flags.no_site == sys.flags.dont_write_bytecode == 1
          and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "isolated_source_interpreter_required")
    value = prior.custody._identity(expected_head)
    _need({SELF_PATH, prior.SELF_PATH, "research/insider_buying_keychain_credentials.py",
        "research/insider_buying_eodhd_price_date_probe.py", "research/insider_buying_sharadar_price_coverage_capture.py",
        "research/insider_buying_sharadar_reference_qualification.py"} <= set(value["source_sha256"]),
        "source_closure_incomplete")
    return value


def _validate_identity(value, head, root):
    try:
        return prior._validate_identity(value, head, root)
    except (ValueError, TypeError, KeyError):
        raise MassiveEvidenceProbeError("exact_clean_identity_required") from None


def _text(value):
    return type(value) is str and len(value) <= 8192 and not any(ord(c) < 32 for c in value)


def _day(value):
    _need(_text(value) and re.fullmatch(r"\d{4}-\d\d-\d\d", value), "date_only_field_required")
    try:
        _need(date.fromisoformat(value).isoformat() == value, "date_only_field_required")
    except ValueError:
        raise MassiveEvidenceProbeError("date_only_field_required") from None


def _structure(body):
    pending, count = [(body, 0)], 0
    while pending:
        value, depth = pending.pop(); count += 1
        _need(count <= 4096 and depth <= 24, "metadata_structure_bound_refused")
        if type(value) is dict:
            _need(len(value) <= 64 and all(_text(k) and len(k) <= 128 for k in value), "metadata_structure_bound_refused")
            pending.extend((v, depth + 1) for v in value.values())
        elif type(value) is list:
            _need(len(value) <= 128, "metadata_structure_bound_refused")
            pending.extend((v, depth + 1) for v in value)
        elif type(value) is str:
            _need(_text(value), "metadata_text_refused")
        elif type(value) in {prior._IntegerLexeme, prior._FloatLexeme}:
            _need(len(value) <= 128, "numeric_lexeme_bound_refused")
        else:
            _need(value is None or type(value) is bool, "source_scalar_refused")


def _split(url, code):
    # Section 342 (Claude review): urlsplit raises a plain ValueError on, for
    # example, an unbalanced IPv6 bracket. That is a typed source refusal.
    try:
        return parse.urlsplit(url)
    except ValueError:
        raise MassiveEvidenceProbeError(code) from None


def _filing(row, kind):
    issuer = "cik" if kind == "index" else "issuer_cik"
    required = {"accession_number", issuer, "form_type", "filing_date", "filing_url"}
    _need(type(row) is dict and required <= set(row) <= (_INDEX_KEYS if kind == "index" else _FORM_KEYS),
          "filing_only_fields_required")
    _need(_text(row[issuer]) and re.fullmatch(r"[0-9]{1,10}", row[issuer])
          and row[issuer].lstrip("0") == "320193" and row["form_type"] == "4"
          and type(row["form_type"]) is str and type(row["filing_date"]) is str
          and "2020-10-01" <= row["filing_date"] <= "2020-12-31" and _text(row["accession_number"])
          and re.fullmatch(r"[0-9]{10}-20-[0-9]{6}", row["accession_number"]), "requested_filing_identity_refused")
    _day(row["filing_date"])
    url = _split(row["filing_url"], "filing_link_identity_refused") if _text(row["filing_url"]) else None
    _need(url is not None and url.scheme == "https" and url.netloc in {"www.sec.gov", "sec.gov"}
          and not url.query and not url.fragment and url.path.startswith("/Archives/edgar/data/320193/")
          and (row["accession_number"] in url.path or row["accession_number"].replace("-", "") in url.path),
          "filing_link_identity_refused")
    if kind == "index":
        _need(all(_text(v) for v in row.values()), "index_metadata_types_refused")
        _need("ticker" not in row or row["ticker"] == "AAPL", "requested_filing_identity_refused")
    else:
        for key in _NUMBER_KEYS & row.keys():
            _need(row[key] is None or type(row[key]) in {prior._IntegerLexeme, prior._FloatLexeme}, "opaque_numeric_source_field_required")
        for key in _BOOL_KEYS & row.keys():
            _need(row[key] is None or type(row[key]) is bool, "source_boolean_required")
        for key in _DATE_KEYS & row.keys():
            if row[key] is not None:
                _day(row[key])
        for key in _TEXT_KEYS & row.keys():
            _need(row[key] is None or _text(row[key]), "source_text_field_required")
        if row.get("owner_cik") is not None:
            _need(re.fullmatch(r"[0-9]{1,10}", row["owner_cik"]) is not None, "source_owner_identifier_refused")
        if "tickers" in row:
            _need(type(row["tickers"]) is list and row["tickers"] == ["AAPL"], "requested_filing_identity_refused")
        if "footnotes" in row:
            _need(type(row["footnotes"]) is list and all(type(v) is dict and set(v) == {"id", "description"}
                and all(_text(x) for x in v.values()) for v in row["footnotes"]), "source_footnote_schema_refused")
    return {"accession_number": row["accession_number"], "issuer_cik": row[issuer].zfill(10),
            "form_type": "4", "filing_date": row["filing_date"]}


def _reference(row):
    _need(type(row) is dict and prior._REQUIRED_ROW_KEYS <= set(row) <= prior._ROW_KEYS
          and row["active"] is True and all(_text(v) for k, v in row.items() if k != "active"),
          "reference_only_fields_required")
    _need(row["ticker"] == "AAPL" and row["cik"].lstrip("0") == "320193"
          and re.fullmatch(r"[0-9]{1,10}", row["cik"]) and row["type"] == "CS"
          and row["market"] == "stocks" and row["locale"] == "us"
          and re.fullmatch(r"[A-Z0-9]{12}", row["share_class_figi"])
          and re.fullmatch(r"[A-Z0-9]{4}", row["primary_exchange"]), "requested_reference_identity_refused")
    if "composite_figi" in row:
        _need(re.fullmatch(r"[A-Z0-9]{12}", row["composite_figi"]) is not None, "reference_identifier_refused")
    for key in ("last_updated_utc", "delisted_utc"):
        if key in row:
            try:
                stamp = prior.datetime.fromisoformat(row[key].replace("Z", "+00:00"))
                _need(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0, "reference_timestamp_refused")
            except ValueError:
                raise MassiveEvidenceProbeError("reference_timestamp_refused") from None
    return {k: row[k] for k in ("ticker", "cik", "type", "primary_exchange", "share_class_figi")} | {"requested_asof_date": "2021-01-04"}


def _projection(raw, credential, ordinal):
    _need(type(ordinal) is int and 1 <= ordinal <= 3 and type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES,
          "fixed_bounded_metadata_required")
    try:
        body = prior._json(raw)
        prior._screen_credential(raw, body, credential)
    except (ValueError, UnicodeError):
        raise MassiveEvidenceProbeError("source_json_or_credential_echo_refused") from None
    _structure(body)
    _need(type(body) is dict and {"results", "status", "request_id"} <= set(body)
          and set(body) <= {"results", "status", "request_id", "count", "next_url"}
          and type(body["status"]) is str and body["status"] == "OK" and _text(body["request_id"])
          and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", body["request_id"])
          and type(body["results"]) is list and len(body["results"]) <= 1, "fixed_single_metadata_envelope_refused")
    if "count" in body:
        _need(type(body["count"]) is prior._IntegerLexeme and body["count"] == str(len(body["results"])), "exact_result_count_required")
    next_url = body.get("next_url")
    if next_url is not None:
        _need(_text(next_url), "cursor_origin_refused")
        parsed = _split(next_url, "cursor_origin_refused"); expected = parse.urlsplit(REQUESTS[ordinal - 1][1])
        _need(parsed.scheme == "https" and parsed.netloc == "api.massive.com" and parsed.path == expected.path
              and not parsed.fragment and parsed.query, "cursor_origin_refused")
    kind = REQUESTS[ordinal - 1][0]
    identity = None if not body["results"] else (_reference(body["results"][0]) if kind == "reference" else _filing(body["results"][0], kind))
    return {"schema": SCHEMA + "/metadata", "ordinal": ordinal, "kind": kind,
        "result_count": len(body["results"]), "has_unfollowed_next_page": next_url is not None,
        "response_field_names": sorted(body), "row_field_names": [] if identity is None else sorted(body["results"][0]),
        "source_identity": identity, "response_body_sha256": _sha(raw), "response_body_bytes": len(raw),
        "numeric_financial_fields_interpreted": False, **dict.fromkeys(FALSE_FLAGS, False)}


def _reservation(identity, fixture):
    return {"schema": SCHEMA, "audit_id": AUDIT_ID, "profile": PROFILE, "owner_direction": OWNER_DIRECTION,
        "identity": identity, "fixture_only": fixture, "requests": _profiles(), "maximum_attempts": 3,
        "maximum_credential_reads": 1, "retry_redirect_paging_fallback_permitted": False, **dict.fromkeys(FALSE_FLAGS, False)}


def _started(ordinal, reservation_sha):
    return {"schema": SCHEMA, "profile": PROFILE, **_profiles()[ordinal - 1], "reservation_sha256": reservation_sha}


class _Context:
    """Fresh held private scope, independent of the consumed predecessor."""
    def __init__(self, root, fixture, head, identity, baseline):
        self.root, self.fixture, self.head, self.identity, self.baseline = root, fixture, head, identity, baseline
        self.parent = self.directory = None
        self.published, self.versions = {}, {}
        try:
            self.parent = prior.custody._Chain(root, OUTPUT_PARTS, create=True)
            _need(os.fstat(self.parent.fd).st_uid == os.geteuid() and not os.listdir(self.parent.fd), "consumed_or_ambiguous_scope_refused")
            self.scope_sha, self.scope_version = prior.publication._publish_raw(self.parent.fd, "scope-reservation.json",
                _raw({"schema": SCHEMA, "audit_id": AUDIT_ID, "profile": PROFILE, "requests": _profiles(), "maximum_attempts": 3}))
            os.mkdir(AUDIT_ID, 0o700, dir_fd=self.parent.fd); os.fsync(self.parent.fd)
            self.directory = prior.custody._Chain(root, (*OUTPUT_PARTS, AUDIT_ID)); self.check()
        except BaseException:
            self.close(); raise

    def check(self):
        _need(_validate_identity(self.identity(self.head, root=self.root), self.head, self.root) == self.baseline, "lane_changed_during_probe")
        self.parent.recheck(); self.directory.recheck()
        _need(set(os.listdir(self.parent.fd)) == {"scope-reservation.json", AUDIT_ID}
              and set(os.listdir(self.directory.fd)) == set(self.published), "probe_inventory_changed")
        raw, version = prior.publication._leaf(self.parent.fd, "scope-reservation.json", MAX_CONTROL_BYTES)
        _need(_sha(raw) == self.scope_sha and version == self.scope_version, "scope_reservation_changed")
        for name, digest in self.published.items():
            raw, version = prior.publication._leaf(self.directory.fd, name, MAX_CONTROL_BYTES)
            _need(_sha(raw) == digest and version == self.versions[name], "published_output_changed")
        self.parent.recheck(); self.directory.recheck()

    def publish(self, name, body, *, raw=False):
        self.check(); value = body if raw else _raw(body)
        _need(type(value) is bytes and 0 < len(value) <= MAX_CONTROL_BYTES, "publication_bound_refused")
        self.published[name], self.versions[name] = prior.publication._publish_raw(self.directory.fd, name, value); self.check()

    def close(self):
        primary, failed = sys.exc_info()[0] is not None, False
        for name in ("directory", "parent"):
            held = getattr(self, name, None); setattr(self, name, None)
            if held is not None:
                try: held.close()
                except BaseException: failed = True
        if failed and not primary:
            raise MassiveEvidenceProbeError("context_cleanup_refused") from None


def _default_transport(url, credential, *, context, ordinal):
    _need(type(context) is _Context and context.root == LANE_ROOT and context.fixture is False
          and context.identity is _identity, "real_probe_context_required")
    prior._credential(credential, False)
    _need(type(ordinal) is int and 1 <= ordinal <= 3 and url == REQUESTS[ordinal - 1][1], "fixed_capability_url_required")
    expected = {"reservation.json", "credential-read-started.json", "credential-read-completed.json", f"{ordinal:02d}-started.json"}
    for previous in range(1, ordinal):
        expected.update(f"{previous:02d}-{suffix}.json" for suffix in ("started", "response", "metadata", "completed"))
    context.check()
    _need(set(context.published) == expected, "observed_started_journal_required")
    leaves = {name: prior.date_probe._json(prior.publication._leaf(context.directory.fd, name, MAX_CONTROL_BYTES)[0])
              for name in ("reservation.json", "credential-read-started.json", "credential-read-completed.json", f"{ordinal:02d}-started.json")}
    _need(_raw(leaves["reservation.json"]) == _raw(_reservation(context.baseline, False))
          and _raw(leaves[f"{ordinal:02d}-started.json"]) == _raw(_started(ordinal, context.published["reservation.json"]))
          and _raw(leaves["credential-read-started.json"]) == _raw({"schema": SCHEMA, "maximum_credential_reads": 1, "reservation_sha256": context.published["reservation.json"]})
          and _raw(leaves["credential-read-completed.json"]) == _raw({"schema": SCHEMA, "fixture_only": False,
              "started_sha256": context.published["credential-read-started.json"], "credential_read_observed": True,
              "disposition": "configured-keychain-credential-read"}), "observed_started_journal_required")
    for previous in range(1, ordinal):
        completed = prior.date_probe._json(prior.publication._leaf(context.directory.fd, f"{previous:02d}-completed.json", MAX_CONTROL_BYTES)[0])
        metadata = prior.date_probe._json(prior.publication._leaf(context.directory.fd, f"{previous:02d}-metadata.json", MAX_CONTROL_BYTES)[0])
        _need(_raw(completed) == _raw({"schema": SCHEMA, "ordinal": previous, "http_status": 200,
            "started_sha256": context.published[f"{previous:02d}-started.json"],
            "disposition": "capability_metadata_observed", "metadata": metadata,
            "body_sha256": context.published[f"{previous:02d}-response.json"],
            "body_size_bytes": metadata["response_body_bytes"], "untrusted_error_body_hashed_or_retained": False})
            and type(metadata["result_count"]) is int and metadata["result_count"] == 1, "preceding_capability_success_required")
    context.check()
    opener = request.build_opener(request.ProxyHandler({}), prior.date_probe._DenyRedirect(), request.HTTPSHandler(context=ssl.create_default_context()))
    item = request.Request(url, headers={"Authorization": "Bearer " + credential.value, "Accept": "application/json", "Accept-Encoding": "identity"}, method="GET")
    stream = None
    try:
        with prior.date_probe._Deadline():
            context.check()
            _need(item.full_url == url and item.get_method() == "GET" and item.get_header("Authorization") == "Bearer " + credential.value, "fixed_capability_request_required")
            try:
                try: stream = opener.open(item, timeout=TIMEOUT_SECONDS)
                except error.HTTPError as exc: stream = exc
                status = stream.getcode()
                if type(status) is not int or not 100 <= status <= 599:
                    return prior.date_probe.ProviderMetadataResponse(None, b"", False, "invalid-http-status")
                if stream.geturl() != url:
                    return prior.date_probe.ProviderMetadataResponse(status, b"", False, "response-origin-mismatch")
                if status != 200:
                    return prior.date_probe.ProviderMetadataResponse(status, b"", False, "redirect-refused" if 300 <= status < 400 else None)
                return prior._read_bounded(stream, status)
            except TimeoutError:
                return prior.date_probe.ProviderMetadataResponse(None, b"", False, "transport-timeout")
            except prior.date_probe.PriceDateProbeError as exc:
                _need(str(exc) == "transport-timeout", "transport_deadline_refused")
                return prior.date_probe.ProviderMetadataResponse(None, b"", False, "transport-timeout")
            except Exception:
                return prior.date_probe.ProviderMetadataResponse(None, b"", False, "transport-error")
    except prior.date_probe.PriceDateProbeError as exc:
        _need(str(exc) == "transport-timeout", "transport_deadline_refused")
        return prior.date_probe.ProviderMetadataResponse(None, b"", False, "transport-timeout")
    finally:
        if stream is not None:
            try: stream.close()
            except Exception: pass


def run_probe(expected_head, *, root=LANE_ROOT, identity=_identity, credential_reader=None, transport=None, clock=prior._now):
    fixture = root != LANE_ROOT or identity is not _identity or credential_reader is not None or transport is not None or clock is not prior._now
    _need(isinstance(root, Path) and root.is_absolute(), "absolute_probe_root_required")
    _need(not fixture or prior._outside_lane(root) and root.resolve() == root and callable(identity) and identity is not _identity
          and callable(credential_reader) and credential_reader is not prior.read_keychain_credential
          and callable(transport) and transport is not _default_transport, "invented_outside_lane_callbacks_required")
    context = None
    try:
        if fixture: prior.date_probe._fixture_denial()
        baseline = _validate_identity(identity(expected_head, root=root), expected_head, root)
        context = _Context(root, fixture, expected_head, identity, baseline)
        context.publish("reservation.json", _reservation(baseline, fixture))
        context.publish("credential-read-started.json", {"schema": SCHEMA, "maximum_credential_reads": 1, "reservation_sha256": context.published["reservation.json"]})
        try: credential = prior._credential((credential_reader if fixture else prior.read_keychain_credential)("massive"), fixture)
        except Exception: credential = None
        observed = credential is not None
        context.publish("credential-read-completed.json", {"schema": SCHEMA, "fixture_only": fixture,
            "started_sha256": context.published["credential-read-started.json"], "credential_read_observed": observed,
            "disposition": "configured-keychain-credential-read" if observed else "credential_read_refused"})
        rows, calls, disposition = [], 0, "credential_read_refused"
        if observed:
            for ordinal, (_, url) in enumerate(REQUESTS, 1):
                started = f"{ordinal:02d}-started.json"
                context.publish(started, _started(ordinal, context.published["reservation.json"])); context.check(); calls += 1
                try: response = transport(url, credential) if fixture else _default_transport(url, credential, context=context, ordinal=ordinal)
                except MassiveEvidenceProbeError:
                    if not fixture: raise
                    response = prior.date_probe.ProviderMetadataResponse(None, b"", False, "transport-error")
                except Exception: response = prior.date_probe.ProviderMetadataResponse(None, b"", False, "transport-error")
                context.check()
                _need(type(response) is prior.date_probe.ProviderMetadataResponse and type(response.body) is bytes
                      and type(response.body_complete) is bool and (response.status is None or type(response.status) is int and 100 <= response.status <= 599)
                      and (response.disposition is None or response.disposition in prior._CODES), "transport_result_refused")
                metadata = None
                disposition = response.disposition or ("http_refused" if response.status != 200 else
                    "partial-read" if not response.body_complete else "oversized-response" if len(response.body) > MAX_BODY_BYTES else None)
                if disposition is None:
                    try:
                        metadata = _projection(response.body, credential, ordinal)
                        disposition = "capability_metadata_observed" if metadata["result_count"] else "requested_day_underfill"
                    except MassiveEvidenceProbeError as exc: disposition = str(exc)
                if metadata is not None:
                    context.publish(f"{ordinal:02d}-response.json", response.body, raw=True)
                    context.publish(f"{ordinal:02d}-metadata.json", metadata)
                completed = {"schema": SCHEMA, "ordinal": ordinal, "http_status": response.status,
                    "started_sha256": context.published[started], "disposition": disposition, "metadata": metadata,
                    "body_sha256": _sha(response.body) if metadata is not None else None,
                    "body_size_bytes": len(response.body) if metadata is not None else None,
                    "untrusted_error_body_hashed_or_retained": False}
                context.publish(f"{ordinal:02d}-completed.json", completed); rows.append(completed)
                if disposition != "capability_metadata_observed": break
        result = {"schema": SCHEMA, "audit_id": AUDIT_ID, "profile": PROFILE, "owner_direction": OWNER_DIRECTION,
            "completed_at_utc": clock(), "fixture_only": fixture, "identity": baseline, "planned_requests": 3,
            "credential_read_observed": observed, "transport_invocation_count": calls, "unattempted_requests": 3 - calls,
            "status": "completed-capability-probe" if calls == 3 and disposition == "capability_metadata_observed" else "stopped-capability-probe",
            "disposition": disposition, "results": rows, "published_leaf_sha256": dict(context.published),
            "scope_reservation_sha256": context.scope_sha, "source_financial_values_interpreted": False,
            "research_looks": 0, "qc_jobs": 0, "backtests": 0, **dict.fromkeys(FALSE_FLAGS, False)}
        context.publish("complete.json", result); return result
    except MassiveEvidenceProbeError: raise
    except Exception: raise MassiveEvidenceProbeError("probe_custody_or_identity_refused") from None
    finally:
        if context is not None: context.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--expected-head", required=True); args = parser.parse_args(argv)
    try: result = run_probe(args.expected_head)
    except MassiveEvidenceProbeError as exc:
        print(json.dumps({"probe_refused": str(exc)}, sort_keys=True)); return 2
    print(json.dumps({key: result[key] for key in ("status", "disposition", "transport_invocation_count", "unattempted_requests", "research_looks", "qc_jobs", "backtests")}, sort_keys=True))
    return 0 if result["status"] == "completed-capability-probe" else 2


if __name__ == "__main__":
    raise SystemExit(main())
