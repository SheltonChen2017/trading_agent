"""Zero-I/O, versioned IB-2 policy admitting amended context filings only.

The immutable v1 contract remains untouched.  This revision retains Forms
3/A and 5/A verbatim alongside 3 and 5; none is a candidate, signal, scoring
input, or selected name.  Only Form 4 and 4/A require metadata/XML pairs.
The new evidence epoch grants no additional data or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date

from data.hashing import canonical_json, hash_bytes
from research.insider_buying.sec_owner_supplied_source_policy import (
    CanonicalIb2SourcePolicy,
    CanonicalIb2SourcePolicyError,
)


CANONICAL_IB2_SOURCE_POLICY_V2_VERSION = "INSETF-IB2-CANONICAL-SOURCE-POLICY-v2"
CANONICAL_IB2_SOURCE_POLICY_V2_SCHEMA = "insider-buying-canonical-source-policy-v2"
CANONICAL_IB2_SOURCE_V2_DIRECTIVE_ID = (
    "owner-approved-canonical-ib2-context-amendments-2026-09-25"
)
CANONICAL_IB2_SOURCE_V2_DIRECTIVE_COMMIT = (
    "7e61d186b39520f87318e0608463bf1a0b35cea4"
)
CANONICAL_IB2_SOURCE_V2_EFFECTIVE_DATE = date(2026, 9, 25)
CANONICAL_IB2_SOURCE_V2_CONTEXT_DOCUMENT_TYPES = ("3", "3/A", "5", "5/A")
CANONICAL_IB2_SOURCE_V2_EVIDENCE_EPOCH = (
    "insider-buying-ib2-source-v2-context-amendments-2026-09-25"
)
CANONICAL_IB2_SOURCE_V2_SUPERSEDES_SHA256 = (
    "eec42a1e34b6200e0e195a6702307a5c716c10c40dbfd8e9e8095846c79e7dbe"
)


@dataclass(frozen=True)
class CanonicalIb2SourcePolicyV2(CanonicalIb2SourcePolicy):
    """Exact owner-approved revision; all inherited safety gates stay shut."""

    version: str = CANONICAL_IB2_SOURCE_POLICY_V2_VERSION
    schema: str = CANONICAL_IB2_SOURCE_POLICY_V2_SCHEMA
    directive_id: str = CANONICAL_IB2_SOURCE_V2_DIRECTIVE_ID
    directive_commit: str = CANONICAL_IB2_SOURCE_V2_DIRECTIVE_COMMIT
    directive_effective_date: date = CANONICAL_IB2_SOURCE_V2_EFFECTIVE_DATE
    context_document_types: tuple[str, ...] = (
        CANONICAL_IB2_SOURCE_V2_CONTEXT_DOCUMENT_TYPES
    )
    supersedes_policy_sha256: str = CANONICAL_IB2_SOURCE_V2_SUPERSEDES_SHA256
    evidence_epoch_id: str = CANONICAL_IB2_SOURCE_V2_EVIDENCE_EPOCH

    def __post_init__(self) -> None:
        if type(self) is not CanonicalIb2SourcePolicyV2:
            raise CanonicalIb2SourcePolicyError(
                "REFUSED: exact canonical IB-2 v2 policy type required"
            )
        approved_differences = (
            ("version", CANONICAL_IB2_SOURCE_POLICY_V2_VERSION),
            ("schema", CANONICAL_IB2_SOURCE_POLICY_V2_SCHEMA),
            ("directive_id", CANONICAL_IB2_SOURCE_V2_DIRECTIVE_ID),
            ("directive_commit", CANONICAL_IB2_SOURCE_V2_DIRECTIVE_COMMIT),
            ("directive_effective_date", CANONICAL_IB2_SOURCE_V2_EFFECTIVE_DATE),
            ("context_document_types", CANONICAL_IB2_SOURCE_V2_CONTEXT_DOCUMENT_TYPES),
            ("supersedes_policy_sha256", CANONICAL_IB2_SOURCE_V2_SUPERSEDES_SHA256),
            ("evidence_epoch_id", CANONICAL_IB2_SOURCE_V2_EVIDENCE_EPOCH),
        )
        for name, expected in approved_differences:
            value = getattr(self, name)
            expected_type = (
                date if name == "directive_effective_date"
                else tuple if name == "context_document_types"
                else str
            )
            if type(value) is not expected_type or value != expected:
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {name} changed from the owner-approved v2 policy"
                )
            if type(value) is tuple and any(type(item) is not str for item in value):
                raise CanonicalIb2SourcePolicyError(
                    f"REFUSED: {name} requires exact string elements"
                )

        # Reuse the exact v1 constructor to validate all unchanged fields,
        # including its independently pinned 99-field semantic fingerprint.
        # Normalize only the six explicitly authorized inherited differences.
        prior = CanonicalIb2SourcePolicy()
        inherited = {
            item.name: getattr(self, item.name)
            for item in fields(CanonicalIb2SourcePolicy)
        }
        for name, _ in approved_differences[:6]:
            inherited[name] = getattr(prior, name)
        CanonicalIb2SourcePolicy(**inherited)

        # This independent literal also rejects coherent rebinding of module
        # defaults and revision fields.  Never trust a public computed digest.
        payload = (canonical_json(self.to_payload()) + "\n").encode("utf-8")
        if hash_bytes(payload) != (
            "556dd4f74e4fadadba69fa917758868ad955af4cbc4e8b988a98d454e599c580"
        ):
            raise CanonicalIb2SourcePolicyError(
                "REFUSED: canonical IB-2 v2 source-policy semantic fingerprint changed"
            )

    def to_payload(self) -> dict[str, object]:
        """Fresh hash-bound v2 payload, retaining every inherited policy field."""

        payload = CanonicalIb2SourcePolicy.to_payload(self)
        payload["revision"] = {
            "evidence_epoch_id": self.evidence_epoch_id,
            "supersedes_policy_sha256": self.supersedes_policy_sha256,
            "context_document_types_retained_verbatim": list(self.context_document_types),
            "context_role": (
                "retained-only-never-candidates-signals-scoring-or-selected-names"
            ),
            "context_accession_artifact_pairs_required": False,
        }
        return payload


CANONICAL_IB2_SOURCE_POLICY_V2 = CanonicalIb2SourcePolicyV2()
CANONICAL_IB2_SOURCE_POLICY_V2_SHA256 = (
    "556dd4f74e4fadadba69fa917758868ad955af4cbc4e8b988a98d454e599c580"
)


__all__ = [
    "CANONICAL_IB2_SOURCE_POLICY_V2",
    "CANONICAL_IB2_SOURCE_POLICY_V2_SHA256",
    "CANONICAL_IB2_SOURCE_POLICY_V2_VERSION",
    "CANONICAL_IB2_SOURCE_V2_EVIDENCE_EPOCH",
    "CanonicalIb2SourcePolicyV2",
]
