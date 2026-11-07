"""Pure readable split-module delivery census; no private input or native effect.

The complete verified delivery sensor and v5 parent/cache guards are reused.
Only the public helper representation changes: a fixed constant-only plaintext
module supplies identical public bytes to the original checksum-before-exec
validator namespace. Project source proofs do not attest import-loader origin.
"""
from __future__ import annotations

import ast
import hashlib
import json
import tokenize

from . import native_cache_delivery_probe_20261107 as delivery

prior = delivery.prior
MODULE = "research/target_price_revisions_qc/native_cache_delivery_plain_probe_20261107.py"
EPOCH = "TPR-NATIVE-PARENT-DELIVERY-PLAIN-20261107-v1"
PROJECT_ID, TARGET_SID_SHA256, SESSIONS = prior.PROJECT_ID, prior.TARGET_SID_SHA256, prior.SESSIONS
reader, base = prior.reader, prior.base
HELPER_SHA256 = prior.HELPER_SHA256
HELPER_FILENAME = "tpr_public_parent_source_20261107.py"
HELPER_MODULE_BYTES = 17368
HELPER_MODULE_SHA256 = "8ab9c6dd9bbeb57c4e29dc88f4b0131046cba15a90899ddc44382ed73e13a98a"
PUBLIC_HELPER_PLAIN_BYTES = 17338
PUBLIC_HELPER_REPRESENTATION = "readable_plaintext_constant_module_v1"
MAX_SOURCE_BYTES = 60000
DELIVERY_SHA256 = "2b6f1225c1e7296f79db831d464a1fbabaa4bfccf80eaaf5267dd35eba3cc6d8"
REQUIRED_SOURCES = delivery.REQUIRED_SOURCES | frozenset((MODULE,))
PINNED = {delivery.MODULE: DELIVERY_SHA256, **delivery.PINNED}
FLAGS = prior.FLAGS
ParentCacheRefusal = prior.ParentCacheRefusal
_fail, _wire, _fixture_parent = prior._fail, prior._wire, prior._fixture_parent
_compact, _tokens = delivery._compact, delivery._tokens
CONFIG_SCHEMA = "tpr-native-delivery-plain-cache-config-v1"
BUILD_SCHEMA = "tpr-native-delivery-plain-cache-build-v1"
OBSERVATION_SCHEMA = "tpr-native-delivery-plain-cache-observations-v1"
CELL_FIELDS = delivery.CELL_FIELDS


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def helper_module_source(helper_source):
    """Emit one fixed assignment with every exact public helper line visible."""
    try:
        if (type(helper_source) is not bytes or len(helper_source) != PUBLIC_HELPER_PLAIN_BYTES
                or _sha(helper_source) != HELPER_SHA256 or not helper_source.isascii()
                or any(token in helper_source for token in (b"\\", b"'''", b"\r", b"\x00"))
                or not helper_source.endswith(b"\n")):
            _fail()
        raw = b"PUBLIC_PARENT_SOURCE = '''" + helper_source + b"'''\n"
        if not 0 < len(raw) <= MAX_SOURCE_BYTES or len(raw) != HELPER_MODULE_BYTES or _sha(raw) != HELPER_MODULE_SHA256:
            _fail()
        tree = ast.parse(raw.decode("utf-8"))
        if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign)
                or len(tree.body[0].targets) != 1
                or not isinstance(tree.body[0].targets[0], ast.Name)
                or tree.body[0].targets[0].id != "PUBLIC_PARENT_SOURCE"
                or not isinstance(tree.body[0].value, ast.Constant)
                or type(tree.body[0].value.value) is not str
                or tree.body[0].value.value.encode("utf-8") != helper_source):
            _fail()
        compile(tree, HELPER_FILENAME, "exec")
        return raw
    except (ValueError, TypeError, SyntaxError, UnicodeError):
        _fail()


helper_module_bytes = helper_module_source


def _finish(source, report_raw, helper_source):
    try:
        helper_module = helper_module_source(helper_source)
        if type(source) is not bytes or type(report_raw) is not bytes:
            _fail()
        report = json.loads(report_raw)
        if (report["schema"] != "tpr-native-parent-cache-build-v5" or report["main_bytes"] != len(source)
                or report["main_sha256"] != _sha(source) or report["source_epoch"] != prior.EPOCH):
            _fail()
        tree = delivery._delivery_tree(source)
        schemas = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)
            and node.value == delivery.OBSERVATION_SCHEMA]
        if len(schemas) != 1:
            _fail()
        schemas[0].value = OBSERVATION_SCHEMA
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
        # A built-in str and bounded length are proved before calling encode.
        # The original SHA-before-compile/exec check follows unchanged.
        imported = ast.parse("""
from tpr_public_parent_source_20261107 import PUBLIC_PARENT_SOURCE as PARENT_HELPER_SOURCE
if (type(PARENT_HELPER_SOURCE) is not str or len(PARENT_HELPER_SOURCE) != 17338
        or len(PARENT_HELPER_SOURCE.encode("utf-8")) != 17338):
    raise ValueError("fixed parent helper refused")
""").body
        tree.body[position:position+1] = imported
        rendered = _compact(ast.unparse(ast.fix_missing_locations(tree))).encode("utf-8")
        if not 0 < len(rendered) <= MAX_SOURCE_BYTES:
            _fail()
        compile(ast.parse(rendered), "main.py", "exec")
        report.update(schema=BUILD_SCHEMA, source_epoch=EPOCH, main_bytes=len(rendered),
            main_sha256=_sha(rendered), config_sha256=_sha(config_raw),
            prior_builder_sha256=PINNED[prior.MODULE], delivery_builder_sha256=DELIVERY_SHA256,
            public_helper_representation=PUBLIC_HELPER_REPRESENTATION,
            public_helper_plain_bytes=PUBLIC_HELPER_PLAIN_BYTES, public_helper_plain_sha256=HELPER_SHA256,
            public_helper_module_filename=HELPER_FILENAME, public_helper_module_bytes=len(helper_module),
            public_helper_module_sha256=_sha(helper_module),
            delivery_cell_fields=list(CELL_FIELDS), delivery_callback_fields=["before_close_attempt", "after_close_attempt"],
            delivery_max_rows_per_callback=2, delivery_event_counts_only=True,
            delivery_zero_requires_complete=True, delivery_native_slice_endpoint_samples_max=24000,
            diagnostic_exception="non_order_native_parent_cache_and_delivery_metadata_only",
            public_helper_bytes_preserved=True, significant_tokens_preserved=True,
            import_loader_origin_attested=False, source_import_atomicity_attested=False)
        return rendered, _wire(report)+b"\n"
    except (ValueError, TypeError, KeyError, IndexError, StopIteration, SyntaxError, UnicodeError, tokenize.TokenError):
        _fail()


def build_cache_probe(*, parent_probe_config_json, helper_source, operation_id, git_head):
    """Keep the exact parent input API; no helper filename or source override."""
    raw, report = prior.build_cache_probe(parent_probe_config_json=parent_probe_config_json,
        helper_source=helper_source, operation_id=operation_id, git_head=git_head)
    return _finish(raw, report, helper_source)


def _build_fixture(*, helper_source, operation_id, git_head, case="valid"):
    raw, report = prior._build_fixture(helper_source=helper_source, operation_id=operation_id,
        git_head=git_head, case=case)
    return _finish(raw, report, helper_source)
