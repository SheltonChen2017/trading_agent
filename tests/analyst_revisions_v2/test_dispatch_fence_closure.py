"""Section 301 (ARV2R301-010): the dispatch-fence closure check is harness-independent."""
import sys
from types import ModuleType

import pytest

from tests.analyst_revisions_v2 import _dispatch_fence_closure as closure


def test_closure_detects_a_transitive_fence_import():
    # risk.execution_gate -> assistant.portfolio_snapshot -> execution.alpaca_broker
    # imports the fence; a closure that missed it would make the lane check vacuous.
    chain = closure.fence_path({"risk.execution_gate"})
    assert chain is not None and chain[0] == "risk.execution_gate"
    assert chain[-1].startswith(closure.FENCE)


def test_lane_modules_exclude_harness_imports_and_the_fence():
    from scripts import capture_arv2_massive_ratings_delta, run_arv2_keychain_connection_check  # noqa: F401
    from research.analyst_revisions_v2_qc import newrule_comparison_submission  # noqa: F401
    lane = closure.lane_modules()
    assert {"scripts.capture_arv2_massive_ratings_delta",
            "research.analyst_revisions_v2_qc.newrule_comparison_submission"} <= lane
    # Modules the shared conftest loads (assistant.*, risk.*) are never lane roots.
    assert not any(name.startswith(("assistant.", "risk.", "execution.")) for name in lane)
    closure.assert_lane_closure_excludes_dispatch_fence()


@pytest.fixture
def graph(tmp_path, monkeypatch):
    """Synthetic sources only: never import the graph or the production fence."""
    clear_cache = getattr(closure._imports, "cache_clear", lambda: None)
    clear_cache()
    monkeypatch.setattr(closure, "ROOT", tmp_path)

    def write(relative, source):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    yield write
    clear_cache()


@pytest.mark.parametrize("statement", [
    "import package.sub.leaf",
    "from package.sub.leaf import value",
    "from package.sub import leaf",
])
def test_closure_includes_implicit_parent_package_initializers(graph, statement):
    graph("entry.py", statement)
    graph("package/__init__.py", "import assistant.dispatch_fence")
    graph("package/sub/__init__.py", "")
    graph("package/sub/leaf.py", "value = 1")
    chain = closure.fence_path({"entry"})
    assert chain is not None and "package" in chain
    assert chain[-1] == closure.FENCE


def test_closure_includes_parent_initializers_of_start_module(graph):
    graph("package/__init__.py", "from assistant import dispatch_fence")
    graph("package/entry.py", "value = 1")
    chain = closure.fence_path({"package.entry"})
    assert chain is not None and chain[0] == "package.entry"
    assert chain[-1] == closure.FENCE


@pytest.mark.parametrize("statement", ["from . import leaf", "from .leaf import value"])
def test_closure_resolves_sibling_relative_imports(graph, statement):
    graph("package/__init__.py", "")
    graph("package/entry.py", statement)
    graph("package/leaf.py", "from assistant import dispatch_fence")
    chain = closure.fence_path({"package.entry"})
    assert chain is not None and "package.leaf" in chain
    assert chain[-1] == closure.FENCE


def test_closure_resolves_parent_relative_imports(graph):
    graph("package/__init__.py", "")
    graph("package/sub/__init__.py", "")
    graph("package/sub/entry.py", "from .. import leaf")
    graph("package/leaf.py", "import assistant.dispatch_fence")
    assert closure.fence_path({"package.sub.entry"})[-1] == closure.FENCE


def test_closure_checks_fence_start_without_reading_its_source(graph):
    assert closure.fence_path({closure.FENCE}) == (closure.FENCE,)


def test_closure_does_not_reuse_stale_source_cache(graph):
    graph("entry.py", "value = 1")
    assert closure.fence_path({"entry"}) is None
    graph("entry.py", "import assistant.dispatch_fence")
    assert closure.fence_path({"entry"}) == ("entry", closure.FENCE)


def test_runtime_fence_remains_forbidden_without_shared_harness(monkeypatch):
    monkeypatch.delitem(sys.modules, "conftest", raising=False)
    monkeypatch.delitem(sys.modules, "tests.conftest", raising=False)
    monkeypatch.setitem(sys.modules, closure.FENCE, ModuleType(closure.FENCE))
    monkeypatch.setattr(closure, "lane_modules", lambda: frozenset())
    with pytest.raises(AssertionError, match="without the shared test harness"):
        closure.assert_lane_closure_excludes_dispatch_fence()


def test_synthetic_shared_harness_can_coexist_with_preloaded_fence(monkeypatch):
    # This simulates only module coexistence, not a real standard pytest run.
    harness = ModuleType("conftest")
    harness.__file__ = str(closure.ROOT / "tests" / "conftest.py")
    monkeypatch.setitem(sys.modules, "conftest", harness)
    monkeypatch.setitem(sys.modules, closure.FENCE, ModuleType(closure.FENCE))
    monkeypatch.setattr(closure, "lane_modules", lambda: frozenset())
    closure.assert_lane_closure_excludes_dispatch_fence()


def test_synthetic_harness_does_not_exempt_lane_static_fence_path(graph, monkeypatch):
    graph("entry.py", "import assistant.dispatch_fence")
    harness = ModuleType("conftest")
    harness.__file__ = str(closure.ROOT / "tests" / "conftest.py")
    monkeypatch.setitem(sys.modules, "conftest", harness)
    monkeypatch.setitem(sys.modules, closure.FENCE, ModuleType(closure.FENCE))
    monkeypatch.setattr(closure, "lane_modules", lambda: frozenset({"entry"}))
    with pytest.raises(AssertionError, match="lane import closure reaches"):
        closure.assert_lane_closure_excludes_dispatch_fence()


def test_unrelated_conftest_does_not_exempt_runtime_fence(monkeypatch):
    harness = ModuleType("conftest")
    harness.__file__ = str(closure.ROOT / "unrelated" / "conftest.py")
    monkeypatch.setitem(sys.modules, "conftest", harness)
    monkeypatch.delitem(sys.modules, "tests.conftest", raising=False)
    monkeypatch.setitem(sys.modules, closure.FENCE, ModuleType(closure.FENCE))
    monkeypatch.setattr(closure, "lane_modules", lambda: frozenset())
    with pytest.raises(AssertionError, match="without the shared test harness"):
        closure.assert_lane_closure_excludes_dispatch_fence()


def test_static_dynamic_import_limitation_is_explicit(graph):
    graph("entry.py", "import importlib\nimportlib.import_module('assistant.dispatch_fence')")
    # Computed/dynamic imports are not proven safe by the static graph. Under
    # --noconftest, the runtime assertion separately rejects a loaded fence.
    assert closure.fence_path({"entry"}) is None
