"""Pure private-input imputation for the noncanonical raw-revision candidate.

No loader, authentication, I/O, provider, authority or outcome evaluation lives
here. The caller must authenticate the frozen private source bodies first.
Returned native identities/bars/actions are private, not a public report.

Sharadar's official FAQ and adjustment article document raw open = split-
adjusted open * closeunadj / close, and tape volume = volume * close / closeunadj:
https://sharadar.com/docs/faqs
https://sharadar.com/blog/posts/sharadar-stock-prices-fund-prices-and-adjustments
Official actiontypes/dividend metadata, indexed in the public homepage preview
https://sharadar.com/signout , defines value as split/stock-dividend adjusted
cash per share and date as ex-dividend. Multiplying it by the same-date price
factor is an explicit current-vintage imputation, not observed raw entitlement
or proof that independently delivered tables share an adjustment vintage.
The native split value's direction is not established by the reviewed public
field metadata, so native splits remain unresolved, not guessed from prices.
"""
from bisect import bisect_left
from collections import Counter
from datetime import date
from fractions import Fraction
import hashlib
import json
import re

from .raw_candidate import SOURCE_START, WINDOW_END, WINDOW_START, plan_target_frames

SCHEMA = "tpr-raw-market-inputs-v1"
PRICE_START = "2024-12-31"
_STOCK = {"ticker", "date", "open", "close", "closeunadj", "volume"}
_ACTION = {"ticker", "date", "action", "value", "contraticker"}
_METADATA_ONLY = frozenset(("sicchangefrom", "sicchangeto"))
_MAX_ROWS = 100_000


def _fail(reason):
    raise ValueError(reason)


def _plain(value, depth=0):
    if depth > 8:
        _fail("market input nesting bound")
    if value is None or type(value) is bool:
        return value
    if type(value) is int and value.bit_length() <= 128:
        return value
    if type(value) is str and len(value) <= 256:
        return value
    if type(value) in (list, tuple) and len(value) <= _MAX_ROWS:
        return [_plain(child, depth + 1) for child in value]
    if type(value) is dict and len(value) <= 32 and all(type(key) is str for key in value):
        return {key: _plain(child, depth + 1) for key, child in value.items()}
    _fail("invalid plain market input")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _day(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        _fail("invalid market date")
    try:
        date.fromisoformat(value)
    except ValueError:
        _fail("invalid market date")
    return value


def _number(value, *, positive=True):
    if (type(value) is not str or len(value) > 96
            or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) is None):
        _fail("invalid market numeric")
    number = Fraction(value)
    if number < 0 or (positive and number == 0) or number > 10**12:
        _fail("invalid market numeric bound")
    return number


def _price(value):
    """Exact rational rounding to eight places, independent of Decimal context."""
    scaled = value * 100_000_000
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    twice = remainder * 2
    if twice > scaled.denominator or (twice == scaled.denominator and whole % 2):
        whole += 1
    if whole <= 0 or whole > 10**20:
        _fail("invalid market numeric quantization")
    text = str(whole).zfill(9)
    return (text[:-8] + "." + text[-8:]).rstrip("0").rstrip(".")


def _native_decimal(value):
    # Input is already a validated plain decimal; preserve its exact value.
    whole, dot, fraction = value.partition(".")
    fraction = fraction.rstrip("0")
    if len(fraction) > 24:
        _fail("invalid market numeric close precision")
    return str(int(whole)) + ("." + fraction if dot and fraction else "")


def _inventory(rows, fields, keys, *, label):
    if type(rows) not in (list, tuple) or len(rows) > _MAX_ROWS:
        _fail("invalid bounded market inventory")
    found, duplicates = {}, 0
    for original in rows:
        if type(original) is not dict or set(original) != fields or any(type(key) is not str for key in original):
            _fail("invalid closed market row")
        if any(value is not None and type(value) is not str for value in original.values()):
            _fail("invalid market numeric or native text")
        row = _plain(original)
        if type(row["ticker"]) is not str or re.fullmatch(r"[A-Z][A-Z0-9./\-]{0,31}", row["ticker"]) is None:
            _fail("invalid market ticker")
        _day(row["date"])
        identity = tuple(None if key == "contraticker" and row[key] == "" else row[key] for key in keys)
        if identity in found:
            if found[identity] != row:
                _fail("conflicting " + label + " row")
            duplicates += 1
        else:
            found[identity] = row
    return found, duplicates


def convert(structure: dict, stocks, actions) -> dict:
    """Return private outcomes/actions plus aggregate, non-authorizing evidence.

    Prices are limited to the source-only proposal union, never chosen using
    outcomes. Missing scheduled bars are explicit no-quote bars; no carry-fill
    of prices or lagged volume occurs. Warmup through Dec 30 remains unpriced.
    Detailed action projections must reconcile with the frozen source inventory.
    The result cannot establish rights, source custody, completeness or readiness.
    """
    structure = _plain(structure)
    proposal = plan_target_frames(structure)
    selected = set(proposal["proposed_security_ids"])
    if not selected:
        _fail("no positive proxy targets")
    mapping, mapped_ids = {}, set()
    for identity in structure["identities"]:
        sid, ticker = identity["security_id"], identity["ticker"]
        if sid in selected:
            if ticker in mapping or sid in mapped_ids:
                _fail("ambiguous selected market identity")
            mapping[ticker] = sid
            mapped_ids.add(sid)
    if mapped_ids != selected:
        _fail("missing selected market identity")
    axis = structure["calendar"]
    dates = [row["session_date"] for row in axis]
    date_set = set(dates)
    if PRICE_START not in date_set:
        _fail("missing fixed price buffer session")
    stock_rows, stock_duplicates = _inventory(stocks, _STOCK, ("ticker", "date"), label="market")
    action_rows, action_duplicates = _inventory(actions, _ACTION, ("ticker", "date", "action", "contraticker"), label="action")
    market = {}
    for key, row in stock_rows.items():
        if row["ticker"] not in mapping or not PRICE_START <= row["date"] <= WINDOW_END or row["date"] not in date_set:
            _fail("market row outside selected fixed scope")
        opening, closing, raw_close = (_number(row[field]) for field in ("open", "close", "closeunadj"))
        volume = _number(row["volume"], positive=False)
        factor = raw_close / closing
        raw_volume = volume / factor
        raw_volume = raw_volume.numerator // raw_volume.denominator
        if raw_volume > 10**9:
            _fail("invalid market numeric volume bound")
        market[key] = (_price(opening * factor), _native_decimal(row["closeunadj"]), raw_volume, factor)
    expected = {(row["ticker"], row["date"], row["action"]) for row in structure["actions"]
                if row["ticker"] in mapping and WINDOW_START <= row["date"] <= WINDOW_END}
    actual = set()
    for row in action_rows.values():
        if row["ticker"] not in mapping or not SOURCE_START <= row["date"] <= WINDOW_END:
            _fail("action row outside selected fixed scope")
        if type(row["action"]) is not str or not row["action"] or len(row["action"]) > 64:
            _fail("invalid market action kind")
        if WINDOW_START <= row["date"]:
            actual.add((row["ticker"], row["date"], row["action"]))
    if expected != actual:
        _fail("action inventory mismatch")
    sessions, missing = [], 0
    for index, session in enumerate(axis):
        day, bars = session["session_date"], []
        if day >= PRICE_START:
            for ticker, sid in sorted(mapping.items(), key=lambda pair: pair[1]):
                row = market.get((ticker, day))
                previous = market.get((ticker, dates[index - 1])) if index else None
                if row is None:
                    missing += 1
                bars.append({"security_id": sid, "open": row[0] if row else None,
                    "close": row[1] if row else None, "lagged_volume": previous[2] if previous else 0,
                    "volume_available_at_utc": axis[index - 1]["close_utc"] if previous else None,
                    "open_available_at_utc": session["open_utc"] if row else None,
                    "close_available_at_utc": session["close_utc"] if row else None,
                    "tradable": row is not None})
        sessions.append({"session_id": day, "open_utc": session["open_utc"], "close_utc": session["close_utc"], "bars": bars})
    converted, counts = [], Counter()
    for row in sorted(action_rows.values(), key=lambda item: _canonical(item)):
        if row["date"] < WINDOW_START:
            counts["prewindow_action_count"] += 1
            continue
        effective = dates[bisect_left(dates, row["date"])]
        if row["action"] in _METADATA_ONLY and row["contraticker"] in (None, ""):
            counts["metadata_only_action_count"] += 1
            continue
        kind, value = "unresolved", None
        factor_row = market.get((row["ticker"], row["date"]))
        if row["action"] == "dividend" and row["contraticker"] in (None, "") and factor_row and row["value"] is not None:
            try:
                value = _price(_number(row["value"]) * factor_row[3])
                kind = "cash_dividend"
            except ValueError:
                value = None
        counts[kind + "_count"] += 1
        converted.append({"action_id": hashlib.sha256(_canonical(row)).hexdigest(), "session_id": effective,
            "security_id": mapping[row["ticker"]], "kind": kind, "value": value})
    converted.sort(key=lambda item: (item["session_id"], item["security_id"], item["action_id"]))
    evidence = {"model": "sharadar-current-vintage-raw-imputation-v1", "selected_security_count": len(selected),
        "calendar_session_count": len(axis), "stock_row_count": len(stock_rows), "action_row_count": len(action_rows),
        "duplicate_stock_rows": stock_duplicates, "duplicate_action_rows": action_duplicates,
        "missing_bar_count": missing, "metadata_only_action_count": counts["metadata_only_action_count"],
        "prewindow_action_count": counts["prewindow_action_count"], "cash_dividend_count": counts["cash_dividend_count"],
        "stock_split_count": 0, "unresolved_action_count": counts["unresolved_count"],
        "raw_open_rounding": "exact-rational-8-decimal-half-even", "raw_volume_rounding": "exact-reciprocal-floor",
        "dividend_model": "ex-date-receivable-nonspendable-no-payment-date",
        "dividend_basis": "same-ex-date-stock-factor-imputed-not-observed",
        "dividend_rounding": "exact-rational-8-decimal-half-even",
        "native_split_value_direction_verified": False, "cross_table_adjustment_vintage_verified": False,
        "action_inventory_reconciled": True,
        "clock_model": "assumed_historical_daily_bar_clock", "observed_provider_availability": False,
        "current_vintage_imputation": True, "current_snapshot_survivorship_bias_possible": True,
        "historical_symbol_match_verified": False, "point_in_time_data": False,
        "canonical_admission": False, "real_backtest_ready": False, "quantconnect_authority": False,
        "trading_authority": False, "missing_or_unresolved_must_propagate_to_engine": True}
    # Bind the exact canonical private-file bytes, whose framing includes one
    # terminal newline. Native action IDs independently use compact JSON only.
    return {"schema": SCHEMA, "structure_sha256": hashlib.sha256(_canonical(structure) + b"\n").hexdigest(),
        "outcomes": {"schema": "tpr-raw-outcomes-v1", "sessions": sessions},
        "corporate_actions": tuple(converted), "evidence": evidence}
