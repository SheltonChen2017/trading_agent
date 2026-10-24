"""Isolated owned-reference qualification; no price, provider or QC access.

Every retained TICKERS/ACTIONS byte and row is verified. Only the explicitly
named action-value fields are Decimal-validated; none is converted to a return,
terminal payoff or entitlement. Present metadata is not historical/PIT proof.
The private dates-only probe plan is a discovery plan, not a dispatch grant.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import errno
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

from research import insider_buying_sharadar_reference_cohort_runner as reference
from research import insider_buying_earnings_archive_assessment_runner as custody
from research.insider_buying_eodhd_earnings_demo import FALSE_FLAGS, EodhdDemoError, _read_leaf
from research.insider_buying_provider_metadata_audit import _exclusive_json


SCHEMA = "insider-sharadar-delisting-qualification-v1"
PLAN_SCHEMA = "insider-sharadar-sep-dates-probe-plan-v1"
LANE_ROOT, LANE_BRANCH = custody.LANE_ROOT, custody.LANE_BRANCH
CAPTURE_ROOT = reference.CAPTURE_ROOT
CAPTURE_MANIFEST_SHA256 = reference.CAPTURE_MANIFEST_SHA256
OUTPUT_PARTS = ("artifacts", "insider_buying", "sharadar_delisting_qualification_v1")
AUDIT_ID = "ib-sharadar-delisting-qualification-20261024-once"
SOURCE_SEED = "research/insider_buying_sharadar_delisting_qualification.py"
WORKER_FLAGS = ("-I", "-S", "-B", "-X", "pycache_prefix=/var/empty/insider-buying-no-bytecode")
CASE_LABELS = ("active_common", "delisted_common", "secondary_common", "ticker_reuse_related")
PRICE_TABLES = frozenset({"stocks", "SEP"})
READINESS_KEYS = tuple(dict.fromkeys((*FALSE_FLAGS, "backtesting_ready", "pit_identity_verified")))
MAX_REPORT_BYTES = 512 * 1024**2
MAX_PLAN_BYTES = 4 * 1024**2
ACTION_COLUMNS = (*reference.cohort.ACTION_COLUMNS, "value")
COMMON_CATEGORIES = frozenset(
    nation + " Common Stock" + suffix
    for nation in ("Domestic", "Canadian", "Foreign")
    for suffix in ("", " Primary Class", " Secondary Class")
)
CASH_ACTIONS = frozenset({"delist", "delisted", "delistedbankruptcy", "acquisitioncash", "acquisitionelectcash"})
STOCK_ACTIONS = frozenset({"acquisitionstock", "acquisitionelectstock"})
SIC_ACTIONS = frozenset({"sicchangefrom", "sicchangeto"})
EXCHANGE_ACTIONS = frozenset({"exchangefrom", "exchangeto", "exchangechangefrom", "exchangechangeto"})
ELECTION_ACTIONS = frozenset({"acquisitionelectcash", "acquisitionelectstock"})
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-^/=]{0,63}\Z")
_NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,12})?\Z")


class DelistingQualificationError(ValueError):
    """Fixed refusal codes only; no private source row or OS text."""


def _need(value, code):
    if not value:
        raise DelistingQualificationError(code)


def _readiness():
    return dict.fromkeys(READINESS_KEYS, False)


def _false_readiness(value):
    return type(value) is dict and set(value) == set(READINESS_KEYS) and all(item is False for item in value.values())


def _day(text):
    if type(text) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _action_status(row):
    label, value = row["action"], row["value"]
    if label in EXCHANGE_ACTIONS:
        return "exchange-code-metadata-not-a-price", False
    if label not in CASH_ACTIONS | STOCK_ACTIONS | SIC_ACTIONS:
        return "unassessed-action-label", False
    if value == "":
        return "missing-value-unresolved", False
    if _NUMBER.fullmatch(value) is None:
        return "invalid-numeric-lexeme", False
    try:
        number = Decimal(value)
    except InvalidOperation:
        return "invalid-numeric-lexeme", False
    if not number.is_finite() or number < 0:
        return "invalid-numeric-value", False
    if label in STOCK_ACTIONS and number <= 0:
        return "nonpositive-share-ratio", False
    if label in SIC_ACTIONS and (number != number.to_integral_value() or number > 9999):
        return "invalid-sic-code", False
    return "numeric-valid-units-and-terminal-meaning-unverified", True


def qualify_metadata(*, ticker_rows, action_rows, source_archives, execution_identity, capture_manifest_sha256):
    """Pure supplied-metadata assessment; caller separately proves byte custody."""
    _need(type(ticker_rows) is list and type(action_rows) is list
          and len(ticker_rows) <= reference.MAX_METADATA_ROWS and len(action_rows) <= reference.MAX_METADATA_ROWS,
          "metadata_row_bound_refused")
    tickers, ticker_refusals, actions = [], [], []
    for ordinal, row in enumerate(ticker_rows, 1):
        _need(type(row) is dict and set(row) == {"source_row_ordinal", *reference.cohort.TICKER_COLUMNS}
              and type(row["source_row_ordinal"]) is int and row["source_row_ordinal"] == ordinal
              and all(type(row[key]) is str for key in reference.cohort.TICKER_COLUMNS), "ticker_row_schema_refused")
        reasons = []
        if row["table"] not in PRICE_TABLES: reasons.append("not-owned-stock-price-table")
        if not _TICKER.fullmatch(row["ticker"]): reasons.append("unsupported-current-ticker")
        if re.fullmatch(r"[0-9]{1,20}", row["permaticker"]) is None or int(row["permaticker"]) == 0:
            reasons.append("unsupported-permaticker")
        if row["isdelisted"] not in {"Y", "N"}: reasons.append("unknown-current-delisting-flag")
        if row["category"] not in COMMON_CATEGORIES: reasons.append("not-supported-current-common-category")
        first = _day(row["firstpricedate"])
        if first is None: reasons.append("missing-or-invalid-first-price-date")
        elif first > date(2006, 1, 1): reasons.append("no-early-metadata-price-bound")
        item = {**row, "discovery_refusals": reasons, "historical_identity_verified": False}
        tickers.append(item)
        if reasons: ticker_refusals.append({"source_row_ordinal": ordinal, "reasons": reasons})
    counts = Counter()
    for ordinal, row in enumerate(action_rows, 1):
        _need(type(row) is dict and set(row) == {"source_row_ordinal", *ACTION_COLUMNS}
              and type(row["source_row_ordinal"]) is int and row["source_row_ordinal"] == ordinal
              and all(type(row[key]) is str for key in ACTION_COLUMNS), "action_row_schema_refused")
        status, interpreted = _action_status(row)
        if _day(row["date"]) is None: status = "invalid-action-date-unresolved"
        counts[status] += 1
        actions.append({**row, "qualification": status, "numeric_value_validated": interpreted,
                        "election_unresolved": row["action"] in ELECTION_ACTIONS,
                        "terminal_payoff_verified": False})
    eligible = sorted((row for row in tickers if not row["discovery_refusals"]),
                      key=lambda row: (row["ticker"], row["permaticker"], row["source_row_ordinal"]))
    collisions = defaultdict(set)
    for row in tickers:
        if (row["table"] in PRICE_TABLES and re.fullmatch(r"[0-9]{1,20}", row["permaticker"]) is not None
                and int(row["permaticker"]) > 0):
            collisions[row["ticker"]].add(row["permaticker"])
    predicates = {
        "active_common": lambda row: row["isdelisted"] == "N",
        "delisted_common": lambda row: row["isdelisted"] == "Y",
        "secondary_common": lambda row: row["category"].endswith(" Secondary Class"),
        "ticker_reuse_related": lambda row: len(collisions[row["ticker"]]) > 1,
    }
    cases, unavailable = [], []
    for label in CASE_LABELS:
        chosen = next((row for row in eligible if predicates[label](row)), None)
        if chosen is None:
            unavailable.append(label)
        else:
            cases.append({"case_label": label, "current_ticker": chosen["ticker"],
                          "permaticker": chosen["permaticker"], "source_row_ordinal": chosen["source_row_ordinal"],
                          "table": chosen["table"]})
    requested = sorted({row["current_ticker"] for row in cases})
    _need(len(requested) <= 6, "probe_plan_ticker_bound_refused")
    plan = {"schema": PLAN_SCHEMA, "audit_id": AUDIT_ID, "execution_identity": execution_identity,
            "source_inventory_sha256": execution_identity["source_inventory_sha256"],
            "capture_manifest_sha256": capture_manifest_sha256, "source_archives": source_archives,
            "cases": cases, "unavailable_cases": unavailable, "requested_tickers": requested,
            "request": {"dataset": "stocks", "format": "csv", "ticker": ",".join(requested),
                        "date_gte": "2005-01-01", "date_lte": "2026-06-30", "fields": ["ticker", "date", "lastupdated"],
                        "sort": "date.asc", "limit": 100000, "maximum_attempts": 1},
            "metadata_discovery_only": True, "early_buffer_is_availability_probe_only": True,
            "readiness": _readiness()}
    report = {"schema": SCHEMA, "capture_manifest_sha256": capture_manifest_sha256, "source_archives": source_archives,
              "ticker_inventory": tickers, "ticker_refusals": ticker_refusals, "action_inventory": actions,
              "action_qualification_counts": dict(sorted(counts.items())),
              "counts": {"ticker_rows": len(tickers), "ticker_refusal_rows": len(ticker_refusals),
                         "action_rows": len(actions), "numeric_values_validated": sum(row["numeric_value_validated"] for row in actions),
                         "unresolved_election_rows": sum(row["election_unresolved"] for row in actions),
                         "planned_tickers": len(requested)},
              "unresolved": ["terminal-cash-share-consideration-not-verified", "election-choices-not-resolved",
                             "contingent-value-rights-not-covered", "complete-delisting-return-not-verified",
                             "historical-share-class-and-availability-not-verified"], "readiness": _readiness()}
    return report, plan


def _identity(expected_head):
    identity = custody._identity(expected_head)
    _need(SOURCE_SEED in identity["source_sha256"], "qualification_source_closure_incomplete")
    return identity


def _load_capture(path, manifest_sha):
    held = reference._HeldCapture(path)
    try:
        _need(held.names == {"manifest.json", "manifest.sha256", *reference.supplied.FILES}, "capture_inventory_refused")
        manifest_raw = held.open("manifest.json", 1024**2).read(1024**2 + 1)
        _need(reference._sha(manifest_raw) == manifest_sha, "capture_manifest_anchor_refused")
        _need(held.open("manifest.sha256", 65).read(66) == (manifest_sha + "\n").encode(), "capture_sidecar_refused")
        manifest, entries = reference.cohort._manifest(manifest_raw, manifest_sha)
        projections, archives = {}, {}
        for dataset, columns in (("tickers", reference.cohort.TICKER_COLUMNS), ("actions", ACTION_COLUMNS)):
            entry = entries[dataset]
            stream = held.open(entry["archive_file"], reference.supplied.MAX_ARCHIVE)
            raw = reference._project_archive(stream, entry, dataset=dataset, columns=columns,
                                            schema=SCHEMA + "/" + dataset, manifest_sha=manifest_sha)
            body = custody._json(raw)
            projections[dataset] = body["rows"]
            archives[dataset] = {"archive_sha256": entry["archive_sha256"], "archive_bytes": entry["archive_byte_count"],
                                 "member_sha256": entry["members"][0]["content_sha256"],
                                 "member_bytes": entry["members"][0]["uncompressed_byte_count"], "source_row_count": entry["row_count"]}
        held.check()
        return held, manifest_raw, entries, projections, archives
    except BaseException:
        held.close()
        raise


def _recheck_capture(held, entries, manifest_sha):
    held.check()
    for name, stream, _, cap in held.handles:
        expected = (manifest_sha if name == "manifest.json" else reference._sha((manifest_sha + "\n").encode())
                    if name == "manifest.sha256" else next(item["archive_sha256"] for item in entries.values() if item["archive_file"] == name))
        _need(reference._hash_stream(stream, cap)[0] == expected, "capture_content_changed")
    held.check()


def _worker(*, root, identity, capture_path, manifest_sha, fixture_only=False):
    _need(type(fixture_only) is bool, "fixture_mode_refused")
    if fixture_only:
        def outside(value, actual):
            named, protected = str(value.resolve()).casefold(), str(actual).casefold()
            return (named != protected and not named.startswith(protected + "/")
                    and not protected.startswith(named.rstrip("/") + "/"))
        _need(not custody._fixture_root_is_lane(root) and outside(root, LANE_ROOT)
              and outside(capture_path, CAPTURE_ROOT) and outside(capture_path, LANE_ROOT), "fixture_actual_inputs_refused")
    else:
        _need(root == LANE_ROOT and capture_path == CAPTURE_ROOT and manifest_sha == CAPTURE_MANIFEST_SHA256,
              "actual_scope_requires_fixed_inputs")
    custody._effective_denial(require_fork=not fixture_only)
    if not fixture_only:
        try:
            pid = os.posix_spawn("/usr/bin/security", ("/usr/bin/security", "-h"), {},
                                 file_actions=((os.POSIX_SPAWN_CLOSE, 1), (os.POSIX_SPAWN_CLOSE, 2)))
        except OSError as exc:
            _need(exc.errno in {errno.EPERM, errno.EACCES}, "keychain_exec_denial_not_observed")
        else:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
            os.waitpid(pid, 0)
            raise DelistingQualificationError("keychain_exec_denial_not_observed")
    _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
    output = custody._Chain(root, (*OUTPUT_PARTS, AUDIT_ID))
    held = None
    try:
        _need(os.listdir(output.fd) == [], "output_cannot_resume_or_overwrite")
        if not fixture_only:
            outside = root.joinpath(*OUTPUT_PARTS, "isolation-" + AUDIT_ID + ".probe")
            try: fd = os.open(outside, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except OSError as exc: _need(exc.errno in {errno.EPERM, errno.EACCES}, "outside_write_denial_not_observed")
            else:
                os.close(fd)
                raise DelistingQualificationError("outside_write_denial_not_observed")
        held, manifest_raw, entries, projections, archives = _load_capture(capture_path, manifest_sha)
        report, plan = qualify_metadata(ticker_rows=projections["tickers"], action_rows=projections["actions"],
                                       source_archives=archives, execution_identity=identity, capture_manifest_sha256=manifest_sha)
        report_raw, plan_raw = reference._canonical(report), reference._canonical(plan)
        _recheck_capture(held, entries, manifest_sha)
        _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
        reference._disk_reserve(output.fd)
        reference._publish(output.fd, "qualification.json", report_raw, MAX_REPORT_BYTES)
        reference._publish(output.fd, "probe-plan.json", plan_raw, MAX_PLAN_BYTES)
        receipt = {"schema": SCHEMA, "audit_id": AUDIT_ID, "fixture_only": fixture_only,
                   "execution_identity": identity, "source_inventory_sha256": identity["source_inventory_sha256"],
                   "capture_manifest_sha256": manifest_sha, "source_archives": archives,
                   "qualification_sha256": reference._sha(report_raw), "plan_sha256": reference._sha(plan_raw),
                   "counts": report["counts"], "effective_process_tree_network_denial": True,
                   "effective_process_fork_denial": not fixture_only,
                   "effective_keychain_exec_denial": not fixture_only,
                   "writes_confined_to_fresh_output_by_launcher": not fixture_only,
                   "provider_dispatches": 0, "credential_reads": 0, "fundamentals_decoded": False,
                   "price_or_return_values_read": False, "looks_jobs_backtests": [0, 0, 0], "readiness": _readiness()}
        _recheck_capture(held, entries, manifest_sha)
        _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
        _exclusive_json(output.fd, "complete.json", receipt)
        _recheck_capture(held, entries, manifest_sha)
        output.recheck()
        _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
        _need(set(os.listdir(output.fd)) == {"qualification.json", "probe-plan.json", "complete.json"}, "publication_inventory_refused")
        return {"schema": SCHEMA, "audit_id": AUDIT_ID, "fixture_only": fixture_only,
                "complete_sha256": reference._sha(reference._canonical(receipt)), "plan_sha256": receipt["plan_sha256"],
                "qualification_sha256": receipt["qualification_sha256"], "counts": report["counts"], "readiness": _readiness()}
    finally:
        if held is not None: held.close()
        output.close()


def _verify_publication(*, root, identity, result, manifest_sha, fixture_only=False):
    # Only newly published OUTPUTS settle macOS UF_TRACKED ctime updates.
    # Every held byte image is rehashed after each read and at the final check;
    # the independently anchored raw SOURCE hold remains strict (default mode).
    held = reference._HeldCapture(root.joinpath(*OUTPUT_PARTS, AUDIT_ID), private=True, settle_ctime=True)
    bound = []
    def recheck():
        held.check()
        for stream, cap, expected in bound:
            _need(reference._hash_stream(stream, cap)[0] == expected, "parent_output_content_changed")
        held.check()
    def bind(name, cap, expected, *, decode_bytes):
        recheck()
        stream = held.open(name, cap)
        _need(reference._hash_stream(stream, cap)[0] == expected, "parent_output_hash_refused")
        bound.append((stream, cap, expected))
        raw = None
        if decode_bytes:
            stream.seek(0)
            raw = stream.read(cap + 1)
            _need(0 < len(raw) <= cap and reference._sha(raw) == expected, "parent_output_hash_refused")
        recheck()
        return raw
    try:
        _need(held.names == {"qualification.json", "probe-plan.json", "complete.json"}, "parent_output_inventory_refused")
        complete_raw = bind("complete.json", MAX_PLAN_BYTES, result["complete_sha256"], decode_bytes=True)
        receipt = custody._json(complete_raw)
        bind("qualification.json", MAX_REPORT_BYTES, receipt["qualification_sha256"], decode_bytes=False)
        plan_raw = bind("probe-plan.json", MAX_PLAN_BYTES, receipt["plan_sha256"], decode_bytes=True)
        # The trusted parent hashes the private qualification bytes only. It
        # must not decode the action-value inventory outside the denied worker.
        plan = custody._json(plan_raw)
        count_fields = {"ticker_rows", "ticker_refusal_rows", "action_rows", "numeric_values_validated",
                        "unresolved_election_rows", "planned_tickers"}
        _need(receipt["schema"] == SCHEMA and receipt["audit_id"] == AUDIT_ID and receipt["fixture_only"] is fixture_only
              and receipt["execution_identity"] == plan["execution_identity"] == identity
              and receipt["source_inventory_sha256"] == plan["source_inventory_sha256"] == identity["source_inventory_sha256"]
              and receipt["capture_manifest_sha256"] == plan["capture_manifest_sha256"] == manifest_sha
              and receipt["source_archives"] == plan["source_archives"]
              and type(receipt["counts"]) is dict and set(receipt["counts"]) == count_fields
              and all(type(value) is int and value >= 0 for value in receipt["counts"].values())
              and receipt["counts"] == result["counts"]
              and receipt["counts"]["ticker_rows"] == receipt["source_archives"]["tickers"]["source_row_count"]
              and receipt["counts"]["action_rows"] == receipt["source_archives"]["actions"]["source_row_count"]
              and receipt["counts"]["ticker_refusal_rows"] <= receipt["counts"]["ticker_rows"]
              and receipt["counts"]["numeric_values_validated"] <= receipt["counts"]["action_rows"]
              and receipt["counts"]["unresolved_election_rows"] <= receipt["counts"]["action_rows"]
              and receipt["counts"]["planned_tickers"] == len(plan["requested_tickers"]) <= 6
              and receipt["plan_sha256"] == result["plan_sha256"] and receipt["qualification_sha256"] == result["qualification_sha256"]
              and all(_false_readiness(value) for value in (receipt["readiness"], plan["readiness"], result["readiness"]))
              and receipt["effective_process_tree_network_denial"] is True
              and receipt["effective_process_fork_denial"] is (not fixture_only)
              and receipt["effective_keychain_exec_denial"] is (not fixture_only)
              and receipt["writes_confined_to_fresh_output_by_launcher"] is (not fixture_only)
              and receipt["provider_dispatches"] == receipt["credential_reads"] == 0
              and receipt["fundamentals_decoded"] is False and receipt["price_or_return_values_read"] is False
              and receipt["looks_jobs_backtests"] == [0, 0, 0], "parent_publication_refused")
        recheck()
    finally:
        held.close()


def run_actual_qualification(*, expected_head):
    identity = _identity(expected_head)
    output = custody._Chain(LANE_ROOT, (*OUTPUT_PARTS, AUDIT_ID), create=True, exclusive_last=True)
    output.close()
    policy = custody._policy(LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)) + '(deny process-exec (literal "/usr/bin/security"))'
    bootstrap = ("import sys,runpy;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");"
                 "runpy.run_module('research.insider_buying_sharadar_delisting_qualification',run_name='__main__')")
    command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
               sys.executable, *WORKER_FLAGS, "-c", bootstrap,
               "--worker", "--expected-head", expected_head]
    launched = subprocess.run(command, cwd=LANE_ROOT, input=reference._canonical(identity), capture_output=True, check=False, timeout=1800)
    _need(_identity(expected_head) == identity, "parent_source_changed")
    _need(launched.returncode == 0 and not launched.stderr, "worker_refused_private_outputs_preserved")
    result = custody._json(launched.stdout.strip())
    _verify_publication(root=LANE_ROOT, identity=identity, result=result, manifest_sha=CAPTURE_MANIFEST_SHA256)
    _need(_identity(expected_head) == identity, "parent_source_changed")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            _need(Path.cwd() == LANE_ROOT, "designated_lane_required")
            _need(sys.flags.isolated == 1 and sys.flags.no_user_site == 1 and sys.flags.no_site == 1
                  and sys.flags.dont_write_bytecode == 1
                  and sys.pycache_prefix == "/var/empty/insider-buying-no-bytecode", "isolated_worker_interpreter_required")
            identity = custody._json(sys.stdin.buffer.read(MAX_PLAN_BYTES + 1))
            _need(identity.get("root") == str(LANE_ROOT) and identity.get("branch") == LANE_BRANCH
                  and identity.get("head") == args.expected_head and identity.get("clean") is True
                  and SOURCE_SEED in identity.get("source_sha256", {})
                  and identity.get("source_inventory_sha256") == reference._sha(reference._canonical(identity["source_sha256"])),
                  "parent_identity_refused")
            result = _worker(root=LANE_ROOT, identity=identity, capture_path=CAPTURE_ROOT,
                             manifest_sha=CAPTURE_MANIFEST_SHA256)
        else:
            result = run_actual_qualification(expected_head=args.expected_head)
        print(reference._canonical(result).decode())
        return 0
    except (DelistingQualificationError, reference.SharadarCohortRunnerError, reference.cohort.SharadarReferenceCohortError,
            reference.supplied.SuppliedSharadarAuditError, custody.ArchiveAssessmentRunnerError, EodhdDemoError,
            OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError):
        print('{"disposition":"offline_delisting_qualification_refused_outputs_preserved"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
