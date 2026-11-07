"""Composition is reproducible software evidence, not backtesting readiness."""
from copy import deepcopy

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.si5_synthetic_rehearsal import (
    run_si5_synthetic_rehearsal,
)


def test_composed_fixed_scenarios_complete_but_do_not_admit_actual_backtest():
    receipt = run_si5_synthetic_rehearsal()
    payload = receipt.to_payload()
    assert receipt.sha256 == hash_payload({key: value for key, value in payload.items() if key != "rehearsal_sha256"})
    assert payload["software_rehearsal_complete"] is True
    assert payload["synthetic_only"] is True
    for name in ("real_backtesting_ready", "source_ranking_to_orders_admitted", "source_admitted",
                 "outcome_access_authorized", "qc_backtest_authorized", "trading_authority"):
        assert payload[name] is False
    assert payload["selected_lookback"] is None
    assert payload["allocated_alpha"] == {"numerator": 0, "denominator": 1}
    assert payload["permanent_look_ids"] == []
    assert payload["authorized_real_outcome_looks"] == payload["consumed_real_outcome_looks"] == 0
    assert len(payload["remaining_external_facts"]) == len(payload["remaining_source_dependent_work"]) == 4
    assert payload["independent_Claude_review_required"] is True
    assert [row["cost_bps_per_side"] for row in payload["order_accounting"]["cost_runs"]] == [0, 5, 10, 20]
    assert payload["gross_R20_diagnostic"]["diagnostic_cost_bps_per_side"] == 0
    assert payload["order_accounting"]["fixture_sha256"] != payload["gross_R20_diagnostic"]["fixture_sha256"]


def test_detached_receipt_cannot_repair_tampering_or_carry_caller_authority():
    receipt = run_si5_synthetic_rehearsal()
    expected = deepcopy(receipt.to_payload())
    exported = receipt.to_payload()
    exported["remaining_external_facts"].clear()
    assert receipt.to_payload() == expected
    receipt._payload["source_admitted"] = 0
    with pytest.raises(ValueError, match="receipt changed"):
        receipt.to_payload()
    with pytest.raises(TypeError):
        run_si5_synthetic_rehearsal(prices=[], source_admitted=True)


def test_rehearsal_replay_has_identical_content_identity():
    assert run_si5_synthetic_rehearsal().to_payload() == run_si5_synthetic_rehearsal().to_payload()
