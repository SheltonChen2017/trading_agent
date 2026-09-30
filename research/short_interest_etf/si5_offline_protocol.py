"""Content-addressed SI-5 stock-test design, with every empirical gate closed.

The owner's delegated choices are bound to an immutable lane-record revision.
This module describes a prospective stock-first experiment; it neither reads
historical data nor registers a research look. Dates, rights, power and an
exact validation receipt must be bound in a later separately reviewed stage
before any real outcome can be opened.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.preregistration import (
    SHORT_INTEREST_BLUEPRINT_SHA256,
    SHORT_INTEREST_RESEARCH_GATE,
    SHORT_INTEREST_RESEARCH_GATE_SHA256,
    require_short_interest_research_gate,
)


SI5_OFFLINE_PROTOCOL_VERSION = "si5-stock-test-offline-design-v1"
_OWNER_DECISION_PATH = (
    "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md"
)
_OWNER_DECISION_COMMIT = "0e3150507bfa1b396e798fd23ad6fa4a7558a326"
_OWNER_DECISION_SHA256 = (
    "3f7a31a7b3955b31bc6f29d312e1c74f4a923302b70121aa5e91a45d5fddf9d6"
)
_CANDIDATE_LOOKBACKS = (20, 60, 120, 252)
_PRIMARY_CONTRAST = "low_pressure_minus_high_pressure_R20"
_CONFIRMATORY_ROLE_CELLS = ("one_composite_stock_contrast",)
_COMPARISON_POPULATION = "common_release_security_intersection_all_four"
_RETURN_SEMANTIC = (
    "gross_next_open_to_20th_later_XNYS_open_split_adjusted_"
    "dividend_excluded_price_return"
)
_RELEASE_AGGREGATION = "equal_weight_each_tail_then_equal_weight_release_events"
_CANDIDATE_SELECTION = "development_only_best_release_mean_exact_tie_no_winner"
_SECTOR_RELATIVE_ROLE = "descriptive_diagnostic_not_another_primary_test"
_ORDER_EXIT = "next_public_release_next_permitted_open"
_ORDER_COST_ROLE = "next_release_order_pnl_only"


class SI5ProtocolError(ValueError):
    """A caller attempted to change or use an unapproved SI-5 design."""


def _refuse(detail: str) -> SI5ProtocolError:
    return SI5ProtocolError(f"REFUSED: {detail}")


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


@dataclass(frozen=True, slots=True)
class SI5OfflineProtocol:
    """Exact offline design candidate; deliberately not an empirical authority."""

    version: str = SI5_OFFLINE_PROTOCOL_VERSION
    owner_decision_path: str = _OWNER_DECISION_PATH
    owner_decision_commit: str = _OWNER_DECISION_COMMIT
    owner_decision_sha256: str = _OWNER_DECISION_SHA256
    blueprint_sha256: str = SHORT_INTEREST_BLUEPRINT_SHA256
    source_research_gate_sha256: str = SHORT_INTEREST_RESEARCH_GATE_SHA256
    candidate_lookbacks: tuple[int, ...] = _CANDIDATE_LOOKBACKS
    selected_lookback: None = None
    primary_stock_contrast: str = _PRIMARY_CONTRAST
    confirmatory_role_cells: tuple[str, ...] = _CONFIRMATORY_ROLE_CELLS
    comparison_population: str = _COMPARISON_POPULATION
    primary_return_semantic: str = _RETURN_SEMANTIC
    release_aggregation: str = _RELEASE_AGGREGATION
    candidate_selection_rule: str = _CANDIDATE_SELECTION
    sector_relative_role: str = _SECTOR_RELATIVE_ROLE
    primary_horizon_sessions: int = 20
    order_exit_rule: str = _ORDER_EXIT
    diagnostic_cost_bps_per_side: int = 0
    terminal_value_rule: None = None
    order_cashflow_rule: None = None
    order_cost_role: str = _ORDER_COST_ROLE
    primary_cost_bps_per_side: int = 10
    cost_sensitivities_bps_per_side: tuple[int, ...] = (0, 5, 20)
    alpha_ceiling: Fraction = Fraction(1, 80)
    allocated_alpha: Fraction = Fraction(0, 1)
    permanent_look_ids: tuple[str, ...] = ()
    development_dates: None = None
    validation_dates: None = None
    prospective_power_verified: bool = False
    source_rights_verified: bool = False
    actual_pit_coverage_verified: bool = False
    outcome_access_authorized: bool = False
    qc_backtest_authorized: bool = False
    production_authoritative: bool = False
    trading_authority: bool = False

    def __post_init__(self) -> None:
        if type(self) is not SI5OfflineProtocol:
            raise _refuse("protocol must be the exact SI5OfflineProtocol type")
        require_short_interest_research_gate(SHORT_INTEREST_RESEARCH_GATE)
        for name, expected in (
            ("version", SI5_OFFLINE_PROTOCOL_VERSION),
            ("owner_decision_path", _OWNER_DECISION_PATH),
            ("owner_decision_commit", _OWNER_DECISION_COMMIT),
            ("owner_decision_sha256", _OWNER_DECISION_SHA256),
            ("blueprint_sha256", SHORT_INTEREST_BLUEPRINT_SHA256),
            ("source_research_gate_sha256", SHORT_INTEREST_RESEARCH_GATE_SHA256),
            ("primary_stock_contrast", _PRIMARY_CONTRAST),
            ("comparison_population", _COMPARISON_POPULATION),
            ("primary_return_semantic", _RETURN_SEMANTIC),
            ("release_aggregation", _RELEASE_AGGREGATION),
            ("candidate_selection_rule", _CANDIDATE_SELECTION),
            ("sector_relative_role", _SECTOR_RELATIVE_ROLE),
            ("order_exit_rule", _ORDER_EXIT),
            ("order_cost_role", _ORDER_COST_ROLE),
        ):
            value = getattr(self, name)
            if type(value) is not str or value != expected:
                raise _refuse(f"{name} differs from delegated offline design")
        for name, expected in (
            ("candidate_lookbacks", _CANDIDATE_LOOKBACKS),
            ("confirmatory_role_cells", _CONFIRMATORY_ROLE_CELLS),
        ):
            value = getattr(self, name)
            if type(value) is not tuple or value != expected or any(
                type(item) is not type(reference)
                for item, reference in zip(value, expected)
            ):
                raise _refuse(f"{name} differs from delegated offline design")
        for name, expected in (
            ("primary_horizon_sessions", 20),
            ("diagnostic_cost_bps_per_side", 0),
            ("primary_cost_bps_per_side", 10),
        ):
            value = getattr(self, name)
            if type(value) is not int or value != expected:
                raise _refuse(f"{name} differs from frozen horizon/cost terms")
        if (
            type(self.cost_sensitivities_bps_per_side) is not tuple
            or self.cost_sensitivities_bps_per_side != (0, 5, 20)
            or any(type(value) is not int for value in self.cost_sensitivities_bps_per_side)
        ):
            raise _refuse("cost sensitivities differ from frozen terms")
        for name, expected in (
            ("alpha_ceiling", Fraction(1, 80)),
            ("allocated_alpha", Fraction(0, 1)),
        ):
            value = getattr(self, name)
            if type(value) is not Fraction or value != expected:
                raise _refuse(f"{name} differs from the zero-look research gate")
        for name in ("selected_lookback", "development_dates", "validation_dates"):
            if getattr(self, name) is not None:
                raise _refuse(f"{name} cannot be selected before data/power admission")
        for name in ("terminal_value_rule", "order_cashflow_rule"):
            if getattr(self, name) is not None:
                raise _refuse(f"{name} cannot be assumed before source admission")
        if type(self.permanent_look_ids) is not tuple or self.permanent_look_ids:
            raise _refuse("permanent look IDs are not registered")
        for name in (
            "prospective_power_verified",
            "source_rights_verified",
            "actual_pit_coverage_verified",
            "outcome_access_authorized",
            "qc_backtest_authorized",
            "production_authoritative",
            "trading_authority",
        ):
            value = getattr(self, name)
            if type(value) is not bool or value:
                raise _refuse(f"{name} must remain false")

    def to_payload(self) -> dict[str, Any]:
        SI5OfflineProtocol.__post_init__(self)
        return {
            "schema": "short-interest-si5-offline-design-v1",
            "version": self.version,
            "owner_decision_source": {
                "path": self.owner_decision_path,
                "commit": self.owner_decision_commit,
                "sha256": self.owner_decision_sha256,
            },
            "blueprint_sha256": self.blueprint_sha256,
            "source_research_gate_sha256": self.source_research_gate_sha256,
            "candidate_lookbacks": list(self.candidate_lookbacks),
            "selected_lookback": self.selected_lookback,
            "primary_stock_contrast": self.primary_stock_contrast,
            "confirmatory_role_cells": list(self.confirmatory_role_cells),
            "comparison_population": self.comparison_population,
            "primary_return_semantic": self.primary_return_semantic,
            "release_aggregation": self.release_aggregation,
            "candidate_selection_rule": self.candidate_selection_rule,
            "sector_relative_role": self.sector_relative_role,
            "primary_horizon_sessions": self.primary_horizon_sessions,
            "order_exit_rule": self.order_exit_rule,
            "diagnostic_cost_bps_per_side": self.diagnostic_cost_bps_per_side,
            "terminal_value_rule": self.terminal_value_rule,
            "order_cashflow_rule": self.order_cashflow_rule,
            "order_cost_role": self.order_cost_role,
            "primary_cost_bps_per_side": self.primary_cost_bps_per_side,
            "cost_sensitivities_bps_per_side": list(self.cost_sensitivities_bps_per_side),
            "alpha_ceiling": _fraction_payload(self.alpha_ceiling),
            "allocated_alpha": _fraction_payload(self.allocated_alpha),
            "permanent_look_ids": list(self.permanent_look_ids),
            "development_dates": self.development_dates,
            "validation_dates": self.validation_dates,
            "prospective_power_verified": self.prospective_power_verified,
            "source_rights_verified": self.source_rights_verified,
            "actual_pit_coverage_verified": self.actual_pit_coverage_verified,
            "outcome_access_authorized": self.outcome_access_authorized,
            "qc_backtest_authorized": self.qc_backtest_authorized,
            "production_authoritative": self.production_authoritative,
            "trading_authority": self.trading_authority,
        }

    @property
    def sha256(self) -> str:
        return require_si5_offline_protocol(self)


SI5_OFFLINE_PROTOCOL_SHA256 = (
    "bfa06b282132a0b5ceef4e9e4e3900f0dea6ffaadad8e00e22f5c8f837022972"
)


def require_si5_offline_protocol(value: SI5OfflineProtocol) -> str:
    if type(value) is not SI5OfflineProtocol:
        raise _refuse("protocol must be the exact SI5OfflineProtocol type")
    payload = SI5OfflineProtocol.to_payload(value)
    if hash_payload(payload) != SI5_OFFLINE_PROTOCOL_SHA256:
        raise _refuse("offline protocol differs from its frozen semantic identity")
    return SI5_OFFLINE_PROTOCOL_SHA256


SI5_OFFLINE_PROTOCOL = SI5OfflineProtocol()
