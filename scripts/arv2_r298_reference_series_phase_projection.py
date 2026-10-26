"""Pure adjacent-series/native-identity/within-job-phase observation projection.

No strategy, vendor fallback, price field or operational capability is added.
Public supplied sources are authenticated; private admission remains external.
Initialize History is supported by LEAN; a measured phase contrast is not a
diagnosis of A19, which already failed later than Initialize.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import re

from scripts import arv2_r298_reference_feed_projection as previous


admission, comparison = previous.admission, previous.comparison
canonical, sha = previous.canonical, previous.sha
SCHEMA = 'arv2-r298-reference-series-phase-projection-v1'
PROFILE_SCHEMA = 'arv2-r298-reference-series-phase-profile-v1'
RESULT_SCHEMA = 'arv2-r298-reference-series-phase-result-v1'
PATCHER_NAME = 'arv2_r298_reference_series_phase_projection.py'
RUNTIME_NAME = previous.RUNTIME_NAME
META_STATISTIC = 'ARV2_REFERENCE_SERIES_PHASE_META'
MAX_STATISTIC_BYTES = 16384
PARENT_PROJECTION, PARENT_PROFILE, PARENT_MANIFEST = previous.PARENT_PROJECTION, previous.PARENT_PROFILE, previous.PARENT_MANIFEST
N_PATCHER = 'bb6750ad44ef1602ab96fa83df8b2df70d1d6cb9b90b616b93706ad75d4915bb'
N_PROJECTION = '5b7dfc6659944f7871d053a09b01deb8c46b7bb51b29cc03ddfdcdb9b2a4ef47'
N_PROFILE = '57b0a00db8de00985ed4bfb4bc3089135ce5b83d0544fd879d01ef6aa64afdf0'
N_MANIFEST = 'a3b0d898c36ccdd53fca9a91459806a82a726b7830b002daa88e04ceb76e1802'
WITNESS, SOURCE_ROW, BINDING_ROW, AXIS = previous.WITNESS, previous.SOURCE_ROW, previous.BINDING_ROW, previous.AXIS
SERIES_SESSIONS = ('2022-10-17', '2022-10-18', '2022-10-19', '2022-10-20', '2022-10-21', '2022-10-24')
PROBE_DATES = ('2020-11-01', '2022-10-21', '2022-10-24')
FALSE_FLAGS = {**previous.FALSE_FLAGS, 'historical_resolution_availability_proven': False,
    'alternate_resolved_symbol_used': False, 'a19_cause_authenticated': False,
    'initialize_history_unsupported_proven': False}
FINITE = previous.FINITE
FAILURE_CODES = previous.FAILURE_CODES + ('feed_missing_clock', 'feed_identity_metadata')
CONTEXT_SCHEMA = 'arv2-reference-series-phase-finite-errors-only-v1'
Refused, require, finite = previous.Refused, previous.require, previous.finite


def policy_record():
    return {'purpose': 'adjacent_series_and_native_identity_and_within_job_phase_not_price_recovery',
        'observation_session': '2022-10-25', 'initialize_clock': '2022-10-25_0000_NY',
        'post_clock': 'actual_non_fill_forward_SPY_2022-10-25_0930_to0931_OnData_only',
        'reference_session': '2022-10-21', 'witness_decision_session': '2022-10-24',
        'series_sessions': list(SERIES_SESSIONS), 'daily_window': '[2022-10-17_0000,2022-10-25_0000)_NY',
        'minute_window': '[2022-10-21_0930,2022-10-21_1600)_NY',
        'explicit_history_calls_maximum': 3, 'daily_maximum_batches_and_items': 6,
        'minute_maximum_batches_and_items_each': 390, 'normalization': 'RAW',
        'fill_forward': False, 'extended_market_hours': False, 'seed_initial_prices': False,
        'warmup': False, 'explicit_selected_security_subscriptions': 1, 'explicit_SPY_clock_subscriptions': 1,
        'dated_FIGI_probes': list(PROBE_DATES), 'dated_FIGI_alternate_symbol_use': False,
        'full_input_binding_count': 6151, 'native_SID_date_is_listing_proof': False,
        'daily_observed_buckets_before_validity': True, 'daily_precise_or_legacy_shapes_observed_separately': True,
        'actual_subscription_configs_verified': True, 'one_summary_key_maximum_updates': 2,
        'initialize_metadata_preserved_on_missing_postclock': True,
        'pending_or_refused_postphase_accepted': False, 'one_metadata_statistic_maximum_bytes': MAX_STATISTIC_BYTES,
        'initialize_history_supported_API_not_assumed_failure': True,
        'a19_original_failure_was_post_initialize': True,
        'price_access_scope': 'generated_main_runtime_only_platform_internals_unmeasured',
        'diagnostic_only': True, 'new_strategy_candidate': False, 'new_provider_request': False, **FALSE_FLAGS}


_OLD_TREE = ast.parse(previous.RUNTIME_SOURCE)
_OLD_CLASS = next(node for node in _OLD_TREE.body if isinstance(node, ast.ClassDef))
_SHARED_METHODS = '\n'.join(ast.unparse(next(node for node in _OLD_CLASS.body
    if isinstance(node, ast.FunctionDef) and node.name == name)) for name in ('no_orders', 'observe'))
_PRELUDE = previous.RUNTIME_SOURCE.split('class ReferenceFeedDiagnostic:', 1)[0].replace(
    'ARV2_REFERENCE_FEED_META', META_STATISTIC)

_NEW_METHODS = '''
def __init__(self, algorithm, *, profile, activation_manifest_key,
             activation_manifest_sha256, activation_manifest_byte_count,
             benchmark_symbol, clock_security, trade_bar_type, quote_bar_type,
             minute_resolution, daily_resolution, raw_normalization):
    seed = dict(profile)
    supplied = seed.pop("profile_sha256", None)
    require(digest(seed) == supplied and seed.get("schema") == "arv2-r298-reference-series-phase-profile-v1", "feed_profile")
    self.algorithm, self.profile = algorithm, json.loads(canonical(profile))
    self.activation = (activation_manifest_key, activation_manifest_sha256, activation_manifest_byte_count)
    self.benchmark, self.clock_security = benchmark_symbol, clock_security
    self.trade_type, self.quote_type = trade_bar_type, quote_bar_type
    self.minute, self.daily, self.raw = minute_resolution, daily_resolution, raw_normalization
    self.started, self.emitted, self.writes = False, False, 0
    self.result, self.symbol, self.native = None, None, None

def native_metadata(self, symbol):
    try:
        identifier = sid(symbol)
        display = symbol.value
        timestamp = symbol.id.date
        require(type(identifier) is str and 0 < len(identifier) <= 512
            and type(display) is str and 0 < len(display) <= 64
            and isinstance(timestamp, datetime), "feed_identity_metadata")
        value = timestamp.date().isoformat()
        reference = datetime(2022, 10, 21).date()
        relation = "before_reference" if timestamp.date() < reference else "exact_reference" if timestamp.date() == reference else "after_reference"
        return {"native_sid_sha256": digest({"schema": "arv2-native-SID-hash-v1", "sid": identifier}),
            "native_display_sha256": digest({"schema": "arv2-native-display-hash-v1", "display": display}),
            "native_sid_date_sha256": digest({"schema": "arv2-native-SID-date-hash-v1", "date": value}),
            "native_sid_date_relation": relation}
    except Exception:
        raise RuntimeError("feed_identity_metadata") from None

def dated_probe(self, figi_value, date_text):
    when = datetime.strptime(date_text, "%Y-%m-%d")
    require(instant(when) <= instant(self.algorithm.time), "feed_clock")
    record = {"trading_date": date_text, "status": "forward_failed", "metadata": None,
        "roundtrip_matches": False, "same_native_sid": False, "same_native_display": False}
    try:
        candidate = self.algorithm.composite_figi(figi_value, when)
    except Exception:
        return record
    if candidate is None:
        record["status"] = "unavailable"
        return record
    try:
        record["metadata"] = self.native_metadata(candidate)
    except Exception:
        record["status"] = "metadata_failed"
        return record
    record["same_native_sid"] = record["metadata"]["native_sid_sha256"] == self.native["native_sid_sha256"]
    record["same_native_display"] = record["metadata"]["native_display_sha256"] == self.native["native_display_sha256"]
    try:
        reversed_value = self.algorithm.composite_figi(candidate)
        record["roundtrip_matches"] = type(reversed_value) is str and reversed_value == figi_value
    except Exception:
        record["status"] = "reverse_failed"
        return record
    record["status"] = "observed"
    return record

def subscription(self, security):
    require(str(self.algorithm.time_zone) == "America/New_York"
        and str(security.exchange.hours.time_zone) == "America/New_York"
        and security.data_normalization_mode == self.raw, "feed_subscription")
    expected = sid(security.symbol)
    entries, trade, quote = iter(security.subscriptions), 0, 0
    for index in range(9):
        try:
            config = next(entries)
        except StopIteration:
            break
        require(index < 8 and sid(config.symbol) == expected and config.resolution == self.minute
            and config.fill_data_forward is False and config.extended_market_hours is False
            and config.data_normalization_mode == self.raw
            and str(config.data_time_zone) == "America/New_York"
            and str(config.exchange_time_zone) == "America/New_York"
            and config.type.FullName in ("QuantConnect.Data.Market.TradeBar", "QuantConnect.Data.Market.QuoteBar"), "feed_subscription")
        trade += int(config.type.FullName == "QuantConnect.Data.Market.TradeBar")
        quote += int(config.type.FullName == "QuantConnect.Data.Market.QuoteBar")
    require(1 <= trade + quote <= 8 and trade > 0, "feed_subscription")
    return {"config_count": trade + quote, "trade_config_count": trade, "quote_config_count": quote,
        "raw": True, "minute": True, "fill_forward": False, "extended_market_hours": False,
        "algorithm_timezone_ny": True, "security_exchange_timezone_ny": True,
        "config_data_timezone_ny": True, "config_exchange_timezone_ny": True}

def series(self, symbol):
    sessions = ("2022-10-17", "2022-10-18", "2022-10-19", "2022-10-20", "2022-10-21", "2022-10-24")
    group = lambda: {key: 0 for key in sessions + ("other", "invalid")}
    record = {"status": "lookup_failed", "call_invoked": False, "maximum": 6, "batches": 0, "items": 0,
        "batch_session": group(), "time_session": group(), "end_session": group(),
        "valid_precise_by_session": {key: 0 for key in sessions},
        "valid_legacy_by_session": {key: 0 for key in sessions},
        "duplicate_count": 0, "sid_mismatch_count": 0, "fill_forward_count": 0,
        "fill_forward_unknown_count": 0, "invalid_metadata_count": 0,
        "period": {key: 0 for key in ("regular_session", "one_day", "other", "invalid")}}
    def bucket(value):
        try:
            text = instant(value).date().isoformat()
            return text if text in sessions else "other"
        except Exception:
            return "invalid"
    try:
        typed = self.algorithm.history[self.trade_type]
        if not callable(typed):
            return record
    except Exception:
        return record
    record["call_invoked"] = True
    try:
        response = typed([symbol], datetime(2022, 10, 17), datetime(2022, 10, 25), self.daily,
            fill_forward=False, extended_market_hours=False, data_normalization_mode=self.raw)
    except Exception:
        record["status"] = "call_failed"
        return record
    seen = set()
    try:
        batches = iter(response)
        for index in range(7):
            try:
                batch = next(batches)
            except StopIteration:
                record["status"] = "complete"
                return record
            if index == 6:
                record["status"] = "bound_exceeded"
                return record
            record["batches"] += 1
            batch_value = batch.time
            record["batch_session"][bucket(batch_value)] += 1
            entries = iter(batch.items())
            for entry_index in range(2):
                try:
                    key, bar = next(entries)
                except StopIteration:
                    break
                if entry_index or record["items"] == 6:
                    record["status"] = "bound_exceeded"
                    return record
                record["items"] += 1
                if not isinstance(bar, self.trade_type):
                    record["invalid_metadata_count"] += 1
                    continue
                left_value, right_value = bar.time, bar.end_time
                record["time_session"][bucket(left_value)] += 1
                record["end_session"][bucket(right_value)] += 1
                try:
                    left, right, observed_batch = instant(left_value), instant(right_value), instant(batch_value)
                except Exception:
                    record["invalid_metadata_count"] += 1
                    record["period"]["invalid"] += 1
                    continue
                seconds = (right - left).total_seconds()
                kind = "regular_session" if seconds == 23400 else "one_day" if seconds == 86400 else "other" if seconds > 0 else "invalid"
                record["period"][kind] += 1
                same = sid(key) == sid(symbol) and sid(bar.symbol) == sid(symbol)
                record["sid_mismatch_count"] += int(not same)
                flag = bar.is_fill_forward
                record["fill_forward_count"] += int(flag is True)
                record["fill_forward_unknown_count"] += int(flag is not True and flag is not False)
                identity = (sid(key), left, right)
                duplicate = identity in seen
                record["duplicate_count"] += int(duplicate)
                seen.add(identity)
                text = left.date().isoformat()
                if same and not duplicate and flag is False and text in sessions and observed_batch == right:
                    opening = datetime.combine(left.date(), datetime(2022, 10, 21, 9, 30).time(), NY)
                    closing = datetime.combine(left.date(), datetime(2022, 10, 21, 16).time(), NY)
                    midnight = datetime.combine(left.date(), datetime.min.time(), NY)
                    if left == opening and right == closing:
                        record["valid_precise_by_session"][text] += 1
                    elif left == midnight and right == midnight + timedelta(days=1):
                        record["valid_legacy_by_session"][text] += 1
        record["status"] = "bound_exceeded"
    except Exception:
        record["status"] = "read_failed"
    return record

def publish(self):
    self.no_orders()
    require(self.result is not None and self.writes < 2, "feed_once")
    self.result["summary_updates"] = self.writes + 1
    raw = canonical(self.result)
    require(len(raw) <= 16384, "feed_result")
    self.algorithm.set_summary_statistic(META_STATISTIC, raw.decode("ascii"))
    self.writes += 1
    self.emitted = True

def initialize(self):
    require(not self.started and not self.emitted, "feed_once")
    self.started = True
    self.no_orders()
    require(instant(self.algorithm.time) == datetime(2022, 10, 25, tzinfo=NY), "feed_clock")
    package = inputs.load_accepted_risk_preliminary_package(self.algorithm,
        activation_manifest_key=self.activation[0], activation_manifest_sha256=self.activation[1],
        activation_manifest_byte_count=self.activation[2])
    require(package.package_sha256 == self.profile["package_sha256"]
        and package.activation_manifest_sha256 == self.activation[1], "feed_package")
    axis = tuple(package.evaluator_input.session_axis)
    require(digest(list(axis)) == AXIS and axis[axis.index("2022-10-24") - 1] == "2022-10-21"
        and tuple(text for text in axis if "2022-10-17" <= text < "2022-10-25") ==
            ("2022-10-17", "2022-10-18", "2022-10-19", "2022-10-20", "2022-10-21", "2022-10-24"), "feed_calendar")
    lineage, rows = dict(package.evaluator_input.source_lineage_sha256s), package.runtime_symbol_bindings
    require(len(rows) == 6151, "feed_catalog")
    resolution = figi.resolve_preliminary_qc_figis(rows,
        expected_security_master_admission_sha256=lineage["security_master_admission_sha256"],
        composite_figi=self.algorithm.composite_figi, benchmark_symbol=self.benchmark)
    require(resolution.input_row_count == 6151 and resolution.resolved_count + resolution.named_refusal_count == 6151, "feed_resolution")
    selected = [row for row in rows if digest({"schema": "arv2-missing-reference-identity-v1",
        "security_id": row["security_id"], "reference_session": "2022-10-21", "decision_session": "2022-10-24"}) == WITNESS]
    require(len(selected) == 1, "feed_witness")
    row = figi._input_row(selected[0], lineage["security_master_admission_sha256"])
    require(row["source_row_sha256"] == SOURCE_ROW and digest(row) == BINDING_ROW, "feed_witness")
    self.symbol = resolution.symbol_for_security(row["security_id"])
    require(self.symbol is not None, "feed_resolution")
    self.native = self.native_metadata(self.symbol)
    security = self.algorithm.add_security(self.symbol, self.minute, False, 1, False)
    security.set_data_normalization_mode(self.raw)
    require(sid(security.symbol) == sid(self.symbol), "feed_subscription")
    selected_subscription = self.subscription(security)
    clock_subscription = self.subscription(self.clock_security)
    daily = self.series(self.symbol)
    minute = self.observe(self.symbol, self.minute, datetime(2022, 10, 21, 9, 30), datetime(2022, 10, 21, 16), 390)
    probes = [self.dated_probe(row["composite_figi"], text) for text in ("2020-11-01", "2022-10-21", "2022-10-24")]
    current = self.native_metadata(self.symbol)
    require(current["native_sid_sha256"] == self.native["native_sid_sha256"], "feed_identity_metadata")
    initial = {"actual_clock": "2022-10-25_0000_NY_initialize", "daily_series": daily, "minute": minute,
        "native_identity": self.native, "native_after_probes": current, "dated_probes": probes,
        "selected_subscription": selected_subscription, "clock_subscription": clock_subscription,
        "resolved_count": resolution.resolved_count, "named_refusal_count": resolution.named_refusal_count}
    self.result = {"schema": "arv2-r298-reference-series-phase-result-v1", "profile_sha256": self.profile["profile_sha256"],
        "identity_sha256": WITNESS, "source_row_sha256": SOURCE_ROW, "whole_binding_row_sha256": BINDING_ROW,
        "session_axis_sha256": AXIS, "input_binding_count": 6151, "initialize": initial,
        "initialize_sha256": digest(initial), "post": {"status": "pending", "actual_clock": None,
            "genuine_clock_bar": False, "same_native_sid": False, "minute": None},
        "explicit_history_calls": int(daily["call_invoked"]) + int(minute["call_invoked"]),
        "diagnostic_complete": False, "diagnostic_only": True,
        "price_fields_read": False, "price_used": False, "orders_submitted": False,
        "strategy_continued": False, "strategy_result_accepted": False, "family_comparable": False,
        "point_in_time_proven": False, "formal_identity_admitted": False,
        "formal_forward_ready": False, "paper_or_live_ready": False,
        "independent_data_completeness_proven": False, "provider_route_admitted": False,
        "historical_resolution_availability_proven": False, "alternate_resolved_symbol_used": False,
        "a19_cause_authenticated": False, "initialize_history_unsupported_proven": False}
    self.publish()
    return self.result

def on_data(self, data):
    require(self.started and self.result is not None, "feed_once")
    if self.result["post"]["status"] != "pending":
        return None
    now = instant(self.algorithm.time)
    expected = datetime(2022, 10, 25, 9, 31, tzinfo=NY)
    if now < expected:
        return None
    if now != expected:
        self.result["post"]["status"] = "clock_missing"
        self.publish()
        raise RuntimeError("feed_missing_clock")
    try:
        require(instant(data.time) == expected, "feed_clock")
        symbol = self.clock_security.symbol
        bar = data.bars[symbol] if symbol in data.bars else None
        require(bar is not None and isinstance(bar, self.trade_type)
            and sid(bar.symbol) == sid(symbol) and bar.is_fill_forward is False
            and instant(bar.time) == datetime(2022, 10, 25, 9, 30, tzinfo=NY)
            and instant(bar.end_time) == expected, "feed_clock")
        require(self.native_metadata(self.symbol)["native_sid_sha256"] == self.native["native_sid_sha256"], "feed_identity_metadata")
        self.no_orders()
    except Exception:
        self.result["post"]["status"] = "clock_refused"
        self.publish()
        raise RuntimeError("feed_clock") from None
    minute = self.observe(self.symbol, self.minute, datetime(2022, 10, 21, 9, 30), datetime(2022, 10, 21, 16), 390)
    self.result["post"] = {"status": "observed", "actual_clock": "2022-10-25_0931_NY_OnData",
        "genuine_clock_bar": True, "same_native_sid": True, "minute": minute}
    self.result["explicit_history_calls"] += int(minute["call_invoked"])
    initial = self.result["initialize"]
    self.result["diagnostic_complete"] = initial["daily_series"]["status"] == initial["minute"]["status"] == minute["status"] == "complete"
    self.publish()
    require(self.result["diagnostic_complete"], "feed_result")
    return self.result

def on_end(self):
    self.no_orders()
    require(self.started and self.result is not None, "feed_once")
    if self.result["post"]["status"] == "pending":
        self.result["post"]["status"] = "clock_missing"
        self.publish()
        raise RuntimeError("feed_missing_clock")
    require(self.result["diagnostic_complete"] and self.writes == 2, "feed_result")
'''

RUNTIME_SOURCE = _PRELUDE + '\nclass ReferenceSeriesPhaseDiagnostic:\n' + '\n'.join(
    '    ' + line if line else '' for line in (_SHARED_METHODS + '\n' + _NEW_METHODS).splitlines()) + '\n'


def _runtime():
    tree = ast.parse(RUNTIME_SOURCE)
    forbidden = {'market_order', 'set_holdings', 'liquidate', 'add_data', 'download', 'open', 'close',
        'high', 'low', 'price', 'value', 'volume', 'set_market_price'}
    # Symbol.value is display metadata; no bar/security value or OHLCV accessor.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden:
            require(node.attr == 'value' and isinstance(node.value, ast.Name) and node.value.id == 'symbol', 'source_bound')
    raw = (ast.unparse(tree) + '\n').encode('ascii')
    require(len(raw) <= 64000, 'source_bound')
    compile(raw, RUNTIME_NAME, 'exec')
    return raw


def profile_digest(profile):
    require(type(profile) is dict, 'profile')
    return sha(canonical({key: value for key, value in profile.items() if key != 'profile_sha256'}))


def _profile(patcher_pin, runtime_pin):
    seed = {'schema': PROFILE_SCHEMA, 'candidate_id': 'R298_REFERENCE_SERIES_PHASE_P_V1',
        'package_sha256': comparison.PLAIN_PACKAGE_SHA256, 'lineage_sha256': comparison.bridge.parent.LINEAGE,
        'parent_projection_sha256': PARENT_PROJECTION, 'parent_profile_sha256': PARENT_PROFILE,
        'n_preimage_projection_sha256': N_PROJECTION, 'n_preimage_profile_sha256': N_PROFILE,
        'identity_sha256': WITNESS, 'source_row_sha256': SOURCE_ROW, 'whole_binding_row_sha256': BINDING_ROW,
        'session_axis_sha256': AXIS, 'activation': list(comparison.PLAIN_ACTIVATION),
        'source_pins': {**comparison.bridge.parent.SOURCE_PINS, **comparison.NEW_SOURCE_PINS,
            'newrule_legacy_primitives.py': previous.A19_LEGACY,
            RUNTIME_NAME: runtime_pin, PATCHER_NAME: patcher_pin,
            previous.PATCHER_NAME: N_PATCHER}, 'policy': policy_record()}
    return {**seed, 'profile_sha256': profile_digest(seed)}


def profile_record(*, patcher_sha256):
    require(type(patcher_sha256) is str and re.fullmatch('[0-9a-f]{64}', patcher_sha256), 'patcher_pin')
    return _profile(patcher_sha256, sha(_runtime()))


def _main(profile):
    key, pin, count = comparison.PLAIN_ACTIVATION
    raw = f'''from AlgorithmImports import *
from newrule_comparison_qc_runtime import ReferenceSeriesPhaseDiagnostic
SERIES_PHASE_PROFILE = {profile!r}
class ReferenceSeriesPhaseAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.settings.daily_precise_end_time = True
        self.settings.seed_initial_prices = False
        self.set_start_date(2022, 10, 25)
        self.set_end_date(2022, 10, 25)
        self.set_cash(1000000)
        clock = self.add_equity("SPY", Resolution.MINUTE, fill_forward=False, leverage=1,
            extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW)
        self.set_benchmark(clock.symbol)
        self._feed = ReferenceSeriesPhaseDiagnostic(self, profile=SERIES_PHASE_PROFILE,
            activation_manifest_key={key!r}, activation_manifest_sha256={pin!r}, activation_manifest_byte_count={count},
            benchmark_symbol=clock.symbol, clock_security=clock, trade_bar_type=TradeBar,
            quote_bar_type=QuoteBar, minute_resolution=Resolution.MINUTE,
            daily_resolution=Resolution.DAILY, raw_normalization=DataNormalizationMode.RAW)
        self._feed.initialize()
    def on_data(self, data):
        self._feed.on_data(data)
    def on_end_of_algorithm(self):
        self._feed.on_end()
'''
    result = (ast.unparse(ast.parse(raw)) + '\n').encode('ascii')
    require(len(result) <= 64000, 'source_bound')
    compile(result, 'main.py', 'exec')
    return result


def _manifest(pairs, projection):
    return {'project_id': 38364439, 'projection_sha256': projection,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)} for name, raw in pairs]}


def _n_pairs(pairs, *, old_input):
    pairs = previous._pairs(pairs)
    files = dict(pairs)
    if old_input:
        require(sha(canonical(_manifest(pairs, PARENT_PROJECTION)) + b'\n') == PARENT_MANIFEST, 'parent_manifest')
        legacy = previous.identity_parent._legacy(previous.identity_parent.parent._legacy(files['newrule_legacy_primitives.py']))
    else:
        legacy = files['newrule_legacy_primitives.py']
    require(sha(legacy) == previous.A19_LEGACY, 'parent_manifest')
    profile = previous._profile(N_PATCHER, sha(previous._runtime()))
    require(profile['profile_sha256'] == N_PROFILE, 'parent_profile')
    n_pairs = tuple((name, previous._runtime() if name == RUNTIME_NAME else previous._main(profile) if name == 'main.py'
        else legacy if name == 'newrule_legacy_primitives.py' else raw) for name, raw in pairs)
    require(sha(canonical(_manifest(n_pairs, N_PROJECTION)) + b'\n') == N_MANIFEST, 'parent_manifest')
    return n_pairs


@dataclasses.dataclass(frozen=True, slots=True)
class SeriesPhaseProjection:
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


def _record(profile, pairs, patcher_pin):
    return {'schema': SCHEMA, 'candidate_id': 'R298_REFERENCE_SERIES_PHASE_P_V1',
        'parent_projection_sha256': PARENT_PROJECTION, 'parent_profile_sha256': PARENT_PROFILE,
        'parent_source_manifest_sha256': PARENT_MANIFEST, 'profile_sha256': profile['profile_sha256'],
        'n_preimage_projection_sha256': N_PROJECTION, 'n_preimage_profile_sha256': N_PROFILE,
        'n_preimage_source_manifest_sha256': N_MANIFEST, 'patcher_sha256': patcher_pin,
        'package_sha256': comparison.PLAIN_PACKAGE_SHA256, 'policy': policy_record(), 'diagnostic_only': True,
        'unchanged_comparison_basis': 'exact_N_cloud_source',
        'unchanged_cloud_files': [name for name, raw in pairs if name not in (RUNTIME_NAME, 'main.py')],
        'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)} for name, raw in pairs], **FALSE_FLAGS}


def public_specification(source_pairs, *, patcher_source_bytes, expected_patcher_sha256):
    require(type(expected_patcher_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_patcher_sha256)
        and type(patcher_source_bytes) is bytes and 0 < len(patcher_source_bytes) <= 100000
        and patcher_source_bytes.isascii() and sha(patcher_source_bytes) == expected_patcher_sha256, 'patcher_pin')
    old = _n_pairs(source_pairs, old_input=True)
    runtime = _runtime()
    profile = _profile(expected_patcher_sha256, sha(runtime))
    pairs = tuple((name, runtime if name == RUNTIME_NAME else _main(profile) if name == 'main.py' else raw)
        for name, raw in old)
    previous._pairs(pairs)
    record = _record(profile, pairs, expected_patcher_sha256)
    result = SeriesPhaseProjection(sha(canonical(record)), canonical(record), canonical(profile), pairs)
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
    pairs = previous._pairs(source_pairs)
    _n_pairs(pairs, old_input=False)
    try:
        record = json.loads(record_bytes)
        require(type(record) is dict and canonical(record) == record_bytes, 'projection_packet')
        profile = _profile(record['patcher_sha256'], sha(_runtime()))
        require(profile['profile_sha256'] == expected_profile_sha256
            and canonical(record) == canonical(_record(profile, pairs, record['patcher_sha256']))
            and dict(pairs)[RUNTIME_NAME] == _runtime() and dict(pairs)['main.py'] == _main(profile), 'projection_packet')
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, RecursionError):
        raise Refused('projection_packet') from None
    return record, profile, pairs


def parse_failure_context(value): return None
def validate_failure_context(value): raise Refused('result')


def _hash(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'result')


def _native(value):
    keys = {'native_sid_sha256', 'native_display_sha256', 'native_sid_date_sha256', 'native_sid_date_relation'}
    require(type(value) is dict and set(value) == keys, 'result')
    for key in keys - {'native_sid_date_relation'}: _hash(value[key])
    require(type(value['native_sid_date_relation']) is str
        and value['native_sid_date_relation'] in ('before_reference', 'exact_reference', 'after_reference'), 'result')


def _subscription(value):
    fixed = {'raw': True, 'minute': True, 'fill_forward': False, 'extended_market_hours': False,
        'algorithm_timezone_ny': True, 'security_exchange_timezone_ny': True,
        'config_data_timezone_ny': True, 'config_exchange_timezone_ny': True}
    require(type(value) is dict and set(value) == {*fixed, 'config_count', 'trade_config_count', 'quote_config_count'}
        and all(value[key] is item for key, item in fixed.items())
        and all(type(value[key]) is int and 0 <= value[key] <= 8 for key in ('config_count', 'trade_config_count', 'quote_config_count'))
        and 1 <= value['trade_config_count'] <= value['config_count'] <= 8
        and value['trade_config_count'] + value['quote_config_count'] == value['config_count'], 'result')


def _minute(value):
    # Delegate ONLY the frozen N metadata-shape validator. This synthetic
    # envelope is never emitted and grants no authority or actual call count.
    blank = {**json.loads(canonical(_blank_minute())), 'maximum': 1}
    wrapper = {'schema': previous.RESULT_SCHEMA, 'profile_sha256': 'a' * 64,
        'identity_sha256': WITNESS, 'source_row_sha256': SOURCE_ROW, 'whole_binding_row_sha256': BINDING_ROW,
        'session_axis_sha256': AXIS, 'actual_observation_clock': '2022-10-24_0000_NY_initialize',
        'input_binding_count': 6151, 'resolved_count': 1, 'named_refusal_count': 6150,
        'daily': blank, 'minute': value, 'subscription': {'raw': True, 'minute_subscription_requested': True,
            'fill_forward_requested': False, 'extended_market_hours_requested': False,
            'algorithm_timezone_ny': True, 'security_exchange_timezone_ny': True},
        'explicit_history_calls': int(value.get('call_invoked') is True) if type(value) is dict else 0,
        'diagnostic_complete': False, 'diagnostic_only': True, **previous.FALSE_FLAGS}
    previous.validate_result_statistics({previous.META_STATISTIC: canonical(wrapper).decode('ascii')},
        expected_profile={'profile_sha256': 'a' * 64})


def _blank_minute():
    return {'status': 'lookup_failed', 'call_invoked': False, 'batches': 0, 'items': 0,
        'maximum': 390, 'duplicate_count': 0, 'sid_mismatch_count': 0,
        'fill_forward_count': 0, 'fill_forward_unknown_count': 0, 'invalid_metadata_count': 0,
        'valid_regular_minute_count': 0, 'valid_daily_bar_count': 0,
        'minute_grid_complete': False, 'first_minute_endpoint_present': False,
        'last_regular_endpoint_present': False,
        **{key: {name: 0 for name in ('before_reference', 'exact_reference', 'after_reference')}
            for key in ('batch_day', 'time_day', 'end_day')},
        **{key: {name: 0 for name in ('before_open', 'at_open', 'inside_regular', 'at_close', 'after_close')}
            for key in ('time_session', 'end_session')},
        'period': {name: 0 for name in ('one_minute', 'regular_session', 'one_day', 'other', 'invalid')}}


def _series(value):
    integers = ('batches', 'items', 'duplicate_count', 'sid_mismatch_count', 'fill_forward_count',
        'fill_forward_unknown_count', 'invalid_metadata_count')
    groups = {'batch_session': SERIES_SESSIONS + ('other', 'invalid'),
        'time_session': SERIES_SESSIONS + ('other', 'invalid'), 'end_session': SERIES_SESSIONS + ('other', 'invalid'),
        'valid_precise_by_session': SERIES_SESSIONS, 'valid_legacy_by_session': SERIES_SESSIONS,
        'period': ('regular_session', 'one_day', 'other', 'invalid')}
    require(type(value) is dict and set(value) == {'status', 'call_invoked', 'maximum', *integers, *groups}
        and type(value['status']) is str and value['status'] in ('lookup_failed', 'call_failed', 'complete', 'bound_exceeded', 'read_failed')
        and type(value['call_invoked']) is bool and type(value['maximum']) is int and value['maximum'] == 6
        and all(type(value[key]) is int and 0 <= value[key] <= 6 for key in integers)
        and value['items'] <= value['batches'], 'result')
    for key, names in groups.items():
        group = value[key]
        require(type(group) is dict and set(group) == set(names)
            and all(type(item) is int and 0 <= item <= 6 for item in group.values())
            and sum(group.values()) <= (value['batches'] if key == 'batch_session' else value['items']), 'result')
    valid = sum(value['valid_precise_by_session'].values()) + sum(value['valid_legacy_by_session'].values())
    require(valid <= value['items'] and all(valid + value[key] <= value['items'] for key in integers[2:])
        and sum(value['valid_precise_by_session'].values()) <= value['period']['regular_session']
        and sum(value['valid_legacy_by_session'].values()) <= value['period']['one_day'], 'result')
    minimum_end = {name: 0 for name in SERIES_SESSIONS + ('other', 'invalid')}
    from datetime import date, timedelta
    for session in SERIES_SESSIONS:
        precise, legacy = value['valid_precise_by_session'][session], value['valid_legacy_by_session'][session]
        require(precise + legacy <= 1 and precise + legacy <= value['time_session'][session]
            and precise <= value['end_session'][session] and precise <= value['batch_session'][session], 'result')
        minimum_end[session] += precise
        following = (date.fromisoformat(session) + timedelta(days=1)).isoformat()
        minimum_end[following if following in SERIES_SESSIONS else 'other'] += legacy
    require(all(value['end_session'][key] >= count and value['batch_session'][key] >= count
        for key, count in minimum_end.items()), 'result')
    if value['status'] in ('lookup_failed', 'call_failed'):
        require(all(value[key] == 0 for key in integers)
            and all(sum(value[key].values()) == 0 for key in groups), 'result')
    require(value['call_invoked'] is (value['status'] != 'lookup_failed'), 'result')


def validate_result_statistics(statistics, *, expected_profile):
    require(type(statistics) is dict and META_STATISTIC in statistics
        and type(statistics[META_STATISTIC]) is str and statistics[META_STATISTIC].isascii()
        and 0 < len(statistics[META_STATISTIC]) <= MAX_STATISTIC_BYTES, 'result_bound')
    try:
        value = json.loads(statistics[META_STATISTIC])
        fixed = {'schema': RESULT_SCHEMA, 'profile_sha256': expected_profile['profile_sha256'],
            'identity_sha256': WITNESS, 'source_row_sha256': SOURCE_ROW, 'whole_binding_row_sha256': BINDING_ROW,
            'session_axis_sha256': AXIS, 'input_binding_count': 6151, 'diagnostic_only': True, **FALSE_FLAGS}
        require(type(value) is dict and set(value) == {*fixed, 'initialize', 'initialize_sha256', 'post',
            'explicit_history_calls', 'diagnostic_complete', 'summary_updates'}
            and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items())
            and canonical(value).decode('ascii') == statistics[META_STATISTIC], 'result')
        initial = value['initialize']
        require(type(initial) is dict and set(initial) == {'actual_clock', 'daily_series', 'minute',
            'native_identity', 'native_after_probes', 'dated_probes', 'selected_subscription', 'clock_subscription',
            'resolved_count', 'named_refusal_count'} and initial['actual_clock'] == '2022-10-25_0000_NY_initialize'
            and type(initial['actual_clock']) is str
            and all(type(initial[key]) is int and 0 <= initial[key] <= 6151 for key in ('resolved_count', 'named_refusal_count'))
            and initial['resolved_count'] > 0 and initial['resolved_count'] + initial['named_refusal_count'] == 6151
            and value['initialize_sha256'] == sha(canonical(initial)), 'result')
        _series(initial['daily_series']); _minute(initial['minute'])
        _native(initial['native_identity']); _native(initial['native_after_probes'])
        require(initial['native_identity']['native_sid_sha256'] == initial['native_after_probes']['native_sid_sha256'], 'result')
        _subscription(initial['selected_subscription']); _subscription(initial['clock_subscription'])
        probes = initial['dated_probes']
        require(type(probes) is list and len(probes) == 3, 'result')
        for record, date_text in zip(probes, PROBE_DATES, strict=True):
            require(type(record) is dict and set(record) == {'trading_date', 'status', 'metadata', 'roundtrip_matches',
                'same_native_sid', 'same_native_display'} and type(record['trading_date']) is str and record['trading_date'] == date_text
                and type(record['status']) is str and record['status'] in ('forward_failed', 'unavailable', 'metadata_failed', 'reverse_failed', 'observed')
                and all(type(record[key]) is bool for key in ('roundtrip_matches', 'same_native_sid', 'same_native_display')), 'result')
            if record['status'] in ('forward_failed', 'unavailable', 'metadata_failed'):
                require(record['metadata'] is None and not record['roundtrip_matches']
                    and not record['same_native_sid'] and not record['same_native_display'], 'result')
            else:
                _native(record['metadata'])
                require(record['same_native_sid'] is (record['metadata']['native_sid_sha256'] == initial['native_identity']['native_sid_sha256'])
                    and record['same_native_display'] is (record['metadata']['native_display_sha256'] == initial['native_identity']['native_display_sha256'])
                    and (record['status'] != 'reverse_failed' or record['roundtrip_matches'] is False), 'result')
        post = value['post']
        require(type(post) is dict and set(post) == {'status', 'actual_clock', 'genuine_clock_bar', 'same_native_sid', 'minute'}
            and type(post['status']) is str and post['status'] in ('pending', 'observed', 'clock_missing', 'clock_refused'), 'result')
        calls = int(initial['daily_series']['call_invoked']) + int(initial['minute']['call_invoked'])
        if post['status'] == 'observed':
            _minute(post['minute']); calls += int(post['minute']['call_invoked'])
            require(type(post['actual_clock']) is str and post['actual_clock'] == '2022-10-25_0931_NY_OnData'
                and post['genuine_clock_bar'] is True and post['same_native_sid'] is True, 'result')
        else:
            require(post['actual_clock'] is None and post['genuine_clock_bar'] is False
                and post['same_native_sid'] is False and post['minute'] is None, 'result')
        complete = post['status'] == 'observed' and initial['daily_series']['status'] == initial['minute']['status'] == post['minute']['status'] == 'complete'
        require(type(value['explicit_history_calls']) is int and value['explicit_history_calls'] == calls <= 3
            and type(value['diagnostic_complete']) is bool and value['diagnostic_complete'] is complete
            and type(value['summary_updates']) is int and value['summary_updates'] == (1 if post['status'] == 'pending' else 2), 'result')
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('result') from None
    return json.loads(canonical(value))
