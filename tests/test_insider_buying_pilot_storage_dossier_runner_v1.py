"""Invented sources only; the caller supplies native process-tree denial."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX retained custody")
from research import insider_buying_pilot_storage_dossier_runner_v1 as m


def _helper(name):
    spec = importlib.util.spec_from_file_location("storage_dossier_fixture_" + name[:-3], Path(__file__).with_name(name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pin(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _metadata():
    selected = []
    for i in range(12):
        warm = i < 8
        ordinal = i if warm else m.controls.RECENT_POSITIONS[i - 8]
        accession = f"0000123456-20-{i+1:06d}" if warm else m.controls.recent.FIXED_ACCESSIONS[ordinal]
        period, day = ("2020Q4", "2020-10-01") if warm else ("2022Q4", "2022-11-17") if i < 10 else ("2023Q1", "2023-02-06")
        pin = {"bytes": 1, "sha256": f"{i+1:064x}"}
        root = m.controls.WARM_ROOT if warm else m.controls.RECENT_ROOT
        target = {"period": period, "accession_number": accession, "form_type": "4", "filing_date": day,
                  "issuer_cik": "0000123456", "quarterly_index_sha256": "a" * 64,
                  "complete_submission_url": "https://www.sec.gov/Archives/edgar/data/123456/" + accession + ".txt"}
        selected.append({"case_id": ("warmup" if warm else "recent") + f"-{i+1 if warm else i-7:02d}",
                         "group": "warmup" if warm else "recent", "ordinal": ordinal, "target": target,
                         "body_path": str(root / "objects" / (pin["sha256"] + ".bin")), "body_pin": pin,
                         "recorded_projection": {}})
    source_names = {str(m.controls.WARM_ROOT / name) for name in (*m.controls.WARM_PINS, "scope.lock",
                    *(f"request-{i:03d}-result.json" for i in range(8)))}
    source_names.update(str(m.controls.RECENT_ROOT / name) for name in (*m.controls.RECENT_PINS, "commit.json"))
    return {"schema": m.controls.SCHEMA + "/metadata", "fixture_only": False,
            "warm_root": str(m.controls.WARM_ROOT), "recent_root": str(m.controls.RECENT_ROOT),
            "selected": selected, "warm_readback_leaves": m.controls._warm_leaves(selected, fixture=False),
            "source_pins": {name: {"bytes": 1, "sha256": "a" * 64} for name in source_names},
            "warm_complete_sha256": "b" * 64, "full_root_inventory_verified": False,
            "bodies_replayed": False, "authority": m.controls._authority()}


def _bound():
    sources = {m.SELF: "a" * 64}
    return {"root": str(m.ROOT), "branch": m.BRANCH, "head": "b" * 40, "clean": True,
            "source_sha256": sources, "source_inventory_sha256": m.sha(m.raw(sources))}


def test_selected_original_paths_have_exact_fixed_scope_without_reading_sources():
    metadata = _metadata()
    paths = m.selected_paths(metadata)
    assert len(paths) == len(set(paths)) == 12
    assert sum(path.is_relative_to(m.controls.WARM_ROOT) for path in paths) == 8
    assert sum(path.is_relative_to(m.controls.RECENT_ROOT) for path in paths) == 4


@pytest.mark.parametrize("fault", ("fixture", "count", "duplicate", "outside", "path-pin", "authority", "recent-position"))
def test_selected_paths_refuse_mutated_metadata_before_native_grant(fault):
    value = _metadata()
    if fault == "fixture": value["fixture_only"] = True
    elif fault == "count": value["selected"].pop()
    elif fault == "duplicate": value["selected"][1]["body_path"] = value["selected"][0]["body_path"]
    elif fault == "outside": value["selected"][0]["body_path"] = "/private/PRIVATE-ACCOUNT"
    elif fault == "path-pin": value["selected"][0]["body_pin"]["sha256"] = "f" * 64
    elif fault == "authority": value["authority"]["point_in_time_data"] = True
    else: value["selected"][8]["ordinal"] = 1
    with pytest.raises(ValueError):
        m.selected_paths(value)


def test_metadata_authenticates_external_completion_then_transitive_metadata_pin(monkeypatch):
    metadata = _metadata(); metadata_raw = m.raw(metadata)
    complete = {"published_leaf_pins": {"controls-metadata.json": _pin(metadata_raw)}}
    complete_raw = m.raw(complete)
    monkeypatch.setitem(m.prior.PINS, "provider_complete", _pin(complete_raw))
    reads = []
    class Provider:
        def read(self, name, pin, *, check):
            reads.append((name, pin)); check()
            return {"complete.json": complete_raw, "controls-metadata.json": metadata_raw}[name]
    found, selected, pin = m._metadata(Provider(), Guard())
    assert found == complete and selected == metadata and pin == _pin(metadata_raw)
    assert [name for name, _ in reads] == ["complete.json", "controls-metadata.json"]


def test_wrong_external_completion_pin_refuses_before_metadata_selection(monkeypatch):
    monkeypatch.setattr(m, "selected_paths", lambda _value: pytest.fail("selected unauthenticated metadata"))
    class Provider:
        def read(self, *_a, **_k): return b"{}"
    with pytest.raises(m.prior.AuditRunnerError, match="input_pin_refused"):
        m._metadata(Provider(), Guard())


def test_worker_policy_has_exact_original_leaves_and_no_source_root_subtree():
    metadata = _metadata(); policy = m.policy(_bound(), metadata=metadata)
    for token in ("(deny network*)", "(deny process-fork)", "(deny file-write*)", "(deny process-exec)"):
        assert token in policy
    for path in (*m.selected_paths(metadata), m.METADATA_PATH):
        assert '(literal "' + str(path) + '")' in policy
    for path in (m.ROOT, m.controls.WARM_ROOT, m.controls.RECENT_ROOT, m.stable.PRIVATE_CUSTODY_ROOT):
        assert '(subpath "' + str(path) + '")' not in policy


def test_parent_policy_limits_publication_to_the_new_epoch_and_git_metadata(monkeypatch):
    monkeypatch.setattr(m.subprocess, "check_output", lambda *_a, **_k: b"/invented-admin/.git\n")
    profile = m.policy(_bound(), metadata=_metadata(), parent=True)
    assert "(deny process-fork)" not in profile and "(deny network*)" in profile
    assert '(allow file-write* (subpath "' + str(m.OUTPUT) + '")' in profile
    assert '(literal "/dev/null")' in profile
    assert '(subpath "' + str(m.stable.PRIVATE_CUSTODY_ROOT) + '")' not in profile
    assert '(allow file-read-data (subpath "/invented-admin/.git"))' in profile


def test_identity_uses_a_git_verified_legacy_shape_and_includes_every_new_image(monkeypatch):
    base = _bound(); seen = []
    monkeypatch.setattr(m.producer, "_identity", lambda _head: deepcopy(base))
    monkeypatch.setattr(m.producer, "_current", lambda value: seen.append(deepcopy(value)))
    monkeypatch.setattr(m.subprocess, "check_output", lambda args, **_k: (m.ROOT / args[-1].split(":", 1)[1]).read_bytes())
    value = m.identity(base["head"])
    assert set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
    assert set(m.OWN) <= set(value["source_sha256"])
    assert value["source_inventory_sha256"] == m.sha(m.raw(value["source_sha256"]))
    assert seen == [value] and m.compact(value)["sources"] == value["source_sha256"]


def test_identity_refuses_working_image_that_differs_from_committed_blob(monkeypatch):
    monkeypatch.setattr(m.producer, "_identity", lambda _head: _bound())
    monkeypatch.setattr(m.subprocess, "check_output", lambda *_a, **_k: b"different committed image")
    with pytest.raises(m.StorageDossierError, match="source_refused"):
        m.identity("b" * 40)


def _worker_result():
    helper = _helper("test_insider_buying_pilot_historical_dossier_v1.py")
    transition_helper = _helper("test_insider_buying_pilot_storage_transition_v1.py")
    bound = _bound(); compact = m.compact(bound)
    physical, proof, qualification, pins, _execution = transition_helper.inputs()
    receipt = m.transition.build_transition(physical, proof, qualification, pins, compact, fixture_only=False)
    identities, cases = [], []
    for i in range(12):
        accession = f"0000999999-22-{i+1:06d}"
        target = replace(helper.sec._target(), accession_number=accession,
                         complete_submission_url="https://www.sec.gov/Archives/edgar/data/888888/" + accession + ".txt")
        body = helper.sec._complete(xml=helper._xml("<nonDerivativeTable>" + helper._entry() + "</nonDerivativeTable>"))
        body = body.replace(b"0000999999-22-000001", accession.encode())
        projected = m.controls.project_sec_complete_submission(target, body)
        evidence = m.dossier.extract_identity(projected); identities.append(evidence)
        cases.append({"case_id": ("warmup" if i < 8 else "recent") + f"-{i+1 if i<8 else i-7:02d}",
                      "cik": evidence["issuer_cik"], "accession": evidence["accession"], "form_type": evidence["form_type"],
                      "filing_date": evidence["filing_date"], "acceptance_digits": evidence["acceptance_digits"],
                      "source_symbol": evidence["source_symbol"], "body_sha256": evidence["body_sha256"]})
    values = list(helper.ref._inputs(cases=cases)); values[1]["fixture_only"] = False; values[4] = pins
    audited = m.prior.audit.build_audit(*values, fixture_only=False)
    derived = m.dossier.build_dossier(cases, identities, audited, receipt.sha256, compact, fixture_only=False)
    private = m.dossier.private_payload(derived)
    # Invent a serialized aggregate with the fixed production row envelope.
    # No retained data or hundreds of thousands of fixture rows are needed to
    # exercise the parent's strict cross-links, accounting and authority checks.
    counts = private["reference_counts"]
    counts["ticker_rows"] = 74150
    counts["action_categories"]["other"] += 698455 - counts["action_rows"]
    counts["action_rows"] = 698455
    reference = {"schema": m.prior.audit.SCHEMA, "fixture_only": False, "source_pins": pins,
                 "counts": counts, "controls": [row["current_reference_evidence"] for row in private["controls"]],
                 "missing_evidence": list(m.prior.audit.MISSING_EVIDENCE), "authority": m.prior.audit.authority()}
    reference_hash = m.sha(m.raw(reference)); private["reference_audit_sha256"] = reference_hash
    audit_summary = {"schema": m.prior.audit.SCHEMA, "fixture_only": False, "counts": counts,
                     "authority": m.prior.audit.authority(), "source_pins": pins, "result_sha256": reference_hash}
    summary = m.dossier.summary_from_payload(private, receipt.sha256, compact, fixture_only=False)
    value = {"completed": True, "transition": receipt.to_payload(), "dossier": private,
             "audit_summary": audit_summary, "dossier_summary": summary,
             "metadata_pin": _pin(b"invented metadata"), "current_storage_identity": physical,
             "input_leaves": 20, "source_inventory_sha256": bound["source_inventory_sha256"]}
    # The real parent receives JSON over a pipe, which has no shared dict
    # aliases. Preserve that boundary so mutations test the intended guard.
    return json.loads(m.raw(value)), bound


def test_parent_accepts_a_consistent_private_worker_result_without_inventing_history():
    value, bound = _worker_result()
    m.validate_result(value, bound, value["metadata_pin"], value["current_storage_identity"])


def _readback_fixture():
    value, bound = _worker_result(); physical = value["current_storage_identity"]
    data = {"reservation.json": {"schema": m.stable.SCHEMA + "/reservation", "code_identity": bound,
        "registration": m.registration(), "fixture_only": False,
        "storage": {"root_kind": "fixed_user_application_support", "policy": m.stable.SCHEMA,
            "audit_id": m.AUDIT_ID, "identity": physical}},
        "observation-started.json": {"schema": m.SCHEMA + "/started", "metadata_pin": value["metadata_pin"],
            "authority": m.transition.authority()}, "transition.json": value["transition"], "dossier.json": value["dossier"]}
    complete = {"schema": m.SCHEMA + "/complete", "fixture_only": False, "audit_id": m.AUDIT_ID,
        "storage_identity": physical, "published_leaf_pins": {}, "audit_summary": value["audit_summary"],
        "dossier_summary": value["dossier_summary"], "metadata_pin": value["metadata_pin"],
        "input_leaves": 20, "authority": m.transition.authority()}
    data["complete.json"] = complete
    return {"schema": m.stable.SCHEMA + "/readback", "audit_id": m.AUDIT_ID,
            "controls": data, "pins": {}, "storage_identity": physical}, bound


def _seal_readback(value):
    complete = value["controls"]["complete.json"]
    complete["published_leaf_pins"] = {name: _pin(m.raw(data)) for name, data in value["controls"].items() if name != "complete.json"}
    value["pins"] = {name: _pin(m.raw(data)) for name, data in value["controls"].items()}
    return value["pins"]["complete.json"]["sha256"]


def test_complete_readback_revalidates_every_private_contract_and_cross_link():
    value, bound = _readback_fixture(); pin = _seal_readback(value)
    assert m.validate_readback(value, bound, pin) is value["controls"]["complete.json"]


@pytest.mark.parametrize("fault", ("audit-counts", "audit-pins", "summary-authority", "reservation-registration",
    "reservation-identity", "started-metadata", "complete-fixture", "complete-extra", "wrong-external-hash"))
def test_readback_refuses_semantic_mutations_even_when_internal_pins_are_recomputed(fault):
    value, bound = _readback_fixture(); data = value["controls"]; complete = data["complete.json"]
    if fault == "audit-counts": complete["audit_summary"]["counts"]["provider_refused_attempts"] += 1
    elif fault == "audit-pins": complete["audit_summary"]["source_pins"]["provider_complete"]["sha256"] = "0" * 64
    elif fault == "summary-authority": complete["dossier_summary"]["authority"]["point_in_time_data"] = True
    elif fault == "reservation-registration": data["reservation.json"]["registration"]["purpose"] = "invented"
    elif fault == "reservation-identity": data["reservation.json"]["code_identity"] = {**bound, "head": "c" * 40}
    elif fault == "started-metadata": data["observation-started.json"]["metadata_pin"] = _pin(b"other")
    elif fault == "complete-fixture": complete["fixture_only"] = True
    elif fault == "complete-extra": complete["PRIVATE-UNKNOWN"] = True
    pin = _seal_readback(value)
    if fault == "wrong-external-hash": pin = "0" * 64
    with pytest.raises(ValueError):
        m.validate_readback(value, bound, pin)


@pytest.mark.parametrize("fault", ("transition-authority", "transition-history", "transition-fixture", "transition-current-root",
    "dossier-authority", "dossier-history", "dossier-fixture", "dossier-known-by", "dossier-transition-pin",
    "dossier-controls", "dossier-duplicate-control", "dossier-original-count", "audit-authority", "summary-authority",
    "metadata-pin", "source-inventory", "input-leaves", "completed-bool-alias", "extra-key"))
def test_parent_refuses_forged_worker_contracts_before_publication(fault):
    value, bound = _worker_result(); expected_pin = deepcopy(value["metadata_pin"]); physical = deepcopy(value["current_storage_identity"])
    if fault == "transition-authority": value["transition"]["authority"]["backtesting_ready"] = True
    elif fault == "transition-history": value["transition"]["historical_physical_continuity_established"] = True
    elif fault == "transition-fixture": value["transition"]["fixture_only"] = True
    elif fault == "transition-current-root": value["transition"]["current_storage_identity"]["inode"] += 1
    elif fault == "dossier-authority": value["dossier"]["authority"]["point_in_time_data"] = True
    elif fault == "dossier-history": value["dossier"]["historical_binding_passed"] = True
    elif fault == "dossier-fixture": value["dossier"]["fixture_only"] = True
    elif fault == "dossier-known-by": value["dossier"]["controls"][0]["historical_public_known_by"] = "2020-10-01T09:00:00-04:00"
    elif fault == "dossier-transition-pin": value["dossier"]["transition_sha256"] = "0" * 64
    elif fault == "dossier-controls": value["dossier"]["controls"].pop()
    elif fault == "dossier-duplicate-control": value["dossier"]["controls"][1] = deepcopy(value["dossier"]["controls"][0])
    elif fault == "dossier-original-count": value["dossier"]["counts"]["originals_reparsed"] = 11
    elif fault == "audit-authority": value["audit_summary"]["authority"]["point_in_time_data"] = True
    elif fault == "summary-authority": value["dossier_summary"]["authority"]["canonical_admitted"] = True
    elif fault == "metadata-pin": value["metadata_pin"]["sha256"] = "0" * 64
    elif fault == "source-inventory": value["source_inventory_sha256"] = "0" * 64
    elif fault == "input-leaves": value["input_leaves"] = 19
    elif fault == "completed-bool-alias": value["completed"] = 1
    else: value["PRIVATE-UNEXPECTED"] = "PRIVATE SOURCE"
    with pytest.raises(ValueError):
        m.validate_result(value, bound, expected_pin, physical)


class Guard:
    def check(self): pass
    def close(self): pass


def _run_setup(monkeypatch, value, bound, *, storage=None, collision=False):
    events, instances = [], []
    metadata = _metadata()
    monkeypatch.setattr(m, "identity", lambda _head: deepcopy(bound))
    monkeypatch.setattr(m, "policy", lambda *_a, **_k: "invented policy")
    monkeypatch.setattr(m, "install_parent_policy", lambda _profile: None)
    monkeypatch.setattr(m, "prove_parent", lambda: None)
    monkeypatch.setattr(m.stable.native, "_WorkerMemoryGuard", Guard)
    def launch(function, *_a, **_k):
        events.append(function)
        return {"completed": True, "metadata": metadata, "metadata_pin": value["metadata_pin"]} if function == "discovery_worker" else value
    monkeypatch.setattr(m, "launch", launch)
    class Epoch:
        def __init__(self, *_a, **_k):
            events.append("epoch")
            if collision: raise m.stable.CustodyError("namespace_consumed", "epoch")
            self.storage_identity = deepcopy(storage or value["current_storage_identity"])
            self.pins = {"reservation.json": _pin(b"invented reservation")}; instances.append(self)
        def publish(self, name, body):
            events.append(name); self.pins[name] = _pin(m.raw(body)); return self.pins[name]["sha256"]
        def check(self): events.append("check")
        def close(self): events.append("close")
    monkeypatch.setattr(m.stable, "Epoch", Epoch)
    return events, instances


def test_parent_publishes_once_in_order_after_validating_the_result(monkeypatch):
    value, bound = _worker_result(); events, instances = _run_setup(monkeypatch, value, bound)
    result = m.run(bound["head"])
    assert result["completed"] is True and len(instances) == 1
    assert [item for item in events if item.endswith(".json")] == ["observation-started.json", "transition.json", "dossier.json", "complete.json"]
    assert result["complete_sha256"] == instances[0].pins["complete.json"]["sha256"]


def test_parent_storage_mismatch_refuses_before_transition_or_dossier_publication(monkeypatch):
    value, bound = _worker_result(); storage = {**value["current_storage_identity"], "inode": 999}
    events, _ = _run_setup(monkeypatch, value, bound, storage=storage)
    with pytest.raises(m.StorageDossierError): m.run(bound["head"])
    assert "transition.json" not in events and "dossier.json" not in events and "complete.json" not in events


def test_namespace_collision_does_not_dispatch_or_resume_an_observation(monkeypatch):
    value, bound = _worker_result(); events, instances = _run_setup(monkeypatch, value, bound, collision=True)
    with pytest.raises(m.StorageDossierError): m.run(bound["head"])
    assert events.count("discovery_worker") == 1 and "dossier_worker" not in events and not instances


def test_original_join_refuses_short_case_list_before_opening_or_parsing(monkeypatch):
    monkeypatch.setattr(m.controls, "_Hold", lambda *_: pytest.fail("truncated join opened an original"))
    with pytest.raises(m.StorageDossierError):
        m._originals(_metadata(), [], Guard(), [])


@pytest.mark.parametrize("attribute", ("st_ctime_ns", "st_gid", "st_flags"))
def test_body_holder_rechecks_full_version_fields_even_when_content_matches(tmp_path, monkeypatch, attribute):
    root = tmp_path / "invented-originals"; (root / "objects").mkdir(mode=0o700, parents=True)
    root.chmod(0o700); data = b"invented original"; name = "objects/" + m.sha(data) + ".bin"
    path = root / name; path.write_bytes(data); path.chmod(0o600)
    held = m.BodyHold(root)
    try:
        assert held.read(name, cap=len(data), pin=(len(data), m.sha(data))) == data
        target = held.leaves[name][0]; original = m.os.fstat
        class Changed:
            def __init__(self, wrapped): self.wrapped = wrapped
            def __getattr__(self, key):
                value = getattr(self.wrapped, key)
                return value + 1 if key == attribute else value
        monkeypatch.setattr(m.os, "fstat", lambda fd: Changed(original(fd)) if fd == target else original(fd))
        with pytest.raises(ValueError): held.check()
    finally:
        held.close()


def test_cleanup_exhausts_holders_and_rejects_a_failed_close():
    events = []
    class Broken:
        def close(self): events.append("broken"); raise OSError("PRIVATE")
    class Other:
        def close(self): events.append("other")
    class Memory:
        def close(self): events.append("guard")
    with pytest.raises(SystemExit) as caught: m._close([Other(), Broken()], Memory())
    assert caught.value.code == 2 and events == ["broken", "other", "guard"]
