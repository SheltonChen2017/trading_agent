"""R278: R270's eight-sleeve AR entry/count, with zero AR weight transfer.

This is an offline source projection, not a QuantConnect launch or result gate.
The corrected R270 source is the exact parent.  In particular, its scored
entry gate and matched baseline target builder are not regenerated or edited.
"""

import ast
import dataclasses
import hashlib
import json
from decimal import Decimal

from . import accepted_risk_six_universe_order_qc_projection as base
from . import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from . import eight_universe_ar_on_split_rounding as parent
from . import eight_universe_qcom_admitted_projection as eight


class EightUniverseEntryOnlyProjectionError(ValueError):
    """The R270 parent, isolated edit, or projected economics changed."""


CANDIDATE_ID = "R278"
ARM = "ar_on0"
ECONOMIC_USAGE = "entry_and_count_no_weight_transfer"
PREDECESSOR_PROJECTION_SHA256 = (
    "a063fc5bce74cdcc00c1bc8ce7fa3eff95b1db84f997d2e8acbc9dd24da0bec4"
)
PREDECESSOR_PROFILE_SHA256 = (
    "25de4c61e081c653e0196402dbef991e356928cfd3135cf07ebec74b510425a5"
)
PREDECESSOR_SOURCE_FILES_SHA256 = (
    "b28c60a933cbd3993862576d523e9106933f1506284e4dc961ddabf9e908cb7d"
)
_TARGET = relaxed._TILT_TARGET_PATH
_RUNTIME = relaxed._TILT_RUNTIME_PATH
_MAIN = "main.py"
_DIAGNOSTICS = "accepted_risk_matched_diagnostics.py"
_CHANGED_FILES = frozenset({_TARGET, _RUNTIME, _MAIN, _DIAGNOSTICS})
_COUNTS = {
    _TARGET: {"r270": 1, "ar_on100": 4, "tilt100": 3,
              "fraction": 2, "usage": 0, "description": 1,
              "class": 0, "diagnostic_arms": 0},
    _RUNTIME: {"r270": 5, "ar_on100": 7, "tilt100": 0,
               "fraction": 2, "usage": 2, "description": 0,
               "class": 0, "diagnostic_arms": 0},
    _MAIN: {"r270": 2, "ar_on100": 3, "tilt100": 0,
            "fraction": 0, "usage": 0, "description": 0,
            "class": 1, "diagnostic_arms": 0},
    _DIAGNOSTICS: {"r270": 0, "ar_on100": 0, "tilt100": 0,
                   "fraction": 0, "usage": 0, "description": 0,
                   "class": 0, "diagnostic_arms": 2},
}
_PARENT_CLASS = (
    "ARV2MatchedHistoricalArOn100S0QcomAdmittedR270Eight"
    "ScoreFloor1ThreeNameAlgorithm"
)
_NEW_CLASS = (
    "ARV2MatchedHistoricalArOn0S0QcomAdmittedR278Eight"
    "ScoreFloor1ThreeNameAlgorithm"
)
_DIAGNOSTIC_ARMS = (
    "ar_off", "ar_on80", "ar_on100", "ar_on120", "ar_on140",
    "ar_on160", "ar_on180", "ar_on200", "eight_etf_basket",
)


def _fail(message):
    raise EightUniverseEntryOnlyProjectionError(message)


def _render(path, source):
    """Rewrite four pinned files; every other source remains exact R270 bytes."""
    if type(source) is not str or not source.isascii():
        _fail("R270 source is not exact ASCII")
    if path not in _CHANGED_FILES:
        return source
    counts = {name: 0 for name in _COUNTS[path]}

    class Rewrite(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is not str:
                return node
            value = node.value
            for old, new in (("r270", "r278"), ("ar_on100", ARM),
                             ("tilt100", "tilt0")):
                if path == _DIAGNOSTICS:
                    break
                counts[old] += value.count(old)
                value = value.replace(old, new)
            if path == _TARGET and "bounded by 100% of its own post-cap" in value:
                counts["description"] += 1
                value = value.replace("bounded by 100% of its own post-cap",
                                      "bounded by 0% of its own post-cap")
            if path in (_TARGET, _RUNTIME) and value == "1.00":
                counts["fraction"] += 1
                value = "0.00"
            if path == _RUNTIME and value == "entry_count_and_weight":
                counts["usage"] += 1
                value = ECONOMIC_USAGE
            node.value = value
            return node

        def visit_ClassDef(self, node):
            if path == _MAIN and node.name == _PARENT_CLASS:
                counts["class"] += 1
                node.name = _NEW_CLASS
            return self.generic_visit(node)

        def visit_Tuple(self, node):
            if (path == _DIAGNOSTICS
                    and all(isinstance(item, ast.Constant) for item in node.elts)
                    and tuple(item.value for item in node.elts) == _DIAGNOSTIC_ARMS):
                counts["diagnostic_arms"] += 1
                node.elts.insert(1, ast.Constant(ARM))
            return self.generic_visit(node)

    tree = Rewrite().visit(ast.parse(source))
    if counts != _COUNTS[path]:
        _fail(f"R270 entry-only exact rewrite anchors changed: {path}: {counts}")
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(
            ast.parse(rendered), include_attributes=False):
        _fail("entry-only projected AST changed while rendering")
    return rendered


def build_projection(package):
    """Project a distinct 17-file R278 order source, without cloud I/O."""
    predecessor, old_profile = parent.build_projection(package, "R270")
    row = next((item for item in parent.frozen_manifest()["candidates"]
                if item["candidate_id"] == "R270"), None)
    if (predecessor.projection_sha256 != PREDECESSOR_PROJECTION_SHA256
            or old_profile["profile_sha256"] != PREDECESSOR_PROFILE_SHA256
            or row is None
            or row["projection_sha256"] != PREDECESSOR_PROJECTION_SHA256
            or row["profile_sha256"] != PREDECESSOR_PROFILE_SHA256
            or row["source_files_sha256"] != PREDECESSOR_SOURCE_FILES_SHA256):
        _fail("R270 corrected predecessor or frozen source inventory changed")
    original = {item.project_path: item.source_bytes.decode("ascii")
                for item in predecessor.source_files}
    sources = {path: _render(path, content) for path, content in original.items()}
    if ({path for path in original if sources[path] != original[path]}
            != _CHANGED_FILES):
        _fail("R278 changed a non-arm R270 source file")
    with relaxed._cloud_loader(sources) as (load, _):
        gate = load(eight._GATE[:-3])
        tilt = load(_TARGET[:-3])
        runtime = load(_RUNTIME[:-3])
        diagnostics = load(_DIAGNOSTICS[:-3])
        profile = runtime.require_tilt_profile()
        runtime.expected_tilt_custom_statistic_names()
        if (gate.UNIVERSE_IDS != eight.UNIVERSES
                or gate.MINIMUM_POSITIVE_SCORE_COUNT != 1
                or gate.RELAXED_COVERAGE_POLICY != eight.NEW_POLICY
                or gate.SLEEVE_BUDGETS != (Decimal("0.1225"),) * 8
                or gate.DIRECT_STOCK_WEIGHT_CAP != Decimal("0.098")
                or tilt.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION != Decimal("0.00")
                or profile["maximum_stock_weight_change_fraction"] != "0.00"
                or profile["comparison_arm"] != ARM
                or profile["analyst_revision_economic_usage"] != ECONOMIC_USAGE
                or profile["matched_baseline_profile_sha256"] !=
                   old_profile["matched_baseline_profile_sha256"]
                or profile["target_gross_exposure"] != "0.98"
                or profile["modeled_fee_bps_per_side"] != "10"
                or profile["slippage_bps"] != "0"
                or profile["admission_leverage"] != "2"
                or profile["overnight_holding_drift_rule"] !=
                   old_profile["overnight_holding_drift_rule"]
                or diagnostics.SCHEMA !=
                   "arv2-eight-matched-historical-diagnostics-v1"):
            _fail("R278 AR entry, zero-transfer, split, or order economics changed")
    profile_changes = {
        "schema", "profile_id", "profile_sha256", "role",
        "target_path_schema", "decision_target_schema",
        "maximum_stock_weight_change_fraction", "comparison_arm",
        "analyst_revision_economic_usage",
    }
    if (set(profile) != set(old_profile)
            or any(profile[key] != value for key, value in old_profile.items()
                   if key not in profile_changes)
            or profile["profile_sha256"] == old_profile["profile_sha256"]):
        _fail("R278 changed an unrelated R270 profile field")
    files = tuple(sorted((base._source_file(path, content.encode("ascii"))
                          for path, content in sources.items()),
                         key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if (len(files) != 17 or len({item.project_path for item in files}) != 17
            or any(item.byte_count > base.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in files)
            or total + base.MINIMUM_REVIEW_MARGIN_BYTES >
               base.MAXIMUM_TOTAL_SOURCE_BYTES):
        _fail("R278 source inventory or QC budget changed")
    for item in files:
        base._audit_source(item.project_path, item.source_bytes)
    projected = dataclasses.replace(
        predecessor,
        schema="arv2-eight-r278-ar-entry-only-split-truncation-projection-v1",
        variant=predecessor.variant.replace(
            "r270_eight_score_floor1_ar_on100",
            "r278_eight_score_floor1_ar_on0"),
        role=profile["role"], profile_id=profile["profile_id"],
        profile_sha256=profile["profile_sha256"],
        source_files=files, total_source_byte_count=total,
    )
    if (projected.variant == predecessor.variant
            or "r270" in projected.variant
            or "ar_on100" in projected.variant):
        _fail("R278 projection identity was not versioned")
    semantic = {key: value for key, value in projected.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(base._canonical(semantic)).hexdigest()
    return dataclasses.replace(
        projected, projection_sha256=digest,
        projection_id="arv2-eight-r278-ar-entry-only-projection-" + digest[:24],
    ), json.loads(base._canonical(profile))
