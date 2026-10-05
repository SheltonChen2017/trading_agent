"""Metadata-only SI-5 source preflight; never a point-in-time admission.

Separately supplied publication-schedule claims can check the date pair in
each release record, but matching caller-supplied dates and digests does not
authenticate the source document, original short-interest vintages, license,
or actual price coverage. This boundary deliberately returns a blocked
receipt even when every structural calendar check succeeds. It reads no
provider data and grants no outcome, QuantConnect, or trading authority.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.availability import release_execution_cohort
from research.short_interest_etf.contracts import (
    ReleaseCalendarEntry,
    ReleasePrecision,
    ShortInterestContractError,
    _canonical_date,
    _sha256,
)
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    SI5_OFFLINE_PROTOCOL_SHA256,
    require_si5_offline_protocol,
)


SI5_SOURCE_PREFLIGHT_VERSION = "si5-source-preflight-metadata-v1"
_FINRA_SCHEDULE_URL = (
    "https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest"
)
_BLOCKERS = (
    "schedule_extract_origin_and_bytes_unverified",
    "original_and_revision_vintages_unverified",
    "short_interest_and_price_usage_rights_unverified",
    "actual_price_volume_coverage_unverified",
    "security_identity_and_terminal_value_unverified",
    "quantconnect_project_and_dataset_route_unverified",
)


class SI5SourcePreflightError(ValueError):
    """A purported metadata-only source or schedule binding failed closed."""


def _refuse(detail: str) -> SI5SourcePreflightError:
    return SI5SourcePreflightError(f"REFUSED: {detail}")


@dataclasses.dataclass(frozen=True, slots=True)
class ScheduleDateClaim:
    """One *unverified extract* from a purported publication schedule.

    The digest is a caller claim, not proof that the URL served those bytes.
    The eventual source-admission stage must independently verify the artifact
    and provenance before calling any release historically available.
    """

    settlement_date: str
    public_release_date: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        try:
            if _canonical_date(
                self.public_release_date, "public_release_date"
            ) <= _canonical_date(self.settlement_date, "settlement_date"):
                raise _refuse("publication must follow settlement")
            _sha256(self.evidence_sha256, "evidence_sha256")
        except ShortInterestContractError as exc:
            raise _refuse(str(exc)) from exc


@dataclasses.dataclass(frozen=True, slots=True)
class SI5SourcePreflightReceipt:
    """Content-addressed calendar cross-check, permanently non-authoritative."""

    bound_releases: tuple[ReleaseCalendarEntry, ...]
    schedule_claims: tuple[ScheduleDateClaim, ...]

    def __post_init__(self) -> None:
        if type(self.bound_releases) is not tuple or not self.bound_releases:
            raise _refuse("receipt requires a nonempty tuple of releases")
        if type(self.schedule_claims) is not tuple or not self.schedule_claims:
            raise _refuse("receipt requires a nonempty tuple of schedule claims")
        # Frozen source contracts are not deeply immutable against a caller's
        # object.__setattr__. Capture detached schema instances at the edge.
        object.__setattr__(self, "bound_releases", tuple(
            _capture_release(release) for release in self.bound_releases
        ))
        object.__setattr__(self, "schedule_claims", tuple(
            _capture_claim(claim) for claim in self.schedule_claims
        ))
        self._validate()

    def _validate(self) -> None:
        if type(self) is not SI5SourcePreflightReceipt:
            raise _refuse("receipt must be the exact SI5SourcePreflightReceipt type")
        if type(self.bound_releases) is not tuple or not self.bound_releases:
            raise _refuse("receipt requires a nonempty tuple of releases")
        if type(self.schedule_claims) is not tuple or not self.schedule_claims:
            raise _refuse("receipt requires a nonempty tuple of schedule claims")
        claims_by_settlement: dict[str, ScheduleDateClaim] = {}
        for claim in self.schedule_claims:
            if type(claim) is not ScheduleDateClaim:
                raise _refuse("schedule claim must be the exact ScheduleDateClaim type")
            try:
                ScheduleDateClaim.__post_init__(claim)
            except (AttributeError, TypeError, ShortInterestContractError) as exc:
                raise _refuse(str(exc)) from exc
            if claim.settlement_date in claims_by_settlement:
                raise _refuse("duplicate schedule settlement")
            claims_by_settlement[claim.settlement_date] = claim
        keys: set[str] = set()
        settlements: set[str] = set()
        for release in self.bound_releases:
            if type(release) is not ReleaseCalendarEntry:
                raise _refuse("bound release must be the exact ReleaseCalendarEntry type")
            try:
                ReleaseCalendarEntry.__post_init__(release)
            except (AttributeError, TypeError, ShortInterestContractError) as exc:
                raise _refuse(str(exc)) from exc
            if release.precision is not ReleasePrecision.DATE_ONLY:
                raise _refuse("schedule-only evidence requires date-only precision")
            if release.key in keys or release.settlement_date in settlements:
                raise _refuse("duplicate bound release or settlement")
            claim = claims_by_settlement.get(release.settlement_date)
            if (
                claim is None
                or claim.public_release_date != release.public_release_date
                or claim.evidence_sha256 != release.evidence_sha256
            ):
                raise _refuse("bound release disagrees with schedule claim")
            keys.add(release.key)
            settlements.add(release.settlement_date)
        if settlements != set(claims_by_settlement):
            raise _refuse("schedule contains an unbound release settlement")
        if tuple(sorted(self.bound_releases, key=lambda row: row.settlement_date)) != self.bound_releases:
            raise _refuse("bound releases must be sorted by settlement date")
        if tuple(sorted(self.schedule_claims, key=lambda row: row.settlement_date)) != self.schedule_claims:
            raise _refuse("schedule claims must be sorted by settlement date")

    def to_payload(self) -> dict[str, Any]:
        SI5SourcePreflightReceipt._validate(self)
        require_si5_offline_protocol(SI5_OFFLINE_PROTOCOL)
        bindings = []
        for release in self.bound_releases:
            cohort = release_execution_cohort(release)
            bindings.append({
                "settlement_date": release.settlement_date,
                "release_calendar_key": release.key,
                "schedule_evidence_sha256_claim": release.evidence_sha256,
                "bound_release": ReleaseCalendarEntry.to_payload(release),
                "execution_session": cohort.session,
                "execution_open_at": cohort.opens_at,
            })
        return {
            "schema": SI5_SOURCE_PREFLIGHT_VERSION,
            "offline_protocol_sha256": SI5_OFFLINE_PROTOCOL_SHA256,
            "finra_publication_schedule_url": _FINRA_SCHEDULE_URL,
            "calendar_check": "date_and_digest_structural_match_only",
            "short_interest_route": "quantconnect_finra_short_interest_candidate_only",
            "price_volume_route": "quantconnect_us_equities_candidate_only",
            "price_crosscheck_route": "sharadar_sep_candidate_only",
            "candidate_lookbacks": [20, 60, 120, 252],
            "separate_coverage_audit_target_sessions": 60,
            "coverage_audit_does_not_change_candidate_eligibility": True,
            "schedule_claims": [
                dataclasses.asdict(claim) for claim in self.schedule_claims
            ],
            "release_bindings": bindings,
            "blockers": list(_BLOCKERS),
            "source_admitted": False,
            "point_in_time_data_verified": False,
            "outcome_access_authorized": False,
            "qc_backtest_authorized": False,
            "authorized_outcome_looks": 0,
            "consumed_outcome_looks": 0,
            "production_authoritative": False,
            "trading_authority": False,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(SI5SourcePreflightReceipt.to_payload(self))


def _capture_release(value: ReleaseCalendarEntry) -> ReleaseCalendarEntry:
    if type(value) is not ReleaseCalendarEntry:
        raise _refuse("release must be the exact ReleaseCalendarEntry type")
    try:
        # Read schema fields, not instance methods that an unslotted caller can
        # shadow. Reconstructing also validates any post-construction mutation.
        return ReleaseCalendarEntry(**{
            field.name: getattr(value, field.name)
            for field in dataclasses.fields(ReleaseCalendarEntry)
        })
    except (AttributeError, TypeError, ShortInterestContractError) as exc:
        raise _refuse(str(exc)) from exc


def _capture_claim(value: ScheduleDateClaim) -> ScheduleDateClaim:
    if type(value) is not ScheduleDateClaim:
        raise _refuse("schedule claim must be the exact ScheduleDateClaim type")
    try:
        return ScheduleDateClaim(**{
            field.name: getattr(value, field.name)
            for field in dataclasses.fields(ScheduleDateClaim)
        })
    except (AttributeError, TypeError) as exc:
        raise _refuse(str(exc)) from exc


def build_si5_source_preflight(
    releases: tuple[ReleaseCalendarEntry, ...],
    schedule_claims: tuple[ScheduleDateClaim, ...],
) -> SI5SourcePreflightReceipt:
    """Cross-check claimed FINRA date pairs; force date-only next-open timing.

    This does not verify the claimed source bytes, vintages, rights, or market
    rows, so even a structurally matching receipt always remains blocked.
    """
    if type(releases) is not tuple or not releases:
        raise _refuse("release calendar must be a nonempty exact tuple")
    if type(schedule_claims) is not tuple or not schedule_claims:
        raise _refuse("schedule claims must be a nonempty exact tuple")

    schedule_by_settlement: dict[str, ScheduleDateClaim] = {}
    for raw_claim in schedule_claims:
        claim = _capture_claim(raw_claim)
        if claim.settlement_date in schedule_by_settlement:
            raise _refuse("duplicate schedule settlement")
        schedule_by_settlement[claim.settlement_date] = claim

    bound: list[ReleaseCalendarEntry] = []
    seen_settlements: set[str] = set()
    for raw_release in releases:
        release = _capture_release(raw_release)
        if release.settlement_date in seen_settlements:
            raise _refuse("duplicate release settlement")
        seen_settlements.add(release.settlement_date)
        claim = schedule_by_settlement.get(release.settlement_date)
        if claim is None:
            raise _refuse("release has no independent schedule-date claim")
        if claim.public_release_date != release.public_release_date:
            raise _refuse("publication date disagrees with schedule claim")
        if claim.evidence_sha256 != release.evidence_sha256:
            raise _refuse("release evidence digest disagrees with schedule claim")
        # A public schedule date alone cannot establish a pre-open exact time.
        # Reuse the existing next-open function with a conservative date-only
        # release, even if an upstream row purported to have an exact time.
        bound.append(dataclasses.replace(
            release,
            precision=ReleasePrecision.DATE_ONLY,
            public_release_at=None,
        ))

    if seen_settlements != set(schedule_by_settlement):
        raise _refuse("schedule includes an unbound release settlement")
    return SI5SourcePreflightReceipt(
        bound_releases=tuple(
            sorted(bound, key=lambda release: release.settlement_date)
        ),
        schedule_claims=tuple(
            sorted(schedule_by_settlement.values(), key=lambda claim: claim.settlement_date)
        ),
    )
