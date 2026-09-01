from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from data.exchange_calendar import resolve_nth_session_after, trading_sessions
import research.analyst_revisions_v2.fold_manifest as manifest_module
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.fold_manifest import (
    StockFoldManifestError,
    load_stock_fold_manifest,
    require_loaded_stock_fold_manifest,
)
from research.analyst_revisions_v2.import_firewall import (
    validate_transitive_import_closure,
)
from research.analyst_revisions_v2.stock_controls import (
    StructuralFoldBoundary,
    require_structural_fold_boundary,
)


ROOT = Path(__file__).resolve().parents[2]
SPEC = (
    ROOT
    / "research"
    / "analyst_revisions_v2"
    / "specs"
    / "arv2_stock_walk_forward_folds.structural.json"
)
STOCK_SPEC = SPEC.with_name("arv2_stock_historical.structural.json")
QC_PLAN = SPEC.with_name("arv2_qc_first.draft.json")
ROUND0_PLAN = SPEC.with_name("arv2_round0.draft.json")
SECTION_NAMES = (
    "calendar_contract",
    "walk_forward_contract",
    "cross_boundary_common_event_contract",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _rehash(raw: dict[str, object]) -> None:
    walk_forward = raw["walk_forward_contract"]
    for fold in walk_forward["folds"]:
        for boundary in fold["horizon_boundaries"]:
            boundary_payload = dict(boundary)
            boundary_payload.pop("structural_fold_sha256", None)
            boundary["structural_fold_sha256"] = hashlib.sha256(
                canonical_json_bytes(boundary_payload)
            ).hexdigest()
        fold["fold_sha256"] = None
        fold["fold_sha256"] = hashlib.sha256(_canonical(fold)).hexdigest()
    raw["section_hashes"] = {
        name: hashlib.sha256(_canonical(raw[name])).hexdigest()
        for name in SECTION_NAMES
    }
    raw["manifest_id"] = None
    raw["manifest_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    raw["manifest_hash"] = digest
    raw["manifest_id"] = f"arv2-stock-folds-{digest[:16]}"


def _write(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / SPEC.name
    path.write_bytes(
        (
            json.dumps(
                raw,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    )
    return path


def _load(path: Path = SPEC):
    return load_stock_fold_manifest(
        path,
        stock_evaluation_path=STOCK_SPEC,
        qc_first_plan_path=QC_PLAN,
    )


def _copy_source_graph(tmp_path: Path) -> tuple[Path, Path, Path]:
    local_manifest = tmp_path / SPEC.name
    local_stock = tmp_path / STOCK_SPEC.name
    local_qc = tmp_path / QC_PLAN.name
    for source, target in (
        (SPEC, local_manifest),
        (STOCK_SPEC, local_stock),
        (QC_PLAN, local_qc),
        (ROUND0_PLAN, tmp_path / ROUND0_PLAN.name),
    ):
        target.write_bytes(source.read_bytes())
    return local_manifest, local_stock, local_qc


def _first_session(year: int) -> str:
    return trading_sessions(date(year, 1, 1), date(year, 1, 15))[0].isoformat()


def test_repository_manifest_regenerates_six_four_horizon_folds() -> None:
    manifest = _load()

    assert manifest.manifest_id == "arv2-stock-folds-1002155dbe8e3e87"
    assert manifest.manifest_hash == (
        "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611"
    )
    assert manifest.parent_plan_id == "arv2-qc-first-plan-36e455e72b8750fe"
    assert manifest.parent_plan_artifact_sha256 == hashlib.sha256(
        QC_PLAN.read_bytes()
    ).hexdigest()
    assert manifest.parent_stock_spec_id == (
        "arv2-stock-historical-c5ff2a6a0dcf341e"
    )
    assert manifest.parent_stock_spec_artifact_sha256 == hashlib.sha256(
        STOCK_SPEC.read_bytes()
    ).hexdigest()
    assert manifest.evaluation_id == "arv2-eval-stock-historical-qc-001"

    sessions = tuple(
        item.isoformat()
        for item in trading_sessions(date(2013, 1, 2), date(2026, 8, 28))
    )
    assert manifest.calendar_contract["axis_session_count"] == len(sessions) == 3435
    assert manifest.calendar_contract["axis_sha256"] == hashlib.sha256(
        _canonical(sessions)
    ).hexdigest()

    walk_forward = manifest.walk_forward_contract
    assert (
        walk_forward["rolling_or_expanding_rule"],
        walk_forward["train_years"],
        walk_forward["validation_years"],
        walk_forward["test_years"],
        walk_forward["step_years"],
    ) == ("rolling", 5, 2, 1, 1)
    folds = walk_forward["folds"]
    assert tuple(fold["test_year"] for fold in folds) == tuple(range(2020, 2026))
    assert walk_forward["ordered_fold_ids"] == tuple(
        f"arv2-wf-test-{year}" for year in range(2020, 2026)
    )

    for fold in folds:
        year = fold["test_year"]
        assert fold["nominal_train_interval"] == {
            "start_inclusive": _first_session(year - 7),
            "end_exclusive": _first_session(year - 2),
        }
        assert fold["nominal_validation_interval"] == {
            "start_inclusive": _first_session(year - 2),
            "end_exclusive": _first_session(year),
        }
        assert fold["nominal_test_interval"] == {
            "start_inclusive": _first_session(year),
            "end_exclusive": _first_session(year + 1),
        }
        assert fold["ordered_horizons_sessions"] == (1, 5, 20, 60)
        assert tuple(
            item["horizon_sessions"] for item in fold["horizon_boundaries"]
        ) == (1, 5, 20, 60)
        for item in fold["horizon_boundaries"]:
            boundary = StructuralFoldBoundary(**dict(item))
            assert require_structural_fold_boundary(boundary) is boundary
            assert boundary.validation_start == resolve_nth_session_after(
                boundary.train_end_exclusive,
                boundary.horizon_sessions,
            )
            assert boundary.test_start == resolve_nth_session_after(
                boundary.validation_end_exclusive,
                boundary.horizon_sessions,
            )


def test_manifest_lineage_common_events_and_authority_are_fail_closed() -> None:
    manifest = _load()

    assert manifest.strategy_pdf_sha256 == manifest_module.STRATEGY_PDF_SHA256
    assert manifest.parent_plan_hash == manifest_module.PARENT_PLAN_HASH
    assert manifest.parent_stock_spec_hash == manifest_module.PARENT_STOCK_SPEC_HASH
    assert manifest.parent_history_section_sha256 == (
        manifest_module.PARENT_HISTORY_SECTION_SHA256
    )
    common_events = manifest.cross_boundary_common_event_contract
    assert common_events["outcome_duplication"] is False
    assert common_events["component_inventory_sha256"] is None
    assert common_events["component_count"] is None
    assert common_events["current_data_access_authorized"] is False
    assert all(value is None for value in manifest.external_bindings.values())
    assert manifest.capabilities and all(
        value is False for value in manifest.capabilities.values()
    )
    assert manifest.source_access_available is False
    assert manifest.outcome_access_available is False
    assert manifest.qc_action_available is False
    assert manifest.result_disposition_available is False
    assert manifest.deployment_available is False
    assert manifest.orders_available is False
    with pytest.raises(TypeError):
        manifest.walk_forward_contract["train_years"] = 4
    with pytest.raises(TypeError):
        manifest_module.CAPABILITIES["qc_launch"] = True


def _drop_last_fold(raw: dict[str, object]) -> None:
    walk_forward = raw["walk_forward_contract"]
    walk_forward["folds"].pop()
    walk_forward["ordered_fold_ids"].pop()


def _weaken_boundary_gap(raw: dict[str, object]) -> None:
    boundary = raw["walk_forward_contract"]["folds"][0]["horizon_boundaries"][3]
    boundary["purge_sessions"] = 20
    boundary["embargo_sessions"] = 20


def _admit_partial_2026(raw: dict[str, object]) -> None:
    raw["walk_forward_contract"]["partial_2026_disposition"] = (
        "admitted_to_fixed_cutoff_evaluation"
    )


def _reorder_folds(raw: dict[str, object]) -> None:
    walk_forward = raw["walk_forward_contract"]
    walk_forward["folds"][0], walk_forward["folds"][1] = (
        walk_forward["folds"][1],
        walk_forward["folds"][0],
    )
    walk_forward["ordered_fold_ids"][0], walk_forward["ordered_fold_ids"][1] = (
        walk_forward["ordered_fold_ids"][1],
        walk_forward["ordered_fold_ids"][0],
    )


def _duplicate_fold(raw: dict[str, object]) -> None:
    walk_forward = raw["walk_forward_contract"]
    walk_forward["folds"].append(copy.deepcopy(walk_forward["folds"][-1]))
    walk_forward["ordered_fold_ids"].append(walk_forward["ordered_fold_ids"][-1])


def _reorder_horizons(raw: dict[str, object]) -> None:
    fold = raw["walk_forward_contract"]["folds"][0]
    fold["ordered_horizons_sessions"].reverse()
    fold["horizon_boundaries"].reverse()


def _duplicate_horizon(raw: dict[str, object]) -> None:
    fold = raw["walk_forward_contract"]["folds"][0]
    fold["ordered_horizons_sessions"].append(fold["ordered_horizons_sessions"][-1])
    fold["horizon_boundaries"].append(
        copy.deepcopy(fold["horizon_boundaries"][-1])
    )


def _move_boundary_one_session(raw: dict[str, object]) -> None:
    boundary = raw["walk_forward_contract"]["folds"][0]["horizon_boundaries"][0]
    boundary["validation_start"] = boundary["train_end_exclusive"]


def _drift_calendar_axis(raw: dict[str, object]) -> None:
    calendar = raw["calendar_contract"]
    calendar["axis_start_inclusive"] = "2013-01-03"
    sessions = tuple(
        item.isoformat()
        for item in trading_sessions(date(2013, 1, 3), date(2026, 8, 28))
    )
    calendar["axis_session_count"] = len(sessions)
    calendar["axis_sha256"] = hashlib.sha256(_canonical(sessions)).hexdigest()


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda raw: raw.update(status="independently_reviewed_executable"),
            id="status",
        ),
        pytest.param(
            lambda raw: raw.update(authority="outcome_and_qc_authority"),
            id="authority",
        ),
        pytest.param(
            lambda raw: raw.update(parent_stock_spec_hash="a" * 64),
            id="parent-lineage",
        ),
        pytest.param(
            lambda raw: raw["walk_forward_contract"].update(train_years=4),
            id="shorter-training",
        ),
        pytest.param(
            lambda raw: raw["walk_forward_contract"].update(
                rolling_or_expanding_rule="expanding"
            ),
            id="different-fold-rule",
        ),
        pytest.param(_drop_last_fold, id="underfilled-fold-set"),
        pytest.param(_admit_partial_2026, id="partial-2026-admission"),
        pytest.param(_reorder_folds, id="reordered-folds"),
        pytest.param(_duplicate_fold, id="duplicate-fold"),
        pytest.param(_reorder_horizons, id="reordered-horizons"),
        pytest.param(_duplicate_horizon, id="duplicate-horizon"),
        pytest.param(_move_boundary_one_session, id="off-by-one-boundary"),
        pytest.param(_drift_calendar_axis, id="calendar-axis-drift"),
        pytest.param(_weaken_boundary_gap, id="weakened-purge-embargo"),
        pytest.param(
            lambda raw: raw["cross_boundary_common_event_contract"].update(
                outcome_duplication=True
            ),
            id="duplicated-common-event-outcomes",
        ),
        pytest.param(
            lambda raw: raw["external_bindings"].update(dataset_id="caller-data"),
            id="caller-data-binding",
        ),
        pytest.param(
            lambda raw: raw["capabilities"].update(qc_launch=True),
            id="qc-authority",
        ),
    ],
)
def test_correctly_rehashed_semantic_weakening_refuses(
    tmp_path: Path,
    mutate,
) -> None:
    raw = copy.deepcopy(json.loads(SPEC.read_text(encoding="utf-8")))
    mutate(raw)
    _rehash(raw)
    with pytest.raises(StockFoldManifestError, match="frozen definition"):
        _load(_write(tmp_path, raw))


@pytest.mark.parametrize(
    ("name", "replacement", "match"),
    [
        (
            "duplicate",
            ('"schema":', '"schema": "forged",\n  "schema":', 1),
            "duplicate JSON key",
        ),
        (
            "float",
            ('"train_years": 5', '"train_years": 5.0', 1),
            "binary floating-point",
        ),
        (
            "nonfinite",
            ('"train_years": 5', '"train_years": NaN', 1),
            "non-finite JSON",
        ),
    ],
)
def test_manifest_rejects_duplicate_float_and_nonfinite_json(
    tmp_path: Path,
    name: str,
    replacement: tuple[str, str, int],
    match: str,
) -> None:
    text = SPEC.read_text(encoding="utf-8")
    path = tmp_path / f"{name}.json"
    path.write_text(text.replace(*replacement), encoding="utf-8")
    with pytest.raises(StockFoldManifestError, match=match):
        _load(path)


@pytest.mark.parametrize(
    ("name", "payload", "match"),
    [
        ("bom", lambda value: b"\xef\xbb\xbf" + value, "BOM"),
        ("crlf", lambda value: value.replace(b"\n", b"\r\n"), "canonical"),
        ("leading", lambda value: b" " + value, "canonical"),
        ("trailing", lambda value: value + b" ", "canonical"),
    ],
)
def test_manifest_rejects_bom_and_noncanonical_whitespace(
    tmp_path: Path,
    name: str,
    payload,
    match: str,
) -> None:
    path = tmp_path / f"{name}.json"
    path.write_bytes(payload(SPEC.read_bytes()))
    with pytest.raises(StockFoldManifestError, match=match):
        _load(path)


def test_manifest_rejects_noncanonical_object_key_order(tmp_path: Path) -> None:
    raw = json.loads(SPEC.read_text(encoding="utf-8"))
    schema = raw.pop("schema")
    raw["schema"] = schema
    path = tmp_path / SPEC.name
    path.write_bytes(
        (json.dumps(raw, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode(
            "utf-8"
        )
    )
    with pytest.raises(StockFoldManifestError, match="canonical"):
        _load(path)


def test_manifest_rejects_escaped_lone_surrogate(tmp_path: Path) -> None:
    text = SPEC.read_text(encoding="utf-8")
    path = tmp_path / SPEC.name
    path.write_text(
        text.replace('"exchange": "XNYS"', '"exchange": "\\ud800"', 1),
        encoding="utf-8",
    )
    with pytest.raises(StockFoldManifestError, match="noncanonical"):
        _load(path)


def test_loader_provenance_copy_mutation_and_source_revalidation(
    tmp_path: Path,
) -> None:
    manifest = _load()
    copied = copy.copy(manifest)
    with pytest.raises(StockFoldManifestError, match="loader authority"):
        require_loaded_stock_fold_manifest(copied)
    with pytest.raises(TypeError):
        dataclasses.replace(manifest)

    object.__setattr__(manifest, "manifest_hash", "a" * 64)
    with pytest.raises(StockFoldManifestError, match="changed after authentication"):
        require_loaded_stock_fold_manifest(manifest)

    path = tmp_path / SPEC.name
    path.write_bytes(SPEC.read_bytes())
    loaded = _load(path)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(StockFoldManifestError):
        require_loaded_stock_fold_manifest(loaded)


@pytest.mark.parametrize(
    ("source_name", "match"),
    [
        ("stock", "stock-evaluation parent"),
        ("qc", "QC-first parent"),
    ],
)
def test_loader_revalidates_parent_source_bytes(
    tmp_path: Path,
    source_name: str,
    match: str,
) -> None:
    local_manifest, local_stock, local_qc = _copy_source_graph(tmp_path)

    loaded = load_stock_fold_manifest(
        local_manifest,
        stock_evaluation_path=local_stock,
        qc_first_plan_path=local_qc,
    )
    target = local_stock if source_name == "stock" else local_qc
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(StockFoldManifestError, match=match):
        require_loaded_stock_fold_manifest(loaded)


@pytest.mark.parametrize(
    ("source_name", "match"),
    [
        ("stock", "stock-evaluation parent artifact bytes changed"),
        ("qc", "QC-first parent artifact bytes changed"),
    ],
)
def test_loader_rejects_mutated_parent_artifact_at_initial_load(
    tmp_path: Path,
    source_name: str,
    match: str,
) -> None:
    local_manifest, local_stock, local_qc = _copy_source_graph(tmp_path)
    target = local_stock if source_name == "stock" else local_qc
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(StockFoldManifestError, match=match):
        load_stock_fold_manifest(
            local_manifest,
            stock_evaluation_path=local_stock,
            qc_first_plan_path=local_qc,
        )


def test_manifest_loader_refuses_symlink_and_toctou_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / SPEC.name
    path.write_bytes(SPEC.read_bytes())
    linked = tmp_path / "linked-folds.json"
    try:
        linked.symlink_to(path)
    except OSError:
        pass
    else:
        with pytest.raises(StockFoldManifestError, match="symlink"):
            _load(linked)

    original_read_bytes = Path.read_bytes
    resolved = path.resolve(strict=True)
    calls = 0

    def unstable_read_bytes(candidate: Path) -> bytes:
        nonlocal calls
        payload = original_read_bytes(candidate)
        if candidate.resolve(strict=False) == resolved:
            calls += 1
            if calls == 2:
                return payload + b" "
        return payload

    monkeypatch.setattr(Path, "read_bytes", unstable_read_bytes)
    with pytest.raises(StockFoldManifestError, match="changed while being read"):
        _load(path)


def test_fold_manifest_is_inside_the_outcome_free_import_closure() -> None:
    reached = validate_transitive_import_closure(ROOT)
    assert "research.analyst_revisions_v2.fold_manifest" in reached
    assert "execution" not in reached
    assert "research.acer" not in reached


def test_parent_mutation_inside_the_load_window_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-load TOCTOU window ARV2FMI-001 closed must stay closed.

    Both parents are byte-read, then their own loaders run, then the final
    ``_revalidate`` calls re-read every file. A parent rewritten after its
    loader returns is only caught by that final trio - deleting those three
    lines left this file green, so the correction had no revert-detecting
    regression. The wrapper mutates the parent immediately after its real
    loader returns, which lands inside the exact window.
    """
    local_manifest, local_stock, local_qc = _copy_source_graph(tmp_path)

    real_plan_loader = manifest_module.load_qc_first_study_plan

    def mutate_after_load(path: Path):
        plan = real_plan_loader(path)
        Path(local_qc).write_bytes(local_qc.read_bytes() + b"\n")
        return plan

    monkeypatch.setattr(
        manifest_module, "load_qc_first_study_plan", mutate_after_load
    )
    with pytest.raises(
        StockFoldManifestError, match="QC-first parent changed after authentication"
    ):
        load_stock_fold_manifest(
            local_manifest,
            stock_evaluation_path=local_stock,
            qc_first_plan_path=local_qc,
        )
    monkeypatch.undo()

    stock_window = tmp_path / "stock-window"
    stock_window.mkdir()
    local_manifest, local_stock, local_qc = _copy_source_graph(stock_window)
    real_stock_loader = manifest_module.load_stock_evaluation_contract

    def mutate_stock_after_load(path: Path, *, qc_first_plan_path: Path):
        contract = real_stock_loader(path, qc_first_plan_path=qc_first_plan_path)
        Path(local_stock).write_bytes(local_stock.read_bytes() + b"\n")
        return contract

    monkeypatch.setattr(
        manifest_module, "load_stock_evaluation_contract", mutate_stock_after_load
    )
    with pytest.raises(
        StockFoldManifestError,
        match="stock-evaluation parent changed after authentication",
    ):
        load_stock_fold_manifest(
            local_manifest,
            stock_evaluation_path=local_stock,
            qc_first_plan_path=local_qc,
        )
