"""Supplied-evidence event clock, ordinary-share exceptions and PIT context.

These pure validators do not retrieve prices or authenticate a trust root.
Their hash arguments are externally established application trust boundaries.
All returned values describe the supplied evidence, not a granted research look.
The old provisional XML classifier and daily-close candidate stay unchanged.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from functools import lru_cache

from research.insider_buying.backtest_evidence_pipeline import _calendar, _utc
from research.insider_buying.form4_xml import _common_stock
from data.hashing import canonical_json, hash_bytes, hash_payload


VERSION = "insider-backtest-event-clock-v2"
MAX_BYTES = 128 * 1024 * 1024  # Full eligible-US-universe preceding-60-session frame.
MAX_EXCEPTION_BYTES = 8 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN = re.compile(r"\b(?:restricted|phantom|preferred|depositary|adr|option|warrant|unit|units|rsu|rsus|award)\b", re.I | re.ASCII)
_ORDINARY = re.compile(r"(?:class [a-z0-9]{1,2} )?(?:ordinary shares|common shares)", re.I | re.ASCII)


class EventClockError(ValueError):
    """A supplied clock, title or context does not meet the exact contract."""


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise EventClockError("REFUSED: " + why)


def _keys(value, names: set[str], label: str) -> dict:
    _require(type(value) is dict and set(value) == names, label + " fields differ")
    return value


def _decode(raw: bytes, digest: str, schema: str, scope: str) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "unbounded evidence")
    _require(type(digest) is str and _SHA.fullmatch(digest) is not None and hash_bytes(raw) == digest,
             "evidence differs from external root")
    _require(type(scope) is str and scope in {"fixture", "production"}, "unknown trust scope")
    def pairs(items):
        result = {}
        for key, val in items:
            _require(key not in result, "duplicate JSON field")
            result[key] = val
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_require(False, "nonfinite JSON")))
    except EventClockError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EventClockError("REFUSED: malformed evidence JSON") from exc
    _require(type(value) is dict and value.get("schema") == schema and value.get("trust_scope") == scope,
             "evidence schema or scope differs")
    _require(canonical_json(value).encode("utf-8") == raw, "noncanonical evidence encoding")
    return value


def _day(value) -> str:
    _require(type(value) is str, "session must be exact text")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise EventClockError("REFUSED: invalid session") from exc
    _require(parsed.isoformat() == value, "noncanonical date")
    return value


def _decimal(value, label: str, *, nonnegative: bool = False) -> Decimal:
    _require(type(value) is str and 0 < len(value) <= 64 and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) is not None,
             label + " must be plain exact decimal text")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise EventClockError("REFUSED: invalid " + label) from exc
    _require(result.is_finite() and (result >= 0 if nonnegative else result > 0),
             label + " is nonpositive/nonfinite")
    return result


def schedule_first_open(*, available_at_utc: str, calendar_raw: bytes,
                        calendar_sha256: str, trust_scope: str,
                        horizons: tuple[int, ...] = (5, 20, 60)) -> dict:
    """Literal first regular open STRICTLY AFTER exact public availability.

    An acceptance exactly at the open cannot use that same instant. Pre-open
    acceptance may use that day's open, unlike the old daily-close candidate.
    No date-only precision, inferred holiday calendar or clamped horizon.
    """
    calendar = _decode(calendar_raw, calendar_sha256, "insider-backtest-calendar-v1", trust_scope)
    sessions, opens, _, digest = _calendar(calendar)
    accepted = _utc(available_at_utc)
    _require(type(horizons) is tuple and horizons == (5, 20, 60)
             and all(type(x) is int for x in horizons), "frozen descriptive/primary horizons differ")
    _require(accepted >= opens[0] - timedelta(days=1), "calendar does not bracket availability")
    first = next((n for n, instant in enumerate(opens) if instant > accepted), None)
    _require(first is not None and first > 0, "missing earlier calendar context or next open")
    _require(opens[first - 1] <= accepted, "calendar cannot prove this is the first open")
    _require(first + max(horizons) < len(sessions), "incomplete frozen horizons")
    _require(sessions[first] >= "2006-01-01", "event before frozen source history")
    exits = {str(n): {"session": sessions[first + n], "open_utc": opens[first + n].strftime("%Y-%m-%dT%H:%M:%SZ")} for n in horizons}
    body = {"kind": VERSION, "trust_scope": trust_scope, "available_at_utc": available_at_utc,
            "calendar_artifact_sha256": calendar_sha256, "calendar_sessions_sha256": digest,
            "entry_session": sessions[first], "entry_open_utc": opens[first].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "exit_opens": exits, "primary_horizon_sessions": 20,
            "literal_first_open_after_acceptance": True, "research_looks": 0, "qc_jobs": 0}
    body["sha256"] = hash_payload(body)
    return body


@lru_cache(maxsize=4)
def _exception_records(raw: bytes, digest: str, scope: str) -> tuple:
    """Cache only immutable, byte/root-bound validation, never caller objects."""
    _require(type(raw) is bytes and len(raw) <= MAX_EXCEPTION_BYTES, "exception dictionary exceeds its separate byte bound")
    body = _decode(raw, digest, "insider-common-equity-exceptions-v2", scope)
    _keys(body, {"schema", "trust_scope", "exceptions"}, "exception dictionary")
    records = body["exceptions"]
    _require(type(records) is list and len(records) <= 20_000, "unbounded exception dictionary")
    fields = {"issuer_cik", "qc_symbol_id", "security_title", "share_class", "security_class", "first_session", "last_session", "knowledge_at_utc"}
    seen = set()
    for item in records:
        _keys(item, fields, "exception")
        _require(all(type(item[key]) is str and 0 < len(item[key]) <= 128
                     and item[key].isascii() and item[key].isprintable() and item[key] == item[key].strip()
                     for key in fields), "exception has invalid bounded text field")
        _require(re.fullmatch(r"[0-9]{10}", item["issuer_cik"]) is not None and int(item["issuer_cik"]) > 0,
                 "invalid exception issuer")
        _require(item["security_class"] == "common_stock" and item["share_class"] and item["qc_symbol_id"], "nonordinary exception")
        _require(_ORDINARY.fullmatch(item["security_title"]) is not None and _FORBIDDEN.search(item["security_title"]) is None,
                 "unsupported exception title")
        _require(_day(item["first_session"]) < _day(item["last_session"]), "exception interval invalid")
        _utc(item["knowledge_at_utc"])
        key = tuple(item[k] for k in sorted(fields - {"knowledge_at_utc"}))
        _require(key not in seen, "duplicate exception")
        seen.add(key)
    return tuple(tuple(sorted(item.items())) for item in records)


def verify_common_equity_exceptions(*, raw: bytes, digest: str, scope: str) -> dict:
    records = _exception_records(raw, digest, scope)
    return {"schema": "insider-common-equity-exceptions-v2", "trust_scope": scope,
            "exceptions": [dict(record) for record in records]}


def classify_pit_common_equity(*, transaction: dict, mapping: dict,
                              exception_dictionary_raw: bytes, exception_dictionary_sha256: str,
                              trust_scope: str, available_at_utc: str) -> dict:
    """Override ONLY the provisional non-common-title reason, never another filter.

    Ordinary/common-share spellings need an exact externally anchored issuer,
    title, share-class, SID and validity/knowledge-time dictionary entry. Known
    restricted/ADR/preferred/derivative titles never become ordinary shares.
    """
    _keys(transaction, {"event_id", "issuer_cik", "security_title_raw", "transaction_date", "outcomes"}, "classification transaction")
    _keys(mapping, {"issuer_cik", "qc_symbol_id", "security_title", "share_class", "security_class", "country", "venue",
                    "mapping_first_session", "mapping_last_session", "knowledge_at_utc"}, "classification mapping")
    records = [dict(item) for item in _exception_records(exception_dictionary_raw, exception_dictionary_sha256, trust_scope)]
    title = transaction["security_title_raw"]
    outcomes = transaction["outcomes"]
    _require(type(outcomes) is list and all(type(x) is str for x in outcomes) and outcomes,
             "classification outcomes absent")
    _require(type(title) is str and 0 < len(title) <= 128 and title == title.strip() and title.isascii(), "invalid original title")
    filed = _day(transaction["transaction_date"])
    accepted = _utc(available_at_utc)
    _require(mapping["issuer_cik"] == transaction["issuer_cik"] and mapping["security_title"] == title,
             "exact issuer/title mapping differs")
    _require(mapping["security_class"] == "common_stock" and mapping["country"] == "US"
             and mapping["venue"] in {"XNAS", "XNYS", "XASE"}, "mapping is not ordinary US equity")
    _require(_day(mapping["mapping_first_session"]) <= filed < _day(mapping["mapping_last_session"])
             and _utc(mapping["knowledge_at_utc"]) <= accepted, "mapping unavailable for original transaction")
    overridden = False
    if outcomes == ["exclude_non_common_stock"] and _ORDINARY.fullmatch(title) is not None and _FORBIDDEN.search(title) is None:
        matching = [item for item in records if all(item[k] == mapping[k] for k in
                    ("issuer_cik", "qc_symbol_id", "security_title", "share_class", "security_class"))
                    and item["first_session"] <= filed < item["last_session"] and _utc(item["knowledge_at_utc"]) <= accepted]
        _require(len(matching) == 1, "ordinary-share title lacks unique PIT exception")
        overridden = True
    eligible = (outcomes == ["eligible_for_lot_aggregation"] and _common_stock(title)) or overridden
    return {"event_id": transaction["event_id"], "eligible_for_lot_aggregation": eligible,
            "original_outcomes": list(outcomes), "ordinary_share_exception_applied": overridden,
            "exception_dictionary_sha256": exception_dictionary_sha256, "qc_symbol_id": mapping["qc_symbol_id"],
            "trust_scope": trust_scope, "research_looks": 0}


def verify_pit_stock_context(*, context_raw: bytes, context_sha256: str, trust_scope: str,
                             calendar_raw: bytes, calendar_sha256: str,
                             decision_session: str, decision_cutoff_utc: str,
                             expected_security_ids: tuple[str, ...]) -> dict:
    """Exact preceding 60 sessions for every security, including no-filing stocks.

    Missing history is not a zero or a liquidity exclusion. Genuine complete
    histories below price/ADV thresholds retain named exclusions. Values must
    be known by the decision and precede its session, so current-session/future
    bars cannot leak into the stock eligibility/context tests.
    """
    body = _decode(context_raw, context_sha256, "insider-stock-context-v2", trust_scope)
    _keys(body, {"schema", "trust_scope", "calendar_sha256", "decision_session", "rows"}, "stock context")
    calendar = _decode(calendar_raw, calendar_sha256, "insider-backtest-calendar-v1", trust_scope)
    sessions, opens, closes, calendar_digest = _calendar(calendar)
    _require(body["calendar_sha256"] == calendar_sha256 and body["decision_session"] == decision_session,
             "context calendar/decision binding differs")
    _require(type(expected_security_ids) is tuple and expected_security_ids
             and all(type(x) is str and x for x in expected_security_ids)
             and tuple(sorted(set(expected_security_ids))) == expected_security_ids
             and len(expected_security_ids) <= 20_000, "security universe absent, duplicate or reordered")
    _require(decision_session in sessions, "decision not in calendar")
    index = sessions.index(decision_session)
    cutoff = _utc(decision_cutoff_utc)
    _require(index >= 60 and opens[index] <= cutoff <= closes[index], "decision lacks prior context or valid cutoff")
    prior = sessions[index - 60:index]
    records = body["rows"]
    _require(type(records) is list and len(records) == len(expected_security_ids), "complete context universe differs")
    result = []
    for sid, item in zip(expected_security_ids, records, strict=True):
        _keys(item, {"qc_symbol_id", "history"}, "security context")
        _require(item["qc_symbol_id"] == sid and type(item["history"]) is list and len(item["history"]) == 60,
                 "context identity/history count differs")
        dollars, prices = [], []
        for day, bar in zip(prior, item["history"], strict=True):
            _keys(bar, {"session", "raw_close_usd", "volume_shares", "knowledge_at_utc"}, "context bar")
            _require(bar["session"] == day and closes[sessions.index(day)] <= _utc(bar["knowledge_at_utc"]) <= cutoff,
                     "context bar missing, reordered, premature or future")
            price = _decimal(bar["raw_close_usd"], "raw close")
            volume = _decimal(bar["volume_shares"], "volume", nonnegative=True)
            with localcontext() as ctx:
                ctx.prec = 160
                dollars.append(price * volume)
            prices.append(price)
        with localcontext() as ctx:
            ctx.prec = 160
            adv = sum(dollars[-20:], Decimal(0)) / Decimal(20)
        reasons = []
        if prices[-1] < Decimal(5):
            reasons.append("stock_price_below_5_usd")
        if adv < Decimal(2_000_000):
            reasons.append("stock_20_session_mean_dollar_volume_below_2m_usd")
        result.append({"qc_symbol_id": sid, "price_usd": str(prices[-1]), "adv20_usd": str(adv),
                       "history_sessions": 60, "eligible": not reasons, "exclusion_reasons": reasons})
    output = {"kind": "insider-pit-stock-context-result-v2", "trust_scope": trust_scope,
              "context_sha256": context_sha256, "calendar_sessions_sha256": calendar_digest,
              "decision_session": decision_session, "decision_cutoff_utc": decision_cutoff_utc,
              "rows": result, "research_looks": 0, "qc_jobs": 0}
    output["sha256"] = hash_payload(output)
    return output


def verify_pit_stock_context_v3(*, context_raw: bytes, context_sha256: str, trust_scope: str,
                              calendar_raw: bytes, calendar_sha256: str,
                              decision_session: str, decision_cutoff_utc: str,
                              expected_security_ids: tuple[str, ...]) -> dict:
    """Complete PIT context with externally bound first-listing provenance.

    A verified young listing requires EVERY supplied-calendar session from its
    first listing through the preceding close. Fewer than 60 sessions gives a
    named exclusion, never an invented zero or missing-data imputation. Older
    listings still require the exact latest 60 bars under unchanged v2 rules.
    Structured document/record/vintage roots do not authenticate their source;
    a mapping's first interval is deliberately not listing-age evidence.
    """
    body = _decode(context_raw, context_sha256, "insider-stock-context-v3", trust_scope)
    _keys(body, {"schema", "trust_scope", "calendar_sha256", "decision_session", "rows"}, "v3 stock context")
    calendar = _decode(calendar_raw, calendar_sha256, "insider-backtest-calendar-v1", trust_scope)
    sessions, opens, closes, calendar_digest = _calendar(calendar)
    _require(body["calendar_sha256"] == calendar_sha256 and body["decision_session"] == decision_session,
             "v3 context calendar/decision binding differs")
    _require(type(expected_security_ids) is tuple and expected_security_ids
             and all(type(sid) is str and sid for sid in expected_security_ids)
             and tuple(sorted(set(expected_security_ids))) == expected_security_ids
             and len(expected_security_ids) <= 20_000, "v3 security universe absent, duplicate or reordered")
    _require(decision_session in sessions, "v3 decision not in calendar")
    index = sessions.index(decision_session)
    cutoff = _utc(decision_cutoff_utc)
    _require(index >= 60 and opens[index] <= cutoff <= closes[index], "v3 decision lacks prior context or valid cutoff")
    date_index = {day: position for position, day in enumerate(sessions)}
    records = body["rows"]
    _require(type(records) is list and len(records) == len(expected_security_ids), "complete v3 context universe differs")
    listing_fields = {"schema", "trust_scope", "qc_symbol_id", "country", "venue", "security_class", "first_listing_session",
        "source_authority", "source_document_sha256", "source_record_id", "source_record_sha256", "source_vintage_sha256",
        "source_publication_utc", "knowledge_at_utc", "listing_history_complete", "predecessor_listing_status"}
    result, mature, listing_facts = {}, [], {}
    latest = None
    for sid, item in zip(expected_security_ids, records, strict=True):
        _keys(item, {"qc_symbol_id", "history", "first_listing_evidence", "first_listing_evidence_sha256"}, "v3 security context")
        _require(item["qc_symbol_id"] == sid and type(item["history"]) is list, "v3 context identity/history differs")
        evidence = _keys(item["first_listing_evidence"], listing_fields, "first-listing evidence")
        _require(all(type(evidence[key]) is str and 0 < len(evidence[key]) <= 128
                     and evidence[key].isascii() and evidence[key].isprintable()
                     and evidence[key] == evidence[key].strip()
                     for key in listing_fields - {"listing_history_complete"}),
                 "first-listing evidence has invalid bounded text fields")
        _require(type(item["first_listing_evidence_sha256"]) is str
                 and _SHA.fullmatch(item["first_listing_evidence_sha256"]) is not None
                 and hash_payload(evidence) == item["first_listing_evidence_sha256"],
                 "first-listing structured evidence differs from pinned row hash")
        _require(evidence["schema"] == "insider-pit-first-listing-evidence-v1"
                 and evidence["trust_scope"] == trust_scope and evidence["qc_symbol_id"] == sid
                 and evidence["country"] == "US" and evidence["venue"] in {"XNAS", "XNYS", "XASE"}
                 and evidence["security_class"] == "common_stock", "first-listing identity/classification differs")
        allowed_authorities = {"invented-first-listing-record"} if trust_scope == "fixture" else {
            "official-exchange-first-listing-record", "licensed-security-master-first-listing-vintage"}
        _require(evidence["source_authority"] in allowed_authorities,
                 "first-listing provenance is not the declared distinct fixture/production profile")
        _require(type(evidence["listing_history_complete"]) is bool and evidence["listing_history_complete"] is True
                 and evidence["predecessor_listing_status"] == "verified-no-predecessor-listing",
                 "first-listing history is incomplete, false or has unresolved predecessor listings")
        record_id = evidence["source_record_id"]
        _require(type(record_id) is str and 0 < len(record_id) <= 128 and record_id.isascii()
                 and record_id.isprintable() and record_id == record_id.strip(), "first-listing source record ID is unbounded/invalid")
        for key in ("source_document_sha256", "source_record_sha256", "source_vintage_sha256"):
            _require(type(evidence[key]) is str and _SHA.fullmatch(evidence[key]) is not None,
                     "first-listing document/record/vintage digest absent or invalid")
        first = _day(evidence["first_listing_session"])
        _require(first <= decision_session and (first < sessions[0] or first in date_index),
                 "first listing is future or not a bound trading-calendar session")
        knowledge, published = _utc(evidence["knowledge_at_utc"]), _utc(evidence["source_publication_utc"])
        _require(published <= knowledge < cutoff, "first-listing publication/knowledge is premature, simultaneous or future")
        latest = max(latest or knowledge, knowledge)
        start = max(date_index.get(first, 0), index-60)
        required_history = sessions[start:index]
        _require(len(item["history"]) == len(required_history), "v3 complete first-listing history count differs")
        prices, dollars = [], []
        for day, bar in zip(required_history, item["history"], strict=True):
            _keys(bar, {"session", "raw_close_usd", "volume_shares", "knowledge_at_utc"}, "v3 context bar")
            instant = _utc(bar["knowledge_at_utc"])
            _require(bar["session"] == day and closes[date_index[day]] <= instant < cutoff,
                     "v3 history bar missing, reordered, premature, simultaneous or future")
            price, volume = _decimal(bar["raw_close_usd"], "raw close"), _decimal(bar["volume_shares"], "volume", nonnegative=True)
            with localcontext() as arithmetic:
                arithmetic.prec = 160
                dollars.append(price * volume)
            prices.append(price)
            latest = max(latest, instant)
        facts = {"first_listing_session": first,
                 "first_listing_evidence_sha256": item["first_listing_evidence_sha256"],
                 "first_listing_knowledge_at_utc": evidence["knowledge_at_utc"],
                 "prior_listing_session_lower_bound": index-date_index.get(first, 0)}
        listing_facts[sid] = facts
        if len(required_history) == 60:
            mature.append({"qc_symbol_id": sid, "history": item["history"]})
        else:
            with localcontext() as arithmetic:
                arithmetic.prec = 160
                adv = str(sum(dollars[-20:], Decimal(0)) / Decimal(20)) if len(dollars) >= 20 else None
            result[sid] = {"qc_symbol_id": sid, **facts, "price_usd": str(prices[-1]) if prices else None,
                "adv20_usd": adv, "history_sessions": len(required_history), "eligible": False,
                "exclusion_reasons": ["insufficient_60_session_history"]}
    if mature:
        converted = canonical_json({"schema": "insider-stock-context-v2", "trust_scope": trust_scope,
            "calendar_sha256": calendar_sha256, "decision_session": decision_session, "rows": mature}).encode("utf-8")
        mature_result = verify_pit_stock_context(context_raw=converted, context_sha256=hash_bytes(converted), trust_scope=trust_scope,
            calendar_raw=calendar_raw, calendar_sha256=calendar_sha256, decision_session=decision_session,
            decision_cutoff_utc=decision_cutoff_utc, expected_security_ids=tuple(item["qc_symbol_id"] for item in mature))
        for item in mature_result["rows"]:
            result[item["qc_symbol_id"]] = {**item, **listing_facts[item["qc_symbol_id"]]}
    output = {"kind": "insider-pit-stock-context-result-v3", "trust_scope": trust_scope,
        "context_sha256": context_sha256, "calendar_sessions_sha256": calendar_digest,
        "decision_session": decision_session, "decision_cutoff_utc": decision_cutoff_utc,
        "rows": [result[sid] for sid in expected_security_ids],
        "latest_prerequisite_knowledge_at_utc": latest.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first_listing_provenance_authenticated_here": False, "source_authenticated_here": False,
        "rights_authenticated_here": False, "look_authority": False, "research_looks": 0, "qc_jobs": 0}
    output["sha256"] = hash_payload(output)
    return output
