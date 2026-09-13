"""Pure worker for the ARV2 QuantConnect Fundamentals discovery run.

The worker deliberately accepts already-returned ``Fundamentals`` members and
does not import LEAN.  The runtime is the only module allowed to request
``History[Fundamentals]``.  Every source member becomes exactly one accepted,
out-of-scope, or named-refusal terminal.  No price, volume, return, portfolio,
order, or result attribute is inspected.

``available_at`` is a conservative decision-clock assignment, not an alleged
Morningstar publication timestamp.  A historical snapshot which QC supplies
for a decision session is assigned one microsecond before that session's
reviewed market open.  The governing host manifest identifies this policy and
the narrower guarantee: a point-in-time census inside QC's US Fundamentals
dataset, not a universal security master or vendor revision archive.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation


CONTRACT_SHA256 = "__ARV2_FUNDAMENTAL_DISCOVERY_CONTRACT_SHA256__"
TERMINAL_SCHEMA = "arv2-qc-fundamental-universe-terminal-v1"
CENSUS_SCHEMA = "arv2-qc-fundamental-universe-session-census-v1"
AVAILABILITY_POLICY_ID = (
    "qc-morningstar-pit-session-snapshot-conservative-preopen-v1"
)
SOURCE_SCOPE_ID = "quantconnect-us-fundamentals-history-all-including-delisted-v1"

COMMON_STOCK_SECURITY_TYPE = "ST00000001"
ELIGIBLE_COUNTRY = "USA"
ELIGIBLE_EXCHANGES = {
    "ASE": "XASE",
    "NAS": "XNAS",
    "NYS": "XNYS",
}
MAX_COLLECTION_ROWS = 25_000
MAX_FIELD_CHARACTERS = 512
MAX_TERMINAL_BYTES = 16 * 1024

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_CUSIP = re.compile(r"[0-9A-Z]{9}\Z")

_FIELDS = frozenset(
    {
        "schema",
        "contract_sha256",
        "source_scope_id",
        "availability_policy_id",
        "disposition",
        "refusal_reason",
        "decision_session",
        "decision_session_ordinal",
        "decision_open_utc",
        "source_ordinal",
        "qc_security_id",
        "cusip",
        "display_ticker_non_authoritative",
        "security_id",
        "issuer_id",
        "share_class_id",
        "listing_id",
        "morningstar_company_id",
        "morningstar_investment_id",
        "cik",
        "incorporation_country",
        "security_type_code",
        "primary_exchange_id",
        "primary_exchange_mic",
        "is_depositary_receipt",
        "is_primary_share",
        "common_share_sub_type",
        "delisting_date",
        "morningstar_sector_code",
        "morningstar_industry_group_code",
        "morningstar_industry_code",
        "period_end",
        "available_at",
        "shares_outstanding",
        "identity_evidence_sha256",
        "classification_evidence_sha256",
        "share_evidence_sha256",
        "terminal_sha256",
    }
)


def _canonical(value):
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


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc(value, name):
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError(name + " is not an exact UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(name + " is not an exact UTC instant") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise ValueError(name + " is not canonical UTC microsecond text")
    return parsed


def _session(value, name):
    if type(value) is not str:
        raise ValueError(name + " is not an exact session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(name + " is not an exact session date") from exc
    if parsed.isoformat() != value:
        raise ValueError(name + " is not canonical session text")
    return parsed


def _bounded_text(value, name, *, optional=False):
    if value is None and optional:
        return None
    if type(value) is not str:
        value = str(value)
    if (
        not value
        or value != value.strip()
        or len(value) > MAX_FIELD_CHARACTERS
        or "\x00" in value
    ):
        raise ValueError(name + " is not bounded exact text")
    return value


def _decimal_text(value, name, *, positive=False):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(name + " is not an exact decimal")
    try:
        parsed = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(name + " is not an exact decimal") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise ValueError(name + " is not an admissible decimal")
    return "0" if parsed == 0 else format(parsed, "f")


def _integer(value, name):
    if type(value) is bool:
        raise ValueError(name + " is not an exact integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(name + " is not an exact integer") from exc
    if parsed <= 0 or str(parsed) != str(value):
        raise ValueError(name + " is not a positive canonical integer")
    return parsed


def _bool(value, name, *, optional=False):
    if value is None and optional:
        return None
    if type(value) is not bool:
        raise ValueError(name + " is not an exact Boolean")
    return value


def _date_text(value, name, *, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, datetime):
        result = value.date().isoformat()
    elif isinstance(value, date):
        result = value.isoformat()
    else:
        result = _bounded_text(value, name)
    return _session(result, name).isoformat()


def _read(root, path):
    value = root
    for name in path:
        value = getattr(value, name)
    return value


def _base_terminal(*, session, ordinal, opened, source_ordinal):
    return {
        "schema": TERMINAL_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "source_scope_id": SOURCE_SCOPE_ID,
        "availability_policy_id": AVAILABILITY_POLICY_ID,
        "disposition": "named_refusal",
        "refusal_reason": None,
        "decision_session": session,
        "decision_session_ordinal": ordinal,
        "decision_open_utc": opened,
        "source_ordinal": source_ordinal,
        "qc_security_id": None,
        "cusip": None,
        "display_ticker_non_authoritative": None,
        "security_id": None,
        "issuer_id": None,
        "share_class_id": None,
        "listing_id": None,
        "morningstar_company_id": None,
        "morningstar_investment_id": None,
        "cik": None,
        "incorporation_country": None,
        "security_type_code": None,
        "primary_exchange_id": None,
        "primary_exchange_mic": None,
        "is_depositary_receipt": None,
        "is_primary_share": None,
        "common_share_sub_type": None,
        "delisting_date": None,
        "morningstar_sector_code": None,
        "morningstar_industry_group_code": None,
        "morningstar_industry_code": None,
        "period_end": None,
        "available_at": None,
        "shares_outstanding": None,
        "identity_evidence_sha256": None,
        "classification_evidence_sha256": None,
        "share_evidence_sha256": None,
        "terminal_sha256": None,
    }


def _finish(row):
    semantic = dict(row)
    semantic["terminal_sha256"] = None
    row["terminal_sha256"] = _sha(semantic)
    if set(row) != _FIELDS or len(_canonical(row)) > MAX_TERMINAL_BYTES:
        raise ValueError("fundamental discovery terminal exceeds its schema bound")
    return row


def _named_refusal(row, reason):
    row["disposition"] = "named_refusal"
    row["refusal_reason"] = reason
    return _finish(row)


def _out_of_scope(row, reason):
    row["disposition"] = "out_of_scope"
    row["refusal_reason"] = reason
    return _finish(row)


def _extract_one(fundamental, *, session, ordinal, opened, source_ordinal):
    row = _base_terminal(
        session=session,
        ordinal=ordinal,
        opened=opened,
        source_ordinal=source_ordinal,
    )

    try:
        sid_raw = _read(fundamental, ("symbol", "id"))
        if sid_raw is None:
            raise ValueError("QC SecurityIdentifier is absent")
        qc_sid = _bounded_text(str(sid_raw), "QC SecurityIdentifier")
        ticker_raw = _read(fundamental, ("symbol", "value"))
        ticker = (
            None
            if ticker_raw is None or str(ticker_raw) == ""
            else _bounded_text(
                str(ticker_raw), "non-authoritative display ticker"
            )
        )
        row["qc_security_id"] = qc_sid
        row["display_ticker_non_authoritative"] = ticker
        sid_digest = hashlib.sha256(qc_sid.encode("utf-8")).hexdigest()
        row["security_id"] = "qc-sid-" + sid_digest[:32]
    except (AttributeError, TypeError, ValueError, UnicodeError):
        return _named_refusal(row, "missing_or_invalid_exact_qc_security_identifier")

    try:
        cusip = _bounded_text(_read(fundamental, ("symbol", "cusip")), "CUSIP")
        if _CUSIP.fullmatch(cusip) is None:
            raise ValueError("CUSIP is not nine alphanumeric characters")
        row["cusip"] = cusip
    except (AttributeError, TypeError, ValueError, UnicodeError):
        return _named_refusal(row, "missing_or_invalid_CUSIP_cross_vendor_join_key")

    try:
        company_reference = _read(fundamental, ("company_reference",))
        company_id_raw = getattr(company_reference, "company_id", None)
        company_id = (
            None
            if company_id_raw is None or str(company_id_raw) == ""
            else _bounded_text(company_id_raw, "Morningstar company id")
        )
        investment_id = _bounded_text(
            _read(fundamental, ("security_reference", "investment_id")),
            "Morningstar investment id",
        )
        country = _bounded_text(
            getattr(company_reference, "country_id"),
            "incorporation country",
        )
        security_type = _bounded_text(
            _read(fundamental, ("security_reference", "security_type")),
            "security type",
        )
        exchange = _bounded_text(
            getattr(company_reference, "primary_exchange_id"),
            "primary exchange",
        )
        adr = _bool(
            _read(fundamental, ("security_reference", "is_depositary_receipt")),
            "depositary-receipt flag",
        )
        primary = _bool(
            _read(fundamental, ("security_reference", "is_primary_share")),
            "primary-share flag",
            optional=True,
        )
        subtype_raw = _read(
            fundamental, ("security_reference", "common_share_sub_type")
        )
        subtype = (
            None
            if subtype_raw is None or str(subtype_raw) == ""
            else _bounded_text(subtype_raw, "common-share subtype")
        )
        cik_raw = getattr(company_reference, "cik")
        cik = None
        if cik_raw is not None and str(cik_raw).strip("0"):
            cik_candidate = str(cik_raw).strip()
            if _CIK.fullmatch(cik_candidate) is None:
                raise ValueError("CIK is not numeric")
            cik = cik_candidate.zfill(10)
        delisting_raw = _read(
            fundamental, ("security_reference", "delisting_date")
        )
        delisting = (
            None
            if delisting_raw is None
            or str(delisting_raw) in ("", "0001-01-01 00:00:00", "0001-01-01")
            else _date_text(delisting_raw, "delisting date")
        )
    except (AttributeError, TypeError, ValueError, UnicodeError, OverflowError):
        return _named_refusal(row, "missing_or_invalid_identity_or_listing_field")

    row.update(
        {
            "morningstar_company_id": company_id,
            "morningstar_investment_id": investment_id,
            "issuer_id": None,
            "share_class_id": "morningstar-investment-"
            + hashlib.sha256(investment_id.encode("utf-8")).hexdigest()[:32],
            "listing_id": "qc-listing-"
            + hashlib.sha256(
                (row["qc_security_id"] + "\x00" + exchange).encode("utf-8")
            ).hexdigest()[:32],
            "cik": cik,
            "incorporation_country": country,
            "security_type_code": security_type,
            "primary_exchange_id": exchange,
            "primary_exchange_mic": ELIGIBLE_EXCHANGES.get(exchange),
            "is_depositary_receipt": adr,
            "is_primary_share": primary,
            "common_share_sub_type": subtype,
            "delisting_date": delisting,
        }
    )
    identity = {
        key: row[key]
        for key in (
            "qc_security_id",
            "cusip",
            "security_id",
            "issuer_id",
            "share_class_id",
            "listing_id",
            "morningstar_company_id",
            "morningstar_investment_id",
            "cik",
            "incorporation_country",
            "security_type_code",
            "primary_exchange_id",
            "primary_exchange_mic",
            "is_depositary_receipt",
            "is_primary_share",
            "common_share_sub_type",
            "delisting_date",
        )
    }
    row["identity_evidence_sha256"] = _sha(identity)

    if country != ELIGIBLE_COUNTRY:
        return _out_of_scope(row, "issuer_incorporation_country_is_not_USA")
    if security_type != COMMON_STOCK_SECURITY_TYPE:
        return _out_of_scope(row, "security_type_is_not_Morningstar_common_stock")
    if adr:
        return _out_of_scope(row, "security_is_a_depositary_receipt")
    if exchange not in ELIGIBLE_EXCHANGES:
        return _out_of_scope(row, "primary_exchange_outside_XASE_XNAS_XNYS")
    issuer_key = company_id if company_id is not None else cik
    if issuer_key is None:
        return _named_refusal(row, "missing_stable_Morningstar_company_id_and_CIK")
    row["issuer_id"] = "morningstar-company-" + hashlib.sha256(
        issuer_key.encode("utf-8")
    ).hexdigest()[:32]
    row["identity_evidence_sha256"] = _sha(
        {
            key: row[key]
            for key in (
                "qc_security_id",
                "cusip",
                "security_id",
                "issuer_id",
                "share_class_id",
                "listing_id",
                "morningstar_company_id",
                "morningstar_investment_id",
                "cik",
                "incorporation_country",
                "security_type_code",
                "primary_exchange_id",
                "primary_exchange_mic",
                "is_depositary_receipt",
                "is_primary_share",
                "common_share_sub_type",
                "delisting_date",
            )
        }
    )

    try:
        sector = _integer(
            _read(fundamental, ("asset_classification", "morningstar_sector_code")),
            "Morningstar sector code",
        )
        industry_group = _integer(
            _read(
                fundamental,
                ("asset_classification", "morningstar_industry_group_code"),
            ),
            "Morningstar industry-group code",
        )
        industry = _integer(
            _read(
                fundamental, ("asset_classification", "morningstar_industry_code")
            ),
            "Morningstar industry code",
        )
    except (AttributeError, TypeError, ValueError, OverflowError):
        return _named_refusal(row, "missing_or_invalid_Morningstar_classification")
    row.update(
        {
            "morningstar_sector_code": sector,
            "morningstar_industry_group_code": industry_group,
            "morningstar_industry_code": industry,
        }
    )
    row["classification_evidence_sha256"] = _sha(
        {
            "morningstar_sector_code": sector,
            "morningstar_industry_group_code": industry_group,
            "morningstar_industry_code": industry,
            "decision_session": session,
        }
    )

    try:
        period_end = _date_text(
            _read(fundamental, ("financial_statements", "period_ending_date")),
            "fundamental period end",
        )
        shares = _decimal_text(
            _read(
                fundamental,
                ("company_profile", "share_class_level_shares_outstanding"),
            ),
            "share-class shares outstanding",
            positive=True,
        )
        available = (
            _utc(opened, "decision open") - timedelta(microseconds=1)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
    ):
        return _named_refusal(row, "missing_or_invalid_preopen_share_observation")

    row.update(
        {
            "period_end": period_end,
            "available_at": available,
            "shares_outstanding": shares,
        }
    )
    row["share_evidence_sha256"] = _sha(
        {
            key: row[key]
            for key in (
                "qc_security_id",
                "decision_session",
                "period_end",
                "available_at",
                "shares_outstanding",
            )
        }
    )
    row["disposition"] = "accepted"
    row["refusal_reason"] = None
    return _finish(row)


def build_collection_terminals(
    *, fundamentals, decision_session, decision_session_ordinal, decision_open_utc
):
    """Return one deterministic terminal for every Fundamentals member."""

    session = _session(decision_session, "decision session").isoformat()
    if type(decision_session_ordinal) is not int or decision_session_ordinal < 1:
        raise ValueError("decision session ordinal is invalid")
    opened = _utc(decision_open_utc, "decision open")
    if opened.date() != date.fromisoformat(session):
        # UTC can be the same date for the US market throughout supported dates.
        raise ValueError("decision open and session differ")
    if type(fundamentals) not in (list, tuple):
        fundamentals = list(fundamentals)
    if len(fundamentals) > MAX_COLLECTION_ROWS:
        raise ValueError("Fundamentals collection exceeds the reviewed row cap")

    rows = [
        _extract_one(
            item,
            session=session,
            ordinal=decision_session_ordinal,
            opened=decision_open_utc,
            source_ordinal=index,
        )
        for index, item in enumerate(fundamentals)
    ]
    observed_sids = [
        row["qc_security_id"] for row in rows if row["qc_security_id"] is not None
    ]
    if len(observed_sids) != len(set(observed_sids)):
        raise ValueError("Fundamentals collection repeats a QC SecurityIdentifier")
    counts = {
        disposition: sum(row["disposition"] == disposition for row in rows)
        for disposition in ("accepted", "out_of_scope", "named_refusal")
    }
    terminal_hashes = [row["terminal_sha256"] for row in rows]
    census = {
        "schema": CENSUS_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "decision_session": session,
        "decision_session_ordinal": decision_session_ordinal,
        "decision_open_utc": decision_open_utc,
        "source_member_count": len(rows),
        "terminal_count": len(rows),
        "qc_sid_bound_count": len(observed_sids),
        "accepted_count": counts["accepted"],
        "out_of_scope_count": counts["out_of_scope"],
        "named_refusal_count": counts["named_refusal"],
        "terminal_projection_sha256": _sha(
            {
                "domain": "arv2-qc-fundamental-session-terminals-v1",
                "terminal_sha256s_in_source_order": terminal_hashes,
            }
        ),
        "all_source_members_terminal": len(rows) == sum(counts.values()),
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
    }
    return rows, census


__all__ = [
    "AVAILABILITY_POLICY_ID",
    "CENSUS_SCHEMA",
    "COMMON_STOCK_SECURITY_TYPE",
    "CONTRACT_SHA256",
    "ELIGIBLE_COUNTRY",
    "ELIGIBLE_EXCHANGES",
    "MAX_COLLECTION_ROWS",
    "MAX_TERMINAL_BYTES",
    "SOURCE_SCOPE_ID",
    "TERMINAL_SCHEMA",
    "build_collection_terminals",
]
