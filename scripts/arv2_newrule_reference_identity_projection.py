"""Pure failure-only missing-reference identities, never a price repair.

The already spent RAW probe is removed. Only date-bound identity digests and
closed aggregate facts can leave the original incomplete-census failure path.
The quote runtime and every successful-path statement remain unchanged.
"""
from __future__ import annotations

import ast
import copy
from datetime import datetime
from functools import lru_cache
import json
import re

from scripts import arv2_newrule_raw_reference_diagnostic_projection as parent


quote = parent.quote
admission, comparison = parent.admission, parent.comparison
canonical, sha = parent.canonical, parent.sha
DiagnosticProjection = parent.DiagnosticProjection
SCHEMA = 'arv2-newrule-reference-identity-projection-v1'
PATCHER_NAME = 'arv2_newrule_reference_identity_projection.py'
LEGACY_NAME = parent.LEGACY_NAME
PARENT_PROJECTION = 'dc1db76b792ab1ac17879e87b3dcf1f544ca288f46a487d93b01b2eac4658e77'
PARENT_PROFILE = '4f5385004a0d5d21abb891d2a4e94ce684cc560ba32015c4da215dd34da67aea'
PARENT_MANIFEST = 'e8118198f92063743cdd52b8c55f155d38326f8e2e6b9d8069c29d8fb5525b61'
PARENT_LEGACY = '78a4caef599226bb960d441be1148dfeb40d81a3f9015cd4a10061c937e4724f'
PARENT_RUNTIME = parent.PARENT_RUNTIME
PARENT_PATCHER = 'ef92bdb198586243166f7cf76276f6ed339fda90f52792eeab70da56894fcae6'
QUOTE_PATCHER = 'ebc6d921c5dbaa5e9bc83379ab45c167780fb87db8441dbd9d618b3efcb1715f'
SESSION_AXIS_SHA256 = '4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
CONTEXT_SCHEMA = 'arv2-raw-reference-identity-context-v2'
IDENTITY_SCHEMA = 'arv2-missing-reference-identity-v1'
FAILURE_CODES = ('raw_reference_census_incomplete',)
MARKER = FAILURE_CODES[0] + '|identity_v2='
ORIGINAL_FAILURE = parent.ORIGINAL_FAILURE
HOLDING_BUCKETS, KIND_BUCKETS, DATE_BUCKETS = parent.HOLDING_BUCKETS, parent.KIND_BUCKETS, parent.DATE_BUCKETS
FINITE = parent.FINITE | frozenset(('complete_witness', 'calendar'))
FALSE_FLAGS = dict(parent.FALSE_FLAGS)
Refused = parent.Refused
require = parent.require


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


def policy_record():
    return {'schema': 'arv2-reference-identity-failure-witness-v2',
        'diagnostic_only': True, 'primary_history_call_unchanged': True,
        'extra_history_calls': 0, 'prior_raw_probe_repeated': False,
        'always_refuse_after_incomplete_census': True, 'maximum_witnesses': 16,
        'partial_witness_selection': False, 'identity_schema': IDENTITY_SCHEMA,
        'identity_hash_fields': ['schema', 'security_id', 'reference_session', 'decision_session'],
        'identity_hash_encoding': 'legacy_sha_canonical_ASCII_JSON_without_LF',
        'hash_is_anonymity_proof': False, 'calendar_hash': SESSION_AXIS_SHA256,
        'calendar': 'actual_NY_0920_decision_and_immediately_previous_public_axis_session',
        'probe_prices_used': False, 'sizing_repaired': False,
        'quote_runtime_unchanged': True, **FALSE_FLAGS}


def context_record(requested, returned):
    require(type(requested) is int and type(returned) is int
        and 1 <= requested <= 256 and 0 <= returned < requested, 'failure_context')
    missing = requested - returned
    return {'schema': CONTEXT_SCHEMA, 'predicate': FAILURE_CODES[0],
        'requested': requested, 'returned': returned, 'missing': missing,
        'missing_holdings': {'held': 0, 'unheld_target': 0, 'unknown': missing},
        'missing_kind': {'own_etf': 0, 'stock': 0, 'unknown': missing},
        'missing_sid_date': {'on_or_before_reference': 0, 'after_reference_through_decision': 0,
            'after_decision': 0, 'unknown': missing},
        'calendar_status': 'unavailable', 'reference_session': None, 'decision_session': None,
        'decision_time': None, 'session_axis_sha256': None,
        'witness_status': 'unavailable', 'witnesses': [],
        'cause_authenticated': False, 'probe_prices_used': False, 'sizing_repaired': False,
        'diagnostic_only': True, 'extra_history_call': False, 'probe_repeated': False}


@lru_cache(maxsize=1)
def _axis():
    axis = comparison.bridge.frozen.october._sessions()
    require(type(axis) is tuple and sha(canonical(list(axis))) == SESSION_AXIS_SHA256, 'calendar')
    decisions = comparison.bridge.frozen.runtime.weekly_axis(axis)
    return axis, frozenset(decisions)


def _calendar(value):
    fields = ('reference_session', 'decision_session', 'decision_time', 'session_axis_sha256')
    status = value['calendar_status']
    require(type(status) is str and status in ('valid', 'unavailable'), 'failure_context')
    if status == 'unavailable':
        require(all(value[key] is None for key in fields), 'failure_context')
        return
    reference, decision = value['reference_session'], value['decision_session']
    require(type(reference) is str and type(decision) is str and len(reference) == len(decision) == 10
        and type(value['decision_time']) is str and value['decision_time'] == '09:20'
        and type(value['session_axis_sha256']) is str
        and value['session_axis_sha256'] == SESSION_AXIS_SHA256, 'failure_context')
    try:
        require(datetime.strptime(reference, '%Y-%m-%d').date().isoformat() == reference
            and datetime.strptime(decision, '%Y-%m-%d').date().isoformat() == decision, 'failure_context')
        axis, decisions = _axis()
        position = axis.index(decision)
        require(position > 0 and decision in decisions and axis[position - 1] == reference, 'failure_context')
    except (ValueError, TypeError):
        raise Refused('failure_context') from None


def validate_failure_context(value):
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == set(context_record(1, 0)), 'failure_context')
    require(type(value['schema']) is str and value['schema'] == CONTEXT_SCHEMA
        and type(value['predicate']) is str and value['predicate'] == FAILURE_CODES[0]
        and all(value[key] is False for key in ('cause_authenticated', 'probe_prices_used',
            'sizing_repaired', 'extra_history_call', 'probe_repeated'))
        and value['diagnostic_only'] is True, 'failure_context')
    for key in ('requested', 'returned', 'missing'):
        require(type(value[key]) is int and 0 <= value[key] <= 256, 'failure_context')
    require(value['requested'] >= 1 and value['missing'] >= 1
        and value['returned'] + value['missing'] == value['requested'], 'failure_context')
    for key, names in (('missing_holdings', HOLDING_BUCKETS), ('missing_kind', KIND_BUCKETS),
                       ('missing_sid_date', DATE_BUCKETS)):
        group = value[key]
        require(type(group) is dict and all(type(name) is str for name in group)
            and set(group) == set(names)
            and all(type(item) is int and 0 <= item <= 256 for item in group.values())
            and sum(group.values()) == value['missing'], 'failure_context')
    _calendar(value)
    status, rows = value['witness_status'], value['witnesses']
    require(type(status) is str and status in ('complete', 'skipped_limit', 'unavailable')
        and type(rows) is list and len(rows) <= 16, 'failure_context')
    for row in rows:
        require(type(row) is dict and all(type(key) is str for key in row)
            and set(row) == {'identity_sha256', 'holding', 'kind', 'sid_date'}
            and type(row['identity_sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['identity_sha256'])
            and type(row['holding']) is str and row['holding'] in HOLDING_BUCKETS
            and type(row['kind']) is str and row['kind'] in KIND_BUCKETS
            and type(row['sid_date']) is str and row['sid_date'] in DATE_BUCKETS, 'failure_context')
    pins = [row['identity_sha256'] for row in rows]
    require(pins == sorted(set(pins)), 'failure_context')
    if status == 'complete':
        require(value['calendar_status'] == 'valid' and len(rows) == value['missing'], 'failure_context')
        for field, key, names in (('holding', 'missing_holdings', HOLDING_BUCKETS),
                ('kind', 'missing_kind', KIND_BUCKETS), ('sid_date', 'missing_sid_date', DATE_BUCKETS)):
            require({name: sum(row[field] == name for row in rows) for name in names} == value[key], 'failure_context')
    else:
        require(rows == [], 'failure_context')
        if status == 'skipped_limit':
            require(value['missing'] > 16, 'failure_context')
    raw = canonical(value)
    require(0 < len(raw) <= 8192, 'failure_context')
    return json.loads(raw)


def validate_complete_witness(value):
    checked = validate_failure_context(value)
    require(checked['calendar_status'] == 'valid' and checked['witness_status'] == 'complete', 'complete_witness')
    return checked


def parse_failure_context(value):
    if type(value) is not str or not 0 < len(value) <= 8192 or not value.isascii():
        return None
    positions = [match.end() for match in re.finditer(r'(?<![A-Za-z0-9_])' + re.escape(MARKER), value)]
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


FAILURE_BODY = '''missing = tuple(identity for identity in security_ids if identity not in result)
context = {"schema": "arv2-raw-reference-identity-context-v2", "predicate": "raw_reference_census_incomplete",
    "requested": len(security_ids), "returned": len(result), "missing": len(missing),
    "missing_holdings": {"held": 0, "unheld_target": 0, "unknown": 0},
    "missing_kind": {"own_etf": 0, "stock": 0, "unknown": 0},
    "missing_sid_date": {"on_or_before_reference": 0, "after_reference_through_decision": 0, "after_decision": 0, "unknown": 0},
    "calendar_status": "unavailable", "reference_session": None, "decision_session": None,
    "decision_time": None, "session_axis_sha256": None, "witness_status": "unavailable", "witnesses": [],
    "cause_authenticated": False, "probe_prices_used": False, "sizing_repaired": False,
    "diagnostic_only": True, "extra_history_call": False, "probe_repeated": False}
pairs = tuple((identity, symbol) for identity, symbol in zip(security_ids, symbols, strict=True) if identity in missing)
try:
    holdings = self._current_holding_census()
except Exception:
    holdings = None
decision = None
try:
    now = self._now()
    if now.time().replace(tzinfo=None) == datetime.strptime("09:20", "%H:%M").time():
        decision = now.replace(tzinfo=None)
        decision_session = decision.date().isoformat()
        position = self._session_positions[decision_session]
        axis_hash = _sha(self._session_axis)
        if (position > 0 and self._session_axis[position - 1] == session
                and decision_session in self._decision_set
                and axis_hash == self._profile["session_axis_sha256"]
                and axis_hash == "4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585"):
            context.update(calendar_status="valid", reference_session=session,
                decision_session=decision_session, decision_time="09:20", session_axis_sha256=axis_hash)
except Exception:
    pass
reference = datetime.strptime(session, "%Y-%m-%d")
facts = []
for identity, symbol in pairs:
    holding = "unknown" if holdings is None else "held" if identity in holdings else "unheld_target"
    context["missing_holdings"][holding] += 1
    try:
        sid = _symbol_sid(symbol, "reference identity diagnostic")
        kind = "own_etf" if sid in self._security_by_etf_sid else "stock" if sid in self._security_by_sid else "unknown"
    except Exception:
        kind = "unknown"
    context["missing_kind"][kind] += 1
    sid_date = "unknown"
    try:
        origin = symbol.id.date
        if isinstance(origin, datetime):
            origin = origin.replace(tzinfo=None)
            if origin.date() <= reference.date():
                sid_date = "on_or_before_reference"
            elif decision is not None:
                sid_date = "after_reference_through_decision" if origin.date() <= decision.date() else "after_decision"
    except Exception:
        pass
    context["missing_sid_date"][sid_date] += 1
    facts.append((identity, holding, kind, sid_date))
if len(facts) > 16:
    context["witness_status"] = "skipped_limit"
elif context["calendar_status"] == "valid":
    try:
        rows = []
        for identity, holding, kind, sid_date in facts:
            if type(identity) is not str or not 0 < len(identity) <= 512:
                raise ValueError()
            pin = _sha({"schema": "arv2-missing-reference-identity-v1", "security_id": identity,
                "reference_session": context["reference_session"], "decision_session": context["decision_session"]})
            rows.append({"identity_sha256": pin, "holding": holding, "kind": kind, "sid_date": sid_date})
        rows.sort(key=lambda row: row["identity_sha256"])
        if len({row["identity_sha256"] for row in rows}) != len(facts):
            raise ValueError()
        context["witnesses"] = rows
        context["witness_status"] = "complete"
    except Exception:
        context["witnesses"] = []
_error("six-universe RAW reference price census is incomplete; no stale-price fallback is permitted"
    + "\\nraw_reference_census_incomplete|identity_v2=" + json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
'''


def _legacy(raw):
    require(sha(raw) == PARENT_LEGACY, 'legacy_pin')
    original = ast.parse(raw)
    tree = copy.deepcopy(original)
    method = parent._legacy_method(tree)
    branches = [node for node in method.body if isinstance(node, ast.If)
        and parent._dump(node.test) == parent._dump(ast.parse('set(result) != set(security_ids)', mode='eval').body)]
    require(len(branches) == 1 and not branches[0].orelse
        and parent._dump(ast.Module(body=branches[0].body, type_ignores=[]))
        == parent._dump(ast.parse(parent.FAILURE_BODY)), 'legacy_anchor')
    old_body = copy.deepcopy(branches[0].body)
    branches[0].body = ast.parse(FAILURE_BODY).body
    ast.fix_missing_locations(tree)
    restored = copy.deepcopy(tree)
    branch, = [node for node in parent._legacy_method(restored).body if isinstance(node, ast.If)
        and parent._dump(node.test) == parent._dump(branches[0].test)]
    branch.body = old_body
    require(parent._dump(restored) == parent._dump(original), 'legacy_semantics')
    result = (ast.unparse(tree) + '\n').encode('ascii')
    require(0 < len(result) <= 64000, 'source_bound')
    compile(result, LEGACY_NAME, 'exec')
    return result


def public_specification(source_pairs, *, patcher_source_bytes, expected_patcher_sha256):
    require(type(expected_patcher_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_patcher_sha256)
        and type(patcher_source_bytes) is bytes and 0 < len(patcher_source_bytes) <= 100000
        and patcher_source_bytes.isascii() and sha(patcher_source_bytes) == expected_patcher_sha256, 'patcher_pin')
    require(type(source_pairs) is tuple and len(source_pairs) == 11
        and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str and type(item[1]) is bytes
            and item[1].isascii() and 0 < len(item[1]) <= 64000 for item in source_pairs)
        and tuple(name for name, _ in source_pairs) == comparison.bridge.parent.FILE_NAMES, 'source_pairs')
    manifest = {'project_id': 38364439, 'projection_sha256': PARENT_PROJECTION,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)} for name, raw in source_pairs]}
    require(sha(canonical(manifest) + b'\n') == PARENT_MANIFEST, 'parent_manifest')
    files = dict(source_pairs)
    profile = ast.literal_eval(quote._driver(ast.parse(files['main.py']))['profile'].value)
    require(type(profile) is dict and profile.get('profile_sha256') == PARENT_PROFILE
        and sha(files[quote.RUNTIME_NAME]) == PARENT_RUNTIME, 'parent_profile')
    expected = quote._profile(comparison.bridge.frozen.october._sessions(), universe_count=6,
        ar_percent=0, source_pins=dict(profile['source_pins']))
    require(canonical(profile) == canonical(expected), 'parent_profile')
    legacy = _legacy(files[LEGACY_NAME])
    pins = {**profile['source_pins'], LEGACY_NAME: sha(legacy), PATCHER_NAME: expected_patcher_sha256}
    profile = quote._profile(comparison.bridge.frozen.october._sessions(), universe_count=6,
        ar_percent=0, source_pins=pins)
    tree = ast.parse(files['main.py'])
    old_value = copy.deepcopy(quote._driver(tree)['profile'].value)
    quote._driver(tree)['profile'].value = ast.parse(repr(profile), mode='eval').body
    ast.fix_missing_locations(tree)
    restored = copy.deepcopy(tree)
    quote._driver(restored)['profile'].value = old_value
    require(parent._dump(restored) == parent._dump(ast.parse(files['main.py'])), 'main_semantics')
    main = (ast.unparse(tree) + '\n').encode('ascii')
    compile(main, 'main.py', 'exec')
    projected = tuple((name, legacy if name == LEGACY_NAME else main if name == 'main.py' else raw)
        for name, raw in source_pairs)
    require(all(0 < len(raw) <= 64000 for _, raw in projected)
        and sum(len(raw) for _, raw in projected) <= 448 * 1024, 'source_bound')
    unchanged = [name for name, raw in projected if raw == files[name]]
    require(len(unchanged) == 9 and quote.RUNTIME_NAME in unchanged, 'unchanged_sources')
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
    raw = canonical(record)
    result = DiagnosticProjection(sha(raw), raw, canonical(profile), projected)
    result.to_record()
    return result


def build_projection(packet, *, patcher_source_bytes, expected_patcher_sha256,
                     quote_patcher_source_bytes, raw_patcher_source_bytes):
    old = parent.build_projection(packet, patcher_source_bytes=raw_patcher_source_bytes,
        expected_patcher_sha256=PARENT_PATCHER, quote_patcher_source_bytes=quote_patcher_source_bytes)
    require(old.projection_sha256 == PARENT_PROJECTION, 'parent_projection')
    return public_specification(old.source_pairs, patcher_source_bytes=patcher_source_bytes,
        expected_patcher_sha256=expected_patcher_sha256)


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
            and record['failure_codes'] == list(FAILURE_CODES) and record['diagnostic_context_schema'] == CONTEXT_SCHEMA
            and record['quote_runtime_sha256'] == PARENT_RUNTIME and all(record[name] is False for name in FALSE_FLAGS)
            and record['package_sha256'] == comparison.PLAIN_PACKAGE_SHA256
            and record['lineage_sha256'] == comparison.bridge.parent.LINEAGE
            and all(record[name] == expected and type(record[name]) is type(expected)
                for name, expected in zip(('activation_manifest_key', 'activation_manifest_sha256',
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
            quote.RUNTIME_NAME: PARENT_RUNTIME, quote.PATCHER_NAME: QUOTE_PATCHER,
            parent.PATCHER_NAME: PARENT_PATCHER, LEGACY_NAME: sha(files[LEGACY_NAME]),
            PATCHER_NAME: record['patcher_sha256']}
        require(type(profile) is dict and profile.get('profile_sha256') == expected_profile_sha256
            and profile.get('candidate_id') == record['economic_candidate_id'] and profile.get('source_pins') == pins,
            'projection_profile')
        expected = quote._profile(comparison.bridge.frozen.october._sessions(), universe_count=6,
            ar_percent=0, source_pins=pins)
        require(canonical(profile) == canonical(expected), 'projection_profile')
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, RecursionError):
        raise Refused('projection_packet') from None
    return record, profile, source_pairs


validate_result_statistics = quote.validate_result_statistics
