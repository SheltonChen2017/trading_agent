"""Additive offline metadata qualification of two retained, unsealed bodies.

This does not repair either original acquisition, attest its HTTP status, or
admit source/PIT/rights evidence. Numeric JSON lexemes become opaque markers;
only date/code/timing/status/quarantine metadata is published privately. All
production access is confined to fixed retained inputs and a fresh output.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from research import insider_buying_earnings_archive_assessment_runner as custody
from research import insider_buying_eodhd_earnings_continuation3 as third
from research import insider_buying_eodhd_earnings_continuation4 as fourth
from research import insider_buying_sharadar_reference_cohort_runner as publication
from research.insider_buying_eodhd_earnings_demo import EodhdDemoError, FALSE_FLAGS, _read_leaf


LANE_ROOT = custody.LANE_ROOT
LANE_BRANCH = custody.LANE_BRANCH
SCHEMA = "insider-retained-unsealed-earnings-supplement-v1"
METADATA_SCHEMA = "insider-retained-unsealed-earnings-metadata-v1"
AUDIT_ID = "ib-earnings-retained-supplement-201902-202002-20261024-once"
OUTPUT_PARTS = ("artifacts", "insider_buying", "earnings_retained_supplement_v1")
PRIOR_PARTS = ("artifacts", "insider_buying", "earnings_archive_assessment",
               "ib-earnings-assessment-dual-partial-2006q1-20261014-once")
MODULE_PATH = "research/insider_buying_retained_earnings_supplement.py"
MAX_CONTROL = 4 * 1024 * 1024
MAX_METADATA = 256 * 1024 * 1024
TIMEOUT_SECONDS = 600
EMPTY_CACHE_PREFIX = "/var/empty/insider-retained-supplement-no-bytecode"
WORKER_FLAGS = ("-I", "-S", "-B", "-X", "pycache_prefix=" + EMPTY_CACHE_PREFIX)
_SUMMARY_FIELDS = frozenset({"schema", "audit_id", "fixture_only", "qualified_at_utc",
    "execution_identity", "windows", "prior_completion_sha256", "witness3_sha256", "witness4_sha256",
    "input_sha256", "input_inventory_sha256", "published_leaf_sha256", "isolation", "provider_dispatches",
    "credential_reads", "looks_jobs_backtests", "producer_roots_repaired", "producer_http_status",
    "producer_window_seals_present", "producer_aggregate_completions_present",
    "raw_json_structurally_reprojected", "financial_numeric_values_interpreted",
    "current_offline_metadata_qualification", *FALSE_FLAGS})
_RESULT_FIELDS = frozenset({"schema", "audit_id", "fixture_only", "complete_sha256", "qualified_windows",
    "counts", "looks_jobs_backtests", *FALSE_FLAGS})


class RetainedSupplementError(ValueError):
    """Fixed sanitized refusal, never input paths, values or exception text."""


def _need(condition, code):
    if not condition:
        raise RetainedSupplementError(code)


@dataclass(frozen=True, slots=True)
class WindowAnchor:
    generation: int
    index: int
    window: tuple[str, str]
    manifest_sha256: str
    start_sha256: str
    scope_sha256: str
    body_sha256: str
    body_bytes: int
    metadata_sha256: str
    metadata_bytes: int


@dataclass(frozen=True, slots=True)
class SupplementAnchors:
    witness3_sha256: str
    witness4_sha256: str
    prior_completion_sha256: str
    prior_completion_bytes: int
    windows: tuple[WindowAnchor, WindowAnchor]


ACTUAL_ANCHORS = SupplementAnchors(
    custody.PARTIAL_WITNESS_SHA256, custody.PARTIAL4_WITNESS_SHA256,
    "8a67f1d629bf1e354e8f8ade8d71cd6a00f98cc66935bdc12f3d1917ae2419b5", 273898,
    (
        WindowAnchor(3, 5, ("2019-02-01", "2019-02-28"),
            "0b2f211f9c7d97b71ad01c6c8f7479ba7db31d67ba21ecc410645db62bb10990",
            "5cdc509c2fb977b79e9b251dfc9fcd3aa645f2b61903d8f86f9898e9b131c47d",
            "8db7cc71a2861e5e0b331861b2ed22484a5514cae8f2e28704ec40bcf0e3aeed",
            "8a3f15c766d83769a6da62cddbf38755fb3bfcf2e2414a16e2a0f8d758c88d5d", 3373434,
            "01b0c3cc5217e88630f8049808ae29e06f412e4ed7f085b26496f20ebd3e4c5e", 4488962),
        WindowAnchor(4, 11, ("2020-02-01", "2020-02-29"),
            "da91c236bf2c7a5b609fb2b467c6dd0cdb2ac03b0d0334e40319a3d0b2883eed",
            "d3bfb23735f2dc0ebf3ff212db9a02e88b349ce5f0ed076711653b1b87094bbd",
            "e4ac0096c00e1f73d9a37bfe3594f269fd83028c8ab8a0afeadf70a1dee36744",
            "329ebf5ef942f52a9a715d77d0a1b8fec5f26a651e0becba0d5afe86319677f8", 3494159,
            "be2b411c72646a7918453ab935ec37347671788fe5f7c64513856a1940f1fdf3", 4640120),
    ))


def _canonical(value):
    return custody._canonical(value)


def _sha(raw):
    return custody._sha(raw)


def _json(raw):
    return custody._json(raw)


def _zero_looks(value):
    return type(value) is list and len(value) == 3 and all(type(item) is int and item == 0 for item in value)


def _anchor_check(anchors, fixture_only):
    _need(type(anchors) is SupplementAnchors and type(fixture_only) is bool,
          "explicit_anchor_scope_required")
    _need(fixture_only or anchors == ACTUAL_ANCHORS, "actual_anchor_scope_refused")
    _need(type(anchors.windows) is tuple and len(anchors.windows) == 2,
          "exact_two_window_scope_required")
    for item, expected in zip(anchors.windows, ACTUAL_ANCHORS.windows):
        _need(type(item) is WindowAnchor and (item.generation, item.index, item.window)
              == (expected.generation, expected.index, expected.window), "fixed_window_scope_refused")
        for name in ("manifest_sha256", "start_sha256", "scope_sha256", "body_sha256", "metadata_sha256"):
            custody._digest(getattr(item, name))
        _need(type(item.body_bytes) is int and 0 < item.body_bytes <= third.MAX_BODY_BYTES
              and type(item.metadata_bytes) is int and 0 < item.metadata_bytes <= MAX_METADATA,
              "bounded_window_sizes_required")
    for digest in (anchors.witness3_sha256, anchors.witness4_sha256, anchors.prior_completion_sha256):
        custody._digest(digest)
    _need(type(anchors.prior_completion_bytes) is int
          and 0 < anchors.prior_completion_bytes <= MAX_CONTROL, "bounded_prior_completion_required")


def _where(item):
    parts, identity = ((custody.V3_PARTS, custody.V3_ID) if item.generation == 3
                       else (custody.V4_PARTS, custody.V4_ID))
    return (*parts, "campaigns", identity), f"window-{item.index:04d}"


def _owned_chain(chain):
    _need(all(not private or os.fstat(fd).st_uid == os.geteuid()
              for _, _, fd, private in chain.links), "private_directory_owner_refused")


def _owned_inputs(inputs):
    for chain in inputs.chains:
        _owned_chain(chain)
    _need(all(os.stat(name, dir_fd=chain.fd, follow_symlinks=False).st_uid == os.geteuid()
              for chain, name, _, _, _ in inputs.leaves), "private_input_owner_refused")


def _held_raw(inputs, parts, name, expected, size, limit):
    """Read a leaf already inventoried/held by the original custody loader."""
    relative = "/".join((*parts, name))
    _need(inputs.hashes.get(relative) == expected, "preexisting_leaf_anchor_required")
    inputs.recheck(); _owned_inputs(inputs)
    chain = inputs.named_chains[tuple(parts)]
    before = custody._version(os.stat(name, dir_fd=chain.fd, follow_symlinks=False))
    raw = _read_leaf(chain.fd, name, limit=limit)
    _need(custody._version(os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) == before
          and len(raw) == size and _sha(raw) == expected, "retained_leaf_binding_refused")
    inputs.recheck(); _owned_inputs(inputs)
    return raw


def _load_inputs(root, anchors, fixture_only):
    _anchor_check(anchors, fixture_only)
    inputs = custody._Inputs(root)
    try:
        custody._load_partial_campaign(inputs, anchors.witness3_sha256,
                                      fixture_only=fixture_only, generation=3)
        custody._load_partial_campaign(inputs, anchors.witness4_sha256,
                                      fixture_only=fixture_only, generation=4)
        prior = inputs.directory(PRIOR_PARTS)
        inputs.inventory(prior, {"assessment.json", "complete.json"})
        raw = inputs.read(prior, PRIOR_PARTS, "complete.json", limit=MAX_CONTROL,
                          expected=anchors.prior_completion_sha256)
        body = _json(raw)
        _need(len(raw) == anchors.prior_completion_bytes and body.get("schema") == custody.SCHEMA
              and body.get("fixture_only") is fixture_only
              and body.get("expected_partial_witness_sha256") == anchors.witness3_sha256
              and body.get("expected_partial4_witness_sha256") == anchors.witness4_sha256
              and type(body.get("input_sha256")) is dict
              and _zero_looks(body.get("looks_jobs_backtests"))
              and body.get("raw_financial_bodies_decoded") is False
              and all(body.get(flag) is False for flag in FALSE_FLAGS),
              "prior_completion_binding_refused")
        if not fixture_only:
            _need(body.get("unavailable_window_count") == 4
                  and body.get("counts", {}).get("source_metadata_rows") == 2358204,
                  "prior_actual_coverage_binding_refused")
        for item in anchors.windows:
            parts, prefix = _where(item)
            source = inputs.named_chains[parts]
            _need(not os.path.lexists(root.joinpath(*parts, prefix + "-complete.json"))
                  and "complete.json" not in os.listdir(source.fd), "original_seal_must_remain_absent")
            for name, digest in (("manifest.json", item.manifest_sha256),
                    (prefix + "-started.json", item.start_sha256),
                    (prefix + "-response.json", item.body_sha256),
                    (prefix + "-metadata.json", item.metadata_sha256)):
                relative = "/".join((*parts, name))
                _need(inputs.hashes.get(relative) == digest
                      and body["input_sha256"].get(relative) == digest,
                      "prior_selected_input_binding_refused")
            start_raw = _read_leaf(source.fd, prefix + "-started.json", limit=MAX_CONTROL)
            start = _json(start_raw)
            _need(start.get("index") == item.index and start.get("window") == list(item.window)
                  and start.get("manifest_sha256") == item.manifest_sha256
                  and start.get("scope_reservation_sha256") == item.scope_sha256
                  and type(start.get("maximum_attempts")) is int and start["maximum_attempts"] == 1,
                  "selected_start_binding_refused")
        inputs.recheck(); _owned_inputs(inputs)
        return inputs
    except BaseException:
        inputs.close()
        raise


def _counts(rows, window):
    _need(type(rows) is list and len(rows) <= third.MAX_ROWS, "projected_row_bound_refused")
    accepted = reported = unknown = missing_timing = 0
    reasons = Counter()
    fields = {"source_row_ordinal", "metadata_accepted", "quarantine_reasons", "code",
              "report_date", "fiscal_date", "before_after_market", "current_provider_reported_status"}
    for ordinal, row in enumerate(rows):
        _need(type(row) is dict and set(row) == fields and type(row["source_row_ordinal"]) is int
              and row["source_row_ordinal"] == ordinal and type(row["metadata_accepted"]) is bool
              and type(row["quarantine_reasons"]) is list, "projected_row_schema_refused")
        row_reasons = row["quarantine_reasons"]
        _need(all(type(value) is str and value in custody.assessment.QUARANTINE_REASONS for value in row_reasons)
              and len(row_reasons) == len(set(row_reasons))
              and row["metadata_accepted"] == (not row_reasons), "quarantine_accounting_refused")
        nonobject = "source_row_not_object" in row_reasons
        code = row["code"]
        _need(type(code) is str and custody.assessment._CODE.fullmatch(code)
              or code is None and (nonobject or "source_code_unknown" in row_reasons),
              "projected_code_refused")
        days = []
        for name in ("report_date", "fiscal_date"):
            value = row[name]
            if value is None:
                _need(nonobject or "source_" + name + "_unknown" in row_reasons,
                      "projected_date_reason_refused")
                days.append(None)
            else:
                days.append(custody.assessment._day(value))
        report, fiscal = days
        _need(report is None or custody.assessment._day(window[0]) <= report <= custody.assessment._day(window[1])
              or "report_date_outside_registered_scope" in row_reasons, "projected_scope_refused")
        _need(report is None or fiscal is None or fiscal <= report
              or "fiscal_date_after_report_date" in row_reasons, "projected_period_refused")
        timing, status = row["before_after_market"], row["current_provider_reported_status"]
        _need((timing is None or type(timing) is str and timing in {"BeforeMarket", "AfterMarket"})
              and (timing is not None or nonobject or "source_timing_unknown" in row_reasons),
              "projected_timing_refused")
        _need(type(status) is str and status in {"reported", "unknown"}
              and (status != "unknown" or nonobject or "current_provider_reported_status_unknown" in row_reasons),
              "projected_status_refused")
        accepted += row["metadata_accepted"]
        reported += status == "reported"
        unknown += status == "unknown"
        missing_timing += timing is None
        reasons.update(row_reasons)
    return {"source_metadata_rows": len(rows), "metadata_accepted_rows": accepted,
            "quarantined_metadata_rows": len(rows) - accepted, "reported_rows": reported,
            "unknown_status_rows": unknown, "timing_unknown_rows": missing_timing,
            "quarantine_reason_counts": dict(sorted(reasons.items()))}


def _metadata_from_retained(inputs, item, fixture_only):
    """Validate metadata only; safe for the trusted parent's strict readback.

    The parent's custody loader/hash rechecks never JSON-decode the source
    response. Only the native-denied worker calls the separate raw projector.
    """
    parts, prefix = _where(item)
    retained_raw = _held_raw(inputs, parts, prefix + "-metadata.json", item.metadata_sha256,
                             item.metadata_bytes, MAX_METADATA)
    retained = _json(retained_raw)
    expected_schema = third.SCHEMA if item.generation == 3 else fourth.SCHEMA
    _need(set(retained) == {"schema", "body_sha256", "rows", "metadata_acceptance_is_source_coverage_or_identity_admission"}
          and retained["schema"] == expected_schema and retained["body_sha256"] == item.body_sha256
          and retained["metadata_acceptance_is_source_coverage_or_identity_admission"] is False,
          "retained_metadata_schema_refused")
    rows = retained["rows"]
    counts = _counts(rows, item.window)
    return {"schema": METADATA_SCHEMA, "fixture_only": fixture_only, "window": list(item.window),
            "generation": item.generation, "source_body_sha256": item.body_sha256,
            "retained_metadata_sha256": item.metadata_sha256, "counts": counts, "rows": rows,
            "producer_http_status": None, "producer_window_seal_present": False,
            "producer_aggregate_completion_present": False, "raw_json_structurally_reprojected": True,
            "financial_numeric_values_interpreted": False,
            "current_offline_metadata_qualification": True, **{flag: False for flag in FALSE_FLAGS}}


def _qualify(inputs, item, fixture_only):
    """Structural raw reprojection; production calls only in denied worker."""
    _need(type(fixture_only) is bool, "explicit_projection_scope_required")
    if fixture_only:
        _need(not custody._fixture_root_is_lane(inputs.root), "fixture_projection_root_refused")
    else:
        # Defense in depth: a future caller cannot move this raw decode into
        # the trusted parent merely by calling the private helper directly.
        custody._effective_denial(require_fork=True)
    parts, prefix = _where(item)
    raw = _held_raw(inputs, parts, prefix + "-response.json", item.body_sha256,
                    item.body_bytes, third.MAX_BODY_BYTES)
    metadata = _metadata_from_retained(inputs, item, fixture_only)
    projector = third._projection if item.generation == 3 else fourth._projection
    rows = projector(raw, item.window, token=None)
    _need(_canonical(rows) == _canonical(metadata["rows"]), "raw_metadata_reprojection_disagreement")
    return metadata


def _identity(expected_head):
    identity = custody._identity(expected_head)
    _need(MODULE_PATH in identity["source_sha256"], "supplement_source_not_in_closure")
    return identity


def _identity_envelope(identity, root, expected_head, fixture_only):
    _need(type(identity) is dict and identity.get("root") == str(root)
          and identity.get("branch") == LANE_BRANCH and identity.get("head") == expected_head
          and identity.get("clean") is True and type(identity.get("source_sha256")) is dict
          and identity["source_sha256"]
          and identity.get("source_inventory_sha256") == _sha(_canonical(identity["source_sha256"])),
          "source_identity_envelope_refused")
    _need(fixture_only or MODULE_PATH in identity["source_sha256"], "supplement_source_not_in_closure")
    _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"],
          "worker_source_inventory_changed")


def _policy(output):
    return ('(version 1)(allow default)(deny network*)(deny process-fork)'
            '(deny process-exec (literal "/usr/bin/security"))(deny file-write*)'
            '(allow file-write* (subpath ' + json.dumps(str(output)) + '))')


def _isolation(root, output, fixture_only):
    custody._effective_denial(require_fork=not fixture_only)
    if not fixture_only:
        try:
            child = os.posix_spawn("/usr/bin/security", ["security", "help"],
                                   {"PATH": "/usr/bin:/bin", "LANG": "C"})
        except OSError as exc:
            _need(exc.errno in {errno.EPERM, errno.EACCES}, "keychain_exec_denial_not_observed")
        else:
            os.waitpid(child, 0)
            raise RetainedSupplementError("keychain_exec_denial_not_observed")
        outside = root.joinpath(*OUTPUT_PARTS, "isolation-" + AUDIT_ID + ".probe")
        try:
            fd = os.open(outside, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            _need(exc.errno in {errno.EPERM, errno.EACCES}, "outside_output_write_denial_not_observed")
        else:
            os.close(fd)
            raise RetainedSupplementError("outside_output_write_denial_not_observed")
    proof = {"schema": SCHEMA, "fixture_only": fixture_only,
             "effective_process_tree_network_denial": True,
             "effective_process_fork_denial": not fixture_only,
             "effective_keychain_exec_denial": not fixture_only,
             "effective_outside_output_write_denial": not fixture_only,
             "fresh_output_write_observed": True}
    custody._write_raw(output.fd, "isolation.json", _canonical(proof))
    return proof


def _metadata_name(item):
    return "window-" + item.window[0][:7].replace("-", "") + "-metadata.json"


def _worker(root, expected_head, identity, anchors, *, fixture_only):
    _identity_envelope(identity, root, expected_head, fixture_only)
    output = custody._Chain(root, (*OUTPUT_PARTS, AUDIT_ID))
    inputs = None
    try:
        _owned_chain(output)
        _need(not os.listdir(output.fd), "fresh_empty_output_required")
        isolation = _isolation(root, output, fixture_only)
        inputs = _load_inputs(root, anchors, fixture_only)
        entries, published = [], {"isolation.json": _sha(_canonical(isolation))}
        for item in anchors.windows:
            metadata = _qualify(inputs, item, fixture_only)
            raw = _canonical(metadata)
            _need(len(raw) <= MAX_METADATA, "supplement_metadata_byte_bound")
            name = _metadata_name(item)
            custody._write_raw(output.fd, name, raw)
            published[name] = _sha(raw)
            entries.append({key: value for key, value in metadata.items() if key != "rows"})
            entries[-1]["metadata_leaf"] = name
            entries[-1]["metadata_sha256"] = _sha(raw)
            inputs.recheck()
        _identity_envelope(identity, root, expected_head, fixture_only)
        summary = {"schema": SCHEMA, "audit_id": AUDIT_ID, "fixture_only": fixture_only,
            "qualified_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "execution_identity": identity, "windows": entries,
            "prior_completion_sha256": anchors.prior_completion_sha256,
            "witness3_sha256": anchors.witness3_sha256, "witness4_sha256": anchors.witness4_sha256,
            "input_sha256": dict(sorted(inputs.hashes.items())),
            "input_inventory_sha256": _sha(_canonical(inputs.hashes)),
            "published_leaf_sha256": published, "isolation": isolation,
            "provider_dispatches": 0, "credential_reads": 0, "looks_jobs_backtests": [0, 0, 0],
            "producer_roots_repaired": False, "producer_http_status": None,
            "producer_window_seals_present": False, "producer_aggregate_completions_present": False,
            "raw_json_structurally_reprojected": True, "financial_numeric_values_interpreted": False,
            "current_offline_metadata_qualification": True, **{flag: False for flag in FALSE_FLAGS}}
        inputs.recheck(); output.recheck()
        complete_raw = _canonical(summary)
        _need(len(complete_raw) <= MAX_CONTROL, "supplement_completion_byte_bound")
        custody._write_raw(output.fd, "complete.json", complete_raw)
        inputs.recheck(); output.recheck()
        _identity_envelope(identity, root, expected_head, fixture_only)
        result = {"schema": SCHEMA, "audit_id": AUDIT_ID, "fixture_only": fixture_only,
                  "complete_sha256": _sha(complete_raw), "qualified_windows": 2,
                  "counts": [entry["counts"] for entry in entries],
                  "looks_jobs_backtests": [0, 0, 0], **{flag: False for flag in FALSE_FLAGS}}
        _verify_publication(root, identity, anchors, result, fixture_only=fixture_only, inputs=inputs)
        return result
    finally:
        if inputs is not None:
            inputs.close()
        output.close()


def _verify_publication(root, identity, anchors, result, *, fixture_only, inputs=None):
    own_inputs = inputs is None
    inputs = _load_inputs(root, anchors, fixture_only) if own_inputs else inputs
    output = None
    try:
        # Only NEW publication leaves settle ctime. All source inputs retain
        # their original strict version policy. Owner/identity/mtime remain
        # held and every output's bytes are rehashed before accepting it.
        output = publication._HeldCapture(root.joinpath(*OUTPUT_PARTS, AUDIT_ID), settle_ctime=True)
        _owned_chain(output.chain)
        names = {"isolation.json", "complete.json", *(_metadata_name(item) for item in anchors.windows)}
        _need(set(os.listdir(output.fd)) == names, "parent_output_inventory_refused")
        _need(all(os.stat(name, dir_fd=output.fd, follow_symlinks=False).st_uid == os.geteuid()
                  for name in names), "private_output_owner_refused")
        def read_output(name, cap):
            stream = output.open(name, cap)
            raw = stream.read(cap + 1)
            _need(0 < len(raw) <= cap, "parent_output_byte_bound_refused")
            output.check()
            return raw
        raw = read_output("complete.json", MAX_CONTROL)
        body = _json(raw)
        _need(type(result) is dict and set(result) == _RESULT_FIELDS and set(body) == _SUMMARY_FIELDS
              and result.get("schema") == body.get("schema") == SCHEMA
              and result.get("audit_id") == body.get("audit_id") == AUDIT_ID
              and result.get("fixture_only") is body.get("fixture_only") is fixture_only
              and result.get("complete_sha256") == _sha(raw)
              and type(result.get("qualified_windows")) is int and result["qualified_windows"] == 2
              and body.get("execution_identity") == identity
              and body.get("prior_completion_sha256") == anchors.prior_completion_sha256
              and body.get("witness3_sha256") == anchors.witness3_sha256
              and body.get("witness4_sha256") == anchors.witness4_sha256
              and body.get("input_sha256") == dict(sorted(inputs.hashes.items()))
              and body.get("input_inventory_sha256") == _sha(_canonical(inputs.hashes)),
              "parent_completion_binding_refused")
        isolation_raw = read_output("isolation.json", MAX_CONTROL)
        isolation = _json(isolation_raw)
        expected_isolation = {"schema": SCHEMA, "fixture_only": fixture_only,
             "effective_process_tree_network_denial": True,
             "effective_process_fork_denial": not fixture_only,
             "effective_keychain_exec_denial": not fixture_only,
             "effective_outside_output_write_denial": not fixture_only,
             "fresh_output_write_observed": True}
        _need(_canonical(isolation) == _canonical(body.get("isolation")) == _canonical(expected_isolation),
              "parent_isolation_binding_refused")
        entries, published = [], {"isolation.json": _sha(isolation_raw)}
        for item in anchors.windows:
            # Never decode financial source JSON in the trusted parent.
            # Raw bodies remain hash/size/identity bound by the held inputs.
            expected = _metadata_from_retained(inputs, item, fixture_only)
            name = _metadata_name(item)
            metadata_raw = read_output(name, MAX_METADATA)
            _need(metadata_raw == _canonical(expected), "parent_metadata_reprojection_binding_refused")
            published[name] = _sha(metadata_raw)
            entry = {key: value for key, value in expected.items() if key != "rows"}
            entry.update(metadata_leaf=name, metadata_sha256=_sha(metadata_raw))
            entries.append(entry)
        _need(_canonical(body.get("windows")) == _canonical(entries)
              and body.get("published_leaf_sha256") == published
              and _canonical(result.get("counts")) == _canonical([entry["counts"] for entry in entries]),
              "parent_window_accounting_refused")
        _need(body.get("producer_http_status") is None
              and all(body.get(key) is False for key in ("producer_roots_repaired", "producer_window_seals_present",
                      "producer_aggregate_completions_present", "financial_numeric_values_interpreted"))
              and body.get("raw_json_structurally_reprojected") is True
              and body.get("current_offline_metadata_qualification") is True
              and type(body.get("provider_dispatches")) is int and body["provider_dispatches"] == 0
              and type(body.get("credential_reads")) is int and body["credential_reads"] == 0
              and _zero_looks(body.get("looks_jobs_backtests")) and _zero_looks(result.get("looks_jobs_backtests"))
              and all(body.get(flag) is False and result.get(flag) is False for flag in FALSE_FLAGS),
              "parent_authority_or_producer_claim_refused")
        custody.assessment._utc(body.get("qualified_at_utc"))
        inputs.recheck(); _owned_inputs(inputs); output.check(); _owned_chain(output.chain)
        _identity_envelope(identity, root, identity["head"], fixture_only)
        expected_hashes = {**published, "complete.json": result["complete_sha256"]}
        for name, stream, _, cap in output.handles:
            _need(publication._hash_stream(stream, cap)[0] == expected_hashes[name],
                  "parent_output_content_changed")
            output.check()
        _need({name for name, _, _, _ in output.handles} == names,
              "parent_output_leaf_hold_incomplete")
        inputs.recheck(); _owned_inputs(inputs); output.check()
    finally:
        if output is not None:
            output.close()
        if own_inputs:
            inputs.close()


def run_fixture(*, root, expected_head, anchors, identity):
    """Invented roots only; no default callback can reach production custody."""
    _need(isinstance(root, Path) and not custody._fixture_root_is_lane(root)
          and root.resolve() == root and callable(identity) and identity is not _identity
          and identity is not custody._identity, "fixture_root_and_identity_required")
    _anchor_check(anchors, True)
    baseline = identity(expected_head)
    _identity_envelope(baseline, root, expected_head, True)
    output = custody._Chain(root, (*OUTPUT_PARTS, AUDIT_ID), create=True, exclusive_last=True)
    output.close()
    return _worker(root, expected_head, baseline, anchors, fixture_only=True)


def run_actual(*, expected_head):
    baseline = _identity(expected_head)
    _identity_envelope(baseline, LANE_ROOT, expected_head, False)
    inputs = _load_inputs(LANE_ROOT, ACTUAL_ANCHORS, False)
    try:
        output = custody._Chain(LANE_ROOT, (*OUTPUT_PARTS, AUDIT_ID), create=True, exclusive_last=True)
        output.close()
        _need(_identity(expected_head) == baseline, "parent_source_identity_changed")
        bootstrap = ("import sys;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");"
                     "from research import insider_buying_retained_earnings_supplement as m;"
                     "raise SystemExit(m.main())")
        command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
                   "/usr/bin/sandbox-exec", "-p", _policy(LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)),
                   sys.executable, *WORKER_FLAGS,
                   "-c", bootstrap, "--worker", "--expected-head", expected_head]
        launched = subprocess.run(command, cwd=LANE_ROOT, input=_canonical(baseline),
                                  capture_output=True, check=False, timeout=TIMEOUT_SECONDS)
        _need(_identity(expected_head) == baseline, "parent_source_identity_changed")
        inputs.recheck()
        _need(launched.returncode == 0 and launched.stderr == b"", "isolated_worker_refused_outputs_preserved")
        stdout = launched.stdout.removesuffix(b"\n")
        result = _json(stdout)
        _verify_publication(LANE_ROOT, baseline, ACTUAL_ANCHORS, result, fixture_only=False, inputs=inputs)
        _need(_identity(expected_head) == baseline, "parent_final_source_identity_changed")
        inputs.recheck()
        return result
    finally:
        inputs.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            _need(Path.cwd() == LANE_ROOT and LANE_ROOT.resolve() == LANE_ROOT, "designated_lane_required")
            _need(sys.flags.isolated == 1 and sys.flags.no_user_site == 1
                  and sys.flags.no_site == 1 and sys.flags.dont_write_bytecode == 1
                  and sys.pycache_prefix == EMPTY_CACHE_PREFIX,
                  "isolated_worker_interpreter_required")
            identity = _json(sys.stdin.buffer.read(MAX_CONTROL + 1))
            result = _worker(LANE_ROOT, args.expected_head, identity, ACTUAL_ANCHORS, fixture_only=False)
        else:
            result = run_actual(expected_head=args.expected_head)
        print(_canonical(result).decode("utf-8"))
        return 0
    except (RetainedSupplementError, custody.ArchiveAssessmentRunnerError, EodhdDemoError,
            third.EarningsCampaignError, fourth.EarningsCampaignError,
            custody.assessment.EarningsArchiveAssessmentError, OSError, KeyError, TypeError,
            ValueError, subprocess.SubprocessError):
        print('{"disposition":"retained_earnings_supplement_refused_outputs_preserved"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
