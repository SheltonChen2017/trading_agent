"""Pure aggregate audit of one frozen matched QuantConnect candidate.

Monetary reconciliation uses exact rational values interpreted from serialized
native decimal scalars. Square roots and exponentiation use floats only for
reported statistical metrics. This is cooperative evidence checking, not a
canonical custody or provider-availability attestation. No I/O occurs here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib
import json
import math
import re
from zoneinfo import ZoneInfo

from .matched_bundle import CANDIDATES, FREEZE_SHA256, PACKET_SHA256, STUDY

NY = ZoneInfo("America/New_York")
INITIAL = Fraction(100000)
PENNY = Fraction(1, 100)
DECISIONS = ("2025-01-02", "2025-01-06", "2025-01-13", "2025-01-21",
             "2025-01-27", "2025-02-03", "2025-02-10", "2025-02-18",
             "2025-02-24", "2025-03-03", "2025-03-10", "2025-03-17",
             "2025-03-24", "2025-03-31")
ETFS = ("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX")
SOURCE_FILES = {"main.py", "proxy_core.py", "signal_packet.py", "matched_config.py"}
HOLIDAYS = {date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17)}
START, END = date(2025, 1, 2), date(2025, 3, 31)
VALUATIONS = tuple((START + timedelta(days=i)).isoformat()
                   for i in range((END - START).days + 1)
                   if (START + timedelta(days=i)).weekday() < 5
                   and START + timedelta(days=i) not in HOLIDAYS)


class AuditError(ValueError):
    """Malformed or mixed evidence; messages never repeat private input."""


def _refuse(message):
    raise AuditError(message)


def _digest(value):
    try:
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    except (ValueError, TypeError, OverflowError):
        _refuse("noncanonical evidence payload")
    if len(raw) > 16 * 1024 * 1024:
        _refuse("evidence resource bound")
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _number(value):
    if type(value) not in (str, int, float, Decimal) or isinstance(value, bool):
        _refuse("native decimal scalar required")
    text = str(value)
    if not 0 < len(text) <= 128 or text.strip() != text:
        _refuse("bounded native decimal required")
    try:
        decimal = Decimal(text)
    except InvalidOperation:
        _refuse("invalid native decimal")
    if not decimal.is_finite() or not -128 <= decimal.as_tuple().exponent <= 128:
        _refuse("nonfinite or unbounded native decimal")
    return Fraction(decimal)


def _integer(value):
    number = _number(value)
    if number.denominator != 1 or number < 0:
        _refuse("nonnegative integer required")
    return int(number)


def _text(value):
    with localcontext() as context:
        context.prec = 50
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def _clock(value):
    if type(value) is not str or len(value) > 64:
        _refuse("aware execution clock required")
    try:
        clock = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _refuse("invalid execution clock")
    if clock.utcoffset() is None:
        _refuse("aware execution clock required")
    return clock.astimezone(NY)


def _json_object(text):
    def pairs(items):
        body = {}
        for key, value in items:
            if key in body:
                _refuse("duplicate log JSON key")
            body[key] = value
        return body
    try:
        value = json.loads(text, object_pairs_hook=pairs,
                           parse_constant=lambda _: _refuse("nonfinite log JSON"))
    except (ValueError, TypeError):
        _refuse("invalid aggregate log JSON")
    if type(value) is not dict:
        _refuse("aggregate log object required")
    return value


def _config(config):
    keys = {"schema", "study_id", "freeze_sha256", "candidate_id", "arm", "cost", "slippage"}
    if type(config) is not dict or set(config) != keys:
        _refuse("closed candidate configuration required")
    policy = (config["candidate_id"], config["arm"], config["cost"], config["slippage"])
    if (config["schema"] != "tpr-qc-matched-config-v1" or config["study_id"] != STUDY
            or config["freeze_sha256"] != FREEZE_SHA256 or policy not in CANDIDATES):
        _refuse("candidate outside frozen matched policy")
    return _digest(config)


def _logs(response, reasons):
    if type(response) is not dict or response.get("success") is not True:
        reasons.append("logs_unavailable")
        return None, [], []
    lines = response.get("logs")
    if type(lines) is not list or len(lines) > 1000:
        _refuse("bounded aggregate log inventory required")
    if response.get("length") != len(lines):
        reasons.append("log_inventory_incomplete")
    groups = {"MATCHED_SUMMARY ": [], "MATCHED_NAV ": [], "MATCHED_COVERAGE ": []}
    for line in lines:
        if type(line) is not str or len(line) > 65536:
            _refuse("bounded aggregate log line required")
        markers = [marker for marker in groups if marker in line]
        if len(markers) > 1:
            _refuse("ambiguous aggregate log marker")
        if markers:
            marker = markers[0]
            if line.count(marker) != 1:
                _refuse("duplicate aggregate log marker")
            groups[marker].append(_json_object(line.split(marker, 1)[1]))
    summaries = groups["MATCHED_SUMMARY "]
    if len(summaries) > 1:
        _refuse("duplicate matched summary")
    if not summaries:
        reasons.append("summary_missing")
    for marker in ("MATCHED_NAV ", "MATCHED_COVERAGE "):
        rows = groups[marker]
        days = [row.get("session") for row in rows]
        if any(type(day) is not str for day in days) or len(set(days)) != len(days):
            _refuse("duplicate or invalid aggregate session")
    return summaries[0] if summaries else None, groups["MATCHED_NAV "], groups["MATCHED_COVERAGE "]


def _source(receipt, config, config_hash, result, logs, pages, reasons):
    if type(receipt) is not dict:
        reasons.append("source_verification_missing")
        return {}
    expected_packet = PACKET_SHA256 if config["arm"] == "tpr_on" else None
    for key, expected in (("candidate_id", config["candidate_id"]),
                          ("config_sha256", config_hash), ("freeze_sha256", FREEZE_SHA256),
                          ("packet_sha256", expected_packet)):
        if key not in receipt:
            reasons.append("source_verification_missing")
        elif receipt[key] != expected:
            _refuse("source and candidate identities differ")
    source_hashes = receipt.get("source_hashes")
    if (type(source_hashes) is not dict or set(source_hashes) != SOURCE_FILES
            or not all(_hash(value) for value in source_hashes.values())
            or receipt.get("exact_cloud_readback") is not True
            or receipt.get("build_success") is not True):
        reasons.append("source_verification_missing")
    for key in ("project_id", "compile_id", "backtest_id"):
        if receipt.get(key) in (None, ""):
            reasons.append("source_verification_missing")
    expected_evidence = {"result": _digest(result), "logs": _digest(logs),
                         "order_pages": [_digest(page) for page in pages]}
    if "evidence_hashes" not in receipt:
        reasons.append("evidence_binding_missing")
    elif receipt["evidence_hashes"] != expected_evidence:
        _refuse("mixed result log or order evidence")
    return (dict(source_hashes) if type(source_hashes) is dict
            and set(source_hashes) == SOURCE_FILES
            and all(_hash(value) for value in source_hashes.values()) else {})


def _summary(summary, config, config_hash, reasons):
    if summary is None:
        return
    expected = {"study_id": STUDY, "candidate_id": config["candidate_id"],
                "arm": config["arm"], "cost": config["cost"],
                "config_sha256": config_hash, "freeze_sha256": FREEZE_SHA256,
                "packet_sha256": PACKET_SHA256 if config["arm"] == "tpr_on" else None,
                "canonical_admission": False, "independent_sleeve_pnl_observed": False}
    if any(key not in summary or summary[key] != value or
           (type(value) is bool and type(summary[key]) is not bool) for key, value in expected.items()):
        _refuse("matched summary identity or authority mismatch")
    required = {"decisions", "refused_decisions", "submitted_orders", "fill_events",
                "requested_shares", "submitted_shares", "filled_shares", "fees",
                "valuation_days", "last_valuation_session", "reason_counts",
                "max_cash_ledger_residual", "max_nav_ledger_residual",
                "position_ledger_mismatches", "risk_breaches", "sleeve_selected_decisions"}
    if not required.issubset(summary):
        reasons.append("summary_accounting_incomplete")
        return
    if (_integer(summary["decisions"]) != 14 or _integer(summary["refused_decisions"]) != 0
            or _integer(summary["valuation_days"]) != 60
            or summary["last_valuation_session"] != END.isoformat()):
        reasons.append("summary_execution_incomplete")
    if (_number(summary["max_cash_ledger_residual"]) > PENNY
            or _number(summary["max_nav_ledger_residual"]) > PENNY
            or _integer(summary["position_ledger_mismatches"]) != 0
            or _integer(summary["risk_breaches"]) != 0):
        reasons.append("summary_accounting_or_risk_failure")
    requested, submitted, filled = (_integer(summary[name]) for name in
                                   ("requested_shares", "submitted_shares", "filled_shares"))
    if not requested >= submitted >= filled:
        _refuse("share accounting order violated")
    counts = summary["reason_counts"]
    if type(counts) is not dict or any(type(key) is not str for key in counts):
        _refuse("invalid diagnostic reason inventory")
    failed = {"missing_mark", "missing_action_custody", "unpriced_held_nav",
              "missing_prior_close_nav", "qc_invalid_order", "qc_canceled_order",
              "delisting_event", "delisting_target_refused"}
    if any(_integer(value) and (key in failed or key.startswith("missing_lagged_membership_"))
           for key, value in counts.items()):
        reasons.append("execution_input_or_order_failure")


def _orders(pages, receipt, summary, stats, config, reasons):
    if type(pages) is not list or len(pages) > 100:
        _refuse("bounded order pages required")
    if not pages:
        reasons.append("order_inventory_missing")
        return {"orders": None, "filled_orders": None, "fill_events": None,
                "filled_shares": None, "fees": None, "fill_notional": None, "order_failures": None,
                "etf_instrument_execution": None}
    orders, total, expected_start = [], None, 0
    for page in pages:
        if type(page) is not dict or page.get("success") is not True:
            reasons.append("order_inventory_loading_or_failed")
            continue
        if page.get("loading") is True:
            reasons.append("order_inventory_loading_or_failed")
        if "start" not in page or "end" not in page:
            reasons.append("order_page_boundary_missing")
        else:
            start, end = _integer(page["start"]), _integer(page["end"])
            if start != expected_start or not 0 < end - start < 100:
                _refuse("overlapping unordered or unbounded order page")
            expected_start = end
        length = _integer(page.get("length"))
        if total is None:
            total = length
        elif total != length:
            _refuse("changing order inventory length")
        rows = page.get("orders")
        if type(rows) is not list or len(rows) > 99 or length > 5000:
            _refuse("bounded native order inventory required")
        for key in ("projectId", "backtestId"):
            expected = receipt.get("project_id" if key == "projectId" else "backtest_id")
            if key in page and page[key] != expected:
                _refuse("foreign order page identity")
        orders.extend(rows)
    if total is None or len(orders) != total:
        reasons.append("order_inventory_incomplete")
    ids, events_seen = set(), set()
    shares, fees, notional = Fraction(0), Fraction(0), Fraction(0)
    fills = filled_orders = failures = 0
    basket = {etf: {"filled_orders": 0, "fill_events": 0, "filled_shares": Fraction(0)} for etf in ETFS}
    for order in orders:
        if type(order) is not dict or "id" not in order:
            _refuse("native order object identity missing")
        oid = _integer(order["id"])
        if oid in ids:
            _refuse("duplicate native order identity")
        ids.add(oid)
        if order.get("type") != 4 or order.get("priceAdjustmentMode") != 0 or order.get("priceCurrency") != "USD":
            reasons.append("non_moo_raw_usd_order")
        created = _clock(order.get("createdTime"))
        if created.date().isoformat() not in DECISIONS or created.strftime("%H:%M:%S") != "09:20:00":
            reasons.append("order_clock_outside_frozen_schedule")
        quantity = _number(order.get("quantity"))
        if quantity.denominator != 1 or quantity == 0:
            _refuse("whole nonzero native order quantity required")
        events = order.get("events")
        if type(events) is not list or len(events) > 100:
            _refuse("bounded native order events required")
        order_fill = Fraction(0)
        order_etf = None
        for event in events:
            if type(event) is not dict:
                _refuse("native event object required")
            if event.get("status") not in ("filled", "partiallyFilled", "partially_filled", 2, 3):
                continue
            if event.get("orderId") != oid:
                _refuse("fill references a different native order")
            event_id = event.get("orderEventId", event.get("id"))
            identity = (oid, _integer(event_id))
            if identity in events_seen:
                _refuse("duplicate native fill event identity")
            events_seen.add(identity)
            amount, price = _number(event.get("fillQuantity")), _number(event.get("fillPrice"))
            fee = _number(event.get("orderFeeAmount"))
            if (amount == 0 or amount.denominator != 1 or price <= 0 or fee < 0
                    or (amount > 0) != (quantity > 0)):
                _refuse("invalid native fill economics")
            if event.get("fillPriceCurrency") != "USD" or event.get("orderFeeCurrency") != "USD":
                reasons.append("non_usd_native_fill")
            if config["arm"] == "etf_basket":
                symbol = order.get("symbol")
                native_value = symbol.get("value") if type(symbol) is dict else None
                event_value = event.get("symbolValue")
                if event_value is not None and native_value is not None and event_value != native_value:
                    _refuse("native ETF order and fill symbol differ")
                etf = event_value if event_value is not None else native_value
                if etf not in ETFS:
                    reasons.append("etf_basket_contains_unknown_or_foreign_instrument")
                else:
                    if order_etf is not None and order_etf != etf:
                        _refuse("one native order mixes ETF instruments")
                    order_etf = etf
                    basket[etf]["fill_events"] += 1
                    basket[etf]["filled_shares"] += abs(amount)
            if fee != abs(amount) * PENNY:
                reasons.append("native_fee_schedule_mismatch")
            stamp = _number(event.get("time"))
            if stamp.denominator != 1:
                _refuse("whole native fill timestamp required")
            try:
                fill_clock = datetime.fromtimestamp(int(stamp), timezone.utc).astimezone(NY)
            except (ValueError, OverflowError, OSError):
                _refuse("invalid native fill timestamp")
            if (fill_clock.date() != created.date()
                    or not "09:30:00" <= fill_clock.strftime("%H:%M:%S") < "09:35:00"):
                reasons.append("fill_clock_outside_frozen_schedule")
            order_fill += amount
            shares += abs(amount)
            fees += fee
            notional += abs(amount) * price
            fills += 1
        if abs(order_fill) > abs(quantity):
            _refuse("native order overfilled")
        if order.get("status") == 3 and order_fill == quantity:
            filled_orders += 1
            if order_etf is not None:
                basket[order_etf]["filled_orders"] += 1
        else:
            failures += 1
    if failures:
        reasons.append("unfilled_or_failed_native_orders")
    if not fills:
        reasons.append("zero_trade_diagnostic")
    if config["arm"] == "etf_basket" and not all(row["filled_orders"] > 0 for row in basket.values()):
        reasons.append("etf_basket_instrument_execution_incomplete")
    if summary is not None and all(key in summary for key in
            ("submitted_orders", "fill_events", "filled_shares", "submitted_shares", "fees")):
        if (len(orders) != _integer(summary["submitted_orders"])
                or fills != _integer(summary["fill_events"])
                or shares != _integer(summary["filled_shares"])
                or shares != _integer(summary["submitted_shares"])
                or fees != _number(summary["fees"])):
            reasons.append("native_and_summary_order_accounting_mismatch")
    if "Total Orders" not in stats:
        reasons.append("native_order_statistic_missing")
    elif _integer(stats["Total Orders"]) != len(orders):
        reasons.append("native_order_statistic_mismatch")
    if "Total Fees" not in stats:
        reasons.append("native_fee_statistic_missing")
    elif _number(str(stats["Total Fees"]).removeprefix("$")) != fees:
        reasons.append("native_fee_statistic_mismatch")
    return {"orders": len(orders), "filled_orders": filled_orders, "fill_events": fills,
            "filled_shares": _text(shares), "fees": _text(fees),
            "fill_notional": _text(notional), "order_failures": failures,
            "etf_instrument_execution": ({etf: dict(row, filled_shares=_text(row["filled_shares"]))
                                          for etf, row in basket.items()} if config["arm"] == "etf_basket" else None)}


def _nav(rows, summary, stats, reasons):
    if tuple(row.get("session") for row in rows) != VALUATIONS:
        reasons.append("valuation_schedule_incomplete_or_wrong")
    if not rows:
        return None
    values, cash_values, exposures = [INITIAL], [], []
    cash_residuals, nav_residuals, mismatches = [], [], 0
    for row in rows:
        required = {"nav", "cash", "gross_exposure", "cash_ledger_residual", "nav_ledger_residual", "position_ledger_mismatches"}
        if not required.issubset(row):
            reasons.append("valuation_accounting_missing")
            return None
        nav, cash, gross = (_number(row[key]) for key in ("nav", "cash", "gross_exposure"))
        if nav <= 0:
            _refuse("nonpositive NAV")
        cash_error, nav_error = (_number(row[key]) for key in ("cash_ledger_residual", "nav_ledger_residual"))
        if cash_error < 0 or nav_error < 0:
            _refuse("negative accounting residual")
        mismatch = _integer(row["position_ledger_mismatches"])
        if cash_error > PENNY or nav_error > PENNY or mismatch:
            reasons.append("daily_accounting_failure")
        if (cash < -PENNY or cash > nav + PENNY or gross < 0 or gross > 1 + PENNY / nav
                or row.get("risk_within_unlevered_account") is not True):
            reasons.append("daily_unlevered_risk_failure")
        if abs(gross - (nav - cash) / nav) > Fraction(1, 100000000):
            reasons.append("cash_exposure_nav_discrepancy")
        values.append(nav)
        cash_values.append(cash)
        exposures.append(gross)
        cash_residuals.append(cash_error)
        nav_residuals.append(nav_error)
        mismatches += mismatch
    if summary is not None and all(key in summary for key in
            ("max_cash_ledger_residual", "max_nav_ledger_residual", "position_ledger_mismatches")):
        if (max(cash_residuals) != _number(summary["max_cash_ledger_residual"])
                or max(nav_residuals) != _number(summary["max_nav_ledger_residual"])
                or mismatches != _integer(summary["position_ledger_mismatches"])):
            reasons.append("daily_and_summary_accounting_mismatch")
    for label, expected in (("Start Equity", INITIAL), ("End Equity", values[-1])):
        if label not in stats:
            reasons.append("native_equity_statistic_missing")
        elif abs(_number(str(stats[label]).removeprefix("$")) - expected) > Fraction(1, 200):
            reasons.append("native_equity_statistic_mismatch")
    if tuple(row.get("session") for row in rows) != VALUATIONS:
        return None
    returns = [right / left - 1 for left, right in zip(values, values[1:])]
    mean = sum(returns, Fraction(0)) / len(returns)
    variance = sum(((value - mean) ** 2 for value in returns), Fraction(0)) / (len(returns) - 1)
    volatility = math.sqrt(float(variance)) * math.sqrt(252)
    sharpe = float(mean) / math.sqrt(float(variance)) * math.sqrt(252) if variance else None
    elapsed = (date.fromisoformat(rows[-1]["session"]) - date.fromisoformat(rows[0]["session"])).days
    try:
        cagr = math.pow(float(values[-1] / INITIAL), 365.25 / elapsed) - 1
    except (OverflowError, ValueError):
        cagr = None
        reasons.append("statistical_annualization_unavailable")
    peak, drawdown = values[0], Fraction(0)
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
    def distribution(items):
        return {"min": _text(min(items)), "mean": _text(sum(items, Fraction(0)) / len(items)),
                "max": _text(max(items)), "end": _text(items[-1])}
    return {"initial_nav": _text(INITIAL), "end_nav": _text(values[-1]),
            "return_pct": _text((values[-1] / INITIAL - 1) * 100),
            "partial_2025_return_pct": _text((values[-1] / INITIAL - 1) * 100),
            "annual_result_is_partial": True, "cagr": cagr, "cagr_elapsed_calendar_days": elapsed,
            "annualized_sample_volatility": volatility, "sharpe_risk_free_zero": sharpe,
            "risk_free_daily": "0", "daily_return_observations": len(returns),
            "daily_drawdown_pct": _text(drawdown * 100),
            "cash": distribution(cash_values), "gross_exposure": distribution(exposures),
            "max_cash_ledger_residual": _text(max(cash_residuals)),
            "max_nav_ledger_residual": _text(max(nav_residuals)),
            "position_ledger_mismatches": mismatches}


def _coverage(rows, config, summary, reasons):
    if tuple(row.get("session") for row in rows) != DECISIONS:
        reasons.append("coverage_schedule_incomplete_or_wrong")
    output = {}
    metadata = {"membership_available", "snapshot_hash", "member_count", "selected_count", "effective_utc", "received_utc", "etf_fallback"}
    allowed = ({"scored", "no_admissible_event", "unknown_input", "missing_identity", "ineligible", "unknown_weight", "zero_weight"}
               if config["arm"] == "tpr_on" else {"known_weight", "unknown_weight", "zero_weight"})
    for row in rows:
        if row.get("arm") != config["arm"]:
            _refuse("coverage belongs to a different arm")
        if row.get("session") not in DECISIONS:
            continue
        if type(row.get("sleeves")) is not dict or set(row["sleeves"]) != set(ETFS):
            reasons.append("sleeve_coverage_missing")
            continue
        for etf, report in row["sleeves"].items():
            if type(report) is not dict or not metadata.issubset(report):
                reasons.append("sleeve_coverage_missing")
                continue
            selected = _integer(report["selected_count"])
            if selected > (1 if config["arm"] == "etf_basket" else 10) or report["etf_fallback"] is not False:
                _refuse("selection or fallback outside frozen arm")
            group = output.setdefault(etf, {"member_counts": [], "selected_counts": [], "state_counts": {}, "state_weights": {},
                "missing_weight_observations": 0, "unavailable_membership_decisions": 0, "snapshot_sequence": []})
            group["snapshot_sequence"].append((row["session"], report["snapshot_hash"],
                report["effective_utc"], report["received_utc"]))
            if report["membership_available"] is False:
                if (config["arm"] != "etf_basket" or selected != 1
                        or any(report[key] is not None for key in ("snapshot_hash", "member_count", "effective_utc", "received_utc"))
                        or set(report) != metadata):
                    _refuse("unknown membership fabricated or admitted to stock arm")
                group["selected_counts"].append(selected)
                group["unavailable_membership_decisions"] += 1
                continue
            if report["membership_available"] is not True or not _hash(report["snapshot_hash"]):
                _refuse("invalid membership availability or snapshot hash")
            members = _integer(report["member_count"])
            prior = date.fromisoformat(row["session"]) - timedelta(days=1)
            while prior.weekday() >= 5 or prior in HOLIDAYS or prior == date(2025, 1, 1):
                prior -= timedelta(days=1)
            cutoff = datetime(prior.year, prior.month, prior.day, 18, tzinfo=NY).astimezone(timezone.utc)
            effective, received = (_clock(report[key]).astimezone(timezone.utc) for key in ("effective_utc", "received_utc"))
            if (received > cutoff or not cutoff - timedelta(days=21) <= effective <= cutoff - timedelta(days=7)):
                reasons.append("membership_clock_outside_frozen_cutoff")
            cats = set(report) - metadata
            if cats != allowed:
                reasons.append("membership_state_inventory_incomplete")
                continue
            counts, weights = {}, {}
            for cat in sorted(cats):
                value = report[cat]
                if type(value) is not dict or set(value) != {"count", "weight"}:
                    _refuse("invalid aggregate membership state")
                counts[cat], weights[cat] = _integer(value["count"]), _number(value["weight"])
                if weights[cat] < 0:
                    _refuse("negative membership weight")
            if sum(counts.values()) != members:
                reasons.append("membership_state_partition_mismatch")
            group["member_counts"].append(members)
            group["selected_counts"].append(selected)
            group["missing_weight_observations"] += counts.get("unknown_weight", 0)
            for cat in cats:
                group["state_counts"][cat] = group["state_counts"].get(cat, 0) + counts[cat]
                group["state_weights"][cat] = group["state_weights"].get(cat, Fraction(0)) + weights[cat]
    for etf, group in output.items():
        group["membership_snapshot_sequence_sha256"] = _digest(group.pop("snapshot_sequence"))
        selected = group.pop("selected_counts")
        members = group.pop("member_counts")
        if not selected:
            output[etf] = None
            continue
        group["observed_decisions"] = len(selected)
        group["selected_decisions"] = sum(value > 0 for value in selected)
        group["zero_selection_diagnostic"] = not any(selected)
        group["selected_min_mean_max"] = [min(selected), _text(Fraction(sum(selected), len(selected))), max(selected)]
        group["members_min_max"] = [min(members), max(members)] if members else None
        group["state_weights"] = {key: _text(value) for key, value in group["state_weights"].items()}
        group["weights_are_callback_slice_not_full_global_holdings"] = True
        if summary is not None and "sleeve_selected_decisions" in summary:
            claimed = summary["sleeve_selected_decisions"]
            if type(claimed) is not dict or set(claimed) != set(ETFS):
                reasons.append("sleeve_summary_incomplete")
            elif _integer(claimed[etf]) != group["selected_decisions"]:
                reasons.append("sleeve_selection_summary_mismatch")
    for etf in ETFS:
        if etf not in output:
            output[etf] = None
    return output


def audit_result(result_response, logs_response, order_pages, source_receipt, candidate_config):
    """Audit one terminal run; incomplete/zero-trade evidence stays diagnostic.

    The source receipt binds canonical hashes of all three supplied response
    inventories under evidence_hashes. Only aggregate summaries are returned;
    native order identifiers, ticker rows and prices never leave this function.
    """
    config_hash = _config(candidate_config)
    reasons = []
    if type(order_pages) is not list:
        _refuse("order page list required")
    receipt = source_receipt if type(source_receipt) is dict else {}
    source_hashes = _source(source_receipt, candidate_config, config_hash,
                            result_response, logs_response, order_pages, reasons)
    if type(result_response) is not dict or result_response.get("success") is not True or type(result_response.get("backtest")) is not dict:
        result, stats = {}, {}
        reasons.append("backtest_response_unavailable")
    else:
        result = result_response["backtest"]
        stats = result.get("statistics") if type(result.get("statistics")) is dict else {}
        if receipt.get("backtest_id") in (None, ""):
            reasons.append("result_identity_unverified")
        elif result.get("backtestId") != receipt.get("backtest_id"):
            _refuse("result belongs to a different backtest")
        if "projectId" in result and receipt.get("project_id") not in (None, "") and result["projectId"] != receipt.get("project_id"):
            _refuse("result belongs to a different project")
        if (result.get("completed") is not True or _number(result.get("progress", "0")) != 1
                or result.get("error") is not None or result.get("status") not in ("Completed", "completed")):
            reasons.append("backtest_not_successfully_completed")
    summary, nav_rows, coverage_rows = _logs(logs_response, reasons)
    _summary(summary, candidate_config, config_hash, reasons)
    orders = _orders(order_pages, receipt, summary, stats, candidate_config, reasons)
    metrics = _nav(nav_rows, summary, stats, reasons)
    coverage = _coverage(coverage_rows, candidate_config, summary, reasons)
    if summary is not None and summary.get("meaningful_execution") is not True:
        reasons.append("adapter_reports_diagnostic")
    if metrics is not None and orders["fill_notional"] is not None:
        metrics["absolute_fill_notional_turnover_initial_nav"] = _text(_number(orders["fill_notional"]) / INITIAL)
    shortfall = None
    if summary is not None and all(key in summary for key in ("requested_shares", "submitted_shares")):
        shortfall = _integer(summary["requested_shares"]) - _integer(summary["submitted_shares"])
    return {"schema": "tpr-qc-matched-audit-v1", "study_id": STUDY,
            "candidate_id": candidate_config["candidate_id"], "arm": candidate_config["arm"], "cost": candidate_config["cost"],
            "project_id": receipt.get("project_id"), "compile_id": receipt.get("compile_id"), "backtest_id": receipt.get("backtest_id"),
            "config_sha256": config_hash, "freeze_sha256": FREEZE_SHA256,
            "packet_sha256": PACKET_SHA256 if candidate_config["arm"] == "tpr_on" else None,
            "source_hashes": source_hashes, "terminal_status": result.get("status"),
            "meaningful_execution": not reasons, "diagnostic_reasons": sorted(set(reasons)),
            "orders": orders, "metrics": metrics, "coverage_by_sleeve": coverage,
            "requested_minus_submitted_shares": shortfall,
            "valuation_observations": len(nav_rows), "decision_coverage_observations": len(coverage_rows),
            "canonical_admission": False, "independent_sleeve_pnl_observed": False,
            "numerical_convention": "Exact decimal-text rational money; 50-digit display ratios; floats only sqrt/exponent statistical metrics; 60 daily returns include initial100000 baseline; CAGR uses elapsed observed calendar days; Sharpe risk-free0; partial2025 only."}
