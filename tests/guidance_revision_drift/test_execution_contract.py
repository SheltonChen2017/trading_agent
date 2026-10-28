"""Focused offline checks for fixed costs and explicitly dated settlement inputs."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
import unittest
from zoneinfo import ZoneInfo

from research.guidance_revision_drift.execution_contract import (
    ExecutionContract, ExecutionContractError, default_contract,
)
from research.guidance_revision_drift.research_reference import CalendarInput


NY = ZoneInfo("America/New_York")
SOURCE = "a" * 64


def _instant(day: date, hour: int, minute: int = 0) -> str:
    return datetime.combine(day, time(hour, minute), NY).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _calendar(*days: date) -> CalendarInput:
    return CalendarInput.from_dict({
        "schema": "gdr.research-calendar.v1", "calendar_id": "OFFLINE-SETTLEMENT-TEST",
        "source_sha256": "b" * 64,
        "covered_from": days[0].isoformat(), "covered_through": days[-1].isoformat(),
        "sessions": [{"date": day.isoformat(), "open_utc": _instant(day, 9, 30),
                      "close_utc": _instant(day, 16)} for day in days],
    })


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), NY).astimezone(timezone.utc)


class ExecutionContractTests(unittest.TestCase):
    def test_2017_t3_to_t2_cutover_uses_supplied_settlement_dates(self):
        calendar = _calendar(date(2017, 9, 1), date(2017, 9, 5), date(2017, 9, 6),
                             date(2017, 9, 7), date(2017, 9, 8))
        contract = default_contract((date(2017, 9, 1), date(2017, 9, 5),
                                     date(2017, 9, 6), date(2017, 9, 7), date(2017, 9, 8)),
                                    calendar_source_sha256=SOURCE)
        self.assertEqual(contract.settlement_on(calendar, date(2017, 9, 1)), date(2017, 9, 7))
        self.assertEqual(contract.settlement_on(calendar, date(2017, 9, 5)), date(2017, 9, 7))

    def test_memorial_transition_has_double_settlement_may_29(self):
        calendar = _calendar(date(2024, 5, 22), date(2024, 5, 23), date(2024, 5, 24),
                             date(2024, 5, 28), date(2024, 5, 29))
        contract = default_contract((date(2024, 5, 22), date(2024, 5, 23),
                                     date(2024, 5, 24), date(2024, 5, 28), date(2024, 5, 29)),
                                    calendar_source_sha256=SOURCE)
        self.assertEqual(contract.settlement_on(calendar, date(2024, 5, 23)), date(2024, 5, 28))
        self.assertEqual(contract.settlement_on(calendar, date(2024, 5, 24)), date(2024, 5, 29))
        self.assertEqual(contract.settlement_on(calendar, date(2024, 5, 28)), date(2024, 5, 29))

    def test_market_open_bank_holiday_is_not_a_settlement_day(self):
        calendar = _calendar(date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13))
        contract = default_contract((date(2026, 10, 9), date(2026, 10, 13)),
                                    calendar_source_sha256=SOURCE)
        # This future trade is protected by the candidate's outcome boundary.
        with self.assertRaisesRegex(ExecutionContractError, "trade_date_outside_unprotected_rule_scope"):
            contract.settlement_on(calendar, date(2026, 10, 12))
        calendar = _calendar(date(2025, 11, 10), date(2025, 11, 11), date(2025, 11, 12))
        contract = default_contract((date(2025, 11, 10), date(2025, 11, 12)),
                                    calendar_source_sha256=SOURCE)
        self.assertEqual(contract.settlement_on(calendar, date(2025, 11, 10)), date(2025, 11, 12))
        self.assertEqual(contract.settlement_on(calendar, date(2025, 11, 11)), date(2025, 11, 12))

    def test_costs_are_cumulative_once_per_order(self):
        contract = default_contract((date(2025, 1, 2),), calendar_source_sha256=SOURCE)
        self.assertEqual(contract.commission(0, "base"), Decimal(0))
        self.assertEqual(contract.commission(50, "base"), Decimal("1"))
        self.assertEqual(contract.commission(250, "base"), Decimal("1.25"))
        self.assertEqual(contract.commission(250, "base") - contract.commission(50, "base"), Decimal("0.25"))
        self.assertEqual(contract.commission(250, "stress"), Decimal("2"))
        self.assertEqual(contract.commission(500, "stress"), Decimal("2.5"))
        self.assertEqual(contract.to_dict()["execution_costs"]["base_impact_fraction"], "0.0005")
        self.assertEqual(contract.to_dict()["execution_costs"]["stress_impact_fraction"], "0.0015")
        with self.assertRaises(ExecutionContractError):
            contract.commission(True, "base")
        with self.assertRaises(ExecutionContractError):
            contract.commission(1, "unregistered")

    def test_terminal_spy_proposed_clock_never_backdates_or_fabricates_fill(self):
        days = (date(2025, 5, 1), date(2025, 5, 2), date(2025, 5, 5))
        calendar = _calendar(*days)
        contract = default_contract(days, calendar_source_sha256=SOURCE)
        self.assertEqual(contract.terminal_spy_unwind_at(calendar, _at(days[0], 9, 30)), _at(days[0], 10))
        self.assertEqual(contract.terminal_spy_unwind_at(calendar, _at(days[0], 9, 59)), _at(days[0], 10))
        self.assertEqual(contract.terminal_spy_unwind_at(calendar, _at(days[0], 10)), _at(days[1], 10))
        self.assertEqual(contract.terminal_spy_unwind_at(calendar, _at(days[0], 10, 1)), _at(days[1], 10))
        self.assertEqual(contract.terminal_spy_unwind_at(calendar, _at(days[0], 9, 29)), _at(days[0], 10))
        self.assertEqual(contract.terminal_spy_unwind_at(calendar, _at(days[0], 0)), _at(days[0], 10))
        self.assertEqual(contract.terminal_spy_unwind_at(calendar, _at(days[0], 16, 1)), _at(days[1], 10))
        self.assertEqual(contract.terminal_spy_unwind_at(calendar, _at(date(2025, 5, 3), 10)), _at(days[2], 10))
        with self.assertRaises(ExecutionContractError):
            contract.terminal_spy_unwind_at(calendar, datetime(2025, 5, 1, 13, 30))
        with self.assertRaisesRegex(ExecutionContractError, "terminal_entitlement_outside_unprotected_calendar_coverage"):
            contract.terminal_spy_unwind_at(calendar, _at(date(2025, 4, 30), 16, 1))
        with self.assertRaises(ExecutionContractError):
            contract.terminal_spy_unwind_at(calendar, _at(days[-1], 10))
        policy = contract.to_dict()["terminal_spy_policy"]
        self.assertFalse(policy["fabricate_source_fill"])
        self.assertFalse(policy["spend_unpaid_terminal_proceeds"])
        self.assertFalse(policy["economic_policy_frozen_by_owner"])

    def test_roundtrip_strict_mutations_and_missing_settlement_refuse(self):
        days = (date(2024, 5, 24), date(2024, 5, 28), date(2024, 5, 29))
        contract = default_contract(days, calendar_source_sha256=SOURCE)
        self.assertEqual(ExecutionContract.from_bytes(contract.canonical_bytes).sha256, contract.sha256)
        self.assertEqual(ExecutionContract.from_dict(contract.to_dict()).to_dict(), contract.to_dict())
        calendar = _calendar(*days)
        with self.assertRaisesRegex(ExecutionContractError, "settlement_date_not_supplied"):
            contract.settlement_on(calendar, date(2024, 5, 29))
        for mutation in (
            lambda body: body.update(extra=True),
            lambda body: body["regular_way_rules"][2].update(settlement_business_day_lag=2),
            lambda body: body["regular_way_rules"][2].update(settlement_business_day_lag=True),
            lambda body: body["execution_costs"].update(per_share_commission="0"),
            lambda body: body["evidence_status"].update(real_orders_allowed=True),
            lambda body: body["evidence_status"].update(real_orders_allowed=0),
            lambda body: body["terminal_spy_policy"].update(economic_policy_frozen_by_owner=True),
            lambda body: body["terminal_spy_policy"].update(economic_policy_frozen_by_owner=0),
            lambda body: body.update(settlement_business_days=["2024-05-24", "2024-05-29", "2024-05-28"]),
        ):
            body = contract.to_dict()
            mutation(body)
            with self.subTest(mutation=mutation), self.assertRaises(ExecutionContractError):
                ExecutionContract.from_dict(body)
        with self.assertRaises(ExecutionContractError):
            ExecutionContract.from_bytes(contract.canonical_bytes + b"\n")
        with self.assertRaises(ExecutionContractError):
            default_contract((date(2024, 5, 25),), calendar_source_sha256=SOURCE)


if __name__ == "__main__":
    unittest.main()
