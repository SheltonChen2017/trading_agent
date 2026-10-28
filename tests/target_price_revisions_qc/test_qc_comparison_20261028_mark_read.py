"""Pure synthetic witness/pointer only; no QC, licensed or operator bytes."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261028_mark_read as m

ROOT = Path(__file__).resolve().parents[2]


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def fixture(*, observed_delta=-60, algorithm_delta=60, day='2021-01-04', microseconds=0):
    expected = datetime.fromisoformat(day+'T21:00:00+00:00').replace(microsecond=microseconds)
    algorithm = expected+timedelta(seconds=algorithm_delta)
    observed = expected+timedelta(seconds=observed_delta)
    predicates = {'observed_equals_expected': observed == expected,
        'expected_date_equals_algorithm': expected.date() == algorithm.date(),
        'observed_date_equals_session': observed.astimezone(m.NY).date() == algorithm.astimezone(m.NY).date(),
        'observed_relation': 'before' if observed < expected else 'after' if observed > expected else 'equal'}
    body = {'schema': 'tpr-cmp28-private-mark-refusal-v1', 'study_id': m.STUDY,
        'candidate_id': m.STUDY+'-OFF', 'arm': 'cap_off', 'operation_id': 'TPR-CMP28-OFF-SYNTHETIC003',
        'attempt': 3, 'config_sha256': 'c'*64, 'source_template_closure_sha256': 'd'*64,
        'policy_sha256': 'e'*64, 'calendar_sha256': 'f'*64, 'project_id': m.PROJECT,
        'job_id': '1'*32, 'security_id': 'SYNTHETIC-PRIVATE-SID', 'data_type': 'trade_bar',
        'algorithm_utc': algorithm.isoformat(), 'algorithm_local': algorithm.astimezone(m.NY).isoformat(),
        'expected_close_utc': expected.isoformat(), 'expected_close_local': expected.astimezone(m.NY).isoformat(),
        'observed_end_utc': observed.isoformat(), 'observed_end_local': observed.astimezone(m.NY).isoformat(),
        'predicates': predicates, 'guard_unchanged': True, 'source_inputs_admitted': False,
        'strategy_accepted': False, 'canonical_admission': False}
    return body, *bind(body)


def bind(body, raw=None):
    raw = wire(body) if raw is None else raw
    binding = m.prepare_binding(operation_id='TPR-CMP28-MARK-SYNTHETIC001', git_head='a'*40,
        source_hashes={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (m.MODULE, m.PRODUCER)},
        off_operation_id='TPR-CMP28-OFF-SYNTHETIC003', attempt=3, job_id='1'*32,
        config_sha256='c'*64, source_template_closure_sha256='d'*64, policy_sha256='e'*64,
        calendar_sha256='f'*64, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_bytes=len(raw))
    pointer = {'schema': 'tpr-cmp28-mark-refusal-pointer-v1', 'status': 'verified', 'key': binding['key'],
        'bytes': len(raw), 'expected_sha256': binding['expected_sha256'], 'verified_sha256': binding['expected_sha256'],
        'readback_verified': True, 'data_type': 'trade_bar', 'predicates': dict(body['predicates'])}
    return raw, binding, pointer


@pytest.mark.parametrize('delta,relation', [(-60, 'before'), (0, 'equal'), (60, 'after')])
def test_exact_own_witness_projects_hashed_identity_and_relative_clocks_only(delta, relation):
    body, raw, binding, pointer = fixture(observed_delta=delta, microseconds=123456)
    result = m.project_witness(raw, binding=binding, pointer=pointer)
    assert result['predicates']['observed_relation'] == relation
    assert result['predicates']['observed_date_equals_session'] is True
    assert result['observed_minus_expected_microseconds'] == delta*1000000
    assert result['algorithm_minus_expected_microseconds'] == 60000000
    assert result['observed_minus_algorithm_microseconds'] == (delta-60)*1000000
    assert result['security_id_sha256'] == hashlib.sha256(body['security_id'].encode()).hexdigest()
    assert result['prefix_sha256'] == hashlib.sha256((binding['key'].rsplit('/', 1)[0]+'/').encode()).hexdigest()
    assert result['native_effects_performed'] == result['private_reads_performed'] == 0
    assert result['native_custody_independently_proven'] is result['source_inputs_admitted'] is False
    assert result['strategy_accepted'] is result['canonical_admission'] is False
    public = json.dumps(result)
    for forbidden in (body['security_id'], body['algorithm_utc'], body['algorithm_local'],
            body['observed_end_utc'], body['observed_end_local'], body['expected_close_utc'], binding['key']):
        assert forbidden not in public


def test_cross_session_and_utc_date_relationships_are_computed_not_assumed():
    _, raw, binding, pointer = fixture(observed_delta=-86400, algorithm_delta=86400)
    result = m.project_witness(raw, binding=binding, pointer=pointer)
    assert result['predicates']['observed_date_equals_session'] is False
    assert result['predicates']['expected_date_equals_algorithm'] is False


@pytest.mark.parametrize('day,offset', [('2021-01-04', '-05:00'), ('2021-07-06', '-04:00')])
def test_native_local_clock_pair_uses_actual_new_york_dst_mapping(day, offset):
    body, raw, binding, pointer = fixture(day=day)
    assert body['expected_close_local'].endswith(offset)
    assert m.project_witness(raw, binding=binding, pointer=pointer)['predicates']['observed_date_equals_session'] is True


@pytest.mark.parametrize('field,value', [('project_id', 1), ('job_id', '2'*32), ('attempt', True),
    ('attempt', 4), ('operation_id', 'TPR-CMP28-OFF-OTHER'), ('config_sha256', 'b'*64),
    ('source_template_closure_sha256', 'b'*64), ('calendar_sha256', 'b'*64), ('policy_sha256', 'b'*64),
    ('candidate_id', m.STUDY+'-ON'), ('study_id', 'FOREIGN'), ('arm', 'pure_tpr'), ('data_type', 'quote_bar'),
    ('guard_unchanged', False), ('source_inputs_admitted', 0), ('strategy_accepted', True), ('canonical_admission', True)])
def test_body_rejects_foreign_parent_job_config_or_false_acceptance_claim(field, value):
    body, _, _, _ = fixture();body[field] = value
    raw, binding, pointer = bind(body)
    with pytest.raises(m.MarkReadRefusal, match='^exact private OFF mark witness refused$'):
        m.project_witness(raw, binding=binding, pointer=pointer)


@pytest.mark.parametrize('field,value', [('key', 'foreign/key/mark-refusal.json'), ('status', 'save_unconfirmed'),
    ('bytes', True), ('bytes', 1), ('expected_sha256', 'b'*64), ('verified_sha256', 'b'*64),
    ('readback_verified', 1), ('data_type', 'quote_bar')])
def test_pointer_requires_exact_verified_readback_and_descriptor(field, value):
    _, raw, binding, pointer = fixture();pointer[field] = value
    with pytest.raises(m.MarkReadRefusal):m.project_witness(raw, binding=binding, pointer=pointer)


@pytest.mark.parametrize('fault', ['pointer_predicate', 'body_predicate', 'local_clock', 'naive_clock',
    'utc_z_alias', 'duplicate_json', 'extra_price', 'extra_sid', 'bad_utf8', 'hash', 'size', 'max', 'sid_control', 'sid_surrogate'])
def test_bytes_schema_clock_and_predicate_refusals_do_not_expose_values(fault):
    body, raw, binding, pointer = fixture()
    if fault == 'pointer_predicate':pointer['predicates']['observed_date_equals_session'] = False
    elif fault == 'body_predicate':
        body['predicates']['observed_date_equals_session'] = False;raw, binding, pointer = bind(body)
    elif fault == 'local_clock':
        body['observed_end_local'] = '2021-01-04T15:59:00-04:00';raw, binding, pointer = bind(body)
    elif fault == 'naive_clock':
        body['observed_end_utc'] = '2021-01-04T20:59:00';raw, binding, pointer = bind(body)
    elif fault == 'utc_z_alias':
        body['observed_end_utc'] = '2021-01-04T20:59:00Z';raw, binding, pointer = bind(body)
    elif fault == 'duplicate_json':
        raw = raw[:-1]+b',"security_id":"SYNTHETIC-DUPLICATE"}';raw, binding, pointer = bind(body, raw)
    elif fault == 'extra_price':
        body['price'] = 'SYNTHETIC-PRIVATE-PRICE';raw, binding, pointer = bind(body)
    elif fault == 'extra_sid':pointer['security_id'] = 'SYNTHETIC-PRIVATE-SID'
    elif fault == 'bad_utf8':raw, binding, pointer = bind(body, b'\xff'+raw)
    elif fault == 'hash':raw += b' '
    elif fault == 'size':binding['expected_bytes'] += 1
    elif fault == 'max':raw = b' '*4097
    elif fault == 'sid_control':
        body['security_id'] = 'SYNTHETIC\nPRIVATE';raw, binding, pointer = bind(body)
    else:
        body['security_id'] = '\ud800';raw, binding, pointer = bind(body)
    with pytest.raises(m.MarkReadRefusal, match='^exact private OFF mark witness refused$'):
        m.project_witness(raw, binding=binding, pointer=pointer)


@pytest.mark.parametrize('fault', ['head', 'source', 'extra_source', 'zero_hash', 'job', 'attempt', 'max', 'effect_flag', 'extra_binding'])
def test_binding_is_closed_inert_and_never_authenticates_supplied_hashes(fault):
    _, _, binding, pointer = fixture()
    if fault == 'head':binding['git_head'] = 'x'*40
    elif fault == 'source':binding['source_hashes'].pop(m.PRODUCER)
    elif fault == 'extra_source':binding['source_hashes']['unrelated.py'] = 'b'*64
    elif fault == 'zero_hash':binding['expected_sha256'] = '0'*64
    elif fault == 'job':binding['job_id'] = '../other'
    elif fault == 'attempt':binding['attempt'] = True
    elif fault == 'max':binding['expected_bytes'] = 4097
    elif fault == 'effect_flag':binding['native_effects_authorized'] = 0
    else:binding['secret'] = 'SYNTHETIC'
    with pytest.raises(m.MarkReadRefusal):m.validate_pointer(pointer, binding=binding)


def test_plain_stdlib_import_closure_excludes_all_native_or_io_receivers():
    source = (ROOT/m.MODULE).read_bytes();tree = ast.parse(source)
    imports = {node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])}
    assert imports == {'__future__', 'datetime', 'hashlib', 'json', 're', 'zoneinfo'}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {'open', 'eval', 'exec', '__import__'} for node in ast.walk(tree))
    assert not hasattr(m, 'execute_plan') and not hasattr(m, '_native_upload')
    compile(tree, m.MODULE, 'exec')


def test_prepared_binding_is_an_independent_copy():
    _, _, binding, _ = fixture();copy = deepcopy(binding)
    copy['source_hashes'][m.MODULE] = 'b'*64
    assert binding['source_hashes'] != copy['source_hashes']
    assert binding['object_download_authorized'] is binding['native_effects_authorized'] is False
