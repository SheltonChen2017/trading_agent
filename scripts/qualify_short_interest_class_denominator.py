"""One prospective, private thirty-request class/denominator supplement.

The old master, native index and rational observations are verified, never
re-requested. This source-only capture is not historical interval admission,
an outcome join, full-study input qualification, or a backtest. Provider rows
and fitness conclusions remain in protected ignored storage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.massive_class_denominator as contract
import scripts.build_short_interest_native_master_offline as native_builder
import scripts.finalize_short_interest_master_offline as finalizer
import scripts.qualify_short_interest_action_supplement as companion_reader
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _NoRedirect, _git,
    _prepare_capture_directory, _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import (
    SharadarCaptureRefusal, _guard, _http, _refuse_credential_echo, _utc_now,
)
from scripts.qualify_short_interest_action_supplement import (
    _clock, _existing_key, _parse_receipt, _protected_bytes,
)

CAPTURE_PARENT = Path("artifacts/short_interest/massive_class_denominator")
NATIVE_SOURCE_HEAD = "4acd6222b5617af57e3ca6bb4dddf1682db9388d"
NATIVE_STARTED_AT = "2026-10-12T07:22:43.794403Z"
NATIVE_COMPLETED_AT = "2026-10-12T07:24:29.013623Z"
NATIVE_INDEX_BYTES_SHA256 = "7612d2326a846c1717ec5d56a07b3ad2b1e5feb36ed7d89c3a798fde147d3b22"
NATIVE_INDEX_PAYLOAD_SHA256 = "e42e6213f744c75a15e1feee2c2156aaac3749999f53bb82821fbc856dae798f"
OBSERVATION_BYTES_SHA256 = "d8fff2685b60be6b9398ae911ba8bd088729ec376bd1dd901f004e1c0977204a"
OBSERVATION_PAYLOAD_SHA256 = "d6b10eaccebe6f9acef1700c2d16c6999ac65921c46be23c189fcf1457aca81c"
MAXIMUM_REQUESTS = 30
MAXIMUM_BYTES = 2 * 1024 * 1024
_CODE_FILES = (
    "data/hashing.py", "ml/immutable_io.py",
    "research/short_interest_etf/contracts.py",
    "research/short_interest_etf/finra_source_qualification.py",
    "research/short_interest_etf/massive_action_supplement.py",
    "research/short_interest_etf/massive_class_denominator.py",
    "research/short_interest_etf/sharadar_actual_input_binding.py",
    "research/short_interest_etf/sharadar_companion_qualification.py",
    "research/short_interest_etf/sharadar_securities_master.py",
    "research/short_interest_etf/sharadar_master_segments.py",
    "research/short_interest_etf/sharadar_native_master_index.py",
    "research/short_interest_etf/sharadar_native_observations.py",
    "scripts/qualify_finra_short_interest.py",
    "scripts/qualify_sharadar_companion.py",
    "scripts/qualify_short_interest_action_supplement.py",
    "scripts/capture_short_interest_securities_master.py",
    "scripts/finalize_short_interest_master_offline.py",
    "scripts/build_short_interest_native_master_offline.py",
    "scripts/qualify_short_interest_class_denominator.py",
)


class ClassDenominatorCaptureRefusal(CaptureRefusal):
    """Only fixed internal codes and validated HTTP integers may be emitted."""

    def __init__(self, code: str, *, status: int | None = None):
        self.code = code
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None
        super().__init__(code)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ClassDenominatorCaptureRefusal(reason)


def _run_id(started_at: str) -> str:
    return "massive-class-" + _clock(started_at).strftime("%Y%m%dT%H%M%SZ")


def _validated_protocol() -> dict:
    value = contract.denominator_protocol()
    _require(type(value) is dict and hash_payload(value) == contract.PROTOCOL_SHA256
             and type(value.get("maximum_requests")) is int
             and value["maximum_requests"] == MAXIMUM_REQUESTS
             and type(value.get("request_ids")) is list
             and tuple(value["request_ids"]) == contract.REQUEST_IDS
             and len(contract.REQUEST_IDS) == MAXIMUM_REQUESTS
             and value.get("requests") == [contract.massive_request(rid) for rid in contract.REQUEST_IDS],
             "frozen_request_inventory")
    _require(contract.MAXIMUM_RESPONSE_BYTES == MAXIMUM_BYTES, "response_size_contract")
    return value


def _source_pins() -> dict:
    return {
        "master_capture_path": str(finalizer.SOURCE),
        "master_capture_inventory_sha256": finalizer.SOURCE_INVENTORY_SHA256,
        "master_budget_file_sha256": finalizer.BUDGET_SHA256,
        "master_offline_index_sha256": native_builder.SOURCE_INDEX_SHA256,
        "native_source_path": str(native_builder.OUTPUT), "native_source_head": NATIVE_SOURCE_HEAD,
        "native_started_at": NATIVE_STARTED_AT, "native_completed_at": NATIVE_COMPLETED_AT,
        "native_index_bytes_sha256": NATIVE_INDEX_BYTES_SHA256,
        "native_index_sha256": NATIVE_INDEX_PAYLOAD_SHA256,
        "native_observation_bytes_sha256": OBSERVATION_BYTES_SHA256,
        "native_observation_binding_sha256": OBSERVATION_PAYLOAD_SHA256,
        "companion_source_path": str(companion_reader.SHARADAR_SOURCE),
        "companion_report_file_sha256": companion_reader.SHARADAR_REPORT_FILE_SHA256,
        "companion_start_file_sha256": companion_reader.SHARADAR_START_FILE_SHA256,
    }


def capture_protocol() -> dict:
    return {
        "schema": "si-massive-class-capture-protocol-v1",
        "qualification_protocol_sha256": contract.PROTOCOL_SHA256,
        "qualification_protocol": _validated_protocol(), "source_pins": _source_pins(),
        "capture_parent": str(CAPTURE_PARENT), "maximum_attempts": MAXIMUM_REQUESTS,
        "maximum_response_bytes": MAXIMUM_BYTES, "automatic_retries": 0,
        "http_404_rule": "status_only_no_error_body_read_or_provider_empty_body_claim",
        "other_http_or_transport_failure_rule": "stop_retain_attempt_no_restart",
        "budget_rule": "global_qualification_protocol_and_prior_source_pins_not_head_or_time",
        "source_rule": "verify_original_spent_captures_before_named_existing_key",
        "chronology_rule": "enclosing_start_then_request_start_then_response_then_next_start_then_report_then_completion",
        "publication_scope": "private_only_no_rows_counts_or_source_fitness_publication",
        "source_only": True, "outcome_looks": 0, "qc_attempts": 0,
        "backtest_result_exists": False,
    }


def _code_identity(root: Path, head: str) -> str:
    return hash_payload({"git_commit": head, "files": [
        {"path": name, "sha256": hash_bytes((root / name).read_bytes())} for name in _CODE_FILES]})


def _source_preflight(root: Path) -> dict:
    """Verify original source custody and stored bindings without recapture."""
    _require_capture_platform()
    captures, anchor = finalizer._reload(root)
    source_index, index_bytes_sha256 = native_builder._source_index(root, anchor)
    archive_pins = native_builder._archives(captures)
    _require(hash_payload(archive_pins) == source_index.capture_identity_sha256,
             "master_capture_identity")
    directory = root / native_builder.OUTPUT
    _require({path.name for path in directory.iterdir()} == {
        "started.json", "completed.json", "native.index.private.json", "observations.private.json"},
        "native_source_inventory")
    native_raw = _protected_bytes(directory / "native.index.private.json", native_builder.MAXIMUM_NATIVE_INDEX_BYTES)
    observations_raw = _protected_bytes(directory / "observations.private.json", native_builder.MAXIMUM_OBSERVATION_BYTES)
    _require(hash_bytes(native_raw) == NATIVE_INDEX_BYTES_SHA256
             and hash_bytes(observations_raw) == OBSERVATION_BYTES_SHA256, "native_source_bytes")
    native = _parse_receipt(native_raw)
    observations = _parse_receipt(observations_raw)
    _require(native.get("index_sha256") == NATIVE_INDEX_PAYLOAD_SHA256
             and native.get("source_report_sha256") == source_index.report_payload_sha256
             and native.get("source_capture_identity_sha256") == source_index.capture_identity_sha256
             and native.get("source_retrieved_at") == anchor
             and hash_payload({k: v for k, v in native.items() if k != "index_sha256"}) == NATIVE_INDEX_PAYLOAD_SHA256,
             "native_source_seal")
    _require(observations.get("binding_sha256") == OBSERVATION_PAYLOAD_SHA256
             and observations.get("native_index_sha256") == NATIVE_INDEX_PAYLOAD_SHA256
             and hash_payload({k: v for k, v in observations.items() if k != "binding_sha256"}) == OBSERVATION_PAYLOAD_SHA256,
             "native_observation_seal")
    start = _parse_receipt(_protected_bytes(directory / "started.json", 65536))
    end = _parse_receipt(_protected_bytes(directory / "completed.json", 65536))
    fixed = {
        "code_head": NATIVE_SOURCE_HEAD, "source_index_sha256": native_builder.SOURCE_INDEX_SHA256,
        "source_index_bytes_sha256": index_bytes_sha256,
        "source_capture_inventory_sha256": finalizer.SOURCE_INVENTORY_SHA256,
        "source_capture_budget_sha256": finalizer.BUDGET_SHA256,
        "source_report_payload_sha256": source_index.report_payload_sha256,
        "source_capture_identity_sha256": source_index.capture_identity_sha256,
        "source_reconstruction_anchor": anchor, "source_archive_pins": archive_pins,
        "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
        "qc_attempts": 0, "backtest_result_exists": False,
    }
    _require(start.get("schema") == "si-native-master-offline-start-v1"
             and end.get("schema") == "si-native-master-offline-complete-v1"
             and end.get("status") == "native_master_offline_complete"
             and all(canonical_json({k: value.get(k) for k in fixed}) == canonical_json(fixed)
                     for value in (start, end))
             and end.get("native_index_bytes_sha256") == NATIVE_INDEX_BYTES_SHA256
             and end.get("native_observation_bytes_sha256") == OBSERVATION_BYTES_SHA256
             and start.get("started_at") == NATIVE_STARTED_AT
             and end.get("started_at") == NATIVE_STARTED_AT
             and end.get("completed_at") == NATIVE_COMPLETED_AT,
             "native_source_receipts")
    _require(_clock(anchor) <= _clock(start.get("started_at")) <= _clock(end.get("completed_at")),
             "native_source_chronology")
    companion_reader._rebuild_sharadar(root)
    return _source_pins()


def _budget_name() -> str:
    return "budget-" + hash_payload({"qualification_protocol_sha256": contract.PROTOCOL_SHA256,
                                     "source_pins": _source_pins()}) + ".json"


def _claim_budget(root: Path, directory: Path, *, head: str, remote: str, started_at: str) -> None:
    _require_capture_platform()
    _guard(root, head, remote)
    try:
        _publish_json(directory.parent, _budget_name(), {
            "schema": "si-massive-class-whole-round-budget-v1", "run_id": directory.name,
            "started_at": started_at, "code_head": head, "remote_head": remote,
            "qualification_protocol_sha256": contract.PROTOCOL_SHA256,
            "source_pins": _source_pins(), "maximum_attempts": MAXIMUM_REQUESTS,
            "resumption_or_restart_allowed": False,
        })
    except (CaptureRefusal, FileExistsError):
        raise ClassDenominatorCaptureRefusal("whole_round_budget_already_claimed") from None


def _publish_guarded(root: Path, directory: Path, name: str, value, *, head: str, remote: str, raw: bool = False) -> None:
    _guard(root, head, remote)
    (_publish if raw else _publish_json)(directory, name, value)


def _request_spec(request_id: str, frozen: dict, ordinal: int) -> tuple[dict, str]:
    spec, digest = contract.massive_request(request_id), contract.request_sha256(request_id)
    parsed = urllib.parse.urlsplit(spec["url"])
    ticker, at = request_id.removeprefix("overview-").rsplit("-", 1)
    _require(spec == frozen["requests"][ordinal - 1] and hash_payload(spec) == digest
             and spec["method"] == "GET" and parsed.scheme == "https"
             and parsed.netloc == "api.massive.com" and not parsed.query and not parsed.fragment
             and parsed.path == "/v3/reference/tickers/" + urllib.parse.quote(ticker, safe="")
             and spec["params"] == {"date": at[:4] + "-" + at[4:6] + "-" + at[6:]},
             "request_origin_or_binding")
    return spec, digest


def _capture(root: Path, directory: Path, key: str, opener, *, head: str, remote: str, started_at: str) -> dict:
    _require_capture_platform()
    protocol = _validated_protocol()
    captures = []
    previous_clock = _clock(started_at)
    for ordinal, request_id in enumerate(contract.REQUEST_IDS, 1):
        _guard(root, head, remote)
        _require(ordinal <= MAXIMUM_REQUESTS, "request_budget")
        spec, digest = _request_spec(request_id, protocol, ordinal)
        request = urllib.request.Request(spec["url"] + "?" + urllib.parse.urlencode(spec["params"]),
            headers={"Accept": "application/json", "Authorization": "Bearer " + key}, method="GET")
        prefix = f"attempt-{ordinal:02d}"
        request_started_at = _utc_now()
        _publish_guarded(root, directory, prefix + ".started.json", {
            "schema": "si-massive-class-request-start-v1", "attempt": ordinal,
            "request_id": request_id, "request": spec, "request_sha256": digest,
            "qualification_protocol_sha256": contract.PROTOCOL_SHA256,
            "code_head": head, "started_at": request_started_at,
        }, head=head, remote=remote)
        status = None
        try:
            request_clock = _clock(request_started_at)
            _require(previous_clock <= request_clock, "capture_receipt_chronology")
            _guard(root, head, remote)
            body_observed = True
            try:
                raw, content_type, status = _http(opener, request, MAXIMUM_BYTES)
            except SharadarCaptureRefusal as exc:
                if exc.code != "http_not_200" or exc.http_status != 404:
                    raise
                # _http never reads error bodies or headers. This is an absent
                # body observation, not provider evidence of an empty body.
                raw, content_type, status, body_observed = b"", "", 404, False
            _refuse_credential_echo(raw, content_type, key, status)
            received_at = _utc_now()
            if body_observed:
                _publish_guarded(root, directory, prefix + ".raw", raw, head=head, remote=remote, raw=True)
            _publish_guarded(root, directory, prefix + ".received.json", {
                "schema": "si-massive-class-response-receipt-v1", "attempt": ordinal,
                "request_id": request_id, "request_sha256": digest, "http_status": status,
                "content_type": content_type if body_observed else None,
                "body_observed": body_observed, "error_body_read": False,
                "raw_path": prefix + ".raw" if body_observed else None,
                "raw_bytes": len(raw) if body_observed else None,
                "raw_sha256": hash_bytes(raw) if body_observed else None, "received_at": received_at,
            }, head=head, remote=remote)
            response_clock = _clock(received_at)
            _require(request_clock <= response_clock, "capture_receipt_chronology")
            previous_clock = response_clock
            captures.append(contract.CapturedMassiveClassResponse(
                request_id=request_id, request_sha256=digest, raw=raw, raw_sha256=hash_bytes(raw),
                http_status=status, content_type=content_type, received_at=received_at,
                body_observed=body_observed))
        except (CaptureRefusal, ValueError, TypeError, OSError) as exc:
            safe = type(exc) in (SharadarCaptureRefusal, ClassDenominatorCaptureRefusal)
            code = exc.code if safe else "response_contract_or_guard_refused"
            observed = exc.http_status if safe else status
            _publish_guarded(root, directory, prefix + ".refused.json", {
                "schema": "si-massive-class-request-refusal-v1", "attempt": ordinal,
                "request_id": request_id, "code": code, "http_status": observed, "refused_at": _utc_now(),
            }, head=head, remote=remote)
            raise ClassDenominatorCaptureRefusal(code, status=observed) from None
    retrieved_at = _utc_now()
    _require(previous_clock <= _clock(retrieved_at), "capture_receipt_chronology")
    report = contract.qualify_massive_class_denominator(tuple(captures), retrieved_at=retrieved_at,
                                                       expected_protocol_sha256=contract.PROTOCOL_SHA256)
    _publish_guarded(root, directory, "qualification.private.json", report.to_bytes(), head=head, remote=remote, raw=True)
    completed_at = _utc_now()
    _require(_clock(retrieved_at) <= _clock(completed_at), "capture_receipt_chronology")
    result = {
        "schema": "si-massive-class-capture-completion-v1", "status": "capture_complete",
        "code_head": head, "qualification_protocol_sha256": contract.PROTOCOL_SHA256,
        "capture_protocol_sha256": hash_payload(capture_protocol()),
        "private_report_sha256": report.sha256,
        "private_report_bytes_sha256": hash_bytes(report.to_bytes()), "completed_at": completed_at,
        "source_only": True, "outcome_looks": 0, "qc_attempts": 0,
        "backtest_result_exists": False,
    }
    _publish_guarded(root, directory, "completed.json", result, head=head, remote=remote)
    # No row count, symbols, coverage or data-fitness conclusion is public.
    return result


def _run(root: Path, *, head: str, remote: str) -> dict:
    _require_capture_platform()
    _guard(root, head, remote)
    protocol = capture_protocol()
    code_identity = _code_identity(root, head)
    source_pins = _source_preflight(root)
    _require(source_pins == protocol["source_pins"], "source_preflight_protocol_binding")
    started_at = _utc_now()
    _require(_clock(started_at) >= _clock(NATIVE_COMPLETED_AT), "capture_start_chronology")
    target = root / CAPTURE_PARENT / _run_id(started_at)
    _require(_git(root, "check-ignore", str(target)) == str(target), "capture_not_ignored")
    _guard(root, head, remote)
    key = _existing_key()
    _guard(root, head, remote)
    directory = _prepare_capture_directory(target)
    # Only this successful exclusive creation grants refusal-write authority.
    # An early refusal or rerun cannot overwrite an earlier capture.
    try:
        _claim_budget(root, directory, head=head, remote=remote, started_at=started_at)
        _publish_guarded(root, directory, "protocol.json", protocol, head=head, remote=remote)
        _publish_guarded(root, directory, "started.json", {
            "schema": "si-massive-class-capture-start-v1", "run_id": directory.name,
            "code_head": head, "remote_head": remote, "code_identity_sha256": code_identity,
            "capture_protocol_sha256": hash_payload(protocol),
            "qualification_protocol_sha256": contract.PROTOCOL_SHA256,
            "source_pins": source_pins, "started_at": started_at,
            "maximum_attempts": MAXIMUM_REQUESTS, "source_only": True,
            "outcome_looks": 0, "qc_attempts": 0,
        }, head=head, remote=remote)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        return _capture(root, directory, key, opener, head=head, remote=remote, started_at=started_at)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        safe = type(exc) in (ClassDenominatorCaptureRefusal, SharadarCaptureRefusal, CapturePlatformRefusal)
        _publish_guarded(root, directory, "refused.json", {
            "schema": "si-massive-class-capture-refusal-v1", "status": "capture_refused",
            "code": exc.code if safe else "owned_output_refused",
            "http_status": exc.http_status if safe else None, "refused_at": _utc_now(),
            "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False,
        }, head=head, remote=remote)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        _require_capture_platform()
        result = _run(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        safe = type(exc) in (ClassDenominatorCaptureRefusal, CapturePlatformRefusal)
        result = {"status": "capture_refused", "code": exc.code if safe else "local_preflight_refused",
                  "http_status": exc.http_status if safe else None,
                  "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
        if type(exc) is CapturePlatformRefusal:
            result["ready_for_empirical_backtest"] = False
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
