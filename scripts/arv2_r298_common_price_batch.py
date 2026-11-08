"""Pure six-cell public-source batch; no data reads, controls or operations.

All source bytes are supplied explicitly and must match the fixed public pins
below. Preparation authenticates proposed code and metadata only. The actual
project, processing rights, payload transfer, run freeze and result acceptance
remain separate operational gates.
"""
import dataclasses
import hashlib
import json

from research.analyst_revisions_v2_qc import newrule_plain_comparison as plain
from research.analyst_revisions_v2_qc import newrule_raw_vendor_price_book_runtime as vendor
from research.analyst_revisions_v2_qc import newrule_native_price_book_runtime as native
from scripts import arv2_r298_common_price_projection as common

SCHEMA = 'arv2-r298-common-price-six-cell-public-batch-v1'
CELL_ORDER = ((6, 0), (6, 100), (6, 200), (8, 0), (8, 100), (8, 200))
PUBLIC_SOURCE_PINS = {
    'accepted_risk_preliminary_rating_policy.py': '7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd',
    'accepted_risk_preliminary_rating_evaluator.py': '2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910',
    'accepted_risk_order_level_core.py': '063ed8fb7024c879a640780c07723c7edfb95665acc711d02fc8be0d964e965f',
    'accepted_risk_order_level_forced_exit.py': '21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f',
    'accepted_risk_order_level_input_runtime.py': 'a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee',
    'accepted_risk_preliminary_qc_figi.py': '4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9',
    'accepted_risk_six_universe_order_qc_runtime.py': '84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a',
    'accepted_risk_six_universe_order_qc_projection.py': '5037fdc1153c9ac927a540201fa92cb45db463e8313e0c88e04ddc9f0eb301f6',
    'accepted_risk_october_order_package.py': '655eec765a8b99d489881f7de7ddc339ab6b2c0bb0470feb814c6ef005d03c0a',
    'accepted_risk_preopen_rating_score.py': '67f86ffc696c036c7fbfef64ee00fb1ad1a8599727f5ef36762e329df85a023a',
    'newrule_comparison_targets.py': '30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d',
    'newrule_comparison_qc_runtime.py': '674415b3179836a613afc6f7bdea23a966db21ab67221472fc5d87b4a742049d',
    'newrule_comparison_projection.py': '4f51d1a9a50293f4fa39be297666c1e6144462abaa82e69e342845580a1a4076',
    'newrule_plain_transport.py': '4cf351095015fddb7a463692f6d789917d229966772e04a60de0c804ed965f5a',
    'newrule_plain_input_runtime.py': 'bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f',
    'newrule_plain_projection.py': 'a0152d0d4109584312ee1e5a2f91cc03bf97cbab6b0e2525dd4f968fa9bd9927',
    'newrule_plain_comparison.py': '7f6a23d157488ae5029510029811fced5c01a363bb5647a2667ed5fe8e92f407'}
ADDON_SOURCE_PINS = {
    'newrule_common_price_format.py': 'd254b3e3a6a52445e4422f03885ec58a3d2b30e8ce902cb80ed8f841c374f873',
    'newrule_native_price_source_diagnostic.py': '57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697',
    'newrule_native_price_book_publication.py': '03d100e962b98cd8b174d947a33636e421692445422c0dcce2282b46015435e2',
    'newrule_native_price_book_runtime.py': '76b2a193fe1b8de9c9f8c598464edc2d0058b61aa690e13cc6216051f862a3f6',
    'newrule_raw_vendor_price_book_runtime.py': 'c97c9d0d4874b85bd50676e3e87c54840be9f3eab952302deb42a301f67fc430',
    'newrule_common_price_qc_runtime.py': 'e9c79d20429b9041874e615a1e6ee06824c640c635ebe75c3868b53018350c89',
    'newrule_common_price_comparison_runtime.py': 'a608b90cad9be75ec06bd2ae42e040e25eb1c98fa8fb568ba1a648e662c25bcb'}
QUOTE_PATCHER_SHA256 = 'ebc6d921c5dbaa5e9bc83379ab45c167780fb87db8441dbd9d618b3efcb1715f'
COMMON_PATCHER_SHA256 = 'b3f21b8e05d77a71e97327b43406203797bc749b558dba7d4c05de00bca1454b'
AR_PUBLIC_ANCHOR_SOURCE_SHA256 = '52ae31ddb440e1ecaf693d54fb6cf6d48ee377813d8614e7ce3cee5a02d68d76'
AR_MANIFEST_PIN = {'byte_count': 22373, 'sha256': 'cf9a27d0c6ccd8ad65b676c6335de35ac6738579e49784cb532d790cf83e7189'}
AR_CATALOG_PIN = {'byte_count': 2224206, 'sha256': 'f55e44f85f39846f0b4946860318760eab68d10d95c79d2cf87da44ad9568cb1'}
MAX_PUBLIC_BYTES, MAX_BATCH_RECORD_BYTES = 2 * 1024 * 1024, 128 * 1024
FALSE_FLAGS = {'source_admission_granted': False, 'QC_processing_rights_granted': False,
    'QC_transfer_granted': False, 'backtest_created': False, 'strategy_result_accepted': False,
    'family_comparable': False, 'complete_price_coverage_proven': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('source_inventory', 'source_pin', 'source_bound', 'context', 'project',
    'quote', 'cell', 'geometry', 'common_sources', 'batch', 'unknown'))


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(canonical(value))
def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}


def _sources(public_sources, addon_source_pairs, quote_raw, common_raw):
    require(type(public_sources) is dict and set(public_sources) == set(PUBLIC_SOURCE_PINS), 'source_inventory')
    require(type(addon_source_pairs) is tuple and len(addon_source_pairs) == len(common.ADDON_NAMES)
        and all(type(item) is tuple and len(item) == 2 for item in addon_source_pairs)
        and tuple(name for name, _ in addon_source_pairs) == common.ADDON_NAMES, 'source_inventory')
    addons = dict(addon_source_pairs)
    for sources, expected in ((public_sources, PUBLIC_SOURCE_PINS), (addons, ADDON_SOURCE_PINS)):
        for name, expected_sha in expected.items():
            raw = sources[name]
            require(type(raw) is bytes and raw.isascii() and 0 < len(raw) <= 100000, 'source_bound')
            require(sha(raw) == expected_sha, 'source_pin')
    for raw, expected_sha in ((quote_raw, QUOTE_PATCHER_SHA256), (common_raw, COMMON_PATCHER_SHA256)):
        require(type(raw) is bytes and raw.isascii() and 0 < len(raw) <= 100000, 'source_bound')
        require(sha(raw) == expected_sha, 'source_pin')
    require(sum(len(raw) for raw in public_sources.values()) + sum(len(raw) for raw in addons.values())
        + len(quote_raw) + len(common_raw) <= MAX_PUBLIC_BYTES, 'source_bound')


def _contexts(project_id, native_context, vendor_context):
    require(type(project_id) is int and 0 < project_id <= 2147483647, 'project')
    try:
        checked_native = native.validate_source_context(native_context)
        checked_vendor = vendor.validate_source_context(vendor_context)
    except Exception:
        raise Refused('context') from None
    require(checked_vendor['runtime_project_id'] == project_id, 'project')
    require(checked_vendor['manifest_pin'] == AR_MANIFEST_PIN and checked_vendor['catalog_pin'] == AR_CATALOG_PIN
        and checked_vendor['AP_fact_sha256'] == vendor.fmt.AP_FACT_SHA256
        and checked_vendor['AP_authentication_sha256'] == vendor.fmt.AP_AUTH_SHA256
        and checked_vendor['object_key_prefix'] == str(project_id) + '/arv2/r326-common/'
            + AR_MANIFEST_PIN['sha256'] + '/', 'context')
    return checked_native, checked_vendor


def _metadata(specs):
    require(type(specs) is tuple and len(specs) == 6 and all(type(spec) is common.Projection for spec in specs), 'batch')
    cells, shared, baseline_common, baseline_strategy = [], None, None, None
    project, native_context, vendor_context = None, None, None
    for (size, arm), spec in zip(CELL_ORDER, specs, strict=True):
        try:
            record = spec.to_record()
            profile = common.runtime.validate_profile(json.loads(spec.profile_bytes))
        except Exception:
            raise Refused('cell') from None
        strategy = profile['strategy_profile']
        require((profile['universe_count'], profile['ar_percent']) == (size, arm)
            and (strategy['universe_count'], strategy['ar_percent']) == (size, arm), 'geometry')
        same_common = {key: value for key, value in profile.items() if key not in {
            'candidate_id', 'profile_sha256', 'strategy_profile', 'strategy_profile_sha256', 'universe_count', 'ar_percent'}}
        same_strategy = {key: value for key, value in strategy.items() if key not in {
            'candidate_id', 'profile_sha256', 'universe_count', 'ar_percent'}}
        non_main = tuple((name, raw) for name, raw in spec.source_pairs if name != 'main.py')
        if shared is None:
            shared, baseline_common, baseline_strategy = non_main, same_common, same_strategy
            project = profile['runtime_project_id']
            native_context, vendor_context = profile['native_source_context_sha256'], profile['vendor_source_context_sha256']
            expected_vendor = {'schema': vendor.fmt.SCHEMA + '-QC-context', 'runtime_project_id': project,
                'manifest_pin': dict(AR_MANIFEST_PIN), 'catalog_pin': dict(AR_CATALOG_PIN),
                'object_key_prefix': str(project) + '/arv2/r326-common/' + AR_MANIFEST_PIN['sha256'] + '/',
                'AP_fact_sha256': vendor.fmt.AP_FACT_SHA256, 'AP_authentication_sha256': vendor.fmt.AP_AUTH_SHA256}
            require(native_context == native.SOURCE_CONTEXT_SHA256 and vendor_context == digest(expected_vendor), 'context')
        require(non_main == shared and same_common == baseline_common and same_strategy == baseline_strategy,
            'common_sources')
        manifest = {'schema': SCHEMA + '-source-manifest', 'runtime_project_id': project,
            'profile_sha256': profile['profile_sha256'], 'source_files': record['source_files']}
        cells.append({'universe_count': size, 'ar_percent': arm, 'candidate_id': profile['candidate_id'],
            'common_profile_sha256': profile['profile_sha256'], 'profile_pin': pin(spec.profile_bytes),
            'strategy_profile_sha256': strategy['profile_sha256'], 'projection_pin': pin(spec.record_bytes),
            'projection_sha256': spec.projection_sha256, 'source_manifest_pin': pin(canonical(manifest)),
            'main_pin': pin(dict(spec.source_pairs)['main.py']), 'source_file_count': len(spec.source_pairs),
            'total_source_byte_count': sum(len(raw) for _, raw in spec.source_pairs),
            'source_files': record['source_files']})
    require(len({row['common_profile_sha256'] for row in cells}) == 6
        and len({row['projection_sha256'] for row in cells}) == 6
        and len({row['main_pin']['sha256'] for row in cells}) == 6, 'geometry')
    shared_files = [{'project_path': name, **pin(raw)} for name, raw in shared]
    return {'schema': SCHEMA, 'runtime_project_id': project, 'cell_count': 6,
        'cell_order': [list(value) for value in CELL_ORDER], 'cells': cells,
        'native_source_context_sha256': native_context, 'vendor_source_context_sha256': vendor_context,
        'AR_public_anchor_source_sha256': AR_PUBLIC_ANCHOR_SOURCE_SHA256,
        'AR_manifest_pin': dict(AR_MANIFEST_PIN), 'AR_catalog_pin': dict(AR_CATALOG_PIN),
        'frozen_quote_projection_sha256': common.BASE_PROJECTION,
        'frozen_quote_profile_sha256': common.BASE_PROFILE,
        'frozen_quote_profile_bytes_sha256': common.BASE_PROFILE_BYTES_SHA256,
        'frozen_quote_base_sha256': common.runtime.FROZEN_BASE_SHA256,
        'public_source_pins': dict(sorted(PUBLIC_SOURCE_PINS.items())),
        'addon_source_pins': dict(ADDON_SOURCE_PINS), 'quote_patcher_sha256': QUOTE_PATCHER_SHA256,
        'common_patcher_sha256': COMMON_PATCHER_SHA256, 'shared_non_main_source_files': shared_files,
        'shared_source_policy_sha256': digest({'common': baseline_common, 'strategy': baseline_strategy,
            'shared_non_main_files': shared_files}), 'all18_sources_equal_except_Main': True,
        'same_source_policy_all_six_cells': True, **FALSE_FLAGS}


@dataclasses.dataclass(frozen=True, slots=True)
class Batch:
    batch_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    specs: tuple = dataclasses.field(repr=False)

    def to_record(self):
        require(type(self.record_bytes) is bytes and 0 < len(self.record_bytes) <= MAX_BATCH_RECORD_BYTES
            and sha(self.record_bytes) == self.batch_sha256, 'batch')
        record = _metadata(self.specs)
        require(canonical(record) == self.record_bytes, 'batch')
        return record


def prepare(public_sources, addon_source_pairs, *, quote_patcher_source_bytes,
            common_patcher_source_bytes, runtime_project_id, native_source_context, vendor_source_context):
    """Prepare all six public source specifications; no operational capability."""
    _sources(public_sources, addon_source_pairs, quote_patcher_source_bytes, common_patcher_source_bytes)
    native_context, vendor_context = _contexts(runtime_project_id, native_source_context, vendor_source_context)
    try:
        plain_spec = plain.public_specification(sources=public_sources,
            expected_host_source_pins={plain.HOST_SOURCE_NAME: PUBLIC_SOURCE_PINS[plain.HOST_SOURCE_NAME]})
        initial_pairs = tuple((row.project_path, row.source_bytes) for row in plain_spec.cells[0].source_files)
        quoted = common.frozen.public_specification(initial_pairs, patcher_source_bytes=quote_patcher_source_bytes,
            expected_patcher_sha256=QUOTE_PATCHER_SHA256)
        common.frozen.validate_public_projection(quoted.record_bytes, quoted.source_pairs,
            expected_projection_sha256=common.BASE_PROJECTION, expected_profile_sha256=common.BASE_PROFILE)
    except Exception:
        raise Refused('quote') from None
    axis = plain.bridge.frozen.october._sessions()
    specs = []
    for size, arm in CELL_ORDER:
        try:
            value = common.public_specification(quoted.record_bytes, quoted.source_pairs, addon_source_pairs,
                session_axis=axis, runtime_project_id=runtime_project_id, universe_count=size, ar_percent=arm,
                native_source_context=native_context, vendor_source_context=vendor_context,
                expected_addon_pins=dict(ADDON_SOURCE_PINS), patcher_source_bytes=common_patcher_source_bytes,
                expected_patcher_sha256=COMMON_PATCHER_SHA256)
        except Exception:
            raise Refused('cell') from None
        specs.append(value)
    cells = tuple(specs)
    raw = canonical(_metadata(cells))
    require(len(raw) <= MAX_BATCH_RECORD_BYTES, 'batch')
    return Batch(sha(raw), raw, cells)


def profile_record():
    return {'schema': SCHEMA, 'cell_order': [list(value) for value in CELL_ORDER],
        'public_source_pins': dict(sorted(PUBLIC_SOURCE_PINS.items())),
        'addon_source_pins': dict(ADDON_SOURCE_PINS), 'quote_patcher_sha256': QUOTE_PATCHER_SHA256,
        'common_patcher_sha256': COMMON_PATCHER_SHA256,
        'AR_public_anchor_source_sha256': AR_PUBLIC_ANCHOR_SOURCE_SHA256,
        'AR_manifest_pin': dict(AR_MANIFEST_PIN), 'AR_catalog_pin': dict(AR_CATALOG_PIN),
        'source_regeneration': '17_supplied_public_sources_plain_public_spec_then_quote_public_spec_no_old_admission',
        'source_policy': 'all18_modules_identical_except_Main_same_context_data_and_monetary_policy_all6',
        'future_project': 'explicit_positive_actual_projectID_requires_separate_external_ownership_run_freeze',
        'no_I_O_or_operational_entrypoint': True, **FALSE_FLAGS}
