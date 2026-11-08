"""Synthetic plaintext-module and unchanged delivery-census regressions."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from research.target_price_revisions_qc import native_cache_delivery_plain_probe_20261107 as p

ROOT = Path(__file__).resolve().parents[2]
HELPER = (ROOT / p.reader.MODULE).read_bytes()
OP = "TPR-CACHE-20261104-PLAIN-SYNTHETIC"
HEAD = "a" * 40


def render(**changes):
    return p._build_fixture(**{"helper_source": HELPER, "operation_id": OP, "git_head": HEAD, **changes})


# The imported fixture is public synthetic code, with no native/private effect.
_spec = importlib.util.spec_from_file_location("_delivery_plain_prior_synthetic_fixtures",
    Path(__file__).with_name("test_qc_native_cache_parent_probe_v5_20261104.py"))
_prior_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prior_fixtures)


@pytest.fixture
def helper_module(monkeypatch):
    name = p.HELPER_FILENAME.removesuffix(".py")
    module = ModuleType(name)
    exec(compile(p.helper_module_source(HELPER), p.HELPER_FILENAME, "exec"), module.__dict__)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture
def native(monkeypatch, helper_module):
    monkeypatch.setattr(_prior_fixtures, "p", p)
    return _prior_fixtures.native.__wrapped__(monkeypatch)


def bootstrap(native):
    n = native()
    n.algo.on_data(n.algo.current_slice)
    assert n.algo._target_ready and not n.algo._disabled
    return n


def _target(n):
    return n.algo._symbols["target"]


def event(n, day, hour, minute, *, absent=False, stale_cache=False):
    data = n.at(day, hour, minute)
    target = _target(n)
    if absent:
        data.bars.pop(target)
    if stale_cache:
        n.algo._registered["target"].last = n.TradeBar(target, datetime(2021, 2, day-1, 16))
    return data


def complete(n, *, absent_day=10, skip_day=None, late_target=True):
    for day in range(8, 13):
        data = event(n, day, 15, 59, absent=day == absent_day, stale_cache=day == absent_day)
        if day != skip_day:
            n.algo.on_data(data)
        event(n, day, 16, 1, absent=day == absent_day, stale_cache=day == absent_day)
        n.state.callback()
        data = event(n, day, 16, 2, absent=day == absent_day or not late_target,
            stale_cache=day == absent_day)
        if day != skip_day:
            n.algo.on_data(data)
    n.algo.on_end_of_algorithm()
    return n.algo._report


def test_fixed_plain_renderer_reports_both_exact_files_and_complete_source_closure():
    raw, report_raw = render()
    report = json.loads(report_raw)
    module = p.helper_module_source(HELPER)
    assert (raw, report_raw) == render()
    assert p.MAX_SOURCE_BYTES == 60000 and 0 < len(raw) < 60000
    assert report["schema"] == p.BUILD_SCHEMA and report["source_epoch"] == p.EPOCH
    assert report["main_bytes"] == len(raw) and report["main_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["public_helper_representation"] == p.PUBLIC_HELPER_REPRESENTATION
    assert report["public_helper_module_filename"] == p.HELPER_FILENAME
    assert report["public_helper_module_bytes"] == len(module) == p.HELPER_MODULE_BYTES == 17368
    assert report["public_helper_module_sha256"] == hashlib.sha256(module).hexdigest() == p.HELPER_MODULE_SHA256
    assert report["public_helper_plain_bytes"] == 17338
    assert report["public_helper_plain_sha256"] == p.HELPER_SHA256
    assert report["public_helper_bytes_preserved"] is True
    assert report["significant_tokens_preserved"] is True
    assert report["delivery_cell_fields"] == list(p.CELL_FIELDS)
    assert report["delivery_callback_fields"] == ["before_close_attempt", "after_close_attempt"]
    assert report["delivery_native_slice_endpoint_samples_max"] == 24000
    assert not report["import_loader_origin_attested"] and not report["source_import_atomicity_attested"]
    assert report["native_requests_dispatched"] == 0 and all(report[k] is False for k in p.FLAGS)
    assert set(inspect.signature(p.build_cache_probe).parameters) == {
        "parent_probe_config_json", "helper_source", "operation_id", "git_head"}
    assert p.helper_module_bytes is p.helper_module_source
    assert p.REQUIRED_SOURCES == p.delivery.REQUIRED_SOURCES | {p.MODULE}
    assert p.PINNED == {p.delivery.MODULE: p.DELIVERY_SHA256, **p.delivery.PINNED}
    assert set(p.PINNED) == {p.delivery.MODULE, p.prior.MODULE, p.base.MODULE, p.reader.MODULE}
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
        for name, digest in p.PINNED.items())


@pytest.mark.parametrize("operation", [
    "TPR-CACHE-20261104-PLAIN-OFF-001",
    "TPR-CACHE-20261104-" + "A" * 40,
])
def test_fixed_route_and_maximum_operation_ids_fit_individual_source_caps(operation):
    raw, report = render(operation_id=operation)
    assert len(raw) <= 60000 and len(p.helper_module_source(HELPER)) <= 60000
    assert json.loads(report)["operation_id"] == operation


@pytest.mark.parametrize("changes", [
    {"helper_source": b"unreviewed code"}, {"operation_id": "wrong"},
    {"git_head": "0" * 40}, {"case": "unreviewed"},
])
def test_no_arbitrary_source_or_lineage_override(changes):
    with pytest.raises(p.ParentCacheRefusal):
        render(**changes)


def test_unpinned_private_config_is_refused_without_reading_or_echo():
    with pytest.raises(p.ParentCacheRefusal, match="^fixed native-parent cache diagnostic refused$"):
        p.build_cache_probe(parent_probe_config_json="PRIVATE", helper_source=HELPER,
            operation_id=OP, git_head=HEAD)


def test_helper_module_is_one_ordinary_literal_with_physically_verbatim_full_source():
    raw = p.helper_module_source(HELPER)
    assert raw == b"PUBLIC_PARENT_SOURCE = '''" + HELPER + b"'''\n"
    assert b"\\" not in HELPER and b"'''" not in HELPER
    assert HELPER.endswith(b"\n") and raw.count(HELPER) == 1
    assert len(raw) < 60000
    tree = ast.parse(raw)
    assert len(tree.body) == 1
    node = tree.body[0]
    assert isinstance(node, ast.Assign) and len(node.targets) == 1
    assert isinstance(node.targets[0], ast.Name) and node.targets[0].id == "PUBLIC_PARENT_SOURCE"
    assert isinstance(node.value, ast.Constant) and type(node.value.value) is str
    assert node.value.value.encode("utf-8") == HELPER
    assert hashlib.sha256(node.value.value.encode("utf-8")).hexdigest() == p.HELPER_SHA256
    assert ast.dump(ast.parse(node.value.value), include_attributes=False) == ast.dump(ast.parse(HELPER), include_attributes=False)
    assert not any(isinstance(n, (ast.Call, ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)) for n in ast.walk(tree))


@pytest.mark.parametrize("value", [None, "", b"", bytearray(b"x"), b"x"*17338, HELPER+b"x", HELPER[:-1]])
def test_helper_module_rejects_every_nonexact_public_payload_without_echo(value):
    with pytest.raises(p.ParentCacheRefusal, match="^fixed native-parent cache diagnostic refused$"):
        p.helper_module_source(value)


@pytest.mark.parametrize("field,value", [
    ("HELPER_MODULE_SHA256", "f"*64), ("HELPER_MODULE_BYTES", 17369),
    ("HELPER_SHA256", "f"*64), ("MAX_SOURCE_BYTES", 17367),
])
def test_module_caps_and_pins_fail_closed(monkeypatch, field, value):
    monkeypatch.setattr(p, field, value)
    with pytest.raises(p.ParentCacheRefusal):
        p.helper_module_source(HELPER)


def _prefix():
    raw, _ = render()
    tree = ast.parse(raw)
    first = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.ImportFrom)
        and node.module == "AlgorithmImports")
    tree.body = tree.body[:first]
    return compile(ast.fix_missing_locations(tree), "synthetic_plain_prefix.py", "exec")


def test_fixed_import_preserves_original_checksum_before_original_validator_namespace(helper_module):
    namespace = {}
    exec(_prefix(), namespace)
    assert namespace["PARENT_HELPER_SOURCE"].encode("utf-8") == HELPER
    assert namespace["PARENT_VALIDATOR"]["__name__"] == "_tpr_fixed_parent_validator"
    assert namespace["PARENT_VALIDATOR"]["MODULE"] == p.reader.MODULE
    assert callable(namespace["PARENT_VALIDATOR"]["project_witness_v2"])
    tree = ast.parse(render()[0])
    old = ast.parse(p.prior._build_fixture(helper_source=HELPER, operation_id=OP, git_head=HEAD)[0])
    imports = [n for n in tree.body if isinstance(n, ast.ImportFrom)
        and n.module == p.HELPER_FILENAME.removesuffix(".py")]
    assert len(imports) == 1
    assert [(n.name, n.asname) for n in imports[0].names] == [("PUBLIC_PARENT_SOURCE", "PARENT_HELPER_SOURCE")]
    guards = lambda t: [n for n in t.body if isinstance(n, ast.If)
        and "HELPER_SHA256" in ast.unparse(n) and "fixed parent helper refused" in ast.unparse(n)]
    assert len(guards(tree)) == len(guards(old)) == 1
    assert ast.dump(guards(tree)[0], include_attributes=False) == ast.dump(guards(old)[0], include_attributes=False)
    guard_at = tree.body.index(guards(tree)[0])
    exec_at = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == "exec")
    assert tree.body.index(imports[0]) < guard_at < exec_at
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {"decompress", "compress", "b64decode", "b64encode", "flush", "decode"}
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom))
        and any(a.name in {"base64", "zlib"} for a in n.names) for n in ast.walk(tree))


@pytest.mark.parametrize("kind", ["none", "bytes", "subclass", "long", "short", "wrong", "unicode"])
def test_imported_helper_value_is_bounded_builtin_str_and_checked_before_exec(helper_module, kind):
    class Foreign(str):
        def encode(self, *args, **kwargs):
            raise AssertionError("custom encode must not execute")
    value = {"none": None, "bytes": HELPER, "subclass": Foreign(HELPER.decode()),
        "long": HELPER.decode()+"x", "short": HELPER.decode()[:-1], "wrong": "x"*17338,
        "unicode": "é"*17338}[kind]
    helper_module.PUBLIC_PARENT_SOURCE = value
    namespace = {}
    with pytest.raises(ValueError, match="^fixed parent helper refused$"):
        exec(_prefix(), namespace)
    assert not namespace.get("PARENT_VALIDATOR", {}).get("project_witness_v2")


def test_plain_builder_has_no_filesystem_effect_or_codec_call():
    tree = ast.parse(Path(p.__file__).read_bytes())
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {"read_bytes", "read_text", "open", "download", "execute_plan", "execute_action",
        "compress", "decompress", "b64encode", "b64decode"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in {"repr", "eval", "exec"} for n in ast.walk(tree))


def test_sensor_metadata_endpoint_samples_add_no_config_or_cache_query(native):
    n = bootstrap(native)
    data = event(n, 9, 10, 1)
    before_gets = n.state.cached_gets
    configs, samples = [], []
    n.state.config_hook = lambda rows: configs.append(rows) or rows
    original = n.algo._cache_values
    def metadata(bar):
        samples.append(bar)
        return original(bar)
    n.algo._cache_values = metadata
    n.algo._delivery(data)
    assert len(samples) == 4  # two roles, two metadata snapshots each
    assert n.state.cached_gets == before_gets and not configs


@pytest.mark.parametrize("source", [
    "x = [1, 2, 'a  b']\n",
    'def f(x):\n    return (x + 1, """a\\nb  c""")\n',
    "# exact comment\nx = {'q': 'literal   spaces'}\n",
])
def test_existing_compactor_preserves_every_significant_token_and_ast(source):
    compact = p._compact(source)
    assert p._tokens(source) == p._tokens(compact)
    assert ast.dump(ast.parse(source), include_attributes=False) == ast.dump(ast.parse(compact), include_attributes=False)


def test_new_source_keeps_guard_classes_and_unmodified_methods_exact():
    raw, _ = render()
    prior_raw, _ = p.prior._build_fixture(helper_source=HELPER, operation_id=OP, git_head=HEAD)
    new, old = ast.parse(raw), ast.parse(prior_raw)
    classes = lambda tree: {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    for name in ("CacheProbeBase", "DiagnosticGuardRefusal"):
        assert ast.dump(classes(new)[name], include_attributes=False) == ast.dump(classes(old)[name], include_attributes=False)
    methods = lambda cls: {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    old_methods, new_methods = methods(classes(old)["Main"]), methods(classes(new)["Main"])
    assert set(new_methods) == set(old_methods) | {"_delivery"}
    for name in set(old_methods) - {"initialize", "on_data", "on_end_of_algorithm"}:
        assert ast.dump(new_methods[name], include_attributes=False) == ast.dump(old_methods[name], include_attributes=False)
    assert "self._configs(" not in ast.unparse(new_methods["_delivery"])
    assert "self._cache_values(" in ast.unparse(new_methods["_delivery"])


def test_fixed_two_role_sensor_counts_measured_absence_without_claiming_no_trades(native):
    n = bootstrap(native)
    report = complete(n)
    assert report["schema"] == p.OBSERVATION_SCHEMA
    assert report["delivery_complete"] is True and report["status"] == "complete_cache_observations"
    assert report["delivery_counts_status"] == "measured_events_only"
    assert report["target_close_canary_days"] == 4
    for day in range(8, 13):
        row = report["delivery"][f"2021-02-{day:02}"]
        assert row["callbacks"] == ([2, 1] if day == 8 else [1, 1])
        assert row["control"][:2] == ([2, 1] if day == 8 else [1, 1])
        assert row["target"][:2] == ([0, 0] if day == 10 else [1, 1])
        assert row["target"][2:] == ([None, None] if day == 10 else [57540000000, 57600000000])
    assert all(report[key] is False for key in p.FLAGS)
    assert not report["provider_wide_absence_proven"] and not report["financial_acceptance"]


def test_slice_delivery_and_stale_cache_remain_independent_observations(native):
    n = bootstrap(native)
    report = complete(n, absent_day=None)
    assert report["delivery_complete"]
    # Make a fresh synthetic run with stale cache but a current target Slice bar.
    n = bootstrap(native)
    for day in range(8, 13):
        n.algo.on_data(event(n, day, 15, 59))
        event(n, day, 16, 1, stale_cache=day == 10)
        n.state.callback()
        n.algo.on_data(event(n, day, 16, 2, stale_cache=day == 10))
    n.algo.on_end_of_algorithm()
    assert n.algo._report["delivery_complete"]
    assert n.algo._report["target_close_canary_days"] == 4
    assert n.algo._report["delivery"]["2021-02-10"]["target"][:2] == [1, 1]
    assert n.algo._report["sessions"]["2021-02-10"]["target"]["same_session"] is False


def test_late_events_and_duplicate_endpoints_never_backfill_before_close_attempt(native):
    n = bootstrap(native)
    n.algo.on_data(event(n, 8, 15, 59))
    event(n, 8, 16, 1)
    n.state.callback()
    before = list(n.algo._report["delivery"]["2021-02-08"]["target"])
    n.algo.on_data(event(n, 8, 16, 2))
    n.algo.on_data(event(n, 8, 16, 3))
    after = n.algo._report["delivery"]["2021-02-08"]["target"]
    assert (after[0], after[2]) == (before[0], before[2])
    assert after[1] == 2 and after[3] == 57600000000  # event count, not unique trade volume


@pytest.mark.parametrize("skip_day", range(8, 13))
def test_missing_pre_or_post_callback_coverage_is_incomplete_not_measured_zero(native, skip_day):
    n = bootstrap(native)
    report = complete(n, skip_day=skip_day)
    # Bootstrap provides a before callback on Feb8 but no after callback when skipped.
    assert report["delivery_complete"] is False
    assert report["delivery_counts_status"] == "provisional_unproved"
    assert report["status"] == "diagnostic_failed"
    assert report["first_failure_code"] == "coverage_incomplete"
    assert report["financial_acceptance"] is False


@pytest.mark.parametrize("fault", [
    "ff", "period", "duration", "future", "wrong_day", "wrong_sid", "untyped",
    "foreign_key", "slice_reference", "clock_mismatch", "lock", "out_of_order",
])
def test_delivery_metadata_faults_fail_closed_without_market_values(native, fault):
    n = bootstrap(native)
    data = event(n, 9, 10, 1)
    target = _target(n)
    bar = data.bars[target]
    if fault == "ff": bar.is_fill_forward = True
    elif fault == "period": bar.period = timedelta(days=1)
    elif fault == "duration": bar.time -= timedelta(minutes=1)
    elif fault == "future": bar.time += timedelta(minutes=2);bar.end_time += timedelta(minutes=2)
    elif fault == "wrong_day": bar.time -= timedelta(days=1);bar.end_time -= timedelta(days=1)
    elif fault == "wrong_sid": bar.symbol = n.algo._symbols["control"]
    elif fault == "untyped": data.bars[target] = object()
    elif fault == "foreign_key": data.bars = {object(): bar}
    elif fault == "slice_reference": data = n.Slice(dict(data.bars))
    elif fault == "clock_mismatch": n.algo.utc_time += timedelta(minutes=1)
    elif fault == "lock": n.state.lock = False
    elif fault == "out_of_order":
        n.algo.on_data(data)
        data = event(n, 9, 10, 2)
        data.bars[target].time -= timedelta(minutes=2)
        data.bars[target].end_time -= timedelta(minutes=2)
    n.algo.on_data(data)
    first = (n.algo._report["first_failure_stage"], n.algo._report["first_failure_code"])
    assert n.algo._disabled and first[0] == "data_delivery"
    n.algo.on_data(data);n.algo.on_end_of_algorithm()
    assert not n.algo._report["delivery_complete"]
    assert (n.algo._report["first_failure_stage"], n.algo._report["first_failure_code"]) == first
    assert "SYNTHETIC.CACHE" not in n.state.logs[-1]


@pytest.mark.parametrize("fault", ["bar_reference", "clock", "current_slice"])
def test_endpoint_mutation_is_detected_and_partial_counts_never_become_complete(native, fault):
    n = bootstrap(native)
    data = event(n, 9, 10, 1)
    original = n.algo._cache_values
    changed = False
    def metadata(bar):
        nonlocal changed
        value = original(bar)
        if not changed:
            changed = True
            if fault == "bar_reference":
                data.bars[bar.symbol] = n.TradeBar(bar.symbol, bar.end_time)
            elif fault == "clock":
                n.algo.time += timedelta(minutes=1);n.algo.utc_time += timedelta(minutes=1)
            else:
                n.algo.current_slice = n.Slice(dict(data.bars))
        return value
    n.algo._cache_values = metadata
    n.algo.on_data(data)
    assert n.algo._disabled and n.algo._report["first_failure_stage"] == "data_delivery"
    n.algo.on_end_of_algorithm()
    assert n.algo._report["delivery_complete"] is False


@pytest.mark.parametrize("fault", ["time", "end_time", "fill_forward", "sid"])
def test_same_reference_metadata_mutation_requires_a_second_snapshot(native, fault):
    n = bootstrap(native)
    data = event(n, 9, 10, 1)
    original = n.algo._cache_values
    changed = False
    def metadata(bar):
        nonlocal changed
        value = original(bar)
        if not changed:
            changed = True
            if fault == "time": bar.time -= timedelta(minutes=1)
            elif fault == "end_time": bar.end_time -= timedelta(minutes=1)
            elif fault == "fill_forward": bar.is_fill_forward = True
            else: bar.symbol = n.algo._symbols["target"]
        return value
    n.algo._cache_values = metadata
    n.algo.on_data(data)
    assert n.algo._disabled and n.algo._report["first_failure_stage"] == "data_delivery"
    n.algo.on_end_of_algorithm()
    assert n.algo._report["delivery_complete"] is False
    assert n.algo._report["delivery_counts_status"] == "provisional_unproved"


def test_sensor_never_reads_ohlc_price_volume_or_other_financial_getters(native):
    n = bootstrap(native)
    data = event(n, 9, 10, 1)
    class Trap(n.TradeBar):
        def __getattribute__(self, name):
            if name in {"open", "high", "low", "close", "price", "value", "volume"}:
                raise AssertionError("market value getter touched")
            return super().__getattribute__(name)
    for key, value in list(data.bars.items()):
        data.bars[key] = Trap(key, value.end_time)
    n.algo.on_data(data)
    assert not n.algo._disabled
    assert n.algo._report["delivery"]["2021-02-09"]["target"][0] == 1


def test_existing_event_caps_prevent_sensor_counter_growth_and_preserve_first_failure(native):
    n = bootstrap(native)
    before = json.loads(json.dumps(n.algo._report["delivery"]))
    n.algo._slices = 6000
    n.algo.on_data(event(n, 9, 10, 1))
    assert n.algo._disabled and n.algo._report["delivery"] == before
    first = n.algo._report["first_failure_code"]
    n.algo.on_data(n.algo.current_slice);n.algo.on_end_of_algorithm()
    assert n.algo._report["first_failure_code"] == first
    assert n.algo._report["delivery_complete"] is False


def test_terminal_custody_failure_withdraws_delivery_completeness(native):
    n = bootstrap(native)
    report = complete(n)
    assert report["delivery_complete"] is True
    n.state.lock = False
    n.algo.on_end_of_algorithm()
    assert report["delivery_complete"] is False and report["status"] == "diagnostic_failed"


def test_final_source_byte_cap_remains_load_bearing(monkeypatch):
    size = len(render()[0])
    monkeypatch.setattr(p, "MAX_SOURCE_BYTES", size-1)
    with pytest.raises(p.ParentCacheRefusal):
        render()
