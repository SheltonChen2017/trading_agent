"""Atomic synthetic action accounting across strategy and comparator sleeves.

Only explicitly supplied cash economics and whole-share splits are supported.
Source terminal cash is not a strategy exit Fill: comparator positions remain
visible with a permanent schedule blocker instead of an invented liquidation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.comparison import MatchedComparator
from research.guidance_revision_drift.events import _date, _identifier, _keys, decode_fixture_object
from research.guidance_revision_drift.market_inputs import calendar_session, input_clock, input_decimal
from research.guidance_revision_drift.simulation import Simulation
from research.guidance_revision_drift.timing import NY, PinnedSchedule


class CorporateActionError(ValueError):
    """Invalid/unsupported synthetic action; both sleeves remain unchanged."""


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """Immutable input; terminal amount is total cash, dividend amount per share."""

    canonical_bytes: bytes

    def __post_init__(self):
        try:
            body = decode_fixture_object(self.canonical_bytes, 16384)
            _keys(body, frozenset(("schema", "source_id", "action_id", "issuer_id", "calendar_sha256",
                "kind", "effective_at", "received_at", "validated_at", "ratio", "amount", "pay_session")), "action")
            if body["schema"] != "gdr.synthetic.corporate-action.v1":
                raise CorporateActionError("explicit synthetic action schema required")
            for name in ("source_id", "action_id", "issuer_id"):
                _identifier(body[name])
            sha = body["calendar_sha256"]
            if type(sha) is not str or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise CorporateActionError("calendar hash required")
            effective, received, validated = (input_clock(body[key]) for key in
                                               ("effective_at", "received_at", "validated_at"))
            if not received <= validated <= effective:
                raise CorporateActionError("action must be received and validated before its effective open")
            kind = body["kind"]
            if kind not in ("split", "dividend", "terminal"):
                raise CorporateActionError("unsupported noncash/action economics")
            if kind == "split":
                input_decimal(body["ratio"])
                if body["amount"] is not None or body["pay_session"] is not None:
                    raise CorporateActionError("split cash-in-lieu is unsupported")
            else:
                if body["ratio"] is not None:
                    raise CorporateActionError("cash action cannot carry a split ratio")
                if kind == "dividend" or body["amount"] is not None:
                    input_decimal(body["amount"], zero=True)
                    _date(body["pay_session"])
                elif body["pay_session"] is not None:
                    raise CorporateActionError("unresolved terminal cannot invent a payment date")
            if canonical_json(body).encode() != self.canonical_bytes:
                raise CorporateActionError("canonical action bytes required")
        except ValueError as exc:
            raise CorporateActionError(str(exc)) from exc

    @classmethod
    def from_dict(cls, body: dict) -> CorporateAction:
        return cls(canonical_json(body).encode())

    @classmethod
    def from_bytes(cls, raw: bytes) -> CorporateAction:
        return cls.from_dict(decode_fixture_object(raw, 16384))

    def to_dict(self) -> dict:
        self.__post_init__()
        return decode_fixture_object(self.canonical_bytes, 16384)

    @property
    def sha256(self) -> str:
        self.__post_init__()
        return hash_bytes(self.canonical_bytes)


def apply_corporate_action(strategy: Simulation, comparator: MatchedComparator,
                           action: CorporateAction, *, schedule: PinnedSchedule) -> str:
    """Apply a complete input once, or restore both synthetic in-memory states.

    This coordinator deliberately uses these exact lane-local engine classes;
    it is not a broker transaction, thread-safe service, durable commit, or
    recovery checkpoint. ENG-12/13 must journal the command before claiming
    durable replay. Pre-existing actions outside this path are not adopted.
    """
    if type(strategy) is not Simulation or type(comparator) is not MatchedComparator or type(action) is not CorporateAction:
        raise CorporateActionError("exact synthetic engines and action required")
    body = action.to_dict()
    at = input_clock(body["effective_at"])
    session = calendar_session(schedule, body["calendar_sha256"], at.astimezone(NY).date())
    if at != session.open_utc:
        raise CorporateActionError("corporate action requires explicit regular-session open")
    expected = tuple((s.session_date, s.open_utc, s.close_utc) for s in schedule.sessions)
    for engine in (strategy, comparator):
        actual = tuple((s.day, s.opens_at, s.closes_at) for s in engine._sessions.values())
        if actual != expected:
            raise CorporateActionError("engine and input calendars differ")
    action_id, issuer, kind = (body[name] for name in ("action_id", "issuer_id", "kind"))
    digest = action.sha256
    amount = input_decimal(body["amount"], zero=True) if body["amount"] is not None else None
    pay = _date(body["pay_session"]) if body["pay_session"] is not None else None
    ratio = input_decimal(body["ratio"]) if body["ratio"] is not None else None
    prior = comparator._state["corporate_action_inputs"].get(action_id)
    if prior is not None:
        if prior != digest:
            raise CorporateActionError("conflicting corporate-action input replay")
        # A receipt in one sleeve cannot acknowledge work on a different or
        # incompletely restored partner. Check each affected domain's original
        # receipt, without comparing mutable post-action holdings or clocks.
        if issuer != "SYN-SPY":
            expected_strategy = {"split": ("split", issuer, ratio, at),
                "dividend": ("dividend", issuer, amount, at, pay),
                "terminal": ("terminal", issuer, at, amount, pay)}[kind]
            if strategy._state["actions"].get(action_id) != expected_strategy:
                raise CorporateActionError("paired action receipt missing or inconsistent in strategy")
            expected_comparator = {"split": ("source_split", issuer, ratio, at),
                "dividend": None, "terminal": ("source_terminal", issuer, at, amount is not None)}[kind]
        else:
            expected_comparator = {"split": ("split", ratio, at),
                "dividend": ("dividend", amount, at, pay), "terminal": ("terminal", at, amount, pay)}[kind]
        if expected_comparator is not None and comparator._state["actions"].get(action_id) != expected_comparator:
            raise CorporateActionError("paired action receipt missing or inconsistent in comparator")
        return digest
    if action_id in strategy._state["actions"] or action_id in comparator._state["actions"]:
        raise CorporateActionError("action ID already applied outside paired input path")
    if pay is not None:
        schedule.index(pay)
    states = deepcopy(strategy._state), deepcopy(comparator._state)
    try:
        # Even a one-sleeve dividend must not be backdated relative to the other
        # sleeve's already-consumed observations. Exact retries return above.
        for engine in (strategy, comparator):
            if engine._state["clock"] is not None and at < engine._state["clock"]:
                raise CorporateActionError("action is earlier than an engine clock")
        if issuer == "SYN-SPY":
            if kind == "split":
                comparator.apply_split(action_id, input_decimal(body["ratio"]), at)
            elif kind == "dividend":
                comparator.credit_dividend(action_id, amount, at, pay)
            else:
                comparator.terminal_settlement(action_id, at, amount, pay)
        elif kind == "split":
            ratio = input_decimal(body["ratio"])
            held = strategy._state["positions"].get(issuer)
            if held is None or comparator._state["strategy_remaining"].get(issuer) != held.quantity:
                raise CorporateActionError("source split requires exact matched strategy-share lineage")
            strategy.apply_split(action_id, issuer, ratio, at)
            comparator.apply_source_split(action_id, issuer, ratio, at)
        elif kind == "dividend":
            strategy.credit_dividend(action_id, issuer, amount, at, pay)
        else:
            strategy.terminal_settlement(action_id, issuer, at, amount, pay)
            comparator.record_source_terminal(action_id, issuer, at, amount is not None)
        comparator._state["corporate_action_inputs"][action_id] = digest
        return digest
    except Exception:
        strategy._state, comparator._state = states
        raise
