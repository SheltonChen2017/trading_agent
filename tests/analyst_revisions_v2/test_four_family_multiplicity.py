from __future__ import annotations

import copy
import dataclasses
import gc
import hashlib
import json
import pickle
import shutil
import weakref
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

import research.analyst_revisions_v2.four_family_multiplicity as module
from research.analyst_revisions_v2.four_family_multiplicity import (
    ANALYST_FAMILY_ID,
    ANALYST_LANE_ID,
    ANALYST_LOOK_ID,
    FIXED_LANE_IDS,
    ID_PREFIX,
    OVERLAY_ARTIFACT_SHA256,
    QC_PLAN_ARTIFACT_SHA256,
    SUPERSEDED_PARENT_PATHS,
    ZERO_LOOK_AUTHORITY_ARTIFACT_SHA256,
    FourFamilyMultiplicityError,
    FourFamilyMultiplicityOverlay,
    load_four_family_multiplicity_overlay,
    render_expected_four_family_multiplicity_overlay,
    require_loaded_four_family_multiplicity_overlay,
)
from research.analyst_revisions_v2.qc_first_plan import load_qc_first_study_plan


SPEC_ROOT = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "analyst_revisions_v2"
    / "specs"
)
FILENAMES = {
    "overlay": "arv2_four_family_multiplicity.structural.json",
    "plan": "arv2_qc_first.draft.json",
    "base": "arv2_round0.draft.json",
    "look_authority": "permanent_look_authority.json",
}
EXPECTED_OVERLAY_ID = "arv2-four-family-multiplicity-54ab0bb69fb6fa16"
EXPECTED_OVERLAY_HASH = (
    "54ab0bb69fb6fa162ca3ba6764864b230136c68c017f1e6b669034dda75b806e"
)
UNCHANGED_ACCEPTED_ARTIFACT_HASHES = {
    "arv2_qc_first.draft.json": QC_PLAN_ARTIFACT_SHA256,
    "arv2_round0.draft.json": (
        "b40a76f5f2f7726f328f1e444a41ecb0670234055a7c9c7245a26ffab601af2f"
    ),
    "arv2_stock_historical.structural.json": (
        "34d1e71548bc6850a02590596594944dad3fadb38954067f2cc2d00dcaa86bc8"
    ),
    "arv2_stock_walk_forward_folds.structural.json": (
        "fecd984ad937fed57b860b15fdcb9cc994ff59ab62c3b72d5160ab62b342953c"
    ),
    "arv2_global_rating_map.structural.json": (
        "630cc822fa83d7aba15920cfb8f37863f6d6fffa262e26ac96074e8526391f4e"
    ),
    "arv2_global_matched_comparison.structural.json": (
        "40b164e3e2944053eaaaaf1a651e34dfb335a4cbc8aeca2ee3f67ecdc9e8dffa"
    ),
    "arv2_stock_historical_successor.structural.json": (
        "51718ee5ae278d1254e8efb01b2acdd9c6cbe51741dd72d5b5969c3b48576647"
    ),
    "arv2_stock_power_calibration_protocol.structural.json": (
        "ff16117a258a1864438d11178a2b31af1b04a3f8b27d1f39c9c33552627f4a13"
    ),
}
EXPECTED_CAPABILITY_FIELDS = (
    "source_access",
    "outcome_access",
    "confirmatory_look_registration",
    "confirmatory_look_commitment",
    "confirmatory_look_spend",
    "qc_upload",
    "qc_compile",
    "qc_launch",
    "result_disposition",
    "paper_deployment",
    "funded_deployment",
    "orders",
)
EXPECTED_EXTERNAL_BINDING_FIELDS = (
    "independent_review_commit",
    "counter_review_commit",
    "cross_lane_review_completion_receipt",
    "external_append_only_look_authority_id",
    "external_zero_observation_receipt",
    "look_spend_receipt_id",
    "source_rights_receipt_id",
    "dataset_id",
    "outcome_artifact_sha256",
    "qc_project_id",
    "qc_run_id",
    "evaluation_receipt_id",
    "paper_epoch_id",
    "funded_live_authority_id",
)


def _paths(root: Path = SPEC_ROOT) -> dict[str, Path]:
    return {name: root / filename for name, filename in FILENAMES.items()}


def _load(root: Path = SPEC_ROOT) -> FourFamilyMultiplicityOverlay:
    paths = _paths(root)
    return load_four_family_multiplicity_overlay(
        paths["overlay"],
        look_authority_path=paths["look_authority"],
        qc_first_plan_path=paths["plan"],
    )


def _clone(tmp_path: Path) -> Path:
    root = tmp_path / "specs"
    root.mkdir(parents=True)
    for filename in FILENAMES.values():
        shutil.copyfile(SPEC_ROOT / filename, root / filename)
    return root


def _rewrite_overlay(path: Path, mutate) -> bytes:
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)
    raw["overlay_id"] = None
    raw["overlay_hash"] = None
    compact = json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(compact).hexdigest()
    raw["overlay_hash"] = digest
    raw["overlay_id"] = ID_PREFIX + digest[:16]
    payload = (
        json.dumps(
            raw,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(payload)
    return payload


@pytest.fixture
def overlay() -> FourFamilyMultiplicityOverlay:
    return _load()


def test_checked_in_overlay_has_exact_renderer_content_and_identities():
    path = _paths()["overlay"]
    payload = path.read_bytes()
    assert payload.decode("utf-8") == render_expected_four_family_multiplicity_overlay()
    assert hashlib.sha256(payload).hexdigest() == OVERLAY_ARTIFACT_SHA256

    raw = json.loads(payload)
    declared_id = raw["overlay_id"]
    declared_hash = raw["overlay_hash"]
    raw["overlay_id"] = None
    raw["overlay_hash"] = None
    digest = hashlib.sha256(
        json.dumps(
            raw,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert declared_id == EXPECTED_OVERLAY_ID == ID_PREFIX + digest[:16]
    assert declared_hash == EXPECTED_OVERLAY_HASH == digest


def test_overlay_is_additive_and_selected_accepted_structural_bytes_are_unchanged():
    for filename, expected in UNCHANGED_ACCEPTED_ARTIFACT_HASHES.items():
        assert hashlib.sha256((SPEC_ROOT / filename).read_bytes()).hexdigest() == expected

    power = json.loads(
        (SPEC_ROOT / "arv2_stock_power_calibration_protocol.structural.json").read_bytes()
    )
    assert power["owner_policy"]["two_sided_size"] == {
        "numerator": 1,
        "denominator": 20,
    }


def test_exact_four_family_contract_and_within_lane_arithmetic(overlay):
    definition = overlay.definition
    shared = definition["shared_family_contract"]
    analyst = definition["analyst_lane_contract"]

    expected_lanes = (
        "analyst-revisions-v2",
        "insider-buying",
        "short-interest",
        "target-price-revisions",
    )
    assert FIXED_LANE_IDS == expected_lanes
    assert overlay.fixed_lane_ids == expected_lanes
    assert shared["fixed_lane_count"] == 4
    assert shared["two_sided_family_wise_alpha"] == {
        "numerator": 1,
        "denominator": 20,
    }
    assert shared["permanent_maximum_per_lane"] == {
        "numerator": 1,
        "denominator": 80,
    }
    assert 4 * Fraction(1, 80) == Fraction(1, 20)
    assert overlay.shared_family_alpha == Fraction(1, 20)
    assert overlay.analyst_confirmatory_alpha_ceiling == Fraction(1, 80)
    assert overlay.analyst_prospective_look_alpha == Fraction(1, 80)

    assert analyst["assigned_lane_id"] == ANALYST_LANE_ID
    assert analyst["lane_family_id"] == ANALYST_FAMILY_ID
    assert analyst["permanent_look_ids"] == (ANALYST_LOOK_ID,)
    assert analyst["look_budget"] == 1
    assert analyst["within_lane_confirmatory_alpha_ceiling"] == {
        "numerator": 1,
        "denominator": 80,
    }
    assert analyst["allocation_sum"] == {"numerator": 1, "denominator": 80}
    allocations = analyst["confirmatory_alpha_allocations"]
    assert len(allocations) == 1
    assert allocations[0]["look_id"] == ANALYST_LOOK_ID
    assert allocations[0]["primary_cell_id"] is None
    assert allocations[0]["exact_estimand_sha256"] is None
    assert allocations[0]["two_sided_alpha"] == {
        "numerator": 1,
        "denominator": 80,
    }


def test_slots_expire_and_cannot_be_recycled_or_recomputed(overlay):
    slot = overlay.definition["shared_family_contract"]["slot_reallocation"]
    assert slot == {
        "denominator_recomputation": "PROHIBITED",
        "redistribution": "PROHIBITED",
        "transferable": False,
        "unused": "EXPIRES",
        "withdrawn": "EXPIRES",
    }


def test_parent_one_over_60_semantics_and_overlay_tombstone_are_jointly_pinned():
    plan = load_qc_first_study_plan(_paths()["plan"])
    assert plan.multiplicity_contract["three_lane_correction_factor"] == 3
    assert plan.multiplicity_contract["prospective_permanent_look_alpha"] == {
        "numerator": 1,
        "denominator": 60,
    }
    assert plan.multiplicity_contract["correction"] == (
        "bonferroni_three_lanes_for_one_prospective_lane_look"
    )
    assert "two_sided_alpha_one_over_60" in (
        plan.prospective_paper_contract["power_plan_required_fields"]
    )
    assert plan.prospective_paper_contract["alpha_commitment_timing"].startswith(
        "sole_one_over_60_"
    )
    assert "three_lane_selection_correction" in (
        plan.inheritance_contract["inherited_cell_ids"]
    )
    assert SUPERSEDED_PARENT_PATHS == (
        "multiplicity_contract.three_lane_correction_factor",
        "multiplicity_contract.prospective_permanent_look_alpha",
        "multiplicity_contract.correction",
        "prospective_paper_contract.power_plan_required_fields.two_sided_alpha_one_over_60",
        "prospective_paper_contract.alpha_commitment_timing.sole_one_over_60",
        "inheritance_contract.inherited_cell_ids.three_lane_selection_correction",
    )
    supersession = _load().definition["supersession_contract"]
    assert supersession["disposition"] == "superseded_unspent_nonrevivable"
    assert supersession["fallback_without_overlay"] == "REFUSED"
    assert supersession["revival"] == "PROHIBITED"


def test_zero_look_state_is_repository_gate_evidence_not_external_proof(overlay):
    state = overlay.definition["repository_zero_look_state"]
    assert hashlib.sha256(_paths()["look_authority"].read_bytes()).hexdigest() == (
        ZERO_LOOK_AUTHORITY_ARTIFACT_SHA256
    )
    assert state["authority_mode"] == "zero_access"
    assert state["authority_entries"] == ()
    assert state["parent_paper_start"] is None
    assert state["parent_paper_end"] is None
    assert state["parent_paper_evidence_epoch_id"] is None
    assert state["parent_paper_deployment_authorized"] is False
    assert state["evidence_scope"] == (
        "repository_gate_state_not_proof_of_unobserved_external_activity"
    )
    predecessor = overlay.definition["supersession_contract"]["predecessor_policy"]
    assert predecessor["repository_recorded_accepted_observations"] == 0
    assert predecessor["authorized_confirmatory_alpha_spent"] is False
    assert predecessor["state_provenance"].endswith(
        "without_external_zero_observation_receipt"
    )
    assert (
        overlay.definition["external_bindings"]["external_zero_observation_receipt"]
        is None
    )


def test_overlay_grants_no_action_and_keeps_later_milestones_closed(overlay):
    bindings = overlay.definition["external_bindings"]
    capabilities = overlay.definition["capabilities"]
    assert set(bindings) == set(EXPECTED_EXTERNAL_BINDING_FIELDS)
    assert set(capabilities) == set(EXPECTED_CAPABILITY_FIELDS)
    assert all(value is None for value in bindings.values())
    assert all(value is False for value in capabilities.values())
    assert overlay.grants_action_authority is False
    assert overlay.source_access_available is False
    assert overlay.outcome_access_available is False
    assert overlay.look_spend_available is False
    assert overlay.qc_action_available is False
    assert overlay.deployment_available is False
    assert overlay.orders_available is False
    gate = overlay.definition["future_composition_gate"]
    assert gate["every_outcome_bearing_successor_must_authenticate_reviewed_overlay"]
    assert gate["all_four_lane_review_completion_receipt_required"]
    assert gate["ARV2_4D_A_nonconfirmatory_planning_size_one_over_20_unchanged"]
    assert gate["ARV2_4D_B_authorized_by_this_overlay"] is False


def test_effective_policy_refuses_absence_clone_and_untyped_substitution(overlay):
    assert require_loaded_four_family_multiplicity_overlay(overlay) is overlay
    for invalid in (None, {}, copy.copy(overlay)):
        with pytest.raises(FourFamilyMultiplicityError, match="overlay"):
            require_loaded_four_family_multiplicity_overlay(invalid)


@pytest.mark.parametrize(
    "getter",
    (
        "shared_family_alpha",
        "analyst_confirmatory_alpha_ceiling",
        "analyst_prospective_look_alpha",
    ),
)
def test_each_positive_policy_getter_reauthenticates(overlay, getter):
    with pytest.raises(FourFamilyMultiplicityError):
        _ = getattr(copy.copy(overlay), getter)


@pytest.mark.parametrize(
    "case",
    (
        "three_lanes_one_over_60",
        "lane_omitted",
        "lane_reordered",
        "lane_duplicated",
        "wrong_lane_count",
        "wrong_family_alpha",
        "wrong_lane_alpha",
        "bool_rational_numerator",
        "wrong_assigned_lane",
        "transferable",
        "redistribution",
        "denominator_recomputation",
        "unused_recycled",
        "withdrawn_recycled",
        "second_full_alpha_look",
        "invented_primary_cell",
        "over_ceiling_allocation",
        "missing_allocation",
        "capability_true",
        "capability_numeric_zero",
        "external_binding",
        "revive_parent",
        "claim_parent_observation",
        "claim_parent_alpha_spent",
        "authorize_4d_b",
        "unknown_nested_field",
    ),
)
def test_rehashed_dangerous_direction_mutations_are_refused(tmp_path, monkeypatch, case):
    root = _clone(tmp_path)
    path = _paths(root)["overlay"]

    def mutate(raw):
        shared = raw["shared_family_contract"]
        analyst = raw["analyst_lane_contract"]
        slot = shared["slot_reallocation"]
        if case == "three_lanes_one_over_60":
            shared["fixed_lane_ids"] = shared["fixed_lane_ids"][:3]
            shared["fixed_lane_count"] = 3
            shared["permanent_maximum_per_lane"] = {"numerator": 1, "denominator": 60}
        elif case == "lane_omitted":
            shared["fixed_lane_ids"].pop()
        elif case == "lane_reordered":
            shared["fixed_lane_ids"][0], shared["fixed_lane_ids"][1] = (
                shared["fixed_lane_ids"][1],
                shared["fixed_lane_ids"][0],
            )
        elif case == "lane_duplicated":
            shared["fixed_lane_ids"][-1] = shared["fixed_lane_ids"][0]
        elif case == "wrong_lane_count":
            shared["fixed_lane_count"] = 3
        elif case == "wrong_family_alpha":
            shared["two_sided_family_wise_alpha"]["denominator"] = 25
        elif case == "wrong_lane_alpha":
            shared["permanent_maximum_per_lane"]["denominator"] = 60
        elif case == "bool_rational_numerator":
            shared["two_sided_family_wise_alpha"]["numerator"] = True
        elif case == "wrong_assigned_lane":
            analyst["assigned_lane_id"] = "insider-buying"
        elif case == "transferable":
            slot["transferable"] = True
        elif case == "redistribution":
            slot["redistribution"] = "ALLOWED"
        elif case == "denominator_recomputation":
            slot["denominator_recomputation"] = "ALLOWED"
        elif case == "unused_recycled":
            slot["unused"] = "REDISTRIBUTE"
        elif case == "withdrawn_recycled":
            slot["withdrawn"] = "REDISTRIBUTE"
        elif case == "second_full_alpha_look":
            analyst["confirmatory_alpha_allocations"].append(
                {
                    "allocation_level": "look",
                    "cell_binding_state": (
                        "deferred_exact_cell_and_estimand_required_before_"
                        "first_observation"
                    ),
                    "exact_estimand_sha256": None,
                    "look_id": "arv2-look-extra",
                    "primary_cell_id": None,
                    "two_sided_alpha": {"numerator": 1, "denominator": 80},
                }
            )
        elif case == "invented_primary_cell":
            analyst["confirmatory_alpha_allocations"][0]["primary_cell_id"] = "invented"
        elif case == "over_ceiling_allocation":
            analyst["confirmatory_alpha_allocations"][0]["two_sided_alpha"] = {
                "numerator": 1,
                "denominator": 60,
            }
        elif case == "missing_allocation":
            analyst["confirmatory_alpha_allocations"] = []
        elif case == "capability_true":
            raw["capabilities"]["outcome_access"] = True
        elif case == "capability_numeric_zero":
            raw["capabilities"]["outcome_access"] = 0
        elif case == "external_binding":
            raw["external_bindings"]["qc_run_id"] = "forged"
        elif case == "revive_parent":
            raw["supersession_contract"]["revival"] = "ALLOWED"
        elif case == "claim_parent_observation":
            raw["supersession_contract"]["predecessor_policy"][
                "repository_recorded_accepted_observations"
            ] = 1
        elif case == "claim_parent_alpha_spent":
            raw["supersession_contract"]["predecessor_policy"][
                "authorized_confirmatory_alpha_spent"
            ] = True
        elif case == "authorize_4d_b":
            raw["future_composition_gate"]["ARV2_4D_B_authorized_by_this_overlay"] = True
        elif case == "unknown_nested_field":
            shared["active_lane_count"] = 3
        else:  # pragma: no cover - the parameter inventory is closed above
            raise AssertionError(case)

    payload = _rewrite_overlay(path, mutate)
    monkeypatch.setattr(module, "OVERLAY_ARTIFACT_SHA256", hashlib.sha256(payload).hexdigest())
    with pytest.raises(FourFamilyMultiplicityError):
        _load(root)


def test_over_ceiling_guard_is_load_bearing_after_exact_contract_match(
    tmp_path, monkeypatch
):
    root = _clone(tmp_path)
    path = _paths(root)["overlay"]

    def mutate(raw):
        alpha = {"numerator": 1, "denominator": 60}
        raw["analyst_lane_contract"]["confirmatory_alpha_allocations"][0][
            "two_sided_alpha"
        ] = alpha
        raw["analyst_lane_contract"]["allocation_sum"] = alpha

    payload = _rewrite_overlay(path, mutate)
    expected = json.loads(payload)
    monkeypatch.setattr(
        module, "OVERLAY_ARTIFACT_SHA256", hashlib.sha256(payload).hexdigest()
    )
    monkeypatch.setattr(module, "_overlay_document", lambda: expected)
    with pytest.raises(FourFamilyMultiplicityError, match="exceeds its fixed slot"):
        _load(root)


@pytest.mark.parametrize("field", EXPECTED_CAPABILITY_FIELDS)
def test_each_action_capability_is_independently_pinned_false(
    tmp_path, monkeypatch, field
):
    root = _clone(tmp_path)
    path = _paths(root)["overlay"]
    payload = _rewrite_overlay(
        path, lambda raw: raw["capabilities"].__setitem__(field, True)
    )
    monkeypatch.setattr(
        module, "OVERLAY_ARTIFACT_SHA256", hashlib.sha256(payload).hexdigest()
    )
    with pytest.raises(FourFamilyMultiplicityError):
        _load(root)


@pytest.mark.parametrize("field", EXPECTED_EXTERNAL_BINDING_FIELDS)
def test_each_external_binding_is_independently_pinned_null(
    tmp_path, monkeypatch, field
):
    root = _clone(tmp_path)
    path = _paths(root)["overlay"]
    payload = _rewrite_overlay(
        path, lambda raw: raw["external_bindings"].__setitem__(field, "forged")
    )
    monkeypatch.setattr(
        module, "OVERLAY_ARTIFACT_SHA256", hashlib.sha256(payload).hexdigest()
    )
    with pytest.raises(FourFamilyMultiplicityError):
        _load(root)


@pytest.mark.parametrize("change", ("missing_root", "unknown_root", "wrong_id"))
def test_rehashed_root_shape_and_identity_mutations_refuse(
    tmp_path, monkeypatch, change
):
    root = _clone(tmp_path)
    path = _paths(root)["overlay"]

    if change == "missing_root":
        mutate = lambda raw: raw.pop("owner_direction")
    elif change == "unknown_root":
        mutate = lambda raw: raw.__setitem__("escape", False)
    else:
        mutate = lambda raw: None
    payload = _rewrite_overlay(path, mutate)
    if change == "wrong_id":
        raw = json.loads(payload)
        raw["overlay_id"] = "arv2-four-family-multiplicity-forged"
        payload = (
            json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        path.write_bytes(payload)
    monkeypatch.setattr(
        module, "OVERLAY_ARTIFACT_SHA256", hashlib.sha256(payload).hexdigest()
    )
    with pytest.raises(FourFamilyMultiplicityError):
        _load(root)


@pytest.mark.parametrize(
    "value",
    (
        {"numerator": True, "denominator": 20},
        {"numerator": 1, "denominator": False},
        {"numerator": 0, "denominator": 20},
        {"numerator": -1, "denominator": 20},
        {"numerator": 1, "denominator": 0},
        {"numerator": 2, "denominator": 40},
        {"numerator": 0.05, "denominator": 1},
    ),
)
def test_exact_rational_parser_rejects_bool_nonpositive_unreduced_and_float(value):
    with pytest.raises(FourFamilyMultiplicityError):
        module._fraction(value, "test alpha")


@pytest.mark.parametrize(
    "kind,message",
    (
        ("crlf", "canonical sorted"),
        ("bom", "BOM"),
        ("duplicate", "duplicate JSON key"),
        ("nan", "non-finite JSON"),
        ("float", "binary floating-point"),
        ("invalid_utf8", "strict UTF-8"),
        ("trailing_space", "canonical sorted"),
    ),
)
def test_noncanonical_or_malformed_overlay_bytes_refuse(
    tmp_path, monkeypatch, kind, message
):
    root = _clone(tmp_path)
    path = _paths(root)["overlay"]
    original = path.read_bytes()
    if kind == "crlf":
        payload = original.replace(b"\n", b"\r\n")
    elif kind == "bom":
        payload = b"\xef\xbb\xbf" + original
    elif kind == "duplicate":
        duplicate = b'  "schema": "arv2-four-family-multiplicity-overlay-structural-v1",\n'
        payload = original.replace(b"{\n", b"{\n" + duplicate, 1)
    elif kind == "nan":
        payload = original.replace(b'"fixed_lane_count": 4', b'"fixed_lane_count": NaN')
    elif kind == "float":
        payload = original.replace(b'"fixed_lane_count": 4', b'"fixed_lane_count": 4.0')
    elif kind == "invalid_utf8":
        payload = b"\xff" + original
    else:
        payload = original + b" "
    path.write_bytes(payload)
    monkeypatch.setattr(
        module, "OVERLAY_ARTIFACT_SHA256", hashlib.sha256(payload).hexdigest()
    )
    with pytest.raises(FourFamilyMultiplicityError, match=message):
        _load(root)


def test_parent_and_zero_look_authority_substitution_refuse(tmp_path):
    root = _clone(tmp_path)
    paths = _paths(root)
    paths["look_authority"].write_text(
        (
            '{"authority_id":"positive","authority_mode":"active",'
            '"entries":[],"schema":"arv2-permanent-look-authority-v1"}\n'
        ),
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(FourFamilyMultiplicityError, match="look authority bytes"):
        _load(root)

    root = _clone(tmp_path / "second")
    paths = _paths(root)
    paths["plan"].write_bytes(paths["plan"].read_bytes() + b" ")
    with pytest.raises(FourFamilyMultiplicityError, match="parent bytes"):
        _load(root)

    root = _clone(tmp_path / "third")
    paths = _paths(root)
    paths["base"].write_bytes(paths["base"].read_bytes() + b" ")
    with pytest.raises(FourFamilyMultiplicityError, match="QC base bytes"):
        _load(root)


def test_unstable_double_read_is_refused(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    target = _paths(root)["overlay"].resolve()
    original = Path.read_bytes
    calls = 0

    def unstable_read(path):
        nonlocal calls
        payload = original(path)
        if path.resolve() == target:
            calls += 1
            if calls == 2:
                return payload + b" "
        return payload

    monkeypatch.setattr(Path, "read_bytes", unstable_read)
    with pytest.raises(FourFamilyMultiplicityError, match="changed while being read"):
        _load(root)


def test_stable_read_stat_identity_change_is_refused(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    target = _paths(root)["overlay"].absolute()
    original_read = Path.read_bytes
    original_stat = Path.stat
    reads = 0

    def tracked_read(path):
        nonlocal reads
        payload = original_read(path)
        if path.absolute() == target:
            reads += 1
        return payload

    def changed_stat(path, *args, **kwargs):
        value = original_stat(path, *args, **kwargs)
        if path.absolute() == target and reads >= 2:
            return SimpleNamespace(
                st_dev=value.st_dev,
                st_ino=value.st_ino,
                st_size=value.st_size,
                st_mtime_ns=value.st_mtime_ns + 1,
            )
        return value

    monkeypatch.setattr(Path, "read_bytes", tracked_read)
    monkeypatch.setattr(Path, "stat", changed_stat)
    with pytest.raises(FourFamilyMultiplicityError, match="changed while being read"):
        _load(root)


@pytest.mark.parametrize("key", ("plan", "base"))
def test_parent_mutation_during_nested_authentication_is_refused(
    tmp_path, monkeypatch, key
):
    root = _clone(tmp_path)
    target_path = _paths(root)[key]
    original = module.load_qc_first_study_plan

    def mutate_after_load(path):
        plan = original(path)
        target_path.write_bytes(target_path.read_bytes() + b" ")
        return plan

    monkeypatch.setattr(module, "load_qc_first_study_plan", mutate_after_load)
    with pytest.raises(FourFamilyMultiplicityError, match="changed after"):
        _load(root)


def test_overlay_mutation_during_nested_parent_authentication_is_refused(
    tmp_path, monkeypatch
):
    root = _clone(tmp_path)
    overlay_path = _paths(root)["overlay"]
    original = module.load_qc_first_study_plan

    def mutate_child_after_parent_load(path):
        plan = original(path)
        overlay_path.write_bytes(overlay_path.read_bytes() + b" ")
        return plan

    monkeypatch.setattr(module, "load_qc_first_study_plan", mutate_child_after_parent_load)
    with pytest.raises(FourFamilyMultiplicityError, match="multiplicity overlay changed"):
        _load(root)


def test_post_load_overlay_parent_and_look_gate_mutations_are_refused(tmp_path):
    for key, expected in (
        ("overlay", "multiplicity overlay"),
        ("plan", "QC-first plan"),
        ("base", "superseded QC base"),
        ("look_authority", "zero-access look authority"),
    ):
        root = _clone(tmp_path / key)
        overlay = _load(root)
        path = _paths(root)[key]
        path.write_bytes(path.read_bytes() + b" ")
        with pytest.raises(FourFamilyMultiplicityError, match=expected):
            require_loaded_four_family_multiplicity_overlay(overlay)


def test_overlay_path_must_not_be_a_symlink(tmp_path):
    root = _clone(tmp_path)
    paths = _paths(root)
    linked = root / "linked-overlay.json"
    try:
        linked.symlink_to(paths["overlay"])
    except OSError as exc:
        pytest.skip(f"host cannot create test symlink: {exc}")
    with pytest.raises(FourFamilyMultiplicityError, match="link"):
        load_four_family_multiplicity_overlay(
            linked,
            look_authority_path=paths["look_authority"],
            qc_first_plan_path=paths["plan"],
        )


@pytest.mark.parametrize("key", ("plan", "base", "look_authority"))
def test_parent_paths_must_not_be_symlinks(tmp_path, key):
    root = _clone(tmp_path)
    paths = _paths(root)
    original = paths[key]
    real = root / f"real-{original.name}"
    original.replace(real)
    try:
        original.symlink_to(real)
    except OSError as exc:
        pytest.skip(f"host cannot create test symlink: {exc}")
    with pytest.raises(FourFamilyMultiplicityError, match="link"):
        _load(root)


def test_ancestor_directory_must_not_be_a_symlink(tmp_path):
    real_root = _clone(tmp_path / "real")
    linked_root = tmp_path / "linked-specs"
    try:
        linked_root.symlink_to(real_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create directory symlink: {exc}")
    with pytest.raises(FourFamilyMultiplicityError, match="link"):
        _load(linked_root)


def test_copy_reconstruction_pickle_and_low_level_mutation_never_create_authority(
    overlay,
):
    copied = copy.copy(overlay)
    with pytest.raises(FourFamilyMultiplicityError):
        require_loaded_four_family_multiplicity_overlay(copied)

    forged = object.__new__(FourFamilyMultiplicityOverlay)
    for field in dataclasses.fields(FourFamilyMultiplicityOverlay):
        object.__setattr__(forged, field.name, getattr(overlay, field.name))
    with pytest.raises(FourFamilyMultiplicityError):
        require_loaded_four_family_multiplicity_overlay(forged)

    try:
        round_trip = pickle.loads(pickle.dumps(overlay))
    except (TypeError, pickle.PicklingError):
        round_trip = None
    if round_trip is not None:
        with pytest.raises(FourFamilyMultiplicityError):
            require_loaded_four_family_multiplicity_overlay(round_trip)

    object.__setattr__(overlay, "overlay_id", overlay.overlay_id + "x")
    with pytest.raises(FourFamilyMultiplicityError, match="changed after"):
        require_loaded_four_family_multiplicity_overlay(overlay)


def test_dataclasses_replace_and_type_spoof_cannot_authenticate(overlay):
    with pytest.raises(TypeError):
        dataclasses.replace(overlay, overlay_hash="0" * 64)

    class SpoofedStr(str):
        pass

    object.__setattr__(overlay, "overlay_id", SpoofedStr(overlay.overlay_id))
    with pytest.raises(FourFamilyMultiplicityError, match="changed type"):
        require_loaded_four_family_multiplicity_overlay(overlay)


@pytest.mark.parametrize(
    "field,replacement",
    (
        ("definition", {}),
        ("fixed_lane_ids", ["analyst-revisions-v2"]),
        ("fixed_lane_ids", ("analyst-revisions-v2",)),
    ),
)
def test_low_level_collection_type_substitution_is_detected(
    overlay, field, replacement
):
    object.__setattr__(overlay, field, replacement)
    with pytest.raises(FourFamilyMultiplicityError):
        require_loaded_four_family_multiplicity_overlay(overlay)


@pytest.mark.parametrize("field", ("overlay_id", "overlay_hash"))
def test_valid_type_identity_mutation_is_detected(overlay, field):
    object.__setattr__(overlay, field, getattr(overlay, field) + "x")
    with pytest.raises(FourFamilyMultiplicityError, match="changed after"):
        require_loaded_four_family_multiplicity_overlay(overlay)


def test_weakref_callback_removes_overlay_authority():
    overlay = _load()
    identity = id(overlay)
    reference = weakref.ref(overlay)
    assert identity in module._FOUR_FAMILY_MULTIPLICITY_AUTHORITIES
    del overlay
    gc.collect()
    assert reference() is None
    assert identity not in module._FOUR_FAMILY_MULTIPLICITY_AUTHORITIES
