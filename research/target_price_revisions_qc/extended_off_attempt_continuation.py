"""Pure OFF continuation drafts and exact attempt-identity source adaptation.

Nothing here reads a file, authenticates a cloud source, publishes a claim,
uploads, launches, retries, or grants native authority. The caller supplies
already-retained bounded bytes. A future effect controller must independently
bind current HEAD/source/ownership and exclusively publish the exact fresh
reservation BEFORE any compile or launch. Historical v1 three-attempt effect
controllers and evidence remain unchanged and still refuse attempt four.

The only generated native changes are the fixed OFF attempt literal and three
journal identity predicates. Native normalization changes only its two attempt
identity predicates; every clock, fill, currency, fee, pagination and missing-
observation rule is retained. Supplied bytes/hashes do not attest authenticity.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import re
from types import MappingProxyType

from . import extended_evidence as e

PREFIX = "research/target_price_revisions_qc/"
SOURCE_RELATIVE = PREFIX + "extended_off_attempt_continuation.py"
CANDIDATE = "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
PROJECT = 37650980
CONFIG_SHA256 = "19a9842cfceb695d1f8256f429745247387c89bb725ee2b8be44fe98a726322a"
CLOUD_CONFIG_SHA256 = "5790ca63661f0f54a7734565342d141cbaba7797eb8c7b1e488c7ad573b01bd0"
INPUTS = MappingProxyType({"calendar.json": "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d",
    "preparation.json": "08e1d006b9ffef3554873722d5c40ebf739ff7e6dd2c372e78069ddf6cf2808f"})
SOURCE_PINS = MappingProxyType({
    PREFIX + "extended_native.py": "22ff20694aa68638a3e10430f3b6b2c3cf4ac6538d980e7f1e5b34290753b5c2",
    PREFIX + "extended_core.py": "706ed5efdcb3999400c5349dc8b5200be1d48c4bb01cbfc7fb080608a679d5da",
    PREFIX + "extended_runtime_successor.py": "2e6bb5c82f356ee7ece4811c9d634ce57d48533d408d4b57b8aee41de062517b",
    PREFIX + "extended_compressed_store.py": "d661b5752c35b9dd04f783f5d78850f453d5f5f299874e5cf19700599df2356e",
    PREFIX + "extended_metrics.py": "a8cfa235c7a54e8f33366570400dbe1bac0a0e900597e94427e5d0c5b7470414",
    PREFIX + "extended_operations.py": "824b3f0c180f1aeb7038d8f280c44507b5c39687fcccc87c539f242d9256d167",
    PREFIX + "extended_evidence.py": "a816b1ddca5a8428f07e9029bc3a7f7db3c5e1a1f50521664992dabf556aa2d7",
    PREFIX + "extended_calendar.json": INPUTS["calendar.json"],
    PREFIX + "extended_study_freeze.json": e.FREEZE_SHA256,
    PREFIX + "extended_source_bundle_completion.json": "daaf0c33fd837b9896c99d1759e67454a9f3027d478879c5e60015af1f099934",
})
HISTORY = MappingProxyType({"record_head": "12be489416af00e266c3a47286f2cabafbf74e27",
    "off_codex_attempts_consumed": 3, "on_codex_attempts_consumed": 0,
    "observed_looks": 33, "observed_cloud_jobs": 31, "observed_local_looks": 2,
    "historical_outcome_look_count": None, "old_unmatched_dispatch_reservation_retained": True})
MAX_CONTINUATIONS = 4096  # Bounded supplied ledger size, NOT an allowance reset.
MAX_BYTES = 16 * 1024 * 1024
MAX_RESERVATION_BYTES = 65536
MAX_LEDGER_BYTES = 16 * 1024 * 1024
MAX_ATTEMPT_ID = 2**31 - 1  # Integer identity syntax, not launch permission.
_RESERVATION_KEYS = frozenset(("schema study_id candidate_id arm project_id freeze_sha256 config_sha256 input_hashes "
    "historical_anchor owner_instruction_sha256 git_head producer_source_hashes cloud_source_hashes operation_id "
    "reservation_id reserved_look_id reserved_look_sequence continuation_sequence attempt previous_reservation_sha256 "
    "previous_closure_sha256 prior_census created_utc expires_utc durable_claim_published native_permission "
    "qc_setup_complete old_effect_controllers_extended accepted_metrics strategy_accepted canonical_admission").split())
_CLOSURE_KEYS = frozenset(("schema reservation_sha256 operation_id candidate_id project_id attempt terminal compile_id "
    "backtest_id outcome_observed observed_jobs_added observed_looks_added outcome_looks_added actual_jobs_bound "
    "terminal_resolved accepted_metrics strategy_accepted canonical_admission").split())
TERMINALS = frozenset({"compile_failed", "runtime_error", "completed", "cancelled_no_job", "unresolved"})


class Refusal(ValueError):
    """Closed public-only refusal without supplied body text."""


def _fail():
    raise Refusal("bounded prospective OFF continuation refused; no native effect or automatic retry")


def _sha(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _fail()
    return hashlib.sha256(raw).hexdigest()


def _hash(value, length=64):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value) is None or set(value) == {"0"}:
        _fail()
    return value


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _integer(value, minimum=0, maximum=MAX_ATTEMPT_ID):
    if type(value) is e.JsonNumber:
        if re.fullmatch(r"0|[1-9][0-9]{0,18}", value.lexeme) is None:
            _fail()
        value = int(value.lexeme)
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _time(value):
    if type(value) is not str or len(value) > 64:
        _fail()
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail()
    if stamp.utcoffset() != timedelta(0):
        _fail()
    return stamp


def _parse(raw, maximum=MAX_RESERVATION_BYTES):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        _fail()
    try:
        return e.parse_json(raw)
    except Exception:
        _fail()


def _identity(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", value) is None:
        _fail()
    return value


def _producer_hashes(value):
    if type(value) is not dict or set(value) != set(SOURCE_PINS) | {SOURCE_RELATIVE}:
        _fail()
    for name, identity in value.items():
        _hash(identity)
        if name in SOURCE_PINS and identity != SOURCE_PINS[name]:
            _fail()
    return value


def _cloud_hashes(value):
    if type(value) is not dict or not 2 <= len(value) <= 32 or not {"main.py", "extended_config.py"} <= set(value):
        _fail()
    for name, identity in value.items():
        if type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}[.]py", name) is None:
            _fail()
        _hash(identity)
    if value["extended_config.py"] != CLOUD_CONFIG_SHA256:
        _fail()
    return value


def _reservation(raw):
    body = _parse(raw)
    _closed(body, _RESERVATION_KEYS)
    if (body["schema"] != "tpr-ext26-off-continuation-reservation-v1" or body["study_id"] != e.STUDY_ID
            or body["candidate_id"] != CANDIDATE or body["arm"] != "tpr_off" or _integer(body["project_id"]) != PROJECT
            or body["freeze_sha256"] != e.FREEZE_SHA256 or body["config_sha256"] != CONFIG_SHA256
            or e.canonical(body["input_hashes"]) != e.canonical(dict(INPUTS))
            or e.canonical(body["historical_anchor"]) != e.canonical(dict(HISTORY))):
        _fail()
    for key in ("durable_claim_published", "native_permission", "qc_setup_complete", "old_effect_controllers_extended",
                "strategy_accepted", "canonical_admission"):
        if body[key] is not False:
            _fail()
    if body["accepted_metrics"] is not None:
        _fail()
    _hash(body["owner_instruction_sha256"]); _hash(body["git_head"], 40)
    _producer_hashes(body["producer_source_hashes"]); _cloud_hashes(body["cloud_source_hashes"])
    operation = _identity(body["operation_id"])
    if not operation.startswith("TPR-EXT26-OFF-CONT-") or len(operation) > 100:
        _fail()
    sequence = _integer(body["continuation_sequence"], 1, MAX_CONTINUATIONS)
    if (_integer(body["attempt"], 4) != 3 + sequence
            or _integer(body["reserved_look_sequence"], 34) != 33 + sequence
            or body["reservation_id"] != operation + "-RESERVATION" or body["reserved_look_id"] != operation + "-LOOK"):
        _fail()
    for key in ("previous_reservation_sha256", "previous_closure_sha256"):
        if sequence == 1:
            if body[key] is not None:
                _fail()
        else:
            _hash(body[key])
    if not 0 < (_time(body["expires_utc"]) - _time(body["created_utc"])).total_seconds() <= 900:
        _fail()
    census = body["prior_census"]
    _closed(census, {"continuation_attempts_spent", "observed_jobs_added", "observed_looks_added", "outcome_looks_added", "unresolved_predecessors"})
    if _integer(census["continuation_attempts_spent"], 0, MAX_CONTINUATIONS) != sequence - 1:
        _fail()
    for key in ("observed_jobs_added", "observed_looks_added", "outcome_looks_added"):
        _integer(census[key], 0, sequence - 1)
    if (_integer(census["observed_looks_added"]) != _integer(census["observed_jobs_added"])
            or _integer(census["outcome_looks_added"]) > _integer(census["observed_jobs_added"])
            or _integer(census["unresolved_predecessors"]) != 0):
        _fail()
    return body


def close_reservation(reservation_raw, *, terminal, compile_id=None, backtest_id=None, outcome_observed=False):
    """Describe retained observations only; no terminal or custody is discovered.

    Compile failure consumes the reserved attempt, not a job/look. A returned
    job is one observed job/look even if outcome statistics were not inspected.
    An unresolved request with no job ID keeps actual-job count unknown, not
    zero; its closure cannot authorize the next continuation.
    """
    reservation = _reservation(reservation_raw)
    if type(terminal) is not str or terminal not in TERMINALS or type(outcome_observed) is not bool:
        _fail()
    if compile_id is not None:
        _identity(compile_id)
    if backtest_id is not None:
        _identity(backtest_id)
    if (terminal in {"compile_failed", "cancelled_no_job"} and (backtest_id is not None or outcome_observed)
            or terminal in {"compile_failed", "cancelled_no_job", "runtime_error", "completed"} and compile_id is None
            or terminal in {"runtime_error", "completed"} and backtest_id is None
            or outcome_observed and backtest_id is None):
        _fail()
    observed = int(backtest_id is not None)
    return e.canonical({"schema": "tpr-ext26-off-continuation-closure-v1", "reservation_sha256": _sha(reservation_raw),
        "operation_id": reservation["operation_id"], "candidate_id": CANDIDATE, "project_id": PROJECT,
        "attempt": _integer(reservation["attempt"]), "terminal": terminal, "compile_id": compile_id,
        "backtest_id": backtest_id, "outcome_observed": outcome_observed, "observed_jobs_added": observed,
        "observed_looks_added": observed, "outcome_looks_added": int(outcome_observed),
        "actual_jobs_bound": None if terminal == "unresolved" and backtest_id is None else observed,
        "terminal_resolved": terminal != "unresolved", "accepted_metrics": None,
        "strategy_accepted": False, "canonical_admission": False})


def _closure(reservation_raw, closure_raw):
    body = _parse(closure_raw)
    _closed(body, _CLOSURE_KEYS)
    expected = close_reservation(reservation_raw, **{key: body[key] for key in ("terminal", "compile_id", "backtest_id", "outcome_observed")})
    if e.canonical(body) != expected:
        _fail()
    return body


def continuation_census(prior):
    """Validate supplied complete chained history; custody completeness is external."""
    if type(prior) not in (list, tuple) or len(prior) > MAX_CONTINUATIONS:
        _fail()
    census = {"continuation_attempts_spent": 0, "observed_jobs_added": 0, "observed_looks_added": 0,
              "outcome_looks_added": 0, "unresolved_predecessors": 0}
    previous = None
    identities, jobs, total = set(), set(), 0
    for index, item in enumerate(prior, 1):
        _closed(item, {"reservation", "closure"})
        reservation_raw, closure_raw = item["reservation"], item["closure"]
        total += len(reservation_raw) + len(closure_raw) if type(reservation_raw) is bytes and type(closure_raw) is bytes else MAX_LEDGER_BYTES + 1
        if total > MAX_LEDGER_BYTES:
            _fail()
        row = _reservation(reservation_raw)
        if (_integer(row["continuation_sequence"]) != index or e.canonical(row["prior_census"]) != e.canonical(census)
                or row["operation_id"] in identities or census["unresolved_predecessors"]):
            _fail()
        if previous and (row["previous_reservation_sha256"] != _sha(previous["reservation"])
                         or row["previous_closure_sha256"] != _sha(previous["closure"])):
            _fail()
        if previous and _time(row["created_utc"]) < _time(_reservation(previous["reservation"])["created_utc"]):
            _fail()
        closure = _closure(reservation_raw, closure_raw)
        if closure["backtest_id"] is not None:
            if closure["backtest_id"] in jobs:
                _fail()
            jobs.add(closure["backtest_id"])
        identities.add(row["operation_id"])
        census["continuation_attempts_spent"] += 1
        for key in ("observed_jobs_added", "observed_looks_added", "outcome_looks_added"):
            census[key] += _integer(closure[key], 0, 1)
        census["unresolved_predecessors"] += not closure["terminal_resolved"]
        previous = item
    return census


def prepare_reservation(*, operation_id, git_head, owner_instruction_sha256, producer_source_hashes,
                        cloud_source_hashes, created_utc, expires_utc, prior=()):
    """Return a fresh draft, not a retained/durable reservation or launch permit."""
    _identity(operation_id)
    _hash(git_head, 40); _hash(owner_instruction_sha256)
    _producer_hashes(producer_source_hashes); _cloud_hashes(cloud_source_hashes)
    _time(created_utc); _time(expires_utc)
    census = continuation_census(prior)
    if census["unresolved_predecessors"] or len(prior) >= MAX_CONTINUATIONS:
        _fail()
    if any(_reservation(item["reservation"])["operation_id"] == operation_id for item in prior):
        _fail()
    if prior and _time(created_utc) < _time(_reservation(prior[-1]["reservation"])["created_utc"]):
        _fail()
    sequence = len(prior) + 1
    raw = e.canonical({"schema": "tpr-ext26-off-continuation-reservation-v1", "study_id": e.STUDY_ID,
        "candidate_id": CANDIDATE, "arm": "tpr_off", "project_id": PROJECT, "freeze_sha256": e.FREEZE_SHA256,
        "config_sha256": CONFIG_SHA256, "input_hashes": dict(INPUTS), "historical_anchor": dict(HISTORY),
        "owner_instruction_sha256": owner_instruction_sha256, "git_head": git_head,
        "producer_source_hashes": producer_source_hashes, "cloud_source_hashes": cloud_source_hashes,
        "operation_id": operation_id, "reservation_id": operation_id + "-RESERVATION", "reserved_look_id": operation_id + "-LOOK",
        "reserved_look_sequence": 33 + sequence, "continuation_sequence": sequence, "attempt": 3 + sequence,
        "previous_reservation_sha256": None if not prior else _sha(prior[-1]["reservation"]),
        "previous_closure_sha256": None if not prior else _sha(prior[-1]["closure"]), "prior_census": census,
        "created_utc": created_utc, "expires_utc": expires_utc, "durable_claim_published": False,
        "native_permission": False, "qc_setup_complete": False, "old_effect_controllers_extended": False,
        "accepted_metrics": None, "strategy_accepted": False, "canonical_admission": False})
    _reservation(raw)
    return raw


def _source(raw, relative):
    if _sha(raw) != SOURCE_PINS.get(relative):
        _fail()
    try:
        return ast.parse(raw.decode("utf-8"))
    except (UnicodeError, SyntaxError):
        _fail()


def _ast_equal(left, right):
    return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


def _replace_node(tree, function_name, before, after):
    """One exact expression change within one named function, never a string sweep."""
    expected, replacement = ast.parse(before, mode="eval").body, ast.parse(after, mode="eval").body
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == function_name
        and any(_ast_equal(child, expected) for child in ast.walk(node))]
    if len(matches) != 1:
        _fail()
    count = 0
    class Replace(ast.NodeTransformer):
        def visit(self, node):
            nonlocal count
            if _ast_equal(node, expected):
                count += 1
                return ast.copy_location(deepcopy(replacement), node)
            return super().visit(node)
    Replace().visit(matches[0])
    if count != 1:
        _fail()


def _adapt(raw, relative, attempt):
    attempt = _integer(attempt, 4)
    original = _source(raw, relative)
    tree = deepcopy(original)
    if relative == PREFIX + "extended_core.py":
        _replace_node(tree, "evidence_prefix", "not 1 <= attempt <= 3",
            "attempt != " + str(attempt) + " or candidate != " + repr(CANDIDATE))
    elif relative in {PREFIX + "extended_runtime_successor.py", PREFIX + "extended_compressed_store.py"}:
        _replace_node(tree, "__init__", "not 1 <= binding['attempt'] <= 3",
            "binding['attempt'] != " + str(attempt) + " or binding['candidate_id'] != " + repr(CANDIDATE))
    elif relative == PREFIX + "extended_native.py":
        _replace_node(tree, "_binding", "not 1 <= attempt <= 3",
            "attempt != " + str(attempt) + " or candidate_id != " + repr(CANDIDATE))
        _replace_node(tree, "normalize_orders", "_ordinal(collection['attempt'], 3, zero=False)",
                      "_ordinal(collection['attempt'], " + str(attempt) + ", zero=False)")
    else:
        _fail()
    ast.fix_missing_locations(tree)
    return (ast.unparse(tree) + "\n").encode(), tree


def prepare_off_source_bundle(*, attempt, completion_bundle_raw):
    """Render public future OFF source BEFORE freezing a reservation's hashes.

    This original safety-preserving template still needs genuine first-refusal
    diagnosis and cloud/native integration. No membership-unit or stale-mark
    remedy is guessed, no ON file/input is included, and no cloud write occurs.
    It creates neither a reservation nor a current effect permit. The supplied
    integer is only an identity, not a numeric grant of further attempts.
    """
    attempt = _integer(attempt, 4)
    relative = PREFIX + "extended_source_bundle_completion.json"
    _source_bundle_hash = _sha(completion_bundle_raw)
    if _source_bundle_hash != SOURCE_PINS[relative]:
        _fail()
    bundle = _parse(completion_bundle_raw, MAX_BYTES)
    if type(bundle) is not dict or type(bundle.get("candidates")) is not list:
        _fail()
    rows = [row for row in bundle["candidates"] if row.get("candidate_id") == CANDIDATE]
    if len(rows) != 1:
        _fail()
    row = rows[0]
    if (_integer(row.get("planned_attempt")) != 3 or _sha(row["config_raw"].encode()) != CONFIG_SHA256
            or row["input_hashes"] != dict(INPUTS) or type(row.get("files")) is not dict
            or any(name.startswith(("signal_packet", "compressed_packet")) for name in row["files"])):
        _fail()
    files = {name: text.encode() for name, text in row["files"].items()}
    for name in ("extended_core.py", "extended_runtime_successor.py", "extended_compressed_store.py"):
        files[name], _ = _adapt(files[name], PREFIX + name, attempt)
    main = ast.parse(files["main.py"].decode())
    literals = [node for node in main.body if isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "EXPECTED_ATTEMPT"]
    if len(literals) != 1 or not isinstance(literals[0].value, ast.Constant) or type(literals[0].value.value) is not int or literals[0].value.value != 3:
        _fail()
    literals[0].value = ast.copy_location(ast.Constant(attempt), literals[0].value)
    # Keep other cloud files byte-for-byte; main formatting may change but its
    # AST changes only at the exact prospective attempt literal above.
    files["main.py"] = (ast.unparse(ast.fix_missing_locations(main)) + "\n").encode()
    if any(not 0 < len(raw) <= 60000 for raw in files.values()):
        _fail()
    receipt = e.canonical({"schema": "tpr-ext26-off-continuation-source-build-v1", "study_id": e.STUDY_ID,
        "candidate_id": CANDIDATE, "attempt": attempt, "reservation_sha256": None,
        "predecessor_bundle_sha256": _source_bundle_hash, "source_hashes": {name: _sha(raw) for name, raw in files.items()},
        "config_sha256": CONFIG_SHA256, "input_hashes": dict(INPUTS), "identity_ast_changes": 4,
        "strategy_economics_changed": False, "first_refusal_repaired": False, "native_permission": False,
        "qc_setup_complete": False, "old_effect_controllers_extended": False, "accepted_metrics": None})
    return files, receipt


def build_off_sources(reservation_raw, completion_bundle_raw):
    """Rebuild exact future sources and match every already-frozen cloud hash.

    Pure source rendering is permitted before draft preparation, avoiding a
    circular source-hash dependency. A future effect controller must publish
    the exact fresh claim BEFORE uploading, compiling or launching these bytes.
    The preserved historical effect controllers are NOT extended here.
    """
    reservation = _reservation(reservation_raw)
    files, receipt_raw = prepare_off_source_bundle(attempt=_integer(reservation["attempt"], 4),
        completion_bundle_raw=completion_bundle_raw)
    if reservation["cloud_source_hashes"] != {name: _sha(raw) for name, raw in files.items()}:
        _fail()
    receipt = _parse(receipt_raw)
    receipt["reservation_sha256"] = _sha(reservation_raw)
    return files, e.canonical(receipt)


def _normalizer(native_source_raw, attempt):
    """Compile pinned pure functions; no client, private opener or transport call.

    The native module's import closure is stdlib, pure evidence/metrics and the
    collector's definitions; it imports neither config nor dispatch/operator
    state. Keep that processing-only dependency out of the template factory.
    """
    from . import extended_native as native
    adapted, tree = _adapt(native_source_raw, PREFIX + "extended_native.py", attempt)
    functions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)], type_ignores=[])
    namespace = {name: getattr(native, name) for name in (
        "e", "metrics", "collector", "NY", "UTC", "MAX_ORDERS", "PAGE_SIZE", "MAX_EVENTS", "STATUS", "EVENT_STATUS",
        "UNAVAILABLE", "NormalizedOrders", "NativeError", "datetime", "timedelta", "Fraction", "re")}
    namespace["__builtins__"] = __builtins__
    namespace["_native_dependency"] = native
    # The only executed source is the hard-pinned public predecessor's pure
    # function definitions with the two enumerated identity changes. Imported
    # predecessor namespaces are never patched; source authenticity remains a
    # separate future native-custody obligation, not a self-declared flag.
    exec(compile(ast.fix_missing_locations(functions), "<tpr-off-native-continuation>", "exec"), namespace, namespace)
    return namespace, _sha(adapted)


def process_off_native(reservation_raw, closure_raw, native_source_raw, calendar_raw, *, nav_series_raw,
                       nav_envelope_raw, order_page_envelopes, order_collection_raw,
                       expected_nav_series_sha256, expected_nav_envelope_sha256, expected_order_collection_sha256):
    """Pure processing of retained bytes; no private read or processing claim.

    Caller-side fresh bounded processing scope/custody is still required BEFORE
    supplying real private bytes. The draft reservation is not substituted for
    that scope. Outputs are observations/diagnostics, never OFF acceptance.
    """
    reservation, closure = _reservation(reservation_raw), _closure(reservation_raw, closure_raw)
    if closure["terminal"] != "completed" or closure["backtest_id"] is None:
        _fail()
    attempt = _integer(reservation["attempt"], 4)
    namespace, adapted_sha = _normalizer(native_source_raw, attempt)
    native = namespace["_native_dependency"]
    binding = {"candidate_id": CANDIDATE, "project_id": PROJECT, "backtest_id": closure["backtest_id"], "attempt": attempt}
    series, nav_census = namespace["normalize_nav"](nav_series_raw, nav_envelope_raw, calendar_raw,
        expected_series_sha256=_hash(expected_nav_series_sha256), expected_envelope_sha256=_hash(expected_nav_envelope_sha256), **binding)
    orders = namespace["normalize_orders"](order_page_envelopes, order_collection_raw, calendar_raw,
        expected_collection_sha256=_hash(expected_order_collection_sha256), **binding)
    census = e.parse_json(orders.public)
    metrics = native.metrics
    report = e.canonical({"schema": "tpr-ext26-off-continuation-native-processing-v1", "study_id": e.STUDY_ID, **binding,
        "reservation_sha256": _sha(reservation_raw), "closure_sha256": _sha(closure_raw),
        "original_native_source_sha256": _sha(native_source_raw), "adapted_native_source_sha256": adapted_sha,
        "nav_census": e.parse_json(nav_census), "order_census": census,
        "nav_metrics": metrics.nav_metrics(series, calendar_raw, expected_series_sha256=_sha(series)),
        "execution_metrics": metrics.execution_metrics(list(orders.pages), series, calendar_raw,
            expected_orders_sha256=metrics.order_pages_identity(list(orders.pages)), expected_series_sha256=_sha(series),
            expected_order_count=_integer(census["order_count"], 0, native.MAX_ORDERS)),
        "independent_source_or_compiled_job_authenticated": False, "private_journal_replay_verified": False,
        "strategy_economics_independently_replayed": False, "native_permission": False, "qc_setup_complete": False,
        "new_jobs": 0, "new_observed_looks": 0, "accepted_metrics": None, "strategy_accepted": False,
        "canonical_admission": False, "classification": "native_observations_require_source_and_accounting_audit"})
    return {"nav_series": series, "nav_census": nav_census, "order_pages": orders.pages,
        "order_observations": orders.observations, "order_census": orders.public, "report": report}
