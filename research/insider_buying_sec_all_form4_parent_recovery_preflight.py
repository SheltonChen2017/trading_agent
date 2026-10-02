"""Read-only custody replay and inert continuation accounting for a halted campaign.

This module never dispatches SEC transport or publishes a recovery root. The
old terminal shard remains terminal; its immutable evidence is read in place.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
import fcntl
import os
import re
import stat

from data.hashing import hash_bytes, hash_payload
from research.insider_buying_sec_acquisition import SecPilotError, _plain_path, _refuse_output_overlap
from research.insider_buying_sec_complete_projection_adapter import (
    SecCompletePilotAdapterError, _PinnedRoot,
)
from research.insider_buying_sec_selected_parent_runner import _Events, _MAX_EVENT_BYTES, _MAX_EVENTS
import research.insider_buying_sec_all_form4_parent_campaign as campaign


PRIOR_CAPTURE_GIT_COMMIT = "b64acd1eb3c9de82d8e4f769e9f38bf7f79cb883"
PRIOR_SHARD_REPORT_SHA256S = (
    "a5ac1bd8d4782ac9dfbcdbfb7a5b9fd7dfdb17ad0ec1b9d4b9184d13c4cded65",
    "99d30899a53b64ea509d96d771d59444c5e24798e3df7d95ccb03c57582e11a3",
)
PRIOR_REQUEST_INVENTORY_SHA256 = "20479412fa9d9e931768180eacad84748ef707cc6d9c13323b1eef91120b5fba"
_EXPECTED_TERMINAL = "REFUSED: SEC response is not a valid bounded parent"
_EVENT_NAME = re.compile(r"event-([0-9]{6})-([0-9a-f]{64})\.json\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class PartialCampaignExpectation:
    """Exact immutable anchors and the only allowed two-shard stop shape."""

    capture_git_commit: str
    shard_report_sha256s: tuple[str, str]
    completed_counts: tuple[int, int]
    reused_counts: tuple[int, int]
    total_attempt_count: int

    def validate(self) -> None:
        if (type(self.capture_git_commit) is not str
                or _COMMIT.fullmatch(self.capture_git_commit) is None
                or type(self.shard_report_sha256s) is not tuple
                or len(self.shard_report_sha256s) != 2
                or any(type(value) is not str or _SHA.fullmatch(value) is None
                       for value in self.shard_report_sha256s)
                or type(self.completed_counts) is not tuple
                or len(self.completed_counts) != 2
                or type(self.reused_counts) is not tuple
                or len(self.reused_counts) != 2
                or any(type(value) is not int or value < 0
                       for value in (*self.completed_counts, *self.reused_counts))
                or any(reused > completed for reused, completed in zip(
                    self.reused_counts, self.completed_counts, strict=True,
                ))
                or type(self.total_attempt_count) is not int
                or self.total_attempt_count < 1):
            campaign._refuse("partial campaign expectation is malformed")


@dataclass(frozen=True, slots=True)
class VerifiedPriorCompletedParent:
    request_index: int
    shard_name: str
    source: str
    object_sha256: str
    object_size_bytes: int
    prior_report_sha256: str | None


@dataclass(frozen=True, slots=True)
class VerifiedPartialCampaignReceipt:
    manifest_sha256: str
    request_inventory_sha256: str
    prior_capture_git_commit: str
    prior_campaign_plan_sha256: str
    prior_shard_report_sha256s: tuple[str, str]
    prior_shard_journal_sha256s: tuple[str, str]
    completed_count: int
    prior_selected_reused_count: int
    prior_newly_acquired_count: int
    prior_attempt_count: int
    refused_prior_attempt_count: int
    remaining_selected_reuse_count: int
    remaining_new_request_count: int
    continuation_request_inventory_sha256: str
    completed: tuple[VerifiedPriorCompletedParent, ...] = field(repr=False)
    refused_request: campaign.CampaignRequest = field(repr=False)


@contextmanager
def _hold_read_lock(directory_fd: int) -> Iterator[None]:
    """Exclude a concurrent v1 writer while keeping its lock byte unchanged."""
    descriptor = os.open(
        "run.lock", os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
        dir_fd=directory_fd,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != 0:
            campaign._refuse("prior campaign lock is not empty and single-link")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as exc:
            raise campaign.CampaignError("REFUSED: prior campaign root is in use") from exc
        yield
    finally:
        os.close(descriptor)


def _read_events(pinned: _PinnedRoot, inventory_raw: bytes) -> tuple[list[dict[str, object]], list[bytes]]:
    names = pinned.names()
    numbered: list[tuple[int, str, str]] = []
    for name in names:
        if name.startswith("event-"):
            match = _EVENT_NAME.fullmatch(name)
            if match is None:
                campaign._refuse("prior shard event filename is malformed")
            numbered.append((int(match.group(1)), name, match.group(2)))
    numbered.sort()
    if (len(numbered) > _MAX_EVENTS
            or [number for number, _, _ in numbered]
            != list(range(1, len(numbered) + 1))):
        campaign._refuse("prior shard event sequence changed")
    chain = hash_bytes(inventory_raw)
    parsed: list[dict[str, object]] = []
    raw_events: list[bytes] = []
    for _, name, expected_digest in numbered:
        raw = pinned.read(name, label="prior campaign event", max_bytes=_MAX_EVENT_BYTES)
        if hash_bytes(raw) != expected_digest:
            campaign._refuse("prior shard event digest changed")
        event = campaign._json(raw, label="prior campaign event")
        if event.get("prev_sha256") != chain:
            campaign._refuse("prior shard event chain changed")
        parsed.append(event)
        raw_events.append(raw)
        chain = expected_digest
    return parsed, raw_events


def _replay_shard(
    root: Path, inventory: dict[str, object], inventory_raw: bytes,
    *, index: int, expectation: PartialCampaignExpectation,
) -> tuple[list[VerifiedPriorCompletedParent], int, str]:
    shard = _plain_path(root / inventory["name"], must_exist=True)
    with _PinnedRoot(shard) as pinned:
        if pinned.root_fd is None:
            campaign._refuse("prior shard handle is closed")
        with _hold_read_lock(pinned.root_fd):
            if pinned.read("inventory.json", label="prior shard inventory",
                           max_bytes=campaign.MAX_SHARD_INVENTORY_BYTES) != inventory_raw:
                campaign._refuse("prior shard inventory differs from exact source plan")
            parsed, raw_events = _read_events(pinned, inventory_raw)

            def read_object(digest: str, size: int) -> bytes:
                if (type(digest) is not str or _SHA.fullmatch(digest) is None
                        or type(size) is not int
                        or not 0 < size <= campaign.MAX_COMPLETE_TXT_BYTES):
                    campaign._refuse("prior completed object descriptor is malformed")
                raw = pinned.read(
                    f"objects/{digest}.bin", label="prior completed parent",
                    max_bytes=campaign.MAX_COMPLETE_TXT_BYTES,
                )
                if len(raw) != size or hash_bytes(raw) != digest:
                    campaign._refuse("prior completed parent hash or size changed")
                return raw

            completed, attempts, pending_start, pending_valid, terminal = campaign._state(
                inventory, parsed, shard, object_reader=read_object,
            )
            if (pending_start is not None or pending_valid is not None
                    or len(completed) != expectation.completed_counts[index]
                    or sum(item["source"] == "reused" for item in completed)
                    != expectation.reused_counts[index]):
                campaign._refuse("prior shard completion counts changed")
            if index == 0:
                if terminal is not None or len(completed) != inventory["count"]:
                    campaign._refuse("first prior shard is not complete")
            elif (terminal != _EXPECTED_TERMINAL
                  or len(completed) >= inventory["count"]
                  or not parsed
                  or parsed[-1].get("kind") != "attempt-finish"
                  or parsed[-1].get("outcome") != "source_envelope_refusal"
                  or attempts.get(
                      inventory["requests"][len(completed)]["accession_number"]
                  ) != 1
                  or sum(event.get("outcome") == "source_envelope_refusal"
                         for event in parsed) != 1):
                campaign._refuse("second prior shard lacks its one terminal refusal")
            events = _Events(shard, (0, 0), hash_bytes(inventory_raw))
            events.raw = raw_events
            report = campaign._shard_report(inventory, events, completed, attempts, terminal)
            report_raw = campaign._bytes(report)
            report_sha = hash_bytes(report_raw)
            if report_sha != expectation.shard_report_sha256s[index]:
                campaign._refuse("prior shard report differs from anchored digest")
            report_name = f"shard-report-{report_sha}.json"
            journal = b"".join(raw_events)
            if (pinned.read("attempts.jsonl", label="prior shard journal",
                            max_bytes=campaign.MAX_SHARD_JOURNAL_BYTES) != journal
                    or pinned.read(report_name, label="prior shard report",
                                   max_bytes=campaign.MAX_SHARD_REPORT_BYTES) != report_raw):
                campaign._refuse("prior shard journal or report differs from replay")
            expected_commit = {
                "kind": campaign.CAMPAIGN_VERSION + "/shard-commit",
                "report_name": report_name,
                "report_sha256": report_sha,
                "inventory_sha256": hash_bytes(inventory_raw),
                "attempt_journal_sha256": hash_bytes(journal),
            }
            actual_commit = campaign._json(
                pinned.read("commit.json", label="prior shard commit", max_bytes=4096),
                label="prior shard commit",
            )
            if actual_commit != expected_commit:
                campaign._refuse("prior shard commit differs from replay")
            expected_names, expected_objects = campaign._expected_shard_names(
                events, completed, report_name=report_name, committed=True,
            )
            if (len(expected_objects) != len(completed)
                    or pinned.names() != expected_names
                    or pinned.names(objects=True) != expected_objects):
                campaign._refuse("prior shard has missing or extra immutable members")
            descriptors = [VerifiedPriorCompletedParent(
                request_index=inventory["start"] + ordinal,
                shard_name=inventory["name"], source=event["source"],
                object_sha256=event["object_sha256"],
                object_size_bytes=event["object_size_bytes"],
                prior_report_sha256=event["prior_report_sha256"],
            ) for ordinal, event in enumerate(completed)]
            return descriptors, report["attempt_count"], hash_bytes(journal)


def verify_partial_campaign(
    plan: campaign.CampaignPlan, prior_campaign_root: str | Path,
    *, expected: PartialCampaignExpectation,
) -> VerifiedPartialCampaignReceipt:
    """Replay an exact two-committed-shard v1 stop with no filesystem writes."""
    if type(plan) is not campaign.CampaignPlan or type(expected) is not PartialCampaignExpectation:
        campaign._refuse("partial replay interface is malformed")
    expected.validate()
    try:
        plan_payload = plan.to_payload()
        shards = campaign._shards(plan, expected.capture_git_commit)
        if (len(shards) < 2
                or expected.completed_counts[0] != shards[0][0]["count"]
                or not 0 <= expected.completed_counts[1] < shards[1][0]["count"]):
            campaign._refuse("partial replay shape differs from two-shard stop")
        plan_raw = campaign._campaign_plan(plan, expected.capture_git_commit, shards)
        root = _plain_path(prior_campaign_root, must_exist=True)
        with campaign._ReadOnlyDirectory(root) as top:
            if top.descriptor is None:
                campaign._refuse("prior campaign root handle is closed")
            with _hold_read_lock(top.descriptor):
                if top.names() != {
                    "run.lock", "campaign-plan.json", "shard-0000", "shard-0001",
                }:
                    campaign._refuse("prior campaign root has unexpected members")
                if top.read("campaign-plan.json", max_bytes=campaign.MAX_CAMPAIGN_PLAN_BYTES) != plan_raw:
                    campaign._refuse("prior campaign plan differs from exact source plan")
                all_completed: list[VerifiedPriorCompletedParent] = []
                attempts = 0
                journal_shas: list[str] = []
                for index in (0, 1):
                    inventory, inventory_raw = shards[index]
                    completed, count, journal_sha = _replay_shard(
                        root, inventory, inventory_raw, index=index, expectation=expected,
                    )
                    all_completed.extend(completed)
                    attempts += count
                    journal_shas.append(journal_sha)
                if top.names() != {
                    "run.lock", "campaign-plan.json", "shard-0000", "shard-0001",
                }:
                    campaign._refuse("prior campaign root changed during replay")
        completed_count = len(all_completed)
        if (attempts != expected.total_attempt_count
                or completed_count != sum(expected.completed_counts)
                or [item.request_index for item in all_completed]
                != list(range(completed_count))
                or sum(item.object_size_bytes for item in all_completed)
                > campaign.MAX_RUN_OBJECT_BYTES
                or completed_count >= len(plan.requests)):
            campaign._refuse("prior campaign prefix or attempt total changed")
        selected = {item.accession_number for item in plan.reuses}
        refused_request = plan.requests[completed_count]
        if refused_request.accession_number in selected:
            campaign._refuse("refused parent is also a planned selected reuse")
        remaining = plan.requests[completed_count:]
        dispatch = tuple(item.to_payload() for item in remaining
                         if item.accession_number not in selected)
        remaining_selected = len(remaining) - len(dispatch)
        prior_reused = sum(item.source == "reused" for item in all_completed)
        if (prior_reused + remaining_selected != len(plan.reuses)
                or completed_count + remaining_selected + len(dispatch) != len(plan.requests)
                or not dispatch or dispatch[0] != refused_request.to_payload()):
            campaign._refuse("continuation inventory duplicates or omits a parent")
        return VerifiedPartialCampaignReceipt(
            manifest_sha256=plan.manifest_sha256,
            request_inventory_sha256=plan_payload["request_inventory_sha256"],
            prior_capture_git_commit=expected.capture_git_commit,
            prior_campaign_plan_sha256=hash_bytes(plan_raw),
            prior_shard_report_sha256s=expected.shard_report_sha256s,
            prior_shard_journal_sha256s=(journal_shas[0], journal_shas[1]),
            completed_count=completed_count,
            prior_selected_reused_count=prior_reused,
            prior_newly_acquired_count=completed_count - prior_reused,
            prior_attempt_count=attempts,
            refused_prior_attempt_count=1,
            remaining_selected_reuse_count=remaining_selected,
            remaining_new_request_count=len(dispatch),
            continuation_request_inventory_sha256=hash_payload(dispatch),
            completed=tuple(all_completed), refused_request=refused_request,
        )
    except campaign.CampaignError:
        raise
    except (SecPilotError, SecCompletePilotAdapterError, OSError, KeyError,
            IndexError, TypeError, ValueError) as exc:
        raise campaign.CampaignError("REFUSED: prior partial campaign replay failed") from exc


def load_observed_partial_all_form4_parent_campaign(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    prior_campaign_root: str | Path,
) -> VerifiedPartialCampaignReceipt:
    """Bind the recorded halt to the exact retained two-quarter source bytes."""
    plan = campaign._build_real_plan(
        raw_q4_directory, parsed_q4_directory, raw_q1_directory,
        parsed_q1_directory, exact16_pilot_root, selected_root,
    )
    if plan.to_payload()["request_inventory_sha256"] != PRIOR_REQUEST_INVENTORY_SHA256:
        campaign._refuse("recorded source request inventory changed")
    try:
        prior = _plain_path(prior_campaign_root, must_exist=True)
        for protected in (
            _plain_path(raw_q4_directory, must_exist=True),
            _plain_path(parsed_q4_directory, must_exist=True),
            _plain_path(raw_q1_directory, must_exist=True),
            _plain_path(parsed_q1_directory, must_exist=True),
            _plain_path(exact16_pilot_root, must_exist=True),
            _plain_path(selected_root, must_exist=True),
            Path(__file__).resolve().parents[1],
        ):
            _refuse_output_overlap(prior, protected)
    except (SecPilotError, OSError, ValueError) as exc:
        raise campaign.CampaignError("REFUSED: prior campaign root overlaps a protected source") from exc
    receipt = verify_partial_campaign(
        plan, prior,
        expected=PartialCampaignExpectation(
            capture_git_commit=PRIOR_CAPTURE_GIT_COMMIT,
            shard_report_sha256s=PRIOR_SHARD_REPORT_SHA256S,
            completed_counts=(8_192, 1_347), reused_counts=(972, 226),
            total_attempt_count=8_342,
        ),
    )
    if (receipt.completed_count != 9_539
            or receipt.prior_selected_reused_count != 1_198
            or receipt.prior_newly_acquired_count != 8_341
            or receipt.remaining_selected_reuse_count != 8_139
            or receipt.remaining_new_request_count != 81_716):
        campaign._refuse("recorded partial campaign recovery counts changed")
    return receipt


def preflight_observed_all_form4_parent_recovery(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    prior_campaign_root: str | Path,
) -> dict[str, object]:
    """Return only aggregate, read-only continuation facts; no target identity."""
    receipt = load_observed_partial_all_form4_parent_campaign(
        raw_q4_directory, parsed_q4_directory, raw_q1_directory,
        parsed_q1_directory, exact16_pilot_root, selected_root,
        prior_campaign_root,
    )
    return {
        "kind": "INSETF-SEC-ALL-FORM4-PARENTS-RECOVERY-PREFLIGHT-v1",
        "manifest_sha256": receipt.manifest_sha256,
        "request_inventory_sha256": receipt.request_inventory_sha256,
        "prior_capture_git_commit": receipt.prior_capture_git_commit,
        "prior_campaign_plan_sha256": receipt.prior_campaign_plan_sha256,
        "prior_shard_report_sha256s": receipt.prior_shard_report_sha256s,
        "prior_shard_journal_sha256s": receipt.prior_shard_journal_sha256s,
        "total_parents": receipt.completed_count + receipt.remaining_selected_reuse_count
        + receipt.remaining_new_request_count,
        "prior_completed_count": receipt.completed_count,
        "prior_selected_reused_count": receipt.prior_selected_reused_count,
        "prior_newly_acquired_count": receipt.prior_newly_acquired_count,
        "prior_attempt_count": receipt.prior_attempt_count,
        "refused_prior_attempt_count": receipt.refused_prior_attempt_count,
        "remaining_selected_reuse_count": receipt.remaining_selected_reuse_count,
        "remaining_new_request_count": receipt.remaining_new_request_count,
        "continuation_request_inventory_sha256": receipt.continuation_request_inventory_sha256,
        "targeted_retry_required": True,
        "source_authenticated": False,
        "complete_parent_bytes_acquired": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "research_looks": 0,
        "qc_jobs": 0,
    }


__all__ = [
    "PartialCampaignExpectation", "VerifiedPriorCompletedParent",
    "VerifiedPartialCampaignReceipt", "verify_partial_campaign",
    "load_observed_partial_all_form4_parent_campaign",
    "preflight_observed_all_form4_parent_recovery",
]
