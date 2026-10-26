"""One-use, network-denied retained-source recovery and October composition.

This is not an acquisition or QC caller. A separate committed run decision
must bind this source, clean HEAD, exact selected pins and actual exit handling.
No raw exceptions, source rows or credential values may cross its console.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import MappingProxyType

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import diagnose_arv2_r297_authentication as diagnostic
from scripts import build_arv2_delta_order_input_package as historical
from scripts import arv2_october_input_failure as failure
from research.analyst_revisions_v2_qc import accepted_risk_latest_order_package as latest
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october
from research.analyst_revisions_v2_qc import accepted_risk_massive_ratings_delta_v2 as recovered

helpers, transport = diagnostic.helpers, diagnostic.original.transport
capture = diagnostic.capture
BRANCH, PYTHON = diagnostic.BRANCH, diagnostic.PYTHON
SOURCE = ROOT / "scripts/build_arv2_october_comparison_inputs.py"
ARTIFACTS = ROOT / "artifacts/analyst_revisions_v2"
CONTROL = ARTIFACTS / "massive_ratings_delta/R297-20261013-D5"
RETAINED = diagnostic.CAPTURE_PATH
TAIL = ARTIFACTS / "physical_accepted_risk_latest_20260925/arv2-physical-accepted-risk-f87c0cb219a7e5f8d51a33b8"
TAIL_SOURCE = ARTIFACTS / "massive_capture/arv2-massive-three-role-20260926T061343494005Z"
PREDECESSOR = ARTIFACTS / "accepted_risk_latest_order_package_20260925_01"
DEADLINE_SECONDS = 1800
SCHEMA = "arv2-october-comparison-input-operation-v1"
# Exact selected pre-use pins; not whole-interpreter integrity or run authority.
SOURCE_PINS = MappingProxyType({
    "research/analyst_revisions_v2/accepted_risk_input_pair.py": "4aa82377661420e4ee017b3cdefd54f038af75eca2b3cf086f57d11a6c55a037",
    "research/analyst_revisions_v2/availability.py": "238738109bb7e2e3408376b143dfafc8fe5dc174b30a6a642276fda669d26ce4",
    "research/analyst_revisions_v2/canonical.py": "c1d1d1aab633b16868fccc371de7c4cf4f3a692943e04a8d785109110e17ae6e",
    "research/analyst_revisions_v2/forward_data_quality.py": "2391ab4d465fead135c9836231294c0de5fce0eae959c15fc67827d82191f557",
    "research/analyst_revisions_v2/global_benchmark_contract.py": "ebb91b61eea62e53466bc20f2b3b3272a48bc2487e3b1e75a9f9337b69e2068b",
    "research/analyst_revisions_v2/specs/arv2_global_matched_comparison.structural.json": "40b164e3e2944053eaaaaf1a651e34dfb335a4cbc8aeca2ee3f67ecdc9e8dffa",
    "research/analyst_revisions_v2/specs/arv2_global_rating_map.structural.json": "630cc822fa83d7aba15920cfb8f37863f6d6fffa262e26ac96074e8526391f4e",
    "research/analyst_revisions_v2/specs/arv2_qc_first.draft.json": "8339238dd5ce32ed7b351aab2662fb408cc7d9a3c62ff89bf8b1d14f20acd081",
    "research/analyst_revisions_v2/specs/arv2_stock_historical.structural.json": "34d1e71548bc6850a02590596594944dad3fadb38954067f2cc2d00dcaa86bc8",
    "research/analyst_revisions_v2/specs/arv2_stock_historical_successor.structural.json": "51718ee5ae278d1254e8efb01b2acdd9c6cbe51741dd72d5b5969c3b48576647",
    "research/analyst_revisions_v2/specs/arv2_stock_walk_forward_folds.structural.json": "fecd984ad937fed57b860b15fdcb9cc994ff59ab62c3b72d5160ab62b342953c",
    "research/analyst_revisions_v2_qc/accepted_risk_delta_order_package.py": "f0465c6bc52722a51cfa8a97700f99e2f87476a195ed88e071aa4a265eacd365",
    "research/analyst_revisions_v2_qc/accepted_risk_latest_order_package.py": "817206750b0ab308a0aecbc1fe6f564cd969eaf8248a5ed9102db8660d464948",
    "research/analyst_revisions_v2_qc/accepted_risk_massive_delta.py": "f8c8f42bb4a2619ede45d5d34648b656732324cbd8de68b957a99cd4599c522f",
    "research/analyst_revisions_v2_qc/accepted_risk_massive_ratings_delta.py": "9c0ec2eede6daeabc03d150c1146d595026fe724028ead856edce9f29b872390",
    "research/analyst_revisions_v2_qc/accepted_risk_massive_ratings_delta_v2.py": "ba736022c91e759e6fce899e8e8b85286bfa9113ce3a063c5ec12fff7b2d5138",
    "research/analyst_revisions_v2_qc/accepted_risk_october_order_package.py": "655eec765a8b99d489881f7de7ddc339ab6b2c0bb0470feb814c6ef005d03c0a",
    "research/analyst_revisions_v2_qc/accepted_risk_preliminary_package.py": "794bdcb8ed3be34b625030ac8a0cd0d65aeaf7dd14e58d081d40f495528e0824",
    "research/analyst_revisions_v2_qc/firm_ontology_owner_decision.py": "9115f777ac9ebe654edbfe816ce3a7927b4dcc8c11aefcc5376c53a690e4e345",
    "research/analyst_revisions_v2_qc/firm_ontology_proposal_generator.py": "d12e77db30cf1dd30d657a5716e1433ba215a41e1873bcd48a3dbb8cba1a2a03",
    "research/analyst_revisions_v2_qc/physical_accepted_risk_archive.py": "f8da20bb28296a942cb1d9219b2fb3056a33af774cf55276c1788aa8983d3b4b",
    "research/analyst_revisions_v2_qc/physical_firm_ontology_review_packet.py": "dfed48da54c605f7ca8a5295edbb419b94328bde43e95339eef1636f063d64e8",
    "research/analyst_revisions_v2_qc/production_evidence_composer.py": "17fa2c3c994a781f0df2fe945f0cd0af2cbfe718d72a9b9d10d2a5d4085e6cb5",
    "scripts/arv2_keychain_connections.py": "bd9c0863c484810b8cf7a02e46551ed63f99ecec7bb4f322b91270fad7a28227",
    "scripts/arv2_massive_capture_diagnostic.py": "8c571988252d5f1ee9364f98d6a163d8da22e88023730f829d11eb7cb1a7ba1a",
    "scripts/arv2_massive_capture_failure.py": "737c3a0cd5b33e42eb906a84e817a74037a6c4e55c4d534d390a19947624edc6",
    "scripts/arv2_october_input_failure.py": "d0d90fb4a80bf649a99cc4e11d63937f49e635559d364664abf6c115b6c66f3c",
    "scripts/build_arv2_delta_order_input_package.py": "7dc231917ffa47e585dd2f4d2bc751763fe05303e4f4b3167bbe8aa079484842",
    "scripts/capture_arv2_massive.py": "e67cabf821a3df804d157c790b6df1c7cd1a13a7c50d717a48b55b3d32e5e906",
    "scripts/capture_arv2_massive_ratings_delta.py": "14936a7a1b493b28554eae0a9dbddfa07363d61fa9ce5d461580ae1b009ce818",
    "scripts/diagnose_arv2_r297_authentication.py": "850864cb1d166526bd73144dbdfa5efce37d46dd9ffeadddd2037a7e29b9d8f9",
    "scripts/run_arv2_forward_data_quality.py": "b82475a9ddbad73b4d38c7469f881f50b23bc0bbf7f57cfbd59dbcc927372557",
    "scripts/run_arv2_keychain_connection_check.py": "399d898d05f8696d4e5a1e6df25053d2449f96646fd870bf4dd2d75cd748af80",
    "scripts/run_arv2_massive_oct12_diagnostic.py": "137743f30acd78aafb768114446f2b20cecec0bbac12fdc995233accf2911860",
})
MAX_REPORT_BYTES = 16 * 1024


class InputOperationError(ValueError):
    pass


def _require(condition):
    if not condition:
        raise InputOperationError("input_operation_refused")


def profile_record():
    return {"schema": SCHEMA, "root": str(ROOT), "branch": BRANCH,
        "python": str(PYTHON), "control": str(CONTROL), "retained": str(RETAINED),
        "tail": str(TAIL), "tail_source": str(TAIL_SOURCE), "predecessor": str(PREDECESSOR),
        "retained_manifest_sha256": diagnostic.MANIFEST_SHA256,
        "retained_manifest_bytes": diagnostic.MANIFEST_BYTES,
        "deadline_seconds": DEADLINE_SECONDS, "source_pins": dict(SOURCE_PINS),
        "max_report_bytes": MAX_REPORT_BYTES,
        "source_profile_sha256": recovered.SOURCE_PROFILE_SHA256,
        "composer_profile_sha256": october.PROFILE_SHA256,
        "native_network_denial": "required_external_sandbox-exec_deny_network",
        "original_capture_accepted": False, "provider_contact_authorized": False,
        "formal_source_admitted": False, "backtest_ready": False,
        "purpose": "exact_retained_identical_repeat_idempotence_then_preserved_prefix_October_package"}


def profile_sha256():
    return hashlib.sha256(helpers.canonical_json_bytes(profile_record())).hexdigest()


def _preflight(head, caller, deadline):
    _require(sys.platform == "darwin" and os.name == "posix" and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE)
    _require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head) is not None)
    helpers.require_sha256(caller, "caller")
    _require(len(SOURCE_PINS) >= 20)
    for args, expected in ((["rev-parse", "--show-toplevel"], str(ROOT)),
            (["branch", "--show-current"], BRANCH), (["rev-parse", "HEAD"], head),
            (["status", "--porcelain"], "")):
        result = subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
        _require(result.returncode == 0 and not result.stderr
            and result.stdout.decode("ascii").strip() == expected)
    for relative, expected in SOURCE_PINS.items():
        helpers.require_sha256(expected, "source pin")
        _require(helpers._source_digest(ROOT / relative) == expected)
    _require(helpers._source_digest(SOURCE) == caller)
    capture._require_dirfd_support()
    helpers._remaining(deadline)


def _claim(head, caller):
    capture._require_operational_artifact_scope(CONTROL)
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="October operation parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "October operation")
        claim, _, identity = transport._write_held(directory, "claim.json", {
            "schema": SCHEMA, "profile_sha256": profile_sha256(), "expected_head": head,
            "caller_sha256": caller, "claimed_at": helpers._utc_now(), "attempt_consumed": True})
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "October operation")
        return directory, claim, identity
    except BaseException:
        for fd in (claim, directory):
            if fd is not None:
                os.close(fd)
        raise
    finally:
        os.close(parent)


def _check(directory, name, fd, identity):
    _require(helpers._identity(helpers._file_metadata(fd)) == identity)
    helpers._named_file(directory, name, fd)
    capture._require_reopened_artifact_identity(CONTROL, directory)


def _compose(deadline, stage):
    """All opaque authorities stay inside this process; only finite pins leave."""
    stage[0] = "retained_source_reauthentication"
    fresh = recovered.authenticate_retained_capture(RETAINED,
        expected_manifest_sha256=diagnostic.MANIFEST_SHA256,
        expected_manifest_byte_count=diagnostic.MANIFEST_BYTES)
    helpers._remaining(deadline)
    stage[0] = "predecessor_package_authentication"
    predecessor = latest.load_latest_order_input_package(
        PREDECESSOR / ("arv2-preliminary-qc-package-" + october.EXPECTED_PREDECESSOR_PACKAGE_SHA256[:24]),
        expected_package_sha256=october.EXPECTED_PREDECESSOR_PACKAGE_SHA256,
        lineage_path=PREDECESSOR / ("arv2-latest-lineage-" + october.EXPECTED_PREDECESSOR_LINEAGE_SHA256) / "lineage.json",
        expected_lineage_sha256=october.EXPECTED_PREDECESSOR_LINEAGE_SHA256)
    stage[0] = "historical_archive_authentication"
    parent = historical.load_physical_accepted_risk_archive(
        archive_path=historical.PARENT_ARCHIVE_PATH, source_artifact_path=historical.PARENT_SOURCE_PATH,
        expected_archive_sha256=historical.PARENT_ARCHIVE_SHA256,
        expected_source_manifest_sha256=historical.PARENT_SOURCE_MANIFEST_SHA256)
    prior = historical.load_physical_accepted_risk_archive(
        archive_path=historical.DELTA_ARCHIVE_PATH, source_artifact_path=historical.DELTA_SOURCE_PATH,
        expected_archive_sha256=historical.DELTA_ARCHIVE_SHA256,
        expected_source_manifest_sha256=historical.DELTA_SOURCE_MANIFEST_SHA256)
    tail = historical.load_physical_accepted_risk_archive(
        archive_path=TAIL, source_artifact_path=TAIL_SOURCE,
        expected_archive_sha256=october.EXPECTED_TAIL_ARCHIVE_SHA256,
        expected_source_manifest_sha256=october.EXPECTED_TAIL_SOURCE_MANIFEST_SHA256)
    helpers._remaining(deadline)
    stage[0] = "frozen_firm_global_reconstruction"
    packet = historical.load_physical_firm_ontology_review_packet(
        archive_path=historical.FIRM_PACKET_PATH, expected_packet_sha256=historical.FIRM_PACKET_SHA256,
        accepted_risk_archive=parent, preopen_seed_archive=None)
    # Retain this newly scoped reconstruction; no TemporaryDirectory cleanup.
    proposal = historical.build_firm_ontology_proposal(review_packet=packet, output_root=CONTROL / "firm-proposal")
    decision = historical.build_firm_ontology_owner_decision(review_packet=packet, proposal=proposal)
    firms = historical.build_section72_owner_waived_firm_admission(decision=decision, review_packet=packet)
    contract = historical._global_contract()
    helpers._remaining(deadline)
    stage[0] = "october_composition"
    value = october.build_october_order_input_package(predecessor=predecessor,
        parent_archive=parent, prior_delta_archive=prior, tail_archive=tail, ratings_delta=fresh,
        firm_admission=firms, global_contract=contract, output_root=CONTROL / "package")
    sidecar = october.persist_october_order_input_lineage(value, CONTROL / "package")
    helpers._remaining(deadline)
    stage[0] = "new_package_authentication"
    checked = october.load_october_order_input_package(value.package.package_path,
        expected_package_sha256=value.package.package_sha256,
        lineage_path=sidecar, expected_lineage_sha256=value.lineage_sha256)
    _require(checked.lineage_bytes == value.lineage_bytes)
    package = checked.package
    activation = package.upload_objects[-1]
    result = {"package_path": str(package.package_path), "package_sha256": package.package_sha256,
        "lineage_path": str(sidecar), "lineage_sha256": checked.lineage_sha256,
        "activation_key": activation.object_store_key, "activation_sha256": activation.content_sha256,
        "activation_byte_count": activation.byte_count, "total_upload_byte_count": package.total_upload_byte_count,
        "session_count": checked.lineage["session_count"],
        "recovered_tail_contribution_count": checked.recovered_tail_contribution_count,
        "fresh_contribution_count": checked.fresh_contribution_count,
        "combined_contribution_count": dict(package.contribution_census)["combined_contribution_count"],
        "decision_cutoff_session": october.DECISION_CUTOFF_SESSION,
        "valuation_end_session": october.VALUATION_END_SESSION}
    helpers._remaining(deadline)
    return result


def _failure(exc):
    # Exact finite types only; never str/repr an exception or its opaque args.
    classified = failure.classify_failure(exc)
    if classified is not None:
        return classified
    if type(exc) is InputOperationError:
        return "input_operation_error", "input_operation_refused"
    if type(exc) is recovered.RatingsDeltaV2Error:
        args = BaseException.args.__get__(exc)
        code = args[0] if type(args) is tuple and len(args) == 1 and type(args[0]) is str and len(args[0]) <= 512 else None
        return "ratings_delta_v2_error", code if code in recovered.FINITE_REFUSAL_CODES else "unknown"
    return diagnostic._failure(exc)


def _run(head, caller, deadline):
    directory = claim = report_fd = None
    consumed, stage = False, ["preflight"]
    terminal, result = "input_operation_refused", None
    exception_type = refusal_code = None
    started = helpers._utc_now()
    try:
        _preflight(head, caller, deadline)
        consumed, stage[0] = None, "claim"
        directory, claim, identity = _claim(head, caller)
        consumed = True
        _check(directory, "claim.json", claim, identity)
        result = _compose(deadline, stage)
        terminal = "october_package_prepared"
    except BaseException as exc:
        result = None
        exception_type, refusal_code = _failure(exc)
    try:
        helpers._remaining(deadline)
        if directory is None:
            print(helpers.canonical_json_bytes({"schema": SCHEMA, "terminal": terminal,
                "stage": stage[0], "attempt_consumed": consumed, "exception_type": exception_type,
                "refusal_code": refusal_code, "backtest_ready": False}).decode())
            return 2
        _check(directory, "claim.json", claim, identity)
        report = {"schema": SCHEMA, "profile_sha256": profile_sha256(), "expected_head": head,
            "caller_sha256": caller, "started_at": started, "finished_at": helpers._utc_now(),
            "terminal": terminal, "stage": stage[0], "exception_type": exception_type,
            "refusal_code": refusal_code, "package": result, "attempt_consumed": True,
            "original_capture_accepted": False, "formal_source_admitted": False,
            "provider_contact_authorized": False, "provider_request_count": None,
            "point_in_time_proven": False, "backtest_ready": False,
            "paper_or_live_ready": False, "qc_calls": 0, "outcome_reads": 0}
        _require(len(helpers.canonical_json_bytes(report)) <= MAX_REPORT_BYTES)
        report_fd, payload, report_identity = transport._write_held(directory, "report.json", report)
        _check(directory, "claim.json", claim, identity)
        _check(directory, "report.json", report_fd, report_identity)
        helpers._remaining(deadline)
        print(helpers.canonical_json_bytes({"report": report,
            "report_sha256": hashlib.sha256(payload).hexdigest(), "report_bytes": len(payload)}).decode())
        return 0 if terminal == "october_package_prepared" else 2
    except BaseException:
        print('{"terminal":"input_publication_ambiguous","backtest_ready":false}')
        return 2
    finally:
        for fd in (report_fd, claim, directory):
            if fd is not None:
                os.close(fd)


def run(head, caller):
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            return _run(head, caller, deadline)
    except BaseException:
        print('{"terminal":"input_parent_ambiguous","backtest_ready":false}')
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    args = parser.parse_args(argv)
    return run(args.expected_head, args.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
