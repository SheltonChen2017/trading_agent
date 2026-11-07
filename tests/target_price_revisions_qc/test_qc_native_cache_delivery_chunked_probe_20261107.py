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

from research.target_price_revisions_qc import native_cache_delivery_chunked_probe_20261107 as p

ROOT = Path(__file__).resolve().parents[2]
HELPER = (ROOT / p.reader.MODULE).read_bytes()
OP = "TPR-CACHE-20261104-CHUNKED-SYNTHETIC"
HEAD = "a" * 40


def render(**changes):
    return p._build_fixture(**{"helper_source": HELPER, "operation_id": OP, "git_head": HEAD, **changes})


# The imported fixture is public synthetic code, with no native/private effect.
_spec = importlib.util.spec_from_file_location("_delivery_chunked_prior_synthetic_fixtures",
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
    monkeypatch.setattr(_prior_fixtures, "OP", OP)
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



def canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def body(**changes):
    value = {"schema": p.OBSERVATION_SCHEMA, "source_epoch": p.EPOCH, "operation_id": OP,
        "root_head": HEAD, "actual_job_id": "c"*32, **{key: False for key in p.FLAGS}}
    value.update(changes)
    return value


def sized_body(size):
    value = body(public_synthetic_padding="")
    count = size-len(canonical(value))
    assert count >= 0
    value["public_synthetic_padding"] = "x"*count
    assert len(canonical(value)) == size
    return value


def frames(raw, *, prefix=""):
    raw = raw.decode("ascii") if type(raw) is bytes else raw
    digest = hashlib.sha256(raw.encode("ascii")).hexdigest()
    pieces = [raw[index:index+3000] for index in range(0, len(raw), 3000)]
    return [prefix+p.PART_TAG+str(index+1)+"/"+str(len(pieces))+" "+digest+" "+piece
        for index, piece in enumerate(pieces)]


def reassemble(lines, **changes):
    return p.reassemble_report(lines, **{"expected_operation_id": OP, "expected_head": HEAD,
        "expected_job_id": "c"*32, **changes})


def emit(value, *, json_module=json, hash_module=hashlib, hook=lambda *_: None):
    from types import SimpleNamespace
    lines = []
    namespace = {"json": json_module, "hashlib": hash_module}
    def log(line):
        hook(namespace, lines, line)
        lines.append(line)
    namespace["self"] = SimpleNamespace(_report=value, log=log)
    exec(compile(ast.parse(p.EMISSION), "synthetic_chunk_emission.py", "exec"), namespace)
    return lines


def test_chunk_builder_fixed_dependencies_helpers_identity_and_individual_caps():
    raw, report_raw = render()
    report = json.loads(report_raw)
    assert (raw, report_raw) == render()
    assert p.MAX_SOURCE_BYTES == 60000 and 0 < len(raw) <= 60000
    assert report["schema"] == p.BUILD_SCHEMA and report["source_epoch"] == p.EPOCH
    assert report["main_bytes"] == len(raw) and report["main_sha256"] == hashlib.sha256(raw).hexdigest()
    assert p.helper_module_source(HELPER) == p.plain.helper_module_source(HELPER)
    assert p.HELPER_MODULE_BYTES == 17368
    assert p.HELPER_MODULE_SHA256 == "8ab9c6dd9bbeb57c4e29dc88f4b0131046cba15a90899ddc44382ed73e13a98a"
    assert report["public_helper_module_bytes"] == 17368
    assert report["public_helper_module_sha256"] == p.HELPER_MODULE_SHA256
    assert p.REQUIRED_SOURCES == p.plain.REQUIRED_SOURCES | {p.MODULE}
    assert p.PINNED == {p.plain.MODULE: p.PLAIN_SHA256, **p.plain.PINNED}
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest for name, digest in p.PINNED.items())
    assert report["report_old_max_bytes"] == 16384 and report["report_max_bytes"] == 9000
    assert report["report_part_max_bytes"] == 3000 and report["report_parts_max"] == 3
    assert report["report_stream_precomputed"] and report["report_whole_sha256_before_emission"]
    assert report["report_parts_raw_contiguous_ascii"] and not report["report_pruning_authorized"]
    assert all(report[key] is False for key in p.FLAGS)
    assert set(inspect.signature(p.build_cache_probe).parameters) == {
        "parent_probe_config_json", "helper_source", "operation_id", "git_head"}
    assert set(inspect.signature(p.reassemble_report).parameters) == {
        "lines", "expected_operation_id", "expected_head", "expected_job_id"}


@pytest.mark.parametrize("operation", ["TPR-CACHE-20261104-CHUNKED-OFF-001", "TPR-CACHE-20261104-"+"A"*40])
def test_planned_and_maximum_operation_id_still_fit_source_cap(operation):
    assert len(render(operation_id=operation)[0]) <= 60000


@pytest.mark.parametrize("changes", [
    {"helper_source": b"arbitrary"}, {"operation_id": "wrong"}, {"git_head": "0"*40}, {"case": "other"},
])
def test_no_source_or_lineage_override(changes):
    with pytest.raises(p.ParentCacheRefusal):
        render(**changes)


def test_all_guard_census_and_terminal_statements_preceding_emission_are_ast_identical():
    raw, _ = render()
    old, _ = p.plain._build_fixture(helper_source=HELPER, operation_id=OP, git_head=HEAD)
    new_tree, old_tree = ast.parse(raw), ast.parse(old)
    for node in ast.walk(new_tree):
        if isinstance(node, ast.Constant) and node.value == p.OBSERVATION_SCHEMA:
            node.value = p.plain.OBSERVATION_SCHEMA
    classes = lambda t: {n.name: n for n in t.body if isinstance(n, ast.ClassDef)}
    for name in classes(old_tree):
        if name != "Main":
            assert ast.dump(classes(new_tree)[name], include_attributes=False) == ast.dump(classes(old_tree)[name], include_attributes=False)
    methods = lambda c: {n.name:n for n in c.body if isinstance(n, ast.FunctionDef)}
    new, prior = methods(classes(new_tree)["Main"]), methods(classes(old_tree)["Main"])
    assert set(new) == set(prior)
    for name in new:
        if name != "on_end_of_algorithm":
            assert ast.dump(new[name], include_attributes=False) == ast.dump(prior[name], include_attributes=False)
    assert ast.dump(ast.Module(body=new["on_end_of_algorithm"].body[:-2], type_ignores=[]), include_attributes=False) == ast.dump(
        ast.Module(body=prior["on_end_of_algorithm"].body[:-2], type_ignores=[]), include_attributes=False)
    assert ast.dump(ast.Module(body=new["on_end_of_algorithm"].body[-2:], type_ignores=[]), include_attributes=False) == ast.dump(
        ast.parse(p.EMISSION), include_attributes=False)
    text = ast.unparse(new["on_end_of_algorithm"])
    assert "16384" in text and "9000" in text and "3000" in text
    assert text.count("self.log(") == 1


@pytest.mark.parametrize("size,count", [(3000,1),(3001,2),(6000,2),(6001,3),(9000,3)])
def test_full_canonical_report_is_precomputed_then_emitted_as_raw_contiguous_pieces(size, count):
    value = sized_body(size)
    expected = canonical(value)
    def hook(namespace, lines, _):
        assert len(namespace["stream"]) == count  # before even the first native log
        if not lines:
            value["public_synthetic_padding"] = "changed after stream was frozen"
    lines = emit(value, hook=hook)
    assert len(lines) == count and max(map(len, lines)) < 3200
    result = reassemble(lines)
    assert result["whole_report_bytes"] == size
    assert result["whole_report_sha256"] == hashlib.sha256(expected).hexdigest()
    assert result["report"]["public_synthetic_padding"] != value["public_synthetic_padding"]
    assert canonical(result["report"]) == expected
    assert all(result[key] is False for key in p.ACCEPTANCE_FLAGS)
    assert not result["report_structure_independently_validated"]


@pytest.mark.parametrize("size", [9001,16384,16385])
def test_any_oversize_emits_exactly_one_fixed_refusal_without_partial_stream(size):
    assert emit(sized_body(size)) == [p.REFUSAL_LINE]
    with pytest.raises(p.ParentCacheRefusal):
        reassemble([p.REFUSAL_LINE])


@pytest.mark.parametrize("fault", ["serialization", "nonascii", "empty", "hash"])
def test_precomputation_failure_never_emits_any_partial_report(fault):
    from types import SimpleNamespace
    class Failure:
        def dumps(self, *_, **__):
            raise ValueError("synthetic private detail")
    options = {}
    if fault == "serialization": options["json_module"] = Failure()
    elif fault == "nonascii": options["json_module"] = SimpleNamespace(dumps=lambda *_, **__: "é")
    elif fault == "empty": options["json_module"] = SimpleNamespace(dumps=lambda *_, **__: "")
    else:
        def fail(*_): raise ValueError("synthetic private detail")
        options["hash_module"] = SimpleNamespace(sha256=fail)
    assert emit(body(), **options) == [p.REFUSAL_LINE]


def test_native_log_failure_leaves_incomplete_stream_unaccepted():
    partial = []
    def hook(_, __, line):
        if partial: raise RuntimeError("synthetic native log uncertainty")
        partial.append(line)
    with pytest.raises(RuntimeError):
        emit(sized_body(9000), hook=hook)
    assert len(partial) == 1
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(partial)


def test_existing_full_native_census_uses_chunked_report_without_any_missing_fields(native):
    n = bootstrap(native)
    report = complete(n)
    lines = [line for line in n.state.logs if p.PART_TAG in line]
    assert len(lines) <= 3 and lines
    result = p.reassemble_report(lines, expected_operation_id=OP, expected_head=HEAD,
        expected_job_id=n.algo._job)
    assert result["report"] == report
    assert result["whole_report_bytes"] == len(canonical(report)) <= 9000
    assert report["delivery_complete"] and not result["delivery_counts_accepted"]


def test_full_synthetic_report_maximum_counter_widths_fit_without_pruning_or_count_acceptance(native):
    n = bootstrap(native)
    report = json.loads(canonical(complete(n)))
    report.update(on_data_entries=6400, on_data_disabled_skips=6400,
        preopen_empty_slices=400, delivered_slices=6000, delivered_bar_rows=12000)
    for row in report["delivery"].values():
        row["callbacks"] = [600,600]
        for role in ("control","target"):
            row[role] = [600,600,86399999999,86399999999]
    # This proves framing capacity for resource-bound integer widths only.
    # It is deliberately not a certificate of consistent native accounting.
    raw = canonical(report)
    assert 6000 < len(raw) <= 9000
    result = p.reassemble_report(emit(report), expected_operation_id=OP,
        expected_head=HEAD, expected_job_id=n.algo._job)
    assert canonical(result["report"]) == raw
    assert not result["delivery_counts_accepted"] and not result["coverage_accepted"]


@pytest.mark.parametrize("fault", ["missing","extra","duplicate","reordered","mixed_digest","wrong_total",
    "wrong_index","zero_index","uppercase_hash","empty_piece","piece_oversize","prefix_oversize","prefix_control","nonascii","newline"])
def test_part_framing_refuses_incomplete_mixed_unbounded_or_reordered_stream(fault):
    lines = frames(canonical(sized_body(9000)))
    if fault == "missing": lines.pop()
    elif fault == "extra": lines.append("extra log")
    elif fault == "duplicate": lines[1] = lines[0]
    elif fault == "reordered": lines.reverse()
    elif fault == "mixed_digest": lines[1] = lines[1].replace(lines[1].split(" ")[2], "f"*64, 1)
    elif fault == "wrong_total": lines[0] = lines[0].replace("1/3", "1/2", 1)
    elif fault == "wrong_index": lines[0] = lines[0].replace("1/3", "2/3", 1)
    elif fault == "zero_index": lines[0] = lines[0].replace("1/3", "0/3", 1)
    elif fault == "uppercase_hash": lines[0] = lines[0].replace(lines[0].split(" ")[2], "A"*64, 1)
    elif fault == "empty_piece": lines[0] = " ".join(lines[0].split(" ")[:3])+" "
    elif fault == "piece_oversize": lines[0] += "x"
    elif fault == "prefix_oversize": lines[0] = "x"*513+lines[0]
    elif fault == "prefix_control": lines[0] = "\t"+lines[0]
    elif fault == "nonascii": lines[0] += "é"
    else: lines[0] += "\n"
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(lines)


def test_printable_qc_prefix_is_bounded_and_no_piece_whitespace_is_trimmed():
    raw = canonical(body())
    assert reassemble(frames(raw, prefix="2021-02-12 21:05:00 "+"x"*492))["framing_complete"]
    lines = frames(raw)
    lines[0] += " "
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(lines)


@pytest.mark.parametrize("value", [None, [], (), iter(()), b"not lines", [None]])
def test_part_container_is_closed_and_bounded_without_iterating_unknown_inputs(value):
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(value)


@pytest.mark.parametrize("changes", [
    {"expected_operation_id":"wrong"},{"expected_head":"A"*40},{"expected_job_id":"z"*32},
    {"expected_operation_id":True},{"expected_head":None},{"expected_job_id":1},
])
def test_expected_native_bindings_are_exact_typed_metadata(changes):
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(frames(canonical(body())), **changes)


@pytest.mark.parametrize("key,value", [
    ("schema","old"),("source_epoch","old"),("operation_id","wrong"),("root_head","b"*40),
    ("actual_job_id","b"*32),("financial_acceptance",True),("delivery_counts_accepted",True),
])
def test_whole_hash_cannot_promote_wrong_source_job_or_acceptance_header(key, value):
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(frames(canonical(body(**{key:value}))))


def test_all_original_false_flags_must_be_present_and_false():
    for key in p.FLAGS:
        missing = body();missing.pop(key)
        with pytest.raises(p.ParentCacheRefusal):
            reassemble(frames(canonical(missing)))
        with pytest.raises(p.ParentCacheRefusal):
            reassemble(frames(canonical(body(**{key:True}))))


@pytest.mark.parametrize("replacement", [b"NaN",b"Infinity",b"1.5",b"01",b"[1,]",
    b'{"x":0,"x":1}',b'{"x":0,"\\u0078":1}',b'"bad\\q"',b'"\\ud800"'])
def test_strict_complete_json_is_checked_after_whole_stream_hash(replacement):
    raw = canonical(body(extra="SENTINEL")).replace(b'"SENTINEL"', replacement)
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(frames(raw))


def test_whole_hash_failure_precedes_json_decoding(monkeypatch):
    lines = frames(canonical(body()))
    lines[0] = lines[0].replace(lines[0].split(" ")[2], "f"*64, 1)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("JSON decoded before whole hash")
    monkeypatch.setattr(p.json, "loads", forbidden)
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(lines)
    assert calls == []


def test_json_depth_node_and_cumulative_limits_are_independent():
    assert (p.MAX_DEPTH,p.MAX_NODES,p.MAX_REPORT_BYTES,p.PART_BYTES,p.MAX_PARTS) == (16,4096,9000,3000,3)
    raw = canonical(body(extra="SENTINEL"))
    assert reassemble(frames(raw.replace(b'"SENTINEL"',b"["*15+b"0"+b"]"*15)))["strict_json_complete"]
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(frames(raw.replace(b'"SENTINEL"',b"["*16+b"0"+b"]"*16)))
    assert reassemble(frames(canonical(body(extra=[0]*3800))))["strict_json_complete"]
    too_many_nodes = canonical(body(extra=[0]*4050))
    assert len(too_many_nodes) <= 9000
    with pytest.raises(p.ParentCacheRefusal):
        reassemble(frames(too_many_nodes))


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
