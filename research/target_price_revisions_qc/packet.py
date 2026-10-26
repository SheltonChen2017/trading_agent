"""Pure, private six-universe signal packet construction and bounded packaging.

The caller owns the fresh authorized source read and cloud upload. This module
opens no files and grants no authority. It reuses the immutable raw-candidate
scoring, retaining every supplied identity rather than the old top-ten winners.
Neither the current identity snapshot nor censored-last-touch scores are PIT.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from research.target_price_revisions_development import raw_candidate, raw_revision

FAMILY_ID = "TPR-QC6-20261008-v1"
FREEZE_SHA256 = "3cf40af7325265b15f7de5e03f0667a1554c889fdd2db02de228a01b2fa97ccf"
FROZEN_STRUCTURE_SHA256 = "509047244d47ec489e5a8e1dfbf74e0d0104b51c7dfff19ae7283abba1e9ccd5"
FROZEN_SOURCE_HASHES = {
    "raw_candidate.py": "6232723188bedfbce5ba88ceccd460c1ce1011bffad5338e87b59b648458a6c0",
    "raw_revision.py": "ea4efcd9b0e73ae0b5c166d820c51e054559a3ed610041a6eb2acc8abca36353",
}
SESSIONS = ("2025-01-02", "2025-01-06", "2025-01-13", "2025-01-21",
            "2025-01-27", "2025-02-03", "2025-02-10", "2025-02-18",
            "2025-02-24", "2025-03-03", "2025-03-10", "2025-03-17",
            "2025-03-24", "2025-03-31")
CUTOFFS = ("2024-12-31T23:00:00+00:00", "2025-01-03T23:00:00+00:00",
           "2025-01-10T23:00:00+00:00", "2025-01-17T23:00:00+00:00",
           "2025-01-24T23:00:00+00:00", "2025-01-31T23:00:00+00:00",
           "2025-02-07T23:00:00+00:00", "2025-02-14T23:00:00+00:00",
           "2025-02-21T23:00:00+00:00", "2025-02-28T23:00:00+00:00",
           "2025-03-07T23:00:00+00:00", "2025-03-14T22:00:00+00:00",
           "2025-03-21T22:00:00+00:00", "2025-03-28T22:00:00+00:00")
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_PACKET_BYTES = 16 * 1024 * 1024
_NO_ADMISSIBLE = frozenset({"issued_after_cutoff", "not_yet_eligible",
    "initiation_not_revision", "withdrawal_not_revision", "unsupported_currency",
    "unsupported_target_action"})
_STATES = frozenset({"scored", "no_admissible_event", "unknown_input", "identity_ineligible"})


class PacketError(ValueError):
    """Fixed refusal that does not echo private input values."""


def _fail(message):
    raise PacketError(message)


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value):
    """Return deterministic UTF-8 JSON bytes; callers must protect private bytes."""
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    except (TypeError, ValueError, OverflowError):
        _fail("packet JSON serialization refused")


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            _fail("duplicate JSON key")
        result[key] = value
    return result


def _constant(_value):
    _fail("nonfinite JSON constant")


def _load(payload, maximum):
    if type(payload) is not bytes or not 0 < len(payload) <= maximum:
        _fail("bounded JSON bytes required")
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError):
        _fail("invalid bounded JSON")


def _closed(value, keys):
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != keys:
        _fail("invalid closed packet schema")


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _source_hashes(source_hashes, structure_sha=None):
    if type(source_hashes) is not dict or not 3 <= len(source_hashes) <= 8:
        _fail("invalid source hash inventory")
    for key, value in source_hashes.items():
        if (type(key) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", key) is None
                or not _hash(value)):
            _fail("invalid source hash label or value")
    if any(source_hashes.get(key) != value for key, value in FROZEN_SOURCE_HASHES.items()):
        _fail("frozen scorer source mismatch")
    if not _hash(source_hashes.get("structure.json")):
        _fail("missing structure source binding")
    if source_hashes["structure.json"] != FROZEN_STRUCTURE_SHA256:
        _fail("frozen structure source mismatch")
    if structure_sha is not None and source_hashes["structure.json"] != structure_sha:
        _fail("structure source hash mismatch")


def _identities(rows):
    """Retain every unique native ID; never select an ambiguous ticker mapping."""
    validated = raw_revision._rows(rows, raw_revision._IDENTITY, 4096)
    mapping, ambiguous = raw_revision._identity_map(validated, raw_revision.SHARADAR_IDENTITY_POLICY)
    by_id = defaultdict(list)
    for row in validated:
        if type(row["security_id"]) is not str or not raw_revision._native_id(row["security_id"]):
            _fail("unaddressable source security identity")
        by_id[row["security_id"]].append(row)
    result = []
    for sid, alternatives in sorted(by_id.items()):
        tickers = {row["ticker"] for row in alternatives}
        if len(tickers) != 1:
            # One ID cannot occupy two unique-ID packet rows or pick one alias.
            _fail("one source security identity has conflicting tickers")
        ticker = next(iter(tickers))
        candidates = mapping[ticker]
        if len(candidates) != 1 or ticker in ambiguous:
            reason = "ambiguous_snapshot_identity"
        else:
            reason = raw_revision._identity_reason(next(iter(candidates.values())),
                                                  raw_revision.SHARADAR_IDENTITY_POLICY)
        result.append({"security_id": sid, "ticker": ticker,
                       "eligible": reason is None, "reason": reason or "eligible_snapshot_identity"})
    return result


def build_signal_packet(structure_payload, *, freeze_payload, source_hashes):
    """Build from exactly bound, already authorized bytes, without reading I/O.

    Declared code hashes are content bindings, not independent proof of how
    these bytes were executed. The calling run must independently hash code.
    """
    if type(freeze_payload) is not bytes or _digest(freeze_payload) != FREEZE_SHA256:
        _fail("six-universe freeze identity mismatch")
    freeze = _load(freeze_payload, 65_536)
    if (type(freeze) is not dict or freeze.get("schema") != "tpr-qc-six-universe-freeze-v1"
            or freeze.get("family_id") != FAMILY_ID
            or freeze.get("signal", {}).get("view") != "censored-last-touch"):
        _fail("six-universe frozen policy mismatch")
    if type(structure_payload) is not bytes or not 0 < len(structure_payload) <= MAX_SOURCE_BYTES:
        _fail("bounded source bytes required")
    source_sha = _digest(structure_payload)
    if source_sha != freeze["signal"]["source_structure_sha256"]:
        _fail("frozen source structure identity mismatch")
    _source_hashes(source_hashes, source_sha)
    structure = _load(structure_payload, MAX_SOURCE_BYTES)
    try:
        planned = raw_candidate.plan_target_frames(structure)
        identities = _identities(structure["identities"])
        if planned["policy"] != raw_candidate.policy() or planned["policy"]["view"] != "censored":
            _fail("raw scorer policy mismatch")
        if tuple(row["session_id"] for row in planned["frames"]) != SESSIONS:
            _fail("frozen fourteen-session schedule mismatch")
        if len(planned["normalization"]) != len(SESSIONS):
            _fail("missing score frame")
        expected_ids = {row["security_id"] for row in identities}
        event_axis = [{"session_date": row["session_date"], "open_utc": row["open_utc"]}
                      for row in structure["calendar"]]
        frames = []
        for target, evidence in zip(planned["frames"], planned["normalization"]):
            if (target["session_id"] != evidence["session_id"]
                    or len(target["weights"]) != len(expected_ids)
                    or {row["security_id"] for row in target["weights"]} != expected_ids):
                _fail("incomplete planner identity frame")
            score_map = {}
            for row in evidence["scores"]:
                sid = row["security_id"]
                if sid in score_map or sid not in expected_ids:
                    _fail("ambiguous or foreign score identity")
                score_map[sid] = row["score"]
            normalized = raw_revision.normalize_raw_revisions(
                structure["ratings"], structure["identities"], structure["actions"], event_axis,
                cutoff_utc=target["cutoff_utc"], capture_utc=structure["capture_utc"],
                view="censored", action_inventory_complete=True,
                identity_policy=raw_revision.SHARADAR_IDENTITY_POLICY,
                action_policy=raw_revision.NOMINAL_ACTION_POLICY,
            )
            by_ticker = defaultdict(set)
            for disposition in normalized.dispositions:
                if disposition.ticker is not None:
                    by_ticker[disposition.ticker].add(disposition.reason)
            states = []
            for identity in identities:
                sid, ticker = identity["security_id"], identity["ticker"]
                reasons = by_ticker[ticker] - {"accepted_proxy_revision"}
                score = None
                if not identity["eligible"]:
                    state, reasons = "identity_ineligible", {identity["reason"]}
                elif sid in score_map:
                    state, score = "scored", score_map[sid]
                elif not by_ticker[ticker]:
                    state, reasons = "unknown_input", {"no_source_rating_rows"}
                elif reasons - _NO_ADMISSIBLE:
                    state = "unknown_input"
                else:
                    state = "no_admissible_event"
                    if not reasons:
                        reasons = {"no_event_in_frozen_score_window"}
                states.append({"security_id": sid, "state": state, "score": score,
                               "reasons": sorted(reasons)})
            frames.append({"session": target["session_id"], "cutoff_utc": target["cutoff_utc"], "states": states})
    except (ValueError, KeyError, TypeError, IndexError, InvalidOperation):
        _fail("source or score framing refused")
    packet = {"schema": "tpr-qc-six-signals-v1", "candidate_id": FAMILY_ID,
              "freeze_sha256": FREEZE_SHA256, "source_hashes": dict(source_hashes),
              "identities": identities, "frames": frames}
    validate_packet(packet)
    return packet


def validate_packet(packet):
    """Closed structural validation, not authentication of provider facts."""
    _closed(packet, {"schema", "candidate_id", "freeze_sha256", "source_hashes", "identities", "frames"})
    if (packet["schema"] != "tpr-qc-six-signals-v1" or packet["candidate_id"] != FAMILY_ID
            or packet["freeze_sha256"] != FREEZE_SHA256):
        _fail("packet frozen policy mismatch")
    _source_hashes(packet["source_hashes"])
    identities, eligible_tickers = {}, set()
    if type(packet["identities"]) is not list or not 0 < len(packet["identities"]) <= 4096:
        _fail("invalid packet identity inventory")
    for row in packet["identities"]:
        _closed(row, {"security_id", "ticker", "eligible", "reason"})
        if (type(row["security_id"]) is not str or not raw_revision._native_id(row["security_id"])
                or not raw_revision._ticker(row["ticker"]) or type(row["eligible"]) is not bool
                or not _reason(row["reason"]) or row["security_id"] in identities):
            _fail("invalid or duplicate packet identity")
        if row["eligible"]:
            if row["ticker"] in eligible_tickers:
                _fail("ambiguous eligible ticker mapping")
            eligible_tickers.add(row["ticker"])
        identities[row["security_id"]] = row
    if type(packet["frames"]) is not list or len(packet["frames"]) != len(SESSIONS):
        _fail("invalid fourteen-frame inventory")
    prior_cutoff = None
    for frame, day, expected_cutoff in zip(packet["frames"], SESSIONS, CUTOFFS):
        _closed(frame, {"session", "cutoff_utc", "states"})
        if frame["session"] != day or type(frame["cutoff_utc"]) is not str:
            _fail("packet session schedule mismatch")
        try:
            cutoff = datetime.fromisoformat(frame["cutoff_utc"].replace("Z", "+00:00"))
            if (cutoff.utcoffset() is None or cutoff.date().isoformat() >= day
                    or cutoff != datetime.fromisoformat(expected_cutoff)
                    or (prior_cutoff is not None and cutoff <= prior_cutoff)):
                _fail("invalid packet cutoff")
        except (ValueError, TypeError):
            _fail("invalid packet cutoff")
        prior_cutoff = cutoff
        if type(frame["states"]) is not list or len(frame["states"]) != len(identities):
            _fail("incomplete identity states")
        seen = set()
        for row in frame["states"]:
            _closed(row, {"security_id", "state", "score", "reasons"})
            sid, state = row["security_id"], row["state"]
            if type(sid) is not str or sid not in identities or sid in seen or type(state) is not str or state not in _STATES:
                _fail("invalid or duplicate score state")
            seen.add(sid)
            if (type(row["reasons"]) is not list or len(row["reasons"]) > 64
                    or any(not _reason(reason) for reason in row["reasons"])
                    or len(set(row["reasons"])) != len(row["reasons"])):
                _fail("invalid state reasons")
            eligible = identities[sid]["eligible"]
            if (state == "identity_ineligible") != (not eligible):
                _fail("identity eligibility state mismatch")
            if state == "scored":
                if (type(row["score"]) is not str or not 0 < len(row["score"]) <= 128
                        or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?(?:E[+-]?[0-9]+)?", row["score"]) is None):
                    _fail("invalid score text")
                try:
                    score = Decimal(row["score"])
                except InvalidOperation:
                    _fail("invalid score text")
                if (not score.is_finite() or score.copy_abs() > Decimal(100_000)
                        or not -128 <= score.as_tuple().exponent <= 128):
                    _fail("nonfinite or out-of-bound score")
            elif row["score"] is not None or not row["reasons"]:
                _fail("missing state cannot masquerade as zero score")
    if len(canonical_json(packet)) > MAX_PACKET_BYTES:
        _fail("packet exceeds byte bound")


def _reason(value):
    return type(value) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,95}", value) is not None


def package_signal_packet(packet):
    """Return plaintext JSON and its identity for private Object Store upload.

    No encoded, compressed or executable data modules are produced. The
    caller must use the frozen lane-owned object key and verify cloud bytes.
    """
    validate_packet(packet)
    payload = canonical_json(packet)
    return {"payload": payload, "sha256": _digest(payload)}
