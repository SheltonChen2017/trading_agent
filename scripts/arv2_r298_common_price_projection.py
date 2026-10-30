"""Pure public-source projection for the common-RAW monetary successor.

Only explicitly supplied public records/source pairs and frozen metadata are
consumed. No admission, activation, claim, storage, credential or QC operation
is performed; future exact project/source/rights/run gates remain separate.
"""
import ast
import copy
import dataclasses
import hashlib
import json
import re

from scripts import arv2_newrule_quote_execution_projection as frozen
from research.analyst_revisions_v2_qc import newrule_common_price_comparison_runtime as runtime
from research.analyst_revisions_v2_qc import newrule_native_price_book_runtime as native_reader

SCHEMA = 'arv2-r298-common-price-public-projection-v1'
PATCHER_NAME = 'arv2_r298_common_price_projection.py'
BASE_PROJECTION = '3735a7764f658ba867edb338615666844ceb8f81d7aebdc36d8b7b6495e67779'
BASE_PROFILE = 'cf6e4063796cd297b28aaa1620056a2a86e8bfe7f65a194de1e531f97dc64569'
BASE_PROFILE_BYTES_SHA256 = 'd7403524daca42b8591b1302e6b87affe81b3bd37dc590752c73853ac3dc4661'
BASE_NAME = 'newrule_comparison_qc_runtime.py'
DRIVER_NAME = 'newrule_common_price_comparison_runtime.py'
ADDON_NAMES = ('newrule_common_price_format.py', 'newrule_native_price_source_diagnostic.py',
    'newrule_native_price_book_publication.py', 'newrule_native_price_book_runtime.py',
    'newrule_raw_vendor_price_book_runtime.py', 'newrule_common_price_qc_runtime.py', DRIVER_NAME)
MAX_SOURCE_BYTES, MAX_TOTAL_BYTES = 64000, 1024 * 1024
FALSE_FLAGS = {'source_admission_granted': False, 'QC_processing_rights_granted': False,
    'backtest_created': False, 'strategy_result_accepted': False, 'family_comparable': False,
    'formal_forward_ready': False, 'point_in_time_proven': False, 'paper_or_live_ready': False}
RECORD_KEYS = frozenset(('schema', 'profile_sha256', 'strategy_profile_sha256', 'runtime_project_id',
    'universe_count', 'ar_percent', 'frozen_public_projection_sha256', 'frozen_public_profile_sha256',
    'frozen_quote_base_sha256', 'patcher_sha256', 'native_source_context_sha256',
    'vendor_source_context_sha256', 'policy', 'original_addon_source_pins', 'source_files',
    'unchanged_frozen_files', 'pure_preparation_is_not_run_or_source_admission', *FALSE_FLAGS))
FINITE = frozenset(('source_pairs', 'source_pin', 'source_bound', 'source_annotations', 'base',
    'profile', 'context', 'project', 'main_anchor', 'main_semantics', 'projection', 'unknown'))


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return runtime.canonical(value)
def _dump(value): return ast.dump(value, include_attributes=False)


def _cloud_source(raw, name):
    require(type(raw) is bytes and raw.isascii() and 0 < len(raw) <= MAX_SOURCE_BYTES, 'source_bound')
    tree = ast.parse(raw)
    futures = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == '__future__']
    if futures:
        require(len(futures) == 1 and len(futures[0].names) == 1
            and futures[0].names[0].name == 'annotations'
            and not any(isinstance(node, ast.AnnAssign)
                or isinstance(node, ast.arg) and node.annotation is not None
                or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None
                for node in ast.walk(tree)), 'source_annotations')
        lines = raw.splitlines(keepends=True)
        future = futures[0]
        require(future.lineno == future.end_lineno, 'source_annotations')
        del lines[future.lineno - 1]
        cloud = b''.join(lines)
        tree.body.remove(future)
        require(_dump(ast.parse(cloud)) == _dump(tree), 'source_annotations')
    else:
        cloud = raw
    compile(b'from AlgorithmImports import *\n' + cloud, name, 'exec')
    return cloud


def _main(raw, strategy, common, native_context, vendor_context):
    original = ast.parse(raw)
    tree = copy.deepcopy(original)
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
        and node.module == BASE_NAME[:-3]]
    require(len(imports) == 1 and [name.name for name in imports[0].names]
        == ['NewruleComparisonDriver', 'STARTING_CASH'], 'main_anchor')
    old_import = copy.deepcopy(imports[0])
    imports[0].module = DRIVER_NAME[:-3]
    imports[0].names[0].name = 'CommonPriceComparisonDriver'
    imports[0].names[0].asname = 'NewruleComparisonDriver'
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver']
    require(len(calls) == 1 and len({key.arg for key in calls[0].keywords}) == len(calls[0].keywords),
        'main_anchor')
    call = calls[0]
    keywords = {key.arg: key for key in call.keywords}
    require('profile' in keywords and not ({'common_profile', 'native_source_context',
        'vendor_source_context'} & set(keywords)), 'main_anchor')
    old_profile = copy.deepcopy(keywords['profile'].value)
    constants = {'COMMON_PRICE_PROFILE': common, 'NATIVE_SOURCE_CONTEXT': native_context,
        'VENDOR_SOURCE_CONTEXT': vendor_context}
    require(not any(isinstance(node, ast.Name) and node.id in constants for node in ast.walk(tree)), 'main_anchor')
    declarations = ast.parse('\n'.join(name + ' = ' + repr(value) for name, value in constants.items())).body
    position = next(index for index, node in enumerate(tree.body) if isinstance(node, ast.ClassDef))
    tree.body[position:position] = declarations
    keywords['profile'].value = ast.parse("COMMON_PRICE_PROFILE['strategy_profile']", mode='eval').body
    call.keywords.extend(ast.keyword(arg=name, value=ast.Name(id=variable, ctx=ast.Load()))
        for name, variable in (('common_profile', 'COMMON_PRICE_PROFILE'),
            ('native_source_context', 'NATIVE_SOURCE_CONTEXT'), ('vendor_source_context', 'VENDOR_SOURCE_CONTEXT')))
    algorithms = [node for node in tree.body if isinstance(node, ast.ClassDef)
        and node.name == 'NewruleComparisonAlgorithm']
    require(len(algorithms) == 1, 'main_anchor')
    initializers = [node for node in algorithms[0].body if isinstance(node, ast.FunctionDef)
        and node.name == 'initialize']
    require(len(initializers) == 1, 'main_anchor')
    seeds = [node for node in initializers[0].body if isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Attribute)
        and _dump(node.targets[0]) == _dump(ast.parse('self.settings.seed_initial_prices = True').body[0].targets[0])]
    require(len(seeds) == 1 and isinstance(seeds[0].value, ast.Constant) and seeds[0].value.value is True,
        'main_anchor')
    seeds[0].value = ast.Constant(False)
    guard = ast.parse('if type(self.project_id) is not int or self.project_id != '
        + str(common['runtime_project_id']) + ' or self.live_mode is not False:\n'
        + '    raise RuntimeError("common_price_project")').body[0]
    initializers[0].body.insert(0, guard)
    ast.fix_missing_locations(tree)
    projected = (ast.unparse(tree) + '\n').encode('ascii')
    restored = copy.deepcopy(tree)
    restored.body = [node for node in restored.body if not (isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in constants)]
    imported = next(node for node in restored.body if isinstance(node, ast.ImportFrom)
        and node.module == DRIVER_NAME[:-3])
    restored.body[restored.body.index(imported)] = old_import
    restored_call = next(node for node in ast.walk(restored) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver')
    restored_call.keywords = [key for key in restored_call.keywords
        if key.arg not in ('common_profile', 'native_source_context', 'vendor_source_context')]
    next(key for key in restored_call.keywords if key.arg == 'profile').value = old_profile
    restored_owner = next(node for node in restored.body if isinstance(node, ast.ClassDef)
        and node.name == 'NewruleComparisonAlgorithm')
    next(node for node in restored_owner.body if isinstance(node, ast.FunctionDef)
        and node.name == 'initialize').body.pop(0)
    restored_seed = next(node for node in ast.walk(restored_owner) if isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Attribute)
        and node.targets[0].attr == 'seed_initial_prices')
    restored_seed.value = ast.Constant(True)
    require(_dump(restored) == _dump(original), 'main_semantics')
    compile(projected, 'main.py', 'exec')
    return projected


@dataclasses.dataclass(frozen=True, slots=True)
class Projection:
    projection_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_pairs: tuple = dataclasses.field(repr=False)

    def to_record(self):
        require(type(self.record_bytes) is bytes and sha(self.record_bytes) == self.projection_sha256
            and type(self.profile_bytes) is bytes and type(self.source_pairs) is tuple, 'projection')
        value, profile = json.loads(self.record_bytes), runtime.validate_profile(json.loads(self.profile_bytes))
        require(type(value) is dict and set(value) == RECORD_KEYS
            and canonical(value) == self.record_bytes and canonical(profile) == self.profile_bytes
            and value['schema'] == SCHEMA and value['profile_sha256'] == profile['profile_sha256']
            and value['source_files'] == [{'project_path': name, 'byte_count': len(raw),
                'content_sha256': sha(raw)} for name, raw in self.source_pairs]
            and all(value[key] is False for key in FALSE_FLAGS)
            and value['pure_preparation_is_not_run_or_source_admission'] is True
            and value['frozen_public_projection_sha256'] == BASE_PROJECTION
            and value['frozen_public_profile_sha256'] == BASE_PROFILE
            and value['frozen_quote_base_sha256'] == runtime.FROZEN_BASE_SHA256
            and value['policy'] == runtime.policy_record(), 'projection')
        for key in ('strategy_profile_sha256', 'runtime_project_id', 'universe_count', 'ar_percent',
                    'native_source_context_sha256', 'vendor_source_context_sha256'):
            require(value[key] == profile[key] and type(value[key]) is type(profile[key]), 'projection')
        require(tuple(name for name, _ in self.source_pairs) == frozen.comparison.bridge.parent.FILE_NAMES + ADDON_NAMES
            and profile['source_pins'] == {**{name: sha(raw) for name, raw in self.source_pairs if name != 'main.py'},
                PATCHER_NAME: value['patcher_sha256']}, 'projection')
        return value


def public_specification(frozen_record_bytes, frozen_source_pairs, addon_source_pairs, *,
                         session_axis, runtime_project_id, universe_count, ar_percent,
                         native_source_context, vendor_source_context, expected_addon_pins,
                         patcher_source_bytes, expected_patcher_sha256):
    require(type(patcher_source_bytes) is bytes and 0 < len(patcher_source_bytes) <= MAX_SOURCE_BYTES
        and sha(patcher_source_bytes) == expected_patcher_sha256
        and type(expected_patcher_sha256) is str
        and re.fullmatch('[0-9a-f]{64}', expected_patcher_sha256) is not None, 'source_pin')
    try:
        _, frozen_profile, pairs = frozen.validate_public_projection(frozen_record_bytes,
            frozen_source_pairs, expected_projection_sha256=BASE_PROJECTION, expected_profile_sha256=BASE_PROFILE)
    except Exception:
        raise Refused('base') from None
    require(dict(pairs)[BASE_NAME] and sha(dict(pairs)[BASE_NAME]) == runtime.FROZEN_BASE_SHA256, 'base')
    require(sha(canonical(frozen_profile)) == BASE_PROFILE_BYTES_SHA256, 'base')
    require(type(addon_source_pairs) is tuple and len(addon_source_pairs) == len(ADDON_NAMES)
        and all(type(item) is tuple and len(item) == 2 for item in addon_source_pairs)
        and tuple(name for name, _ in addon_source_pairs) == ADDON_NAMES
        and type(expected_addon_pins) is dict and set(expected_addon_pins) == set(ADDON_NAMES), 'source_pairs')
    require(all(type(item) is tuple and len(item) == 2 and type(item[0]) is str and type(item[1]) is bytes
        and type(expected_addon_pins[item[0]]) is str
        and re.fullmatch('[0-9a-f]{64}', expected_addon_pins[item[0]]) is not None
        and sha(item[1]) == expected_addon_pins[item[0]] for item in addon_source_pairs), 'source_pin')
    require(type(session_axis) is tuple and len(session_axis) == runtime.monetary.native.EXPECTED_AXIS_COUNT
        and runtime.digest(list(session_axis)) == runtime.monetary.native.AXIS_SHA256, 'profile')
    native_context = native_reader.validate_source_context(native_source_context)
    # Vendor's own closed constructor authenticates the content-addressed context;
    # the supplied public context is frozen here, never inferred from a directory.
    try:
        from research.analyst_revisions_v2_qc import newrule_raw_vendor_price_book_runtime as vendor
        vendor_context = vendor.validate_source_context(vendor_source_context)
    except Exception:
        raise Refused('context') from None
    require(type(runtime_project_id) is int and runtime_project_id > 0
        and vendor_context['runtime_project_id'] == runtime_project_id, 'project')
    strategy = frozen._profile(session_axis, universe_count=universe_count, ar_percent=ar_percent,
        source_pins=dict(frozen_profile['source_pins']))
    cloud_addons = tuple((name, _cloud_source(raw, name)) for name, raw in addon_source_pairs)
    source_pins = {name: sha(raw) for name, raw in (*pairs, *cloud_addons) if name != 'main.py'}
    source_pins[PATCHER_NAME] = expected_patcher_sha256
    common = runtime.make_profile(strategy, runtime_project_id=runtime_project_id,
        native_source_context_sha256=runtime.digest(native_context),
        vendor_source_context_sha256=runtime.digest(vendor_context), source_pins=source_pins)
    main = _main(dict(pairs)['main.py'], strategy, common, native_context, vendor_context)
    output = tuple((name, main if name == 'main.py' else raw) for name, raw in pairs) + cloud_addons
    require(len({name for name, _ in output}) == len(output)
        and all(0 < len(raw) <= MAX_SOURCE_BYTES for _, raw in output)
        and sum(len(raw) for _, raw in output) <= MAX_TOTAL_BYTES, 'source_bound')
    record = {'schema': SCHEMA, 'profile_sha256': common['profile_sha256'],
        'strategy_profile_sha256': strategy['profile_sha256'], 'runtime_project_id': runtime_project_id,
        'universe_count': universe_count, 'ar_percent': ar_percent,
        'frozen_public_projection_sha256': BASE_PROJECTION, 'frozen_public_profile_sha256': BASE_PROFILE,
        'frozen_quote_base_sha256': runtime.FROZEN_BASE_SHA256, 'patcher_sha256': expected_patcher_sha256,
        'native_source_context_sha256': runtime.digest(native_context),
        'vendor_source_context_sha256': runtime.digest(vendor_context), 'policy': runtime.policy_record(),
        'original_addon_source_pins': dict(sorted(expected_addon_pins.items())),
        'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)} for name, raw in output],
        'unchanged_frozen_files': [name for name, _ in pairs if name != 'main.py'],
        'pure_preparation_is_not_run_or_source_admission': True, **FALSE_FLAGS}
    result = Projection(sha(canonical(record)), canonical(record), canonical(common), output)
    result.to_record()
    return result
