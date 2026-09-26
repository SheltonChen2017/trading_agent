"""SI-2B offline candidate-window investability evidence, not seeds or outcomes.

Only synthetic history is accepted. Each authenticated snapshot receives all
four window dispositions, including upstream readiness refusals. Parser-level
refusals remain bound in the vintage identity, not invented snapshot rows.
The cutoff is the authenticated SI-2A execution open: only completed XNYS
bars published strictly before it can enter
the trailing window. No row is borrowed from another identity or a future
revision. This does not claim a release-time or licensed investable universe.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from fractions import Fraction
from typing import Any

from data.exchange_calendar import (
    ExchangeCalendarError,
    SUPPORTED_SESSION_START,
    session_close_instant,
    trading_sessions,
)
from data.financial_primitives import decimal_text
from data.hashing import hash_payload
from research.short_interest_etf.contracts import (
    CollectionManifest,
    DenominatorKind,
    DenominatorObservation,
    ReleaseCalendarEntry,
    ReleasePrecision,
    SecurityIdentity,
    ShortInterestContractError,
    ShortInterestSnapshot,
    SourceEntitlement,
    SourceSemantic,
    VolumeBasis,
    _canonical_date,
    _required_text,
    _sha256,
    parse_utc_timestamp,
)
from research.short_interest_etf.dataset import (
    ShortInterestDatasetError,
    ShortInterestVintage,
    build_identity,
)
from research.short_interest_etf.pit_eligibility import (
    CorporateActionIssue,
    ListingStatus,
    PitReferenceBundle,
    PitReferenceError,
    PitReferenceManifest,
    SectorClassificationObservation,
    SecurityLifecycleObservation,
    build_stock_data_readiness,
)
from research.short_interest_etf.normalize import SnapshotRefusal
from research.short_interest_etf.stock_percentile import (
    STOCK_PERCENTILE_POLICY,
    StockPercentilePolicy,
    require_stock_percentile_policy,
)


class StockInvestabilityError(ValueError):
    """An offline evidence boundary failed closed."""


# Only immutable exchange-calendar facts, never history values or decisions.
# Bounding the cache avoids repeated schedule construction on each public
# reauthentication while retaining a fixed memory ceiling for offline audits.
_SESSION_CLOSE_CACHE: dict[str, datetime] = {}


def _session_close(session: str) -> datetime:
    if session not in _SESSION_CLOSE_CACHE:
        close = session_close_instant(session)
        if len(_SESSION_CLOSE_CACHE) >= 512:
            _SESSION_CLOSE_CACHE.clear()
        _SESSION_CLOSE_CACHE[session] = close
    return _SESSION_CLOSE_CACHE[session]


def _refuse(detail: str) -> StockInvestabilityError:
    return StockInvestabilityError(f"REFUSED: {detail}")


def _positive_decimal(value: Any, name: str) -> Fraction:
    if type(value) is not str or len(value) > 128:
        raise _refuse(f"{name} must be canonical positive decimal text")
    # Bound the spelling before projection; exponent notation is not canonical
    # and could allocate enormous strings in a generic decimal formatter.
    if not value or any(c not in "0123456789." for c in value):
        raise _refuse(f"{name} must be canonical positive decimal text")
    try:
        if decimal_text(value) != value or Fraction(value) <= 0:
            raise ValueError("noncanonical or nonpositive")
        return Fraction(value)
    except ValueError as exc:
        raise _refuse(f"{name} must be canonical positive decimal text") from exc


def _validate_observation(row: Any) -> None:
    try:
        _validate_observation_fields(row)
    except (ShortInterestContractError, ExchangeCalendarError) as exc:
        raise _refuse(str(exc)) from exc


def _validate_observation_fields(row: Any) -> None:
    _required_text(row.security_id, "security_id")
    _sha256(row.security_identity_sha256, "security_identity_sha256")
    _sha256(row.raw_record_sha256, "raw_record_sha256")
    _canonical_date(row.session, "session")
    close = _session_close(row.session)
    available = parse_utc_timestamp(row.available_at, "available_at")
    observed = parse_utc_timestamp(row.observed_at, "observed_at")
    if available < close:
        raise _refuse("daily close evidence cannot be available before session close")
    if observed < available:
        raise _refuse("observed_at must not precede available_at")


@dataclasses.dataclass(frozen=True, slots=True)
class DailyLiquidityObservation:
    security_id: str
    security_identity_sha256: str
    session: str
    close_usd: str
    volume_shares: int
    available_at: str
    observed_at: str
    raw_record_sha256: str

    def __post_init__(self) -> None:
        _validate_observation(self)
        _positive_decimal(self.close_usd, "close_usd")
        if type(self.volume_shares) is not int or self.volume_shares < 0:
            raise _refuse("volume_shares must be a nonnegative exact integer")


@dataclasses.dataclass(frozen=True, slots=True)
class MarketCapObservation:
    security_id: str
    security_identity_sha256: str
    session: str
    market_cap_usd: str
    available_at: str
    observed_at: str
    raw_record_sha256: str

    def __post_init__(self) -> None:
        _validate_observation(self)
        _positive_decimal(self.market_cap_usd, "market_cap_usd")


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticMarketHistory:
    daily: tuple[DailyLiquidityObservation, ...]
    capitalizations: tuple[MarketCapObservation, ...]
    source_id: str = "synthetic-si2b-v1"
    entitlement: SourceEntitlement = SourceEntitlement.SYNTHETIC_FIXTURE_ONLY

    def __post_init__(self) -> None:
        _required_text(self.source_id, "source_id")
        if self.entitlement is not SourceEntitlement.SYNTHETIC_FIXTURE_ONLY:
            raise _refuse("market history accepts synthetic entitlement only")
        for rows, cls in (
            (self.daily, DailyLiquidityObservation),
            (self.capitalizations, MarketCapObservation),
        ):
            if type(rows) is not tuple or any(type(row) is not cls for row in rows):
                raise _refuse("history requires exact tuples of canonical observations")
            for row in rows:
                cls.__post_init__(row)
            identities = [hash_payload(dataclasses.asdict(row)) for row in rows]
            if len(set(identities)) != len(identities):
                raise _refuse("duplicate market observation")

    def to_payload(self) -> dict[str, Any]:
        SyntheticMarketHistory.__post_init__(self)
        return {
            "source_id": self.source_id,
            "entitlement": self.entitlement.value,
            "daily": sorted(
                (dataclasses.asdict(row) for row in self.daily), key=hash_payload
            ),
            "capitalizations": sorted(
                (dataclasses.asdict(row) for row in self.capitalizations),
                key=hash_payload,
            ),
        }

    @property
    def sha256(self) -> str:
        return hash_payload(SyntheticMarketHistory.to_payload(self))


def _policy() -> dict[str, Any]:
    require_stock_percentile_policy(STOCK_PERCENTILE_POLICY)
    authority = StockPercentilePolicy.to_payload(STOCK_PERCENTILE_POLICY)
    return {
        "policy_id": "si2b-offline-candidate-investability-v1",
        "candidate_lookbacks": [20, 60, 120, 252],
        "minimum_market_cap_usd": "300000000",
        "minimum_median_dollar_volume_usd": "10000000",
        "history_semantic": "unadjusted_daily_close_usd_times_volume_shares",
        "median_semantic": "exact_middle_or_mean_of_two_middle_values",
        "evidence_cutoff": "strictly_before_authenticated_execution_open",
        "cap_freshness": "exact_last_completed_session",
        "revision_selection": "latest_available_strictly_before_cutoff_or_ambiguous",
        "history_completeness": "every_trailing_XNYS_session_no_gap_replenishment",
        "owner_directive_path": authority["owner_directive_path"],
        "owner_directive_commit": authority["owner_directive_commit"],
        "owner_directive_sha256": authority["owner_directive_sha256"],
        "selected_lookback": None,
        "production_authoritative": False,
        "seed_authorized": False,
        "outcome_authorized": False,
    }


def _selection(rows: tuple, cutoff, identity: str):
    visible = [
        row for row in rows
        if parse_utc_timestamp(row.available_at, "available_at") < cutoff
    ]
    if not visible:
        return None, "missing"
    latest = max(
        parse_utc_timestamp(row.available_at, "available_at") for row in visible
    )
    winners = [
        row for row in visible
        if parse_utc_timestamp(row.available_at, "available_at") == latest
    ]
    if len(winners) != 1:
        return None, "ambiguous"
    row = winners[0]
    if row.security_identity_sha256 != identity:
        return None, "identity_mismatch"
    return row, None


def _clone_contract(value: Any) -> Any:
    """Reconstruct only known contracts from fields, never instance callbacks.

    Older unslotted source contracts can carry per-instance method shadows.
    Reading their payload methods would trust caller code before validation.
    Constructors here receive only recursively reconstructed schema fields.
    """
    if type(value) is tuple:
        return tuple(_clone_contract(item) for item in value)
    allowed = (
        CollectionManifest, DenominatorObservation, ReleaseCalendarEntry,
        SecurityIdentity, ShortInterestSnapshot, VolumeBasis, SnapshotRefusal,
        ShortInterestVintage, PitReferenceManifest, SecurityLifecycleObservation,
        SectorClassificationObservation, PitReferenceBundle,
        DailyLiquidityObservation, MarketCapObservation, SyntheticMarketHistory,
    )
    if any(type(value) is cls for cls in allowed):
        try:
            return type(value)(**{
                field.name: _clone_contract(getattr(value, field.name))
                for field in dataclasses.fields(value) if field.init
            })
        except (
            ShortInterestContractError, ShortInterestDatasetError,
            PitReferenceError, ExchangeCalendarError, TypeError, AttributeError,
        ) as exc:
            raise _refuse(f"invalid source contract: {exc}") from exc
    scalar_types = (
        str, int, bool, type(None), SourceEntitlement, SourceSemantic,
        DenominatorKind, ReleasePrecision, ListingStatus, CorporateActionIssue,
    )
    if any(type(value) is cls for cls in scalar_types):
        return value
    raise _refuse("source contains a noncanonical contract or scalar type")


@dataclasses.dataclass(frozen=True, slots=True)
class StockInvestabilityEvidence:
    vintage: ShortInterestVintage
    references: PitReferenceBundle
    history: SyntheticMarketHistory
    _source_vintage_sha256: str = dataclasses.field(init=False, repr=False)
    _reference_bundle_sha256: str = dataclasses.field(init=False, repr=False)
    _market_history_sha256: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        for name, cls in (
            ("vintage", ShortInterestVintage),
            ("references", PitReferenceBundle),
            ("history", SyntheticMarketHistory),
        ):
            source = getattr(self, name)
            if type(source) is not cls:
                raise _refuse(f"{name} must be the exact {cls.__name__} type")
            object.__setattr__(self, name, _clone_contract(source))
        object.__setattr__(
            self, "_source_vintage_sha256", build_identity(self.vintage)["content_hash"]
        )
        object.__setattr__(self, "_reference_bundle_sha256", self.references.sha256)
        object.__setattr__(self, "_market_history_sha256", self.history.sha256)

    def to_payload(self) -> dict[str, Any]:
        try:
            return StockInvestabilityEvidence._to_payload(self)
        except StockInvestabilityError:
            raise
        except (ValueError, TypeError, AttributeError) as exc:
            raise _refuse(f"invalid eligibility evidence: {exc}") from exc

    def _to_payload(self) -> dict[str, Any]:
        # Rebuild instead of trusting frozen objects, stored ready booleans, or
        # caller-created result rows. Public serialization is the authority seam.
        if type(self) is not StockInvestabilityEvidence:
            raise _refuse("evidence must be the exact StockInvestabilityEvidence type")
        if type(self.vintage) is not ShortInterestVintage:
            raise _refuse("vintage must be the exact ShortInterestVintage type")
        if type(self.references) is not PitReferenceBundle:
            raise _refuse("references must be the exact PitReferenceBundle type")
        if type(self.history) is not SyntheticMarketHistory:
            raise _refuse("history must be the exact SyntheticMarketHistory type")
        vintage = _clone_contract(self.vintage)
        if vintage.manifest.entitlement is not SourceEntitlement.SYNTHETIC_FIXTURE_ONLY:
            raise _refuse("SI-2B accepts synthetic vintage entitlement only")
        references = _clone_contract(self.references)
        if references.manifest.entitlement is not SourceEntitlement.SYNTHETIC_FIXTURE_ONLY:
            raise _refuse("SI-2B accepts synthetic reference entitlement only")
        history = _clone_contract(self.history)
        history_payload = SyntheticMarketHistory.to_payload(history)
        vintage_hash = build_identity(vintage)["content_hash"]
        reference_hash = references.sha256
        history_hash = hash_payload(history_payload)
        for actual, expected in (
            (vintage_hash, self._source_vintage_sha256),
            (reference_hash, self._reference_bundle_sha256),
            (history_hash, self._market_history_sha256),
        ):
            if type(expected) is not str or actual != expected:
                raise _refuse("evidence source content changed after construction")
        readiness = build_stock_data_readiness(vintage, references)
        snapshots = {row.event_id: row for row in vintage.snapshots}
        daily: dict[tuple[str, str], list] = {}
        caps: dict[tuple[str, str], list] = {}
        for rows, index in (
            (history.daily, daily), (history.capitalizations, caps)
        ):
            for row in rows:
                index.setdefault((row.security_id, row.session), []).append(row)
        policy = _policy()
        window_cache: dict[str, tuple[str, ...]] = {}
        results = []
        for ready in readiness:
            cutoff = parse_utc_timestamp(ready.execution_at, "execution_at")
            if ready.execution_at not in window_cache:
                # An execution open precedes its same-day close. Sessions on
                # strictly earlier dates are complete by this authenticated open.
                end_date = cutoff.date() - timedelta(days=1)
                sessions = (
                    trading_sessions(
                        max(SUPPORTED_SESSION_START, cutoff.date() - timedelta(days=800)),
                        end_date,
                    ) if end_date >= SUPPORTED_SESSION_START else ()
                )
                window_cache[ready.execution_at] = tuple(
                    session.isoformat() for session in sessions[-252:]
                )
            sessions = window_cache[ready.execution_at]
            end = sessions[-1] if sessions else None
            snapshot = snapshots[ready.event_id]
            cap, cap_error = _selection(
                tuple(caps.get((ready.security_id, end), ())),
                cutoff, ready.security_identity_sha256,
            )
            if cap is not None and not snapshot.security.valid_on(cap.session):
                cap, cap_error = None, "identity_not_valid"
            for lookback in policy["candidate_lookbacks"]:
                reasons = list(ready.refusal_reasons)
                window = sessions[-lookback:]
                dollar_volumes: list[Fraction] = []
                if len(window) != lookback:
                    reasons.append("insufficient_calendar_history")
                for session in window:
                    row, error = _selection(
                        tuple(daily.get((ready.security_id, session), ())),
                        cutoff, ready.security_identity_sha256,
                    )
                    if row is not None and not snapshot.security.valid_on(session):
                        row, error = None, "identity_not_valid"
                    if error is not None:
                        reasons.append(f"daily_history_{error}")
                    else:
                        dollar_volumes.append(Fraction(row.close_usd) * row.volume_shares)
                median = None
                if len(dollar_volumes) == lookback:
                    ordered = sorted(dollar_volumes)
                    mid = lookback // 2
                    median = (ordered[mid - 1] + ordered[mid]) / 2
                    if median < Fraction(policy["minimum_median_dollar_volume_usd"]):
                        reasons.append("below_median_dollar_volume_floor")
                if cap_error is not None:
                    reasons.append(f"market_cap_{cap_error}")
                elif Fraction(cap.market_cap_usd) < Fraction(policy["minimum_market_cap_usd"]):
                    reasons.append("below_market_cap_floor")
                results.append({
                    "event_id": ready.event_id,
                    "security_id": ready.security_id,
                    "security_identity_sha256": ready.security_identity_sha256,
                    "lookback_sessions": lookback,
                    "evidence_cutoff_at": ready.execution_at,
                    "window_end_session": end,
                    "window_start_session": window[0] if window else None,
                    "complete_session_count": len(dollar_volumes),
                    "median_dollar_volume": (
                        {"numerator": median.numerator, "denominator": median.denominator}
                        if median is not None else None
                    ),
                    "market_cap_usd": cap.market_cap_usd if cap is not None else None,
                    "eligible": not reasons,
                    "refusal_reasons": sorted(set(reasons)),
                })
        payload = {
            "policy": policy,
            "policy_sha256": hash_payload(policy),
            "source_vintage_sha256": vintage_hash,
            "reference_bundle_sha256": reference_hash,
            "market_history_sha256": history_hash,
            "rows": results,
            "production_authoritative": False,
            "outcome_authorized": False,
            "seed_authorized": False,
            "selected_lookback": None,
        }
        payload["evidence_sha256"] = hash_payload(payload)
        return payload

    @property
    def sha256(self) -> str:
        return StockInvestabilityEvidence.to_payload(self)["evidence_sha256"]


def build_stock_investability(
    vintage: ShortInterestVintage,
    references: PitReferenceBundle,
    history: SyntheticMarketHistory,
) -> StockInvestabilityEvidence:
    evidence = StockInvestabilityEvidence(vintage, references, history)
    StockInvestabilityEvidence.to_payload(evidence)
    return evidence
