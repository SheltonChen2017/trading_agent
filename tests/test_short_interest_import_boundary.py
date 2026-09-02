"""Hard boundary between official short interest and daily short-sale volume."""
from __future__ import annotations

import ast
import copy
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

import research.short_interest_etf as canonical_package
from research.short_interest_etf.availability import snapshot_execution_cohort
from research.short_interest_etf.contracts import ShortInterestContractError
from research.short_interest_etf.daily_short_volume import (
    DailyShortSaleVolumeRecord,
    DailyVolumeSemantic,
)
from research.short_interest_etf.dataset import (
    ShortInterestDatasetError,
    build_identity,
    build_vintage,
    load_synthetic_fixture,
)
from research.short_interest_etf.normalize import (
    REFUSAL_DAILY_SHORT_VOLUME,
    REFUSAL_DUPLICATE_SOURCE_RECORD,
    REFUSAL_INVALID_SNAPSHOT,
    normalize_snapshot_payloads,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "short_interest_etf"
    / "official_style_v1.json"
)
PACKAGE_ROOT = Path(__file__).parents[1] / "research" / "short_interest_etf"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _daily_volume() -> DailyShortSaleVolumeRecord:
    return DailyShortSaleVolumeRecord(
        semantic=DailyVolumeSemantic.DAILY_SHORT_SALE_VOLUME,
        trade_date="2024-01-12",
        ticker="SYN",
        short_sale_volume=400,
        total_volume=1000,
        source_id="synthetic-daily-volume",
        source_version="1",
        raw_record_sha256="dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    )


def test_daily_short_volume_type_is_not_exported_by_canonical_package():
    assert "DailyShortSaleVolumeRecord" not in canonical_package.__all__
    assert not hasattr(canonical_package, "DailyShortSaleVolumeRecord")


def test_daily_short_volume_object_cannot_enter_snapshot_or_availability_boundary():
    vintage = load_synthetic_fixture(FIXTURE)
    daily = _daily_volume()
    with pytest.raises(ShortInterestDatasetError, match="daily short-sale volume"):
        build_vintage(
            replace(
                vintage.manifest,
                requested_record_count=1,
                input_row_count=1,
                accepted_record_count=1,
            ),
            vintage.release_calendar,
            (daily,),
        )
    with pytest.raises(ShortInterestContractError, match="daily volume is forbidden"):
        snapshot_execution_cohort(daily, vintage.release_calendar[0])


def test_daily_short_volume_row_gets_named_refusal_not_field_coercion():
    daily_payload = _daily_volume().to_payload()
    accepted, refusals = normalize_snapshot_payloads([daily_payload])
    assert accepted == ()
    assert len(refusals) == 1
    assert refusals[0].reason == REFUSAL_DAILY_SHORT_VOLUME


def test_every_duplicate_source_identity_is_explicitly_refused():
    row = _payload()["snapshot_rows"][0]
    original = copy.deepcopy(row)
    accepted, refusals = normalize_snapshot_payloads([row, copy.deepcopy(row)])
    assert accepted == ()
    assert len(refusals) == 2
    assert {item.reason for item in refusals} == {
        REFUSAL_DUPLICATE_SOURCE_RECORD
    }
    assert row == original


def test_malformed_rows_are_named_and_never_silently_dropped():
    good = _payload()["snapshot_rows"][0]
    bad = copy.deepcopy(good)
    bad["source_record_id"] = "malformed-row"
    bad.pop("denominator")
    accepted, refusals = normalize_snapshot_payloads([good, bad, 42])
    assert len(accepted) == 1
    assert len(refusals) == 2
    assert all(item.reason == REFUSAL_INVALID_SNAPSHOT for item in refusals)
    assert len(accepted) + len(refusals) == 3


def test_daily_volume_refusal_is_bound_into_immutable_identity():
    vintage = load_synthetic_fixture(FIXTURE)
    accepted, refusals = normalize_snapshot_payloads([_daily_volume().to_payload()])
    manifest = replace(
        vintage.manifest,
        requested_record_count=1,
        input_row_count=1,
        accepted_record_count=0,
        refusal_count=1,
    )
    refused_vintage = build_vintage(
        manifest, vintage.release_calendar, accepted, refusals
    )
    identity = build_identity(refused_vintage)
    assert identity["snapshot_count"] == 0
    assert identity["refusal_count"] == 1


def test_lane_package_has_no_provider_outcome_or_authority_imports():
    allowed_modules = {
        "__future__",
        "bisect",
        "collections",
        "copy",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "fractions",
        "json",
        "pathlib",
        "re",
        "types",
        "typing",
        "zoneinfo",
        "data.exchange_calendar",
        "data.financial_primitives",
        "data.hashing",
        "ml.immutable_io",
    }
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name in allowed_modules or alias.name.startswith(
                        "research.short_interest_etf."
                    )
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, "relative imports are not approved"
                assert node.module is not None
                assert node.module in allowed_modules or node.module.startswith(
                    "research.short_interest_etf."
                )


def test_canonical_modules_never_import_daily_short_volume_module():
    for path in PACKAGE_ROOT.rglob("*.py"):
        if path.name == "daily_short_volume.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(
                    alias.name.endswith(".daily_short_volume")
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                assert all(
                    alias.name != "daily_short_volume" for alias in node.names
                )
                if node.module:
                    assert not node.module.endswith(".daily_short_volume")


def test_snapshot_subclass_cannot_substitute_for_the_exact_canonical_type():
    """Both boundaries require the exact type, not merely an instance of it.

    ``isinstance`` would admit a subclass that overrides validated behaviour --
    an availability property, a denominator, or ``to_payload`` -- and carry
    non-canonical semantics into the immutable dataset under a canonical name.
    The daily-volume record is a separate class, so it is rejected either way;
    only a subclass distinguishes the exact-type rule from ``isinstance`` and
    keeps that deliberate predicate mutation-sensitive.
    """
    vintage = load_synthetic_fixture(FIXTURE)
    genuine = vintage.snapshots[0]

    class SubclassedSnapshot(type(genuine)):
        pass

    impostor = SubclassedSnapshot(
        **{field.name: getattr(genuine, field.name) for field in fields(genuine)}
    )
    assert isinstance(impostor, type(genuine))
    assert type(impostor) is not type(genuine)

    with pytest.raises(ShortInterestDatasetError, match="exact ShortInterestSnapshot"):
        build_vintage(
            vintage.manifest, vintage.release_calendar, (impostor,)
        )
    with pytest.raises(ShortInterestContractError, match="daily volume is forbidden"):
        snapshot_execution_cohort(impostor, vintage.release_calendar[0])
