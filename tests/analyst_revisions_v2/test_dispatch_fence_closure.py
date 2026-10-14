"""Section 301 (ARV2R301-010): the dispatch-fence closure check is harness-independent."""
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
