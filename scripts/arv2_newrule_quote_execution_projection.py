"""Pure explicitly versioned quote-aware 09:31 execution projection.

This changes the execution witness, side-aware cash budget and strategy fee
basis; it does not claim equivalence to the old trade-price execution contract.
No file, credential, provider, QC or private-source operation exists here.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import re

from scripts import arv2_newrule_quote_diagnostic_projection as parent


admission, comparison = parent.admission, parent.comparison
canonical = comparison.canonical
SCHEMA = 'arv2-newrule-quote-aware-execution-projection-v1'
PATCHER_NAME = 'arv2_newrule_quote_execution_projection.py'
POLICY = 'arv2-newrule-quote-aware-execution-v1'
RUNTIME_NAME = parent.RUNTIME_NAME
PARENT_PROJECTION = parent.PARENT_PROJECTION
PARENT_PROFILE = parent.PARENT_PROFILE
PARENT_MANIFEST = parent.PARENT_MANIFEST
PARENT_RUNTIME_CLOUD = parent.PARENT_RUNTIME_CLOUD
PARENT_RUNTIME_RAW = parent.PARENT_RUNTIME_RAW
CONTEXT_SCHEMA = 'arv2-quote-aware-failure-context-none-v1'
FAILURE_CODES = (
    'quote_execution_quantity', 'quote_execution_clock', 'quote_execution_slice',
    'quote_execution_type', 'quote_execution_identity', 'quote_execution_period',
    'quote_execution_fill_forward', 'quote_execution_sides', 'quote_execution_spread',
    'quote_execution_cache', 'quote_execution_cache_binding', 'quote_execution_security_sides',
    'quote_execution_fee_order', 'quote_execution_fee_intent', 'quote_execution_fill_price')
FINITE = frozenset(('patcher_pin', 'source_pairs', 'source_inventory', 'parent_manifest',
    'parent_profile', 'runtime_pin', 'runtime_anchor', 'runtime_semantics', 'main_anchor',
    'main_semantics', 'source_bound', 'unchanged_sources', 'activation', 'profile_policy',
    'projection_changed', 'parent_projection', 'projection_pin', 'projection_packet',
    'projection_profile', 'failure_context', 'bytes'))
FALSE_FLAGS = {
    'backtest_created': False, 'strategy_result_accepted': False, 'family_comparable': False,
    'formal_forward_ready': False, 'point_in_time_proven': False, 'paper_or_live_ready': False}


class Refused(ValueError):
    """Finite pure source-binding refusal; no raw input or exception text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


def sha(raw):
    require(type(raw) is bytes, 'bytes')
    return hashlib.sha256(raw).hexdigest()


def policy_profile_fields():
    return {
        'execution_policy': POLICY,
        'execution_quote': 'own_current_Slice_QuoteBar_and_typed_cache;bid_sell_ask_buy;no_stale_or_one_sided_fallback',
        'quote_readiness': 'same_SID;Time0930_EndTime0931_exact60s;non_fill_forward;positive_bid_le_ask;typed_cache_and_security_sides_equal',
        'strategy_fee_basis': '10bps_times_absolute_quantity_times_frozen_intent_side_quote;exact_order_symbol_tag_signed_quantity_binding',
        'outside_intent_fee_basis': 'unchanged_security_price_for_engine_forced_delisting_orders;separately_accounted',
        'buy_cash_bound': 'floor_current_cash_divided_by_ask_times_1point001;prior_RAW_close_target_quantities_unchanged',
        'fill_price_binding': 'actual_engine_market_fill_equals_frozen_side_quote_absolute_USD_tolerance_0.0000001',
        'quote_liquidity_qualification': 'minute_quote_bar_not_independent_per_side_tick_freshness_or_size_market_impact_proof'}


def policy_record():
    return {**policy_profile_fields(), 'candidate_version_suffix': '-quote-aware-v1',
        'period_witness': 'typed_QuoteBar_EndTime_equals_Time_plus_Period;Time_EndTime_difference_60s',
        'engine_price_cache_modified': False, 'execution_clock_delayed': False,
        'trade_price_fallback': False, 'new_custom_fill_model': False,
        'fill_price_absolute_usd_tolerance': '0.0000001', 'fee_rate': '0.001',
        'preserved_rules': ['0920_snapshot', 'prior_RAW_close_sizing', 'sell_before_buy',
            'whole_long_only', 'actual_cash_holdings_reconciliation', 'no_pending_orders',
            'forced_delisting_accounting', 'daily_NAV_and_monthly_result_validation'],
        'economic_revision': True, 'diagnostic_only': False, **FALSE_FLAGS}


QUOTE_METHOD = '''def _quote_snapshot(self, security):
    now = self._now()
    require(now.time().replace(tzinfo=None) == time(9, 31), "quote_execution_clock")
    symbol = security.symbol
    try:
        bars = self._algorithm.current_slice.quote_bars
        quote = bars[symbol] if symbol in bars else None
    except Exception:
        raise targets.NewruleError("quote_execution_slice") from None
    require(quote is not None, "quote_execution_slice")
    def fields(bar):
        try:
            supported = isinstance(bar, self._quote_bar_type)
        except Exception:
            supported = False
        require(supported, "quote_execution_type")
        require(legacy._symbol_sid(bar.symbol, "quote identity") == legacy._symbol_sid(symbol, "security quote identity"), "quote_execution_identity")
        start, end = instant(bar.time), instant(bar.end_time)
        require(start.date() == now.date() and start.time().replace(tzinfo=None) == time(9, 30)
                and end == now and (end - start).total_seconds() == 60, "quote_execution_period")
        require(bar.is_fill_forward is False, "quote_execution_fill_forward")
        require(bar.bid is not None and bar.ask is not None, "quote_execution_sides")
        try:
            bid, ask = number(bar.bid.close, positive=True), number(bar.ask.close, positive=True)
        except Exception:
            raise targets.NewruleError("quote_execution_sides") from None
        require(bid <= ask, "quote_execution_spread")
        return (start, end, bid, ask)
    observed = fields(quote)
    try:
        cached = security.cache.get_data[self._quote_bar_type]()
    except Exception:
        raise targets.NewruleError("quote_execution_cache") from None
    require(cached is not None, "quote_execution_cache")
    require(fields(cached) == observed, "quote_execution_cache_binding")
    try:
        bid, ask = number(security.bid_price, positive=True), number(security.ask_price, positive=True)
    except Exception:
        raise targets.NewruleError("quote_execution_security_sides") from None
    require((bid, ask) == observed[2:], "quote_execution_security_sides")
    return (bid, ask)
'''
PRICE_METHOD = '''def _current_execution_price(self, security, quantity):
    require(type(quantity) is int and quantity != 0, "quote_execution_quantity")
    bid, ask = self._quote_snapshot(security)
    return ask if quantity > 0 else bid
'''
FEE_METHOD = '''def fee_basis(self, parameters):
    intent = self._intent
    if intent is None:
        return number(parameters.security.price, positive=True)
    order, security = parameters.order, parameters.security
    require(legacy._symbol_sid(order.symbol, "fee order symbol") == intent["qc_sid"]
            and legacy._symbol_sid(security.symbol, "fee security symbol") == intent["qc_sid"]
            and order.tag == intent["tag"] and number(order.quantity) == intent["quantity"],
            "quote_execution_fee_order")
    quote = number(intent["fee_basis_quote"], positive=True)
    require(self._now() == intent["dispatched_at"]
            and self._current_execution_price(security, intent["quantity"]) == quote,
            "quote_execution_fee_intent")
    return quote
'''
FEE_CLASS = '''class NewruleTenBpsFeeModel(FeeModel):
    def __init__(self, driver):
        self._driver = driver
    def get_order_fee(self, parameters):
        price = self._driver.fee_basis(parameters)
        quantity = abs(Decimal(str(parameters.order.absolute_quantity)))
        if not price.is_finite() or price <= 0 or not quantity.is_finite():
            raise RuntimeError("newrule fee input")
        return OrderFee(CashAmount(price * quantity * Decimal("0.001"), "USD"))
'''


def _dump(node):
    return ast.dump(node, include_attributes=False)


def _node(tree, name, kind=ast.FunctionDef):
    items = [item for item in tree.body if type(item) is kind and item.name == name]
    require(len(items) == 1, 'runtime_anchor' if kind is ast.FunctionDef else 'main_anchor')
    return items[0]


def _owner(tree):
    return _node(tree, 'NewruleComparisonDriver', ast.ClassDef)


def _driver(tree):
    return parent._driver(tree)


def _profile(axis, *, universe_count, ar_percent, source_pins):
    value = comparison.bridge.frozen.runtime.make_profile(axis,
        package_sha256=comparison.PLAIN_PACKAGE_SHA256, lineage_sha256=comparison.bridge.parent.LINEAGE,
        universe_count=universe_count, ar_percent=ar_percent, source_pins=source_pins)
    seed = {key: item for key, item in value.items() if key != 'profile_sha256'}
    seed['candidate_id'] += '-quote-aware-v1'
    seed.update(policy_profile_fields())
    return {**seed, 'profile_sha256': comparison.bridge.frozen.targets.digest(seed)}


def _runtime(raw):
    require(sha(raw) == PARENT_RUNTIME_CLOUD, 'runtime_pin')
    original = ast.parse(raw)
    tree = copy.deepcopy(original)
    owner = _owner(tree)
    names = ('__init__', '_current_execution_price', '_submit_market', 'on_after_open', 'on_order_event')
    old_methods = {name: copy.deepcopy(_node(owner, name)) for name in names}
    require(_dump(old_methods['_current_execution_price']) == _dump(ast.parse(parent.OLD_METHOD).body[0]),
        'runtime_anchor')
    require(not any(isinstance(node, ast.FunctionDef) and node.name in ('_quote_snapshot', 'fee_basis')
        for node in owner.body), 'runtime_anchor')
    constructor = _node(owner, '__init__')
    require('quote_bar_type' not in [item.arg for item in constructor.args.kwonlyargs], 'runtime_anchor')
    position = [item.arg for item in constructor.args.kwonlyargs].index('trade_bar_type') + 1
    constructor.args.kwonlyargs.insert(position, ast.arg(arg='quote_bar_type'))
    constructor.args.kw_defaults.insert(position, None)
    anchors = [node for node in constructor.body if isinstance(node, ast.Assign) and len(node.targets) == 1
        and _dump(node.targets[0]) == _dump(ast.parse('self._trade_bar_type = trade_bar_type').body[0].targets[0])]
    require(len(anchors) == 1, 'runtime_anchor')
    constructor.body.insert(constructor.body.index(anchors[0]) + 1,
        ast.parse('self._quote_bar_type = quote_bar_type').body[0])
    old_price = _node(owner, '_current_execution_price')
    owner.body[owner.body.index(old_price)] = ast.parse(PRICE_METHOD).body[0]
    for name, quantity in (('_submit_market', ast.Name(id='quantity', ctx=ast.Load())),
                           ('on_after_open', ast.Constant(value=1))):
        method = _node(owner, name)
        calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr == '_current_execution_price']
        require(len(calls) == 1 and len(calls[0].args) == 1 and not calls[0].keywords, 'runtime_anchor')
        calls[0].args.append(quantity)
    event = _node(owner, 'on_order_event')
    anchors = [node for node in event.body if isinstance(node, ast.Assign) and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Tuple)
        and [item.id for item in node.targets[0].elts] == ['quantity', 'price']]
    require(len(anchors) == 1, 'runtime_anchor')
    event.body.insert(event.body.index(anchors[0]) + 1, ast.parse(
        'require(abs(price - Decimal(intent["fee_basis_quote"])) <= Decimal("0.0000001"), "quote_execution_fill_price")').body[0])
    owner.body.extend(ast.parse(QUOTE_METHOD + '\n' + FEE_METHOD).body)
    profile_method = _node(tree, 'make_profile')
    old_profile = copy.deepcopy(profile_method)
    require(isinstance(profile_method.body[-1], ast.Return), 'runtime_anchor')
    profile_method.body[-1:-1] = ast.parse(
        'seed["candidate_id"] += "-quote-aware-v1"\nseed.update(' + repr(policy_profile_fields()) + ')').body
    ast.fix_missing_locations(tree)
    projected = (ast.unparse(tree) + '\n').encode('ascii')
    require(0 < len(projected) <= 64000, 'source_bound')
    restored = copy.deepcopy(tree)
    restored_owner = _owner(restored)
    for name, method in old_methods.items():
        changed = _node(restored_owner, name)
        restored_owner.body[restored_owner.body.index(changed)] = method
    restored_owner.body = [node for node in restored_owner.body
        if not (isinstance(node, ast.FunctionDef) and node.name in ('_quote_snapshot', 'fee_basis'))]
    changed = _node(restored, 'make_profile')
    restored.body[restored.body.index(changed)] = old_profile
    require(_dump(restored) == _dump(original), 'runtime_semantics')
    require(_dump(_node(tree, 'validate_result_statistics')) == _dump(_node(original, 'validate_result_statistics')),
        'runtime_semantics')
    compile(projected, RUNTIME_NAME, 'exec')
    return projected


def _main(raw, profile):
    original = ast.parse(raw)
    tree = copy.deepcopy(original)
    keywords = _driver(tree)
    old_profile, old_factory = copy.deepcopy(keywords['profile'].value), copy.deepcopy(keywords['fee_model_factory'].value)
    require('quote_bar_type' not in keywords, 'main_anchor')
    old_fee = _node(tree, 'NewruleTenBpsFeeModel', ast.ClassDef)
    original_fee = copy.deepcopy(old_fee)
    require(_dump(old_factory) == _dump(ast.parse('lambda: NewruleTenBpsFeeModel()', mode='eval').body), 'main_anchor')
    tree.body[tree.body.index(old_fee)] = ast.parse(FEE_CLASS).body[0]
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver']
    require(len(calls) == 1, 'main_anchor')
    calls[0].keywords.append(ast.keyword(arg='quote_bar_type', value=ast.Name(id='QuoteBar', ctx=ast.Load())))
    keywords['fee_model_factory'].value = ast.parse('lambda: NewruleTenBpsFeeModel(self._driver)', mode='eval').body
    keywords['profile'].value = ast.parse(repr(profile), mode='eval').body
    ast.fix_missing_locations(tree)
    projected = (ast.unparse(tree) + '\n').encode('ascii')
    restored = copy.deepcopy(tree)
    fee = _node(restored, 'NewruleTenBpsFeeModel', ast.ClassDef)
    restored.body[restored.body.index(fee)] = original_fee
    restored_calls = [node for node in ast.walk(restored) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver']
    restored_calls[0].keywords = [item for item in restored_calls[0].keywords if item.arg != 'quote_bar_type']
    restored_keywords = _driver(restored)
    restored_keywords['profile'].value = old_profile
    restored_keywords['fee_model_factory'].value = old_factory
    require(_dump(restored) == _dump(original), 'main_semantics')
    compile(projected, 'main.py', 'exec')
    return projected


@dataclasses.dataclass(frozen=True, slots=True)
class ExecutionProjection:
    projection_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_pairs: tuple = dataclasses.field(repr=False)

    def to_record(self):
        try:
            require(sha(self.record_bytes) == self.projection_sha256 and type(self.profile_bytes) is bytes
                and type(self.source_pairs) is tuple, 'projection_changed')
            value, profile = json.loads(self.record_bytes), json.loads(self.profile_bytes)
            require(canonical(profile) == self.profile_bytes
                and value['profile_sha256'] == profile['profile_sha256']
                and value['source_files'] == [{'project_path': name, 'byte_count': len(raw),
                    'content_sha256': sha(raw)} for name, raw in self.source_pairs], 'projection_changed')
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise Refused('projection_changed') from None
        return value


def public_specification(source_pairs, *, patcher_source_bytes, expected_patcher_sha256):
    """Freeze a public R298 proposal; this supplies no operational admission."""
    require(type(expected_patcher_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_patcher_sha256)
        and type(patcher_source_bytes) is bytes and 0 < len(patcher_source_bytes) <= 100000
        and patcher_source_bytes.isascii() and sha(patcher_source_bytes) == expected_patcher_sha256, 'patcher_pin')
    require(type(source_pairs) is tuple and len(source_pairs) == 11
        and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str
            and type(item[1]) is bytes and item[1].isascii() and 0 < len(item[1]) <= 64000
            for item in source_pairs), 'source_pairs')
    require(tuple(name for name, _ in source_pairs) == comparison.bridge.parent.FILE_NAMES, 'source_inventory')
    manifest = {'project_id': 38364439, 'projection_sha256': PARENT_PROJECTION,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)} for name, raw in source_pairs]}
    require(sha(canonical(manifest) + b'\n') == PARENT_MANIFEST, 'parent_manifest')
    files, axis = dict(source_pairs), comparison.bridge.frozen.october._sessions()
    keywords = _driver(ast.parse(files['main.py']))
    old_profile = ast.literal_eval(keywords['profile'].value)
    require(type(old_profile) is dict and old_profile.get('profile_sha256') == PARENT_PROFILE
        and old_profile.get('source_pins', {}).get(RUNTIME_NAME) == PARENT_RUNTIME_RAW, 'parent_profile')
    expected_old = comparison.bridge.frozen.runtime.make_profile(axis,
        package_sha256=comparison.PLAIN_PACKAGE_SHA256, lineage_sha256=comparison.bridge.parent.LINEAGE,
        universe_count=6, ar_percent=0, source_pins=dict(old_profile['source_pins']))
    require(canonical(expected_old) == canonical(old_profile), 'parent_profile')
    expected_activation = dict(zip(('activation_manifest_key', 'activation_manifest_sha256',
        'activation_manifest_byte_count'), comparison.PLAIN_ACTIVATION, strict=True))
    require(all(ast.literal_eval(keywords[name].value) == value for name, value in expected_activation.items()), 'activation')
    runtime = _runtime(files[RUNTIME_NAME])
    pins = {**old_profile['source_pins'], RUNTIME_NAME: sha(runtime), PATCHER_NAME: expected_patcher_sha256}
    profile = _profile(axis, universe_count=6, ar_percent=0, source_pins=pins)
    main = _main(files['main.py'], profile)
    projected = tuple((name, runtime if name == RUNTIME_NAME else main if name == 'main.py' else raw)
        for name, raw in source_pairs)
    require(all(0 < len(raw) <= 64000 for _, raw in projected)
        and sum(len(raw) for _, raw in projected) <= 448 * 1024, 'source_bound')
    unchanged = [name for name, raw in projected if raw == files[name]]
    require(len(unchanged) == 9 and comparison.bridge.INPUT_NAME in unchanged, 'unchanged_sources')
    record = {'schema': SCHEMA, 'candidate_id': 'R298', 'economic_candidate_id': profile['candidate_id'],
        'parent_projection_sha256': PARENT_PROJECTION, 'parent_profile_sha256': PARENT_PROFILE,
        'parent_source_manifest_sha256': PARENT_MANIFEST, 'profile_sha256': profile['profile_sha256'],
        'package_sha256': comparison.PLAIN_PACKAGE_SHA256, 'lineage_sha256': comparison.bridge.parent.LINEAGE,
        **expected_activation, 'patcher_sha256': expected_patcher_sha256, 'policy': policy_record(),
        'runtime_source_pin_representation': 'normalized_cloud_ascii_python',
        'economic_revision': True, 'diagnostic_only': False, 'failure_codes': list(FAILURE_CODES),
        'diagnostic_context_schema': CONTEXT_SCHEMA, 'unchanged_cloud_files': unchanged,
        'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)}
            for name, raw in projected], **FALSE_FLAGS}
    record_bytes = canonical(record)
    result = ExecutionProjection(sha(record_bytes), record_bytes, canonical(profile), projected)
    result.to_record()
    return result


def build_projection(packet, *, patcher_source_bytes, expected_patcher_sha256):
    """Require the unchanged source-bound old R298 admission packet."""
    raw, pairs = admission.validate_packet(packet)
    require(sha(raw) == PARENT_PROJECTION, 'parent_projection')
    return public_specification(pairs, patcher_source_bytes=patcher_source_bytes,
        expected_patcher_sha256=expected_patcher_sha256)


def validate_public_projection(record_bytes, source_pairs, *, expected_projection_sha256,
                               expected_profile_sha256):
    """Validate public bytes against external exact pins, never operational authority."""
    require(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
        for value in (expected_projection_sha256, expected_profile_sha256))
        and type(record_bytes) is bytes and 0 < len(record_bytes) <= 128 * 1024
        and sha(record_bytes) == expected_projection_sha256, 'projection_pin')
    try:
        require(type(source_pairs) is tuple and len(source_pairs) == 11
            and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str
                and type(item[1]) is bytes and item[1].isascii() and 0 < len(item[1]) <= 64000
                for item in source_pairs)
            and tuple(name for name, _ in source_pairs) == comparison.bridge.parent.FILE_NAMES
            and sum(len(raw) for _, raw in source_pairs) <= 448 * 1024, 'source_pairs')
        record = json.loads(record_bytes)
        expected_keys = {'schema', 'candidate_id', 'economic_candidate_id', 'parent_projection_sha256',
            'parent_profile_sha256', 'parent_source_manifest_sha256', 'profile_sha256', 'package_sha256',
            'lineage_sha256', 'activation_manifest_key', 'activation_manifest_sha256',
            'activation_manifest_byte_count', 'patcher_sha256', 'policy',
            'runtime_source_pin_representation', 'economic_revision', 'diagnostic_only', 'failure_codes',
            'diagnostic_context_schema', 'unchanged_cloud_files', 'source_files'} | set(FALSE_FLAGS)
        require(type(record) is dict and set(record) == expected_keys and canonical(record) == record_bytes
            and record['schema'] == SCHEMA and record['candidate_id'] == 'R298'
            and record['parent_projection_sha256'] == PARENT_PROJECTION
            and record['parent_profile_sha256'] == PARENT_PROFILE
            and record['parent_source_manifest_sha256'] == PARENT_MANIFEST
            and record['profile_sha256'] == expected_profile_sha256
            and record['economic_revision'] is True and record['diagnostic_only'] is False
            and canonical(record['policy']) == canonical(policy_record())
            and record['failure_codes'] == list(FAILURE_CODES)
            and record['diagnostic_context_schema'] == CONTEXT_SCHEMA
            and all(record[name] is False for name in FALSE_FLAGS)
            and record['package_sha256'] == comparison.PLAIN_PACKAGE_SHA256
            and record['lineage_sha256'] == comparison.bridge.parent.LINEAGE
            and all(record[name] == value and type(record[name]) is type(value)
                for name, value in zip(('activation_manifest_key', 'activation_manifest_sha256',
                    'activation_manifest_byte_count'), comparison.PLAIN_ACTIVATION, strict=True))
            and type(record['patcher_sha256']) is str and re.fullmatch('[0-9a-f]{64}', record['patcher_sha256'])
            and record['runtime_source_pin_representation'] == 'normalized_cloud_ascii_python'
            and record['unchanged_cloud_files'] == [name for name in comparison.bridge.parent.FILE_NAMES
                if name not in (RUNTIME_NAME, 'main.py')]
            and record['source_files'] == [{'project_path': name, 'byte_count': len(raw),
                'content_sha256': sha(raw)} for name, raw in source_pairs], 'projection_packet')
        files = dict(source_pairs)
        profile = ast.literal_eval(_driver(ast.parse(files['main.py']))['profile'].value)
        require(type(profile) is dict and profile.get('profile_sha256') == expected_profile_sha256
            and profile.get('candidate_id') == record['economic_candidate_id']
            and profile.get('source_pins', {}).get(RUNTIME_NAME) == sha(files[RUNTIME_NAME])
            and profile.get('source_pins', {}).get(PATCHER_NAME) == record['patcher_sha256'], 'projection_profile')
        require(profile['source_pins'] == {**comparison.bridge.parent.SOURCE_PINS,
            **comparison.NEW_SOURCE_PINS, RUNTIME_NAME: sha(files[RUNTIME_NAME]),
            PATCHER_NAME: record['patcher_sha256']}, 'projection_profile')
        expected = _profile(comparison.bridge.frozen.october._sessions(), universe_count=6,
            ar_percent=0, source_pins=dict(profile['source_pins']))
        require(canonical(profile) == canonical(expected), 'projection_profile')
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, RecursionError):
        raise Refused('projection_packet') from None
    return record, profile, source_pairs


def parse_failure_context(value):
    """This policy emits finite codes only, never a structured context."""
    return None


def validate_failure_context(value):
    raise Refused('failure_context')


validate_result_statistics = comparison.bridge.frozen.runtime.validate_result_statistics
