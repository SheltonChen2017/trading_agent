"""Pure bounded raw-part framing for the exact plaintext delivery diagnostic.

Only epoch identities and the final emission change. The complete report is
never pruned; reassembly returns an unadmitted object for independent review.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import tokenize

from . import native_cache_delivery_plain_probe_20261107 as plain

prior, delivery, base, reader = plain.prior, plain.delivery, plain.base, plain.reader
MODULE = "research/target_price_revisions_qc/native_cache_delivery_chunked_probe_20261107.py"
EPOCH = "TPR-NATIVE-PARENT-DELIVERY-CHUNKED-20261107-v1"
CONFIG_SCHEMA = "tpr-native-delivery-chunked-cache-config-v1"
BUILD_SCHEMA = "tpr-native-delivery-chunked-cache-build-v1"
OBSERVATION_SCHEMA = "tpr-native-delivery-chunked-cache-observations-v1"
PLAIN_SHA256 = "818304661420287e6b9b3fc900d597a233f83254978e1fd3755cf426e4fdee46"
REQUIRED_SOURCES = plain.REQUIRED_SOURCES | frozenset((MODULE,))
PINNED = {plain.MODULE: PLAIN_SHA256, **plain.PINNED}
PROJECT_ID, TARGET_SID_SHA256, SESSIONS = plain.PROJECT_ID, plain.TARGET_SID_SHA256, plain.SESSIONS
FLAGS, CELL_FIELDS = plain.FLAGS, plain.CELL_FIELDS
HELPER_FILENAME, HELPER_SHA256 = plain.HELPER_FILENAME, plain.HELPER_SHA256
HELPER_MODULE_BYTES, HELPER_MODULE_SHA256 = plain.HELPER_MODULE_BYTES, plain.HELPER_MODULE_SHA256
PUBLIC_HELPER_PLAIN_BYTES, PUBLIC_HELPER_REPRESENTATION = plain.PUBLIC_HELPER_PLAIN_BYTES, plain.PUBLIC_HELPER_REPRESENTATION
helper_module_source, helper_module_bytes = plain.helper_module_source, plain.helper_module_bytes
ParentCacheRefusal, _fail = plain.ParentCacheRefusal, plain._fail
_wire, _fixture_parent, _compact, _tokens = plain._wire, plain._fixture_parent, plain._compact, plain._tokens
MAX_SOURCE_BYTES = 60000
OLD_REPORT_BYTES, MAX_REPORT_BYTES, PART_BYTES, MAX_PARTS = 16384, 9000, 3000, 3
MAX_PREFIX_BYTES, MAX_DEPTH, MAX_NODES = 512, 16, 4096
PART_TAG = "TPR_PARENT_CACHE_PROBE_PART "
REFUSAL_LINE = "TPR_PARENT_CACHE_PROBE_REFUSED output_bound"
ACCEPTANCE_FLAGS = ("financial_acceptance", "delivery_counts_accepted", "economics_accepted",
    "native_origin_independently_attested", "import_origin_attested", "source_import_atomicity_attested",
    "coverage_accepted", "backtesting_ready", "market_trading_authorized")

# All JSON and framed lines exist before the first log call. The old 16,384
# limit remains explicit in addition to the tighter prospective 9,000 limit.
EMISSION = r"""
try:
    wire = json.dumps(self._report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if (type(wire) is not str or not wire.isascii() or not 0 < len(wire) <= 16384 or len(wire) > 9000):
        raise ValueError("diagnostic output bound")
    digest = hashlib.sha256(wire.encode("ascii")).hexdigest()
    pieces = [wire[offset:offset+3000] for offset in range(0, len(wire), 3000)]
    stream = ["TPR_PARENT_CACHE_PROBE_PART "+str(index+1)+"/"+str(len(pieces))+" "+digest+" "+piece
        for index, piece in enumerate(pieces)]
except Exception:
    stream = ["TPR_PARENT_CACHE_PROBE_REFUSED output_bound"]
for line in stream:
    self.log(line)
"""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _finish(source, report_raw):
    try:
        if type(source) is not bytes or type(report_raw) is not bytes:
            _fail()
        report = json.loads(report_raw)
        if (report["schema"] != plain.BUILD_SCHEMA or report["source_epoch"] != plain.EPOCH
                or report["main_bytes"] != len(source) or report["main_sha256"] != _sha(source)):
            _fail()
        tree = ast.parse(source)
        assignments = {node.targets[0].id: node for node in tree.body if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
        config = json.loads(assignments["CONFIG_JSON"].value.value)
        if config["schema"] != plain.CONFIG_SCHEMA or config["source_epoch"] != plain.EPOCH:
            _fail()
        config["schema"], config["source_epoch"] = CONFIG_SCHEMA, EPOCH
        config_raw = _wire(config)
        assignments["SOURCE_EPOCH"].value = ast.Constant(EPOCH)
        assignments["CONFIG_JSON"].value = ast.Constant(config_raw.decode("ascii"))
        assignments["CONFIG_SHA256"].value = ast.Constant(_sha(config_raw))
        schemas = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)
            and node.value == plain.OBSERVATION_SCHEMA]
        if len(schemas) != 1:
            _fail()
        schemas[0].value = OBSERVATION_SCHEMA
        main = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Main")
        end = delivery._function(main, "on_end_of_algorithm")
        if (len(end.body) < 2 or not isinstance(end.body[-2], ast.Assign)
                or ast.unparse(end.body[-2].targets[0]) != "wire"
                or not isinstance(end.body[-1], ast.If)
                or ast.unparse(end.body[-1].test) != "len(wire) <= 16384"
                or ast.unparse(end.body[-1].body[0])
                    != "self.log('TPR_PARENT_CACHE_PROBE_RESULT ' + wire)"):
            _fail()
        end.body[-2:] = ast.parse(EMISSION).body
        rendered = _compact(ast.unparse(ast.fix_missing_locations(tree))).encode("utf-8")
        if not 0 < len(rendered) <= MAX_SOURCE_BYTES:
            _fail()
        compile(ast.parse(rendered), "main.py", "exec")
        report.update(schema=BUILD_SCHEMA, source_epoch=EPOCH, main_bytes=len(rendered),
            main_sha256=_sha(rendered), config_sha256=_sha(config_raw), plain_builder_sha256=PLAIN_SHA256,
            report_old_max_bytes=OLD_REPORT_BYTES, report_max_bytes=MAX_REPORT_BYTES,
            report_part_max_bytes=PART_BYTES, report_parts_max=MAX_PARTS,
            report_part_tag=PART_TAG, report_parts_raw_contiguous_ascii=True,
            report_whole_sha256_before_emission=True, report_stream_precomputed=True,
            report_pruning_authorized=False)
        return rendered, _wire(report)+b"\n"
    except (ValueError, TypeError, KeyError, IndexError, StopIteration, SyntaxError, UnicodeError, tokenize.TokenError):
        _fail()


def build_cache_probe(*, parent_probe_config_json, helper_source, operation_id, git_head):
    raw, report = plain.build_cache_probe(parent_probe_config_json=parent_probe_config_json,
        helper_source=helper_source, operation_id=operation_id, git_head=git_head)
    return _finish(raw, report)


def _build_fixture(*, helper_source, operation_id, git_head, case="valid"):
    raw, report = plain._build_fixture(helper_source=helper_source, operation_id=operation_id,
        git_head=git_head, case=case)
    return _finish(raw, report)


def reassemble_report(lines, *, expected_operation_id, expected_head, expected_job_id):
    """Strict framing/header gate; a returned report has no count acceptance."""
    try:
        if (type(lines) not in (list, tuple) or not 1 <= len(lines) <= MAX_PARTS
                or type(expected_operation_id) is not str
                or re.fullmatch(r"TPR-CACHE-20261104-[A-Z0-9-]{1,40}", expected_operation_id) is None
                or type(expected_head) is not str or re.fullmatch(r"[a-f0-9]{40}", expected_head) is None
                or type(expected_job_id) is not str or re.fullmatch(r"[a-f0-9]{32}", expected_job_id) is None):
            _fail()
        pieces, digest, total_bytes = [], None, 0
        for index, line in enumerate(lines, 1):
            if (type(line) is not str or not line.isascii()
                    or len(line) > MAX_PREFIX_BYTES+len(PART_TAG)+3+1+64+1+PART_BYTES
                    or line.count(PART_TAG) != 1 or "\n" in line or "\r" in line):
                _fail()
            prefix, payload = line.split(PART_TAG, 1)
            if len(prefix) > MAX_PREFIX_BYTES or any(ord(char) < 32 or ord(char) > 126 for char in prefix):
                _fail()
            frame = re.fullmatch(r"([1-3])/([1-3]) ([a-f0-9]{64}) (.+)", payload)
            if frame is None:
                _fail()
            number, total, found_digest, piece = frame.groups()
            if (int(number) != index or int(total) != len(lines)
                    or not 0 < len(piece) <= PART_BYTES or any(ord(char) < 32 or ord(char) > 126 for char in piece)
                    or digest is not None and found_digest != digest):
                _fail()
            total_bytes += len(piece)
            if total_bytes > MAX_REPORT_BYTES:
                _fail()
            pieces.append(piece)
            digest = found_digest
        raw = "".join(pieces).encode("ascii")
        if _sha(raw) != digest:
            _fail()
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    _fail()
                result[key] = value
            return result
        def integer(token):
            if len(token) > 1000:
                _fail()
            return int(token)
        value = json.loads(raw, object_pairs_hook=pairs, parse_int=integer,
            parse_float=lambda _: _fail(), parse_constant=lambda _: _fail())
        nodes = 0
        def walk(item, depth=0):
            nonlocal nodes
            nodes += 1
            if nodes > MAX_NODES or depth > MAX_DEPTH:
                _fail()
            if type(item) is dict:
                for key, child in item.items():
                    walk(key, depth+1)
                    walk(child, depth+1)
            elif type(item) is list:
                for child in item:
                    walk(child, depth+1)
            elif type(item) is str:
                item.encode("utf-8", errors="strict")
            elif item is not None and type(item) not in (bool, int):
                _fail()
        walk(value)
        if type(value) is not dict:
            _fail()
        headers = {"schema": OBSERVATION_SCHEMA, "source_epoch": EPOCH,
            "operation_id": expected_operation_id, "root_head": expected_head, "actual_job_id": expected_job_id}
        if (any(type(value.get(key)) is not str or value[key] != bound for key, bound in headers.items())
                or any(value.get(flag) is not False for flag in FLAGS)
                or any(flag in value and value[flag] is not False for flag in ACCEPTANCE_FLAGS)):
            _fail()
        return {"schema": "tpr-native-delivery-chunked-reassembly-v1", "report": value,
            "whole_report_bytes": len(raw), "whole_report_sha256": digest, "parts": len(lines),
            "framing_complete": True, "strict_json_complete": True, "native_bindings_matched": True,
            "report_structure_independently_validated": False, "financial_metrics": None,
            **{flag: False for flag in ACCEPTANCE_FLAGS}}
    except Exception:
        _fail()
