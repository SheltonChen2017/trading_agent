"""Pure successor for fixed plain-datetime post-gap History endpoints.

The prior diagnostic and every native custody/clock/history predicate remain
unchanged. Only the request end constructor changes from a native-clock
replace() result to the exact already-frozen plain datetime. This does not
attest the deployed clock class, restore any mark, or grant native access.
"""
from __future__ import annotations

import ast
import hashlib
import json

from . import comparison_20261028_mark_probe_post_gap as prior

POST_GAP_SHA256 = 'bf9c69322c9fb505174908d5acd2fb4ef9ce63f458f5fcb85fea4038f77e84de'
CONSTRUCTION = 'fixed_plain_datetime_request_end_v1'


class NativeEndpointProbeRefusal(ValueError):
    """Body-free refusal for an unproved public source or endpoint edit."""


def _fail():
    raise NativeEndpointProbeRefusal('fixed native endpoint post-gap probe refused') from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_mark_probe_post_gap_native(*, post_gap_source, control_source,
        base_probe_source, helper_source, producer_source, operation_id, git_head):
    """Return plaintext main/report bytes; no file/private/native effect exists."""
    if type(post_gap_source) is not bytes or _sha(post_gap_source) != POST_GAP_SHA256:
        _fail()
    try:
        raw, report_raw = prior.build_mark_probe_post_gap(control_source=control_source,
            base_probe_source=base_probe_source, helper_source=helper_source,
            producer_source=producer_source, operation_id=operation_id, git_head=git_head)
        source = raw.decode('utf-8')
        tree = ast.parse(source)
        mains = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Main']
        if len(mains) != 1:
            _fail()
        probes = [node for node in mains[0].body if isinstance(node, ast.FunctionDef) and node.name == '_probe']
        if len(probes) != 1:
            _fail()
        assignments = [node for node in ast.walk(probes[0]) if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'end']
        expected = ast.parse('end=self.time.replace(tzinfo=None)').body[0]
        if len(assignments) != 1 or ast.dump(assignments[0], include_attributes=False) != ast.dump(expected, include_attributes=False):
            _fail()
        # Keep _history's exact-type/range predicate and _bound's genuine local
        # and UTC clock checks intact. A caller-supplied native marker is absent.
        source = prior.control._replace_node(source, assignments[0].value, 'datetime(2021,2,12,16,1)')
        source = prior.control._replace_once(source,
            "'schema':'tpr-cmp28-native-mark-probe-post-gap-result-v1'",
            "'schema':'tpr-cmp28-native-mark-probe-post-gap-native-result-v1'")
        nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'PROBE_CONFIG_JSON']
        if len(nodes) != 1:
            _fail()
        config = json.loads(ast.literal_eval(nodes[0].value))
        config.update(schema='tpr-cmp28-native-mark-probe-post-gap-native-config-v1',
            predecessor_post_gap_source_sha256=POST_GAP_SHA256,
            request_endpoint_construction=CONSTRUCTION,
            native_clock_class_attested=False, financial_recovery_proven=False)
        config_raw = json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
            allow_nan=False).encode('ascii')
        digest = _sha(config_raw)
        source = prior.control._assignment(source, 'PROBE_CONFIG_JSON', repr(config_raw.decode('ascii')))
        source = prior.control._assignment(source, 'PROBE_CONFIG_SHA256', repr(digest)).encode('utf-8')
        if not 0 < len(source) <= 60000:
            _fail()
        compile(ast.parse(source), 'main.py', 'exec')
        report = json.loads(report_raw)
        report.update(schema='tpr-cmp28-mark-probe-post-gap-native-build-v1',
            predecessor_post_gap_source_sha256=POST_GAP_SHA256,
            request_endpoint_construction=CONSTRUCTION,
            public_source_sha256={
                'comparison_20261028_mark_probe_post_gap.py':POST_GAP_SHA256,
                'comparison_20261028_mark_probe_control.py':_sha(control_source),
                'comparison_20261028_mark_probe.py':_sha(base_probe_source),
                'comparison_20261028_mark_read.py':_sha(helper_source),
                'comparison_20261028_algorithm.py':_sha(producer_source)},
            config_sha256=digest, main_sha256=_sha(source), main_bytes=len(source),
            native_clock_class_attested=False, request_construction_correction_only=True,
            additional_source_edits=report['additional_source_edits'] + [
                'Main._probe_exact_plain_datetime_request_end', 'distinct_successor_config_and_result_schema'])
    except (prior.PostGapProbeRefusal, ValueError, TypeError, SyntaxError, UnicodeError, StopIteration):
        _fail()
    return source, (json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False) + '\n').encode('ascii')
