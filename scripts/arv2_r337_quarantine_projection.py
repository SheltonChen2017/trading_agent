"""Pure six-cell source/Main construction for the R337 exploratory quarantine.

Only supplied public source bytes, the genuine supplied full session axis,
private quarantine catalog and proposed project/vendor context are consumed.
No filesystem, QC, provider, credential, operational or old generator call is
available. Selected code and source metadata never grant a launch or admission.
"""
import ast
import copy
import dataclasses
import hashlib
import json
import re
from types import SimpleNamespace

from research.analyst_revisions_v2_qc import newrule_comparison_projection as frozen
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_runtime as runtime
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_targets as quarantine
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_vendor_book as vendor

SCHEMA = 'arv2-r337-quarantine-six-cell-public-source-v1'
CELL_SCHEMA = SCHEMA + '-cell'
CELL_ORDER = ((6, 0), (6, 100), (6, 200), (8, 0), (8, 100), (8, 200))
MAX_HOST_BYTES, MAX_SOURCE_BYTES, MAX_TOTAL_BYTES = 100000, 64000, 2 * 1024 * 1024
MAX_RECORD_BYTES = 256 * 1024
TEMPLATE_NAME = 'accepted_risk_six_universe_order_qc_projection.py'
LEGACY_NAME = 'accepted_risk_six_universe_order_qc_runtime.py'
HELPER_NAME = 'newrule_comparison_projection.py'
LOADER_NAME = 'newrule_plain_input_runtime.py'
INPUT_NAME = 'accepted_risk_order_level_input_runtime.py'
DRIVER_NAME = 'newrule_five_case_quarantine_runtime.py'
ACTIVATION = ('arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/transport-manifest.json',
    'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b', 5901)
ENGINE_START_SESSION = '2021-09-01'
HOST_SOURCE_PINS = {'accepted_risk_order_level_core.py': '063ed8fb7024c879a640780c07723c7edfb95665acc711d02fc8be0d964e965f', 'accepted_risk_order_level_forced_exit.py': '21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f', 'accepted_risk_preliminary_qc_figi.py': '4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9', 'accepted_risk_preliminary_rating_evaluator.py': '2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910', 'accepted_risk_preliminary_rating_policy.py': '7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd', 'accepted_risk_preopen_rating_score.py': '67f86ffc696c036c7fbfef64ee00fb1ad1a8599727f5ef36762e329df85a023a', 'accepted_risk_six_universe_order_qc_projection.py': '5037fdc1153c9ac927a540201fa92cb45db463e8313e0c88e04ddc9f0eb301f6', 'accepted_risk_six_universe_order_qc_runtime.py': '84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a', 'newrule_available_history_comparison_runtime.py': '7b32ec439553089fbd9b3ffd5fabb708bc823fffca479c8f941dbfe185b33150', 'newrule_common_price_format.py': 'd254b3e3a6a52445e4422f03885ec58a3d2b30e8ce902cb80ed8f841c374f873', 'newrule_comparison_projection.py': '4f51d1a9a50293f4fa39be297666c1e6144462abaa82e69e342845580a1a4076', 'newrule_comparison_targets.py': '30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d', 'newrule_five_case_quarantine_common_price.py': '7006b05843e4c7fbdfec0b9f8ea5f716c0d631dcde4cdf04a13a520b9a67645b', 'newrule_five_case_quarantine_contract.py': 'f047a1f0eff4fc7424da04246b0a89edc47bb8358ea93cd979ca10c935cbe8ad', 'newrule_five_case_quarantine_policy.py': '77280e4963c38e9197da81f3b02b920d91d5e727380b1323bfa9e54a715a8ac0', 'newrule_five_case_quarantine_runtime.py': '2cbb69c89b9735331219ec9f573110ec9f27338f6d706c08a836404f43ccc958', 'newrule_five_case_quarantine_targets.py': 'd98777e7398f3f1779a5a0bd4ec68b83db24542730aeb24a4cea70b6f95ff6b4', 'newrule_five_case_quarantine_vendor_book.py': '8f1baa74cb5fa3b27a26748f94b6bf422fbb13f13f5524d598b92a82def80504', 'newrule_native_price_book_publication.py': '03d100e962b98cd8b174d947a33636e421692445422c0dcce2282b46015435e2', 'newrule_native_price_source_diagnostic.py': '57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697', 'newrule_plain_input_runtime.py': 'bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f'}
CLOUD_SOURCE_PINS = {'accepted_risk_order_level_core.py': '96d3f886dee6faa97574ef2ea64a9e0fa85057eb568cecfea028228905aa9435', 'accepted_risk_order_level_forced_exit.py': 'e421721bb0f3cd29dbca0f2c9fdff87c52a3c298fc94b50f57213d7e22889649', 'accepted_risk_order_level_input_runtime.py': 'b3f48e1b1c6fc6cc665d9f8b475292260074feec5571eab6e8f0d1c1a091fd35', 'accepted_risk_preliminary_qc_figi.py': '5958786ddd787a45a90d636a36d07136841ee79cf1ce904c8d749d47045ff81d', 'accepted_risk_preliminary_rating_evaluator.py': 'd706a19324f59ac36e910b715c3ee17312a7126444287d9eba18c8fc8d06c21a', 'accepted_risk_preliminary_rating_policy.py': 'be082935781e8d406e5c6126fe33bb08866bc765b1d1ac162a96df4c0c988fd7', 'accepted_risk_preopen_rating_score.py': '5c64bfddcbc8e374d7f82b30dcb046125f556e7d8fb67c5f492754f7c1255d11', 'newrule_available_history_comparison_runtime.py': 'bb7fbd652a1220c6a9975049cf86915d8378c4970b22caac09e5d3121a38f0ef', 'newrule_common_price_format.py': '9efb7f2d770176742e0984bb71499ff80953d5bc6f880d886214768beb6ea409', 'newrule_comparison_targets.py': 'da2b7bb1e1bdfa8d12022152a6e9e3315a806b7890763c7876e32f614601fb11', 'newrule_five_case_quarantine_common_price.py': '451474447c3861ecf058fe293f7b5d851e997034126da48ee0ceac752517eac1', 'newrule_five_case_quarantine_contract.py': '9145ab0c39635b54d65b5206b53ec0799def4a330452523395ba49261bcf593f', 'newrule_five_case_quarantine_policy.py': '3dd20042305ef0011be910f184d7a50c10caaa11d4da1e32c9642b27c9e4b54a', 'newrule_five_case_quarantine_runtime.py': 'fbf66fc0735bc04f30e60396e8280d2a3fbbc3d88c99fb8d1ee45c9f686a3116', 'newrule_five_case_quarantine_targets.py': 'd4832c4adb2f8600eb4b1915495454cdedc7b68aab6e945bedc8e16aafaecfa1', 'newrule_five_case_quarantine_vendor_book.py': 'd07548a53e69c69d15c0233c830c13bd88846f947943fcf1d13c2f838f7d3657', 'newrule_legacy_primitives.py': 'ed32742c02623c03364d5f235b65cf8c0bb921c0e0d6febbb435c48c05092e16', 'newrule_native_price_book_publication.py': 'f625466fbeda3f59170ef49b76ebd31900a391dc8025589e621c31cc91326085', 'newrule_native_price_source_diagnostic.py': '1e1c43c106ebef50973f26b9202b6393e4ab47e4b62e26433da32ffc662d085c'}
FALSE_FLAGS = {name: False for name in ('QC_or_Safari_access', 'runtime_project_currently_verified',
    'QC_processing_rights_granted', 'QC_transfer_granted', 'input_DATA_reauthenticated',
    'price_coverage_proven', 'source_admission_granted', 'strategy_result_accepted',
    'family_comparable', 'backtest_created', 'point_in_time_proven', 'formal_identity_admitted',
    'formal_forward_ready', 'paper_or_live_ready', 'old_results_relabelled')}
FINITE = frozenset(('source_inventory', 'source_pin', 'source_bound', 'source_shape',
    'source_semantics', 'source_closure', 'template', 'main', 'profile', 'catalog',
    'context', 'project', 'cell', 'batch', 'json', 'unknown'))


class Refused(ValueError):
    """Closed source/profile predicate; never private IDs or source content."""


def require(condition, code):
    if not condition: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try: return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError): raise Refused('json') from None


def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(canonical(value))
def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}
def _dump(value): return ast.dump(value, include_attributes=False)
def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _loads(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'json')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'json'); result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(canonical(value) == raw, 'json'); return value
    except Refused: raise
    except (ValueError, UnicodeError, TypeError, RecursionError): raise Refused('json') from None


def _source_pairs(value, names):
    require(type(value) is tuple and len(value) == len(names)
        and all(type(row) is tuple and len(row) == 2 and type(row[0]) is str and type(row[1]) is bytes for row in value)
        and tuple(name for name, _ in value) == tuple(sorted(names)), 'source_inventory')
    return dict(value)


def _normalize(raw, name):
    require(type(raw) is bytes and raw.isascii() and 0 < len(raw) <= MAX_HOST_BYTES, 'source_bound')
    try:
        tree = ast.parse(raw, filename=name)
        futures = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == '__future__']
        if futures:
            require(len(futures) == 1 and [alias.name for alias in futures[0].names] == ['annotations']
                and not any(isinstance(node, ast.AnnAssign) or isinstance(node, ast.arg) and node.annotation is not None
                    or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None
                    for node in ast.walk(tree)), 'source_shape')
            tree.body.remove(futures[0])
        result = (ast.unparse(tree) + '\n').encode('ascii')
        require(_dump(ast.parse(result)) == _dump(tree), 'source_semantics')
        require(0 < len(result) <= MAX_SOURCE_BYTES, 'source_bound')
        compile(result, name, 'exec'); compile(b'from AlgorithmImports import *\n' + result, name, 'exec')
        return result
    except Refused: raise
    except (SyntaxError, UnicodeError, ValueError, TypeError, RecursionError): raise Refused('source_shape') from None


def _cloud_sources(source_pairs, expected_source_pins):
    require(type(expected_source_pins) is dict and expected_source_pins == HOST_SOURCE_PINS
        and all(type(k) is str and _hash(v) for k, v in expected_source_pins.items()), 'source_pin')
    supplied = _source_pairs(source_pairs, HOST_SOURCE_PINS)
    for name, raw in supplied.items():
        require(raw.isascii() and 0 < len(raw) <= MAX_HOST_BYTES and sha(raw) == HOST_SOURCE_PINS[name], 'source_pin')
    cloud = {}
    for name, raw in supplied.items():
        if name in (TEMPLATE_NAME, HELPER_NAME): continue
        if name == LEGACY_NAME:
            try: raw = frozen.legacy_primitives(raw)
            except Exception: raise Refused('source_semantics') from None
            name = 'newrule_legacy_primitives.py'
        elif name == LOADER_NAME: name = INPUT_NAME
        cloud[name] = _normalize(raw, name)
    result = tuple(sorted(cloud.items()))
    require(len(result) == 19 and len(cloud) == 19 and sum(map(len, cloud.values())) <= MAX_TOTAL_BYTES,
        'source_inventory')
    require({name: sha(raw) for name, raw in result} == CLOUD_SOURCE_PINS, 'source_pin')
    return result


FEE_CLASS = 'class NewruleTenBpsFeeModel(FeeModel):\n    def __init__(self, driver):\n        self._driver = driver\n    def get_order_fee(self, parameters):\n        price = self._driver.fee_basis(parameters)\n        quantity = abs(Decimal(str(parameters.order.absolute_quantity)))\n        if not price.is_finite() or price <= 0 or not quantity.is_finite():\n            raise RuntimeError("newrule fee input")\n        return OrderFee(CashAmount(price * quantity * Decimal("0.001"), "USD"))\n'


def _node(owner, name, kind):
    found = [node for node in owner.body if type(node) is kind and node.name == name]
    require(len(found) == 1, 'main'); return found[0]


def _main(profile, catalog, context, template_raw):
    require(type(template_raw) is bytes and sha(template_raw) == HOST_SOURCE_PINS[TEMPLATE_NAME], 'template')
    # JSON key insertion order is not semantic input. Canonicalize supplied
    # mappings before embedding Python literals, including validator roundtrips.
    profile, catalog, context = (json.loads(canonical(value)) for value in (profile, catalog, context))
    activation = SimpleNamespace(object_store_key=ACTIVATION[0], content_sha256=ACTIVATION[1], byte_count=ACTIVATION[2])
    try: original = ast.parse(frozen.main_source(profile['strategy_profile'], activation, template_raw))
    except Exception: raise Refused('template') from None
    tree = copy.deepcopy(original)
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == 'newrule_comparison_qc_runtime']
    require(len(imports) == 1 and [item.name for item in imports[0].names] == ['NewruleComparisonDriver', 'STARTING_CASH'], 'main')
    old_import = copy.deepcopy(imports[0]); imports[0].module = DRIVER_NAME[:-3]
    imports[0].names[0].name = 'FiveCaseQuarantineComparisonDriver'; imports[0].names[0].asname = 'NewruleComparisonDriver'
    fee = _node(tree, 'NewruleTenBpsFeeModel', ast.ClassDef); old_fee = copy.deepcopy(fee)
    tree.body[tree.body.index(fee)] = ast.parse(FEE_CLASS).body[0]
    algorithm = _node(tree, 'NewruleComparisonAlgorithm', ast.ClassDef)
    initializer = _node(algorithm, 'initialize', ast.FunctionDef)
    old_init = copy.deepcopy(initializer)
    seeds = [node for node in initializer.body if isinstance(node, ast.Assign)
        and _dump(node.targets[0]) == _dump(ast.parse('self.settings.seed_initial_prices = True').body[0].targets[0])]
    starts = [node for node in initializer.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'set_start_date']
    require(len(seeds) == len(starts) == 1 and seeds[0].value.value is True
        and [v.value for v in starts[0].value.args] == [2020, 11, 1], 'main')
    seeds[0].value = ast.Constant(value=False); starts[0].value.args = [ast.Constant(value=n) for n in (2021, 9, 1)]
    calls = [node for node in ast.walk(initializer) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver']
    require(len(calls) == 1 and len(calls[0].args) == 1 and not any(key.arg is None for key in calls[0].keywords), 'main')
    call = calls[0]; keys = {key.arg: key for key in call.keywords}
    require(len(keys) == len(call.keywords) and 'profile' in keys and 'fee_model_factory' in keys
        and not {'common_profile', 'vendor_source_context', 'quarantine_catalog', 'quote_bar_type', 'native_source_context'} & set(keys), 'main')
    old_call = copy.deepcopy(call)
    constants = {'COMMON_PRICE_PROFILE': profile, 'QUARANTINE_CATALOG': catalog, 'VENDOR_SOURCE_CONTEXT': context}
    require(not any(isinstance(node, ast.Name) and node.id in constants for node in ast.walk(tree)), 'main')
    declarations = ast.parse('\n'.join(name + ' = ' + repr(value) for name, value in constants.items())).body
    index = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.ClassDef))
    tree.body[index:index] = declarations
    keys['profile'].value = ast.parse("COMMON_PRICE_PROFILE['strategy_profile']", mode='eval').body
    keys['fee_model_factory'].value = ast.parse('lambda: NewruleTenBpsFeeModel(self._driver)', mode='eval').body
    call.keywords.extend(ast.keyword(arg=name, value=ast.Name(id=constant, ctx=ast.Load()))
        for name, constant in (('common_profile', 'COMMON_PRICE_PROFILE'), ('vendor_source_context', 'VENDOR_SOURCE_CONTEXT'),
            ('quarantine_catalog', 'QUARANTINE_CATALOG')))
    position = next(i for i, key in enumerate(call.keywords) if key.arg == 'trade_bar_type') + 1
    call.keywords.insert(position, ast.keyword(arg='quote_bar_type', value=ast.Name(id='QuoteBar', ctx=ast.Load())))
    result = _normalize(ast.unparse(ast.fix_missing_locations(tree)).encode('ascii'), 'main.py')
    # Inverse proof: only declared Main import/fee/profile/seed/start changes.
    inverse = copy.deepcopy(tree)
    inverse.body = [node for node in inverse.body if not (isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in constants)]
    replacement = next(node for node in inverse.body if isinstance(node, ast.ImportFrom) and node.module == DRIVER_NAME[:-3])
    inverse.body[inverse.body.index(replacement)] = old_import
    replacement = _node(inverse, 'NewruleTenBpsFeeModel', ast.ClassDef)
    inverse.body[inverse.body.index(replacement)] = old_fee
    algo = _node(inverse, 'NewruleComparisonAlgorithm', ast.ClassDef)
    replacement = _node(algo, 'initialize', ast.FunctionDef); algo.body[algo.body.index(replacement)] = old_init
    require(_dump(inverse) == _dump(original), 'source_semantics')
    return result


def _source_records(source_pairs):
    return [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)} for name, raw in source_pairs]


def _cell_record(profile, source_pairs):
    return {'schema': CELL_SCHEMA, 'candidate_id': profile['candidate_id'], 'research_epoch_id': runtime.RESEARCH_EPOCH_ID,
        'runtime_project_id': profile['runtime_project_id'], 'universe_count': profile['universe_count'], 'ar_percent': profile['ar_percent'],
        'profile_sha256': profile['profile_sha256'], 'strategy_profile_sha256': profile['strategy_profile_sha256'],
        'quarantine_catalog_sha256': profile['quarantine_catalog_sha256'], 'quarantine_policy_sha256': profile['quarantine_policy_sha256'],
        'vendor_source_context_sha256': profile['vendor_source_context_sha256'], 'package_sha256': profile['package_sha256'],
        'lineage_sha256': profile['lineage_sha256'], 'activation_manifest_key': ACTIVATION[0],
        'activation_manifest_sha256': ACTIVATION[1], 'activation_manifest_byte_count': ACTIVATION[2],
        'engine_start_session': ENGINE_START_SESSION, 'evaluation_first': runtime.START_SESSION, 'evaluation_last': runtime.END_SESSION,
        'source_files': _source_records(source_pairs), 'host_source_pins': dict(HOST_SOURCE_PINS),
        'cloud_non_main_source_pins': dict(CLOUD_SOURCE_PINS), 'builder_profile_sha256': digest(profile_record()), **FALSE_FLAGS}


@dataclasses.dataclass(frozen=True, slots=True)
class Cell:
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_pairs: tuple = dataclasses.field(repr=False)
    template_source_bytes: bytes = dataclasses.field(repr=False)

    @property
    def projection_sha256(self): return sha(self.record_bytes)

    def to_record(self):
        record = _loads(self.record_bytes, MAX_RECORD_BYTES)
        profile = _loads(self.profile_bytes, MAX_SOURCE_BYTES)
        try: runtime.validate_profile(profile)
        except Exception: raise Refused('profile') from None
        pairs = _source_pairs(self.source_pairs, (*CLOUD_SOURCE_PINS, 'main.py'))
        require({name: sha(raw) for name, raw in self.source_pairs if name != 'main.py'} == CLOUD_SOURCE_PINS,
            'source_pin')
        require(profile['source_pins'] == CLOUD_SOURCE_PINS and all(raw.isascii() and 0 < len(raw) <= MAX_SOURCE_BYTES
            for _, raw in self.source_pairs), 'source_bound')
        constants = {}
        try:
            for node in ast.parse(pairs['main.py']).body:
                if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id in ('COMMON_PRICE_PROFILE', 'QUARANTINE_CATALOG', 'VENDOR_SOURCE_CONTEXT')):
                    require(node.targets[0].id not in constants, 'main'); constants[node.targets[0].id] = ast.literal_eval(node.value)
        except Refused: raise
        except (SyntaxError, ValueError, TypeError, RecursionError, UnicodeError): raise Refused('main') from None
        require(set(constants) == {'COMMON_PRICE_PROFILE', 'QUARANTINE_CATALOG', 'VENDOR_SOURCE_CONTEXT'}
            and constants['COMMON_PRICE_PROFILE'] == profile, 'main')
        try:
            catalog = quarantine.validate_quarantine_catalog(constants['QUARANTINE_CATALOG'], expected_sha256=profile['quarantine_catalog_sha256'])
            context = vendor.validate_source_context(constants['VENDOR_SOURCE_CONTEXT'])
        except Exception: raise Refused('catalog') from None
        require(context['runtime_project_id'] == profile['runtime_project_id']
            and digest(context) == profile['vendor_source_context_sha256'], 'context')
        require(pairs['main.py'] == _main(profile, catalog, context, self.template_source_bytes), 'main')
        require(self.record_bytes == canonical(_cell_record(profile, self.source_pairs)), 'cell')
        return record


@dataclasses.dataclass(frozen=True, slots=True)
class Batch:
    record_bytes: bytes = dataclasses.field(repr=False)
    cells: tuple = dataclasses.field(repr=False)

    @property
    def batch_sha256(self): return sha(self.record_bytes)

    def to_record(self):
        require(type(self.cells) is tuple and len(self.cells) == 6 and all(type(cell) is Cell for cell in self.cells), 'batch')
        records = [cell.to_record() for cell in self.cells]
        require([(row['universe_count'], row['ar_percent']) for row in records] == list(CELL_ORDER), 'batch')
        shared = tuple(pair for pair in self.cells[0].source_pairs if pair[0] != 'main.py')
        require(all(tuple(pair for pair in cell.source_pairs if pair[0] != 'main.py') == shared for cell in self.cells), 'batch')
        expected = {'schema': SCHEMA, 'cell_count': 6, 'cell_order': [list(cell) for cell in CELL_ORDER],
            'research_epoch_id': runtime.RESEARCH_EPOCH_ID, 'cells': records,
            'shared_non_main_source_files': _source_records(shared), 'all_sources_equal_except_main': True,
            'builder_profile_sha256': digest(profile_record()), **FALSE_FLAGS}
        require(len({row['candidate_id'] for row in records}) == len({row['profile_sha256'] for row in records}) == 6,
            'batch')
        for key in ('runtime_project_id', 'quarantine_catalog_sha256', 'quarantine_policy_sha256', 'vendor_source_context_sha256',
                    'package_sha256', 'lineage_sha256', 'activation_manifest_key', 'activation_manifest_sha256', 'activation_manifest_byte_count'):
            require(len({row[key] for row in records}) == 1, 'batch')
        _loads(self.record_bytes, MAX_RECORD_BYTES)
        require(self.record_bytes == canonical(expected), 'batch'); return expected


def prepare(source_pairs, *, expected_source_pins, session_axis, quarantine_catalog,
            expected_quarantine_catalog_sha256, runtime_project_id, vendor_source_context):
    """Bind a proposed project; no claim of current cloud access or run authority."""
    require(type(runtime_project_id) is int and 0 < runtime_project_id <= 2147483647, 'project')
    require(type(session_axis) is tuple and len(session_axis) == runtime.base.FULL_AXIS_COUNT
        and digest(list(session_axis)) == runtime.base.FULL_AXIS_SHA256, 'profile')
    cloud = _cloud_sources(source_pairs, expected_source_pins)
    try:
        catalog = quarantine.validate_quarantine_catalog(quarantine_catalog, expected_sha256=expected_quarantine_catalog_sha256)
        context = vendor.validate_source_context(vendor_source_context)
    except Exception: raise Refused('catalog') from None
    require(context['runtime_project_id'] == runtime_project_id, 'context')
    template = dict(source_pairs)[TEMPLATE_NAME]; cells = []
    for size, arm in CELL_ORDER:
        try:
            strategy = runtime.make_strategy_profile(session_axis, package_sha256=runtime.monetary.native.PACKAGE_SHA256,
                lineage_sha256=runtime.LINEAGE_SHA256, universe_count=size, ar_percent=arm,
                source_pins=dict(CLOUD_SOURCE_PINS), quarantine_catalog_sha256=expected_quarantine_catalog_sha256)
            profile = runtime.make_profile(strategy, runtime_project_id=runtime_project_id,
                vendor_source_context_sha256=digest(context), quarantine_catalog_sha256=expected_quarantine_catalog_sha256,
                source_pins=dict(CLOUD_SOURCE_PINS))
        except Exception: raise Refused('profile') from None
        main = _main(profile, catalog, context, template)
        output = tuple(sorted((*cloud, ('main.py', main))))
        require(len(output) == 20 and sum(len(raw) for _, raw in output) <= MAX_TOTAL_BYTES, 'source_bound')
        cell = Cell(canonical(_cell_record(profile, output)), canonical(profile), output, template)
        cell.to_record(); cells.append(cell)
    shared = tuple(pair for pair in cells[0].source_pairs if pair[0] != 'main.py')
    record = {'schema': SCHEMA, 'cell_count': 6, 'cell_order': [list(cell) for cell in CELL_ORDER],
        'research_epoch_id': runtime.RESEARCH_EPOCH_ID, 'cells': [cell.to_record() for cell in cells],
        'shared_non_main_source_files': _source_records(shared), 'all_sources_equal_except_main': True,
        'builder_profile_sha256': digest(profile_record()), **FALSE_FLAGS}
    require(len(canonical(record)) <= MAX_RECORD_BYTES, 'batch')
    result = Batch(canonical(record), tuple(cells)); result.to_record(); return result


def profile_record():
    return {'schema': SCHEMA, 'cell_schema': CELL_SCHEMA, 'cell_order': [list(c) for c in CELL_ORDER],
        'research_epoch_id': runtime.RESEARCH_EPOCH_ID, 'host_source_pins': dict(HOST_SOURCE_PINS),
        'cloud_non_main_source_pins': dict(CLOUD_SOURCE_PINS), 'cloud_source_count': 20,
        'maximum_cloud_source_bytes': MAX_SOURCE_BYTES, 'maximum_total_cloud_source_bytes': MAX_TOTAL_BYTES,
        'legacy_host_source_maximum_bytes': MAX_HOST_BYTES,
        'transforms': 'declared_plain_loader_flat_alias_frozen_AST_legacy_extraction_and_annotation_free_future_removal_only',
        'Main': 'exact_quarantine_driver_profiles_catalog_vendor_context_quote_fee_witness_RAW_no_seeding_2021Sep_warmup',
        'unchanged': 'input_loader_legacy_primitives_evaluator_and_all_nonMain_bytes_same_all_six',
        'activation': {'key': ACTIVATION[0], 'sha256': ACTIVATION[1], 'byte_count': ACTIVATION[2]},
        'private_catalog': 'supplied_values_embedded_only_in_returned_private_Main_never_public_metadata_or_module_literal',
        'prospective_project': 'positive_explicit_ID_only_not_current_access_capacity_rights_or_submission_authority',
        'old_W5_projection_invoked': False, 'native_source_context_required': False,
        'backtest_attempt_consumed': False, **FALSE_FLAGS}
