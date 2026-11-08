"""Synthetic evidence/software only; no private artifacts or native authority."""
import ast
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from research.target_price_revisions_qc import comparison_20261107_sid_cash_single_base_results as r
from research.target_price_revisions_qc import comparison_20261107_sid_cash_single_base_bundle as b
from research.target_price_revisions_qc import comparison_20261028 as parent
import test_qc_comparison_20261028_completion as old

ROOT = Path(__file__).resolve().parents[2]
SID = "SYNTHETIC 1"
JOB = "1" * 32


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def wire(value):
    return json.dumps(r._encoded(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def registry():
    owner, org = 123, "a" * 32
    return {"schema": "tpr-cmp28-five-project-bindings-v1", "round_id": b.bundle.ROUND,
        "owner_instruction_sha256": b.REGISTRY_CREATION_OWNER_SHA256, "git_head": "a" * 40,
        "adapter_source_sha256": b.bundle.PROJECTS_SHA256, "organization_id": org, "owner_id": owner,
        "baseline_receipt_sha256": "b" * 64, "privacy_basis": "documented_private_default_and_observed_collaborators",
        "explicit_privacy_flag_observed": False, "independent_native_origin_attested": False,
        "projects": {key: {"project_id": project, "name": b.bundle.NAMES[key],
            "organization_id": org, "owner_id": owner, "language": "Py",
            "create_receipt_sha256": sha((key + "-create").encode()), "read_receipt_sha256": sha((key + "-read").encode()),
            "collaboration_receipt_sha256": sha((key + "-collaborators").encode()),
            "collaborator_count": 1, "nonowner_collaborator_count": 0, "collaborators_sha256": "c" * 64}
            for key, project in b.preflight.REGISTERED_PROJECTS.items()}}


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("private/provider/native effect denied")
    monkeypatch.setattr(b.bundle.projects.ops, "credential", denied)
    monkeypatch.setattr(b.bundle.projects.ops, "read_private", denied)
    monkeypatch.setattr(b.bundle.projects.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(b.bundle.projects.subprocess, "run", denied)


@pytest.fixture(scope="module")
def sources():
    return {name: (ROOT / name).read_bytes() for name in r.REQUIRED_SOURCES}


def spec(arm):
    return {"arm": arm, "operation_id": ("TPR-CMP28-OFF-" if arm == "cap_off" else "TPR-CMP28-")
        + "SID-CASH-20261107-SYNTHETIC-" + arm, "attempt": 1,
        "prior_attempts_looks_sha256": sha(b"all original failures retained"),
        "latest_owner_instruction_sha256": b.OWNER_SHA256}


def arguments(sources, arm="cap_off"):
    raw = wire(registry())
    return {"public_sources": sources, "project_bindings_raw": raw,
        "expected_project_bindings_sha256": sha(raw), "financial_spec": spec(arm),
        "parent_job_id": JOB, "terminal_evidence_sha256": sha(b"actual receipt required; synthetic here")}


def helper_modules(sources, arm="cap_off", monkeypatch=None):
    files, report = r.build_runtime_helpers(**arguments(sources, arm))

    def load(name):
        # Normal Python import registers a module BEFORE executing its body.
        # dataclasses resolves the defining module through sys.modules; keep
        # this fixture equivalent to QC's ordinary readable-file import.
        module = ModuleType(name)
        if monkeypatch:
            monkeypatch.setitem(sys.modules, name, module)
        else:
            sys.modules[name] = module
        exec(compile(files[name + ".py"], name + ".py", "exec"), module.__dict__)
        return module

    load(r.METADATA_HELPER[:-3])
    load(r.PRIMITIVES_HELPER[:-3])
    module = load(r.REPLAY_HELPER[:-3])
    return module, files, json.loads(report)


def construction(arm):
    members = {sleeve: [{"sid": SID, "ticker": "SYN"}] for sleeve in parent.SLEEVES}
    caps, scores, finance = {SID: "1000"}, {SID: "1"}, {SID: "noninsurance"}
    if arm == "cap_off":
        weights, detail = parent.construct_off(members, caps, finance_insurance_by_sid=finance)
    elif arm == "pure_tpr":
        weights, detail = parent.construct_pure_tpr(members, scores, finance_insurance_by_sid=finance)
    else:
        weights, detail = parent.construct_tilt(members, caps, scores, arm=arm, finance_insurance_by_sid=finance)
    detail["study_id"] = r.STUDY
    _, audit = r.mask.plan_cash_exclusion(weights, detail, {sid: sha(sid.encode("ascii")) for sid in weights})
    return detail, audit


def package(sources, arm="cap_off"):
    raw_registry = wire(registry())
    args = spec(arm)
    cloud, report_raw = b.build_cash_candidate(public_sources={name: sources[name] for name in b.REQUIRED_SOURCES},
        project_bindings_raw=raw_registry, expected_project_bindings_sha256=sha(raw_registry), **args)
    report = json.loads(report_raw)
    config = b.preflight._config(cloud["comparison_20261028_config.py"])
    source_raw = sources[r.PREFIX + "extended_calendar.json"]
    source = json.loads(source_raw)
    calendar = b.bundle.off._calendar(source_raw, report["policy_sha256"])
    calendar["study_id"] = r.STUDY
    summary = old.pack(source_raw, arm)["summary"]
    summary.update({key: config[key] for key in ("study_id", "candidate_id", "arm", "operation_id",
        "attempt", "project_id", "policy_sha256", "calendar_sha256", "source_template_closure_sha256")})
    summary.update(config_sha256=report["config_sha256"], fees=Fraction(0), max_name_exposure=Fraction(1, 10000),
        max_cash_residual=Fraction(0), max_nav_residual=Fraction(0), submitted_orders=1, fill_events=1,
        requested_shares=Fraction(1), submitted_shares=Fraction(1), filled_shares=Fraction(1))
    prefix = ("tpr-cmp28/evidence/" + r.STUDY + "/" + config["operation_id"] + "/" + report["config_sha256"]
        + "/attempt-1/" + str(config["project_id"]) + "/" + JOB + "/")
    if arm != "cap_off":
        summary["signal_runtime_access"]["claim_key"] = prefix + "signal-packet-access.json"
    detail, audit = construction(arm)
    records = []
    def add(kind, row):
        records.append({"ordinal": len(records) + 1, "kind": kind, "payload": row})
    decision_days = {row["session"] for row in source["decisions"]}
    intent = sha((config["candidate_id"] + ":2021-01-04:" + SID).encode())[:20]
    first_stamp = "2021-01-04T14:20:00+00:00"
    fill_stamp = "2021-01-04T14:30:00+00:00"
    for day in source["valuation_sessions"]:
        if day in decision_days:
            add("COVERAGE", {"kind": "sid_cash_exclusion_execution_mask", "session": day, **deepcopy(audit)})
            add("COVERAGE", {"session": day, "arm": arm, "construction": deepcopy(detail), "source_inputs_admitted": False,
                "coverage_semantics": {"execution_mask": "post_construction_fixed_sid_to_cash"}, "execution_mask": deepcopy(audit)})
        if day == "2021-01-04":
            add("ORDER", {"session": day, "security_id": SID, "order_id": 1, "requested": Fraction(1),
                "submitted": Fraction(1), "reason": "submitted", "intent": intent, "utc": first_stamp})
            add("FILL", {"order_id": 1, "security_id": SID, "utc": fill_stamp, "status": "Filled",
                "quantity": Fraction(1), "price": Fraction(10), "fee": Fraction(0), "fee_currency": "USD",
                "native_final_exception": False, "cash_ledger": Fraction(99990), "quantity_ledger": Fraction(1)})
        close = datetime.fromisoformat(day).replace(hour=16, tzinfo=r.NY).astimezone(timezone.utc).isoformat()
        add("NAV", {"session": day, "nav": "100000", "cash": "99990", "gross_exposure": "0.0001",
            "risk_within_unlevered_account": True, "max_name_exposure": "0.0001",
            "name_cap_is_prior_close_soft_target": True, "position_ledger_mismatches": 0,
            "cash_ledger_residual": "0", "nav_ledger_residual": "0", "cash_ledger": Fraction(99990),
            "fees": Fraction(0), "independent_holdings_value": Fraction(10), "holdings_value_residual": Fraction(0),
            "holdings": [{"security_id": SID, "quantity": Fraction(1), "value": Fraction(10)}],
            "raw_marks": [{"security_id": SID, "price": Fraction(10), "mark_utc": close}]})
    common = {"schema": "tpr-sid-cash-native-order-history-v1", "study_id": r.STUDY}
    capture = "2026-10-09T20:01:00+00:00"
    claim = {"claim_key": prefix + "native-order-history-access.json", "claim_bytes": 500,
        "claim_sha256": sha(b"synthetic in-QC claim"), "claim_same_node_verified": True,
        "backend_durability_proven": False, "capture_utc": capture}
    add("COVERAGE", {**common, "kind": "sid_cash_native_history_claim", **claim})
    order = {**common, "kind": "sid_cash_native_order", "order_id": 1, "security_id": SID,
        "order_type": "MarketOnOpen", "status": "Filled", "quantity": Fraction(1), "time_utc": first_stamp,
        "price_currency": "USD", "tag": "TPRE:" + intent, "ticket_quantity": Fraction(1),
        "ticket_quantity_filled": Fraction(1), "ticket_average_fill_price": Fraction(10),
        "ticket_status": "Filled", "ticket_event_count": 1}
    event = {**common, "kind": "sid_cash_native_order_event", "order_id": 1, "event_id": 0, "security_id": SID,
        "utc": fill_stamp, "status": "Filled", "fill_quantity": Fraction(1), "fill_price": Fraction(10),
        "fill_currency": "USD", "fee": Fraction(0), "fee_currency": "USD", "is_assignment": False}
    add("COVERAGE", order)
    add("COVERAGE", event)
    add("COVERAGE", {**common, "kind": "sid_cash_native_history_census", "orders": 1, "events": 1,
        "nonzero_fills": 1, "open_orders": 0, "absolute_filled_shares": Fraction(1), "reported_fees": Fraction(0),
        "order_rows_sha256": sha(b"tpr-sid-cash-native-orders-v1\n" + wire(order) + b"\n"),
        "event_rows_sha256": sha(b"tpr-sid-cash-native-events-v1\n" + wire(event) + b"\n"),
        "known_history": True, "stable_second_capture": True, "source_inputs_admitted": False,
        "strategy_accepted": False, **claim})
    add("COVERAGE", {"kind": "sid_cash_exclusion_census", "schema": r.mask.SID_CASH_SCHEMA,
        "study_id": r.STUDY, "parent_study_id": r.mask.PARENT_STUDY_ID,
        "excluded_security_id_sha256": r.mask.EXCLUDED_SID_SHA256, "guard_calls": 10000,
        "masked_decisions": 0, "masked_slot_occurrences": 0, "blocked_submission_attempts": 0,
        "excluded_submitted_orders": 0, "excluded_fill_events": 0, "initializing": False,
        "excluded_native_quantity": 0, "excluded_independent_quantity": 0, "excluded_open_orders": 0,
        "checked_native_order_history": True, "source_inputs_admitted": False, "strategy_accepted": False})
    add("SUMMARY", summary)
    return rebuild({"summary": summary, "config": config, "calendar": calendar, "source": source_raw,
        "records": records, "prefix": prefix, "report": report, "sources": sources, "registry": raw_registry})


def rebuild(p):
    p["records"][-1]["payload"] = p["summary"]
    chunks, current, counts = [], bytearray(), Counter()
    for number, record in enumerate(p["records"], 1):
        record["ordinal"] = number
        row = wire(record) + b"\n"
        if len(current) + len(row) > r.MAX_CHUNK_BYTES:
            chunks.append(bytes(current))
            current.clear()
        current.extend(row)
        counts[record["kind"]] += 1
    if current:
        chunks.append(bytes(current))
    config_raw, calendar_raw = wire(p["config"]), wire(p["calendar"])
    index = {"schema": "tpr-cmp28-private-journal-index-v2-plain", "study_id": r.STUDY,
        "candidate_id": p["config"]["candidate_id"], "config_sha256": sha(config_raw),
        "project_id": p["config"]["project_id"], "job_id": JOB, "config": p["config"],
        "records": len(p["records"]), "plain_bytes": sum(map(len, chunks)), "kind_counts": dict(counts),
        "chunks": [{"key": p["prefix"] + f"chunk-{n:04d}.jsonl", "bytes": len(raw), "sha256": sha(raw)}
            for n, raw in enumerate(chunks)], "encoding": "utf-8-jsonl",
        "source_inputs_admitted": False, "strategy_accepted": False, "canonical_admission": False}
    raws = [wire(p["summary"]), wire(index), config_raw, calendar_raw, p["source"]]
    binding = {"schema": r.RESULT_SCHEMA, **{key: p["summary"][key] for key in
        ("study_id", "candidate_id", "arm", "project_id", "job_id", "operation_id", "attempt", "config_sha256",
         "policy_sha256", "calendar_sha256", "source_template_closure_sha256")},
        "terminal_status": "Completed", "terminal_evidence_sha256": arguments(p["sources"])["terminal_evidence_sha256"],
        "prior_attempts_looks_sha256": p["config"]["prior_attempts_looks_sha256"],
        "template_source_hashes": p["report"]["template_source_hashes"],
        "rendered_source_hashes": p["report"]["cloud_source_hashes"],
        "rendered_source_closure_sha256": p["report"]["rendered_source_closure_sha256"],
        "envelopes": {key: {"bytes": len(raw), "sha256": sha(raw)} for key, raw in zip(r.ENVELOPES, raws)}}
    p.update(chunks=chunks, index=index, raws=raws, binding=binding)
    return p


def call(p, name):
    return getattr(r, name)(*p["raws"], binding=p["binding"], chunks=p["chunks"],
        public_sources={name: p["sources"][name] for name in b.REQUIRED_SOURCES},
        project_bindings_raw=p["registry"], expected_project_bindings_sha256=sha(p["registry"]))


def row(p, kind):
    return next(record["payload"] for record in p["records"] if record["payload"].get("kind") == kind)


def reseal_history(p):
    order, event, census = (row(p, kind) for kind in ("sid_cash_native_order",
        "sid_cash_native_order_event", "sid_cash_native_history_census"))
    census["order_rows_sha256"] = sha(b"tpr-sid-cash-native-orders-v1\n" + wire(order) + b"\n")
    census["event_rows_sha256"] = sha(b"tpr-sid-cash-native-events-v1\n" + wire(event) + b"\n")
    return rebuild(p)


@pytest.mark.parametrize("arm", b.ARMS)
def test_all_five_exact_full_axis_replays_preserve_distinct_authority(sources, arm):
    p = package(sources, arm)
    report = call(p, "audit_evidence")
    assert report["study_id"] == r.STUDY
    assert report["supplied_evidence_accounting_reconciled"] is True
    assert report["execution_masks_replayed"] == 301
    assert report["daily_nav_observations"] == 1449
    assert report["excluded_runtime_final_census_zero"] is True
    assert report["excluded_journal_holdings_orders_and_fills_zero"] is True
    assert report["native_journal_fill_fee_agreement"] is True
    assert report["native_chart_rounding_agreement"] is False
    assert report["engine_chart_observed"] is False
    assert report["native_origin_authenticated"] is report["strategy_accepted"] is report["canonical_admission"] is False
    assert report["accepted_performance"] is None
    assert report["original_strategy_intent_verified"] is False
    assert report["native_ticket_average_price_recomputed"] is False


@pytest.mark.parametrize("key,value", [
    ("study_id", b.PARENT_STUDY_ID), ("project_id", 37650980), ("candidate_id", "foreign"),
    ("policy_sha256", "a" * 64), ("rendered_source_closure_sha256", "a" * 64),
    ("operation_id", "TPR-CMP28-OLD-1"), ("attempt", 4), ("schema", "tpr-cmp28-completion-binding-v1")])
def test_original_study_retired_project_and_changed_binding_refused(sources, key, value):
    p = package(sources)
    p["binding"][key] = value
    with pytest.raises(r.CompletionRefusal, match="SID-CASH supplied completion evidence refused"):
        call(p, "audit_evidence")


@pytest.mark.parametrize("mutation", ["missing_mask", "changed_cash", "new_target", "duplicate_coverage", "nonzero_census", "missing_census"])
def test_mask_or_zero_census_cannot_be_asserted_without_replay(sources, mutation):
    p = package(sources)
    if mutation == "missing_mask":
        p["records"] = [record for record in p["records"] if record["payload"].get("kind") != "sid_cash_exclusion_execution_mask"]
    elif mutation == "changed_cash":
        row(p, "sid_cash_exclusion_execution_mask")["cash_increment"] = Fraction(1, 60)
    elif mutation == "new_target":
        coverage = next(record["payload"] for record in p["records"] if "construction" in record["payload"])
        coverage["execution_mask"]["per_sleeve"]["SPY"]["execution_weights"]["NEW 2"] = Fraction(1, 60)
    elif mutation == "duplicate_coverage":
        p["records"].insert(2, deepcopy(p["records"][1]))
    elif mutation == "nonzero_census":
        row(p, "sid_cash_exclusion_census")["excluded_native_quantity"] = 1
    else:
        p["records"] = [record for record in p["records"] if record["payload"].get("kind") != "sid_cash_exclusion_census"]
    rebuild(p)
    with pytest.raises(r.CompletionRefusal):
        call(p, "audit_evidence")


@pytest.mark.parametrize("mutation", ["duplicate_id", "bad_hash", "open_order", "unclaimed", "unstable", "future_event", "negative_fee", "wrong_currency", "excluded"])
def test_native_terminal_history_is_bounded_claimed_complete_and_exclusion_free(sources, mutation, monkeypatch):
    p = package(sources)
    event = row(p, "sid_cash_native_order_event")
    census = row(p, "sid_cash_native_history_census")
    if mutation == "duplicate_id":
        p["records"].insert(-3, deepcopy(next(record for record in p["records"] if record["payload"].get("kind") == "sid_cash_native_order_event")))
    elif mutation == "bad_hash":
        census["event_rows_sha256"] = "a" * 64
    elif mutation == "open_order":
        census["open_orders"] = 1
    elif mutation == "unclaimed":
        p["records"] = [record for record in p["records"] if record["payload"].get("kind") != "sid_cash_native_history_claim"]
    elif mutation == "unstable":
        census["stable_second_capture"] = False
    elif mutation == "future_event":
        event["utc"] = "2026-10-09T23:00:00+00:00"
        reseal_history(p)
    elif mutation == "negative_fee":
        event["fee"] = Fraction(-1)
        reseal_history(p)
    elif mutation == "wrong_currency":
        event["fee"] = Fraction(1)
        event["fee_currency"] = "EUR"
        reseal_history(p)
    else:
        monkeypatch.setattr(r.mask, "EXCLUDED_SID_SHA256", sha(SID.encode()))
    rebuild(p)
    with pytest.raises(r.CompletionRefusal):
        r._native_history(p["chunks"], p["source"], p["binding"])


def test_independent_history_disagrees_even_when_both_chunk_and_census_hashes_are_coherent(sources):
    p = package(sources)
    event = row(p, "sid_cash_native_order_event")
    order = row(p, "sid_cash_native_order")
    event["fill_price"] = order["ticket_average_fill_price"] = Fraction(11)
    reseal_history(p)
    report = call(p, "audit_evidence")
    assert report["native_journal_fill_fee_agreement"] is False
    assert report["supplied_evidence_accounting_reconciled"] is False
    assert report["accepted_performance"] is None


def test_submitted_clock_and_candidate_intent_are_independently_checked(sources):
    p = package(sources)
    submitted = next(record["payload"] for record in p["records"] if record["kind"] == "ORDER")
    submitted["utc"] = "2021-01-04T14:21:00+00:00"
    rebuild(p)
    with pytest.raises(r.CompletionRefusal):
        call(p, "audit_evidence")


def test_missing_nav_axis_is_not_completed_accounting(sources):
    p = package(sources)
    p["records"] = [record for record in p["records"] if not (record["kind"] == "NAV" and record["payload"]["session"] == "2021-01-05")]
    rebuild(p)
    with pytest.raises(r.CompletionRefusal):
        call(p, "audit_evidence")


def test_exact_native_unknown_zero_currency_is_retained_without_usd_inference(sources):
    p = package(sources)
    event = row(p, "sid_cash_native_order_event")
    event.update(fill_quantity=Fraction(0), fill_price=Fraction(0), fill_currency=None, fee_currency=None, status="Canceled")
    order = row(p, "sid_cash_native_order")
    order.update(ticket_quantity_filled=Fraction(0), ticket_average_fill_price=Fraction(0), status="Canceled", ticket_status="Canceled")
    census = row(p, "sid_cash_native_history_census")
    census.update(nonzero_fills=0, absolute_filled_shares=Fraction(0))
    reseal_history(p)
    observation, _ = r._native_history(p["chunks"], p["source"], p["binding"])
    assert observation["native_order_census"]["currency_inference_performed"] is False
    assert observation["native_order_census"]["currency_fields_complete"] is False
    assert observation["known_event_count"] == 1


@pytest.mark.parametrize("arm", b.ARMS)
def test_three_fixed_readable_helpers_run_in_qc_shape_without_private_bodies_in_source(sources, arm, monkeypatch):
    helper, files, report = helper_modules(sources, arm, monkeypatch)
    p = package(sources, arm)
    binding = helper.make_binding(p["raws"][0], p["raws"][1])
    assert binding == p["binding"]
    result = helper.audit_evidence(*p["raws"], binding=binding, chunks=p["chunks"])
    assert result["supplied_evidence_accounting_reconciled"] is True
    assert report["helper_files"] == 3 and report["native_effects"] == report["private_reads"] == 0
    assert report["native_origin_authenticated"] is False
    assert set(files) == {r.REPLAY_HELPER, r.PRIMITIVES_HELPER, r.METADATA_HELPER}
    for body in files.values():
        assert 0 < len(body) <= 60000
        assert SID.encode() not in body
        tree = ast.parse(body)
        assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"exec", "eval", "compile", "open", "__import__"} for node in ast.walk(tree))
    assert helper.get_public_envelopes() == tuple(p["raws"][2:])
    with pytest.raises(Exception):
        helper.audit_evidence(*p["raws"], binding={**binding, "job_id": "2" * 32}, chunks=p["chunks"])


@pytest.mark.parametrize("path", sorted(r.PINS))
def test_every_pinned_source_drift_refuses_before_render(sources, path):
    changed = dict(sources)
    changed[path] += b"\n"
    with pytest.raises(r.CompletionRefusal):
        r.build_runtime_helpers(**{**arguments(changed), "public_sources": changed})


def test_own_executable_runtime_ast_drift_cannot_be_supplied_as_code(sources):
    changed = dict(sources)
    changed[r.MODULE] = changed[r.MODULE].replace(b'return events,', b'return events,')
    changed[r.MODULE] = changed[r.MODULE].replace(b'minimum=1) < 1', b'minimum=1) < 2')
    assert changed[r.MODULE] != sources[r.MODULE]
    with pytest.raises(r.CompletionRefusal):
        r.build_runtime_helpers(**arguments(changed))


def test_renderer_exposes_no_caller_context_policy_sid_or_source_fragment_override():
    parameters = set(inspect.signature(r.build_runtime_helpers).parameters)
    assert parameters == {"public_sources", "project_bindings_raw", "expected_project_bindings_sha256",
        "financial_spec", "parent_job_id", "terminal_evidence_sha256"}
    assert r.STUDY != b.PARENT_STUDY_ID


@pytest.mark.parametrize("mutation", ["nonterminal", "opposite_fill", "overfill", "filled_partial", "capture_before_nav"])
def test_terminal_history_rejects_coherently_rehashed_impossible_native_states(sources, mutation):
    p = package(sources)
    order, event, census = (row(p, kind) for kind in ("sid_cash_native_order",
        "sid_cash_native_order_event", "sid_cash_native_history_census"))
    if mutation == "nonterminal":
        order["status"] = order["ticket_status"] = event["status"] = "PartiallyFilled"
    elif mutation == "opposite_fill":
        event["fill_quantity"] = order["ticket_quantity_filled"] = Fraction(-1)
    elif mutation == "overfill":
        event["fill_quantity"] = order["ticket_quantity_filled"] = Fraction(2)
        census["absolute_filled_shares"] = Fraction(2)
    elif mutation == "filled_partial":
        order["quantity"] = order["ticket_quantity"] = Fraction(2)
        submitted = next(record["payload"] for record in p["records"] if record["kind"] == "ORDER")
        submitted["requested"] = submitted["submitted"] = Fraction(2)
    else:
        capture = "2026-10-09T19:59:00+00:00"
        census["capture_utc"] = row(p, "sid_cash_native_history_claim")["capture_utc"] = capture
    reseal_history(p)
    with pytest.raises(r.CompletionRefusal):
        r._native_history(p["chunks"], p["source"], p["binding"])


def test_renderer_keeps_nested_canonical_encoder_and_calls_in_same_lexical_scope(sources):
    files, _ = r.build_runtime_helpers(**arguments(sources))
    tree = ast.parse(files[r.PRIMITIVES_HELPER])
    canonical = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "E_canonical")
    nested = [node.name for node in canonical.body if isinstance(node, ast.FunctionDef)]
    assert nested == ["encode"]
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "encode"
        for node in ast.walk(canonical))
    assert not any(isinstance(node, ast.Name) and node.id == "E_encode" for node in ast.walk(canonical))


def test_runtime_ast_identity_normalizes_only_empty_added_type_params():
    node = ast.parse("def sample(value):\n    return [value]\n").body[0]
    legacy = deepcopy(node)
    legacy._fields = tuple(name for name in legacy._fields if name != "type_params")
    modern = deepcopy(node)
    modern._fields = tuple(name for name in modern._fields if name != "type_params") + ("type_params",)
    modern.type_params = []
    assert r._semantic_ast(legacy) == r._semantic_ast(modern)
    modern.type_params = [ast.Name(id="T", ctx=ast.Load())]
    with pytest.raises(r.CompletionRefusal):
        r._semantic_ast(modern)


def test_runtime_ast_identity_preserves_empty_fields_and_typed_constant_values():
    node = ast.parse("def sample():\n    return True\n").body[0]
    changed = deepcopy(node)
    changed.body[0].value = ast.Constant(1)
    assert r._semantic_ast(node) != r._semantic_ast(changed)
    changed = deepcopy(node)
    changed.args.args = [ast.arg(arg="value")]
    assert r._semantic_ast(node) != r._semantic_ast(changed)


def test_selected_runtime_external_imports_are_in_the_closed_stdlib_header(sources):
    import builtins
    selected, _ = r._runtime_nodes(sources)
    files, _ = r.build_runtime_helpers(**arguments(sources))
    tree = ast.parse(files[r.PRIMITIVES_HELPER])
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(alias.asname or alias.name for alias in node.names)
    assert any(isinstance(node, ast.ImportFrom) and node.module == "collections.abc"
        and [(alias.name, alias.asname) for alias in node.names] == [("Mapping", None)] for node in tree.body)
    for group, nodes in selected.items():
        declared = set().union(*(r._declared(node) for node in nodes)) if nodes else set()
        loaded = {child.id for node in nodes for child in ast.walk(node)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)}
        locally_bound = {child.id for node in nodes for child in ast.walk(node)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)}
        locally_bound |= {child.arg for node in nodes for child in ast.walk(node) if isinstance(child, ast.arg)}
        locally_bound |= {child.name for node in nodes for child in ast.walk(node)
            if isinstance(child, (ast.FunctionDef, ast.ClassDef))}
        external = loaded - declared - locally_bound - set(dir(builtins)) - set(r._ALIASES[group])
        assert external <= imported, (group, sorted(external - imported))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"globals", "locals", "__import__"} for node in ast.walk(tree))


def test_single_base_epoch_is_fixed_and_old_v1_binding_is_not_admitted(sources):
    from research.target_price_revisions_qc import comparison_20261107_sid_cash_bundle as legacy
    p = package(sources)
    raw_registry = wire(registry())
    old_files, old_report_raw = legacy.build_cash_candidate(
        public_sources={name: sources[name] for name in legacy.REQUIRED_SOURCES},
        project_bindings_raw=raw_registry, expected_project_bindings_sha256=sha(raw_registry),
        **spec("cap_off"))
    old_report = json.loads(old_report_raw)
    expected = r._expected(p["binding"], {name: sources[name] for name in b.REQUIRED_SOURCES},
        raw_registry, sha(raw_registry))
    assert r.SOURCE_EPOCH == b.SOURCE_EPOCH == "TPR-SID-CASH-SINGLE-BASE-20261107-v2"
    assert b.STUDY_ID == legacy.STUDY_ID
    assert expected["policy_sha256"] == old_report["policy_sha256"]
    assert expected["calendar_sha256"] == old_report["calendar_sha256"]
    assert expected["config_sha256"] != old_report["config_sha256"]
    assert expected["source_template_closure_sha256"] != old_report["source_template_closure_sha256"]
    stale = deepcopy(p["binding"])
    for field in ("config_sha256", "source_template_closure_sha256", "rendered_source_closure_sha256"):
        stale[field] = old_report[field]
    stale["template_source_hashes"] = old_report["template_source_hashes"]
    stale["rendered_source_hashes"] = old_report["cloud_source_hashes"]
    with pytest.raises(r.CompletionRefusal):
        r.validate_completion(*p["raws"], binding=stale,
            public_sources={name: sources[name] for name in b.REQUIRED_SOURCES},
            project_bindings_raw=raw_registry, expected_project_bindings_sha256=sha(raw_registry))
    assert b.preflight._config(old_files["comparison_20261028_config.py"])["study_id"] == b.STUDY_ID


def test_single_base_result_helpers_report_only_the_fixed_v2_epoch(sources):
    _, report_raw = r.build_runtime_helpers(**arguments(sources))
    report = json.loads(report_raw)
    assert report["source_epoch"] == r.SOURCE_EPOCH
    assert report["native_origin_authenticated"] is False
    assert report["accepted_performance"] is None


def test_single_base_expected_context_cannot_use_v1_builder_output(sources, monkeypatch):
    from research.target_price_revisions_qc import comparison_20261107_sid_cash_bundle as legacy
    p = package(sources)
    raw_registry = wire(registry())
    output = legacy.build_cash_candidate(
        public_sources={name: sources[name] for name in legacy.REQUIRED_SOURCES},
        project_bindings_raw=raw_registry, expected_project_bindings_sha256=sha(raw_registry),
        **spec("cap_off"))
    monkeypatch.setattr(r.cash_bundle, "build_cash_candidate", lambda **_kwargs: output)
    with pytest.raises(r.CompletionRefusal):
        r._expected(p["binding"], {name: sources[name] for name in b.REQUIRED_SOURCES},
            raw_registry, sha(raw_registry))


def test_all_accounting_and_rendered_runtime_functions_preserve_reviewed_v1_ast():
    legacy_path = ROOT / "research/target_price_revisions_qc/comparison_20261107_sid_cash_results.py"
    old = {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(legacy_path.read_bytes()).body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    current = {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(Path(r.__file__).read_bytes()).body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    assert set(current) == set(old)
    for name in old:
        if name not in {"_expected", "build_runtime_helpers"}:
            assert current[name] == old[name], name
