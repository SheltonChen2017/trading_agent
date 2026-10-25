"""Protected full-stream selection of the pilot's first64 fresh2021Q1 parents.

This new offline operation rederives every source/disposition row and retains
all locator quarantines. It never performs transport or grants dispatch by a
shaped payload. The earlier audit namespace and body classifications stay intact.
"""
from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import sys
import time

from research import insider_buying_pilot_sec_parent_audit_runner as base
from research import insider_buying_pilot_sec_parent_structure_runner as retained
from research import insider_buying_pilot_sec_fresh_selection as selection


SELF_PATH = "research/insider_buying_pilot_sec_fresh_selection_runner.py"
SCHEMA = "insider-pilot-sec-fresh-selection-observer-v1"
AUDIT_ID = "ib-pilot-sec-first64-selection-20261025-once"
OUTPUT_PARTS = ("artifacts", "insider_buying", "pilot_sec_fresh_selection_v1")
LANE_ROOT = base.LANE_ROOT
REGISTRATION = {
    "schema": SCHEMA + "/registration", "audit_id": AUDIT_ID,
    "prior_audit_id": base.AUDIT_ID,
    "prior_audit_pins": {name: {"sha256": digest, "bytes": size} for name, (digest, size) in retained.PINS.items()},
    "selection_period": selection.PERIOD, "selection_limit": selection.LIMIT,
    "selection_policy": selection.POLICY,
    "full_source_scope": "25quarter2020Q1..2026Q1_all_six_forms",
    "locator_quarantines": "all target quarantines retained as metadata, never synthesized URLs",
    "whole_stream_and_operational_inputs_must_equal_completed_audit": True,
    "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0,
    "outcome_looks": 0, "backtests": 0, "backtesting_ready": False,
    "worker_invocations": 1,
    "native_worker_network_fork_allwrite_securityexec_denial": True,
    "trusted_parent_not_native_isolation": True,
}
_raw, _sha = base._raw, base._sha


class FreshSelectionRunnerError(ValueError):
    """Fixed source-independent refusal codes only."""


def _need(value, code):
    if not value:
        raise FreshSelectionRunnerError(code)


def _derive(prior, *, intake, operational_holds, exposure_raw, retained_raw, selection_raw):
    master = next((hold for hold in operational_holds if hold.spec.root_id == "masters-v3"), None)
    _need(master is not None, "fresh_selection_master_missing")
    builder, quarantines = selection.PilotSecFreshSelectionBuilder(), []

    def consume(disposition):
        builder.consume(disposition)
        if disposition["relevant_parent_target"] and disposition["selected_locator"] is None:
            _need(len(quarantines) < 256, "fresh_locator_quarantine_bound")
            # Detached canonical metadata. Full disposition digest is separately
            # consumed by the builder and completed compiler, not reconstructed.
            quarantines.append(base._decode(_raw(disposition)))

    compiler = base.compiler.PilotSecParentAuditCompiler(exposure_raw=exposure_raw,
        expected_exposure_sha256=_sha(exposure_raw), candidates_raw=retained_raw,
        expected_candidates_sha256=_sha(retained_raw),
        master_for_period=lambda period: base._master(master.tree, period), emit_row=consume)
    roster = base.roster.derive_pilot_sec_roster(intake_manifest_raw=intake.manifest_raw,
        expected_manifest_sha256=intake.context["manifest_sha256"], selection_raw=selection_raw,
        expected_selection_sha256=base.prior.ACTUAL_ANCHORS.selection,
        quarter_inputs=base.roster.held_context_quarters(intake), consume_row=compiler.consume, fixture_only=False)
    audit = compiler.finish(roster)
    _need(roster.to_payload() == prior["source_roster"] and audit.to_payload() == prior["parent_audit"],
        "fresh_full_completed_audit_changed")
    chosen = builder.finish(roster=roster, audit=audit,
        expected_roster_sha256=roster.sha256, expected_audit_sha256=audit.sha256)
    selection.validate_pilot_sec_fresh_selection(chosen)
    lines = b"".join(_raw(row) + b"\n" for row in quarantines)
    return {"selection": chosen.to_payload(), "selection_sha256": chosen.sha256,
        "source_roster": roster.to_payload(), "parent_audit": audit.to_payload(),
        "locator_quarantines": quarantines, "locator_quarantine_jsonl_sha256": _sha(lines),
        "locator_quarantine_jsonl_bytes": len(lines)}


def _worker(identity):
    _need(sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == base.EMPTY_CACHE_PREFIX, "fresh_selection_worker_isolation")
    _need(type(identity) is dict and identity.get("root") == str(LANE_ROOT)
        and identity.get("branch") == base.LANE_BRANCH and identity.get("clean") is True
        and identity.get("source_inventory_sha256") == _sha(_raw(identity["source_sha256"])),
        "fresh_selection_worker_identity")
    base._prove_isolation()
    _need(base.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"], "fresh_source_changed")
    _need(base.custody._source_bytes(LANE_ROOT, tuple(base.FROZEN)) == base.FROZEN, "fresh_frozen_source_changed")
    prior_hold, accepted_hold, intake, holds = None, None, None, []
    phase = "fresh_prior_controls"
    try:
        prior_hold = retained._PriorHold()
        prior = prior_hold.report()
        accepted_hold = base.prior._Held(LANE_ROOT)
        base.prior._selector(accepted_hold, base.prior.ACTUAL_ANCHORS)
        accepted_selection = accepted_hold.leaf(base.prior.SELECTOR_PARTS, "selection.json", base.prior.MAX_CONTROL,
            base.prior.ACTUAL_ANCHORS.selection)
        phase = "fresh_operational_recheck"
        holds, exposure_raw, snapshot_raw, candidates_raw = base.exposure.observe_exposures(base.exposure.actual_roots(), fixture_only=False)
        _need(_sha(exposure_raw) == prior["exposure_inventory_sha256"]
            and _sha(snapshot_raw) == prior["exposure_snapshot_sha256"], "fresh_operational_snapshot_changed")
        retained_raw = base.exposure.hash_candidate_bodies(holds, candidates_raw)
        _need(_sha(retained_raw) == prior["retained_body_inventory_sha256"], "fresh_retained_inventory_changed")
        phase = "fresh_full_source_rederivation"
        intake = base.selector._HeldIntake()
        derived = _derive(prior, intake=intake, operational_holds=holds, exposure_raw=exposure_raw,
            retained_raw=retained_raw, selection_raw=accepted_selection)
        phase = "fresh_final_input_recheck"
        intake.recheck();accepted_hold.recheck();prior_hold.recheck()
        for hold in holds: hold.recheck()
        _need(base.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"], "fresh_source_changed")
        result = {"schema": SCHEMA, "audit_id": AUDIT_ID, "registration": REGISTRATION,
            "registration_sha256": _sha(_raw(REGISTRATION)), "execution_identity": identity,
            "prior_audit_complete_sha256": retained.PINS["complete.json"][0],
            "exposure_inventory_sha256": _sha(exposure_raw), "exposure_snapshot_sha256": _sha(snapshot_raw),
            "retained_body_inventory_sha256": _sha(retained_raw), **derived,
            "native_network_fork_allwrite_securityexec_denial": True,
            "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
            "dispatch_authorized": False, "canonical_admitted": False, "backtesting_ready": False}
        return _validate(result, identity, prior)
    except Exception as exc:
        exc._pilot_audit_phase = phase
        raise
    finally:
        base.selector._close_all((intake, accepted_hold, prior_hold, *reversed(holds)), phase="fresh_selection_worker_cleanup")


def _validate(result, identity, prior):
    keys = {"schema", "audit_id", "registration", "registration_sha256", "execution_identity", "prior_audit_complete_sha256",
        "exposure_inventory_sha256", "exposure_snapshot_sha256", "retained_body_inventory_sha256", "selection", "selection_sha256",
        "source_roster", "parent_audit", "locator_quarantines", "locator_quarantine_jsonl_sha256", "locator_quarantine_jsonl_bytes",
        "native_network_fork_allwrite_securityexec_denial", "new_provider_requests", "credential_reads", "qc_accesses",
        "outcome_looks", "backtests", "dispatch_authorized", "canonical_admitted", "backtesting_ready"}
    _need(type(result) is dict and set(result) == keys and result["schema"] == SCHEMA and result["audit_id"] == AUDIT_ID
        and result["registration"] == REGISTRATION and result["registration_sha256"] == _sha(_raw(REGISTRATION))
        and result["execution_identity"] == identity and result["prior_audit_complete_sha256"] == retained.PINS["complete.json"][0]
        and result["native_network_fork_allwrite_securityexec_denial"] is True, "fresh_result_identity")
    for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
        _need(type(result[key]) is int and result[key] == 0, "fresh_result_access")
    for key in ("dispatch_authorized", "canonical_admitted", "backtesting_ready"):
        _need(result[key] is False, "fresh_result_authority")
    for key in ("source_roster", "parent_audit", "exposure_inventory_sha256", "exposure_snapshot_sha256", "retained_body_inventory_sha256"):
        _need(result[key] == prior[key], "fresh_result_prior_binding")
    value = selection.validate_selection_payload(result["selection"])
    _need(value["fixture_only"] is False and _sha(_raw(value)) == result["selection_sha256"]
        and value["source_roster_sha256"] == _sha(_raw(result["source_roster"]))
        and value["parent_audit_sha256"] == _sha(_raw(result["parent_audit"]))
        and value["exposure_inventory_sha256"] == result["exposure_inventory_sha256"]
        and value["retained_candidate_inventory_sha256"] == result["retained_body_inventory_sha256"]
        and value["quarter_bindings"] == result["parent_audit"]["quarters"], "fresh_selection_crosslinks")
    for stem in ("source_row", "disposition", "fresh_request"):
        _need(all(value["full_" + stem + suffix] == result["parent_audit"][stem + suffix]
            for suffix in ("_jsonl_sha256", "_jsonl_bytes")), "fresh_selection_completed_streams")
    rows = result["locator_quarantines"]
    _need(type(rows) is list and len(rows) <= 256, "fresh_quarantine_roster")
    totals, previous = Counter(), (-1, 0)
    for row in rows:
        _need(type(row) is dict and set(row) == selection._DISPOSITION_KEYS, "fresh_quarantine_schema")
        source, _ = base.compiler._source(row["source"])
        _need(row["schema"] == base.compiler.SCHEMA + "/filing", "fresh_quarantine_schema")
        for key in ("relevant_parent_target", "prior_consumed", "cross_quarter_accession_repeat",
                "cross_quarter_source_identity_conflict", "historical_ambiguous_start_preserved",
                "retained_candidate_body_identity_conflict", "body_candidate_is_not_parent_admission",
                "complete_parent_parsed_here", "fresh_locatable_candidate", "dispatch_authorized", "canonical_admitted"):
            _need(type(row[key]) is bool, "fresh_quarantine_boolean_type")
        evidence = row["prior_exposure_evidence"]
        _need(type(evidence) is list and row["prior_consumed"] is bool(evidence)
            and row["historical_ambiguous_start_preserved"] is any(item.get("state") == "ambiguous" for item in evidence),
            "fresh_quarantine_exposure_consistency")
        if evidence:
            base.compiler._exposures({"schema": base.compiler.EXPOSURE_SCHEMA, "records": [{
                "accession_number": source["accession_number"], "accession_key_sha256": source["accession_key_sha256"], "evidence": evidence}]})
        _need(type(row["locator_quarantine_reasons"]) is list and len(row["locator_quarantine_reasons"]) == 1
            and row["locator_quarantine_reasons"][0] in {"master_locator_missing", "master_form_disagreement",
                "master_filing_date_disagreement", "multiple_master_aliases_without_unique_issuer_path"}, "fresh_quarantine_reason")
        aliases = row["master_aliases"]
        _need(type(aliases) is list and len(aliases) <= base.compiler.MAX_EVIDENCE_PER_ACCESSION, "fresh_quarantine_alias_bound")
        for alias in aliases:
            parsed = selection.SecMasterIndexRow(**alias).to_payload()
            _need(parsed == alias and alias["accession_number"] == source["accession_number"], "fresh_quarantine_alias_identity")
        reason = ("master_locator_missing" if not aliases else
            "master_form_disagreement" if any(alias["form_type"] != source["form_type"] for alias in aliases) else
            "master_filing_date_disagreement" if any(alias["filing_date"] != source["filing_date"] for alias in aliases) else
            "multiple_master_aliases_without_unique_issuer_path")
        _need(row["locator_quarantine_reasons"] == [reason], "fresh_quarantine_reason_binding")
        if reason == "multiple_master_aliases_without_unique_issuer_path":
            matches = [alias for alias in aliases if base.compiler._cik(base.compiler._PATH.fullmatch(alias["archive_path"]).group(1))
                == source["issuer_comparison_key"]]
            _need(len(aliases) > 1 and len(matches) != 1, "fresh_quarantine_unique_locator_exists")
        # This operation must reproduce the captured audit, whose complete
        # source has zero repeated/conflicting identities and whose quarantines
        # lie outside every retained consumed quarter. Do not widen its scope
        # by accepting a coherently rewritten quarantine ledger.
        _need(row["prior_consumed"] is False and evidence == []
            and row["historical_ambiguous_start_preserved"] is False
            and row["prior_source_occurrence"] is None and row["cross_quarter_accession_repeat"] is False
            and row["cross_quarter_source_identity_conflict"] is False
            and row["candidate_identity_conflicts"] == [] and row["matching_retained_candidates"] == []
            and row["retained_candidate_body_identity_conflict"] is False
            and row["disposition"] == "no_prior_dispatch_observed_locator_quarantined", "fresh_quarantine_prior_scope")
        ordinal = (base.roster.CONTEXT_PERIODS.index(source["period"]), source["source_record_ordinal"])
        _need(ordinal > previous and source["form_type"] in {"4", "4/A"}
            and row["source_record_sha256"] == source["filing_metadata_sha256"]
            and row["relevant_parent_target"] is True and row["selected_locator"] is None
            and row["request"] is None and row["request_sha256"] is None and row["locator_quarantine_reasons"]
            and row["pre_normalization_target"] is None and row["body_candidate_is_not_parent_admission"] is True
            and row["fresh_locatable_candidate"] is False and row["complete_parent_parsed_here"] is False
            and row["dispatch_authorized"] is False and row["canonical_admitted"] is False,
            "fresh_quarantine_identity_or_authority")
        totals[source["period"]] += 1;previous = ordinal
    _need(all(totals[row["period"]] == row["counts"]["locator_quarantined_targets"] for row in result["parent_audit"]["quarters"]),
        "fresh_quarantine_conservation")
    lines = b"".join(_raw(row) + b"\n" for row in rows)
    _need(result["locator_quarantine_jsonl_sha256"] == _sha(lines)
        and type(result["locator_quarantine_jsonl_bytes"]) is int and result["locator_quarantine_jsonl_bytes"] == len(lines),
        "fresh_quarantine_stream")
    return result


def _failure_control(exc):
    result = base._failure_control(exc)
    if type(exc) in {FreshSelectionRunnerError, selection.PilotSecFreshSelectionError} and base.re.fullmatch(r"[a-z][a-z0-9_]{0,159}", str(exc)):
        result["code"] = str(exc)
    return result


class _Guard(base._ParentGuard):
    def __init__(self, head, command):
        super().__init__(head, command)
        self.output = LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)


class _Output(base._Publication):
    def __init__(self, chain):
        self.path = LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)
        self.chain, self.tree, self.pins = chain, None, {}
        _need(os.listdir(chain.fd) == [], "fresh_selection_cannot_resume")


def run_actual(expected_head):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "fixed_fresh_selection_source")
    identity = base.custody._identity(expected_head)
    _need(SELF_PATH in identity["source_sha256"] and selection.__file__.endswith("insider_buying_pilot_sec_fresh_selection.py"),
        "committed_fresh_selection_source")
    code = ("import sys;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");"
        "from research import insider_buying_pilot_sec_fresh_selection_runner as m;import json;"
        "identity=json.loads(" + repr(_raw(identity).decode()) + ");"
        "\ntry: result=m._worker(identity)\nexcept Exception as exc: "
        "print(m._raw(m._failure_control(exc)).decode());sys.exit(2)\nprint(m._raw(result).decode())")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix=" + base.EMPTY_CACHE_PREFIX, "-c", code)
    sys.addaudithook(_Guard(expected_head, command))
    parent = base.custody._Chain(LANE_ROOT, OUTPUT_PARTS[:2])
    try:
        try: os.mkdir(LANE_ROOT.joinpath(*OUTPUT_PARTS), 0o700)
        except FileExistsError: pass
        parent.recheck()
    finally: parent.close()
    directory = base.custody._Chain(LANE_ROOT, OUTPUT_PARTS)
    try:
        os.mkdir(LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID), 0o700)
        directory.recheck()
    finally: directory.close()
    directory = base.custody._Chain(LANE_ROOT, (*OUTPUT_PARTS, AUDIT_ID))
    output, prior_hold = None, None
    try:
        _need(os.fstatvfs(directory.fd).f_bavail * os.fstatvfs(directory.fd).f_frsize >= 4 * 1024**3 + 3 * base.MAX_REPORT,
            "fresh_selection_disk_reserve")
        output = _Output(directory)
        reservation_sha = output.publish("reservation.json", _raw({"schema": SCHEMA + "/reservation",
            "registration": REGISTRATION, "execution_identity": identity}))
        started = time.monotonic()
        child = base.launcher.run_child(command, cwd=LANE_ROOT, env=None, timeout=1800, cap=base.MAX_REPORT)
        terminal = {"schema": SCHEMA + "/terminal", "reservation_sha256": reservation_sha,
            "elapsed_seconds": round(time.monotonic() - started, 6), "exit_code": child.returncode,
            "stdout_bytes": len(child.stdout), "stdout_sha256": _sha(child.stdout),
            "stderr_bytes": len(child.stderr), "stderr_sha256": _sha(child.stderr)}
        if child.returncode != 0 and child.stderr == b"" and 0 < len(child.stdout) <= 1024:
            try:
                refusal = base._decode(child.stdout.removesuffix(b"\n"))
                _need(set(refusal) == {"worker_refused", "code", "phase"} and all(type(value) is str
                    and base.re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,159}", value) for value in refusal.values()), "fresh_refusal_schema")
                terminal["worker_refusal"] = refusal
            except Exception: pass
        output.publish("terminal.json", _raw(terminal))
        _need(child.returncode == 0 and child.stderr == b"" and 0 < len(child.stdout) <= base.MAX_REPORT, "fresh_selection_worker_refused")
        prior_hold = retained._PriorHold()
        prior = prior_hold.report()
        worker = _validate(base._decode(child.stdout.removesuffix(b"\n")), identity, prior)
        prior_hold.recheck()
        _need(base.custody._identity(expected_head) == identity, "fresh_selection_parent_source_changed")
        complete = {"schema": SCHEMA + "/complete", "audit_id": AUDIT_ID,
            "reservation_sha256": reservation_sha, "terminal_sha256": _sha(_raw(terminal)), "worker_result": worker}
        raw = _raw(complete);digest = output.publish("complete.json", raw)
        output.recheck(final=True)
        return {"schema": SCHEMA, "audit_id": AUDIT_ID, "complete_sha256": digest, "complete_bytes": len(raw),
            "selection_sha256": worker["selection_sha256"], "selected_count": worker["selection"]["selected_count"],
            "locator_quarantines": len(worker["locator_quarantines"]), "elapsed_seconds": terminal["elapsed_seconds"],
            "backtesting_ready": False}
    finally:
        base.selector._close_all((prior_hold, output, directory), phase="fresh_selection_parent_cleanup")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try: result = run_actual(args.expected_head)
    except Exception:
        print('{"disposition":"pilot_fresh_selection_refused"}')
        return 2
    print(_raw(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
