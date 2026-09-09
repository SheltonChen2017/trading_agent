from __future__ import annotations

import copy
import concurrent.futures
import dataclasses
import errno
import gc
import hashlib
import json
import os
import pickle
import signal
import stat
import threading
import time
import traceback
import weakref
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    getcontext,
    localcontext,
    setcontext,
)
from pathlib import Path
from types import MappingProxyType

import pytest

import research.analyst_revisions_v2.artifact_io as artifact_io_module
import research.analyst_revisions_v2.power_calibration_receipt as module
import tests.analyst_revisions_v2.test_power_calibration_input_manifest as b2_helpers
from research.analyst_revisions_v2.power_calibration_input_manifest import (
    PowerCalibrationManifestAdmission,
    ProductionCalibrationInputManifestCandidate,
    load_power_calibration_manifest_admission,
)
from research.analyst_revisions_v2.power_calibration_protocol import (
    CALIBRATION_SESSION_COUNT,
    HAC_MAX_LAG,
    MINIMUM_ABSOLUTE_FLOOR,
    NORMAL_SUM_SQUARED,
    TEST_SESSION_CAPACITY,
    PowerCalibrationProtocol,
    ProvisionalPowerDisposition,
    load_power_calibration_protocol,
)


SPEC_ROOT = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "analyst_revisions_v2"
    / "specs"
)
CONTENT_CONTRACT_FILENAME = (
    "arv2_stock_power_calibration_input_content_contract.structural.json"
)


def _wait_child_bounded(process_id: int, *, timeout_seconds: float = 8.0) -> int:
    """Reap a forked test child without hanging on an after-fork regression."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        waited, status = os.waitpid(process_id, os.WNOHANG)
        if waited == process_id:
            return status
        time.sleep(0.01)
    try:
        os.kill(process_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _, status = os.waitpid(process_id, 0)
    return status


AUTHORIZATION_ID = "owner-arv2-4d-b-input-nuisance-authorization-20260907"
AUTHORIZATION_EVIDENCE_SHA256 = hashlib.sha256(
    b"synthetic fixture standing in for the exact owner authorization evidence"
).hexdigest()
AUTHORIZED_AT_UTC = "2026-09-07T20:00:00.000000Z"
FIXTURE_TRUTH_REVIEW_ID = "fixture-only-independent-truth-review"
FIXTURE_TRUTH_REVIEW_EVIDENCE_SHA256 = hashlib.sha256(
    b"fixture-only truth evidence; never production approval"
).hexdigest()
FIXTURE_TRUTH_REVIEWED_AT_UTC = "2026-09-07T19:59:00.000000Z"


class _FingerprintThenForgeMapping(Mapping[str, object]):
    """Expose honest values for one fingerprint pass, then a forged value."""

    def __init__(
        self,
        honest: Mapping[str, object],
        *,
        target: str,
        forged: object,
    ) -> None:
        self._honest = dict(honest)
        self._target = target
        self._forged = forged
        self._honest_reads_remaining = len(self._honest)
        self.touches = 0

    def __getitem__(self, key: str) -> object:
        self.touches += 1
        if self._honest_reads_remaining:
            self._honest_reads_remaining -= 1
            return self._honest[key]
        if key == self._target:
            return self._forged
        return self._honest[key]

    def __iter__(self):
        self.touches += 1
        return iter(self._honest)

    def __len__(self) -> int:
        self.touches += 1
        return len(self._honest)


def _equal_distinct_container(value: object) -> object:
    if type(value) is MappingProxyType:
        return MappingProxyType(dict(value))
    if type(value) is tuple:
        replacement = tuple(item for item in value)
        assert replacement is not value
        return replacement
    raise AssertionError("test field is not a loader-owned container")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _is_link_capability_error(exc: OSError) -> bool:
    unsupported = {errno.EACCES, errno.EPERM, errno.ENOSYS}
    for name in ("ENOTSUP", "EOPNOTSUPP"):
        value = getattr(errno, name, None)
        if value is not None:
            unsupported.add(value)
    return getattr(exc, "winerror", None) in {1, 5, 50, 1314} or (
        exc.errno in unsupported
    )


def _symlink_or_skip(
    link: Path, target: Path, *, target_is_directory: bool = False
) -> None:
    """Create a test symlink, skipping only for a known host capability limit."""
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as exc:
        if _is_link_capability_error(exc):
            pytest.skip(f"host cannot create a symlink: {exc}")
        raise


def _junction_or_skip(link: Path, target: Path) -> None:
    try:
        import _winapi
    except ImportError:
        pytest.skip("directory junctions are Windows-only")
    try:
        _winapi.CreateJunction(str(target), str(link))
    except OSError as exc:
        if _is_link_capability_error(exc):
            pytest.skip(f"host cannot create a junction: {exc}")
        raise
    assert link.is_junction()


def _render(value: object) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class _Parents:
    protocol: PowerCalibrationProtocol
    input_schema: object
    overlay: object
    admission: PowerCalibrationManifestAdmission
    content_contract: object


@dataclass(frozen=True)
class _AuthorizedInputs:
    candidate: ProductionCalibrationInputManifestCandidate
    input_authority: object
    beta_path: Path
    component_path: Path
    truth_approval_path: Path
    beta_document: dict[str, object]
    component_document: dict[str, object]


def _load_protocol() -> PowerCalibrationProtocol:
    names = b2_helpers.PARENT_FILENAMES
    return load_power_calibration_protocol(
        SPEC_ROOT / names["protocol"],
        map_path=SPEC_ROOT / names["map"],
        matched_contract_path=SPEC_ROOT / names["matched"],
        successor_spec_path=SPEC_ROOT / names["successor"],
        parent_stock_spec_path=SPEC_ROOT / names["stock"],
        fold_manifest_path=SPEC_ROOT / names["folds"],
        qc_first_plan_path=SPEC_ROOT / names["plan"],
    )


@pytest.fixture(scope="module")
def parents() -> _Parents:
    protocol = _load_protocol()
    input_schema = b2_helpers._load_input_schema()
    overlay = b2_helpers._load_overlay()
    admission = load_power_calibration_manifest_admission(
        SPEC_ROOT / b2_helpers.ADMISSION_FILENAME,
        input_schema=input_schema,
        multiplicity_overlay=overlay,
    )
    content_contract = module.load_power_calibration_input_content_contract(
        SPEC_ROOT / CONTENT_CONTRACT_FILENAME,
        power_protocol=protocol,
        input_schema=input_schema,
        manifest_admission=admission,
        multiplicity_overlay=overlay,
    )
    return _Parents(
        protocol=protocol,
        input_schema=input_schema,
        overlay=overlay,
        admission=admission,
        content_contract=content_contract,
    )


def _baseline_beta_document(
    sessions: tuple[str, ...],
    *,
    missing: frozenset[int] = frozenset({37, 211}),
    refused: frozenset[int] = frozenset({103, 401}),
    multiplier: Decimal = Decimal("0.000001"),
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for index, session in enumerate(sessions):
        if index in missing:
            state = "missing"
            value = None
        elif index in refused:
            state = "refused"
            value = None
        else:
            state = "valid"
            value = _decimal_text(Decimal(index - 241) * multiplier)
        records.append(
            {
                "decision_session": session,
                "state": state,
                "beta_value": value,
            }
        )
    return {
        "schema": "arv2-power-calibration-date-beta-input-v1",
        "records": records,
    }


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def _baseline_component_document(
    sessions: tuple[str, ...], *, zero_count: int = 24
) -> dict[str, object]:
    return {
        "schema": "arv2-power-calibration-component-count-input-v1",
        "records": [
            {
                "decision_session": session,
                "connected_component_count": 0 if index < zero_count else 3,
            }
            for index, session in enumerate(sessions)
        ],
    }


def _beta_inventory(document: dict[str, object]) -> list[dict[str, object]]:
    return [
        {"session": record["decision_session"], "state": record["state"]}
        for record in document["records"]
    ]


def _component_inventory(document: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "session": record["decision_session"],
            "connected_component_count": record["connected_component_count"],
        }
        for record in document["records"]
    ]


@contextmanager
def _fixture_only_truth_gate(truth_approval_path: Path):
    """Test-only direct injection; production exposes no pin override API."""
    old_opener = module.PRODUCTION_TRUTH_EVIDENCE_OPENER_IMPLEMENTED
    old_truth_pin = module.PRODUCTION_TRUTH_APPROVAL_ARTIFACT_SHA256
    module.PRODUCTION_TRUTH_EVIDENCE_OPENER_IMPLEMENTED = True
    module.PRODUCTION_TRUTH_APPROVAL_ARTIFACT_SHA256 = hashlib.sha256(
        truth_approval_path.read_bytes()
    ).hexdigest()
    try:
        yield
    finally:
        module.PRODUCTION_TRUTH_EVIDENCE_OPENER_IMPLEMENTED = old_opener
        module.PRODUCTION_TRUTH_APPROVAL_ARTIFACT_SHA256 = old_truth_pin


@contextmanager
def _fixture_only_authority_gate(
    authority_path: Path, truth_approval_path: Path
):
    with _fixture_only_truth_gate(truth_approval_path):
        old_authority_pin = module.PRODUCTION_INPUT_AUTHORITY_ARTIFACT_SHA256
        module.PRODUCTION_INPUT_AUTHORITY_ARTIFACT_SHA256 = hashlib.sha256(
            authority_path.read_bytes()
        ).hexdigest()
        try:
            yield
        finally:
            module.PRODUCTION_INPUT_AUTHORITY_ARTIFACT_SHA256 = old_authority_pin


def _write_fixture_only_truth_approval(
    tmp_path: Path,
    candidate: ProductionCalibrationInputManifestCandidate,
) -> Path:
    path = tmp_path / "FIXTURE_ONLY-production-truth-approval.json"
    path.write_bytes(
        _render(
            module._truth_approval_document(
                candidate,
                review_id=FIXTURE_TRUTH_REVIEW_ID,
                review_evidence_sha256=FIXTURE_TRUTH_REVIEW_EVIDENCE_SHA256,
                reviewed_at_utc=FIXTURE_TRUTH_REVIEWED_AT_UTC,
            )
        )
    )
    return path


def _write_authorized_inputs(
    tmp_path: Path,
    parents: _Parents,
    *,
    beta_document: dict[str, object] | None = None,
    component_document: dict[str, object] | None = None,
    beta_payload: bytes | None = None,
    component_payload: bytes | None = None,
    beta_metadata_document: dict[str, object] | None = None,
    component_metadata_document: dict[str, object] | None = None,
    descriptor_mutate=None,
) -> _AuthorizedInputs:
    tmp_path.mkdir(parents=True, exist_ok=True)
    sessions = parents.admission.calibration_session_axis
    beta_document = beta_document or _baseline_beta_document(sessions)
    component_document = component_document or _baseline_component_document(sessions)
    beta_metadata_document = beta_metadata_document or beta_document
    component_metadata_document = component_metadata_document or component_document
    beta_payload = beta_payload if beta_payload is not None else _render(beta_document)
    component_payload = (
        component_payload
        if component_payload is not None
        else _render(component_document)
    )
    beta_path = tmp_path / "date-beta.json"
    component_path = tmp_path / "component-counts.json"
    beta_path.write_bytes(beta_payload)
    component_path.write_bytes(component_payload)

    beta_inventory = _beta_inventory(beta_metadata_document)
    component_inventory = _component_inventory(component_metadata_document)
    states = [item["state"] for item in beta_inventory]
    descriptors: dict[str, dict[str, object]] = {
        "date_level_beta_series": {
            "content_sha256": hashlib.sha256(_canonical(beta_document)).hexdigest(),
            "artifact_sha256": hashlib.sha256(beta_payload).hexdigest(),
            "byte_count": len(beta_payload),
            "record_count": len(beta_inventory),
            "session_state_inventory": beta_inventory,
            "valid_beta_date_count": states.count("valid"),
            "missing_beta_date_count": states.count("missing"),
            "refused_beta_date_count": states.count("refused"),
            "state_census_sha256": hashlib.sha256(
                _canonical(beta_inventory)
            ).hexdigest(),
        },
        "component_count_census": {
            "content_sha256": hashlib.sha256(
                _canonical(component_document)
            ).hexdigest(),
            "artifact_sha256": hashlib.sha256(component_payload).hexdigest(),
            "byte_count": len(component_payload),
            "record_count": len(component_inventory),
            "session_count_inventory": component_inventory,
            "component_count_census_sha256": hashlib.sha256(
                _canonical(component_inventory)
            ).hexdigest(),
            "component_count_census_session_count": len(component_inventory),
            "missing_session_count": 0,
        },
    }
    if descriptor_mutate is not None:
        descriptor_mutate(descriptors)

    def evidence_mutate(raw: dict[str, object]) -> None:
        bindings = raw["processing_rights_evidence"][
            "candidate_input_metadata_bindings"
        ]
        for binding in bindings:
            descriptor = descriptors[binding["role"]]
            binding["content_sha256"] = descriptor["content_sha256"]
            binding["artifact_sha256"] = descriptor["artifact_sha256"]

    def manifest_mutate(raw: dict[str, object]) -> None:
        for item in raw["input_artifacts"]:
            descriptor = descriptors[item["role"]]
            item.update(descriptor)
        terminal_by_role = {
            node["role"]: node
            for node in raw["producing_lineage"]["ordered_nodes"]
            if node["role"] in descriptors
        }
        for role, descriptor in descriptors.items():
            terminal_by_role[role]["content_sha256"] = descriptor["content_sha256"]
            terminal_by_role[role]["artifact_sha256"] = descriptor["artifact_sha256"]
        b2_helpers._rehash_lineage(raw)

    paths = b2_helpers._write_candidate(
        tmp_path,
        parents.admission,
        evidence_mutate=evidence_mutate,
        manifest_mutate=manifest_mutate,
    )
    candidate = b2_helpers._load_candidate(parents.admission, paths)
    truth_approval_path = _write_fixture_only_truth_approval(tmp_path, candidate)
    authority_path = tmp_path / "input-authority.json"
    with _fixture_only_truth_gate(truth_approval_path):
        authority_payload = module.render_power_calibration_input_authority(
            parents.content_contract,
            candidate,
            production_truth_approval_path=truth_approval_path,
            owner_authorization_id=AUTHORIZATION_ID,
            owner_authorization_evidence_sha256=AUTHORIZATION_EVIDENCE_SHA256,
            authorized_at_utc=AUTHORIZED_AT_UTC,
        ).encode("utf-8")
        authority_path.write_bytes(authority_payload)
        with _fixture_only_authority_gate(authority_path, truth_approval_path):
            input_authority = module.load_power_calibration_input_authority(
                authority_path,
                content_contract=parents.content_contract,
                manifest_candidate=candidate,
                production_truth_approval_path=truth_approval_path,
            )
    return _AuthorizedInputs(
        candidate=candidate,
        input_authority=input_authority,
        beta_path=beta_path,
        component_path=component_path,
        truth_approval_path=truth_approval_path,
        beta_document=beta_document,
        component_document=component_document,
    )


def _compute(parents: _Parents, inputs: _AuthorizedInputs):
    return module.compute_power_calibration_receipt(
        parents.content_contract,
        inputs.candidate,
        input_authority=inputs.input_authority,
        beta_series_path=inputs.beta_path,
        component_count_path=inputs.component_path,
    )


def _fresh_context() -> Context:
    context = Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )
    for signal in context.traps:
        context.traps[signal] = False
    for signal in (InvalidOperation, DivisionByZero, Overflow):
        context.traps[signal] = True
    context.clear_flags()
    return context


def _stable_sum(values: list[Decimal]) -> Decimal:
    total = Decimal(0)
    for value in sorted(values, key=lambda item: (abs(item), item)):
        total += value
    return total


def _expected_hac(
    document: dict[str, object],
) -> tuple[Decimal, tuple[int, ...]]:
    records = document["records"]
    with localcontext(_fresh_context()) as active:
        active.clear_flags()
        values_by_index = {
            index: Decimal(record["beta_value"])
            for index, record in enumerate(records)
            if record["state"] == "valid"
        }
        count = len(values_by_index)
        mean = _stable_sum(list(values_by_index.values())) / Decimal(count)
        centered = {
            index: value - mean for index, value in values_by_index.items()
        }
        covariances: list[Decimal] = []
        pair_counts: list[int] = []
        for lag in range(HAC_MAX_LAG + 1):
            products = [
                centered[index] * centered[index - lag]
                for index in centered
                if index - lag in centered
            ]
            pair_counts.append(len(products))
            covariances.append(_stable_sum(products) / Decimal(count))
        weighted = [
            (Decimal(HAC_MAX_LAG + 1 - lag) / Decimal(HAC_MAX_LAG + 1))
            * covariances[lag]
            for lag in range(1, HAC_MAX_LAG + 1)
        ]
        omega = covariances[0] + Decimal(2) * _stable_sum(weighted)
    return omega, tuple(pair_counts)


def test_valid_inputs_compute_exact_gap_preserving_hac_and_closed_floors(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    expected_omega, expected_pairs = _expected_hac(inputs.beta_document)

    assert receipt.valid_beta_date_count == CALIBRATION_SESSION_COUNT - 4
    assert receipt.lag_pair_counts_0_through_20 == expected_pairs
    assert receipt.long_run_variance == expected_omega
    assert expected_pairs[0] == receipt.valid_beta_date_count
    assert expected_pairs[1] < receipt.valid_beta_date_count - 1
    assert receipt.q05_components_per_date == 3
    with localcontext(_fresh_context()) as active:
        active.clear_flags()
        expected_raw_dates = int(
            (
                expected_omega
                * Decimal(NORMAL_SUM_SQUARED)
                / ((Decimal(1) / Decimal(1000)) ** 2)
            ).to_integral_value(rounding=ROUND_CEILING)
        )
    assert receipt.raw_required_valid_dates == expected_raw_dates
    assert receipt.required_valid_dates >= MINIMUM_ABSOLUTE_FLOOR
    assert receipt.required_connected_components == max(
        MINIMUM_ABSOLUTE_FLOOR,
        receipt.required_valid_dates * receipt.q05_components_per_date,
    )
    assert receipt.fixed_h20_test_session_capacity == TEST_SESSION_CAPACITY
    assert receipt.disposition is ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
    assert module.require_loaded_power_calibration_receipt(receipt) is receipt


def test_hac_uses_valid_N_not_each_lag_pair_count(
    tmp_path: Path, parents: _Parents
):
    sessions = parents.admission.calibration_session_axis
    beta = _baseline_beta_document(
        sessions,
        missing=frozenset(range(30, 181, 10)),
        refused=frozenset(range(35, 186, 10)),
    )
    inputs = _write_authorized_inputs(tmp_path, parents, beta_document=beta)
    receipt = _compute(parents, inputs)
    expected_omega, expected_pairs = _expected_hac(beta)

    assert len(set(expected_pairs)) > 1
    assert receipt.lag_pair_counts_0_through_20 == expected_pairs
    assert receipt.long_run_variance == expected_omega


def test_decimal_context_is_fresh_and_does_not_leak_flags(
    tmp_path: Path, parents: _Parents
):
    original = getcontext().copy()
    try:
        ambient = getcontext()
        ambient.prec = 7
        ambient.rounding = ROUND_DOWN
        ambient.traps[InvalidOperation] = False
        ambient.flags[Inexact] = True
        before = ambient.copy()
        inputs = _write_authorized_inputs(tmp_path, parents)
        first = _compute(parents, inputs)
        after = getcontext().copy()
        assert after.prec == before.prec
        assert after.rounding == before.rounding
        assert after.traps == before.traps
        assert after.flags == before.flags

        ambient.prec = 31
        ambient.rounding = ROUND_CEILING
        ambient.clear_flags()
        second = _compute(parents, inputs)
        assert second.long_run_variance == first.long_run_variance
        assert second.raw_required_valid_dates == first.raw_required_valid_dates
        assert second.receipt_hash == first.receipt_hash
    finally:
        setcontext(original)


def test_stable_sum_signed_tie_break_survives_cancellation():
    magnitude = Decimal("9" * 49)
    residual = Decimal("0.6")
    values = (
        magnitude,
        magnitude,
        residual.copy_negate(),
        magnitude.copy_negate(),
    )
    with localcontext(_fresh_context()) as active:
        active.clear_flags()
        signed_tie_break = module._stable_sum(values)
        abs_only = Decimal(0)
        for value in sorted(values, key=abs):
            abs_only += value
        expected_signed = magnitude - residual
        expected_abs_only = magnitude - Decimal(1)
    assert signed_tie_break == expected_signed
    assert abs_only == expected_abs_only
    assert signed_tie_break != abs_only


def test_stable_sum_orders_more_than_context_precision_by_exact_magnitude():
    values = (
        Decimal("1E-52"),
        Decimal("-1." + "0" * 49 + "02"),
        Decimal("1." + "0" * 49 + "01"),
    )
    with localcontext(_fresh_context()) as active:
        active.clear_flags()
        exact_magnitude_order = module._stable_sum(values)
        context_rounded_order = Decimal(0)
        for value in sorted(values, key=lambda item: (abs(item), item)):
            context_rounded_order += value
    assert exact_magnitude_order == Decimal("-2E-51")
    assert context_rounded_order == Decimal("1E-51")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.update(extra="forbidden"),
        lambda raw: raw.pop("schema"),
        lambda raw: raw.update(schema="wrong-schema"),
        lambda raw: raw.update(records={}),
        lambda raw: raw["records"][0].update(extra="forbidden"),
        lambda raw: raw["records"][0].pop("state"),
        lambda raw: raw["records"][0].update(decision_session="2018-02-01"),
        lambda raw: raw["records"][0].update(state="unknown"),
        lambda raw: raw["records"][0].update(state="valid", beta_value=None),
        lambda raw: raw["records"][0].update(state="missing", beta_value="0"),
        lambda raw: raw["records"][0].update(state="refused", beta_value="0"),
        lambda raw: raw["records"].pop(),
        lambda raw: raw["records"].append(copy.deepcopy(raw["records"][-1])),
        lambda raw: raw["records"].reverse(),
    ],
)
def test_beta_content_schema_and_exact_483_axis_are_closed(
    tmp_path: Path, parents: _Parents, mutate
):
    baseline = _baseline_beta_document(parents.admission.calibration_session_axis)
    changed = copy.deepcopy(baseline)
    mutate(changed)
    inputs = _write_authorized_inputs(
        tmp_path,
        parents,
        beta_document=changed,
        beta_metadata_document=baseline,
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, inputs)


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        0,
        1,
        [],
        {},
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        "+0.001",
        "01",
        "-01",
        "1e-3",
        "1E-3",
        "0.0010",
        "1.",
        " 0.001",
        "0.001 ",
        "-0",
        "1" * (module.MAX_DECIMAL_TEXT_BYTES + 1),
        "",
    ],
)
def test_beta_values_require_one_canonical_finite_decimal_string(
    tmp_path: Path, parents: _Parents, value: object
):
    baseline = _baseline_beta_document(parents.admission.calibration_session_axis)
    changed = copy.deepcopy(baseline)
    changed["records"][0] = {
        "decision_session": changed["records"][0]["decision_session"],
        "state": "valid",
        "beta_value": value,
    }
    inputs = _write_authorized_inputs(
        tmp_path,
        parents,
        beta_document=changed,
        beta_metadata_document=baseline,
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, inputs)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.update(extra="forbidden"),
        lambda raw: raw.pop("schema"),
        lambda raw: raw.update(schema="wrong-schema"),
        lambda raw: raw.update(records={}),
        lambda raw: raw["records"][0].update(extra="forbidden"),
        lambda raw: raw["records"][0].pop("connected_component_count"),
        lambda raw: raw["records"][0].update(decision_session="2018-02-01"),
        lambda raw: raw["records"][0].update(connected_component_count=-1),
        lambda raw: raw["records"][0].update(connected_component_count=True),
        lambda raw: raw["records"][0].update(connected_component_count=1.0),
        lambda raw: raw["records"][0].update(connected_component_count="1"),
        lambda raw: raw["records"].pop(),
        lambda raw: raw["records"].append(copy.deepcopy(raw["records"][-1])),
        lambda raw: raw["records"].reverse(),
    ],
)
def test_component_content_schema_counts_and_exact_483_axis_are_closed(
    tmp_path: Path, parents: _Parents, mutate
):
    baseline = _baseline_component_document(
        parents.admission.calibration_session_axis
    )
    changed = copy.deepcopy(baseline)
    mutate(changed)
    inputs = _write_authorized_inputs(
        tmp_path,
        parents,
        component_document=changed,
        component_metadata_document=baseline,
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, inputs)


def test_component_q05_includes_honest_zero_sessions(
    tmp_path: Path, parents: _Parents
):
    sessions = parents.admission.calibration_session_axis
    twenty_four_zeroes = _baseline_component_document(sessions, zero_count=24)
    twenty_five_zeroes = _baseline_component_document(sessions, zero_count=25)
    first = _compute(
        parents,
        _write_authorized_inputs(
            tmp_path / "rank-25-is-three",
            parents,
            component_document=twenty_four_zeroes,
        ),
    )
    second = _compute(
        parents,
        _write_authorized_inputs(
            tmp_path / "rank-25-is-zero",
            parents,
            component_document=twenty_five_zeroes,
        ),
    )

    assert first.q05_components_per_date == 3
    assert second.q05_components_per_date == 0
    assert second.required_connected_components == MINIMUM_ABSOLUTE_FLOOR


@pytest.mark.parametrize(
    ("payload_factory", "target"),
    [
        (lambda payload: b"\xef\xbb\xbf" + payload, "beta"),
        (lambda payload: payload[:-1], "beta"),
        (lambda payload: payload.replace(b'"schema"', b'"schema"', 1) + b" ", "beta"),
        (lambda payload: b"\xff" + payload, "beta"),
        (lambda payload: b"[]\n", "beta"),
        (lambda payload: b"null\n", "component"),
    ],
)
def test_input_files_require_strict_canonical_utf8_json(
    tmp_path: Path, parents: _Parents, payload_factory, target: str
):
    beta = _baseline_beta_document(parents.admission.calibration_session_axis)
    component = _baseline_component_document(parents.admission.calibration_session_axis)
    source = _render(beta if target == "beta" else component)
    payload = payload_factory(source)
    inputs = _write_authorized_inputs(
        tmp_path,
        parents,
        beta_document=beta,
        component_document=component,
        beta_payload=payload if target == "beta" else None,
        component_payload=payload if target == "component" else None,
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, inputs)


def test_duplicate_json_keys_and_binary_float_tokens_are_refused(
    tmp_path: Path, parents: _Parents
):
    beta = _baseline_beta_document(parents.admission.calibration_session_axis)
    component = _baseline_component_document(parents.admission.calibration_session_axis)
    beta_payload = _render(beta).replace(
        b'{\n      "beta_value":',
        b'{\n      "beta_value": "0",\n      "beta_value":',
        1,
    )
    duplicate = _write_authorized_inputs(
        tmp_path / "duplicate",
        parents,
        beta_document=beta,
        component_document=component,
        beta_payload=beta_payload,
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, duplicate)

    float_payload = _render(beta).replace(b'"-0.000241"', b"0.001", 1)
    floating = _write_authorized_inputs(
        tmp_path / "float",
        parents,
        beta_document=beta,
        component_document=component,
        beta_payload=float_payload,
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, floating)


@pytest.mark.parametrize(
    ("payload", "secret_token"),
    [
        (b'{"value":928374650123.456789}\n', "928374650123.456789"),
        (b'{"value":NaN}\n', "NaN"),
        (
            b'{"distinctive-private-field":1,"distinctive-private-field":2}\n',
            "distinctive-private-field",
        ),
    ],
)
def test_strict_parser_refusals_never_echo_numeric_or_key_tokens(
    payload: bytes, secret_token: str
):
    with pytest.raises(module.PowerCalibrationReceiptError) as caught:
        module._parse(payload, "opaque calibration input")
    assert secret_token not in str(caught.value)


@pytest.mark.parametrize(
    ("payload", "secret_token"),
    [
        (b'{"private-value":"918273645","unterminated":', "918273645"),
        (b'{"private-value":"81726354"}\xff\n', "81726354"),
    ],
)
def test_decoder_refusals_do_not_chain_payload_bearing_exceptions(
    payload: bytes, secret_token: str
):
    with pytest.raises(module.PowerCalibrationReceiptError) as caught:
        module._parse(payload, "opaque calibration input")
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert secret_token not in str(caught.value)
    assert secret_token not in "".join(
        traceback.format_exception(caught.value)
    )


def test_both_raw_artifact_identities_are_checked_before_either_parser(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    inputs.component_path.write_bytes(inputs.component_path.read_bytes() + b" ")
    parsed: list[str] = []
    original = module._parse

    def observe(payload, name):
        if name in {"date-beta input", "component-count input"}:
            parsed.append(name)
        return original(payload, name)

    monkeypatch.setattr(module, "_parse", observe)
    with pytest.raises(module.PowerCalibrationReceiptError, match="B2 manifest"):
        _compute(parents, inputs)
    assert parsed == []


def test_input_manifest_semantic_artifact_size_and_role_bindings_are_exact(
    tmp_path: Path, parents: _Parents
):
    mutations = (
        lambda descriptors: descriptors["date_level_beta_series"].update(
            content_sha256="0" * 64
        ),
        lambda descriptors: descriptors["date_level_beta_series"].update(
            artifact_sha256="0" * 64
        ),
        lambda descriptors: descriptors["date_level_beta_series"].update(
            byte_count=descriptors["date_level_beta_series"]["byte_count"] + 1
        ),
        lambda descriptors: descriptors["component_count_census"].update(
            content_sha256="0" * 64
        ),
        lambda descriptors: descriptors["component_count_census"].update(
            artifact_sha256="0" * 64
        ),
        lambda descriptors: descriptors["component_count_census"].update(
            byte_count=descriptors["component_count_census"]["byte_count"] + 1
        ),
    )
    for index, mutate in enumerate(mutations):
        inputs = _write_authorized_inputs(
            tmp_path / str(index), parents, descriptor_mutate=mutate
        )
        with pytest.raises(module.PowerCalibrationReceiptError):
            _compute(parents, inputs)


def test_swapped_input_paths_are_refused(tmp_path: Path, parents: _Parents):
    inputs = _write_authorized_inputs(tmp_path, parents)
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.compute_power_calibration_receipt(
            parents.content_contract,
            inputs.candidate,
            input_authority=inputs.input_authority,
            beta_series_path=inputs.component_path,
            component_count_path=inputs.beta_path,
        )


def test_too_few_valid_dates_and_nonpositive_hac_refuse_without_fallback(
    tmp_path: Path, parents: _Parents
):
    sessions = parents.admission.calibration_session_axis
    too_few = _baseline_beta_document(
        sessions,
        missing=frozenset(range(49, CALIBRATION_SESSION_COUNT)),
        refused=frozenset(),
    )
    few_inputs = _write_authorized_inputs(
        tmp_path / "few", parents, beta_document=too_few
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, few_inputs)

    constant = _baseline_beta_document(
        sessions,
        missing=frozenset(),
        refused=frozenset(),
        multiplier=Decimal(0),
    )
    constant_inputs = _write_authorized_inputs(
        tmp_path / "constant", parents, beta_document=constant
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, constant_inputs)


def test_every_lag_requires_an_exact_axis_pair(tmp_path: Path, parents: _Parents):
    sessions = parents.admission.calibration_session_axis
    odd_positions_missing = _baseline_beta_document(
        sessions,
        missing=frozenset(range(1, CALIBRATION_SESSION_COUNT, 2)),
        refused=frozenset(),
    )
    assert sum(
        record["state"] == "valid" for record in odd_positions_missing["records"]
    ) > MINIMUM_ABSOLUTE_FLOOR
    inputs = _write_authorized_inputs(
        tmp_path, parents, beta_document=odd_positions_missing
    )
    with pytest.raises(module.PowerCalibrationReceiptError, match="lag"):
        _compute(parents, inputs)


def _beta_document_for_raw_date_requirement(
    sessions: tuple[str, ...], target_raw_dates: int
) -> dict[str, object]:
    unit = _baseline_beta_document(
        sessions,
        missing=frozenset(),
        refused=frozenset(),
        multiplier=Decimal(1),
    )
    unit_omega, _ = _expected_hac(unit)
    context = _fresh_context()
    with localcontext(context) as active:
        active.clear_flags()
        effect_squared = (Decimal(1) / Decimal(1000)) ** 2
        midpoint_planned_dates = Decimal(target_raw_dates) - Decimal("0.5")
        target_omega = (
            midpoint_planned_dates
            * effect_squared
            / Decimal(NORMAL_SUM_SQUARED)
        )
        multiplier = (target_omega / unit_omega).sqrt()
    return _baseline_beta_document(
        sessions,
        missing=frozenset(),
        refused=frozenset(),
        multiplier=multiplier,
    )


@pytest.mark.parametrize(
    ("raw_dates", "disposition"),
    [
        (
            TEST_SESSION_CAPACITY,
            ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT,
        ),
        (
            TEST_SESSION_CAPACITY + 1,
            ProvisionalPowerDisposition.UNDERPOWERED_FIXED_DESIGN_NO_LAUNCH,
        ),
    ],
)
def test_fixed_capacity_boundary_is_inclusive_only_at_1388(
    tmp_path: Path,
    parents: _Parents,
    raw_dates: int,
    disposition: ProvisionalPowerDisposition,
):
    beta = _beta_document_for_raw_date_requirement(
        parents.admission.calibration_session_axis, raw_dates
    )
    receipt = _compute(
        parents,
        _write_authorized_inputs(tmp_path, parents, beta_document=beta),
    )
    assert receipt.raw_required_valid_dates == raw_dates
    assert receipt.required_valid_dates == raw_dates
    assert receipt.disposition is disposition


def test_checked_in_content_contract_is_exact_canonical_content_addressed_bytes(
    parents: _Parents,
):
    path = SPEC_ROOT / CONTENT_CONTRACT_FILENAME
    payload = path.read_bytes()
    assert payload == module.render_expected_power_calibration_input_content_contract().encode(
        "utf-8"
    )
    assert hashlib.sha256(payload).hexdigest() == module.CONTENT_CONTRACT_ARTIFACT_SHA256
    raw = json.loads(payload)
    declared_id = raw["content_contract_id"]
    declared_hash = raw["content_contract_hash"]
    raw["content_contract_id"] = None
    raw["content_contract_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    assert declared_hash == digest
    assert declared_id == module.CONTENT_CONTRACT_ID_PREFIX + digest[:16]
    assert module.require_loaded_power_calibration_input_content_contract(
        parents.content_contract
    ) is parents.content_contract


def test_content_contract_loader_uses_one_authenticated_parent_snapshot(
    monkeypatch: pytest.MonkeyPatch,
):
    protocol = _load_protocol()
    input_schema = b2_helpers._load_input_schema()
    overlay = b2_helpers._load_overlay()
    admission = load_power_calibration_manifest_admission(
        SPEC_ROOT / b2_helpers.ADMISSION_FILENAME,
        input_schema=input_schema,
        multiplicity_overlay=overlay,
    )
    original_axis = protocol.calibration_session_axis
    forged_axis = ("1900-01-01", *original_axis[1:])
    original_revalidate = module._revalidate
    contract_revalidations = 0

    def mutate_after_final_revalidation(path, payload, name, **kwargs):
        nonlocal contract_revalidations
        result = original_revalidate(path, payload, name, **kwargs)
        if name == "input-content contract":
            contract_revalidations += 1
            if contract_revalidations == 2:
                object.__setattr__(
                    protocol, "calibration_session_axis", forged_axis
                )
        return result

    monkeypatch.setattr(module, "_revalidate", mutate_after_final_revalidation)
    try:
        loaded = module.load_power_calibration_input_content_contract(
            SPEC_ROOT / CONTENT_CONTRACT_FILENAME,
            power_protocol=protocol,
            input_schema=input_schema,
            manifest_admission=admission,
            multiplicity_overlay=overlay,
        )
    finally:
        object.__setattr__(protocol, "calibration_session_axis", original_axis)
    assert contract_revalidations == 2
    assert loaded.calibration_session_axis == original_axis
    assert module.require_loaded_power_calibration_input_content_contract(
        loaded
    ) is loaded

    object.__setattr__(protocol, "calibration_session_axis", forged_axis)
    try:
        with pytest.raises(module.PowerCalibrationReceiptError):
            module.require_loaded_power_calibration_input_content_contract(
                loaded
            )
    finally:
        object.__setattr__(protocol, "calibration_session_axis", original_axis)


def test_committed_production_truth_and_operation_gates_are_zero_access(
    parents: _Parents,
):
    boundary = parents.content_contract.definition["authority_boundary"]
    assert module.PRODUCTION_TRUTH_EVIDENCE_OPENER_IMPLEMENTED is False
    assert module.PRODUCTION_TRUTH_APPROVAL_ARTIFACT_SHA256 is None
    assert module.PRODUCTION_INPUT_AUTHORITY_ARTIFACT_SHA256 is None
    assert boundary["production_truth_evidence_opener_implemented"] is False
    assert boundary["truth_aggregate_pin_alone_grants_access"] is False
    assert boundary["committed_production_truth_approval_artifact_sha256"] is None
    assert boundary["committed_input_operation_authority_artifact_sha256"] is None
    assert boundary["caller_rendered_owner_provenance_grants_access"] is False


def test_structural_candidate_and_owner_strings_refuse_before_input_open(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    for claim in module.PRODUCTION_TRUTH_CLAIMS:
        assert getattr(inputs.candidate, claim) is False

    opened: list[str] = []
    original = module._read_stable_regular

    def observe(path, name, **kwargs):
        opened.append(name)
        return original(path, name, **kwargs)

    monkeypatch.setattr(module, "_read_stable_regular", observe)
    with pytest.raises(
        module.PowerCalibrationReceiptError,
        match="truth evidence opener",
    ):
        module.render_power_calibration_input_authority(
            parents.content_contract,
            inputs.candidate,
            production_truth_approval_path=inputs.truth_approval_path,
            owner_authorization_id="caller-rendered-owner-claim",
            owner_authorization_evidence_sha256="7" * 64,
            authorized_at_utc=AUTHORIZED_AT_UTC,
        )
    assert "date-beta input" not in opened
    assert "component-count input" not in opened

    with _fixture_only_truth_gate(inputs.truth_approval_path):
        rendered = module.render_power_calibration_input_authority(
            parents.content_contract,
            inputs.candidate,
            production_truth_approval_path=inputs.truth_approval_path,
            owner_authorization_id="caller-rendered-owner-claim",
            owner_authorization_evidence_sha256="7" * 64,
            authorized_at_utc=AUTHORIZED_AT_UTC,
        )
    authority_path = tmp_path / "caller-rendered-authority.json"
    authority_path.write_bytes(rendered.encode("utf-8"))  # exact LF bytes on every host
    with pytest.raises(
        module.PowerCalibrationReceiptError,
        match="operation authority is pinned",
    ):
        module.load_power_calibration_input_authority(
            authority_path,
            content_contract=parents.content_contract,
            manifest_candidate=inputs.candidate,
            production_truth_approval_path=inputs.truth_approval_path,
        )
    assert "date-beta input" not in opened
    assert "component-count input" not in opened


def test_truth_aggregate_requires_every_exact_positive_claim(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    raw = module._truth_approval_document(
        inputs.candidate,
        review_id=FIXTURE_TRUTH_REVIEW_ID,
        review_evidence_sha256=FIXTURE_TRUTH_REVIEW_EVIDENCE_SHA256,
        reviewed_at_utc=FIXTURE_TRUTH_REVIEWED_AT_UTC,
    )
    raw["authenticated_truth_claims"]["vintage_proven"] = False
    changed_path = tmp_path / "FIXTURE_ONLY-negative-truth.json"
    changed_path.write_bytes(_render(raw))
    with _fixture_only_truth_gate(changed_path):
        with pytest.raises(
            module.PowerCalibrationReceiptError,
            match="truth approval content changed",
        ):
            module.render_power_calibration_input_authority(
                parents.content_contract,
                inputs.candidate,
                production_truth_approval_path=changed_path,
                owner_authorization_id=AUTHORIZATION_ID,
                owner_authorization_evidence_sha256=AUTHORIZATION_EVIDENCE_SHA256,
                authorized_at_utc=AUTHORIZED_AT_UTC,
            )


def test_truth_document_uses_one_candidate_snapshot_during_transient_mutation(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    candidate = inputs.candidate
    original_manifest_id = candidate.manifest_id
    original_builder = module._truth_approval_document_from_snapshot
    mutated = False

    def mutate_live_candidate(snapshot, **kwargs):
        nonlocal mutated
        object.__setattr__(candidate, "manifest_id", "forged-transient-manifest")
        mutated = True
        try:
            return original_builder(snapshot, **kwargs)
        finally:
            object.__setattr__(candidate, "manifest_id", original_manifest_id)

    monkeypatch.setattr(
        module,
        "_truth_approval_document_from_snapshot",
        mutate_live_candidate,
    )
    raw = module._truth_approval_document(
        candidate,
        review_id=FIXTURE_TRUTH_REVIEW_ID,
        review_evidence_sha256=FIXTURE_TRUTH_REVIEW_EVIDENCE_SHA256,
        reviewed_at_utc=FIXTURE_TRUTH_REVIEWED_AT_UTC,
    )
    assert mutated is True
    assert raw["production_manifest_binding"]["artifact_id"] == (
        original_manifest_id
    )
    assert candidate.manifest_id == original_manifest_id


def _walk_keys(value: object) -> set[str]:
    if isinstance(value, dict | MappingProxyType):
        return set(value) | {
            key
            for item in value.values()
            for key in _walk_keys(item)
        }
    if isinstance(value, list | tuple):
        return {key for item in value for key in _walk_keys(item)}
    return set()


def _thaw(value: object) -> object:
    if isinstance(value, dict | MappingProxyType):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_thaw(item) for item in value]
    return value


def test_receipt_is_content_addressed_and_has_only_closed_outputs_and_bindings(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    raw = _thaw(receipt.definition)
    assert set(raw) == set(module.RECEIPT_ROOT_FIELDS)
    assert raw["schema"] == module.RECEIPT_SCHEMA
    assert raw["status"] == module.RECEIPT_STATUS
    assert raw["authority"] == module.RECEIPT_AUTHORITY
    required = raw["required_receipt_fields"]
    assert tuple(required) == module.REQUIRED_RECEIPT_FIELDS
    assert required == {
        "protocol_id": receipt.protocol_id,
        "protocol_hash": receipt.protocol_hash,
        "calibration_input_manifest_sha256": receipt.manifest_artifact_sha256,
        "valid_beta_date_count": receipt.valid_beta_date_count,
        "lag_pair_counts_0_through_20": list(
            receipt.lag_pair_counts_0_through_20
        ),
        "long_run_variance": _decimal_text(receipt.long_run_variance),
        "component_count_census_sha256": receipt.component_count_census_sha256,
        "component_count_census_session_count": (
            receipt.component_count_census_session_count
        ),
        "q05_components_per_date": receipt.q05_components_per_date,
        "raw_required_valid_dates": receipt.raw_required_valid_dates,
        "required_valid_dates": receipt.required_valid_dates,
        "required_connected_components": receipt.required_connected_components,
        "fixed_capacity_disposition": receipt.disposition.value,
    }
    declared_id = raw["receipt_id"]
    declared_hash = raw["receipt_hash"]
    raw["receipt_id"] = None
    raw["receipt_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    assert declared_hash == digest
    assert declared_id == module.RECEIPT_ID_PREFIX + digest[:16]

    forbidden = {
        "records",
        "beta_value",
        "date_level_beta_values",
        "beta_mean",
        "centered_values",
        "autocovariances",
        "gamma",
        "return",
        "returns",
        "outcome",
        "outcomes",
        "p_value",
        "information_coefficient",
        "pnl",
        "gate_result",
        "strategy_performance",
    }
    assert _walk_keys(receipt.definition).isdisjoint(forbidden)
    rendered = _canonical(raw).decode("utf-8").lower()
    for record in inputs.beta_document["records"]:
        if record["beta_value"] not in (None, "0"):
            assert f'"{record["beta_value"]}"' not in rendered


def test_receipt_binds_exact_contract_manifest_authority_and_input_identities(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    metadata = inputs.candidate.definition["manifest"]["input_artifacts"]
    assert receipt.protocol_id == parents.protocol.protocol_id
    assert receipt.protocol_hash == parents.protocol.protocol_hash
    assert receipt.content_contract_id == parents.content_contract.content_contract_id
    assert receipt.content_contract_hash == parents.content_contract.content_contract_hash
    assert receipt.manifest_id == inputs.candidate.manifest_id
    assert receipt.manifest_content_sha256 == inputs.candidate.manifest_content_sha256
    assert receipt.manifest_artifact_sha256 == inputs.candidate.manifest_artifact_sha256
    assert (
        receipt.beta_input_id,
        receipt.beta_input_content_sha256,
        receipt.beta_input_artifact_sha256,
    ) == (
        metadata[0]["artifact_id"],
        metadata[0]["content_sha256"],
        metadata[0]["artifact_sha256"],
    )
    assert (
        receipt.component_input_id,
        receipt.component_input_content_sha256,
        receipt.component_input_artifact_sha256,
    ) == (
        metadata[1]["artifact_id"],
        metadata[1]["content_sha256"],
        metadata[1]["artifact_sha256"],
    )
    authority_binding = receipt.definition["input_authority_binding"]
    assert authority_binding["authority_id"] == inputs.input_authority.authority_id
    assert authority_binding["authority_hash"] == inputs.input_authority.authority_hash
    assert authority_binding["owner_authorization_id"] == AUTHORIZATION_ID
    assert (
        authority_binding["owner_authorization_evidence_sha256"]
        == AUTHORIZATION_EVIDENCE_SHA256
    )


def test_content_contract_authority_and_receipt_keep_all_adjacent_actions_closed(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    assert all(value is False for value in parents.content_contract.capabilities.values())
    for owner in (parents.content_contract, inputs.input_authority, receipt):
        assert owner.outcome_access_available is False
        assert owner.qc_action_available is False
    assert parents.content_contract.input_access_available is False
    assert receipt.launch_authorized is False
    operations = inputs.input_authority.definition["authorized_operations"]
    assert inputs.input_authority.input_read_authorized is True
    assert inputs.input_authority.nuisance_compute_authorized is True
    assert inputs.input_authority.closed_receipt_compute_authorized is True
    for claim in module.PRODUCTION_TRUTH_CLAIMS:
        assert getattr(inputs.input_authority, claim) is True
    assert receipt.receipt_content_authenticated is True
    assert {name for name, allowed in operations.items() if allowed} == {
        "calibration_input_read",
        "nuisance_calibration_compute",
        "closed_numeric_receipt_compute",
    }
    assert operations["source_provider_read"] is False
    assert operations["outcome_read"] is False
    assert operations["qc_upload"] is False
    assert operations["qc_compile"] is False
    assert operations["qc_launch"] is False


def test_authority_renderer_alone_does_not_grant_compute(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    with _fixture_only_truth_gate(inputs.truth_approval_path):
        rendered = module.render_power_calibration_input_authority(
            parents.content_contract,
            inputs.candidate,
            production_truth_approval_path=inputs.truth_approval_path,
            owner_authorization_id=AUTHORIZATION_ID,
            owner_authorization_evidence_sha256=AUTHORIZATION_EVIDENCE_SHA256,
            authorized_at_utc=AUTHORIZED_AT_UTC,
        )
    assert isinstance(rendered, str)
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.compute_power_calibration_receipt(
            parents.content_contract,
            inputs.candidate,
            input_authority=rendered,
            beta_series_path=inputs.beta_path,
            component_count_path=inputs.component_path,
        )


@pytest.mark.parametrize(
    "owner",
    [
        module.PowerCalibrationInputContentContract,
        module.PowerCalibrationInputAuthority,
        module.PowerCalibrationReceipt,
    ],
)
def test_authority_bearing_types_cannot_be_constructed(owner):
    with pytest.raises(TypeError):
        owner()


def test_authority_objects_reject_copy_replace_pickle_subclass_and_mutation(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    checks = (
        (
            parents.content_contract,
            module.require_loaded_power_calibration_input_content_contract,
        ),
        (
            inputs.input_authority,
            module.require_loaded_power_calibration_input_authority,
        ),
        (receipt, module.require_loaded_power_calibration_receipt),
    )
    for value, checker in checks:
        with pytest.raises(TypeError):
            dataclasses.replace(value)
        copied = copy.copy(value)
        with pytest.raises(module.PowerCalibrationReceiptError):
            checker(copied)
        try:
            restored = pickle.loads(pickle.dumps(value))
        except (TypeError, pickle.PickleError):
            pass
        else:
            with pytest.raises(module.PowerCalibrationReceiptError):
                checker(restored)

    copied_authority = copy.copy(inputs.input_authority)
    for name in (
        "input_read_authorized",
        "nuisance_compute_authorized",
        "closed_receipt_compute_authorized",
    ):
        with pytest.raises(module.PowerCalibrationReceiptError):
            getattr(copied_authority, name)
    copied_receipt = copy.copy(receipt)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _ = copied_receipt.receipt_content_authenticated

    class ReceiptSubclass(module.PowerCalibrationReceipt):
        pass

    forged_subclass = object.__new__(ReceiptSubclass)
    object.__setattr__(forged_subclass, "_authority", module._LOADED_RECEIPT)
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.require_loaded_power_calibration_receipt(forged_subclass)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _ = forged_subclass.receipt_content_authenticated

    forged_authority = object.__new__(module.PowerCalibrationInputAuthority)
    object.__setattr__(forged_authority, "_authority", module._LOADED_INPUT_AUTHORITY)
    for name in (
        "input_read_authorized",
        "nuisance_compute_authorized",
        "closed_receipt_compute_authorized",
    ):
        with pytest.raises(module.PowerCalibrationReceiptError):
            getattr(forged_authority, name)

    original_authority_id = inputs.input_authority.authority_id
    object.__setattr__(inputs.input_authority, "authority_id", "forged-authority")
    try:
        for name in (
            "input_read_authorized",
            "nuisance_compute_authorized",
            "closed_receipt_compute_authorized",
        ):
            with pytest.raises(module.PowerCalibrationReceiptError):
                getattr(inputs.input_authority, name)
    finally:
        object.__setattr__(
            inputs.input_authority, "authority_id", original_authority_id
        )

    original = receipt.receipt_id
    object.__setattr__(receipt, "receipt_id", "arv2-stock-power-calibration-receipt-forged")
    try:
        with pytest.raises(module.PowerCalibrationReceiptError):
            _ = receipt.receipt_content_authenticated
    finally:
        object.__setattr__(receipt, "receipt_id", original)
    assert module.require_loaded_power_calibration_receipt(receipt) is receipt


def test_nested_authority_state_is_immutable_and_extra_non_string_keys_refuse(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    with pytest.raises(TypeError):
        receipt.definition["status"] = "forged"
    with pytest.raises(TypeError):
        receipt.definition["required_receipt_fields"]["protocol_id"] = "forged"

    class SpoofedStr(str):
        pass

    original = receipt.definition
    changed = dict(original)
    changed[SpoofedStr("unfingerprinted_extra")] = "forged"
    object.__setattr__(receipt, "definition", MappingProxyType(changed))
    try:
        with pytest.raises(module.PowerCalibrationReceiptError):
            module.require_loaded_power_calibration_receipt(receipt)
    finally:
        object.__setattr__(receipt, "definition", original)


def test_all_receipt_authorities_pin_every_exact_container_root(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    cases = (
        (
            parents.content_contract,
            module.require_loaded_power_calibration_input_content_contract,
            module._CONTENT_CONTRACT_CONTAINER_FIELDS,
        ),
        (
            inputs.input_authority,
            module.require_loaded_power_calibration_input_authority,
            module._INPUT_AUTHORITY_CONTAINER_FIELDS,
        ),
        (
            receipt,
            module.require_loaded_power_calibration_receipt,
            module._POWER_RECEIPT_CONTAINER_FIELDS,
        ),
    )
    for value, checker, field_names in cases:
        for field_name in field_names:
            original = getattr(value, field_name)
            replacement = _equal_distinct_container(original)
            assert replacement == original
            object.__setattr__(value, field_name, replacement)
            try:
                with pytest.raises(
                    module.PowerCalibrationReceiptError,
                    match="container roots changed",
                ):
                    checker(value)
            finally:
                object.__setattr__(value, field_name, original)
            assert checker(value) is value


def test_receipt_hostile_mapping_proxies_refuse_before_fingerprint_traversal(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    cases = (
        (
            parents.content_contract,
            module.require_loaded_power_calibration_input_content_contract,
            "capabilities",
        ),
        (
            inputs.input_authority,
            module.require_loaded_power_calibration_input_authority,
            "definition",
        ),
        (
            receipt,
            module.require_loaded_power_calibration_receipt,
            "definition",
        ),
    )
    for value, checker, field_name in cases:
        original = getattr(value, field_name)
        target = next(iter(original))
        honest_item = original[target]
        forged = not honest_item if type(honest_item) is bool else None
        if honest_item is None:
            forged = "forged-after-authentication"
        assert forged != honest_item

        probe_backing = _FingerprintThenForgeMapping(
            original, target=target, forged=forged
        )
        probe = MappingProxyType(probe_backing)
        assert module._fingerprint(probe) == module._fingerprint(original)
        assert probe[target] == forged

        attack_backing = _FingerprintThenForgeMapping(
            original, target=target, forged=forged
        )
        object.__setattr__(value, field_name, MappingProxyType(attack_backing))
        try:
            with pytest.raises(
                module.PowerCalibrationReceiptError,
                match="container roots changed",
            ):
                checker(value)
            assert attack_backing.touches == 0
        finally:
            object.__setattr__(value, field_name, original)
        assert checker(value) is value


def test_receipt_registry_authority_is_removed_after_collection(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    identity = id(receipt)
    reference = weakref.ref(receipt)
    assert identity in module._POWER_RECEIPT_AUTHORITIES
    del receipt
    gc.collect()
    assert reference() is None
    assert identity not in module._POWER_RECEIPT_AUTHORITIES


def _strong_registry_values(value: object):
    yield value
    if isinstance(value, weakref.ReferenceType):
        return
    if dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            yield from _strong_registry_values(getattr(value, field.name))
    elif isinstance(value, dict | MappingProxyType):
        for key, item in value.items():
            yield from _strong_registry_values(key)
            yield from _strong_registry_values(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strong_registry_values(item)


def test_receipt_registry_retains_only_input_paths_digests_sizes_and_weak_parents(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    record = module._POWER_RECEIPT_AUTHORITIES[id(receipt)]
    assert isinstance(record.content_contract, weakref.ReferenceType)
    assert isinstance(record.manifest_candidate, weakref.ReferenceType)
    assert isinstance(record.input_authority, weakref.ReferenceType)
    assert record.beta_artifact.path == inputs.beta_path.resolve()
    assert record.component_artifact.path == inputs.component_path.resolve()
    assert record.beta_artifact.byte_count == inputs.beta_path.stat().st_size
    assert record.component_artifact.byte_count == inputs.component_path.stat().st_size
    retained = tuple(_strong_registry_values(record))
    assert not any(type(value) is bytes for value in retained)
    assert not any(type(value) is tuple and len(value) == CALIBRATION_SESSION_COUNT for value in retained)
    assert not hasattr(record, "beta_payload")
    assert not hasattr(record, "component_payload")

    opened: list[str] = []
    original = module._read_stable_regular

    def observe(path, name, **kwargs):
        opened.append(name)
        return original(path, name, **kwargs)

    monkeypatch.setattr(module, "_read_stable_regular", observe)
    assert module.require_loaded_power_calibration_receipt(receipt) is receipt
    assert opened.count("date-beta input") == 2
    assert opened.count("component-count input") == 2
    assert not any(
        type(value) is bytes
        for value in _strong_registry_values(
            module._POWER_RECEIPT_AUTHORITIES[id(receipt)]
        )
    )


def test_receipt_reauthentication_refuses_changed_input_or_authority_bytes(
    tmp_path: Path, parents: _Parents
):
    first = _write_authorized_inputs(tmp_path / "input", parents)
    receipt = _compute(parents, first)
    first.beta_path.write_bytes(first.beta_path.read_bytes() + b" ")
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.require_loaded_power_calibration_receipt(receipt)

    second = _write_authorized_inputs(tmp_path / "authority", parents)
    second.input_authority.definition
    authority_record = module._INPUT_AUTHORITIES[id(second.input_authority)]
    authority_path = authority_record[1]
    authority_path.write_bytes(authority_path.read_bytes() + b" ")
    for name in (
        "input_read_authorized",
        "nuisance_compute_authorized",
        "closed_receipt_compute_authorized",
    ):
        with pytest.raises(module.PowerCalibrationReceiptError):
            getattr(second.input_authority, name)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, second)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="host has no symlink support")
def test_input_paths_must_remain_regular_nonsymlink_files(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    target = tmp_path / "real-beta.json"
    target.write_bytes(inputs.beta_path.read_bytes())
    inputs.beta_path.unlink()
    _symlink_or_skip(inputs.beta_path, target)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, inputs)


def test_input_path_through_a_junctioned_ancestor_refuses(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path / "real", parents)
    linked = tmp_path / "linked"
    _junction_or_skip(linked, inputs.beta_path.parent)
    junction_inputs = dataclasses.replace(
        inputs,
        beta_path=linked / inputs.beta_path.name,
    )
    with pytest.raises(module.PowerCalibrationReceiptError, match="link"):
        _compute(parents, junction_inputs)


def test_missing_directory_and_oversized_input_paths_refuse(
    tmp_path: Path, parents: _Parents
):
    missing = _write_authorized_inputs(tmp_path / "missing", parents)
    missing.beta_path.unlink()
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, missing)

    directory = _write_authorized_inputs(tmp_path / "directory", parents)
    directory.beta_path.unlink()
    directory.beta_path.mkdir()
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, directory)

    oversized = _write_authorized_inputs(tmp_path / "oversized", parents)
    with oversized.beta_path.open("wb") as handle:
        handle.truncate(module.MAX_INPUT_ARTIFACT_BYTES + 1)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, oversized)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="host has no FIFO support")
def test_fifo_input_refuses_without_blocking(tmp_path: Path, parents: _Parents):
    inputs = _write_authorized_inputs(tmp_path, parents)
    inputs.beta_path.unlink()
    os.mkfifo(inputs.beta_path)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, inputs)


def test_exactly_fifty_consecutive_valid_dates_are_admitted(
    tmp_path: Path, parents: _Parents
):
    sessions = parents.admission.calibration_session_axis
    beta = _baseline_beta_document(
        sessions,
        missing=frozenset(range(MINIMUM_ABSOLUTE_FLOOR, CALIBRATION_SESSION_COUNT)),
        refused=frozenset(),
    )
    receipt = _compute(
        parents,
        _write_authorized_inputs(tmp_path, parents, beta_document=beta),
    )
    assert receipt.valid_beta_date_count == MINIMUM_ABSOLUTE_FLOOR
    assert receipt.lag_pair_counts_0_through_20 == tuple(
        MINIMUM_ABSOLUTE_FLOOR - lag for lag in range(HAC_MAX_LAG + 1)
    )


def test_input_change_during_postcompute_revalidation_is_detected(
    tmp_path: Path, parents: _Parents, monkeypatch: pytest.MonkeyPatch
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    original = module._revalidate
    changed = False

    def race(path, payload, name, **kwargs):
        nonlocal changed
        if name == "date-beta input" and not changed:
            changed = True
            path.write_bytes(payload + b" ")
        return original(path, payload, name, **kwargs)

    monkeypatch.setattr(module, "_revalidate", race)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _compute(parents, inputs)
    assert changed is True


@pytest.mark.parametrize(
    ("owner_name", "field_name", "receipt_section", "receipt_field"),
    [
        (
            "candidate",
            "manifest_artifact_sha256",
            "required_receipt_fields",
            "calibration_input_manifest_sha256",
        ),
        (
            "authority",
            "authority_id",
            "input_authority_binding",
            "authority_id",
        ),
        (
            "contract",
            "content_contract_id",
            "content_contract_binding",
            "artifact_id",
        ),
    ],
)
def test_transient_parent_mutation_cannot_launder_receipt_construction(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
    owner_name: str,
    field_name: str,
    receipt_section: str,
    receipt_field: str,
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    owners = {
        "candidate": inputs.candidate,
        "authority": inputs.input_authority,
        "contract": parents.content_contract,
    }
    owner = owners[owner_name]
    original_value = getattr(owner, field_name)
    forged = "f" * 64 if field_name.endswith("sha256") else "forged-transient-id"
    original_loader = module._load_beta_series
    original_revalidate = module._revalidate
    mutated = False

    def mutate_after_snapshot(payload, metadata, sessions):
        nonlocal mutated
        result = original_loader(payload, metadata, sessions)
        object.__setattr__(owner, field_name, forged)
        mutated = True
        return result

    def restore_before_final_auth(path, payload, name, **kwargs):
        if mutated and getattr(owner, field_name) == forged:
            object.__setattr__(owner, field_name, original_value)
        return original_revalidate(path, payload, name, **kwargs)

    monkeypatch.setattr(module, "_load_beta_series", mutate_after_snapshot)
    monkeypatch.setattr(module, "_revalidate", restore_before_final_auth)
    receipt = _compute(parents, inputs)
    assert mutated is True
    assert getattr(owner, field_name) == original_value
    assert receipt.definition[receipt_section][receipt_field] == original_value


def test_final_input_revalidation_catches_mutation_during_parent_reauth(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    original = module.require_loaded_power_calibration_input_authority
    changed = False

    def mutate_during_intervening_reauth(authority):
        nonlocal changed
        result = original(authority)
        if not changed:
            inputs.beta_path.write_bytes(inputs.beta_path.read_bytes() + b" ")
            changed = True
        return result

    monkeypatch.setattr(
        module,
        "require_loaded_power_calibration_input_authority",
        mutate_during_intervening_reauth,
    )
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.require_loaded_power_calibration_receipt(receipt)
    assert changed is True


def test_numeric_receipt_round_trips_only_by_exact_recomputation(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    computed = _compute(parents, inputs)
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.require_persisted_power_calibration_receipt(computed)
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.power_calibration_receipt_artifact_sha256(computed)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _ = computed.receipt_artifact_sha256
    with pytest.raises(module.PowerCalibrationReceiptError):
        _ = computed.persisted_artifact_authenticated
    rendered = module.render_power_calibration_receipt(computed)
    assert rendered.encode("utf-8") == _render(_thaw(computed.definition))
    receipt_path = tmp_path / module.power_calibration_receipt_filename(computed)
    receipt_path.write_bytes(rendered.encode("utf-8"))
    loaded = module.load_power_calibration_receipt(
        receipt_path,
        content_contract=parents.content_contract,
        manifest_candidate=inputs.candidate,
        input_authority=inputs.input_authority,
        beta_series_path=inputs.beta_path,
        component_count_path=inputs.component_path,
    )
    assert loaded == computed
    assert loaded is not computed
    assert module.require_loaded_power_calibration_receipt(loaded) is loaded
    assert loaded.receipt_content_authenticated is True
    assert loaded.persisted_artifact_authenticated is True
    artifact_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert module.power_calibration_receipt_artifact_sha256(loaded) == artifact_sha256
    assert loaded.receipt_artifact_sha256 == artifact_sha256
    assert artifact_sha256 != loaded.receipt_hash

    receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.require_loaded_power_calibration_receipt(loaded)
    with pytest.raises(module.PowerCalibrationReceiptError):
        _ = loaded.receipt_content_authenticated
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.power_calibration_receipt_artifact_sha256(loaded)


def test_receipt_loader_requires_content_versioned_name_before_input_open(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    wrong_name = tmp_path / "numeric-receipt.json"
    # write_bytes: write_text would translate LF to CRLF on Windows and the
    # canonical-bytes refusal would fire before the filename check under test.
    wrong_name.write_bytes(
        module.render_power_calibration_receipt(receipt).encode("utf-8")
    )
    opened: list[str] = []
    original = module._read_stable_regular

    def observe(path, name, **kwargs):
        opened.append(name)
        return original(path, name, **kwargs)

    monkeypatch.setattr(module, "_read_stable_regular", observe)
    with pytest.raises(
        module.PowerCalibrationReceiptError,
        match="filename is not content-versioned",
    ):
        module.load_power_calibration_receipt(
            wrong_name,
            content_contract=parents.content_contract,
            manifest_candidate=inputs.candidate,
            input_authority=inputs.input_authority,
            beta_series_path=inputs.beta_path,
            component_count_path=inputs.component_path,
        )
    assert "date-beta input" not in opened
    assert "component-count input" not in opened


def test_atomic_receipt_persistence_is_exact_idempotent_and_no_overwrite(
    tmp_path: Path, parents: _Parents
):
    first_inputs = _write_authorized_inputs(tmp_path / "first", parents)
    first = _compute(parents, first_inputs)
    destination = tmp_path / module.power_calibration_receipt_filename(first)
    resolved = module.persist_power_calibration_receipt(first, destination)
    expected = module.render_power_calibration_receipt(first).encode("utf-8")
    assert resolved == destination.resolve()
    assert destination.read_bytes() == expected
    if os.name != "nt":
        assert destination.stat().st_mode & 0o777 == 0o600
    assert module.persist_power_calibration_receipt(first, destination) == resolved

    second_inputs = _write_authorized_inputs(
        tmp_path / "different",
        parents,
        beta_document=_baseline_beta_document(
            parents.admission.calibration_session_axis,
            multiplier=Decimal("0.000002"),
        ),
    )
    second = _compute(parents, second_inputs)
    with pytest.raises(module.PowerCalibrationReceiptError, match="content-versioned"):
        module.persist_power_calibration_receipt(second, destination)
    assert destination.read_bytes() == expected


def test_atomic_receipt_persistence_same_bytes_is_concurrency_safe(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    destination = tmp_path / module.power_calibration_receipt_filename(receipt)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = tuple(
            executor.map(
                lambda _: module.persist_power_calibration_receipt(
                    receipt, destination
                ),
                range(8),
            )
        )
    assert set(results) == {destination.resolve()}
    assert destination.read_text(encoding="utf-8") == (
        module.render_power_calibration_receipt(receipt)
    )


@pytest.mark.parametrize("pause_stage", ("pre_link", "post_link"))
def test_atomic_facade_serializes_same_process_writer_transactions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause_stage: str,
) -> None:
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    first_thread: dict[str, int] = {}
    second_thread: dict[str, int] = {}
    first_paused = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_reached_temporary_open = threading.Event()
    original_open = artifact_io_module.os.open
    original_link = artifact_io_module.os.link
    original_unlink = artifact_io_module.os.unlink

    def observed_open(path, *args, **kwargs):
        if (
            threading.get_ident() == second_thread.get("identity")
            and Path(path).name.startswith(".receipt.json.atomic-")
        ):
            second_reached_temporary_open.set()
        return original_open(path, *args, **kwargs)

    def pause_before_link(*args, **kwargs):
        if (
            pause_stage == "pre_link"
            and threading.get_ident() == first_thread.get("identity")
        ):
            first_paused.set()
            assert release_first.wait(timeout=5)
        return original_link(*args, **kwargs)

    def pause_after_link(path, *args, **kwargs):
        if (
            pause_stage == "post_link"
            and threading.get_ident() == first_thread.get("identity")
            and Path(path).name.startswith(".receipt.json.atomic-")
        ):
            first_paused.set()
            assert release_first.wait(timeout=5)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(artifact_io_module.os, "open", observed_open)
    monkeypatch.setattr(artifact_io_module.os, "link", pause_before_link)
    monkeypatch.setattr(artifact_io_module.os, "unlink", pause_after_link)

    def first_writer() -> Path:
        first_thread["identity"] = threading.get_ident()
        return artifact_io_module.create_new_regular_atomically(
            destination,
            payload,
            name="fixture artifact",
            maximum_bytes=128,
        )

    def second_writer() -> Path:
        second_thread["identity"] = threading.get_ident()
        second_started.set()
        return artifact_io_module.create_new_regular_atomically(
            destination,
            payload,
            name="fixture artifact",
            maximum_bytes=128,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_writer)
        assert first_paused.wait(timeout=5)
        second = executor.submit(second_writer)
        assert second_started.wait(timeout=5)
        try:
            assert not second_reached_temporary_open.wait(timeout=0.25)
        finally:
            release_first.set()
        assert first.result(timeout=5) == destination.resolve()
        assert second.result(timeout=5) == destination.resolve()

    assert destination.read_bytes() == payload
    assert destination.stat().st_nlink == 1
    assert tuple(tmp_path.glob(".receipt.json.atomic-*.tmp")) == ()


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="POSIX fork-lock reset check",
)
@pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded, use of fork\\(\\) may lead to "
    "deadlocks in the child.:DeprecationWarning"
)
def test_atomic_facade_resets_an_inherited_process_lock_after_fork(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "forked-child.json"
    payload = b"closed receipt fixture\n"
    lock_held = threading.Event()
    release_holder = threading.Event()

    def hold_process_lock() -> None:
        with artifact_io_module._ATOMIC_CREATE_LOCK:
            lock_held.set()
            assert release_holder.wait(timeout=8)

    holder = threading.Thread(target=hold_process_lock)
    holder.start()
    assert lock_held.wait(timeout=5)
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions run in the child
        signal.alarm(3)
        try:
            result = artifact_io_module.create_new_regular_atomically(
                destination,
                payload,
                name="fixture artifact",
                maximum_bytes=128,
            )
            exit_code = int(result != destination.resolve())
        except BaseException:
            exit_code = 2
        os._exit(exit_code)

    try:
        child_status = _wait_child_bounded(child_pid)
    finally:
        release_holder.set()
        holder.join(timeout=5)

    assert not holder.is_alive()
    assert os.waitstatus_to_exitcode(child_status) == 0
    assert destination.read_bytes() == payload


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "fork") or not hasattr(os, "fchmod"),
    reason="POSIX exact-mode publication check",
)
@pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded, use of fork\\(\\) may lead to "
    "deadlocks in the child.:DeprecationWarning"
)
def test_atomic_facade_enforces_exact_mode_despite_restrictive_umask(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "umask-independent.json"
    payload = b"closed receipt fixture\n"
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions run in the child
        signal.alarm(5)
        previous_umask = os.umask(0o777)
        try:
            first = artifact_io_module.create_new_regular_atomically(
                destination,
                payload,
                name="fixture artifact",
                maximum_bytes=128,
            )
            second = artifact_io_module.create_new_regular_atomically(
                destination,
                payload,
                name="fixture artifact",
                maximum_bytes=128,
            )
            exit_code = int(
                first != destination.resolve()
                or second != destination.resolve()
                or stat.S_IMODE(destination.stat().st_mode) != 0o600
            )
        except BaseException:
            exit_code = 2
        finally:
            os.umask(previous_umask)
        os._exit(exit_code)

    child_status = _wait_child_bounded(child_pid)
    assert os.waitstatus_to_exitcode(child_status) == 0
    assert destination.read_bytes() == payload
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="POSIX process-local authority reset check",
)
@pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded, use of fork\\(\\) may lead to "
    "deadlocks in the child.:DeprecationWarning"
)
def test_receipt_authority_locks_and_registries_fail_closed_after_fork(
    tmp_path: Path,
    parents: _Parents,
) -> None:
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    destination = tmp_path / module.power_calibration_receipt_filename(receipt)
    locks_held = threading.Event()
    release_holder = threading.Event()

    def hold_every_receipt_authority_lock() -> None:
        with module._CONTENT_CONTRACT_AUTHORITIES_LOCK:
            with module._INPUT_AUTHORITIES_LOCK:
                with module._POWER_RECEIPT_AUTHORITIES_LOCK:
                    locks_held.set()
                    assert release_holder.wait(timeout=8)

    holder = threading.Thread(target=hold_every_receipt_authority_lock)
    holder.start()
    assert locks_held.wait(timeout=5)
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions run in the child
        signal.alarm(4)
        inherited = module._INHERITED_RECEIPT_AUTHORITY_QUARANTINE[-1]
        if (
            id(parents.content_contract) not in inherited[0]
            or id(inputs.input_authority) not in inherited[1]
            or id(receipt) not in inherited[2]
            or module._CONTENT_CONTRACT_AUTHORITIES
            or module._INPUT_AUTHORITIES
            or module._POWER_RECEIPT_AUTHORITIES
        ):
            os._exit(4)
        checks = (
            lambda: module.require_loaded_power_calibration_input_content_contract(
                parents.content_contract
            ),
            lambda: module.require_loaded_power_calibration_input_authority(
                inputs.input_authority
            ),
            lambda: module.require_loaded_power_calibration_receipt(receipt),
            lambda: module.persist_power_calibration_receipt(
                receipt, destination
            ),
        )
        exit_code = 0
        for check in checks:
            try:
                check()
            except module.PowerCalibrationReceiptError:
                continue
            except BaseException:
                exit_code = 2
                break
            else:
                exit_code = 3
                break
        os._exit(exit_code)

    try:
        child_status = _wait_child_bounded(child_pid)
    finally:
        release_holder.set()
        holder.join(timeout=5)

    assert not holder.is_alive()
    assert os.waitstatus_to_exitcode(child_status) == 0
    assert not destination.exists()
    assert module.require_loaded_power_calibration_receipt(receipt) is receipt


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX process interleaving")
@pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded, use of fork\\(\\) may lead to "
    "deadlocks in the child.:DeprecationWarning"
)
def test_atomic_facade_cooperatively_recovers_live_foreign_pre_link_temporary(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    paused_read, paused_write = os.pipe()
    release_read, release_write = os.pipe()
    first_pid = os.fork()
    if first_pid == 0:  # pragma: no cover - assertions run in the child
        os.close(paused_read)
        os.close(release_write)
        signal.alarm(6)
        original_link = artifact_io_module.os.link
        paused = False

        def pause_before_link(source, *args, **kwargs):
            nonlocal paused
            if (
                not paused
                and Path(source).name.startswith(".receipt.json.atomic-")
            ):
                paused = True
                os.write(paused_write, b"P")
                os.read(release_read, 1)
            return original_link(source, *args, **kwargs)

        artifact_io_module.os.link = pause_before_link
        try:
            result = artifact_io_module.create_new_regular_atomically(
                destination,
                payload,
                name="fixture artifact",
                maximum_bytes=128,
            )
            exit_code = int(result != destination.resolve())
        except BaseException:
            exit_code = 2
        os._exit(exit_code)

    os.close(paused_write)
    os.close(release_read)
    second_pid: int | None = None
    cleanup_read = -1
    cleanup_write = -1
    first_status = -1
    second_status = -1
    try:
        assert os.read(paused_read, 1) == b"P"
        os.close(paused_read)
        paused_read = -1
        cleanup_read, cleanup_write = os.pipe()
        second_pid = os.fork()
        if second_pid == 0:  # pragma: no cover - assertions run in the child
            os.close(cleanup_read)
            os.close(release_write)
            signal.alarm(6)
            original_unlink = artifact_io_module.os.unlink
            reported_cleanup = False

            def observe_foreign_cleanup(path, *args, **kwargs):
                nonlocal reported_cleanup
                result = original_unlink(path, *args, **kwargs)
                if (
                    not reported_cleanup
                    and f".receipt.json.atomic-{first_pid}-" in Path(path).name
                ):
                    reported_cleanup = True
                    os.write(cleanup_write, b"C")
                return result

            artifact_io_module.os.unlink = observe_foreign_cleanup
            try:
                result = artifact_io_module.create_new_regular_atomically(
                    destination,
                    payload,
                    name="fixture artifact",
                    maximum_bytes=128,
                )
                exit_code = int(result != destination.resolve())
            except BaseException:
                exit_code = 2
            os._exit(exit_code)

        os.close(cleanup_write)
        cleanup_write = -1
        assert os.read(cleanup_read, 1) == b"C"
    finally:
        try:
            os.write(release_write, b"R")
        except OSError:
            pass
        os.close(release_write)
        if paused_read >= 0:
            os.close(paused_read)
        if cleanup_read >= 0:
            os.close(cleanup_read)
        if cleanup_write >= 0:
            os.close(cleanup_write)
        if second_pid is not None:
            _, second_status = os.waitpid(second_pid, 0)
        _, first_status = os.waitpid(first_pid, 0)

    assert os.waitstatus_to_exitcode(first_status) == 0
    assert os.waitstatus_to_exitcode(second_status) == 0
    assert destination.read_bytes() == payload
    assert destination.stat().st_nlink == 1
    assert tuple(tmp_path.glob(".receipt.json.atomic-*.tmp")) == ()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX process interleaving")
@pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded, use of fork\\(\\) may lead to "
    "deadlocks in the child.:DeprecationWarning"
)
def test_atomic_facade_resyncs_after_live_foreign_post_link_cleanup(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    paused_read, paused_write = os.pipe()
    release_read, release_write = os.pipe()
    first_pid = os.fork()
    if first_pid == 0:  # pragma: no cover - assertions run in the child
        os.close(paused_read)
        os.close(release_write)
        signal.alarm(6)
        original_unlink = artifact_io_module.os.unlink
        paused = False

        def pause_after_link(path, *args, **kwargs):
            nonlocal paused
            if (
                not paused
                and Path(path).name.startswith(".receipt.json.atomic-")
            ):
                paused = True
                os.write(paused_write, b"P")
                os.read(release_read, 1)
            return original_unlink(path, *args, **kwargs)

        artifact_io_module.os.unlink = pause_after_link
        artifact_io_module._fsync_directory = lambda *_args, **_kwargs: os._exit(23)
        try:
            result = artifact_io_module.create_new_regular_atomically(
                destination,
                payload,
                name="fixture artifact",
                maximum_bytes=128,
            )
            exit_code = int(result != destination.resolve())
        except BaseException:
            exit_code = 2
        os._exit(exit_code)

    os.close(paused_write)
    os.close(release_read)
    second_pid: int | None = None
    cleanup_read = -1
    cleanup_write = -1
    first_status = -1
    second_status = -1
    try:
        assert os.read(paused_read, 1) == b"P"
        os.close(paused_read)
        paused_read = -1
        cleanup_read, cleanup_write = os.pipe()
        second_pid = os.fork()
        if second_pid == 0:  # pragma: no cover - assertions run in the child
            os.close(cleanup_read)
            os.close(release_write)
            signal.alarm(6)
            original_unlink = artifact_io_module.os.unlink
            original_sync = artifact_io_module._fsync_directory
            reported_cleanup = False
            sync_count = 0

            def observe_foreign_cleanup(path, *args, **kwargs):
                nonlocal reported_cleanup
                result = original_unlink(path, *args, **kwargs)
                if (
                    not reported_cleanup
                    and f".receipt.json.atomic-{first_pid}-" in Path(path).name
                ):
                    reported_cleanup = True
                    os.write(cleanup_write, b"C")
                return result

            def count_directory_sync(*args, **kwargs) -> None:
                nonlocal sync_count
                sync_count += 1
                original_sync(*args, **kwargs)

            artifact_io_module.os.unlink = observe_foreign_cleanup
            artifact_io_module._fsync_directory = count_directory_sync
            try:
                result = artifact_io_module.create_new_regular_atomically(
                    destination,
                    payload,
                    name="fixture artifact",
                    maximum_bytes=128,
                )
                exit_code = int(
                    result != destination.resolve() or sync_count != 2
                )
            except BaseException:
                exit_code = 2
            os._exit(exit_code)

        os.close(cleanup_write)
        cleanup_write = -1
        assert os.read(cleanup_read, 1) == b"C"
    finally:
        try:
            os.write(release_write, b"R")
        except OSError:
            pass
        os.close(release_write)
        if paused_read >= 0:
            os.close(paused_read)
        if cleanup_read >= 0:
            os.close(cleanup_read)
        if cleanup_write >= 0:
            os.close(cleanup_write)
        if second_pid is not None:
            _, second_status = os.waitpid(second_pid, 0)
        _, first_status = os.waitpid(first_pid, 0)

    assert os.waitstatus_to_exitcode(first_status) == 23
    assert os.waitstatus_to_exitcode(second_status) == 0
    assert destination.read_bytes() == payload
    assert destination.stat().st_nlink == 1
    assert tuple(tmp_path.glob(".receipt.json.atomic-*.tmp")) == ()


def test_atomic_receipt_persistence_normalizes_dot_segments_for_retry(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    subdirectory = tmp_path / "subdirectory"
    subdirectory.mkdir()
    destination = (
        subdirectory
        / ".."
        / module.power_calibration_receipt_filename(receipt)
    )
    expected = tmp_path / module.power_calibration_receipt_filename(receipt)
    assert module.persist_power_calibration_receipt(
        receipt, destination
    ) == expected.resolve()
    assert module.persist_power_calibration_receipt(
        receipt, destination
    ) == expected.resolve()


def test_atomic_receipt_persistence_allows_only_one_concurrent_destination(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    filename = module.power_calibration_receipt_filename(receipt)
    destinations = (tmp_path / "one" / filename, tmp_path / "two" / filename)
    for destination in destinations:
        destination.parent.mkdir()

    def persist(destination: Path):
        try:
            return ("created", module.persist_power_calibration_receipt(
                receipt, destination
            ))
        except module.PowerCalibrationReceiptError:
            return ("refused", destination)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(persist, destinations))
    assert [status for status, _ in results].count("created") == 1
    assert [status for status, _ in results].count("refused") == 1
    assert sum(destination.exists() for destination in destinations) == 1


def test_atomic_facade_refuses_existing_different_bytes_and_unsafe_mode(
    tmp_path: Path,
):
    different = tmp_path / "different.json"
    artifact_io_module.create_new_regular_atomically(
        different,
        b"first\n",
        name="fixture artifact",
        maximum_bytes=64,
    )
    with pytest.raises(
        artifact_io_module.ArtifactIOError,
        match="different bytes",
    ):
        artifact_io_module.create_new_regular_atomically(
            different,
            b"second\n",
            name="fixture artifact",
            maximum_bytes=64,
        )
    assert different.read_bytes() == b"first\n"

    if os.name != "nt":
        permissive = tmp_path / "permissive.json"
        permissive.write_bytes(b"same\n")
        permissive.chmod(0o666)
        with pytest.raises(
            artifact_io_module.ArtifactIOError,
            match="permissions are not private",
        ):
            artifact_io_module.create_new_regular_atomically(
                permissive,
                b"same\n",
                name="fixture artifact",
                maximum_bytes=64,
            )


def test_atomic_facade_refuses_same_bytes_destination_with_external_hard_link(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "receipt.json"
    alias = tmp_path / "outside-reserved-namespace.json"
    payload = b"closed receipt fixture\n"
    destination.write_bytes(payload)
    destination.chmod(0o600)
    os.link(destination, alias)

    with pytest.raises(
        artifact_io_module.ArtifactIOError,
        match="destination link count changed",
    ):
        artifact_io_module.create_new_regular_atomically(
            destination,
            payload,
            name="fixture artifact",
            maximum_bytes=128,
        )
    assert destination.read_bytes() == payload
    assert alias.read_bytes() == payload
    assert destination.stat().st_nlink == 2


def test_atomic_facade_rechecks_bytes_after_link_count_settles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "receipt.json"
    external_alias = tmp_path / "outside-reserved-namespace.json"
    replacement = tmp_path / "replacement.json"
    payload = b"closed receipt fixture\n"
    different = b"different bytes\n"
    destination.write_bytes(payload)
    destination.chmod(0o600)
    os.link(destination, external_alias)
    replacement.write_bytes(different)
    replacement.chmod(0o600)
    original_sleep = artifact_io_module.time.sleep
    replaced = False

    def replace_during_settle(seconds: float) -> None:
        nonlocal replaced
        if not replaced:
            replaced = True
            os.replace(replacement, destination)
        original_sleep(seconds)

    monkeypatch.setattr(artifact_io_module.time, "sleep", replace_during_settle)
    with pytest.raises(
        artifact_io_module.ArtifactIOError,
        match="changed after atomic creation",
    ):
        artifact_io_module.create_new_regular_atomically(
            destination,
            payload,
            name="fixture artifact",
            maximum_bytes=128,
        )

    assert replaced is True
    assert destination.read_bytes() == different
    assert external_alias.read_bytes() == payload
    assert destination.stat().st_nlink == 1


def test_atomic_facade_matches_final_custody_to_stable_read_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "receipt.json"
    replacement = tmp_path / "replacement.json"
    payload = b"closed receipt fixture\n"
    different = b"different receipt bytes\n"
    replacement.write_bytes(different)
    replacement.chmod(0o600)
    original_custody = artifact_io_module._require_private_single_link
    custody_calls = 0

    def replace_before_final_custody(*args, **kwargs):
        nonlocal custody_calls
        custody_calls += 1
        if custody_calls == 2:
            os.replace(replacement, destination)
        return original_custody(*args, **kwargs)

    monkeypatch.setattr(
        artifact_io_module,
        "_require_private_single_link",
        replace_before_final_custody,
    )
    with pytest.raises(
        artifact_io_module.ArtifactIOError,
        match="changed after atomic creation",
    ):
        artifact_io_module.create_new_regular_atomically(
            destination,
            payload,
            name="fixture artifact",
            maximum_bytes=128,
        )

    assert custody_calls == 2
    assert destination.read_bytes() == different
    assert destination.stat().st_nlink == 1


def test_atomic_facade_recovers_exact_stale_post_link_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    original_unlink = artifact_io_module.os.unlink
    interrupted = False

    def interrupt_post_link(path):
        nonlocal interrupted
        if Path(path).name.startswith(".receipt.json.atomic-"):
            interrupted = True
            raise OSError("fixture-only post-link interruption")
        return original_unlink(path)

    monkeypatch.setattr(artifact_io_module.os, "unlink", interrupt_post_link)
    with pytest.raises(
        artifact_io_module.ArtifactIOError,
        match="temporary cleanup failed",
    ):
        artifact_io_module.create_new_regular_atomically(
            destination,
            payload,
            name="fixture artifact",
            maximum_bytes=128,
        )
    assert destination.read_bytes() == payload
    assert destination.stat().st_nlink == 2
    assert tuple(tmp_path.glob(".receipt.json.atomic-*.tmp"))

    monkeypatch.setattr(artifact_io_module.os, "unlink", original_unlink)
    assert artifact_io_module.create_new_regular_atomically(
        destination,
        payload,
        name="fixture artifact",
        maximum_bytes=128,
    ) == destination.resolve()
    assert destination.stat().st_nlink == 1
    assert tuple(tmp_path.glob(".receipt.json.atomic-*.tmp")) == ()


def test_atomic_facade_recovers_exact_stale_prelink_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    original_link = artifact_io_module.os.link
    original_unlink = artifact_io_module.os.unlink

    def interrupt_before_link(*args, **kwargs):
        raise OSError("fixture-only pre-link interruption")

    def preserve_temporary(path):
        if Path(path).name.startswith(".receipt.json.atomic-"):
            raise OSError("fixture-only abrupt cleanup loss")
        return original_unlink(path)

    monkeypatch.setattr(artifact_io_module.os, "link", interrupt_before_link)
    monkeypatch.setattr(artifact_io_module.os, "unlink", preserve_temporary)
    with pytest.raises(
        artifact_io_module.ArtifactIOError,
        match="atomic creation failed",
    ):
        artifact_io_module.create_new_regular_atomically(
            destination,
            payload,
            name="fixture artifact",
            maximum_bytes=128,
        )
    assert not destination.exists()
    stale = tuple(tmp_path.glob(".receipt.json.atomic-*.tmp"))
    assert len(stale) == 1
    assert stale[0].read_bytes() == payload

    monkeypatch.setattr(artifact_io_module.os, "link", original_link)
    monkeypatch.setattr(artifact_io_module.os, "unlink", original_unlink)
    assert artifact_io_module.create_new_regular_atomically(
        destination,
        payload,
        name="fixture artifact",
        maximum_bytes=128,
    ) == destination.resolve()
    assert tuple(tmp_path.glob(".receipt.json.atomic-*.tmp")) == ()


def test_atomic_facade_exact_retry_recovers_before_all_slots_are_exhausted(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    destination.write_bytes(payload)
    destination.chmod(0o600)
    for attempt in range(1024):
        stale = tmp_path / (
            f".receipt.json.atomic-{os.getpid()}-{attempt:04d}.tmp"
        )
        stale.write_bytes(payload)
        stale.chmod(0o600)

    assert artifact_io_module.create_new_regular_atomically(
        destination,
        payload,
        name="fixture artifact",
        maximum_bytes=128,
    ) == destination.resolve()
    assert destination.read_bytes() == payload
    assert destination.stat().st_nlink == 1
    assert tuple(tmp_path.glob(".receipt.json.atomic-*.tmp")) == ()


def test_windows_directory_sync_branch_is_an_explicit_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    synthesized_mode = tmp_path / "windows-synthesized-mode.json"
    synthesized_mode.write_bytes(b"fixture\n")
    synthesized_mode.chmod(0o666)
    monkeypatch.setattr(artifact_io_module.os, "name", "nt")
    artifact_io_module._require_private_single_link(
        synthesized_mode, name="fixture artifact"
    )

    def unexpected_open(*args, **kwargs):
        raise AssertionError("Windows directory sync attempted os.open")

    monkeypatch.setattr(artifact_io_module.os, "open", unexpected_open)
    artifact_io_module._fsync_directory(tmp_path, name="fixture artifact")


def test_atomic_receipt_persistence_recovers_after_post_link_sync_failure(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    destination = tmp_path / module.power_calibration_receipt_filename(receipt)
    original = artifact_io_module._fsync_directory

    def fail_after_link(path, *, name):
        raise artifact_io_module.ArtifactIOError(
            "fixture-only simulated directory-sync failure"
        )

    monkeypatch.setattr(artifact_io_module, "_fsync_directory", fail_after_link)
    with pytest.raises(module.PowerCalibrationReceiptError, match="persistence failed"):
        module.persist_power_calibration_receipt(receipt, destination)
    assert destination.read_text(encoding="utf-8") == (
        module.render_power_calibration_receipt(receipt)
    )
    assert list(tmp_path.glob(".*.tmp")) == []

    monkeypatch.setattr(artifact_io_module, "_fsync_directory", original)
    assert module.persist_power_calibration_receipt(receipt, destination) == (
        destination.resolve()
    )


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="host has no symlink support")
@pytest.mark.parametrize("link_kind", ["leaf", "ancestor"])
def test_atomic_receipt_persistence_refuses_leaf_and_ancestor_links(
    tmp_path: Path,
    parents: _Parents,
    link_kind: str,
):
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    filename = module.power_calibration_receipt_filename(receipt)
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    if link_kind == "leaf":
        target = real_directory / "target.json"
        target.write_bytes(b"must remain unchanged")
        destination = real_directory / filename
        _symlink_or_skip(destination, target)
    else:
        linked_directory = tmp_path / "linked"
        _symlink_or_skip(
            linked_directory,
            real_directory,
            target_is_directory=True,
        )
        destination = linked_directory / filename
        target = real_directory / filename
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.persist_power_calibration_receipt(receipt, destination)
    if link_kind == "leaf":
        assert target.read_bytes() == b"must remain unchanged"
    else:
        assert not target.exists()


def test_atomic_receipt_persistence_refuses_a_junctioned_destination_parent(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    filename = module.power_calibration_receipt_filename(receipt)
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    linked_directory = tmp_path / "linked"
    _junction_or_skip(linked_directory, real_directory)
    destination = linked_directory / filename
    with pytest.raises(module.PowerCalibrationReceiptError) as caught:
        module.persist_power_calibration_receipt(receipt, destination)
    assert caught.value.__cause__ is not None
    assert "link" in str(caught.value.__cause__)
    assert not (real_directory / filename).exists()


def test_closed_persisted_receipt_reauth_never_opens_calibration_inputs(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path / "inputs", parents)
    receipt = _compute(parents, inputs)
    destination = tmp_path / module.power_calibration_receipt_filename(receipt)
    module.persist_power_calibration_receipt(receipt, destination)
    opened: list[str] = []
    original = module._read_stable_regular

    def refuse_sensitive(path, name, **kwargs):
        opened.append(name)
        if name in {"date-beta input", "component-count input"}:
            raise AssertionError("closed receipt reauth opened calibration input")
        return original(path, name, **kwargs)

    monkeypatch.setattr(module, "_read_stable_regular", refuse_sensitive)
    assert module.require_persisted_power_calibration_receipt(receipt) is receipt
    assert receipt.persisted_artifact_authenticated is True
    assert module.power_calibration_receipt_artifact_sha256(receipt) == (
        hashlib.sha256(destination.read_bytes()).hexdigest()
    )
    assert "date-beta input" not in opened
    assert "component-count input" not in opened


@pytest.mark.parametrize("kind", ["unknown", "numeric", "identity", "noncanonical"])
def test_persisted_receipt_refuses_any_changed_output_or_shape(
    tmp_path: Path, parents: _Parents, kind: str
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    computed = _compute(parents, inputs)
    raw = _thaw(computed.definition)
    if kind == "unknown":
        raw["outcome"] = "forbidden"
    elif kind == "numeric":
        raw["required_receipt_fields"]["required_valid_dates"] += 1
    elif kind == "identity":
        raw["receipt_hash"] = "0" * 64
    else:
        pass
    payload = _render(raw)
    if kind == "noncanonical":
        payload += b" "
    path = tmp_path / "changed-receipt.json"
    path.write_bytes(payload)
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.load_power_calibration_receipt(
            path,
            content_contract=parents.content_contract,
            manifest_candidate=inputs.candidate,
            input_authority=inputs.input_authority,
            beta_series_path=inputs.beta_path,
            component_count_path=inputs.component_path,
        )


def test_persisted_receipt_refuses_duplicate_keys_floats_and_oversize(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    receipt = _compute(parents, inputs)
    payload = module.render_power_calibration_receipt(receipt).encode("utf-8")
    variants = {
        "duplicate": payload.replace(
            b'{\n  "authority":',
            b'{\n  "authority": "duplicate",\n  "authority":',
            1,
        ),
        "float": payload.replace(
            f'"required_valid_dates": {receipt.required_valid_dates}'.encode(),
            b'"required_valid_dates": 1.0',
            1,
        ),
        "bom": b"\xef\xbb\xbf" + payload,
    }
    for name, changed in variants.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(changed)
        with pytest.raises(module.PowerCalibrationReceiptError):
            module.load_power_calibration_receipt(
                path,
                content_contract=parents.content_contract,
                manifest_candidate=inputs.candidate,
                input_authority=inputs.input_authority,
                beta_series_path=inputs.beta_path,
                component_count_path=inputs.component_path,
            )

    oversized = tmp_path / "oversized-receipt.json"
    with oversized.open("wb") as handle:
        handle.truncate(module.MAX_INPUT_ARTIFACT_BYTES + 1)
    with pytest.raises(module.PowerCalibrationReceiptError):
        module.load_power_calibration_receipt(
            oversized,
            content_contract=parents.content_contract,
            manifest_candidate=inputs.candidate,
            input_authority=inputs.input_authority,
            beta_series_path=inputs.beta_path,
            component_count_path=inputs.component_path,
        )


@pytest.mark.parametrize(
    ("authorization_id", "evidence_hash", "instant"),
    [
        ("", AUTHORIZATION_EVIDENCE_SHA256, AUTHORIZED_AT_UTC),
        (AUTHORIZATION_ID, "A" * 64, AUTHORIZED_AT_UTC),
        (AUTHORIZATION_ID, "0" * 63, AUTHORIZED_AT_UTC),
        (AUTHORIZATION_ID, AUTHORIZATION_EVIDENCE_SHA256, "2026-09-07"),
        (
            AUTHORIZATION_ID,
            AUTHORIZATION_EVIDENCE_SHA256,
            "2026-09-07T20:00:00.000000+00:00",
        ),
    ],
)
def test_input_authority_provenance_fields_are_strict(
    tmp_path: Path,
    parents: _Parents,
    authorization_id: str,
    evidence_hash: str,
    instant: str,
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    with _fixture_only_truth_gate(inputs.truth_approval_path):
        with pytest.raises(module.PowerCalibrationReceiptError):
            module.render_power_calibration_input_authority(
                parents.content_contract,
                inputs.candidate,
                production_truth_approval_path=inputs.truth_approval_path,
                owner_authorization_id=authorization_id,
                owner_authorization_evidence_sha256=evidence_hash,
                authorized_at_utc=instant,
            )


def test_input_authority_exact_operations_and_bindings_cannot_be_changed(
    tmp_path: Path, parents: _Parents
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    raw = _thaw(inputs.input_authority.definition)
    changes = []
    changed_operation = copy.deepcopy(raw)
    changed_operation["authorized_operations"]["outcome_read"] = True
    changes.append(changed_operation)
    changed_binding = copy.deepcopy(raw)
    changed_binding["input_artifact_bindings"][0]["artifact_sha256"] = "0" * 64
    changes.append(changed_binding)
    changed_shape = copy.deepcopy(raw)
    changed_shape["qc_project_id"] = "forbidden"
    changes.append(changed_shape)
    for index, changed in enumerate(changes):
        path = tmp_path / f"authority-{index}.json"
        path.write_bytes(_render(changed))
        with _fixture_only_authority_gate(path, inputs.truth_approval_path):
            with pytest.raises(module.PowerCalibrationReceiptError):
                module.load_power_calibration_input_authority(
                    path,
                    content_contract=parents.content_contract,
                    manifest_candidate=inputs.candidate,
                    production_truth_approval_path=inputs.truth_approval_path,
                )


def test_input_authority_loader_uses_one_authenticated_parent_snapshot(
    tmp_path: Path,
    parents: _Parents,
    monkeypatch: pytest.MonkeyPatch,
):
    inputs = _write_authorized_inputs(tmp_path, parents)
    candidate = inputs.candidate
    authority_path = module._INPUT_AUTHORITIES[id(inputs.input_authority)][1]
    original_manifest_id = candidate.manifest_id
    original_revalidate = module._revalidate
    authority_revalidations = 0

    def mutate_after_final_revalidation(path, payload, name, **kwargs):
        nonlocal authority_revalidations
        result = original_revalidate(path, payload, name, **kwargs)
        if name == "input authority":
            authority_revalidations += 1
            if authority_revalidations == 2:
                object.__setattr__(
                    candidate, "manifest_id", "forged-transient-manifest"
                )
        return result

    monkeypatch.setattr(module, "_revalidate", mutate_after_final_revalidation)
    try:
        with _fixture_only_authority_gate(
            authority_path, inputs.truth_approval_path
        ):
            loaded = module.load_power_calibration_input_authority(
                authority_path,
                content_contract=parents.content_contract,
                manifest_candidate=candidate,
                production_truth_approval_path=inputs.truth_approval_path,
            )
    finally:
        object.__setattr__(candidate, "manifest_id", original_manifest_id)
    assert authority_revalidations == 2
    assert loaded.manifest_id == original_manifest_id
    assert module.require_loaded_power_calibration_input_authority(loaded) is loaded

    object.__setattr__(candidate, "manifest_id", "forged-parent-manifest")
    try:
        with pytest.raises(module.PowerCalibrationReceiptError):
            module.require_loaded_power_calibration_input_authority(loaded)
    finally:
        object.__setattr__(candidate, "manifest_id", original_manifest_id)


def test_input_authority_must_match_the_reviewed_pin_not_merely_its_parents(
    tmp_path: Path, parents: _Parents
):
    # ARV2R17-001: a structurally valid, parent-bound authority rendered for a
    # different owner triple must refuse on the pin alone.  Nothing else in the
    # loader distinguishes it from the reviewed artifact.
    inputs = _write_authorized_inputs(tmp_path, parents)
    with _fixture_only_truth_gate(inputs.truth_approval_path):
        other = module.render_power_calibration_input_authority(
            parents.content_contract,
            inputs.candidate,
            production_truth_approval_path=inputs.truth_approval_path,
            owner_authorization_id="owner-other-authorization-20260907",
            owner_authorization_evidence_sha256="f" * 64,
            authorized_at_utc=AUTHORIZED_AT_UTC,
        )
    other_path = tmp_path / "other-input-authority.json"
    other_path.write_bytes(other.encode("utf-8"))
    reviewed_path = tmp_path / "input-authority.json"
    assert other_path.read_bytes() != reviewed_path.read_bytes()
    with _fixture_only_authority_gate(reviewed_path, inputs.truth_approval_path):
        with pytest.raises(
            module.PowerCalibrationReceiptError,
            match="does not match the reviewed pin",
        ):
            module.load_power_calibration_input_authority(
                other_path,
                content_contract=parents.content_contract,
                manifest_candidate=inputs.candidate,
                production_truth_approval_path=inputs.truth_approval_path,
            )


def test_production_truth_approval_must_match_the_reviewed_pin_not_merely_its_candidate(
    tmp_path: Path, parents: _Parents
):
    # ARV2R17-002: a self-consistent aggregate carrying a different review
    # triple must refuse on the truth pin before the authority is even read.
    inputs = _write_authorized_inputs(tmp_path, parents)
    other_truth_path = tmp_path / "other-truth-approval.json"
    other_truth_path.write_bytes(
        _render(
            module._truth_approval_document(
                inputs.candidate,
                review_id="fixture-only-other-truth-review",
                review_evidence_sha256="e" * 64,
                reviewed_at_utc=FIXTURE_TRUTH_REVIEWED_AT_UTC,
            )
        )
    )
    assert other_truth_path.read_bytes() != inputs.truth_approval_path.read_bytes()
    reviewed_path = tmp_path / "input-authority.json"
    with _fixture_only_authority_gate(reviewed_path, inputs.truth_approval_path):
        with pytest.raises(
            module.PowerCalibrationReceiptError,
            match="does not match the reviewed pin",
        ):
            module.load_power_calibration_input_authority(
                reviewed_path,
                content_contract=parents.content_contract,
                manifest_candidate=inputs.candidate,
                production_truth_approval_path=other_truth_path,
            )


def test_receipt_loader_refuses_rehashed_output_drift_at_load_not_only_downstream(
    tmp_path: Path, parents: _Parents
):
    # ARV2R17-003: a receipt whose closed output was changed and whose identity
    # and filename were recomputed to match is refused by the load-time
    # recomputation comparison, not merely by a later persisted-reauthentication.
    inputs = _write_authorized_inputs(tmp_path, parents)
    computed = _compute(parents, inputs)
    raw = _thaw(computed.definition)
    raw["required_receipt_fields"]["required_valid_dates"] += 1
    raw = module._content_identity(
        raw,
        id_field="receipt_id",
        hash_field="receipt_hash",
        prefix=module.RECEIPT_ID_PREFIX,
    )
    path = tmp_path / f"{raw['receipt_id']}.{raw['receipt_hash']}.json"
    path.write_bytes(_render(raw))
    with pytest.raises(
        module.PowerCalibrationReceiptError,
        match="differs from recomputation",
    ):
        module.load_power_calibration_receipt(
            path,
            content_contract=parents.content_contract,
            manifest_candidate=inputs.candidate,
            input_authority=inputs.input_authority,
            beta_series_path=inputs.beta_path,
            component_count_path=inputs.component_path,
        )


def test_atomic_facade_preserves_different_payload_residue_in_reserved_namespace(
    tmp_path: Path,
):
    # ARV2R17-004: the bounded recovery sweep may remove only exact same-payload
    # or same-inode residue; a private same-owner temporary holding different
    # bytes is foreign work in progress and must survive publication.
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    foreign = tmp_path / ".receipt.json.atomic-99999-0000.tmp"
    foreign_payload = b"different in-progress bytes\n"
    foreign.write_bytes(foreign_payload)
    foreign.chmod(0o600)
    assert artifact_io_module.create_new_regular_atomically(
        destination, payload, name="fixture artifact", maximum_bytes=128
    ) == destination.resolve()
    assert destination.read_bytes() == payload
    assert foreign.exists()
    assert foreign.read_bytes() == foreign_payload


def test_atomic_facade_recovers_foreign_same_payload_without_liveness_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    foreign_pid = os.getpid() + 1
    foreign = tmp_path / f".receipt.json.atomic-{foreign_pid}-0000.tmp"
    foreign.write_bytes(payload)
    foreign.chmod(0o600)
    def unexpected_liveness_probe(*args, **kwargs):
        raise AssertionError("cooperative exact-payload recovery probed liveness")

    monkeypatch.setattr(artifact_io_module.os, "kill", unexpected_liveness_probe)
    assert artifact_io_module.create_new_regular_atomically(
        destination,
        payload,
        name="fixture artifact",
        maximum_bytes=128,
    ) == destination.resolve()
    assert destination.read_bytes() == payload
    assert not foreign.exists()


def test_atomic_facade_preserves_unlink_denied_single_link_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    foreign_pid = os.getpid() + 1
    foreign = tmp_path / f".receipt.json.atomic-{foreign_pid}-0000.tmp"
    foreign.write_bytes(payload)
    foreign.chmod(0o600)
    original_unlink = artifact_io_module.os.unlink

    def deny_foreign_unlink(path, *args, **kwargs):
        if Path(path) == foreign:
            raise PermissionError("fixture-only open Windows writer")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(artifact_io_module.os, "unlink", deny_foreign_unlink)
    assert artifact_io_module.create_new_regular_atomically(
        destination,
        payload,
        name="fixture artifact",
        maximum_bytes=128,
    ) == destination.resolve()
    assert destination.read_bytes() == payload
    assert destination.stat().st_nlink == 1
    assert foreign.read_bytes() == payload


def test_atomic_recovery_removes_foreign_post_link_destination_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    destination.write_bytes(payload)
    destination.chmod(0o600)
    foreign_pid = os.getpid() + 1
    foreign = tmp_path / f".receipt.json.atomic-{foreign_pid}-0000.tmp"
    os.link(destination, foreign)
    monkeypatch.setattr(artifact_io_module.os, "name", "nt")

    artifact_io_module._recover_stale_atomic_links(
        tmp_path,
        destination,
        payload,
        candidate_name=destination.name,
        name="fixture artifact",
        maximum_bytes=128,
    )

    assert destination.read_bytes() == payload
    assert destination.stat().st_nlink == 1
    assert not foreign.exists()


@pytest.mark.parametrize(
    "malformed_name",
    (
        ".receipt.json.atomic-not-a-pid.tmp",
        ".receipt.json.atomic-99999999999-0000.tmp",
        ".receipt.json.atomic-99999-1024.tmp",
        f".receipt.json.atomic-0{os.getpid()}-0000.tmp",
    ),
)
def test_atomic_facade_preserves_malformed_reserved_namespace_residue(
    tmp_path: Path,
    malformed_name: str,
) -> None:
    destination = tmp_path / "receipt.json"
    payload = b"closed receipt fixture\n"
    malformed = tmp_path / malformed_name
    malformed.write_bytes(payload)
    malformed.chmod(0o600)

    assert artifact_io_module.create_new_regular_atomically(
        destination,
        payload,
        name="fixture artifact",
        maximum_bytes=128,
    ) == destination.resolve()
    assert malformed.exists()
    assert malformed.read_bytes() == payload


@pytest.mark.parametrize(
    ("pid_text", "expected"),
    (
        ("2147483648", 2_147_483_648),
        ("4294967295", 4_294_967_295),
        ("4294967296", None),
    ),
)
def test_atomic_temporary_pid_parser_accepts_unsigned_windows_range(
    pid_text: str,
    expected: int | None,
) -> None:
    prefix = ".receipt.json.atomic-"
    suffix = ".tmp"
    assert artifact_io_module._reserved_temporary_owner_pid(
        f"{prefix}{pid_text}-0000{suffix}",
        prefix=prefix,
        suffix=suffix,
    ) == expected
