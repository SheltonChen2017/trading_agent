"""Invented SEC pilot bytes only; no external artifact, provider, or outcome access."""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, replace
import inspect
import os
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_acquisition_preparation import SecAcquisitionTarget
from research.insider_buying import sec_pilot_ib1c_readiness as readiness
from research.insider_buying.sec_raw_parent_projection import derive_sec_raw_parent_projection
from research import insider_buying_sec_pilot_projection_adapter as adapter


_PILOT_VERSION = "INSETF-SEC-SIXTEEN-ACQUISITION-v1"
_CONTINUATION_VERSION = "INSETF-SEC-SIXTEEN-XML-CONTINUATION-v1"
_INDEX_ROUTE_VERSION = "sec-accession-directory-index-json-v1"
_FIRST_REPORT_SHA256 = "410bbb079f9cec25733e798d3aceaea179c0d47d657743d199a041922d81f642"
_FIRST_JOURNAL_SHA256 = "e56ec3fb369a11598bb2ac30cf5fd1f1e299c52fae1a6ee410c6816c4d2586db"
_FIRST_CODE_COMMIT = "f5430fff9b09a963b5cb0307c9e87b28a69c4767"
_CONTINUATION_CODE_COMMIT = "5cc897dbf9b7e9216370b2157ef79c9c9b2a0508"
_FIRST_REASON = "REFUSED: missing or ambiguous ACCESSION NUMBER"


def _canonical_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _candidate(year: int, ordinal: int) -> dict[str, str]:
    accession = f"0000999999-{year % 100:02d}-{ordinal:06d}"
    period = "2022Q4" if year == 2022 else "2023Q1"
    filing_date = "2022-11-07" if year == 2022 else "2023-03-13"
    return {
        "period": period,
        "accession_number": accession,
        "form_type": "4" if ordinal <= 6 else "4/A",
        "filing_date_raw": "07-NOV-2022" if year == 2022 else "13-MAR-2023",
        "filing_date": filing_date,
        "issuer_cik": "0000123456",
        "quarterly_zip_sha256": ("a" if year == 2022 else "b") * 64,
        "submission_row_id": hash_bytes(accession.encode("ascii")),
        "raw_snapshot_id": f"invented-sec-insider-bulk-{period.lower()}",
        "raw_lineage_sha256": hash_bytes(f"invented-{period}".encode("ascii")),
    }


def _archive_root(candidate: dict[str, str]) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/123456/"
        + candidate["accession_number"].replace("-", "") + "/"
    )


def _raw_images(candidate: dict[str, str], ordinal: int) -> tuple[str, dict[str, bytes]]:
    accession = candidate["accession_number"]
    filing_raw = candidate["filing_date"].replace("-", "")
    accepted_raw = filing_raw + "101112"
    owner_cik = f"{900000 + (100 if candidate['period'] == '2023Q1' else 0) + ordinal:010d}"
    filename = f"invented{candidate['period'].lower()}{ordinal}.xml"
    index = _canonical_bytes({"directory": {"item": [{"name": filename}]}})
    header = (
        f"<SEC-HEADER>{accession}.hdr.sgml : {filing_raw}\n"
        f"<ACCEPTANCE-DATETIME>{accepted_raw}\n"
        f"<ACCESSION-NUMBER>{accession}\n"
        f"<TYPE>{candidate['form_type']}\n"
        f"<FILING-DATE>{filing_raw}\n"
        "<REPORTING-OWNER>\n<OWNER-DATA>\n"
        f"<CIK>{owner_cik}\n<CONFORMED-NAME>Invented Owner\n"
        "</OWNER-DATA>\n</REPORTING-OWNER>\n"
        "<ISSUER>\n<COMPANY-DATA>\n<CIK>0000123456\n"
        "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
    ).encode("ascii")
    xml = (
        "<ownershipDocument>"
        f"<documentType>{candidate['form_type']}</documentType>"
        "<issuer><issuerCik>0000123456</issuerCik></issuer>"
        "<reportingOwner><reportingOwnerId>"
        f"<rptOwnerCik>{owner_cik}</rptOwnerCik>"
        "</reportingOwnerId></reportingOwner>"
        "</ownershipDocument>"
    ).encode("ascii")
    return filename, {"index": index, "header": header, "xml": xml}


def _tag_receipt(candidate: dict[str, str], header: bytes) -> dict[str, object]:
    accepted = (
        candidate["filing_date"] + "T10:11:12"
        + ("-05:00" if candidate["period"] == "2022Q4" else "-04:00")
    )
    return {
        "version": "sec-header-tag-line-compat-v1",
        "raw_header_sha256": hash_bytes(header),
        "raw_header_size_bytes": len(header),
        "source_url": _archive_root(candidate) + candidate["accession_number"] + ".hdr.sgml",
        "source_fields": {
            "accession_number": candidate["accession_number"],
            "form_type": candidate["form_type"],
            "filing_date_raw": candidate["filing_date"].replace("-", ""),
            "accepted_at_raw": candidate["filing_date"].replace("-", "") + "101112",
            "issuer_cik_raw": candidate["issuer_cik"],
        },
        "accepted_at_interpretation": accepted,
        "timezone_interpretation_verified": False,
        "retrieval_timestamp_unavailable": True,
        "official_sec_profile_verified": False,
        "direct_ib1c_ingest_authorized": False,
        "canonical": False,
    }


@dataclass
class _SyntheticPilot:
    root: Path
    report: dict[str, object]
    inventory: dict[str, object]
    report_sha256: str
    inventory_sha256: str
    accessions: tuple[str, ...]
    expected_rows: tuple[dict[str, object], ...]

    @property
    def report_path(self) -> Path:
        return self.root / f"sec-pilot-report-{self.report_sha256}.json"

    def load(self):
        return adapter._load_pilot_projections(
            self.root,
            report_sha256=self.report_sha256,
            inventory_sha256=self.inventory_sha256,
            expected_accessions=self.accessions,
        )

    def republish_report(self) -> None:
        """Bind a semantic mutation to a fresh report/commit hash."""
        self.report_path.unlink()
        report_bytes = _canonical_bytes(self.report)
        self.report_sha256 = hash_bytes(report_bytes)
        self.report_path.write_bytes(report_bytes)
        (self.root / "commit.json").write_bytes(_canonical_bytes({
            "kind": "sec-pilot-commit",
            "report": self.report_path.name,
            "report_sha256": self.report_sha256,
        }))


def _make_synthetic_pilot(root: Path) -> _SyntheticPilot:
    root.mkdir()
    objects = root / "objects"
    objects.mkdir()
    candidates: list[dict[str, str]] = []
    rows: list[dict[str, object]] = []
    expected_rows: list[dict[str, object]] = []
    requests: list[str] = []
    for year in (2022, 2023):
        for ordinal in range(1, 9):
            candidate = _candidate(year, ordinal)
            filename, images = _raw_images(candidate, ordinal)
            candidates.append(candidate)
            target = SecAcquisitionTarget(
                period=candidate["period"],
                accession_number=candidate["accession_number"],
                form_type=candidate["form_type"],
                filing_date=candidate["filing_date"],
                issuer_cik=candidate["issuer_cik"],
                quarterly_zip_sha256=candidate["quarterly_zip_sha256"],
                submission_row_id=candidate["submission_row_id"],
                primary_xml_filename=filename,
            )
            projection = derive_sec_raw_parent_projection(
                target, images["index"], images["header"], images["xml"]
            )
            descriptors = {}
            for role, raw in images.items():
                digest = hash_bytes(raw)
                (objects / f"{digest}.bin").write_bytes(raw)
                descriptors[role] = {
                    "relative_path": f"objects/{digest}.bin",
                    "sha256": digest,
                    "size_bytes": len(raw),
                }
            rows.append({
                "candidate": candidate,
                "primary_xml_filename": filename,
                "status": "acquired_noncanonical",
                "reason": None,
                "first_pass_reason": _FIRST_REASON,
                "artifacts": descriptors,
                "tag_header_validation": _tag_receipt(candidate, images["header"]),
            })
            expected_rows.append({
                "accession_number": candidate["accession_number"],
                "period": candidate["period"],
                "form_type": candidate["form_type"],
                "projection_sha256": projection.sha256,
                "raw_parent_hashes": {role: descriptor["sha256"]
                                      for role, descriptor in descriptors.items()},
                "derived_projection_sha256": hash_bytes(projection.derived_json_bytes),
            })
            requests.append(_archive_root(candidate) + filename)

    assert len(candidates) == 16
    assert len({child.name for child in objects.iterdir()}) == 48
    inventory_sha256 = hash_payload(candidates)
    inventory = {
        "kind": "sec-pilot-frozen-inventory",
        "version": _PILOT_VERSION,
        "index_route_version": _INDEX_ROUTE_VERSION,
        "inventory_sha256": inventory_sha256,
        "candidates": candidates,
        "continuation": {
            "version": _CONTINUATION_VERSION,
            "first_pass_report_sha256": _FIRST_REPORT_SHA256,
            "first_pass_journal_sha256": _FIRST_JOURNAL_SHA256,
            "first_pass_attempts": 32,
            "first_pass_code_commit_operator_attested": _FIRST_CODE_COMMIT,
            "prior_code_sha_artifact_verified": False,
            "continuation_code_commit_verified": _CONTINUATION_CODE_COMMIT,
            "requests": requests,
        },
    }
    (root / "inventory.json").write_bytes(_canonical_bytes(inventory))
    (root / "attempts.jsonl").write_bytes(b"")
    report = {
        "kind": _CONTINUATION_VERSION,
        "canonical": False,
        "point_in_time_data": False,
        "direct_ib1c_ingest_authorized": False,
        "source_authenticity_verified": False,
        "official_sec_profile_verified": False,
        "timezone_interpretation_verified": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
        "inventory_sha256": inventory_sha256,
        "index_route_version": _INDEX_ROUTE_VERSION,
        "first_pass_report_sha256": _FIRST_REPORT_SHA256,
        "first_pass_journal_sha256": _FIRST_JOURNAL_SHA256,
        "first_pass_code_commit_operator_attested": _FIRST_CODE_COMMIT,
        "prior_code_sha_artifact_verified": False,
        "continuation_code_commit_verified": _CONTINUATION_CODE_COMMIT,
        "cumulative_attempt_count": 48,
        "cumulative_distinct_artifact_count": 48,
        "new_attempt_count": 16,
        "halted_on_sec_access": False,
        "rows": rows,
        "acquisition_available": True,
    }
    report_bytes = _canonical_bytes(report)
    report_sha256 = hash_bytes(report_bytes)
    report_name = f"sec-pilot-report-{report_sha256}.json"
    (root / report_name).write_bytes(report_bytes)
    (root / "commit.json").write_bytes(_canonical_bytes({
        "kind": "sec-pilot-commit",
        "report": report_name,
        "report_sha256": report_sha256,
    }))
    return _SyntheticPilot(
        root, report, inventory, report_sha256, inventory_sha256,
        tuple(item["accession_number"] for item in candidates), tuple(expected_rows),
    )


@pytest.fixture
def synthetic_pilot(tmp_path: Path) -> _SyntheticPilot:
    return _make_synthetic_pilot(tmp_path / "invented-pilot")


def _tree_state(root: Path) -> dict[str, tuple[int, int, str | None]]:
    state = {}
    for path in (root, *root.rglob("*")):
        details = path.lstat()
        state[str(path.relative_to(root))] = (
            details.st_mtime_ns,
            details.st_nlink,
            hash_bytes(path.read_bytes()) if path.is_file() else None,
        )
    return state


def test_synthetic_sixteen_filing_projection_receipt_has_exact_rows_and_zero_authority(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    before = _tree_state(synthetic_pilot.root)
    receipt = synthetic_pilot.load()
    payload = receipt.to_payload()
    assert _tree_state(synthetic_pilot.root) == before
    assert payload["version"] == adapter.OFFLINE_PILOT_ADAPTER_VERSION
    assert payload["source_report_sha256"] == synthetic_pilot.report_sha256
    assert payload["source_inventory_sha256"] == synthetic_pilot.inventory_sha256
    assert payload["rows"] == list(synthetic_pilot.expected_rows)
    assert len({row["projection_sha256"] for row in payload["rows"]}) == 16
    assert len({digest for row in payload["rows"]
                for digest in row["raw_parent_hashes"].values()}) == 48
    assert Counter((row["period"], row["form_type"]) for row in payload["rows"]) == {
        ("2022Q4", "4"): 6, ("2022Q4", "4/A"): 2,
        ("2023Q1", "4"): 6, ("2023Q1", "4/A"): 2,
    }
    authority = payload["authority"]
    assert authority["input_scope"] == "synthetic_test_receipt"
    assert all(type(value) in (bool, int) and value == 0
               for name, value in authority.items() if name != "input_scope")
    payload["rows"][0]["raw_parent_hashes"]["index"] = "0" * 64
    payload["authority"]["canonical_evidence"] = True
    assert receipt.to_payload()["rows"] == list(synthetic_pilot.expected_rows)
    assert receipt.to_payload()["authority"]["canonical_evidence"] is False


def test_receipt_cannot_be_directly_fabricated_or_relabelled_as_retained_pilot(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    receipt = synthetic_pilot.load()
    with pytest.raises(adapter.SecOfflinePilotAdapterError, match="verified loader"):
        adapter.SecOfflinePilotProjectionReceipt(
            report_sha256=adapter.FINAL_REPORT_SHA256,
            inventory_sha256=adapter.INVENTORY_SHA256,
            projections=receipt.projections,
            _report_bytes=receipt._report_bytes,
            _expected_accessions=adapter.FIXED_ACCESSIONS,
            _projection_sha256s=tuple(item.sha256 for item in receipt.projections),
            _public_pilot=True,
            _loader_token=object(),
        )
    object.__setattr__(receipt, "_public_pilot", True)
    with pytest.raises(adapter.SecOfflinePilotAdapterError, match="approved source pins"):
        receipt.to_payload()


def test_receipt_rejects_changed_parent_even_when_projection_hash_pin_is_replaced(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    receipt = synthetic_pilot.load()
    first = receipt.projections[0]
    index = _canonical_bytes({"directory": {"item": [
        {"name": first.target.primary_xml_filename}, {"name": "invented-notes.txt"},
    ]}})
    changed = derive_sec_raw_parent_projection(
        first.target, index, first.header_bytes, first.xml_bytes,
    )
    with pytest.raises(adapter.SecOfflinePilotAdapterError, match="parent differs from report"):
        replace(
            receipt,
            projections=(changed, *receipt.projections[1:]),
            _projection_sha256s=(changed.sha256, *receipt._projection_sha256s[1:]),
        )


def test_public_loader_keeps_real_report_inventory_and_accession_pins(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    assert adapter.FINAL_REPORT_SHA256 == (
        "722ab1b03c93d1d6aa61f798b2cb6a391a934ee8a334034eff2b5102cea40ec5"
    )
    assert adapter.INVENTORY_SHA256 == (
        "4b8a4c3a233855ea2aa6cde0b2739a83aca478180ac881e1cf011943753d78db"
    )
    assert adapter.FIXED_ACCESSIONS == (
        "0000002178-22-000091", "0000002178-22-000094", "0000002178-22-000095",
        "0000002178-22-000097", "0000002178-22-000099", "0000002488-22-000165",
        "0000050725-22-000079", "0000050725-22-000083",
        "0000002178-23-000019", "0000002178-23-000020", "0000002178-23-000021",
        "0000002178-23-000022", "0000002178-23-000023", "0000002178-23-000024",
        "0000016058-23-000011", "0000019745-23-000002",
    )
    assert synthetic_pilot.report_sha256 != adapter.FINAL_REPORT_SHA256
    assert synthetic_pilot.inventory_sha256 != adapter.INVENTORY_SHA256
    assert synthetic_pilot.accessions != adapter.FIXED_ACCESSIONS
    with pytest.raises(ValueError, match="REFUSED"):
        adapter.load_fixed_pilot_projections(synthetic_pilot.root)
    for override in (
        {"report_sha256": synthetic_pilot.report_sha256},
        {"inventory_sha256": synthetic_pilot.inventory_sha256},
        {"expected_accessions": synthetic_pilot.accessions},
    ):
        with pytest.raises(TypeError):
            adapter.load_fixed_pilot_projections(synthetic_pilot.root, **override)


def test_adapter_static_imports_do_not_cross_the_sec_transport_boundary() -> None:
    tree = ast.parse(inspect.getsource(adapter))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    forbidden = (
        "research.insider_buying_sec_acquisition",
        "http", "urllib", "requests", "socket", "aiohttp", "subprocess",
    )
    assert all(
        name != prefix and not name.startswith(prefix + ".")
        for name in imported for prefix in forbidden
    )


@pytest.mark.parametrize("part", ["report", "inventory", "object"])
def test_tampered_bytes_refuse_even_when_original_pins_are_supplied(
    synthetic_pilot: _SyntheticPilot, part: str,
) -> None:
    if part == "report":
        target = synthetic_pilot.report_path
    elif part == "inventory":
        target = synthetic_pilot.root / "inventory.json"
    else:
        digest = synthetic_pilot.expected_rows[0]["raw_parent_hashes"]["xml"]
        target = synthetic_pilot.root / "objects" / f"{digest}.bin"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_pilot.load()


@pytest.mark.parametrize("part", ["commit", "report", "inventory", "journal", "object"])
def test_missing_publication_component_refuses(
    synthetic_pilot: _SyntheticPilot, part: str,
) -> None:
    target = {
        "commit": synthetic_pilot.root / "commit.json",
        "report": synthetic_pilot.report_path,
        "inventory": synthetic_pilot.root / "inventory.json",
        "journal": synthetic_pilot.root / "attempts.jsonl",
        "object": synthetic_pilot.root / "objects" / (
            synthetic_pilot.expected_rows[0]["raw_parent_hashes"]["header"] + ".bin"
        ),
    }[part]
    target.unlink()
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_pilot.load()


@pytest.mark.parametrize("location", ["root", "objects"])
def test_extra_publication_component_refuses(
    synthetic_pilot: _SyntheticPilot, location: str,
) -> None:
    if location == "root":
        extra = synthetic_pilot.root / "unexpected.txt"
    else:
        extra = synthetic_pilot.root / "objects" / ("0" * 64 + ".bin")
    extra.write_bytes(b"invented extra")
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_pilot.load()


def test_hardlink_alias_of_an_object_refuses(
    synthetic_pilot: _SyntheticPilot, tmp_path: Path,
) -> None:
    digest = synthetic_pilot.expected_rows[0]["raw_parent_hashes"]["index"]
    source = synthetic_pilot.root / "objects" / f"{digest}.bin"
    os.link(source, tmp_path / "invented-hardlink-alias.bin")
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_pilot.load()


@pytest.mark.parametrize("part", ["inventory", "journal", "object"])
def test_symlink_redirect_refuses_even_when_target_bytes_match(
    synthetic_pilot: _SyntheticPilot, tmp_path: Path, part: str,
) -> None:
    if part == "inventory":
        target = synthetic_pilot.root / "inventory.json"
    elif part == "journal":
        target = synthetic_pilot.root / "attempts.jsonl"
    else:
        digest = synthetic_pilot.expected_rows[0]["raw_parent_hashes"]["xml"]
        target = synthetic_pilot.root / "objects" / f"{digest}.bin"
    outside = tmp_path / f"invented-{part}-target"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_pilot.load()


@pytest.mark.parametrize(("field", "value"), [
    ("canonical", True),
    ("point_in_time_data", True),
    ("direct_ib1c_ingest_authorized", True),
    ("source_authenticity_verified", True),
    ("official_sec_profile_verified", True),
    ("timezone_interpretation_verified", True),
    ("prior_code_sha_artifact_verified", True),
    ("research_looks", 1),
    ("authorized_outcome_looks", 1),
    ("consumed_outcome_looks", 1),
])
def test_rehashed_report_cannot_promote_authority_or_looks(
    synthetic_pilot: _SyntheticPilot, field: str, value: object,
) -> None:
    synthetic_pilot.report[field] = value
    synthetic_pilot.republish_report()
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_pilot.load()


@pytest.mark.parametrize("mutation", ["missing_row", "extra_row", "wrong_quarter_form"])
def test_rehashed_report_refuses_incomplete_or_drifted_fixed_sample(
    synthetic_pilot: _SyntheticPilot, mutation: str,
) -> None:
    rows = synthetic_pilot.report["rows"]
    assert type(rows) is list
    if mutation == "missing_row":
        rows.pop()
    elif mutation == "extra_row":
        rows.append(rows[-1].copy())
    else:
        rows[0]["candidate"]["form_type"] = "4/A"
    synthetic_pilot.republish_report()
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_pilot.load()


def test_canonical_rewritten_inventory_request_drift_refuses(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    continuation = synthetic_pilot.inventory["continuation"]
    assert type(continuation) is dict
    continuation["requests"][0] = "https://www.sec.gov/Archives/edgar/data/123456/wrong.xml"
    (synthetic_pilot.root / "inventory.json").write_bytes(
        _canonical_bytes(synthetic_pilot.inventory)
    )
    with pytest.raises(ValueError, match="REFUSED"):
        synthetic_pilot.load()


def test_ib1c_readiness_is_an_exact_sixteen_row_blocker_inventory_only(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    receipt = synthetic_pilot.load()
    before = _tree_state(synthetic_pilot.root)
    report = readiness.assess_sec_pilot_ib1c_readiness(receipt)
    payload = report.to_payload()
    assert _tree_state(synthetic_pilot.root) == before
    assert payload["version"] == readiness.SEC_PILOT_IB1C_READINESS_VERSION
    assert payload["input_scope"] == "synthetic_test_receipt"
    assert payload["source_report_sha256"] == receipt.report_sha256
    assert payload["source_inventory_sha256"] == receipt.inventory_sha256
    assert len(payload["rows"]) == 16
    assert [row["accession_number"] for row in payload["rows"]] == list(
        synthetic_pilot.accessions
    )
    assert [row["projection_sha256"] for row in payload["rows"]] == [
        row["projection_sha256"] for row in synthetic_pilot.expected_rows
    ]
    assert [row["raw_parent_sha256s"] for row in payload["rows"]] == [
        row["raw_parent_hashes"] for row in synthetic_pilot.expected_rows
    ]
    assert all(row["reporting_owner_count"] == 1 for row in payload["rows"])
    row_blockers = [
        "VERBATIM_IB1C_METADATA_SOURCE_UNAVAILABLE",
        "RETRIEVAL_TIMESTAMP_UNAVAILABLE",
        "OFFICIAL_SEC_METADATA_PROFILE_UNVERIFIED",
        "TIMEZONE_INTERPRETATION_UNVERIFIED",
        "SOURCE_AUTHENTICITY_UNVERIFIED",
        "DIRECT_IB1C_INGEST_NOT_AUTHORIZED",
    ]
    assert all(row["blockers"][:6] == row_blockers for row in payload["rows"])
    assert sum("AMENDMENT_ORIGINAL_ACCESSION_LINK_UNAVAILABLE" in row["blockers"]
               for row in payload["rows"]) == 4
    assert payload["corpus_blockers"] == [
        "CONTINUATION_JOURNAL_NOT_REPLAYED",
        "FIRST_PASS_CODE_SHA_ARTIFACT_UNVERIFIED",
        "FIRST_PASS_PACING_TRACE_UNVERIFIED",
        "CANONICAL_82_QUARTER_CORPUS_INCOMPLETE",
    ]
    assert payload["authority"] == {
        "ib1c_ready": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "outcome_access_authorized": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }
    assert report.sha256 == hash_payload(payload)
    assert report.sha256 == readiness.assess_sec_pilot_ib1c_readiness(receipt).sha256
    payload["rows"][0]["blockers"].clear()
    payload["authority"]["canonical_evidence"] = True
    assert report.to_payload()["rows"][0]["blockers"]
    assert report.to_payload()["authority"]["canonical_evidence"] is False


def test_ib1c_readiness_refuses_foreign_partial_and_mutated_receipts(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    receipt = synthetic_pilot.load()
    with pytest.raises(readiness.SecPilotIb1cReadinessError, match="exact fixed-pilot"):
        readiness.assess_sec_pilot_ib1c_readiness(object())
    object.__setattr__(receipt, "projections", receipt.projections[:-1])
    with pytest.raises(readiness.SecPilotIb1cReadinessError, match="no longer validates"):
        readiness.assess_sec_pilot_ib1c_readiness(receipt)


def test_ib1c_readiness_refuses_authority_promotion_and_scope_spoof(
    synthetic_pilot: _SyntheticPilot, monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = synthetic_pilot.load()
    original = adapter.SecOfflinePilotProjectionReceipt.to_payload

    def promoted(self):
        payload = original(self)
        payload["authority"]["direct_ib1c_ingest_authorized"] = True
        return payload

    monkeypatch.setattr(adapter.SecOfflinePilotProjectionReceipt, "to_payload", promoted)
    with pytest.raises(readiness.SecPilotIb1cReadinessError, match="positive or unknown"):
        readiness.assess_sec_pilot_ib1c_readiness(receipt)

    def spoofed(self):
        payload = original(self)
        payload["authority"]["input_scope"] = "retained_noncanonical_pilot"
        return payload

    monkeypatch.setattr(adapter.SecOfflinePilotProjectionReceipt, "to_payload", spoofed)
    with pytest.raises(readiness.SecPilotIb1cReadinessError, match="positive or unknown"):
        readiness.assess_sec_pilot_ib1c_readiness(receipt)


def test_ib1c_readiness_report_rechecks_source_and_cannot_be_relabelled(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    receipt = synthetic_pilot.load()
    report = readiness.assess_sec_pilot_ib1c_readiness(receipt)
    with pytest.raises(readiness.SecPilotIb1cReadinessError, match="not built"):
        replace(report, _token=object())
    with pytest.raises(readiness.SecPilotIb1cReadinessError, match="not built"):
        replace(report, input_scope="retained_noncanonical_pilot")
    object.__setattr__(receipt, "_public_pilot", True)
    with pytest.raises(readiness.SecPilotIb1cReadinessError, match="no longer validates"):
        report.to_payload()


def test_ib1c_readiness_module_has_no_io_transport_or_downstream_imports() -> None:
    tree = ast.parse(inspect.getsource(readiness))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    forbidden = (
        "pathlib", "os", "http", "urllib", "requests", "socket", "subprocess",
        "research.insider_buying.sec_edgar_acceptance_snapshot",
        "research.insider_buying.form4_amendment_reconciliation",
        "research.insider_buying.form4_multi_period_amendment_evidence",
        "backtest", "qc", "quantconnect", "execution", "broker",
    )
    assert all(name != prefix and not name.startswith(prefix + ".")
               for name in imported for prefix in forbidden)


# Section 107 (Claude review): isolate adapter guards whose deletion no
# earlier test detected. Each case names its exact refusal, so a second
# guard refusing the same input can no longer hide a deleted check.
def test_commit_marker_must_name_the_pinned_report(synthetic_pilot: _SyntheticPilot) -> None:
    (synthetic_pilot.root / "commit.json").write_bytes(_canonical_bytes({
        "kind": "sec-pilot-commit",
        "report": synthetic_pilot.report_path.name,
        "report_sha256": "0" * 64,
    }))
    with pytest.raises(adapter.SecOfflinePilotAdapterError,
                       match="commit does not name the pinned report"):
        synthetic_pilot.load()


def test_canonical_report_rewrite_under_original_pins_refuses(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    synthetic_pilot.report["rows"][0]["first_pass_reason"] = "REFUSED: invented other reason"
    synthetic_pilot.report_path.write_bytes(_canonical_bytes(synthetic_pilot.report))
    with pytest.raises(adapter.SecOfflinePilotAdapterError,
                       match="report SHA-256 differs from the pinned receipt"):
        synthetic_pilot.load()


def test_receipt_refuses_substituted_report_bytes_with_the_same_rows(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    receipt = synthetic_pilot.load()
    synthetic_pilot.report["rows"][0]["first_pass_reason"] = "REFUSED: invented other reason"
    object.__setattr__(receipt, "_report_bytes", _canonical_bytes(synthetic_pilot.report))
    with pytest.raises(adapter.SecOfflinePilotAdapterError, match="lost its report byte binding"):
        receipt.to_payload()


def test_receipt_refuses_a_partial_projection_set(synthetic_pilot: _SyntheticPilot) -> None:
    receipt = synthetic_pilot.load()
    with pytest.raises(adapter.SecOfflinePilotAdapterError, match="partial or altered projection set"):
        replace(receipt, projections=receipt.projections[:-1],
                _projection_sha256s=receipt._projection_sha256s[:-1])


def test_receipt_refuses_a_substituted_projection_hash_list(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    receipt = synthetic_pilot.load()
    with pytest.raises(adapter.SecOfflinePilotAdapterError, match="partial or altered projection set"):
        replace(receipt, _projection_sha256s=("0" * 64, *receipt._projection_sha256s[1:]))


def test_receipt_refuses_a_projection_for_a_different_target_with_same_parents(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    receipt = synthetic_pilot.load()
    first = receipt.projections[0]
    changed = derive_sec_raw_parent_projection(
        replace(first.target, submission_row_id="d" * 64),
        first.index_bytes, first.header_bytes, first.xml_bytes,
    )
    with pytest.raises(adapter.SecOfflinePilotAdapterError,
                       match="projection target differs from report"):
        replace(receipt, projections=(changed, *receipt.projections[1:]),
                _projection_sha256s=(changed.sha256, *receipt._projection_sha256s[1:]))


def test_expected_accessions_out_of_order_refuse_at_the_inventory(
    synthetic_pilot: _SyntheticPilot,
) -> None:
    with pytest.raises(adapter.SecOfflinePilotAdapterError,
                       match="accessions differ from the approved 16 in order"):
        adapter._load_pilot_projections(
            synthetic_pilot.root, report_sha256=synthetic_pilot.report_sha256,
            inventory_sha256=synthetic_pilot.inventory_sha256,
            expected_accessions=synthetic_pilot.accessions[::-1],
        )


def test_relative_root_refuses_even_without_traversal(
    synthetic_pilot: _SyntheticPilot, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(synthetic_pilot.root.parent)
    with pytest.raises(adapter.SecOfflinePilotAdapterError, match="root must be absolute"):
        adapter._load_pilot_projections(
            synthetic_pilot.root.name, report_sha256=synthetic_pilot.report_sha256,
            inventory_sha256=synthetic_pilot.inventory_sha256,
            expected_accessions=synthetic_pilot.accessions,
        )


@pytest.mark.parametrize(("change", "message"), [
    ("extra_key", "report schema drifted"),
    ("identity", "report identity drifted"),
    ("unavailable", "not an available 16-row pilot"),
    ("row_status", "not an exact acquired triple"),
    ("tag_header", "tagged-header receipt differs from its raw parent"),
])
def test_rehashed_report_drift_refuses_with_its_named_reason(
    synthetic_pilot: _SyntheticPilot, change: str, message: str,
) -> None:
    report = synthetic_pilot.report
    rows = report["rows"]
    assert type(rows) is list
    if change == "extra_key":
        report["invented_extra"] = False
    elif change == "identity":
        report["index_route_version"] = "invented-route-v2"
    elif change == "unavailable":
        report["acquisition_available"] = False
    elif change == "row_status":
        rows[0]["status"] = "refused"
    else:
        rows[0]["tag_header_validation"]["raw_header_sha256"] = "0" * 64
    synthetic_pilot.republish_report()
    with pytest.raises(adapter.SecOfflinePilotAdapterError, match=message):
        synthetic_pilot.load()
