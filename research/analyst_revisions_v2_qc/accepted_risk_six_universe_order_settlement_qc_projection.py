"""Separate settlement-cash projections of the exact R182 and R186 sources.

The stock targets, data lineage, 98% gross target, fees, and order cadence are
unchanged. Only the order lifecycle, bridge cash policy, profile/schema, and
entry-point variant differ. No cloud or result access occurs on import.
"""

import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_bridge_qc_projection as _r182
from . import accepted_risk_six_universe_order_tilt80_qc_projection as _r186
from . import accepted_risk_six_universe_order_bridge_qc_runtime as _bridge
from . import accepted_risk_six_universe_order_targets as _targets


class SixUniverseSettlementQcProjectionError(ValueError):
    """The exact predecessor or settlement-cash projection changed."""


PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-settlement-v1"
SETTLEMENT_POLICY_ID = "pending_sell_moo_signed_cash_settled_nonnegative_v1"
BRIDGE_VARIANT = "cap90_admission_settlement_v1"
BRIDGE_PROFILE_SCHEMA = "arv2-six-universe-order-admission-settlement-profile-v1"
BRIDGE_SUMMARY_SCHEMA = "arv2-six-universe-order-admission-settlement-summary-v1"
TILT_VARIANT = "cap90_matched_revision_tilt80_settlement_v1"
TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt80-settlement-profile-v1"
TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt80-settlement-summary-v1"

_PREDECESSOR = {
    "R191": ("186cb2bb3dbd2a37358c9c0b2dbfa86e1e685203dba33795eb192f74faa9feeb",
             "b419d3f2b149a1509ef09bd0a5bf607bea8c25a3363cbc8a9dc04a40910f9c0c", 14),
    "R192": (_r186.PINNED_TILT80_PROJECTION_SHA256,
             _r186.PINNED_TILT80_PROFILE_SHA256, 16),
}

# Filled only after the entire projected source/profile has been reviewed.
CANDIDATES = {
    "R191": {
        "role": _targets.ROLE_MATCHED, "variant": BRIDGE_VARIANT,
        "summary_schema": BRIDGE_SUMMARY_SCHEMA,
        "profile_schema": BRIDGE_PROFILE_SCHEMA,
        "projection_sha256": "883fc448d6b5a3f7800921988a174995ad233e0c8eab5434f6b18874b189a5bb",
        "profile_sha256": "f650044a704a4a0522e4c95c065a3eda3d3de22e8c5425579e04155c88f5220c",
        "source_files_sha256": "5bf0cdc32148d84105256da5c818c1d023ee996b27a014302fe7c250ad1f9f73",
        "total_source_byte_count": 397120, "source_file_count": 14,
    },
    "R192": {
        "role": _r186.TILT80_ROLE, "variant": TILT_VARIANT,
        "summary_schema": TILT_SUMMARY_SCHEMA,
        "profile_schema": TILT_PROFILE_SCHEMA,
        "projection_sha256": "8f5db5bf895a51683d9c7c2a4848c302aeac01284317ceaab9e22d9c9b3c3b09",
        "profile_sha256": "2c149ea159473f7976f10daa5ad74b0a3f8d0bf6992911e96a58b3a7a490f923",
        "source_files_sha256": "023707c5709525247ac88384e5ea356655ef5501fb7f07e19b158642456224ae",
        "total_source_byte_count": 425742, "source_file_count": 16,
    },
}


def _error(message):
    raise SixUniverseSettlementQcProjectionError(message)


def _replace_exact(source, old, new, count=1):
    if type(source) is not str or source.count(old) != count or old == new:
        _error("settlement source lost an exact replacement point")
    return source.replace(old, new, count)


def _core_source(source):
    source = _replace_exact(
        source,
        "                    if proposed_cash < 0:\n"
        "                        raise OrderLevelBacktestError(MARGIN_REFUSAL)\n",
        "                    if proposed_cash < 0 and not any(\n"
        "                        other.side == SELL and\n"
        "                        state[order_id][\"status\"] not in TERMINAL_STATUSES\n"
        "                        for order_id, other in intents.items()\n"
        "                    ):\n"
        "                        raise OrderLevelBacktestError(MARGIN_REFUSAL)\n",
    )
    return _replace_exact(
        source,
        "            raise OrderLevelBacktestError(INCOMPLETE_LIFECYCLE_REFUSAL)\n\n"
        "        final_equity = cash + sum(\n",
        "            raise OrderLevelBacktestError(INCOMPLETE_LIFECYCLE_REFUSAL)\n"
        "        if cash < 0:\n"
        "            raise OrderLevelBacktestError(MARGIN_REFUSAL)\n\n"
        "        final_equity = cash + sum(\n",
    )


def _bridge_source(source):
    source = _replace_exact(
        source,
        '"""Prospective R-181 A3 buying-power admission bridge, for QC backtests only.\n\n'
        'This is a *permission* for LEAN to admit simultaneous pre-open sell and buy\n'
        'MOO tickets, not a 2x portfolio target.  The six-universe construction and\n'
        '98% long-only target are unchanged.  Every actual security is configured for\n'
        '2x buying power, while cash, end-day exposure, and executed target tracking\n'
        'must pass separate, explicit validity gates.  Neither this module nor a\n'
        'terminal QC ``Completed`` status makes an invalid order run valid.\n"""',
        '"""Backtest-only 2x admission with signed, pending-SELL cash settlement.\n\n'
        'The portfolio target remains 98% long-only and settled cash must be\n'
        'nonnegative. A QC Completed status alone is not a valid result.\n"""',
    )
    for old, new in (
        ('BRIDGE_VARIANT = "cap90_admission_bridge_v1"',
         f'BRIDGE_VARIANT = "{BRIDGE_VARIANT}"'),
        ('BRIDGE_PROFILE_SCHEMA = "arv2-six-universe-order-admission-bridge-profile-v1"',
         f'BRIDGE_PROFILE_SCHEMA = "{BRIDGE_PROFILE_SCHEMA}"'),
        ('BRIDGE_SUMMARY_SCHEMA = "arv2-six-universe-order-admission-bridge-summary-v1"',
         f'BRIDGE_SUMMARY_SCHEMA = "{BRIDGE_SUMMARY_SCHEMA}"'),
        ('"-cap90-admission-bridge-v1"', '"-cap90-admission-settlement-v1"'),
        ('"realized_borrowing_allowed": False,',
         '"transient_pending_sell_cash_deficit_allowed": True,\n'
         '        "settled_cash_nonnegative_required": True,\n'
         f'        "event_cash_policy_id": "{SETTLEMENT_POLICY_ID}",'),
        ('"daily_cash_nonnegative_and_end_day_gross_at_most_one_"',
         '"pending_sell_only_negative_event_cash_and_settled_cash_nonnegative_"\n'
         '            "and_daily_cash_nonnegative_and_end_day_gross_at_most_one_"'),
    ):
        source = _replace_exact(source, old, new)
    source = _replace_exact(
        source,
        "        self._bridge_event_cash_count = 0\n",
        "        self._bridge_event_cash_count = 0\n"
        "        self._bridge_sell_moo_ids = {}\n"
        "        self._bridge_negative_event_count = 0\n"
        "        self._bridge_unexplained_negative_count = 0\n",
        2,
    )
    source = _replace_exact(
        source,
        "        return super()._submit_market_on_open(symbol, signed_quantity, tag)\n\n"
        "    def on_order_event(self, event):\n",
        "        if type(signed_quantity) is not int or signed_quantity == 0:\n"
        "            _error(\"bridge MOO quantity changed\")\n"
        "        ticket = super()._submit_market_on_open(symbol, signed_quantity, tag)\n"
        "        order_id = ticket.order_id\n"
        "        if type(order_id) is not int or order_id <= 0:\n"
        "            _error(\"bridge MOO id changed\")\n"
        "        if signed_quantity < 0:\n"
        "            self._bridge_sell_moo_ids[order_id] = self._algorithm.time.date()\n"
        "        return ticket\n\n"
        "    def _bridge_pending_sell_moo(self):\n"
        "        try:\n"
        "            open_ids = {order.id for order in self._algorithm.transactions.get_open_orders()}\n"
        "        except Exception as exc:\n"
        "            raise AcceptedRiskSixUniverseOrderBridgeQcRuntimeError(\n"
        "                \"bridge open SELL MOO inventory unavailable\"\n"
        "            ) from exc\n"
        "        if any(type(order_id) is not int for order_id in open_ids):\n"
        "            _error(\"bridge open SELL MOO id changed\")\n"
        "        self._bridge_sell_moo_ids = {\n"
        "            order_id: session for order_id, session in self._bridge_sell_moo_ids.items()\n"
        "            if order_id in open_ids\n"
        "        }\n"
        "        return any(session == self._algorithm.time.date()\n"
        "                   for session in self._bridge_sell_moo_ids.values())\n\n"
        "    def on_order_event(self, event):\n",
    )
    source = _replace_exact(
        source,
        "        cash = self._portfolio_cash()\n"
        "        self._bridge_event_cash_count += 1\n",
        "        if (event.order_id in self._bridge_sell_moo_ids and\n"
        "                self._executor._status_text(event.status) in\n"
        "                (\"Filled\", \"Canceled\", \"Invalid\")):\n"
        "            self._bridge_sell_moo_ids.pop(event.order_id)\n"
        "        cash = _base._decimal(self._algorithm.portfolio.cash,\n"
        "                              \"bridge signed order-event cash\")\n"
        "        if cash < 0:\n"
        "            if not self._bridge_pending_sell_moo():\n"
        "                self._bridge_unexplained_negative_count += 1\n"
        "                _error(\"bridge negative cash has no pending SELL MOO\")\n"
        "            self._bridge_negative_event_count += 1\n"
        "        self._bridge_event_cash_count += 1\n",
    )
    source = _replace_exact(
        source,
        "                    and self._bridge_event_cash_minimum.is_finite()\n"
        "                    and self._bridge_event_cash_minimum >= 0\n",
        "                    and self._bridge_event_cash_minimum.is_finite()\n",
    )
    source = _replace_exact(
        source,
        "        if not event_cash_valid:\n"
        "            _error(\"bridge order-event cash path is invalid\")\n",
        "        event_cash_valid = (\n"
        "            event_cash_valid and self._bridge_unexplained_negative_count == 0\n"
        "            and 0 <= self._bridge_negative_event_count <= self._bridge_event_cash_count\n"
        "            and ((self._bridge_event_cash_minimum is not None\n"
        "                  and self._bridge_event_cash_minimum < 0)\n"
        "                 is (self._bridge_negative_event_count > 0))\n"
        "            and not self._bridge_pending_sell_moo()\n"
        "        )\n"
        "        if not event_cash_valid:\n"
        "            _error(\"bridge order-event settlement cash path is invalid\")\n",
    )
    return _replace_exact(
        source,
        '            "order_event_cash_nonnegative": event_cash_valid,\n',
        '            "transient_negative_order_event_count": self._bridge_negative_event_count,\n'
        '            "unexplained_negative_order_event_count": self._bridge_unexplained_negative_count,\n'
        '            "negative_cash_requires_pending_sell_moo": True,\n'
        '            "settled_cash_nonnegative": True,\n',
    )


def _tilt_source(source, matched_profile_sha256):
    for old, new in (
        ('TILT_VARIANT = "cap90_matched_revision_tilt80_admission_bridge_v1"',
         f'TILT_VARIANT = "{TILT_VARIANT}"'),
        ('TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt80-bridge-profile-v1"',
         f'TILT_PROFILE_SCHEMA = "{TILT_PROFILE_SCHEMA}"'),
        ('TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt80-bridge-summary-v1"',
         f'TILT_SUMMARY_SCHEMA = "{TILT_SUMMARY_SCHEMA}"'),
        ('"b419d3f2b149a1509ef09bd0a5bf607bea8c25a3363cbc8a9dc04a40910f9c0c"',
         f'"{matched_profile_sha256}"'),
        ('"arv2-six-universe-order-matched-revision-tilt80-bridge-v1"',
         '"arv2-six-universe-order-matched-revision-tilt80-settlement-v1"'),
    ):
        source = _replace_exact(source, old, new)
    return _replace_exact(
        source,
        "        self._bridge_event_cash_count = 0\n"
        "        self._bridge_initialized = True\n",
        "        self._bridge_event_cash_count = 0\n"
        "        self._bridge_sell_moo_ids = {}\n"
        "        self._bridge_negative_event_count = 0\n"
        "        self._bridge_unexplained_negative_count = 0\n"
        "        self._bridge_initialized = True\n",
    )


def _render_profile(candidate_id):
    if candidate_id not in CANDIDATES:
        _error("settlement candidate is not frozen")
    predecessor = (_bridge.require_bridge_profile(_targets.ROLE_MATCHED)
                   if candidate_id == "R191" else _r186.require_tilt80_profile())
    if predecessor["profile_sha256"] != _PREDECESSOR[candidate_id][1]:
        _error("settlement predecessor profile changed")
    seed = {key: value for key, value in predecessor.items()
            if key not in ("profile_sha256", "realized_borrowing_allowed")}
    seed.update({
        "schema": CANDIDATES[candidate_id]["profile_schema"],
        "profile_id": ("arv2-six-universe-order-matched-cap90-admission-settlement-v1"
                       if candidate_id == "R191" else
                       "arv2-six-universe-order-matched-revision-tilt80-settlement-v1"),
        "transient_pending_sell_cash_deficit_allowed": True,
        "settled_cash_nonnegative_required": True,
        "event_cash_policy_id": SETTLEMENT_POLICY_ID,
        "execution_validity_rule": (
            "all_orders_terminal_no_invalid_or_canceled_and_"
            "pending_sell_only_negative_event_cash_and_settled_cash_nonnegative_"
            "and_daily_cash_nonnegative_and_end_day_gross_at_most_one_"
            "and_target_l1_within_both_bounds"
        ),
    })
    if candidate_id == "R192":
        matched = _render_profile("R191")
        seed["matched_baseline_profile_sha256"] = matched["profile_sha256"]
    return json.loads(_base._canonical({
        **seed, "profile_sha256": hashlib.sha256(_base._canonical(seed)).hexdigest(),
    }).decode("ascii"))


def require_settlement_profile(candidate_id):
    profile = _render_profile(candidate_id)
    if profile["profile_sha256"] != CANDIDATES[candidate_id]["profile_sha256"]:
        _error("settlement profile changed from exact pin")
    return profile


def _build_unpinned(delta_package, candidate_id):
    if candidate_id not in CANDIDATES:
        _error("settlement candidate is not frozen")
    old = (_r182.build_accepted_risk_six_universe_order_bridge_qc_projection(
        delta_package, role=_targets.ROLE_MATCHED)
        if candidate_id == "R191" else
        _r186.build_accepted_risk_six_universe_order_tilt80_qc_projection(delta_package))
    if (old.projection_sha256, old.profile_sha256, len(old.source_files)) != _PREDECESSOR[candidate_id]:
        _error("settlement predecessor source changed")
    profile = _render_profile(candidate_id)
    matched_profile = _render_profile("R191")
    files = []
    for item in old.source_files:
        source = item.source_bytes.decode("ascii")
        if item.content_sha256 != hashlib.sha256(item.source_bytes).hexdigest():
            _error("settlement predecessor file changed")
        if item.project_path == "accepted_risk_order_level_core.py":
            source = _core_source(source)
        elif item.project_path == "accepted_risk_six_universe_order_bridge_qc_runtime.py":
            source = _bridge_source(source)
        elif item.project_path == "accepted_risk_six_universe_order_tilt_qc_runtime.py":
            source = _tilt_source(source, matched_profile["profile_sha256"])
        elif item.project_path == "main.py":
            old_variant = (_bridge.BRIDGE_VARIANT if candidate_id == "R191"
                           else _r186.TILT80_VARIANT)
            source = _replace_exact(source, f"variant='{old_variant}',",
                                    f"variant='{CANDIDATES[candidate_id]['variant']}',")
        files.append(_base._source_file(item.project_path, source.encode("ascii")))
    files.sort(key=lambda item: item.project_path)
    for item in files:
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"),
                item.project_path, "exec")
    total = sum(item.byte_count for item in files)
    if (len(files) != CANDIDATES[candidate_id]["source_file_count"]
            or len({item.project_path for item in files}) != len(files)
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _error("settlement QC source closure or budget changed")
    semantic = {key: value for key, value in old.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    semantic.update({
        "schema": PROJECTION_SCHEMA,
        "variant": CANDIDATES[candidate_id]["variant"],
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        old, schema=PROJECTION_SCHEMA,
        projection_id="arv2-six-universe-order-settlement-qc-projection-" + digest[:24],
        projection_sha256=digest, variant=CANDIDATES[candidate_id]["variant"],
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=tuple(files), total_source_byte_count=total,
    )
    if {key: item for key, item in value.to_record().items()
            if key not in ("projection_id", "projection_sha256")} != semantic:
        _error("settlement QC projection failed self-authentication")
    return value


def build_settlement_projection(delta_package, candidate_id):
    value = _build_unpinned(delta_package, candidate_id)
    spec = CANDIDATES[candidate_id]
    source_manifest = hashlib.sha256(_base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in value.source_files
    ))).hexdigest()
    if (value.projection_sha256 != spec["projection_sha256"]
            or value.profile_sha256 != spec["profile_sha256"]
            or source_manifest != spec["source_files_sha256"]
            or value.total_source_byte_count != spec["total_source_byte_count"]):
        _error("settlement QC source/profile/manifest changed from exact pin")
    return value


__all__ = (
    "BRIDGE_SUMMARY_SCHEMA", "BRIDGE_VARIANT", "CANDIDATES",
    "PROJECTION_SCHEMA", "SETTLEMENT_POLICY_ID", "TILT_SUMMARY_SCHEMA",
    "TILT_VARIANT", "SixUniverseSettlementQcProjectionError",
    "build_settlement_projection", "require_settlement_profile",
)
