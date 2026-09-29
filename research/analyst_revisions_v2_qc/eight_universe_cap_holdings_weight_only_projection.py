"""Prospective R277: AR weights on R268 A3's exact cap-selected holdings.

This is an offline source projection only. It cannot launch or read QC results.
The R268 A3 gate and baseline target builder remain byte-identical. Only the
bounded 100% within-sleeve transfer consumes AR scores. The cloud runtime
refuses if its complete baseline target path differs from the retained R268
A3 path, so a later data-vintage change cannot masquerade as fixed holdings.
"""

import ast
import copy
import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as source_contract
from . import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from . import eight_universe_ar_on_split_rounding as full_ar
from . import eight_universe_qcom_admitted_projection as eight
from . import eight_universe_r268_a3_split_rounding as baseline


class EightCapHoldingsWeightOnlyProjectionError(ValueError):
    """The exact R268/R270 source or the fixed-holdings rule changed."""


CANDIDATE_ID = "R277"
ARM = "ar_on100_weights_only"
ECONOMIC_USAGE = "weight_only_same_R268_cap_selected_holdings"
SCHEMA = "arv2-eight-r277-cap-holdings-weight-only-projection-v1"
R268_A3_PROJECTION_SHA256 = "9bf45940b9215cdbfe17e868cb56f13ba65f382e9743d271fc768dcc442d6f76"
R270_PROJECTION_SHA256 = "a063fc5bce74cdcc00c1bc8ce7fa3eff95b1db84f997d2e8acbc9dd24da0bec4"
R268_BASELINE_PROFILE_SHA256 = "2ff2ff702c7f4fe24a5ed0f9af421d7d63874768b8fa0f5ff69f483be5509aad"
R268_BASELINE_TARGET_PATH_SHA256 = "e2a4ea68d8e7f6bebe262876163f191b4895735a815204d989d7ed415900ba46"
_TILT = eight._TILT_TARGETS
_RUNTIME = eight._TILT_RUNTIME
_BASE_RUNTIME = eight._RUNTIME
_DIAGNOSTICS = eight._DIAGNOSTICS
_MAIN = "main.py"
CHANGED_SOURCE_PATHS = frozenset((_TILT, _RUNTIME, _BASE_RUNTIME, _DIAGNOSTICS, _MAIN))

_OLD_ROLE = "matched_qcom_admitted_r268_eight_three_name_ar_off_s0"
_NEW_ROLE = "matched_qcom_admitted_r277_eight_cap_holdings_ar_weight_only_s0"
_OLD_VARIANT = "three_name_matched_qcom_admitted_r268_eight_ar_off_s0_v1"
_NEW_VARIANT = "three_name_matched_qcom_admitted_r277_eight_cap_holdings_ar_weight_only_s0_v1"
_OLD_META = "arv2-eight-matched-qcom-admitted-r268-eight-three-name-ar_off-meta-v1"
_NEW_META = "arv2-eight-matched-qcom-admitted-r277-eight-cap-holdings-ar-weight-only-meta-v1"
_OLD_PROFILE_SCHEMA = "arv2-eight-matched-qcom-admitted-r268-eight-three-name-ar_off-profile-v1-lean-int-split-truncation-v1"
_NEW_PROFILE_SCHEMA = "arv2-eight-matched-qcom-admitted-r277-eight-cap-holdings-ar-weight-only-profile-v1-lean-int-split-truncation-v1"
_OLD_PROFILE_ID = "arv2-eight-matched-qcom-admitted-r268-eight-three-name-ar_off-s0-profile-v1-lean-int-split-truncation-v1"
_NEW_PROFILE_ID = "arv2-eight-matched-qcom-admitted-r277-eight-cap-holdings-ar-weight-only-s0-profile-v1-lean-int-split-truncation-v1"
_OLD_SUMMARY = "arv2-eight-matched-qcom-admitted-r268-eight-three-name-ar_off-summary-v1"
_NEW_SUMMARY = "arv2-eight-matched-qcom-admitted-r277-eight-cap-holdings-ar-weight-only-summary-v1"


def _fail(message):
    raise EightCapHoldingsWeightOnlyProjectionError(message)


def _function(tree, name):
    matches = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        _fail(f"R277 exact function anchor changed: {name}")
    return matches[0]


def _replace_literals(tree, replacements):
    counts = {old: 0 for old in replacements}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) is str and node.value in replacements:
            old = node.value
            node.value = replacements[old][0]
            counts[old] += 1
    if any(counts[old] != expected for old, (_, expected) in replacements.items()):
        _fail(f"R277 exact literal anchor changed: {counts}")


def _render_tilt_targets(old, donor):
    tree, donor_tree = ast.parse(old), ast.parse(donor)
    before, after = _function(tree, "tilt_matched_weights"), _function(donor_tree, "tilt_matched_weights")
    if (len([node for node in ast.walk(before) if isinstance(node, ast.Return)]) != 1
            or ast.unparse(next(node for node in ast.walk(before)
                                if isinstance(node, ast.Return)).value) != "construction.matched_weights"
            or not any(isinstance(node, ast.With) for node in ast.walk(after))):
        _fail("R277 AR-off return or 100% donor transfer anchor changed")
    for index, node in enumerate(tree.body):
        if node is before:
            replacement = copy.deepcopy(after)
            replacement.body[0] = ast.Expr(ast.Constant(
                "Apply 100% AR transfers only to the R268 cap-selected stocks; AR never controls entry or count."))
            tree.body[index] = replacement
            break
    old_score = [node for node in ast.walk(tree)
                 if isinstance(node, ast.keyword) and node.arg == "firm_specific_score"]
    donor_score = [node for node in ast.walk(donor_tree)
                   if isinstance(node, ast.keyword) and node.arg == "firm_specific_score"]
    if (len(old_score) != 1 or len(donor_score) != 1
            or not isinstance(old_score[0].value, ast.Constant)
            or old_score[0].value.value is not None
            or isinstance(donor_score[0].value, ast.Constant)):
        _fail("R277 score enrichment anchor changed")
    old_score[0].value = copy.deepcopy(donor_score[0].value)
    _replace_literals(tree, {
        _OLD_ROLE: (_NEW_ROLE, 1),
        "0.00": ("1.00", 2),
        "disabled_full_AR_off_v1": ("scored_tied_midrank_centered_v1", 1),
        "arv2-eight-universe-order-tilt0-guard-decision-target-v1-aroff-v1-matched-ar_off-s0-v1-three-name-v1":
            ("arv2-eight-universe-order-tilt100-cap-holdings-weight-only-decision-target-v1", 1),
        "arv2-eight-universe-order-tilt0-guard-target-path-v1-aroff-v1-matched-ar_off-s0-v1-three-name-v1":
            ("arv2-eight-universe-order-tilt100-cap-holdings-weight-only-target-path-v1", 1),
        "arv2-eight-universe-order-tilt0-guard-target-path-aroff--matched-ar_off-s0-v1":
            ("arv2-eight-universe-order-tilt100-cap-holdings-weight-only-target-path-", 1),
    })
    return tree


def _render_tilt_runtime(old):
    tree = ast.parse(old)
    _replace_literals(tree, {
        _OLD_VARIANT: (_NEW_VARIANT, 1),
        _OLD_META: (_NEW_META, 1),
        _OLD_PROFILE_SCHEMA: (_NEW_PROFILE_SCHEMA, 1),
        _OLD_PROFILE_ID: (_NEW_PROFILE_ID, 1),
        _OLD_SUMMARY: (_NEW_SUMMARY, 1),
        "0.00": ("1.00", 2),
        "ar_off": (ARM, 2),
        "none_authenticated_score_clock_only": (ECONOMIC_USAGE, 2),
    })
    error = _function(tree, "_error")
    index = tree.body.index(error) + 1
    tree.body[index:index] = ast.parse(f'''
REFERENCE_BASELINE_TARGET_PATH_SHA256 = "{R268_BASELINE_TARGET_PATH_SHA256}"

def _require_reference_baseline_target_path(value):
    if type(value) is not str or value != REFERENCE_BASELINE_TARGET_PATH_SHA256:
        _error("R277 baseline holdings/weights differ from authenticated R268 A3")
''').body
    aggregate = _function(tree, "_aggregate")
    calls = [index for index, node in enumerate(aggregate.body)
             if isinstance(node, ast.Expr) and ast.unparse(node.value) == "path.to_record()"]
    if len(calls) != 1:
        _fail("R277 baseline-path verification site changed")
    aggregate.body[calls[0] + 1:calls[0] + 1] = ast.parse(
        "_require_reference_baseline_target_path(path.baseline_target_path_sha256)"
    ).body
    profile = _function(tree, "require_tilt_profile")
    seed_updates = [node for node in ast.walk(profile) if isinstance(node, ast.Call)
                    and ast.unparse(node.func) == "seed.update" and len(node.args) == 1
                    and isinstance(node.args[0], ast.Dict)]
    if len(seed_updates) != 1:
        _fail("R277 profile disclosure anchor changed")
    disclosed = seed_updates[0].args[0]
    if any(isinstance(key, ast.Constant) and key.value == "reference_baseline_target_path_sha256"
           for key in disclosed.keys):
        _fail("R277 baseline-path profile disclosure duplicated")
    disclosed.keys.append(ast.Constant("reference_baseline_target_path_sha256"))
    disclosed.values.append(ast.Name("REFERENCE_BASELINE_TARGET_PATH_SHA256", ast.Load()))
    return tree


def _render_diagnostics(old):
    tree = ast.parse(old)
    count = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Tuple) and len(node.elts) == 3
                and all(isinstance(item, ast.Constant) for item in node.elts)
                and tuple(item.value for item in node.elts)
                    == ("ar_off", "ar_on100", "eight_etf_basket")):
            node.elts.append(ast.Constant(ARM))
            count += 1
    if count != 2:
        _fail("R277 diagnostic accepted-arm census changed")
    return tree


def _render_main(old):
    tree = ast.parse(old)
    _replace_literals(tree, {
        _OLD_ROLE: (_NEW_ROLE, 1),
        _OLD_VARIANT: (_NEW_VARIANT, 1),
        "ar_off": (ARM, 1),
    })
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "ARV2MatchedHistoricalArOffS0QcomAdmittedR268EightThreeNameAlgorithm"]
    if len(classes) != 1:
        _fail("R277 main algorithm identity anchor changed")
    classes[0].name = "ARV2EightR277CapHoldingsWeightOnlyAlgorithm"
    return tree


def _render(path, old, donor):
    if path == _TILT:
        tree = _render_tilt_targets(old, donor)
    elif path == _RUNTIME:
        tree = _render_tilt_runtime(old)
    elif path == _BASE_RUNTIME:
        tree = ast.parse(old)
        _replace_literals(tree, {_OLD_META: (_NEW_META, 1)})
    elif path == _DIAGNOSTICS:
        tree = _render_diagnostics(old)
    elif path == _MAIN:
        tree = _render_main(old)
    else:
        _fail("R277 renderer was called for an unchanged source")
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(rendered), include_attributes=False):
        _fail("R277 source normalization changed executable AST")
    return rendered


def build_projection(package):
    """Return the new 17-file QC source and versioned profile without I/O."""
    old, old_profile = baseline.build_projection(package)
    donor, _ = full_ar.build_projection(package, "R270")
    if (old.projection_sha256 != R268_A3_PROJECTION_SHA256
            or donor.projection_sha256 != R270_PROJECTION_SHA256
            or old_profile["matched_baseline_profile_sha256"] != R268_BASELINE_PROFILE_SHA256
            or old_profile["comparison_arm"] != "ar_off"
            or old_profile["maximum_stock_weight_change_fraction"] != "0.00"):
        _fail("R277 exact R268 A3 or R270 source ancestry changed")
    old_sources = {item.project_path: item.source_bytes.decode("ascii")
                   for item in old.source_files}
    donor_sources = {item.project_path: item.source_bytes.decode("ascii")
                     for item in donor.source_files}
    sources = {path: (_render(path, source, donor_sources[_TILT] if path == _TILT else "")
                      if path in CHANGED_SOURCE_PATHS else source)
               for path, source in old_sources.items()}
    if ({path for path in sources if sources[path] != old_sources[path]}
            != CHANGED_SOURCE_PATHS):
        _fail("R277 source changes escaped the five-file allowlist")
    with relaxed._cloud_loader(sources) as (load, _):
        gate = load(eight._GATE[:-3])
        tilt = load(_TILT[:-3])
        runtime = load(_RUNTIME[:-3])
        profile = runtime.require_tilt_profile()
        if (gate.UNIVERSE_IDS != eight.UNIVERSES
                or gate.RELAXED_COVERAGE_POLICY != eight.NEW_POLICY
                or gate.DIRECT_STOCK_WEIGHT_CAP != tilt.Decimal("0.098")
                or gate.SLEEVE_BUDGETS != (tilt.Decimal("0.1225"),) * 8
                or tilt.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION != tilt.Decimal("1.00")
                or tilt.TILT_RANK_RULE_ID != "scored_tied_midrank_centered_v1"
                or profile.get("role") != _NEW_ROLE
                or profile.get("comparison_arm") != ARM
                or profile.get("analyst_revision_economic_usage") != ECONOMIC_USAGE
                or profile.get("coverage_policy_id") != eight.OFF_POLICY_ID
                or profile.get("matched_baseline_profile_sha256") != R268_BASELINE_PROFILE_SHA256
                or profile.get("reference_baseline_target_path_sha256")
                    != R268_BASELINE_TARGET_PATH_SHA256
                or profile.get("maximum_stock_weight_change_fraction") != "1.00"
                or profile.get("target_gross_exposure") != "0.98"
                or profile.get("modeled_fee_bps_per_side") != "10"
                or profile.get("slippage_bps") != "0"
                or profile.get("admission_leverage") != "2"
                or runtime.TILT_META_SCHEMA != _NEW_META
                or load(_BASE_RUNTIME[:-3]).META_SCHEMA != _NEW_META):
            _fail("R277 fixed-holdings profile or order economics changed")
        runtime.expected_tilt_custom_statistic_names()
    files = tuple(sorted((source_contract._source_file(path, source.encode("ascii"))
                          for path, source in sources.items()), key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > source_contract.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in files)
            or total + source_contract.MINIMUM_REVIEW_MARGIN_BYTES
                > source_contract.MAXIMUM_TOTAL_SOURCE_BYTES):
        _fail("R277 exact QC source closure or budget changed")
    for item in files:
        source_contract._audit_source(item.project_path, item.source_bytes)
    semantic = dataclasses.replace(old, schema=SCHEMA, role=_NEW_ROLE,
        variant=_NEW_VARIANT, profile_id=profile["profile_id"],
        profile_sha256=profile["profile_sha256"], source_files=files,
        total_source_byte_count=total)
    record = {key: value for key, value in semantic.to_record().items()
              if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(source_contract._canonical(record)).hexdigest()
    return dataclasses.replace(semantic, projection_sha256=digest,
        projection_id=f"arv2-eight-r277-cap-holdings-weight-only-projection-{digest[:24]}"), json.loads(
            source_contract._canonical(profile))


__all__ = ("ARM", "CANDIDATE_ID", "CHANGED_SOURCE_PATHS", "ECONOMIC_USAGE",
           "R268_BASELINE_TARGET_PATH_SHA256", "SCHEMA", "build_projection")
