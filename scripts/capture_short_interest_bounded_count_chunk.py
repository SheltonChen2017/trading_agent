"""One newly claimed, finite transport-recovery chunk, never a v1 restart.

The first 512 unresolved descriptors are a bounded implementation milestone.
No loop dispatches later chunks, no spent claim can resume, and a transport
closure is not a class-denominator or full-study qualification. Existing
negative evidence and all prior charges remain independently authenticated.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from itertools import islice
import os
from pathlib import Path
import re
import stat
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_dated_class_reference as references
from scripts import capture_short_interest_count_recovery as old
from scripts import short_interest_lane_batch_guard as lane
from scripts import short_interest_recovery_transport as transport
from scripts import short_interest_refused_count_snapshot as snapshot
from scripts.continue_short_interest_native_identity import _OwnedOutput
from scripts.qualify_finra_short_interest import _prepare_capture_directory, _require_capture_platform
from scripts.qualify_sharadar_companion import _utc_now
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain

DRIVER = "scripts/capture_short_interest_bounded_count_chunk.py"
OUTPUT = old.OUTPUT.parent / "count-bounded-20261024-v2-chunk001"
CLAIM = "count-bounded-20261024-v2-chunk001.spent.json"
FIRST_POSITION = 13_991
DESCRIPTORS = 512
EXTRA_ATTEMPTS = 16
MAXIMUM_ATTEMPTS = DESCRIPTORS + EXTRA_ATTEMPTS
MAXIMUM_TRIES = 3
BACKOFF_SECONDS = (2, 10)
MAXIMUM_SECONDS = 3600
MAXIMUM_INFLIGHT = 8
MAXIMUM_RESPONSE_BYTES = 2 * 1024 ** 2
PRIOR_STARTS = 13_992
PRIOR_HTTP = 13_991
PRIOR_BYTES = 23_452_681
MAXIMUM_CUMULATIVE_BYTES = 4 * 1024 ** 3
# Frozen after the original-byte, read-only manifest measurement, before any
# successor claim/key/HTTP. PENDING is deliberately a hard operational gate.
PREDECESSOR_MANIFEST_SHA256 = "PENDING"
PROTOCOL_SHA256 = "PENDING"


class BoundedRecoveryRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise BoundedRecoveryRefusal("REFUSED: " + code)


def authority():
    return {"source_only": True, "source_admitted": False,
            "denominator_admitted": False, "historical_PIT_admitted": False,
            "ready_for_backtest": False, "outcome_looks": 0,
            "qc_attempts": 0, "trading_authority": False}


def protocol():
    return {"schema": "si-bounded-count-chunk-v2", "driver": DRIVER,
        "predecessor_protocol_sha256": old.PROTOCOL_SHA256,
        "predecessor_manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
        "anchor_plan_sha256": old.original.ANCHOR_PLAN_SHA256,
        "original_positions": [FIRST_POSITION, FIRST_POSITION + DESCRIPTORS - 1],
        "descriptors": DESCRIPTORS, "maximum_new_STARTs": MAXIMUM_ATTEMPTS,
        "maximum_extra_attempts": EXTRA_ATTEMPTS, "maximum_tries_per_descriptor": MAXIMUM_TRIES,
        "maximum_inflight": MAXIMUM_INFLIGHT, "maximum_START_window_seconds": MAXIMUM_SECONDS,
        "deadline": "no_new_START_at_deadline_then_drain;closure_refused_if_elapsed_exceeded",
        "backoff_seconds": list(BACKOFF_SECONDS), "minimum_batch_interval_seconds": 1,
        "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES,
        "maximum_child_charged_bytes": MAXIMUM_ATTEMPTS * MAXIMUM_RESPONSE_BYTES,
        "prior_STARTs": PRIOR_STARTS, "prior_HTTP_invocations": PRIOR_HTTP,
        "prior_charged_bytes": PRIOR_BYTES,
        "maximum_cumulative_STARTs_this_chunk": PRIOR_STARTS + MAXIMUM_ATTEMPTS,
        "historical_cumulative_START_ceiling": old.MAXIMUM_CUMULATIVE_STARTS,
        "maximum_cumulative_bytes": MAXIMUM_CUMULATIVE_BYTES,
        "retry": "only_statusless_allowlisted_transient_transport_GET;each_new_START_receipt_and_full_page_debit",
        "unknown_body_charge": "full_page_even_if_HTTP_invocation_unproven",
        "no_retry": "any_HTTP_status;TLS;permanent_DNS;unknown;local;guard;clock;echo;media;publication;resource",
        "failure": "stop_new_STARTs_drain_at_most_eight_then_dominant_negative",
        "closure": "transport_chunk_only_never_full_source_or_old_refusal_completion",
        "restart_allowed": False, "later_chunks_enabled": False,
        "output": str(OUTPUT), "claim": CLAIM, "authority": authority()}


def registered():
    require(re.fullmatch(r"[0-9a-f]{64}", PREDECESSOR_MANIFEST_SHA256) is not None
        and hash_payload(protocol()) == PROTOCOL_SHA256
        and MAXIMUM_ATTEMPTS == DESCRIPTORS + EXTRA_ATTEMPTS
        and PRIOR_STARTS + MAXIMUM_ATTEMPTS <= old.MAXIMUM_CUMULATIVE_STARTS
        and PRIOR_BYTES + MAXIMUM_ATTEMPTS * MAXIMUM_RESPONSE_BYTES <= MAXIMUM_CUMULATIVE_BYTES,
        "prospective_bounded_protocol_pending_or_changed")


def code_paths():
    return tuple(sorted(set((*old.expected_code_paths(), DRIVER,
        "scripts/short_interest_recovery_transport.py",
        "scripts/short_interest_refused_count_snapshot.py"))))


class _ComposedCodeCustody:
    """Reuse the saved cache's exact base-code FDs; hold only four additions."""
    def __init__(self, root, base, extras):
        require(type(base) is old.cache.HeldFiles and type(extras) is old.cache.HeldFiles,
                "exact_composed_code_custody_required")
        names = code_paths()
        base_names = frozenset(old.cache.COUNT_CODE_FILES)
        extra_names = frozenset(names) - base_names
        require(root == lane.ROOT and base_names < frozenset(names) and extra_names,
                "complete_composed_code_membership_required")
        self._anchor = self._identity = (root, base, extras, base_names, extra_names)
        self.check()

    def check(self):
        require(type(self) is _ComposedCodeCustody and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 5,
                "composed_code_custody_changed")
        unused_root, base, extras, base_names, extra_names = self._anchor
        require(base_names == frozenset(old.cache.COUNT_CODE_FILES)
                and base_names | extra_names == frozenset(code_paths())
                and not base_names & extra_names, "composed_code_membership_changed")
        base.check(); extras.check()

    def read(self, path, maximum):
        self.check()
        root, base, extras, base_names, extra_names = self._anchor
        require(isinstance(path, Path) and path.is_absolute() and path.is_relative_to(root),
                "composed_code_exact_root_path_required")
        name = str(path.relative_to(root))
        require(name in base_names | extra_names, "unregistered_composed_code_path")
        value = (base if name in base_names else extras).read(path, maximum)
        self.check()
        return value


def freeze_queries(source):
    require(type(source) is old.anchors.NativeReportedAnchorPlan
        and source.sha256 == old.original.ANCHOR_PLAN_SHA256, "exact_original_source_required")
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    require(type(selected) is list and len(selected) == old.ORIGINAL_COUNT
        and FIRST_POSITION + DESCRIPTORS - 1 <= len(selected), "frozen_chunk_bounds")
    return references.freeze_native_class_query_plan(source._matrix, mode="explicit_anchors",
        selected_query_ordinals=tuple(selected[FIRST_POSITION - 1:FIRST_POSITION - 1 + DESCRIPTORS]))


def capture_chunk(queries, *, registration, check, refresh, owned, get_secret=read_named_keychain,
                  http=transport.http, clock=_utc_now, sleep=time.sleep, monotonic=time.monotonic,
                  source_final_audit=lambda: None, refusal_check=None):
    with ExitStack() as lifecycle:
        return _capture_chunk(queries, registration=registration, check=check, refresh=refresh,
            owned=owned, get_secret=get_secret, http=http, clock=clock, sleep=sleep,
            monotonic=monotonic, lifecycle=lifecycle, source_final_audit=source_final_audit,
            refusal_check=check if refusal_check is None else refusal_check)


def _capture_chunk(queries, *, registration, check, refresh, owned, get_secret,
                   http, clock, sleep, monotonic, lifecycle, source_final_audit, refusal_check):
    """Private fabricated seams; operational wrapper supplies exact held proofs.

    No retries are hidden in transport. An attempt is debited before its START
    write; a failed/partial write consumes that full page and forbids its HTTP.
    Receipt loss, clocks, and publication errors never erase an earlier debit.
    """
    registered(); _require_capture_platform()
    require(type(queries) is references.NativeClassQueryPlan and callable(check)
        and callable(refresh) and callable(source_final_audit) and callable(refusal_check)
        and type(owned) is _OwnedOutput, "exact_chunk_operational_bindings")
    tickets = tuple(queries.iter_queries())
    require(len(tickets) == DESCRIPTORS and type(registration) is dict
        and set(registration) == {"head", "remote", "code_identity_sha256"}
        and all(re.fullmatch(r"[0-9a-f]{40}", registration[name]) for name in ("head", "remote"))
        and re.fullmatch(r"[0-9a-f]{64}", registration["code_identity_sha256"]), "exact_chunk_registration")
    frozen, started, begin_tick = canonical_json(protocol()), clock(), monotonic()
    old.parallel.clock(started)
    attempts, receipts, charges, chosen, extras = [], [], 0, {}, 0
    published, published_stamps, persisted_receipts = {}, {}, set()
    held_claim, claim_sha = None, None
    previous_start, last_batch = old.parallel.clock(started), begin_tick - 1
    queue = deque((query, 1, None, begin_tick) for query in tickets)
    failure = None

    def local(*, negative=False):
        (refusal_check if negative else check)(); owned.check(); registered()
        require(canonical_json(protocol()) == frozen, "frozen_chunk_policy_changed")
        if held_claim is not None and not negative:
            held_claim.check()

    def publish(name, value, *, negative=False):
        raw = value if type(value) is bytes else canonical_json(value).encode()
        local(negative=negative); owned.publish(name, raw); local(negative=negative)
        published[name] = {"name": name, "bytes": len(raw), "sha256": hash_bytes(raw)}
        published_stamps[name] = old.PrefixSnapshot._file_stamp(
            os.stat(name, dir_fd=owned._anchor[2], follow_symlinks=False))

    def audit_files():
        # At most one member FD, exact membership, original byte hashes and
        # inode stamps. This is a closure proof, not a per-byte Git/dir scan.
        local(); descriptor = owned._anchor[2]
        require(tuple(sorted(os.listdir(descriptor))) == tuple(sorted(published)),
            "chunk_membership_changed_or_negative_sibling")
        for number, (name, pin) in enumerate(sorted(published.items())):
            if number % 64 == 0:
                local()
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            try:
                info = os.fstat(fd)
                stamp = old.PrefixSnapshot._file_stamp(info)
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                    and stamp == published_stamps[name]
                    and info.st_size == pin["bytes"] <= MAXIMUM_RESPONSE_BYTES,
                    "chunk_member_protection_or_size_changed")
                parts, size = [], 0
                while size < info.st_size:
                    part = os.read(fd, min(65536, info.st_size - size))
                    require(bool(part), "chunk_member_short_read")
                    parts.append(part); size += len(part)
                require(stamp == old.PrefixSnapshot._file_stamp(os.fstat(fd))
                    == old.PrefixSnapshot._file_stamp(os.stat(name, dir_fd=descriptor, follow_symlinks=False))
                    and hash_bytes(b"".join(parts)) == pin["sha256"], "chunk_original_member_changed")
            finally:
                os.close(fd)
        # A later file read may race an in-place write to an earlier member.
        # Close that pass with every originally published full inode stamp,
        # not merely the directory namespace or the last file's body hash.
        for name, stamp in published_stamps.items():
            require(old.PrefixSnapshot._file_stamp(os.stat(name, dir_fd=descriptor,
                follow_symlinks=False)) == stamp, "chunk_prior_member_changed_during_audit")
        require(tuple(sorted(os.listdir(descriptor))) == tuple(sorted(published)), "chunk_final_membership_changed")
        local()

    def negative(code):
        # This path must remain available when actual remote evidence has
        # advanced. Local inode/code/branch safety is still mandatory.
        local(negative=True)
        observed = {row["attempt"] for row in receipts}
        missing = tuple(row["attempt"] for row in attempts if row["attempt"] not in observed)
        unpublished = tuple(row["attempt"] for row in attempts if row["attempt"] not in persisted_receipts)
        charged = charges + len(missing) * MAXIMUM_RESPONSE_BYTES
        publish("run.refused.json", {"schema": "si-bounded-count-refused-v2", "code": code,
            "protocol_sha256": PROTOCOL_SHA256, "started_at": started, "refused_at": clock(),
            "START_debits": len(attempts), "known_HTTP_invocations": sum(row["http_invoked"] for row in receipts),
            "HTTP_count_exact": not missing, "unreceipted_attempts": missing,
            "receipt_not_persisted_attempts": unpublished,
            "unpublished_observed_diagnostics": [row for row in receipts if row["attempt"] in unpublished],
            "charged_bytes": charged, "cumulative_STARTs": PRIOR_STARTS + len(attempts),
            "cumulative_charged_bytes": PRIOR_BYTES + charged,
            "resolved_descriptors": len(chosen), "new_claim_sha256": claim_sha,
            "authority": authority()}, negative=True)

    local(); refresh(); old.require_fd_headroom()
    claim = {"schema": "si-bounded-count-spent-claim-v2", "protocol_sha256": PROTOCOL_SHA256,
        "registration": registration, "started_at": started, "query_plan_sha256": queries.sha256,
        "predecessor_manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
        "maximum_attempts": MAXIMUM_ATTEMPTS, "maximum_extra_attempts": EXTRA_ATTEMPTS,
        "prior_STARTs": PRIOR_STARTS, "prior_charged_bytes": PRIOR_BYTES,
        "maximum_cumulative_bytes": MAXIMUM_CUMULATIVE_BYTES, "restart_allowed": False}
    claim_raw = canonical_json(claim).encode()
    claim_sha = hash_bytes(claim_raw)
    owned.publish(CLAIM, claim_raw, parent=True)
    try:
        claim_path = owned._anchor[1] / CLAIM
        held_claim = lifecycle.enter_context(old.cache.HeldFiles((claim_path,), protected=True, boundary=check))
        require(held_claim.read(claim_path, 65536) == claim_raw, "new_claim_original_bytes_changed")
        publish("protocol.private.json", frozen.encode())
        publish("started.json", claim)
        local(); secret = get_secret("massive"); local()
        require(type(secret) is KeychainSecret, "exact_named_existing_key_required")
    except Exception:
        negative("key_or_initial_publication_refused_after_claim")
        return None

    def worker(query, start):
        raw, media, status, invoked = None, None, None, False
        stage = "local_custody"
        diagnostic = {"code": "local_refused", "phase": "local", "failure_class": "local",
                      "http_status": None, "retryable": False, "errno_name": None}
        try:
            local()
            stage = "request_build"
            request = old.original._wire_request(query, secret)
            stage = "opener_build"
            opener = old.original.transport.build_protected_opener()
            stage = "opener_validation"
            old.original.transport._opener(opener)
            local()
            stage = "HTTP_deadline"
            require(monotonic() - begin_tick < MAXIMUM_SECONDS, "HTTP_after_START_window_refused")
            stage = "transport"; invoked = True
            raw, media, status = http(opener, request, MAXIMUM_RESPONSE_BYTES)
            stage = "response_contract"
            require(type(raw) is bytes and len(raw) <= MAXIMUM_RESPONSE_BYTES and type(status) is int
                and status == 200 and old.original._json_media(media), "bounded_JSON_response_required")
            stage = "secret_echo_check"
            require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "response_echo_refused")
            diagnostic, stage = None, None
        except transport.RecoveryTransportFailure as error:
            raw, media, status = None, None, error.http_status
            diagnostic = error.diagnostic()
        except Exception:
            raw, media = None, None
        try:
            at = clock()
            require(old.parallel.clock(start["started_at"]) <= old.parallel.clock(at), "receipt_clock_refused")
        except Exception:
            at, raw, media = None, None, None
            stage = "receipt_clock"
            diagnostic = {"code": "clock_refused", "phase": "local", "failure_class": "local",
                          "http_status": None, "retryable": False, "errno_name": None}
        receipt = {"attempt": start["attempt"], "query_ordinal": start["query_ordinal"],
            "try_number": start["try_number"], "retry_of": start["retry_of"],
            "original_position": start["original_position"], "request_sha256": start["request_sha256"],
            "started_at": start["started_at"], "received_at": at,
            "http_invoked": invoked, "http_status": status, "body_observed": raw is not None,
            "raw_path": None, "raw_sha256": None, "raw_bytes": None,
            "content_type": media if raw is not None else None, "diagnostic": diagnostic,
            "failure_stage": stage,
            "charged_bytes": len(raw) if raw is not None else MAXIMUM_RESPONSE_BYTES}
        return receipt, raw

    with ThreadPoolExecutor(max_workers=MAXIMUM_INFLIGHT) as pool:
        while queue and failure is None:
            ready, pending = [], []
            try:
                local()
                require(monotonic() - begin_tick < MAXIMUM_SECONDS, "chunk_wall_time_exhausted")
                wait = max(0, last_batch + 1 - monotonic(), queue[0][3] - monotonic())
                if wait:
                    sleep(wait)
                local(); refresh(); local()
                require(monotonic() - begin_tick < MAXIMUM_SECONDS, "chunk_wall_time_exhausted")
                last_batch = monotonic()
                while queue and len(ready) < MAXIMUM_INFLIGHT and queue[0][3] <= monotonic():
                    query, number, retry_of, unused = queue.popleft()
                    require(len(attempts) < MAXIMUM_ATTEMPTS, "attempt_budget_exhausted")
                    local(); at = clock(); parsed = old.parallel.clock(at)
                    require(previous_start <= parsed, "START_clock_backdated")
                    previous_start = parsed
                    ticket = query.to_payload()
                    start = {"schema": "si-bounded-count-START-v2", "attempt": len(attempts) + 1,
                        "query_ordinal": ticket["query_ordinal"], "try_number": number, "retry_of": retry_of,
                        "original_position": FIRST_POSITION + ticket["query_ordinal"] - 1,
                        "request": ticket["request"], "request_sha256": ticket["request_sha256"],
                        "query_plan_sha256": queries.sha256, "protocol_sha256": PROTOCOL_SHA256,
                        "started_at": at, "whole_page_bytes_reserved": MAXIMUM_RESPONSE_BYTES}
                    # Debit precedes persistence, submission and HTTP. Any
                    # missing receipt is charged in full by negative().
                    require(monotonic() - begin_tick < MAXIMUM_SECONDS, "START_window_exhausted_before_debit")
                    attempts.append(start)
                    publish(f'attempt-{start["attempt"]:05d}.started.json', start)
                    ready.append((query, start))
                require(ready, "empty_or_unaffordable_batch")
                for query, start in ready:
                    pending.append((query, start, pool.submit(worker, query, start)))
            except Exception:
                failure = "batch_guard_START_or_submission_refused"
            # Always drain every submitted future, even after another worker
            # or local publication fails. No later batch starts after failure.
            for query, start, future in pending:
                try:
                    receipt, raw = future.result()
                except Exception:
                    failure = "worker_result_unusable"
                    continue
                receipts.append(receipt); charges += receipt["charged_bytes"]
                try:
                    name = f'attempt-{start["attempt"]:05d}'
                    if raw is not None:
                        receipt.update(raw_path=name + ".raw", raw_sha256=hash_bytes(raw), raw_bytes=len(raw))
                        publish(receipt["raw_path"], raw)
                    publish(name + ".received.json", receipt)
                    persisted_receipts.add(start["attempt"])
                except Exception:
                    failure = "immutable_attempt_publication_refused"
                    continue
                resolved = receipt["received_at"] is not None and (raw is not None or (
                    receipt["http_invoked"] and receipt["http_status"] == 404))
                if resolved:
                    chosen[start["query_ordinal"]] = start["attempt"]
                else:
                    diagnostic = receipt["diagnostic"]
                    retry = (failure is None and receipt["received_at"] is not None
                        and receipt["http_invoked"] and receipt["http_status"] is None
                        and type(diagnostic) is dict and diagnostic.get("retryable") is True
                        and start["try_number"] < MAXIMUM_TRIES and extras < EXTRA_ATTEMPTS)
                    if retry:
                        extras += 1
                        queue.append((query, start["try_number"] + 1, start["attempt"],
                            monotonic() + BACKOFF_SECONDS[start["try_number"] - 1]))
                    else:
                        failure = "unrecovered_attempt_no_more_STARTs"
            try:
                local(); refresh(); local()
            except Exception:
                failure = "post_batch_remote_or_custody_refused"
    if failure is not None or len(chosen) != DESCRIPTORS or len(receipts) != len(attempts):
        negative(failure or "incomplete_chunk")
        return None
    result = {"schema": "si-bounded-count-transport-inventory-v2", "protocol_sha256": PROTOCOL_SHA256,
        "query_plan_sha256": queries.sha256, "registration": registration,
        "new_claim_sha256": claim_sha,
        "started_at": started, "completed_at": clock(), "START_debits": len(attempts),
        "HTTP_invocations": sum(row["http_invoked"] for row in receipts), "extra_attempts": extras,
        "charged_bytes": charges, "cumulative_STARTs": PRIOR_STARTS + len(attempts),
        "cumulative_charged_bytes": PRIOR_BYTES + charges,
        "resolved_descriptors": len(chosen), "selected_attempts": sorted(chosen.items()),
        "all_attempt_receipts_sha256": hash_payload(receipts),
        "complete_transport_chunk": True, "complete_original_source": False, "authority": authority()}
    try:
        local(); refresh(); local()
        completed = old.parallel.clock(result["completed_at"])
        require(old.parallel.clock(started) <= previous_start <= completed
            and all(row["received_at"] is not None
                and old.parallel.clock(row["started_at"]) <= old.parallel.clock(row["received_at"]) <= completed
                for row in receipts), "closure_clock_refused")
        require(monotonic() - begin_tick <= MAXIMUM_SECONDS, "chunk_closure_deadline_exceeded")
        source_final_audit()
        audit_files()
        manifest = [published[name] for name in sorted(published)]
        result["transport_files_manifest_sha256"] = hash_payload(manifest)
        publish("manifest.private.json", manifest)
        publish("inventory.private.json", result)
        local(); refresh(); source_final_audit(); audit_files()
        publish("chunk.completed.provisional.json", {"inventory_sha256": hash_payload(result), "authority": authority()})
        local(); refresh(); source_final_audit(); audit_files()
        require(monotonic() - begin_tick <= MAXIMUM_SECONDS, "chunk_final_close_deadline_exceeded")
        publish("chunk.closed.json", {"schema": "si-bounded-count-transport-close-v2",
            "inventory_sha256": hash_payload(result), "protocol_sha256": PROTOCOL_SHA256,
            "new_claim_sha256": claim_sha,
            "matching_remote_equal": True, "authority": authority()})
        local(); refresh(); source_final_audit(); audit_files()
        require(monotonic() - begin_tick <= MAXIMUM_SECONDS, "chunk_final_audit_deadline_exceeded")
    except Exception:
        negative("postpublication_chunk_refused")
        return None
    return result


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest):
    """Only fixed registered source and clean committed exact code can dispatch."""
    registered(); _require_capture_platform()
    require(root == lane.ROOT and Path(__file__).absolute() == root / DRIVER,
        "designated_runtime_driver_required")
    guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    guard.refresh()
    names = code_paths()
    require(type(complete_code_manifest) is dict and set(complete_code_manifest) == set(names),
        "complete_exact_code_manifest_required")
    with ExitStack() as stack:
        saved = stack.enter_context(old.cache.load_registered_cache(root, runtime_head=runtime_head,
            actual_remote=actual_remote, for_counts=True))
        saved.code_custody()
        extra_names = tuple(name for name in names if name not in old.cache.COUNT_CODE_FILES)
        current = stack.enter_context(old.cache.HeldFiles(tuple(root / name for name in extra_names),
            protected=False, boundary=guard.check))
        composed = _ComposedCodeCustody(root, saved._anchor[2], current)
        entries, code_sha = old.cache._code_manifest(root, runtime_head, names, composed, guard)
        require({row["path"]: row["sha256"] for row in entries} == complete_code_manifest,
            "registered_code_bytes_changed")
        prior = stack.enter_context(snapshot.load_refused_child(root, saved.plan, guard,
            expected_manifest_sha256=PREDECESSOR_MANIFEST_SHA256))
        require(prior.inventory.to_payload()["attempts_started"] == 13_944
            and prior.inventory.to_payload()["charged_response_bytes"] == 21_293_349
            and prior.inventory.to_payload()["halted"] is True, "refused_predecessor_debits_required")
        queries = freeze_queries(saved.plan)
        target = root / OUTPUT
        require(old.cache._git(root, ["check-ignore", str(target)], guard).strip() == str(target).encode(),
            "fixed_chunk_output_must_be_ignored")
        directory = _prepare_capture_directory(target)
        owned = stack.enter_context(_OwnedOutput(directory, guard.check))
        def check():
            guard.check(); composed.check(); saved.source_custody(); saved.code_custody(); prior.check()
        def refusal_check():
            # A failed old-source audit must still be able to record a new
            # dominant negative, but never bypass lane/code/output custody.
            guard.check(); current.check(); saved.code_custody()
        return capture_chunk(queries, registration={"head": runtime_head, "remote": actual_remote,
            "code_identity_sha256": code_sha}, check=check, refresh=guard.refresh, owned=owned,
            source_final_audit=prior.full_check, refusal_check=refusal_check)
