"""Frozen contracts for the defensive-carry overlay shadow stream (SHW-1).

Task-specific on purpose. This module follows the ML-LR-6 precedent
(`ml/shadow_runtime.py` + the ``ml_*`` tables) rather than generalizing
it: a generic multi-strategy adapter would hide the overlay's own
semantics — monthly cycles settled on exchange sessions, wide-band
rebalancing, per-ticker unavailability — behind a common-looking
interface (see `docs/reference/SHADOW_OBSERVATION_DESIGN.md` section 0).

Everything here is observation-only. No contract in this module can
express order, proposal, or promotion authority, and the module imports
nothing from ``ml`` or from any execution-capable path.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Mapping, Sequence

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
#: The three observed series. Frozen: adding a series is a new epoch.
SERIES_KEYS = ("carry", "combined", "universe")
#: Registration statuses. Deliberately unable to express authority,
#: mirroring `register_ml_model`'s shadow/retired-only rule.
STREAM_STATUSES = ("shadow", "closed")

_MIN_WEIGHT = Decimal("0.01")
_MAX_WEIGHT = Decimal("0.99")
_MIN_BAND = Decimal("0.01")
_MAX_BAND = Decimal("1")


class OverlayContractError(ValueError):
    """A shadow-overlay contract value is missing, malformed, or unsafe."""


def _non_empty_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OverlayContractError(f"{name} must be a non-empty string")
    return value.strip()


def _sha256_text(value: Any, name: str) -> str:
    text = _non_empty_text(value, name)
    if not _SHA256.fullmatch(text):
        raise OverlayContractError(f"{name} must be a 64-character lowercase sha256")
    return text


def _commit_text(value: Any, name: str) -> str:
    text = _non_empty_text(value, name)
    if not _COMMIT.fullmatch(text):
        raise OverlayContractError(f"{name} must be a full lowercase commit hash")
    return text


_SESSION = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _session_text(value: Any, name: str) -> str:
    text = _non_empty_text(value, name)
    # Python 3.11+ fromisoformat accepts compact "YYYYMMDD" too; the
    # canonical dashed form is required explicitly so identities never
    # fork on formatting.
    if not _SESSION.fullmatch(text):
        raise OverlayContractError(f"{name} must use canonical YYYY-MM-DD")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise OverlayContractError(f"{name} must use canonical YYYY-MM-DD") from exc
    return text


def _aware_timestamp_text(value: Any, name: str) -> str:
    text = _non_empty_text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OverlayContractError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OverlayContractError(f"{name} must be timezone-aware")
    return text


def _ticker_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise OverlayContractError(f"{name} must be a sequence of tickers")
    members = tuple(_non_empty_text(item, f"{name} member").upper() for item in value)
    if not members:
        raise OverlayContractError(f"{name} must not be empty")
    if len(set(members)) != len(members):
        raise OverlayContractError(f"{name} must not contain duplicates")
    return tuple(sorted(members))


def _bounded_fraction(value: Any, name: str, low: Decimal, high: Decimal) -> str:
    text = _non_empty_text(value, name)
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise OverlayContractError(f"{name} must be a decimal fraction") from exc
    if not parsed.is_finite() or parsed < low or parsed > high:
        raise OverlayContractError(
            f"{name} must be a finite fraction in [{low}, {high}], got {text!r}"
        )
    return text


def _finite_positive_levels(value: Any, name: str) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        raise OverlayContractError(f"{name} must be a mapping of series levels")
    if tuple(sorted(value)) != SERIES_KEYS:
        raise OverlayContractError(
            f"{name} must contain exactly the series {SERIES_KEYS}"
        )
    cleaned: dict[str, float] = {}
    for key in SERIES_KEYS:
        raw = value[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise OverlayContractError(f"{name}[{key}] must be a number")
        level = float(raw)
        if not math.isfinite(level) or level <= 0.0:
            raise OverlayContractError(f"{name}[{key}] must be finite and positive")
        cleaned[key] = level
    return MappingProxyType(cleaned)


def _finite_returns(value: Any, name: str) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        raise OverlayContractError(f"{name} must be a mapping of series returns")
    if tuple(sorted(value)) != SERIES_KEYS:
        raise OverlayContractError(
            f"{name} must contain exactly the series {SERIES_KEYS}"
        )
    cleaned: dict[str, float] = {}
    for key in SERIES_KEYS:
        raw = value[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise OverlayContractError(f"{name}[{key}] must be a number")
        result = float(raw)
        if not math.isfinite(result) or result <= -1.0:
            raise OverlayContractError(
                f"{name}[{key}] must be finite and above -100%"
            )
        cleaned[key] = result
    return MappingProxyType(cleaned)


def _refusal_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise OverlayContractError(f"{name} must be a sequence of reasons")
    return tuple(_non_empty_text(item, f"{name} entry") for item in value)


@dataclass(frozen=True)
class OverlayStreamRegistration:
    """One stream+epoch registration, bound to its preregistration doc."""

    stream_name: str
    evidence_epoch: str
    preregistration_path: str
    preregistration_sha256: str
    code_commit: str
    schedule_key: str
    schedule_version: str
    universe_members: tuple[str, ...]
    carry_members: tuple[str, ...]
    carry_weight: str
    band_fraction: str
    status: str = "shadow"

    def __post_init__(self) -> None:
        object.__setattr__(self, "stream_name", _non_empty_text(self.stream_name, "stream_name"))
        object.__setattr__(self, "evidence_epoch", _non_empty_text(self.evidence_epoch, "evidence_epoch"))
        object.__setattr__(self, "preregistration_path", _non_empty_text(self.preregistration_path, "preregistration_path"))
        object.__setattr__(self, "preregistration_sha256", _sha256_text(self.preregistration_sha256, "preregistration_sha256"))
        object.__setattr__(self, "code_commit", _commit_text(self.code_commit, "code_commit"))
        object.__setattr__(self, "schedule_key", _non_empty_text(self.schedule_key, "schedule_key"))
        object.__setattr__(self, "schedule_version", _non_empty_text(self.schedule_version, "schedule_version"))
        object.__setattr__(self, "universe_members", _ticker_tuple(self.universe_members, "universe_members"))
        object.__setattr__(self, "carry_members", _ticker_tuple(self.carry_members, "carry_members"))
        overlap = set(self.universe_members) & set(self.carry_members)
        if overlap:
            raise OverlayContractError(
                f"carry and universe members must not overlap: {sorted(overlap)}"
            )
        object.__setattr__(self, "carry_weight", _bounded_fraction(self.carry_weight, "carry_weight", _MIN_WEIGHT, _MAX_WEIGHT))
        object.__setattr__(self, "band_fraction", _bounded_fraction(self.band_fraction, "band_fraction", _MIN_BAND, _MAX_BAND))
        if self.status not in STREAM_STATUSES:
            raise OverlayContractError(
                "stream status must be one of "
                f"{STREAM_STATUSES}; authority cannot be expressed here"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "stream_name": self.stream_name,
            "evidence_epoch": self.evidence_epoch,
            "preregistration_path": self.preregistration_path,
            "preregistration_sha256": self.preregistration_sha256,
            "code_commit": self.code_commit,
            "schedule_key": self.schedule_key,
            "schedule_version": self.schedule_version,
            "universe_members": list(self.universe_members),
            "carry_members": list(self.carry_members),
            "carry_weight": self.carry_weight,
            "band_fraction": self.band_fraction,
            "status": self.status,
        }


@dataclass(frozen=True)
class OverlayObservation:
    """One cycle's observation — or its refusal, occupying the cycle slot.

    ``combined_carry_weight`` is the combined sleeve's carry weight AFTER
    this cycle's band decision — the state the next cycle advances from.
    Persisting it makes the band mechanism restart-safe and auditable
    instead of an in-memory secret.
    """

    stream_name: str
    evidence_epoch: str
    cycle_session: str
    generated_at: str
    provider: str
    inputs_sha256: str
    available: bool
    refusal_reasons: tuple[str, ...] = ()
    index_levels: Mapping[str, float] | None = None
    combined_carry_weight: float | None = None
    point_in_time_data: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "stream_name", _non_empty_text(self.stream_name, "stream_name"))
        object.__setattr__(self, "evidence_epoch", _non_empty_text(self.evidence_epoch, "evidence_epoch"))
        object.__setattr__(self, "cycle_session", _session_text(self.cycle_session, "cycle_session"))
        object.__setattr__(self, "generated_at", _aware_timestamp_text(self.generated_at, "generated_at"))
        object.__setattr__(self, "provider", _non_empty_text(self.provider, "provider"))
        object.__setattr__(self, "inputs_sha256", _sha256_text(self.inputs_sha256, "inputs_sha256"))
        if not isinstance(self.available, bool):
            raise OverlayContractError("available must be a bool")
        # SHW2-005: adjusted provider history is not point-in-time, and a
        # point-in-time claim must derive from verifiable availability
        # evidence — never from a caller's assertion. This stream has no
        # such evidence, so the only representable value is False.
        if self.point_in_time_data is not False:
            raise OverlayContractError(
                "point_in_time_data cannot be asserted by a caller; this "
                "stream's provider history is explicitly non-point-in-time"
            )
        object.__setattr__(self, "refusal_reasons", _refusal_tuple(self.refusal_reasons, "refusal_reasons"))
        if self.available:
            if self.refusal_reasons:
                raise OverlayContractError(
                    "an available observation must not carry refusal reasons"
                )
            if self.index_levels is None:
                raise OverlayContractError(
                    "an available observation must carry index levels"
                )
            object.__setattr__(self, "index_levels", _finite_positive_levels(self.index_levels, "index_levels"))
            weight = self.combined_carry_weight
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise OverlayContractError(
                    "an available observation must carry a numeric "
                    "combined_carry_weight"
                )
            weight = float(weight)
            if not math.isfinite(weight) or not 0.0 < weight < 1.0:
                raise OverlayContractError(
                    "combined_carry_weight must be a finite fraction in (0, 1)"
                )
            object.__setattr__(self, "combined_carry_weight", weight)
        else:
            if not self.refusal_reasons:
                raise OverlayContractError(
                    "a refused observation must name at least one reason"
                )
            if self.index_levels is not None:
                raise OverlayContractError(
                    "a refused observation must not carry index levels; "
                    "partial imputation is exactly the failure this refuses"
                )
            if self.combined_carry_weight is not None:
                raise OverlayContractError(
                    "a refused observation must not carry a carry weight"
                )

    def to_payload(self) -> dict[str, Any]:
        return {
            "stream_name": self.stream_name,
            "evidence_epoch": self.evidence_epoch,
            "cycle_session": self.cycle_session,
            "generated_at": self.generated_at,
            "provider": self.provider,
            "inputs_sha256": self.inputs_sha256,
            "available": self.available,
            "refusal_reasons": list(self.refusal_reasons),
            "index_levels": (
                None if self.index_levels is None else dict(self.index_levels)
            ),
            "combined_carry_weight": self.combined_carry_weight,
            "point_in_time_data": self.point_in_time_data,
        }


@dataclass(frozen=True)
class OverlayOutcome:
    """One matured monthly outcome for an AVAILABLE observation."""

    stream_name: str
    evidence_epoch: str
    cycle_session: str
    matured_at: str
    available: bool
    refusal_reasons: tuple[str, ...] = ()
    monthly_returns: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "stream_name", _non_empty_text(self.stream_name, "stream_name"))
        object.__setattr__(self, "evidence_epoch", _non_empty_text(self.evidence_epoch, "evidence_epoch"))
        object.__setattr__(self, "cycle_session", _session_text(self.cycle_session, "cycle_session"))
        object.__setattr__(self, "matured_at", _aware_timestamp_text(self.matured_at, "matured_at"))
        if not isinstance(self.available, bool):
            raise OverlayContractError("available must be a bool")
        object.__setattr__(self, "refusal_reasons", _refusal_tuple(self.refusal_reasons, "refusal_reasons"))
        if self.available:
            if self.refusal_reasons:
                raise OverlayContractError(
                    "an available outcome must not carry refusal reasons"
                )
            if self.monthly_returns is None:
                raise OverlayContractError(
                    "an available outcome must carry monthly returns"
                )
            object.__setattr__(self, "monthly_returns", _finite_returns(self.monthly_returns, "monthly_returns"))
        else:
            if not self.refusal_reasons:
                raise OverlayContractError(
                    "an unavailable outcome must name at least one reason"
                )
            if self.monthly_returns is not None:
                raise OverlayContractError(
                    "an unavailable outcome must not carry returns"
                )

    def to_payload(self) -> dict[str, Any]:
        return {
            "stream_name": self.stream_name,
            "evidence_epoch": self.evidence_epoch,
            "cycle_session": self.cycle_session,
            "matured_at": self.matured_at,
            "available": self.available,
            "refusal_reasons": list(self.refusal_reasons),
            "monthly_returns": (
                None if self.monthly_returns is None else dict(self.monthly_returns)
            ),
        }


# ---------------------------------------------------------------------------
# Pure cycle computation (SHW-2). No I/O, no persistence, no clock: the
# scripts/run_overlay_shadow.py adapter owns fetching and storage, mirroring
# the ml/shadow_runtime.py / run_ml_shadow.py split.
# ---------------------------------------------------------------------------


def completed_month_end_sessions(sessions: Sequence[date]) -> tuple[date, ...]:
    """Last session of every month that has a session in a LATER month.

    The in-progress month is deliberately absent: its "month end" is not
    known until a later month's session proves the month closed. Sessions
    must be strictly ascending; duplicates or disorder refuse loudly.
    """
    ordered = list(sessions)
    if any(not isinstance(item, date) for item in ordered):
        raise OverlayContractError("sessions must be date objects")
    if any(b <= a for a, b in zip(ordered, ordered[1:])):
        raise OverlayContractError("sessions must be strictly ascending")
    ends: list[date] = []
    for current, following in zip(ordered, ordered[1:]):
        if (current.year, current.month) != (following.year, following.month):
            ends.append(current)
    return tuple(ends)


def sleeve_return(
    previous_closes: Mapping[str, float],
    current_closes: Mapping[str, float],
    members: Sequence[str],
) -> tuple[float | None, tuple[str, ...]]:
    """Equal-weight mean return of the sleeve, or None plus the tickers
    that made it uncomputable. A single bad member refuses the WHOLE
    sleeve — per-ticker imputation is the contract's forbidden failure."""
    missing: list[str] = []
    returns: list[float] = []
    for ticker in members:
        before = previous_closes.get(ticker)
        after = current_closes.get(ticker)
        usable = (
            isinstance(before, (int, float)) and not isinstance(before, bool)
            and isinstance(after, (int, float)) and not isinstance(after, bool)
            and math.isfinite(float(before)) and math.isfinite(float(after))
            and float(before) > 0.0 and float(after) > 0.0
        )
        if not usable:
            missing.append(ticker)
            continue
        returns.append(float(after) / float(before) - 1.0)
    if missing:
        return None, tuple(sorted(missing))
    return sum(returns) / len(returns), ()


def advance_overlay(
    *,
    level: float,
    carry_weight: float,
    universe_return: float,
    carry_return: float,
    carry_target: float,
    band_fraction: float,
) -> tuple[float, float, bool]:
    """One band-rebalance step of the combined sleeve.

    Grow both sleeves by their returns, then rebalance the carry weight
    to target ONLY if drift pushed it outside the relative band
    (target * (1 +/- band)) — the operational wide-band mechanism. Returns
    (new_level, new_carry_weight, rebalanced).
    """
    for name, value in (("level", level), ("carry_weight", carry_weight),
                        ("universe_return", universe_return),
                        ("carry_return", carry_return),
                        ("carry_target", carry_target),
                        ("band_fraction", band_fraction)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(float(value)):
            raise OverlayContractError(f"{name} must be a finite number")
    if not 0.0 < carry_weight < 1.0 or not 0.0 < carry_target < 1.0:
        raise OverlayContractError("carry weights must be fractions in (0, 1)")
    if level <= 0.0:
        raise OverlayContractError("level must be positive")
    carry_part = carry_weight * (1.0 + carry_return)
    universe_part = (1.0 - carry_weight) * (1.0 + universe_return)
    total = carry_part + universe_part
    if total <= 0.0:
        raise OverlayContractError(
            "combined sleeve NAV would be non-positive; refusing to price a "
            "wiped-out book"
        )
    new_level = level * total
    drifted = carry_part / total
    low = carry_target * (1.0 - band_fraction)
    high = carry_target * (1.0 + band_fraction)
    if drifted < low or drifted > high:
        return new_level, carry_target, True
    return new_level, drifted, False
