"""Pure, default-disabled canonical-clock QC source and pre-outcome batch plans.

Only the exact frozen c80ff4f5 standalone source is transformed. Guarded spans
retain its fixed cash, slots, reserve, gap, order-direction, live-mode, split,
delisting, partial-fill and terminal-completion refusals. This is engineering,
not QC engine/auction/data/cost parity or permission to configure/launch a job.

MOO proposals occur exactly two minutes before the bound regular open. Any
event or prerequisite reference arriving later refuses the WHOLE plan: no row
is dropped, backdated, or forwarded. Every source event belongs to one stable
child batch; all children share one preregistered parent study and permanent
look. Each child preserves 100,000 starting cash/20 slots/4,500 slot budget and
10,000 reserve. These independent diagnostic accounts are never pooled into
an inferred capital portfolio. At most three attempts per child are planned;
this module neither launches nor grants a new look.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, localcontext
import hashlib
import heapq
import json
import re
import weakref

from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying import backtest_study_package as study
from research.insider_buying import backtest_qc_export_adapter as native
from research.insider_buying.backtest_event_study_manifest import (
    SourceEventStudyManifest, validate_source_event_study_manifest,
)


VERSION = "insider-canonical-qc-batch-plan-v1"
VERSION_V2 = "insider-canonical-qc-batch-plan-v2"
MANIFEST_SCHEMA = "insider-qc-canonical-open-study-v2"
GATE_SCHEMA = "insider-qc-canonical-open-gate-v2"
LEGACY_SOURCE_SHA256 = "c80ff4f585d59d1b8e4ecd0d6199605fee727de9df0a13b74e987fe4d2819f87"
MAX_EVENTS = 20_000
MAX_BATCHES = 1_000
MAX_BYTES = 64_000_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
_TOKEN = object()
_BUILT: dict[int, tuple[weakref.ReferenceType, bytes]] = {}
_NATIVE_BUILT: dict[int, tuple[weakref.ReferenceType, bytes]] = {}
NATIVE_PROFILE = "INSETF-IB-QC-CANONICAL-MOO-EXPORT-v2"
NATIVE_MONEY_PROFILE = "USD-magnitude-at-most-1e12-scale-at-most-28-exact-v1"


class CanonicalQcCandidateError(ValueError):
    """Source, cutoff, partition, rendering or completion evidence refused."""


def _need(value, message):
    if not value:
        raise CanonicalQcCandidateError("REFUSED: " + message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _id(value):
    _need(type(value) is str and _ID.fullmatch(value) is not None, "exact bounded study identity required")
    return value


def _decode(raw, expected):
    try:
        return analysis._decode(raw, expected)
    except analysis.RegisteredAnalysisError as exc:
        raise CanonicalQcCandidateError("REFUSED: anchored prerequisite bytes differ") from exc


def _exact(source, old, new):
    _need(source.count(old) == 1, "captured source replacement anchor absent or duplicated")
    return source.replace(old, new, 1)


def _span(source, first, following, replacement):
    _need(source.count(first) == source.count(following) == 1, "captured source span anchors absent or duplicated")
    begin, end = source.index(first), source.index(following)
    _need(begin < end, "captured source spans reordered")
    return source[:begin] + replacement.rstrip() + "\n\n\n" + source[end:]


_FIELDS = '''_MANIFEST_FIELDS = frozenset({
    "schema", "parent_study_id", "registered_look_id", "batch_id", "batch_plan_sha256",
    "source_event_manifest_sha256", "source_manifest_sha256", "security_master_sha256",
    "calendar_sha256", "outcome_vintage_sha256", "sessions", "signals",
})
_SIGNAL_FIELDS = frozenset({
    "signal_id", "issuer_id", "ticker", "qc_symbol_id", "source_event_sha256",
    "mapping_first_session", "mapping_last_session", "available_at_utc",
    "decision_session", "entry_session", "exit_session",
})
_GATE_FIELDS = frozenset({
    "schema", "scope", "registered_look_id", "manifest_sha256", "rights_record_sha256",
    "outcome_vintage_sha256", "parent_study_id", "batch_id", "batch_plan_sha256",
})


def _exact_arithmetic(function):
    def bounded(*args, **kwargs):
        with _localcontext() as arithmetic:
            arithmetic.prec = 100
            return function(*args, **kwargs)
    return bounded'''

_MANIFEST_TYPE = '''class StudyManifest(NamedTuple):
    raw_sha256: str
    source_manifest_sha256: str
    security_master_sha256: str
    calendar_sha256: str
    outcome_vintage_sha256: str
    sessions: tuple[_dt.date, ...]
    signals: tuple[Signal, ...]
    opens: tuple[_dt.datetime, ...]
    closes: tuple[_dt.datetime, ...]
    parent_study_id: str
    batch_id: str
    batch_plan_sha256: str'''

_PARSE_MANIFEST = '''def parse_study_manifest(raw: bytes, expected_sha256: str) -> StudyManifest:
    value, actual = _decode(raw, expected_sha256, max_bytes=MAX_MANIFEST_BYTES)
    if frozenset(value) != _MANIFEST_FIELDS or value["schema"] != SCHEMA:
        raise StockStudyRefusal("REFUSED: canonical manifest schema drift")
    for key in ("source_event_manifest_sha256", "source_manifest_sha256", "security_master_sha256", "calendar_sha256", "outcome_vintage_sha256", "batch_plan_sha256"):
        _digest(value[key], key)
    for key in ("parent_study_id", "registered_look_id", "batch_id"):
        if type(value[key]) is not str or _LOOK_ID.fullmatch(value[key]) is None:
            raise StockStudyRefusal("REFUSED: canonical study identity drift")
    supplied = value["sessions"]
    if type(supplied) is not list or not 314 <= len(supplied) <= MAX_CALENDAR_SESSIONS:
        raise StockStudyRefusal("REFUSED: full canonical calendar absent or unbounded")
    if _hashlib.sha256(_json.dumps(supplied,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest() != value["calendar_sha256"]:
        raise StockStudyRefusal("REFUSED: full-instant calendar digest mismatch")
    dates, opens, closes = [], [], []
    zone = _ZoneInfo("America/New_York")
    for item in supplied:
        if type(item) is not dict or set(item) != {"session","open_utc","close_utc"}:
            raise StockStudyRefusal("REFUSED: full-instant calendar row drift")
        day = _session(item["session"],"session")
        if any(type(item[key]) is not str or _re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",item[key]) is None for key in ("open_utc","close_utc")):
            raise StockStudyRefusal("REFUSED: exact full-instant UTC calendar spelling required")
        opening = _utc(item["open_utc"][:-1]+"+00:00")
        closing = _utc(item["close_utc"][:-1]+"+00:00")
        if opening is None or closing is None or not opening < closing or day > SHARED_RESEARCH_CUTOFF:
            raise StockStudyRefusal("REFUSED: full-instant calendar invalid")
        lo, lc = opening.astimezone(zone), closing.astimezone(zone)
        if lo.date()!=day or lc.date()!=day or lo.weekday()>=5 or (lo.hour,lo.minute,lo.second)!=(9,30,0) or (lc.hour,lc.minute,lc.second) not in {(16,0,0),(13,0,0)}:
            raise StockStudyRefusal("REFUSED: not bound regular US session")
        if dates and (day<=dates[-1] or opening<=closes[-1]):
            raise StockStudyRefusal("REFUSED: calendar duplicate or reordered")
        dates.append(day); opens.append(opening); closes.append(closing)
    index = {day:n for n,day in enumerate(dates)}
    supplied_rows=value["signals"]
    if type(supplied_rows) is not list or not 1<=len(supplied_rows)<=MAX_SIGNALS:
        raise StockStudyRefusal("REFUSED: canonical batch empty or unbounded")
    rows, ids, issuer_days, ticker_ids, by_sid = [],set(),set(),{},{}
    for item in supplied_rows:
        if type(item) is not dict or frozenset(item)!=_SIGNAL_FIELDS:
            raise StockStudyRefusal("REFUSED: canonical signal fields drift")
        signal_id, issuer = item["signal_id"],item["issuer_id"]
        if type(signal_id) is not str or _LOOK_ID.fullmatch(signal_id) is None or type(issuer) is not str or _LOOK_ID.fullmatch(issuer) is None:
            raise StockStudyRefusal("REFUSED: canonical signal/issuer malformed")
        ticker=item["ticker"]
        if type(ticker) is not str or _TICKER.fullmatch(ticker) is None:
            raise StockStudyRefusal("REFUSED: canonical ticker malformed")
        sid=_identity(item["qc_symbol_id"],"QC SID")
        available=_utc(item["available_at_utc"])
        decision,entry,exit_day=(_session(item[key],key) for key in ("decision_session","entry_session","exit_session"))
        if entry not in index or decision!=entry or not 253<=index[entry] or index[entry]+60>=len(dates) or exit_day!=dates[index[entry]+20]:
            raise StockStudyRefusal("REFUSED: canonical first-open/horizon context incomplete")
        first=next((n for n,opening in enumerate(opens) if opening>available),None)
        if first!=index[entry] or available>opens[first]-_dt.timedelta(minutes=2):
            raise StockStudyRefusal("REFUSED: canonical event unavailable at two-minute MOO cutoff")
        mapping_first,mapping_last=(_session(item[key],key) for key in ("mapping_first_session","mapping_last_session"))
        if not mapping_first<=entry<exit_day<mapping_last or signal_id in ids or (issuer,entry) in issuer_days:
            raise StockStudyRefusal("REFUSED: mapping or duplicate issuer/day drift")
        if ticker in ticker_ids and ticker_ids[ticker]!=sid:
            raise StockStudyRefusal("REFUSED: ticker/SID ambiguity")
        ids.add(signal_id); issuer_days.add((issuer,entry));ticker_ids[ticker]=sid
        row=Signal(signal_id,ticker,sid,_digest(item["source_event_sha256"],"source event"),mapping_first,mapping_last,available,decision,entry,exit_day)
        rows.append(row);by_sid.setdefault(sid,[]).append(row)
    if rows!=sorted(rows,key=lambda row:(row.entry_session,row.signal_id)):
        raise StockStudyRefusal("REFUSED: canonical signal order drift")
    for trades in by_sid.values():
        trades.sort(key=lambda row:row.entry_session)
        if any(right.entry_session<=left.exit_session for left,right in zip(trades,trades[1:])):
            raise StockStudyRefusal("REFUSED: canonical same-SID overlap")
    _preflight_capacity(rows,tuple(dates),index)
    if value["registered_look_id"]!=APPROVED_LOOK_ID:
        raise StockStudyRefusal("REFUSED: manifest permanent parent look differs")
    return StudyManifest(actual,value["source_manifest_sha256"],value["security_master_sha256"],value["calendar_sha256"],value["outcome_vintage_sha256"],tuple(dates),tuple(rows),tuple(opens),tuple(closes),value["parent_study_id"],value["batch_id"],value["batch_plan_sha256"])'''

_PARSE_GATE = '''def parse_study_gate(raw: bytes, expected_sha256: str, manifest: StudyManifest, approved_look_id: str) -> StudyGate:
    value,actual=_decode(raw,expected_sha256,max_bytes=MAX_GATE_BYTES)
    if frozenset(value)!=_GATE_FIELDS or value["schema"]!=GATE_SCHEMA or value["scope"]!="single-research-backtest-only":
        raise StockStudyRefusal("REFUSED: canonical gate drift")
    if type(approved_look_id) is not str or _LOOK_ID.fullmatch(approved_look_id) is None or value["registered_look_id"]!=approved_look_id:
        raise StockStudyRefusal("REFUSED: permanent parent look unbound")
    if value["parent_study_id"]!=manifest.parent_study_id or value["batch_id"]!=manifest.batch_id or value["batch_plan_sha256"]!=manifest.batch_plan_sha256:
        raise StockStudyRefusal("REFUSED: parent/batch plan drift")
    if _digest(value["manifest_sha256"],"manifest")!=manifest.raw_sha256 or _digest(value["outcome_vintage_sha256"],"outcome")!=manifest.outcome_vintage_sha256:
        raise StockStudyRefusal("REFUSED: canonical gate object mismatch")
    return StudyGate(actual,approved_look_id,manifest.raw_sha256,_digest(value["rights_record_sha256"],"rights"),manifest.outcome_vintage_sha256)'''

_CAPACITY = '''@_exact_arithmetic
def _preflight_capacity(rows, sessions, index):
    if type(MAX_POSITIONS) is not int or MAX_POSITIONS!=20:
        raise StockStudyRefusal("REFUSED: frozen fixed-slot capacity drift")
    cash=_positive_decimal(STARTING_CASH,"starting cash")
    reserve=_positive_decimal(CASH_RESERVE,"reserve")
    slot=_positive_decimal(SLOT_BUDGET,"slot")
    capacity=min(MAX_POSITIONS,int((cash-reserve)//slot))
    decisions=[0]*len(sessions);deltas=[0]*(len(sessions)+1)
    for row in rows:
        decisions[index[row.entry_session]]+=1
        deltas[index[row.entry_session]+1]+=1
        deltas[index[row.exit_session]+1]-=1
    active=0
    for n in range(len(sessions)):
        active+=deltas[n]
        if active+decisions[n]>capacity:
            raise StockStudyRefusal("REFUSED: preopen fixed-slot/cash capacity underfill")'''

_CALLBACKS = '''    @_exact_arithmetic
    def _before_market_open(self) -> None:
        if self.live_mode or RESEARCH_BACKTEST_ENABLED is not True:
            raise StockStudyRefusal("REFUSED: live or unapproved canonical order path")
        if self.is_warming_up:
            return
        n=self._preopen_session_index
        if n>=len(self._manifest.sessions) or self.time.date()!=self._manifest.sessions[n] or n!=self._next_session_index:
            raise StockStudyRefusal("REFUSED: preopen calendar callback drift")
        now=_engine_utc(self.utc_time)
        if now!=self._manifest.opens[n]-_dt.timedelta(minutes=2):
            raise StockStudyRefusal("REFUSED: two-minute MOO callback instant drift")
        if self._pending:
            raise StockStudyRefusal("REFUSED: unresolved earlier opening orders")
        session=self._manifest.sessions[n]
        cash=self._cash_with_reserve()
        for sid,(held_row,held_quantity) in self._active.items():
            held_symbol,_=self._previous_regular_close(held_row,n)
            if str(held_symbol.id)!=sid or self.portfolio[held_symbol].quantity!=held_quantity:
                raise StockStudyRefusal("REFUSED: canonical preopen held quantity drift")
        planned_exits=[]
        for row in self._by_exit_decision.get(session,()):
            held=self._active.get(row.qc_symbol_id)
            if held is None or held[0]!=row:
                raise StockStudyRefusal("REFUSED: canonical exit lacks exact filled entry")
            symbol,_=self._previous_regular_close(row,n)
            if self.portfolio[symbol].quantity!=held[1]:
                raise StockStudyRefusal("REFUSED: canonical held quantity changed")
            planned_exits.append((row,symbol,-held[1]))
        batch_reserved=_Decimal("0");planned_entries=[]
        for row in self._by_decision.get(session,()):
            if row.available_at_utc>now:
                raise StockStudyRefusal("REFUSED: event unavailable at MOO cutoff")
            symbol,price=self._previous_regular_close(row,n)
            if row.qc_symbol_id in self._active or any(order.signal.qc_symbol_id==row.qc_symbol_id for order in self._pending.values()):
                raise StockStudyRefusal("REFUSED: overlapping canonical position")
            if len(self._active)+len(planned_entries)>=MAX_POSITIONS:
                raise StockStudyRefusal("REFUSED: canonical position capacity underfill")
            budget=min(SLOT_BUDGET,cash-CASH_RESERVE-batch_reserved)
            unit=price*OPEN_GAP_PAD
            quantity=int(budget//unit)
            if budget<=0 or quantity<=0:
                raise StockStudyRefusal("REFUSED: canonical cash/gap/one-share underfill")
            batch_reserved+=unit*quantity
            planned_entries.append((row,symbol,quantity))
        self._preopen_session_index+=1
        for row,symbol,quantity in planned_exits:
            self._submit(row,symbol,"EXIT",quantity,row.exit_session)
        for row,symbol,quantity in planned_entries:
            self._submit(row,symbol,"ENTRY",quantity,row.entry_session)

    def _previous_regular_close(self,row,n):
        if n<1:
            raise StockStudyRefusal("REFUSED: no prior regular-close pricing context")
        symbol=self._symbols[row.ticker]
        if str(symbol.id)!=row.qc_symbol_id:
            raise StockStudyRefusal("REFUSED: canonical QC SID changed")
        security=self.securities[symbol];bar=security.get_last_data()
        if not security.is_tradable or security.is_delisted or not security.has_data or bar is None or getattr(bar,"is_fill_forward",False):
            raise StockStudyRefusal("REFUSED: previous regular-close bar missing or invalid")
        ended=bar.end_time
        if type(ended) is not _dt.datetime:
            raise StockStudyRefusal("REFUSED: previous regular-close EndTime unavailable")
        if ended.tzinfo is None:
            ended=ended.replace(tzinfo=_ZoneInfo("America/New_York"))
        if ended.astimezone(_dt.timezone.utc)!=self._manifest.closes[n-1]:
            raise StockStudyRefusal("REFUSED: previous regular-close EndTime drift")
        return symbol,_positive_decimal(getattr(bar,"close",None),"previous regular close")

    def _after_market_close(self) -> None:
        if self.live_mode or RESEARCH_BACKTEST_ENABLED is not True:
            raise StockStudyRefusal("REFUSED: live or unapproved canonical completion path")
        if self.is_warming_up:
            return
        n=self._next_session_index
        if n>=len(self._manifest.sessions) or self.time.date()!=self._manifest.sessions[n] or self._preopen_session_index!=n+1:
            raise StockStudyRefusal("REFUSED: canonical completion calendar drift")
        if _engine_utc(self.utc_time)!=self._manifest.closes[n]+_dt.timedelta(minutes=1):
            raise StockStudyRefusal("REFUSED: canonical afterclose callback instant drift")
        if self._pending:
            raise StockStudyRefusal("REFUSED: canonical opening fill missing")
        self._cash_with_reserve()
        for sid,(row,quantity) in self._active.items():
            symbol,_=self._check_security(row,self._manifest.sessions[n])
            if str(symbol.id)!=sid or self.portfolio[symbol].quantity!=quantity:
                raise StockStudyRefusal("REFUSED: canonical held quantity drift")
        self._next_session_index+=1'''


def _render(legacy, manifest_raw, gate_raw, look):
    _need(type(legacy) is bytes and _sha(legacy) == LEGACY_SOURCE_SHA256, "legacy source is not exact frozen captured c80 source")
    source = legacy.decode("utf-8")
    source = _exact(source, 'SCHEMA = "insider-qc-stock-order-study-v1"', 'SCHEMA = "' + MANIFEST_SCHEMA + '"')
    source = _exact(source, 'GATE_SCHEMA = "insider-qc-single-backtest-gate-v1"', 'GATE_SCHEMA = "' + GATE_SCHEMA + '"')
    source = _exact(source, "from typing import NamedTuple", "from typing import NamedTuple\nfrom zoneinfo import ZoneInfo as _ZoneInfo")
    source = _exact(source, "from decimal import Decimal as _Decimal", "from decimal import localcontext as _localcontext\nfrom decimal import Decimal as _Decimal")
    source = _span(source, "_MANIFEST_FIELDS = frozenset({", "class StockStudyRefusal", _FIELDS)
    source = _span(source, "class StudyManifest(NamedTuple):", "class StudyGate(NamedTuple):", _MANIFEST_TYPE)
    source = _span(source, "def parse_study_manifest(", "def parse_study_gate(", _PARSE_MANIFEST)
    source = _span(source, "def parse_study_gate(", "def _positive_decimal(", _PARSE_GATE)
    source = _span(source, "def _preflight_capacity(", "def _engine_utc(", _CAPACITY)
    source = _exact(source, "        self._next_session_index = 0", "        self._next_session_index = 0\n        self._preopen_session_index = 0")
    source = _exact(source, '            previous = manifest.sessions[session_index[row.exit_session] - 1]\n            self._by_exit_decision.setdefault(previous, []).append(row)', '            self._by_exit_decision.setdefault(row.exit_session, []).append(row)')
    source = _exact(source, "        self.schedule.on(\n", "        self.schedule.on(self.date_rules.every_day(self._clock_symbol), self.time_rules.before_market_open(self._clock_symbol, 2), self._before_market_open)\n        self.schedule.on(\n")
    source = _span(source, "    def _after_market_close(self)", "    def on_data(self", _CALLBACKS)
    source = _exact(source, "    def on_order_event(self, order_event) -> None:", "    @_exact_arithmetic\n    def on_order_event(self, order_event) -> None:")
    source = _exact(source, '        fill_price = _positive_decimal(order_event.fill_price, "MOO fill price")', '        index = self._manifest.sessions.index(pending.fill_session)\n        now = _engine_utc(self.utc_time)\n        if not self._manifest.opens[index] <= now <= self._manifest.opens[index] + _dt.timedelta(minutes=1):\n            raise StockStudyRefusal("REFUSED: canonical opening callback outside minute profile")\n        fill_price = _positive_decimal(order_event.fill_price, "MOO fill price")')
    source = _exact(source, "IBQC_STUDY_INPUT|", "IBQC_CANONICAL_INPUT|")
    source = _exact(source, "IBQC_STUDY_ORDER_PATH_COMPLETE|", "IBQC_CANONICAL_ORDER_PATH_COMPLETE|")
    suffix = _sha(manifest_raw)[:24]
    for key, value in {"SIGNAL_OBJECT_STORE_KEY": "insider-buying/canonical/" + suffix + "/signals.json", "APPROVED_SIGNAL_SHA256": _sha(manifest_raw),
                       "GATE_OBJECT_STORE_KEY": "insider-buying/canonical/" + suffix + "/gate.json", "APPROVED_GATE_SHA256": _sha(gate_raw), "APPROVED_LOOK_ID": look}.items():
        source = _exact(source, key + ' = ""\n', key + " = " + json.dumps(value) + "\n")
    _need(source.count("RESEARCH_BACKTEST_ENABLED = False\n") == 1 and "RESEARCH_BACKTEST_ENABLED = True\n" not in source, "rendered candidate must remain default-disabled")
    source = '"""Default-disabled canonical-first-open QC v2 candidate; generated from exact frozen c80 source.\nMOO cutoff=open-minus-two-minutes; prior regular-close sizing; no late-row dropping.\nNative opening callback minute profile is NOT independent auction/price/engine parity.\n"""\n' + source[source.index("from __future__ import annotations"):]
    compile(source, "<canonical-qc-captured-source-v2>", "exec", dont_inherit=True)
    return source.encode("utf-8")


def _partition(signals, dates):
    index = {day: n for n, day in enumerate(dates)}
    batches, active, available, available_set, ending = [], [], [], set(), []
    for signal in signals:
        entry, exit_day = index[signal["entry_session"]], index[signal["exit_session"]]
        while ending and ending[0][0] < entry:
            _, batch, sid = heapq.heappop(ending)
            active[batch].remove(sid)
            if batch not in available_set:
                heapq.heappush(available, batch); available_set.add(batch)
        held, selected = [], None
        while available:
            batch = heapq.heappop(available); available_set.remove(batch)
            if signal["qc_symbol_id"] not in active[batch]:
                selected = batch; break
            held.append(batch)
        for batch in held:
            heapq.heappush(available, batch); available_set.add(batch)
        if selected is None:
            _need(len(batches) < MAX_BATCHES, "complete deterministic batch population exceeds bound")
            selected = len(batches); batches.append([]); active.append(set())
        batches[selected].append(signal)
        active[selected].add(signal["qc_symbol_id"])
        heapq.heappush(ending, (exit_day, selected, signal["qc_symbol_id"]))
        if len(active[selected]) < 20:
            heapq.heappush(available, selected); available_set.add(selected)
    return batches


@dataclass(frozen=True, slots=True, weakref_slot=True)
class CanonicalQcBatchPlan:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def _body(self):
        registered = _BUILT.get(id(self))
        _need(type(self) is CanonicalQcBatchPlan and self._token is _TOKEN and registered is not None
              and registered[0]() is self and type(self._bytes) is bytes and registered[1] == self._bytes, "canonical batch plan reconstructed or altered")
        return json.loads(self._bytes)

    def to_payload(self):
        body = self._body()
        return {"kind": body["version"], "parent_study_id": body["parent_study_id"], "registered_look_id": body["registered_look_id"],
            "plan_sha256": body["plan_sha256"], "source_event_study_sha256": body["source_event_study_sha256"],
            "source_event_manifest_sha256": body["source_event_manifest_sha256"], "event_count": sum(len(row) for row in body["batches"]),
            "batch_count": len(body["batches"]), "batch_ids": [self._batch_id(n) for n in range(len(body["batches"]))],
            "all_batches_required_before_analysis": True, "maximum_attempts_per_candidate": 3,
            "planned_starting_cash_per_child": "100000", "slot_budget_usd": "4500", "cash_reserve_usd": "10000", "maximum_slots": 20,
            "pooled_capital_portfolio_inferred": False, "source_authenticated_here": False, "look_authority": False,
            "candidate_enabled": False, "dispatch_enabled": False, "qc_jobs": 0, "research_looks": 0,
            "engine_revision_parity_verified": False, "auction_price_parity_verified": False, "data_cost_parity_verified": False}

    def _batch_id(self, index):
        body = self._body()
        _need(type(index) is int and 0 <= index < len(body["batches"]), "exact child batch index required")
        return "ibcanon-" + body["plan_sha256"][:24] + "-" + str(index + 1)

    def batch_manifest_bytes(self, index):
        body = self._body(); batch_id = self._batch_id(index)
        return study.canonical_bytes({"schema": MANIFEST_SCHEMA, "parent_study_id": body["parent_study_id"],
            "registered_look_id": body["registered_look_id"], "batch_id": batch_id, "batch_plan_sha256": body["plan_sha256"],
            "source_event_manifest_sha256": body["source_event_manifest_sha256"], **body["manifest_roots"],
            "sessions": body["sessions"], "signals": sorted(body["batches"][index], key=lambda row: (row["entry_session"], row["signal_id"]))})

    def batch_files(self, index):
        body = self._body(); manifest = self.batch_manifest_bytes(index)
        gate = study.canonical_bytes({"schema": GATE_SCHEMA, "scope": "single-research-backtest-only",
            "parent_study_id": body["parent_study_id"], "registered_look_id": body["registered_look_id"], "batch_id": self._batch_id(index),
            "batch_plan_sha256": body["plan_sha256"], "manifest_sha256": _sha(manifest),
            "rights_record_sha256": body["rights_sha256"], "outcome_vintage_sha256": body["manifest_roots"]["outcome_vintage_sha256"]})
        return {"main.py": _render(bytes.fromhex(body["legacy_hex"]), manifest, gate, body["registered_look_id"]), "signals.json": manifest, "gate.json": gate}

    @property
    def sha256(self):
        self._body()
        return _sha(self._bytes)

    def verify_completion_set(self, *, terminals: tuple[bytes, ...], expected_terminal_sha256s: tuple[str, ...]) -> bytes:
        return _completion(self, terminals, expected_terminal_sha256s)

    def verify_native_completion_set(self, results):
        body = self._body()
        _need(type(results) is tuple and len(results) == len(body["batches"]), "ALL sealed native child exports required")
        for n, result in enumerate(results):
            checked = result._body() if type(result) is CanonicalQcExport else None
            _need(checked is not None and checked["plan_sha256"] == self.sha256 and checked["batch_index"] == n,
                  "sealed native child order/plan differs")
        raws = tuple(result.terminal_bytes() for result in results)
        return _completion(self, raws, tuple(_sha(raw) for raw in raws))

    def new_child_attempt_ledger(self, index):
        body = self._body()
        return study.new_attempt_ledger(candidate_id=self._batch_id(index), registered_look_id=body["registered_look_id"], trust_scope=body["trust_scope"])

    def _ledger(self, index, raw, expected):
        body = self._body()
        _need(body["trust_scope"] == "fixture", "production attempt accounting blocked without configured canonical source")
        _need(type(raw) is bytes and _sha(raw) == native._digest(expected), "child ledger external anchor differs")
        try:
            ledger = study._ledger(raw)
        except ValueError as exc:
            raise CanonicalQcCandidateError("REFUSED: existing three-attempt ledger schema differs") from exc
        _need(ledger["candidate_id"] == self._batch_id(index) and ledger["registered_look_id"] == body["registered_look_id"]
              and ledger["trust_scope"] == "fixture", "child ledger candidate/look differs")
        files = self.batch_files(index)
        _need(all(row["package_sha256"] == self.sha256 and row["source_sha256"] == _sha(files["main.py"]) for row in ledger["attempts"]), "prior child attempt source/plan differs")
        return ledger

    def begin_child_attempt(self, *, index, ledger_raw, expected_ledger_sha256, attempt_id):
        """Reuse the existing maximum-three/pending/completed rules; no launch."""
        ledger = self._ledger(index, ledger_raw, expected_ledger_sha256)
        _need(study.attempt_ledger_status(ledger_raw)["can_begin_attempt"], "existing three-attempt state forbids another child attempt")
        _id(attempt_id)
        _need(attempt_id not in {row["attempt_id"] for row in ledger["attempts"]}, "duplicate child attempt")
        ledger["attempts"].append({"attempt_id": attempt_id, "package_sha256": self.sha256,
            "source_sha256": _sha(self.batch_files(index)["main.py"]), "state": "pending", "result_sha256": None})
        raw = study.canonical_bytes(ledger); study._ledger(raw)
        return raw

    def finish_child_attempt(self, *, index, ledger_raw, expected_ledger_sha256, native_result=None,
                             failure_raw=None, expected_failure_sha256=None):
        """Fixture accounting only; failures count even without a backtest ID.

        Failure diagnostic bytes are externally anchored, NOT authenticated
        native compile proof. A successor configured/authenticated profile is
        required before production attempt accounting or dispatch.
        """
        ledger = self._ledger(index, ledger_raw, expected_ledger_sha256)
        _need(bool(ledger["attempts"]) and ledger["attempts"][-1]["state"] == "pending", "child lacks pending attempt")
        attempt = ledger["attempts"][-1]
        _need((native_result is not None) != (failure_raw is not None), "exact one native completion or failure diagnostic required")
        if native_result is not None:
            _need(type(native_result) is CanonicalQcExport, "sealed native result required")
            result = native_result._body()
            _need(result["plan_sha256"] == self.sha256 and result["batch_index"] == index
                  and result["attempt_id"] == attempt["attempt_id"], "native result child/attempt differs")
            terminal = json.loads(native_result.terminal_bytes()); clock = {r["session"]: r["open_utc"] for r in self._body()["sessions"]}
            attempt["state"] = "completed" if all(row["filled_at_utc"] == clock[row["session"]] for row in terminal["fills"]) else "invalid_data"
            attempt["result_sha256"] = _sha(native_result._bytes)
        else:
            result = _decode(failure_raw, expected_failure_sha256)
            required = {"schema", "trust_scope", "parent_study_id", "batch_id", "batch_plan_sha256", "registered_look_id", "candidate_source_sha256",
                "attempt_id", "project_id", "compile_id", "backtest_id", "status", "errors"}
            body = self._body()
            _need(type(result) is dict and set(result) == required and result["schema"] == "insider-canonical-qc-attempt-failure-v1"
                  and result["trust_scope"] == "fixture" and result["parent_study_id"] == body["parent_study_id"]
                  and result["batch_id"] == self._batch_id(index) and result["batch_plan_sha256"] == body["plan_sha256"]
                  and result["registered_look_id"] == body["registered_look_id"] and result["candidate_source_sha256"] == attempt["source_sha256"]
                  and result["attempt_id"] == attempt["attempt_id"], "failure diagnostic child/source/attempt differs")
            for key in ("project_id", "compile_id"):
                _id(result[key])
            states = {"CompileError": "compile_failed", "RuntimeError": "runtime_failed", "Cancelled": "cancelled", "Refused": "refused"}
            _need(type(result["status"]) is str and result["status"] in states and type(result["errors"]) is list
                  and 1 <= len(result["errors"]) <= 100 and all(type(error) is str and 0 < len(error) <= 2000 for error in result["errors"]), "failure status/errors differ")
            if result["status"] == "CompileError":
                _need(result["backtest_id"] is None, "compile failure must not invent backtest ID")
            else:
                _id(result["backtest_id"])
            attempt["state"] = states[result["status"]]; attempt["result_sha256"] = _sha(failure_raw)
        raw = study.canonical_bytes(ledger); study._ledger(raw)
        return raw


def _build_canonical_qc_batch_plan(*, source_events: SourceEventStudyManifest, legacy_source: bytes,
                                 security_master: bytes, entry_reference: bytes, registration: bytes,
                                 parent_study_id: str, v2=False) -> CanonicalQcBatchPlan:
    """Plan every sealed causal event BEFORE outcomes; no enabled source route."""
    _id(parent_study_id)
    _need(type(legacy_source) is bytes and _sha(legacy_source) == LEGACY_SOURCE_SHA256, "captured legacy source differs")
    try:
        metadata = validate_source_event_study_manifest(source_events)
    except ValueError as exc:
        raise CanonicalQcCandidateError("REFUSED: exact sealed source-event manifest required") from exc
    from research.insider_buying import backtest_event_study_manifest as causal
    from research.insider_buying import backtest_event_study_collection as collection
    _need(metadata["kind"] in ({causal.VERSION_V2, collection.VERSION_V2} if v2 else {causal.VERSION, collection.VERSION}),
          "canonical candidate source causal epoch differs")
    raw = source_events.manifest_bytes()
    validator = analysis.verify_registered_analysis_manifest_v2 if v2 else analysis.verify_registered_analysis_manifest
    checked = validator(registration_raw=registration, manifest_raw=raw,
        expected_registration_sha256=metadata["registration_sha256"], expected_manifest_sha256=_sha(raw),
        expected_implementation_sha256=metadata["analysis_implementation_sha256"])
    manifest, registered = checked["manifest"], checked["registration"]
    master = _decode(security_master, metadata["security_master_sha256"])
    _decode(entry_reference, metadata["entry_reference_sha256"])
    sessions = manifest["sessions"]; dates = [row["session"] for row in sessions]
    opens = {row["session"]: analysis._utc(row["open_utc"]) for row in sessions}
    # Compact facts originate in the sealed producer, which already checked
    # every streamed/nested reference record. Never reload all 60-bar contexts.
    reference_facts = source_events.entry_reference_facts()
    contexts = {row["entry_session"]: row for row in reference_facts}
    events = manifest["events"]
    _need(type(events) is list and 0 < len(events) <= MAX_EVENTS and len(events) == metadata["event_count"], "complete source-event population absent or unbounded")
    signals = []
    for event in events:
        cutoff = opens[event["entry_session"]] - timedelta(minutes=2)
        _need(analysis._utc(event["available_at_utc"]) <= cutoff, "whole plan refuses event after two-minute MOO cutoff")
        context = contexts[event["entry_session"]]
        _need(analysis._utc(context["latest_prerequisite_knowledge_at_utc"]) <= cutoff,
              "whole plan refuses prerequisite reference after MOO cutoff")
        matches = [row for row in master["mappings"] if row["qc_symbol_id"] == event["security_id"] and row["issuer_cik"] == event["issuer_id"]]
        _need(len(matches) == 1 and analysis._utc(matches[0]["knowledge_at_utc"]) <= cutoff, "exact source issuer/SID mapping unavailable at cutoff")
        mapping = matches[0]
        _need(mapping["mapping_first_session"] <= event["entry_session"] < event["exit_session"] < mapping["mapping_last_session"], "mapped canonical horizon incomplete")
        signals.append({"signal_id": event["signal_id"], "issuer_id": event["issuer_id"], "ticker": mapping["ticker"],
            "qc_symbol_id": event["security_id"], "source_event_sha256": event["source_event_sha256"],
            "mapping_first_session": mapping["mapping_first_session"], "mapping_last_session": mapping["mapping_last_session"],
            "available_at_utc": event["available_at_utc"][:-1] + "+00:00", "decision_session": event["entry_session"],
            "entry_session": event["entry_session"], "exit_session": event["exit_session"]})
    signals.sort(key=lambda row: (row["entry_session"], row["issuer_id"], row["signal_id"]))
    batches = _partition(signals, dates)
    _need(sorted(row["signal_id"] for batch in batches for row in batch) == sorted(row["signal_id"] for row in events), "batch partition changed complete event population")
    body = {"version": VERSION_V2 if v2 else VERSION, "trust_scope": metadata["trust_scope"], "parent_study_id": parent_study_id,
        "candidate_id": registered["candidate_id"], "registered_look_id": registered["registered_look_id"],
        "registration_sha256": metadata["registration_sha256"], "source_event_study_sha256": source_events.sha256,
        "source_event_manifest_sha256": _sha(raw), "rights_sha256": registered["rights_sha256"],
        "manifest_roots": {key: manifest[key] for key in ("source_manifest_sha256", "security_master_sha256", "calendar_sha256", "outcome_vintage_sha256")},
        "sessions": sessions, "batches": batches, "entry_reference_facts": reference_facts, "legacy_hex": legacy_source.hex()}
    body["plan_sha256"] = _sha(study.canonical_bytes({key: value for key, value in body.items() if key != "legacy_hex"}))
    encoded = study.canonical_bytes(body)
    _need(len(encoded) <= MAX_BYTES, "complete immutable batch plan exceeds bound")
    result = CanonicalQcBatchPlan(encoded, _TOKEN)
    _BUILT[id(result)] = (weakref.ref(result, lambda _, identity=id(result): _BUILT.pop(identity, None)), encoded)
    # Compile the exact first child now; every child has the same guarded spans.
    result.batch_files(0)
    return result


def build_canonical_qc_batch_plan(**kwargs) -> CanonicalQcBatchPlan:
    """Unchanged v1 source epoch; no generic future-reference override."""
    _need("v2" not in kwargs, "public canonical profile override forbidden")
    return _build_canonical_qc_batch_plan(**kwargs)


def build_canonical_qc_batch_plan_v2(**kwargs) -> CanonicalQcBatchPlan:
    """Explicit causal-v2 profile, same MOO economics and native clock checks."""
    _need("v2" not in kwargs, "public canonical profile override forbidden")
    return _build_canonical_qc_batch_plan(**kwargs, v2=True)


def _completion(plan, terminals, digests):
    body = plan._body()
    _need(body["trust_scope"] == "fixture", "production completion blocked without registered canonical configuration/native-v2 provenance")
    _need(type(terminals) is tuple and type(digests) is tuple and len(terminals) == len(digests) == len(body["batches"]), "ALL planned child completions required before analysis")
    fills, event_ids, seen_runs = [], set(), set()
    opens = {row["session"]: row["open_utc"] for row in body["sessions"]}
    required = {"schema", "trust_scope", "parent_study_id", "batch_id", "batch_plan_sha256", "registered_look_id",
        "candidate_source_sha256", "manifest_sha256", "gate_sha256", "project_id", "compile_id", "backtest_id",
        "status", "errors", "processed_sessions", "final_positions", "fills"}
    for n, (raw, digest) in enumerate(zip(terminals, digests, strict=True)):
        terminal = _decode(raw, digest)
        _need(set(terminal) == required and terminal["schema"] == "insider-canonical-qc-child-terminal-v1"
              and terminal["trust_scope"] == "fixture" and terminal["parent_study_id"] == body["parent_study_id"]
              and terminal["batch_id"] == plan._batch_id(n) and terminal["batch_plan_sha256"] == body["plan_sha256"]
              and terminal["registered_look_id"] == body["registered_look_id"], "child completion plan/look/epoch mismatch")
        files = plan.batch_files(n)
        _need(terminal["candidate_source_sha256"] == _sha(files["main.py"]) and terminal["manifest_sha256"] == _sha(files["signals.json"])
              and terminal["gate_sha256"] == _sha(files["gate.json"]), "child completion source/object parity differs")
        run = tuple(_id(terminal[key]) for key in ("project_id", "compile_id", "backtest_id"))
        _need(run not in seen_runs, "same native run cannot complete multiple planned children")
        seen_runs.add(run)
        _need(terminal["status"] == "Completed" and terminal["errors"] == [] and terminal["final_positions"] == []
              and terminal["processed_sessions"] == [row["session"] for row in body["sessions"]], "child incomplete/error/residual calendar path")
        expected = {row["signal_id"]: row for row in body["batches"][n]}
        _need(type(terminal["fills"]) is list and len(terminal["fills"]) == 2 * len(expected), "child full order population incomplete")
        seen, order_ids, quantities = set(), set(), {}
        for fill in terminal["fills"]:
            _need(type(fill) is dict and set(fill) == {"signal_id", "side", "security_id", "session", "filled_at_utc", "quantity", "price", "order_id"}, "child native fill schema differs")
            key = (fill["signal_id"], fill["side"])
            _need(fill["signal_id"] in expected and fill["side"] in {"entry", "exit"} and key not in seen, "child foreign/duplicate fill")
            row = expected[fill["signal_id"]]
            _need(fill["security_id"] == row["qc_symbol_id"] and fill["session"] == row[fill["side"] + "_session"]
                  and fill["filled_at_utc"] == opens[fill["session"]], "child exact native SID/session/open evidence differs")
            quantity = fill["quantity"]
            _need(type(quantity) is int and 0 < abs(quantity) <= 10**12
                  and (quantity > 0 if fill["side"] == "entry" else quantity < 0), "child fill quantity direction/type differs")
            try:
                price = analysis._decimal(fill["price"], positive=True)
            except ValueError as exc:
                raise CanonicalQcCandidateError("REFUSED: child fill price invalid") from exc
            if fill["side"] == "entry":
                with localcontext() as arithmetic:
                    arithmetic.prec = 100
                    _need(price * quantity <= Decimal(4500), "child actual opening fill exceeds frozen slot budget")
            order_id = _id(fill["order_id"])
            _need(order_id not in order_ids, "child duplicate native order")
            order_ids.add(order_id); seen.add(key); quantities[key] = quantity
            # Native order IDs are only per-run unique. Preserve run association.
            fills.append({**fill, "order_id": "batch-" + str(n + 1) + ":" + order_id})
        _need(all(quantities[(sid, "entry")] == -quantities[(sid, "exit")] for sid in expected), "child partial unmatched entry/exit quantities")
        event_ids.update(expected)
    _need(event_ids == {row["signal_id"] for batch in body["batches"] for row in batch}, "aggregate completion dropped source events")
    return analysis.canonical_bytes({"schema": "insider-stock-event-study-terminal-v1", "trust_scope": "fixture",
        "registration_sha256": body["registration_sha256"], "manifest_sha256": body["source_event_manifest_sha256"],
        "candidate_id": body["candidate_id"], "registered_look_id": body["registered_look_id"],
        "outcome_vintage_sha256": body["manifest_roots"]["outcome_vintage_sha256"], "status": "Completed", "errors": [],
        "final_positions": [], "fills": fills})


@dataclass(frozen=True, slots=True, weakref_slot=True)
class CanonicalQcExport:
    """Sealed native observations; callback timestamps are NEVER relabeled."""
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def _body(self):
        registered = _NATIVE_BUILT.get(id(self))
        _need(type(self) is CanonicalQcExport and self._token is _TOKEN and registered is not None
              and registered[0]() is self and type(self._bytes) is bytes and registered[1] == self._bytes, "canonical native export reconstructed or altered")
        return json.loads(self._bytes)

    def terminal_bytes(self):
        return bytes.fromhex(self._body()["terminal_hex"])

    def to_payload(self):
        return self._body()["summary"]

    def native_fills(self):
        return self._body()["native_fills"]

    def native_cash_path(self):
        return self._body()["native_cash_path"]


def _money(value):
    number = native._number(value)
    # This successor profile refuses unsupported precision, NEVER rounds it.
    # <=41 monetary digits, <=13 share digits and <=40,000 executions need
    # <60 exact product/sum digits; local precision100 is therefore sufficient.
    _need(number.copy_abs() <= Decimal("1e12") and (number == 0 or number.as_tuple().exponent >= -28),
          "native USD magnitude/scale exceeds explicit exact money profile")
    return number


def _canonical_order_fills(orders, events, capture, manifest, clock):
    # Native REST field/type and lifecycle validators are shared with v1;
    # submission semantics are explicitly v2, not a fake prior-close clock.
    expected = {f'IB5:{manifest["registered_look_id"]}:{row["signal_id"]}:{side.upper()}': (row, side)
                for row in manifest["signals"] for side in ("entry", "exit")}
    _need(type(events) is list and len(events) <= native.MAX_EVENTS and len(orders) == len(expected), "complete bounded native order population required")
    flat, fills, cash_events, seen_ids, seen_tags, seen_events, net = [], [], [], set(), set(), set(), {}
    for order in orders:
        native._fields(order, native._ORDER_REQUIRED, native._ORDER_FIELDS)
        oid = native._integer(order["id"], 1, 2**63-1)
        _need(oid not in seen_ids and type(order["tag"]) is str and order["tag"] in expected and order["tag"] not in seen_tags, "foreign/duplicate native order/tag")
        row, side = expected[order["tag"]]; seen_ids.add(oid); seen_tags.add(order["tag"])
        symbol = native._fields(order["symbol"], {"id", "value", "permtick"})
        _need(symbol["id"] == row["qc_symbol_id"] and symbol["value"] == row["ticker"] and type(symbol["permtick"]) is str and symbol["permtick"], "native canonical SID/ticker differs")
        quantity = native._shares(order["quantity"])
        _need(quantity != 0 and (quantity > 0) == (side == "entry") and type(order["type"]) is int and order["type"] == 4
              and type(order["securityType"]) is int and order["securityType"] == 1 and type(order["direction"]) is int
              and order["direction"] == (0 if side == "entry" else 1) and type(order["status"]) is int and order["status"] == 3, "native MOO/full-fill direction/type differs")
        session = row[side + "_session"]; opening = clock[session][0]
        submitted = native._utc(order["time"])
        _need(submitted == opening - timedelta(minutes=2), "native canonical submission differs from exact two-minute cutoff")
        if "createdTime" in order:
            _need(native._utc(order["createdTime"]) == submitted, "native creation/submission differs")
        lifecycle = order["events"]
        _need(type(lifecycle) is list and 1 <= len(lifecycle) <= 100, "native lifecycle absent/unbounded")
        previous, terminal = submitted, False
        for index, event in enumerate(lifecycle, 1):
            native._fields(event, native._EVENT_FIELDS)
            eid = native._identity(event["id"]); instant = native._event_time(event["time"])
            _need(eid not in seen_events and type(event["orderId"]) is int and event["orderId"] == oid
                  and type(event["orderEventId"]) is int and event["orderEventId"] == index
                  and event["algorithmId"] == capture["backtest_id"] and event["symbol"] == symbol["id"]
                  and event["symbolValue"] == symbol["value"] and event["symbolPermtick"] == symbol["permtick"]
                  and instant >= previous and not terminal, "native lifecycle association/order differs")
            previous = instant; seen_events.add(eid)
            _need(event["direction"] == ("buy" if side == "entry" else "sell") and native._shares(event["quantity"]) == quantity
                  and event["isAssignment"] is False and event["isInTheMoney"] is False and event["fillPriceCurrency"] == "USD"
                  and event["orderFeeCurrency"] == "USD" and type(event["message"]) is str and len(event["message"]) <= 2000
                  and _money(event["orderFeeAmount"]) >= 0, "native money/option fields differ")
            status = event["status"]; price = _money(event["fillPrice"]); filled = native._shares(event["fillQuantity"])
            _need(type(status) is str and status in {"new", "submitted", "filled"}, "native partial/rejected/unknown lifecycle")
            if status == "filled":
                _need(filled == quantity and price > 0 and opening <= instant <= opening + timedelta(minutes=1)
                      and native._utc(order["lastFillTime"]) == instant, "native full opening-minute fill differs")
                fills.append({"signal_id": row["signal_id"], "side": side, "security_id": symbol["id"], "session": session,
                    "filled_at_utc": instant.isoformat().replace("+00:00", "Z"), "quantity": quantity, "price": str(price), "order_id": str(oid)})
                cash_events.append((instant, oid, quantity, price, _money(event["orderFeeAmount"])))
                terminal = True; net[symbol["id"]] = net.get(symbol["id"], 0) + quantity
            else:
                _need(filled == 0 and price == 0 and _money(event["orderFeeAmount"]) == 0,
                      "native nonfill contains execution/fees")
            flat.append(event)
        _need(terminal, "native filled order lacks final full fill")
    _need(native._native_equal(flat, events), "native separate events differ in values/types/completeness")
    _need(all(quantity == 0 for quantity in net.values()), "native residual quantities remain")
    cash = Decimal(100000); minimum = cash
    with localcontext() as arithmetic:
        arithmetic.prec = 100
        for _, _, quantity, price, fee in sorted(cash_events):
            notional = price * quantity
            _need(quantity < 0 or notional <= Decimal(4500), "native actual entry fill exceeds frozen slot budget")
            cash -= notional + fee
            _need(cash >= Decimal(10000), "native actual fills/fees breach fixed cash reserve")
            minimum = min(minimum, cash)
    return fills, {"starting_cash_usd": "100000", "ending_cash_usd": str(cash), "minimum_cash_usd": str(minimum),
        "observed_fill_fees_usd": [str(row[4]) for row in sorted(cash_events)], "capital_pooling_inferred": False}


def adapt_canonical_qc_export(*, plan: CanonicalQcBatchPlan, batch_index: int, native_backtest: bytes,
                             order_pages: tuple[bytes, ...], native_order_events: bytes, project_files: bytes,
                             cloud_signal_manifest: bytes, cloud_gate: bytes, logs_pages: tuple[bytes, ...],
                             capture_manifest: bytes, trust_roots: native.QcExportTrustRoots) -> CanonicalQcExport:
    """Ingest invented/native supplied v2 captures, never retrieve or activate.

    Currently fixture-only because emitted code stays disabled. Full engine,
    source authorization and fee/data/auction parity need independent evidence.
    Native open+one-minute callbacks remain observed; strict registered analysis
    completion refuses them, rather than inventing an exact-open execution.
    """
    _need(type(plan) is CanonicalQcBatchPlan and type(trust_roots) is native.QcExportTrustRoots,
          "exact sealed plan and separate native trust roots required")
    body = plan._body(); files = plan.batch_files(batch_index)
    try:
        trust_roots.validate()
        _need(body["trust_scope"] == trust_roots.trust_scope == "fixture", "production native-v2 blocked without registered configured source")
        required = {"schema", "profile", "trust_scope", "origin", "plan_sha256", "batch_id", "project_id", "compile_id", "backtest_id",
            "attempt_id", "compiled_source_sha256", "project_files_sha256", "signal_manifest_sha256", "gate_sha256", "native_backtest_sha256",
            "native_order_events_sha256", "order_pages", "logs_pages"}
        capture = native._fields(native._decode(capture_manifest, trust_roots.capture_manifest_sha256), required)
        _need(capture["schema"] == "insider-qc-canonical-capture-v2" and capture["profile"] == NATIVE_PROFILE
              and capture["trust_scope"] == "fixture" and capture["origin"] == "invented-native-QC-export"
              and capture["plan_sha256"] == plan.sha256 and capture["batch_id"] == plan._batch_id(batch_index), "externally anchored canonical capture context differs")
        native._integer(capture["project_id"], 1, 2**63-1)
        for key in ("compile_id", "backtest_id", "attempt_id"):
            native._identity(capture[key])
        _need(capture["compiled_source_sha256"] == _sha(files["main.py"]) and capture["signal_manifest_sha256"] == _sha(files["signals.json"])
              and capture["gate_sha256"] == _sha(files["gate.json"]), "capture source/object parity differs")
        _need(type(order_pages) is tuple and type(logs_pages) is tuple and all(type(raw) is bytes for raw in order_pages + logs_pages), "exact native byte-page tuples required")
        raws = (native_backtest, native_order_events, project_files, cloud_signal_manifest, cloud_gate, capture_manifest) + order_pages + logs_pages
        _need(all(type(raw) is bytes for raw in raws) and sum(map(len, raws)) <= native.MAX_TOTAL_BYTES, "bounded exact native bytes required")
        native._source_and_objects(capture, files, project_files, cloud_signal_manifest, cloud_gate)
        manifest = json.loads(files["signals.json"])
        clock = {row["session"]: (analysis._utc(row["open_utc"]), analysis._utc(row["close_utc"])) for row in manifest["sessions"]}
        response = native._fields(native._decode(native_backtest, capture["native_backtest_sha256"]), {"backtest", "success", "errors"}, {"backtest", "success", "errors", "debugging"})
        native._success(response)
        result = native._fields(response["backtest"], native._BACKTEST_REQUIRED, native._BACKTEST_FIELDS)
        _need(type(result["projectId"]) is int and result["projectId"] == capture["project_id"] and result["backtestId"] == capture["backtest_id"]
              and result["status"] == "Completed." and result["completed"] is True and result["hasInitializeError"] is False
              and result["error"] == "" and result["stacktrace"] == "", "native canonical run not clean Completed")
        _need(type(result["statistics"]) is dict and type(result["statistics"].get("Total Orders")) is str
              and re.fullmatch(r"0|[1-9][0-9]{0,5}", result["statistics"]["Total Orders"]), "native total orders absent/malformed")
        orders = native._pages(order_pages, capture["order_pages"])
        _need(len(orders) == int(result["statistics"]["Total Orders"]), "native canonical pagination incomplete")
        events = native._decode(native_order_events, capture["native_order_events_sha256"], array=True)
        fills, cash_path = _canonical_order_fills(orders, events, capture, manifest, clock)
        logs = native._pages(logs_pages, capture["logs_pages"], logs=True)
        _need(all(type(line) is str and len(line) <= 4000 for line in logs), "native logs unbounded")
        markers = [re.sub(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} : ", "", line) for line in logs]
        look = body["registered_look_id"]; count = len(manifest["signals"])
        start = f'IBQC_CANONICAL_INPUT|look={look}|manifest={_sha(files["signals.json"])}|gate={_sha(files["gate.json"])}|signals={count}|canonical=false'
        end = f'IBQC_CANONICAL_ORDER_PATH_COMPLETE|look={look}|manifest={_sha(files["signals.json"])}|entries={count}|exits={count}|canonical=false'
        _need(markers.count(start) == markers.count(end) == 1 and markers.index(start) < markers.index(end), "native pinned full-calendar completion markers absent/duplicate/reordered")
        _need(type(result["runtimeStatistics"]) is dict and type(result["runtimeStatistics"].get("Holdings")) is str
              and re.fullmatch(r"\$0(?:\.0+)?", result["runtimeStatistics"]["Holdings"]), "native nonzero/missing terminal holdings")
        _need(type(result["serverStatistics"]) is dict and type(result["serverStatistics"].get("LEAN Version")) is str
              and 0 < len(result["serverStatistics"]["LEAN Version"]) <= 80, "native engine observation absent")
        terminal = {"schema": "insider-canonical-qc-child-terminal-v1", "trust_scope": "fixture", "parent_study_id": body["parent_study_id"],
            "batch_id": plan._batch_id(batch_index), "batch_plan_sha256": body["plan_sha256"], "registered_look_id": look,
            "candidate_source_sha256": _sha(files["main.py"]), "manifest_sha256": _sha(files["signals.json"]), "gate_sha256": _sha(files["gate.json"]),
            "project_id": str(capture["project_id"]), "compile_id": capture["compile_id"], "backtest_id": capture["backtest_id"], "status": "Completed",
            "errors": [], "processed_sessions": [row["session"] for row in manifest["sessions"]], "final_positions": [], "fills": fills}
        summary = {"kind": NATIVE_PROFILE, "native_money_profile": NATIVE_MONEY_PROFILE,
            "source_contents_verified": True, "native_order_count": len(orders), "native_event_count": len(events),
            "native_engine_version_observed": result["serverStatistics"]["LEAN Version"], "source_authenticated_here": False,
            "engine_revision_parity_verified": False, "auction_price_parity_verified": False, "data_cost_parity_verified": False,
            "dispatch_enabled": False, "look_authority": False, "qc_jobs": 0, "research_looks": 0}
        encoded = study.canonical_bytes({"summary": summary, "plan_sha256": plan.sha256, "batch_index": batch_index, "attempt_id": capture["attempt_id"],
            "capture_manifest_sha256": trust_roots.capture_manifest_sha256, "terminal_hex": study.canonical_bytes(terminal).hex(),
            "native_fills": fills, "native_cash_path": cash_path})
        sealed = CanonicalQcExport(encoded, _TOKEN)
        _NATIVE_BUILT[id(sealed)] = (weakref.ref(sealed, lambda _, identity=id(sealed): _NATIVE_BUILT.pop(identity, None)), encoded)
        return sealed
    except native.QcExportAdapterError as exc:
        raise CanonicalQcCandidateError("REFUSED: native v2 field/provenance profile differs") from exc
