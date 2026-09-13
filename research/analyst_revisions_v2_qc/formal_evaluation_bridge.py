"""Process-authenticated QC summary receipt to formal aggregate authority.

The formal evaluator runs inside the reviewed QuantConnect source closure and
publishes only a gzip-compressed, URL-safe-base64 aggregate through named
summary statistics.  This module is the pure post-run boundary: it accepts the
typed one-use result-read receipt, reconstructs and validates the exact
aggregate, and mints an opaque content-and-process authority.  It cannot read
QuantConnect, the filesystem, credentials, providers, or outcomes itself.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import re
import sys
import threading
import weakref
import zlib
from collections.abc import Mapping

from . import formal_cloud_evaluator as _cloud_evaluator
from .formal_cloud_evaluator import (
    FormalCloudEvaluationBindings,
    FormalCloudEvaluationError,
    derive_streamed_formal_evaluation_preknown_bindings_record,
    require_formal_cloud_evaluation_aggregate_bytes,
)
from .formal_report_contract import (
    COMPARATOR_LEDGER_IDS,
    FORMAL_FOLD_IDS,
    REPORT_FAMILY_IDS,
    SLICE_IDS,
    SOURCE_VIEW_IDS,
)
from .formal_runtime_projection import (
    ABSOLUTE_MAX_SUMMARY_CHUNK_CHARACTERS,
    ABSOLUTE_MAX_SUMMARY_CHUNKS,
    ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES,
    AGGREGATE_RESULT_SCHEMA,
    EVALUATION_ID,
    FORMAL_RESULT_FAMILY_OBJECT_COUNT,
    MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES,
    MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES,
    MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES,
    MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES,
    REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX,
    REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA,
    SUMMARY_CHUNK_PREFIX,
    SUMMARY_META_NAME,
    SUMMARY_RECEIPT_SCHEMA,
)
from .formal_submission_adapter import (
    FormalQcLaunchReceipt,
    FormalQcResultReadAuthority,
    FormalQcSubmissionError,
    FormalQcSummaryResultReadReceipt,
    FormalQcTerminalStatusReceipt,
    StreamedFormalSubmissionAdapterBridge,
    require_formal_qc_summary_result_read_receipt,
    require_streamed_formal_submission_adapter_bridge,
)
from .formal_streaming_input import streamed_formal_contract_record


class FormalEvaluationBridgeError(ValueError):
    """The authenticated QC result cannot cross the formal result gate."""


SCHEMA = "arv2-formal-aggregate-evaluation-receipt-v2"
STATUS = "qc_process_and_content_authenticated_formal_aggregate_only"
AUTHORITY = (
    "formal_aggregate_evaluation_only_no_result_disposition_deployment_order_"
    "or_trading_authority"
)
MAX_AGGREGATE_BYTES = 4 * 1024 * 1024
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SUMMARY_META_FIELDS = frozenset(
    {
        "schema",
        "evaluation_id",
        "input_manifest_sha256",
        "cloud_evaluator_sha256",
        "root_manifest_schema",
        "root_manifest_sha256",
        "root_manifest_byte_count",
        "compressed_root_sha256",
        "compressed_root_byte_count",
        "encoding",
        "chunk_count",
        "chunks",
        "report_family_object_reference_schema",
        "report_family_object_count",
        "report_family_object_inventory_sha256",
        "report_family_object_total_uncompressed_byte_count",
        "report_family_object_total_compressed_byte_count",
        "report_family_object_full_key_prefix",
        "object_store_write_once_existing_identical_bytes_only",
        "object_store_save_then_reopen_and_rehash_complete",
        "object_store_reopened_object_count",
        "raw_report_family_rows_in_summary",
        "fold_horizon_axis_count",
        "source_view_fold_horizon_axis_count",
        "failed_arm_omission_count",
        "orders_placed",
    }
)
_CHUNK_FIELDS = frozenset({"name", "ordinal", "character_count", "sha256"})


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise FormalEvaluationBridgeError("value is not canonical JSON") from exc


def _reject_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FormalEvaluationBridgeError("summary metadata contains a duplicate key")
        result[key] = value
    return result


def _reject_number(_value: str) -> object:
    raise FormalEvaluationBridgeError("summary metadata contains a JSON float")


def _json_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise FormalEvaluationBridgeError(f"{name} is not nonempty exact bytes")
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_reject_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalEvaluationBridgeError):
            raise
        raise FormalEvaluationBridgeError(f"{name} is not strict JSON") from exc
    if type(value) is not dict or _canonical_bytes(value) != payload:
        raise FormalEvaluationBridgeError(f"{name} is not one canonical JSON object")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise FormalEvaluationBridgeError(f"{name} is not a lowercase SHA-256")
    return value


def _exact_base64(value: object, name: str) -> bytes:
    if type(value) is not str or not value:
        raise FormalEvaluationBridgeError(f"{name} is not nonempty base64 text")
    try:
        result = base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeError, ValueError) as exc:
        raise FormalEvaluationBridgeError(f"{name} is not strict URL-safe base64") from exc
    if base64.urlsafe_b64encode(result).decode("ascii") != value:
        raise FormalEvaluationBridgeError(f"{name} has a noncanonical base64 encoding")
    return result


def _bounded_gzip(payload: bytes, expected_count: int) -> bytes:
    if type(expected_count) is not int or not 0 < expected_count <= MAX_AGGREGATE_BYTES:
        raise FormalEvaluationBridgeError("aggregate byte count exceeds the result gate")
    if (
        type(payload) is not bytes
        or len(payload) < 18
        or payload[:4] != b"\x1f\x8b\x08\x00"
        or payload[4:8] != b"\x00\x00\x00\x00"
        or payload[8] != 2
        or payload[9] != 255
    ):
        raise FormalEvaluationBridgeError(
            "summary gzip header changed from the canonical wire contract"
        )
    try:
        decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        result = decoder.decompress(payload, MAX_AGGREGATE_BYTES + 1)
        if decoder.unconsumed_tail:
            raise FormalEvaluationBridgeError(
                "summary aggregate exceeded its decompression bound"
            )
        result += decoder.flush(MAX_AGGREGATE_BYTES + 1 - len(result))
    except (ValueError, zlib.error) as exc:
        raise FormalEvaluationBridgeError("summary payload is not valid gzip") from exc
    if (
        len(result) != expected_count
        or len(result) > MAX_AGGREGATE_BYTES
        or decoder.eof is not True
        or decoder.unused_data
        or decoder.unconsumed_tail
    ):
        raise FormalEvaluationBridgeError("summary aggregate byte count changed")
    return result


def _reconstruct_aggregate(
    receipt: FormalQcSummaryResultReadReceipt,
    bindings: FormalCloudEvaluationBindings,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
) -> tuple[bytes, dict[str, object], int, str]:
    if type(receipt.summary_pairs) is not tuple:
        raise FormalEvaluationBridgeError("summary pair topology changed")
    pairs = dict(receipt.summary_pairs)
    if len(pairs) != len(receipt.summary_pairs) or SUMMARY_META_NAME not in pairs:
        raise FormalEvaluationBridgeError("summary statistic names are incomplete or duplicated")
    meta_payload = _exact_base64(pairs[SUMMARY_META_NAME], "summary metadata")
    meta = _json_object(meta_payload, "summary metadata")
    if set(meta) != _SUMMARY_META_FIELDS:
        raise FormalEvaluationBridgeError("summary metadata fields changed")
    chunks = meta["chunks"]
    if type(chunks) is not list or type(meta["chunk_count"]) is not int:
        raise FormalEvaluationBridgeError("summary chunk census changed type")
    expected_names = tuple(
        SUMMARY_CHUNK_PREFIX + str(index).zfill(3) for index in range(len(chunks))
    )
    if (
        meta["schema"] != SUMMARY_RECEIPT_SCHEMA
        or meta["evaluation_id"] != EVALUATION_ID
        or meta["input_manifest_sha256"] != bindings.input_manifest_sha256
        or meta["cloud_evaluator_sha256"] != bindings.evaluator_source_closure_sha256
        or meta["root_manifest_schema"] != AGGREGATE_RESULT_SCHEMA
        or meta["report_family_object_reference_schema"]
        != REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
        or meta["report_family_object_count"]
        != FORMAL_RESULT_FAMILY_OBJECT_COUNT
        or meta["object_store_write_once_existing_identical_bytes_only"]
        is not True
        or meta["object_store_save_then_reopen_and_rehash_complete"] is not True
        or meta["object_store_reopened_object_count"]
        != FORMAL_RESULT_FAMILY_OBJECT_COUNT
        or meta["raw_report_family_rows_in_summary"] is not False
        or meta["encoding"]
        != "gzip-mtime-zero-os-255-plus-urlsafe-base64-no-linebreaks"
        or meta["chunk_count"] != len(chunks)
        or not chunks
        or len(chunks) > ABSOLUTE_MAX_SUMMARY_CHUNKS
        or set(pairs) != {SUMMARY_META_NAME, *expected_names}
        or meta["fold_horizon_axis_count"] != 24
        or meta["source_view_fold_horizon_axis_count"] != 48
        or meta["failed_arm_omission_count"] != 0
        or meta["orders_placed"] != 0
    ):
        raise FormalEvaluationBridgeError("summary metadata contract changed")
    encoded_parts: list[str] = []
    for ordinal, raw in enumerate(chunks):
        if type(raw) is not dict or set(raw) != _CHUNK_FIELDS:
            raise FormalEvaluationBridgeError("summary chunk descriptor changed")
        name = expected_names[ordinal]
        text = pairs[name]
        if (
            raw["name"] != name
            or raw["ordinal"] != ordinal
            or raw["character_count"] != len(text)
            or len(text) > ABSOLUTE_MAX_SUMMARY_CHUNK_CHARACTERS
            or raw["sha256"] != hashlib.sha256(text.encode("ascii")).hexdigest()
        ):
            raise FormalEvaluationBridgeError("summary chunk identity changed")
        encoded_parts.append(text)
    compressed = _exact_base64("".join(encoded_parts), "summary aggregate")
    if (
        type(meta["compressed_root_byte_count"]) is not int
        or meta["compressed_root_byte_count"] != len(compressed)
        or not 0 < len(compressed) <= ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES
        or _sha(meta["compressed_root_sha256"], "compressed result hash")
        != hashlib.sha256(compressed).hexdigest()
    ):
        raise FormalEvaluationBridgeError("compressed summary identity changed")
    aggregate = _bounded_gzip(compressed, meta["root_manifest_byte_count"])
    if (
        _sha(meta["root_manifest_sha256"], "aggregate result hash")
        != hashlib.sha256(aggregate).hexdigest()
    ):
        raise FormalEvaluationBridgeError("aggregate summary identity changed")
    if (
        type(receipt._formal_result_root_manifest) is not bytes
        or receipt._formal_result_root_manifest != aggregate
        or type(receipt._formal_result_bindings)
        is not FormalCloudEvaluationBindings
        or receipt._formal_result_bindings.to_record() != bindings.to_record()
        or type(receipt._formal_result_family_descriptors) is not tuple
        or type(receipt._formal_result_family_payloads) is not tuple
    ):
        raise FormalEvaluationBridgeError(
            "process-authenticated multipart result package changed"
        )
    try:
        descriptors = _cloud_evaluator.formal_cloud_evaluation_family_object_read_plan(
            aggregate, expected_bindings=bindings
        )
        descriptor_records = [item.to_record() for item in descriptors]
        if (
            descriptors != receipt._formal_result_family_descriptors
            or len(descriptors) != FORMAL_RESULT_FAMILY_OBJECT_COUNT
            or meta["report_family_object_inventory_sha256"]
            != hashlib.sha256(_canonical_bytes(descriptor_records)).hexdigest()
            or meta["report_family_object_total_uncompressed_byte_count"]
            != sum(item.uncompressed_byte_count for item in descriptors)
            or meta["report_family_object_total_compressed_byte_count"]
            != sum(item.compressed_byte_count for item in descriptors)
            or type(meta["report_family_object_total_uncompressed_byte_count"])
            is not int
            or not 0
            < meta["report_family_object_total_uncompressed_byte_count"]
            <= MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES
            or type(meta["report_family_object_total_compressed_byte_count"])
            is not int
            or not 0
            < meta["report_family_object_total_compressed_byte_count"]
            <= MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
            or any(
                type(item.uncompressed_byte_count) is not int
                or not 0
                < item.uncompressed_byte_count
                <= MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES
                or type(item.compressed_byte_count) is not int
                or not 0
                < item.compressed_byte_count
                <= MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES
                for item in descriptors
            )
            or meta["report_family_object_full_key_prefix"]
            != f"{receipt.project_id}/{REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX}"
        ):
            raise FormalEvaluationBridgeError(
                "formal result descriptor inventory changed"
            )
        payloads = dict(receipt._formal_result_family_payloads)
        if (
            len(payloads) != len(receipt._formal_result_family_payloads)
            or len(payloads) != len(descriptors)
            or tuple(payloads)
            != tuple(item.object_store_key_suffix for item in descriptors)
        ):
            raise FormalEvaluationBridgeError(
                "formal result family payload inventory changed"
            )
        document = require_formal_cloud_evaluation_aggregate_bytes(
            aggregate,
            expected_bindings=bindings,
            report_family_object_payloads=payloads,
        )
    except (FormalCloudEvaluationError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalEvaluationBridgeError):
            raise
        raise FormalEvaluationBridgeError("formal cloud aggregate is invalid") from exc
    coverage_count, coverage_sha256 = _require_exact_preoutcome_coverage_output(
        document=document,
        submission_bridge=submission_bridge,
    )
    return aggregate, document, coverage_count, coverage_sha256


def _expected_preoutcome_coverage_rows(
    coverages: tuple[dict[str, object], ...],
    *,
    source_view_id: str,
) -> list[dict[str, object]]:
    """Project the 7 authenticated coverage parents into exact family-4 rows."""

    expected_scopes = (*FORMAL_FOLD_IDS, "POOLED")
    selected = tuple(
        item for item in coverages if item.get("source_view_id") == source_view_id
    )
    scopes = tuple(
        item.get("fold_ids", [None])[0]
        if type(item.get("fold_ids")) is list
        and len(item["fold_ids"]) == 1
        else "POOLED"
        for item in selected
    )
    if len(selected) != 7 or scopes != expected_scopes:
        raise FormalEvaluationBridgeError(
            "authenticated preoutcome coverage parents are incomplete or reordered"
        )
    result: list[dict[str, object]] = []
    for coverage, fold_id in zip(selected, scopes, strict=True):
        diagnostic_counts = {
            "endpoint_status_counts": coverage.get("endpoint_status_counts"),
            "endpoint_pair_status_counts": coverage.get(
                "endpoint_pair_status_counts"
            ),
            "direction_status_counts": coverage.get("direction_status_counts"),
            "date_diagnostic_counts": coverage.get("date_diagnostic_counts"),
            "raw_form_collision_counts": coverage.get(
                "raw_form_collision_counts"
            ),
        }
        ledgers = coverage.get("ledgers")
        if type(ledgers) is not list or len(ledgers) != len(COMPARATOR_LEDGER_IDS):
            raise FormalEvaluationBridgeError(
                "authenticated preoutcome coverage ledger census changed"
            )
        for ledger, ledger_id in zip(ledgers, COMPARATOR_LEDGER_IDS, strict=True):
            if (
                type(ledger) is not dict
                or ledger.get("ledger_id") != ledger_id
                or ledger.get("disposition") != "PASS"
                or ledger.get("passes") is not True
                or ledger.get("reasons") != []
            ):
                raise FormalEvaluationBridgeError(
                    "authenticated preoutcome coverage ledger changed"
                )
            result.append(
                {
                    "source_view_id": source_view_id,
                    "slice_id": SLICE_IDS[0],
                    "fold_id": fold_id,
                    "record_kind": "preoutcome_coverage_ledger",
                    "record_id": ledger_id,
                    "status": "AVAILABLE",
                    "numerator": ledger.get("numerator"),
                    "denominator": ledger.get("denominator"),
                    "passes_19_of_20": True,
                    "valid_date_count": None,
                    "mean_firm_ic": None,
                    "mean_global_ic": None,
                    "observed_difference": None,
                    "one_sided_q95": None,
                    "one_sided_lcb95": None,
                    "diagnostic_counts": diagnostic_counts,
                    "reasons": [],
                }
            )
    return result


def _require_exact_preoutcome_coverage_output(
    *,
    document: Mapping[str, object],
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
) -> tuple[int, str]:
    """Bind every family-4 coverage cell to all 14 exact input records."""

    try:
        streamed_input = (
            submission_bridge.runtime_bridge.resource_candidate.streamed_input
        )
        contract = streamed_formal_contract_record(streamed_input)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise FormalEvaluationBridgeError(
            "authenticated streamed formal contract is unavailable"
        ) from exc
    manifest = _json_object(
        submission_bridge.runtime_bridge.input_manifest_payload,
        "streamed runtime manifest",
    )
    lineage = manifest.get("streamed_formal_input_lineage")
    if (
        type(contract) is not dict
        or type(lineage) is not dict
        or lineage.get("formal_contract_sha256")
        != hashlib.sha256(_canonical_bytes(contract)).hexdigest()
    ):
        raise FormalEvaluationBridgeError(
            "authenticated streamed formal contract differs from its manifest"
        )
    fold = contract.get("global_comparator_fold_coverages")
    pooled = contract.get("global_comparator_pooled_coverages")
    if (
        type(fold) is not list
        or len(fold) != 12
        or type(pooled) is not list
        or len(pooled) != 2
        or any(type(item) is not dict for item in (*fold, *pooled))
    ):
        raise FormalEvaluationBridgeError(
            "authenticated preoutcome coverage record census changed"
        )
    coverages = tuple((*fold, *pooled))
    report_contract = contract.get("formal_report_contract")
    schemas = (
        report_contract.get("report_schemas")
        if type(report_contract) is dict
        else None
    )
    if type(schemas) is not list or len(schemas) != len(REPORT_FAMILY_IDS):
        raise FormalEvaluationBridgeError(
            "authenticated report-family schemas are unavailable"
        )
    family_id = REPORT_FAMILY_IDS[4]
    family_schema = schemas[4]
    if type(family_schema) is not dict or family_schema.get("family_id") != family_id:
        raise FormalEvaluationBridgeError(
            "authenticated family-4 schema changed"
        )
    chunks = document.get("report_family_chunks")
    if type(chunks) is not list:
        raise FormalEvaluationBridgeError("formal aggregate omitted report-family chunks")
    family_chunks = tuple(
        item
        for item in chunks
        if type(item) is dict and item.get("family_id") == family_id
    )
    if (
        len(family_chunks) != len(SOURCE_VIEW_IDS)
        or tuple(item.get("source_view_id") for item in family_chunks)
        != SOURCE_VIEW_IDS
    ):
        raise FormalEvaluationBridgeError(
            "formal aggregate family-4 chunks are incomplete or reordered"
        )
    fields = tuple(family_schema.get("ordered_key_fields", ())) + tuple(
        family_schema.get("ordered_value_fields", ())
    )
    if not fields or len(set(fields)) != len(fields):
        raise FormalEvaluationBridgeError("authenticated family-4 fields changed")
    for raw_chunk, view in zip(family_chunks, SOURCE_VIEW_IDS, strict=True):
        try:
            family = _cloud_evaluator._decode_report_family_chunk(raw_chunk)
        except (FormalCloudEvaluationError, AttributeError, TypeError, ValueError) as exc:
            raise FormalEvaluationBridgeError(
                "formal aggregate family-4 chunk is invalid"
            ) from exc
        if family.get("family_schema") != family_schema:
            raise FormalEvaluationBridgeError(
                "formal aggregate family-4 schema differs from its input contract"
            )
        raw_rows = family.get("rows")
        if type(raw_rows) is not list:
            raise FormalEvaluationBridgeError("formal aggregate family-4 rows changed")
        rows = []
        for cells in raw_rows:
            if type(cells) is not list or len(cells) != len(fields):
                raise FormalEvaluationBridgeError(
                    "formal aggregate family-4 row alignment changed"
                )
            rows.append(dict(zip(fields, cells, strict=True)))
        observed = [
            row
            for row in rows
            if row.get("record_kind") == "preoutcome_coverage_ledger"
        ]
        expected = _expected_preoutcome_coverage_rows(
            coverages,
            source_view_id=view,
        )
        if observed != expected:
            raise FormalEvaluationBridgeError(
                "family-4 coverage output differs from authenticated input records"
            )
    coverage_digest = hashlib.sha256(
        _canonical_bytes(
            {
                "global_comparator_fold_coverages": fold,
                "global_comparator_pooled_coverages": pooled,
            }
        )
    ).hexdigest()
    return len(coverages), coverage_digest


def _require_submission_derived_bindings(
    *,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    bindings: FormalCloudEvaluationBindings,
) -> FormalCloudEvaluationBindings:
    """Refuse caller-authored preknown lineage at the one-use result gate.

    The market-panel identity is necessarily learned inside the authenticated
    QC evaluation.  Every other binding is known before launch and must be
    derived from the exact manifest retained by the authenticated streamed
    submission bridge, never supplied independently by a caller.
    """

    manifest = _json_object(
        submission_bridge.runtime_bridge.input_manifest_payload,
        "streamed runtime manifest",
    )
    try:
        preknown = derive_streamed_formal_evaluation_preknown_bindings_record(
            manifest
        )
    except (FormalCloudEvaluationError, TypeError, ValueError) as exc:
        raise FormalEvaluationBridgeError(
            "streamed runtime manifest cannot derive formal evaluation bindings"
        ) from exc
    record = bindings.to_record()
    qc_derived = {
        "shared_market_panel_sha256",
        "shared_market_panel_observation_count",
    }
    preknown_fields = set(record) - qc_derived
    if (
        not preknown_fields.issubset(preknown)
        or any(record[name] != preknown[name] for name in preknown_fields)
    ):
        raise FormalEvaluationBridgeError(
            "formal evaluation bindings diverged from the exact streamed manifest"
        )
    return bindings


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalAggregateEvaluationReceipt:
    receipt_id: str
    receipt_sha256: str
    schema: str
    status: str
    authority: str
    evaluation_id: str
    aggregate_result_sha256: str
    aggregate_result_byte_count: int
    input_manifest_sha256: str
    production_scoring_census_sha256: str
    evaluation_input_bundle_id: str
    evaluation_input_bundle_sha256: str
    terminal_disposition_package_sha256: str
    formal_evaluator_source_sha256: str
    evaluator_source_closure_sha256: str
    execution_plan_sha256: str
    capacity_plan_sha256: str
    formal_contract_sha256: str
    shared_market_panel_sha256: str
    shared_market_panel_observation_count: int
    current_view_report_id: str
    current_view_report_sha256: str
    censored_view_report_id: str
    censored_view_report_sha256: str
    result_read_receipt_id: str
    result_read_receipt_sha256: str
    terminal_receipt_id: str
    terminal_receipt_sha256: str
    launch_receipt_id: str
    launch_receipt_sha256: str
    runtime_bridge_id: str
    runtime_bridge_sha256: str
    submission_adapter_bridge_id: str
    submission_adapter_bridge_sha256: str
    authenticated_power_floor_id: str
    authenticated_power_floor_sha256: str
    economic_execution_binding_id: str
    economic_execution_binding_sha256: str
    economic_execution_definition_id: str
    economic_execution_definition_sha256: str
    economic_h20_terminal_liquidation_session: str
    formal_report_contract_id: str
    formal_report_contract_sha256: str
    formal_report_contract_artifact_sha256: str
    formal_report_contract_economic_execution_definition_sha256: str
    formal_report_contract_secondary_hypothesis_registry_sha256: str
    formal_report_contract_deflated_sharpe_trial_registry_sha256: str
    formal_report_contract_stock_bootstrap_seed_sha256: str
    formal_report_contract_report_family_count: int
    formal_report_contract_secondary_hypothesis_count: int
    formal_report_contract_strategy_trial_count: int
    secondary_hypothesis_registry_sha256: str
    deflated_sharpe_trial_registry_sha256: str
    stock_bootstrap_seed_sha256: str
    preoutcome_global_comparator_coverage_record_count: int
    preoutcome_global_comparator_coverages_sha256: str
    process_authenticated_qc_read: bool
    content_authenticated: bool
    result_disposition_authority: bool
    deployment_authority: bool
    orders_authority: bool
    trading_authority: bool
    _aggregate_bytes: bytes = dataclasses.field(repr=False)
    _result_read_receipt: FormalQcSummaryResultReadReceipt = dataclasses.field(repr=False)
    _bindings: FormalCloudEvaluationBindings = dataclasses.field(repr=False)
    _submission_bridge: StreamedFormalSubmissionAdapterBridge = dataclasses.field(
        repr=False
    )


_RECEIPTS: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalAggregateEvaluationReceipt],
        FormalQcSummaryResultReadReceipt,
        FormalQcResultReadAuthority,
        FormalQcTerminalStatusReceipt,
        FormalQcLaunchReceipt,
        StreamedFormalSubmissionAdapterBridge,
        tuple[object, ...],
        bytes,
        int,
    ],
] = {}
_RECEIPTS_LOCK = threading.RLock()


def _make_evaluation_receipt_authority_vault():
    """Keep aggregate receipt authority independent from its public mirror."""

    private_receipts: tuple[tuple[int, tuple[object, ...]], ...] = ()
    register_provenance: tuple[tuple[object, ...], ...] = ()
    missing_closure_value = object()
    function_type = type(_make_evaluation_receipt_authority_vault)
    authority_module = sys.modules.get(__name__)

    def private_entry(identity: int) -> tuple[object, ...] | None:
        return next(
            (entry for key, entry in private_receipts if key == identity),
            None,
        )

    def caller_is_exact() -> bool:
        if not register_provenance:
            return False
        frame = sys._getframe(2)
        for position, provenance in enumerate(register_provenance):
            (
                expected_function,
                expected_code,
                expected_name,
                expected_global_bindings,
                expected_closure,
            ) = provenance
            if (
                frame is None
                or frame.f_code is not expected_code
                or frame.f_code.co_name != expected_name
                or frame.f_globals.get("__name__") != __name__
                or authority_module is None
                or sys.modules.get(__name__) is not authority_module
                or vars(authority_module) is not frame.f_globals
                or expected_function.__code__ is not expected_code
                or expected_function.__globals__ is not frame.f_globals
                or expected_function.__name__ != expected_name
                or any(
                    expected_function.__globals__.get(
                        name, missing_closure_value
                    ) is not expected
                    or frame.f_globals.get(name, missing_closure_value)
                    is not expected
                    for name, expected in expected_global_bindings
                )
                or tuple(expected_function.__code__.co_freevars)
                != tuple(item[0] for item in expected_closure)
                or len(expected_function.__closure__ or ())
                != len(expected_closure)
                or any(
                    cell.cell_contents is not expected
                    for cell, (_name, expected) in zip(
                        expected_function.__closure__ or (),
                        expected_closure,
                        strict=True,
                    )
                )
                or any(
                    frame.f_locals.get(name, missing_closure_value)
                    is not expected
                    for name, expected in expected_closure
                )
                or (
                    position == len(register_provenance) - 1
                    and frame.f_globals.get(expected_name)
                    is not expected_function
                )
            ):
                return False
            frame = frame.f_back
        return True

    def forget(identity: int, reference: object) -> None:
        nonlocal private_receipts

        with _RECEIPTS_LOCK:
            current = private_entry(identity)
            if current is not None and current[0] is reference:
                private_receipts = tuple(
                    item for item in private_receipts
                    if item[0] != identity
                )
            if _RECEIPTS.get(identity) is current:
                _RECEIPTS.pop(identity, None)

    def reset_after_fork() -> None:
        nonlocal private_receipts
        global _RECEIPTS, _RECEIPTS_LOCK

        _RECEIPTS = {}
        _RECEIPTS_LOCK = threading.RLock()
        private_receipts = ()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    def register(value: object, entry_tail: tuple[object, ...]) -> object:
        nonlocal private_receipts

        if os.getpid() != authority_pid or not caller_is_exact():
            raise FormalEvaluationBridgeError(
                "formal aggregate receipt register caller changed"
            )
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: forget(key, ref)
        )
        entry = (reference, *entry_tail, os.getpid())
        with _RECEIPTS_LOCK:
            if private_entry(identity) is not None or identity in _RECEIPTS:
                raise FormalEvaluationBridgeError(
                    "formal aggregate receipt authority identity was reused"
                )
            private_receipts = (*private_receipts, (identity, entry))
            _RECEIPTS[identity] = entry
        return value

    def current(value: object) -> tuple[object, ...] | None:
        nonlocal private_receipts

        identity = id(value)
        with _RECEIPTS_LOCK:
            private = private_entry(identity)
            public = _RECEIPTS.get(identity)
            if (
                private is None
                or public is not private
                or private[0]() is not value
                or private[-1] != os.getpid()
            ):
                private_receipts = tuple(
                    item for item in private_receipts
                    if item[0] != identity
                )
                _RECEIPTS.pop(identity, None)
                return None
            return private

    def seal_register_provenance(
        value: tuple[object, ...],
    ) -> None:
        nonlocal register_provenance

        if (
            register_provenance
            or type(value) is not tuple
            or len(value) != 2
            or any(
                type(item) is not function_type
                or authority_module is None
                or item.__globals__ is not vars(authority_module)
                or item.__module__ != __name__
                for item in value
            )
        ):
            raise FormalEvaluationBridgeError(
                "formal aggregate receipt register provenance changed"
            )
        try:
            register_provenance = tuple(
                (
                    item,
                    item.__code__,
                    item.__name__,
                    tuple(
                        (
                            name,
                            item.__globals__.get(
                                name, missing_closure_value
                            ),
                        )
                        for name in item.__code__.co_names
                    ),
                    tuple(
                        (name, cell.cell_contents)
                        for name, cell in zip(
                            item.__code__.co_freevars,
                            item.__closure__ or (),
                            strict=True,
                        )
                    ),
                )
                for item in value
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise FormalEvaluationBridgeError(
                "formal aggregate receipt register provenance changed"
            ) from exc

    authority_pid = os.getpid()
    return register, current, seal_register_provenance


(
    _evaluation_receipt_authority_register,
    _evaluation_receipt_authority_current,
    _seal_evaluation_receipt_authority_provenance,
) = (
    _make_evaluation_receipt_authority_vault()
)


def _topology(value: FormalAggregateEvaluationReceipt) -> tuple[object, ...]:
    return (
        tuple((field.name, id(getattr(value, field.name))) for field in dataclasses.fields(value)),
        id(value._aggregate_bytes),
        id(value._result_read_receipt),
        id(value._bindings),
    )


def _receipt_record(
    *, aggregate: bytes, document: Mapping[str, object],
    read_receipt: FormalQcSummaryResultReadReceipt,
    bindings: FormalCloudEvaluationBindings,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    preoutcome_coverage_record_count: int,
    preoutcome_coverages_sha256: str,
) -> dict[str, object]:
    reports = document["reports"]
    if type(reports) is not list or len(reports) != 2:
        raise FormalEvaluationBridgeError("formal aggregate lost a source-view report")
    if (
        bindings.economic_execution_binding_id
        != submission_bridge.economic_execution.binding_id
        or bindings.economic_execution_binding_sha256
        != submission_bridge.economic_execution.binding_sha256
        or bindings.economic_execution_definition_id
        != submission_bridge.economic_execution.definition_id
        or bindings.economic_execution_definition_sha256
        != submission_bridge.economic_execution.definition_sha256
        or bindings.formal_report_contract_id
        != submission_bridge.report_contract.contract_id
        or bindings.formal_report_contract_sha256
        != submission_bridge.report_contract.contract_sha256
        or bindings.formal_report_contract_artifact_sha256
        != submission_bridge.report_contract.artifact_sha256
        or bindings.secondary_hypothesis_registry_sha256
        != submission_bridge.report_contract.secondary_hypothesis_registry_sha256
        or bindings.deflated_sharpe_trial_registry_sha256
        != submission_bridge.report_contract.deflated_sharpe_trial_registry_sha256
        or bindings.stock_bootstrap_seed_sha256
        != submission_bridge.report_contract.stock_bootstrap_seed_sha256
    ):
        raise FormalEvaluationBridgeError(
            "formal evaluation binding lineage differs from the exact submission"
        )
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "evaluation_id": EVALUATION_ID,
        "aggregate_result_sha256": hashlib.sha256(aggregate).hexdigest(),
        "aggregate_result_byte_count": len(aggregate),
        "input_manifest_sha256": bindings.input_manifest_sha256,
        "production_scoring_census_sha256": (
            bindings.production_scoring_census_sha256
        ),
        "evaluation_input_bundle_id": bindings.evaluation_input_bundle_id,
        "evaluation_input_bundle_sha256": bindings.evaluation_input_bundle_sha256,
        "terminal_disposition_package_sha256": (
            bindings.terminal_disposition_package_sha256
        ),
        "formal_evaluator_source_sha256": bindings.formal_evaluator_source_sha256,
        "evaluator_source_closure_sha256": bindings.evaluator_source_closure_sha256,
        "execution_plan_sha256": bindings.execution_plan_sha256,
        "capacity_plan_sha256": bindings.capacity_plan_sha256,
        "formal_contract_sha256": bindings.formal_contract_sha256,
        "shared_market_panel_sha256": bindings.shared_market_panel_sha256,
        "shared_market_panel_observation_count": bindings.shared_market_panel_observation_count,
        "current_view_report_id": reports[0]["report_id"],
        "current_view_report_sha256": reports[0]["report_sha256"],
        "censored_view_report_id": reports[1]["report_id"],
        "censored_view_report_sha256": reports[1]["report_sha256"],
        "result_read_receipt_id": read_receipt.receipt_id,
        "result_read_receipt_sha256": read_receipt.receipt_sha256,
        "terminal_receipt_id": read_receipt.terminal_receipt_id,
        "terminal_receipt_sha256": read_receipt.terminal_receipt_sha256,
        "launch_receipt_id": read_receipt.launch_receipt_id,
        "launch_receipt_sha256": read_receipt.launch_receipt_sha256,
        "runtime_bridge_id": submission_bridge.runtime_bridge.bridge_id,
        "runtime_bridge_sha256": submission_bridge.runtime_bridge.bridge_sha256,
        "submission_adapter_bridge_id": submission_bridge.bridge_id,
        "submission_adapter_bridge_sha256": submission_bridge.bridge_sha256,
        "authenticated_power_floor_id": (
            submission_bridge.authenticated_power_floor.binding_id
        ),
        "authenticated_power_floor_sha256": (
            submission_bridge.authenticated_power_floor.binding_sha256
        ),
        "economic_execution_binding_id": (
            submission_bridge.economic_execution.binding_id
        ),
        "economic_execution_binding_sha256": (
            submission_bridge.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": (
            submission_bridge.economic_execution.definition_id
        ),
        "economic_execution_definition_sha256": (
            submission_bridge.economic_execution.definition_sha256
        ),
        "economic_h20_terminal_liquidation_session": (
            bindings.economic_h20_terminal_liquidation_session
        ),
        "formal_report_contract_id": submission_bridge.report_contract.contract_id,
        "formal_report_contract_sha256": (
            submission_bridge.report_contract.contract_sha256
        ),
        "formal_report_contract_artifact_sha256": (
            submission_bridge.report_contract.artifact_sha256
        ),
        "formal_report_contract_economic_execution_definition_sha256": (
            submission_bridge.report_contract.economic_execution_definition_sha256
        ),
        "formal_report_contract_secondary_hypothesis_registry_sha256": (
            submission_bridge.report_contract.secondary_hypothesis_registry_sha256
        ),
        "formal_report_contract_deflated_sharpe_trial_registry_sha256": (
            submission_bridge.report_contract.deflated_sharpe_trial_registry_sha256
        ),
        "formal_report_contract_stock_bootstrap_seed_sha256": (
            submission_bridge.report_contract.stock_bootstrap_seed_sha256
        ),
        "formal_report_contract_report_family_count": (
            submission_bridge.report_contract.report_family_count
        ),
        "formal_report_contract_secondary_hypothesis_count": (
            submission_bridge.report_contract.secondary_hypothesis_count
        ),
        "formal_report_contract_strategy_trial_count": (
            submission_bridge.report_contract.strategy_trial_count
        ),
        "secondary_hypothesis_registry_sha256": (
            bindings.secondary_hypothesis_registry_sha256
        ),
        "deflated_sharpe_trial_registry_sha256": (
            bindings.deflated_sharpe_trial_registry_sha256
        ),
        "stock_bootstrap_seed_sha256": bindings.stock_bootstrap_seed_sha256,
        "preoutcome_global_comparator_coverage_record_count": (
            preoutcome_coverage_record_count
        ),
        "preoutcome_global_comparator_coverages_sha256": (
            preoutcome_coverages_sha256
        ),
        "process_authenticated_qc_read": True,
        "content_authenticated": True,
        "result_disposition_authority": False,
        "deployment_authority": False,
        "orders_authority": False,
        "trading_authority": False,
    }


def _build_formal_aggregate_evaluation_receipt_impl(
    *, result_read_receipt: FormalQcSummaryResultReadReceipt,
    result_authority: FormalQcResultReadAuthority,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    expected_bindings: FormalCloudEvaluationBindings,
    _authority_register,
    _authority_require,
) -> FormalAggregateEvaluationReceipt:
    """Mint formal aggregate authority only from the exact QC result-read chain."""

    try:
        submitted = require_streamed_formal_submission_adapter_bridge(
            submission_bridge
        )
    except (FormalQcSubmissionError, AttributeError, TypeError, ValueError) as exc:
        raise FormalEvaluationBridgeError(
            "exact authenticated streamed submission bridge is required"
        ) from exc
    if type(expected_bindings) is not FormalCloudEvaluationBindings:
        raise FormalEvaluationBridgeError("formal cloud bindings changed type")
    expected_bindings.__post_init__()
    _require_submission_derived_bindings(
        submission_bridge=submitted,
        bindings=expected_bindings,
    )
    try:
        require_formal_qc_summary_result_read_receipt(
            result_read_receipt,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
        )
    except (FormalQcSubmissionError, AttributeError, TypeError, ValueError) as exc:
        raise FormalEvaluationBridgeError(
            "process-authenticated QuantConnect result-read receipt is required"
        ) from exc
    aggregate, document, coverage_count, coverage_sha256 = _reconstruct_aggregate(
        result_read_receipt, expected_bindings, submitted
    )
    record = _receipt_record(
        aggregate=aggregate,
        document=document,
        read_receipt=result_read_receipt,
        bindings=expected_bindings,
        submission_bridge=submitted,
        preoutcome_coverage_record_count=coverage_count,
        preoutcome_coverages_sha256=coverage_sha256,
    )
    digest = hashlib.sha256(_canonical_bytes(record)).hexdigest()
    values = {
        "receipt_id": "arv2-formal-aggregate-evaluation-" + digest[:24],
        "receipt_sha256": digest,
        **record,
        "_aggregate_bytes": aggregate,
        "_result_read_receipt": result_read_receipt,
        "_bindings": expected_bindings,
        "_submission_bridge": submitted,
    }
    value = object.__new__(FormalAggregateEvaluationReceipt)
    for name, item in values.items():
        object.__setattr__(value, name, item)
    _authority_register(
        value,
        (
            result_read_receipt,
            result_authority,
            terminal,
            launch,
            submitted,
            _topology(value),
            _canonical_bytes(record),
        ),
    )
    return _authority_require(
        value,
        result_authority=result_authority,
        terminal=terminal,
        launch=launch,
    )


def _require_formal_aggregate_evaluation_receipt_impl(
    value: FormalAggregateEvaluationReceipt,
    *, result_authority: FormalQcResultReadAuthority,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    submission_bridge: StreamedFormalSubmissionAdapterBridge | None = None,
    _authority_current=None,
) -> FormalAggregateEvaluationReceipt:
    if type(value) is not FormalAggregateEvaluationReceipt:
        raise FormalEvaluationBridgeError("formal aggregate receipt changed type")
    registered = _authority_current(value)
    if registered is None or registered[0]() is not value:
        raise FormalEvaluationBridgeError("formal aggregate receipt is not builder-authenticated")
    if (
        registered[1] is not value._result_read_receipt
        or registered[2] is not result_authority
        or registered[3] is not terminal
        or registered[4] is not launch
        or registered[5] is not value._submission_bridge
        or (
            submission_bridge is not None
            and registered[5] is not submission_bridge
        )
        or registered[6] != _topology(value)
        or registered[8] != os.getpid()
    ):
        raise FormalEvaluationBridgeError("formal aggregate parent/topology changed")
    try:
        require_formal_qc_summary_result_read_receipt(
            value._result_read_receipt,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
        )
    except (FormalQcSubmissionError, AttributeError, TypeError, ValueError) as exc:
        raise FormalEvaluationBridgeError("formal aggregate process parent changed") from exc
    try:
        submitted = require_streamed_formal_submission_adapter_bridge(
            value._submission_bridge
        )
    except (FormalQcSubmissionError, AttributeError, TypeError, ValueError) as exc:
        raise FormalEvaluationBridgeError(
            "formal aggregate streamed submission parent changed"
        ) from exc
    _require_submission_derived_bindings(
        submission_bridge=submitted,
        bindings=value._bindings,
    )
    aggregate, document, coverage_count, coverage_sha256 = _reconstruct_aggregate(
        value._result_read_receipt,
        value._bindings,
        submitted,
    )
    record = _receipt_record(
        aggregate=aggregate,
        document=document,
        read_receipt=value._result_read_receipt,
        bindings=value._bindings,
        submission_bridge=submitted,
        preoutcome_coverage_record_count=coverage_count,
        preoutcome_coverages_sha256=coverage_sha256,
    )
    digest = hashlib.sha256(_canonical_bytes(record)).hexdigest()
    expected = {
        "receipt_id": "arv2-formal-aggregate-evaluation-" + digest[:24],
        "receipt_sha256": digest,
        **record,
        "_aggregate_bytes": aggregate,
    }
    if (
        any(getattr(value, name) != item for name, item in expected.items())
        or registered[7] != _canonical_bytes(record)
    ):
        raise FormalEvaluationBridgeError("formal aggregate receipt content changed")
    return value


def _render_formal_aggregate_evaluation_bytes_impl(
    value: FormalAggregateEvaluationReceipt,
    *, result_authority: FormalQcResultReadAuthority,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    submission_bridge: StreamedFormalSubmissionAdapterBridge | None = None,
    _authority_require=None,
) -> bytes:
    _authority_require(
        value,
        result_authority=result_authority,
        terminal=terminal,
        launch=launch,
        submission_bridge=submission_bridge,
    )
    return bytes(value._aggregate_bytes)


def _bind_evaluation_receipt_authority(
    authority_register,
    authority_current,
    build_impl,
    require_impl,
    render_impl,
):
    """Bind the private receipt authority only into its reviewed consumers."""

    def require_formal_aggregate_evaluation_receipt(
        value: FormalAggregateEvaluationReceipt,
        *,
        result_authority: FormalQcResultReadAuthority,
        terminal: FormalQcTerminalStatusReceipt,
        launch: FormalQcLaunchReceipt,
        submission_bridge: StreamedFormalSubmissionAdapterBridge | None = None,
    ) -> FormalAggregateEvaluationReceipt:
        return require_impl(
            value,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
            submission_bridge=submission_bridge,
            _authority_current=authority_current,
        )

    def build_formal_aggregate_evaluation_receipt(
        *,
        result_read_receipt: FormalQcSummaryResultReadReceipt,
        result_authority: FormalQcResultReadAuthority,
        terminal: FormalQcTerminalStatusReceipt,
        launch: FormalQcLaunchReceipt,
        submission_bridge: StreamedFormalSubmissionAdapterBridge,
        expected_bindings: FormalCloudEvaluationBindings,
    ) -> FormalAggregateEvaluationReceipt:
        return build_impl(
            result_read_receipt=result_read_receipt,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
            submission_bridge=submission_bridge,
            expected_bindings=expected_bindings,
            _authority_register=authority_register,
            _authority_require=require_formal_aggregate_evaluation_receipt,
        )

    def render_formal_aggregate_evaluation_bytes(
        value: FormalAggregateEvaluationReceipt,
        *,
        result_authority: FormalQcResultReadAuthority,
        terminal: FormalQcTerminalStatusReceipt,
        launch: FormalQcLaunchReceipt,
        submission_bridge: StreamedFormalSubmissionAdapterBridge | None = None,
    ) -> bytes:
        return render_impl(
            value,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
            submission_bridge=submission_bridge,
            _authority_require=require_formal_aggregate_evaluation_receipt,
        )

    return (
        build_formal_aggregate_evaluation_receipt,
        require_formal_aggregate_evaluation_receipt,
        render_formal_aggregate_evaluation_bytes,
    )


(
    build_formal_aggregate_evaluation_receipt,
    require_formal_aggregate_evaluation_receipt,
    render_formal_aggregate_evaluation_bytes,
) = _bind_evaluation_receipt_authority(
    _evaluation_receipt_authority_register,
    _evaluation_receipt_authority_current,
    _build_formal_aggregate_evaluation_receipt_impl,
    _require_formal_aggregate_evaluation_receipt_impl,
    _render_formal_aggregate_evaluation_bytes_impl,
)
_seal_evaluation_receipt_authority_provenance((
    _build_formal_aggregate_evaluation_receipt_impl,
    build_formal_aggregate_evaluation_receipt,
))

del _make_evaluation_receipt_authority_vault
del _seal_evaluation_receipt_authority_provenance
del _evaluation_receipt_authority_register
del _evaluation_receipt_authority_current
del _build_formal_aggregate_evaluation_receipt_impl
del _require_formal_aggregate_evaluation_receipt_impl
del _render_formal_aggregate_evaluation_bytes_impl
del _bind_evaluation_receipt_authority


__all__ = (
    "AUTHORITY",
    "FormalAggregateEvaluationReceipt",
    "FormalEvaluationBridgeError",
    "MAX_AGGREGATE_BYTES",
    "SCHEMA",
    "STATUS",
    "build_formal_aggregate_evaluation_receipt",
    "render_formal_aggregate_evaluation_bytes",
    "require_formal_aggregate_evaluation_receipt",
)
