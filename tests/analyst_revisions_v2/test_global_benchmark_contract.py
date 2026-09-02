import dataclasses
import hashlib
import json
import shutil
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

import research.analyst_revisions_v2.global_benchmark_contract as module
from research.analyst_revisions_v2.global_benchmark_contract import (
    FOLD_MANIFEST_ARTIFACT_SHA256,
    FOLD_MANIFEST_HASH,
    MAP_BINDING,
    MATCHED_BINDING,
    PARENT_STOCK_SPEC_ARTIFACT_SHA256,
    SUCCESSOR_BINDING,
    GlobalBenchmarkContract,
    GlobalBenchmarkContractError,
    GlobalRatingMapEntry,
    GlobalRatingMapping,
    GlobalRatingMappingRefusal,
    GlobalRatingRefusalReason,
    GlobalRatingTransitionDisposition,
    bootstrap_seed_record,
    classify_global_rating_transition,
    coverage_meets_minimum,
    global_rating_delta,
    hash_counter_start_index,
    load_global_benchmark_contract,
    render_expected_artifact,
    require_loaded_global_benchmark_contract,
    resolve_global_rating,
)


SPEC_ROOT = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "analyst_revisions_v2"
    / "specs"
)
FILENAMES = {
    "map": "arv2_global_rating_map.structural.json",
    "matched": "arv2_global_matched_comparison.structural.json",
    "successor": "arv2_stock_historical_successor.structural.json",
    "stock": "arv2_stock_historical.structural.json",
    "folds": "arv2_stock_walk_forward_folds.structural.json",
    "plan": "arv2_qc_first.draft.json",
    "base": "arv2_round0.draft.json",
}

EXPECTED_MAPPINGS = {
    "strong buy": Fraction(1),
    "conviction buy": Fraction(1),
    "top pick": Fraction(1),
    "action list buy": Fraction(1),
    "buy": Fraction(1, 2),
    "outperform": Fraction(1, 2),
    "overweight": Fraction(1, 2),
    "market outperform": Fraction(1, 2),
    "sector outperform": Fraction(1, 2),
    "positive": Fraction(1, 2),
    "accumulate": Fraction(1, 2),
    "add": Fraction(1, 2),
    "speculative buy": Fraction(1, 2),
    "long-term buy": Fraction(1, 2),
    "outperformer": Fraction(1, 2),
    "above average": Fraction(1, 2),
    "neutral": Fraction(0),
    "hold": Fraction(0),
    "equal-weight": Fraction(0),
    "market perform": Fraction(0),
    "sector perform": Fraction(0),
    "in-line": Fraction(0),
    "sector weight": Fraction(0),
    "perform": Fraction(0),
    "peer perform": Fraction(0),
    "market weight": Fraction(0),
    "average": Fraction(0),
    "underweight": Fraction(-1, 2),
    "underperform": Fraction(-1, 2),
    "sector underperform": Fraction(-1, 2),
    "market underperform": Fraction(-1, 2),
    "reduce": Fraction(-1, 2),
    "negative": Fraction(-1, 2),
    "underperformer": Fraction(-1, 2),
    "below average": Fraction(-1, 2),
    "trim": Fraction(-1, 2),
    "cautious": Fraction(-1, 2),
    "sell": Fraction(-1),
    "strong sell": Fraction(-1),
}
EXPECTED_REFUSALS = (
    "developing",
    "equalweight",
    "fair value",
    "gradually accumulate",
    "hold neutral",
    "mixed",
    "not rated",
    "performer",
    "sector overweight",
    "sector performer",
    "sector underweight",
    "speculative hold",
    "tender",
    "trading buy",
    "trading sell",
)


def _paths(root: Path = SPEC_ROOT) -> dict[str, Path]:
    return {name: root / filename for name, filename in FILENAMES.items()}


def _load(root: Path = SPEC_ROOT) -> GlobalBenchmarkContract:
    paths = _paths(root)
    return load_global_benchmark_contract(
        map_path=paths["map"],
        matched_contract_path=paths["matched"],
        successor_spec_path=paths["successor"],
        parent_stock_spec_path=paths["stock"],
        fold_manifest_path=paths["folds"],
        qc_first_plan_path=paths["plan"],
    )


def _clone(tmp_path: Path) -> Path:
    root = tmp_path / "specs"
    root.mkdir()
    for filename in FILENAMES.values():
        shutil.copyfile(SPEC_ROOT / filename, root / filename)
    return root


def _rewrite_identity(
    path: Path, *, id_field: str, hash_field: str, prefix: str
) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw[id_field] = None
    raw[hash_field] = None
    payload = json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    raw[hash_field] = digest
    raw[id_field] = prefix + digest[:16]
    path.write_text(
        json.dumps(
            raw,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return raw


@pytest.fixture(scope="module")
def contract() -> GlobalBenchmarkContract:
    return _load()


def test_exact_artifacts_load_and_bind_unchanged_ancestry(contract):
    assert contract.map_id == MAP_BINDING["artifact_id"]
    assert contract.map_hash == MAP_BINDING["content_sha256"]
    assert contract.matched_contract_id == MATCHED_BINDING["artifact_id"]
    assert contract.matched_contract_hash == MATCHED_BINDING["content_sha256"]
    assert contract.successor_spec_id == SUCCESSOR_BINDING["artifact_id"]
    assert contract.successor_spec_hash == SUCCESSOR_BINDING["content_sha256"]
    assert len(contract.entries) == 39
    assert contract.measured_refusals == EXPECTED_REFUSALS
    assert all(value is False for value in contract.capabilities.values())
    assert contract.source_access_available is False
    assert contract.outcome_access_available is False
    assert contract.qc_action_available is False
    assert contract.result_disposition_available is False
    assert contract.deployment_available is False
    assert contract.orders_available is False
    assert hashlib.sha256(_paths()["stock"].read_bytes()).hexdigest() == (
        PARENT_STOCK_SPEC_ARTIFACT_SHA256
    )
    assert hashlib.sha256(_paths()["folds"].read_bytes()).hexdigest() == (
        FOLD_MANIFEST_ARTIFACT_SHA256
    )


@pytest.mark.parametrize("name", ("map", "matched", "successor"))
def test_checked_in_artifact_is_exact_renderer_output(name):
    assert _paths()[name].read_bytes() == render_expected_artifact(name).encode("utf-8")


@pytest.mark.parametrize("label,score", tuple(EXPECTED_MAPPINGS.items()))
def test_every_approved_alias_maps_to_exact_fraction(contract, label, score):
    result = resolve_global_rating(contract, label)
    assert isinstance(result, GlobalRatingMapping)
    assert result.canonical_label == label
    assert result.score == score
    assert Fraction(result.entry.legacy_level - 3, 2) == score


@pytest.mark.parametrize("label", EXPECTED_REFUSALS)
def test_every_measured_refusal_is_named(contract, label):
    result = resolve_global_rating(contract, label)
    assert isinstance(result, GlobalRatingMappingRefusal)
    assert result.canonical_label == label
    assert result.reason is GlobalRatingRefusalReason.MEASURED_REFUSAL


@pytest.mark.parametrize(
    "raw,canonical,score",
    (
        ("  MARKET   PERFORM  ", "market perform", Fraction(0)),
        (" Sector   Outperform ", "sector outperform", Fraction(1, 2)),
        ("STRONG BUY", "strong buy", Fraction(1)),
    ),
)
def test_only_ascii_case_and_literal_space_runs_are_canonicalized(
    contract, raw, canonical, score
):
    result = resolve_global_rating(contract, raw)
    assert isinstance(result, GlobalRatingMapping)
    assert result.canonical_label == canonical
    assert result.score == score


@pytest.mark.parametrize(
    "raw,reason,canonical",
    (
        ("equalweight", GlobalRatingRefusalReason.MEASURED_REFUSAL, "equalweight"),
        ("equal weight", GlobalRatingRefusalReason.UNKNOWN_FUTURE_LABEL, "equal weight"),
        ("sector performer", GlobalRatingRefusalReason.MEASURED_REFUSAL, "sector performer"),
        ("in line", GlobalRatingRefusalReason.UNKNOWN_FUTURE_LABEL, "in line"),
        ("brand new rating", GlobalRatingRefusalReason.UNKNOWN_FUTURE_LABEL, "brand new rating"),
    ),
)
def test_punctuation_and_unknown_tripwires_do_not_default(
    contract, raw, reason, canonical
):
    result = resolve_global_rating(contract, raw)
    assert isinstance(result, GlobalRatingMappingRefusal)
    assert result.reason is reason
    assert result.canonical_label == canonical


def test_exact_hyphenated_and_ambiguous_naive_aliases_are_explicit(contract):
    for label in ("equal-weight", "sector perform", "in-line"):
        result = resolve_global_rating(contract, label)
        assert isinstance(result, GlobalRatingMapping)
        assert result.score == 0


@pytest.mark.parametrize(
    "raw,reason",
    (
        (None, GlobalRatingRefusalReason.INVALID_TYPE),
        (True, GlobalRatingRefusalReason.INVALID_TYPE),
        ("", GlobalRatingRefusalReason.EMPTY_OR_OVERLONG),
        ("   ", GlobalRatingRefusalReason.EMPTY_OR_OVERLONG),
        ("x" * 257, GlobalRatingRefusalReason.EMPTY_OR_OVERLONG),
        ("market\tperform", GlobalRatingRefusalReason.NON_PRINTABLE_ASCII),
        ("market\nperform", GlobalRatingRefusalReason.NON_PRINTABLE_ASCII),
        ("market\x7fperform", GlobalRatingRefusalReason.NON_PRINTABLE_ASCII),
        ("market\u00a0perform", GlobalRatingRefusalReason.NON_PRINTABLE_ASCII),
        ("in\u2013line", GlobalRatingRefusalReason.NON_PRINTABLE_ASCII),
        ("Ｂuy", GlobalRatingRefusalReason.NON_PRINTABLE_ASCII),
    ),
)
def test_invalid_text_refuses_without_unicode_normalization(contract, raw, reason):
    result = resolve_global_rating(contract, raw)
    assert isinstance(result, GlobalRatingMappingRefusal)
    assert result.reason is reason


def _average_ranks(values):
    ordered = sorted(set(values))
    ranks = {}
    for value in ordered:
        positions = [index + 1 for index, item in enumerate(sorted(values)) if item == value]
        ranks[value] = Fraction(positions[0] + positions[-1], 2)
    return tuple(ranks[value] for value in values)


def test_range_alignment_is_spearman_inert_and_delta_is_exact(contract):
    labels = (
        "strong buy",
        "buy",
        "neutral",
        "neutral",
        "underweight",
        "sell",
    )
    mappings = tuple(resolve_global_rating(contract, label) for label in labels)
    assert all(isinstance(item, GlobalRatingMapping) for item in mappings)
    levels = tuple(item.entry.legacy_level - 3 for item in mappings)
    aligned = tuple(item.score for item in mappings)
    assert _average_ranks(levels) == _average_ranks(aligned)
    assert global_rating_delta(contract, mappings[1], mappings[1]) == 0
    assert global_rating_delta(contract, mappings[-1], mappings[0]) == 2


def test_transition_direction_and_tier_collapse_dispositions_are_exact(contract):
    neutral = resolve_global_rating(contract, "neutral")
    buy = resolve_global_rating(contract, "buy")
    assert isinstance(neutral, GlobalRatingMapping)
    assert isinstance(buy, GlobalRatingMapping)
    assert classify_global_rating_transition(
        contract, action="upgrade", previous=neutral, current=buy
    ).disposition is GlobalRatingTransitionDisposition.ACTIVE_EXPECTED_DIRECTION
    assert classify_global_rating_transition(
        contract, action="upgrade", previous=neutral, current=neutral
    ).disposition is GlobalRatingTransitionDisposition.ACTIVE_TIER_COLLAPSE_ZERO
    assert classify_global_rating_transition(
        contract, action="upgrade", previous=buy, current=neutral
    ).disposition is (
        GlobalRatingTransitionDisposition.JOINT_DIRECTION_CONFLICT_REFUSAL
    )


def test_forged_mapping_and_nested_entry_are_rejected_by_delta(contract):
    resolved = resolve_global_rating(contract, "buy")
    assert isinstance(resolved, GlobalRatingMapping)
    forged_entry = GlobalRatingMapEntry("buy", 4, 1, 1)
    forged = dataclasses.replace(resolved, entry=forged_entry)
    with pytest.raises(GlobalBenchmarkContractError, match="resolver-authentic"):
        global_rating_delta(contract, resolved, forged)


def test_equality_spoofed_mapping_entry_cannot_bypass_delta_authentication(contract):
    resolved = resolve_global_rating(contract, "buy")
    assert isinstance(resolved, GlobalRatingMapping)

    class AlwaysEqualEntry:
        score = Fraction(999)

        def __eq__(self, _other):
            return True

    forged = GlobalRatingMapping(
        resolved.raw_label,
        resolved.canonical_label,
        AlwaysEqualEntry(),
        resolved.map_id,
        resolved.map_hash,
    )
    with pytest.raises(GlobalBenchmarkContractError, match="resolver-authentic"):
        global_rating_delta(contract, resolved, forged)


@pytest.mark.parametrize(
    "numerator,denominator,expected",
    ((19, 20, True), (95, 100, True), (949, 1000, False), (0, 1, False)),
)
def test_coverage_uses_exact_cross_multiplication(numerator, denominator, expected):
    assert coverage_meets_minimum(numerator, denominator) is expected


def test_coverage_threshold_cannot_be_overridden_by_caller():
    with pytest.raises(TypeError):
        coverage_meets_minimum(0, 1, minimum_numerator=0)


@pytest.mark.parametrize(
    "args",
    ((True, 20), (19, True), (-1, 20), (1, 0), (21, 20)),
)
def test_invalid_coverage_counts_refuse(args):
    with pytest.raises(GlobalBenchmarkContractError, match="coverage"):
        coverage_meets_minimum(*args)


def test_fold_axes_and_hash_counter_are_exact_and_dependency_independent(contract):
    assert tuple(item["session_count"] for item in contract.fold_axis_summaries) == (
        233,
        232,
        231,
        230,
        232,
        230,
    )
    assert tuple(item["allowed_start_count"] for item in contract.fold_axis_summaries) == (
        214,
        213,
        212,
        211,
        213,
        211,
    )
    assert hash_counter_start_index(
        contract,
        resample_ordinal=0,
        fold_ordinal=0,
        block_ordinal=0,
    ) == 142
    assert hash_counter_start_index(
        contract,
        resample_ordinal=19998,
        fold_ordinal=5,
        block_ordinal=11,
    ) == 187
    seed = bootstrap_seed_record(contract)
    assert tuple(seed) == (
        "domain",
        "successor_stock_spec_sha256",
        "matched_row_contract_sha256",
        "global_rating_map_sha256",
        "fold_manifest_sha256",
        "evaluation_id",
        "sampler_version",
    )
    assert seed["fold_manifest_sha256"] == FOLD_MANIFEST_HASH


def test_unbiased_conversion_rejects_tail_without_modulo_bias():
    ceiling = 1 << 256
    modulus = 10
    limit = ceiling - (ceiling % modulus)
    assert module._unbiased_index((limit, limit + 1, 7), modulus) == 7


@pytest.mark.parametrize(
    "kwargs",
    (
        {"resample_ordinal": True, "fold_ordinal": 0, "block_ordinal": 0},
        {"resample_ordinal": -1, "fold_ordinal": 0, "block_ordinal": 0},
        {"resample_ordinal": 19999, "fold_ordinal": 0, "block_ordinal": 0},
        {"resample_ordinal": 0, "fold_ordinal": 6, "block_ordinal": 0},
        {"resample_ordinal": 0, "fold_ordinal": 0, "block_ordinal": 12},
    ),
)
def test_hash_counter_refuses_invalid_ordinals(contract, kwargs):
    with pytest.raises(GlobalBenchmarkContractError):
        hash_counter_start_index(contract, **kwargs)


def test_hash_counter_start_count_cannot_be_overridden_by_caller(contract):
    with pytest.raises(TypeError):
        hash_counter_start_index(
            contract,
            resample_ordinal=0,
            fold_ordinal=0,
            block_ordinal=0,
            start_count=1,
        )


def test_successor_lineage_is_acyclic_and_does_not_reparent_fold(contract):
    assert contract.lineage_graph["qc_base"] == ("strategy_pdf",)
    assert contract.lineage_graph["qc_plan"] == ("strategy_pdf", "qc_base")
    assert contract.lineage_graph["fold_manifest"] == (
        "strategy_pdf",
        "qc_plan",
        "stock_v1",
    )
    assert "stock_v2" not in contract.lineage_graph["fold_manifest"]
    module._assert_acyclic(contract.lineage_graph)


def test_successor_explicitly_binds_superseded_qc_plan_base():
    raw = json.loads(_paths()["successor"].read_text(encoding="utf-8"))
    assert raw["superseded_qc_plan_base"] == {
        "artifact_id": "arv2-round0-candidate-8d13a0a4577df322",
        "content_sha256": (
            "8d13a0a4577df3223c96c4c11722457e059b4ade63f578ab860ce7364494e847"
        ),
        "artifact_sha256": (
            "b40a76f5f2f7726f328f1e444a41ecb0670234055a7c9c7245a26ffab601af2f"
        ),
    }


def test_rehashed_lineage_cannot_omit_qc_base_parent(tmp_path):
    root = _clone(tmp_path)
    path = _paths(root)["successor"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    qc_plan = next(
        item for item in raw["acyclic_lineage"]["ordered_nodes"]
        if item["node"] == "qc_plan"
    )
    qc_plan["parents"].remove("qc_base")
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_identity(
        path,
        id_field="spec_id",
        hash_field="spec_hash",
        prefix="arv2-stock-historical-successor-",
    )
    with pytest.raises(GlobalBenchmarkContractError, match="incomplete"):
        _load(root)


def test_rehashed_reverse_edge_is_rejected_as_cycle(tmp_path):
    root = _clone(tmp_path)
    path = _paths(root)["successor"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    fold = next(
        item for item in raw["acyclic_lineage"]["ordered_nodes"]
        if item["node"] == "fold_manifest"
    )
    fold["parents"].append("stock_v2")
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_identity(
        path,
        id_field="spec_id",
        hash_field="spec_hash",
        prefix="arv2-stock-historical-successor-",
    )
    with pytest.raises(GlobalBenchmarkContractError, match="cycle"):
        _load(root)


def test_rehashed_lineage_missing_transitive_authority_edge_is_rejected(tmp_path):
    root = _clone(tmp_path)
    path = _paths(root)["successor"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    stock_v2 = next(
        item for item in raw["acyclic_lineage"]["ordered_nodes"]
        if item["node"] == "stock_v2"
    )
    stock_v2["parents"].remove("qc_plan")
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_identity(
        path,
        id_field="spec_id",
        hash_field="spec_hash",
        prefix="arv2-stock-historical-successor-",
    )
    with pytest.raises(GlobalBenchmarkContractError, match="incomplete"):
        _load(root)


def test_rehashed_lineage_malformed_parent_refuses_with_domain_error(tmp_path):
    root = _clone(tmp_path)
    path = _paths(root)["successor"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["acyclic_lineage"]["ordered_nodes"][1]["parents"] = [["strategy_pdf"]]
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_identity(
        path,
        id_field="spec_id",
        hash_field="spec_hash",
        prefix="arv2-stock-historical-successor-",
    )
    with pytest.raises(GlobalBenchmarkContractError, match="malformed"):
        _load(root)


@pytest.mark.parametrize(
    "artifact,id_field,hash_field,prefix,mutate",
    (
        (
            "map",
            "map_id",
            "map_hash",
            "arv2-global-rating-map-",
            lambda raw: raw["ordered_mappings"][1]["aliases"].__setitem__(
                1, "BUY"
            ),
        ),
        (
            "map",
            "map_id",
            "map_hash",
            "arv2-global-rating-map-",
            lambda raw: raw["capabilities"].update({"outcome_access": True}),
        ),
        (
            "matched",
            "contract_id",
            "contract_hash",
            "arv2-global-matched-",
            lambda raw: raw["paired_metric_contract"].update(
                {"both_scores_constant": "both_totalize_to_zero"}
            ),
        ),
        (
            "matched",
            "contract_id",
            "contract_hash",
            "arv2-global-matched-",
            lambda raw: raw["coverage_contract"].update(
                {"outcome_informed_map_fold_period_seed_or_retry_change": "allowed"}
            ),
        ),
        (
            "matched",
            "contract_id",
            "contract_hash",
            "arv2-global-matched-",
            lambda raw: raw["paired_sector_normalization"].update(
                {"nonzero_range_zero_MAD": "all_zero"}
            ),
        ),
        (
            "successor",
            "spec_id",
            "spec_hash",
            "arv2-stock-historical-successor-",
            lambda raw: raw["existing_fold_manifest"].update(
                {"bytes_and_parent_pins_changed": True}
            ),
        ),
    ),
)
def test_correctly_rehashed_policy_weakenings_refuse(
    tmp_path, artifact, id_field, hash_field, prefix, mutate
):
    root = _clone(tmp_path)
    path = _paths(root)[artifact]
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_identity(
        path,
        id_field=id_field,
        hash_field=hash_field,
        prefix=prefix,
    )
    with pytest.raises(GlobalBenchmarkContractError):
        _load(root)


@pytest.mark.parametrize(
    "mutation,reason",
    (
        (
            lambda raw: raw["ordered_refusals"].__setitem__(0, "buy"),
            "overlap",
        ),
        (
            lambda raw: raw["ordered_mappings"][1].__setitem__(
                "score", {"numerator": 2, "denominator": 4}
            ),
            "reduced rational",
        ),
    ),
)
def test_rehashed_map_overlap_and_unreduced_rational_refuse(
    tmp_path, mutation, reason
):
    root = _clone(tmp_path)
    path = _paths(root)["map"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutation(raw)
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_identity(
        path,
        id_field="map_id",
        hash_field="map_hash",
        prefix="arv2-global-rating-map-",
    )
    with pytest.raises(GlobalBenchmarkContractError, match=reason):
        _load(root)


def test_matched_contract_pins_symmetric_totalization_coverage_and_numerics():
    raw = json.loads(_paths()["matched"].read_text(encoding="utf-8"))
    sector = raw["paired_sector_normalization"]
    assert sector["exact_zero_range_firm_arm"].startswith(
        "paired_only_all_zero_standardized_scores"
    )
    assert sector["exact_zero_range_global_arm"].startswith(
        "paired_only_all_zero_standardized_scores"
    )
    assert sector["nonzero_range_zero_MAD"].startswith("joint_")
    direction = raw["arm_contract"]["global_direction_contract"]
    assert direction["zero_delta"].startswith("ACTIVE_")
    assert direction["opposite_sign_delta"].startswith("joint_")
    ledgers = raw["coverage_contract"]["separate_ledgers"]
    assert "direction_admissible_expected_sign_or_zero_delta" in (
        ledgers["endpoint_pair_mapping"]
    )
    assert "opposite_sign_is_denominator_only" in ledgers["endpoint_pair_mapping"]
    assert raw["coverage_contract"]["gate_aggregation"].endswith(
        "every_nonempty_fold"
    )
    numerical = raw["paired_metric_contract"]["numerical_contract"]
    assert numerical["decimal_precision"] == 50
    assert numerical["decimal_rounding"] == "ROUND_HALF_EVEN"
    assert numerical["decimal_Emin"] == -999999
    assert numerical["decimal_Emax"] == 999999
    assert numerical["finite_inputs_only"] is True
    assert numerical["ambient_decimal_context"].startswith("ignored_")
    assert raw["paired_metric_contract"]["ordered_primary_date_disposition"] == [
        "outcome_identity_invalid_or_duplicate_INVALID_DATA",
        "fewer_than_20_identical_rows_joint_date_refusal",
        "constant_shared_outcome_joint_date_refusal",
        "both_scores_constant_joint_date_refusal",
        "exactly_one_score_constant_totalize_constant_arm_to_zero",
        "neither_score_constant_compute_both_Spearman",
    ]


def test_diagnostic_ratios_keep_identical_units_and_exact_denominators():
    raw = json.loads(_paths()["matched"].read_text(encoding="utf-8"))
    ratios = {
        item["id"]: item
        for item in raw["diagnostics_contract"]["required_ratios"]
    }
    assert ratios["global_tier_collapse_zero_share"]["denominator"] == (
        "paired_admitted_directional_event_instances_with_both_global_endpoints_mapped"
    )
    assert ratios["global_direction_conflict_share"]["denominator"] == (
        "paired_admitted_directional_event_instances_with_both_global_endpoints_mapped"
    )
    assert ratios["firm_totalized_zero_date_share"]["denominator"] == (
        "preoutcome_candidate_dates"
    )
    assert ratios["global_totalized_zero_date_share"]["denominator"] == (
        "preoutcome_candidate_dates"
    )
    assert ratios["zero_available_bootstrap_replicate_share"]["denominator"] == (
        "exactly_19999_registered_bootstrap_replicates"
    )


@pytest.mark.parametrize("attack", ("bom", "crlf", "float", "nonfinite", "duplicate"))
def test_noncanonical_map_bytes_refuse(tmp_path, attack):
    root = _clone(tmp_path)
    path = _paths(root)["map"]
    payload = path.read_bytes()
    if attack == "bom":
        payload = b"\xef\xbb\xbf" + payload
    elif attack == "crlf":
        payload = payload.replace(b"\n", b"\r\n")
    elif attack == "float":
        payload = payload.replace(b'"union_count": 54', b'"union_count": 54.0')
    elif attack == "nonfinite":
        payload = payload.replace(b'"union_count": 54', b'"union_count": NaN')
    else:
        payload = payload.replace(
            b'  "authority":',
            b'  "schema": "duplicate",\n  "authority":',
            1,
        )
    path.write_bytes(payload)
    with pytest.raises(GlobalBenchmarkContractError):
        _load(root)


@pytest.mark.parametrize("source", tuple(FILENAMES))
def test_loaded_authority_rejects_every_source_mutation(tmp_path, source):
    root = _clone(tmp_path)
    contract = _load(root)
    path = _paths(root)[source]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(GlobalBenchmarkContractError, match="changed"):
        require_loaded_global_benchmark_contract(contract)


def test_loaded_authority_rejects_object_forgery(tmp_path):
    root = _clone(tmp_path)
    contract = _load(root)
    forged = object.__new__(GlobalBenchmarkContract)
    for field in dataclasses.fields(GlobalBenchmarkContract):
        object.__setattr__(forged, field.name, getattr(contract, field.name))
    with pytest.raises(GlobalBenchmarkContractError, match="loader authority"):
        require_loaded_global_benchmark_contract(forged)


def test_low_level_mutation_of_loaded_object_is_detected():
    contract = _load()
    object.__setattr__(contract, "map_hash", "0" * 64)
    with pytest.raises(GlobalBenchmarkContractError, match="changed"):
        require_loaded_global_benchmark_contract(contract)


def test_low_level_mutation_of_nested_map_entry_is_detected():
    contract = _load()
    object.__setattr__(contract.entries[0], "legacy_level", 4)
    with pytest.raises(GlobalBenchmarkContractError, match="changed"):
        require_loaded_global_benchmark_contract(contract)


def test_equality_spoofed_identity_type_is_detected_before_comparison():
    class AlwaysEqualStr(str):
        def __eq__(self, _other):
            return True

    contract = _load()
    object.__setattr__(contract, "map_hash", AlwaysEqualStr("0" * 64))
    with pytest.raises(GlobalBenchmarkContractError, match="changed type"):
        require_loaded_global_benchmark_contract(contract)


def test_malformed_authority_collection_type_is_detected():
    contract = _load()
    object.__setattr__(contract, "entries", list(contract.entries))
    with pytest.raises(GlobalBenchmarkContractError, match="entries changed type"):
        require_loaded_global_benchmark_contract(contract)


def test_private_expected_policy_constants_are_recursively_immutable():
    with pytest.raises(TypeError):
        module._EXTERNAL_BINDINGS["dataset_id"] = "forged"
    with pytest.raises(TypeError):
        module._FOLD_AXIS_SUMMARIES[0]["session_count"] = 1
    with pytest.raises(TypeError):
        module.MAP_BINDING["content_sha256"] = "0" * 64


def test_unstable_double_read_refuses_before_authentication(tmp_path, monkeypatch):
    root = _clone(tmp_path)
    target = _paths(root)["map"].resolve()
    original = Path.read_bytes
    calls = 0

    def unstable(path):
        nonlocal calls
        payload = original(path)
        if path.resolve() == target:
            calls += 1
            if calls == 2:
                return payload + b" "
        return payload

    monkeypatch.setattr(Path, "read_bytes", unstable)
    with pytest.raises(GlobalBenchmarkContractError, match="changed while being read"):
        _load(root)


@pytest.mark.parametrize("source", tuple(FILENAMES))
def test_in_load_source_mutation_refuses_final_revalidation(
    tmp_path, monkeypatch, source
):
    root = _clone(tmp_path)
    target = _paths(root)[source]
    original = module._validate_fold_axes

    def mutate_after_all_initial_reads(manifest):
        result = original(manifest)
        target.write_bytes(target.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        module,
        "_validate_fold_axes",
        mutate_after_all_initial_reads,
    )
    with pytest.raises(GlobalBenchmarkContractError, match="changed after authentication"):
        _load(root)


@pytest.mark.parametrize(
    "slot_group,slot_name",
    (
        ("global", "global_rating_map_definition_sha256"),
        ("global", "matched_row_contract_sha256"),
        ("global", "minimum_paired_coverage_definition_sha256"),
        ("external", "global_rating_map_definition_sha256"),
        ("external", "matched_global_comparison_definition_sha256"),
        ("external", "fold_manifest_sha256"),
        ("history", "fold_manifest_sha256"),
    ),
)
def test_each_predecessor_child_slot_must_remain_null(
    tmp_path, monkeypatch, slot_group, slot_name
):
    root = _clone(tmp_path)
    original = module.load_stock_evaluation_contract

    def parent_with_forged_child(*args, **kwargs):
        parent = original(*args, **kwargs)
        sections = dict(parent.sections)
        external = dict(parent.external_bindings)
        if slot_group == "global":
            section = dict(sections["global_benchmark_definition"])
            section[slot_name] = "0" * 64
            sections["global_benchmark_definition"] = section
        elif slot_group == "external":
            external[slot_name] = "0" * 64
        else:
            history = dict(sections["history_definition"])
            walk_forward = dict(history["walk_forward"])
            walk_forward[slot_name] = "0" * 64
            history["walk_forward"] = walk_forward
            sections["history_definition"] = history
        return SimpleNamespace(
            spec_id=parent.spec_id,
            spec_hash=parent.spec_hash,
            sections=sections,
            external_bindings=external,
        )

    monkeypatch.setattr(
        module,
        "load_stock_evaluation_contract",
        parent_with_forged_child,
    )
    with pytest.raises(GlobalBenchmarkContractError, match="child slots|circular"):
        _load(root)


def test_qc_plan_error_is_normalized_to_global_contract_error(tmp_path, monkeypatch):
    from research.analyst_revisions_v2.qc_first_plan import QcFirstPlanError

    root = _clone(tmp_path)

    def fail_parent(*_args, **_kwargs):
        raise QcFirstPlanError("simulated ancestry race")

    monkeypatch.setattr(module, "load_stock_evaluation_contract", fail_parent)
    with pytest.raises(GlobalBenchmarkContractError, match="authentication failed"):
        _load(root)


def test_symlinked_artifact_refuses_when_host_can_create_symlink(tmp_path):
    root = _clone(tmp_path)
    path = _paths(root)["map"]
    target = root / "real-map.json"
    path.replace(target)
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("host cannot create an unprivileged symlink")
    with pytest.raises(GlobalBenchmarkContractError, match="link"):
        _load(root)
