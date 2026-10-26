"""One protected offline structural pass over the audited retained pilot parents.

This is a NEW operation, not a replay/relabel of the metadata audit, an old
collector, or canonical IB1C admission. Financial XML text is structurally
decoded by the unchanged frozen parser, never numerically projected here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from research import insider_buying_pilot_sec_parent_audit_runner as base
from research import insider_buying_pilot_sec_parent_structure as structure


SELF_PATH = "research/insider_buying_pilot_sec_parent_structure_runner.py"
SCHEMA = "insider-pilot-retained-parent-structure-observer-v1"
AUDIT_ID = "ib-pilot-sec-parent-structure-20261025-once"
OUTPUT_PARTS = ("artifacts", "insider_buying", "pilot_sec_parent_structure_v1")
LANE_ROOT = base.LANE_ROOT
PINS = {
    "reservation.json": ("c804118503b580c1985ecf4849fb0a990c160ca5ce4681a9234b4d753c3537cc", 13328),
    "terminal.json": ("1cefa3150c7dcab598391105a8fcc899bac6e21d4277d5417dafe4b405149bd4", 423),
    "complete.json": ("f9ae8d1b96437f7107bfa431739132d49a0880f28de581e6dfe913673e2cc558", 73723173),
}
REGISTRATION = {
    "schema": SCHEMA + "/registration", "audit_id": AUDIT_ID,
    "prior_audit_id": base.AUDIT_ID,
    "prior_audit_pins": {name: {"sha256": digest, "bytes": size} for name, (digest, size) in PINS.items()},
    "prior_existing_execution_head": "b33cf144153fd118add3acdc6a9caad22b8b4077",
    "pilot_window": "2021Q1..2025Q4", "expected_distinct_pilot_body_candidates": 19852,
    "original_financial_numeric_fields_converted": False,
    "scope": "request_bound_original_header_and_XML_structure_not_IB1C_canonical_admission",
    "ambiguous_prior_requests_resolved_or_retried": False,
    "duplicate_physical_copies": "all copies hash-checked; require unanimous URL/body/target; parse one identical image",
    "all_source_rows_accounted_by_prior_audit": True,
    "new_provider_requests": 0, "credential_reads": 0, "qc_access": False,
    "outcome_looks": 0, "backtests": 0, "backtesting_ready": False,
    "worker_invocations": 1, "native_worker_network_fork_allwrite_securityexec_denial": True,
    "trusted_parent_not_native_isolation": True,
}


class StructureRunnerError(ValueError):
    """Fixed source-independent refusal codes only."""


def _need(value, code):
    if not value:
        raise StructureRunnerError(code)


_raw, _sha = base._raw, base._sha


class _PriorHold:
    def __init__(self):
        self.tree = None
        try:
            self.tree = base.selector.held_io._HeldCapture(LANE_ROOT.joinpath(*base.OUTPUT_PARTS, base.AUDIT_ID),
                private=True, settle_ctime=True)
            _need(self.tree.names == set(PINS), "prior_control_inventory")
            for name, (_, size) in PINS.items():
                self.tree.open(name, size)
            self.recheck()
        except BaseException:
            self.close()
            raise

    def recheck(self):
        self.tree.check()
        for name, stream, _, cap in self.tree.handles:
            _need(base.selector.held_io._hash_stream(stream, cap) == PINS[name], "prior_control_hash_changed")
        self.tree.check()

    def report(self):
        stream = next(stream for name, stream, _, _ in self.tree.handles if name == "complete.json")
        stream.seek(0)
        report = base._decode(stream.read(PINS["complete.json"][1] + 1))
        base._validate_result(report, report["execution_identity"])
        _need(report["execution_identity"]["head"] == REGISTRATION["prior_existing_execution_head"], "prior_execution_head")
        return report

    def close(self):
        base.selector._close_tree(self.tree, phase="structure_prior_cleanup")


def _pilot_records(inventory):
    result = []
    for row in inventory["records"]:
        candidates = [item for item in row["candidates"] if item["retained_target"]["period"] in base.roster.PILOT_PERIODS]
        if not candidates:
            continue
        # Selection is only between already verified byte-identical copies,
        # never between archive aliases, conflicting identities or bodies.
        signatures = {(_raw({**item["retained_target"], "issuer_cik": item["retained_target"]["issuer_cik"].zfill(10)}),
            item["request_url"], item["raw_object"]["sha256"], item["raw_object"]["size_bytes"]) for item in candidates}
        _need(len(signatures) == 1 and all(item["body_currently_hash_verified"] is True for item in candidates),
            "retained_candidate_unanimity_required")
        result.append((row["accession_number"], candidates))
    _need(len(result) == REGISTRATION["expected_distinct_pilot_body_candidates"], "exact_audited_pilot_candidate_count")
    return result


def _derive(prior, holds, exposure_raw, retained_raw, process=structure.process_candidate):
    exposure_records = base._decode(exposure_raw)["records"]
    exposures = {item["accession_number"]: item["evidence"] for item in exposure_records}
    inventory = base._decode(retained_raw)
    by_root = {hold.spec.root_id: hold for hold in holds}
    masters = {row["period"]: row["producer_receipt"]["decoded_sha256"] for row in inventory["masters"]}
    rows, totals, quarters, digest, byte_count = [], Counter(), {}, hashlib.sha256(), 0
    for accession, candidates in _pilot_records(inventory):
        item = candidates[0]
        period = item["retained_target"]["period"]
        evidence = exposures.get(accession)
        _need(evidence is not None and period in masters, "audited_consumption_or_master_missing")
        parts = tuple(Path(item["raw_object"]["relative_path"]).parts)
        body = by_root[item["root_id"]].tree.read(parts[:-1], parts[-1],
            cap=structure.MAX_BODY_BYTES, expected=item["raw_object"]["sha256"])
        _need(len(body) == item["raw_object"]["size_bytes"], "original_body_size_changed")
        observed = process(body, item, expected_candidate_sha256=_sha(_raw(item)),
            expected_body_sha256=item["raw_object"]["sha256"], expected_master_decoded_sha256=masters[period],
            prior_exposure_evidence=evidence)
        payload = structure.validate_pilot_sec_parent_structure(observed)
        wrapped = {"structure": payload, "all_matching_evidence": [{"root_id": other["root_id"],
            "control_name": other["control_name"], "control_sha256": other["control_sha256"],
            "request_sha256": other["request_sha256"], "retained_target": other["retained_target"],
            "request_url": other["request_url"], "raw_object": other["raw_object"]} for other in candidates]}
        encoded = _raw(wrapped) + b"\n"
        digest.update(encoded)
        byte_count += len(encoded)
        rows.append(wrapped)
        success = payload["full_original_structurally_bound"]
        key = "structurally_bound" if success else "structure_quarantined"
        totals[key] += 1
        totals["candidates"] += 1
        totals["historical_ambiguous_start_preserved"] += any(e["state"] == "ambiguous" for e in evidence)
        count = quarters.setdefault(period, Counter())
        count[key] += 1
        count["candidates"] += 1
    expected = {row["period"]: row["counts"]["hash_verified_matching_body_candidate_targets"]
        for row in prior["parent_audit"]["quarters"] if row["period"] in base.roster.PILOT_PERIODS}
    _need(all(quarters.get(period, {}).get("candidates", 0) == count for period, count in expected.items()),
        "audited_quarter_candidate_conservation")
    counts = {key: totals[key] for key in ("candidates", "structurally_bound", "structure_quarantined", "historical_ambiguous_start_preserved")}
    _need(counts["candidates"] == counts["structurally_bound"] + counts["structure_quarantined"]
        == prior["parent_audit"]["pilot_counts"]["hash_verified_matching_body_candidate_targets"], "full_candidate_conservation")
    return {"counts": counts, "quarter_counts": {period: dict(quarters.get(period, {})) for period in base.roster.PILOT_PERIODS},
        "structural_records": rows, "ordered_structural_jsonl_sha256": digest.hexdigest(),
        "ordered_structural_jsonl_bytes": byte_count,
        "framing": "sha256_canonical_wrapped_structure_record_plus_LF_in_accession_order",
        "source_filings_not_redecoded_here": True,
        "prior_full_source_roster_sha256": _sha(_raw(prior["source_roster"])),
        "body_structure_is_not_bulk_numeric_or_IB1C_identity_admission": True,
        "all_authority_remains_false": True}


def _worker(identity):
    _need(sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == base.EMPTY_CACHE_PREFIX, "isolated_structure_worker")
    _need(identity.get("root") == str(LANE_ROOT) and identity.get("branch") == base.LANE_BRANCH
        and identity.get("clean") is True and identity.get("source_inventory_sha256") == _sha(_raw(identity["source_sha256"])),
        "exact_structure_identity")
    base._prove_isolation()
    _need(base.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"], "source_changed")
    _need(base.custody._source_bytes(LANE_ROOT, tuple(base.FROZEN)) == base.FROZEN, "frozen_source_changed")
    prior_hold, holds = None, []
    try:
        prior_hold = _PriorHold()
        prior = prior_hold.report()
        holds, exposure_raw, snapshot_raw, candidate_raw = base.exposure.observe_exposures(base.exposure.actual_roots(), fixture_only=False)
        _need(_sha(exposure_raw) == prior["exposure_inventory_sha256"]
            and _sha(snapshot_raw) == prior["exposure_snapshot_sha256"], "operational_snapshot_changed_since_audit")
        retained_raw = base.exposure.hash_candidate_bodies(holds, candidate_raw)
        _need(_sha(retained_raw) == prior["retained_body_inventory_sha256"], "retained_inventory_changed_since_audit")
        result = _derive(prior, holds, exposure_raw, retained_raw)
        for hold in holds:
            hold.recheck()
        prior_hold.recheck()
        _need(base.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"], "source_changed")
        return {"schema": SCHEMA, "audit_id": AUDIT_ID, "registration": REGISTRATION,
            "registration_sha256": _sha(_raw(REGISTRATION)), "execution_identity": identity,
            "prior_audit_complete_sha256": PINS["complete.json"][0],
            "exposure_inventory_sha256": _sha(exposure_raw), "retained_inventory_sha256": _sha(retained_raw),
            "result": result, "authority": dict(base.compiler._AUTHORITY),
            "native_network_fork_allwrite_securityexec_denial": True,
            "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0,
            "financial_numeric_fields_converted": False, "canonical_admitted": False, "backtesting_ready": False}
    finally:
        base.selector._close_all((prior_hold, *reversed(holds)), phase="structure_worker_cleanup")


def _failure_control(exc):
    value = base._failure_control(exc)
    if type(exc) in {StructureRunnerError, structure.PilotSecParentStructureError}:
        code = str(exc)
        if base.re.fullmatch(r"[a-z][a-z0-9_]{0,159}", code):
            value["code"] = code
    return value


class _Guard(base._ParentGuard):
    def __init__(self, head, command):
        super().__init__(head, command)
        self.output = LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)


class _Output(base._Publication):
    def __init__(self, chain):
        # Fixed NEW production scope, not a fixture fence escape or a mutable
        # global substitution in the already consumed metadata observer.
        self.path = LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)
        self.chain, self.tree, self.pins = chain, None, {}
        _need(os.listdir(chain.fd) == [], "structure_output_cannot_resume")


def _validate(result, identity):
    expected_keys = {"schema", "audit_id", "registration", "registration_sha256", "execution_identity",
        "prior_audit_complete_sha256", "exposure_inventory_sha256", "retained_inventory_sha256", "result", "authority",
        "native_network_fork_allwrite_securityexec_denial", "new_provider_requests", "credential_reads", "qc_accesses",
        "financial_numeric_fields_converted", "canonical_admitted", "backtesting_ready"}
    _need(type(result) is dict and set(result) == expected_keys and result.get("schema") == SCHEMA and result.get("audit_id") == AUDIT_ID
        and result.get("execution_identity") == identity and result.get("registration") == REGISTRATION
        and result.get("registration_sha256") == _sha(_raw(REGISTRATION))
        and result.get("prior_audit_complete_sha256") == PINS["complete.json"][0]
        and result.get("native_network_fork_allwrite_securityexec_denial") is True
        and result.get("authority") == base.compiler._AUTHORITY, "structure_result_identity")
    base.readback._false_authority(result["authority"], base.compiler._AUTHORITY)
    for key in ("exposure_inventory_sha256", "retained_inventory_sha256"):
        base.roster._digest(result[key])
    for key in ("new_provider_requests", "credential_reads", "qc_accesses"):
        _need(type(result.get(key)) is int and result[key] == 0, "structure_access_not_zero")
    for key in ("financial_numeric_fields_converted", "canonical_admitted", "backtesting_ready"):
        _need(result.get(key) is False, "structure_authority_refused")
    body = result["result"]
    _need(type(body) is dict and set(body) == {"counts", "quarter_counts", "structural_records", "ordered_structural_jsonl_sha256",
        "ordered_structural_jsonl_bytes", "framing", "source_filings_not_redecoded_here", "prior_full_source_roster_sha256",
        "body_structure_is_not_bulk_numeric_or_IB1C_identity_admission", "all_authority_remains_false"}
        and type(body.get("structural_records")) is list
        and body["source_filings_not_redecoded_here"] is True
        and body["body_structure_is_not_bulk_numeric_or_IB1C_identity_admission"] is True
        and body["all_authority_remains_false"] is True
        and body["framing"] == "sha256_canonical_wrapped_structure_record_plus_LF_in_accession_order", "structure_record_roster")
    base.roster._digest(body["prior_full_source_roster_sha256"])
    digest, count, totals, by_quarter, seen = hashlib.sha256(), 0, Counter(), {}, set()
    previous_accession = ""
    for row in body["structural_records"]:
        _need(type(row) is dict and set(row) == {"structure", "all_matching_evidence"}, "structure_row_schema")
        item = row["structure"]
        structure_keys = {"schema", "scope", "candidate_descriptor_sha256", "request_sha256", "request", "retained_target",
            "frozen_parser_comparison_target", "issuer_comparison_padding_applied", "raw_request_target_rewritten", "source_body_modified",
            "expected_master_decoded_sha256", "raw_parent", "retained_control", "prior_exposure_evidence",
            "historical_ambiguous_start_preserved", "original_unmatched_start_resolved", "consumed_accession_released_for_redispatch",
            "disposition", "quarantine_code", "full_original_structurally_bound", "ownership_xml_identity_structurally_checked",
            "frozen_parser_version", "frozen_projection_sha256", "children", "source_declared_fields",
            "source_declared_acceptance_is_not_official_or_pit", "xml_financial_text_may_be_structurally_decoded",
            "financial_numeric_fields_converted", "financial_values_projected", "canonical_or_ib1c_identity_admitted",
            "named_file_custody_verified_here", "authority"}
        _need(type(item) is dict and set(item) == structure_keys, "structure_payload_schema")
        accession = item["retained_target"]["accession_number"]
        _need(accession not in seen and previous_accession < accession, "structure_accession_order_or_repeat")
        seen.add(accession)
        previous_accession = accession
        _need(item["schema"] == structure.SCHEMA and item["authority"] == base.compiler._AUTHORITY
            and item["financial_numeric_fields_converted"] is False and item["financial_values_projected"] is False
            and item["canonical_or_ib1c_identity_admitted"] is False, "structure_row_authority")
        _need(item["scope"] == "supplied_source_structure_not_operational_or_canonical_attestation"
            and item["frozen_parser_version"] == structure.frozen.SEC_COMPLETE_SUBMISSION_VERSION, "structure_parser_scope")
        base.readback._false_authority(item["authority"], base.compiler._AUTHORITY)
        _need(item["original_unmatched_start_resolved"] is False and item["consumed_accession_released_for_redispatch"] is False
            and item["raw_request_target_rewritten"] is False and item["source_body_modified"] is False
            and item["named_file_custody_verified_here"] is False
            and item["source_declared_acceptance_is_not_official_or_pit"] is True
            and item["xml_financial_text_may_be_structurally_decoded"] is True
            and type(item["historical_ambiguous_start_preserved"]) is bool, "structure_row_scope")
        _need(item["request_sha256"] == _sha(_raw(item["request"]))
            and item["historical_ambiguous_start_preserved"] is any(e["state"] == "ambiguous" for e in item["prior_exposure_evidence"]),
            "structure_request_or_ambiguity_binding")
        raw_target = item["retained_target"]
        _need(type(raw_target) is dict and set(raw_target) == {"period", "accession_number", "form_type", "filing_date", "issuer_cik"},
            "structure_raw_target_schema")
        comparison = structure.frozen.SecCompleteSubmissionTarget(**item["frozen_parser_comparison_target"]).to_payload()
        _need(all(raw_target[key] == comparison[key] for key in ("period", "accession_number", "form_type", "filing_date"))
            and raw_target["issuer_cik"].zfill(10) == comparison["issuer_cik"]
            and comparison["quarterly_index_sha256"] == item["expected_master_decoded_sha256"]
            and type(item["issuer_comparison_padding_applied"]) is bool
            and item["issuer_comparison_padding_applied"] is (raw_target["issuer_cik"] != comparison["issuer_cik"]),
            "structure_comparison_target_binding")
        _need(all(key not in item["request"] or item["request"][key] == value for key, value in raw_target.items())
            and ("url" not in item["request"] or item["request"]["url"] == comparison["complete_submission_url"]),
            "structure_request_target_binding")
        success = item["full_original_structurally_bound"]
        _need(type(success) is bool and (item["quarantine_code"] is None if success else item["quarantine_code"] == structure.QUARANTINE_CODE),
            "structure_row_disposition")
        _need(item["ownership_xml_identity_structurally_checked"] is success
            and item["disposition"] == ("original_complete_parent_structurally_bound_noncanonical" if success else
                "original_complete_parent_structure_quarantined_noncanonical"), "structure_disposition_mismatch")
        if success:
            base.roster._digest(item["frozen_projection_sha256"])
            _need(type(item["children"]) is dict and set(item["children"]) == {"header", "primary_xml"}
                and all(child["parent_sha256"] == item["raw_parent"]["sha256"] for child in item["children"].values())
                and type(item["source_declared_fields"]) is dict, "structure_children_parent_binding")
        else:
            _need(item["children"] is None and item["source_declared_fields"] is None
                and item["frozen_projection_sha256"] is None, "structure_quarantine_not_empty")
        _need(type(row["all_matching_evidence"]) is list and row["all_matching_evidence"], "structure_evidence_missing")
        selected_found = False
        for evidence in row["all_matching_evidence"]:
            _need(type(evidence) is dict and set(evidence) == {"root_id", "control_name", "control_sha256", "request_sha256", "retained_target", "request_url", "raw_object"}
                and evidence["raw_object"]["sha256"] == item["raw_parent"]["sha256"]
                and evidence["raw_object"]["size_bytes"] == item["raw_parent"]["size_bytes"], "structure_evidence_parent_binding")
            target = evidence["retained_target"]
            _need(type(target) is dict and set(target) == set(raw_target)
                and all(target[key] == raw_target[key] for key in ("period", "accession_number", "form_type", "filing_date"))
                and target["issuer_cik"].zfill(10) == comparison["issuer_cik"]
                and evidence["request_url"] == comparison["complete_submission_url"], "structure_all_evidence_target_binding")
            for key in ("control_sha256", "request_sha256"):
                base.roster._digest(evidence[key])
            selected_found |= (evidence["retained_target"] == raw_target and evidence["request_sha256"] == item["request_sha256"]
                and all(evidence[key] == item["retained_control"][key] for key in ("root_id", "control_name", "control_sha256")))
        _need(selected_found, "structure_selected_control_not_in_evidence")
        totals["candidates"] += 1
        totals["structurally_bound" if success else "structure_quarantined"] += 1
        totals["historical_ambiguous_start_preserved"] += item["historical_ambiguous_start_preserved"]
        period = item["retained_target"]["period"]
        _need(period in base.roster.PILOT_PERIODS, "structure_pilot_period")
        q = by_quarter.setdefault(period, Counter())
        q["candidates"] += 1
        q["structurally_bound" if success else "structure_quarantined"] += 1
        encoded = _raw(row) + b"\n"
        digest.update(encoded)
        count += len(encoded)
    expected_counts = {key: totals[key] for key in ("candidates", "structurally_bound", "structure_quarantined", "historical_ambiguous_start_preserved")}
    _need(type(body["quarter_counts"]) is dict and set(body["quarter_counts"]) == set(base.roster.PILOT_PERIODS)
        and all(type(counts) is dict and set(counts) <= {"candidates", "structurally_bound", "structure_quarantined"}
            and all(type(value) is int and 0 <= value <= REGISTRATION["expected_distinct_pilot_body_candidates"]
                for value in counts.values()) for counts in body["quarter_counts"].values()), "structure_quarter_typed_counts")
    _need(body["counts"] == expected_counts and all(type(value) is int for value in body["counts"].values())
        and expected_counts["candidates"] == REGISTRATION["expected_distinct_pilot_body_candidates"]
        and body["ordered_structural_jsonl_sha256"] == digest.hexdigest() and body["ordered_structural_jsonl_bytes"] == count
        and body["quarter_counts"] == {period: dict(by_quarter.get(period, {})) for period in base.roster.PILOT_PERIODS},
        "structure_full_stream_conservation")
    return result


def run_actual(expected_head):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "fixed_structure_source")
    identity = base.custody._identity(expected_head)
    _need(SELF_PATH in identity["source_sha256"], "committed_structure_source")
    code = ("import sys;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");"
        "from research import insider_buying_pilot_sec_parent_structure_runner as m;import json;"
        "identity=json.loads(" + repr(_raw(identity).decode()) + ");"
        "\ntry: result=m._worker(identity)\nexcept Exception as exc: "
        "print(m._raw(m._failure_control(exc)).decode());sys.exit(2)\nprint(m._raw(result).decode())")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix=" + base.EMPTY_CACHE_PREFIX, "-c", code)
    sys.addaudithook(_Guard(expected_head, command))
    parent = base.custody._Chain(LANE_ROOT, OUTPUT_PARTS[:2])
    try:
        try:
            os.mkdir(LANE_ROOT.joinpath(*OUTPUT_PARTS), 0o700)
        except FileExistsError:
            pass
        parent.recheck()
    finally:
        parent.close()
    directory = base.custody._Chain(LANE_ROOT, OUTPUT_PARTS)
    try:
        os.mkdir(LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID), 0o700)
        directory.recheck()
    finally:
        directory.close()
    directory = base.custody._Chain(LANE_ROOT, (*OUTPUT_PARTS, AUDIT_ID))
    output = None
    try:
        _need(os.fstatvfs(directory.fd).f_bavail * os.fstatvfs(directory.fd).f_frsize >= 4 * 1024**3 + 3 * base.MAX_REPORT,
            "structure_disk_reserve")
        output = _Output(directory)
        reservation_sha = output.publish("reservation.json", _raw({"schema": SCHEMA + "/reservation",
            "registration": REGISTRATION, "execution_identity": identity}))
        started = time.monotonic()
        child = base.launcher.run_child(command, cwd=LANE_ROOT, env=None, timeout=1800, cap=base.MAX_REPORT)
        terminal = {"schema": SCHEMA + "/terminal", "reservation_sha256": reservation_sha,
            "elapsed_seconds": round(time.monotonic() - started, 6), "exit_code": child.returncode,
            "stdout_bytes": len(child.stdout), "stdout_sha256": _sha(child.stdout),
            "stderr_bytes": len(child.stderr), "stderr_sha256": _sha(child.stderr)}
        if child.returncode != 0 and not child.stderr and 0 < len(child.stdout) <= 1024:
            try:
                refusal = base._decode(child.stdout.removesuffix(b"\n"))
                _need(set(refusal) == {"worker_refused", "code", "phase"}
                    and all(type(value) is str and base.re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,159}", value)
                        for value in refusal.values()), "sanitized_structure_refusal_schema")
                terminal["worker_refusal"] = refusal
            except Exception:
                pass
        output.publish("terminal.json", _raw(terminal))
        _need(child.returncode == 0 and child.stderr == b"" and 0 < len(child.stdout) <= base.MAX_REPORT, "structure_worker_refused")
        result = _validate(base._decode(child.stdout.removesuffix(b"\n")), identity)
        _need(base.custody._identity(expected_head) == identity, "structure_parent_source_changed")
        raw = _raw(result)
        digest = output.publish("complete.json", raw)
        output.recheck(final=True)
        return {"schema": SCHEMA, "audit_id": AUDIT_ID, "complete_sha256": digest, "complete_bytes": len(raw),
            "elapsed_seconds": terminal["elapsed_seconds"], "counts": result["result"]["counts"],
            "quarter_counts": result["result"]["quarter_counts"], "backtesting_ready": False}
    finally:
        base.selector._close_all((output, directory), phase="structure_parent_cleanup")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_actual(args.expected_head)
    except Exception:
        print('{"disposition":"pilot_parent_structure_refused"}')
        return 2
    print(_raw(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
