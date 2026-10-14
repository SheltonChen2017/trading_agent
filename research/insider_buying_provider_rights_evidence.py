"""Pure admission of supplied, privately anchored provider rights evidence.

Authentication, public metadata, a key, and an agent's delegated decision are
not licence grants. The metadata journal establishes only the recorded probe
observation; it does not identify a purchased product or historical vintage.
An external contract assessment must bind the exact account/product/subject,
private purchase or provider confirmation bytes, and applicable clause ranges.
This code checks those bindings, NOT authenticity or legal interpretation.

Public references (not private-account permission evidence):
https://www.quantconnect.com/terms (v1.4, 2026-10-02, especially section 2.6)
https://sharadar.com/terms
Public terms alone cannot establish purchase-specific applicability. Nothing
here authorizes exporting QC PlatformData to construct local outcome panels.
Normal permitted strategy outputs and an independently purchased data licence
are distinct from native data access. No credential, file, transport, outcome,
permanent-look allocation, upload, or backtest operation exists in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
import weakref

from data.hashing import canonical_json, hash_bytes


PERMISSIONS = ("local-process", "qc-store", "qc-process")
PROVIDERS = ("quantconnect", "massive", "sharadar")
MAX_RECORD_BYTES = 1024 * 1024
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_TOTAL_BYTES = 64 * 1024 * 1024
MAX_DOCUMENTS = 8
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_ACCOUNT = re.compile(r"acct-[0-9a-f]{32,64}\Z")
_PROFILE = {"quantconnect": "qc-authenticate-v1", "massive": "massive-marketstatus-now-v1",
            "sharadar": "sharadar-tickers-bulk-status-v1"}
_OBSERVATIONS = {"quantconnect": "qc-authentication-observed", "massive": "public-market-status-observed",
                 "sharadar": "bulk-status-metadata-observed"}
_FAILURES = frozenset({"authentication-refused", "authentication-http-refused", "rate-limited", "http-error",
    "invalid-metadata-schema", "credentials-missing", "credentials-invalid", "clock-invalid", "request-refused",
    "unsupported-content-encoding", "invalid-content-length", "oversized-response", "truncated-response",
    "partial-read", "redirect-refused", "invalid-http-status", "response-origin-mismatch", "transport-timeout",
    "transport-error", "invalid-transport-result"})
_REGISTRY: dict[int, tuple[weakref.ReferenceType, bytes]] = {}


class ProviderRightsEvidenceError(ValueError):
    """A supplied evidence contract is inconsistent; messages disclose no bytes."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ProviderRightsEvidenceError("REFUSED: " + code)


def _sha(value: object, label: str) -> None:
    _require(type(value) is str and _SHA.fullmatch(value) is not None, label + "-digest-invalid")


def _fields(value: object, names: set[str], label: str) -> None:
    _require(type(value) is dict and set(value) == names, label + "-fields-differ")


def _utc(value: object) -> datetime:
    _require(type(value) is str and value.endswith("Z"), "instant-not-canonical-utc")
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ProviderRightsEvidenceError("REFUSED: instant-invalid") from None
    _require(instant.tzinfo == timezone.utc and instant.isoformat().replace("+00:00", "Z") == value,
             "instant-not-canonical-utc")
    return instant


def _date(value: object) -> date:
    _require(type(value) is str, "session-invalid")
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise ProviderRightsEvidenceError("REFUSED: session-invalid") from None
    _require(result.isoformat() == value, "session-not-canonical")
    return result


def _identity(value: object, label: str) -> None:
    _require(type(value) is str and _ID.fullmatch(value) is not None, label + "-identity-invalid")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def _json(raw: object, expected: str, label: str) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_RECORD_BYTES, label + "-bytes-invalid")
    _require(hash_bytes(raw) == expected, label + "-external-root-differs")
    def refuse_number(_):
        raise ProviderRightsEvidenceError("REFUSED: noninteger-json-number")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                            parse_float=refuse_number, parse_constant=refuse_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ProviderRightsEvidenceError("REFUSED: " + label + "-json-invalid") from None
    _require(type(result) is dict, label + "-not-object")
    return result


@dataclass(frozen=True, slots=True)
class ProviderRightsTrustRoots:
    """Roots obtained outside admission; a digest is not self-authentication."""
    trust_scope: str
    probe_receipt_sha256: str
    subject_sha256: str
    terms_index_sha256: str | None = None
    permission_assessment_sha256: str | None = None

    def __post_init__(self) -> None:
        _require(type(self.trust_scope) is str and self.trust_scope in {"fixture", "production"}, "scope-invalid")
        for label in ("probe_receipt", "subject"):
            _sha(getattr(self, label + "_sha256"), label)
        for label in ("terms_index", "permission_assessment"):
            value = getattr(self, label + "_sha256")
            if value is not None:
                _sha(value, label)
        _require((self.terms_index_sha256 is None) == (self.permission_assessment_sha256 is None),
                 "partial-contract-roots")


def _subject(raw: bytes, roots: ProviderRightsTrustRoots) -> dict:
    value = _json(raw, roots.subject_sha256, "subject")
    _fields(value, {"schema", "trust_scope", "provider", "account_pseudonym", "product_id", "dataset_id",
        "vintage_id", "vintage_kind", "data_class", "source_manifest_sha256", "outcome_vintage_sha256",
        "representation", "platform", "first_session", "last_session", "market_data_profile",
        "clock_data_entitlements"}, "subject")
    _require(value["schema"] == "insider-provider-rights-subject-v1" and value["trust_scope"] == roots.trust_scope,
             "subject-schema-scope-differs")
    _require(type(value["provider"]) is str and value["provider"] in PROVIDERS, "provider-invalid")
    _require(type(value["account_pseudonym"]) is str and _ACCOUNT.fullmatch(value["account_pseudonym"]) is not None,
             "account-pseudonym-invalid")
    for name in ("product_id", "dataset_id", "vintage_id"):
        _identity(value[name], name)
    _sha(value["source_manifest_sha256"], "source-manifest")
    _require(type(value["vintage_kind"]) is str and value["vintage_kind"] in {
        "current-reference-snapshot", "historical-reference-vintage", "historical-outcome-vintage"}, "vintage-kind-invalid")
    _require(type(value["data_class"]) is str and value["data_class"] in {
        "reference-metadata", "price-and-corporate-action", "fundamentals"}, "data-class-invalid")
    if value["vintage_kind"] == "historical-outcome-vintage":
        _sha(value["outcome_vintage_sha256"], "outcome-vintage")
        _require(value["data_class"] == "price-and-corporate-action", "outcome-data-class-differs")
    else:
        _require(value["outcome_vintage_sha256"] is None and value["data_class"] != "price-and-corporate-action",
                 "reference-is-not-outcome-vintage")
    _require(type(value["representation"]) is str and value["representation"] in {
        "local-only", "local-and-quantconnect", "quantconnect-only"}, "representation-invalid")
    _require(value["platform"] == ("local" if value["representation"] == "local-only" else "QuantConnect Cloud"),
             "platform-representation-differs")
    _require(_date(value["first_session"]) <= _date(value["last_session"]), "coverage-reversed")
    profile = value["market_data_profile"]
    if profile is not None:
        _fields(profile, {"provider", "asset_class", "stock_resolution", "stock_price_normalization",
            "stock_fill_forward", "stock_extended_market_hours_argument", "clock_ticker", "clock_resolution",
            "clock_extended_market_hours", "clock_fill_forward"}, "market-profile")
        for field in ("stock_fill_forward", "clock_extended_market_hours", "clock_fill_forward"):
            _require(type(profile[field]) is bool, "market-profile-boolean-invalid")
        for field in ("provider", "asset_class", "stock_resolution", "stock_price_normalization",
                      "stock_extended_market_hours_argument", "clock_ticker", "clock_resolution"):
            _identity(profile[field], "market-profile")
    _require(type(value["clock_data_entitlements"]) is list and len(value["clock_data_entitlements"]) <= 8
             and all(type(v) is str and _ID.fullmatch(v) is not None for v in value["clock_data_entitlements"])
             and value["clock_data_entitlements"] == sorted(set(value["clock_data_entitlements"])), "clock-inventory-invalid")
    return value


def _probe(raw: bytes, roots: ProviderRightsTrustRoots, subject: dict, evaluated: datetime) -> dict:
    row = _json(raw, roots.probe_receipt_sha256, "probe-receipt")
    _fields(row, {"schema", "provider", "completed_at_utc", "started_sha256", "receipt"}, "completed-probe")
    _require(row["schema"] == "insider-provider-metadata-one-shot-audit-v1"
             and row["provider"] == subject["provider"], "probe-provider-schema-differs")
    _sha(row["started_sha256"], "started")
    _require(_utc(row["completed_at_utc"]) <= evaluated, "probe-after-evaluation")
    item = row["receipt"]
    _fields(item, {"kind", "provider", "request_profile", "http_status", "body_sha256", "body_size_bytes",
        "body_complete", "disposition", "facts", "http_access_observed", "authentication_observed",
        "entitlement_verified", "rights_verified", "historical_coverage_verified", "research_ready",
        "qc_backtest_authorized", "outcome_access_authorized"}, "probe")
    provider = subject["provider"]
    _require(item["kind"] == "insider-provider-metadata-receipt-v1" and item["provider"] == provider
             and item["request_profile"] == _PROFILE[provider], "probe-profile-differs")
    status = item["http_status"]
    _require(status is None or (type(status) is int and 100 <= status <= 599), "http-status-invalid")
    _require(type(item["body_size_bytes"]) is int and 0 <= item["body_size_bytes"] <= 1024 * 1024 + 1,
             "probe-body-size-invalid")
    _require(type(item["body_complete"]) is bool and type(item["facts"]) is dict, "probe-shape-invalid")
    if item["body_sha256"] is not None:
        _sha(item["body_sha256"], "probe-body")
    else:
        _require(item["body_size_bytes"] == 0 and item["body_complete"] is False and status is None,
                 "missing-body-inconsistent")
    disposition = item["disposition"]
    _require(type(disposition) is str and disposition in _FAILURES | {_OBSERVATIONS[provider]}, "probe-disposition-invalid")
    observed = disposition == _OBSERVATIONS[provider]
    if observed:
        _require(type(status) is int and 200 <= status < 300 and item["body_complete"] is True
                 and item["body_sha256"] is not None and item["body_size_bytes"] > 0, "successful-probe-inconsistent")
    auth = provider == "quantconnect" and observed
    _require(type(item["http_access_observed"]) is bool and item["http_access_observed"] == (status is not None)
             and type(item["authentication_observed"]) is bool and item["authentication_observed"] == auth,
             "probe-observation-inconsistent")
    if provider == "quantconnect" and observed:
        _require(item["facts"] == {"success": True} and type(item["facts"]["success"]) is bool,
                 "authentication-facts-differ")
    for flag in ("entitlement_verified", "rights_verified", "historical_coverage_verified", "research_ready",
                 "qc_backtest_authorized", "outcome_access_authorized"):
        _require(item[flag] is False, "probe-cannot-promote-authority")
    return {"request_profile": item["request_profile"], "disposition": disposition,
        "http_access_observed": item["http_access_observed"], "authentication_observed": auth,
        "public_metadata_observed": observed and not auth, "account_identity_verified_here": False,
        "purchased_product_entitlement": "UNMEASURED", "historical_coverage": "UNMEASURED"}


def _clause(value: dict, documents: dict[str, tuple[dict, bytes]]) -> str:
    _fields(value, {"document_id", "start_byte", "end_byte", "clause_sha256"}, "clause")
    key = value["document_id"]
    _require(type(key) is str and key in documents, "clause-document-missing")
    _, raw = documents[key]
    start, end = value["start_byte"], value["end_byte"]
    _require(type(start) is int and type(end) is int and 0 <= start < end <= len(raw)
             and end - start <= 128 * 1024, "clause-range-invalid")
    _sha(value["clause_sha256"], "clause")
    _require(hash_bytes(raw[start:end]) == value["clause_sha256"], "clause-bytes-differ")
    return key


def _contract(index_raw: bytes, docs: tuple[bytes, ...], assessment_raw: bytes,
              roots: ProviderRightsTrustRoots, subject: dict, evaluated: datetime) -> tuple[dict, dict]:
    index = _json(index_raw, roots.terms_index_sha256, "terms-index")
    _fields(index, {"schema", "trust_scope", "subject_sha256", "probe_receipt_sha256", "effective_at_utc",
                    "expires_at_utc", "documents"}, "terms-index")
    _require(index["schema"] == "insider-provider-private-terms-index-v1"
             and index["trust_scope"] == roots.trust_scope and index["subject_sha256"] == roots.subject_sha256
             and index["probe_receipt_sha256"] == roots.probe_receipt_sha256, "terms-subject-roots-differ")
    start, end = _utc(index["effective_at_utc"]), _utc(index["expires_at_utc"])
    _require(start < end, "contract-effective-window-invalid")
    _require(type(docs) is tuple and type(index["documents"]) is list and 0 < len(docs) <= MAX_DOCUMENTS
             and len(docs) == len(index["documents"]), "document-inventory-incomplete")
    documents, total = {}, 0
    for descriptor, raw in zip(index["documents"], docs, strict=True):
        _fields(descriptor, {"document_id", "sha256", "byte_length", "kind", "account_pseudonym", "product_id"}, "document")
        key = descriptor["document_id"]
        _identity(key, "document")
        _require(key not in documents, "duplicate-document")
        _sha(descriptor["sha256"], "document")
        _require(type(raw) is bytes and 0 < len(raw) <= MAX_DOCUMENT_BYTES
                 and type(descriptor["byte_length"]) is int and descriptor["byte_length"] == len(raw)
                 and descriptor["sha256"] == hash_bytes(raw), "document-bytes-differ")
        total += len(raw)
        _require(total <= MAX_DOCUMENT_TOTAL_BYTES, "document-total-oversized")
        _require(type(descriptor["kind"]) is str and descriptor["kind"] in {
            "account-purchase", "provider-account-confirmation", "public-incorporated-terms"}, "document-kind-invalid")
        _require(descriptor["product_id"] == subject["product_id"], "document-product-differs")
        _require(descriptor["account_pseudonym"] == (None if descriptor["kind"] == "public-incorporated-terms"
                    else subject["account_pseudonym"]), "document-account-differs")
        documents[key] = descriptor, raw
    assessment = _json(assessment_raw, roots.permission_assessment_sha256, "permission-assessment")
    _fields(assessment, {"schema", "trust_scope", "subject_sha256", "probe_receipt_sha256", "terms_index_sha256",
        "assessed_at_utc", "assessment_basis", "account_identity_binding", "permissions"}, "permission-assessment")
    _require(assessment["schema"] == "insider-provider-contract-permission-assessment-v1"
             and assessment["trust_scope"] == roots.trust_scope and assessment["subject_sha256"] == roots.subject_sha256
             and assessment["probe_receipt_sha256"] == roots.probe_receipt_sha256
             and assessment["terms_index_sha256"] == roots.terms_index_sha256, "assessment-roots-differ")
    _require(start <= _utc(assessment["assessed_at_utc"]) <= evaluated, "assessment-instant-differs")
    _require(type(assessment["assessment_basis"]) is str and assessment["assessment_basis"] in {
        "externally-reviewed-applicable-contract", "provider-account-confirmation", "not-established"},
        "authentication-public-terms-or-delegation-is-not-permission")
    rows = assessment["permissions"]
    _require(type(rows) is list and len(rows) == len(PERMISSIONS), "permission-inventory-incomplete")
    statuses = {}
    established = False
    for row, permission in zip(rows, PERMISSIONS, strict=True):
        _fields(row, {"permission", "status", "basis", "clause_bindings"}, "permission")
        _require(row["permission"] == permission, "permission-inventory-reordered")
        _require(type(row["status"]) is str and row["status"] in {"UNMEASURED", "REFUSED", "GRANTED"}, "permission-status-invalid")
        _require(type(row["clause_bindings"]) is list and len(row["clause_bindings"]) <= MAX_DOCUMENTS, "permission-clause-inventory-invalid")
        status = row["status"]
        if status == "UNMEASURED":
            _require(row["basis"] == "not-established" and not row["clause_bindings"], "unmeasured-permission-cannot-claim-clause")
        else:
            established = True
            _require(assessment["assessment_basis"] != "not-established" and row["clause_bindings"], "permission-evidence-missing")
            expected_basis = "applicable-contract-" + ("grant" if status == "GRANTED" else "refusal")
            if assessment["assessment_basis"] == "provider-account-confirmation":
                expected_basis = "provider-account-confirmed-" + ("grant" if status == "GRANTED" else "refusal")
            _require(row["basis"] == expected_basis, "permission-basis-differs")
            clause_keys = [_clause(binding, documents) for binding in row["clause_bindings"]]
            _require(len({canonical_json(binding) for binding in row["clause_bindings"]}) == len(clause_keys), "duplicate-clause")
            if assessment["assessment_basis"] == "provider-account-confirmation":
                _require(any(documents[key][0]["kind"] == "provider-account-confirmation" for key in clause_keys),
                         "provider-confirmation-clause-missing")
        statuses[permission] = status
    identity = assessment["account_identity_binding"]
    if established:
        key = _clause(identity, documents)
        _require(documents[key][0]["kind"] != "public-incorporated-terms", "public-terms-do-not-bind-private-account")
    else:
        _require(identity is None and assessment["assessment_basis"] == "not-established", "unmeasured-account-binding-differs")
    current = start <= evaluated < end
    return statuses, {"effective_at_utc": index["effective_at_utc"], "expires_at_utc": index["expires_at_utc"],
        "current_at_evaluation": current, "assessment_basis": assessment["assessment_basis"],
        "private_account_contract_binding_supplied": established,
        "document_inventory": [{key: descriptor[key] for key in ("document_id", "sha256", "byte_length", "kind")}
                               for descriptor, _ in documents.values()]}


@dataclass(frozen=True, slots=True, weakref_slot=True)
class ProviderRightsEvidence:
    """Sealed detached report; no supplied private document bytes are retained."""
    _bytes: bytes

    def to_payload(self) -> dict:
        registered = _REGISTRY.get(id(self))
        _require(type(self) is ProviderRightsEvidence and registered is not None and registered[0]() is self
                 and type(self._bytes) is bytes and registered[1] == self._bytes, "not-an-unchanged-factory-result")
        return json.loads(self._bytes)

    @property
    def sha256(self) -> str:
        self.to_payload()
        return hash_bytes(self._bytes)

    def backtest_rights_declaration(self, *, expected_subject_sha256: str, expected_account_pseudonym: str,
                                   expected_source_manifest_sha256: str, expected_outcome_vintage_sha256: str,
                                   evaluated_at_utc: str) -> dict:
        """Project a bound supplied assessment, NOT an entitlement or look grant.

        The mapping sidecar must accompany the legacy rights artifact. Native QC
        product entitlement, source/PIT truth, raw-data export permission, and
        permanent-look authority still need their independent factual gates.
        This method never produces a qc_entitlement or authorization artifact.
        """
        payload = self.to_payload()
        subject, contract = payload["subject"], payload["contract"]
        _require(evaluated_at_utc == payload["evaluated_at_utc"] and contract is not None
                 and contract["current_at_evaluation"] is True, "contract-not-current-at-exact-evaluation")
        _require(payload["permission_status"] == dict.fromkeys(PERMISSIONS, "GRANTED"), "all-processing-permissions-not-granted")
        for supplied, expected in ((payload["roots"]["subject_sha256"], expected_subject_sha256),
            (subject["source_manifest_sha256"], expected_source_manifest_sha256),
            (subject["outcome_vintage_sha256"], expected_outcome_vintage_sha256)):
            _sha(expected, "projection")
            _require(supplied == expected, "projection-external-binding-differs")
        _require(subject["account_pseudonym"] == expected_account_pseudonym, "projection-account-differs")
        _require(subject["provider"] == "quantconnect" and subject["vintage_kind"] == "historical-outcome-vintage"
                 and subject["data_class"] == "price-and-corporate-action"
                 and subject["representation"] == "local-and-quantconnect" and subject["platform"] == "QuantConnect Cloud",
                 "not-native-qc-historical-outcome-representation")
        expected_profile = {"provider": "QuantConnect-native", "asset_class": "US-equity", "stock_resolution": "minute",
            "stock_price_normalization": "raw", "stock_fill_forward": False,
            "stock_extended_market_hours_argument": "omitted", "clock_ticker": "SPY", "clock_resolution": "minute",
            "clock_extended_market_hours": True, "clock_fill_forward": False}
        _require(canonical_json(subject["market_data_profile"]) == canonical_json(expected_profile)
                 and subject["clock_data_entitlements"] == ["SPY"], "native-feed-clock-profile-differs")
        artifact = {"schema": "insider-backtest-rights-v1", "trust_scope": payload["trust_scope"],
            "account_id": subject["account_pseudonym"], "dataset_id": subject["dataset_id"], "vintage_id": subject["vintage_id"],
            "outcome_vintage_sha256": subject["outcome_vintage_sha256"], "representation": subject["representation"],
            "platform": subject["platform"], "first_session": subject["first_session"], "last_session": subject["last_session"],
            "market_data_profile": subject["market_data_profile"], "clock_data_entitlements": subject["clock_data_entitlements"],
            "use": "single-research-backtest-only", "permissions": list(PERMISSIONS)}
        return {"schema": "insider-provider-rights-package-mapping-v1", "rights_artifact": artifact,
            "rights_artifact_sha256": hash_bytes(canonical_json(artifact).encode("utf-8")),
            "provider": subject["provider"], "product_id": subject["product_id"],
            "source_manifest_sha256": subject["source_manifest_sha256"], "evidence_sha256": self.sha256,
            "subject_sha256": payload["roots"]["subject_sha256"],
            "probe_receipt_sha256": payload["roots"]["probe_receipt_sha256"],
            "terms_index_sha256": payload["roots"]["terms_index_sha256"],
            "permission_assessment_sha256": payload["roots"]["permission_assessment_sha256"],
            "qc_entitlement_verified_here": False, "legal_interpretation_performed_here": False,
            "source_pit_rights_look_qc_backtest_execution_authority": False}


def admit_provider_rights_evidence(*, probe_receipt_raw: bytes, subject_raw: bytes,
                                  trust_roots: ProviderRightsTrustRoots, evaluated_at_utc: str,
                                  terms_index_raw: bytes | None = None, term_document_bytes: tuple[bytes, ...] = (),
                                  permission_assessment_raw: bytes | None = None) -> ProviderRightsEvidence:
    """Admit exact supplied completed-probe and separately assessed contract bytes.

    Without a complete contract bundle all three permissions stay UNMEASURED.
    REFUSED is a supplied contract disposition, not an HTTP failure. Expired
    grants remain historically recorded GRANTED but are explicitly noncurrent
    and cannot be projected. Subject vintage/coverage never comes from a probe.
    No externally supplied roots are described as independently authenticated.
    """
    _require(type(trust_roots) is ProviderRightsTrustRoots, "exact-trust-roots-required")
    trust_roots.__post_init__()
    evaluated = _utc(evaluated_at_utc)
    subject = _subject(subject_raw, trust_roots)
    probe = _probe(probe_receipt_raw, trust_roots, subject, evaluated)
    supplied = trust_roots.terms_index_sha256 is not None
    _require(type(term_document_bytes) is tuple, "document-inventory-not-immutable")
    _require(supplied == (terms_index_raw is not None) == (permission_assessment_raw is not None), "partial-contract-bundle")
    if supplied:
        statuses, contract = _contract(terms_index_raw, term_document_bytes, permission_assessment_raw,
                                       trust_roots, subject, evaluated)
    else:
        _require(not term_document_bytes, "unbound-private-document-bytes")
        statuses, contract = dict.fromkeys(PERMISSIONS, "UNMEASURED"), None
    raw = canonical_json({"schema": "insider-provider-rights-evidence-v1", "trust_scope": trust_roots.trust_scope,
        "evaluated_at_utc": evaluated_at_utc, "roots": {name: getattr(trust_roots, name) for name in (
            "probe_receipt_sha256", "subject_sha256", "terms_index_sha256", "permission_assessment_sha256")},
        "subject": subject, "probe_observation": probe, "permission_status": statuses, "contract": contract,
        "external_roots_are_not_authentication": True, "subject_is_external_claim_not_probe_derived": True,
        "subject_coverage_vintage_verified_here": False, "document_authenticity_verified_here": False,
        "legal_interpretation_performed_here": False, "private_document_bytes_retained": False,
        "qc_entitlement_verified_here": False, "permanent_look_allocated": False, "research_ready": False,
        "source_pit_rights_look_qc_backtest_execution_authority": False}).encode("utf-8")
    result = ProviderRightsEvidence(raw)
    key = id(result)
    _REGISTRY[key] = (weakref.ref(result, lambda _: _REGISTRY.pop(key, None)), raw)
    return result
