"""Owner-approved sleeve allocation profile (REBAL-1 Stage 0).

A profile is the owner's stated intent about portfolio shape: what fraction
of total equity each SLEEVE should hold, and how far it may drift before the
drift is worth naming. It is versioned and fingerprinted so that any change
to it makes previously displayed analysis stale rather than silently
re-interpreted.

Two things this module deliberately does not do.

**It does not derive targets.** The approved mandate defines risk-SHAPE
targets (a volatility band, drawdown limits) and `TradingPolicy` defines
CAPS. A cap is not a target: `max_leveraged_etf_pct` says how much leveraged
exposure is forbidden, not how much is wanted. Neither document contains an
allocation, so deriving one here would be this project inventing an
investment policy it has no evidence for. The numbers below were chosen by
the owner on 2026-08-15 and are recorded as preference, not as a finding.

**It does not claim the band is optimal.** This project's one `confirmed`
research entry -- ~89% less tax and turnover from a wide band -- was measured
on the SOXX/SOXL vol-targeting pair (`relevant_tickers: ["SOXX", "SOXL"]`),
not on a general multi-sleeve portfolio. It is a reason to prefer a wide
band over a tight one as a MECHANISM, and it is not evidence about this
book. Any surface built on this profile must say so.

Sleeve membership comes from `config`, so the lists that already drive the
sleeve report drive this too rather than drifting into a second definition.
A ticker appearing in two sleeves is refused rather than silently assigned,
because an ambiguous classification moves every other sleeve's weight
through the shared denominator.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

import config
from assistant.money import decimal_or_none, decimal_text

SLEEVE_CASH = "cash"
SLEEVE_DIVIDEND = "dividend_income"
SLEEVE_GROWTH = "growth"
SLEEVE_LEVERAGED = "leveraged_reinvestment"
SLEEVE_HEDGE = "hedge"
SLEEVE_OTHER = "other_unassigned"

#: Deterministic display order: cash first, the residual last, so a reader
#: always finds the two buckets that are easiest to misread at the edges.
SLEEVE_ORDER = (
    SLEEVE_CASH,
    SLEEVE_DIVIDEND,
    SLEEVE_GROWTH,
    SLEEVE_LEVERAGED,
    SLEEVE_HEDGE,
    SLEEVE_OTHER,
)

SLEEVE_LABELS = {
    SLEEVE_CASH: "Cash",
    SLEEVE_DIVIDEND: "Dividend income",
    SLEEVE_GROWTH: "Growth",
    SLEEVE_LEVERAGED: "Leveraged reinvestment",
    SLEEVE_HEDGE: "Hedge",
    SLEEVE_OTHER: "Other / unassigned",
}

#: Sleeves whose membership is a ticker list. Cash and the residual are
#: computed, not listed.
_TICKER_SLEEVES = {
    SLEEVE_DIVIDEND: "DIVIDEND_INCOME_TICKERS",
    SLEEVE_GROWTH: "GROWTH_ROTATION_TICKERS",
    SLEEVE_LEVERAGED: "DIVIDEND_REINVEST_TICKERS",
    SLEEVE_HEDGE: "HEDGE_SLEEVE_TICKERS",
}

MINIMUM_BAND_FRACTION = Decimal("0.01")
MAXIMUM_BAND_FRACTION = Decimal("1")


class AllocationProfileError(ValueError):
    """A profile that cannot be trusted to describe an allocation."""


@dataclasses.dataclass(frozen=True)
class AllocationProfile:
    """Owner-stated sleeve targets and the band around each one."""

    version: str
    name: str
    #: Sleeve -> exact target percentage of total equity, as decimal text.
    targets: Mapping[str, str]
    #: Relative fraction of each target, NOT percentage points. 0.25 means a
    #: 40% target tolerates 30-50% and a 10% target tolerates 7.5-12.5%, so
    #: "wide" keeps its meaning across targets of very different size.
    band_fraction: str
    notes: str = ""

    def __post_init__(self) -> None:
        # ``frozen=True`` does not freeze a nested dict. Copy before wrapping
        # so neither the caller nor later code can mutate the profile behind
        # a report's version/fingerprint.
        if not isinstance(self.targets, Mapping):
            raise AllocationProfileError("Profile targets must be a mapping.")
        object.__setattr__(self, "targets", MappingProxyType(dict(self.targets)))

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "name": self.name,
            "targets": dict(sorted(self.targets.items())),
            "band_fraction": self.band_fraction,
            "notes": self.notes,
        }

    def target_decimal(self, sleeve: str) -> Decimal:
        return Decimal(self.targets[sleeve])

    def band_decimal(self) -> Decimal:
        return Decimal(self.band_fraction)

    def band_edges(self, sleeve: str) -> tuple[Decimal, Decimal]:
        """Inclusive lower and upper edge for one sleeve, in percent."""
        target = self.target_decimal(sleeve)
        half_width = target * self.band_decimal()
        return target - half_width, target + half_width


def compute_profile_fingerprint(profile: AllocationProfile) -> str:
    """Deterministic fingerprint over every field except `notes`.

    Mirrors `compute_policy_fingerprint`: free-text notes are explanatory and
    do not change behaviour, but every target and the band do. Analysis and
    (in later stages) proposals bind to this, so an edited-but-not-rebumped
    profile still invalidates what was shown rather than being silently
    re-interpreted against numbers the reader never saw.
    """
    if not isinstance(profile, AllocationProfile):
        raise AllocationProfileError("An AllocationProfile is required.")
    payload = {k: v for k, v in profile.to_dict().items() if k != "notes"}
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def sleeve_membership() -> dict[str, str]:
    """Canonical ticker -> sleeve, built from `config`.

    Raises rather than choosing when a ticker appears in two sleeves: an
    ambiguous classification silently moves every other sleeve's weight
    through the shared equity denominator, so first-wins would be a hidden
    allocation decision.
    """
    membership: dict[str, str] = {}
    for sleeve, attribute in sorted(_TICKER_SLEEVES.items()):
        configured = getattr(config, attribute, ()) or ()
        if isinstance(configured, (str, bytes)):
            raise AllocationProfileError(
                f"{attribute} must be a collection of ticker strings."
            )
        for raw in configured:
            if not isinstance(raw, str) or not raw.strip():
                raise AllocationProfileError(
                    f"{attribute} contains an invalid ticker {raw!r}."
                )
            ticker = raw.strip().upper()
            existing = membership.get(ticker)
            if existing is not None and existing != sleeve:
                raise AllocationProfileError(
                    f"{ticker} is listed in both the {existing} and {sleeve} "
                    "sleeves; an ambiguous classification would move every "
                    "other sleeve's weight. Fix the config lists."
                )
            membership[ticker] = sleeve
    return membership


def validate_profile(profile: AllocationProfile) -> None:
    """Raise unless the profile describes a usable allocation."""
    if not isinstance(profile, AllocationProfile):
        raise AllocationProfileError("An AllocationProfile is required.")
    if not str(profile.version).strip():
        raise AllocationProfileError("The profile needs a version.")

    missing = [s for s in SLEEVE_ORDER if s not in profile.targets]
    if missing:
        raise AllocationProfileError(
            "Every sleeve needs a target, including the residual. Missing: "
            + ", ".join(missing)
        )
    unknown = sorted(set(profile.targets) - set(SLEEVE_ORDER))
    if unknown:
        raise AllocationProfileError(
            "Unknown sleeve(s) in the profile: " + ", ".join(unknown)
        )

    total = Decimal("0")
    for sleeve in SLEEVE_ORDER:
        target = decimal_or_none(profile.targets[sleeve])
        if target is None or target < 0 or target > 100:
            raise AllocationProfileError(
                f"{sleeve}'s target must be between 0 and 100, got "
                f"{profile.targets[sleeve]!r}."
            )
        total += target
    if total != 100:
        # Exactly 100, not "about 100": a profile summing to 99 or 101 makes
        # every percentage quietly mean something other than share-of-equity.
        raise AllocationProfileError(
            f"Sleeve targets must total exactly 100%, got {decimal_text(total)}%."
        )

    band = decimal_or_none(profile.band_fraction)
    if band is None or band < MINIMUM_BAND_FRACTION or band > MAXIMUM_BAND_FRACTION:
        raise AllocationProfileError(
            "The band must be a relative fraction between "
            f"{decimal_text(MINIMUM_BAND_FRACTION)} and "
            f"{decimal_text(MAXIMUM_BAND_FRACTION)}, got "
            f"{profile.band_fraction!r}."
        )
    sleeve_membership()  # refuse an ambiguous config here, not mid-report


#: The owner approved these exact numbers on 2026-08-15 after being shown the
#: portfolio's current sleeve weights. They are a PREFERENCE. The rationale
#: recorded at the time: cash 10% matches `min_cash_reserve_pct`, dividend
#: 15% is the top of the owner's stated 10-15% range, leveraged 15% sits
#: under the 20% `max_leveraged_etf_pct` cap, and the residual keeps a
#: deliberate 10% so unassigned holdings are budgeted rather than treated as
#: an error. Nothing here is derived from a research result.
OWNER_APPROVED_PROFILE = AllocationProfile(
    version="2026-08-15.1",
    name="Owner sleeve allocation (policy-anchored)",
    targets={
        SLEEVE_CASH: "10",
        SLEEVE_DIVIDEND: "15",
        SLEEVE_GROWTH: "40",
        SLEEVE_LEVERAGED: "15",
        SLEEVE_HEDGE: "10",
        SLEEVE_OTHER: "10",
    },
    band_fraction="0.25",
    notes=(
        "Owner-approved 2026-08-15. Targets and band are stated preference, "
        "not a research finding. The wide-band turnover result behind the "
        "mechanism was measured on the SOXX/SOXL vol-targeting pair and says "
        "nothing about this portfolio's shape."
    ),
)
