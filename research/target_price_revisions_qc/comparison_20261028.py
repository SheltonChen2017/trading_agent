"""Pure candidate construction for the owner-directed five-arm comparison.

Only supplied public/synthetic values are processed here. Caller must prove
historical membership, classification, identity, clocks, rights and complete
signal inputs independently. No source opener, native adapter, QC setup, order
or input admission exists. Old studies, sources and look histories stay intact.

200% means twice baseline rank-scaled TRANSFER DEMAND, not short weights or
independent clipping. Donors fund only from actual remaining sleeve weight;
unfunded recipient demand is recorded. Requested capacities are floored to
1e-30; exact rational funding may consume a final sub-quantum donor residual.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json

from . import cap_tilt as legacy

STUDY_ID = "TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1"
SLEEVES = ("SPY", "XLE", "REMX", "KIE", "XLF", "IWM")
ARMS = ("cap_off", "cap_tilt_50", "cap_tilt_100", "cap_tilt_200", "pure_tpr")
MAX_IDENTITIES = 4096
BASE = legacy.BASE_SLOT_WEIGHT
SLEEVE_BUDGET = legacy.SLEEVE_BUDGET
NAME_CAP = legacy.AGGREGATE_NAME_CAP
QUANTUM = legacy.TRANSFER_QUANTUM
SCORE_STATES = ("nonzero", "zero", "missing", "unknown", "invalid")


class ComparisonError(ValueError):
    """Body-free refusal of the bounded supplied-value candidate contract."""


def _refuse():
    raise ComparisonError("invalid bounded five-arm comparison input") from None


def policy():
    """Return a fresh candidate declaration, never a native admission record."""
    return {
        "schema": "tpr-five-arm-policy-candidate-v1", "study_id": STUDY_ID,
        "status": "CANDIDATE_ONLY", "source_inputs_admitted": False,
        "native_setup_complete": False, "backtesting_ready": False,
        "canonical_admission": False, "trading_authority": False,
        "dates": {"first_session": "2021-01-04", "end": "2026-10-09",
                  "signal_warmup_start": "2020-09-01", "valuations": 1449, "decisions": 301},
        "universes": [
            {"sleeve": "SPY", "meaning": "historical S&P500 stock proxy"},
            {"sleeve": "XLE", "meaning": "historical energy stock proxy"},
            {"sleeve": "REMX", "meaning": "historical US-covered global rare-earth/strategic-metals subset"},
            {"sleeve": "KIE", "meaning": "historical insurance stock proxy"},
            {"sleeve": "XLF", "meaning": "historical financials stock proxy excluding all as-of insurance classifications"},
            {"sleeve": "IWM", "meaning": "historical small-cap stock proxy"}],
        "arms": [
            {"arm": "cap_off", "selection": "cap", "capacity": "0"},
            {"arm": "cap_tilt_50", "selection": "cap", "capacity": "0.5"},
            {"arm": "cap_tilt_100", "selection": "cap", "capacity": "1"},
            {"arm": "cap_tilt_200", "selection": "cap", "capacity": "2"},
            {"arm": "pure_tpr", "selection": "highest-valid-signed-TPR", "capacity": "0"}],
        "construction": {
            "sleeve_order": list(SLEEVES), "slots_per_sleeve": 10,
            "base_slot": "1/60", "sleeve_budget": "1/6", "aggregate_name_cap": "1/10",
            "cap_selection": "finite positive cap descending; permanent SID tie; independent of scores",
            "pure_selection": "valid signed scores descending including measured zeros; permanent SID tie",
            "pure_unavailable": "exclude with separate missing/unknown/invalid census; never zero or cap fallback",
            "pure_weights": "equal fixed1/60 slots; no second tilt",
            "unusable": "warning/final removal after top10 ranking; no rank11 refill",
            "missing_slots": "cash; no renormalization or ETF fallback",
            "finance_classification": "all supplied XLF members require explicit insurance/noninsurance; unknown/missing refuses; insurance removed before selection",
            "tilt_rank": "nonzero scores only; ascending tied midrank centered[-1,1]; zero/unavailable neutral",
            "tilt_demand": "baseline times capacity times absolute rank; requested capacity floor1e-30",
            "tilt_funding": "min(remaining rank demand, actual positive donor sleeve weight); stop at zero",
            "tilt_order": "frozen sleeve order; receivers high-score/SID; donors low-score/SID",
            "tilt_caps": "aggregate name headroom limits actual transfer; retain unfunded demand",
            "funded_residual": "exact rational final donor residual may be below1e-30; no independent weight clipping",
            "no_shorts": True, "no_independent_clipping": True, "no_renormalization": True,
            "ar_enabled": False},
        "unchanged_execution_contract": {
            "capital_usd": "100000", "currency": "USD", "leverage": "1",
            "buy_cash_fraction": "0.97", "cash_rule": "settled cash; no anticipated sale proceeds",
            "decision_ny": "09:20", "order_type": "MarketOnOpen simulated orders",
            "cancel_ny": "09:35", "valuation_ny": "16:01", "whole_shares": True,
            "sizing_nav": "prior close", "prior_session_volume_limit": "0.01",
            "fees_usd_per_share": "0.01", "slippage_per_side": "0.001",
            "corporate_actions": "native RAW; affirmative known share-basis evidence required"},
        "valuation_verification_contract": {
            "mode": "strict_minute_or_raw_daily_equal_close_v1", "all_five_arms": True,
            "primary": "real same-session minute cache ends exactly at native exchange close",
            "corroboration": "earlier real same-session minute cache only; exactly1 native exact-SID current-session RAW DAILY non-fill-forward regular-hours bar ending at native close<=now",
            "price": "positive finite daily.close exactly equals unchanged security.price and cached.price; positive volume",
            "history_range": "local session midnight through captured16:01; max2rows; no future/date widening",
            "custody": "actual project/job before and after request/enumeration; unchanged native cache/clock/price/quantity/cash/NAV snapshots",
            "refuse": "missing/duplicate/wrongSID/wrongday/fillforward/future/zero-volume/unequal-price; no timestamp rewrite, mark substitution or exclusion",
            "provenance": "retain original minute endpoint and independent DAILY session-close endpoint; DAILY aggregate is not proof of a final-minute trade",
            "decision_id": "TPR-CMP104-D009"},
        "signal_contract": {
            "formula": "exploratory nominal new/prior target minus1, clipped[-1,1]; not canonical price-scaled TPR",
            "aggregation": "firm/security/eligible-session median;20-session half-life;80-session truncation; sum within firm then median firms",
            "timing": "prior exchange-session18:00 America/New_York cutoff; censored last_updated; second exchange-open eligibility"},
        "provenance": {
            "owner": "2026-10-28 five arms and existing formula coefficients50/100/200;200% long-only actual-donor funding accepted; remaining choices delegated",
            "delegated_decisions": [
                {"id": "TPR-CMP104-D001", "decision": "IWM historical small caps replaces Nasdaq proxy to reduce overlap; overlap still reported"},
                {"id": "TPR-CMP104-D002", "decision": "pure signed top10 includes measured zeros; unavailable excluded; equal fixed slots; no refill"},
                {"id": "TPR-CMP104-D003", "decision": "complete explicit as-of insurance classification required for XLF; unknown refuses"},
                {"id": "TPR-CMP104-D004", "decision": "200% demand funded only by actual donors; rational zero-stop residual; no leverage"}],
            "historical_study": "TPR-CAP-TILT-EXT26-20261010-v1",
            "historical_attempts_looks_preserved": True,
            "no_outcome_selected_choices": True},
        "limits": {
            "max_identities": MAX_IDENTITIES, "private_reads": 0, "qc_effects": 0,
            "new_attempts": 0, "new_observed_looks": 0,
            "required_before_native": ["new study/calendar/config/source hashes", "complete historical membership and as-of insurance classifications", "full admitted identity/action/signal bridge", "fresh bounded access/operation/attempt claims", "verified source-unit repair and native order/accounting evidence"],
            "historical_input_limitations_retained": True,
            "native_runtime_integration_implemented": False,
            "accepted_performance": None}}


def policy_bytes():
    return (json.dumps(policy(), sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def validate_policy(raw):
    """Accept only this exact canonical candidate, without authenticating it."""
    if type(raw) is not bytes or raw != policy_bytes():
        _refuse()
    return hashlib.sha256(raw).hexdigest()


def _sid(value):
    if (type(value) is not str or not 0 < len(value) <= 128 or value.strip() != value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        _refuse()
    return value


def _ids(values):
    if type(values) not in (list, tuple, set, frozenset) or len(values) > MAX_IDENTITIES:
        _refuse()
    result = tuple(_sid(value) for value in values)
    if len(set(result)) != len(result):
        _refuse()
    return frozenset(result)


def _members(members, finance_insurance_by_sid):
    if type(members) is not dict or set(members) != set(SLEEVES):
        _refuse()
    inventory, sid_to_ticker, ticker_to_sid = {}, {}, {}
    for sleeve in SLEEVES:
        rows = members[sleeve]
        if type(rows) not in (list, tuple) or len(rows) > MAX_IDENTITIES:
            _refuse()
        retained, local_sids, local_tickers = [], set(), set()
        for row in rows:
            if not isinstance(row, Mapping):
                _refuse()
            sid, ticker = _sid(row.get("sid")), row.get("ticker")
            if (type(ticker) is not str or not 0 < len(ticker) <= 32 or ticker.strip() != ticker
                    or any(ord(char) < 32 or ord(char) == 127 for char in ticker)
                    or sid in local_sids or ticker in local_tickers):
                _refuse()
            local_sids.add(sid)
            local_tickers.add(ticker)
            if (sid in sid_to_ticker and sid_to_ticker[sid] != ticker
                    or ticker in ticker_to_sid and ticker_to_sid[ticker] != sid):
                _refuse()
            sid_to_ticker[sid], ticker_to_sid[ticker] = ticker, sid
            retained.append({"sid": sid, "ticker": ticker})
        inventory[sleeve] = retained
    if len(sid_to_ticker) > MAX_IDENTITIES:
        _refuse()
    finance = inventory["XLF"]
    if (type(finance_insurance_by_sid) is not dict
            or set(finance_insurance_by_sid) != {row["sid"] for row in finance}
            or any(type(value) is not str or value not in ("insurance", "noninsurance")
                   for value in finance_insurance_by_sid.values())):
        _refuse()
    insurance = sum(value == "insurance" for value in finance_insurance_by_sid.values())
    inventory["XLF"] = [row for row in finance if finance_insurance_by_sid[row["sid"]] == "noninsurance"]
    return inventory, {"supplied_finance_members": len(finance), "insurance_excluded": insurance,
        "noninsurance_retained": len(finance) - insurance, "missing_or_unknown": 0,
        "historical_classification_authenticated": False}


def _bounded_cell(raw):
    if (isinstance(raw, Mapping) and set(raw) <= {"state", "value"}
            and raw.get("state") in ("missing", "unknown", "invalid")):
        return raw  # Unavailable state does not consume or validate a retained value.
    value = raw.get("value") if isinstance(raw, Mapping) else raw
    if type(value) is str:
        if len(value) > 128:
            return {"state": "invalid"}
        try:
            number = Decimal(value)
        except InvalidOperation:
            return raw  # Legacy parser retains the invalid state.
        parts = number.as_tuple()
        if not number.is_finite() or len(parts.digits) > 64 or not -128 <= parts.exponent <= 128:
            return {"state": "invalid"}
    elif type(value) in (int, Fraction):
        number = Fraction(value)
        if max(number.numerator.bit_length(), number.denominator.bit_length()) > 512:
            return {"state": "invalid"}
    elif type(value) is Decimal:
        parts = value.as_tuple()
        if not value.is_finite() or len(parts.digits) > 64 or not -128 <= parts.exponent <= 128:
            return {"state": "invalid"}
    return raw


def _mapping(value):
    if not isinstance(value, Mapping) or len(value) > MAX_IDENTITIES:
        _refuse()
    for key in value:
        _sid(key)
    return value


def _state(scores, sid):
    return legacy._score_state(_bounded_cell(scores.get(sid)), present=sid in scores)


def _allocate(selected, scores, capacity):
    totals = {}
    for sleeve in SLEEVES:
        for sid in selected[sleeve]:
            totals[sid] = totals.get(sid, Fraction(0)) + BASE
    baseline_totals, details = dict(totals), {}
    if any(weight > NAME_CAP for weight in totals.values()):
        _refuse()
    for sleeve in SLEEVES:
        baseline = {sid: BASE for sid in selected[sleeve]}
        updated = dict(baseline)
        counts, scored = dict.fromkeys(SCORE_STATES, 0), {}
        for sid in selected[sleeve]:
            state, value = _state(scores, sid)
            counts[state] += 1
            if state == "nonzero":
                scored[sid] = value
        ranks = legacy._rank_tilts(scored)
        receivers = sorted((sid for sid in ranks if ranks[sid] > 0), key=lambda sid: (-scored[sid], sid))
        donors = sorted((sid for sid in ranks if ranks[sid] < 0), key=lambda sid: (scored[sid], sid))
        demand = {sid: legacy._transfer_capacity(BASE, capacity, rank) for sid, rank in ranks.items()}
        transferred, blocked, cap_bindings = Fraction(0), Fraction(0), 0
        for receiver in receivers:
            room = min(demand[receiver], NAME_CAP - totals[receiver])
            blocked += demand[receiver] - room
            cap_bindings += int(room < demand[receiver])
            for donor in donors:
                spent = baseline[donor] - updated[donor]
                available = min(demand[donor] - spent, updated[donor])
                moved = min(room, available)
                if moved <= 0:
                    continue
                updated[receiver] += moved
                updated[donor] -= moved
                totals[receiver] += moved
                totals[donor] -= moved
                transferred += moved
                room -= moved
                if not room:
                    break
        recipient_demand = sum((demand[sid] for sid in receivers), Fraction(0))
        actual_budget = sum(updated.values(), Fraction(0))
        if (actual_budget != len(selected[sleeve]) * BASE or set(updated) != set(baseline)
                or any(weight < 0 for weight in updated.values())
                or any(abs(updated[sid] - BASE) > BASE * capacity for sid in updated)):
            _refuse()
        details[sleeve] = {"baseline_weights": baseline, "target_weights": updated,
            "rank_tilts": dict(sorted(ranks.items())), "score_state_counts": counts,
            "ranked_score_count": len(scored), "baseline_weight": len(baseline) * BASE,
            "target_weight": actual_budget, "cash_weight": SLEEVE_BUDGET - actual_budget,
            "recipient_capacity": recipient_demand,
            "donor_capacity": sum((demand[sid] for sid in donors), Fraction(0)),
            "transferred_weight": transferred, "recipient_underfill": recipient_demand - transferred,
            "aggregate_cap_blocked_capacity": blocked, "cap_binding_recipient_count": cap_bindings,
            "zero_weight_count": sum(weight == 0 for weight in updated.values())}
    gross = sum(totals.values(), Fraction(0))
    if (totals.keys() != baseline_totals.keys() or gross != sum(baseline_totals.values(), Fraction(0))
            or not 0 <= gross <= 1 or any(not 0 <= value <= NAME_CAP for value in totals.values())):
        _refuse()
    return dict(sorted(totals.items())), {"baseline_weights": dict(sorted(baseline_totals.items())),
        "per_sleeve": details, "target_gross_weight": gross, "cash_weight": 1 - gross,
        "transferred_weight": sum((row["transferred_weight"] for row in details.values()), Fraction(0))}


def _finish(inventory, ranked, coverage, scores, *, arm, capacity, warning_ids, final_ids, finance):
    warnings, finals = _ids(warning_ids), _ids(final_ids)
    unusable = warnings | finals
    selected = {sleeve: tuple(sid for sid in ranked[sleeve] if sid not in unusable) for sleeve in SLEEVES}
    weights, report = _allocate(selected, scores, capacity)
    for sleeve in SLEEVES:
        row = report["per_sleeve"][sleeve]
        removed = tuple({"security_id": sid, "state": "final" if sid in finals else "warning"}
                        for sid in ranked[sleeve] if sid in unusable)
        row.update({"ranked_ids": tuple(ranked[sleeve]), "executable_ids": selected[sleeve],
                    "ranked_count": len(ranked[sleeve]), "executable_count": len(selected[sleeve]),
                    "removed_unusable": removed, "unfilled_slots": 10 - len(selected[sleeve]),
                    "selection_coverage": coverage[sleeve]})
        if arm in ("cap_off", "pure_tpr"):
            row["score_state_counts"] = {"not_used_for_weighting": len(selected[sleeve])}
    report.update({"schema": "tpr-five-arm-construction-candidate-v1", "study_id": STUDY_ID,
        "arm": arm, "capacity": capacity, "finance_classification": finance,
        "selected_slot_count": sum(map(len, selected.values())),
        "source_inputs_admitted": False, "native_basis_authenticated": False,
        "runtime_integration_complete": False, "backtesting_ready": False,
        "accepted_performance": None, "canonical_admission": False})
    return weights, report


def _cap(members, caps, *, scores, arm, capacity, finance_insurance_by_sid, warning_ids, final_ids):
    inventory, finance = _members(members, finance_insurance_by_sid)
    caps = _mapping(caps)
    bounded_caps = {sid: _bounded_cell(value) for sid, value in caps.items()}
    ranked, coverage = {}, {}
    for sleeve in SLEEVES:
        try:
            ranked[sleeve], coverage[sleeve] = legacy.rank_cap_members(inventory[sleeve], bounded_caps)
        except legacy.CapTiltError:
            _refuse()
    return _finish(inventory, ranked, coverage, scores, arm=arm, capacity=capacity,
        warning_ids=warning_ids, final_ids=final_ids, finance=finance)


def construct_off(members, caps, *, finance_insurance_by_sid, warning_ids=(), final_ids=()):
    """Cap-only neutral arm with no score input or callback."""
    return _cap(members, caps, scores={}, arm="cap_off", capacity=Fraction(0),
        finance_insurance_by_sid=finance_insurance_by_sid, warning_ids=warning_ids, final_ids=final_ids)


def construct_tilt(members, caps, scores, *, arm, finance_insurance_by_sid, warning_ids=(), final_ids=()):
    """Only the three prospectively declared coefficients, not a sweep API."""
    capacities = {"cap_tilt_50": Fraction(1, 2), "cap_tilt_100": Fraction(1), "cap_tilt_200": Fraction(2)}
    if type(arm) is not str or arm not in capacities:
        _refuse()
    return _cap(members, caps, scores=_mapping(scores), arm=arm, capacity=capacities[arm],
        finance_insurance_by_sid=finance_insurance_by_sid, warning_ids=warning_ids, final_ids=final_ids)


def construct_pure_tpr(members, scores, *, finance_insurance_by_sid, warning_ids=(), final_ids=()):
    """Signed top10 from full membership; measured zeros rank, caps cannot enter."""
    inventory, finance = _members(members, finance_insurance_by_sid)
    scores = _mapping(scores)
    ranked, coverage = {}, {}
    for sleeve in SLEEVES:
        counts, eligible = dict.fromkeys(SCORE_STATES, 0), []
        for row in inventory[sleeve]:
            sid = row["sid"]
            state, score = _state(scores, sid)
            counts[state] += 1
            if state in ("nonzero", "zero"):
                eligible.append((sid, score))
        eligible.sort(key=lambda row: (-row[1], row[0]))
        ranked[sleeve] = [sid for sid, _ in eligible[:10]]
        coverage[sleeve] = {"member_count": len(inventory[sleeve]), "score_state_counts": counts,
            "eligible_count": len(eligible), "eligible_unselected_count": max(0, len(eligible) - 10),
            "ranked_count": len(ranked[sleeve]), "unfilled_slots_before_unusable": 10 - len(ranked[sleeve])}
    return _finish(inventory, ranked, coverage, {}, arm="pure_tpr", capacity=Fraction(0),
        warning_ids=warning_ids, final_ids=final_ids, finance=finance)
