"""Fixed refused-count epoch accounting, never count qualification or admission.

The private adapter is called only after the operational loader authenticates
complete original manifests, external spent claims, refusals and historical
code. All numeric and position facts are independently rebuilt from exact
typed plans/inventories, not supplied payloads, maxima or completion flags.
No successful bounded chunk is registered or accepted in this first slice.
"""
from dataclasses import dataclass, field
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_parallel_count_contract as parallel
import research.short_interest_etf.native_reported_anchor_plan as reported

ORIGINAL_COUNT = 81_875
MAXIMUM_CUMULATIVE_STARTS = 81_876
MAXIMUM_CUMULATIVE_BYTES = 4 * 1024 ** 3
PARENT_STARTED, PARENT_HTTP, PARENT_RAW = 48, 47, 47
PARENT_CHARGED_BYTES = 2_159_332
RECOVERY_STARTED, RECOVERY_HTTP, RECOVERY_RAW = 13_944, 13_944, 13_943
RECOVERY_CHARGED_BYTES = 21_293_349
FAILED_PARENT_POSITION = 47
ANCHOR_PLAN_SHA256 = "d58b2b3d006319899e6af9cd06a2fef17128c391513ea0ee99c987c483d2af3b"
EPOCH_IDS = ("original48", "refused13944", "v2zero", "v3zero")
_PROOF_PINS = (
    (("full_manifest", "f6f5baf16c0fac2ffa26f994cf82122bcef9dfa842526530797531bc5c8f55c6"),
     ("external_claim", "008e56b20a5dafa1a9f7af71dbe91e79cfc96a282cb9680a1e3488936a189d7c"),
     ("protocol", "45a554213ed8fb12ac6f334bb0b87053b0d1a899603e093bdc4bfe06daf47354"),
     ("historical_code", "52e988dfd219b378846afea7176d3a9784c1e9bd5118641f3e221b43dd1219f1")),
    (("full_manifest", "9be5d93cbc48527c1de98afa7e5b3599abfca63bdb9bdc5eef0f05d727aac4d7"),
     ("external_claim", "cdc0d80751c01189afe75a8ed59ca90bb66c76a3c5ed3871ef7d0f433d8bc398"),
     ("terminal_refusal", "b688011e116271dcfb6e3d905103b04785e752794210c69338b12c7771243ddc"),
     ("protocol", "5876de333c792b63253390bae32d3dfe58e8f760b215859ffb324afed969219b"),
     ("historical_code", "254b457da17190cba7986a21e9fff98dc415f329cee15e5fe64ace016dde022e")),
    (("external_claim", "3a7b6aaf1f59acac715c71d599a16928e5ad388c2278e3cff9ee6cf667ddb90b"),
     ("terminal_refusal", "3e8af0d070ed41ae162bfb6c1dab071299c71bcfceaa6b236ffaa3cabe2bdf39"),
     ("protocol", "b0eb4dc35db8787ef02e0ef9f6e514f81fd0eaa8855838bde2efdb47f822a2c5"),
     ("historical_code_manifest", "7d304cc9fa66d8dbb2a3f22bdc26846f46537becff43b9fbb21ee1f69c367fb0")),
    (("external_claim", "b32d9e9757a29e0edae07b87159361a83185f84513826280bef4560aef96e353"),
     ("terminal_refusal", "594f53f5b275fabc5a2784e660533d98f0f0069d30dec85855ea9251bec213dc"),
     ("protocol", "1004b9b4753be8ae3bf15b56d51feed08d0c4c1cc92ee814ee20dc6c81ab9e3f"),
     # Exact value is authenticated against the frozen claim/historical Git
     # blobs by the loader; this opaque linkage grants no numeric authority.
     ("historical_code", None)),
)
# Identity-keyed process-local provenance, not caller-supplied seal fields.
# Strong references intentionally retain the exact factory objects and their
# source-only proofs until process exit. The operational first slice creates
# four epochs and one ledger once; this is not a long-running/general registry.
# Retention also prevents id reuse from making a later object look minted.
_MINTED_EPOCHS = {}
_MINTED_LEDGERS = {}
_AUTHORITY_PROFILE = (("source_only", True), ("accounting_only", True),
    ("source_admitted", False), ("denominator_admitted", False), ("historical_PIT_admitted", False),
    ("actual_input_execution_admitted", False), ("ready_for_backtest", False),
    ("outcome_looks", 0), ("qc_attempts", 0), ("trading_authority", False))


class CountEpochLedgerRefusal(ValueError):
    pass


_CODES = frozenset("""
exact_typed_anchor_source_required fixed_original_anchor_scope_changed epoch_inventory_factory_required
sealed_epoch_inventory_changed epoch_scope_or_report_changed unregistered_epoch_refused
registered_proof_lineage_changed exact_parallel_inventory_required epoch_source_matrix_changed
epoch_original_position_mapping_changed refused_epoch_header_or_debit_types_changed
all_started_receipts_not_only_retained_required exact_started_ticket_required epoch_receipt_request_changed
epoch_position_outside_original_source exact_epoch_observation_flags_required retained_body_provenance_changed
unknown_body_not_synthetic_observation unregistered_negative_receipt_kind epoch_actual_debits_or_retained_totals_changed
zero_START_epoch_cannot_adopt_inventory duplicate_epoch_position_contribution epoch_ledger_factory_required
sealed_epoch_ledger_changed ledger_scope_or_report_changed exact_registered_epoch_roster_required
exact_sealed_epoch_inventory_required registered_epoch_order_or_source_changed overlapping_retained_epoch_contribution
immutable_historical_cumulative_ceiling_exceeded epoch_registered_plan_budget_changed
fixed_source_only_authority_required
""".split())


def failure_summary(error):
    code = None
    if type(error) is not CountEpochLedgerRefusal:
        return {"category": "unknown_local_error", "errno_name": None, "contract_code": None}
    arguments = BaseException.args.__get__(error, BaseException)
    if (type(arguments) is tuple and len(arguments) == 1 and type(arguments[0]) is str
        and len(arguments[0]) <= 256 and arguments[0].startswith("REFUSED: ")):
        candidate = arguments[0][len("REFUSED: "):]
        if candidate in _CODES: code = candidate
    return {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}


def require(value, code):
    if not value:
        raise CountEpochLedgerRefusal("REFUSED: " + code)


def authority():
    return dict(_AUTHORITY_PROFILE)


def _scope_sha256():
    profile = authority()
    require(type(profile) is dict and set(profile) == {name for name, unused in _AUTHORITY_PROFILE}
        and all(type(profile[name]) is type(value) and profile[name] == value
            for name, value in _AUTHORITY_PROFILE), "fixed_source_only_authority_required")
    return hash_payload({"original_count": ORIGINAL_COUNT, "maximum_STARTs": MAXIMUM_CUMULATIVE_STARTS,
        "maximum_bytes": MAXIMUM_CUMULATIVE_BYTES, "parent": [PARENT_STARTED, PARENT_HTTP, PARENT_RAW, PARENT_CHARGED_BYTES],
        "recovery": [RECOVERY_STARTED, RECOVERY_HTTP, RECOVERY_RAW, RECOVERY_CHARGED_BYTES],
        "failed_parent_position": FAILED_PARENT_POSITION, "anchor_plan": ANCHOR_PLAN_SHA256,
        "epoch_ids": EPOCH_IDS, "proofs": _PROOF_PINS,
        "whole_unknown_page_bytes": parallel.MAXIMUM_RESPONSE_BYTES, "authority": profile})


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _source_positions(source):
    require(type(source) is reported.NativeReportedAnchorPlan, "exact_typed_anchor_source_required")
    source._guard()
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    require(source.sha256 == ANCHOR_PLAN_SHA256 and type(selected) is list and len(selected) == ORIGINAL_COUNT
        and all(type(value) is int and value > 0 for value in selected)
        and selected == sorted(set(selected)), "fixed_original_anchor_scope_changed")
    return selected, {original: position for position, original in enumerate(selected, 1)}


@dataclass(frozen=True, slots=True, init=False, eq=False)
class CountEpochInventory:
    _parts: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise CountEpochLedgerRefusal("REFUSED: epoch_inventory_factory_required")

    def _guard(self):
        require(type(self) is CountEpochInventory, "sealed_epoch_inventory_changed")
        try:
            parts = object.__getattribute__(self, "_parts")
            identity = object.__getattribute__(self, "_identity")
        except AttributeError:
            raise CountEpochLedgerRefusal("REFUSED: sealed_epoch_inventory_changed") from None
        require(parts is identity and type(parts) is tuple and len(parts) == 11 and parts[0] is self,
            "sealed_epoch_inventory_changed")
        require(_MINTED_EPOCHS.get(id(self)) is parts, "sealed_epoch_inventory_changed")
        unused_self, source, inventory, unused_epoch, unused_proof, unused_started, unused_retained, raw, digest, scope, unused_unknown = parts
        source._guard()
        if inventory is not None: inventory.guard()
        require(scope == _scope_sha256() and type(raw) is bytes and hash_bytes(raw) == digest,
            "epoch_scope_or_report_changed")

    def private_payload(self):
        self._guard()
        return json.loads(self._parts[7])

    def public_summary(self):
        value = self.private_payload()
        return {name: value[name] for name in ("schema", "epoch_id", "epoch_status", "START_debits",
            "known_HTTP_invocations", "recorded_not_invoked_STARTs", "charged_response_bytes",
            "retained_transport_observation_positions", "unknown_body_full_page_START_debits",
            "proof_lineage_sha256", "authority")}

    @property
    def sha256(self):
        self._guard(); return self._parts[8]


def _seal_registered_epoch_inventory(source, inventory, *, epoch_id, proof_lineage):
    """Private authenticated-loader adapter; never accepts counters/positions.

    `proof_lineage` binds fixed full-manifest/claim/negative/code roots whose
    actual protected byte/custody proof is the operational loader's duty. It
    is not itself an input-admission capability or a source qualification.
    """
    selected, positions = _source_positions(source)
    require(type(epoch_id) is str and epoch_id in EPOCH_IDS, "unregistered_epoch_refused")
    index = EPOCH_IDS.index(epoch_id)
    expected = _PROOF_PINS[index]
    require(type(proof_lineage) is tuple and len(proof_lineage) == len(expected)
        and all(type(row) is tuple and len(row) == 2 and type(row[0]) is str and _digest(row[1])
            and row[0] == pin[0] and (pin[1] is None or row[1] == pin[1])
            for row, pin in zip(proof_lineage, expected)), "registered_proof_lineage_changed")
    started_positions, retained_positions, not_invoked_ordinals = [], [], []
    starts = known = charges = retained_bytes = unknown_body = 0
    receipts_sha = None
    if index < 2:
        require(type(inventory) is parallel.ParallelCountInventory, "exact_parallel_inventory_required")
        inventory.guard()
        header = inventory.to_payload()
        plan_budget = inventory._plan.to_payload()["maximum_total_response_bytes"]
        require(type(plan_budget) is int and plan_budget == (MAXIMUM_CUMULATIVE_BYTES if index == 0
            else MAXIMUM_CUMULATIVE_BYTES - PARENT_CHARGED_BYTES), "epoch_registered_plan_budget_changed")
        queries = inventory._plan._queries
        require(queries._matrix is source._matrix, "epoch_source_matrix_changed")
        query_selected = queries.to_payload()["selected_query_ordinals"]
        wanted = selected if index == 0 else [selected[position - 1]
            for position in (FAILED_PARENT_POSITION, *range(PARENT_STARTED + 1, ORIGINAL_COUNT + 1))]
        require(query_selected == wanted and (index != 0 or queries is source.query_plan),
            "epoch_original_position_mapping_changed")
        expected_counts = ((PARENT_STARTED, PARENT_HTTP, PARENT_RAW, PARENT_CHARGED_BYTES),
            (RECOVERY_STARTED, RECOVERY_HTTP, RECOVERY_RAW, RECOVERY_CHARGED_BYTES))[index]
        require(all(type(header.get(name)) is int for name in ("attempts_started", "http_invocations",
            "charged_response_bytes", "retained_raw_bytes")) and header.get("halted") is True
            and header.get("complete_frozen_request_sequence") is False,
            "refused_epoch_header_or_debit_types_changed")
        receipts = tuple(inventory.iter_receipts())
        require(len(receipts) == header["attempts_started"] == expected_counts[0],
            "all_started_receipts_not_only_retained_required")
        tickets = queries.iter_queries()
        for ordinal, receipt in enumerate(receipts, 1):
            ticket = next(tickets, None)
            require(ticket is not None and type(receipt) is dict, "exact_started_ticket_required")
            ticket = ticket.to_payload()
            require(type(receipt.get("query_ordinal")) is int and receipt["query_ordinal"] == ordinal
                and receipt.get("request_sha256") == ticket["request_sha256"], "epoch_receipt_request_changed")
            original = query_selected[ordinal - 1]
            require(original in positions, "epoch_position_outside_original_source")
            position = positions[original]
            started_positions.append(position); starts += 1
            require(type(receipt.get("http_attempted")) is bool and type(receipt.get("body_observed")) is bool,
                "exact_epoch_observation_flags_required")
            known += int(receipt["http_attempted"])
            if receipt["body_observed"]:
                size = receipt.get("raw_bytes")
                require(type(size) is int and 0 <= size <= parallel.MAXIMUM_RESPONSE_BYTES
                    and receipt.get("http_status") == 200 and receipt["http_attempted"] is True
                    and _digest(receipt.get("raw_sha256")), "retained_body_provenance_changed")
                charges += size; retained_bytes += size; retained_positions.append(position)
            else:
                require(all(receipt.get(key) is None for key in ("raw_path", "raw_sha256", "raw_bytes", "content_type")),
                    "unknown_body_not_synthetic_observation")
                require(receipt.get("code") == "material_request_refused", "unregistered_negative_receipt_kind")
                charges += parallel.MAXIMUM_RESPONSE_BYTES; unknown_body += 1
                if not receipt["http_attempted"]: not_invoked_ordinals.append(ordinal)
        require((starts, known, len(retained_positions), charges) == expected_counts
            and known == header["http_invocations"] and charges == header["charged_response_bytes"]
            and retained_bytes == header["retained_raw_bytes"], "epoch_actual_debits_or_retained_totals_changed")
        receipts_sha = hash_payload(receipts)
    else:
        require(inventory is None, "zero_START_epoch_cannot_adopt_inventory")
    require(len(set(started_positions)) == len(started_positions)
        and len(set(retained_positions)) == len(retained_positions), "duplicate_epoch_position_contribution")
    payload = {"schema": "si-count-epoch-inventory-v1", "epoch_id": epoch_id,
        "epoch_status": "authenticated_refused_spent_never_promoted", "anchor_plan_sha256": source.sha256,
        "typed_inventory_sha256": None if inventory is None else inventory.sha256,
        "query_plan_sha256": None if inventory is None else inventory._plan._queries.sha256,
        "START_debits": starts, "known_HTTP_invocations": known,
        "recorded_not_invoked_STARTs": len(not_invoked_ordinals), "recorded_HTTP_flags_complete": True,
        # All START receipts contain a recorded invocation flag. This loose
        # START-based ceiling does not assert an extra HTTP invocation or
        # uncertainty about a recorded False flag, and is not wire evidence.
        "START_based_HTTP_upper_bound": starts, "HTTP_upper_bound_is_observation": False,
        "actual_wire_HTTP_count_established": False,
        "charged_response_bytes": charges, "retained_raw_bytes": retained_bytes,
        "retained_transport_observation_positions": len(retained_positions),
        "unknown_body_full_page_START_debits": unknown_body,
        "unknown_body_full_page_charged_bytes": unknown_body * parallel.MAXIMUM_RESPONSE_BYTES,
        "started_position_provenance_sha256": hash_payload(started_positions),
        "retained_position_provenance_sha256": hash_payload(retained_positions),
        "all_started_receipts_sha256": receipts_sha, "proof_lineage": proof_lineage,
        "proof_lineage_sha256": hash_payload(proof_lineage), "positive_closed_chunk_count": 0,
        "authority": authority()}
    raw = canonical_json(payload).encode()
    value = object.__new__(CountEpochInventory)
    parts = (value, source, inventory, epoch_id, proof_lineage, tuple(started_positions),
        tuple(retained_positions), raw, hash_bytes(raw), _scope_sha256(), tuple(not_invoked_ordinals))
    object.__setattr__(value, "_parts", parts); object.__setattr__(value, "_identity", parts)
    _MINTED_EPOCHS[id(value)] = parts
    value._guard()
    return value


@dataclass(frozen=True, slots=True, init=False, eq=False)
class CountEpochLedger:
    _parts: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise CountEpochLedgerRefusal("REFUSED: epoch_ledger_factory_required")

    def _guard(self):
        require(type(self) is CountEpochLedger, "sealed_epoch_ledger_changed")
        try:
            parts = object.__getattribute__(self, "_parts")
            identity = object.__getattribute__(self, "_identity")
        except AttributeError:
            raise CountEpochLedgerRefusal("REFUSED: sealed_epoch_ledger_changed") from None
        require(parts is identity and type(parts) is tuple and len(parts) == 7 and parts[0] is self,
            "sealed_epoch_ledger_changed")
        require(_MINTED_LEDGERS.get(id(self)) is parts, "sealed_epoch_ledger_changed")
        unused_self, source, epochs, raw, digest, scope, unused_provenance = parts
        source._guard()
        for epoch in epochs: epoch._guard()
        require(scope == _scope_sha256() and hash_bytes(raw) == digest, "ledger_scope_or_report_changed")

    def private_payload(self):
        self._guard(); return json.loads(self._parts[3])

    def public_summary(self):
        value = self.private_payload()
        return {name: item for name, item in value.items() if name != "epochs"}

    @property
    def sha256(self):
        self._guard(); return self._parts[4]


def seal_registered_count_epoch_ledger(source, epochs):
    _source_positions(source)
    require(type(epochs) is tuple and len(epochs) == len(EPOCH_IDS), "exact_registered_epoch_roster_required")
    starts, retained = [], set()
    payloads = []
    for epoch, name in zip(epochs, EPOCH_IDS):
        require(type(epoch) is CountEpochInventory, "exact_sealed_epoch_inventory_required")
        epoch._guard()
        require(epoch._parts[1] is source and epoch._parts[3] == name, "registered_epoch_order_or_source_changed")
        require(not retained.intersection(epoch._parts[6]), "overlapping_retained_epoch_contribution")
        starts.extend(epoch._parts[5]); retained.update(epoch._parts[6]); payloads.append(epoch.private_payload())
    totals = {name: sum(value[name] for value in payloads) for name in ("START_debits", "known_HTTP_invocations",
        "recorded_not_invoked_STARTs", "charged_response_bytes", "retained_raw_bytes", "unknown_body_full_page_START_debits",
        "unknown_body_full_page_charged_bytes")}
    require(totals["START_debits"] <= MAXIMUM_CUMULATIVE_STARTS
        and totals["charged_response_bytes"] <= MAXIMUM_CUMULATIVE_BYTES,
        "immutable_historical_cumulative_ceiling_exceeded")
    missing, available = ORIGINAL_COUNT - len(retained), MAXIMUM_CUMULATIVE_STARTS - totals["START_debits"]
    payload = {"schema": "si-count-epoch-ledger-v1", "anchor_plan_sha256": source.sha256, **totals,
        "recorded_HTTP_flags_complete": True, "START_based_HTTP_upper_bound": totals["START_debits"],
        "HTTP_upper_bound_is_observation": False, "actual_wire_HTTP_count_established": False,
        "registered_spent_epochs": len(epochs), "positive_closed_chunk_count": 0,
        "retained_transport_observation_positions": len(retained), "missing_transport_observation_positions": missing,
        "distinct_started_positions": len(set(starts)), "repeated_position_START_debits": len(starts) - len(set(starts)),
        "maximum_historical_STARTs": MAXIMUM_CUMULATIVE_STARTS,
        "available_historical_STARTs": available, "minimum_future_STARTs_for_missing_observations": missing,
        "minimum_additional_START_allowance_lower_bound": max(0, missing - available),
        "maximum_historical_bytes": MAXIMUM_CUMULATIVE_BYTES,
        "remaining_historical_bytes": MAXIMUM_CUMULATIVE_BYTES - totals["charged_response_bytes"],
        "original_source_complete": False, "any_count_source_qualified": False,
        "epoch_inventory_sha256s": [epoch.sha256 for epoch in epochs], "epochs": payloads,
        "retained_position_union_sha256": hash_payload(sorted(retained)), "authority": authority()}
    raw = canonical_json(payload).encode()
    value = object.__new__(CountEpochLedger)
    parts = value, source, epochs, raw, hash_bytes(raw), _scope_sha256(), tuple(sorted(retained))
    object.__setattr__(value, "_parts", parts); object.__setattr__(value, "_identity", parts)
    _MINTED_LEDGERS[id(value)] = parts
    value._guard()
    return value
