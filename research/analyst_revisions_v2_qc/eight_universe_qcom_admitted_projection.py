"""Offline, versioned eight-universe order sources; no QC authority.

The first six sleeves and their order economics come from pinned QCOM-admitted
sources.  XLI and XLF are appended in that order.  This projection does not
assert that their historical QC constituent callbacks are usable: a separate
input-only diagnostic must prove that before any outcome launch.
"""

import ast
import dataclasses
import hashlib
import json
from decimal import Decimal

from . import accepted_risk_matched_historical_projection as matched
from . import accepted_risk_six_universe_order_qc_projection as base
from . import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from . import six_universe_qcom_exclusion_three_name_projection as three_name
from . import six_universe_qcom_restored_projection as restored
from . import six_universe_qcom_restored_score_floor1_projection as floor1


class EightUniverseProjectionError(ValueError):
    """The exact source parent, universe census, or economic anchor changed."""


UNIVERSES = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE", "XLI", "XLF")
ARMS = ("ar_off", *(f"ar_on{percent}" for percent in floor1.TILT_PERCENTS),
        "eight_etf_basket")
CANDIDATE_BY_ARM = dict(zip(ARMS, ("R268", "R269", "R270", "R271", "R272",
                                    "R273", "R274", "R275", "R276")))
PARENT_IDS = {
    "ar_off": ("R242", "R255", "e9bb937e7d4d1c629068be52cd803a226f50fb001c78589bdac34d6c2f118dc5"),
    "ar_on80": ("R243", "R260", "e12f5d60b77cec2a18f5c68b5cbc4c6a900c819c14aea462ca8b440350f2b801"),
    "ar_on100": ("R243", "R261", "932b76962609ae8ee17b55f7ce90ea3a30d75d5d949cc68127f88731faba7fb2"),
    "ar_on120": ("R244", "R262", "8dd192073cc4772170982904214154a2ddba3ca73763a269fafdd41b119e36b3"),
    "ar_on140": ("R243", "R263", "a2e05e106752d6f429795010ad6635b25969756f03e9433303a801ef7b59b990"),
    "ar_on160": ("R243", "R264", "a0ce043a5fa34d228f1fa628885e69617e06852d910c503de6df487ecbe0a072"),
    "ar_on180": ("R243", "R265", "965e8ce9a85ca4525831b9e1c5177f2fe43e1f200b953bc0b1715acfae55d2dd"),
    "ar_on200": ("R245", "R266", "6e0cf5b25f845ae85dedb509f47e31197c86cbc4c5f453b033f96c106133cdb0"),
    "eight_etf_basket": ("R242", "R255", "e9bb937e7d4d1c629068be52cd803a226f50fb001c78589bdac34d6c2f118dc5"),
}
NEW_POLICY_ID = "all_eight_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1"
OFF_POLICY_ID = "all_eight_minimum_mapping_cap_total_10pct_verified_names_3_ar_off_v1"
NEW_POLICY = three_name.COVERAGE_POLICY + (("XLI", "0.10", "0.10", "0.10", 3),
                                           ("XLF", "0.10", "0.10", "0.10", 3))
STATISTIC_NAMES = ("ARV2_EIGHT_GATE_ORDER_META", "ARV2_EIGHT_GATE_ORDER_AGGREGATES",
                   "ARV2_EIGHT_GATE_ORDER_DIAGNOSTICS")
_GATE = relaxed._GATE_PATH
_RUNTIME = restored._ORDER
_TILT_RUNTIME = relaxed._TILT_RUNTIME_PATH
_MAIN = "main.py"
_DIAGNOSTICS = "accepted_risk_matched_diagnostics.py"
_TARGETS = relaxed._TARGET_PATH
_TILT_TARGETS = relaxed._TILT_TARGET_PATH
_SIX = UNIVERSES[:6]


def _fail(message):
    raise EightUniverseProjectionError(message)


def _assignment(tree, name):
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
               and node.targets[0].id == name]
    if len(matches) != 1:
        _fail(f"eight-universe assignment anchor changed: {name}")
    return matches[0]


def _render(path, source, *, parent_id, new_id, basket):
    if type(source) is not str or not source.isascii():
        _fail("eight-universe parent source is not exact ASCII")
    if basket and path in (_TARGETS, _TILT_TARGETS):
        source = matched._render_basket(path, source)
    tree = ast.parse(source)
    old_slug, new_slug = parent_id.lower(), new_id.lower()
    old_policy = (three_name.COVERAGE_POLICY_ID if basket or parent_id == "R255"
                  else floor1.COVERAGE_POLICY_ID)
    new_policy = OFF_POLICY_ID if parent_id == "R255" else NEW_POLICY_ID
    counts = {"marker": 0, "policy": 0, "statistics": 0,
              "six_schema": 0, "loops": 0, "basket_arm": 0}

    class Version(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is not str:
                return node
            value = node.value
            if value == old_policy:
                value = new_policy
                counts["policy"] += 1
            if "arv2-six-" in value:
                value = value.replace("arv2-six-", "arv2-eight-")
                counts["six_schema"] += 1
            if "ALL_SIX_budget_times_" in value:
                value = value.replace("ALL_SIX_budget_times_", "ALL_EIGHT_budget_times_")
            if "all_six_ETFs_have_" in value:
                value = value.replace("all_six_ETFs_have_", "all_eight_ETFs_have_")
            for before, after in ((f"qcom_admitted_{old_slug}", f"qcom_admitted_{new_slug}_eight"),
                                  (f"qcom-admitted-{old_slug}", f"qcom-admitted-{new_slug}-eight"),
                                  (f"QCOM-admitted-{parent_id}", f"QCOM-admitted-{new_id}-eight")):
                if before in value:
                    value = value.replace(before, after)
                    counts["marker"] += 1
            if "ARV2_SIX_GATE_ORDER_" in value:
                value = value.replace("ARV2_SIX_GATE_ORDER_", "ARV2_EIGHT_GATE_ORDER_")
                counts["statistics"] += 1
            if path == _DIAGNOSTICS and value == "six_etf_panel_row_count":
                value = "eight_etf_panel_row_count"
            if value == "six_etf_basket":
                value = "eight_etf_basket"
            elif value == "six_frozen_sleeve_budgets_in_actual_etfs":
                value = "eight_frozen_sleeve_budgets_in_actual_etfs"
            node.value = value
            return node

        def visit_ClassDef(self, node):
            if path == _MAIN and f"QcomAdmitted{parent_id}" in node.name:
                node.name = node.name.replace(f"QcomAdmitted{parent_id}",
                    f"QcomAdmitted{new_id}Eight")
            return self.generic_visit(node)

    tree = Version().visit(tree)
    if path == _GATE:
        specs = _assignment(tree, "UNIVERSE_SPECS")
        coverage = _assignment(tree, "RELAXED_COVERAGE_POLICY")
        if (not isinstance(specs.value, ast.Tuple) or len(specs.value.elts) != 6
                or any(not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name)
                       or item.func.id != "UniverseSpec" or len(item.args) != 2
                       or not all(isinstance(arg, ast.Constant) for arg in item.args)
                       or (item.args[0].value, item.args[1].value) != (name, name)
                       for item, name in zip(specs.value.elts, _SIX))
                or ast.literal_eval(coverage.value) != three_name.COVERAGE_POLICY):
            _fail("eight-universe parent six-member census changed")
        for name in UNIVERSES[6:]:
            specs.value.elts.append(ast.Call(ast.Name("UniverseSpec", ast.Load()),
                                              [ast.Constant(name), ast.Constant(name)], []))
        coverage.value = ast.parse(repr(NEW_POLICY), mode="eval").body
        if parent_id == "R255":
            floor = _assignment(tree, "MINIMUM_POSITIVE_SCORE_COUNT")
            if not isinstance(floor.value, ast.Constant) or floor.value.value != 3:
                _fail("eight-universe AR-off unused score-floor ancestor changed")
    if path == _MAIN:
        loops = [node for node in ast.walk(tree) if isinstance(node, ast.For)
                 and isinstance(node.iter, ast.Tuple)
                 and tuple(item.value for item in node.iter.elts
                           if isinstance(item, ast.Constant)) == _SIX]
        if len(loops) != 2:
            _fail("eight-universe main ETF and callback loops changed")
        for loop in loops:
            loop.iter.elts.extend(ast.Constant(name) for name in UNIVERSES[6:])
        counts["loops"] = 2
        if basket:
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id == "install_matched_diagnostics"
                     and len(node.args) == 3 and isinstance(node.args[1], ast.Constant)
                     and node.args[1].value == "ar_off"]
            if len(calls) != 1:
                _fail("eight-ETF diagnostic arm anchor changed")
            calls[0].args[1].value = "eight_etf_basket"
            counts["basket_arm"] += 1
    if path == _RUNTIME:
        bound = _assignment(tree, "MAXIMUM_STATISTIC_BYTES")
        if not isinstance(bound.value, ast.Constant) or bound.value.value != 8192:
            _fail("eight-universe statistic bound ancestor changed")
        bound.value.value = 16_384
    if basket and path == _TILT_RUNTIME:
        changed = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [key.value if isinstance(key, ast.Constant) else None for key in node.keys]
            if "comparison_arm" in keys:
                index = keys.index("comparison_arm")
                if (not isinstance(node.values[index], ast.Constant)
                        or node.values[index].value != "ar_off"):
                    _fail("eight-ETF comparison arm anchor changed")
                node.values[index].value = "eight_etf_basket"
                changed += 1
        if changed != 2:
            _fail("eight-ETF profile and aggregate arm census changed")
        counts["basket_arm"] += changed
    if basket and path == _TILT_TARGETS:
        rank = _assignment(tree, "TILT_RANK_RULE_ID")
        if not isinstance(rank.value, ast.Constant):
            _fail("eight-ETF disabled-rank anchor changed")
        rank.value.value = "disabled_eight_ETF_budget_basket_v1"
    if path == _DIAGNOSTICS:
        for name, old, new in (
            ("SCHEMA", "arv2-matched-historical-diagnostics-v1",
             "arv2-eight-matched-historical-diagnostics-v1"),
            ("REFERENCE_REPAIR_SCHEMA", "arv2-matched-historical-diagnostics-v2-closing-minute",
             "arv2-eight-matched-historical-diagnostics-v2-closing-minute"),
        ):
            value = _assignment(tree, name).value
            if not isinstance(value, ast.Constant) or value.value != old:
                _fail("eight-universe diagnostic schema ancestor changed")
            value.value = new
        for old, new in ((7530, 10040), (30, 40)):
            values = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)
                      and type(node.value) is int and node.value == old]
            if len(values) != 1:
                _fail("eight-universe diagnostic geometry ancestor changed")
            values[0].value = new
        if basket:
            # Both installation and validation accept the new public basket arm.
            tuples = [node for node in ast.walk(tree) if isinstance(node, ast.Tuple)
                      and all(isinstance(item, ast.Constant) for item in node.elts)
                      and tuple(item.value for item in node.elts)
                      == ("ar_off", "ar_on100", "eight_etf_basket")]
            if len(tuples) != 2:
                _fail("eight-ETF diagnostic accepted-arm census changed")
    if (path == _GATE and counts["policy"] != 1
            or path == _TILT_RUNTIME and counts["policy"] != 2
            or path not in (_GATE, _TILT_RUNTIME) and counts["policy"] != 0
            or counts["loops"] != (2 if path == _MAIN else 0)
            or basket and counts["basket_arm"] != (1 if path == _MAIN else
                                                    2 if path == _TILT_RUNTIME else 0)):
        _fail(f"eight-universe versioning anchor changed in {path}: {counts}")
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(rendered), include_attributes=False):
        _fail("eight-universe rendered AST changed")
    return rendered


def _parent(package, arm):
    source_id, parent_id, pin = PARENT_IDS[arm]
    if arm.startswith("ar_on"):
        predecessor, old_profile = floor1.build_qcom_admitted_score_floor1_projection(
            package, int(arm[5:]), parent_id)
    else:
        predecessor, old_profile = restored.build_qcom_admitted_projection(
            package, source_id, parent_id)
    if predecessor.projection_sha256 != pin:
        _fail("eight-universe frozen source projection changed")
    return predecessor, old_profile, parent_id


def build_eight_universe_projection(package, arm, new_candidate_id):
    """Return one 17-file source and profile, with no cloud or outcome action."""
    if (type(arm) is not str or arm not in ARMS
            or type(new_candidate_id) is not str
            or new_candidate_id != CANDIDATE_BY_ARM[arm]):
        _fail("eight-universe arm or new candidate identity is invalid")
    predecessor, old_profile, parent_id = _parent(package, arm)
    basket = arm == "eight_etf_basket"
    sources = {item.project_path: _render(item.project_path,
        item.source_bytes.decode("ascii"), parent_id=parent_id,
        new_id=new_candidate_id, basket=basket) for item in predecessor.source_files}
    with relaxed._cloud_loader(sources) as (load, _):
        gate = load(_GATE[:-3])
        if (gate.UNIVERSE_IDS != UNIVERSES or gate.RELAXED_COVERAGE_POLICY != NEW_POLICY
                or gate.MINIMUM_POSITIVE_SCORE_COUNT != (3 if arm in ("ar_off", "eight_etf_basket") else 1)
                or gate.DIRECT_STOCK_WEIGHT_CAP != Decimal("0.098")
                or gate.SLEEVE_BUDGETS != (Decimal("0.1225"),) * 8
                or hasattr(gate, "EXCLUDED_QCOM_SECURITY_ID")):
            _fail("eight-universe construction, admission, or cap changed")
        baseline = load(relaxed._BRIDGE_NAME).require_bridge_profile("matched")
        sources[_TILT_RUNTIME] = relaxed._replace(sources[_TILT_RUNTIME],
            old_profile["matched_baseline_profile_sha256"], baseline["profile_sha256"])
        runtime = load(_TILT_RUNTIME[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        expected_arm = arm
        if (profile.get("coverage_policy_id") != (
                OFF_POLICY_ID if arm in ("ar_off", "eight_etf_basket") else NEW_POLICY_ID)
                or profile.get("comparison_arm") != expected_arm
                or profile.get("matched_baseline_profile_sha256") != baseline["profile_sha256"]
                or profile.get("target_gross_exposure") != "0.98"
                or profile.get("modeled_fee_bps_per_side") != "10"
                or profile.get("slippage_bps") != "0"
                or profile.get("admission_leverage") != "2"
                or profile.get("maximum_stock_weight_change_fraction") != (
                    f"{int(arm[5:]) // 100}.{int(arm[5:]) % 100:02d}"
                    if arm.startswith("ar_on") else "0.00")
                or load(_RUNTIME[:-3]).MAXIMUM_STATISTIC_BYTES != 16_384
                or load(_DIAGNOSTICS[:-3]).MAXIMUM_STATISTIC_BYTES != 8192):
            _fail("eight-universe profile, economics, or transport changed")
    files = tuple(sorted((base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + base.MINIMUM_REVIEW_MARGIN_BYTES > base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _fail("eight-universe source closure exceeded unchanged QC budgets")
    for item in files:
        base._audit_source(item.project_path, item.source_bytes)
    semantic = dataclasses.replace(predecessor,
        schema=f"arv2-eight-qcom-admitted-{new_candidate_id.lower()}-projection-v1",
        role=profile["role"], variant=(predecessor.variant.replace(
            f"qcom_admitted_{parent_id.lower()}",
            f"qcom_admitted_{new_candidate_id.lower()}_eight") + "_eight_universe_v1"),
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    record = {key: item for key, item in semantic.to_record().items()
              if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(base._canonical(record)).hexdigest()
    return dataclasses.replace(semantic, projection_sha256=digest,
        projection_id=f"arv2-eight-qcom-admitted-{new_candidate_id.lower()}-projection-"
                      + digest[:24]), json.loads(base._canonical(profile))
