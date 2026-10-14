"""Synthetic OWN47 proofs; executed sources, real outcomes and providers frozen."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from fractions import Fraction
import json
import os
import socket

import pytest

from research.target_price_revisions_development import raw_market_dividend_correction as correction
from research.target_price_revisions_development import raw_market_inputs as frozen
from research.target_price_revisions_development import raw_candidate, raw_backtest
import test_raw_market_resume as synthetic
from test_raw_market_inputs import inputs, attach

resume, market, source = correction.resume, correction.market, correction.source
NOW, canonical, digest = synthetic.NOW, source._canonical, source._digest


@pytest.fixture(autouse=True)
def no_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("provider/credential access during synthetic correction proof")
    monkeypatch.setattr(resume, "_FIXED_RESOLVER", forbidden)
    monkeypatch.setattr(resume, "_FIXED_TRANSPORT", forbidden)
    monkeypatch.setattr(source, "_FIXED_RESOLVER", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def test_production_freeze_preserves_original_historical_head_not_current_head(monkeypatch):
    # Pure synthetic plan construction, no private original-plan read/execution.
    old = synthetic.original_plan().body()
    args = {key: old[key] for key in ("structure_sha256", "waiver_sha256", "code_hashes", "candidate_policy_sha256",
        "owner_instruction_sha256", "created_utc", "expires_utc")}
    original = market.freeze_capture_plan(**args, tickers=synthetic.TICKERS, git_sha="b" * 40)
    monkeypatch.setattr(resume.detail.prior, "ORIGINAL_PLAN_SHA256", original.sha256)
    parent = resume.freeze_resume_plan(original, probe_report_sha256=resume.PROBE_SHA, probe_code_sha256=resume.PROBE_CODE,
        request_mode="three", code_sha256=correction.RESUME_CODE, git_sha=resume.detail.HEAD,
        owner_instruction_sha256=resume.detail.OWNER, created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=11)).isoformat())
    monkeypatch.setattr(correction, "RECORDED", dict(correction.RECORDED, resume_plan_sha256=parent.sha256))
    args = {key: correction.RECORDED[key] for key in ("capture_report_sha256", "projection_sha256",
        "first_simulation_report_sha256", "first_private_result_sha256")}
    plan = correction.freeze_correction_plan(original, parent, **args, code_sha256="d" * 64, git_sha=resume.detail.HEAD,
        owner_instruction_sha256=resume.detail.OWNER, created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=10)).isoformat())
    assert plan.body()["resume_plan"]["original_plan"]["git_sha"] == "b" * 40
    assert plan.body()["git_sha"] == resume.detail.HEAD
    for key in ("capture_report_sha256", "projection_sha256", "first_simulation_report_sha256", "first_private_result_sha256"):
        with pytest.raises(ValueError, match="exact executed chain"):
            correction.freeze_correction_plan(original, parent, **dict(args, **{key: "a" * 64}), code_sha256="d" * 64,
                git_sha=resume.detail.HEAD, owner_instruction_sha256=resume.detail.OWNER,
                created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=10)).isoformat())
    def invalid_source(_body):
        raise ValueError("synthetic changed correction source")
    monkeypatch.setattr(correction, "_identity", invalid_source)
    monkeypatch.setattr(correction.raw_run, "_open_root", lambda *_: pytest.fail("root opened before code identity"))
    with pytest.raises(ValueError, match="changed correction source"):
        correction.execute_correction(plan)


def test_exact_dividend_na_is_narrowly_interpreted_with_native_id_and_mutation_free_inputs():
    structure, stocks, actions = inputs()
    attach(structure, actions, contra="N/A")
    before = deepcopy((structure, stocks, actions))
    baseline = frozen.convert(structure, stocks, actions)
    assert baseline["corporate_actions"][0]["kind"] == "unresolved"
    prepared = correction.convert_dividend_correction(structure, stocks, actions)
    event = prepared["corporate_actions"][0]
    assert event["kind"] == "cash_dividend" and event["value"] == "1"
    assert event["action_id"] == digest(frozen._canonical(actions[0])) == baseline["corporate_actions"][0]["action_id"]
    assert (structure, stocks, actions) == before
    assert prepared["evidence"]["dividend_counterparty_interpretation"] == correction.ASSUMPTION
    assert prepared["evidence"]["native_action_ids_preserved"] is True
    assert prepared["evidence"]["universal_vendor_null_semantics_verified"] is False


@pytest.mark.parametrize("kind,contra", [("stockdividend", "N/A"), ("split", "N/A"), ("acquisitioncash", "N/A"),
    ("dividend", "ZZOTHER"), ("dividend", "n/a"), ("dividend", " N/A"), ("dividend", "NA"), ("sicchangefrom", "N/A")])
def test_nonmatching_or_counterparty_economics_remain_unresolved(kind, contra):
    structure, stocks, actions = inputs()
    attach(structure, actions, kind=kind, contra=contra)
    corrected = correction.convert_dividend_correction(structure, stocks, actions)
    assert corrected["corporate_actions"] == frozen.convert(structure, stocks, actions)["corporate_actions"]
    assert corrected["corporate_actions"][0]["kind"] == "unresolved"
    assert corrected["evidence"]["interpreted_native_action_count"] == 0


def test_duplicate_native_rows_keep_one_original_id_and_count_without_double_entitlement():
    structure, stocks, actions = inputs()
    attach(structure, actions, contra="N/A")
    corrected = correction.convert_dividend_correction(structure, stocks, actions + [dict(actions[0])])
    assert len(corrected["corporate_actions"]) == 1
    assert corrected["evidence"]["duplicate_action_rows"] == 1
    assert corrected["evidence"]["interpreted_native_action_count"] == 1


@pytest.mark.parametrize("contra,value", [(None, "0.4"), ("", "0.4"), (None, "0.5"), ("N/A", "0.5")])
def test_interpretation_or_native_conflict_is_refused_not_collapsed(contra, value):
    structure, stocks, actions = inputs()
    attach(structure, actions, contra="N/A")
    with pytest.raises(ValueError, match="collision|conflicting"):
        correction.convert_dividend_correction(structure, stocks, actions + [dict(actions[0], contraticker=contra, value=value)])


def test_missing_same_exdate_factor_does_not_borrow_next_session_factor():
    structure, stocks, actions = inputs()
    attach(structure, actions, contra="N/A")
    corrected = correction.convert_dividend_correction(structure, [row for row in stocks if row["date"] != "2025-01-13"], actions)
    assert corrected["corporate_actions"][0]["kind"] == "unresolved"
    assert corrected["corporate_actions"][0]["value"] is None


def test_corrected_cash_entitlement_is_for_prior_holder_not_exdate_buyer_or_spendable_cash():
    structure, stocks, actions = inputs()
    attach(structure, actions, contra="N/A")
    prepared = correction.convert_dividend_correction(structure, stocks, actions)
    event = prepared["corporate_actions"][0]
    session = next(row for row in prepared["outcomes"]["sessions"] if row["session_id"] == event["session_id"])
    previous = next(row for row in prepared["outcomes"]["sessions"] if row["session_id"] == "2025-01-06")
    sid = event["security_id"]
    frame = {"session_id": session["session_id"], "cutoff_utc": previous["close_utc"],
        "weights": ({"security_id": sid, "weight": "0.1"},),
        "decision_marks": ({"security_id": sid, "price": "5", "available_at_utc": previous["close_utc"]},)}
    common = dict(security_inventory=({"security_id": sid, "asset_type": "common-stock"},),
        sessions=(dict(previous, bars=tuple(previous["bars"])), dict(session, bars=tuple(session["bars"]))), corporate_actions=(event,))
    blocked = dict(common, sessions=(common["sessions"][0], dict(session, bars=tuple(dict(bar, tradable=False) for bar in session["bars"]))))
    held = raw_backtest.run_raw_revision_backtest(**blocked, initial_cash="0", initial_positions=({"security_id": sid, "quantity": 20},), targets=(frame,))
    assert held.final_dividend_receivable == "20" and held.final_cash == "0"
    assert held.corporate_action_accounting_complete is True and held.fills == ()
    buyer = raw_backtest.run_raw_revision_backtest(**common, initial_cash="1000", initial_positions=(), targets=(frame,))
    assert buyer.fills and buyer.final_dividend_receivable == "0"


@pytest.fixture
def chain(tmp_path, monkeypatch):
    original_structure = synthetic.structure
    def structured():
        body = original_structure()
        body["actions"] = [{"ticker": synthetic.TICKERS[0], "date": "2025-01-06", "action": "dividend"}]
        return body
    # Reuse synthetic fixture-building helpers; no production global is patched.
    monkeypatch.setattr(synthetic, "structure", structured)
    bundle = synthetic.bundle.__wrapped__(tmp_path)
    parent = synthetic.plan(bundle)
    def transport(dataset, batch, key, budget):
        if dataset == "stocks":
            return synthetic.transport(dataset, batch, key, budget)
        rows = [{"ticker": synthetic.TICKERS[0], "date": "2025-01-06", "action": "dividend", "value": "0.4", "contraticker": "N/A"}]
        return synthetic.response(dataset, rows if synthetic.TICKERS[0] in batch else [])
    capture = synthetic.capture(bundle, parent, fetch=transport)
    first = resume._execute_fixture_backtest(parent, capture.sha256, bundle["root"], now=NOW)
    report = json.loads(first.payload)
    assert report["status"] == "SIMULATED" and report["summary"]["corporate_action_accounting_complete"] is False
    return dict(bundle, parent=parent, capture=capture, first=first, first_report=report)


def plan(chain, **changes):
    args = dict(capture_report_sha256=chain["capture"].sha256, projection_sha256=json.loads(chain["capture"].payload)["projection_sha256"],
        first_simulation_report_sha256=chain["first"].sha256, first_private_result_sha256=chain["first_report"]["private_report_sha256"],
        code_sha256="d" * 64, git_sha="b" * 40, owner_instruction_sha256=resume.detail.OWNER,
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=10)).isoformat(), mode="offline-fixture")
    args.update(changes)
    return correction.freeze_correction_plan(chain["original"], chain["parent"], **args)


def test_connected_one_new_fixture_run_claims_before_outcomes_and_preserves_all_old_files(chain, monkeypatch, capsys):
    root, frozen_plan = chain["root"], plan(chain)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    read = market.raw_run._read_file
    def guarded(fd, name, *args):
        if name.endswith((".backtest.json", ".projection.json")):
            claim = json.loads((root / (correction.CORRECTION_ID + ".spent.json")).read_bytes())
            assert claim["correction_plan_sha256"] == frozen_plan.sha256
            assert claim["fixture_runs"] == 1 and claim["additional_development_look_reserved"] == 0
        return read(fd, name, *args)
    monkeypatch.setattr(market.raw_run, "_read_file", guarded)
    result = correction._execute_fixture(frozen_plan, root, now=NOW)
    report = json.loads(result.payload)
    assert report["status"] == "SIMULATED", report
    assert report["summary"]["study_sessions"] == 60 and report["summary"]["corporate_action_accounting_complete"] is True
    assert Fraction(report["summary"]["final_dividend_receivable"]) > 0 and report["summary"]["fills"] > 0
    assert report["accounting_evidence"]["interpreted_native_action_count"] == 1
    assert report["additional_development_looks"] == report["cumulative_development_looks"] == report["provider_requests"] == report["quantconnect_attempts"] == 0
    assert report["prior_look_or_simulation_rearmed"] is report["canonical_admission"] is report["contractual_rights_verified"] is report["trading"] is False
    assert all((root / name).read_bytes() == payload for name, payload in before.items())
    assert all(value not in result.payload for value in (b"ZZ000", b"SHARADAR:", synthetic.KEY.encode()))
    assert b"ZZ000" not in correction.public_plan_summary(frozen_plan)
    with pytest.raises(ValueError, match="already spent"):
        correction._execute_fixture(frozen_plan, root, now=NOW)
    with pytest.raises(ValueError, match="already spent"):
        correction._execute_fixture(plan(chain, code_sha256="e" * 64), root, now=NOW)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("binding", ["capture_report_sha256", "projection_sha256", "first_simulation_report_sha256", "first_private_result_sha256"])
def test_mismatched_chain_never_claims_or_opens_outcomes(chain, monkeypatch, binding):
    frozen_plan = plan(chain, **{binding: "f" * 64})
    read = market.raw_run._read_file
    def guarded(fd, name, *args):
        if name.endswith((".projection.json", ".backtest.json")):
            pytest.fail("outcome opened before chain admitted")
        return read(fd, name, *args)
    monkeypatch.setattr(market.raw_run, "_read_file", guarded)
    with pytest.raises((ValueError, OSError)):
        correction._execute_fixture(frozen_plan, chain["root"], now=NOW)
    assert not (chain["root"] / (correction.CORRECTION_ID + ".spent.json")).exists()


@pytest.mark.parametrize("suffix", ["projection.json", "backtest.json"])
def test_changed_private_outcome_fails_after_claim_without_rerun(chain, suffix):
    frozen_plan = plan(chain)
    target = chain["capture"].projection_path if suffix == "projection.json" else chain["first"].report_path
    target.write_bytes(b"{}\n")
    result = correction._execute_fixture(frozen_plan, chain["root"], now=NOW)
    report = json.loads(result.payload)
    assert report["status"] == "FAILED" and report["summary"] is None
    assert report["failure_stage"] == ("projection" if suffix == "projection.json" else "prior_result")
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"
    with pytest.raises(ValueError, match="already spent"):
        correction._execute_fixture(frozen_plan, chain["root"], now=NOW)


def test_public_api_rejects_fixture_before_opening_root_and_unsafe_path_stays_closed(chain):
    frozen_plan = plan(chain)
    with pytest.raises(ValueError, match="production-only"):
        correction.execute_correction(frozen_plan)
    with pytest.raises(ValueError, match="synthetic root"):
        correction._execute_fixture(frozen_plan, market.PRODUCTION_ROOT, now=NOW)
    target = chain["root"] / (correction.CORRECTION_ID + ".spent.json")
    target.symlink_to(chain["root"] / "rights.json")
    before = (chain["root"] / "rights.json").read_bytes()
    with pytest.raises(ValueError, match="already spent"):
        correction._execute_fixture(frozen_plan, chain["root"], now=NOW)
    assert (chain["root"] / "rights.json").read_bytes() == before


def test_rehashed_authority_or_custody_expansion_refuses(chain):
    original = plan(chain)
    for key, value in (("additional_development_looks", 0), ("reservation_file", "reset.json"), ("quantconnect", True), ("interpretation", "all-null-values")):
        body = original.body()
        body[key] = value
        payload = canonical(body)
        with pytest.raises(ValueError, match="plan"):
            correction._execute_fixture(replace(original, payload=payload, sha256=digest(payload)), chain["root"], now=NOW)
    assert not (chain["root"] / (correction.CORRECTION_ID + ".spent.json")).exists()


@pytest.mark.parametrize("target", ["structure", "prior_claim"])
def test_changed_source_or_prior_claim_refuses_before_spending(chain, target):
    frozen_plan = plan(chain)
    name = "structure.json" if target == "structure" else market.CANDIDATE_ID + ".simulation.spent.json"
    synthetic.write(chain["root"], name, {"unrelated": True})
    with pytest.raises((ValueError, KeyError)):
        correction._execute_fixture(frozen_plan, chain["root"], now=NOW)
    assert not (chain["root"] / (correction.CORRECTION_ID + ".spent.json")).exists()


@pytest.mark.parametrize("interrupt", [False, True])
def test_failed_or_interrupted_computation_retains_new_spend_and_sanitized_terminal(chain, monkeypatch, interrupt):
    frozen_plan = plan(chain)
    old = (chain["root"] / (market.CANDIDATE_ID + ".simulation.spent.json")).read_bytes()
    def bad(*_):
        if interrupt: raise KeyboardInterrupt(synthetic.KEY)
        raise RuntimeError(synthetic.KEY)
    # Explicit failure injection into the NEW adapter; frozen parent untouched.
    monkeypatch.setattr(correction, "_compute", bad)
    if interrupt:
        with pytest.raises(KeyboardInterrupt, match="remains spent"):
            correction._execute_fixture(frozen_plan, chain["root"], now=NOW)
    else:
        result = correction._execute_fixture(frozen_plan, chain["root"], now=NOW)
        assert synthetic.KEY.encode() not in result.payload
        assert json.loads(result.payload)["failure_stage"] == "simulation"
    terminal = json.loads((chain["root"] / (correction.CORRECTION_ID + ".terminal.json")).read_bytes())
    assert terminal["status"] == ("INTERRUPTED" if interrupt else "FAILED")
    assert (chain["root"] / (market.CANDIDATE_ID + ".simulation.spent.json")).read_bytes() == old
    with pytest.raises(ValueError, match="already spent"):
        correction._execute_fixture(frozen_plan, chain["root"], now=NOW)


def test_partial_new_claim_never_opens_prior_private_result_or_projection(chain, monkeypatch):
    frozen_plan, root = plan(chain), chain["root"]
    write, read = source._write_fd, market.raw_run._read_file
    def partial(fd, payload):
        if b'"schema":"tpr-dividend-correction-reservation-v1"' in payload:
            os.write(fd, b"{")
            raise OSError(synthetic.KEY)
        return write(fd, payload)
    def guarded(fd, name, *args):
        if name.endswith((".projection.json", ".backtest.json")):
            pytest.fail("outcomes after incomplete correction reservation")
        return read(fd, name, *args)
    monkeypatch.setattr(source, "_write_fd", partial)
    monkeypatch.setattr(market.raw_run, "_read_file", guarded)
    result = correction._execute_fixture(frozen_plan, root, now=NOW)
    assert json.loads(result.payload)["failure_stage"] == "reservation"
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"


def test_correction_expiry_never_extends_parent_or_exceeds_twelve_hours(chain):
    for expires in (NOW.isoformat(), (NOW + timedelta(hours=13)).isoformat()):
        with pytest.raises(ValueError, match="scope"):
            plan(chain, expires_utc=expires)
    with pytest.raises(ValueError, match="expired"):
        correction._execute_fixture(plan(chain), chain["root"], now=NOW + timedelta(hours=10))
    assert not (chain["root"] / (correction.CORRECTION_ID + ".spent.json")).exists()
