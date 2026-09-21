"""V12-only wrapper for authenticated LEAN delisting liquidations.

V4--V11 remain byte-identical in the legacy runtime.  This module maps each
V12 profile to its V11 execution behavior, then adds only the narrow engine
forced-exit boundary and separate redacted accounting required by V12.
"""

from decimal import Decimal

try:
    import accepted_risk_order_level_core as _orders
    import accepted_risk_order_level_forced_exit as _forced_exit
    import accepted_risk_qqq_order_level_qc_runtime as _base
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_core as _orders,
        accepted_risk_order_level_forced_exit as _forced_exit,
        accepted_risk_qqq_order_level_qc_runtime as _base,
    )


AcceptedRiskQqqOrderLevelQcRuntimeError = (
    _base.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


FORCED_EXIT_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v12"
FORCED_EXIT_SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v8"
FORCED_EXIT_PROFILE_IDS = tuple(
    "arv2-qqq-order-level-tilt-" + str(year) + "-cutoff-v12"
    for year in (2025, 2026)
)
(
    FORCED_EXIT_PROFILE_2025_ID,
    FORCED_EXIT_PROFILE_2026_ID,
) = FORCED_EXIT_PROFILE_IDS

STARTING_CASH = _base.STARTING_CASH
META_STATISTIC_NAME = _base.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _base.AGGREGATES_STATISTIC_NAME

_V11_PROFILE_BY_V12 = {
    FORCED_EXIT_PROFILE_2025_ID: _base.REFLECTED_TICKET_PROFILE_2025_ID,
    FORCED_EXIT_PROFILE_2026_ID: _base.REFLECTED_TICKET_PROFILE_2026_ID,
}


def _v12_profile(profile_id):
    legacy_id = _V11_PROFILE_BY_V12.get(profile_id)
    if legacy_id is None:
        raise _Refusal(
            "QQQ order-level V12 profile is not an exact fixed profile"
        )
    record = _base.require_qqq_order_level_profile(legacy_id)
    record.pop("profile_sha256")
    record.update({
        "schema": FORCED_EXIT_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "engine_forced_delisting_policy": (
            "accept_only_exact_LEAN_direct_Filled_Liquidate_from_delisting_"
            "for_exact_authenticated_delisted_security"
        ),
        "forced_delisting_quantity_authority": (
            "terminal_active_or_frozen_preopen_plan_else_exact_engine_order_"
            "fill_with_postfill_zero"
        ),
        "pending_preopen_forced_delisting_policy": (
            "invalidate_entire_frozen_rebalance_never_rewrite_or_reweight"
        ),
        "forced_delisting_accounting": (
            "separate_redacted_engine_ledger_strategy_order_ledger_unchanged"
        ),
    })
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _v12_profile(profile_id)
    for profile_id in FORCED_EXIT_PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level V12 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


def _nonzero_quantities(values):
    return {
        security_id: quantity
        for security_id, quantity in values.items()
        if quantity != 0
    }


class AcceptedRiskQqqOrderLevelV12QcRuntime(
    _base.AcceptedRiskQqqOrderLevelQcRuntime
):
    """Run V11 behavior plus one exact, fail-closed delisting exit path."""

    def __init__(self, algorithm, *, profile_id, **kwargs):
        profile = require_qqq_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V11_PROFILE_BY_V12[profile_id],
            **kwargs,
        )
        self._profile = profile
        self._forced_delisting_ledger = (
            _forced_exit.empty_forced_delisting_ledger()
        )
        self._forced_exit_invalidated_pending_plan_count = 0

    @staticmethod
    def _quantities_after_strategy_events(plan, events):
        try:
            _orders.summarize_order_lifecycle(
                plan, events, require_all_terminal=True,
            )
        except _orders.OrderLevelBacktestError as exc:
            raise _Refusal(str(exc)) from exc
        intents = {
            intent.client_order_id: intent for intent in plan.intents
        }
        quantities = dict(plan.starting_quantities)
        seen = set()
        for event in events:
            if event.event_id in seen:
                continue
            seen.add(event.event_id)
            if event.status not in _orders.FILL_STATUSES:
                continue
            intent = intents[event.client_order_id]
            delta = (
                -event.fill_quantity
                if intent.side == "SELL" else event.fill_quantity
            )
            quantities[intent.security_id] = (
                quantities.get(intent.security_id, 0) + delta
            )
        return _nonzero_quantities(quantities)

    def _forced_exit_quantity_state(self, security_id, signed_quantity):
        if self._open_plan is not None and self._pending_preopen is not None:
            raise _Refusal(
                "order-level open and pending rebalance states overlap"
            )
        if self._open_plan is not None:
            quantity_authority_available = True
            quantities = self._quantities_after_strategy_events(
                self._open_plan, tuple(self._open_plan_events)
            )
        elif self._pending_preopen is not None:
            quantity_authority_available = True
            quantities = _nonzero_quantities(
                dict(self._pending_preopen[1].starting_quantities)
            )
        else:
            quantity_authority_available = False
            quantities = {}
        maximum = quantities.get(security_id, 0)
        if not quantity_authority_available:
            absolute = -signed_quantity
            maximum = (
                int(absolute)
                if absolute.is_finite()
                and absolute > 0
                and absolute == absolute.to_integral_value()
                else 0
            )
        if type(maximum) is not int or maximum <= 0:
            maximum = 0
        return maximum, quantities

    def _record_forced_delisting_exit(
        self, event, engine_order, order_id, event_id, status,
    ):
        unknown = _forced_exit.UNKNOWN_ORDER_REFUSAL
        try:
            event_symbol = event.symbol
            event_message = event.message
            engine_order_id = engine_order.id
            engine_order_symbol = engine_order.symbol
            engine_order_tag = engine_order.tag
            engine_order_quantity = engine_order.quantity
            security = self._algorithm.securities[event_symbol]
            portfolio_quantity = self._algorithm.portfolio[event_symbol].quantity
            is_delisted = security.is_delisted
        except (AttributeError, KeyError, TypeError) as exc:
            raise _Refusal(unknown) from exc
        try:
            event_sid = _base._symbol_sid(
                event_symbol, "order-level forced exit event"
            )
            canonical_id = self._resolution.security_for_qc_sid(event_sid)
            canonical_symbol = self._resolution.symbol_for_security(canonical_id)
            identities_match = (
                type(engine_order_id) is int
                and engine_order_id == order_id
                and _base._symbol_sid(
                    engine_order_symbol, "order-level forced exit order"
                ) == event_sid
                and _base._symbol_sid(
                    security.symbol, "order-level forced exit security"
                ) == event_sid
                and _base._symbol_sid(
                    canonical_symbol, "order-level forced exit canonical"
                ) == event_sid
                and event_sid in self._configured_security_ids
                and is_delisted is True
            )
        except Exception as exc:
            raise _Refusal(unknown) from exc
        if not identities_match:
            raise _Refusal(unknown)
        signed_quantity = _base._decimal(
            event.fill_quantity,
            "order-level forced delisting signed fill quantity",
        )
        if _base._decimal(
            engine_order_quantity,
            "order-level forced delisting order quantity",
        ) != signed_quantity:
            raise _Refusal(
                "order-level forced delisting order quantity changed"
            )
        if _base._decimal(
            portfolio_quantity,
            "order-level forced delisting post-fill portfolio quantity",
            nonnegative=True,
        ) != 0:
            raise _Refusal(
                "order-level forced delisting portfolio quantity is not exact zero"
            )
        fill_price = _base._decimal(
            event.fill_price,
            "order-level forced delisting fill price",
        )
        try:
            fee_value = event.order_fee.value
            fee_amount = _base._decimal(
                fee_value.amount,
                "order-level forced delisting fee amount",
            )
            fee_currency = fee_value.currency
        except AttributeError as exc:
            raise _Refusal(
                "order-level forced delisting fee is unreadable"
            ) from exc
        maximum, _quantities = self._forced_exit_quantity_state(
            canonical_id, signed_quantity
        )
        try:
            candidate = _forced_exit.record_forced_delisting_fill(
                self._forced_delisting_ledger,
                authenticated_delisted_security_ids=frozenset({canonical_id}),
                security_id=canonical_id,
                order_id=order_id,
                event_id=event_id,
                event_message=event_message,
                order_tag=engine_order_tag,
                status=status,
                maximum_sale_quantity=maximum,
                signed_fill_quantity=signed_quantity,
                fill_price=fill_price,
                fee_amount=fee_amount,
                fee_currency=fee_currency,
            )
        except _forced_exit.ForcedDelistingError as exc:
            raise _Refusal(str(exc)) from exc

        had_pending = self._pending_preopen is not None
        if self._open_plan is not None:
            self._close_open_plan()
        self._forced_delisting_ledger = candidate
        if had_pending:
            self._pending_preopen = None
            self._forced_exit_invalidated_pending_plan_count += 1

    def on_order_event(self, event, engine_order=None):
        if self._pending_submission_events is not None:
            return super().on_order_event(event)
        try:
            order_id = event.order_id
        except Exception:
            return super().on_order_event(event)
        if order_id in self._open_order_ids:
            return super().on_order_event(event)
        try:
            event_id = event.id
            status = self._order_status_text(event.status)
        except Exception as exc:
            raise _Refusal("order-level QC event is unreadable") from exc
        if type(order_id) is not int or order_id < 0:
            raise _Refusal("order-level QC event order identity changed")
        if type(event_id) is not int or event_id < 0:
            raise _Refusal("order-level QC event identity changed")
        return self._record_forced_delisting_exit(
            event, engine_order, order_id, event_id, status,
        )

    def _aggregate_record(self):
        summary = super()._aggregate_record()
        forced = _forced_exit.forced_delisting_summary(
            self._forced_delisting_ledger
        )
        summary.update({
            "schema": FORCED_EXIT_SUMMARY_SCHEMA,
            "engine_forced_delisting": forced,
            "forced_exit_invalidated_pending_rebalance_count": (
                self._forced_exit_invalidated_pending_plan_count
            ),
            "run_valid": (
                not summary["execution_failure"]
                and summary["skipped_unpriced_decision_count"] == 0
                and (
                    summary["completed_rebalance_count"]
                    + self._forced_exit_invalidated_pending_plan_count
                    == summary["decision_count"]
                )
                and forced["accounting_complete"] is True
            ),
        })
        return summary

    def on_end_of_algorithm(self):
        if not self._initialized or self._completed:
            raise _Refusal(
                "order-level end callback escaped runtime state"
            )
        if self._pending_preopen is not None:
            raise _Refusal(
                "order-level pending preopen submission remained at end"
            )
        if (
            self._algorithm.time.date().isoformat()
            != _base.FINAL_EXECUTION_SESSION
        ):
            raise _Refusal(
                "order-level backtest ended outside the exact final session"
            )
        self._close_open_plan()
        if self._decision_count != len(self._decision_sessions):
            raise _Refusal(
                "order-level decision schedule did not complete"
            )
        aggregates = self._aggregate_record()
        aggregates_sha256 = _base._sha(aggregates)
        meta = {
            "schema": "arv2-qqq-order-level-tilt-runtime-meta-v2",
            "profile_id": self._profile["profile_id"],
            "profile_sha256": self._profile["profile_sha256"],
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": (
                self._package.activation_manifest_sha256
            ),
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "score_source_view_id": _base._score.PRIMARY_SOURCE_VIEW_ID,
            "aggregates_sha256": aggregates_sha256,
            "result_transport": "aggregate_only_custom_summary_statistics",
            "backtest_only": True,
            "simulated_order_submission": True,
            "live_orders": False,
            "paper_orders": False,
            "funded_orders": False,
            "deployment": False,
            "trading": False,
        }
        statistics = {
            META_STATISTIC_NAME: _base._canonical(meta).decode("ascii"),
            AGGREGATES_STATISTIC_NAME: (
                _base._canonical(aggregates).decode("ascii")
            ),
        }
        if (
            tuple(sorted(statistics))
            != expected_custom_summary_statistic_names(
                self._profile["profile_id"]
            )
            or any(
                len(key) > 64
                or len(value.encode("ascii"))
                > _base.MAXIMUM_STATISTIC_BYTES
                for key, value in statistics.items()
            )
        ):
            raise _Refusal(
                "order-level aggregate transport exceeded its exact bound"
            )
        for key, value in sorted(statistics.items()):
            self._algorithm.set_summary_statistic(key, value)
        self._completed = True

__all__ = (
    "AGGREGATES_STATISTIC_NAME",
    "AcceptedRiskQqqOrderLevelQcRuntimeError",
    "AcceptedRiskQqqOrderLevelV12QcRuntime",
    "FORCED_EXIT_PROFILE_2025_ID",
    "FORCED_EXIT_PROFILE_2026_ID",
    "FORCED_EXIT_PROFILE_IDS",
    "FORCED_EXIT_PROFILE_SCHEMA",
    "FORCED_EXIT_SUMMARY_SCHEMA",
    "META_STATISTIC_NAME",
    "STARTING_CASH",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
