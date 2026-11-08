"""Synthetic one-use and publication-order checks; never production inputs."""
from contextlib import ExitStack
import copy
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r343_legacy_six as m


def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64,
        profile_sha256=m.sha(m.canonical(m.profile_record())))


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert caught.value.args == (code,)


def summary(value):
    m.require(value == {'synthetic_only': True}, 'output')
    return value


def envelope(a):
    result = {'schema': m.SCHEMA + '-result', 'binding': m.binding(a),
        'offline_submission_package_prepared': True, 'attempt_consumed': True,
        'private_pin': {'byte_count': 123, 'sha256': 'c' * 64},
        'source_summary': {'synthetic_only': True},
        'input_package_sha256': '411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad',
        'input_lineage_sha256': 'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9',
        'source_guard_returned': True, 'input_guard_returned': True,
        'actual_upload_object_count': 6, **m.FLAGS}
    return {'binding': m.binding(a), 'result': result,
        'report_pin': m.pin(m.canonical({'binding': m.binding(a), 'result': result}))}


def repin(value):
    value['report_pin'] = m.pin(m.canonical({key: value[key] for key in ('binding', 'result')}))
    return m.canonical(value) + b'\n'


def test_original_stdout_and_actual_exit_validate_with_closed_summary():
    a = args()
    result = m.validate_output(repin(envelope(a)), 0, a, summary_validator=summary)
    assert result['accepted'] is True and result['output_envelope_validated'] is True
    assert 'not_independent_private_file_attestation' in result['qualification']


@pytest.mark.parametrize('exit_code', [True, False, 2, -1, None, '0'])
def test_nonzero_unknown_or_bool_exit_never_accepts_report(exit_code):
    a = args()
    refused('output', lambda: m.validate_output(repin(envelope(a)), exit_code, a, summary_validator=summary))


@pytest.mark.parametrize('key', list(m.FLAGS))
def test_rehashed_readiness_or_contact_claim_is_rejected(key):
    a = args(); value = envelope(a); value['result'][key] = True
    refused('output', lambda: m.validate_output(repin(value), 0, a, summary_validator=summary))


@pytest.mark.parametrize('key', ['source_guard_returned', 'input_guard_returned',
    'attempt_consumed', 'offline_submission_package_prepared'])
def test_guard_return_and_consumption_fields_are_strict(key):
    a = args(); value = envelope(a); value['result'][key] = 1
    refused('output', lambda: m.validate_output(repin(value), 0, a, summary_validator=summary))


@pytest.mark.parametrize('fault', ['empty_summary', 'source_summary_changed', 'private_pin',
    'upload_bool', 'upload_zero', 'package', 'lineage', 'binding', 'extra'])
def test_rehashed_result_forgery_reaches_targeted_guards(fault):
    a = args(); value = envelope(a); result = value['result']
    if fault == 'empty_summary': result['source_summary'] = {}
    elif fault == 'source_summary_changed': result['source_summary']['synthetic_only'] = False
    elif fault == 'private_pin': result['private_pin']['sha256'] = 'g' * 64
    elif fault == 'upload_bool': result['actual_upload_object_count'] = True
    elif fault == 'upload_zero': result['actual_upload_object_count'] = 0
    elif fault == 'package': result['input_package_sha256'] = 'd' * 64
    elif fault == 'lineage': result['input_lineage_sha256'] = 'd' * 64
    elif fault == 'binding': result['binding']['expected_head'] = 'd' * 40
    else: result['extra'] = None
    refused('output', lambda: m.validate_output(repin(value), 0, a, summary_validator=summary))


@pytest.mark.parametrize('raw', [b'{}\n\n', b'{}\ntrailing', b' { }\n', b'{"x":1,"x":1}\n', b'{"x":NaN}\n'])
def test_malformed_ambiguous_or_noncanonical_stdout_refuses(raw):
    refused('output', lambda: m.validate_output(raw, 0, args(), summary_validator=summary))


@pytest.mark.parametrize('field', ['expected_head', 'caller_sha256', 'profile_sha256'])
def test_bindings_refuse_wrong_types_or_hashes(field):
    a = args(); setattr(a, field, False)
    refused('arguments', lambda: m.binding(a))


class Security:
    @staticmethod
    def snapshot(fd):
        return ('synthetic-empty-native-security', os.fstat(fd).st_uid)


@pytest.fixture
def location(tmp_path, monkeypatch):
    root = tmp_path / 'synthetic-repository'
    root.mkdir(mode=0o755)
    (root / 'artifacts').mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', root / 'artifacts' / 'only-this-protocol' / 'A')
    monkeypatch.setattr(m, 'CLAIM_STATE', 'unallocated')
    return root


def test_real_store_claims_exclusively_retains_original_descriptors_and_private_modes(location):
    with m.Store(Security) as store:
        assert m.CLAIM_STATE == 'allocated_unknown'
        store.write('claim.json', b'{"synthetic":true}')
        assert m.CLAIM_STATE == 'consumed'
        store.write('preparation-started.json', b'{}')
        store.write('submission-private.json', b'{"nonce":"synthetic"}')
        store.write('report.json', b'{}')
        store.verify()
        assert all((m.CONTROL / name).stat().st_mode & 0o777 == 0o600 for name in m.Store.NAMES
            if (m.CONTROL / name).exists())
    refused('claim_spent', lambda: m.Store(Security).__enter__())
    assert m.CLAIM_STATE == 'consumed_or_unknown'
    assert (m.CONTROL / 'claim.json').read_bytes() == b'{"synthetic":true}'


def test_real_store_refuses_symlink_ancestor_without_following_it(location):
    elsewhere = location / 'synthetic-elsewhere'; elsewhere.mkdir(mode=0o700)
    m.CONTROL.parent.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(OSError):
        m.Store(Security).__enter__()
    assert list(elsewhere.iterdir()) == []


def test_real_store_detects_named_leaf_swap(location):
    with pytest.raises(m.Refused, match='control'):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'claim.json').rename(m.CONTROL / 'retained-synthetic-old')
            (m.CONTROL / 'claim.json').write_bytes(b'{}')
            store.verify()


def test_real_code_guard_rejects_changed_bytes_under_same_metadata_shape(tmp_path):
    path = tmp_path / 'source.py'; path.write_bytes(b'a=1\n')
    with pytest.raises(m.Refused, match='source_changed'):
        with m.HeldSource(path, m.pin(b'a=1\n'), time.monotonic() + 100) as held:
            path.write_bytes(b'a=2\n')
            held.verify()


@pytest.fixture
def preparation(monkeypatch):
    log = []; state = NS(exit_failure=None, raw_files={})
    a = args()
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    class MemoryStore:
        def __init__(self, security): pass
        def __enter__(self): log.append('store-enter'); return self
        def __exit__(self, *_): log.append('store-return')
        def verify(self): log.append('store-verify')
        def write(self, name, raw):
            log.append(name); state.raw_files[name] = raw; return m.pin(raw)
    class Fresh:
        _wrapped = object(); _package = object()
        axis = ('synthetic-axis',); bindings = ('synthetic-bindings',)
        def __init__(self, deadline): pass
        def __enter__(self): log.append('input-enter'); return self
        def __exit__(self, *_):
            log.append('input-return')
            if state.exit_failure == 'input': raise m.Refused('input')
        def _libraries(self): log.append('genuine-check')
        def receipt(self): return {'synthetic_receipt': True}
    class Descriptor:
        def __init__(self, activation): self.activation = activation
        @property
        def byte_count(self): return 2
        @property
        def content_sha256(self): return m.sha(b'{}')
        def to_record(self): return {'activation_manifest': self.activation}
    def build(*args, **kwargs):
        log.append('build')
        return {'bundle': {'synthetic_only': True}, 'summary': {'synthetic_only': True}}
    def bootstrap(stack, *args):
        def source_exit():
            log.append('sources-return')
            if state.exit_failure == 'source': raise m.Refused('source_changed')
        stack.callback(source_exit)
        return {'security': Security,
            'input': NS(GenuineInput=Fresh, PACKAGE_SHA256='p', LINEAGE_SHA256='l'),
            'projection': NS(HOST_SOURCE_PINS={'x.py': 'a'*64}, MAX_SECONDS=600, prepare=build, validate_summary=summary),
            'compact': NS(iter_accepted_risk_preliminary_upload_objects=lambda _: iter([
                (Descriptor(False), b'{}'), (Descriptor(True), b'{}')])),
            'raws': {'research/analyst_revisions_v2_qc/x.py': b'x=1',
                'research/analyst_revisions_v2_qc/legacy_six_october_reporting.py': b'x=1'},
            'verify': lambda: log.append('sources-verify')}
    monkeypatch.setattr(m, 'Store', MemoryStore)
    monkeypatch.setattr(m, 'bootstrap', bootstrap)
    return NS(log=log, state=state, args=a)


def test_real_orchestrator_waits_for_both_guard_returns_before_any_package_publication(preparation):
    result = m.prepare(preparation.args, time.monotonic() + 800)
    log = preparation.log
    assert log.index('claim.json') < log.index('preparation-started.json') < log.index('input-enter')
    assert log.index('input-return') < log.index('sources-return') < log.index('submission-private.json')
    assert log.index('submission-private.json') < log.index('report.json') < log.index('store-return')
    assert result['result']['source_guard_returned'] is result['result']['input_guard_returned'] is True


def test_real_publication_blinds_private_package_with_fresh_claim_bound_nonce(preparation):
    result = m.prepare(preparation.args, time.monotonic() + 800)
    private = m.loads(preparation.state.raw_files['submission-private.json'], m.MAX_PRIVATE)
    nonce = private['private_transport_nonce']
    assert type(nonce) is str and len(nonce) == 64 and all(c in '0123456789abcdef' for c in nonce)
    assert private['claim_pin'] == m.pin(preparation.state.raw_files['claim.json'])
    assert nonce.encode() not in m.canonical(result)


@pytest.mark.parametrize('which', ['input', 'source'])
def test_guard_return_refusal_never_publishes_a_package_or_success_report(preparation, which):
    preparation.state.exit_failure = which
    with pytest.raises(m.Refused):
        m.prepare(preparation.args, time.monotonic() + 800)
    assert 'claim.json' in preparation.log and 'preparation-started.json' in preparation.log
    assert 'submission-private.json' not in preparation.log and 'report.json' not in preparation.log


def test_native_policy_has_all_network_and_both_keychain_denials():
    profile = m.native_profile()
    assert '(deny network*)' in profile
    for path in ('/Volumes', '/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        assert '(deny file-read* file-write* (subpath "' + path + '"))' in profile
    assert '(deny process-exec (literal "/usr/bin/security"))' in profile


def test_cached_pinned_module_is_rejected_before_any_claim_or_import(monkeypatch):
    monkeypatch.delitem(sys.modules, 'scripts', raising=False)
    monkeypatch.setitem(sys.modules, 'synthetic_selected_module', NS(synthetic=True))
    refused('environment', lambda: m.require_fresh_modules({'synthetic_selected_module': 'synthetic.py'}))


@pytest.mark.parametrize('name', ['input', 'projection'])
@pytest.mark.parametrize('code', ['deadline', 'source_pin'])
def test_dependency_finite_code_and_deadline_are_preserved(name, code, monkeypatch):
    class DependencyRefused(ValueError): pass
    module = NS(Refused=DependencyRefused, FINITE={'deadline', 'source_pin'})
    roles = {'input': NS(Refused=type('Other', (ValueError,), {}), FINITE=set()),
        'projection': NS(Refused=type('Other2', (ValueError,), {}), FINITE=set())}
    roles[name] = module
    monkeypatch.setattr(m, 'DEPENDENCY_FAILURE', None)
    refused('deadline' if code == 'deadline' else 'input',
        lambda: m.dependency_problem(DependencyRefused(code), roles, 'input'))
    assert m.DEPENDENCY_FAILURE == {'module': name, 'code': code}


def test_callers_own_deadline_is_not_relabelled_as_upload_stage():
    refused('deadline', lambda: m.dependency_problem(m.Refused('deadline'), {}, 'upload'))


def test_no_dispatch_fence_or_cloud_namespace_was_imported():
    assert 'assistant.dispatch_fence' not in sys.modules
    assert not any(name.startswith(('QuantConnect', 'quantconnect', 'qc.client')) for name in sys.modules)


def test_complete_sanitized_environment_and_exact_current_uid_cf_value_are_accepted():
    environment = m.safe_env()
    assert m.validate_environment(environment) == environment
    environment['__CF_USER_TEXT_ENCODING'] = f'0x{os.getuid():X}:0x0:0x0'
    assert m.validate_environment(environment) == m.safe_env()


@pytest.mark.parametrize('key', list(m.safe_env()))
def test_absent_configured_environment_key_refuses_before_claim(key):
    environment = m.safe_env(); environment.pop(key)
    refused('environment', lambda: m.validate_environment(environment))


@pytest.mark.parametrize('change', ['wrong_uid', 'wrong_format', 'extra_secret', 'external_tmp'])
def test_environment_cannot_copy_untrusted_inheritance(change):
    environment = m.safe_env()
    if change == 'wrong_uid': environment['__CF_USER_TEXT_ENCODING'] = f'0x{os.getuid()+1:X}:0x0:0x0'
    elif change == 'wrong_format': environment['__CF_USER_TEXT_ENCODING'] = f'{os.getuid():X}:0:0'
    elif change == 'extra_secret': environment['SYNTHETIC_CREDENTIAL'] = 'synthetic-not-a-key'
    else: environment['TMPDIR'] = '/synthetic-outside-root'
    refused('environment', lambda: m.validate_environment(environment))


def native_security_fixture(names=b'com.apple.synthetic\0', value=b'synthetic-opaque-metadata'):
    state = NS(names=names, value=value, acl_calls=0)
    class Native:
        def flistxattr(self, fd, buffer, maximum, options):
            ctypes.memmove(buffer, state.names, min(len(state.names), maximum))
            return len(state.names)
        def fgetxattr(self, fd, name, buffer, maximum, position, options):
            ctypes.memmove(buffer, state.value, min(len(state.value), maximum))
            return len(state.value)
    def acl(native, fd):
        state.acl_calls += 1
    return state, NS(_native=lambda: Native(), _require_empty_acl=acl, XATTR_SHOWCOMPRESSION=32)


def test_public_code_observes_every_bounded_xattr_and_binds_changes(tmp_path):
    path = tmp_path / 'synthetic-source.py'; path.write_bytes(b'x=1\n')
    state, security = native_security_fixture()
    with path.open('rb') as source:
        initial = m.public_source_security(source.fileno(), security)
        state.value = b'changed-synthetic-opaque-metadata'
        assert m.public_source_security(source.fileno(), security) != initial
        state.value = b'synthetic-opaque-metadata'; state.names = b'other.synthetic\0'
        assert m.public_source_security(source.fileno(), security) != initial
    assert state.acl_calls == 6


@pytest.mark.parametrize('names', [b'no-terminator', b'a\0a\0', b'\0', b'a'*256+b'\0',
    b''.join(str(i).encode()+b'\0' for i in range(33)), b'a'*8193])
def test_public_source_xattr_inventory_is_bounded_and_exact(tmp_path, names):
    path = tmp_path / 'synthetic-source.py'; path.write_bytes(b'x=1\n')
    _, security = native_security_fixture(names=names)
    with path.open('rb') as source:
        refused('source_pin', lambda: m.public_source_security(source.fileno(), security))


def test_public_metadata_observation_does_not_change_private_evidence_allowlist():
    from scripts import arv2_relocation_security
    assert arv2_relocation_security.ALLOWED_XATTRS == frozenset({b'com.apple.provenance'})


def test_new_store_normal_return_with_real_native_security_on_synthetic_files(location):
    from scripts import arv2_relocation_security
    with m.Store(arv2_relocation_security) as store:
        for name in ('claim.json', 'preparation-started.json', 'submission-private.json', 'report.json'):
            observed = store.write(name, m.canonical({'synthetic_only': name}))
            assert observed == m.pin(m.canonical({'synthetic_only': name}))
        store.verify()
    assert (m.CONTROL / 'report.json').is_file()
