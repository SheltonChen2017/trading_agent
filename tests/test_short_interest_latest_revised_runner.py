"""Connected provider-shaped *fabricated* file replay and launch fences."""
from __future__ import annotations

import copy
import json
import subprocess
from decimal import localcontext
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_payload
from ml.immutable_io import ImmutableFileConflictError
from research.short_interest_etf.latest_revised_fixture import (
    FIXTURE_MANIFEST_SHA256,
    fabricated_manifest,
    publish_fabricated_files,
)
from research.short_interest_etf.latest_revised_protocol import (
    OWNER_DECISION_COMMIT,
    OWNER_DECISION_SHA256,
    PROTOCOL_SHA256,
    protocol_payload,
)
from research.short_interest_etf.latest_revised_runner import (
    LatestRevisedRunError,
    run_public_file_rehearsal,
)
import research.short_interest_etf.latest_revised_runner as runner
import research.short_interest_etf.latest_revised_source as source_module
from scripts.run_short_interest_exploratory import main


@pytest.fixture(scope="module")
def connected_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("si-exploratory-connected")
    manifest = publish_fabricated_files(root / "raw")
    receipt = run_public_file_rehearsal(manifest, root / "reports")
    report = json.loads(Path(receipt["report_path"]).read_text(encoding="utf-8"))
    return manifest, receipt, report


def test_protocol_is_bound_to_the_prospective_owner_record():
    root = Path(__file__).resolve().parents[1]
    record = subprocess.check_output(
        ["git", "show", OWNER_DECISION_COMMIT + ":docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md"],
        cwd=root,
    )
    from data.hashing import hash_bytes
    assert hash_bytes(record) == OWNER_DECISION_SHA256
    assert hash_payload(protocol_payload()) == PROTOCOL_SHA256
    assert b"## 97. Separate latest-revised exploratory build" in record


def test_protocol_detaches_and_keeps_both_research_claims_separate():
    first = protocol_payload()
    first["normalization"]["epsilon"] = 1
    first["source_rights_verified"] = True
    second = protocol_payload()
    assert hash_payload(second) == PROTOCOL_SHA256
    assert second["source_rights_verified"] is False
    assert second["actual_outcome_looks_authorized"] == 0
    assert second["candidate_lookbacks"] == [20, 60, 120, 252]
    assert second["selected_lookback"] is None


def test_public_fixture_manifest_binds_every_member_byte():
    manifest, files = fabricated_manifest()
    assert hash_payload(manifest) == FIXTURE_MANIFEST_SHA256
    assert set(files) == {"short-interest.json", "calendar.json", "references.json", "bars.json", "events.json"}
    assert all("apiKey" not in str(value) for value in manifest.values())


def test_public_recipe_identity_does_not_depend_on_ambient_decimal_precision():
    with localcontext() as context:
        context.prec = 2
        manifest, _ = fabricated_manifest()
    assert hash_payload(manifest) == FIXTURE_MANIFEST_SHA256


def test_connected_file_replay_completes_all_48_books(connected_run):
    _, receipt, report = connected_run
    assert receipt["software_replay_complete"] is True
    assert receipt["books"] == 48
    assert report["source_summary"]["row_counts"]["observations"] == 160
    assert report["source_summary"]["row_counts"]["releases"] == 4
    assert len(report["orders"]["books"]) == 48
    assert all(book["complete"] for book in report["orders"]["books"])
    assert len(report["comparisons"]) == 16
    assert {book["allocation_role"] for book in report["orders"]["books"]} == {
        "equal_weight_common", "avoid_high_pressure", "long_low_pressure",
    }
    assert all(book["financial_result"]["final_positions"] == []
               for book in report["orders"]["books"])


def test_connected_run_preserves_every_refused_and_final_release(connected_run):
    _, _, report = connected_run
    assert len(report["rankings"]["releases"]) == 4
    for book in report["orders"]["books"]:
        assert len(book["release_records"]) == 4
        assert book["release_records"][-1]["execution_status"] == "final_exit_only"
        assert not book["release_records"][-1]["allocation_security_ids"]
        assert all(order["side"] in {"buy", "sell"} for order in book["orders"])


def test_report_has_exact_connected_lineage_and_no_empirical_authority(connected_run):
    _, receipt, report = connected_run
    assert report["source_summary"]["bundle_sha256"] == report["rankings"]["source_bundle_sha256"]
    assert report["rankings"]["rankings_sha256"] == report["orders"]["rankings_sha256"]
    assert report["authority"] == report["rankings"]["authority"] == report["orders"]["authority"]
    assert report["authority"]["latest_revised"] is True
    assert all(value is False for key, value in report["authority"].items() if key != "latest_revised")
    assert report["ready_for_empirical_backtest"] is False
    assert report["real_outcome_looks_consumed"] == 0
    assert report["allocated_alpha"] == {"numerator": 0, "denominator": 1}
    assert report["confirmatory_look_ids"] == []
    assert report["selected_lookback"] is None
    detached = copy.deepcopy(report)
    claimed = detached.pop("report_sha256")
    assert hash_payload(detached) == claimed == receipt["report_sha256"]
    assert len(report["implementation"]["files"]) == 7


def test_exact_rehearsal_retry_is_immutable_and_idempotent(connected_run):
    manifest, receipt, _ = connected_run
    replayed = run_public_file_rehearsal(manifest, Path(receipt["report_path"]).parent)
    assert replayed == receipt


def test_report_publication_refuses_different_existing_bytes(connected_run, tmp_path):
    manifest, receipt, _ = connected_run
    target = tmp_path / (receipt["report_sha256"] + ".report.json")
    target.write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(ImmutableFileConflictError):
        run_public_file_rehearsal(manifest, tmp_path)
    assert target.read_text(encoding="utf-8") == "do not overwrite"


def test_unknown_manifest_is_refused_before_source_or_outcome_parse(tmp_path, monkeypatch):
    manifest = tmp_path / "private-manifest.json"
    manifest.write_text('{"synthetic":true,"rights_verified":true}', encoding="utf-8")
    calls = []
    monkeypatch.setattr(runner, "load_latest_revised_bundle", lambda *_: calls.append("opened"))
    with pytest.raises(LatestRevisedRunError, match="not the pinned public fabricated"):
        run_public_file_rehearsal(manifest, tmp_path / "reports")
    assert calls == []
    assert not (tmp_path / "reports").exists()


def test_cli_reports_unknown_input_refusal_without_an_approval_bypass(tmp_path, capsys):
    manifest = tmp_path / "unknown.json"
    manifest.write_text("{}", encoding="utf-8")
    assert main(["--manifest", str(manifest), "--output-dir", str(tmp_path / "reports")]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "refused"
    assert output["ready_for_empirical_backtest"] is False


def test_cli_accepts_no_rights_or_authority_override(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(["--manifest", str(tmp_path / "none"), "--output-dir", str(tmp_path / "out"), "--rights-verified"])
    assert error.value.code == 2


def test_fixture_publication_is_idempotent_and_cannot_overwrite(tmp_path):
    manifest = publish_fabricated_files(tmp_path / "raw")
    assert publish_fabricated_files(tmp_path / "raw") == manifest
    member = manifest.parent / "events.json"
    member.write_text("{}", encoding="utf-8")
    with pytest.raises(ImmutableFileConflictError):
        publish_fabricated_files(tmp_path / "raw")
    assert member.read_text(encoding="utf-8") == "{}"


def test_tampered_member_fails_even_with_the_genuine_manifest(tmp_path):
    manifest = publish_fabricated_files(tmp_path / "raw")
    (manifest.parent / "short-interest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_public_file_rehearsal(manifest, tmp_path / "reports")
    assert not list((tmp_path / "reports").glob("*.report.json"))


def test_manifest_swap_is_refused_before_any_member_or_outcome_read(tmp_path, monkeypatch):
    manifest = publish_fabricated_files(tmp_path / "raw")
    original_identity = runner._code_identity
    calls = []

    def replace_after_first_fence():
        changed = json.loads(manifest.read_text(encoding="utf-8"))
        changed["retrieved_at"] = "2024-03-02T00:00:00Z"
        manifest.write_text(canonical_json(changed), encoding="utf-8")
        return original_identity()

    def forbidden_member_read(*_args, **_kwargs):
        calls.append("member_opened")
        raise AssertionError("member read reached after manifest identity changed")

    monkeypatch.setattr(runner, "_code_identity", replace_after_first_fence)
    monkeypatch.setattr(source_module, "_read_bound", forbidden_member_read)
    with pytest.raises(ValueError, match="manifest SHA-256"):
        run_public_file_rehearsal(manifest, tmp_path / "reports")
    assert calls == []
