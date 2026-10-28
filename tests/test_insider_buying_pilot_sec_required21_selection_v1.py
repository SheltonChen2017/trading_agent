"""Invented full25-quarter source images; no private input or transport access."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody stack")
from research import insider_buying_pilot_sec_required21_selection_v1 as m


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("invented_required21_source_fixture",
        Path(__file__).with_name("test_insider_buying_pilot_sec_fresh_selection.py"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper, helper.corpus.__wrapped__(tmp_path_factory)


def _pipeline(corpus, *, consumed=(), limit=8, supplied=None, mutate=None, exposures=()):
    helper, fixture = corpus
    _unused, generated, completed, emitted = helper._pipeline(fixture, supplied=supplied, consumed=exposures)
    builder = m.Required21SelectionBuilder(consumed_accessions=tuple(sorted(consumed)),
        consumption_sha256="a" * 64, limit=limit)
    for row in emitted:
        item = deepcopy(row)
        if mutate is not None:
            mutate(item)
        builder.consume(item)
    return builder, generated, completed, emitted


def _finish(pipeline, **changes):
    builder, generated, completed, _ = pipeline
    arguments = {"source_roster": generated, "parent_audit": completed,
        "expected_roster_sha256": generated.sha256, "expected_audit_sha256": completed.sha256}
    arguments.update(changes)
    return builder.finish(**arguments)


def _fixture_selection(corpus, *, consumed=(), limit=8, supplied=None):
    """Genuine invented full25 factory for the separate protected capture tests."""
    return _finish(_pipeline(corpus, consumed=consumed, limit=limit, supplied=supplied))


def _eligible(emitted, consumed=()):
    return [row for row in emitted if row["source"]["period"] in m.REQUIRED_PERIODS
        and row["fresh_locatable_candidate"] and row["source"]["accession_number"] not in consumed]


def test_complete25_source_selects_required21_first8_not_old_context_or_pilot_prefix(corpus):
    pipeline = _pipeline(corpus)
    sealed = _finish(pipeline)
    value = sealed.to_payload()
    eligible = _eligible(pipeline[3])
    assert value["selected_count"] == 8 and value["underfilled"] is False
    assert [row["request"] for row in value["requests"]] == [row["request"] for row in eligible[:8]]
    assert value["requests"][0]["request"]["period"] == "2020Q4"
    assert value["requests"][2]["request"]["period"] == "2021Q1"
    assert value["required21_provisional_fresh_count"] == len(eligible)
    assert tuple(row["period"] for row in value["quarter_bindings"]) == m.CONTEXT_PERIODS
    assert len(m.REQUIRED_PERIODS) == 21 and len(m.CONTEXT_PERIODS) == 25
    assert m.validate_required21_selection(sealed) == m.validate_selection_payload(value) == value
    assert sealed.sha256 == m._sha(sealed.canonical_bytes())
    assert value["source_roster_sha256"] == pipeline[1].sha256
    assert value["parent_audit_sha256"] == pipeline[2].sha256
    assert value["consumption_sha256"] == "a" * 64
    assert value["consumption_authenticity_verified_here"] is False
    assert all(flag is False if type(flag) is bool else flag == 0 for flag in value["authority"].values())
    assert value["dispatch_authorized"] is value["canonical_admitted"] is False
    assert b"PRIVATE FINANCIAL SENTINEL" not in sealed.canonical_bytes()


def test_all_six_forms_all25_hashes_and_required21_counts_are_conserved(corpus):
    pipeline = _pipeline(corpus)
    value = _finish(pipeline).to_payload()
    completed = pipeline[2].to_payload()
    assert value["quarter_bindings"] == completed["quarters"]
    assert value["parent_context_counts"] == completed["context_counts"]
    assert value["source_roster_counts"] == pipeline[1].to_payload()["counts"]
    for stem in m._STEMS:
        for suffix in ("_jsonl_sha256", "_jsonl_bytes"):
            assert value[stem + suffix] == completed[stem + suffix]
    assert value["required21_counts"] == {key: sum(row["counts"][key] for row in completed["quarters"]
        if row["period"] in m.REQUIRED_PERIODS) for key in m.audit._COUNTS}
    assert all(set(row["source_form_counts"]) == set(m.audit.FORMS) for row in value["quarter_bindings"])


def test_verified_external_consumption_excludes_prefix_and_root_is_not_fabricated(corpus):
    pipeline = _pipeline(corpus)
    consumed = tuple(sorted(row["source"]["accession_number"] for row in _eligible(pipeline[3])[:3]))
    following = _pipeline(corpus, consumed=consumed)
    value = _finish(following).to_payload()
    assert [row["request"] for row in value["requests"]] == [row["request"] for row in _eligible(following[3], consumed)[:8]]
    assert value["consumed_accessions"] == list(consumed)
    assert value["consumed_accessions_sha256"] == m._sha(m._raw(list(consumed)))
    assert value["consumption_sha256"] == "a" * 64 != value["consumed_accessions_sha256"]


@pytest.mark.parametrize("state", sorted(m.audit._STATES))
def test_compiler_consumed_reserved_and_ambiguous_states_are_suppressed(corpus, state):
    pipeline = _pipeline(corpus)
    target = _eligible(pipeline[3])[0]["source"]
    value = _finish(_pipeline(corpus, exposures=[(target, state)])).to_payload()
    assert target["accession_number"] not in {row["request"]["accession_number"] for row in value["requests"]}
    assert value["required21_counts"]["prior_consumed_targets"] == 1


@pytest.mark.parametrize("remaining", (0, 1, 7))
def test_underfill_is_honest_and_never_borrows_outside_required21(corpus, remaining):
    pipeline = _pipeline(corpus)
    eligible = _eligible(pipeline[3])
    consumed = [row["source"]["accession_number"] for row in eligible[remaining:]]
    value = _finish(_pipeline(corpus, consumed=consumed)).to_payload()
    assert value["selected_count"] == value["required21_provisional_fresh_count"] == remaining
    assert value["underfilled"] is True
    assert [row["request"] for row in value["requests"]] == [row["request"] for row in eligible[:remaining]]


@pytest.mark.parametrize("limit", (1, 8))
def test_exact_limit_within_first8_is_allowed(corpus, limit):
    value = _fixture_selection(corpus, limit=limit).to_payload()
    assert value["limit"] == value["selected_count"] == limit


@pytest.mark.parametrize("limit", (True, False, 0, 9, 1.0, "8"))
def test_other_or_boolean_limits_refuse(limit):
    with pytest.raises(m.Required21SelectionError):
        m.Required21SelectionBuilder(consumed_accessions=(), consumption_sha256="a" * 64, limit=limit)


@pytest.mark.parametrize("consumed", ([], ("bad",), ("0000000001-20-000001",) * 2,
    ("0000000001-21-000001", "0000000001-20-000001"), (True,)))
def test_consumption_requires_sorted_unique_exact_accessions(consumed):
    with pytest.raises(m.Required21SelectionError):
        m.Required21SelectionBuilder(consumed_accessions=consumed, consumption_sha256="a" * 64)


@pytest.mark.parametrize("fault", ("roster_pin", "audit_pin", "fake_roster", "fake_audit", "cloned_roster", "cloned_audit"))
def test_actual_factory_seals_and_external_roots_are_required(corpus, fault):
    pipeline = _pipeline(corpus)
    changes = {}
    if fault == "roster_pin": changes["expected_roster_sha256"] = "f" * 64
    if fault == "audit_pin": changes["expected_audit_sha256"] = "f" * 64
    if fault == "fake_roster": changes["source_roster"] = SimpleNamespace(to_payload=pipeline[1].to_payload, sha256=pipeline[1].sha256)
    if fault == "fake_audit": changes["parent_audit"] = SimpleNamespace(to_payload=pipeline[2].to_payload, sha256=pipeline[2].sha256)
    if fault == "cloned_roster": changes["source_roster"] = replace(pipeline[1])
    if fault == "cloned_audit": changes["parent_audit"] = replace(pipeline[2])
    with pytest.raises(ValueError):
        _finish(pipeline, **changes)
    with pytest.raises(m.Required21SelectionError, match="closed"):
        _finish(pipeline)


def test_late_repeat_in_last_context_quarter_refuses_whole_prefix_without_refill(corpus):
    helper, fixture = corpus
    target = _eligible(_pipeline(corpus)[3])[0]["source"]
    original_helper, supplied, _, _ = fixture
    changed = original_helper._changed(supplied, "2026Q1", lambda raw:
        original_helper._fields(raw, 3, "ACCESSION_NUMBER", target["accession_number"]))
    # Independently rederive the invented 82-image census/header/selector
    # evidence, including this new accession-year mismatch, from source bytes.
    manifest, images, _ = changed
    pure = original_helper.m.selector.pure
    bindings = pure.census._manifest_bindings(manifest)
    profile = pure.build_retained_82q_schema_profile_candidate()
    quarters = tuple(pure.census._census_quarter(item.raw_bytes, binding)
        for item, binding in zip(images, bindings, strict=True))
    headers = tuple(pure.headers._quarter_headers(item.raw_bytes, item.period, profile) for item in images)
    census = pure._census_receipt(quarters, m._sha(manifest), len(manifest), True)
    header = pure._header_receipt(headers, census.sha256, True)
    selected = pure.select_affected_quarters(intake_manifest_raw=manifest,
        expected_manifest_sha256=m._sha(manifest), quarter_inputs=iter(images),
        expected_census_sha256=census.sha256, expected_header_preflight_sha256=header.sha256,
        fixture_only=True).to_payload()
    # Existing fixture parser exercises the retained-control schema, while
    # the derived new roster/audit/selection still all carry fixture_only=True.
    selected["fixture_only"] = False
    changed = manifest, images, selected
    pipeline = _pipeline(corpus, supplied=changed)
    assert pipeline[2].to_payload()["context_counts"]["cross_quarter_repeat_targets"] == 1
    with pytest.raises(m.Required21SelectionError, match="late_selected_repeat"):
        _finish(pipeline)


@pytest.mark.parametrize("drop", ("prefix", "suffix", "middle"))
def test_no_partial25_stream_can_finish(corpus, drop):
    pipeline = _pipeline(corpus)
    builder = m.Required21SelectionBuilder(consumed_accessions=(), consumption_sha256="a" * 64)
    rows = pipeline[3]
    chosen = rows[1:] if drop == "prefix" else rows[:-1] if drop == "suffix" else rows[:20] + rows[21:]
    with pytest.raises(m.Required21SelectionError):
        for row in chosen:
            builder.consume(row)
        builder.finish(source_roster=pipeline[1], parent_audit=pipeline[2],
            expected_roster_sha256=pipeline[1].sha256, expected_audit_sha256=pipeline[2].sha256)


@pytest.mark.parametrize("fault", ("extra", "bool", "source_hash", "authority", "locator", "request"))
def test_source_callback_refusal_poisoning_prevents_skip_and_resume(corpus, fault):
    pipeline = _pipeline(corpus)
    target = _eligible(pipeline[3])[0]
    builder = m.Required21SelectionBuilder(consumed_accessions=(), consumption_sha256="a" * 64)
    with pytest.raises(ValueError):
        for original in pipeline[3]:
            row = deepcopy(original)
            if row["source"] == target["source"]:
                if fault == "extra": row["unknown"] = "PRIVATE"
                elif fault == "bool": row["prior_consumed"] = 0
                elif fault == "source_hash": row["source_record_sha256"] = "f" * 64
                elif fault == "authority": row["canonical_admitted"] = True
                elif fault == "locator": row["selected_locator"]["archive_path"] = "edgar/data/1/0000000001-20-999999.txt"
                else: row["request"]["source_record_ordinal"] = True
            builder.consume(row)
    with pytest.raises(m.Required21SelectionError, match="closed"):
        builder.consume(pipeline[3][0])


def test_changed_nonselected_lastquarter_disposition_still_breaks_full_stream_binding(corpus):
    def mutate(row):
        if row["source"]["period"] == "2026Q1":
            row["disposition"] = "invented_changed_nonselected_disposition"
    pipeline = _pipeline(corpus, mutate=mutate)
    with pytest.raises(m.Required21SelectionError, match="complete_compiler_stream"):
        _finish(pipeline)


@pytest.mark.parametrize("fault", ("count", "bool", "window", "order", "consumed", "quarter_count", "quarter_form",
    "required_count", "source_count", "root", "authority", "authenticity", "policy", "extra"))
def test_detached_metadata_mutations_fail_semantic_validation(corpus, fault):
    value = _fixture_selection(corpus).to_payload()
    if fault == "count": value["selected_count"] += 1
    elif fault == "bool": value["requests"][0]["request"]["source_record_ordinal"] = True
    elif fault == "window": value["quarter_bindings"][0]["period"] = "2006Q1"
    elif fault == "order": value["requests"][0], value["requests"][1] = value["requests"][1], value["requests"][0]
    elif fault == "consumed":
        value["consumed_accessions"] = [value["requests"][0]["request"]["accession_number"]]
        value["consumed_accessions_sha256"] = m._sha(m._raw(value["consumed_accessions"]))
    elif fault == "quarter_count": value["quarter_bindings"][0]["counts"]["source_filings"] += 1
    elif fault == "quarter_form": value["quarter_bindings"][0]["source_form_counts"]["4"] += 1
    elif fault == "required_count": value["required21_counts"]["target_filings"] += 1
    elif fault == "source_count": value["source_roster_counts"]["context_submission_rows"] += 1
    elif fault == "root": value["selected_request_jsonl_sha256"] = "f" * 64
    elif fault == "authority": value["authority"]["sec_dispatches"] = 1
    elif fault == "authenticity": value["consumption_authenticity_verified_here"] = True
    elif fault == "policy": value["policy"]["maximum_selected"] = 9
    else: value["unknown"] = "PRIVATE"
    with pytest.raises(ValueError):
        m.validate_selection_payload(value)


def test_factory_detached_controls_and_clones_cannot_mint_seal(corpus):
    sealed = _fixture_selection(corpus)
    before = sealed.canonical_bytes()
    detached = sealed.to_payload()
    detached["policy"]["maximum_selected"] = 999
    assert sealed.canonical_bytes() == before
    for forged in (replace(sealed), m.Required21Selection(before, object()), sealed.to_payload(),
        SimpleNamespace(canonical_bytes=lambda: before)):
        with pytest.raises(m.Required21SelectionError):
            m.validate_required21_selection(forged)


def test_finished_builder_cannot_consume_or_finish_again(corpus):
    pipeline = _pipeline(corpus)
    _finish(pipeline)
    with pytest.raises(m.Required21SelectionError, match="closed"):
        pipeline[0].consume(pipeline[3][0])
    with pytest.raises(m.Required21SelectionError, match="closed"):
        _finish(pipeline)
