"""One fixed daily recovery child; original failed evidence is never altered.

Root first measures/audits the original files, then commits the derived scope
and protocol digests before this entry point can spend the new stable claim.
No provider action occurs on import or during the offline parent audit.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat
import subprocess

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_daily_recovery as recovery
from scripts import capture_short_interest_native_daily_active as producer
from scripts import capture_short_interest_native_daily_operational as operational
from scripts import continue_short_interest_native_identity as custody
from scripts import short_interest_lane_batch_guard as lane
from scripts.qualify_sharadar_companion import _utc_now

daily = recovery.daily
require = recovery.require
ROOT = lane.ROOT
PARENT_DIRECTORY = Path(operational.OUTPUT_DIRECTORY)
DIRECTORY = PARENT_DIRECTORY.parent / "daily-recovery-20261024-v1"
CLAIM_NAME = "daily-recovery-20261024-v1.spent.json"


def required_code_paths():
    return tuple(sorted((*operational.required_code_paths(), str(ROOT / "scripts/capture_short_interest_daily_recovery.py"))))


def protocol(scope):
    require(type(scope) is recovery.DailyRecoveryScope, "audited_scope_required")
    return {"schema": "si-daily-recovery-operational-v1", "recovery_scope_sha256": scope.sha256,
        "scope": scope.payload(), "output": str(DIRECTORY), "claim": CLAIM_NAME,
        "source_directory": str(PARENT_DIRECTORY), "source_head": recovery.SOURCE_HEAD,
        "current_code_paths": list(required_code_paths()), "producer_default_protocol": producer.PROTOCOL_SHA256,
        "capture": "same_qualifier_fresh_whole_selected_day_chains_no_cursor_stitching",
        "limits": "original_debits_plus_child_fit_original_global_and_per_day_ceilings",
        "maximum_concurrency": 8, "maximum_HTTP_starts_per_remote_batch": 8,
        "automatic_retries": 0, "restart_or_resumption_allowed": False,
        "proxies": False, "redirects": False, "parent_claim": "remains_spent_refused",
        "closure": "fresh_postpublication_child_scope_only_then_separate_all1169_replay",
        "source_admitted": False, "ready_for_empirical_backtest": False, "outcome_looks": 0, "qc_attempts": 0}


@contextmanager
def _bundle(head, remote, code_manifest):
    require(type(code_manifest) is dict and tuple(sorted(code_manifest)) == required_code_paths(),
        "complete_daily_recovery_code_manifest_required")
    guard = lane.LaneGuard(ROOT, expected_head=head, expected_remote=remote); guard.refresh()
    for path, digest in sorted(code_manifest.items()):
        guard.check()
        result = subprocess.run(["git", "show", head + ":" + str(Path(path).relative_to(ROOT))],
            cwd=ROOT, capture_output=True, check=False)
        require(result.returncode == 0 and hash_bytes(result.stdout) == digest, "committed_recovery_code_changed")
    registration = operational.RuntimeRegistration(head=head, remote=remote,
        code_manifest={name: code_manifest[name] for name in operational.required_code_paths()})
    bundle = operational.LoadedSourceBundle(guard, registration)
    extra = None
    try:
        path = ROOT / "scripts/capture_short_interest_daily_recovery.py"
        extra = operational.HeldPinnedFile(path, code_manifest[str(path)], 2 * 1024**2,
            private=False, boundary=guard.check)
        def check():
            guard.check(); bundle.check(); extra.check()
        yield guard, bundle, registration, check
    finally:
        if extra is not None: extra.close()
        bundle.close()


def _names(owned):
    owned.check()
    descriptor = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=owned._anchor[2])
    try:
        names = tuple(sorted(os.listdir(descriptor)))
    finally:
        os.close(descriptor)
    require(len(names) == recovery.SOURCE_COUNTS["files"] and all(re.fullmatch(
        r"(?:inventory\.private\.json|round\.closed\.json|day-[0-9]{4}\.(?:started\.json|completed\.json|refused\.json|qualified\.private\.json)|day-[0-9]{4}-page-[0-9]{2}\.(?:started\.json|received\.json|refused\.json|raw))", name)
        for name in names), "exact_original_daily_member_names_required")
    owned.check(); return names


def measure_parent_manifest(*, boundary):
    """Read-only bounded original-byte manifest. Caller freezes returned digest."""
    boundary(); entries = []
    with custody._OwnedOutput(PARENT_DIRECTORY, boundary) as held:
        names = _names(held)
        for number, name in enumerate(names):
            held.check()
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=held._anchor[2])
            try:
                info = os.fstat(descriptor)
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o600 and 0 <= info.st_size <= 256 * 1024**2,
                    "original_private_regular_file_required")
                before = operational.HeldPinnedFile._state(info)
                parts = []; size = 0
                while size < info.st_size:
                    part = os.read(descriptor, min(65536, info.st_size - size))
                    require(bool(part), "original_manifest_short_read")
                    parts.append(part); size += len(part)
                named = os.stat(name, dir_fd=held._anchor[2], follow_symlinks=False)
                require(before == operational.HeldPinnedFile._state(os.fstat(descriptor))
                    == operational.HeldPinnedFile._state(named), "original_manifest_inode_changed")
                entries.append({"name": name, "bytes": size, "sha256": hash_bytes(b"".join(parts))})
            finally:
                os.close(descriptor)
            if number % 64 == 0: boundary()
        require(_names(held) == names, "original_names_changed_during_manifest")
    boundary(); return canonical_json(entries).encode()


@contextmanager
def _original_scope(bundle, manifest_raw, boundary):
    pins = recovery.manifest_index(manifest_raw)
    with custody._OwnedOutput(PARENT_DIRECTORY, boundary) as held:
        require(_names(held) == tuple(pins), "manifest_must_cover_every_original_member")
        def check():
            boundary(); held.check()
        def read(name, maximum):
            require(name in pins, "unregistered_original_name")
            handle = operational.HeldPinnedFile(PARENT_DIRECTORY / name, pins[name][0], maximum, boundary=check)
            try: return handle.bytes()
            finally: handle.close()
        claim = operational.HeldPinnedFile(PARENT_DIRECTORY.parent / operational.GLOBAL_CLAIM_NAME,
            recovery.SOURCE_PINS["claim"], 2 * 1024**2, boundary=check)
        try:
            def historical(head, name):
                check()
                result = subprocess.run(["git", "show", head + ":" + name], cwd=ROOT, capture_output=True, check=False)
                require(result.returncode == 0, "original_historical_code_unavailable")
                return result.stdout
            scope = recovery.audit_refused_parent(bundle.plan, bundle.index, manifest_raw=manifest_raw,
                read=read, claim_raw=claim.bytes(), historical_code=historical, boundary=check)
            yield scope
            check(); require(_names(held) == tuple(pins), "original_names_changed_after_audit")
        finally:
            claim.close()


def audit_registered(*, head, remote, code_manifest, manifest_raw):
    """Offline actual-parent qualification; only counts/ordinals/digests escape."""
    with _bundle(head, remote, code_manifest) as (_, bundle, _, check):
        with _original_scope(bundle, manifest_raw, check) as scope:
            return {"scope": scope.payload(), "scope_sha256": scope.sha256,
                "protocol_sha256": hash_payload(protocol(scope))}


class RecoveryPublisher:
    """Reuse existing per-page gates; distinct child closure never changes parent."""
    def __init__(self, owned, gate, scope, directory, registration, complete_manifest):
        require(type(gate) is operational.DailyHTTPBatchGate and type(scope) is recovery.DailyRecoveryScope,
            "exact_recovery_publisher_bindings")
        scope.check(gate.plan, gate.index)
        self.owned, self.gate, self.scope, self.directory = owned, gate, scope, directory
        self.inner = operational.ScopedPublisher(owned, gate, directory)
        self.registration = registration; self.complete_manifest = dict(complete_manifest)
        self.inventory = None
    def marker(self):
        return {"head": self.registration.binding()[0], "remote": self.registration.binding()[1],
            "code_manifest": self.complete_manifest, "code_manifest_sha256": hash_payload(self.complete_manifest),
            "scope_sha256": self.scope.sha256, "protocol_sha256": hash_payload(protocol(self.scope))}
    def check(self):
        self.scope.check(self.gate.plan, self.gate.index); self.gate.local_check(); self.owned.check()
    def claim(self, value):
        self.check(); a, b, r = self.scope.limits()
        require(value.get("schema") == "si-daily-recovery-spent-whole-round-v1"
            and value.get("recovery_scope_sha256") == self.scope.sha256
            and (value.get("maximum_attempts"), value.get("maximum_total_bytes"), value.get("maximum_total_rows")) == (a, b, r)
            and value.get("restart_or_resumption_allowed") is False
            and (value.get("code_head"), value.get("remote_head")) == self.registration.binding()[:2],
            "exact_new_recovery_claim_required")
        self.owned.publish(CLAIM_NAME, canonical_json(dict(value, recovery_registration=self.marker())).encode(), parent=True)
    def publish(self, directory, name, value, json_value=False):
        self.check(); require(directory == self.directory, "fixed_child_directory")
        match = re.match(r"day-([0-9]{4})(?:-page-([0-9]{2}))?\.", name)
        if match:
            day = int(match[1])
            require(day in self.scope.days(self.gate.plan, self.gate.index)
                and (match[2] is None or 1 <= int(match[2]) <= self.scope.page_limit(day)), "only_registered_recovery_days_pages")
        if name == "inventory.private.json":
            require(type(value) is dict and value.get("schema") == "si-daily-recovery-capture-inventory-v1"
                and value.get("recovery_scope_sha256") == self.scope.sha256
                and value.get("complete_frozen_sequence") is False, "child_inventory_cannot_complete_parent")
            self.owned.publish(name, canonical_json(dict(value, recovery_registration=self.marker())).encode())
            # A qualified in-memory result is not a durable inventory. Never
            # let a failed exclusive write seed a positive final closure.
            self.inventory = canonical_json(value).encode()
        else:
            self.inner.publish(directory, name, value, json_value=json_value)
    def bytes(self, directory, name, value): self.publish(directory, name, value)
    def json(self, directory, name, value): self.publish(directory, name, value, True)
    def finish(self, *, force_refused=False):
        require(type(force_refused) is bool, "exact_forced_refusal_flag")
        self.check(); began = _utc_now(); matching = True
        try: self.gate.guard.refresh()
        except (lane.LaneBatchRefusal, OSError):
            self.gate._halted = True; matching = False
        ended = _utc_now()
        value = {} if self.inventory is None else recovery.parsed(self.inventory)
        selected = set(self.scope.days(self.gate.plan, self.gate.index))
        complete = (not force_refused and matching and not self.gate._halted and not self.gate._slots
            and self.gate._closed_days == set(self.gate._qualified) == selected
            and value.get("complete_recovery_scope") is True and value.get("halted") is False
            and value.get("publication_failed") is False and value.get("days_returned") == len(selected)
            and value.get("http_invocations") == self.gate._invocations)
        closed = {"schema": "si-daily-recovery-authoritative-close-v1", "recovery_registration": self.marker(),
            "audit_started_at": began, "audit_received_at": ended, "matching_remote_equal": matching,
            "pending_slots": len(self.gate._slots), "http_invocations": self.gate._invocations,
            "complete_recovery_scope": complete, "complete_frozen_sequence": False,
            "round_closure_status": "completed_child_scope" if complete else "refused",
            "parent_claim_status": "spent_refused", "source_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_looks": 0, "qc_attempts": 0}
        require(daily._clock(began) <= daily._clock(ended), "fresh_child_closure_clock")
        self.check(); self.owned.publish("round.closed.json", canonical_json(closed).encode())
        after_start = _utc_now()
        try:
            self.gate.guard.refresh()
        except (lane.LaneBatchRefusal, OSError):
            self.gate._halted = True
            negative = dict(closed, complete_recovery_scope=False, round_closure_status="refused",
                matching_remote_equal=False, code="post_publication_remote_refused",
                audit_started_at=after_start, audit_received_at=_utc_now())
            self.check()
            self.owned.publish("round.post-publication-refused.json", canonical_json(negative).encode())
            return negative
        after = {"schema": "si-daily-recovery-post-publication-audit-v1",
            "closure_sha256": hash_payload(closed), "recovery_registration": self.marker(),
            "matching_remote_equal": True, "audit_started_at": after_start, "audit_received_at": _utc_now(),
            "complete_recovery_scope": complete, "complete_frozen_sequence": False}
        self.check(); self.owned.publish("round.post-publication-audit.json", canonical_json(after).encode())
        final_start = _utc_now()
        try:
            self.gate.guard.refresh(); self.check()
        except (lane.LaneBatchRefusal, OSError):
            self.gate._halted = True
            negative = dict(closed, complete_recovery_scope=False, round_closure_status="refused",
                matching_remote_equal=False, code="final_audit_publication_remote_refused",
                audit_started_at=final_start, audit_received_at=_utc_now())
            self.check()
            self.owned.publish("round.post-publication-refused.json", canonical_json(negative).encode())
            return negative
        return closed


def run_registered(*, head, remote, code_manifest, manifest_raw, expected_scope_sha256, expected_protocol_sha256):
    with _bundle(head, remote, code_manifest) as (guard, bundle, registration, check):
        with _original_scope(bundle, manifest_raw, check) as scope:
            require(scope.sha256 == expected_scope_sha256 and hash_payload(protocol(scope)) == expected_protocol_sha256,
                "prospectively_frozen_derived_recovery_scope_required")
            guard.refresh(); DIRECTORY.mkdir(mode=0o700)
            gate = operational.DailyHTTPBatchGate(guard, bundle.plan, check, bundle.index, registration)
            gate.initial()
            with custody._OwnedOutput(DIRECTORY, check) as owned:
                publisher = RecoveryPublisher(owned, gate, scope, DIRECTORY, registration, code_manifest)
                try:
                    producer.capture_with_seams(ROOT, DIRECTORY, bundle.plan, bundle.index,
                        head=head, remote=remote, started_at=_utc_now(), verify_sources=lambda *args: check(),
                        verify_code=lambda *args: check(), claim_budget=publisher.claim,
                        publish=publisher.bytes, publish_json=publisher.json, lane_guard=gate.local_check,
                        transport=gate.transport, on_qualified_day=gate.observe_qualified, recovery_scope=scope)
                except (daily.DailyActiveReferenceError, operational.OperationalRefusal, recovery.DailyRecoveryRefusal,
                        lane.LaneBatchRefusal, OSError):
                    publisher.finish(force_refused=True)
                    raise recovery.DailyRecoveryRefusal("REFUSED: daily_recovery_closed_negative") from None
                closed = publisher.finish()
                require(closed["complete_recovery_scope"] is True, "daily_recovery_closed_negative")
                return closed


@contextmanager
def combined_registered(*, head, remote, code_manifest, parent_manifest_raw, child_manifest_raw,
        child_manifest_sha256, child_claim_sha256, expected_child_registration):
    """Offline source-only whole-chain union, retaining both original claims."""
    with _bundle(head, remote, code_manifest) as (_, bundle, _, check):
        with _original_scope(bundle, parent_manifest_raw, check) as scope:
            require(expected_child_registration.get("protocol_sha256") == hash_payload(protocol(scope)),
                "registered_child_protocol_changed")
            pins = recovery.manifest_index(child_manifest_raw)
            with custody._OwnedOutput(DIRECTORY, check) as owned:
                def boundary():
                    check(); owned.check(); scope.check()
                def names():
                    boundary()
                    fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=owned._anchor[2])
                    try: return tuple(sorted(os.listdir(fd)))
                    finally: os.close(fd)
                require(names() == tuple(pins), "complete_child_directory_manifest_required")
                def read(name, maximum):
                    require(name in pins, "unregistered_child_name")
                    held = operational.HeldPinnedFile(DIRECTORY / name, pins[name][0], maximum, boundary=boundary)
                    try: return held.bytes()
                    finally: held.close()
                def historical(at, name):
                    boundary()
                    result = subprocess.run(["git", "show", at + ":" + name], cwd=ROOT, capture_output=True, check=False)
                    require(result.returncode == 0, "child_historical_code_unavailable")
                    return result.stdout
                claim = operational.HeldPinnedFile(DIRECTORY.parent / CLAIM_NAME, child_claim_sha256,
                    2 * 1024**2, boundary=boundary)
                try:
                    reports = recovery.combined_reports(scope, child_manifest_raw=child_manifest_raw,
                        child_manifest_sha256=child_manifest_sha256, read=read, child_claim_raw=claim.bytes(),
                        expected_registration=expected_child_registration, historical_code=historical, boundary=boundary)
                    exhausted = [0]
                    def stream():
                        for report in reports:
                            exhausted[0] += 1
                            yield report
                    yield bundle.plan, stream()
                    require(exhausted[0] == daily.EXPECTED_SESSIONS and names() == tuple(pins),
                        "all1169_source_reports_must_be_exhausted")
                    boundary()
                finally:
                    claim.close()
