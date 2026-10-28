"""Pure retained-Massive projection -> derived nominal events -> bound scores.

No opener, credential, provider, QC client, current-vintage identity snapshot or
order path exists. A caller needs a fresh bounded read/processing claim BEFORE
supplying real private bytes. Supplied hashes/bindings are claims, not rights,
PIT, provider completeness or native historical SID/share-basis proof.

Input schema/fields are exactly extended_source_capture._massive_projection.
Only event/firm/ticker/date/update identifiers, clipped rational contributions
and refusal metadata leave the projection function; raw target prices never do.
The existing raw_revision numeric/date/ID helpers own their exact semantics.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, time, timezone
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from research.target_price_revisions_development import raw_revision as raw_revision

STUDY = "TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1"
START, END = "2020-09-01", "2026-10-09"
MAX_PAGE_BYTES = 128 * 1024**2
MAX_ROWS = 1000
MAX_EVENTS = 386000
MAX_SECURITIES = 4096
# Public approved date/open axis; it authenticates neither native data nor PIT.
SOURCE_CALENDAR_SHA256 = "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d"
SESSION_AXIS_SHA256 = '647b16f61ea1129e6a36f341dc7de0bf5f176b478406b9a6738c80f27f475090'
PAGE_KEYS = frozenset("schema window rows source_rows row_refusals identical_duplicate_rows conflicting_duplicate_rows".split())
ROW_KEYS = frozenset(("source", "refusals", "nominal_disposition"))
DESCRIPTOR_KEYS = frozenset("request_index page name bytes sha256 fetch_utc row_count".split())
SOURCE_FIELDS = frozenset(raw_revision._RATING)
CAPTURE_REASONS = frozenset(("invalid_native_id", "invalid_native_ticker", "invalid_native_touch_order",
    "invalid_native_touch_clock", "conflicting_native_event_id"))
EVENT_KEYS = frozenset("schema event_key event_id firm_id ticker raw_issued_date last_updated_utc capture_utc source_row_sha256 source_page_sha256 source_ordinal contribution state refusals source_refusals source_nominal_disposition contribution_was_clipped historical_identity_proven raw_share_basis_unproven".split())


class EventBridgeError(ValueError):
    """Fixed body-free framing refusal; no supplied source value is exposed."""


def _fail():
    raise EventBridgeError("bounded nominal event bridge refused") from None


def canonical(value):
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False) + "\n").encode("ascii")
    except (ValueError, TypeError, OverflowError, RecursionError):
        _fail()


def _closed(value, keys):
    if type(value) is not dict or set(value) != keys:
        _fail()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail()
    return value


def _count(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _clock(value):
    try:
        return raw_revision._utc(value)
    except (raw_revision.RawRevisionError, ValueError, TypeError):
        _fail()


def _day(value):
    try:
        return raw_revision._day(value)
    except (raw_revision.RawRevisionError, ValueError, TypeError):
        _fail()


def _sid(value):
    if (type(value) is not str or not 0 < len(value) <= 128 or value.strip() != value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        _fail()
    return value


def _json(raw):
    def pairs(items):
        body = {}
        for key, value in items:
            if key in body:
                _fail()
            body[key] = value
        return body
    def number(text):
        if len(text) > 256:
            _fail()
        return int(text)
    def forbidden(_):
        _fail()
    try:
        body = json.loads(raw, object_pairs_hook=pairs, parse_int=number,
            parse_float=forbidden, parse_constant=forbidden)
        pending, nodes = [(body, 0)], 0
        while pending:
            value, depth = pending.pop(); nodes += 1
            if nodes > 20000 or depth > 8:
                _fail()
            if type(value) is dict:
                pending.extend((item, depth+1) for item in value.values())
            elif type(value) is list:
                pending.extend((item, depth+1) for item in value)
            elif type(value) is str and (len(value) > 8192 or "\x00" in value):
                _fail()
        return body
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail()


def _window(value):
    if type(value) not in (list, tuple) or len(value) != 2:
        _fail()
    start, end = map(_day, value)
    import calendar
    expected_end = "2026-10-09" if start.isoformat() == "2026-10-01" else start.replace(
        day=calendar.monthrange(start.year, start.month)[1]).isoformat()
    if start.day != 1 or not START <= start.isoformat() <= end.isoformat() <= END or end.isoformat() != expected_end:
        _fail()
    return [start.isoformat(), end.isoformat()]


def _capture_nominal(value):
    # Exact public capture-probe predicate, including its scientific-string
    # allowance. The raw signal parser can separately refuse that representation.
    if type(value) not in (str, int, Decimal) or type(value) is str and len(value) > 96:
        return False
    try:
        amount = Decimal(value)
        return (amount.is_finite() and 0 < amount <= Decimal(10**24)
            and len(amount.as_tuple().digits) <= 64 and -32 <= amount.as_tuple().exponent <= 32)
    except (ValueError, InvalidOperation, OverflowError):
        return False


def _ratio(value):
    _closed(value, frozenset(("numerator", "denominator")))
    numerator, denominator = value["numerator"], value["denominator"]
    if (type(numerator) is not str or re.fullmatch(r"0|-?[1-9][0-9]{0,160}", numerator) is None
            or type(denominator) is not str or re.fullmatch(r"[1-9][0-9]{0,160}", denominator) is None):
        _fail()
    result = Fraction(int(numerator), int(denominator))
    if abs(result) > 1 or max(result.numerator.bit_length(), result.denominator.bit_length()) > 512:
        _fail()
    return result


def _contribution(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _event_key(identity, signature):
    return hashlib.sha256(canonical([type(identity).__name__, identity, signature])).hexdigest()


def project_page(payload, *, expected_sha256, expected_bytes, window, descriptor):
    """Project only one already-retained, freshly scoped exact native page.

    Descriptor is the seven-field projection descriptor emitted by the fixed
    FAILED001 index parser. No path is opened and no old scope is renewed.
    IDs remain native typed values; every security ID remains UNBOUND here.
    """
    expected_sha256 = _hash(expected_sha256)
    if (type(payload) is not bytes or not 0 < _count(expected_bytes, MAX_PAGE_BYTES)
            or len(payload) != expected_bytes or hashlib.sha256(payload).hexdigest() != expected_sha256):
        _fail()
    window = _window(window)
    _closed(descriptor, DESCRIPTOR_KEYS)
    request = _count(descriptor["request_index"], 386)
    if (not request or _count(descriptor["page"], 63) < 0
            or descriptor["name"] != f"request.{request:04}.projection.json"
            or type(descriptor["bytes"]) is not int or descriptor["bytes"] != expected_bytes
            or descriptor["sha256"] != expected_sha256
            or descriptor["row_count"] is not None and type(descriptor["row_count"]) is not int):
        _fail()
    captured = _clock(descriptor["fetch_utc"])
    body = _json(payload)
    _closed(body, PAGE_KEYS)
    if (body["schema"] != "tpr-extended-massive-native-page-v1" or body["window"] != window
            or type(body["rows"]) is not list or len(body["rows"]) > MAX_ROWS
            or type(body["source_rows"]) is not int or body["source_rows"] != len(body["rows"])):
        _fail()
    if descriptor["row_count"] is not None and descriptor["row_count"] != len(body["rows"]):
        _fail()
    reported_duplicates = _count(body["identical_duplicate_rows"], len(body["rows"]))
    reported_conflicts = _count(body["conflicting_duplicate_rows"], len(body["rows"]))
    if reported_duplicates + reported_conflicts > len(body["rows"]):
        _fail()
    events, reason_counts, source_refused, source_conflicted, previous = [], Counter(), 0, 0, None
    local_seen, local_duplicates, local_conflicts = {}, 0, 0
    for ordinal, wrapped in enumerate(body["rows"], 1):
        _closed(wrapped, ROW_KEYS); source = wrapped["source"]
        _closed(source, SOURCE_FIELDS)
        if any(value is not None and type(value) not in (str, int, bool) for value in source.values()):
            _fail()
        issued = _day(source["date"])
        if not window[0] <= issued.isoformat() <= window[1] or previous is not None and issued < previous:
            _fail()
        previous = issued
        capture_refusals, reasons = [], []
        event_ok, firm_ok = raw_revision._native_id(source["benzinga_id"]), raw_revision._native_id(source["benzinga_firm_id"])
        if not event_ok or not firm_ok: capture_refusals.append("invalid_native_id")
        if not event_ok: reasons.append("invalid_native_event_id")
        if not firm_ok: reasons.append("invalid_firm_id")
        ticker_ok = raw_revision._ticker(source["ticker"])
        if not ticker_ok:
            capture_refusals.append("invalid_native_ticker"); reasons.append("invalid_rating_ticker")
        try:
            touched = raw_revision._utc(source["last_updated"])
            if touched.date() < issued or touched > captured:
                capture_refusals.append("invalid_native_touch_order")
                reasons.append("touch_precedes_issue_date" if touched.date() < issued else "touch_after_capture")
        except raw_revision.RawRevisionError:
            touched = None; capture_refusals.append("invalid_native_touch_clock"); reasons.append("invalid_touch_clock")
        supplied = wrapped["refusals"]
        if (type(supplied) is not list or len(supplied) > 5 or any(type(item) is not str or item not in CAPTURE_REASONS for item in supplied)
                or len(set(supplied)) != len(supplied)):
            _fail()
        captured_conflict = "conflicting_native_event_id" in supplied
        if captured_conflict:
            if not event_ok: _fail()
            capture_refusals.append("conflicting_native_event_id"); reasons.append("conflicting_native_event_id")
        if supplied != capture_refusals:
            _fail()
        nominal = _capture_nominal(source["price_target"]) and _capture_nominal(source["previous_price_target"])
        if wrapped["nominal_disposition"] != ("nominal_pair_present" if nominal else "nominal_pair_unavailable"):
            _fail()
        if source["currency"] != "USD": reasons.append("unsupported_currency")
        action = source["price_target_action"]
        if action in ("sets", "announces"): reasons.append("initiation_not_revision")
        elif action == "withdraws": reasons.append("withdrawal_not_revision")
        elif type(action) is not str or action not in ("raises", "lowers", "maintains"):
            reasons.append("unsupported_target_action")
        new, new_reason = raw_revision._number(source["price_target"])
        prior, prior_reason = raw_revision._number(source["previous_price_target"])
        if new_reason or prior_reason: reasons.append(new_reason or prior_reason)
        elif action in ("raises", "lowers", "maintains") and (new > prior) - (new < prior) != {"raises":1,"lowers":-1,"maintains":0}[action]:
            reasons.append("action_direction_conflict")
        value, clipped = None, False
        if not reasons:
            original = Fraction(new) / Fraction(prior) - 1
            value = min(Fraction(1), max(Fraction(-1), original)); clipped = original != value
        signature = hashlib.sha256(canonical(source)).hexdigest()
        if event_ok:
            key = (type(source["benzinga_id"]).__name__, source["benzinga_id"])
            if key in local_seen:
                local_duplicates += local_seen[key] == signature
                local_conflicts += local_seen[key] != signature
            else: local_seen[key] = signature
        source_refused += bool(supplied); source_conflicted += captured_conflict
        reason_counts.update(set(reasons))
        event_id = source["benzinga_id"] if event_ok else None
        events.append({"schema":"tpr-cmp28-derived-nominal-event-v1", "event_key":_event_key(event_id, signature),
            "event_id":event_id, "firm_id":source["benzinga_firm_id"] if firm_ok else None,
            "ticker":source["ticker"] if ticker_ok else None, "raw_issued_date":issued.isoformat(),
            "last_updated_utc":touched.isoformat() if touched is not None else None, "capture_utc":captured.isoformat(),
            "source_row_sha256":signature, "source_page_sha256":expected_sha256, "source_ordinal":ordinal,
            "contribution":_contribution(value) if value is not None else None,
            "state":"derived" if value is not None else "unavailable", "refusals":sorted(set(reasons)),
            "source_refusals":list(supplied), "source_nominal_disposition":wrapped["nominal_disposition"],
            "contribution_was_clipped":clipped, "historical_identity_proven":False, "raw_share_basis_unproven":True})
    if type(body["row_refusals"]) is not int or body["row_refusals"] != source_refused or source_conflicted != reported_conflicts:
        _fail()
    return {"schema":"tpr-cmp28-derived-nominal-page-v1", "study_id":STUDY,
        "descriptor":json.loads(canonical(descriptor)), "window":window, "events":events,
        "census":{"source_rows":len(events), "derived_rows":sum(row["state"]=="derived" for row in events),
            "unavailable_rows":sum(row["state"]=="unavailable" for row in events), "source_refused_rows":source_refused,
            "refusal_counts":dict(sorted(reason_counts.items())), "reported_capture_identical_duplicates":reported_duplicates,
            "reported_capture_conflicts":reported_conflicts,"observed_within_page_identical_duplicates":local_duplicates,
            "observed_within_page_conflicts":local_conflicts,"unbound_identity_rows":len(events)},
        "source_inputs_admitted":False,"provider_completeness_proven":False,"point_in_time_data":False,
        "historical_identity_proven":False,"native_share_basis_proven":False,"canonical_admission":False,
        "raw_targets_returned":False,"new_attempts":0,"new_observed_looks":0}


def _event(value):
    _closed(value, EVENT_KEYS)
    if (value["schema"] != "tpr-cmp28-derived-nominal-event-v1" or value["historical_identity_proven"] is not False
            or value["raw_share_basis_unproven"] is not True or value["state"] not in ("derived","unavailable")
            or type(value["refusals"]) is not list or type(value["source_refusals"]) is not list
            or any(type(item) is not str or not 0 < len(item) <= 80 for item in value["refusals"])
            or value["refusals"] != sorted(set(value["refusals"])) or len(value["refusals"]) > 12
            or any(type(item) is not str or item not in CAPTURE_REASONS for item in value["source_refusals"])
            or value["source_nominal_disposition"] not in ("nominal_pair_present", "nominal_pair_unavailable")
            or type(value["contribution_was_clipped"]) is not bool):
        _fail()
    for name in ("source_row_sha256","source_page_sha256","event_key"): _hash(value[name])
    if value["event_id"] is not None and not raw_revision._native_id(value["event_id"]): _fail()
    if value["firm_id"] is not None and not raw_revision._native_id(value["firm_id"]): _fail()
    if value["ticker"] is not None and not raw_revision._ticker(value["ticker"]): _fail()
    if not START <= _day(value["raw_issued_date"]).isoformat() <= END or not 1 <= _count(value["source_ordinal"],1000): _fail()
    _clock(value["capture_utc"])
    if value["last_updated_utc"] is not None: _clock(value["last_updated_utc"])
    if value["event_key"] != _event_key(value["event_id"],value["source_row_sha256"]): _fail()
    if value["state"] == "derived":
        if (value["refusals"] or value["source_refusals"] or value["event_id"] is None
                or value["firm_id"] is None or value["ticker"] is None or value["last_updated_utc"] is None
                or value["source_nominal_disposition"] != "nominal_pair_present"): _fail()
        _ratio(value["contribution"])
    elif value["contribution"] is not None or not value["refusals"]:
        _fail()
    return value


def _median(values):
    values = sorted(values); middle = len(values)//2
    return values[middle] if len(values)%2 else (values[middle-1]+values[middle])/2


def score_bound_events(events, *, sessions, decision_session, cutoff_utc, security_id_by_event, security_ids):
    """Fixed signal arithmetic over caller-supplied historical native bindings.

    Sessions are actual exchange session/open records supplied by the future
    native producer. A binding is PER EVENT VERSION, not a current-ticker map.
    No binding statement authenticates historical SID/share-basis or rights.
    Unknown/no-event names stay null and are never measured-zero substitutes.
    """
    if type(events) not in (list,tuple) or len(events)>MAX_EVENTS or type(security_id_by_event) is not dict:
        _fail()
    try: axis = raw_revision._calendar(sessions)
    except raw_revision.RawRevisionError: _fail()
    if not axis or len(axis)>2000: _fail()
    normalized_axis = [{"session_date":day.isoformat(), "open_utc":opened.isoformat()} for day,opened in axis]
    if hashlib.sha256(canonical(normalized_axis)).hexdigest() != SESSION_AXIS_SHA256: _fail()
    dates, opens = tuple(row[0] for row in axis), tuple(row[1] for row in axis)
    for day, opened in axis:
        local = opened.astimezone(ZoneInfo("America/New_York"))
        if local.date()!=day or local.time().replace(tzinfo=None)!=time(9,30): _fail()
    day, cutoff = _day(decision_session), _clock(cutoff_utc)
    if day not in dates: _fail()
    index = dates.index(day)
    local = cutoff.astimezone(ZoneInfo("America/New_York"))
    if not index or local.date()!=dates[index-1] or local.time().replace(tzinfo=None)!=time(18): _fail()
    if type(security_ids) not in (list,tuple,set,frozenset) or len(security_ids)>MAX_SECURITIES: _fail()
    inventory = tuple(_sid(sid) for sid in security_ids)
    if len(set(inventory))!=len(inventory): _fail()
    inventory = frozenset(inventory)
    rows = [_event(row) for row in events]
    keys = {row["event_key"] for row in rows}
    if len(security_id_by_event)>len(keys) or not set(security_id_by_event)<=keys: _fail()
    bindings = {key:None if sid is None else _sid(sid) for key,sid in security_id_by_event.items()}
    groups = defaultdict(list)
    for row in rows:
        event_id = row["event_id"]
        key = (type(event_id).__name__,event_id) if event_id is not None else ("unidentified",row["source_page_sha256"],row["source_ordinal"])
        groups[key].append(row)
    counts, units, seen, reasons = Counter(), defaultdict(list), Counter(), defaultdict(set)
    duplicate_rows=conflict_groups=unbound_versions=0
    static_refusals = Counter(reason for row in rows for reason in row["refusals"])
    for group_key in sorted(groups):
        group = groups[group_key]
        signatures = {row["source_row_sha256"] for row in group}
        conflict = len(signatures)>1 or any("conflicting_native_event_id" in row["source_refusals"] for row in group)
        duplicate_rows += len(group)-len(signatures)
        conflict_groups += conflict
        variants = defaultdict(list)
        for row in group: variants[row["source_row_sha256"]].append(row)
        for signature in sorted(variants):
            copies = variants[signature]
            # Same native source version cannot silently change its derived
            # arithmetic/refusals between pages. Preserve that ambiguity as
            # unknown instead of selecting the last caller-provided copy.
            metadata = {canonical({name:value for name,value in item.items() if name not in
                ("capture_utc", "source_page_sha256", "source_ordinal")}) for item in copies}
            inconsistent = len(metadata) != 1
            row = min(copies, key=lambda item: (item["capture_utc"],item["source_page_sha256"],item["source_ordinal"]))
            occurrences = len(copies)
            sid = bindings.get(row["event_key"])
            unbound_versions += sid is None
            if sid in inventory: seen[sid]+=occurrences
            issued = _day(row["raw_issued_date"])
            reason = ("conflicting_native_event_id" if conflict else "inconsistent_derived_event_metadata" if inconsistent
                else row["refusals"][0] if row["refusals"] else None)
            touched = _clock(row["last_updated_utc"]) if row["last_updated_utc"] is not None else None
            eligible = bisect_right(dates,issued)+1
            if reason is None:
                if issued>local.date():reason="issued_after_cutoff"
                elif touched.date()<issued:reason="touch_precedes_issue_date"
                elif touched>_clock(row["capture_utc"]):reason="touch_after_capture"
                elif touched>cutoff:reason="later_touch_censored"
                elif issued<dates[0]:reason="calendar_anchor_missing"
                elif eligible>=len(dates):reason="insufficient_calendar"
                elif opens[eligible]>cutoff:reason="not_yet_eligible"
                elif sid is None:reason="unbound_native_identity"
                elif sid not in inventory:reason="bound_outside_current_inventory"
                elif not 0 <= index-1-eligible <= 80:reason="outside_frozen_score_window"
            if reason is None:
                firm=(type(row["firm_id"]).__name__,row["firm_id"])
                units[(sid,firm,eligible)].append(_ratio(row["contribution"]))
                counts["accepted_distinct_events"]+=1
            else:
                counts[reason]+=occurrences
                if sid in inventory:
                    reasons[sid].update(row["refusals"])
                    reasons[sid].add(reason)
    scores = defaultdict(list)
    with localcontext(Context(prec=48,rounding=ROUND_HALF_EVEN)):
        firms = defaultdict(Decimal)
        for (sid,firm,eligible), values in units.items():
            unit = _median(values)
            decay = Decimal(2)**(-Decimal(index-1-eligible)/Decimal(20))
            firms[(sid,firm)] += Decimal(unit.numerator)/Decimal(unit.denominator)*decay
        for (sid,_), value in firms.items():scores[sid].append(value)
        values={sid:str(_median(observations)) for sid,observations in scores.items()}
    state_rows, native_scores = [], {}
    no_admissible={"issued_after_cutoff","not_yet_eligible","initiation_not_revision","withdrawal_not_revision",
        "unsupported_currency","unsupported_target_action","outside_frozen_score_window"}
    for sid in sorted(inventory):
        if sid in values:state,value="available",values[sid]
        elif not seen[sid] or reasons[sid]-no_admissible:state,value="unknown",None
        else:state,value="missing",None
        native_scores[sid]={"state":state,"value":value}
        state_rows.append({"security_id":sid,"state":state,"score":value,
            "observed_source_rows":seen[sid],"refusals":sorted(reasons[sid]) or ([] if value is not None else ["no_source_rating_rows"])})
    return {"schema":"tpr-cmp28-bound-nominal-scores-v1","study_id":STUDY,"session":decision_session,
        "cutoff_utc":cutoff.isoformat(),"scores_by_sid":native_scores,"states":state_rows,
        "census":{"source_rows":len(rows),"event_groups":len(groups),"identical_duplicate_rows":duplicate_rows,
            "conflicting_event_groups":conflict_groups,"unbound_event_versions":unbound_versions,
            "static_refusal_counts":dict(sorted(static_refusals.items())),"dispositions":dict(sorted(counts.items())),
            "scored_identities":len(values),"unknown_identities":sum(row["state"]=="unknown" for row in state_rows),
            "missing_identities":sum(row["state"]=="missing" for row in state_rows)},
        "historical_identity_proven":False,"native_share_basis_proven":False,"point_in_time_data":False,
        "session_axis_sha256":SESSION_AXIS_SHA256,"native_calendar_authenticated":False,
        "provider_completeness_proven":False,"source_inputs_admitted":False,"canonical_admission":False,
        "new_attempts":0,"new_observed_looks":0}
