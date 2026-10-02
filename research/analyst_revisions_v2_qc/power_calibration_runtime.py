"""Offline source projection for accepted-risk nuisance calibration."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import textwrap

from .power_calibration_bridge import (
    BACKTEST_NAME,
    INPUT_SCHEMA,
    OUTPUT_MANIFEST_SCHEMA,
    OUTPUT_PREFIX,
    PROJECT_NAME,
    AcceptedRiskPowerCalibrationInput,
    canonical_json_bytes,
    require_accepted_risk_power_calibration_input,
)


class PowerCalibrationRuntimeProjectionError(ValueError):
    """The calibration input or projected QC source is invalid."""


ENTRY_PATH = "main.py"
WORKER_PATH = "power_calibration_worker.py"
ENTRY_CLASS_NAME = "AnalystRevisionsV2PowerCalibrationRuntime"
MAX_SOURCE_BYTES = 60_000
HISTORY_BATCH_WIDTH = 100
MAX_DAILY_HISTORY_CALLS = 20_000
MAX_MINUTE_HISTORY_CALLS = 100_000


@dataclasses.dataclass(frozen=True, slots=True)
class PowerCalibrationProjectSource:
    project_path: str
    content_sha256: str
    byte_count: int
    content: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "project_path": self.project_path,
            "content_sha256": self.content_sha256,
            "byte_count": self.byte_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PowerCalibrationQcProjection:
    projection_id: str
    projection_sha256: str
    input_id: str
    input_sha256: str
    input_manifest_key: str
    output_manifest_key: str
    project_name: str
    backtest_name: str
    sources: tuple[PowerCalibrationProjectSource, ...]
    daily_history_call_limit: int
    minute_history_call_limit: int
    formal_outcome_evaluation: bool
    orders_authorized: bool

    def to_record(self) -> dict[str, object]:
        return {
            "input_id": self.input_id,
            "input_sha256": self.input_sha256,
            "input_manifest_key": self.input_manifest_key,
            "output_manifest_key": self.output_manifest_key,
            "project_name": self.project_name,
            "backtest_name": self.backtest_name,
            "sources": [item.to_record() for item in self.sources],
            "daily_history_call_limit": self.daily_history_call_limit,
            "minute_history_call_limit": self.minute_history_call_limit,
            "formal_outcome_evaluation": self.formal_outcome_evaluation,
            "orders_authorized": self.orders_authorized,
        }


def _source(path: str, payload: bytes) -> PowerCalibrationProjectSource:
    if type(payload) is not bytes or not payload or len(payload) > MAX_SOURCE_BYTES:
        raise PowerCalibrationRuntimeProjectionError("calibration source exceeded capacity")
    try:
        text = payload.decode("utf-8")
        tree = ast.parse(text, filename=path)
    except (UnicodeError, SyntaxError) as exc:
        raise PowerCalibrationRuntimeProjectionError("calibration source is not Python") from exc
    forbidden = {
        "market_order", "set_holdings", "liquidate", "submit_order",
        "limit_order", "stop_market_order", "stop_limit_order",
    }
    if any(
        isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name) and node.func.id.casefold() in forbidden
            or isinstance(node.func, ast.Attribute) and node.func.attr.casefold() in forbidden
        )
        for node in ast.walk(tree)
    ):
        raise PowerCalibrationRuntimeProjectionError("calibration source contains order call")
    return PowerCalibrationProjectSource(
        project_path=path,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        content=bytes(payload),
    )


def _entry_source(
    value: AcceptedRiskPowerCalibrationInput,
    *, input_manifest_key: str, output_manifest_key: str,
) -> bytes:
    constants = {
        "INPUT_MANIFEST_KEY": input_manifest_key,
        "INPUT_MANIFEST_SHA256": value.manifest_sha256,
        "INPUT_MANIFEST_BYTE_COUNT": len(value.manifest_bytes),
        "INPUT_SCHEMA": INPUT_SCHEMA,
        "OUTPUT_MANIFEST_SCHEMA": OUTPUT_MANIFEST_SCHEMA,
        "OUTPUT_MANIFEST_KEY": output_manifest_key,
        "INPUT_ID": value.input_id,
        "INPUT_SHA256": value.input_sha256,
        "HISTORY_BATCH_WIDTH": HISTORY_BATCH_WIDTH,
        "MAX_DAILY_HISTORY_CALLS": MAX_DAILY_HISTORY_CALLS,
        "MAX_MINUTE_HISTORY_CALLS": MAX_MINUTE_HISTORY_CALLS,
    }
    literals = "\n".join(
        f"{name} = {json.dumps(item, separators=(',', ':'))}"
        for name, item in constants.items()
    )
    body = r'''
from AlgorithmImports import *
import gzip
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from power_calibration_worker import evaluate_calibration_session

__CONSTANTS__


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


class AnalystRevisionsV2PowerCalibrationRuntime(QCAlgorithm):
    """No-orders collector returning only 483 aggregate nuisance beta states."""

    def initialize(self):
        self.set_start_date(2020, 2, 3)
        self.set_end_date(2020, 2, 4)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.set_cash(100000)
        self._daily_calls = 0
        self._minute_calls = 0
        manifest = self._read_object(
            INPUT_MANIFEST_KEY, INPUT_MANIFEST_SHA256,
            INPUT_MANIFEST_BYTE_COUNT, INPUT_SCHEMA)
        if (manifest.get("input_id") != INPUT_ID
                or manifest.get("input_sha256") != INPUT_SHA256
                or manifest.get("formal_outcome_evaluation") is not False
                or manifest.get("orders_authorized") is not False):
            raise ValueError("calibration input manifest changed")
        output_rows = []
        output_descriptors = []
        for descriptor in manifest["shards"]:
            rows = self._read_rows(descriptor)
            daily, minute = self._collect_observations(rows)
            results = [evaluate_calibration_session(row, daily, minute) for row in rows]
            raw = b"".join(_canonical(row) for row in results)
            compressed = gzip.compress(raw, compresslevel=9, mtime=0)
            compressed_hash = hashlib.sha256(compressed).hexdigest()
            key = "arv2/power-calibration/output/content/" + compressed_hash + ".jsonl.gz"
            if not self.object_store.save_bytes(key, compressed):
                raise ValueError("calibration output shard write failed")
            output_descriptors.append({
                "ordinal": len(output_descriptors),
                "object_store_key": key,
                "content_sha256": hashlib.sha256(raw).hexdigest(),
                "compressed_sha256": compressed_hash,
                "row_count": len(results),
                "uncompressed_byte_count": len(raw),
                "compressed_byte_count": len(compressed),
                "first_session": results[0]["decision_session"],
                "last_session": results[-1]["decision_session"],
            })
            output_rows.extend(results)
        census = {
            "session_count": len(output_rows),
            "valid_date_count": sum(row["state"] == "valid" for row in output_rows),
            "missing_date_count": sum(row["state"] == "missing" for row in output_rows),
            "refused_date_count": sum(row["state"] == "refused" for row in output_rows),
            "component_instance_count": sum(
                row["connected_component_count"] for row in output_rows),
        }
        seed = {
            "schema": OUTPUT_MANIFEST_SCHEMA,
            "input_id": INPUT_ID,
            "input_sha256": INPUT_SHA256,
            "protocol_id": manifest["protocol_id"],
            "protocol_sha256": manifest["protocol_sha256"],
            "calibration_axis_sha256": manifest["calibration_axis_sha256"],
            "shards": output_descriptors,
            "census": census,
            "formal_outcome_evaluation": False,
            "qc_result_statistics_read": False,
            "orders_placed": 0,
        }
        digest = hashlib.sha256(_canonical(seed)).hexdigest()
        output = {
            **seed,
            "output_id": "arv2-accepted-risk-power-output-" + digest[:24],
            "output_sha256": digest,
        }
        payload = _canonical(output)
        if not self.object_store.save_bytes(OUTPUT_MANIFEST_KEY, payload):
            raise ValueError("calibration manifest-last write failed")

    def _read_object(self, key, digest, count, schema):
        if not self.object_store.contains_key(key):
            raise ValueError("calibration Object Store input is absent")
        payload = bytes(self.object_store.read_bytes(key))
        if len(payload) != count or hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("calibration Object Store input changed")
        value = json.loads(payload.decode("utf-8"))
        if type(value) is not dict or value.get("schema") != schema or _canonical(value) != payload:
            raise ValueError("calibration Object Store input is not canonical")
        return value

    def _read_rows(self, descriptor):
        payload = bytes(self.object_store.read_bytes(descriptor["object_store_key"]))
        if (len(payload) != descriptor["compressed_byte_count"]
                or hashlib.sha256(payload).hexdigest() != descriptor["compressed_sha256"]):
            raise ValueError("calibration input shard changed")
        raw = gzip.decompress(payload)
        if (len(raw) != descriptor["uncompressed_byte_count"]
                or hashlib.sha256(raw).hexdigest() != descriptor["content_sha256"]):
            raise ValueError("calibration input shard content changed")
        rows = [json.loads(line) for line in raw.splitlines()]
        if len(rows) != descriptor["row_count"]:
            raise ValueError("calibration input shard row count changed")
        return rows

    def _symbol(self, security_id):
        symbol = self.symbol(security_id)
        if str(symbol.id) != security_id:
            raise ValueError("permanent QC SID did not round trip")
        return symbol

    @staticmethod
    def _batches(values):
        return [values[offset:offset + HISTORY_BATCH_WIDTH]
                for offset in range(0, len(values), HISTORY_BATCH_WIDTH)]

    @staticmethod
    def _text(value):
        return format(value, "f")

    def _collect_observations(self, rows):
        daily_required = set()
        minute_required = set()
        for row in rows:
            if row["preoutcome_disposition"] != "ready":
                continue
            if any(
                decision["terminal_disposition"] is not None
                and decision["terminal_disposition"]["disposition"]
                == "named_terminal_refusal"
                for decision in row["decisions"]
            ):
                # The date is already a named refusal and the worker gives it
                # terminal precedence.  Do not request any outcome for it.
                continue
            daily_required.add((row["benchmark_security_id"], row["decision_session"]))
            daily_required.add((row["benchmark_security_id"], row["exit_session"]))
            for decision in row["decisions"]:
                daily_required.add((decision["security_id"], row["decision_session"]))
                daily_required.add((decision["security_id"], row["exit_session"]))
                for contribution in decision["contributions"]:
                    if contribution["publication_at_utc"] is not None:
                        minute_required.add((
                            decision["security_id"], contribution["publication_at_utc"]
                        ))
        daily = {}
        by_security = {}
        for security_id, session in daily_required:
            by_security.setdefault(security_id, set()).add(session)
        for batch in self._batches(sorted(by_security)):
            start = min(datetime.strptime(session, "%Y-%m-%d")
                        for security in batch for session in by_security[security]) - timedelta(days=8)
            end = max(datetime.strptime(session, "%Y-%m-%d")
                      for security in batch for session in by_security[security]) + timedelta(days=8)
            self._daily_calls += 1
            if self._daily_calls > MAX_DAILY_HISTORY_CALLS:
                raise ValueError("daily History call capacity exceeded")
            try:
                history = self.history[TradeBar](
                    [self._symbol(item) for item in batch], start, end,
                    Resolution.DAILY,
                    data_normalization_mode=DataNormalizationMode.TOTAL_RETURN)
            except Exception:
                history = ()
            for bar in history:
                key = (str(bar.symbol.id), bar.time.date().isoformat())
                if key in daily_required:
                    if key in daily:
                        raise ValueError("daily TotalReturn observation duplicated")
                    daily[key] = self._text(bar.open)
        minute = {}
        by_day = {}
        for security_id, publication in minute_required:
            instant = datetime.fromisoformat(publication[:-1] + "+00:00")
            by_day.setdefault(instant.date(), {}).setdefault(security_id, []).append(
                (publication, instant))
        for day, securities in sorted(by_day.items()):
            for batch in self._batches(sorted(securities)):
                latest = max(instant for security in batch
                             for _, instant in securities[security])
                local_end = latest.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
                self._minute_calls += 1
                if self._minute_calls > MAX_MINUTE_HISTORY_CALLS:
                    raise ValueError("minute History call capacity exceeded")
                try:
                    history = self.history[TradeBar](
                        [self._symbol(item) for item in batch],
                        local_end - timedelta(days=8), local_end,
                        Resolution.MINUTE,
                        data_normalization_mode=DataNormalizationMode.TOTAL_RETURN)
                except Exception:
                    history = ()
                bars = {security: [] for security in batch}
                for bar in history:
                    security = str(bar.symbol.id)
                    if security not in bars:
                        raise ValueError("minute History returned unrequested SID")
                    ended = bar.end_time
                    if ended.tzinfo is None:
                        ended = ended.replace(tzinfo=ZoneInfo("America/New_York"))
                    bars[security].append((ended.astimezone(timezone.utc), bar.close))
                for security in batch:
                    for publication, instant in securities[security]:
                        eligible = [item for item in bars[security] if item[0] < instant]
                        if eligible:
                            minute[(security, publication)] = self._text(
                                max(eligible, key=lambda item: item[0])[1])
        return daily, minute
'''
    return textwrap.dedent(body).replace("__CONSTANTS__", literals).lstrip().encode("utf-8")


def build_power_calibration_qc_projection(
    *, calibration_input: AcceptedRiskPowerCalibrationInput,
    worker_source: bytes,
) -> PowerCalibrationQcProjection:
    calibration_input = require_accepted_risk_power_calibration_input(calibration_input)
    input_key = (
        "arv2/power-calibration/input/manifests/"
        + calibration_input.manifest_sha256 + ".json"
    )
    output_key = OUTPUT_PREFIX + calibration_input.input_sha256 + "/manifest.json"
    sources = (
        _source(ENTRY_PATH, _entry_source(
            calibration_input, input_manifest_key=input_key,
            output_manifest_key=output_key,
        )),
        _source(WORKER_PATH, worker_source),
    )
    seed = {
        "schema": "arv2-power-calibration-qc-projection-v1",
        "input_id": calibration_input.input_id,
        "input_sha256": calibration_input.input_sha256,
        "input_manifest_key": input_key,
        "output_manifest_key": output_key,
        "project_name": PROJECT_NAME,
        "backtest_name": BACKTEST_NAME,
        "sources": [item.to_record() for item in sources],
        "daily_history_call_limit": MAX_DAILY_HISTORY_CALLS,
        "minute_history_call_limit": MAX_MINUTE_HISTORY_CALLS,
        "formal_outcome_evaluation": False,
        "orders_authorized": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    return PowerCalibrationQcProjection(
        projection_id=f"arv2-power-calibration-qc-projection-{digest[:24]}",
        projection_sha256=digest,
        input_id=calibration_input.input_id,
        input_sha256=calibration_input.input_sha256,
        input_manifest_key=input_key,
        output_manifest_key=output_key,
        project_name=PROJECT_NAME,
        backtest_name=BACKTEST_NAME,
        sources=sources,
        daily_history_call_limit=MAX_DAILY_HISTORY_CALLS,
        minute_history_call_limit=MAX_MINUTE_HISTORY_CALLS,
        formal_outcome_evaluation=False,
        orders_authorized=False,
    )


def require_power_calibration_qc_projection(
    value: PowerCalibrationQcProjection,
) -> PowerCalibrationQcProjection:
    if type(value) is not PowerCalibrationQcProjection:
        raise PowerCalibrationRuntimeProjectionError("calibration projection changed type")
    if (
        value.formal_outcome_evaluation is not False
        or value.orders_authorized is not False
        or value.project_name != PROJECT_NAME
        or value.backtest_name != BACKTEST_NAME
        or tuple(item.project_path for item in value.sources) != (ENTRY_PATH, WORKER_PATH)
    ):
        raise PowerCalibrationRuntimeProjectionError("calibration projection changed")
    seed = {"schema": "arv2-power-calibration-qc-projection-v1", **value.to_record()}
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    if (
        value.projection_id != f"arv2-power-calibration-qc-projection-{digest[:24]}"
        or value.projection_sha256 != digest
    ):
        raise PowerCalibrationRuntimeProjectionError("calibration projection identity changed")
    for item in value.sources:
        if hashlib.sha256(item.content).hexdigest() != item.content_sha256:
            raise PowerCalibrationRuntimeProjectionError("calibration source changed")
    return value


__all__ = [
    "PowerCalibrationProjectSource", "PowerCalibrationQcProjection",
    "PowerCalibrationRuntimeProjectionError",
    "build_power_calibration_qc_projection",
    "require_power_calibration_qc_projection",
]
