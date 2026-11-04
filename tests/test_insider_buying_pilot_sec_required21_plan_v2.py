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
    calls = []
    def launch(command, payload, **options):
        calls.append((command, payload, options)); return {"passed": True, "value": {"invented": True}}
    monkeypatch.setattr(m.storage.legacy.ipc, "_launch", launch)
    assert m._child(role, IDENTITY, {}) == {"invented": True}
    command, payload, options = calls[0]
    assert command[:6] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", m._policy(role))
    assert payload == b"{}"
    assert options == {"timeout": m.WORKER_SECONDS if role == "plan" else 120}
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
    monkeypatch.setattr(m.storage.legacy.ipc, "_launch", lambda *_a, **_k: deepcopy(reply))
    with pytest.raises(m.Required21PlanError) as caught: m._child("health", IDENTITY)
    assert "INVENTED-PRIVATE-TEXT" not in str(caught.value)


def test_child_launcher_exception_and_unknown_role_never_expose_exception_or_launch_twice(monkeypatch):
    calls = []
    def refuse(*_a, **_k):
        calls.append(True); raise RuntimeError("INVENTED-PRIVATE-EXCEPTION")
    monkeypatch.setattr(m.storage.legacy.ipc, "_launch", refuse)
    with pytest.raises(m.Required21PlanError, match="^worker_refused$"): m._child("plan", IDENTITY)
    with pytest.raises(m.Required21PlanError, match="^arguments_refused$"): m._child("provider", IDENTITY)
    assert calls == [True]


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
    m._worker("health", IDENTITY, {})
    decoded = m.storage.legacy.ipc._ipc_result(output.getvalue(), b"", 0)
    assert decoded == {"passed": True, "value": {"passed": True, "source_only": True, "authority": m.authority()}}
    assert checks == [IDENTITY, IDENTITY]
    assert "memory" in events[:events.index("write")]
    assert events[events.index("flush") + 1:events.index("close")] == ["memory"]


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
    class Receiver:
        def __init__(self, identity, registered):
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
    monkeypatch.setattr(m, "_parent_native", lambda guard: guard.check())
    monkeypatch.setattr(m.stable, "production_parent_current", lambda *_: None)
    monkeypatch.setattr(m, "_validate_result", lambda result, *_a, **_k: result)
    monkeypatch.setattr(m.chain_source, "read_actual_chain", lambda **_k: pytest.fail("controller read actual chain"))
    guard_class = m.chain_source.producer.previous._WorkerMemoryGuard
    real_close = guard_class.close
    def close_memory(guard): events.append("memory_closed"); return real_close(guard)
    monkeypatch.setattr(guard_class, "close", close_memory)
    def child(role, identity, supplied=None):
        events.append("child:" + role)
        assert identity == IDENTITY
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
    assert events.count("child:plan") == 1
    assert context.closed is True and events[-2:] == ["receiver_closed", "memory_closed"]
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
