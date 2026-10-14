"""Frozen, descriptive latest-revised study; never historical-PIT authority.

The decision record predates any actual market-input or outcome read. This
protocol is separate from SI5OfflineProtocol and cannot reopen its gates.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from data.hashing import hash_payload

EPOCH_ID = "latest-revised-exploratory-si-v1"
EVIDENCE_EPOCH = EPOCH_ID
LOOKBACKS = (20, 60, 120, 252)
COSTS_BPS = (0, 5, 10, 20)
INITIAL_CASH_USD = "100000"
EVALUATION_START = "2023-01-03"
EVALUATION_END = "2026-08-31"
ALLOCATION_ROLES = ("equal_weight_common", "avoid_high_pressure", "long_low_pressure")
OWNER_DECISION_COMMIT = "b034cda27075d48eca42b943db0e45af6024b53d"
OWNER_DECISION_SHA256 = "d67ef69de29d797fde7ea5f9b2793eac3ceec9c8726978a7c3b6696d636e6d8b"


def _frozen_protocol() -> dict[str, Any]:
    return {
        "schema": "si-latest-revised-exploratory-protocol-v1",
        "evidence_epoch": EPOCH_ID,
        "owner_decision_source": {
            "path": "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md",
            "commit": OWNER_DECISION_COMMIT,
            "sha256": OWNER_DECISION_SHA256,
            "section": 97,
        },
        "candidate_lookbacks": list(LOOKBACKS),
        "selected_lookback": None,
        "evaluation_start": EVALUATION_START,
        "evaluation_end": EVALUATION_END,
        "warmup_only_before_start": True,
        "signal": "S1_current_SI_current_shares_minus_immediate_prior_SI_prior_shares",
        "normalization": {
            "winsor": "global_exact_type7_p01_p99_structural_sectors",
            "minimum_sector_peers": 20,
            "mad_scale": {"numerator": 7413, "denominator": 5000},
            "epsilon": 0,
            "zero_mad": "whole_sector_refusal",
        },
        "minimum_market_cap_usd": "300000000",
        "minimum_median_daily_dollar_volume_usd": "10000000",
        "volume_windows": "every_completed_XNYS_session_strictly_before_entry",
        "ranking": "exact_midpercentile_2lower_plus_equal_over_2N",
        "tail_threshold": {"numerator": 9, "denominator": 10},
        "minimum_rankable_population": 10,
        "comparison": "all_four_common_share_class_identity_intersection_original_tails",
        "timing": "hypothetical_calendar_publication_date_next_XNYS_open",
        "initial_cash_usd": INITIAL_CASH_USD,
        "cost_bps_per_side": list(COSTS_BPS),
        "primary_cost_bps_per_side": 10,
        "allocation_roles": list(ALLOCATION_ROLES),
        "cash_books": 48,
        "capital_rule": "continuous_self_financing_long_only_fractional_fee_reserved",
        "rebalance": "successor_calendar_entry_open_final_exit_without_new_entry",
        "cashflow_rule": "raw_opens_split_quantity_dividend_entitlement_then_payment_explicit_terminal",
        "incomplete_rule": "no_cumulative_pnl_no_missing_member_or_terminal_substitution",
        "research_claim": "descriptive_latest_revised_feasibility_not_historical_PIT",
        "latest_revised": True,
        "point_in_time_data": False,
        "source_admitted": False,
        "confirmatory_eligible": False,
        "historical_availability_known": False,
        "original_vintages_retained": False,
        "exhaustive_correction_inventory_available": False,
        "whole_listed_universe_coverage_verified": False,
        "source_rights_verified": False,
        "qc_processing_rights_verified": False,
        "qc_authority": False,
        "production_authoritative": False,
        "trading_authority": False,
        "allocated_alpha": {"numerator": 0, "denominator": 1},
        "confirmatory_permanent_look_ids": [],
        "actual_outcome_looks_authorized": 0,
        "launch_attempts": 0,
    }


PROTOCOL_SHA256 = "b88060aee6cecb232f68f2fe415b3981215ea6f53374fb86a79dbae2efc981c6"


def protocol_payload() -> dict[str, Any]:
    """Return a detached design; flags describe evidence, not caller approval."""
    payload = _frozen_protocol()
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise ValueError("REFUSED: latest-revised protocol differs from frozen decisions")
    return deepcopy(payload)
