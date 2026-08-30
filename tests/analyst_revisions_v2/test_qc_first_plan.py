from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import research.analyst_revisions_v2.qc_first_plan as plan_module
from research.analyst_revisions_v2.qc_first_plan import (
    QcFirstPlanError,
    load_qc_first_study_plan,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN = (
    ROOT
    / "research"
    / "analyst_revisions_v2"
    / "specs"
    / "arv2_qc_first.draft.json"
)


def _canonical(raw: dict[str, object]) -> bytes:
    return json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _rehash(raw: dict[str, object]) -> None:
    raw["plan_id"] = None
    raw["plan_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    raw["plan_hash"] = digest
    raw["plan_id"] = f"arv2-qc-first-plan-{digest[:16]}"


def _write(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    legacy = PLAN.with_name("arv2_round0.draft.json")
    legacy_target = tmp_path / legacy.name
    if not legacy_target.exists():
        legacy_target.write_bytes(legacy.read_bytes())
    return path


def test_repository_plan_is_exactly_outcome_free_and_stage_separated() -> None:
    plan = load_qc_first_study_plan(PLAN)

    assert plan.supersession["disposition"] == (
        "superseded_unspent_by_owner_qc_first_direction"
    )
    assert plan.supersession["looks_consumed"] == 0
    assert plan.multiplicity_contract["prospective_permanent_look_alpha"] == {
        "numerator": 1,
        "denominator": 60,
    }
    assert plan.qc_historical_contract["outcome_data_cutoff_session"] == (
        "2026-08-28"
    )
    assert plan.qc_historical_contract[
        "last_eligible_decision_session_by_horizon"
    ] == {
        "1": "2026-08-27",
        "5": "2026-08-21",
        "20": "2026-07-31",
        "60": "2026-06-03",
    }
    assert plan.qc_historical_contract["qc_plan_sha256"] is None
    assert plan.prospective_paper_contract["start"] is None
    assert plan.prospective_paper_contract["end"] is None
    assert plan.prospective_paper_contract["duration_nyse_sessions"] == 252
    assert plan.funded_pilot_contract["current_authority"] == "none"
    assert plan.upload_available is False
    assert plan.historical_launch_available is False
    assert plan.paper_deployment_available is False
    assert plan.funded_live_available is False

    with pytest.raises(TypeError):
        plan.qc_historical_contract["launch_authorized"] = True
    with pytest.raises(TypeError):
        plan_module.QC_HISTORICAL_POLICY["launch_authorized"] = True
    with pytest.raises(AttributeError):
        plan_module._ROOT_KEYS.add("launch_authorized")


def test_amendment_hash_binds_the_exact_superseded_base_artifact() -> None:
    plan = load_qc_first_study_plan(PLAN)
    legacy_path = PLAN.with_name("arv2_round0.draft.json")
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))

    assert plan.inheritance_contract["mode"] == (
        "hash_bound_amendment_not_complete_successor_specification"
    )
    assert legacy["spec_id"] == plan.supersession["legacy_spec_id"]
    assert legacy["spec_hash"] == plan.supersession["legacy_spec_hash"]
    assert legacy["looks"][0]["look_id"] == plan.supersession["legacy_look_id"]
    assert plan.inheritance_contract["base_spec_hash"] == legacy["spec_hash"]


def test_missing_or_content_substituted_superseded_base_refuses(
    tmp_path: Path,
) -> None:
    raw = json.loads(PLAN.read_text(encoding="utf-8"))
    path = _write(tmp_path, raw)
    legacy_path = tmp_path / "arv2_round0.draft.json"
    legacy_path.unlink()
    with pytest.raises(QcFirstPlanError, match="base artifact is unavailable"):
        load_qc_first_study_plan(path)

    path = _write(tmp_path, raw)
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    legacy["cells"][0]["source"] = "substituted without changing embedded hash"
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    with pytest.raises(QcFirstPlanError, match="base content hash"):
        load_qc_first_study_plan(path)


def test_historical_development_and_future_paper_contracts_cannot_blur() -> None:
    plan = load_qc_first_study_plan(PLAN)
    multiplicity = plan.multiplicity_contract
    controls = plan.control_contract
    study = plan.stock_event_study_contract
    historical = plan.qc_historical_contract
    paper = plan.prospective_paper_contract

    assert multiplicity["development_evidence_role"] == (
        "selection_and_engineering_only_no_confirmatory_alpha_claim"
    )
    assert tuple(multiplicity["prospective_permanent_look_ids"]) == (
        "arv2-look-etf-paper-prospective-001",
    )
    assert historical["stock_stage"]["confirmatory_alpha_spent"] is False
    assert historical["etf_stage"]["confirmatory_alpha_spent"] is False
    assert "migration_only" in historical["legacy_v1_preregistration"]
    assert controls["stock_residualization"]["fit_population"] == (
        "active_rating_signal_stock_rows_in_training_fold_only"
    )
    assert controls["etf_residualization"]["current_execution_authorized"] is False
    assert study["primary_estimator"]["common_event_handling"][
        "outcome_duplication"
    ] is False
    assert "actual_session_distance" in study["inference"]["hac_session_axis"]
    assert study["inference"]["pre_outcome_power_plan_sha256"] is None
    assert "stock_event_returns_by_rating_action" in study[
        "reporting_classification"
    ]["secondary_registry_required_fields"]
    assert "event_time_cumulative_abnormal_return_by_rating_action" in study[
        "reporting_classification"
    ]["secondary_registry_required_fields"]
    assert study["economic_gate"]["primary_cost_gate"] == (
        "fixed_10_bps_per_side_only"
    )
    assert study["economic_gate"]["liquidity_impact"]["role"] == (
        "capacity_bound_diagnostic_not_promotion_gate"
    )
    assert paper["pre_observation_power_plan_sha256"] is None
    assert paper["alpha_spend_timing"] == (
        "only_atomic_final_unseal_never_at_deployment"
    )
    assert paper["replacement_policy"].startswith("no_replacement")
    assert "zero_accepted_observations" in paper["pre_observation_cancellation"]
    assert any(
        "zero_accepted_observations" in transition
        for transition in paper["look_state_machine"]["allowed_transitions"]
    )
    assert any(
        "retired_invalid_uninspected_on_monitoring" in transition
        for transition in paper["look_state_machine"]["allowed_transitions"]
    )
    assert "only_when_no_monitoring_safety_or_epoch_violation" in paper[
        "pre_observation_cancellation"
    ]
    assert paper["look_state_machine"]["terminal"] == (
        "spent_at_atomic_final_unseal",
        "retired_invalid_uninspected",
        "retired_underfilled_uninspected",
    )
    assert "provider_or_entitlement" in paper["epoch_invalidating_changes"]
    assert "gross_net_and_single_position_limit_breach_flags_without_pnl" in (
        paper["operational_monitoring_whitelist"]
    )


def test_plan_hash_covers_every_stage_and_policy_choice(tmp_path: Path) -> None:
    raw = json.loads(PLAN.read_text(encoding="utf-8"))
    raw["prospective_paper_contract"]["duration_nyse_sessions"] = 251

    with pytest.raises(QcFirstPlanError, match="content hash"):
        load_qc_first_study_plan(_write(tmp_path, raw))


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda raw: raw["supersession"].update(looks_consumed=1),
            "supersession",
        ),
        # ARV2Q-005 claims type-aware exact comparison defeats Python's
        # True == 1 equivalence. Nothing exercised it: relaxing the scalar
        # check to a plain != left the suite green.
        (
            lambda raw: raw["control_contract"].update(
                stock_control_execution_authorized=0
            ),
            "changed from the owner-frozen contract",
        ),
        # Unknown-field rejection was pinned only at the root, so a nested
        # contract could grow a field the frozen template never declared.
        (
            lambda raw: raw["control_contract"].update(
                claude_review_injected_field=True
            ),
            "changed from the owner-frozen contract",
        ),

        # The authority, schema and status strings are the plan's own
        # boundary markers. A correctly re-hashed file asserting action
        # authority must refuse; without these cases the loader could stop
        # comparing them and every test would stay green.
        (
            lambda raw: raw.update(
                authority="full_qc_action_and_deployment_authority"
            ),
            "authority changed from the owner-frozen contract",
        ),
        (
            lambda raw: raw.update(schema="arv2-qc-first-plan-v2"),
            "schema changed from the owner-frozen contract",
        ),
        (
            lambda raw: raw.update(status="reviewed_frozen"),
            "status changed from the owner-frozen contract",
        ),
        (
            lambda raw: raw["multiplicity_contract"].update(
                three_lane_correction_factor=1
            ),
            "multiplicity_contract",
        ),
        (
            lambda raw: raw["control_contract"].update(
                rank_deficiency="drop_collinear_controls"
            ),
            "control_contract",
        ),
        (
            lambda raw: raw["control_contract"][
                "stock_pretrade_signal_controls"
            ].append("event_price_jump_vector"),
            "control_contract",
        ),
        (
            lambda raw: raw["stock_event_study_contract"].update(
                development_pass_rule="positive_point_estimate_only"
            ),
            "stock_event_study_contract",
        ),
        (
            lambda raw: raw["stock_event_study_contract"]["economic_gate"].update(
                current_execution_authorized=True
            ),
            "stock_event_study_contract",
        ),
        (
            lambda raw: raw["qc_historical_contract"].update(
                engine="local_lean"
            ),
            "qc_historical_contract",
        ),
        (
            lambda raw: raw["qc_historical_contract"].update(
                upload_authorized=True
            ),
            "qc_historical_contract",
        ),
        (
            lambda raw: raw["qc_historical_contract"]["stock_stage"].update(
                pass_unlocks="paper_trading"
            ),
            "qc_historical_contract",
        ),
        (
            lambda raw: raw["prospective_paper_contract"].update(
                start="2026-09-01", end="2027-08-31"
            ),
            "prospective_paper_contract",
        ),
        (
            lambda raw: raw["prospective_paper_contract"][
                "start_preconditions"
            ].remove("ARV2-7_qc_parity_complete"),
            "prospective_paper_contract",
        ),
        (
            lambda raw: raw["prospective_paper_contract"].update(
                vehicle="small_funded_account"
            ),
            "prospective_paper_contract",
        ),
        (
            lambda raw: raw["prospective_paper_contract"][
                "look_state_machine"
            ]["allowed_transitions"].pop(1),
            "prospective_paper_contract",
        ),
        (
            lambda raw: raw["funded_pilot_contract"].update(
                live_deployment_authorized=True
            ),
            "funded_pilot_contract",
        ),
        (
            lambda raw: raw["funded_pilot_contract"].update(
                live_deployment_authorized=1
            ),
            "funded_pilot_contract",
        ),
    ],
)
def test_correctly_rehashed_dangerous_plan_changes_refuse(
    tmp_path: Path, mutate, match: str
) -> None:
    raw = copy.deepcopy(json.loads(PLAN.read_text(encoding="utf-8")))
    mutate(raw)
    _rehash(raw)

    with pytest.raises(QcFirstPlanError, match=match):
        load_qc_first_study_plan(_write(tmp_path, raw))


def test_declared_plan_identity_must_be_content_derived(tmp_path: Path) -> None:
    """plan_id is nulled out of the hashed payload before hashing.

    Only the explicit derivation check ties the declared identity back to the
    content, so a file can otherwise carry a correct plan_hash beside a
    plan_id naming a different plan. Deleting that check left the suite green.
    """
    raw = json.loads(PLAN.read_text(encoding="utf-8"))
    _rehash(raw)
    raw["plan_id"] = "arv2-qc-first-plan-0000000000000000"
    with pytest.raises(QcFirstPlanError, match="plan_id is not content-derived"):
        load_qc_first_study_plan(_write(tmp_path, raw))


def test_duplicate_json_keys_refuse(tmp_path: Path) -> None:
    """object_pairs_hook is the only defence against a duplicated key.

    Python keeps the last occurrence silently, so a duplicated authority or
    capability key would authenticate while a reader saw the first value.
    Removing the hook left the suite green.
    """
    text = PLAN.read_text(encoding="utf-8")
    index = text.index('"authority"')
    duplicated = text[:index] + '"authority": "planning_only", ' + text[index:]
    path = tmp_path / "duplicate.json"
    path.write_text(duplicated, encoding="utf-8")
    legacy = PLAN.with_name("arv2_round0.draft.json")
    (tmp_path / legacy.name).write_bytes(legacy.read_bytes())
    with pytest.raises(QcFirstPlanError, match="duplicate JSON key"):
        load_qc_first_study_plan(path)


def test_unknown_root_field_and_binary_float_refuse(tmp_path: Path) -> None:
    unknown = json.loads(PLAN.read_text(encoding="utf-8"))
    unknown["launch"] = True
    _rehash(unknown)
    with pytest.raises(QcFirstPlanError, match="root fields"):
        load_qc_first_study_plan(_write(tmp_path, unknown))

    floating = PLAN.read_text(encoding="utf-8").replace(
        '"duration_nyse_sessions": 252',
        '"duration_nyse_sessions": 252.0',
    )
    path = tmp_path / "float.json"
    path.write_text(floating, encoding="utf-8")
    with pytest.raises(QcFirstPlanError, match="floating-point"):
        load_qc_first_study_plan(path)

    # json.loads routes bare NaN/Infinity through parse_constant, not
    # parse_float, so these tokens bypassed the no-binary-float contract.
    for token in ("NaN", "Infinity", "-Infinity"):
        nonfinite = PLAN.read_text(encoding="utf-8").replace(
            '"duration_nyse_sessions": 252',
            f'"duration_nyse_sessions": {token}',
        )
        nonfinite_path = tmp_path / f"nonfinite_{token.strip('-')}.json"
        nonfinite_path.write_text(nonfinite, encoding="utf-8")
        with pytest.raises(QcFirstPlanError, match="floating-point"):
            load_qc_first_study_plan(nonfinite_path)
