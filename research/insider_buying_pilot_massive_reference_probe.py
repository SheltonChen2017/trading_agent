"""One separately journaled historical-reference capability probe; no prices.

Only the fixed All Tickers A/2020-01-02 metadata request is supported.
Historical reference fields are discovery evidence, not first-public knowledge,
SEC-title identity, QC SID, complete coverage, or research/backtest authority.
No overview/fundamental/quote/trade endpoint, redirect, paging or retry exists.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import ssl
import sys
from urllib import error, request

from research import insider_buying_earnings_archive_assessment_runner as custody
from research import insider_buying_eodhd_price_date_probe as date_probe
from research import insider_buying_sharadar_price_coverage_capture as publication
from research.insider_buying_keychain_credentials import KeychainCredential, read_keychain_credential
from research.insider_buying_provider_metadata_audit import _now
from research.insider_buying_sharadar_reference_qualification import _outside_lane, _screen_credential


LANE_ROOT, LANE_BRANCH = custody.LANE_ROOT, custody.LANE_BRANCH
SELF_PATH = "research/insider_buying_pilot_massive_reference_probe.py"
SCHEMA = "insider-pilot-massive-historical-reference-probe-v1"
PROFILE = "massive-all-tickers-a-20200102-metadata-only-v1"
OWNER_DIRECTION = "owner:2026-10-24:separate-2021-2025-pilot-owned-sources-no-qc"
OUTPUT_PARTS = ("artifacts", "insider_buying", "pilot_massive_reference_v1")
AUDIT_ID = "ib-pilot-massive-reference-20200102-20261024-once"
URL = ("https://api.massive.com/v3/reference/tickers?ticker=A&market=stocks&active=true"
       "&date=2020-01-02&sort=ticker&order=asc&limit=1")
ASOF = "2020-01-02"
MAX_BODY_BYTES = 256 * 1024
MAX_CONTROL_BYTES = 256 * 1024
TIMEOUT_SECONDS = 15
EMPTY_CACHE_PREFIX = "/var/empty/insider-pilot-massive-reference-no-bytecode"
_SHA, _HEAD = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[0-9a-f]{40}\Z")
_ROW_KEYS = frozenset({"active", "cik", "composite_figi", "currency_name", "currency_symbol",
    "delisted_utc", "last_updated_utc", "locale", "market", "name", "primary_exchange",
    "share_class_figi", "ticker", "type", "base_currency_name", "base_currency_symbol"})
_REQUIRED_ROW_KEYS = frozenset({"active", "cik", "locale", "market", "name", "primary_exchange",
    "share_class_figi", "ticker", "type"})
_CODES = date_probe._TRANSPORT_CODES
FALSE_FLAGS = tuple(dict.fromkeys((*date_probe.FALSE_FLAGS, "historical_identity_verified",
    "first_public_knowledge_verified", "qc_sid_bound", "full_pilot_coverage_verified")))


class MassiveReferenceProbeError(ValueError):
    """Fixed codes only; no source, credential, URL or exception contents."""


class _IntegerLexeme(str):
    """Opaque JSON integer text; only exact count=1 is a permitted control."""


class _FloatLexeme(str):
    """Opaque JSON numeric text, never interpreted as a financial number."""


def _need(condition, code):
    if not condition:
        raise MassiveReferenceProbeError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return publication._sha(raw)


def _profile():
    return {"method": "GET", "endpoint": "https://api.massive.com/v3/reference/tickers",
        "ticker": "A", "market": "stocks", "active": True, "date": ASOF,
        "sort": "ticker", "order": "asc", "limit": 1, "maximum_attempts": 1,
        "maximum_credential_reads": 1, "timeout_seconds": TIMEOUT_SECONDS,
        "maximum_response_bytes": MAX_BODY_BYTES}


def _identity(expected_head, *, root=LANE_ROOT):
    _need(root == LANE_ROOT and Path(__file__).resolve() == LANE_ROOT / SELF_PATH,
        "designated_committed_source_required")
    _need(sys.flags.isolated == sys.flags.no_user_site == sys.flags.no_site == sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "isolated_source_interpreter_required")
    identity = custody._identity(expected_head)
    _need({SELF_PATH, "research/insider_buying_keychain_credentials.py",
        "research/insider_buying_eodhd_price_date_probe.py",
        "research/insider_buying_sharadar_price_coverage_capture.py"} <= set(identity["source_sha256"]),
        "reference_source_closure_incomplete")
    return identity


def _validate_identity(value, expected_head, root):
    _need(type(expected_head) is str and _HEAD.fullmatch(expected_head) is not None,
        "exact_clean_identity_required")
    try:
        return date_probe._validate_identity(value, expected_head, root)
    except (ValueError, TypeError, KeyError):
        raise MassiveReferenceProbeError("exact_clean_identity_required") from None


def _credential(value, fixture):
    _need(type(value) is KeychainCredential and value.provider == "massive"
        and type(value.fixture_only) is bool and value.fixture_only is fixture
        and type(value.value) is str and re.fullmatch(r"[!-~]{1,4096}", value.value) is not None
        and value.value.casefold() not in {"demo", "test-api-key"}, "credential_read_refused")
    return value


def _json(raw):
    def unique(pairs):
        body = {}
        for key, value in pairs:
            _need(key not in body, "duplicate_metadata_key_refused")
            body[key] = value
        return body
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_int=_IntegerLexeme,
            parse_float=_FloatLexeme, parse_constant=lambda _: _need(False, "nonfinite_metadata_refused"))
    except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError):
        raise MassiveReferenceProbeError("source_json_refused") from None


def _projection(raw, credential):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES, "metadata_resource_refused")
    body = _json(raw)
    try:
        _screen_credential(raw, body, credential)
    except (ValueError, UnicodeError):
        raise MassiveReferenceProbeError("credential_echo_refused") from None
    pending = [(body, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop(); nodes += 1
        _need(nodes <= 4096 and depth <= 24, "metadata_structure_bound_refused")
        if type(value) is dict:
            _need(len(value) <= 32 and all(type(key) is str and len(key) <= 128 for key in value),
                "metadata_structure_bound_refused")
            pending.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            _need(len(value) <= 16, "metadata_structure_bound_refused")
            pending.extend((item, depth + 1) for item in value)
        elif type(value) is str:
            _need(len(value) <= 8192 and not any(ord(char) < 32 for char in value), "metadata_text_refused")
    _need(type(body) is dict and {"results", "status", "request_id", "count"} <= set(body)
        and set(body) <= {"results", "status", "request_id", "count", "next_url"}
        and body["status"] == "OK" and type(body["status"]) is str
        and type(body["count"]) is _IntegerLexeme and body["count"] == "1"
        and type(body["request_id"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", body["request_id"]) is not None
        and body.get("next_url") is None and type(body["results"]) is list and len(body["results"]) == 1,
        "fixed_single_reference_envelope_refused")
    row = body["results"][0]
    _need(type(row) is dict and _REQUIRED_ROW_KEYS <= set(row) <= _ROW_KEYS
        and row["active"] is True and all(type(value) is str for key,value in row.items() if key != "active"),
        "reference_only_fields_required")
    _need(row["ticker"] == "A" and row["locale"] == "us" and row["market"] == "stocks" and row["type"] == "CS"
        and re.fullmatch(r"[0-9]{1,10}", row["cik"]) is not None and int(row["cik"]) > 0
        and re.fullmatch(r"[A-Z0-9]{12}", row["share_class_figi"]) is not None
        and re.fullmatch(r"[A-Z0-9]{4}", row["primary_exchange"]) is not None
        and 0 < len(row["name"]) <= 8192, "requested_reference_identity_refused")
    if "composite_figi" in row:
        _need(re.fullmatch(r"[A-Z0-9]{12}", row["composite_figi"]) is not None, "reference_identifier_refused")
    for key in ("last_updated_utc", "delisted_utc"):
        if key in row:
            try:
                stamp = datetime.fromisoformat(row[key].replace("Z", "+00:00"))
                _need(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0, "reference_timestamp_refused")
            except ValueError:
                raise MassiveReferenceProbeError("reference_timestamp_refused") from None
    return {"schema": SCHEMA + "/metadata", "requested_asof_date": ASOF,
        "reference_count": 1, "source_reference": dict(row), "response_body_sha256": _sha(raw),
        "response_body_bytes": len(raw), "historical_reference_capability_observed": True,
        "numeric_financial_fields_interpreted": False, **dict.fromkeys(FALSE_FLAGS, False)}


def _reservation(identity, fixture):
    return {"schema": SCHEMA, "audit_id": AUDIT_ID, "profile": PROFILE, "owner_direction": OWNER_DIRECTION,
        "identity": identity, "fixture_only": fixture, "request": _profile(), "url": URL,
        "maximum_attempts": 1, "retry_redirect_paging_fallback_permitted": False, **dict.fromkeys(FALSE_FLAGS, False)}


def _started(reservation_sha):
    return {"schema": SCHEMA, "profile": PROFILE, "url": URL, "method": "GET",
        "maximum_attempts": 1, "reservation_sha256": reservation_sha}


class _Context:
    """Fresh private scope; existing settled-output/hash policy, no old latch."""
    def __init__(self, root, fixture, head, identity, baseline):
        self.root,self.fixture,self.head,self.identity,self.baseline = root,fixture,head,identity,baseline
        self.parent=self.directory=None
        self.published,self.versions={},{}
        try:
            self.parent=custody._Chain(root,OUTPUT_PARTS,create=True)
            _need(os.fstat(self.parent.fd).st_uid == os.geteuid() and not os.listdir(self.parent.fd),
                "consumed_or_ambiguous_scope_refused")
            self.scope_sha,self.scope_version=publication._publish_raw(self.parent.fd,"scope-reservation.json",
                _raw({"schema":SCHEMA,"audit_id":AUDIT_ID,"profile":PROFILE,"request":_profile(),"maximum_attempts":1}))
            os.mkdir(AUDIT_ID,0o700,dir_fd=self.parent.fd);os.fsync(self.parent.fd)
            self.directory=custody._Chain(root,(*OUTPUT_PARTS,AUDIT_ID));self.check()
        except BaseException:self.close();raise

    def check(self):
        _need(_validate_identity(self.identity(self.head,root=self.root),self.head,self.root)==self.baseline,
            "lane_changed_during_probe")
        self.parent.recheck();self.directory.recheck()
        _need(set(os.listdir(self.parent.fd))=={"scope-reservation.json",AUDIT_ID}
            and set(os.listdir(self.directory.fd))==set(self.published), "probe_inventory_changed")
        raw,version=publication._leaf(self.parent.fd,"scope-reservation.json",MAX_CONTROL_BYTES)
        _need(_sha(raw)==self.scope_sha and version==self.scope_version,"scope_reservation_changed")
        for name,digest in self.published.items():
            raw,version=publication._leaf(self.directory.fd,name,MAX_CONTROL_BYTES)
            _need(_sha(raw)==digest and version==self.versions[name],"published_output_changed")
        self.parent.recheck();self.directory.recheck()

    def publish(self,name,body,*,raw=False):
        self.check();value=body if raw else _raw(body)
        _need(type(value) is bytes and 0<len(value)<=MAX_CONTROL_BYTES,"publication_bound_refused")
        self.published[name],self.versions[name]=publication._publish_raw(self.directory.fd,name,value);self.check()

    def close(self):
        primary=sys.exc_info()[0] is not None;failed=False
        for name in ("directory","parent"):
            held=getattr(self,name,None);setattr(self,name,None)
            if held is not None:
                try:held.close()
                except BaseException:failed=True
        if failed and not primary:raise MassiveReferenceProbeError("context_cleanup_refused") from None


def _read_bounded(stream,status):
    try:
        _need(callable(getattr(stream.headers,"get_all",None)),"partial-read")
        enc=stream.headers.get_all("Content-Encoding",[])
        lengths=stream.headers.get_all("Content-Length",[])
        transfers=stream.headers.get_all("Transfer-Encoding",[])
        _need(all(type(items) is list and all(type(value) is str for value in items)
            for items in (enc,lengths,transfers)),"partial-read")
        _need(len(enc)<=1 and (not enc or enc[0].strip().lower()=="identity"),"unsupported-content-encoding")
        _need(len(lengths)<=1,"invalid-content-length")
        _need(len(transfers)<=1 and (not transfers or not lengths and transfers[0].strip().lower()=="chunked"),"partial-read")
        length=None
        if lengths:
            _need(re.fullmatch(r"[0-9]{1,20}",lengths[0]) is not None,"invalid-content-length")
            length=int(lengths[0]);_need(length<=MAX_BODY_BYTES,"oversized-response")
        chunks=[];count=0
        while count<=MAX_BODY_BYTES:
            requested=MAX_BODY_BYTES+1-count;part=stream.read(requested)
            _need(type(part) is bytes and len(part)<=requested,"partial-read")
            if not part:
                _need(length is None or count==length,"truncated-response")
                return date_probe.ProviderMetadataResponse(status,b"".join(chunks),True)
            chunks.append(part);count+=len(part)
        raise MassiveReferenceProbeError("oversized-response")
    except MassiveReferenceProbeError as exc:return date_probe.ProviderMetadataResponse(status,b"",False,str(exc))
    except Exception:return date_probe.ProviderMetadataResponse(status,b"",False,"partial-read")


def _default_transport(url,credential,*,context):
    _need(type(context) is _Context and context.root==LANE_ROOT and context.fixture is False,"real_probe_context_required")
    _credential(credential,False);_need(url==URL,"fixed_reference_url_required");context.check()
    expected={"reservation.json","credential-read-started.json","credential-read-completed.json","01-reference-started.json"}
    _need(set(context.published)==expected,"observed_started_journal_required")
    leaves={name:date_probe._json(publication._leaf(context.directory.fd,name,MAX_CONTROL_BYTES)[0]) for name in expected}
    _need(leaves["reservation.json"]==_reservation(context.baseline,False)
        and leaves["01-reference-started.json"]==_started(context.published["reservation.json"])
        and leaves["credential-read-started.json"]=={"schema":SCHEMA,"maximum_credential_reads":1,"reservation_sha256":context.published["reservation.json"]}
        and leaves["credential-read-completed.json"]=={"schema":SCHEMA,"fixture_only":False,
            "started_sha256":context.published["credential-read-started.json"],"credential_read_observed":True,
            "disposition":"configured-keychain-credential-read"},"observed_started_journal_required")
    context.check()
    opener=request.build_opener(request.ProxyHandler({}),date_probe._DenyRedirect(),
        request.HTTPSHandler(context=ssl.create_default_context()))
    item=request.Request(URL,headers={"Authorization":"Bearer "+credential.value,"Accept":"application/json","Accept-Encoding":"identity"},method="GET")
    stream=None
    try:
        with date_probe._Deadline():
            context.check()
            _need(item.full_url==URL and item.get_method()=="GET" and item.get_header("Authorization")=="Bearer "+credential.value,
                "fixed_reference_request_required")
            try:
                try:stream=opener.open(item,timeout=TIMEOUT_SECONDS)
                except error.HTTPError as exc:stream=exc
                status=stream.getcode()
                if type(status) is not int or not 100<=status<=599:return date_probe.ProviderMetadataResponse(None,b"",False,"invalid-http-status")
                if stream.geturl()!=URL:return date_probe.ProviderMetadataResponse(status,b"",False,"response-origin-mismatch")
                if status!=200:return date_probe.ProviderMetadataResponse(status,b"",False,"redirect-refused" if 300<=status<400 else None)
                return _read_bounded(stream,status)
            except TimeoutError:return date_probe.ProviderMetadataResponse(None,b"",False,"transport-timeout")
            except date_probe.PriceDateProbeError as exc:
                _need(str(exc)=="transport-timeout","transport_deadline_refused")
                return date_probe.ProviderMetadataResponse(None,b"",False,"transport-timeout")
            except Exception:return date_probe.ProviderMetadataResponse(None,b"",False,"transport-error")
    except date_probe.PriceDateProbeError as exc:
        # The wall alarm also covers the last source/custody recheck. A timeout
        # before opener.open is not proof of an HTTP dispatch or HTTP refusal.
        _need(str(exc)=="transport-timeout","transport_deadline_refused")
        return date_probe.ProviderMetadataResponse(None,b"",False,"transport-timeout")
    finally:
        if stream is not None:
            try:stream.close()
            except Exception:pass


def run_probe(expected_head,*,root=LANE_ROOT,identity=_identity,credential_reader=None,transport=None,clock=_now):
    fixture=root!=LANE_ROOT or identity is not _identity or credential_reader is not None or transport is not None or clock is not _now
    _need(isinstance(root,Path) and root.is_absolute(),"absolute_probe_root_required")
    _need(not fixture or _outside_lane(root) and root.resolve()==root and callable(identity) and identity is not _identity
        and callable(credential_reader) and credential_reader is not read_keychain_credential
        and callable(transport) and transport is not _default_transport,"invented_outside_lane_callbacks_required")
    context=None
    try:
        if fixture:date_probe._fixture_denial()
        baseline=_validate_identity(identity(expected_head,root=root),expected_head,root)
        context=_Context(root,fixture,expected_head,identity,baseline)
        context.publish("reservation.json",_reservation(baseline,fixture))
        context.publish("credential-read-started.json",{"schema":SCHEMA,"maximum_credential_reads":1,"reservation_sha256":context.published["reservation.json"]})
        credential=None
        try:credential=_credential((credential_reader if fixture else read_keychain_credential)("massive"),fixture)
        except Exception:credential=None
        observed=credential is not None
        context.publish("credential-read-completed.json",{"schema":SCHEMA,"fixture_only":fixture,
            "started_sha256":context.published["credential-read-started.json"],"credential_read_observed":observed,
            "disposition":"configured-keychain-credential-read" if observed else "credential_read_refused"})
        response=metadata=None;calls=0;disposition="credential_read_refused"
        if observed:
            context.publish("01-reference-started.json",_started(context.published["reservation.json"]));context.check();calls=1
            try:response=transport(URL,credential) if fixture else _default_transport(URL,credential,context=context)
            except MassiveReferenceProbeError:
                if not fixture:raise
                response=date_probe.ProviderMetadataResponse(None,b"",False,"transport-error")
            except Exception:response=date_probe.ProviderMetadataResponse(None,b"",False,"transport-error")
            context.check()
            _need(type(response) is date_probe.ProviderMetadataResponse and type(response.body) is bytes
                and type(response.body_complete) is bool
                and (response.status is None or type(response.status) is int and 100<=response.status<=599)
                and (response.disposition is None or response.disposition in _CODES),"transport_result_refused")
            disposition=response.disposition
            if response.status!=200:disposition=disposition or "http_refused"
            elif disposition is None:
                disposition="partial-read" if not response.body_complete else "oversized-response" if len(response.body)>MAX_BODY_BYTES else None
                if disposition is None:
                    try:metadata=_projection(response.body,credential);disposition="historical-reference-capability-observed"
                    except MassiveReferenceProbeError as exc:disposition=str(exc)
            if metadata is not None:
                context.publish("01-reference-response.json",response.body,raw=True);context.publish("01-reference-metadata.json",metadata)
            context.publish("01-reference-completed.json",{"schema":SCHEMA,"http_status":response.status,
                "started_sha256":context.published["01-reference-started.json"],"disposition":disposition,
                "metadata_observed":metadata is not None,"body_sha256":_sha(response.body) if metadata is not None else None,
                "body_size_bytes":len(response.body) if metadata is not None else None,"untrusted_error_body_hashed_or_retained":False})
        result={"schema":SCHEMA,"audit_id":AUDIT_ID,"profile":PROFILE,"owner_direction":OWNER_DIRECTION,
            "completed_at_utc":clock(),"fixture_only":fixture,"identity":baseline,"planned_requests":1,
            "credential_read_observed":observed,"transport_invocation_count":calls,"http_status":None if response is None else response.status,
            "status":"completed-reference-metadata-probe" if metadata is not None else "stopped-reference-metadata-probe",
            "disposition":disposition,"metadata":metadata,"published_leaf_sha256":dict(context.published),
            "scope_reservation_sha256":context.scope_sha,"price_or_return_values_interpreted":False,
            "research_looks":0,"qc_jobs":0,"backtests":0,**dict.fromkeys(FALSE_FLAGS,False)}
        context.publish("complete.json",result);return result
    except MassiveReferenceProbeError:raise
    except Exception:raise MassiveReferenceProbeError("probe_custody_or_identity_refused") from None
    finally:
        if context is not None:context.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--expected-head",required=True);args=parser.parse_args(argv)
    try:result=run_probe(args.expected_head)
    except MassiveReferenceProbeError as exc:
        print(json.dumps({"probe_refused":str(exc)},sort_keys=True));return 2
    print(json.dumps({key:result[key] for key in ("status","http_status","disposition","transport_invocation_count","research_looks","qc_jobs","backtests")},sort_keys=True))
    return 0 if result["status"]=="completed-reference-metadata-probe" else 2


if __name__=="__main__":raise SystemExit(main())
