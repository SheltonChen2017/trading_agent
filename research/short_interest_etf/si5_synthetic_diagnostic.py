"""Executable SI-5 R(20) arithmetic rehearsal, never historical evaluation.

The public runner accepts a fixed checked-in scenario name, not caller prices,
dates, memberships or an asserted PIT/synthetic flag. The private kernel is
testable without making its result a source-admission or research receipt.
This gross price diagnostic is deliberately separate from order cashflows:
splits affect share-equivalent prices; dividends and fees do not enter R(20).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from data.exchange_calendar import resolve_nth_session_after, session_open_instant
from data.financial_primitives import decimal_text
from data.hashing import hash_payload
from research.short_interest_etf.contracts import format_utc_timestamp
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    require_si5_offline_protocol,
)
from research.short_interest_etf.si5_synthetic_policy import (
    SI5_SYNTHETIC_POLICY_SHA256,
    synthetic_policy_payload,
)

SI5_SYNTHETIC_DIAGNOSTIC_ID = "si5-gross-r20-arithmetic-rehearsal-v1"
_LOOKBACKS = (20, 60, 120, 252)
_MINIMUM_COMMON = 10


class SI5SyntheticDiagnosticError(ValueError):
    """The rehearsal input, policy or retained result is not canonical."""


def _refuse(detail: str) -> SI5SyntheticDiagnosticError:
    return SI5SyntheticDiagnosticError(f"REFUSED: {detail}")


def _positive_decimal(value: Any, name: str) -> Fraction:
    if type(value) is not str or not value or len(value) > 128 or any(
        char not in "0123456789." for char in value
    ):
        raise _refuse(f"{name} must be canonical positive decimal text")
    try:
        if decimal_text(value) != value or Fraction(value) <= 0:
            raise ValueError("noncanonical or nonpositive")
        return Fraction(value)
    except ValueError as exc:
        raise _refuse(f"{name} must be canonical positive decimal text") from exc


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise _refuse(f"{name} must be canonical nonempty text")
    return value


def _rational(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _mean(values: tuple[Fraction, ...]) -> Fraction:
    return sum(values, Fraction(0)) / len(values)


@dataclass(frozen=True, slots=True)
class _PricePair:
    """A private fabricated raw-open pair; not an admitted market record."""

    security_id: str
    entry_session: str
    exit_session: str
    entry_open_usd: str | None
    exit_open_usd: str | None
    cumulative_split_ratio: Fraction = Fraction(1)
    terminal_before_horizon: bool = False

    def to_payload(self) -> dict[str, Any]:
        _text(self.security_id, "security_id")
        expected = resolve_nth_session_after(self.entry_session, 20)
        if self.exit_session != expected:
            raise _refuse("R20 exit must be the 20th later XNYS session")
        entry_at = format_utc_timestamp(session_open_instant(self.entry_session))
        exit_at = format_utc_timestamp(session_open_instant(self.exit_session))
        for name in ("entry_open_usd", "exit_open_usd"):
            if getattr(self, name) is not None:
                _positive_decimal(getattr(self, name), name)
        if type(self.cumulative_split_ratio) is not Fraction or (
            self.cumulative_split_ratio <= 0
        ):
            raise _refuse("split ratio must be an exact positive rational")
        if type(self.terminal_before_horizon) is not bool:
            raise _refuse("terminal marker must be an exact bool")
        return {
            "security_id": self.security_id,
            "entry_session": self.entry_session,
            "exit_session": self.exit_session,
            "entry_at": entry_at,
            "exit_at": exit_at,
            "entry_open_usd": self.entry_open_usd,
            "exit_open_usd": self.exit_open_usd,
            "cumulative_split_ratio": _rational(self.cumulative_split_ratio),
            "terminal_before_horizon": self.terminal_before_horizon,
        }


@dataclass(frozen=True, slots=True)
class _Window:
    lookback_sessions: int
    full_security_ids: tuple[str, ...]
    low_pressure_ids: tuple[str, ...]
    high_pressure_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        if type(self.lookback_sessions) is not int or (
            self.lookback_sessions not in _LOOKBACKS
        ):
            raise _refuse("candidate lookback is not one of all four frozen windows")
        for name in ("full_security_ids", "low_pressure_ids", "high_pressure_ids"):
            members = getattr(self, name)
            if type(members) is not tuple or len(members) != len(set(members)):
                raise _refuse(f"{name} must be a unique tuple")
            for identity in members:
                _text(identity, name)
        full = set(self.full_security_ids)
        if not set(self.low_pressure_ids) <= full or not set(self.high_pressure_ids) <= full:
            raise _refuse("original pressure tail is outside its full population")
        if set(self.low_pressure_ids) & set(self.high_pressure_ids):
            raise _refuse("complementary pressure tails overlap")
        return {
            "lookback_sessions": self.lookback_sessions,
            "full_security_ids": list(self.full_security_ids),
            "low_pressure_ids": list(self.low_pressure_ids),
            "high_pressure_ids": list(self.high_pressure_ids),
        }


@dataclass(frozen=True, slots=True)
class _Release:
    release_id: str
    entry_session: str
    windows: tuple[_Window, ...]
    prices: tuple[_PricePair, ...]

    def to_payload(self) -> dict[str, Any]:
        _text(self.release_id, "release_id")
        session_open_instant(self.entry_session)
        if type(self.windows) is not tuple or len(self.windows) != 4 or any(
            type(window) is not _Window for window in self.windows
        ) or {window.lookback_sessions for window in self.windows} != set(_LOOKBACKS):
            raise _refuse("release requires exactly all four candidate windows")
        if type(self.prices) is not tuple or any(type(row) is not _PricePair for row in self.prices):
            raise _refuse("prices require exact private price-pair types")
        if len({row.security_id for row in self.prices}) != len(self.prices):
            raise _refuse("duplicate security price pair")
        for row in self.prices:
            if row.entry_session != self.entry_session:
                raise _refuse("price pair belongs to another release/open")
        return {
            "release_id": self.release_id,
            "entry_session": self.entry_session,
            "windows": [window.to_payload() for window in self.windows],
            "prices": [row.to_payload() for row in self.prices],
        }


def _evaluate_release(release: _Release) -> dict[str, Any]:
    if type(release) is not _Release:
        raise _refuse("release must be the exact private rehearsal type")
    source = release.to_payload()
    common = set.intersection(*(set(window.full_security_ids) for window in release.windows))
    prices = {row.security_id: row for row in release.prices}
    full_union = set.union(*(set(window.full_security_ids) for window in release.windows))
    if not set(prices) <= full_union:
        raise _refuse("price row is outside every predeclared full population")
    reasons: list[str] = []
    if len(common) < _MINIMUM_COMMON:
        reasons.append("underfilled_common_intersection")
    returns: dict[str, Fraction] = {}
    refusals = []
    # Every common member is represented, including missing baseline/price rows.
    # A refusal blocks the entire release for all four, not just a losing tail.
    for security in sorted(common):
        row = prices.get(security)
        refusal = None
        if row is None:
            refusal = "missing_price_pair"
        elif row.terminal_before_horizon:
            refusal = "terminal_value_rule_unbound"
        elif row.entry_open_usd is None or row.exit_open_usd is None:
            refusal = "missing_exact_horizon_open"
        if refusal is not None:
            refusals.append({"security_id": security, "reason": refusal})
        else:
            returns[security] = (
                _positive_decimal(row.exit_open_usd, "exit_open_usd")
                * row.cumulative_split_ratio
                / _positive_decimal(row.entry_open_usd, "entry_open_usd") - 1
            )
    if refusals:
        reasons.append("incomplete_common_outcomes")
    projected = []
    for window in sorted(release.windows, key=lambda item: item.lookback_sessions):
        low = tuple(security for security in window.low_pressure_ids if security in common)
        high = tuple(security for security in window.high_pressure_ids if security in common)
        if len(window.full_security_ids) < _MINIMUM_COMMON:
            reasons.append("underfilled_full_cohort")
        if not low:
            reasons.append("missing_common_low_pressure_tail")
        if not high:
            reasons.append("missing_common_high_pressure_tail")
        projected.append({
            "lookback_sessions": window.lookback_sessions,
            "full_population_sha256": hash_payload(window.to_payload()),
            "low_pressure_ids": list(low),
            "high_pressure_ids": list(high),
        })
    # One shared disposition avoids selectively removing release dates/windows.
    comparable = not reasons
    for output in projected:
        output["low_mean_R20"] = None
        output["high_mean_R20"] = None
        output["low_minus_high_R20"] = None
        if comparable:
            low_mean = _mean(tuple(returns[item] for item in output["low_pressure_ids"]))
            high_mean = _mean(tuple(returns[item] for item in output["high_pressure_ids"]))
            output["low_mean_R20"] = _rational(low_mean)
            output["high_mean_R20"] = _rational(high_mean)
            output["low_minus_high_R20"] = _rational(low_mean - high_mean)
    return {
        "release_id": release.release_id,
        "source_fixture_release_sha256": hash_payload(source),
        "common_security_ids": sorted(common),
        "comparable": comparable,
        "no_comparison_reasons": sorted(set(reasons)),
        "refusals": refusals,
        "windows": projected,
    }


def _evaluate_synthetic_kernel(releases: tuple[_Release, ...]) -> dict[str, Any]:
    if type(releases) is not tuple or not releases or any(type(row) is not _Release for row in releases):
        raise _refuse("kernel requires nonempty exact private releases")
    if len({row.release_id for row in releases}) != len(releases) or (
        len({row.entry_session for row in releases}) != len(releases)
    ):
        raise _refuse("duplicate release/date is not an independent observation")
    outputs = [_evaluate_release(release) for release in sorted(releases, key=lambda row: row.entry_session)]
    comparable = all(row["comparable"] for row in outputs)
    aggregates = []
    for lookback in _LOOKBACKS:
        values = []
        for row in outputs:
            window = next(item for item in row["windows"] if item["lookback_sessions"] == lookback)
            if window["low_minus_high_R20"] is not None:
                ratio = window["low_minus_high_R20"]
                values.append(Fraction(ratio["numerator"], ratio["denominator"]))
        aggregates.append({
            "lookback_sessions": lookback,
            "mean_release_contrast": _rational(_mean(tuple(values))) if comparable else None,
            "comparable_release_count": len(values),
            "expected_release_count": len(outputs),
        })
    return {
        "releases": outputs,
        "aggregate_comparable": comparable,
        "candidate_aggregates": aggregates,
        "selected_lookback": None,
        "effective_independent_sample_count": None,
        "power_verified": False,
        "market_edge_evidence": False,
    }


def _fixture() -> tuple[_Release, ...]:
    # These invented values have no ticker/provider correspondence. Ten and
    # twenty distinct-score identities give one and two inclusive 10% tail
    # members respectively; tests detect ticker-weighting across release dates.
    releases = []
    for number, session in enumerate(("2024-02-13", "2024-03-04")):
        population_size = 10 * (number + 1)
        ids = tuple(f"SYNTHETIC-{index:02d}" for index in range(population_size))
        exit_session = resolve_nth_session_after(session, 20)
        tail_size = number + 1
        windows = tuple(_Window(window, ids, ids[:tail_size], ids[-tail_size:]) for window in _LOOKBACKS)
        prices = tuple(_PricePair(
            security, session, exit_session, "100",
            "110" if index < tail_size else ("90" if index >= population_size - tail_size else "100"),
        ) for index, security in enumerate(ids))
        releases.append(_Release(f"SYNTHETIC-RELEASE-{number}", session, windows, prices))
    return tuple(releases)


# The literal digest is populated once from the fixed constructed fixture,
# not from a caller's payload or a synthetic=true assertion.
SI5_SYNTHETIC_DIAGNOSTIC_FIXTURE_SHA256 = "bdd8fe1d208384fa01de88812366713b606e98cf0a9861b035ebbdf177c3707d"


@dataclass(frozen=True, slots=True, init=False)
class SI5SyntheticDiagnosticResult:
    _payload: dict[str, Any] = field(repr=False)
    _sha256: str = field(repr=False)

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not SI5SyntheticDiagnosticResult:
            raise _refuse("result must be the exact synthetic diagnostic type")
        expected = _run_payload()
        if (
            type(self._payload) is not dict
            or type(self._sha256) is not str
            or hash_payload(self._payload) != hash_payload(expected)
            or self._sha256 != expected["result_sha256"]
        ):
            raise _refuse("synthetic diagnostic result or provenance changed")
        return deepcopy(expected)

    @property
    def sha256(self) -> str:
        return SI5SyntheticDiagnosticResult.to_payload(self)["result_sha256"]


def _run_payload() -> dict[str, Any]:
    protocol_sha256 = require_si5_offline_protocol(SI5_OFFLINE_PROTOCOL)
    releases = _fixture()
    fixture_sha256 = hash_payload([release.to_payload() for release in releases])
    if fixture_sha256 != SI5_SYNTHETIC_DIAGNOSTIC_FIXTURE_SHA256:
        raise _refuse("fixed synthetic diagnostic fixture changed")
    payload = {
        "schema": SI5_SYNTHETIC_DIAGNOSTIC_ID,
        "demonstration_policy": synthetic_policy_payload(),
        "demonstration_policy_sha256": SI5_SYNTHETIC_POLICY_SHA256,
        "fixture_sha256": fixture_sha256,
        "offline_protocol_sha256": protocol_sha256,
        "return_basis": SI5_OFFLINE_PROTOCOL.primary_return_semantic,
        "diagnostic_cost_bps_per_side": 0,
        "synthetic_only": True,
        "source_ranking_linked": False,
        "source_admitted": False,
        "actual_pit_coverage_verified": False,
        "outcome_access_authorized": False,
        "qc_backtest_authorized": False,
        "trading_authority": False,
        "real_backtesting_ready": False,
        "authorized_real_outcome_looks": 0,
        "consumed_real_outcome_looks": 0,
        "diagnostic": _evaluate_synthetic_kernel(releases),
    }
    payload["result_sha256"] = hash_payload(payload)
    return payload


def run_si5_synthetic_diagnostic_scenario(
    scenario_id: str = SI5_SYNTHETIC_DIAGNOSTIC_ID,
) -> SI5SyntheticDiagnosticResult:
    if type(scenario_id) is not str or scenario_id != SI5_SYNTHETIC_DIAGNOSTIC_ID:
        raise _refuse("only the fixed built-in synthetic diagnostic is supported")
    payload = _run_payload()
    result = object.__new__(SI5SyntheticDiagnosticResult)
    object.__setattr__(result, "_payload", deepcopy(payload))
    object.__setattr__(result, "_sha256", payload["result_sha256"])
    return result
