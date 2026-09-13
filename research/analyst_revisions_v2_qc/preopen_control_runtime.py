"""Bounded QC runtime for ARV2 pre-open control construction."""
from __future__ import annotations

import gzip
import hashlib
import heapq
import io
import json
from datetime import datetime, timedelta, timezone
from itertools import groupby
from zoneinfo import ZoneInfo

from AlgorithmImports import DataNormalizationMode, Resolution, TradeBar
from preopen_control_worker import (
    accumulate_peer_aggregates,
    build_market_control_summaries,
    build_security_batch_terminals,
    peer_aggregate_records,
)

MARKET_OBSERVATION_SCHEMA = "arv2-preopen-control-market-observation-v1"
MARKET_SESSION_SCHEMA = "arv2-preopen-control-market-session-commitment-v1"
INTERMEDIATE_SCHEMA = (
    "arv2-preopen-control-construction-intermediate-commitment-v1"
)
QUALITY_PROJECTION_SCHEMA = "arv2-qdata-physical-measurement-projection-v1"
PEER_PROJECTION_SCHEMA = "arv2-preopen-control-peer-aggregate-projection-v1"
MARKET_PROJECTION_SCHEMA = "arv2-preopen-control-market-session-projection-v1"


def _canonical(value):
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _inline(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _merkle_add(frontier, row):
    node = hashlib.sha256(_canonical({
        "domain": "arv2-terminal-leaf-v1", "record": row,
    })).hexdigest()
    level = 0
    while level in frontier:
        node = hashlib.sha256(_canonical({
            "domain": "arv2-terminal-node-v1",
            "left": frontier.pop(level), "right": node,
        })).hexdigest()
        level += 1
    frontier[level] = node


def _merkle_finish(frontier):
    if not frontier:
        return hashlib.sha256(_canonical({
            "domain": "arv2-empty-terminal-set-v1",
        })).hexdigest()
    ordered = sorted(frontier)
    level = ordered[0]
    node = frontier[level]
    for target in ordered[1:]:
        while level < target:
            node = hashlib.sha256(_canonical({
                "domain": "arv2-terminal-node-v1",
                "left": node, "right": node,
            })).hexdigest()
            level += 1
        node = hashlib.sha256(_canonical({
            "domain": "arv2-terminal-node-v1",
            "left": frontier[target], "right": node,
        })).hexdigest()
        level += 1
    return node


def initialize_runtime_state(algorithm):
    algorithm._output_shards = []
    algorithm._constructed = False
    algorithm._benchmark_rows = None
    algorithm._peer_records = None
    algorithm._market_records = None


def _read_security_batch(algorithm, batch):
    roles = ("universe", "sid_mapping", "fundamentals", "earnings", "guidance", "ratings")
    result = {role: [] for role in roles}
    descriptors = [item for item in algorithm._manifest["shards"]
        if item["security_batch_ordinal"] == batch["security_batch_ordinal"]]
    if (
        sum(item["compressed_byte_count"] for item in descriptors)
        != batch["compressed_input_byte_count"]
        or sum(item["uncompressed_byte_count"] for item in descriptors)
        != batch["uncompressed_input_byte_count"]
        or sum(item["row_count"] for item in descriptors) != batch["input_row_count"]
    ):
        raise ValueError("security-batch input resource census changed")
    seen = set()
    limits = algorithm._manifest["resource_census"]
    for item in descriptors:
        payload = bytes(algorithm.object_store.read_bytes(item["object_store_key"]))
        if (
            len(payload) != item["compressed_byte_count"]
            or len(payload) > limits["maximum_one_security_batch_compressed_input_bytes"]
            or hashlib.sha256(payload).hexdigest() != item["compressed_sha256"]
        ):
            raise ValueError("pre-open input shard identity changed")
        maximum = item["uncompressed_byte_count"]
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            raw = stream.read(maximum + 1)
            extra = stream.read(1)
        if (
            len(raw) != maximum or extra
            or len(raw) > limits["maximum_one_security_batch_uncompressed_input_bytes"]
            or hashlib.sha256(raw).hexdigest() != item["uncompressed_sha256"]
        ):
            raise ValueError("pre-open input shard raw identity changed")
        rows = []
        for line in raw.splitlines(keepends=True):
            row = json.loads(line)
            if _canonical(row) != line or row.get("schema") != item["row_schema"]:
                raise ValueError("pre-open input row is not exact canonical schema")
            identity = hashlib.sha256(line).hexdigest()
            if identity in seen:
                raise ValueError("pre-open security batch repeats a row")
            seen.add(identity)
            rows.append(row)
        if len(rows) != item["row_count"]:
            raise ValueError("pre-open input shard census changed")
        result[item["role"]].extend(rows)
    if set(result) != set(roles):
        raise ValueError("pre-open input security-batch roles changed")
    for role in roles:
        result[role].sort(key=_canonical)
    ids = sorted({row["security_id"] for row in result["universe"]})
    if (
        len(ids) != batch["distinct_security_count"]
        or ids[0] != batch["first_security_id"]
        or ids[-1] != batch["last_security_id"]
    ):
        raise ValueError("security-batch identity range changed")
    return result


def _market_bounds(algorithm):
    sessions = algorithm._manifest["resource_census"]["decision_sessions"]
    opens = [datetime.fromisoformat(
        item["decision_open_utc"].replace("Z", "+00:00")) for item in sessions]
    return min(opens) - timedelta(
        days=algorithm._manifest["resource_census"]["history_lookback_calendar_days"]
    ), max(opens)


def _history_rows(
    algorithm, symbols, start, last, kind, mode, sid_to_logical_security=None,
):
    output = []
    history = algorithm.history[TradeBar](
        symbols, start, last, Resolution.DAILY, data_normalization_mode=mode,
    )
    for bar in history:
        observed_sid = str(bar.symbol.id)
        security_id = (
            sid_to_logical_security.get(observed_sid)
            if sid_to_logical_security is not None else observed_sid
        )
        if not security_id:
            raise ValueError("history returned an unbound QC SecurityIdentifier")
        ended = bar.end_time
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=ZoneInfo("America/New_York"))
        available = ended.astimezone(timezone.utc)
        if available >= last:
            raise ValueError("future bar escaped full-sample history bound")
        output.append({
            "security_id": security_id, "schema": MARKET_OBSERVATION_SCHEMA,
            "kind": kind, "session_ordinal": ended.date().toordinal(),
            "available_at": available.strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
            "close": str(bar.close),
            "volume": str(bar.volume) if kind == "raw" else None,
        })
    return sorted(output, key=_canonical)


def _resolution_refusal(seed, detail):
    semantic = {
        "decision_session": seed["decision_session"],
        "security_id": seed["security_id"],
        "issuer_id": seed["issuer_id"],
        "share_class_id": seed["share_class_id"],
        "listing_id": seed["listing_id"],
        "historical_ticker": seed["historical_ticker"],
        "reason": detail,
        "source_id": seed.get("source_id", "qc-sid-discovery"),
        "source_sha256": seed.get(
            "source_sha256", seed["security_master_row_sha256"]
        ),
        "available_at": seed.get("identity_available_at"),
    }
    refusal = dict(semantic)
    refusal["refusal_sha256"] = hashlib.sha256(_canonical(semantic)).hexdigest()
    return {
        "schema": seed["schema"], "disposition": "named_refusal",
        "decision_session": seed["decision_session"],
        "decision_session_ordinal": seed["decision_session_ordinal"],
        "decision_open_utc": seed["decision_open_utc"],
        "security_id": seed["security_id"], "qc_security_id": None,
        "issuer_id": seed["issuer_id"],
        "share_class_id": seed["share_class_id"],
        "listing_id": seed["listing_id"],
        "historical_ticker": seed["historical_ticker"],
        "security_master_row_sha256": seed["security_master_row_sha256"],
        "qc_sid_mapping_row_sha256": seed["qc_sid_mapping_row_sha256"],
        "census_refusal": refusal,
    }


def _reviewed_batch_symbols(algorithm, inputs):
    """Deserialize only exact prebound SIDs; a display ticker has no authority."""

    mappings = sorted(inputs["sid_mapping"], key=lambda row: row["row_sha256"])
    by_security = {}
    sid_to_logical = {}
    symbols = []
    accepted_logical = {
        row["security_id"] for row in inputs["universe"]
        if row["disposition"] == "accepted"
    }
    for row in mappings:
        logical = row["security_id"]
        encoded_sid = row.get("qc_security_id")
        if (
            type(encoded_sid) is not str
            or not encoded_sid
        ):
            raise ValueError("security batch lacks an exact reviewed QC SID binding")
        if logical in by_security:
            raise ValueError("logical security repeats in reviewed QC SID bindings")
        by_security[logical] = row
        if logical not in accepted_logical:
            if row.get("mapping_status") != "named_refusal_unresolved_cross_vendor_join":
                raise ValueError("refused universe row has an inconsistent SID binding")
            continue
        if (
            row.get("mapping_status")
            != "reviewed_qc_fundamental_discovery_exact_cusip_join"
        ):
            raise ValueError("accepted universe row lacks a reviewed QC SID binding")
        symbol = algorithm.symbol(encoded_sid)
        if str(symbol.id) != encoded_sid:
            raise ValueError("prebound permanent QC SecurityIdentifier changed")
        if encoded_sid in sid_to_logical:
            raise ValueError("QC SecurityIdentifier maps to distinct logical securities")
        sid_to_logical[encoded_sid] = logical
        symbols.append(symbol)
    for seed in inputs["universe"]:
        mapping = by_security.get(seed["security_id"])
        if mapping is None:
            raise ValueError("universe terminal lacks its reviewed QC SID binding")
        if seed.get("qc_security_id") != mapping["qc_security_id"]:
            raise ValueError("universe QC SID differs from reviewed binding")
    return symbols, sid_to_logical


def _stock_history(algorithm, inputs, start, last):
    symbols, sid_to_logical = _reviewed_batch_symbols(algorithm, inputs)
    if not symbols:
        return []
    rows = _history_rows(
        algorithm, symbols, start, last, "total_return",
        DataNormalizationMode.TOTAL_RETURN, sid_to_logical,
    )
    rows.extend(_history_rows(
        algorithm, symbols, start, last, "raw", DataNormalizationMode.RAW,
        sid_to_logical,
    ))
    maximum = algorithm._manifest["resource_census"][
        "maximum_one_batch_market_observation_count"
    ]
    if len(rows) + len(algorithm._benchmark_rows) > maximum:
        raise ValueError("one full-sample market batch exceeded reviewed capacity")
    return rows


def _benchmark_history(algorithm, start, last):
    encoded_sid = algorithm._manifest["benchmark_security_id"]
    symbol = algorithm.symbol(encoded_sid)
    if str(symbol.id) != encoded_sid:
        raise ValueError("prebound benchmark QC SecurityIdentifier changed")
    return _history_rows(
        algorithm, [symbol], start, last, "benchmark_total_return",
        DataNormalizationMode.TOTAL_RETURN,
        {encoded_sid: encoded_sid},
    )


def _session_rows(inputs, session):
    return sorted(
        [row for row in inputs["universe"] if row["decision_session"] == session],
        key=lambda row: row["security_id"],
    )


def _summaries(algorithm, inputs, session, stock_rows):
    rows = _session_rows(inputs, session)
    if not rows:
        raise ValueError("security-batch session has no universe terminals")
    return rows, build_market_control_summaries(
        universe_rows=rows, stock_market_rows=stock_rows,
        benchmark_market_rows=algorithm._benchmark_rows,
        benchmark_security_id=algorithm._manifest["benchmark_security_id"],
    )


def _update_market_state(state, session, lineages, benchmark_security_id):
    benchmark = [row for row in lineages
        if row["role"] == "benchmark_total_return"]
    securities = sorted(
        [row for row in lineages if row["role"] == "security_market"],
        key=lambda row: row["security_id"],
    )
    if len(benchmark) != 1 or benchmark[0]["security_id"] != benchmark_security_id:
        raise ValueError("benchmark market lineage census changed")
    current = state.get(session)
    if current is None:
        current = {
            "benchmark": benchmark[0],
            "chain": hashlib.sha256(_canonical({
                "domain": "arv2-preopen-market-lineage-chain-seed-v1",
                "decision_session": session, "benchmark": benchmark[0],
            })).hexdigest(),
            "security_lineage_count": 0,
            "market_observation_count": benchmark[0]["observation_count"],
            "last_security_id": None,
        }
        state[session] = current
    elif current["benchmark"] != benchmark[0]:
        raise ValueError("benchmark lineage changed between security batches")
    for row in securities:
        if (
            current["last_security_id"] is not None
            and row["security_id"] <= current["last_security_id"]
        ):
            raise ValueError("security market lineage repeats or reorders")
        current["chain"] = hashlib.sha256(_canonical({
            "domain": "arv2-preopen-market-lineage-chain-node-v1",
            "previous_sha256": current["chain"], "record": row,
        })).hexdigest()
        current["security_lineage_count"] += 1
        current["market_observation_count"] += row["observation_count"]
        current["last_security_id"] = row["security_id"]


def _market_records(algorithm, state):
    records = []
    for item in algorithm._manifest["resource_census"]["decision_sessions"]:
        session = item["decision_session"]
        current = state.get(session)
        if current is None:
            raise ValueError("market commitment omitted a decision session")
        semantic = {
            "schema": MARKET_SESSION_SCHEMA, "decision_session": session,
            "benchmark_observation_count": current["benchmark"]["observation_count"],
            "benchmark_observation_sha256": current["benchmark"]["observation_sha256"],
            "security_lineage_count": current["security_lineage_count"],
            "market_observation_count": current["market_observation_count"],
            "security_lineage_chain_sha256": current["chain"],
        }
        semantic["commitment_sha256"] = hashlib.sha256(_canonical(semantic)).hexdigest()
        records.append(semantic)
    return records


def _market_pass(algorithm, *, emit_terminals, peer_records_by_session=None,
                 market_records_by_session=None):
    peer_state = {}
    market_state = {}
    start, last = _market_bounds(algorithm)
    session_index = {item["decision_session"]: index for index, item in enumerate(
        algorithm._manifest["resource_census"]["decision_sessions"])}
    for batch in algorithm._manifest["resource_census"]["security_batches"]:
        inputs = _read_security_batch(algorithm, batch)
        static_roots = {role: hashlib.sha256(_canonical(inputs[role])).hexdigest()
            for role in ("universe", "sid_mapping", "fundamentals", "earnings",
                         "guidance", "ratings")}
        stock_rows = _stock_history(algorithm, inputs, start, last)
        buffers = {}
        sessions = sorted({row["decision_session"] for row in inputs["universe"]})
        if len(sessions) != batch["decision_session_count"]:
            raise ValueError("security-batch decision-session census changed")
        for session in sessions:
            rows, (summaries, lineages) = _summaries(
                algorithm, inputs, session, stock_rows,
            )
            accumulate_peer_aggregates(
                state=peer_state, universe_rows=rows,
                market_control_summaries=summaries,
            )
            _update_market_state(
                market_state, session, lineages,
                algorithm._manifest["benchmark_security_id"],
            )
            if emit_terminals:
                market_commitment = market_records_by_session[session]
                roots = dict(static_roots)
                roots["market_observations"] = market_commitment["commitment_sha256"]
                opened = datetime.fromisoformat(
                    rows[0]["decision_open_utc"].replace("Z", "+00:00")
                )
                policy = algorithm._manifest["source_policy"]
                terminals = build_security_batch_terminals(
                    universe_rows=rows, market_control_summaries=summaries,
                    market_session_commitment=market_commitment,
                    peer_aggregate_rows=peer_records_by_session.get(session, []),
                    benchmark_security_id=algorithm._manifest["benchmark_security_id"],
                    fundamental_rows=inputs["fundamentals"],
                    earnings_rows=inputs["earnings"],
                    guidance_rows=inputs["guidance"], rating_rows=inputs["ratings"],
                    observed_at_utc=(opened - timedelta(microseconds=1)).strftime(
                        "%Y-%m-%dT%H:%M:%S.%fZ"
                    ),
                    rating_source_complete=policy["rating_source_complete"],
                    earnings_source_complete=policy["earnings_source_complete"],
                    guidance_source_complete=policy["guidance_source_complete"],
                    input_roots=roots,
                )
                chunk = session_index[session] // algorithm._manifest[
                    "resource_census"
                ]["decision_chunk_session_count"]
                buffers.setdefault(chunk, []).extend(terminals)
        if emit_terminals:
            for chunk in sorted(buffers):
                _flush_physical_shard(
                    algorithm, chunk, batch["security_batch_ordinal"], buffers[chunk],
                )
        del stock_rows, inputs
    return peer_aggregate_records(peer_state), _market_records(algorithm, market_state)


def _flush_physical_shard(algorithm, chunk, batch, rows):
    rows.sort(key=lambda row: (row["decision_session"], row["security_id"]))
    raw = b"".join(_canonical(row) for row in rows)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    limits = algorithm._manifest["resource_census"]
    if (
        not rows or len(rows) > limits["maximum_buffered_terminal_count"]
        or len(raw) > 256 * 1024 * 1024 or len(compressed) > 32 * 1024 * 1024
    ):
        raise ValueError("pre-open physical terminal shard capacity exceeded")
    digest = hashlib.sha256(compressed).hexdigest()
    key = (
        "arv2/preopen/output/content/control_terminals/chunk-"
        + str(chunk).zfill(4) + "/security-batch-" + str(batch).zfill(4)
        + "/" + digest + ".jsonl.gz"
    )
    if not algorithm.object_store.save_bytes(key, compressed):
        raise ValueError("pre-open physical terminal shard persistence failed")
    security_ids = sorted({row["security_id"] for row in rows})
    algorithm._output_shards.append({
        "schema": "arv2-preopen-control-output-shard-v1",
        "role": "control_terminals", "ordinal": None,
        "decision_chunk_ordinal": chunk, "security_batch_ordinal": batch,
        "partition_first_session": rows[0]["decision_session"],
        "partition_last_session": rows[-1]["decision_session"],
        "first_security_id": security_ids[0], "last_security_id": security_ids[-1],
        "object_store_key": key, "compression": "gzip-level9-mtime0",
        "encoding": "canonical-json-lines-utf8-lf",
        "row_schema": "arv2-preopen-control-terminal-v1",
        "compressed_sha256": digest, "compressed_byte_count": len(compressed),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "uncompressed_byte_count": len(raw), "row_count": len(rows),
    })


class _Cursor:
    def __init__(self, descriptor, payload):
        if (
            len(payload) != descriptor["compressed_byte_count"]
            or hashlib.sha256(payload).hexdigest() != descriptor["compressed_sha256"]
        ):
            raise ValueError("logical merge shard identity changed")
        self.descriptor = descriptor
        self.stream = gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb")
        self.raw_hash = hashlib.sha256()
        self.raw_count = 0
        self.row_count = 0
        self.last_key = None
        self.first_session = None
        self.last_session = None
        self.first_security = None
        self.last_security = None

    def next(self):
        line = self.stream.readline()
        if not line:
            self.stream.close()
            if (
                self.raw_count != self.descriptor["uncompressed_byte_count"]
                or self.raw_hash.hexdigest() != self.descriptor["uncompressed_sha256"]
                or self.row_count != self.descriptor["row_count"]
                or self.first_session != self.descriptor["partition_first_session"]
                or self.last_session != self.descriptor["partition_last_session"]
                or self.first_security != self.descriptor["first_security_id"]
                or self.last_security != self.descriptor["last_security_id"]
            ):
                raise ValueError("logical merge shard census changed")
            return None
        self.raw_hash.update(line)
        self.raw_count += len(line)
        self.row_count += 1
        row = json.loads(line)
        if _canonical(row) != line or row.get("schema") != self.descriptor["row_schema"]:
            raise ValueError("logical merge row is not canonical")
        key = (row.get("decision_session"), row.get("security_id"))
        if self.last_key is not None and key <= self.last_key:
            raise ValueError("physical shard rows repeat or reorder")
        self.last_key = key
        self.first_session = self.first_session or key[0]
        self.last_session = key[0]
        self.first_security = min(self.first_security, key[1]) if self.first_security else key[1]
        self.last_security = max(self.last_security, key[1]) if self.last_security else key[1]
        return row


def _logical_projection(algorithm, market_by_session):
    descriptors = algorithm._output_shards
    universe_sessions = []
    control_sessions = []
    accepted_total = refused_total = terminal_total = measurement_count = 0
    quality_hash = hashlib.sha256()
    quality_hash.update(b'{"measurements":[')
    first_measurement = True
    last_global_key = None
    current_session = None
    terminal_frontier = {}
    universe_frontier = {}
    accepted = refused = terminal_count = 0

    def finish_session():
        nonlocal terminal_frontier, universe_frontier, accepted, refused, terminal_count
        if current_session is None:
            return
        market = market_by_session[current_session]
        universe_sessions.append({
            "schema": "arv2-preopen-control-universe-session-commitment-v1",
            "decision_session": current_session, "accepted_count": accepted,
            "refusal_count": refused, "terminal_count": terminal_count,
            "terminal_merkle_root": _merkle_finish(universe_frontier),
        })
        control_sessions.append({
            "schema": "arv2-preopen-control-session-commitment-v1",
            "decision_session": current_session, "accepted_count": accepted,
            "refusal_count": refused, "terminal_count": terminal_count,
            "terminal_merkle_root": _merkle_finish(terminal_frontier),
            "market_observation_count": market["market_observation_count"],
            "market_observation_sha256": market["commitment_sha256"],
        })
        terminal_frontier = {}
        universe_frontier = {}
        accepted = refused = terminal_count = 0

    for _chunk, grouped in groupby(
        descriptors, key=lambda item: item["decision_chunk_ordinal"],
    ):
        group = list(grouped)
        payloads = []
        if len(group) > algorithm._manifest["resource_census"]["maximum_logical_merge_cursor_count"]:
            raise ValueError("logical merge cursor capacity exceeded")
        for item in group:
            payloads.append(bytes(algorithm.object_store.read_bytes(item["object_store_key"])))
        if sum(map(len, payloads)) > algorithm._manifest["resource_census"][
            "maximum_logical_merge_compressed_bytes"
        ]:
            raise ValueError("logical merge compressed working set exceeded")
        cursors = [_Cursor(item, payload) for item, payload in zip(group, payloads)]
        heap = []
        for index, cursor in enumerate(cursors):
            row = cursor.next()
            if row is not None:
                heapq.heappush(heap, (
                    row["decision_session"], row["security_id"], index, row,
                ))
        while heap:
            session, security_id, index, row = heapq.heappop(heap)
            key = (session, security_id)
            if last_global_key is not None and key <= last_global_key:
                raise ValueError("logical terminal rows repeat or reorder")
            if current_session is not None and session != current_session:
                finish_session()
            current_session = session
            _merkle_add(terminal_frontier, row)
            universe = {
                "terminal": "accepted" if row["disposition"] == "accepted" else "refused",
                "value": row["eligible_security_session"] if
                    row["disposition"] == "accepted" else row["census_refusal"],
            }
            _merkle_add(universe_frontier, universe)
            terminal_count += 1
            terminal_total += 1
            if row["disposition"] == "accepted":
                accepted += 1
                accepted_total += 1
                measurement = row["q_data_measurement"]
                if not first_measurement:
                    quality_hash.update(b",")
                quality_hash.update(_inline(measurement))
                first_measurement = False
                measurement_count += 1
            else:
                refused += 1
                refused_total += 1
            last_global_key = key
            following = cursors[index].next()
            if following is not None:
                heapq.heappush(heap, (
                    following["decision_session"], following["security_id"],
                    index, following,
                ))
        del cursors, payloads
    finish_session()
    declared_sessions = [
        item["decision_session"] for item in
        algorithm._manifest["resource_census"]["decision_sessions"]
    ]
    universe_by_session = {
        item["decision_session"]: item for item in universe_sessions
    }
    control_by_session = {
        item["decision_session"]: item for item in control_sessions
    }
    if not set(universe_by_session).issubset(declared_sessions):
        raise ValueError("logical terminals escaped declared decision sessions")
    empty = _merkle_finish({})
    universe_sessions = [
        universe_by_session.get(session, {
            "schema": "arv2-preopen-control-universe-session-commitment-v1",
            "decision_session": session, "accepted_count": 0,
            "refusal_count": 0, "terminal_count": 0,
            "terminal_merkle_root": empty,
        })
        for session in declared_sessions
    ]
    control_sessions = [
        control_by_session.get(session, {
            "schema": "arv2-preopen-control-session-commitment-v1",
            "decision_session": session, "accepted_count": 0,
            "refusal_count": 0, "terminal_count": 0,
            "terminal_merkle_root": empty,
            "market_observation_count": market_by_session[session][
                "market_observation_count"
            ],
            "market_observation_sha256": market_by_session[session][
                "commitment_sha256"
            ],
        })
        for session in declared_sessions
    ]
    quality_hash.update(
        b'],"schema":"arv2-qdata-physical-measurement-projection-v1"}\n'
    )
    return {
        "universe_sessions": universe_sessions,
        "control_sessions": control_sessions,
        "accepted_count": accepted_total, "refusal_count": refused_total,
        "terminal_count": terminal_total,
        "q_data_measurement_count": measurement_count,
        "q_data_measurement_projection_sha256": quality_hash.hexdigest(),
    }


def run_preopen_control_construction(algorithm):
    start, last = _market_bounds(algorithm)
    algorithm._benchmark_rows = _benchmark_history(algorithm, start, last)
    first_peer, first_market = _market_pass(algorithm, emit_terminals=False)
    peer_by_session = {}
    for row in first_peer:
        peer_by_session.setdefault(row["decision_session"], []).append(row)
    market_by_session = {row["decision_session"]: row for row in first_market}
    second_peer, second_market = _market_pass(
        algorithm, emit_terminals=True,
        peer_records_by_session=peer_by_session,
        market_records_by_session=market_by_session,
    )
    if second_peer != first_peer or second_market != first_market:
        raise ValueError("second full-sample market pass changed its commitments")
    algorithm._peer_records = first_peer
    algorithm._market_records = first_market
    algorithm._output_shards.sort(key=lambda item: (
        item["decision_chunk_ordinal"], item["security_batch_ordinal"],
    ))
    for ordinal, item in enumerate(algorithm._output_shards):
        item["ordinal"] = ordinal
    if len(algorithm._output_shards) != algorithm._manifest["resource_census"][
        "projected_output_shard_count"
    ]:
        raise ValueError("physical terminal shard census changed")
    algorithm._constructed = True


def finalize_preopen_control_construction(algorithm, config, contract_id, contract_sha256):
    if not algorithm._constructed or not algorithm._output_shards:
        raise ValueError("pre-open construction produced no terminal shards")
    market_by_session = {row["decision_session"]: row for row in algorithm._market_records}
    logical = _logical_projection(algorithm, market_by_session)
    peer_projection = hashlib.sha256(_canonical({
        "schema": PEER_PROJECTION_SCHEMA, "records": algorithm._peer_records,
    })).hexdigest()
    market_projection = hashlib.sha256(_canonical({
        "schema": MARKET_PROJECTION_SCHEMA, "records": algorithm._market_records,
    })).hexdigest()
    descriptors = algorithm._output_shards
    intermediates = {
        "schema": INTERMEDIATE_SCHEMA,
        "peer_aggregate_record_count": len(algorithm._peer_records),
        "peer_aggregate_projection_sha256": peer_projection,
        "market_session_commitment_count": len(algorithm._market_records),
        "market_session_projection_sha256": market_projection,
        "physical_terminal_shard_count": len(descriptors),
        "logical_terminal_order": "decision_session_then_security_id",
        "q_data_measurement_count": logical["q_data_measurement_count"],
        "q_data_measurement_projection_sha256": logical[
            "q_data_measurement_projection_sha256"
        ],
    }
    manifest = {
        "schema": config["OUTPUT_MANIFEST_SCHEMA"], "contract_id": contract_id,
        "contract_sha256": contract_sha256,
        "input_manifest": {
            "artifact_id": config["INPUT_MANIFEST_ID"],
            "content_sha256": config["INPUT_MANIFEST_SHA256"],
            "artifact_sha256": config["INPUT_MANIFEST_SHA256"],
            "byte_count": config["INPUT_MANIFEST_BYTE_COUNT"],
        },
        "eligible_universe_source": algorithm._manifest["eligible_universe_source"],
        "qc_sid_mapping_source": algorithm._manifest["qc_sid_mapping_source"],
        "source_policy": algorithm._manifest["source_policy"],
        "construction_resource_census": algorithm._manifest["resource_census"],
        "run_authority": algorithm._manifest["construction_gate"][
            "external_private_run_authority"
        ],
        "input_source_inventory_sha256": algorithm._manifest[
            "input_source_inventory_sha256"
        ],
        "input_role_bindings": algorithm._manifest["input_role_bindings"],
        "truth_source_bindings": algorithm._manifest["truth_source_bindings"],
        "project_source_set_sha256": config["PROJECT_SOURCE_SET_SHA256"],
        "construction_intermediates": intermediates,
        "output_shards": descriptors,
        "output_shard_inventory_sha256": hashlib.sha256(
            _canonical(descriptors)
        ).hexdigest(),
        "universe_sessions": logical["universe_sessions"],
        "control_sessions": logical["control_sessions"],
        "universe_terminal_projection_sha256": hashlib.sha256(_canonical({
            "domain": "arv2-preopen-universe-session-projection-v1",
            "records": logical["universe_sessions"],
        })).hexdigest(),
        "control_terminal_projection_sha256": hashlib.sha256(_canonical({
            "domain": "arv2-preopen-control-session-projection-v1",
            "records": logical["control_sessions"],
        })).hexdigest(),
        "census": {
            "universe_terminal_count": logical["terminal_count"],
            "control_accepted_count": logical["accepted_count"],
            "control_refusal_count": logical["refusal_count"],
            "control_terminal_count": logical["terminal_count"],
        },
        "capabilities": {
            "provider_access": False, "credential_access": False,
            "filesystem_access": False, "quantconnect_access": False,
            "object_store_access": False, "price_access": False,
            "outcome_access": False, "result_access": False,
            "deployment": False, "orders": False, "trading": False,
        },
    }
    manifest_bytes = _canonical(manifest)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_key = config["OUTPUT_PREFIX"] + "manifests/" + manifest_hash + ".json"
    if not algorithm.object_store.save_bytes(manifest_key, manifest_bytes):
        raise ValueError("pre-open output manifest persistence failed")
    package = {
        "schema": config["TERMINAL_PACKAGE_SCHEMA"],
        "contract_id": contract_id, "contract_sha256": contract_sha256,
        "input_manifest": manifest["input_manifest"],
        "project_source_set_sha256": config["PROJECT_SOURCE_SET_SHA256"],
        "output_manifest": {
            "artifact_id": "arv2-preopen-control-output-" + manifest_hash[:24],
            "content_sha256": manifest_hash, "artifact_sha256": manifest_hash,
            "byte_count": len(manifest_bytes), "object_store_key": manifest_key,
        },
        "output_shard_inventory_sha256": manifest[
            "output_shard_inventory_sha256"
        ],
        "universe_terminal_projection_sha256": manifest[
            "universe_terminal_projection_sha256"
        ],
        "control_terminal_projection_sha256": manifest[
            "control_terminal_projection_sha256"
        ],
        "q_data_measurement_projection_sha256": intermediates[
            "q_data_measurement_projection_sha256"
        ],
        "census": manifest["census"],
        "outcome_statistics_log_order_accessed": False,
    }
    package_bytes = _canonical(package)
    if len(package_bytes) > 64 * 1024:
        raise ValueError("pre-open terminal package exceeds bound")
    if not algorithm.object_store.save_bytes(
        config["TERMINAL_PACKAGE_KEY"], package_bytes
    ):
        raise ValueError("pre-open terminal package persistence failed")
    receipt = {
        "schema": config["SUMMARY_SCHEMA"], "manifest_sha256": manifest_hash,
        "manifest_byte_count": len(manifest_bytes),
        "source_set_sha256": config["PROJECT_SOURCE_SET_SHA256"],
        "terminal_count": logical["terminal_count"],
        "accepted_count": logical["accepted_count"],
        "refusal_count": logical["refusal_count"], "shard_count": len(descriptors),
    }
    algorithm.set_summary_statistic(
        config["SUMMARY_NAME"], _canonical(receipt).decode("utf-8").strip(),
    )


__all__ = [
    "finalize_preopen_control_construction", "initialize_runtime_state",
    "run_preopen_control_construction",
]
