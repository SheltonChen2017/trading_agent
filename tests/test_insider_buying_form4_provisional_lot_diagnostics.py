"""IB-2D provisional lot diagnostics tests (synthetic/offline only).

The tests compose the exact factory-created IB-1E/IB-2A/IB-2B/IB-2C chain.
They grant no canonical filtering, amendment supersession, official-security,
outcome, QuantConnect, deployment, execution, or trading authority.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

import research.insider_buying as insider_package
from data.hashing import hash_payload
from research.insider_buying import (
    ClassificationOutcome,
    Form4SecurityClass,
    Form4SecurityTitleMappingKind,
    TransactionDiagnostic,
    build_form4_provisional_disposition_report,
    build_form4_pit_security_mapping,
)
from research.insider_buying import (
    form4_observed_identity_inventory as inventory_module,
)
from research.insider_buying import (
    form4_pit_security_mapping as mapping_module,
)
from research.insider_buying import (
    form4_provisional_lot_diagnostics as diagnostics_module,
)
from research.insider_buying.form4_observed_identity_inventory import (
    build_form4_observed_identity_inventory as _real_inventory_builder,
)
from tests import test_insider_buying_form4_pit_security_mapping as ib2c
from tests import test_insider_buying_form4_sec_entity_grouping as ib2b


BUILDER_COMMIT = "d" * 40


def _replace_transaction_fragment(
    spec,
    *,
    lots: tuple[tuple[str, str, str, str], ...],
):
    """Replace the fixture's one transaction with exact synthetic lots.

    Each lot is ``(shares, price, transaction_date, security_title)``.
    """

    xml = spec.xml_bytes.decode("utf-8")
    start = xml.index("<nonDerivativeTransaction>")
    end = xml.index("</nonDerivativeTransaction>", start) + len(
        "</nonDerivativeTransaction>"
    )
    template = xml[start:end]
    old_shares = str(5000 + int(spec.accession.rsplit("-", 1)[1]))
    rendered = []
    for shares, price, transaction_date, security_title in lots:
        item = template.replace(
            f"<transactionShares><value>{old_shares}</value>",
            f"<transactionShares><value>{shares}</value>",
        )
        item = item.replace(
            "<transactionPricePerShare><value>12.50</value>",
            f"<transactionPricePerShare><value>{price}</value>",
        )
        item = item.replace(
            "<transactionDate><value>2026-08-18</value>",
            f"<transactionDate><value>{transaction_date}</value>",
        )
        item = item.replace(
            "<securityTitle><value>Common Stock</value>",
            f"<securityTitle><value>{security_title}</value>",
        )
        rendered.append(item)
    return replace(
        spec,
        xml_bytes=(xml[:start] + "".join(rendered) + xml[end:]).encode("utf-8"),
    )


def _build_upstream(
    monkeypatch,
    specs=None,
    *,
    reverse: bool = False,
    securities=None,
    titles=None,
    tickers=None,
    manual_title: bool = False,
):
    """Build and retain the exact four-stage upstream object chain."""

    specs = (ib2b._spec(1),) if specs is None else tuple(specs)
    captured_evidence = []
    def capture_evidence(evidence, **kwargs):
        captured_evidence.append(evidence)
        return _real_inventory_builder(evidence, **kwargs)

    monkeypatch.setattr(
        ib2b,
        "build_form4_observed_identity_inventory",
        capture_evidence,
    )
    inventory, grouping = ib2b._group(monkeypatch, specs, reverse=reverse)
    assert len(captured_evidence) == 1

    defaults = ib2c._catalog()
    securities = defaults[0] if securities is None else securities
    titles = defaults[1] if titles is None else titles
    tickers = defaults[2] if tickers is None else tickers
    if manual_title:
        assert len(titles) == 1
        titles = (
            replace(
                titles[0],
                mapping_kind=Form4SecurityTitleMappingKind.MANUAL_EXCEPTION,
            ),
        )
    mapping = build_form4_pit_security_mapping(
        grouping,
        security_records=securities,
        title_intervals=titles,
        ticker_intervals=tickers,
        reference_id="synthetic-offline-reference",
        reference_version="v1",
        reference_sha256=ib2c.REFERENCE_SHA256,
        builder_git_commit=ib2c.BUILDER_COMMIT,
    )
    return captured_evidence[0], inventory, grouping, mapping


def _build(monkeypatch, specs=None, **kwargs):
    evidence, inventory, grouping, mapping = _build_upstream(
        monkeypatch,
        specs,
        **kwargs,
    )
    result = diagnostics_module.build_form4_provisional_lot_diagnostics(
        mapping,
        grouping,
        inventory,
        evidence,
        builder_git_commit=BUILDER_COMMIT,
    )
    return evidence, inventory, grouping, mapping, result


def _forge(value, **updates):
    forged = object.__new__(type(value))
    for name, item in vars(value).items():
        object.__setattr__(forged, name, item)
    for name, item in updates.items():
        object.__setattr__(forged, name, item)
    return forged


def _rehash_diagnostic_row(row, **updates):
    changed = _forge(row, **updates)
    return _forge(
        changed,
        diagnostic_row_id=hash_payload(changed.lineage_payload()),
    )


def _rehash_group(group, **updates):
    changed = _forge(group, **updates)
    return _forge(
        changed,
        provisional_group_id=hash_payload(changed.lineage_payload()),
    )


def _rehash_identity(identity, **updates):
    changed = _forge(identity, **updates)
    return _forge(
        changed,
        diagnostics_id=(
            "form4-provisional-lot-diagnostics-"
            f"{hash_payload(changed.lineage_payload())[:16]}"
        ),
    )


def _lot_spec(
    sequence: int,
    lots: tuple[tuple[str, str, str, str], ...],
    **kwargs,
):
    return _replace_transaction_fragment(
        ib2b._spec(sequence, **kwargs),
        lots=lots,
    )


def test_ib2d_contract_version_and_threshold_are_frozen():
    assert diagnostics_module.FORM4_PROVISIONAL_LOT_DIAGNOSTICS_VERSION == (
        "INSETF-IB2D-FORM4-PROVISIONAL-LOT-DIAGNOSTICS-v1"
    )
    assert diagnostics_module.FORM4_PROVISIONAL_LOT_THRESHOLD_USD == Decimal(
        "50000"
    )


def test_same_key_thirty_thousand_lots_aggregate_to_sixty_thousand(monkeypatch):
    spec = _lot_spec(
        1,
        (
            ("2400", "12.50", "2026-08-18", "Common Stock"),
            ("2400", "12.50", "2026-08-18", "Common Stock"),
        ),
    )
    _evidence, _inventory, _grouping, _mapping, result = _build(
        monkeypatch,
        (spec,),
    )

    assert len(result.rows) == 2
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.member_count == 2
    assert group.member_row_ids == tuple(
        sorted(row.diagnostic_row_id for row in result.rows)
    )
    assert group.total_shares == Decimal("4800")
    assert group.total_purchase_value_usd == Decimal("60000.00")
    assert group.threshold_usd == Decimal("50000")
    assert group.threshold_diagnostic is (
        diagnostics_module.Form4ProvisionalLotThresholdDiagnostic.AT_OR_ABOVE_PROVISIONAL_MINIMUM
    )
    assert group.meets_provisional_minimum_purchase_value is True
    assert all(
        row.disposition
        is diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
        and row.quarantine_reasons == ()
        and row.provisional_group_key == group.provisional_group_key
        for row in result.rows
    )


@pytest.mark.parametrize(
    ("value", "expected_diagnostic", "meets"),
    (
        (
            "49999.99",
            "BELOW_PROVISIONAL_MINIMUM",
            False,
        ),
        (
            "50000",
            "AT_OR_ABOVE_PROVISIONAL_MINIMUM",
            True,
        ),
        (
            "50000.01",
            "AT_OR_ABOVE_PROVISIONAL_MINIMUM",
            True,
        ),
    ),
)
def test_threshold_is_diagnostic_and_applies_after_aggregation(
    monkeypatch,
    value,
    expected_diagnostic,
    meets,
):
    spec = _lot_spec(
        1,
        (("1", value, "2026-08-18", "Common Stock"),),
    )
    *_upstream, result = _build(monkeypatch, (spec,))
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.total_purchase_value_usd == Decimal(value)
    assert group.threshold_diagnostic is getattr(
        diagnostics_module.Form4ProvisionalLotThresholdDiagnostic,
        expected_diagnostic,
    )
    assert group.meets_provisional_minimum_purchase_value is meets
    assert result.lot_aggregation_authorized is False
    assert result.post_aggregation_minimum_gate_authorized is False


def test_exact_decimal_sum_ignores_low_ambient_precision(monkeypatch):
    spec = _lot_spec(
        1,
        (
            ("1", "49999.99", "2026-08-18", "Common Stock"),
            ("1", "0.02", "2026-08-18", "Common Stock"),
        ),
    )
    evidence, inventory, grouping, mapping = _build_upstream(
        monkeypatch,
        (spec,),
    )
    with localcontext() as context:
        context.prec = 3
        result = diagnostics_module.build_form4_provisional_lot_diagnostics(
            mapping,
            grouping,
            inventory,
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )
    group = result.groups[0]
    assert group.total_purchase_value_usd == Decimal("50000.01")
    assert group.total_shares == Decimal("2")
    assert group.meets_provisional_minimum_purchase_value is True


def test_group_key_contains_only_owner_security_share_class_and_date(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    row = result.rows[0]
    group = result.groups[0]
    expected = hash_payload(
        {
            "attributed_owner_cik": row.attributed_owner_cik,
            "attributed_owner_candidate_id": row.attributed_owner_candidate_id,
            "security_id": row.security_id,
            "share_class_id": row.share_class_id,
            "transaction_date": row.transaction_date.isoformat(),
        }
    )
    assert row.provisional_group_key == expected
    assert group.provisional_group_key == expected
    assert (
        group.attributed_owner_cik,
        group.attributed_owner_candidate_id,
        group.security_id,
        group.share_class_id,
        group.transaction_date,
    ) == (
        row.attributed_owner_cik,
        row.attributed_owner_candidate_id,
        row.security_id,
        row.share_class_id,
        row.transaction_date,
    )


def test_latest_member_acceptance_and_input_order_are_deterministic(monkeypatch):
    specs = (
        _lot_spec(1, (("2", "10000", "2026-08-18", "Common Stock"),)),
        _lot_spec(2, (("3", "10000", "2026-08-18", "Common Stock"),)),
    )
    *_upstream, forward = _build(monkeypatch, specs)
    *_upstream, reverse = _build(monkeypatch, specs, reverse=True)

    assert forward.to_payload() == reverse.to_payload()
    assert forward.groups[0].latest_member_accepted_at_utc == (
        specs[1].accepted_at.isoformat(timespec="seconds")
    )
    assert forward.groups[0].member_count == 2
    assert forward.groups[0].total_purchase_value_usd == Decimal("50000")


def test_multiple_group_and_row_order_is_canonical(monkeypatch):
    specs = (
        _lot_spec(1, (("1", "50000", "2026-08-19", "Common Stock"),)),
        _lot_spec(2, (("1", "50000", "2026-08-18", "Common Stock"),)),
    )
    *_upstream, forward = _build(monkeypatch, specs)
    *_upstream, reverse = _build(monkeypatch, specs, reverse=True)
    assert forward.to_payload() == reverse.to_payload()
    assert tuple(group.transaction_date.isoformat() for group in forward.groups) == (
        "2026-08-18",
        "2026-08-19",
    )
    assert tuple(row.accession_number for row in forward.rows) == tuple(
        sorted(row.accession_number for row in forward.rows)
    )


def test_manual_title_mapping_remains_explicit_and_non_authoritative(monkeypatch):
    *_upstream, result = _build(monkeypatch, manual_title=True)
    assert len(result.rows) == 1
    assert result.rows[0].title_mapping_kind is (
        Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
    )
    assert result.identity.manual_exception_candidate_row_count == 1
    assert result.rows[0].disposition is (
        diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
    )
    assert result.ordinary_equity_classification_verified is False
    assert result.canonical_filter_authorized is False


def test_non_ordinary_structural_class_is_quarantined_without_authority(monkeypatch):
    securities = (
        ib2c._security(security_class=Form4SecurityClass.PREFERRED_STOCK),
    )
    *_upstream, result = _build(monkeypatch, securities=securities)
    row = result.rows[0]
    assert row.security_class_normalized is Form4SecurityClass.PREFERRED_STOCK
    assert row.quarantine_reasons == (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.NON_ORDINARY_EQUITY_CLASS_QUARANTINED,
    )
    assert row.provisional_group_key is None
    assert result.groups == ()
    assert row.ordinary_equity_classification_verified is False


@pytest.mark.parametrize(
    ("security_class", "candidate"),
    (
        (Form4SecurityClass.COMMON_STOCK, True),
        (Form4SecurityClass.COMMON_SHARES, True),
        (Form4SecurityClass.ORDINARY_SHARES, True),
        (Form4SecurityClass.AMERICAN_DEPOSITARY_RECEIPT, False),
        (Form4SecurityClass.PREFERRED_STOCK, False),
        (Form4SecurityClass.OTHER, False),
    ),
)
def test_provisional_ordinary_equity_class_matrix_is_exact(
    monkeypatch,
    security_class,
    candidate,
):
    securities = (ib2c._security(security_class=security_class),)
    *_upstream, result = _build(monkeypatch, securities=securities)
    row = result.rows[0]
    assert (row.disposition is (
        diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
    )) is candidate
    assert (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.NON_ORDINARY_EQUITY_CLASS_QUARANTINED
        in row.quarantine_reasons
    ) is (not candidate)
    assert bool(result.groups) is candidate
    assert result.ordinary_equity_classification_verified is False


def test_manual_exception_never_overrides_non_ordinary_class_quarantine(monkeypatch):
    securities = (
        ib2c._security(security_class=Form4SecurityClass.PREFERRED_STOCK),
    )
    *_upstream, result = _build(
        monkeypatch,
        securities=securities,
        manual_title=True,
    )
    assert result.rows[0].title_mapping_kind is (
        Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
    )
    assert result.rows[0].disposition is (
        diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
    )
    assert result.identity.manual_exception_candidate_row_count == 0


def test_every_member_of_a_supplied_amendment_family_is_quarantined(monkeypatch):
    original = ib2b._spec(1)
    first_amendment = ib2b._spec(
        2,
        year=2027,
        month=1,
        day=4,
        form="4/A",
        amends_accession=original.accession,
    )
    second_amendment = ib2b._spec(
        3,
        year=2027,
        month=1,
        day=5,
        form="4/A",
        amends_accession=original.accession,
    )
    *_upstream, result = _build(
        monkeypatch,
        (original, first_amendment, second_amendment),
    )
    family_reason = (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.AMENDMENT_FAMILY_REQUIRES_SUPERSESSION
    )

    assert len(result.rows) == 3
    assert result.groups == ()
    assert {row.original_accession for row in result.rows} == {original.accession}
    assert all(
        row.amendment_family_has_supplied_amendment is True
        and family_reason in row.quarantine_reasons
        and row.provisional_group_key is None
        and row.disposition
        is diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
        for row in result.rows
    )


def test_zero_row_amendment_still_quarantines_the_original_family(monkeypatch):
    original = ib2b._spec(1)
    empty_amendment = ib2b._spec(
        2,
        year=2027,
        month=1,
        day=4,
        form="4/A",
        amends_accession=original.accession,
        include_transaction=False,
    )
    evidence, _inventory, _grouping, mapping, result = _build(
        monkeypatch,
        (original, empty_amendment),
    )

    assert len(evidence.as_filed_corpus.filings) == 2
    assert len(mapping.rows) == 1
    assert len(result.rows) == 1
    assert result.groups == ()
    assert result.amendment_family_original_accessions == (original.accession,)
    assert result.identity.amendment_family_quarantined_count == 1
    row = result.rows[0]
    assert row.accession_number == original.accession
    assert row.amendment_family_has_supplied_amendment is True
    assert row.quarantine_reasons == (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.AMENDMENT_FAMILY_REQUIRES_SUPERSESSION,
    )


def test_zero_row_original_and_amendment_retain_exact_empty_family_intersection(
    monkeypatch,
):
    original = ib2b._spec(1, include_transaction=False)
    empty_amendment = ib2b._spec(
        2,
        year=2027,
        month=1,
        day=4,
        form="4/A",
        amends_accession=original.accession,
        include_transaction=False,
    )
    evidence, inventory, grouping, mapping, result = _build(
        monkeypatch,
        (original, empty_amendment),
    )

    assert len(evidence.as_filed_corpus.filings) == 2
    assert inventory.transactions == ()
    assert grouping.transaction_attributions == ()
    assert mapping.rows == ()
    assert result.rows == ()
    assert result.groups == ()
    assert result.amendment_family_original_accessions == (original.accession,)
    assert result.identity.amendment_family_quarantined_count == 1
    assert result.identity.amendment_family_quarantined_row_count == 0
    assert result.identity.amendment_family_inventory_hash == hash_payload(
        [original.accession]
    )


def test_amendment_family_quarantine_does_not_poison_unrelated_original(
    monkeypatch,
):
    original = ib2b._spec(1)
    amendment = ib2b._spec(
        2,
        year=2027,
        month=1,
        day=4,
        form="4/A",
        amends_accession=original.accession,
    )
    unrelated = ib2b._spec(3)
    *_upstream, result = _build(
        monkeypatch,
        (original, amendment, unrelated),
    )
    by_accession = {row.accession_number: row for row in result.rows}
    family_reason = (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.AMENDMENT_FAMILY_REQUIRES_SUPERSESSION
    )

    assert result.amendment_family_original_accessions == (original.accession,)
    assert all(
        by_accession[accession].amendment_family_has_supplied_amendment is True
        and family_reason in by_accession[accession].quarantine_reasons
        for accession in (original.accession, amendment.accession)
    )
    unrelated_row = by_accession[unrelated.accession]
    assert unrelated_row.amendment_family_has_supplied_amendment is False
    assert unrelated_row.quarantine_reasons == ()
    assert unrelated_row.disposition is (
        diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
    )
    assert len(result.groups) == 1
    assert result.groups[0].member_row_ids == (unrelated_row.diagnostic_row_id,)


def test_parser_and_observed_identity_quarantine_are_both_retained(monkeypatch):
    spec = ib2c._with_xml(
        ib2b._spec(1),
        "<transactionCode>P</transactionCode>",
        "<transactionCode>S</transactionCode>",
    )
    *_upstream, result = _build(monkeypatch, (spec,))
    row = result.rows[0]
    assert row.provisional_group_key is None
    assert row.quarantine_reasons == (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.UPSTREAM_PARSER_QUARANTINED,
        diagnostics_module.Form4ProvisionalLotQuarantineReason.UPSTREAM_IDENTITY_QUARANTINED,
    )


def test_owner_attribution_quarantine_is_retained(monkeypatch):
    spec = ib2b._spec(
        1,
        owners=(ib2b._Owner(), ib2b._Owner(cik=ib2b.OTHER_OWNER_CIK)),
    )
    *_upstream, result = _build(monkeypatch, (spec,))
    row = result.rows[0]
    assert row.provisional_group_key is None
    assert (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.OWNER_ATTRIBUTION_QUARANTINED
        in row.quarantine_reasons
    )
    assert row.attributed_owner_cik is None


def test_security_mapping_quarantine_is_retained(monkeypatch):
    *_upstream, result = _build(monkeypatch, titles=())
    row = result.rows[0]
    assert row.provisional_group_key is None
    assert row.quarantine_reasons == (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.SECURITY_MAPPING_QUARANTINED,
    )
    assert row.security_id is None


def test_independent_quarantine_directions_accumulate_without_loss(monkeypatch):
    spec = ib2c._with_xml(
        ib2b._spec(
            1,
            owners=(ib2b._Owner(), ib2b._Owner(cik=ib2b.OTHER_OWNER_CIK)),
        ),
        "<transactionCode>P</transactionCode>",
        "<transactionCode>S</transactionCode>",
    )
    *_upstream, result = _build(monkeypatch, (spec,), titles=())
    assert result.groups == ()
    assert result.rows[0].quarantine_reasons == (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.UPSTREAM_PARSER_QUARANTINED,
        diagnostics_module.Form4ProvisionalLotQuarantineReason.UPSTREAM_IDENTITY_QUARANTINED,
        diagnostics_module.Form4ProvisionalLotQuarantineReason.OWNER_ATTRIBUTION_QUARANTINED,
        diagnostics_module.Form4ProvisionalLotQuarantineReason.SECURITY_MAPPING_QUARANTINED,
    )


def test_invalid_economics_are_retained_as_upstream_quarantine(monkeypatch):
    spec = _lot_spec(
        1,
        (("1", "0", "2026-08-18", "Common Stock"),),
    )
    *_upstream, result = _build(monkeypatch, (spec,))
    row = result.rows[0]
    assert row.purchase_value_usd == Decimal("0")
    assert (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.UPSTREAM_PARSER_QUARANTINED
        in row.quarantine_reasons
    )
    assert (
        diagnostics_module.Form4ProvisionalLotQuarantineReason.ECONOMICS_UNAVAILABLE_QUARANTINED
        in row.quarantine_reasons
    )
    assert result.groups == ()


def test_singleton_candidate_is_retained_even_below_diagnostic_threshold(monkeypatch):
    spec = _lot_spec(
        1,
        (("1", "1.25", "2026-08-18", "Common Stock"),),
    )
    *_upstream, result = _build(monkeypatch, (spec,))
    assert len(result.rows) == len(result.groups) == 1
    assert result.groups[0].member_count == 1
    assert result.groups[0].total_purchase_value_usd == Decimal("1.25")
    assert result.groups[0].meets_provisional_minimum_purchase_value is False
    assert result.rows[0].disposition is (
        diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
    )


def test_empty_transaction_inventory_is_a_valid_hash_bound_result(monkeypatch):
    spec = ib2b._spec(1, include_transaction=False)
    *_upstream, result = _build(monkeypatch, (spec,))
    assert result.rows == ()
    assert result.groups == ()
    assert result.identity.mapping_row_count == 0
    assert result.identity.provisional_group_count == 0
    assert result.identity.diagnostic_row_inventory_hash == hash_payload([])
    assert result.identity.provisional_group_inventory_hash == hash_payload([])


def test_every_output_authority_gate_is_false_and_looks_are_zero(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    authority_fields = (
        "official_profile_compatibility_verified",
        "official_amendment_link_verified",
        "complete_amendment_coverage_verified",
        "official_security_master_compatibility_verified",
        "authenticated_amendment_supersession_verified",
        "point_in_time_issuer_identity_verified",
        "point_in_time_reporting_owner_identity_verified",
        "point_in_time_security_identity_verified",
        "point_in_time_transaction_identity_verified",
        "ordinary_equity_classification_verified",
        "deduplication_authorized",
        "canonical_filter_authorized",
        "lot_aggregation_authorized",
        "post_aggregation_minimum_gate_authorized",
        "sec_access_authorized",
        "provider_access_authorized",
        "outcomes_authorized",
        "qc_execution_authorized",
        "deployment_authorized",
        "trading_authorized",
    )
    for value in (result, result.identity, result.rows[0], result.groups[0]):
        assert all(getattr(value, name) is False for name in authority_fields)
        assert value.authorized_outcome_looks == 0
        assert value.consumed_outcome_looks == 0


def test_public_result_types_are_factory_gated(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    for value in (result, result.identity, result.rows[0], result.groups[0]):
        with pytest.raises(
            diagnostics_module.Form4ProvisionalLotDiagnosticsError,
            match="factory-created",
        ):
            replace(value)


def test_four_stage_provenance_and_every_transaction_join_are_bound(monkeypatch):
    evidence, inventory, grouping, mapping, result = _build(monkeypatch)
    identity = result.identity
    rebuilt_report = build_form4_provisional_disposition_report(
        evidence,
        builder_git_commit=inventory.identity.builder_git_commit,
    )

    assert identity.upstream_mapping_id == mapping.identity.mapping_id
    assert identity.upstream_mapping_identity_hash == hash_payload(
        mapping.identity.to_payload()
    )
    assert identity.upstream_mapping_fingerprint == (
        mapping_module._mapping_provenance_fingerprint(mapping)
    )
    assert identity.upstream_mapping_runtime_fingerprint == (
        diagnostics_module._runtime_provenance_fingerprint(mapping)
    )
    assert identity.upstream_grouping_id == grouping.identity.grouping_id
    assert identity.upstream_grouping_identity_hash == hash_payload(
        grouping.identity.to_payload()
    )
    assert identity.upstream_grouping_fingerprint == (
        ib2b.grouping_module._grouping_provenance_fingerprint(grouping)
    )
    assert identity.upstream_grouping_runtime_fingerprint == (
        diagnostics_module._runtime_provenance_fingerprint(grouping)
    )
    assert identity.upstream_inventory_id == inventory.identity.inventory_id
    assert identity.upstream_inventory_identity_hash == hash_payload(
        inventory.identity.to_payload()
    )
    assert identity.upstream_inventory_fingerprint == (
        inventory_module._inventory_provenance_fingerprint(inventory)
    )
    assert identity.upstream_inventory_runtime_fingerprint == (
        diagnostics_module._runtime_provenance_fingerprint(inventory)
    )
    assert identity.upstream_evidence_id == evidence.identity.evidence_id
    assert identity.upstream_evidence_identity_hash == hash_payload(
        evidence.identity.to_payload()
    )
    assert identity.upstream_evidence_runtime_fingerprint == (
        diagnostics_module._runtime_provenance_fingerprint(evidence)
    )
    assert identity.rebuilt_report_id == rebuilt_report.identity.report_id
    assert identity.rebuilt_report_identity_hash == hash_payload(
        rebuilt_report.identity.to_payload()
    )
    assert identity.rebuilt_report_row_inventory_hash == hash_payload(
        [row.to_payload() for row in rebuilt_report.rows]
    )

    diagnostic = result.rows[0]
    mapped = mapping.rows[0]
    grouped = grouping.transaction_attributions[0]
    observed = inventory.transactions[0]
    report_row = rebuilt_report.rows[0]
    parsed = evidence.as_filed_corpus.filings[0].transactions[0]
    assert diagnostic.mapping_row_id == mapped.mapping_row_id
    assert diagnostic.transaction_attribution_id == grouped.transaction_attribution_id
    assert diagnostic.upstream_transaction_observation_id == (
        observed.transaction_observation_id
    )
    assert diagnostic.upstream_report_row_id == report_row.row_id
    assert diagnostic.upstream_report_row_id == observed.upstream_report_row_id
    assert diagnostic.transaction_payload_hash == report_row.transaction_payload_hash
    assert diagnostic.event_id == parsed.event_id == mapped.event_id
    assert diagnostic.parser_outcomes == parsed.outcomes == report_row.outcomes
    assert diagnostic.parser_diagnostics == parsed.diagnostics == report_row.diagnostics
    assert diagnostic.shares == parsed.shares
    assert diagnostic.price_per_share == parsed.price_per_share
    assert diagnostic.purchase_value_usd == parsed.purchase_value_usd


def test_builder_refuses_any_cross_chain_object_substitution(monkeypatch):
    first = _build_upstream(monkeypatch, (ib2b._spec(1),))
    second = _build_upstream(monkeypatch, (ib2b._spec(2),))
    evidence, inventory, grouping, mapping = first
    other_evidence, other_inventory, other_grouping, _other_mapping = second
    substitutions = (
        (mapping, other_grouping, inventory, evidence),
        (mapping, grouping, other_inventory, evidence),
        (mapping, grouping, inventory, other_evidence),
    )
    for supplied in substitutions:
        with pytest.raises(diagnostics_module.Form4ProvisionalLotDiagnosticsError):
            diagnostics_module.build_form4_provisional_lot_diagnostics(
                *supplied,
                builder_git_commit=BUILDER_COMMIT,
            )


@pytest.mark.parametrize(
    ("stage", "corruption"),
    (
        ("inventory", "enum_to_string"),
        ("inventory", "tuple_to_list"),
        ("grouping", "enum_to_string"),
        ("grouping", "tuple_to_list"),
        ("mapping", "enum_to_string"),
        ("mapping", "tuple_to_list"),
    ),
)
def test_builder_refuses_stable_type_corruption_in_every_upstream_input(
    monkeypatch,
    stage,
    corruption,
):
    evidence, inventory, grouping, mapping = _build_upstream(monkeypatch)
    upstream = {
        "inventory": inventory,
        "grouping": grouping,
        "mapping": mapping,
    }[stage]
    collection_name = {
        "inventory": "transactions",
        "grouping": "transaction_attributions",
        "mapping": "rows",
    }[stage]
    collection = getattr(upstream, collection_name)

    if corruption == "tuple_to_list":
        target = upstream
        field_name = collection_name
        original_value = collection
        corrupted_value = list(collection)
    else:
        target = collection[0]
        field_name = "upstream_disposition"
        original_value = target.upstream_disposition
        corrupted_value = original_value.value

    object.__setattr__(target, field_name, corrupted_value)
    try:
        with pytest.raises(
            diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        ):
            diagnostics_module.build_form4_provisional_lot_diagnostics(
                mapping,
                grouping,
                inventory,
                evidence,
                builder_git_commit=BUILDER_COMMIT,
            )
    finally:
        object.__setattr__(target, field_name, original_value)


@pytest.mark.parametrize(
    ("boundary", "expected"),
    (
        (
            "mapping_attribution",
            "mapping row disagrees with its grouping attribution",
        ),
        (
            "attribution_inventory",
            "grouping attribution disagrees with inventory transaction",
        ),
        (
            "mapping_issuer",
            "mapping row disagrees with its filing observation",
        ),
        (
            "mapping_report",
            "mapping row disagrees with rebuilt IB-1G report",
        ),
    ),
)
def test_each_direct_upstream_join_mismatch_fails_closed(
    monkeypatch,
    boundary,
    expected,
):
    evidence, inventory, grouping, mapping = _build_upstream(monkeypatch)
    mapping_snapshot = mapping_module._mapping_provenance_payload(mapping)
    grouping_snapshot = ib2b.grouping_module._grouping_provenance_payload(grouping)
    inventory_snapshot = inventory_module._inventory_provenance_payload(inventory)
    rebuilt_report = build_form4_provisional_disposition_report(
        evidence,
        builder_git_commit=inventory.identity.builder_git_commit,
    )
    mapping_state = dict(mapping_snapshot["rows"][0])
    attribution = dict(grouping_snapshot["transaction_attributions"][0])
    inventory_transaction = dict(inventory_snapshot["transactions"][0])
    issuer_observation = next(
        dict(observation)
        for candidate in grouping_snapshot["issuer_candidates"]
        for observation in candidate["observations"]
        if observation["filing_observation_id"]
        == mapping_state["filing_observation_id"]
    )
    report_row = rebuilt_report.rows[0]

    if boundary == "mapping_attribution":
        attribution["source_sha256"] = "0" * 64
    elif boundary == "attribution_inventory":
        inventory_transaction["source_sha256"] = "0" * 64
    elif boundary == "mapping_issuer":
        issuer_observation["source_sha256"] = "0" * 64
    else:
        report_row = _forge(report_row, transaction_payload_hash="0" * 64)

    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match=expected,
    ):
        diagnostics_module._build_diagnostic_row(
            mapping_state,
            attribution=attribution,
            inventory_transaction=inventory_transaction,
            issuer_observation=issuer_observation,
            report_row=report_row,
            amended_families=frozenset(),
        )


def test_every_row_group_and_identity_authority_guard_is_load_bearing(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    authority_fields = (
        "official_profile_compatibility_verified",
        "official_amendment_link_verified",
        "complete_amendment_coverage_verified",
        "official_security_master_compatibility_verified",
        "authenticated_amendment_supersession_verified",
        "point_in_time_issuer_identity_verified",
        "point_in_time_reporting_owner_identity_verified",
        "point_in_time_security_identity_verified",
        "point_in_time_transaction_identity_verified",
        "ordinary_equity_classification_verified",
        "deduplication_authorized",
        "canonical_filter_authorized",
        "lot_aggregation_authorized",
        "post_aggregation_minimum_gate_authorized",
        "sec_access_authorized",
        "provider_access_authorized",
        "outcomes_authorized",
        "qc_execution_authorized",
        "deployment_authorized",
        "trading_authorized",
    )
    guarded_values = (
        (result.rows[0], diagnostics_module._ROW_FACTORY_TOKEN),
        (result.groups[0], diagnostics_module._GROUP_FACTORY_TOKEN),
        (result.identity, diagnostics_module._IDENTITY_FACTORY_TOKEN),
    )
    for value, token in guarded_values:
        for name in authority_fields:
            forged = _forge(value, **{name: True})
            with pytest.raises(
                diagnostics_module.Form4ProvisionalLotDiagnosticsError,
                match="claims authority",
            ):
                type(value).__post_init__(forged, token)
        for name in ("authorized_outcome_looks", "consumed_outcome_looks"):
            forged = _forge(value, **{name: 1})
            with pytest.raises(
                diagnostics_module.Form4ProvisionalLotDiagnosticsError,
                match="claims authority",
            ):
                type(value).__post_init__(forged, token)


def test_constructor_replay_refuses_changed_row_economics(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    row = _rehash_diagnostic_row(
        result.rows[0],
        purchase_value_usd=result.rows[0].purchase_value_usd + Decimal("0.01"),
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="economics are inconsistent",
    ):
        type(row).__post_init__(row, diagnostics_module._ROW_FACTORY_TOKEN)


@pytest.mark.parametrize("missing_field", ("shares", "price_per_share"))
def test_constructor_replay_refuses_partial_economics_with_positive_value(
    monkeypatch,
    missing_field,
):
    *_upstream, result = _build(monkeypatch)
    row = _rehash_diagnostic_row(
        result.rows[0],
        **{
            missing_field: None,
            "provisional_group_key": None,
            "disposition": (
                diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
            ),
            "quarantine_reasons": (
                diagnostics_module.Form4ProvisionalLotQuarantineReason.ECONOMICS_UNAVAILABLE_QUARANTINED,
            ),
        },
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="economics are inconsistent",
    ):
        type(row).__post_init__(row, diagnostics_module._ROW_FACTORY_TOKEN)


@pytest.mark.parametrize("include_attributed_outcome", (False, True))
def test_constructor_replay_refuses_owner_quarantine_with_retained_owner(
    monkeypatch,
    include_attributed_outcome,
):
    *_upstream, result = _build(monkeypatch)
    quarantine = ib2b.Form4OwnerAttributionOutcome.MULTIPLE_OWNER_SET_QUARANTINED
    attributed = (
        ib2b.Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED
    )
    outcomes = (attributed, quarantine) if include_attributed_outcome else (quarantine,)
    row = _rehash_diagnostic_row(
        result.rows[0],
        owner_attribution_outcomes=outcomes,
        provisional_group_key=None,
        disposition=(
            diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
        ),
        quarantine_reasons=(
            diagnostics_module.Form4ProvisionalLotQuarantineReason.OWNER_ATTRIBUTION_QUARANTINED,
        ),
    )
    with pytest.raises(diagnostics_module.Form4ProvisionalLotDiagnosticsError):
        type(row).__post_init__(row, diagnostics_module._ROW_FACTORY_TOKEN)


@pytest.mark.parametrize("include_mapped_outcome", (False, True))
def test_constructor_replay_refuses_mapping_quarantine_with_retained_mapping(
    monkeypatch,
    include_mapped_outcome,
):
    *_upstream, result = _build(monkeypatch)
    quarantine = (
        ib2c.Form4PitSecurityMappingOutcome.NO_ACTIVE_SECURITY_TITLE_MAPPING_QUARANTINED
    )
    mapped = ib2c.Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY
    outcomes = (mapped, quarantine) if include_mapped_outcome else (quarantine,)
    row = _rehash_diagnostic_row(
        result.rows[0],
        security_mapping_outcomes=outcomes,
        provisional_group_key=None,
        disposition=(
            diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
        ),
        quarantine_reasons=(
            diagnostics_module.Form4ProvisionalLotQuarantineReason.SECURITY_MAPPING_QUARANTINED,
        ),
    )
    with pytest.raises(diagnostics_module.Form4ProvisionalLotDiagnosticsError):
        type(row).__post_init__(row, diagnostics_module._ROW_FACTORY_TOKEN)


@pytest.mark.parametrize(
    "missing_field",
    ("security_class_normalized", "title_mapping_kind"),
)
def test_constructor_replay_refuses_incomplete_mapped_diagnostic_state(
    monkeypatch,
    missing_field,
):
    *_upstream, result = _build(monkeypatch)
    row = _rehash_diagnostic_row(
        result.rows[0],
        **{missing_field: None},
    )

    assert row.security_mapping_outcomes == (
        ib2c.Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="mapped diagnostic state is incomplete",
    ):
        type(row).__post_init__(row, diagnostics_module._ROW_FACTORY_TOKEN)


def test_result_replays_groups_instead_of_trusting_coherent_group_hashes(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    forged_group = _rehash_group(
        result.groups[0],
        total_shares=result.groups[0].total_shares + Decimal("1"),
    )
    forged_identity = _rehash_identity(
        result.identity,
        provisional_group_inventory_hash=hash_payload(
            [forged_group.to_payload()]
        ),
    )
    forged_result = _forge(
        result,
        identity=forged_identity,
        groups=(forged_group,),
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="do not replay from rows",
    ):
        type(result).__post_init__(
            forged_result,
            diagnostics_module._RESULT_FACTORY_TOKEN,
        )


def test_result_binds_threshold_counts_even_when_identity_is_rehashed(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    assert result.identity.threshold_met_group_count == 1
    forged_identity = _rehash_identity(
        result.identity,
        threshold_met_group_count=0,
        below_threshold_group_count=1,
    )
    forged_result = _forge(result, identity=forged_identity)
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="counts or hashes are inconsistent",
    ):
        type(result).__post_init__(
            forged_result,
            diagnostics_module._RESULT_FACTORY_TOKEN,
        )


@pytest.mark.parametrize("cleared_member", ("original", "amendment"))
def test_result_replay_requires_exact_amendment_family_membership_per_row(
    monkeypatch,
    cleared_member,
):
    original = ib2b._spec(1)
    amendment = ib2b._spec(
        2,
        year=2027,
        month=1,
        day=4,
        form="4/A",
        amends_accession=original.accession,
    )
    *_upstream, result = _build(monkeypatch, (original, amendment))
    target_accession = (
        original.accession if cleared_member == "original" else amendment.accession
    )
    rows = []
    for row in result.rows:
        family_flag = row.accession_number != target_accession
        reasons = diagnostics_module._quarantine_reasons_from_state(
            amendment_family_has_supplied_amendment=family_flag,
            upstream_disposition=row.upstream_disposition,
            identity_disposition=row.identity_disposition,
            owner_attribution_outcomes=row.owner_attribution_outcomes,
            security_mapping_outcomes=row.security_mapping_outcomes,
            attributed_owner_cik=row.attributed_owner_cik,
            attributed_owner_candidate_id=row.attributed_owner_candidate_id,
            security_id=row.security_id,
            share_class_id=row.share_class_id,
            security_class_normalized=row.security_class_normalized,
            transaction_date=row.transaction_date,
            shares=row.shares,
            price_per_share=row.price_per_share,
            purchase_value_usd=row.purchase_value_usd,
        )
        disposition = (
            diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
            if not reasons
            else diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
        )
        group_key = (
            hash_payload(
                diagnostics_module._group_key_payload(
                    attributed_owner_cik=row.attributed_owner_cik,
                    attributed_owner_candidate_id=row.attributed_owner_candidate_id,
                    security_id=row.security_id,
                    share_class_id=row.share_class_id,
                    transaction_date=row.transaction_date,
                )
            )
            if not reasons
            else None
        )
        rows.append(
            _rehash_diagnostic_row(
                row,
                amendment_family_has_supplied_amendment=family_flag,
                quarantine_reasons=reasons,
                disposition=disposition,
                provisional_group_key=group_key,
            )
        )
    rows = tuple(rows)
    groups = diagnostics_module._aggregate_provisional_groups(rows)
    candidate_count = sum(
        row.disposition
        is diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
        for row in rows
    )
    threshold_met_count = sum(
        group.meets_provisional_minimum_purchase_value for group in groups
    )
    forged_identity = _rehash_identity(
        result.identity,
        diagnostic_row_inventory_hash=hash_payload(
            [row.to_payload() for row in rows]
        ),
        provisional_group_inventory_hash=hash_payload(
            [group.to_payload() for group in groups]
        ),
        provisional_candidate_row_count=candidate_count,
        quarantined_row_count=len(rows) - candidate_count,
        provisional_group_count=len(groups),
        threshold_met_group_count=threshold_met_count,
        below_threshold_group_count=len(groups) - threshold_met_count,
        amendment_family_quarantined_row_count=sum(
            row.amendment_family_has_supplied_amendment for row in rows
        ),
    )
    forged_result = _forge(
        result,
        identity=forged_identity,
        rows=rows,
        groups=groups,
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="counts or hashes are inconsistent",
    ):
        type(result).__post_init__(
            forged_result,
            diagnostics_module._RESULT_FACTORY_TOKEN,
        )


def test_result_replay_requires_every_form4a_to_flag_its_own_family(monkeypatch):
    original = ib2b._spec(1)
    amendment = ib2b._spec(
        2,
        year=2027,
        month=1,
        day=4,
        form="4/A",
        amends_accession=original.accession,
    )
    *_upstream, result = _build(monkeypatch, (original, amendment))
    rows = []
    for row in result.rows:
        reasons = diagnostics_module._quarantine_reasons_from_state(
            amendment_family_has_supplied_amendment=False,
            upstream_disposition=row.upstream_disposition,
            identity_disposition=row.identity_disposition,
            owner_attribution_outcomes=row.owner_attribution_outcomes,
            security_mapping_outcomes=row.security_mapping_outcomes,
            attributed_owner_cik=row.attributed_owner_cik,
            attributed_owner_candidate_id=row.attributed_owner_candidate_id,
            security_id=row.security_id,
            share_class_id=row.share_class_id,
            security_class_normalized=row.security_class_normalized,
            transaction_date=row.transaction_date,
            shares=row.shares,
            price_per_share=row.price_per_share,
            purchase_value_usd=row.purchase_value_usd,
        )
        disposition = (
            diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
            if not reasons
            else diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
        )
        group_key = (
            hash_payload(
                diagnostics_module._group_key_payload(
                    attributed_owner_cik=row.attributed_owner_cik,
                    attributed_owner_candidate_id=row.attributed_owner_candidate_id,
                    security_id=row.security_id,
                    share_class_id=row.share_class_id,
                    transaction_date=row.transaction_date,
                )
            )
            if not reasons
            else None
        )
        rows.append(
            _rehash_diagnostic_row(
                row,
                amendment_family_has_supplied_amendment=False,
                quarantine_reasons=reasons,
                disposition=disposition,
                provisional_group_key=group_key,
            )
        )
    rows = tuple(rows)
    groups = diagnostics_module._aggregate_provisional_groups(rows)
    candidate_count = sum(
        row.disposition
        is diagnostics_module.Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
        for row in rows
    )
    threshold_met_count = sum(
        group.meets_provisional_minimum_purchase_value for group in groups
    )
    forged_identity = _rehash_identity(
        result.identity,
        amendment_family_inventory_hash=hash_payload([]),
        diagnostic_row_inventory_hash=hash_payload(
            [row.to_payload() for row in rows]
        ),
        provisional_group_inventory_hash=hash_payload(
            [group.to_payload() for group in groups]
        ),
        provisional_candidate_row_count=candidate_count,
        quarantined_row_count=len(rows) - candidate_count,
        provisional_group_count=len(groups),
        threshold_met_group_count=threshold_met_count,
        below_threshold_group_count=len(groups) - threshold_met_count,
        amendment_family_quarantined_count=0,
        amendment_family_quarantined_row_count=0,
    )
    forged_result = _forge(
        result,
        identity=forged_identity,
        amendment_family_original_accessions=(),
        rows=rows,
        groups=groups,
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="counts or hashes are inconsistent",
    ):
        type(result).__post_init__(
            forged_result,
            diagnostics_module._RESULT_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    ("limit_name", "expected"),
    (
        ("MAX_FORM4_PROVISIONAL_LOT_PROJECTION_NODES", "node bound"),
        ("MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS", "text bound"),
        ("MAX_FORM4_PROVISIONAL_LOT_PROJECTION_DEPTH", "depth bound"),
    ),
)
def test_output_projection_resource_guards_are_load_bearing(
    monkeypatch,
    limit_name,
    expected,
):
    evidence, inventory, grouping, mapping = _build_upstream(monkeypatch)
    monkeypatch.setattr(diagnostics_module, limit_name, -1)
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match=expected,
    ):
        diagnostics_module.build_form4_provisional_lot_diagnostics(
            mapping,
            grouping,
            inventory,
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_decimal_extreme_exponent_is_refused_before_canonical_expansion(
    monkeypatch,
):
    extreme = Decimal("1e1000000")
    real_decimal_text = diagnostics_module.decimal_text

    def reject_expansion(value):
        if value is extreme:
            raise AssertionError("extreme Decimal reached canonical expansion")
        return real_decimal_text(value)

    monkeypatch.setattr(diagnostics_module, "decimal_text", reject_expansion)
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="Decimal bound",
    ):
        diagnostics_module._decimal(extreme, label="adversarial decimal")


@pytest.mark.parametrize(
    ("projector_name", "expected"),
    (
        ("_project_output", "output projection exceeds the text bound"),
        (
            "_project_diagnostics_provenance",
            "diagnostics provenance exceeds the text bound",
        ),
    ),
)
def test_decimal_projection_charges_canonical_text_budget(
    monkeypatch,
    projector_name,
    expected,
):
    monkeypatch.setattr(
        diagnostics_module,
        "MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS",
        0,
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match=expected,
    ):
        getattr(diagnostics_module, projector_name)(Decimal("1"))


def test_group_count_resource_guard_is_load_bearing(monkeypatch):
    evidence, inventory, grouping, mapping = _build_upstream(monkeypatch)
    monkeypatch.setattr(diagnostics_module, "MAX_FORM4_PROVISIONAL_LOT_GROUPS", 0)
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="result state is invalid",
    ):
        diagnostics_module.build_form4_provisional_lot_diagnostics(
            mapping,
            grouping,
            inventory,
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_row_count_preflight_refuses_before_output_projection(monkeypatch):
    evidence, inventory, grouping, mapping = _build_upstream(monkeypatch)

    def projection_must_not_run(*_args, **_kwargs):
        raise AssertionError("output projection ran before row-count preflight")

    monkeypatch.setattr(
        diagnostics_module,
        "MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS",
        0,
    )
    monkeypatch.setattr(
        diagnostics_module,
        "_project_output",
        projection_must_not_run,
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="snapshot shape exceeds a resource bound",
    ):
        diagnostics_module.build_form4_provisional_lot_diagnostics(
            mapping,
            grouping,
            inventory,
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_amendment_family_count_preflights_before_element_scan(monkeypatch):
    *_upstream, result = _build(monkeypatch)

    class _ElementScanBomb:
        def fullmatch(self, _value):
            raise AssertionError("amendment-family element scan ran before count guard")

    overlong = (
        "0000000000-00-000000",
    ) * (diagnostics_module.MAX_FORM4_OBSERVED_IDENTITY_FILINGS + 1)
    forged_result = _forge(
        result,
        amendment_family_original_accessions=overlong,
    )
    monkeypatch.setattr(diagnostics_module, "_ACCESSION_RE", _ElementScanBomb())
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="result state is invalid",
    ):
        type(result).__post_init__(
            forged_result,
            diagnostics_module._RESULT_FACTORY_TOKEN,
        )


def test_identity_caps_amendment_family_count_to_filing_bound(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    forged = _forge(
        result.identity,
        amendment_family_quarantined_count=(
            diagnostics_module.MAX_FORM4_OBSERVED_IDENTITY_FILINGS + 1
        ),
    )
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="identity counts are invalid",
    ):
        type(result.identity).__post_init__(
            forged,
            diagnostics_module._IDENTITY_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    ("field_name", "enum_type", "member"),
    (
        (
            "owner_attribution_outcomes",
            ib2b.Form4OwnerAttributionOutcome,
            ib2b.Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
        ),
        (
            "security_mapping_outcomes",
            ib2c.Form4PitSecurityMappingOutcome,
            ib2c.Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,
        ),
        (
            "parser_outcomes",
            ClassificationOutcome,
            ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,
        ),
        (
            "parser_diagnostics",
            TransactionDiagnostic,
            TransactionDiagnostic.TEN_B5_1_PLAN,
        ),
        (
            "quarantine_reasons",
            diagnostics_module.Form4ProvisionalLotQuarantineReason,
            diagnostics_module.Form4ProvisionalLotQuarantineReason.UPSTREAM_PARSER_QUARANTINED,
        ),
    ),
)
def test_row_enum_tuple_counts_preflight_before_duplicate_set_work(
    monkeypatch,
    field_name,
    enum_type,
    member,
):
    *_upstream, result = _build(monkeypatch)
    overlong = (member,) * (len(enum_type) + 1)
    real_set = set

    def guarded_set(value):
        if value is overlong:
            raise AssertionError("duplicate-set work ran before enum count guard")
        return real_set(value)

    forged = _forge(result.rows[0], **{field_name: overlong})
    monkeypatch.setitem(diagnostics_module.__dict__, "set", guarded_set)
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="diagnostic dispositions are invalid",
    ):
        type(result.rows[0]).__post_init__(
            forged,
            diagnostics_module._ROW_FACTORY_TOKEN,
        )


def test_output_projection_refuses_cycles():
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(
        diagnostics_module.Form4ProvisionalLotDiagnosticsError,
        match="contains a cycle",
    ):
        diagnostics_module._project_output(cyclic)


def test_mapping_mutation_during_build_is_detected_and_restored(
    monkeypatch,
):
    evidence, inventory, grouping, mapping = _build_upstream(monkeypatch)
    real_validate = diagnostics_module._validate_upstream_chain
    original_mapping_id = mapping.identity.mapping_id

    def mutate_after_capture(*args, **kwargs):
        validated = real_validate(*args, **kwargs)
        object.__setattr__(mapping.identity, "mapping_id", "changed-during-build")
        return validated

    monkeypatch.setattr(
        diagnostics_module,
        "_validate_upstream_chain",
        mutate_after_capture,
    )
    try:
        with pytest.raises(
            diagnostics_module.Form4ProvisionalLotDiagnosticsError,
            match="changed",
        ):
            diagnostics_module.build_form4_provisional_lot_diagnostics(
                mapping,
                grouping,
                inventory,
                evidence,
                builder_git_commit=BUILDER_COMMIT,
            )
    finally:
        object.__setattr__(mapping.identity, "mapping_id", original_mapping_id)


def test_evidence_mutation_during_build_is_detected_and_restored(monkeypatch):
    evidence, inventory, grouping, mapping = _build_upstream(monkeypatch)
    real_validate_report = diagnostics_module._validate_rebuilt_report
    original_hash = evidence.identity.parsed_corpus_hash

    def mutate_after_report(*args, **kwargs):
        report = real_validate_report(*args, **kwargs)
        object.__setattr__(evidence.identity, "parsed_corpus_hash", "0" * 64)
        return report

    monkeypatch.setattr(
        diagnostics_module,
        "_validate_rebuilt_report",
        mutate_after_report,
    )
    try:
        with pytest.raises(
            diagnostics_module.Form4ProvisionalLotDiagnosticsError,
            match="inventory and rebuilt evidence report disagree|evidence changed",
        ):
            diagnostics_module.build_form4_provisional_lot_diagnostics(
                mapping,
                grouping,
                inventory,
                evidence,
                builder_git_commit=BUILDER_COMMIT,
            )
    finally:
        object.__setattr__(
            evidence.identity,
            "parsed_corpus_hash",
            original_hash,
        )


def test_evidence_enum_to_string_mutation_during_build_is_detected_and_restored(
    monkeypatch,
):
    evidence, inventory, grouping, mapping = _build_upstream(monkeypatch)
    real_validate_report = diagnostics_module._validate_rebuilt_report
    transaction = evidence.as_filed_corpus.filings[0].transactions[0]
    original_outcomes = transaction.outcomes
    string_outcomes = tuple(outcome.value for outcome in original_outcomes)

    def mutate_after_report(*args, **kwargs):
        report = real_validate_report(*args, **kwargs)
        object.__setattr__(transaction, "outcomes", string_outcomes)
        return report

    monkeypatch.setattr(
        diagnostics_module,
        "_validate_rebuilt_report",
        mutate_after_report,
    )
    try:
        with pytest.raises(
            diagnostics_module.Form4ProvisionalLotDiagnosticsError,
            match="inventory and rebuilt evidence report disagree|evidence changed",
        ):
            diagnostics_module.build_form4_provisional_lot_diagnostics(
                mapping,
                grouping,
                inventory,
                evidence,
                builder_git_commit=BUILDER_COMMIT,
            )
    finally:
        object.__setattr__(transaction, "outcomes", original_outcomes)


def test_factory_result_has_an_unchanged_process_local_seal(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    fingerprint = diagnostics_module._diagnostics_provenance_fingerprint(result)
    assert diagnostics_module._matches_factory_created_diagnostics_fingerprint(
        result,
        fingerprint,
    )
    assert diagnostics_module._is_factory_created_form4_provisional_lot_diagnostics(
        result
    )
    object.__setattr__(result.identity, "diagnostics_id", "changed-after-build")
    assert not diagnostics_module._is_factory_created_form4_provisional_lot_diagnostics(
        result
    )


def test_process_seal_detects_enum_to_string_type_erasure(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    object.__setattr__(
        result.rows[0],
        "disposition",
        result.rows[0].disposition.value,
    )
    assert not diagnostics_module._is_factory_created_form4_provisional_lot_diagnostics(
        result
    )


def test_process_seal_detects_tuple_to_list_type_erasure(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    object.__setattr__(result, "rows", list(result.rows))
    assert not diagnostics_module._is_factory_created_form4_provisional_lot_diagnostics(
        result
    )


def test_process_seal_detects_equal_decimal_representation_change(monkeypatch):
    *_upstream, result = _build(monkeypatch)
    original = result.rows[0].shares
    assert original is not None
    decimal_tuple = original.as_tuple()
    representation_variant = Decimal(
        (
            decimal_tuple.sign,
            decimal_tuple.digits + (0,),
            decimal_tuple.exponent - 1,
        )
    )
    assert representation_variant == original
    assert representation_variant.as_tuple() != decimal_tuple

    object.__setattr__(result.rows[0], "shares", representation_variant)
    assert not diagnostics_module._is_factory_created_form4_provisional_lot_diagnostics(
        result
    )


def test_ib2d_module_has_exact_offline_import_surface_and_no_float():
    source = Path(diagnostics_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imports == {
        "__future__",
        "hashlib",
        "re",
        "threading",
        "weakref",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "data.financial_primitives",
        "data.hashing",
        "research.insider_buying.contracts",
        "research.insider_buying.form4_multi_period_amendment_evidence",
        "research.insider_buying.form4_observed_identity_inventory",
        "research.insider_buying.form4_pit_security_mapping",
        "research.insider_buying.form4_provisional_disposition_report",
        "research.insider_buying.form4_sec_entity_grouping",
    }
    assert not any(
        isinstance(node, ast.Constant) and type(node.value) is float
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"__import__", "eval", "exec", "float", "open"}
        for node in ast.walk(tree)
    )
    assert imports.isdisjoint(
        {
            "QuantConnect",
            "aiohttp",
            "alpaca",
            "execution",
            "httpx",
            "pandas",
            "requests",
            "socket",
            "urllib",
            "yfinance",
        }
    )


def test_ib2d_module_and_package_exports_are_explicit_and_exact():
    expected = [
        "FORM4_PROVISIONAL_LOT_DIAGNOSTICS_VERSION",
        "FORM4_PROVISIONAL_LOT_THRESHOLD_USD",
        "Form4ProvisionalLotDiagnosticRow",
        "Form4ProvisionalLotDiagnostics",
        "Form4ProvisionalLotDiagnosticsError",
        "Form4ProvisionalLotDiagnosticsIdentity",
        "Form4ProvisionalLotDisposition",
        "Form4ProvisionalLotGroup",
        "Form4ProvisionalLotQuarantineReason",
        "Form4ProvisionalLotThresholdDiagnostic",
        "MAX_FORM4_PROVISIONAL_LOT_GROUPS",
        "MAX_FORM4_PROVISIONAL_LOT_PROJECTION_DEPTH",
        "MAX_FORM4_PROVISIONAL_LOT_PROJECTION_NODES",
        "build_form4_provisional_lot_diagnostics",
    ]
    assert diagnostics_module.__all__ == expected
    package_exports = [
        name for name in expected if not name.startswith("MAX_FORM4_PROVISIONAL")
    ]
    assert all(name in insider_package.__all__ for name in package_exports)
    assert all(
        getattr(insider_package, name) is getattr(diagnostics_module, name)
        for name in package_exports
    )
