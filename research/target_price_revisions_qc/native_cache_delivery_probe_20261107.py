"""Pure fixed OFF delivery census; no private input is read by this module.

The exact v5 bootstrap, cache observations and guards remain in the rendered
program. A separate per-session callback/TradeBar census never supplies a
financial mark. Its public parent validator is transported in a fixed bounded
zlib/base64 envelope; its complete 17,338 bytes and SHA are verified before exec.
"""
from __future__ import annotations

import ast
import base64
import copy
import hashlib
import io
import json
import tokenize
import zlib

from . import native_cache_parent_probe_v5_20261104 as prior

MODULE = "research/target_price_revisions_qc/native_cache_delivery_probe_20261107.py"
EPOCH = "TPR-NATIVE-PARENT-DELIVERY-20261107-v1"
PROJECT_ID, TARGET_SID_SHA256, SESSIONS = prior.PROJECT_ID, prior.TARGET_SID_SHA256, prior.SESSIONS
reader, base = prior.reader, prior.base
HELPER_SHA256 = prior.HELPER_SHA256
MAX_SOURCE_BYTES = 60000
PRIOR_SHA256 = "6f26b28afdbcb35c10f89245e267ed6a7618ff3a0ee137977ad0d0ec3dc548a1"
REQUIRED_SOURCES = prior.REQUIRED_SOURCES | frozenset((MODULE, prior.MODULE))
PINNED = {prior.MODULE: PRIOR_SHA256, **prior.PINNED}
FLAGS = prior.FLAGS
ParentCacheRefusal = prior.ParentCacheRefusal
_fail, _wire, _fixture_parent = prior._fail, prior._wire, prior._fixture_parent
PUBLIC_HELPER_PLAIN_BYTES = 17338
PUBLIC_HELPER_MAX_ENCODED_BYTES = 8192
PUBLIC_HELPER_ENCODING = "fixed_public_base64_zlib_bounded_v1"
PUBLIC_HELPER_B64 = "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"
CONFIG_SCHEMA = "tpr-native-delivery-cache-config-v1"
BUILD_SCHEMA = "tpr-native-delivery-cache-build-v1"
OBSERVATION_SCHEMA = "tpr-native-delivery-cache-observations-v1"
CELL_FIELDS = ("before_close_attempt_events", "after_close_attempt_events",
    "last_before_end_since_midnight_us", "last_after_end_since_midnight_us")

# These are delivery events, not share volume or distinct trades. The known
# two-role membership checks avoid assuming how a .NET dictionary iterates.
DELIVERY_METHOD = r'''
def _delivery(self, data):
    now = clock(self.utc_time, "UTC")
    day = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    if (now != clock(self.time, "America/New_York") or day not in self._report["delivery"]
            or not NetObject.ReferenceEquals(data, self.current_slice)
            or self._delivery_previous_now is not None and now < self._delivery_previous_now):
        raise ValueError("delivery scope unproved")
    bucket = int(day in self._seen)
    self._report["delivery"][day]["callbacks"][bucket] += 1
    found, frames = 0, []
    for label, symbol in self._symbols.items():
        if symbol in data.bars:
            found += 1
            bar = data.bars[symbol]
            frame = self._cache_values(bar)
            frames.append((symbol, bar, frame))
            if not (frame[1] and frame[2] == str(symbol.id) and frame[3] is False
                    and frame[4] == frame[6]-frame[5] == timedelta(minutes=1)
                    and frame[6] <= now):
                raise ValueError("delivery metadata unproved")
            ended = frame[6].astimezone(ZoneInfo("America/New_York"))
            if ended.date().isoformat() != day or not NetObject.ReferenceEquals(bar, data.bars[symbol]):
                raise ValueError("delivery identity unproved")
            row = self._report["delivery"][day][label]
            offset = ((ended.hour*60+ended.minute)*60+ended.second)*1000000+ended.microsecond
            previous = max((value for value in row[2:] if value is not None), default=None)
            if previous is not None and offset < previous:
                raise ValueError("delivery order unproved")
            row[bucket] += 1
            row[bucket+2] = offset
    self._bound()
    if (found != len(data.bars) or now != clock(self.utc_time, "UTC")
            or now != clock(self.time, "America/New_York")
            or not NetObject.ReferenceEquals(data, self.current_slice)):
        raise ValueError("delivery endpoint unproved")
    if any(not NetObject.ReferenceEquals(bar, data.bars[symbol])
            or frame != self._cache_values(data.bars[symbol]) for symbol, bar, frame in frames):
        raise ValueError("delivery metadata changed")
    if (now != clock(self.utc_time, "UTC") or now != clock(self.time, "America/New_York")
            or not NetObject.ReferenceEquals(data, self.current_slice)):
        raise ValueError("delivery endpoint changed")
    self._delivery_previous_now = now
'''

# This prefix decodes only a fixed, bounded public source literal. There is no
# decoder callback, runtime source override, flush, external read or raw SID.
PACKED_PREFIX = r'''
import base64 as _helper_base64
import zlib as _helper_zlib
_HELPER_PUBLIC_B64 = __ENCODED_LITERAL__
if len(_HELPER_PUBLIC_B64) > 8192:
    raise ValueError("fixed public helper envelope refused")
_helper_decoder = _helper_zlib.decompressobj()
_helper_decoded = _helper_decoder.decompress(_helper_base64.b64decode(_HELPER_PUBLIC_B64, validate=True), 17339)
if (len(_helper_decoded) != 17338 or not _helper_decoder.eof
        or _helper_decoder.unused_data or _helper_decoder.unconsumed_tail):
    raise ValueError("fixed public helper envelope refused")
PARENT_HELPER_SOURCE = _helper_decoded.decode("utf-8")
del _helper_decoder, _helper_decoded
'''


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _packed_helper_bytes():
    """Verify the fixed public envelope locally without accepting an override."""
    try:
        if type(PUBLIC_HELPER_B64) is not str or not 0 < len(PUBLIC_HELPER_B64) <= PUBLIC_HELPER_MAX_ENCODED_BYTES:
            _fail()
        encoded = base64.b64decode(PUBLIC_HELPER_B64, validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(encoded, PUBLIC_HELPER_PLAIN_BYTES+1)
        if (len(raw) != PUBLIC_HELPER_PLAIN_BYTES or not decoder.eof
                or decoder.unused_data or decoder.unconsumed_tail or _sha(raw) != HELPER_SHA256):
            _fail()
        return raw
    except (ValueError, TypeError, UnicodeError, zlib.error):
        _fail()


def _tokens(source):
    return tuple((item.type, item.string) for item in tokenize.generate_tokens(io.StringIO(source).readline)
        if item.type not in (tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER))


def _compact(source):
    """Keep all significant tokens, literal contents and the complete AST."""
    compacted = prior._compact_indentation(source)
    if (_tokens(source) != _tokens(compacted)
            or ast.dump(ast.parse(source), include_attributes=False)
            != ast.dump(ast.parse(compacted), include_attributes=False)):
        _fail()
    return compacted


def _function(main, name):
    matches = [node for node in main.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        _fail()
    return matches[0]


def _delivery_tree(source):
    """Add only the fixed census to a fresh copy of the exact prior program."""
    tree = ast.parse(source)
    main = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Main")
    initialize = _function(main, "initialize")
    report_assignments = [(i, node) for i, node in enumerate(initialize.body)
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "self._report"]
    if len(report_assignments) != 1 or not isinstance(report_assignments[0][1].value, ast.Dict):
        _fail()
    index, report = report_assignments[0]
    schema = [value for key, value in zip(report.value.keys, report.value.values)
        if isinstance(key, ast.Constant) and key.value == "schema"]
    if len(schema) != 1 or not isinstance(schema[0], ast.Constant) or schema[0].value != "tpr-native-parent-cache-observations-v5":
        _fail()
    schema[0].value = OBSERVATION_SCHEMA
    initialize.body[index+1:index+1] = ast.parse('''
self._report["delivery"] = {day: {**{role: [0, 0, None, None] for role in ("control", "target")}, "callbacks": [0, 0]} for day in CONFIG["sessions"]}
self._report["delivery_complete"] = False
self._report["delivery_counts_status"] = "provisional_unproved"
self._delivery_previous_now = None
''').body
    on_data = _function(main, "on_data")
    passed = [node for node in ast.walk(on_data) if isinstance(node, ast.If)
        and ast.unparse(node.test) == "self._disabled" and node.orelse]
    if len(passed) != 1 or ast.unparse(passed[0].orelse[0]) != "self._completed('data_delivery')":
        _fail()
    passed[0].orelse.insert(0, ast.parse("self._delivery(data)").body[0])
    main.body.append(ast.parse(DELIVERY_METHOD).body[0])
    end = _function(main, "on_end_of_algorithm")
    status = [i for i, node in enumerate(end.body) if isinstance(node, ast.Assign)
        and ast.unparse(node.targets[0]) == "self._report['status']"]
    if len(status) != 1:
        _fail()
    end.body[status[0]+1:status[0]+1] = ast.parse('''
self._report["delivery_complete"] = self._report["status"] == "complete_cache_observations" and all(all(row["callbacks"]) for row in self._report["delivery"].values())
self._report["delivery_counts_status"] = "measured_events_only" if self._report["delivery_complete"] else "provisional_unproved"
if not self._report["delivery_complete"]:
    self._stage("end_coverage")
    self._failure(code="coverage_incomplete", category="state")
    self._report["status"] = "diagnostic_failed"
''').body
    return ast.fix_missing_locations(tree)


def _finish(source, report_raw, helper_source):
    try:
        if type(source) is not bytes or type(report_raw) is not bytes or helper_source != _packed_helper_bytes():
            _fail()
        report = json.loads(report_raw)
        if (report["schema"] != "tpr-native-parent-cache-build-v5" or report["main_bytes"] != len(source)
                or report["main_sha256"] != _sha(source) or report["source_epoch"] != prior.EPOCH):
            _fail()
        tree = _delivery_tree(source)
        assignments = {node.targets[0].id: node for node in tree.body if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
        config = json.loads(assignments["CONFIG_JSON"].value.value)
        if config["schema"] != "tpr-native-parent-cache-config-v5" or config["source_epoch"] != prior.EPOCH:
            _fail()
        config["schema"], config["source_epoch"] = CONFIG_SCHEMA, EPOCH
        config_raw = _wire(config)
        assignments["SOURCE_EPOCH"].value = ast.Constant(EPOCH)
        assignments["CONFIG_JSON"].value = ast.Constant(config_raw.decode("ascii"))
        assignments["CONFIG_SHA256"].value = ast.Constant(_sha(config_raw))
        helper = assignments["PARENT_HELPER_SOURCE"]
        if not isinstance(helper.value, ast.Constant) or helper.value.value.encode("utf-8") != helper_source:
            _fail()
        position = tree.body.index(helper)
        packed = ast.parse(PACKED_PREFIX.replace("__ENCODED_LITERAL__", repr(PUBLIC_HELPER_B64))).body
        tree.body[position:position+1] = packed
        rendered = _compact(ast.unparse(ast.fix_missing_locations(tree))).encode("utf-8")
        if not 0 < len(rendered) <= MAX_SOURCE_BYTES:
            _fail()
        compile(ast.parse(rendered), "main.py", "exec")
        report.update(schema=BUILD_SCHEMA, source_epoch=EPOCH, main_bytes=len(rendered),
            main_sha256=_sha(rendered), config_sha256=_sha(config_raw), prior_builder_sha256=PRIOR_SHA256,
            public_helper_encoding=PUBLIC_HELPER_ENCODING, public_helper_plain_bytes=PUBLIC_HELPER_PLAIN_BYTES,
            public_helper_plain_sha256=HELPER_SHA256, public_helper_encoded_bytes=len(PUBLIC_HELPER_B64),
            delivery_cell_fields=list(CELL_FIELDS), delivery_callback_fields=["before_close_attempt", "after_close_attempt"],
            delivery_max_rows_per_callback=2, delivery_event_counts_only=True,
            delivery_zero_requires_complete=True, delivery_native_slice_endpoint_samples_max=24000,
            diagnostic_exception="non_order_native_parent_cache_and_delivery_metadata_only",
            public_helper_bytes_preserved=True, significant_tokens_preserved=True)
        return rendered, _wire(report)+b"\n"
    except (ValueError, TypeError, KeyError, IndexError, StopIteration, SyntaxError, UnicodeError, tokenize.TokenError):
        _fail()


def build_cache_probe(*, parent_probe_config_json, helper_source, operation_id, git_head):
    """Same exact parent input API; no SID, helper decoder or source override."""
    raw, report = prior.build_cache_probe(parent_probe_config_json=parent_probe_config_json,
        helper_source=helper_source, operation_id=operation_id, git_head=git_head)
    return _finish(raw, report, helper_source)


def _build_fixture(*, helper_source, operation_id, git_head, case="valid"):
    raw, report = prior._build_fixture(helper_source=helper_source, operation_id=operation_id,
        git_head=git_head, case=case)
    return _finish(raw, report, helper_source)
