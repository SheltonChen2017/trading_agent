"""Private, selected retained-original controls for provider qualification.

The two stages authenticate metadata before selecting exact body paths. They
never fetch, publish, select a strategy population or confer historical/PIT
authority. Only the eight required21 originals and four fixed recent parents
are reparsed. The caller keeps its real native memory guard through IPC flush.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

from data.hashing import hash_payload
from research import insider_buying_pilot_sec_required21_capture_v1 as warm
from research import insider_buying_pilot_sec_consumption_chain_v1 as chain
from research import insider_buying_sec_complete_projection_adapter as recent
from research import insider_buying_sec_feed_archive_format_v3 as native
from research.insider_buying.sec_complete_submission import SecCompleteSubmissionTarget, project_sec_complete_submission

SCHEMA = "insider-pilot-provider-retained-controls-v1"
SELF_PATH = "research/insider_buying_pilot_provider_controls_v1.py"
TEST_PATH = "tests/test_insider_buying_pilot_provider_controls_v1.py"
LANE_ROOT, LANE_BRANCH = native.LANE_ROOT, native.LANE_BRANCH
WARM_ROOT = LANE_ROOT.joinpath(*warm.ARTIFACT_PARTS)
RECENT_ROOT = LANE_ROOT.parent / "insider_buying_sec_complete_16_9ab2ed0"
RECENT_POSITIONS = (0, 5, 8, 14)
RECENT_REPORT = "sec-complete-report-" + recent.FINAL_REPORT_SHA256 + ".json"
RECENT_INVENTORY_FILE_SHA256 = "32a97340632d603a9e8b01f9719d08bcbf21136464e103addd307b6a2d4cabe8"
WARM_PINS = {k: chain.CONTROL_PINS[k] for k in ("reservation.json", "plan.json", "consumed-index.json", "complete.json")}
RECENT_PINS = {"inventory.json": (None, RECENT_INVENTORY_FILE_SHA256), RECENT_REPORT: (None, recent.FINAL_REPORT_SHA256)}
MAX_CONTROL = 8 * 1024 * 1024
MAX_METADATA = 128 * 1024
MAX_BODY = 8 * 1024 * 1024
WORKER_SECONDS = 120
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CASE_KEYS = {"case_id", "cik", "accession", "form_type", "filing_date", "acceptance_digits", "source_symbol", "body_sha256"}
_CODES = frozenset({"native_refused", "fixture_root_refused", "metadata_refused", "external_pin_refused", "custody_refused", "body_refused", "symbol_refused", "metadata_changed", "cleanup_refused"})


class ProviderControlsError(ValueError):
    """Only finite own codes; private inputs never become exception text."""


def _need(ok, code):
    if not ok:
        raise ProviderControlsError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_failure(error):
    return str(error) if type(error) is ProviderControlsError and str(error) in _CODES else "native_refused"


def _authority():
    return {"source_authenticated": False, "historical_public_known_by_verified": False,
        "historical_identity_verified": False, "point_in_time_data": False, "rights_verified": False,
        "canonical_admitted": False, "full_population_complete": False, "backtesting_ready": False,
        "new_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0}


def _native(memory):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH and type(memory) is native._WorkerMemoryGuard, "native_refused")
    native._isolated(); native.batch.campaign.base._prove_isolation(); memory.check()


def _version(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_size, info.st_mtime_ns)


class _Hold:
    """Held ancestry and leaves, final content rehash beyond stat versions."""
    def __init__(self, root):
        self.root, self.chains, self.leaves = Path(root), {}, {}
        try:
            self.directory("")
        except BaseException:
            self.close(); raise

    def directory(self, name):
        _need(name in {"", "objects", "claims"}, "custody_refused")
        if name not in self.chains:
            held = native.custody._Chain(self.root, (name,) if name else ())
            self.chains[name] = held
        held = self.chains[name]; held.recheck(); info = os.fstat(held.fd)
        _need(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid(), "custody_refused")
        return held

    def read(self, relative, *, cap, pin=None):
        _need(type(relative) is str and type(cap) is int and 0 < cap <= MAX_CONTROL, "custody_refused")
        bits = relative.split("/")
        _need(len(bits) in {1, 2} and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,255}", b) for b in bits), "custody_refused")
        folder, name = ("", bits[0]) if len(bits) == 1 else bits
        held = self.directory(folder)
        if relative not in self.leaves:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=held.fd)
            try:
                info = os.fstat(fd); named = os.stat(name, dir_fd=held.fd, follow_symlinks=False)
                _need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and 0 < info.st_size <= cap
                    and _version(info) == _version(named), "custody_refused")
                self.leaves[relative] = (fd, _version(info), None)
            except BaseException:
                os.close(fd); raise
        fd, version, previous = self.leaves[relative]
        _need(version[5] <= cap, "custody_refused")
        raw = os.pread(fd, cap + 1, 0)
        _need(len(raw) == version[5] and _version(os.fstat(fd)) == version
            == _version(os.stat(name, dir_fd=held.fd, follow_symlinks=False)), "custody_refused")
        digest = _sha(raw)
        _need(previous is None or previous == digest, "custody_refused")
        self.leaves[relative] = (fd, version, digest)
        if pin is not None:
            size, expected = pin
            _need((size is None or len(raw) == size) and digest == expected, "external_pin_refused")
        return raw

    def check(self):
        for name in self.chains:
            self.directory(name)
        for relative, (_, version, digest) in tuple(self.leaves.items()):
            _need(_sha(self.read(relative, cap=version[5])) == digest, "custody_refused")

    def pins(self):
        return {str(self.root / relative): {"bytes": version[5], "sha256": digest}
            for relative, (_, version, digest) in sorted(self.leaves.items())}

    def inventory(self, leaves):
        expected = set(leaves)
        _need(set(os.listdir(self.directory("").fd)) == {p.split("/")[0] for p in expected}, "custody_refused")
        for folder in ("objects", "claims"):
            names = {p.split("/", 1)[1] for p in expected if p.startswith(folder+"/")}
            if names:
                _need(set(os.listdir(self.directory(folder).fd)) == names, "custody_refused")

    def close(self):
        primary, failed = sys.exc_info()[0] is not None, False
        for fd, _, _ in self.leaves.values():
            try: os.close(fd)
            except OSError: failed = True
        for held in reversed(tuple(self.chains.values())):
            # Existing _Chain.close stops on its first close error. These
            # are our own held descriptors; exhaust every one on failure.
            for fd in reversed(held.fds):
                try: os.close(fd)
                except OSError: failed = True
            held.fds = []
        self.leaves, self.chains = {}, {}
        _need(primary or not failed, "cleanup_refused")


def _close_holds(*holders):
    primary, failed = sys.exc_info()[0] is not None, False
    for holder in holders:
        if holder is None: continue
        try: holder.close()
        except BaseException: failed = True
    _need(primary or not failed, "cleanup_refused")


def metadata_paths():
    """Fixed initial leaves only, no body opens or path discovery."""
    return tuple([WARM_ROOT / n for n in (*WARM_PINS, "scope.lock", *(f"request-{i:03d}-result.json" for i in range(8)))]
        + [RECENT_ROOT / n for n in (*RECENT_PINS, "commit.json")])


def _target(request):
    return SecCompleteSubmissionTarget(period=request["period"], accession_number=request["accession_number"],
        form_type=request["form_type"], filing_date=request["filing_date"], issuer_cik=request["issuer_cik"].zfill(10),
        quarterly_index_sha256=request["master_decoded_sha256"], complete_submission_url=request["url"])


def _descriptor(value):
    _need(type(value) is dict and set(value) == {"relative_path", "sha256", "size_bytes"}
        and type(value["sha256"]) is str and _SHA.fullmatch(value["sha256"])
        and type(value["size_bytes"]) is int and 0 < value["size_bytes"] <= MAX_BODY
        and value["relative_path"] == "objects/" + value["sha256"] + ".bin", "metadata_refused")
    return value


def _warm_leaves(selected, *, fixture):
    top = {"scope.lock", "reservation.json", "plan.json", "contact-validated.json", "rate-origin.json", "consumed-index.json", "complete.json"}
    if not fixture: top.update({"selection-started.json", "selection-complete.json"})
    top.update(f"request-{i:03d}-{suffix}.json" for i in range(8) for suffix in ("start", "result", "headers"))
    return sorted((*top, *("claims/"+_sha(row["target"]["accession_number"].encode())+".json" for row in selected[:8]),
        *("objects/"+row["body_pin"]["sha256"]+".bin" for row in selected[:8])))


def _metadata(warm_root, recent_root, *, warm_pins, recent_pins, fixture, memory):
    wh = rh = None
    try:
        wh, rh = _Hold(warm_root), _Hold(recent_root)
        _need(wh.read("scope.lock", cap=4096) == warm.LOCK_BYTES, "metadata_refused")
        fcntl.flock(wh.leaves["scope.lock"][0], fcntl.LOCK_SH | fcntl.LOCK_NB)
        values = {name: warm._decode(wh.read(name, cap=MAX_CONTROL, pin=pin)) for name, pin in warm_pins.items()}
        plan = warm.selection.validate_selection_payload(values["plan.json"])
        complete, reservation, index = (values[n] for n in ("complete.json", "reservation.json", "consumed-index.json"))
        _need(plan["fixture_only"] is complete["fixture_only"] is fixture and complete["schema"] == warm.SCHEMA + "/complete"
            and complete["audit_id"] == warm.AUDIT_ID and complete["authority"] == warm._authority()
            and complete["planned"] == complete["started"] == len(complete["results"]) == len(plan["requests"]) == 8
            and complete["unattempted"] == 0 and complete["completed_without_refusal"] is True, "metadata_refused")
        for name, field in (("reservation.json", "reservation_sha256"), ("plan.json", "plan_sha256"), ("consumed-index.json", "index_sha256")):
            _need(complete[field] == _sha(wh.read(name, cap=MAX_CONTROL)), "metadata_refused")
        _need(reservation["authority"] == warm._authority()
            and index["plan_sha256"] == complete["plan_sha256"] and index["previous_index_sha256"] == plan["consumption_sha256"]
            and index["unknown_prior_archive_memberships_remain_unknown"] is True, "metadata_refused")
        expected_added = [row["request"]["accession_number"] for row in plan["requests"]]
        _need(len(set(expected_added)) == 8 and not set(expected_added) & set(plan["consumed_accessions"])
            and index["accessions"] == sorted((*plan["consumed_accessions"], *expected_added)), "metadata_refused")
        if not fixture:
            identity = complete["execution_identity"]
            _need(reservation["execution_identity"] == identity and identity["head"] == chain.PRODUCER_HEAD and identity["root"] == str(LANE_ROOT)
                and identity["branch"] == LANE_BRANCH and identity["clean"] is True and len(index["accessions"]) == 20052, "metadata_refused")
        selected = []
        for i, row in enumerate(plan["requests"]):
            descriptor = complete["results"][i]; request = row["request"]
            _need(set(descriptor) == {"accession_number", "claim_name", "claim_sha256", "start_name", "start_sha256", "result_name", "result_sha256"}
                and descriptor["accession_number"] == request["accession_number"]
                and descriptor["claim_name"] == _sha(request["accession_number"].encode()) + ".json"
                and descriptor["start_name"] == f"request-{i:03d}-start.json"
                and descriptor["result_name"] == f"request-{i:03d}-result.json", "metadata_refused")
            result = warm._decode(wh.read(descriptor["result_name"], cap=MAX_CONTROL, pin=(None, descriptor["result_sha256"])))
            warm._result_valid(result, row, i, descriptor["claim_sha256"], descriptor["start_sha256"])
            checked = result["inspection"]
            _need(result["code"] == "none" and result["http_status"] == 200 and result["transport_invocations"] == 1
                and checked["privacy_cleared"] is checked["structure_bound"] is True and checked["authority"] == warm._authority()
                and checked["code"] == "none" and type(checked["body_bytes"]) is int and 0 < checked["body_bytes"] <= MAX_BODY
                and _SHA.fullmatch(checked["body_sha256"]) and result["body_object"] == checked["body_sha256"] + ".bin", "metadata_refused")
            selected.append({"case_id": f"warmup-{i+1:02d}", "group": "warmup", "ordinal": i,
                "target": _target(request).to_payload(), "body_path": str(Path(warm_root)/"objects"/result["body_object"]),
                "body_pin": {"bytes": checked["body_bytes"], "sha256": checked["body_sha256"]},
                "recorded_projection": checked["projection"]})
        report_raw = rh.read(RECENT_REPORT, cap=2*1024*1024, pin=recent_pins[RECENT_REPORT])
        inventory_raw = rh.read("inventory.json", cap=128*1024, pin=recent_pins["inventory.json"])
        report = recent._canonical_object(report_raw, label="selected report")
        inventory = recent._canonical_object(inventory_raw, label="selected inventory")
        inventory_sha = hash_payload(inventory["candidates"]) if fixture else recent.INVENTORY_SHA256
        candidates = recent._inventory(inventory, inventory_sha=inventory_sha, code_sha=recent.CAPTURE_CODE_COMMIT, accessions=recent.FIXED_ACCESSIONS)
        indexes, filings = recent._report(report, inventory_sha=inventory_sha, code_sha=recent.CAPTURE_CODE_COMMIT)
        commit = recent._canonical_object(rh.read("commit.json", cap=4096), label="selected commit")
        _need(commit == {"kind": "sec-complete-commit", "report_name": RECENT_REPORT,
            "report_sha256": _sha(report_raw), "attempt_journal_sha256": report["attempt_journal"]["sha256"]}, "metadata_refused")
        for j, position in enumerate(RECENT_POSITIONS):
            candidate, filing = candidates[position], filings[position]
            _need(set(filing) == {"candidate", "status", "reason", "source_url", "index_receipt_sha256", "raw_object", "projection"}
                and filing["candidate"] == candidate and filing["status"] == "acquired_noncanonical" and filing["reason"] is None, "metadata_refused")
            matching = [v for v in indexes if v["period"] == candidate["period"]]
            _need(len(matching) == 1 and filing["index_receipt_sha256"] == matching[0]["receipt"]["receipt_sha256"], "metadata_refused")
            obj = _descriptor(filing["raw_object"])
            target = SecCompleteSubmissionTarget(period=candidate["period"], accession_number=candidate["accession_number"],
                form_type=candidate["form_type"], filing_date=candidate["filing_date"], issuer_cik=candidate["issuer_cik"],
                quarterly_index_sha256=matching[0]["receipt"]["source_sha256"], complete_submission_url=filing["source_url"])
            _need(filing["projection"]["target"] == target.to_payload()
                and filing["projection"]["raw_parent"]["sha256"] == obj["sha256"]
                and filing["projection"]["raw_parent"]["size_bytes"] == obj["size_bytes"], "metadata_refused")
            selected.append({"case_id": f"recent-{j+1:02d}", "group": "recent", "ordinal": position,
                "target": target.to_payload(), "body_path": str(Path(recent_root)/obj["relative_path"]),
                "body_pin": {"bytes": obj["size_bytes"], "sha256": obj["sha256"]}, "recorded_projection": filing["projection"]})
        warm_leaves = _warm_leaves(selected, fixture=fixture)
        _need(len(warm_leaves) == len(set(warm_leaves)) == (47 if fixture else 49), "metadata_refused")
        wh.check(); rh.check(); memory.check()
        value = {"schema": SCHEMA+"/metadata", "fixture_only": fixture, "warm_root": str(warm_root), "recent_root": str(recent_root),
            "selected": selected, "warm_readback_leaves": warm_leaves, "source_pins": {**wh.pins(), **rh.pins()},
            "warm_complete_sha256": _sha(wh.read("complete.json", cap=MAX_CONTROL)),
            "full_root_inventory_verified": False, "bodies_replayed": False, "authority": _authority()}
        _need(len(_raw(value)) <= MAX_METADATA, "metadata_refused")
        return value
    except ProviderControlsError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ProviderControlsError("metadata_refused") from None
    finally:
        _close_holds(rh, wh)


def metadata_actual(*, memory):
    _native(memory)
    return _metadata(WARM_ROOT, RECENT_ROOT, warm_pins=WARM_PINS, recent_pins=RECENT_PINS, fixture=False, memory=memory)


def _validate_metadata(value):
    _need(type(value) is dict and set(value) == {"schema", "fixture_only", "warm_root", "recent_root", "selected", "warm_readback_leaves",
        "source_pins", "warm_complete_sha256", "full_root_inventory_verified", "bodies_replayed", "authority"}
        and value["schema"] == SCHEMA+"/metadata" and type(value["fixture_only"]) is bool
        and value["authority"] == _authority() and value["full_root_inventory_verified"] is value["bodies_replayed"] is False
        and len(_raw(value)) <= MAX_METADATA, "metadata_refused")
    wr, rr = Path(value["warm_root"]), Path(value["recent_root"])
    if not value["fixture_only"]:
        _need(wr == WARM_ROOT and rr == RECENT_ROOT, "metadata_refused")
    else:
        _fixture_root(wr); _fixture_root(rr)
    selected = value["selected"]
    _need(type(selected) is list and len(selected) == 12 and len({v["body_path"] for v in selected}) == 12, "metadata_refused")
    for i, row in enumerate(selected):
        group = "warmup" if i < 8 else "recent"; ordinal = i if i < 8 else RECENT_POSITIONS[i-8]
        _need(set(row) == {"case_id", "group", "ordinal", "target", "body_path", "body_pin", "recorded_projection"}
            and row["case_id"] == group+f"-{(i+1 if i<8 else i-7):02d}" and row["group"] == group and row["ordinal"] == ordinal,
            "metadata_refused")
        SecCompleteSubmissionTarget(**row["target"])
        if not value["fixture_only"]:
            _need(row["target"]["period"] == ("2020Q4" if i<8 else "2022Q4" if i<10 else "2023Q1"), "metadata_refused")
        if i >= 8:
            _need(row["target"]["accession_number"] == recent.FIXED_ACCESSIONS[ordinal], "metadata_refused")
        pin = row["body_pin"]
        _need(type(pin) is dict and set(pin) == {"bytes", "sha256"} and type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_BODY
            and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"])
            and row["body_path"] == str((wr if i<8 else rr)/"objects"/(pin["sha256"]+".bin")), "metadata_refused")
    leaves = value["warm_readback_leaves"]
    _need(type(leaves) is list and len(leaves) == len(set(leaves)) == (47 if value["fixture_only"] else 49)
        and all(type(p) is str and re.fullmatch(r"(?:claims/[0-9a-f]{64}\.json|objects/[0-9a-f]{64}\.bin|[A-Za-z0-9][A-Za-z0-9_.-]{0,100})", p) for p in leaves), "metadata_refused")
    _need(leaves == _warm_leaves(selected, fixture=value["fixture_only"]), "metadata_refused")
    expected_metadata = {str(wr/n) for n in (*WARM_PINS,"scope.lock",*(f"request-{i:03d}-result.json" for i in range(8)))}
    expected_metadata.update(str(rr/n) for n in (*RECENT_PINS,"commit.json"))
    _need(type(value["source_pins"]) is dict and set(value["source_pins"]) == expected_metadata
        and all(type(pin) is dict and set(pin)=={"bytes","sha256"} and type(pin["bytes"]) is int and 0<pin["bytes"]<=MAX_CONTROL
            and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"]) for pin in value["source_pins"].values()), "metadata_refused")
    return value


def body_paths(metadata):
    """Private allowlist; never print these paths or case metadata publicly."""
    value = _validate_metadata(metadata)
    paths = {Path(value["warm_root"])/p for p in value["warm_readback_leaves"]}
    paths.update(Path(value["recent_root"])/p for p in (*RECENT_PINS, "commit.json"))
    paths.update(Path(v["body_path"]) for v in value["selected"])
    _need(len(paths) == (54 if value["fixture_only"] else 56), "metadata_refused")
    return tuple(sorted(paths))


def _symbol(xml):
    _need(type(xml) is bytes and 0 < len(xml) <= 4*1024*1024 and b"<!DOCTYPE" not in xml.upper() and b"<!ENTITY" not in xml.upper(), "symbol_refused")
    try: root = ET.fromstring(xml)
    except (ET.ParseError, ValueError): raise ProviderControlsError("symbol_refused") from None
    nodes = list(root.iter()); _need(len(nodes) <= 50000, "symbol_refused")
    def local(node):
        _need(type(node.tag) is str and len(node.tag) <= 512, "symbol_refused")
        return node.tag.rsplit("}", 1)[-1]
    _need(local(root) == "ownershipDocument", "symbol_refused")
    issuers = [n for n in root if local(n) == "issuer"]
    _need(len(issuers) == 1 and sum(local(n) == "issuer" for n in nodes) == 1, "symbol_refused")
    symbols = [n for n in issuers[0] if local(n) == "issuerTradingSymbol"]
    _need(sum(local(n) == "issuerTradingSymbol" for n in nodes) == len(symbols) <= 1, "symbol_refused")
    if not symbols: return None
    node = symbols[0]
    _need(not list(node) and not node.attrib and (node.tail is None or not node.tail.strip()), "symbol_refused")
    text = (node.text or "").strip()
    if not text: return None
    _need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.^/_ -]{0,63}", text) is not None, "symbol_refused")
    return text


def _case(row, projected):
    target = projected.target
    _need(target.to_payload() == row["target"], "body_refused")
    accession = target.accession_number.replace("-", "")
    _need(re.fullmatch(r"[0-9]{10}", target.issuer_cik) and re.fullmatch(r"[0-9]{18}", accession)
        and re.fullmatch(r"[0-9]{14}", projected.accepted_at_raw), "body_refused")
    return {"case_id": row["case_id"], "cik": target.issuer_cik, "accession": accession,
        "form_type": target.form_type, "filing_date": target.filing_date, "acceptance_digits": projected.accepted_at_raw,
        "source_symbol": _symbol(projected.xml_bytes), "body_sha256": _sha(projected.raw_bytes)}


def _derive(metadata, *, memory, fixture, warm_pins, recent_pins):
    current = _metadata(Path(metadata["warm_root"]), Path(metadata["recent_root"]), warm_pins=warm_pins, recent_pins=recent_pins, fixture=fixture, memory=memory)
    _need(_raw(current) == _raw(metadata), "metadata_changed")
    wh = rh = None
    try:
        wh, rh = _Hold(metadata["warm_root"]), _Hold(metadata["recent_root"])
        _need(wh.read("scope.lock", cap=4096) == warm.LOCK_BYTES, "body_refused")
        fcntl.flock(wh.leaves["scope.lock"][0], fcntl.LOCK_SH | fcntl.LOCK_NB)
        wh.inventory(metadata["warm_readback_leaves"])
        for relative in metadata["warm_readback_leaves"]:
            memory.check(); wh.read(relative, cap=MAX_CONTROL)
        checked = warm._readback(Path(metadata["warm_root"]), metadata["warm_complete_sha256"], fixture=fixture)
        _need(checked["retained_bodies"] == checked["structurally_bound_bodies"] == checked["started"] == checked["planned"] == 8
            and checked["unattempted"] == 0 and checked["completed_without_refusal"] is True and checked["authority"] == warm._authority(), "body_refused")
        cases = []
        for row in metadata["selected"]:
            memory.check(); holder = wh if row["group"] == "warmup" else rh
            name = "objects/" + row["body_pin"]["sha256"] + ".bin"
            raw = holder.read(name, cap=MAX_BODY, pin=(row["body_pin"]["bytes"], row["body_pin"]["sha256"]))
            projected = project_sec_complete_submission(SecCompleteSubmissionTarget(**row["target"]), raw)
            expected = warm._project(raw, {"period": projected.target.period, "accession_number": projected.target.accession_number,
                "form_type": projected.target.form_type, "filing_date": projected.target.filing_date, "issuer_cik": projected.target.issuer_cik,
                "master_decoded_sha256": projected.target.quarterly_index_sha256, "url": projected.target.complete_submission_url}) if row["group"] == "warmup" else projected.to_payload()
            _need(_raw(expected) == _raw(row["recorded_projection"]), "body_refused")
            cases.append(_case(row, projected))
        wh.check(); rh.check(); wh.inventory(metadata["warm_readback_leaves"]); memory.check()
        # Metadata is independently rederived again after all body work, not
        # merely trusted because its caller supplied coherent self-hashes.
        final = _metadata(Path(metadata["warm_root"]), Path(metadata["recent_root"]), warm_pins=warm_pins, recent_pins=recent_pins, fixture=fixture, memory=memory)
        _need(_raw(final) == _raw(metadata), "metadata_changed")
        return {"schema": SCHEMA+"/controls", "fixture_only": fixture, "cases": cases,
            "source_pins": {**metadata["source_pins"], **wh.pins(), **rh.pins()}, "metadata_sha256": _sha(_raw(metadata)),
            "warmup_full_readback_verified": True, "recent_selected_parent_count": 4,
            "warmup_original_privacy_rescreened": False, "recent_master_bodies_replayed": False,
            "recent_full16_replayed": False, "financial_values_interpreted": False, "authority": _authority()}
    except ProviderControlsError: raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ProviderControlsError("body_refused") from None
    finally:
        _close_holds(rh, wh)


def derive_actual(metadata, *, memory):
    _native(memory); _validate_metadata(metadata)
    _need(metadata["fixture_only"] is False, "native_refused")
    return _derive(metadata, memory=memory, fixture=False, warm_pins=WARM_PINS, recent_pins=RECENT_PINS)


def _fixture_root(root):
    path = Path(root)
    _need(path.is_absolute() and not path.is_relative_to(LANE_ROOT) and not path.is_relative_to(Path("/Volumes"))
        and path != RECENT_ROOT and path != WARM_ROOT and path.resolve() == path, "fixture_root_refused")


def metadata_invented(warm_root, recent_root, *, warm_pins, recent_pins, memory):
    _fixture_root(warm_root); _fixture_root(recent_root)
    return _metadata(warm_root, recent_root, warm_pins=warm_pins, recent_pins=recent_pins, fixture=True, memory=memory)


def derive_invented(metadata, *, warm_pins, recent_pins, memory):
    _validate_metadata(metadata); _need(metadata["fixture_only"] is True, "fixture_root_refused")
    return _derive(metadata, memory=memory, fixture=True, warm_pins=warm_pins, recent_pins=recent_pins)


def public_summary(value):
    """Literal public whitelist: case identities, symbols and paths stay private."""
    _need(type(value) is dict and set(value) == {"schema", "fixture_only", "cases", "source_pins", "metadata_sha256",
        "warmup_full_readback_verified", "recent_selected_parent_count", "warmup_original_privacy_rescreened", "recent_master_bodies_replayed",
        "recent_full16_replayed", "financial_values_interpreted", "authority"}
        and value["schema"] == SCHEMA+"/controls" and type(value["fixture_only"]) is bool and value["authority"] == _authority()
        and value["warmup_full_readback_verified"] is True and value["recent_selected_parent_count"] == 4
        and value["recent_full16_replayed"] is value["financial_values_interpreted"] is value["warmup_original_privacy_rescreened"] is value["recent_master_bodies_replayed"] is False
        and type(value["cases"]) is list and len(value["cases"]) == 12 and all(set(v) == _CASE_KEYS for v in value["cases"]), "metadata_refused")
    return {"schema": SCHEMA+"/public", "fixture_only": value["fixture_only"], "control_count": 12,
        "warmup_control_count": 8, "recent_control_count": 4, "source_pin_count": len(value["source_pins"]),
        "controls_sha256": _sha(_raw(value)), "metadata_sha256": value["metadata_sha256"],
        "missing_source_symbol_count": sum(v["source_symbol"] is None for v in value["cases"]),
        "warmup_full_readback_verified": True, "recent_full16_replayed": False,
        "warmup_original_privacy_rescreened": False, "recent_master_bodies_replayed": False,
        "financial_values_interpreted": False, "authority": _authority()}
