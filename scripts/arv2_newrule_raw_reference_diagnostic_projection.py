"""Pure failure-only RAW-reference diagnostic; never a sizing-price repair.

The quote-aware runtime stays byte-identical. Only its inherited reference
failure branch receives a bounded observation/probe and always raises. The
probe cannot supply sizing inputs, a fallback, a result cell or source truth.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import json
import re

from scripts import arv2_newrule_quote_execution_projection as quote


admission, comparison = quote.admission, quote.comparison
canonical, sha = quote.canonical, quote.sha
SCHEMA = 'arv2-newrule-raw-reference-diagnostic-projection-v1'
PATCHER_NAME = 'arv2_newrule_raw_reference_diagnostic_projection.py'
LEGACY_NAME = 'newrule_legacy_primitives.py'
PARENT_PROJECTION = '3735a7764f658ba867edb338615666844ceb8f81d7aebdc36d8b7b6495e67779'
PARENT_PROFILE = 'cf6e4063796cd297b28aaa1620056a2a86e8bfe7f65a194de1e531f97dc64569'
PARENT_MANIFEST = 'b4ed1a5f3cb5da08bed86589b1d06fa8fa620b90a809b264b78661a723b3e907'
PARENT_RUNTIME = 'c7b829020ac20704ec6f813997ebef396ed2069b8ad60c77bf3dc84cd67e2814'
PARENT_LEGACY = 'ed32742c02623c03364d5f235b65cf8c0bb921c0e0d6febbb435c48c05092e16'
FAILURE_CODES = ('raw_reference_census_incomplete',)
CONTEXT_SCHEMA = 'arv2-raw-reference-census-context-v1'
HOLDING_BUCKETS = ('held', 'unheld_target', 'unknown')
KIND_BUCKETS = ('own_etf', 'stock', 'unknown')
DATE_BUCKETS = ('on_or_before_reference', 'after_reference_through_decision', 'after_decision', 'unknown')
OFFSET_BUCKETS = ('before_reference', 'exact_reference', 'after_reference_before_cutoff')
PROBE_STATUSES = ('not_started', 'skipped_limit', 'unknown_clock', 'call_failed', 'read_failed',
    'bound_exceeded', 'identity_invalid', 'time_invalid', 'fill_forward_invalid', 'complete')
ORIGINAL_FAILURE = ('six-universe RAW reference price census is incomplete; '
    'no stale-price fallback is permitted')
FINITE = frozenset(('patcher_pin', 'source_pairs', 'source_inventory', 'parent_manifest',
    'parent_profile', 'legacy_pin', 'legacy_anchor', 'legacy_semantics', 'main_semantics',
    'projection_changed', 'parent_projection', 'projection_pin', 'projection_packet',
    'projection_profile', 'failure_context', 'source_bound', 'unchanged_sources'))
FALSE_FLAGS = {'backtest_created': False, 'strategy_result_accepted': False, 'family_comparable': False,
    'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}


class Refused(ValueError):
    """Finite pure projection refusal, never input or exception text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


def context_record(requested, returned):
    """Fresh closed fixture/base context; does not assert that a probe ran."""
    require(type(requested) is int and type(returned) is int
        and 1 <= requested <= 256 and 0 <= returned < requested, 'failure_context')
    missing = requested - returned
    return {'schema': CONTEXT_SCHEMA, 'predicate': FAILURE_CODES[0],
        'requested': requested, 'returned': returned, 'missing': missing,
        'missing_holdings': {'held': 0, 'unheld_target': 0, 'unknown': missing},
        'missing_kind': {'own_etf': 0, 'stock': 0, 'unknown': missing},
        'missing_sid_date': {'on_or_before_reference': 0, 'after_reference_through_decision': 0,
            'after_decision': 0, 'unknown': missing},
        'probe': {'status': 'not_started', 'requested': 0, 'batches': 0, 'items': 0,
            'identity_valid': None, 'request_invoked': False,
            'rows_by_offset': {'before_reference': 0, 'exact_reference': 0, 'after_reference_before_cutoff': 0}},
        'cause_authenticated': False, 'probe_prices_used': False, 'sizing_repaired': False,
        'diagnostic_only': True}


def policy_record():
    return {'schema': 'arv2-raw-reference-failure-probe-v1', 'diagnostic_only': True,
        'primary_history_call_unchanged': True, 'always_refuse_after_incomplete_census': True,
        'probe_only_missing_maximum': 16, 'probe_maximum_batches': 8, 'probe_maximum_items': 128,
        'probe_bounds_use_one_unprocessed_sentinel': True,
        'probe_start': 'reference_midnight_minus_five_calendar_days',
        'probe_end': 'min_reference_midnight_plus_two_calendar_days_current_decision_0920',
        'probe_resolution': 'typed_TradeBar_DAILY', 'probe_normalization': 'RAW',
        'probe_fill_forward': False, 'probe_extended_market_hours': False,
        'probe_close_prices_inspected': False, 'probe_prices_used': False,
        'sid_date_is_independent_listing_proof': False, 'sizing_repaired': False,
        'quote_runtime_unchanged': True, **FALSE_FLAGS}


FAILURE_BODY = '''missing = tuple(identity for identity in security_ids if identity not in result)
context = {"schema": "arv2-raw-reference-census-context-v1", "predicate": "raw_reference_census_incomplete",
    "requested": len(security_ids), "returned": len(result), "missing": len(missing),
    "missing_holdings": {"held": 0, "unheld_target": 0, "unknown": 0},
    "missing_kind": {"own_etf": 0, "stock": 0, "unknown": 0},
    "missing_sid_date": {"on_or_before_reference": 0, "after_reference_through_decision": 0, "after_decision": 0, "unknown": 0},
    "probe": {"status": "not_started", "requested": 0, "batches": 0, "items": 0, "identity_valid": None,
        "request_invoked": False, "rows_by_offset": {"before_reference": 0, "exact_reference": 0, "after_reference_before_cutoff": 0}},
    "cause_authenticated": False, "probe_prices_used": False, "sizing_repaired": False, "diagnostic_only": True}
pairs = tuple((identity, symbol) for identity, symbol in zip(security_ids, symbols, strict=True) if identity in missing)
try:
    holdings = self._current_holding_census()
except Exception:
    holdings = None
try:
    decision = self._now().replace(tzinfo=None)
    if decision.time() != datetime.strptime("09:20", "%H:%M").time():
        decision = None
except Exception:
    decision = None
reference = datetime.strptime(session, "%Y-%m-%d")
for identity, symbol in pairs:
    context["missing_holdings"]["unknown" if holdings is None else "held" if identity in holdings else "unheld_target"] += 1
    try:
        sid = _symbol_sid(symbol, "reference diagnostic identity")
        kind = "own_etf" if sid in self._security_by_etf_sid else "stock" if sid in self._security_by_sid else "unknown"
    except Exception:
        kind = "unknown"
    context["missing_kind"][kind] += 1
    date_kind = "unknown"
    try:
        origin = symbol.id.date
        if isinstance(origin, datetime):
            origin = origin.replace(tzinfo=None)
            if origin.date() <= reference.date():
                date_kind = "on_or_before_reference"
            elif decision is not None:
                date_kind = "after_reference_through_decision" if origin.date() <= decision.date() else "after_decision"
    except Exception:
        pass
    context["missing_sid_date"][date_kind] += 1
def probe_missing():
    probe = context["probe"]
    if len(pairs) > 16:
        probe["status"] = "skipped_limit"
        return
    if decision is None or decision < reference + timedelta(days=1):
        probe["status"] = "unknown_clock"
        return
    start = reference - timedelta(days=5)
    end = min(reference + timedelta(days=2), decision)
    wanted = {_symbol_sid(symbol, "reference diagnostic probe key") for _, symbol in pairs}
    try:
        probe_symbols = [symbol for _, symbol in pairs]
        typed_history = self._algorithm.history[self._trade_bar_type]
        resolution, normalization = self._daily_resolution, self._raw_normalization
        if not callable(typed_history):
            probe["status"] = "read_failed"
            return
    except Exception:
        probe["status"] = "read_failed"
        return
    probe["requested"] = len(pairs)
    probe["request_invoked"] = True
    try:
        response = typed_history(probe_symbols, start, end, resolution,
            fill_forward=False, extended_market_hours=False, data_normalization_mode=normalization)
    except Exception:
        probe["status"] = "call_failed"
        return
    try:
        iterator = iter(response)
        for index in range(9):
            try:
                batch = next(iterator)
            except StopIteration:
                probe["status"] = "complete"
                probe["identity_valid"] = True
                return
            if index == 8:
                probe["status"] = "bound_exceeded"
                return
            probe["batches"] += 1
            batch_time = batch.time
            if not isinstance(batch_time, datetime):
                probe["status"] = "time_invalid"
                return
            batch_time = batch_time.replace(tzinfo=None)
            if not start < batch_time <= end:
                probe["status"] = "time_invalid"
                return
            items = iter(batch.items())
            for unused in range(129):
                try:
                    item = next(items)
                except StopIteration:
                    break
                if probe["items"] == 128:
                    probe["status"] = "bound_exceeded"
                    return
                symbol, bar = item
                probe["items"] += 1
                sid = _symbol_sid(symbol, "reference diagnostic probe result")
                if sid not in wanted or _symbol_sid(bar.symbol, "reference diagnostic probe payload") != sid:
                    probe["status"] = "identity_invalid"
                    probe["identity_valid"] = False
                    return
                if bar.is_fill_forward is not False:
                    probe["status"] = "fill_forward_invalid"
                    return
                left, right = bar.time, bar.end_time
                if not isinstance(left, datetime) or not isinstance(right, datetime):
                    probe["status"] = "time_invalid"
                    return
                left, right = left.replace(tzinfo=None), right.replace(tzinfo=None)
                if not start <= left < right <= end or right > decision or batch_time != right:
                    probe["status"] = "time_invalid"
                    return
                bucket = "before_reference" if left.date() < reference.date() else "exact_reference" if left.date() == reference.date() else "after_reference_before_cutoff"
                probe["rows_by_offset"][bucket] += 1
        probe["status"] = "bound_exceeded"
    except Exception:
        probe["status"] = "read_failed"
try:
    probe_missing()
except Exception:
    context["probe"]["status"] = "read_failed"
_error("six-universe RAW reference price census is incomplete; no stale-price fallback is permitted"
    + "\\nraw_reference_census_incomplete|context=" + json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
'''


def _dump(node):
    return ast.dump(node, include_attributes=False)


def _legacy_method(tree):
    owner = quote._node(tree, 'AcceptedRiskSixUniverseOrderQcDriver', ast.ClassDef)
    return quote._node(owner, '_reference_prices')


def _legacy(raw):
    require(sha(raw) == PARENT_LEGACY, 'legacy_pin')
    original = ast.parse(raw)
    tree = copy.deepcopy(original)
    method = _legacy_method(tree)
    branches = [node for node in method.body if isinstance(node, ast.If)
        and _dump(node.test) == _dump(ast.parse('set(result) != set(security_ids)', mode='eval').body)]
    require(len(branches) == 1 and not branches[0].orelse and len(branches[0].body) == 1
        and isinstance(branches[0].body[0], ast.Expr)
        and isinstance(branches[0].body[0].value, ast.Call)
        and isinstance(branches[0].body[0].value.func, ast.Name)
        and branches[0].body[0].value.func.id == '_error'
        and len(branches[0].body[0].value.args) == 1
        and ast.literal_eval(branches[0].body[0].value.args[0]) == ORIGINAL_FAILURE, 'legacy_anchor')
    old_body = copy.deepcopy(branches[0].body)
    branches[0].body = ast.parse(FAILURE_BODY).body
    ast.fix_missing_locations(tree)
    raw_next = (ast.unparse(tree) + '\n').encode('ascii')
    require(0 < len(raw_next) <= 64000, 'source_bound')
    restored = copy.deepcopy(tree)
    branch, = [node for node in _legacy_method(restored).body if isinstance(node, ast.If)
        and _dump(node.test) == _dump(ast.parse('set(result) != set(security_ids)', mode='eval').body)]
    branch.body = old_body
    require(_dump(restored) == _dump(original), 'legacy_semantics')
    compile(raw_next, LEGACY_NAME, 'exec')
    return raw_next


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
            record, profile = json.loads(self.record_bytes), json.loads(self.profile_bytes)
            require(canonical(profile) == self.profile_bytes and record['profile_sha256'] == profile['profile_sha256']
                and record['source_files'] == [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)}
                    for name, raw in self.source_pairs], 'projection_changed')
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise Refused('projection_changed') from None
        return record


def public_specification(source_pairs, *, patcher_source_bytes, expected_patcher_sha256):
    """Bind the held quote-aware source manifest without private reads."""
    require(type(expected_patcher_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_patcher_sha256)
        and type(patcher_source_bytes) is bytes and 0 < len(patcher_source_bytes) <= 100000
        and patcher_source_bytes.isascii() and sha(patcher_source_bytes) == expected_patcher_sha256, 'patcher_pin')
    require(type(source_pairs) is tuple and len(source_pairs) == 11
        and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str and type(item[1]) is bytes
            and item[1].isascii() and 0 < len(item[1]) <= 64000 for item in source_pairs), 'source_pairs')
    require(tuple(name for name, _ in source_pairs) == comparison.bridge.parent.FILE_NAMES, 'source_inventory')
    manifest = {'project_id': 38364439, 'projection_sha256': PARENT_PROJECTION,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)} for name, raw in source_pairs]}
    require(sha(canonical(manifest) + b'\n') == PARENT_MANIFEST, 'parent_manifest')
    files = dict(source_pairs)
    keywords = quote._driver(ast.parse(files['main.py']))
    profile = ast.literal_eval(keywords['profile'].value)
    require(type(profile) is dict and profile.get('profile_sha256') == PARENT_PROFILE
        and sha(files[quote.RUNTIME_NAME]) == PARENT_RUNTIME, 'parent_profile')
    expected = quote._profile(comparison.bridge.frozen.october._sessions(), universe_count=6,
        ar_percent=0, source_pins=dict(profile['source_pins']))
    require(canonical(profile) == canonical(expected), 'parent_profile')
    legacy = _legacy(files[LEGACY_NAME])
    next_pins = {**profile['source_pins'], LEGACY_NAME: sha(legacy), PATCHER_NAME: expected_patcher_sha256}
    profile = quote._profile(comparison.bridge.frozen.october._sessions(), universe_count=6,
        ar_percent=0, source_pins=next_pins)
    tree = ast.parse(files['main.py'])
    old_value = copy.deepcopy(quote._driver(tree)['profile'].value)
    quote._driver(tree)['profile'].value = ast.parse(repr(profile), mode='eval').body
    ast.fix_missing_locations(tree)
    main = (ast.unparse(tree) + '\n').encode('ascii')
    restored = copy.deepcopy(tree)
    quote._driver(restored)['profile'].value = old_value
    require(_dump(restored) == _dump(ast.parse(files['main.py'])), 'main_semantics')
    compile(main, 'main.py', 'exec')
    projected = tuple((name, legacy if name == LEGACY_NAME else main if name == 'main.py' else raw)
        for name, raw in source_pairs)
    require(all(0 < len(raw) <= 64000 for _, raw in projected)
        and sum(len(raw) for _, raw in projected) <= 448 * 1024, 'source_bound')
    unchanged = [name for name, raw in projected if raw == files[name]]
    require(len(unchanged) == 9 and quote.RUNTIME_NAME in unchanged
        and comparison.bridge.INPUT_NAME in unchanged, 'unchanged_sources')
    record = {'schema': SCHEMA, 'candidate_id': 'R298', 'economic_candidate_id': profile['candidate_id'],
        'parent_projection_sha256': PARENT_PROJECTION, 'parent_profile_sha256': PARENT_PROFILE,
        'parent_source_manifest_sha256': PARENT_MANIFEST, 'profile_sha256': profile['profile_sha256'],
        'package_sha256': comparison.PLAIN_PACKAGE_SHA256, 'lineage_sha256': comparison.bridge.parent.LINEAGE,
        'activation_manifest_key': comparison.PLAIN_ACTIVATION[0],
        'activation_manifest_sha256': comparison.PLAIN_ACTIVATION[1],
        'activation_manifest_byte_count': comparison.PLAIN_ACTIVATION[2],
        'patcher_sha256': expected_patcher_sha256, 'diagnostic_only': True, 'policy': policy_record(),
        'failure_codes': list(FAILURE_CODES), 'diagnostic_context_schema': CONTEXT_SCHEMA,
        'unchanged_cloud_files': unchanged, 'quote_runtime_sha256': PARENT_RUNTIME,
        'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)}
            for name, raw in projected], **FALSE_FLAGS}
    record_bytes = canonical(record)
    result = DiagnosticProjection(sha(record_bytes), record_bytes, canonical(profile), projected)
    result.to_record()
    return result


def build_projection(packet, *, patcher_source_bytes, expected_patcher_sha256, quote_patcher_source_bytes):
    old = quote.build_projection(packet, patcher_source_bytes=quote_patcher_source_bytes,
        expected_patcher_sha256='ebc6d921c5dbaa5e9bc83379ab45c167780fb87db8441dbd9d618b3efcb1715f')
    require(old.projection_sha256 == PARENT_PROJECTION, 'parent_projection')
    return public_specification(old.source_pairs, patcher_source_bytes=patcher_source_bytes,
        expected_patcher_sha256=expected_patcher_sha256)
def validate_failure_context(value):
    expected = set(context_record(1, 0))
    require(type(value) is dict and all(type(key) is str for key in value) and set(value) == expected
        and type(value['schema']) is str and value['schema'] == CONTEXT_SCHEMA
        and type(value['predicate']) is str and value['predicate'] == FAILURE_CODES[0]
        and value['cause_authenticated'] is False
        and value['probe_prices_used'] is False and value['sizing_repaired'] is False
        and value['diagnostic_only'] is True, 'failure_context')
    def integer(item, maximum):
        require(type(item) is int and 0 <= item <= maximum, 'failure_context')
    for key in ('requested', 'returned', 'missing'):
        integer(value[key], 256)
    require(value['requested'] >= 1 and value['missing'] >= 1
        and value['returned'] + value['missing'] == value['requested'], 'failure_context')
    for key, names in (('missing_holdings', HOLDING_BUCKETS), ('missing_kind', KIND_BUCKETS),
                       ('missing_sid_date', DATE_BUCKETS)):
        group = value[key]
        require(type(group) is dict and all(type(key) is str for key in group)
            and set(group) == set(names), 'failure_context')
        for item in group.values(): integer(item, 256)
        require(sum(group.values()) == value['missing'], 'failure_context')
    probe = value['probe']
    require(type(probe) is dict and all(type(key) is str for key in probe)
        and set(probe) == {'status', 'requested', 'batches', 'items',
        'identity_valid', 'request_invoked', 'rows_by_offset'} and type(probe['status']) is str
        and probe['status'] in PROBE_STATUSES and (probe['identity_valid'] is None
            or type(probe['identity_valid']) is bool) and type(probe['request_invoked']) is bool,
        'failure_context')
    for key, maximum in (('requested', 16), ('batches', 8), ('items', 128)):
        integer(probe[key], maximum)
    offsets = probe['rows_by_offset']
    require(type(offsets) is dict and all(type(key) is str for key in offsets)
        and set(offsets) == set(OFFSET_BUCKETS), 'failure_context')
    for item in offsets.values(): integer(item, 128)
    require(sum(offsets.values()) <= probe['items'], 'failure_context')
    if probe['request_invoked']:
        require(probe['requested'] == value['missing'] and 1 <= value['missing'] <= 16
            and probe['status'] not in ('not_started', 'skipped_limit', 'unknown_clock'), 'failure_context')
    else:
        require(probe['requested'] == probe['batches'] == probe['items'] == 0
            and probe['identity_valid'] is None and sum(offsets.values()) == 0
            and probe['status'] in ('not_started', 'skipped_limit', 'unknown_clock', 'read_failed'), 'failure_context')
    if probe['status'] == 'complete':
        require(probe['identity_valid'] is True and sum(offsets.values()) == probe['items'], 'failure_context')
    if probe['status'] == 'identity_invalid':
        require(probe['identity_valid'] is False, 'failure_context')
    require(probe['identity_valid'] is (True if probe['status'] == 'complete' else
        False if probe['status'] == 'identity_invalid' else None), 'failure_context')
    if probe['status'] == 'skipped_limit':
        require(value['missing'] > 16, 'failure_context')
    raw = canonical(value)
    require(0 < len(raw) <= 8192, 'failure_context')
    return json.loads(raw)


def parse_failure_context(value):
    if type(value) is not str or not 0 < len(value) <= 8192 or not value.isascii():
        return None
    prefix = FAILURE_CODES[0] + '|context='
    positions = [match.end() for match in re.finditer(r'(?<![A-Za-z0-9_])' + re.escape(prefix), value)]
    if len(positions) != 1:
        return None
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise Refused('failure_context')
            result[key] = item
        return result
    try:
        text = value[positions[0]:]
        parsed, end = json.JSONDecoder(object_pairs_hook=pairs).raw_decode(text)
        require(canonical(parsed).decode('ascii') == text[:end]
            and (end == len(text) or text[end] in '\r\n'), 'failure_context')
        return validate_failure_context(parsed)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None


def validate_public_projection(record_bytes, source_pairs, *, expected_projection_sha256,
                               expected_profile_sha256):
    require(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
        for value in (expected_projection_sha256, expected_profile_sha256))
        and type(record_bytes) is bytes and 0 < len(record_bytes) <= 128 * 1024
        and sha(record_bytes) == expected_projection_sha256, 'projection_pin')
    try:
        require(type(source_pairs) is tuple and len(source_pairs) == 11
            and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str and type(item[1]) is bytes
                and item[1].isascii() and 0 < len(item[1]) <= 64000 for item in source_pairs)
            and tuple(name for name, _ in source_pairs) == comparison.bridge.parent.FILE_NAMES
            and sum(len(raw) for _, raw in source_pairs) <= 448 * 1024, 'source_pairs')
        record = json.loads(record_bytes)
        keys = {'schema', 'candidate_id', 'economic_candidate_id', 'parent_projection_sha256',
            'parent_profile_sha256', 'parent_source_manifest_sha256', 'profile_sha256', 'package_sha256',
            'lineage_sha256', 'activation_manifest_key', 'activation_manifest_sha256',
            'activation_manifest_byte_count', 'patcher_sha256', 'diagnostic_only', 'policy',
            'failure_codes', 'diagnostic_context_schema', 'unchanged_cloud_files', 'quote_runtime_sha256',
            'source_files'} | set(FALSE_FLAGS)
        require(type(record) is dict and set(record) == keys and canonical(record) == record_bytes
            and record['schema'] == SCHEMA and record['candidate_id'] == 'R298'
            and record['parent_projection_sha256'] == PARENT_PROJECTION
            and record['parent_profile_sha256'] == PARENT_PROFILE
            and record['parent_source_manifest_sha256'] == PARENT_MANIFEST
            and record['profile_sha256'] == expected_profile_sha256
            and record['diagnostic_only'] is True and canonical(record['policy']) == canonical(policy_record())
            and record['failure_codes'] == list(FAILURE_CODES)
            and record['diagnostic_context_schema'] == CONTEXT_SCHEMA
            and record['quote_runtime_sha256'] == PARENT_RUNTIME
            and all(record[name] is False for name in FALSE_FLAGS)
            and record['package_sha256'] == comparison.PLAIN_PACKAGE_SHA256
            and record['lineage_sha256'] == comparison.bridge.parent.LINEAGE
            and all(record[name] == value and type(record[name]) is type(value)
                for name, value in zip(('activation_manifest_key', 'activation_manifest_sha256',
                    'activation_manifest_byte_count'), comparison.PLAIN_ACTIVATION, strict=True))
            and type(record['patcher_sha256']) is str and re.fullmatch('[0-9a-f]{64}', record['patcher_sha256'])
            and record['unchanged_cloud_files'] == [name for name in comparison.bridge.parent.FILE_NAMES
                if name not in (LEGACY_NAME, 'main.py')]
            and record['source_files'] == [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)}
                for name, raw in source_pairs], 'projection_packet')
        files = dict(source_pairs)
        require(sha(files[quote.RUNTIME_NAME]) == PARENT_RUNTIME, 'projection_packet')
        profile = ast.literal_eval(quote._driver(ast.parse(files['main.py']))['profile'].value)
        pins = {**comparison.bridge.parent.SOURCE_PINS, **comparison.NEW_SOURCE_PINS,
            quote.RUNTIME_NAME: PARENT_RUNTIME, quote.PATCHER_NAME:
            'ebc6d921c5dbaa5e9bc83379ab45c167780fb87db8441dbd9d618b3efcb1715f',
            LEGACY_NAME: sha(files[LEGACY_NAME]), PATCHER_NAME: record['patcher_sha256']}
        require(type(profile) is dict and profile.get('profile_sha256') == expected_profile_sha256
            and profile.get('candidate_id') == record['economic_candidate_id']
            and profile.get('source_pins') == pins, 'projection_profile')
        expected = quote._profile(comparison.bridge.frozen.october._sessions(), universe_count=6,
            ar_percent=0, source_pins=pins)
        require(canonical(profile) == canonical(expected), 'projection_profile')
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, RecursionError):
        raise Refused('projection_packet') from None
    return record, profile, source_pairs


validate_result_statistics = quote.validate_result_statistics
