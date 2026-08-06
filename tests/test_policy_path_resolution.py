"""Entry-point policy-file resolution (owner request, 2026-08-05).

The owner asked that the app stop defaulting to `default_policy.json` and
load their own `my_policy.json` without retyping it every session. That
makes *which file governs proposals* a default, so these tests pin the
precedence and — more importantly — the two directions where a wrong
answer would be dangerous:

  * a policy file the caller NAMED but that does not exist must raise,
    never silently resolve to a different (here: more permissive) policy;
  * `load_policy()` with no argument must keep meaning the committed
    default, so library code and the rest of the suite cannot change
    behavior depending on whether an untracked personal policy happens to
    exist on the machine running the tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from assistant import policy as policy_module
from assistant.policy import (
    DEFAULT_POLICY_PATH,
    POLICY_PATH_ENV_VAR,
    load_policy,
    resolve_policy_path,
)


def _write_policy(path: Path, *, name: str, version: str) -> Path:
    """Write a real, loadable policy file (not a stub) at `path`."""
    payload = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    payload["name"] = name
    payload["version"] = version
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Point both module path constants at a temp directory.

    Without this the tests would read whichever policy files happen to sit
    in `assistant/`, so the result would differ between the owner's machine
    (where `my_policy.json` exists) and a fresh clone (where it does not).
    """
    personal = tmp_path / "my_policy.json"
    default = _write_policy(tmp_path / "default_policy.json", name="d", version="1.0.0")
    monkeypatch.setattr(policy_module, "PERSONAL_POLICY_PATH", personal)
    monkeypatch.setattr(policy_module, "DEFAULT_POLICY_PATH", default)
    monkeypatch.delenv(POLICY_PATH_ENV_VAR, raising=False)
    return {"dir": tmp_path, "personal": personal, "default": default}


def test_personal_policy_wins_when_it_exists(isolated_paths):
    """The owner's actual request: my_policy.json without retyping it."""
    personal = _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    assert resolve_policy_path() == personal
    assert load_policy(resolve_policy_path()).name == "p"


def test_falls_back_to_the_committed_default_when_absent(isolated_paths):
    """A fresh clone has no my_policy.json; it must still start, on the
    conservative committed baseline rather than failing."""
    assert not isolated_paths["personal"].exists()
    assert resolve_policy_path() == isolated_paths["default"]


def test_explicit_argument_outranks_everything(isolated_paths, monkeypatch):
    _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    env_file = _write_policy(isolated_paths["dir"] / "env.json", name="e", version="3.0.0")
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, str(env_file))
    chosen = _write_policy(isolated_paths["dir"] / "chosen.json", name="c", version="4.0.0")

    assert resolve_policy_path(chosen) == chosen
    assert resolve_policy_path(str(chosen)) == chosen


def test_environment_variable_outranks_the_personal_file(isolated_paths, monkeypatch):
    _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    env_file = _write_policy(isolated_paths["dir"] / "env.json", name="e", version="3.0.0")
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, str(env_file))

    assert resolve_policy_path() == env_file


def test_a_named_but_missing_explicit_file_raises_instead_of_falling_back(
    isolated_paths,
):
    """The dangerous direction. If a caller names a policy that is not
    there and we quietly resolved the personal file instead, proposals
    would be governed by a MORE permissive policy than the one asked for,
    with nothing on screen to say so."""
    _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    missing = isolated_paths["dir"] / "not_here.json"

    with pytest.raises(FileNotFoundError):
        resolve_policy_path(missing)


def test_a_named_but_missing_env_policy_raises_instead_of_falling_back(
    isolated_paths, monkeypatch
):
    _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, str(isolated_paths["dir"] / "gone.json"))

    with pytest.raises(FileNotFoundError):
        resolve_policy_path()


def test_blank_environment_variable_is_ignored(isolated_paths, monkeypatch):
    """An empty/whitespace value is an unset variable, not a request for a
    file named "" — that would otherwise raise on every command."""
    personal = _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, "   ")

    assert resolve_policy_path() == personal


def test_use_env_false_skips_the_variable_without_touching_os_environ(
    isolated_paths, monkeypatch
):
    """CROPS-001. A caller that has already reported a broken environment
    variable continues down the chain via the parameter, NOT by mutating
    process-global state that Streamlit's per-session threads share."""
    import os

    personal = _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    broken = str(isolated_paths["dir"] / "gone.json")
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, broken)

    assert resolve_policy_path(use_env=False) == personal
    # The variable must still be exactly where it was afterwards.
    assert os.environ[POLICY_PATH_ENV_VAR] == broken


def test_use_env_false_still_honors_an_explicit_path(isolated_paths, monkeypatch):
    """Skipping the environment must not also disable the highest-priority
    level; an explicit argument still outranks everything."""
    _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, str(isolated_paths["dir"] / "gone.json"))
    chosen = _write_policy(isolated_paths["dir"] / "chosen.json", name="c", version="4.0.0")

    assert resolve_policy_path(chosen, use_env=False) == chosen


def test_bare_load_policy_still_means_the_committed_default():
    """Machine independence. Dozens of tests and `context_builder`'s
    fallback call `load_policy()` with no argument; if that started
    resolving the personal file, results would depend on an untracked file
    existing on a given computer. Deliberately NOT using the isolating
    fixture — this asserts against the real repository files."""
    from assistant.policy import DEFAULT_POLICY_PATH as real_default

    assert load_policy().name == load_policy(real_default).name
    assert load_policy().version == load_policy(real_default).version


def test_cli_parser_survives_a_broken_policy_env_and_honors_explicit_policy(
    isolated_paths, monkeypatch
):
    """Eager default=resolve_policy_path() would brick --help and --policy."""
    from scripts.run_personal_assistant import build_parser

    monkeypatch.setenv(
        POLICY_PATH_ENV_VAR, str(isolated_paths["dir"] / "missing-env-policy.json")
    )
    help_text = build_parser().format_help()
    assert "--policy" in help_text

    chosen = _write_policy(
        isolated_paths["dir"] / "explicit.json", name="c", version="9.0.0"
    )
    args = build_parser().parse_args(["--policy", str(chosen), "verify-db-schema"])
    assert args.policy == str(chosen)
    # Omitted --policy stays unresolved until main() so parser construction
    # cannot raise on a bad environment default.
    omitted = build_parser().parse_args(["verify-db-schema"])
    assert omitted.policy is None


def test_every_cli_load_policy_call_goes_through_the_resolver():
    """OPSREV-006 generalized. The behavioural tests prove the handlers that
    they exercise; they cannot prove the NEXT handler someone adds.

    `--policy` defaults to None, so a new `load_policy(args.policy)` would
    pass None straight into `Path()` and raise TypeError — but only on the
    one command that happened to be exercised. That is precisely how the
    original regression reached a green focused run and failed the full
    suite.

    An AST check is the right tool here: the defect is a wrong ARGUMENT to a
    correct function, which `load_policy` itself cannot observe.
    """
    import ast

    source = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "run_personal_assistant.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    offenders = []
    seen = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "load_policy"):
            continue
        seen += 1
        if not node.args:
            offenders.append((node.lineno, "load_policy() with no argument"))
            continue
        arg = node.args[0]
        resolved = (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Name)
            and arg.func.id == "_cli_policy_path"
        )
        if not resolved:
            offenders.append((node.lineno, ast.unparse(arg)))

    assert seen, "expected load_policy call sites in the CLI"
    assert not offenders, (
        "every CLI load_policy() must take _cli_policy_path(args); "
        f"offending sites: {offenders}"
    )


def test_cli_handlers_resolve_none_policy_without_going_through_main(
    isolated_paths, monkeypatch
):
    """OPSREV-006. Lazy argparse default must not leave handlers unable to
    load a policy when tests (or any caller) invoke them after parse_args
    without going through main()."""
    from scripts.run_personal_assistant import _cli_policy_path, build_parser

    personal = _write_policy(isolated_paths["personal"], name="p", version="2.0.0")
    args = build_parser().parse_args(["verify-db-schema"])
    assert args.policy is None
    assert _cli_policy_path(args) == str(personal)