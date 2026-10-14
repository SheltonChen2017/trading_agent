"""Synthetic values follow measured schema; no captured response is retained."""
from dataclasses import asdict
import json

import pytest

from research.target_price_revisions_development.sharadar_metadata import parse_status_metadata


def fixture():
    return {"table": "tickers", "files": [{"available": True, "history": "invented",
        "historyLabel": "invented", "key": "fixture-key", "name": "fixture-name",
        "size": 123, "sizeLabel": "invented", "modified": "2025-01-01T00:00:00Z"}]}


def test_observed_schema_maps_without_retaining_identifiers_or_granting_authority():
    result = asdict(parse_status_metadata(fixture()))
    assert result["size_bytes"] == 123 and result["snapshot_utc"] == "2025-01-01T00:00:00+00:00"
    assert result["entitlement_proven"] is result["canonical_admission"] is result["point_in_time_data"] is False
    assert "fixture-" not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("size", True), ("size", -1), ("size", 1.5),
    ("modified", "2025-01-01T00:00:00"), ("modified", 1735689600), ("key", []),
    ("history", {}), ("available", "true"), ("name", ""), ("sizeLabel", None)])
def test_bad_values_refuse(field, value):
    body = fixture(); body["files"][0][field] = value
    with pytest.raises(ValueError):
        parse_status_metadata(body)


@pytest.mark.parametrize("mutation", [lambda b: b.update(table="sep"),
    lambda b: b["files"].append(b["files"][0]), lambda b: b["files"][0].update(ticker="PRIVATE"),
    lambda b: b["files"][0].pop("key"), lambda b: b.update(error="PRIVATE")])
def test_schema_drift_refuses(mutation):
    body = fixture(); mutation(body)
    with pytest.raises(ValueError):
        parse_status_metadata(body)


def test_auxiliary_flag_is_not_an_entitlement_switch():
    body = fixture(); body["files"][0]["available"] = False
    assert parse_status_metadata(body).entitlement_proven is False
