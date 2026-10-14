"""Pure status-schema projection; extracted file metadata grants no authority.

Direct schema identifier names are deliberately visible, bounded to ASCII
identifiers. A provider could use a value-like identifier as a key; this is
schema evidence, not a guarantee that arbitrary provider keys lack meaning.
Credential echo rejection belongs to the wrapper before this pure projection.
No filenames, URLs, arbitrary values or nested object keys are published.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re

FIELDS = ("table", "files", "name", "filename", "size", "sizeLabel", "size_label", "modified",
    "lastModified", "last_modified", "status", "code", "error", "message", "years", "type",
    "url", "download_url", "downloadUrl", "path", "link", "fileName", "fileSize", "bytes",
    "sizeBytes", "lastmodified", "updated", "created", "md5", "sha256", "description", "title", "key",
    "file_name", "file_size", "file_size_bytes", "size_bytes", "content_length", "contentLength",
    "last_updated", "lastupdated", "date", "modified_at", "updated_at", "created_at",
    "lastUpdate", "last_update", "timestamp", "metadata", "format", "compression", "version")
ROW_MARKERS = ("ticker", "permaticker", "cusips", "figi", "price", "open", "close", "volume", "rows", "columns")
NAME_FIELDS = ("name", "filename", "fileName", "file_name")
SIZE_FIELDS = ("size", "fileSize", "bytes", "sizeBytes", "file_size", "file_size_bytes", "size_bytes",
    "content_length", "contentLength")
LABEL_FIELDS = ("sizeLabel", "size_label")
CLOCK_FIELDS = ("modified", "lastModified", "last_modified", "lastmodified", "updated", "created",
    "last_updated", "lastupdated", "date", "modified_at", "updated_at", "created_at", "lastUpdate",
    "last_update", "timestamp")
MAX_FILES = 8
MAX_SCHEMA_IDENTIFIERS = 32
EPOCH_SECONDS_MIN = 946684800
EPOCH_SECONDS_MAX = 4102444800


def _kind(value: object) -> str:
    return {str: "string", int: "integer", bool: "boolean", type(None): "null",
        list: "array", dict: "object", Decimal: "decimal"}.get(type(value), "unsupported")


def _clock(value: object) -> tuple[str, str | None]:
    """Classify units prospectively; normalize only explicit UTC/plausible ints."""
    if type(value) is int:
        if EPOCH_SECONDS_MIN <= value < EPOCH_SECONDS_MAX:
            clock = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=value)
            return "integer_epoch_seconds", clock.isoformat()
        if EPOCH_SECONDS_MIN * 1000 <= value < EPOCH_SECONDS_MAX * 1000:
            clock = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=value)
            return "integer_epoch_milliseconds", clock.isoformat()
        return "integer_out_of_range", None
    if type(value) in (Decimal, float):
        return "non_integer_number", None
    if type(value) is str and 1 <= len(value) <= 64:
        if re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", value):
            return "numeric_string", None
        try:
            clock = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if clock.tzinfo is None:
                return "iso_naive", None
            if clock.utcoffset() != timedelta(0):
                return "iso_non_utc", None
            if not 2000 <= clock.year < 2100:
                return "iso_out_of_range", None
            return "iso_utc", clock.isoformat()
        except (ValueError, OverflowError):
            pass
    return "other", None


def _known_components(body: dict) -> dict:
    valid = {}
    for key in NAME_FIELDS + SIZE_FIELDS + LABEL_FIELDS + CLOCK_FIELDS:
        if key not in body:
            continue
        value = body[key]
        if key in NAME_FIELDS:
            valid[key] = type(value) is str and 1 <= len(value) <= 256
        elif key in LABEL_FIELDS:
            valid[key] = type(value) is str and 1 <= len(value) <= 128
        elif key in SIZE_FIELDS:
            valid[key] = type(value) is int and 0 <= value <= 10**15
        else:
            valid[key] = _clock(value)[1] is not None
    return valid


def _components(body: dict) -> dict:
    valid = _known_components(body)
    def unique(fields):
        found = [field for field in fields if field in body]
        return len(found) == 1 and valid[found[0]]
    return {"name_valid": unique(NAME_FIELDS), "size_label_valid": unique(LABEL_FIELDS),
        "size_valid": unique(SIZE_FIELDS), "modified_utc_valid": unique(CLOCK_FIELDS)}


def _object_types(body: dict) -> dict:
    if any(type(key) is not str for key in body):
        return {"schema_refused": True}
    if any(key.lower() in ROW_MARKERS for key in body):
        return {"row_shape_refused": True}
    unknown = [key for key in body if key not in FIELDS]
    counts = {}
    for key in unknown:
        kind = _kind(body[key])
        counts[kind] = counts.get(kind, 0) + 1
    identifiers = sorted(key for key in body if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key))
    return {"fields": {key: _kind(body[key]) if key in body else "absent" for key in FIELDS},
        "unknown_key_count": len(unknown), "unknown_types": counts,
        "schema_identifiers": identifiers[:MAX_SCHEMA_IDENTIFIERS],
        "schema_identifiers_complete": len(identifiers) <= MAX_SCHEMA_IDENTIFIERS,
        "unexamined_identifier_count": max(0, len(identifiers) - MAX_SCHEMA_IDENTIFIERS),
        "suppressed_identifier_count": len(body) - len(identifiers)}


def _metadata_candidate(body: dict, projected: dict) -> dict:
    result = {"recognized": False, "refusal": None, "name_field": None, "size_field": None,
        "clock_field": None, "size_bytes": None, "snapshot_utc": None}
    if any(key in body for key in ("code", "status", "error", "message")):
        result["refusal"] = "application_fields"
    elif "table" in body and (type(body["table"]) is not str or body["table"] != "tickers"):
        result["refusal"] = "descriptor_table_mismatch"
    elif projected["unknown_key_count"] or not projected["schema_identifiers_complete"]:
        result["refusal"] = "unknown_fields"
    elif any(type(value) in (dict, list) for value in body.values()):
        result["refusal"] = "nested_descriptor"
    else:
        groups = [[field for field in fields if field in body] for fields in (NAME_FIELDS, SIZE_FIELDS, CLOCK_FIELDS)]
        labels = [field for field in LABEL_FIELDS if field in body]
        if any(len(group) != 1 for group in groups) or len(labels) > 1:
            result["refusal"] = "missing_or_ambiguous_alias"
        elif (not all(projected["known_components"][group[0]] for group in groups)
                or any(not projected["known_components"][field] for field in labels)):
            result["refusal"] = "invalid_component"
        else:
            name, size, clock = (group[0] for group in groups)
            result.update(recognized=True, name_field=name, size_field=size, clock_field=clock,
                size_bytes=body[size], snapshot_utc=_clock(body[clock])[1])
    return result


def project_metadata_shape(body: dict) -> dict:
    """Publish bounded schema names/types plus validated file metadata only.

    The caller bounds JSON and rejects credential echoes first. Date fields
    alone are metadata candidates, not sufficient evidence of market rows.
    Unknown values and nested keys are never traversed or semantically read.
    """
    if type(body) is not dict or any(type(key) is not str for key in body):
        raise ValueError("invalid metadata shape object")
    result = {"schema": "tpr-sharadar-projection-v2", "root": _object_types(body),
        "files": {"kind": _kind(body["files"]) if "files" in body else "absent"},
        "selected_metadata": {"recognized": False, "refusal": "files_not_singleton"},
        "canonical_metadata_admission": False, "raw_retention": False}
    if result["root"].get("row_shape_refused") or result["root"].get("schema_refused"):
        return result
    files = body.get("files")
    if type(files) is not list:
        return result
    counts, descriptors = {}, []
    for index, value in enumerate(files[:MAX_FILES]):
        kind = _kind(value)
        counts[kind] = counts.get(kind, 0) + 1
        if type(value) is dict:
            descriptor = {"index": index, **_object_types(value)}
            if "fields" in descriptor:
                descriptor["known_components"] = _known_components(value)
                descriptor["components"] = _components(value)
                descriptor["clock_formats"] = {key: _clock(value[key])[0] for key in CLOCK_FIELDS if key in value}
                descriptor["metadata_candidate"] = _metadata_candidate(value, descriptor)
            descriptors.append(descriptor)
    result["files"].update(length=len(files), element_types=counts,
        element_types_complete=len(files) <= MAX_FILES, unexamined_count=max(0, len(files) - MAX_FILES),
        descriptors=descriptors)
    if len(files) == 1 and len(descriptors) == 1:
        if set(body) != {"table", "files"} or type(body["table"]) is not str or body["table"] != "tickers":
            result["selected_metadata"] = {"recognized": False, "refusal": "root_contract_unmapped"}
        elif "metadata_candidate" not in descriptors[0]:
            result["selected_metadata"] = {"recognized": False, "refusal": "descriptor_refused"}
        else:
            result["selected_metadata"] = dict(descriptors[0]["metadata_candidate"])
    return result
