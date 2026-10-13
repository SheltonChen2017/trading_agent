"""Verify at most two frozen SEC originals, privately and without credentials.

Rebuild the exact four-response disclosure capture before selecting original
document URLs it actually observed. HTTPS transport and captured bytes do not
admit per-share consideration, payment cashflow, a look, or backtest readiness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.qualify_short_interest_terminal_disclosure as terminal_reader
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _NoRedirect, _git,
    _prepare_capture_directory, _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal, _guard, _http, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock, _parse_receipt, _protected_bytes

SOURCE = Path("artifacts/short_interest/terminal_disclosure/terminal-disclosure-20261013T222323Z")
SOURCE_HEAD = "da3edc513cb64cc758388546a57c82cd3f295437"
SOURCE_REPORT_BYTES_SHA256 = "75cf8d5d02648131717b4d79071a861a1137780b4327c1fac8918651be8eaf28"
SOURCE_REPORT_SHA256 = "067ab5ffaa92983a3858d56416db7905c9e4e9e8e0892509d70e06413e830011"
SOURCE_PROTOCOL_SHA256 = "b98c369106561b291e6f01da7d1a7d5849fb1c061b494095d2946fb670a09304"
EXPECTED_PROTOCOL_SHA256 = "9ca6368824557c81610e1017f45dbc47dee8fd626cc7582b10b7caca5ee9f84c"
CAPTURE_PARENT = Path("artifacts/short_interest/terminal_originals")
MAXIMUM_REQUESTS = 2
MAXIMUM_BYTES = 16 * 1024 * 1024
USER_AGENT = "ShortInterestIndependentResearch/1.0 (personal noncommercial research)"
ACCEPT = "text/html, text/plain, application/xhtml+xml, application/xml, text/xml"
_REMOTE_REF = "refs/heads/codex/strategy-short-interest"
_MEDIA = {"text/html", "text/plain", "application/xhtml+xml", "application/xml", "text/xml"}
_ELIGIBLE_TEXT = re.compile(r"\bItem\s+2\.01\b|\breceivership\b|\bmerger\b", re.IGNORECASE)
_CODE_FILES = terminal_reader.class_reader._CODE_FILES + (
    "research/short_interest_etf/terminal_disclosure_evidence.py",
    "scripts/qualify_short_interest_terminal_disclosure.py",
    "scripts/verify_short_interest_terminal_originals.py",
)


class TerminalOriginalCaptureRefusal(CaptureRefusal):
    def __init__(self, code: str, *, status=None):
        self.code = code
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise TerminalOriginalCaptureRefusal(code)


def _read(root, path, maximum, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    return _protected_bytes(path, maximum)


def _publish_guarded(root, directory, name, value, *, head, remote, raw=False):
    _require_capture_platform()
    _guard(root, head, remote)
    (_publish if raw else _publish_json)(directory, name, value)


def _historical_source_identity(root, *, head, remote):
    _require_capture_platform()
    names = _CODE_FILES[:-1]
    _require(type(SOURCE_HEAD) is str and re.fullmatch(r"[0-9a-f]{40}", SOURCE_HEAD) is not None,
             "source_commit_invalid")
    files = []
    for name in names:
        _guard(root, head, remote)
        result = subprocess.run(["git", "show", SOURCE_HEAD + ":" + name], cwd=root,
                                capture_output=True, check=False)
        _require(type(result.returncode) is int and result.returncode == 0 and type(result.stdout) is bytes,
                 "source_code_blob_unavailable")
        files.append({"path": name, "sha256": hash_bytes(result.stdout)})
    return hash_payload({"git_commit": SOURCE_HEAD, "files": files})


def _source(root: Path, *, head=None, remote=None) -> dict:
    """Rebuild exact C receipts/report; never recapture its spent requests."""
    _require_capture_platform()
    if head is None:
        head = _git(root, "rev-parse", "HEAD")
    if remote is None:
        observed = _git(root, "ls-remote", "origin", _REMOTE_REF).split()
        _require(len(observed) == 2 and observed[1] == _REMOTE_REF, "matching_remote_ambiguous")
        remote = observed[0]
    _guard(root, head, remote)
    # Reuse the fixed protected class replay rather than a parallel reader.
    # Recheck after this composite read before using any returned assertion.
    class_source = terminal_reader._source(root)
    _guard(root, head, remote)
    protocol = terminal_reader._protocol(class_source)
    _require(protocol.sha256 == SOURCE_PROTOCOL_SHA256, "source_protocol_derivation")
    directory = root / SOURCE
    def read(name, maximum=65536):
        return _read(root, directory / name, maximum, head=head, remote=remote)
    saved_protocol = _parse_receipt(read("protocol.private.json", 131072))
    _require(canonical_json(saved_protocol) == canonical_json(protocol.to_payload()), "source_protocol_bytes")
    start, end = (_parse_receipt(read(name)) for name in ("started.json", "completed.json"))
    _require(start.get("schema") == "si-terminal-disclosure-start-v1"
             and start.get("code_head") == SOURCE_HEAD
             and start.get("code_identity_sha256") == _historical_source_identity(root, head=head, remote=remote)
             and start.get("protocol_sha256") == SOURCE_PROTOCOL_SHA256
             and start.get("source_class_report_sha256") == terminal_reader.CLASS_REPORT_SHA256
             and type(start.get("maximum_attempts")) is int and start["maximum_attempts"] == 4
             and end.get("schema") == "si-terminal-disclosure-completion-v1"
             and end.get("status") == "capture_complete" and end.get("code_head") == SOURCE_HEAD
             and end.get("protocol_sha256") == SOURCE_PROTOCOL_SHA256
             and type(end.get("http_attempts")) is int and end["http_attempts"] == 4
             and end.get("private_report_sha256") == SOURCE_REPORT_SHA256
             and end.get("backtest_result_exists") is False,
             "source_start_completion_binding")
    for receipt in (start, end):
        _require(all(type(receipt.get(name)) is int and receipt[name] == 0
                     for name in ("outcome_looks", "qc_attempts")), "source_closed_counters")
    claim = _parse_receipt(_read(root, directory.parent / ("budget-" + SOURCE_PROTOCOL_SHA256 + ".json"),
                                65536, head=head, remote=remote))
    _require(canonical_json(claim) == canonical_json({
        "schema": "si-terminal-disclosure-budget-v1", "code_head": SOURCE_HEAD,
        "remote_head": start.get("remote_head"), "run_id": directory.name,
        "protocol_sha256": SOURCE_PROTOCOL_SHA256, "maximum_attempts": 4,
        "started_at": start.get("started_at"), "resumption_or_restart_allowed": False}),
        "source_consumed_budget_binding")
    previous = _clock(start.get("started_at"))
    _require(_clock(class_source.get("retrieved_at")) <= previous, "source_class_chronology")
    captures = []
    inventory = {"protocol.private.json", "started.json", "completed.json", "evidence.private.json"}
    for ordinal, request_id in enumerate(terminal_reader.disclosures.REQUEST_IDS, 1):
        prefix = f"attempt-{ordinal:02d}"
        began = _parse_receipt(read(prefix + ".started.json"))
        received = _parse_receipt(read(prefix + ".received.json"))
        raw = read(prefix + ".raw", terminal_reader.MAXIMUM_BYTES)
        digest = protocol.request_sha256(request_id)
        _require(canonical_json(began) == canonical_json({
            "schema": "si-terminal-disclosure-request-start-v1", "attempt": ordinal,
            "request_id": request_id, "request": protocol.request(request_id), "request_sha256": digest,
            "code_head": SOURCE_HEAD, "protocol_sha256": SOURCE_PROTOCOL_SHA256,
            "started_at": began.get("started_at")}), "source_request_binding")
        _require(canonical_json(received) == canonical_json({
            "schema": "si-terminal-disclosure-response-v1", "attempt": ordinal,
            "request_id": request_id, "request_sha256": digest, "http_status": 200,
            "content_type": received.get("content_type"), "raw_path": prefix + ".raw",
            "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw), "received_at": received.get("received_at")}),
            "source_response_binding")
        requested_at, received_at = _clock(began.get("started_at")), _clock(received.get("received_at"))
        _require(previous <= requested_at <= received_at, "source_receipt_chronology")
        previous = received_at
        captures.append(terminal_reader.disclosures.CapturedDisclosureResponse(
            request_id, digest, raw, received["received_at"], 200, received["content_type"]))
        inventory.update((prefix + ".started.json", prefix + ".received.json", prefix + ".raw"))
    _guard(root, head, remote)
    _require({path.name for path in directory.iterdir()} == inventory, "source_inventory")
    raw = read("evidence.private.json", 64 * 1024 * 1024)
    _require(hash_bytes(raw) == SOURCE_REPORT_BYTES_SHA256, "source_report_bytes")
    saved = _parse_receipt(raw)
    _require(previous <= _clock(saved.get("retrieved_at")) <= _clock(end.get("completed_at")),
             "source_completion_chronology")
    rebuilt = terminal_reader.disclosures.qualify_terminal_disclosure(protocol, tuple(captures),
                                                                      retrieved_at=saved["retrieved_at"])
    report = rebuilt.to_payload()
    _require(rebuilt.sha256 == SOURCE_REPORT_SHA256 and (canonical_json(report) + "\n").encode() == raw,
             "source_report_rebuild")
    return {"report": report, "protocol": protocol, "completed_at": end["completed_at"]}


def _safe_url(value):
    _require(type(value) is str and re.fullmatch(r"https://www\.sec\.gov/Archives/[A-Za-z0-9_./-]+", value) is not None,
             "original_url_origin")
    parsed = urllib.parse.urlsplit(value)
    parts = parsed.path.removeprefix("/Archives/").split("/")
    _require(parsed.scheme == "https" and parsed.netloc == "www.sec.gov"
             and not parsed.query and not parsed.fragment and all(part not in {"", ".", ".."} for part in parts),
             "original_url_path")
    return value


def build_protocol(source: dict) -> dict:
    """Deterministic source-only selection; no fallback ticker or extra link."""
    _require(type(source) is dict and type(source.get("report")) is dict,
             "originals_source_report_shape")
    _require(type(USER_AGENT) is str and USER_AGENT ==
             "ShortInterestIndependentResearch/1.0 (personal noncommercial research)", "user_agent_changed")
    _require(type(MAXIMUM_REQUESTS) is int and MAXIMUM_REQUESTS == 2
             and type(MAXIMUM_BYTES) is int and MAXIMUM_BYTES == 16 * 1024 * 1024,
             "originals_policy_changed")
    # Seal-check a detached snapshot before selecting a URL. A stale digest
    # field cannot authenticate caller mutations to otherwise safe SEC paths.
    report = json.loads(canonical_json(source["report"]))
    source_protocol = source["protocol"]
    _require(type(source_protocol) is terminal_reader.disclosures.DisclosureProtocol
             and source_protocol.sha256 == SOURCE_PROTOCOL_SHA256
             and report.get("report_sha256") == SOURCE_REPORT_SHA256
             and hash_payload({name: value for name, value in report.items() if name != "report_sha256"})
                 == SOURCE_REPORT_SHA256
             and report.get("protocol_sha256") == SOURCE_PROTOCOL_SHA256,
             "originals_source_protocol_binding")
    requests, missing = [], []
    ciks = source_protocol.to_payload()["issuer_CIKs"]
    for position, (case, first, last) in enumerate(terminal_reader.disclosures.WINDOWS):
        tables = [table for table in report["tables"] if table.get("request_id") == "text-" + case]
        _require(len(tables) == 1, "originals_text_inventory")
        candidates = []
        for row in tables[0]["records"]:
            metadata = row.get("metadata")
            if row.get("inventory_status") != "core_Items_inventory" or type(metadata) is not dict:
                continue
            _require(metadata.get("cik") == ciks[position] and first <= metadata["filing_date"] <= last,
                     "originals_issuer_window")
            text = row.get("items_text")
            if type(text) is str and _ELIGIBLE_TEXT.search(text):
                url = _safe_url(metadata.get("filing_url"))
                candidates.append((metadata["filing_date"], metadata["accession_number"], url, row["origin"]))
        if not candidates:
            missing.append({"case": case, "code": "terminal_original_candidate_unavailable"})
            continue
        at, accession, url, origin = min(candidates, key=lambda value: (value[0], value[1]))
        requests.append({"request_id": "original-" + case, "method": "GET", "url": url,
                         "headers": {"Accept": ACCEPT, "User-Agent": USER_AGENT},
                         "case": case, "issuer_CIK": ciks[position], "filing_date": at,
                         "accession_number": accession, "source_row_origin": origin})
    _require(0 < len(requests) <= MAXIMUM_REQUESTS, "terminal_original_candidate_unavailable")
    _require(len({request["url"] for request in requests}) == len(requests), "original_document_duplicate")
    return {"schema": "si-terminal-originals-protocol-v1", "source_path": str(SOURCE),
            "source_code_head": SOURCE_HEAD, "source_report_bytes_sha256": SOURCE_REPORT_BYTES_SHA256,
            "source_report_sha256": SOURCE_REPORT_SHA256, "source_protocol_sha256": SOURCE_PROTOCOL_SHA256,
            "source_class_report_sha256": terminal_reader.CLASS_REPORT_SHA256,
            "source_completed_at": source["completed_at"], "requests": requests, "missing_cases": missing,
            "selection_rule": "earliest_captured_filing_date_accession_valid_core_Items_Item_2.01_receivership_or_merger",
            "population_scope": "two_source_bound_cases_not_full_study_or_exhaustive_filing_inventory",
            "maximum_attempts": len(requests), "maximum_response_bytes": MAXIMUM_BYTES,
            "automatic_retries": 0, "redirects": False, "proxies": False,
            "document_rule": "observed_exact_HTTPS_SEC_Archives_URL_only_no_links_or_exhibit_follow",
            "issuer_rule": "CIK_is_issuer_association_not_share_class_consideration_authority",
            "publication_scope": "private_only_source_document_transport_verification",
            "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}


def _capture(root, directory, protocol, opener, *, head, remote, started_at):
    _require_capture_platform()
    _require(type(protocol) is dict, "original_protocol_shape")
    # Neither an opener callback nor a retained caller alias may replace a
    # later request descriptor after the prospective whole-protocol check.
    protocol = json.loads(canonical_json(protocol))
    _require(hash_payload(protocol) == EXPECTED_PROTOCOL_SHA256, "originals_freeze_pending_or_changed")
    previous = _clock(started_at)
    receipts = []
    for ordinal, descriptor in enumerate(protocol["requests"], 1):
        _require(ordinal <= MAXIMUM_REQUESTS and descriptor["method"] == "GET"
                 and descriptor["headers"] == {"Accept": ACCEPT, "User-Agent": USER_AGENT},
                 "original_request_descriptor")
        _safe_url(descriptor["url"])
        digest, prefix = hash_payload(descriptor), f"attempt-{ordinal:02d}"
        began = _utc_now()
        _require(previous <= _clock(began), "original_capture_chronology")
        _publish_guarded(root, directory, prefix + ".started.json", {
            "schema": "si-terminal-original-request-start-v1", "attempt": ordinal,
            "request_id": descriptor["request_id"], "request": descriptor, "request_sha256": digest,
            "code_head": head, "protocol_sha256": EXPECTED_PROTOCOL_SHA256, "started_at": began},
            head=head, remote=remote)
        status = None
        try:
            _guard(root, head, remote)
            request = urllib.request.Request(descriptor["url"], headers=descriptor["headers"], method="GET")
            raw, media, status = _http(opener, request, MAXIMUM_BYTES)
            received_at = _utc_now()
            _publish_guarded(root, directory, prefix + ".raw", raw, head=head, remote=remote, raw=True)
            receipt = {"schema": "si-terminal-original-response-v1", "attempt": ordinal,
                       "request_id": descriptor["request_id"], "request_sha256": digest,
                       "http_status": status, "content_type": media, "raw_path": prefix + ".raw",
                       "raw_bytes": len(raw), "raw_sha256": hash_bytes(raw), "received_at": received_at}
            _publish_guarded(root, directory, prefix + ".received.json", receipt, head=head, remote=remote)
            _require(raw and media.split(";", 1)[0].strip().lower() in _MEDIA, "original_body_or_media_refused")
            _require(_clock(began) <= _clock(received_at), "original_capture_chronology")
            previous = _clock(received_at)
            receipts.append({"descriptor": descriptor, "receipt": receipt,
                             "HTTPS_transport_origin_verified": True,
                             "terminal_economics_admitted": False, "payment_cash_settlement_verified": False})
        except (CaptureRefusal, ValueError, TypeError, OSError) as exc:
            safe = type(exc) in (TerminalOriginalCaptureRefusal, SharadarCaptureRefusal)
            _publish_guarded(root, directory, prefix + ".refused.json", {
                "schema": "si-terminal-original-request-refusal-v1", "attempt": ordinal,
                "request_id": descriptor["request_id"], "code": exc.code if safe else "request_refused",
                "http_status": exc.http_status if safe else status, "refused_at": _utc_now()}, head=head, remote=remote)
            raise
    retrieved_at = _utc_now()
    _require(previous <= _clock(retrieved_at), "original_capture_chronology")
    evidence = {"schema": "si-terminal-original-evidence-v1", "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
                "source_report_sha256": SOURCE_REPORT_SHA256, "retrieved_at": retrieved_at,
                "documents": receipts, "missing_cases": protocol["missing_cases"],
                "terminal_economics_admitted": False, "payment_cash_settlement_verified": False,
                "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    evidence["report_sha256"] = hash_payload(evidence)
    _publish_guarded(root, directory, "originals.private.json", evidence, head=head, remote=remote)
    completed_at = _utc_now()
    _require(_clock(retrieved_at) <= _clock(completed_at), "original_capture_chronology")
    result = {"schema": "si-terminal-original-completion-v1", "status": "capture_complete",
              "code_head": head, "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
              "http_attempts": len(receipts), "private_report_sha256": evidence["report_sha256"],
              "completed_at": completed_at, "outcome_looks": 0, "qc_attempts": 0,
              "backtest_result_exists": False}
    _publish_guarded(root, directory, "completed.json", result, head=head, remote=remote)
    return result


def _run(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    source = _source(root, head=head, remote=remote)
    protocol = build_protocol(source)
    _require(hash_payload(protocol) == EXPECTED_PROTOCOL_SHA256, "originals_freeze_pending_or_changed")
    started_at = _utc_now()
    _require(_clock(source["completed_at"]) <= _clock(started_at), "original_capture_chronology")
    target = root / CAPTURE_PARENT / ("terminal-originals-" + _clock(started_at).strftime("%Y%m%dT%H%M%SZ"))
    _require(_git(root, "check-ignore", str(target)) == str(target), "original_capture_not_ignored")
    _guard(root, head, remote)
    directory = _prepare_capture_directory(target)
    try:
        _publish_guarded(root, directory.parent, "budget-" + EXPECTED_PROTOCOL_SHA256 + ".json", {
            "schema": "si-terminal-original-budget-v1", "code_head": head, "remote_head": remote,
            "run_id": directory.name, "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            "source_report_sha256": SOURCE_REPORT_SHA256, "maximum_attempts": len(protocol["requests"]),
            "started_at": started_at, "resumption_or_restart_allowed": False}, head=head, remote=remote)
        _publish_guarded(root, directory, "protocol.private.json", protocol, head=head, remote=remote)
        files = []
        for name in _CODE_FILES:
            _guard(root, head, remote)
            files.append({"path": name, "sha256": hash_bytes((root / name).read_bytes())})
        _publish_guarded(root, directory, "started.json", {
            "schema": "si-terminal-original-start-v1", "code_head": head, "remote_head": remote,
            "code_identity_sha256": hash_payload({"git_commit": head, "files": files}),
            "protocol_sha256": EXPECTED_PROTOCOL_SHA256, "started_at": started_at,
            "maximum_attempts": len(protocol["requests"]), "outcome_looks": 0, "qc_attempts": 0},
            head=head, remote=remote)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        return _capture(root, directory, protocol, opener, head=head, remote=remote, started_at=started_at)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        safe = type(exc) in (TerminalOriginalCaptureRefusal, SharadarCaptureRefusal)
        _publish_guarded(root, directory, "refused.json", {
            "schema": "si-terminal-original-refusal-v1", "status": "capture_refused",
            "code": exc.code if safe else "owned_capture_refused", "http_status": exc.http_status if safe else None,
            "refused_at": _utc_now(), "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False},
            head=head, remote=remote)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        _require_capture_platform()
        result = _run(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        safe = type(exc) in (TerminalOriginalCaptureRefusal, SharadarCaptureRefusal, CapturePlatformRefusal)
        result = {"status": "capture_refused", "code": exc.code if safe else "local_preflight_refused",
                  "http_status": exc.http_status if safe else None, "outcome_looks": 0,
                  "qc_attempts": 0, "backtest_result_exists": False}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
