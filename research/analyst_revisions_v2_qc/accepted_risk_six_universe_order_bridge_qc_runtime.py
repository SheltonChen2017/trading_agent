"""Prospective R-181 A3 buying-power admission bridge, for QC backtests only.

This is a *permission* for LEAN to admit simultaneous pre-open sell and buy
MOO tickets, not a 2x portfolio target.  The six-universe construction and
98% long-only target are unchanged.  Every actual security is configured for
2x buying power, while cash, end-day exposure, and executed target tracking
must pass separate, explicit validity gates.  Neither this module nor a
terminal QC ``Completed`` status makes an invalid order run valid.
"""

import json
from decimal import Decimal

try:
    import accepted_risk_six_universe_order_qc_runtime as _base
    import accepted_risk_six_universe_order_targets as _targets
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_qc_runtime as _base,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_targets as _targets,
    )


class AcceptedRiskSixUniverseOrderBridgeQcRuntimeError(
    _base.AcceptedRiskSixUniverseOrderQcRuntimeError
):
    """A bridge configuration or its actual unlevered path was refused."""


BRIDGE_VARIANT = "cap90_admission_bridge_v1"
BRIDGE_PROFILE_SCHEMA = "arv2-six-universe-order-admission-bridge-profile-v1"
BRIDGE_SUMMARY_SCHEMA = "arv2-six-universe-order-admission-bridge-summary-v1"
ADMISSION_LEVERAGE = Decimal("2")
MAXIMUM_REALIZED_GROSS_EXPOSURE = Decimal("1")
MAXIMUM_MEAN_TARGET_WEIGHT_L1_ERROR = Decimal("0.02")
MAXIMUM_SINGLE_TARGET_WEIGHT_L1_ERROR = Decimal("0.05")
META_STATISTIC_NAME = _base.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _base.AGGREGATES_STATISTIC_NAME
MAXIMUM_STATISTIC_BYTES = _base.MAXIMUM_STATISTIC_BYTES


def _error(message):
    raise AcceptedRiskSixUniverseOrderBridgeQcRuntimeError(message)


def require_bridge_profile(role):
    """Return a detached, digest-checked admission-only profile."""
    if type(role) is not str or role not in _targets.ROLES:
        _error("bridge role is not frozen")
    predecessor = _base.require_six_universe_order_profile(
        role, variant=_base.CAP90_VARIANT
    )
    seed = {
        key: value for key, value in predecessor.items()
        if key != "profile_sha256"
    }
    seed.update({
        "schema": BRIDGE_PROFILE_SCHEMA,
        "profile_id": (
            "arv2-six-universe-order-" + role + "-cap90-admission-bridge-v1"
        ),
        "cap90_predecessor_profile_sha256": predecessor["profile_sha256"],
        "admission_policy": (
            "two_x_security_buying_power_for_pending_preopen_moo_"
            "sell_buy_overlap_only"
        ),
        "admission_leverage": "2",
        "leverage": True,
        "target_gross_exposure": "0.98",
        "realized_borrowing_allowed": False,
        "daily_cash_minimum": "0",
        "end_day_gross_exposure_maximum": "1",
        # Whole-share rounding and prior-close execution marks may leave
        # small ordinary residuals.  A 5%-of-equity single-rebalance L1
        # deviation or 2% mean would no longer track a 98% target closely.
        "maximum_mean_target_weight_l1_error": "0.02",
        "maximum_single_target_weight_l1_error": "0.05",
        "target_weight_l1_error_mark_basis": (
            "prior_close_reference_prices_not_realized_open_prices"
        ),
        "execution_validity_rule": (
            "all_orders_terminal_no_invalid_or_canceled_and_"
            "daily_cash_nonnegative_and_end_day_gross_at_most_one_"
            "and_target_l1_within_both_bounds"
        ),
    })
    result = {**seed, "profile_sha256": _base._sha(seed)}
    return json.loads(_base._canonical(result).decode("ascii"))


def expected_bridge_custom_statistic_names(role):
    require_bridge_profile(role)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


class BridgeAdmissionMixin:
    """Reusable admission, authority and realized-path gates for each role.

    A later tilt successor may override the two ``_bridge_expected_*`` hooks
    and inherit this mixin immediately before the base QC driver.  It must
    not combine this mixin with the frozen tilt-v4 driver, whose old profile
    checker deliberately rejects a new profile.
    """

    def _bridge_expected_profile(self):
        return require_bridge_profile(self._bridge_role)

    def _bridge_expected_builder_type(self):
        return _targets.SixUniverseOrderTargetBuilder

    def _bridge_summary_schema(self):
        return BRIDGE_SUMMARY_SCHEMA

    def _bridge_expected_statistic_names(self):
        return expected_bridge_custom_statistic_names(self._bridge_role)

    def _bridge_authority(self):
        if self._algorithm.live_mode is not False:
            _error("bridge runtime is backtest-only")
        expected = self._bridge_expected_profile()
        if (
            self._bridge_initialized is not True
            or type(self._role) is not str
            or self._role != self._bridge_role
            or type(self._variant) is not str
            or self._variant != _base.CAP90_VARIANT
            or type(self._profile) is not dict
            or self._profile is not self._bridge_profile
            or self._profile != expected
            or type(self._target_builder)
            is not self._bridge_expected_builder_type()
            or self._target_builder is not self._bridge_builder
        ):
            _error("bridge runtime role, profile, or target authority changed")

    def initialize(self):
        if self._bridge_initialized is True:
            _error("bridge runtime initialized more than once")
        if self._algorithm.live_mode is not False:
            _error("bridge runtime is backtest-only")
        super().initialize()
        expected = self._bridge_expected_profile()
        if type(self._target_builder) is not self._bridge_expected_builder_type():
            _error("bridge target builder type changed")
        self._bridge_role = self._role
        self._profile = expected
        self._bridge_profile = expected
        self._bridge_builder = self._target_builder
        self._bridge_cash_observations = {}
        self._bridge_event_cash_minimum = None
        self._bridge_event_cash_count = 0
        self._bridge_initialized = True
        self._bridge_authority()
        return True

    def _require_initialized(self):
        super()._require_initialized()
        self._bridge_authority()

    def configure_security(self, security):
        if self._algorithm.live_mode is not False:
            _error("bridge runtime is backtest-only")
        configured = super().configure_security(security)
        try:
            security.set_leverage(2)
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderBridgeQcRuntimeError(
                "bridge security buying-power leverage could not be set"
            ) from exc
        self._require_effective_two_x(security)
        return configured

    def _require_effective_two_x(self, security):
        try:
            effective = _base._decimal(
                security.buying_power_model.get_leverage(security),
                "bridge effective security leverage",
                positive=True,
            )
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderBridgeQcRuntimeError(
                "bridge security buying-power leverage is unavailable"
            ) from exc
        if effective != ADMISSION_LEVERAGE:
            _error("bridge effective security leverage is not two")

    def _ensure_security(self, security_id):
        # The frozen base path explicitly calls add_security(..., leverage=1).
        # Reuse its identity, cap, and configuration checks, replacing only
        # the subscription leverage argument.  The configured security's
        # effective buying-power model is verified before any order can use it.
        symbol = self._symbol_for_security(security_id)
        sid = _base._symbol_sid(symbol, "bridge target security")
        is_static_etf = sid in self._security_by_etf_sid
        if not is_static_etf and sid not in self._active_dynamic_sids:
            security = self._algorithm.add_security(
                symbol, self._minute_resolution, False, 2, False
            )
            self._active_dynamic_sids.add(sid)
            self._maximum_active_dynamic_security_count = max(
                self._maximum_active_dynamic_security_count,
                len(self._active_dynamic_sids),
            )
            if (
                len(self._active_dynamic_sids)
                > _base.MAXIMUM_ACTIVE_DYNAMIC_SECURITY_COUNT
            ):
                _error("bridge active minute-subscription cap exceeded")
        else:
            try:
                security = self._algorithm.securities[symbol]
            except KeyError as exc:
                raise AcceptedRiskSixUniverseOrderBridgeQcRuntimeError(
                    "bridge active subscription security is unavailable"
                ) from exc
        if sid not in self._configured_sids:
            self.configure_security(security)
        self._require_effective_two_x(security)
        return symbol, security

    def _observe_account(self, session):
        self._bridge_authority()
        cash = self._portfolio_cash()  # Exact nonnegative cash, before record.
        super()._observe_account(session)
        gross = self._gross_exposure_observations[session]
        if gross > MAXIMUM_REALIZED_GROSS_EXPOSURE:
            _error("bridge end-day actual gross exposure exceeds one")
        prior = self._bridge_cash_observations.get(session)
        if prior is not None and prior != cash:
            _error("bridge repeated end-day cash observation conflicts")
        self._bridge_cash_observations[session] = cash

    def _submit_market_on_open(self, symbol, signed_quantity, tag):
        self._require_initialized()
        try:
            security = self._algorithm.securities[symbol]
        except KeyError as exc:
            raise AcceptedRiskSixUniverseOrderBridgeQcRuntimeError(
                "bridge order security is unavailable"
            ) from exc
        self._require_effective_two_x(security)
        return super()._submit_market_on_open(symbol, signed_quantity, tag)

    def on_order_event(self, event):
        self._require_initialized()
        result = super().on_order_event(event)
        # LEAN's callback exposes a post-event portfolio state.  This checks
        # every observed event boundary, not an unobservable continuous path.
        cash = self._portfolio_cash()
        self._bridge_event_cash_count += 1
        if (
            self._bridge_event_cash_minimum is None
            or cash < self._bridge_event_cash_minimum
        ):
            self._bridge_event_cash_minimum = cash
        return result

    def _aggregate(self):
        self._require_initialized()
        aggregate = super()._aggregate()
        if (
            type(self._bridge_cash_observations) is not dict
            or tuple(sorted(self._bridge_cash_observations))
            != self._evaluation_sessions
            or any(type(value) is not Decimal or not value.is_finite()
                   or value < 0
                   for value in self._bridge_cash_observations.values())
        ):
            _error("bridge daily cash path is incomplete or invalid")
        minimum_cash = min(self._bridge_cash_observations.values())
        maximum_gross = _base._decimal(
            aggregate["maximum_gross_exposure"],
            "bridge maximum realized gross exposure",
            nonnegative=True,
        )
        execution = aggregate["execution"]
        if type(execution) is not dict:
            _error("bridge execution aggregate changed")
        mean_error = _base._decimal(
            execution.get("mean_target_weight_l1_error"),
            "bridge mean target-weight L1 error",
            nonnegative=True,
        )
        maximum_error = _base._decimal(
            execution.get("maximum_target_weight_l1_error"),
            "bridge maximum target-weight L1 error",
            nonnegative=True,
        )
        if execution.get("target_weight_l1_error_mark_basis") != (
            "prior_close_reference_prices_not_realized_open_prices"
        ):
            _error("bridge target-weight error mark basis changed")
        cash_valid = minimum_cash >= 0
        event_cash_valid = (
            type(self._bridge_event_cash_count) is int
            and self._bridge_event_cash_count >= 0
            and (
                self._bridge_event_cash_minimum is None
                if self._bridge_event_cash_count == 0
                else (
                    type(self._bridge_event_cash_minimum) is Decimal
                    and self._bridge_event_cash_minimum.is_finite()
                    and self._bridge_event_cash_minimum >= 0
                )
            )
        )
        if not event_cash_valid:
            _error("bridge order-event cash path is invalid")
        exposure_valid = maximum_gross <= MAXIMUM_REALIZED_GROSS_EXPOSURE
        tracking_valid = (
            mean_error <= MAXIMUM_MEAN_TARGET_WEIGHT_L1_ERROR
            and maximum_error <= MAXIMUM_SINGLE_TARGET_WEIGHT_L1_ERROR
        )
        aggregate.update({
            "schema": self._bridge_summary_schema(),
            "admission_leverage": "2",
            "target_gross_exposure": "0.98",
            "minimum_end_day_cash": _base._decimal_text(minimum_cash),
            "daily_cash_nonnegative": cash_valid,
            "order_event_cash_observation_count": self._bridge_event_cash_count,
            "minimum_observed_order_event_cash": (
                None if self._bridge_event_cash_minimum is None
                else _base._decimal_text(self._bridge_event_cash_minimum)
            ),
            "order_event_cash_nonnegative": event_cash_valid,
            "cash_observation_granularity": (
                "daily_close_and_post_order_event_not_continuous_intraday"
            ),
            "end_day_gross_at_most_one": exposure_valid,
            "target_tracking_valid": tracking_valid,
            "maximum_mean_target_weight_l1_error": "0.02",
            "maximum_single_target_weight_l1_error": "0.05",
            "run_valid": (
                aggregate["run_valid"] is True
                and cash_valid and event_cash_valid
                and exposure_valid and tracking_valid
            ),
        })
        return aggregate

    def on_end_of_algorithm(self):
        self._require_initialized()
        if self._algorithm.live_mode is not False:
            _error("bridge runtime is backtest-only")
        end_clock = self._algorithm.time
        if (
            end_clock.year != 2026
            or end_clock.month != 1
            or end_clock.day != 1
            or end_clock.hour != 0
            or end_clock.minute != 0
            or end_clock.second != 0
            or end_clock.microsecond != 0
        ):
            _error("bridge terminal clock is not the next midnight")
        aggregate = self._aggregate()
        meta = {
            "schema": _base.META_SCHEMA,
            "role": self._role,
            "profile_id": self._profile["profile_id"],
            "profile_sha256": self._profile["profile_sha256"],
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": (
                self._package.activation_manifest_sha256
            ),
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "aggregate_schema": aggregate["schema"],
            "aggregate_sha256": _base._sha(aggregate),
            "result_transport": "two_bounded_custom_summary_statistics",
            "raw_provider_rows": False,
            "raw_price_rows": False,
            "raw_order_rows": False,
            "preliminary": True,
            "formal": False,
            "backtest_only": True,
            "trading": False,
        }
        statistics = {
            META_STATISTIC_NAME: _base._canonical(meta).decode("ascii"),
            AGGREGATES_STATISTIC_NAME: (
                _base._canonical(aggregate).decode("ascii")
            ),
        }
        if tuple(sorted(statistics)) != self._bridge_expected_statistic_names():
            _error("bridge statistic inventory changed")
        if any(
            len(name) > 64
            or len(value.encode("ascii")) > MAXIMUM_STATISTIC_BYTES
            for name, value in statistics.items()
        ):
            _error("bridge statistic exceeded its transport bound")
        try:
            for name, value in sorted(statistics.items()):
                self._algorithm.set_summary_statistic(name, value)
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderBridgeQcRuntimeError(
                "bridge aggregate emission failed"
            ) from exc
        self._emitted = True
        self._completed = True
        return aggregate


class AcceptedRiskSixUniverseOrderBridgeQcDriver(
    BridgeAdmissionMixin, _base.AcceptedRiskSixUniverseOrderQcDriver
):
    """Exact A3 cap-90 role with permission bridge and no target leverage."""

    def __init__(
        self, algorithm, *, role, variant=BRIDGE_VARIANT, **kwargs
    ):
        if (
            type(role) is not str
            or role not in _targets.ROLES
            or type(variant) is not str
            or variant != BRIDGE_VARIANT
        ):
            _error("bridge runtime role or variant is not frozen")
        super().__init__(
            algorithm, role=role, variant=_base.CAP90_VARIANT, **kwargs
        )
        self._bridge_role = role
        self._bridge_profile = None
        self._bridge_builder = None
        self._bridge_cash_observations = {}
        self._bridge_event_cash_minimum = None
        self._bridge_event_cash_count = 0
        self._bridge_initialized = False


__all__ = (
    "ADMISSION_LEVERAGE",
    "AGGREGATES_STATISTIC_NAME",
    "AcceptedRiskSixUniverseOrderBridgeQcDriver",
    "AcceptedRiskSixUniverseOrderBridgeQcRuntimeError",
    "BRIDGE_PROFILE_SCHEMA",
    "BRIDGE_SUMMARY_SCHEMA",
    "BRIDGE_VARIANT",
    "BridgeAdmissionMixin",
    "MAXIMUM_MEAN_TARGET_WEIGHT_L1_ERROR",
    "MAXIMUM_SINGLE_TARGET_WEIGHT_L1_ERROR",
    "MAXIMUM_STATISTIC_BYTES",
    "META_STATISTIC_NAME",
    "expected_bridge_custom_statistic_names",
    "require_bridge_profile",
)
