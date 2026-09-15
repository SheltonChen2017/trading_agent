"""QC-flat exact semantic validation for ARV2 pre-open terminals.

The physical acquisition layer validates the same schema after download.  This
copy is intentionally dependency-light so an in-QuantConnect consumer can
refuse a semantically impossible but self-hashed terminal before it reaches a
process-local spool or any downstream evaluator.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

try:  # QuantConnect projects are projected as a flat source directory.
    from preopen_control_worker import BINARY_NAMES, CONTINUOUS_NAMES, CONTROL_NAMES
    from preopen_quality_worker import validate_q_data_measurement
except ImportError:  # Host tests import through the repository package.
    from research.analyst_revisions_v2.preopen_control_acquisition import (
        BINARY_CONTROL_NAMES as BINARY_NAMES,
        CONTINUOUS_CONTROL_NAMES as CONTINUOUS_NAMES,
        CONTROL_NAMES,
    )
    from research.analyst_revisions_v2_qc.preopen_quality_worker import (
        validate_q_data_measurement,
    )


class PreopenTerminalSemanticsError(ValueError):
    """A terminal differs from the exact reviewed pre-open schema."""


TERMINAL_SCHEMA = "arv2-preopen-control-terminal-v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TERMINAL_FIELDS = {
    "schema", "decision_session", "security_id", "qc_security_id", "issuer_id",
    "share_class_id", "listing_id", "security_master_row_sha256",
    "disposition", "detail_reason", "eligible_security_session",
    "q_data_measurement", "census_refusal", "input_roots", "terminal_sha256",
}
TERMINAL_FIELDS = frozenset(_TERMINAL_FIELDS)
_ELIGIBLE_FIELDS = {
    "decision_session", "security_id", "issuer_id", "share_class_id",
    "listing_id", "historical_ticker", "sector_id", "industry_id", "q_data",
    "controls", "source_id", "source_sha256", "identity_evidence_sha256",
    "identity_available_at", "classification_evidence_sha256",
    "classification_available_at", "q_data_evidence_sha256",
    "q_data_available_at", "control_evidence_sha256", "control_available_at",
    "control_vector_sha256", "point_in_time", "evidence_sha256",
    "earnings_anchor_signed_session_distance",
}
_REFUSAL_FIELDS = {
    "decision_session", "security_id", "issuer_id", "share_class_id",
    "listing_id", "historical_ticker", "reason", "source_id", "source_sha256",
    "available_at", "refusal_sha256",
}
_INPUT_ROOT_FIELDS = {
    "universe", "sid_mapping", "fundamentals", "earnings", "guidance", "ratings",
    "market_observations",
}


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PreopenTerminalSemanticsError(
            "pre-open terminal is not canonical JSON"
        ) from exc


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise PreopenTerminalSemanticsError(f"{name} is not SHA-256")
    return value


def _utc(value: object, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise PreopenTerminalSemanticsError(f"{name} is not exact UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PreopenTerminalSemanticsError(f"{name} is not exact UTC") from exc
    if (
        parsed.utcoffset() != timezone.utc.utcoffset(parsed)
        or parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value
    ):
        raise PreopenTerminalSemanticsError(f"{name} is not canonical UTC")
    return parsed


def _decision_open(session: str) -> datetime:
    try:
        parsed = date.fromisoformat(session)
    except ValueError as exc:
        raise PreopenTerminalSemanticsError(
            "output terminal decision session changed"
        ) from exc
    if parsed.isoformat() != session:
        raise PreopenTerminalSemanticsError(
            "output terminal decision session changed"
        )
    return datetime.fromisoformat(session).replace(
        hour=9, minute=30, tzinfo=ZoneInfo("America/New_York")
    ).astimezone(timezone.utc)


def _before_open(value: object, opened: datetime, name: str) -> None:
    if _utc(value, name) >= opened:
        raise PreopenTerminalSemanticsError(
            f"{name} is not strictly before decision open"
        )


def validate_preopen_terminal_semantics(row: object) -> dict[str, object]:
    """Return an exact copy after validating every nested terminal invariant."""

    if type(row) is not dict or set(row) != _TERMINAL_FIELDS:
        raise PreopenTerminalSemanticsError("output terminal fields changed")
    value = dict(row)
    if value["schema"] != TERMINAL_SCHEMA:
        raise PreopenTerminalSemanticsError("output terminal schema changed")
    for name in (
        "decision_session", "security_id", "issuer_id", "share_class_id", "listing_id"
    ):
        if type(value[name]) is not str or not value[name]:
            raise PreopenTerminalSemanticsError(f"output terminal {name} changed")
    opened = _decision_open(value["decision_session"])
    _sha(value["security_master_row_sha256"], "security master row")
    roots = value["input_roots"]
    if type(roots) is not dict or set(roots) != _INPUT_ROOT_FIELDS:
        raise PreopenTerminalSemanticsError("terminal input roots changed")
    for name, digest in roots.items():
        _sha(digest, name + " input root")
    identity = tuple(
        value[name]
        for name in (
            "decision_session", "security_id", "issuer_id", "share_class_id", "listing_id"
        )
    )
    if value["disposition"] == "accepted":
        eligible = value["eligible_security_session"]
        if (
            type(value["qc_security_id"]) is not str
            or not value["qc_security_id"]
            or value["detail_reason"] is not None
            or value["census_refusal"] is not None
            or type(value["q_data_measurement"]) is not dict
            or type(eligible) is not dict
            or set(eligible) != _ELIGIBLE_FIELDS
            or tuple(
                eligible[name]
                for name in (
                    "decision_session", "security_id", "issuer_id",
                    "share_class_id", "listing_id",
                )
            )
            != identity
            or eligible["point_in_time"] is not True
            or any(
                type(eligible[name]) is not str or not eligible[name]
                for name in ("historical_ticker", "sector_id", "industry_id", "source_id")
            )
            or type(eligible["q_data"]) is not str
            or (
                eligible["earnings_anchor_signed_session_distance"] is not None
                and type(eligible["earnings_anchor_signed_session_distance"]) is not int
            )
        ):
            raise PreopenTerminalSemanticsError(
                "accepted output terminal shape changed"
            )
        controls = eligible["controls"]
        if (
            type(controls) is not list
            or len(controls) != len(CONTROL_NAMES)
            or any(type(item) is not list or len(item) != 2 for item in controls)
            or [item[0] for item in controls] != list(CONTROL_NAMES)
        ):
            raise PreopenTerminalSemanticsError("control vector shape changed")
        for index, item in enumerate(controls):
            control = item[1]
            if index < len(CONTINUOUS_NAMES):
                if type(control) is not str:
                    raise PreopenTerminalSemanticsError(
                        "continuous control encoding changed"
                    )
                try:
                    parsed = Decimal(control)
                except InvalidOperation as exc:
                    raise PreopenTerminalSemanticsError(
                        "continuous control is not decimal"
                    ) from exc
                if not parsed.is_finite():
                    raise PreopenTerminalSemanticsError(
                        "continuous control is not finite"
                    )
            elif type(control) is not int or control not in (0, 1):
                raise PreopenTerminalSemanticsError(
                    "binary control encoding changed"
                )
        try:
            quality = Decimal(eligible["q_data"])
        except (InvalidOperation, TypeError) as exc:
            raise PreopenTerminalSemanticsError("q_data changed") from exc
        if not quality.is_finite() or not Decimal(0) <= quality <= Decimal(1):
            raise PreopenTerminalSemanticsError("q_data changed")
        for name in (
            "source_sha256", "identity_evidence_sha256",
            "classification_evidence_sha256", "q_data_evidence_sha256",
            "control_evidence_sha256", "control_vector_sha256", "evidence_sha256",
        ):
            _sha(eligible[name], name)
        for name in (
            "identity_available_at", "classification_available_at",
            "q_data_available_at", "control_available_at",
        ):
            _before_open(eligible[name], opened, name)
        opened_text = opened.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        try:
            validate_q_data_measurement(
                value["q_data_measurement"],
                value["security_id"],
                value["decision_session"],
                opened_text,
            )
        except ValueError as exc:
            raise PreopenTerminalSemanticsError(
                "q_data measurement changed"
            ) from exc
        if (
            value["q_data_measurement"]["q_data"] != eligible["q_data"]
            or value["q_data_measurement"]["evidence_sha256"]
            != eligible["q_data_evidence_sha256"]
            or value["q_data_measurement"]["available_at"]
            != eligible["q_data_available_at"]
        ):
            raise PreopenTerminalSemanticsError(
                "q_data measurement differs from eligible evidence"
            )
        if eligible["control_vector_sha256"] != hashlib.sha256(
            _canonical(controls)
        ).hexdigest():
            raise PreopenTerminalSemanticsError("control vector hash changed")
        semantic = dict(eligible)
        declared_evidence = semantic.pop("evidence_sha256")
        if declared_evidence != hashlib.sha256(_canonical(semantic)).hexdigest():
            raise PreopenTerminalSemanticsError("eligible evidence hash changed")
    elif value["disposition"] == "named_refusal":
        refusal = value["census_refusal"]
        if (
            value["qc_security_id"] is not None
            and (type(value["qc_security_id"]) is not str or not value["qc_security_id"])
        ):
            raise PreopenTerminalSemanticsError(
                "refused output QC permanent identity changed"
            )
        if (
            type(value["detail_reason"]) is not str
            or not value["detail_reason"]
            or value["eligible_security_session"] is not None
            or value["q_data_measurement"] is not None
            or type(refusal) is not dict
            or set(refusal) != _REFUSAL_FIELDS
            or tuple(
                refusal[name]
                for name in (
                    "decision_session", "security_id", "issuer_id",
                    "share_class_id", "listing_id",
                )
            )
            != identity
            or any(
                type(refusal[name]) is not str or not refusal[name]
                for name in ("historical_ticker", "reason", "source_id")
            )
        ):
            raise PreopenTerminalSemanticsError(
                "refused output terminal shape changed"
            )
        _sha(refusal["source_sha256"], "refusal source")
        _sha(refusal["refusal_sha256"], "refusal hash")
        if refusal["available_at"] is not None:
            _before_open(refusal["available_at"], opened, "refusal available_at")
        semantic = dict(refusal)
        declared_refusal = semantic.pop("refusal_sha256")
        if declared_refusal != hashlib.sha256(_canonical(semantic)).hexdigest():
            raise PreopenTerminalSemanticsError("refusal hash changed")
    else:
        raise PreopenTerminalSemanticsError("output terminal disposition changed")
    semantic = dict(value)
    declared_terminal = semantic.pop("terminal_sha256")
    _sha(declared_terminal, "terminal content hash")
    if declared_terminal != hashlib.sha256(_canonical(semantic)).hexdigest():
        raise PreopenTerminalSemanticsError("terminal content hash changed")
    return value


__all__ = (
    "PreopenTerminalSemanticsError",
    "TERMINAL_SCHEMA",
    "TERMINAL_FIELDS",
    "validate_preopen_terminal_semantics",
)
