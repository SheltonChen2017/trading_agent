"""Synthetic tests for the preparation-only 82-quarter master request plan."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from data.hashing import hash_payload
from research.insider_buying.sec_zip_corpus_census import (
    SecZipCensusQuarter,
    _expected_url,
)
from research.insider_buying_sec_master82_acquisition import (
    MAX_DISTINCT_ARTIFACTS,
    MAX_TOTAL_ATTEMPTS,
    PINNED_MASTER_URL_INVENTORY_SHA256,
    RETAINED_CENSUS_SHA256,
    SecMaster82PreparationError,
    _PERIODS,
    _build_plan,
    prepare_retained_master82_acquisition,
)


def _quarters() -> tuple[SecZipCensusQuarter, ...]:
    return tuple(
        SecZipCensusQuarter(
            period=period,
            zip_sha256="a" * 64,
            zip_size_bytes=1,
            source_url_from_retained_manifest=_expected_url(period),
            local_last_write_utc_unverified="2026-09-24T22:52:19.7647157Z",
            submission_member_sha256="b" * 64,
            submission_member_size_bytes=1,
            submission_header_line_sha256="c" * 64,
            submission_headers=(
                "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT",
                "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL",
            ),
            form_counts=(0, 0, 1, 1, 0, 0),
        )
        for period in _PERIODS
    )


def _synthetic_plan():
    return _build_plan(
        census_scope="synthetic_test_census",
        census_sha256="d" * 64,
        quarters=_quarters(),
        contact_email="research@example.org",
    )


def test_exact_82_urls_and_source_zip_bindings_are_pinned() -> None:
    plan = _synthetic_plan()
    assert len(plan.requests) == MAX_DISTINCT_ARTIFACTS == 82
    assert plan.requests[0].url == (
        "https://www.sec.gov/Archives/edgar/full-index/2006/QTR1/master.gz"
    )
    assert plan.requests[-1].url == (
        "https://www.sec.gov/Archives/edgar/full-index/2026/QTR2/master.gz"
    )
    assert all(request.retained_zip_sha256 == "a" * 64 for request in plan.requests)
    assert hash_payload([
        {"period": request.period, "url": request.url} for request in plan.requests
    ]) == PINNED_MASTER_URL_INVENTORY_SHA256
    assert plan.request_inventory_sha256 == hash_payload([
        request.to_payload() for request in plan.requests
    ])
    assert plan.sha256 == hash_payload(plan.to_payload())


def test_policy_is_explicitly_non_executable_and_zero_authority() -> None:
    plan = _synthetic_plan()
    payload = plan.to_payload()
    assert "contact_email" not in payload
    assert payload["identifying_contact_provided"] is True
    assert "research@example.org" not in repr(plan)
    policy = payload["request_policy_for_future_review"]
    authority = payload["authority"]
    assert policy["exact_distinct_artifacts"] == 82
    assert policy["max_attempts_per_artifact"] == 3
    assert policy["max_total_attempts"] == MAX_TOTAL_ATTEMPTS == 246
    assert policy["minimum_interval_between_transport_completions_and_next_dispatch_ns"] == 500_000_000
    assert policy["ideal_first_to_last_dispatch_floor_ms_excluding_work_and_backoff"] == 40_500
    assert policy["stop_on_http_403_or_429"] is True
    assert policy["redirects_forbidden"] is True
    assert policy["fresh_outside_git_immutable_output_journal_report_required"] is True
    assert authority["operational_runner_implemented"] is False
    assert authority["network_request_made"] is False
    assert authority["output_journal_report_published"] is False
    assert authority["canonical_evidence"] is False
    assert authority["qc_backtest_authorized"] is False
    assert authority["research_looks"] == 0


@pytest.mark.parametrize("bad", ["research", "research@example.org:443", "x@example.org\nInjected", "x@y", "a" * 255 + "@z.org"])
def test_identifying_contact_is_required(bad: str) -> None:
    with pytest.raises(SecMaster82PreparationError, match="REFUSED"):
        _build_plan(
            census_scope="synthetic_test_census", census_sha256="d" * 64,
            quarters=_quarters(), contact_email=bad,
        )


def test_missing_or_reordered_quarter_refuses_before_plan() -> None:
    quarters = _quarters()
    for changed in (quarters[:-1], quarters[1:] + quarters[:1], quarters[:-1] + quarters[-2:-1]):
        with pytest.raises(SecMaster82PreparationError, match="REFUSED:.*incomplete or reordered"):
            _build_plan(
                census_scope="synthetic_test_census", census_sha256="d" * 64,
                quarters=changed, contact_email="research@example.org",
            )


def test_changed_request_url_or_zip_digest_refuses_without_partial_acceptance() -> None:
    plan = _synthetic_plan()
    with pytest.raises(SecMaster82PreparationError, match="REFUSED"):
        replace(plan.requests[0], url="https://example.org/master.gz")
    changed = replace(plan.requests[0], retained_zip_sha256="e" * 64)
    with pytest.raises(SecMaster82PreparationError, match="REFUSED:.*fingerprint changed"):
        replace(plan, requests=(changed,) + plan.requests[1:])
    with pytest.raises(SecMaster82PreparationError, match="REFUSED:.*fingerprint changed"):
        replace(plan, request_inventory_sha256="0" * 64)


def test_retained_label_refuses_synthetic_census_or_wrong_target_count() -> None:
    with pytest.raises(SecMaster82PreparationError, match="REFUSED:.*retained census fingerprint"):
        replace(_synthetic_plan(), census_scope="retained_noncanonical_zip_census")
    with pytest.raises(SecMaster82PreparationError, match="REFUSED:.*retained census fingerprint"):
        replace(
            _synthetic_plan(), census_scope="retained_noncanonical_zip_census",
            census_sha256=RETAINED_CENSUS_SHA256,
        )


def test_direct_constructor_cannot_forge_retained_census_binding() -> None:
    synthetic = _synthetic_plan()
    forged_first = replace(
        synthetic.requests[0],
        form4_target_count=4_034_227 - (82 * 2 - 1),
    )
    forged_requests = (forged_first,) + synthetic.requests[1:]
    with pytest.raises(SecMaster82PreparationError, match="REFUSED:.*source census"):
        replace(
            synthetic,
            census_scope="retained_noncanonical_zip_census",
            census_sha256=RETAINED_CENSUS_SHA256,
            requests=forged_requests,
            request_inventory_sha256=hash_payload([
                request.to_payload() for request in forged_requests
            ]),
        )


def test_public_entry_refuses_non_census_and_module_has_no_transport() -> None:
    with pytest.raises(SecMaster82PreparationError, match="REFUSED:.*source-bound census"):
        prepare_retained_master82_acquisition(object(), contact_email="research@example.org")
    import research.insider_buying_sec_master82_acquisition as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not imports.intersection({"http", "urllib", "requests", "socket", "subprocess"})
    assert not hasattr(module, "run_master82_acquisition")
    assert not hasattr(module, "_sec_transport")
