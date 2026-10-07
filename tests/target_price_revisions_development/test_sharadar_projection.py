"""Bounded status schema names and validated metadata never admit rows."""
from decimal import Decimal
import json

import pytest

from research.target_price_revisions_development import sharadar_projection as projection

FILE = {"name": "SYNTHETIC-private.zip", "size": 1234,
        "sizeLabel": "SYNTHETIC-private-label", "modified": "2026-10-06T12:00:00Z"}


def test_unknown_descriptor_key_does_not_hide_all_known_field_types():
    result = projection.project_metadata_shape({"table": "tickers", "files": [
        dict(FILE, extension={"PRIVATE": "VALUE"})]})
    descriptor = result["files"]["descriptors"][0]
    assert descriptor["fields"]["name"] == descriptor["fields"]["modified"] == "string"
    assert descriptor["fields"]["size"] == "integer"
    assert descriptor["unknown_key_count"] == 1
    assert descriptor["unknown_types"] == {"object": 1}
    assert all(descriptor["components"].values())
    assert descriptor["known_components"]["modified"] is True
    assert "extension" in descriptor["schema_identifiers"]
    assert descriptor["metadata_candidate"]["refusal"] == "unknown_fields"
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
    assert descriptor["unknown_key_count"] == 0
    assert descriptor["known_components"]["fileName"] is True
    assert descriptor["known_components"]["fileSize"] is False
    assert descriptor["metadata_candidate"]["recognized"] is False
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


def test_unknown_descriptor_values_are_not_validated_but_known_components_remain_visible():
    class Uninspected:
        def __str__(self):
            pytest.fail("unknown value converted")
        def __len__(self):
            pytest.fail("unknown value measured")
    result = projection.project_metadata_shape({"files": [dict(FILE, extension=Uninspected())]})
    descriptor = result["files"]["descriptors"][0]
    assert all(descriptor["components"].values())
    assert descriptor["unknown_types"] == {"unsupported": 1}
    assert descriptor["metadata_candidate"]["recognized"] is False


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
    assert result["files"]["descriptors"][0]["fields"]["metadata"] == "object"
    assert result["files"]["descriptors"][0]["metadata_candidate"]["refusal"] == "nested_descriptor"
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("change, component", [
    ({"size": True}, "size_valid"), ({"size": -1}, "size_valid"),
    ({"size": Decimal("1234")}, "size_valid"), ({"name": ""}, "name_valid"),
    ({"sizeLabel": ""}, "size_label_valid"), ({"modified": "2026-10-06T12:00:00"}, "modified_utc_valid"),
])
def test_known_component_validation_never_admits_invalid_metadata(change, component):
    result = projection.project_metadata_shape({"files": [dict(FILE, **change)]})
    assert result["files"]["descriptors"][0]["components"][component] is False
    assert result["canonical_metadata_admission"] is False


def test_exact_profile_component_truth_still_grants_no_canonical_authority():
    result = projection.project_metadata_shape({"table": "tickers", "files": [FILE]})
    assert all(result["files"]["descriptors"][0]["components"].values())
    assert result["canonical_metadata_admission"] is False
    assert result["raw_retention"] is False
    assert "SYNTHETIC-private" not in json.dumps(result)
    assert result["files"]["descriptors"][0]["metadata_candidate"] == {
        "recognized": True, "refusal": None, "name_field": "name", "size_field": "size",
        "clock_field": "modified", "size_bytes": 1234, "snapshot_utc": "2026-10-06T12:00:00+00:00"}


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


@pytest.mark.parametrize("clock_alias", ["date", "last_updated", "lastupdated", "updated_at", "timestamp"])
def test_timestamp_alias_alone_is_not_a_market_row(clock_alias):
    file = {"filename": "PRIVATE", "bytes": 1234, clock_alias: "2026-10-06T12:00:00Z"}
    descriptor = projection.project_metadata_shape({"files": [file]})["files"]["descriptors"][0]
    assert descriptor["known_components"][clock_alias] is True
    assert descriptor["clock_formats"][clock_alias] == "iso_utc"
    assert descriptor["metadata_candidate"]["recognized"] is True


@pytest.mark.parametrize("clock, kind, valid", [
    ("2026-10-06T12:00:00Z", "iso_utc", True),
    ("2026-10-06T12:00:00+01:00", "iso_non_utc", False),
    ("2026-10-06T12:00:00", "iso_naive", False),
    (1789992000, "integer_epoch_seconds", True),
    (1789992000000, "integer_epoch_milliseconds", True),
    ("1789992000", "numeric_string", False),
    (1, "integer_out_of_range", False),
    (True, "other", False),
    (Decimal("1789992000"), "non_integer_number", False),
    ("PRIVATE", "other", False),
])
def test_clock_format_has_no_raw_value_or_unit_guess(clock, kind, valid):
    descriptor = projection.project_metadata_shape({"files": [dict(FILE, modified=clock)]})["files"]["descriptors"][0]
    assert descriptor["clock_formats"] == {"modified": kind}
    assert descriptor["known_components"]["modified"] is valid
    assert descriptor["metadata_candidate"]["recognized"] is valid
    assert "PRIVATE" not in json.dumps(descriptor)


@pytest.mark.parametrize("change", [
    {"filename": "PRIVATE"}, {"bytes": 1234}, {"date": "2026-10-06T12:00:00Z"},
    {"error": False}, {"status": "ok"}, {"code": 200},
])
def test_ambiguous_aliases_and_application_fields_never_extract_metadata(change):
    candidate = projection.project_metadata_shape({"files": [dict(FILE, **change)]})["files"]["descriptors"][0]["metadata_candidate"]
    assert candidate["recognized"] is False
    assert candidate["size_bytes"] is candidate["snapshot_utc"] is None


def test_safe_schema_identifier_names_are_bounded_and_non_identifier_names_suppressed():
    descriptor = dict(FILE, extension="PRIVATE", **{
        "https://PRIVATE/": "PRIVATE", "PRIVATE KEY": "PRIVATE", "é": "PRIVATE", "x" * 65: "PRIVATE"})
    result = projection.project_metadata_shape({"files": [descriptor]})
    projected = result["files"]["descriptors"][0]
    assert projected["schema_identifiers"] == ["extension", "modified", "name", "size", "sizeLabel"]
    assert projected["schema_identifiers_complete"] is True
    assert projected["suppressed_identifier_count"] == 4
    assert "PRIVATE" not in json.dumps(result)


def test_schema_identifier_limit_is_explicit_and_prevents_value_extraction():
    descriptor = dict(FILE, **{"extra_" + str(index): "PRIVATE" for index in range(40)})
    projected = projection.project_metadata_shape({"files": [descriptor]})["files"]["descriptors"][0]
    assert len(projected["schema_identifiers"]) == 32
    assert projected["schema_identifiers_complete"] is False
    assert projected["unexamined_identifier_count"] == 12
    assert projected["metadata_candidate"]["recognized"] is False
    assert "PRIVATE" not in json.dumps(projected)


@pytest.mark.parametrize("row_marker", ["ticker", "permaticker", "figi", "cusips", "open", "close", "volume", "rows", "columns"])
def test_row_descriptors_never_emit_schema_names(row_marker):
    result = projection.project_metadata_shape({"files": [dict(FILE, **{row_marker: "PRIVATE"})]})
    assert result["files"]["descriptors"] == [{"index": 0, "row_shape_refused": True}]


def test_multi_file_response_prevents_selection_without_hiding_per_file_structure():
    result = projection.project_metadata_shape({"files": [FILE, FILE]})
    assert len(result["files"]["descriptors"]) == 2
    assert result["selected_metadata"] == {"recognized": False, "refusal": "files_not_singleton"}


@pytest.mark.parametrize("marker", ["TICKER", "Permaticker", "VOLUME"])
def test_row_marker_case_cannot_publish_schema_or_metadata(marker):
    descriptor = projection.project_metadata_shape({"files": [dict(FILE, **{marker: "PRIVATE"})]})["files"]["descriptors"][0]
    assert descriptor == {"index": 0, "row_shape_refused": True}


@pytest.mark.parametrize("table", ["sf1", "TICKERS", None, True])
def test_contradictory_optional_descriptor_table_prevents_metadata_selection(table):
    result = projection.project_metadata_shape({"table": "tickers", "files": [dict(FILE, table=table)]})
    assert result["selected_metadata"]["recognized"] is False
    assert result["selected_metadata"]["refusal"] == "descriptor_table_mismatch"


def test_closed_alias_profile_with_matching_optional_table_is_explicit():
    result = projection.project_metadata_shape({"table": "tickers", "files": [{
        "table": "tickers", "filename": "PRIVATE", "size_bytes": 1234,
        "last_updated": 1789992000000, "download_url": "https://PRIVATE"}]})
    assert result["selected_metadata"]["recognized"] is True
    assert result["selected_metadata"]["size_field"] == "size_bytes"
    assert result["selected_metadata"]["clock_field"] == "last_updated"
    assert result["selected_metadata"]["size_bytes"] == 1234
    assert "PRIVATE" not in json.dumps(result)
