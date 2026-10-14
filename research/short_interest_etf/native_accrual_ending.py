"""Prospective v2 native ending-NAV prototype, not cash-settled performance.

Published _book and v1 representation completion remain untouched. Known
ordinary dividends owed at the frozen cutoff may be reported at undiscounted
contractual face value, but are never spendable cash or verified future
collection. Source/identity/classification digests are required lineage slots,
not independently authenticating evidence or an actual-input/QC permit.
"""
from __future__ import annotations

import dataclasses
from datetime import date
from fractions import Fraction

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.latest_revised_protocol import (
    EVALUATION_END, INITIAL_CASH_USD, PROTOCOL_SHA256 as ECONOMIC_SHA256,
)
import research.short_interest_etf.native_qc_order_representation as rep

CUTOFF = EVALUATION_END + "T23:59:59.999999Z"


class NativeAccrualRefusal(ValueError):
    pass


def _refuse(code):
    return NativeAccrualRefusal("REFUSED: " + code)


def _sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise _refuse("source_lineage_digest_required")
    return value


def _date(value):
    if type(value) is not str:
        raise _refuse("canonical_scheduled_pay_date_required")
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise _refuse("canonical_scheduled_pay_date_required") from None
    return value


def _authority():
    return {"source_independently_authenticated": False, "actual_input_admitted": False,
            "outcome_access_authorized": False, "processing_qualified": False,
            "look_registered": False, "qc_execution_authorized": False,
            "actual_bank_cash_settlement_verified": False, "trading_authority": False}


def accrual_policy():
    payload = {
        "schema": "si-native-accrual-ending-policy-v2-prototype",
        "economic_protocol_sha256": ECONOMIC_SHA256,
        "v1_representation_sha256": rep.representation_requirements()["representation_sha256"],
        "decision": "prospective_SI-DEC-20261013-31_native_reporting_only",
        "cutoff": CUTOFF, "initial_cash_per_book_usd": INITIAL_CASH_USD,
        "cell_ids": list(rep.CELL_IDS), "selected_lookback": None,
        "published_kernel": "unchanged_v1_cash_only_completion_and_realized_PnL",
        "eligible_receivable": "source_bound_ordinary_cash_entitlement_same_native_class_positive_known_amount_valid_pay_date_with_modeled_availability_after_cutoff",
        "valuation": "undiscounted_contractual_face_value_explicit_assumption_not_collection_or_market_price",
        "ending_NAV": "cash_plus_qualified_nonspendable_receivables_no_open_positions",
        "cash": "cash_only_at_separately_frozen_modeled_payment_availability_never_ex_date",
        "metrics": "cash_realized_PnL_separate_from_provisional_nominal_accrual_NAV_change",
        "future": "scheduled_pay_date_metadata_only_no_future_price_collection_or_return_join",
        "refusals": ["unknown_ambiguous_amount_or_payment", "missing_native_class_or_source_linkage",
                     "modeled_availability_at_or_before_cutoff_without_settlement", "special_due_bill_stock_or_contingent",
                     "open_positions_or_missing_cohort_outcomes"],
        "ordinary_payment_clock": "first_XNYS_open_strictly_after_provider_pay_day_modeled_not_actual_bank_UTC",
        "zero_entitlement": "zero_value_no_external_payment_required_any_supplied_known_amount_must_match",
        "actual_admission": "external_independent_source_qualifier_processing_look_and_engine_required_prototype_always_refuses",
        "authority": _authority(),
    }
    payload["reporting_policy_sha256"] = hash_payload(payload)
    return payload


def modeled_payment_clock(scheduled_pay_date):
    """Calendar metadata; no bank instant or future cash collection inferred."""
    _date(scheduled_pay_date)
    calendar = rep.nominal_release_open(scheduled_pay_date)
    return {"provider_scheduled_pay_date": scheduled_pay_date,
            "provider_precision": "date_only",
            "modeled_cash_available_at": calendar["entry_at"],
            "clock_semantic": "conservative_first_XNYS_open_strictly_after_provider_pay_day",
            "actual_bank_UTC": None, "actual_bank_cash_settlement_verified": False,
            "model_clock_not_observed_payment_fact": True}


@dataclasses.dataclass(frozen=True, slots=True)
class OrdinaryDividendAssertion:
    """Unadmitted source-free assertion; positive hash slots prove no facts."""
    security_id: str
    dividend_id: str
    cash_per_share: Fraction
    scheduled_pay_date: str
    source_payload_sha256: str
    native_class_binding_sha256: str
    ordinary_classification_evidence_sha256: str
    distribution: str = "ordinary_cash"
    currency: str = "USD"
    _anchor: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not OrdinaryDividendAssertion:
            raise _refuse("exact_ordinary_dividend_assertion_required")
        payload = canonical_json(self._payload())
        if hasattr(self, "_anchor") and (type(self._anchor) is not str or self._anchor != payload):
            raise _refuse("dividend_assertion_identity_changed")
        if not hasattr(self, "_anchor"):
            object.__setattr__(self, "_anchor", payload)

    def _payload(self):
        if type(self) is not OrdinaryDividendAssertion:
            raise _refuse("exact_ordinary_dividend_assertion_required")
        rep._identifier(self.security_id); rep._identifier(self.dividend_id)
        rep._fraction(self.cash_per_share)
        _date(self.scheduled_pay_date)
        if type(self.distribution) is not str or self.distribution != "ordinary_cash":
            raise _refuse("nonordinary_or_unqualified_distribution")
        if type(self.currency) is not str or self.currency != "USD":
            raise _refuse("USD_native_ordinary_cash_required")
        return {"security_id": self.security_id, "dividend_id": self.dividend_id,
                "cash_per_share": rep._rational(self.cash_per_share),
                "scheduled_pay_date": self.scheduled_pay_date,
                "source_payload_sha256": _sha(self.source_payload_sha256),
                "native_class_binding_sha256": _sha(self.native_class_binding_sha256),
                "ordinary_classification_evidence_sha256": _sha(self.ordinary_classification_evidence_sha256),
                "distribution": self.distribution, "currency": self.currency}

    def to_payload(self):
        if type(self) is not OrdinaryDividendAssertion:
            raise _refuse("exact_ordinary_dividend_assertion_required")
        payload = self._payload()
        if type(self._anchor) is not str or canonical_json(payload) != self._anchor:
            raise _refuse("dividend_assertion_identity_changed")
        payload["assertion_sha256"] = hash_payload(payload)
        return payload


def _ending(books, dividends):
    rep._family(books)
    if type(dividends) is not tuple or any(type(d) is not OrdinaryDividendAssertion for d in dividends):
        raise _refuse("immutable_exact_dividend_assertions_required")
    dividend_map = {}
    for dividend in dividends:
        dividend.to_payload()
        key = dividend.security_id, dividend.dividend_id
        if key in dividend_map:
            raise _refuse("duplicate_or_ambiguous_dividend_assertion")
        dividend_map[key] = dividend
    outputs = []
    initial = Fraction(INITIAL_CASH_USD)
    for book in books:
        if type(book._anchor) is not str:
            raise _refuse("source_book_anchor_identity_changed")
        source = book.to_payload()
        if book.transport.positions:
            raise _refuse("open_positions_at_frozen_cutoff")
        if book.last_key is not None and rep._stamp(book.last_key[0]) > rep._stamp(CUTOFF):
            raise _refuse("book_has_post_cutoff_transition")
        receivables, accrued = [], Fraction(0)
        for receivable in book.receivables:
            receivable.payload()
            if rep._stamp(receivable.entitlement_at) > rep._stamp(CUTOFF):
                raise _refuse("entitlement_after_cutoff")
            dividend = dividend_map.get((receivable.security_id, receivable.dividend_id))
            if dividend is not None and dividend.cash_per_share != receivable.cash_per_share:
                raise _refuse("ordinary_amount_or_native_class_linkage_mismatch")
            if receivable.economic_amount == 0:
                continue
            if dividend is None:
                raise _refuse("positive_receivable_without_ordinary_source_assertion")
            clock = modeled_payment_clock(dividend.scheduled_pay_date)
            if rep._stamp(clock["modeled_cash_available_at"]) <= rep._stamp(CUTOFF):
                raise _refuse("model_available_receivable_requires_separate_settlement")
            amount = receivable.economic_amount
            accrued += amount
            receivables.append({"security_id": receivable.security_id, "dividend_id": receivable.dividend_id,
                "entitlement_at": receivable.entitlement_at,
                "scheduled_pay_date": dividend.scheduled_pay_date,
                "amount": rep._rational(amount), "spendable_cash": False,
                "future_collection_verified": False, "actual_bank_UTC": None,
                "modeled_payment_clock": clock,
                "valuation": "undiscounted_contractual_face_value_assumption",
                "assertion_sha256": dividend.to_payload()["assertion_sha256"]})
        cash = book.transport.economic_cash
        nav = cash + accrued
        outputs.append({"cell_id": book.transport.cell_id, "source_book_sha256": source["book_sha256"],
            "cutoff": CUTOFF, "initial_cash": rep._rational(initial),
            "ending_cash": rep._rational(cash), "cash_realized_pnl": rep._rational(cash - initial),
            "ordinary_dividend_receivables": receivables, "receivable_face_value": rep._rational(accrued),
            "provisional_nominal_accrual_NAV": rep._rational(nav),
            "provisional_nominal_NAV_change": rep._rational(nav - initial),
            "provisional_nominal_NAV_return": rep._rational((nav - initial) / initial),
            "total_fees": rep._rational(book.transport.economic_fees_paid),
            "cash_settlement_complete": accrued == 0,
            "native_reporting_computable": True, "actual_bank_cash_settlement_verified": False,
            "final_positions": []})
    payload = {"schema": "si-native-accrual-ending-report-v2-prototype",
        "reporting_policy_sha256": accrual_policy()["reporting_policy_sha256"],
        "source_ordinary_assertions_sha256": hash_payload([d.to_payload() for d in dividends]),
        "cutoff": CUTOFF, "books": outputs,
        "all_48_native_reports_computable": True,
        "all_cash_settled": all(b["cash_settlement_complete"] for b in outputs),
        "provisional_nominal_accrual_NAV_not_realized_performance": True,
        "qc_backtest_completed": False, "authority": _authority(),
        "actual_outcome_looks": 0, "qc_launch_attempts": 0, "selected_lookback": None}
    payload["native_ending_report_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class NativeAccrualEndingReport:
    books: tuple[rep.CellBook, ...] = dataclasses.field(repr=False)
    dividends: tuple[OrdinaryDividendAssertion, ...] = dataclasses.field(repr=False)
    _anchor: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not NativeAccrualEndingReport:
            raise _refuse("exact_native_ending_report_required")
        payload = canonical_json(_ending(self.books, self.dividends))
        if hasattr(self, "_anchor") and (type(self._anchor) is not str or self._anchor != payload):
            raise _refuse("native_ending_identity_changed")
        if not hasattr(self, "_anchor"):
            object.__setattr__(self, "_anchor", payload)

    def to_payload(self):
        if type(self) is not NativeAccrualEndingReport:
            raise _refuse("exact_native_ending_report_required")
        payload = _ending(self.books, self.dividends)
        if type(self._anchor) is not str or canonical_json(payload) != self._anchor:
            raise _refuse("native_ending_identity_changed")
        return payload


def build_native_ending_report(books, dividends=()):
    return NativeAccrualEndingReport(books, dividends)


def require_actual_execution(*_args, **_kwargs):
    raise _refuse("prototype_ending_report_is_not_actual_source_processing_look_or_engine_authority")
