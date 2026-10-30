"""Pinned, source-free bundle closure proposal. No cloud or engine execution.

Reads only the explicitly permitted Main source files and package markers.
AST closure auditing never imports an installed engine or executes copied code.
This is not a source, processing, runtime, project or research-look permit.
"""
from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
import re
from types import MappingProxyType

from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.short_interest_qc_source_free_candidate as entry
import scripts.short_interest_qc_receiver_proposal as receivers

ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
MAIN_COMPONENTS = (
    'research/short_interest_etf/native_qc_order_representation.py',
    'research/short_interest_etf/native_accrual_ending.py',
    'scripts/short_interest_lean_joint_transport.py',
    'scripts/short_interest_compact_joint_transport.py')
SOURCE_FILES = MAIN_COMPONENTS + (
    'data/__init__.py', 'data/hashing.py', 'data/exchange_calendar.py', 'data/financial_primitives.py',
    'research/__init__.py', 'research/short_interest_etf/__init__.py',
    'research/short_interest_etf/contracts.py', 'research/short_interest_etf/availability.py',
    'research/short_interest_etf/preregistration.py',
    'research/short_interest_etf/latest_revised_protocol.py',
    'research/short_interest_etf/qc_fractional_transport.py')
FORBIDDEN_IMPORT_ROOTS = frozenset(('subprocess', 'socket', 'requests', 'urllib', 'sqlite3',
    'keyring', 'secrets', 'importlib', 'ctypes', 'operator_database'))
EXTERNAL_RUNTIME_ROOTS = frozenset(('AlgorithmImports', 'clr', 'System', 'QuantConnect',
    'pandas', 'pandas_market_calendars'))
STDLIB_ROOTS = frozenset(('__future__', 'base64', 'collections', 'copy', 'dataclasses', 'datetime',
    'decimal', 'enum', 'fractions', 'functools', 'hashlib', 'json', 'math', 'os', 'sys',
    're', 'tempfile', 'typing', 'zoneinfo', 'zlib'))


class BundleRefusal(ValueError):
    pass


def require(value, reason):
    if not value:
        raise BundleRefusal('REFUSED: ' + reason)


def audit_closure(files):
    """Exact package closure, including code imported by __init__ exports."""
    require(type(files) in (dict, MappingProxyType), 'exact_source_file_mapping')
    external, edges = set(), []
    for path, raw in sorted(files.items()):
        require(type(path) is str and path.endswith('.py') and type(raw) is bytes,
                'source_text_file_required')
        tree = ast.parse(raw.decode('utf-8'), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Import):
                names = [(name.name, True) for name in node.names]
            else:
                require(node.level == 0, 'unresolved_relative_package_import')
                names = [(node.module or '', True)]
                # A from-import may name a module or an exported member. Only
                # an actual module has ancestor package markers of its own.
                names.extend(((node.module or '') + '.' + alias.name, False)
                    for alias in node.names if alias.name != '*')
            for name, must_resolve in names:
                root = name.split('.')[0]
                require(root not in FORBIDDEN_IMPORT_ROOTS and root != 'artifacts', 'non_source_free_import')
                if root not in ('data', 'research', 'scripts'):
                    require(root in STDLIB_ROOTS | EXTERNAL_RUNTIME_ROOTS, 'undeclared_runtime_import')
                    external.add(root)
                    continue
                pieces = name.split('.')
                candidates = ('/'.join(pieces) + '.py', '/'.join(pieces) + '/__init__.py')
                # Imported function/class names need not be a separate module.
                existing = [c for c in candidates if c in files]
                if existing:
                    edges.append([path, name, existing[0]])
                else:
                    require(not must_resolve, 'local_source_dependency_missing')
                    continue
                for count in range(1, len(pieces)):
                    marker = '/'.join(pieces[:count]) + '/__init__.py'
                    require(marker in files, 'package_marker_missing')
    return {'external_import_roots': sorted(external), 'local_import_edges': edges,
        'no_credentials_provider_network_database_imports': True,
        'installed_engine_imported_or_executed': False}


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class SourceFreeCloudBundle:
    _files: MappingProxyType = dataclasses.field(repr=False)
    _manifest: dict = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise BundleRefusal('REFUSED: source_free_bundle_factory_required')

    def _guard(self):
        require(type(self) is SourceFreeCloudBundle and type(self._anchor) is tuple
            and len(self._anchor) == 3 and self._files is self._anchor[0]
            and self._manifest is self._anchor[1], 'sealed_bundle_changed')
        require(canonical_json(self._manifest) == self._anchor[2], 'bundle_manifest_changed')
        rows = [{'path': path, 'bytes': len(raw), 'sha256': hash_bytes(raw)} for path, raw in sorted(self._files.items())]
        require(rows == self._manifest['files'], 'bundle_source_bytes_changed')
        value = dict(self._manifest); claimed = value.pop('bundle_sha256')
        require(hash_payload(value) == claimed, 'bundle_manifest_changed')

    def to_payload(self):
        self._guard()
        import json
        from data.hashing import canonical_json
        return json.loads(canonical_json(self._manifest))

    def iter_files(self):
        self._guard()
        for path, raw in sorted(self._files.items()):
            self._guard()
            yield path, raw


def assemble_bundle(*, expected_head, guard, include_receiving_instrumentation=False):
    require(type(expected_head) is str and re.fullmatch('[0-9a-f]{40}', expected_head) is not None,
            'exact_code_HEAD_required')
    require(Path.cwd().resolve() == ROOT and ROOT.resolve() == ROOT, 'designated_physical_root_required')
    require(type(include_receiving_instrumentation) is bool, 'exact_instrumentation_choice_required')
    files = {}
    for relative in SOURCE_FILES:
        guard()
        path = ROOT / relative
        require(path.resolve() == path and path.is_file(), 'exact_owned_source_path_required')
        raw = path.read_bytes()  # Enumerated source code only; never a data/secret path.
        guard()
        compile(raw, relative, 'exec')
        files[relative] = raw
    # Main scripts are an implicit namespace package locally. The cloud bundle
    # uses an empty regular-package marker, not another lane's __init__ side effects.
    files['scripts/__init__.py'] = b'"""Source-free same48 script package marker; no startup behavior."""\n'
    source = entry.candidate_source()
    if include_receiving_instrumentation:
        original = 'from scripts.short_interest_compact_joint_transport import CompactLeanRuntime, CompactJointTransport, trade_instruction, action_instruction'
        replacement = ('from scripts.short_interest_compact_joint_transport import CompactJointTransport, trade_instruction, action_instruction\n'
            'from scripts.short_interest_typed_receiving import ReceivingCheckedCompactLeanRuntime as CompactLeanRuntime')
        require(source.count(original) == 1, 'held_entrypoint_exact_import_overlay_changed')
        source = source.replace(original, replacement)
        files['scripts/short_interest_typed_receiving.py'] = receivers.receiver_source().encode('utf-8')
        compile(files['scripts/short_interest_typed_receiving.py'], 'scripts/short_interest_typed_receiving.py', 'exec')
    files['main.py'] = source.encode('utf-8')
    compile(files['main.py'], 'main.py', 'exec')
    audit = audit_closure(files)
    guard()
    rows = [{'path': path, 'bytes': len(raw), 'sha256': hash_bytes(raw)} for path, raw in sorted(files.items())]
    largest = max(row['bytes'] for row in rows)
    manifest = {'schema': 'si-source-free-same48-cloud-bundle-proposal-v1', 'code_head': expected_head,
        'canonical_Main_components': list(MAIN_COMPONENTS), 'files': rows,
        'total_files': len(rows), 'total_source_bytes': sum(row['bytes'] for row in rows),
        'largest_file_bytes': largest, 'cloud_maxFileSize_verified': False,
        'minimum_per_file_capacity_required_bytes': largest, 'cloud_file_count_capacity_verified': False,
        'fixture_sha256': entry.fabricated_manifest()['fixture_sha256'], 'dependency_audit': audit,
        'receiving_instrumentation_included': include_receiving_instrumentation,
        'receiving_instrumentation': receivers.descriptor(),
        'runtime_requirements': ['Python_at_least_3.10_for_union_and_dataclass_slots',
            'pandas_and_pandas_market_calendars_versions_and_frozen_fixture_XNYS_opens',
            'actual_QC_AlgorithmImports_CLR_pythonnet_and_wrapper_versions',
            'permitted_exact_project_file_hierarchy_and_each_file_limit',
            'actual_custom_local_feed_delivery_and_default_portfolio_callback_order',
            'typed_outbound_receiving_fields_and_getter_decimal_roundtrips'],
        'positive_data_free_registration': False, 'actual_input_admitted': False,
        'actual_engine_proof': False, 'project_upload_or_job_authority': False,
        'actual_outcome_looks': 0, 'qc_attempts': 0, 'performance_result': False,
        'topology': 'joint48_fictional_mechanics_only_not_full_population_RAM_qualification',
        'attempt_scope': 'at_most_three_unsuccessful_same_economic_candidate_compile_runtime_cycles_no_reset_by_technical_source_edit',
        'public_package_evidence': 'https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/libraries',
        'public_file_limit_evidence': 'https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/project-management/create-project'}
    manifest['bundle_sha256'] = hash_payload(manifest)
    result = object.__new__(SourceFreeCloudBundle)
    mapping = MappingProxyType(files)
    for name, value in (('_files', mapping), ('_manifest', manifest), ('_anchor', (mapping, manifest, canonical_json(manifest)))):
        object.__setattr__(result, name, value)
    result._guard()
    return result


def main():
    raise BundleRefusal('REFUSED: unregistered_proposal_has_no_upload_or_job_entrypoint')
