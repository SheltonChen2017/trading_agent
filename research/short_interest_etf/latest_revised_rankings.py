"""Separate file-fed, latest-revised exploratory S1 rankings.

Calendar dates define hypothetical replay cutoffs, not observed historical
availability. Structural normalization precedes every investability filter;
intersection never changes an original candidate's order statistics or tails.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import timedelta
from fractions import Fraction
from typing import Any

from data.exchange_calendar import (
    SUPPORTED_SESSION_START,
    parse_session_date,
    trading_sessions,
)
from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.latest_revised_protocol import (
    EPOCH_ID,
    LOOKBACKS,
    PROTOCOL_SHA256,
    protocol_payload,
)
from research.short_interest_etf.latest_revised_source import LatestRevisedBundle
from research.short_interest_etf.stock_normalization import _type7_quantile


SCHEMA = "si-latest-revised-rankings-v1"
_MAD_SCALE = Fraction(7413, 5000)
_MINIMUM_SECTOR_PEERS = 20
_MINIMUM_TAIL_POPULATION = 10


def _authority() -> dict[str, bool]:
    return {
        "point_in_time_data": False,
        "source_admitted": False,
        "confirmatory_eligible": False,
        "outcome_access_authorized": False,
        "qc_backtest_authorized": False,
        "production_authoritative": False,
        "trading_authority": False,
        "latest_revised": True,
    }


class LatestRevisedRankingError(ValueError):
    """The separate exploratory ranking contract could not be authenticated."""


def _refuse(detail: str) -> LatestRevisedRankingError:
    return LatestRevisedRankingError(f"REFUSED: {detail}")


def _rational(value: Fraction | None) -> dict[str, int] | None:
    return None if value is None else {
        "numerator": value.numerator, "denominator": value.denominator,
    }


def _fraction(value: dict[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def _median(values: tuple[Fraction, ...]) -> Fraction:
    return _type7_quantile(values, Fraction(1, 2))


def _valid_on(row: dict[str, Any], session: str) -> bool:
    return row["effective_from"] <= session and (
        row["effective_to"] is None or session <= row["effective_to"]
    )


def _reference(
    references: list[dict[str, Any]], ticker: str, settlement: str, entry: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    dated = [row for row in references if row["ticker"] == ticker
             and _valid_on(row, settlement)
             and row["observation_session"] <= settlement]
    visible = [row for row in dated if row["available_date"] < entry]
    if not visible:
        return None, ["late_dated_reference" if dated else "missing_dated_reference"]
    latest = max((row["observation_session"], row["available_date"]) for row in visible)
    winners = [row for row in visible
               if (row["observation_session"], row["available_date"]) == latest]
    if len(winners) != 1:
        return None, ["ambiguous_dated_reference"]
    return winners[0], []


def _structural_rows(
    source: dict[str, Any], release: dict[str, Any], previous: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    settlement, entry = release["settlement_date"], release["entry_session"]
    current = [row for row in source["observations"] if row["settlement_date"] == settlement]
    prior_by_security: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    if previous is not None:
        prior_settlement = previous["settlement_date"]
        for observation in source["observations"]:
            if observation["settlement_date"] != prior_settlement:
                continue
            reference, reasons = _reference(
                source["references"], observation["ticker"], prior_settlement, entry,
            )
            if not reasons:
                prior_by_security.setdefault(reference["security_id"], []).append(
                    (observation, reference)
                )
    rows: list[dict[str, Any]] = []
    identities: set[str] = set()
    for observation in sorted(current, key=lambda row: row["ticker"]):
        reference, reasons = _reference(
            source["references"], observation["ticker"], settlement, entry,
        )
        security = None if reference is None else reference["security_id"]
        if security is not None:
            if security in identities:
                raise _refuse("duplicate same-share-class observations in a release")
            identities.add(security)
        if previous is None:
            reasons.append("missing_previous_calendar_release")
        if reference is not None:
            if reference["country"] != "US":
                reasons.append("outside_us_structural_population")
            if reference["security_type"] != "COMMON_STOCK":
                reasons.append("outside_common_stock_structural_population")
        prior = prior_by_security.get(security, [])
        if previous is not None and not prior:
            reasons.append("missing_same_security_immediate_previous_short_interest")
        elif len(prior) > 1:
            reasons.append("ambiguous_same_security_immediate_previous_short_interest")
        prior_observation, prior_reference = prior[0] if len(prior) == 1 else (None, None)
        delta = None
        if not reasons:
            delta = (
                Fraction(observation["short_interest"], reference["shares_outstanding"])
                - Fraction(prior_observation["short_interest"], prior_reference["shares_outstanding"])
            )
        rows.append({
            "security_id": security,
            "ticker": observation["ticker"],
            "sector": None if reference is None else reference["sector"],
            "taxonomy_id": None if reference is None else reference["taxonomy_id"],
            "current_short_interest": observation["short_interest"],
            "current_shares_outstanding": None if reference is None else reference["shares_outstanding"],
            "prior_short_interest": None if prior_observation is None else prior_observation["short_interest"],
            "prior_shares_outstanding": None if prior_reference is None else prior_reference["shares_outstanding"],
            "current_observation_sha256": observation["raw_record_sha256"],
            "current_reference_sha256": None if reference is None else reference["raw_record_sha256"],
            "prior_observation_sha256": None if prior_observation is None else prior_observation["raw_record_sha256"],
            "prior_reference_sha256": None if prior_reference is None else prior_reference["raw_record_sha256"],
            "raw_s1_delta": _rational(delta),
            "sector_peer_count": 0,
            "winsor_lower": None,
            "winsor_upper": None,
            "winsorized_value": None,
            "sector_median": None,
            "sector_mad": None,
            "scaled_mad": None,
            "score": None,
            "refusal_reasons": sorted(set(reasons)),
        })
    # The canonical structural policy admits one taxonomy lineage per release.
    # Separating sector buckets by taxonomy cannot authorize a pooled global
    # quantile, even if a later investability filter removes one taxonomy.
    lineages = {row["taxonomy_id"] for row in rows if not row["refusal_reasons"]}
    if len(lineages) > 1:
        for row in rows:
            row["refusal_reasons"] = sorted(set(row["refusal_reasons"] + ["mixed_taxonomy_lineage"]))
        return rows
    sectors: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if not row["refusal_reasons"]:
            sectors.setdefault((row["taxonomy_id"], row["sector"]), []).append(row)
    full_population = [row for sector in sectors.values()
                       if len(sector) >= _MINIMUM_SECTOR_PEERS for row in sector]
    bounds = None if not full_population else (
        _type7_quantile(tuple(_fraction(row["raw_s1_delta"]) for row in full_population), Fraction(1, 100)),
        _type7_quantile(tuple(_fraction(row["raw_s1_delta"]) for row in full_population), Fraction(99, 100)),
    )
    for sector in sectors.values():
        for row in sector:
            row["sector_peer_count"] = len(sector)
        if len(sector) < _MINIMUM_SECTOR_PEERS:
            for row in sector:
                row["refusal_reasons"] = ["insufficient_sector_peers"]
            continue
        lower, upper = bounds
        values = tuple(max(lower, min(upper, _fraction(row["raw_s1_delta"]))) for row in sector)
        median = _median(values)
        mad = _median(tuple(abs(value - median) for value in values))
        scaled = mad * _MAD_SCALE
        for row, value in zip(sector, values, strict=True):
            row.update({
                "winsor_lower": _rational(lower), "winsor_upper": _rational(upper),
                "winsorized_value": _rational(value), "sector_median": _rational(median),
                "sector_mad": _rational(mad), "scaled_mad": _rational(scaled),
                "score": None if mad == 0 else _rational((value - median) / scaled),
                "refusal_reasons": ["zero_sector_mad"] if mad == 0 else [],
            })
    return rows


def _completed_sessions(entry: str) -> tuple[str, ...]:
    cutoff = parse_session_date(entry)
    end = cutoff - timedelta(days=1)
    if end < SUPPORTED_SESSION_START:
        return ()
    start = max(SUPPORTED_SESSION_START, cutoff - timedelta(days=800))
    return tuple(session.isoformat() for session in trading_sessions(start, end)[-max(LOOKBACKS):])


def _eligibility(
    source: dict[str, Any], structural: dict[str, Any], entry: str,
    sessions: tuple[str, ...], lookback: int,
    bars: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    security = structural["security_id"]
    window = sessions[-lookback:]
    last = sessions[-1] if sessions else None
    reasons: list[str] = []
    if security is None:
        reasons.append("missing_security_mapping")
    if len(window) != lookback:
        reasons.append("insufficient_calendar_history")
    cap_rows = [row for row in source["references"] if row["security_id"] == security
                and row["observation_session"] == last and _valid_on(row, last)]
    visible_caps = [row for row in cap_rows if row["available_date"] < entry]
    cap = None
    if not visible_caps:
        reasons.append("market_cap_late" if cap_rows else "market_cap_missing_last_completed_session")
    else:
        latest = max(row["available_date"] for row in visible_caps)
        winners = [row for row in visible_caps if row["available_date"] == latest]
        if len(winners) != 1:
            reasons.append("market_cap_ambiguous")
        else:
            cap = winners[0]
            if Fraction(cap["market_cap"]) < 300_000_000:
                reasons.append("below_market_cap_floor")
    values: list[Fraction] = []
    missing: list[str] = []
    for session in window:
        bar = bars.get((security, session))
        if bar is None:
            missing.append(session)
        else:
            values.append(Fraction(bar["close"]) * bar["volume"])
    if missing:
        reasons.append("daily_history_missing_required_session")
    median = _median(tuple(values)) if len(values) == lookback else None
    if median is not None and median < 10_000_000:
        reasons.append("below_median_dollar_volume_floor")
    return {
        "security_id": security, "ticker": structural["ticker"],
        "lookback_sessions": lookback, "window_sessions": list(window),
        "window_start_session": window[0] if window else None,
        "window_end_session": last, "complete_session_count": len(values),
        "missing_sessions": missing, "median_dollar_volume": _rational(median),
        "market_cap": None if cap is None else cap["market_cap"],
        "market_cap_reference_sha256": None if cap is None else cap["raw_record_sha256"],
        "eligible": not reasons, "refusal_reasons": sorted(set(reasons)),
    }


def _rank_lookback(
    source: dict[str, Any], structural: list[dict[str, Any]], release: dict[str, Any],
    sessions: tuple[str, ...], lookback: int,
    bars: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    eligibility = [
        _eligibility(source, row, release["entry_session"], sessions, lookback, bars)
        for row in structural
    ]
    selected = [row for row, evidence in zip(structural, eligibility, strict=True)
                if evidence["eligible"] and row["score"] is not None]
    scores = {row["security_id"]: _fraction(row["score"]) for row in selected}
    total = len(scores)
    rows = []
    for row in selected:
        value = scores[row["security_id"]]
        lower = sum(score < value for score in scores.values())
        equal = sum(score == value for score in scores.values())
        pressure = Fraction(2 * lower + equal, 2 * total)
        covering = 1 - pressure
        rows.append({
            "security_id": row["security_id"], "ticker": row["ticker"],
            "score": row["score"], "covering_score": _rational(-value),
            "strictly_lower_count": lower, "equal_count": equal,
            "strictly_higher_count": total - lower - equal, "population_count": total,
            "pressure_percentile": _rational(pressure), "covering_percentile": _rational(covering),
            "high_tail": total >= _MINIMUM_TAIL_POPULATION and pressure >= Fraction(9, 10),
            "low_tail": total >= _MINIMUM_TAIL_POPULATION and covering >= Fraction(9, 10),
        })
    refusals = []
    for row, evidence in zip(structural, eligibility, strict=True):
        reasons = sorted(set(evidence["refusal_reasons"] + row["refusal_reasons"]))
        if reasons:
            refusals.append({"security_id": row["security_id"], "ticker": row["ticker"], "reasons": reasons})
    return {
        "lookback_sessions": lookback,
        "eligible_security_ids": sorted(row["security_id"] for row in eligibility if row["eligible"]),
        "ranked_security_ids": sorted(scores), "eligibility_rows": eligibility,
        "rows": sorted(rows, key=lambda row: row["security_id"]), "refusals": refusals,
        "original_high_tail_security_ids": sorted(row["security_id"] for row in rows if row["high_tail"]),
        "original_low_tail_security_ids": sorted(row["security_id"] for row in rows if row["low_tail"]),
        "refusal_reasons": ["insufficient_ranked_population_for_tails"] if total < _MINIMUM_TAIL_POPULATION else [],
    }


def _compute(source: dict[str, Any]) -> dict[str, Any]:
    if tuple(LOOKBACKS) != (20, 60, 120, 252):
        raise _refuse("protocol lookbacks differ from the frozen four candidates")
    if _MAD_SCALE != Fraction(7413, 5000) or _MINIMUM_SECTOR_PEERS != 20 or _MINIMUM_TAIL_POPULATION != 10:
        raise _refuse("normalization or rank population floor differs from the frozen protocol")
    protocol = protocol_payload()
    if hash_payload(protocol) != PROTOCOL_SHA256 or protocol["evidence_epoch"] != EPOCH_ID:
        raise _refuse("frozen exploratory protocol identity changed")
    bars = {(row["security_id"], row["session"]): row for row in source["bars"]}
    if len(bars) != len(source["bars"]):
        raise _refuse("ambiguous security/session raw history")
    releases = []
    calendar = source["releases"]
    for index, release in enumerate(calendar):
        previous = calendar[index - 1] if index else None
        successor = calendar[index + 1] if index + 1 < len(calendar) else None
        structural = _structural_rows(source, release, previous)
        sessions = _completed_sessions(release["entry_session"])
        lookbacks = [_rank_lookback(source, structural, release, sessions, lookback, bars)
                     for lookback in LOOKBACKS]
        common = set.intersection(*(set(row["ranked_security_ids"]) for row in lookbacks))
        # A common view may lose some original tail members, but it cannot
        # become a valid comparison with an absent role or a population below
        # the frozen floor. Never replenish either tail by reranking this view.
        comparison_reasons = ([] if len(common) >= _MINIMUM_TAIL_POPULATION
                              else ["underfilled_common_intersection"])
        for ranking in lookbacks:
            ranking["common_security_ids"] = sorted(common)
            for role in ("high", "low"):
                original = set(ranking[f"original_{role}_tail_security_ids"])
                ranking[f"{role}_tail_security_ids"] = sorted(original & common)
                ranking[f"lost_{role}_tail_security_ids"] = sorted(original - common)
                if original - common:
                    ranking["refusal_reasons"].append(f"original_{role}_tail_lost_at_common_intersection")
                if not ranking[f"{role}_tail_security_ids"]:
                    comparison_reasons.append(f"missing_common_{role}_pressure_tail")
            for row in ranking["rows"]:
                row["in_common"] = row["security_id"] in common
        reasons = list(comparison_reasons)
        if previous is None:
            reasons.append("missing_previous_calendar_release")
        if not structural:
            reasons.append("no_short_interest_observations_for_calendar_release")
        if not common:
            reasons.append("empty_four_lookback_common_population")
        if any("mixed_taxonomy_lineage" in row["refusal_reasons"] for row in structural):
            reasons.append("mixed_taxonomy_lineage")
        if successor is None:
            reasons.append("no_calendar_successor_for_new_entry")
        status = (
            "final_no_successor" if successor is None else "warmup" if previous is None
            else "empty" if not structural else "refused" if comparison_reasons else "ready"
        )
        releases.append({
            **release,
            "previous_settlement_date": None if previous is None else previous["settlement_date"],
            "next_settlement_date": None if successor is None else successor["settlement_date"],
            "next_entry_session": None if successor is None else successor["entry_session"],
            "next_entry_at": None if successor is None else successor["entry_at"],
            "last_completed_session": sessions[-1] if sessions else None,
            "status": status, "refusal_reasons": sorted(set(reasons)),
            "structural_rows": structural, "lookbacks": lookbacks,
            "common_security_ids": sorted(common),
        })
    result = {
        "schema": SCHEMA, "evidence_epoch": EPOCH_ID,
        "protocol_sha256": PROTOCOL_SHA256, "protocol": protocol,
        "source_bundle_sha256": source["bundle_sha256"],
        "authority": _authority(), "selected_lookback": None,
        "actual_outcome_access_authority": False, "look_accounting": "runner_managed",
        "releases": releases,
        "source_refusals": source["refusals"],
    }
    result["rankings_sha256"] = hash_payload(result)
    return result


@dataclasses.dataclass(frozen=True, slots=True)
class LatestRevisedRankings:
    bundle: LatestRevisedBundle
    _source_bundle_sha256: str = dataclasses.field(init=False, repr=False)
    _protocol_sha256: str = dataclasses.field(init=False, repr=False)
    _payload_json: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self) is not LatestRevisedRankings or type(self.bundle) is not LatestRevisedBundle:
            raise _refuse("ranking requires exact LatestRevisedRankings and LatestRevisedBundle types")
        original = LatestRevisedBundle.to_payload(self.bundle)
        captured = LatestRevisedBundle(self.bundle.payload_json)
        source = LatestRevisedBundle.to_payload(captured)
        if original != source:
            raise _refuse("source bundle changed during capture")
        object.__setattr__(self, "bundle", captured)
        object.__setattr__(self, "_source_bundle_sha256", source["bundle_sha256"])
        object.__setattr__(self, "_protocol_sha256", PROTOCOL_SHA256)
        object.__setattr__(self, "_payload_json", canonical_json(_compute(source)))

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not LatestRevisedRankings or type(self.bundle) is not LatestRevisedBundle:
            raise _refuse("ranking receipt types changed")
        source = LatestRevisedBundle.to_payload(self.bundle)
        if source["bundle_sha256"] != self._source_bundle_sha256 or self._protocol_sha256 != PROTOCOL_SHA256:
            raise _refuse("source bundle or protocol binding changed")
        recomputed = canonical_json(_compute(source))
        if recomputed != self._payload_json:
            raise _refuse("ranking receipt differs from its deterministic source or protocol")
        return json.loads(recomputed)

    @property
    def sha256(self) -> str:
        return LatestRevisedRankings.to_payload(self)["rankings_sha256"]


def rank_latest_revised_bundle(bundle: LatestRevisedBundle) -> LatestRevisedRankings:
    return LatestRevisedRankings(bundle)
