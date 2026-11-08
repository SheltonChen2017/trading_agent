"""Invented policies/admin records only; caller supplies native test fencing."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from research import insider_buying_pilot_readback_isolation_v2 as m


def _layout():
    files = {}
    for path in m._admin_paths():
        files[str(path)] = {"present": True, "bytes": 4, "sha256": "a" * 64,
                            "version": [1, 2, 0o100644, 1, 501, 20, 4, 8, 9, 0]}
    return {"common": str(m.EXPECTED_COMMON), "worktree": str(m.EXPECTED_GITDIR), "files": files}


def _runtime(monkeypatch):
    values = ((Path("/opt/ib386-python"),), (Path("/opt/ib386-python/bin/python3.13"),), ())
    monkeypatch.setattr(m, "runtime_layout", lambda _python=None: values)
    return values


@pytest.mark.parametrize("directory", (
    "/Volumes/ib386/python", "/Volumes", "/Users/sheltonchen/Library/Keychains/ib386",
    "/Library/Keychains/ib386", "/Users/sheltonchen/Library/Application Support/other/py",
    "/Users/sheltonchen/Documents/other-lane/py", "/Users/sheltonchen/Desktop/py",
    "/Users/sheltonchen/Downloads/py", "/Users/sheltonchen/Documents", "/Users", "/",
))
def test_global_runtime_roots_reject_both_coverage_and_nesting(directory):
    with pytest.raises(m.IsolationError, match="runtime_refused"):
        m.require_disjoint((Path(directory),))


def test_common_root_ancestry_does_not_reject_unrelated_runtime_and_data():
    m.require_disjoint((Path("/opt/invented-python"),), (Path("/private/tmp/invented-data"),))


@pytest.mark.parametrize("covering", (False, True))
def test_symlinked_runtime_cannot_hide_a_nested_or_covering_private_tree(tmp_path, covering):
    protected = tmp_path / "protected"; protected.mkdir()
    nested = protected / "inside"; nested.mkdir()
    alias = tmp_path / "alias"; alias.symlink_to(tmp_path if covering else nested, target_is_directory=True)
    with pytest.raises(m.IsolationError, match="runtime_refused"):
        m.require_disjoint((alias,), (protected,))


@pytest.mark.parametrize("covering", (False, True))
def test_physical_endpoint_aliases_are_refused_even_with_unrelated_lexical_names(monkeypatch, covering):
    runtime, protected = Path("/invented/runtime"), Path("/invented/data")
    def metadata(path):
        if path == runtime:
            return {runtime: (1, 9), runtime.parent: (1, 7 if covering else 8)}
        return {protected: (1, 7 if covering else 9), protected.parent: (1, 9 if covering else 7)}
    monkeypatch.setattr(m, "_ancestors", metadata)
    with pytest.raises(m.IsolationError, match="runtime_refused"):
        m.require_disjoint((runtime,), (protected,))


def test_metadata_failure_is_finite_and_not_ignored(monkeypatch):
    def fail(_path):
        raise m.IsolationError("metadata_refused")
    monkeypatch.setattr(m, "_ancestors", fail)
    with pytest.raises(m.IsolationError, match="^metadata_refused$"):
        m.require_disjoint((Path("/opt/invented-runtime"),))


@pytest.mark.parametrize("name", (
    "./artifacts/private.py", "artifacts/private.py", "research/../private.py",
    "research//private.py", "/research/private.py", "research/./private.py",
    "research/artifacts/private.py", "research/file.json",
))
def test_source_names_are_normalized_python_leaves_only(name):
    with pytest.raises(m.IsolationError, match="source_refused"):
        m.validate_source_names((name,))


def test_source_name_positive_control():
    names = ("research/insider_buying_pilot_readback_isolation_v2.py",)
    assert m.validate_source_names(names) == names


def test_health_profile_has_zero_data_and_no_write_or_fork_grant(monkeypatch):
    _runtime(monkeypatch)
    profile = m.policy(sources=("research/invented.py",))
    assert all(token in profile for token in ("(deny network*)", "(deny process-fork)",
        "(deny process-exec)", "(deny file-write*)", "(deny file-read-data)"))
    assert "(allow file-write" not in profile
    assert str(m.EPOCH_ROOT) not in profile
    assert str(m.RECORD_SOURCE) not in profile
    assert '(subpath "' + str(m.ROOT) + '")' not in profile
    assert '(literal "' + str(m.GIT_IMAGE) + '")' in profile
    executable_grants = profile.split("(allow process-exec ", 1)[1].split("(allow file-read-data", 1)[0]
    assert str(m.GIT_IMAGE) not in executable_grants


def test_saved_reader_profile_grants_only_the_exact_five_saved_leaves(monkeypatch):
    _runtime(monkeypatch)
    leaves = tuple(m.EPOCH_ROOT / name for name in m.OUTPUT_NAMES)
    profile = m.policy(sources=("research/invented.py",), data_leaves=leaves)
    assert all("(literal " + json.dumps(str(path)) + ")" in profile for path in leaves)
    assert '(subpath "' + str(m.EPOCH_ROOT) + '")' not in profile
    assert "failure.json" not in profile and "(allow file-write" not in profile
    assert "(deny process-fork)" in profile


def test_installed_controller_needs_no_initial_python_exec_allowance(monkeypatch):
    _runtime(monkeypatch)
    profile = m.policy(sources=("research/invented.py",), controller=True)
    assert "(deny process-exec)" in profile and "(deny process-fork)" in profile
    assert "(allow process-exec" not in profile and "(allow file-write" not in profile
    assert str(m.EPOCH_ROOT) not in profile


@pytest.mark.parametrize("fault", ("git", "data", "alias"))
def test_controller_role_cannot_gain_git_data_or_boolean_alias(monkeypatch, fault):
    _runtime(monkeypatch)
    with pytest.raises(m.IsolationError):
        m.policy(sources=("research/invented.py",), controller=1 if fault == "alias" else True,
                 git=fault == "git", admin=_layout() if fault == "git" else None,
                 data_leaves=tuple(m.EPOCH_ROOT / name for name in m.OUTPUT_NAMES) if fault == "data" else ())


@pytest.mark.parametrize("fault", ("partial", "duplicate", "neighbor", "with-git"))
def test_data_scope_cannot_be_widened_or_mixed_with_git(monkeypatch, fault):
    _runtime(monkeypatch)
    leaves = tuple(m.EPOCH_ROOT / name for name in m.OUTPUT_NAMES)
    if fault == "partial": leaves = leaves[:-1]
    elif fault == "duplicate": leaves = (*leaves[:-1], leaves[0])
    elif fault == "neighbor": leaves = (*leaves[:-1], m.EPOCH_ROOT / "failure.json")
    with pytest.raises(m.IsolationError, match="data_scope_refused"):
        m.policy(sources=("research/invented.py",), data_leaves=leaves,
                 git=fault == "with-git", admin=_layout() if fault == "with-git" else None)


def test_git_profile_only_adds_exact_admin_and_directory_literals(monkeypatch):
    _runtime(monkeypatch)
    profile = m.policy(sources=("research/invented.py",), admin=_layout(), git=True,
        source_directories=(m.ROOT / "research",), gitignore_leaves=(m.ROOT / ".gitignore",))
    assert '(subpath "' + str(m.EXPECTED_COMMON) + '")' in profile
    assert '(subpath "' + str(m.ROOT) + '")' not in profile
    assert '(literal "' + str(m.ROOT / "research") + '")' in profile
    assert '(literal "' + str(m.ROOT / ".gitignore") + '")' in profile
    assert '(literal "' + str(m.RECORD_SOURCE) + '")' in profile
    assert '(subpath "' + str(m.RECORD_SOURCE.parent) + '")' not in profile
    assert '(literal "' + str(m.ROOT / ".gitattributes") + '")' in profile
    assert '(literal "' + str(m.ROOT / "research/.gitattributes") + '")' in profile
    assert '(literal "' + str(m.GIT_IMAGE) + '")' in profile
    assert "(deny process-fork)" not in profile
    assert profile.count("(allow file-write") == 1
    assert '(allow file-write-data (literal "/dev/null"))' in profile
    assert str(m.EPOCH_ROOT) not in profile


@pytest.mark.parametrize("path", (m.ROOT.parent, m.ROOT / "research/../docs", Path("/Volumes")))
def test_git_directory_literals_cannot_leave_or_alias_the_current_source(monkeypatch, path):
    _runtime(monkeypatch)
    with pytest.raises(m.IsolationError):
        m.policy(sources=("research/invented.py",), admin=_layout(), git=True,
                 source_directories=(path,))


def test_unknown_runtime_extension_is_not_an_arbitrary_read_grant(monkeypatch):
    _runtime(monkeypatch)
    with pytest.raises(m.IsolationError, match="runtime_refused"):
        m.policy(sources=("research/invented.py",), runtime_directories=(Path("/opt/unqualified"),))


def test_existing_attribute_configuration_is_refused_instead_of_trusted(monkeypatch):
    target = m.ROOT / "tests/.gitattributes"
    original = Path.lstat
    monkeypatch.setattr(Path, "lstat", lambda path: object() if path == target else original(path))
    with pytest.raises(m.IsolationError, match="attribute_config_refused"):
        m.attribute_controls(("tests/invented.py",))


def test_admin_discovery_reads_fixed_pointers_and_config_without_git(monkeypatch):
    observed = []
    values = {m.ROOT / ".git": ("gitdir: " + str(m.EXPECTED_GITDIR) + "\n").encode(),
        m.EXPECTED_GITDIR / "commondir": b"../..\n",
        m.EXPECTED_GITDIR / "gitdir": (str(m.ROOT / ".git") + "\n").encode(),
        m.EXPECTED_COMMON / "config": b"[core]\n", m.EXPECTED_GITDIR / "config.worktree": None}
    values[m.EXPECTED_COMMON / "info/exclude"] = None
    values[m.EXPECTED_COMMON / "info/attributes"] = None
    def read(path, *, optional=False):
        observed.append((path, optional)); body = values[path]
        return body, {"present": False} if body is None else {
            "present": True, "bytes": len(body), "sha256": "a" * 64,
            "version": [1, 2, 0o100644, 1, 501, 20, len(body), 8, 9, 0]}
    monkeypatch.setattr(m, "_read_admin", read)
    layout = m.discover_admin()
    assert set(layout["files"]) == {str(p) for p in m._admin_paths()}
    assert observed == [(p, m._optional_admin(p)) for p in m._admin_paths()]
    assert layout["files"][str(m.EXPECTED_GITDIR / "config.worktree")] == {"present": False}
    assert layout["files"][str(m.EXPECTED_COMMON / "info/exclude")] == {"present": False}


def test_shared_admin_metadata_exception_refuses_physical_private_alias(monkeypatch):
    def metadata(path):
        if path == m.EXPECTED_COMMON:
            return {path: (1, 900)}
        if path == Path("/Volumes"):
            return {path: (1, 900)}
        return {}
    monkeypatch.setattr(m, "_ancestors", metadata)
    monkeypatch.setattr(m, "_read_admin", lambda *_a, **_k: pytest.fail("read before admin overlap proof"))
    with pytest.raises(m.IsolationError, match="admin_refused"):
        m.discover_admin()


def test_wrong_admin_pointer_refuses_before_following_any_other_path(monkeypatch):
    observed = []
    def read(path, **_kwargs):
        observed.append(path)
        return b"gitdir: /Volumes/forbidden\n", {"present": True}
    monkeypatch.setattr(m, "_read_admin", read)
    with pytest.raises(m.IsolationError, match="admin_refused"):
        m.discover_admin()
    assert observed == [m.ROOT / ".git"]


def test_admin_recheck_detects_any_pointer_config_or_absence_change(monkeypatch):
    layout = _layout(); changed = deepcopy(layout)
    changed["files"][str(m.EXPECTED_COMMON / "config")]["sha256"] = "b" * 64
    monkeypatch.setattr(m, "discover_admin", lambda: changed)
    with pytest.raises(m.IsolationError, match="admin_changed"):
        m.check_admin(layout)


def test_admin_leaf_reader_positive_control_uses_nofollow_held_chain(tmp_path):
    path = tmp_path / "config"; path.write_bytes(b"[core]\n")
    body, pin = m._read_admin(path)
    assert body == b"[core]\n" and pin["present"] is True and pin["bytes"] == 7


def test_empty_admin_configuration_is_hash_bound_not_refused(tmp_path):
    path = tmp_path / "config"; path.write_bytes(b"")
    body, pin = m._read_admin(path)
    assert body == b"" and pin["bytes"] == 0 and pin["present"] is True


def test_admin_reader_detects_renamed_parent_even_if_held_fd_and_body_stay_valid(monkeypatch, tmp_path):
    parent = tmp_path / "active"; parent.mkdir()
    path = parent / "config"; path.write_bytes(b"[core]\n")
    original = m.os.pread
    def replace_parent(fd, count, offset):
        body = original(fd, count, offset)
        parent.rename(tmp_path / "replaced")
        parent.mkdir(); (parent / "config").write_bytes(body)
        return body
    monkeypatch.setattr(m.os, "pread", replace_parent)
    with pytest.raises(m.IsolationError, match="admin_refused"):
        m._read_admin(path)


def test_admin_reader_refuses_symlinked_leaf(tmp_path):
    target = tmp_path / "target"; target.write_bytes(b"[core]\n")
    path = tmp_path / "config"; path.symlink_to(target)
    with pytest.raises(m.IsolationError, match="admin_refused"):
        m._read_admin(path)


@pytest.mark.parametrize("fault", ("common", "worktree", "extra-file", "bool-size", "size-version", "wrong-absent"))
def test_untrusted_admin_layout_shape_cannot_broaden_the_read_scope(fault):
    layout = _layout()
    if fault == "common": layout["common"] = str(Path("/Volumes"))
    elif fault == "worktree": layout["worktree"] = str(m.EXPECTED_COMMON)
    elif fault == "extra-file": layout["files"]["/Volumes/private"] = {"present": False}
    elif fault == "bool-size": layout["files"][str(m.EXPECTED_COMMON / "config")]["bytes"] = True
    elif fault == "size-version": layout["files"][str(m.EXPECTED_COMMON / "config")]["bytes"] = 5
    else: layout["files"][str(m.EXPECTED_COMMON / "config")] = {"present": False}
    with pytest.raises(m.IsolationError, match="admin_refused"):
        m.git_environment(layout)


def test_git_invocation_uses_fixed_image_fixed_root_and_explicit_config_denials():
    command = m.git_command(("status", "--porcelain=v2", "--branch", "--untracked-files=all"), _layout())
    assert command[:4] == (str(m.GIT_IMAGE), "--no-pager", "--no-replace-objects", "--no-optional-locks")
    for setting in ("core.fsmonitor=false", "core.hooksPath=/dev/null", "core.excludesFile=/dev/null",
                    "core.untrackedCache=false", "maintenance.auto=false", "gc.auto=0", "credential.helper="):
        assert setting in command
    assert "--git-dir=" + str(m.EXPECTED_GITDIR) in command
    assert "--work-tree=" + str(m.ROOT) in command
    env = m.git_environment(_layout())
    assert env["GIT_CONFIG_GLOBAL"] == env["GIT_CONFIG_SYSTEM"] == "/dev/null"
    assert env["GIT_CONFIG_NOSYSTEM"] == env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert env["GIT_CONFIG_COUNT"] == env["GIT_OPTIONAL_LOCKS"] == env["GIT_TERMINAL_PROMPT"] == "0"
    assert "HOME" not in env and "GIT_SSH_COMMAND" not in env


def test_diff_always_disables_external_driver_and_textconv_execution():
    command = m.git_command(("diff", "--name-only"), _layout())
    assert command[-4:] == ("diff", "--no-ext-diff", "--no-textconv", "--name-only")


@pytest.mark.parametrize("arguments", (
    ("push", "origin"), ("fetch", "origin"), ("config", "core.fsmonitor"),
    ("-c", "core.fsmonitor=/bin/sh", "status"), ("status", "--no-optional-locks"),
    ("show", "a" * 40 + ":./artifacts/private.py"),
    ("show", "HEAD:research/invented.py"), ("show", "a" * 40 + ":/private/file.py"),
    ("ls-tree", "--exec=/usr/bin/security", "a" * 40),
))
def test_git_wrapper_rejects_actions_external_options_and_unnormalized_source_paths(arguments):
    with pytest.raises(m.IsolationError, match="git_refused"):
        m.git_command(arguments, _layout())


@pytest.mark.parametrize("arguments", (
    ("rev-parse", "--show-toplevel"), ("rev-parse", "--verify", "HEAD"),
    ("ls-tree", "-r", "-d", "--name-only", "a" * 40),
    ("ls-tree", "-r", "--name-only", "a" * 40),
    ("show", "a" * 40 + ":research/invented.py"),
    ("show", "a" * 40 + ":.gitignore"),
))
def test_explicit_read_only_git_shapes_remain_supported(arguments):
    assert m.git_command(arguments, _layout())[-len(arguments):] == arguments
