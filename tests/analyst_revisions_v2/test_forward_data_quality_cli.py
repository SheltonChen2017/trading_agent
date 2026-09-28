"""The forward-quality CLI is local-only and value-free."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import run_arv2_forward_data_quality as cli
from tests.analyst_revisions_v2 import test_forward_data_quality as offline


def _build_args(source, output_root):
    return [
        "build", "--capture-path", str(source.artifact_path),
        "--capture-manifest-sha256", source.manifest_sha256,
        "--first-event-date", offline.FIRST,
        "--last-event-date", offline.LAST,
        "--output-root", str(output_root),
    ]


def _build(source, output_root, capsys):
    assert cli.main(
        _build_args(source, output_root),
        _expected_transport=cli.quality.capture.TEST_TRANSPORT,
    ) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["purpose"] == cli.quality.PURPOSE
    assert result["capture_manifest_sha256"] == source.manifest_sha256
    assert result["source_row_count"] == source.total_row_count
    assert Path(result["receipt_path"]).read_bytes()
    return result


def test_build_and_compare_two_exact_pinned_captures_without_provider_or_qc(
    tmp_path, monkeypatch, capsys,
):
    before_source = offline._capture(tmp_path)
    after_source = offline._capture(tmp_path, newer=True)
    allowed = tmp_path / "allowed"
    monkeypatch.setattr(cli.quality.capture, "REPOSITORY_ARTIFACTS_ROOT", allowed)

    def no_provider(*_args, **_kwargs):
        raise AssertionError("CLI attempted provider access")

    monkeypatch.setattr(cli.quality.capture, "capture_massive_history", no_provider)
    monkeypatch.setattr(cli.quality.capture, "_api_key", no_provider)
    before = _build(before_source, allowed / "receipts", capsys)
    after = _build(after_source, allowed / "receipts", capsys)
    assert cli.main([
        "compare",
        "--before-path", before["receipt_path"],
        "--before-sha256", before["receipt_sha256"],
        "--after-path", after["receipt_path"],
        "--after-sha256", after["receipt_sha256"],
        "--first-event-date", offline.FIRST,
        "--last-event-date", offline.LAST,
    ]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    rating = result["roles"][cli.quality.capture.ROLE_ORDER[0].value]
    assert rating["same_id_different_version_between_receipts"] == 1
    assert rating["old_only_id_cause_unknown"] == 1
    assert rating["new_only_id_cause_unknown"] == 1
    assert result["point_in_time_proven"] is result["paper_look_committed"] is False
    assert result["return_looks"] == 0
    assert "PRIVATE-DO-NOT-PUBLISH" not in output
    assert "same-rating" not in output
    assert "price_target" not in output


def test_build_refuses_wrong_manifest_pin_and_never_publishes(tmp_path, monkeypatch, capsys):
    source = offline._capture(tmp_path)
    allowed = tmp_path / "allowed"
    monkeypatch.setattr(cli.quality.capture, "REPOSITORY_ARTIFACTS_ROOT", allowed)
    args = _build_args(source, allowed / "receipts")
    args[args.index("--capture-manifest-sha256") + 1] = "0" * 64
    assert cli.main(args, _expected_transport=cli.quality.capture.TEST_TRANSPORT) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "REFUSED: forward data-quality authentication failed\n"
    assert not (allowed / "receipts").exists()


def test_same_receipt_cannot_be_republished_and_wrong_comparison_window_refuses(
    tmp_path, monkeypatch, capsys,
):
    source = offline._capture(tmp_path)
    allowed = tmp_path / "allowed"
    monkeypatch.setattr(cli.quality.capture, "REPOSITORY_ARTIFACTS_ROOT", allowed)
    first = _build(source, allowed / "receipts", capsys)
    assert cli.main(
        _build_args(source, allowed / "receipts"),
        _expected_transport=cli.quality.capture.TEST_TRANSPORT,
    ) == 2
    assert capsys.readouterr().out == ""
    newer = _build(offline._capture(tmp_path, newer=True), allowed / "receipts", capsys)
    assert cli.main([
        "compare", "--before-path", first["receipt_path"],
        "--before-sha256", first["receipt_sha256"],
        "--after-path", newer["receipt_path"],
        "--after-sha256", newer["receipt_sha256"],
        "--first-event-date", "2021-01-02",
        "--last-event-date", offline.LAST,
    ]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("side", ("before", "after"))
def test_compare_refuses_unpinned_name_or_digest(tmp_path, monkeypatch, capsys, side):
    allowed = tmp_path / "allowed"
    monkeypatch.setattr(cli.quality.capture, "REPOSITORY_ARTIFACTS_ROOT", allowed)
    before = _build(offline._capture(tmp_path), allowed / "receipts", capsys)
    after = _build(offline._capture(tmp_path, newer=True), allowed / "receipts", capsys)
    args = [
        "compare", "--before-path", before["receipt_path"],
        "--before-sha256", before["receipt_sha256"],
        "--after-path", after["receipt_path"],
        "--after-sha256", after["receipt_sha256"],
        "--first-event-date", offline.FIRST,
        "--last-event-date", offline.LAST,
    ]
    args[args.index(f"--{side}-sha256") + 1] = "0" * 64
    assert cli.main(args) == 2
    assert capsys.readouterr().out == ""


def test_cli_source_has_no_network_or_outcome_adapter_imports():
    tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name.startswith(("requests", "quantconnect", "backtest", "execution"))
                   for name in imports if name)
    assert not any(getattr(node, "attr", None) == "capture_massive_history"
                   for node in ast.walk(tree))
