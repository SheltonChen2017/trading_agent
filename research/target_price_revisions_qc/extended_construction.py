"""Pure construction/basis contracts for the owner-authorized extended study.

The unchanged cap helper owns selection and exact tilt economics. Known
warning/final-stage selected names lose their existing slots BEFORE scoring;
rank eleven is never promoted and unavailable slots remain cash. OFF has no
signal argument. This module never opens sources or authenticates providers.

The basis contract validates explicitly supplied interval/identity/hash claims,
not native source truth. An independently verified native producer and actual
runtime integration are still required. A missing factor or merely observing
no split event cannot establish factor one. This interval covers RAW mark to
decision share units, NOT like-for-like analyst target units or canonical TPR.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re

from . import cap_tilt

MAX_IDENTITIES = 4096
BASIS_SCHEMA = "tpr-extended-share-basis-evidence-v1"
BASIS_SCOPE = "prior-raw-mark-to-decision-share-basis"
BASIS_DIRECTION = "prior-raw-price-times-factor-to-decision-share-units"
BASIS_PROVENANCE = frozenset({"native-factor-file-ratio", "complete-native-action-interval"})
_BASIS_KEYS = frozenset({"schema", "scope", "state", "security_id", "mark_utc",
    "cutoff_utc", "decision_utc", "received_utc", "price_multiplier",
    "prior_factor", "current_factor", "direction",
    "source_sha256", "provenance"})


class ConstructionError(ValueError):
    """Fixed, source-value-free refusal; no execution authority is granted."""


def _refuse():
    raise ConstructionError("invalid bounded extended construction or known basis")


def _sid(value):
    if (type(value) is not str or not 0 < len(value) <= 128 or value.strip() != value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        _refuse()
    return value


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _refuse()
    return value


def _clock(value):
    if type(value) is not str or not 0 < len(value) <= 64:
        _refuse()
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            _refuse()
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        _refuse()


def _factor_number(value):
    if type(value) is str:
        if not 0 < len(value) <= 128:
            _refuse()
        try:
            represented = Decimal(value)
        except InvalidOperation:
            _refuse()
        parts = represented.as_tuple()
        if (not represented.is_finite() or len(parts.digits) > 64
                or not -128 <= parts.exponent <= 128):
            _refuse()
    elif type(value) is int:
        if value.bit_length() > 128:
            _refuse()
    elif type(value) is Fraction:
        if max(value.numerator.bit_length(), value.denominator.bit_length()) > 512:
            _refuse()
    elif type(value) is Decimal:
        parts = value.as_tuple()
        if not value.is_finite() or len(parts.digits) > 64 or not -128 <= parts.exponent <= 128:
            _refuse()
    else:
        _refuse()
    try:
        number = cap_tilt._exact_number(value)
    except cap_tilt.CapTiltError:
        _refuse()
    if not 0 < number <= 10**30 or max(number.numerator.bit_length(), number.denominator.bit_length()) > 512:
        _refuse()
    return number


def known_basis_factor(evidence, *, security_id, mark_utc, cutoff_utc,
                       decision_utc, source_sha256):
    """Return an exact affirmed price multiplier or refuse; never default one.

    All expected clocks/identity/source hash come from the caller's separately
    verified frozen inputs. The source must affirm the ENTIRE mark-to-decision
    interval and multiplier direction. The multiplier is prior/current native
    factors, never their inverse. Positive ratio equality catches reversed
    or mismatched representations; it is not authentication of native ratio
    orientation. ``received_utc`` must lie from the prior cutoff through the
    decision, with no stale/future interval. There is no implied carry-forward.
    """
    sid, expected_hash = _sid(security_id), _hash(source_sha256)
    mark, cutoff, decision = map(_clock, (mark_utc, cutoff_utc, decision_utc))
    if not mark <= cutoff < decision:
        _refuse()
    if type(evidence) is not dict or set(evidence) != _BASIS_KEYS:
        _refuse()
    if (evidence["schema"] != BASIS_SCHEMA or evidence["scope"] != BASIS_SCOPE
            or evidence["state"] != "known" or evidence["security_id"] != sid
            or evidence["direction"] != BASIS_DIRECTION
            or type(evidence["provenance"]) is not str
            or evidence["provenance"] not in BASIS_PROVENANCE
            or _hash(evidence["source_sha256"]) != expected_hash):
        _refuse()
    observed = tuple(_clock(evidence[key]) for key in ("mark_utc", "cutoff_utc", "decision_utc"))
    if observed != (mark, cutoff, decision):
        _refuse()
    received = _clock(evidence["received_utc"])
    if not cutoff <= received <= decision:
        _refuse()
    prior, current, factor = map(_factor_number,
        (evidence["prior_factor"], evidence["current_factor"], evidence["price_multiplier"]))
    if factor != prior / current:
        _refuse()
    return factor


def _id_inventory(values):
    if type(values) not in (list, tuple, set, frozenset) or len(values) > MAX_IDENTITIES:
        _refuse()
    validated = tuple(_sid(value) for value in values)
    if len(set(validated)) != len(validated):
        _refuse()
    return frozenset(validated)


def _construct(members_by_sleeve, caps_by_sid, scores_by_sid, *, arm,
               warning_ids, final_ids):
    if (type(members_by_sleeve) is not dict or set(members_by_sleeve) != set(cap_tilt.ETFS)
            or not isinstance(caps_by_sid, Mapping) or len(caps_by_sid) > MAX_IDENTITIES):
        _refuse()
    warnings, finals = _id_inventory(warning_ids), _id_inventory(final_ids)
    unusable = warnings | finals
    ranked_by_sleeve, executable_by_sleeve, coverage_by_sleeve = {}, {}, {}
    members_seen = set()
    # Complete cap-only ranking and removal BEFORE any signal lookup.
    for etf in cap_tilt.ETFS:
        members = members_by_sleeve[etf]
        if type(members) not in (list, tuple) or len(members) > MAX_IDENTITIES:
            _refuse()
        try:
            ranked, coverage = cap_tilt.rank_cap_members(members, caps_by_sid)
        except cap_tilt.CapTiltError:
            _refuse()
        members_seen.update(_sid(row["sid"]) for row in members)
        if len(members_seen) > MAX_IDENTITIES:
            _refuse()
        ranked_by_sleeve[etf] = tuple(ranked)
        executable_by_sleeve[etf] = tuple(sid for sid in ranked if sid not in unusable)
        coverage_by_sleeve[etf] = coverage
    executable = set().union(*map(set, executable_by_sleeve.values()))
    if arm == "tpr_on":
        if not isinstance(scores_by_sid, Mapping) or len(scores_by_sid) > MAX_IDENTITIES:
            _refuse()
        selected_scores = {sid: scores_by_sid.get(sid) for sid in sorted(executable)}
        capacity = "0.20"
    elif arm == "tpr_off":
        # No test, len, iteration, get or callback on a signal object here.
        selected_scores, capacity = {}, "0"
    else:
        _refuse()
    try:
        weights, tilt = cap_tilt.tilt_sleeves(executable_by_sleeve, selected_scores, capacity=capacity)
    except cap_tilt.CapTiltError:
        _refuse()
    reports = {}
    for etf in cap_tilt.ETFS:
        ranked, selected = ranked_by_sleeve[etf], executable_by_sleeve[etf]
        removed = tuple({"security_id": sid, "state": "final" if sid in finals else "warning"}
                        for sid in ranked if sid in unusable)
        detail = dict(tilt["per_sleeve"][etf])
        if arm == "tpr_off":
            detail["score_state_counts"] = {"not_used": len(selected)}
        expected_base = len(selected) * cap_tilt.BASE_SLOT_WEIGHT
        if (detail["baseline_weight"] != expected_base or detail["target_weight"] != expected_base
                or detail["cash_weight"] + expected_base != cap_tilt.SLEEVE_BUDGET
                or set(detail["target_weights"]) != set(selected)):
            _refuse()
        reports[etf] = {**detail, "cap_ranked_ids": ranked, "executable_ids": selected,
            "removed_unusable": removed, "cap_ranked_count": len(ranked),
            "executable_count": len(selected), "removed_unusable_count": len(removed),
            "unfilled_slots": cap_tilt.MAX_SLOTS - len(selected),
            "cap_coverage": dict(coverage_by_sleeve[etf])}
    slots = sum(len(rows) for rows in executable_by_sleeve.values())
    gross = sum(weights.values(), Fraction(0))
    if (set(weights) != executable or gross != slots * cap_tilt.BASE_SLOT_WEIGHT
            or gross != sum(row["target_weight"] for row in reports.values())
            or gross + sum(row["cash_weight"] for row in reports.values()) != 1):
        _refuse()
    return weights, {"schema": "tpr-extended-cap-selected-construction-v1", "arm": arm,
        "cap_ranked_slot_count": sum(len(rows) for rows in ranked_by_sleeve.values()),
        "executable_slot_count": slots,
        "removed_unusable_slot_count": sum(row["removed_unusable_count"] for row in reports.values()),
        "target_gross_weight": gross, "cash_weight": 1 - gross,
        "baseline_weights": dict(tilt["baseline_weights"]),
        "transferred_weight": tilt["transferred_weight"], "per_sleeve": reports,
        "nonmember_unusable_id_count": len(unusable - members_seen),
        "canonical_admission": False, "native_basis_authenticated": False,
        "runtime_integration_complete": False}


def construct_on(members_by_sleeve, caps_by_sid, scores_by_sid, *, warning_ids=(), final_ids=()):
    """Cap-only selected stocks, usable-slot filter, then unchanged20% TPR tilt."""
    return _construct(members_by_sleeve, caps_by_sid, scores_by_sid, arm="tpr_on",
                      warning_ids=warning_ids, final_ids=final_ids)


def construct_off(members_by_sleeve, caps_by_sid, *, warning_ids=(), final_ids=()):
    """Matched no-signal construction; accepts no scores or signal callback."""
    return _construct(members_by_sleeve, caps_by_sid, None, arm="tpr_off",
                      warning_ids=warning_ids, final_ids=final_ids)
