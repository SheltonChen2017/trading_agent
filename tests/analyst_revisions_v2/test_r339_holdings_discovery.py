"""Synthetic supplied bodies only; no provider/account/retained DATA access."""
import ast
import copy
from decimal import localcontext
import hashlib
import json
from pathlib import Path

import pytest

from scripts import arv2_r339_holdings_discovery as m

KEY = 'SYNTHETIC-NOT-A-REAL-ACCOUNT-TOKEN'


def raw(value): return json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode('ascii')
def request(provider='massive', index=0):
    return [row for row in m.request_plan() if row['provider'] == provider][index]


def massive(item=None):
    item = item or request()
    return {'status': 'OK', 'request_id': 'SYNTHETIC-REQUEST-ID', 'count': 1,
        'results': [{'composite_ticker': item['fund'], 'effective_date': item['effective_date'],
            'processed_date': '2026-10-13', 'constituent_ticker': 'PRIVATE-POSITION',
            'figi': 'BBG000000001', 'isin': 'US0378331005', 'sedol': '2046251',
            'us_code': '037833100', 'weight': 0.1234567890123456,
            'shares_held': 1234567, 'market_value': 7654321.1234,
            'constituent_name': 'SYNTHETIC PRIVATE HOLDING NAME', 'asset_class': 'Equity',
            'country_of_exchange': 'US', 'currency_traded': 'USD', 'exchange': 'SYNTHETIC',
            'security_type': 'Common Stock', 'constituent_rank': 1}]}


def dates():
    return [{'date': '2026-04-30', 'year': 2026, 'quarter': 2},
        {'date': '2021-09-30', 'year': 2021, 'quarter': 3}]


def inspect(item, value): return m.parse_response(item, raw(value), credential=KEY)
def refuse(code, callback):
    with pytest.raises(m.Refused) as error: callback()
    assert m.finite(error.value) == code
    assert KEY not in str(error.value)


def test_exact_closed_request_inventory_is_fresh_and_has_no_credentials():
    plan = m.request_plan()
    assert len(plan) == 24 and [row['ordinal'] for row in plan] == list(range(24))
    assert tuple(m.FUNDS) == ('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE', 'XLI', 'XLF')
    assert tuple(m.DATES) == ('2021-10-29', '2026-10-12')
    assert [row['provider'] for row in plan] == ['massive'] * 16 + ['fmp'] * 8
    assert [row['provider_ordinal'] for row in plan] == list(range(16)) + list(range(8))
    assert {(row['fund'], row['effective_date']) for row in plan[:16]} == {
        (fund, day) for fund in m.FUNDS for day in m.DATES}
    assert all(row['query'] == {'composite_ticker': row['fund'], 'effective_date': row['effective_date'],
        'limit': '1', 'sort': 'constituent_ticker.asc'} for row in plan[:16])
    assert all(row['query'] == {'symbol': row['fund']} for row in plan[16:])
    assert KEY.encode() not in m.canonical(plan)
    plan[0]['query']['limit'] = '5000'
    assert m.request_plan()[0]['query']['limit'] == '1'


@pytest.mark.parametrize('ordinal', range(16))
def test_all_massive_fund_date_samples_emit_only_metadata(ordinal):
    item = request(index=ordinal); body = raw(massive(item))
    result = m.parse_response(item, body, credential=KEY)
    assert result == m.validate_summary(item, result)
    assert result['result_count'] == result['date_count'] == result['distinct_date_count'] == 1
    assert result['earliest_date'] == result['latest_date'] == item['effective_date']
    assert result['processed_date_count'] == 1
    assert result['identifier_presence_counts'] == {name: 1 for name in m.IDENTIFIERS}
    assert result['numeric_presence_counts'] == {name: 1 for name in m.NUMBERS}
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    encoded = m.canonical(result)
    for secret in (KEY, 'PRIVATE-POSITION', 'BBG000000001', 'US0378331005', '037833100',
            '2046251', 'SYNTHETIC PRIVATE HOLDING NAME', '1234567', '7654321.1234',
            '0.1234567890123456', hashlib.sha256(body).hexdigest(), 'SYNTHETIC-REQUEST-ID'):
        assert secret.encode() not in encoded


@pytest.mark.parametrize('index', range(8))
def test_all_fmp_funds_emit_date_range_not_rows_or_daily_holdings(index):
    item = request('fmp', index); body = dates(); body[0]['symbol'] = item['fund']
    result = inspect(item, body)
    assert result['result_count'] == result['date_count'] == result['distinct_date_count'] == 2
    assert result['earliest_date'] == '2021-09-30' and result['latest_date'] == '2026-04-30'
    assert result['fmp_year_count'] == result['fmp_quarter_count'] == 2
    assert result['processed_date_count'] == 0 and result['next_page_present'] is False
    assert not any(result['identifier_presence_counts'].values())
    assert b'"quarter":' not in m.canonical(result) and b'"year":' not in m.canonical(result)
    assert all(result[key] is False for key in m.FALSE_FLAGS)


def test_empty_results_are_valid_empty_samples_and_disclosure_metadata():
    massive_summary = inspect(request(), {'status': 'OK', 'results': [], 'count': 0})
    fmp_summary = inspect(request('fmp'), [])
    for result in (massive_summary, fmp_summary):
        assert result['result_count'] == result['date_count'] == result['distinct_date_count'] == 0
        assert result['earliest_date'] is result['latest_date'] is None
        assert result['full_window_coverage_proven'] is False


def test_next_url_presence_is_not_a_query_or_persisted_URL():
    body = massive(); body['next_url'] = 'https://UNTRUSTED.invalid/do-not-contact?cursor=PRIVATE'
    result = inspect(request(), body)
    assert result['next_page_present'] is True
    assert b'UNTRUSTED' not in m.canonical(result) and b'cursor' not in m.canonical(result)
    assert result['pagination_followed'] is False


@pytest.mark.parametrize('value', [1, 123456789, 'SYNTHETIC-REQUEST-ID', None, ''])
def test_request_id_accepts_both_official_documented_variants_without_emitting_it(value):
    body = massive(); body['request_id'] = value
    result = inspect(request(), body)
    assert result['result_count'] == 1
    assert 'request_id' not in result
    assert result == inspect(request(), {key: item for key, item in body.items() if key != 'request_id'})


@pytest.mark.parametrize('value', [True, False, 0, -1, 1.5, [], {}])
def test_request_id_does_not_treat_bool_or_other_arbitrary_values_as_positive_integer(value):
    body = massive(); body['request_id'] = value
    refuse('schema', lambda: inspect(request(), body))


@pytest.mark.parametrize('field', m.IDENTIFIERS)
@pytest.mark.parametrize('value', [None, ''])
def test_unavailable_optional_identifier_counts_zero_without_dropping_dated_row(field, value):
    body = massive(); body['results'][0][field] = value
    result = inspect(request(), body)
    assert result['result_count'] == result['date_count'] == 1
    assert result['identifier_presence_counts'][field] == 0
    assert result['point_in_time_proven'] is result['permanent_security_master_proven'] is False


@pytest.mark.parametrize('field', m.MASSIVE_TEXT)
@pytest.mark.parametrize('value', [None, ''])
def test_unavailable_optional_descriptive_text_does_not_destroy_dated_sample(field, value):
    body = massive(); body['results'][0][field] = value
    assert inspect(request(), body)['result_count'] == 1


@pytest.mark.parametrize('field', m.NUMBERS)
def test_null_optional_numeric_field_counts_zero_without_dropping_row(field):
    body = massive(); body['results'][0][field] = None
    result = inspect(request(), body)
    assert result['result_count'] == 1 and result['numeric_presence_counts'][field] == 0


@pytest.mark.parametrize('value', [None, ''])
def test_unavailable_processed_date_and_continuation_hint_are_not_availability_or_page_claims(value):
    body = massive(); body['results'][0]['processed_date'] = value; body['next_url'] = value
    result = inspect(request(), body)
    assert result['result_count'] == 1 and result['processed_date_count'] == 0
    assert result['earliest_processed_date'] is result['latest_processed_date'] is None
    assert result['next_page_present'] is False
    assert result['publication_time_proven'] is False


def test_all_optional_nulls_keep_exact_fund_date_sample_without_inventing_identifiers_or_weights():
    body = massive(); row = body['results'][0]
    for field in m.MASSIVE_FIELDS - {'composite_ticker', 'effective_date'}: row[field] = None
    for field in ('count', 'request_id', 'next_url'): body[field] = None
    result = inspect(request(), body)
    assert result['result_count'] == result['date_count'] == 1
    assert result['processed_date_count'] == 0 and result['next_page_present'] is False
    assert not any(result['identifier_presence_counts'].values())
    assert not any(result['numeric_presence_counts'].values())
    assert all(result[name] is False for name in m.FALSE_FLAGS)


@pytest.mark.parametrize('field', ['status', 'results', 'composite_ticker', 'effective_date'])
def test_required_exact_fund_date_status_and_result_list_still_refuse_null(field):
    body = massive()
    if field in {'status', 'results'}: body[field] = None
    else: body['results'][0][field] = None
    refuse('date' if field == 'effective_date' else 'schema', lambda: inspect(request(), body))


def test_duplicate_fmp_dates_remain_counts_without_dedup_or_quarter_inference():
    body = dates(); body.append(dict(body[0], year=2025, quarter=4))
    result = inspect(request('fmp'), body)
    assert result['result_count'] == 3 and result['distinct_date_count'] == 2
    assert result['fmp_year_count'] == result['fmp_quarter_count'] == 3


@pytest.mark.parametrize('fault', ['ordinal_bool', 'provider', 'fund', 'date', 'query', 'path', 'extra', 'provider_ordinal'])
def test_any_request_change_refuses_before_response_parse(fault):
    item = request()
    if fault == 'ordinal_bool': item['ordinal'] = False
    elif fault == 'query': item['query']['limit'] = '2'
    elif fault == 'extra': item['authorized'] = True
    elif fault == 'provider_ordinal': item['provider_ordinal'] = False
    else: item[{'date': 'effective_date'}.get(fault, fault)] = 'UNFROZEN'
    refuse('request', lambda: m.parse_response(item, b'not JSON', credential=KEY))


@pytest.mark.parametrize('credential', [None, True, b'x' * 32, '', 'short', 'x' * 513, 'x' * 8 + '\n', 'has space'])
def test_closed_credential_shape_never_includes_supplied_value_in_error(credential):
    refuse('credential', lambda: m.parse_response(request(), raw(massive()), credential=credential))


@pytest.mark.parametrize('variant', ['raw', 'standard_escape', 'all_unicode', 'mixed_unicode', 'key', 'nested'])
def test_raw_and_JSON_escaped_echo_refuse_before_schema(variant):
    key = 'SYNTHETIC-"SLASH\\TOKEN'
    if variant == 'raw': body = b'not JSON ' + key.encode()
    elif variant == 'standard_escape': body = raw({'error': key})
    elif variant == 'all_unicode': body = ('{"error":"' + ''.join('\\u%04x' % ord(c) for c in key) + '"}').encode()
    elif variant == 'mixed_unicode':
        body = ('{"error":"' + ''.join('\\u%04x' % ord(c) if index % 2 == 0
            else json.dumps(c)[1:-1] for index, c in enumerate(key)) + '"}').encode()
    elif variant == 'key': body = raw({key: 'failure'})
    else: body = raw({'other': [{'nested': key}]})
    with pytest.raises(m.Refused) as error: m.parse_response(request(), body, credential=key)
    assert m.finite(error.value) == 'credential_echo' and key not in str(error.value)


@pytest.mark.parametrize('body,code', [(b'', 'response_bound'), (b'x' * (m.MAX_BODY + 1), 'response_bound'),
    (b'{} {}', 'json'), (b'{"status":"OK","status":"OK","results":[]}', 'json'),
    (b'{"status":"OK","results":[],"count":NaN}', 'json'),
    (b'{"status":"OK","results":[],"count":Infinity}', 'json'),
    (b'\xff', 'json'), (b'[{]', 'json'), (b'{}\x00', 'json'),
    (b'[' * 25 + b'0' + b']' * 25, 'depth')])
def test_bounded_strict_JSON_and_preparse_depth(body, code):
    refuse(code, lambda: m.parse_response(request(), body, credential=KEY))


def test_braces_and_backslashes_in_string_do_not_fabricate_depth():
    body = massive(); body['results'][0]['constituent_name'] = '[{' * 100 + '\\"' + '}]' * 100
    assert inspect(request(), body)['result_count'] == 1


@pytest.mark.parametrize('fault', ['missing_results', 'bad_status', 'extra_top', 'count_bool', 'count_mismatch',
    'request_id_bool', 'row_extra', 'fund', 'row_bool', 'two_rows', 'rank_bool'])
def test_massive_closed_schema_and_limit_one(fault):
    body = massive()
    if fault == 'missing_results': body.pop('results')
    elif fault == 'bad_status': body['status'] = 'ERROR'
    elif fault == 'extra_top': body['current_only'] = True
    elif fault == 'count_bool': body['count'] = True
    elif fault == 'count_mismatch': body['count'] = 0
    elif fault == 'request_id_bool': body['request_id'] = True
    elif fault == 'row_extra': body['results'][0]['unrecognized'] = 1
    elif fault == 'fund': body['results'][0]['composite_ticker'] = 'OTHER'
    elif fault == 'row_bool': body['results'][0] = True
    elif fault == 'rank_bool': body['results'][0]['constituent_rank'] = True
    else: body['results'].append(copy.deepcopy(body['results'][0]))
    refuse('row_cap' if fault == 'two_rows' else 'schema', lambda: inspect(request(), body))


@pytest.mark.parametrize('field', ['effective_date', 'processed_date'])
@pytest.mark.parametrize('value', ['2026-02-30', '2026-1-01', '2026-10-12T00:00:00', True])
def test_massive_date_shape_and_real_calendar(field, value):
    body = massive(); body['results'][0][field] = value
    refuse('date', lambda: inspect(request(), body))


def test_valid_but_wrong_effective_date_is_not_current_holdings_substitution():
    body = massive(); body['results'][0]['effective_date'] = '2026-10-12'
    refuse('date', lambda: inspect(request(), body))


@pytest.mark.parametrize('field,value', [('figi', 'BBG1'), ('isin', 'US037833100'), ('us_code', True),
    ('sedol', 'bad'), ('constituent_ticker', 'NAME WITH SPACE')])
def test_optional_identifiers_have_strict_shapes_without_identity_admission(field, value):
    body = massive(); body['results'][0][field] = value
    refuse('identifier', lambda: inspect(request(), body))


@pytest.mark.parametrize('field', m.NUMBERS)
@pytest.mark.parametrize('value', [True, '123.5', {'value': 1}])
def test_optional_money_or_share_fields_are_numbers_not_bools_or_strings(field, value):
    body = massive(); body['results'][0][field] = value
    refuse('number', lambda: inspect(request(), body))


def test_decimal_validation_is_context_independent_and_does_not_round_prices_or_weights():
    body = raw(massive()).replace(b'0.1234567890123456', b'-0.123456789012345678901234567890')
    with localcontext() as context:
        context.prec = 2
        assert m.parse_response(request(), body, credential=KEY)['numeric_presence_counts']['weight'] == 1
    for number in (b'1e1001', b'1e-1001', b'1' * 129):
        refuse('number', lambda: m.parse_response(request(),
            raw(massive()).replace(b'0.1234567890123456', number), credential=KEY))


@pytest.mark.parametrize('fault', ['not_list', 'row_extra', 'missing_date', 'wrong_symbol', 'year_bool',
    'year_string', 'quarter_bool', 'quarter_zero', 'quarter_five', 'invalid_date', 'too_many'])
def test_FMP_dates_are_closed_validated_metadata(fault):
    body = dates()
    if fault == 'not_list': body = {'dates': body}
    elif fault == 'row_extra': body[0]['holdings'] = ['PRIVATE']
    elif fault == 'missing_date': body[0].pop('date')
    elif fault == 'wrong_symbol': body[0]['symbol'] = 'OTHER'
    elif fault == 'year_bool': body[0]['year'] = True
    elif fault == 'year_string': body[0]['year'] = '2026'
    elif fault == 'quarter_bool': body[0]['quarter'] = True
    elif fault == 'quarter_zero': body[0]['quarter'] = 0
    elif fault == 'quarter_five': body[0]['quarter'] = 5
    elif fault == 'invalid_date': body[0]['date'] = '2026-02-30'
    else: body = [body[0]] * 513
    refuse('row_cap' if fault == 'too_many' else 'date' if fault == 'invalid_date' else 'schema',
        lambda: inspect(request('fmp'), body))


@pytest.mark.parametrize('provider', m.PROVIDERS)
@pytest.mark.parametrize('fault', ['extra', 'body_hash', 'bool_count', 'false_flag', 'provider',
    'date_count', 'distinct_zero', 'same_date_two_distinct', 'different_dates_one_distinct',
    'identifier_count', 'numeric_count', 'provider_specific_count', 'next_url_string'])
def test_public_summary_closed_schema_and_crossfield_invariants(provider, fault):
    item = request(provider); result = inspect(item, massive() if provider == 'massive' else dates())
    if fault == 'extra': result['raw_rows'] = []
    elif fault == 'body_hash': result['response_sha256'] = 'f' * 64
    elif fault == 'bool_count': result['result_count'] = True
    elif fault == 'false_flag': result['daily_holdings_proven'] = True
    elif fault == 'provider': result['provider'] = 'OTHER'
    elif fault == 'date_count': result['date_count'] = 0
    elif fault == 'distinct_zero': result['distinct_date_count'] = 0
    elif fault == 'same_date_two_distinct':
        result['result_count'] = result['date_count'] = result['distinct_date_count'] = 2
        result['earliest_date'] = result['latest_date'] = '2021-09-30'
        if provider == 'fmp': result['fmp_year_count'] = result['fmp_quarter_count'] = 2
    elif fault == 'different_dates_one_distinct':
        result['distinct_date_count'] = 1
        result['earliest_date'], result['latest_date'] = '2021-09-30', '2026-04-30'
    elif fault == 'identifier_count': result['identifier_presence_counts']['figi'] = 99
    elif fault == 'numeric_count': result['numeric_presence_counts']['weight'] = True
    elif fault == 'provider_specific_count':
        result['fmp_year_count' if provider == 'massive' else 'processed_date_count'] = 1
    else: result['next_page_present'] = 'https://not-persisted.invalid/'
    refuse('output', lambda: m.validate_summary(item, result))


def test_validator_returns_defensive_copy_and_profile_is_fresh():
    item = request(); result = inspect(item, massive()); validated = m.validate_summary(item, result)
    validated['identifier_presence_counts']['figi'] = 0
    assert result['identifier_presence_counts']['figi'] == 1
    profile = m.profile_record(); profile['request_plan'][0]['query']['limit'] = '100'
    assert m.request_plan()[0]['query']['limit'] == '1'
    assert m.profile_record()['request_plan'][0]['query']['limit'] == '1'


def test_module_has_only_stdlib_imports_and_no_IO_or_dispatch_entrypoint():
    tree = ast.parse(Path(m.__file__).read_bytes())
    imports = {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {name.name.split('.')[0] for node in ast.walk(tree)
        if isinstance(node, ast.Import) for name in node.names}
    assert imports <= {'datetime', 'decimal', 'json', 're'}
    calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not calls.intersection({'open', 'read_bytes', 'write_bytes', 'Popen', 'run',
        'urlopen', 'request', 'urlencode', 'main', 'produce', 'find_generic_password'})
    assert not any(isinstance(node, ast.Name) and node.id in {'requests', 'socket', 'subprocess', 'os'}
        for node in ast.walk(tree))
    assert all(m.profile_record()[name] is False for name in m.FALSE_FLAGS)


def test_error_labels_never_forward_unknown_provider_text_or_subclass_payload():
    class PrivateError(m.Refused): pass
    assert m.finite(PrivateError(KEY)) == m.finite(ValueError(KEY)) == 'unknown'
    assert m.finite(m.Refused(KEY)) == 'unknown'
