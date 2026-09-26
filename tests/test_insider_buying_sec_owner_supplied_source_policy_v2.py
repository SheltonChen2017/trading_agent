"""Exact-policy and dangerous-direction checks for the retained-context epoch."""
from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from data.hashing import canonical_json
from research.insider_buying import sec_owner_supplied_source_policy as v1
from research.insider_buying import sec_owner_supplied_source_policy_v2 as v2


POLICY = v2.CANONICAL_IB2_SOURCE_POLICY_V2
EXPECTED_SHA256 = "556dd4f74e4fadadba69fa917758868ad955af4cbc4e8b988a98d454e599c580"
PRIOR_SHA256 = "eec42a1e34b6200e0e195a6702307a5c716c10c40dbfd8e9e8095846c79e7dbe"
FIELD_NAMES = tuple(item.name for item in fields(v2.CanonicalIb2SourcePolicyV2))
REVISION_CONSTANTS = (
    ("version", "CANONICAL_IB2_SOURCE_POLICY_V2_VERSION"),
    ("schema", "CANONICAL_IB2_SOURCE_POLICY_V2_SCHEMA"),
    ("directive_id", "CANONICAL_IB2_SOURCE_V2_DIRECTIVE_ID"),
    ("directive_commit", "CANONICAL_IB2_SOURCE_V2_DIRECTIVE_COMMIT"),
    ("directive_effective_date", "CANONICAL_IB2_SOURCE_V2_EFFECTIVE_DATE"),
    ("context_document_types", "CANONICAL_IB2_SOURCE_V2_CONTEXT_DOCUMENT_TYPES"),
    ("supersedes_policy_sha256", "CANONICAL_IB2_SOURCE_V2_SUPERSEDES_SHA256"),
    ("evidence_epoch_id", "CANONICAL_IB2_SOURCE_V2_EVIDENCE_EPOCH"),
)


class _String(str):
    pass


class _Date(date):
    pass


class _Integer(int):
    pass


class _Tuple(tuple):
    pass


class _NoneEqual:
    def __eq__(self, other: object) -> bool:
        return other is None


def _changed(name: str) -> object:
    value = getattr(POLICY, name)
    if type(value) is str:
        return value + "-changed"
    if type(value) is date:
        return value + timedelta(days=1)
    if type(value) is tuple:
        return (*value, "changed")
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    assert value is None
    return "bound"


def _wrong_type(name: str) -> object:
    value = getattr(POLICY, name)
    if type(value) is str:
        return _String(value)
    if type(value) is date:
        return _Date(value.year, value.month, value.day)
    if type(value) is tuple:
        return _Tuple(value)
    if type(value) is bool:
        return int(value)
    if type(value) is int:
        return _Integer(value)
    assert value is None
    return _NoneEqual()


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256((canonical_json(payload) + "\n").encode("utf-8")).hexdigest()


def test_v2_has_exact_revision_and_preserves_every_v1_field() -> None:
    assert type(POLICY) is v2.CanonicalIb2SourcePolicyV2
    assert len(fields(v1.CanonicalIb2SourcePolicy)) == 99
    assert len(FIELD_NAMES) == 101
    differences = {name for name, _ in REVISION_CONSTANTS[:6]}
    for item in fields(v1.CanonicalIb2SourcePolicy):
        if item.name not in differences:
            assert getattr(POLICY, item.name) == getattr(v1.CANONICAL_IB2_SOURCE_POLICY, item.name)
            assert type(getattr(POLICY, item.name)) is type(getattr(v1.CANONICAL_IB2_SOURCE_POLICY, item.name))
    assert POLICY.version == "INSETF-IB2-CANONICAL-SOURCE-POLICY-v2"
    assert POLICY.schema == "insider-buying-canonical-source-policy-v2"
    assert POLICY.directive_commit == "7e61d186b39520f87318e0608463bf1a0b35cea4"
    assert POLICY.directive_effective_date == date(2026, 9, 25)
    assert POLICY.context_document_types == ("3", "3/A", "5", "5/A")
    assert POLICY.accession_document_types == ("4", "4/A")
    assert POLICY.required_accession_artifacts == ("acceptance_metadata", "complete_primary_ownership_xml")
    assert POLICY.supersedes_policy_sha256 == PRIOR_SHA256
    assert POLICY.evidence_epoch_id == "insider-buying-ib2-source-v2-context-amendments-2026-09-25"


def test_v2_literal_digest_and_revision_metadata() -> None:
    payload = POLICY.to_payload()
    assert _digest(payload) == EXPECTED_SHA256
    assert POLICY.semantic_sha256 == EXPECTED_SHA256
    assert v2.CANONICAL_IB2_SOURCE_POLICY_V2_SHA256 == EXPECTED_SHA256
    assert payload["revision"] == {
        "evidence_epoch_id": POLICY.evidence_epoch_id,
        "supersedes_policy_sha256": PRIOR_SHA256,
        "context_document_types_retained_verbatim": ["3", "3/A", "5", "5/A"],
        "context_role": "retained-only-never-candidates-signals-scoring-or-selected-names",
        "context_accession_artifact_pairs_required": False,
    }
    assert POLICY.real_artifact_read_authorized is False
    assert POLICY.canonical_ib2_complete is False
    assert POLICY.authorized_outcome_looks == POLICY.consumed_outcome_looks == 0
    assert POLICY.trading_authority is False


@pytest.mark.parametrize("name", FIELD_NAMES)
def test_every_field_change_is_refused(name: str) -> None:
    with pytest.raises(v1.CanonicalIb2SourcePolicyError, match="REFUSED"):
        replace(POLICY, **{name: _changed(name)})


@pytest.mark.parametrize("name", FIELD_NAMES)
def test_every_field_requires_exact_type(name: str) -> None:
    with pytest.raises(v1.CanonicalIb2SourcePolicyError, match="REFUSED"):
        replace(POLICY, **{name: _wrong_type(name)})


@pytest.mark.parametrize("name", FIELD_NAMES)
def test_every_field_is_in_the_semantic_hash(name: str) -> None:
    forged = copy.copy(POLICY)
    object.__setattr__(forged, name, _changed(name))
    assert _digest(forged.to_payload()) != EXPECTED_SHA256


@pytest.mark.parametrize("name,constant", REVISION_CONSTANTS)
def test_coherent_revision_constant_rebinding_is_refused(
    monkeypatch: pytest.MonkeyPatch, name: str, constant: str
) -> None:
    monkeypatch.setattr(v2, constant, _changed(name))
    monkeypatch.setattr(v2, "CANONICAL_IB2_SOURCE_POLICY_V2_SHA256", "0" * 64)
    with pytest.raises(v1.CanonicalIb2SourcePolicyError, match="semantic fingerprint"):
        replace(POLICY, **{name: _changed(name)})


@pytest.mark.parametrize("name,constant", REVISION_CONSTANTS)
def test_same_value_subclass_and_constant_rebinding_are_refused(
    monkeypatch: pytest.MonkeyPatch, name: str, constant: str
) -> None:
    changed = _wrong_type(name)
    monkeypatch.setattr(v2, constant, changed)
    with pytest.raises(v1.CanonicalIb2SourcePolicyError, match="owner-approved"):
        replace(POLICY, **{name: changed})


def test_context_tuple_elements_must_be_exact_strings() -> None:
    with pytest.raises(v1.CanonicalIb2SourcePolicyError, match="exact string"):
        replace(POLICY, context_document_types=("3", _String("3/A"), "5", "5/A"))


def test_subclass_policy_is_not_the_exact_contract() -> None:
    class Derived(v2.CanonicalIb2SourcePolicyV2):
        pass

    with pytest.raises(v1.CanonicalIb2SourcePolicyError, match="exact canonical"):
        Derived()


def test_policy_frozen_payload_fresh_and_prior_epoch_untouched() -> None:
    with pytest.raises(FrozenInstanceError):
        POLICY.evidence_epoch_id = "changed"  # type: ignore[misc]
    first = POLICY.to_payload()
    first["revision"]["context_document_types_retained_verbatim"].clear()
    first["accession_evidence"]["context_document_types"].append("4")
    first["authority"]["trading_authority"] = True
    assert POLICY.semantic_sha256 == EXPECTED_SHA256
    assert v1.CANONICAL_IB2_SOURCE_POLICY.context_document_types == ("3", "5")
    assert v1.CANONICAL_IB2_SOURCE_POLICY.version == "INSETF-IB2-CANONICAL-SOURCE-POLICY-v1"
    assert v1.CANONICAL_IB2_SOURCE_POLICY.semantic_sha256 == PRIOR_SHA256
    assert v1.CANONICAL_IB2_SOURCE_POLICY_SHA256 == PRIOR_SHA256
    assert "revision" not in v1.CANONICAL_IB2_SOURCE_POLICY.to_payload()


def test_module_has_no_io_or_execution_surface() -> None:
    source = Path(v2.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert roots == {"__future__", "dataclasses", "datetime", "data", "research"}
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    forbidden = {"open", "read_bytes", "read_text", "write_bytes", "write_text", "connect", "urlopen", "request", "submit_order"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            assert name not in forbidden
