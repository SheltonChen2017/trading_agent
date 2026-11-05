"""Pure diagnostic projection: distinguish the three existing freshness refusals.

No execution predicate, returned price, order behavior, date or economic rule
changes. A separately frozen caller must authenticate input and cloud state.
The public specification grants no source admission or operational authority.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import itertools
import json
import re

from scripts import arv2_r298_launch_admission as admission
from research.analyst_revisions_v2_qc import newrule_plain_comparison as comparison


SCHEMA = 'arv2-newrule-quote-diagnostic-projection-v1'
PATCHER_NAME = 'arv2_newrule_quote_diagnostic_projection.py'
RUNTIME_NAME = 'newrule_comparison_qc_runtime.py'
PARENT_PROJECTION = '9dde39783bcb401d1f36aeb5beb1b1983882250b0472c2afd22dca1408c2a5f5'
PARENT_PROFILE = '89d6ac9bb0f1be8bd8f307f0b00d5725620e33b402fecb7ee2ff06daecc2106e'
PARENT_MANIFEST = '8dfc3d3e16c0f6b555c565d9cac5d4e86a2fe35d037f95538e2a7dfe70a7bfa9'
PARENT_RUNTIME_RAW = '674415b3179836a613afc6f7bdea23a966db21ab67221472fc5d87b4a742049d'
PARENT_RUNTIME_CLOUD = 'd6c30a86507bebd3281fbcd51081972f7a0deca0a542547c144cbc537433befd'
FAILURE_CODES = ('execution_price_missing', 'execution_price_end_not_current', 'execution_price_fill_forward')
CACHE_CLASSES = ('trade_bar', 'quote_bar', 'other', 'missing')
BAR_STATES = ('missing', 'fresh_non_fill_forward', 'fresh_fill_forward', 'stale', 'invalid')
PRICE_STATES = ('equal', 'different', 'unknown')
CONTEXT_SCHEMA = 'arv2-quote-freshness-context-v1'
CONTEXT_FAILURE_CODES = frozenset(code + '|cache=' + cache + '|trade=' + trade
    + '|quote=' + quote + '|price_trade=' + price
    for code, cache, trade, quote, price in itertools.product(
        FAILURE_CODES, CACHE_CLASSES, BAR_STATES, BAR_STATES, PRICE_STATES))
FALSE_FLAGS = {'backtest_created': False, 'strategy_result_accepted': False,
    'formal_forward_ready': False, 'point_in_time_proven': False, 'paper_or_live_ready': False}
OLD_METHOD = '''def _current_execution_price(self, security):
    now = self._now()
    data = security.get_last_data()
    require(data is not None and instant(data.end_time) == now
            and data.is_fill_forward is False, "execution_price_not_current_minute")
    return number(security.price, positive=True)
'''
NEW_METHOD = '''def _current_execution_price(self, security):
    now = self._now()
    data = security.get_last_data()
    if data is None:
        require(False, self._execution_price_context("execution_price_missing", security, data, now))
    if instant(data.end_time) != now:
        require(False, self._execution_price_context("execution_price_end_not_current", security, data, now))
    if data.is_fill_forward is not False:
        require(False, self._execution_price_context("execution_price_fill_forward", security, data, now))
    return number(security.price, positive=True)
'''
CONTEXT_METHOD = '''def _execution_price_context(self, code, security, data, now):
    cache = "missing" if data is None else "other"
    try:
        kind = type(data).__name__
        if kind == "TradeBar":
            cache = "trade_bar"
        elif kind == "QuoteBar":
            cache = "quote_bar"
    except Exception:
        pass
    def classify(bar):
        if bar is None:
            return "missing"
        try:
            if instant(bar.end_time) != now:
                return "stale"
            if bar.is_fill_forward is False:
                return "fresh_non_fill_forward"
            if bar.is_fill_forward is True:
                return "fresh_fill_forward"
        except Exception:
            pass
        return "invalid"
    trade, quote, price = "invalid", "invalid", "unknown"
    trade_bar = None
    try:
        symbol = security.symbol
        bars = self._algorithm.current_slice.bars
        trade_bar = bars[symbol] if symbol in bars else None
        trade = classify(trade_bar)
    except Exception:
        pass
    try:
        symbol = security.symbol
        bars = self._algorithm.current_slice.quote_bars
        quote = classify(bars[symbol] if symbol in bars else None)
    except Exception:
        pass
    if trade_bar is not None:
        try:
            price = "equal" if number(security.price, positive=True) == number(trade_bar.close, positive=True) else "different"
        except Exception:
            pass
    return code + "|cache=" + cache + "|trade=" + trade + "|quote=" + quote + "|price_trade=" + price
'''


class Refused(ValueError):
    """Finite source projection refusal; no private input or exception rendering."""


def require(value, code):
    if not value:
        raise Refused(code)


canonical = comparison.canonical


def sha(raw):
    require(type(raw) is bytes, 'bytes')
    return hashlib.sha256(raw).hexdigest()


def _dump(node):
    return ast.dump(node, include_attributes=False)


def _method(tree):
    classes = [node for node in tree.body if type(node) is ast.ClassDef and node.name == 'NewruleComparisonDriver']
    require(len(classes) == 1, 'runtime_anchor')
    methods = [node for node in classes[0].body if type(node) is ast.FunctionDef and node.name == '_current_execution_price']
    require(len(methods) == 1, 'runtime_anchor')
    return classes[0], methods[0]


def _driver(tree):
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver']
    require(len(calls) == 1, 'main_anchor')
    keywords = {item.arg: item for item in calls[0].keywords}
    require(len(keywords) == len(calls[0].keywords)
        and comparison.bridge.MAIN_KEYWORDS <= set(keywords), 'main_anchor')
    return keywords


def _runtime(raw):
    require(sha(raw) == PARENT_RUNTIME_CLOUD, 'runtime_pin')
    tree = ast.parse(raw.decode('ascii'))
    owner, previous = _method(tree)
    require(_dump(previous) == _dump(ast.parse(OLD_METHOD).body[0]), 'runtime_anchor')
    replacement = ast.parse(NEW_METHOD).body[0]
    owner.body[owner.body.index(previous)] = replacement
    require(not any(isinstance(node, ast.FunctionDef) and node.name == '_execution_price_context'
        for node in owner.body), 'runtime_anchor')
    owner.body.append(ast.parse(CONTEXT_METHOD).body[0])
    ast.fix_missing_locations(tree)
    projected = (ast.unparse(tree) + '\n').encode('ascii')
    require(0 < len(projected) <= 64000, 'source_bound')
    # Restore the sole method and require the complete original tree, including
    # every other call, class member and literal, to be unchanged.
    restored = copy.deepcopy(tree)
    restored_owner, patched = _method(restored)
    restored_owner.body[restored_owner.body.index(patched)] = ast.parse(OLD_METHOD).body[0]
    restored_owner.body = [node for node in restored_owner.body
        if not (isinstance(node, ast.FunctionDef) and node.name == '_execution_price_context')]
    require(_dump(restored) == _dump(ast.parse(raw)), 'runtime_semantics')
    compile(projected, RUNTIME_NAME, 'exec')
    return projected


@dataclasses.dataclass(frozen=True, slots=True)
class DiagnosticProjection:
    projection_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_pairs: tuple = dataclasses.field(repr=False)

    def to_record(self):
        try:
            require(sha(self.record_bytes) == self.projection_sha256
                and type(self.profile_bytes) is bytes and type(self.source_pairs) is tuple, 'projection_changed')
            value, profile = json.loads(self.record_bytes), json.loads(self.profile_bytes)
            require(canonical(profile) == self.profile_bytes
                and value['profile_sha256'] == profile['profile_sha256']
                and value['source_files'] == [{'project_path': name, 'byte_count': len(raw),
                    'content_sha256': sha(raw)} for name, raw in self.source_pairs], 'projection_changed')
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise Refused('projection_changed') from None
        return value


def public_specification(source_pairs, *, patcher_source_bytes, expected_patcher_sha256):
    """Bind public source bytes to A11's fixed manifest, without private reads."""
    require(type(expected_patcher_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_patcher_sha256)
        and type(patcher_source_bytes) is bytes and 0 < len(patcher_source_bytes) <= 100000
        and patcher_source_bytes.isascii() and sha(patcher_source_bytes) == expected_patcher_sha256,
        'patcher_pin')
    require(type(source_pairs) is tuple and len(source_pairs) == 11
        and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str
            and type(item[1]) is bytes and item[1].isascii() and 0 < len(item[1]) <= 64000
            for item in source_pairs), 'source_pairs')
    require(tuple(name for name, _ in source_pairs) == comparison.bridge.parent.FILE_NAMES, 'source_inventory')
    manifest = {'project_id': 38364439, 'projection_sha256': PARENT_PROJECTION,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)} for name, raw in source_pairs]}
    require(sha(canonical(manifest) + b'\n') == PARENT_MANIFEST, 'parent_manifest')
    files = dict(source_pairs)
    tree = ast.parse(files['main.py'])
    keywords = _driver(tree)
    original_profile = ast.literal_eval(keywords['profile'].value)
    require(type(original_profile) is dict and original_profile.get('profile_sha256') == PARENT_PROFILE
        and original_profile.get('source_pins', {}).get(RUNTIME_NAME) == PARENT_RUNTIME_RAW,
        'parent_profile')
    profile = comparison.bridge.frozen.runtime.make_profile(comparison.bridge.frozen.october._sessions(),
        package_sha256=comparison.PLAIN_PACKAGE_SHA256, lineage_sha256=comparison.bridge.parent.LINEAGE,
        universe_count=6, ar_percent=0, source_pins=dict(original_profile['source_pins']))
    require(canonical(profile) == canonical(original_profile), 'parent_profile')
    runtime = _runtime(files[RUNTIME_NAME])
    next_pins = {**original_profile['source_pins'], RUNTIME_NAME: sha(runtime), PATCHER_NAME: expected_patcher_sha256}
    profile = comparison.bridge.frozen.runtime.make_profile(comparison.bridge.frozen.october._sessions(),
        package_sha256=comparison.PLAIN_PACKAGE_SHA256, lineage_sha256=comparison.bridge.parent.LINEAGE,
        universe_count=6, ar_percent=0, source_pins=next_pins)
    require(comparison.bridge._economic_profile(profile) == comparison.bridge._economic_profile(original_profile),
        'economic_profile')
    expected_activation = dict(zip(('activation_manifest_key', 'activation_manifest_sha256',
        'activation_manifest_byte_count'), comparison.PLAIN_ACTIVATION, strict=True))
    require(all(ast.literal_eval(keywords[name].value) == value for name, value in expected_activation.items()),
        'activation')
    keywords['profile'].value = ast.parse(repr(profile), mode='eval').body
    ast.fix_missing_locations(tree)
    main = (ast.unparse(tree) + '\n').encode('ascii')
    require(comparison.bridge._main_shape(main) == comparison.bridge._main_shape(files['main.py']), 'main_semantics')
    compile(main, 'main.py', 'exec')
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
        **expected_activation, 'patcher_sha256': expected_patcher_sha256,
        'runtime_source_pin_representation': 'normalized_cloud_ascii_python',
        'diagnostic_only': True, 'failure_codes': list(FAILURE_CODES),
        'diagnostic_context_schema': CONTEXT_SCHEMA,
        'diagnostic_context_enums': {'cache_class': list(CACHE_CLASSES), 'trade_bar': list(BAR_STATES),
            'quote_bar': list(BAR_STATES), 'price_trade': list(PRICE_STATES)},
        'unchanged_cloud_files': unchanged,
        'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)}
            for name, raw in projected], **FALSE_FLAGS}
    raw = canonical(record)
    result = DiagnosticProjection(sha(raw), raw, canonical(profile), projected)
    result.to_record()
    return result


def build_projection(packet, *, patcher_source_bytes, expected_patcher_sha256):
    """Require the source-bound native admission packet before projection."""
    raw, pairs = admission.validate_packet(packet)
    require(sha(raw) == PARENT_PROJECTION, 'parent_projection')
    return public_specification(pairs, patcher_source_bytes=patcher_source_bytes,
        expected_patcher_sha256=expected_patcher_sha256)


def validate_public_projection(record_bytes, source_pairs, *, expected_projection_sha256,
                               expected_profile_sha256):
    """Pure receiver validation against separately frozen literal output pins."""
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
        require(type(record) is dict and canonical(record) == record_bytes
            and record.get('schema') == SCHEMA and record.get('candidate_id') == 'R298'
            and record.get('parent_projection_sha256') == PARENT_PROJECTION
            and record.get('parent_profile_sha256') == PARENT_PROFILE
            and record.get('parent_source_manifest_sha256') == PARENT_MANIFEST
            and record.get('profile_sha256') == expected_profile_sha256
            and record.get('diagnostic_only') is True
            and record.get('failure_codes') == list(FAILURE_CODES)
            and record.get('diagnostic_context_schema') == CONTEXT_SCHEMA
            and record.get('diagnostic_context_enums') == {'cache_class': list(CACHE_CLASSES),
                'trade_bar': list(BAR_STATES), 'quote_bar': list(BAR_STATES), 'price_trade': list(PRICE_STATES)}
            and all(record.get(name) is False for name in FALSE_FLAGS)
            and record.get('source_files') == [{'project_path': name, 'byte_count': len(raw),
                'content_sha256': sha(raw)} for name, raw in source_pairs], 'projection_packet')
        files = dict(source_pairs)
        profile = ast.literal_eval(_driver(ast.parse(files['main.py']))['profile'].value)
        require(type(profile) is dict and profile.get('profile_sha256') == expected_profile_sha256,
            'projection_profile')
        seed = dict(profile)
        seed.pop('profile_sha256')
        require(comparison.bridge.frozen.targets.digest(seed) == expected_profile_sha256
            and profile['source_pins'][RUNTIME_NAME] == sha(files[RUNTIME_NAME])
            and profile['source_pins'][PATCHER_NAME] == record['patcher_sha256'], 'projection_profile')
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, RecursionError):
        raise Refused('projection_packet') from None
    return record, profile, source_pairs


def validate_failure_context(value):
    """Validate only closed metadata; no identity, timestamp or market value."""
    require(type(value) is dict and set(value) == {'schema', 'predicate', 'cache_class',
        'trade_bar', 'quote_bar', 'price_trade'} and value.get('schema') == CONTEXT_SCHEMA
        and all(type(item) is str for item in value.values())
        and value['predicate'] in FAILURE_CODES and value['cache_class'] in CACHE_CLASSES
        and value['trade_bar'] in BAR_STATES and value['quote_bar'] in BAR_STATES
        and value['price_trade'] in PRICE_STATES, 'failure_context')
    return dict(value)


def parse_failure_context(value):
    """Read one unambiguous finite code from a bounded ASCII error line."""
    if type(value) is not str or not 0 < len(value) <= 4096 or not value.isascii():
        return None
    pattern = (r'(?<![A-Za-z0-9_])(' + '|'.join(FAILURE_CODES) + r')\|cache=('
        + '|'.join(CACHE_CLASSES) + r')\|trade=(' + '|'.join(BAR_STATES) + r')\|quote=('
        + '|'.join(BAR_STATES) + r')\|price_trade=(' + '|'.join(PRICE_STATES)
        + r')(?![A-Za-z0-9_|=])')
    matches = list(re.finditer(pattern, value))
    if len(matches) != 1:
        return None
    predicate, cache, trade, quote, price = matches[0].groups()
    return validate_failure_context({'schema': CONTEXT_SCHEMA, 'predicate': predicate,
        'cache_class': cache, 'trade_bar': trade, 'quote_bar': quote, 'price_trade': price})
