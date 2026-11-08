"""Pure identity-v2 selected response; no operation or full-body authentication.

The existing HTTP transport owns its unchanged 16-MiB wire bound.  Call this
selector before canonicalizing the decoded response: ignored chart, order,
trade and performance subtrees are neither traversed nor hashed here.  The pin
authenticates only this selected projection, never the complete HTTP body.
Import performs no operation and supplies no launch or result-admission authority.
"""
from __future__ import annotations

import hashlib
import json
import re

from scripts import arv2_r298_quote_execution_a16_remote as frozen
from scripts import arv2_newrule_reference_identity_projection as raw_diagnostic


SCHEMA = 'arv2-newrule-reference-identity-response-v1'
MAX_SELECTED_BYTES = 64 * 1024
MAX_STATISTIC_BYTES = 8192
MAX_ERROR_BYTES = frozen.MAX_ERROR_BYTES
MAX_ERROR_VALUES, MAX_ERROR_LINES = 11, 512
META_STATISTIC = frozen.previous.frozen.runtime.META_STATISTIC
MONTHLY_STATISTIC = frozen.previous.frozen.runtime.MONTHLY_STATISTIC
RAW_REFERENCE_LITERAL = ('six-universe RAW reference price census is incomplete; '
    'no stale-price fallback is permitted')
RAW_REFERENCE_CODE = 'raw_reference_census_incomplete'
KNOWN_CODES = frozen.KNOWN_CODES | frozenset((RAW_REFERENCE_CODE,))
PYTHON_CATEGORIES = frozenset(('SyntaxError', 'IndentationError', 'ImportError',
    'ModuleNotFoundError', 'NameError', 'TypeError'))
FINITE = frozenset(('binding', 'response', 'response_success', 'response_errors',
    'response_identity', 'response_status', 'response_compile', 'error_bound',
    'error_shape', 'statistics', 'selected_shape', 'selected_pin', 'selected_bound',
    'failure_evidence'))


class Refused(ValueError):
    """Closed finite refusal, never a provider message."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def profile_record():
    return {'schema': SCHEMA, 'modes': ['error', 'completed'],
        'selection_pin_scope': 'selected_projection_only',
        'whole_response_authenticated': False,
        'maximum_selected_bytes': MAX_SELECTED_BYTES,
        'maximum_statistic_bytes_each': MAX_STATISTIC_BYTES,
        'statistic_names': [META_STATISTIC, MONTHLY_STATISTIC],
        'maximum_error_bytes_each': MAX_ERROR_BYTES,
        'maximum_error_values': MAX_ERROR_VALUES,
        'maximum_error_lines_each': MAX_ERROR_LINES,
        'error_fields': ['error', 'errorMessage', 'stacktrace', 'errors'],
        'additional_diagnostic_code': RAW_REFERENCE_CODE,
        'diagnostic_context_schema': raw_diagnostic.CONTEXT_SCHEMA,
        'raw_error_retained': False, 'cause_authenticated': False,
        'complete_body_pin': False, 'financial_result_validated': False,
        'ignored_subtrees': 'not_traversed_or_canonicalized'}


def _identifier(value):
    return type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value) is not None


def _binding(project_id, backtest_id, backtest_name, compile_id, mode):
    require(type(project_id) is int and 0 < project_id < 2**63 and _identifier(backtest_id)
        and type(backtest_name) is str and 0 < len(backtest_name) <= 200 and backtest_name.isascii()
        and all(32 <= ord(c) < 127 for c in backtest_name)
        and (compile_id is None or _identifier(compile_id))
        and type(mode) is str and mode in ('error', 'completed'), 'binding')
    return {'project_id': project_id, 'backtest_id': backtest_id,
        'backtest_name': backtest_name, 'compile_id': compile_id,
        'status': 'Runtime Error' if mode == 'error' else 'Completed.'}


def _row_identity(row, binding):
    require(type(row) is dict, 'response_identity')
    require(type(row.get('projectId')) is int and row['projectId'] == binding['project_id']
        and type(row.get('backtestId')) is str and row['backtestId'] == binding['backtest_id']
        and type(row.get('name')) is str and row['name'] == binding['backtest_name'], 'response_identity')
    require(type(row.get('status')) is str and row['status'] == binding['status'], 'response_status')
    selected = {name: row[name] for name in ('projectId', 'backtestId', 'name', 'status')}
    if 'compileId' in row:
        require(type(row['compileId']) is str and binding['compile_id'] is not None
            and row['compileId'] == binding['compile_id'], 'response_compile')
        selected['compileId'] = row['compileId']
    return selected


def _context(value):
    # The v2 validator rejects fixed-shape/type/bound violations before any
    # canonical copy, including unknown hostile/oversized witness subtrees.
    try:
        return raw_diagnostic.validate_failure_context(value)
    except Exception:
        raise Refused('failure_evidence') from None


def validate_failure_evidence(value):
    fields = {'terminal_category', 'known_runtime_code', 'known_runtime_code_sha256',
        'python_error_category', 'raw_error_retained', 'cause_authenticated', 'diagnostic_context'}
    require(type(value) is dict and set(value) == fields
        and type(value['terminal_category']) is str and value['terminal_category'] == 'runtime_error'
        and value['raw_error_retained'] is False and value['cause_authenticated'] is False, 'failure_evidence')
    code, category = value['known_runtime_code'], value['python_error_category']
    require(code is None or (type(code) is str and code in KNOWN_CODES), 'failure_evidence')
    require(category is None or (type(category) is str and category in PYTHON_CATEGORIES), 'failure_evidence')
    pin = value['known_runtime_code_sha256']
    if code is None:
        require(pin is None, 'failure_evidence')
    else:
        require(type(pin) is str and pin == sha(code.encode('ascii')), 'failure_evidence')
    context = value['diagnostic_context']
    if context is not None:
        require(code == RAW_REFERENCE_CODE, 'failure_evidence')
        context = _context(context)
        require(context['predicate'] == code, 'failure_evidence')
    if code != RAW_REFERENCE_CODE:
        frozen._validate_failure(value, 'runtime_error')
    return {**value, 'diagnostic_context': context}


def _error_values(row):
    values = []
    for field in ('error', 'errorMessage', 'stacktrace'):
        value = row.get(field)
        if value is not None:
            require(type(value) is str, 'error_shape')
            values.append(value)
    if 'errors' in row and row['errors'] is not None:
        extra = row['errors']
        require(type(extra) is list and len(extra) <= 8, 'error_shape')
        require(all(type(value) is str for value in extra), 'error_shape')
        values.extend(extra)
    require(len(values) <= MAX_ERROR_VALUES, 'error_bound')
    for value in values:
        require(len(value) <= MAX_ERROR_BYTES, 'error_bound')
        try:
            require(len(value.encode('utf-8')) <= MAX_ERROR_BYTES
                and len(value.splitlines()) <= MAX_ERROR_LINES, 'error_bound')
        except UnicodeError:
            raise Refused('error_bound') from None
    return values


def _is_raw_reference(line):
    # Whole fixed message, with only explicit known exception wrappers.  Old
    # formatted context suffixes are not this exact diagnostic literal.
    for prefix in ('', 'AcceptedRiskSixUniverseOrderQcRuntimeError: ',
            'NewruleError: ', 'RuntimeError: ', 'Runtime Error: '):
        text = prefix + RAW_REFERENCE_LITERAL
        if line == text:
            return True
    return False


def failure_evidence(row):
    require(type(row) is dict, 'response')
    codes, categories, contexts = set(), set(), {}
    for value in _error_values(row):
        item = frozen.failure_evidence({'error': value}, 'runtime_error')
        frozen._validate_failure(item, 'runtime_error')
        # Preserve ambiguity across and within messages; the frozen classifier
        # intentionally returns None for multiple codes, which must not later
        # be mistaken for an absent code and overwritten by a second message.
        for line in value.splitlines():
            line = line.strip()
            context = raw_diagnostic.parse_failure_context(line)
            if context is not None:
                checked = _context(context)
                contexts[canonical(checked)] = checked
                codes.add(checked['predicate'])
            if line in KNOWN_CODES:
                codes.add(line)
            for match in re.finditer(r'(?<![A-Za-z0-9_])(?:NewruleError|RuntimeError|Runtime Error)\s*:\s*([a-z_]{1,64})(?![A-Za-z0-9_])', line):
                if match.group(1) in KNOWN_CODES:
                    codes.add(match.group(1))
            for category in PYTHON_CATEGORIES:
                if line.startswith(category + ': '):
                    categories.add(category)
            if _is_raw_reference(line):
                codes.add(RAW_REFERENCE_CODE)
    code = next(iter(codes)) if len(codes) == 1 and len(contexts) <= 1 else None
    context = next(iter(contexts.values())) if len(contexts) == 1 else None
    if context is not None and context['predicate'] != code:
        context = None
    result = {'terminal_category': 'runtime_error', 'known_runtime_code': code,
        'known_runtime_code_sha256': sha(code.encode('ascii')) if code else None,
        'python_error_category': next(iter(categories)) if len(categories) == 1 else None,
        'raw_error_retained': False, 'cause_authenticated': False, 'diagnostic_context': context}
    return validate_failure_evidence(result)


def _statistics(row):
    stats = row.get('statistics')
    require(type(stats) is dict, 'statistics')
    result = {}
    for name in (META_STATISTIC, MONTHLY_STATISTIC):
        value = stats.get(name)
        require(type(value) is str and 0 < len(value) <= MAX_STATISTIC_BYTES and value.isascii(),
            'statistics')
        result[name] = value
    return result


def _with_pin(selected):
    raw = canonical(selected)
    require(len(raw) <= MAX_SELECTED_BYTES, 'selected_bound')
    result = {**selected, 'selection_pin': {'scope': 'selected_projection_only',
        'byte_count': len(raw), 'sha256': sha(raw)}}
    require(len(canonical(result)) <= MAX_SELECTED_BYTES, 'selected_bound')
    return result


def select_response(value, *, project_id, backtest_id, backtest_name, compile_id, mode):
    """Select only a bound Runtime Error or exact Completed. response.

    This is not financial-result admission, proof of authenticated root cause,
    or whole-body integrity.  Expected identities must come from the caller's
    separately authenticated launch receipt, never from this response itself.
    """
    binding = _binding(project_id, backtest_id, backtest_name, compile_id, mode)
    require(type(value) is dict, 'response')
    require(value.get('success') is True, 'response_success')
    require('errors' not in value or (type(value['errors']) is list and not value['errors']), 'response_errors')
    row = value.get('backtest')
    selected = _row_identity(row, binding)
    if mode == 'error':
        selected['finite_projected_error'] = failure_evidence(row)
    else:
        selected['statistics'] = _statistics(row)
    return _with_pin({'schema': SCHEMA, 'mode': mode, 'expected_binding': binding,
        'success': True, 'backtest': selected, 'whole_response_authenticated': False})


def validate_selected(value, *, project_id, backtest_id, backtest_name, compile_id, mode):
    """Validate a received small selection and its selected-fields-only pin."""
    binding = _binding(project_id, backtest_id, backtest_name, compile_id, mode)
    require(type(value) is dict and set(value) == {'schema', 'mode', 'expected_binding',
        'success', 'backtest', 'whole_response_authenticated', 'selection_pin'}, 'selected_shape')
    require(type(value['schema']) is str and value['schema'] == SCHEMA
        and type(value['mode']) is str and value['mode'] == mode and value['success'] is True
        and value['whole_response_authenticated'] is False
        and type(value['expected_binding']) is dict and set(value['expected_binding']) == set(binding)
        and all(type(value['expected_binding'][key]) is type(wanted)
            and value['expected_binding'][key] == wanted for key, wanted in binding.items()), 'selected_shape')
    row = value['backtest']
    selected = _row_identity(row, binding)
    extra = 'finite_projected_error' if mode == 'error' else 'statistics'
    require(set(row) == set(selected) | {extra}, 'selected_shape')
    if mode == 'error':
        selected[extra] = validate_failure_evidence(row[extra])
    else:
        require(type(row[extra]) is dict and set(row[extra]) == {META_STATISTIC, MONTHLY_STATISTIC}, 'statistics')
        selected[extra] = _statistics(row)
    pin = value['selection_pin']
    require(type(pin) is dict and set(pin) == {'scope', 'byte_count', 'sha256'}
        and type(pin['scope']) is str and pin['scope'] == 'selected_projection_only'
        and type(pin['byte_count']) is int and 0 < pin['byte_count'] <= MAX_SELECTED_BYTES
        and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'selected_pin')
    expected = _with_pin({'schema': SCHEMA, 'mode': mode, 'expected_binding': binding,
        'success': True, 'backtest': selected, 'whole_response_authenticated': False})
    require(pin == expected['selection_pin'], 'selected_pin')
    return expected
