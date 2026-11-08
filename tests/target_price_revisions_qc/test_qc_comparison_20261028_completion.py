"""Synthetic supplied-byte completion contracts; no private/native effects."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import pytest

from research.target_price_revisions_qc import comparison_20261028_completion as c
from research.target_price_revisions_qc import extended_evidence as e


def wire(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def rat(value):
    value = Fraction(value)
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


@pytest.fixture(scope="module")
def original_calendar():
    # Public exchange-date declaration, never licensed/private inputs.
    raw = (Path(__file__).resolve().parents[2] / "research/target_price_revisions_qc/extended_calendar.json").read_bytes()
    assert sha(raw) == c.metrics.CALENDAR_SHA256
    return raw


def pack(original, arm="cap_off", days=None, proof=False):
    source = json.loads(original)
    sessions = source["valuation_sessions"]
    if days is None:
        days = sessions
    policy_hash = sha(c.comparison.policy_bytes())
    templates = {c.PREFIX + "comparison_20261028_policy.json": policy_hash,
        c.PREFIX + "extended_calendar.json": sha(original), c.PREFIX + "comparison_20261028_algorithm.py": sha(b"public synthetic template")}
    template_hash = sha(wire({"schema": "tpr-cmp28-public-template-closure-v1", "source_hashes": templates}))
    rendered = {"main.py": sha(b"synthetic public main"), "comparison_20261028_algorithm.py": sha(b"synthetic public rendered")}
    calendar = {"schema": "tpr-cmp28-calendar-candidate-v1", "study_id": c.STUDY,
        "policy_sha256": policy_hash, "source_calendar_sha256": sha(original), "timezone": "America/New_York",
        "start": "2021-01-04", "end": "2026-10-09", "warmup_start": "2020-09-01", "valuation_count": 1449,
        "decision_count": 301, "valuation_sessions": sessions, "warmup_sessions": source["warmup_sessions"],
        "decisions": source["decisions"], "no_market_outcomes": True}
    calendar_raw = wire(calendar)
    config = {"schema": "tpr-cmp28-off-native-config-v1" if arm == "cap_off" else "tpr-cmp28-multi-native-config-v1",
        "study_id": c.STUDY, "candidate_id": c.CANDIDATES[arm], "arm": arm,
        "operation_id": "TPR-CMP28-SYNTHETIC-001", "attempt": 1, "project_id": 37650980,
        "policy_sha256": policy_hash, "calendar_sha256": sha(calendar_raw), "source_template_closure_sha256": template_hash,
        "prior_attempts_looks_sha256": sha(b"all historical failures preserved"), "source_inputs_admitted": False, "canonical_admission": False}
    if arm != "cap_off":
        config["signal_packet"] = {"key": "tpr-cmp28/inputs/synthetic/packet.json", "sha256": sha(b"derived synthetic"),
            "bytes": 1234, "encoding": "utf-8-json", "source_inventory_sha256": sha(b"synthetic inventory")}
    config_raw, job = wire(config), "1" * 32
    config_hash = sha(config_raw)
    prefix = f"tpr-cmp28/evidence/{c.STUDY}/{config['operation_id']}/{config_hash}/attempt-1/37650980/{job}/"
    complete = days == sessions
    summary = {"schema": "tpr-cmp28-off-native-summary-v1" if arm == "cap_off" else "tpr-cmp28-multi-native-summary-v1",
        **{key: config[key] for key in ("study_id", "candidate_id", "arm", "operation_id", "attempt", "project_id", "policy_sha256", "calendar_sha256", "source_template_closure_sha256")},
        "config_sha256": config_hash, "job_id": job, "decisions": 301 if complete else 0, "refused_decisions": 0,
        "valuation_days": len(days), "coverage_complete": complete, "calendar_complete": complete,
        "internally_useful_order_run": complete, "accounting_parity_within_cent": True,
        "submitted_orders": 1, "fill_events": 1, "requested_shares": rat(1), "submitted_shares": rat(1),
        "filled_shares": rat(1), "fees": rat("0.01"), "last_observed_nav": rat(100000) if days else None,
        "last_valuation_session": days[-1] if days else None, "final_nav": rat(100000) if complete else None,
        "max_cash_residual": rat(0), "max_nav_residual": rat(0), "position_ledger_mismatches": 0,
        "risk_breaches": 0, "max_name_exposure": rat("0.1"), "name_soft_cap_breaches": 0, "clock_assertions": 301,
        "reason_counts": {}, "delisting_audit": c.cap_observer.empty_audit(),
        "mark_verification": {"mode": "strict_minute_or_raw_daily_equal_close_v1", "decision_id": "TPR-CMP104-D009",
            "strict_minute_marks": 0, "daily_requests": int(proof), "daily_claims_attempted": int(proof),
            "daily_claims_verified": int(proof), "daily_corroborated_marks": int(proof), "refused_marks": 0,
            "minute_endpoints_rewritten": 0, "prices_substituted": 0},
        "source_inputs_admitted": False, "native_basis_authenticated": False, "full_evidence_retrieval_verified": False,
        "strategy_accepted": False, "canonical_admission": False, "accepted_performance": None}
    if arm != "cap_off":
        summary["signal_runtime_access"] = {"claim_attempts": 1, "claim_same_node_verified": True,
            "backend_durability_proven": False, "claim_key": prefix + "signal-packet-access.json",
            "claim_sha256": sha(b"synthetic access"), "claim_bytes": 1000, "packet_reads": 1, "provider_ready": True,
            "scores_calls": 301 if complete else 0, "drain_calls": 301, "faulted": False, "packet_scope_spent": True, "actual_job_bound": True}
    records = []
    for day in days:
        payload = {"session": day, "nav": "100000", "cash": "100000", "gross_exposure": "0",
            "risk_within_unlevered_account": True, "max_name_exposure": "0", "name_cap_is_prior_close_soft_target": True,
            "position_ledger_mismatches": 0, "cash_ledger_residual": "0", "nav_ledger_residual": "0", "holdings": [],
            "cash_ledger": rat(100000), "fees": rat("0.01"), "independent_holdings_value": rat(0), "holdings_value_residual": rat(0), "raw_marks": []}
        records.append({"ordinal": len(records) + 1, "kind": "NAV", "payload": payload})
    if proof:
        payload = {key: None for key in c.PROOF_KEYS}
        payload.update(record_type="raw_daily_equal_close_corroboration", schema="tpr-cmp28-raw-daily-close-proof-v1",
            session=sessions[0], mode="strict_minute_or_raw_daily_equal_close_v1", decision_id="TPR-CMP104-D009",
            **{key: summary[key] for key in ("project_id", "job_id", "config_sha256", "policy_sha256", "calendar_sha256", "source_template_closure_sha256")},
            minute_endpoint_equals_close=False, daily_price_equals_unchanged_cache=True, native_snapshot_unchanged=True,
            source_inputs_admitted=False, canonical_admission=False)
        records.append({"ordinal": len(records) + 1, "kind": "NAV", "payload": payload})
    records.append({"ordinal": len(records) + 1, "kind": "SUMMARY", "payload": summary})
    package = {"summary": summary, "config": config, "calendar": calendar, "original": original,
        "records": records, "prefix": prefix, "templates": templates, "rendered": rendered}
    return rebuild(package)


def rebuild(p):
    p["records"][-1]["payload"] = p["summary"]
    chunks, current, counts = [], bytearray(), {}
    for record in p["records"]:
        raw = wire(record) + b"\n"
        if len(current) + len(raw) > c.MAX_CHUNK_BYTES:
            chunks.append(bytes(current)); current.clear()
        current.extend(raw)
        counts[record["kind"]] = counts.get(record["kind"], 0) + 1
    if current:
        chunks.append(bytes(current))
    summary, config = p["summary"], p["config"]
    config_raw, calendar_raw = wire(config), wire(p["calendar"])
    index = {"schema": "tpr-cmp28-private-journal-index-v2-plain", "study_id": c.STUDY,
        "candidate_id": summary["candidate_id"], "config_sha256": sha(config_raw), "project_id": summary["project_id"],
        "job_id": summary["job_id"], "config": config, "records": len(p["records"]), "plain_bytes": sum(map(len, chunks)),
        "kind_counts": counts, "chunks": [{"key": p["prefix"] + f"chunk-{n:04d}.jsonl", "bytes": len(raw), "sha256": sha(raw)} for n, raw in enumerate(chunks)],
        "encoding": "utf-8-jsonl", "source_inputs_admitted": False, "strategy_accepted": False, "canonical_admission": False}
    raws = [wire(summary), wire(index), config_raw, calendar_raw, p["original"]]
    binding = {"schema": "tpr-cmp28-completion-binding-v1", **{key: summary[key] for key in
        ("study_id", "candidate_id", "arm", "project_id", "job_id", "operation_id", "attempt", "config_sha256", "policy_sha256", "calendar_sha256", "source_template_closure_sha256")},
        "terminal_status": "Completed", "terminal_evidence_sha256": sha(b"synthetic Completed evidence"),
        "prior_attempts_looks_sha256": config["prior_attempts_looks_sha256"], "template_source_hashes": p["templates"],
        "rendered_source_hashes": p["rendered"], "rendered_source_closure_sha256": sha(wire(p["rendered"])),
        "envelopes": {key: {"sha256": sha(raw), "bytes": len(raw)} for key, raw in zip(c.ENVELOPES, raws)}}
    p.update(raws=raws, binding=binding, chunks=chunks, index=index)
    return p


def validate(p):
    return c.validate_completion(*p["raws"], binding=p["binding"])


def replay(p):
    return c.replay_chunks(*p["raws"], binding=p["binding"], chunks=p["chunks"])


@pytest.mark.parametrize("arm", c.CANDIDATES)
def test_all_five_closed_summary_index_bindings(original_calendar, arm):
    p = pack(original_calendar, arm, days=[])
    result = validate(p)
    assert result["terminal_completed_as_supplied"] is True
    assert result["producer_useful_run_claim"] is False
    assert result["journal_framing_replayed"] is False
    assert result["reported_nav_metrics"] is None
    assert result["reported_fees"] == rat("0.01")
    for key in ("native_origin_authenticated", "backend_durability_proven", "source_inputs_admitted",
                "historical_pit_authenticated", "data_rights_authenticated", "native_permission", "strategy_accepted",
                "canonical_admission", "full_evidence_retrieval_verified", "independent_order_fill_action_cash_reconciliation"):
        assert result[key] is False
    assert result["accepted_performance"] is None
    assert "signal-packet-access" not in json.dumps(result)


def test_full_axis_exact_nav_metrics_with_extra_corroboration_not_extra_daily_nav(original_calendar):
    p = pack(original_calendar, proof=True)
    result = replay(p)
    assert result["producer_useful_run_claim"] is True
    assert result["daily_nav_observations"] == 1449
    assert result["nav_kind_records"] == 1450
    assert result["daily_close_corroboration_proofs"] == 1
    assert result["reported_nav_metrics"]["total_return"] == rat(0)
    assert result["daily_nav_axis_complete"] is True
    assert result["independent_order_fill_action_cash_reconciliation"] is False
    assert "security_id" not in json.dumps(result)


def test_partial_nav_never_gap_filled_or_metrics_invented(original_calendar):
    p = pack(original_calendar, days=["2021-01-04", "2021-01-06"])
    result = replay(p)
    assert result["daily_nav_observations"] == 2
    assert result["daily_nav_axis_complete"] is False
    assert result["reported_nav_metrics"] is None


def test_private_plan_exact_owned_prefix_and_hashes_without_io(original_calendar):
    p = pack(original_calendar, days=[])
    plan = c.chunk_replay_plan(*p["raws"], binding=p["binding"])
    assert plan == [{"ordinal": 0, "key": p["prefix"] + "chunk-0000.jsonl", "bytes": len(p["chunks"][0]), "sha256": sha(p["chunks"][0])}]
    plan[0]["key"] = "changed"
    assert c.chunk_replay_plan(*p["raws"], binding=p["binding"])[0]["key"].startswith(p["prefix"])


@pytest.mark.parametrize("key,value", [("terminal_status", "In Progress..."), ("job_id", "other"), ("project_id", 1),
    ("attempt", True), ("operation_id", "../escape"), ("candidate_id", "wrong"), ("arm", "tpr_on"),
    ("terminal_evidence_sha256", "0" * 64), ("unknown", False)])
def test_malformed_foreign_or_nonterminal_binding_refused(original_calendar, key, value):
    p = pack(original_calendar, days=[])
    p["binding"][key] = value
    with pytest.raises(c.CompletionRefusal, match="^CMP28 supplied completion evidence refused$"):
        validate(p)


@pytest.mark.parametrize("field,value", [("strategy_accepted", True), ("canonical_admission", True),
    ("native_basis_authenticated", True), ("full_evidence_retrieval_verified", True),
    ("source_inputs_admitted", True), ("accepted_performance", 1), ("unknown", "private secret")])
def test_summary_flags_cannot_create_authority(original_calendar, field, value):
    p = pack(original_calendar, days=[])
    p["summary"][field] = value; rebuild(p)
    with pytest.raises(c.CompletionRefusal): validate(p)


@pytest.mark.parametrize("field,value", [("decisions", 300), ("refused_decisions", 1), ("valuation_days", 1448),
    ("fill_events", 0), ("coverage_complete", False), ("calendar_complete", False),
    ("position_ledger_mismatches", 1), ("max_nav_residual", rat("0.011")),
    ("max_cash_residual", rat("0.011")), ("risk_breaches", 1),
    ("reason_counts", {"missing_mark": 1}), ("final_nav", None)])
def test_useful_summary_observable_gates_cannot_be_skipped(original_calendar, field, value):
    p = pack(original_calendar)
    p["summary"][field] = value; rebuild(p)
    with pytest.raises(c.CompletionRefusal): validate(p)


@pytest.mark.parametrize("which", ["summary", "index", "config", "calendar", "source_calendar"])
def test_exact_envelope_hash_size_fail_closed(original_calendar, which):
    p = pack(original_calendar, days=[])
    n = list(c.ENVELOPES).index(which)
    p["raws"][n] += b" "
    with pytest.raises(c.CompletionRefusal): validate(p)


@pytest.mark.parametrize("mutation", ["chunk_key", "chunk_bytes", "chunk_hash", "records", "plain", "kind_counts", "index_unknown", "foreignjob", "changedconfig"])
def test_index_framing_refuses_foreign_or_unbounded_scope(original_calendar, mutation):
    p = pack(original_calendar, days=[])
    i = p["index"]
    if mutation == "chunk_key": i["chunks"][0]["key"] = p["prefix"] + "../chunk-0000.jsonl"
    if mutation == "chunk_bytes": i["chunks"][0]["bytes"] = c.MAX_CHUNK_BYTES + 1
    if mutation == "chunk_hash": i["chunks"][0]["sha256"] = "0" * 64
    if mutation == "records": i["records"] = c.MAX_RECORDS + 1
    if mutation == "plain": i["plain_bytes"] = c.MAX_JOURNAL_BYTES + 1
    if mutation == "kind_counts": i["kind_counts"]["SUMMARY"] = 2
    if mutation == "index_unknown": i["secret"] = "private secret"
    if mutation == "foreignjob": i["job_id"] = "2" * 32
    if mutation == "changedconfig": i["config"]["attempt"] = 2
    p["raws"][1] = wire(i)
    p["binding"]["envelopes"]["index"] = {"sha256": sha(p["raws"][1]), "bytes": len(p["raws"][1])}
    with pytest.raises(c.CompletionRefusal): validate(p)


@pytest.mark.parametrize("mutation", ["ordinal", "duplicate_day", "out_of_order", "unknown_nav", "missing_nav", "summary_changed", "proof_as_day"])
def test_replay_does_not_accept_shape_flags_as_daily_axis(original_calendar, mutation):
    p = pack(original_calendar, days=["2021-01-04", "2021-01-05"], proof=True)
    if mutation == "ordinal": p["records"][0]["ordinal"] = 2
    if mutation == "duplicate_day": p["records"][1]["payload"]["session"] = "2021-01-04"
    if mutation == "out_of_order": p["records"][0]["payload"]["session"], p["records"][1]["payload"]["session"] = "2021-01-05", "2021-01-04"
    if mutation == "unknown_nav": p["records"][0]["payload"]["record_type"] = "custom"
    if mutation == "missing_nav": p["records"][0]["kind"] = "COVERAGE"
    if mutation == "summary_changed": p["records"].insert(0, {"ordinal": 1, "kind": "SUMMARY", "payload": {}})
    if mutation == "proof_as_day": del p["records"][-2]["payload"]["record_type"]
    rebuild(p)
    with pytest.raises(c.CompletionRefusal): replay(p)


@pytest.mark.parametrize("value", [True, 1.0, "NaN", "Infinity", "-1", "0", {"numerator": "2", "denominator": "2"}])
def test_invalid_nav_representations_refused(original_calendar, value):
    p = pack(original_calendar, days=["2021-01-04"])
    p["records"][0]["payload"]["nav"] = value; rebuild(p)
    with pytest.raises(c.CompletionRefusal): replay(p)


def test_hash_bound_but_changed_calendar_and_source_closure_refused(original_calendar):
    p = pack(original_calendar, days=[])
    p["calendar"]["valuation_sessions"][0] = "2021-01-05"; rebuild(p)
    p["binding"]["calendar_sha256"] = sha(p["raws"][3])
    with pytest.raises(c.CompletionRefusal): validate(p)
    p = pack(original_calendar, days=[])
    p["binding"]["template_source_hashes"][c.PREFIX + "comparison_20261028_algorithm.py"] = sha(b"changed public source")
    with pytest.raises(c.CompletionRefusal): validate(p)


def test_multisignal_useful_run_requires_spent_actualjob_claim_and_301_scores(original_calendar):
    p = pack(original_calendar, "cap_tilt_50")
    assert validate(p)["producer_useful_run_claim"] is True
    for key, value in (("scores_calls", 300), ("packet_reads", 0), ("actual_job_bound", False), ("faulted", True),
                       ("claim_key", "tpr-cmp28/evidence/foreign/signal-packet-access.json"), ("backend_durability_proven", True)):
        q = deepcopy(p); q["summary"]["signal_runtime_access"][key] = value; rebuild(q)
        with pytest.raises(c.CompletionRefusal): validate(q)


def test_duplicate_json_and_nonfinite_do_not_echo_private_bodies(original_calendar):
    p = pack(original_calendar, days=[])
    p["raws"][0] = b'{"private secret":NaN,"private secret":1}'
    p["binding"]["envelopes"]["summary"] = {"bytes": len(p["raws"][0]), "sha256": sha(p["raws"][0])}
    with pytest.raises(c.CompletionRefusal) as caught: validate(p)
    assert "private secret" not in str(caught.value)
    assert caught.value.__suppress_context__ is True


def test_no_imported_effectful_or_native_modules():
    import ast
    tree = ast.parse(Path(c.__file__).read_text())
    names = [alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
    assert not {"Path", "os", "socket", "requests", "QuantConnect", "AlgorithmImports", "extended_core"} & set(names)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("open", "eval", "exec", "compile") for node in ast.walk(tree))


def test_calendar_complete_requires_actual_final_session_in_summary(original_calendar):
    p = pack(original_calendar)
    p["summary"]["last_valuation_session"] = "2026-10-08"
    p["summary"]["final_nav"] = None
    rebuild(p)
    with pytest.raises(c.CompletionRefusal): validate(p)


def test_nav_index_counts_include_daily_plus_recognized_proofs(original_calendar):
    p = pack(original_calendar, days=["2021-01-04"], proof=True)
    assert validate(p)["journal_records_planned"] == 3
    p["summary"]["mark_verification"]["daily_corroborated_marks"] = 0
    rebuild(p)
    with pytest.raises(c.CompletionRefusal): validate(p)


@pytest.mark.parametrize("value", [e.JsonNumber("1"), -1, "1", 1.0, None])
def test_expected_attempt_identity_requires_exact_native_int(original_calendar, value):
    p = pack(original_calendar, days=[])
    p["binding"]["attempt"] = value
    with pytest.raises(c.CompletionRefusal): validate(p)


def test_nonordinary_stop_not_swallowed_by_pure_consumer(original_calendar, monkeypatch):
    p = pack(original_calendar, days=[])
    def stop(_):
        raise KeyboardInterrupt("synthetic cancellation")
    monkeypatch.setattr(c.evidence, "parse_json", stop)
    with pytest.raises(KeyboardInterrupt): validate(p)


def test_three_semantic_mutants_killed_in_memory_only(original_calendar):
    import types
    source = Path(c.__file__).read_text()
    cases = [
        ('    if summary["internally_useful_order_run"] and not useful:\n', '    if False:\n', "useful"),
        ('if _integer(record["ordinal"], MAX_RECORDS, 1) != ordinal or record["kind"] not in KINDS:',
         'if record["kind"] not in KINDS:', "ordinal"),
        ('"daily_nav_observations": len(daily),', '"daily_nav_observations": len(daily) + proofs,', "nav_count")]
    for before, after, case in cases:
        assert source.count(before) == 1
        mutant = types.ModuleType(c.__name__ + "_synthetic_mutant")
        mutant.__package__ = c.__package__
        exec(compile(source.replace(before, after, 1), "<synthetic completion mutant>", "exec"), mutant.__dict__)
        if case == "useful":
            p = pack(original_calendar)
            p["summary"]["reason_counts"]["missing_mark"] = 1; rebuild(p)
            with pytest.raises(c.CompletionRefusal): validate(p)
            assert mutant.validate_completion(*p["raws"], binding=p["binding"])["producer_useful_run_claim"] is True
        elif case == "ordinal":
            p = pack(original_calendar, days=["2021-01-04"])
            p["records"][0]["ordinal"] = 2; rebuild(p)
            with pytest.raises(c.CompletionRefusal): replay(p)
            assert mutant.replay_chunks(*p["raws"], binding=p["binding"], chunks=p["chunks"])["journal_framing_replayed"] is True
        else:
            p = pack(original_calendar, proof=True)
            assert replay(p)["daily_nav_observations"] == 1449
            assert mutant.replay_chunks(*p["raws"], binding=p["binding"], chunks=p["chunks"])["daily_nav_observations"] != 1449


@pytest.mark.parametrize("arm", c.CANDIDATES)
def test_real_frozen_public_renderer_config_calendar_and_source_closures_interoperate(original_calendar, arm):
    """Use real 11-/15-file candidate builders, never a private packet body."""
    import ast
    from research.target_price_revisions_qc import comparison_20261028_bundle as off
    from research.target_price_revisions_qc import comparison_20261028_multi_bundle as multi
    if arm == "cap_off":
        sources = {name: Path(name).read_bytes() for name in off.SOURCE_PATHS}
        files, report_raw = off.build_off_candidate(public_sources=sources,
            operation_id="TPR-CMP28-OFF-CONSUMER-INTEROP-001", attempt=4, prior_attempts_looks_sha256="b" * 64)
    else:
        sources = {name: Path(name).read_bytes() for name in multi.SOURCE_PATHS}
        descriptor = {"key": "tpr-cmp28/inputs/synthetic/packet.json", "sha256": "c" * 64, "bytes": 1234,
            "encoding": "utf-8-json", "source_inventory_sha256": "d" * 64}
        files, report_raw = multi.build_multi_candidate(public_sources=sources, arm=arm,
            operation_id="TPR-CMP28-OFF-CONSUMER-INTEROP-001", attempt=4, prior_attempts_looks_sha256="b" * 64,
            signal_packet=descriptor)
        assert len(files) == 15
    report = json.loads(report_raw)
    config_ast = ast.parse(files["comparison_20261028_config.py"])
    value = next(node.value for node in config_ast.body if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "CONFIG_JSON")
    config_raw = ast.literal_eval(value).encode("ascii")
    config = json.loads(config_raw)
    calendar = off._calendar(original_calendar, config["policy_sha256"])
    p = pack(original_calendar, arm, days=[])
    p["config"], p["calendar"] = config, calendar
    p["templates"], p["rendered"] = report["template_source_hashes"], report["cloud_source_hashes"]
    for key in ("study_id", "candidate_id", "arm", "operation_id", "attempt", "project_id", "policy_sha256",
                "calendar_sha256", "source_template_closure_sha256"):
        p["summary"][key] = config[key]
    p["summary"]["config_sha256"] = sha(config_raw)
    p["prefix"] = (f"tpr-cmp28/evidence/{c.STUDY}/{config['operation_id']}/{sha(config_raw)}"
        f"/attempt-4/{config['project_id']}/{p['summary']['job_id']}/")
    if arm != "cap_off":
        p["summary"]["signal_runtime_access"]["claim_key"] = p["prefix"] + "signal-packet-access.json"
        assert p["templates"][c.RAW_HELPER_PATH] == c.RAW_HELPER_SHA256
    rebuild(p)
    assert p["raws"][2] == config_raw
    assert p["binding"]["source_template_closure_sha256"] == report["source_template_closure_sha256"]
    assert p["binding"]["rendered_source_closure_sha256"] == report["rendered_source_closure_sha256"]
    result = replay(p)
    assert result["journal_framing_replayed"] is True
    assert result["native_origin_authenticated"] is False
    assert result["source_inputs_admitted"] is False


@pytest.mark.parametrize("path,digest", [
    (c.RAW_HELPER_PATH, "1" * 64),
    ("research/target_price_revisions_development/other.py", c.RAW_HELPER_SHA256),
    ("research/target_price_revisions_development/raw_revision_copy.py", c.RAW_HELPER_SHA256)])
def test_only_exact_pinned_development_helper_path_identity_allowed(path, digest):
    with pytest.raises(c.CompletionRefusal): c._sources({path: digest}, template=True)
