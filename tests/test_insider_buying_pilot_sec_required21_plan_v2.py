"""Genuine invented full25 factories and private fixture custody; no API/QC."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX custody")
from research import insider_buying_pilot_sec_required21_plan_v2 as m


STORAGE_SHA = "6" * 64
IDENTITY = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": "1" * 40,
    "clean": True, "source_sha256": {}, "source_inventory_sha256": m._sha(b"{}")}


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    path = Path(__file__).with_name("test_insider_buying_pilot_sec_consumption_chain_v1.py")
    spec = importlib.util.spec_from_file_location("invented_required21_plan_chain", path)
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    data = helper.corpus.__wrapped__(tmp_path_factory)
    values, pipeline, old = helper._controls(data)
    return SimpleNamespace(helper=helper, data=data, values=values, pipeline=pipeline,
        old=old, chain=helper._chain(values))


def _arguments(corpus, *, supplied=None):
    _selection_helper, (fresh_helper, fresh_corpus) = corpus.data
    roster_helper, original, _unused_roster, all_rows = fresh_corpus
    chosen = original if supplied is None else supplied
    args = roster_helper._args(chosen)
    args.pop("consume_row"); args.pop("fixture_only")
    exposure = {"schema": m.base.compiler.EXPOSURE_SCHEMA, "records": []}
    candidates = {"schema": m.base.compiler.CANDIDATE_SCHEMA, "fixture_only": True,
        "records": [], "masters": [], "authority": dict(m.base.compiler._AUTHORITY)}
    args.update(exposure_raw=m._raw(exposure), candidates_raw=m._raw(candidates),
        master_for_period=lambda period: fresh_helper._master(period, all_rows),
        expected_roster_sha256=corpus.pipeline[1].sha256,
        expected_audit_sha256=corpus.pipeline[2].sha256, fixture=True)
    return args


def _derive(corpus, **changes):
    args = _arguments(corpus); args.update(changes)
    return m._derive(corpus.chain, **args)


def test_full25_rederivation_excludes_prior_and_eight_started_without_new_dispatch(corpus):
    result = _derive(corpus); plan = result["plan"]
    consumed = m.chain_source.consumed_accessions(corpus.chain)
    eligible = [row for row in corpus.pipeline[3]
        if row["source"]["period"] in m.chain_source.selection.REQUIRED_PERIODS
        and row["fresh_locatable_candidate"] and row["source"]["accession_number"] not in consumed]
    assert plan["requests"] == [dict(selection_ordinal=i + 1,
        **{key: row[key] for key in ("source", "source_record_sha256", "request", "request_sha256",
            "pre_normalization_target", "selected_locator")},
        compiler_disposition_sha256=m._sha(m._raw(row)), dispatch_authorized=False, canonical_admitted=False)
        for i, row in enumerate(eligible[:8])]
    assert len(consumed) == 10 and set(corpus.old) <= set(consumed)
    assert plan["consumed_accessions"] == list(consumed)
    assert plan["consumption_sha256"] == corpus.chain.sha256
    assert result["consumption"]["started_added_count"] == 8
    assert result["consumption"]["chain_sha256"] == corpus.chain.sha256
    assert len(plan["quarter_bindings"]) == 25
    assert [row["period"] for row in plan["quarter_bindings"]] == list(m.chain_source.selection.CONTEXT_PERIODS)
    assert len(m.chain_source.selection.REQUIRED_PERIODS) == 21
    assert plan["fixture_only"] is True and plan["selected_count"] == 8
    assert result["source_roster"] == corpus.pipeline[1].to_payload()
    assert result["parent_audit"] == corpus.pipeline[2].to_payload()
    assert result["plan_sha256"] == m._sha(m._raw(plan))
    assert plan["dispatch_authorized"] is plan["canonical_admitted"] is False
    assert all(flag is False if type(flag) is bool else flag == 0 for flag in plan["authority"].values())
    assert b"PRIVATE FINANCIAL SENTINEL" not in m._raw(result)


@pytest.mark.parametrize("fault", ("missing_late", "missing_middle", "wrong_roster_pin", "wrong_audit_pin",
    "wrong_manifest_pin", "wrong_selection_pin", "wrong_fixture_scope"))
def test_source_population_cannot_be_partial_rebound_or_scope_promoted(corpus, fault):
    args = _arguments(corpus)
    if fault == "missing_late": args["quarter_inputs"] = (item for item in args["quarter_inputs"] if item.period != "2026Q1")
    elif fault == "missing_middle": args["quarter_inputs"] = (item for item in args["quarter_inputs"] if item.period != "2023Q2")
    elif fault == "wrong_roster_pin": args["expected_roster_sha256"] = "a" * 64
    elif fault == "wrong_audit_pin": args["expected_audit_sha256"] = "b" * 64
    elif fault == "wrong_manifest_pin": args["expected_manifest_sha256"] = "c" * 64
    elif fault == "wrong_selection_pin": args["expected_selection_sha256"] = "d" * 64
    elif fault == "wrong_fixture_scope": args["fixture"] = False
    with pytest.raises(ValueError): m._derive(corpus.chain, **args)


@pytest.mark.parametrize("fault", ("payload", "clone", "duck"))
def test_chain_must_be_genuine_before_source_iteration(corpus, fault):
    wrong = corpus.chain.to_payload() if hasattr(corpus.chain, "to_payload") else corpus.helper.m._payload(corpus.chain)
    if fault == "clone": wrong = replace(corpus.chain)
    if fault == "duck": wrong = SimpleNamespace(canonical_bytes=corpus.chain.canonical_bytes, sha256=corpus.chain.sha256)
    def unread():
        pytest.fail("source rows reached before genuine chain seal")
        yield
    args = _arguments(corpus); args["quarter_inputs"] = unread()
    with pytest.raises(ValueError): m._derive(wrong, **args)


def test_nonselected_lastquarter_source_drift_cannot_hide_behind_same_prefix(corpus):
    _selection_helper, (_fresh_helper, fresh_corpus) = corpus.data
    helper, original, _unused_roster, _all_rows = fresh_corpus
    changed = helper._changed(original, "2026Q1", lambda raw: helper._fields(raw, 3, "ISSUERTRADINGSYMBOL", "CHANGED"))
    with pytest.raises(ValueError): m._derive(corpus.chain, **_arguments(corpus, supplied=changed))


@pytest.mark.parametrize("factory,kind", (("roster", "clone"), ("roster", "duck"), ("audit", "clone"), ("audit", "duck")))
def test_factory_attestations_cannot_be_replaced_after_complete_real_stream(corpus, monkeypatch, factory, kind):
    def wrong(genuine):
        return replace(genuine) if kind == "clone" else SimpleNamespace(
            to_payload=genuine.to_payload, sha256=genuine.sha256, canonical_bytes=genuine.canonical_bytes)
    if factory == "roster":
        real = m.base.roster.derive_pilot_sec_roster
        monkeypatch.setattr(m.base.roster, "derive_pilot_sec_roster", lambda **kw: wrong(real(**kw)))
    else:
        real = m.base.compiler.PilotSecParentAuditCompiler.finish
        monkeypatch.setattr(m.base.compiler.PilotSecParentAuditCompiler, "finish", lambda self, roster: wrong(real(self, roster)))
    with pytest.raises(ValueError): _derive(corpus)


def test_last_context_quarter_repeat_refuses_whole_chained_prefix_without_refill(corpus):
    _selection_helper, (fresh_helper, fresh_corpus) = corpus.data
    helper, original, _roster, _rows = fresh_corpus
    consumed = m.chain_source.consumed_accessions(corpus.chain)
    target = next(row["source"] for row in corpus.pipeline[3]
        if row["source"]["period"] in m.chain_source.selection.REQUIRED_PERIODS
        and row["fresh_locatable_candidate"] and row["source"]["accession_number"] not in consumed)
    manifest, images, _ = helper._changed(original, "2026Q1",
        lambda raw: helper._fields(raw, 3, "ACCESSION_NUMBER", target["accession_number"]))
    # Independently regenerate the changed82-image census/selector; no stale
    # downstream hash may be the reason the late repeated accession refuses.
    pure = helper.m.selector.pure
    bindings = pure.census._manifest_bindings(manifest)
    profile = pure.build_retained_82q_schema_profile_candidate()
    quarters = tuple(pure.census._census_quarter(item.raw_bytes, binding)
        for item, binding in zip(images, bindings, strict=True))
    headers = tuple(pure.headers._quarter_headers(item.raw_bytes, item.period, profile) for item in images)
    census = pure._census_receipt(quarters, m._sha(manifest), len(manifest), True)
    header = pure._header_receipt(headers, census.sha256, True)
    selected = pure.select_affected_quarters(intake_manifest_raw=manifest,
        expected_manifest_sha256=m._sha(manifest), quarter_inputs=iter(images),
        expected_census_sha256=census.sha256, expected_header_preflight_sha256=header.sha256,
        fixture_only=True).to_payload()
    selected["fixture_only"] = False  # Existing invented retained-control schema only.
    changed = manifest, images, selected
    pipeline = fresh_helper._pipeline(fresh_corpus, supplied=changed)
    all_rows = []
    m.base.roster.derive_pilot_sec_roster(**helper._args(changed, all_rows.append))
    args = _arguments(corpus, supplied=changed)
    args.update(expected_roster_sha256=pipeline[1].sha256, expected_audit_sha256=pipeline[2].sha256,
        master_for_period=lambda period: fresh_helper._master(period, all_rows))
    with pytest.raises(ValueError, match="late_selected_repeat"):
        m._derive(corpus.chain, **args)


def test_worker_envelope_is_exact_and_keeps_every_readiness_gate_false(corpus):
    result = deepcopy(m._result(_derive(corpus), IDENTITY, fixture=True))
    assert m._validate_result(result, IDENTITY, fixture=True) == result
    assert result["fixture_only"] is True and result["execution_identity"] == IDENTITY
    assert result["native_network_fork_allwrite_securityexec_denial"] is True
    for key in ("provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
        assert type(result[key]) is int and result[key] == 0
    assert result["dispatch_authorized"] is result["canonical_admitted"] is result["backtesting_ready"] is False
    with pytest.raises(ValueError): m._validate_result(result, IDENTITY, fixture=False)


@pytest.mark.parametrize("fault", ("extra", "identity", "audit_id", "fixture", "native_boolean_alias",
    "provider", "credential_boolean_alias", "qc", "look", "backtest", "dispatch", "canonical", "ready",
    "plan_pin", "roster_pin", "audit_pin", "consumption_pin", "source_count", "required_count", "authority"))
def test_parent_cannot_accept_rehashed_metadata_with_changed_scope_inputs_or_authority(corpus, fault):
    result = deepcopy(m._result(_derive(corpus), IDENTITY, fixture=True))
    if fault == "extra": result["unregistered"] = True
    elif fault == "identity": result["execution_identity"]["head"] = "2" * 40
    elif fault == "audit_id": result["audit_id"] = "old-namespace"
    elif fault == "fixture": result["fixture_only"] = False
    elif fault == "native_boolean_alias": result["native_network_fork_allwrite_securityexec_denial"] = 1
    elif fault == "provider": result["provider_requests"] = 1
    elif fault == "credential_boolean_alias": result["credential_reads"] = False
    elif fault == "qc": result["qc_accesses"] = 1
    elif fault == "look": result["outcome_looks"] = 1
    elif fault == "backtest": result["backtests"] = 1
    elif fault == "dispatch": result["dispatch_authorized"] = True
    elif fault == "canonical": result["canonical_admitted"] = True
    elif fault == "ready": result["backtesting_ready"] = True
    elif fault == "plan_pin": result["plan_sha256"] = "a" * 64
    elif fault == "roster_pin": result["plan"]["source_roster_sha256"] = "b" * 64
    elif fault == "audit_pin": result["plan"]["parent_audit_sha256"] = "c" * 64
    elif fault == "consumption_pin": result["consumption"]["chain_sha256"] = "d" * 64
    elif fault == "source_count": result["source_roster_counts"]["context_submission_rows"] += 1
    elif fault == "required_count": result["plan"]["required21_counts"]["target_filings"] += 1
    elif fault == "authority": result["plan"]["authority"]["sec_dispatches"] = 1
    if fault in {"roster_pin", "audit_pin", "required_count", "authority"}:
        result["plan_sha256"] = m._sha(m._raw(result["plan"]))
    with pytest.raises(ValueError): m._validate_result(result, IDENTITY, fixture=True)


@pytest.mark.parametrize("field", ("source_roster_counts", "parent_context_counts"))
def test_wrapper_count_aliases_cannot_equal_the_strict_genuine_plan_counts(corpus, field):
    result = deepcopy(m._result(_derive(corpus), IDENTITY, fixture=True))
    counts = result[field]
    key = next((name for name, value in counts.items() if type(value) is int and value in {0, 1}), None)
    if key is not None:
        original = counts[key]; counts[key] = bool(original)
    else:
        key = next(name for name, value in counts.items() if type(value) is int)
        original = counts[key]; counts[key] = float(original)
    # Only the detached wrapper changes. The genuine selection and its root
    # remain intact; Python numeric equality must not admit another JSON type.
    assert counts[key] == original and type(counts[key]) is not int
    assert type(result["plan"]["source_roster_counts" if field == "source_roster_counts" else "parent_context_counts"][key]) is int
    assert result["plan_sha256"] == m._sha(m._raw(result["plan"]))
    with pytest.raises(ValueError): m._validate_result(result, IDENTITY, fixture=True)


@pytest.mark.parametrize("fault", ("extra", "requests", "authority", "boolean_count", "prior_count",
    "added_count", "future_root_inventory", "fixture_custody", "false_unknown_membership"))
def test_consumption_summary_cannot_claim_unobserved_access_custody_or_changed_counts(corpus, fault):
    result = deepcopy(m._result(_derive(corpus), IDENTITY, fixture=True)); summary = result["consumption"]
    if fault == "extra": summary["private_provider_text"] = "INVENTED-UNTRUSTED-SENTINEL"
    elif fault == "requests": summary["new_source_requests"] = 1
    elif fault == "authority": summary["authority"]["sec_dispatches"] = 1
    elif fault == "boolean_count": summary["backtests"] = False
    elif fault == "prior_count": summary["prior_count"] += 1
    elif fault == "added_count": summary["started_added_count"] -= 1
    elif fault == "future_root_inventory": summary["full_root_inventory_verified"] = True
    elif fault == "fixture_custody": summary["selected_metadata_custody_verified"] = True
    elif fault == "false_unknown_membership": summary["unknown_prior_archive_memberships_remain_unknown"] = False
    with pytest.raises(ValueError): m._validate_result(result, IDENTITY, fixture=True)


def test_compact_worker_result_roundtrips_real_frozen_integer_only_ipc(corpus):
    result = m._result(_derive(corpus), IDENTITY, fixture=True)
    assert "source_roster" not in result and "parent_audit" not in result
    assert len(m._raw(result)) <= m.MAX_CONTROL == 2 * 1024 ** 2
    value = {"passed": True, "value": result}
    assert m.storage.legacy.ipc._ipc_result(m._raw({"ok": True, "value": value}) + b"\n", b"", 0) == value


def test_control_byte_bound_applies_even_to_semantically_valid_plan(corpus):
    identity = deepcopy(IDENTITY)
    identity["source_sha256"] = {f"invented/source-{i:05d}.py": "a" * 64 for i in range(26000)}
    identity["source_inventory_sha256"] = m._sha(m._raw(identity["source_sha256"]))
    result = m._result(_derive(corpus), identity, fixture=True)
    assert len(m._raw(result)) > m.MAX_CONTROL
    with pytest.raises(ValueError, match="output_refused"):
        m._validate_result(result, identity, fixture=True)


def _epoch(tmp_path, *, registration=None, identity=None):
    root = tmp_path / "invented-stable-custody"; root.mkdir(mode=0o700)
    identity = IDENTITY if identity is None else identity
    epoch = m.stable.Epoch(identity, m.registration(STORAGE_SHA) if registration is None else registration,
        fixture=True, fixture_root=root, checker=lambda: None)
    epoch.publish("storage-qualification.json", {"schema": m.storage.SCHEMA + "/bound-storage-proof",
        "receipt_sha256": STORAGE_SHA, "receipt_head": "2" * 40, "source_inventory_sha256": "3" * 64,
        "qualification_head": identity["head"], "qualification_source_inventory_sha256": identity["source_inventory_sha256"],
        "historical_probe_bound": True, "storage_identity": epoch.storage_identity,
        "observed_nanoseconds": 117222362000, "post_publication_observed_nanoseconds": 71648182541,
        "passed": True, "fixture_only": True, "authority": m.storage.authority()})
    epoch.publish("observation-started.json", {"schema": m.SCHEMA + "/observation-started", "audit_id": m.AUDIT_ID,
        "execution_identity": identity, "registration_sha256": m._sha(m._raw(epoch.registration)),
        "storage_qualification_sha256": epoch.pins["storage-qualification.json"]["sha256"],
        "maximum_planning_worker_invocations": 1, "started_monotonic_ns": 123456789, "authority": m.authority()})
    return epoch


def test_fixture_publication_rechecks_four_private_leaves_and_returns_external_complete_pin(corpus, tmp_path, monkeypatch):
    epoch = _epoch(tmp_path)
    monkeypatch.setattr(m, "_child", lambda *_a, **_k: pytest.fail("fixture reached native actual input loader"))
    monkeypatch.setattr(m.chain_source, "read_actual_chain", lambda **_k: pytest.fail("fixture reached actual chain"))
    result = m._result(_derive(corpus), IDENTITY, fixture=True)
    try:
        digest = m.run_invented(epoch, result)
        assert digest == epoch.pins["complete.json"]["sha256"] == m._sha(m._raw(epoch.read("complete.json")))
        assert set(epoch.pins) == set(m._NAMES)
        final = epoch.read("complete.json")
        assert final["fixture_only"] is True and final["authority"] == m.authority()
        assert final["published_leaf_pins"] == {name: {"bytes": pin["bytes"], "sha256": pin["sha256"]}
            for name, pin in epoch.pins.items() if name != "complete.json"}
        assert epoch.read("plan.json") == result
        assert epoch.is_actual() is False
        with pytest.raises(m.stable.CustodyError, match="namespace_consumed"):
            m.run_invented(epoch, result)
    finally: epoch.close()


@pytest.mark.parametrize("fault", ("purpose", "audit", "storage_pin", "registration_bool", "actual_flag"))
def test_fixture_output_never_promotes_actual_scope_or_reinterprets_registration(corpus, tmp_path, fault):
    registered = m.registration(STORAGE_SHA)
    if fault == "purpose": registered["purpose"] = "provider_control_qualification"
    elif fault == "audit": registered["audit_id"] = "foreign-claimed-audit"
    elif fault == "storage_pin": registered["storage_receipt_sha256"] = False
    elif fault == "registration_bool": registered["maximum_selected"] = True
    epoch = _epoch(tmp_path, registration=registered)
    result = m._result(_derive(corpus), IDENTITY, fixture=True)
    if fault == "actual_flag": result["fixture_only"] = False
    try:
        with pytest.raises(ValueError): m.run_invented(epoch, result)
        assert set(epoch.pins) == {"reservation.json", "storage-qualification.json", "observation-started.json"}
        assert epoch.is_actual() is False
    finally: epoch.close()


@pytest.mark.parametrize("role", ("health", "proof", "plan", "readback"))
def test_child_command_retains_native_process_tree_denial_and_fixed_isolated_python(monkeypatch, role):
    command = m._command(role, IDENTITY)
    assert command[:6] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", m._policy(role))
    assert command[7:10] == ("-I", "-S", "-B")
    assert "pycache_prefix=" + m.chain_source.producer.EMPTY_CACHE_PREFIX in command
    policy = command[5]
    for needed in ("(deny network*)", "(deny process-fork)", "(deny file-write*)", '(literal "/usr/bin/security")'):
        assert needed in policy


def test_plan_policy_allows_fixed_retained_inputs_and_not_other_artifact_subtrees():
    policy = m._policy("plan")
    roots, leaves = m._scope_paths()
    assert roots and leaves
    for path in roots:
        assert "(subpath " + m.json.dumps(str(path)) + ")" in policy
    for path in leaves:
        assert "(literal " + m.json.dumps(str(path)) + ")" in policy
    assert "(subpath " + m.json.dumps(str(m.LANE_ROOT / "artifacts")) + ")" in policy
    assert "(require-not " in policy
    assert str(m.stable.PRIVATE_CUSTODY_ROOT) in policy
    assert '(deny file-read* (subpath "/Volumes"))' in policy
    assert '(deny file-read* (subpath "/Users/sheltonchen/Library/Keychains"))' in policy
    with pytest.raises(ValueError): m._policy("credential")


@pytest.mark.parametrize("reply", ({"passed": 1, "value": {}}, {"passed": True},
    {"passed": True, "value": {}, "extra": "INVENTED-PRIVATE-TEXT"},
    {"passed": False, "code": "INVENTED-PRIVATE-TEXT"}, {"passed": False, "code": "worker_refused", "extra": True}))
def test_child_ipc_refuses_forged_envelopes_without_echoing_foreign_values(monkeypatch, reply):
    workers = _worker_stubs(lambda *_: deepcopy(reply))
    with pytest.raises(m.Required21PlanError) as caught: m._child("health", IDENTITY, workers=workers)
    assert "INVENTED-PRIVATE-TEXT" not in str(caught.value)


def test_child_launcher_exception_and_unknown_role_never_expose_exception_or_launch_twice(monkeypatch):
    calls = []
    def refuse(*_a, **_k):
        calls.append(True); raise m.Required21PlanError("worker_refused")
    workers = _worker_stubs(refuse)
    with pytest.raises(m.Required21PlanError, match="^worker_refused$"): m._child("plan", IDENTITY, workers=workers)
    with pytest.raises(m.Required21PlanError, match="^arguments_refused$"): m._child("provider", IDENTITY, workers=workers)
    assert calls == [True]


def _worker_stubs(activate):
    workers = {}
    for role in ("health", "proof", "plan", "readback"):
        worker = m._PreparedWorker.__new__(m._PreparedWorker)
        worker.role, worker.identity = role, deepcopy(IDENTITY)
        worker.activate = activate; workers[role] = worker
    return workers


def test_health_worker_uses_real_native_isolation_and_memory_guard_through_integer_ipc(monkeypatch):
    events = []
    class ObservedOutput(io.BytesIO):
        def write(self, value): events.append("write"); return super().write(value)
        def flush(self): events.append("flush"); return super().flush()
    output = ObservedOutput(); checks = []
    guard_class = m.chain_source.producer.previous._WorkerMemoryGuard
    real_check, real_close = guard_class.check, guard_class.close
    def check(guard): events.append("memory"); return real_check(guard)
    def close(guard): events.append("close"); return real_close(guard)
    monkeypatch.setattr(guard_class, "check", check)
    monkeypatch.setattr(guard_class, "close", close)
    monkeypatch.setattr(m, "_current", lambda identity: checks.append(deepcopy(identity)))
    monkeypatch.setattr(m, "_plan_actual", lambda *_: pytest.fail("health read actual retained inputs"))
    monkeypatch.setattr(m.sys, "stdout", SimpleNamespace(buffer=output))
    monkeypatch.setattr(m.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(m._raw(_activation_frame(role="health")) + b"\n")))
    m._prepared_worker("health", IDENTITY)
    ready_raw, remainder = output.getvalue().split(b"\n", 1)
    m._validate_ready(ready_raw + b"\n", "health", IDENTITY)
    decoded = m.storage.legacy.ipc._ipc_result(remainder, b"", 0)
    assert decoded == {"passed": True, "value": {"passed": True, "source_only": True, "authority": m.authority()}}
    assert checks == [IDENTITY, IDENTITY, IDENTITY]
    assert "memory" in events[:events.index("write")]
    last_flush = len(events) - 1 - events[::-1].index("flush")
    assert events[last_flush + 1:events.index("close")] == ["memory"]


def _large_chain(corpus):
    values = deepcopy(corpus.values)
    old = tuple(sorted((*corpus.old, *(f"9999999999-20-{i:06d}" for i in range(20042)))))
    assert len(old) == 20044 and len(set(old)) == 20044
    values["previous-index.json"]["accessions"] = list(old)
    prior_sha = m._sha(m._raw(values["previous-index.json"]))
    builder = m.chain_source.selection.Required21SelectionBuilder(consumed_accessions=old, consumption_sha256=prior_sha)
    for row in corpus.pipeline[3]: builder.consume(row)
    sealed = builder.finish(source_roster=corpus.pipeline[1], parent_audit=corpus.pipeline[2],
        expected_roster_sha256=corpus.pipeline[1].sha256, expected_audit_sha256=corpus.pipeline[2].sha256)
    values["plan.json"] = sealed.to_payload()
    values["reservation.json"]["registration"].update(known_consumed_count=20044, known_consumed_index_sha256=prior_sha)
    values["consumed-index.json"]["accessions"] = sorted((*old,
        *(row["request"]["accession_number"] for row in sealed.to_payload()["requests"])))
    values["consumed-index.json"]["previous_index_sha256"] = prior_sha
    return corpus.helper._chain(corpus.helper._relink(values))


def test_actual_sized_20052_genuine_fixture_chain_and_five_leaf_readback_fit_real_integer_ipc(corpus, tmp_path):
    chain = _large_chain(corpus)
    derived = m._derive(chain, **_arguments(corpus))
    identity = deepcopy(IDENTITY)
    # Equivalent bounded source inventory shape: the164-source storage closure
    # plus the20 explicit planner paths. These are invented hashes throughout.
    identity["source_sha256"] = {f"research/invented_storage_source_{i:03d}.py": "a" * 64 for i in range(164)}
    identity["source_sha256"].update({name: "b" * 64 for name in m.OWN_PATHS})
    identity["source_inventory_sha256"] = m._sha(m._raw(identity["source_sha256"]))
    result = m._result(derived, identity, fixture=True)
    assert len(result["plan"]["consumed_accessions"]) == result["consumption"]["consumed_count"] == 20052
    assert result["plan"]["selected_count"] == 8
    value = {"passed": True, "value": result}
    result_wire = m._raw({"ok": True, "value": value}) + b"\n"
    assert len(result_wire) <= m.MAX_CONTROL
    assert m.storage.legacy.ipc._ipc_result(result_wire, b"", 0) == value
    epoch = _epoch(tmp_path, identity=identity)
    guard = m.chain_source.producer.previous._WorkerMemoryGuard()
    try:
        pin = m.run_invented(epoch, result)
        back = m.stable.read_epoch_controls_invented(epoch.storage_root, m.AUDIT_ID, list(m._NAMES),
            {"complete.json": {"bytes": None, "sha256": pin}}, memory=guard)
        assert set(back["controls"]) == set(m._NAMES)
        assert back["controls"]["plan.json"] == result
        assert back["controls"]["complete.json"]["plan_control_sha256"] == epoch.pins["plan.json"]["sha256"]
        assert back["controls"]["complete.json"]["selection_sha256"] == result["plan_sha256"]
        readback_value = {"passed": True, "value": back}
        readback_wire = m._raw({"ok": True, "value": readback_value}) + b"\n"
        assert len(readback_wire) <= m.MAX_CONTROL
        decoded = m.storage.legacy.ipc._ipc_result(readback_wire, b"", 0)
        assert decoded == m.json.loads(m._raw(readback_value))
        assert all(pin["bytes"] <= m.stable.MAX_BYTES for pin in epoch.pins.values())
        assert sum(pin["bytes"] for pin in epoch.pins.values()) <= m.MAX_EPOCH
        guard.check()
    finally:
        guard.close(); epoch.close()


def test_separate_proof_identity_is_current_subset_without_omitting_new_planner_sources(monkeypatch):
    monkeypatch.setattr(m.storage, "_current", lambda *_: pytest.fail("recomputed smaller proof closure in loaded planner"))
    proof = deepcopy(IDENTITY)
    proof["source_sha256"] = {name: m._sha(name.encode()) for name in m.storage.OWN_PATHS}
    proof["source_inventory_sha256"] = m._sha(m._raw(proof["source_sha256"]))
    full = deepcopy(proof); full["source_sha256"].update({name: m._sha(name.encode()) for name in m.OWN_PATHS})
    full["source_inventory_sha256"] = m._sha(m._raw(full["source_sha256"]))
    m._proof_subset(proof, full)
    assert set(m.OWN_PATHS) <= set(full["source_sha256"])
    for fault in ("head", "root", "common_hash", "digest", "not_a_subset"):
        bad = deepcopy(proof)
        if fault == "head": bad["head"] = "f" * 40
        elif fault == "root": bad["root"] = "/private/tmp/invented-foreign-root"
        elif fault == "common_hash": bad["source_sha256"][next(iter(bad["source_sha256"]))] = "f" * 64
        elif fault == "digest": bad["source_inventory_sha256"] = "e" * 64
        elif fault == "not_a_subset": bad = deepcopy(full)
        if fault == "common_hash": bad["source_inventory_sha256"] = m._sha(m._raw(bad["source_sha256"]))
        with pytest.raises(ValueError): m._proof_subset(bad, full)


@pytest.mark.parametrize("plan_fails,close_fails", ((True, False), (True, True), (False, True), (False, False)))
def test_controller_records_start_before_plan_and_drains_cleanup_without_losing_primary_failure(monkeypatch, plan_fails, close_fails):
    # Controller-only orchestration seam: no real Epoch, capability, inputs or
    # native launcher is constructed. Genuine source/IPC/custody are tested
    # separately above, and the actual transport does not exist in this module.
    events, receivers = [], []
    proof_identity = deepcopy(IDENTITY)
    storage_identity = {"fixture_only": True, "marker": "invented-controller-storage"}
    proof = {"passed": True, "fixture_only": False, "receipt_sha256": m.STORAGE_RECEIPT_SHA256,
        "qualification_head": IDENTITY["head"], "qualification_source_inventory_sha256": IDENTITY["source_inventory_sha256"],
        "storage_identity": storage_identity}
    class IdleWorker:
        def __init__(self, role): self.role = role
        def close(self): events.append("worker_closed:" + self.role)
    workers = {role: IdleWorker(role) for role in ("health", "proof", "plan", "readback")}
    def prepare(identity): events.append("workers_ready"); return workers
    class Receiver:
        def __init__(self, identity, registered):
            events.append("receiver_created")
            self.identity, self.registration, self.fixture = deepcopy(identity), deepcopy(registered), False
            self.storage_identity, self.pins, self.records = deepcopy(storage_identity), {}, {}
            self.closed = False; receivers.append(self)
            self.publish("reservation.json", {"fixture_only": True, "controller_seam": True})
        def publish(self, name, value):
            events.append("publish:" + name); raw = m._raw(value)
            self.records[name] = deepcopy(value)
            self.pins[name] = {"bytes": len(raw), "sha256": m._sha(raw)}
            return self.pins[name]["sha256"]
        def check(self): events.append("checked")
        def close(self):
            events.append("receiver_closed"); self.closed = True
            if close_fails: raise RuntimeError("INVENTED-PRIVATE-CLEANUP-EXCEPTION")
    monkeypatch.setattr(m.stable, "Epoch", Receiver)
    monkeypatch.setattr(m, "_identity", lambda head: (deepcopy(IDENTITY), proof_identity))
    monkeypatch.setattr(m, "_prepare_workers", prepare)
    monkeypatch.setattr(m, "_apply_parent_policy", lambda: events.append("parent_applied"))
    def parent_native(guard): events.append("parent_native_proved"); guard.check()
    monkeypatch.setattr(m, "_parent_native", parent_native)
    monkeypatch.setattr(m.stable, "production_parent_current", lambda *_: None)
    monkeypatch.setattr(m, "_validate_result", lambda result, *_a, **_k: result)
    monkeypatch.setattr(m.chain_source, "read_actual_chain", lambda **_k: pytest.fail("controller read actual chain"))
    guard_class = m.chain_source.producer.previous._WorkerMemoryGuard
    real_close = guard_class.close
    def close_memory(guard): events.append("memory_closed"); return real_close(guard)
    monkeypatch.setattr(guard_class, "close", close_memory)
    def child(role, identity, supplied=None, **kwargs):
        events.append("child:" + role)
        assert identity == IDENTITY
        assert kwargs == {"workers": workers}
        if role == "health": return {"passed": True, "source_only": True, "authority": m.authority()}
        if role == "proof": return deepcopy(proof)
        if role == "plan":
            assert "observation-started.json" in receivers[0].records
            if plan_fails: raise m.Required21PlanError("worker_refused")
            return {"plan": {"selected_count": 8, "underfilled": False}, "plan_sha256": "f" * 64}
        assert role == "readback"
        context = receivers[0]
        assert supplied == {"complete_sha256": context.pins["complete.json"]["sha256"]}
        return {"schema": m.stable.SCHEMA + "/readback", "audit_id": m.AUDIT_ID,
            "controls": deepcopy(context.records), "pins": deepcopy(context.pins), "storage_identity": storage_identity}
    monkeypatch.setattr(m, "_child", child)
    result = m.run_actual(IDENTITY["head"], m.STORAGE_RECEIPT_SHA256)
    context = receivers[0]
    assert events.index("publish:observation-started.json") < events.index("child:plan")
    assert events.index("workers_ready") < events.index("parent_applied") < events.index("parent_native_proved")
    assert events.index("parent_native_proved") < events.index("child:health") < events.index("receiver_created")
    assert events.count("child:plan") == 1
    assert context.closed is True and events.index("receiver_closed") < events.index("memory_closed")
    assert {event.split(":", 1)[1] for event in events if event.startswith("worker_closed:")} == set(workers)
    assert context.records["observation-started.json"]["maximum_planning_worker_invocations"] == 1
    if plan_fails:
        assert result == {"passed": False, "phase": "plan", "code": "worker_refused"}
        assert "complete.json" not in context.records
    elif close_fails:
        assert result == {"passed": False, "phase": "final", "code": "cleanup_refused"}
        assert "complete.json" in context.records
    else:
        assert result["passed"] is True and result["complete_sha256"] == context.pins["complete.json"]["sha256"]
        assert result["authority"] == m.authority()
    assert "INVENTED-PRIVATE" not in m._raw(result).decode()


def _activation_frame(payload=None, *, role="plan", identity=None):
    return {"schema": m.SCHEMA + "/activate", "role": role,
        "identity_sha256": m._sha(m._raw(IDENTITY if identity is None else identity)),
        "payload": {} if payload is None else payload}


def test_prepared_worker_ready_and_explicit_activation_bind_exact_role_and_identity():
    assert m.MAX_ACTIVATION == 256 * 1024 and m.MAX_READY == m.MAX_STDERR == 4096
    assert m.MAX_CONTROL == 2 * 1024 ** 2 and m.WORKER_SECONDS == 900
    ready = m._ready("plan", IDENTITY)
    assert ready == {"schema": m.SCHEMA + "/ready", "role": "plan",
        "identity_sha256": m._sha(m._raw(IDENTITY)), "ready": True, "data_operations": 0}
    payload = {"invented": "typed activation only"}
    raw = m._raw(_activation_frame(payload)) + b"\n"
    assert m._activation(raw, "plan", IDENTITY) == payload
    detached = m._activation(raw, "plan", IDENTITY); detached["invented"] = "changed"
    assert m._activation(raw, "plan", IDENTITY) == payload


@pytest.mark.parametrize("fault", ("EOF", "empty_dict", "missing_newline", "extra_line", "schema", "role",
    "identity", "extra_field", "payload_list", "payload_boolean", "duplicate_field", "oversize", "scalar", "null"))
def test_prepared_worker_refuses_eof_untyped_or_noncanonical_activation(corpus, monkeypatch, fault):
    monkeypatch.setattr(m, "_plan_actual", lambda *_: pytest.fail("unactivated worker touched actual inputs"))
    frame = _activation_frame()
    if fault == "schema": frame["schema"] = "foreign/activate"
    elif fault == "role": frame["role"] = "proof"
    elif fault == "identity": frame["identity_sha256"] = "f" * 64
    elif fault == "extra_field": frame["default_execute"] = True
    elif fault == "payload_list": frame["payload"] = []
    elif fault == "payload_boolean": frame["payload"] = False
    elif fault == "oversize": frame["payload"] = {"invented": "X" * (256 * 1024)}
    raw = m._raw(frame) + b"\n"
    if fault == "EOF": raw = b""
    elif fault == "empty_dict": raw = b"{}\n"
    elif fault == "missing_newline": raw = raw[:-1]
    elif fault == "extra_line": raw += b"{}\n"
    elif fault == "duplicate_field": raw = raw[:-2] + b',"payload":{}}\n'
    elif fault == "scalar": raw = b"7\n"
    elif fault == "null": raw = b"null\n"
    with pytest.raises(ValueError): m._activation(raw, "plan", IDENTITY)


def _prepared_pipes(monkeypatch, *, role="plan", stdout=None, stderr=b"", write_error=False, alive=False, timeout=False):
    events, buffers = [], {}
    class Stream:
        def __init__(self, fd): self.fd, self.closed = fd, False
        def fileno(self): return self.fd
        def close(self): self.closed = True; events.append(("closed", self.fd))
    class Process:
        def __init__(self):
            self.stdin, self.stdout, self.stderr = Stream(101), Stream(102), Stream(103)
            self.pid = 424242
        def poll(self): return None if alive else 0
        def wait(self, *, timeout): events.append(("wait", timeout)); return 0
    class Poll:
        def __init__(self): self.keys = {}; self.closed = False
        def register(self, stream, flags, data): self.keys[stream.fd] = SimpleNamespace(fileobj=stream, data=data)
        def unregister(self, stream): self.keys.pop(stream.fd)
        def get_map(self): return self.keys
        def select(self, timeout):
            events.append(("select", timeout))
            keys = list(self.keys.values())
            # A live prepared child's stderr is not EOF-ready while waiting
            # for activation. After input registration model all pipe events.
            if 101 not in self.keys and not any(event[0] == "write" for event in events):
                keys = [key for key in keys if key.data == "out"]
            return [(key, 0) for key in keys]
        def close(self): self.closed = True; events.append(("selector_closed",))
    process = Process()
    wire = m._raw({"ok": True, "value": {"passed": True, "value": {"fixture_only": True}}}) + b"\n"
    buffers[102] = bytearray(wire if stdout is None else stdout); buffers[103] = bytearray(stderr)
    reads, writes = {102: 0, 103: 0}, []
    def read(fd, maximum):
        raw = bytes(buffers[fd][:maximum]); del buffers[fd][:maximum]
        reads[fd] += len(raw); events.append(("read", fd, maximum)); return raw
    def write(fd, raw):
        events.append(("write", fd)); writes.append(bytes(raw))
        if write_error: raise BrokenPipeError("INVENTED-PRIVATE-BROKEN-PIPE")
        return len(raw)
    monkeypatch.setattr(m.selectors, "DefaultSelector", Poll)
    monkeypatch.setattr(m.os, "read", read); monkeypatch.setattr(m.os, "write", write)
    monkeypatch.setattr(m.os, "set_blocking", lambda *_: None)
    monkeypatch.setattr(m.os, "killpg", lambda pid, sig: events.append(("kill", pid, sig)))
    if timeout:
        ticks = iter((0.0, 1000.0, 1001.0))
        monkeypatch.setattr(m.time, "monotonic", lambda: next(ticks))
    worker = m._PreparedWorker.__new__(m._PreparedWorker)
    worker.role, worker.identity, worker.activated, worker.closed, worker.process = role, deepcopy(IDENTITY), False, False, process
    return SimpleNamespace(worker=worker, process=process, events=events, reads=reads, writes=writes)


def test_prepared_pipe_activation_is_claimed_once_and_uses_real_frozen_decoder(monkeypatch):
    state = _prepared_pipes(monkeypatch)
    assert state.worker.activate({}) == {"passed": True, "value": {"fixture_only": True}}
    assert state.worker.activated is True
    assert b"".join(state.writes) == m._raw(_activation_frame()) + b"\n"
    assert state.process.stdin.closed is True
    count = len(state.writes)
    with pytest.raises(ValueError, match="activation_refused"): state.worker.activate({})
    assert len(state.writes) == count


@pytest.mark.parametrize("fault", ("broken_pipe", "input_cap", "stdout_cap", "stderr_cap", "timeout"))
def test_prepared_pipe_refusal_keeps_one_shot_claim_and_bounded_io(monkeypatch, fault):
    stdout = None
    if fault == "stdout_cap":
        stdout = m._raw({"ok": True, "value": {"passed": True, "value": "X" * m.MAX_CONTROL}}) + b"\n"
    state = _prepared_pipes(monkeypatch, stdout=stdout,
        stderr=b"X" * (m.MAX_STDERR + 1) if fault == "stderr_cap" else b"",
        write_error=fault == "broken_pipe", timeout=fault == "timeout")
    supplied = {"oversize": "X" * m.MAX_ACTIVATION} if fault == "input_cap" else {}
    with pytest.raises(m.Required21PlanError) as caught: state.worker.activate(supplied)
    assert "INVENTED-PRIVATE" not in str(caught.value)
    assert state.worker.activated is True
    assert state.reads[102] <= m.MAX_CONTROL + 2 and state.reads[103] <= m.MAX_STDERR + 1
    before = len(state.writes)
    with pytest.raises(ValueError, match="activation_refused"): state.worker.activate({})
    assert len(state.writes) == before
    if fault in {"input_cap", "timeout"}: assert before == 0
    if fault == "broken_pipe": assert before == 1


def test_unused_prepared_worker_is_killed_drained_and_closed_without_activation(monkeypatch):
    state = _prepared_pipes(monkeypatch, alive=True)
    state.worker.close(); state.worker.close()
    assert state.worker.closed is True and state.worker.activated is False and not state.writes
    assert [event for event in state.events if event[0] == "kill"] == [("kill", 424242, m.signal.SIGKILL)]
    assert ("wait", 5) in state.events
    assert all(stream.closed for stream in (state.process.stdin, state.process.stdout, state.process.stderr))


@pytest.mark.parametrize("fault", ("EOF", "wrong_role", "numeric_ready", "data_started", "oversize"))
def test_prepared_constructor_refuses_bad_ready_before_any_activation_and_closes_process(monkeypatch, fault):
    ready = m._ready("plan", IDENTITY)
    if fault == "wrong_role": ready["role"] = "readback"
    elif fault == "numeric_ready": ready["ready"] = 1
    elif fault == "data_started": ready["data_operations"] = 1
    raw = m._raw(ready) + b"\n"
    if fault == "EOF": raw = b""
    elif fault == "oversize": raw = b"X" * (m.MAX_READY + 1)
    state = _prepared_pipes(monkeypatch, stdout=raw, alive=True)
    monkeypatch.setattr(m, "_PARENT_SANDBOX_APPLIED", False)
    monkeypatch.setattr(m.subprocess, "Popen", lambda *_a, **_k: state.process)
    with pytest.raises(m.Required21PlanError): m._PreparedWorker("plan", IDENTITY)
    assert not state.writes
    assert state.reads[102] <= m.MAX_READY + 1
    assert all(stream.closed for stream in (state.process.stdin, state.process.stdout, state.process.stderr))


def test_parent_policy_is_claimed_once_even_when_native_application_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(m, "_PARENT_SANDBOX_APPLIED", False)
    def refuse(policy):
        calls.append(policy); raise m.Required21PlanError("parent_sandbox_refused")
    monkeypatch.setattr(m, "_sandbox_apply", refuse)
    with pytest.raises(ValueError, match="parent_sandbox_refused"): m._apply_parent_policy()
    with pytest.raises(ValueError, match="parent_sandbox_refused"): m._apply_parent_policy()
    assert calls == [m.parent_native_policy()] and m._PARENT_SANDBOX_APPLIED is True


def test_no_sandbox_child_or_source_identity_process_can_start_after_parent_activation(monkeypatch):
    monkeypatch.setattr(m, "_PARENT_SANDBOX_APPLIED", True)
    monkeypatch.setattr(m.subprocess, "Popen", lambda *_a, **_k: pytest.fail("nested sandbox launch"))
    monkeypatch.setattr(m.storage, "_identity", lambda *_a, **_k: pytest.fail("late source identity process"))
    with pytest.raises(ValueError): m._PreparedWorker("plan", IDENTITY)
    with pytest.raises(ValueError): m._identity(IDENTITY["head"])
    with pytest.raises(ValueError): m._proof_source_identity(IDENTITY["head"])


def test_partial_preparation_drains_earlier_workers_without_activating_any(monkeypatch):
    events = []
    class Worker:
        def __init__(self, role, identity):
            events.append(("prepared", role))
            if role == "plan": raise m.Required21PlanError("ready_refused")
            self.role = role
        def close(self): events.append(("closed", self.role))
        def activate(self, supplied): pytest.fail("partial preparation activated a worker")
    monkeypatch.setattr(m, "_PreparedWorker", Worker)
    with pytest.raises(ValueError, match="ready_refused"): m._prepare_workers(IDENTITY)
    assert events == [("prepared", "health"), ("prepared", "proof"), ("prepared", "plan"),
        ("closed", "proof"), ("closed", "health")]


def test_prepared_data_worker_eof_emits_refusal_without_entering_any_data_role(monkeypatch):
    output, checked = io.BytesIO(), []
    monkeypatch.setattr(m, "_current", lambda identity: checked.append(deepcopy(identity)))
    monkeypatch.setattr(m, "_perform", lambda *_: pytest.fail("EOF activated data work"))
    monkeypatch.setattr(m.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"")))
    monkeypatch.setattr(m.sys, "stdout", SimpleNamespace(buffer=output))
    m._prepared_worker("plan", IDENTITY)
    ready, remainder = output.getvalue().split(b"\n", 1)
    m._validate_ready(ready + b"\n", "plan", IDENTITY)
    assert m.storage.legacy.ipc._ipc_result(remainder, b"", 0) == {"passed": False, "code": "activation_refused"}
    assert checked == [IDENTITY]
