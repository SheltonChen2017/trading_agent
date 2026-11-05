"""Concurrent mutation probes on invented scopes only; never hosted SDK/QC."""
from pathlib import Path
from contextlib import contextmanager
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
import test_insider_buying_qc_sdk_metadata_supervisor as base
from test_insider_buying_qc_sdk_metadata_supervisor import tmp_path  # noqa: F401  section 194: /tmp fixture root


def test_locked_scope_claim_cannot_be_swapped_after_initial_check_before_publication(tmp_path):
    prepared = base.prepare(tmp_path)
    value = base.observation(prepared)
    namespace = Path(prepared["namespace"])
    original = (namespace / "scope-claim.json").read_bytes()
    called = []
    def concurrent_change():
        called.append(True)
        replacement = namespace / "invented-replacement"
        replacement.write_bytes(original);replacement.chmod(0o600)
        replacement.replace(namespace / "scope-claim.json")
    with pytest.raises(base.supervisor.SupervisorRefusal):
        base.supervisor._complete(tmp_path.resolve(), base.raw(value), "e" * 64, True,
            prepared["lineage_sha256"], concurrent_change)
    assert called == [True]
    assert not (namespace / "metadata-observation.json").exists()
    assert not (namespace / "completion.json").exists()


@pytest.mark.parametrize("changed_leaf", ["metadata-observation.json", "completion.json"])
def test_terminal_leaf_mutation_after_publication_cannot_be_reported_as_verified_completion(tmp_path, changed_leaf):
    prepared = base.prepare(tmp_path)
    value = base.observation(prepared)
    namespace = Path(prepared["namespace"])
    calls = []
    def concurrent_change():
        calls.append(True)
        if len(calls) == 2:
            (namespace / changed_leaf).write_bytes(b"{}")
    with pytest.raises(base.supervisor.SupervisorRefusal):
        base.supervisor._complete(tmp_path.resolve(), base.raw(value), "e" * 64, True,
            prepared["lineage_sha256"], concurrent_change)
    assert calls == [True, True]
    assert (namespace / changed_leaf).read_bytes() == b"{}", "refusal preserves changed/ambiguous evidence, never cleans it"


def test_invented_existing_non_lane_root_is_fenced_as_non_temporary_before_any_constructor(monkeypatch):
    root = Path("/invented/non-temporary/historical-source")
    opened = []
    monkeypatch.setattr(Path, "exists", lambda _: True)
    monkeypatch.setattr(Path, "resolve", lambda self, **kwargs: self)
    monkeypatch.setattr(base.supervisor.os.path, "samefile", lambda *_: False)
    @contextmanager
    def forbidden_constructor(*args, **kwargs):
        opened.append(True)
        yield None
    monkeypatch.setattr(base.supervisor, "_held_source", forbidden_constructor)
    with pytest.raises(base.supervisor.SupervisorRefusal, match="fixture-not-private-temporary-root"):
        base.supervisor._fixture_root(root)
    assert opened == []


def test_production_git_identity_has_fixed_binary_no_inherited_secret_environment_or_monitor_hook(monkeypatch):
    observed = []
    def fixture_git(command, **kwargs):
        observed.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"invented local code metadata")
    monkeypatch.setattr(base.supervisor.subprocess, "run", fixture_git)
    assert base.supervisor._git(base.supervisor.LANE_ROOT, "rev-parse", "HEAD") == b"invented local code metadata"
    command, kwargs = observed[0]
    assert command[:4] == ["/usr/bin/git", "--no-optional-locks", "-c", "core.fsmonitor=false"]
    assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    assert kwargs["stdin"] == base.supervisor.subprocess.DEVNULL
    assert kwargs["stderr"] == base.supervisor.subprocess.DEVNULL
    assert kwargs["stdout"] == base.supervisor.subprocess.PIPE
