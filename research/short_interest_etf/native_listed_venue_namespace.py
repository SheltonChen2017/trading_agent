"""Finite public namespace policy draft, not historical listing admission.

This is a prospective structural pre-count filter. Original identity rows and
origins remain intact. MIC registry creation is not a security listing date;
current registry status is not backdated. Unknown coverage stays negative.
"""
from __future__ import annotations

import json
import re

from data.hashing import canonical_json, hash_payload

ISO_REGISTER = "https://www.iso20022.org/sites/default/files/ISO10383_MIC/ISO10383_MIC.pdf"
ISO_PAGE = "https://www.iso20022.org/market-identifier-codes"
SEC_NASDAQ = "https://www.sec.gov/newsroom/press-releases/2006-9-approval-nasdaq-stock-market-llc-exchange-application"
NYSE_HISTORY = "https://www.nyse.com/history-of-nyse"
CBOE_2017 = "https://ir.cboe.com/news/news-details/2017/CBOE-Holdings-Announces-Additional-Listing-on-Bats-BZX-Exchange-03-08-2017/default.aspx"
VENUES = (
    ("ARCX", "NYSE Arca", "2006-09-25", NYSE_HISTORY),
    ("BATS", "Cboe BZX equities", "2008-11-24", CBOE_2017),
    ("XASE", "NYSE American", "2009-05-25", NYSE_HISTORY),
    ("XNAS", "Nasdaq", "2005-06-27", SEC_NASDAQ),
    ("XNCM", "Nasdaq Capital", "2008-02-25", SEC_NASDAQ),
    ("XNGS", "Nasdaq Global Select", "2006-07-24", SEC_NASDAQ),
    ("XNMS", "Nasdaq Global", "2005-06-27", SEC_NASDAQ),
    ("XNYS", "NYSE", "2005-05-23", NYSE_HISTORY),
)
# Public registry identifies these as OTC/reporting/dark namespaces. The
# negative result never depends on current ACTIVE/EXPIRED status.
NONLISTING = frozenset({"OTCM", "OTCB", "OTCQ", "PINX", "PINL", "PINI", "PINC", "PSGM", "XOTC",
                       "TRFN", "FINR", "XOFF", "NYSD", "ARCD", "NASD"})


def venue_policy():
    return {"schema": "si-finite-dated-source-venue-namespace-draft-v1",
            "prospective_sample_scope": ["2022-01-01", "2026-08-31"],
            "recognized_namespace": [{"mic": mic, "venue_label": label,
                 "iso_registry_creation_date": created, "iso_source": ISO_REGISTER,
                 "historical_venue_source": history} for mic, label, created, history in VENUES],
            "registration_facts": {"Nasdaq_SEC_approval": "2006-01-13",
                 "NYSE_Arca_merger_year": 2006, "Amex_NYSE_acquisition_year": 2008,
                 "BZX_registration_month": "2008-10", "BZX_common_stock_listing_notice": "2017-03-08"},
            "iso_publication_observed": "2026-10-12", "iso_current_active_status_not_backdated": True,
            "mic_creation_is_not_venue_registration_or_security_listing_date": True,
            "per_security_dated_assertion": "exact_source_primary_exchange_only_not_current_master_or_locale",
            "active_listing": "exact_true_from_AllTickers_active_panel_on_queried_date_never_current_status_backdated",
            "active_query_contract": "https://massive.com/docs/rest/stocks/tickers/all-tickers",
            "verified_continuous_venue_effective_intervals": [],
            "negative_namespace": sorted(NONLISTING),
            "unmapped_rule": "negative_original_row_and_origin_retained_no_fallback_or_outcome_pruning",
            "coverage": "finite_declared_namespace_subset_not_all_US_equity_listing_venues",
            "source_admitted": False, "historical_listing_admitted": False,
            "point_in_time_data": False, "outcome_looks": 0, "qc_attempts": 0}


def qualify_venue_namespace(row):
    """Return a detached source-candidate assessment, never a source permit."""
    if type(row) is not dict:
        raise ValueError("exact_dated_identity_row_required")
    value = json.loads(canonical_json(row))
    mic = value.get("primary_exchange")
    reasons = []
    if value.get("active") is not True:
        reasons.append("dated_source_active_listing_assertion_missing_or_inactive")
    if mic is None or mic == "":
        reasons.append("dated_primary_listing_MIC_missing")
    elif type(mic) is not str or re.fullmatch(r"[A-Z0-9]{4}", mic) is None:
        reasons.append("dated_primary_listing_MIC_malformed")
    elif mic in NONLISTING:
        reasons.append("dated_primary_MIC_nonlisting_namespace")
    elif mic not in {item[0] for item in VENUES}:
        reasons.append("dated_primary_MIC_outside_finite_qualified_namespace")
    if (value.get("type"), value.get("locale"), value.get("market")) != ("CS", "us", "stocks"):
        reasons.append("outside_dated_US_common_stock_source_classification")
    value["venue_namespace_assessment"] = {
        "policy_sha256": hash_payload(venue_policy()), "source_listing_venue_candidate": not reasons,
        "refusal_reasons": sorted(reasons), "historical_listing_admitted": False,
        "historical_effective_intervals": [], "historical_available_date": None,
        "source_admitted": False, "outcome_looks": 0, "qc_attempts": 0}
    return value
