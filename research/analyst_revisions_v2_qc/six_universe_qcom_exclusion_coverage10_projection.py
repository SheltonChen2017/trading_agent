"""Separate 10% coverage-floor sources for the QCOM-excluded historical arms.

This builder renders a new physical-order source closure from the frozen 25%
arms. It changes only the six sleeves' minimum name-mapping, market-cap-weight
coverage, and total-reported-weight floors. Five verified names are still
required, and the existing partial stock budget stays in its own sleeve ETF.
"""

import ast
import dataclasses
import hashlib
import json

from . import accepted_risk_matched_historical_projection as _matched
from . import accepted_risk_six_universe_order_relaxed_qc_projection as _relaxed
from . import accepted_risk_six_universe_order_qc_projection as _base
from . import six_universe_relaxed_selection_source as _selection


class QcomCoverage10ProjectionError(ValueError):
    """The frozen predecessor, exact source anchor, or new profile differs."""


ARMS = ("ar_off", "ar_on80", "ar_on120", "ar_on200")
COVERAGE_POLICY_ID = "all_six_minimum_mapping_cap_total_10pct_verified_names_5_v1"
COVERAGE_POLICY = tuple((name, "0.10", "0.10", "0.10", 5)
                        for name in _selection.ALL25_UNIVERSES)
PREDECESSOR_PROJECTION_SHA256 = {
    "ar_off": "0c6a4c5a7cd3bffacb9d4148b5167fe0d1b38b8617b3c01fd974f2639a76704b",
    "ar_on80": "06842824c2fee60f447c4e920ee23634917958f94fa2332a9f21ea24eeed0aa1",
    "ar_on120": "cc18bcdda7dc17750c186a403c8ec74568c4a7f71c528bdd4b714c00ef63c17b",
    "ar_on200": "44b7e0dfcd31ecb1698e0b46196ebe4de80ca036d9273516b05f35dd65241f25",
}
_SCHEMA_ASSIGNMENTS = {
    _relaxed._GATE_PATH: ("PROFILE_SCHEMA", "CONSTRUCTION_SCHEMA"),
    _relaxed._TARGET_PATH: ("SLEEVE_DIAGNOSTIC_SCHEMA", "DECISION_TARGET_SCHEMA",
                            "TARGET_PATH_SCHEMA", "CONSTRUCTION_PATH_SCHEMA"),
    "accepted_risk_six_universe_gate_evaluator.py": (
        "PROFILE_SCHEMA", "SUMMARY_SCHEMA", "ACCOUNT_SCHEMA", "SLEEVE_SCHEMA", "SERIES_SCHEMA"),
    _relaxed._BRIDGE_NAME + ".py": ("BRIDGE_PROFILE_SCHEMA", "BRIDGE_SUMMARY_SCHEMA"),
    "accepted_risk_six_universe_order_qc_runtime.py": (
        "PROFILE_SCHEMA", "SUMMARY_SCHEMA", "META_SCHEMA", "CAP90_PROFILE_SCHEMA",
        "CAP90_SUMMARY_SCHEMA", "ACCOUNT_PATH_SCHEMA", "GROSS_EXPOSURE_PATH_SCHEMA",
        "SPLIT_AUTHORITY_PATH_SCHEMA"),
    _relaxed._TILT_TARGET_PATH: ("DECISION_TARGET_SCHEMA", "TARGET_PATH_SCHEMA"),
    _relaxed._TILT_RUNTIME_PATH: ("TILT_PROFILE_SCHEMA", "TILT_SUMMARY_SCHEMA",
                                 "TILT_META_SCHEMA"),
}
_ROLE_COUNTS = {_relaxed._TILT_TARGET_PATH: 1, "main.py": 1}
_VARIANT_COUNTS = {_relaxed._TILT_RUNTIME_PATH: 1, "main.py": 1}


def _error(message):
    raise QcomCoverage10ProjectionError(message)


def _function(tree, name):
    matches = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        _error("coverage10 exact function anchor changed")
    return matches[0]


def _update_dict(function, call_target):
    matches = [node.args[0] for node in ast.walk(function)
               if isinstance(node, ast.Call) and ast.unparse(node.func) == call_target
               and len(node.args) == 1 and isinstance(node.args[0], ast.Dict)]
    if len(matches) != 1:
        _error("coverage10 profile or aggregate disclosure anchor changed")
    value = matches[0]
    keys = [key.value if isinstance(key, ast.Constant) else None for key in value.keys]
    if keys.count("stock_exclusion_policy_id") != 1 or "coverage_policy_id" in keys:
        _error("coverage10 policy disclosure anchor changed")
    value.keys.append(ast.Constant("coverage_policy_id"))
    value.values.append(ast.Constant(COVERAGE_POLICY_ID))


def _render_source(path, source, predecessor, old_profile, arm):
    """Rewrite only versioned closure members; reject any changed anchor."""
    if path not in {*_SCHEMA_ASSIGNMENTS, "main.py"}:
        return source
    if type(source) is not str or not source.isascii():
        _error("coverage10 source is not exact ASCII")
    old_role = predecessor.role
    old_variant = predecessor.variant
    new_role = f"matched_qcom_excluded_coverage10_{arm}_s0"
    new_variant = f"coverage10_matched_qcom_excluded_{arm}_s0_v1"
    new_profile_id = f"arv2-six-matched-qcom-excluded-coverage10-{arm}-s0-profile-v1"
    counts = {"role": 0, "variant": 0, "profile_id": 0, "class": 0}

    class Version(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is str:
                if node.value == old_role:
                    node.value = new_role
                    counts["role"] += 1
                elif node.value == old_variant:
                    node.value = new_variant
                    counts["variant"] += 1
                elif path == _relaxed._TILT_RUNTIME_PATH and node.value == old_profile["profile_id"]:
                    node.value = new_profile_id
                    counts["profile_id"] += 1
            return node

        def visit_ClassDef(self, node):
            expected = f"ARV2MatchedHistorical{arm.title().replace('_', '')}S0QcomExcludedAlgorithm"
            if path == "main.py" and node.name == expected:
                node.name = expected.replace("Algorithm", "Coverage10Algorithm")
                counts["class"] += 1
            return self.generic_visit(node)

    tree = Version().visit(ast.parse(source))
    if (counts["role"] != _ROLE_COUNTS.get(path, 0)
            or counts["variant"] != _VARIANT_COUNTS.get(path, 0)
            or counts["profile_id"] != int(path == _relaxed._TILT_RUNTIME_PATH)
            or counts["class"] != int(path == "main.py")):
        _error(f"coverage10 role, variant, or profile identity anchor changed in {path}: {counts}")

    expected_names = _SCHEMA_ASSIGNMENTS.get(path, ())
    seen = set()
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in expected_names):
            name = node.targets[0].id
            if (name in seen or not isinstance(node.value, ast.Constant)
                    or type(node.value.value) is not str
                    or not node.value.value.startswith("arv2-six-")):
                _error("coverage10 schema anchor changed")
            seen.add(name)
            if path == _relaxed._TILT_RUNTIME_PATH and name in (
                    "TILT_PROFILE_SCHEMA", "TILT_SUMMARY_SCHEMA", "TILT_META_SCHEMA"):
                category = name.removeprefix("TILT_").removesuffix("_SCHEMA").lower()
                node.value.value = f"arv2-six-matched-qcom-excluded-coverage10-{arm}-{category}-v1"
            elif path == "accepted_risk_six_universe_order_qc_runtime.py" and name == "META_SCHEMA":
                node.value.value = f"arv2-six-matched-qcom-excluded-coverage10-{arm}-meta-v1"
            else:
                node.value.value += "-coverage10-v1"
    if seen != set(expected_names):
        _error("coverage10 schema assignment inventory changed")

    if path == _relaxed._GATE_PATH:
        policy = [node for node in tree.body if isinstance(node, ast.Assign)
                  and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id == "RELAXED_COVERAGE_POLICY"]
        if len(policy) != 1 or ast.literal_eval(policy[0].value) != _selection.ALL25_COVERAGE_POLICY:
            _error("coverage10 six-universe predecessor policy changed")
        policy[0].value = ast.parse(repr(COVERAGE_POLICY), mode="eval").body
        semantic = _function(tree, "_profile_semantic")
        returns = [node.value for node in semantic.body if isinstance(node, ast.Return)
                   and isinstance(node.value, ast.Dict)]
        if len(returns) != 1:
            _error("coverage10 gate profile disclosure anchor changed")
        keys = [key.value if isinstance(key, ast.Constant) else None for key in returns[0].keys]
        if (keys.count("relaxed_universe_coverage_policy") != 1
                or keys.count("stock_exclusion_policy_id") != 1
                or "coverage_policy_id" in keys):
            _error("coverage10 gate policy disclosure anchor changed")
        returns[0].keys.append(ast.Constant("coverage_policy_id"))
        returns[0].values.append(ast.Constant(COVERAGE_POLICY_ID))
    elif path == _relaxed._TILT_RUNTIME_PATH:
        _update_dict(_function(tree, "require_tilt_profile"), "seed.update")
        _update_dict(_function(tree, "_aggregate"), "aggregate.update")
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(rendered), include_attributes=False):
        _error("coverage10 source formatting changed executable AST")
    return rendered


def build_qcom_exclusion_coverage10_projection(package, arm):
    """Return a separately versioned 0-bps historical order arm and profile."""
    if type(arm) is not str or arm not in ARMS:
        _error("coverage10 arm must be ar_off or ar_on80/120/200")
    predecessor, old_profile = (
        _matched.build_qcom_exclusion_projection(package, "ar_off", 0)
        if arm == "ar_off" else
        _matched.build_qcom_exclusion_tilt_projection(package, int(arm[5:]), 0))
    if predecessor.projection_sha256 != PREDECESSOR_PROJECTION_SHA256[arm]:
        _error("coverage10 frozen QCOM-excluded predecessor changed")
    sources = {item.project_path: _render_source(
        item.project_path, item.source_bytes.decode("ascii"), predecessor, old_profile, arm)
        for item in predecessor.source_files}
    with _relaxed._cloud_loader(sources) as (load, _):
        bridge = load(_relaxed._BRIDGE_NAME)
        baseline = bridge.require_bridge_profile("matched")
        old_baseline = old_profile["matched_baseline_profile_sha256"]
        sources[_relaxed._TILT_RUNTIME_PATH] = _relaxed._replace(
            sources[_relaxed._TILT_RUNTIME_PATH], old_baseline, baseline["profile_sha256"])
        gate = load(_relaxed._GATE_PATH[:-3])
        if (gate.RELAXED_COVERAGE_POLICY != COVERAGE_POLICY
                or gate.EXCLUDED_QCOM_SECURITY_ID_SHA256
                != _matched.QCOM_EXCLUSION_SECURITY_ID_SHA256):
            _error("coverage10 gate policy or QCOM exclusion changed")
        runtime = load(_relaxed._TILT_RUNTIME_PATH[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        expected = {
            "role": f"matched_qcom_excluded_coverage10_{arm}_s0",
            "profile_id": f"arv2-six-matched-qcom-excluded-coverage10-{arm}-s0-profile-v1",
            "schema": f"arv2-six-matched-qcom-excluded-coverage10-{arm}-profile-v1",
            "comparison_arm": arm,
            "coverage_policy_id": COVERAGE_POLICY_ID,
            "matched_baseline_profile_sha256": baseline["profile_sha256"],
            "stock_exclusion_policy_id": _matched.QCOM_EXCLUSION_POLICY_ID,
            "excluded_logical_security_sha256": _matched.QCOM_EXCLUSION_SECURITY_ID_SHA256,
            "maximum_stock_weight_change_fraction": ("0.00" if arm == "ar_off"
                                                     else f"{int(arm[5:]) // 100}.{int(arm[5:]) % 100:02d}"),
            "target_gross_exposure": "0.98",
            "modeled_fee_bps_per_side": "10",
            "slippage_bps": "0",
            "admission_leverage": "2",
        }
        if any(profile.get(key) != value for key, value in expected.items()):
            _error("coverage10 matched order profile or economics changed")
        expected_meta = f"arv2-six-matched-qcom-excluded-coverage10-{arm}-meta-v1"
        expected_summary = f"arv2-six-matched-qcom-excluded-coverage10-{arm}-summary-v1"
        if (runtime.TILT_META_SCHEMA != expected_meta
                or runtime.TILT_SUMMARY_SCHEMA != expected_summary
                or load("accepted_risk_six_universe_order_qc_runtime").META_SCHEMA
                != expected_meta):
            _error("coverage10 result transport schemas changed")
    files = tuple(sorted((_base._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS for item in files)
            or total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _error("coverage10 source closure exceeded unchanged QC budgets")
    for item in files:
        _base._audit_source(item.project_path, item.source_bytes)
    value = dataclasses.replace(predecessor,
        schema=f"arv2-six-matched-qcom-excluded-coverage10-{arm}-projection-v1",
        role=profile["role"],
        variant=f"coverage10_matched_qcom_excluded_{arm}_s0_v1",
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    semantic = {key: item for key, item in value.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    return dataclasses.replace(value, projection_sha256=digest,
        projection_id="arv2-six-matched-qcom-excluded-coverage10-projection-" + digest[:24]), json.loads(
            _base._canonical(profile))
