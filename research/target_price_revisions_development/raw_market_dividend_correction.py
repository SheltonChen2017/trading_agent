"""OWN47: one new look for a narrow owner-inferred dividend interpretation.

Only exact action='dividend', contraticker='N/A' is interpreted as no
counterparty. This is NOT a universal vendor-null fact. The frozen converter's
same-ex-date split-adjustment-factor imputation and nonspendable receivable
model remain unchanged. Native canonical action identities are preserved.
No provider/credential path, source refresh, strategy selection or QC action.
Custody remains cooperative owner-local, not external anti-rollback protection.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os

from . import raw_market_resume as resume

market, source, raw_run = resume.market, resume.source, resume.raw_run
CORRECTION_ID = "TPR-RAWREV-DIVIDEND-CORRECTION-20261008-001"
RESUME_CODE = "0379c5d958f1cc0b75e8b02e807dc1b2e7074a2aafd9b25db8ff32b4594eba0f"
RECORDED = {
    "resume_plan_sha256": "8bb23041fa5809315b158d333c61d94cad37547865a0f4fdc61215f1d41b3422",
    "capture_report_sha256": "725a9ed6aaebf7f230147faf4fe301f9705f0874c55aaade26337e26b7fb18a3",
    "projection_sha256": "9db40559cf2d9e400eb8329556fed4cf000edbd24456d6e11037ef7ba29790c4",
    "first_simulation_report_sha256": "68518f0438ff8f14a3d63fcdbaf890018c5213dc6978fa2c732cc2bcbd186877",
    "first_private_result_sha256": "bb8bc27fe7a02d36bccabb4895b72f31843578063bfa62bfe5dba0a15fe9de56",
}
ASSUMPTION = "owner-inference-exact-dividend-N/A-means-no-counterparty-not-universal-vendor-null"


def convert_dividend_correction(structure, stocks, actions):
    """Pure, mutation-free adapter; native action IDs survive the interpretation."""
    from . import raw_market_inputs as frozen
    native, _ = frozen._inventory(actions, frozen._ACTION, ("ticker", "date", "action", "contraticker"), label="action")
    by_normalized, native_hashes, changes = {}, {}, 0
    for row in native.values():
        normalized = dict(row)
        if row["action"] == "dividend" and row["contraticker"] == "N/A":
            normalized["contraticker"] = None
            changes += 1
        original_bytes, normalized_bytes = frozen._canonical(row), frozen._canonical(normalized)
        original_id, normalized_id = source._digest(original_bytes), source._digest(normalized_bytes)
        if original_id in native_hashes and native_hashes[original_id] != original_bytes:
            raise ValueError("native action identity collision")
        native_hashes[original_id] = original_bytes
        if normalized_id in by_normalized and by_normalized[normalized_id] != (normalized_bytes, original_id):
            raise ValueError("dividend interpretation action collision")
        by_normalized[normalized_id] = (normalized_bytes, original_id)
    normalized_rows = [dict(row, contraticker=None) if row["action"] == "dividend" and row["contraticker"] == "N/A" else dict(row)
        for row in actions]
    prepared = frozen.convert(structure, stocks, normalized_rows)
    restored, seen = [], set()
    for action in prepared["corporate_actions"]:
        binding = by_normalized.get(action["action_id"])
        if binding is None or binding[1] in seen:
            raise ValueError("converted action identity binding mismatch")
        seen.add(binding[1])
        restored.append(dict(action, action_id=binding[1]))
    prepared["corporate_actions"] = tuple(sorted(restored, key=lambda row: (row["session_id"], row["security_id"], row["action_id"])))
    prepared["evidence"] = dict(prepared["evidence"], correction_id=CORRECTION_ID, owner_decision="TPR-OWN-47",
        dividend_counterparty_interpretation=ASSUMPTION, interpreted_native_action_count=changes,
        native_action_ids_preserved=True, universal_vendor_null_semantics_verified=False,
        strategy_policy_unchanged=True, accounting_interpretation_changed=True, additional_development_look_required=True)
    return prepared


@dataclass(frozen=True)
class CorrectionPlan:
    payload: bytes
    sha256: str

    def body(self):
        try:
            if type(self.payload) is not bytes or not 0 < len(self.payload) <= 65536 or source._digest(self.payload) != self.sha256:
                raise ValueError()
            body = raw_run._decode(self.payload, 65536)
            parent = _parent(body)
            expected = freeze_correction_plan(resume._original(parent.body()), parent, **{key: body[key] for key in (
                "capture_report_sha256", "projection_sha256", "first_simulation_report_sha256", "first_private_result_sha256",
                "code_sha256", "git_sha", "owner_instruction_sha256", "created_utc", "expires_utc", "mode")})
            if expected.payload != self.payload:
                raise ValueError()
            return body
        except (TypeError, ValueError, KeyError, RecursionError):
            raise ValueError("invalid dividend-correction plan") from None


def _parent(body):
    parent = resume.ResumePlan(source._canonical(body["resume_plan"]), body["resume_plan_sha256"])
    parent.body()
    return parent


def freeze_correction_plan(original, resume_plan, *, capture_report_sha256, projection_sha256,
        first_simulation_report_sha256, first_private_result_sha256, code_sha256, git_sha,
        owner_instruction_sha256, created_utc, expires_utc, mode="production"):
    if type(original) is not market.CapturePlan or type(resume_plan) is not resume.ResumePlan:
        raise ValueError("frozen original and resume plans required")
    old, parent = original.body(), resume_plan.body()
    bindings = dict(capture_report_sha256=capture_report_sha256, projection_sha256=projection_sha256,
        first_simulation_report_sha256=first_simulation_report_sha256, first_private_result_sha256=first_private_result_sha256)
    for value in (*bindings.values(), code_sha256, owner_instruction_sha256):
        source._hash(value)
    source._hash(git_sha, 40)
    created, expires = source._clock(created_utc), source._clock(expires_utc)
    if (type(mode) is not str or mode not in ("production", "offline-fixture") or parent["mode"] != mode or old["mode"] != mode
            or original.sha256 != parent["original_plan_sha256"] or parent["git_sha"] != git_sha
            or owner_instruction_sha256 != resume.detail.OWNER or not created < expires <= created + timedelta(hours=12)
            or not source._clock(parent["created_utc"]) <= created < source._clock(parent["expires_utc"])
            or expires > source._clock(parent["expires_utc"])):
        raise ValueError("invalid prospective dividend-correction scope")
    if mode == "production" and (git_sha != resume.detail.HEAD or parent["code_sha256"] != RESUME_CODE
            or dict(bindings, resume_plan_sha256=resume_plan.sha256) != RECORDED):
        raise ValueError("correction requires exact executed chain")
    body = {"schema": "tpr-raw-dividend-correction-plan-v1", "correction_id": CORRECTION_ID, "base_candidate_id": market.CANDIDATE_ID,
        "owner_decision": "TPR-OWN-47", "owner_instruction_sha256": owner_instruction_sha256, "mode": mode,
        "resume_plan": parent, "resume_plan_sha256": resume_plan.sha256, "original_plan_sha256": original.sha256,
        **bindings, "resume_code_sha256": RESUME_CODE, "code_sha256": code_sha256, "code_hashes": old["code_hashes"],
        "git_sha": git_sha, "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "structure_sha256": old["structure_sha256"], "waiver_sha256": old["waiver_sha256"], "candidate_policy_sha256": old["candidate_policy_sha256"],
        "price_dates": old["price_dates"], "action_dates": old["action_dates"], "ticker_count": len(old["tickers"]),
        "lane_root": str(raw_run.LANE_ROOT), "lane_branch": raw_run.LANE_BRANCH, "private_root": str(market.PRODUCTION_ROOT),
        "reservation_file": CORRECTION_ID + ".spent.json", "original_spent_file": market.CANDIDATE_ID + ".spent.json",
        "prior_simulation_spent_file": market.CANDIDATE_ID + ".simulation.spent.json", "interpretation": ASSUMPTION,
        "native_action_ids_preserved": True, "universal_vendor_null_semantics_verified": False,
        "additional_development_looks": 1, "cumulative_development_looks": 2, "prior_look_or_simulation_rearmed": False,
        "provider_requests": 0, "source_refresh": False, "strategy_policy_unchanged": True,
        "accounting_interpretation_changed": True, "canonical_admission": False,
        "contractual_rights_verified": False, "quantconnect": False, "trading": False}
    payload = source._canonical(body)
    return CorrectionPlan(payload, source._digest(payload))


def public_plan_summary(plan):
    body = plan.body()
    return source._canonical(dict({k: v for k, v in body.items() if k not in ("resume_plan", "private_root")},
        schema="tpr-raw-dividend-correction-plan-summary-v1", correction_plan_sha256=plan.sha256, native_ticker_list_published=False))


def _identity(body):
    resume._identity(body["resume_plan"])
    source._verify_code(raw_run.LANE_ROOT / "research/target_price_revisions_development/raw_market_resume.py", RESUME_CODE)
    source._verify_code(raw_run.LANE_ROOT / "research/target_price_revisions_development/raw_market_dividend_correction.py", body["code_sha256"])


def _history(fd, plan):
    body, parent = plan.body(), _parent(plan.body())
    resume._history(fd, parent)
    resume._check_resume_claim(fd, parent)
    captured = resume._read(fd, resume.RESUME_ID + "." + body["capture_report_sha256"] + ".aggregate.json", body["capture_report_sha256"])
    if resume._admit_capture_report(captured, parent) != body["projection_sha256"]:
        raise ValueError("correction capture identity mismatch")
    claim = resume.detail._owned_claim(fd, market.CANDIDATE_ID + ".simulation.spent.json")
    started = source._clock(claim["started_utc"])
    market._before_expiry(parent.body(), started)
    if source._canonical(claim) != source._canonical(resume._claim_body(parent, started,
            capture_report_sha256=body["capture_report_sha256"], projection_sha256=body["projection_sha256"])):
        raise ValueError("correction prior simulation claim mismatch")
    prior = resume._read(fd, resume.RESUME_ID + "." + body["first_simulation_report_sha256"] + ".simulation.aggregate.json",
        body["first_simulation_report_sha256"])
    required = {"schema", "resume_id", "resume_plan_sha256", "original_plan_sha256", "capture_report_sha256", "projection_sha256",
        "private_report_sha256", "mode", "status", "failure", "failure_stage", "summary", "existing_development_look_spent",
        "additional_development_looks", "simulation_runs", "canonical_admission", "quantconnect_attempts", "trading"}
    if (set(prior) != required or prior["schema"] != "tpr-raw-resume-simulation-report-v1" or prior["resume_id"] != resume.RESUME_ID
            or prior["resume_plan_sha256"] != parent.sha256 or prior["original_plan_sha256"] != body["original_plan_sha256"]
            or prior["capture_report_sha256"] != body["capture_report_sha256"] or prior["projection_sha256"] != body["projection_sha256"]
            or prior["private_report_sha256"] != body["first_private_result_sha256"] or prior["mode"] != body["mode"]
            or prior["status"] != "SIMULATED" or prior["failure"] is not None or prior["failure_stage"] is not None
            or type(prior["summary"]) is not dict or prior["canonical_admission"] is not False or prior["trading"] is not False):
        raise ValueError("correction prior simulation receipt mismatch")
    for key, value in (("simulation_runs", 1), ("additional_development_looks", 0), ("quantconnect_attempts", 0),
            ("existing_development_look_spent", 1 if body["mode"] == "production" else 0)):
        if type(prior[key]) is not int or prior[key] != value:
            raise ValueError("correction prior simulation counter mismatch")
    return prior


def _claim_body(plan, current):
    body = plan.body()
    return {"schema": "tpr-dividend-correction-reservation-v1", "correction_id": CORRECTION_ID,
        "correction_plan_sha256": plan.sha256, "resume_plan_sha256": body["resume_plan_sha256"],
        "capture_report_sha256": body["capture_report_sha256"], "projection_sha256": body["projection_sha256"],
        "first_simulation_report_sha256": body["first_simulation_report_sha256"], "first_private_result_sha256": body["first_private_result_sha256"],
        "code_sha256": body["code_sha256"], "resume_code_sha256": RESUME_CODE, "code_hashes": body["code_hashes"],
        "started_utc": current.isoformat(), "mode": body["mode"], "additional_development_look_reserved": 1 if body["mode"] == "production" else 0,
        "cumulative_development_looks": 2 if body["mode"] == "production" else 0, "fixture_runs": 1 if body["mode"] == "offline-fixture" else 0}


def _projection(fd, body, current):
    identity = body["projection_sha256"]
    projection = resume._read(fd, resume.RESUME_ID + "." + identity + ".projection.json", identity, resume.LIMITS["total_bytes"])
    required = {"schema", "resume_id", "resume_plan_sha256", "original_plan_sha256", "mode", "structure_sha256", "waiver_sha256",
        "code_hashes", "resume_code_sha256", "capture_utc", "prices", "actions", "pages", "native_source_rows", "exact_duplicate_rows",
        "transactional_snapshot", "point_in_time_data", "canonical_admission"}
    if (set(projection) != required or projection["schema"] != "tpr-raw-market-resume-projection-v1" or projection["resume_id"] != resume.RESUME_ID
            or projection["resume_plan_sha256"] != body["resume_plan_sha256"] or projection["original_plan_sha256"] != body["original_plan_sha256"]
            or projection["mode"] != body["mode"] or projection["structure_sha256"] != body["structure_sha256"]
            or projection["waiver_sha256"] != body["waiver_sha256"] or projection["code_hashes"] != body["code_hashes"]
            or projection["resume_code_sha256"] != body["resume_plan"]["code_sha256"]
            or not source._clock(body["resume_plan"]["created_utc"]) <= source._clock(projection["capture_utc"]) <= current
            or any(projection[key] is not False for key in ("transactional_snapshot", "point_in_time_data", "canonical_admission"))):
        raise ValueError("correction projection binding mismatch")
    return projection


def _compute(structure, projection):
    from .raw_candidate import run_accounted_raw_candidate
    return run_accounted_raw_candidate(structure, convert_dividend_correction(structure, projection["prices"], projection["actions"]))


def execute_correction(plan):
    if type(plan) is not CorrectionPlan or plan.body()["mode"] != "production":
        raise ValueError("public dividend correction is production-only")
    return _execute(plan, market.PRODUCTION_ROOT)


def _execute_fixture(plan, root, *, now):
    if type(plan) is not CorrectionPlan or plan.body()["mode"] != "offline-fixture" or root == market.PRODUCTION_ROOT:
        raise ValueError("fixture correction requires synthetic root and mode")
    return _execute(plan, root, now=now)


def _execute(plan, root, *, now=None):
    body = plan.body()
    production = body["mode"] == "production"
    if production:
        if root != market.PRODUCTION_ROOT or now is not None:
            raise ValueError("production correction context cannot change")
        _identity(body)
    elif root == market.PRODUCTION_ROOT or now is None:
        raise ValueError("fixture correction requires synthetic context")
    current = datetime.now(timezone.utc) if now is None else now
    market._before_expiry(body, current)
    market._before_expiry(body["resume_plan"], current)
    fd = raw_run._open_root(root, body["mode"])
    try:
        prior = _history(fd, plan)
        claim_failure = resume._claim(fd, CORRECTION_ID + ".spent.json", _claim_body(plan, current))
        status, stage, failure, interrupted, private_id, private_path, summary, evidence = "FAILED", "reservation", None, False, None, None, None, None
        try:
            if claim_failure:
                if claim_failure.interrupted: raise KeyboardInterrupt
                raise claim_failure
            stage = "expiry"
            market._before_expiry(body, datetime.now(timezone.utc) if now is None else now)
            stage = "prior_result"
            first = resume._read(fd, resume.RESUME_ID + "." + body["first_private_result_sha256"] + ".backtest.json",
                body["first_private_result_sha256"], resume.LIMITS["total_bytes"])
            if (set(first) != {"schema", "resume_plan_sha256", "capture_report_sha256", "projection_sha256", "code_sha256", "code_hashes", "result", "summary"}
                    or first["schema"] != "tpr-raw-resume-private-simulation-v1" or first["resume_plan_sha256"] != body["resume_plan_sha256"]
                    or first["capture_report_sha256"] != body["capture_report_sha256"] or first["projection_sha256"] != body["projection_sha256"]
                    or first["code_sha256"] != body["resume_plan"]["code_sha256"] or first["code_hashes"] != body["code_hashes"]
                    or first["summary"] != prior["summary"]):
                raise ValueError("correction first private result binding mismatch")
            stage = "projection"
            projection = _projection(fd, body, current)
            stage = "structure"
            structure = resume._read(fd, "structure.json", body["structure_sha256"], raw_run.MAX_INPUT_BYTES)
            stage = "simulation"
            result = _compute(structure, projection)
            if production: _identity(body)
            stage = "summary"
            summary, evidence = market._result_summary(result), result["accounting_model"]
            payload = source._canonical({"schema": "tpr-raw-dividend-correction-private-result-v1", "correction_id": CORRECTION_ID,
                "correction_plan_sha256": plan.sha256, "projection_sha256": body["projection_sha256"], "code_sha256": body["code_sha256"],
                "first_private_result_sha256": body["first_private_result_sha256"], "result": result, "summary": summary})
            if len(payload) > resume.LIMITS["total_bytes"]: raise ValueError("correction private result size bound")
            private_id = source._digest(payload)
            name = CORRECTION_ID + "." + private_id + ".backtest.json"
            stage = "publication"
            source._publish(fd, name, payload)
            private_path, status = root / name, "SIMULATED"
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "dividend_correction_interrupted", True
        except Exception:
            failure = "dividend_correction_failed"
        report = {"schema": "tpr-raw-dividend-correction-report-v1", "correction_id": CORRECTION_ID, "base_candidate_id": market.CANDIDATE_ID,
            "correction_plan_sha256": plan.sha256, "resume_plan_sha256": body["resume_plan_sha256"],
            "capture_report_sha256": body["capture_report_sha256"], "projection_sha256": body["projection_sha256"],
            "first_simulation_report_sha256": body["first_simulation_report_sha256"], "first_private_result_sha256": body["first_private_result_sha256"],
            "private_result_sha256": private_id, "mode": body["mode"], "status": status, "failure": failure,
            "failure_stage": stage if status != "SIMULATED" else None, "summary": summary, "accounting_evidence": evidence,
            "owner_decision": "TPR-OWN-47", "interpretation": ASSUMPTION, "additional_development_looks": 1 if production else 0,
            "cumulative_development_looks": 2 if production else 0, "fixture_runs": 0 if production else 1,
            "prior_look_or_simulation_rearmed": False, "provider_requests": 0, "source_refresh": False,
            "contractual_rights_verified": False, "canonical_admission": False, "quantconnect_attempts": 0, "trading": False}
        payload = source._canonical(report)
        identity = source._digest(payload)
        name, terminal = CORRECTION_ID + "." + identity + ".aggregate.json", CORRECTION_ID + ".terminal.json"
        source._publish(fd, name, payload)
        source._publish(fd, terminal, source._canonical({"schema": "tpr-dividend-correction-terminal-v1", "correction_id": CORRECTION_ID,
            "correction_plan_sha256": plan.sha256, "aggregate_sha256": identity, "private_result_sha256": private_id, "status": status,
            "additional_development_looks": 1 if production else 0, "cumulative_development_looks": 2 if production else 0}))
        if interrupted: raise KeyboardInterrupt("dividend correction interrupted; remains spent") from None
        return market.SimulationResult(payload, identity, private_path, root / name, root / terminal)
    finally:
        os.close(fd)
