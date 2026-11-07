"""Pure retained-original identity dossier; no historical availability release.

The caller authenticates pinned original bytes and current storage first.
Only already-validated complete-submission projections enter this module.
Financial values remain uninterpreted; current reference candidates are not
historical security identities, and acceptance is not public delivery.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import re
import xml.etree.ElementTree as ET

from research import insider_buying_pilot_pit_retained_audit_v1 as audit
from research.insider_buying.sec_complete_submission import SecCompleteSubmissionProjection

SCHEMA = "insider-pilot-historical-evidence-dossier-v1"
MAX_NODES, MAX_TITLES, MAX_REPORT_BYTES = 50000, 10000, 2 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_KINDS = {"nonDerivativeTable": ("nonDerivativeTransaction", "nonDerivativeHolding"),
          "derivativeTable": ("derivativeTransaction", "derivativeHolding")}
_IDENTITIES, _DOSSIERS = OrderedDict(), OrderedDict()


class HistoricalDossierError(ValueError):
    """Finite own code only; no source values or foreign exception strings."""


def _need(value, code="dossier_input_refused"):
    if not value:
        raise HistoricalDossierError(code)


def _raw(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise HistoricalDossierError("dossier_input_refused") from None


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _register(registry, value):
    data = _raw(value)
    _need(len(data) <= MAX_REPORT_BYTES, "dossier_output_refused")
    registry[id(value)] = (value, data)
    while len(registry) > 64:
        registry.popitem(last=False)
    return value


def _genuine(registry, value):
    saved = registry.get(id(value))
    _need(type(value) is dict and saved is not None and saved[0] is value
          and saved[1] == _raw(value), "genuine_dossier_evidence_required")
    return saved[1]


def _symbol(root):
    issuers = root.findall("issuer")
    _need(len(issuers) == 1, "original_identity_refused")
    found = issuers[0].findall("issuerTradingSymbol")
    _need(len(found) <= 1 and len(list(root.iter("issuerTradingSymbol"))) == len(found),
          "original_identity_refused")
    if not found:
        return None
    node = found[0]
    _need(not list(node) and not node.attrib, "original_identity_refused")
    text = (node.text or "").strip()
    if not text:
        return None
    _need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.^/_ -]{0,63}", text), "original_identity_refused")
    return text


def _titles(root):
    """Account every title node; malformed text is quarantined, never mapped."""
    observations, placed, entries, missing = [], set(), 0, 0
    for table_name, kinds in _KINDS.items():
        tables = root.findall(table_name)
        _need(len(tables) <= 1 and len(list(root.iter(table_name))) == len(tables),
              "original_title_structure_refused")
        for table in tables:
            for entry in table:
                if entry.tag not in kinds:
                    continue
                entries += 1
                titles = entry.findall("securityTitle")
                missing += int(not titles)
                for node in titles:
                    placed.add(id(node))
                    scalar = node.findall("value")
                    valid_shape = (len(titles) == 1 and len(scalar) == 1 and not node.attrib
                        and not list(scalar[0]) and not scalar[0].attrib
                        and all(child.tag in {"value", "footnoteId"} for child in node))
                    title = scalar[0].text if valid_shape else None
                    valid_text = (type(title) is str and bool(title.strip())
                        and len(title.encode("utf-8")) <= 4096
                        and not any(ord(char) < 32 for char in title))
                    observations.append({"kind": entry.tag, "source_ordinal": len(observations) + 1,
                        "title_raw": title if valid_text else None,
                        "disposition": "metadata_observed" if valid_text else
                        "title_shape_refused" if not valid_shape else "title_text_refused"})
                    _need(len(observations) <= MAX_TITLES, "original_title_resource_refused")
    total = sum(type(node.tag) is str and node.tag.rsplit("}", 1)[-1] == "securityTitle" for node in root.iter())
    _need(total <= MAX_TITLES and len(placed) <= total, "original_title_resource_refused")
    return observations, total - len(placed), entries, missing


def extract_identity(projected):
    """Derive only lexical identity metadata from an exact frozen projection."""
    _need(type(projected) is SecCompleteSubmissionProjection, "original_projection_required")
    try:
        payload = projected.to_payload()  # Revalidates header/XML/body and their owner sets.
        xml = projected.xml_bytes
        _need(b"<!DOCTYPE" not in xml.upper() and b"<!ENTITY" not in xml.upper(),
              "original_identity_refused")
        root = ET.fromstring(xml)
        nodes = list(root.iter())
        _need(len(nodes) <= MAX_NODES and root.tag == "ownershipDocument", "original_identity_refused")
        titles, unplaced, entries, missing = _titles(root)
        target = projected.target
        result = {"schema": SCHEMA + "/original-identity", "body_sha256": payload["raw_parent"]["sha256"],
            "body_bytes": payload["raw_parent"]["size_bytes"], "issuer_cik": target.issuer_cik,
            "accession": target.accession_number.replace("-", ""), "form_type": target.form_type,
            "filing_date": target.filing_date, "acceptance_digits": projected.accepted_at_raw,
            "source_symbol": _symbol(root), "header_pin": dict(payload["children"]["header"]),
            "xml_pin": dict(payload["children"]["primary_xml"]),
            "reporting_owner_ciks": list(projected.header_owner_ciks),
            "header_xml_owner_sets_agree": True, "security_titles": titles,
            "unplaced_security_title_count": unplaced, "known_entry_count": entries,
            "entries_missing_security_title": missing, "financial_values_interpreted": False,
            "acceptance_is_public_delivery": False, "historical_validity_interval": None,
            "historical_public_known_by": None}
    except HistoricalDossierError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, ET.ParseError, RecursionError):
        raise HistoricalDossierError("original_identity_refused") from None
    return _register(_IDENTITIES, result)


def _execution(value):
    _need(type(value) is dict and set(value) == {"head", "sources", "source_inventory_sha256"}
          and type(value["head"]) is str and _HEAD.fullmatch(value["head"])
          and type(value["sources"]) is dict and 0 < len(value["sources"]) <= 512,
          "dossier_execution_refused")
    for name, pin in value["sources"].items():
        _need(type(name) is str and re.fullmatch(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py", name)
              and ".." not in name.split("/") and name.split("/")[0] != "artifacts"
              and type(pin) is str and _SHA.fullmatch(pin), "dossier_execution_refused")
    _need(type(value["source_inventory_sha256"]) is str and _SHA.fullmatch(value["source_inventory_sha256"])
          and value["source_inventory_sha256"] == _sha(_raw(value["sources"])), "dossier_execution_refused")
    return json.loads(_raw(value))


def build_dossier(cases, body_evidence, audit_result, transition_sha256, execution_identity, *, fixture_only=True):
    """Join original identity and current-reference evidence, with unknown PIT."""
    _need(type(fixture_only) is bool and type(transition_sha256) is str
          and _SHA.fullmatch(transition_sha256), "dossier_arguments_refused")
    try:
        _need(type(cases) in {list, tuple} and 0 < len(cases) <= 12
              and all(type(case) is dict and set(case) == audit.CASE_KEYS for case in cases)
              and (fixture_only or len(cases) == 12), "dossier_controls_refused")
        cases = audit.projection._cases(cases)
        reference = audit.public_summary(audit_result)  # Refuses cloned or mutated audit results.
    except HistoricalDossierError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HistoricalDossierError("dossier_controls_refused") from None
    _need(reference["fixture_only"] is fixture_only and len(audit_result["controls"]) == len(cases),
          "dossier_reference_refused")
    _need(type(body_evidence) in {list, tuple} and len(body_evidence) == len(cases),
          "dossier_originals_refused")
    if not fixture_only:
        _need([case["case_id"] for case in cases] == [*(f"warmup-{i:02d}" for i in range(1, 9)),
               *(f"recent-{i:02d}" for i in range(1, 5))], "dossier_controls_refused")
    execution = _execution(execution_identity)
    rows, owners, title_count, title_good, title_bad, title_cases, unplaced = [], set(), 0, 0, 0, 0, 0
    for case, identity, context in zip(cases, body_evidence, audit_result["controls"]):
        _genuine(_IDENTITIES, identity)
        expected = {"issuer_cik": case["cik"], "accession": case["accession"], "form_type": case["form_type"],
            "filing_date": case["filing_date"], "acceptance_digits": case["acceptance_digits"],
            "source_symbol": case["source_symbol"], "body_sha256": case["body_sha256"]}
        _need(all(identity[key] == value for key, value in expected.items())
              and context["control_sha256"] == _sha(_raw(case)), "dossier_originals_refused")
        owners.update(identity["reporting_owner_ciks"])
        titles = identity["security_titles"]
        observed = sum(item["disposition"] == "metadata_observed" for item in titles)
        title_count += len(titles); title_good += observed
        title_bad += len(titles) - observed; title_cases += int(observed > 0)
        unplaced += identity["unplaced_security_title_count"]
        rows.append({"case_id": case["case_id"], "control_sha256": _sha(_raw(case)),
            "original_identity": json.loads(_raw(identity)), "current_reference_evidence": json.loads(_raw(context)),
            "historical_validity_interval": None, "historical_public_known_by": None,
            "historical_share_class_binding_verified": False, "authority": audit.authority()})
    result = {"schema": SCHEMA, "fixture_only": fixture_only, "transition_sha256": transition_sha256,
        "execution_identity": execution, "reference_audit_sha256": reference["result_sha256"],
        "reference_source_pins": reference["source_pins"], "controls": rows,
        "counts": {"controls": len(cases), "originals_reparsed": len(body_evidence),
            "issuer_ciks": len({case["cik"] for case in cases}),
            "reporting_owner_occurrences": sum(len(item["reporting_owner_ciks"]) for item in body_evidence),
            "distinct_reporting_owners": len(owners), "security_title_occurrences": title_count,
            "observed_security_titles": title_good, "quarantined_security_titles": title_bad,
            "unplaced_security_titles": unplaced, "controls_with_observed_titles": title_cases,
            "known_entry_occurrences": sum(item["known_entry_count"] for item in body_evidence),
            "entries_missing_security_title": sum(item["entries_missing_security_title"] for item in body_evidence),
            "historical_identity_gate_closures": 0, "historical_availability_gate_closures": 0},
        "reference_counts": reference["counts"], "all_six_form_coverage_verified": False,
        "historical_physical_continuity_established": False, "historical_binding_passed": False,
        "financial_values_interpreted": False, "authority": audit.authority()}
    checked = validate_payload(result, transition_sha256, execution, fixture_only=fixture_only)
    return _register(_DOSSIERS, checked)


def private_payload(result):
    return json.loads(_genuine(_DOSSIERS, result))


def _integer(value, maximum=1_000_000_000):
    _need(type(value) is int and 0 <= value <= maximum, "dossier_payload_refused")
    return value


def _false_authority(value):
    _need(type(value) is dict and _raw(value) == _raw(audit.authority()), "dossier_payload_refused")


def _original_payload(value):
    fields = {"schema", "body_sha256", "body_bytes", "issuer_cik", "accession", "form_type", "filing_date",
        "acceptance_digits", "source_symbol", "header_pin", "xml_pin", "reporting_owner_ciks",
        "header_xml_owner_sets_agree", "security_titles", "unplaced_security_title_count", "known_entry_count",
        "entries_missing_security_title", "financial_values_interpreted", "acceptance_is_public_delivery",
        "historical_validity_interval", "historical_public_known_by"}
    _need(type(value) is dict and set(value) == fields and value["schema"] == SCHEMA + "/original-identity",
          "dossier_payload_refused")
    _need(0 < _integer(value["body_bytes"], 8 * 1024 * 1024), "dossier_payload_refused")
    case = {"case_id": "payload-control", "cik": value["issuer_cik"], "accession": value["accession"],
        "form_type": value["form_type"], "filing_date": value["filing_date"],
        "acceptance_digits": value["acceptance_digits"], "source_symbol": value["source_symbol"],
        "body_sha256": value["body_sha256"]}
    audit.projection._cases([case])
    _need(value["header_xml_owner_sets_agree"] is True
          and value["financial_values_interpreted"] is value["acceptance_is_public_delivery"] is False
          and value["historical_validity_interval"] is value["historical_public_known_by"] is None,
          "dossier_payload_refused")
    for key, maximum in (("header_pin", 2 * 1024 * 1024), ("xml_pin", 4 * 1024 * 1024)):
        pin = value[key]
        _need(type(pin) is dict and set(pin) == {"parent_sha256", "sha256", "size_bytes"}
              | ({"filename"} if key == "xml_pin" else set())
              and pin["parent_sha256"] == value["body_sha256"]
              and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"])
              and 0 < _integer(pin["size_bytes"], maximum) < value["body_bytes"], "dossier_payload_refused")
        if key == "xml_pin":
            name = pin["filename"]
            _need(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,250}\.xml", name)
                  and ".." not in name and not name.casefold().startswith("xsl"), "dossier_payload_refused")
    owners = value["reporting_owner_ciks"]
    _need(type(owners) is list and 1 <= len(owners) <= 256 and len(set(owners)) == len(owners)
          and all(type(owner) is str and re.fullmatch(r"[0-9]{10}", owner) and int(owner) > 0 for owner in owners),
          "dossier_payload_refused")
    titles = value["security_titles"]
    _need(type(titles) is list and len(titles) <= MAX_TITLES, "dossier_payload_refused")
    kinds = {kind for group in _KINDS.values() for kind in group}
    for ordinal, title in enumerate(titles, 1):
        _need(type(title) is dict and set(title) == {"kind", "source_ordinal", "title_raw", "disposition"}
              and type(title["kind"]) is str and title["kind"] in kinds
              and type(title["source_ordinal"]) is int and title["source_ordinal"] == ordinal
              and title["disposition"] in {"metadata_observed", "title_shape_refused", "title_text_refused"},
              "dossier_payload_refused")
        text = title["title_raw"]
        if title["disposition"] == "metadata_observed":
            _need(type(text) is str and text.strip() and len(text.encode("utf-8")) <= 4096
                  and not any(ord(char) < 32 for char in text), "dossier_payload_refused")
        else:
            _need(text is None, "dossier_payload_refused")
    unplaced = _integer(value["unplaced_security_title_count"], MAX_TITLES)
    entries = _integer(value["known_entry_count"], MAX_NODES)
    missing = _integer(value["entries_missing_security_title"], MAX_NODES)
    _need(len(titles) + unplaced <= MAX_TITLES and missing <= entries
          and entries - missing <= len(titles)
          and (entries > missing or not titles), "dossier_payload_refused")
    return case


_REFERENCE_CONTROL_COUNTS = frozenset({"fmp_candidate_rows", "fmp_joint_rows", "fmp_form_agreeing_rows",
    "fmp_naive_acceptance_agreeing_rows", "current_candidate_rows", "current_candidate_permatickers",
    "current_quarantined_candidate_rows", "source_symbol_equal_rows", "conflicting_permatickers", "reused_labels",
    "action_candidate_rows", "action_rows_before_filing", "action_primary_label_rows", "action_counterparty_label_rows"})
_REFERENCE_COUNTS = frozenset({"ticker_rows", "ticker_quarantined_rows", "ticker_exact_duplicate_rows",
    "ticker_primary_key_conflict_groups", "ticker_candidate_rows", "global_permaticker_cik_conflicts",
    "global_label_reuse_groups", "controls_no_current_candidate", "controls_one_current_candidate",
    "controls_multiple_current_candidates", "controls_conflicting_current_candidates", "controls_source_symbol_agreement",
    "action_rows", "action_quarantined_rows", "action_exact_duplicate_rows", "action_candidate_rows",
    "action_candidate_relations", "action_rows_before_filing_relations", "action_primary_label_relations",
    "action_counterparty_label_relations", "controls", "issuers", "eod_current_mapping_agreement_controls",
    "provider_planned_requests", "provider_transport_invocations", "provider_projected_responses",
    "provider_scoped_responses", "provider_clean_scoped_responses", "provider_unattempted_requests",
    "provider_refused_attempts", "fmp_sec_attempts", "fmp_insider_attempts", "eod_mapping_attempts",
    "fmp_joint_controls", "fmp_form_guaranteed_controls", "fmp_naive_acceptance_guaranteed_controls", "action_categories"})


def _reference_control(value, control_sha):
    fields = {"control_sha256", "counts", "candidate_permatickers_sha256", "candidate_source_ordinals_sha256",
        "action_source_ordinals_sha256", "fmp_form_exact_row_guaranteed", "fmp_naive_acceptance_exact_row_guaranteed",
        "effective_interval", "public_known_by", "authority"}
    _need(type(value) is dict and set(value) == fields and value["control_sha256"] == control_sha,
          "dossier_payload_refused")
    for field in ("candidate_permatickers_sha256", "candidate_source_ordinals_sha256", "action_source_ordinals_sha256"):
        _need(type(value[field]) is str and _SHA.fullmatch(value[field]), "dossier_payload_refused")
    _false_authority(value["authority"])
    _need(value["effective_interval"] is value["public_known_by"] is None, "dossier_payload_refused")
    counts = value["counts"]
    _need(type(counts) is dict and set(counts) == _REFERENCE_CONTROL_COUNTS, "dossier_payload_refused")
    for child in counts.values(): _integer(child)
    c, j = counts["fmp_candidate_rows"], counts["fmp_joint_rows"]
    _need(0 < j <= c and counts["fmp_form_agreeing_rows"] <= c
          and counts["fmp_naive_acceptance_agreeing_rows"] <= c, "dossier_payload_refused")
    for flag, field in (("fmp_form_exact_row_guaranteed", "fmp_form_agreeing_rows"),
                        ("fmp_naive_acceptance_exact_row_guaranteed", "fmp_naive_acceptance_agreeing_rows")):
        _need(type(value[flag]) is bool and value[flag] == (counts[field] > c-j), "dossier_payload_refused")
    rows, actions = counts["current_candidate_rows"], counts["action_candidate_rows"]
    _need(all(counts[key] <= rows for key in ("current_candidate_permatickers", "current_quarantined_candidate_rows",
          "source_symbol_equal_rows", "reused_labels"))
          and counts["conflicting_permatickers"] <= counts["current_candidate_permatickers"]
          and all(counts[key] <= actions for key in ("action_rows_before_filing", "action_primary_label_rows",
          "action_counterparty_label_rows"))
          and counts["action_primary_label_rows"] + counts["action_counterparty_label_rows"] >= actions,
          "dossier_payload_refused")


def _reference_counts(value, rows):
    _need(type(value) is dict and set(value) == _REFERENCE_COUNTS, "dossier_payload_refused")
    for key, child in value.items():
        if key != "action_categories": _integer(child)
    categories = value["action_categories"]
    _need(type(categories) is dict and set(categories) == set(audit._CATEGORIES), "dossier_payload_refused")
    for child in categories.values(): _integer(child, audit.MAX_ROWS)
    _need(sum(categories.values()) == value["action_rows"] <= audit.MAX_ROWS
          and value["ticker_rows"] <= audit.MAX_ROWS, "dossier_payload_refused")
    for prefix, fields in (("ticker_rows", ("ticker_quarantined_rows", "ticker_exact_duplicate_rows",
            "ticker_primary_key_conflict_groups", "ticker_candidate_rows", "global_permaticker_cik_conflicts", "global_label_reuse_groups")),
            ("action_rows", ("action_quarantined_rows", "action_exact_duplicate_rows", "action_candidate_rows"))):
        _need(all(value[field] <= value[prefix] for field in fields), "dossier_payload_refused")
    controls = [row["current_reference_evidence"] for row in rows]
    cc = [row["counts"] for row in controls]
    required = {"controls": len(rows), "issuers": len({row["original_identity"]["issuer_cik"] for row in rows}),
        "controls_no_current_candidate": sum(c["current_candidate_permatickers"] == 0 for c in cc),
        "controls_one_current_candidate": sum(c["current_candidate_permatickers"] == 1 for c in cc),
        "controls_multiple_current_candidates": sum(c["current_candidate_permatickers"] > 1 for c in cc),
        "controls_conflicting_current_candidates": sum(c["conflicting_permatickers"] > 0 for c in cc),
        "controls_source_symbol_agreement": sum(c["source_symbol_equal_rows"] > 0 for c in cc),
        "action_candidate_relations": sum(c["action_candidate_rows"] for c in cc),
        "action_rows_before_filing_relations": sum(c["action_rows_before_filing"] for c in cc),
        "action_primary_label_relations": sum(c["action_primary_label_rows"] for c in cc),
        "action_counterparty_label_relations": sum(c["action_counterparty_label_rows"] for c in cc),
        "fmp_joint_controls": sum(c["fmp_joint_rows"] > 0 for c in cc),
        "fmp_form_guaranteed_controls": sum(c["fmp_form_exact_row_guaranteed"] for c in controls),
        "fmp_naive_acceptance_guaranteed_controls": sum(c["fmp_naive_acceptance_exact_row_guaranteed"] for c in controls)}
    _need(all(value[key] == child for key, child in required.items())
          and value["eod_current_mapping_agreement_controls"] <= len(rows)
          and value["provider_planned_requests"] == value["provider_transport_invocations"] + value["provider_unattempted_requests"] <= 36
          and value["provider_transport_invocations"] == sum(value[k] for k in ("fmp_sec_attempts", "fmp_insider_attempts", "eod_mapping_attempts"))
          and value["provider_transport_invocations"] - value["provider_refused_attempts"] == value["provider_scoped_responses"]
          and value["provider_clean_scoped_responses"] <= value["provider_scoped_responses"] <= value["provider_projected_responses"] <= value["provider_transport_invocations"],
          "dossier_payload_refused")


def validate_payload(value, transition_sha256, execution_identity, *, fixture_only=False):
    """Validate already hash-authenticated serialized output, not its provenance.

    The caller must authenticate the enclosing bytes BEFORE JSON decoding.
    Unlike the in-process factory seal, this reader proves strict structure,
    cross-links, accounting and zero authority; it cannot authenticate a source.
    """
    try:
        _need(type(fixture_only) is bool and type(transition_sha256) is str and _SHA.fullmatch(transition_sha256),
              "dossier_arguments_refused")
        expected_execution = _execution(execution_identity)
        fields = {"schema", "fixture_only", "transition_sha256", "execution_identity", "reference_audit_sha256",
            "reference_source_pins", "controls", "counts", "reference_counts", "all_six_form_coverage_verified",
            "historical_physical_continuity_established", "historical_binding_passed", "financial_values_interpreted", "authority"}
        _need(type(value) is dict and set(value) == fields and value["schema"] == SCHEMA
              and value["fixture_only"] is fixture_only and value["transition_sha256"] == transition_sha256
              and _raw(value["execution_identity"]) == _raw(expected_execution)
              and type(value["reference_audit_sha256"]) is str and _SHA.fullmatch(value["reference_audit_sha256"]),
              "dossier_payload_refused")
        _false_authority(value["authority"])
        _need(all(value[key] is False for key in ("all_six_form_coverage_verified", "historical_physical_continuity_established",
              "historical_binding_passed", "financial_values_interpreted")), "dossier_payload_refused")
        pins = audit._pins(value["reference_source_pins"])
        rows = value["controls"]
        _need(type(rows) is list and 0 < len(rows) <= 12 and (fixture_only or len(rows) == 12), "dossier_payload_refused")
        cases = []
        for row in rows:
            _need(type(row) is dict and set(row) == {"case_id", "control_sha256", "original_identity", "current_reference_evidence",
                  "historical_validity_interval", "historical_public_known_by", "historical_share_class_binding_verified", "authority"},
                  "dossier_payload_refused")
            case = _original_payload(row["original_identity"]); case["case_id"] = row["case_id"]
            cases.append(case)
            _need(row["control_sha256"] == _sha(_raw(case))
                  and row["historical_validity_interval"] is row["historical_public_known_by"] is None
                  and row["historical_share_class_binding_verified"] is False, "dossier_payload_refused")
            _false_authority(row["authority"])
            _reference_control(row["current_reference_evidence"], row["control_sha256"])
        audit.projection._cases(cases)
        if not fixture_only:
            _need([c["case_id"] for c in cases] == [*(f"warmup-{i:02d}" for i in range(1, 9)),
                   *(f"recent-{i:02d}" for i in range(1, 5))], "dossier_payload_refused")
        _reference_counts(value["reference_counts"], rows)
        reference = {"schema": audit.SCHEMA, "fixture_only": fixture_only, "source_pins": pins,
            "counts": value["reference_counts"], "controls": [row["current_reference_evidence"] for row in rows],
            "missing_evidence": list(audit.MISSING_EVIDENCE), "authority": audit.authority()}
        _need(_sha(_raw(reference)) == value["reference_audit_sha256"], "dossier_payload_refused")
        identities = [row["original_identity"] for row in rows]
        titles = [title for identity in identities for title in identity["security_titles"]]
        required_counts = {"controls": len(rows), "originals_reparsed": len(rows),
            "issuer_ciks": len({c["cik"] for c in cases}),
            "reporting_owner_occurrences": sum(len(identity["reporting_owner_ciks"]) for identity in identities),
            "distinct_reporting_owners": len({owner for identity in identities for owner in identity["reporting_owner_ciks"]}),
            "security_title_occurrences": len(titles), "observed_security_titles": sum(t["disposition"] == "metadata_observed" for t in titles),
            "quarantined_security_titles": sum(t["disposition"] != "metadata_observed" for t in titles),
            "unplaced_security_titles": sum(identity["unplaced_security_title_count"] for identity in identities),
            "controls_with_observed_titles": sum(any(t["disposition"] == "metadata_observed" for t in identity["security_titles"]) for identity in identities),
            "known_entry_occurrences": sum(identity["known_entry_count"] for identity in identities),
            "entries_missing_security_title": sum(identity["entries_missing_security_title"] for identity in identities),
            "historical_identity_gate_closures": 0, "historical_availability_gate_closures": 0}
        _need(type(value["counts"]) is dict and set(value["counts"]) == set(required_counts)
              and all(type(value["counts"][k]) is int and value["counts"][k] == v for k, v in required_counts.items()),
              "dossier_payload_refused")
        data = _raw(value); _need(len(data) <= MAX_REPORT_BYTES, "dossier_output_refused")
        return json.loads(data)
    except HistoricalDossierError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise HistoricalDossierError("dossier_payload_refused") from None


def summary_from_payload(value, transition_sha256, execution_identity, *, fixture_only=False):
    """Safe summary after external pin authentication and strict readback checks."""
    checked = validate_payload(value, transition_sha256, execution_identity, fixture_only=fixture_only)
    return _summary(checked, _raw(checked))


def _summary(result, data):
    return json.loads(_raw({"schema": SCHEMA + "/public", "fixture_only": result["fixture_only"],
        "dossier_sha256": _sha(data), "transition_sha256": result["transition_sha256"],
        "execution_head": result["execution_identity"]["head"],
        "source_inventory_sha256": result["execution_identity"]["source_inventory_sha256"],
        "reference_audit_sha256": result["reference_audit_sha256"],
        "counts": result["counts"], "reference_counts": result["reference_counts"],
        "all_six_form_coverage_verified": False, "historical_physical_continuity_established": False,
        "historical_binding_passed": False, "financial_values_interpreted": False,
        "authority": audit.authority()}))


def public_summary(result):
    data = _genuine(_DOSSIERS, result)
    return _summary(result, data)
