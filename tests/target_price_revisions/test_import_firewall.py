from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from research.target_price_revisions.import_firewall import (
    DEFAULT_ALLOWED_STDLIB_ROOTS,
    ImportBoundaryError,
    _validate_import_closure,
    validate_transitive_import_closure,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _package(root: Path, name: str = "guarded") -> Path:
    package = root / name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    return package


def test_current_target_package_transitive_import_closure_is_safe():
    reached = validate_transitive_import_closure(WORKSPACE_ROOT)

    assert "research" in reached
    assert "research.target_price_revisions" in reached
    assert "research.target_price_revisions.canonical" in reached
    assert "research.target_price_revisions.import_firewall" in reached
    assert "research.target_price_revisions.trust_root" in reached
    assert "research.target_price_revisions.windows_acl" in reached
    assert "research.analyst_revisions_v2" not in reached
    assert "execution" not in reached
    assert "importlib" not in DEFAULT_ALLOWED_STDLIB_ROOTS


def test_local_facade_cannot_hide_forbidden_import_and_reports_path(tmp_path):
    package = _package(tmp_path)
    (package / "__init__.py").write_text(
        "from . import facade\n", encoding="utf-8"
    )
    (package / "facade.py").write_text(
        "from . import safe_helper\n", encoding="utf-8"
    )
    (package / "safe_helper.py").write_text(
        "import execution.orders\n", encoding="utf-8"
    )

    with pytest.raises(ImportBoundaryError) as captured:
        _validate_import_closure(tmp_path, package_name="guarded")

    message = str(captured.value)
    assert "guarded.facade" in message
    assert "guarded.safe_helper" in message
    assert "execution.orders" in message
    assert "guarded\\safe_helper.py" in message or "guarded/safe_helper.py" in message


def test_imported_parent_package_initializer_is_in_closure(tmp_path):
    guarded = _package(tmp_path)
    (guarded / "__init__.py").write_text(
        "import facade_package.safe\n", encoding="utf-8"
    )
    facade = _package(tmp_path, "facade_package")
    (facade / "__init__.py").write_text(
        "import http.client\n", encoding="utf-8"
    )
    (facade / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(ImportBoundaryError) as captured:
        _validate_import_closure(tmp_path, package_name="guarded")

    message = str(captured.value)
    assert "facade_package.safe" in message
    assert "facade_package" in message
    assert "http.client" in message
    assert "facade_package\\__init__.py" in message or "facade_package/__init__.py" in message


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module('requests.sessions')\n",
        "import importlib as loader\nname = 'requests'\nloader.import_module(name)\n",
        "from importlib import import_module as load\nload('execution.orders')\n",
        "name = 'research.quantconnect'\n__import__(name)\n",
        "load = __import__\nload('requests.sessions')\n",
        "import importlib\nload = importlib.import_module\nload('requests')\n",
        (
            "import importlib\n"
            "load = getattr(importlib, 'import_module')\n"
            "load('requests')\n"
        ),
        "from safe_helper import helper as import_module\n",
        "import pathlib as importlib\n",
        "from pathlib import Path as __import__\n",
        "class Holder: pass\nload = Holder.import_module\n",
    ],
)
def test_import_aliases_and_reflection_cannot_bypass_firewall(tmp_path, source):
    package = _package(tmp_path)
    (package / "__init__.py").write_text(source, encoding="utf-8")

    with pytest.raises(ImportBoundaryError, match="import/reflection primitive"):
        _validate_import_closure(tmp_path, package_name="guarded")


@pytest.mark.parametrize(
    "source",
    [
        "runner = eval\nrunner(\"__import__('requests')\")\n",
        "runner = exec\nrunner(\"import requests\")\n",
        "builder = compile\nbuilder('import requests', '<x>', 'exec')\n",
        "scope = globals\nscope()['__builtins__']\n",
        "lookup = getattr\nlookup(object, '__getattribute__')\n",
        "value = __builtins__['__import__']\n",
    ],
)
def test_eval_exec_compile_and_namespace_indirection_fail_closed(tmp_path, source):
    package = _package(tmp_path)
    (package / "__init__.py").write_text(source, encoding="utf-8")

    with pytest.raises(ImportBoundaryError, match="import/reflection primitive"):
        _validate_import_closure(tmp_path, package_name="guarded")


def test_literal_nondangerous_getattr_remains_available(tmp_path):
    package = _package(tmp_path)
    (package / "__init__.py").write_text(
        "value = object()\ngetattr(value, '_authority', None)\n",
        encoding="utf-8",
    )

    assert _validate_import_closure(
        tmp_path, package_name="guarded"
    ) == ("guarded",)


@pytest.mark.parametrize("imported", ["third_party_facade", "sys"])
def test_only_explicitly_allowed_standard_library_roots_are_external(
    tmp_path, imported
):
    package = _package(tmp_path)
    (package / "__init__.py").write_text(
        f"import {imported}\n", encoding="utf-8"
    )

    with pytest.raises(ImportBoundaryError, match="unapproved external import"):
        _validate_import_closure(tmp_path, package_name="guarded")


def test_relative_import_cannot_escape_guarded_top_level_package(tmp_path):
    package = _package(tmp_path)
    (package / "__init__.py").write_text(
        "from ..outside import value\n", encoding="utf-8"
    )

    with pytest.raises(ImportBoundaryError, match="relative import escapes"):
        _validate_import_closure(tmp_path, package_name="guarded")


def test_guarded_package_symlink_is_rejected(tmp_path):
    package = _package(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    link = package / "linked.py"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"host cannot create a test symlink: {exc}")

    with pytest.raises(ImportBoundaryError, match="symlink"):
        _validate_import_closure(tmp_path, package_name="guarded")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_guarded_package_junction_is_rejected(tmp_path):
    package = _package(tmp_path)
    outside = tmp_path / "outside-directory"
    outside.mkdir()
    (outside / "payload.py").write_text("VALUE = 1\n", encoding="utf-8")
    junction = package / "linked-directory"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0 or not junction.is_junction():
        pytest.skip("host cannot create a test junction")

    with pytest.raises(ImportBoundaryError, match="junction"):
        _validate_import_closure(tmp_path, package_name="guarded")


def test_authoritative_wrapper_exposes_no_boundary_overrides(tmp_path):
    with pytest.raises(TypeError):
        validate_transitive_import_closure(
            tmp_path,
            package_name="caller.chosen",  # type: ignore[call-arg]
        )


def test_authoritative_wrapper_rejects_unlisted_local_modules(tmp_path):
    research = _package(tmp_path, "research")
    target = research / "target_price_revisions"
    target.mkdir()
    (target / "__init__.py").write_text(
        "import research.unlisted_strategy\n", encoding="utf-8"
    )
    (research / "unlisted_strategy.py").write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(ImportBoundaryError, match="unapproved repository-local"):
        validate_transitive_import_closure(tmp_path)


def test_import_does_not_fall_back_to_a_local_ancestor_package(tmp_path):
    package = _package(tmp_path)
    local = _package(tmp_path, "local_facade")
    (package / "__init__.py").write_text(
        "import local_facade.missing_submodule\n", encoding="utf-8"
    )
    (local / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(ImportBoundaryError, match="unapproved external import"):
        _validate_import_closure(tmp_path, package_name="guarded")


@pytest.mark.parametrize("suffix", [".pyd", ".so"])
def test_extension_module_cannot_substitute_for_reviewed_source(tmp_path, suffix):
    package = _package(tmp_path)
    (package / "__init__.py").write_text("import opaque_helper\n", encoding="utf-8")
    (tmp_path / f"opaque_helper{suffix}").write_bytes(b"not executable")

    with pytest.raises(ImportBoundaryError, match="reviewed Python source"):
        _validate_import_closure(tmp_path, package_name="guarded")
