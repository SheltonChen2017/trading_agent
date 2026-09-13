"""Pure validation for physical ARV2 q-data measurements."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

QUALITY_METHOD_ID = "arv2-qdata-conservative-min-v1"
QUALITY_COMPONENT_ORDER = (
    "timestamp_quality",
    "firm_label_mapping_quality",
    "security_entity_mapping_quality",
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value):
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal(value, name):
    if type(value) is not str:
        raise ValueError(name + " is not canonical decimal text")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(name + " is not canonical decimal text") from exc
    canonical = "0" if parsed == 0 else format(parsed, "f")
    if (
        not parsed.is_finite() or canonical != value
        or not Decimal(0) <= parsed <= Decimal(1)
    ):
        raise ValueError(name + " is not canonical quality")
    return parsed


def _utc(value, name):
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError(name + " is not exact UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(name + " is not exact UTC") from exc
    if (
        parsed.utcoffset() != timezone.utc.utcoffset(parsed)
        or parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value
    ):
        raise ValueError(name + " is not canonical UTC")
    return parsed


def _sha(value, name):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError(name + " is not SHA-256")


def validate_q_data_measurement(value, security_id, session, opened):
    fields = {
        "security_id", "measured_session", "source_id", "source_sha256",
        "components", "measurement_method_id", "q_data", "available_at",
        "evidence_sha256", "point_in_time",
    }
    if (
        type(value) is not dict or set(value) != fields
        or value.get("security_id") != security_id
        or value.get("measured_session") != session
        or value.get("measurement_method_id") != QUALITY_METHOD_ID
        or value.get("point_in_time") is not True
        or type(value.get("source_id")) is not str or not value["source_id"]
    ):
        raise ValueError("q_data measurement identity or schema changed")
    _sha(value.get("source_sha256"), "q_data source")
    components = value.get("components")
    if (
        type(components) is not list
        or [item.get("kind") if type(item) is dict else None for item in components]
        != list(QUALITY_COMPONENT_ORDER)
    ):
        raise ValueError("q_data components are missing, duplicated, or reordered")
    values = []
    clocks = []
    component_fields = {
        "kind", "value", "source_id", "source_sha256", "payload_sha256",
        "available_at", "point_in_time", "accepted_risk_non_pristine",
        "evidence_sha256",
    }
    for index, component in enumerate(components):
        if (
            set(component) != component_fields
            or type(component.get("source_id")) is not str
            or not component["source_id"]
            or component.get("point_in_time") is not (index != 0)
            or component.get("accepted_risk_non_pristine") is not (index == 0)
        ):
            raise ValueError("q_data component schema changed")
        for name in ("source_sha256", "payload_sha256", "evidence_sha256"):
            _sha(component.get(name), "q_data component " + name)
        semantic = dict(component)
        declared = semantic.pop("evidence_sha256")
        if declared != _hash(semantic):
            raise ValueError("q_data component hash changed")
        values.append(_decimal(component["value"], "q_data component"))
        clocks.append(_utc(component["available_at"], "q_data component clock"))
    quality = _decimal(value.get("q_data"), "q_data")
    available = _utc(value.get("available_at"), "q_data available_at")
    if (
        quality != min(values) or available != max(clocks)
        or available >= _utc(opened, "decision open")
    ):
        raise ValueError("q_data formula or availability changed")
    _sha(value.get("evidence_sha256"), "q_data evidence")
    semantic = dict(value)
    declared = semantic.pop("evidence_sha256")
    if declared != _hash(semantic):
        raise ValueError("q_data aggregate hash changed")
    return value


__all__ = [
    "QUALITY_COMPONENT_ORDER", "QUALITY_METHOD_ID",
    "validate_q_data_measurement",
]
