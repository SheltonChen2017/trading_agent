"""Pure configured canonical-source and supplied native-evidence successor.

Application-established roots are the provenance boundary, NOT authentication
by a scope label, hash, provider probe, or this parser. No credential, file,
network, dispatch, outcome calculation or change to the zero-look gate exists.
The caller must independently establish the applicability of the supplied
account/contract/permanent-registration records before using these roots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import weakref

from research import insider_buying_provider_rights_evidence as rights
from research.insider_buying import backtest_qc_canonical_candidate as canonical
from research.insider_buying import backtest_qc_export_adapter as native
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying import backtest_study_package as study

VERSION = "insider-configured-canonical-qc-plan-v1"
CAPTURE_SCHEMA = "insider-configured-canonical-qc-capture-v1"
PROFILE = "INSETF-IB-CONFIGURED-CANONICAL-MOO-EXPORT-v1"
_TOKEN = object()
_PLANS = {}
_EXPORTS = {}


class CanonicalActivationError(ValueError):
    """Supplied external bindings or configured native evidence differ."""


def _need(condition, message):
    if not condition:
        raise CanonicalActivationError("REFUSED: " + message)


def _decode(raw, digest):
    try:
        return analysis._decode(raw, native._digest(digest))
    except ValueError as exc:
        raise CanonicalActivationError("REFUSED: external canonical record differs") from exc


def _keys(value, keys):
    _need(type(value) is dict and set(value) == set(keys), "exact record fields required")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalActivationTrustRoots:
    """Externally established application anchors, never an auth mechanism."""
    rights_evidence_sha256: str
    account_entitlement_sha256: str
    registration_sha256: str

    def hashes(self):
        _need(type(self) is CanonicalActivationTrustRoots, "exact activation roots required")
        return {name: native._digest(getattr(self, name)) for name in (
            "rights_evidence_sha256", "account_entitlement_sha256", "registration_sha256")}


def _configured_files(plan, index):
    files = plan.batch_files(index)
    source = files["main.py"]
    old = b"RESEARCH_BACKTEST_ENABLED = False\n"
    _need(source.count(old) == 1 and b"RESEARCH_BACKTEST_ENABLED = True\n" not in source,
          "exact single disabled source switch required")
    files["main.py"] = source.replace(old, b"RESEARCH_BACKTEST_ENABLED = True\n", 1)
    compile(files["main.py"], "<configured-canonical-qc>", "exec", dont_inherit=True)
    return files


def _children(plan):
    return [{"batch_index": n, "batch_id": plan._batch_id(n),
             "files": {name: native._sha(raw) for name, raw in _configured_files(plan, n).items()}}
            for n in range(plan.to_payload()["batch_count"])]


@dataclass(frozen=True, slots=True, weakref_slot=True)
class ConfiguredCanonicalQcPlan:
    _bytes: bytes = field(repr=False)
    _plan: canonical.CanonicalQcBatchPlan = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)

    def _body(self):
        registered = _PLANS.get(id(self))
        _need(type(self) is ConfiguredCanonicalQcPlan and self._token is _TOKEN
              and type(self._bytes) is bytes and registered is not None
              and registered[0]() is self and registered[1] == self._bytes,
              "configured plan reconstructed or altered")
        body = json.loads(self._bytes)
        _need(type(self._plan) is canonical.CanonicalQcBatchPlan and self._plan.sha256 == body["plan_sha256"],
              "preceding sealed plan differs")
        return body

    @property
    def sha256(self):
        self._body()
        return native._sha(self._bytes)

    def to_payload(self):
        body = self._body()
        return {key: body[key] for key in ("kind", "plan_sha256", "roots", "children", "parent_study_id",
            "registered_look_id", "candidate_id", "candidate_enabled", "dispatch_enabled",
            "contract_validity", "authentication_performed_here", "engine_data_auction_cost_parity_verified", "qc_jobs", "research_looks")}

    def batch_files(self, index):
        body = self._body()
        files = _configured_files(self._plan, index)
        _need({name: native._sha(raw) for name, raw in files.items()} == body["children"][index]["files"],
              "configured child source/object inventory differs")
        return files

    def _batch_id(self, index):
        self._body()
        return self._plan._batch_id(index)

    def new_child_attempt_ledger(self, index):
        """Pure initial bytes, ONLY for an externally proven fresh candidate.

        The application's permanent service must prove no earlier attempts,
        publish a start before dispatch, and anchor the latest immutable ledger.
        Recalling this method cannot reset real attempt accounting. This module
        has no registry, authentication, journal publication or launch operation.
        """
        body = self._body(); self.batch_files(index)
        return study.new_attempt_ledger(candidate_id=self._batch_id(index),
            registered_look_id=body["registered_look_id"], trust_scope="production")

    def _ledger(self, index, raw, digest):
        self.batch_files(index)
        _need(type(raw) is bytes and native._sha(raw) == native._digest(digest), "external ledger root differs")
        ledger = study._ledger(raw)
        body = self._body()
        _need(ledger["trust_scope"] == "production" and ledger["candidate_id"] == self._batch_id(index)
              and ledger["registered_look_id"] == body["registered_look_id"], "ledger candidate/look differs")
        _need(all(row["package_sha256"] == self.sha256 and row["source_sha256"] == body["children"][index]["files"]["main.py"]
                  for row in ledger["attempts"]), "prior attempt configured source differs")
        return ledger

    def begin_child_attempt(self, *, index, ledger_raw, expected_ledger_sha256, attempt_id):
        ledger = self._ledger(index, ledger_raw, expected_ledger_sha256)
        _need(study.attempt_ledger_status(ledger_raw)["can_begin_attempt"], "pending/completed/three-attempt state refuses")
        native._identity(attempt_id)
        _need(attempt_id not in {row["attempt_id"] for row in ledger["attempts"]}, "duplicate attempt identity")
        ledger["attempts"].append({"attempt_id": attempt_id, "package_sha256": self.sha256,
            "source_sha256": self._body()["children"][index]["files"]["main.py"], "state": "pending", "result_sha256": None})
        return study.canonical_bytes(ledger)

    def finish_child_attempt(self, *, index, ledger_raw, expected_ledger_sha256, native_result=None,
                             failure_raw=None, expected_failure_sha256=None):
        """Consume supplied bound evidence, not independently observed failure.

        A compile diagnostic has no backtest ID and spends an attempt even
        before an outcome access. Actual operational chronology/provenance of
        failure bytes and latest-ledger continuity belong to the external
        permanent service, not to simulated historical order timestamps.
        """
        ledger = self._ledger(index, ledger_raw, expected_ledger_sha256)
        _need(bool(ledger["attempts"]) and ledger["attempts"][-1]["state"] == "pending", "no pending child attempt")
        _need((native_result is None) != (failure_raw is None), "exactly one result or externally anchored failure required")
        attempt = ledger["attempts"][-1]
        if native_result is not None:
            _need(type(native_result) is ConfiguredCanonicalQcExport, "sealed configured native result required")
            result = native_result._body()
            _need(result["configured_plan_sha256"] == self.sha256 and result["batch_index"] == index
                  and result["attempt_id"] == attempt["attempt_id"], "native child/attempt lineage differs")
            attempt["state"] = "completed" if result["exact_open_bridge_verified"] else "invalid_data"
            attempt["result_sha256"] = native._sha(native_result._bytes)
        else:
            result = _decode(failure_raw, expected_failure_sha256)
            _keys(result, {"schema", "configured_plan_sha256", "batch_index", "attempt_id", "candidate_source_sha256",
                "project_id", "compile_id", "backtest_id", "status", "errors"})
            _need(result["schema"] == "insider-configured-canonical-qc-failure-v1"
                  and result["configured_plan_sha256"] == self.sha256 and type(result["batch_index"]) is int
                  and result["batch_index"] == index and result["attempt_id"] == attempt["attempt_id"]
                  and result["candidate_source_sha256"] == attempt["source_sha256"], "failure configured lineage differs")
            native._integer(result["project_id"], 1, 2**63 - 1); native._identity(result["compile_id"])
            states = {"CompileError": "compile_failed", "RuntimeError": "runtime_failed", "Cancelled": "cancelled", "Refused": "refused"}
            _need(type(result["status"]) is str and result["status"] in states and type(result["errors"]) is list
                  and 1 <= len(result["errors"]) <= 100 and all(type(s) is str and 0 < len(s) <= 2000 for s in result["errors"]),
                  "failure terminal classification differs")
            if result["status"] == "CompileError":
                _need(result["backtest_id"] is None, "compile failure cannot invent backtest ID")
            else:
                native._identity(result["backtest_id"])
            attempt["state"] = states[result["status"]]; attempt["result_sha256"] = native._sha(failure_raw)
        encoded = study.canonical_bytes(ledger); study._ledger(encoded)
        return encoded

    def verify_native_completion_set(self, results):
        body = self._body()
        _need(type(results) is tuple and len(results) == len(body["children"]), "ALL configured child exports required")
        fills, runs = [], set()
        for n, result in enumerate(results):
            _need(type(result) is ConfiguredCanonicalQcExport, "exact sealed native export required")
            checked = result._body()
            _need(checked["configured_plan_sha256"] == self.sha256 and checked["batch_index"] == n
                  and checked["exact_open_bridge_verified"] is True, "configured native child/open bridge differs")
            terminal = json.loads(result.terminal_bytes())
            run = tuple(terminal[key] for key in ("project_id", "compile_id", "backtest_id"))
            _need(run not in runs, "same native run cannot complete multiple children")
            runs.add(run)
            fills.extend({**fill, "order_id": f"batch-{n+1}:" + fill["order_id"]} for fill in terminal["fills"])
        preceding = self._plan._body()
        return analysis.canonical_bytes({"schema": "insider-stock-event-study-terminal-v1", "trust_scope": "production",
            "registration_sha256": preceding["registration_sha256"], "manifest_sha256": preceding["source_event_manifest_sha256"],
            "candidate_id": body["candidate_id"], "registered_look_id": body["registered_look_id"],
            "outcome_vintage_sha256": preceding["manifest_roots"]["outcome_vintage_sha256"], "status": "Completed",
            "errors": [], "final_positions": [], "fills": fills})


def configure_canonical_qc_plan(*, plan, rights_evidence, account_entitlement_raw, registration_raw,
                                analysis_registration_raw, trust_roots):
    """Derive configured bytes; external applicability is the caller's duty.

    This receipt deliberately records no actual job/look or authentication.
    The old disabled plan and production-analysis refusal remain unchanged.
    """
    _need(type(plan) is canonical.CanonicalQcBatchPlan and type(rights_evidence) is rights.ProviderRightsEvidence,
          "genuine sealed plan and rights factory required")
    roots = trust_roots.hashes() if type(trust_roots) is CanonicalActivationTrustRoots else None
    _need(roots is not None, "exact external activation roots required")
    source = plan._body()
    _need(source["version"] == canonical.VERSION_V2 and source["trust_scope"] == "production", "exact production causal-v2 plan required")
    parent_registration = _decode(analysis_registration_raw, source["registration_sha256"])
    evidence = rights_evidence.to_payload()
    _need(evidence["trust_scope"] == "production" and rights_evidence.sha256 == roots["rights_evidence_sha256"], "rights scope/root differs")
    subject = evidence["subject"]
    mapped = rights_evidence.backtest_rights_declaration(expected_subject_sha256=evidence["roots"]["subject_sha256"],
        expected_account_pseudonym=subject["account_pseudonym"], expected_source_manifest_sha256=source["manifest_roots"]["source_manifest_sha256"],
        expected_outcome_vintage_sha256=source["manifest_roots"]["outcome_vintage_sha256"], evaluated_at_utc=evidence["evaluated_at_utc"])
    _need(source["rights_sha256"] == mapped["rights_artifact_sha256"], "analysis registration rights projection differs")
    entitlement = _decode(account_entitlement_raw, roots["account_entitlement_sha256"])
    _keys(entitlement, {"schema", "trust_scope", "origin", "account_pseudonym", "organization_id", "product_id", "dataset_id", "vintage_id",
        "outcome_vintage_sha256", "market_data_profile", "clock_data_entitlements", "first_session", "last_session", "rights_evidence_sha256",
        "processing_scope", "observed_at_utc"})
    _need(entitlement["schema"] == "insider-canonical-qc-account-entitlement-v1" and entitlement["trust_scope"] == "production"
          and entitlement["origin"] == "externally-anchored-account-product-evidence" and entitlement["processing_scope"] == study.SCOPE,
          "account product/processing profile differs")
    native._identity(entitlement["organization_id"]); analysis._utc(entitlement["observed_at_utc"])
    for key in ("account_pseudonym", "product_id", "dataset_id", "vintage_id", "outcome_vintage_sha256", "market_data_profile", "clock_data_entitlements"):
        _need(study.canonical_bytes(entitlement[key]) == study.canonical_bytes(subject[key]), "account/rights subject differs: " + key)
    _need(entitlement["rights_evidence_sha256"] == rights_evidence.sha256, "account rights factory root differs")
    first, last = source["sessions"][0]["session"], source["sessions"][-1]["session"]
    for record in (subject, entitlement):
        _need(analysis._date(record["first_session"]) <= analysis._date(first)
              and analysis._date(record["last_session"]) >= analysis._date(last), "rights/account whole-calendar coverage incomplete")
    registration = _decode(registration_raw, roots["registration_sha256"])
    expected = {"schema": "insider-canonical-qc-permanent-registration-v1", "trust_scope": "production",
        "origin": "externally-registered-permanent-stock-study", "parent_gate_sha256": study.PARENT_GATE_SHA256,
        "parent_study_id": source["parent_study_id"], "candidate_id": source["candidate_id"], "registered_look_id": source["registered_look_id"],
        "plan_sha256": plan.sha256, "source_event_study_sha256": source["source_event_study_sha256"],
        "source_event_manifest_sha256": source["source_event_manifest_sha256"], "analysis_registration_sha256": source["registration_sha256"],
        **source["manifest_roots"], "rights_evidence_sha256": rights_evidence.sha256,
        "account_entitlement_sha256": roots["account_entitlement_sha256"], "maximum_attempts_per_candidate": 3,
        "all_batches_required": True, "children": _children(plan)}
    _keys(registration, set(expected) | {"registered_at_utc", "first_outcome_access_utc"})
    for key, value in expected.items():
        _need(type(registration[key]) is type(value) and study.canonical_bytes(registration[key]) == study.canonical_bytes(value),
              "permanent full-inventory registration differs: " + key)
    _need(analysis._utc(registration["registered_at_utc"]) < analysis._utc(registration["first_outcome_access_utc"])
          and registration["first_outcome_access_utc"] == parent_registration["first_outcome_access_utc"]
          and analysis._utc(parent_registration["registered_at_utc"]) <= analysis._utc(registration["registered_at_utc"])
          and registration["registered_at_utc"] == evidence["evaluated_at_utc"]
          and analysis._utc(entitlement["observed_at_utc"]) <= analysis._utc(registration["registered_at_utc"]), "activation records not pre-outcome/current evaluation")
    body = {"kind": VERSION, "plan_sha256": plan.sha256, "roots": roots, "children": expected["children"],
        "parent_study_id": source["parent_study_id"], "registered_look_id": source["registered_look_id"], "candidate_id": source["candidate_id"],
        "candidate_enabled": True, "dispatch_enabled": False, "authentication_performed_here": False,
        "registered_at_utc": registration["registered_at_utc"],
        "first_outcome_access_utc": registration["first_outcome_access_utc"],
        "contract_validity": {key: evidence["contract"][key] for key in ("effective_at_utc", "expires_at_utc")},
        "engine_data_auction_cost_parity_verified": False, "qc_jobs": 0, "research_looks": 0}
    encoded = study.canonical_bytes(body)
    result = ConfiguredCanonicalQcPlan(encoded, plan, _TOKEN)
    _PLANS[id(result)] = (weakref.ref(result, lambda _, key=id(result): _PLANS.pop(key, None)), encoded)
    return result


@dataclass(frozen=True, slots=True, weakref_slot=True)
class ConfiguredCanonicalQcExport:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def _body(self):
        row = _EXPORTS.get(id(self))
        _need(type(self) is ConfiguredCanonicalQcExport and self._token is _TOKEN and type(self._bytes) is bytes
              and row is not None and row[0]() is self and row[1] == self._bytes, "configured export reconstructed or altered")
        return json.loads(self._bytes)

    def to_payload(self):
        return self._body()["summary"]

    def terminal_bytes(self):
        return bytes.fromhex(self._body()["terminal_hex"])

    def native_fills(self):
        return json.loads(self.terminal_bytes())["fills"]


def _paired_full_quantities(fills):
    """Per-event matching, not merely aggregate zero holdings for a SID."""
    entries = {row["signal_id"]: row["quantity"] for row in fills if row["side"] == "entry"}
    exits = {row["signal_id"]: row["quantity"] for row in fills if row["side"] == "exit"}
    _need(set(entries) == set(exits) and all(entries[key] == -exits[key] for key in entries),
          "native per-event full entry/exit quantities differ")


def adapt_configured_canonical_qc_export(*, plan, batch_index, native_backtest, order_pages, native_order_events,
        project_files, cloud_signal_manifest, cloud_gate, logs_pages, capture_manifest, operational_receipt_raw, trust_roots):
    """Validate supplied provenance roots and native values, never authenticate."""
    _need(type(plan) is ConfiguredCanonicalQcPlan and type(trust_roots) is native.QcExportTrustRoots, "configured plan/external capture roots required")
    trust_roots.validate(); files = plan.batch_files(batch_index)
    _need(trust_roots.trust_scope == "production", "distinct production export roots required")
    capture = _decode(capture_manifest, trust_roots.capture_manifest_sha256)
    _keys(capture, {"schema", "profile", "trust_scope", "origin", "configured_plan_sha256", "batch_id", "project_id", "compile_id", "backtest_id",
        "attempt_id", "compiled_source_sha256", "project_files_sha256", "signal_manifest_sha256", "gate_sha256", "native_backtest_sha256",
        "native_order_events_sha256", "operational_receipt_sha256", "order_pages", "logs_pages"})
    _need(capture["schema"] == CAPTURE_SCHEMA and capture["profile"] == PROFILE and capture["trust_scope"] == "production"
          and capture["origin"] == "externally-rooted-supplied-native-QC-export" and capture["configured_plan_sha256"] == plan.sha256
          and capture["batch_id"] == plan._batch_id(batch_index), "capture configured context differs")
    native._integer(capture["project_id"], 1, 2**63-1)
    for key in ("compile_id", "backtest_id", "attempt_id"): native._identity(capture[key])
    operation = _decode(operational_receipt_raw, capture["operational_receipt_sha256"])
    expected_operation = {"schema": "insider-canonical-qc-external-operation-v1",
        "origin": "externally-rooted-supplied-operation-record", "configured_plan_sha256": plan.sha256,
        "permanent_registration_sha256": plan._body()["roots"]["registration_sha256"],
        **{key: capture[key] for key in ("project_id", "compile_id", "backtest_id", "attempt_id", "compiled_source_sha256")}}
    _keys(operation, set(expected_operation) | {"launch_started_at_utc", "capture_completed_at_utc"})
    for key, value in expected_operation.items():
        _need(type(operation[key]) is type(value) and operation[key] == value, "external operational lineage differs")
    # These are externally anchored operational observations, not historical
    # simulated order timestamps or authentication performed by this module.
    launch = analysis._utc(operation["launch_started_at_utc"])
    completed_at = analysis._utc(operation["capture_completed_at_utc"])
    _need(analysis._utc(plan._body()["registered_at_utc"]) < analysis._utc(plan._body()["first_outcome_access_utc"]) <= launch
          <= completed_at, "external actual-operation chronology differs")
    validity = plan._body()["contract_validity"]
    _need(analysis._utc(validity["effective_at_utc"]) <= launch <= completed_at < analysis._utc(validity["expires_at_utc"]),
          "bound applicable contract is not current over actual operation")
    _need(capture["compiled_source_sha256"] == native._sha(files["main.py"]) and capture["signal_manifest_sha256"] == native._sha(files["signals.json"])
          and capture["gate_sha256"] == native._sha(files["gate.json"]), "configured source/object capture differs")
    _need(type(order_pages) is tuple and type(logs_pages) is tuple, "exact native page tuples required")
    raws = (native_backtest, native_order_events, project_files, cloud_signal_manifest, cloud_gate, capture_manifest, operational_receipt_raw) + order_pages + logs_pages
    _need(all(type(raw) is bytes for raw in raws) and sum(map(len, raws)) <= native.MAX_TOTAL_BYTES, "bounded exact native byte inventory required")
    native._source_and_objects(capture, files, project_files, cloud_signal_manifest, cloud_gate)
    response = native._fields(native._decode(native_backtest, capture["native_backtest_sha256"]), {"backtest", "success", "errors"}, {"backtest", "success", "errors", "debugging"})
    native._success(response); result = native._fields(response["backtest"], native._BACKTEST_REQUIRED, native._BACKTEST_FIELDS)
    _need(type(result["projectId"]) is int and result["projectId"] == capture["project_id"] and result["backtestId"] == capture["backtest_id"]
          and result["status"] == "Completed." and result["completed"] is True and result["hasInitializeError"] is False
          and result["error"] == result["stacktrace"] == "", "native run not clean Completed")
    _need(type(result["statistics"]) is dict and type(result["statistics"].get("Total Orders")) is str
          and re.fullmatch(r"0|[1-9][0-9]{0,5}", result["statistics"]["Total Orders"]), "native total orders malformed")
    orders = native._pages(order_pages, capture["order_pages"])
    _need(len(orders) == int(result["statistics"]["Total Orders"]), "native pages incomplete")
    manifest = json.loads(files["signals.json"])
    clock = {row["session"]: (analysis._utc(row["open_utc"]), analysis._utc(row["close_utc"])) for row in manifest["sessions"]}
    events = native._decode(native_order_events, capture["native_order_events_sha256"], array=True)
    fills, cash = canonical._canonical_order_fills(orders, events, capture, manifest, clock)
    _paired_full_quantities(fills)
    logs = native._pages(logs_pages, capture["logs_pages"], logs=True)
    _need(all(type(line) is str and len(line) <= 4000 for line in logs), "native logs unbounded")
    markers = [re.sub(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} : ", "", line) for line in logs]
    look = manifest["registered_look_id"]; count = len(manifest["signals"])
    begin = f'IBQC_CANONICAL_INPUT|look={look}|manifest={native._sha(files["signals.json"])}|gate={native._sha(files["gate.json"])}|signals={count}|canonical=false'
    end = f'IBQC_CANONICAL_ORDER_PATH_COMPLETE|look={look}|manifest={native._sha(files["signals.json"])}|entries={count}|exits={count}|canonical=false'
    _need(markers.count(begin) == markers.count(end) == 1 and markers.index(begin) < markers.index(end), "native complete session markers differ")
    _need(type(result["runtimeStatistics"]) is dict and type(result["runtimeStatistics"].get("Holdings")) is str
          and re.fullmatch(r"\$0(?:\.0+)?", result["runtimeStatistics"]["Holdings"]), "native residual/missing holdings")
    _need(type(result["serverStatistics"]) is dict and type(result["serverStatistics"].get("LEAN Version")) is str
          and 0 < len(result["serverStatistics"]["LEAN Version"]) <= 80, "native engine observation absent")
    exact = all(fill["filled_at_utc"] == manifest["sessions"][next(n for n, r in enumerate(manifest["sessions"]) if r["session"] == fill["session"])]["open_utc"] for fill in fills)
    terminal = {"schema": "insider-configured-canonical-qc-child-terminal-v1", "trust_scope": "production",
        "configured_plan_sha256": plan.sha256, "batch_id": plan._batch_id(batch_index), "project_id": str(capture["project_id"]),
        "candidate_source_sha256": capture["compiled_source_sha256"], "manifest_sha256": capture["signal_manifest_sha256"],
        "gate_sha256": capture["gate_sha256"], "capture_manifest_sha256": trust_roots.capture_manifest_sha256,
        "operational_receipt_sha256": capture["operational_receipt_sha256"], "attempt_id": capture["attempt_id"],
        "compile_id": capture["compile_id"], "backtest_id": capture["backtest_id"], "status": "Completed", "errors": [],
        "processed_sessions": [row["session"] for row in manifest["sessions"]], "final_positions": [], "fills": fills}
    summary = {"kind": PROFILE, "source_contents_verified": True, "native_order_count": len(orders), "native_event_count": len(events),
        "native_engine_version_observed": result["serverStatistics"]["LEAN Version"], "exact_open_bridge_verified": exact,
        "external_operational_chronology_bound": True,
        "authentication_performed_here": False, "engine_data_auction_cost_parity_verified": False,
        "dispatch_enabled": False, "statistical_gate": "UNADJUDICATED", "qc_jobs": 0, "research_looks": 0}
    encoded = study.canonical_bytes({"summary": summary, "configured_plan_sha256": plan.sha256, "batch_index": batch_index,
        "attempt_id": capture["attempt_id"], "capture_manifest_sha256": trust_roots.capture_manifest_sha256,
        "operational_receipt_sha256": capture["operational_receipt_sha256"],
        "exact_open_bridge_verified": exact, "native_cash_path": cash, "terminal_hex": study.canonical_bytes(terminal).hex()})
    sealed = ConfiguredCanonicalQcExport(encoded, _TOKEN)
    _EXPORTS[id(sealed)] = (weakref.ref(sealed, lambda _, key=id(sealed): _EXPORTS.pop(key, None)), encoded)
    return sealed
