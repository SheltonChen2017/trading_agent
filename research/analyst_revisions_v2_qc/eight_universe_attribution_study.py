"""Fixed-100% eight-universe attribution diagnostic, not a new parameter sweep.

R277 weights the exact R268 A3 cap-selected holdings. R278 keeps R270's
AR-controlled entry/count and removes only its AR weight transfer. The two
previously completed arms remain immutable local controls. This module does
not confer outcome or trading authority by itself.
"""

import ast
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

from . import eight_universe_ar_entry_only_projection as entry
from . import eight_universe_cap_holdings_weight_only_projection as weight
from . import eight_universe_study as eight
from . import six_universe_relaxed_submission as adapter
from . import six_universe_settlement_submission as common


FAMILY = "eight_attribution"
MANIFEST_SCHEMA = "arv2-eight-fixed100-factorial-order-study-v1"
MANIFEST_PATH = Path(__file__).with_name("eight_universe_attribution_candidates.json")
FROZEN_MANIFEST_SHA256 = "98e2279189c09d517441741840a173239ab2e105259d024efb17b2ba48929b60"
CONTROL = Path(__file__).resolve().parents[2] / (
    "artifacts/analyst_revisions_v2/eight_attribution_qc_control_20260929")
PARENT_CONTROL = eight._R267_CONTROL.parent / "eight_universe_qc_control_20260929"
PARENT_RESULT_SHA256 = {
    "R268": "45171f6720f5cb187f6772e02dc0654e0455d5ebb03be3401611295e5c2fc1ac",
    "R270": "afa7b3a6299a28e80e80dd868e322a298643eaac5acb9e6de5a6ae13135d1a6c",
}
PARENT_BASELINE_PATH_SHA256 = {
    "R268": "e2a4ea68d8e7f6bebe262876163f191b4895735a815204d989d7ed415900ba46",
    "R270": "a0b8cfce58539fbe2c0b17c1f4b570f0f65e054e84fc6ea4edf8113029d3d8ea",
}
CANDIDATE_ARMS = {"R277": weight.ARM, "R278": entry.ARM}
STATISTIC_NAMES = eight.STATISTIC_NAMES
PROTOCOL = {
    "parent_candidates": ["R268-A3", "R270-A1"],
    "new_candidates": ["R277", "R278"],
    "window": ["2021-01-04", "2025-12-31"],
    "universes": list(eight.renderer.UNIVERSES),
    "decision_count": 261,
    "observation_count": 1255,
    "fixed_tilt_percent": 100,
    "target_gross_exposure": "0.98",
    "modeled_fee_bps_per_side": "10",
    "slippage_bps": 0,
    "admission_leverage": "2",
    "maximum_attempts_per_new_candidate": 3,
    "physical_orders": True,
    "historical_exploratory_diagnostic_only": True,
    "formal_alpha_or_forward_efficacy": False,
    "paper_live_or_funded_orders": False,
}
_PARENTS = {"R277": "R268", "R278": "R270"}
_PARENT_ATTEMPTS = {"R268": 3, "R270": 1}


def _fail(message):
    adapter._fail(message)


def _module(candidate):
    if candidate not in CANDIDATE_ARMS:
        _fail("fixed-100 attribution candidate changed")
    return weight if candidate == "R277" else entry


def build_projection(package, candidate):
    return _module(candidate).build_projection(package)


def _literal(projection, path, name):
    files = [item for item in projection.source_files if item.project_path == path]
    if len(files) != 1:
        _fail("attribution source constant file changed")
    tree = ast.parse(files[0].source_bytes.decode("ascii"))
    nodes = [node for node in tree.body if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
             and node.targets[0].id == name]
    if (len(nodes) != 1 or not isinstance(nodes[0].value, ast.Constant)
            or type(nodes[0].value.value) is not str):
        _fail("attribution source constant changed")
    return nodes[0].value.value


def _parent_rows():
    return {
        "R268": adapter._eight_r268_a3_manifest()["candidates"][0],
        "R270": next(row for row in adapter._eight_ar_on_split_manifest()["candidates"]
                     if row["candidate_id"] == "R270"),
    }


def _row(candidate, projection, profile):
    parent = _parent_rows()[_PARENTS[candidate]]
    files = [[item.project_path, item.content_sha256, item.byte_count]
             for item in projection.source_files]
    return {**parent,
            "candidate_id": candidate,
            "arm": CANDIDATE_ARMS[candidate],
            "project_name": f"ARV2 EIGHT ATTRIBUTION {candidate} 2021 2025",
            "backtest_name": f"ARV2 {candidate} eight fixed100 attribution 2021 2025",
            "tilt_fraction": profile["maximum_stock_weight_change_fraction"],
            "coverage_policy_id": profile["coverage_policy_id"],
            "analyst_revision_economic_usage": _module(candidate).ECONOMIC_USAGE,
            "minimum_positive_score_count": 0 if candidate == "R277" else 1,
            "role": projection.role,
            "projection_schema": projection.schema,
            "projection_sha256": projection.projection_sha256,
            "profile_id": projection.profile_id,
            "profile_sha256": projection.profile_sha256,
            "matched_baseline_profile_sha256": profile["matched_baseline_profile_sha256"],
            "source_files_sha256": hashlib.sha256(common._canonical(files)).hexdigest(),
            "source_file_count": len(files),
            "total_source_bytes": projection.total_source_byte_count,
            "statistic_names": STATISTIC_NAMES,
            "meta_schema": _literal(projection,
                "accepted_risk_six_universe_order_qc_runtime.py", "META_SCHEMA"),
            "summary_schema": _literal(projection,
                "accepted_risk_six_universe_order_tilt_qc_runtime.py", "TILT_SUMMARY_SCHEMA")}


def freeze_manifest(package):
    """Render both sources without QC I/O, for preregistration before launch."""
    original = adapter._eight_r268_a3_manifest()
    second = adapter._eight_ar_on_split_manifest()
    if (original["package_sha256"] != second["package_sha256"]
            or original["activation_manifest_sha256"] != second["activation_manifest_sha256"]):
        _fail("attribution parent input lineage changed")
    rows = []
    for candidate in CANDIDATE_ARMS:
        projection, profile = build_projection(package, candidate)
        rows.append(_row(candidate, projection, profile))
    return validate_manifest({
        "schema": MANIFEST_SCHEMA,
        "protocol": PROTOCOL,
        "parent_manifest_sha256s": {
            "R268": adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256,
            "R270": adapter.FROZEN_EIGHT_AR_ON_SPLIT_MANIFEST_SHA256},
        "parent_result_sha256s": PARENT_RESULT_SHA256,
        "parent_baseline_path_sha256s": PARENT_BASELINE_PATH_SHA256,
        "package_sha256": original["package_sha256"],
        "activation_manifest_sha256": original["activation_manifest_sha256"],
        "candidates": rows,
    })


def validate_manifest(value):
    rows = value.get("candidates") if type(value) is dict else None
    original = adapter._eight_r268_a3_manifest()
    if (type(value) is not dict or set(value) != {
            "schema", "protocol", "parent_manifest_sha256s",
            "parent_result_sha256s", "parent_baseline_path_sha256s",
            "package_sha256", "activation_manifest_sha256", "candidates"}
            or value["schema"] != MANIFEST_SCHEMA or value["protocol"] != PROTOCOL
            or value["parent_manifest_sha256s"] != {
                "R268": adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256,
                "R270": adapter.FROZEN_EIGHT_AR_ON_SPLIT_MANIFEST_SHA256}
            or value["parent_result_sha256s"] != PARENT_RESULT_SHA256
            or value["parent_baseline_path_sha256s"] != PARENT_BASELINE_PATH_SHA256
            or value["package_sha256"] != original["package_sha256"]
            or value["activation_manifest_sha256"] != original["activation_manifest_sha256"]
            or type(rows) is not list or len(rows) != 2):
        _fail("fixed-100 attribution protocol or ancestry changed")
    parents = _parent_rows()
    allowed = {"candidate_id", "arm", "project_name", "backtest_name",
               "tilt_fraction", "coverage_policy_id", "analyst_revision_economic_usage",
               "minimum_positive_score_count", "role", "projection_schema",
               "projection_sha256", "profile_id", "profile_sha256",
               "matched_baseline_profile_sha256", "source_files_sha256",
               "source_file_count", "total_source_bytes", "meta_schema", "summary_schema"}
    for candidate, row in zip(CANDIDATE_ARMS, rows):
        parent = parents[_PARENTS[candidate]]
        if (type(row) is not dict or set(row) != set(parent)
                or any(row[key] != parent[key] for key in parent if key not in allowed)
                or row["candidate_id"] != candidate or row["arm"] != CANDIDATE_ARMS[candidate]
                or row["project_name"] != f"ARV2 EIGHT ATTRIBUTION {candidate} 2021 2025"
                or row["backtest_name"] != f"ARV2 {candidate} eight fixed100 attribution 2021 2025"
                or row["analyst_revision_economic_usage"] != _module(candidate).ECONOMIC_USAGE
                or row["minimum_positive_score_count"] != (0 if candidate == "R277" else 1)
                or row["tilt_fraction"] != ("1.00" if candidate == "R277" else "0.00")
                or row["statistic_names"] != STATISTIC_NAMES
                or row["source_file_count"] != 17
                or type(row["total_source_bytes"]) is not int
                or not 0 < row["total_source_bytes"] + 32768 <= 448 * 1024
                or any(type(row[key]) is not str or adapter.cap._HEX.fullmatch(row[key]) is None
                       for key in ("projection_sha256", "profile_sha256",
                                   "matched_baseline_profile_sha256", "source_files_sha256"))):
            _fail(f"fixed-100 attribution candidate changed: {candidate}")
    return value


def frozen_manifest():
    if type(FROZEN_MANIFEST_SHA256) is not str:
        _fail("fixed-100 attribution source is not frozen")
    raw = MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_MANIFEST_SHA256:
        _fail("fixed-100 attribution manifest changed")
    return validate_manifest(json.loads(raw))


def parse_order(plan, statistics):
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or set(statistics) != set(STATISTIC_NAMES)
            or row["candidate_id"] not in CANDIDATE_ARMS):
        _fail("fixed-100 attribution result inventory changed")
    parsed = adapter._parse_order_common(
        plan, statistics, expected_geometry=None, decision_count=261,
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({
            "comparison_arm", "analyst_revision_economic_usage", "coverage_policy_id"}),
        result_transport="three_bounded_custom_summary_statistics", eight_universe=True)
    aggregate, meta = parsed["aggregates"], parsed["meta"]
    if (aggregate.get("comparison_arm") != row["arm"]
            or aggregate.get("analyst_revision_economic_usage") !=
               row["analyst_revision_economic_usage"]
            or aggregate.get("coverage_policy_id") != row["coverage_policy_id"]):
        _fail("fixed-100 attribution economic arm changed")
    report = adapter._statistic(statistics[eight.DIAGNOSTIC_NAME])
    if (meta.get("matched_diagnostics_sha256") != adapter._sha(report)
            or report.get("arm") != row["arm"]):
        _fail("fixed-100 attribution diagnostic digest or arm changed")
    # The common diagnostic validator has only the original arms; normalize
    # its *copy* after binding the actual arm above. Never normalize producer
    # statistics or the hash checked against the original META.
    eight._validate_eight_diagnostics({**report, "arm": "ar_on100"}, "ar_on100")
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        _fail("fixed-100 attribution diagnostic and account return differ")
    return {**parsed, "diagnostics": report}


def _authenticated_result(plan):
    row = adapter._candidate(plan)
    launch = common._read(adapter._path(plan, "launch"))
    adapter._receipt(plan, launch)
    expected = {"candidate_id": plan.candidate_id, "attempt": plan.attempt,
                "project_id": launch["project_id"], "backtest_id": launch["backtest_id"],
                "status": "Completed."}
    if (common._read(adapter._path(plan, "project")) != {
            "candidate_id": plan.candidate_id, "project_id": launch["project_id"],
            "project_name": row["project_name"]}
            or common._read(adapter._path(plan, "terminal")) != expected
            or common._read(adapter._path(plan, "read-claim")) != expected):
        _fail("fixed-100 attribution retained result lineage changed")
    raw = adapter._read_artifact(adapter._path(plan, "raw-custom"))
    if (type(raw) is not dict or set(raw) != set(expected) | {"statistics"}
            or any(raw.get(key) != value for key, value in expected.items())
            or type(raw["statistics"]) is not dict
            or set(raw["statistics"]) != set(row["statistic_names"])):
        _fail("fixed-100 attribution retained statistics changed")
    parsed = adapter._parse_order(plan, raw["statistics"])
    saved = adapter._read_artifact(adapter._path(plan, "result"))
    if saved != {**expected, **parsed,
                 "manifest_sha256": adapter._plan_manifest_sha256(plan),
                 "projection_sha256": row["projection_sha256"]}:
        _fail("fixed-100 attribution saved result differs from exact statistics")
    return saved


def require_parents(plan):
    if plan.family != FAMILY or plan.candidate_id not in CANDIDATE_ARMS:
        _fail("fixed-100 attribution predecessor plan changed")
    parents = {}
    for candidate in PARENT_RESULT_SHA256:
        old = adapter.build_plan(candidate, plan.organization_id, PARENT_CONTROL,
            _PARENT_ATTEMPTS[candidate], family=eight.FAMILY)
        result_path = adapter._path(old, "result")
        try:
            result_bytes = result_path.read_bytes()
        except OSError:
            _fail("fixed-100 attribution predecessor result is unavailable")
        if hashlib.sha256(result_bytes).hexdigest() != PARENT_RESULT_SHA256[candidate]:
            _fail("fixed-100 attribution predecessor result bytes changed")
        result = _authenticated_result(old)
        if (result["run_valid"] is not True
                or result["aggregates"]["matched_baseline_target_path_sha256"] !=
                   PARENT_BASELINE_PATH_SHA256[candidate]):
            _fail("fixed-100 attribution predecessor validity or holdings path changed")
        parents[candidate] = result
    input_plan = adapter.build_plan("R270", plan.organization_id, PARENT_CONTROL,
                                    1, family=eight.FAMILY)
    eight.require_input_readiness(input_plan)
    return parents


def _require_fixed_holdings_paths(parents, new):
    if (new["R277"]["aggregates"]["matched_baseline_target_path_sha256"] !=
            parents["R268"]["aggregates"]["matched_baseline_target_path_sha256"]
            or new["R278"]["aggregates"]["matched_baseline_target_path_sha256"] !=
               parents["R270"]["aggregates"]["matched_baseline_target_path_sha256"]
            or parents["R268"]["aggregates"]["matched_baseline_target_path_sha256"] !=
               PARENT_BASELINE_PATH_SHA256["R268"]
            or parents["R270"]["aggregates"]["matched_baseline_target_path_sha256"] !=
               PARENT_BASELINE_PATH_SHA256["R270"]):
        _fail("fixed-100 attribution did not hold selected-holdings paths fixed")
    return True


def _annual_contrasts(arms):
    names = ("cap_base", "cap_AR_weight", "AR_entry_base_weight",
             "AR_entry_AR_weight")
    if type(arms) is not dict or set(arms) != set(names):
        _fail("fixed-100 attribution annual arm census changed")
    rows = {name: arms[name]["diagnostics"]["annual_account_rows"] for name in names}
    dates = [[row[index] for index in (0, 1, 2, 3, 4)] for row in rows[names[0]]]
    if (len(dates) != 5 or [row[0] for row in dates] != [str(year) for year in range(2021, 2026)]
            or any([[row[index] for index in (0, 1, 2, 3, 4)] for row in rows[name]] != dates
                   for name in names[1:])):
        _fail("fixed-100 attribution annual axes differ")
    with localcontext() as context:
        context.prec = 96
        annual = []
        series = {key: [] for key in (
            "AR_weight_on_cap_holdings_pp", "AR_entry_count_at_base_weights_pp",
            "AR_weight_on_AR_entry_holdings_pp", "entry_weight_interaction_pp",
            "full_minus_cap_base_pp")}
        for index, date in enumerate(dates):
            a, b, c, d = (Decimal(rows[name][index][5]) for name in names)
            values = ((b - a) * 100, (c - a) * 100, (d - c) * 100,
                      ((d - c) - (b - a)) * 100, (d - a) * 100)
            annual.append({"year": date[0], **{
                key: str(value) for key, value in zip(series, values)}})
            for key, value in zip(series, values):
                series[key].append(value)
        uncertainty = {}
        for key, values in series.items():
            mean = sum(values) / Decimal(5)
            sample_variance = sum((value - mean) ** 2 for value in values) / Decimal(4)
            standard_error = (sample_variance / Decimal(5)).sqrt()
            uncertainty[key] = {
                "mean_annual_pp": str(mean),
                "t_over_five_years": (None if standard_error == 0
                                      else str(mean / standard_error)),
            }
    return annual, uncertainty


def compare_from_saved(organization_id):
    """Authenticate all four arms and report descriptive factorial contrasts."""
    control = adapter.build_plan("R277", organization_id, CONTROL, 1, family=FAMILY)
    parents = require_parents(control)
    new = {}
    for candidate in CANDIDATE_ARMS:
        found = []
        for attempt in (1, 2, 3):
            plan = adapter.build_plan(candidate, organization_id, CONTROL, attempt, family=FAMILY)
            if adapter._path(plan, "result").exists():
                found.append(_authenticated_result(plan))
        valid = [result for result in found if result["run_valid"] is True]
        if len(valid) != 1:
            _fail(f"fixed-100 attribution needs exactly one valid {candidate} result")
        new[candidate] = valid[0]
    arms = {"cap_base": parents["R268"], "cap_AR_weight": new["R277"],
            "AR_entry_base_weight": new["R278"], "AR_entry_AR_weight": parents["R270"]}
    _require_fixed_holdings_paths(parents, new)
    reference = parents["R268"]
    for name, result in arms.items():
        account, execution, report = (result["aggregates"]["account"],
                                       result["aggregates"]["execution"],
                                       result["diagnostics"])
        if (result["run_valid"] is not True
                or account["starting_equity"] != reference["aggregates"]["account"]["starting_equity"]
                or account["first_observation_session"] != "2021-01-04"
                or account["last_observation_session"] != "2025-12-31"
                or account["observation_count"] != 1255
                or execution["submitted_rebalance_count"] != 261
                or execution["completed_rebalance_count"] != 261
                or execution["invalid_order_count_sum"] != 0
                or execution["canceled_order_count_sum"] != 0
                or execution["submitted_order_count"] != execution["filled_order_count_sum"]
                or execution["actual_engine_fee_amount"] != execution["modeled_fee_amount"]
                or result["aggregates"]["target_gross_exposure"] != "0.98"
                or result["aggregates"]["admission_leverage"] != "2"
                or report["membership_cap_path_sha256"] !=
                   reference["diagnostics"]["membership_cap_path_sha256"]
                or report["etf_daily_panel_sha256"] !=
                   reference["diagnostics"]["etf_daily_panel_sha256"]):
            _fail(f"fixed-100 attribution account, orders, fee or input changed: {name}")
    with localcontext() as context:
        context.prec = 96
        returns = {name: Decimal(result["aggregates"]["account"]["cumulative_return"])
                   for name, result in arms.items()}
        a, b, c, d = (returns[key] for key in (
            "cap_base", "cap_AR_weight", "AR_entry_base_weight",
            "AR_entry_AR_weight"))
        contrasts = {
            "AR_weight_on_cap_holdings_pp": str((b - a) * 100),
            "AR_entry_count_at_base_weights_pp": str((c - a) * 100),
            "AR_weight_on_AR_entry_holdings_pp": str((d - c) * 100),
            "entry_weight_interaction_pp": str(((d - c) - (b - a)) * 100),
            "full_minus_cap_base_pp": str((d - a) * 100),
        }
    annual, uncertainty = _annual_contrasts(arms)
    return {"valid": True, "historical_diagnostic_only": True,
            "common_input_not_full_stock_minute_fill_tape": True,
            "returns": {name: str(value) for name, value in returns.items()},
            "contrasts": contrasts,
            "annual_contrasts": annual,
            "five_year_descriptive_uncertainty": uncertainty}
