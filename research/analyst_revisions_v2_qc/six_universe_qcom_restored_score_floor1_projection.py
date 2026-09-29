"""Prospective QCOM-admitted, three-verified-name, one-positive-score sources.

The seven AR-on tilt strengths are source projections, not QC outcomes.  The
80/120/200% parents are the exact frozen R256/R257/R258 closures; intervening
tilts are exact, audited transfer-strength rewrites of R256.  Only the non-XLE
positive-score entry floor changes from three to one.  The six 10% coverage
floors, three-verified-name floor, XLE cap rule, and order economics remain.
"""

import ast
import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as base
from . import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from . import six_universe_qcom_exclusion_three_name_projection as three_name
from . import six_universe_qcom_restored_projection as restored


class QcomRestoredScoreFloor1ProjectionError(ValueError):
    """A pinned source, identity, or exact economic rewrite anchor changed."""


TILT_PERCENTS = (80, 100, 120, 140, 160, 180, 200)
PARENT_BY_PERCENT = {
    80: ("R243", "R256", "7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924"),
    100: ("R243", "R256", "7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924"),
    120: ("R244", "R257", "6fec1642589062cc6810250fda9d8be70f83bd7c4c5f771d65a8e480de0d99a3"),
    140: ("R243", "R256", "7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924"),
    160: ("R243", "R256", "7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924"),
    180: ("R243", "R256", "7f53404c5bad44996dde2c2cec7d8fb30983f63384d431d0e6c005058288e924"),
    200: ("R245", "R258", "ae6ee5ee842e9b39c41d8f07fbd44377fb28fa05143c8bf652ee60021fd7df60"),
}
COVERAGE_POLICY_ID = (
    "all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1"
)
_OLD_RULE = three_name._RULE_NEW
_NEW_RULE = _OLD_RULE.replace(
    "non_XLE_fewer_than_three_is_full_etf_fallback",
    "non_XLE_fewer_than_one_is_full_etf_fallback",
)
_GATE = relaxed._GATE_PATH
_TARGET = relaxed._TILT_TARGET_PATH
_RUNTIME = relaxed._TILT_RUNTIME_PATH
_ORDER = restored._ORDER
_MAIN = "main.py"
_DIAGNOSTICS = "accepted_risk_matched_diagnostics.py"


def _fail(message):
    raise QcomRestoredScoreFloor1ProjectionError(message)


def _assignment(tree, name):
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
               and node.targets[0].id == name]
    if len(matches) != 1:
        _fail(f"score-floor1 assignment anchor changed: {name}")
    return matches[0]


def _render_source(path, source, *, old_id, old_percent, percent, new_id):
    if type(source) is not str or not source.isascii():
        _fail("score-floor1 parent source must be exact ASCII")
    tree = ast.parse(source)
    old_slug, new_slug = old_id.lower(), new_id.lower()
    old_marker = f"qcom_admitted_{old_slug}"
    new_marker = f"qcom_admitted_{new_slug}_score_floor1"
    old_hyphen = f"qcom-admitted-{old_slug}"
    new_hyphen = f"qcom-admitted-{new_slug}-score-floor1"
    counts = {"identity": 0, "policy": 0, "rule": 0, "arm": 0,
              "tilt": 0, "fraction": 0, "description": 0, "class": 0,
              "diagnostic_arm": 0, "diagnostic_allowed_arms": 0}

    class Rewrite(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is not str:
                return node
            value = node.value
            if value == three_name.COVERAGE_POLICY_ID:
                counts["policy"] += 1
                value = COVERAGE_POLICY_ID
            if value == _OLD_RULE:
                counts["rule"] += 1
                value = _NEW_RULE
            if old_percent != percent and path in (_TARGET, _RUNTIME, _MAIN):
                old_arm, new_arm = f"ar_on{old_percent}", f"ar_on{percent}"
                if old_arm in value:
                    counts["arm"] += 1
                    value = value.replace(old_arm, new_arm)
                old_tilt, new_tilt = f"tilt{old_percent}", f"tilt{percent}"
                if old_tilt in value:
                    counts["tilt"] += 1
                    value = value.replace(old_tilt, new_tilt)
                old_fraction = f"{old_percent // 100}.{old_percent % 100:02d}"
                if value == old_fraction:
                    counts["fraction"] += 1
                    value = f"{percent // 100}.{percent % 100:02d}"
                old_phrase = f"bounded by {old_percent}% of its own post-cap"
                if old_phrase in value:
                    counts["description"] += 1
                    value = value.replace(old_phrase,
                        f"bounded by {percent}% of its own post-cap")
            for before, after in ((old_marker, new_marker), (old_hyphen, new_hyphen),
                                  (f"QCOM-admitted-{old_id}",
                                   f"QCOM-admitted-{new_id}-score-floor1")):
                if before in value:
                    counts["identity"] += 1
                    value = value.replace(before, after)
            node.value = value
            return node

        def visit_ClassDef(self, node):
            if path == _MAIN and f"QcomAdmitted{old_id}" in node.name:
                counts["class"] += 1
                node.name = node.name.replace(f"QcomAdmitted{old_id}",
                    f"QcomAdmitted{new_id}ScoreFloor1")
                if old_percent != percent:
                    node.name = node.name.replace(f"ArOn{old_percent}", f"ArOn{percent}")
            return self.generic_visit(node)

        def visit_Call(self, node):
            if (path == _MAIN and isinstance(node.func, ast.Name)
                    and node.func.id == "install_matched_diagnostics"
                    and len(node.args) == 3 and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value == "ar_on100"
                    and isinstance(node.args[2], ast.Constant) and node.args[2].value == 0):
                counts["diagnostic_arm"] += 1
                node.args[1].value = f"ar_on{percent}"
            return self.generic_visit(node)

        def visit_Tuple(self, node):
            if (path == _DIAGNOSTICS and all(isinstance(item, ast.Constant)
                    for item in node.elts)
                    and tuple(item.value for item in node.elts)
                    == ("ar_off", "ar_on100", "six_etf_basket")):
                counts["diagnostic_allowed_arms"] += 1
                node.elts = [ast.Constant(value=value) for value in
                    ("ar_off", *(f"ar_on{value}" for value in TILT_PERCENTS),
                     "six_etf_basket")]
            return self.generic_visit(node)

    tree = Rewrite().visit(tree)
    if path == _GATE:
        floor = _assignment(tree, "MINIMUM_POSITIVE_SCORE_COUNT")
        policy = _assignment(tree, "RELAXED_COVERAGE_POLICY")
        if (not isinstance(floor.value, ast.Constant) or type(floor.value.value) is not int
                or floor.value.value != 3
                or ast.literal_eval(policy.value) != three_name.COVERAGE_POLICY):
            _fail("score-floor1 positive-score or three-name coverage anchor changed")
        floor.value.value = 1
    if path == _ORDER:
        meta = _assignment(tree, "META_SCHEMA")
        expected_old = (f"arv2-six-matched-qcom-admitted-{new_slug}-score-floor1-"
                        f"three-name-ar_on{old_percent}-meta-v1")
        if (not isinstance(meta.value, ast.Constant)
                or meta.value.value != expected_old):
            _fail("score-floor1 order META schema anchor changed")
        meta.value.value = (f"arv2-six-matched-qcom-admitted-{new_slug}-score-floor1-"
                            f"three-name-ar_on{percent}-meta-v1")
    expected_policy = 1 if path == _GATE else 2 if path == _RUNTIME else 0
    if (counts["policy"] != expected_policy or counts["rule"] != int(path == _GATE)
            or counts["class"] != int(path == _MAIN)
            or counts["diagnostic_arm"] != int(path == _MAIN)
            or counts["diagnostic_allowed_arms"] != 2 * int(path == _DIAGNOSTICS)):
        _fail(f"score-floor1 policy, rule, or diagnostics anchor changed in {path}: {counts}")
    if old_percent != percent:
        expected = {
            _TARGET: {"arm": 4, "tilt": 3, "fraction": 2, "description": 1},
            _RUNTIME: {"arm": 7, "tilt": 0, "fraction": 2, "description": 0},
            _MAIN: {"arm": 2, "tilt": 0, "fraction": 0, "description": 0},
        }.get(path, {"arm": 0, "tilt": 0, "fraction": 0, "description": 0})
        if any(counts[key] != value for key, value in expected.items()):
            _fail(f"score-floor1 tilt exact source anchor changed in {path}: {counts}")
    if not counts["identity"] and path not in (_GATE, _RUNTIME, _MAIN, _TARGET, _DIAGNOSTICS):
        return source
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(rendered), include_attributes=False):
        _fail("score-floor1 formatting changed executable AST")
    return rendered


def build_qcom_admitted_score_floor1_projection(package, percent, new_candidate_id):
    """Build a separately identified 17-file order closure; never launch QC.

    The caller chooses a fresh R-number and must freeze its source/profile
    hashes before any authorized exploratory QC run. No ID is assigned here.
    """
    if (type(percent) is not int or percent not in TILT_PERCENTS
            or type(new_candidate_id) is not str
            or not restored._CANDIDATE_ID.fullmatch(new_candidate_id)
            or int(new_candidate_id[1:]) <= 259):
        _fail("score-floor1 percent or fresh candidate identity is invalid")
    old_source_id, old_id, pinned_sha = PARENT_BY_PERCENT[percent]
    old_percent = {"R256": 80, "R257": 120, "R258": 200}[old_id]
    predecessor, old_profile = restored.build_qcom_admitted_projection(
        package, old_source_id, old_id)
    if predecessor.projection_sha256 != pinned_sha:
        _fail("score-floor1 frozen QCOM-admitted predecessor changed")
    sources = {item.project_path: _render_source(item.project_path,
        item.source_bytes.decode("ascii"), old_id=old_id, old_percent=old_percent,
        percent=percent, new_id=new_candidate_id) for item in predecessor.source_files}
    if any(token in body for body in sources.values() for token in (
            f"qcom_admitted_{old_id.lower()}", f"qcom-admitted-{old_id.lower()}",
            f"QcomAdmitted{old_id}")):
        _fail("score-floor1 source retains parent identity")
    with relaxed._cloud_loader(sources) as (load, _):
        baseline = load(relaxed._BRIDGE_NAME).require_bridge_profile("matched")
        sources[_RUNTIME] = relaxed._replace(sources[_RUNTIME],
            old_profile["matched_baseline_profile_sha256"], baseline["profile_sha256"])
        gate = load(_GATE[:-3])
        if (gate.RELAXED_COVERAGE_POLICY != three_name.COVERAGE_POLICY
                or gate.MINIMUM_POSITIVE_SCORE_COUNT != 1
                or hasattr(gate, "EXCLUDED_QCOM_SECURITY_ID")):
            _fail("score-floor1 gate coverage, count, or QCOM admission changed")
        runtime = load(_RUNTIME[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        expected = {
            "coverage_policy_id": COVERAGE_POLICY_ID,
            "comparison_arm": f"ar_on{percent}",
            "maximum_stock_weight_change_fraction":
                f"{percent // 100}.{percent % 100:02d}",
            "matched_baseline_profile_sha256": baseline["profile_sha256"],
            "target_gross_exposure": "0.98", "modeled_fee_bps_per_side": "10",
            "slippage_bps": "0", "admission_leverage": "2",
        }
        if any(profile.get(key) != value for key, value in expected.items()):
            _fail("score-floor1 profile, tilt, or order economics changed")
        allowed_changes = {
            "role", "profile_id", "schema", "profile_sha256", "coverage_policy_id",
            "matched_baseline_profile_sha256", "comparison_arm",
            "maximum_stock_weight_change_fraction", "target_path_schema",
            "decision_target_schema", "cap90_predecessor_profile_sha256",
            "gate_profile_id", "gate_profile_sha256", "evaluation_profile_id",
            "evaluation_profile_sha256",
        }
        if (profile.keys() != old_profile.keys()
                or any(profile[key] != value for key, value in old_profile.items()
                       if key not in allowed_changes)):
            _fail("score-floor1 changed an unrelated profile field")
    files = tuple(sorted((base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()),
                         key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + base.MINIMUM_REVIEW_MARGIN_BYTES > base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _fail("score-floor1 source closure exceeded unchanged QC budgets")
    for item in files:
        base._audit_source(item.project_path, item.source_bytes)
    old_marker = f"qcom_admitted_{old_id.lower()}"
    new_marker = f"qcom_admitted_{new_candidate_id.lower()}_score_floor1"
    if predecessor.variant.count(old_marker) != 1:
        _fail("score-floor1 predecessor variant identity changed")
    value = dataclasses.replace(predecessor,
        schema=f"arv2-six-qcom-admitted-{new_candidate_id.lower()}-score-floor1-projection-v1",
        role=profile["role"], variant=predecessor.variant.replace(old_marker, new_marker)
            .replace(f"ar_on{old_percent}", f"ar_on{percent}"),
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id=f"arv2-six-qcom-admitted-{new_candidate_id.lower()}-score-floor1-projection-"
                      + digest[:24]), json.loads(base._canonical(profile))
