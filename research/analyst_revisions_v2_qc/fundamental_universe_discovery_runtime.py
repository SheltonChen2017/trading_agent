"""Bounded LEAN runtime for ARV2 US Fundamentals universe discovery.

Only a dedicated US-fundamental ``Universe`` history request and private
Object Store are used.  The universe selector admits no securities, so the
runtime does not subscribe to security prices, inspect results, touch a
portfolio, or place orders.  Success and refusal both produce a redacted
terminal package whose payload contains hashes, counts, and safe reason IDs.
"""
import gzip
import hashlib
import io
import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

from fundamental_universe_discovery_worker import build_collection_terminals


CONTRACT_SHA256 = "__ARV2_FUNDAMENTAL_DISCOVERY_CONTRACT_SHA256__"
PLAN_SCHEMA = "arv2-qc-fundamental-universe-discovery-plan-v1"
OUTPUT_MANIFEST_SCHEMA = "arv2-qc-fundamental-universe-output-manifest-v1"
OUTPUT_SHARD_SCHEMA = "arv2-qc-fundamental-universe-terminal-shard-v1"
TERMINAL_PACKAGE_SCHEMA = "arv2-qc-fundamental-universe-terminal-package-v1"
FAILURE_SCHEMA = "arv2-qc-fundamental-universe-failure-v1"
OUTPUT_PREFIX = "arv2/fundamental-universe-discovery/output/"

MAX_PLAN_BYTES = 2 * 1024 * 1024
MAX_HISTORY_CALLS = 165
MAX_COLLECTIONS_PER_HISTORY_CALL = 64
MAX_COLLECTION_ROWS = 25_000
MAX_TOTAL_SOURCE_ROWS = 82_500_000
MAX_SHARD_ROWS = 500_000
MAX_TERMINAL_SHARDS = 3_300
MAX_UNCOMPRESSED_SHARD_BYTES = 256 * 1024 * 1024
MAX_COMPRESSED_SHARD_BYTES = 10 * 1024 * 1024
MAX_TOTAL_COMPRESSED_OUTPUT_BYTES = (
    MAX_TERMINAL_SHARDS * MAX_COMPRESSED_SHARD_BYTES
)
MIN_OBJECT_STORE_CAPACITY_BYTES = (
    MAX_TOTAL_COMPRESSED_OUTPUT_BYTES
    + 8 * 1024 * 1024
    + 64 * 1024
    + MAX_PLAN_BYTES
)
MIN_OBJECT_STORE_FILE_CAPACITY = MAX_TERMINAL_SHARDS + 3
NEW_YORK = ZoneInfo("America/New_York")

_CAPACITY_SIZE_BUCKETS = (
    (50 * 1024 * 1024, "size_lt_50mib"),
    (2 * 1024 * 1024 * 1024, "size_50mib_to_lt_2gib"),
    (5 * 1024 * 1024 * 1024, "size_2gib_to_lt_5gib"),
    (10 * 1024 * 1024 * 1024, "size_5gib_to_lt_10gib"),
    (50 * 1024 * 1024 * 1024, "size_10gib_to_lt_50gib"),
)
_CAPACITY_FILE_BUCKETS = (
    (1_000, "files_lt_1000"),
    (20_000, "files_1000_to_lt_20000"),
    (50_000, "files_20000_to_lt_50000"),
    (100_000, "files_50000_to_lt_100000"),
    (500_000, "files_100000_to_lt_500000"),
)


def _canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _read_back_exact(algorithm, key, expected):
    observed = bytes(algorithm.object_store.read_bytes(key))
    if observed != expected:
        raise ValueError("Object Store read-after-write identity changed")


def _save_exact(algorithm, key, payload):
    if not algorithm.object_store.save_bytes(key, payload):
        raise ValueError("Object Store persistence refused")
    _read_back_exact(algorithm, key, payload)


def _require_object_store_capacity(algorithm, plan):
    try:
        maximum_bytes = algorithm.object_store.max_size
        maximum_files = algorithm.object_store.max_files
    except AttributeError as exc:
        raise ValueError("Object Store capacity metadata is unavailable") from exc
    if (
        type(maximum_bytes) is not int
        or type(maximum_files) is not int
    ):
        raise ValueError("Object Store capacity metadata has an invalid type")
    planned_session_count = len(plan["decision_sessions"])
    planned_minimum_bytes = min(
        MIN_OBJECT_STORE_CAPACITY_BYTES,
        planned_session_count * MAX_COMPRESSED_SHARD_BYTES
        + 8 * 1024 * 1024
        + 64 * 1024
        + MAX_PLAN_BYTES,
    )
    planned_minimum_files = min(
        MIN_OBJECT_STORE_FILE_CAPACITY,
        planned_session_count + 3,
    )
    if (
        maximum_bytes < planned_minimum_bytes
        or maximum_files < planned_minimum_files
    ):
        size_bucket = next(
            (
                label
                for ceiling, label in _CAPACITY_SIZE_BUCKETS
                if maximum_bytes < ceiling
            ),
            "size_gte_50gib",
        )
        file_bucket = next(
            (
                label
                for ceiling, label in _CAPACITY_FILE_BUCKETS
                if maximum_files < ceiling
            ),
            "files_gte_500000",
        )
        raise ValueError(
            "Object Store capacity is below the reviewed bound ["
            + size_bucket
            + "_"
            + file_bucket
            + "]"
        )


def _strict_plan(payload, constants):
    if type(payload) is not bytes or not payload or len(payload) > MAX_PLAN_BYTES:
        raise ValueError("discovery plan byte bound changed")
    if (
        len(payload) != constants["PLAN_BYTE_COUNT"]
        or hashlib.sha256(payload).hexdigest() != constants["PLAN_SHA256"]
    ):
        raise ValueError("discovery plan identity changed")
    value = json.loads(payload.decode("utf-8"))
    if _canonical(value) != payload:
        raise ValueError("discovery plan is not canonical")
    if (
        value.get("schema") != PLAN_SCHEMA
        or value.get("contract_sha256") != CONTRACT_SHA256
        or value.get("plan_id") != constants["PLAN_ID"]
        or value.get("terminal_package_key")
        != constants["TERMINAL_PACKAGE_KEY"]
    ):
        raise ValueError("discovery plan contract changed")
    gate = value.get("execution_contract")
    if type(gate) is not dict or set(gate) != {
        "history_dataset",
        "algorithm_time_zone",
        "all_us_equities_including_delisted",
        "object_store_read_write",
        "custom_terminal_summary",
        "price_or_return_access",
        "outcome_or_result_access",
        "orders_or_portfolio_actions",
        "external_launch_authority_embedded",
    } or gate.get("history_dataset") != "Fundamentals":
        raise ValueError("discovery execution contract changed")
    if (
        gate.get("algorithm_time_zone") != "America/New_York"
        or gate.get("all_us_equities_including_delisted") is not True
        or gate.get("object_store_read_write") is not True
        or gate.get("custom_terminal_summary") is not True
        or gate.get("price_or_return_access") is not False
        or gate.get("outcome_or_result_access") is not False
        or gate.get("orders_or_portfolio_actions") is not False
        or gate.get("external_launch_authority_embedded") is not False
    ):
        raise ValueError("discovery capability envelope changed")
    return value


def _collection_geometry(history_index):
    if not isinstance(history_index, tuple) or len(history_index) != 2:
        raise ValueError("Fundamentals history index is not (universe, time)")
    observed = history_index[1]
    if not isinstance(observed, datetime):
        raise ValueError("Fundamentals collection time is not datetime")
    if observed.tzinfo is None or observed.utcoffset() is None:
        local = observed.replace(tzinfo=NEW_YORK)
    else:
        local = observed.astimezone(NEW_YORK)
    if local.timetz().replace(tzinfo=None) >= time(9, 30):
        raise ValueError("Fundamentals collection was not observed before market open")
    return (
        local.date().isoformat(),
        observed.isoformat(timespec="microseconds"),
    )


def _gzip_exact(raw):
    if type(raw) is not bytes or len(raw) > MAX_UNCOMPRESSED_SHARD_BYTES:
        raise ValueError("terminal shard raw byte bound exceeded")
    payload = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(payload) > MAX_COMPRESSED_SHARD_BYTES:
        raise ValueError("terminal shard compressed byte bound exceeded")
    return payload


def _persist_terminal_shard(
    algorithm, constants, descriptors, raw, payload, first_session, last_session,
):
    if (
        not raw
        or not payload
        or len(raw) > MAX_UNCOMPRESSED_SHARD_BYTES
        or len(payload) > MAX_COMPRESSED_SHARD_BYTES
        or len(descriptors) >= MAX_TERMINAL_SHARDS
    ):
        raise ValueError("terminal shard capacity changed")
    digest = hashlib.sha256(payload).hexdigest()
    # LEAN's Object Store path grammar permits one final alphanumeric
    # extension; keep the format marker before that sole dot.
    key = (
        OUTPUT_PREFIX
        + "terminal-shards/"
        + constants["PLAN_SHA256"]
        + "/"
        + digest
        + "-jsonl.gz"
    )
    _save_exact(algorithm, key, payload)
    descriptors.append(
        {
            "schema": OUTPUT_SHARD_SCHEMA,
            "ordinal": len(descriptors),
            "first_session": first_session,
            "last_session": last_session,
            "object_store_key": key,
            "compression": "gzip-level9-mtime0",
            "encoding": "canonical-json-lines-utf8-lf",
            "compressed_sha256": digest,
            "compressed_byte_count": len(payload),
            "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
            "uncompressed_byte_count": len(raw),
            "row_count": len(raw.splitlines()),
        }
    )
    return len(payload)


def _success_package(manifest_key, manifest_payload, manifest):
    return {
        "schema": TERMINAL_PACKAGE_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "status": "completed",
        "output_manifest_key": manifest_key,
        "output_manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "output_manifest_byte_count": len(manifest_payload),
        "decision_session_count": manifest["census"]["decision_session_count"],
        "source_member_count": manifest["census"]["source_member_count"],
        "terminal_count": manifest["census"]["terminal_count"],
        "accepted_count": manifest["census"]["accepted_count"],
        "out_of_scope_count": manifest["census"]["out_of_scope_count"],
        "named_refusal_count": manifest["census"]["named_refusal_count"],
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }


def _safe_refusal_id(error):
    """Return a value-free diagnostic identity for one runtime refusal.

    The digest lets the host compare a cloud refusal with the finite set of
    reviewed constant guard messages without exporting a provider value, a
    security identifier, or arbitrary exception text.  The exception class is
    retained only when it is a bounded Python identifier.
    """

    kind = type(error).__name__
    if (
        type(kind) is not str
        or not kind
        or len(kind) > 64
        or not kind.replace("_", "a").isalnum()
    ):
        kind = "Exception"
    try:
        message = str(error)
    except Exception:
        message = "unprintable"
    capacity_prefix = "Object Store capacity is below the reviewed bound ["
    if (
        kind == "ValueError"
        and message.startswith(capacity_prefix)
        and message.endswith("]")
    ):
        bucket = message[len(capacity_prefix):-1]
        size_labels = tuple(label for _ceiling, label in _CAPACITY_SIZE_BUCKETS) + (
            "size_gte_50gib",
        )
        file_labels = tuple(label for _ceiling, label in _CAPACITY_FILE_BUCKETS) + (
            "files_gte_500000",
        )
        if any(
            bucket == size_label + "_" + file_label
            for size_label in size_labels
            for file_label in file_labels
        ):
            return "discovery_runtime_refused_capacity_" + bucket
    coverage_prefix = "Fundamentals history coverage changed ["
    if (
        kind == "ValueError"
        and message.startswith(coverage_prefix)
        and message.endswith("]")
    ):
        bucket = message[len(coverage_prefix):-1]
        if (
            bucket
            and len(bucket) <= 256
            and all(
                character == "_"
                or (character.isascii() and character.islower())
                or character.isdigit()
                for character in bucket
            )
            and bucket.startswith("missing_")
            and "_matched_" in bucket
            and "_before_" in bucket
            and "_after_" in bucket
            and "_inside_" in bucket
        ):
            return "discovery_runtime_refused_history_coverage_" + bucket
    location = "unknown"
    try:
        traceback = error.__traceback__
        while traceback is not None and traceback.tb_next is not None:
            traceback = traceback.tb_next
        if traceback is not None:
            function = traceback.tb_frame.f_code.co_name
            line = traceback.tb_lineno
            if (
                type(function) is str
                and function
                and len(function) <= 64
                and function.replace("_", "a").isalnum()
                and type(line) is int
                and 1 <= line <= 100_000
            ):
                location = function + "_line_" + str(line)
    except Exception:
        pass
    digest = hashlib.sha256(message.encode("utf-8", errors="replace")).hexdigest()
    return (
        "discovery_runtime_refused_"
        + kind
        + "_at_"
        + location
        + "_"
        + digest[:16]
    )


def _persist_failure(algorithm, constants, safe_reason):
    failure = {
        "schema": FAILURE_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "status": "named_refusal",
        "plan_id": constants["PLAN_ID"],
        "plan_sha256": constants["PLAN_SHA256"],
        "safe_reason": safe_reason,
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }
    failure_bytes = _canonical(failure)
    failure_hash = hashlib.sha256(failure_bytes).hexdigest()
    failure_key = OUTPUT_PREFIX + "failures/" + failure_hash + ".json"
    _save_exact(algorithm, failure_key, failure_bytes)
    package = {
        "schema": TERMINAL_PACKAGE_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "status": "named_refusal",
        "failure_key": failure_key,
        "failure_sha256": failure_hash,
        "failure_byte_count": len(failure_bytes),
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }
    package_bytes = _canonical(package)
    _save_exact(algorithm, constants["TERMINAL_PACKAGE_KEY"], package_bytes)


def _run(algorithm, constants):
    plan_payload = bytes(
        algorithm.object_store.read_bytes(constants["PLAN_OBJECT_STORE_KEY"])
    )
    plan = _strict_plan(plan_payload, constants)
    _require_object_store_capacity(algorithm, plan)
    chunks = plan["history_chunks"]
    if not chunks or len(chunks) > MAX_HISTORY_CALLS:
        raise ValueError("history call count exceeds reviewed bound")

    sessions = {item["decision_session"]: item for item in plan["decision_sessions"]}
    observed_sessions = set()
    descriptors = []
    session_censuses = []
    total_source_rows = 0
    total_compressed_bytes = 0

    for chunk in chunks:
        requested_sequence = list(chunk["decision_sessions"])
        start = datetime.fromisoformat(chunk["request_start"])
        end = datetime.fromisoformat(chunk["request_end_exclusive"])
        history = algorithm.history(
            algorithm._arv2_fundamental_universe,
            start,
            end,
            flatten=False,
        )
        pending_raw = b""
        pending_payload = b""
        pending_first = None
        pending_last = None
        pending_rows = 0
        collection_count = 0
        available_collections = {}
        observed_chunk_sessions = []
        try:
            history_items = history.items()
        except AttributeError as exc:
            raise ValueError("Fundamentals history is not an item series") from exc
        for history_index, collection_members in history_items:
            collection_count += 1
            if collection_count > MAX_COLLECTIONS_PER_HISTORY_CALL:
                raise ValueError("one history call returned too many collections")
            session, collection_time = _collection_geometry(history_index)
            observed_chunk_sessions.append(session)
            if session > requested_sequence[-1]:
                continue
            if session in available_collections:
                raise ValueError("history repeated a Fundamentals collection date")
            available_collections[session] = (
                collection_time,
                list(collection_members),
            )

        selected_collections = {}
        for session in requested_sequence:
            candidates = [
                collection_session
                for collection_session in available_collections
                if collection_session <= session
            ]
            if candidates:
                selected_collections[session] = available_collections[max(candidates)]
        if len(selected_collections) != len(requested_sequence):
            missing = [
                str(index)
                for index, session in enumerate(requested_sequence)
                if session not in selected_collections
            ]
            first_requested = requested_sequence[0]
            last_requested = requested_sequence[-1]
            matched = len(selected_collections)
            before = sum(
                session < first_requested for session in observed_chunk_sessions
            )
            after = sum(
                session > last_requested for session in observed_chunk_sessions
            )
            inside = collection_count - matched - before - after
            raise ValueError(
                "Fundamentals history coverage changed [missing_"
                + "_".join(missing)
                + "_matched_"
                + str(matched)
                + "_before_"
                + str(before)
                + "_after_"
                + str(after)
                + "_inside_"
                + str(inside)
                + "]"
            )

        # Consume the exact requested sessions in the already-authenticated
        # plan order.  A reused collection is necessarily the latest snapshot
        # already available no later than that session; no future collection
        # can enter the selection.
        for session in requested_sequence:
            collection_time, collection_members = selected_collections[session]
            geometry = sessions[session]
            members = list(collection_members)
            if not members:
                raise ValueError("requested Fundamentals collection is empty")
            if len(members) > MAX_COLLECTION_ROWS:
                raise ValueError("Fundamentals collection exceeds row bound")
            terminals, census = build_collection_terminals(
                fundamentals=members,
                decision_session=session,
                decision_session_ordinal=geometry["decision_session_ordinal"],
                decision_open_utc=geometry["decision_open_utc"],
            )
            if len(terminals) != len(members) or not census["all_source_members_terminal"]:
                raise ValueError("worker did not terminal every source member")
            census["qc_history_collection_time"] = collection_time
            census["qc_history_collection_time_zone"] = "America/New_York"
            census["collection_observed_before_decision_open"] = True
            total_source_rows += len(members)
            if total_source_rows > MAX_TOTAL_SOURCE_ROWS:
                raise ValueError("total source row cap exceeded")
            session_raw = b"".join(_canonical(row) for row in terminals)
            session_payload = _gzip_exact(session_raw)
            if len(terminals) > MAX_SHARD_ROWS:
                raise ValueError("one session exceeds the terminal row cap")
            candidate_raw = pending_raw + session_raw
            candidate_rows = pending_rows + len(terminals)
            if pending_raw and (
                len(candidate_raw) > MAX_UNCOMPRESSED_SHARD_BYTES
                or candidate_rows > MAX_SHARD_ROWS
            ):
                candidate_payload = b""
            else:
                candidate_payload = gzip.compress(
                    candidate_raw, compresslevel=9, mtime=0
                )
            if pending_raw and (
                not candidate_payload
                or len(candidate_payload) > MAX_COMPRESSED_SHARD_BYTES
            ):
                total_compressed_bytes += _persist_terminal_shard(
                    algorithm, constants, descriptors, pending_raw,
                    pending_payload, pending_first, pending_last,
                )
                pending_raw = session_raw
                pending_payload = session_payload
                pending_first = session
                pending_rows = len(terminals)
            else:
                pending_raw = candidate_raw
                pending_payload = candidate_payload
                pending_first = pending_first or session
                pending_rows = candidate_rows
            pending_last = session
            if total_compressed_bytes > MAX_TOTAL_COMPRESSED_OUTPUT_BYTES:
                raise ValueError("total compressed output cap exceeded")
            session_censuses.append(census)
            observed_sessions.add(session)
        total_compressed_bytes += _persist_terminal_shard(
            algorithm, constants, descriptors, pending_raw, pending_payload,
            pending_first, pending_last,
        )
        if total_compressed_bytes > MAX_TOTAL_COMPRESSED_OUTPUT_BYTES:
            raise ValueError("total compressed output cap exceeded")

    if observed_sessions != set(sessions):
        raise ValueError("requested decision-session census is incomplete")
    session_censuses.sort(key=lambda item: item["decision_session"])
    descriptor_hash = hashlib.sha256(_canonical(descriptors)).hexdigest()
    counts = {
        name: sum(item[name] for item in session_censuses)
        for name in (
            "source_member_count",
            "terminal_count",
            "qc_sid_bound_count",
            "accepted_count",
            "out_of_scope_count",
            "named_refusal_count",
        )
    }
    if (
        counts["source_member_count"] != counts["terminal_count"]
        or counts["terminal_count"]
        != counts["accepted_count"]
        + counts["out_of_scope_count"]
        + counts["named_refusal_count"]
        or counts["terminal_count"] != sum(item["row_count"] for item in descriptors)
    ):
        raise ValueError("aggregate terminal census changed")

    universe_projection = {
        "schema": "arv2-qc-fundamental-eligible-universe-artifact-v1",
        "selection": "accepted_terminal_rows_projected_to_identity_and_membership",
        "terminal_shard_inventory_sha256": descriptor_hash,
        "row_count": counts["accepted_count"],
    }
    sid_projection = {
        "schema": "arv2-qc-fundamental-sid-mapping-artifact-v1",
        "selection": "all_non_null_qc_security_ids_with_terminal_disposition",
        "terminal_shard_inventory_sha256": descriptor_hash,
        "row_count": counts["qc_sid_bound_count"],
    }
    projections = {
        "eligible_universe": {
            "artifact_id": "arv2-qc-fundamental-eligible-universe-"
            + hashlib.sha256(_canonical(universe_projection)).hexdigest()[:24],
            "artifact_sha256": hashlib.sha256(
                _canonical(universe_projection)
            ).hexdigest(),
            "byte_count": len(_canonical(universe_projection)),
            "row_count": counts["accepted_count"],
            "projection": universe_projection,
        },
        "qc_sid_mapping": {
            "artifact_id": "arv2-qc-fundamental-sid-mapping-"
            + hashlib.sha256(_canonical(sid_projection)).hexdigest()[:24],
            "artifact_sha256": hashlib.sha256(_canonical(sid_projection)).hexdigest(),
            "byte_count": len(_canonical(sid_projection)),
            "row_count": counts["qc_sid_bound_count"],
            "projection": sid_projection,
        },
    }
    manifest = {
        "schema": OUTPUT_MANIFEST_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "status": "completed",
        "plan_id": constants["PLAN_ID"],
        "plan_sha256": constants["PLAN_SHA256"],
        "project_source_set_sha256": constants["PROJECT_SOURCE_SET_SHA256"],
        "source_scope": plan["source_contract"],
        "availability_policy": plan["availability_policy"],
        "first_session": plan["first_session"],
        "last_session": plan["last_session"],
        "decision_session_censuses": session_censuses,
        "terminal_shards": descriptors,
        "terminal_shard_inventory_sha256": descriptor_hash,
        "artifact_projections": projections,
        "census": {
            "decision_session_count": len(session_censuses),
            "history_call_count": len(chunks),
            "terminal_shard_count": len(descriptors),
            **counts,
        },
        "guarantees": {
            "every_requested_session_observed_once": True,
            "every_source_member_terminal_once": True,
            "every_collection_observed_before_decision_open": True,
            "exact_qc_sid_bound_when_source_exposes_sid": True,
            "delisted_members_not_filtered": True,
            "current_ticker_used_as_identity": False,
            "full_pit_universe_established_within_qc_source_scope": True,
            "full_market_peer_census_established_with_terminal_refusals": True,
            "morningstar_publication_timestamp_established": False,
            "vendor_revision_or_tombstone_history_established": False,
            "off_qc_security_master_established": False,
            "production_preopen_input_available": False,
            "USD_statement_facts_established": False,
            "actual_prior_fiscal_year_revenue_established": False,
        },
        "capabilities": {
            "quantconnect_fundamentals_history_access_performed": True,
            "private_object_store_read_write_performed": True,
            "object_store_capacity_preflight_performed": True,
            "provider_credentials_accessed": False,
            "price_or_return_access_performed": False,
            "outcome_access_performed": False,
            "result_access_performed": False,
            "orders_or_portfolio_actions_performed": False,
            "deployment_or_trading_performed": False,
        },
    }
    manifest_payload = _canonical(manifest)
    manifest_hash = hashlib.sha256(manifest_payload).hexdigest()
    manifest_key = OUTPUT_PREFIX + "manifests/" + manifest_hash + ".json"
    _save_exact(algorithm, manifest_key, manifest_payload)
    package = _success_package(manifest_key, manifest_payload, manifest)
    package_payload = _canonical(package)
    _save_exact(algorithm, constants["TERMINAL_PACKAGE_KEY"], package_payload)
    algorithm._arv2_fundamental_discovery_summary = json.dumps(
        {
            "status": "completed",
            "package_sha256": hashlib.sha256(package_payload).hexdigest(),
            "package_byte_count": len(package_payload),
            "terminal_count": counts["terminal_count"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return manifest


def execute_fundamental_universe_discovery(algorithm, constants):
    """Execute once, persisting either a complete manifest or safe refusal."""

    try:
        manifest = _run(algorithm, constants)
        algorithm._arv2_fundamental_discovery_completed = True
        return manifest
    except Exception as error:
        algorithm._arv2_fundamental_discovery_completed = False
        safe_reason = _safe_refusal_id(error)
        try:
            _persist_failure(algorithm, constants, safe_reason)
        except Exception:
            pass
        raise RuntimeError(
            "ARV2 fundamental-universe discovery refused [" + safe_reason + "]"
        ) from None


__all__ = ["execute_fundamental_universe_discovery"]
