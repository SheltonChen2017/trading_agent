"""Guarded, prospective LEAN split-quantity overlay for eight-sleeve sources.

Accepts an existing frozen 17-file projection as input and returns a new
projection.  Callers own their separate candidate/attempt manifest pins.
"""

import ast
import dataclasses
import hashlib

from . import accepted_risk_six_universe_order_qc_projection as base
from . import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed


_RUNTIME = "accepted_risk_six_universe_order_qc_runtime.py"
_BRIDGE = "accepted_risk_six_universe_order_bridge_qc_runtime.py"
_TILT = "accepted_risk_six_universe_order_tilt_qc_runtime.py"
_SUFFIX = "-lean-int-split-truncation-v1"
_RULE = (
    "replan_only_when_each_changed_holding_has_same_session_split_"
    "and_recorded_factor_integer_truncation_matches_v1"
)


class EightUniverseSplitTruncationError(ValueError):
    """The prior source or its split/profile anchor did not authenticate."""


def _fail(message):
    raise EightUniverseSplitTruncationError(message)


def _tree(source, path):
    tree = ast.parse(source)
    if ast.unparse(tree) + "\n" != source:
        _fail("eight-universe generated source formatting changed: " + path)
    return tree


def _function(tree, name):
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == name]
    if len(matches) != 1:
        _fail("eight-universe profile function anchor changed: " + name)
    return matches[0]


def _constant(node, old, new):
    matches = [item for item in ast.walk(node)
               if isinstance(item, ast.Constant) and item.value == old]
    if len(matches) != 1:
        _fail("eight-universe split/profile constant anchor changed: " + old)
    matches[0].value = new


def _assignment(tree, name):
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
               and node.targets[0].id == name and isinstance(node.value, ast.Constant)
               and type(node.value.value) is str]
    if len(matches) != 1:
        _fail("eight-universe profile assignment anchor changed: " + name)
    return matches[0]


def _profile_value(function, key):
    matches = [item.values[index] for item in ast.walk(function)
               if isinstance(item, ast.Dict)
               for index, name in enumerate(item.keys)
               if isinstance(name, ast.Constant) and name.value == key]
    if len(matches) != 1 or not isinstance(matches[0], ast.Constant) or type(matches[0].value) is not str:
        _fail("eight-universe profile field anchor changed: " + key)
    return matches[0]


def _render_runtime(source):
    tree = _tree(source, _RUNTIME)
    drivers = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "AcceptedRiskSixUniverseOrderQcDriver"]
    methods = [node for driver in drivers for node in driver.body
               if isinstance(node, ast.FunctionDef)
               and node.name == "_holding_drift_replan"]
    old = ("adjusted != adjusted.to_integral_value() or int(adjusted) != "
           "observed_quantities.get(security_id, 0)")
    guards = [node for method in methods for node in ast.walk(method)
              if isinstance(node, ast.If) and ast.unparse(node.test) == old]
    if len(drivers) != 1 or len(methods) != 1 or len(guards) != 1:
        _fail("eight-universe exact split quotient guard changed")
    # LEAN casts the recorded-factor quotient to an integer.  Negative
    # holdings remain refused even if a direct caller bypasses the executor's
    # independent long-only census.
    guards[0].test = ast.parse(
        "adjusted < 0 or int(adjusted) != observed_quantities.get(security_id, 0)",
        mode="eval").body
    _constant(_function(tree, "_profile"),
              "replan_only_when_each_changed_holding_has_same_session_split", _RULE)
    _constant(_function(tree, "_profile"), "-v2", "-v2" + _SUFFIX)
    _constant(_function(tree, "_cap90_profile"), "-cap90-exploratory-v3",
              "-cap90-exploratory-v3" + _SUFFIX)
    for name in ("PROFILE_SCHEMA", "CAP90_PROFILE_SCHEMA"):
        assignment = _assignment(tree, name)
        assignment.value.value += _SUFFIX
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _render_bridge(source):
    tree = _tree(source, _BRIDGE)
    _assignment(tree, "BRIDGE_PROFILE_SCHEMA").value.value += _SUFFIX
    _constant(_function(tree, "require_bridge_profile"),
              "-cap90-admission-settlement-v1",
              "-cap90-admission-settlement-v1" + _SUFFIX)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _render_tilt(source, old_baseline_hash, new_baseline_hash):
    tree = _tree(source, _TILT)
    baseline = _assignment(tree, "BASELINE_MATCHED_PROFILE_SHA256")
    if baseline.value.value != old_baseline_hash:
        _fail("eight-universe old bridge profile pin changed")
    baseline.value.value = new_baseline_hash
    _assignment(tree, "TILT_PROFILE_SCHEMA").value.value += _SUFFIX
    identity = _profile_value(_function(tree, "require_tilt_profile"), "profile_id")
    identity.value += _SUFFIX
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def correct_projection(projection, profile, *, schema, projection_id_prefix):
    """Version split execution policy while preserving all strategy economics."""
    if (type(schema) is not str or not schema or type(projection_id_prefix) is not str
            or not projection_id_prefix or type(profile) is not dict
            or len(projection.source_files) != 17):
        _fail("eight-universe split overlay input changed")
    original = {item.project_path: item.source_bytes.decode("ascii")
                for item in projection.source_files}
    if len(original) != 17 or not {_RUNTIME, _BRIDGE, _TILT} <= set(original):
        _fail("eight-universe split overlay source inventory changed")
    source = dict(original)
    source[_RUNTIME] = _render_runtime(source[_RUNTIME])
    source[_BRIDGE] = _render_bridge(source[_BRIDGE])
    with relaxed._cloud_loader(source) as (load, _):
        baseline = load(_BRIDGE[:-3]).require_bridge_profile("matched")
    old_baseline_hash = profile["matched_baseline_profile_sha256"]
    source[_TILT] = _render_tilt(source[_TILT], old_baseline_hash,
                                baseline["profile_sha256"])
    with relaxed._cloud_loader(source) as (load, _):
        corrected = load(_TILT[:-3]).require_tilt_profile()
        if load(_BRIDGE[:-3]).require_bridge_profile("matched") != baseline:
            _fail("eight-universe corrected bridge profile changed")
    allowed = {"schema", "profile_id", "profile_sha256",
               "overnight_holding_drift_rule", "cap90_predecessor_profile_sha256",
               "matched_baseline_profile_sha256"}
    if (set(corrected) != set(profile)
            or any(corrected[key] != profile[key] for key in profile
                   if key not in allowed)
            or corrected["overnight_holding_drift_rule"] != _RULE
            or corrected["profile_sha256"] == profile["profile_sha256"]
            or corrected["matched_baseline_profile_sha256"] == old_baseline_hash):
        _fail("eight-universe split overlay changed strategy economics")
    files = tuple(sorted((base._source_file(path, content.encode("ascii"))
                          for path, content in source.items()),
                         key=lambda item: item.project_path))
    prior = {item.project_path: item.content_sha256 for item in projection.source_files}
    changed = {item.project_path for item in files
               if item.content_sha256 != prior[item.project_path]}
    if changed != {_RUNTIME, _BRIDGE, _TILT}:
        _fail("eight-universe split overlay changed unexpected source files")
    total = sum(item.byte_count for item in files)
    if total + base.MINIMUM_REVIEW_MARGIN_BYTES > base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _fail("eight-universe corrected source exceeds QC budget")
    successor = dataclasses.replace(
        projection, schema=schema,
        variant=projection.variant + "_lean_int_split_truncation_v1",
        profile_id=corrected["profile_id"],
        profile_sha256=corrected["profile_sha256"],
        source_files=files, total_source_byte_count=total)
    record = {key: value for key, value in successor.to_record().items()
              if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(base._canonical(record)).hexdigest()
    return dataclasses.replace(
        successor, projection_sha256=digest,
        projection_id=projection_id_prefix + digest[:24]), corrected
