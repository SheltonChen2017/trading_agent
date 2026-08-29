from __future__ import annotations

import copy
import dataclasses
import os
import subprocess
from fractions import Fraction

import pytest

from research.analyst_revisions_v2 import security_master as security_master_module
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2.firm_ontology import (
    FIRM_ONTOLOGY_SCHEMA,
    FirmOntologyError,
    load_reviewed_firm_rating_ontology,
    require_registered_production_firm_ontology,
)
from research.analyst_revisions_v2.production_registry import ProductionRegistryError
from research.analyst_revisions_v2.ratings_ingest import (
    BENZINGA_PROVIDER_CONTRACT_ID,
    BENZINGA_PROVIDER_CONTRACT_SHA256,
    audit_benzinga_snapshot,
    normalize_firm_rating_audit,
)
from research.analyst_revisions_v2.security_master import (
    PIT_SECURITY_MASTER_SCHEMA,
    CombinedRefusalStage,
    IdentityMappingRefusal,
    IdentityRefusalReason,
    LineageKind,
    PointInTimeSecurityMaster,
    ResolvedSecurityIdentity,
    SecurityMasterError,
    SecurityType,
    audit_benzinga_security_identities,
    bind_firm_normalization_to_security_identities,
    load_pit_security_master,
    require_registered_production_security_master,
    resolve_historical_security,
    revalidate_identity_resolved_firm_rating_result,
    revalidate_pit_security_master,
    revalidate_security_identity_audit,
    revalidate_terminal_outcome_requirements,
    terminal_outcome_requirements,
)
from research.analyst_revisions_v2.snapshot import load_verified_snapshot

from ._helpers import write_snapshot


EVIDENCE_HASH = "8" * 64
SOURCE_HASH = "9" * 64


def _issuer(
    issuer_id: str,
    *,
    country: str = "US",
    valid_from: str = "2010-01-01",
    valid_to: str | None = None,
    available_at: str = "2010-01-01T00:00:00.000000Z",
    valid_to_available_at: str | None = None,
):
    closure_available = (
        valid_to_available_at
        if valid_to_available_at is not None
        else None
        if valid_to is None
        else f"{valid_to}T00:00:00.000000Z"
    )
    return {
        "issuer_id": issuer_id,
        "cik": None,
        "incorporation_country": country,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "valid_to_available_at": closure_available,
        "available_at": available_at,
        "evidence_id": f"evidence-{issuer_id}",
        "evidence_sha256": EVIDENCE_HASH,
    }


def _security(
    security_id: str,
    issuer_id: str,
    share_class_id: str,
    *,
    security_type: str = "common_stock",
    valid_from: str = "2010-01-01",
    valid_to: str | None = None,
    available_at: str = "2010-01-01T00:00:00.000000Z",
    valid_to_available_at: str | None = None,
):
    closure_available = (
        valid_to_available_at
        if valid_to_available_at is not None
        else None
        if valid_to is None
        else f"{valid_to}T00:00:00.000000Z"
    )
    return {
        "security_id": security_id,
        "issuer_id": issuer_id,
        "share_class_id": share_class_id,
        "security_type": security_type,
        "isin": None,
        "figi": None,
        "vendor_ids": [
            {
                "provider": "fixture",
                "value": f"vendor-{security_id}",
                "valid_from": valid_from,
                "valid_to": valid_to,
                "valid_to_available_at": closure_available,
                "available_at": available_at,
                "evidence_id": f"vendor-evidence-{security_id}",
                "evidence_sha256": EVIDENCE_HASH,
            }
        ],
        "valid_from": valid_from,
        "valid_to": valid_to,
        "valid_to_available_at": closure_available,
        "available_at": available_at,
        "evidence_id": f"evidence-{security_id}",
        "evidence_sha256": EVIDENCE_HASH,
    }


def _listing(
    listing_id: str,
    security_id: str,
    ticker: str,
    *,
    exchange: str = "XNAS",
    country: str = "US",
    valid_from: str = "2010-01-01",
    valid_to: str | None = None,
    available_at: str = "2010-01-01T00:00:00.000000Z",
    valid_to_available_at: str | None = None,
):
    closure_available = (
        valid_to_available_at
        if valid_to_available_at is not None
        else None
        if valid_to is None
        else f"{valid_to}T00:00:00.000000Z"
    )
    return {
        "listing_id": listing_id,
        "security_id": security_id,
        "ticker": ticker,
        "exchange": exchange,
        "country": country,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "valid_to_available_at": closure_available,
        "available_at": available_at,
        "evidence_id": f"evidence-{listing_id}",
        "evidence_sha256": EVIDENCE_HASH,
    }


def _lineage(
    event_id: str,
    kind: str,
    security_id: str,
    effective_date: str,
    *,
    successor_security_id: str | None = None,
):
    return {
        "lineage_event_id": event_id,
        "kind": kind,
        "security_id": security_id,
        "effective_date": effective_date,
        "available_at": f"{effective_date}T00:00:00.000000Z",
        "successor_security_id": successor_security_id,
        "evidence_id": f"evidence-{event_id}",
        "evidence_sha256": EVIDENCE_HASH,
    }


def _master_payload(
    *,
    issuers=None,
    securities=None,
    listings=None,
    lineage_events=None,
):
    issuer_rows = issuers or [_issuer("issuer-live")]
    security_rows = securities or [
        _security("security-live", "issuer-live", "class-live")
    ]
    listing_rows = listings or [_listing("listing-live", "security-live", "LIVE")]
    lineage_rows = [] if lineage_events is None else lineage_events
    return {
        "schema": PIT_SECURITY_MASTER_SCHEMA,
        "security_master_id": "security-master-fixture-1",
        "version": "version-1",
        "created_at": "2026-08-29T00:00:00.000000Z",
        "source_id": "synthetic-fixture-source",
        "source_sha256": SOURCE_HASH,
        "issuers": sorted(issuer_rows, key=lambda item: item["issuer_id"]),
        "securities": sorted(security_rows, key=lambda item: item["security_id"]),
        "listings": sorted(
            listing_rows,
            key=lambda item: (
                item["ticker"],
                item["valid_from"],
                item["exchange"],
                item["security_id"],
                item["listing_id"],
            ),
        ),
        "lineage_events": sorted(
            lineage_rows,
            key=lambda item: (
                item["effective_date"],
                item["security_id"],
                item["lineage_event_id"],
            ),
        ),
    }


def _write_master(path, payload=None):
    path.write_bytes(canonical_json_bytes(payload or _master_payload()))
    return load_pit_security_master(path)


def _historical_payload(*, terminal_kind: str = "delisting"):
    return _master_payload(
        issuers=[
            _issuer("issuer-new", valid_from="2021-01-01"),
            _issuer("issuer-old", valid_to="2021-01-01"),
        ],
        securities=[
            _security(
                "security-new",
                "issuer-new",
                "class-new",
                valid_from="2021-01-01",
            ),
            _security(
                "security-old",
                "issuer-old",
                "class-old",
                valid_to="2021-01-01",
            ),
        ],
        listings=[
            _listing(
                "listing-old-new-symbol",
                "security-old",
                "AAA",
                valid_from="2015-01-01",
                valid_to="2021-01-01",
            ),
            _listing(
                "listing-reused-symbol",
                "security-new",
                "AAA",
                valid_from="2021-01-01",
            ),
            _listing(
                "listing-old-symbol",
                "security-old",
                "OLD",
                valid_to="2015-01-01",
            ),
        ],
        lineage_events=[
            _lineage(
                "lineage-symbol-change",
                "symbol_change",
                "security-old",
                "2015-01-01",
            ),
            _lineage(
                "lineage-terminal",
                terminal_kind,
                "security-old",
                "2021-01-01",
                successor_security_id=(
                    "security-new" if terminal_kind == "merger" else None
                ),
            ),
        ],
    )


def _resolve(master, ticker, day, known_at=None):
    return resolve_historical_security(
        master,
        historical_ticker=ticker,
        effective_date=day,
        known_at=known_at or f"{day}T23:59:59.000000Z",
    )


def _rating_row(row_id: str, ticker: str, *, date: str = "2020-01-02"):
    year = int(date[:4])
    return {
        "event_year": year,
        "benzinga_id": row_id,
        "benzinga_firm_id": "firm-1",
        "firm": "Broker One",
        "benzinga_analyst_id": "analyst-1",
        "analyst": "Analyst One",
        "date": date,
        "time": "09:31:02",
        "last_updated": f"{date}T15:01:03Z",
        "rating_action": "upgrades",
        "rating": "Buy",
        "previous_rating": "Hold",
        "ticker": ticker,
    }


def _ingest_audit(root, rows, *, year: int = 2020):
    write_snapshot(
        root,
        rows_by_year={year: rows},
        snapshot_id=f"snapshot-{root.name}",
        provider_contract_id=BENZINGA_PROVIDER_CONTRACT_ID,
        provider_contract_sha256=BENZINGA_PROVIDER_CONTRACT_SHA256,
        captured_at="2026-08-26T11:00:00.000000Z",
    )
    snapshot = load_verified_snapshot(
        root, verified_at="2026-08-28T12:00:00.000000Z"
    )
    return audit_benzinga_snapshot(snapshot)


def _ontology(path):
    entries = []
    for label, rank in (("Hold", 1), ("Buy", 2)):
        entries.append(
            {
                "provider_firm_id": "firm-1",
                "firm_name": "Broker One",
                "valid_from": "2010-01-01",
                "valid_to": None,
                "raw_label": label,
                "ordered_rank": rank,
                "scale_size": 2,
                "scope": "absolute",
                "mapping_quality": "reviewed_primary",
                "reviewer": "Independent Reviewer",
                "source_evidence_id": f"ontology-evidence-{rank}",
                "source_evidence_sha256": EVIDENCE_HASH,
            }
        )
    entries.sort(
        key=lambda item: (
            item["provider_firm_id"],
            item["valid_from"],
            "9999-12-31",
            item["ordered_rank"],
            item["raw_label"].casefold(),
            item["raw_label"],
        )
    )
    payload = {
        "schema": FIRM_ONTOLOGY_SCHEMA,
        "ontology_id": "ontology-fixture-1",
        "version": "version-1",
        "status": "reviewed",
        "reviewed_at": "2026-08-26T12:00:00.000000Z",
        "entries": entries,
    }
    path.write_bytes(canonical_json_bytes(payload))
    return load_reviewed_firm_rating_ontology(path)


def _git(repo, *arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def test_master_is_canonical_loader_authenticated_and_revalidated(tmp_path):
    path = tmp_path / "master.json"
    master = _write_master(path)
    assert master.payload_sha256
    assert revalidate_pit_security_master(master) is master

    forged = copy.copy(master)
    assert type(forged) is PointInTimeSecurityMaster
    with pytest.raises(SecurityMasterError, match="loader-authenticated"):
        revalidate_pit_security_master(forged)

    changed = _master_payload()
    changed["version"] = "version-2"
    path.write_bytes(canonical_json_bytes(changed))
    with pytest.raises(SecurityMasterError, match="hash changed"):
        revalidate_pit_security_master(master)


def test_public_resolver_reauthenticates_master_source_bytes(tmp_path):
    path = tmp_path / "master.json"
    master = _write_master(path)
    changed = _master_payload()
    changed["version"] = "version-after-load"
    path.write_bytes(canonical_json_bytes(changed))
    with pytest.raises(SecurityMasterError, match="hash changed"):
        _resolve(master, "LIVE", "2020-01-02")


def test_noncanonical_unknown_field_and_symlink_refuse(tmp_path):
    unknown = _master_payload()
    unknown["current_ticker"] = "LIVE"
    path = tmp_path / "unknown.json"
    path.write_bytes(canonical_json_bytes(unknown))
    with pytest.raises(SecurityMasterError, match="keys are not exact"):
        load_pit_security_master(path)

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text("{}", encoding="utf-8")
    with pytest.raises(SecurityMasterError, match="canonical"):
        load_pit_security_master(noncanonical)

    source = tmp_path / "source.json"
    source.write_bytes(canonical_json_bytes(_master_payload()))
    link = tmp_path / "link.json"
    try:
        os.symlink(source, link)
    except OSError:
        pytest.skip("symlink creation is not available on this Windows host")
    with pytest.raises(SecurityMasterError, match="symlink|regular file"):
        load_pit_security_master(link)


def test_loader_checks_unresolved_path_before_following_symlink(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_bytes(canonical_json_bytes(_master_payload()))
    path_type = type(source)
    original = path_type.is_symlink
    monkeypatch.setattr(
        path_type,
        "is_symlink",
        lambda self: True if self == source else original(self),
    )
    with pytest.raises(SecurityMasterError, match="must not be a symlink"):
        load_pit_security_master(source)


def test_ontology_loader_checks_unresolved_symlink_path(tmp_path, monkeypatch):
    path = tmp_path / "ontology.json"
    _ontology(path)
    path_type = type(path)
    original = path_type.is_symlink
    monkeypatch.setattr(
        path_type,
        "is_symlink",
        lambda self: True if self == path else original(self),
    )
    with pytest.raises(FirmOntologyError, match="must not be a symlink"):
        load_reviewed_firm_rating_ontology(path)


def test_symbol_change_and_ticker_reuse_resolve_by_event_date(tmp_path):
    master = _write_master(tmp_path / "master.json", _historical_payload())
    old_symbol = _resolve(master, "OLD", "2012-01-02")
    renamed = _resolve(master, "AAA", "2020-01-02")
    reused = _resolve(master, "AAA", "2022-01-02")
    assert isinstance(old_symbol, ResolvedSecurityIdentity)
    assert isinstance(renamed, ResolvedSecurityIdentity)
    assert isinstance(reused, ResolvedSecurityIdentity)
    assert old_symbol.security_id == renamed.security_id == "security-old"
    assert reused.security_id == "security-new"
    assert old_symbol.identity_mapping_evidence_sha256 != (
        renamed.identity_mapping_evidence_sha256
    )

    # A current-ticker/backfill mutation would incorrectly map this pre-rename row.
    before_rename = _resolve(master, "AAA", "2012-01-02")
    assert isinstance(before_rename, IdentityMappingRefusal)
    assert before_rename.reason is IdentityRefusalReason.NO_ACTIVE_TICKER_MAPPING


def test_same_ticker_exchange_transfer_retains_security_identity(tmp_path):
    payload = _master_payload(
        listings=[
            _listing(
                "listing-move-nasdaq",
                "security-live",
                "MOVE",
                exchange="XNAS",
                valid_to="2018-01-01",
            ),
            _listing(
                "listing-move-nyse",
                "security-live",
                "MOVE",
                exchange="XNYS",
                valid_from="2018-01-01",
            ),
        ],
        lineage_events=[
            _lineage(
                "lineage-exchange-transfer",
                "listing_change",
                "security-live",
                "2018-01-01",
            )
        ],
    )
    master = _write_master(tmp_path / "master.json", payload)
    nasdaq = _resolve(master, "MOVE", "2017-01-02")
    nyse = _resolve(master, "MOVE", "2019-01-02")
    assert isinstance(nasdaq, ResolvedSecurityIdentity)
    assert isinstance(nyse, ResolvedSecurityIdentity)
    assert nasdaq.security_id == nyse.security_id == "security-live"
    assert nasdaq.exchange == "XNAS"
    assert nyse.exchange == "XNYS"


def test_future_interval_closure_is_redacted_until_its_knowledge_time(tmp_path):
    master = _write_master(tmp_path / "master.json", _historical_payload())
    event_time = _resolve(
        master,
        "OLD",
        "2012-01-02",
        known_at="2012-01-02T23:59:59.000000Z",
    )
    after_closure_known = _resolve(
        master,
        "OLD",
        "2012-01-02",
        known_at="2016-01-02T23:59:59.000000Z",
    )
    assert isinstance(event_time, ResolvedSecurityIdentity)
    assert isinstance(after_closure_known, ResolvedSecurityIdentity)
    assert event_time.ticker_valid_to is None
    assert event_time.identity_mapping_valid_to is None
    assert after_closure_known.ticker_valid_to == "2015-01-01"
    assert after_closure_known.identity_mapping_valid_to == "2015-01-01"
    assert event_time.identity_mapping_evidence_sha256 != (
        after_closure_known.identity_mapping_evidence_sha256
    )
    assert event_time.identity_mapping_available_at == (
        "2010-01-01T00:00:00.000000Z"
    )
    assert after_closure_known.identity_mapping_available_at == (
        "2015-01-01T00:00:00.000000Z"
    )


def test_post_change_old_ticker_with_hidden_closure_is_not_future_missing(tmp_path):
    payload = _historical_payload()
    old_listing = next(
        item
        for item in payload["listings"]
        if item["listing_id"] == "listing-old-symbol"
    )
    old_listing["valid_to_available_at"] = "2018-01-01T00:00:00.000000Z"
    symbol_change = next(
        item
        for item in payload["lineage_events"]
        if item["kind"] == "symbol_change"
    )
    symbol_change["available_at"] = "2018-01-01T00:00:00.000000Z"
    master = _write_master(tmp_path / "master.json", payload)
    before_closure_known = _resolve(
        master,
        "OLD",
        "2016-01-02",
        known_at="2016-01-02T23:59:59.000000Z",
    )
    after_closure_known = _resolve(
        master,
        "OLD",
        "2019-01-02",
        known_at="2019-01-02T23:59:59.000000Z",
    )
    assert isinstance(before_closure_known, IdentityMappingRefusal)
    assert (
        before_closure_known.reason
        is IdentityRefusalReason.IDENTITY_NOT_AVAILABLE_BY_EVENT
    )
    assert isinstance(after_closure_known, IdentityMappingRefusal)
    assert (
        after_closure_known.reason
        is IdentityRefusalReason.NO_ACTIVE_TICKER_MAPPING
    )


def test_ticker_reuse_waits_for_predecessor_closure_evidence(tmp_path):
    payload = _historical_payload()
    old_reused_listing = next(
        item
        for item in payload["listings"]
        if item["listing_id"] == "listing-old-new-symbol"
    )
    old_reused_listing["valid_to_available_at"] = (
        "2025-01-01T00:00:00.000000Z"
    )
    old_security = next(
        item
        for item in payload["securities"]
        if item["security_id"] == "security-old"
    )
    old_security["valid_to_available_at"] = "2025-01-01T00:00:00.000000Z"
    old_security["vendor_ids"][0]["valid_to_available_at"] = (
        "2025-01-01T00:00:00.000000Z"
    )
    terminal = next(
        item
        for item in payload["lineage_events"]
        if item["kind"] == "delisting"
    )
    terminal["available_at"] = "2025-01-01T00:00:00.000000Z"
    master = _write_master(tmp_path / "master.json", payload)
    before_predecessor_closure = _resolve(
        master,
        "AAA",
        "2022-01-02",
        known_at="2022-01-02T23:59:59.000000Z",
    )
    after_predecessor_closure = _resolve(
        master,
        "AAA",
        "2025-01-02",
        known_at="2025-01-02T23:59:59.000000Z",
    )
    assert isinstance(before_predecessor_closure, IdentityMappingRefusal)
    assert (
        before_predecessor_closure.reason
        is IdentityRefusalReason.IDENTITY_NOT_AVAILABLE_BY_EVENT
    )
    assert isinstance(after_predecessor_closure, ResolvedSecurityIdentity)
    assert after_predecessor_closure.security_id == "security-new"


def test_share_classes_under_one_issuer_remain_distinct(tmp_path):
    payload = _master_payload(
        issuers=[_issuer("issuer-dual")],
        securities=[
            _security("security-a", "issuer-dual", "class-a"),
            _security("security-b", "issuer-dual", "class-b"),
        ],
        listings=[
            _listing("listing-a", "security-a", "DUA"),
            _listing("listing-b", "security-b", "DUB"),
        ],
    )
    master = _write_master(tmp_path / "master.json", payload)
    first = _resolve(master, "DUA", "2020-01-02")
    second = _resolve(master, "DUB", "2020-01-02")
    assert isinstance(first, ResolvedSecurityIdentity)
    assert isinstance(second, ResolvedSecurityIdentity)
    assert first.issuer_id == second.issuer_id == "issuer-dual"
    assert first.security_id != second.security_id
    assert first.share_class_id != second.share_class_id

    collapsed = copy.deepcopy(payload)
    collapsed["securities"][1]["share_class_id"] = "class-a"
    path = tmp_path / "collapsed.json"
    path.write_bytes(canonical_json_bytes(collapsed))
    with pytest.raises(SecurityMasterError, match="share_class_id"):
        load_pit_security_master(path)


@pytest.mark.parametrize("identifier_kind", ["cik", "isin", "figi", "vendor"])
def test_permanent_identifiers_cannot_be_reused_sequentially(
    tmp_path, identifier_kind
):
    payload = _historical_payload()
    if identifier_kind == "cik":
        for issuer in payload["issuers"]:
            issuer["cik"] = "0000123456"
    elif identifier_kind in {"isin", "figi"}:
        for security in payload["securities"]:
            security[identifier_kind] = "PERMANENT-ID-1"
    else:
        for security in payload["securities"]:
            security["vendor_ids"][0]["value"] = "permanent-vendor-id-1"
    path = tmp_path / f"reused-{identifier_kind}.json"
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(SecurityMasterError, match="permanent"):
        load_pit_security_master(path)


def test_cross_exchange_ticker_ambiguity_never_first_wins(tmp_path):
    payload = _master_payload(
        issuers=[_issuer("issuer-a"), _issuer("issuer-b")],
        securities=[
            _security("security-a", "issuer-a", "class-a"),
            _security("security-b", "issuer-b", "class-b"),
        ],
        listings=[
            _listing("listing-a", "security-a", "DUO", exchange="XNAS"),
            _listing("listing-b", "security-b", "DUO", exchange="XNYS"),
        ],
    )
    master = _write_master(tmp_path / "master.json", payload)
    result = _resolve(master, "DUO", "2020-01-02")
    assert isinstance(result, IdentityMappingRefusal)
    assert result.reason is IdentityRefusalReason.AMBIGUOUS_ACTIVE_TICKER_MAPPING


def test_overlapping_same_ticker_exchange_is_rejected_at_load(tmp_path):
    payload = _master_payload(
        issuers=[_issuer("issuer-a"), _issuer("issuer-b")],
        securities=[
            _security("security-a", "issuer-a", "class-a"),
            _security("security-b", "issuer-b", "class-b"),
        ],
        listings=[
            _listing("listing-a", "security-a", "DUO"),
            _listing("listing-b", "security-b", "DUO"),
        ],
    )
    path = tmp_path / "overlap.json"
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(SecurityMasterError, match="ticker/exchange"):
        load_pit_security_master(path)


@pytest.mark.parametrize("late_record", ["issuer", "security", "listing"])
def test_missing_and_late_identity_have_distinct_refusals(tmp_path, late_record):
    late = "2020-01-03T00:00:00.000000Z"
    payload = _master_payload(
        issuers=[
            _issuer(
                "issuer-live",
                available_at=(
                    late
                    if late_record == "issuer"
                    else "2010-01-01T00:00:00.000000Z"
                ),
            )
        ],
        securities=[
            _security(
                "security-live",
                "issuer-live",
                "class-live",
                available_at=(
                    late
                    if late_record == "security"
                    else "2010-01-01T00:00:00.000000Z"
                ),
            )
        ],
        listings=[
            _listing(
                "listing-live",
                "security-live",
                "LIVE",
                available_at=(
                    late
                    if late_record == "listing"
                    else "2010-01-01T00:00:00.000000Z"
                ),
            )
        ],
    )
    master = _write_master(tmp_path / "master.json", payload)
    missing = _resolve(master, "MISS", "2020-01-02")
    late = _resolve(
        master,
        "LIVE",
        "2020-01-02",
        known_at="2020-01-02T23:59:59.000000Z",
    )
    assert isinstance(missing, IdentityMappingRefusal)
    assert missing.reason is IdentityRefusalReason.NO_ACTIVE_TICKER_MAPPING
    assert isinstance(late, IdentityMappingRefusal)
    assert late.reason is IdentityRefusalReason.IDENTITY_NOT_AVAILABLE_BY_EVENT


def test_future_terminal_evidence_does_not_leak_termination_reason(tmp_path):
    payload = _historical_payload()
    terminal = next(
        item for item in payload["lineage_events"] if item["kind"] == "delisting"
    )
    terminal["available_at"] = "2025-01-01T00:00:00.000000Z"
    master = _write_master(tmp_path / "master.json", payload)
    before_evidence = _resolve(
        master,
        "OLD",
        "2022-01-02",
        known_at="2022-01-02T23:59:59.000000Z",
    )
    after_evidence = _resolve(
        master,
        "OLD",
        "2025-01-02",
        known_at="2025-01-02T23:59:59.000000Z",
    )
    assert isinstance(before_evidence, IdentityMappingRefusal)
    assert (
        before_evidence.reason
        is IdentityRefusalReason.IDENTITY_NOT_AVAILABLE_BY_EVENT
    )
    assert isinstance(after_evidence, IdentityMappingRefusal)
    assert (
        after_evidence.reason
        is IdentityRefusalReason.SECURITY_TERMINATED_BEFORE_EVENT
    )


def test_lineage_cannot_predate_mapping_or_closure_evidence(tmp_path):
    payload = _historical_payload()
    old_listing = next(
        item
        for item in payload["listings"]
        if item["listing_id"] == "listing-old-symbol"
    )
    old_listing["available_at"] = "2016-01-01T00:00:00.000000Z"
    old_listing["valid_to_available_at"] = "2016-01-01T00:00:00.000000Z"
    path = tmp_path / "early-lineage.json"
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(SecurityMasterError, match="cannot predate"):
        load_pit_security_master(path)


def test_closure_availability_is_paired_and_bounded_by_master_creation(tmp_path):
    unpaired = _master_payload()
    unpaired["listings"][0]["valid_to_available_at"] = (
        "2020-01-01T00:00:00.000000Z"
    )
    path = tmp_path / "unpaired.json"
    path.write_bytes(canonical_json_bytes(unpaired))
    with pytest.raises(SecurityMasterError, match="both be null or present"):
        load_pit_security_master(path)

    future = _master_payload()
    vendor = future["securities"][0]["vendor_ids"][0]
    vendor["valid_to"] = "2020-01-01"
    vendor["valid_to_available_at"] = "2030-01-01T00:00:00.000000Z"
    path = tmp_path / "future-closure.json"
    path.write_bytes(canonical_json_bytes(future))
    with pytest.raises(SecurityMasterError, match="cannot predate included"):
        load_pit_security_master(path)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("foreign", IdentityRefusalReason.INELIGIBLE_ISSUER_COUNTRY),
        ("listing_country", IdentityRefusalReason.INELIGIBLE_LISTING_COUNTRY),
        ("exchange", IdentityRefusalReason.INELIGIBLE_EXCHANGE),
        ("type", IdentityRefusalReason.INELIGIBLE_SECURITY_TYPE),
    ],
)
def test_frozen_universe_ineligibility_is_named(tmp_path, mutation, reason):
    issuers = [_issuer("issuer-live", country="CA" if mutation == "foreign" else "US")]
    securities = [
        _security(
            "security-live",
            "issuer-live",
            "class-live",
            security_type="reit" if mutation == "type" else "common_stock",
        )
    ]
    listings = [
        _listing(
            "listing-live",
            "security-live",
            "LIVE",
            exchange="OTCM" if mutation == "exchange" else "XNAS",
            country="CA" if mutation == "listing_country" else "US",
        )
    ]
    master = _write_master(
        tmp_path / f"{mutation}.json",
        _master_payload(issuers=issuers, securities=securities, listings=listings),
    )
    result = _resolve(master, "LIVE", "2020-01-02")
    assert isinstance(result, IdentityMappingRefusal)
    assert result.reason is reason


def test_delisting_retains_history_refuses_post_terminal_and_requires_outcome(tmp_path):
    master = _write_master(tmp_path / "master.json", _historical_payload())
    historical = _resolve(master, "OLD", "2012-01-02")
    after_delisting = _resolve(master, "OLD", "2022-01-02")
    assert isinstance(historical, ResolvedSecurityIdentity)
    assert historical.security_id == "security-old"
    assert isinstance(after_delisting, IdentityMappingRefusal)
    assert (
        after_delisting.reason
        is IdentityRefusalReason.SECURITY_TERMINATED_BEFORE_EVENT
    )
    requirements = terminal_outcome_requirements(
        master,
        start_date="2020-01-01",
        end_date="2022-01-01",
        known_at="2022-01-02T00:00:00.000000Z",
    )
    assert len(requirements) == 1
    assert requirements[0].kind is LineageKind.DELISTING
    assert requirements[0].security_id == "security-old"
    assert requirements[0].missing_policy == "named_refusal_never_drop"
    assert revalidate_terminal_outcome_requirements(
        requirements,
        master=master,
        start_date="2020-01-01",
        end_date="2022-01-01",
        known_at="2022-01-02T00:00:00.000000Z",
    ) is requirements

    with pytest.raises(SecurityMasterError, match="unavailable by known_at"):
        terminal_outcome_requirements(
            master,
            start_date="2020-01-01",
            end_date="2022-01-01",
            known_at="2020-12-31T23:59:59.000000Z",
        )


def test_merger_successor_does_not_rewrite_predecessor_history(tmp_path):
    master = _write_master(
        tmp_path / "master.json", _historical_payload(terminal_kind="merger")
    )
    historical = _resolve(master, "AAA", "2020-01-02")
    reused = _resolve(master, "AAA", "2022-01-02")
    assert isinstance(historical, ResolvedSecurityIdentity)
    assert isinstance(reused, ResolvedSecurityIdentity)
    assert historical.security_id == "security-old"
    assert reused.security_id == "security-new"
    requirement = terminal_outcome_requirements(
        master,
        start_date="2021-01-01",
        end_date="2021-01-02",
        known_at="2021-01-02T00:00:00.000000Z",
    )[0]
    assert requirement.kind is LineageKind.MERGER
    assert requirement.successor_security_id == "security-new"


@pytest.mark.parametrize("mutation", ["dangling", "self"])
def test_invalid_successor_lineage_fails_closed(tmp_path, mutation):
    payload = _historical_payload(terminal_kind="merger")
    terminal = next(
        item for item in payload["lineage_events"] if item["kind"] == "merger"
    )
    terminal["successor_security_id"] = (
        "absent-security" if mutation == "dangling" else "security-old"
    )
    path = tmp_path / f"{mutation}.json"
    path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(SecurityMasterError, match="successor"):
        load_pit_security_master(path)


def test_identity_audit_is_exhaustive_and_reports_integer_coverage(tmp_path):
    audit = _ingest_audit(
        tmp_path / "snapshot",
        [_rating_row("event-map", "LIVE"), _rating_row("event-miss", "MISS")],
    )
    master = _write_master(tmp_path / "master.json")
    identity_audit = audit_benzinga_security_identities(audit, master)
    assert len(identity_audit.mappings) == 1
    assert len(identity_audit.refusals) == 1
    assert identity_audit.coverage.total_records == 2
    assert identity_audit.coverage.mapped_records == 1
    assert identity_audit.coverage.refusal_counts == (
        (IdentityRefusalReason.NO_ACTIVE_TICKER_MAPPING, 1),
    )
    event_known_at = "2020-01-02T15:01:03.000000Z"
    public_mapping = _resolve(
        master, "LIVE", "2020-01-02", known_at=event_known_at
    )
    public_refusal = _resolve(
        master, "MISS", "2020-01-02", known_at=event_known_at
    )
    assert public_mapping == identity_audit.mappings[0].identity
    assert public_refusal == identity_audit.refusals[0].refusal
    assert revalidate_security_identity_audit(
        identity_audit, ingest_audit=audit, master=master
    ) is identity_audit

    forged = dataclasses.replace(identity_audit, mappings=())
    with pytest.raises(SecurityMasterError, match="not source-derived"):
        revalidate_security_identity_audit(
            forged, ingest_audit=audit, master=master
        )


def test_identity_and_firm_join_preserves_exact_rational_mapping(tmp_path):
    ingest = _ingest_audit(
        tmp_path / "snapshot", [_rating_row("event-map", "LIVE")]
    )
    master = _write_master(tmp_path / "master.json")
    ontology = _ontology(tmp_path / "ontology.json")
    firm_result = normalize_firm_rating_audit(ingest, ontology)
    identity_audit = audit_benzinga_security_identities(ingest, master)
    combined = bind_firm_normalization_to_security_identities(
        firm_result,
        identity_audit,
        ingest_audit=ingest,
        ontology=ontology,
        master=master,
    )
    assert len(combined.events) == 1
    assert not combined.refusals
    event = combined.events[0]
    assert event.firm_event.rating_change == Fraction(2, 1)
    assert event.identity.issuer_id == "issuer-live"
    assert event.identity.security_id == "security-live"
    assert event.identity.share_class_id == "class-live"
    assert event.identity.security_id != event.identity.issuer_id
    assert revalidate_identity_resolved_firm_rating_result(
        combined,
        firm_result=firm_result,
        identity_audit=identity_audit,
        ingest_audit=ingest,
        ontology=ontology,
        master=master,
    ) is combined

    forged = dataclasses.replace(combined, events=())
    with pytest.raises(SecurityMasterError, match="not source-derived"):
        revalidate_identity_resolved_firm_rating_result(
            forged,
            firm_result=firm_result,
            identity_audit=identity_audit,
            ingest_audit=ingest,
            ontology=ontology,
            master=master,
        )


def test_combined_result_uses_identity_refusal_precedence(tmp_path):
    ingest = _ingest_audit(
        tmp_path / "snapshot", [_rating_row("event-miss", "MISS")]
    )
    master = _write_master(tmp_path / "master.json")
    ontology = _ontology(tmp_path / "ontology.json")
    firm_result = normalize_firm_rating_audit(ingest, ontology)
    identity_audit = audit_benzinga_security_identities(ingest, master)
    combined = bind_firm_normalization_to_security_identities(
        firm_result,
        identity_audit,
        ingest_audit=ingest,
        ontology=ontology,
        master=master,
    )
    assert not combined.events
    assert len(combined.refusals) == 1
    assert combined.refusals[0].stage is CombinedRefusalStage.IDENTITY
    assert combined.refusals[0].reason == "no_active_ticker_mapping"


def test_structural_files_cannot_self_promote_to_production(tmp_path):
    master = _write_master(tmp_path / "master.json")
    ontology = _ontology(tmp_path / "ontology.json")
    with pytest.raises(ProductionRegistryError, match="no unique production"):
        require_registered_production_security_master(master)
    with pytest.raises(ProductionRegistryError, match="no unique production"):
        require_registered_production_firm_ontology(ontology)


def test_production_registry_is_checked_before_symlink_resolution(
    tmp_path, monkeypatch
):
    master = _write_master(tmp_path / "master.json")
    registry = tmp_path / "registry.json"
    registry.write_bytes(
        canonical_json_bytes(
            {"schema": "arv2-security-master-registry-v1", "entries": []}
        )
    )
    monkeypatch.setattr(
        security_master_module, "SECURITY_MASTER_REGISTRY_PATH", registry
    )
    path_type = type(registry)
    original = path_type.is_symlink
    monkeypatch.setattr(
        path_type,
        "is_symlink",
        lambda self: True if self == registry else original(self),
    )
    with pytest.raises(ProductionRegistryError, match="registry must not be a symlink"):
        require_registered_production_security_master(master)


def test_positive_registry_path_binds_reviewed_blob_and_rejects_later_substitution(
    tmp_path, monkeypatch
):
    repo = tmp_path / "reference-repo"
    specs = repo / "specs"
    specs.mkdir(parents=True)
    artifact_path = repo / "master.json"
    registry_path = specs / "security_master_registry.json"
    artifact_path.write_bytes(canonical_json_bytes(_master_payload()))
    registry_path.write_bytes(
        canonical_json_bytes(
            {"schema": "arv2-security-master-registry-v1", "entries": []}
        )
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Fixture Reviewer")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "add", "--", "master.json", "specs/security_master_registry.json")
    _git(repo, "commit", "-q", "-m", "review exact structural fixture")
    review_commit = _git(repo, "rev-parse", "HEAD")

    artifact_sha256 = sha256_bytes(artifact_path.read_bytes())
    entry = {
        "artifact_id": "security-master-fixture-1",
        "artifact_sha256": artifact_sha256,
        "artifact_path": "master.json",
        "review_commit": review_commit,
        "reviewed_by": "Independent Fixture Reviewer",
        "reviewed_at": "2026-08-29T01:00:00.000000Z",
    }
    registry_path.write_bytes(
        canonical_json_bytes(
            {
                "schema": "arv2-security-master-registry-v1",
                "entries": [entry],
            }
        )
    )
    _git(repo, "add", "--", "specs/security_master_registry.json")
    _git(repo, "commit", "-q", "-m", "register reviewed structural fixture")
    master = load_pit_security_master(artifact_path)
    monkeypatch.setattr(
        security_master_module, "SECURITY_MASTER_REGISTRY_PATH", registry_path
    )
    assert require_registered_production_security_master(master) is master

    substituted = _master_payload()
    substituted["version"] = "version-substituted"
    artifact_path.write_bytes(canonical_json_bytes(substituted))
    entry["artifact_sha256"] = sha256_bytes(artifact_path.read_bytes())
    registry_path.write_bytes(
        canonical_json_bytes(
            {
                "schema": "arv2-security-master-registry-v1",
                "entries": [entry],
            }
        )
    )
    _git(repo, "add", "--", "master.json", "specs/security_master_registry.json")
    _git(repo, "commit", "-q", "-m", "attempt post-review substitution")
    substituted_master = load_pit_security_master(artifact_path)
    with pytest.raises(ProductionRegistryError, match="reviewed blob"):
        require_registered_production_security_master(substituted_master)


def test_lineage_and_terminal_interval_guards_are_structural(tmp_path):
    missing_terminal = _historical_payload()
    missing_terminal["lineage_events"] = [
        item
        for item in missing_terminal["lineage_events"]
        if item["kind"] == "symbol_change"
    ]
    path = tmp_path / "missing-terminal.json"
    path.write_bytes(canonical_json_bytes(missing_terminal))
    with pytest.raises(SecurityMasterError, match="ended security"):
        load_pit_security_master(path)

    open_listing = _historical_payload()
    listing = next(
        item
        for item in open_listing["listings"]
        if item["listing_id"] == "listing-old-new-symbol"
    )
    listing["valid_to"] = None
    listing["valid_to_available_at"] = None
    path = tmp_path / "open-listing.json"
    path.write_bytes(canonical_json_bytes(open_listing))
    with pytest.raises(SecurityMasterError, match="listing validity escapes"):
        load_pit_security_master(path)


def test_security_type_enum_exactly_matches_frozen_universe_vocabulary():
    assert {item.value for item in SecurityType} == {
        "common_stock",
        "adr",
        "bdc",
        "closed_end_fund",
        "etf",
        "foreign_ordinary",
        "limited_partnership",
        "preferred_stock",
        "reit",
        "right",
        "trust",
        "unit",
        "warrant",
    }


def test_unexplained_listing_closure_is_rejected_at_load(tmp_path):
    """A ticker may not simply stop without lineage explaining why.

    This guard exists and works, but nothing pinned it: disabling it left the
    whole file green. An unexplained closure is exactly how a delisting hides
    as a quiet gap, which would silently drop the hardest names from the
    identity layer feeding the QC test.
    """
    payload = _master_payload(
        securities=[_security("security-live", "issuer-live", "class-live")],
        listings=[
            _listing("listing-live", "security-live", "LIVE", valid_to="2020-01-01")
        ],
        lineage_events=[],
    )
    with pytest.raises(SecurityMasterError, match="transition or terminal lineage"):
        _write_master(tmp_path / "master.json", payload)


def test_identity_coverage_rejects_non_exhaustive_counts():
    """Coverage must stay exhaustive even when constructed directly.

    The audit builds consistent coverage today, but the dataclass is public
    and its arithmetic guard had no regression: mapped + refused must equal
    total, and the per-reason counts must sum to the refusals.
    """
    from research.analyst_revisions_v2.security_master import SecurityIdentityCoverage

    with pytest.raises(SecurityMasterError, match="not exhaustive"):
        SecurityIdentityCoverage(
            total_records=5, mapped_records=2, refused_records=2, refusal_counts=(
                (IdentityRefusalReason.NO_ACTIVE_TICKER_MAPPING, 2),
            ),
        )
    with pytest.raises(SecurityMasterError, match="do not sum"):
        SecurityIdentityCoverage(
            total_records=4, mapped_records=2, refused_records=2, refusal_counts=(
                (IdentityRefusalReason.NO_ACTIVE_TICKER_MAPPING, 1),
            ),
        )


def test_identity_eligibility_matches_the_frozen_arv2_0_universe():
    """The identity layer must enforce exactly the frozen owner decision.

    ARV2-0 froze the research universe; this module independently hardcodes
    the same venues, incorporation country and instrument vocabulary. They
    agree today, but nothing bound them, so amending the frozen universe would
    silently leave the identity gate enforcing the old one - and that gate is
    what decides which securities can ever reach the QuantConnect test.
    """
    import json
    from pathlib import Path as _Path

    from research.analyst_revisions_v2.security_master import (
        ELIGIBLE_ISSUER_COUNTRY,
        ELIGIBLE_LISTING_EXCHANGES,
    )

    spec = json.loads(
        (
            _Path(__file__).resolve().parents[2]
            / "research"
            / "analyst_revisions_v2"
            / "specs"
            / "arv2_round0.draft.json"
        ).read_text(encoding="utf-8")
    )
    universe = next(
        cell["value"]
        for cell in spec["cells"]
        if cell["cell_id"] == "universe_contract"
    )

    assert set(universe["listing_venues"]) == set(ELIGIBLE_LISTING_EXCHANGES)
    # The spec states incorporation in prose; pin the exact code equivalent so
    # neither representation can drift from the other unnoticed.
    assert universe["issuer_incorporation"] == "united_states"
    assert ELIGIBLE_ISSUER_COUNTRY == "US"
    # The enum must cover the eligible type plus every excluded type, so a new
    # instrument category cannot be added to the frozen universe without also
    # being representable (and therefore refusable) here.
    assert {item.value for item in SecurityType} == set(
        universe["instrument_types"]
    ) | set(universe["excluded_instrument_types"])
    # Exactly one type is eligible, and it is the one resolution admits.
    assert universe["instrument_types"] == ["common_stock"]
    assert SecurityType.COMMON_STOCK.value == "common_stock"
