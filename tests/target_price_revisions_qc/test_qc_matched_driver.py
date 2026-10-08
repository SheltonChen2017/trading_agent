"""Committed driver boundary tests; synthetic transport, no empirical I/O."""
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import matched_driver as d


def test_rendered_real_template_contains_all_six_closed_configs():
    rendered = d.render_sources()
    assert len(rendered["cases"]) == 6
    assert set(row["candidate_id"] for row in rendered["cases"]) == d.ops.CANDIDATES
    assert all(set(row["files"]) == d.ops.SOURCE_FILES for row in rendered["cases"])
    assert rendered["freeze_sha256"] == d.bundle.FREEZE_SHA256
    assert rendered["template_sha256"] == d.ops.digest((d.PACKAGE / "matched_algorithm_v3.py").read_bytes())
    assert rendered["template_sha256"] != d.ops.digest((d.PACKAGE / "matched_algorithm_v2.py").read_bytes())
    assert rendered["template_sha256"] != d.ops.digest((d.PACKAGE / "matched_algorithm.py").read_bytes())


def test_prepare_commits_fresh_scope_before_any_explicit_packet_read(monkeypatch):
    events, receipts = [], {}
    class FakeController:
        def __init__(self, manifest, *, manifest_sha256):
            assert d.ops.digest(d.ops.canonical(manifest)) == manifest_sha256
            assert manifest["log_prefix"] == "MATCHED_"
            assert len(manifest["candidates"]) == 6
            self.operation = manifest["operation_id"]
            self.manifest = manifest
        def prepare_access(self):
            events.append("access")
        def exclusive(self, name, value):
            receipts[name] = value
            events.append(name.split(".", 1)[0])
        def prepare_packet(self):
            assert events == ["access", "manifest", "source-bundle"]
            events.append("packet")
        def read_private(self, name):
            assert name == "signal-packet." + self.operation + ".json"
            return b"synthetic packet never uploaded"
    monkeypatch.setattr(d.ops, "Operations", FakeController)
    monkeypatch.setattr(d.bundle, "validate_packet_bytes", lambda raw: events.append("validate"))
    result = d.prepare("TPR-MATCHED-ACCESS-SYNTHETIC")
    assert events == ["access", "manifest", "source-bundle", "packet", "validate"]
    assert result["operation_id"] == "TPR-MATCHED-ACCESS-SYNTHETIC"
    manifest = receipts["manifest.TPR-MATCHED-ACCESS-SYNTHETIC.json"]
    assert set(manifest["repository_source_hashes"]) == set(d.REPOSITORY_SOURCES)
    assert manifest["packet_path"] == d.ops.PACKET_PATH
    assert manifest["packet_sha256"] == d.bundle.PACKET_SHA256
    assert manifest["max_attempts_per_candidate"] == 3


def test_prepare_contains_no_implicit_network_or_credential_access(monkeypatch):
    monkeypatch.setattr(d.ops.http.client, "HTTPSConnection", lambda *args, **kwargs: pytest.fail("network"))
    original_get = d.ops.os.environ.get
    def guarded_get(key, *args, **kwargs):
        if key in {"QC_USER_ID", "QC_API_TOKEN"}:
            pytest.fail("credential")
        return original_get(key, *args, **kwargs)
    monkeypatch.setattr(d.ops.os.environ, "get", guarded_get)
    test_prepare_commits_fresh_scope_before_any_explicit_packet_read(monkeypatch)


@pytest.mark.parametrize("action", ["create", "source-upload", "reserve", "compile", "launch", "status", "collect"])
def test_explicit_candidate_is_required(action, monkeypatch):
    monkeypatch.setattr(d, "controller_for", lambda operation: object())
    with pytest.raises(SystemExit) as error:
        d.main([action])
    assert error.value.code == 2


@pytest.mark.parametrize("action", ["compile", "compile-status", "launch", "status", "collect"])
def test_attempt_identity_is_required_for_attempt_stages(action, monkeypatch):
    monkeypatch.setattr(d, "controller_for", lambda operation: object())
    with pytest.raises(SystemExit) as error:
        d.main([action, "--candidate", "TPR-MATCHED-ON-BASE-v1"])
    assert error.value.code == 2


def test_import_does_not_prepare_or_launch(monkeypatch):
    import importlib
    monkeypatch.setattr(d.ops, "Operations", lambda *args, **kwargs: pytest.fail("operation on import"))
    importlib.reload(d)
    assert callable(d.main)
