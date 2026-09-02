from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from typing import Callable

import pytest

import research.target_price_revisions.preregistration as preregistration
from research.target_price_revisions import FAMILY_ID, PRIMARY_CELL_ID, PRIMARY_LOOK_ID
from research.target_price_revisions.canonical import (
    CanonicalContractError,
    require_aware_instant,
    require_decimal_text,
)
from research.target_price_revisions.preregistration import (
    AlgorithmCandidate,
    OutcomeAccessPermit,
    OutcomeAccessRequest,
    PreregistrationError,
    ReviewedAlgorithmSpec,
    assert_outcome_access_permit,
    authorize_outcome_access,
    build_algorithm_candidate_bytes,
    load_algorithm_candidate,
    load_reviewed_algorithm_spec,
    require_reviewed_algorithm_spec,
    require_zero_access_permanent_look_authority,
    require_zero_access_source_authority,
)


ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = ROOT / "research" / "target_price_revisions" / "specs"
CANDIDATE = SPEC_DIR / "tpr_round0a.candidate.json"
HASH_A = "a" * 64
HASH_B = "b" * 64
EXPECTED_SPEC_ID = "tpr-round0a-candidate-74b096af24c8d481"
EXPECTED_SPEC_HASH = (
    "74b096af24c8d48196054f56deb562924380884c1b14b747ba432cc57658df2c"
)
EXPECTED_ARTIFACT_SHA256 = (
    "17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a"
)


def _canonical(value: object, *, trailing_lf: bool = True) -> bytes:
    rendered = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return (rendered + ("\n" if trailing_lf else "")).encode("utf-8")


def _raw_candidate() -> dict[str, object]:
    return json.loads(CANDIDATE.read_text(encoding="utf-8"))


def _cell(raw: dict[str, object], cell_id: str) -> dict[str, object]:
    return next(cell for cell in raw["cells"] if cell["cell_id"] == cell_id)


def _rehash(raw: dict[str, object]) -> None:
    raw["spec_id"] = None
    raw["spec_hash"] = None
    digest = hashlib.sha256(_canonical(raw, trailing_lf=False)).hexdigest()
    raw["spec_hash"] = digest
    prefix = (
        "tpr-round0a-candidate-"
        if raw["status"] == preregistration.CANDIDATE_STATUS
        else "tpr-round0a-"
    )
    raw["spec_id"] = prefix + digest[:16]


def _write(tmp_path: Path, raw: dict[str, object], name: str = "spec.json") -> Path:
    path = tmp_path / name
    path.write_bytes(_canonical(raw))
    return path


def _cells_with_confirmatory_alpha(alpha: str) -> tuple[object, ...]:
    """Build a semantic-validation fixture without changing the frozen candidate."""
    raw = _raw_candidate()
    _cell(raw, "family_multiplicity")["value"][
        "confirmatory_alpha_allocations"
    ][0]["two_sided_alpha"] = alpha
    _cell(raw, "empirical_binding_contract")["value"]["assigned_alpha"] = alpha
    _cell(raw, "trial_and_null_contract")["value"][
        "primary_acceptance_contract"
    ]["two_sided_alpha"] = alpha
    return tuple(
        preregistration.PreregistrationCell(
            cell_id=cell["cell_id"],
            state=cell["state"],
            value=preregistration.deep_freeze(cell["value"]),
            source=cell["source"],
        )
        for cell in raw["cells"]
    )


def _request() -> OutcomeAccessRequest:
    return OutcomeAccessRequest(
        family_id=FAMILY_ID,
        look_id=PRIMARY_LOOK_ID,
        algorithm_spec_id="tpr-round0a-reviewed-placeholder",
        algorithm_spec_hash=HASH_A,
        structural_binding_id="tpr-structural-bindings-placeholder",
        structural_binding_sha256=HASH_B,
        dataset_id="tpr-dataset-placeholder",
        code_identity=HASH_A,
        requested_start="2026-09-01",
        requested_end="2027-08-31",
        horizon_exchange_sessions=20,
        assigned_alpha="0.0125",
    )


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    return completed.stdout.strip()


def _anchored_reviewed_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    repository = tmp_path / "review-repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    candidate_relative = Path(preregistration.CANDIDATE_REPO_PATH)
    candidate_path = repository / candidate_relative
    candidate_path.parent.mkdir(parents=True)
    candidate_payload = CANDIDATE.read_bytes()
    candidate_path.write_bytes(candidate_payload)
    for policy_relative_text in preregistration.POLICY_CODE_REPO_PATHS:
        policy_relative = Path(policy_relative_text)
        policy_path = repository / policy_relative
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_bytes((ROOT / policy_relative).read_bytes())
    _git(
        repository,
        "add",
        candidate_relative.as_posix(),
        *preregistration.POLICY_CODE_REPO_PATHS,
    )
    _git(
        repository,
        "-c",
        "user.name=TPR Producer",
        "-c",
        "user.email=producer@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "producing snapshot",
    )
    producing_commit = _git(repository, "rev-parse", "HEAD")

    raw = _raw_candidate()
    raw.update(
        status=preregistration.REVIEWED_ALGORITHM_STATUS,
        producing_commit=producing_commit,
        reviewed_by="independent-reviewer",
        reviewed_at="2026-08-30T02:00:00Z",
    )
    _rehash(raw)
    spec_relative = Path("research/target_price_revisions/specs/tpr_round0a.json")
    spec_path = repository / spec_relative
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_payload = _canonical(raw)
    spec_path.write_bytes(spec_payload)
    _git(repository, "add", spec_relative.as_posix())
    _git(
        repository,
        "-c",
        "user.name=Independent Reviewer",
        "-c",
        "user.email=reviewer@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "independent review",
    )
    review_commit = _git(repository, "rev-parse", "HEAD")

    registry_relative = Path(
        "research/target_price_revisions/specs/reviewed_spec_registry.json"
    )
    registry_path = repository / registry_relative
    registry = {
        "schema": preregistration.REVIEW_REGISTRY_SCHEMA,
        "entries": [
            {
                "spec_id": raw["spec_id"],
                "spec_hash": raw["spec_hash"],
                "artifact_sha256": hashlib.sha256(spec_payload).hexdigest(),
                "spec_path": spec_relative.as_posix(),
                "candidate_path": candidate_relative.as_posix(),
                "candidate_spec_id": _raw_candidate()["spec_id"],
                "candidate_spec_hash": _raw_candidate()["spec_hash"],
                "candidate_artifact_sha256": hashlib.sha256(
                    candidate_payload
                ).hexdigest(),
                "policy_code_sha256": {
                    policy_path: hashlib.sha256(
                        (ROOT / policy_path).read_bytes()
                    ).hexdigest()
                    for policy_path in preregistration.POLICY_CODE_REPO_PATHS
                },
                "review_commit": review_commit,
                "reviewed_by": raw["reviewed_by"],
                "reviewed_at": raw["reviewed_at"],
            }
        ],
    }
    registry_path.write_bytes(_canonical(registry))
    _git(repository, "add", registry_relative.as_posix())
    _git(
        repository,
        "-c",
        "user.name=TPR Counter Reviewer",
        "-c",
        "user.email=counter-reviewer@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "anchor reviewed algorithm",
    )
    monkeypatch.setattr(
        preregistration, "REVIEWED_SPEC_REGISTRY_PATH", registry_path
    )
    return spec_path


def test_repository_candidate_freezes_the_approved_tpr0a_contract() -> None:
    payload = CANDIDATE.read_bytes()
    raw = _raw_candidate()
    candidate = load_algorithm_candidate(CANDIDATE)

    assert payload == _canonical(raw)
    assert payload == build_algorithm_candidate_bytes()
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    assert b"\r" not in payload
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_ARTIFACT_SHA256
    assert candidate.spec_hash == raw["spec_hash"] == EXPECTED_SPEC_HASH
    assert candidate.spec_id == raw["spec_id"] == EXPECTED_SPEC_ID
    assert len(candidate.cells) == 24
    assert len(candidate.looks) == 1
    binding = candidate.cell("empirical_binding_contract")
    empirical_keys = tuple(binding["required_bindings"])
    assert len(empirical_keys) == 39
    assert len(candidate.pending_bindings) == 48
    assert candidate.pending_bindings[:4] == (
        "independent_review_anchor",
        "tpr_structural_bindings_v1_child",
        "reviewed_TPR1_source_snapshot_and_rights",
        "reviewed_TPR2_identity_basis_controls_and_cost_inputs",
    )
    assert set(candidate.pending_bindings[4:43]) == {
        f"empirical.{key}" for key in empirical_keys
    }
    assert candidate.pending_bindings[43:] == (
        f"looks.{PRIMARY_LOOK_ID}.dataset_id",
        f"looks.{PRIMARY_LOOK_ID}.code_identity",
        f"looks.{PRIMARY_LOOK_ID}.structural_binding_id",
        f"looks.{PRIMARY_LOOK_ID}.structural_binding_sha256",
        "external_append_only_permanent_look_authority",
    )
    assert candidate.unresolved_owner_decisions == ()
    assert candidate.looks[0].state == "planned_unbound"
    assert candidate.looks[0].dataset_id is None
    assert candidate.looks[0].structural_binding_id is None

    governance = candidate.cell("governance_contract")
    assert governance["blueprint_sha256"] == (
        "f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b"
    )
    assert governance["blueprint_version"] == "2.2"
    assert governance["blueprint_role"] == (
        "sole_governing_target_price_strategy_authority"
    )
    family = candidate.cell("family_multiplicity")
    assert family["fixed_lane_ids"] == (
        "analyst-revisions-v2",
        "insider-buying",
        "short-interest",
        "target-price-revisions",
    )
    assert family["assigned_lane_id"] == "target-price-revisions"
    assert family["shared_family_count"] == 4
    assert family["assigned_family_alpha"] == "0.0125"
    assert family["within_lane_confirmatory_alpha_ceiling"] == "0.0125"
    assert family["slot_reallocation"] == {
        "transferable": False,
        "unused": "EXPIRES",
        "withdrawn": "EXPIRES",
        "redistribution": "PROHIBITED",
    }
    assert family["confirmatory_alpha_allocations"] == (
        {
            "look_id": PRIMARY_LOOK_ID,
            "primary_cell_id": PRIMARY_CELL_ID,
            "two_sided_alpha": "0.0125",
        },
    )
    assert family["permanent_look_ids"] == (PRIMARY_LOOK_ID,)
    holdout = candidate.cell("shared_holdout")
    assert holdout["validation_start"] == "2026-09-01"
    assert holdout["validation_end"] == holdout["cutoff_session"] == "2027-08-31"
    assert holdout["reserved_start"] == "2027-09-01"
    assert holdout["reserved_end"] == "2029-08-31"
    assert holdout["lane_access_prohibited"] is True

    source = candidate.cell("source_contract")
    assert source["provider"] == "Massive/Benzinga Analyst Ratings"
    assert source["http_method"] == "GET"
    assert source["endpoint"] == "/benzinga/v1/ratings"
    assert source["schema_version"] == "v1"
    assert source["provider_reader_implemented"] is False
    assert source["documentation_urls"] == (
        "https://massive.com/docs/rest/partners/benzinga/analyst-ratings",
        "https://www.benzinga.com/apis/cloud-product/analyst-ratings-api/",
    )
    retrieval = source["retrieval_contract"]
    assert retrieval["scope"] == "all_history_unfiltered_through_frozen_high_water"
    assert retrieval["first_request_limit"] == 50000
    assert retrieval["first_request_sort"] == "last_updated_ascending"
    assert retrieval["provider_earliest_history_claim"] == "2011-12-08"
    assert retrieval["earliest_history_claim_disposition"].startswith(
        "audit_claim_only"
    )
    assert retrieval["cursor_cycle_duplicate_or_page_replay"] == "REFUSED"
    schema = source["schema_handling_contract"]
    assert "exact_finite_Decimal" in schema["numeric_token_parser"]
    assert schema["unknown_field_policy"].startswith("REFUSED")
    secrets = source["secret_handling_contract"]
    assert "derived_secret_hashes" in secrets[
        "excluded_from_persisted_request_metadata_and_hashes"
    ]
    assert secrets["raw_response_secret_scan_required_before_persistence"] is True
    assert secrets["unclassified_secret_bearing_metadata"] == "REFUSED"
    source_authority = candidate.cell("source_authority")
    assert source_authority["authority_mode"] == "zero_access"
    assert not any(
        value
        for key, value in source_authority.items()
        if key != "authority_mode" and type(value) is bool
    )
    assert {
        value
        for key, value in source_authority.items()
        if key.endswith("_state")
    } == {"UNESTABLISHED"}

    cutoff = candidate.cell("cutoff_contract")
    assert cutoff["prior_session_local_time"] == "18:00:00"
    assert cutoff["timezone"] == "America/New_York"
    clock = candidate.cell("clock_contract")
    assert clock["same_day_premarket_canonical"] is False
    assert "second_exchange_open" in clock["date_only_rule"]
    formula = candidate.cell("primary_event_formula")
    assert formula["primary_cell_id"] == PRIMARY_CELL_ID
    assert formula["event_clip_absolute"] is None
    decay = candidate.cell("decay_contract")
    assert decay["half_life_exchange_sessions"] == 20
    assert decay["truncate_after_exchange_sessions"] == 80
    assert decay["age_above_80"] == "expired_zero_weight_preserve_event_disposition"
    assert decay["expiry_changes_raw_event_disposition"] is False

    basis = candidate.cell("basis_contract")
    assert "immediately_preceding_completed_exchange_session" in basis[
        "pre_event_price_policy"
    ]
    assert "event_calendar_date" in basis["pre_event_price_policy"]
    assert "select_exactly_one_unmixed_pair" in basis["target_pair_selection"]
    identity = candidate.cell("independence_contract")["stable_institution_identity"]
    assert "benzinga_firm_id" in identity["canonical_key"]
    assert identity["current_name_join"] == "PROHIBITED"
    assert identity["missing_or_ambiguous_alias_lineage"] == "REFUSED"
    assert identity["provider_id_collision_or_concurrent_many_to_one"] == "REFUSED"

    controls = candidate.cell("controls_contract")
    assert controls["categorical_controls"][0] == "hierarchical_normalization_group"
    assert controls["simultaneous_nested_industry_sector_dummies"] is False
    assert controls["classification_control_count"] == 1
    assert controls["rating_no_event_state"] == "NO_ACCEPTED_RATING_EVENT"
    assert controls["rating_no_event_is_generic_missing"] is False
    assert controls["eligible_open_gap_is_a_pre_rank_control"] is False
    assert controls["continuous_scaling"].startswith(
        "separately_for_each_decision_session"
    )
    assert controls["continuous_zero_or_nonfinite_mad"] == "decision_session_REFUSED"
    assert "without_annualization" in controls["as_of_endpoints"][
        "realized_volatility_20_sessions"
    ]

    walk_forward = candidate.cell("walk_forward_contract")
    assert walk_forward["development_start"] is None
    assert "complete_admitted_point_in_time_coverage" in (
        walk_forward["development_start_binding_algorithm"]
    )
    assert all(value is None for value in binding["required_bindings"].values())
    assert binding["required_bindings"]["reliability_thresholds"] is None
    assert "type7_q0.005_signed" in binding["event_clip_algorithm"]["formula"]
    assert "cost_p95" in binding["power_and_effect_algorithm"]
    assert binding["power_and_effect_algorithm"]["design_effect"].startswith(
        "max(1,overlap_factor,block_factor)*max(1,security_factor)"
    )
    assert "normal_quantile_0.99375" in (
        binding["power_and_effect_algorithm"]["planning_mde"]
    )
    assert binding["reliability_binding_algorithm"]["primary_rank_effect"] is False
    assert binding["required_bindings"]["institution_identity_alias_audit"] is None
    assert binding["required_bindings"]["institution_master_id"] is None
    assert binding["required_bindings"]["institution_master_sha256"] is None
    null = candidate.cell("trial_and_null_contract")
    assert null["valid_null_closes_family"] is True
    assert null["secondary_or_etf_rescue"] is False
    acceptance = null["primary_acceptance_contract"]
    assert acceptance["two_sided_alpha"] == "0.0125"
    assert acceptance["positive_direction_required"] is True
    assert acceptance["primary_bootstrap"]["block_length_weeks"] == 4
    assert acceptance["primary_bootstrap"]["resamples"] == 10000
    assert acceptance["primary_bootstrap"]["p_value"] == (
        "(1+count(abs(replicate_t)>=abs(observed_t)))/(10000+1)"
    )
    assert "first_16_raw_digest_bytes" in acceptance["primary_bootstrap"][
        "block_start_draw"
    ]
    assert "98.75_percent_studentized" in acceptance["primary_bootstrap"][
        "confidence_interval"
    ]
    assert acceptance["two_way_cluster_cross_check"]["clusters"] == (
        "decision_session",
        "permanent_security_id",
    )
    assert acceptance["two_way_cluster_cross_check"]["p_value"] == (
        "2*(1-Student_t_CDF(abs(m/sqrt(V)),degrees_of_freedom))"
    )
    assert "g_di=(z_di-m/n_d)/D" in acceptance["two_way_cluster_cross_check"][
        "row_influence"
    ]
    assert acceptance["chronological_fold_stability"]["rule_binding"].startswith(
        "exact_independently_reviewed"
    )
    assert acceptance["disposition_precedence"][-1].startswith("VALID_NULL")


def test_repository_authority_declarations_are_exactly_zero_access() -> None:
    assert require_zero_access_source_authority() == (
        preregistration.ZERO_ACCESS_SOURCE_AUTHORITY_ID
    )
    assert require_zero_access_permanent_look_authority() == (
        preregistration.ZERO_ACCESS_LOOK_AUTHORITY_ID
    )
    with pytest.raises(PreregistrationError, match="independently reviewed"):
        load_reviewed_algorithm_spec(CANDIDATE)
    with pytest.raises(PreregistrationError, match="zero outcome access"):
        authorize_outcome_access(load_algorithm_candidate(CANDIDATE), _request())


def test_candidate_json_is_protected_from_checkout_translation() -> None:
    relative = CANDIDATE.relative_to(ROOT).as_posix()
    completed = subprocess.run(
        ["git", "check-attr", "text", "--", relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.rstrip().endswith(": text: unset")


@pytest.mark.parametrize(
    "variant",
    [
        "duplicate_key",
        "nan",
        "infinity",
        "binary_float",
        "pretty",
        "bom",
        "missing_lf",
        "crlf",
    ],
)
def test_noncanonical_or_ambiguous_json_refuses(tmp_path: Path, variant: str) -> None:
    payload = CANDIDATE.read_bytes()
    raw = _raw_candidate()
    if variant == "duplicate_key":
        bad = b'{"cells":[],' + payload[1:]
    elif variant == "nan":
        bad = payload.replace(b'"look_budget":1', b'"look_budget":NaN', 1)
    elif variant == "infinity":
        bad = payload.replace(b'"look_budget":1', b'"look_budget":Infinity', 1)
    elif variant == "binary_float":
        bad = payload.replace(b'"shared_family_count":4', b'"shared_family_count":4.0', 1)
    elif variant == "pretty":
        bad = (json.dumps(raw, indent=2) + "\n").encode("utf-8")
    elif variant == "bom":
        bad = b"\xef\xbb\xbf" + payload
    elif variant == "missing_lf":
        bad = payload[:-1]
    elif variant == "crlf":
        bad = payload[:-1] + b"\r\n"
    else:  # pragma: no cover - exhaustive parameter list
        raise AssertionError(variant)
    path = tmp_path / "ambiguous.json"
    path.write_bytes(bad)

    with pytest.raises(PreregistrationError):
        load_algorithm_candidate(path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: _cell(raw, "governance_contract")["value"].update(
            blueprint_sha256=HASH_A
        ),
        lambda raw: _cell(raw, "governance_contract").update(source="self declared"),
        lambda raw: _cell(raw, "family_multiplicity")["value"].update(
            shared_family_count=3, assigned_family_alpha="0.0166666667"
        ),
        lambda raw: _cell(raw, "family_multiplicity")["value"].update(
            fixed_lane_ids=[
                "analyst-revisions-v2",
                "insider-buying",
                "short-interest",
            ]
        ),
        lambda raw: _cell(raw, "family_multiplicity")["value"].update(
            fixed_lane_ids=[
                "analyst-revisions-v2",
                "insider-buying",
                "short-interest",
                "short-interest",
            ]
        ),
        lambda raw: _cell(raw, "family_multiplicity")["value"].update(
            assigned_lane_id="insider-buying"
        ),
        lambda raw: _cell(raw, "family_multiplicity")["value"][
            "slot_reallocation"
        ].update(transferable=True),
        lambda raw: _cell(raw, "family_multiplicity")["value"][
            "slot_reallocation"
        ].update(unused="REDISTRIBUTE"),
        lambda raw: _cell(raw, "family_multiplicity")["value"][
            "confirmatory_alpha_allocations"
        ][0].update(two_sided_alpha="0.0126"),
        lambda raw: _cell(raw, "family_multiplicity")["value"][
            "confirmatory_alpha_allocations"
        ].append(
            {
                "look_id": "tpr-look-stock-primary-002",
                "primary_cell_id": "tpr-stock-primary-20d-second-look",
                "two_sided_alpha": "0.0125",
            }
        ),
        lambda raw: _cell(raw, "family_multiplicity")["value"][
            "confirmatory_alpha_allocations"
        ][0].update(look_id="tpr-look-stock-primary-substituted"),
        lambda raw: _cell(raw, "family_multiplicity")["value"][
            "confirmatory_alpha_allocations"
        ][0].update(two_sided_alpha="1.25e-2"),
        lambda raw: _cell(raw, "shared_holdout")["value"].update(
            reserved_start="2027-08-31"
        ),
        lambda raw: _cell(raw, "clock_contract")["value"].update(
            same_day_premarket_canonical=True
        ),
        lambda raw: _cell(raw, "clock_contract")["value"].update(
            date_only_rule="first_open_after_event_date"
        ),
        lambda raw: _cell(raw, "correction_contract")["value"].update(
            final_state_backfill_prohibited=False
        ),
        lambda raw: _cell(raw, "correction_contract")["value"].update(
            missing_from_later_snapshot_is_withdrawal=True
        ),
        lambda raw: _cell(raw, "basis_contract")["value"].update(
            split_double_adjustment="ALLOWED"
        ),
        lambda raw: _cell(raw, "basis_contract")["value"].update(
            missing_stale_or_ambiguous_fx="DROP"
        ),
        lambda raw: _cell(raw, "independence_contract")["value"].update(
            unknown_catalyst_policy="each_row_is_independent"
        ),
        lambda raw: _cell(raw, "normalization_contract")["value"].update(
            epsilon_denominator=True
        ),
        lambda raw: _cell(raw, "controls_contract")["value"].update(
            continuous_controls=[]
        ),
        lambda raw: _cell(raw, "decision_outcome_contract")["value"].update(
            outcome_horizon_exchange_sessions=5
        ),
        lambda raw: _cell(raw, "empirical_binding_contract")["value"].update(
            assigned_alpha="0.05"
        ),
        lambda raw: _cell(raw, "trial_and_null_contract")["value"].update(
            secondary_or_etf_rescue=True
        ),
        lambda raw: _cell(raw, "source_contract")["value"].update(
            provider_reader_implemented=True
        ),
        lambda raw: _cell(raw, "source_contract")["value"][
            "retrieval_contract"
        ].update(scope="caller_filtered_history"),
        lambda raw: _cell(raw, "basis_contract")["value"].update(
            target_pair_selection="mix_provider_raw_and_adjusted"
        ),
        lambda raw: _cell(raw, "decay_contract")["value"].update(
            age_above_80="VALID_ZERO"
        ),
        lambda raw: _cell(raw, "controls_contract")["value"].update(
            simultaneous_nested_industry_sector_dummies=True
        ),
        lambda raw: _cell(raw, "controls_contract")["value"].update(
            rating_no_event_is_generic_missing=True
        ),
        lambda raw: _cell(raw, "empirical_binding_contract")["value"][
            "required_bindings"
        ].update(event_clip_resolution_and_stability_rule="guessed"),
        lambda raw: _cell(raw, "trial_and_null_contract")["value"][
            "primary_acceptance_contract"
        ].update(two_sided_alpha="0.05"),
        lambda raw: _cell(raw, "trial_and_null_contract")["value"][
            "primary_acceptance_contract"
        ]["primary_bootstrap"].update(resamples=9999),
        lambda raw: _cell(raw, "source_authority")["value"].update(
            credential_access_authorized=True
        ),
        lambda raw: _cell(raw, "legacy_separation_contract")["value"].update(
            cross_strategy_imports="ALLOWED"
        ),
        lambda raw: raw["looks"][0].update(state="registered_unspent"),
        lambda raw: raw["looks"][0].update(dataset_id="caller-controlled"),
        lambda raw: raw["looks"].append(dict(raw["looks"][0])),
    ],
)
def test_rehashed_policy_weakenings_still_refuse(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None]
) -> None:
    raw = _raw_candidate()
    mutate(raw)
    _rehash(raw)

    with pytest.raises(PreregistrationError):
        load_algorithm_candidate(_write(tmp_path, raw))


def test_candidate_values_are_detached_and_recursively_immutable() -> None:
    candidate = load_algorithm_candidate(CANDIDATE)
    family = candidate.cell("family_multiplicity")
    controls = candidate.cell("controls_contract")

    with pytest.raises(TypeError):
        family["shared_family_count"] = 3
    with pytest.raises(TypeError):
        family["permanent_look_ids"][0] = "replacement"
    with pytest.raises(TypeError):
        controls["continuous_controls"] += ("future_return",)


def test_alpha_accounting_allows_underallocation_but_refuses_overspend() -> None:
    """The permanent 1/80 slot is a ceiling, not an entitlement to spend it."""
    preregistration._validate_dates_and_alpha(
        _cells_with_confirmatory_alpha("0.00625")
    )

    with pytest.raises(PreregistrationError):
        preregistration._validate_dates_and_alpha(
            _cells_with_confirmatory_alpha("0.0126")
        )


def test_git_anchored_reviewed_parent_still_cannot_reach_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _anchored_reviewed_spec(tmp_path, monkeypatch)
    reviewed = load_reviewed_algorithm_spec(spec_path)

    assert require_reviewed_algorithm_spec(reviewed) is reviewed
    with pytest.raises(PreregistrationError, match="no reviewed structural child"):
        authorize_outcome_access(reviewed, _request())


def test_reviewed_authority_cannot_be_forged_cloned_or_mutated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _anchored_reviewed_spec(tmp_path, monkeypatch)
    reviewed = load_reviewed_algorithm_spec(spec_path)

    forged = object.__new__(ReviewedAlgorithmSpec)
    with pytest.raises(PreregistrationError, match="loader-authenticated"):
        require_reviewed_algorithm_spec(forged)

    clone = object.__new__(ReviewedAlgorithmSpec)
    for field in fields(reviewed):
        object.__setattr__(clone, field.name, getattr(reviewed, field.name))
    with pytest.raises(PreregistrationError, match="forged or unregistered"):
        require_reviewed_algorithm_spec(clone)

    object.__setattr__(reviewed, "looks", ())
    with pytest.raises(PreregistrationError, match="changed after verification"):
        require_reviewed_algorithm_spec(reviewed)

    permit = object.__new__(OutcomeAccessPermit)
    with pytest.raises(PreregistrationError, match="unavailable"):
        assert_outcome_access_permit(permit)


def test_self_declared_review_and_registry_substitution_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _raw_candidate()
    raw.update(
        status=preregistration.REVIEWED_ALGORITHM_STATUS,
        producing_commit="d" * 40,
        reviewed_by="self-declared-reviewer",
        reviewed_at="2026-08-30T02:00:00Z",
    )
    _rehash(raw)
    with pytest.raises(PreregistrationError, match="Git repository"):
        load_reviewed_algorithm_spec(_write(tmp_path, raw, "self-reviewed.json"))

    spec_path = _anchored_reviewed_spec(tmp_path, monkeypatch)
    reviewed = load_reviewed_algorithm_spec(spec_path)
    registry = preregistration.REVIEWED_SPEC_REGISTRY_PATH
    registry.write_bytes(
        _canonical(
            {"schema": preregistration.REVIEW_REGISTRY_SCHEMA, "entries": []}
        )
    )
    with pytest.raises(PreregistrationError):
        require_reviewed_algorithm_spec(reviewed)


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-30T02:00:00+00:00",
        "2026-08-30T02:00:00+0000",
        "2026-08-30 02:00:00Z",
        "2026-08-30T02:00:00.000000Z",
        "2026-08-30T02:00:00z",
        "2026-08-29T19:00:00-07:00",
    ],
)
def test_review_instants_have_one_exact_utc_spelling(value: str) -> None:
    assert require_aware_instant("2026-08-30T02:00:00Z", "reviewed_at") == (
        "2026-08-30T02:00:00Z"
    )
    with pytest.raises(CanonicalContractError, match="exact UTC"):
        require_aware_instant(value, "reviewed_at")


@pytest.mark.parametrize("value", ["0", "1.25", "-1.25", "1000"])
def test_decimal_text_accepts_one_plain_canonical_spelling(value: str) -> None:
    assert require_decimal_text(value, "decimal") == Decimal(value)


@pytest.mark.parametrize(
    "value",
    ["-0", "+1", "0.0", "1.2300", "1E+3", "1e3", "01", "NaN", "Infinity"],
)
def test_decimal_text_rejects_alternate_or_nonfinite_spellings(value: str) -> None:
    with pytest.raises(CanonicalContractError):
        require_decimal_text(value, "decimal")


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("candidate_path", "research/target_price_revisions/specs/other.json"),
        ("candidate_spec_id", "tpr-round0a-candidate-substituted"),
        ("candidate_spec_hash", HASH_A),
        ("candidate_artifact_sha256", HASH_B),
    ],
)
def test_review_registry_must_bind_the_exact_producing_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: str,
) -> None:
    spec_path = _anchored_reviewed_spec(tmp_path, monkeypatch)
    repository = spec_path.parents[3]
    registry_path = preregistration.REVIEWED_SPEC_REGISTRY_PATH
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["entries"][0][field] = replacement
    registry_path.write_bytes(_canonical(registry))
    relative = registry_path.relative_to(repository).as_posix()
    _git(repository, "add", relative)
    _git(
        repository,
        "-c",
        "user.name=Registry Mutator",
        "-c",
        "user.email=mutator@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "mutate candidate anchor",
    )

    with pytest.raises(PreregistrationError):
        load_reviewed_algorithm_spec(spec_path)


def test_review_registry_policy_code_map_cannot_be_substituted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _anchored_reviewed_spec(tmp_path, monkeypatch)
    repository = spec_path.parents[3]
    registry_path = preregistration.REVIEWED_SPEC_REGISTRY_PATH
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["entries"][0]["policy_code_sha256"][
        "research/target_price_revisions/canonical.py"
    ] = HASH_A
    registry_path.write_bytes(_canonical(registry))
    relative = registry_path.relative_to(repository).as_posix()
    _git(repository, "add", relative)
    _git(
        repository,
        "-c",
        "user.name=Registry Mutator",
        "-c",
        "user.email=mutator@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "substitute reviewed policy map",
    )

    with pytest.raises(PreregistrationError, match="policy code"):
        load_reviewed_algorithm_spec(spec_path)


def test_policy_code_changed_after_review_cannot_retain_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _anchored_reviewed_spec(tmp_path, monkeypatch)
    repository = spec_path.parents[3]
    policy_relative = Path("research/__init__.py")
    policy_path = repository / policy_relative
    policy_path.write_bytes(policy_path.read_bytes() + b"\n# post-review change\n")
    _git(repository, "add", policy_relative.as_posix())
    _git(
        repository,
        "-c",
        "user.name=Policy Mutator",
        "-c",
        "user.email=mutator@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "change policy after review",
    )

    with pytest.raises(PreregistrationError, match="policy code differs"):
        load_reviewed_algorithm_spec(spec_path)


def test_every_registry_entry_is_typed_before_duplicate_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _anchored_reviewed_spec(tmp_path, monkeypatch)
    repository = spec_path.parents[3]
    registry_path = preregistration.REVIEWED_SPEC_REGISTRY_PATH
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    malformed = dict(registry["entries"][0])
    malformed["spec_id"] = ["unrelated-but-malformed"]
    registry["entries"].append(malformed)
    registry_path.write_bytes(_canonical(registry))
    relative = registry_path.relative_to(repository).as_posix()
    _git(repository, "add", relative)
    _git(
        repository,
        "-c",
        "user.name=Registry Mutator",
        "-c",
        "user.email=mutator@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "add malformed unmatched anchor",
    )

    with pytest.raises(PreregistrationError, match="registry spec_id"):
        load_reviewed_algorithm_spec(spec_path)


def test_zero_access_authority_rejects_a_symlinked_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real-authority"
    real.mkdir()
    authority = real / "source.json"
    authority.write_bytes(preregistration.RESEARCH_SOURCE_AUTHORITY_PATH.read_bytes())
    linked = tmp_path / "linked-authority"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"host cannot create a directory symlink: {exc}")
    monkeypatch.setattr(
        preregistration,
        "RESEARCH_SOURCE_AUTHORITY_PATH",
        linked / authority.name,
    )

    with pytest.raises(PreregistrationError, match="symlink"):
        require_zero_access_source_authority()


def test_reviewed_spec_rejects_a_symlinked_artifact_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec_path = _anchored_reviewed_spec(tmp_path, monkeypatch)
    target = spec_path.with_name("reviewed-target.json")
    target.write_bytes(spec_path.read_bytes())
    spec_path.unlink()
    try:
        spec_path.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"host cannot create a file symlink: {exc}")

    with pytest.raises(PreregistrationError, match="symlink"):
        load_reviewed_algorithm_spec(spec_path)


@pytest.mark.parametrize("authority_name", ["source", "look"])
def test_local_positive_authority_substitution_cannot_enable_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority_name: str,
) -> None:
    if authority_name == "source":
        schema = preregistration.SOURCE_AUTHORITY_SCHEMA
        path_name = "RESEARCH_SOURCE_AUTHORITY_PATH"
        loader = require_zero_access_source_authority
    else:
        schema = preregistration.PERMANENT_LOOK_AUTHORITY_SCHEMA
        path_name = "PERMANENT_LOOK_AUTHORITY_PATH"
        loader = require_zero_access_permanent_look_authority
    forged = tmp_path / f"{authority_name}-authority.json"
    forged.write_bytes(
        _canonical(
            {
                "schema": schema,
                "authority_mode": "append_only",
                "authority_id": "caller-controlled",
                "entries": [{"state": "authorized"}],
            }
        )
    )
    monkeypatch.setattr(preregistration, path_name, forged)

    with pytest.raises(PreregistrationError, match="zero-access declaration"):
        loader()


def test_candidate_type_itself_never_authenticates_as_reviewed() -> None:
    candidate = load_algorithm_candidate(CANDIDATE)
    assert type(candidate) is AlgorithmCandidate
    with pytest.raises(PreregistrationError, match="loader-authenticated"):
        require_reviewed_algorithm_spec(candidate)
