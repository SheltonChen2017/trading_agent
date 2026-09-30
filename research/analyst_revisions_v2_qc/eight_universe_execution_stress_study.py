"""Frozen four-arm 5-bps stress identity and explicit ADV unavailability.

The four source projections are physical-order backtests, but this module
never launches QC or reads an outcome. No volume feed has yet been admitted:
the 1%-of-20-prior-session-ADV leg is unavailable, not a passing zero.
"""

import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path

from . import accepted_risk_six_universe_order_qc_projection as source_contract
from . import eight_universe_attribution_study as attribution
from . import eight_universe_execution_stress_projection as projection
from . import eight_universe_study as eight
from . import six_universe_relaxed_submission as adapter


class EightUniverseExecutionStressStudyError(ValueError):
    """The prospective source, frozen manifest or input ancestry changed."""


FAMILY = "eight_execution_stress"
SCHEMA = "arv2-eight-fixed100-five-bps-execution-stress-study-v1"
MANIFEST_PATH = Path(__file__).with_name("eight_universe_execution_stress_candidates.json")
CONTROL = Path(__file__).resolve().parents[2] / (
    "artifacts/analyst_revisions_v2/eight_execution_stress_qc_control_20260929")
FROZEN_MANIFEST_SHA256 = "1e1754c6bf46aceeb03aadb80647c11524094063c0fe0d59ae5121a2a5d7f5fa"
PARENT_BY_CANDIDATE = {
    "R280": "R268", "R281": "R277", "R282": "R278", "R283": "R270"}
PARENT_RESULT_SHA256 = {
    "R268": "45171f6720f5cb187f6772e02dc0654e0455d5ebb03be3401611295e5c2fc1ac",
    "R277": "b869a20a8f6abc90111237e1c0553ab2744c2f3f1163f6ccc8302b9b92b9f821",
    "R278": "b93eb261298d65052de33f0caba07fc5cd2a212d7388b2783f6219657da4929d",
    "R270": "afa7b3a6299a28e80e80dd868e322a298643eaac5acb9e6de5a6ae13135d1a6c",
}
ARMS = {
    "R280": "ar_off", "R281": "ar_on100_weights_only",
    "R282": "ar_on0", "R283": "ar_on100"}
PINS = {
    "R280": ("4cc0a420bc4c0ed48c65aef1d27be49b840913f0045beed23f92ec28a3f3ffdd",
             "15f5f52f9d084ea9c7af1755867e1b016054aacd1e6498ac561ac132bfae8f72",
             "bf8ad26e49b0cb4a77fe8c2773b7276b0342870b17854d08946bcb3715ebd7d9"),
    "R281": ("7a725fe4dc8d913cf56916b1f3d87409e6019a0cb01c7f1c73231e679fdddc2d",
             "5e5c53cbda74b2a1e4cb30f55ad22b5027baedbe67087ba236a24c1715a1d57e",
             "8aa4cee20367332d894205b9b389d4bd896bfb7b31be08096b212426fb755a1a"),
    "R282": ("ce56c5860e2c76af685f02da53fcc18d5c93e5caa208e09b37ef8749ada1b5fe",
             "3563d10778d2ea843aad7e6c15a9e7d056567f25770879d76899e030cded075c",
             "c52e857af3d24512e591cbd8d6b3ea0a64834c4382c31cc9f11448f870a5e267"),
    "R283": ("bf5a8a130efe4a89d57ee06c62333bccd59c0d0ad72fbae0b6fbee4687ff12b1",
             "9119debdeaf8108eff46cffe74cc4d5df46b92ba59d09612a8ed03bbe5db310c",
             "3d2b91a0f3d21af268689da58ab9ee67c2aa4c36721034f6c92429a89c272a5e"),
}
ADV_UNAVAILABLE = {
    "status": "unavailable",
    "reason": "no_authenticated_prior_20_closed_session_RAW_volume_feed_in_source_v1",
}
PROTOCOL = {
    "parent_candidates": ["R268-A3", "R277-A1", "R278-A1", "R270-A1"],
    "new_candidates": list(PARENT_BY_CANDIDATE),
    "window": ["2021-01-04", "2025-12-31"],
    "universes": ["SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE", "XLI", "XLF"],
    "decision_count": 261,
    "observation_count": 1255,
    "fixed_tilt_percent": 100,
    "target_gross_exposure": "0.98",
    "modeled_fee_bps_per_side": "10",
    "slippage_bps_per_side": "5",
    "slippage_model": "ConstantSlippageModel(0.0005)",
    "admission_leverage": "2",
    "maximum_attempts_per_candidate": 3,
    "physical_orders": True,
    "liquidity_capacity_diagnostic": ADV_UNAVAILABLE,
    "historical_exploratory_diagnostic_only": True,
    "formal_alpha_or_forward_efficacy": False,
    "paper_live_or_funded_orders": False,
}


def _fail(message):
    raise EightUniverseExecutionStressStudyError(message)


def _parents():
    attribute = attribution.frozen_manifest()
    return {
        "R268": adapter._eight_r268_a3_manifest()["candidates"][0],
        "R277": attribute["candidates"][0],
        "R278": attribute["candidates"][1],
        "R270": next(row for row in adapter._eight_ar_on_split_manifest()["candidates"]
                     if row["candidate_id"] == "R270"),
    }


def _row(package, candidate, parent):
    rendered, profile = projection.build_projection(package, candidate)
    files = [[item.project_path, item.content_sha256, item.byte_count]
             for item in rendered.source_files]
    files_sha256 = hashlib.sha256(source_contract._canonical(files)).hexdigest()
    if ((rendered.projection_sha256, profile["profile_sha256"], files_sha256)
            != PINS[candidate]
            or parent["projection_sha256"]
            != projection.CANDIDATE_PARENTS[candidate][1]
            or profile["slippage_bps"] != "5"):
        _fail("five-bps stress source or predecessor pin changed")
    return {**parent,
            "candidate_id": candidate,
            "arm": ARMS[candidate],
            "project_name": f"ARV2 EIGHT EXECUTION STRESS {candidate} 2021 2025",
            "backtest_name": f"ARV2 {candidate} fixed100 five-bps execution stress 2021 2025",
            "role": rendered.role,
            "profile_id": rendered.profile_id,
            "profile_sha256": rendered.profile_sha256,
            "projection_schema": rendered.schema,
            "projection_sha256": rendered.projection_sha256,
            "source_files_sha256": files_sha256,
            "source_file_count": len(files),
            "total_source_bytes": rendered.total_source_byte_count,
            "slippage_bps": 5}


def freeze_manifest(package):
    """Render the exact four source identities before any external action."""
    parents = _parents()
    rows = [_row(package, candidate, parents[PARENT_BY_CANDIDATE[candidate]])
            for candidate in PARENT_BY_CANDIDATE]
    if len({row["source_files_sha256"] for row in rows}) != 4:
        _fail("five-bps stress sources are not distinct")
    return {
        "schema": SCHEMA,
        "protocol": PROTOCOL,
        "package_sha256": attribution.frozen_manifest()["package_sha256"],
        "activation_manifest_sha256": attribution.frozen_manifest()["activation_manifest_sha256"],
        "parent_manifest_sha256s": {
            "R268": adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256,
            "R277/R278": attribution.FROZEN_MANIFEST_SHA256,
            "R270": adapter.FROZEN_EIGHT_AR_ON_SPLIT_MANIFEST_SHA256,
        },
        "parent_result_sha256s": PARENT_RESULT_SHA256,
        "parent_projection_sha256s": {
            parent: projection.CANDIDATE_PARENTS[candidate][1]
            for candidate, parent in PARENT_BY_CANDIDATE.items()},
        "candidates": rows,
    }


def frozen_manifest():
    if type(FROZEN_MANIFEST_SHA256) is not str:
        _fail("five-bps stress manifest has not been frozen")
    try:
        raw = MANIFEST_PATH.read_bytes()
        current = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise EightUniverseExecutionStressStudyError(
            "five-bps stress manifest is unavailable or malformed") from exc
    if (hashlib.sha256(raw).hexdigest() != FROZEN_MANIFEST_SHA256
            or type(current) is not dict
            or current.get("schema") != SCHEMA
            or current.get("protocol") != PROTOCOL
            or [row.get("candidate_id") for row in current.get("candidates", ())]
               != list(PARENT_BY_CANDIDATE)
            or any((row.get("projection_sha256"), row.get("profile_sha256"),
                    row.get("source_files_sha256")) != PINS[row["candidate_id"]]
                   for row in current["candidates"])):
        _fail("five-bps stress frozen manifest changed")
    return current


def build_projection(package, candidate):
    if candidate not in PARENT_BY_CANDIDATE:
        _fail("five-bps stress candidate changed")
    return projection.build_projection(package, candidate)


def require_parents(plan):
    """Reauthenticate the completed four-arm zero-slippage comparison locally."""
    if plan.family != FAMILY or plan.candidate_id not in PARENT_BY_CANDIDATE:
        _fail("five-bps stress parent plan changed")
    summary = attribution.compare_from_saved(plan.organization_id)
    if (summary.get("valid") is not True
            or summary.get("common_input_not_full_stock_minute_fill_tape") is not True):
        _fail("five-bps stress parent result is not valid")
    results = {}
    for parent, digest in PARENT_RESULT_SHA256.items():
        control = (attribution.CONTROL if parent in {"R277", "R278"}
                   else attribution.PARENT_CONTROL)
        family = (attribution.FAMILY if parent in {"R277", "R278"}
                  else "eight_universe")
        attempt = 3 if parent == "R268" else 1
        prior = adapter.build_plan(parent, plan.organization_id, control, attempt,
                                   family=family)
        try:
            raw = adapter._path(prior, "result").read_bytes()
        except OSError:
            _fail("five-bps stress parent result is unavailable")
        if hashlib.sha256(raw).hexdigest() != digest:
            _fail("five-bps stress parent result bytes changed")
        result = attribution._authenticated_result(prior)
        if result["run_valid"] is not True:
            _fail("five-bps stress predecessor is not valid")
        results[parent] = result
    return {"summary": summary, "results": results}


def parse_order(plan, statistics):
    """Parse one three-statistic physical-order result with explicit 5-bps evidence."""
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or row["candidate_id"] not in PARENT_BY_CANDIDATE
            or set(statistics) != set(row["statistic_names"])):
        _fail("five-bps stress result inventory changed")
    parsed = adapter._parse_order_common(
        plan, statistics, expected_geometry=None, decision_count=261,
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({
            "comparison_arm", "analyst_revision_economic_usage", "coverage_policy_id",
            "execution_stress_fill_audit"}),
        result_transport="three_bounded_custom_summary_statistics",
        eight_universe=True,
    )
    aggregate, meta = parsed["aggregates"], parsed["meta"]
    if (aggregate.get("comparison_arm") != row["arm"]
            or aggregate.get("analyst_revision_economic_usage") !=
               row["analyst_revision_economic_usage"]
            or aggregate.get("coverage_policy_id") != row["coverage_policy_id"]):
        _fail("five-bps stress economic arm changed")
    audit = aggregate.get("execution_stress_fill_audit")
    execution = aggregate["execution"]
    if (type(audit) is not dict or set(audit) != {
            "schema", "filled_moo_count", "buy_fill_count", "sell_fill_count",
            "unverifiable_fill_count", "non_adverse_fill_count",
            "minimum_signed_adverse_bps", "reference", "valid"}
            or audit["schema"] != "arv2-eight-five-bps-moo-fill-audit-v1"
            or audit["reference"] != "same-session-TradeBar-open"
            or any(type(audit[key]) is not int or audit[key] < 0 for key in (
                "filled_moo_count", "buy_fill_count", "sell_fill_count",
                "unverifiable_fill_count", "non_adverse_fill_count"))
            or audit["filled_moo_count"] != audit["buy_fill_count"] + audit["sell_fill_count"]
            or type(audit["valid"]) is not bool
            or (audit["minimum_signed_adverse_bps"] is not None
                and not adapter.cap._finite_decimal(audit["minimum_signed_adverse_bps"]))
            or (audit["valid"] is not (
                audit["filled_moo_count"] == execution["filled_order_count_sum"]
                and audit["buy_fill_count"] > 0 and audit["sell_fill_count"] > 0
                and audit["unverifiable_fill_count"] == 0
                and audit["non_adverse_fill_count"] == 0
                and audit["minimum_signed_adverse_bps"] is not None
                and Decimal(audit["minimum_signed_adverse_bps"]) > 0))
            or (parsed["run_valid"] is True and audit["valid"] is not True)):
        _fail("five-bps stress fill audit is inconsistent")
    baseline_parent = "R268" if plan.candidate_id in {"R280", "R281"} else "R270"
    if aggregate.get("matched_baseline_target_path_sha256") != \
            attribution.PARENT_BASELINE_PATH_SHA256[baseline_parent]:
        _fail("five-bps stress matched selected-name/weight baseline path changed")
    report = adapter._statistic(statistics["ARV2_EIGHT_GATE_ORDER_DIAGNOSTICS"])
    if (meta.get("matched_diagnostics_sha256") != adapter._sha(report)
            or report.get("arm") != row["arm"]):
        _fail("five-bps stress diagnostic identity changed")
    eight._validate_eight_diagnostics(report, row["arm"], expected_slippage_bps=5)
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        _fail("five-bps stress diagnostic and account return differ")
    return {**parsed, "diagnostics": report}


def _authenticated_result(plan):
    row = adapter._candidate(plan)
    launch = adapter.common._read(adapter._path(plan, "launch"))
    adapter._receipt(plan, launch)
    expected = {"candidate_id": plan.candidate_id, "attempt": plan.attempt,
                "project_id": launch["project_id"],
                "backtest_id": launch["backtest_id"], "status": "Completed."}
    if (adapter.common._read(adapter._path(plan, "project")) != {
            "candidate_id": plan.candidate_id, "project_id": launch["project_id"],
            "project_name": row["project_name"]}
            or adapter.common._read(adapter._path(plan, "terminal")) != expected
            or adapter.common._read(adapter._path(plan, "read-claim")) != expected):
        _fail("five-bps stress retained terminal or read claim changed")
    raw = adapter._read_artifact(adapter._path(plan, "raw-custom"))
    if (type(raw) is not dict or set(raw) != set(expected) | {"statistics"}
            or any(raw.get(key) != value for key, value in expected.items())
            or type(raw["statistics"]) is not dict
            or set(raw["statistics"]) != set(row["statistic_names"])):
        _fail("five-bps stress retained statistic inventory changed")
    parsed = parse_order(plan, raw["statistics"])
    saved = adapter._read_artifact(adapter._path(plan, "result"))
    if saved != {**expected, **parsed,
                 "manifest_sha256": adapter._plan_manifest_sha256(plan),
                 "projection_sha256": row["projection_sha256"]}:
        _fail("five-bps stress saved result differs from exact statistics")
    return saved


def compare_from_saved(organization_id):
    """Value-free QC access: compare only four one-use local result artifacts."""
    anchor = adapter.build_plan("R280", organization_id, CONTROL, 1, family=FAMILY)
    parents = require_parents(anchor)["results"]
    arms = {}
    names = {"R280": "cap_base", "R281": "cap_AR_weight",
             "R282": "AR_entry_base_weight", "R283": "AR_entry_AR_weight"}
    for candidate, name in names.items():
        found = []
        for attempt in (1, 2, 3):
            plan = adapter.build_plan(candidate, organization_id, CONTROL,
                                      attempt, family=FAMILY)
            if adapter._path(plan, "result").exists():
                found.append(_authenticated_result(plan))
        valid = [item for item in found if item["run_valid"] is True]
        if len(valid) != 1:
            _fail("five-bps stress requires exactly one valid " + candidate + " result")
        arms[name] = valid[0]
    reference = arms["cap_base"]["diagnostics"]
    reference_account = parents["R268"]["aggregates"]["account"]
    for candidate, name in names.items():
        result = arms[name]
        aggregate, report = result["aggregates"], result["diagnostics"]
        execution = aggregate["execution"]
        account = aggregate["account"]
        parent = parents[PARENT_BY_CANDIDATE[candidate]]
        parent_report = parent["diagnostics"]
        if (account["starting_equity"] != reference_account["starting_equity"]
                or account["first_observation_session"] != "2021-01-04"
                or account["last_observation_session"] != "2025-12-31"
                or account["observation_count"] != 1255
                or aggregate["target_gross_exposure"] != "0.98"
                or aggregate["admission_leverage"] != "2"
                or report["membership_cap_path_sha256"] != reference["membership_cap_path_sha256"]
                or report["etf_daily_panel_sha256"] != reference["etf_daily_panel_sha256"]
                or report["membership_cap_path_sha256"] !=
                   parent_report["membership_cap_path_sha256"]
                or report["etf_daily_panel_sha256"] !=
                   parent_report["etf_daily_panel_sha256"]
                or report["slippage_bps_per_side"] != 5
                or aggregate["execution_stress_fill_audit"]["valid"] is not True
                or execution["submitted_rebalance_count"] != 261
                or execution["completed_rebalance_count"] != 261
                or execution["invalid_order_count_sum"] != 0
                or execution["canceled_order_count_sum"] != 0
                or execution["submitted_order_count"] != execution["filled_order_count_sum"]
                or execution["actual_engine_fee_amount"] != execution["modeled_fee_amount"]):
            _fail("five-bps stress common input, fill, fee or order gate changed: " + name)
    if (arms["cap_base"]["aggregates"]["matched_baseline_target_path_sha256"] !=
            arms["cap_AR_weight"]["aggregates"]["matched_baseline_target_path_sha256"]
            or arms["AR_entry_base_weight"]["aggregates"]["matched_baseline_target_path_sha256"] !=
               arms["AR_entry_AR_weight"]["aggregates"]["matched_baseline_target_path_sha256"]):
        _fail("five-bps stress fixed-pair matched selection path changed")
    with localcontext() as context:
        context.prec = 96
        returns = {name: Decimal(item["aggregates"]["account"]["cumulative_return"])
                   for name, item in arms.items()}
        a, b, c, d = (returns[name] for name in (
            "cap_base", "cap_AR_weight", "AR_entry_base_weight", "AR_entry_AR_weight"))
        contrasts = {
            "AR_weight_on_cap_holdings_pp": str((b - a) * 100),
            "AR_entry_count_at_base_weights_pp": str((c - a) * 100),
            "AR_weight_on_AR_entry_holdings_pp": str((d - c) * 100),
            "entry_weight_interaction_pp": str(((d - c) - (b - a)) * 100),
            "full_minus_cap_base_pp": str((d - a) * 100),
        }
        paired = {}
        for candidate, parent in PARENT_BY_CANDIDATE.items():
            stressed = arms[names[candidate]]["aggregates"]
            unstressed = parents[parent]["aggregates"]
            paired[candidate] = {
                "parent": parent,
                "net_return_change_pp": str((
                    Decimal(stressed["account"]["cumulative_return"])
                    - Decimal(unstressed["account"]["cumulative_return"])) * 100),
                "modeled_fee_change": str(
                    Decimal(stressed["execution"]["modeled_fee_amount"])
                    - Decimal(unstressed["execution"]["modeled_fee_amount"])),
                "maximum_drawdown_change_pp": str((
                    Decimal(stressed["account"]["maximum_drawdown"])
                    - Decimal(unstressed["account"]["maximum_drawdown"])) * 100),
            }
    annual, uncertainty = attribution._annual_contrasts(arms)
    return {"valid": True, "historical_diagnostic_only": True,
            "all_moo_fill_audits_valid": True,
            "liquidity_capacity_diagnostic": ADV_UNAVAILABLE,
            "returns": {name: str(value) for name, value in returns.items()},
            "paired_five_bps_minus_zero_bps": paired,
            "contrasts": contrasts, "annual_contrasts": annual,
            "five_year_descriptive_uncertainty": uncertainty}


__all__ = ("ADV_UNAVAILABLE", "ARMS", "CONTROL", "FAMILY", "FROZEN_MANIFEST_SHA256",
           "MANIFEST_PATH", "PARENT_BY_CANDIDATE", "PARENT_RESULT_SHA256", "PINS", "PROTOCOL",
           "build_projection", "compare_from_saved", "freeze_manifest",
           "frozen_manifest", "parse_order", "require_parents")
