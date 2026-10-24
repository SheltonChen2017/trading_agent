"""Offline early-quarter locator bootstrap with conservative global exposure.

This observer reads operational controls, not parent financial bodies. Plans
resolve exact request-hash references but are never dispatch evidence. Starts,
pending reservations and global claims remain consumed without a completion.
The master gzip is independently byte-bound and completely decompressed; hash
agreement is not SEC authenticity, original acceptance, PIT or admission.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zlib

from research import insider_buying_earnings_archive_assessment_runner as custody
from research import insider_buying_sec_2006q1_parent_locators as locators


SCHEMA = "insider-2006q1-original-parent-operational-bootstrap-v1"
OUTPUT_PARTS = ("artifacts", "insider_buying", "sec_2006q1_parent_bootstrap")
MASTER_ROOT_PARTS = ("insider-source-20260929.hP4utF", "masters-v3")
MASTER_COMMIT_SHA256 = "8b98248bf9c9e2a46340950e596372bb55bde36d1fd0cd435c9c6890369a04ae"
MASTER_REPORT_SHA256 = "9a7aca08f44e392ab13a8c156cfa88f53a5637e65c9e6883a9bf1ae5176fd2e0"
MASTER_GZIP_SHA256 = "55b4abc041b61bd06e1e88b818c0b776b48d146c141ecb676677f7112f63cd04"
MASTER_GZIP_BYTES = 4_209_950
MASTER_DECODED_BYTES = 29_813_237
MASTER_RECEIPT_SHA256 = "d326fbbbd05e243965f84fbcedeba24118b2fede0f6addb9e4ddbe0727ece2e0"
MAX_CONTROL_BYTES = 128 * 1024 * 1024
MAX_CONTROLS = 100_000
MAX_DIRECTORIES = 4096
MAX_MASTER_BYTES = 64 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
MIN_PUBLICATION_FREE_BYTES = 4 * 1024 * 1024 * 1024
MAX_PUBLICATION_BYTES = locators.MAX_OUTPUT_BYTES + locators.MAX_EXPOSURE_BYTES + MAX_SNAPSHOT_BYTES + MAX_CONTROL_BYTES
_EVENT = re.compile(r"event-([0-9]{6})-([0-9a-f]{64})\.json\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_EVENT_KINDS = frozenset({"attempt-start", "attempt-reserved", "attempt-finish", "attempt-response",
    "attempt-abandoned", "attempt-network-error", "attempt-framing-refusal", "attempt-refused",
    "item-complete", "quarter-complete", "quarter-refused", "pilot-finished", "continuation-finished",
    "verified-first-pass-replayed"})
_ID = re.compile(r"[a-z][a-z0-9-]{0,100}\Z")
_ROOT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}\Z")
_MASTER_URL = "https://www.sec.gov/Archives/edgar/full-index/2006/QTR1/master.gz"
_PARENT_URL = re.compile(r"https://www\.sec\.gov/Archives/edgar/data/[0-9]{1,10}/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt\Z")
_XML_PATH = re.compile(r"(?:https://www\.sec\.gov/Archives/|/Archives/|)edgar/data/[0-9]{1,10}/([0-9]{18})/[^/?#]+\Z")
# Only these exact original public-metadata bytes may retain their producer's
#644 mode. Frozen roots are not rewritten; every new output remains600.
LEGACY_PUBLIC_METADATA_SHA256 = {
    ("insider_buying_sec_pilot_2022q4_2023q1_f5430ff", "inventory.json"):
        "c19c98c7cd399d063815408f275ed8af7fc8446f863940cf1d18842d7421bf93",
    ("insider_buying_sec_xml_continue_2022q4_2023q1_5cc897d", "inventory.json"):
        "fa8ed1991991838b6b3f58adeb542d83f6dc6230d51b6ffffd9c02566c514bcd",
}


class ParentBootstrapError(ValueError):
    """Fixed sanitized refusal codes, never private control/body text."""


def _need(value, code):
    if not value:
        raise ParentBootstrapError(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _json(raw, *, newline=True):
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "control_duplicate_json_key")
            result[key] = value
        return result
    try:
        body = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: _need(False, "control_nonfinite_json"))
        _need(type(body) is dict and (raw in (_canonical(body), _canonical(body) + b"\n") if newline else
              raw == _canonical(body)), "canonical_control_required")
        return body
    except (UnicodeError, ValueError, RecursionError, TypeError):
        raise ParentBootstrapError("control_json_refused") from None


def _utc(value):
    _need(type(value) is str and len(value) <= 64, "control_clock_refused")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ParentBootstrapError("control_clock_refused") from None
    _need(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0, "control_clock_refused")
    return stamp


def _accession_url(value):
    _need(type(value) is str, "dispatch_locator_refused")
    match = _PARENT_URL.fullmatch(value)
    if match:
        return match.group(1)
    match = _XML_PATH.fullmatch(value)
    if match:
        raw = match.group(1)
        return raw[:10] + "-" + raw[10:12] + "-" + raw[12:]
    if re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/full-index/[0-9]{4}/QTR[1-4]/master\.gz", value):
        return None
    raise ParentBootstrapError("dispatch_locator_refused")


@dataclass(frozen=True, slots=True)
class RootSpec:
    root_id: str
    path: Path
    profile: str


def actual_roots():
    base = custody.LANE_ROOT.parent
    legacy = base / "insider-source-20260929.hP4utF"
    campaign = base / "insider-source-allparents-20260929.3Nut2i"
    specs = [RootSpec(name, base / name, "simple-jsonl") for name in (
        "insider_buying_sec_pilot_2022q4_2023q1_f5430ff",
        "insider_buying_sec_xml_continue_2022q4_2023q1_5cc897d",
        "insider_buying_sec_complete_16_8f7fca3", "insider_buying_sec_complete_16_1ecb3d4",
        "insider_buying_sec_complete_16_9ab2ed0")]
    specs.extend(RootSpec(name, legacy / name, "event-chain") for name in (
        "masters", "masters-v2", "masters-v3", "selected-parents-v1", "selected-parents-v2"))
    specs.extend(RootSpec(name, campaign / name, "sharded-events") for name in (
        "all-form4-parents", "all-form4-parents-recovery-v3"))
    specs.extend(RootSpec(name, campaign / name, "diagnostic") for name in (
        "refused-parent-diagnostic-v1", "all-form4-parents-v3-ambiguous-diagnostic-v1"))
    specs.append(RootSpec("sec-recovery-v4-global-claims", custody.LANE_ROOT / "artifacts/insider_buying/sec_recovery_v4", "global-claims"))
    return tuple(specs)


class _Tree:
    """Hold no-follow ancestry and shared locks; recheck every read control."""
    def __init__(self, spec):
        _need(type(spec) is RootSpec and type(spec.root_id) is str and _ROOT_ID.fullmatch(spec.root_id)
              and isinstance(spec.path, Path) and spec.path.is_absolute(), "root_spec_refused")
        self.spec, self.directories, self.leaves, self.locks = spec, {}, {}, []
        try:
            self.open(())
        except BaseException:
            self.close(); raise

    def open(self, parts):
        if parts not in self.directories:
            _need(len(self.directories) < MAX_DIRECTORIES and len(parts) <= 8
                  and all(type(name) is str and name not in {"", ".", ".."} and "/" not in name for name in parts),
                  "relative_control_name_or_directory_bound_refused")
            chain = custody._Chain(self.spec.path, parts)
            self.directories[parts] = (chain, ())
            info = os.fstat(chain.fd)
            _need(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid(), "private_directory_owner_required")
            names = tuple(sorted(os.listdir(chain.fd)))
            self.directories[parts] = (chain, names)
            for name in ("run.lock", "capture.lock"):
                if name in names:
                    before = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
                    _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid()
                          and stat.S_IMODE(before.st_mode) == 0o600, "private_lock_refused")
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=chain.fd)
                    self.locks.append((chain, name, fd, custody._version(before)))
                    _need(custody._version(before) == custody._version(os.fstat(fd)), "source_lock_changed")
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return self.directories[parts][0]

    def read(self, parts, name, *, cap=MAX_CONTROL_BYTES, expected=None):
        chain = self.open(parts); chain.recheck()
        before = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
        _need(before.st_uid == os.geteuid(), "private_leaf_owner_required")
        key = "/".join((*parts, name))
        legacy = LEGACY_PUBLIC_METADATA_SHA256.get((self.spec.root_id, key))
        mode = stat.S_IMODE(before.st_mode)
        _need(mode == 0o600 or legacy is not None and mode == 0o644, "private_leaf_mode_required")
        raw = custody._read_leaf(chain.fd, name, limit=cap, private=mode == 0o600)
        after = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
        _need(custody._version(before) == custody._version(after), "source_leaf_changed")
        digest = _sha(raw)
        _need(legacy is None or digest == legacy, "legacy_public_metadata_external_hash_mismatch")
        _need(expected is None or digest == expected, "external_source_hash_mismatch")
        _need(key not in self.leaves or self.leaves[key][2] == digest, "source_leaf_changed")
        self.leaves[key] = (parts, name, digest, custody._version(after), cap)
        return raw

    def names(self, parts=()):
        self.open(parts)
        return self.directories[parts][1]

    def recheck(self):
        for parts, (chain, names) in self.directories.items():
            chain.recheck()
            info = os.fstat(chain.fd)
            _need(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid()
                  and tuple(sorted(os.listdir(chain.fd))) == names, "source_directory_changed")
        for parts, name, digest, version, cap in tuple(self.leaves.values()):
            chain = self.open(parts)
            _need(custody._version(os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) == version
                  and _sha(custody._read_leaf(chain.fd, name, limit=cap,
                    private=stat.S_IMODE(version[2]) == 0o600)) == digest, "source_leaf_changed")
        for chain, name, fd, version in self.locks:
            _need(custody._version(os.fstat(fd)) == version
                  and custody._version(os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) == version, "source_lock_changed")

    def close(self):
        for _, _, fd, _ in self.locks:
            os.close(fd)
        for chain, _ in reversed(tuple(self.directories.values())):
            chain.close()
        self.locks, self.directories = [], {}


def _controls(tree, parts=()):
    """Bodies are intentionally not opened; names still participate in custody."""
    result = {}
    for name in tree.names(parts):
        info = os.stat(name, dir_fd=tree.open(parts).fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            tree.open((*parts, name))
            if name != "objects":
                result.update(_controls(tree, (*parts, name)))
        elif name.endswith((".json", ".jsonl")):
            raw = tree.read(parts, name)
            result["/".join((*parts, name))] = raw
        else:
            _need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                  and stat.S_IMODE(info.st_mode) == 0o600, "unexpected_or_nonprivate_root_leaf")
            if name in {"run.lock", "capture.lock"}:
                result["/".join((*parts, name))] = tree.read(parts, name, cap=1024)
    _need(len(result) <= MAX_CONTROLS, "control_inventory_bound")
    return result


def _request_lookup(controls):
    result = defaultdict(set)
    # Explicit inventory/reservation containers only; no report/source-row scan.
    for name, raw in controls.items():
        if Path(name).name not in {"inventory.json", "campaign-plan.json", "plan.json", "reservation.json"}:
            continue
        body = _json(raw)
        requests = body.get("requests", body.get("rows", []))
        if Path(name).name == "reservation.json":
            selection = body.get("selection", {})
            _need(type(selection) is dict, "reservation_selection_refused")
            requests = selection.get("requests", [])
        _need(type(requests) is list, "plan_request_inventory_refused")
        for item in requests:
            _need(type(item) is dict, "plan_request_inventory_refused")
            request = item.get("request", item)
            _need(type(request) is dict, "plan_request_inventory_refused")
            accession = request.get("accession_number")
            if accession is None:
                continue  # Fixed master plans have no original-parent accession.
            _need(type(accession) is str and _ACCESSION.fullmatch(accession), "plan_accession_refused")
            if "url" in request:
                _need(_accession_url(request["url"]) == accession, "plan_locator_disagreement")
            result[_sha(_canonical(request))].add(accession)
    return result


def _event_chain(controls, parts=""):
    prefix = parts + "/" if parts else ""
    inventory_raw = controls.get(prefix + "inventory.json")
    _need(inventory_raw is not None, "event_inventory_missing")
    tail, events, pieces = _sha(inventory_raw), [], []
    numbered = []
    for name in controls:
        if str(Path(name).parent) != (parts or "."):
            continue
        match = _EVENT.fullmatch(Path(name).name)
        if match:
            numbered.append((int(match.group(1)), match.group(2), name))
        elif Path(name).name.startswith("event-"):
            raise ParentBootstrapError("event_filename_refused")
    numbered.sort()
    _need([item[0] for item in numbered] == list(range(1, len(numbered) + 1)), "event_sequence_refused")
    for _, digest, name in numbered:
        raw = controls[name]; body = _json(raw)
        _need(_sha(raw) == digest and body.get("prev_sha256") == tail, "event_hash_chain_refused")
        tail = digest; pieces.append(raw); events.append((name, body, digest))
    journal = controls.get(prefix + "attempts.jsonl")
    # An unfinished v3 shard may have only its durable individual event files.
    _need(journal is None or journal == b"".join(pieces), "event_journal_disagreement")
    commit_raw = controls.get(prefix + "commit.json")
    if commit_raw is not None:
        commit = _json(commit_raw)
        _need(commit.get("attempt_journal_sha256") == _sha(b"".join(pieces))
              and ("inventory_sha256" not in commit or commit["inventory_sha256"] == _sha(inventory_raw)),
              "event_commit_journal_binding")
        report_name = commit.get("report_name")
        _need(type(report_name) is str and "/" not in report_name and prefix + report_name in controls
              and _sha(controls[prefix + report_name]) == commit.get("report_sha256"), "event_commit_report_binding")
    return events


def _clocks(body):
    clocks = {key: value for key, value in body.items() if key.endswith(("_utc", "_at_utc")) and value is not None}
    for value in clocks.values():
        _utc(value)
    return clocks


def _simple_commit(controls):
    raw = controls.get("commit.json")
    if raw is None:
        return  # Missing completion cannot erase a started/reserved request.
    body = _json(raw)
    name = body.get("report_name", body.get("report"))
    _need(type(name) is str and "/" not in name and name in controls
          and _sha(controls[name]) == body.get("report_sha256"), "simple_commit_report_binding")
    if "attempt_journal_sha256" in body:
        _need(body["attempt_journal_sha256"] == _sha(controls["attempts.jsonl"]), "simple_commit_journal_binding")


def bootstrap_exposures(roots):
    """Hold all genuine roots through final publication; never erase pending."""
    trees, controls_by_root, lookup = [], {}, defaultdict(set)
    try:
        _need(type(roots) is tuple and 1 <= len(roots) <= 32 and len({item.root_id for item in roots}) == len(roots), "exposure_root_inventory")
        for spec in roots:
            tree = _Tree(spec); trees.append(tree)
            controls = _controls(tree); controls_by_root[spec.root_id] = controls
            for digest, accessions in _request_lookup(controls).items():
                lookup[digest].update(accessions)
        exposures, root_reports = defaultdict(set), []
        def add(spec, accession, digest, state):
            _need(type(accession) is str and _ACCESSION.fullmatch(accession), "consumed_accession_refused")
            exposures[accession].add((spec.root_id, digest, state))
        for tree in trees:
            spec, controls = tree.spec, controls_by_root[tree.spec.root_id]
            evidence_events, clocks, starts, reservations, reuses, masters = [], {}, 0, 0, 0, 0
            completed, terminal_records, claim_pending, diagnostic_pending = 0, 0, set(), set()
            for control_name, control_raw in controls.items():
                if control_name.endswith(".json"):
                    observed_clocks = _clocks(_json(control_raw))
                    if observed_clocks:
                        clocks[control_name] = observed_clocks
            if spec.profile == "simple-jsonl":
                raw = controls.get("attempts.jsonl")
                _need(type(raw) is bytes and raw.endswith(b"\n"), "simple_attempt_journal_missing_or_truncated")
                _simple_commit(controls)
                events = [(f"attempts.jsonl:line-{index:06d}", _json(line + b"\n"), _sha(raw))
                          for index, line in enumerate(raw.splitlines(), 1)]
            elif spec.profile == "event-chain":
                events = _event_chain(controls)
            elif spec.profile == "sharded-events":
                shards = sorted(name for name in tree.names() if re.fullmatch(r"shard-[0-9]{4}", name))
                _need(shards, "campaign_shards_missing")
                events = [item for name in shards for item in _event_chain(controls, name)]
            elif spec.profile == "diagnostic":
                manifest_raw, start_raw = controls.get("manifest.json"), controls.get("attempt-start.json")
                _need(manifest_raw is not None, "diagnostic_manifest_missing")
                events = []
                if start_raw is not None:
                    manifest, start = _json(manifest_raw), _json(start_raw)
                    _need(start.get("manifest_sha256") == _sha(manifest_raw), "diagnostic_start_binding")
                    request_sha = manifest.get("refused_request_sha256", manifest.get("ambiguous_request_sha256"))
                    _need(type(request_sha) is str and _SHA.fullmatch(request_sha) and len(lookup[request_sha]) == 1,
                          "diagnostic_exact_request_linkage_missing")
                    accession = next(iter(lookup[request_sha])); add(spec, accession, _sha(start_raw), "started")
                    starts += 1; clocks["attempt-start.json"] = _clocks(start)
                    commit_raw = controls.get("commit.json")
                    if commit_raw is None:
                        diagnostic_pending.add(accession)
                        add(spec, accession, _sha(start_raw), "ambiguous")
                    else:
                        commit = _json(commit_raw); report_name = commit.get("report_name")
                        _need(type(report_name) is str and "/" not in report_name and report_name in controls
                              and commit.get("manifest_sha256") == _sha(manifest_raw)
                              and _sha(controls[report_name]) == commit.get("report_sha256"), "diagnostic_commit_binding")
                        report = _json(controls[report_name])
                        _need(report.get("attempt_start_sha256") == _sha(start_raw)
                              and report.get("manifest_sha256") == _sha(manifest_raw)
                              and _utc(start.get("started_utc")) <= _utc(report.get("finished_utc")),
                              "diagnostic_terminal_binding")
                        terminal_records += 1
            elif spec.profile == "global-claims":
                events = []
                _need({"claims", "runs", "capture.lock"} == set(tree.names()), "global_claim_namespace_refused")
                for name in tree.names(("claims",)):
                    _need(re.fullmatch(r"[0-9a-f]{64}\.json", name), "global_claim_name_refused")
                    raw = controls["claims/" + name]; claim = _json(raw)
                    row = claim.get("request"); _need(type(row) is dict and type(row.get("request")) is dict, "global_claim_request_missing")
                    request = row["request"]; accession = request.get("accession_number")
                    _need(_ACCESSION.fullmatch(accession or "") and name == locators.accession_key(accession) + ".json"
                          and row.get("request_sha256") == _sha(_canonical(request)), "global_claim_accession_binding")
                    capture_id = claim.get("capture_id")
                    _need(type(capture_id) is str and _ID.fullmatch(capture_id), "global_claim_run_refused")
                    reservation_name = "runs/" + capture_id + "/reservation.json"
                    _need(reservation_name in controls and _sha(controls[reservation_name]) == claim.get("reservation_sha256"),
                          "global_claim_reservation_linkage_missing")
                    reservation = _json(controls[reservation_name])
                    _need(reservation.get("selection_sha256") == claim.get("selection_sha256")
                          and row in reservation.get("selection", {}).get("requests", []), "global_claim_selection_binding")
                    add(spec, accession, _sha(raw), "reserved"); reservations += 1
                    clocks[reservation_name] = _clocks(reservation)
                    ordinal = reservation["selection"]["requests"].index(row)
                    prefix = "runs/" + capture_id + f"/request-{ordinal:03d}"
                    start_raw = controls.get(prefix + "-start.json")
                    result_raw = controls.get(prefix + "-result.json")
                    _need(result_raw is None or start_raw is not None, "global_claim_terminal_without_start")
                    if start_raw is None:
                        claim_pending.add(accession)
                    else:
                        start = _json(start_raw)
                        _need(start.get("claim_sha256") == _sha(raw)
                              and start.get("request_sha256") == row["request_sha256"]
                              and start.get("reservation_sha256") == claim["reservation_sha256"]
                              and type(start.get("ordinal")) is int and start["ordinal"] == ordinal,
                              "global_claim_start_binding")
                        add(spec, accession, _sha(start_raw), "started"); starts += 1
                        if result_raw is None:
                            add(spec, accession, _sha(start_raw), "ambiguous"); claim_pending.add(accession)
                        else:
                            result = _json(result_raw)
                            _need(result.get("start_sha256") == _sha(start_raw)
                                  and result.get("request_sha256") == row["request_sha256"]
                                  and type(result.get("ordinal")) is int and result["ordinal"] == ordinal
                                  and _utc(start.get("started_utc")) <= _utc(result.get("finished_utc")),
                                  "global_claim_terminal_binding")
                            terminal_records += 1
            else:
                raise ParentBootstrapError("unknown_exposure_profile")
            pending, active_ordinals, last_clock = {}, {}, None
            for name, event, digest in events:
                kind = event.get("kind")
                _need(type(kind) is str and kind in _EVENT_KINDS, "event_kind_refused")
                current_clocks = _clocks(event)
                if current_clocks:
                    clocks[name] = current_clocks
                    current = min(_utc(value) for value in current_clocks.values())
                    _need(last_clock is None or current >= last_clock, "event_clock_order_refused")
                    last_clock = current
                if kind in {"attempt-start", "attempt-reserved"}:
                    accession = event.get("accession_number")
                    path = event.get("url", event.get("path"))
                    derived = _accession_url(path)
                    _need(accession is None or accession == derived, "consumed_locator_accession_disagreement")
                    ordinal = event.get("ordinal")
                    _need(type(ordinal) is int and ordinal > 0, "attempt_ordinal_refused")
                    key = (str(Path(name).parent), ordinal)
                    _need(key not in active_ordinals, "attempt_overlaps_pending_ordinal")
                    active_ordinals[key] = derived
                    if derived is None:
                        masters += 1; continue
                    state = "reserved" if kind == "attempt-reserved" else "started"
                    add(spec, derived, digest, state); starts += kind == "attempt-start"; reservations += kind == "attempt-reserved"
                    # Retain each genuine historical start independently. An
                    # earlier ordinal's finish cannot erase a later unmatched
                    # start for the same accession. No duplicate is new access
                    # authority and the accession remains globally consumed.
                    pending[(*key, derived)] = (derived, digest)
                    evidence_events.append({"control_name": name, "control_sha256": digest, "accession_number": derived,
                                            "state": state, "clock": current_clocks or None})
                elif kind == "item-complete":
                    _need(event.get("source") in {"reused", "acquired", "new_acquired"}, "item_complete_source_refused")
                    state = "reused" if event.get("source") == "reused" else "completed"
                    add(spec, event.get("accession_number"), digest, state)
                    reuses += state == "reused"; completed += state == "completed"
                elif kind in {"attempt-finish", "attempt-abandoned", "attempt-network-error", "attempt-framing-refusal",
                              "attempt-response", "attempt-refused"}:
                    ordinal = event.get("ordinal")
                    _need(type(ordinal) is int and ordinal > 0, "attempt_ordinal_refused")
                    key = (str(Path(name).parent), ordinal)
                    _need(key in active_ordinals, "terminal_without_reserved_start")
                    derived = active_ordinals.pop(key)
                    _need(event.get("accession_number", derived) == derived, "terminal_locator_accession_disagreement")
                    terminal_records += 1
                    pending.pop((*key, derived), None)
            for accession, digest in pending.values():
                add(spec, accession, digest, "ambiguous")
            root_reports.append({"root_id": spec.root_id, "profile": spec.profile,
                "control_sha256": {name: _sha(raw) for name, raw in sorted(controls.items())},
                "directory_inventories": {"/".join(parts): list(names) for parts, (_, names) in sorted(tree.directories.items())},
                "control_clocks": clocks, "consumed_start_records": starts, "consumed_reservation_records": reservations,
                "reused_records": reuses, "completed_item_records": completed, "terminal_records": terminal_records,
                "master_index_attempts_not_parent_exposure": masters,
                "pending_parent_accessions": sorted({accession for accession, _ in pending.values()} | claim_pending | diagnostic_pending),
                "clock_missing_is_not_backdated": True,
                "legacy_public_metadata_modes": {key: stat.S_IMODE(value[3][2])
                    for key, value in tree.leaves.items() if (spec.root_id, key) in LEGACY_PUBLIC_METADATA_SHA256},
                "exposure_controls": evidence_events, "plan_requests_are_dispatch_evidence": False})
        records = [{"accession_number": accession, "accession_key_sha256": locators.accession_key(accession),
                    "evidence": [{"root_id": root_id, "journal_sha256": digest, "state": state}
                                 for root_id, digest, state in sorted(evidence)]}
                   for accession, evidence in sorted(exposures.items())]
        exposure_raw = _canonical({"schema": locators.EXPOSURE_SCHEMA, "records": records})
        _need(len(exposure_raw) <= locators.MAX_EXPOSURE_BYTES, "exposure_inventory_byte_bound")
        snapshot = {"schema": SCHEMA + "/exposure-snapshot", "roots": root_reports,
                    "exposure_inventory_sha256": _sha(exposure_raw), "global_exposed_accessions": len(records)}
        snapshot_raw = _canonical(snapshot)
        _need(len(snapshot_raw) <= MAX_SNAPSHOT_BYTES, "exposure_snapshot_byte_bound")
        for tree in trees:
            tree.recheck()
        return trees, exposure_raw, snapshot_raw
    except BaseException:
        for tree in reversed(trees):
            tree.close()
        raise


def _decompress_master(raw):
    decoder, result, count = zlib.decompressobj(16 + zlib.MAX_WBITS), [], 0
    try:
        for offset in range(0, len(raw), 64 * 1024):
            chunk = raw[offset:offset + 64 * 1024]
            while chunk:
                decoded = decoder.decompress(chunk, min(1024 * 1024, MAX_MASTER_BYTES + 1 - count))
                result.append(decoded); count += len(decoded)
                _need(count <= MAX_MASTER_BYTES, "master_expansion_bound")
                chunk = decoder.unconsumed_tail
        _need(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail, "master_gzip_truncated_or_trailing")
        return b"".join(result)
    except zlib.error:
        raise ParentBootstrapError("master_gzip_crc_or_format_refused") from None


def _publish(directory, name, raw, cap):
    _need(type(raw) is bytes and 0 < len(raw) <= cap, "output_byte_bound")
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.fsync(directory)
    _need(custody._read_leaf(directory, name, limit=cap) == raw, "output_publication_changed")
    return _sha(raw)


def _private_output(output):
    info = os.fstat(output.fd)
    _need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
          "private_output_owner_required")
    for name in os.listdir(output.fd):
        leaf = os.stat(name, dir_fd=output.fd, follow_symlinks=False)
        _need(stat.S_ISREG(leaf.st_mode) and leaf.st_nlink == 1 and leaf.st_uid == os.geteuid()
              and stat.S_IMODE(leaf.st_mode) == 0o600, "private_output_leaf_required")


def _publication_disk_reserve(output):
    """Finite four-leaf publication budget plus a 4GiB remaining floor."""
    output.recheck(); _private_output(output)
    info = os.fstatvfs(output.fd)
    _need(type(info.f_frsize) is int and info.f_frsize > 0 and
          type(info.f_bavail) is int and info.f_bavail >= 0, "publication_disk_stat_refused")
    available = info.f_frsize * info.f_bavail
    _need(available >= MIN_PUBLICATION_FREE_BYTES + MAX_PUBLICATION_BYTES,
          "publication_disk_reserve_insufficient")
    output.recheck(); _private_output(output)
    return {"maximum_publication_bytes": MAX_PUBLICATION_BYTES,
            "minimum_remaining_free_bytes": MIN_PUBLICATION_FREE_BYTES,
            "available_bytes_at_preflight": available}


def _pre_input_disk_reserve(root, audit_id):
    output = custody._Chain(root, (*OUTPUT_PARTS, audit_id))
    try:
        _need(os.listdir(output.fd) == [], "output_cannot_resume_or_overwrite")
        return _publication_disk_reserve(output)
    finally:
        output.close()


def _verify_disk_receipt(value):
    _need(type(value) is dict and set(value) == {"maximum_publication_bytes", "minimum_remaining_free_bytes",
          "available_bytes_at_preflight"} and all(type(item) is int for item in value.values())
          and value["maximum_publication_bytes"] == MAX_PUBLICATION_BYTES
          and value["minimum_remaining_free_bytes"] == MIN_PUBLICATION_FREE_BYTES
          and value["available_bytes_at_preflight"] >= MIN_PUBLICATION_FREE_BYTES + MAX_PUBLICATION_BYTES,
          "publication_disk_receipt_refused")


def _outside_write_denied(root, audit_id):
    # A new sibling probe, never an existing user or credential file.
    path = root.joinpath(*OUTPUT_PARTS, "isolation-" + audit_id + ".probe")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        _need(exc.errno in {errno.EPERM, errno.EACCES}, "outside_output_write_denial_not_observed")
    else:
        os.close(fd)
        raise ParentBootstrapError("outside_output_write_denial_not_observed")


@dataclass(frozen=True, slots=True)
class FixtureAnchors:
    inventory_sha256: str
    census_complete_sha256: str
    master_commit_sha256: str
    master_report_sha256: str
    master_gzip_sha256: str
    master_decoded_sha256: str
    master_receipt_sha256: str


def _worker(*, root, roots, master_root, audit_id, identity, expected_snapshot_sha256, anchors, fixture_only):
    if fixture_only:
        _fixture_roots_only(root, roots, master_root)
    pre_input_disk = _pre_input_disk_reserve(root, audit_id)
    custody._effective_denial(require_fork=not fixture_only)
    if not fixture_only:
        _outside_write_denied(root, audit_id)
    _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
    trees, exposure_raw, snapshot_raw = bootstrap_exposures(roots)
    census_tree = master_tree = output = None
    try:
        _need(_sha(snapshot_raw) == expected_snapshot_sha256, "external_exposure_snapshot_hash_mismatch")
        census_tree = _Tree(RootSpec("early-census", root.joinpath(*custody.CENSUS_PARTS), "census"))
        _need(set(census_tree.names()) == {"inventory.json", "complete.json"}, "census_leaf_inventory_refused")
        inventory_raw = census_tree.read((), "inventory.json", cap=locators.MAX_INVENTORY_BYTES, expected=anchors.inventory_sha256)
        completion_raw = census_tree.read((), "complete.json", expected=anchors.census_complete_sha256)
        inventory, completion = _json(inventory_raw), _json(completion_raw)
        _need(completion.get("schema") == "insider-2006q1-metadata-observer-completion-v1"
              and completion.get("inventory_sha256") == anchors.inventory_sha256 and completion.get("accounting") == inventory.get("accounting")
              and type(completion.get("inventory_bytes")) is int and completion["inventory_bytes"] == len(inventory_raw)
              and completion.get("fixture_only") is fixture_only, "census_completion_binding")
        master_tree = next((tree for tree in trees if tree.spec.path == master_root), None)
        _need(master_tree is not None, "master_root_not_in_exposure_snapshot")
        commit_raw = master_tree.read((), "commit.json", expected=anchors.master_commit_sha256)
        commit = _json(commit_raw); report_name = commit.get("report_name")
        _need(type(report_name) is str and "/" not in report_name, "master_report_name_refused")
        report_raw = master_tree.read((), report_name, expected=anchors.master_report_sha256)
        _need(commit.get("report_sha256") == anchors.master_report_sha256, "master_report_commit_binding")
        report = _json(report_raw)
        rows = [row for row in report.get("master_indexes", []) if type(row) is dict and row.get("period") == "2006Q1"]
        _need(len(rows) == 1, "master_2006q1_receipt_missing")
        row = rows[0]; descriptor = row.get("raw_object")
        _need(type(descriptor) is dict and descriptor.get("sha256") == anchors.master_gzip_sha256
              and descriptor.get("relative_path") == "objects/" + anchors.master_gzip_sha256 + ".bin"
              and row.get("source_url") == _MASTER_URL, "master_raw_receipt_binding")
        compressed = master_tree.read(("objects",), anchors.master_gzip_sha256 + ".bin", cap=8 * 1024 * 1024,
                                      expected=anchors.master_gzip_sha256)
        _need(type(descriptor.get("size_bytes")) is int and descriptor["size_bytes"] == len(compressed), "master_compressed_size_binding")
        master = _decompress_master(compressed)
        if not fixture_only:
            _need(len(compressed) == MASTER_GZIP_BYTES and len(master) == MASTER_DECODED_BYTES,
                  "actual_master_byte_counts_differ")
        _need(_sha(master) == anchors.master_decoded_sha256, "master_decoded_external_hash_mismatch")
        receipt = row.get("receipt")
        _need(type(receipt) is dict and receipt.get("decoded_sha256") == anchors.master_decoded_sha256
              and type(receipt.get("decoded_size_bytes")) is int and receipt["decoded_size_bytes"] == len(master)
              and receipt.get("master_receipt_sha256") == anchors.master_receipt_sha256, "master_parsed_receipt_binding")
        result = locators.build_2006q1_parent_locators(inventory_raw, master, exposure_raw,
            expected_inventory_sha256=anchors.inventory_sha256, expected_master_sha256=anchors.master_decoded_sha256,
            expected_prior_exposure_sha256=_sha(exposure_raw), maximum_prefix=64)
        body = result.to_payload()
        _need(body["master_receipt_sha256"] == anchors.master_receipt_sha256, "executed_master_receipt_differs")
        for tree in (*trees, census_tree):
            tree.recheck()
        _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
        output = custody._Chain(root, (*OUTPUT_PARTS, audit_id))
        _private_output(output)
        _need(os.listdir(output.fd) == [], "output_cannot_resume_or_overwrite")
        pre_publication_disk = _publication_disk_reserve(output)
        exposure_sha = _publish(output.fd, "exposure.json", exposure_raw, locators.MAX_EXPOSURE_BYTES)
        _publication_disk_reserve(output)
        snapshot_sha = _publish(output.fd, "exposure-snapshot.json", snapshot_raw, MAX_SNAPSHOT_BYTES)
        _publication_disk_reserve(output)
        accounting_raw = result.canonical_bytes()
        locator_sha = _publish(output.fd, "locator-accounting.json", accounting_raw, locators.MAX_OUTPUT_BYTES)
        receipt = {"schema": SCHEMA, "audit_id": audit_id, "fixture_only": fixture_only, "execution_identity": identity,
            "pre_input_publication_disk_reserve": pre_input_disk,
            "pre_publication_disk_reserve": pre_publication_disk,
            "completed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "exposure_sha256": exposure_sha, "exposure_snapshot_sha256": snapshot_sha, "locator_accounting_sha256": locator_sha,
            "expected_exposure_snapshot_sha256": expected_snapshot_sha256, "input_anchors": anchors.__dict__ if hasattr(anchors, "__dict__") else
                {name: getattr(anchors, name) for name in anchors.__dataclass_fields__},
            "counts": {"source_filings": body["source_filings"], "fresh_locator_count": body["fresh_locator_count"],
                       "selected_prefix": len(body["prefix"]), "global_exposed_accessions": body["prior_exposure_input_records"]},
            "operational_exposure_custody_verified": True, "plans_are_dispatch_evidence": False,
            "exposure_scope": "explicit_known_operational_roots_not_proof_of_no_unjournaled_access",
            "effective_process_tree_network_denial": True, "effective_process_fork_denial": not fixture_only,
            "effective_outside_output_write_denial": not fixture_only,
            "writes_confined_to_fresh_output_by_launcher": not fixture_only, "parent_financial_bodies_decoded": False,
            "authority": locators._authority(), "provider_dispatches": 0, "research_looks": 0, "qc_jobs": 0}
        _publication_disk_reserve(output)
        receipt_sha = _publish(output.fd, "complete.json", _canonical(receipt), MAX_CONTROL_BYTES)
        _need(set(os.listdir(output.fd)) == {"exposure.json", "exposure-snapshot.json", "locator-accounting.json", "complete.json"}, "output_inventory_changed")
        for tree in (*trees, census_tree):
            tree.recheck()
        output.recheck()
        _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
        return {"audit_id": audit_id, "fixture_only": fixture_only, "complete_sha256": receipt_sha,
                "locator_accounting_sha256": locator_sha, "exposure_snapshot_sha256": snapshot_sha, "counts": receipt["counts"],
                "source_authenticated": False, "backtest_ready": False, "dispatch_enabled": False}
    finally:
        for tree in reversed(trees):
            tree.close()
        if census_tree is not None:
            census_tree.close()
        if output is not None:
            output.close()


def _id(value):
    _need(type(value) is str and re.fullmatch(r"ib-2006q1-parent-bootstrap-[a-z0-9-]{1,80}", value), "audit_id_refused")
    return value


def _fixture_roots_only(root, roots, master_root):
    """Metadata-only fence before callbacks, control reads, or output opens."""
    try:
        _need(isinstance(root, Path) and root.is_absolute() and root.resolve() == root
              and not custody._fixture_root_is_lane(root), "fixture_root_only_required")
        _need(type(roots) is tuple and 1 <= len(roots) <= 32
              and all(type(spec) is RootSpec and isinstance(spec.path, Path) for spec in roots)
              and isinstance(master_root, Path), "fixture_root_only_required")
        paths = (root, master_root, *(spec.path for spec in roots))
        _need(all(path.is_relative_to(root) and path.resolve() == path for path in paths)
              and master_root in {spec.path for spec in roots}, "fixture_root_only_required")
        protected = (custody.LANE_ROOT, *(spec.path for spec in actual_roots()))
        for path in paths:
            _need(not custody._fixture_root_is_lane(path), "fixture_root_only_required")
            for actual in protected:
                resolved = actual.resolve()
                _need(not path.is_relative_to(resolved) and not resolved.is_relative_to(path),
                      "fixture_root_only_required")
                if actual.exists():
                    # Mac case aliases can resolve to different text while
                    # naming exactly the same live directory inode.
                    _need(all(not parent.samefile(actual) for parent in (path, *path.parents)) and
                          all(not path.samefile(parent) for parent in actual.parents),
                          "fixture_root_only_required")
    except ParentBootstrapError:
        raise
    except (OSError, RuntimeError, custody.ArchiveAssessmentRunnerError):
        raise ParentBootstrapError("fixture_root_only_required") from None


def run_fixture_bootstrap(*, root, roots, master_root, audit_id, identity, anchors, expected_snapshot_sha256):
    _fixture_roots_only(root, roots, master_root)
    _need(callable(identity) and type(anchors) is FixtureAnchors, "fixture_root_only_required")
    _id(audit_id); custody._digest(expected_snapshot_sha256)
    output = custody._Chain(root, (*OUTPUT_PARTS, audit_id), create=True, exclusive_last=True)
    try:
        _publication_disk_reserve(output)
    finally:
        output.close()
    return _worker(root=root, roots=roots, master_root=master_root, audit_id=audit_id, identity=identity(),
                   expected_snapshot_sha256=expected_snapshot_sha256, anchors=anchors, fixture_only=True)


def run_actual_bootstrap(*, audit_id, expected_head, expected_snapshot_sha256):
    _id(audit_id); custody._digest(expected_snapshot_sha256)
    baseline = custody._identity(expected_head)
    _required_identity(baseline, expected_head)
    output = custody._Chain(custody.LANE_ROOT, (*OUTPUT_PARTS, audit_id), create=True, exclusive_last=True)
    try:
        _publication_disk_reserve(output)
    finally:
        output.close()
    command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p",
        custody._policy(custody.LANE_ROOT.joinpath(*OUTPUT_PARTS, audit_id)), sys.executable, "-B", "-m",
        "research.insider_buying_sec_2006q1_parent_bootstrap", "--worker", "--audit-id", audit_id,
        "--expected-head", expected_head, "--expected-exposure-snapshot-sha256", expected_snapshot_sha256]
    result = subprocess.run(command, cwd=custody.LANE_ROOT, input=_canonical(baseline), capture_output=True, check=False, timeout=1800)
    _need(custody._identity(expected_head) == baseline, "parent_source_changed")
    _need(result.returncode == 0 and not result.stderr, "isolated_parent_bootstrap_refused_output_preserved")
    _need(len(result.stdout) <= 2 * 1024 * 1024, "worker_summary_byte_bound")
    observed = _json(result.stdout)
    _verify_publication(root=custody.LANE_ROOT, audit_id=audit_id, identity=baseline,
                        expected_snapshot_sha256=expected_snapshot_sha256, observed=observed, fixture_only=False)
    _need(custody._identity(expected_head) == baseline, "parent_source_changed")
    return observed


def _verify_publication(*, root, audit_id, identity, expected_snapshot_sha256, observed, fixture_only):
    output = custody._Chain(root, (*OUTPUT_PARTS, audit_id))
    try:
        _private_output(output)
        receipt_raw = custody._read_leaf(output.fd, "complete.json", limit=MAX_CONTROL_BYTES); receipt = _json(receipt_raw)
        _verify_disk_receipt(receipt.get("pre_input_publication_disk_reserve"))
        _verify_disk_receipt(receipt.get("pre_publication_disk_reserve"))
        _typed_counts(receipt.get("counts"))
        _typed_counts(observed.get("counts") if type(observed) is dict else None)
        _need(set(os.listdir(output.fd)) == {"exposure.json", "exposure-snapshot.json", "locator-accounting.json", "complete.json"},
              "parent_output_inventory_refused")
        _need(type(observed) is dict and set(observed) == {"audit_id", "fixture_only", "complete_sha256",
                  "locator_accounting_sha256", "exposure_snapshot_sha256", "counts", "source_authenticated", "backtest_ready", "dispatch_enabled"}
              and receipt.get("schema") == SCHEMA and receipt.get("audit_id") == audit_id
              and receipt.get("execution_identity") == identity and receipt.get("fixture_only") is fixture_only
              and observed.get("fixture_only") is fixture_only and observed.get("complete_sha256") == _sha(receipt_raw)
              and observed.get("audit_id") == audit_id
              and receipt.get("expected_exposure_snapshot_sha256") == expected_snapshot_sha256
              and receipt.get("exposure_snapshot_sha256") == expected_snapshot_sha256 == observed.get("exposure_snapshot_sha256")
              and receipt.get("locator_accounting_sha256") == observed.get("locator_accounting_sha256")
              and receipt.get("counts") == observed.get("counts")
              and receipt.get("effective_process_tree_network_denial") is True
              and receipt.get("effective_process_fork_denial") is (not fixture_only)
              and receipt.get("effective_outside_output_write_denial") is (not fixture_only)
              and receipt.get("writes_confined_to_fresh_output_by_launcher") is (not fixture_only)
              and receipt.get("parent_financial_bodies_decoded") is False
              and receipt.get("operational_exposure_custody_verified") is True
              and receipt.get("exposure_scope") == "explicit_known_operational_roots_not_proof_of_no_unjournaled_access"
              and receipt.get("plans_are_dispatch_evidence") is False
              and observed.get("source_authenticated") is False
              and observed.get("backtest_ready") is False and observed.get("dispatch_enabled") is False
              and receipt.get("authority") == locators._authority()
              and all(receipt.get(key) == 0 and type(receipt.get(key)) is int for key in ("provider_dispatches", "research_looks", "qc_jobs")),
              "parent_output_binding_refused")
        _utc(receipt.get("completed_at_utc"))
        payloads = {}
        for name, key, cap in (("exposure.json", "exposure_sha256", locators.MAX_EXPOSURE_BYTES),
            ("exposure-snapshot.json", "exposure_snapshot_sha256", MAX_SNAPSHOT_BYTES),
            ("locator-accounting.json", "locator_accounting_sha256", locators.MAX_OUTPUT_BYTES)):
            raw = custody._read_leaf(output.fd, name, limit=cap)
            _need(_sha(raw) == receipt.get(key), "parent_output_hash_refused")
            payloads[name] = _json(raw, newline=False)
        accounting, snapshot, exposure = payloads["locator-accounting.json"], payloads["exposure-snapshot.json"], payloads["exposure.json"]
        _typed_payload_counts(accounting, snapshot)
        _need(type(accounting.get("prefix")) is list and type(exposure.get("records")) is list,
              "parent_payload_count_collections_refused")
        _need(accounting.get("schema") == locators.SCHEMA and accounting.get("maximum_prefix") == 64
              and accounting.get("authority") == locators._authority()
              and accounting.get("prior_exposure_inventory_sha256") == receipt["exposure_sha256"]
              and snapshot.get("exposure_inventory_sha256") == receipt["exposure_sha256"]
              and exposure.get("schema") == locators.EXPOSURE_SCHEMA
              and snapshot.get("global_exposed_accessions") == len(exposure.get("records", []))
              and accounting.get("prior_exposure_input_records") == len(exposure["records"])
              and receipt.get("counts") == {"source_filings": accounting.get("source_filings"),
                  "fresh_locator_count": accounting.get("fresh_locator_count"), "selected_prefix": len(accounting.get("prefix", [])),
                  "global_exposed_accessions": len(exposure.get("records", []))}, "parent_payload_binding_refused")
        anchors = receipt.get("input_anchors")
        _need(type(anchors) is dict and set(anchors) == set(FixtureAnchors.__dataclass_fields__)
              and accounting.get("submission_inventory_sha256") == anchors["inventory_sha256"]
              and accounting.get("master_decoded_sha256") == anchors["master_decoded_sha256"]
              and accounting.get("master_receipt_sha256") == anchors["master_receipt_sha256"], "parent_input_anchor_binding_refused")
        if not fixture_only:
            _need(anchors == {"inventory_sha256": custody.INVENTORY_SHA256,
                "census_complete_sha256": custody.CENSUS_COMPLETE_SHA256, "master_commit_sha256": MASTER_COMMIT_SHA256,
                "master_report_sha256": MASTER_REPORT_SHA256, "master_gzip_sha256": MASTER_GZIP_SHA256,
                "master_decoded_sha256": locators.RETAINED_MASTER_SHA256, "master_receipt_sha256": MASTER_RECEIPT_SHA256},
                "actual_input_anchors_refused")
        output.recheck()
        _need(set(os.listdir(output.fd)) == set(payloads) | {"complete.json"}
              and custody._read_leaf(output.fd, "complete.json", limit=MAX_CONTROL_BYTES) == receipt_raw,
              "parent_output_changed_after_read")
        for name, raw in payloads.items():
            cap = locators.MAX_OUTPUT_BYTES if name == "locator-accounting.json" else MAX_SNAPSHOT_BYTES
            _need(_json(custody._read_leaf(output.fd, name, limit=cap), newline=False) == raw, "parent_output_changed_after_read")
        output.recheck()
        _private_output(output)
    finally:
        output.close()


def _typed_counts(counts):
    _need(type(counts) is dict and set(counts) == {"source_filings", "fresh_locator_count", "selected_prefix", "global_exposed_accessions"}
          and all(type(value) is int and value >= 0 for value in counts.values()), "parent_counts_refused")


def _typed_payload_counts(accounting, snapshot):
    _need(type(accounting) is dict and type(snapshot) is dict
          and all(type(accounting.get(key)) is int and accounting[key] >= 0
                  for key in ("source_filings", "fresh_locator_count", "prior_exposure_input_records"))
          and type(snapshot.get("global_exposed_accessions")) is int and snapshot["global_exposed_accessions"] >= 0,
          "parent_payload_counts_refused")


def _required_identity(identity, expected_head):
    required = {"research/insider_buying_sec_2006q1_parent_bootstrap.py",
                "research/insider_buying_sec_2006q1_parent_locators.py",
                "research/insider_buying/sec_quarter_master_index.py",
                "research/insider_buying/sec_edgar_acceptance_snapshot.py"}
    _need(type(identity) is dict and identity.get("root") == str(custody.LANE_ROOT)
          and identity.get("branch") == custody.LANE_BRANCH and identity.get("head") == expected_head
          and identity.get("clean") is True and type(identity.get("source_sha256")) is dict
          and required <= set(identity["source_sha256"])
          and identity.get("source_inventory_sha256") == _sha(_canonical(identity["source_sha256"])),
          "parent_identity_refused")
    for name, digest in identity["source_sha256"].items():
        _need(type(name) is str and type(digest) is str and _SHA.fullmatch(digest), "parent_identity_refused")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True); parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-exposure-snapshot-sha256", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            _need(Path.cwd() == custody.LANE_ROOT, "designated_lane_required")
            identity = _json(sys.stdin.buffer.read(4 * 1024 * 1024))
            _required_identity(identity, args.expected_head)
            anchors = FixtureAnchors(custody.INVENTORY_SHA256, custody.CENSUS_COMPLETE_SHA256, MASTER_COMMIT_SHA256,
                MASTER_REPORT_SHA256, MASTER_GZIP_SHA256, locators.RETAINED_MASTER_SHA256, MASTER_RECEIPT_SHA256)
            result = _worker(root=custody.LANE_ROOT, roots=actual_roots(),
                master_root=custody.LANE_ROOT.parent.joinpath(*MASTER_ROOT_PARTS), audit_id=_id(args.audit_id), identity=identity,
                expected_snapshot_sha256=custody._digest(args.expected_exposure_snapshot_sha256), anchors=anchors, fixture_only=False)
        else:
            result = run_actual_bootstrap(audit_id=args.audit_id, expected_head=args.expected_head,
                                         expected_snapshot_sha256=args.expected_exposure_snapshot_sha256)
        # The parent's strict decoder accepts canonical controls, including
        # its child's summary. Default json.dumps spacing is not that wire format.
        print(_canonical(result).decode()); return 0
    except (ParentBootstrapError, custody.ArchiveAssessmentRunnerError, custody.EodhdDemoError, locators.ParentLocatorError,
            OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print('{"disposition":"offline_parent_bootstrap_refused_outputs_preserved"}'); return 2


if __name__ == "__main__":
    raise SystemExit(main())
