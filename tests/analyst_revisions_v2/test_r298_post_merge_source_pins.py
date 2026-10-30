"""Closed prospective pin projection; native no-network/artifact isolation."""
import ast
import copy
import hashlib
import inspect
import subprocess

import pytest

from scripts import arv2_r298_post_merge_source_pins as m


@pytest.fixture(autouse=True)
def no_operational_entrypoints(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('old operation or credential lookup')
    for module in (m.frozen, m.frozen.frozen, m.frozen.previous):
        for name in ('run', 'observe', 'main', 'preflight'):
            monkeypatch.setattr(module, name, denied)
    monkeypatch.setattr(m.frozen.keychain, 'load_key', denied)
    monkeypatch.setattr(m.frozen.protocol, 'observe', denied)
    monkeypatch.setattr(m.frozen.protocol, '_fetch', denied)


def refused(code, callback):
    with pytest.raises(m.Refused) as error:
        callback()
    assert m.finite(error.value) == code


def baseline():
    return m.frozen.pins()


def test_exact_two_replacements_and_two_imports_do_not_modify_predecessor():
    original = baseline()
    before = copy.deepcopy(original)
    projected = m.pins()
    assert len(original) == 157 and len(projected) == 159
    assert {name for name in original if projected[name] != original[name]} == {
        name for name, _, _ in m.REPLACEMENTS}
    for name, old, new in m.REPLACEMENTS:
        assert original[name] == old and projected[name] == new
    for name, pin in m.ADDITIONS:
        assert name not in original and projected[name] == pin
    assert original == before == baseline()
    assert m.validate_projection(original, projected) == projected
    assert m.project_baseline(original) == projected


def test_original_baseline_digest_is_frozen_not_refreshed_from_disk():
    raw = m.canonical(baseline())
    assert not raw.endswith(b'\n')
    assert m.sha(raw) == 'd27eea9e5676ecc8b0cabaa3b8a12510d2d9b28248f799a41b73b8f51f682220'
    for name, old, _ in m.REPLACEMENTS:
        assert baseline()[name] == old


@pytest.mark.parametrize('fault', ['missing', 'extra', 'old_changed', 'third_changed',
    'key_type', 'pin_type', 'zero', 'parent_path', 'absolute', 'normalized_alias'])
def test_baseline_changes_cannot_silently_change_the_projection(fault):
    value = baseline()
    first, _, _ = m.REPLACEMENTS[0]
    unaffected = next(name for name in value if name not in {row[0] for row in m.REPLACEMENTS})
    code = 'baseline_shape'
    if fault == 'missing': del value[unaffected]
    elif fault == 'extra': value['scripts/new_source.py'] = 'a' * 64
    elif fault == 'old_changed': value[first] = 'a' * 64; code = 'baseline_pin'
    elif fault == 'third_changed': value[unaffected] = 'a' * 64; code = 'baseline_digest'
    elif fault == 'key_type': value[42] = value.pop(unaffected)
    elif fault == 'pin_type': value[unaffected] = True
    elif fault == 'zero': value[unaffected] = '0' * 64
    elif fault == 'parent_path': value['scripts/../wrong.py'] = value.pop(unaffected)
    elif fault == 'absolute': value['/scripts/wrong.py'] = value.pop(unaffected)
    else: value['scripts//wrong.py'] = value.pop(unaffected)
    refused(code, lambda: m.project_baseline(value))


@pytest.mark.parametrize('fault', ['missing', 'extra', 'unchanged', 'wrong_new', 'third',
    'wrong_addition', 'missing_addition', 'pin_type', 'zero'])
def test_projected_map_accepts_only_the_exact_registered_delta(fault):
    original, projected = baseline(), m.pins()
    first, old, _ = m.REPLACEMENTS[0]
    unaffected = next(name for name in original if name not in {row[0] for row in m.REPLACEMENTS})
    if fault == 'missing': del projected[unaffected]
    elif fault == 'extra': projected['scripts/new_source.py'] = 'a' * 64
    elif fault == 'unchanged': projected[first] = old
    elif fault == 'wrong_new': projected[first] = 'a' * 64
    elif fault == 'third': projected[unaffected] = 'a' * 64
    elif fault == 'wrong_addition': projected[m.ADDITIONS[0][0]] = 'a' * 64
    elif fault == 'missing_addition': del projected[m.ADDITIONS[0][0]]
    elif fault == 'pin_type': projected[unaffected] = True
    else: projected[unaffected] = '0' * 64
    refused('projection', lambda: m.validate_projection(original, projected))


@pytest.mark.parametrize('kind', [None, True, [], (), 'pins'])
def test_nonmaps_are_not_projection_inputs(kind):
    refused('baseline_shape', lambda: m.project_baseline(kind))
    refused('projection', lambda: m.validate_projection(baseline(), kind))


def test_public_manifest_has_exact_lineage_and_never_grants_operation_authority():
    value = m.profile_record()
    assert value['premerge_snapshot'] == '503168ac5caa1d2f0ee678f697c24dd552f0a818'
    assert value['reviewed_snapshot'] == 'e57d785fd813dfe8a17d11233ba47534ae42616a'
    assert value['byte_correction_commit'] == 'ad14e37973863c79393dca264483e5e1b9f2d829'
    assert value['preserving_merge_commit'] == '630e1abc2c78b87b625c161f6ca196eb2e4e531e'
    assert value['source_pins'] == m.pins() and value['source_pin_count'] == 159
    assert value['source_pins_canonical_NO_LF_sha256'] == m.sha(m.canonical(m.pins()))
    assert value['caller_must_authenticate_selected_actual_bytes_before_claim_or_contact'] is True
    assert value['caller_must_bind_own_source_profile_clean_HEAD_and_one_use_scope'] is True
    assert value['old_protocols_remain_spent'] is True
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert m.validate_manifest(value) == value


@pytest.mark.parametrize('fault', ['extra', 'schema', 'bool_count', 'count', 'digest', 'baseline_digest',
    'premerge', 'review', 'correction', 'merge', 'old_pin', 'new_pin', 'third_pin', 'addition',
    'replacement_path', 'replacement_order', 'addition_order', 'authority', 'freshness', 'flag_type',
    'no_claim_gate', 'spent_gate'])
def test_manifest_rejects_forgery_even_with_recomputed_pin_hash(fault):
    value = m.profile_record()
    if fault == 'extra': value['extra'] = True
    elif fault == 'schema': value['schema'] = 'alternate'
    elif fault == 'bool_count': value['source_pin_count'] = True
    elif fault == 'count': value['source_pin_count'] -= 1
    elif fault == 'digest': value['source_pins_canonical_NO_LF_sha256'] = '0' * 64
    elif fault == 'baseline_digest': value['baseline_canonical_NO_LF_sha256'] = '0' * 64
    elif fault in ('premerge', 'review', 'correction', 'merge'):
        key = {'premerge': 'premerge_snapshot', 'review': 'reviewed_snapshot',
            'correction': 'byte_correction_commit', 'merge': 'preserving_merge_commit'}[fault]
        value[key] = 'a' * 40
    elif fault == 'old_pin': value['allowed_replacements'][0]['old_sha256'] = 'a' * 64
    elif fault == 'new_pin': value['allowed_replacements'][0]['new_sha256'] = 'a' * 64
    elif fault == 'third_pin':
        key = next(name for name in value['source_pins'] if name not in {row[0] for row in m.REPLACEMENTS})
        value['source_pins'][key] = 'a' * 64
        value['source_pins_canonical_NO_LF_sha256'] = m.sha(m.canonical(value['source_pins']))
    elif fault == 'addition': value['explicit_import_additions'][0]['sha256'] = 'a' * 64
    elif fault == 'replacement_path': value['allowed_replacements'][0]['path'] = 'scripts/other.py'
    elif fault == 'replacement_order': value['allowed_replacements'].reverse()
    elif fault == 'addition_order': value['explicit_import_additions'].reverse()
    elif fault == 'authority': value['operational_authority_granted'] = True
    elif fault == 'freshness': value['automatic_pin_refresh'] = True
    elif fault == 'flag_type': value['automatic_pin_refresh'] = 0
    elif fault == 'no_claim_gate': value['caller_must_authenticate_selected_actual_bytes_before_claim_or_contact'] = False
    else: value['old_protocols_remain_spent'] = False
    refused('manifest', lambda: m.validate_manifest(value))


def test_return_values_are_independent_deep_copies():
    original, selected = baseline(), m.pins()
    first = next(iter(selected))
    selected[first] = '0' * 64
    assert m.pins()[first] != '0' * 64 and baseline() == original
    value = m.profile_record()
    result = m.validate_manifest(value)
    result['allowed_replacements'][0]['old_sha256'] = '0' * 64
    result['source_pins'][first] = '0' * 64
    assert m.validate_manifest(value) == value


def test_current_source_bytes_match_the_new_fixed_pins_not_automatic_refresh():
    root = m.frozen.ROOT
    for name, pin in m.pins().items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == pin
    for name, old, _ in m.REPLACEMENTS:
        assert baseline()[name] == old


@pytest.mark.parametrize('name,old,new', m.REPLACEMENTS)
def test_two_authorized_changes_are_only_the_exact_single_LF_removal(name, old, new):
    root = m.frozen.ROOT
    def blob(ref):
        return subprocess.check_output(['/usr/bin/git', 'show', ref + ':' + name], cwd=root)
    before, corrected = blob(m.PREMERGE_HEAD), blob(m.CORRECTION_COMMIT)
    assert before == corrected + b'\n'
    assert corrected.endswith(b'\n') and not corrected.endswith(b'\n\n')
    assert hashlib.sha256(before).hexdigest() == old
    assert hashlib.sha256(corrected).hexdigest() == new
    assert ast.dump(ast.parse(before), include_attributes=False) == ast.dump(ast.parse(corrected), include_attributes=False)
    compile(corrected, name, 'exec')


def test_manifest_has_no_filesystem_or_dispatch_capability_and_is_finitely_refused():
    source = inspect.getsource(m)
    tree = ast.parse(source)
    forbidden = {'open', 'read_bytes', 'read_text', 'write_bytes', 'write_text', 'load_key',
        'run', 'observe', 'main', 'preflight', 'capture', 'Popen', 'check_output'}
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)}
    assert not (calls & forbidden)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == 'open' for node in ast.walk(tree))
    assert m.finite(ValueError('untrusted text')) == 'unknown'
    assert m.finite(m.Refused('untrusted text')) == 'unknown'
    assert m.finite(m.Refused('manifest')) == 'manifest'
