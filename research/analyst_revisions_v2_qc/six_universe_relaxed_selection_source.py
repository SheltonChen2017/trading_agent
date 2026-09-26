"""Host-only exact successor rendering; frozen gate sources remain untouched."""

import ast
from decimal import Decimal
import re


class RelaxedSelectionSourceError(ValueError):
    """The prospective policy or an exact reviewed source anchor changed."""


RELAXED_UNIVERSES = ("QQQ", "SOXX", "REMX")


def _replace(source, old, new):
    if old == new or source.count(old) != 1:
        raise RelaxedSelectionSourceError("relaxed source exact anchor changed")
    return source.replace(old, new, 1)


def _normalize(source):
    if type(source) is not str or not source.isascii():
        raise RelaxedSelectionSourceError("relaxed source is not exact ASCII text")
    try:
        tree = ast.parse(source)
        normalized = ast.unparse(tree) + "\n"
        rebuilt = ast.parse(normalized)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise RelaxedSelectionSourceError("relaxed source normalization failed") from exc
    if ast.dump(tree, include_attributes=False) != ast.dump(rebuilt, include_attributes=False):
        raise RelaxedSelectionSourceError("relaxed source normalization changed executable AST")
    return normalized


def _policy(value):
    if type(value) is not tuple or len(value) != 3:
        raise RelaxedSelectionSourceError("relaxed policy requires three exact universe tuples")
    for expected, item in zip(RELAXED_UNIVERSES, value):
        if (type(item) is not tuple or len(item) != 5 or type(item[0]) is not str
                or item[0] != expected or type(item[4]) is not int or item[4] != 5):
            raise RelaxedSelectionSourceError("relaxed policy universe or known-name floor changed")
        for text, maximum in zip(item[1:4], ("0.90", "0.90", "0.95")):
            if (type(text) is not str or re.fullmatch(r"(?:0\.[0-9]{1,8}|1)", text) is None
                    or not Decimal(0) < Decimal(text) <= Decimal(maximum)):
                raise RelaxedSelectionSourceError("relaxed coverage threshold is outside its finite bound")
    return value


_COVERAGE_ANCHOR = '''def _coverage(
    rows: tuple[UniverseConstituent, ...],
    profile: GateProfile,
) -> CoverageAssessment:
'''
_COVERAGE_REPLACEMENT = '''def _coverage(
    rows: tuple[UniverseConstituent, ...],
    profile: GateProfile,
    universe_id=None,
) -> CoverageAssessment:
'''
_THRESHOLD_ANCHOR = '''    reasons = []
    if not (
        MINIMUM_TOTAL_REPORTED_WEIGHT
        <= total_weight
        <= MAXIMUM_TOTAL_REPORTED_WEIGHT
    ):
        reasons.append("TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE")
    if mapping_ratio < MINIMUM_SID_NAME_MAPPING_RATIO:
        reasons.append("SID_NAME_MAPPING_BELOW_MINIMUM")
    if cap_ratio < profile.minimum_market_cap_weight_coverage_ratio:
        reasons.append("MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM")
'''
_THRESHOLD_REPLACEMENT = '''    policy = next((item for item in RELAXED_COVERAGE_POLICY if item[0] == universe_id), None)
    mapping_floor = MINIMUM_SID_NAME_MAPPING_RATIO if policy is None else Decimal(policy[1])
    cap_floor = profile.minimum_market_cap_weight_coverage_ratio if policy is None else Decimal(policy[2])
    total_floor = MINIMUM_TOTAL_REPORTED_WEIGHT if policy is None else Decimal(policy[3])
    reasons = []
    if not total_floor <= total_weight <= MAXIMUM_TOTAL_REPORTED_WEIGHT:
        reasons.append("TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE")
    if mapping_ratio < mapping_floor:
        reasons.append("SID_NAME_MAPPING_BELOW_MINIMUM")
    if cap_ratio < cap_floor:
        reasons.append("MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM")
    if policy is not None and sum(row.security_id is not None and row.security_name is not None and row.pit_market_cap is not None for row in rows) < policy[4]:
        reasons.append("KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM")
'''
_SELECTION_ANCHOR = '''    with localcontext() as context:
        context.prec = 96
        slot_weight = +(budget / Decimal(profile.slot_count))
'''
_SELECTION_REPLACEMENT = '''    if snapshot.universe_id == "XLE" and coverage.valid:
        eligible = sorted((row for row in rows if row.security_id is not None and row.security_name is not None and row.pit_market_cap is not None), key=lambda row: (-row.pit_market_cap, row.security_id))
        signal_ids = matched_ids = tuple(row.security_id for row in eligible[:profile.slot_count])
    slot_weight = _stock_slot_weight(coverage, budget, profile.slot_count, snapshot.universe_id)
'''
_SLOT_HELPER = '''def _stock_slot_weight(coverage, budget, slot_count, universe_id):
    with localcontext() as context:
        context.prec = 96
        if universe_id in tuple(item[0] for item in RELAXED_COVERAGE_POLICY):
            scale = min(Decimal(1), coverage.cap_weight_coverage_ratio * coverage.total_reported_weight)
            if scale < 1:
                return (budget * scale / Decimal(slot_count)).quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
        return +(budget / Decimal(slot_count))


'''


def render_gate_source(original_ascii, per_universe_policy_tuple):
    """Render verified-subset coverage and XLE cap selection, never guessed IDs.

    Policy entries are ``(universe, mapping_floor, cap_floor, total_floor, 5)``
    in QQQ/SOXX/REMX order; floors are exact decimal ASCII strings. Unknown
    members remain coverage denominators and cannot become selected names.
    """
    policy = _policy(per_universe_policy_tuple)
    if type(original_ascii) is not str or not original_ascii.isascii():
        raise RelaxedSelectionSourceError("relaxed source is not exact ASCII text")
    source = _replace(original_ascii,
        'PROFILE_SCHEMA = "arv2-six-universe-gate-profile-v1"',
        'PROFILE_SCHEMA = "arv2-six-universe-gate-relaxed-selection-profile-v1"')
    source = _replace(source,
        'CONSTRUCTION_SCHEMA = "arv2-six-universe-gate-construction-v1"',
        'CONSTRUCTION_SCHEMA = "arv2-six-universe-gate-relaxed-selection-construction-v1"')
    source = _replace(source, '\nSOURCE_VIEW_ID = ',
        "\nRELAXED_COVERAGE_POLICY = " + repr(policy) + "\nSOURCE_VIEW_ID = ")
    source = _replace(source, '        "minimum_positive_score_count": MINIMUM_POSITIVE_SCORE_COUNT,',
        '''        "minimum_positive_score_count": MINIMUM_POSITIVE_SCORE_COUNT,
        "xle_stock_entry_rule": "verified_cap_desc_sid_top10_independent_of_analyst_scores",
        "relaxed_universe_coverage_policy": [list(item) for item in RELAXED_COVERAGE_POLICY],
        "unresolved_coverage_stock_budget_rule": "QQQ_SOXX_REMX_budget_times_min_1_cap_coverage_times_reported_total_unresolved_slots_floor_to_1e-24_residual_own_ETF",
'''.rstrip())
    source = _replace(source,
        '"fallback_for_unfilled_slots;fewer_than_five_is_full_etf_fallback"',
        '"fallback_for_unfilled_slots;non_XLE_fewer_than_five_is_full_etf_fallback;XLE_cap_top10_independent_of_AR"')
    source = _replace(source, _COVERAGE_ANCHOR, _COVERAGE_REPLACEMENT)
    source = _replace(source, _THRESHOLD_ANCHOR, _THRESHOLD_REPLACEMENT)
    source = _replace(source, '        coverage = _coverage(rows, profile)',
        '        coverage = _coverage(rows, profile, snapshot.universe_id)')
    source = _replace(source, _SELECTION_ANCHOR, _SELECTION_REPLACEMENT)
    source = _replace(source, 'def _raw_sleeve(\n', _SLOT_HELPER + 'def _raw_sleeve(\n')
    return _normalize(source)


def render_targets_source(original_ascii):
    """Render honest unresolved-budget diagnostics using the gate's same rule."""
    if type(original_ascii) is not str or not original_ascii.isascii():
        raise RelaxedSelectionSourceError("relaxed source is not exact ASCII text")
    source = _replace(original_ascii,
        'SLEEVE_DIAGNOSTIC_SCHEMA = "arv2-six-universe-order-sleeve-diagnostic-v1"',
        'SLEEVE_DIAGNOSTIC_SCHEMA = "arv2-six-universe-order-relaxed-sleeve-diagnostic-v1"')
    source = _replace(source,
        '        slot_weight = +(sleeve.budget / Decimal(gate_profile.slot_count))',
        '        slot_weight = _gate._stock_slot_weight(sleeve.coverage, sleeve.budget, gate_profile.slot_count, sleeve.universe_id)')
    source = _replace(source,
        '    elif sleeve.positive_score_count < _gate.MINIMUM_POSITIVE_SCORE_COUNT:',
        '    elif sleeve.positive_score_count < _gate.MINIMUM_POSITIVE_SCORE_COUNT and sleeve.universe_id != "XLE":')
    source = _replace(source,
        '    elif len(selected_ids) < gate_profile.slot_count:',
        '''    elif slot_weight * Decimal(gate_profile.slot_count) < sleeve.budget:
        status = "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK"
    elif len(selected_ids) < gate_profile.slot_count:''')
    return _normalize(source)
