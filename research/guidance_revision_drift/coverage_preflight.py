"""Dated subscription metadata assessment, never market ingestion or authority.

Only the small known-product inventory is supported. No payloads, arbitrary
URLs, secrets, asserted approvals or positive readiness fields are accepted.
A retained hash binds bytes, not their authenticity. This new offline source
requires independent review; it is not the accepted 372-frame recovery epoch.
"""
from __future__ import annotations

from datetime import date
import re

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.contracts import (
    Candidate, CandidateError, _decode, load_candidate,
)
from research.guidance_revision_drift.readiness import preflight


class CoverageError(ValueError):
    """Invalid bounded metadata; messages never echo caller content."""


_SCHEMA = "gdr.coverage-metadata.v1"
_PRODUCTS = {
    "eodhd": frozenset({"eod_all_world", "eod_calendar"}),
    "fmp": frozenset({"starter"}),
    "massive": frozenset({"stocks_starter", "benzinga_analyst_ratings", "benzinga_analyst_insights"}),
    "sharadar": frozenset({"bundle_5y"}),
}
_NOMINAL_YEARS = {"eodhd": None, "fmp": 5, "massive": 5, "sharadar": 5}
_SOURCES = {
    "eod_calendar": "https://eodhd.com/financial-apis/calendar-upcoming-earnings-ipos-and-splits",
    "eod_snapshot": "https://eodhd.com/financial-apis/live-v2-for-us-stocks-extended-quotes-2025",
    "fmp_plans": "https://site.financialmodelingprep.com/datasets/market-data-historic",
    "fmp_guidance": "https://site.financialmodelingprep.com/insights/enterprise/earnings-data-apis-how-to-access-transcripts-guidance-and-actual",
    "massive_bars": "https://massive.com/docs/rest/stocks/aggregates/custom-bars",
    "massive_quotes": "https://massive.com/docs/rest/stocks/trades-quotes/quotes",
    "massive_ratings": "https://massive.com/docs/rest/partners/benzinga/analyst-ratings",
    "massive_insights": "https://massive.com/docs/rest/partners/benzinga/analyst-insights",
    "massive_guidance": "https://massive.com/docs/rest/partners/benzinga/corporate-guidance",
    "sharadar_bundle": "https://sharadar.com/bundle",
    "sharadar_history": "https://sharadar.com/blog/posts/upgrade-pause-resume",
}
_BLOCKERS = (
    "issuer_guidance_versions_unestablished",
    "comparable_predecessor_and_availability_unverified",
    "historical_stock_nbbo_unestablished",
    "historical_spy_nbbo_unestablished",
    "minute_volume_and_normalization_unverified",
    "common_usable_history_unverified",
    "source_rights_and_retention_unverified",
    "dated_identity_sector_and_terminal_actions_unverified",
    "real_data_adapter_pending",
    "native_comparator_actions_and_settlement_unverified",
    "independent_review_of_new_source_epoch_pending",
    "QC_access_prohibited_by_current_owner_direction",
)


def _day(value: object) -> date:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CoverageError("exact ISO metadata date required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CoverageError("invalid metadata date") from exc


def _subscription(row: object, as_of: date) -> dict:
    fields = {"provider", "products", "evidence_class", "status", "observed_on",
              "displayed_access_end_date", "nominal_history_years", "evidence_ref"}
    if type(row) is not dict or set(row) != fields:
        raise CoverageError("exact subscription metadata fields required")
    provider = row["provider"]
    if type(provider) is not str or provider not in _PRODUCTS:
        raise CoverageError("unsupported metadata provider")
    products = row["products"]
    if (type(products) is not list or not 1 <= len(products) <= 3
            or any(type(item) is not str or item not in _PRODUCTS[provider] for item in products)
            or len(set(products)) != len(products)):
        raise CoverageError("unique known provider products required")
    observed = _day(row["observed_on"])
    if observed > as_of:
        raise CoverageError("future subscription observation")
    years = row["nominal_history_years"]
    if years is not None and type(years) is not int:
        raise CoverageError("exact nominal history integer or null required")
    expected_years = _NOMINAL_YEARS[provider]
    if provider == "massive" and "stocks_starter" not in products:
        expected_years = None  # analyst-product history is not stock-bar history
    if years != expected_years:
        raise CoverageError("nominal history conflicts with known product tier")
    evidence = row["evidence_class"]
    if type(evidence) is not str or evidence not in {"owner_report", "account_ui_observation"}:
        raise CoverageError("unverified metadata evidence class required")
    end = row["displayed_access_end_date"]
    if evidence == "owner_report":
        if (row["status"] != "owner_reported" or end is not None
                or row["evidence_ref"] != "owner_report"):
            raise CoverageError("owner report cannot impersonate an account observation")
    elif (row["status"] != "displayed_cancellation_pending"
          or row["evidence_ref"] != "authenticated_subscription_page"):
        raise CoverageError("exact observed account metadata required")
    if evidence == "account_ui_observation":
        _day(end)
    result = dict(row, products=sorted(products))
    result["access_date_screen"] = (
        "unknown_owner_report_only" if end is None else
        "at_or_after_displayed_end_recheck_required" if as_of >= _day(end) else
        "before_displayed_end_not_entitlement_proof")
    return result


def _coverage(provider: str, subscription: dict | None) -> dict:
    row = {"provider": provider,
           "guidance": "unknown_no_subscription_metadata",
           "historical_stock_nbbo": "not_demonstrated",
           "historical_spy_nbbo": "not_demonstrated",
           "minute_volume": "unverified", "current_bid_ask": "not_assessed"}
    if subscription is None:
        return row
    products = subscription["products"]
    if provider == "eodhd":
        row["guidance"] = ("analyst_consensus_not_issuer_guidance" if "eod_calendar" in products
                           else "issuer_guidance_not_demonstrated")
        if "eod_all_world" in products:
            row["current_bid_ask"] = "documented_delayed_snapshot_only"
            row["minute_volume"] = "not_in_reported_eod_product"
    elif provider == "massive":
        analysts = {"benzinga_analyst_ratings", "benzinga_analyst_insights"}
        row["guidance"] = ("ratings_and_insights_not_issuer_guidance" if analysts.intersection(products)
                           else "issuer_guidance_not_in_reported_products")
        row["historical_stock_nbbo"] = row["historical_spy_nbbo"] = "not_in_reported_product"
        row["minute_volume"] = ("documented_aggregate_candidate_not_row_verified"
                                if "stocks_starter" in products else "not_in_reported_product")
    elif provider == "fmp":
        row["guidance"] = "structured_issuer_guidance_not_demonstrated"
        row["minute_volume"] = "not_in_published_starter_tier"
    else:
        row["guidance"] = "financial_statements_not_issuer_guidance"
        row["minute_volume"] = "daily_product_not_minute_execution_data"
    return row


def assess_coverage(candidate: Candidate, manifest_bytes: bytes, *, expected_sha256: str) -> dict:
    """Assess only dated metadata; no I/O or caller-certified readiness path.

    Supplied metadata and its outer hash are not independently authenticated.
    No market rows or timestamps are accepted, joined, inferred or backdated.
    Unknown products/fields need a new reviewed contract, not a silent fallback.
    """
    if type(candidate) is not Candidate:
        raise CoverageError("exact pinned candidate required")
    checked = Candidate(candidate.canonical_bytes)
    try:
        body = _decode(manifest_bytes)
    except CandidateError as exc:
        raise CoverageError("strict bounded metadata JSON required") from exc
    if (type(expected_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or hash_bytes(manifest_bytes) != expected_sha256):
        raise CoverageError("retained metadata hash mismatch")
    if (set(body) != {"schema", "candidate_sha256", "as_of_date", "subscriptions"}
            or body["schema"] != _SCHEMA or body["candidate_sha256"] != checked.sha256):
        raise CoverageError("metadata schema or candidate binding mismatch")
    as_of = _day(body["as_of_date"])
    if type(body["subscriptions"]) is not list or len(body["subscriptions"]) > 4:
        raise CoverageError("bounded subscription inventory required")
    subscriptions = [_subscription(row, as_of) for row in body["subscriptions"]]
    subscriptions.sort(key=lambda row: row["provider"])
    by_provider = {row["provider"]: row for row in subscriptions}
    if len(by_provider) != len(subscriptions):
        raise CoverageError("duplicate provider metadata")
    blockers = list(_BLOCKERS)
    if len(subscriptions) != len(_PRODUCTS):
        blockers.append("missing_subscription_metadata")
    if any(row["access_date_screen"] == "at_or_after_displayed_end_recheck_required" for row in subscriptions):
        blockers.append("displayed_access_end_requires_recheck")
    floor = checked.to_dict()["evidence"]["history_feasibility_min_years"]
    return {
        "schema": "gdr.offline.coverage-preflight.v1",
        "scope": "metadata_only_no_market_rows_or_outcomes",
        "status": "blocked", "as_of_date": as_of.isoformat(),
        "candidate_sha256": checked.sha256, "manifest_sha256": expected_sha256,
        "metadata_authenticity_verified": False,
        "subscriptions": subscriptions,
        "coverage": [_coverage(provider, by_provider.get(provider)) for provider in sorted(_PRODUCTS)],
        "public_documentation": dict(_SOURCES),
        "history": {
            "proposed_minimum_usable_years": floor,
            "individual_nominal_tiers_below_floor": [row["provider"] for row in subscriptions
                if row["nominal_history_years"] is not None and row["nominal_history_years"] < floor],
            "common_usable_years_verified": None, "minimum_common_history_established": False,
            "sources_stitched_or_window_shortened": False,
        },
        "blockers": sorted(blockers), "original_readiness": preflight(checked).to_dict(),
        "ready_for_backtesting": False, "point_in_time_evidence_verified": False,
        "qc_access_allowed": False, "provider_access_allowed": False,
        "outcome_access_allowed": False, "orders_allowed": False,
        "note": "Dated metadata and matching hashes do not certify rights, PIT, completeness or authority.",
    }


def observed_manifest() -> bytes:
    """Manual October 24 observations, not a fresh account or entitlement probe.

    End dates reproduce the displayed dates only, not an exact expiry instant
    or permission to retain data afterward. No accounts, keys or payment data.
    """
    products = {
        "eodhd": ["eod_all_world", "eod_calendar"], "fmp": ["starter"],
        "massive": ["benzinga_analyst_insights", "benzinga_analyst_ratings", "stocks_starter"],
        "sharadar": ["bundle_5y"],
    }
    ends = {"eodhd": "2026-11-14", "fmp": "2026-11-13", "massive": "2026-11-06", "sharadar": None}
    subscriptions = []
    for provider in sorted(products):
        owner = provider == "sharadar"
        subscriptions.append({
            "provider": provider, "products": products[provider],
            "evidence_class": "owner_report" if owner else "account_ui_observation",
            "status": "owner_reported" if owner else "displayed_cancellation_pending",
            "observed_on": "2026-10-24", "displayed_access_end_date": ends[provider],
            "nominal_history_years": _NOMINAL_YEARS[provider],
            "evidence_ref": "owner_report" if owner else "authenticated_subscription_page",
        })
    return canonical_json({"schema": _SCHEMA, "candidate_sha256": load_candidate().sha256,
                           "as_of_date": "2026-10-24", "subscriptions": subscriptions}).encode()


def latest_observed_manifest() -> bytes:
    """Retained October 28 metadata; no fresh probe or verified entitlement.

    EODHD, FMP and Massive were observed again; only Stocks Starter appeared
    in Massive's relevant inventory. Absent products have no inferred cause
    or expiry status. Sharadar remains the October 24 owner report. Reuse the
    historical snapshot as a detached projection; do not rewrite its evidence.
    """
    values = _decode(observed_manifest())
    values["as_of_date"] = "2026-10-28"
    for row in values["subscriptions"]:
        if row["provider"] != "sharadar":
            row["observed_on"] = "2026-10-28"
        if row["provider"] == "massive":
            row["products"] = ["stocks_starter"]
    return canonical_json(values).encode()


def main() -> int:
    raw = observed_manifest()
    print(canonical_json(assess_coverage(load_candidate(), raw, expected_sha256=hash_bytes(raw))))
    return 2  # an intact metadata inventory is still blocked, never a launch permit


if __name__ == "__main__":
    raise SystemExit(main())
