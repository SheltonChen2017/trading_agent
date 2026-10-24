"""Bounded multi-session invented order accounting, with no market evidence.

Only precomputed synthetic targets and invented opening marks are consumed.
The supplied clocks prove their ordering, not real provider availability or
an exchange calendar. Reports are immutable transcripts; supplied-memory
hashes and replay recomputation are not protected durable custody. A completed
software run can contain named refusals and never establishes real backtest,
outcome, source, QuantConnect, capital, or trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re

from .scoring import FixtureScoringError, TargetResult, TargetWeight, fixture_target_sha256
from .simulation import (
    AUTHORITY, MAX_ASSETS, MAX_HISTORY_BYTES, MAX_RECEIPT_BYTES, MAX_SHARES, MAX_TRANSITIONS,
    MODE, FixturePortfolio, FixturePosition, FixtureReceipt,
    FixtureSimulationError, execute_fixture_open,
)

MAX_REPORT_BYTES = 4 * 1024 * 1024
D0_PLAN_SHA256 = "15e0b00978d4060ae3d6b827474e320df2003c9ceee529c8a8436b31570b7bcb"
D0_REPORT_SHA256 = "fbe99ce620689c61052330a220b9f989b29a8ea732a45204d88b02e6f5648148"
_STEP_KEYS = {"target", "quotes", "open_utc", "open_session_index"}
_CHECKPOINT_KEYS = {"cash", "positions", "receipts", "sha256"}
_REPORT_KEYS = {"schema", "mode", "authority", "software_completed", "status", "real_backtest_ready",
                "custody", "context", "config", "initial_checkpoint", "sessions", "terminal_checkpoint",
                "totals", "external_access"}


class FixtureBacktestError(ValueError):
    """A named refusal of the synthetic-only backtest transcript contract."""


@dataclass(frozen=True)
class FixtureBacktestReport:
    payload: bytes
    sha256: str
    terminal_state: FixturePortfolio


def _fail(reason):
    raise FixtureBacktestError(reason)


def _schema(value, keys):
    if type(value) is not dict or len(value) != len(keys) or any(type(key) is not str for key in value) or set(value) != keys:
        _fail("invalid closed synthetic backtest schema")


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        _fail("invalid synthetic backtest content identity")
    return value


def _utc(value):
    if type(value) is not str or len(value) > 64:
        _fail("invalid synthetic backtest clock")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        _fail("invalid synthetic backtest clock")


def _bytes(value):
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        _fail("invalid synthetic backtest primitive JSON")


def _text(value):
    """Canonical terminating exact accounting, independent of Decimal context."""
    numerator, denominator = value.numerator, value.denominator
    if numerator < 0:
        _fail("negative synthetic backtest cost")
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        _fail("nonterminating synthetic backtest accounting")
    scale = max(twos, fives)
    digits = str(numerator * 2 ** (scale - twos) * 5 ** (scale - fives))
    if scale:
        digits = digits.zfill(scale + 1)
        digits = digits[:-scale] + "." + digits[-scale:]
        digits = digits.rstrip("0").rstrip(".")
    return digits


def _checkpoint(state):
    # Only called after public execute_fixture_open has authenticated the
    # entire supplied history and independently recomputed its accounting,
    # or for a terminal frame compared byte-exactly with that recomputation.
    # Exact primitive types must precede equality or caller serialization:
    # bool/int aliases and custom row/literal callbacks are never authority.
    if type(state) is not FixturePortfolio or type(state.mode) is not str or state.mode != MODE:
        _fail("invalid synthetic checkpoint mode")
    if type(state.authority) is not tuple or len(state.authority) != len(AUTHORITY):
        _fail("invalid synthetic checkpoint authority")
    for row, expected in zip(state.authority, AUTHORITY):
        if type(row) is not tuple or len(row) != 2 or type(row[0]) is not str or row[0] != expected[0] or row[1] is not False:
            _fail("invalid synthetic checkpoint authority")
    _hash(state.sha256)
    if type(state.cash) is not str or len(state.cash) > 256:
        _fail("invalid synthetic checkpoint cash")
    if type(state.positions) is not tuple or len(state.positions) > MAX_ASSETS:
        _fail("invalid bounded synthetic checkpoint positions")
    for row in state.positions:
        if type(row) is not FixturePosition or type(row.etf_id) is not str or type(row.shares) is not int or not 0 <= row.shares <= MAX_SHARES:
            _fail("invalid synthetic checkpoint position types")
        if len(row.etf_id) > 128 or re.fullmatch(r"SYNTHETIC-[A-Z0-9][A-Z0-9_-]*", row.etf_id) is None:
            _fail("invalid bounded synthetic checkpoint identity")
    if type(state.receipts) is not tuple or len(state.receipts) > MAX_TRANSITIONS:
        _fail("invalid bounded synthetic checkpoint receipts")
    history_bytes = 0
    for row in state.receipts:
        if type(row) is not FixtureReceipt or type(row.payload) is not bytes or len(row.payload) > MAX_RECEIPT_BYTES:
            _fail("invalid bounded synthetic checkpoint receipt")
        _hash(row.sha256)
        history_bytes += len(row.payload)
    if history_bytes > MAX_HISTORY_BYTES:
        _fail("synthetic checkpoint history resource bound")
    return {"cash": state.cash,
            "positions": [{"etf_id": row.etf_id, "shares": row.shares} for row in state.positions],
            "receipts": [{"payload": row.payload.decode("utf-8"), "sha256": row.sha256} for row in state.receipts],
            "sha256": state.sha256}


def _restore_checkpoint(value):
    _schema(value, _CHECKPOINT_KEYS)
    if type(value["cash"]) is not str or type(value["positions"]) is not list or len(value["positions"]) > 128:
        _fail("invalid bounded synthetic checkpoint")
    if type(value["receipts"]) is not list or len(value["receipts"]) > MAX_TRANSITIONS:
        _fail("invalid bounded synthetic checkpoint history")
    positions, receipts = [], []
    for row in value["positions"]:
        _schema(row, {"etf_id", "shares"})
        if type(row["etf_id"]) is not str or type(row["shares"]) is not int:
            _fail("invalid synthetic checkpoint positions")
        positions.append(FixturePosition(row["etf_id"], row["shares"]))
    for row in value["receipts"]:
        _schema(row, {"payload", "sha256"})
        if type(row["payload"]) is not str:
            _fail("invalid synthetic checkpoint receipt")
        try:
            payload = row["payload"].encode("utf-8")
        except UnicodeEncodeError:
            _fail("invalid synthetic checkpoint receipt")
        receipts.append(FixtureReceipt(payload, _hash(row["sha256"])))
    return FixturePortfolio(value["cash"], tuple(positions), tuple(receipts), _hash(value["sha256"]))


def _target_from_body(value):
    _schema(value, {"schema", "mode", "authority", "cutoff_utc", "decision_session_index",
                    "cash_weight", "addition_weight", "reduction_weight", "targets"})
    if type(value["schema"]) is not str or value["schema"] != "tpr-d2-fixture-targets-v1":
        _fail("invalid synthetic backtest target schema")
    _schema(value["authority"], set(dict(AUTHORITY)))
    if any(flag is not False for flag in value["authority"].values()):
        _fail("invalid synthetic backtest authority")
    if type(value["targets"]) is not list or len(value["targets"]) > 128:
        _fail("invalid bounded synthetic target collection")
    rows = []
    for row in value["targets"]:
        _schema(row, {"etf_id", "weight", "reason"})
        rows.append(TargetWeight(row["etf_id"], row["weight"], row["reason"]))
    return TargetResult(tuple(rows), value["cash_weight"], value["addition_weight"], value["reduction_weight"],
                        value["cutoff_utc"], value["decision_session_index"], value["mode"], AUTHORITY)


def run_fixture_backtest(initial, steps, *, expected_initial_sha256, fee_per_order, slippage_bps, name_cap):
    """Execute 1..32 new invented sessions and retain every refusal.

    Inputs are caller-generated memory fixtures, never files or real rows.
    Every target must be frozen after the preceding executed open; its next
    open is enforced by the public transition contract. Same-open replay is
    not counted as another backtest session. Checkpoint resume verifies the
    entire supplied history but supplies no protected antirollback authority.
    """
    expected = _hash(expected_initial_sha256)
    if type(initial) is not FixturePortfolio or type(initial.receipts) is not tuple:
        _fail("invalid synthetic backtest initial checkpoint")
    if type(steps) is not tuple or not 1 <= len(steps) <= MAX_TRANSITIONS or len(initial.receipts) + len(steps) > MAX_TRANSITIONS:
        _fail("invalid bounded synthetic backtest sessions")
    state, sessions = initial, []
    prior_open = None
    fees = slippage = Fraction(0)
    fill_count = buy_count = sell_count = complete_count = 0
    for ordinal, step in enumerate(steps, 1):
        _schema(step, _STEP_KEYS)
        try:
            target_hash = fixture_target_sha256(step["target"])
            cutoff = _utc(step["target"].cutoff_utc)
            if prior_open is not None and cutoff <= prior_open:
                _fail("synthetic decision cutoff does not follow prior open")
            transition = execute_fixture_open(
                state, step["target"], quotes=step["quotes"], open_utc=step["open_utc"],
                open_session_index=step["open_session_index"], expected_target_sha256=target_hash,
                expected_state_sha256=expected if ordinal == 1 else state.sha256,
                fee_per_order=fee_per_order, slippage_bps=slippage_bps, name_cap=name_cap,
            )
        except (FixtureScoringError, FixtureSimulationError) as exc:
            raise FixtureBacktestError("invalid synthetic session: " + str(exc)) from exc
        if transition.replayed:
            _fail("duplicate synthetic backtest open is not a new session")
        if ordinal == 1 and initial.receipts:
            # Public execution validated this historical body already. This
            # check also covers a supplied resume checkpoint, not just steps
            # produced in this invocation; it does not assert OS custody.
            previous = json.loads(initial.receipts[-1].payload)["inputs"]
            if cutoff <= _utc(previous["open_utc"]):
                _fail("synthetic decision cutoff does not follow checkpoint open")
        receipt = json.loads(transition.receipt.payload)
        marks = {row["etf_id"]: Fraction(Decimal(row["price"])) for row in receipt["inputs"]["quotes"]}
        for fill in transition.fills:
            fees += Fraction(Decimal(fill.fee))
            slippage += abs(Fraction(Decimal(fill.unit_price)) - marks[fill.etf_id]) * fill.shares
            fill_count += 1
            buy_count += fill.side == "buy"
            sell_count += fill.side == "sell"
        complete_count += transition.transition_complete
        sessions.append({"sequence": ordinal, "start_state_sha256": state.sha256,
                         "decision_target_sha256": target_hash, "receipt_sha256": transition.receipt.sha256,
                         "terminal_state_sha256": transition.portfolio.sha256,
                         "transition_complete": transition.transition_complete, "receipt": receipt})
        state = transition.portfolio
        prior_open = _utc(receipt["inputs"]["open_utc"])
    value = {"schema": "tpr-synthetic-order-backtest-v1", "mode": MODE, "authority": dict(AUTHORITY),
             "software_completed": True,
             "status": "COMPLETED" if complete_count == len(steps) else "COMPLETED_WITH_REFUSALS",
             "real_backtest_ready": False,
             "custody": "supplied-memory-only-not-protected-durable-custody",
             "context": {"d0_plan_sha256": D0_PLAN_SHA256, "d0_aggregate_sha256": D0_REPORT_SHA256,
                         "role": "committed-aggregate-context-only-not-source-admission"},
             "config": {"fee_per_order": fee_per_order, "slippage_bps": slippage_bps, "name_cap": name_cap},
             "initial_checkpoint": _checkpoint(initial), "sessions": sessions, "terminal_checkpoint": _checkpoint(state),
             "totals": {"sessions": len(steps), "complete_sessions": complete_count,
                        "refused_sessions": len(steps) - complete_count, "fills": fill_count,
                        "buy_fills": buy_count, "sell_fills": sell_count,
                        "fees": _text(fees), "slippage_cost": _text(slippage)},
             "external_access": {"provider_requests": 0, "retained_rows_read": 0, "outcome_reads": 0,
                                 "development_looks": 0, "qc_attempts": 0, "broker_orders": 0,
                                 "operator_state_reads": 0}}
    payload = _bytes(value)
    if len(payload) > MAX_REPORT_BYTES:
        _fail("synthetic backtest report resource bound")
    return FixtureBacktestReport(payload, hashlib.sha256(payload).hexdigest(), state)


def verify_fixture_backtest(report, *, expected_report_sha256):
    """Recompute full ordered accounting and compare byte-exact transcript.

    External expected identity is checked before JSON parsing. Rehashing a
    false completion, cost, receipt, target, authority or counter does not
    replace independent recomputation. This does not authenticate a caller
    or prove real source/custody rights; all inputs remain invented fixtures.
    """
    expected = _hash(expected_report_sha256)
    if type(report) is not FixtureBacktestReport or type(report.payload) is not bytes or len(report.payload) > MAX_REPORT_BYTES:
        _fail("invalid bounded synthetic backtest report")
    if _hash(report.sha256) != expected or hashlib.sha256(report.payload).hexdigest() != expected:
        _fail("synthetic backtest report content mismatch")
    try:
        value = json.loads(report.payload)
    except (ValueError, UnicodeDecodeError, RecursionError):
        _fail("invalid synthetic backtest report JSON")
    _schema(value, _REPORT_KEYS)
    if _bytes(value) != report.payload:
        _fail("noncanonical synthetic backtest report")
    _schema(value["config"], {"fee_per_order", "slippage_bps", "name_cap"})
    if type(value["sessions"]) is not list or not 1 <= len(value["sessions"]) <= MAX_TRANSITIONS:
        _fail("invalid bounded synthetic report sessions")
    initial = _restore_checkpoint(value["initial_checkpoint"])
    steps = []
    for session in value["sessions"]:
        _schema(session, {"sequence", "start_state_sha256", "decision_target_sha256", "receipt_sha256",
                          "terminal_state_sha256", "transition_complete", "receipt"})
        receipt = session["receipt"]
        _schema(receipt, {"schema", "sequence", "before", "inputs", "input_sha256", "after"})
        inputs = receipt["inputs"]
        _schema(inputs, {"schema", "prior_state_sha256", "target", "target_sha256", "quotes",
                         "open_utc", "open_session_index", "fee_per_order", "slippage_bps", "name_cap"})
        if type(inputs["quotes"]) is not list or len(inputs["quotes"]) > 128:
            _fail("invalid bounded synthetic report quotes")
        quotes = {}
        for row in inputs["quotes"]:
            _schema(row, {"etf_id", "price", "observed_at_utc"})
            if type(row["etf_id"]) is not str or row["etf_id"] in quotes:
                _fail("invalid synthetic report quote identity")
            quotes[row["etf_id"]] = {"price": row["price"], "observed_at_utc": row["observed_at_utc"]}
        steps.append({"target": _target_from_body(inputs["target"]), "quotes": quotes,
                      "open_utc": inputs["open_utc"], "open_session_index": inputs["open_session_index"]})
    recomputed = run_fixture_backtest(initial, tuple(steps), expected_initial_sha256=initial.sha256, **value["config"])
    if recomputed.payload != report.payload or recomputed.sha256 != report.sha256:
        _fail("synthetic backtest accounting transcript mismatch")
    # Byte-exact checkpoint comparison rejects Python's bool/int equality
    # aliases and authenticates supplied terminal receipt history via replay.
    if type(report.terminal_state) is not FixturePortfolio:
        _fail("invalid synthetic backtest terminal checkpoint")
    try:
        terminal = _checkpoint(report.terminal_state)
    except (AttributeError, TypeError, ValueError):
        _fail("invalid synthetic backtest terminal checkpoint")
    if _bytes(terminal) != _bytes(value["terminal_checkpoint"]):
        _fail("synthetic backtest terminal checkpoint mismatch")
    return recomputed
