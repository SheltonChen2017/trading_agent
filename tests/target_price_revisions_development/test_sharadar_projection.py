"""A richer pure shape projector never admits rows or emits source values."""
from decimal import Decimal
import json

import pytest

from research.target_price_revisions_development import sharadar_projection as projection

FILE = {"name": "SYNTHETIC-private.zip", "size": 1234,
        "sizeLabel": "SYNTHETIC-private-label", "modified": "2026-10-06T12:00:00Z"}


def test_unknown_descriptor_key_does_not_hide_all_known_field_types():
    result = projection.project_metadata_shape({"table": "tickers", "files": [
        dict(FILE, PRIVATE_UNKNOWN={"PRIVATE": "VALUE"})]})
    descriptor = result["files"]["descriptors"][0]
    assert descriptor["fields"]["name"] == descriptor["fields"]["modified"] == "string"
    assert descriptor["fields"]["size"] == "integer"
    assert descriptor["unknown_key_count"] == 1
    assert descriptor["unknown_types"] == {"object": 1}
    assert descriptor["components"] is None
    assert result["canonical_metadata_admission"] is False
    assert "PRIVATE" not in json.dumps(result) and "SYNTHETIC-private" not in json.dumps(result)


def test_every_file_element_type_is_visible_without_nested_traversal():
    result = projection.project_metadata_shape({"files": [None, True, 3, Decimal("1.25"), "PRIVATE", [], {}]})
    assert result["files"]["element_types"] == {
        "null": 1, "boolean": 1, "integer": 1, "decimal": 1, "string": 1, "array": 1, "object": 1}
    assert result["files"]["element_types_complete"] is True
    assert result["files"]["descriptors"][0]["index"] == 6
    assert "PRIVATE" not in json.dumps(result)


def test_aliases_are_types_only_and_do_not_invent_a_mapping():
    aliases = {key: "PRIVATE" for key in ("fileName", "fileSize", "bytes", "sizeBytes", "lastmodified",
        "updated", "created", "md5", "sha256", "description", "title", "key")}
    result = projection.project_metadata_shape({"table": "tickers", "files": [aliases]})
    descriptor = result["files"]["descriptors"][0]
    assert all(descriptor["fields"][key] == "string" for key in aliases)
    assert descriptor["unknown_key_count"] == 0 and descriptor["components"] is None
    assert result["canonical_metadata_admission"] is False
    assert "PRIVATE" not in json.dumps(result)


def test_row_marker_refuses_before_field_values_or_components(monkeypatch):
    row = {"ticker": "PRIVATE", "name": "PRIVATE", "size": 12, "modified": "PRIVATE"}
    def forbidden(_body):
        pytest.fail("row component processing")
    monkeypatch.setattr(projection, "_components", forbidden)
    result = projection.project_metadata_shape({"files": [row]})
    assert result["files"]["element_types"] == {"object": 1}
    descriptor = result["files"]["descriptors"][0]
    assert descriptor == {"index": 0, "row_shape_refused": True}
    assert "PRIVATE" not in json.dumps(result)


def test_unknown_descriptor_is_types_only_even_with_plausible_metadata(monkeypatch):
    def forbidden(_body):
        pytest.fail("unrecognized descriptor value processing")
    monkeypatch.setattr(projection, "_components", forbidden)
    result = projection.project_metadata_shape({"files": [dict(FILE, PRIVATE_UNKNOWN="PRIVATE")]})
    assert result["files"]["descriptors"][0]["components"] is None


def test_root_row_refusal_stops_file_component_processing(monkeypatch):
    def forbidden(_body):
        pytest.fail("root row refusal failed to stop component processing")
    monkeypatch.setattr(projection, "_components", forbidden)
    result = projection.project_metadata_shape({"ticker": "SYNTHETIC", "files": [FILE]})
    assert result["root"] == {"row_shape_refused": True}
    assert result["files"] == {"kind": "array"}
    assert result["canonical_metadata_admission"] is False


def test_nested_data_rows_are_never_traversed():
    result = projection.project_metadata_shape({"data": [{"ticker": "PRIVATE", "price": 123}],
        "files": [{"metadata": {"ticker": "PRIVATE", "price": 123}}]})
    assert result["root"]["unknown_types"] == {"array": 1}
    assert result["files"]["descriptors"][0]["unknown_types"] == {"object": 1}
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("change, component", [
    ({"size": True}, "size_valid"), ({"size": -1}, "size_valid"),
    ({"size": Decimal("1234")}, "size_valid"), ({"name": ""}, "name_valid"),
    ({"sizeLabel": ""}, "size_label_valid"), ({"modified": "2026-10-06T12:00:00"}, "modified_utc_valid"),
])
def test_only_exact_profile_gets_non_authorizing_component_validation(change, component):
    result = projection.project_metadata_shape({"files": [dict(FILE, **change)]})
    assert result["files"]["descriptors"][0]["components"][component] is False
    assert result["canonical_metadata_admission"] is False


def test_exact_profile_component_truth_still_grants_no_canonical_authority():
    result = projection.project_metadata_shape({"table": "tickers", "files": [FILE]})
    assert all(result["files"]["descriptors"][0]["components"].values())
    assert result["canonical_metadata_admission"] is False
    assert result["raw_retention"] is False
    assert "SYNTHETIC-private" not in json.dumps(result)


def test_array_budget_explicitly_reports_unexamined_entries():
    result = projection.project_metadata_shape({"files": [FILE] * 9})
    assert result["files"]["length"] == 9
    assert result["files"]["element_types"] == {"object": 8}
    assert result["files"]["element_types_complete"] is False
    assert result["files"]["unexamined_count"] == 1


@pytest.mark.parametrize("body", [None, [], {1: "PRIVATE"}])
def test_non_json_root_refuses(body):
    with pytest.raises(ValueError, match="metadata shape"):
        projection.project_metadata_shape(body)
