"""Pure continuous raw-revision frames; no file/provider/outcome opener.

The immutable raw normalizer's reason precedence and exact score arithmetic
are preserved, with cached calendar eligibility and global event groups.
Signal action history begins at the frozen source warm-up, as in the original
bounded source-window candidate, and never resets between years. Older captured
actions remain audit inputs, not new unbounded historical signal economics.
Supplied source completeness and current identity claims are not authenticated.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
from zoneinfo import ZoneInfo

from research.target_price_revisions_development import raw_revision as raw

STUDY_ID = "TPR-CAP-TILT-EXT26-20261010-v1"
FREEZE_SHA256 = "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067"
CALENDAR_SHA256 = "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d"
SOURCE_START, SOURCE_END = "2020-09-01", "2026-10-09"
MAX_RATINGS, MAX_IDENTITIES, MAX_ACTIONS = 2048000, 640000, 1280000
NO_ADMISSIBLE = frozenset({"issued_after_cutoff", "not_yet_eligible",
    "initiation_not_revision", "withdrawal_not_revision", "unsupported_currency",
    "unsupported_target_action"})


class SignalError(ValueError):
    """Closed source framing refusal, without licensed values."""


def _fail():
    raise SignalError("invalid bounded continuous raw signal input")


def canonical(body):
    try:
        return (json.dumps(body, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    except (ValueError, TypeError, OverflowError):
        _fail()


def _rows(value, keys, bound):
    if type(value) is not list or len(value) > bound:
        _fail()
    for row in value:
        try:
            raw._schema(row, keys)
        except raw.RawRevisionError:
            _fail()
    return value


def identity_inventory(native, rating_tickers):
    """Resolve collisions on the FULL supplied snapshot before relevant filtering."""
    native = _rows(native, {"ticker", "permaticker", "figi", "category", "exchange", "isdelisted"}, MAX_IDENTITIES)
    rows = []
    for row in native:
        if row["isdelisted"] not in ("Y", "N") or type(row["permaticker"]) is not str:
            _fail()
        rows.append({**row, "security_id": "SHARADAR:" + row["permaticker"],
                     "isdelisted": row["isdelisted"] == "Y"})
    try:
        mapping, ambiguous = raw._identity_map(rows, raw.SHARADAR_IDENTITY_POLICY)
    except raw.RawRevisionError:
        _fail()
    by_id, result, reasons = {}, [], {}
    for ticker in sorted(rating_tickers):
        alternatives = mapping.get(ticker, {})
        if not alternatives:
            continue  # Explicit unmatched counts are retained by build_frames.
        for row in alternatives.values():
            sid = row["security_id"]
            if sid in by_id and by_id[sid] != ticker:
                _fail()  # Never choose one alias for a source identity.
            by_id[sid] = ticker
            reason = ("ambiguous_snapshot_identity" if len(alternatives) != 1 or ticker in ambiguous
                      else raw._identity_reason(row, raw.SHARADAR_IDENTITY_POLICY))
            reasons[ticker] = reason
    for sid, ticker in sorted(by_id.items()):
        reason = reasons[ticker]
        result.append({"security_id": sid, "ticker": ticker, "eligible": reason is None,
                       "reason": reason or "eligible_snapshot_identity"})
    if not result or len(result) > 100000:
        _fail()
    return mapping, ambiguous, result, reasons


def _median(values):
    values = sorted(values)
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def _cache(groups, mapping, ambiguous, days, opens):
    cached = []
    for key in sorted(groups):
        group = groups[key]
        row = min(group, key=raw._signature)
        reason = None
        if len({raw._signature(item) for item in group}) != 1:
            reason = "conflicting_native_event_id"
        elif not raw._ticker(row["ticker"]):
            reason = "invalid_rating_ticker"
        elif not raw._native_id(row["benzinga_firm_id"]):
            reason = "invalid_firm_id"
        try:
            issued = raw._day(row["date"])
        except raw.RawRevisionError:
            issued, reason = None, reason or "invalid_issued_date"
        try:
            touched = raw._utc(row["last_updated"])
        except raw.RawRevisionError:
            touched, reason = None, reason or "invalid_touch_clock"
        later_reason, identity, ratio = None, None, None
        if row["currency"] != "USD":
            later_reason = "unsupported_currency"
        new, new_reason = raw._number(row["price_target"])
        prior, prior_reason = raw._number(row["previous_price_target"])
        action = row["price_target_action"]
        if later_reason is None:
            if action in ("sets", "announces"):
                later_reason = "initiation_not_revision"
            elif action == "withdraws":
                later_reason = "withdrawal_not_revision"
            elif type(action) is not str or action not in ("raises", "lowers", "maintains"):
                later_reason = "unsupported_target_action"
            elif new_reason or prior_reason:
                later_reason = new_reason or prior_reason
            elif (new > prior) - (new < prior) != {"raises": 1, "lowers": -1, "maintains": 0}[action]:
                later_reason = "action_direction_conflict"
        if later_reason is None:
            alternatives = mapping.get(row["ticker"], {})
            if not alternatives:
                later_reason = "missing_snapshot_identity"
            elif len(alternatives) != 1 or row["ticker"] in ambiguous:
                later_reason = "ambiguous_snapshot_identity"
            else:
                identity = next(iter(alternatives.values()))
                later_reason = raw._identity_reason(identity, raw.SHARADAR_IDENTITY_POLICY)
        if later_reason is None:
            ratio = min(Fraction(1), max(Fraction(-1), Fraction(new) / Fraction(prior) - 1))
        eligible = bisect_right(days, issued) + 1 if issued is not None else None
        eligible = eligible if eligible is not None and eligible < len(days) else None
        cached.append((row, len(group), reason, issued, touched, later_reason,
                       identity, ratio, eligible))
    return cached


def build_frames(ratings, native_identities, actions, *, calendar_payload, capture_utc):
    """Complete301-frame census, with global dedup/actions and no yearly reset.

    This computes signals only. Caller must prove fresh input bytes, source
    pagination completeness, actual producer custody and private read authority.
    """
    if type(calendar_payload) is not bytes or hashlib.sha256(calendar_payload).hexdigest() != CALENDAR_SHA256:
        _fail()
    calendar = json.loads(calendar_payload)
    dates = calendar["warmup_sessions"] + calendar["valuation_sessions"]
    days = [date.fromisoformat(day) for day in dates]
    opens = [datetime.combine(day, time(9, 30), ZoneInfo("America/New_York")) for day in days]
    capture = raw._utc(capture_utc)
    if capture.date().isoformat() < SOURCE_END:
        _fail()
    ratings = _rows(ratings, raw._RATING, MAX_RATINGS)
    groups, tickers = {}, set()
    for row in ratings:
        if not raw._native_id(row["benzinga_id"]):
            _fail()
        key = (type(row["benzinga_id"]).__name__, str(row["benzinga_id"]))
        groups.setdefault(key, []).append(row)
        if raw._ticker(row["ticker"]):
            tickers.add(row["ticker"])
    mapping, ambiguous, identities, identity_reasons = identity_inventory(native_identities, tickers)
    cached = _cache(groups, mapping, ambiguous, days, opens)
    action_rows, older_actions = [], 0
    for row in _rows(actions, {"ticker", "date", "action", "contraticker"}, MAX_ACTIONS):
        if not raw._ticker(row["ticker"]):
            _fail()
        day = raw._day(row["date"])
        if day.isoformat() > SOURCE_END:
            _fail()
        if day.isoformat() < SOURCE_START:
            older_actions += 1
        else:
            action_rows.append((day, row["ticker"], row["action"]))
    action_rows.sort(key=lambda row: (row[0], row[1], str(row[2])))
    frames, normalization, exclusions, nonshare_counts, action_cursor = [], [], set(), defaultdict(int), 0
    with localcontext(Context(prec=48, rounding=ROUND_HALF_EVEN)):
        for decision in calendar["decisions"]:
            cutoff = raw._utc(decision["cutoff"])
            index = dates.index(decision["session"])
            while action_cursor < len(action_rows) and action_rows[action_cursor][0] <= cutoff.date():
                _, ticker, kind = action_rows[action_cursor]
                if type(kind) is str and kind in raw._NONSHARE_ACTIONS:
                    nonshare_counts[kind] += 1
                else:
                    exclusions.add(ticker)
                action_cursor += 1
            units, by_ticker, counts, accepted = defaultdict(list), defaultdict(set), defaultdict(int), 0
            for row, occurrences, initial, issued, touched, later, identity, ratio, eligible in cached:
                reason = initial
                if reason is None:
                    if issued > cutoff.date(): reason = "issued_after_cutoff"
                    elif touched.date() < issued: reason = "touch_precedes_issue_date"
                    elif touched > capture: reason = "touch_after_capture"
                    elif touched > cutoff: reason = "later_touch_censored"
                reason = reason or later
                if reason is None and row["ticker"] in exclusions:
                    reason = "corporate_action_ambiguity"
                if reason is None:
                    if days[0] > issued: reason = "calendar_anchor_missing"
                    elif eligible is None: reason = "insufficient_calendar"
                    elif opens[eligible] > cutoff: reason = "not_yet_eligible"
                if reason is None:
                    accepted += 1
                    age = index - 1 - eligible
                    if 0 <= age <= 80:
                        firm = (type(row["benzinga_firm_id"]).__name__, row["benzinga_firm_id"])
                        units[(identity["security_id"], firm, eligible)].append(ratio)
                    reason = "accepted_proxy_revision"
                else:
                    counts[reason] += occurrences
                if raw._ticker(row["ticker"]):
                    by_ticker[row["ticker"]].add(reason)
            firms = defaultdict(Decimal)
            for (sid, firm, eligible), values in units.items():
                unit = _median(values)
                decay = Decimal(2) ** (-Decimal(index - 1 - eligible) / Decimal(20))
                firms[(sid, firm)] += Decimal(unit.numerator) / Decimal(unit.denominator) * decay
            values = defaultdict(list)
            for (sid, _firm), score in firms.items(): values[sid].append(score)
            scores = {sid: str(_median(observations)) for sid, observations in values.items()}
            states = []
            for identity_row in identities:
                sid, ticker = identity_row["security_id"], identity_row["ticker"]
                reasons = by_ticker[ticker] - {"accepted_proxy_revision"}
                score = None
                if not identity_row["eligible"]:
                    state, reasons = "identity_ineligible", {identity_row["reason"]}
                elif sid in scores:
                    state, score = "scored", scores[sid]
                elif not by_ticker[ticker]:
                    state, reasons = "unknown_input", {"no_source_rating_rows"}
                elif reasons - NO_ADMISSIBLE:
                    state = "unknown_input"
                else:
                    state = "no_admissible_event"
                    if not reasons: reasons = {"no_event_in_frozen_score_window"}
                states.append({"security_id": sid, "state": state, "score": score, "reasons": sorted(reasons)})
            frames.append({"session": decision["session"], "cutoff_utc": cutoff.isoformat(), "states": states})
            normalization.append({"session": decision["session"], "accepted_distinct_events": accepted,
                "refusal_counts": dict(sorted(counts.items())), "cumulative_excluded_ticker_count": len(exclusions),
                "cumulative_nonshare_counts": dict(sorted(nonshare_counts.items())),
                "scored_identity_count": len(scores)})
    return {"identities": identities, "frames": frames, "normalization": normalization,
        "source_census": {"ratings": len(ratings), "native_event_groups": len(groups),
            "duplicate_rows": len(ratings) - len(groups), "native_identity_rows": len(native_identities),
            "unmatched_rating_ticker_count": len(tickers - set(mapping)),
            "all_captured_actions": len(actions), "pre_warmup_actions_audit_only": older_actions,
            "signal_window_actions": len(action_rows)},
        "point_in_time_data": False, "canonical_admission": False, "outcome_reads": 0}
