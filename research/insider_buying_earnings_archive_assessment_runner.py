"""Isolated, offline actual metadata assessment with externally pinned inputs.

The parent verifies committed lane identity before/after a Seatbelt worker.
The worker denies process-tree network/fork and all writes except its fresh
output directory. It only hashes paid response bodies; it never decodes their
financial fields or reads credentials. This does not authenticate the vendor,
establish historical mappings, or grant QC/backtest/processing authority.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys

from research import insider_buying_earnings_archive_cohort_assessment as assessment
from research.insider_buying_eodhd_earnings_demo import EodhdDemoError, _git, _read_leaf, FALSE_FLAGS
from research.insider_buying_provider_metadata_audit import _exclusive_json


LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
SCHEMA = "insider-earnings-archive-assessment-observer-v1"
CENSUS_PARTS = ("artifacts", "insider_buying", "earnings_issuer_inventory", "ib-2006q1-metadata-20261013-once")
V1_PARTS = ("artifacts", "insider_buying", "eodhd_earnings_campaign")
V2_PARTS = ("artifacts", "insider_buying", "eodhd_earnings_continuation")
OUTPUT_PARTS = ("artifacts", "insider_buying", "earnings_archive_assessment")
V1_ID = "ib-eodhd-campaign-200512-202607-20261013-once"
V2_ID = "ib-eodhd-campaign-continuation-200602-202607-20261013-once"
INVENTORY_SHA256 = "a36662f0d29888ee3d38543c9cae2a2d702073790419280b596fe879ea24c30f"
CENSUS_COMPLETE_SHA256 = "3b6016400f667a375814214a3b9ea17a3a5b7e6597f9eb3fe2f3b949dcb8d102"
V1_COMPLETE_SHA256 = "c2607ac0b5b412d5e907ce5a904fa272cbd47cee59385090646d3adc4c12f201"
V1_MANIFEST_SHA256 = "ee6c2374ad0b1770ec27dfce781f2dd5a47c4959735f112ec059805dc7eaddf5"
# Later independent raw-body reprojection/custody observation, not a field
# retroactively inserted into the frozen original producer receipt.
V1_METADATA_SHA256 = "61e257f768e1ce658e3d1f893aded7c5a79121ae7e0293580a36334b5b222023"
REQUIRED_SOURCES = (
    "research/__init__.py", "research/insider_buying_earnings_archive_assessment_runner.py",
    "research/insider_buying_earnings_archive_cohort_assessment.py",
    "research/insider_buying_earnings_issuer_inventory.py", "research/insider_buying_eodhd_earnings_campaign.py",
    "research/insider_buying_eodhd_earnings_continuation.py", "research/insider_buying_eodhd_calendar_qualification.py",
    "research/insider_buying_eodhd_earnings_demo.py", "research/insider_buying_provider_metadata_audit.py",
    "research/insider_buying_provider_metadata_transport.py", "research/quantconnect.py",
)


class ArchiveAssessmentRunnerError(ValueError):
    """Fixed sanitized refusal, never filesystem/provider/credential text."""


def _need(condition, code):
    if not condition:
        raise ArchiveAssessmentRunnerError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    _need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "external_digest_required")
    return value


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            _need(key not in value, "duplicate_metadata_key")
            value[key] = item
        return value
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: _need(False, "nonfinite_metadata"))
        _need(type(value) is dict and _canonical(value) == raw, "canonical_metadata_required")
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ArchiveAssessmentRunnerError("metadata_schema_refused") from None


@dataclass(frozen=True, slots=True)
class FixtureAnchors:
    inventory_sha256: str
    census_complete_sha256: str
    v1_complete_sha256: str
    v1_manifest_sha256: str
    v1_metadata_sha256: str


def _version(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


class _Chain:
    """Held no-follow ancestry, including every component of the absolute root."""
    def __init__(self, root, parts, *, create=False, exclusive_last=False):
        self.links, self.fds = [], []
        root = Path(root)
        _need(root.is_absolute() and ".." not in root.parts, "absolute_named_root_required")
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.fds.append(directory)
        try:
            components = tuple(root.parts[1:]) + tuple(parts)
            for index, name in enumerate(components):
                private = tuple(parts[:2]) == ("artifacts", "insider_buying") and index >= len(root.parts) - 1 + 2
                if create and index >= len(root.parts) - 1:
                    try:
                        os.mkdir(name, 0o700, dir_fd=directory); os.fsync(directory)
                    except FileExistsError:
                        _need(not (exclusive_last and index == len(components) - 1), "output_cannot_resume_or_overwrite")
                named = os.stat(name, dir_fd=directory, follow_symlinks=False)
                _need(stat.S_ISDIR(named.st_mode) and (not private or stat.S_IMODE(named.st_mode) == 0o700),
                      "directory_custody_refused")
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                self.fds.append(child)
                opened = os.fstat(child)
                _need((named.st_dev, named.st_ino, named.st_mode) == (opened.st_dev, opened.st_ino, opened.st_mode),
                      "directory_custody_refused")
                self.links.append((directory, name, child, private))
                directory = child
            self.fd = directory
        except BaseException:
            self.close(); raise

    def recheck(self):
        for parent, name, child, private in self.links:
            named = os.stat(name, dir_fd=parent, follow_symlinks=False); opened = os.fstat(child)
            _need(stat.S_ISDIR(named.st_mode) and (not private or stat.S_IMODE(named.st_mode) == 0o700)
                  and (named.st_dev, named.st_ino, named.st_mode) == (opened.st_dev, opened.st_ino, opened.st_mode),
                  "directory_custody_refused")

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds = []


class _Inputs:
    def __init__(self, root):
        self.root, self.chains, self.leaves, self.locks = root, [], [], []
        self.hashes = {}
        self.inventories = []

    def directory(self, parts):
        chain = _Chain(self.root, parts)
        self.chains.append(chain)
        return chain

    def read(self, chain, parts, name, *, limit, expected=None):
        chain.recheck()
        before = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
        raw = _read_leaf(chain.fd, name, limit=limit)
        after = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
        _need(_version(before) == _version(after), "input_leaf_changed")
        digest = _sha(raw)
        _need(expected is None or digest == _digest(expected), "external_input_hash_mismatch")
        relative = "/".join((*parts, name))
        _need(relative not in self.hashes, "input_leaf_accounted_twice")
        self.hashes[relative] = digest
        self.leaves.append((chain, name, limit, digest, _version(after)))
        chain.recheck()
        return raw

    def lock(self, chain):
        named = os.stat("campaign.lock", dir_fd=chain.fd, follow_symlinks=False)
        _need(stat.S_ISREG(named.st_mode) and stat.S_IMODE(named.st_mode) == 0o600
              and named.st_nlink == 1 and named.st_size == 0, "source_lock_custody_refused")
        fd = os.open("campaign.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=chain.fd)
        try:
            _need(_version(named) == _version(os.fstat(fd)), "source_lock_custody_refused")
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd); raise
        self.locks.append((chain, fd, _version(named)))

    def inventory(self, chain, names):
        _need(set(os.listdir(chain.fd)) == set(names), "input_directory_inventory_refused")
        self.inventories.append((chain, set(names)))

    def recheck(self):
        for chain in self.chains:
            chain.recheck()
        for chain, names in self.inventories:
            _need(set(os.listdir(chain.fd)) == names, "input_directory_inventory_refused")
        for chain, name, limit, digest, version in self.leaves:
            _need(_version(os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) == version
                  and _sha(_read_leaf(chain.fd, name, limit=limit)) == digest, "input_leaf_changed")
        for chain, fd, version in self.locks:
            _need(_version(os.stat("campaign.lock", dir_fd=chain.fd, follow_symlinks=False)) == version
                  and _version(os.fstat(fd)) == version, "source_lock_custody_refused")
        for chain in self.chains:
            chain.recheck()

    def close(self):
        for _, fd, _ in self.locks:
            os.close(fd)
        for chain in reversed(self.chains):
            chain.close()


def _internal_source_paths(root):
    """Conservative static internal import closure plus loaded internal modules."""
    pending, found = list(REQUIRED_SOURCES), set()
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if type(filename) is str:
            path = Path(filename)
            if path.suffix == ".py" and path.is_relative_to(root):
                pending.append(str(path.relative_to(root)))
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        chain = _Chain(root, tuple(Path(name).parts[:-1]))
        try:
            raw = _read_leaf(chain.fd, Path(name).name, limit=4 * 1024 * 1024, private=False)
        finally:
            chain.close()
        tree = ast.parse(raw, filename=name)
        modules = []
        package = Path(name).parent.parts
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = ".".join(package[:len(package) + 1 - node.level]) if node.level else ""
                module = ".".join(part for part in (prefix, node.module) if part)
                modules.append(module)
                modules.extend(module + "." + alias.name for alias in node.names if alias.name != "*")
        for module in modules:
            parts = tuple(module.split("."))
            candidates = (Path(*parts).with_suffix(".py"), Path(*parts) / "__init__.py")
            for candidate in candidates:
                if (root / candidate).is_file():
                    pending.append(str(candidate))
            for count in range(1, len(parts)):
                candidate = Path(*parts[:count]) / "__init__.py"
                if (root / candidate).is_file():
                    pending.append(str(candidate))
    return tuple(sorted(found))


def _source_bytes(root, names):
    inventory = {}
    for name in names:
        _need(type(name) is str and not Path(name).is_absolute() and ".." not in Path(name).parts, "source_name_refused")
        chain = _Chain(root, tuple(Path(name).parts[:-1]))
        try:
            raw = _read_leaf(chain.fd, Path(name).name, limit=4 * 1024 * 1024, private=False)
            chain.recheck()
        finally:
            chain.close()
        inventory[name] = _sha(raw)
    return inventory


def _identity(expected_head):
    _need(Path.cwd() == LANE_ROOT and LANE_ROOT.resolve() == LANE_ROOT
          and type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head), "designated_lane_required")
    _need(_git(LANE_ROOT, "rev-parse", "--show-toplevel").decode().strip() == str(LANE_ROOT)
          and _git(LANE_ROOT, "branch", "--show-current").decode().strip() == LANE_BRANCH
          and _git(LANE_ROOT, "rev-parse", "HEAD").decode().strip() == expected_head
          and _git(LANE_ROOT, "status", "--porcelain=v1", "--untracked-files=all") == b"", "clean_exact_committed_lane_required")
    inventory = _source_bytes(LANE_ROOT, _internal_source_paths(LANE_ROOT))
    for name, digest in inventory.items():
        _need(_sha(_git(LANE_ROOT, "show", expected_head + ":" + name)) == digest, "current_committed_source_mismatch")
    _need(_git(LANE_ROOT, "rev-parse", "HEAD").decode().strip() == expected_head
          and _git(LANE_ROOT, "branch", "--show-current").decode().strip() == LANE_BRANCH
          and _git(LANE_ROOT, "status", "--porcelain=v1", "--untracked-files=all") == b"", "lane_changed_during_identity")
    return {"root": str(LANE_ROOT), "branch": LANE_BRANCH, "head": expected_head, "clean": True,
            "source_sha256": inventory, "source_inventory_sha256": _sha(_canonical(inventory))}


def _scope(window):
    return {"method": "GET", "endpoint": "https://eodhd.com/api/calendar/earnings",
            "from": window[0], "to": window[1], "fmt": "json", "symbols": None}


def _load_campaign(inputs, parts, campaign_id, complete_sha, *, manifest_sha=None, fixture_only=False,
                   v1_metadata_sha256=None):
    base = inputs.directory(parts); inputs.lock(base)
    scopes_parts, campaign_parts = (*parts, "scopes"), (*parts, "campaigns", campaign_id)
    scopes, source = inputs.directory(scopes_parts), inputs.directory(campaign_parts)
    inputs.inventory(base, {"campaigns", "scopes", "campaign.lock"})
    parents = inputs.directory((*parts, "campaigns"))
    inputs.inventory(parents, {campaign_id})
    manifest_raw = inputs.read(source, campaign_parts, "manifest.json", limit=assessment.MAX_JOURNAL_BYTES, expected=manifest_sha)
    manifest_digest = _sha(manifest_raw); manifest = _json(manifest_raw)
    complete_raw = inputs.read(source, campaign_parts, "complete.json", limit=assessment.MAX_JOURNAL_BYTES, expected=complete_sha)
    complete = _json(complete_raw)
    _need(complete.get("campaign_id") == manifest.get("campaign_id") == campaign_id
          and complete.get("manifest_sha256") == manifest_digest
          and complete.get("identity") == manifest.get("identity")
          and complete.get("fixture_only") is fixture_only and manifest.get("fixture_only") is fixture_only,
          "campaign_actual_source_binding")
    windows = manifest.get("windows"); results = complete.get("window_results")
    _need(type(windows) is list and type(results) is list and len(results) <= len(windows), "campaign_window_inventory")
    expected_leaves, expected_scopes, evidence = {"manifest.json", "complete.json"}, set(), []
    for index, result in enumerate(results):
        _need(type(result) is dict and type(result.get("index")) is int and result["index"] == index
              and result.get("window") == windows[index], "campaign_window_order")
        window = windows[index]; prefix = f"window-{index:04d}"
        child_name, start_name = prefix + "-complete.json", prefix + "-started.json"
        child_raw = inputs.read(source, campaign_parts, child_name, limit=assessment.MAX_JOURNAL_BYTES, expected=result["complete_sha256"])
        child = _json(child_raw)
        start_raw = inputs.read(source, campaign_parts, start_name, limit=assessment.MAX_JOURNAL_BYTES, expected=child["started_sha256"])
        start = _json(start_raw)
        _need(start == {"schema": manifest["schema"], "window": window, "index": index,
            "started_at_utc": start.get("started_at_utc"), "manifest_sha256": manifest_digest,
            "scope_reservation_sha256": child["scope_reservation_sha256"], "maximum_attempts": 1}, "started_hash_chain")
        reservation_scope = _scope(window); scope_name = _sha(_canonical(reservation_scope)) + ".json"
        scope_raw = inputs.read(scopes, scopes_parts, scope_name, limit=assessment.MAX_JOURNAL_BYTES, expected=child["scope_reservation_sha256"])
        scope = _json(scope_raw)
        _need(scope == {"schema": manifest["schema"], "scope": reservation_scope, "campaign_id": campaign_id,
            "reserved_at_utc": scope.get("reserved_at_utc"), "maximum_attempts": 1}, "scope_hash_chain")
        _need(assessment._utc(manifest["registered_at_utc"]) <= assessment._utc(scope["reserved_at_utc"])
              <= assessment._utc(start["started_at_utc"]) <= assessment._utc(child["completed_at_utc"])
              <= assessment._utc(complete["completed_at_utc"]), "journal_observation_order")
        receipt = child["receipt"]
        expected_leaves.update((child_name, start_name)); expected_scopes.add(scope_name)
        _need(all(receipt.get(flag) is False for flag in FALSE_FLAGS), "source_authority_flags_not_false")
        metadata_raw = metadata_sha = None
        if receipt.get("calendar_window_observed") is True:
            # Hash only: no JSON parsing, field conversion or value observation.
            body_name = prefix + "-response.json"
            body_raw = inputs.read(source, campaign_parts, body_name, limit=4 * 1024 * 1024, expected=receipt["body_sha256"])
            _need(type(receipt["body_size_bytes"]) is int and len(body_raw) == receipt["body_size_bytes"], "response_body_size_mismatch")
            del body_raw
            metadata_name = prefix + "-metadata.json"
            expected_metadata = (v1_metadata_sha256 if manifest["schema"] != assessment.CONTINUATION_SCHEMA
                                 else receipt.get("metadata_sha256"))
            _digest(expected_metadata)
            metadata_raw = inputs.read(source, campaign_parts, metadata_name, limit=assessment.MAX_JOURNAL_BYTES,
                                       expected=expected_metadata)
            metadata_sha = _sha(metadata_raw)
            expected_leaves.update((body_name, metadata_name))
        evidence.append(assessment.ArchiveWindowMetadata(child_raw, _sha(child_raw), metadata_raw, metadata_sha))
    inputs.inventory(source, expected_leaves); inputs.inventory(scopes, expected_scopes)
    source.recheck(); scopes.recheck()
    return assessment.ArchiveCampaignMetadata(manifest_raw, manifest_digest, complete_raw, complete_sha, tuple(evidence))


def _effective_denial(*, require_fork):
    handle = None
    try:
        handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        handle.settimeout(0.2); handle.connect(("127.0.0.1", 9))
    except OSError as exc:
        _need(exc.errno in {errno.EPERM, errno.EACCES}, "effective_os_network_denial_not_observed")
    else:
        raise ArchiveAssessmentRunnerError("effective_os_network_denial_not_observed")
    finally:
        if handle is not None:
            handle.close()
    if require_fork:
        try:
            child = os.fork()
        except OSError as exc:
            _need(exc.errno in {errno.EPERM, errno.EACCES}, "effective_process_fork_denial_not_observed")
        else:
            if child == 0:
                os._exit(0)
            os.waitpid(child, 0)
            raise ArchiveAssessmentRunnerError("effective_process_fork_denial_not_observed")


def _write_raw(directory, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.fsync(directory)
    _need(_read_leaf(directory, name, limit=assessment.MAX_INVENTORY_BYTES) == raw, "published_assessment_custody")


def _policy(output_path):
    return '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(allow file-write* (subpath ' + json.dumps(str(output_path)) + '))'


def _outside_write_denied(root, audit_id):
    # A fresh sibling name, never an existing credential/user file. If the OS
    # policy is unexpectedly absent, preserve the empty probe and refuse.
    path = root.joinpath(*OUTPUT_PARTS, "isolation-" + audit_id + ".probe")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        _need(exc.errno in {errno.EPERM, errno.EACCES}, "outside_output_write_denial_not_observed")
    else:
        os.close(fd)
        raise ArchiveAssessmentRunnerError("outside_output_write_denial_not_observed")


def _assess_worker(*, root, audit_id, identity, v2_complete_sha, anchors, fixture_only):
    _effective_denial(require_fork=not fixture_only)
    if not fixture_only:
        _outside_write_denied(root, audit_id)
    _need(_source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_inventory_changed")
    inputs = _Inputs(root); output = None
    try:
        census = inputs.directory(CENSUS_PARTS)
        inputs.inventory(census, {"inventory.json", "complete.json"})
        inventory_raw = inputs.read(census, CENSUS_PARTS, "inventory.json", limit=assessment.MAX_INVENTORY_BYTES, expected=anchors.inventory_sha256)
        census_complete_raw = inputs.read(census, CENSUS_PARTS, "complete.json", limit=assessment.MAX_JOURNAL_BYTES, expected=anchors.census_complete_sha256)
        census_complete = _json(census_complete_raw); inventory = _json(inventory_raw)
        _need(census_complete.get("schema") == "insider-2006q1-metadata-observer-completion-v1"
              and census_complete.get("fixture_only") is fixture_only
              and census_complete.get("inventory_sha256") == anchors.inventory_sha256
              and type(census_complete.get("inventory_bytes")) is int and census_complete["inventory_bytes"] == len(inventory_raw)
              and census_complete.get("accounting") == inventory.get("accounting"), "census_completion_binding")
        first = _load_campaign(inputs, V1_PARTS, V1_ID, anchors.v1_complete_sha256,
                               manifest_sha=anchors.v1_manifest_sha256, fixture_only=fixture_only,
                               v1_metadata_sha256=anchors.v1_metadata_sha256)
        second = _load_campaign(inputs, V2_PARTS, V2_ID, v2_complete_sha, fixture_only=fixture_only)
        inputs.recheck()
        result = assessment.assess_earnings_archive_cohort(inventory_raw=inventory_raw,
            inventory_sha256=anchors.inventory_sha256, campaigns=(first, second))
        inputs.recheck()
        _need(_source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_inventory_changed")
        output = _Chain(root, (*OUTPUT_PARTS, audit_id))
        _need(os.listdir(output.fd) == [], "output_cannot_resume_or_overwrite")
        raw = result.canonical_bytes(); _write_raw(output.fd, "assessment.json", raw)
        body = result.to_payload()
        receipt = {"schema": SCHEMA, "audit_id": audit_id, "completed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "fixture_only": fixture_only, "execution_identity": identity, "assessment_sha256": result.sha256,
            "assessment_bytes": len(raw), "input_sha256": dict(sorted(inputs.hashes.items())),
            "input_inventory_sha256": _sha(_canonical(inputs.hashes)), "expected_v2_complete_sha256": v2_complete_sha,
            "v1_metadata_anchor_provenance": "later-independent-body-reprojection-not-original-producer-receipt",
            "counts": {key: body[key] for key in ("source_filings", "all_form_issuer_count", "relevant_issuer_count",
                "source_metadata_rows", "provider_code_count", "metadata_accepted_rows", "quarantined_metadata_rows")},
            "unavailable_window_count": len(body["unavailable_windows"]), "source_file_custody_verified": True,
            "effective_process_tree_network_denial": True, "effective_process_fork_denial": not fixture_only,
            "effective_outside_output_write_denial": not fixture_only,
            "writes_confined_to_fresh_output_by_launcher": not fixture_only, "raw_financial_bodies_decoded": False,
            "credential_read": False, "looks_jobs_backtests": [0, 0, 0], **{flag: False for flag in FALSE_FLAGS}}
        inputs.recheck(); output.recheck()
        complete_sha = _exclusive_json(output.fd, "complete.json", receipt)
        _need(set(os.listdir(output.fd)) == {"assessment.json", "complete.json"}
              and _sha(_read_leaf(output.fd, "assessment.json", limit=assessment.MAX_INVENTORY_BYTES)) == result.sha256
              and _sha(_read_leaf(output.fd, "complete.json", limit=assessment.MAX_JOURNAL_BYTES)) == complete_sha,
              "published_output_inventory_or_hash")
        inputs.recheck(); output.recheck()
        _need(_source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_inventory_changed")
        return {"audit_id": audit_id, "fixture_only": fixture_only, "assessment_sha256": result.sha256,
                "complete_sha256": complete_sha, "counts": receipt["counts"],
                "unavailable_window_count": receipt["unavailable_window_count"], **{flag: False for flag in FALSE_FLAGS}}
    except (OSError, EodhdDemoError, assessment.EarningsArchiveAssessmentError, KeyError, TypeError, ValueError) as exc:
        if type(exc) is ArchiveAssessmentRunnerError:
            raise
        raise ArchiveAssessmentRunnerError("offline_input_or_output_refused") from None
    finally:
        if output is not None:
            output.close()
        inputs.close()


def _audit_id(value):
    _need(type(value) is str and re.fullmatch(r"ib-earnings-assessment-[a-z0-9-]{1,80}", value), "audit_id_refused")
    return value


def run_fixture_assessment(*, root, audit_id, expected_head, expected_v2_complete_sha256,
                           anchors: FixtureAnchors, identity):
    """Explicit invented-root/callback path, always marked fixture-only."""
    _need(isinstance(root, Path) and root != LANE_ROOT and root.resolve() == root
          and callable(identity) and identity is not _identity and type(anchors) is FixtureAnchors,
          "fixture_root_and_explicit_identity_required")
    _audit_id(audit_id); _digest(expected_v2_complete_sha256)
    baseline = identity(expected_head)
    output = _Chain(root, (*OUTPUT_PARTS, audit_id), create=True, exclusive_last=True); output.close()
    return _assess_worker(root=root, audit_id=audit_id, identity=baseline, v2_complete_sha=expected_v2_complete_sha256,
                         anchors=anchors, fixture_only=True)


def _verify_worker_publication(*, root, audit_id, identity, v2_complete_sha, result, fixture_only=False):
    """Parent reattaches the output and binds the worker response to its bytes."""
    output = _Chain(root, (*OUTPUT_PARTS, audit_id))
    try:
        _need(set(os.listdir(output.fd)) == {"assessment.json", "complete.json"}, "parent_output_inventory_refused")
        receipt_raw = _read_leaf(output.fd, "complete.json", limit=assessment.MAX_JOURNAL_BYTES)
        receipt = _json(receipt_raw)
        body = _read_leaf(output.fd, "assessment.json", limit=assessment.MAX_INVENTORY_BYTES)
        _need(type(result) is dict and result.get("audit_id") == audit_id and result.get("fixture_only") is fixture_only
              and result.get("complete_sha256") == _sha(receipt_raw)
              and result.get("assessment_sha256") == _sha(body) == receipt.get("assessment_sha256")
              and type(receipt.get("assessment_bytes")) is int and receipt["assessment_bytes"] == len(body)
              and receipt.get("schema") == SCHEMA and receipt.get("execution_identity") == identity
              and receipt.get("fixture_only") is fixture_only
              and receipt.get("expected_v2_complete_sha256") == v2_complete_sha
              and receipt.get("counts") == result.get("counts")
              and receipt.get("unavailable_window_count") == result.get("unavailable_window_count")
              and receipt.get("raw_financial_bodies_decoded") is False and receipt.get("credential_read") is False
              and receipt.get("looks_jobs_backtests") == [0, 0, 0]
              and all(receipt.get(flag) is False and result.get(flag) is False for flag in FALSE_FLAGS),
              "parent_worker_receipt_binding_refused")
        output.recheck()
    finally:
        output.close()


def run_actual_assessment(*, audit_id, expected_head, expected_v2_complete_sha256):
    _audit_id(audit_id); _digest(expected_v2_complete_sha256)
    baseline = _identity(expected_head)
    output = _Chain(LANE_ROOT, (*OUTPUT_PARTS, audit_id), create=True, exclusive_last=True); output.close()
    _need(_identity(expected_head) == baseline, "parent_source_identity_changed")
    output_path = LANE_ROOT.joinpath(*OUTPUT_PARTS, audit_id)
    policy = _policy(output_path)
    command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
               sys.executable, "-B", "-m", "research.insider_buying_earnings_archive_assessment_runner", "--worker",
               "--audit-id", audit_id, "--expected-head", expected_head,
               "--expected-v2-complete-sha256", expected_v2_complete_sha256]
    launched = subprocess.run(command, cwd=LANE_ROOT, input=_canonical(baseline), capture_output=True, check=False)
    _need(_identity(expected_head) == baseline, "parent_source_identity_changed")
    _need(launched.returncode == 0 and not launched.stderr, "isolated_worker_refused_output_preserved")
    try:
        result = json.loads(launched.stdout)
    except (ValueError, UnicodeError):
        raise ArchiveAssessmentRunnerError("isolated_worker_output_schema") from None
    _verify_worker_publication(root=LANE_ROOT, audit_id=audit_id, identity=baseline,
                              v2_complete_sha=expected_v2_complete_sha256, result=result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-v2-complete-sha256", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            _need(Path.cwd() == LANE_ROOT, "designated_lane_required")
            identity = _json(sys.stdin.buffer.read(4 * 1024 * 1024))
            _need(identity.get("root") == str(LANE_ROOT) and identity.get("branch") == LANE_BRANCH
                  and identity.get("head") == args.expected_head and identity.get("clean") is True
                  and set(REQUIRED_SOURCES) <= set(identity.get("source_sha256", {}))
                  and identity.get("source_inventory_sha256") == _sha(_canonical(identity["source_sha256"])),
                  "parent_identity_envelope_refused")
            anchors = FixtureAnchors(INVENTORY_SHA256, CENSUS_COMPLETE_SHA256, V1_COMPLETE_SHA256,
                                     V1_MANIFEST_SHA256, V1_METADATA_SHA256)
            result = _assess_worker(root=LANE_ROOT, audit_id=_audit_id(args.audit_id), identity=identity,
                v2_complete_sha=_digest(args.expected_v2_complete_sha256), anchors=anchors, fixture_only=False)
        else:
            result = run_actual_assessment(audit_id=args.audit_id, expected_head=args.expected_head,
                                          expected_v2_complete_sha256=args.expected_v2_complete_sha256)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ArchiveAssessmentRunnerError, OSError, EodhdDemoError, subprocess.SubprocessError):
        print('{"disposition":"offline_assessment_refused_outputs_preserved"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
