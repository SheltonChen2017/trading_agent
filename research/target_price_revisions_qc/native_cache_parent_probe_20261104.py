"""Pure native-parent cache diagnostic: the raw witness and SID stay in QC.

This fixed non-order input canary registers the exact historical SID during
the first locked preopen SPY callback, never during unlocked Initialize.
The future-dated failure witness selects a hindsight diagnostic identity only;
it supplies no financial value and establishes no PIT or financial admission.
All caller code is rejected except the exact pinned public witness validator.
No filesystem, private read, provider, compile or job effect occurs here.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re

from . import comparison_20261028_mark_read as reader
from . import native_cache_probe_20261104 as base

MODULE = "research/target_price_revisions_qc/native_cache_parent_probe_20261104.py"
EPOCH = "TPR-NATIVE-PARENT-PREOPEN-CACHE-20261104-v2"
PROJECT_ID = base.PROJECT_ID
TARGET_SID_SHA256 = base.TARGET_SID_SHA256
SESSIONS = base.SESSIONS
MAX_SOURCE_BYTES = 128 * 1024
HELPER_SHA256 = "6539ae749aefb4884ed52258fc2f0f77c9481a5e8ee37ea80ec7065218f0da95"
BASE_SHA256 = "481602457ae78568b3b708cbefd0315d7115baf95a8bd27536983e8bbfec7a86"
BASE_RUNTIME_SHA256 = "4ff09e1079905afb08ee8d9a42e0bfc27a72ff0f878efbc9d591e865b661eb10"
PARENT_CONFIG_SHA256 = "8292239f62e01d20a221fe49f76b3c29a23e9089eed3d6468f0a0953cbbb02b3"
PARENT_KEY_SHA256 = "7a27356ccf09e0674b56dac39adaad4d1a0ef7a2cee7ef7f948982f20004e13f"
PARENT_WITNESS_SHA256 = "eef08aca32b99056dee0ce00389c53a8ee6a1628c29188afd8bebd362fe183dd"
PARENT_BYTES = 1343
REQUIRED_SOURCES = frozenset((MODULE, base.MODULE, reader.MODULE))
PINNED = {base.MODULE: BASE_SHA256, reader.MODULE: HELPER_SHA256}
FLAGS = base.FLAGS + ("sdk_hard_timeout_proven", "sdk_preallocation_byte_bound_proven",
    "parent_read_source_origin_proven", "provider_wide_absence_proven")


class ParentCacheRefusal(ValueError):
    """Body-free refusal: no source key, witness, or SID enters an exception."""


def _fail():
    raise ParentCacheRefusal("fixed native-parent cache diagnostic refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")


def _parse(raw):
    def pairs(items):
        value = {}
        for key, cell in items:
            if key in value:
                _fail()
            value[key] = cell
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_float=lambda _: _fail(),
            parse_constant=lambda _: _fail())
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail()


RUNTIME = r'''
def parent_bytes(value):
    expected = CONFIG["parent_binding"]["expected_bytes"]
    if type(value) in (bytes, bytearray):
        if len(value) != expected:
            raise ValueError("parent byte bound unproved")
    else:
        from System import Array, Byte
        if type(value) is not Array[Byte] or value.Length != expected:
            raise ValueError("parent byte type unproved")
    return bytes(value)

class Main(CacheProbeBase):
    def initialize(self):
        self._job, self._disabled, self._target_ready, self._bootstrap_attempted = None, False, False, False
        self._waiting_previous_now = None
        self._seen, self._slices, self._bars = set(), 0, 0
        self._report = {"schema": "tpr-native-parent-cache-observations-v2", "source_epoch": SOURCE_EPOCH,
            "operation_id": None, "root_head": None, "status": "setup_unproved", "sessions": {},
            "input_canary_only": True, "non_order_diagnostic_exception": True,
            "hindsight_identity_diagnostic_only": True, "initialize_private_effects": False,
            "external_native_read_manifest_required": True, "parent_contains_calls": 0,
            "parent_read_calls": 0, "object_store_calls": 0, "parent_bytes_expected": CONFIG_PARENT_BYTES,
            "parent_hash_verified": False, "parent_schema_verified": False, "parent_sid_hash_verified": False,
            "registration_before_open": False, "direct_order_calls": 0, "history_calls": 0,
            "preopen_empty_slices": 0, "preopen_empty_slices_max": 400,
            "direct_provider_calls": 0, "cache_updates": 0, "subscription_removals": 0,
            "resource_cap_changes": 0, "cache_reads_per_check_max": 3, "config_reads_per_check_max": 3,
            "native_close_reads_per_check_max": 2, **{key: False for key in FALSE_FLAGS}}
        try:
            self._configuration()
            if (self.live_mode is not False or type(self.project_id) is not int
                    or self.project_id != 38609822 or self.get_locked() is not False):
                raise ValueError("setup custody unproved")
            self._report.update(operation_id=CONFIG["operation_id"], root_head=CONFIG["git_head"])
            self.set_time_zone("America/New_York")
            self.set_start_date(2021, 2, 8)
            self.set_end_date(2021, 2, 12)
            self.settings.daily_precise_end_time = True
            control = self.add_equity("SPY", Resolution.MINUTE, fill_forward=False,
                extended_market_hours=True, data_normalization_mode=DataNormalizationMode.RAW)
            if not isinstance(control, Security):
                raise ValueError("native control unproved")
            self._symbols, self._registered = {"control": control.symbol}, {"control": control}
            self.set_benchmark(control.symbol)
            self.schedule.on(self.date_rules.every_day(control.symbol), self.time_rules.at(16, 1), self._check_close)
            self._report["status"] = "awaiting_first_locked_preopen_slice"
        except KeyboardInterrupt:
            raise KeyboardInterrupt("native-parent diagnostic cancelled") from None
        except Exception:
            self._disabled = True

    def _configuration(self):
        if (hashlib.sha256(CONFIG_JSON.encode("ascii")).hexdigest() != CONFIG_SHA256
                or json.dumps(CONFIG, sort_keys=True, separators=(",", ":")) != CONFIG_JSON
                or hashlib.sha256(PARENT_HELPER_SOURCE.encode("utf-8")).hexdigest() != HELPER_SHA256
                or CONFIG["target_sid_sha256"] != EXPECTED_TARGET_SHA256
                or CONFIG["parent_binding"]["expected_bytes"] != CONFIG_PARENT_BYTES):
            raise ValueError("configuration unproved")

    def _preopen(self, data, expected_now=None, expected_slice=None, expected_control=None):
        self._bound()
        now, local = clock(self.utc_time, "UTC"), clock(self.time, "America/New_York")
        ny = local.astimezone(ZoneInfo("America/New_York"))
        if (now != local or ny.date().isoformat() != "2021-02-08" or not time(4) <= ny.time() < time(9, 30)
                or not isinstance(data, Slice) or not NetObject.ReferenceEquals(data, self.current_slice)
                or expected_now is not None and now != expected_now
                or expected_slice is not None and not NetObject.ReferenceEquals(data, expected_slice)):
            raise ValueError("preopen native scope unproved")
        control = self._registered["control"]
        if (len(self.securities) != 1 or not NetObject.ReferenceEquals(self.securities[control.symbol], control)
                or expected_control is not None and not NetObject.ReferenceEquals(control, expected_control)
                or not 0 < len(data.bars) <= 1 or control.symbol not in data.bars):
            raise ValueError("preopen native control unproved")
        bar = data.bars[control.symbol]
        if not isinstance(bar, TradeBar):
            raise ValueError("preopen trade clock unproved")
        values = self._cache_values(bar)
        began, ended = values[5:7]
        if (values[2] != str(control.symbol.id) or values[3] is not False
                or values[4] != timedelta(minutes=1) or ended-began != timedelta(minutes=1)
                or began.astimezone(ZoneInfo("America/New_York")).date().isoformat() != "2021-02-08"
                or not time(4) <= began.astimezone(ZoneInfo("America/New_York")).time() < time(9, 30)
                or ended > now or (now-ended) > timedelta(minutes=1)):
            raise ValueError("preopen native bar unproved")
        configs = self._bootstrap_configs("control", control.symbol, control)
        # The config service is a native boundary. Recheck its endpoint before
        # any ObjectStore call, rather than returning the earlier clock/bar.
        self._bound()
        if (clock(self.utc_time, "UTC") != now or clock(self.time, "America/New_York") != now
                or not NetObject.ReferenceEquals(data, self.current_slice) or len(self.securities) != 1
                or not NetObject.ReferenceEquals(self.securities[control.symbol], control)
                or control.symbol not in data.bars or not NetObject.ReferenceEquals(data.bars[control.symbol], bar)
                or self._cache_values(bar) != values
                or configs[1] != tuple(self._config_values(row) for row in configs[0])):
            raise ValueError("preopen configuration endpoint changed")
        return now, data, control, values, configs, bar

    def _same_preopen(self, data, prior):
        current = self._preopen(data, prior[0], prior[1], prior[2])
        if (prior[3] != current[3] or not NetObject.ReferenceEquals(prior[5], current[5])
                or prior[4][1] != current[4][1]
                or len(prior[4][0]) != len(current[4][0]) or not all(
                    NetObject.ReferenceEquals(a, b) for a, b in zip(prior[4][0], current[4][0]))):
            raise ValueError("preopen scope changed")
        return current

    def _bootstrap(self, data):
        prior = self._preopen(data)
        self._report["parent_contains_calls"] += 1
        self._report["object_store_calls"] += 1
        present = self.object_store.contains_key(CONFIG["parent_binding"]["key"])
        self._same_preopen(data, prior)
        if type(present) is not bool or present is not True:
            raise ValueError("parent existence unproved")
        self._report["parent_read_calls"] += 1
        self._report["object_store_calls"] += 1
        raw = parent_bytes(self.object_store.read_bytes(CONFIG["parent_binding"]["key"]))
        self._same_preopen(data, prior)
        if hashlib.sha256(raw).hexdigest() != CONFIG["parent_binding"]["expected_sha256"]:
            raise ValueError("parent hash unproved")
        self._report["parent_hash_verified"] = True
        safe = PARENT_VALIDATOR["project_witness_v2"](raw, binding=CONFIG["parent_binding"], pointer=CONFIG["parent_pointer"])
        self._same_preopen(data, prior)
        self._report["parent_schema_verified"] = True
        body = PARENT_VALIDATOR["_parse"](raw)
        sid_text = body["security_id"]
        if (safe["security_id_sha256"] != EXPECTED_TARGET_SHA256 or type(sid_text) is not str
                or not sid_text.isascii() or re.fullmatch(r"[^\s|]{1,64} [A-Z0-9]{1,13}", sid_text) is None
                or int(sid_text.split(" ")[1], 36) >= 2**64
                or hashlib.sha256(sid_text.encode("ascii")).hexdigest() != EXPECTED_TARGET_SHA256):
            raise ValueError("parent identity hash unproved")
        parsed = SecurityIdentifier.parse(sid_text)
        symbol = Symbol(parsed, parsed.symbol)
        if (not isinstance(parsed, SecurityIdentifier) or not isinstance(symbol, Symbol)
                or parsed.security_type != SecurityType.EQUITY or parsed.market != Market.USA
                or str(parsed) != sid_text or str(symbol.id) != sid_text):
            raise ValueError("native parent identity unproved")
        self._same_preopen(data, prior)
        self._report["parent_sid_hash_verified"] = True
        target = self.add_security(symbol, resolution=Resolution.MINUTE, fill_forward=False,
            extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW)
        self._bound()
        if (not isinstance(target, Security) or target.symbol != symbol or symbol == prior[2].symbol
                or clock(self.utc_time, "UTC") != prior[0] or clock(self.time, "America/New_York") != prior[0]
                or not NetObject.ReferenceEquals(data, self.current_slice)):
            raise ValueError("native registration scope changed")
        self._symbols["target"], self._registered["target"] = symbol, target
        control_after = self._configs("control", prior[2].symbol, prior[2])
        target_after = self._configs("target", symbol, target)
        self._bound()
        if (clock(self.utc_time, "UTC") != prior[0] or clock(self.time, "America/New_York") != prior[0]
                or not NetObject.ReferenceEquals(data, self.current_slice) or len(self.securities) != 2
                or not NetObject.ReferenceEquals(self.securities[prior[2].symbol], prior[2])
                or not NetObject.ReferenceEquals(self.securities[symbol], target)
                or control_after[1] != tuple(self._config_values(row) for row in control_after[0])
                or target_after[1] != tuple(self._config_values(row) for row in target_after[0])):
            raise ValueError("registration configuration endpoint changed")
        if (prior[4][1] != control_after[1] or len(prior[4][0]) != len(control_after[0])
                or not all(NetObject.ReferenceEquals(a, b) for a, b in zip(prior[4][0], control_after[0]))
                or prior[2].symbol not in data.bars or not NetObject.ReferenceEquals(prior[5], data.bars[prior[2].symbol])
                or self._cache_values(data.bars[prior[2].symbol]) != prior[3]):
            raise ValueError("control registration changed")
        self._target_ready = True
        self._report.update(registration_before_open=True, status="awaiting_fixed_close_checks")
        del raw, body, sid_text

    def on_data(self, data):
        if self._disabled:
            return
        try:
            if not self._target_ready:
                self._bound()
                now, local = clock(self.utc_time, "UTC"), clock(self.time, "America/New_York")
                ny = local.astimezone(ZoneInfo("America/New_York"))
                if (now != local or ny.date().isoformat() != "2021-02-08" or not time() <= ny.time() < time(9, 30)
                        or self._waiting_previous_now is not None and now < self._waiting_previous_now
                        or not isinstance(data, Slice) or not NetObject.ReferenceEquals(data, self.current_slice)
                        or not 0 <= len(data.bars) <= 1):
                    raise ValueError("preopen waiting scope unproved")
                self._waiting_previous_now = now
                control = self._registered["control"].symbol
                if control not in data.bars:
                    if len(data.bars) != 0:
                        raise ValueError("foreign preopen trade unproved")
                    self._report["preopen_empty_slices"] += 1
                    if self._report["preopen_empty_slices"] > 400:
                        raise ValueError("preopen waiting bound")
                    return
                if self._bootstrap_attempted:
                    raise ValueError("parent bootstrap already spent")
                self._bootstrap_attempted = True
                self._bootstrap(data)
            CacheProbeBase.on_data(self, data)
        except KeyboardInterrupt:
            raise KeyboardInterrupt("native-parent diagnostic cancelled") from None
        except Exception:
            self._disabled = True
            self._report["status"] = "native_parent_scope_unproved"

    def _check_close(self):
        if not self._target_ready:
            self._disabled = True
            self._report["status"] = "native_parent_bootstrap_unproved"
            return
        CacheProbeBase._check_close(self)
'''


def _base_source():
    if _sha(base.RUNTIME.encode("utf-8")) != BASE_RUNTIME_SHA256:
        _fail()
    tree = ast.parse(base.RUNTIME)
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Main")
    bootstrap = copy.deepcopy(next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "_configs"))
    bootstrap.name = "_bootstrap_configs"
    count = 0
    for item in ast.walk(bootstrap):
        if isinstance(item, ast.Compare) and ast.unparse(item.left) == "len(self.securities)":
            if ast.unparse(item) != "len(self.securities) != 2":
                _fail()
            item.comparators = [ast.Constant(1)]
            count += 1
    if count != 1:
        _fail()
    node.name = "CacheProbeBase"
    node.body = [n for n in node.body if not isinstance(n, ast.FunctionDef) or n.name not in ("initialize", "_configuration")]
    node.body.append(bootstrap)
    result = ast.unparse(ast.fix_missing_locations(tree))
    return result.replace("TPR_CACHE_PROBE_RESULT ", "TPR_PARENT_CACHE_PROBE_RESULT ")


def _render(parent, helper_source, operation_id, git_head, target_sha):
    if (type(helper_source) is not bytes or _sha(helper_source) != HELPER_SHA256
            or type(operation_id) is not str or re.fullmatch(r"TPR-CACHE-20261104-[A-Z0-9-]{1,40}", operation_id) is None
            or type(git_head) is not str or re.fullmatch("[a-f0-9]{40}", git_head) is None or git_head == "0"*40):
        _fail()
    binding = reader._binding_v2(parent["binding"])
    reader.validate_pointer_v2(parent["pointer"], binding=binding)
    config = {"schema": "tpr-native-parent-cache-config-v2", "source_epoch": EPOCH, "operation_id": operation_id,
        "git_head": git_head, "project_id": PROJECT_ID, "target_sid_sha256": target_sha,
        "parent_binding": binding, "parent_pointer": parent["pointer"], "sessions": list(SESSIONS)}
    raw = _wire(config)
    prefix = ("SOURCE_EPOCH = "+repr(EPOCH)+"\nCONFIG_JSON = "+repr(raw.decode("ascii"))
        +"\nCONFIG_SHA256 = "+repr(_sha(raw))+"\nCONFIG = __import__('json').loads(CONFIG_JSON)"
        +"\nFALSE_FLAGS = "+repr(FLAGS)+"\nHELPER_SHA256 = "+repr(HELPER_SHA256)
        +"\nPARENT_HELPER_SOURCE = "+repr(helper_source.decode("utf-8"))
        +"\nEXPECTED_TARGET_SHA256 = "+repr(target_sha)+"\nCONFIG_PARENT_BYTES = "+repr(binding["expected_bytes"])
        +"\nPARENT_VALIDATOR = {'__name__':'_tpr_fixed_parent_validator'}\n"
        +"import hashlib as _parent_source_hash\n"
        +"if _parent_source_hash.sha256(PARENT_HELPER_SOURCE.encode('utf-8')).hexdigest() != HELPER_SHA256: raise ValueError('fixed parent helper refused')\n"
        +"exec(compile(PARENT_HELPER_SOURCE, '<fixed_parent_validator>', 'exec'), PARENT_VALIDATOR)\n")
    source = (prefix+_base_source()+"\n"+RUNTIME).encode("utf-8")
    if not 0 < len(source) <= MAX_SOURCE_BYTES:
        _fail()
    compile(ast.parse(source), "main.py", "exec")
    report = {"schema": "tpr-native-parent-cache-build-v2", "source_epoch": EPOCH, "project_id": PROJECT_ID,
        "operation_id": operation_id, "git_head": git_head, "main_bytes": len(source), "main_sha256": _sha(source),
        "config_sha256": _sha(raw), "helper_sha256": HELPER_SHA256, "base_sha256": BASE_SHA256,
        "sessions": list(SESSIONS), "local_raw_sid_supplied": False, "raw_witness_export_authorized": False,
        "initialize_private_effects": False, "parent_contains_max": 1, "parent_reads_max": 1,
        "preopen_empty_slices_max": 400, "empty_slice_wait_window_ny": "00:00..09:30 exclusive; private reads only04:00..09:30 exclusive",
        "parent_bytes_expected": binding["expected_bytes"], "max_securities": 2,
        "input_canary_only": True, "hindsight_identity_diagnostic_only": True,
        "diagnostic_exception": "non_order_native_parent_cache_freshness_only",
        "native_requests_dispatched": 0, **{key: False for key in FLAGS}}
    return source, _wire(report)+b"\n"


def build_cache_probe(*, parent_probe_config_json, helper_source, operation_id, git_head):
    """Pure exact-source configuration input; never accepts a raw SID or body."""
    try:
        if (type(parent_probe_config_json) is not str or not parent_probe_config_json.isascii()
                or not 0 < len(parent_probe_config_json) <= 65536
                or _sha(parent_probe_config_json.encode("ascii")) != PARENT_CONFIG_SHA256):
            _fail()
        parent = _parse(parent_probe_config_json)
        binding = reader._binding_v2(parent["binding"])
        if (binding["project_id"] != 37650980 or binding["job_id"] != "12dd4732ba5d9d8f57950beb2a371c79"
                or type(binding["attempt"]) is not int or binding["attempt"] != 4
                or binding["expected_bytes"] != PARENT_BYTES or binding["expected_sha256"] != PARENT_WITNESS_SHA256
                or _sha(binding["key"].encode("ascii")) != PARENT_KEY_SHA256
                or binding["source_hashes"][reader.MODULE] != HELPER_SHA256):
            _fail()
        return _render(parent, helper_source, operation_id, git_head, TARGET_SID_SHA256)
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, StopIteration):
        _fail()


def _fixture_parent(case="valid"):
    """Synthetic cases only; no production override flag or private argument."""
    if case not in ("valid", "wrong_schema", "wrong_sid", "wrong_clock"):
        _fail()
    args = dict(operation_id="TPR-CMP28-MARK-SYNTHETIC", git_head="a"*40,
        source_hashes={reader.MODULE: HELPER_SHA256, reader.PRODUCER: "b"*64},
        off_operation_id="TPR-CMP28-OFF-SYNTHETIC", attempt=4, job_id="c"*32,
        config_sha256="d"*64, source_template_closure_sha256="e"*64,
        policy_sha256="f"*64, calendar_sha256="1"*64, expected_sha256="2"*64, expected_bytes=1)
    binding = reader.prepare_binding_v2(**args)
    body = {key: binding[key] for key in ("study_id", "candidate_id", "arm", "attempt", "project_id", "job_id",
        "config_sha256", "source_template_closure_sha256", "policy_sha256", "calendar_sha256")}
    predicates = {"observed_equals_expected": False, "expected_date_equals_algorithm": True,
        "observed_date_equals_session": False, "observed_relation": "before"}
    body.update(schema="tpr-cmp28-private-mark-refusal-v2", operation_id=binding["off_operation_id"],
        security_id="SYNTHETIC.CACHE 1" if case != "wrong_sid" else "SYNTHETIC.OTHER 2", data_type="trade_bar",
        algorithm_utc="2021-02-10T21:01:00+00:00", algorithm_local="2021-02-10T16:01:00-05:00",
        expected_close_utc="2021-02-10T21:00:00+00:00", expected_close_local="2021-02-10T16:00:00-05:00",
        observed_end_utc="2021-02-09T21:00:00+00:00", observed_end_local="2021-02-09T16:00:00-05:00",
        predicates=predicates, source_inputs_admitted=False, strategy_accepted=False, canonical_admission=False,
        valuation_verification_mode=reader.V2_MODE, verification_policy_extended=True)
    if case == "wrong_schema": body["schema"] = "invalid"
    if case == "wrong_clock": body["observed_end_local"] = "2021-02-09T15:00:00-05:00"
    raw = _wire(body)
    binding = reader.prepare_binding_v2(**{**args, "expected_sha256": _sha(raw), "expected_bytes": len(raw)})
    pointer = {"schema": binding["pointer_schema"], "status": "verified", "key": binding["key"], "bytes": len(raw),
        "expected_sha256": _sha(raw), "verified_sha256": _sha(raw), "readback_verified": True, "data_type": "trade_bar",
        "predicates": predicates, "reason_code": "minute_or_native_close_wrong_day_or_future",
        "valuation_verification_mode": reader.V2_MODE}
    return {"binding": binding, "pointer": pointer}, raw


def _build_fixture(*, helper_source, operation_id, git_head, case="valid"):
    parent, _ = _fixture_parent(case)
    return _render(parent, helper_source, operation_id, git_head, _sha(b"SYNTHETIC.CACHE 1"))
