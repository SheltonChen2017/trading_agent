"""Collection guards use real child imports; no custody root is executed.

An absent-fcntl simulation proves the documented unsupported-host treatment.
The child is still required to inherit the test runner's OS network denial.

Section 350 counter-review: 25 new guards remain, while 17 production-pinned
test images keep their exact pre-review bytes. The explicit lane pytest plugin
handles their unsupported-host collection; shared/default pytest is unchanged.
Neither collection policy establishes a Windows custody port.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
_platform_spec = importlib.util.spec_from_file_location(
    "insider_buying_pytest_platform", ROOT / "tests" / "insider_buying_pytest_platform.py",
)
assert _platform_spec is not None and _platform_spec.loader is not None
platform_policy = importlib.util.module_from_spec(_platform_spec)
sys.modules[_platform_spec.name] = platform_policy
_platform_spec.loader.exec_module(platform_policy)
PRE_GUARD_COMMIT = "85c7755deb75b5d0c61cc4a63a385d4b87b55110"
GUARDED_FILES = (
    "test_insider_buying_sec_all_form4_parent_ambiguous_diagnostic.py",
    "test_insider_buying_sec_all_form4_parent_ambiguous_diagnostic_verifier.py",
    "test_insider_buying_sec_all_form4_parent_campaign.py",
    "test_insider_buying_sec_all_form4_parent_recovery_campaign.py",
    "test_insider_buying_sec_all_form4_parent_recovery_executor.py",
    "test_insider_buying_sec_all_form4_parent_recovery_partial_verifier.py",
    "test_insider_buying_sec_all_form4_parent_recovery_preflight.py",
    "test_insider_buying_sec_all_form4_parent_recovery_union.py",
    "test_insider_buying_sec_all_form4_parent_recovery_verifier.py",
    "test_insider_buying_sec_parent_refusal_diagnostic.py",
    "test_insider_buying_sec_recovery_v4_capture.py",
    "test_insider_buying_sec_recovery_v4_combined.py",
    "test_insider_buying_sec_recovery_v4_continuation_capture.py",
    "test_insider_buying_sec_recovery_v4_projection.py",
    "test_insider_buying_sec_recovery_v4_reconciliation.py",
    "test_insider_buying_sec_selected_parent_projection_adapter.py",
)
# Section 350: lane tests added after the section-161 declaration that loaded a
# POSIX-only module before any guard, so Windows collection errored on them.
PRE_GUARD_COMMIT_350 = "1635900df1385ebeb4d791948b7816e2a875435e"
_REVIEW_FILES_350 = (
    "test_insider_buying_affected_quarter_selector_launcher_v3.py",
    "test_insider_buying_affected_quarter_selector_runner.py",
    "test_insider_buying_affected_quarter_selector_verification_v2.py",
    "test_insider_buying_pilot_coverage_audit.py",
    "test_insider_buying_pilot_event_composition.py",
    "test_insider_buying_pilot_production_composition.py",
    "test_insider_buying_pilot_sec_exposure.py",
    "test_insider_buying_pilot_sec_fresh_selection.py",
    "test_insider_buying_pilot_sec_fresh_selection_runner.py",
    "test_insider_buying_pilot_sec_locator_diagnostic.py",
    "test_insider_buying_pilot_sec_locator_diagnostic_runner.py",
    "test_insider_buying_pilot_sec_parent_audit.py",
    "test_insider_buying_pilot_sec_parent_audit_runner.py",
    "test_insider_buying_pilot_sec_parent_readback.py",
    "test_insider_buying_pilot_sec_parent_structure_runner.py",
    "test_insider_buying_pilot_sec_roster.py",
    "test_insider_buying_qc_sdk_metadata_custody.py",
    "test_insider_buying_qc_sdk_metadata_supervisor.py",
    "test_insider_buying_sec_2006q1_parent_bootstrap.py",
    "test_insider_buying_sec_feed_compact_capture_v1_review.py",
    "test_insider_buying_sec_feed_compact_members_v1.py",
    "test_insider_buying_sec_feed_compact_members_v1_review.py",
    "test_insider_buying_sec_feed_format_v3.py",
    "test_insider_buying_sec_feed_nc_binding_accounting_review.py",
    "test_insider_buying_sec_feed_nc_padding_review.py",
    "test_insider_buying_sec_feed_nc_route_v1.py",
    "test_insider_buying_sec_feed_nc_route_v1_barrier_review.py",
    "test_insider_buying_sec_feed_nc_route_v1_review.py",
    "test_insider_buying_sec_feed_nc_source_binding_observe_v1.py",
    "test_insider_buying_sec_feed_nc_source_binding_observe_v1_review.py",
    "test_insider_buying_sec_feed_nc_source_binding_v1.py",
    "test_insider_buying_sec_feed_prefix_capture_v1.py",
    "test_insider_buying_sec_feed_prefix_capture_v1_review.py",
    "test_insider_buying_sec_feed_prefix_format_v1.py",
    "test_insider_buying_sec_feed_prefix_format_v1_review.py",
    "test_insider_buying_sec_feed_prefix_nc_observe_v1.py",
    "test_insider_buying_sec_feed_prefix_nc_structure_v1.py",
    "test_insider_buying_sec_feed_prefix_nc_structure_v1_review.py",
    "test_insider_buying_sec_feed_prefix_shape_runner_v1.py",
    "test_insider_buying_sec_feed_prefix_shape_runner_v1_review.py",
    "test_insider_buying_sec_feed_prefix_shape_v1.py",
    "test_insider_buying_sec_feed_prefix_shape_v1_review.py",
)
# Frozen test bytes are production custody inputs. Keep their exact images and
# apply unsupported-host collection policy through the explicit lane plugin.
FROZEN_FILES_350 = tuple(Path(name).name for name in platform_policy.FROZEN_POSIX_TEST_SHA256)
GUARDED_FILES_350 = tuple(name for name in _REVIEW_FILES_350 if name not in FROZEN_FILES_350)
PROBES = tuple((PRE_GUARD_COMMIT, name) for name in GUARDED_FILES) + tuple(
    (PRE_GUARD_COMMIT_350, name) for name in GUARDED_FILES_350
)
_CHILD = r"""
import importlib.abc
import importlib.util
import json
import sys

request = json.load(sys.stdin)
# -I drops the user site; re-add only the parent's site-packages so pytest resolves
for entry in request["site_packages"]:
    if entry not in sys.path:
        sys.path.append(entry)
sys.path.insert(0, request["root"])
import pytest
if request["missing_fcntl"]:
    sys.modules.pop("fcntl", None)

class LaneImportReached(RuntimeError):
    pass

class GuardFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if request["missing_fcntl"] and fullname == "fcntl":
            raise ModuleNotFoundError("invented unsupported host: fcntl", name="fcntl")
        if (fullname == "research" or fullname.startswith("research.")
                or fullname.startswith("test_insider_buying")):
            raise LaneImportReached("research import reached: " + fullname)

def _file_load_reached(name, location, *args, **kwargs):
    raise LaneImportReached("research import reached: file load " + str(location))

sys.meta_path.insert(0, GuardFinder())
importlib.util.spec_from_file_location = _file_load_reached
try:
    exec(compile(request["prefix"], request["filename"], "exec"),
         {"__name__": "invented_collection_prefix", "__file__": request["filename"]})
except pytest.skip.Exception as error:
    print(json.dumps({"outcome": "skipped", "reason": str(error)}))
except (ModuleNotFoundError, LaneImportReached) as error:
    print(json.dumps({"outcome": "collection-error", "reason": str(error)}))
else:
    raise AssertionError("collection prefix must reach the poisoned research import or skip")
"""

# --- AST-only scan of where a lane test first loads a POSIX-only module -----
_RESEARCH_FILE_RE = re.compile(r"research/(insider_buying(?:/[A-Za-z0-9_]+)?[A-Za-z0-9_]*)\.py")
_SIBLING_FILE_RE = re.compile(r"(test_insider_buying[A-Za-z0-9_]*)\.py")
_REACH_CACHE: dict[str, bool] = {}


def _module_path(name: str) -> Path | None:
    if not name.startswith("research."):
        return None
    candidate = ROOT / "research" / Path(*name.split(".")[1:])
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    if (candidate / "__init__.py").is_file():
        return candidate / "__init__.py"
    return None


def _import_names(statement: ast.stmt, package: str) -> list[str]:
    """Unconditional module-level import names of one Import/ImportFrom statement."""
    if isinstance(statement, ast.Import):
        return [alias.name for alias in statement.names]
    if isinstance(statement, ast.ImportFrom):
        module = statement.module or ""
        if statement.level:
            base = package if statement.level == 1 else ".".join(package.split(".")[: -(statement.level - 1)])
            module = f"{base}.{module}" if module else base
        return [module] + [f"{module}.{alias.name}" for alias in statement.names]
    return []


def _reaches_fcntl(path: Path, package: str, stack: tuple[str, ...] = ()) -> bool:
    key = str(path)
    if key in _REACH_CACHE:
        return _REACH_CACHE[key]
    if key in stack:
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = False
    for statement in tree.body:
        for name in _import_names(statement, package):
            if name == "fcntl" or name.startswith("fcntl."):
                result = True
            else:
                dependency = _module_path(name)
                if dependency is not None:
                    dependency_package = name if dependency.name == "__init__.py" else name.rsplit(".", 1)[0]
                    if _reaches_fcntl(dependency, dependency_package, stack + (key,)):
                        result = True
            if result:
                break
        if result:
            break
    _REACH_CACHE[key] = result
    return result


def _is_guard(statement: ast.stmt) -> bool:
    if isinstance(statement, (ast.Assign, ast.AnnAssign)) and isinstance(statement.value, ast.Call):
        statement = ast.Expr(value=statement.value)
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        function = statement.value.func
        if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name) and function.value.id == "pytest":
            if (function.attr == "importorskip" and statement.value.args
                    and isinstance(statement.value.args[0], ast.Constant) and statement.value.args[0].value == "fcntl"):
                return True
            if function.attr == "skip" and any(
                keyword.arg == "allow_module_level" and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True for keyword in statement.value.keywords
            ):
                return True
    if isinstance(statement, ast.If):
        condition = statement.test
        # Existing lane tests also explicitly defer all non-POSIX hosts. Only
        # this literal platform predicate is accepted, not an arbitrary branch.
        if (isinstance(condition, ast.Compare) and len(condition.ops) == 1
                and isinstance(condition.ops[0], ast.NotEq)
                and isinstance(condition.left, ast.Attribute)
                and isinstance(condition.left.value, ast.Name)
                and condition.left.value.id == "os" and condition.left.attr == "name"
                and len(condition.comparators) == 1
                and isinstance(condition.comparators[0], ast.Constant)
                and condition.comparators[0].value == "posix"):
            return any(_is_guard(inner) for inner in statement.body)
    # An arbitrary condition (including if False) does not establish a guard.
    return False


def _spec_load_targets(statement: ast.stmt, assigned: dict[str, ast.expr]) -> list[str]:
    """Module names loaded through spec_from_file_location in this statement."""
    found: list[str] = []
    for node in ast.walk(statement):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "spec_from_file_location" and len(node.args) >= 2):
            target = node.args[1]
            if isinstance(target, ast.Name) and target.id in assigned:
                target = assigned[target.id]
            for inner in ast.walk(target):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    match = _RESEARCH_FILE_RE.search(inner.value.replace("\\", "/"))
                    if match:
                        found.append("research." + match.group(1).replace("/", "."))
                    match = _SIBLING_FILE_RE.search(inner.value)
                    if match:
                        found.append("tests." + match.group(1))
    return found


def _lane_loads(path: Path) -> list[tuple[bool, ast.stmt, bool]]:
    """Every module-level statement that loads a lane module, sibling test, or fcntl.

    Each entry is (guard_seen_before, statement, reaches_fcntl).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guarded, assigned, loads = False, {}, []
    for statement in tree.body:
        if _is_guard(statement):
            guarded = True
            continue
        if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)):
            assigned[statement.targets[0].id] = statement.value
        for name in _import_names(statement, "tests") + _spec_load_targets(statement, assigned):
            if name == "fcntl" or name.startswith("fcntl."):
                loads.append((guarded, statement, True))
            elif name.startswith("test_insider_buying") or name.startswith("tests.test_insider_buying"):
                sibling = ROOT / "tests" / (name.split(".")[-1] + ".py")
                if sibling.is_file() and sibling.resolve() != path.resolve():
                    loads.append((guarded, statement, _first_posix_load(sibling)[1] is not None))
            else:
                dependency = _module_path(name)
                if dependency is not None:
                    dependency_package = name if dependency.name == "__init__.py" else name.rsplit(".", 1)[0]
                    loads.append((guarded, statement, _reaches_fcntl(dependency, dependency_package)))
    return loads


def _first_posix_load(path: Path) -> tuple[bool | None, ast.stmt | None]:
    """If any module-level load reaches fcntl: (guard precedes the FIRST lane load?, that first load).

    The guard must come before every lane load, not merely before the first
    POSIX-reaching one, so the collection prefix and the guard rule agree.
    """
    loads = _lane_loads(path)
    if not any(reaches for _, _, reaches in loads):
        return None, None
    return loads[0][0], loads[0][1]


def _collection_prefix(source: str, path: Path) -> str:
    """Execute only the header through the first lane-module or sibling-test load."""
    tree = ast.parse(source)
    assigned: dict[str, ast.expr] = {}
    for statement in tree.body:
        if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)):
            assigned[statement.targets[0].id] = statement.value
        names = _import_names(statement, "tests") + _spec_load_targets(statement, assigned)
        if any(name.startswith(("research", "test_insider_buying", "tests.test_insider_buying")) for name in names):
            assert statement.end_lineno is not None
            return "\n".join(source.splitlines()[:statement.end_lineno]) + "\n"
    raise AssertionError(f"{path.name}: guarded test must contain a protected lane load")


def _probe(source: str, filename: str, *, missing_fcntl: bool) -> dict[str, str]:
    environment = {
        name: os.environ[name]
        for name in ("PATH", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PROGRAMDATA")
        if name in os.environ
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    path = ROOT / "tests" / filename
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", _CHILD],
        input=json.dumps({
            "root": str(ROOT), "prefix": _collection_prefix(source, path),
            "filename": str(path), "missing_fcntl": missing_fcntl,
            "site_packages": [entry for entry in sys.path if "site-packages" in entry],
        }),
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(("commit", "filename"), PROBES)
def test_missing_fcntl_skips_before_any_custody_import_and_detects_prior_collection_error(commit, filename):
    path = ROOT / "tests" / filename
    prior = subprocess.run(
        ["git", "show", f"{commit}:tests/{filename}"],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=20,
    ).stdout
    red = _probe(prior, filename, missing_fcntl=True)
    assert red["outcome"] == "collection-error"
    assert "research import reached" in red["reason"] or "unsupported host: fcntl" in red["reason"]
    green = _probe(path.read_text(encoding="utf-8"), filename, missing_fcntl=True)
    assert green["outcome"] == "skipped"
    assert "IBWIN-CR01" in green["reason"]
    assert "Windows custody port deferred" in green["reason"]


@pytest.mark.parametrize(("commit", "filename"), PROBES)
def test_available_fcntl_does_not_skip_supported_host_collection(commit, filename):
    pytest.importorskip("fcntl", reason="IBWIN-CR01: this control needs actual POSIX fcntl")
    source = (ROOT / "tests" / filename).read_text(encoding="utf-8")
    result = _probe(source, filename, missing_fcntl=False)
    assert result["outcome"] == "collection-error"
    assert result["reason"].startswith("research import reached:")


def test_every_lane_test_reaching_fcntl_guards_before_its_first_posix_load():
    # Section 350: the rule, not a list. Any new lane test that loads a module
    # whose import closure includes fcntl (directly, through research modules,
    # or through a sibling test) must guard at module level before that load.
    unguarded, guarded, frozen = [], [], []
    for path in sorted((ROOT / "tests").glob("test_insider_buying*.py")):
        before, statement = _first_posix_load(path)
        if statement is None:
            continue
        if not before and path.name in FROZEN_FILES_350:
            relative = path.relative_to(ROOT).as_posix()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == platform_policy.FROZEN_POSIX_TEST_SHA256[relative]
            frozen.append(path.name)
        else:
            (guarded if before else unguarded).append(f"{path.name}:{statement.lineno}")
    assert not unguarded, f"unguarded POSIX-only loads: {unguarded}"
    # Non-vacuous: the rule must see the files it was written for.
    assert set(GUARDED_FILES) | set(GUARDED_FILES_350) <= {entry.split(":")[0] for entry in guarded}
    assert set(frozen) == set(FROZEN_FILES_350)


def test_scan_sees_direct_fcntl_imports_and_sibling_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_insider_buying_invented_sibling.py").write_text(
        "import fcntl\n", encoding="utf-8",
    )
    direct = tmp_path / "test_insider_buying_invented_direct.py"
    direct.write_text("import pytest\nimport fcntl\n", encoding="utf-8")
    before, statement = _first_posix_load(direct)
    assert (before, statement.lineno) == (False, 2)
    guarded = tmp_path / "test_insider_buying_invented_guarded.py"
    guarded.write_text(
        'import pytest\npytest.importorskip("fcntl", reason="IBWIN-CR01")\nimport fcntl\n',
        encoding="utf-8",
    )
    assert _first_posix_load(guarded)[0] is True
    clean = tmp_path / "test_insider_buying_invented_clean.py"
    clean.write_text("import json\n", encoding="utf-8")
    assert _first_posix_load(clean) == (None, None)
    sibling = tmp_path / "tests" / "test_insider_buying_invented_caller.py"
    sibling.write_text("import test_insider_buying_invented_sibling\n", encoding="utf-8")
    assert _first_posix_load(sibling)[0] is False
    sibling.write_text('import pytest\npytest.importorskip("fcntl")\n'
                       'import test_insider_buying_invented_sibling\n', encoding="utf-8")
    assert _first_posix_load(sibling)[0] is True


@pytest.mark.parametrize("guard", [
    'if False:\n    pytest.importorskip("fcntl")',
    'pytest.skip("ineffective", allow_module_level=False)',
])
def test_scan_rejects_ineffective_guard_statements(tmp_path, guard):
    path = tmp_path / "test_insider_buying_invented_ineffective.py"
    path.write_text("import pytest\n" + guard + "\nimport fcntl\n", encoding="utf-8")
    assert _first_posix_load(path)[0] is False


def test_frozen_platform_policy_keeps_native_selection_and_exact_scope(tmp_path):
    platform_policy._validate_frozen_images()
    assert len(platform_policy.FROZEN_POSIX_TEST_SHA256) == 17
    for relative in platform_policy.FROZEN_POSIX_TEST_SHA256:
        path = ROOT / relative
        assert platform_policy._skip_frozen_path(path, missing_fcntl=False) is None
        assert platform_policy._skip_frozen_path(path, missing_fcntl=True) is True
        assert platform_policy._skip_frozen_path(tmp_path / path.name, missing_fcntl=True) is None
    assert platform_policy._skip_frozen_path(ROOT / "tests" / GUARDED_FILES_350[0], missing_fcntl=True) is None
    with pytest.raises(pytest.UsageError, match="exact boolean"):
        platform_policy._skip_frozen_path(ROOT, missing_fcntl=1)


@pytest.mark.parametrize("mutation", ["scope", "digest", "bytes", "symlink"])
def test_frozen_platform_policy_refuses_changed_contract_or_image(tmp_path, mutation):
    pins = dict(platform_policy.FROZEN_POSIX_TEST_SHA256)
    for relative in pins:
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    first = next(iter(pins))
    if mutation == "scope":
        pins["tests/test_insider_buying_invented.py"] = pins.pop(first)
    elif mutation == "digest":
        pins[first] = "not-a-digest"
    elif mutation == "bytes":
        (tmp_path / first).write_bytes((tmp_path / first).read_bytes() + b"\n")
    else:
        original = tmp_path / first
        target = tmp_path / "same-bytes.py"
        target.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(target)
    with pytest.raises(pytest.UsageError):
        platform_policy._validate_frozen_images(tmp_path, pins)


def test_frozen_platform_policy_stops_explicit_file_collection_before_import():
    child = r'''
import importlib.abc, json, os, sys
request=json.load(sys.stdin)
sys.path.insert(0,request["root"])
for entry in request["site_packages"]:
    if entry not in sys.path:sys.path.append(entry)
import pytest
sys.path.insert(0,os.path.join(request["root"],"tests"))
import insider_buying_pytest_platform as policy
sys.modules.pop("fcntl",None)
class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname=="fcntl":raise ModuleNotFoundError("invented unsupported host",name="fcntl")
        if fullname=="research" or fullname.startswith("research."):
            raise AssertionError("frozen custody import reached")
sys.meta_path.insert(0,Finder())
class Reports:
    skipped=0
    failed=0
    def pytest_collectreport(self,report):
        self.skipped+=report.skipped
        self.failed+=report.failed
reports=Reports()
result=pytest.main(["--noconftest","--collect-only","-q","-p","no:cacheprovider",
                    *policy.FROZEN_POSIX_TEST_SHA256],plugins=[policy,reports])
print(json.dumps({"exit":int(result),"skipped":reports.skipped,"failed":reports.failed}))
'''
    environment = {name: os.environ[name] for name in ("PATH", "TMPDIR", "TEMP", "TMP") if name in os.environ}
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run([sys.executable, "-I", "-B", "-c", child], cwd=ROOT,
                            env=environment, capture_output=True, text=True, timeout=30,
                            input=json.dumps({"root": str(ROOT), "site_packages": [
                                entry for entry in sys.path if "site-packages" in entry]}))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {"exit": 5, "skipped": 17, "failed": 0}


def test_frozen_production_pin_maps_still_match_current_test_bytes():
    pytest.importorskip("fcntl", reason="This source-only pin control needs POSIX imports")
    from research import insider_buying_sec_feed_nc_source_binding_observe_v1 as observer
    from research import insider_buying_sec_feed_compact_capture_v1 as compact_capture
    modules = [observer, observer.inherited, observer.binder,
               compact_capture, compact_capture.previous]
    checked = set()
    for module in modules:
        for attribute in ("FROZEN", "CODE_PINS"):
            for relative, digest in getattr(module, attribute, {}).items():
                if relative.startswith("tests/"):
                    assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
                    checked.add(relative)
    assert set(platform_policy.FROZEN_POSIX_TEST_SHA256) <= checked


def test_qc_checkout_controls_remain_available_without_custody_platform_guard():
    path = ROOT / "tests" / "test_insider_buying_qc_source_checkout.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"importorskip", "skip"}
        for node in ast.walk(tree)
    )
