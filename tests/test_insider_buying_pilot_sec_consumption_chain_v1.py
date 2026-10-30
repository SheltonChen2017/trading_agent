"""Invented full25 source and selected metadata; no actual artifact access."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX custody")
from research import insider_buying_pilot_sec_consumption_chain_v1 as m


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    path = Path(__file__).with_name("test_insider_buying_pilot_sec_required21_selection_v1.py")
    spec = importlib.util.spec_from_file_location("invented_consumption_chain_source", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper, helper.corpus.__wrapped__(tmp_path_factory)


def _pins(raws):
    return {name: (len(raw), m._sha(raw)) for name, raw in raws.items()}


def _raws(values):
    return {name: m._raw(value) for name, value in values.items()}


def _relink(values):
    """Only downstream control pins; semantic contradictions remain intact."""
    value = deepcopy(values)
    plan, index, complete = (value[name] for name in ("plan.json", "consumed-index.json", "complete.json"))
    index["plan_sha256"] = m._sha(m._raw(plan))
    complete["reservation_sha256"] = m._sha(m._raw(value["reservation.json"]))
    complete["plan_sha256"] = m._sha(m._raw(plan))
    complete["index_sha256"] = m._sha(m._raw(index))
    complete["registration_sha256"] = m._sha(m._raw(value["reservation.json"]["registration"]))
    return value


def _controls(corpus):
    helper, source = corpus
    pipeline = helper._pipeline(source)
    old = tuple(sorted(row["source"]["accession_number"] for row in helper._eligible(pipeline[3])[:2]))
    prior = {"schema": m.producer.batch.campaign.SCHEMA + "/consumed-index", "generation": 1,
        "accessions": list(old), "plan_sha256": "b" * 64, "predecessor_index_sha256": None,
        "base_consumption": {}, "archive_exposures": [], "archive_membership_known": False,
        "authority": dict(m.producer.batch.AUTHORITY)}
    prior_hash = m._sha(m._raw(prior))
    builder = m.selection.Required21SelectionBuilder(consumed_accessions=old, consumption_sha256=prior_hash)
    for row in pipeline[3]:
        builder.consume(row)
    sealed = builder.finish(source_roster=pipeline[1], parent_audit=pipeline[2],
        expected_roster_sha256=pipeline[1].sha256, expected_audit_sha256=pipeline[2].sha256)
    plan = sealed.to_payload()
    registration = m.producer.registration()
    registration["known_consumed_count"] = len(old)
    registration["known_consumed_index_sha256"] = prior_hash
    reservation = {"schema": m.producer.SCHEMA + "/reservation", "audit_id": m.producer.AUDIT_ID,
        "execution_identity": {"fixture_only": True}, "registration": registration,
        "input_metadata_sha256": "c" * 64, "authority": m.producer._authority()}
    results = [{"accession_number": row["request"]["accession_number"],
        "claim_name": m._sha(row["request"]["accession_number"].encode()) + ".json",
        "claim_sha256": "d" * 64, "start_name": f"request-{ordinal:03d}-start.json",
        "start_sha256": "e" * 64, "result_name": f"request-{ordinal:03d}-result.json",
        "result_sha256": "f" * 64} for ordinal, row in enumerate(plan["requests"])]
    index = {"schema": m.producer.SCHEMA + "/consumed-index",
        "accessions": sorted((*old, *(item["accession_number"] for item in results))),
        "previous_index_sha256": prior_hash, "plan_sha256": m._sha(m._raw(plan)),
        "unknown_prior_archive_memberships_remain_unknown": True}
    complete = {"schema": m.producer.SCHEMA + "/complete", "audit_id": m.producer.AUDIT_ID,
        "fixture_only": True, "execution_identity": {"fixture_only": True},
        "registration_sha256": "a" * 64, "reservation_sha256": "a" * 64,
        "plan_sha256": "a" * 64, "index_sha256": "a" * 64,
        "planned": len(results), "started": len(results), "unattempted": 0,
        "results": results, "completed_without_refusal": True, "authority": m.producer._authority()}
    values = _relink({"previous-index.json": prior, "reservation.json": reservation,
        "plan.json": plan, "consumed-index.json": index, "complete.json": complete})
    return values, pipeline, old


def _chain(values):
    raws = _raws(values)
    return m.qualify_invented_controls(raws, expected_pins=_pins(raws))


def test_selected_chain_preserves_all_prior_and_eight_started_exclusions(corpus):
    values, _, old = _controls(corpus)
    chain = _chain(values)
    summary = m.public_summary(chain)
    assert summary["fixture_only"] is True
    assert summary["prior_count"] == 2 and summary["started_added_count"] == 8
    assert summary["consumed_count"] == 10
    assert set(old) <= set(m.consumed_accessions(chain))
    assert m.consumed_accessions(chain) == tuple(values["consumed-index.json"]["accessions"])
    assert summary["chain_sha256"] == m._sha(chain.canonical_bytes())
    assert summary["consumed_accessions_sha256"] == m._sha(m._raw(list(m.consumed_accessions(chain))))
    assert "accessions" not in summary and not any(accession in m._raw(summary).decode() for accession in old)
    assert summary["archive_membership_known"] is False
    assert summary["unknown_prior_archive_memberships_remain_unknown"] is True
    for key in ("selected_metadata_custody_verified", "full_root_inventory_verified", "claim_start_result_leaves_replayed",
        "original_bodies_replayed", "producer_git_images_verified_here"):
        assert summary[key] is False
    for key in ("new_source_requests", "original_body_reads", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
        assert summary[key] == 0
    assert all(value is False if type(value) is bool else value == 0 for value in summary["authority"].values())
    summary["control_sha256"].clear()
    assert len(m.public_summary(chain)["control_sha256"]) == 5


def test_genuine_adapter_rederives_full25_and_keeps_required21_and_consumption_hash(corpus):
    values, pipeline, _ = _controls(corpus)
    chain = _chain(values)
    builder = m.required21_selection_builder(chain)
    for row in pipeline[3]:
        builder.consume(row)
    result = builder.finish(source_roster=pipeline[1], parent_audit=pipeline[2],
        expected_roster_sha256=pipeline[1].sha256, expected_audit_sha256=pipeline[2].sha256)
    value = result.to_payload()
    consumed = m.consumed_accessions(chain)
    assert value["consumed_accessions"] == list(consumed)
    assert value["consumption_sha256"] == chain.sha256
    assert value["fixture_only"] is True
    assert len(value["quarter_bindings"]) == 25
    assert [row["period"] for row in value["quarter_bindings"]] == list(m.selection.CONTEXT_PERIODS)
    assert all(row["request"]["period"] in m.selection.REQUIRED_PERIODS
        and row["request"]["accession_number"] not in consumed for row in value["requests"])
    assert value["dispatch_authorized"] is value["canonical_admitted"] is False


@pytest.mark.parametrize("fault", ("subtract", "extra", "duplicate", "unsorted", "replace", "unknown_membership"))
def test_coherently_rehashed_index_cannot_change_monotonic_exclusions(corpus, fault):
    values, _, _ = _controls(corpus)
    index = values["consumed-index.json"]
    if fault == "subtract": index["accessions"].pop(0)
    if fault == "extra": index["accessions"].append("9999999999-25-999999")
    if fault == "duplicate": index["accessions"].append(index["accessions"][-1])
    if fault == "unsorted": index["accessions"].reverse()
    if fault == "replace": index["accessions"][-1] = "9999999999-25-999999"
    if fault == "unknown_membership": index["unknown_prior_archive_memberships_remain_unknown"] = False
    with pytest.raises(m.ConsumptionChainError):
        _chain(_relink(values))


def test_wrong_prior_list_with_right_length_and_authenticated_hash_still_refuses(corpus):
    values, _, _ = _controls(corpus)
    prior = values["previous-index.json"]
    prior["accessions"] = ["9999999998-20-000001", "9999999999-20-000001"]
    digest = m._sha(m._raw(prior))
    values["plan.json"]["consumption_sha256"] = digest
    values["consumed-index.json"]["previous_index_sha256"] = digest
    values["consumed-index.json"]["accessions"] = sorted((*prior["accessions"],
        *(row["accession_number"] for row in values["complete.json"]["results"])))
    values["reservation.json"]["registration"]["known_consumed_index_sha256"] = digest
    with pytest.raises(m.ConsumptionChainError, match="prior_consumption_differs"):
        _chain(_relink(values))


@pytest.mark.parametrize("field", ("claim_name", "claim_sha256", "start_name", "start_sha256", "result_name",
    "result_sha256", "accession_number"))
def test_started_descriptor_each_link_is_required_even_with_rehashed_completion(corpus, field):
    values, _, _ = _controls(corpus)
    values["complete.json"]["results"][0][field] = "bad"
    with pytest.raises(m.ConsumptionChainError, match="started_descriptor_refused"):
        _chain(values)


@pytest.mark.parametrize("fault", ("started_bool", "started_prefix", "missing_result", "planned", "unattempted",
    "reservation", "registration", "plan", "index", "prior_membership", "authority", "unknown_key"))
def test_impossible_or_unlinked_controls_refuse(corpus, fault):
    values, _, _ = _controls(corpus)
    complete = values["complete.json"]
    if fault == "started_bool": complete["started"] = True
    if fault == "started_prefix": complete["started"] = 7
    if fault == "missing_result": complete["results"].pop()
    if fault == "planned": complete["planned"] = 9
    if fault == "unattempted": complete["unattempted"] = 1
    if fault == "reservation": complete["reservation_sha256"] = "f" * 64
    if fault == "registration": complete["registration_sha256"] = "f" * 64
    if fault == "plan": complete["plan_sha256"] = "f" * 64
    if fault == "index": complete["index_sha256"] = "f" * 64
    if fault == "prior_membership": values["previous-index.json"]["archive_membership_known"] = True
    if fault == "authority": complete["authority"]["backtesting_ready"] = True
    if fault == "unknown_key": complete["new_authority"] = True
    with pytest.raises(m.ConsumptionChainError):
        _chain(values)


def test_partial_refusal_still_consumes_every_started_and_no_unattempted_suffix(corpus):
    values, _, old = _controls(corpus)
    complete, index = values["complete.json"], values["consumed-index.json"]
    complete.update(started=1, unattempted=7, completed_without_refusal=False, results=complete["results"][:1])
    added = complete["results"][0]["accession_number"]
    index["accessions"] = sorted((*old, added))
    chain = _chain(_relink(values))
    assert m.consumed_accessions(chain) == tuple(sorted((*old, added)))
    assert m.public_summary(chain)["started_added_count"] == 1


@pytest.mark.parametrize("control", ("previous-index.json", "complete.json", "reservation.json"))
@pytest.mark.parametrize("kind", ("false_to_zero", "zero_to_false"))
def test_canonical_authority_types_cannot_be_laundered(corpus, control, kind):
    values, _, _ = _controls(corpus)
    authority = values[control]["authority"]
    key = next(key for key, value in authority.items()
        if (value is False if kind == "false_to_zero" else type(value) is int and value == 0))
    authority[key] = 0 if kind == "false_to_zero" else False
    if control == "previous-index.json":
        digest = m._sha(m._raw(values[control]))
        values["plan.json"]["consumption_sha256"] = digest
        values["consumed-index.json"]["previous_index_sha256"] = digest
        values["reservation.json"]["registration"]["known_consumed_index_sha256"] = digest
    with pytest.raises(m.ConsumptionChainError):
        _chain(_relink(values))


def test_registration_boolean_cannot_be_replaced_by_equal_integer(corpus):
    values, _, _ = _controls(corpus)
    registered = m._sha(m._raw(values["reservation.json"]["registration"]))
    values["reservation.json"]["registration"]["redirects_retries_aliases_or_pagination"] = 0
    values = _relink(values)
    values["complete.json"]["registration_sha256"] = registered
    with pytest.raises(m.ConsumptionChainError, match="reservation_crosslinks_refused"):
        _chain(values)


def test_adapter_refuses_cross_scope_result_and_poisoned_fullstream_propagates(corpus, monkeypatch):
    values, pipeline, _ = _controls(corpus)
    chain = _chain(values)
    adapter = m.required21_selection_builder(chain)
    monkeypatch.setattr(adapter.builder, "finish", lambda **kwargs: SimpleNamespace(to_payload=lambda: {"fixture_only": False}))
    with pytest.raises(m.ConsumptionChainError, match="chain_source_scope_differs"):
        adapter.finish()
    adapter = m.required21_selection_builder(chain)
    with pytest.raises(m.selection.Required21SelectionError):
        adapter.consume({"corrupt": "row"})
    with pytest.raises(m.selection.Required21SelectionError, match="closed"):
        adapter.finish(source_roster=pipeline[1], parent_audit=pipeline[2],
            expected_roster_sha256=pipeline[1].sha256, expected_audit_sha256=pipeline[2].sha256)


def test_fixture_controls_can_never_mint_actual_pinned_scope(corpus):
    values, _, _ = _controls(corpus)
    raws = _raws(values)
    with pytest.raises(m.ConsumptionChainError, match="actual_pin_scope_refused"):
        m._seal(raws, _pins(raws), fixture=False, selected_metadata_custody_verified=True)
    with pytest.raises(m.ConsumptionChainError, match="external_pin_refused"):
        m._seal(raws, m.CONTROL_PINS, fixture=False, selected_metadata_custody_verified=True)


@pytest.mark.parametrize("kind", ("clone", "fake", "dict", "wrong_token"))
def test_detached_or_forged_seal_never_grants_consumer_or_adapter(corpus, kind):
    values, _, _ = _controls(corpus)
    chain = _chain(values)
    fake = {"clone": lambda: replace(chain), "fake": lambda: SimpleNamespace(canonical_bytes=chain.canonical_bytes),
        "dict": lambda: m._decode(chain.canonical_bytes()),
        "wrong_token": lambda: m.ConsumptionChain(chain.canonical_bytes(), object())}[kind]()
    for operation in (m.public_summary, m.consumed_accessions, m.required21_selection_builder):
        with pytest.raises(m.ConsumptionChainError):
            operation(fake)


@pytest.mark.parametrize("raw", (b'{"a":1,"a":2}', b'{ "a":1}', b'{"a":1.0}', b'{"a":NaN}',
    b'[]', b'{"a":1}\n', b'\xff', b'', b'{}' * (m.MAX_CONTROL // 2 + 1)))
def test_strict_bounded_canonical_controls(raw):
    with pytest.raises(m.ConsumptionChainError):
        m._decode(raw)


def _write_root(tmp_path):
    root = tmp_path / "invented"
    root.mkdir(mode=0o700)
    (root / "scope.lock").write_bytes(b"lock\n")
    (root / "selected.json").write_bytes(b'{"invented":true}')
    for path in root.iterdir(): path.chmod(0o600)
    return root


def test_selected_hold_reads_only_named_metadata_and_preserves_unopened_extra(tmp_path, monkeypatch):
    root = _write_root(tmp_path)
    extra = root / "opaque-original.bin"
    extra.write_bytes(b"must never open")
    extra.chmod(0o600)
    actual_open = m.os.open
    seen = []
    def opened(path, *args, **kwargs):
        seen.append(path)
        assert path != "opaque-original.bin"
        return actual_open(path, *args, **kwargs)
    monkeypatch.setattr(m.os, "open", opened)
    held = m._SelectedHold(root, (), lock_bytes=b"lock\n")
    try:
        assert held.read("selected.json") == b'{"invented":true}'
        held.recheck()
        assert "opaque-original.bin" not in seen
    finally:
        held.close()


@pytest.mark.parametrize("fault", ("leaf_symlink", "leaf_hardlink", "leaf_mode", "root_symlink", "root_mode", "wrong_lock"))
def test_selected_hold_refuses_unsafe_custody(tmp_path, fault):
    root = _write_root(tmp_path)
    target = root / "selected.json"
    supplied = root
    if fault == "leaf_symlink": target.rename(root / "other"); target.symlink_to("other")
    if fault == "leaf_hardlink": os.link(target, root / "other")
    if fault == "leaf_mode": target.chmod(0o644)
    if fault == "root_symlink": supplied = tmp_path / "alias"; supplied.symlink_to(root, target_is_directory=True)
    if fault == "root_mode": root.chmod(0o755)
    held = None
    with pytest.raises((m.ConsumptionChainError, OSError)):
        try:
            held = m._SelectedHold(supplied, (), lock_bytes=b"wrong\n" if fault == "wrong_lock" else b"lock\n")
            held.read("selected.json")
        finally:
            if held is not None: held.close()


@pytest.mark.parametrize("fault", ("edit", "replace", "extra", "lock"))
def test_selected_hold_rechecks_before_and_after_selected_hashes(tmp_path, fault):
    root = _write_root(tmp_path)
    held = m._SelectedHold(root, (), lock_bytes=b"lock\n")
    try:
        held.read("selected.json")
        if fault == "edit": (root / "selected.json").write_bytes(b'{"invented":false}')
        if fault == "replace":
            (root / "selected.json").unlink()
            (root / "selected.json").write_bytes(b'{"invented":true}')
            (root / "selected.json").chmod(0o600)
        if fault == "extra": (root / "late.json").write_bytes(b"{}"); (root / "late.json").chmod(0o600)
        if fault == "lock": (root / "scope.lock").write_bytes(b"other\n")
        with pytest.raises(m.ConsumptionChainError): held.recheck()
    finally:
        held.close()


def test_actual_pin_failure_precedes_other_control_reads(monkeypatch):
    seen = []
    def read(name, **kwargs):
        seen.append(name)
        return b"untrusted"
    with pytest.raises(m.ConsumptionChainError, match="external_pin_refused"):
        m._actual_raws(SimpleNamespace(read=read), SimpleNamespace(read=read))
    assert seen == ["complete.json"]


def test_late_directory_addition_during_final_selected_rehash_refuses(tmp_path, monkeypatch):
    root = _write_root(tmp_path)
    held = m._SelectedHold(root, (), lock_bytes=b"lock\n")
    try:
        held.read("selected.json")
        original = held.read
        inserted = False
        def read(name, **kwargs):
            nonlocal inserted
            raw = original(name, **kwargs)
            if name == "selected.json" and not inserted:
                inserted = True
                (root / "late.json").write_bytes(b"{}")
                (root / "late.json").chmod(0o600)
            return raw
        monkeypatch.setattr(held, "read", read)
        with pytest.raises(m.ConsumptionChainError):
            held.recheck()
        assert inserted
    finally:
        held.close()


def test_actual_raw_reader_fixed_names_only_and_each_pin_precedes_next_read(corpus, monkeypatch):
    values, _, _ = _controls(corpus)
    raws = _raws(values)
    monkeypatch.setattr(m, "CONTROL_PINS", _pins(raws))
    opened = []
    def required(name, **kwargs):
        assert name in {"complete.json", "reservation.json", "plan.json", "consumed-index.json"}
        opened.append(("required", name))
        return raws[name]
    def prior(name, **kwargs):
        assert name == "consumed-index.json"
        opened.append(("prior", name))
        return raws["previous-index.json"]
    assert m._actual_raws(SimpleNamespace(read=required), SimpleNamespace(read=prior)) == raws
    assert opened == [("required", name) for name in
        ("complete.json", "reservation.json", "plan.json", "consumed-index.json")] + [("prior", "consumed-index.json")]


def test_actual_entry_refuses_before_any_private_inputs_without_native_flags(monkeypatch):
    monkeypatch.setattr(m, "_SelectedHold", lambda *args, **kwargs: pytest.fail("private input reached"))
    with pytest.raises(m.ConsumptionChainError, match="native_refused"):
        m.read_actual_chain(memory=None)
