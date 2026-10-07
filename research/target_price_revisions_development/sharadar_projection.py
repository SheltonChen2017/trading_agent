"""Pure, bounded status-metadata projection; no source values or authority.

Unknown descriptor siblings do not obscure known field types. Objects that
are not an exact metadata profile receive no value/component validation.
"""
from datetime import datetime, timedelta
from decimal import Decimal

FIELDS = ("table", "files", "name", "filename", "size", "sizeLabel", "size_label", "modified",
    "lastModified", "last_modified", "status", "code", "error", "message", "years", "type",
    "url", "download_url", "downloadUrl", "path", "link", "fileName", "fileSize", "bytes",
    "sizeBytes", "lastmodified", "updated", "created", "md5", "sha256", "description", "title", "key")
ROW_MARKERS = ("ticker", "permaticker", "cusips", "figi", "date", "price", "lastupdated",
    "last_updated", "open", "close", "volume", "rows", "columns")
CORE = ("name", "size", "sizeLabel", "modified")
MAX_FILES = 8


def _kind(value: object) -> str:
    return {str: "string", int: "integer", bool: "boolean", type(None): "null",
        list: "array", dict: "object", Decimal: "decimal"}.get(type(value), "unsupported")


def _components(body: dict) -> dict:
    clock_valid = False
    modified = body.get("modified")
    if type(modified) is str and 1 <= len(modified) <= 64:
        try:
            clock = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            clock_valid = clock.tzinfo is not None and clock.utcoffset() == timedelta(0)
        except ValueError:
            pass
    return {"name_valid": type(body.get("name")) is str and 1 <= len(body["name"]) <= 256,
        "size_label_valid": type(body.get("sizeLabel")) is str and 1 <= len(body["sizeLabel"]) <= 128,
        "size_valid": type(body.get("size")) is int and 0 <= body["size"] <= 10**15,
        "modified_utc_valid": clock_valid}


def _object_types(body: dict) -> dict:
    if any(type(key) is not str for key in body):
        return {"schema_refused": True}
    if any(key in ROW_MARKERS for key in body):
        return {"row_shape_refused": True}
    unknown = [key for key in body if key not in FIELDS]
    counts = {}
    for key in unknown:
        kind = _kind(body[key])
        counts[kind] = counts.get(kind, 0) + 1
    return {"fields": {key: _kind(body[key]) if key in body else "absent" for key in FIELDS},
        "unknown_key_count": len(unknown), "unknown_types": counts}


def project_metadata_shape(body: dict) -> dict:
    """Publish static-key type counts, never arbitrary names/values or rows.

    This operates on an already bounded decoded JSON object; it performs no
    I/O, credential handling, hashing, clock/size extraction or data admission.
    """
    if type(body) is not dict or any(type(key) is not str for key in body):
        raise ValueError("invalid metadata shape object")
    result = {"schema": "tpr-sharadar-projection-v1", "root": _object_types(body),
        "files": {"kind": _kind(body["files"]) if "files" in body else "absent"},
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
                # Four exact fields alone are a recognized profile. Optional
                # or unknown siblings get TYPE projection only, not validation.
                descriptor["components"] = _components(value) if set(value) == set(CORE) else None
            descriptors.append(descriptor)
    result["files"].update(length=len(files), element_types=counts,
        element_types_complete=len(files) <= MAX_FILES, unexamined_count=max(0, len(files) - MAX_FILES),
        descriptors=descriptors)
    return result
