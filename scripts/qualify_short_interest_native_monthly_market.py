"""Offline replay of all retained monthly source panels, never input admission.

No provider, credential, capture, outcome, or publication API is implemented.
The operational context holds exact current code and original protected source
custody. Every original panel is replayed before any result escapes; later
iteration reconstructs only one bounded private normalized panel at a time.
"""
from __future__ import annotations

from contextlib import contextmanager
import dataclasses
import json
from pathlib import Path
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_market_input_protocol as inputs
from research.short_interest_etf import native_monthly_market_qualification as monthly
from scripts import capture_short_interest_native_anchor_cache as custody
from scripts import short_interest_lane_batch_guard as lane
from scripts import short_interest_monthly_market_snapshot as source


DRIVER = "scripts/qualify_short_interest_native_monthly_market.py"
SCHEMA = "si-native-monthly-market-operational-qualification-v1"
SOURCE_PROTOCOL_SHA256 = "b95ecfeefdc8b0bd01a7cb9fd1ea7b250e777356a2db8f7a026810899e7582b1"
EXPECTED_ATTEMPTS = 112
EXPECTED_PANELS = 112
# Main freezes the complete AST-reviewed current-code closure before invoking
# the operational wrapper. Caller-supplied hashes cannot populate this gate.
CURRENT_CODE_FILES = (
    "data/__init__.py",
    "data/exchange_calendar.py",
    "data/financial_primitives.py",
    "data/hashing.py",
    "ml/__init__.py",
    "ml/immutable_io.py",
    "research/__init__.py",
    "research/short_interest_etf/__init__.py",
    "research/short_interest_etf/availability.py",
    "research/short_interest_etf/contracts.py",
    "research/short_interest_etf/finra_source_qualification.py",
    "research/short_interest_etf/massive_action_supplement.py",
    "research/short_interest_etf/massive_class_denominator.py",
    "research/short_interest_etf/native_dated_class_reference.py",
    "research/short_interest_etf/native_dated_identity.py",
    "research/short_interest_etf/native_grouped_market_source.py",
    "research/short_interest_etf/native_listed_venue_namespace.py",
    "research/short_interest_etf/native_market_input_protocol.py",
    "research/short_interest_etf/native_monthly_market_qualification.py",
    "research/short_interest_etf/native_parallel_count_contract.py",
    "research/short_interest_etf/native_population_class_matrix.py",
    "research/short_interest_etf/native_reported_anchor_cache.py",
    "research/short_interest_etf/native_reported_anchor_plan.py",
    "research/short_interest_etf/preregistration.py",
    "research/short_interest_etf/sharadar_actual_input_binding.py",
    "research/short_interest_etf/sharadar_companion_qualification.py",
    "research/short_interest_etf/sharadar_master_segments.py",
    "research/short_interest_etf/sharadar_native_master_index.py",
    "research/short_interest_etf/sharadar_native_observations.py",
    "research/short_interest_etf/sharadar_securities_master.py",
    "scripts/build_short_interest_native_master_offline.py",
    "scripts/capture_short_interest_native_anchor_cache.py",
    "scripts/capture_short_interest_native_grouped_market.py",
    "scripts/capture_short_interest_native_identity.py",
    "scripts/capture_short_interest_native_parallel_counts.py",
    "scripts/capture_short_interest_native_population.py",
    "scripts/capture_short_interest_native_reported_count_round.py",
    "scripts/capture_short_interest_securities_master.py",
    "scripts/continue_short_interest_native_identity.py",
    "scripts/finalize_short_interest_master_offline.py",
    "scripts/load_short_interest_native_class_matrix.py",
    "scripts/load_short_interest_native_identity_continuation.py",
    "scripts/preflight_short_interest_native_reported_anchors.py",
    "scripts/qualify_finra_short_interest.py",
    "scripts/qualify_sharadar_companion.py",
    "scripts/qualify_short_interest_action_supplement.py",
    "scripts/qualify_short_interest_native_monthly_market.py",
    "scripts/read_short_interest_native_identity_continuation.py",
    "scripts/short_interest_keychain.py",
    "scripts/short_interest_lane_batch_guard.py",
    "scripts/short_interest_monthly_market_snapshot.py",
    "scripts/short_interest_reported_anchor_cache.py",
    "scripts/stream_short_interest_native_identity_continuation.py",
    "scripts/verify_short_interest_native_identity_continuation.py",
)
CURRENT_CODE_PATHS_SHA256 = "e3140cf8de961412f519366280909140bc929fc312851529a100e48bd47202b0"
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class MonthlyMarketOperationalRefusal(ValueError):
    """Fixed codes never interpolate source values or external exceptions."""


def require(value, code):
    if not value:
        raise MonthlyMarketOperationalRefusal("REFUSED: " + code)


def authority():
    return monthly.qualification_policy()["authority"]


def policy():
    return {"schema": SCHEMA + "-policy", "source_protocol_sha256": SOURCE_PROTOCOL_SHA256,
        "actual_capture_protocol_sha256": hash_payload(inputs.market_input_protocol()),
        "pure_qualification_policy_sha256": hash_payload(monthly.qualification_policy()),
        "source_manifest_sha256": source.MANIFEST_SHA256, "source_creator": source.SOURCE_HEAD,
        "source_code_identity_sha256": source.CODE_IDENTITY_SHA256,
        "all_original_panels_required_before_first_yield": EXPECTED_PANELS,
        "all_original_attempts_required": EXPECTED_ATTEMPTS,
        "controls_serialization": "original_canonical_JSON_plus_exactly_one_LF",
        "original_refusal_events": "exact_page_events_and_panel_groups_including_all_cross_page_origins",
        "budget": "replay_original_whole_next_8MiB_and_10000_rows_before_every_START",
        "memory": "one_bounded_panel_at_a_time_then_retained_digest_and_chronology_only",
        "consumer": "context_bound_private_only_no_coverage_license_identity_USD_or_input_admission",
        "authority": authority()}


def _same(actual, expected):
    return canonical_json(actual) == canonical_json(expected)


def _clock(value):
    try:
        return source._clock(value)
    except (TypeError, ValueError):
        raise MonthlyMarketOperationalRefusal("REFUSED: original_UTC_clock_required") from None


def _parsed(raw):
    value = source.parsed(raw)
    require((canonical_json(value) + "\n").encode() == raw, "original_canonical_control_required")
    return value


def _read(snap, name, check):
    check(); snap.check()
    raw = snap.read(name, inputs.MAXIMUM_BYTES)
    check(); snap.check()
    require(type(raw) is bytes and len(raw) <= inputs.MAXIMUM_BYTES, "bounded_original_member_required")
    return raw


def _expected_names():
    names = set(source.CONTROL_PINS)
    for attempt in range(1, EXPECTED_ATTEMPTS + 1):
        names.update(f"attempt-{attempt:05d}" + suffix for suffix in
            (".started.json", ".received.json", ".raw", ".refusals.private.json"))
    return tuple(sorted(names))


def _initial_controls(snap, check):
    check(); snap.full_check()
    controls = snap.controls
    require(set(controls) == set(source.CONTROL_PINS), "four_original_global_controls_required")
    source._controls(controls, snap.claim_raw)
    protocol, start, inventory, completed = (_parsed(controls[name]) for name in
        ("protocol.json", "started.json", "inventory.private.json", "completed.json"))
    require(_same(protocol, inputs.market_input_protocol()) and hash_payload(protocol) == SOURCE_PROTOCOL_SHA256,
            "exact_original_protocol_required")
    require(type(protocol["panels"]) is list and len(protocol["panels"]) == EXPECTED_PANELS
        and type(inventory["panels"]) is list and len(inventory["panels"]) == EXPECTED_PANELS
        and snap.names() == _expected_names(), "complete_original_membership_required")
    require(_clock(start["started_at"]) <= _clock(inventory["retrieved_at"]) <= _clock(completed["completed_at"]),
        "original_global_chronology_required")
    pins = tuple((name, hash_bytes(controls[name])) for name in sorted(controls))
    return protocol, start, inventory, completed, pins


def _replay_panel(snap, panel, original, *, state, retrieved_at, check):
    check(); snap.check()
    require(type(original) is dict and set(original) == {
        "table", "month", "pages", "malformed_refusals", "duplicate_groups"}
        and original["table"] == panel["table"] and original["month"] == panel["month"]
        and type(original["pages"]) is list and 1 <= len(original["pages"]) <= inputs.PAGES_PER_PANEL,
        "original_panel_order_or_shape_required")
    table, month = panel["table"], panel["month"]
    attempt, total_bytes, total_rows, previous = state
    groups, malformed, captures, previous_date = {}, [], [], None
    for number, saved_page in enumerate(original["pages"]):
        check(); snap.check()
        require(attempt < inputs.MAXIMUM_REQUESTS and attempt < EXPECTED_ATTEMPTS
            and total_rows + inputs.PAGE_LIMIT <= inputs.MAXIMUM_ROWS
            and total_bytes + inputs.MAXIMUM_BYTES <= inputs.MAXIMUM_RAW_BYTES,
            "original_whole_next_page_budget_required")
        attempt += 1
        prefix = f"attempt-{attempt:05d}"
        request = inputs.page_request(table, month, number)
        digest = hash_payload(request)
        began = _parsed(_read(snap, prefix + ".started.json", check))
        require(type(began) is dict and _same(began, {
            "schema": "si-native-market-request-start-v1", "attempt": attempt,
            "table": table, "month": month, "page": number, "request": request,
            "request_sha256": digest, "code_head": source.SOURCE_HEAD,
            "protocol_sha256": SOURCE_PROTOCOL_SHA256, "started_at": began.get("started_at")}),
            "original_contiguous_START_request_required")
        receipt = _parsed(_read(snap, prefix + ".received.json", check))
        raw = _read(snap, prefix + ".raw", check)
        require(type(receipt) is dict and set(receipt) == {"schema", "attempt", "request_sha256", "http_status",
            "content_type", "raw_path", "raw_sha256", "raw_bytes", "received_at"}
            and type(receipt.get("content_type")) is str and len(receipt["content_type"]) <= 256
            and receipt["content_type"].split(";", 1)[0].strip().lower() == "application/json"
            and _same(receipt, {"schema": "si-native-market-response-v1", "attempt": attempt,
                "request_sha256": digest, "http_status": 200, "content_type": receipt["content_type"],
                "raw_path": prefix + ".raw", "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw),
                "received_at": receipt.get("received_at")}), "original_response_and_raw_binding_required")
        require(_clock(previous) <= _clock(began["started_at"]) <= _clock(receipt["received_at"])
            <= _clock(retrieved_at), "original_serial_request_chronology_required")
        rows = inputs.decode_page(raw)
        observations, previous_date = inputs.inspect_page(rows, table=table, month=month, previous_date=previous_date)
        require(type(saved_page) is dict and _same(saved_page, {
            "attempt": attempt, "request": request, "receipt": receipt, "row_count": len(rows)}),
            "original_panel_page_descriptor_required")
        require(len(rows) == inputs.PAGE_LIMIT if number + 1 < len(original["pages"])
            else len(rows) < inputs.PAGE_LIMIT, "original_full_predecessor_and_short_exhaustion_required")
        issues, duplicate_events = [], {}
        raw_sha = hash_bytes(raw)
        for row_index, slot, reason in observations:
            origin = {"attempt": attempt, "row_index": row_index, "source_file_sha256": raw_sha}
            if reason is not None:
                issue = {"source_origin": origin, "reason": reason}
                issues.append(issue); malformed.append(issue)
            if slot is not None:
                peers = groups.setdefault(slot, [])
                peers.append(origin)
                if len(peers) > 1:
                    event = duplicate_events.setdefault(slot, {"source_key": {
                        "table": table, "ticker": slot[0], "date": slot[1]},
                        "reason": "all_identifiable_duplicate_copies_quarantined",
                        "first_source_origin": peers[0], "new_source_origins": []})
                    event["new_source_origins"].append(origin)
        issues.extend(duplicate_events.values())
        refusal = _parsed(_read(snap, prefix + ".refusals.private.json", check))
        require(_same(refusal, {"schema": "si-native-market-page-refusals-v1", "attempt": attempt,
            "request_sha256": digest, "raw_sha256": raw_sha, "refusals": issues,
            "financial_values_normalized": False, "signal_or_return_computed": False}),
            "original_page_refusal_events_required")
        captures.append(monthly.CapturedMonthlyMarketPage(page_number=number, attempt=attempt,
            request_json=canonical_json(request), request_sha256=digest, raw=raw,
            source_file_sha256=raw_sha, started_at=began["started_at"],
            received_at=receipt["received_at"], http_status=200, content_type=receipt["content_type"]))
        total_bytes += len(raw); total_rows += len(rows); previous = receipt["received_at"]
    duplicates = [{"source_key": {"table": table, "ticker": slot[0], "date": slot[1]},
        "reason": "all_identifiable_duplicate_copies_quarantined", "source_origins": origins}
        for slot, origins in groups.items() if len(origins) > 1]
    require(_same(original["malformed_refusals"], malformed) and _same(original["duplicate_groups"], duplicates),
            "original_panel_malformed_and_duplicate_origins_required")
    qualified = monthly.qualify_monthly_market_panel(table, month, tuple(captures), retrieved_at=retrieved_at)
    check(); snap.check()
    return qualified, (attempt, total_bytes, total_rows, previous)


class _Lease:
    def __init__(self):
        self.active = True


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class MonthlyMarketSourceQualification:
    _snapshot: object = dataclasses.field(repr=False)
    _check: object = dataclasses.field(repr=False)
    _lease: object = dataclasses.field(repr=False)
    _inventory_json: str = dataclasses.field(repr=False)
    _entries: tuple = dataclasses.field(repr=False)
    _json: str = dataclasses.field(repr=False)
    _policy_sha: str = dataclasses.field(repr=False)
    _control_pins: tuple = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise MonthlyMarketOperationalRefusal("REFUSED: complete_monthly_factory_required")

    def _guard(self, *, full=False):
        require(type(self) is MonthlyMarketSourceQualification and self._anchor is self._identity
            and type(self._anchor) is tuple and len(self._anchor) == 8
            and all(getattr(self, name) is item for name, item in zip(("_snapshot", "_check", "_lease",
                "_inventory_json", "_entries", "_json", "_policy_sha", "_control_pins"), self._anchor))
            and type(self._lease) is _Lease and self._lease.active is True, "sealed_monthly_context_changed")
        self._check(); self._snapshot.check()
        require(hash_payload(policy()) == self._policy_sha, "current_monthly_policy_changed")
        controls = self._snapshot.controls
        require(tuple((name, hash_bytes(controls[name])) for name, unused in self._control_pins) == self._control_pins,
            "original_global_controls_changed")
        if full:
            self._snapshot.full_check(); self._check()

    def to_payload(self):
        """PRIVATE provenance/totals/digests only; rows are streamed separately."""
        self._guard()
        return json.loads(self._json)

    def to_bytes(self):
        self._guard()
        return self._json.encode()

    @property
    def sha256(self):
        return hash_bytes(self.to_bytes())

    def public_summary(self):
        self._guard()
        saved = json.loads(self._json)
        return {"schema": SCHEMA, "original_panels_replayed": EXPECTED_PANELS,
            "original_attempts_replayed": EXPECTED_ATTEMPTS,
            "source_protocol_sha256": SOURCE_PROTOCOL_SHA256,
            "runtime_code_identity_sha256": saved["runtime_lineage"]["code_identity_sha256"],
            "authority": authority()}

    def iter_panels(self):
        self._guard(full=True)
        inventory = json.loads(self._inventory_json)
        for panel, original, encoded in zip(inputs.market_input_protocol()["panels"], inventory["panels"], self._entries):
            self._guard()
            entry = json.loads(encoded)
            qualified, state = _replay_panel(self._snapshot, panel, original, state=entry["before"],
                retrieved_at=inventory["retrieved_at"], check=self._check)
            require(qualified.sha256 == entry["qualification_sha256"] and tuple(state) == tuple(entry["after"]),
                    "replayed_panel_identity_changed")
            self._guard(full=True)
            yield qualified
        self._guard(full=True)


@contextmanager
def _qualify_snapshot(snap, *, check, registration):
    """Private fabricated seam; only qualify_registered supplies real custody."""
    require(type(registration) is dict and set(registration) == {"head", "remote", "code_identity_sha256"}
        and all(type(registration[name]) is str and re.fullmatch(r"[0-9a-f]{40}", registration[name])
            for name in ("head", "remote")) and type(registration["code_identity_sha256"]) is str
        and _SHA.fullmatch(registration["code_identity_sha256"]), "exact_current_code_lineage_required")
    frozen_policy = hash_payload(policy())
    protocol, start, inventory, completed, pins = _initial_controls(snap, check)
    state = (0, 0, 0, start["started_at"])
    entries = []
    for panel, original in zip(protocol["panels"], inventory["panels"]):
        require(hash_payload(policy()) == frozen_policy, "monthly_policy_changed_during_full_replay")
        before = state
        qualified, state = _replay_panel(snap, panel, original, state=before,
            retrieved_at=inventory["retrieved_at"], check=check)
        entries.append({"table": panel["table"], "month": panel["month"],
            "before": before, "after": state, "qualification_sha256": qualified.sha256})
        del qualified
    require(len(entries) == EXPECTED_PANELS and state[0] == EXPECTED_ATTEMPTS
        and _same((state[0], state[1], state[2]), (inventory["http_attempts"], inventory["total_raw_bytes"], inventory["total_raw_rows"]))
        and _clock(state[3]) <= _clock(inventory["retrieved_at"]) <= _clock(completed["completed_at"]),
        "all_original_attempts_totals_and_clocks_required")
    check(); snap.full_check()
    require(snap.names() == _expected_names(), "final_original_membership_changed")
    lease = _Lease()
    payload = {"schema": SCHEMA, "source_creator": source.SOURCE_HEAD,
        "source_protocol_sha256": SOURCE_PROTOCOL_SHA256, "source_manifest_sha256": hash_bytes(snap.manifest_raw),
        "source_claim_sha256": hash_bytes(snap.claim_raw), "source_global_controls": dict(pins),
        "original_report_sha256": inventory["report_sha256"], "retrieved_at": inventory["retrieved_at"],
        "original_completed_at": completed["completed_at"], "original_attempts": state[0],
        "original_raw_bytes": state[1], "original_raw_rows": state[2],
        "runtime_lineage": registration, "qualification_policy_sha256": frozen_policy,
        "panels": entries, "authority": authority()}
    value = object.__new__(MonthlyMarketSourceQualification)
    fields = (snap, check, lease, canonical_json(inventory), tuple(canonical_json(entry) for entry in entries),
              canonical_json(payload), frozen_policy, pins)
    for name, item in zip(("_snapshot", "_check", "_lease", "_inventory_json", "_entries", "_json",
                           "_policy_sha", "_control_pins"), fields):
        object.__setattr__(value, name, item)
    object.__setattr__(value, "_anchor", fields); object.__setattr__(value, "_identity", fields)
    try:
        value._guard(full=True)
        yield value
    finally:
        try:
            value._guard(full=True)
            require(snap.names() == _expected_names(), "exit_original_membership_changed")
        finally:
            lease.active = False


def code_paths():
    require(type(CURRENT_CODE_FILES) is tuple and 1 <= len(CURRENT_CODE_FILES) <= 256
        and CURRENT_CODE_FILES == tuple(sorted(set(CURRENT_CODE_FILES)))
        and DRIVER in CURRENT_CODE_FILES and hash_payload(list(CURRENT_CODE_FILES)) == CURRENT_CODE_PATHS_SHA256,
        "prospective_complete_current_code_paths_pending")
    return CURRENT_CODE_FILES


@contextmanager
def qualify_registered(root, *, runtime_head, actual_remote, complete_code_manifest):
    names = code_paths()
    require(root == lane.ROOT and Path(__file__).absolute() == root / DRIVER, "designated_monthly_runtime_required")
    require(type(complete_code_manifest) is dict and set(complete_code_manifest) == set(names)
        and all(type(value) is str and _SHA.fullmatch(value) for value in complete_code_manifest.values()),
        "complete_current_code_manifest_required")
    guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    guard.refresh()
    with custody.HeldFiles(tuple(root / name for name in names), protected=False, boundary=guard.check) as held:
        entries, digest = custody._code_manifest(root, runtime_head, names, held, guard)
        require({row["path"]: row["sha256"] for row in entries} == complete_code_manifest,
            "current_committed_code_bytes_changed")
        with source.load_registered_snapshot(root, guard) as snap:
            def check():
                guard.check(); held.check()
            registration = {"head": runtime_head, "remote": actual_remote, "code_identity_sha256": digest}
            with _qualify_snapshot(snap, check=check, registration=registration) as result:
                guard.refresh(); result._guard(full=True)
                try:
                    yield result
                finally:
                    result._guard(full=True); guard.refresh(); check()
