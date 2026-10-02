"""Pure, inert v4 partition proposal; not a stopped-root replay or executor.

Inputs are caller-supplied descriptors, not independently verified receipts.
Historical blob binding checks exact bytes but never executes historical code.
No transport, artifact loader, output directory, or publication API exists here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload


V4_PLAN_VERSION = "INSETF-IB1B-OFFLINE-CUSTODY-PLAN-v4"
HISTORICAL_COMMIT = "aa0d635d00b64825bf8003289e0a60279bd52e73"
HISTORICAL_FILES = (
    ("research/insider_buying_sec_all_form4_parent_recovery_union.py",
     "67a72b5cfd3be3ae9b1fc938a241da74df0a57979ca1a114d13122b675848a48"),
    ("research/insider_buying_sec_all_form4_parent_campaign.py",
     "33f2a54944b8f5674ae92c77c4a17ff03e6455ffcf7c0d07d377945e8dbad551"),
    ("research/insider_buying/sec_complete_submission.py",
     "d15ed661d32f13fd1f3644106bd6a21c428605b1a001d58ea5fc6a3319af63a6"),
    ("research/insider_buying/sec_raw_parent_projection.py",
     "d5631b6a2684e30061be1753e00e7f50f56690643537a9d67e34e228dd20578b"),
)
HISTORICAL_VALIDATOR_SHA256 = "e47d595ee62fe30c1b9823d9db4d2219160af5e182aa16d8a9ed4b658eb7f0ee"
OBSERVED_REQUEST_INVENTORY = "20479412fa9d9e931768180eacad84748ef707cc6d9c13323b1eef91120b5fba"
OBSERVED_SOURCE_ASSIGNMENT = "9c497cabeff43a40f01b8da916264cc140088a356dc18233c660e91d7a6552d2"
OBSERVED_LATER_INVENTORY = "2318bafbe7eec167b545b747ce5a7923fcb5dbef34bd38aca27c95bd3d7f52b8"
OBSERVED_PARTIAL_ANCHORS = {
    "root_plan_sha256": "f8f1d26f93f9f7e5a5fa90c0867231519b0c6c791cdc0cdc50cc165072889f41",
    "source_plan_sha256": "e921fc09c7de9c1eab3d16bf5c8ea8a9bfceb00b7a325f9065322df264f0916e",
    "pending_shard_journal_sha256": "3decc20fec36eb7bcebdf57893cc1194e0df5414f1a3143f4d0de18a5ffda6ae",
    "pending_attempt_start_sha256": "789f9595c35cf44a5974bbf62a20011480f6cb50387fa7dc142316a9a95ebb4b",
    "pending_shard_inventory_sha256": "fc5a4222395614cc0bc742fcdfe4c0c58e93e9ee8a7974047b8408ffee9b6736",
}
OBSERVED_DIAGNOSTIC_ANCHORS = {
    "report_sha256": "206e6db9677fb169455f62357ce966384926080b6eba582094e9536e88d705b7",
    "body_sha256": "61c9b1bee6d9b365cb7f5363b30969382def65f5e652f2f63722348db465ce1c",
    "diagnostic_capture_git_commit": "b5a140816eeaa05c6178fa544d00fa7028e4a9d9",
    "body_size_bytes": 7373,
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_REQUEST_KEYS = frozenset({
    "period", "accession_number", "form_type", "filing_date", "issuer_cik",
    "archive_path", "submission_row_id", "parsed_lineage_hash",
    "master_source_sha256", "url",
})
_PARTIAL_HASHES = (
    "pending_request_sha256", "root_plan_sha256", "source_plan_sha256",
    "pending_shard_inventory_sha256", "pending_shard_journal_sha256",
    "pending_attempt_start_sha256", "source_assignment_sha256",
)
_PARTIAL_INTS = ("pending_global_index", "pending_attempt_number", "completed_new_count", "attempt_count")
_DIAGNOSTIC_HASHES = (
    "report_sha256", "ambiguous_request_sha256", "original_pending_start_sha256",
    "v3_root_plan_sha256", "v3_source_plan_sha256", "v3_source_assignment_sha256",
    "pending_shard_inventory_sha256", "pending_shard_journal_sha256", "body_sha256",
)
_TOKEN = object()


class RecoveryV4PlanError(ValueError):
    """Malformed or conflicting offline inputs refused."""


def _refuse(reason: str) -> None:
    raise RecoveryV4PlanError(f"REFUSED: {reason}")


def _sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class _SealedPayload:
    _raw: bytes = field(repr=False)
    _sha256: str
    _token: object = field(repr=False, compare=False)
    _factory_raw: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def to_payload(self) -> dict[str, object]:
        if (type(self) is not _SealedPayload or self._token is not _TOKEN
                or type(self._raw) is not bytes or self._raw != self._factory_raw
                or hash_bytes(self._raw) != self._sha256):
            _refuse("offline payload was not built here or was altered")
        return json.loads(self._raw)

    @property
    def sha256(self) -> str:
        self.to_payload()
        return self._sha256


def _seal(body: dict[str, object]) -> _SealedPayload:
    raw = canonical_json(body).encode("utf-8")
    result = _SealedPayload(raw, hash_bytes(raw), _TOKEN)
    object.__setattr__(result, "_factory_raw", raw)
    return result


def bind_v3_historical_validator(
    commit: str, blobs: tuple[tuple[str, bytes], ...],
) -> _SealedPayload:
    """Require the exact four ordered blobs; commit label is not Git attestation."""
    if (commit != HISTORICAL_COMMIT or type(commit) is not str
            or type(blobs) is not tuple or len(blobs) != len(HISTORICAL_FILES)):
        _refuse("historical validator commit or blob inventory differs")
    files = []
    for item, (path, expected) in zip(blobs, HISTORICAL_FILES, strict=True):
        if (type(item) is not tuple or len(item) != 2 or type(item[0]) is not str
                or item[0] != path or type(item[1]) is not bytes
                or hash_bytes(item[1]) != expected):
            _refuse("historical validator bytes differ")
        files.append({"path": path, "sha256": expected})
    if hash_payload(files) != HISTORICAL_VALIDATOR_SHA256:
        _refuse("historical validator aggregate differs")
    return _seal({
        "kind": V4_PLAN_VERSION + "/historical-validator-binding",
        "commit": commit, "files": files, "validator_sha256": hash_payload(files),
        "git_provenance_verified": False, "historical_code_executed": False,
        "historical_root_replayed": False,
    })


def _request_payload(value: object) -> dict[str, str]:
    if (type(value) is not dict or set(value) != _REQUEST_KEYS
            or any(type(item) is not str for item in value.values())):
        _refuse("request schema differs")
    accession, cik = value["accession_number"], value["issuer_cik"]
    if (_ACCESSION.fullmatch(accession) is None or _CIK.fullmatch(cik) is None
            or int(cik) == 0 or value["form_type"] not in {"4", "4/A"}
            or value["period"] not in {"2022Q4", "2023Q1"}
            or any(not _sha(value[name]) for name in (
                "submission_row_id", "parsed_lineage_hash", "master_source_sha256",
            ))):
        _refuse("request source identity differs")
    filed = date.fromisoformat(value["filing_date"])
    if filed.isoformat() != value["filing_date"] or f"{filed.year}Q{(filed.month - 1) // 3 + 1}" != value["period"]:
        _refuse("request filing date differs from frozen quarter")
    # Archive CIK may be an owner, not the issuer; never compare the two.
    if (re.fullmatch(r"edgar/data/[0-9]{1,10}/" + re.escape(accession) + r"\.txt", value["archive_path"]) is None
            or int(value["archive_path"].split("/")[2]) == 0
            or value["url"] != "https://www.sec.gov/Archives/" + value["archive_path"]):
        _refuse("request locator differs")
    return dict(value)


def _require_observed_anchors(p: dict[str, object], d: dict[str, object]) -> None:
    if (any(p[name] != value for name, value in OBSERVED_PARTIAL_ANCHORS.items())
            or any(d[name] != value for name, value in OBSERVED_DIAGNOSTIC_ANCHORS.items())):
        _refuse("frozen observed custody anchors differ")


def build_recovery_v4_offline_plan(
    requests: tuple[dict[str, str], ...], original_classes: tuple[str, ...],
    partial_descriptor: dict[str, object], diagnostic_descriptor: dict[str, object],
    historical_binding: _SealedPayload, *, scope: str = "observed_descriptor_proposal",
) -> _SealedPayload:
    """Partition supplied inventories, without accepting custody or dispatch.

Observed scope requires the frozen 99,394 inventory hashes and scalar anchors.
Synthetic scope has a <=64-row bound and never promotes to observed evidence.
Both remain proposals: descriptors do not prove artifact bodies or journal replay.
"""
    try:
        if scope not in {"observed_descriptor_proposal", "synthetic_test"} or type(scope) is not str:
            _refuse("unknown proposal scope")
        observed = scope == "observed_descriptor_proposal"
        if (type(requests) is not tuple or type(original_classes) is not tuple
                or len(requests) != len(original_classes)
                or (len(requests) != 99394 if observed else not 3 <= len(requests) <= 64)):
            _refuse("request or ordinal denominator differs")
        if type(historical_binding) is not _SealedPayload:
            _refuse("historical byte binding is required")
        binding = historical_binding.to_payload()
        if (binding.get("kind") != V4_PLAN_VERSION + "/historical-validator-binding"
                or binding.get("validator_sha256") != HISTORICAL_VALIDATOR_SHA256):
            _refuse("historical byte binding has the wrong kind")
        originals = [_request_payload(item) for item in requests]
        accessions = [item["accession_number"] for item in originals]
        if len(set(accessions)) != len(accessions):
            _refuse("duplicate source accession")
        if any(type(item) is not str or item not in {
            "prior_completed", "offline_corrected_diagnostic", "remaining_selected_reuse", "later_unattempted",
        } for item in original_classes):
            _refuse("unknown original source class")
        prior = original_classes.count("prior_completed")
        if (original_classes[:prior] != ("prior_completed",) * prior
                or original_classes.count("offline_corrected_diagnostic") != 1
                or original_classes[prior] != "offline_corrected_diagnostic"):
            _refuse("original completed prefix or diagnostic ordinal differs")
        later = [index for index, item in enumerate(original_classes) if item == "later_unattempted"]
        assignment_sha = hash_payload(list(original_classes))
        inventory_sha = hash_payload(originals)
        later_sha = hash_payload([originals[index] for index in later])
        if type(partial_descriptor) is not dict or type(diagnostic_descriptor) is not dict:
            _refuse("partial or diagnostic descriptor type differs")
        p, d = dict(partial_descriptor), dict(diagnostic_descriptor)
        if (set(p) != set(_PARTIAL_HASHES + _PARTIAL_INTS)
                or any(not _sha(p[name]) for name in _PARTIAL_HASHES)
                or any(type(p[name]) is not int or p[name] < 0 for name in _PARTIAL_INTS)
                or set(d) != set(_DIAGNOSTIC_HASHES) | {
                    "diagnostic_capture_git_commit", "pending_global_index", "body_size_bytes",
                } or any(not _sha(d[name]) for name in _DIAGNOSTIC_HASHES)
                or type(d["pending_global_index"]) is not int
                or type(d["body_size_bytes"]) is not int or d["body_size_bytes"] <= 0
                or type(d["diagnostic_capture_git_commit"]) is not str
                or _COMMIT.fullmatch(d["diagnostic_capture_git_commit"]) is None):
            _refuse("partial or diagnostic descriptor schema differs")
        completed = p["completed_new_count"]
        if (completed >= len(later) or p["pending_attempt_number"] != 1
                or p["attempt_count"] != completed + 1
                or p["pending_global_index"] != later[completed]
                or p["pending_request_sha256"] != hash_payload(originals[later[completed]])
                or p["source_assignment_sha256"] != assignment_sha):
            _refuse("ambiguous start differs from ordered original inventory")
        for diagnostic_key, partial_key in (
            ("ambiguous_request_sha256", "pending_request_sha256"),
            ("original_pending_start_sha256", "pending_attempt_start_sha256"),
            ("v3_root_plan_sha256", "root_plan_sha256"),
            ("v3_source_plan_sha256", "source_plan_sha256"),
            ("v3_source_assignment_sha256", "source_assignment_sha256"),
            ("pending_shard_inventory_sha256", "pending_shard_inventory_sha256"),
            ("pending_shard_journal_sha256", "pending_shard_journal_sha256"),
            ("pending_global_index", "pending_global_index"),
        ):
            if d[diagnostic_key] != p[partial_key]:
                _refuse("diagnostic is not bound to the original ambiguous start")
        if observed and (
            inventory_sha != OBSERVED_REQUEST_INVENTORY or assignment_sha != OBSERVED_SOURCE_ASSIGNMENT
            or later_sha != OBSERVED_LATER_INVENTORY or prior != 9539
            or original_classes.count("remaining_selected_reuse") != 8139
            or completed != 1846 or len(later[completed + 1:]) != 79868
        ):
            _refuse("frozen observed inventory or custody anchors differ")
        if observed:
            _require_observed_anchors(p, d)
        classes = list(original_classes)
        for index in later[:completed]:
            classes[index] = "v3_completed"
        classes[later[completed]] = "accepted_ambiguous_diagnostic"
        for index in later[completed + 1:]:
            classes[index] = "originally_unattempted"
        partition = [{"global_index": index, "request_sha256": hash_payload(request), "source_class": classes[index]}
                     for index, request in enumerate(originals)]
        eligible = [row for row in partition if row["source_class"] == "originally_unattempted"]
        return _seal({
            "kind": V4_PLAN_VERSION, "evidence_epoch": V4_PLAN_VERSION + "-proposal",
            "scope": scope, "source_window": ["2022Q4", "2023Q1"],
            "total_parents": len(partition), "request_inventory_sha256": inventory_sha,
            "original_source_assignment_sha256": assignment_sha,
            "original_later_inventory_sha256": later_sha,
            "partition": partition, "partition_sha256": hash_payload(partition),
            "class_counts": {name: classes.count(name) for name in (
                "prior_completed", "offline_corrected_diagnostic", "remaining_selected_reuse",
                "v3_completed", "accepted_ambiguous_diagnostic", "originally_unattempted",
            )},
            "proposed_unattempted_inventory": eligible,
            "proposed_unattempted_inventory_sha256": hash_payload(eligible),
            "partial_descriptor_sha256": hash_payload(p), "diagnostic_descriptor_sha256": hash_payload(d),
            "historical_binding_sha256": historical_binding.sha256,
            "stopped_v3_disposition": "preserved_unresolved_not_resumable",
            "authority": {
                "caller_supplied_descriptors": True, "custody_replayed": False,
                "historical_root_replay_implemented": False, "historical_code_executed": False,
                "transport_implemented": False, "dispatch_enabled": False, "output_written": False,
                "source_authenticated": False, "complete_corpus": False,
                "official_acceptance_verified": False, "publication_time_verified": False,
                "point_in_time_data": False, "rights_verified": False, "canonical_evidence": False,
                "qc_authorized": False, "backtest_authorized": False, "execution_authorized": False,
                "sec_dispatches": 0, "outcome_looks": 0, "qc_jobs": 0,
            },
        })
    except RecoveryV4PlanError:
        raise
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, RecursionError) as exc:
        raise RecoveryV4PlanError("REFUSED: offline proposal inputs failed validation") from exc
