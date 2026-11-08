"""Offline supplied-buffer plain DATA and old-six source recovery proposal.

No file, credential, network, publication, operational caller or authority mint
exists here. External pins check supplied DATA consistency; they do not prove a
fresh private read. A future frozen caller must authenticate B's original DATA
and selected sources. The three R343-AR100 attempts stay exhausted. This is not
a new candidate, attempt reset, source-policy acceptance or submission permit.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re

from research.analyst_revisions_v2_qc import accepted_risk_preliminary_package as compact
from research.analyst_revisions_v2_qc import newrule_plain_transport as transport
from research.analyst_revisions_v2_qc import newrule_plain_input_runtime as plain_runtime


SCHEMA = 'arv2-r345-legacy-six-plain-buffer-bridge-v1'
INPUT_NAME = 'accepted_risk_order_level_input_runtime.py'
INPUT_MODULE = INPUT_NAME[:-3]
LOADER_NAME = 'newrule_plain_input_runtime.py'
AR_PERCENTS = (80, 100, 120, 140, 160, 180, 200)
ACTIVATION_KEYWORDS = ('activation_manifest_key', 'activation_manifest_sha256',
                       'activation_manifest_byte_count')
USED_INPUT_EXPORTS = frozenset(('load_accepted_risk_preliminary_package', 'collection_rows'))
FALSE_FLAGS = {'operational_authority': False, 'fresh_private_input_authenticated': False,
    'new_storage_admitted': False, 'qc_source_policy_acceptance_proven': False,
    'attempt_budget_reset': False, 'backtest_completed': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}


class Refused(ValueError):
    """A bounded local category, never supplied source or licensed data."""


def require(value, code):
    if not value:
        raise Refused(code)


def canonical(value):
    try:
        return transport.canonical(value)
    except transport.PlainTransportError:
        raise Refused('json') from None


def sha(raw):
    require(type(raw) is bytes, 'bytes')
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _hash(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'hash')
    return value


def _pin(raw, expected):
    require(type(expected) is dict and set(expected) == {'byte_count', 'sha256'}
        and type(expected['byte_count']) is int and expected['byte_count'] > 0
        and pin(raw) == expected, 'pin')
    _hash(expected['sha256'])


@dataclasses.dataclass(frozen=True, slots=True)
class ParentMetadata:
    """Explicit supplied metadata, deliberately NOT a genuine package class."""
    package_id: str
    package_sha256: str
    source_disposition_sha256: str
    upload_objects: tuple
    total_upload_byte_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class PlainData:
    """Serializable immutable buffers, not process authority or admission."""
    source_package_sha256: str
    source_lineage_sha256: str
    source_activation_json: bytes = dataclasses.field(repr=False)
    record_bytes: bytes = dataclasses.field(repr=False)
    uploads: tuple = dataclasses.field(repr=False)  # (canonical descriptor bytes, payload bytes)


@dataclasses.dataclass(frozen=True, slots=True)
class ParentCell:
    candidate_id: str
    ar_percent: int
    profile_bytes: bytes = dataclasses.field(repr=False)
    sources: tuple = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class PlainCell:
    candidate_id: str
    ar_percent: int
    profile_bytes: bytes = dataclasses.field(repr=False)
    sources: tuple = dataclasses.field(repr=False)
    record_bytes: bytes = dataclasses.field(repr=False)


def _json(raw):
    require(type(raw) is bytes and 0 < len(raw) <= transport.MAX_OBJECT_BYTES, 'json')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'json')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('json') from None
    return value


def convert_supplied_inputs(pairs, *, expected_package_sha256, expected_lineage_sha256,
                            expected_inventory_pin):
    """Re-use the existing pure conversion seam; never mint its capability.

    ``pairs`` contains descriptor dictionaries and immutable payload bytes from
    a future authenticated B DATA consumer. Synthetic callers supply explicitly
    synthetic metadata. No old package/capture iterator or private reader runs.
    """
    _hash(expected_package_sha256); _hash(expected_lineage_sha256)
    require(type(pairs) is tuple and 6 <= len(pairs) <= transport.MAX_OBJECTS, 'inventory')
    descriptors, converted = [], []
    for pair in pairs:
        require(type(pair) is tuple and len(pair) == 2 and type(pair[0]) is dict
            and type(pair[1]) is bytes, 'inventory')
        record, raw = pair
        try:
            descriptor = compact.PreliminaryUploadObject(**record)
        except (TypeError, ValueError):
            raise Refused('inventory') from None
        require(canonical(descriptor.to_record()) == canonical(record), 'inventory')
        descriptors.append(descriptor); converted.append((descriptor, raw))
    _pin(canonical([item.to_record() for item in descriptors]), expected_inventory_pin)
    activation = _json(pairs[-1][1])
    require(type(activation) is dict and activation.get('package_sha256') == expected_package_sha256
        and activation.get('source_disposition_sha256') == expected_lineage_sha256, 'parent')
    metadata = ParentMetadata(activation.get('package_id'), expected_package_sha256,
        expected_lineage_sha256, tuple(descriptors), sum(len(raw) for _, raw in pairs))
    try:
        # _convert_payloads explicitly returns an UNMINTED value. No genuine
        # package is forged, and require_plain_transport/_mint are never called.
        proposal = transport._convert_payloads(metadata, tuple(converted))
    except (transport.PlainTransportError, compact.AcceptedRiskPreliminaryPackageError):
        raise Refused('transport') from None
    value = PlainData(proposal.source_package_sha256, proposal.source_lineage_sha256,
        canonical(descriptors[-1].to_record()), proposal.record_bytes,
        tuple((canonical(item.to_record()), item.payload) for item in proposal.upload_objects))
    validate_plain_data(value)
    return value


def validate_plain_data(value):
    """Check immutable buffer contents; the type does not authenticate origin."""
    require(type(value) is PlainData and type(value.record_bytes) is bytes
        and type(value.source_activation_json) is bytes and type(value.uploads) is tuple
        and 6 <= len(value.uploads) <= transport.MAX_OBJECTS, 'plain')
    _hash(value.source_package_sha256); _hash(value.source_lineage_sha256)
    source_activation, record = _json(value.source_activation_json), _json(value.record_bytes)
    require(type(source_activation) is dict and type(record) is dict
        and canonical(source_activation) == value.source_activation_json
        and canonical(record) + b'\n' == value.record_bytes, 'plain')
    objects, total = [], 0
    for pair in value.uploads:
        require(type(pair) is tuple and len(pair) == 2 and type(pair[0]) is bytes and type(pair[1]) is bytes,
                'plain')
        descriptor = _json(pair[0]); raw = pair[1]
        require(type(descriptor) is dict and canonical(descriptor) == pair[0]
            and type(descriptor.get('byte_count')) is int and 0 < len(raw) <= transport.MAX_OBJECT_BYTES
            and descriptor['byte_count'] == len(raw) and descriptor.get('content_sha256') == sha(raw)
            and descriptor.get('compression') == 'identity', 'plain')
        objects.append(descriptor); total += len(raw)
    require(total <= transport.MAX_TOTAL_BYTES and objects[-1].get('activation_manifest') is True
        and objects[-1].get('role') == 'activation_manifest' and value.uploads[-1][1] == value.record_bytes
        and all(item.get('activation_manifest') is False for item in objects[:-1]), 'plain')
    activation = objects[-1]
    try:
        _, validated = plain_runtime._validate_transport(record, activation['object_store_key'], len(value.record_bytes))
        require(canonical(list(validated)) == canonical(objects[:-1]), 'plain')
        for descriptor, (_, raw) in zip(objects[:-1], value.uploads[:-1], strict=True):
            if descriptor['role'] != 'evaluator_manifest':
                plain_runtime._plain_rows(raw, descriptor['record_count'], descriptor['role'])
    except plain_runtime.AcceptedRiskOrderLevelInputRuntimeError:
        raise Refused('plain') from None
    proof = record['parent_proof']
    require(proof['source_package_sha256'] == value.source_package_sha256
        and proof['source_lineage_sha256'] == value.source_lineage_sha256
        and proof['source_activation_sha256'] == source_activation['content_sha256']
        and proof['source_activation_byte_count'] == source_activation['byte_count'], 'parent')
    return record, source_activation, activation


def parent_vector(cells):
    require(type(cells) is tuple and len(cells) == 7, 'cells')
    rows = []
    for percent, cell in zip(AR_PERCENTS, cells, strict=True):
        require(type(cell) is ParentCell and type(cell.ar_percent) is int and cell.ar_percent == percent
            and cell.candidate_id == f'R343-AR{percent:03d}' and type(cell.profile_bytes) is bytes
            and type(cell.sources) is tuple and len(cell.sources) == 18, 'cells')
        sources, names = [], []
        for pair in cell.sources:
            require(type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str
                and re.fullmatch('[A-Za-z][A-Za-z0-9_]*[.]py', pair[0]) and type(pair[1]) is bytes
                and pair[1].isascii() and 0 < len(pair[1]) <= 64000, 'sources')
            names.append(pair[0]); sources.append({'project_path': pair[0], **pin(pair[1])})
        require(names == sorted(set(names)) and {INPUT_NAME, 'main.py', 'legacy_six_october_reporting.py'} <= set(names),
                'sources')
        rows.append({'candidate_id': cell.candidate_id, 'ar_percent': percent,
                     'profile_pin': pin(cell.profile_bytes), 'sources': sources})
    return canonical(rows)


def _tree(raw):
    require(type(raw) is bytes and raw.isascii(), 'source_ast')
    try:
        return ast.parse(raw.decode('ascii'))
    except (SyntaxError, ValueError, TypeError):
        raise Refused('source_ast') from None


def _function(tree, name):
    values = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    require(len(values) == 1, 'loader_surface')
    return values[0]


def input_surface(sources):
    """Prove this exact closed source graph uses only the two plain exports.

    Bare module/function alias use, rebinding, reflection, star imports and
    dynamic imports of the input module refuse. This is a conservative static
    closure check, not a claim about arbitrary Python programs.
    """
    seen = set()
    for name, raw in sources:
        if name == INPUT_NAME:
            continue
        tree = _tree(raw); parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        modules, functions = set(), {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    require(alias.name.split('.')[0] not in ('importlib', 'sys', 'builtins'), 'loader_surface')
                    if alias.name == INPUT_MODULE:
                        modules.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                require((node.module or '').split('.')[0] not in ('importlib', 'sys', 'builtins'), 'loader_surface')
                if node.module == INPUT_MODULE:
                    for alias in node.names:
                        require(alias.name in USED_INPUT_EXPORTS, 'loader_surface')
                        functions[alias.asname or alias.name] = alias.name
                else:
                    for alias in node.names:
                        if alias.name == INPUT_MODULE:
                            modules.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            require(not (isinstance(node, ast.Name) and node.id in
                ('__import__', '__builtins__', 'exec', 'eval', 'compile', 'globals', 'locals', 'vars'))
                and not (isinstance(node, ast.Attribute) and node.attr == 'import_module'), 'loader_surface')
            if isinstance(node, ast.ImportFrom) and (modules or functions):
                require(all(alias.name != '*' for alias in node.names), 'loader_surface')
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                require(node.name not in modules | set(functions), 'loader_surface')
            if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
                require(node.name not in modules | set(functions), 'loader_surface')
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                require(not set(node.names) & (modules | set(functions)), 'loader_surface')
            if isinstance(node, ast.Name) and node.id in modules:
                parent = parents.get(node)
                require(isinstance(node.ctx, ast.Load) and isinstance(parent, ast.Attribute) and parent.value is node
                    and parent.attr in USED_INPUT_EXPORTS and isinstance(parents.get(parent), ast.Call)
                    and parents[parent].func is parent, 'loader_surface')
                seen.add(parent.attr)
            elif isinstance(node, ast.Name) and node.id in functions:
                parent = parents.get(node)
                require(isinstance(node.ctx, ast.Load) and isinstance(parent, ast.Call) and parent.func is node,
                        'loader_surface')
                seen.add(functions[node.id])
            elif isinstance(node, ast.arg):
                require(node.arg not in modules | set(functions), 'loader_surface')
    require(seen == USED_INPUT_EXPORTS, 'loader_surface')
    return tuple(sorted(seen))


def _plain_loader(raw):
    tree = _tree(raw)
    forbidden = {'gzip', 'zlib', 'io', 'base64', 'marshal', 'pickle', 'os', 'subprocess',
                 'socket', 'requests', 'urllib', 'http'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            require(not {item.name.split('.')[0] for item in node.names} & forbidden, 'plain_loader')
        elif isinstance(node, ast.ImportFrom):
            require((node.module or '').split('.')[0] not in forbidden, 'plain_loader')
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            require(node.func.id not in ('exec', 'eval', 'compile', '__import__'), 'plain_loader')
    for name in USED_INPUT_EXPORTS:
        _function(tree, name)
    return tree


def _main(raw, old_activation, new_activation):
    tree = _tree(raw)
    hooks = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
             and node.name == 'on_end_of_algorithm']
    guard = ast.parse("aggregate['run_valid'] is True").body[0].value
    require(len(hooks) == 1 and any(isinstance(node, ast.If)
        and ast.dump(node.test, include_attributes=False) == ast.dump(guard, include_attributes=False)
        for node in ast.walk(hooks[0])), 'validity_guard')
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and set(ACTIVATION_KEYWORDS) <= {item.arg for item in node.keywords}]
    require(len(calls) == 1, 'main')
    keywords = {item.arg: item for item in calls[0].keywords}
    require(len(keywords) == len(calls[0].keywords), 'main')
    original = ast.dump(tree, include_attributes=False)
    old_values, new_values = {}, {}
    for keyword, field in zip(ACTIVATION_KEYWORDS,
            ('object_store_key', 'content_sha256', 'byte_count'), strict=True):
        try:
            value = ast.literal_eval(keywords[keyword].value)
        except (ValueError, TypeError, SyntaxError):
            raise Refused('main') from None
        require(type(value) is type(old_activation[field]) and value == old_activation[field], 'main')
        old_values[keyword], new_values[keyword] = value, new_activation[field]
        keywords[keyword].value = ast.Constant(new_activation[field])
    rendered = (ast.unparse(ast.fix_missing_locations(tree)) + '\n').encode('ascii')
    # Reverting ONLY these three keyword literals must exactly recover the
    # original AST, including the section-344 valid-run guard and all money,
    # dates, rules, order calls, imports, hooks and other literals.
    for keyword in ACTIVATION_KEYWORDS:
        keywords[keyword].value = ast.Constant(old_values[keyword])
    require(ast.dump(tree, include_attributes=False) == original, 'economic_ast')
    return rendered


def build_source_bridge(cells, plain_data, *, expected_parent_vector_pin,
                        plain_loader_source, expected_plain_loader_pin):
    """Prepare only a two-file source delta; every financial rule is retained.

    Unchanged profile.source_package_sha256 denotes ANCESTRAL input, never the
    actual plain transport read. New records bind both identities distinctly;
    a future result consumer must validate the new runtime META identity too.
    """
    vector = parent_vector(cells); _pin(vector, expected_parent_vector_pin)
    record, old_activation, activation = validate_plain_data(plain_data)
    _pin(plain_loader_source, expected_plain_loader_pin)
    plain_tree = _plain_loader(plain_loader_source)
    loader = (ast.unparse(plain_tree) + '\n').encode('ascii')
    results = []
    for cell in cells:
        sources = dict(cell.sources); old_loader = _tree(sources[INPUT_NAME])
        require(ast.dump(_function(old_loader, 'collection_rows'), include_attributes=False)
            == ast.dump(_function(plain_tree, 'collection_rows'), include_attributes=False), 'collection_semantics')
        for tree in (old_loader, plain_tree):
            bounds = [node.value for node in tree.body if isinstance(node, ast.Assign)
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'MAX_COLLECTION_ROWS']
            require(len(bounds) == 1, 'collection_semantics')
            bound = ast.literal_eval(bounds[0])
            require(type(bound) is int and bound == 25000, 'collection_semantics')
        used = input_surface(cell.sources)
        profile = _json(cell.profile_bytes)
        require(type(profile) is dict and canonical(profile) == cell.profile_bytes
            and profile.get('candidate_id') == cell.candidate_id
            and profile.get('source_package_sha256') == plain_data.source_package_sha256
            and profile.get('source_lineage_sha256') == plain_data.source_lineage_sha256, 'parent_profile')
        seed = dict(profile); supplied = seed.pop('profile_sha256', None)
        require(type(supplied) is str and sha(canonical(seed)) == supplied, 'parent_profile')
        sources[INPUT_NAME] = loader
        sources['main.py'] = _main(sources['main.py'], old_activation, activation)
        buffers = tuple(sorted(sources.items()))
        require(len(buffers) == 18 and sum(len(raw) for _, raw in buffers) + 32768 <= 448 * 1024
            and all(0 < len(raw) <= 64000 for _, raw in buffers), 'source_bound')
        unchanged = [name for name, raw in cell.sources if name not in (INPUT_NAME, 'main.py')]
        require(len(unchanged) == 16 and all(sources[name] == dict(cell.sources)[name] for name in unchanged),
                'unchanged')
        for name, raw in buffers:
            try:
                compile(raw, name, 'exec')
            except (SyntaxError, ValueError, TypeError):
                raise Refused('source_ast') from None
        result = {'schema': SCHEMA, 'candidate_id': cell.candidate_id, 'ar_percent': cell.ar_percent,
            'prepared_only': True, 'parent_vector_pin': expected_parent_vector_pin,
            'unchanged_profile_pin': pin(cell.profile_bytes),
            'ancestral_source_package_sha256': plain_data.source_package_sha256,
            'source_lineage_sha256': plain_data.source_lineage_sha256,
            'actual_plain_package_sha256': record['package_sha256'],
            'actual_activation': {field: activation[field] for field in
                ('object_store_key', 'content_sha256', 'byte_count')},
            'parent_proof_sha256': record['parent_proof_sha256'],
            'changed_files': [INPUT_NAME, 'main.py'], 'unchanged_files': unchanged,
            'input_exports_used': list(used),
            'source_mapping': {INPUT_NAME: LOADER_NAME},
            'actual_loader_source_pin': pin(loader), 'selected_loader_source_pin': expected_plain_loader_pin,
            'source_files': [{'project_path': name, **pin(raw)} for name, raw in buffers],
            'result_contract': 'new_actual_plain_transport_META_plus_unchanged_ancestral_profile',
            **FALSE_FLAGS}
        results.append(PlainCell(cell.candidate_id, cell.ar_percent, cell.profile_bytes, buffers, canonical(result)))
    return tuple(results)
