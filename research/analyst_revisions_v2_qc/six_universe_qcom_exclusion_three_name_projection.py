"""Separate three-verified-name source closure for QCOM-excluded order studies.

Only the six-sleeve verified-name minimum and the active non-XLE positive
analyst-score entry minimum change, each from five to three. The 10% coverage
floors, unknown-ID exclusion, QCOM direct-stock exclusion, residual own-ETF
budget, and physical-order economics retain their predecessor behavior.
"""

import ast
import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_relaxed_qc_projection as _relaxed
from . import six_universe_qcom_exclusion_coverage10_projection as _prior


class QcomThreeNameProjectionError(ValueError):
    """A frozen predecessor or exact policy/source anchor has changed."""


ARMS = ("ar_off", "ar_on80", "ar_on120", "ar_on200")
COVERAGE_POLICY_ID = "all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_3_v1"
COVERAGE_POLICY = tuple((name, "0.10", "0.10", "0.10", 3)
                        for name in _prior._selection.ALL25_UNIVERSES)
PREDECESSOR_PROJECTION_SHA256 = {
    "ar_off": "26e4680967e6f4a6bc66b0fe7c3e4198cdab1db2f1a7357878f01952560fd654",
    "ar_on80": "b3037679192d13cd931f22dd27ff7443ea328d17a7bed5d294bed3754f97dc9d",
    "ar_on120": "bf62a1fcf62bee8d63a739d88220a8d8764a30b889baaa1bca0ef025a7264f4f",
    "ar_on200": "ddaf84b437d347f43f789377b9629f90120d8418edfed3e7c596cfecf7e33f18",
}
_RULE_OLD = (
    "five_to_slot_count_uses_available_stock_slots_and_own_etf_fallback_for_unfilled_slots;"
    "non_XLE_fewer_than_five_is_full_etf_fallback;XLE_cap_top10_independent_of_AR"
)
_RULE_NEW = (
    "three_to_slot_count_uses_available_stock_slots_and_own_etf_fallback_for_unfilled_slots;"
    "non_XLE_fewer_than_three_is_full_etf_fallback;XLE_cap_top10_independent_of_AR"
)


def _fail(message):
    raise QcomThreeNameProjectionError(message)


def _assignment(tree, name):
    matches = [node for node in tree.body
               if isinstance(node, ast.Assign) and len(node.targets) == 1
               and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    if len(matches) != 1:
        _fail(f"three-name exact assignment anchor changed: {name}")
    return matches[0]


def _render_source(path, source, predecessor, arm):
    if path not in {*_prior._SCHEMA_ASSIGNMENTS, "main.py"}:
        return source
    if type(source) is not str or not source.isascii():
        _fail("three-name predecessor source is not exact ASCII")
    tree = ast.parse(source)
    old_role = predecessor.role
    old_variant = predecessor.variant
    old_profile_id = predecessor.profile_id
    old_policy = _prior.COVERAGE_POLICY_ID
    new_role = f"matched_qcom_excluded_three_name_{arm}_s0"
    new_variant = f"three_name_matched_qcom_excluded_{arm}_s0_v1"
    new_profile_id = f"arv2-six-matched-qcom-excluded-three-name-{arm}-s0-profile-v1"
    counts = {"role": 0, "variant": 0, "profile_id": 0, "policy": 0, "rule": 0}

    class Identity(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is str:
                replacements = {
                    old_role: (new_role, "role"),
                    old_variant: (new_variant, "variant"),
                    old_profile_id: (new_profile_id, "profile_id"),
                    old_policy: (COVERAGE_POLICY_ID, "policy"),
                    _RULE_OLD: (_RULE_NEW, "rule"),
                }
                replacement = replacements.get(node.value)
                if replacement is not None:
                    node.value = replacement[0]
                    counts[replacement[1]] += 1
            return node

        def visit_ClassDef(self, node):
            expected = (f"ARV2MatchedHistorical{arm.title().replace('_', '')}"
                        "S0QcomExcludedCoverage10Algorithm")
            if path == "main.py" and node.name == expected:
                node.name = expected.replace("Coverage10Algorithm", "ThreeNameAlgorithm")
                counts["class"] = counts.get("class", 0) + 1
            return self.generic_visit(node)

    tree = Identity().visit(tree)
    if (counts != {"role": _prior._ROLE_COUNTS.get(path, 0),
                   "variant": _prior._VARIANT_COUNTS.get(path, 0),
                   "profile_id": int(path == _relaxed._TILT_RUNTIME_PATH),
                   "policy": (1 if path == _relaxed._GATE_PATH else
                              2 if path == _relaxed._TILT_RUNTIME_PATH else 0),
                   "rule": int(path == _relaxed._GATE_PATH and arm != "ar_off"),
                   **({"class": 1} if path == "main.py" else {})}):
        _fail(f"three-name role, profile, or policy anchor changed in {path}: {counts}")

    expected_names = _prior._SCHEMA_ASSIGNMENTS.get(path, ())
    for name in expected_names:
        assignment = _assignment(tree, name)
        if (not isinstance(assignment.value, ast.Constant)
                or type(assignment.value.value) is not str
                or "coverage10" not in assignment.value.value):
            _fail(f"three-name schema anchor changed in {path}: {name}")
        assignment.value.value = assignment.value.value.replace("coverage10", "three-name")
    if path == _relaxed._GATE_PATH:
        policy = _assignment(tree, "RELAXED_COVERAGE_POLICY")
        if ast.literal_eval(policy.value) != _prior.COVERAGE_POLICY:
            _fail("three-name predecessor coverage policy changed")
        policy.value = ast.parse(repr(COVERAGE_POLICY), mode="eval").body
        positive = _assignment(tree, "MINIMUM_POSITIVE_SCORE_COUNT")
        if not isinstance(positive.value, ast.Constant) or positive.value.value != 5:
            _fail("three-name positive-score threshold anchor changed")
        positive.value.value = 3
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(rendered), include_attributes=False):
        _fail("three-name source formatting changed executable AST")
    return rendered


def build_qcom_exclusion_three_name_projection(package, arm):
    """Return one immutable, separately identified 2021--2025 order arm."""
    if type(arm) is not str or arm not in ARMS:
        _fail("three-name arm must be ar_off or ar_on80/120/200")
    predecessor, prior_profile = _prior.build_qcom_exclusion_coverage10_projection(package, arm)
    if predecessor.projection_sha256 != PREDECESSOR_PROJECTION_SHA256[arm]:
        _fail("three-name frozen 10%-coverage predecessor changed")
    sources = {item.project_path: _render_source(
        item.project_path, item.source_bytes.decode("ascii"), predecessor, arm)
        for item in predecessor.source_files}
    with _relaxed._cloud_loader(sources) as (load, _):
        bridge = load(_relaxed._BRIDGE_NAME)
        baseline = bridge.require_bridge_profile("matched")
        sources[_relaxed._TILT_RUNTIME_PATH] = _relaxed._replace(
            sources[_relaxed._TILT_RUNTIME_PATH],
            prior_profile["matched_baseline_profile_sha256"], baseline["profile_sha256"])
        gate = load(_relaxed._GATE_PATH[:-3])
        if gate.RELAXED_COVERAGE_POLICY != COVERAGE_POLICY or gate.MINIMUM_POSITIVE_SCORE_COUNT != 3:
            _fail("three-name gate policy or positive-score floor changed")
        runtime = load(_relaxed._TILT_RUNTIME_PATH[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        expected = {
            "role": f"matched_qcom_excluded_three_name_{arm}_s0",
            "profile_id": f"arv2-six-matched-qcom-excluded-three-name-{arm}-s0-profile-v1",
            "schema": f"arv2-six-matched-qcom-excluded-three-name-{arm}-profile-v1",
            "comparison_arm": arm,
            "coverage_policy_id": COVERAGE_POLICY_ID,
            "matched_baseline_profile_sha256": baseline["profile_sha256"],
            "stock_exclusion_policy_id": prior_profile["stock_exclusion_policy_id"],
            "excluded_logical_security_sha256": prior_profile["excluded_logical_security_sha256"],
            "maximum_stock_weight_change_fraction": prior_profile[
                "maximum_stock_weight_change_fraction"],
            "target_gross_exposure": "0.98",
            "modeled_fee_bps_per_side": "10",
            "slippage_bps": "0",
            "admission_leverage": "2",
        }
        if any(profile.get(key) != value for key, value in expected.items()):
            _fail("three-name matched order profile or economics changed")
        expected_meta = f"arv2-six-matched-qcom-excluded-three-name-{arm}-meta-v1"
        expected_summary = f"arv2-six-matched-qcom-excluded-three-name-{arm}-summary-v1"
        if (runtime.TILT_META_SCHEMA != expected_meta
                or runtime.TILT_SUMMARY_SCHEMA != expected_summary
                or load("accepted_risk_six_universe_order_qc_runtime").META_SCHEMA
                != expected_meta):
            _fail("three-name result transport schemas changed")
    files = tuple(sorted((_base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _fail("three-name source closure exceeded unchanged QC budgets")
    for item in files:
        _base._audit_source(item.project_path, item.source_bytes)
    value = dataclasses.replace(predecessor,
        schema=f"arv2-six-matched-qcom-excluded-three-name-{arm}-projection-v1",
        role=profile["role"],
        variant=f"three_name_matched_qcom_excluded_{arm}_s0_v1",
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id="arv2-six-matched-qcom-excluded-three-name-projection-" + digest[:24]), json.loads(
            _base._canonical(profile))
