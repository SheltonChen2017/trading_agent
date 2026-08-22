"""Immutable, provider-neutral results passed from research to the assistant.

These contracts contain measurements only. They carry no proposal, approval,
broker, execution, database, or licensed-row authority. The assistant validates
their input bindings before using them; the research product owns how they are
computed.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any, Literal

import pandas as pd


RESEARCH_RESULT_SCHEMA_VERSION = "1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ResearchResultContractError(ValueError):
    """A cross-product result is malformed or not bound to its inputs."""


def research_parameters_sha256(parameters: Mapping[str, Any]) -> str:
    """Hash caller-owned JSON parameters without interpreting their policy."""
    try:
        encoded = json.dumps(
            dict(parameters),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResearchResultContractError(
            "research parameters must be finite JSON values"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def close_series_sha256(series: pd.Series) -> str:
    """Hash an ordered close series using explicit timestamp/value strings."""
    if not isinstance(series, pd.Series):
        raise ResearchResultContractError("close history must be a pandas Series")
    if series.empty:
        raise ResearchResultContractError("close history cannot be empty")
    if series.index.has_duplicates:
        raise ResearchResultContractError("close history cannot repeat timestamps")
    if not series.index.is_monotonic_increasing:
        raise ResearchResultContractError("close history must be time-ordered")

    rows: list[list[str]] = []
    for index, raw_value in series.items():
        if isinstance(raw_value, bool):
            raise ResearchResultContractError("close values cannot be booleans")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ResearchResultContractError(
                f"close value at {index!r} is not numeric"
            ) from exc
        if not math.isfinite(value) or value <= 0:
            raise ResearchResultContractError(
                f"close value at {index!r} must be positive and finite"
            )
        timestamp = (
            index.isoformat()
            if hasattr(index, "isoformat")
            else str(index)
        )
        rows.append([timestamp, format(value, ".17g")])
    encoded = json.dumps(rows, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_text(name: str, value: str, *, max_length: int = 200) -> None:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ResearchResultContractError(
            f"{name} must be non-empty text no longer than {max_length} characters"
        )
    if "\n" in value or "\r" in value:
        raise ResearchResultContractError(f"{name} cannot contain a newline")


def _require_ticker(name: str, value: str) -> None:
    _require_text(name, value, max_length=32)
    if value != value.upper() or value.strip() != value:
        raise ResearchResultContractError(
            f"{name} must be canonical uppercase text"
        )


def _require_sha256(name: str, value: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ResearchResultContractError(f"{name} must be a lowercase SHA-256")


@dataclasses.dataclass(frozen=True)
class SignalTriggerResult:
    """One non-authoritative signal observation safe for assistant display."""

    rule: str
    direction: Literal["dip", "up"]
    date: str
    return_zscore: float
    volume_zscore: float

    def __post_init__(self) -> None:
        _require_text("rule", self.rule)
        _require_text("date", self.date, max_length=64)
        if self.direction not in {"dip", "up"}:
            raise ResearchResultContractError("direction must be 'dip' or 'up'")
        for name, value in (
            ("return_zscore", self.return_zscore),
            ("volume_zscore", self.volume_zscore),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ResearchResultContractError(f"{name} must be numeric")
            if not math.isfinite(float(value)):
                raise ResearchResultContractError(f"{name} must be finite")

    def to_dict(self) -> dict[str, str | float]:
        return {
            "rule": self.rule,
            "direction": self.direction,
            "date": self.date,
            "return_zscore": round(float(self.return_zscore), 2),
            "volume_zscore": round(float(self.volume_zscore), 2),
        }


@dataclasses.dataclass(frozen=True)
class TickerSignalResearchResult:
    """Read-only per-ticker trigger result; raw price history is excluded."""

    ticker: str
    as_of: str | None
    triggers: tuple[SignalTriggerResult, ...]
    schema_version: str = RESEARCH_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_ticker("ticker", self.ticker)
        if self.schema_version != RESEARCH_RESULT_SCHEMA_VERSION:
            raise ResearchResultContractError(
                f"unsupported research-result schema {self.schema_version!r}"
            )
        if self.as_of is not None:
            _require_text("as_of", self.as_of, max_length=64)
        if not isinstance(self.triggers, tuple) or not all(
            isinstance(trigger, SignalTriggerResult) for trigger in self.triggers
        ):
            raise ResearchResultContractError(
                "triggers must be a tuple of SignalTriggerResult objects"
            )


@dataclasses.dataclass(frozen=True)
class LeveragedPairResearchResult:
    """Input-bound target measurement for one stable/leveraged pair."""

    stable_ticker: str
    leveraged_ticker: str
    as_of: str
    target_leveraged_weight: float | None
    label: str
    stable_close_sha256: str
    leveraged_close_sha256: str
    parameters_sha256: str
    schema_version: str = RESEARCH_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_ticker("stable_ticker", self.stable_ticker)
        _require_ticker("leveraged_ticker", self.leveraged_ticker)
        if self.stable_ticker == self.leveraged_ticker:
            raise ResearchResultContractError("pair tickers must be different")
        _require_text("as_of", self.as_of, max_length=64)
        _require_text("label", self.label)
        for name, digest in (
            ("stable_close_sha256", self.stable_close_sha256),
            ("leveraged_close_sha256", self.leveraged_close_sha256),
            ("parameters_sha256", self.parameters_sha256),
        ):
            _require_sha256(name, digest)
        if self.schema_version != RESEARCH_RESULT_SCHEMA_VERSION:
            raise ResearchResultContractError(
                f"unsupported research-result schema {self.schema_version!r}"
            )
        target = self.target_leveraged_weight
        if target is not None:
            if isinstance(target, bool) or not isinstance(target, (int, float)):
                raise ResearchResultContractError(
                    "target_leveraged_weight must be numeric or None"
                )
            if not math.isfinite(float(target)) or float(target) < 0:
                raise ResearchResultContractError(
                    "target_leveraged_weight must be finite and non-negative"
                )


__all__ = [
    "LeveragedPairResearchResult",
    "RESEARCH_RESULT_SCHEMA_VERSION",
    "ResearchResultContractError",
    "SignalTriggerResult",
    "TickerSignalResearchResult",
    "close_series_sha256",
    "research_parameters_sha256",
]
