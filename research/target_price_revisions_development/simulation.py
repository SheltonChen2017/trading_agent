"""Pure invented order-transition contract; never a backtest or order adapter.

The supplied calendar, marks, fees and slippage are fixture choices, not market
facts. All arithmetic is exact Fraction-of-Decimal arithmetic. A conservative
cost reserve underinvests: fees for at most one order per target plus slippage
on twice the initial marked NAV. Missing marks block increases, not priced
explicit zero exits. Supplied in-memory history/checkpoints are not protected
durable custody, authentication, or permission to process any real data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re

from .scoring import FixtureScoringError, TargetResult, TargetWeight, fixture_target_body, fixture_target_sha256

AUTHORITY = (("canonical_admission", False), ("point_in_time_data", False),
             ("outcomes", False), ("qc", False), ("trading", False))
MODE = "synthetic-fixture-only"
# Resource bounds are software fixture policy, not source/operator budgets.
MAX_ASSETS = 128
MAX_SHARES = 1_000_000_000
MAX_TRANSITIONS = 32
MAX_RECEIPT_BYTES = 128 * 1024
MAX_HISTORY_BYTES = 1024 * 1024
_TARGET_KEYS = {"schema", "mode", "authority", "cutoff_utc", "decision_session_index",
                "cash_weight", "addition_weight", "reduction_weight", "targets"}
_INPUT_KEYS = {"schema", "prior_state_sha256", "target", "target_sha256", "quotes",
               "open_utc", "open_session_index", "fee_per_order", "slippage_bps", "name_cap"}
_RECEIPT_KEYS = {"schema", "sequence", "before", "inputs", "input_sha256", "after"}
_REASONS = {"filled", "unchanged", "already_zero", "missing_quote", "stale_quote", "future_quote",
            "incomplete_portfolio_marks", "proceeds_below_fee", "insufficient_cash_or_whole_share",
            "share_resource_cap"}


class FixtureSimulationError(ValueError):
    """A named refusal of the synthetic-only transition contract."""


@dataclass(frozen=True)
class FixturePosition:
    etf_id: str
    shares: int


@dataclass(frozen=True)
class FixtureFill:
    side: str
    etf_id: str
    shares: int
    unit_price: str
    fee: str


@dataclass(frozen=True)
class FixtureDisposition:
    etf_id: str
    reason: str


@dataclass(frozen=True)
class FixtureReceipt:
    payload: bytes
    sha256: str


@dataclass(frozen=True)
class FixturePortfolio:
    cash: str
    positions: tuple[FixturePosition, ...]
    receipts: tuple[FixtureReceipt, ...]
    sha256: str
    mode: str = MODE
    authority: tuple[tuple[str, bool], ...] = AUTHORITY


@dataclass(frozen=True)
class FixtureTransition:
    portfolio: FixturePortfolio
    fills: tuple[FixtureFill, ...]
    dispositions: tuple[FixtureDisposition, ...]
    receipt: FixtureReceipt
    replayed: bool
    transition_complete: bool
    mode: str = MODE
    real_backtest_ready: bool = False
    authority: tuple[tuple[str, bool], ...] = AUTHORITY


def _fail(reason):
    raise FixtureSimulationError(reason)


def _schema(value, keys):
    if type(value) is not dict or len(value) != len(keys) or any(type(k) is not str for k in value) or set(value) != keys:
        _fail("invalid closed fixture schema")


def _id(value):
    if type(value) is not str or len(value) > 128 or re.fullmatch(r"SYNTHETIC-[A-Z0-9][A-Z0-9_-]*", value) is None:
        _fail("invalid synthetic identity")
    return value


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        _fail("invalid fixture content identity")
    return value


def _index(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        _fail("invalid synthetic session")
    return value


def _shares(value):
    if type(value) is not int or not 0 <= value <= MAX_SHARES:
        _fail("invalid whole-share fixture position")
    return value


def _utc(value):
    if type(value) is not str or len(value) > 64:
        _fail("invalid synthetic clock")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        _fail("invalid synthetic clock")


def _num(value, *, positive=False, maximum=Fraction(10**24)):
    if type(value) is not str or len(value) > 256 or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) is None:
        _fail("invalid finite nonnegative fixture decimal")
    number = Fraction(Decimal(value))
    if number > maximum or (positive and not number):
        _fail("invalid bounded fixture decimal")
    return number


def _text(value):
    """Emit terminating exact decimal text without caller Decimal context."""
    if value < 0:
        _fail("negative fixture accounting")
    numerator, denominator = value.numerator, value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        _fail("nonterminating fixture accounting")
    scale = max(twos, fives)
    digits = str(numerator * 2 ** (scale - twos) * 5 ** (scale - fives))
    if scale:
        digits = digits.zfill(scale + 1)
        digits = digits[:-scale] + "." + digits[-scale:]
        digits = digits.rstrip("0").rstrip(".")
    return digits


def _bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _digest(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _authority(value):
    if type(value) is not tuple or len(value) != len(AUTHORITY):
        _fail("invalid zero-authority fixture state")
    for item, expected in zip(value, AUTHORITY):
        if type(item) is not tuple or len(item) != 2 or type(item[0]) is not str or item[0] != expected[0] or item[1] is not False:
            _fail("invalid zero-authority fixture state")


def _balances(cash, positions):
    return {"cash": cash, "positions": [{"etf_id": sid, "shares": shares} for sid, shares in sorted(positions.items())]}


def _read_balances(value):
    _schema(value, {"cash", "positions"})
    cash = _num(value["cash"])
    if _text(cash) != value["cash"] or type(value["positions"]) is not list or len(value["positions"]) > MAX_ASSETS:
        _fail("invalid fixture state balances")
    positions, order = {}, []
    for row in value["positions"]:
        _schema(row, {"etf_id", "shares"})
        sid = _id(row["etf_id"])
        if sid in positions:
            _fail("duplicate fixture state identity")
        positions[sid] = _shares(row["shares"])
        order.append(sid)
    if order != sorted(order):
        _fail("noncanonical fixture state order")
    return cash, positions


def _state_body(balances, receipt_hashes):
    return {"schema": "tpr-synthetic-portfolio-v1", "mode": MODE, "authority": dict(AUTHORITY),
            "balances": balances, "receipts": receipt_hashes}


def _portfolio(balances, receipts):
    cash, positions = _read_balances(balances)
    return FixturePortfolio(_text(cash), tuple(FixturePosition(sid, shares) for sid, shares in positions.items()),
                            receipts, _digest(_state_body(balances, [receipt.sha256 for receipt in receipts])))


def freeze_fixture_portfolio(cash, rows):
    """Freeze invented initial balances; grants no real capital/order authority."""
    number = _num(cash)
    if type(rows) is not tuple or len(rows) > MAX_ASSETS:
        _fail("invalid fixture position collection")
    positions = {}
    for row in rows:
        _schema(row, {"etf_id", "shares"})
        sid = _id(row["etf_id"])
        if sid in positions:
            _fail("duplicate fixture position")
        positions[sid] = _shares(row["shares"])
    return _portfolio(_balances(_text(number), positions), ())


def _target(value):
    try:
        body = fixture_target_body(value)
        target_hash = fixture_target_sha256(value)
    except FixtureScoringError as exc:
        raise FixtureSimulationError("invalid precomputed fixture targets") from exc
    if len(body["targets"]) > MAX_ASSETS:
        _fail("fixture target resource bound")
    # Independent exact-rational accounting and reason consistency, not scores.
    total = Fraction(0)
    for row in body["targets"]:
        weight = _num(row["weight"], maximum=Fraction(1))
        total += weight
        if row["reason"] in ("forced_zero_exit", "ineligible_zero") and weight:
            _fail("nonzero refused fixture target")
    if total + _num(body["cash_weight"], maximum=Fraction(1)) != 1:
        _fail("invalid exact fixture target accounting")
    return body, target_hash


def _read_target(value):
    _schema(value, _TARGET_KEYS)
    if type(value["schema"]) is not str or value["schema"] != "tpr-d2-fixture-targets-v1":
        _fail("invalid fixture target schema")
    _schema(value["authority"], set(dict(AUTHORITY)))
    if any(value["authority"][key] is not False for key, _ in AUTHORITY):
        _fail("invalid fixture target authority")
    if type(value["targets"]) is not list or len(value["targets"]) > MAX_ASSETS:
        _fail("invalid fixture target collection")
    rows = []
    for row in value["targets"]:
        _schema(row, {"etf_id", "weight", "reason"})
        rows.append(TargetWeight(row["etf_id"], row["weight"], row["reason"]))
    result = TargetResult(tuple(rows), value["cash_weight"], value["addition_weight"], value["reduction_weight"],
                          value["cutoff_utc"], value["decision_session_index"], value["mode"], AUTHORITY)
    return _target(result)


def _quotes(value):
    if type(value) is not dict or len(value) > MAX_ASSETS or any(type(k) is not str for k in value):
        _fail("invalid fixture quotes")
    result = []
    for sid, row in value.items():
        _id(sid)
        _schema(row, {"price", "observed_at_utc"})
        _num(row["price"], positive=True)
        _utc(row["observed_at_utc"])
        result.append({"etf_id": sid, "price": row["price"], "observed_at_utc": row["observed_at_utc"]})
    return sorted(result, key=lambda row: row["etf_id"])


def _read_inputs(value):
    _schema(value, _INPUT_KEYS)
    if type(value["schema"]) is not str or value["schema"] != "tpr-synthetic-transition-inputs-v1":
        _fail("invalid fixture transition schema")
    _hash(value["prior_state_sha256"])
    body, target_hash = _read_target(value["target"])
    if _hash(value["target_sha256"]) != target_hash:
        _fail("fixture target content mismatch")
    opened = _utc(value["open_utc"])
    if value["open_utc"] != opened.isoformat() or _index(value["open_session_index"]) != body["decision_session_index"] + 1 or opened <= _utc(body["cutoff_utc"]):
        _fail("not the next synthetic eligible open")
    _num(value["fee_per_order"])
    _num(value["slippage_bps"], maximum=Fraction(1000))
    cap = _num(value["name_cap"], maximum=Fraction(1))
    if any(_num(row["weight"], maximum=Fraction(1)) > cap for row in body["targets"]):
        _fail("fixture target exceeds name cap")
    if type(value["quotes"]) is not list or len(value["quotes"]) > MAX_ASSETS:
        _fail("invalid fixture quote collection")
    quote_map = {}
    for row in value["quotes"]:
        _schema(row, {"etf_id", "price", "observed_at_utc"})
        sid = _id(row["etf_id"])
        if sid in quote_map:
            _fail("duplicate fixture quote")
        quote_map[sid] = {"price": row["price"], "observed_at_utc": row["observed_at_utc"]}
    if _quotes(quote_map) != value["quotes"]:
        _fail("noncanonical fixture quote order")
    if set(quote_map) - {row["etf_id"] for row in body["targets"]}:
        _fail("quote without a fixture target")
    return body, quote_map, opened


def _transition(before, inputs):
    """One deterministic invented accounting transition, also used on replay."""
    cash, positions = _read_balances(before)
    body, quote_map, opened = _read_inputs(inputs)
    weights = {row["etf_id"]: _num(row["weight"], maximum=Fraction(1)) for row in body["targets"]}
    if set(positions) - set(weights):
        _fail("missing prior target; no inferred exit")
    for sid in weights:
        positions.setdefault(sid, 0)
    fee = _num(inputs["fee_per_order"])
    slip = _num(inputs["slippage_bps"], maximum=Fraction(1000)) / 10000
    marks, refusals = {}, {}
    for sid in weights:
        quote = quote_map.get(sid)
        if quote is None:
            refusals[sid] = "missing_quote"
        elif _utc(quote["observed_at_utc"]) < opened:
            refusals[sid] = "stale_quote"
        elif _utc(quote["observed_at_utc"]) > opened:
            refusals[sid] = "future_quote"
        else:
            marks[sid] = _num(quote["price"], positive=True)
    complete_marks = all(not shares or sid in marks for sid, shares in positions.items())
    nav = cash + sum((shares * marks[sid] for sid, shares in positions.items() if shares and sid in marks), Fraction(0))
    budget = max(Fraction(0), nav - fee * len(weights) - 2 * slip * nav)
    desired, reasons = {}, {}
    for sid, weight in weights.items():
        if not weight and not positions[sid]:
            desired[sid], reasons[sid] = 0, "already_zero"
        elif sid not in marks:
            desired[sid], reasons[sid] = positions[sid], refusals[sid]
        elif not weight:
            desired[sid] = 0
        elif not complete_marks:
            desired[sid], reasons[sid] = positions[sid], "incomplete_portfolio_marks"
        else:
            quantity = (weight * budget) // marks[sid]
            desired[sid] = min(quantity, MAX_SHARES)
            if quantity > MAX_SHARES:
                reasons[sid] = "share_resource_cap"
    fills = []
    # All valid reductions precede all additions; no order API is called.
    for sid in sorted(desired):
        quantity = positions[sid] - desired[sid]
        if quantity <= 0:
            continue
        unit = marks[sid] * (1 - slip)
        proceeds = quantity * unit
        if proceeds < fee:
            reasons[sid] = "proceeds_below_fee"
            continue
        cash += proceeds - fee
        positions[sid] -= quantity
        fills.append({"side": "sell", "etf_id": sid, "shares": quantity, "unit_price": _text(unit), "fee": _text(fee)})
        reasons.setdefault(sid, "filled")
    for sid in sorted(desired):
        quantity = desired[sid] - positions[sid]
        if quantity <= 0:
            continue
        unit = marks[sid] * (1 + slip)
        affordable = max(0, (cash - fee) // unit)
        executed = min(quantity, affordable)
        if not executed:
            reasons[sid] = "insufficient_cash_or_whole_share"
            continue
        cash -= executed * unit + fee
        positions[sid] += executed
        fills.append({"side": "buy", "etf_id": sid, "shares": executed, "unit_price": _text(unit), "fee": _text(fee)})
        reasons.setdefault(sid, "filled" if executed == quantity else "insufficient_cash_or_whole_share")
    for sid in sorted(weights):
        reasons.setdefault(sid, "unchanged")
    after = _balances(_text(cash), positions)
    _read_balances(after)
    return {"balances": after, "fills": fills,
            "dispositions": [{"etf_id": sid, "reason": reasons[sid]} for sid in sorted(weights)],
            "transition_complete": all(reason in ("filled", "unchanged", "already_zero") for reason in reasons.values())}


def _read_receipt(receipt):
    if type(receipt) is not FixtureReceipt or type(receipt.payload) is not bytes or len(receipt.payload) > MAX_RECEIPT_BYTES:
        _fail("invalid bounded fixture receipt")
    if _hash(receipt.sha256) != hashlib.sha256(receipt.payload).hexdigest():
        _fail("fixture receipt content mismatch")
    try:
        value = json.loads(receipt.payload)
    except (ValueError, UnicodeDecodeError, RecursionError):
        _fail("invalid fixture receipt JSON")
    _schema(value, _RECEIPT_KEYS)
    try:
        canonical = _bytes(value)
    except (ValueError, RecursionError):
        _fail("invalid fixture receipt JSON")
    if type(value["schema"]) is not str or value["schema"] != "tpr-synthetic-order-receipt-v1" or canonical != receipt.payload:
        _fail("noncanonical fixture receipt")
    return value


def _validate_state(state):
    if type(state) is not FixturePortfolio or type(state.mode) is not str or state.mode != MODE:
        _fail("invalid fixture state")
    _authority(state.authority)
    if type(state.positions) is not tuple or len(state.positions) > MAX_ASSETS or any(type(row) is not FixturePosition for row in state.positions):
        _fail("invalid fixture state positions")
    positions = {}
    for row in state.positions:
        sid = _id(row.etf_id)
        if sid in positions:
            _fail("duplicate fixture state positions")
        positions[sid] = _shares(row.shares)
    current = _balances(state.cash, positions)
    _read_balances(current)
    if tuple(positions) != tuple(sorted(positions)) or type(state.receipts) is not tuple or len(state.receipts) > MAX_TRANSITIONS:
        _fail("invalid bounded fixture state history")
    history, seen, previous, last_inputs = [], 0, None, None
    for index, receipt in enumerate(state.receipts, 1):
        value = _read_receipt(receipt)
        seen += len(receipt.payload)
        if seen > MAX_HISTORY_BYTES or type(value["sequence"]) is not int or value["sequence"] != index:
            _fail("invalid bounded fixture state history")
        _read_balances(value["before"])
        if previous is not None and value["before"] != previous:
            _fail("fixture state history balances diverged")
        inputs = value["inputs"]
        _read_inputs(inputs)
        if inputs["prior_state_sha256"] != _digest(_state_body(value["before"], history)) or _hash(value["input_sha256"]) != _digest(inputs):
            _fail("fixture state history checkpoint mismatch")
        if last_inputs is not None and (inputs["open_session_index"] <= last_inputs["open_session_index"] or _utc(inputs["open_utc"]) <= _utc(last_inputs["open_utc"])):
            _fail("fixture state replay or backward history")
        after = _transition(value["before"], inputs)
        # Python equality aliases bool/int and float/int. Byte-exact primitive
        # bodies must match the independently recomputed accounting receipt.
        if _bytes(value["after"]) != _bytes(after):
            _fail("fixture state accounting history mismatch")
        previous, last_inputs = after["balances"], inputs
        history.append(receipt.sha256)
    if previous is not None and current != previous:
        _fail("fixture state balances mismatch")
    if _hash(state.sha256) != _digest(_state_body(current, history)):
        _fail("fixture state content mismatch")
    return current, last_inputs


def _result(state, receipt, after, *, replayed):
    return FixtureTransition(state,
                             () if replayed else tuple(FixtureFill(**row) for row in after["fills"]),
                             tuple(FixtureDisposition(**row) for row in after["dispositions"]),
                             receipt, replayed, after["transition_complete"])


def execute_fixture_open(state, target, *, quotes, open_utc, open_session_index, expected_target_sha256,
                         expected_state_sha256, fee_per_order, slippage_bps, name_cap):
    """Consume one frozen synthetic target map at its supplied next open.

    Same-open replay from the returned checkpoint produces no new fills. This
    is a bounded pure transition, not execution, actual D4 evidence, protected
    antirollback custody, real source/outcome admission or backtest readiness.
    """
    before, last = _validate_state(state)
    if _hash(expected_state_sha256) != state.sha256:
        _fail("fixture state checkpoint mismatch")
    target_body, target_hash = _target(target)
    if _hash(expected_target_sha256) != target_hash:
        _fail("fixture target checkpoint mismatch")
    if {row["etf_id"] for row in before["positions"]} - {row["etf_id"] for row in target_body["targets"]}:
        _fail("missing prior target; no inferred exit")
    opened = _utc(open_utc).isoformat()
    index = _index(open_session_index)
    same_open = last is not None and last["open_utc"] == opened and last["open_session_index"] == index
    inputs = {"schema": "tpr-synthetic-transition-inputs-v1",
              "prior_state_sha256": last["prior_state_sha256"] if same_open else state.sha256,
              "target": target_body, "target_sha256": target_hash, "quotes": _quotes(quotes),
              "open_utc": opened, "open_session_index": index,
              "fee_per_order": fee_per_order, "slippage_bps": slippage_bps, "name_cap": name_cap}
    _read_inputs(inputs)
    if same_open:
        if _bytes(inputs) != _bytes(last):
            _fail("same-open fixture inputs changed")
        receipt = state.receipts[-1]
        return _result(state, receipt, _read_receipt(receipt)["after"], replayed=True)
    if last is not None and (index <= last["open_session_index"] or _utc(opened) <= _utc(last["open_utc"])):
        _fail("earlier or mismatched replayed fixture open")
    if len(state.receipts) >= MAX_TRANSITIONS:
        _fail("fixture transition history resource bound")
    after = _transition(before, inputs)
    body = {"schema": "tpr-synthetic-order-receipt-v1", "sequence": len(state.receipts) + 1,
            "before": before, "inputs": inputs, "input_sha256": _digest(inputs), "after": after}
    payload = _bytes(body)
    if len(payload) > MAX_RECEIPT_BYTES or sum(len(row.payload) for row in state.receipts) + len(payload) > MAX_HISTORY_BYTES:
        _fail("fixture receipt history resource bound")
    receipt = FixtureReceipt(payload, hashlib.sha256(payload).hexdigest())
    new_state = _portfolio(after["balances"], state.receipts + (receipt,))
    _validate_state(new_state)
    return _result(new_state, receipt, after, replayed=False)
