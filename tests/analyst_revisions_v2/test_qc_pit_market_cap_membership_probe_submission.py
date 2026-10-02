from __future__ import annotations

import hashlib
import json
import types
from pathlib import Path

import pytest

import research.analyst_revisions_v2_qc.formal_qc_transport as transport_module
import research.analyst_revisions_v2_qc.pit_market_cap_membership_probe as probe
import research.analyst_revisions_v2_qc.pit_market_cap_membership_probe_submission_adapter as adapter
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = (
    ROOT
    / "research"
    / "analyst_revisions_v2_qc"
    / "pit_market_cap_membership_probe_runtime.py"
)


def _cell(value):
    def close():
        return value

    return close.__closure__[0]


def _replace_closure(function, name: str, value: object):
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__ or (), strict=True)
    )
    assert name in cells
    rebound = types.FunctionType(
        function.__code__,
        function.__globals__,
        function.__name__,
        function.__defaults__,
        tuple(
            _cell(value) if freevar == name else cells[freevar]
            for freevar in function.__code__.co_freevars
        ),
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _owner_signature():
    value = object.__new__(OwnerSignatureAuthority)
    object.__setattr__(value, "authority_sha256", "a" * 64)
    return value


DECISION_SESSIONS = (
    "2025-01-02",
    "2025-01-06",
    "2025-01-13",
    "2025-01-21",
    "2025-07-07",
    "2025-07-14",
    "2025-07-21",
    "2025-07-28",
    "2026-01-02",
    "2026-01-05",
    "2026-01-12",
    "2026-01-20",
    "2026-08-24",
    "2026-08-31",
    "2026-09-08",
    "2026-09-14",
)


def test_successor_uses_fresh_r082_project_and_backtest_identity():
    assert probe.PROJECT_NAME == (
        "30 ARV2_PIT_MARKET_CAP_MEMBERSHIP_SUMMARY_R082 - 20260917"
    )
    assert probe.BACKTEST_NAME == (
        "ARV2 R082 outcome-free PIT market-cap and ETF-membership summary retry 2"
    )


def test_successor_attestation_uses_an_exact_v2_persisted_filename():
    assert adapter.PERSISTED_ATTESTATION_FILENAME == (
        "arv2-pit-market-cap-membership-probe-coverage-attestation-v2.json"
    )


def _valid_attestation(plan, *, status="completed"):
    no_export = {
        "price_or_return_access_performed": False,
        "outcome_or_result_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
        "raw_rows_emitted": False,
        "security_identifiers_emitted": False,
        "constituent_weights_emitted": False,
        "market_cap_values_emitted": False,
        "full_receipt_or_pointer_export_performed": False,
    }
    if status == "named_refusal":
        value = {
            "schema": probe.ATTESTATION_SCHEMA,
            "status": "named_refusal",
            "contract_sha256": probe.CONTRACT_SHA256,
            "plan_id": plan.projection.plan_id,
            "plan_sha256": plan.projection.plan_sha256,
            "project_source_set_sha256": plan.project_source_set_sha256,
            "safe_reason": "pit_coverage_refused_fixture_deadbeefdeadbeef",
            "capabilities": no_export,
        }
    else:
        value = {
            "schema": probe.ATTESTATION_SCHEMA,
            "status": "completed",
            "contract_sha256": probe.CONTRACT_SHA256,
            "plan_id": plan.projection.plan_id,
            "plan_sha256": plan.projection.plan_sha256,
            "project_source_set_sha256": plan.project_source_set_sha256,
            "first_session": DECISION_SESSIONS[0],
            "last_session": DECISION_SESSIONS[-1],
            "decision_session_count": 16,
            "passed_session_count": 16,
            "history_call_count": 16,
            "fetched_source_row_count": 4800,
            "aggregate": {
                "fundamental_source_member_count": 3200,
                "fundamental_exact_sid_count": 3000,
                "fundamental_missing_or_invalid_sid_count": 200,
                "fundamental_duplicate_exact_sid_count": 0,
                "fundamental_duplicate_exact_sid_row_count": 0,
                "positive_market_cap_count": 2800,
                "null_market_cap_count": 100,
                "nonpositive_market_cap_count": 50,
                "invalid_or_nonfinite_market_cap_count": 50,
                "union_positive_member_count": 1600,
                "union_positive_market_cap_covered_count": 1500,
                "union_market_cap_uncovered_count": 100,
            },
            "etf_bounds": {
                "SPY": {
                    "minimum_positive_member_count": 490,
                    "maximum_positive_member_count": 510,
                    "minimum_market_cap_covered_count": 470,
                    "maximum_market_cap_covered_count": 500,
                },
                "QQQ": {
                    "minimum_positive_member_count": 95,
                    "maximum_positive_member_count": 105,
                    "minimum_market_cap_covered_count": 90,
                    "maximum_market_cap_covered_count": 100,
                },
                "SOXX": {
                    "minimum_positive_member_count": 28,
                    "maximum_positive_member_count": 32,
                    "minimum_market_cap_covered_count": 25,
                    "maximum_market_cap_covered_count": 30,
                },
            },
            "union_bounds": {
                "minimum_positive_member_count": 550,
                "maximum_positive_member_count": 620,
                "minimum_market_cap_covered_count": 525,
                "maximum_market_cap_covered_count": 605,
            },
            "availability_extrema": {
                "fundamentals": {
                    "earliest_collection_time_local": (
                        "2025-01-01T08:00:00.000000"
                    ),
                    "latest_collection_time_local": (
                        "2026-09-13T08:00:00.000000"
                    ),
                },
                "etfs": {
                    ticker: {
                        "earliest_collection_end_time_local": (
                            "2025-01-01T00:00:00.000000"
                        ),
                        "latest_collection_end_time_local": (
                            "2026-09-11T00:00:00.000000"
                        ),
                    }
                    for ticker in probe.ETFS
                },
            },
            "receipt_id": (
                "arv2-pit-market-cap-membership-coverage-" + "a" * 24
            ),
            "receipt_sha256": "b" * 64,
            "receipt_byte_count": 12_345,
            "terminal_pointer_sha256": "c" * 64,
            "terminal_pointer_byte_count": 512,
            "full_receipt_remains_qc_internal": True,
            "capabilities": {
                **no_export,
                "fundamental_history_access_performed": True,
                "etf_constituent_history_access_performed": True,
                "market_cap_field_access_performed": True,
            },
        }
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


class _Backend:
    def __init__(self, plan):
        self.plan = plan
        self.objects: dict[str, bytes] = {}
        self.files: dict[str, str] = {}
        self.default_files: dict[str, str] = {
            "main.py": "# QuantConnect default main\n",
            "research.ipynb": "{}",
        }
        self.created = False
        self.events: list[tuple[str, dict[str, object]]] = []
        self.terminal_status = "Completed."
        self.corrupt_source_readback = False
        self.file_read_count = 0
        self.summary = _valid_attestation(plan)
        self.extra_statistics: dict[str, object] = {}
        self.read_backtest_overrides: dict[str, object] = {}
        self.read_top_overrides: dict[str, object] = {}

    def project(self):
        return {
            "projectId": 2501,
            "organizationId": self.plan.organization_id,
            "name": self.plan.project_name,
            "language": "Py",
            "owner": True,
            "codeRunning": False,
            "collaborators": [{"owner": True}],
        }

    def request(self, path: str, payload: dict[str, object]):
        self.events.append((path, dict(payload)))
        if path == "authenticate":
            return {"success": True}
        if path == "projects/read":
            return {
                "success": True,
                "projects": [self.project()] if self.created else [],
            }
        if path == "projects/create":
            self.created = True
            self.files = dict(self.default_files)
            return {"success": True, "projects": [self.project()]}
        if path == "files/read":
            self.file_read_count += 1
            files = dict(self.files)
            if self.corrupt_source_readback and self.file_read_count == 2:
                first = sorted(files)[0]
                files[first] += "\n# unreviewed mutation\n"
            return {
                "success": True,
                "files": [
                    {"name": name, "content": content}
                    for name, content in sorted(files.items())
                ],
            }
        if path in {"files/create", "files/update"}:
            self.files[payload["name"]] = payload["content"]
            return {"success": True}
        if path == "files/delete":
            del self.files[payload["name"]]
            return {"success": True}
        if path == "compile/create":
            return {
                "success": True,
                "compileId": "probe-compile",
                "state": "InQueue",
                "parameters": [],
                "projectId": 2501,
                "signature": "probe-signature",
                "signatureOrder": [],
            }
        if path == "compile/read":
            return {
                "success": True,
                "compileId": "probe-compile",
                "state": "BuildSuccess",
                "logs": ["discard-only fixture compile log"],
            }
        if path == "backtests/create":
            return {
                "success": True,
                "backtest": {
                    "backtestId": "probe-backtest",
                    "name": payload["backtestName"],
                    "projectId": 2501,
                    "status": "In Queue...",
                },
            }
        if path == "backtests/list":
            assert payload == {"projectId": 2501, "includeStatistics": False}
            return {
                "success": True,
                "count": 1,
                "backtests": [
                    {
                        "backtestId": "probe-backtest",
                        "name": self.plan.backtest_name,
                        "projectId": 2501,
                        "status": self.terminal_status,
                        "statistics": {"forbidden": "must-not-be-selected"},
                    }
                ],
            }
        if path == "backtests/read":
            assert payload == {
                "projectId": 2501,
                "backtestId": "probe-backtest",
            }
            backtest = {
                "backtestId": "probe-backtest",
                "name": self.plan.backtest_name,
                "projectId": 2501,
                "status": "Completed.",
                "statistics": {
                    probe.SUMMARY_NAME: self.summary,
                    "Total Orders": "999; must never be selected",
                    **self.extra_statistics,
                },
            }
            backtest.update(self.read_backtest_overrides)
            response = {
                "success": True,
                "errors": [],
                "messages": [],
                "backtest": backtest,
            }
            response.update(self.read_top_overrides)
            return response
        raise AssertionError(path)


def _transport(backend):
    def http(url, body, headers, timeout):
        del timeout
        assert "Authorization" in headers
        path = url.split("/api/v2/", 1)[1]
        if path == "object/set":
            boundary = headers["Content-Type"].split("boundary=", 1)[1]
            key = body.split(b'name="key"\r\n\r\n', 1)[1].split(
                b"\r\n--" + boundary.encode(), 1
            )[0].decode()
            marker = (
                b'name="objectData"; filename="object.bin"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
            )
            backend.objects[key] = body.split(marker, 1)[1].rsplit(
                b"\r\n--" + boundary.encode() + b"--\r\n", 1
            )[0]
            backend.events.append((path, {"key": key}))
            result = {"success": True}
        else:
            payload = json.loads(body)
            if path == "object/properties":
                stored = backend.objects[payload["key"]]
                backend.events.append((path, dict(payload)))
                result = {
                    "success": True,
                    "metadata": {
                        "key": payload["key"],
                        "size": len(stored),
                        "md5": hashlib.md5(
                            stored, usedforsecurity=False
                        ).hexdigest(),
                    },
                }
            else:
                result = backend.request(path, payload)
        return 200, json.dumps(result, separators=(",", ":")).encode("utf-8")

    return transport_module.FormalQcTransport(
        http_transport=http,
        clock=lambda: 1_789_000_000,
    )


def _fixture(monkeypatch, tmp_path):
    tmp_path.chmod(0o700)
    plan_bytes = probe.build_pit_market_cap_membership_probe_plan_bytes(
        decision_sessions=DECISION_SESSIONS,
        calculation_session="2026-09-16",
    )
    projection = probe.build_pit_market_cap_membership_probe_qc_projection(
        plan_bytes=plan_bytes,
        runtime_source_bytes=RUNTIME_PATH.read_bytes(),
    )
    plan = adapter.build_pit_market_cap_membership_probe_submission_plan(
        projection=projection,
        organization_id="probe-test-organization",
        review_directory=tmp_path,
    )
    review_path = tmp_path / adapter.REVIEW_FILENAME
    review_path.write_bytes(
        adapter.render_pit_market_cap_membership_probe_review_claim_candidate(plan)
    )
    review_path.chmod(0o600)
    claim = adapter.load_pit_market_cap_membership_probe_review_claim(plan)
    owner = _owner_signature()
    backend = _Backend(plan)
    client = _transport(backend)
    monkeypatch.setattr(adapter, "_require_owner_signature", lambda *_args: owner)
    monkeypatch.setattr(adapter.formal, "_require_concrete_transport", lambda value: value)
    minted = []

    def minter(*, transport, scope, binding_record, call_budget):
        minted.append((scope, dict(binding_record), dict(call_budget)))
        return transport_module._mint_offline_test_capability(
            transport,
            scope=scope,
            binding_record=binding_record,
            call_budget=call_budget,
        )

    for name in (
        "execute_pit_market_cap_membership_probe_submission_once",
        "inspect_pit_market_cap_membership_probe_terminal_status",
        "read_pit_market_cap_membership_probe_receipt_once",
    ):
        monkeypatch.setattr(
            adapter,
            name,
            _replace_closure(getattr(adapter, name), "minter", minter),
        )
    return plan, claim, owner, backend, client, minted


def _launch(monkeypatch, tmp_path):
    plan, claim, owner, backend, client, minted = _fixture(monkeypatch, tmp_path)
    permit, launch = adapter.execute_pit_market_cap_membership_probe_submission_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner,
        client=client,
        started_at_utc="2026-09-16T12:00:00Z",
    )
    return plan, claim, owner, backend, client, minted, permit, launch


def _terminal(monkeypatch, tmp_path):
    values = _launch(monkeypatch, tmp_path)
    plan, claim, owner, backend, client, _minted, permit, launch = values
    terminal = adapter.inspect_pit_market_cap_membership_probe_terminal_status(
        plan=plan,
        review_claim=claim,
        owner_signature=owner,
        permit=permit,
        launch=launch,
        client=client,
    )
    return (*values, terminal)


def test_review_claim_truthfully_records_owner_prereview_waiver(monkeypatch, tmp_path):
    plan, claim, *_rest = _fixture(monkeypatch, tmp_path)
    raw = json.loads(
        adapter.render_pit_market_cap_membership_probe_review_claim_candidate(plan)
    )
    assert raw["review_disposition"] == "OWNER_DIRECTED_PREREVIEW_DIAGNOSTIC_WAIVER"
    assert raw["independent_review_complete"] is False
    assert raw["owner_directed_prereview_diagnostic"] is True
    assert raw["outcome_access"] is False
    authority = json.loads(
        adapter.render_pit_market_cap_membership_probe_execution_authority_candidate(
            plan, claim
        )
    )
    assert (
        "files/delete_exact_new_project_default_research_notebook_once"
        in authority["actions"]
    )


def test_submission_uploads_exact_projection_and_launches_once(monkeypatch, tmp_path):
    (
        plan,
        claim,
        owner,
        backend,
        client,
        minted,
        permit,
        launch,
    ) = _launch(monkeypatch, tmp_path)
    assert backend.objects[plan.plan_object_store_key] == plan.projection.plan_bytes
    assert backend.files == {
        item.project_path: item.content.decode("ascii")
        for item in plan.projection.source_files
    }
    paths = [path for path, _payload in backend.events]
    assert paths.count("compile/create") == 1
    assert paths.count("backtests/create") == 1
    assert [
        payload for path, payload in backend.events if path == "files/delete"
    ] == [
        {
            "projectId": 2501,
            "name": adapter.QC_DEFAULT_RESEARCH_NOTEBOOK_PATH,
        }
    ]
    assert "backtests/read" not in paths
    assert (tmp_path / adapter.PERMIT_FILENAME).stat().st_mode & 0o777 == 0o600
    assert (tmp_path / adapter.LAUNCH_RECEIPT_FILENAME).stat().st_mode & 0o777 == 0o600
    reloaded_permit = adapter.load_pit_market_cap_membership_probe_submission_permit(
        plan=plan,
        review_claim=claim,
        owner_signature=owner,
    )
    assert reloaded_permit == permit
    assert adapter.load_pit_market_cap_membership_probe_launch_receipt(
        plan=plan,
        permit=reloaded_permit,
        review_claim=claim,
        owner_signature=owner,
    ) == launch
    scope, _binding, budget = minted[0]
    assert scope == "submission"
    assert budget == {
        "authenticate": 1,
        "projects/read": 2,
        "projects/create": 1,
        "object/set": 1,
        "object/properties": 1,
        "files/read": 2,
        "files/create": 2,
        "files/update": 1,
        "files/delete": 1,
        "compile/create": 1,
        "compile/read": adapter.COMPILE_POLLS,
        "backtests/create": 1,
    }
    before = len(backend.events)
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionLocked,
        match="already spent|ambiguous",
    ):
        adapter.execute_pit_market_cap_membership_probe_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            client=client,
            started_at_utc="2026-09-16T12:01:00Z",
        )
    assert len(backend.events) == before


@pytest.mark.parametrize(
    "unexpected_path",
    (
        "unreviewed.py",
        "Research.ipynb",
        "notebooks/research.ipynb",
        "pit_market_cap_membership_probe_runtime.py",
    ),
)
def test_submission_refuses_any_nondefault_fresh_project_source_before_compile(
    monkeypatch, tmp_path, unexpected_path
):
    plan, claim, owner, backend, client, _minted = _fixture(monkeypatch, tmp_path)
    backend.default_files[unexpected_path] = "raise RuntimeError('must not run')\n"
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionLocked,
        match="ambiguous",
    ):
        adapter.execute_pit_market_cap_membership_probe_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            client=client,
            started_at_utc="2026-09-16T12:00:00Z",
        )
    paths = [path for path, _payload in backend.events]
    assert "files/delete" not in paths
    assert "files/create" not in paths
    assert "files/update" not in paths
    assert "compile/create" not in paths
    assert "backtests/create" not in paths


def test_owner_signature_refuses_before_permit_or_network(monkeypatch, tmp_path):
    plan, claim, owner, backend, client, _minted = _fixture(monkeypatch, tmp_path)

    def refuse(*_args):
        raise adapter.PitMarketCapMembershipProbeSubmissionError("no authority")

    monkeypatch.setattr(adapter, "_require_owner_signature", refuse)
    with pytest.raises(adapter.PitMarketCapMembershipProbeSubmissionError):
        adapter.execute_pit_market_cap_membership_probe_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            client=client,
            started_at_utc="2026-09-16T12:00:00Z",
        )
    assert backend.events == []
    assert not (tmp_path / adapter.PERMIT_FILENAME).exists()


def test_source_readback_mutation_locks_before_compile(monkeypatch, tmp_path):
    plan, claim, owner, backend, client, _minted = _fixture(monkeypatch, tmp_path)
    backend.corrupt_source_readback = True
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionLocked,
        match="ambiguous",
    ):
        adapter.execute_pit_market_cap_membership_probe_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            client=client,
            started_at_utc="2026-09-16T12:00:00Z",
        )
    paths = [path for path, _payload in backend.events]
    assert "compile/create" not in paths
    assert "backtests/create" not in paths
    assert (tmp_path / adapter.PERMIT_FILENAME).exists()


def test_submission_capability_mint_failure_refuses_before_spend_or_network(
    monkeypatch, tmp_path
):
    plan, claim, owner, backend, client, _minted = _fixture(monkeypatch, tmp_path)

    def refuse_mint(**_kwargs):
        raise RuntimeError("offline minter failure")

    monkeypatch.setattr(
        adapter,
        "execute_pit_market_cap_membership_probe_submission_once",
        _replace_closure(
            adapter.execute_pit_market_cap_membership_probe_submission_once,
            "minter",
            refuse_mint,
        ),
    )
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionError,
        match="mint failed before permit spend",
    ):
        adapter.execute_pit_market_cap_membership_probe_submission_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            client=client,
            started_at_utc="2026-09-16T12:00:00Z",
        )
    assert not (tmp_path / adapter.PERMIT_FILENAME).exists()
    assert backend.events == []


def test_output_capability_mint_failure_refuses_before_spend_or_network(
    monkeypatch, tmp_path
):
    values = _terminal(monkeypatch, tmp_path)
    plan, claim, owner, backend, client, _minted, permit, launch, terminal = values

    def refuse_mint(**_kwargs):
        raise RuntimeError("offline output minter failure")

    monkeypatch.setattr(
        adapter,
        "read_pit_market_cap_membership_probe_receipt_once",
        _replace_closure(
            adapter.read_pit_market_cap_membership_probe_receipt_once,
            "minter",
            refuse_mint,
        ),
    )
    before = len(backend.events)
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionError,
        match="mint failed before permit spend",
    ):
        adapter.read_pit_market_cap_membership_probe_receipt_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
            client=client,
            started_at_utc="2026-09-16T12:05:00Z",
        )
    assert not (tmp_path / adapter.OUTPUT_READ_PERMIT_FILENAME).exists()
    assert len(backend.events) == before


def test_status_is_statistics_free_and_durably_reloadable(monkeypatch, tmp_path):
    (
        plan,
        claim,
        owner,
        backend,
        _client,
        minted,
        permit,
        launch,
        terminal,
    ) = _terminal(monkeypatch, tmp_path)
    status_events = [payload for path, payload in backend.events if path == "backtests/list"]
    assert status_events == [{"projectId": 2501, "includeStatistics": False}]
    assert all(path != "backtests/read" for path, _payload in backend.events)
    assert terminal.result_values_selected_or_inspected is False
    assert (tmp_path / adapter.TERMINAL_RECEIPT_FILENAME).stat().st_mode & 0o777 == 0o600
    reloaded_permit = adapter.load_pit_market_cap_membership_probe_submission_permit(
        plan=plan, review_claim=claim, owner_signature=owner
    )
    reloaded_launch = adapter.load_pit_market_cap_membership_probe_launch_receipt(
        plan=plan,
        permit=reloaded_permit,
        review_claim=claim,
        owner_signature=owner,
    )
    assert adapter.load_pit_market_cap_membership_probe_terminal_status(
        plan=plan,
        permit=reloaded_permit,
        launch=reloaded_launch,
        review_claim=claim,
        owner_signature=owner,
    ) == terminal
    assert minted[1][0] == "status"
    assert minted[1][2] == {"backtests/list": adapter.STATUS_POLLS}


def test_output_reads_exactly_one_aggregate_attestation_then_reloads(
    monkeypatch, tmp_path
):
    (
        plan,
        claim,
        owner,
        backend,
        client,
        minted,
        permit,
        launch,
        terminal,
    ) = _terminal(monkeypatch, tmp_path)
    result = adapter.read_pit_market_cap_membership_probe_receipt_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner,
        permit=permit,
        launch=launch,
        terminal_status=terminal,
        client=client,
        started_at_utc="2026-09-16T12:05:00Z",
    )
    assert isinstance(
        result, probe.ReviewedPitMarketCapMembershipCoverageAttestation
    )
    assert result.decision_session_count == 16
    assert result.passed_session_count == 16
    reads = [
        payload for path, payload in backend.events if path == "backtests/read"
    ]
    assert reads == [{"projectId": 2501, "backtestId": "probe-backtest"}]
    assert all(
        path not in {"object/read", "object/get"}
        for path, _payload in backend.events
    )
    assert minted[2][0] == "result_read"
    assert minted[2][2] == {"backtests/read": 1}
    persisted = tmp_path / adapter.PERSISTED_ATTESTATION_FILENAME
    assert persisted.read_bytes() == backend.summary.encode("ascii")
    assert (
        adapter.load_persisted_pit_market_cap_membership_probe_output(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
        )
        == result
    )
    before = len(backend.events)
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionLocked,
        match="already spent|ambiguous",
    ):
        adapter.read_pit_market_cap_membership_probe_receipt_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
            client=client,
            started_at_utc="2026-09-16T12:06:00Z",
        )
    assert len(backend.events) == before


def test_persisted_output_requires_its_durable_read_permit(monkeypatch, tmp_path):
    values = _terminal(monkeypatch, tmp_path)
    plan, claim, owner, _backend, client, _minted, permit, launch, terminal = values
    adapter.read_pit_market_cap_membership_probe_receipt_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner,
        permit=permit,
        launch=launch,
        terminal_status=terminal,
        client=client,
        started_at_utc="2026-09-16T12:05:00Z",
    )
    (tmp_path / adapter.OUTPUT_READ_PERMIT_FILENAME).unlink()
    before = len(_backend.events)
    with pytest.raises(adapter.PitMarketCapMembershipProbeSubmissionError):
        adapter.load_persisted_pit_market_cap_membership_probe_output(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
        )
    assert len(_backend.events) == before


def test_runtime_error_terminal_refuses_live_and_persisted_output_before_read(
    monkeypatch, tmp_path
):
    plan, claim, owner, backend, client, _minted, permit, launch = _launch(
        monkeypatch, tmp_path
    )
    backend.terminal_status = "Runtime Error"
    terminal = adapter.inspect_pit_market_cap_membership_probe_terminal_status(
        plan=plan,
        review_claim=claim,
        owner_signature=owner,
        permit=permit,
        launch=launch,
        client=client,
    )
    assert terminal.status == "Runtime Error"
    before = len(backend.events)
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionError,
        match="requires Completed terminal status",
    ):
        adapter.read_pit_market_cap_membership_probe_receipt_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
            client=client,
            started_at_utc="2026-09-16T12:05:00Z",
        )
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionError,
        match="requires Completed terminal status",
    ):
        adapter.load_persisted_pit_market_cap_membership_probe_output(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
        )
    assert not (tmp_path / adapter.OUTPUT_READ_PERMIT_FILENAME).exists()
    assert len(backend.events) == before


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("malformed", "ambiguous"),
        ("extra_arv2", "ambiguous"),
        ("wrong_run", "ambiguous"),
        ("unknown_top", "ambiguous"),
        ("unknown_backtest", "ambiguous"),
        ("non_ascii", "ambiguous"),
        ("oversize", "ambiguous"),
    ),
)
def test_invalid_result_read_spends_permit_and_persists_nothing(
    monkeypatch, tmp_path, mutation, message
):
    values = _terminal(monkeypatch, tmp_path)
    plan, claim, owner, backend, client, _minted, permit, launch, terminal = values
    if mutation == "malformed":
        backend.summary = "{}"
    elif mutation == "extra_arv2":
        backend.extra_statistics["ARV2_UNREVIEWED"] = "forbidden"
    elif mutation == "wrong_run":
        backend.read_backtest_overrides["backtestId"] = "another-run"
    elif mutation == "unknown_top":
        backend.read_top_overrides["unreviewed"] = True
    elif mutation == "unknown_backtest":
        backend.read_backtest_overrides["unreviewed"] = True
    elif mutation == "non_ascii":
        backend.summary += "N{SNOWMAN}"
    elif mutation == "oversize":
        backend.summary = "x" * (probe.MAX_SUMMARY_CHARACTERS + 1)
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionLocked,
        match=message,
    ):
        adapter.read_pit_market_cap_membership_probe_receipt_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
            client=client,
            started_at_utc="2026-09-16T12:05:00Z",
        )
    assert (tmp_path / adapter.OUTPUT_READ_PERMIT_FILENAME).exists()
    assert not (tmp_path / adapter.PERSISTED_ATTESTATION_FILENAME).exists()
    assert [
        path for path, _payload in backend.events if path == "backtests/read"
    ] == ["backtests/read"]


def test_persisted_attestation_mutation_is_refused_without_network(
    monkeypatch, tmp_path
):
    values = _terminal(monkeypatch, tmp_path)
    plan, claim, owner, backend, client, _minted, permit, launch, terminal = values
    adapter.read_pit_market_cap_membership_probe_receipt_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner,
        permit=permit,
        launch=launch,
        terminal_status=terminal,
        client=client,
        started_at_utc="2026-09-16T12:05:00Z",
    )
    persisted = tmp_path / adapter.PERSISTED_ATTESTATION_FILENAME
    persisted.write_bytes(persisted.read_bytes() + b" ")
    before = len(backend.events)
    with pytest.raises(adapter.PitMarketCapMembershipProbeSubmissionError):
        adapter.load_persisted_pit_market_cap_membership_probe_output(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
        )
    assert len(backend.events) == before


def test_named_refusal_exports_only_safe_reason_and_negative_capabilities(
    monkeypatch, tmp_path
):
    values = _terminal(monkeypatch, tmp_path)
    plan, claim, owner, backend, client, _minted, permit, launch, terminal = values
    backend.summary = _valid_attestation(plan, status="named_refusal")
    refusal = adapter.read_pit_market_cap_membership_probe_receipt_once(
        plan=plan,
        review_claim=claim,
        owner_signature=owner,
        permit=permit,
        launch=launch,
        terminal_status=terminal,
        client=client,
        started_at_utc="2026-09-16T12:05:00Z",
    )
    assert isinstance(refusal, probe.PitMarketCapMembershipCoverageNamedRefusal)
    assert refusal.safe_reason == "pit_coverage_refused_fixture_deadbeefdeadbeef"
    assert refusal.outcome_access_performed is False
    assert refusal.price_or_return_access_performed is False
    assert refusal.orders_or_portfolio_actions_performed is False


def test_named_refusal_cannot_export_an_unsanitized_reason(monkeypatch, tmp_path):
    values = _terminal(monkeypatch, tmp_path)
    plan, claim, owner, backend, client, _minted, permit, launch, terminal = values
    raw = json.loads(_valid_attestation(plan, status="named_refusal"))
    raw["safe_reason"] = "raw provider row was ticker SECRET at value 123.45"
    backend.summary = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    with pytest.raises(
        adapter.PitMarketCapMembershipProbeSubmissionLocked,
        match="ambiguous",
    ):
        adapter.read_pit_market_cap_membership_probe_receipt_once(
            plan=plan,
            review_claim=claim,
            owner_signature=owner,
            permit=permit,
            launch=launch,
            terminal_status=terminal,
            client=client,
            started_at_utc="2026-09-16T12:05:00Z",
        )
    assert not (tmp_path / adapter.PERSISTED_ATTESTATION_FILENAME).exists()


def test_execution_authority_pins_summary_read_and_forbids_object_export(
    monkeypatch, tmp_path
):
    plan, claim, *_rest = _fixture(monkeypatch, tmp_path)
    authority = json.loads(
        adapter.render_pit_market_cap_membership_probe_execution_authority_candidate(
            plan, claim
        )
    )
    assert authority["maximum_backtests_read_calls"] == 1
    assert authority["selected_summary_statistic"] == probe.SUMMARY_NAME
    assert authority["backtests_read"] is True
    assert authority["object_store_export"] is False
    assert "backtests/read_exact_aggregate_attestation_once" in authority["actions"]
    assert "persist_exact_validated_attestation_only" in authority["actions"]
    assert all("object/read" not in action for action in authority["actions"])
