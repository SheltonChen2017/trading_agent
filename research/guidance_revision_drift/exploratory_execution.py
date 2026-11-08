"""Pure local order execution over supplied exploratory market observations.

This is an order/account adapter, not a strategy, backtest dispatcher or broker.
Fills use a completed-minute volume proxy and adverse quote-side prices. They
are modeled executions, never historical or native fill evidence. Supplied
calendars, identity, ADV and quote assumptions remain unverified.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

from data.financial_primitives import (
    decimal_text, exact_decimal_add as add, exact_decimal_multiply as mul,
    exact_decimal_subtract as sub, exact_decimal_sum as total,
)
from data.hashing import hash_bytes
from research.guidance_revision_drift.execution_contract import ExecutionContract
from research.guidance_revision_drift.historical_market import instant_ns
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, digest, identifier,
)
from research.guidance_revision_drift.research_reference import CalendarInput, PROTECTED_FROM
from research.guidance_revision_drift.simulation import execution_price

ZERO = Decimal(0)
ACTIVE = frozenset({'open', 'cancel_requested'})


class ExploratoryExecutionError(InputError):
    """Invalid supplied order/account transition; mutations are atomic."""


def _fail(code):
    raise ExploratoryExecutionError(code)


def _clock(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        _fail('explicit_aware_UTC_execution_clock_required')
    return value


def _cash(value, *, positive=False):
    if type(value) is not Decimal:
        _fail('exact_Decimal_execution_amount_required')
    amount(decimal_text(value), positive=positive, nonnegative=not positive)
    return value


def _quantity(value, *, zero=False):
    if type(value) is not int or not (0 if zero else 1) <= value <= 10**12:
        _fail('bounded_whole_share_quantity_required')
    return value


def _floor(numerator, denominator):
    an, ad = numerator.as_integer_ratio()
    bn, bd = denominator.as_integer_ratio()
    return an * bd // (ad * bn)


def _project(value):
    if type(value) is Decimal:
        return decimal_text(value)
    if type(value) in (date, datetime):
        return value.isoformat().replace('+00:00', 'Z')
    if type(value) is dict:
        return {key: _project(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_project(item) for item in value]
    return value


def _atomic(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        before = deepcopy(self._state)
        try:
            return method(self, *args, **kwargs)
        except Exception:
            self._state = before
            raise
    return wrapped


@dataclass(frozen=True, slots=True)
class LiquidityReference:
    """Decision-known trailing average DAILY DOLLAR volume, not share ADV."""

    security_id: str
    session_date: date
    known_at: datetime
    adv20_dollars: Decimal
    source_sha256: str

    def __post_init__(self):
        identifier(self.security_id)
        if type(self.session_date) is not date or self.session_date >= PROTECTED_FROM:
            _fail('unprotected_explicit_liquidity_session_required')
        _clock(self.known_at)
        _cash(self.adv20_dollars, positive=True)
        digest(self.source_sha256)


@dataclass(frozen=True, slots=True)
class LocalOrder:
    order_id: str
    security_id: str
    symbol: str
    side: str
    quantity: int
    remaining: int
    submitted_at: datetime
    session_date: date
    limit: Decimal | None
    liquidity: LiquidityReference
    status: str = 'open'
    filled_quantity: int = 0
    fees_paid: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class LocalFill:
    fill_id: str
    order_id: str
    security_id: str
    symbol: str
    sleeve: str
    side: str
    quantity: int
    price: Decimal
    notional: Decimal
    fee: Decimal
    at: datetime
    quote_timestamp_ns: int
    minute_start_ns: int
    minute_end_ns: int
    minute_source_sha256: str
    quote_source_sha256: str
    market_source_sha256: str
    unknown_quote_condition_assumed: bool
    condition_assumption_sha256: str | None
    settlement_on: date

    def __post_init__(self):
        for value in (self.fill_id, self.order_id, self.security_id, self.symbol):
            identifier(value)
        if self.sleeve not in ('strategy', 'benchmark') or self.side not in ('buy', 'sell'):
            _fail('explicit_fill_sleeve_and_side_required')
        _quantity(self.quantity)
        _cash(self.price, positive=True)
        _cash(self.notional, positive=True)
        _cash(self.fee)
        if self.notional != mul(self.price, Decimal(self.quantity)):
            _fail('fill_notional_does_not_reconcile')
        _clock(self.at)
        if (type(self.settlement_on) is not date
                or self.settlement_on < self.at.date()
                or any(type(value) is not int for value in (self.quote_timestamp_ns, self.minute_start_ns, self.minute_end_ns))
                or not self.minute_start_ns <= self.quote_timestamp_ns <= self.minute_end_ns <= instant_ns(self.at)):
            _fail('fill_observation_or_settlement_clock_mismatch')
        for value in (self.minute_source_sha256, self.quote_source_sha256, self.market_source_sha256):
            digest(value)
        if type(self.unknown_quote_condition_assumed) is not bool:
            _fail('explicit_quote_assumption_flag_required')
        if self.condition_assumption_sha256 is not None:
            digest(self.condition_assumption_sha256)
        if self.unknown_quote_condition_assumed and self.condition_assumption_sha256 is None:
            _fail('unknown_quote_condition_assumption_anchor_required')

    def projection(self):
        return _project(asdict(self) | {'modeled_execution': True,
            'capacity_source': 'completed_minute_volume_proxy',
            'source_execution_qualified': False, 'point_in_time_data': False,
            'native_execution_verified': False, 'broker_execution': False})


class LocalExecutionAdapter:
    """Explicit orders only; independent strategy or SPY cash-account sleeve.

    Caller supplies each action and observation. Cash is never borrowed from a
    second sleeve or unpaid sale. Cancellation requests may race fills until a
    separate acknowledgement. A repeated order/minute cannot consume volume
    twice. No source quote condition is rewritten by this adapter.
    """

    def __init__(self, *, calendar: CalendarInput, contract: ExecutionContract,
                 settled_cash: Decimal, at: datetime, sleeve='strategy', mode='base',
                 positions: dict[str, int] | None = None):
        if type(calendar) is not CalendarInput or type(contract) is not ExecutionContract:
            _fail('exact_supplied_calendar_and_execution_contract_required')
        if (type(sleeve) is not str or sleeve not in ('strategy', 'benchmark')
                or type(mode) is not str or mode not in ('base', 'stress')):
            _fail('explicit_sleeve_and_cost_mode_required')
        self._calendar = CalendarInput(calendar.canonical_bytes)
        self._contract = ExecutionContract(contract.canonical_bytes)
        self._mode, self._sleeve = mode, sleeve
        self._state = {'at': _clock(at), 'cash': _cash(settled_cash), 'positions': {},
                       'orders': {}, 'fills': [], 'receivables': [], 'cash_movements': [],
                       'daily_used': {}, 'minute_used': {}, 'minute_sources': {},
                       'processed': set(), 'process_calls': {}, 'liquidity': {}, 'cancel_requests': {},
                       'cancel_acks': {}, 'external_receivables': {}, 'refusals': []}
        self._session(at)
        if positions is not None:
            if type(positions) is not dict:
                _fail('explicit_initial_position_inventory_required')
            for security, quantity in positions.items():
                identifier(security)
                self._state['positions'][security] = _quantity(quantity, zero=True)

    def _session(self, at):
        _clock(at)
        sessions = [row for row in self._calendar.sessions if row.open_utc <= at <= row.close_utc]
        if len(sessions) != 1 or sessions[0].session_date >= PROTECTED_FROM:
            _fail('execution_clock_outside_supplied_unprotected_regular_session')
        return sessions[0]

    def _advance(self, at):
        session = self._session(at)
        if at < self._state['at']:
            _fail('execution_clock_cannot_rewind')
        self._state['at'] = at
        for item in self._state['receivables']:
            if (not item['released'] and item['settlement_on'] is not None
                    and item['settlement_on'] <= session.session_date):
                self._state['cash'] = add(self._state['cash'], item['amount'])
                item['released'] = True
                self._state['cash_movements'].append({'kind': 'modeled_settlement',
                    'reference': item['fill_id'], 'at': at, 'amount': item['amount']})
        return session

    def _reserved(self, except_order=None):
        return total(add(mul(row.limit, Decimal(row.remaining)),
                         max(ZERO, sub(self._contract.commission(row.quantity, self._mode), row.fees_paid)))
                     for row in self._state['orders'].values()
                     if row.side == 'buy' and row.status in ACTIVE and row.order_id != except_order)

    @_atomic
    def advance_to(self, at: datetime):
        """Release modeled due cash at the next supplied regular-session observation."""
        self._advance(at)

    @_atomic
    def register_cash_entitlement(self, *, receivable_id: str, security_id: str, kind: str,
            quantity: int, cash_per_share: Decimal, entitlement_date: date,
            payment_on: date | None, known_at: datetime, observed_at: datetime,
            source_sha256: str):
        """Retain an externally supplied dividend/terminal entitlement, even flat.

        Quantity eligibility and the supplied payment date are caller assertions,
        not verified corporate-action evidence. Missing payment dates remain
        unresolved and unspendable; no ex-date-as-payment shortcut exists.
        """
        identifier(receivable_id)
        identifier(security_id)
        digest(source_sha256)
        _quantity(quantity)
        _cash(cash_per_share, positive=True)
        if kind not in ('dividend', 'terminal_cash') or type(kind) is not str:
            _fail('explicit_external_cash_entitlement_kind_required')
        _clock(known_at)
        _clock(observed_at)
        session = self._session(observed_at)
        if (type(entitlement_date) is not date or entitlement_date > session.session_date
                or known_at > observed_at or payment_on is not None
                and (type(payment_on) is not date or payment_on < entitlement_date)):
            _fail('cash_entitlement_date_or_known_clock_mismatch')
        item = {'fill_id': receivable_id, 'security_id': security_id, 'kind': kind,
                'quantity': quantity, 'cash_per_share': cash_per_share,
                'amount': mul(Decimal(quantity), cash_per_share),
                'entitlement_date': entitlement_date, 'settlement_on': payment_on,
                'known_at': known_at, 'observed_at': observed_at, 'source_sha256': source_sha256,
                'quantity_eligibility_is_caller_asserted': True, 'released': False}
        previous = self._state['external_receivables'].get(receivable_id)
        if previous is not None:
            if previous != {key: value for key, value in item.items() if key != 'released'}:
                _fail('conflicting_cash_entitlement_replay')
            return
        if (any(row['fill_id'] == receivable_id for row in self._state['receivables'])
                or any(fill.fill_id == receivable_id for fill in self._state['fills'])):
            _fail('cash_receivable_identity_already_used')
        self._advance(observed_at)
        self._state['external_receivables'][receivable_id] = {
            key: value for key, value in item.items() if key != 'released'}
        self._state['receivables'].append(item)
        self._advance(observed_at)

    @_atomic
    def submit(self, *, order_id: str, security_id: str, symbol: str, side: str,
               quantity: int, submitted_at: datetime, liquidity: LiquidityReference,
               limit: Decimal | None = None) -> LocalOrder:
        for value in (order_id, security_id, symbol):
            identifier(value)
        if len(order_id) > 96:
            _fail('bounded_local_order_identity_required')
        if side not in ('buy', 'sell') or type(side) is not str:
            _fail('explicit_order_side_required')
        _quantity(quantity)
        if type(liquidity) is not LiquidityReference:
            _fail('exact_liquidity_reference_required')
        LiquidityReference(**asdict(liquidity))
        session = self._session(submitted_at)
        if (security_id != liquidity.security_id or session.session_date != liquidity.session_date
                or liquidity.known_at > submitted_at):
            _fail('order_liquidity_identity_date_or_known_clock_mismatch')
        if self._sleeve == 'benchmark' and symbol != 'SPY':
            _fail('benchmark_orders_must_identify_SPY')
        if limit is not None:
            _cash(limit, positive=True)
        if side == 'buy' and limit is None:
            _fail('bounded_buy_limit_required')
        proposed = LocalOrder(order_id, security_id, symbol, side, quantity, quantity,
                              submitted_at, session.session_date, limit, liquidity)
        existing = self._state['orders'].get(order_id)
        if existing is not None:
            if replace(existing, status='open', filled_quantity=0, fees_paid=ZERO,
                       remaining=existing.quantity) != proposed:
                _fail('conflicting_order_identity_replay')
            return existing
        self._advance(submitted_at)
        key = (security_id, session.session_date)
        if key in self._state['liquidity'] and self._state['liquidity'][key] != liquidity:
            _fail('daily_liquidity_reference_changed')
        if side == 'buy':
            reserve = add(mul(limit, Decimal(quantity)), self._contract.commission(quantity, self._mode))
            if reserve > sub(self._state['cash'], self._reserved()):
                _fail('buy_reservation_exceeds_available_settled_cash')
        else:
            reserved_shares = sum(row.remaining for row in self._state['orders'].values()
                if row.side == 'sell' and row.security_id == security_id and row.status in ACTIVE)
            if quantity > self._state['positions'].get(security_id, 0) - reserved_shares:
                _fail('sell_quantity_exceeds_unreserved_position')
        self._state['orders'][order_id] = proposed
        self._state['liquidity'][key] = liquidity
        return proposed

    @_atomic
    def request_cancel(self, order_id: str, at: datetime) -> LocalOrder:
        _clock(at)
        order = self._state['orders'].get(order_id)
        if order is None:
            _fail('unknown_cancel_order')
        previous = self._state['cancel_requests'].get(order_id)
        if previous is not None:
            if previous != at:
                _fail('conflicting_cancel_request_replay')
            return order
        self._advance(at)
        if order.status not in ACTIVE:
            _fail('cancel_requires_active_order')
        self._state['cancel_requests'][order_id] = at
        order = replace(order, status='cancel_requested')
        self._state['orders'][order_id] = order
        return order

    @_atomic
    def acknowledge_cancel(self, order_id: str, at: datetime) -> LocalOrder:
        _clock(at)
        if order_id not in self._state['cancel_requests']:
            _fail('cancel_ack_without_request')
        previous = self._state['cancel_acks'].get(order_id)
        if previous is not None:
            if previous != at:
                _fail('conflicting_cancel_ack_replay')
            return self._state['orders'][order_id]
        self._advance(at)
        order = self._state['orders'][order_id]
        if order.status not in ('cancel_requested', 'filled'):
            _fail('cancel_ack_order_state_mismatch')
        if order.status == 'cancel_requested':
            order = replace(order, status='cancelled')
            self._state['orders'][order_id] = order
        self._state['cancel_acks'][order_id] = at
        return order

    @_atomic
    def process(self, order_id: str, market, *, callback_at: datetime) -> LocalFill | None:
        """Apply at most one completed post-submission minute for this order.

        Latest-quote selection/condition handling belongs to the supplied market
        batch; any refusal propagates atomically. This method checks causality
        again and never falls back to an earlier favorable quote.
        """
        from research.guidance_revision_drift.exploratory_market import ExploratoryMarketBatch
        if type(market) is not ExploratoryMarketBatch:
            _fail('exact_exploratory_market_batch_required')
        _clock(callback_at)
        call_key = (order_id, instant_ns(callback_at))
        market_sha = market.sha256
        previous_call = self._state['process_calls'].get(call_key)
        if previous_call is not None:
            if previous_call != market_sha:
                _fail('conflicting_market_callback_replay')
            return None
        session = self._advance(callback_at)
        order = self._state['orders'].get(order_id)
        if order is None:
            _fail('unknown_execution_order')
        if order.status not in ACTIVE:
            return None
        if session.session_date != order.session_date:
            _fail('open_order_requires_explicit_session_reconciliation')
        if market.session != session or market.role != ('stock' if self._sleeve == 'strategy' else 'benchmark'):
            _fail('market_calendar_or_sleeve_role_mismatch')
        frame = market.subsequent_minute(submitted_at=order.submitted_at, callback_at=callback_at)
        quote, minute = frame.quote, frame.minute
        if (minute.security_id != order.security_id or minute.symbol != order.symbol
                or quote.security_id != order.security_id or quote.symbol != order.symbol):
            _fail('execution_market_identity_mismatch')
        submitted_ns, callback_ns = instant_ns(order.submitted_at), instant_ns(callback_at)
        if not (submitted_ns <= minute.start_timestamp_ns < minute.end_timestamp_ns <= callback_ns
                and submitted_ns < quote.timestamp_ns <= callback_ns
                and minute.start_timestamp_ns <= quote.timestamp_ns <= minute.end_timestamp_ns):
            _fail('strictly_subsequent_quote_and_completed_minute_required')
        key = (order.security_id, minute.start_timestamp_ns)
        source = hash_bytes(canonical_bytes(minute.projection()))
        previous = self._state['minute_sources'].get(key)
        if previous is not None and previous != source:
            _fail('conflicting_execution_minute_replay')
        self._state['minute_sources'][key] = source
        self._state['process_calls'][call_key] = market_sha
        if (order_id, key) in self._state['processed']:
            return None
        self._state['processed'].add((order_id, key))
        price = execution_price(order.side, quote.bid, quote.ask, self._mode)
        if order.limit is not None and ((order.side == 'buy' and price > order.limit)
                                       or (order.side == 'sell' and price < order.limit)):
            self._state['refusals'].append({'order_id': order_id, 'at': callback_at, 'reason': 'adverse_price_outside_limit'})
            return None
        day_key = (order.security_id, session.session_date)
        dollar_left = max(ZERO, sub(mul(order.liquidity.adv20_dollars, Decimal('0.001')),
                                       self._state['daily_used'].get(day_key, ZERO)))
        minute_left = max(0, minute.volume // 100 - self._state['minute_used'].get(key, 0))
        quantity = min(order.remaining, minute_left, _floor(dollar_left, price))
        if not quantity:
            self._state['refusals'].append({'order_id': order_id, 'at': callback_at, 'reason': 'whole_share_participation_capacity_exhausted'})
            return None
        fee_total = self._contract.commission(order.filled_quantity + quantity, self._mode)
        fee = sub(fee_total, order.fees_paid)
        notional = mul(price, Decimal(quantity))
        settlement = self._contract.settlement_on(self._calendar, session.session_date)
        fill = LocalFill(f'{order_id}_F{order.filled_quantity + quantity}', order_id,
            order.security_id, order.symbol, self._sleeve, order.side, quantity, price,
            notional, fee, callback_at, quote.timestamp_ns, minute.start_timestamp_ns,
            minute.end_timestamp_ns, minute.source_sha256, quote.source_page_sha256,
            market_sha, quote.unknown_condition_assumed,
            quote.unknown_condition_assumption_sha256, settlement)
        if (fill.fill_id in self._state['external_receivables']
                or any(row['fill_id'] == fill.fill_id for row in self._state['receivables'])
                or any(previous.fill_id == fill.fill_id for previous in self._state['fills'])):
            _fail('fill_cash_reference_identity_already_used')
        if order.side == 'buy':
            self._state['cash'] = sub(self._state['cash'], add(notional, fee))
            self._state['positions'][order.security_id] = self._state['positions'].get(order.security_id, 0) + quantity
            delta = sub(ZERO, add(notional, fee))
        else:
            shortfall = max(ZERO, sub(fee, notional))
            if shortfall > sub(self._state['cash'], self._reserved()):
                _fail('sell_fee_shortfall_exceeds_available_settled_cash')
            self._state['cash'] = sub(self._state['cash'], shortfall)
            self._state['positions'][order.security_id] -= quantity
            self._state['receivables'].append({'fill_id': fill.fill_id,
                'security_id': order.security_id, 'kind': 'sale',
                'amount': max(ZERO, sub(notional, fee)), 'settlement_on': settlement, 'released': False})
            delta = sub(ZERO, shortfall)
        order = replace(order, filled_quantity=order.filled_quantity + quantity,
                        remaining=order.remaining - quantity, fees_paid=fee_total,
                        status='filled' if order.remaining == quantity else order.status)
        self._state['orders'][order_id] = order
        if self._state['cash'] < self._reserved():
            _fail('execution_broke_settled_cash_reservations')
        self._state['cash_movements'].append({'kind': order.side + '_fill',
            'reference': fill.fill_id, 'at': callback_at, 'amount': delta})
        self._state['daily_used'][day_key] = add(self._state['daily_used'].get(day_key, ZERO), notional)
        self._state['minute_used'][key] = self._state['minute_used'].get(key, 0) + quantity
        self._state['fills'].append(fill)
        return fill

    def snapshot(self):
        """Detached accounting state; no valuation, return or parity inference."""
        state = deepcopy(self._state)
        return _project({'schema': 'gdr.exploratory-local-execution.v1', 'sleeve': self._sleeve,
            'mode': self._mode, 'at': state['at'], 'settled_cash': state['cash'],
            'reserved_cash': self._reserved(), 'positions': state['positions'],
            'orders': [asdict(row) for _, row in sorted(state['orders'].items())],
            'fills': [row.projection() for row in state['fills']], 'receivables': state['receivables'],
            'cash_movements': state['cash_movements'], 'refusals': state['refusals'],
            'execution_contract_sha256': self._contract.sha256, 'calendar_sha256': self._calendar.sha256,
            'capacity_model': 'one_percent_completed_minute_share_volume_and_0.1_percent_ADV20_dollars',
            'depth_model': 'minute_volume_proxy_not_displayed_quote_depth',
            'cash_arrival_model': 'first_supplied_regular_session_observation_on_or_after_due_date',
            'fees': 'cumulative_per_order_minimum_once_plus_unverified_additional_historical_fees',
            'source_execution_qualified': False, 'settlement_calendar_verified': False,
            'point_in_time_data': False, 'native_execution_verified': False,
            'complete_strategy_runner': False, 'matched_SPY_parity_verified': False,
            'corporate_action_entitlement_reconciliation_verified': False,
            'open_position_valuation_implemented': False,
            'unresolved_receivables': sum(not row['released'] for row in state['receivables']),
            'unknown_payment_date_receivables': sum(row['settlement_on'] is None for row in state['receivables']),
            'open_order_ids': sorted(row.order_id for row in state['orders'].values() if row.status in ACTIVE),
            'retained_position_count': sum(quantity > 0 for quantity in state['positions'].values()),
            'outcomes_evaluated': False, 'backtest_ready': False, 'qc_access_allowed': False,
            'broker_orders_allowed': False, 'real_orders_allowed': False,
            'empirical_evaluation_allowed': False})


class MatchedSpyBudgetLedger:
    """Separate actual source-fill budgets and independently supplied SPY fills.

    Residual cash and unmatched obligations remain visible. This does not
    schedule exits, fabricate a SPY fill, transfer cash between sleeves or
    certify strategy/comparator parity.
    """

    def __init__(self):
        self._entries = {}
        self._spy_fills = {}

    def register_strategy_buy(self, fill: LocalFill):
        if type(fill) is not LocalFill or fill.sleeve != 'strategy' or fill.side != 'buy':
            _fail('actual_modeled_strategy_buy_fill_required')
        LocalFill(**asdict(fill))
        existing = self._entries.get(fill.fill_id)
        if existing is not None:
            if existing['fill'] != fill:
                _fail('conflicting_source_fill_budget_replay')
            return
        self._entries[fill.fill_id] = {'fill': fill, 'budget': add(fill.notional, fill.fee),
                                      'spent': ZERO, 'spy_quantity': 0, 'spy_fill_ids': []}

    def record_spy_buy(self, source_fill_id: str, fill: LocalFill):
        if source_fill_id not in self._entries:
            _fail('unknown_matched_source_budget')
        if type(fill) is not LocalFill or fill.sleeve != 'benchmark' or fill.symbol != 'SPY' or fill.side != 'buy':
            _fail('independently_modeled_SPY_buy_fill_required')
        LocalFill(**asdict(fill))
        key = fill.fill_id
        existing = self._spy_fills.get(key)
        if existing is not None:
            if existing != (source_fill_id, fill):
                _fail('SPY_fill_reused_or_changed')
            return
        entry = self._entries[source_fill_id]
        if fill.at <= entry['fill'].at:
            _fail('matched_SPY_execution_must_follow_source_fill')
        spent = add(entry['spent'], add(fill.notional, fill.fee))
        if spent > entry['budget']:
            _fail('matched_SPY_fill_exceeds_source_cash_budget')
        entry['spent'] = spent
        entry['spy_quantity'] += fill.quantity
        entry['spy_fill_ids'].append(fill.fill_id)
        self._spy_fills[key] = (source_fill_id, fill)

    def snapshot(self):
        return _project({'schema': 'gdr.exploratory-matched-SPY-budgets.v1',
            'entries': [{'source_fill_id': key, 'source_fill': item['fill'].projection(),
                'budget': item['budget'], 'spent': item['spent'],
                'residual_cash_budget': sub(item['budget'], item['spent']),
                'spy_quantity': item['spy_quantity'], 'spy_fill_ids': list(item['spy_fill_ids']),
                'status': 'unmatched' if not item['spy_fill_ids'] else 'SPY_fills_recorded_residual_retained'}
                for key, item in sorted(self._entries.items())],
            'matched_exit_schedule_implemented': False, 'cash_transfers_between_sleeves': False,
            'matched_SPY_parity_verified': False, 'outcomes_evaluated': False,
            'backtest_ready': False, 'qc_access_allowed': False, 'broker_orders_allowed': False})
