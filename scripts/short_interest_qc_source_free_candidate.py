"""Source-free SAME48 transport entrypoint proposal, not a launch permit.

candidate_source() returns compile-only text. No AlgorithmImports/clr import,
provider access, credentials, API, project, upload, compile or run occurs here.
The eventual root must register source/fixture/engine identities and a separate
data-free exception before substituting the PENDING registration constants.
"""
from __future__ import annotations

from fractions import Fraction
from decimal import Decimal
import base64
import zlib

from data.hashing import canonical_json, hash_payload
import research.short_interest_etf.native_qc_order_representation as rep
from research.short_interest_etf.latest_revised_orders import _book


def _fictional_inputs():
    ids = ('native:fixture-a', 'native:fixture-b', 'native:fixture-c')
    a, _, c = ids
    dates = ('2023-01-03', '2023-01-17', '2023-02-01')
    records = []
    for n, day in enumerate(dates):
        final, common = n == 2, list(ids if n == 0 else ids[:2])
        records.append({'settlement_date': day, 'entry_session': day,
            'entry_at': day + 'T14:30:00Z', 'exit_session': None if final else dates[n + 1],
            'exit_at': None if final else dates[n + 1] + 'T14:30:00Z',
            'status': 'final_no_successor' if final else 'ready', 'common_security_ids': common,
            'high_tail_security_ids': [common[-1]], 'low_tail_security_ids': [a], 'refusal_reasons': []})
    bars = {(sid, day): {'open': str(price)} for day, prices in (
        (dates[0], (7, 11, 13)), (dates[1], (5, 15, 8)), (dates[2], (8, 19, 8))) for sid, price in zip(ids, prices)}
    events = [
        {'event_id': 'split-a', 'security_id': a, 'kind': 'split', 'at': '2023-01-10T14:30:00Z', 'split_numerator': 3, 'split_denominator': 2},
        {'event_id': 'entitle-a', 'security_id': a, 'kind': 'dividend_entitlement', 'at': '2023-01-11T14:30:00Z', 'cash_per_share': '1', 'dividend_id': 'div-a'},
        {'event_id': 'terminal-c', 'security_id': c, 'kind': 'terminal', 'at': '2023-01-13T00:00:00Z', 'cash_per_share': '8'},
        {'event_id': 'payment-a', 'security_id': a, 'kind': 'dividend_payment', 'at': '2023-01-20T00:00:00Z', 'cash_per_share': '1', 'dividend_id': 'div-a'}]
    return ids, records, bars, events


def _r(value):
    return [value.numerator, value.denominator]


def _trade(book, source, event, order):
    quantity = Fraction(source['quantity']['numerator'], source['quantity']['denominator'])
    price = Fraction(source['raw_open_usd'])
    scheduled = rep.prepare_cell_order(book, at=source['at'], security_id=source['security_id'],
        event_id=event, order_id=order, side=source['side'], economic_quantity=quantity, economic_price=price)
    o = scheduled.transport_order
    proof = rep.FillProof(o.cell_id, o.security_id, o.event_id, o.order_id, o.side,
        o.submitted_quantity, o.fill_price, o.fee_usd, o.posted_notional_usd, o.posted_cash_delta_usd)
    after = rep.accept_fill(book.transport, o, proof)
    before_position, after_position = rep._position(book.transport, o.security_id), rep._position(after, o.security_id)
    control = rep.EngineControl(o.cell_id, rep.security_alias(o.cell_id, o.security_id), source['at'], event,
        book.transport.mirror_cash, after.mirror_cash,
        Decimal(0) if before_position is None else before_position.mirror_quantity,
        Decimal(0) if after_position is None else after_position.mirror_quantity,
        book.transport.mirror_fees_paid, after.mirror_fees_paid)
    result = rep.accept_cell_order(book, scheduled, proof, at=source['at'], control=control)
    return result, {'cell': o.cell_id, 'at': source['at'], 'security': o.security_id,
        'event': event, 'kind': o.side, 'order': order, 'quantity': _r(quantity), 'price': _r(price)}


def fabricated_manifest():
    """Frozen oracle-generated mechanical fixture, not actual input admission."""
    ids, records, bars, events = _fictional_inputs()
    oracles, books = {}, {c: rep.CellBook.new(c) for c in rep.CELL_IDS}
    for cell in rep.CELL_IDS:
        lookback, tail = cell.split('-L')[1].split('-C')
        cost, role = tail.split('-', 1)
        oracles[cell] = _book(records, bars, events, int(lookback), int(cost), role)
        if not oracles[cell]['complete']:
            raise ValueError('REFUSED: fabricated_oracle_incomplete')
    times = sorted({e['at'] for e in events} | {o['at'] for result in oracles.values() for o in result['orders']})
    cohorts = []
    for at in times:
        commands = []
        prices = {sid: Fraction(bars.get((sid, at[:10]), {'open': '1'})['open']) for sid in ids}
        for cell in rep.CELL_IDS:
            for source in (e for e in events if e['at'] == at):
                book = books[cell]
                if (rep._position(book.transport, source['security_id']) is None
                    and not any(r.security_id == source['security_id'] and r.dividend_id == source.get('dividend_id') for r in book.receivables)):
                    continue
                action = rep.CorporateAction(source['event_id'], source['security_id'], at, source['kind'],
                    None if source['kind'] == 'split' else Fraction(source['cash_per_share']), source.get('dividend_id'),
                    Fraction(3, 2) if source['kind'] == 'split' else None,
                    Fraction(5) if source['kind'] == 'split' else None)
                books[cell] = rep.accept_corporate_action(book, action, rep.prepare_corporate_control(book, action))
                commands.append({'cell': cell, 'at': at, 'security': action.security_id,
                    'event': action.event_id, 'kind': action.kind,
                    'cash': None if action.cash_per_share is None else _r(action.cash_per_share),
                    'dividend': action.dividend_id, 'split': None if action.split_ratio is None else _r(action.split_ratio),
                    'raw_price': None if action.valuation_price is None else _r(action.valuation_price)})
            for n, source in enumerate(oracles[cell]['orders']):
                if source['at'] == at:
                    books[cell], command = _trade(books[cell], source, f'trade-{n:04d}', f'order-{n:04d}')
                    commands.append(command)
                    prices[source['security_id']] = Fraction(source['raw_open_usd'])
        cohorts.append({'at': at, 'prices': {sid: _r(prices[sid]) for sid in ids}, 'commands': commands})
    expected = {}
    for cell in rep.CELL_IDS:
        oracle = oracles[cell]['financial_result']
        book = books[cell]
        if (book.transport.positions or book.receivables
            or book.transport.economic_cash != Fraction(oracle['ending_cash']['numerator'], oracle['ending_cash']['denominator'])
            or book.transport.economic_fees_paid != Fraction(oracle['total_fees']['numerator'], oracle['total_fees']['denominator'])):
            raise ValueError('REFUSED: fabricated_48book_oracle_parity')
        expected[cell] = {'cash': _r(book.transport.economic_cash), 'fees': _r(book.transport.economic_fees_paid)}
    value = {'schema': 'si-source-free-same48-transport-smoke-fixture-v1', 'fictional': True,
        'strictly_no_real_source_rows': True, 'economic_sha256': rep.ECONOMIC_SHA256,
        'transport_sha256': rep.TRANSPORT_SHA256, 'initial_cash_per_cell': 100000,
        'ids': list(ids), 'cell_ids': list(rep.CELL_IDS), 'cohorts': cohorts, 'expected': expected,
        'ranking_or_empirical_study_exercised': False, 'outcome_looks': 0, 'qc_attempts': 0}
    value['fixture_sha256'] = hash_payload(value)
    return value


def candidate_source():
    """Concrete compile-only text; Initialize refuses pending registration."""
    manifest = canonical_json(fabricated_manifest()).encode()
    compressed = base64.b64encode(zlib.compress(manifest, 9)).decode('ascii')
    return _TEMPLATE.replace('__FABRICATED_MANIFEST__', repr(compressed))


_TEMPLATE = '''"""UNREGISTERED source-free SAME48 engine mechanics candidate; never actual input."""
from AlgorithmImports import *
from System import DateTime, DateTimeKind
from decimal import Decimal
from fractions import Fraction
import base64, json, os, sys, tempfile, zlib
from data.hashing import canonical_json, hash_payload
import research.short_interest_etf.native_qc_order_representation as rep
from scripts.short_interest_compact_joint_transport import CompactLeanRuntime, CompactJointTransport, trade_instruction, action_instruction

_unpacker = zlib.decompressobj()
_raw_fixture = _unpacker.decompress(base64.b64decode(__FABRICATED_MANIFEST__, validate=True), 2 * 1024 * 1024)
if not _unpacker.eof or _unpacker.unconsumed_tail or _unpacker.unused_data:
    raise ValueError("REFUSED: bounded_single_registered_fictional_fixture")
FIXTURE = json.loads(_raw_fixture)
REGISTERED_CANDIDATE_ID = "PENDING"
REGISTERED_ENGINE_IDENTITY = "PENDING"
REGISTERED_DATA_FREE_DECISION = "PENDING"
_FILES = {}

def rational(pair):
    if type(pair) is not list or len(pair) != 2 or any(type(x) is not int for x in pair) or pair[1] <= 0:
        raise ValueError("REFUSED: fictional_rational_contract")
    return Fraction(*pair)

def clr_time(at):
    value = rep._stamp(at)
    return DateTime(value.year, value.month, value.day, value.hour, value.minute, value.second, DateTimeKind.Utc)

class FrozenFictionalPoint(PythonData):
    def GetSource(self, config, date, isLiveMode):
        if isLiveMode:
            raise ValueError("REFUSED: no_live_source_free_smoke")
        key = config.Symbol.Value, date.strftime("%Y-%m-%d")
        return SubscriptionDataSource(_FILES.get(key, _FILES["empty"]), SubscriptionTransportMedium.LocalFile)

    def Reader(self, config, line, date, isLiveMode):
        if isLiveMode:
            raise ValueError("REFUSED: no_live_source_free_smoke")
        if not line:
            return None
        row = json.loads(line)
        if set(row) != {"schema", "at", "alias", "rational_price"} or row["schema"] != "fictional-si-native-point-v1":
            raise ValueError("REFUSED: only_registered_fictional_feed")
        if row["alias"] != config.Symbol.Value or row["at"][:10] != date.strftime("%Y-%m-%d"):
            raise ValueError("REFUSED: fictional_feed_scope")
        data = FrozenFictionalPoint()
        data.Symbol = config.Symbol
        data.Time = clr_time(row["at"])
        data.EndTime = data.Time  # Genuine point event, no one-minute clock shift.
        data.Value = rep._decimal(rep._lattice(rational(row["rational_price"]), "nearest_even"))
        data["cohort_at"] = row["at"]
        data["rational_price_json"] = canonical_json(row["rational_price"])
        return data

class Same48NativeMechanicsSmoke(QCAlgorithm):
    def Initialize(self):
        # Root must replace/freeze this exact registration, not supply a Boolean
        # or runtime parameter. Metadata catalog alone grants no execution pin.
        if any(x == "PENDING" for x in (REGISTERED_CANDIDATE_ID, REGISTERED_ENGINE_IDENTITY, REGISTERED_DATA_FREE_DECISION)):
            raise ValueError("REFUSED: same48_smoke_not_prospectively_registered")
        payload = dict(FIXTURE); claimed = payload.pop("fixture_sha256")
        if hash_payload(payload) != claimed or FIXTURE["fictional"] is not True or FIXTURE["strictly_no_real_source_rows"] is not True:
            raise ValueError("REFUSED: exact_source_free_fixture_required")
        if FIXTURE["cell_ids"] != list(rep.CELL_IDS) or FIXTURE["economic_sha256"] != rep.ECONOMIC_SHA256 or FIXTURE["transport_sha256"] != rep.TRANSPORT_SHA256:
            raise ValueError("REFUSED: same48_economic_identity_changed")
        if self.LiveMode:
            raise ValueError("REFUSED: source_free_backtest_only")
        self.SetTimeZone(TimeZones.Utc)
        self.SetStartDate(2023, 1, 3); self.SetEndDate(2023, 2, 1)
        self.SetAccountCurrency("USD"); self.SetCash(4800000)
        self.SetBenchmark(lambda _when: Decimal(1))
        self._runtime = CompactLeanRuntime(self)
        self._runtime.source_free_decimal_probe()
        from QuantConnect import Globals
        import pandas, pandas_market_calendars
        # Selected public engine identity must be registered and matched by
        # root; do not enumerate other Globals/config fields or infer pin rights.
        self._runtime_identity = {"Globals.Version": str(Globals.Version),
            "QCAlgorithm_assembly_version": self._runtime.clr.GetClrType(QCAlgorithm).Assembly.GetName().Version.ToString(),
            "Python_runtime": ".".join(str(v) for v in sys.version_info[:3]),
            "pandas_version": str(pandas.__version__),
            "pandas_market_calendars_version": str(pandas_market_calendars.__version__),
            "pythonnet_version_if_exposed": str(getattr(self._runtime.clr, "__version__", "unavailable"))}
        self._hub = CompactJointTransport(self._runtime)
        self._temp = tempfile.TemporaryDirectory(prefix="si-fictional-native-mechanics-")
        empty = os.path.join(self._temp.name, "empty.jsonl")
        with open(empty, "x", encoding="utf-8"):
            pass
        _FILES["empty"] = empty
        for cell in rep.CELL_IDS:
            for native in FIXTURE["ids"]:
                alias = rep.security_alias(cell, native)
                for cohort in FIXTURE["cohorts"]:
                    key = alias, cohort["at"][:10]
                    path = os.path.join(self._temp.name, alias + "-" + key[1] + ".jsonl")
                    with open(path, "x", encoding="utf-8") as handle:
                        handle.write(canonical_json({"schema": "fictional-si-native-point-v1", "at": cohort["at"],
                            "alias": alias, "rational_price": cohort["prices"][native]}) + "\\n")
                    _FILES[key] = path
                self._runtime.install(self._hub, cell, native, FrozenFictionalPoint)
        self._cohorts = {c["at"]: c for c in FIXTURE["cohorts"]}
        self._processed = set()
        self._completed = False

    def OnData(self, data):
        at = self._runtime.now()
        if at not in self._cohorts:
            return
        if at in self._processed:
            raise ValueError("REFUSED: repeated_registered_cohort")
        cohort = self._cohorts[at]
        for alias, security in self._hub.securities.items():
            if not data.ContainsKey(security.Symbol):
                raise ValueError("REFUSED: incomplete_same_clock_custom_feed")
            point = data[security.Symbol]
            native = self._hub.identities[alias][1]
            expected = rep._decimal(rep._lattice(rational(cohort["prices"][native]), "nearest_even"))
            if point["cohort_at"] != at or json.loads(point["rational_price_json"]) != cohort["prices"][native] or self._runtime.decimal(security, "Price") != expected:
                raise ValueError("REFUSED: native_feed_price_clock_or_rational_identity")
        commands = []
        for row in cohort["commands"]:
            if row["kind"] in ("buy", "sell"):
                command = trade_instruction(row["cell"], at=at, security_id=row["security"], event_id=row["event"],
                    order_id=row["order"], side=row["kind"], quantity=rational(row["quantity"]), price=rational(row["price"]))
            else:
                action = rep.CorporateAction(row["event"], row["security"], at, row["kind"],
                    None if row["cash"] is None else rational(row["cash"]), row["dividend"],
                    None if row["split"] is None else rational(row["split"]),
                    None if row["raw_price"] is None else rational(row["raw_price"]))
                command = action_instruction(row["cell"], action)
            commands.append(command)
        agenda = tuple((cell, tuple(c for c in commands if c.cell_id == cell)) for cell in rep.CELL_IDS)
        self._hub.begin_cohort("fictional-" + at, at=at, instructions=agenda)
        for command in commands:
            if command.action is None:
                self._hub.offer_raw_open(rep.security_alias(command.cell_id, command.security_id), at=at, raw_open=command.price)
                self._hub.submit(self._hub.prepare(command))
            else:
                self._hub.corporate_instruction(command)
        self._hub.end_cohort()
        self._processed.add(at)

    def OnOrderEvent(self, event):
        self._hub.on_order_event(event)

    def OnEndOfAlgorithm(self):
        if self._processed != set(self._cohorts):
            raise ValueError("REFUSED: registered_cohorts_not_all_executed")
        family = self._hub.snapshot_family()
        for book in family:
            expected = FIXTURE["expected"][book.transport.cell_id]
            if book.transport.economic_cash != rational(expected["cash"]) or book.transport.economic_fees_paid != rational(expected["fees"]):
                raise ValueError("REFUSED: cloud_same48_oracle_parity")
        result = self._hub.finish_v1()
        if not result["software_accounting_complete"]:
            raise ValueError("REFUSED: incomplete_exact_family")
        self._completed = True
        # Only bounded source-free mechanical metadata; never enumerate Globals
        # or config/credentials/account information.
        self.Debug(canonical_json({"schema": "si-fabricated-same48-engine-proof-v1", "fixture_sha256": FIXTURE["fixture_sha256"],
            "all48_mechanics_reconciled": True, "journal_sha256": self._hub.journal_head,
            "observed_runtime_identity": self._runtime_identity, "engine_identity_independently_qualified": False,
            "actual_outcome_looks": 0, "source_admitted": False, "performance_result": False}))
'''
