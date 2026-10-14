"""One reproducible software rehearsal, with real-backtest blockers explicit.

No providers, external prices, ranking seeds or outcome registries are read.
This composes two fixed-fixture runners; it is not an empirical runner shell.
Actual ranking-to-order translation must be separately reviewed against an
admitted source, the frozen evaluation and that platform's execution contract.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    require_si5_offline_protocol,
)
from research.short_interest_etf.si5_synthetic_diagnostic import (
    run_si5_synthetic_diagnostic_scenario,
)
from research.short_interest_etf.si5_synthetic_orders import (
    run_si5_synthetic_order_scenario,
)
from research.short_interest_etf.si5_synthetic_policy import (
    SI5_SYNTHETIC_POLICY_SHA256,
    synthetic_policy_payload,
)


def _payload() -> dict[str, Any]:
    policy = synthetic_policy_payload()
    protocol_sha256 = require_si5_offline_protocol(SI5_OFFLINE_PROTOCOL)
    orders = run_si5_synthetic_order_scenario().to_payload()
    diagnostic = run_si5_synthetic_diagnostic_scenario().to_payload()
    for component in (orders, diagnostic):
        if component["demonstration_policy_sha256"] != SI5_SYNTHETIC_POLICY_SHA256:
            raise ValueError("REFUSED: rehearsal components differ from demonstration policy")
        if component["synthetic_only"] is not True or component["real_backtesting_ready"] is not False:
            raise ValueError("REFUSED: component crossed synthetic-only boundary")
        if component["authorized_real_outcome_looks"] != 0 or component["consumed_real_outcome_looks"] != 0:
            raise ValueError("REFUSED: software rehearsal cannot carry real research looks")
    if {run["cost_bps_per_side"] for run in orders["cost_runs"]} != {0, 5, 10, 20} or any(
        run["complete"] is not True for run in orders["cost_runs"]
    ):
        raise ValueError("REFUSED: fixed order rehearsal did not complete all cost cases")
    if diagnostic["diagnostic"]["aggregate_comparable"] is not True or (
        diagnostic["diagnostic"]["selected_lookback"] is not None
    ):
        raise ValueError("REFUSED: diagnostic rehearsal incomplete or selected a candidate")
    result = {
        "schema": "si5-composed-synthetic-software-rehearsal-v1",
        "demonstration_policy": policy,
        "demonstration_policy_sha256": SI5_SYNTHETIC_POLICY_SHA256,
        "offline_protocol_sha256": protocol_sha256,
        "synthetic_only": True,
        "software_rehearsal_complete": True,
        "real_backtesting_ready": False,
        "source_ranking_to_orders_admitted": False,
        "selected_lookback": None,
        "source_admitted": False,
        "outcome_access_authorized": False,
        "qc_backtest_authorized": False,
        "trading_authority": False,
        "allocated_alpha": {"numerator": 0, "denominator": 1},
        "permanent_look_ids": [],
        "authorized_real_outcome_looks": 0,
        "consumed_real_outcome_looks": 0,
        "order_accounting": orders,
        "gross_R20_diagnostic": diagnostic,
        "remaining_external_facts": [
            "authentic_SI_first_releases_all_corrections_or_exhaustive_inventory",
            "actual_publication_availability_and_historical_listed_delisted_identity",
            "licensed_PIT_price_volume_corporate_action_terminal_coverage",
            "local_retention_computation_rights_and_separate_exact_QC_route_rights",
        ],
        "remaining_source_dependent_work": [
            "reviewed_source_specific_immutable_acquisition_and_normalization_adapter",
            "ranking_cohort_to_order_and_price_join_with_admitted_identity_and_fill_rules",
            "prospective_dates_power_and_permanent_research_look_freeze_before_outcomes",
            "platform_parity_and_exact_QC_candidate_compile_run_after_its_gates_clear",
        ],
        "independent_Claude_review_required": True,
    }
    result["rehearsal_sha256"] = hash_payload(result)
    return result


@dataclass(frozen=True, slots=True, init=False)
class SI5SyntheticRehearsal:
    _payload: dict[str, Any] = field(repr=False)
    _canonical_json: str = field(repr=False)

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not SI5SyntheticRehearsal:
            raise ValueError("REFUSED: exact synthetic rehearsal type required")
        expected = _payload()
        if (
            type(self._payload) is not dict
            or type(self._canonical_json) is not str
            or canonical_json(self._payload) != canonical_json(expected)
            or self._canonical_json != canonical_json(expected)
        ):
            raise ValueError("REFUSED: synthetic rehearsal receipt changed")
        return deepcopy(expected)

    @property
    def sha256(self) -> str:
        return SI5SyntheticRehearsal.to_payload(self)["rehearsal_sha256"]


def run_si5_synthetic_rehearsal() -> SI5SyntheticRehearsal:
    """Complete only the fixed synthetic software cases, without side effects."""
    payload = _payload()
    result = object.__new__(SI5SyntheticRehearsal)
    object.__setattr__(result, "_payload", deepcopy(payload))
    object.__setattr__(result, "_canonical_json", canonical_json(payload))
    return result
