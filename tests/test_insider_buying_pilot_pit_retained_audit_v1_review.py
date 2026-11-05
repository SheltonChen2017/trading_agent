"""Claude review section 375: retained PIT audit guards that mutants survived.

Invented metadata only. Kept beside the module's own test file so these pins do
not change that file's image. No provider, archive, account or QC access occurs.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "pit_retained_audit_test_helpers", Path(__file__).with_name("test_insider_buying_pilot_pit_retained_audit_v1.py"))
t = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(t)
m = t.m


def _refused(values, code):
    with pytest.raises(m.PitRetainedAuditError) as caught:
        m.build_audit(*values)
    assert str(caught.value) == code


def _receipt(complete, family, *, scoped=True):
    return next(r for r in complete["receipts"] if r["family"] == family and r.get("projection") is not None
                and r["projection"]["scoped"] is scoped)


def _check(complete, family):
    projection = _receipt(complete, family)["projection"]
    return next(iter(projection["case_checks"].values()))


@pytest.mark.parametrize(("code", "family"), (
    ("listed", "listed"), ("LISTED", "listed"), ("delisted", "delisted"),
    ("regulatorydelisting", "delisted"), ("voluntarydelisting", "delisted"), ("bankruptcyliquidation", "delisted"),
    ("tickerchange", "ticker_change"), ("tickerchangefrom", "ticker_change"), ("tickerchangeto", "ticker_change"),
    ("merger", "merger"), ("mergerfrom", "merger"), ("mergerto", "merger"),
    ("acquisition", "acquisition"), ("acquisitionby", "acquisition"), ("acquisitionof", "acquisition"),
    ("spinoff", "spinoff"), ("spinoffdividend", "spinoff"), ("spunofffrom", "spinoff"),
    ("dividend", "other"), ("split", "other"), ("relation", "other"), ("initiated", "other"), ("invented", "other"),
))
def test_directional_action_codes_are_counted_in_their_family(code, family):
    cases = t._cases()[:1]
    result = m.build_audit(*t._inputs(cases=cases, action_rows=[t._action(cases[0], 1, action=code)]))
    categories = result["counts"]["action_categories"]
    assert categories[family] == 1
    assert sum(categories.values()) == result["counts"]["action_rows"] == 1


@pytest.mark.parametrize("key", ("response_rows_retained", "response_body_retained",
    "metadata_evidence_can_independently_reparse_response", "all_six_form_coverage_verified",
    "current_label_agreement_is_historical_identity", "naive_acceptance_is_publication_or_timezone_evidence",
    "latest_date_filter_semantics_verified", "financial_values_interpreted"))
def test_provider_projection_cannot_assert_a_retained_or_verified_flag(key):
    values = list(t._inputs())
    _receipt(values[1], "fmp_sec")["projection"][key] = True
    _refused(values, "provider_refused")


def test_provider_projection_cannot_assert_authority():
    values = list(t._inputs())
    _receipt(values[1], "fmp_sec")["projection"]["authority"]["point_in_time_data"] = True
    _refused(values, "authority_refused")


def test_credential_screening_must_stay_an_external_required_control():
    values = list(t._inputs())
    _receipt(values[1], "fmp_sec")["projection"]["credential_screening_is_external_required_control"] = False
    _refused(values, "provider_refused")


@pytest.mark.parametrize("flag", ("acceptance_timezone_verified", "public_known_by_verified", "source_body_equivalence_verified"))
def test_fmp_case_check_cannot_verify_availability_or_body_equivalence(flag):
    values = list(t._inputs())
    _check(values[1], "fmp_sec")[flag] = True
    _refused(values, "provider_refused")


def test_eod_case_check_cannot_verify_historical_identity():
    values = list(t._inputs())
    _check(values[1], "eod_mapping")["historical_identity_verified"] = True
    _refused(values, "provider_refused")


def test_case_check_for_an_unlisted_control_refuses():
    values = list(t._inputs())
    projection = _receipt(values[1], "fmp_sec")["projection"]
    projection["case_checks"]["INVENTED-OTHER-CONTROL"] = next(iter(projection["case_checks"].values()))
    _refused(values, "provider_refused")


def test_unscoped_response_cannot_carry_case_evidence():
    values = list(t._inputs())
    borrowed = dict(_check(values[1], "fmp_sec"))
    _receipt(values[1], "fmp_insider", scoped=False)["projection"]["case_checks"] = {values[0][0]["case_id"]: borrowed}
    _refused(values, "provider_refused")


@pytest.mark.parametrize(("field", "value"), (("exact_accession_rows", 99), ("joint_cik_accession_rows", 99)))
def test_field_counts_cannot_exceed_candidate_rows(field, value):
    values = list(t._inputs())
    _check(values[1], "fmp_sec")[field] = value
    _refused(values, "provider_refused")


def test_joint_rows_cannot_exceed_either_side_of_the_join():
    values = list(t._inputs())
    check = _check(values[1], "fmp_sec")
    check["candidate_rows"] = 5
    check["joint_cik_accession_rows"] = 2
    check["exact_accession_rows"] = 1
    _refused(values, "provider_refused")


def test_reversed_filing_bounds_refuse():
    values = list(t._inputs())
    _receipt(values[1], "fmp_sec")["projection"]["filing_date_bounds"] = ["2021-01-02", "2021-01-01"]
    _refused(values, "provider_refused")


def test_projected_code_cannot_appear_without_a_projection():
    values = list(t._inputs())
    _receipt(values[1], "fmp_insider", scoped=False).update(code="metadata_projected", projection=None)
    # Keep the totals consistent so reconciliation cannot refuse in this guard's place.
    values[1]["projected_responses"] -= 1
    _refused(values, "provider_refused")


def test_projection_on_a_failed_http_status_refuses():
    values = list(t._inputs())
    _receipt(values[1], "fmp_sec")["http_status"] = 500
    _refused(values, "provider_refused")


@pytest.mark.parametrize("family, scoped, code", (("fmp_sec", True, "provider_scope_refused"),
    ("fmp_insider", False, "metadata_projected")))
def test_receipt_code_must_agree_with_the_projection_scope(family, scoped, code):
    values = list(t._inputs())
    _receipt(values[1], family, scoped=scoped)["code"] = code
    _refused(values, "provider_refused")


def test_unclean_scoped_response_is_not_control_evidence():
    cases = t._cases()[:1]
    complete = t._complete(cases, include_refusal=False)
    projection = _receipt(complete, "fmp_sec")["projection"]
    assert next(iter(projection["case_checks"].values()))["joint_cik_accession_rows"] > 0
    projection.update(metadata_clean=False, body_pin=None)
    complete["clean_scoped_responses"] -= 1
    _refused(list(t._inputs(cases=cases, complete=complete)), "control_evidence_missing")


@pytest.mark.parametrize("field", ("cik_rows", "current_symbol_us_namespace_equal_rows"))
def test_eod_agreement_requires_both_the_cik_and_the_symbol(field):
    cases = t._cases()[:1]
    complete = t._complete(cases)
    _check(complete, "eod_mapping")[field] = 0
    counts = m.build_audit(*t._inputs(cases=cases, complete=complete))["counts"]
    assert counts["eod_current_mapping_agreement_controls"] == 0


def test_date_only_completion_time_refuses_because_it_is_naive():
    values = list(t._inputs())
    values[1]["completed_utc"] = "2026-01-01Z"
    _refused(values, "provider_refused")
    values = list(t._inputs())
    values[1]["completed_utc"] = "2026-01-01T00:00:00Z"
    assert m.build_audit(*values)["schema"] == m.SCHEMA


def test_source_pin_size_is_capped():
    values = list(t._inputs())
    values[4]["controls.json"]["bytes"] = m.MAX_PIN_BYTES + 1
    _refused(values, "pin_refused")


def test_actual_audit_cannot_rest_on_a_fixture_provider_receipt():
    base = t._cases()[0]
    cases = [dict(base, case_id=f"PRIVATE-CONTROL-{i}", cik=f"{1000 + i:010d}",
                  accession=f"{1000 + i:010d}20{i:06d}") for i in range(m.MAX_CASES)]
    complete = t._complete(cases, include_refusal=False)
    rows = [t._ticker(c, i + 1) for i, c in enumerate(cases)]
    values = list(t._inputs(cases=cases, complete=complete, ticker_rows=rows))
    with pytest.raises(m.PitRetainedAuditError, match="provider_refused"):
        m.build_audit(*values, fixture_only=False)
    complete["fixture_only"] = False
    assert m.build_audit(*values, fixture_only=False)["fixture_only"] is False


@pytest.mark.parametrize("control", ("\n", "\x00", "\t"))
def test_control_characters_refuse_outside_the_free_text_name_fields(control):
    cases = t._cases()[:1]
    row = t._ticker(cases[0], 1, ticker="PRIVATE" + control + "LABEL")
    _refused(list(t._inputs(cases=cases, ticker_rows=[row])), "row_schema_refused")


def test_name_line_breaks_are_quarantined_not_refused():
    cases = t._cases()[:1]
    row = t._ticker(cases[0], 1, name="PRIVATE\nNAME")
    assert m.build_audit(*t._inputs(cases=cases, ticker_rows=[row]))["counts"]["ticker_quarantined_rows"] == 1


@pytest.mark.parametrize("table", ("ticker", "action"))
def test_each_table_stops_at_the_row_limit(monkeypatch, table):
    monkeypatch.setattr(m, "MAX_ROWS", 1)
    cases = t._cases()[:1]
    if table == "ticker":
        values = t._inputs(cases=cases, ticker_rows=[t._ticker(cases[0], 1), t._ticker(cases[0], 2)])
    else:
        values = t._inputs(cases=cases, ticker_rows=[t._ticker(cases[0], 1)],
                           action_rows=[t._action(cases[0], 1), t._action(cases[0], 2)])
    _refused(list(values), "row_limit_refused")


def test_memory_guard_runs_inside_both_row_streams(monkeypatch):
    # One before input, one at each table boundary, one at the end, plus one per
    # row at this cadence. A stream that stopped pulsing would change the total.
    monkeypatch.setattr(m, "CHECK_EVERY", 1)
    cases = t._cases()[:1]
    tickers = [t._ticker(cases[0], i + 1) for i in range(3)]
    actions = [t._action(cases[0], i + 1) for i in range(5)]
    pulses = []
    m.build_audit(*t._inputs(cases=cases, ticker_rows=tickers, action_rows=actions), check=lambda: pulses.append(1))
    assert len(pulses) == 4 + len(tickers) + len(actions)


def test_conflicting_primary_key_is_counted():
    cases = t._cases()[:1]
    rows = [t._ticker(cases[0], 1, permaticker="1001"),
            t._ticker(cases[0], 2, permaticker="1001", name="PRIVATE OTHER NAME")]
    counts = m.build_audit(*t._inputs(cases=cases, ticker_rows=rows))["counts"]
    assert counts["ticker_primary_key_conflict_groups"] == 1
    assert counts["ticker_exact_duplicate_rows"] == 0


@pytest.mark.parametrize("changes", ({"isdelisted": "X"}, {"firstadded": "2020-13-01"}, {"lastupdated": "20200101"}))
def test_quality_faults_quarantine_a_ticker_row_without_dropping_it(changes):
    cases = t._cases()[:1]
    result = m.build_audit(*t._inputs(cases=cases, ticker_rows=[t._ticker(cases[0], 1, **changes)]))
    assert result["counts"]["ticker_quarantined_rows"] == 1
    assert result["counts"]["ticker_candidate_rows"] == 1
    assert result["controls"][0]["counts"]["current_quarantined_candidate_rows"] == 1


@pytest.mark.parametrize("changes", ({"contraticker": "bad label!"}, {"date": "not-a-date"}, {"action": ""}))
def test_quality_faults_quarantine_an_action_row_without_dropping_it(changes):
    cases = t._cases()[:1]
    result = m.build_audit(*t._inputs(cases=cases, action_rows=[t._action(cases[0], 1, **changes)]))
    assert result["counts"]["action_rows"] == result["counts"]["action_quarantined_rows"] == 1
    assert result["counts"]["action_candidate_rows"] == 1
