"""ML-LR-3: portfolio-volatility targets (live-readiness plan section 9.2).

Pure functions over ALREADY-LOADED position and equity records. This module
imports no broker and no execution service (plan 9.2) -- it is handed
records and returns targets, which is what keeps it a research surface and
keeps `tests/test_ml_import_boundary.py` green.

Two DIFFERENT targets, never silently substituted for each other:

  1. `build_frozen_weight_targets()` -- weights known at `as_of_session`
     applied to the next `horizon_sessions` of aligned security returns.
     This answers "how volatile was the book I actually held?"
  2. `build_realized_account_targets()` -- flow-adjusted account-equity
     returns, usable only when daily equity and external-flow coverage are
     complete. This answers "how volatile was the account?"

They are not interchangeable. The frozen-weight target holds the portfolio
constant and measures only market movement; the realized target includes
every intra-horizon trade the owner made. A model trained on one and
evaluated against the other would be scored on a quantity it never
predicted, so each function returns its own type and neither falls back to
the other.

UNIT CONVENTION (plan 9.3), enforced by the type system rather than by
comment: every target is a daily-return standard deviation IN PERCENT,
matching `ml/labels.py`'s `compute_forward_realized_vol_labels`. Annualized
values exist only as an explicitly-named display field. Doc 9.3: "Do not
compare a daily-percent target with an annualized baseline."
"""
from __future__ import annotations

import dataclasses
import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from assistant.money import to_decimal
from ml.hashing import hash_payload

TRADING_SESSIONS_PER_YEAR = 252
CASH_TICKER = "__CASH__"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PortfolioVolatilityError(ValueError):
    """Position/equity records cannot support a trustworthy target."""


def _parse_session(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise PortfolioVolatilityError(f"{name} must use canonical YYYY-MM-DD format")
    try:
        parsed = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise PortfolioVolatilityError(
            f"{name} must use canonical YYYY-MM-DD format"
        ) from exc
    if pd.isna(parsed) or str(parsed.date()) != value:
        raise PortfolioVolatilityError(f"{name} must use canonical YYYY-MM-DD format")
    return value


def _parse_instant(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PortfolioVolatilityError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioVolatilityError(
            f"{name} must be a timezone-aware ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PortfolioVolatilityError(f"{name} must be timezone-aware")
    return parsed


@dataclasses.dataclass(frozen=True)
class PortfolioVolatilityTarget:
    """One realized forward portfolio volatility observation.

    `target_kind` is part of the record, not an assumption a consumer has to
    remember -- it is what makes silently mixing the two target definitions
    impossible downstream.
    """

    KINDS = ("frozen_weight", "realized_account")

    account_key: str
    as_of_session: str
    target_kind: str
    horizon_sessions: int
    daily_volatility_pct: float
    observation_count: int
    weights: Mapping[str, float]
    cash_weight: float
    first_return_session: str
    last_return_session: str
    position_snapshot_hash: str
    price_input_hash: str

    def __post_init__(self) -> None:
        if self.target_kind not in self.KINDS:
            raise PortfolioVolatilityError(
                f"target_kind must be one of {self.KINDS}, got {self.target_kind!r}"
            )
        if not isinstance(self.account_key, str) or not self.account_key.strip():
            raise PortfolioVolatilityError("account_key must be a non-empty string")
        _parse_session(self.as_of_session, "as_of_session")
        first_return = _parse_session(self.first_return_session, "first_return_session")
        last_return = _parse_session(self.last_return_session, "last_return_session")
        if first_return > last_return:
            raise PortfolioVolatilityError(
                "first_return_session must not be after last_return_session"
            )
        if (
            isinstance(self.horizon_sessions, bool)
            or not isinstance(self.horizon_sessions, int)
            or self.horizon_sessions < 2
        ):
            raise PortfolioVolatilityError(
                "horizon_sessions must be an integer >= 2 to compute a volatility"
            )
        if (
            not isinstance(self.daily_volatility_pct, (int, float))
            or isinstance(self.daily_volatility_pct, bool)
            or not math.isfinite(float(self.daily_volatility_pct))
            or self.daily_volatility_pct < 0
        ):
            raise PortfolioVolatilityError(
                "daily_volatility_pct must be a non-negative finite number"
            )
        if (
            isinstance(self.observation_count, bool)
            or not isinstance(self.observation_count, int)
            or self.observation_count < 2
        ):
            raise PortfolioVolatilityError(
                "observation_count must be an integer >= 2 to support a volatility"
            )
        for name in ("position_snapshot_hash", "price_input_hash"):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise PortfolioVolatilityError(f"{name} must be a lowercase SHA-256 hash")
        if not isinstance(self.weights, Mapping):
            raise PortfolioVolatilityError("weights must be a mapping")
        if (
            isinstance(self.cash_weight, bool)
            or not isinstance(self.cash_weight, (int, float))
            or not math.isfinite(float(self.cash_weight))
            or self.cash_weight < 0
        ):
            raise PortfolioVolatilityError("cash_weight must be a non-negative finite number")
        if self.target_kind == "frozen_weight":
            if not self.weights:
                raise PortfolioVolatilityError("a frozen_weight target requires held security weights")
            total_weight = float(self.cash_weight)
            for ticker, weight in self.weights.items():
                if not isinstance(ticker, str) or ticker != ticker.upper() or not ticker.strip():
                    raise PortfolioVolatilityError("weight tickers must be canonical uppercase strings")
                if (
                    isinstance(weight, bool)
                    or not isinstance(weight, (int, float))
                    or not math.isfinite(float(weight))
                    or weight == 0
                ):
                    raise PortfolioVolatilityError(
                        "frozen_weight targets require finite, non-zero security weights"
                    )
                total_weight += float(weight)
            if not math.isclose(total_weight, 1.0, abs_tol=1e-12):
                raise PortfolioVolatilityError(
                    "security weights plus cash_weight must sum to one"
                )
        elif self.weights or self.cash_weight != 0:
            raise PortfolioVolatilityError(
                "a realized_account target cannot carry frozen security or cash weights"
            )

    @property
    def annualized_volatility_pct(self) -> float:
        """Display-only. The field name states `annualized` explicitly so it
        can never be compared against a daily-percent target by accident
        (plan 9.3)."""
        return float(self.daily_volatility_pct * math.sqrt(TRADING_SESSIONS_PER_YEAR))

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_key": self.account_key,
            "as_of_session": self.as_of_session,
            "target_kind": self.target_kind,
            "horizon_sessions": self.horizon_sessions,
            "daily_volatility_pct": self.daily_volatility_pct,
            "annualized_volatility_pct": round(self.annualized_volatility_pct, 6),
            "observation_count": self.observation_count,
            "weights": dict(self.weights),
            "cash_weight": self.cash_weight,
            "first_return_session": self.first_return_session,
            "last_return_session": self.last_return_session,
            "position_snapshot_hash": self.position_snapshot_hash,
            "price_input_hash": self.price_input_hash,
        }


def compute_frozen_weights(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    cash: Any,
    allow_short: bool = False,
) -> tuple[dict[str, float], float, str]:
    """Portfolio weights from EXACT stored market values (plan 9.2).

    Returns (security_weights, cash_weight, snapshot_hash).

    Cash is retained as a zero-volatility exposure rather than renormalized
    away. That distinction is the whole point: a book that is 50% cash has
    roughly half the volatility of the same securities held at full weight,
    and renormalizing would report the fully-invested number for a portfolio
    that was not fully invested -- overstating realized risk by ~2x exactly
    when the owner was being cautious.

    Arithmetic runs through Decimal (assistant/money.py's convention) because
    weights are ratios of stored money text; float round-tripping would make
    the weights fail to sum to one at the last digit and quietly bias every
    downstream variance.
    """
    if not snapshots:
        raise PortfolioVolatilityError("at least one position snapshot is required")

    cash_amount = to_decimal(cash, name="cash")
    if cash_amount < 0:
        raise PortfolioVolatilityError(
            "negative cash (margin) is outside this mandate; refusing to build a target"
        )

    market_values: dict[str, Decimal] = {}
    for index, snapshot in enumerate(snapshots):
        for field in ("ticker", "market_value"):
            if field not in snapshot:
                raise PortfolioVolatilityError(
                    f"position snapshot {index} is missing {field!r}"
                )
        ticker = snapshot["ticker"]
        if not isinstance(ticker, str) or ticker != ticker.upper() or not ticker.strip():
            raise PortfolioVolatilityError(
                f"position snapshot {index} ticker must be canonical uppercase"
            )
        if ticker == CASH_TICKER:
            raise PortfolioVolatilityError(
                f"{CASH_TICKER!r} is reserved for the cash sleeve and cannot be a position"
            )
        if ticker in market_values:
            raise PortfolioVolatilityError(f"duplicate position snapshot for {ticker}")
        value = to_decimal(snapshot["market_value"], name=f"{ticker}.market_value")
        if value < 0 and not allow_short:
            raise PortfolioVolatilityError(
                f"{ticker} has a negative market value; shorts are outside the current "
                "mandate. Pass allow_short=True only once the mandate supports them."
            )
        market_values[ticker] = value

    total = sum(market_values.values(), Decimal(0)) + cash_amount
    if total <= 0:
        raise PortfolioVolatilityError(
            "total portfolio value must be positive to define weights"
        )
    zero_weight_tickers = sorted(ticker for ticker, value in market_values.items() if value == 0)
    if zero_weight_tickers:
        # A zero-valued row is not a held position. Retaining it would require
        # price coverage for a security that cannot affect the target, masking
        # stale position data as a genuine holding.
        raise PortfolioVolatilityError(
            "zero-weight positions cannot define a portfolio-volatility target: "
            f"{zero_weight_tickers}"
        )

    weights = {
        ticker: float(value / total) for ticker, value in sorted(market_values.items())
    }
    cash_weight = float(cash_amount / total)
    snapshot_hash = hash_payload(
        {
            "cash": str(cash_amount),
            "positions": {t: str(v) for t, v in sorted(market_values.items())},
        }
    )
    return weights, cash_weight, snapshot_hash


def build_frozen_weight_targets(
    account_key: str,
    *,
    as_of_session: str,
    captured_at: str,
    forecast_cutoff: str,
    snapshots: Sequence[Mapping[str, Any]],
    cash: Any,
    close_by_ticker: Mapping[str, pd.Series],
    horizon_sessions: int = 20,
    allow_short: bool = False,
) -> PortfolioVolatilityTarget:
    """Realized forward volatility of the book held at `as_of_session`.

    Refuses rather than approximates. Plan 9.2 lists each refusal, and each
    exists because the silent alternative corrupts the target:

      * a snapshot captured AFTER the forecast cutoff would encode holdings
        the forecaster could not have known -- straightforward look-ahead;
      * a held security missing future returns cannot simply be dropped,
        because dropping it silently re-weights every remaining position and
        reports the volatility of a book that was never held.
    """
    _parse_session(as_of_session, "as_of_session")
    captured = _parse_instant(captured_at, "captured_at")
    cutoff = _parse_instant(forecast_cutoff, "forecast_cutoff")
    if captured > cutoff:
        raise PortfolioVolatilityError(
            f"position snapshot captured at {captured_at} is after the forecast "
            f"cutoff {forecast_cutoff}; a forecaster cannot know holdings recorded "
            "after its own decision point"
        )
    if isinstance(horizon_sessions, bool) or not isinstance(horizon_sessions, int) or horizon_sessions < 2:
        raise PortfolioVolatilityError("horizon_sessions must be an integer >= 2")

    weights, cash_weight, snapshot_hash = compute_frozen_weights(
        snapshots, cash=cash, allow_short=allow_short
    )

    missing = sorted(set(weights) - set(close_by_ticker))
    if missing:
        raise PortfolioVolatilityError(
            f"held securities have no price history: {missing}. Refusing rather than "
            "dropping them, which would silently re-weight the remaining positions."
        )

    # Explicit session alignment (plan 9.2). Build one frame so every
    # security contributes a return for exactly the same sessions.
    frame = pd.DataFrame(
        {
            ticker: pd.to_numeric(close_by_ticker[ticker], errors="coerce").where(
                lambda s: s > 0
            )
            for ticker in weights
        }
    ).sort_index()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise PortfolioVolatilityError("price series must be indexed by trading session")
    if frame.index.has_duplicates:
        raise PortfolioVolatilityError("price series contain duplicate sessions")

    as_of_timestamp = pd.Timestamp(as_of_session)
    future = frame[frame.index > as_of_timestamp]
    # horizon_sessions RETURNS require horizon_sessions+1 closes, the first of
    # which is the as-of close itself.
    base = frame[frame.index <= as_of_timestamp]
    if base.empty:
        raise PortfolioVolatilityError(
            f"no price history at or before {as_of_session}"
        )
    window = pd.concat([base.iloc[[-1]], future.iloc[:horizon_sessions]])
    if len(window) < horizon_sessions + 1:
        raise PortfolioVolatilityError(
            f"only {len(window) - 1} forward sessions available after {as_of_session}; "
            f"{horizon_sessions} required. Refusing rather than computing a shorter "
            "window under the declared horizon's name."
        )
    if window.isna().to_numpy().any():
        raise PortfolioVolatilityError(
            "a held security has missing or non-positive prices inside the forecast "
            "window; refusing rather than dropping it"
        )

    returns = window.pct_change(fill_method=None).dropna(how="any")
    if len(returns) < 2:
        raise PortfolioVolatilityError("at least 2 forward returns are required")

    weight_vector = np.array([weights[t] for t in returns.columns], dtype=float)
    # Cash contributes zero return, and is already reflected because the
    # weights sum to (1 - cash_weight) rather than 1.
    portfolio_returns = returns.to_numpy(dtype=float) @ weight_vector
    daily_volatility_pct = float(np.std(portfolio_returns, ddof=1) * 100)
    if not math.isfinite(daily_volatility_pct):
        raise PortfolioVolatilityError("portfolio volatility is not finite")

    price_input_hash = hash_payload(
        {
            "sessions": [str(ts.date()) for ts in window.index],
            "closes": {
                ticker: [float(v) for v in window[ticker].to_numpy()]
                for ticker in window.columns
            },
        }
    )
    return PortfolioVolatilityTarget(
        account_key=account_key,
        as_of_session=as_of_session,
        target_kind="frozen_weight",
        horizon_sessions=horizon_sessions,
        daily_volatility_pct=round(daily_volatility_pct, 6),
        observation_count=int(len(portfolio_returns)),
        weights=weights,
        cash_weight=cash_weight,
        first_return_session=str(returns.index[0].date()),
        last_return_session=str(returns.index[-1].date()),
        position_snapshot_hash=snapshot_hash,
        price_input_hash=price_input_hash,
    )


def build_realized_account_targets(
    account_key: str,
    *,
    as_of_session: str,
    equity_by_session: Mapping[str, Any],
    net_external_flow_by_session: Mapping[str, Any],
    horizon_sessions: int = 20,
) -> PortfolioVolatilityTarget:
    """Realized forward volatility of flow-adjusted ACCOUNT equity.

    A deposit is not a gain. Without subtracting external flows, a $10,000
    contribution into a $100,000 account reads as a +10% "return" and would
    dominate the realized volatility estimate for that window -- so this
    refuses outright when any session in the window lacks a flow record,
    rather than assuming zero flow.

    Deliberately a SEPARATE function from the frozen-weight builder with a
    distinct `target_kind`: plan 9.2 says never silently substitute one for
    the other.
    """
    _parse_session(as_of_session, "as_of_session")
    if isinstance(horizon_sessions, bool) or not isinstance(horizon_sessions, int) or horizon_sessions < 2:
        raise PortfolioVolatilityError("horizon_sessions must be an integer >= 2")

    sessions = sorted(equity_by_session)
    for session in sessions:
        _parse_session(session, "equity session")
    forward = [s for s in sessions if s > as_of_session]
    if as_of_session not in equity_by_session:
        raise PortfolioVolatilityError(
            f"no account equity recorded for {as_of_session}"
        )
    if len(forward) < horizon_sessions:
        raise PortfolioVolatilityError(
            f"only {len(forward)} forward equity observations after {as_of_session}; "
            f"{horizon_sessions} required. Report unavailable rather than "
            "backfilling guessed holdings (plan 9.7)."
        )
    window_sessions = [as_of_session] + forward[:horizon_sessions]

    missing_flows = [s for s in window_sessions[1:] if s not in net_external_flow_by_session]
    if missing_flows:
        raise PortfolioVolatilityError(
            f"net external flow is unrecorded for {missing_flows}; a deposit or "
            "withdrawal would otherwise be counted as investment return"
        )

    equities = [to_decimal(equity_by_session[s], name=f"equity[{s}]") for s in window_sessions]
    if any(value <= 0 for value in equities):
        raise PortfolioVolatilityError("account equity must be positive in every session")

    returns: list[float] = []
    for index in range(1, len(window_sessions)):
        session = window_sessions[index]
        flow = to_decimal(
            net_external_flow_by_session[session], name=f"flow[{session}]"
        )
        previous = equities[index - 1]
        # Subtract the external flow from the ending equity so only market
        # movement remains.
        adjusted = equities[index] - flow
        returns.append(float(adjusted / previous) - 1.0)

    daily_volatility_pct = float(np.std(np.asarray(returns, dtype=float), ddof=1) * 100)
    if not math.isfinite(daily_volatility_pct):
        raise PortfolioVolatilityError("account volatility is not finite")

    return PortfolioVolatilityTarget(
        account_key=account_key,
        as_of_session=as_of_session,
        target_kind="realized_account",
        horizon_sessions=horizon_sessions,
        daily_volatility_pct=round(daily_volatility_pct, 6),
        observation_count=len(returns),
        weights={},
        cash_weight=0.0,
        first_return_session=window_sessions[1],
        last_return_session=window_sessions[-1],
        position_snapshot_hash=hash_payload({"kind": "realized_account"}),
        price_input_hash=hash_payload(
            {
                "sessions": window_sessions,
                "equity": [str(v) for v in equities],
                "flows": [
                    str(to_decimal(net_external_flow_by_session[s]))
                    for s in window_sessions[1:]
                ],
            }
        ),
    )
