"""Source-only closure proofs, no installed CLR or cloud execution."""
import sys
from types import MappingProxyType

import pytest

from data.hashing import hash_bytes, hash_payload
import scripts.short_interest_qc_source_free_bundle as p
from pathlib import Path

# These cases need the lane's pinned physical root: code manifests, protocol
# paths and sibling imports are built from the designated macOS worktree.
_DESIGNATED_ROOT_ONLY = pytest.mark.skipif(
    Path.cwd().resolve() != p.ROOT,
    reason=(
        "the lane pins its physical root, code manifest and protocol paths to the "
        "designated macOS worktree; this host is not it, see the lane record SI-CR18-005"
    ),
)


HEAD = '0368862746e3388091e50801d4f2c128ebc9fe55'


def guard():
    # The invoking shell supplies the physical/root/branch/HEAD guard. No
    # subprocess, credentials, network or engine operation inside this factory.
    assert p.ROOT.cwd().resolve() == p.ROOT


@pytest.fixture(scope='module')
def bundle():
    return p.assemble_bundle(expected_head=HEAD, guard=guard)


@_DESIGNATED_ROOT_ONLY
def test_current_main_complete_import_closure_is_package_valid(bundle):
    value = bundle.to_payload()
    files = dict(bundle.iter_files())
    assert len(files) == value['total_files']
    assert all(path in files for path in p.MAIN_COMPONENTS)
    assert files['scripts/__init__.py'].startswith(b'"""Source-free')
    assert 'artifacts' not in files['main.py'].decode()
    assert p.audit_closure(files) == value['dependency_audit']
    assert 'clr' not in sys.modules and 'AlgorithmImports' not in sys.modules


def test_imported_member_is_not_misclassified_as_a_package():
    files = {'data/__init__.py': b'', 'data/hashing.py': b'def hash_payload(x): return x\n',
             'main.py': b'from data.hashing import hash_payload\n'}
    result = p.audit_closure(files)
    assert ['main.py', 'data.hashing', 'data/hashing.py'] in result['local_import_edges']


@pytest.mark.parametrize('missing', ['data/__init__.py', 'data/hashing.py',
    'research/short_interest_etf/__init__.py', 'research/short_interest_etf/contracts.py'])
@_DESIGNATED_ROOT_ONLY
def test_missing_transitive_module_or_package_refuses(bundle, missing):
    files = dict(bundle.iter_files()); files.pop(missing)
    with pytest.raises(p.BundleRefusal, match='(package_marker_missing|local_source_dependency_missing)'):
        p.audit_closure(files)


@pytest.mark.parametrize('bad', [b'import requests\n', b'import keyring\n',
    b'from artifacts.private import anything\n', b'import unknown_runtime\n'])
def test_provider_secret_database_unknown_import_refuses(bad):
    with pytest.raises(p.BundleRefusal):
        p.audit_closure({'main.py': bad})


@_DESIGNATED_ROOT_ONLY
def test_bundle_hashes_all_code_bytes_and_flags_do_not_grant_execution(bundle):
    value = bundle.to_payload()
    asserted = value.pop('bundle_sha256')
    assert hash_payload(value) == asserted
    files = dict(bundle.iter_files())
    for row in value['files']:
        assert row == {'path': row['path'], 'bytes': len(files[row['path']]),
            'sha256': hash_bytes(files[row['path']])}
    assert value['largest_file_bytes'] == max(len(raw) for raw in files.values())
    assert value['cloud_maxFileSize_verified'] is False
    assert value['cloud_file_count_capacity_verified'] is False
    assert value['actual_input_admitted'] is value['actual_engine_proof'] is False
    assert value['positive_data_free_registration'] is value['project_upload_or_job_authority'] is False
    assert value['actual_outcome_looks'] == value['qc_attempts'] == 0


@_DESIGNATED_ROOT_ONLY
def test_returned_manifest_detached_and_source_mapping_immutable(bundle):
    value = bundle.to_payload(); value['files'].clear()
    assert bundle.to_payload()['files']
    with pytest.raises(TypeError):
        bundle._files['main.py'] = b''
    assert type(bundle._files) is MappingProxyType


def test_pending_proposal_has_no_operational_entrypoint():
    with pytest.raises(p.BundleRefusal, match='no_upload_or_job_entrypoint'):
        p.main()


@_DESIGNATED_ROOT_ONLY
def test_optional_receiving_overlay_preserves_economic_commands_and_fixture(bundle):
    checked = p.assemble_bundle(expected_head=HEAD, guard=guard, include_receiving_instrumentation=True)
    value = checked.to_payload()
    plain_files, checked_files = dict(bundle.iter_files()), dict(checked.iter_files())
    assert value['fixture_sha256'] == bundle.to_payload()['fixture_sha256']
    assert value['receiving_instrumentation_included'] is True
    for path in p.SOURCE_FILES:
        assert checked_files[path] == plain_files[path]
    assert b'from scripts.short_interest_typed_receiving import ReceivingCheckedCompactLeanRuntime' in checked_files['main.py']
    assert b'self._hub.submit(self._hub.prepare(command))' in checked_files['main.py']
    assert b'self._hub.snapshot_family()' in checked_files['main.py']
    assert checked.to_payload()['actual_engine_proof'] is False

@_DESIGNATED_ROOT_ONLY
def test_manifest_cannot_be_mutated_and_rehashed_into_authority():
    value = p.assemble_bundle(expected_head=HEAD, guard=guard)
    value._manifest['actual_input_admitted'] = True
    changed = dict(value._manifest)
    changed.pop('bundle_sha256')
    value._manifest['bundle_sha256'] = hash_payload(changed)
    with pytest.raises(p.BundleRefusal, match='bundle_manifest_changed'):
        value.to_payload()
