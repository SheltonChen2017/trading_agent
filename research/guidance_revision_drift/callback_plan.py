"""Pure invented data-to-callback plans and paired account consistency audits.

These are separate offline prototypes, not the approved 372-frame QC source.
No input is fetched, no engine is run here, and equal observations never prove
external authenticity, native settlement parity, research readiness or authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import re

from data.financial_primitives import exact_decimal_multiply as mul
from data.financial_primitives import exact_decimal_subtract as sub
from data.financial_primitives import exact_decimal_sum as total
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.assessment import assess_candidate
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift.events import decode_fixture_object
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant, fixture_projection
from research.guidance_revision_drift.integration import _market, fixture_lineage
from research.guidance_revision_drift.market_inputs import MarketInputError, SyntheticMarketInput, input_decimal
from research.guidance_revision_drift.timing import TimingError, decision_cutoff


class CallbackPlanError(ValueError):
    """Malformed or incomplete supplied synthetic observations."""


MAX_PLAN_BYTES = 512_000
MAX_ACCOUNT_ROW_BYTES = 256_000
RECIPES = ("base", "missing_data", "stale_data")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CLOSED = {"filled", "cancelled", "rejected", "expired", "rounded_to_zero"}
_ACCOUNT_FIELDS = {"snapshot_sha256", "settled_cash", "reserved_cash", "available_cash", "immediate_cash",
    "receivables", "holdings", "pending_orders", "orders_sha256", "fills_sha256", "fees", "marks", "nav",
    "permanent_blockers", "terminal_complete"}


def _decode(raw: bytes, maximum: int) -> dict:
    body = decode_fixture_object(raw, maximum)
    if canonical_json(body).encode() != raw:
        raise CallbackPlanError("canonical immutable bytes required")
    return body


def _hash(value: object) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise CallbackPlanError("retained lowercase SHA-256 required")
    return value


def _plan_body(recipe: str) -> dict:
    if type(recipe) is not str or recipe not in RECIPES:
        raise CallbackPlanError("fixed synthetic callback recipe required")
    corpus, lineage = example_corpus(), fixture_lineage()
    schedule, rows = corpus.schedule, []
    for index, session in enumerate(schedule.sessions):
        day, at = session.session_date, fixture_instant(session.session_date, 10)
        visible = lineage.as_of(at)
        assessment = assess_candidate(book=visible.book, disclosure_id="SYN-RAISE", as_of=at,
            schedule=schedule, permanent_security_id="SYN-SEC-A",
            references=corpus.references, bars=corpus.bars)
        reasons = [reason for _, refusals in assessment.refusals for reason in refusals]
        cutoff = decision_cutoff(schedule, day) if index else None
        if cutoff is None:
            reasons.append("preceding_session_outside_fixture")
        settlement = schedule.sessions[min(index + 1, len(schedule.sessions) - 1)].session_date
        quote, source, comparator_quote, comparator, hashes = None, None, None, None, []
        opportunity = assessment.eligible_session == day
        for role, end, adv in (("decision", at, Decimal("25000000")),
                ("source", at + timedelta(minutes=1), Decimal("25000000")),
                ("comparator_quote", at + timedelta(minutes=1), Decimal("1000000000")),
                ("comparator", at + timedelta(minutes=2), Decimal("1000000000"))):
            paired = role.startswith("comparator")
            market = _market(schedule, day, end, comparator=paired, price="100" if paired else "50")
            if role == "decision" and opportunity and recipe == "missing_data":
                reasons.append("missing_decision_market_input")
                continue
            if role == "decision" and opportunity and recipe == "stale_data":
                body = market.to_dict()
                for clock in ("received_at", "validated_at"):
                    body[clock] = (end - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
                for domain in ("quote", "trade"):
                    for clock in ("start_utc", "end_utc"):
                        value = datetime.fromisoformat(body[domain][clock].replace("Z", "+00:00"))
                        body[domain][clock] = (value - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
                market = SyntheticMarketInput.from_dict(body)
            hashes.append(market.sha256)
            try:
                if role in ("decision", "comparator_quote"):
                    value = market.quote_at(schedule, as_of=end)
                    values = fixture_projection({"at": value.at, "bid": value.bid, "ask": value.ask})
                    if role == "decision":
                        quote = values
                    else:
                        comparator_quote = values
                else:
                    value = market.prepare(schedule, as_of=end, adv20=adv, settlement_session=settlement)
                    minute = fixture_projection({"issuer": value.minute.issuer, "at": value.minute.at,
                        "bid": value.minute.bid, "ask": value.minute.ask, "volume": value.minute.volume,
                        "adv20": value.minute.adv20, "settlement_session": value.minute.settlement_session})
                    if value.minute.at <= at:
                        raise CallbackPlanError("execution must follow the decision quote")
                    if role == "source":
                        source = minute
                    else:
                        comparator = minute
            except (MarketInputError, TimingError) as exc:
                reasons.append(role + ":" + str(exc))
        rows.append({"session": day.isoformat(), "decision_at": at.isoformat(),
            "cutoff": None if cutoff is None else cutoff.isoformat(),
            "lineage_head": visible.lineage_head_sha256, "archive_head": visible.archive.head_sha256,
            "receipts_seen": len(visible.observation_sha256s),
            "receipt_statuses": list(visible.receipt_statuses),
            "assessment": fixture_projection({"eligible_session": assessment.eligible_session,
                "sector": assessment.sector, "adv20": assessment.adv20}),
            "decision_quote": quote, "source_minute": source, "comparator_quote": comparator_quote,
            "comparator_minute": comparator,
            "input_hashes": hashes, "refusals": reasons,
            "entry_eligible": opportunity and all(value is not None for value in
                (quote, source, comparator_quote, comparator))})
    return {"schema": "gdr.synthetic.callback-plan.v1", "recipe": recipe,
        "candidate_sha256": CANDIDATE_SHA256, "calendar_sha256": schedule.sha256,
        "corpus_sha256": corpus.sha256, "lineage_head_sha256": lineage.head_sha256,
        "rows": rows, "synthetic_only": True, "point_in_time_data": False,
        "native_runtime_verified": False, "external_authority": False, "cloud_completed": False}


@dataclass(frozen=True, slots=True)
class CallbackPlan:
    canonical_bytes: bytes

    def __post_init__(self):
        body = _decode(self.canonical_bytes, MAX_PLAN_BYTES)
        if self.canonical_bytes != canonical_json(_plan_body(body.get("recipe"))).encode():
            raise CallbackPlanError("plan does not reconstruct the complete fixed synthetic recipe")

    def to_dict(self) -> dict:
        self.__post_init__()
        return _decode(self.canonical_bytes, MAX_PLAN_BYTES)

    @property
    def rows(self) -> tuple[dict, ...]:
        return tuple(self.to_dict()["rows"])

    @property
    def sha256(self) -> str:
        self.__post_init__()
        return hash_bytes(self.canonical_bytes)


def build_callback_plan(recipe: str = "base") -> CallbackPlan:
    return CallbackPlan(canonical_json(_plan_body(recipe)).encode())


def verify_callback_plan(raw: bytes, *, expected_sha256: str) -> CallbackPlan:
    if hash_bytes(raw) != _hash(expected_sha256):
        raise CallbackPlanError("callback plan differs from retained anchor")
    return CallbackPlan(raw)


def _account(snapshot: dict, *, sleeve: str, day: date, marks: dict) -> dict:
    if type(snapshot) is not dict or type(marks) is not dict:
        raise CallbackPlanError("detached synthetic snapshot and marks required")
    # Canonical encode/decode first captures caller-owned nested state once.
    state = _decode(canonical_json(snapshot).encode(), MAX_ACCOUNT_ROW_BYTES)
    if (state.get("schema") != ("gdr.synthetic_simulation.v1" if sleeve == "strategy" else
            "gdr.synthetic_matched_comparator.v1") or state.get("synthetic_only") is not True
            or state.get("market_evidence") is not False
            or any(state.get(name) is not False for name in (("order_authority",) if sleeve == "strategy" else
                    ("execution_authorized", "empirical_inference_permitted", "cloud_parity_verified")))):
        raise CallbackPlanError("exact synthetic sleeve snapshot required")
    cash = input_decimal(state["settled_cash"], zero=True)
    receivables = state["receivables"]
    if type(receivables) is not list or len(receivables) > 256 or any(type(row) is not dict for row in receivables):
        raise CallbackPlanError("bounded dated receivables required")
    amount = total(input_decimal(row["amount"], zero=True) for row in receivables)
    holdings = state["positions" if sleeve == "strategy" else "tranches"]
    navs = state["navs"]
    if type(navs) is not list or not navs or navs[-1]["session"] != day.isoformat():
        raise CallbackPlanError("both sleeves must have the supplied session close")
    nav = navs[-1]["nav"]
    if type(state["orders"]) is not list or type(state["fills"]) is not list:
        raise CallbackPlanError("complete synthetic order/fill inventories required")
    fees = total(input_decimal(fill["fee"], zero=True) for fill in state["fills"])
    pending = [order for order in state["orders"] if order["status"] not in _CLOSED]
    blockers = (state.get("permanent_parity_blockers", []) + state.get("missing_session_closes", []))
    if sleeve == "strategy":
        blockers += list(state["unresolved"].items()) + state["missing_valuation_sessions"]
    elif state["unresolved_terminal"] or state["source_terminals"]:
        blockers += ["unresolved_or_unmatched_terminal"]
    if (sleeve == "comparator" and any(state["strategy_remaining"].values())
            and not any(holding["quantity"] for holding in holdings) and not pending):
        blockers += ["unclosed_source_schedule"]
    projection = fixture_projection({"snapshot_sha256": hash_payload(state), "settled_cash": cash,
        "reserved_cash": state["reserved_cash"], "available_cash": state["available_cash"],
        "immediate_cash": total((cash, amount)),
        "receivables": receivables, "holdings": holdings, "pending_orders": pending,
        "orders_sha256": hash_payload(state["orders"]), "fills_sha256": hash_payload(state["fills"]),
        "fees": fees, "marks": marks, "nav": nav, "permanent_blockers": blockers,
        "terminal_complete": not (pending or receivables or blockers or nav is None
            or state["completion_blocked" if sleeve == "strategy" else "study_completion_blocked"])})
    _checked_account(projection, sleeve=sleeve, day=day)
    return projection


def account_row(day: date, strategy_snapshot: dict, comparator_snapshot: dict, *, marks: dict) -> bytes:
    """Snapshot immutable close observations; supplied marks are not fetched.

    Callers retain the expected-row anchor independently. These snapshots are
    consistency inputs, not native observations or a source of trust by themselves.
    """
    if type(day) is not date or day not in {s.session_date for s in example_corpus().schedule.sessions}:
        raise CallbackPlanError("exact fixed fixture session required")
    if type(marks) is not dict or set(marks) != {"strategy", "comparator"}:
        raise CallbackPlanError("explicit independent sleeve marks required")
    raw = canonical_json({"schema": "gdr.synthetic.paired-account-row.v1", "session": day.isoformat(),
        "strategy": _account(strategy_snapshot, sleeve="strategy", day=day, marks=marks["strategy"]),
        "comparator": _account(comparator_snapshot, sleeve="comparator", day=day, marks=marks["comparator"]),
        "synthetic_only": True, "external_authenticity_verified": False,
        "native_runtime_verified": False, "settlement_parity_verified": False}).encode()
    _decode(raw, MAX_ACCOUNT_ROW_BYTES)
    return raw


@dataclass(frozen=True, slots=True)
class PairedAccountAudit:
    canonical_bytes: bytes

    def __post_init__(self):
        value = _decode(self.canonical_bytes, MAX_ACCOUNT_ROW_BYTES)
        closed = ("external_authenticity_verified", "native_runtime_verified", "settlement_parity_verified",
                  "empirical_backtest_ready", "execution_authorized")
        fields = {"schema", "calendar_rows", "observed_rows", "expected_rows_sha256", "observed_rows_sha256",
            "mismatches", "permanent_blockers", "terminal_flat_and_settled", "fixture_consistency_complete",
            "status", "synthetic_only", *closed}
        if (set(value) != fields or value["schema"] != "gdr.synthetic.paired-account-audit.v1"
                or value["synthetic_only"] is not True or any(value[key] is not False for key in closed)
                or type(value["calendar_rows"]) is not int or value["calendar_rows"] != 93
                or type(value["observed_rows"]) is not int or not 0 <= value["observed_rows"] <= 93
                or type(value["terminal_flat_and_settled"]) is not bool
                or type(value["fixture_consistency_complete"]) is not bool):
            raise CallbackPlanError("exact nonpromoting offline account audit required")
        for key in ("expected_rows_sha256", "observed_rows_sha256"):
            _hash(value[key])
        for key in ("mismatches", "permanent_blockers"):
            if type(value[key]) is not list or len(value[key]) > 4096:
                raise CallbackPlanError("bounded retained audit findings required")
        complete = (value["observed_rows"] == 93 and value["terminal_flat_and_settled"]
                    and not value["mismatches"] and not value["permanent_blockers"])
        if value["fixture_consistency_complete"] != complete or value["status"] != (
                "consistent_offline_fixture" if complete else "blocked"):
            raise CallbackPlanError("audit status must derive from complete retained findings")

    def to_dict(self) -> dict:
        self.__post_init__()
        return _decode(self.canonical_bytes, MAX_ACCOUNT_ROW_BYTES)


def _checked_account(value: dict, *, sleeve: str, day: date) -> None:
    if set(value) != _ACCOUNT_FIELDS:
        raise CallbackPlanError("complete account projection required")
    for key in ("snapshot_sha256", "orders_sha256", "fills_sha256"):
        _hash(value[key])
    for key in ("settled_cash", "reserved_cash", "available_cash", "immediate_cash", "fees"):
        input_decimal(value[key], zero=True)
    if value["nav"] is not None:
        input_decimal(value["nav"], zero=True)
    for key in ("receivables", "holdings", "pending_orders", "permanent_blockers"):
        if type(value[key]) is not list or len(value[key]) > 256:
            raise CallbackPlanError("bounded complete account inventories required")
    if type(value["marks"]) is not dict or type(value["terminal_complete"]) is not bool:
        raise CallbackPlanError("raw marks and exact terminal Boolean required")
    for identity, mark in value["marks"].items():
        if identity not in ("SYN-ISSUER-A", "SYN-SPY"):
            raise CallbackPlanError("fixed invented marked identity required")
        if mark is not None:
            input_decimal(mark)
    cash, reserved, available, immediate = (input_decimal(value[key], zero=True) for key in
        ("settled_cash", "reserved_cash", "available_cash", "immediate_cash"))
    if sub(cash, reserved) != available:
        raise CallbackPlanError("observed cash/reservation arithmetic mismatch")
    quantities, dates, ids = {}, {s.session_date for s in example_corpus().schedule.sessions}, set()
    for row in value["holdings"]:
        identity = row.get("issuer", row.get("security")) if type(row) is dict else None
        quantity = row.get("quantity") if type(row) is dict else None
        if (identity != ("SYN-ISSUER-A" if sleeve == "strategy" else "SYN-SPY")
                or type(quantity) is not int or not 0 <= quantity <= 10**12):
            raise CallbackPlanError("observed fixed whole-share holdings required")
        if quantity:
            quantities[identity] = quantities.get(identity, 0) + quantity
    proceeds = []
    for row in value["receivables"]:
        if type(row) is not dict:
            raise CallbackPlanError("observed dated receivable required")
        payment = row.get("pay_session", row.get("settlement_session"))
        identity = row.get("id", row.get("order_id", row.get("action_id")))
        if (type(payment) is not str or date.fromisoformat(payment) not in dates
                or date.fromisoformat(payment) <= day or type(identity) is not str
                or not identity.startswith("SYN-") or identity in ids):
            raise CallbackPlanError("observed unique future-dated receivable required")
        ids.add(identity)
        proceeds.append(input_decimal(row.get("amount"), zero=True))
    if total((cash, *proceeds)) != immediate:
        raise CallbackPlanError("observed immediate cash excludes or invents proceeds")
    order_reserves, ids = [], set()
    for row in value["pending_orders"]:
        if (type(row) is not dict or type(row.get("order_id")) is not str
                or not row["order_id"].startswith("SYN-") or row["order_id"] in ids
                or row.get("status") not in ("open", "cancel_requested") or row.get("side") not in ("buy", "sell")
                or any(type(row.get(key)) is not int for key in ("quantity", "remaining"))
                or not 0 < row["remaining"] <= row["quantity"] <= 10**12):
            raise CallbackPlanError("observed unique whole-share pending order required")
        ids.add(row["order_id"])
        amounts = (input_decimal(row.get("reserved_notional"), zero=True), input_decimal(row.get("reserved_fee"), zero=True)) if sleeve == "strategy" else (input_decimal(row.get("reserved"), zero=True),)
        if row["side"] == "sell" and total(amounts):
            raise CallbackPlanError("sell order cannot reserve buying cash")
        order_reserves.extend(amounts)
    if total(order_reserves) != reserved:
        raise CallbackPlanError("observed reservation differs from pending orders")
    if set(value["marks"]) != set(quantities):
        raise CallbackPlanError("observed raw marks must cover exactly held identities")
    calculated = None if any(mark is None for mark in value["marks"].values()) else total((cash, *proceeds,
        *(mul(input_decimal(mark), Decimal(quantities[key])) for key, mark in value["marks"].items())))
    if calculated != (None if value["nav"] is None else input_decimal(value["nav"], zero=True)):
        raise CallbackPlanError("observed cash/holdings/raw-mark NAV mismatch")
    complete = not (quantities or value["pending_orders"] or proceeds or value["permanent_blockers"] or calculated is None)
    if value["terminal_complete"] is not complete:
        raise CallbackPlanError("observed terminal status must derive from actual account state")


def audit_paired_accounts(observed: tuple[bytes, ...], expected: tuple[bytes, ...], *,
                         session_dates: tuple[date, ...], expected_sha256: str) -> PairedAccountAudit:
    """Compare every immutable close, retaining any transient/permanent defect.

    Missing rows are results, not dropped dates. Malformed envelopes refuse.
    A matching terminal portfolio cannot erase an earlier mismatch or blocker.
    """
    dates = tuple(s.session_date for s in example_corpus().schedule.sessions)
    if type(session_dates) is not tuple or session_dates != dates:
        raise CallbackPlanError("complete fixed synthetic calendar required")
    if (type(observed) is not tuple or type(expected) is not tuple
            or len(observed) > len(dates) or len(expected) != len(dates)
            or any(type(raw) is not bytes or not 0 < len(raw) <= MAX_ACCOUNT_ROW_BYTES
                   for collection in (expected, observed) for raw in collection)):
        raise CallbackPlanError("bounded immutable observed and complete expected rows required")
    if hash_payload([hash_bytes(raw) for raw in expected]) != _hash(expected_sha256):
        raise CallbackPlanError("expected rows differ from retained anchor")
    fields = {"schema", "session", "strategy", "comparator", "synthetic_only",
              "external_authenticity_verified", "native_runtime_verified", "settlement_parity_verified"}
    parsed = []
    for collection in (expected, observed):
        rows = []
        for raw in collection:
            row = _decode(raw, MAX_ACCOUNT_ROW_BYTES)
            if (set(row) != fields or row["schema"] != "gdr.synthetic.paired-account-row.v1"
                    or row["synthetic_only"] is not True or any(row[name] is not False for name in (
                        "external_authenticity_verified", "native_runtime_verified", "settlement_parity_verified"))
                    or type(row["strategy"]) is not dict or type(row["comparator"]) is not dict):
                raise CallbackPlanError("nonpromoting exact account-row envelope required")
            for sleeve in ("strategy", "comparator"):
                _checked_account(row[sleeve], sleeve=sleeve, day=date.fromisoformat(row["session"]))
            rows.append(row)
        names = tuple(row["session"] for row in rows)
        if len(set(names)) != len(names) or names != tuple(sorted(names)) or any(name not in {d.isoformat() for d in dates} for name in names):
            raise CallbackPlanError("unique chronological fixed session rows required")
        parsed.append(rows)
    wanted, seen = parsed
    if tuple(row["session"] for row in wanted) != tuple(d.isoformat() for d in dates):
        raise CallbackPlanError("expected account calendar is incomplete")
    by_day = {row["session"]: row for row in seen}
    mismatches, blockers = [], []
    for row in wanted:
        day = row["session"]
        actual = by_day.get(day)
        if actual is None:
            mismatches.append({"session": day, "field": "missing_account_row"})
        elif actual != row:
            for sleeve in ("strategy", "comparator"):
                for field in sorted(set(row[sleeve]) | set(actual[sleeve])):
                    if canonical_json(actual[sleeve].get(field)) != canonical_json(row[sleeve].get(field)):
                        mismatches.append({"session": day, "field": sleeve + "." + field})
        for sleeve in ("strategy", "comparator"):
            if row[sleeve]["permanent_blockers"] or row[sleeve]["nav"] is None:
                blockers.append({"session": day, "sleeve": sleeve,
                                 "reasons": row[sleeve]["permanent_blockers"], "missing_nav": row[sleeve]["nav"] is None})
    terminal = all(wanted[-1][sleeve]["terminal_complete"] is True for sleeve in ("strategy", "comparator"))
    complete = not mismatches and not blockers and terminal
    body = {"schema": "gdr.synthetic.paired-account-audit.v1", "calendar_rows": len(dates),
        "observed_rows": len(observed), "expected_rows_sha256": expected_sha256,
        "observed_rows_sha256": hash_payload([hash_bytes(raw) for raw in observed]),
        "mismatches": mismatches, "permanent_blockers": blockers, "terminal_flat_and_settled": terminal,
        "fixture_consistency_complete": complete, "status": "consistent_offline_fixture" if complete else "blocked",
        "synthetic_only": True, "external_authenticity_verified": False, "native_runtime_verified": False,
        "settlement_parity_verified": False, "empirical_backtest_ready": False, "execution_authorized": False}
    return PairedAccountAudit(canonical_json(body).encode())
