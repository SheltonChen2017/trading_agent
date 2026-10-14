"""Invented legacy observations only: no actual QC account/job IDs or outcomes."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import unittest

from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift.evaluation import EvaluationError, FIXTURE_SHA256
from research.guidance_revision_drift.persistence import canonical_object
from research.guidance_revision_drift.recovery_preparation import (
    HISTORICAL_CYCLE_ID, HISTORICAL_PUBLICATION_COMMIT, HistoricalCycleClosure,
    MAX_LEGACY_BYTES, MAX_LEGACY_LINE_BYTES, MAX_LEGACY_RECORDS,
    RECOVERY_IDENTITY_FIELDS, RecoveryPreparation,
)


def records():
    rows = []
    context = {"candidate_sha256": CANDIDATE_SHA256, "fixture_sha256": FIXTURE_SHA256,
               "bundle_sha256": "b" * 64, "runtime_source_sha256": "c" * 64}

    def add(kind, **fields):
        rows.append({"kind": kind, "at": f"2025-01-02T00:{len(rows):02d}:00+00:00", **fields})

    def response(endpoint, number):
        add("response", endpoint=endpoint, file=f"{number:032x}.json", http_status=200,
            raw_response_sha256=f"{number:064x}")

    add("authorization", cycle=HISTORICAL_CYCLE_ID, empirical_allowed=False,
        external_human_authorization="Invented supplied waiver observation; not authorization proof",
        installations_allowed=False, maximum_unsuccessful_attempts=3,
        producing_source_commit="a" * 40, projectId=123, project_sha256="1" * 64,
        real_data_allowed=False, review_commit=None, review_waived_by_owner=True,
        runtime_context=context, source_commit="1" * 40, source_manifest_sha256="1" * 64)
    for number in range(1, 4):
        if number > 1:
            add("source_epoch", attempt=number, external_owner_waiver_retained=True,
                project_sha256=str(number) * 64, runtime_context=deepcopy(context),
                source_commit=str(number) * 40, source_manifest_sha256=str(number) * 64)
        add("compile_intent", attempt=number, project_sha256=str(number) * 64,
            source_manifest_sha256=str(number) * 64)
        response("compile/create", number * 10)
        add("compile_ack", attempt=number, compileId=f"SYN_compile_{number}", signature="SYN",
            signatureOrder=["project/main.py"], state="InQueue")
        response("compile/read", number * 10 + 1)
        add("compile_observation", attempt=number, compileId=f"SYN_compile_{number}", errors=None,
            logs=["Invented BuildSuccess"], state="BuildSuccess")
        add("run_intent", attempt=number, backtestName=f"SYN invented attempt {number}",
            compileId=f"SYN_compile_{number}")
        response("backtests/create", number * 10 + 2)
        add("run_ack", attempt=number, backtestId=f"SYN_run_{number}", status="In Queue...")
        response("backtests/read", number * 10 + 3)
        add("run_observation", attempt=number, backtestId=f"SYN_run_{number}", completed=True,
            error="Invented initialization error", hasInitializeError=True, progress=1,
            serverStatistics={"LEAN Version": "LEAN-SYN-1"}, stacktrace="Invented", status="Runtime Error")
        add("terminal", attempt=number, backtestId=f"SYN_run_{number}", status="Runtime Error", unsuccessful=True)
    add("attempt_ceiling", candidate_edits_stopped=True, manual_relaunch_allowed=False, unsuccessful=3)
    return rows


def raw(rows=None):
    return b"\n".join(canonical_object(row) for row in (records() if rows is None else rows)) + b"\n"


def closure(rows=None):
    payload = raw(rows)
    return HistoricalCycleClosure(payload, hash_bytes(payload))


def manifest():
    return {**{name: "d" * 64 for name in RECOVERY_IDENTITY_FIELDS},
            "candidate_sha256": CANDIDATE_SHA256, "fixture_sha256": FIXTURE_SHA256}


def prepared(history=None, identity=None):
    return RecoveryPreparation.from_manifest(closure() if history is None else history,
        manifest() if identity is None else identity, source_commit="e" * 40,
        prior_review_commit="f" * 40, prior_review_record_sha256="a" * 64)


class HistoricalClosureTests(unittest.TestCase):
    def test_complete_legacy_closure_preserves_each_epoch_receipt_and_absent_binding(self):
        result = closure().to_dict()
        self.assertEqual(result["cycle_id"], HISTORICAL_CYCLE_ID)
        self.assertEqual(result["publication_commit"], HISTORICAL_PUBLICATION_COMMIT)
        self.assertEqual((result["unsuccessful_attempts"], result["remaining_manual_attempts"]), (3, 0))
        self.assertIsNone(result["historical_review_commit"])
        self.assertIsNone(result["historical_binding_version"])
        for number, row in enumerate(result["attempts"], 1):
            self.assertEqual(row["source_commit"], str(number) * 40)
            self.assertEqual(row["source_manifest_sha256"], str(number) * 64)
            self.assertEqual(row["project_sha256"], str(number) * 64)
            self.assertEqual(row["compile_id"], f"SYN_compile_{number}")
            self.assertEqual(row["run_id"], f"SYN_run_{number}")
            self.assertEqual((row["compile_status"], row["run_status"], row["status"]),
                             ("BuildSuccess", "Runtime Error", "failed"))
            for offset, receipt in enumerate(("compile_request_receipt", "compile_output_receipt",
                    "run_request_receipt", "run_output_receipt")):
                self.assertEqual(row[receipt]["raw_response_sha256"], f"{number * 10 + offset:064x}")
            self.assertIsNone(row["review_commit"])
            self.assertIsNone(row["binding_version"])
        for name in ("typed_journal_custody_verified", "external_provenance_verified",
                     "owner_authorization_verified", "native_runtime_verified", "qc_upload_allowed", "qc_launch_allowed"):
            self.assertIs(result[name], False)

    def test_immutable_bytes_and_fresh_projection_do_not_expose_caller_mutations(self):
        history = closure()
        original = history.to_dict()
        projected = history.to_dict()
        projected["attempts"][0]["status"] = "completed"
        self.assertEqual(history.to_dict(), original)
        with self.assertRaises(FrozenInstanceError):
            history.events_bytes = b"changed"
        self.assertEqual(history.sha256, closure().sha256)

    def test_changed_truncated_reordered_bytes_refuse_the_retained_raw_anchor(self):
        payload = raw()
        for changed in (payload + b"\n", payload[:-1], payload.replace(b"Runtime Error", b"Completed"),
                        b"\n".join(reversed(payload.splitlines())) + b"\n", bytearray(payload)):
            with self.subTest(type=type(changed).__name__), self.assertRaises(EvaluationError):
                HistoricalCycleClosure(changed, hash_bytes(payload))
        for anchor in ("0" * 63, "A" * 64, True, None):
            with self.subTest(anchor=anchor), self.assertRaises(EvaluationError):
                HistoricalCycleClosure(payload, anchor)
        with self.assertRaises(EvaluationError):
            replace(closure(), publication_commit="0" * 40)

    def test_strict_bounded_json_refuses_duplicates_numbers_and_incomplete_lines(self):
        payload = raw()
        for changed in (payload.replace(b'"kind":"authorization"', b'"kind":"authorization","kind":"authorization"'),
                        payload.replace(b'"projectId":123', b'"projectId":123.0'),
                        payload.replace(b'"projectId":123', b'"projectId":NaN'),
                        payload[:-1], payload.replace(b"\n", b"\r\n"), b"\xff\n", b"\n",
                        b"x" * (MAX_LEGACY_BYTES + 1), b"x" * (MAX_LEGACY_LINE_BYTES + 1) + b"\n",
                        raw([records()[0]] * (MAX_LEGACY_RECORDS + 1))):
            with self.subTest(length=len(changed)), self.assertRaises(EvaluationError):
                HistoricalCycleClosure(changed, hash_bytes(changed))

    def test_missing_duplicate_unknown_and_reordered_observations_refuse_even_new_anchor(self):
        original = records()
        changes = []
        for kind in ("authorization", "compile_intent", "compile_ack", "compile_observation", "run_intent",
                     "run_ack", "run_observation", "terminal", "source_epoch", "attempt_ceiling"):
            index = next(i for i, row in enumerate(original) if row["kind"] == kind)
            missing = deepcopy(original); del missing[index]; changes.append(("missing " + kind, missing))
            duplicate = deepcopy(original); duplicate.insert(index, deepcopy(duplicate[index])); changes.append(("duplicate " + kind, duplicate))
        extra = deepcopy(original); extra[0]["unexpected"] = True; changes.append(("unknown field", extra))
        swapped = deepcopy(original); swapped[2], swapped[3] = swapped[3], swapped[2]; changes.append(("reordered", swapped))
        unknown = deepcopy(original); unknown[2]["kind"] = "recovery_launch"; changes.append(("unknown kind", unknown))
        for label, changed in changes:
            with self.subTest(label=label), self.assertRaises(EvaluationError):
                closure(changed)

    def test_changed_lineage_permissions_ids_and_receipt_hashes_refuse(self):
        cases = [("authorization", "cycle", "SYN-new-cycle"), ("authorization", "review_commit", "e" * 40),
                 ("authorization", "real_data_allowed", True), ("authorization", "maximum_unsuccessful_attempts", 4),
                 ("compile_intent", "source_manifest_sha256", "0" * 64), ("compile_intent", "attempt", True),
                 ("compile_observation", "compileId", "SYN-other"), ("compile_observation", "state", "BuildError"),
                 ("run_intent", "compileId", "SYN-other"), ("run_observation", "status", "Completed"),
                 ("run_observation", "hasInitializeError", False), ("terminal", "unsuccessful", False),
                 ("response", "raw_response_sha256", "bad"), ("response", "http_status", True),
                 ("attempt_ceiling", "manual_relaunch_allowed", True), ("attempt_ceiling", "unsuccessful", 2)]
        for kind, field, value in cases:
            changed = records(); next(row for row in changed if row["kind"] == kind)[field] = value
            with self.subTest(kind=kind, field=field), self.assertRaises(EvaluationError):
                closure(changed)


    def test_each_historical_custody_rule_refuses_alone(self):
        # GDR-CR31-005: every case keeps all other replay rules satisfied, so
        # each isolates one custody guard. The raw-anchor case changes only
        # free text, which replays cleanly, against the original anchor.
        base = records()
        HistoricalCycleClosure(raw(base), hash_bytes(raw(base)))
        def first(rows, kind, attempt=None):
            return next(i for i, row in enumerate(rows) if row["kind"] == kind
                        and (attempt is None or row.get("attempt") == attempt))
        cases = {}
        changed = deepcopy(base)
        changed[0]["external_human_authorization"] += " (edited)"
        cases["raw anchor"] = (raw(changed), hash_bytes(raw(base)))
        changed = deepcopy(base)
        changed[5]["at"] = changed[3]["at"]
        cases["timestamps regressed"] = changed
        changed = deepcopy(base)
        ack, observed = first(changed, "compile_ack", 1), first(changed, "compile_observation", 1)
        changed[ack - 1]["endpoint"], changed[observed - 1]["endpoint"] = "compile/read", "compile/create"
        cases["response endpoint lineage"] = changed
        changed = deepcopy(base)
        changed[first(changed, "compile_ack", 1) - 1]["file"] = "../" + "0" * 26 + ".json"
        cases["response file name"] = changed
        changed = deepcopy(base)
        changed[first(changed, "source_epoch", 2)]["external_owner_waiver_retained"] = False
        cases["waiver not retained"] = changed
        changed = deepcopy(base)
        changed[first(changed, "source_epoch", 2)]["runtime_context"]["bundle_sha256"] = "e" * 64
        cases["epoch runtime context changed"] = changed
        changed = deepcopy(base)
        del changed[first(changed, "source_epoch", 2)]
        intent = changed[first(changed, "compile_intent", 2)]
        intent["project_sha256"] = intent["source_manifest_sha256"] = "1" * 64
        cases["second attempt without a new source epoch"] = changed
        changed = deepcopy(base)
        for kind in ("compile_ack", "compile_observation", "run_intent"):
            changed[first(changed, kind, 2)]["compileId"] = "SYN_compile_1"
        cases["compile id reused"] = changed
        changed = deepcopy(base)
        for kind in ("run_ack", "run_observation", "terminal"):
            changed[first(changed, kind, 2)]["backtestId"] = "SYN_run_1"
        cases["run id reused"] = changed
        changed = deepcopy(base)
        del changed[first(changed, "terminal", 3)]
        cases["ceiling before the third terminal"] = changed
        for label, case in cases.items():
            payload, anchor = case if type(case) is tuple else (raw(case), hash_bytes(raw(case)))
            with self.subTest(case=label), self.assertRaises(EvaluationError):
                HistoricalCycleClosure(payload, anchor)

    def test_no_orphan_launch_response_or_mutation_after_historical_ceiling(self):
        for added in ({"kind": "file_write_intent", "endpoint": "files/update", "name": "main.py", "sha256": "a" * 64},
                      {"kind": "response", "endpoint": "compile/create", "file": "0" * 32 + ".json",
                       "http_status": 200, "raw_response_sha256": "a" * 64}):
            changed = records()
            changed.append({"at": "2025-01-02T00:50:00+00:00", **added})
            with self.subTest(kind=added["kind"]), self.assertRaises(EvaluationError):
                closure(changed)
        changed = records()
        extra = deepcopy(changed[2]); extra["at"] = changed[1]["at"]
        changed.insert(2, extra)
        with self.assertRaises(EvaluationError):
            closure(changed)
        for kind, field in (("compile_ack", "compileId"), ("run_ack", "backtestId")):
            changed = records()
            same = [row for row in changed if row["kind"] == kind]
            same[1][field] = same[0][field]
            with self.subTest(kind=kind), self.assertRaises(EvaluationError):
                closure(changed)


class RecoveryPreparationTests(unittest.TestCase):
    def test_current_package_is_separate_pending_review_and_never_reopens_budget(self):
        old = prepared()
        for field in RECOVERY_IDENTITY_FIELDS - {"candidate_sha256", "fixture_sha256"}:
            changed = manifest(); changed[field] = "9" * 64
            new = prepared(identity=changed)
            self.assertNotEqual(old.sha256, new.sha256)
            result = new.to_dict()
            self.assertEqual(result["remaining_manual_attempts"], 0)
            self.assertEqual(result["history_sha256"], old.to_dict()["history_sha256"])
            self.assertIs(result["recovery_review_pending"], True)
            for flag in ("typed_journal_custody_verified", "external_provenance_verified",
                         "owner_authorization_verified", "qc_upload_allowed", "qc_launch_allowed", "launch_allowed",
                         "economic_acceptance", "market_evidence"):
                self.assertIs(result[flag], False)
        self.assertEqual(replace(old, source_commit="1" * 40, prior_review_commit="2" * 40,
            prior_review_record_sha256="3" * 64).to_dict()["remaining_manual_attempts"], 0)

    def test_strict_identity_and_review_fields_and_mutation_isolation(self):
        identity = manifest()
        preparation = prepared(identity=identity)
        identity["project_sha256"] = "0" * 64
        self.assertEqual(preparation.to_dict()["recovery_manifest"]["project_sha256"], "d" * 64)
        body = preparation.to_dict(); body["history"]["attempts"].clear()
        self.assertEqual(len(preparation.to_dict()["history"]["attempts"]), 3)
        for field in RECOVERY_IDENTITY_FIELDS:
            missing = manifest(); del missing[field]
            changed = manifest(); changed[field] = "bad"
            for invalid in (missing, changed):
                with self.subTest(field=field), self.assertRaises(EvaluationError):
                    prepared(identity=invalid)
        for invalid in ({**manifest(), "owner_approved": True}, {**manifest(), "candidate_sha256": "0" * 64},
                        {**manifest(), "fixture_sha256": "0" * 64}):
            with self.assertRaises(EvaluationError):
                prepared(identity=invalid)
        for field, value in (("source_commit", "bad"), ("prior_review_commit", None),
                             ("prior_review_record_sha256", "A" * 64), ("history", closure().to_dict())):
            with self.subTest(field=field), self.assertRaises(EvaluationError):
                replace(preparation, **{field: value})
        with self.assertRaises(FrozenInstanceError):
            preparation.source_commit = "0" * 40
        self.assertFalse(any(hasattr(preparation, name) for name in ("launch", "append", "reset", "create_cycle")))


if __name__ == "__main__":
    unittest.main()
