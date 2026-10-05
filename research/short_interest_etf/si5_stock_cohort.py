"""Synthetic-only SI-5 stock comparison cohorts without any return or look.

Each candidate keeps its *full*, authenticated release-next-open eligible S1
ranking. The common stable-security/event intersection is a separate view for
prospective candidate comparison; rows are never reranked on that view.
"""
from __future__ import annotations

import dataclasses
from copy import deepcopy
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    SI5OfflineProtocol,
    require_si5_offline_protocol,
)
from research.short_interest_etf.stock_eligible_ranking import (
    StockEligibleRankingInventory,
)


SI5_STOCK_COHORT_VERSION = "si5-stock-cohort-synthetic-v1"
_LOOKBACKS = (20, 60, 120, 252)
_MINIMUM_FULL_COHORT = 10


class SI5StockCohortError(ValueError):
    """An authentic, release-open synthetic comparison was not established."""


def _refuse(detail: str) -> SI5StockCohortError:
    return SI5StockCohortError(f"REFUSED: {detail}")


def _capture_source(
    source: StockEligibleRankingInventory,
) -> tuple[StockEligibleRankingInventory, dict[str, Any]]:
    if type(source) is not StockEligibleRankingInventory:
        raise _refuse("source must be the exact StockEligibleRankingInventory type")
    # Validate the defensive copy, not a potentially changing caller alias.
    # Upstream to_payload fully reauthenticates and rebuilds the ranking;
    # every later public read repeats that check against the captured hash.
    captured = deepcopy(source)
    return captured, StockEligibleRankingInventory.to_payload(captured)


def _index_source(
    ranking: dict[str, Any], binding: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, int], dict[str, Any]],
           dict[tuple[str, int], dict[str, Any]]]:
    summaries = {row["settlement_date"]: row for row in binding["normalization_cohorts"]}
    if len(summaries) != len(binding["normalization_cohorts"]):
        raise _refuse("duplicate normalization release")
    expected = {(settlement, lookback) for settlement in summaries for lookback in _LOOKBACKS}
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for row in ranking["rankings"]:
        key = row["settlement_date"], row["lookback_sessions"]
        if key in by_key:
            raise _refuse("duplicate release/lookback ranking")
        by_key[key] = row
    if set(by_key) != expected:
        raise _refuse("missing or unexpected release/lookback ranking")
    same_open: dict[tuple[str, int], dict[str, Any]] = {}
    for row in binding["bindings"]:
        if row["cutoff_relation"] != "same_open":
            continue
        key = row["settlement_date"], row["lookback_sessions"]
        if key in same_open:
            raise _refuse("duplicate release-open source binding")
        same_open[key] = row
    if not set(same_open) <= expected:
        raise _refuse("unexpected release-open source binding")
    return summaries, by_key, same_open


def _window_identity_map(
    row: dict[str, Any], binding: dict[str, Any] | None,
    summary: dict[str, Any],
) -> dict[str, dict[str, str]]:
    if (
        row["decision_at"] != summary["decision_at"]
        or row["normalization_cohort_sha256"] != summary["normalization_cohort_sha256"]
        or row["source_binding_cohort_sha256"] != (
            None if binding is None else binding["binding_sha256"]
        )
        or row["release_open_evidence_available"] is not (binding is not None)
    ):
        raise _refuse("candidate ranking differs from its canonical release open")
    members = {} if binding is None else {member["event_id"]: member for member in binding["members"]}
    if binding is not None and len(members) != len(binding["members"]):
        raise _refuse("duplicate event in source binding")
    if len(set(row["ranked_event_ids"])) != len(row["ranked_event_ids"]):
        raise _refuse("duplicate ranked event")
    by_identity: dict[str, dict[str, str]] = {}
    for event in row["ranked_event_ids"]:
        member = members.get(event)
        if member is None:
            raise _refuse("ranked event lacks release-open stable identity")
        identity = member["security_identity_sha256"]
        if type(identity) is not str or not identity:
            raise _refuse("ranked event lacks stable security identity")
        if identity in by_identity:
            raise _refuse("duplicate stable identity in candidate ranking")
        by_identity[identity] = {
            "event_id": event,
            "security_id": member["security_id"],
        }
    return by_identity


def _comparison_rows(
    ranking: dict[str, Any], identities: dict[str, dict[str, str]],
    common: list[str],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    role_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in ranking["rows"]:
        key = row["event_id"], row["role"]
        if key in role_rows:
            raise _refuse("duplicate ranking role row")
        role_rows[key] = row
    rows = []
    high, low = [], []
    for identity in common:
        event = identities[identity]["event_id"]
        pressure = role_rows.get((event, "pressure"))
        covering = role_rows.get((event, "covering"))
        if pressure is None or covering is None:
            raise _refuse("common event lacks original pressure/covering ranks")
        if pressure["security_id"] != identities[identity]["security_id"] or (
            covering["security_id"] != identities[identity]["security_id"]
        ):
            raise _refuse("common rank differs from stable security mapping")
        high_tail = pressure["threshold_candidate"]
        low_tail = covering["threshold_candidate"]
        if high_tail is True and low_tail is True:
            raise _refuse("complementary pressure tails overlap")
        if high_tail is True:
            high.append(event)
        if low_tail is True:
            low.append(event)
        rows.append({
            "security_identity_sha256": identity,
            "security_id": identities[identity]["security_id"],
            "event_id": event,
            "pressure_row_sha256": pressure["ranking_row_sha256"],
            "covering_row_sha256": covering["ranking_row_sha256"],
            "pressure_percentile": pressure["role_percentile"],
            "covering_percentile": covering["role_percentile"],
            "high_pressure_tail": high_tail,
            "low_pressure_tail": low_tail,
        })
    return rows, sorted(high), sorted(low)


def _project_releases(
    ranking: dict[str, Any], binding: dict[str, Any],
    calendar_settlements: tuple[str, ...],
) -> list[dict[str, Any]]:
    summaries, by_key, same_open = _index_source(ranking, binding)
    if len(calendar_settlements) != len(set(calendar_settlements)) or (
        set(calendar_settlements) != set(summaries)
    ):
        raise _refuse("authenticated release calendar has a missing or duplicate cohort")
    releases = []
    for settlement, summary in sorted(summaries.items()):
        identities_by_lookback: dict[int, dict[str, dict[str, str]]] = {}
        event_identity: dict[str, str] = {}
        identity_event: dict[str, str] = {}
        for lookback in _LOOKBACKS:
            key = settlement, lookback
            identities = _window_identity_map(by_key[key], same_open.get(key), summary)
            identities_by_lookback[lookback] = identities
            for identity, item in identities.items():
                event = item["event_id"]
                if event in event_identity and event_identity[event] != identity:
                    raise _refuse("event identity drifts across candidate windows")
                if identity in identity_event and identity_event[identity] != event:
                    raise _refuse("stable security maps to different release events")
                event_identity[event] = identity
                identity_event[identity] = event
        common = sorted(set.intersection(*(set(items) for items in identities_by_lookback.values())))
        reasons = []
        if not common:
            reasons.append("empty_common_intersection")
        if len(common) < _MINIMUM_FULL_COHORT:
            reasons.append("underfilled_common_intersection")
        lookbacks = []
        for lookback in _LOOKBACKS:
            source = by_key[settlement, lookback]
            identities = identities_by_lookback[lookback]
            comparisons, high, low = _comparison_rows(source, identities, common)
            if not source["release_open_evidence_available"]:
                reasons.append("missing_release_open_evidence")
            if source["underfill_reasons"] or len(identities) < _MINIMUM_FULL_COHORT:
                reasons.append("underfilled_full_cohort")
            if not high:
                reasons.append("missing_common_high_pressure_tail")
            if not low:
                reasons.append("missing_common_low_pressure_tail")
            lookbacks.append({
                "lookback_sessions": lookback,
                "source_ranking": source,
                "ranked_security_identity_sha256s": sorted(identities),
                "comparison_rows": comparisons,
                "high_pressure_event_ids": high,
                "low_pressure_event_ids": low,
            })
        release = {
            "settlement_date": settlement,
            "release_sha256": summary["release_sha256"],
            "decision_at": summary["decision_at"],
            "common_security_identity_sha256s": common,
            "common_event_ids": sorted(identity_event[identity] for identity in common),
            "lookbacks": lookbacks,
            "cohort_comparable": not reasons,
            "no_comparison_reasons": sorted(set(reasons)),
        }
        release["release_manifest_sha256"] = hash_payload(release)
        releases.append(release)
    return releases


@dataclasses.dataclass(frozen=True, slots=True)
class SI5StockCohortManifest:
    ranking: StockEligibleRankingInventory
    protocol: SI5OfflineProtocol = SI5_OFFLINE_PROTOCOL
    _source_ranking_sha256: str = dataclasses.field(init=False, repr=False)
    _protocol_sha256: str = dataclasses.field(init=False, repr=False)
    _frozen_payload: dict[str, Any] = dataclasses.field(init=False, repr=False)
    _frozen_payload_sha256: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self) is not SI5StockCohortManifest:
            raise _refuse("manifest must be the exact SI5StockCohortManifest type")
        try:
            protocol_sha256 = require_si5_offline_protocol(self.protocol)
            captured, source = _capture_source(self.ranking)
            binding = captured.binding.to_payload()
            if source["source_binding_sha256"] != binding["inventory_sha256"]:
                raise _refuse("ranking no longer matches source binding")
            vintage = captured.binding.population.evidence.vintage
            calendar_settlements = tuple(
                release.settlement_date for release in vintage.release_calendar
                if vintage.manifest.settlement_start <= release.settlement_date
                <= vintage.manifest.settlement_end
            )
            releases = _project_releases(source, binding, calendar_settlements)
            payload = {
                "schema": SI5_STOCK_COHORT_VERSION,
                "source_ranking_sha256": source["inventory_sha256"],
                "source_binding_sha256": binding["inventory_sha256"],
                "si5_protocol_sha256": protocol_sha256,
                "comparison_rule": "common_stable_security_event_per_release_preserve_full_ranks",
                "calendar_settlements": list(calendar_settlements),
                "releases": releases,
                "selected_lookback": None,
                "source_rights_verified": False,
                "actual_pit_coverage_verified": False,
                "outcome_authorized": False,
                "qc_backtest_authorized": False,
                "production_authoritative": False,
                "trading_authority": False,
            }
            payload["manifest_sha256"] = hash_payload(payload)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise _refuse(f"invalid cohort source: {exc}") from exc
        object.__setattr__(self, "ranking", captured)
        object.__setattr__(self, "_source_ranking_sha256", source["inventory_sha256"])
        object.__setattr__(self, "_protocol_sha256", protocol_sha256)
        object.__setattr__(self, "_frozen_payload", payload)
        object.__setattr__(self, "_frozen_payload_sha256", payload["manifest_sha256"])

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not SI5StockCohortManifest:
            raise _refuse("manifest must be the exact SI5StockCohortManifest type")
        try:
            protocol_sha256 = require_si5_offline_protocol(self.protocol)
            source = StockEligibleRankingInventory.to_payload(self.ranking)
            if source["inventory_sha256"] != self._source_ranking_sha256 or (
                protocol_sha256 != self._protocol_sha256
            ):
                raise _refuse("captured ranking or protocol identity changed")
            if source["source_binding_sha256"] != self._frozen_payload["source_binding_sha256"]:
                raise _refuse("captured binding identity changed")
            frozen = self._frozen_payload
            if hash_payload({key: value for key, value in frozen.items() if key != "manifest_sha256"}) != (
                self._frozen_payload_sha256
            ) or frozen["manifest_sha256"] != self._frozen_payload_sha256:
                raise _refuse("captured manifest payload changed")
            return deepcopy(frozen)
        except SI5StockCohortError:
            raise
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise _refuse(f"invalid cohort projection: {exc}") from exc

    @property
    def sha256(self) -> str:
        return SI5StockCohortManifest.to_payload(self)["manifest_sha256"]


def build_si5_stock_cohort_manifest(
    ranking: StockEligibleRankingInventory,
    protocol: SI5OfflineProtocol = SI5_OFFLINE_PROTOCOL,
) -> SI5StockCohortManifest:
    return SI5StockCohortManifest(ranking, protocol)
