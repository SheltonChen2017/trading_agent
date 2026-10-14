"""Fabricated Git/ticket evidence, no remote/source/key/provider requests."""
import importlib.util
from pathlib import Path
import sys

import pytest

from scripts import short_interest_lane_batch_guard as m

SPEC = importlib.util.spec_from_file_location("bounded_lane_guard_query_fixtures",
        Path(__file__).with_name("test_short_interest_native_parallel_counts.py"))
fixtures = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fixtures
SPEC.loader.exec_module(fixtures)
HEAD, REMOTE = "a" * 40, "b" * 40


class Git:
    def __init__(self):
        self.commands, self.physical = [], []
        self.root = (str(m.ROOT) + "\n").encode()
        self.status = ("# branch.oid " + HEAD + "\n# branch.head " + m.BRANCH
                + "\n# branch.upstream origin/" + m.BRANCH + "\n").encode()
        self.remote = (REMOTE + "\t" + m.REF + "\n").encode()
    def run(self, root, command):
        self.commands.append(command)
        assert root == m.ROOT
        if command[1] == "rev-parse":
            return self.root
        if command[1] == "status":
            return self.status
        assert command == ["git", "ls-remote", "--exit-code", "origin", m.REF]
        return self.remote
    def path(self, root):
        assert root == m.ROOT
        self.physical.append(root)
    def guard(self):
        return m.LaneGuard(m.ROOT, expected_head=HEAD, expected_remote=REMOTE, runner=self.run, physical=self.path)


def gate(count=10):
    git = Git()
    plan = fixtures.plan(count)
    return git, m.BoundedBatchGate(git.guard(), plan), tuple(plan._queries.iter_queries())


def test_two_process_snapshot_preserves_all_local_lane_facts_and_flags():
    git = Git()
    evidence = git.guard().check().payload()
    assert len(git.commands) == 2 and len(git.physical) == 4
    assert git.commands[1] == ["git", "status", "--porcelain=v2", "--branch", "--no-ahead-behind", "--untracked-files=all"]
    assert evidence["HEAD"] == HEAD and evidence["branch"] == m.BRANCH and evidence["dirty_entries"] == 0


@pytest.mark.parametrize("change", [
    lambda text: text.replace(HEAD, "c" * 40),
    lambda text: text.replace("# branch.head " + m.BRANCH, "# branch.head main"),
    lambda text: text.replace("# branch.head " + m.BRANCH, "# branch.head (detached)"),
    lambda text: text.replace(HEAD, "(initial)"),
    lambda text: text + "# branch.oid " + HEAD + "\n",
    lambda text: text + "# branch.ab +0 -0\n",
    lambda text: text + "# fabricated.clean true\n",
    lambda text: text + "1 .M N... 100644 100644 100644 a b source.py\n",
    lambda text: text + "2 R. N... 100644 100644 100644 a b R100 new.py\told.py\n",
    lambda text: text + "u UU N... a b c d e f g conflict.py\n",
    lambda text: text + "? untracked_source.py\n",
    lambda text: text.replace("origin/" + m.BRANCH, "origin/main"),
    lambda text: text.replace("# branch.head " + m.BRANCH + "\n", ""),
    lambda text: text + "\0",
])
def test_wrong_dirty_unknown_duplicate_or_reflected_headers_refuse(change):
    git = Git()
    git.status = change(git.status.decode()).encode()
    with pytest.raises(m.LaneBatchRefusal):
        git.guard().check()


def test_physical_root_mismatch_precedes_any_Git_or_source_operation():
    git = Git()
    def wrong(root):
        raise m.LaneBatchRefusal("physical_root_changed")
    guard = m.LaneGuard(m.ROOT, expected_head=HEAD, expected_remote=REMOTE, runner=git.run, physical=wrong)
    with pytest.raises(m.LaneBatchRefusal):
        guard.check()
    assert not git.commands


def test_wrong_Git_root_refuses_before_status_snapshot():
    git = Git()
    git.root = b"/another/checkout\n"
    with pytest.raises(m.LaneBatchRefusal):
        git.guard().check()
    assert len(git.commands) == 1


@pytest.mark.parametrize("remote", [b"", b"invalid", (REMOTE + "\trefs/heads/main\n").encode(),
        (("c" * 40) + "\t" + m.REF + "\n").encode(), (REMOTE + "\t" + m.REF + "\n" + REMOTE + "\t" + m.REF + "\n").encode()])
def test_only_matching_actual_origin_ref_exactly_once_is_remote_evidence(remote):
    git = Git()
    git.remote = remote
    with pytest.raises(m.LaneBatchRefusal):
        git.guard().refresh()
    assert all(call[1] != "ls-remote" or call[-1] == m.REF for call in git.commands)


def test_root_or_HEAD_change_during_remote_operation_refuses():
    git = Git()
    original = git.run
    def changed(root, command):
        result = original(root, command)
        if command[1] == "ls-remote":
            git.status = git.status.replace(HEAD.encode(), b"c" * 40)
        return result
    guard = m.LaneGuard(m.ROOT, expected_head=HEAD, expected_remote=REMOTE, runner=changed, physical=git.path)
    with pytest.raises(m.LaneBatchRefusal):
        guard.refresh()


def test_each_finite_HTTP_batch_gets_fresh_remote_evidence_not_per_slot_or_chunk():
    git, value, tickets = gate()
    value.open_HTTP_batch(tickets[:8])
    before = len(git.commands)
    for ticket in tickets[:8]:
        value.authorize_start(ticket)
        value.drain(ticket)
    assert len(git.commands) == before + 16  # Fresh two-Git local check per START; no per-slot remote request.
    value.close_HTTP_batch()
    value.open_HTTP_batch(tickets[8:])
    for ticket in tickets[8:]:
        value.authorize_start(ticket)
        value.drain(ticket)
    value.close_HTTP_batch()
    value.completion_evidence()
    assert len([call for call in git.commands if call[1] == "ls-remote"]) == 5


def test_more_than_eight_stale_duplicate_foreign_or_unopened_slots_never_start():
    git, value, tickets = gate()
    with pytest.raises(m.LaneBatchRefusal):
        value.open_HTTP_batch(tickets[:9])
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_start(tickets[0])
    value.open_HTTP_batch(tickets[:8])
    value.authorize_start(tickets[0])
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_start(tickets[0])
    foreign = next(value._anchor[1]._queries.iter_queries())
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_start(foreign)
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_start(tickets[8])


def test_remote_advance_latches_halt_drains_started_slots_and_cannot_complete_or_restart():
    git, value, tickets = gate()
    value.open_HTTP_batch(tickets[:8])
    value.authorize_start(tickets[0])
    value.authorize_start(tickets[1])
    git.remote = (("c" * 40) + "\t" + m.REF + "\n").encode()
    with pytest.raises(m.LaneBatchRefusal):
        value.before_publication_batch()
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_start(tickets[2])
    value.drain(tickets[0])
    value.drain(tickets[1])
    with pytest.raises(m.LaneBatchRefusal, match="drained_no_completion"):
        value.close_HTTP_batch()
    with pytest.raises(m.LaneBatchRefusal):
        value.open_HTTP_batch(tickets[:8])
    with pytest.raises(m.LaneBatchRefusal):
        value.completion_evidence()


def test_publication_evidence_is_finite_named_one_shot_and_cannot_publish_premature_completion():
    git, value, tickets = gate(count=2)
    with pytest.raises(m.LaneBatchRefusal):
        value.open_publication_batch(("completed.json",))
    value.open_publication_batch(("started.json", "protocol.private.json"))
    before = len(git.commands)
    value.authorize_publication("started.json")
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_publication("started.json")
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_publication("another.raw")
    value.authorize_publication("protocol.private.json")
    assert len(git.commands) == before + 4  # Only the two valid writes receive fresh local checks.
    value.close_publication_batch()


def test_snapshot_gate_or_plan_reflection_cannot_create_permission():
    git, value, tickets = gate(count=2)
    evidence = git.guard().check()
    object.__setattr__(evidence, "_json", "{}")
    with pytest.raises(m.LaneBatchRefusal):
        evidence.payload()
    value._state["halted"] = "false"
    with pytest.raises(m.LaneBatchRefusal):
        value.open_HTTP_batch(tickets)


def test_local_HEAD_change_after_batch_open_refuses_before_next_HTTP_start():
    git, value, tickets = gate(count=2)
    value.open_HTTP_batch(tickets)
    git.status = git.status.replace(HEAD.encode(), b"c" * 40)
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_start(tickets[0])
    assert not value._state["started"]


def test_local_dirty_change_after_publication_batch_open_refuses_before_named_write():
    git, value, tickets = gate(count=2)
    value.open_publication_batch(("started.json",))
    git.status += b"? unexpected.py\n"
    with pytest.raises(m.LaneBatchRefusal):
        value.authorize_publication("started.json")
    assert not value._state["publication"][1]
