"""Prospective lane-only guard batching, with no provider or publication API.

Every local snapshot preserves both physical/Git roots, branch, HEAD and all
dirty entries with two Git commands. Remote evidence is single-batch (<=8
exact source tickets), never a timed/permissive cache. This gate supplies no
economic, source-admission, credential, publication or QC authority.
"""
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import sys
import threading

from data.hashing import canonical_json, hash_bytes
from research.short_interest_etf.native_dated_class_reference import NativeDatedClassQuery

from research.short_interest_etf import native_parallel_count_contract as parallel

ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
BRANCH = "codex/strategy-short-interest"
REF = "refs/heads/" + BRANCH
MAXIMUM_BATCH_REQUESTS = 8


class LaneBatchRefusal(ValueError):
    pass


def require(value, reason):
    if not value:
        raise LaneBatchRefusal(reason)


def _run(root, command):
    try:
        result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except Exception:
        raise LaneBatchRefusal("lane_Git_unavailable") from None
    require(result.returncode == 0 and type(result.stdout) is bytes and len(result.stdout) <= 16 * 1024 * 1024,
            "lane_Git_result_refused")
    return result.stdout


def _physical(root):
    require(type(root) is Path or isinstance(root, Path), "exact_physical_root_path")
    require(root == ROOT and root.is_absolute() and root.resolve() == root and Path.cwd().resolve() == root,
            "designated_physical_root_changed")


@dataclass(frozen=True, slots=True, init=False)
class LaneEvidence:
    _json: str = field(repr=False)
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise LaneBatchRefusal("lane_evidence_factory_required")

    def payload(self):
        require(type(self) is LaneEvidence and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 1
                and self._json is self._anchor[0], "lane_evidence_changed")
        return json.loads(self._json)


def _evidence(payload):
    result = object.__new__(LaneEvidence)
    raw = canonical_json(payload)
    anchor = (raw,)
    for name, value in (("_json", raw), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, value)
    return result


class LaneGuard:
    __slots__ = ("_anchor", "_identity")

    def __init__(self, root, *, expected_head, expected_remote, runner=None, physical=None):
        require(root == ROOT and all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value)
                for value in (expected_head, expected_remote)), "fixed_lane_roots_and_hashes_required")
        self._anchor = self._identity = (root, expected_head, expected_remote,
                _run if runner is None else runner, _physical if physical is None else physical,
                "codex/strategy-short-interest", "refs/heads/codex/strategy-short-interest")

    def binding(self):
        require(type(self) is LaneGuard and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 7, "lane_guard_changed")
        return self._anchor

    def check(self):
        root, head, remote, runner, physical, branch, ref = self.binding()
        physical(root)
        try:
            git_root = runner(root, ["git", "rev-parse", "--show-toplevel"])
        finally:
            physical(root)
        require(type(git_root) is bytes and git_root == (str(root) + "\n").encode(), "Git_root_changed")
        physical(root)
        try:
            raw = runner(root, ["git", "status", "--porcelain=v2", "--branch", "--no-ahead-behind", "--untracked-files=all"])
        finally:
            physical(root)
        require(type(raw) is bytes and len(raw) <= 16 * 1024 * 1024 and b"\0" not in raw,
                "porcelain_status_shape")
        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeError:
            raise LaneBatchRefusal("porcelain_status_encoding") from None
        headers = {}
        for line in lines:
            require(line.startswith("# "), "dirty_or_unrecognized_status_entry")
            field, separator, value = line[2:].partition(" ")
            require(separator and field in {"branch.oid", "branch.head", "branch.upstream", "branch.ab"}
                    and field not in headers and value and not any(ord(char) < 32 for char in value),
                    "porcelain_header_changed")
            headers[field] = value
        require(headers.get("branch.oid") == head and headers.get("branch.head") == branch,
                "lane_HEAD_or_branch_changed")
        require("branch.upstream" not in headers or headers["branch.upstream"] == "origin/" + branch,
                "lane_upstream_changed")
        # With --no-ahead-behind Git can still emit the exact uncomputed
        # placeholder. It proves no ancestry or remote equality; refresh()
        # independently reads only the actual matching origin ref.
        require("branch.ab" not in headers or (headers["branch.ab"] == "+? -?"
                and headers.get("branch.upstream") == "origin/" + branch),
                "porcelain_disabled_counts_shape")
        self.binding()
        return _evidence({"schema": "si-two-Git-lane-snapshot-v1", "HEAD": head, "branch": branch,
                "status": "clean", "dirty_entries": 0, "status_bytes_sha256": hash_bytes(raw)})

    def refresh(self):
        before = self.check()
        root, head, remote, runner, physical, branch, ref = self.binding()
        physical(root)
        try:
            observed = runner(root, ["git", "ls-remote", "--exit-code", "origin", ref])
        finally:
            physical(root)
        after = self.check()
        require(type(observed) is bytes and observed == (remote + "\t" + ref + "\n").encode(),
                "matching_actual_remote_advanced_or_ambiguous")
        require(before.payload()["HEAD"] == after.payload()["HEAD"], "lane_changed_during_remote_read")
        return _evidence({"schema": "si-bounded-batch-lane-evidence-v1", "HEAD": head, "branch": branch,
                "actual_remote": remote, "actual_ref": ref, "status": "clean", "maximum_HTTP_slots": 8})


class BoundedBatchGate:
    """Drain-only after advancement; no HTTP or source writer is implemented."""
    __slots__ = ("_anchor", "_identity", "_state", "_lock")

    def __init__(self, guard, plan):
        require(type(guard) is LaneGuard and type(plan) is parallel.ParallelCountPlan, "exact_lane_and_parallel_plan_required")
        guard.binding()
        plan.guard()
        state = {"halted": False, "next": 1, "active": None, "publication": None, "started": set(), "drained": set()}
        lock = threading.RLock()
        self._anchor = self._identity = (guard, plan, plan.sha256, state, lock)
        self._state, self._lock = state, lock

    def check(self):
        require(type(self) is BoundedBatchGate and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 5
                and self._state is self._anchor[3] and self._lock is self._anchor[4], "bounded_batch_gate_changed")
        self._anchor[0].binding()
        self._anchor[1].guard()
        require(self._anchor[1].sha256 == self._anchor[2], "bound_parallel_plan_changed")
        require(type(self._state.get("halted")) is bool and type(self._state.get("next")) is int
                and self._state["next"] >= 1 and type(self._state.get("started")) is set
                and type(self._state.get("drained")) is set
                and self._state["drained"] <= self._state["started"], "bounded_batch_state_changed")

    def refresh_boundary(self):
        self.check()
        require(self._state["halted"] is False, "halted_batch_cannot_restart")
        try:
            return self._anchor[0].refresh()
        except LaneBatchRefusal:
            self._state["halted"] = True
            raise

    def open_HTTP_batch(self, tickets):
        with self._lock:
            self.check()
            require(type(tickets) is tuple and 1 <= len(tickets) <= 8
                    and self._state["active"] is None, "finite_one_active_HTTP_batch_required")
            ordinals = []
            for ticket in tickets:
                require(type(ticket) is NativeDatedClassQuery and ticket._plan is self._anchor[1]._queries,
                        "exact_bound_source_ticket_required")
                ordinals.append(ticket.to_payload()["query_ordinal"])
            require(ordinals == list(range(self._state["next"], self._state["next"] + len(tickets))),
                    "next_exact_query_prefix_required")
            evidence = self.refresh_boundary()
            self._state["active"] = (tickets, tuple(ordinals), evidence)
            return evidence

    def authorize_start(self, ticket):
        with self._lock:
            self.check()
            require(self._state["halted"] is False and self._state["active"] is not None,
                    "batch_not_open_or_halted")
            tickets, ordinals, evidence = self._state["active"]
            require(any(ticket is known for known in tickets), "one_of_eight_exact_ticket_instances_required")
            ordinal = ticket.to_payload()["query_ordinal"]
            require(ordinal not in self._state["started"] and evidence.payload()["HEAD"] == self._anchor[0].binding()[1],
                    "one_shot_bounded_HTTP_slot_required")
            try:
                self._anchor[0].check()
            except LaneBatchRefusal:
                self._state["halted"] = True
                raise
            self._state["started"].add(ordinal)
            return evidence

    def drain(self, ticket):
        with self._lock:
            self.check()
            require(self._state["active"] is not None and any(ticket is known for known in self._state["active"][0]),
                    "only_active_started_ticket_can_drain")
            ordinal = ticket.to_payload()["query_ordinal"]
            require(ordinal in self._state["started"] and ordinal not in self._state["drained"], "one_started_slot_one_drain")
            self._state["drained"].add(ordinal)

    def close_HTTP_batch(self):
        with self._lock:
            self.check()
            require(self._state["active"] is not None, "open_HTTP_batch_required")
            ordinals = self._state["active"][1]
            if self._state["halted"]:
                require(set(ordinals) & self._state["started"] <= self._state["drained"],
                        "halted_batch_must_drain_every_started_slot")
                self._state["active"] = None
                raise LaneBatchRefusal("halted_batch_drained_no_completion")
            require(set(ordinals) <= self._state["drained"], "drain_all_started_slots_before_new_batch")
            self._state["active"] = None
            self._state["next"] = ordinals[-1] + 1
            return self.refresh_boundary()  # Advancement prevents publication/completion or new starts.

    def before_publication_batch(self):
        with self._lock:
            return self.refresh_boundary()

    def open_publication_batch(self, names):
        with self._lock:
            self.check()
            require(type(names) is tuple and 1 <= len(names) <= 24 and len(set(names)) == len(names)
                    and all(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", name)
                        and name not in {".", ".."} for name in names)
                    and self._state["publication"] is None, "finite_one_shot_publication_batch_required")
            if "completed.json" in names:
                evidence = self.completion_evidence()
            else:
                evidence = self.refresh_boundary()
            self._state["publication"] = (names, set(), evidence)
            return evidence

    def authorize_publication(self, name):
        with self._lock:
            self.check()
            require(self._state["halted"] is False and self._state["publication"] is not None,
                    "publication_batch_not_open_or_halted")
            names, consumed, evidence = self._state["publication"]
            require(name in names and name not in consumed, "one_shot_named_publication_only")
            try:
                self._anchor[0].check()
            except LaneBatchRefusal:
                self._state["halted"] = True
                raise
            consumed.add(name)  # Failed exclusive writes never regain a retry slot.
            return evidence

    def close_publication_batch(self):
        with self._lock:
            self.check()
            require(self._state["publication"] is not None, "publication_batch_required")
            names, consumed, evidence = self._state["publication"]
            require(consumed == set(names), "all_named_publication_slots_consumed")
            self._state["publication"] = None
            return self.refresh_boundary()

    def completion_evidence(self):
        with self._lock:
            self.check()
            require(self._state["active"] is None and self._state["next"] - 1
                    == self._anchor[1].to_payload()["maximum_attempts"], "exact_frozen_sequence_not_completed")
            return self.refresh_boundary()
