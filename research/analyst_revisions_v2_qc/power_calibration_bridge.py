"""Accepted-risk ARV2 nuisance power-calibration bridge.

This additive bridge leaves the frozen ARV2-4D-B artifacts untouched.  It
composes an outcome-free 483-session H20 input from the authenticated current-
row scoring stack, authenticates a future owner-only QC output archive, and
computes only the frozen nuisance power quantities.  Nothing here contacts a
provider or QuantConnect.

Every calibration date remains at its exact NYSE-axis position as ``valid``,
``missing``, or ``refused``.  Missing dates are never compressed and refused
dates are never zero-filled.
"""
from __future__ import annotations

import dataclasses
import gzip
import hashlib
import json
import os
import re
import stat
import sys
import threading
import weakref
from datetime import date
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    localcontext,
)
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from data.exchange_calendar import resolve_nth_session_after, trading_sessions
from research.analyst_revisions_v2.power_calibration_protocol import (
    CALIBRATION_AXIS_SHA256,
    CALIBRATION_FOLD_HASH,
    CALIBRATION_FOLD_ID,
    CALIBRATION_SESSION_COUNT,
    CALIBRATION_START,
    HAC_MAX_LAG,
    MINIMUM_ABSOLUTE_FLOOR,
    TEST_SESSION_CAPACITY,
    PowerCalibrationProtocol,
    PowerCalibrationProtocolError,
    ProvisionalPowerDisposition,
    derive_provisional_power_requirement,
    require_loaded_power_calibration_protocol,
)
from research.analyst_revisions_v2.power_calibration_input_schema import (
    POWER_PROTOCOL_HASH,
    POWER_PROTOCOL_ID,
)


class AcceptedRiskPowerCalibrationError(ValueError):
    """A calibration parent, archive, result, or floor is inauthentic."""


class CalibrationBetaState(str, Enum):
    VALID = "valid"
    MISSING = "missing"
    REFUSED = "refused"


INPUT_SCHEMA = "arv2-accepted-risk-power-calibration-input-v1"
INPUT_SHARD_SCHEMA = "arv2-accepted-risk-power-calibration-input-shard-v1"
INPUT_ROW_SCHEMA = "arv2-accepted-risk-power-calibration-session-v1"
OUTPUT_MANIFEST_SCHEMA = "arv2-accepted-risk-power-calibration-output-manifest-v1"
OUTPUT_SHARD_SCHEMA = "arv2-accepted-risk-power-calibration-output-shard-v1"
OUTPUT_ROW_SCHEMA = "arv2-accepted-risk-power-calibration-beta-state-v1"
RECEIPT_SCHEMA = "arv2-accepted-risk-power-calibration-receipt-v1"
SUCCESSOR_SCHEMA = "arv2-accepted-risk-stock-power-successor-v1"
FORMAL_CENSUS_SCHEMA = "arv2-accepted-risk-formal-test-power-census-v2"
PROJECT_NAME = "ARV2_POWER_CALIBRATION_H20_2018_2019_20260912"
BACKTEST_NAME = "ARV2 accepted-risk nuisance power calibration H20 2018-2019"
OUTPUT_PREFIX = "arv2/power-calibration/output/"
INPUT_PREFIX = "arv2/power-calibration/input/"
CALIBRATION_LAST_SESSION = "2019-12-31"
CALIBRATION_LAST_OUTCOME_SESSION = "2020-01-30"
CALIBRATION_TRAIN_START = "2013-01-02"
CALIBRATION_TRAIN_END_EXCLUSIVE = "2018-01-02"
CALIBRATION_TERMINAL_CALCULATION_AS_OF = "2026-09-12"
SHARD_SESSION_WIDTH = 10
MAX_INPUT_SHARDS = 64
MAX_INPUT_SHARD_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_SHARDS = 64
MAX_OUTPUT_SHARD_BYTES = 4 * 1024 * 1024
MAX_SESSION_SECURITY_COUNT = 30_000
MAX_SESSION_MINUTE_REQUIREMENTS = 100_000
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,511}\Z")
_DECIMAL_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise AcceptedRiskPowerCalibrationError("value is not canonical JSON") from exc


def _decimal_text(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        raise AcceptedRiskPowerCalibrationError("value is not a finite Decimal")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _decimal(value: object, name: str, *, positive: bool = False) -> Decimal:
    if type(value) is not str or _DECIMAL_TEXT.fullmatch(value) is None:
        raise AcceptedRiskPowerCalibrationError(f"{name} is not canonical Decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise AcceptedRiskPowerCalibrationError(f"{name} is not Decimal") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise AcceptedRiskPowerCalibrationError(f"{name} is outside its domain")
    if _decimal_text(parsed) != value:
        raise AcceptedRiskPowerCalibrationError(f"{name} is not canonical Decimal text")
    return parsed


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise AcceptedRiskPowerCalibrationError(f"{name} is not SHA-256")
    return value


def _safe(value: object, name: str) -> str:
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        raise AcceptedRiskPowerCalibrationError(f"{name} is not a safe identifier")
    return value


def _count(value: object, name: str, *, zero: bool = True) -> int:
    if type(value) is not int or value < (0 if zero else 1):
        raise AcceptedRiskPowerCalibrationError(f"{name} is not an exact count")
    return value


def calibration_axis() -> tuple[str, ...]:
    sessions = tuple(
        item.isoformat()
        for item in trading_sessions(
            date.fromisoformat(CALIBRATION_START),
            date.fromisoformat(CALIBRATION_LAST_SESSION),
        )
    )
    if (
        len(sessions) != CALIBRATION_SESSION_COUNT
        or sessions[0] != CALIBRATION_START
        or sessions[-1] != CALIBRATION_LAST_SESSION
        or hashlib.sha256(
            json.dumps(
                sessions, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        != CALIBRATION_AXIS_SHA256
    ):
        raise AcceptedRiskPowerCalibrationError("frozen calibration axis changed")
    return sessions


@dataclasses.dataclass(frozen=True, slots=True)
class CalibrationShardDescriptor:
    ordinal: int
    object_store_key: str
    content_sha256: str
    compressed_sha256: str
    row_count: int
    uncompressed_byte_count: int
    compressed_byte_count: int
    first_session: str
    last_session: str

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class AcceptedRiskPowerCalibrationInput:
    input_id: str
    input_sha256: str
    protocol_id: str
    protocol_sha256: str
    source_archive_id: str
    source_archive_sha256: str
    production_evidence_receipt_id: str
    production_evidence_receipt_sha256: str
    protocol: PowerCalibrationProtocol = dataclasses.field(repr=False)
    source_archive: object = dataclasses.field(repr=False)
    production_evidence: object = dataclasses.field(repr=False)
    terminal_build: object = dataclasses.field(repr=False)
    physical_scoring_stream: object | None = dataclasses.field(repr=False)
    terminal_build_id: str
    terminal_build_sha256: str
    terminal_package_id: str
    terminal_package_sha256: str
    terminal_requirement_count: int
    benchmark_security_id: str
    manifest_bytes: bytes = dataclasses.field(repr=False)
    manifest_sha256: str
    shard_paths: tuple[Path, ...] = dataclasses.field(repr=False)
    shard_descriptors: tuple[CalibrationShardDescriptor, ...]
    path_fingerprints: tuple[tuple[int, ...], ...] = dataclasses.field(repr=False)
    calibration_session_count: int
    scored_row_count: int
    preoutcome_refusal_count: int
    component_instance_count: int
    minute_requirement_count: int
    outcome_access: bool
    quantconnect_access: bool


@dataclasses.dataclass(frozen=True, slots=True)
class CalibrationBetaRecord:
    decision_session: str
    state: CalibrationBetaState
    beta_value: Decimal | None
    connected_component_count: int
    reason: str | None
    input_session_sha256: str
    output_lineage_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "schema": OUTPUT_ROW_SCHEMA,
            "decision_session": self.decision_session,
            "state": self.state.value,
            "beta_value": None if self.beta_value is None else _decimal_text(self.beta_value),
            "connected_component_count": self.connected_component_count,
            "reason": self.reason,
            "input_session_sha256": self.input_session_sha256,
            "output_lineage_sha256": self.output_lineage_sha256,
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class AcceptedRiskPowerCalibrationOutput:
    output_id: str
    output_sha256: str
    input_id: str
    input_sha256: str
    protocol_id: str
    protocol_sha256: str
    calibration_input: AcceptedRiskPowerCalibrationInput = dataclasses.field(
        repr=False
    )
    terminal_receipt: object = dataclasses.field(repr=False)
    records: tuple[CalibrationBetaRecord, ...]
    manifest_path: Path = dataclasses.field(repr=False)
    shard_paths: tuple[Path, ...] = dataclasses.field(repr=False)
    file_fingerprints: tuple[tuple[int, ...], ...] = dataclasses.field(repr=False)
    valid_date_count: int
    missing_date_count: int
    refused_date_count: int
    component_instance_count: int
    complete_axis: bool
    qc_result_statistics_read: bool
    formal_outcome_evaluation: bool


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class AcceptedRiskPowerCalibrationReceipt:
    receipt_id: str
    receipt_hash: str
    output: AcceptedRiskPowerCalibrationOutput = dataclasses.field(repr=False)
    protocol: PowerCalibrationProtocol = dataclasses.field(repr=False)
    protocol_id: str
    protocol_hash: str
    manifest_id: str
    manifest_content_sha256: str
    valid_beta_date_count: int
    lag_pair_counts_0_through_20: tuple[int, ...]
    long_run_variance: Decimal
    component_count_census_sha256: str
    component_count_census_session_count: int
    q05_components_per_date: int
    raw_required_valid_dates: int
    required_valid_dates: int
    required_connected_components: int
    fixed_h20_test_session_capacity: int
    disposition: ProvisionalPowerDisposition
    accepted_risk_policy_id: str
    output_id: str
    output_sha256: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class AcceptedRiskStockPowerSuccessor:
    successor_id: str
    successor_sha256: str
    receipt_id: str
    receipt_sha256: str
    required_valid_dates: int
    required_connected_components: int
    disposition: str
    outcome_access: bool
    qc_action: bool
    deployment: bool
    orders: bool


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class AuthenticatedFormalTestPowerCensus:
    census_id: str
    census_sha256: str
    scoring_artifact: object = dataclasses.field(repr=False)
    scoring_artifact_id: str
    scoring_artifact_sha256: str
    h20_test_session_capacity: int
    preoutcome_candidate_date_count: int
    valid_h20_test_session_count: int
    refused_h20_test_session_count: int
    missing_h20_test_session_count: int
    connected_component_instance_count: int
    complete_axis: bool


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class AuthenticatedPowerFloorBinding:
    binding_id: str
    binding_sha256: str
    power_floor: object
    formal_power: object
    receipt: AcceptedRiskPowerCalibrationReceipt = dataclasses.field(repr=False)
    successor: AcceptedRiskStockPowerSuccessor = dataclasses.field(repr=False)
    formal_census: AuthenticatedFormalTestPowerCensus = dataclasses.field(
        repr=False
    )
    receipt_id: str
    receipt_sha256: str
    successor_id: str
    successor_sha256: str
    formal_census_id: str
    formal_census_sha256: str
    scoring_artifact_id: str
    scoring_artifact_sha256: str
    h20_test_session_capacity: int
    preoutcome_candidate_date_count: int
    valid_h20_test_session_count: int
    refused_h20_test_session_count: int
    missing_h20_test_session_count: int
    connected_component_instance_count: int
    observed_valid_dates: int
    observed_connected_components: int


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PowerCalibrationQcTerminalReceipt:
    terminal_id: str
    terminal_sha256: str
    plan_id: str
    plan_sha256: str
    input_id: str
    input_sha256: str
    project_id: str
    backtest_id: str
    terminal_status: str
    output_manifest_key: str


_INPUTS: dict[int, tuple[object, ...]] = {}
_OUTPUTS: dict[int, tuple[weakref.ReferenceType[AcceptedRiskPowerCalibrationOutput], tuple[object, ...]]] = {}
_RECEIPTS: dict[int, tuple[object, ...]] = {}
_SUCCESSORS: dict[int, tuple[weakref.ReferenceType[AcceptedRiskStockPowerSuccessor], weakref.ReferenceType[AcceptedRiskPowerCalibrationReceipt], bytes]] = {}
_FORMAL_CENSUSES: dict[int, tuple[object, ...]] = {}
_POWER_FLOORS: dict[int, tuple[object, ...]] = {}
_QC_TERMINALS: dict[int, tuple[weakref.ReferenceType[PowerCalibrationQcTerminalReceipt], bytes]] = {}
_LOCK = threading.RLock()


def _reset_power_authorities_after_fork() -> None:
    global _INPUTS, _OUTPUTS, _RECEIPTS, _SUCCESSORS
    global _FORMAL_CENSUSES, _POWER_FLOORS, _QC_TERMINALS, _LOCK

    _INPUTS = {}
    _OUTPUTS = {}
    _RECEIPTS = {}
    _SUCCESSORS = {}
    _FORMAL_CENSUSES = {}
    _POWER_FLOORS = {}
    _QC_TERMINALS = {}
    _LOCK = threading.RLock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_power_authorities_after_fork)


def _make_power_artifact_authority():
    """Create the process-local provenance vault for the power artifact chain.

    The public dictionaries are retained only as bounded-state inspection
    surfaces.  An entry authenticates only when it is the *same tuple object*
    held by this closure.  Consequently replacing a public entry with
    caller-composed bytes can revoke an artifact but can never reseal one.
    """

    records: tuple[tuple[str, int, tuple[object, ...]], ...] = ()
    register_callers: tuple[tuple[str, object, int, str], ...] = ()
    terminal_persistence_chain: tuple[
        tuple[object, int, str, tuple[tuple[str, object], ...]], ...
    ] = ()
    terminal_submission_module: object | None = None
    terminal_minter_claimed = False
    rlock_factory = threading.RLock
    lock = rlock_factory()
    getpid = os.getpid
    realpath = os.path.realpath
    getframe = sys._getframe
    authority_pid = getpid()
    bridge_module_name = __name__
    bridge_module_path = realpath(__file__)
    submission_module_name = (
        "research.analyst_revisions_v2_qc.power_calibration_submission_adapter"
    )
    submission_module_path = realpath(
        os.path.join(
            os.path.dirname(__file__),
            "power_calibration_submission_adapter.py",
        )
    )
    function_type = type(lambda: None)

    def public_registry(kind: str) -> dict[int, tuple[object, ...]]:
        registry = {
            "input": _INPUTS,
            "output": _OUTPUTS,
            "receipt": _RECEIPTS,
            "successor": _SUCCESSORS,
            "terminal": _QC_TERMINALS,
        }.get(kind)
        if type(registry) is not dict:
            raise AcceptedRiskPowerCalibrationError(
                "power artifact public registry changed"
            )
        return registry

    def expected_caller(kind: str, frame: object) -> None:
        matches = tuple(
            item for item in register_callers if item[0] == kind
        )
        if (
            not matches
            or getpid() != authority_pid
            or not any(
                frame.f_code is match[1]
                and id(frame.f_globals) == match[2]
                and realpath(frame.f_code.co_filename) == match[3]
                for match in matches
            )
        ):
            raise AcceptedRiskPowerCalibrationError(
                "power artifact registration caller changed"
            )

    def forget(kind: str, identity: int, reference: object) -> None:
        nonlocal records
        with lock:
            matching = next(
                (
                    item for item in records
                    if item[0] == kind and item[1] == identity
                ),
                None,
            )
            if matching is not None and matching[2][0] is reference:
                records = tuple(item for item in records if item is not matching)
                public = public_registry(kind)
                if public.get(identity) is matching[2]:
                    public.pop(identity, None)

    def register(
        kind: str,
        caller_frame: object,
        value: object,
        *lineage: object,
    ) -> tuple[object, ...]:
        nonlocal records
        expected_caller(kind, caller_frame)
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda ref, category=kind, key=identity: forget(category, key, ref),
        )
        entry = (reference, *lineage, getpid())
        with lock:
            public = public_registry(kind)
            if (
                any(item[0] == kind and item[1] == identity for item in records)
                or identity in public
            ):
                raise AcceptedRiskPowerCalibrationError(
                    "power artifact identity was reused"
                )
            records = (*records, (kind, identity, entry))
            public[identity] = entry
        return entry

    def current(kind: str, value: object) -> tuple[object, ...] | None:
        nonlocal records
        identity = id(value)
        with lock:
            matching = next(
                (
                    item for item in records
                    if item[0] == kind and item[1] == identity
                ),
                None,
            )
            private = None if matching is None else matching[2]
            public_records = public_registry(kind)
            public = public_records.get(identity)
            if (
                private is None
                or public is not private
                or private[0]() is not value
                or private[-1] != getpid()
            ):
                if matching is not None:
                    records = tuple(item for item in records if item is not matching)
                public_records.pop(identity, None)
                return None
            return private

    def seal_builder_callers(
        *, input_builder: object, physical_input_builder: object,
        output_loader: object,
        receipt_builder: object, successor_builder: object,
    ) -> None:
        nonlocal register_callers
        specifications = (
            ("input", input_builder, "_build_accepted_risk_power_calibration_input_impl"),
            (
                "input",
                physical_input_builder,
                "_build_physical_accepted_risk_power_calibration_input_impl",
            ),
            ("output", output_loader, "_load_accepted_risk_power_calibration_output_impl"),
            ("receipt", receipt_builder, "_compute_accepted_risk_power_calibration_receipt_impl"),
            ("successor", successor_builder, "_build_accepted_risk_stock_power_successor_impl"),
        )
        if register_callers:
            raise AcceptedRiskPowerCalibrationError(
                "power artifact registration provenance was already sealed"
            )
        sealed: tuple[tuple[str, object, int, str], ...] = ()
        for kind, function, expected_name in specifications:
            if (
                type(function) is not function_type
                or function.__module__ != bridge_module_name
                or function.__globals__ is not globals()
                or function.__code__.co_name != expected_name
                or realpath(function.__code__.co_filename) != bridge_module_path
            ):
                raise AcceptedRiskPowerCalibrationError(
                    "power artifact registration provenance changed"
                )
            sealed = (*sealed, (
                kind,
                function.__code__,
                id(function.__globals__),
                bridge_module_path,
            ))
        register_callers = sealed

    def register_input(
        value: AcceptedRiskPowerCalibrationInput,
        protocol: PowerCalibrationProtocol,
        archive: object,
        evidence: object,
        terminal_build: object,
        physical_scoring_stream: object | None,
        manifest_bytes: bytes,
        path_fingerprints: tuple[tuple[int, ...], ...],
    ) -> None:
        caller = getframe(1)
        expected_caller("input", caller)
        register(
            "input",
            caller,
            value,
            weakref.ref(protocol),
            weakref.ref(archive),
            weakref.ref(evidence),
            weakref.ref(terminal_build),
            (
                None
                if physical_scoring_stream is None
                else weakref.ref(physical_scoring_stream)
            ),
            manifest_bytes,
            path_fingerprints,
        )

    def current_input(value: AcceptedRiskPowerCalibrationInput):
        return current("input", value)

    def register_output(
        value: AcceptedRiskPowerCalibrationOutput,
        calibration_input: AcceptedRiskPowerCalibrationInput,
        terminal: PowerCalibrationQcTerminalReceipt,
        fingerprint: tuple[object, ...],
    ) -> None:
        caller = getframe(1)
        expected_caller("output", caller)
        register(
            "output",
            caller,
            value,
            weakref.ref(calibration_input),
            weakref.ref(terminal),
            fingerprint,
        )

    def current_output(value: AcceptedRiskPowerCalibrationOutput):
        return current("output", value)

    def register_receipt(
        value: AcceptedRiskPowerCalibrationReceipt,
        output: AcceptedRiskPowerCalibrationOutput,
        protocol: PowerCalibrationProtocol,
        record_bytes: bytes,
        digest: str,
        fingerprint: tuple[object, ...],
    ) -> None:
        caller = getframe(1)
        expected_caller("receipt", caller)
        register(
            "receipt",
            caller,
            value,
            weakref.ref(output),
            weakref.ref(protocol),
            record_bytes,
            digest,
            fingerprint,
        )

    def current_receipt(value: AcceptedRiskPowerCalibrationReceipt):
        return current("receipt", value)

    def register_successor(
        value: AcceptedRiskStockPowerSuccessor,
        receipt: AcceptedRiskPowerCalibrationReceipt,
        record_bytes: bytes,
    ) -> None:
        caller = getframe(1)
        expected_caller("successor", caller)
        register(
            "successor",
            caller,
            value,
            weakref.ref(receipt),
            record_bytes,
        )

    def current_successor(value: AcceptedRiskStockPowerSuccessor):
        return current("successor", value)

    def register_terminal(
        value: PowerCalibrationQcTerminalReceipt,
        calibration_input: AcceptedRiskPowerCalibrationInput,
        record_bytes: bytes,
    ) -> None:
        caller = getframe(1)
        expected_caller("terminal", caller)
        register(
            "terminal",
            caller,
            value,
            weakref.ref(calibration_input),
            record_bytes,
        )

    def current_terminal(value: PowerCalibrationQcTerminalReceipt):
        return current("terminal", value)

    def claim_terminal_minter(persistence_function):
        """Return the sole terminal minter once, bound to this private vault."""

        nonlocal register_callers, terminal_minter_claimed
        nonlocal terminal_submission_module
        try:
            caller = getframe(1)
            caller_globals = caller.f_globals
            persistence_code = persistence_function.__code__
            persistence_globals = persistence_function.__globals__
            registered_submission = sys.modules.get(submission_module_name)
        except (AttributeError, TypeError, ValueError):
            caller = None
            caller_globals = None
            persistence_code = None
            persistence_globals = None
            registered_submission = None
        if (
            getpid() != authority_pid
            or caller is None
            or caller.f_code.co_name != "<module>"
            or caller_globals.get("__name__") != submission_module_name
            or type(registered_submission) is not type(sys)
            or vars(registered_submission) is not caller_globals
            or realpath(caller.f_code.co_filename) != submission_module_path
            or type(persistence_function) is not function_type
            or persistence_function.__module__ != submission_module_name
            or persistence_globals is not caller_globals
            or persistence_code.co_name != "_persist_power_calibration_output_impl"
            or realpath(persistence_code.co_filename) != submission_module_path
        ):
            raise AcceptedRiskPowerCalibrationError(
                "power-calibration QC terminal minter claim is adapter-private"
            )
        with lock:
            if terminal_minter_claimed:
                raise AcceptedRiskPowerCalibrationError(
                    "power-calibration QC terminal minter was already claimed"
                )
            terminal_minter_claimed = True
            terminal_submission_module = registered_submission
        creator_pid = getpid()

        def mint(
            *, plan_id: str, plan_sha256: str,
            calibration_input: AcceptedRiskPowerCalibrationInput,
            project_id: str, backtest_id: str, output_manifest_key: str,
        ) -> PowerCalibrationQcTerminalReceipt:
            mint_caller = getframe(1)
            current_frame = mint_caller
            valid = (
                getpid() == creator_pid
                and len(terminal_persistence_chain) == 2
            )
            for code, globals_id, path, bindings in terminal_persistence_chain:
                if (
                    not valid
                    or current_frame is None
                    or current_frame.f_code is not code
                    or id(current_frame.f_globals) != globals_id
                    or realpath(current_frame.f_code.co_filename) != path
                    or tuple(current_frame.f_code.co_freevars)
                    != tuple(name for name, _value in bindings)
                    or any(
                        current_frame.f_locals.get(name) is not value
                        for name, value in bindings
                    )
                ):
                    valid = False
                    break
                current_frame = current_frame.f_back
            if not valid:
                raise AcceptedRiskPowerCalibrationError(
                    "power-calibration terminal mint is persistence-private"
                )
            calibration_input = require_accepted_risk_power_calibration_input(
                calibration_input
            )
            record = {
                "schema": "arv2-power-calibration-qc-terminal-receipt-v1",
                "plan_id": _safe(plan_id, "calibration plan id"),
                "plan_sha256": _sha(plan_sha256, "calibration plan hash"),
                "input_id": calibration_input.input_id,
                "input_sha256": calibration_input.input_sha256,
                "project_id": _safe(project_id, "calibration project id"),
                "backtest_id": _safe(backtest_id, "calibration backtest id"),
                "terminal_status": "Completed.",
                "output_manifest_key": _safe(
                    output_manifest_key, "calibration output manifest key"
                ),
            }
            record_bytes = canonical_json_bytes(record)
            digest = hashlib.sha256(record_bytes).hexdigest()
            value = object.__new__(PowerCalibrationQcTerminalReceipt)
            for name, item in {
                "terminal_id": f"arv2-power-calibration-terminal-{digest[:24]}",
                "terminal_sha256": digest,
                **{key: record[key] for key in record if key != "schema"},
            }.items():
                object.__setattr__(value, name, item)
            register_terminal(
                value,
                calibration_input,
                record_bytes,
            )
            return require_power_calibration_qc_terminal_receipt(value)

        register_callers = (*register_callers, (
            "terminal", mint.__code__, id(mint.__globals__), bridge_module_path,
        ))
        # The claim is a one-time import handshake.  Removing the module
        # address after the exact adapter has claimed it prevents a later
        # caller from even reaching the already-spent authority seam.
        globals().pop("_claim_power_calibration_terminal_minter", None)
        return mint

    def seal_terminal_persistence_chain(
        persistence_function: object,
        public_persistence_function: object,
    ) -> None:
        """Bind terminal minting to the exact public persistence wrapper."""

        nonlocal terminal_persistence_chain
        if terminal_persistence_chain:
            raise AcceptedRiskPowerCalibrationError(
                "power-calibration persistence provenance was already sealed"
            )
        specifications = (
            (persistence_function, "_persist_power_calibration_output_impl"),
            (
                public_persistence_function,
                "persist_power_calibration_output",
            ),
        )
        sealed = ()
        for function, expected_name in specifications:
            if (
                type(function) is not function_type
                or function.__module__ != submission_module_name
                or sys.modules.get(submission_module_name)
                is not terminal_submission_module
                or function.__globals__ is not vars(terminal_submission_module)
                or function.__code__.co_name != expected_name
                or realpath(function.__code__.co_filename)
                != submission_module_path
            ):
                raise AcceptedRiskPowerCalibrationError(
                    "power-calibration persistence provenance changed"
                )
            closure = function.__closure__ or ()
            if len(closure) != len(function.__code__.co_freevars):
                raise AcceptedRiskPowerCalibrationError(
                    "power-calibration persistence closure changed"
                )
            sealed = (*sealed, (
                function.__code__,
                id(function.__globals__),
                submission_module_path,
                tuple(
                    (name, cell.cell_contents)
                    for name, cell in zip(
                        function.__code__.co_freevars,
                        closure,
                        strict=True,
                    )
                ),
            ))
        terminal_persistence_chain = sealed
        globals().pop("_seal_power_calibration_terminal_persistence", None)

    def reset_private_after_fork() -> None:
        nonlocal lock, records
        records = ()
        lock = rlock_factory()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_private_after_fork)
    return (
        seal_builder_callers,
        register_input,
        current_input,
        register_output,
        current_output,
        register_receipt,
        current_receipt,
        register_successor,
        current_successor,
        claim_terminal_minter,
        seal_terminal_persistence_chain,
        current_terminal,
    )


(
    _seal_power_artifact_builder_callers,
    _power_artifact_register_input,
    _power_artifact_current_input,
    _power_artifact_register_output,
    _power_artifact_current_output,
    _power_artifact_register_receipt,
    _power_artifact_current_receipt,
    _power_artifact_register_successor,
    _power_artifact_current_successor,
    _claim_power_calibration_terminal_minter,
    _seal_power_calibration_terminal_persistence,
    _power_artifact_current_terminal,
) = _make_power_artifact_authority()


def _make_power_launch_authority():
    """Create non-self-mintable census and launch-binding registries.

    Public registries remain visible for bounded retained-state inspection, but
    a replacement is accepted only when it is the exact tuple also retained in
    this closure.  Registration itself is bound lexically to the two public
    builders at module finalization and then removed from the namespace.
    """

    records: tuple[tuple[str, int, tuple[object, ...]], ...] = ()
    register_callers: tuple[tuple[str, object, int, str], ...] = ()
    rlock_factory = threading.RLock
    lock = rlock_factory()
    getpid = os.getpid
    realpath = os.path.realpath
    getframe = sys._getframe
    authority_pid = getpid()
    bridge_module_name = __name__
    bridge_module_path = realpath(__file__)
    function_type = type(lambda: None)

    def public_registry(kind: str) -> dict[int, tuple[object, ...]]:
        registry = (
            _FORMAL_CENSUSES if kind == "census"
            else _POWER_FLOORS if kind == "floor"
            else None
        )
        if type(registry) is not dict:
            raise AcceptedRiskPowerCalibrationError(
                "power launch public registry changed"
            )
        return registry

    def expected_caller(kind: str, frame: object) -> None:
        match = next(
            (item for item in register_callers if item[0] == kind),
            None,
        )
        if (
            match is None
            or getpid() != authority_pid
            or frame.f_code is not match[1]
            or id(frame.f_globals) != match[2]
            or realpath(frame.f_code.co_filename) != match[3]
        ):
            raise AcceptedRiskPowerCalibrationError(
                "power launch registration caller changed"
            )

    def forget(kind: str, identity: int, reference: object) -> None:
        nonlocal records
        with lock:
            matching = next(
                (
                    item for item in records
                    if item[0] == kind and item[1] == identity
                ),
                None,
            )
            if matching is not None and matching[2][0] is reference:
                records = tuple(item for item in records if item is not matching)
                public = public_registry(kind)
                if public.get(identity) is matching[2]:
                    public.pop(identity, None)

    def register(
        kind: str, caller_frame: object, value: object, *lineage: object,
    ) -> None:
        nonlocal records
        expected_caller(kind, caller_frame)
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda ref, category=kind, key=identity: forget(category, key, ref),
        )
        entry = (reference, *lineage, getpid())
        with lock:
            public = public_registry(kind)
            if (
                any(item[0] == kind and item[1] == identity for item in records)
                or identity in public
            ):
                raise AcceptedRiskPowerCalibrationError(
                    "power launch identity was reused"
                )
            records = (*records, (kind, identity, entry))
            public[identity] = entry

    def current(kind: str, value: object) -> tuple[object, ...] | None:
        nonlocal records
        identity = id(value)
        with lock:
            matching = next(
                (
                    item for item in records
                    if item[0] == kind and item[1] == identity
                ),
                None,
            )
            private = None if matching is None else matching[2]
            public_records = public_registry(kind)
            public = public_records.get(identity)
            if (
                private is None
                or public is not private
                or private[0]() is not value
                or private[-1] != getpid()
            ):
                if matching is not None:
                    records = tuple(item for item in records if item is not matching)
                public_records.pop(identity, None)
                return None
            return private

    def seal_builder_callers(
        *, census_builder: object, floor_builder: object,
    ) -> None:
        nonlocal register_callers
        specifications = (
            ("census", census_builder, "_build_authenticated_formal_test_power_census_impl"),
            ("floor", floor_builder, "_build_authenticated_power_floor_binding_impl"),
        )
        if register_callers:
            raise AcceptedRiskPowerCalibrationError(
                "power launch registration provenance was already sealed"
            )
        sealed: tuple[tuple[str, object, int, str], ...] = ()
        for kind, function, expected_name in specifications:
            if (
                type(function) is not function_type
                or function.__module__ != bridge_module_name
                or function.__globals__ is not globals()
                or function.__code__.co_name != expected_name
                or realpath(function.__code__.co_filename) != bridge_module_path
            ):
                raise AcceptedRiskPowerCalibrationError(
                    "power launch registration provenance changed"
                )
            sealed = (*sealed, (
                kind,
                function.__code__,
                id(function.__globals__),
                bridge_module_path,
            ))
        register_callers = sealed

    def register_census(
        value: AuthenticatedFormalTestPowerCensus,
        artifact: object,
        record: dict[str, object],
    ) -> None:
        caller = getframe(1)
        expected_caller("census", caller)
        register(
            "census",
            caller,
            value,
            weakref.ref(artifact),
            canonical_json_bytes(record),
        )

    def current_census(
        value: AuthenticatedFormalTestPowerCensus,
    ) -> tuple[object, ...] | None:
        return current("census", value)

    def register_floor(
        value: AuthenticatedPowerFloorBinding,
        receipt: AcceptedRiskPowerCalibrationReceipt,
        successor: AcceptedRiskStockPowerSuccessor,
        census: AuthenticatedFormalTestPowerCensus,
        formal_power: object,
        power_floor: object,
        record: dict[str, object],
    ) -> None:
        caller = getframe(1)
        expected_caller("floor", caller)
        register(
            "floor",
            caller,
            value,
            weakref.ref(receipt),
            weakref.ref(successor),
            weakref.ref(census),
            weakref.ref(formal_power),
            id(power_floor),
            canonical_json_bytes(record),
        )

    def current_floor(
        value: AuthenticatedPowerFloorBinding,
    ) -> tuple[object, ...] | None:
        return current("floor", value)

    def reset_private_after_fork() -> None:
        nonlocal lock, records
        records = ()
        lock = rlock_factory()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_private_after_fork)
    return (
        seal_builder_callers,
        register_census,
        current_census,
        register_floor,
        current_floor,
    )


(
    _seal_power_launch_builder_callers,
    _power_authority_register_census,
    _power_authority_current_census,
    _power_authority_register_floor,
    _power_authority_current_floor,
) = _make_power_launch_authority()


def _path_fingerprint(path: Path, *, directory: bool = False) -> tuple[int, ...]:
    try:
        observed = os.lstat(path)
    except OSError as exc:
        raise AcceptedRiskPowerCalibrationError("calibration path is unavailable") from exc
    required = stat.S_ISDIR(observed.st_mode) if directory else stat.S_ISREG(observed.st_mode)
    if (
        not required or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o077
        or (not directory and observed.st_nlink != 1)
    ):
        raise AcceptedRiskPowerCalibrationError(
            "calibration path must be owner-only, nonsymlink, and single-link"
        )
    return (
        observed.st_dev, observed.st_ino, observed.st_uid,
        stat.S_IMODE(observed.st_mode), observed.st_nlink, observed.st_size,
        observed.st_mtime_ns, observed.st_ctime_ns,
    )


def _read_private(path: Path, maximum: int) -> tuple[bytes, tuple[int, ...]]:
    if type(path) is not type(Path()) or not path.is_absolute() or ".." in path.parts:
        raise AcceptedRiskPowerCalibrationError("calibration file path is not exact")
    before = _path_fingerprint(path)
    if before[5] > maximum:
        raise AcceptedRiskPowerCalibrationError("calibration file exceeded fixed capacity")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            first = os.read(descriptor, maximum + 1)
            os.lseek(descriptor, 0, os.SEEK_SET)
            second = os.read(descriptor, maximum + 1)
            observed = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise AcceptedRiskPowerCalibrationError("calibration file could not be read") from exc
    after = _path_fingerprint(path)
    if first != second or before != after or observed.st_size != len(first):
        raise AcceptedRiskPowerCalibrationError("calibration file changed while read")
    return first, before


def _write_private(path: Path, payload: bytes) -> tuple[int, ...]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise AcceptedRiskPowerCalibrationError("private write made no progress")
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _path_fingerprint(path)


def _strict_object(payload: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise AcceptedRiskPowerCalibrationError(f"{name} is not JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise AcceptedRiskPowerCalibrationError(f"{name} is not one canonical object")
    return value


def _gzip_rows(rows: Sequence[Mapping[str, object]]) -> tuple[bytes, str, int]:
    raw = b"".join(canonical_json_bytes(dict(row)) for row in rows)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    return compressed, hashlib.sha256(raw).hexdigest(), len(raw)


def _iter_gzip_rows(payload: bytes, descriptor: CalibrationShardDescriptor) -> Iterator[dict[str, Any]]:
    if len(payload) != descriptor.compressed_byte_count or hashlib.sha256(payload).hexdigest() != descriptor.compressed_sha256:
        raise AcceptedRiskPowerCalibrationError("calibration shard compressed identity changed")
    try:
        raw = gzip.decompress(payload)
    except (OSError, EOFError) as exc:
        raise AcceptedRiskPowerCalibrationError("calibration shard is not deterministic gzip") from exc
    if len(raw) != descriptor.uncompressed_byte_count or hashlib.sha256(raw).hexdigest() != descriptor.content_sha256:
        raise AcceptedRiskPowerCalibrationError("calibration shard content identity changed")
    lines = raw.splitlines(keepends=True)
    if len(lines) != descriptor.row_count or any(not line.endswith(b"\n") for line in lines):
        raise AcceptedRiskPowerCalibrationError("calibration shard row census changed")
    for line in lines:
        yield _strict_object(line, "calibration shard row")


def _context() -> Context:
    context = Context(
        prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
        capitals=1, clamp=0,
    )
    for signal in context.traps:
        context.traps[signal] = False
    for signal in (InvalidOperation, DivisionByZero, Overflow):
        context.traps[signal] = True
    context.clear_flags()
    return context


def _stable_sum(values: Iterable[Decimal]) -> Decimal:
    # Decimal.__abs__ obeys the ambient context and can round values wider
    # than that context before the ordering comparison.  The frozen ARV2
    # dialect orders the exact coefficient magnitudes first.
    ordered = sorted(tuple(values), key=lambda item: (item.copy_abs(), item))
    with localcontext(_context()):
        total = Decimal(0)
        for item in ordered:
            total = +(total + item)
        return total


def _hac(values: tuple[Decimal | None, ...]) -> tuple[tuple[int, ...], Decimal]:
    valid = tuple(item for item in values if item is not None)
    if len(valid) < MINIMUM_ABSOLUTE_FLOOR:
        raise AcceptedRiskPowerCalibrationError("fewer than 50 valid beta dates")
    try:
        with localcontext(_context()):
            mean = _stable_sum(valid) / Decimal(len(valid))
            centered = tuple(None if item is None else +(item - mean) for item in values)
            gammas: list[Decimal] = []
            counts: list[int] = []
            for lag in range(HAC_MAX_LAG + 1):
                products = tuple(
                    +(centered[index] * centered[index - lag])
                    for index in range(lag, len(centered))
                    if centered[index] is not None and centered[index - lag] is not None
                )
                if not products:
                    raise AcceptedRiskPowerCalibrationError(
                        "a required exact-axis HAC lag has no valid pair"
                    )
                counts.append(len(products))
                gammas.append(+(_stable_sum(products) / Decimal(len(valid))))
            weighted = tuple(
                +(
                    Decimal(HAC_MAX_LAG + 1 - lag)
                    / Decimal(HAC_MAX_LAG + 1)
                    * gammas[lag]
                )
                for lag in range(1, HAC_MAX_LAG + 1)
            )
            omega = +(gammas[0] + Decimal(2) * _stable_sum(weighted))
    except (InvalidOperation, DivisionByZero, Overflow) as exc:
        raise AcceptedRiskPowerCalibrationError("HAC arithmetic failed") from exc
    if not omega.is_finite() or omega <= 0:
        raise AcceptedRiskPowerCalibrationError("HAC long-run variance is not positive")
    return tuple(counts), omega


def _require_output_directory(path: Path) -> Path:
    if type(path) is not type(Path()) or not path.is_absolute() or ".." in path.parts:
        raise AcceptedRiskPowerCalibrationError("output directory must be an exact absolute Path")
    _path_fingerprint(path, directory=True)
    try:
        names = tuple(path.iterdir())
    except OSError as exc:
        raise AcceptedRiskPowerCalibrationError("output directory cannot be enumerated") from exc
    if names:
        raise AcceptedRiskPowerCalibrationError("output directory must begin empty")
    return path


def _calibration_fold():
    from research.analyst_revisions_v2.production_scoring import ProductionScoringFold

    fold = ProductionScoringFold(
        fold_id=CALIBRATION_FOLD_ID,
        train_start=CALIBRATION_TRAIN_START,
        train_end_exclusive=CALIBRATION_TRAIN_END_EXCLUSIVE,
        validation_start=CALIBRATION_START,
        validation_end_exclusive="2020-01-02",
        test_start="2020-01-31",
        test_end_exclusive="2021-01-04",
    )
    fold.__post_init__()
    if hashlib.sha256(canonical_json_bytes(fold.to_record())).hexdigest() != CALIBRATION_FOLD_HASH:
        # The structural fold hash in the old protocol uses its own canonical
        # projection.  Recheck the semantic boundaries below even when the
        # dialect hash differs; the loaded protocol remains the authority.
        expected = (
            CALIBRATION_FOLD_ID, CALIBRATION_TRAIN_START,
            CALIBRATION_TRAIN_END_EXCLUSIVE, CALIBRATION_START,
            "2020-01-02", "2020-01-31", "2021-01-04",
        )
        observed = (
            fold.fold_id, fold.train_start, fold.train_end_exclusive,
            fold.validation_start, fold.validation_end_exclusive,
            fold.test_start, fold.test_end_exclusive,
        )
        if observed != expected:
            raise AcceptedRiskPowerCalibrationError("H20 calibration fold changed")
    return fold


def _calibration_terminal_slot_id(decision_sha256: str) -> str:
    digest = hashlib.sha256(canonical_json_bytes({
        "domain": "arv2-power-calibration-terminal-slot-v1",
        "decision_sha256": _sha(decision_sha256, "calibration decision hash"),
        "horizon": 20,
    })).hexdigest()
    return "arv2-power-calibration-terminal-slot-" + digest


def _decision_record(
    value: object, terminal_disposition: Mapping[str, object] | None,
) -> dict[str, object]:
    from research.analyst_revisions_v2.production_scoring import FinalDecisionInput, ScoreState

    if type(value) is not FinalDecisionInput:
        raise AcceptedRiskPowerCalibrationError("calibration decision changed type")
    value.__post_init__()
    if len(value.transformed_controls) != 25:
        raise AcceptedRiskPowerCalibrationError("calibration decision lost 25 controls")
    contributions = []
    for item in value.contributions:
        contributions.append(
            {
                "lineage_sha256": item.lineage_sha256,
                "publication_at_utc": item.publication_at_utc,
                "firm_absolute_decayed_weight": _decimal_text(
                    item.firm_absolute_decayed_weight
                ),
            }
        )
    return {
        "security_id": value.security_id,
        "decision_lineage_sha256": value.row_sha256,
        "industry_id": value.industry_id,
        "common_event_component_id": value.common_event_component_id,
        "structural_zero": value.state is ScoreState.STRUCTURAL_ZERO,
        "firm_specific_score": _decimal_text(value.firm_specific_score),
        "continuous_controls": [
            _decimal_text(item) for item in value.transformed_controls[:19]
        ],
        "binary_controls": [int(item) for item in value.transformed_controls[19:]],
        "contributions": contributions,
        "terminal_disposition": (
            None if terminal_disposition is None else dict(terminal_disposition)
        ),
    }


def _calibration_session_record(
    *, session: str, position: int, accepted: Sequence[object],
    refused: Sequence[object], benchmark_security_id: str,
    terminal_by_slot: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    decisions = [
        _decision_record(
            item,
            terminal_by_slot.get(_calibration_terminal_slot_id(item.row_sha256)),
        )
        for item in accepted
    ]
    decisions.sort(key=lambda item: item["security_id"])
    if len(decisions) > MAX_SESSION_SECURITY_COUNT:
        raise AcceptedRiskPowerCalibrationError(
            "one calibration session exceeded the fixed security capacity"
        )
    refusal_hashes = sorted(
        _sha(getattr(item, "refusal_sha256", None), "preoutcome refusal hash")
        for item in refused
    )
    minute_count = sum(
        item["publication_at_utc"] is not None
        for decision in decisions for item in decision["contributions"]
    )
    if minute_count > MAX_SESSION_MINUTE_REQUIREMENTS:
        raise AcceptedRiskPowerCalibrationError(
            "one calibration session exceeded the fixed minute capacity"
        )
    components = {item["common_event_component_id"] for item in decisions}
    disposition = (
        "refused" if refusal_hashes else "missing" if not decisions else "ready"
    )
    exit_session = resolve_nth_session_after(session, 20)
    seed = {
        "schema": INPUT_ROW_SCHEMA,
        "decision_session": session,
        "session_position": position,
        "horizon_sessions": 20,
        "exit_session": exit_session,
        "benchmark_security_id": benchmark_security_id,
        "preoutcome_disposition": disposition,
        "preoutcome_refusal_sha256s": refusal_hashes,
        "connected_component_count": len(components),
        # Only scored decisions can consume an H20 outcome.  Preoutcome
        # refusals are committed separately and never mint terminal slots.
        "security_terminal_count": len(decisions),
        "minute_requirement_count": minute_count,
        "decisions": decisions,
    }
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    return {**seed, "input_session_sha256": digest}


def _require_calibration_terminal_recorder_lineage(
    recorder: object, *, preopen: object, evidence: object,
) -> object:
    """Bind the lifecycle recorder to the scorer's exact reviewed sources."""

    from research.analyst_revisions_v2.preopen_control_acquisition import (
        acquisition_truth_source_binding_records,
    )
    from .formal_terminal_disposition_builder import (
        require_fresh_formal_terminal_disposition_recorder,
    )

    recorder = require_fresh_formal_terminal_disposition_recorder(recorder)
    bridge = recorder.historical_bridge
    from . import physical_production_evidence_acquisition as physical_acquisition
    from . import physical_production_evidence_bridge as physical_bridge_module
    from . import preopen_control_prereview_downloader as prereview

    if (
        type(evidence)
        is physical_acquisition.PhysicalProductionEvidenceAcquisitionReceipt
        and evidence.review_mode
        == physical_acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
    ):
        try:
            physical_receipt = (
                physical_acquisition
                .require_section72_owner_waived_production_evidence_receipt(
                    evidence
                )
            )
            physical_bridge = (
                physical_bridge_module.require_physical_production_evidence_bridge(
                    physical_receipt.bridge
                )
            )
            prereview_archive = prereview.require_preopen_control_prereview_archive(
                preopen
            )
        except (AttributeError, TypeError, ValueError, OSError) as exc:
            raise AcceptedRiskPowerCalibrationError(
                "section-72 calibration lifecycle parents changed"
            ) from exc
        if (
            physical_receipt.preopen_acquisition_receipt is not prereview_archive
            or physical_bridge.preopen_acquisition_receipt is not prereview_archive
            or physical_bridge.terminal_archive is not prereview_archive
            or physical_bridge.historical_bridge is not bridge
            or recorder.historical_bridge_id != bridge.bridge_id
            or recorder.historical_bridge_sha256 != bridge.bridge_sha256
        ):
            raise AcceptedRiskPowerCalibrationError(
                "section-72 calibration lifecycle and scorer sources differ"
            )
        return recorder

    sources = {
        item["kind"]: (item["artifact_id"], item["artifact_sha256"])
        for item in acquisition_truth_source_binding_records(preopen)
    }
    pair = evidence.authority.pair
    if (
        bridge.pair_id != pair.pair_id
        or bridge.pair_sha256 != pair.pair_sha256
        or preopen.input_manifest_sha256 != bridge.closed_input_manifest_sha256
        or preopen.input_source_inventory_sha256
        != bridge.input_shard_inventory_sha256
        or sources.get("accepted_risk_capture")
        != (bridge.accepted_risk_bridge_id, bridge.accepted_risk_bridge_sha256)
        or sources.get("eligible_universe")
        != (
            bridge.discovery_eligible_universe_artifact_id,
            bridge.discovery_eligible_universe_artifact_sha256,
        )
        or sources.get("security_master")
        != (
            bridge.security_master_artifact_id,
            bridge.security_master_artifact_sha256,
        )
        or sources.get("preopen_control")
        != (bridge.physical_candidate_id, bridge.physical_candidate_sha256)
        or preopen.control_sessions[0].decision_session != bridge.first_session
        or preopen.control_sessions[-1].decision_session != bridge.last_session
    ):
        raise AcceptedRiskPowerCalibrationError(
            "calibration lifecycle and scorer sources differ"
        )
    return recorder


def _construct_accepted_risk_power_calibration_input(
    *,
    protocol: PowerCalibrationProtocol,
    source_archive: object,
    production_evidence: object,
    terminal_build: object,
    physical_scoring_stream: object | None,
    benchmark_security_id: str,
    model: object,
    axis: tuple[str, ...],
    paths: tuple[Path, ...],
    descriptors: tuple[CalibrationShardDescriptor, ...],
    resource_counts: Mapping[str, int],
) -> tuple[
    AcceptedRiskPowerCalibrationInput,
    bytes,
    tuple[tuple[int, ...], ...],
]:
    """Construct the common legacy/physical input surface without authority."""

    from .formal_terminal_disposition_builder import (
        formal_terminal_disposition_build_record,
    )

    archive_id = getattr(source_archive, "archive_id", None)
    archive_sha256 = getattr(source_archive, "archive_sha256", None)
    if archive_id is None and archive_sha256 is None:
        archive_id = getattr(source_archive, "capture_id", None)
        archive_sha256 = getattr(source_archive, "capture_sha256", None)
    archive_id = _safe(archive_id, "calibration source archive id")
    archive_sha256 = _sha(
        archive_sha256, "calibration source archive SHA-256"
    )

    physical_record = None
    if physical_scoring_stream is not None:
        try:
            physical_record = physical_scoring_stream.to_record()
        except (AttributeError, TypeError, ValueError) as exc:
            raise AcceptedRiskPowerCalibrationError(
                "physical calibration stream could not be projected"
            ) from exc
    required_counts = {
        "calibration_session_count",
        "scored_row_count",
        "preoutcome_refusal_count",
        "component_instance_count",
        "minute_requirement_count",
    }
    if (
        type(resource_counts) is not dict
        or set(resource_counts) != required_counts
        or any(type(item) is not int or item < 0 for item in resource_counts.values())
        or resource_counts["calibration_session_count"] != len(axis)
        or type(paths) is not tuple
        or type(descriptors) is not tuple
        or len(paths) != len(descriptors)
        or not descriptors
        or len(descriptors) > MAX_INPUT_SHARDS
    ):
        raise AcceptedRiskPowerCalibrationError(
            "calibration input resource census changed"
        )
    seed = {
        "schema": INPUT_SCHEMA,
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.protocol_hash,
        "calibration_fold_id": CALIBRATION_FOLD_ID,
        "calibration_fold_sha256": CALIBRATION_FOLD_HASH,
        "calibration_axis_sha256": CALIBRATION_AXIS_SHA256,
        "calibration_sessions": list(axis),
        "benchmark_security_id": benchmark_security_id,
        "source_archive_id": archive_id,
        "source_archive_sha256": archive_sha256,
        "production_evidence_receipt_id": production_evidence.receipt_id,
        "production_evidence_receipt_sha256": production_evidence.receipt_sha256,
        "terminal_disposition_build": (
            formal_terminal_disposition_build_record(terminal_build)
        ),
        "model": model.to_record(),
        "shards": [item.to_record() for item in descriptors],
        "resource_census": {
            **resource_counts,
            "maximum_session_security_count": MAX_SESSION_SECURITY_COUNT,
            "maximum_session_minute_requirement_count": (
                MAX_SESSION_MINUTE_REQUIREMENTS
            ),
            "maximum_input_shard_byte_count": MAX_INPUT_SHARD_BYTES,
        },
        "market_contract": {
            "stock_return": "20_session_open_to_open_total_return",
            "benchmark_return": "SPY_20_session_open_to_open_total_return",
            "publication_price": (
                "last_tradable_minute_with_bar_end_strictly_before_publication"
            ),
            "terminal_disposition_precedes_numeric_market_bar": True,
            "terminal_payoff_source_available": False,
            "qc_delisting_price_used": False,
            "merger_bankruptcy_successor_payoff_inferred": False,
        },
        "formal_outcome_evaluation": False,
        "result_statistics_read": False,
        "orders_authorized": False,
    }
    if physical_record is not None:
        seed["physical_scoring_stream"] = physical_record
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    manifest = {
        **seed,
        "input_id": f"arv2-accepted-risk-power-input-{digest[:24]}",
        "input_sha256": digest,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise AcceptedRiskPowerCalibrationError(
            "calibration manifest exceeded capacity"
        )
    path_fingerprints = tuple(_path_fingerprint(item) for item in paths)
    value = object.__new__(AcceptedRiskPowerCalibrationInput)
    values: dict[str, object] = {
        "input_id": manifest["input_id"],
        "input_sha256": digest,
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.protocol_hash,
        "source_archive_id": archive_id,
        "source_archive_sha256": archive_sha256,
        "production_evidence_receipt_id": production_evidence.receipt_id,
        "production_evidence_receipt_sha256": production_evidence.receipt_sha256,
        "protocol": protocol,
        "source_archive": source_archive,
        "production_evidence": production_evidence,
        "terminal_build": terminal_build,
        "physical_scoring_stream": physical_scoring_stream,
        "terminal_build_id": terminal_build.build_id,
        "terminal_build_sha256": terminal_build.build_sha256,
        "terminal_package_id": terminal_build.terminal_package.package_id,
        "terminal_package_sha256": terminal_build.terminal_package.package_sha256,
        "terminal_requirement_count": terminal_build.terminal_requirement_count,
        "benchmark_security_id": benchmark_security_id,
        "manifest_bytes": manifest_bytes,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "shard_paths": paths,
        "shard_descriptors": descriptors,
        "path_fingerprints": path_fingerprints,
        **resource_counts,
        "outcome_access": False,
        "quantconnect_access": False,
    }
    if set(values) != {item.name for item in dataclasses.fields(value)}:
        raise AcceptedRiskPowerCalibrationError(
            "calibration input field inventory changed"
        )
    for name, item in values.items():
        object.__setattr__(value, name, item)
    return value, manifest_bytes, path_fingerprints


def _build_accepted_risk_power_calibration_input_impl(
    *, scoring_builder: object, protocol: PowerCalibrationProtocol,
    terminal_recorder: object, benchmark_security_id: str,
    output_directory: Path, _authority_register: object,
) -> AcceptedRiskPowerCalibrationInput:
    """Consume a fresh streamed scorer into the exact H20 calibration input.

    The scorer is deliberately consumed and cannot later be reused as the
    formal six-fold scorer.  Formal construction must open a fresh builder
    over the same authenticated archive/evidence parents.
    """

    from research.analyst_revisions_v2.production_input_pipeline import SignalArm
    from research.analyst_revisions_v2.production_scoring import (
        CONTROL_COLUMNS, FinalDecisionInput, FoldPartition, ScoreState,
    )
    from research.analyst_revisions_v2_qc import formal_streaming_input as stream
    from .formal_terminal_disposition_builder import (
        finalize_formal_terminal_disposition_recording,
        record_formal_terminal_security,
        record_formal_terminal_slot,
        require_formal_terminal_disposition_build,
    )

    try:
        protocol = require_loaded_power_calibration_protocol(protocol)
        stream.require_streamed_production_scoring_builder(scoring_builder)
    except (PowerCalibrationProtocolError, TypeError, ValueError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "calibration parents did not authenticate"
        ) from exc
    if (
        protocol.protocol_id != POWER_PROTOCOL_ID
        or protocol.protocol_hash != POWER_PROTOCOL_HASH
        or tuple(protocol.calibration_session_axis) != calibration_axis()
        or len(CONTROL_COLUMNS) != 25
    ):
        raise AcceptedRiskPowerCalibrationError("calibration protocol changed")
    benchmark_security_id = _safe(benchmark_security_id, "benchmark security id")
    directory = _require_output_directory(output_directory)

    def consume(state: object, observed: dict[str, int]) -> object:
        if state.next_fold_index != 0 or state.active_fold or state.finalized:
            raise AcceptedRiskPowerCalibrationError(
                "calibration requires a fresh scorer"
            )
        try:
            authenticated_terminal_recorder = (
                _require_calibration_terminal_recorder_lineage(
                    terminal_recorder,
                    preopen=state.archive.preopen_acquisition_receipt,
                    evidence=state.evidence,
                )
            )
        except (TypeError, ValueError, OSError) as exc:
            raise AcceptedRiskPowerCalibrationError(
                "calibration lifecycle recorder did not authenticate"
            ) from exc
        fold = _calibration_fold()
        paths: list[Path] = []
        descriptors: list[CalibrationShardDescriptor] = []
        all_records: list[dict[str, object]] = []
        levels: set[str] = set()
        for block in stream._iter_verified_sessions(state, observed):
            partition = fold.partition(block.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            rows, _ = stream._score_session_arm(
                state, fold, partition, block, SignalArm.CURRENT_VINTAGE,
                observed,
            )
            levels.update(
                item.industry_id for item in rows if item.state is ScoreState.ACTIVE
            )
        ordered_levels = tuple(sorted(levels))
        if not ordered_levels:
            raise AcceptedRiskPowerCalibrationError(
                "calibration training has no active industry"
            )
        limits = dict(state.archive.capacity.limits)
        qr = stream._DiskBackedDecimalMgs(
            1 + len(CONTROL_COLUMNS) + len(ordered_levels) - 1, limits
        )
        for block in stream._iter_verified_sessions(state, observed):
            partition = fold.partition(block.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            rows, _ = stream._score_session_arm(
                state, fold, partition, block, SignalArm.CURRENT_VINTAGE,
                observed,
            )
            for row in rows:
                if row.state is not ScoreState.ACTIVE:
                    continue
                design = (
                    Decimal(1), *row.transformed_controls,
                    *(
                        Decimal(row.industry_id == level)
                        for level in ordered_levels[1:]
                    ),
                )
                qr.update(design, row.firm_reliable_score, row.global_reliable_score)
        model = stream._build_streamed_model(
            arm=SignalArm.CURRENT_VINTAGE, fold=fold,
            levels=ordered_levels, qr=qr,
        )
        prepared_by_session: dict[
            str, tuple[tuple[FinalDecisionInput, ...], tuple[object, ...]]
        ] = {}
        axis = calibration_axis()
        positions = {session: index for index, session in enumerate(axis)}
        recorded_securities: set[str] = set()
        for block in stream._iter_verified_sessions(state, observed):
            if block.decision_session not in positions:
                continue
            rows, refusals = stream._score_session_arm(
                state, fold, FoldPartition.VALIDATION, block,
                SignalArm.CURRENT_VINTAGE, observed,
            )
            accepted: list[FinalDecisionInput] = []
            terminal_refusals = list(refusals)
            for row in rows:
                adjusted = stream._apply_streamed_model(model, row)
                if type(adjusted) is FinalDecisionInput:
                    accepted.append(adjusted)
                else:
                    terminal_refusals.append(adjusted)
            accepted_tuple = tuple(
                sorted(accepted, key=lambda item: item.security_id)
            )
            for decision in accepted_tuple:
                if decision.security_id not in recorded_securities:
                    record_formal_terminal_security(
                        authenticated_terminal_recorder,
                        security_id=decision.security_id,
                    )
                    recorded_securities.add(decision.security_id)
                record_formal_terminal_slot(
                    authenticated_terminal_recorder,
                    slot_kind="decision_horizon",
                    slot_id=_calibration_terminal_slot_id(decision.row_sha256),
                    horizon_sessions=20,
                    security_id=decision.security_id,
                    first_session=date.fromisoformat(block.decision_session),
                    last_session=date.fromisoformat(
                        resolve_nth_session_after(block.decision_session, 20)
                    ),
                )
            prepared_by_session[block.decision_session] = (
                accepted_tuple,
                tuple(sorted(
                    terminal_refusals, key=lambda item: item.security_id
                )),
            )
        if set(prepared_by_session) != set(axis):
            raise AcceptedRiskPowerCalibrationError(
                "physical replay omitted a calibration-axis session"
            )
        terminal_build = finalize_formal_terminal_disposition_recording(
            recorder=authenticated_terminal_recorder,
            calculation_as_of_date=date.fromisoformat(
                CALIBRATION_TERMINAL_CALCULATION_AS_OF
            ),
        )
        terminal_build = require_formal_terminal_disposition_build(
            terminal_build
        )
        terminal_by_slot: dict[str, dict[str, object]] = {}
        for item in terminal_build.terminal_package.rows:
            if item.slot_kind != "decision_horizon" or item.horizon_sessions != 20:
                raise AcceptedRiskPowerCalibrationError(
                    "calibration terminal package escaped the H20 slot census"
                )
            terminal_by_slot[item.slot_id] = {
                "disposition": item.disposition,
                "stock_return": (
                    None
                    if item.stock_return is None
                    else _decimal_text(item.stock_return)
                ),
                "reason": item.reason,
                "terminal_lineage_sha256": item.terminal_lineage_sha256,
                "available_at_utc": item.available_at_utc,
            }
        if len(terminal_by_slot) != len(terminal_build.terminal_package.rows):
            raise AcceptedRiskPowerCalibrationError(
                "calibration terminal package repeated a slot"
            )
        all_records = []
        used_terminal_slots: set[str] = set()
        for session in axis:
            accepted, refused = prepared_by_session[session]
            for decision in accepted:
                slot_id = _calibration_terminal_slot_id(decision.row_sha256)
                if slot_id in terminal_by_slot:
                    used_terminal_slots.add(slot_id)
            all_records.append(_calibration_session_record(
                session=session,
                position=positions[session],
                accepted=accepted,
                refused=refused,
                benchmark_security_id=benchmark_security_id,
                terminal_by_slot=terminal_by_slot,
            ))
        if used_terminal_slots != set(terminal_by_slot):
            raise AcceptedRiskPowerCalibrationError(
                "calibration terminal package contains an unbound slot"
            )
        if (
            sum(item["security_terminal_count"] for item in all_records)
            != terminal_build.terminal_requirement_count
        ):
            raise AcceptedRiskPowerCalibrationError(
                "calibration terminal census differs from scored H20 decisions"
            )
        for offset in range(0, len(all_records), SHARD_SESSION_WIDTH):
            rows = all_records[offset : offset + SHARD_SESSION_WIDTH]
            compressed, content_hash, raw_count = _gzip_rows(rows)
            if len(compressed) > MAX_INPUT_SHARD_BYTES:
                raise AcceptedRiskPowerCalibrationError(
                    "one calibration input shard exceeded fixed capacity"
                )
            ordinal = len(descriptors)
            compressed_hash = hashlib.sha256(compressed).hexdigest()
            key = f"{INPUT_PREFIX}content/{compressed_hash}.jsonl.gz"
            path = directory / f"input-{ordinal:03d}-{compressed_hash}.jsonl.gz"
            _write_private(path, compressed)
            paths.append(path)
            descriptors.append(CalibrationShardDescriptor(
                ordinal=ordinal, object_store_key=key,
                content_sha256=content_hash, compressed_sha256=compressed_hash,
                row_count=len(rows), uncompressed_byte_count=raw_count,
                compressed_byte_count=len(compressed),
                first_session=rows[0]["decision_session"],
                last_session=rows[-1]["decision_session"],
            ))
        if not descriptors or len(descriptors) > MAX_INPUT_SHARDS:
            raise AcceptedRiskPowerCalibrationError("calibration input shard count changed")
        resource_counts = {
            "calibration_session_count": len(all_records),
            "scored_row_count": sum(
                len(item["decisions"]) for item in all_records
            ),
            "preoutcome_refusal_count": sum(
                len(item["preoutcome_refusal_sha256s"])
                for item in all_records
            ),
            "component_instance_count": sum(
                item["connected_component_count"] for item in all_records
            ),
            "minute_requirement_count": sum(
                item["minute_requirement_count"] for item in all_records
            ),
        }
        value, manifest_bytes, path_fingerprints = (
            _construct_accepted_risk_power_calibration_input(
                protocol=protocol,
                source_archive=state.archive,
                production_evidence=state.evidence,
                terminal_build=terminal_build,
                physical_scoring_stream=None,
                benchmark_security_id=benchmark_security_id,
                model=model,
                axis=axis,
                paths=tuple(paths),
                descriptors=tuple(descriptors),
                resource_counts=resource_counts,
            )
        )
        _authority_register(
            value,
            protocol,
            state.archive,
            state.evidence,
            terminal_build,
            None,
            manifest_bytes,
            path_fingerprints,
        )
        return require_accepted_risk_power_calibration_input(value)

    try:
        return stream._run_accepted_risk_power_calibration_stream(
            scoring_builder, consume
        )
    except AcceptedRiskPowerCalibrationError:
        raise
    except (TypeError, ValueError, OSError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "calibration stream could not be consumed"
        ) from exc


def _build_physical_accepted_risk_power_calibration_input_impl(
    *,
    scoring_builder: object,
    accepted_risk_binding: object,
    protocol: PowerCalibrationProtocol,
    terminal_recorder: object,
    benchmark_security_id: str,
    output_directory: Path,
    _authority_register: object,
    _physical_operations: tuple[object, object, object],
) -> AcceptedRiskPowerCalibrationInput:
    """Compose H20 calibration input from the reviewed physical scorer."""

    from .formal_terminal_disposition_builder import (
        finalize_formal_terminal_disposition_recording,
        record_formal_terminal_security,
        record_formal_terminal_slot,
        require_formal_terminal_disposition_build,
    )

    context_fn, run_stream, require_stream = _physical_operations
    try:
        protocol = require_loaded_power_calibration_protocol(protocol)
        context = context_fn(
            scoring_builder,
            accepted_risk_binding=accepted_risk_binding,
        )
    except (PowerCalibrationProtocolError, TypeError, ValueError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "physical calibration parents did not authenticate"
        ) from exc
    axis = calibration_axis()
    if (
        protocol.protocol_id != POWER_PROTOCOL_ID
        or protocol.protocol_hash != POWER_PROTOCOL_HASH
        or tuple(protocol.calibration_session_axis) != axis
        or context.accepted_risk_binding is not accepted_risk_binding
        or context.next_fold_index != 0
        or context.active_fold
        or context.finalized
    ):
        raise AcceptedRiskPowerCalibrationError(
            "physical calibration protocol or context changed"
        )
    benchmark_security_id = _safe(
        benchmark_security_id, "benchmark security id"
    )
    directory = _require_output_directory(output_directory)
    evidence = context.capacity.production_evidence_receipt
    try:
        authenticated_terminal_recorder = (
            _require_calibration_terminal_recorder_lineage(
                terminal_recorder,
                preopen=context.preopen_acquisition_receipt,
                evidence=evidence,
            )
        )
    except (TypeError, ValueError, OSError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "physical calibration lifecycle recorder did not authenticate"
        ) from exc

    preliminary_paths: list[Path] = []
    preliminary_descriptors: list[CalibrationShardDescriptor] = []
    final_paths: list[Path] = []
    final_descriptors: list[CalibrationShardDescriptor] = []
    pending_rows: list[dict[str, object]] = []
    recorded_securities: set[str] = set()
    resource_counts = {
        "calibration_session_count": 0,
        "scored_row_count": 0,
        "preoutcome_refusal_count": 0,
        "component_instance_count": 0,
        "minute_requirement_count": 0,
    }
    succeeded = False

    def flush_preliminary() -> None:
        if not pending_rows:
            return
        compressed, content_hash, raw_count = _gzip_rows(pending_rows)
        if len(compressed) > MAX_INPUT_SHARD_BYTES:
            raise AcceptedRiskPowerCalibrationError(
                "one preliminary physical calibration shard exceeded capacity"
            )
        ordinal = len(preliminary_descriptors)
        compressed_hash = hashlib.sha256(compressed).hexdigest()
        path = directory / (
            f"preliminary-{ordinal:03d}-{compressed_hash}.jsonl.gz"
        )
        _write_private(path, compressed)
        preliminary_paths.append(path)
        preliminary_descriptors.append(CalibrationShardDescriptor(
            ordinal=ordinal,
            object_store_key="preliminary-only",
            content_sha256=content_hash,
            compressed_sha256=compressed_hash,
            row_count=len(pending_rows),
            uncompressed_byte_count=raw_count,
            compressed_byte_count=len(compressed),
            first_session=pending_rows[0]["decision_session"],
            last_session=pending_rows[-1]["decision_session"],
        ))
        pending_rows.clear()

    def consume(block: object) -> None:
        position = resource_counts["calibration_session_count"]
        if (
            position >= len(axis)
            or getattr(block, "decision_session", None) != axis[position]
            or getattr(block, "session_position", None) != position
            or type(getattr(block, "accepted", None)) is not tuple
            or type(getattr(block, "refused", None)) is not tuple
        ):
            raise AcceptedRiskPowerCalibrationError(
                "physical calibration callback block changed"
            )
        accepted = block.accepted
        refused = block.refused
        for decision in accepted:
            if decision.security_id not in recorded_securities:
                record_formal_terminal_security(
                    authenticated_terminal_recorder,
                    security_id=decision.security_id,
                )
                recorded_securities.add(decision.security_id)
            record_formal_terminal_slot(
                authenticated_terminal_recorder,
                slot_kind="decision_horizon",
                slot_id=_calibration_terminal_slot_id(decision.row_sha256),
                horizon_sessions=20,
                security_id=decision.security_id,
                first_session=date.fromisoformat(block.decision_session),
                last_session=date.fromisoformat(
                    resolve_nth_session_after(block.decision_session, 20)
                ),
            )
        record = _calibration_session_record(
            session=block.decision_session,
            position=position,
            accepted=accepted,
            refused=refused,
            benchmark_security_id=benchmark_security_id,
            terminal_by_slot={},
        )
        pending_rows.append(record)
        resource_counts["calibration_session_count"] += 1
        resource_counts["scored_row_count"] += len(record["decisions"])
        resource_counts["preoutcome_refusal_count"] += len(
            record["preoutcome_refusal_sha256s"]
        )
        resource_counts["component_instance_count"] += record[
            "connected_component_count"
        ]
        resource_counts["minute_requirement_count"] += record[
            "minute_requirement_count"
        ]
        if (
            len(pending_rows) == SHARD_SESSION_WIDTH
            or position + 1 == len(axis)
        ):
            flush_preliminary()

    try:
        physical_stream = run_stream(
            scoring_builder,
            accepted_risk_binding=accepted_risk_binding,
            calibration_fold=_calibration_fold(),
            calibration_fold_sha256=CALIBRATION_FOLD_HASH,
            calibration_sessions=axis,
            calibration_axis_sha256=CALIBRATION_AXIS_SHA256,
            consumer=consume,
        )
        physical_stream = require_stream(physical_stream)
        if (
            resource_counts["calibration_session_count"] != len(axis)
            or physical_stream.calibration_session_count != len(axis)
            or physical_stream.accepted_decision_count
            != resource_counts["scored_row_count"]
            or physical_stream.preoutcome_refusal_count
            != resource_counts["preoutcome_refusal_count"]
            or len(preliminary_paths) != len(preliminary_descriptors)
            or len(preliminary_paths) > MAX_INPUT_SHARDS
        ):
            raise AcceptedRiskPowerCalibrationError(
                "physical calibration stream and preliminary census differ"
            )
        terminal_build = finalize_formal_terminal_disposition_recording(
            recorder=authenticated_terminal_recorder,
            calculation_as_of_date=date.fromisoformat(
                CALIBRATION_TERMINAL_CALCULATION_AS_OF
            ),
        )
        terminal_build = require_formal_terminal_disposition_build(
            terminal_build
        )
        terminal_by_slot: dict[str, dict[str, object]] = {}
        for item in terminal_build.terminal_package.rows:
            if item.slot_kind != "decision_horizon" or item.horizon_sessions != 20:
                raise AcceptedRiskPowerCalibrationError(
                    "physical calibration terminal package escaped H20"
                )
            terminal_by_slot[item.slot_id] = {
                "disposition": item.disposition,
                "stock_return": (
                    None
                    if item.stock_return is None
                    else _decimal_text(item.stock_return)
                ),
                "reason": item.reason,
                "terminal_lineage_sha256": item.terminal_lineage_sha256,
                "available_at_utc": item.available_at_utc,
            }
        if len(terminal_by_slot) != len(terminal_build.terminal_package.rows):
            raise AcceptedRiskPowerCalibrationError(
                "physical calibration terminal package repeated a slot"
            )
        used_terminal_slots: set[str] = set()
        output_security_terminal_count = 0
        expected_session_position = 0
        for preliminary_path, preliminary_descriptor in zip(
            preliminary_paths, preliminary_descriptors, strict=True
        ):
            payload, _fingerprint = _read_private(
                preliminary_path, MAX_INPUT_SHARD_BYTES
            )
            rows = list(_iter_gzip_rows(payload, preliminary_descriptor))
            finalized_rows: list[dict[str, object]] = []
            for row in rows:
                if (
                    row.get("decision_session") != axis[expected_session_position]
                    or row.get("session_position") != expected_session_position
                    or type(row.get("decisions")) is not list
                ):
                    raise AcceptedRiskPowerCalibrationError(
                        "preliminary physical calibration session changed"
                    )
                seed = dict(row)
                seed.pop("input_session_sha256", None)
                finalized_decisions: list[dict[str, object]] = []
                for raw_decision in row["decisions"]:
                    if type(raw_decision) is not dict:
                        raise AcceptedRiskPowerCalibrationError(
                            "preliminary physical calibration decision changed"
                        )
                    decision = dict(raw_decision)
                    slot_id = _calibration_terminal_slot_id(
                        decision.get("decision_lineage_sha256")
                    )
                    disposition = terminal_by_slot.get(slot_id)
                    if disposition is not None:
                        used_terminal_slots.add(slot_id)
                    decision["terminal_disposition"] = disposition
                    finalized_decisions.append(decision)
                seed["decisions"] = finalized_decisions
                digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
                finalized_rows.append(
                    {**seed, "input_session_sha256": digest}
                )
                output_security_terminal_count += seed["security_terminal_count"]
                expected_session_position += 1
            compressed, content_hash, raw_count = _gzip_rows(finalized_rows)
            if len(compressed) > MAX_INPUT_SHARD_BYTES:
                raise AcceptedRiskPowerCalibrationError(
                    "one physical calibration input shard exceeded capacity"
                )
            ordinal = len(final_descriptors)
            compressed_hash = hashlib.sha256(compressed).hexdigest()
            key = f"{INPUT_PREFIX}content/{compressed_hash}.jsonl.gz"
            path = directory / f"input-{ordinal:03d}-{compressed_hash}.jsonl.gz"
            _write_private(path, compressed)
            final_paths.append(path)
            final_descriptors.append(CalibrationShardDescriptor(
                ordinal=ordinal,
                object_store_key=key,
                content_sha256=content_hash,
                compressed_sha256=compressed_hash,
                row_count=len(finalized_rows),
                uncompressed_byte_count=raw_count,
                compressed_byte_count=len(compressed),
                first_session=finalized_rows[0]["decision_session"],
                last_session=finalized_rows[-1]["decision_session"],
            ))
            preliminary_path.unlink()
        if (
            expected_session_position != len(axis)
            or used_terminal_slots != set(terminal_by_slot)
            or output_security_terminal_count
            != terminal_build.terminal_requirement_count
        ):
            raise AcceptedRiskPowerCalibrationError(
                "physical calibration terminal census is not exact"
            )
        value, manifest_bytes, path_fingerprints = (
            _construct_accepted_risk_power_calibration_input(
                protocol=protocol,
                source_archive=physical_stream.terminal_archive,
                production_evidence=(
                    physical_stream.capacity.production_evidence_receipt
                ),
                terminal_build=terminal_build,
                physical_scoring_stream=physical_stream,
                benchmark_security_id=benchmark_security_id,
                model=physical_stream.model,
                axis=axis,
                paths=tuple(final_paths),
                descriptors=tuple(final_descriptors),
                resource_counts=resource_counts,
            )
        )
        _authority_register(
            value,
            protocol,
            physical_stream.terminal_archive,
            physical_stream.capacity.production_evidence_receipt,
            terminal_build,
            physical_stream,
            manifest_bytes,
            path_fingerprints,
        )
        value = require_accepted_risk_power_calibration_input(value)
        succeeded = True
        return value
    except AcceptedRiskPowerCalibrationError:
        raise
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "physical calibration stream could not be consumed"
        ) from exc
    finally:
        for path in (*preliminary_paths, *final_paths):
            try:
                if path.exists() and (path in preliminary_paths or not succeeded):
                    path.unlink()
            except OSError:
                pass


def _require_accepted_risk_power_calibration_input_impl(
    value: AcceptedRiskPowerCalibrationInput,
    *, _authority_current: object, _resolve_physical: object,
) -> AcceptedRiskPowerCalibrationInput:
    from research.analyst_revisions_v2_qc import formal_streaming_input as stream
    from research.analyst_revisions_v2.production_evidence_acquisition import (
        require_production_evidence_acquisition_receipt,
    )
    from .formal_terminal_disposition_builder import (
        require_formal_terminal_disposition_build,
    )

    if type(value) is not AcceptedRiskPowerCalibrationInput:
        raise AcceptedRiskPowerCalibrationError("calibration input changed type")
    registered = _authority_current(value)
    if registered is None or registered[0]() is not value:
        raise AcceptedRiskPowerCalibrationError("calibration input lacks builder authority")
    protocol, archive, evidence, terminal_build = (
        registered[index]() for index in (1, 2, 3, 4)
    )
    physical_reference = registered[5]
    physical_stream = (
        None if physical_reference is None else physical_reference()
    )
    if any(
        item is None for item in (protocol, archive, evidence, terminal_build)
    ) or (physical_reference is not None and physical_stream is None):
        raise AcceptedRiskPowerCalibrationError("calibration input parent was released")
    try:
        require_loaded_power_calibration_protocol(protocol)
        if physical_stream is not None:
            if _resolve_physical()[2](physical_stream) is not physical_stream:
                raise AcceptedRiskPowerCalibrationError(
                    "physical calibration stream verifier changed identity"
                )
        else:
            if type(archive) is stream.PhysicalPreopenTerminalArchive:
                stream.require_physical_preopen_terminal_archive(archive)
            elif type(archive) is stream.PhysicalProductionEvidenceTerminalArchive:
                stream.require_physical_production_evidence_terminal_archive(archive)
            else:
                raise AcceptedRiskPowerCalibrationError(
                    "calibration archive type changed"
                )
            require_production_evidence_acquisition_receipt(evidence)
        require_formal_terminal_disposition_build(terminal_build)
    except (TypeError, ValueError) as exc:
        raise AcceptedRiskPowerCalibrationError("calibration input parent changed") from exc
    try:
        manifest = _strict_object(value.manifest_bytes, "calibration input manifest")
        physical_record = (
            None if physical_stream is None else physical_stream.to_record()
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "calibration input physical lineage changed"
        ) from exc
    if (
        value.protocol is not protocol
        or value.source_archive is not archive
        or value.production_evidence is not evidence
        or value.terminal_build is not terminal_build
        or value.physical_scoring_stream is not physical_stream
        or (
            physical_stream is not None
            and (
                physical_stream.terminal_archive is not archive
                or physical_stream.capacity.production_evidence_receipt
                is not evidence
            )
        )
        or manifest.get("physical_scoring_stream") != physical_record
        or (
            physical_stream is None
            and "physical_scoring_stream" in manifest
        )
        or value.terminal_build_id != terminal_build.build_id
        or value.terminal_build_sha256 != terminal_build.build_sha256
        or value.terminal_package_id != terminal_build.terminal_package.package_id
        or value.terminal_package_sha256
        != terminal_build.terminal_package.package_sha256
        or value.terminal_requirement_count
        != terminal_build.terminal_requirement_count
        or value.manifest_bytes != registered[6]
        or value.path_fingerprints != registered[7]
        or registered[8] != os.getpid()
        or value.manifest_sha256 != hashlib.sha256(value.manifest_bytes).hexdigest()
        or value.calibration_session_count != CALIBRATION_SESSION_COUNT
        or value.outcome_access is not False
        or value.quantconnect_access is not False
        or len(value.shard_paths) != len(value.shard_descriptors)
    ):
        raise AcceptedRiskPowerCalibrationError("calibration input identity changed")
    for path, expected in zip(value.shard_paths, value.path_fingerprints, strict=True):
        if _path_fingerprint(path) != expected:
            raise AcceptedRiskPowerCalibrationError("calibration input shard changed")
    return value


def iter_accepted_risk_power_calibration_input_rows(
    value: AcceptedRiskPowerCalibrationInput,
) -> Iterator[dict[str, Any]]:
    value = require_accepted_risk_power_calibration_input(value)
    expected_axis = iter(calibration_axis())
    observed = 0
    for path, descriptor in zip(
        value.shard_paths, value.shard_descriptors, strict=True
    ):
        payload, fingerprint = _read_private(path, MAX_INPUT_SHARD_BYTES)
        if fingerprint != value.path_fingerprints[descriptor.ordinal]:
            raise AcceptedRiskPowerCalibrationError("calibration input shard changed")
        for row in _iter_gzip_rows(payload, descriptor):
            if row.get("schema") != INPUT_ROW_SCHEMA:
                raise AcceptedRiskPowerCalibrationError("calibration input row schema changed")
            try:
                expected_session = next(expected_axis)
            except StopIteration as exc:
                raise AcceptedRiskPowerCalibrationError("calibration input has extra rows") from exc
            if row.get("decision_session") != expected_session:
                raise AcceptedRiskPowerCalibrationError("calibration input axis reordered")
            seed = dict(row)
            supplied = seed.pop("input_session_sha256", None)
            if supplied != hashlib.sha256(canonical_json_bytes(seed)).hexdigest():
                raise AcceptedRiskPowerCalibrationError("calibration input row identity changed")
            observed += 1
            yield row
    if observed != CALIBRATION_SESSION_COUNT:
        raise AcceptedRiskPowerCalibrationError("calibration input axis is incomplete")


def _require_power_calibration_qc_terminal_receipt_impl(
    value: PowerCalibrationQcTerminalReceipt,
    *, _authority_current: object,
) -> PowerCalibrationQcTerminalReceipt:
    if type(value) is not PowerCalibrationQcTerminalReceipt:
        raise AcceptedRiskPowerCalibrationError("QC terminal receipt changed type")
    registered = _authority_current(value)
    if registered is None:
        raise AcceptedRiskPowerCalibrationError("QC terminal receipt changed")
    calibration_input = registered[1]()
    if calibration_input is None:
        raise AcceptedRiskPowerCalibrationError("QC terminal input was released")
    require_accepted_risk_power_calibration_input(calibration_input)
    record = {
        "schema": "arv2-power-calibration-qc-terminal-receipt-v1",
        "plan_id": value.plan_id,
        "plan_sha256": value.plan_sha256,
        "input_id": value.input_id,
        "input_sha256": value.input_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "terminal_status": value.terminal_status,
        "output_manifest_key": value.output_manifest_key,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    if (
        registered[2] != canonical_json_bytes(record)
        or registered[3] != os.getpid()
        or value.terminal_id != f"arv2-power-calibration-terminal-{digest[:24]}"
        or value.terminal_sha256 != digest
        or value.terminal_status != "Completed."
        or value.input_id != calibration_input.input_id
        or value.input_sha256 != calibration_input.input_sha256
    ):
        raise AcceptedRiskPowerCalibrationError("QC terminal receipt changed")
    return value


def _descriptor_from_record(value: object, *, maximum_bytes: int) -> CalibrationShardDescriptor:
    if type(value) is not dict or set(value) != {
        "ordinal", "object_store_key", "content_sha256", "compressed_sha256",
        "row_count", "uncompressed_byte_count", "compressed_byte_count",
        "first_session", "last_session",
    }:
        raise AcceptedRiskPowerCalibrationError("calibration shard descriptor changed")
    result = CalibrationShardDescriptor(
        ordinal=_count(value["ordinal"], "shard ordinal"),
        object_store_key=_safe(value["object_store_key"], "shard key"),
        content_sha256=_sha(value["content_sha256"], "shard content hash"),
        compressed_sha256=_sha(value["compressed_sha256"], "shard compressed hash"),
        row_count=_count(value["row_count"], "shard row count", zero=False),
        uncompressed_byte_count=_count(
            value["uncompressed_byte_count"], "shard raw bytes", zero=False
        ),
        compressed_byte_count=_count(
            value["compressed_byte_count"], "shard compressed bytes", zero=False
        ),
        first_session=_safe(value["first_session"], "first session"),
        last_session=_safe(value["last_session"], "last session"),
    )
    if result.compressed_byte_count > maximum_bytes:
        raise AcceptedRiskPowerCalibrationError("calibration output shard exceeded capacity")
    return result


def _beta_record(value: object) -> CalibrationBetaRecord:
    expected = {
        "schema", "decision_session", "state", "beta_value",
        "connected_component_count", "reason", "input_session_sha256",
        "output_lineage_sha256",
    }
    if type(value) is not dict or set(value) != expected or value.get("schema") != OUTPUT_ROW_SCHEMA:
        raise AcceptedRiskPowerCalibrationError("calibration beta row fields changed")
    try:
        state = CalibrationBetaState(value["state"])
    except (TypeError, ValueError) as exc:
        raise AcceptedRiskPowerCalibrationError("calibration beta state changed") from exc
    beta = None if value["beta_value"] is None else _decimal(
        value["beta_value"], "calibration beta"
    )
    reason = value["reason"]
    if (
        (state is CalibrationBetaState.VALID) != (beta is not None)
        or (state is CalibrationBetaState.VALID) == (reason is not None)
        or (reason is not None and type(reason) is not str)
    ):
        raise AcceptedRiskPowerCalibrationError("calibration beta terminal is inconsistent")
    semantic = dict(value)
    supplied = semantic.pop("output_lineage_sha256")
    if supplied != hashlib.sha256(canonical_json_bytes(semantic)).hexdigest():
        raise AcceptedRiskPowerCalibrationError("calibration beta lineage changed")
    return CalibrationBetaRecord(
        decision_session=_safe(value["decision_session"], "beta session"),
        state=state, beta_value=beta,
        connected_component_count=_count(
            value["connected_component_count"], "beta component count"
        ),
        reason=reason,
        input_session_sha256=_sha(
            value["input_session_sha256"], "beta input-session hash"
        ),
        output_lineage_sha256=_sha(supplied, "beta output lineage"),
    )


def _load_accepted_risk_power_calibration_output_impl(
    *, calibration_input: AcceptedRiskPowerCalibrationInput,
    terminal_receipt: PowerCalibrationQcTerminalReceipt,
    manifest_path: Path, shard_paths: tuple[Path, ...],
    _authority_register: object,
) -> AcceptedRiskPowerCalibrationOutput:
    """Authenticate a completed calibration's manifest-last local archive."""

    calibration_input = require_accepted_risk_power_calibration_input(calibration_input)
    terminal_receipt = require_power_calibration_qc_terminal_receipt(terminal_receipt)
    if (
        terminal_receipt.input_id != calibration_input.input_id
        or terminal_receipt.input_sha256 != calibration_input.input_sha256
    ):
        raise AcceptedRiskPowerCalibrationError("QC terminal and calibration input differ")
    manifest_payload, manifest_fingerprint = _read_private(
        manifest_path, MAX_MANIFEST_BYTES
    )
    manifest = _strict_object(manifest_payload, "calibration output manifest")
    required = {
        "schema", "output_id", "output_sha256", "input_id", "input_sha256",
        "protocol_id", "protocol_sha256", "calibration_axis_sha256", "shards",
        "census", "formal_outcome_evaluation", "qc_result_statistics_read",
        "orders_placed",
    }
    if type(manifest) is not dict or set(manifest) != required:
        raise AcceptedRiskPowerCalibrationError("calibration output manifest fields changed")
    seed = dict(manifest)
    output_id = seed.pop("output_id")
    output_sha = seed.pop("output_sha256")
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    if (
        manifest["schema"] != OUTPUT_MANIFEST_SCHEMA
        or output_sha != digest
        or output_id != f"arv2-accepted-risk-power-output-{digest[:24]}"
        or manifest["input_id"] != calibration_input.input_id
        or manifest["input_sha256"] != calibration_input.input_sha256
        or manifest["protocol_id"] != POWER_PROTOCOL_ID
        or manifest["protocol_sha256"] != POWER_PROTOCOL_HASH
        or manifest["calibration_axis_sha256"] != CALIBRATION_AXIS_SHA256
        or manifest["formal_outcome_evaluation"] is not False
        or manifest["qc_result_statistics_read"] is not False
        or manifest["orders_placed"] != 0
    ):
        raise AcceptedRiskPowerCalibrationError("calibration output manifest identity changed")
    raw_descriptors = manifest["shards"]
    if type(raw_descriptors) is not list:
        raise AcceptedRiskPowerCalibrationError("calibration output descriptors changed")
    descriptors = tuple(
        _descriptor_from_record(item, maximum_bytes=MAX_OUTPUT_SHARD_BYTES)
        for item in raw_descriptors
    )
    if (
        not descriptors or len(descriptors) > MAX_OUTPUT_SHARDS
        or tuple(item.ordinal for item in descriptors) != tuple(range(len(descriptors)))
        or type(shard_paths) is not tuple or len(shard_paths) != len(descriptors)
    ):
        raise AcceptedRiskPowerCalibrationError("calibration output shard inventory changed")
    input_rows = tuple(iter_accepted_risk_power_calibration_input_rows(calibration_input))
    input_by_session = {item["decision_session"]: item for item in input_rows}
    records: list[CalibrationBetaRecord] = []
    file_fingerprints = [manifest_fingerprint]
    for path, descriptor in zip(shard_paths, descriptors, strict=True):
        payload, fingerprint = _read_private(path, MAX_OUTPUT_SHARD_BYTES)
        file_fingerprints.append(fingerprint)
        for raw in _iter_gzip_rows(payload, descriptor):
            record = _beta_record(raw)
            source = input_by_session.get(record.decision_session)
            if (
                source is None
                or record.input_session_sha256 != source["input_session_sha256"]
                or record.connected_component_count
                != source["connected_component_count"]
            ):
                raise AcceptedRiskPowerCalibrationError(
                    "calibration output does not bind its exact preoutcome session"
                )
            if source["preoutcome_disposition"] == "refused" and record.state is not CalibrationBetaState.REFUSED:
                raise AcceptedRiskPowerCalibrationError("preoutcome refusal was not preserved")
            if source["preoutcome_disposition"] == "missing" and record.state is not CalibrationBetaState.MISSING:
                raise AcceptedRiskPowerCalibrationError("empty preoutcome date was not preserved")
            records.append(record)
    axis = calibration_axis()
    if tuple(item.decision_session for item in records) != axis:
        raise AcceptedRiskPowerCalibrationError("calibration output axis is incomplete or reordered")
    census = manifest["census"]
    observed_census = {
        "session_count": len(records),
        "valid_date_count": sum(item.state is CalibrationBetaState.VALID for item in records),
        "missing_date_count": sum(item.state is CalibrationBetaState.MISSING for item in records),
        "refused_date_count": sum(item.state is CalibrationBetaState.REFUSED for item in records),
        "component_instance_count": sum(item.connected_component_count for item in records),
    }
    if census != observed_census:
        raise AcceptedRiskPowerCalibrationError("calibration output census changed")
    value = object.__new__(AcceptedRiskPowerCalibrationOutput)
    values: dict[str, object] = {
        "output_id": output_id, "output_sha256": output_sha,
        "input_id": calibration_input.input_id,
        "input_sha256": calibration_input.input_sha256,
        "protocol_id": POWER_PROTOCOL_ID, "protocol_sha256": POWER_PROTOCOL_HASH,
        "calibration_input": calibration_input,
        "terminal_receipt": terminal_receipt,
        "records": tuple(records), "manifest_path": manifest_path,
        "shard_paths": shard_paths,
        "file_fingerprints": tuple(file_fingerprints),
        "valid_date_count": observed_census["valid_date_count"],
        "missing_date_count": observed_census["missing_date_count"],
        "refused_date_count": observed_census["refused_date_count"],
        "component_instance_count": observed_census["component_instance_count"],
        "complete_axis": True, "qc_result_statistics_read": False,
        "formal_outcome_evaluation": False,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    fingerprint = (
        output_id, output_sha, id(calibration_input), id(terminal_receipt),
        tuple(item.output_lineage_sha256 for item in records),
        tuple(file_fingerprints),
    )
    _authority_register(value, calibration_input, terminal_receipt, fingerprint)
    return require_accepted_risk_power_calibration_output(value)


def _require_accepted_risk_power_calibration_output_impl(
    value: AcceptedRiskPowerCalibrationOutput,
    *, _authority_current: object,
) -> AcceptedRiskPowerCalibrationOutput:
    if type(value) is not AcceptedRiskPowerCalibrationOutput:
        raise AcceptedRiskPowerCalibrationError("calibration output changed type")
    registered = _authority_current(value)
    if registered is None or registered[0]() is not value:
        raise AcceptedRiskPowerCalibrationError("calibration output lacks loader authority")
    calibration_input, terminal = registered[1](), registered[2]()
    if calibration_input is None or terminal is None:
        raise AcceptedRiskPowerCalibrationError("calibration output parent was released")
    require_accepted_risk_power_calibration_input(calibration_input)
    require_power_calibration_qc_terminal_receipt(terminal)
    current_files = tuple(
        _path_fingerprint(path) for path in (value.manifest_path, *value.shard_paths)
    )
    fingerprint = (
        value.output_id, value.output_sha256, id(calibration_input), id(terminal),
        tuple(item.output_lineage_sha256 for item in value.records), current_files,
    )
    if (
        value.calibration_input is not calibration_input
        or value.terminal_receipt is not terminal
        or fingerprint != registered[3]
        or registered[4] != os.getpid()
        or current_files != value.file_fingerprints
        or value.complete_axis is not True
        or value.qc_result_statistics_read is not False
        or value.formal_outcome_evaluation is not False
    ):
        raise AcceptedRiskPowerCalibrationError("calibration output changed")
    return value


def _receipt_fingerprint(
    value: AcceptedRiskPowerCalibrationReceipt,
) -> tuple[object, ...]:
    return tuple(
        getattr(value, field.name)
        for field in dataclasses.fields(AcceptedRiskPowerCalibrationReceipt)
    )


def _receipt_record(
    value: AcceptedRiskPowerCalibrationReceipt,
) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "protocol_id": value.protocol_id,
        "protocol_hash": value.protocol_hash,
        "manifest_id": value.manifest_id,
        "manifest_content_sha256": value.manifest_content_sha256,
        "valid_beta_date_count": value.valid_beta_date_count,
        "lag_pair_counts_0_through_20": list(value.lag_pair_counts_0_through_20),
        "long_run_variance": _decimal_text(value.long_run_variance),
        "component_count_census_sha256": value.component_count_census_sha256,
        "component_count_census_session_count": (
            value.component_count_census_session_count
        ),
        "q05_components_per_date": value.q05_components_per_date,
        "raw_required_valid_dates": value.raw_required_valid_dates,
        "required_valid_dates": value.required_valid_dates,
        "required_connected_components": value.required_connected_components,
        "fixed_h20_test_session_capacity": value.fixed_h20_test_session_capacity,
        "disposition": value.disposition.value,
        "accepted_risk_policy_id": value.accepted_risk_policy_id,
        "output_id": value.output_id,
        "output_sha256": value.output_sha256,
    }


def _compute_accepted_risk_power_calibration_receipt_impl(
    *, protocol: PowerCalibrationProtocol,
    output: AcceptedRiskPowerCalibrationOutput,
    accepted_risk_policy_id: str, _authority_register: object,
) -> AcceptedRiskPowerCalibrationReceipt:
    """Compute the closed Decimal HAC and frozen provisional power formula."""

    try:
        protocol = require_loaded_power_calibration_protocol(protocol)
        output = require_accepted_risk_power_calibration_output(output)
    except (PowerCalibrationProtocolError, TypeError, ValueError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "power receipt parents did not authenticate"
        ) from exc
    if (
        protocol.protocol_id != output.protocol_id
        or protocol.protocol_hash != output.protocol_sha256
    ):
        raise AcceptedRiskPowerCalibrationError("power protocol and output differ")
    accepted_risk_policy_id = _safe(
        accepted_risk_policy_id, "accepted-risk policy id"
    )
    beta_values = tuple(
        item.beta_value if item.state is CalibrationBetaState.VALID else None
        for item in output.records
    )
    pair_counts, omega = _hac(beta_values)
    components = tuple(
        (item.decision_session, item.connected_component_count)
        for item in output.records
    )
    try:
        provisional = derive_provisional_power_requirement(
            protocol, long_run_variance=omega,
            per_session_component_counts=components,
        )
    except PowerCalibrationProtocolError as exc:
        raise AcceptedRiskPowerCalibrationError(
            "frozen provisional power arithmetic failed"
        ) from exc
    component_digest = hashlib.sha256(
        canonical_json_bytes([[session, count] for session, count in components])
    ).hexdigest()
    record = {
        "schema": RECEIPT_SCHEMA,
        "protocol_id": protocol.protocol_id,
        "protocol_hash": protocol.protocol_hash,
        "manifest_id": output.output_id,
        "manifest_content_sha256": output.output_sha256,
        "valid_beta_date_count": output.valid_date_count,
        "lag_pair_counts_0_through_20": list(pair_counts),
        "long_run_variance": _decimal_text(omega),
        "component_count_census_sha256": component_digest,
        "component_count_census_session_count": CALIBRATION_SESSION_COUNT,
        "q05_components_per_date": provisional.q05_components_per_date,
        "raw_required_valid_dates": provisional.raw_required_valid_dates,
        "required_valid_dates": provisional.required_valid_dates,
        "required_connected_components": provisional.required_connected_components,
        "fixed_h20_test_session_capacity": TEST_SESSION_CAPACITY,
        "disposition": provisional.disposition.value,
        "accepted_risk_policy_id": accepted_risk_policy_id,
        "output_id": output.output_id,
        "output_sha256": output.output_sha256,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(AcceptedRiskPowerCalibrationReceipt)
    values: dict[str, object] = {
        "receipt_id": f"arv2-accepted-risk-power-receipt-{digest[:24]}",
        "receipt_hash": digest,
        "output": output,
        "protocol": protocol,
        "protocol_id": protocol.protocol_id,
        "protocol_hash": protocol.protocol_hash,
        "manifest_id": output.output_id,
        "manifest_content_sha256": output.output_sha256,
        "valid_beta_date_count": output.valid_date_count,
        "lag_pair_counts_0_through_20": pair_counts,
        "long_run_variance": omega,
        "component_count_census_sha256": component_digest,
        "component_count_census_session_count": CALIBRATION_SESSION_COUNT,
        "q05_components_per_date": provisional.q05_components_per_date,
        "raw_required_valid_dates": provisional.raw_required_valid_dates,
        "required_valid_dates": provisional.required_valid_dates,
        "required_connected_components": provisional.required_connected_components,
        "fixed_h20_test_session_capacity": TEST_SESSION_CAPACITY,
        "disposition": provisional.disposition,
        "accepted_risk_policy_id": accepted_risk_policy_id,
        "output_id": output.output_id,
        "output_sha256": output.output_sha256,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    record_bytes = canonical_json_bytes(record)
    if record != _receipt_record(value):
        raise AcceptedRiskPowerCalibrationError(
            "power receipt derivation changed before registration"
        )
    _authority_register(
        value,
        output,
        protocol,
        record_bytes,
        digest,
        _receipt_fingerprint(value),
    )
    return require_accepted_risk_power_calibration_receipt(value)


def _require_accepted_risk_power_calibration_receipt_impl(
    value: AcceptedRiskPowerCalibrationReceipt,
    *, _authority_current: object,
) -> AcceptedRiskPowerCalibrationReceipt:
    if type(value) is not AcceptedRiskPowerCalibrationReceipt:
        raise AcceptedRiskPowerCalibrationError("power receipt changed type")
    registered = _authority_current(value)
    if registered is None:
        raise AcceptedRiskPowerCalibrationError("power receipt lacks worker authority")
    output, protocol = registered[1](), registered[2]()
    if output is None or protocol is None:
        raise AcceptedRiskPowerCalibrationError("power receipt parent was released")
    require_accepted_risk_power_calibration_output(output)
    try:
        require_loaded_power_calibration_protocol(protocol)
    except PowerCalibrationProtocolError as exc:
        raise AcceptedRiskPowerCalibrationError("power receipt protocol changed") from exc
    if (
        value.output is not output
        or value.protocol is not protocol
        or canonical_json_bytes(_receipt_record(value)) != registered[3]
        or value.receipt_hash != registered[4]
        or _receipt_fingerprint(value) != registered[5]
        or registered[6] != os.getpid()
        or value.output_id != output.output_id
        or value.output_sha256 != output.output_sha256
        or value.valid_beta_date_count != output.valid_date_count
        or value.component_count_census_session_count != CALIBRATION_SESSION_COUNT
        or value.fixed_h20_test_session_capacity != TEST_SESSION_CAPACITY
        or type(value.disposition) is not ProvisionalPowerDisposition
    ):
        raise AcceptedRiskPowerCalibrationError("power receipt changed")
    return value


def _build_accepted_risk_stock_power_successor_impl(
    receipt: AcceptedRiskPowerCalibrationReceipt,
    *, _authority_register: object,
) -> AcceptedRiskStockPowerSuccessor:
    """Bind the accepted-risk receipt without editing frozen stock-v3 bytes."""

    receipt = require_accepted_risk_power_calibration_receipt(receipt)
    record = {
        "schema": SUCCESSOR_SCHEMA,
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.receipt_hash,
        "required_valid_dates": receipt.required_valid_dates,
        "required_connected_components": receipt.required_connected_components,
        "disposition": receipt.disposition.value,
        "authority": (
            "power_floor_only_no_source_outcome_qc_result_deployment_order_or_trading"
        ),
        "capabilities": {
            "outcome_access": False, "qc_action": False,
            "deployment": False, "orders": False,
        },
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(AcceptedRiskStockPowerSuccessor)
    for name, item in {
        "successor_id": f"arv2-accepted-risk-stock-power-{digest[:24]}",
        "successor_sha256": digest,
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.receipt_hash,
        "required_valid_dates": receipt.required_valid_dates,
        "required_connected_components": receipt.required_connected_components,
        "disposition": receipt.disposition.value,
        "outcome_access": False, "qc_action": False,
        "deployment": False, "orders": False,
    }.items():
        object.__setattr__(value, name, item)
    _authority_register(value, receipt, canonical_json_bytes(record))
    return require_accepted_risk_stock_power_successor(value)


def _require_accepted_risk_stock_power_successor_impl(
    value: AcceptedRiskStockPowerSuccessor,
    *, _authority_current: object,
) -> AcceptedRiskStockPowerSuccessor:
    if type(value) is not AcceptedRiskStockPowerSuccessor:
        raise AcceptedRiskPowerCalibrationError("stock-power successor changed type")
    registered = _authority_current(value)
    if registered is None:
        raise AcceptedRiskPowerCalibrationError("stock-power successor lacks authority")
    receipt = registered[1]()
    if receipt is None:
        raise AcceptedRiskPowerCalibrationError("stock-power receipt was released")
    require_accepted_risk_power_calibration_receipt(receipt)
    record = {
        "schema": SUCCESSOR_SCHEMA,
        "receipt_id": value.receipt_id,
        "receipt_sha256": value.receipt_sha256,
        "required_valid_dates": value.required_valid_dates,
        "required_connected_components": value.required_connected_components,
        "disposition": value.disposition,
        "authority": (
            "power_floor_only_no_source_outcome_qc_result_deployment_order_or_trading"
        ),
        "capabilities": {
            "outcome_access": value.outcome_access, "qc_action": value.qc_action,
            "deployment": value.deployment, "orders": value.orders,
        },
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    if (
        canonical_json_bytes(record) != registered[2]
        or registered[3] != os.getpid()
        or value.successor_id != f"arv2-accepted-risk-stock-power-{digest[:24]}"
        or value.successor_sha256 != digest
        or value.receipt_id != receipt.receipt_id
        or value.receipt_sha256 != receipt.receipt_hash
        or any((value.outcome_access, value.qc_action, value.deployment, value.orders))
    ):
        raise AcceptedRiskPowerCalibrationError("stock-power successor changed")
    return value


def _build_authenticated_formal_test_power_census_impl(
    scoring_builder: object,
    *,
    _authority_register: object,
) -> AuthenticatedFormalTestPowerCensus:
    """Consume a fresh six-fold scorer into an outcome-free H20 census."""

    from research.analyst_revisions_v2_qc import formal_streaming_input as stream
    from research.analyst_revisions_v2.production_scoring import (
        build_formal_production_scoring_fold,
        formal_horizon_fold_boundary,
    )
    from research.analyst_revisions_v2_qc.formal_input_bundle import (
        CENSORED_VIEW_LABEL,
        CURRENT_VIEW_LABEL,
        FORMAL_PRIMARY_FOLD_IDS,
        FormalInputBundleError,
        _is_preoutcome_candidate_date,
    )

    try:
        stream.require_streamed_production_scoring_builder(scoring_builder)
    except (TypeError, ValueError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "formal census scorer did not authenticate"
        ) from exc
    state = stream._state(scoring_builder)
    if state.next_fold_index != 0 or state.active_fold or state.finalized:
        raise AcceptedRiskPowerCalibrationError("formal census requires a fresh scorer")

    def view_disposition(
        accepted: tuple[object, ...], refused: tuple[object, ...],
    ) -> tuple[bool, bool, str, tuple[str, ...]]:
        accepted_ids = tuple(item.security_id for item in accepted)
        refused_ids = tuple(item.security_id for item in refused)
        terminal_ids = tuple(sorted((*accepted_ids, *refused_ids)))
        try:
            candidate = _is_preoutcome_candidate_date(
                terminal_ids, accepted_ids, refused_ids
            )
        except FormalInputBundleError as exc:
            raise AcceptedRiskPowerCalibrationError(
                "formal census source-view terminal keys changed"
            ) from exc
        complete_scores = (
            candidate and not refused and accepted_ids == terminal_ids
        )
        capable = False
        if complete_scores:
            firm_scores = {item.firm_specific_score for item in accepted}
            global_scores = {item.global_score for item in accepted}
            capable = not (
                len(firm_scores) == 1 and len(global_scores) == 1
            )
        if capable:
            disposition = "valid_score_capable"
        elif candidate and not complete_scores:
            disposition = "refused_score_terminal"
        elif candidate:
            disposition = "refused_both_arms_constant"
        else:
            disposition = "missing_preoutcome_candidate"
        return candidate, capable, disposition, terminal_ids

    def component_topologies(
        accepted: tuple[object, ...],
    ) -> frozenset[tuple[str, tuple[str, ...]]]:
        by_component: dict[str, list[str]] = {}
        for item in accepted:
            by_component.setdefault(
                item.common_event_component_id, []
            ).append(item.security_id)
        return frozenset(
            (component, tuple(sorted(securities)))
            for component, securities in by_component.items()
        )

    total_sessions = 0
    total_candidates = 0
    total_valid = 0
    total_refused = 0
    total_missing = 0
    total_components = 0
    fold_records: list[dict[str, object]] = []
    source_views = (CURRENT_VIEW_LABEL, CENSORED_VIEW_LABEL)
    expected_coverage_by_fold: dict[
        str, dict[str, tuple[int, int, int, int]]
    ] = {}
    for year in range(2020, 2026):
        fold = build_formal_production_scoring_fold(year)
        boundary = formal_horizon_fold_boundary(fold.fold_id, 20)
        h20_test_start, h20_test_end = boundary[6], boundary[7]
        axis = tuple(
            item.isoformat() for item in trading_sessions(
                date.fromisoformat(h20_test_start),
                date.fromisoformat(h20_test_end),
            ) if item.isoformat() < h20_test_end
        )
        by_session: dict[str, list[object]] = {
            session: [
                "missing_preoutcome_candidate", 0, 0,
                "missing_preoutcome_candidate",
                "missing_preoutcome_candidate",
            ]
            for session in axis
        }
        seen_h20_sessions: set[str] = set()
        for block in stream.iter_streamed_production_scoring_fold(scoring_builder):
            session = block.decision_session.isoformat()
            if block.fold_id != fold.fold_id:
                raise AcceptedRiskPowerCalibrationError("formal census block escaped fold")
            # The outcome-free scorer deliberately spans from the earliest H1
            # start.  The power floor is the reviewed H20 estimand, so earlier
            # H1/H5-only sessions are consumed but excluded from its census.
            if session not in by_session:
                continue
            if session in seen_h20_sessions:
                raise AcceptedRiskPowerCalibrationError(
                    "formal census duplicated an H20 session"
                )
            seen_h20_sessions.add(session)
            current = view_disposition(
                block.current_accepted, block.current_refused
            )
            censored = view_disposition(
                block.censored_accepted, block.censored_refused
            )
            if current[3] != censored[3]:
                raise AcceptedRiskPowerCalibrationError(
                    "formal census source-view terminal keys differ"
                )
            candidate = current[0] and censored[0]
            capable = current[1] and censored[1]
            if capable:
                components = len(
                    component_topologies(block.current_accepted)
                    & component_topologies(block.censored_accepted)
                )
                state_name = "valid_both_views_score_capable"
            elif candidate:
                components = 0
                state_name = "refused_source_view_score_capability"
            else:
                components = 0
                state_name = "missing_preoutcome_candidate"
            by_session[session] = [
                state_name, len(current[3]), components,
                current[2], censored[2],
            ]
        fold_valid = sum(
            item[0] == "valid_both_views_score_capable"
            for item in by_session.values()
        )
        fold_refused = sum(
            str(item[0]).startswith("refused_")
            for item in by_session.values()
        )
        fold_missing = len(axis) - fold_valid - fold_refused
        fold_candidates = fold_valid + fold_refused
        fold_components = sum(int(item[2]) for item in by_session.values())
        source_view_date_census: list[dict[str, object]] = []
        expected_coverage_by_view: dict[str, tuple[int, int, int, int]] = {}
        for source_view_id, disposition_index in zip(
            source_views, (3, 4), strict=True,
        ):
            dispositions = tuple(
                str(item[disposition_index]) for item in by_session.values()
            )
            capable_dates = dispositions.count("valid_score_capable")
            both_constant_dates = dispositions.count(
                "refused_both_arms_constant"
            )
            score_refused_dates = dispositions.count(
                "refused_score_terminal"
            )
            candidate_dates = (
                capable_dates + both_constant_dates + score_refused_dates
            )
            expected_coverage_by_view[source_view_id] = (
                candidate_dates,
                capable_dates,
                both_constant_dates,
                score_refused_dates,
            )
            source_view_date_census.append({
                "source_view_id": source_view_id,
                "preoutcome_candidate_date_count": candidate_dates,
                "score_capable_date_count": capable_dates,
                "both_arms_constant_date_count": both_constant_dates,
                "score_refused_candidate_date_count": score_refused_dates,
            })
        expected_coverage_by_fold[fold.fold_id] = expected_coverage_by_view
        total_sessions += len(axis)
        total_candidates += fold_candidates
        total_valid += fold_valid
        total_refused += fold_refused
        total_missing += fold_missing
        total_components += fold_components
        fold_records.append({
            "fold_id": fold.fold_id,
            "h20_test_session_capacity": len(axis),
            "preoutcome_candidate_date_count": fold_candidates,
            "valid_h20_test_session_count": fold_valid,
            "refused_h20_test_session_count": fold_refused,
            "missing_h20_test_session_count": fold_missing,
            "connected_component_instance_count": fold_components,
            "source_view_date_census": source_view_date_census,
            "session_disposition_census_sha256": hashlib.sha256(
                canonical_json_bytes([
                    [session, *by_session[session]] for session in axis
                ])
            ).hexdigest(),
        })
    artifact = stream.finish_streamed_production_scoring(scoring_builder)
    try:
        stream.require_streamed_production_scoring_artifact(artifact)
        commitments = artifact.fold_commitments
        if (
            type(commitments) is not tuple
            or len(commitments) != len(FORMAL_PRIMARY_FOLD_IDS)
            or tuple(item.fold_id for item in commitments)
            != FORMAL_PRIMARY_FOLD_IDS
        ):
            raise AcceptedRiskPowerCalibrationError(
                "formal census scoring fold commitments changed"
            )
        for commitment in commitments:
            coverages = commitment.global_comparator_coverages
            if (
                type(coverages) is not tuple
                or len(coverages) != len(source_views)
                or tuple(item.source_view_id for item in coverages)
                != source_views
            ):
                raise AcceptedRiskPowerCalibrationError(
                    "formal census scoring source-view coverages changed"
                )
            expected_by_view = expected_coverage_by_fold[commitment.fold_id]
            for coverage in coverages:
                ledgers = {item.ledger_id: item for item in coverage.ledgers}
                dates = dict(coverage.date_diagnostic_counts)
                score_capable = ledgers["score_capable_dates"]
                observed = (
                    dates["preoutcome_candidate_dates"],
                    score_capable.numerator,
                    dates["both_arms_constant_dates"],
                    dates["score_refused_candidate_dates"],
                )
                if (
                    coverage.fold_ids != (commitment.fold_id,)
                    or type(score_capable.numerator) is not int
                    or type(score_capable.denominator) is not int
                    or any(type(item) is not int for item in observed)
                    or score_capable.denominator != observed[0]
                    or observed[0] != sum(observed[1:])
                    or observed != expected_by_view[coverage.source_view_id]
                ):
                    raise AcceptedRiskPowerCalibrationError(
                        "formal census differs from authenticated coverage ledger"
                    )
    except AcceptedRiskPowerCalibrationError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise AcceptedRiskPowerCalibrationError(
            "formal census scoring coverage could not be authenticated"
        ) from exc
    if total_sessions != TEST_SESSION_CAPACITY:
        raise AcceptedRiskPowerCalibrationError("formal H20 test capacity changed")
    record = {
        "schema": FORMAL_CENSUS_SCHEMA,
        "scoring_artifact_id": artifact.artifact_id,
        "scoring_artifact_sha256": artifact.artifact_sha256,
        "h20_test_session_capacity": total_sessions,
        "preoutcome_candidate_date_count": total_candidates,
        "valid_h20_test_session_count": total_valid,
        "refused_h20_test_session_count": total_refused,
        "missing_h20_test_session_count": total_missing,
        "connected_component_instance_count": total_components,
        "folds": fold_records,
        "complete_axis": True,
        "source_views": list(source_views),
        "source_view_date_census_matches_authenticated_coverage": True,
        "valid_dates_require_both_views_score_capable": True,
        "connected_components_require_exact_common_view_topology": True,
        "outcome_access": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(AuthenticatedFormalTestPowerCensus)
    for name, item in {
        "census_id": f"arv2-formal-test-power-census-{digest[:24]}",
        "census_sha256": digest,
        "scoring_artifact": artifact,
        "scoring_artifact_id": artifact.artifact_id,
        "scoring_artifact_sha256": artifact.artifact_sha256,
        "h20_test_session_capacity": total_sessions,
        "preoutcome_candidate_date_count": total_candidates,
        "valid_h20_test_session_count": total_valid,
        "refused_h20_test_session_count": total_refused,
        "missing_h20_test_session_count": total_missing,
        "connected_component_instance_count": total_components,
        "complete_axis": True,
    }.items():
        object.__setattr__(value, name, item)
    _authority_register(value, artifact, record)
    return require_authenticated_formal_test_power_census(value)


def _require_authenticated_formal_test_power_census_impl(
    value: AuthenticatedFormalTestPowerCensus,
    *,
    _authority_current: object,
) -> AuthenticatedFormalTestPowerCensus:
    from research.analyst_revisions_v2_qc.formal_streaming_input import (
        require_streamed_production_scoring_artifact,
    )

    if type(value) is not AuthenticatedFormalTestPowerCensus:
        raise AcceptedRiskPowerCalibrationError("formal power census changed type")
    registered = _authority_current(value)
    if registered is None or registered[0]() is not value:
        raise AcceptedRiskPowerCalibrationError("formal power census lacks authority")
    artifact = registered[1]()
    if artifact is None:
        raise AcceptedRiskPowerCalibrationError("formal census scorer was released")
    require_streamed_production_scoring_artifact(artifact)
    count_fields = (
        value.h20_test_session_capacity,
        value.preoutcome_candidate_date_count,
        value.valid_h20_test_session_count,
        value.refused_h20_test_session_count,
        value.missing_h20_test_session_count,
        value.connected_component_instance_count,
    )
    stored = json.loads(registered[2].decode("utf-8"))
    stored_digest = hashlib.sha256(registered[2]).hexdigest()
    if (
        value.scoring_artifact is not artifact
        or registered[3] != os.getpid()
        or value.census_sha256 != stored_digest
        or value.census_id
        != f"arv2-formal-test-power-census-{stored_digest[:24]}"
        or any(type(item) is not int for item in count_fields)
        or value.scoring_artifact_id != artifact.artifact_id
        or value.scoring_artifact_sha256 != artifact.artifact_sha256
        or value.scoring_artifact_id != stored["scoring_artifact_id"]
        or value.scoring_artifact_sha256
        != stored["scoring_artifact_sha256"]
        or value.h20_test_session_capacity != TEST_SESSION_CAPACITY
        or value.h20_test_session_capacity
        != stored["h20_test_session_capacity"]
        or value.preoutcome_candidate_date_count
        != stored["preoutcome_candidate_date_count"]
        or value.valid_h20_test_session_count
        != stored["valid_h20_test_session_count"]
        or value.refused_h20_test_session_count
        != stored["refused_h20_test_session_count"]
        or value.missing_h20_test_session_count
        != stored["missing_h20_test_session_count"]
        or value.connected_component_instance_count
        != stored["connected_component_instance_count"]
        or value.preoutcome_candidate_date_count
        != (
            value.valid_h20_test_session_count
            + value.refused_h20_test_session_count
        )
        or value.h20_test_session_capacity
        != (
            value.valid_h20_test_session_count
            + value.refused_h20_test_session_count
            + value.missing_h20_test_session_count
        )
        or min(
            value.preoutcome_candidate_date_count,
            value.valid_h20_test_session_count,
            value.refused_h20_test_session_count,
            value.missing_h20_test_session_count,
        ) < 0
        or value.connected_component_instance_count < 0
        or value.complete_axis is not True
    ):
        raise AcceptedRiskPowerCalibrationError("formal power census changed")
    return value


def _build_authenticated_power_floor_binding_impl(
    *, receipt: AcceptedRiskPowerCalibrationReceipt,
    successor: AcceptedRiskStockPowerSuccessor,
    formal_census: AuthenticatedFormalTestPowerCensus,
    _authority_register: object,
) -> AuthenticatedPowerFloorBinding:
    """Create the sole accepted-risk formal power floor from authenticated data.

    The ordinary ``PowerFloorBinding`` remains a transport value.  This wrapper
    is the launch authority: it binds that exact object by identity to the
    accepted-risk receipt, stock-power successor, formal binding, and the
    separately streamed 1,388-session preoutcome TEST census.
    """

    from .formal_input_bundle import (
        build_formal_power_calibration_binding,
        require_formal_power_calibration_binding,
    )
    from .formal_run_protocol import (
        ArtifactBinding, PowerFloorBinding, require_power_floor_binding,
    )

    receipt = require_accepted_risk_power_calibration_receipt(receipt)
    successor = require_accepted_risk_stock_power_successor(successor)
    formal_census = require_authenticated_formal_test_power_census(formal_census)
    if (
        successor.receipt_id != receipt.receipt_id
        or successor.receipt_sha256 != receipt.receipt_hash
        or receipt.disposition
        is not ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
        or formal_census.valid_h20_test_session_count
        < receipt.required_valid_dates
        or formal_census.connected_component_instance_count
        < receipt.required_connected_components
    ):
        raise AcceptedRiskPowerCalibrationError(
            "authenticated formal preoutcome census does not meet the fixed power floor"
        )
    formal_power = build_formal_power_calibration_binding(receipt)
    receipt_bytes = canonical_json_bytes({
        "schema": RECEIPT_SCHEMA,
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.receipt_hash,
    })
    successor_bytes = canonical_json_bytes({
        "schema": SUCCESSOR_SCHEMA,
        "successor_id": successor.successor_id,
        "successor_sha256": successor.successor_sha256,
    })
    power_floor = PowerFloorBinding(
        numeric_receipt=ArtifactBinding(
            artifact_id=receipt.receipt_id,
            content_sha256=receipt.receipt_hash,
            artifact_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
            byte_count=len(receipt_bytes),
        ),
        stock_successor=ArtifactBinding(
            artifact_id=successor.successor_id,
            content_sha256=successor.successor_sha256,
            artifact_sha256=hashlib.sha256(successor_bytes).hexdigest(),
            byte_count=len(successor_bytes),
        ),
        disposition=receipt.disposition.value,
        required_valid_dates=receipt.required_valid_dates,
        observed_preoutcome_valid_dates=(
            formal_census.valid_h20_test_session_count
        ),
        required_connected_components=receipt.required_connected_components,
        observed_preoutcome_connected_components=(
            formal_census.connected_component_instance_count
        ),
        h20_test_session_capacity=formal_census.h20_test_session_capacity,
        preoutcome_candidate_date_count=(
            formal_census.preoutcome_candidate_date_count
        ),
        valid_h20_test_session_count=(
            formal_census.valid_h20_test_session_count
        ),
        refused_h20_test_session_count=(
            formal_census.refused_h20_test_session_count
        ),
        missing_h20_test_session_count=(
            formal_census.missing_h20_test_session_count
        ),
        connected_component_instance_count=(
            formal_census.connected_component_instance_count
        ),
    )
    require_power_floor_binding(power_floor)
    record = {
        "schema": "arv2-authenticated-formal-power-floor-binding-v3",
        "power_floor": power_floor.to_record(),
        "formal_power": formal_power.to_record(),
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.receipt_hash,
        "successor_id": successor.successor_id,
        "successor_sha256": successor.successor_sha256,
        "formal_census_id": formal_census.census_id,
        "formal_census_sha256": formal_census.census_sha256,
        "scoring_artifact_id": formal_census.scoring_artifact_id,
        "scoring_artifact_sha256": formal_census.scoring_artifact_sha256,
        "h20_test_session_capacity": (
            formal_census.h20_test_session_capacity
        ),
        "preoutcome_candidate_date_count": (
            formal_census.preoutcome_candidate_date_count
        ),
        "valid_h20_test_session_count": (
            formal_census.valid_h20_test_session_count
        ),
        "refused_h20_test_session_count": (
            formal_census.refused_h20_test_session_count
        ),
        "missing_h20_test_session_count": (
            formal_census.missing_h20_test_session_count
        ),
        "connected_component_instance_count": (
            formal_census.connected_component_instance_count
        ),
        "observed_valid_dates": formal_census.valid_h20_test_session_count,
        "observed_connected_components": (
            formal_census.connected_component_instance_count
        ),
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(AuthenticatedPowerFloorBinding)
    for name, item in {
        "binding_id": f"arv2-authenticated-power-floor-{digest[:24]}",
        "binding_sha256": digest,
        "power_floor": power_floor, "formal_power": formal_power,
        "receipt": receipt, "successor": successor,
        "formal_census": formal_census,
        "receipt_id": receipt.receipt_id, "receipt_sha256": receipt.receipt_hash,
        "successor_id": successor.successor_id,
        "successor_sha256": successor.successor_sha256,
        "formal_census_id": formal_census.census_id,
        "formal_census_sha256": formal_census.census_sha256,
        "scoring_artifact_id": formal_census.scoring_artifact_id,
        "scoring_artifact_sha256": formal_census.scoring_artifact_sha256,
        "h20_test_session_capacity": formal_census.h20_test_session_capacity,
        "preoutcome_candidate_date_count": (
            formal_census.preoutcome_candidate_date_count
        ),
        "valid_h20_test_session_count": (
            formal_census.valid_h20_test_session_count
        ),
        "refused_h20_test_session_count": (
            formal_census.refused_h20_test_session_count
        ),
        "missing_h20_test_session_count": (
            formal_census.missing_h20_test_session_count
        ),
        "connected_component_instance_count": (
            formal_census.connected_component_instance_count
        ),
        "observed_valid_dates": formal_census.valid_h20_test_session_count,
        "observed_connected_components": (
            formal_census.connected_component_instance_count
        ),
    }.items():
        object.__setattr__(value, name, item)
    _authority_register(
        value,
        receipt,
        successor,
        formal_census,
        formal_power,
        power_floor,
        record,
    )
    return require_authenticated_power_floor_binding(value)


def _require_authenticated_power_floor_binding_impl(
    value: AuthenticatedPowerFloorBinding,
    *,
    _authority_current: object,
) -> AuthenticatedPowerFloorBinding:
    from .formal_input_bundle import require_formal_power_calibration_binding
    from .formal_run_protocol import require_power_floor_binding

    if type(value) is not AuthenticatedPowerFloorBinding:
        raise AcceptedRiskPowerCalibrationError("authenticated power floor changed type")
    registered = _authority_current(value)
    if registered is None or registered[0]() is not value:
        raise AcceptedRiskPowerCalibrationError("authenticated power floor lacks authority")
    receipt, successor, census, formal_power = (
        registered[index]() for index in (1, 2, 3, 4)
    )
    if any(item is None for item in (receipt, successor, census, formal_power)):
        raise AcceptedRiskPowerCalibrationError("authenticated power-floor parent released")
    require_accepted_risk_power_calibration_receipt(receipt)
    require_accepted_risk_stock_power_successor(successor)
    require_authenticated_formal_test_power_census(census)
    require_formal_power_calibration_binding(formal_power)
    require_power_floor_binding(value.power_floor)
    record = {
        "schema": "arv2-authenticated-formal-power-floor-binding-v3",
        "power_floor": value.power_floor.to_record(),
        "formal_power": value.formal_power.to_record(),
        "receipt_id": value.receipt_id,
        "receipt_sha256": value.receipt_sha256,
        "successor_id": value.successor_id,
        "successor_sha256": value.successor_sha256,
        "formal_census_id": value.formal_census_id,
        "formal_census_sha256": value.formal_census_sha256,
        "scoring_artifact_id": value.scoring_artifact_id,
        "scoring_artifact_sha256": value.scoring_artifact_sha256,
        "h20_test_session_capacity": (
            census.h20_test_session_capacity
        ),
        "preoutcome_candidate_date_count": (
            census.preoutcome_candidate_date_count
        ),
        "valid_h20_test_session_count": (
            census.valid_h20_test_session_count
        ),
        "refused_h20_test_session_count": (
            census.refused_h20_test_session_count
        ),
        "missing_h20_test_session_count": (
            census.missing_h20_test_session_count
        ),
        "connected_component_instance_count": (
            census.connected_component_instance_count
        ),
        "observed_valid_dates": value.observed_valid_dates,
        "observed_connected_components": value.observed_connected_components,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    if (
        value.formal_power is not formal_power
        or value.receipt is not receipt
        or value.successor is not successor
        or value.formal_census is not census
        or id(value.power_floor) != registered[5]
        or canonical_json_bytes(record) != registered[6]
        or registered[7] != os.getpid()
        or value.binding_id != f"arv2-authenticated-power-floor-{digest[:24]}"
        or value.binding_sha256 != digest
        or value.power_floor.numeric_receipt.artifact_id != receipt.receipt_id
        or value.power_floor.numeric_receipt.content_sha256 != receipt.receipt_hash
        or value.power_floor.stock_successor.artifact_id != successor.successor_id
        or value.power_floor.stock_successor.content_sha256 != successor.successor_sha256
        or value.power_floor.observed_preoutcome_valid_dates
        != census.valid_h20_test_session_count
        or value.power_floor.observed_preoutcome_connected_components
        != census.connected_component_instance_count
        or value.scoring_artifact_id != census.scoring_artifact_id
        or value.scoring_artifact_sha256 != census.scoring_artifact_sha256
        or value.h20_test_session_capacity
        != census.h20_test_session_capacity
        or value.preoutcome_candidate_date_count
        != census.preoutcome_candidate_date_count
        or value.valid_h20_test_session_count
        != census.valid_h20_test_session_count
        or value.refused_h20_test_session_count
        != census.refused_h20_test_session_count
        or value.missing_h20_test_session_count
        != census.missing_h20_test_session_count
        or value.connected_component_instance_count
        != census.connected_component_instance_count
    ):
        raise AcceptedRiskPowerCalibrationError("authenticated power floor changed")
    return value


def _bind_power_artifact_authority(
    *,
    build_input_impl: object,
    build_physical_input_impl: object,
    require_input_impl: object,
    load_output_impl: object,
    require_output_impl: object,
    compute_receipt_impl: object,
    require_receipt_impl: object,
    build_successor_impl: object,
    require_successor_impl: object,
    require_terminal_impl: object,
    register_input: object,
    current_input: object,
    register_output: object,
    current_output: object,
    register_receipt: object,
    current_receipt: object,
    register_successor: object,
    current_successor: object,
    current_terminal: object,
    system_module: object,
    module_registry: object,
) -> tuple[object, ...]:
    """Bind every artifact transition to the closure-private authority vault."""

    physical_module_name = (
        "research.analyst_revisions_v2_qc.physical_streaming_scoring"
    )
    physical_names = (
        "physical_streaming_scoring_composition_context",
        "run_physical_power_calibration_stream",
        "require_physical_power_calibration_stream",
    )
    physical_authority: tuple[object, tuple[object, ...]] | None = None

    def resolve_physical() -> tuple[object, object, object]:
        nonlocal physical_authority
        try:
            module = module_registry.get(physical_module_name)
            registry_is_current = system_module.modules is module_registry
            operations = tuple(getattr(module, name) for name in physical_names)
        except (AttributeError, TypeError) as exc:
            raise AcceptedRiskPowerCalibrationError(
                "physical calibration scorer is unavailable"
            ) from exc
        if (
            module is None
            or not registry_is_current
            or any(
                not callable(operation)
                or getattr(operation, "__module__", None) != physical_module_name
                or getattr(operation, "__name__", None) != name
                for operation, name in zip(
                    operations, physical_names, strict=True
                )
            )
        ):
            raise AcceptedRiskPowerCalibrationError(
                "physical calibration operations changed before use"
            )
        if physical_authority is None:
            physical_authority = (module, operations)
        elif (
            physical_authority[0] is not module
            or module_registry.get(physical_module_name) is not module
            or any(
                operation is not expected
                for operation, expected in zip(
                    operations, physical_authority[1], strict=True
                )
            )
        ):
            raise AcceptedRiskPowerCalibrationError(
                "sealed physical calibration operations changed"
            )
        return operations  # type: ignore[return-value]

    def build_input(
        *, scoring_builder: object, protocol: PowerCalibrationProtocol,
        terminal_recorder: object, benchmark_security_id: str,
        output_directory: Path,
    ) -> AcceptedRiskPowerCalibrationInput:
        """Use SignalArm.CURRENT_VINTAGE via _run_accepted_risk_power_calibration_stream."""

        return build_input_impl(
            scoring_builder=scoring_builder,
            protocol=protocol,
            terminal_recorder=terminal_recorder,
            benchmark_security_id=benchmark_security_id,
            output_directory=output_directory,
            _authority_register=register_input,
        )

    def require_input(
        value: AcceptedRiskPowerCalibrationInput,
    ) -> AcceptedRiskPowerCalibrationInput:
        return require_input_impl(
            value,
            _authority_current=current_input,
            _resolve_physical=resolve_physical,
        )

    def build_physical_accepted_risk_power_calibration_input(
        *,
        scoring_builder: object,
        accepted_risk_binding: object,
        protocol: PowerCalibrationProtocol,
        terminal_recorder: object,
        benchmark_security_id: str,
        output_directory: Path,
    ) -> AcceptedRiskPowerCalibrationInput:
        return build_physical_input_impl(
            scoring_builder=scoring_builder,
            accepted_risk_binding=accepted_risk_binding,
            protocol=protocol,
            terminal_recorder=terminal_recorder,
            benchmark_security_id=benchmark_security_id,
            output_directory=output_directory,
            _authority_register=register_input,
            _physical_operations=resolve_physical(),
        )

    def load_output(
        *, calibration_input: AcceptedRiskPowerCalibrationInput,
        terminal_receipt: PowerCalibrationQcTerminalReceipt,
        manifest_path: Path, shard_paths: tuple[Path, ...],
    ) -> AcceptedRiskPowerCalibrationOutput:
        return load_output_impl(
            calibration_input=calibration_input,
            terminal_receipt=terminal_receipt,
            manifest_path=manifest_path,
            shard_paths=shard_paths,
            _authority_register=register_output,
        )

    def require_output(
        value: AcceptedRiskPowerCalibrationOutput,
    ) -> AcceptedRiskPowerCalibrationOutput:
        return require_output_impl(value, _authority_current=current_output)

    def compute_receipt(
        *, protocol: PowerCalibrationProtocol,
        output: AcceptedRiskPowerCalibrationOutput,
        accepted_risk_policy_id: str,
    ) -> AcceptedRiskPowerCalibrationReceipt:
        return compute_receipt_impl(
            protocol=protocol,
            output=output,
            accepted_risk_policy_id=accepted_risk_policy_id,
            _authority_register=register_receipt,
        )

    def require_receipt(
        value: AcceptedRiskPowerCalibrationReceipt,
    ) -> AcceptedRiskPowerCalibrationReceipt:
        return require_receipt_impl(value, _authority_current=current_receipt)

    def build_successor(
        receipt: AcceptedRiskPowerCalibrationReceipt,
    ) -> AcceptedRiskStockPowerSuccessor:
        return build_successor_impl(
            receipt,
            _authority_register=register_successor,
        )

    def require_successor(
        value: AcceptedRiskStockPowerSuccessor,
    ) -> AcceptedRiskStockPowerSuccessor:
        return require_successor_impl(value, _authority_current=current_successor)

    def require_terminal(
        value: PowerCalibrationQcTerminalReceipt,
    ) -> PowerCalibrationQcTerminalReceipt:
        return require_terminal_impl(value, _authority_current=current_terminal)

    return (
        build_input,
        build_physical_accepted_risk_power_calibration_input,
        require_input,
        load_output,
        require_output,
        compute_receipt,
        require_receipt,
        build_successor,
        require_successor,
        require_terminal,
    )


_seal_power_artifact_builder_callers(
    input_builder=_build_accepted_risk_power_calibration_input_impl,
    physical_input_builder=(
        _build_physical_accepted_risk_power_calibration_input_impl
    ),
    output_loader=_load_accepted_risk_power_calibration_output_impl,
    receipt_builder=_compute_accepted_risk_power_calibration_receipt_impl,
    successor_builder=_build_accepted_risk_stock_power_successor_impl,
)


(
    build_accepted_risk_power_calibration_input,
    build_physical_accepted_risk_power_calibration_input,
    require_accepted_risk_power_calibration_input,
    load_accepted_risk_power_calibration_output,
    require_accepted_risk_power_calibration_output,
    compute_accepted_risk_power_calibration_receipt,
    require_accepted_risk_power_calibration_receipt,
    build_accepted_risk_stock_power_successor,
    require_accepted_risk_stock_power_successor,
    require_power_calibration_qc_terminal_receipt,
) = _bind_power_artifact_authority(
    build_input_impl=_build_accepted_risk_power_calibration_input_impl,
    build_physical_input_impl=(
        _build_physical_accepted_risk_power_calibration_input_impl
    ),
    require_input_impl=_require_accepted_risk_power_calibration_input_impl,
    load_output_impl=_load_accepted_risk_power_calibration_output_impl,
    require_output_impl=_require_accepted_risk_power_calibration_output_impl,
    compute_receipt_impl=_compute_accepted_risk_power_calibration_receipt_impl,
    require_receipt_impl=_require_accepted_risk_power_calibration_receipt_impl,
    build_successor_impl=_build_accepted_risk_stock_power_successor_impl,
    require_successor_impl=_require_accepted_risk_stock_power_successor_impl,
    require_terminal_impl=_require_power_calibration_qc_terminal_receipt_impl,
    register_input=_power_artifact_register_input,
    current_input=_power_artifact_current_input,
    register_output=_power_artifact_register_output,
    current_output=_power_artifact_current_output,
    register_receipt=_power_artifact_register_receipt,
    current_receipt=_power_artifact_current_receipt,
    register_successor=_power_artifact_register_successor,
    current_successor=_power_artifact_current_successor,
    current_terminal=_power_artifact_current_terminal,
    system_module=sys,
    module_registry=sys.modules,
)

del _bind_power_artifact_authority
del _build_accepted_risk_power_calibration_input_impl
del _build_physical_accepted_risk_power_calibration_input_impl
del _require_accepted_risk_power_calibration_input_impl
del _load_accepted_risk_power_calibration_output_impl
del _require_accepted_risk_power_calibration_output_impl
del _compute_accepted_risk_power_calibration_receipt_impl
del _require_accepted_risk_power_calibration_receipt_impl
del _build_accepted_risk_stock_power_successor_impl
del _require_accepted_risk_stock_power_successor_impl
del _require_power_calibration_qc_terminal_receipt_impl
del _power_artifact_register_input
del _power_artifact_current_input
del _power_artifact_register_output
del _power_artifact_current_output
del _power_artifact_register_receipt
del _power_artifact_current_receipt
del _power_artifact_register_successor
del _power_artifact_current_successor
del _power_artifact_current_terminal
del _seal_power_artifact_builder_callers
del _make_power_artifact_authority


def _bind_power_launch_authority(
    *,
    build_census_impl: object,
    require_census_impl: object,
    build_floor_impl: object,
    require_floor_impl: object,
    register_census: object,
    current_census: object,
    register_floor: object,
    current_floor: object,
) -> tuple[object, object, object, object]:
    """Bind authority mutation lexically to its derivation-only builders."""

    def build_census(
        scoring_builder: object,
    ) -> AuthenticatedFormalTestPowerCensus:
        return build_census_impl(
            scoring_builder,
            _authority_register=register_census,
        )

    def require_census(
        value: AuthenticatedFormalTestPowerCensus,
    ) -> AuthenticatedFormalTestPowerCensus:
        return require_census_impl(
            value,
            _authority_current=current_census,
        )

    def build_floor(
        *,
        receipt: AcceptedRiskPowerCalibrationReceipt,
        successor: AcceptedRiskStockPowerSuccessor,
        formal_census: AuthenticatedFormalTestPowerCensus,
    ) -> AuthenticatedPowerFloorBinding:
        return build_floor_impl(
            receipt=receipt,
            successor=successor,
            formal_census=formal_census,
            _authority_register=register_floor,
        )

    def require_floor(
        value: AuthenticatedPowerFloorBinding,
    ) -> AuthenticatedPowerFloorBinding:
        return require_floor_impl(
            value,
            _authority_current=current_floor,
        )

    return build_census, require_census, build_floor, require_floor


_seal_power_launch_builder_callers(
    census_builder=_build_authenticated_formal_test_power_census_impl,
    floor_builder=_build_authenticated_power_floor_binding_impl,
)


(
    build_authenticated_formal_test_power_census,
    require_authenticated_formal_test_power_census,
    build_authenticated_power_floor_binding,
    require_authenticated_power_floor_binding,
) = _bind_power_launch_authority(
    build_census_impl=_build_authenticated_formal_test_power_census_impl,
    require_census_impl=_require_authenticated_formal_test_power_census_impl,
    build_floor_impl=_build_authenticated_power_floor_binding_impl,
    require_floor_impl=_require_authenticated_power_floor_binding_impl,
    register_census=_power_authority_register_census,
    current_census=_power_authority_current_census,
    register_floor=_power_authority_register_floor,
    current_floor=_power_authority_current_floor,
)

del _bind_power_launch_authority
del _build_authenticated_formal_test_power_census_impl
del _require_authenticated_formal_test_power_census_impl
del _build_authenticated_power_floor_binding_impl
del _require_authenticated_power_floor_binding_impl
del _power_authority_register_census
del _power_authority_current_census
del _power_authority_register_floor
del _power_authority_current_floor
del _seal_power_launch_builder_callers
del _make_power_launch_authority


__all__ = [
    "AcceptedRiskPowerCalibrationError",
    "AcceptedRiskPowerCalibrationInput",
    "AcceptedRiskPowerCalibrationOutput",
    "AcceptedRiskPowerCalibrationReceipt",
    "AcceptedRiskStockPowerSuccessor",
    "AuthenticatedFormalTestPowerCensus",
    "AuthenticatedPowerFloorBinding",
    "BACKTEST_NAME",
    "CalibrationBetaRecord",
    "CalibrationBetaState",
    "CalibrationShardDescriptor",
    "PROJECT_NAME",
    "PowerCalibrationQcTerminalReceipt",
    "build_accepted_risk_power_calibration_input",
    "build_physical_accepted_risk_power_calibration_input",
    "build_accepted_risk_stock_power_successor",
    "build_authenticated_formal_test_power_census",
    "build_authenticated_power_floor_binding",
    "calibration_axis",
    "canonical_json_bytes",
    "compute_accepted_risk_power_calibration_receipt",
    "iter_accepted_risk_power_calibration_input_rows",
    "load_accepted_risk_power_calibration_output",
    "require_accepted_risk_power_calibration_input",
    "require_accepted_risk_power_calibration_output",
    "require_accepted_risk_power_calibration_receipt",
    "require_accepted_risk_stock_power_successor",
    "require_authenticated_formal_test_power_census",
    "require_authenticated_power_floor_binding",
    "require_power_calibration_qc_terminal_receipt",
]
