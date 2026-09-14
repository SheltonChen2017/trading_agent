from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Callable

import pytest

import research.analyst_revisions_v2.preregistration as preregistration
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.preregistration import PreregistrationError


def _artifact_path() -> Path:
    return preregistration.INFRASTRUCTURE_LOOK_LEDGER_PATH


def _install_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> Path:
    path = tmp_path / preregistration.INFRASTRUCTURE_LOOK_LEDGER_FILENAME
    path.write_bytes(payload)
    monkeypatch.setattr(preregistration, "INFRASTRUCTURE_LOOK_LEDGER_PATH", path)
    monkeypatch.setattr(
        preregistration,
        "INFRASTRUCTURE_LOOK_LEDGER_ARTIFACT_SHA256",
        hashlib.sha256(payload).hexdigest(),
    )
    return path


def _reidentify(raw: dict[str, object]) -> None:
    raw["ledger_id"] = None
    raw["ledger_hash"] = None
    digest = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
    raw["ledger_hash"] = digest
    raw["ledger_id"] = (
        preregistration.INFRASTRUCTURE_LOOK_LEDGER_ID_PREFIX + digest[:24]
    )


def test_committed_infrastructure_look_is_exact_accounting_without_authority() -> None:
    binding = preregistration.load_infrastructure_look_ledger()
    payload = binding.payload
    raw = json.loads(payload)
    entry = raw["entries"][0]

    assert binding.path == _artifact_path().resolve(strict=True)
    assert binding.artifact_sha256 == hashlib.sha256(payload).hexdigest()
    assert binding.ledger_id == raw["ledger_id"]
    assert binding.ledger_hash == raw["ledger_hash"]
    assert raw["totals"] == {
        "confirmatory_alpha_spent": False,
        "development_evaluations_spent": 0,
        "infrastructure_research_looks_spent": 1,
        "permanent_family_looks_spent": 0,
        "prospective_permanent_looks_remaining": 1,
    }
    assert entry["operation_id"] == "arv2-qc-b5c-refusal-smoke-002"
    assert entry["conservative_research_look_count"] == 1
    assert entry["ambiguous_submission_consumes_look"] is True
    assert entry["retry_authorized"] is False
    assert entry["development_evaluation_consumed"] is False
    assert entry["permanent_family_look_consumed"] is False
    assert entry["confirmatory_alpha_consumed"] is False
    assert entry["receipt_artifact_sha256"] == (
        "6cef656b40ac988afb1d81cf81784fcfad3ca7381ccfea0baabe4e14a6740fb3"
    )
    assert entry["driver_artifact_sha256"] == (
        "b19a489aca60394a2605363be5a1963a9401c37164c5f0da41ea2d45f39b70c0"
    )
    assert entry["receipt_byte_count"] == 3639
    assert entry["driver_byte_count"] == 34882
    assert raw["capabilities"] and all(
        value is False for value in raw["capabilities"].values()
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw["totals"].__setitem__(
            "infrastructure_research_looks_spent", 0
        ),
        lambda raw: raw["totals"].__setitem__(
            "development_evaluations_spent", 1
        ),
        lambda raw: raw["totals"].__setitem__(
            "permanent_family_looks_spent", 1
        ),
        lambda raw: raw["totals"].__setitem__("confirmatory_alpha_spent", True),
        lambda raw: raw["entries"][0].__setitem__("retry_authorized", True),
        lambda raw: raw["entries"][0].__setitem__(
            "ambiguous_submission_consumes_look", False
        ),
        lambda raw: raw["entries"][0].__setitem__(
            "development_evaluation_consumed", True
        ),
        lambda raw: raw["entries"][0].__setitem__(
            "permanent_family_look_consumed", True
        ),
        lambda raw: raw["entries"][0].__setitem__(
            "confirmatory_alpha_consumed", True
        ),
        lambda raw: raw["capabilities"].__setitem__(
            "grants_provider_access", True
        ),
        lambda raw: raw["entries"].append(copy.deepcopy(raw["entries"][0])),
        lambda raw: raw.__setitem__("unexpected", False),
    ),
)
def test_self_consistent_accounting_or_authority_mutations_refuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    raw = json.loads(_artifact_path().read_bytes())
    mutate(raw)
    _reidentify(raw)
    payload = canonical_json_bytes(raw)
    _install_payload(tmp_path, monkeypatch, payload)

    with pytest.raises(PreregistrationError, match="infrastructure-look ledger"):
        preregistration.load_infrastructure_look_ledger()


@pytest.mark.parametrize("encoding", ("pretty", "bom", "duplicate"))
def test_noncanonical_or_ambiguous_ledger_bytes_refuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    encoding: str,
) -> None:
    raw = json.loads(_artifact_path().read_bytes())
    if encoding == "pretty":
        payload = (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode()
    elif encoding == "bom":
        payload = b"\xef\xbb\xbf" + canonical_json_bytes(raw)
    else:
        payload = canonical_json_bytes(raw).replace(
            b"{", b'{"schema":"duplicate",', 1
        )
    _install_payload(tmp_path, monkeypatch, payload)

    with pytest.raises(PreregistrationError, match="infrastructure-look ledger"):
        preregistration.load_infrastructure_look_ledger()


def test_missing_or_linked_ledger_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / preregistration.INFRASTRUCTURE_LOOK_LEDGER_FILENAME
    monkeypatch.setattr(
        preregistration, "INFRASTRUCTURE_LOOK_LEDGER_PATH", missing
    )
    with pytest.raises(PreregistrationError, match="infrastructure-look ledger"):
        preregistration.load_infrastructure_look_ledger()

    link = tmp_path / "linked" / preregistration.INFRASTRUCTURE_LOOK_LEDGER_FILENAME
    link.parent.symlink_to(_artifact_path().parent, target_is_directory=True)
    monkeypatch.setattr(preregistration, "INFRASTRUCTURE_LOOK_LEDGER_PATH", link)
    with pytest.raises(PreregistrationError, match="infrastructure-look ledger"):
        preregistration.load_infrastructure_look_ledger()
