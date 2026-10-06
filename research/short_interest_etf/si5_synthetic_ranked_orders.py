"""Fixed-fixture SI-2B/P1C ranking-to-order integration rehearsal.

This module constructs one code-owned, synthetic-only source fixture and runs
it through the genuine investability, eligible-population, binding, ranking,
and SI-5 cohort builders before adapting original low-pressure tails to long
orders and original high-pressure tails to avoidance.  Its public entry point
accepts only the single built-in scenario ID.  It accepts no rows, source/PIT
assertions, prices, memberships, dates, or authority from a caller.

The three fabricated release cycles are deliberately visible: the first is a
warm-up refusal, the second is executable because it has an authenticated
synthetic successor, and the third is retained as ``no_successor_release``.
Every candidate lookback and every frozen cost remains separate.  The result
is software-plumbing evidence only; it is not a market outcome, a source
admission, a production latency claim, or backtesting/trading authority.
"""
from __future__ import annotations

import dataclasses
import json
from copy import deepcopy
from datetime import date
from typing import Any

from data.exchange_calendar import trading_sessions
from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.contracts import (
    CollectionManifest,
    DenominatorKind,
    DenominatorObservation,
    ReleaseCalendarEntry,
    ReleasePrecision,
    SecurityIdentity,
    ShortInterestSnapshot,
    SourceEntitlement,
    SourceSemantic,
    VolumeBasis,
    parse_utc_timestamp,
    recompute_days_to_cover,
)
from research.short_interest_etf.dataset import (
    ShortInterestVintage,
    build_identity,
    build_vintage,
    fixture_source_payload_sha256,
)
from research.short_interest_etf.pit_eligibility import (
    ListingStatus,
    PitReferenceBundle,
    PitReferenceManifest,
    SecurityLifecycleObservation,
    SectorClassificationObservation,
    reference_fixture_body_sha256,
)
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    SI5_OFFLINE_PROTOCOL_SHA256,
    require_si5_offline_protocol,
)
from research.short_interest_etf.si5_stock_cohort import (
    build_si5_stock_cohort_manifest,
)
from research.short_interest_etf.si5_synthetic_orders import (
    _SyntheticEvent,
    _SyntheticEventKind,
    _SyntheticScenario,
    _run_synthetic_order_kernel,
    _scenario_payload,
)
from research.short_interest_etf.si5_synthetic_policy import (
    SI5_SYNTHETIC_POLICY_SHA256,
    synthetic_policy_payload,
)
from research.short_interest_etf.stock_eligible_population import (
    build_stock_eligible_population_inventory,
)
from research.short_interest_etf.stock_eligible_ranking import (
    build_stock_eligible_ranking_inventory,
)
from research.short_interest_etf.stock_investability import (
    DailyLiquidityObservation,
    MarketCapObservation,
    SyntheticMarketHistory,
    build_stock_investability,
)
from research.short_interest_etf.stock_population_binding import (
    build_stock_population_binding_inventory,
)


SI5_SYNTHETIC_RANKED_ORDER_VERSION = "si5-synthetic-ranked-orders-v1"
SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID = (
    "si5-synthetic-ranked-order-routing-v1"
)

_DECISION_RECORD_PATH = (
    "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md"
)
_DECISION_RECORD_COMMIT = "782e85ecd2867537f5f7e93abe4d9ab66eb9bddc"
_DECISION_RECORD_RAW_SHA256 = (
    "a2c8e49681dd890583255f336c838b79b415dd70c8a078e221f41a9f05fde177"
)
_AUTHORITY_ID = "SI-AUTH-20261006-06"
_DECISION_IDS = (
    "SI-DEC-20261006-09",
    "SI-DEC-20261006-10",
    "SI-DEC-20261006-11",
)
_LOOKBACKS = (20, 60, 120, 252)
_COSTS_BPS = (0, 5, 10, 20)
_SECURITY_COUNT = 20
_REFUSED_SECURITY_INDEX = 19
_INITIAL_CASH_USD = "19000"
_INSTRUCTION_AT = "2024-02-13T13:00:00Z"
_SOURCE_ID = "synthetic-si5-ranked-routing-v1"
_SOURCE_VERSION = "2026-10-06.v1"
_REFERENCE_SOURCE_ID = "synthetic-si5-ranked-reference-v1"

# These literals are filled only from a locally constructed, caller-free
# fixture and then enforced by every public run.  They are intentionally not
# derived from an external file or a caller-supplied assertion.
SI5_SYNTHETIC_RANKED_ORDER_POLICY_SHA256 = (
    "85704221bb8e7333f2bdbb45751f030fe7cbd8a4a17fedc8dc0615d1c4bd9eda"
)
SI5_SYNTHETIC_RANKED_ORDER_RECIPE_SHA256 = (
    "a3d72cc3d9f4218bd1873169ce2d61a021dc866561b87c0c2f95bce31f74c58a"
)
SI5_SYNTHETIC_RANKED_ORDER_RESULT_SHA256 = (
    "9d2ce7bbdf716623adab59722478eee5e6d4550ac9108880f6a60c7e092055c2"
)
_EXPECTED_SOURCE_VINTAGE_SHA256 = (
    "b07a41c47140782a48bb0ede4b078abaa3fd6758ae2f38771042b881ae6c117c"
)
_EXPECTED_REFERENCE_BUNDLE_SHA256 = (
    "eb99f39b997c7d6e1c17e93ab85989bce16ea8822e84fad5473c655a3ea5f417"
)
_EXPECTED_MARKET_HISTORY_SHA256 = (
    "8babc07835793cd8548154f83b5b90eb173ca277441f3d3b98cc587c7cffe71e"
)
_EXPECTED_POPULATION_INVENTORY_SHA256 = (
    "6c87ad29bd97014251ff42e20de8dbbe399e58385fb76ad403aded40d4ddb392"
)
_EXPECTED_BINDING_INVENTORY_SHA256 = (
    "6980e9e6067a755be10f16a4e0a53e61494274f88a9297cfae6e8bd2c93e89d7"
)
_EXPECTED_RANKING_INVENTORY_SHA256 = (
    "04a4304e2d62c5fd2d8b5a8bcdc44fd70b011c77ea03c9466465f6e0b268e577"
)
_EXPECTED_COHORT_MANIFEST_SHA256 = (
    "9dd99147ecf303399288faba11b522acf171aa8df44b93c5a8852da3a58a33bb"
)
_EXPECTED_ROUTING_SHA256 = (
    "93d68e02851413686277916a09e20fd012f643d81f153e60a1af0e53493841bb"
)


class SI5SyntheticRankedOrderError(ValueError):
    """The fixed synthetic ranking-to-order rehearsal failed closed."""


def _refuse(detail: str) -> SI5SyntheticRankedOrderError:
    return SI5SyntheticRankedOrderError(f"REFUSED: {detail}")


def _sha(label: str) -> str:
    return hash_payload({"synthetic_si5_ranked_orders": label})


def _zero_authority_payload() -> dict[str, Any]:
    return {
        "actual_source_admitted": False,
        "actual_source_ranking_to_orders_admitted": False,
        "allocated_alpha": {"numerator": 0, "denominator": 1},
        "authorized_real_outcome_looks": 0,
        "consumed_real_outcome_looks": 0,
        "market_edge_evidence": False,
        "outcome_access_authorized": False,
        "point_in_time_data_verified": False,
        "permanent_look_ids": [],
        "production_authoritative": False,
        "qc_backtest_authorized": False,
        "real_backtesting_ready": False,
        "selected_lookback": None,
        "synthetic_only": True,
        "trading_authority": False,
    }


def _bridge_policy_payload() -> dict[str, Any]:
    return {
        "policy_id": "si5-fixed-ranked-order-integration-policy-v1",
        "authority_id": _AUTHORITY_ID,
        "decision_ids": list(_DECISION_IDS),
        "decision_record_path": _DECISION_RECORD_PATH,
        "decision_record_commit": _DECISION_RECORD_COMMIT,
        "decision_record_raw_sha256": _DECISION_RECORD_RAW_SHA256,
        "public_input": "exact_builtin_scenario_id_only",
        "pipeline": [
            "stock_investability",
            "eligible_population",
            "population_binding",
            "eligible_s1_ranking",
            "si5_stock_cohort",
            "synthetic_order_kernel",
        ],
        "release_cycle_count": 3,
        "security_count": _SECURITY_COUNT,
        "eligible_security_count": _SECURITY_COUNT - 1,
        "candidate_lookbacks": list(_LOOKBACKS),
        "cost_bps_per_side": list(_COSTS_BPS),
        "routing_rule": (
            "original_common_low_pressure_tail_long_and_original_common_"
            "high_pressure_tail_avoided_never_rerank_or_short"
        ),
        "execution_rule": (
            "every_comparable_release_with_authenticated_synthetic_successor"
        ),
        "entry_clock": "canonical_cohort_decision_at_release_next_XNYS_open",
        "instruction_clock": "separate_fixed_synthetic_preopen_after_entry_facts",
        "exit_clock": "authenticated_successor_release_next_XNYS_open",
        "missing_price_rule": "whole_common_cohort_atomic_refusal_before_tail_routing",
        "warmup_rule": "retain_all_four_windows_as_explicit_cohort_refusals",
        "terminal_rule": "retain_all_four_windows_as_no_successor_release",
        "demonstration_policy_sha256": SI5_SYNTHETIC_POLICY_SHA256,
        "si5_offline_protocol_sha256": SI5_OFFLINE_PROTOCOL_SHA256,
        "selected_lookback": None,
        **_zero_authority_payload(),
    }


def _require_bridge_policy() -> dict[str, Any]:
    if (
        _DECISION_RECORD_COMMIT
        != "782e85ecd2867537f5f7e93abe4d9ab66eb9bddc"
        or _DECISION_RECORD_RAW_SHA256
        != "a2c8e49681dd890583255f336c838b79b415dd70c8a078e221f41a9f05fde177"
        or _AUTHORITY_ID != "SI-AUTH-20261006-06"
        or _DECISION_IDS
        != (
            "SI-DEC-20261006-09",
            "SI-DEC-20261006-10",
            "SI-DEC-20261006-11",
        )
    ):
        raise _refuse("bridge decision anchor changed")
    demonstration = synthetic_policy_payload()
    if (
        type(demonstration) is not dict
        or hash_payload(demonstration) != SI5_SYNTHETIC_POLICY_SHA256
    ):
        raise _refuse("synthetic demonstration policy authentication failed")
    if require_si5_offline_protocol(SI5_OFFLINE_PROTOCOL) != (
        SI5_OFFLINE_PROTOCOL_SHA256
    ):
        raise _refuse("SI-5 offline protocol authentication failed")
    payload = _bridge_policy_payload()
    if hash_payload(payload) != SI5_SYNTHETIC_RANKED_ORDER_POLICY_SHA256:
        raise _refuse("bridge policy differs from its pinned digest")
    return payload


def _security_rows() -> list[dict[str, Any]]:
    rows = []
    for index in range(_SECURITY_COUNT):
        rows.append(
            {
                "index": index,
                "security_id": f"sec-si5-ranked-{index:03d}",
                "security_identity_sha256": hash_payload(
                    _identity(index).to_payload()
                ),
                "ticker": f"R{index:03d}",
                "current_short_shares_by_cycle": [
                    130 - index,
                    100 + index,
                    140 - index,
                ],
                "eligible": index != _REFUSED_SECURITY_INDEX,
                "entry_raw_open_usd": str(100 + index),
                "exit_raw_open_usd": str(102 + index),
            }
        )
    return rows


def _release_rows() -> list[dict[str, str]]:
    return [
        {
            "settlement_date": "2024-01-12",
            "previous_settlement_date": "2023-12-29",
            "filing_deadline_date": "2024-01-19",
            "public_release_date": "2024-01-25",
            "public_release_at": "2024-01-25T21:00:00Z",
            "observed_at": "2024-01-25T22:00:00Z",
            "execution_session": "2024-01-26",
            "volume_window_start": "2023-12-13",
            "last_completed_session": "2024-01-25",
        },
        {
            "settlement_date": "2024-01-31",
            "previous_settlement_date": "2024-01-12",
            "filing_deadline_date": "2024-02-07",
            "public_release_date": "2024-02-12",
            "public_release_at": "2024-02-12T21:00:00Z",
            "observed_at": "2024-02-12T22:00:00Z",
            "execution_session": "2024-02-13",
            "volume_window_start": "2024-01-02",
            "last_completed_session": "2024-02-12",
        },
        {
            "settlement_date": "2024-02-15",
            "previous_settlement_date": "2024-01-31",
            "filing_deadline_date": "2024-02-22",
            "public_release_date": "2024-02-27",
            "public_release_at": "2024-02-27T21:00:00Z",
            "observed_at": "2024-02-27T22:00:00Z",
            "execution_session": "2024-02-28",
            "volume_window_start": "2024-01-16",
            "last_completed_session": "2024-02-27",
        },
    ]


def _fixture_recipe_payload() -> dict[str, Any]:
    return {
        "schema": "si5-synthetic-ranked-order-fixture-recipe-v1",
        "scenario_id": SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID,
        "source_id": _SOURCE_ID,
        "source_version": _SOURCE_VERSION,
        "reference_source_id": _REFERENCE_SOURCE_ID,
        "securities": _security_rows(),
        "releases": _release_rows(),
        "history_rule": (
            "union_of_exact_252_session_windows_before_each_release_next_open"
        ),
        "daily_close_usd": "100",
        "daily_volume_shares": 100000,
        "eligible_market_cap_usd": "300000000",
        "refused_market_cap_usd": "299999999",
        "refused_security_index": _REFUSED_SECURITY_INDEX,
        "instruction_at": _INSTRUCTION_AT,
        "initial_cash_usd": _INITIAL_CASH_USD,
        "candidate_lookbacks": list(_LOOKBACKS),
        "cost_bps_per_side": list(_COSTS_BPS),
        "demonstration_policy_sha256": SI5_SYNTHETIC_POLICY_SHA256,
        "bridge_policy_sha256": SI5_SYNTHETIC_RANKED_ORDER_POLICY_SHA256,
        "si5_offline_protocol_sha256": SI5_OFFLINE_PROTOCOL_SHA256,
        "synthetic_only": True,
    }


def _identity(index: int) -> SecurityIdentity:
    security_id = f"sec-si5-ranked-{index:03d}"
    return SecurityIdentity(
        security_id=security_id,
        vendor_security_id=f"vendor-si5-ranked-{index:03d}",
        qc_symbol=None,
        ticker=f"R{index:03d}",
        share_class="A",
        primary_venue="XNYS",
        country="US",
        security_type="COMMON_STOCK",
        valid_from="2020-01-01",
        valid_to=None,
        predecessor_security_id=None,
        successor_security_id=None,
        identity_source_id="synthetic-si5-ranked-security-master",
        identity_source_version="2024.v1",
        raw_record_sha256=_sha(f"identity:{index}"),
    )


def _build_vintage() -> ShortInterestVintage:
    release_specs = _release_rows()
    releases = tuple(
        ReleaseCalendarEntry(
            calendar_id="synthetic-si5-ranked-calendar-v1",
            settlement_date=spec["settlement_date"],
            filing_deadline_date=spec["filing_deadline_date"],
            public_release_date=spec["public_release_date"],
            public_release_at=spec["public_release_at"],
            precision=ReleasePrecision.EXACT_TIMESTAMP,
            source_id="synthetic-si5-ranked-release-calendar",
            source_version="2024.v1",
            evidence_sha256=_sha(f"release:{spec['settlement_date']}"),
            observed_at=spec["observed_at"],
        )
        for spec in release_specs
    )
    identities = tuple(_identity(index) for index in range(_SECURITY_COUNT))
    shares = [
        row["current_short_shares_by_cycle"] for row in _security_rows()
    ]
    snapshots: list[ShortInterestSnapshot] = []
    for cycle, (release, spec) in enumerate(zip(releases, release_specs, strict=True)):
        for index, security in enumerate(identities):
            current = shares[index][cycle]
            previous = 120 - index if cycle == 0 else shares[index][cycle - 1]
            volume = VolumeBasis(
                security_id=security.security_id,
                average_daily_share_volume="100",
                lookback_sessions=20,
                window_start_date=spec["volume_window_start"],
                window_end_date=spec["settlement_date"],
                available_at=spec["public_release_at"].replace("21:00", "20:00"),
                observed_at=spec["observed_at"],
                definition_id="mean_consolidated_daily_share_volume_20_sessions",
                source_id="synthetic-si5-ranked-volume",
                source_version="2024.v1",
                raw_record_sha256=_sha(
                    f"volume:{security.security_id}:{spec['settlement_date']}"
                ),
            )
            denominator = DenominatorObservation(
                security_id=security.security_id,
                kind=DenominatorKind.POINT_IN_TIME_SHARES_OUTSTANDING,
                value="10000",
                effective_date=spec["settlement_date"],
                available_at=spec["public_release_at"].replace("21:00", "20:00"),
                observed_at=spec["observed_at"],
                source_id="synthetic-si5-ranked-fundamentals",
                source_version="2024.v1",
                raw_record_sha256=_sha(
                    f"denominator:{security.security_id}:{spec['settlement_date']}"
                ),
            )
            days_to_cover = recompute_days_to_cover(
                current, volume.average_daily_share_volume
            )
            snapshots.append(
                ShortInterestSnapshot(
                    semantic=SourceSemantic.OFFICIAL_OPEN_SHORT_POSITION_SNAPSHOT,
                    source_id=_SOURCE_ID,
                    source_version=_SOURCE_VERSION,
                    source_record_id=(
                        f"{security.security_id}:{spec['settlement_date']}:r1"
                    ),
                    security=security,
                    settlement_date=spec["settlement_date"],
                    current_short_shares=current,
                    previous_settlement_date=spec["previous_settlement_date"],
                    previous_short_shares=previous,
                    release_calendar_key=release.key,
                    volume_basis=volume,
                    reported_days_to_cover=days_to_cover,
                    recomputed_days_to_cover=days_to_cover,
                    denominator=denominator,
                    revision_id="r1",
                    revision_published_at=spec["public_release_at"],
                    observed_at=spec["observed_at"],
                    supersedes_event_id=None,
                    raw_record_sha256=_sha(
                        f"snapshot:{security.security_id}:{spec['settlement_date']}"
                    ),
                )
            )
    raw_artifact_sha256 = fixture_source_payload_sha256(
        [release.to_payload() for release in releases],
        [snapshot.to_payload() for snapshot in snapshots],
    )
    manifest = CollectionManifest(
        source_dataset_id="synthetic-si5-ranked-three-cycle-v1",
        snapshot_name="synthetic-si5-ranked-three-cycle-fixed-fixture",
        source_id=_SOURCE_ID,
        source_version=_SOURCE_VERSION,
        endpoint_schema_version="synthetic.1",
        semantic=SourceSemantic.OFFICIAL_OPEN_SHORT_POSITION_SNAPSHOT,
        entitlement=SourceEntitlement.SYNTHETIC_FIXTURE_ONLY,
        retrieved_at="2024-02-28T22:00:00Z",
        settlement_start=release_specs[0]["settlement_date"],
        settlement_end=release_specs[-1]["settlement_date"],
        requested_record_count=len(snapshots),
        input_row_count=len(snapshots),
        accepted_record_count=len(snapshots),
        refusal_count=0,
        raw_artifact_sha256=raw_artifact_sha256,
        collector_git_commit=_DECISION_RECORD_COMMIT,
    )
    return build_vintage(manifest, releases, snapshots)


def _build_references() -> PitReferenceBundle:
    lifecycles = tuple(
        SecurityLifecycleObservation(
            security_id=f"sec-si5-ranked-{index:03d}",
            status=ListingStatus.LISTED,
            effective_date="2020-01-01",
            available_at="2020-01-02T15:00:00Z",
            observed_at="2020-01-02T15:00:00Z",
            unresolved_actions=(),
            source_id=_REFERENCE_SOURCE_ID,
            source_version="2024.v1",
            raw_record_sha256=_sha(f"lifecycle:{index}"),
        )
        for index in range(_SECURITY_COUNT)
    )
    classifications = tuple(
        SectorClassificationObservation(
            security_id=f"sec-si5-ranked-{index:03d}",
            taxonomy_id="SYNTHETIC_SECTOR_V1",
            sector_code="TECHNOLOGY",
            industry_code="SYNTHETIC_TECHNOLOGY",
            valid_from="2020-01-01",
            valid_to=None,
            available_at="2020-01-02T15:00:00Z",
            observed_at="2020-01-02T15:00:00Z",
            source_id="synthetic-si5-ranked-sector-master",
            source_version="2024.v1",
            raw_record_sha256=_sha(f"classification:{index}"),
        )
        for index in range(_SECURITY_COUNT)
    )
    body_sha256 = reference_fixture_body_sha256(
        [row.to_payload() for row in lifecycles],
        [row.to_payload() for row in classifications],
    )
    manifest = PitReferenceManifest(
        reference_dataset_id="synthetic-si5-ranked-reference-three-cycle-v1",
        source_id=_REFERENCE_SOURCE_ID,
        source_version="2024.v1",
        semantic="pit_security_lifecycle_and_sector_reference",
        entitlement=SourceEntitlement.SYNTHETIC_FIXTURE_ONLY,
        retrieved_at="2024-01-03T15:00:00Z",
        lifecycle_record_count=len(lifecycles),
        classification_record_count=len(classifications),
        source_body_sha256=body_sha256,
        collector_git_commit=_DECISION_RECORD_COMMIT,
    )
    return PitReferenceBundle(manifest, lifecycles, classifications)


def _history_sessions() -> tuple[str, ...]:
    sessions: set[str] = set()
    for spec in _release_rows():
        window = trading_sessions(
            date(2022, 1, 1),
            date.fromisoformat(spec["last_completed_session"]),
        )[-252:]
        if len(window) != 252:
            raise _refuse("fixed fixture cannot construct a 252-session history")
        sessions.update(session.isoformat() for session in window)
    return tuple(sorted(sessions))


def _build_history(vintage: ShortInterestVintage) -> SyntheticMarketHistory:
    identities = {
        snapshot.security.security_id: hash_payload(snapshot.security.to_payload())
        for snapshot in vintage.snapshots
    }
    sessions = _history_sessions()
    daily = tuple(
        DailyLiquidityObservation(
            security_id=security_id,
            security_identity_sha256=identity,
            session=session,
            close_usd="100",
            volume_shares=100000,
            available_at=f"{session}T23:00:00Z",
            observed_at=f"{session}T23:00:00Z",
            raw_record_sha256=_sha(f"daily:{security_id}:{session}"),
        )
        for security_id, identity in sorted(identities.items())
        for session in sessions
    )
    cap_sessions = tuple(
        spec["last_completed_session"] for spec in _release_rows()
    )
    capitalizations = tuple(
        MarketCapObservation(
            security_id=security_id,
            security_identity_sha256=identity,
            session=session,
            market_cap_usd=(
                "299999999"
                if security_id
                == f"sec-si5-ranked-{_REFUSED_SECURITY_INDEX:03d}"
                else "300000000"
            ),
            available_at=f"{session}T23:00:00Z",
            observed_at=f"{session}T23:00:00Z",
            raw_record_sha256=_sha(f"cap:{security_id}:{session}"),
        )
        for security_id, identity in sorted(identities.items())
        for session in cap_sessions
    )
    return SyntheticMarketHistory(
        daily=daily,
        capitalizations=capitalizations,
        source_id="synthetic-si5-ranked-market-history-v1",
    )


@dataclasses.dataclass(frozen=True, slots=True)
class _FixtureSources:
    vintage: ShortInterestVintage
    references: PitReferenceBundle
    history: SyntheticMarketHistory


def _build_fixture_sources() -> _FixtureSources:
    vintage = _build_vintage()
    return _FixtureSources(
        vintage=vintage,
        references=_build_references(),
        history=_build_history(vintage),
    )


def _source_identities(sources: _FixtureSources) -> dict[str, str]:
    return {
        "source_vintage_sha256": build_identity(sources.vintage)["content_hash"],
        "reference_bundle_sha256": sources.references.sha256,
        "market_history_sha256": sources.history.sha256,
    }


def _entry_fact_witness(
    sources: _FixtureSources,
    *,
    settlement_date: str,
    entry_open_at: str,
) -> dict[str, Any]:
    entry = parse_utc_timestamp(entry_open_at, "entry_open_at")
    times: list[tuple[str, str]] = []
    release = next(
        row
        for row in sources.vintage.release_calendar
        if row.settlement_date == settlement_date
    )
    times.extend(
        (
            ("release.public_release_at", release.public_release_at or ""),
            ("release.observed_at", release.observed_at),
        )
    )
    for snapshot in sources.vintage.snapshots:
        if snapshot.settlement_date != settlement_date:
            continue
        times.extend(
            (
                ("snapshot.revision_published_at", snapshot.revision_published_at),
                ("snapshot.observed_at", snapshot.observed_at),
                ("volume.available_at", snapshot.volume_basis.available_at),
                ("volume.observed_at", snapshot.volume_basis.observed_at),
                ("denominator.available_at", snapshot.denominator.available_at),
                ("denominator.observed_at", snapshot.denominator.observed_at),
            )
        )
    for row in (*sources.references.lifecycles, *sources.references.classifications):
        times.extend(
            (
                ("reference.available_at", row.available_at),
                ("reference.observed_at", row.observed_at),
            )
        )
    for row in (*sources.history.daily, *sources.history.capitalizations):
        if date.fromisoformat(row.session) >= entry.date():
            continue
        times.extend(
            (
                ("market.available_at", row.available_at),
                ("market.observed_at", row.observed_at),
            )
        )
    if any(not value for _, value in times):
        raise _refuse("entry fact witness contains an unavailable timestamp")
    latest_name, latest_at = max(
        times,
        key=lambda item: parse_utc_timestamp(item[1], item[0]),
    )
    instruction = parse_utc_timestamp(_INSTRUCTION_AT, "instruction_at")
    if not parse_utc_timestamp(latest_at, latest_name) < instruction < entry:
        raise _refuse(
            "entry facts, synthetic instruction, and canonical entry open are misordered"
        )
    witness = {
        "settlement_date": settlement_date,
        "entry_open_at": entry_open_at,
        "instruction_at": _INSTRUCTION_AT,
        "latest_entry_fact_name": latest_name,
        "latest_entry_fact_observed_at": latest_at,
        "authenticated_fact_timestamp_count": len(times),
        "semantic": (
            "fixture_entry_membership_facts_observed_before_instruction;"
            "future_successor_and_open_prices_are_not_entry_selection_facts"
        ),
    }
    witness["entry_fact_witness_sha256"] = hash_payload(witness)
    return witness


def _comparison_route(
    row: dict[str, Any],
    price_pair: dict[str, Any] | None,
) -> dict[str, Any]:
    route = {
        "event_id": row["event_id"],
        "security_id": row["security_id"],
        "security_identity_sha256": row["security_identity_sha256"],
        "pressure_row_sha256": row["pressure_row_sha256"],
        "covering_row_sha256": row["covering_row_sha256"],
        "high_pressure_tail": row["high_pressure_tail"],
        "low_pressure_tail": row["low_pressure_tail"],
        "entry_price_event_id": (
            None if price_pair is None else price_pair["entry_price_event_id"]
        ),
        "exit_price_event_id": (
            None if price_pair is None else price_pair["exit_price_event_id"]
        ),
    }
    route["route_member_sha256"] = hash_payload(route)
    return route


def _price_pairs(
    release: dict[str, Any], successor: dict[str, Any]
) -> list[dict[str, Any]]:
    first_window = release["lookbacks"][0]
    by_identity = {
        row["security_identity_sha256"]: row
        for row in first_window["comparison_rows"]
    }
    common = release["common_security_identity_sha256s"]
    if set(by_identity) != set(common) or len(by_identity) != len(common):
        raise _refuse("common cohort lacks a unique stable-identity price mapping")
    recipe = {row["security_id"]: row for row in _security_rows()}
    pairs = []
    for identity in common:
        comparison = by_identity[identity]
        security_id = comparison["security_id"]
        source = recipe.get(security_id)
        if source is None:
            raise _refuse("common cohort identity is absent from the fixed price recipe")
        if source["security_identity_sha256"] != identity:
            raise _refuse(
                "common cohort stable identity differs from the fixed price recipe"
            )
        pair = {
            "event_id": comparison["event_id"],
            "security_id": security_id,
            "security_identity_sha256": identity,
            "entry_open_at": release["decision_at"],
            "entry_price_event_id": f"ranked-entry:{security_id}",
            "entry_raw_open_usd": source["entry_raw_open_usd"],
            "exit_open_at": successor["decision_at"],
            "exit_price_event_id": f"ranked-exit:{security_id}",
            "exit_raw_open_usd": source["exit_raw_open_usd"],
            "synthetic_only": True,
        }
        # Validate every common-cohort open before any tail is selected.  The
        # order kernel later sees only long/avoided tails, so relying on it
        # would allow a malformed middle-member price to disappear silently.
        _SyntheticEvent(
            event_id=pair["entry_price_event_id"],
            security_identity_sha256=identity,
            at=pair["entry_open_at"],
            kind=_SyntheticEventKind.OPEN,
            raw_open_usd=pair["entry_raw_open_usd"],
        )
        _SyntheticEvent(
            event_id=pair["exit_price_event_id"],
            security_identity_sha256=identity,
            at=pair["exit_open_at"],
            kind=_SyntheticEventKind.OPEN,
            raw_open_usd=pair["exit_raw_open_usd"],
        )
        pair["price_pair_sha256"] = hash_payload(pair)
        pairs.append(pair)
    pairs.sort(key=lambda row: row["security_identity_sha256"])
    if [row["security_identity_sha256"] for row in pairs] != sorted(common):
        raise _refuse("price pairs do not cover the complete common cohort")
    return pairs


def _tail_routes(
    window: dict[str, Any],
    price_pairs: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    comparisons = {row["event_id"]: row for row in window["comparison_rows"]}
    if len(comparisons) != len(window["comparison_rows"]):
        raise _refuse("comparison rows repeat an event")
    pairs = {} if price_pairs is None else {
        row["security_identity_sha256"]: row for row in price_pairs
    }

    def project(event_ids: list[str], tail_name: str) -> list[dict[str, Any]]:
        rows = []
        for event_id in event_ids:
            comparison = comparisons.get(event_id)
            if comparison is None or comparison[tail_name] is not True:
                raise _refuse("tail event differs from its original comparison row")
            pair = pairs.get(comparison["security_identity_sha256"])
            if price_pairs is not None and pair is None:
                raise _refuse("tail member lacks a whole-cohort price pair")
            rows.append(_comparison_route(comparison, pair))
        return sorted(rows, key=lambda row: row["security_identity_sha256"])

    long_routes = project(window["low_pressure_event_ids"], "low_pressure_tail")
    avoided_routes = project(
        window["high_pressure_event_ids"], "high_pressure_tail"
    )
    long_ids = {row["security_identity_sha256"] for row in long_routes}
    avoided_ids = {row["security_identity_sha256"] for row in avoided_routes}
    if long_ids & avoided_ids:
        raise _refuse("long and avoided original tails overlap")
    return long_routes, avoided_routes


def _scenario_for_window(
    *,
    settlement_date: str,
    lookback: int,
    release: dict[str, Any],
    successor: dict[str, Any],
    price_pairs: list[dict[str, Any]],
    long_routes: list[dict[str, Any]],
    avoided_routes: list[dict[str, Any]],
) -> _SyntheticScenario:
    by_identity = {
        row["security_identity_sha256"]: row for row in price_pairs
    }
    long_identities = tuple(
        sorted(row["security_identity_sha256"] for row in long_routes)
    )
    avoided_identities = tuple(
        sorted(row["security_identity_sha256"] for row in avoided_routes)
    )
    if not long_identities or not avoided_identities:
        raise _refuse("an executable window requires nonempty original tails")
    events = []
    for identity in (*long_identities, *avoided_identities):
        pair = by_identity[identity]
        events.extend(
            (
                _SyntheticEvent(
                    event_id=pair["entry_price_event_id"],
                    security_identity_sha256=identity,
                    at=release["decision_at"],
                    kind=_SyntheticEventKind.OPEN,
                    raw_open_usd=pair["entry_raw_open_usd"],
                ),
                _SyntheticEvent(
                    event_id=pair["exit_price_event_id"],
                    security_identity_sha256=identity,
                    at=successor["decision_at"],
                    kind=_SyntheticEventKind.OPEN,
                    raw_open_usd=pair["exit_raw_open_usd"],
                ),
            )
        )
    return _SyntheticScenario(
        scenario_id=(
            f"{SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID}:"
            f"{settlement_date}:{lookback}"
        ),
        decision_at=_INSTRUCTION_AT,
        entry_open_at=release["decision_at"],
        exit_open_at=successor["decision_at"],
        initial_cash_usd=_INITIAL_CASH_USD,
        long_security_identity_sha256s=long_identities,
        avoided_security_identity_sha256s=avoided_identities,
        events=tuple(events),
    )


def _source_refusal_reasons(window: dict[str, Any]) -> list[str]:
    reasons = set(window["source_ranking"]["underfill_reasons"])
    for member in window["source_ranking"]["excluded_members"]:
        reasons.update(member["reasons"])
    return sorted(reasons)


def _window_payload(
    *,
    release: dict[str, Any],
    successor: dict[str, Any] | None,
    window: dict[str, Any],
    price_pairs: list[dict[str, Any]] | None,
    entry_witness: dict[str, Any] | None,
) -> dict[str, Any]:
    source_ranking = window["source_ranking"]
    lookback = window["lookback_sessions"]
    source_reasons = _source_refusal_reasons(window)
    long_routes, avoided_routes = _tail_routes(window, price_pairs)
    if not release["cohort_comparable"]:
        status = "cohort_refused"
        reasons = sorted(set(release["no_comparison_reasons"] + source_reasons))
        scenario = None
        cost_runs: list[dict[str, Any]] = []
    elif successor is None:
        status = "no_successor_release"
        reasons = ["no_authenticated_successor_release"]
        scenario = None
        cost_runs = []
    else:
        if price_pairs is None or entry_witness is None:
            raise _refuse("executable release lacks price or entry-fact evidence")
        status = "executed"
        reasons = []
        scenario = _scenario_for_window(
            settlement_date=release["settlement_date"],
            lookback=lookback,
            release=release,
            successor=successor,
            price_pairs=price_pairs,
            long_routes=long_routes,
            avoided_routes=avoided_routes,
        )
        cost_runs = [
            _run_synthetic_order_kernel(scenario, cost_bps=cost)
            for cost in _COSTS_BPS
        ]
        if any(run["complete"] is not True for run in cost_runs):
            raise _refuse("built-in ranked-order kernel run did not complete")
        long_identities = {
            row["security_identity_sha256"] for row in long_routes
        }
        for run in cost_runs:
            ordered = {
                row["security_identity_sha256"] for row in run["orders"]
            }
            if ordered != long_identities or any(
                row["security_identity_sha256"]
                in {
                    item["security_identity_sha256"] for item in avoided_routes
                }
                for row in run["orders"]
            ):
                raise _refuse("kernel orders differ from original long-only tail routing")
    payload = {
        "lookback_sessions": lookback,
        "source_ranking_sha256": source_ranking["ranking_sha256"],
        "source_binding_cohort_sha256": source_ranking[
            "source_binding_cohort_sha256"
        ],
        "source_underfill_reasons": list(source_ranking["underfill_reasons"]),
        "source_refusal_reasons": source_reasons,
        "routing_status": status,
        "executable": status == "executed",
        "refusal_reasons": reasons,
        "common_security_identity_sha256s": list(
            release["common_security_identity_sha256s"]
        ),
        "long_routes": long_routes,
        "avoided_routes": avoided_routes,
        "instruction_at": None if scenario is None else _INSTRUCTION_AT,
        "entry_open_at": release["decision_at"],
        "exit_open_at": None if successor is None else successor["decision_at"],
        "successor_settlement_date": (
            None if successor is None else successor["settlement_date"]
        ),
        "entry_fact_witness_sha256": (
            None
            if entry_witness is None
            else entry_witness["entry_fact_witness_sha256"]
        ),
        "price_pair_fixture_sha256": (
            None if price_pairs is None else hash_payload(price_pairs)
        ),
        "scenario_sha256": (
            None if scenario is None else hash_payload(_scenario_payload(scenario))
        ),
        "cost_runs": cost_runs,
    }
    payload["route_sha256"] = hash_payload(payload)
    return payload


def _routing_payload(
    sources: _FixtureSources,
    cohort: dict[str, Any],
) -> dict[str, Any]:
    releases = cohort["releases"]
    if len(releases) != 3:
        raise _refuse("fixed bridge requires exactly three authenticated releases")
    projected = []
    for index, release in enumerate(releases):
        successor = releases[index + 1] if index + 1 < len(releases) else None
        executable = release["cohort_comparable"] is True and successor is not None
        price_pairs = _price_pairs(release, successor) if executable else None
        entry_witness = (
            _entry_fact_witness(
                sources,
                settlement_date=release["settlement_date"],
                entry_open_at=release["decision_at"],
            )
            if executable
            else None
        )
        windows = [
            _window_payload(
                release=release,
                successor=successor,
                window=window,
                price_pairs=price_pairs,
                entry_witness=entry_witness,
            )
            for window in release["lookbacks"]
        ]
        if [row["lookback_sessions"] for row in windows] != list(_LOOKBACKS):
            raise _refuse("release windows differ from the frozen lookback grid")
        release_payload = {
            "settlement_date": release["settlement_date"],
            "decision_at": release["decision_at"],
            "release_sha256": release["release_sha256"],
            "release_manifest_sha256": release["release_manifest_sha256"],
            "cohort_comparable": release["cohort_comparable"],
            "executable": executable,
            "refusal_reasons": (
                []
                if executable
                else sorted(
                    set(
                        [
                            reason
                            for window in windows
                            for reason in window["refusal_reasons"]
                        ]
                    )
                )
            ),
            "common_security_identity_sha256s": list(
                release["common_security_identity_sha256s"]
            ),
            "entry_fact_witness": entry_witness,
            "price_pairs": [] if price_pairs is None else price_pairs,
            "price_pair_fixture_sha256": (
                None if price_pairs is None else hash_payload(price_pairs)
            ),
            "windows": windows,
        }
        release_payload["release_routing_sha256"] = hash_payload(release_payload)
        projected.append(release_payload)
    if [row["executable"] for row in projected] != [False, True, False]:
        raise _refuse("fixed releases must be warm-up, executable, then no-successor")
    return {
        "routing_rule": (
            "original_low_pressure_tail_to_long_original_high_pressure_tail_"
            "to_avoidance_stable_identity_only"
        ),
        "release_count": len(projected),
        "releases": projected,
    }


def _build_unpinned_public_payload() -> dict[str, Any]:
    """Compose canonical bytes; the sole public caller enforces every pin."""

    bridge_policy = _bridge_policy_payload()
    recipe = _fixture_recipe_payload()
    sources = _build_fixture_sources()
    source_hashes = _source_identities(sources)
    evidence = build_stock_investability(
        sources.vintage, sources.references, sources.history
    )
    population = build_stock_eligible_population_inventory(evidence)
    binding = build_stock_population_binding_inventory(population)
    ranking = build_stock_eligible_ranking_inventory(binding)
    ranking_payload = ranking.to_payload()
    cohort = build_si5_stock_cohort_manifest(ranking)
    cohort_payload = cohort.to_payload()
    routing = _routing_payload(sources, cohort_payload)
    routing_sha256 = hash_payload(routing)
    payload = {
        "schema": SI5_SYNTHETIC_RANKED_ORDER_VERSION,
        "scenario_id": SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID,
        "fixture_recipe_sha256": hash_payload(recipe),
        **source_hashes,
        "population_inventory_sha256": ranking_payload[
            "source_population_sha256"
        ],
        "binding_inventory_sha256": ranking_payload["source_binding_sha256"],
        "ranking_inventory_sha256": ranking_payload["inventory_sha256"],
        "cohort_manifest_sha256": cohort_payload["manifest_sha256"],
        "routing_sha256": routing_sha256,
        "bridge_policy_sha256": hash_payload(bridge_policy),
        "demonstration_policy_sha256": SI5_SYNTHETIC_POLICY_SHA256,
        "si5_offline_protocol_sha256": SI5_OFFLINE_PROTOCOL_SHA256,
        "release_count": routing["release_count"],
        "releases": routing["releases"],
        "synthetic_typed_ranking_to_orders_rehearsed": True,
        "hypothetical_timing_only_not_production_latency": True,
        **_zero_authority_payload(),
    }
    payload["result_sha256"] = hash_payload(payload)
    return payload


def _public_payload() -> dict[str, Any]:
    _require_bridge_policy()
    if hash_payload(_fixture_recipe_payload()) != (
        SI5_SYNTHETIC_RANKED_ORDER_RECIPE_SHA256
    ):
        raise _refuse("fixed fixture recipe differs from its pinned digest")
    payload = _build_unpinned_public_payload()
    expected = {
        "source_vintage_sha256": _EXPECTED_SOURCE_VINTAGE_SHA256,
        "reference_bundle_sha256": _EXPECTED_REFERENCE_BUNDLE_SHA256,
        "market_history_sha256": _EXPECTED_MARKET_HISTORY_SHA256,
        "population_inventory_sha256": _EXPECTED_POPULATION_INVENTORY_SHA256,
        "binding_inventory_sha256": _EXPECTED_BINDING_INVENTORY_SHA256,
        "ranking_inventory_sha256": _EXPECTED_RANKING_INVENTORY_SHA256,
        "cohort_manifest_sha256": _EXPECTED_COHORT_MANIFEST_SHA256,
        "routing_sha256": _EXPECTED_ROUTING_SHA256,
        "result_sha256": SI5_SYNTHETIC_RANKED_ORDER_RESULT_SHA256,
    }
    for name, expected_value in expected.items():
        if type(expected_value) is not str or payload[name] != expected_value:
            raise _refuse(f"built-in {name} differs from its pinned digest")
    _validate_public_payload(payload)
    return payload


def _validate_public_payload(payload: dict[str, Any]) -> None:
    if type(payload) is not dict:
        raise _refuse("result payload must be an exact dictionary")
    if payload.get("scenario_id") != SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID:
        raise _refuse("result scenario identity changed")
    if payload.get("result_sha256") != SI5_SYNTHETIC_RANKED_ORDER_RESULT_SHA256:
        raise _refuse("result differs from its pinned identity")
    if hash_payload(
        {key: value for key, value in payload.items() if key != "result_sha256"}
    ) != payload["result_sha256"]:
        raise _refuse("result hash is invalid")
    for name, expected in _zero_authority_payload().items():
        if type(payload.get(name)) is not type(expected) or payload[name] != expected:
            raise _refuse("result contains noncanonical or open authority")
    releases = payload.get("releases")
    if type(releases) is not list or len(releases) != 3:
        raise _refuse("result must retain exactly three releases")
    routing_body = {
        "routing_rule": (
            "original_low_pressure_tail_to_long_original_high_pressure_tail_"
            "to_avoidance_stable_identity_only"
        ),
        "release_count": len(releases),
        "releases": releases,
    }
    if hash_payload(routing_body) != payload.get("routing_sha256"):
        raise _refuse("routing hash is invalid")
    for release in releases:
        if hash_payload(
            {
                key: value
                for key, value in release.items()
                if key != "release_routing_sha256"
            }
        ) != release.get("release_routing_sha256"):
            raise _refuse("release routing hash is invalid")
        windows = release.get("windows")
        if type(windows) is not list or [
            row.get("lookback_sessions") for row in windows
        ] != list(_LOOKBACKS):
            raise _refuse("release windows differ from the frozen grid")
        for window in windows:
            if hash_payload(
                {
                    key: value
                    for key, value in window.items()
                    if key != "route_sha256"
                }
            ) != window.get("route_sha256"):
                raise _refuse("window route hash is invalid")
            runs = window.get("cost_runs")
            if window.get("executable") is True:
                if type(runs) is not list or [
                    row.get("cost_bps_per_side") for row in runs
                ] != list(_COSTS_BPS):
                    raise _refuse("executable window lost a frozen cost run")
            elif runs != []:
                raise _refuse("refused window cannot retain a partial cost run")
            for run in runs:
                if run.get("complete") is not True or hash_payload(
                    {
                        key: value
                        for key, value in run.items()
                        if key != "kernel_result_sha256"
                    }
                ) != run.get("kernel_result_sha256"):
                    raise _refuse("kernel result hash is invalid")


_RESULT_AUTHORITY = object()


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class SI5SyntheticRankedOrderResult:
    """Detached authenticated receipt for the sole built-in bridge run."""

    _payload_json: str = dataclasses.field(repr=False)
    _payload_sha256: str = dataclasses.field(repr=False)
    _authority: object = dataclasses.field(repr=False, compare=False)

    def to_payload(self) -> dict[str, Any]:
        if (
            type(self) is not SI5SyntheticRankedOrderResult
            or getattr(self, "_authority", None) is not _RESULT_AUTHORITY
        ):
            raise _refuse("result is not an authenticated built-in run")
        if type(self._payload_json) is not str:
            raise _refuse("stored result payload is invalid")
        try:
            payload = json.loads(self._payload_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise _refuse("stored result payload is invalid") from exc
        if (
            type(payload) is not dict
            or canonical_json(payload) != self._payload_json
            or type(self._payload_sha256) is not str
            or payload.get("result_sha256") != self._payload_sha256
        ):
            raise _refuse("stored result is not canonical")
        _validate_public_payload(payload)
        return deepcopy(payload)

    @property
    def sha256(self) -> str:
        return SI5SyntheticRankedOrderResult.to_payload(self)["result_sha256"]


def _result_from_payload(payload: dict[str, Any]) -> SI5SyntheticRankedOrderResult:
    value = object.__new__(SI5SyntheticRankedOrderResult)
    object.__setattr__(value, "_payload_json", canonical_json(payload))
    object.__setattr__(value, "_payload_sha256", payload["result_sha256"])
    object.__setattr__(value, "_authority", _RESULT_AUTHORITY)
    return value


def run_si5_synthetic_ranked_order_scenario(
    scenario_id: str = SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID,
) -> SI5SyntheticRankedOrderResult:
    """Run the pinned typed synthetic bridge; external rows are unavailable."""

    if (
        type(scenario_id) is not str
        or scenario_id != SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID
    ):
        raise _refuse("only the pinned built-in synthetic scenario is available")
    try:
        return _result_from_payload(_public_payload())
    except SI5SyntheticRankedOrderError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise _refuse(f"built-in synthetic ranked-order bridge failed: {exc}") from exc
