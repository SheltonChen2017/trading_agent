"""Pure no-order, exact-identity RAW Daily/Minute presence diagnostic.

This is neither R298 strategy continuation nor a source/price fallback. Only
public supplied source bytes are transformed; operational admission is external.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re

from scripts import arv2_newrule_quote_diagnostic_projection as parent
from scripts import arv2_newrule_reference_identity_projection as identity_parent


admission, comparison = parent.admission, parent.comparison
canonical = comparison.canonical
SCHEMA = 'arv2-r298-reference-feed-projection-v1'
PROFILE_SCHEMA = 'arv2-r298-reference-feed-profile-v1'
RESULT_SCHEMA = 'arv2-r298-reference-feed-result-v1'
PATCHER_NAME = 'arv2_r298_reference_feed_projection.py'
RUNTIME_NAME = parent.RUNTIME_NAME
META_STATISTIC = 'ARV2_REFERENCE_FEED_META'
PARENT_PROJECTION, PARENT_PROFILE, PARENT_MANIFEST = parent.PARENT_PROJECTION, parent.PARENT_PROFILE, parent.PARENT_MANIFEST
WITNESS = '9daff6253d858c3762ecb0f5fbe9d62cef6cb896afcb027693b5e3ea59dceb75'
SOURCE_ROW = '5d9097a2c0dfe4dc736eb28d38b8adbc9e2f6e1b6c2adfd1c67d00505adb0ef9'
BINDING_ROW = '1975b7c6f03af2f2dc22a8986144686c31cb468cf41db5849ba75e710e08e8b8'
AXIS = '4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
A19_LEGACY = '62a731eded8710f34c968f2ab61bc80052ad6486a2e41fa893e3ed8a9487ce84'
FALSE_FLAGS = {'price_fields_read': False, 'price_used': False, 'orders_submitted': False,
    'strategy_continued': False, 'strategy_result_accepted': False, 'family_comparable': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'independent_data_completeness_proven': False, 'provider_route_admitted': False}
FINITE = frozenset(('bytes', 'patcher_pin', 'source_pairs', 'parent_manifest', 'parent_profile',
    'activation', 'source_bound', 'parent_projection', 'projection_pin', 'projection_packet',
    'profile', 'result', 'result_bound'))
FAILURE_CODES = ('feed_profile', 'feed_clock', 'feed_live', 'feed_orders', 'feed_package',
    'feed_calendar', 'feed_catalog', 'feed_witness', 'feed_resolution', 'feed_subscription',
    'feed_once', 'feed_result')
CONTEXT_SCHEMA = 'arv2-reference-feed-finite-errors-only-v1'


class Refused(ValueError):
    pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def sha(raw):
    require(type(raw) is bytes, 'bytes')
    return hashlib.sha256(raw).hexdigest()


def policy_record():
    return {'purpose': 'exact_missing_identity_Daily_vs_Minute_feed_presence_not_price_recovery',
        'observation_clock': 'actual_2022-10-24_0000_America_New_York_in_initialize',
        'identity_witness_decision_clock': '2022-10-24_0920_not_actual_observation_clock',
        'reference_session': '2022-10-21', 'decision_session': '2022-10-24',
        'explicit_history_calls_maximum': 2, 'history_types': ['TradeBar_DAILY', 'TradeBar_MINUTE'],
        'daily_window': '2022-10-21_0000_through_2022-10-22_0000_NY',
        'minute_window': '2022-10-21_0930_through_2022-10-21_1600_NY',
        'daily_maximum_batches_and_items': 1, 'minute_maximum_batches_and_items': 390,
        'normalization': 'RAW', 'fill_forward': False, 'extended_market_hours': False,
        'seed_initial_prices': False, 'full_input_binding_count': 6151,
        'benchmark_identity': 'native_Symbol_create_SPY_only_no_explicit_SPY_subscription',
        'explicit_selected_security_subscriptions': 1,
        'price_access_scope': 'generated_main_and_runtime_only_engine_internals_unmeasured',
        'clock_zone_witness': 'exact_NodaTime_ToString_of_algorithm.time_zone_and_security.exchange.hours.time_zone_equal_America_New_York',
        'one_metadata_statistic_maximum_bytes': 8192,
        'count_390_is_independent_completeness_proof': False, 'diagnostic_only': True,
        'new_strategy_candidate': False, 'new_provider_request': False, **FALSE_FLAGS}


RUNTIME_SOURCE = '''import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
try:
    import accepted_risk_order_level_input_runtime as inputs
    import accepted_risk_preliminary_qc_figi as figi
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_plain_input_runtime as inputs
    from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi

META_STATISTIC = "ARV2_REFERENCE_FEED_META"
NY = ZoneInfo("America/New_York")
WITNESS = "9daff6253d858c3762ecb0f5fbe9d62cef6cb896afcb027693b5e3ea59dceb75"
SOURCE_ROW = "5d9097a2c0dfe4dc736eb28d38b8adbc9e2f6e1b6c2adfd1c67d00505adb0ef9"
BINDING_ROW = "1975b7c6f03af2f2dc22a8986144686c31cb468cf41db5849ba75e710e08e8b8"
AXIS = "4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585"

def require(value, code):
    if not value:
        raise RuntimeError(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def instant(value):
    require(isinstance(value, datetime), "feed_clock")
    return value.replace(tzinfo=NY) if value.tzinfo is None else value.astimezone(NY)

def sid(symbol):
    return figi._symbol_identity(symbol, "feed identity")[0]

def day(value):
    reference = datetime(2022, 10, 21).date()
    return "before_reference" if value.date() < reference else "exact_reference" if value.date() == reference else "after_reference"

def session_bucket(value):
    clock = value.time().replace(tzinfo=None)
    opening, closing = datetime(2022, 10, 21, 9, 30).time(), datetime(2022, 10, 21, 16).time()
    return "before_open" if clock < opening else "at_open" if clock == opening else "inside_regular" if clock < closing else "at_close" if clock == closing else "after_close"

def blank(cap):
    return {"status": "not_started", "call_invoked": False, "batches": 0, "items": 0,
        "maximum": cap, "duplicate_count": 0, "sid_mismatch_count": 0,
        "fill_forward_count": 0, "fill_forward_unknown_count": 0, "invalid_metadata_count": 0,
        "valid_regular_minute_count": 0, "valid_daily_bar_count": 0,
        "minute_grid_complete": False, "first_minute_endpoint_present": False,
        "last_regular_endpoint_present": False,
        "batch_day": {key: 0 for key in ("before_reference", "exact_reference", "after_reference")},
        "time_day": {key: 0 for key in ("before_reference", "exact_reference", "after_reference")},
        "end_day": {key: 0 for key in ("before_reference", "exact_reference", "after_reference")},
        "time_session": {key: 0 for key in ("before_open", "at_open", "inside_regular", "at_close", "after_close")},
        "end_session": {key: 0 for key in ("before_open", "at_open", "inside_regular", "at_close", "after_close")},
        "period": {key: 0 for key in ("one_minute", "regular_session", "one_day", "other", "invalid")}}

class ReferenceFeedDiagnostic:
    def __init__(self, algorithm, *, profile, activation_manifest_key,
                 activation_manifest_sha256, activation_manifest_byte_count,
                 benchmark_symbol, trade_bar_type, minute_resolution, daily_resolution, raw_normalization):
        seed = dict(profile)
        supplied = seed.pop("profile_sha256", None)
        require(digest(seed) == supplied and seed.get("schema") == "arv2-r298-reference-feed-profile-v1", "feed_profile")
        self.algorithm, self.profile = algorithm, json.loads(canonical(profile))
        self.activation = (activation_manifest_key, activation_manifest_sha256, activation_manifest_byte_count)
        self.benchmark, self.trade_type = benchmark_symbol, trade_bar_type
        self.minute, self.daily, self.raw = minute_resolution, daily_resolution, raw_normalization
        self.started = self.emitted = False

    def no_orders(self):
        require(self.algorithm.live_mode is False, "feed_live")
        require(not tuple(self.algorithm.transactions.get_orders()), "feed_orders")
        require(all(holding.quantity == 0 for _, holding in self.algorithm.portfolio.items()), "feed_orders")

    def observe(self, symbol, resolution, start, end, cap):
        record = blank(cap)
        try:
            typed = self.algorithm.history[self.trade_type]
            if not callable(typed):
                record["status"] = "lookup_failed"
                return record
        except Exception:
            record["status"] = "lookup_failed"
            return record
        record["call_invoked"] = True
        try:
            response = typed([symbol], start, end, resolution, fill_forward=False,
                extended_market_hours=False, data_normalization_mode=self.raw)
        except Exception:
            record["status"] = "call_failed"
            return record
        seen, minute_indices = set(), set()
        try:
            batches = iter(response)
            for index in range(cap + 1):
                try:
                    batch = next(batches)
                except StopIteration:
                    record["status"] = "complete"
                    record["minute_grid_complete"] = cap == 390 and len(minute_indices) == 390
                    return record
                if index == cap:
                    record["status"] = "bound_exceeded"
                    return record
                record["batches"] += 1
                batch_time = instant(batch.time)
                record["batch_day"][day(batch_time)] += 1
                entries = iter(batch.items())
                for entry_index in range(2):
                    try:
                        key, bar = next(entries)
                    except StopIteration:
                        break
                    if entry_index or record["items"] == cap:
                        record["status"] = "bound_exceeded"
                        return record
                    record["items"] += 1
                    if not isinstance(bar, self.trade_type):
                        record["invalid_metadata_count"] += 1
                        continue
                    same = sid(key) == sid(symbol) and sid(bar.symbol) == sid(symbol)
                    record["sid_mismatch_count"] += int(not same)
                    left, right = instant(bar.time), instant(bar.end_time)
                    record["time_day"][day(left)] += 1
                    record["end_day"][day(right)] += 1
                    record["time_session"][session_bucket(left)] += 1
                    record["end_session"][session_bucket(right)] += 1
                    seconds = (right - left).total_seconds()
                    period = "one_minute" if seconds == 60 else "regular_session" if seconds == 23400 else "one_day" if seconds == 86400 else "other" if seconds > 0 else "invalid"
                    record["period"][period] += 1
                    flag = bar.is_fill_forward
                    record["fill_forward_count"] += int(flag is True)
                    record["fill_forward_unknown_count"] += int(flag is not True and flag is not False)
                    identity = (sid(key), left, right)
                    duplicate = identity in seen
                    record["duplicate_count"] += int(duplicate)
                    seen.add(identity)
                    reference = datetime(2022, 10, 21).date()
                    opening = datetime(2022, 10, 21, 9, 30, tzinfo=NY)
                    grid_offset = (left - opening).total_seconds()
                    grid_index = int(grid_offset // 60)
                    if (same and not duplicate and flag is False and period == "one_minute"
                            and resolution == self.minute and left.second == right.second == 0
                            and left.microsecond == right.microsecond == 0
                            and grid_offset == grid_index * 60 and 0 <= grid_index <= 389
                            and grid_index not in minute_indices
                            and left.date() == right.date() == reference
                            and session_bucket(left) in ("at_open", "inside_regular")
                            and session_bucket(right) in ("inside_regular", "at_close")
                            and batch_time == right):
                        minute_indices.add(grid_index)
                        record["valid_regular_minute_count"] += 1
                        record["first_minute_endpoint_present"] |= grid_index == 0
                        record["last_regular_endpoint_present"] |= grid_index == 389
                    if (same and not duplicate and flag is False and resolution == self.daily
                            and batch_time == right
                            and ((left == datetime(2022, 10, 21, tzinfo=NY)
                                and right == datetime(2022, 10, 22, tzinfo=NY))
                                or (left == opening and right == datetime(2022, 10, 21, 16, tzinfo=NY)))):
                        record["valid_daily_bar_count"] += 1
                        record["last_regular_endpoint_present"] |= right == datetime(2022, 10, 21, 16, tzinfo=NY)
            record["status"] = "bound_exceeded"
        except Exception:
            record["status"] = "read_failed"
        return record

    def initialize(self):
        require(not self.started and not self.emitted, "feed_once")
        self.started = True
        self.no_orders()
        require(instant(self.algorithm.time) == datetime(2022, 10, 24, tzinfo=NY), "feed_clock")
        package = inputs.load_accepted_risk_preliminary_package(self.algorithm,
            activation_manifest_key=self.activation[0], activation_manifest_sha256=self.activation[1],
            activation_manifest_byte_count=self.activation[2])
        require(package.package_sha256 == self.profile["package_sha256"]
            and package.activation_manifest_sha256 == self.activation[1], "feed_package")
        axis = tuple(package.evaluator_input.session_axis)
        require(digest(list(axis)) == AXIS and axis[axis.index("2022-10-24") - 1] == "2022-10-21", "feed_calendar")
        lineage = dict(package.evaluator_input.source_lineage_sha256s)
        rows = package.runtime_symbol_bindings
        require(len(rows) == 6151, "feed_catalog")
        resolution = figi.resolve_preliminary_qc_figis(rows,
            expected_security_master_admission_sha256=lineage["security_master_admission_sha256"],
            composite_figi=self.algorithm.composite_figi, benchmark_symbol=self.benchmark)
        require(resolution.input_row_count == 6151
            and resolution.resolved_count + resolution.named_refusal_count == 6151, "feed_resolution")
        selected = [row for row in rows if digest({"schema": "arv2-missing-reference-identity-v1",
            "security_id": row["security_id"], "reference_session": "2022-10-21", "decision_session": "2022-10-24"}) == WITNESS]
        require(len(selected) == 1, "feed_witness")
        row = figi._input_row(selected[0], lineage["security_master_admission_sha256"])
        require(row["source_row_sha256"] == SOURCE_ROW and digest(row) == BINDING_ROW, "feed_witness")
        symbol = resolution.symbol_for_security(row["security_id"])
        require(symbol is not None, "feed_resolution")
        expected_sid = sid(symbol)
        security = self.algorithm.add_security(symbol, self.minute, False, 1, False)
        security.set_data_normalization_mode(self.raw)
        require(sid(security.symbol) == expected_sid, "feed_subscription")
        subscription = {"raw": security.data_normalization_mode == self.raw,
            "minute_subscription_requested": True, "fill_forward_requested": False,
            "extended_market_hours_requested": False,
            "algorithm_timezone_ny": str(self.algorithm.time_zone) == "America/New_York",
            "security_exchange_timezone_ny": str(security.exchange.hours.time_zone) == "America/New_York"}
        require(subscription["raw"] is True and subscription["algorithm_timezone_ny"] is True
            and subscription["security_exchange_timezone_ny"] is True, "feed_subscription")
        daily = self.observe(symbol, self.daily, datetime(2022, 10, 21), datetime(2022, 10, 22), 1)
        minute = self.observe(symbol, self.minute, datetime(2022, 10, 21, 9, 30), datetime(2022, 10, 21, 16), 390)
        self.no_orders()
        result = {"schema": "arv2-r298-reference-feed-result-v1", "profile_sha256": self.profile["profile_sha256"],
            "identity_sha256": WITNESS, "source_row_sha256": SOURCE_ROW, "whole_binding_row_sha256": BINDING_ROW,
            "session_axis_sha256": AXIS, "actual_observation_clock": "2022-10-24_0000_NY_initialize",
            "input_binding_count": 6151, "resolved_count": resolution.resolved_count,
            "named_refusal_count": resolution.named_refusal_count,
            "explicit_history_calls": int(daily["call_invoked"]) + int(minute["call_invoked"]),
            "daily": daily, "minute": minute, "subscription": subscription,
            "diagnostic_complete": daily["status"] == minute["status"] == "complete", "diagnostic_only": True,
            "price_fields_read": False, "price_used": False, "orders_submitted": False,
            "strategy_continued": False, "strategy_result_accepted": False, "family_comparable": False,
            "point_in_time_proven": False, "formal_identity_admitted": False,
            "formal_forward_ready": False, "paper_or_live_ready": False,
            "independent_data_completeness_proven": False, "provider_route_admitted": False}
        raw = canonical(result)
        require(len(raw) <= 8192, "feed_result")
        self.algorithm.set_summary_statistic(META_STATISTIC, raw.decode("ascii"))
        self.emitted = True
        return result

    def on_end(self):
        self.no_orders()
        require(self.started and self.emitted, "feed_once")
'''


def _runtime():
    tree = ast.parse(RUNTIME_SOURCE)
    raw = (ast.unparse(tree) + '\n').encode('ascii')
    forbidden = {'market_order', 'set_holdings', 'liquidate', 'add_data', 'download', 'history_request',
        'open', 'close', 'high', 'low', 'price', 'value', 'volume', 'set_market_price'}
    require(not any(isinstance(node, ast.Attribute) and node.attr in forbidden for node in ast.walk(tree)), 'source_bound')
    compile(raw, RUNTIME_NAME, 'exec')
    return raw


def profile_digest(profile):
    require(type(profile) is dict, 'profile')
    seed = dict(profile)
    seed.pop('profile_sha256', None)
    return sha(canonical(seed))


def _profile(patcher_pin, runtime_pin):
    seed = {'schema': PROFILE_SCHEMA, 'candidate_id': 'R298_REFERENCE_FEED_V1',
        'package_sha256': comparison.PLAIN_PACKAGE_SHA256, 'lineage_sha256': comparison.bridge.parent.LINEAGE,
        'parent_projection_sha256': PARENT_PROJECTION, 'parent_profile_sha256': PARENT_PROFILE,
        'identity_sha256': WITNESS, 'source_row_sha256': SOURCE_ROW, 'whole_binding_row_sha256': BINDING_ROW,
        'session_axis_sha256': AXIS, 'activation': list(comparison.PLAIN_ACTIVATION),
        'source_pins': {**comparison.bridge.parent.SOURCE_PINS, **comparison.NEW_SOURCE_PINS,
            'newrule_legacy_primitives.py': A19_LEGACY,
            RUNTIME_NAME: runtime_pin, PATCHER_NAME: patcher_pin}, 'policy': policy_record()}
    return {**seed, 'profile_sha256': sha(canonical(seed))}


def profile_record(*, patcher_sha256):
    require(type(patcher_sha256) is str and re.fullmatch('[0-9a-f]{64}', patcher_sha256), 'patcher_pin')
    return _profile(patcher_sha256, sha(_runtime()))


def _main(profile):
    key, pin, count = comparison.PLAIN_ACTIVATION
    raw = f'''from AlgorithmImports import *
from newrule_comparison_qc_runtime import ReferenceFeedDiagnostic
FEED_PROFILE = {profile!r}
class ReferenceFeedAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.settings.seed_initial_prices = False
        self.set_start_date(2022, 10, 24)
        self.set_end_date(2022, 10, 24)
        self.set_cash(1000000)
        benchmark = Symbol.create("SPY", SecurityType.EQUITY, Market.USA)
        self._feed = ReferenceFeedDiagnostic(self, profile=FEED_PROFILE,
            activation_manifest_key={key!r}, activation_manifest_sha256={pin!r}, activation_manifest_byte_count={count},
            benchmark_symbol=benchmark, trade_bar_type=TradeBar, minute_resolution=Resolution.MINUTE,
            daily_resolution=Resolution.DAILY, raw_normalization=DataNormalizationMode.RAW)
        self._feed.initialize()
    def on_end_of_algorithm(self):
        self._feed.on_end()
'''.encode('ascii')
    raw = (ast.unparse(ast.parse(raw)) + '\n').encode('ascii')
    compile(raw, 'main.py', 'exec')
    return raw


@dataclasses.dataclass(frozen=True, slots=True)
class FeedProjection:
    projection_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_pairs: tuple = dataclasses.field(repr=False)

    def to_record(self):
        record, profile, _ = validate_public_projection(self.record_bytes, self.source_pairs,
            expected_projection_sha256=self.projection_sha256,
            expected_profile_sha256=json.loads(self.profile_bytes)['profile_sha256'])
        require(canonical(profile) == self.profile_bytes, 'profile')
        return record


def _pairs(value):
    require(type(value) is tuple and len(value) == 11
        and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str
            and type(item[1]) is bytes and item[1].isascii() and 0 < len(item[1]) <= 64000 for item in value)
        and tuple(name for name, _ in value) == comparison.bridge.parent.FILE_NAMES
        and sum(len(raw) for _, raw in value) <= 448 * 1024, 'source_pairs')
    return value


def public_specification(source_pairs, *, patcher_source_bytes, expected_patcher_sha256):
    require(type(expected_patcher_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_patcher_sha256)
        and type(patcher_source_bytes) is bytes and 0 < len(patcher_source_bytes) <= 100000
        and patcher_source_bytes.isascii() and sha(patcher_source_bytes) == expected_patcher_sha256, 'patcher_pin')
    source_pairs = _pairs(source_pairs)
    old = dict(source_pairs)
    manifest = {'project_id': 38364439, 'projection_sha256': PARENT_PROJECTION,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)} for name, raw in source_pairs]}
    require(sha(canonical(manifest) + b'\n') == PARENT_MANIFEST, 'parent_manifest')
    keywords = parent._driver(ast.parse(old['main.py']))
    old_profile = ast.literal_eval(keywords['profile'].value)
    require(old_profile['profile_sha256'] == PARENT_PROFILE, 'parent_profile')
    require(all(ast.literal_eval(keywords[name].value) == expected for name, expected in zip(
        ('activation_manifest_key', 'activation_manifest_sha256', 'activation_manifest_byte_count'),
        comparison.PLAIN_ACTIVATION, strict=True)), 'activation')
    runtime = _runtime()
    # Preserve the exact currently uploaded A19 legacy file.  Both frozen
    # transformations are pure and source-bound; their operational readers are
    # not invoked. This legacy code is never instantiated by the new runtime.
    legacy = identity_parent._legacy(identity_parent.parent._legacy(old['newrule_legacy_primitives.py']))
    require(sha(legacy) == A19_LEGACY, 'parent_manifest')
    profile = _profile(expected_patcher_sha256, sha(runtime))
    main = _main(profile)
    pairs = tuple((name, runtime if name == RUNTIME_NAME else main if name == 'main.py'
                  else legacy if name == 'newrule_legacy_primitives.py' else raw)
        for name, raw in source_pairs)
    _pairs(pairs)
    record = {'schema': SCHEMA, 'candidate_id': 'R298_REFERENCE_FEED_V1',
        'parent_projection_sha256': PARENT_PROJECTION, 'parent_profile_sha256': PARENT_PROFILE,
        'parent_source_manifest_sha256': PARENT_MANIFEST, 'profile_sha256': profile['profile_sha256'],
        'patcher_sha256': expected_patcher_sha256, 'package_sha256': comparison.PLAIN_PACKAGE_SHA256,
        'policy': policy_record(), 'diagnostic_only': True,
        'unchanged_comparison_basis': 'current_A19_cloud_source',
        'preserved_a19_legacy_sha256': A19_LEGACY,
        'unchanged_cloud_files': [name for name in comparison.bridge.parent.FILE_NAMES if name not in (RUNTIME_NAME, 'main.py')],
        'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)} for name, raw in pairs],
        **FALSE_FLAGS}
    result = FeedProjection(sha(canonical(record)), canonical(record), canonical(profile), pairs)
    result.to_record()
    return result


def build_projection(packet, *, patcher_source_bytes, expected_patcher_sha256):
    raw, pairs = admission.validate_packet(packet)
    require(sha(raw) == PARENT_PROJECTION, 'parent_projection')
    return public_specification(pairs, patcher_source_bytes=patcher_source_bytes,
        expected_patcher_sha256=expected_patcher_sha256)


def validate_public_projection(record_bytes, source_pairs, *, expected_projection_sha256, expected_profile_sha256):
    require(type(record_bytes) is bytes and 0 < len(record_bytes) <= 128 * 1024
        and sha(record_bytes) == expected_projection_sha256, 'projection_pin')
    pairs = _pairs(source_pairs)
    try:
        record = json.loads(record_bytes)
        require(type(record) is dict and canonical(record) == record_bytes, 'projection_packet')
        files = dict(pairs)
        assignments = [node for node in ast.parse(files['main.py']).body if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'FEED_PROFILE']
        require(len(assignments) == 1, 'profile')
        profile = ast.literal_eval(assignments[0].value)
        expected = _profile(record['patcher_sha256'], sha(_runtime()))
        require(canonical(profile) == canonical(expected) and profile['profile_sha256'] == expected_profile_sha256,
            'profile')
        expected_record = {'schema': SCHEMA, 'candidate_id': 'R298_REFERENCE_FEED_V1',
            'parent_projection_sha256': PARENT_PROJECTION, 'parent_profile_sha256': PARENT_PROFILE,
            'parent_source_manifest_sha256': PARENT_MANIFEST, 'profile_sha256': expected_profile_sha256,
            'patcher_sha256': record['patcher_sha256'], 'package_sha256': comparison.PLAIN_PACKAGE_SHA256,
            'policy': policy_record(), 'diagnostic_only': True,
            'unchanged_comparison_basis': 'current_A19_cloud_source',
            'preserved_a19_legacy_sha256': A19_LEGACY,
            'unchanged_cloud_files': [name for name in comparison.bridge.parent.FILE_NAMES if name not in (RUNTIME_NAME, 'main.py')],
            'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)} for name, raw in pairs],
            **FALSE_FLAGS}
        require(canonical(record) == canonical(expected_record) and files[RUNTIME_NAME] == _runtime()
            and files['main.py'] == _main(profile)
            and sha(files['newrule_legacy_primitives.py']) == A19_LEGACY, 'projection_packet')
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, RecursionError):
        raise Refused('projection_packet') from None
    return record, profile, pairs


def parse_failure_context(value): return None


def validate_failure_context(value): raise Refused('result')


def validate_result_statistics(statistics, *, expected_profile):
    require(type(statistics) is dict and META_STATISTIC in statistics
        and type(statistics[META_STATISTIC]) is str and statistics[META_STATISTIC].isascii()
        and 0 < len(statistics[META_STATISTIC]) <= 8192, 'result_bound')
    try:
        value = json.loads(statistics[META_STATISTIC])
        require(canonical(value).decode('ascii') == statistics[META_STATISTIC], 'result')
        fixed = {'schema': RESULT_SCHEMA, 'profile_sha256': expected_profile['profile_sha256'],
            'identity_sha256': WITNESS, 'source_row_sha256': SOURCE_ROW, 'whole_binding_row_sha256': BINDING_ROW,
            'session_axis_sha256': AXIS, 'actual_observation_clock': '2022-10-24_0000_NY_initialize',
            'input_binding_count': 6151, 'diagnostic_only': True, **FALSE_FLAGS}
        require(type(value) is dict and set(value) == {*fixed, 'resolved_count', 'named_refusal_count',
            'explicit_history_calls', 'daily', 'minute', 'subscription', 'diagnostic_complete'}
            and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()), 'result')
        subscription = {'raw': True, 'minute_subscription_requested': True,
            'fill_forward_requested': False, 'extended_market_hours_requested': False,
            'algorithm_timezone_ny': True, 'security_exchange_timezone_ny': True}
        require(all(type(value[key]) is int and 0 <= value[key] <= 6151 for key in ('resolved_count', 'named_refusal_count'))
            and value['resolved_count'] > 0 and value['resolved_count'] + value['named_refusal_count'] == 6151
            and type(value['subscription']) is dict and set(value['subscription']) == set(subscription)
            and all(value['subscription'][key] is item for key, item in subscription.items()), 'result')
        for kind, cap in (('daily', 1), ('minute', 390)):
            row = value[kind]
            integers = ('batches', 'items', 'duplicate_count', 'sid_mismatch_count', 'fill_forward_count',
                'fill_forward_unknown_count', 'invalid_metadata_count', 'valid_regular_minute_count', 'valid_daily_bar_count')
            groups = {'batch_day': ('before_reference', 'exact_reference', 'after_reference'),
                'time_day': ('before_reference', 'exact_reference', 'after_reference'),
                'end_day': ('before_reference', 'exact_reference', 'after_reference'),
                'time_session': ('before_open', 'at_open', 'inside_regular', 'at_close', 'after_close'),
                'end_session': ('before_open', 'at_open', 'inside_regular', 'at_close', 'after_close'),
                'period': ('one_minute', 'regular_session', 'one_day', 'other', 'invalid')}
            require(type(row) is dict and set(row) == {'status', 'call_invoked', 'maximum',
                'first_minute_endpoint_present', 'last_regular_endpoint_present', 'minute_grid_complete', *integers, *groups}
                and row['status'] in ('lookup_failed', 'call_failed', 'complete', 'bound_exceeded', 'read_failed')
                and type(row['call_invoked']) is bool and type(row['maximum']) is int and row['maximum'] == cap
                and all(type(row[key]) is int and 0 <= row[key] <= cap for key in integers)
                and type(row['first_minute_endpoint_present']) is bool
                and type(row['last_regular_endpoint_present']) is bool
                and type(row['minute_grid_complete']) is bool, 'result')
            for key, names in groups.items():
                group = row[key]
                require(type(group) is dict and set(group) == set(names)
                    and all(type(item) is int and 0 <= item <= cap for item in group.values())
                    and sum(group.values()) <= (row['batches'] if key == 'batch_day' else row['items']), 'result')
            require(row['valid_regular_minute_count'] <= row['items']
                and row['valid_daily_bar_count'] <= row['items']
                and row['items'] <= row['batches']
                and row['valid_regular_minute_count'] <= min(row['time_day']['exact_reference'],
                    row['end_day']['exact_reference'], row['period']['one_minute'],
                    row['batch_day']['exact_reference'],
                    row['time_session']['at_open'] + row['time_session']['inside_regular'],
                    row['end_session']['inside_regular'] + row['end_session']['at_close'])
                and row['valid_daily_bar_count'] <= row['period']['regular_session'] + row['period']['one_day']
                and row['valid_daily_bar_count'] <= min(row['time_day']['exact_reference'],
                    row['end_day']['exact_reference'] + row['end_day']['after_reference'],
                    row['batch_day']['exact_reference'] + row['batch_day']['after_reference'])
                and row['duplicate_count'] <= row['items']
                and all(row[key] <= row['items'] for key in ('sid_mismatch_count', 'fill_forward_count',
                    'fill_forward_unknown_count', 'invalid_metadata_count'))
                and all(row['valid_regular_minute_count'] + row['valid_daily_bar_count'] + row[key] <= row['items']
                    for key in ('duplicate_count', 'sid_mismatch_count', 'fill_forward_count',
                        'fill_forward_unknown_count', 'invalid_metadata_count'))
                and (row['first_minute_endpoint_present'] is False or row['valid_regular_minute_count'] > 0)
                and (row['first_minute_endpoint_present'] is False or
                    (row['time_session']['at_open'] > 0 and row['end_session']['inside_regular'] > 0))
                and (row['last_regular_endpoint_present'] is False
                    or row['valid_regular_minute_count'] + row['valid_daily_bar_count'] > 0)
                and (row['last_regular_endpoint_present'] is False or row['end_session']['at_close'] > 0)
                and (row['status'] not in ('lookup_failed', 'call_failed') or
                    (all(row[key] == 0 for key in integers) and all(sum(row[key].values()) == 0 for key in groups)
                    and row['first_minute_endpoint_present'] is False
                    and row['last_regular_endpoint_present'] is False and row['minute_grid_complete'] is False))
                and (kind != 'daily' or (row['valid_regular_minute_count'] == 0 and row['minute_grid_complete'] is False
                    and row['first_minute_endpoint_present'] is False))
                and (kind != 'minute' or row['valid_daily_bar_count'] == 0)
                and (row['minute_grid_complete'] is False or (kind == 'minute' and row['status'] == 'complete'
                    and row['valid_regular_minute_count'] == 390 and row['duplicate_count'] == 0
                    and row['sid_mismatch_count'] == row['fill_forward_count'] == row['fill_forward_unknown_count'] == 0
                    and row['batch_day']['exact_reference'] == 390
                    and row['time_session']['at_open'] == row['end_session']['at_close'] == 1
                    and row['time_session']['inside_regular'] == row['end_session']['inside_regular'] == 389
                    and row['first_minute_endpoint_present'] is True and row['last_regular_endpoint_present'] is True))
                and (row['status'] != 'lookup_failed' or row['call_invoked'] is False)
                and (row['status'] == 'lookup_failed' or row['call_invoked'] is True), 'result')
        require(type(value['explicit_history_calls']) is int and value['explicit_history_calls'] ==
            int(value['daily']['call_invoked']) + int(value['minute']['call_invoked'])
            and type(value['diagnostic_complete']) is bool and value['diagnostic_complete'] ==
            (value['daily']['status'] == value['minute']['status'] == 'complete'), 'result')
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('result') from None
    return json.loads(canonical(value))
