"""ML-LR-4 sections 10.1/10.4: earnings event identity, pre-event features,
and the typed gap forecast.

The controlling rule is that an EVENT, not a row, is the unit of evidence.
Repeated feature rows, repeated documents, and repeated tickers do not
create independent observations (plan 10.2), so `EventIdentity` exists to
make double-counting structurally impossible rather than merely discouraged:
two records describing the same announcement collapse to one identity even
when their timestamps are written in different timezones.

The second rule is that a pre-event feature row may contain only what was
knowable BEFORE the announcement cutoff. Post-release price, transcript
text, revised consensus, and later filings are named prohibitions in plan
10.1 and are rejected by name here -- not left to reviewer vigilance. Each
is a plausible-looking feature that would leak the answer:

  * post-release price IS the gap, restated;
  * a transcript is published after the release it describes;
  * revised consensus is the estimate as it exists TODAY, not as it stood
    before the print; and
  * a later filing restates the quarter the event reported.

Timing that is naive, unknown, or intraday produces an UNAVAILABLE event
(plan 10.1: "Do not guess"). ml/earnings_gap.py already refuses to map an
intraday release to a gap window; this module refuses to build a feature row
for one, so the two layers agree.
"""
from __future__ import annotations

import dataclasses
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ml.earnings_gap import (
    EarningsGapError,
    GapObservation,
    classify_release_timing,
    map_gap_window,
)
from ml.hashing import hash_payload

# Plan 10.1's explicit prohibitions. Matched on normalized feature NAMES so a
# camelCase or hyphenated spelling cannot slip past.
_PROHIBITED_FEATURE_TOKENS = frozenset(
    {
        "post", "postrelease", "after", "afterrelease", "transcript", "call",
        "revised", "revision", "restated", "consensus_now", "later", "future",
        "actual", "reported", "outcome", "gap",
    }
)
_ALLOWED_DESPITE_TOKEN = frozenset(
    {
        # Historical gaps are legitimate pre-event features -- they describe
        # PRIOR events, not this one. The name must say so explicitly.
        "prior_absolute_gap_mean_pct",
        "prior_signed_gap_mean_pct",
        "prior_absolute_gap_median_pct",
        "sessions_since_prior_event",
    }
)

UNKNOWN_TIMING = "unknown"


class EarningsFeatureError(ValueError):
    """Event data cannot support a trustworthy pre-event feature row."""


def _normalize_feature_name(name: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name).strip())
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def assert_pre_event_feature_names(names: Sequence[str]) -> None:
    """Reject feature names that describe post-release information.

    A name-based check is a coarse instrument and is not a substitute for
    the availability lineage in ml/availability.py. It exists because the
    specific leaks plan 10.1 names are all things a well-meaning person adds
    because they are genuinely predictive -- which is exactly the problem.
    """
    offenders: list[str] = []
    for name in names:
        normalized = _normalize_feature_name(name)
        if normalized in _ALLOWED_DESPITE_TOKEN:
            continue
        tokens = set(normalized.split("_"))
        if tokens & _PROHIBITED_FEATURE_TOKENS:
            offenders.append(name)
    if offenders:
        raise EarningsFeatureError(
            f"pre-event features must not describe post-release information: "
            f"{sorted(offenders)}. Post-release price restates the gap, a "
            "transcript postdates its release, and revised consensus is today's "
            "estimate rather than the one that stood before the print."
        )


@dataclasses.dataclass(frozen=True)
class EventIdentity:
    """Stable identity for one earnings announcement (plan 10.1).

    Built from ticker, the CANONICAL announcement instant (normalized to
    UTC), source, and the source's own event ID. Normalizing to UTC before
    hashing is what makes timezone-equivalent duplicates collapse: the same
    announcement filed as `2026-07-31T20:30:00+00:00` and
    `2026-07-31T16:30:00-04:00` is one event, and counting it twice would
    inflate the sample the whole experiment's power rests on.
    """

    ticker: str
    announced_at_utc: str
    source_id: str
    source_event_id: str

    def __post_init__(self) -> None:
        for name in ("ticker", "source_id", "source_event_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise EarningsFeatureError(f"{name} must be a non-empty string")
        if self.ticker != self.ticker.upper():
            raise EarningsFeatureError("ticker must be canonical uppercase")
        parsed = datetime.fromisoformat(self.announced_at_utc)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise EarningsFeatureError("announced_at_utc must be timezone-aware")
        if parsed.utcoffset().total_seconds() != 0:
            raise EarningsFeatureError(
                "announced_at_utc must already be normalized to UTC; use "
                "EventIdentity.build() rather than constructing directly"
            )

    @classmethod
    def build(
        cls, *, ticker: str, announced_at: Any, source_id: str, source_event_id: str
    ) -> "EventIdentity":
        """Normalize any timezone-aware instant to UTC, then identify."""
        timestamp = pd.to_datetime(announced_at, errors="coerce")
        if pd.isna(timestamp):
            raise EarningsFeatureError("announced_at is not a parseable timestamp")
        if timestamp.tzinfo is None:
            # Plan 10.1: naive timing produces an unavailable event. Guessing a
            # timezone would silently decide whether a release was before or
            # after the close, which determines the entire gap window.
            raise EarningsFeatureError(
                "announced_at is timezone-naive; a naive instant cannot be "
                "classified as before-open or after-close without guessing"
            )
        return cls(
            ticker=ticker,
            announced_at_utc=timestamp.tz_convert("UTC").isoformat(),
            source_id=source_id,
            source_event_id=source_event_id,
        )

    @property
    def event_id(self) -> str:
        return hash_payload(
            {
                "ticker": self.ticker,
                "announced_at_utc": self.announced_at_utc,
                "source_id": self.source_id,
                "source_event_id": self.source_event_id,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "ticker": self.ticker,
            "announced_at_utc": self.announced_at_utc,
            "source_id": self.source_id,
            "source_event_id": self.source_event_id,
        }


def deduplicate_events(identities: Sequence[EventIdentity]) -> tuple[EventIdentity, ...]:
    """Collapse timezone-equivalent duplicates (plan 10.1).

    Order-preserving on first appearance so the result is deterministic.
    """
    seen: dict[str, EventIdentity] = {}
    for identity in identities:
        seen.setdefault(identity.event_id, identity)
    return tuple(seen.values())


@dataclasses.dataclass(frozen=True)
class EventFeatureRow:
    """One pre-event feature row, bound to its event identity."""

    identity: EventIdentity
    release_timing: str
    as_of_session: str
    cutoff_at: str
    features: Mapping[str, float]
    available: bool
    refusal_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.available and self.refusal_reasons:
            raise EarningsFeatureError(
                "an available feature row cannot carry refusal reasons"
            )
        if not self.available and not self.refusal_reasons:
            raise EarningsFeatureError(
                "an unavailable feature row must carry at least one reason"
            )
        if self.available:
            if not self.features:
                raise EarningsFeatureError("an available feature row requires features")
            assert_pre_event_feature_names(list(self.features))
            for name, value in self.features.items():
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise EarningsFeatureError(
                        f"feature {name!r} must be a finite number"
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity.to_dict(),
            "release_timing": self.release_timing,
            "as_of_session": self.as_of_session,
            "cutoff_at": self.cutoff_at,
            "features": dict(self.features),
            "available": self.available,
            "refusal_reasons": list(self.refusal_reasons),
        }


def _unavailable_row(
    identity: EventIdentity, timing: str, reasons: Sequence[str]
) -> EventFeatureRow:
    return EventFeatureRow(
        identity=identity,
        release_timing=timing,
        as_of_session="",
        cutoff_at="",
        features={},
        available=False,
        refusal_reasons=tuple(reasons),
    )


def build_pre_event_features(
    identity: EventIdentity,
    *,
    price: pd.DataFrame,
    prior_gaps: Sequence[GapObservation] = (),
    benchmark_close: pd.Series | None = None,
    minimum_prior_sessions: int = 20,
) -> EventFeatureRow:
    """One feature row computed strictly from data available before the cutoff.

    The cutoff is the announcement instant itself. Every window below ends at
    the last session that CLOSED before it, so a same-day after-close release
    cannot see its own session's close if that close postdates the cutoff.
    """
    announced = datetime.fromisoformat(identity.announced_at_utc)
    timing = classify_release_timing(pd.Timestamp(announced))
    if timing == "intraday":
        return _unavailable_row(
            identity, timing,
            ["intraday release has no isolatable open/close gap (plan 10.1)"],
        )

    sessions = pd.DatetimeIndex(price.index).normalize()
    window = map_gap_window(pd.Timestamp(announced), session_index=sessions)
    if not window.available:
        return _unavailable_row(identity, timing, [window.reason or "unmappable event"])

    # The last session whose close is genuinely prior to the event. For an
    # after-close release that is the release day itself; for a before-open
    # release it is the previous session.
    cutoff_session = pd.Timestamp(window.from_session)
    history = price.loc[price.index.normalize() <= cutoff_session]
    if len(history) < minimum_prior_sessions + 1:
        return _unavailable_row(
            identity, timing,
            [f"only {len(history)} prior sessions; {minimum_prior_sessions + 1} required"],
        )

    close = pd.to_numeric(history["close"], errors="coerce").where(lambda s: s > 0)
    returns = close.pct_change(fill_method=None).dropna()
    if len(returns) < minimum_prior_sessions:
        return _unavailable_row(
            identity, timing, ["insufficient finite prior returns"]
        )

    recent = returns.tail(minimum_prior_sessions)
    downside = recent.clip(upper=0.0)
    features: dict[str, float] = {
        "pre_event_volatility_pct": float(recent.std(ddof=1) * 100),
        "pre_event_downside_volatility_pct": float(
            np.sqrt(float((downside**2).mean())) * 100
        ),
        "pre_event_return_20d_pct": float(
            (close.iloc[-1] / close.iloc[-min(len(close), 21)] - 1.0) * 100
        ),
    }

    volume = pd.to_numeric(history.get("volume"), errors="coerce")
    if volume is not None and volume.notna().any():
        recent_volume = volume.tail(minimum_prior_sessions)
        average = float(recent_volume.mean())
        if math.isfinite(average) and average > 0:
            features["pre_event_dollar_volume"] = float(
                (close.tail(minimum_prior_sessions) * recent_volume).mean()
            )
            features["pre_event_volume_ratio"] = float(
                recent_volume.iloc[-1] / average
            )

    if benchmark_close is not None:
        aligned = pd.to_numeric(benchmark_close, errors="coerce").reindex(close.index)
        aligned = aligned.where(lambda s: s > 0).dropna()
        if len(aligned) >= 21:
            own = float(close.iloc[-1] / close.iloc[-min(len(close), 21)] - 1.0) * 100
            bench = float(aligned.iloc[-1] / aligned.iloc[-min(len(aligned), 21)] - 1.0) * 100
            features["pre_event_residual_momentum_pct"] = own - bench

    # Prior gaps describe EARLIER events, which is why they survive the
    # prohibited-name check via the explicit allowlist. Only gaps whose own
    # announcement precedes this cutoff may contribute.
    usable_prior = [
        observation
        for observation in prior_gaps
        if pd.Timestamp(observation.to_session) <= cutoff_session
    ]
    if usable_prior:
        magnitudes = [abs(o.gap_pct) for o in usable_prior]
        features["prior_absolute_gap_mean_pct"] = float(np.mean(magnitudes))
        features["prior_absolute_gap_median_pct"] = float(np.median(magnitudes))
        features["prior_signed_gap_mean_pct"] = float(
            np.mean([o.gap_pct for o in usable_prior])
        )
        last_prior = max(usable_prior, key=lambda o: o.to_session)
        prior_sessions = sessions[
            (sessions > pd.Timestamp(last_prior.to_session))
            & (sessions <= cutoff_session)
        ]
        features["sessions_since_prior_event"] = float(len(prior_sessions))

    return EventFeatureRow(
        identity=identity,
        release_timing=timing,
        as_of_session=str(cutoff_session.date()),
        cutoff_at=identity.announced_at_utc,
        features=features,
        available=True,
    )


def event_frame(rows: Sequence[EventFeatureRow]) -> pd.DataFrame:
    """Available rows as a frame keyed by event, for grouped evaluation.

    `as_of_session` doubles as the grouping key so ml/splits.py's
    date-grouped purging works unchanged: two companies reporting on the same
    session share market conditions and are not independent draws.
    """
    usable = [row for row in rows if row.available]
    if not usable:
        return pd.DataFrame(
            columns=["event_id", "ticker", "as_of_session", "release_timing"]
        )
    records = []
    for row in usable:
        record = {
            "event_id": row.identity.event_id,
            "ticker": row.identity.ticker,
            "as_of_session": row.as_of_session,
            "release_timing": row.release_timing,
            "announced_at_utc": row.identity.announced_at_utc,
        }
        record.update(row.features)
        records.append(record)
    frame = pd.DataFrame(records)
    if frame["event_id"].duplicated().any():
        raise EarningsFeatureError(
            "duplicate event_id in the feature frame; repeated rows would be "
            "counted as independent evidence"
        )
    return frame.sort_values(["as_of_session", "ticker"]).reset_index(drop=True)


def summarize_event_support(
    rows: Sequence[EventFeatureRow],
) -> dict[str, Any]:
    """Distinct events, tickers, and refusal reasons (plan 10.3).

    Counts DISTINCT EVENTS, never rows. Plan 10.3 is explicit that the
    software minimum is a fit-refusal threshold rather than a promotion
    threshold, so this reports the counts and takes no view on sufficiency.
    """
    available = [row for row in rows if row.available]
    refused = [row for row in rows if not row.available]
    reason_counts: dict[str, int] = {}
    for row in refused:
        for reason in row.refusal_reasons:
            key = str(reason).split(";")[0].split(":")[0].strip()
            reason_counts[key] = reason_counts.get(key, 0) + 1
    timing_counts: dict[str, int] = {}
    for row in available:
        timing_counts[row.release_timing] = timing_counts.get(row.release_timing, 0) + 1
    return {
        "distinct_events": len({row.identity.event_id for row in available}),
        "distinct_tickers": len({row.identity.ticker for row in available}),
        "distinct_sessions": len({row.as_of_session for row in available}),
        "refused_event_count": len(refused),
        "refusal_reason_counts": dict(sorted(reason_counts.items())),
        "release_timing_counts": dict(sorted(timing_counts.items())),
        "note": (
            "Counts are DISTINCT EVENTS, not rows. The fit-refusal minimum in "
            "ml/earnings_gap.py is not a promotion threshold; a confirmation "
            "spec must justify its own sample requirement (plan 10.3)."
        ),
    }


@dataclasses.dataclass(frozen=True)
class EarningsGapForecast:
    """Plan 10.4's typed output. Carries no trade field of any kind."""

    event_id: str
    ticker: str
    announced_at_utc: str
    release_timing: str
    as_of_session: str
    target_available_at: str
    absolute_gap_interval_pct: tuple[float, float] | None
    probability_above_absolute_threshold: float | None
    probability_below_downside_threshold: float | None
    absolute_threshold_pct: float
    downside_threshold_pct: float
    baseline_median_absolute_gap_pct: float | None
    calibration_status: str
    event_support: Mapping[str, Any]
    model_key: str
    artifact_hash: str
    feature_snapshot_hash: str
    evidence_status: str
    available: bool
    refusal_reasons: tuple[str, ...] = ()

    WHAT_THIS_DOES_NOT_MEAN = (
        "This estimates how far a stock may move on its earnings release. It "
        "does not predict direction, does not say whether the company will "
        "beat expectations, and is not a recommendation to buy or sell. It "
        "never overrides the deterministic earnings blackout and never delays "
        "a risk-reducing sale."
    )

    def __post_init__(self) -> None:
        if self.available and self.refusal_reasons:
            raise EarningsFeatureError(
                "an available forecast cannot carry refusal reasons"
            )
        if not self.available and not self.refusal_reasons:
            raise EarningsFeatureError(
                "an unavailable forecast must carry at least one refusal reason"
            )
        for name in (
            "probability_above_absolute_threshold",
            "probability_below_downside_threshold",
        ):
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise EarningsFeatureError(f"{name} must be within [0, 1]")
        if self.available and self.absolute_gap_interval_pct is not None:
            low, high = self.absolute_gap_interval_pct
            if not (math.isfinite(low) and math.isfinite(high)) or high < low:
                raise EarningsFeatureError("absolute_gap_interval_pct is not ordered")
            if low < 0:
                raise EarningsFeatureError(
                    "an ABSOLUTE gap interval cannot extend below zero"
                )

    @property
    def production_authoritative(self) -> bool:
        return False

    @property
    def probability_label(self) -> str:
        return (
            "calibrated_probability"
            if self.calibration_status == "calibrated"
            else "experimental_probability"
        )

    def to_dict(self) -> dict[str, Any]:
        label = self.probability_label
        return {
            "event_id": self.event_id,
            "ticker": self.ticker,
            "announced_at_utc": self.announced_at_utc,
            "release_timing": self.release_timing,
            "as_of_session": self.as_of_session,
            "target_available_at": self.target_available_at,
            "absolute_gap_interval_pct": (
                list(self.absolute_gap_interval_pct)
                if self.absolute_gap_interval_pct is not None
                else None
            ),
            f"{label}_above_absolute_threshold": (
                self.probability_above_absolute_threshold
            ),
            f"{label}_below_downside_threshold": (
                self.probability_below_downside_threshold
            ),
            "absolute_threshold_pct": self.absolute_threshold_pct,
            "downside_threshold_pct": self.downside_threshold_pct,
            "baseline_median_absolute_gap_pct": self.baseline_median_absolute_gap_pct,
            "calibration_status": self.calibration_status,
            "event_support": dict(self.event_support),
            "model_key": self.model_key,
            "artifact_hash": self.artifact_hash,
            "feature_snapshot_hash": self.feature_snapshot_hash,
            "evidence_status": self.evidence_status,
            "available": self.available,
            "refusal_reasons": list(self.refusal_reasons),
            "production_authoritative": self.production_authoritative,
            "what_this_does_not_mean": self.WHAT_THIS_DOES_NOT_MEAN,
        }
