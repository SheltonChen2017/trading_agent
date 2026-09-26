"""Host-only exact successor rendering; frozen gate sources remain untouched."""

import ast
from decimal import Decimal
import re


class RelaxedSelectionSourceError(ValueError):
    """The prospective policy or an exact reviewed source anchor changed."""


RELAXED_UNIVERSES = ("QQQ", "SOXX", "REMX")
ALL25_UNIVERSES = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
ALL25_COVERAGE_POLICY = tuple((name, "0.25", "0.25", "0.25", 5)
                              for name in ALL25_UNIVERSES)


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
    return _render_gate_source(original_ascii, policy, all25=False)


def render_all25_gate_source(original_ascii, policy=ALL25_COVERAGE_POLICY):
    """Strict separate successor: all six numeric coverage floors are 25%.

    Five verified names, prior-time inputs, positive-score entry outside XLE,
    and the original finite upper bounds remain unchanged. Unresolved budget
    stays in each sleeve's own ETF rather than guessed security identities.
    """
    if (type(policy) is not tuple or len(policy) != 6
            or any(type(item) is not tuple or len(item) != 5
                   or any(type(value) is not str for value in item[:4])
                   or type(item[4]) is not int for item in policy)
            or policy != ALL25_COVERAGE_POLICY):
        raise RelaxedSelectionSourceError("all25 policy requires exact six-universe 25-percent floors")
    return _render_gate_source(original_ascii, policy, all25=True)


def render_full_ar_off_gate_source(original_ascii):
    """All25 coverage with cap-ranked stock entry/count independent of AR.

    Existing score input validation is retained, but the count diagnostic is
    explicitly zero/not-used and no score enters selection or construction.
    Five verified cap names, finite coverage, budget scaling and caps remain.
    """
    source = render_all25_gate_source(original_ascii)
    source = _replace(source, "arv2-six-universe-gate-all25-selection-profile-v1",
                      "arv2-six-universe-gate-full-ar-off-selection-profile-v1")
    source = _replace(source, "arv2-six-universe-gate-all25-selection-construction-v1",
                      "arv2-six-universe-gate-full-ar-off-selection-construction-v1")
    tree = ast.parse(source)
    selected = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "_selected_ids")
    selected.body = ast.parse('''
if not coverage.valid:
    return (), (), 0
cap_ranked = sorted((row for row in rows if row.security_id is not None
                    and row.security_name is not None and row.pit_market_cap is not None),
                    key=lambda row: (-row.pit_market_cap, row.security_id))
selected_ids = tuple(row.security_id for row in cap_ranked[:slot_count])
return selected_ids, selected_ids, 0
''').body
    # Profile semantics must describe the actual absence of score authority,
    # rather than retaining a positive-score entry rule in a new schema.
    class OffProfile(ast.NodeTransformer):
        def visit_Dict(self, node):
            self.generic_visit(node)
            replacements = {
                "minimum_positive_score_count": ast.Constant(0),
                "signal_rank_rule": ast.Constant("point_in_time_market_cap_desc_then_security_id_top10_independent_of_AR"),
                "matched_rank_rule": ast.Constant("point_in_time_market_cap_desc_then_security_id_top10_independent_of_AR"),
                "underfill_rule": ast.Constant("verified_cap_names_fill_up_to_ten_slots_unfilled_scaled_budget_stays_in_own_ETF"),
            }
            for index, key in enumerate(node.keys):
                if isinstance(key, ast.Constant) and key.value in replacements:
                    node.values[index] = replacements[key.value]
            if any(isinstance(key, ast.Constant) and key.value == "minimum_positive_score_count"
                   for key in node.keys):
                node.keys.append(ast.Constant("analyst_revision_usage"))
                node.values.append(ast.Constant("disabled_for_stock_entry_stock_count_and_weights_authenticated_score_clock_retained"))
                node.keys.append(ast.Constant("positive_score_count_diagnostic"))
                node.values.append(ast.Constant("zero_not_used_no_positive_entry_floor"))
            return node
    tree = OffProfile().visit(tree)
    ast.fix_missing_locations(tree)
    return _normalize(ast.unparse(tree) + "\n")


def render_full_ar_off_targets_source(original_ascii):
    """AR-off diagnostics and enrichment: scores cannot enter gate inputs."""
    source = render_all25_targets_source(original_ascii)
    source = _replace(source, "arv2-six-universe-order-all25-sleeve-diagnostic-v1",
                      "arv2-six-universe-order-full-ar-off-sleeve-diagnostic-v1")
    tree = ast.parse(source)
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "firm_specific_score":
            node.value = ast.Constant(None)
            count += 1
    if count != 1:
        raise RelaxedSelectionSourceError("full AR-off score enrichment exact anchor changed")
    class RemovePositiveFallback(ast.NodeTransformer):
        count = 0

        def visit_If(self, node):
            self.generic_visit(node)
            if ast.unparse(node.test) == "sleeve.positive_score_count < _gate.MINIMUM_POSITIVE_SCORE_COUNT and sleeve.universe_id != 'XLE'":
                self.count += 1
                return node.orelse
            return node
    remover = RemovePositiveFallback()
    tree = remover.visit(tree)
    if remover.count != 1:
        raise RelaxedSelectionSourceError("full AR-off positive fallback exact anchor changed")
    ast.fix_missing_locations(tree)
    return _normalize(ast.unparse(tree) + "\n")


def _render_gate_source(original_ascii, policy, *, all25):
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
    if all25:
        source = _replace(source, "arv2-six-universe-gate-relaxed-selection-profile-v1",
                          "arv2-six-universe-gate-all25-selection-profile-v1")
        source = _replace(source, "arv2-six-universe-gate-relaxed-selection-construction-v1",
                          "arv2-six-universe-gate-all25-selection-construction-v1")
        source = _replace(source,
            "QQQ_SOXX_REMX_budget_times_min_1_cap_coverage_times_reported_total_unresolved_slots_floor_to_1e-24_residual_own_ETF",
            "ALL_SIX_budget_times_min_1_cap_coverage_times_reported_total_unresolved_slots_floor_to_1e-24_residual_own_ETF")
    return _normalize(source)


def render_targets_source(original_ascii):
    """Render honest unresolved-budget diagnostics using the gate's same rule."""
    return _render_targets_source(original_ascii, all25=False)


def render_all25_targets_source(original_ascii):
    """New-schema diagnostics using all six sleeves' shared partial-budget rule."""
    return _render_targets_source(original_ascii, all25=True)


def _render_targets_source(original_ascii, *, all25):
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
    if all25:
        source = _replace(source, "arv2-six-universe-order-relaxed-sleeve-diagnostic-v1",
                          "arv2-six-universe-order-all25-sleeve-diagnostic-v1")
    return _normalize(source)
