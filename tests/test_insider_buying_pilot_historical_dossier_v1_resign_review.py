"""Claude section 383 review: each dossier reader guard, tested on its own.

The existing serialized-readback faults change a payload without re-signing
its reference digest or its summary counts, so those recomputations refuse
first and the guard a fault names can be deleted with every test still green.
Here each fault is re-signed, leaving only the named guard to refuse it.
Invented filings only; the caller supplies native network/DATA isolation.
"""
import importlib.util
from pathlib import Path

import pytest

from research import insider_buying_pilot_historical_dossier_v1 as m


def _sibling(name):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location("dossier_resign_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _sibling("test_insider_buying_pilot_historical_dossier_v1.py")


def _resign(payload):
    """Recompute exactly what validate_payload recomputes, so only one guard is left."""
    rows = payload["controls"]
    identities = [row["original_identity"] for row in rows]
    titles = [title for identity in identities for title in identity["security_titles"]]
    owners = [owner for identity in identities for owner in identity["reporting_owner_ciks"]]
    payload["counts"].update(
        reporting_owner_occurrences=len(owners), distinct_reporting_owners=len(set(owners)),
        security_title_occurrences=len(titles),
        observed_security_titles=sum(t["disposition"] == "metadata_observed" for t in titles),
        quarantined_security_titles=sum(t["disposition"] != "metadata_observed" for t in titles),
        unplaced_security_titles=sum(identity["unplaced_security_title_count"] for identity in identities),
        known_entry_occurrences=sum(identity["known_entry_count"] for identity in identities),
        entries_missing_security_title=sum(identity["entries_missing_security_title"] for identity in identities))
    counts = payload["reference_counts"]
    evidence = [row["current_reference_evidence"] for row in rows]
    counts.update(fmp_joint_controls=sum(e["counts"]["fmp_joint_rows"] > 0 for e in evidence),
        fmp_form_guaranteed_controls=sum(e["fmp_form_exact_row_guaranteed"] for e in evidence),
        fmp_naive_acceptance_guaranteed_controls=sum(e["fmp_naive_acceptance_exact_row_guaranteed"] for e in evidence))
    # The digest covers the counts just recomputed, so it is signed last.
    reference = {"schema": m.audit.SCHEMA, "fixture_only": payload["fixture_only"],
        "source_pins": payload["reference_source_pins"], "counts": counts, "controls": evidence,
        "missing_evidence": list(m.audit.MISSING_EVIDENCE), "authority": m.audit.authority()}
    payload["reference_audit_sha256"] = m._sha(m._raw(reference))
    return payload


def _payload():
    return m.private_payload(base._build())


def _validate(payload):
    return m.validate_payload(payload, "c" * 64, base._identity(), fixture_only=True)


def _rule(evidence, flag, field):
    counts = evidence["counts"]
    return counts[field] > counts["fmp_candidate_rows"] - counts["fmp_joint_rows"]


def test_resigning_an_unchanged_payload_still_validates():
    # Without this control a broken re-signing helper would make every fault pass.
    payload = _payload()
    assert _validate(_resign(payload)) == payload


@pytest.mark.parametrize("flag,field", (("fmp_form_exact_row_guaranteed", "fmp_form_agreeing_rows"),
    ("fmp_naive_acceptance_exact_row_guaranteed", "fmp_naive_acceptance_agreeing_rows")))
def test_exact_row_flag_must_follow_the_pigeonhole_rule(flag, field):
    # A marginal same-issuer row must never be labelled an exact-row agreement.
    payload = _payload()
    evidence = payload["controls"][0]["current_reference_evidence"]
    evidence[flag] = not _rule(evidence, flag, field)
    with pytest.raises(m.HistoricalDossierError, match="^dossier_payload_refused$"):
        _validate(_resign(payload))


@pytest.mark.parametrize("joint", (0, "above-candidates"))
def test_joint_rows_must_be_positive_and_within_candidates(joint):
    payload = _payload()
    evidence = payload["controls"][0]["current_reference_evidence"]
    counts = evidence["counts"]
    counts["fmp_joint_rows"] = 0 if joint == 0 else counts["fmp_candidate_rows"] + 1
    for flag, field in (("fmp_form_exact_row_guaranteed", "fmp_form_agreeing_rows"),
                        ("fmp_naive_acceptance_exact_row_guaranteed", "fmp_naive_acceptance_agreeing_rows")):
        evidence[flag] = _rule(evidence, flag, field)
    with pytest.raises(m.HistoricalDossierError, match="^dossier_payload_refused$"):
        _validate(_resign(payload))


def test_duplicate_reporting_owners_are_refused_after_recounting():
    payload = _payload()
    payload["controls"][0]["original_identity"]["reporting_owner_ciks"] *= 2
    with pytest.raises(m.HistoricalDossierError, match="^dossier_payload_refused$"):
        _validate(_resign(payload))


def test_entries_with_titles_cannot_exceed_the_titles_seen():
    payload = _payload()
    original = payload["controls"][0]["original_identity"]
    original["known_entry_count"] = len(original["security_titles"]) + 2
    original["entries_missing_security_title"] = 1
    with pytest.raises(m.HistoricalDossierError, match="^dossier_payload_refused$"):
        _validate(_resign(payload))


@pytest.mark.parametrize("fault", ("category-sum", "request-sum", "source-pin-type"))
def test_reference_accounting_and_pins_refuse_on_their_own(fault):
    payload = _payload()
    counts = payload["reference_counts"]
    if fault == "category-sum":
        counts["action_categories"]["other"] += 1
    elif fault == "request-sum":
        counts["provider_unattempted_requests"] += 1
    else:
        payload["reference_source_pins"][next(iter(payload["reference_source_pins"]))]["bytes"] = True
    with pytest.raises(m.HistoricalDossierError, match="^dossier_payload_refused$"):
        _validate(_resign(payload))
