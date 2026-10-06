"""Pure D2 fixture scoring, exact pre-rank algebra, projection and targets.

Explicit synthetic metadata/configuration is not provider/PIT/source admission.
Clip, screen, group and portfolio values are fixture choices, not empirical
bindings. Historical eligible-session indices remain unchanged as events age.
Unit medians are summed per institution across sessions/catalysts, then stock
strength is the institution median; catalyst totals use the same unit mass.
Decimal calculations use a fresh fixed 96-digit context, never caller context.
OLS and ties use exact rationals after deterministic Decimal normalization.
External decimals are bounded separately from emitted 96-digit normalizations;
exact rational components have an explicit 8192-bit software resource budget.
No loader, publication, outcomes, broker, QC or real-data authority exists.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

AUTHORITY = (("canonical_admission", False), ("point_in_time_data", False),
             ("outcomes", False), ("qc", False), ("trading", False))
CONTROL_NAMES = ("prior_total_return_5_sessions", "prior_total_return_20_sessions",
                 "prior_total_return_60_sessions", "log_point_in_time_market_cap",
                 "log_point_in_time_adv_20_sessions", "realized_volatility_20_sessions")
_CTX = Context(prec=96, rounding=ROUND_HALF_EVEN)
_CONFIG = {"clip_absolute", "industry_min_total", "industry_min_active", "sector_min_total", "sector_min_active",
           "min_price", "min_adv", "max_spread_fraction", "max_capacity_fraction"}
_UNIVERSE = {"security_id", "instrument_type", "venue", "primary_listing", "basis_id", "adr_ratio", "underlying_id",
             "industry_id", "sector_id", "available_at_utc", "effective_session_index", "controls"}
_CONTROLS = {"values", "available_at_utc", "effective_session_index", "complete", "evidence_id", "price", "adv",
             "spread_fraction", "capacity_fraction", "rating_state", "catalyst_state", "rating_inventory_complete", "catalyst_inventory_complete"}
_EVENT = {"lineage_id", "version_id", "security_id", "institution_id", "catalyst_id", "eligible_session_index", "available_at_utc", "payload"}
_PRICE = {"new_target", "prior_target", "pre_event_price", "target_basis_id", "price_basis_id", "price_available_at_utc",
          "information_at_utc", "price_session_index", "information_session_index"}


class FixtureScoringError(ValueError):
    """Fixed reason codes, never caller/source values."""


@dataclass(frozen=True)
class VersionScore:
    lineage_id: str
    version_id: str
    security_id: str
    institution_id: str
    state: str
    reasons: tuple[str, ...]
    age_sessions: int | None
    contribution: str | None


@dataclass(frozen=True)
class StockScore:
    security_id: str
    state: str
    reasons: tuple[str, ...]
    strength: str | None
    normalized_score: str | None
    group_id: str | None
    controls: tuple[tuple[str, str], ...]
    rating_state: str | None
    catalyst_state: str | None
    n_inst: str
    n_cat: str
    n_ind: str


@dataclass(frozen=True)
class StockResult:
    rows: tuple[StockScore, ...]
    versions: tuple[VersionScore, ...]
    cutoff_utc: str
    decision_session_index: int
    mode: str = "synthetic-fixture-only"
    authority: tuple[tuple[str, bool], ...] = AUTHORITY


@dataclass(frozen=True)
class RankRow:
    security_id: str
    state: str
    reasons: tuple[str, ...]
    score: str | None
    percentile: str | None
    strength: str | None


@dataclass(frozen=True)
class RankResult:
    rows: tuple[RankRow, ...]
    columns: tuple[str, ...]
    coefficients: tuple[str, ...]
    cutoff_utc: str
    decision_session_index: int
    mode: str = "synthetic-fixture-only"
    authority: tuple[tuple[str, bool], ...] = AUTHORITY


@dataclass(frozen=True)
class ETFProjection:
    etf_id: str
    state: str
    reasons: tuple[str, ...]
    raw_score: str | None
    known_raw_score: str
    mapped_weight: str
    observed_weight: str
    active_weight: str
    missing_security_ids: tuple[str, ...]
    constituent_effective_n: str
    hhi: str
    cutoff_utc: str
    decision_session_index: int
    authority: tuple[tuple[str, bool], ...] = AUTHORITY


@dataclass(frozen=True)
class TargetWeight:
    etf_id: str
    weight: str
    reason: str


@dataclass(frozen=True)
class TargetResult:
    targets: tuple[TargetWeight, ...]
    cash_weight: str
    addition_weight: str
    reduction_weight: str
    cutoff_utc: str
    decision_session_index: int
    mode: str = "synthetic-fixture-only"
    authority: tuple[tuple[str, bool], ...] = AUTHORITY


def _fail(reason):
    raise FixtureScoringError(reason)


def _sequence(value, maximum=4096):
    if type(value) not in (list, tuple) or len(value) > maximum:
        _fail("invalid_fixture_collection")
    return value


def _schema(value, keys, reason="invalid_fixture_schema"):
    if type(value) is not dict or len(value) != len(keys) or any(type(k) is not str for k in value) or set(value) != keys:
        _fail(reason)


def _id(value):
    if type(value) is not str or len(value) > 128 or re.fullmatch(r"SYNTHETIC-[A-Z0-9][A-Z0-9_-]*", value) is None:
        _fail("invalid_fixture_identity")
    return value


def _index(value):
    if type(value) is not int or not 0 <= value <= 1000000:
        _fail("invalid_fixture_session")
    return value


def _utc(value):
    if type(value) is not str or len(value) > 64:
        _fail("invalid_fixture_clock")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        _fail("invalid_fixture_clock")


def _num(value, *, positive=False, weight=False, emitted=False):
    if type(value) is not str or len(value) > (256 if emitted else 96) or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value) is None:
        _fail("invalid_fixture_decimal")
    try:
        number = Decimal(value)
    except InvalidOperation:
        _fail("invalid_fixture_decimal")
    if not number.is_finite() or number.copy_abs() > Decimal("1e128" if emitted else "1e24") or (positive and number <= 0) or (weight and not 0 <= number <= 1):
        _fail("invalid_fixture_decimal")
    return number


def _text(value):
    if not value:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _fraction(value):
    if type(value) is not str or len(value) > 5000 or re.fullmatch(r"-?[0-9]+(?:/[1-9][0-9]*)?", value) is None:
        _fail("invalid_fixture_rational")
    if any(len(component.lstrip("-")) > 2500 for component in value.split("/")):
        _fail("fixture_rational_resource_limit")
    number = Fraction(value)
    _ftext(number)
    return number


def _ftext(value):
    if type(value) is not Fraction:
        _fail("invalid_fixture_rational")
    if value.numerator.bit_length() > 8192 or value.denominator.bit_length() > 8192:
        _fail("fixture_rational_resource_limit")
    return str(value.numerator) if value.denominator == 1 else str(value.numerator) + "/" + str(value.denominator)


def _authority(value):
    if type(value) is not tuple or len(value) != len(AUTHORITY):
        _fail("invalid_fixture_authority")
    for item, expected in zip(value, AUTHORITY):
        if type(item) is not tuple or len(item) != 2 or type(item[0]) is not str or item[0] != expected[0] or item[1] is not False:
            _fail("invalid_fixture_authority")


def _state(value, allowed, reason="invalid_fixture_state"):
    if type(value) is not str or value not in allowed:
        _fail(reason)


def _reasons(value):
    if type(value) is not tuple or len(value) > 16 or any(type(reason) is not str or len(reason) > 128 for reason in value):
        _fail("invalid_fixture_reasons")


def _control_value(name, value):
    number = _num(value)
    if (name in CONTROL_NAMES[:3] and number < -1) or (name == CONTROL_NAMES[-1] and number < 0):
        _fail("invalid_fixture_control_value")
    return number


def _group(value):
    if type(value) is not str or len(value) > 137:
        _fail("invalid_fixture_category")
    kind, _, identity = value.partition(":")
    if kind not in ("industry", "sector"):
        _fail("invalid_fixture_category")
    try:
        _id(identity)
    except FixtureScoringError:
        _fail("invalid_fixture_category")


def _median(values):
    ordered = sorted(values)
    if not ordered:
        _fail("empty_fixture_median")
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _neff(values):
    denominator = sum(v * v for v in values)
    return sum(abs(v) for v in values) ** 2 / denominator if denominator else Decimal(0)


def _configuration(config):
    _schema(config, _CONFIG)
    parsed = {k: _num(config[k], positive=k in ("clip_absolute", "min_price", "min_adv"), weight=k.startswith("max_"))
              for k in _CONFIG if "min_total" not in k and "min_active" not in k}
    for group in ("industry", "sector"):
        total, active = config[group + "_min_total"], config[group + "_min_active"]
        if type(total) is not int or type(active) is not int or not 2 <= total <= 4096 or not 1 <= active <= total:
            _fail("invalid_fixture_group_minima")
        parsed[group + "_min_total"], parsed[group + "_min_active"] = total, active
    return parsed


def _universe_row(row, cutoff, decision, config):
    _schema(row, _UNIVERSE)
    for key in ("security_id", "basis_id", "industry_id", "sector_id"):
        _id(row[key])
    if type(row["instrument_type"]) is not str or row["instrument_type"] not in ("common_stock", "adr") or row["primary_listing"] is not True or type(row["venue"]) is not str or row["venue"] not in ("XNYS", "XNAS", "XASE"):
        _fail("ineligible_fixture_universe")
    if _utc(row["available_at_utc"]) > cutoff or _index(row["effective_session_index"]) > decision:
        _fail("future_fixture_classification")
    if row["instrument_type"] == "adr":
        _id(row["underlying_id"])
        _num(row["adr_ratio"], positive=True)
    elif row["adr_ratio"] is not None or row["underlying_id"] is not None:
        _fail("ambiguous_fixture_share_basis")
    controls = row["controls"]
    _schema(controls, _CONTROLS, "missing_control")
    _schema(controls["values"], set(CONTROL_NAMES), "missing_control")
    if controls["complete"] is not True or controls["rating_inventory_complete"] is not True or controls["catalyst_inventory_complete"] is not True:
        _fail("incomplete_fixture_controls")
    _id(controls["evidence_id"])
    _id(controls["rating_state"])
    _id(controls["catalyst_state"])
    if _utc(controls["available_at_utc"]) >= cutoff or _index(controls["effective_session_index"]) != decision - 1:
        _fail("unavailable_fixture_controls")
    values = tuple((name, _text(_control_value(name, controls["values"][name]))) for name in CONTROL_NAMES)
    if (_num(controls["price"], positive=True) < config["min_price"] or _num(controls["adv"], positive=True) < config["min_adv"] or
            _num(controls["spread_fraction"], weight=True) > config["max_spread_fraction"] or
            _num(controls["capacity_fraction"], weight=True) > config["max_capacity_fraction"]):
        _fail("fixture_control_screen_failed")
    return values


def _event_value(record, universe, decision, clip):
    age = decision - record["eligible_session_index"]
    if age < 0:
        _fail("future_eligible_session")
    p = record["payload"]
    _schema(p, _PRICE, "invalid_fixture_event_payload")
    for key in ("target_basis_id", "price_basis_id"):
        _id(p[key])
    if p["target_basis_id"] != p["price_basis_id"] or p["target_basis_id"] != universe["basis_id"]:
        _fail("incompatible_fixture_price_basis")
    information = _utc(p["information_at_utc"])
    if _utc(p["price_available_at_utc"]) >= information or information > record["available"]:
        _fail("invalid_pre_event_price_clock")
    info_index, price_index = _index(p["information_session_index"]), _index(p["price_session_index"])
    if price_index != info_index - 1 or info_index > record["eligible_session_index"]:
        _fail("invalid_pre_event_price_session")
    delta = (_num(p["new_target"], positive=True) - _num(p["prior_target"], positive=True)) / _num(p["pre_event_price"], positive=True)
    clipped = min(clip, max(-clip, delta))
    decay = Decimal(0) if age > 80 else Decimal(2) ** (-Decimal(age) / Decimal(20))
    return clipped * decay, age, "VALID_ZERO" if delta == 0 else "VALID_NONZERO"


def score_fixture_stocks(universe, versions, *, cutoff_utc, decision_session_index, config, inventory_complete):
    """Complete fixture universe, cutoff-visible versions, no real-data admission."""
    if inventory_complete is not True:
        _fail("incomplete_fixture_inventory")
    cutoff, decision = _utc(cutoff_utc), _index(decision_session_index)
    with localcontext(_CTX):
        config = _configuration(config)
        stocks, controls, failures = {}, {}, {}
        for row in _sequence(universe, 1024):
            if type(row) is not dict or any(type(k) is not str for k in row) or "security_id" not in row:
                _fail("invalid_fixture_schema")
            sid = _id(row["security_id"])
            if sid in stocks:
                _fail("duplicate_fixture_security")
            stocks[sid] = row
            try:
                controls[sid] = _universe_row(row, cutoff, decision, config)
            except FixtureScoringError as exc:
                failures[sid] = str(exc)
        groups, dispositions = {}, []
        for row in _sequence(versions, 8192):
            _schema(row, _EVENT)
            for key in ("lineage_id", "version_id", "security_id", "institution_id"):
                _id(row[key])
            if row["catalyst_id"] is not None:
                _id(row["catalyst_id"])
            _index(row["eligible_session_index"])
            available = _utc(row["available_at_utc"])
            if available > cutoff:
                dispositions.append(VersionScore(row["lineage_id"], row["version_id"], row["security_id"], row["institution_id"], "NOT_VISIBLE", ("version_after_cutoff",), None, None))
                continue
            if row["security_id"] not in stocks:
                _fail("unknown_fixture_event_security")
            snapshot = {key: row[key] for key in _EVENT}
            snapshot["available"] = available
            groups.setdefault(row["lineage_id"], []).append(snapshot)
        units = {}
        for lineage in sorted(groups):
            records = groups[lineage]
            identity = {(r["security_id"], r["institution_id"], r["eligible_session_index"], r["catalyst_id"]) for r in records}
            collision = len(identity) != 1 or len({r["version_id"] for r in records}) != len(records) or len({r["available"] for r in records}) != len(records)
            latest = max(records, key=lambda r: r["available"])
            for record in records:
                sid, inst = record["security_id"], record["institution_id"]
                if collision:
                    failures[sid] = "fixture_lineage_collision"
                    dispositions.append(VersionScore(lineage, record["version_id"], sid, inst, "REFUSED", ("fixture_lineage_collision",), None, None))
                    continue
                if record is not latest:
                    dispositions.append(VersionScore(lineage, record["version_id"], sid, inst, "SUPERSEDED", (), None, None))
                    continue
                if sid in failures:
                    dispositions.append(VersionScore(lineage, record["version_id"], sid, inst, "REFUSED", (failures[sid],), None, None))
                    continue
                try:
                    value, age, state = _event_value(record, stocks[sid], decision, config["clip_absolute"])
                    catalyst = record["catalyst_id"] or ("UNKNOWN:" + sid + ":" + str(record["eligible_session_index"]))
                    key = (sid, inst, record["eligible_session_index"], catalyst)
                    units.setdefault(key, []).append(value)
                    dispositions.append(VersionScore(lineage, record["version_id"], sid, inst, state, ("expired_zero_weight",) if age > 80 else (), age, _text(value)))
                except FixtureScoringError as exc:
                    failures[sid] = str(exc)
                    dispositions.append(VersionScore(lineage, record["version_id"], sid, inst, "REFUSED", (str(exc),), None, None))
        strengths, breadth = {}, {}
        for sid in sorted(stocks):
            if sid in failures:
                continue
            institutions, catalysts = {}, {}
            for (security, institution, _, catalyst), values in sorted(units.items()):
                if security == sid:
                    unit = _median(values)
                    institutions[institution] = institutions.get(institution, Decimal(0)) + unit
                    catalysts[catalyst] = catalysts.get(catalyst, Decimal(0)) + unit
            strengths[sid] = _median(list(institutions.values())) if institutions else Decimal(0)
            ni, nc = _neff(list(institutions.values())), _neff(list(catalysts.values()))
            breadth[sid] = (_text(ni), _text(nc), _text(min(ni, nc)))
        rows = []
        for sid in sorted(stocks):
            if sid in failures:
                rows.append(StockScore(sid, "REFUSED", (failures[sid],), None, None, None, (), None, None, "0", "0", "0"))
                continue
            strength, normalized, group_id = strengths[sid], None, None
            for group in ("industry", "sector"):
                members = [s for s in strengths if stocks[s][group + "_id"] == stocks[sid][group + "_id"]]
                values = [strengths[s] for s in members]
                if len(values) < config[group + "_min_total"] or sum(v != 0 for v in values) < config[group + "_min_active"]:
                    continue
                center = _median(values)
                mad = _median([abs(v - center) for v in values])
                if mad > 0:
                    normalized = _text((strength - center) / (Decimal("1.4826") * mad))
                    group_id = group + ":" + stocks[sid][group + "_id"]
                    break
            state = ("VALID_ZERO" if strength == 0 else "VALID_NONZERO") if normalized is not None else "REFUSED"
            c = stocks[sid]["controls"]
            rows.append(StockScore(sid, state, () if normalized is not None else ("normalization_unavailable",), _text(strength), normalized, group_id,
                                   controls[sid], c["rating_state"], c["catalyst_state"], *breadth[sid]))
        return StockResult(tuple(rows), tuple(sorted(dispositions, key=lambda v: (v.security_id, v.lineage_id, v.version_id, v.state))), cutoff.isoformat(), decision)


def _lcm(left, right):
    a, b = left, right
    while b:
        a, b = b, a % b
    return left // a * right


def _solve_exact(matrix, response):
    dimension = len(matrix[0])
    if dimension > 24 or len(matrix) < dimension:
        _fail("singular_control_design")
    gram = [[sum(row[i] * row[j] for row in matrix) for j in range(dimension)] +
            [sum(row[i] * y for row, y in zip(matrix, response))] for i in range(dimension)]
    scale = 1
    for row in gram:
        for value in row:
            scale = _lcm(scale, value.denominator)
    integer = [[int(value * scale) for value in row] for row in gram]
    previous = 1
    for column in range(dimension - 1):
        pivot_row = next((r for r in range(column, dimension) if integer[r][column]), None)
        if pivot_row is None:
            _fail("singular_control_design")
        integer[column], integer[pivot_row] = integer[pivot_row], integer[column]
        pivot = integer[column][column]
        for r in range(column + 1, dimension):
            for c in range(column + 1, dimension + 1):
                numerator = integer[r][c] * pivot - integer[r][column] * integer[column][c]
                if numerator % previous:
                    _fail("invalid_fraction_free_elimination")
                integer[r][c] = numerator // previous
            integer[r][column] = 0
        previous = pivot
    coefficients = [Fraction(0)] * dimension
    for row in range(dimension - 1, -1, -1):
        if not integer[row][row]:
            _fail("singular_control_design")
        coefficients[row] = (Fraction(integer[row][-1]) - sum(integer[row][c] * coefficients[c] for c in range(row + 1, dimension))) / integer[row][row]
    return coefficients


def residualize_fixture_scores(result):
    """Exact pre-rank OLS on identical complete fixture rows; no outcomes."""
    if type(result) is not StockResult or type(result.mode) is not str or result.mode != "synthetic-fixture-only":
        _fail("invalid_fixture_stock_result")
    _authority(result.authority)
    _utc(result.cutoff_utc)
    _index(result.decision_session_index)
    if type(result.rows) is not tuple:
        _fail("invalid_fixture_stock_result")
    _sequence(result.rows, 1024)
    eligible = []
    for row in result.rows:
        if type(row) is not StockScore:
            _fail("invalid_fixture_stock_row")
        _id(row.security_id)
        _state(row.state, ("VALID_ZERO", "VALID_NONZERO", "REFUSED"), "invalid_fixture_stock_row")
        _reasons(row.reasons)
        if row.strength is not None:
            _num(row.strength, emitted=True)
        if row.state in ("VALID_ZERO", "VALID_NONZERO"):
            if (type(row.controls) is not tuple or len(row.controls) != len(CONTROL_NAMES) or
                    any(type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str for pair in row.controls) or
                    tuple(name for name, _ in row.controls) != CONTROL_NAMES or type(row.group_id) is not str or len(row.group_id) > 256):
                _fail("missing_control")
            _num(row.normalized_score, emitted=True)
            _group(row.group_id)
            for name, value in row.controls:
                _control_value(name, value)
            _id(row.rating_state)
            _id(row.catalyst_state)
            eligible.append(row)
    if len({r.security_id for r in result.rows}) != len(result.rows):
        _fail("duplicate_fixture_security")
    columns, coefficients, residuals, failure = ["intercept", *CONTROL_NAMES], [], {}, None
    with localcontext(_CTX):
        try:
            if not eligible:
                _fail("empty_eligible_cross_section")
            continuous = []
            for index in range(len(CONTROL_NAMES)):
                values = [_num(r.controls[index][1]) for r in eligible]
                center = _median(values)
                mad = _median([abs(v - center) for v in values])
                if mad == 0:
                    _fail("zero_control_mad")
                continuous.append([Fraction((v - center) / (Decimal("1.4826") * mad)) for v in values])
            categories = [("group", [r.group_id for r in eligible]), ("rating", [r.rating_state for r in eligible]), ("catalyst", [r.catalyst_state for r in eligible])]
            dummy_columns = []
            for name, values in categories:
                if any(type(value) is not str or len(value) > 256 for value in values):
                    _fail("invalid_fixture_category")
                for level in sorted(set(values), key=lambda v: v.encode("utf-8"))[1:]:
                    columns.append(name + ":" + level)
                    if len(columns) > 24:
                        _fail("singular_control_design")
                    dummy_columns.append([Fraction(int(v == level)) for v in values])
            matrix = [[Fraction(1), *(col[index] for col in continuous), *(col[index] for col in dummy_columns)] for index in range(len(eligible))]
            response = [Fraction(_num(r.normalized_score, emitted=True)) for r in eligible]
            coefficients = _solve_exact(matrix, response)
            residuals = {row.security_id: y - sum(x * beta for x, beta in zip(design, coefficients)) for row, y, design in zip(eligible, response, matrix)}
            for value in (*coefficients, *residuals.values()):
                _ftext(value)
        except FixtureScoringError as exc:
            failure = str(exc)
            coefficients, residuals = [], {}
        ordered = sorted(residuals.values())
        rows = []
        for row in result.rows:
            if row.security_id not in residuals:
                rows.append(RankRow(row.security_id, "REFUSED", (failure,) if failure else row.reasons, None, None, row.strength))
                continue
            score = residuals[row.security_id]
            first, last = ordered.index(score) + 1, len(ordered) - list(reversed(ordered)).index(score)
            percentile = (Fraction(first + last, 2) - Fraction(1, 2)) / len(ordered)
            rows.append(RankRow(row.security_id, "VALID_ZERO" if score == 0 else "VALID_NONZERO", (), _ftext(score), _ftext(percentile), row.strength))
        return RankResult(tuple(sorted(rows, key=lambda r: r.security_id)), tuple(columns), tuple(_ftext(v) for v in coefficients), result.cutoff_utc, result.decision_session_index)


def project_fixture_etf(book, stock_result, *, cutoff_utc, decision_session_index, max_age_sessions):
    """Complete-book absolute mapping >=99%; raw weighted residual, no uplift."""
    cutoff, decision = _utc(cutoff_utc), _index(decision_session_index)
    if type(stock_result) is not RankResult or type(stock_result.mode) is not str or stock_result.mode != "synthetic-fixture-only":
        _fail("fixture_stock_epoch_mismatch")
    _authority(stock_result.authority)
    if type(stock_result.rows) is not tuple:
        _fail("invalid_fixture_rank_result")
    if _utc(stock_result.cutoff_utc).isoformat() != cutoff.isoformat() or _index(stock_result.decision_session_index) != decision:
        _fail("fixture_stock_epoch_mismatch")
    if type(max_age_sessions) is not int or not 0 <= max_age_sessions <= 80:
        _fail("invalid_fixture_holdings_age")
    keys = {"etf_id", "product_type", "complete", "available_at_utc", "captured_at_utc", "effective_session_index", "cash_weight", "residual_weight", "cash_evidence_id", "residual_evidence_id", "holdings"}
    _schema(book, keys)
    etf_id = _id(book["etf_id"])
    mapped = observed = active = raw = Decimal(0)
    missing, weights, failure = [], [], None
    with localcontext(_CTX):
        try:
            if book["complete"] is not True or type(book["product_type"]) is not str or book["product_type"] != "unlevered_equity_etf":
                _fail("ineligible_or_incomplete_fixture_etf")
            if not _utc(book["available_at_utc"]) <= _utc(book["captured_at_utc"]) <= cutoff:
                _fail("unavailable_fixture_holdings")
            age = decision - _index(book["effective_session_index"])
            if not 0 <= age <= max_age_sessions:
                _fail("stale_fixture_holdings")
            cash, residual = _num(book["cash_weight"], weight=True), _num(book["residual_weight"], weight=True)
            _id(book["cash_evidence_id"])
            _id(book["residual_evidence_id"])
            mapped = cash + residual
            total, seen = cash + residual, set()
            scores = {}
            for row in _sequence(stock_result.rows, 1024):
                if type(row) is not RankRow:
                    _fail("invalid_fixture_rank_row")
                _id(row.security_id)
                _state(row.state, ("VALID_ZERO", "VALID_NONZERO", "REFUSED"))
                _reasons(row.reasons)
                if row.security_id in scores:
                    _fail("duplicate_fixture_security")
                scores[row.security_id] = row
            for holding in _sequence(book["holdings"], 8192):
                _schema(holding, {"security_id", "weight", "mapped", "mapping_evidence_id"})
                weight = _num(holding["weight"], weight=True)
                total += weight
                weights.append(weight)
                if type(holding["mapped"]) is not bool:
                    _fail("invalid_fixture_mapping")
                if holding["mapped"]:
                    sid = _id(holding["security_id"])
                    _id(holding["mapping_evidence_id"])
                    if sid in seen:
                        _fail("duplicate_fixture_holding")
                    seen.add(sid)
                    mapped += weight
                    row = scores.get(sid)
                    if row is not None and row.state in ("VALID_ZERO", "VALID_NONZERO"):
                        value = _fraction(row.score)
                        raw += weight * Decimal(value.numerator) / Decimal(value.denominator)
                        observed += weight
                        if _num(row.strength, emitted=True) != 0:
                            active += weight
                    else:
                        missing.append(sid)
                elif holding["security_id"] is not None or holding["mapping_evidence_id"] is not None:
                    _fail("ambiguous_fixture_mapping")
            if total != 1:
                _fail("incomplete_fixture_weight_accounting")
            if mapped < Decimal("0.99"):
                _fail("mapping_below_99_percent")
            if missing:
                _fail("missing_fixture_stock_features")
        except FixtureScoringError as exc:
            failure = str(exc)
        hhi = sum(w * w for w in weights)
        state = "REFUSED" if failure else ("MISSING" if observed == 0 else "VALID_ZERO" if raw == 0 else "VALID_NONZERO")
        return ETFProjection(etf_id, state, (failure,) if failure else (), None if failure or observed == 0 else _text(raw), _text(raw), _text(mapped), _text(observed), _text(active), tuple(sorted(missing)), _text(_neff(weights)), _text(hhi), cutoff.isoformat(), decision)


def build_fixture_targets(candidates, prior_positions, *, cutoff_utc, decision_session_index, max_names, name_cap, sector_cap, peer_cap, additions_cap):
    """Desired-weight fixture allocator; additions capped, zero/risk exits intact.

    Stable ID order is a fixture-only allocation choice. No weight uplift or
    automatic promotion. Additions turnover is positive weight change; risk
    reductions/forced zero exits are reported separately and never blocked.
    """
    cutoff, decision = _utc(cutoff_utc), _index(decision_session_index)
    if type(max_names) is not int or not 1 <= max_names <= 16:
        _fail("invalid_fixture_name_limit")
    with localcontext(_CTX):
        caps = [_num(value, weight=True) for value in (name_cap, sector_cap, peer_cap, additions_cap)]
        prior, candidate_map = {}, {}
        for item in _sequence(prior_positions, 256):
            _schema(item, {"etf_id", "weight"})
            sid = _id(item["etf_id"])
            if sid in prior:
                _fail("duplicate_fixture_position")
            prior[sid] = _num(item["weight"], weight=True)
        if sum(prior.values()) > 1:
            _fail("invalid_fixture_prior_weight")
        for item in _sequence(candidates, 256):
            _schema(item, {"etf_id", "state", "desired_weight", "sector_id", "peer_id"})
            sid = _id(item["etf_id"])
            _id(item["sector_id"])
            _id(item["peer_id"])
            if sid in candidate_map or type(item["state"]) is not str or item["state"] not in ("VALID_ZERO", "VALID_NONZERO", "MISSING", "REFUSED", "INELIGIBLE"):
                _fail("invalid_fixture_candidate")
            candidate_map[sid] = (_num(item["desired_weight"], weight=True), item)
        target, sectors, peers = {}, {}, {}
        additions = reductions = total = Decimal(0)
        names = 0
        for sid in sorted(set(prior) | set(candidate_map)):
            item = candidate_map.get(sid)
            weight = Decimal(0)
            reason = "forced_zero_exit" if sid in prior else "ineligible_zero"
            if item is not None and item[1]["state"] in ("VALID_ZERO", "VALID_NONZERO") and names < max_names:
                desired, metadata = item
                sector, peer = metadata["sector_id"], metadata["peer_id"]
                weight = min(desired, caps[0], caps[1] - sectors.get(sector, Decimal(0)), caps[2] - peers.get(peer, Decimal(0)), 1 - total)
                weight = min(weight, prior.get(sid, Decimal(0)) + caps[3] - additions)
                weight = max(Decimal(0), weight)
                sectors[sector], peers[peer] = sectors.get(sector, Decimal(0)) + weight, peers.get(peer, Decimal(0)) + weight
                if weight > 0:
                    names += 1
                    reason = "bounded_fixture_target"
            change = weight - prior.get(sid, Decimal(0))
            additions += max(Decimal(0), change)
            reductions += max(Decimal(0), -change)
            total += weight
            target[sid] = TargetWeight(sid, _text(weight), reason)
        return TargetResult(tuple(target[sid] for sid in sorted(target)), _text(1 - total), _text(additions), _text(reductions), cutoff.isoformat(), decision)


def fixture_target_body(result):
    """Primitive in-memory identity body, not a published/admitted packet."""
    if type(result) is not TargetResult or type(result.mode) is not str or result.mode != "synthetic-fixture-only":
        _fail("invalid_fixture_target_result")
    _authority(result.authority)
    _utc(result.cutoff_utc)
    _index(result.decision_session_index)
    if type(result.targets) is not tuple:
        _fail("invalid_fixture_target_result")
    seen, total = set(), Decimal(0)
    with localcontext(_CTX):
        for row in _sequence(result.targets, 512):
            if type(row) is not TargetWeight:
                _fail("invalid_fixture_target_result")
            sid = _id(row.etf_id)
            if sid in seen or type(row.reason) is not str or row.reason not in ("forced_zero_exit", "ineligible_zero", "bounded_fixture_target"):
                _fail("invalid_fixture_target_result")
            seen.add(sid)
            total += _num(row.weight, weight=True, emitted=True)
        if total + _num(result.cash_weight, weight=True, emitted=True) != 1:
            _fail("invalid_fixture_target_accounting")
        _num(result.addition_weight, weight=True, emitted=True)
        _num(result.reduction_weight, weight=True, emitted=True)
    return {"schema": "tpr-d2-fixture-targets-v1", "mode": result.mode, "authority": dict(AUTHORITY),
            "cutoff_utc": result.cutoff_utc, "decision_session_index": result.decision_session_index,
            "cash_weight": result.cash_weight, "addition_weight": result.addition_weight, "reduction_weight": result.reduction_weight,
            "targets": [{"etf_id": row.etf_id, "weight": row.weight, "reason": row.reason} for row in result.targets]}


def fixture_target_sha256(result):
    payload = (json.dumps(fixture_target_body(result), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
