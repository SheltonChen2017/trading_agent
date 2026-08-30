"""Executable, content-addressed preregistration and outcome-access gate."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import weakref
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from data.exchange_calendar import ExchangeCalendarError, is_trading_session

from .dataset import (
    DatasetVerificationError,
    capture_clean_git_lineage,
    compute_package_source_sha256,
    git_commit_is_ancestor,
    load_normalized_dataset,
    read_git_bytes,
    read_git_text,
    revalidate_normalized_dataset,
)
from .snapshot import load_verified_snapshot, revalidate_verified_snapshot


class PreregistrationError(ValueError):
    """A research choice is missing, edited, spent, or outcome-contaminating."""


REQUIRED_CELL_IDS = (
    "shared_holdout",
    "contaminated_legacy_periods",
    "canonical_family",
    "channel_family_policy",
    "availability_rule",
    "label_contract",
    "corporate_action_contract",
    "walk_forward_contract",
    "inference_contract",
    "mandatory_controls",
    "missing_control_policy",
    "universe_contract",
    "normalization_contract",
    "stock_topology",
    "topology_comparison_hierarchy",
    "observation_rule_parity",
    "cost_contract",
    "holdings_contract",
    "portfolio_contract",
    "multiplicity_family",
    "historical_evaluation_contract",
    "lane_validation_period",
    "three_lane_selection_correction",
    "valid_null_closes_family",
    "legacy_reproduction_policy",
)

MANDATORY_CONTROLS = (
    "earnings_guidance",
    "immediate_price_jump",
    "liquidity",
    "momentum",
    "sector",
    "size",
    "volatility",
)
_TOP_KEYS = {
    "schema",
    "status",
    "spec_id",
    "spec_hash",
    "producing_commit",
    "reviewed_by",
    "reviewed_at",
    "cells",
    "looks",
}
_CELL_KEYS = {"cell_id", "state", "value", "source"}
_LOOK_KEYS = {
    "look_id",
    "family_id",
    "state",
    "validation_start",
    "validation_end",
    "dataset_id",
    "code_identity",
    "cost_cell_hash",
    "topology_id",
}
_REGISTRY_KEYS = {"schema", "entries"}
_REGISTRY_ENTRY_KEYS = {
    "spec_id",
    "spec_hash",
    "artifact_sha256",
    "spec_path",
    "review_commit",
    "reviewed_by",
    "reviewed_at",
}
_CONTAMINATED_PERIOD_KEYS = {"start", "end", "disposition", "reason"}
_CORPORATE_ACTION_KEYS = {
    "source_id",
    "source_sha256",
    "point_in_time",
    "split_policy",
    "cash_dividend_policy",
    "delisting_policy",
    "missing_terminal_return",
}
_UNIVERSE_KEYS = {
    "security_master_id",
    "security_master_sha256",
    "point_in_time",
    "listing_venues",
    "issuer_incorporation",
    "instrument_types",
    "excluded_instrument_types",
    "share_class_policy",
    "include_delisted",
    "current_ticker_joins",
    "unknown_identity",
}
_NORMALIZATION_KEYS = {
    "population",
    "method",
    "peer_hierarchy",
    "minimum_total_names",
    "minimum_active_names",
    "structural_zero",
    "clipping",
    "residualization",
    "degenerate_group",
}
_HISTORICAL_EVALUATION_KEYS = {
    "eligible_history_start",
    "development_end",
    "history_extension_policy",
    "market_benchmark",
    "regime_signal_timing",
    "stress_rule",
    "boom_rule",
    "ordinary_rule",
    "formal_selection_policy",
    "regime_output_policy",
    "named_episode_policy",
    "named_episodes",
}
_NAMED_EPISODE_KEYS = {"episode_id", "start", "end", "label"}
_STOCK_TOPOLOGY_KEYS = {"topology_id", "primary_cell_id", "cells"}
_STOCK_CELL_KEYS = {
    "cell_id",
    "signal",
    "sign",
    "half_life_sessions",
    "threshold",
    "clip",
    "residualization",
}
_MULTIPLICITY_KEYS = {
    "family_id",
    "alpha",
    "correction",
    "permanent_cell_ids",
    "permanent_look_ids",
}

REVIEWED_SPEC_REGISTRY_PATH = (
    Path(__file__).resolve().parent / "specs" / "reviewed_spec_registry.json"
)
LEGACY_LOCAL_LOOK_LEDGER_PATH = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "analyst_revisions_v2"
    / "permanent_look_ledger.sqlite3"
)
PERMANENT_LOOK_AUTHORITY_PATH = (
    Path(__file__).resolve().parent
    / "specs"
    / "permanent_look_authority.json"
)
REVIEW_REGISTRY_SCHEMA = "arv2-reviewed-spec-registry-v1"
PERMANENT_LOOK_AUTHORITY_SCHEMA = "arv2-permanent-look-authority-v1"
ZERO_ACCESS_AUTHORITY_ID = "arv2-zero-access-no-external-authority"
OWNER_DECISION_CANDIDATE_STATUS = (
    "owner_decisions_frozen_pending_external_bindings_and_review"
)
PRIMARY_OUTCOME_LOOK_ID = "arv2-look-legacy-v1-migration-only"
SUPERSEDED_LOOK_IDS = frozenset({"arv2-look-stock-primary-001"})
SUPERSEDED_VALIDATION_PERIODS = frozenset(
    {
        (
            "2026-09-01",
            "2027-08-31",
        )
    }
)
LEGACY_V1_OUTCOME_AUTHORITY_RETIRED_REASON = (
    "legacy v1 outcome authority was superseded unspent; a complete reviewed "
    "QC-first v2 evaluation specification is required"
)
_PENDING_SOURCE_CELL_IDS = frozenset(
    {"corporate_action_contract", "universe_contract"}
)
_REVIEWED_AUTHORITY = object()
_PERMIT_AUTHORITY = object()
_REVIEWED_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType["ReviewedPreregistration"],
        Path,
        tuple[object, ...],
    ],
] = {}
_REVIEWED_AUTHORITIES_LOCK = threading.RLock()


def _sha256(value: object, name: str, length: int = 64) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PreregistrationError(f"{name} must be a lowercase {length}-hex digest")
    return value


def _dataset_id(value: object, name: str = "dataset_id") -> str:
    if not isinstance(value, str) or not value.startswith("arv2_ds_"):
        raise PreregistrationError(f"{name} must use arv2_ds_<sha256>")
    _sha256(value.removeprefix("arv2_ds_"), name)
    return value


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise PreregistrationError(f"{name} must be canonical non-empty text")
    return value


def _positive_int(value: object, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PreregistrationError(f"{name} must be an integer >= {minimum}")
    return value


def _decimal_text(
    value: object,
    name: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
    strictly_positive: bool = False,
) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PreregistrationError(f"{name} must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PreregistrationError(f"{name} must be a finite decimal string") from exc
    if not parsed.is_finite() or str(parsed) != value:
        raise PreregistrationError(f"{name} must be a canonical finite decimal string")
    if strictly_positive and parsed <= 0:
        raise PreregistrationError(f"{name} must be positive")
    if minimum is not None and parsed < minimum:
        raise PreregistrationError(f"{name} is below its minimum")
    if maximum is not None and parsed > maximum:
        raise PreregistrationError(f"{name} exceeds its maximum")
    return parsed


def _date(value: object, name: str) -> date:
    if not isinstance(value, str):
        raise PreregistrationError(f"{name} must be canonical YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PreregistrationError(f"{name} must be canonical YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise PreregistrationError(f"{name} must be canonical YYYY-MM-DD")
    return parsed


def _session(value: object, name: str) -> date:
    parsed = _date(value, name)
    try:
        valid = is_trading_session(parsed.isoformat())
    except ExchangeCalendarError as exc:
        raise PreregistrationError(f"{name} cannot be resolved by the exchange calendar") from exc
    if not valid:
        raise PreregistrationError(f"{name} must be an NYSE trading session")
    return parsed


def _aware_instant(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise PreregistrationError(f"{name} must be an aware ISO instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreregistrationError(f"{name} must be an aware ISO instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreregistrationError(f"{name} must be an aware ISO instant")


def _strict_json(value: object, path: str = "value") -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if isinstance(value, float):
        raise PreregistrationError(f"{path} cannot use binary floating-point")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _strict_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) or not key for key in value):
            raise PreregistrationError(f"{path} keys must be non-empty strings")
        for key, item in value.items():
            _strict_json(item, f"{path}.{key}")
        return
    raise PreregistrationError(f"{path} contains a non-JSON value")


def _deep_freeze(value: object) -> object:
    """Detach loaded authority from caller-owned mutable JSON containers."""
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _cell_sha256(value: object) -> str:
    _strict_json(value)
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_payload(raw: Mapping[str, object]) -> bytes:
    without_hash = dict(raw)
    without_hash["spec_hash"] = None
    without_hash["spec_id"] = None
    return json.dumps(
        without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclasses.dataclass(frozen=True)
class PreregistrationCell:
    cell_id: str
    value: object
    source: str


@dataclasses.dataclass(frozen=True)
class RegisteredLook:
    look_id: str
    family_id: str
    state: str
    validation_start: str
    validation_end: str
    dataset_id: str
    code_identity: str
    cost_cell_hash: str
    topology_id: str


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedPreregistration:
    spec_id: str
    spec_hash: str
    producing_commit: str
    reviewed_by: str
    reviewed_at: str
    cells: tuple[PreregistrationCell, ...]
    looks: tuple[RegisteredLook, ...]
    source_path: str
    artifact_sha256: str
    review_commit: str
    _authority: object = dataclasses.field(repr=False, compare=False)

    def cell(self, cell_id: str) -> object:
        for cell in self.cells:
            if cell.cell_id == cell_id:
                return cell.value
        raise PreregistrationError(f"required preregistration cell is absent: {cell_id}")


def _authority_value(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple(
            (key, _authority_value(item))
            for key, item in sorted(value.items())
        )
    if isinstance(value, tuple):
        return tuple(_authority_value(item) for item in value)
    return value


def _reviewed_fingerprint(
    spec: ReviewedPreregistration,
) -> tuple[object, ...]:
    return (
        spec.spec_id,
        spec.spec_hash,
        spec.producing_commit,
        spec.reviewed_by,
        spec.reviewed_at,
        tuple(
            (cell.cell_id, _authority_value(cell.value), cell.source)
            for cell in spec.cells
        ),
        tuple(
            (
                look.look_id,
                look.family_id,
                look.state,
                look.validation_start,
                look.validation_end,
                look.dataset_id,
                look.code_identity,
                look.cost_cell_hash,
                look.topology_id,
            )
            for look in spec.looks
        ),
        spec.source_path,
        spec.artifact_sha256,
        spec.review_commit,
    )


def _forget_reviewed_authority(
    identity: int,
    reference: weakref.ReferenceType[ReviewedPreregistration],
) -> None:
    with _REVIEWED_AUTHORITIES_LOCK:
        current = _REVIEWED_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _REVIEWED_AUTHORITIES.pop(identity, None)


def _reviewed_preregistration(
    *,
    spec_id: str,
    spec_hash: str,
    producing_commit: str,
    reviewed_by: str,
    reviewed_at: str,
    cells: tuple[PreregistrationCell, ...],
    looks: tuple[RegisteredLook, ...],
    source_path: str,
    artifact_sha256: str,
    review_commit: str,
) -> ReviewedPreregistration:
    value = object.__new__(ReviewedPreregistration)
    for name, item in {
        "spec_id": spec_id,
        "spec_hash": spec_hash,
        "producing_commit": producing_commit,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "cells": cells,
        "looks": looks,
        "source_path": source_path,
        "artifact_sha256": artifact_sha256,
        "review_commit": review_commit,
        "_authority": _REVIEWED_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    fingerprint = _reviewed_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_reviewed_authority(key, ref)
    )
    with _REVIEWED_AUTHORITIES_LOCK:
        _REVIEWED_AUTHORITIES[identity] = (
            reference,
            Path(source_path),
            fingerprint,
        )
    return value


@dataclasses.dataclass(frozen=True)
class DraftPreregistration:
    status: str
    spec_id: str
    spec_hash: str
    unresolved_owner_decisions: tuple[str, ...]
    pending_external_bindings: tuple[str, ...]
    planned_look_ids: tuple[str, ...]


def _parse_root(path: Path) -> dict[str, object]:
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise PreregistrationError("preregistration is unreadable") from exc
    if not isinstance(raw, dict) or set(raw) != _TOP_KEYS:
        raise PreregistrationError("preregistration has missing or unknown root fields")
    if raw["schema"] != "arv2-round0-preregistration-v1":
        raise PreregistrationError("preregistration schema is unsupported")
    _strict_json(raw)
    return raw


def _refuse_superseded_look_id(raw: Mapping[str, object]) -> None:
    looks = raw.get("looks")
    if not isinstance(looks, list):
        return
    for item in looks:
        if isinstance(item, dict) and item.get("look_id") in SUPERSEDED_LOOK_IDS:
            raise PreregistrationError(
                "look identity was superseded unspent and cannot be revived"
            )


def _git(root: Path, *arguments: str, binary: bool = False) -> str | bytes:
    try:
        if binary:
            return read_git_bytes(root, arguments)
        return read_git_text(root, arguments)
    except (DatasetVerificationError, OSError, UnicodeError) as exc:
        raise PreregistrationError("review anchor Git verification could not run") from exc


def _json_object(payload: bytes, name: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreregistrationError(f"{name} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise PreregistrationError(f"{name} must be a JSON object")
    _strict_json(value, name)
    return value


def _review_anchor(
    spec_path: Path,
    raw: Mapping[str, object],
) -> tuple[str, str, str]:
    """Bind a reviewed spec to the committed counter-review registry.

    The registry entry is added only after the independent review commit has
    put the exact reviewed spec bytes into Git. This prevents a self-hashed
    caller-created JSON file from granting outcome authority.
    """
    try:
        registry_path = REVIEWED_SPEC_REGISTRY_PATH.resolve(strict=True)
        resolved_spec = spec_path.resolve(strict=True)
    except OSError as exc:
        raise PreregistrationError("reviewed spec or review registry is absent") from exc
    registry_root_text = str(
        _git(registry_path.parent, "rev-parse", "--show-toplevel")
    ).strip()
    spec_root_text = str(_git(resolved_spec.parent, "rev-parse", "--show-toplevel")).strip()
    registry_root = Path(registry_root_text).resolve(strict=True)
    spec_root = Path(spec_root_text).resolve(strict=True)
    if registry_root != spec_root:
        raise PreregistrationError("reviewed spec and review registry are not in one repository")
    try:
        spec_relative = resolved_spec.relative_to(spec_root).as_posix()
        registry_relative = registry_path.relative_to(spec_root).as_posix()
    except ValueError as exc:
        raise PreregistrationError("review anchor escaped its Git repository") from exc

    status = str(
        _git(
            spec_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            spec_relative,
            registry_relative,
        )
    )
    if status:
        raise PreregistrationError("reviewed spec and review registry must be committed and clean")
    _git(spec_root, "ls-files", "--error-unmatch", "--", spec_relative)
    _git(spec_root, "ls-files", "--error-unmatch", "--", registry_relative)

    registry = _json_object(registry_path.read_bytes(), "review registry")
    if set(registry) != _REGISTRY_KEYS or registry["schema"] != REVIEW_REGISTRY_SCHEMA:
        raise PreregistrationError("review registry schema or root fields are invalid")
    entries = registry["entries"]
    if not isinstance(entries, list):
        raise PreregistrationError("review registry entries must be a list")
    canonical_registry = _canonical_json(registry)
    committed_registry = _json_object(
        bytes(_git(spec_root, "show", f"HEAD:{registry_relative}", binary=True)),
        "committed review registry",
    )
    if canonical_registry != _canonical_json(committed_registry):
        raise PreregistrationError("working review registry differs from committed registry")

    spec_id = raw.get("spec_id")
    matches: list[dict[str, object]] = []
    seen_ids: set[object] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _REGISTRY_ENTRY_KEYS:
            raise PreregistrationError("review registry entry fields are invalid")
        if entry["spec_id"] in seen_ids:
            raise PreregistrationError("review registry contains duplicate spec_id")
        seen_ids.add(entry["spec_id"])
        if entry["spec_id"] == spec_id:
            matches.append(entry)
    if len(matches) != 1:
        raise PreregistrationError("reviewed spec has no unique external review anchor")
    anchor = matches[0]
    spec_hash = _sha256(anchor["spec_hash"], "anchored spec_hash")
    artifact_hash = _sha256(anchor["artifact_sha256"], "anchored artifact_sha256")
    review_commit = _sha256(anchor["review_commit"], "review_commit", 40)
    _text(anchor["reviewed_by"], "anchored reviewed_by")
    _aware_instant(anchor["reviewed_at"], "anchored reviewed_at")
    if (
        anchor["spec_path"] != spec_relative
        or spec_hash != raw.get("spec_hash")
        or anchor["reviewed_by"] != raw.get("reviewed_by")
        or anchor["reviewed_at"] != raw.get("reviewed_at")
    ):
        raise PreregistrationError("review anchor does not match the reviewed spec")
    canonical_spec = _canonical_json(raw)
    if artifact_hash != hashlib.sha256(canonical_spec).hexdigest():
        raise PreregistrationError("review anchor does not bind the complete spec artifact")
    _git(spec_root, "cat-file", "-e", f"{review_commit}^{{commit}}")
    try:
        review_is_ancestor = git_commit_is_ancestor(spec_root, review_commit, "HEAD")
    except DatasetVerificationError as exc:
        raise PreregistrationError("independent review ancestry cannot be verified") from exc
    if not review_is_ancestor:
        raise PreregistrationError("independent review commit is not an ancestor of HEAD")
    producing_commit = _sha256(
        raw.get("producing_commit"), "anchored producing_commit", 40
    )
    _git(spec_root, "cat-file", "-e", f"{producing_commit}^{{commit}}")
    try:
        producing_was_reviewed = git_commit_is_ancestor(
            spec_root, producing_commit, review_commit
        )
    except DatasetVerificationError as exc:
        raise PreregistrationError("producing commit ancestry cannot be verified") from exc
    if not producing_was_reviewed:
        raise PreregistrationError(
            "producing commit is not contained in the independent review commit"
        )
    reviewed_blob = _json_object(
        bytes(_git(spec_root, "show", f"{review_commit}:{spec_relative}", binary=True)),
        "reviewed spec blob",
    )
    if _canonical_json(reviewed_blob) != canonical_spec:
        raise PreregistrationError("current spec differs from the independently reviewed blob")
    return str(resolved_spec), artifact_hash, review_commit


def _assert_review_authority(spec: ReviewedPreregistration) -> None:
    if (
        type(spec) is not ReviewedPreregistration
        or getattr(spec, "_authority", None) is not _REVIEWED_AUTHORITY
    ):
        raise PreregistrationError("outcome access requires loader-authenticated review authority")
    with _REVIEWED_AUTHORITIES_LOCK:
        authority = _REVIEWED_AUTHORITIES.get(id(spec))
    if authority is None or authority[0]() is not spec:
        raise PreregistrationError(
            "review authority is not registered to this loader-created object"
        )
    _, original_path, expected_fingerprint = authority
    if _reviewed_fingerprint(spec) != expected_fingerprint:
        raise PreregistrationError("review authority changed after spec verification")
    reloaded = load_reviewed_preregistration(original_path)
    if _reviewed_fingerprint(reloaded) != expected_fingerprint:
        raise PreregistrationError(
            "reviewed spec bytes, semantics, review anchor, or look bindings changed"
        )


def require_reviewed_preregistration(
    value: object,
) -> ReviewedPreregistration:
    """Return only currently reauthenticated, independently reviewed authority."""
    if type(value) is not ReviewedPreregistration:
        raise PreregistrationError(
            "review authority requires a ReviewedPreregistration"
        )
    _assert_review_authority(value)
    return value


def load_draft_preregistration(path: Path) -> DraftPreregistration:
    raw = _parse_root(path)
    if raw["status"] != OWNER_DECISION_CANDIDATE_STATUS:
        raise PreregistrationError("artifact is not the owner-decision candidate")
    spec_hash = _sha256(raw["spec_hash"], "spec_hash")
    if spec_hash != hashlib.sha256(_canonical_payload(raw)).hexdigest():
        raise PreregistrationError("owner-decision candidate content hash mismatch")
    if raw["spec_id"] != f"arv2-round0-candidate-{spec_hash[:16]}":
        raise PreregistrationError("candidate spec_id is not content-derived")
    _refuse_superseded_look_id(raw)
    if any(
        raw[field] is not None
        for field in ("producing_commit", "reviewed_by", "reviewed_at")
    ):
        raise PreregistrationError(
            "unreviewed candidate cannot claim production or review authority"
        )
    cells = raw["cells"]
    if not isinstance(cells, list) or len(cells) != len(REQUIRED_CELL_IDS):
        raise PreregistrationError("candidate must inventory every required cell")
    values: dict[str, object] = {}
    for expected, cell in zip(REQUIRED_CELL_IDS, cells, strict=True):
        if not isinstance(cell, dict) or set(cell) != _CELL_KEYS or cell["cell_id"] != expected:
            raise PreregistrationError(
                "candidate cells must have exact fields and canonical order"
            )
        expected_state = (
            "frozen_policy_external_binding_required"
            if expected in _PENDING_SOURCE_CELL_IDS
            else "frozen"
        )
        if cell["state"] != expected_state or cell["value"] is None:
            raise PreregistrationError(
                "every owner decision must be populated and frozen; only exact "
                "external source bindings may remain pending"
            )
        _text(cell["source"], f"{expected} source")
        values[expected] = cell["value"]
    _validate_semantics(values, allow_unbound_external_sources=True)

    validation = values["lane_validation_period"]
    multiplicity = values["multiplicity_family"]
    raw_looks = raw["looks"]
    if not isinstance(raw_looks, list) or not raw_looks:
        raise PreregistrationError("candidate must freeze at least one planned look")
    planned_look_ids: list[str] = []
    for item in raw_looks:
        if not isinstance(item, dict) or set(item) != _LOOK_KEYS:
            raise PreregistrationError("planned look has missing or unknown fields")
        look_id = item["look_id"]
        if (
            not isinstance(look_id, str)
            or not look_id.startswith("arv2-look-")
            or look_id in planned_look_ids
        ):
            raise PreregistrationError("planned look_id is invalid or duplicated")
        if look_id in SUPERSEDED_LOOK_IDS:
            raise PreregistrationError(
                "planned look identity was superseded unspent and cannot be revived"
            )
        planned_look_ids.append(look_id)
        if (
            item["state"] != "planned_unbound"
            or item["dataset_id"] is not None
            or item["code_identity"] is not None
        ):
            raise PreregistrationError(
                "candidate looks must remain explicitly unbound and non-executable"
            )
        if (
            item["validation_start"] != validation["start"]
            or item["validation_end"] != validation["end"]
        ):
            raise PreregistrationError(
                "planned look period differs from the frozen validation period"
            )
        if (
            item["family_id"] != multiplicity["family_id"]
            or item["topology_id"] != "stock_primary"
        ):
            raise PreregistrationError("planned look changed family or topology")
        _sha256(item["cost_cell_hash"], "planned look cost_cell_hash")
        if item["cost_cell_hash"] != _cell_sha256(values["cost_contract"]):
            raise PreregistrationError("planned look does not bind the frozen cost cell")
    if tuple(multiplicity["permanent_look_ids"]) != tuple(planned_look_ids):
        raise PreregistrationError(
            "multiplicity family does not cover every planned look"
        )
    pending = (
        "corporate_action_contract.source_id",
        "corporate_action_contract.source_sha256",
        "universe_contract.security_master_id",
        "universe_contract.security_master_sha256",
        f"looks.{planned_look_ids[0]}.dataset_id",
        f"looks.{planned_look_ids[0]}.code_identity",
        "independent_review_anchor",
        "external_permanent_look_authority",
    )
    return DraftPreregistration(
        status=str(raw["status"]),
        spec_id=str(raw["spec_id"]),
        spec_hash=spec_hash,
        unresolved_owner_decisions=(),
        pending_external_bindings=pending,
        planned_look_ids=tuple(planned_look_ids),
    )


def _require_mapping(value: object, name: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PreregistrationError(f"{name} must have exact keys {sorted(keys)}")
    return value


def _string_list(value: object, name: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        raise PreregistrationError(f"{name} must be a{' non-empty' if nonempty else ''} list")
    materialized = tuple(_text(item, f"{name} item") for item in value)
    if len(materialized) != len(set(materialized)):
        raise PreregistrationError(f"{name} must not contain duplicates")
    return materialized


def _validate_semantics(
    cells: Mapping[str, object],
    *,
    allow_unbound_external_sources: bool = False,
) -> None:
    holdout = _require_mapping(
        cells["shared_holdout"],
        "shared_holdout",
        {"cutoff_session", "reserved_start", "reserved_end", "lane_access_prohibited"},
    )
    cutoff = _session(holdout["cutoff_session"], "shared holdout cutoff")
    reserved_start = _session(holdout["reserved_start"], "shared holdout start")
    reserved_end = _session(holdout["reserved_end"], "shared holdout end")
    if holdout["lane_access_prohibited"] is not True or not cutoff < reserved_start <= reserved_end:
        raise PreregistrationError("shared final holdout is not genuinely reserved")
    contaminated = cells["contaminated_legacy_periods"]
    if not isinstance(contaminated, list) or not contaminated:
        raise PreregistrationError("contaminated legacy periods must be exhaustively classified")
    contaminated_ranges: list[tuple[date, date]] = []
    for index, period in enumerate(contaminated):
        record = _require_mapping(
            period,
            f"contaminated_legacy_periods[{index}]",
            _CONTAMINATED_PERIOD_KEYS,
        )
        start = _date(record["start"], "contaminated period start")
        end = _date(record["end"], "contaminated period end")
        if start > end:
            raise PreregistrationError("contaminated period is reversed")
        if record["disposition"] not in {"discovery_only", "prohibited"}:
            raise PreregistrationError("contaminated period disposition is invalid")
        _text(record["reason"], "contaminated period reason")
        contaminated_ranges.append((start, end))
    ordered_ranges = sorted(contaminated_ranges)
    if any(current[0] <= prior[1] for prior, current in zip(ordered_ranges, ordered_ranges[1:])):
        raise PreregistrationError("contaminated legacy periods overlap")
    if cells["canonical_family"] != "rating_only":
        raise PreregistrationError("first canonical family must be rating_only")
    if cells["channel_family_policy"] != {
        "price_target": "separate_future_family",
        "eps_revision": "separate_future_family",
        "news": "separate_future_family",
    }:
        raise PreregistrationError("non-rating channels must remain separate future families")
    availability = _require_mapping(
        cells["availability_rule"],
        "availability_rule",
        {"exact_clock", "date_only", "ambiguous_clock"},
    )
    if availability != {
        "exact_clock": "first_exchange_open_strictly_after_public_instant",
        "date_only": "second_exchange_session_open_strictly_after_event_date",
        "ambiguous_clock": "refuse",
    }:
        raise PreregistrationError("availability rule is not the conservative V2 contract")
    label = _require_mapping(
        cells["label_contract"],
        "label_contract",
        {"horizon_sessions", "entry", "exit", "missing_exit"},
    )
    horizon = label["horizon_sessions"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise PreregistrationError("label horizon must be a positive exchange-session count")
    if label["entry"] != "eligible_session_open" or label["exit"] != "h_session_open":
        raise PreregistrationError("labels must use eligible-open to h-session-open")
    if label["missing_exit"] != "terminal_return_or_named_refusal_never_drop":
        raise PreregistrationError("missing exits cannot be silently dropped")
    corporate = _require_mapping(
        cells["corporate_action_contract"],
        "corporate_action_contract",
        _CORPORATE_ACTION_KEYS,
    )
    if allow_unbound_external_sources:
        if corporate["source_id"] is not None or corporate["source_sha256"] is not None:
            raise PreregistrationError(
                "candidate corporate-action source must remain explicitly unbound"
            )
    else:
        _text(corporate["source_id"], "corporate action source_id")
        _sha256(corporate["source_sha256"], "corporate action source_sha256")
    if corporate != {
        "source_id": corporate["source_id"],
        "source_sha256": corporate["source_sha256"],
        "point_in_time": True,
        "split_policy": "effective_session_point_in_time",
        "cash_dividend_policy": "ex_date_point_in_time_total_return",
        "delisting_policy": "terminal_return_required",
        "missing_terminal_return": "named_refusal_never_drop",
    }:
        raise PreregistrationError("corporate-action and terminal-return rules are unsafe")
    walk = _require_mapping(
        cells["walk_forward_contract"],
        "walk_forward_contract",
        {"train_years", "validation_years", "test_years", "purge_group", "embargo_sessions"},
    )
    if (walk["train_years"], walk["validation_years"], walk["test_years"]) != (5, 2, 1):
        raise PreregistrationError("walk-forward windows must remain 5y/2y/1y")
    if walk["purge_group"] != "decision_date_and_common_event":
        raise PreregistrationError("splits must purge decision date and common event")
    embargo = walk["embargo_sessions"]
    if isinstance(embargo, bool) or not isinstance(embargo, int) or embargo < horizon:
        raise PreregistrationError("embargo must be at least the outcome horizon")
    inference = _require_mapping(
        cells["inference_contract"],
        "inference_contract",
        {"sample_unit", "cluster", "block_length_sessions", "minimum_independent_dates"},
    )
    block = inference["block_length_sessions"]
    minimum_dates = inference["minimum_independent_dates"]
    if inference["sample_unit"] != "decision_date" or inference["cluster"] != "common_event":
        raise PreregistrationError("independent unit and common-event clustering are required")
    if isinstance(block, bool) or not isinstance(block, int) or block < horizon:
        raise PreregistrationError("bootstrap block must cover the outcome horizon")
    if isinstance(minimum_dates, bool) or not isinstance(minimum_dates, int) or minimum_dates < 50:
        raise PreregistrationError("minimum independent dates must be at least 50")
    controls = cells["mandatory_controls"]
    if not isinstance(controls, list) or tuple(controls) != MANDATORY_CONTROLS:
        raise PreregistrationError("mandatory controls are omitted or reordered")
    if cells["missing_control_policy"] != "refuse_row_before_cross_section":
        raise PreregistrationError("missing controls must refuse before the cross-section")
    universe = _require_mapping(
        cells["universe_contract"], "universe_contract", _UNIVERSE_KEYS
    )
    if allow_unbound_external_sources:
        if (
            universe["security_master_id"] is not None
            or universe["security_master_sha256"] is not None
        ):
            raise PreregistrationError(
                "candidate security-master source must remain explicitly unbound"
            )
    else:
        _text(universe["security_master_id"], "security master id")
        _sha256(universe["security_master_sha256"], "security master sha256")
    venues = _string_list(universe["listing_venues"], "listing venues")
    instruments = _string_list(universe["instrument_types"], "instrument types")
    exclusions = _string_list(
        universe["excluded_instrument_types"], "excluded instrument types"
    )
    if (
        universe["point_in_time"] is not True
        or universe["include_delisted"] is not True
        or universe["current_ticker_joins"] is not False
        or universe["unknown_identity"] != "refuse"
        or universe["issuer_incorporation"] != "united_states"
        or venues != ("XASE", "XNAS", "XNYS")
        or instruments != ("common_stock",)
        or exclusions
        != (
            "adr",
            "bdc",
            "closed_end_fund",
            "etf",
            "foreign_ordinary",
            "limited_partnership",
            "preferred_stock",
            "reit",
            "right",
            "trust",
            "unit",
            "warrant",
        )
        or universe["share_class_policy"]
        != "separate_security_with_point_in_time_issuer_link"
    ):
        raise PreregistrationError("universe is not point-in-time and survivorship-safe")
    normalization = _require_mapping(
        cells["normalization_contract"],
        "normalization_contract",
        _NORMALIZATION_KEYS,
    )
    if normalization != {
        "population": "eligible_point_in_time_cross_section",
        "method": "sector_median_mad",
        "peer_hierarchy": ["sector", "refuse"],
        "minimum_total_names": 20,
        "minimum_active_names": 5,
        "structural_zero": "valid_no_event_only",
        "clipping": "frozen_cell_specific",
        "residualization": "mandatory_controls_cross_sectional",
        "degenerate_group": "named_refusal",
    }:
        raise PreregistrationError("normalization contract is incomplete or fail-open")
    topology = _require_mapping(
        cells["stock_topology"], "stock_topology", _STOCK_TOPOLOGY_KEYS
    )
    if topology["topology_id"] != "stock_primary":
        raise PreregistrationError("first topology must remain stock_primary")
    primary_cell_id = _text(topology["primary_cell_id"], "primary stock cell id")
    raw_stock_cells = topology["cells"]
    if (
        primary_cell_id != "arv2-stock-primary-20d"
        or not isinstance(raw_stock_cells, list)
        or len(raw_stock_cells) != 1
    ):
        raise PreregistrationError(
            "stock topology must contain only the frozen primary 20-day cell"
        )
    stock_cell_ids: list[str] = []
    for index, raw_cell in enumerate(raw_stock_cells):
        cell = _require_mapping(
            raw_cell, f"stock_topology.cells[{index}]", _STOCK_CELL_KEYS
        )
        cell_id = _text(cell["cell_id"], "stock cell id")
        if cell_id in stock_cell_ids:
            raise PreregistrationError("stock topology cell IDs are duplicated")
        stock_cell_ids.append(cell_id)
        if (
            cell["signal"] != "rating_change"
            or cell["sign"] != "upgrade_positive_downgrade_negative"
            or cell["residualization"] != "mandatory_controls_cross_sectional"
        ):
            raise PreregistrationError("stock topology changed the rating-only primary family")
        if _positive_int(
            cell["half_life_sessions"], "stock half-life sessions"
        ) != 20:
            raise PreregistrationError("stock half-life must remain 20 sessions")
        if _decimal_text(
            cell["threshold"], "stock threshold", minimum=Decimal("0")
        ) != Decimal("0"):
            raise PreregistrationError("stock threshold must remain zero")
        if _decimal_text(
            cell["clip"], "stock clip", strictly_positive=True
        ) != Decimal("4"):
            raise PreregistrationError("stock clip must remain four")
    if primary_cell_id not in stock_cell_ids:
        raise PreregistrationError("primary stock cell is absent from the frozen topology")
    if cells["topology_comparison_hierarchy"] != ["stock", "industry", "etf"]:
        raise PreregistrationError("stock must precede industry and ETF topology")
    if (
        cells["observation_rule_parity"]
        != "identical_timing_universe_missingness_and_cost_rules_for_signal_and_baselines"
    ):
        raise PreregistrationError("signal and baseline observation rules are not identical")
    costs = _require_mapping(
        cells["cost_contract"], "cost_contract", {"scenario_bps", "units", "missing_adv"}
    )
    if costs != {
        "scenario_bps": ["0", "5", "10", "20"],
        "units": "dollars_then_divide_once_by_nav",
        "missing_adv": "refuse_except_forced_terminal_exit",
    }:
        raise PreregistrationError("cost scenarios or units changed")
    holdings = _require_mapping(
        cells["holdings_contract"],
        "holdings_contract",
        {"minimum_mapped_candidate_weight", "point_in_time", "stale_or_incomplete"},
    )
    if holdings != {
        "minimum_mapped_candidate_weight": "0.99",
        "point_in_time": True,
        "stale_or_incomplete": "refuse",
    }:
        raise PreregistrationError("holdings contract is not fail-closed")
    portfolio = _require_mapping(
        cells["portfolio_contract"],
        "portfolio_contract",
        {"maximum_holdings", "etf_cap", "sector_cap", "cluster_cap", "leverage"},
    )
    if portfolio != {
        "maximum_holdings": 5,
        "etf_cap": "0.20",
        "sector_cap": "0.40",
        "cluster_cap": "0.30",
        "leverage": False,
    }:
        raise PreregistrationError("portfolio hard caps changed")
    historical = _require_mapping(
        cells["historical_evaluation_contract"],
        "historical_evaluation_contract",
        _HISTORICAL_EVALUATION_KEYS,
    )
    history_start = _session(
        historical["eligible_history_start"], "eligible history start"
    )
    development_end = _session(
        historical["development_end"], "historical development end"
    )
    if history_start > development_end:
        raise PreregistrationError("historical evaluation period is reversed")
    if historical != {
        "eligible_history_start": historical["eligible_history_start"],
        "development_end": historical["development_end"],
        "history_extension_policy": (
            "earlier_only_after_independent_source_coverage_and_semantics_review"
        ),
        "market_benchmark": "SPY_total_return",
        "regime_signal_timing": "prior_session_close_only",
        "stress_rule": "trailing_252_session_drawdown_lte_-0.20",
        "boom_rule": (
            "trailing_252_session_total_return_gte_0.20_and_not_stress"
        ),
        "ordinary_rule": "neither_boom_nor_stress",
        "formal_selection_policy": "all_periods_walk_forward_only",
        "regime_output_policy": "descriptive_non_rescuing",
        "named_episode_policy": "descriptive_non_rescuing_no_model_selection",
        "named_episodes": historical["named_episodes"],
    }:
        raise PreregistrationError(
            "historical and regime evaluation contract is not the frozen V2 design"
        )
    episodes = historical["named_episodes"]
    if not isinstance(episodes, list) or not episodes:
        raise PreregistrationError("named historical episodes must be explicit")
    episode_ids: list[str] = []
    episode_labels: list[str] = []
    episode_ranges: list[tuple[date, date]] = []
    for index, episode in enumerate(episodes):
        item = _require_mapping(
            episode,
            f"historical_evaluation_contract.named_episodes[{index}]",
            _NAMED_EPISODE_KEYS,
        )
        episode_id = _text(item["episode_id"], "named episode id")
        if episode_id in episode_ids:
            raise PreregistrationError("named episode IDs are duplicated")
        episode_ids.append(episode_id)
        episode_start = _session(item["start"], "named episode start")
        episode_end = _session(item["end"], "named episode end")
        episode_labels.append(_text(item["label"], "named episode label"))
        if not history_start <= episode_start <= episode_end <= development_end:
            raise PreregistrationError("named episode is outside eligible history")
        episode_ranges.append((episode_start, episode_end))
    ordered_episodes = sorted(episode_ranges)
    if any(
        current[0] <= prior[1]
        for prior, current in zip(ordered_episodes, ordered_episodes[1:])
    ):
        raise PreregistrationError("named historical episodes overlap")
    if not {"boom", "stress"}.issubset(episode_labels):
        raise PreregistrationError(
            "named historical episodes must include boom and stress diagnostics"
        )
    validation = _require_mapping(
        cells["lane_validation_period"],
        "lane_validation_period",
        {"start", "end", "one_shot"},
    )
    validation_start = _session(validation["start"], "lane validation start")
    validation_end = _session(validation["end"], "lane validation end")
    if (validation["start"], validation["end"]) in SUPERSEDED_VALIDATION_PERIODS:
        raise PreregistrationError(
            "lane validation period was superseded unspent by the owner QC-first "
            "sequence and cannot be backfilled or reviewed"
        )
    if validation["one_shot"] is not True or not validation_start <= validation_end <= cutoff:
        raise PreregistrationError("lane validation is not one-shot and holdout-excluded")
    if development_end >= validation_start:
        raise PreregistrationError(
            "historical development must end before prospective validation starts"
        )
    if any(
        validation_start <= contaminated_end and contaminated_start <= validation_end
        for contaminated_start, contaminated_end in contaminated_ranges
    ):
        raise PreregistrationError("lane validation overlaps contaminated discovery history")
    multiplicity = _require_mapping(
        cells["multiplicity_family"], "multiplicity_family", _MULTIPLICITY_KEYS
    )
    if multiplicity["family_id"] != "arv2-rating-only-v1":
        raise PreregistrationError("multiplicity family ID changed")
    alpha = _decimal_text(
        multiplicity["alpha"],
        "multiplicity alpha",
        strictly_positive=True,
        maximum=Decimal("1"),
    )
    if multiplicity["correction"] != "bonferroni_all_registered_cells_and_looks":
        raise PreregistrationError("multiplicity correction is not exhaustive")
    permanent_cells = _string_list(
        multiplicity["permanent_cell_ids"], "permanent cell IDs"
    )
    permanent_looks = _string_list(
        multiplicity["permanent_look_ids"], "permanent look IDs"
    )
    if alpha != Decimal("0.05"):
        raise PreregistrationError("multiplicity alpha must remain 0.05")
    if permanent_cells != ("arv2-stock-primary-20d",):
        raise PreregistrationError("multiplicity family does not cover every stock cell")
    if permanent_looks != (PRIMARY_OUTCOME_LOOK_ID,):
        raise PreregistrationError(
            "multiplicity family permanent-look budget must remain one named look"
        )
    if cells["three_lane_selection_correction"] != 3:
        raise PreregistrationError("three-lane selection family must count all three attempts")
    if cells["valid_null_closes_family"] is not True:
        raise PreregistrationError("a valid null must close the canonical family")
    if cells["legacy_reproduction_policy"] != "non_new_non_v2_offline_registered_only":
        raise PreregistrationError("legacy reproductions cannot enter active evidence")


def load_reviewed_preregistration(path: Path) -> ReviewedPreregistration:
    raw = _parse_root(path)
    if raw["status"] != "reviewed_frozen":
        raise PreregistrationError("outcome access requires a reviewed_frozen preregistration")
    spec_hash = _sha256(raw["spec_hash"], "spec_hash")
    actual_hash = hashlib.sha256(_canonical_payload(raw)).hexdigest()
    if spec_hash != actual_hash:
        raise PreregistrationError("preregistration content hash mismatch")
    if raw["spec_id"] != f"arv2-round0-{spec_hash[:16]}":
        raise PreregistrationError("spec_id is not derived from the complete spec hash")
    _refuse_superseded_look_id(raw)
    producing_commit = _sha256(raw["producing_commit"], "producing_commit", 40)
    if not isinstance(raw["reviewed_by"], str) or not raw["reviewed_by"].strip():
        raise PreregistrationError("reviewed_by must name the independent reviewer")
    _aware_instant(raw["reviewed_at"], "reviewed_at")
    raw_cells = raw["cells"]
    if not isinstance(raw_cells, list) or len(raw_cells) != len(REQUIRED_CELL_IDS):
        raise PreregistrationError("reviewed spec must contain every required cell exactly once")
    cells: list[PreregistrationCell] = []
    for expected, cell in zip(REQUIRED_CELL_IDS, raw_cells, strict=True):
        if not isinstance(cell, dict) or set(cell) != _CELL_KEYS:
            raise PreregistrationError("cell has missing or unknown fields")
        if cell["cell_id"] != expected or cell["state"] != "frozen" or cell["value"] is None:
            raise PreregistrationError("every cell must be frozen, populated, and canonically ordered")
        if not isinstance(cell["source"], str) or not cell["source"].strip():
            raise PreregistrationError("every decision must name its source")
        cells.append(
            PreregistrationCell(
                expected,
                _deep_freeze(cell["value"]),
                str(cell["source"]),
            )
        )
    # Semantics are checked against detached ordinary JSON first. The stored
    # authority below receives an independently deep-frozen copy.
    mutable_by_id = {
        str(cell["cell_id"]): cell["value"] for cell in raw_cells
    }
    _validate_semantics(mutable_by_id)
    raw_looks = raw["looks"]
    if not isinstance(raw_looks, list) or not raw_looks:
        raise PreregistrationError("reviewed spec must register at least one permanent look")
    looks: list[RegisteredLook] = []
    seen: set[str] = set()
    validation = mutable_by_id["lane_validation_period"]
    for item in raw_looks:
        if not isinstance(item, dict) or set(item) != _LOOK_KEYS:
            raise PreregistrationError("look registration has missing or unknown fields")
        look_id = item["look_id"]
        if not isinstance(look_id, str) or not look_id.startswith("arv2-look-") or look_id in seen:
            raise PreregistrationError("look_id is invalid or duplicated")
        if look_id in SUPERSEDED_LOOK_IDS:
            raise PreregistrationError(
                "registered look identity was superseded unspent and cannot be revived"
            )
        seen.add(look_id)
        if item["state"] != "registered_unspent":
            raise PreregistrationError("immutable preregistration may contain only unspent looks")
        if item["validation_start"] != validation["start"] or item["validation_end"] != validation["end"]:
            raise PreregistrationError("look period differs from the frozen lane validation period")
        _dataset_id(item["dataset_id"], "look dataset_id")
        _sha256(item["code_identity"], "look code_identity")
        _sha256(item["cost_cell_hash"], "look cost_cell_hash")
        if not isinstance(item["family_id"], str) or item["family_id"] != "arv2-rating-only-v1":
            raise PreregistrationError("look belongs to an unknown family")
        if item["topology_id"] != "stock_primary":
            raise PreregistrationError("first outcome look must be stock-primary")
        if item["cost_cell_hash"] != _cell_sha256(mutable_by_id["cost_contract"]):
            raise PreregistrationError("look cost_cell_hash does not bind the frozen cost cell")
        looks.append(RegisteredLook(**item))
    multiplicity = mutable_by_id["multiplicity_family"]
    if tuple(multiplicity["permanent_look_ids"]) != tuple(look.look_id for look in looks):
        raise PreregistrationError("multiplicity family does not cover every registered look")
    source_path, artifact_hash, review_commit = _review_anchor(path, raw)
    return _reviewed_preregistration(
        spec_id=str(raw["spec_id"]),
        spec_hash=spec_hash,
        producing_commit=producing_commit,
        reviewed_by=str(raw["reviewed_by"]),
        reviewed_at=str(raw["reviewed_at"]),
        cells=tuple(cells),
        looks=tuple(looks),
        source_path=source_path,
        artifact_sha256=artifact_hash,
        review_commit=review_commit,
    )


@dataclasses.dataclass(frozen=True)
class OutcomeAccessRequest:
    look_id: str
    dataset_id: str
    code_identity: str
    requested_start: str
    requested_end: str
    horizon_sessions: int
    embargo_sessions: int
    block_length_sessions: int
    controls: tuple[str, ...]
    topology_id: str
    cost_cell_hash: str


@dataclasses.dataclass(frozen=True, init=False)
class OutcomeAccessPermit:
    spec_id: str
    spec_hash: str
    spec_artifact_sha256: str
    review_commit: str
    look_id: str
    family_id: str
    dataset_id: str
    code_identity: str
    requested_start: str
    requested_end: str
    horizon_sessions: int
    embargo_sessions: int
    block_length_sessions: int
    controls: tuple[str, ...]
    topology_id: str
    cost_cell_hash: str
    request_sha256: str
    holdout_exclusion_proved: bool
    permit_id: str
    spent_at: str
    authority_id: str
    authority_receipt_id: str
    _authority: object = dataclasses.field(repr=False, compare=False)


def _request_payload(request: OutcomeAccessRequest) -> dict[str, object]:
    return {
        "look_id": request.look_id,
        "dataset_id": request.dataset_id,
        "code_identity": request.code_identity,
        "requested_start": request.requested_start,
        "requested_end": request.requested_end,
        "horizon_sessions": request.horizon_sessions,
        "embargo_sessions": request.embargo_sessions,
        "block_length_sessions": request.block_length_sessions,
        "controls": list(request.controls),
        "topology_id": request.topology_id,
        "cost_cell_hash": request.cost_cell_hash,
    }


def _request_sha256(request: OutcomeAccessRequest) -> str:
    return hashlib.sha256(
        _canonical_json(
            {"schema": "arv2-outcome-access-request-v1", **_request_payload(request)}
        )
    ).hexdigest()


def _outcome_permit(
    *,
    spec: ReviewedPreregistration,
    request: OutcomeAccessRequest,
    look: RegisteredLook,
    authority_id: str,
    authority_receipt_id: str,
    permit_id: str,
    spent_at: str,
) -> OutcomeAccessPermit:
    validated_look, request_hash = _validate_outcome_request(spec, request)
    if validated_look != look:
        raise PreregistrationError("permit look is not the approved registered look")
    _text(authority_id, "authority_id")
    _text(authority_receipt_id, "authority_receipt_id")
    _text(permit_id, "permit_id")
    _aware_instant(spent_at, "spent_at")
    value = object.__new__(OutcomeAccessPermit)
    for name, item in {
        "spec_id": spec.spec_id,
        "spec_hash": spec.spec_hash,
        "spec_artifact_sha256": spec.artifact_sha256,
        "review_commit": spec.review_commit,
        "look_id": request.look_id,
        "family_id": look.family_id,
        "dataset_id": request.dataset_id,
        "code_identity": request.code_identity,
        "requested_start": request.requested_start,
        "requested_end": request.requested_end,
        "horizon_sessions": request.horizon_sessions,
        "embargo_sessions": request.embargo_sessions,
        "block_length_sessions": request.block_length_sessions,
        "controls": request.controls,
        "topology_id": request.topology_id,
        "cost_cell_hash": request.cost_cell_hash,
        "request_sha256": request_hash,
        "holdout_exclusion_proved": True,
        "permit_id": permit_id,
        "spent_at": spent_at,
        "authority_id": authority_id,
        "authority_receipt_id": authority_receipt_id,
        "_authority": _PERMIT_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    return value


# A deletable or substitutable local database is never permanent-look authority.
# Outcome authorization below is exclusively fail-closed until an independently
# pinned cross-machine append-only authority is configured.
def _validate_outcome_request(
    spec: ReviewedPreregistration,
    request: OutcomeAccessRequest,
) -> tuple[RegisteredLook, str]:
    require_reviewed_preregistration(spec)
    if type(request) is not OutcomeAccessRequest:
        raise PreregistrationError("outcome request must be typed")
    _text(request.look_id, "look_id")
    _dataset_id(request.dataset_id)
    _sha256(request.code_identity, "code_identity")
    _sha256(request.cost_cell_hash, "cost_cell_hash")
    _text(request.topology_id, "topology_id")
    if type(request.controls) is not tuple:
        raise PreregistrationError("outcome controls must be an immutable tuple")
    matches = [look for look in spec.looks if look.look_id == request.look_id]
    if len(matches) != 1:
        raise PreregistrationError("research look is unregistered")
    look = matches[0]
    for name in ("dataset_id", "code_identity", "cost_cell_hash", "topology_id"):
        if getattr(request, name) != getattr(look, name):
            raise PreregistrationError(f"outcome request changed frozen {name}")
    if (
        request.requested_start != look.validation_start
        or request.requested_end != look.validation_end
    ):
        raise PreregistrationError(
            "outcome request changed the one-shot validation period"
        )
    start = _session(request.requested_start, "requested_start")
    end = _session(request.requested_end, "requested_end")
    holdout = spec.cell("shared_holdout")
    if not start <= end < _date(holdout["reserved_start"], "shared holdout start"):
        raise PreregistrationError("outcome request touches the shared final holdout")
    label = spec.cell("label_contract")
    walk = spec.cell("walk_forward_contract")
    inference = spec.cell("inference_contract")
    if request.horizon_sessions != label["horizon_sessions"]:
        raise PreregistrationError("outcome horizon changed")
    if (
        request.embargo_sessions != walk["embargo_sessions"]
        or request.embargo_sessions < request.horizon_sessions
    ):
        raise PreregistrationError("split is unpurged or embargo is too short")
    if (
        request.block_length_sessions != inference["block_length_sessions"]
        or request.block_length_sessions < request.horizon_sessions
    ):
        raise PreregistrationError("bootstrap block is shorter than the horizon")
    if request.controls != MANDATORY_CONTROLS:
        raise PreregistrationError(
            "outcome request omitted or changed a mandatory control"
        )
    return look, _request_sha256(request)


def _require_zero_access_authority() -> str:
    """Authenticate the declaration that no permanent spend authority exists."""
    try:
        path = Path(PERMANENT_LOOK_AUTHORITY_PATH).resolve(strict=True)
    except OSError as exc:
        raise PreregistrationError(
            "permanent-look authority is absent; outcome access remains zero-access"
        ) from exc
    if not path.is_file() or path.is_symlink():
        raise PreregistrationError(
            "permanent-look authority must be a regular zero-access artifact"
        )
    authority = _json_object(path.read_bytes(), "permanent-look authority")
    if set(authority) != {"schema", "authority_mode", "authority_id", "entries"}:
        raise PreregistrationError("permanent-look authority fields are invalid")
    if (
        authority["schema"] != PERMANENT_LOOK_AUTHORITY_SCHEMA
        or authority["authority_mode"] != "zero_access"
        or authority["authority_id"] != ZERO_ACCESS_AUTHORITY_ID
        or authority["entries"] != []
    ):
        raise PreregistrationError(
            "no externally pinned append-only spend authority is configured; "
            "the repository authority must remain zero-access"
        )
    return ZERO_ACCESS_AUTHORITY_ID


def authorize_outcome_access(
    spec: ReviewedPreregistration,
    request: OutcomeAccessRequest,
) -> OutcomeAccessPermit:
    """Refuse the retired v1 authority after validating the requested slice."""
    _validate_outcome_request(spec, request)
    raise PreregistrationError(LEGACY_V1_OUTCOME_AUTHORITY_RETIRED_REASON)


def assert_outcome_access_permit(
    permit: OutcomeAccessPermit,
    request: OutcomeAccessRequest | None = None,
) -> None:
    """Reject permits until an external authority can reauthenticate its receipt."""
    if (
        type(permit) is not OutcomeAccessPermit
        or getattr(permit, "_authority", None) is not _PERMIT_AUTHORITY
        or permit.holdout_exclusion_proved is not True
    ):
        raise PreregistrationError("outcome access permit is forged or malformed")
    if request is None or type(request) is not OutcomeAccessRequest:
        raise PreregistrationError(
            "permit reauthentication requires the exact approved outcome request"
        )
    if permit.request_sha256 != _request_sha256(request):
        raise PreregistrationError(
            "outcome access permit was reused for a different slice"
        )
    for name, expected in _request_payload(request).items():
        actual = getattr(permit, name)
        if name == "controls":
            expected = tuple(expected)
        if actual != expected:
            raise PreregistrationError(
                "outcome access permit does not bind the complete approved request"
            )
    _require_zero_access_authority()
    raise PreregistrationError(
        "outcome access permit cannot be authenticated without an externally "
        "pinned append-only authority"
    )


def run_authorized_outcome_slice(
    *,
    preregistration_path: Path,
    snapshot_root: Path,
    dataset_root: Path,
    repository_root: Path,
    request: OutcomeAccessRequest,
    outcome_loader: Callable[[OutcomeAccessPermit, OutcomeAccessRequest], bytes],
) -> bytes:
    """The only bounded outcome-I/O boundary; currently deliberately zero-access.

    The boundary reauthenticates the committed review, raw snapshot, normalized
    dataset, clean committed code, frozen cost cell and exact requested slice
    before seeking a spend receipt. No truthful cross-machine append-only
    authority is configured, so it fails before ``outcome_loader`` executes.
    """
    if not callable(outcome_loader):
        raise PreregistrationError("outcome_loader must be callable")
    spec = load_reviewed_preregistration(preregistration_path)
    require_reviewed_preregistration(spec)
    snapshot = load_verified_snapshot(snapshot_root)
    revalidate_verified_snapshot(snapshot)
    dataset = load_normalized_dataset(dataset_root, snapshot=snapshot)
    revalidate_normalized_dataset(dataset)
    if request.dataset_id != dataset.manifest.dataset_id:
        raise PreregistrationError(
            "requested dataset is not the authenticated normalized dataset"
        )
    lineage = capture_clean_git_lineage(repository_root)
    actual_code_identity = compute_package_source_sha256(lineage.repository_root)
    if request.code_identity != actual_code_identity:
        raise PreregistrationError(
            "requested code identity is not the clean committed package code"
        )
    _validate_outcome_request(spec, request)
    permit = authorize_outcome_access(spec, request)
    assert_outcome_access_permit(permit, request)
    payload = outcome_loader(permit, request)
    if type(payload) is not bytes:
        raise PreregistrationError("outcome loader must return exact bytes")
    return payload
