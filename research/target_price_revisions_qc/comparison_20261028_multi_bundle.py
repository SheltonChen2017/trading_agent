"""Pure pinned flat source renderer for four new-study native comparison arms.

Only caller-supplied public source bytes and an explicit plain packet descriptor
are processed. No opener, private reader, claim, upload, compile or job exists.
The nine unrelated legacy cloud files remain outside this active15-file bundle;
preserving them yields24 total files. The common config module is versioned per
arm. Template closure/config/final cloud source hashes stay separate to avoid
self-referential hash cycles. Numeric attempts allocate no reservation or look.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

from . import comparison_20261028_bundle as off_bundle

PREFIX = "research/target_price_revisions_qc/"
STUDY = "TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1"
PROJECTS = frozenset((37650980, 37650453))
ARMS = {"cap_tilt_50": STUDY + "-CAP-TILT-50", "cap_tilt_100": STUDY + "-CAP-TILT-100",
    "cap_tilt_200": STUDY + "-CAP-TILT-200", "pure_tpr": STUDY + "-PURE-TPR"}
BASE_PINS = {
    "extended_core.py": "706ed5efdcb3999400c5349dc8b5200be1d48c4bb01cbfc7fb080608a679d5da",
    "cap_tilt.py": "262f568b7c0fe0b08af8a26896431465c17746bcd32e9addc568f58631e11a5c",
    "cap_observer.py": "cad8a3306f6b459bc8bf187c8fd8b8bb980c7b1dc0d85465fba11dd318b70c4d",
    "extended_construction.py": "4be72251040a0f133ee4a39245a3b0fe96285715a8510b4328b5d06c276596a6",
    "extended_loader.py": "24c752b0859a04d73306e3afddc10d45cc6d3c7b566e2ff17ef160fd90e6e10b",
    "extended_runtime_successor.py": "2e6bb5c82f356ee7ece4811c9d634ce57d48533d408d4b57b8aee41de062517b",
    "extended_algorithm_successor.py": "e0077b7992dc64515384f56687b350725d694c746a8d4523336d18aa144dd9a8",
    "comparison_20261028.py": "e9b1f513fe453fcd47408171ecbc4342a9321195405c2ce31b7591439f5f44c5",
    "comparison_20261028_algorithm.py": "27c6516b9dfd2d1e71f0ef8fbdb7c371266e36e11bd9e3089e2ce6b76d25aee0",
    "extended_calendar.json": "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d",
    "comparison_20261028_policy.json": "2cfeca1b9058f3587a6d5c98df0e6b1ed10b25cdc4398b24a3525130da6425b2"}
PINS = {PREFIX + name: digest for name, digest in BASE_PINS.items()}
PINS.update({
    PREFIX + "comparison_20261028_bundle.py": "76637ed47522b6f4eb0a8e19d0962afce5e08cd249d28348dc1204547ee71b6a",
    PREFIX + "comparison_20261028_multi_algorithm.py": "201d1fa0ffa5f2771eb245997c6c160119e9cf766300d254615bcfc76eb49e34",
    PREFIX + "comparison_20261028_events.py": "8041ed95e01103007379e4b5761d14b4f5c0425afb6e889d9e295dd6acc9965d",
    PREFIX + "comparison_20261028_signal_native.py": "6fdab16bdfe070e138b92977279dec0d03d67e6a05b1be5f9af5e9136bd96935",
    "research/target_price_revisions_development/raw_revision.py": "ea4efcd9b0e73ae0b5c166d820c51e054559a3ed610041a6eb2acc8abca36353"})
SOURCE_PATHS = tuple(PINS)
RAW_PATH = "research/target_price_revisions_development/raw_revision.py"
RAW_HELPERS = ("MAX_ROWS", "MAX_SESSIONS", "_RATING", "_SESSION", "RawRevisionError", "_fail", "_schema",
    "_signature", "_rows", "_native_id", "_ticker", "_day", "_utc", "_calendar", "_number")
RAW_IMPORTS = ("from __future__ import annotations", "from datetime import date, datetime, timezone",
    "from decimal import Decimal, InvalidOperation", "import re")
MAIN = b"import comparison_20261028_multi_algorithm as candidate\n\nclass Main(candidate.ComparisonMultiAlgorithm):\n    pass\n"


class MultiBundleRefusal(ValueError):
    """Body-free invalid source/config framing; no native authentication."""


def _fail():
    raise MultiBundleRefusal("pinned comparison multi bundle refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(body):
    try:
        return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError, RecursionError):
        _fail()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None or set(value) == {"0"}:
        _fail()
    return value


def _flat_exact(raw, *, module, name, alias, level):
    text = raw.decode("utf-8")
    matches = [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.ImportFrom)
        and node.module == module and node.level == level]
    if len(matches) != 1:
        _fail()
    node = matches[0]
    if [(item.name,item.asname) for item in node.names] != [(name,alias)]:
        _fail()
    return off_bundle._span_replace(text,node,"import " + name + (" as " + alias if alias else "")).encode("utf-8")


def _raw_helpers(raw):
    """Source-select exact pure helpers; no historical identity/action filters."""
    text = raw.decode("utf-8")
    selected = {}
    for node in ast.parse(text).body:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            name = ast.unparse(node)
            if name in RAW_IMPORTS:
                if name in selected:
                    _fail()
                selected[name] = node
        elif isinstance(node,(ast.ClassDef,ast.FunctionDef)):
            if node.name in RAW_HELPERS:
                if node.name in selected:
                    _fail()
                selected[node.name] = node
        elif isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name = node.targets[0].id
            if name in RAW_HELPERS:
                if name in selected:
                    _fail()
                selected[name] = node
    if set(selected) != set(RAW_IMPORTS + RAW_HELPERS):
        _fail()
    lines = text.splitlines(keepends=True)
    output = ['"""Exact pinned numeric/date/calendar helpers only; no identity/action policy."""\n']
    for name in RAW_IMPORTS + RAW_HELPERS:
        node = selected[name]
        output.append("".join(lines[node.lineno-1:node.end_lineno]).rstrip()+"\n\n")
    return "".join(output).encode("utf-8")


def _packet(value):
    if type(value) is not dict or set(value) != {"key","sha256","bytes","encoding","source_inventory_sha256"}:
        _fail()
    key = value["key"]
    if (type(key) is not str or not key.startswith("tpr-cmp28/inputs/") or len(key)>512
            or re.fullmatch(r"[A-Za-z0-9_./-]+",key) is None
            or any(part in ("", ".", "..") for part in key.split("/"))
            or type(value["bytes"]) is not int or not 0<value["bytes"]<=512*1024**2
            or value["encoding"] != "utf-8-json"):
        _fail()
    return {"key":key,"sha256":_hash(value["sha256"]),"bytes":value["bytes"],"encoding":"utf-8-json",
        "source_inventory_sha256":_hash(value["source_inventory_sha256"])}


def build_multi_candidate(*,public_sources,arm,operation_id,attempt,prior_attempts_looks_sha256,
        signal_packet,project_id=37650980):
    """Return fifteen flat files and a candidate report; no effects or claim."""
    if (type(public_sources) is not dict or set(public_sources)!=set(SOURCE_PATHS)
            or type(arm) is not str or arm not in ARMS
            or type(attempt) is not int or not 1<=attempt<=2**31-1
            or type(project_id) is not int or project_id not in PROJECTS
            or type(operation_id) is not str or len(operation_id)>160
            or re.fullmatch(r"TPR-CMP28-[A-Za-z0-9][A-Za-z0-9_.-]*",operation_id) is None
            or off_bundle.PINS != BASE_PINS):
        _fail()
    prior, packet = _hash(prior_attempts_looks_sha256), _packet(signal_packet)
    for path,digest in PINS.items():
        raw = public_sources[path]
        if digest is None or type(raw) is not bytes or not 0<len(raw)<=131072 or _sha(raw)!=digest:
            _fail()
    template_hashes = {path:_sha(raw) for path,raw in sorted(public_sources.items())}
    closure = _sha(_canonical({"schema":"tpr-cmp28-public-template-closure-v1","source_hashes":template_hashes}))
    try:
        files, base_raw = off_bundle.build_off_candidate(
            public_sources={PREFIX+name:public_sources[PREFIX+name] for name in BASE_PINS},
            operation_id="TPR-CMP28-OFF-IMPORT-ONLY-"+str(attempt),attempt=attempt,
            prior_attempts_looks_sha256=prior)
        base_report = json.loads(base_raw)
        config = {"schema":"tpr-cmp28-multi-native-config-v1","study_id":STUDY,"candidate_id":ARMS[arm],
            "arm":arm,"operation_id":operation_id,"attempt":attempt,"project_id":project_id,
            "policy_sha256":BASE_PINS["comparison_20261028_policy.json"],
            "calendar_sha256":base_report["calendar_sha256"],"source_template_closure_sha256":closure,
            "prior_attempts_looks_sha256":prior,"signal_packet":packet,
            "source_inputs_admitted":False,"canonical_admission":False}
        config_raw = _canonical(config); config_hash = _sha(config_raw)
        files["raw_revision.py"] = _raw_helpers(public_sources[RAW_PATH])
        files["comparison_20261028_events.py"] = _flat_exact(public_sources[PREFIX+"comparison_20261028_events.py"],
            module="research.target_price_revisions_development",name="raw_revision",alias="raw_revision",level=0)
        files["comparison_20261028_signal_native.py"] = _flat_exact(public_sources[PREFIX+"comparison_20261028_signal_native.py"],
            module=None,name="comparison_20261028_events",alias="events",level=1)
        files["comparison_20261028_multi_algorithm.py"] = off_bundle._assignment(
            public_sources[PREFIX+"comparison_20261028_multi_algorithm.py"],"EXPECTED_CONFIG_SHA256",
            "__CMP28_MULTI_CONFIG_SHA256__",repr(config_hash))
        files["comparison_20261028_config.py"] = ("CONFIG_JSON = "+repr(config_raw.decode("ascii"))+"\n").encode("ascii")
        files["main.py"] = MAIN
        if len(files)!=15:
            _fail()
        for name,raw in files.items():
            if not 0<len(raw)<=60000:
                _fail()
            tree = ast.parse(raw,filename=name)
            if any(isinstance(node,ast.ImportFrom) and (node.level or (node.module or "").startswith("research."))
                    for node in ast.walk(tree)):
                _fail()
            imports={node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
            imports|={item.name for node in ast.walk(tree) if isinstance(node,ast.Import) for item in node.names}
            if imports & {"gzip","zlib","codecs","extended_compressed_store"}:
                _fail()
            compile(tree,name,"exec")
    except (off_bundle.BundleRefusal,SyntaxError,UnicodeError,TypeError,KeyError):
        _fail()
    hashes={name:_sha(raw) for name,raw in sorted(files.items())}
    report={"schema":"tpr-cmp28-multi-bundle-candidate-v1","study_id":STUDY,"candidate_id":ARMS[arm],"arm":arm,
        "operation_id":operation_id,"attempt":attempt,"project_id":project_id,"config_sha256":config_hash,
        "policy_sha256":config["policy_sha256"],"calendar_sha256":config["calendar_sha256"],
        "source_template_closure_sha256":closure,"template_source_hashes":template_hashes,
        "cloud_source_hashes":hashes,"cloud_source_bytes":{name:len(raw) for name,raw in sorted(files.items())},
        "rendered_source_closure_sha256":_sha(_canonical(hashes)),"file_count":len(files),
        "preserved_legacy_files":9,"maximum_combined_cloud_files":24,
        "ast_changes":base_report["ast_changes"]+["raw_revision.exact_numeric_date_calendar_helpers_only",
            "comparison_events.flat_raw_revision_import","signal_native.flat_events_import","multi_algorithm.config_literal",
            "shared_comparison_config.multi_schema_literal","main.multi_subclass_only"],
        "main_class":"Main(candidate.ComparisonMultiAlgorithm)","predecessor_initialize_selected":False,
        "off_initialize_selected":False,"raw_development_identity_action_filters_shipped":False,
        "signal_packet_descriptor_sha256":_sha(_canonical(packet)),"signal_packet_encoding":"utf-8-json",
        "source_inputs_admitted":False,"native_permission":False,"qc_setup_complete":False,"reservation_sha256":None,
        "new_attempts":0,"new_observed_looks":0,"strategy_accepted":False,"canonical_admission":False,"accepted_performance":None}
    return files,_canonical(report)+b"\n"
