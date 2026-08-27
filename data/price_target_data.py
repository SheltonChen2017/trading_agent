"""Legacy analyst price-target consensus data for advisory display only.

This module is deliberately outside ``research.analyst_revisions_v2``. It
retains the historical trimmed-consensus feature without allowing its weaker
provider contract to become V2 evidence.

Publication instants and effective sessions are different types here:

* yfinance publication indexes must be timezone-aware instants;
* those instants are converted through the real NYSE calendar (including
  holidays and half days);
* returned history uses timezone-naive, midnight ``effective_session`` labels,
  because a session label is a date rather than an instant.

The returned frame has one exact schema: a ``DatetimeIndex`` named
``effective_session`` and exactly ``[firm, price_target]`` columns. Direct
consensus callers are held to the same contract.
"""
from __future__ import annotations

import math
from enum import Enum
from numbers import Real

import pandas as pd

from config import (
    ANALYST_TARGET_METHOD,
    ANALYST_TARGET_MIN_ANALYSTS,
    ANALYST_TARGET_STALENESS_DAYS,
)
from data.exchange_calendar import (
    ExchangeCalendarError,
    is_trading_session,
    resolve_nth_session_after,
    session_close_instant,
)


PRICE_TARGET_COLUMNS = ("firm", "price_target")
EFFECTIVE_SESSION_INDEX = "effective_session"
_EXCHANGE_TIMEZONE = "America/New_York"


class PriceTargetContractError(ValueError):
    """Legacy price-target evidence is malformed or semantically ambiguous."""


class ConsensusMethod(str, Enum):
    """The only aggregation semantics supported by the legacy feature."""

    MEAN = "mean"
    MEDIAN = "median"


try:
    _DEFAULT_CONSENSUS_METHOD = ConsensusMethod(ANALYST_TARGET_METHOD)
except ValueError as exc:  # configuration ambiguity must fail, not silently mean
    raise PriceTargetContractError(
        "ANALYST_TARGET_METHOD must be exactly 'mean' or 'median'"
    ) from exc


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "firm": pd.Series(dtype="object"),
            "price_target": pd.Series(dtype="float64"),
        },
        index=pd.DatetimeIndex([], name=EFFECTIVE_SESSION_INDEX),
    )


def _consensus_method(value: ConsensusMethod | str) -> ConsensusMethod:
    if isinstance(value, ConsensusMethod):
        return value
    if type(value) is str:
        try:
            return ConsensusMethod(value)
        except ValueError:
            pass
    raise PriceTargetContractError("method must be exactly 'mean' or 'median'")


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PriceTargetContractError(f"{name} must be a non-negative integer")
    return value


def _minimum_analysts(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 3:
        raise PriceTargetContractError(
            "min_analysts must be an integer of at least 3 for two-sided trimming"
        )
    return value


def validate_effective_session(
    value: object, name: str = "effective_session"
) -> pd.Timestamp:
    """Validate a canonical timezone-free NYSE session-date label."""
    if not isinstance(value, pd.Timestamp):
        raise PriceTargetContractError(f"{name} must be a pandas Timestamp session label")
    if value.tzinfo is not None:
        raise PriceTargetContractError(
            f"{name} is a session label and must not carry an instant timezone"
        )
    if pd.isna(value) or value != value.normalize():
        raise PriceTargetContractError(f"{name} must be a normalized session date")
    session = value.date().isoformat()
    try:
        if not is_trading_session(session):
            raise PriceTargetContractError(f"{name} is not an NYSE trading session")
    except ExchangeCalendarError as exc:
        raise PriceTargetContractError(f"{name} cannot be verified: {exc}") from exc
    return value


def _effective_session(publication: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(publication)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise PriceTargetContractError(
            "provider publication index must contain timezone-aware instants"
        )
    publication_utc = timestamp.tz_convert("UTC")
    publication_date = publication_utc.tz_convert(_EXCHANGE_TIMEZONE).date().isoformat()
    try:
        if (
            is_trading_session(publication_date)
            and publication_utc.to_pydatetime()
            < session_close_instant(publication_date)
        ):
            effective = publication_date
        else:
            effective = resolve_nth_session_after(publication_date, 1)
    except ExchangeCalendarError as exc:
        raise PriceTargetContractError(
            f"provider publication session cannot be resolved: {exc}"
        ) from exc
    return pd.Timestamp(effective)


def _validate_history(history: pd.DataFrame) -> None:
    if not isinstance(history, pd.DataFrame):
        raise PriceTargetContractError("history must be a pandas DataFrame")
    if tuple(history.columns) != PRICE_TARGET_COLUMNS:
        raise PriceTargetContractError(
            "history columns must be exactly ['firm', 'price_target'] in that order"
        )
    if not isinstance(history.index, pd.DatetimeIndex):
        raise PriceTargetContractError("history index must be a DatetimeIndex")
    if history.index.name != EFFECTIVE_SESSION_INDEX:
        raise PriceTargetContractError(
            "history index must be named 'effective_session'"
        )
    if history.index.tz is not None:
        raise PriceTargetContractError(
            "history index contains session labels and must be timezone-naive"
        )
    if history.index.hasnans:
        raise PriceTargetContractError("history index cannot contain NaT")
    if not history.index.is_monotonic_increasing:
        raise PriceTargetContractError("history index must be monotonic increasing")
    if any(timestamp != timestamp.normalize() for timestamp in history.index):
        raise PriceTargetContractError("history index must contain normalized sessions")
    for timestamp in history.index.unique():
        validate_effective_session(timestamp, "history effective_session")

    firms: list[str] = []
    for value in history["firm"].tolist():
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(character) < 32 for character in value)
        ):
            raise PriceTargetContractError(
                "history firm values must be non-empty trimmed text"
            )
        firms.append(value)
    for value in history["price_target"].tolist():
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            or float(value) <= 0
        ):
            raise PriceTargetContractError(
                "history price_target values must be finite positive numbers"
            )
    if history.assign(_firm=firms).reset_index().duplicated(
        [EFFECTIVE_SESSION_INDEX, "_firm"]
    ).any():
        raise PriceTargetContractError(
            "history must contain at most one row per (effective_session, firm)"
        )


def _normalize_provider_history(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if not isinstance(raw, pd.DataFrame):
        raise PriceTargetContractError(f"{ticker}: provider history is not a DataFrame")
    required = {"Firm", "currentPriceTarget"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise PriceTargetContractError(
            f"{ticker}: provider history is missing required columns {missing}"
        )
    if not isinstance(raw.index, pd.DatetimeIndex) or raw.index.tz is None:
        raise PriceTargetContractError(
            f"{ticker}: provider history index must be timezone-aware"
        )
    if raw.index.hasnans:
        raise PriceTargetContractError(f"{ticker}: provider history index contains NaT")

    ordered = raw.sort_index(kind="mergesort")
    numeric_targets = pd.to_numeric(
        ordered["currentPriceTarget"], errors="coerce"
    )
    valid_targets = numeric_targets.map(
        lambda value: pd.notna(value)
        and math.isfinite(float(value))
        and float(value) > 0
    )
    valid_firms = ordered["Firm"].map(
        lambda value: isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(ord(character) < 32 for character in value)
    )
    prepared = ordered.assign(_price_target=numeric_targets)
    selected = prepared.loc[
        valid_targets & valid_firms, ["Firm", "_price_target"]
    ].copy()
    if selected.empty:
        return _empty_history()
    selected["price_target"] = selected.pop("_price_target").astype(float)
    selected["effective_session"] = [
        _effective_session(timestamp) for timestamp in selected.index
    ]
    selected = selected.rename(columns={"Firm": "firm"})
    # A firm can publish more than once in one session. The exact legacy
    # schema contains one row per firm/session, so retain the latest aware
    # publication after the stable timestamp sort.
    selected = selected.drop_duplicates(
        ["effective_session", "firm"], keep="last"
    )
    normalized = (
        selected.set_index("effective_session")[["firm", "price_target"]]
        .sort_index(kind="mergesort")
    )
    normalized.index = pd.DatetimeIndex(
        normalized.index, name=EFFECTIVE_SESSION_INDEX
    )
    _validate_history(normalized)
    return normalized


def fetch_price_target_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Fetch canonical legacy price-target histories from yfinance.

    Missing/zero/nonfinite target rows represent actions without a usable
    dollar target and are omitted. A non-empty provider payload with an
    unverifiable schema or timezone refuses instead of fabricating a session.
    """
    import yfinance as yf  # lazy: this advisory fetch is not a V2 dependency

    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            raw = yf.Ticker(ticker).upgrades_downgrades
        except (KeyError, TypeError, AttributeError, ValueError):
            continue
        if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
            continue
        data[ticker] = _normalize_provider_history(raw, ticker)
    return data


def compute_consensus_price_target(
    history: pd.DataFrame,
    as_of: pd.Timestamp,
    staleness_days: int = ANALYST_TARGET_STALENESS_DAYS,
    min_analysts: int = ANALYST_TARGET_MIN_ANALYSTS,
    method: ConsensusMethod | str = _DEFAULT_CONSENSUS_METHOD,
) -> float | None:
    """Return the finite positive trimmed consensus for one NYSE session."""
    aggregation = _consensus_method(method)
    staleness_days = _nonnegative_int(staleness_days, "staleness_days")
    min_analysts = _minimum_analysts(min_analysts)
    as_of = validate_effective_session(as_of, "as_of")
    _validate_history(history)
    if history.empty:
        return None

    window_start = as_of - pd.Timedelta(days=staleness_days)
    window = history[(history.index <= as_of) & (history.index >= window_start)]
    if window.empty:
        return None

    latest_per_firm = (
        window.sort_index(kind="mergesort")
        .groupby("firm", sort=True)["price_target"]
        .last()
    )
    if len(latest_per_firm) < min_analysts:
        return None

    trimmed = latest_per_firm.sort_values().iloc[1:-1]
    if trimmed.empty:
        return None
    result = float(
        trimmed.median()
        if aggregation is ConsensusMethod.MEDIAN
        else trimmed.mean()
    )
    if not math.isfinite(result) or result <= 0:  # defense beyond input contract
        raise PriceTargetContractError(
            "computed consensus must be a finite positive number"
        )
    return result
