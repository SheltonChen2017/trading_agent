"""Pure, exploratory market-cap selection followed by a bounded TPR tilt.

The caller owns universe identity, historical availability and source-clock
validation. A finite supplied market cap is not proof of point-in-time data.
Only positive market caps select stocks; neither member weights nor TPR
presence, state, sign or magnitude may change the selected identities.

Six equal sleeves have ten fixed 1/60 slots each. Missing slots stay cash.
Within selected stocks, unavailable and exact-zero scores remain neutral.
Nonzero scores receive ascending tied midranks centered on [-1, 1], as in
the Analyst lane's bounded within-selected tilt. This is a relative rank:
a lower positive score may donate to a higher positive score. Exact rational
transfers preserve sleeve budgets and the aggregate 1/10 name cap. There is
no I/O, LEAN dependency, fallback, score generation or execution authority.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re


ETFS = ("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX")
MAX_SLOTS = 10
BASE_SLOT_WEIGHT = Fraction(1, 60)
SLEEVE_BUDGET = Fraction(1, 6)
AGGREGATE_NAME_CAP = Fraction(1, 10)
TRANSFER_QUANTUM = Fraction(1, 10**30)
_CAP_STATES = ("available", "missing", "unknown", "invalid", "nonpositive")
_SCORE_STATES = ("nonzero", "zero", "missing", "unknown", "invalid")
_DECIMAL_TEXT = re.compile(r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?\Z")


class CapTiltError(ValueError):
    """The pure construction input or a conservation invariant is invalid."""


def _exact_number(value):
    """Accept exact represented values only, never authoritative floats."""
    if type(value) is Fraction:
        return value
    if type(value) is int:
        return Fraction(value)
    if type(value) is str:
        if _DECIMAL_TEXT.fullmatch(value) is None:
            raise CapTiltError("number is not exact decimal text")
        try:
            value = Decimal(value)
        except InvalidOperation as exc:
            raise CapTiltError("number is not exact decimal text") from exc
    if type(value) is Decimal and value.is_finite():
        return Fraction(value)
    raise CapTiltError("number is not exact and finite")


def _sid(value):
    if type(value) is not str or not value or value.strip() != value:
        raise CapTiltError("native SID is missing or malformed")
    return value


def _cap_state(raw, *, present):
    if not present or raw is None:
        return "missing", None
    if isinstance(raw, Mapping):
        if not set(raw) <= {"state", "value"} or raw.get("state") not in _CAP_STATES:
            return "invalid", None
        state = raw["state"]
        if state in ("missing", "unknown", "invalid"):
            # An explicitly unavailable row never becomes an eligible amount,
            # even if a caller retains a value for its separate provenance.
            return state, None
        value = raw.get("value")
        if state == "nonpositive" and value is None:
            return state, None
        try:
            number = _exact_number(value)
        except CapTiltError:
            return "invalid", None
        if state == "nonpositive" and number > 0:
            return "invalid", None
    else:
        try:
            number = _exact_number(raw)
        except CapTiltError:
            return "invalid", None
    return ("available", number) if number > 0 else ("nonpositive", None)


def rank_cap_members(members, caps):
    """Return ``(selected_sids, coverage)`` without accepting score inputs.

    Members are mappings with nonempty unique ``sid`` and ``ticker`` fields;
    other member metadata, including ``weight`` or ``score``, is not consumed.
    Caps map SID to exact str/int/Decimal/Fraction values, None, or a state
    row with ``state`` and optional ``value``. State rows use available,
    missing, unknown, invalid or nonpositive. Only an available, finite,
    positive amount is ranked descending, with native SID breaking cap ties.
    Coverage counts every member, including each unselected/missing member.
    The represented-cap sum is diagnostic, not a full-universe/PIT claim.
    """
    if not isinstance(caps, Mapping) or type(members) not in (list, tuple):
        raise CapTiltError("explicit member sequence and cap mapping required")
    seen_sids, seen_tickers, ranked = set(), set(), []
    counts = {state: 0 for state in _CAP_STATES}
    for member in members:
        if not isinstance(member, Mapping):
            raise CapTiltError("member row is not a mapping")
        sid = _sid(member.get("sid"))
        ticker = member.get("ticker")
        if type(ticker) is not str or not ticker or ticker.strip() != ticker:
            raise CapTiltError("member ticker is missing or malformed")
        if sid in seen_sids or ticker in seen_tickers:
            raise CapTiltError("ambiguous native membership identity")
        seen_sids.add(sid)
        seen_tickers.add(ticker)
        state, cap = _cap_state(caps.get(sid), present=sid in caps)
        counts[state] += 1
        if state == "available":
            ranked.append((sid, cap))
    ranked.sort(key=lambda row: (-row[1], row[0]))
    selected = [sid for sid, _ in ranked[:MAX_SLOTS]]
    coverage = {
        "member_count": len(members),
        "cap_state_counts": counts,
        "eligible_count": len(ranked),
        "selected_count": len(selected),
        "eligible_unselected_count": len(ranked) - len(selected),
        "unfilled_slots": MAX_SLOTS - len(selected),
        "represented_positive_cap_sum": sum((cap for _, cap in ranked), Fraction(0)),
        "ignored_nonmember_cap_rows": sum(sid not in seen_sids for sid in caps),
    }
    if sum(counts.values()) != len(members):
        raise CapTiltError("cap coverage does not partition membership")
    return selected, coverage


def _score_state(raw, *, present):
    if not present or raw is None:
        return "missing", None
    if isinstance(raw, Mapping):
        if not set(raw) <= {"state", "value"}:
            return "invalid", None
        state = raw.get("state")
        if state in ("missing", "unknown", "invalid"):
            return state, None
        if state not in ("available", "zero", "nonzero"):
            return "invalid", None
        value = raw.get("value")
        if state == "zero" and value is None:
            value = "0"
        try:
            number = _exact_number(value)
        except CapTiltError:
            return "invalid", None
        if (state == "zero" and number != 0) or (state == "nonzero" and number == 0):
            return "invalid", None
    else:
        try:
            number = _exact_number(raw)
        except CapTiltError:
            return "invalid", None
    return ("nonzero", number) if number else ("zero", number)


def _selected_inventory(selected_by_sleeve):
    if not isinstance(selected_by_sleeve, Mapping) or set(selected_by_sleeve) != set(ETFS):
        raise CapTiltError("all six exact sleeves required")
    inventory, totals = {}, {}
    for etf in ETFS:
        selected = selected_by_sleeve[etf]
        if isinstance(selected, Mapping):
            selected = tuple(selected)
        if type(selected) not in (list, tuple) or len(selected) > MAX_SLOTS:
            raise CapTiltError("explicit selected SID slots required")
        sids = tuple(sorted(_sid(sid) for sid in selected))
        if len(set(sids)) != len(sids):
            raise CapTiltError("selected SID duplicated within a sleeve")
        inventory[etf] = sids
        for sid in sids:
            totals[sid] = totals.get(sid, Fraction(0)) + BASE_SLOT_WEIGHT
    if any(weight > AGGREGATE_NAME_CAP for weight in totals.values()):
        raise CapTiltError("baseline aggregate name cap exceeded")
    return inventory, dict(sorted(totals.items()))


def _rank_tilts(scored):
    if len(scored) < 2:
        return {}
    ascending = sorted(scored.items(), key=lambda row: (row[1], row[0]))
    ranks, start = {}, 0
    while start < len(ascending):
        end = start + 1
        while end < len(ascending) and ascending[end][1] == ascending[start][1]:
            end += 1
        # start is zero-based and end is exclusive. Twice the tied midrank
        # minus the center gives this exact rational centered rank.
        rank = Fraction(start + end - len(ascending), len(ascending) - 1)
        for sid, _ in ascending[start:end]:
            ranks[sid] = rank
        start = end
    return ranks


def _transfer_capacity(base, capacity, rank):
    amount = base * capacity * abs(rank)
    units = amount // TRANSFER_QUANTUM
    return units * TRANSFER_QUANTUM


def tilt_sleeves(selected_by_sleeve, score_by_sid, capacity="0.20"):
    """Return ``(aggregate_fraction_weights, diagnostics)`` for fixed stocks.

    ``capacity`` is a frozen exact fraction between zero and one; zero is the
    matched neutral control. Scores map SID to exact represented values,
    None, or state rows (available/nonzero/zero/missing/unknown/invalid).
    Missing/nonfinite scores and actual zero scores are separately counted,
    remain neutral and do not enter the nonzero-score rank cross-section.

    Recipient order is high-score/SID, donor order is low-score/SID and sleeve
    order is ETFS. Each side's rank-scaled transfer capacity is floored at
    1e-30 before use. Aggregate cap headroom may prevent full transfer; that
    underfill is retained, not renormalized into missing slots or other names.
    Diagnostics contain identities/weights for the caller's private evidence;
    they are not a public-market-row publication contract.
    """
    if not isinstance(score_by_sid, Mapping):
        raise CapTiltError("explicit score mapping required")
    capacity = _exact_number(capacity)
    if not 0 <= capacity <= 1:
        raise CapTiltError("tilt capacity outside zero-to-one bounds")
    inventory, baseline_totals = _selected_inventory(selected_by_sleeve)
    totals, sleeves = dict(baseline_totals), {}
    for etf in ETFS:
        baseline = {sid: BASE_SLOT_WEIGHT for sid in inventory[etf]}
        updated = dict(baseline)
        counts, scored = {state: 0 for state in _SCORE_STATES}, {}
        for sid in inventory[etf]:
            state, score = _score_state(score_by_sid.get(sid), present=sid in score_by_sid)
            counts[state] += 1
            if state == "nonzero":
                scored[sid] = score
        ranks = _rank_tilts(scored)
        receivers = sorted((sid for sid in ranks if ranks[sid] > 0),
                           key=lambda sid: (-scored[sid], sid))
        donors = sorted((sid for sid in ranks if ranks[sid] < 0),
                        key=lambda sid: (scored[sid], sid))
        capacities = {sid: _transfer_capacity(baseline[sid], capacity, rank)
                      for sid, rank in ranks.items()}
        moved_total, cap_blocked, transfer_count = Fraction(0), Fraction(0), 0
        cap_binding_count = 0
        for receiver in receivers:
            requested = capacities[receiver]
            room = min(requested, AGGREGATE_NAME_CAP - totals[receiver])
            cap_blocked += requested - room
            cap_binding_count += int(room < requested)
            for donor in donors:
                available = capacities[donor] - (baseline[donor] - updated[donor])
                moved = min(room, available)
                if moved <= 0:
                    continue
                updated[receiver] += moved
                updated[donor] -= moved
                totals[receiver] += moved
                totals[donor] -= moved
                moved_total += moved
                transfer_count += 1
                room -= moved
                if room == 0:
                    break
        base_budget = sum(baseline.values(), Fraction(0))
        final_budget = sum(updated.values(), Fraction(0))
        if final_budget != base_budget or set(updated) != set(baseline):
            raise CapTiltError("tilt changed sleeve budget or selected identities")
        if any(abs(updated[sid] - baseline[sid]) > baseline[sid] * capacity
               or updated[sid] < 0 for sid in baseline):
            raise CapTiltError("tilt exceeded own baseline weight band")
        requested_receivers = sum((capacities[sid] for sid in receivers), Fraction(0))
        sleeves[etf] = {
            "selected_count": len(baseline),
            "score_state_counts": counts,
            "ranked_score_count": len(scored),
            "baseline_weights": baseline,
            "target_weights": updated,
            "rank_tilts": dict(sorted(ranks.items())),
            "baseline_weight": base_budget,
            "target_weight": final_budget,
            "cash_weight": SLEEVE_BUDGET - base_budget,
            "recipient_capacity": requested_receivers,
            "donor_capacity": sum((capacities[sid] for sid in donors), Fraction(0)),
            "transferred_weight": moved_total,
            "recipient_underfill": requested_receivers - moved_total,
            "aggregate_cap_blocked_capacity": cap_blocked,
            "cap_binding_recipient_count": cap_binding_count,
            "transfer_count": transfer_count,
            "maximum_absolute_relative_change": max(
                (abs(updated[sid] - baseline[sid]) / baseline[sid] for sid in baseline),
                default=Fraction(0)),
        }
    if set(totals) != set(baseline_totals) or any(not 0 <= weight <= AGGREGATE_NAME_CAP
                                               for weight in totals.values()):
        raise CapTiltError("tilt changed aggregate identities or name cap")
    gross = sum(totals.values(), Fraction(0))
    if gross != sum(baseline_totals.values(), Fraction(0)) or not 0 <= gross <= 1:
        raise CapTiltError("tilt changed gross budget")
    return dict(sorted(totals.items())), {
        "schema": "tpr-cap-selected-within-stock-tilt-v1",
        "capacity": capacity,
        "transfer_quantum": TRANSFER_QUANTUM,
        "baseline_weights": baseline_totals,
        "selected_slot_count": sum(len(inventory[etf]) for etf in ETFS),
        "target_gross_weight": gross,
        "cash_weight": 1 - gross,
        "transferred_weight": sum((row["transferred_weight"] for row in sleeves.values()), Fraction(0)),
        "per_sleeve": sleeves,
    }
