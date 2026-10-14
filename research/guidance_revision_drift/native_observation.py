"""Bounded observations of the fixed synthetic runtime, never native proof.

This module neither loads an SDK nor obtains external data. Missing reflective
labels remain missing; Python test doubles cannot certify a .NET execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import sys

from data.financial_primitives import decimal_text, exact_decimal_multiply, exact_decimal_sum, to_decimal
from data.hashing import canonical_json
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256, _decode


class ObservationError(ValueError):
    """An observation is absent, malformed or incompatible with this fixture."""


FIXTURE_SHA256 = "8f35d56a335d3f7d9dad016e1e2236de7fcd2635e5c463c30081f97b7b944458"
CONTEXT_KEYS = frozenset({"runtime_source_sha256", "bundle_sha256", "candidate_sha256", "fixture_sha256"})
MAX_DEFERRED_EVENTS = 64
MAX_NATIVE_ID = 2_147_483_647


def _text(value, *, limit=256):
    if type(value) is not str or not value or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ObservationError("malformed bounded runtime label")
    return value


def _sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ObservationError("malformed runtime context hash")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    canonical_bytes: bytes

    def __post_init__(self):
        row = _decode(self.canonical_bytes)
        if set(row) != CONTEXT_KEYS or canonical_json(row).encode() != self.canonical_bytes:
            raise ObservationError("runtime context requires exact canonical four-key identity")
        for value in row.values():
            _sha(value)
        if row["candidate_sha256"] != CANDIDATE_SHA256 or row["fixture_sha256"] != FIXTURE_SHA256:
            raise ObservationError("runtime context differs from fixed candidate/fixture")

    @classmethod
    def capture(cls, row):
        if type(row) is not dict or set(row) != CONTEXT_KEYS:
            raise ObservationError("runtime context requires exact four-key identity")
        return cls(canonical_json(row).encode())

    def to_dict(self):
        return _decode(self.canonical_bytes)


def _get(obj, *names):
    for name in names:
        try:
            value = getattr(obj, name)
        except (AttributeError, TypeError):
            continue
        if value is not None:
            return value
    return None


def object_labels(obj):
    """Read actual Python/reflected types; do not guess an SDK version."""
    if obj is None:
        return {"python_type": None, "native_type": None, "assembly": None, "assembly_version": None}
    python_type = _text(f"{type(obj).__module__}.{type(obj).__qualname__}")
    native_type = assembly = version = None
    getter = _get(obj, "GetType")
    if callable(getter):
        try:
            native = getter()
            native_type = _text(native.FullName)
        except Exception:
            # Python proxies may not expose CLR reflection. Absence is evidence
            # of missing observation, not permission to substitute known labels.
            native_type = None
        else:
            # A missing assembly/version must not erase an observed wrong
            # native model type and turn that contradiction into "missing".
            try:
                name = native.Assembly.GetName()
                assembly = _text(name.Name)
            except Exception:
                name = None
            if name is not None:
                try:
                    version = _text(name.Version.ToString())
                except Exception:
                    version = None
    return {"python_type": python_type, "native_type": native_type,
            "assembly": assembly, "assembly_version": version}


def symbol_value(symbol):
    return _text(symbol if type(symbol) is str else _get(symbol, "value", "Value"), limit=64)


def observe_runtime(algorithm, security):
    """Read configured objects. Contradictory observed native labels refuse."""
    symbol = symbol_value(_get(security, "symbol", "Symbol"))
    if symbol != "SYN-GDR":
        raise ObservationError("native security symbol differs from fixed fixture")
    zone = _get(algorithm, "time_zone", "TimeZone")
    zone_id = _get(zone, "id", "Id")
    if zone_id is not None:
        zone_id = _text(zone_id)
        if zone_id not in {"UTC", "Etc/UTC"}:
            raise ObservationError("native timezone differs from UTC")
    rows = {"algorithm": object_labels(algorithm), "security": object_labels(security),
            "fill_model": object_labels(_get(security, "fill_model", "FillModel")),
            "fee_model": object_labels(_get(security, "fee_model", "FeeModel")),
            "settlement_model": object_labels(_get(security, "settlement_model", "SettlementModel"))}
    expected = {"fill_model": {"GuidanceReceiptFillModel", "FillModelPythonWrapper"},
                "fee_model": {"ConstantFeeModel"}, "settlement_model": {"ImmediateSettlementModel"}}
    missing = []
    for key, accepted in expected.items():
        label = rows[key]["native_type"]
        if label is not None and label.rsplit(".", 1)[-1] not in accepted:
            raise ObservationError(f"observed native {key} differs from fixed configuration")
        if label is None:
            missing.append(key + "_native_type")
    if zone_id is None:
        missing.append("timezone")
    if rows["algorithm"]["assembly_version"] is None:
        missing.append("algorithm_assembly_version")
    loaded_binding = sys.modules.get("clr") or sys.modules.get("pythonnet")
    binding_version = _get(loaded_binding, "__version__")
    if binding_version is not None:
        binding_version = _text(binding_version)
    else:
        missing.append("pythonnet_version")
    return {"schema": "gdr-native-runtime-observation-v1", "python_implementation": sys.implementation.name,
            "python_version": ".".join(str(n) for n in sys.version_info[:3]),
            "pythonnet_version": binding_version, "symbol": symbol, "timezone": zone_id,
            "objects": rows, "missing": sorted(missing), "configuration_verified": False,
            "native_binding_verified": False, "settlement_parity_verified": False,
            "empirical_readiness": False, "cloud_completion_verified": False}


def valuation_checkpoint(index, *, quantity, cash, price, nav):
    """Check actual whole-account mark/NAV without changing receipt economics."""
    if type(index) is not int or not 0 <= index < 372:
        raise ObservationError("invalid native valuation frame")
    q, c, p, n = (to_decimal(x) for x in (quantity, cash, price, nav))
    if any(len(x.as_tuple().digits) > 64 or abs(x.as_tuple().exponent) > 64 for x in (q, c, p, n)):
        raise ObservationError("native valuation decimal exceeds bound")
    if q < 0 or q != q.to_integral_value() or c < 0 or n < 0:
        raise ObservationError("malformed native account valuation observation")
    if p != Decimal("50"):
        raise ObservationError("native raw mark mismatch")
    if n != exact_decimal_sum((c, exact_decimal_multiply(q, p))):
        raise ObservationError("native whole-account NAV mismatch")
    # The accepted bridge account_checkpoint already carries q/c and time. The
    # compact valuation tuple is the additional raw mark/NAV observation only.
    return (index, decimal_text(p), decimal_text(n))


@dataclass(frozen=True, slots=True)
class ReceiptSnapshot:
    canonical_bytes: bytes

    def __post_init__(self):
        row = _decode(self.canonical_bytes)
        if set(row) != {"native_id", "event_id", "symbol", "status", "at", "quantity", "price", "fee", "currency"}:
            raise ObservationError("malformed deferred receipt fields")
        if canonical_json(row).encode() != self.canonical_bytes:
            raise ObservationError("deferred receipt requires canonical bytes")
        for key, floor in (("native_id", 1), ("event_id", 0)):
            if type(row[key]) is not int or not floor <= row[key] <= MAX_NATIVE_ID:
                raise ObservationError("malformed native receipt identity")
        if row["symbol"] != "SYN-GDR" or type(row["status"]) is not str or row["status"] not in {"submitted", "filled", "partially_filled", "cancel_pending", "canceled"}:
            raise ObservationError("unsupported native symbol/status receipt")
        if type(row["quantity"]) is not int or abs(row["quantity"]) > MAX_NATIVE_ID:
            raise ObservationError("non-whole-share native receipt")
        try:
            at = datetime.fromisoformat(row["at"])
        except (TypeError, ValueError) as exc:
            raise ObservationError("malformed native receipt clock") from exc
        if at.tzinfo != timezone.utc or at.isoformat() != row["at"]:
            raise ObservationError("native receipt requires exact UTC clock")
        price, fee = to_decimal(row["price"]), to_decimal(row["fee"])
        if any(type(row[key]) is not str or decimal_text(value) != row[key] for key, value in (("price", price), ("fee", fee))):
            raise ObservationError("native receipt requires canonical exact economics")
        if any(len(x.as_tuple().digits) > 64 or abs(x.as_tuple().exponent) > 64 for x in (price, fee)) or price < 0 or fee < 0:
            raise ObservationError("malformed native receipt economics")
        zero = row["status"] in {"submitted", "cancel_pending", "canceled"} and row["quantity"] == 0 and price == 0 and fee == 0
        if row["currency"] != "USD" and not (row["currency"] == "QCC" and zero):
            raise ObservationError("non-USD native receipt")

    @classmethod
    def capture(cls, event, *, expected_symbol, statuses):
        symbol = _get(event, "symbol")
        if symbol != expected_symbol or symbol_value(symbol) != "SYN-GDR":
            raise ObservationError("native receipt symbol mismatch")
        at = event.utc_time
        if type(at) is not datetime:
            raise ObservationError("malformed native receipt clock")
        at = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)
        quantity, price, fee = (to_decimal(x) for x in (event.fill_quantity, event.fill_price, event.order_fee.value.amount))
        if any(len(x.as_tuple().digits) > 64 or abs(x.as_tuple().exponent) > 64 for x in (quantity, price, fee)):
            raise ObservationError("native receipt decimal exceeds bound")
        if quantity != quantity.to_integral_value() or abs(quantity) > MAX_NATIVE_ID:
            raise ObservationError("non-whole-share native receipt")
        return cls(canonical_json({"native_id": event.order_id, "event_id": event.id,
            "symbol": symbol_value(symbol), "status": statuses.get(event.status, "unsupported"),
            "at": at.isoformat(), "quantity": int(quantity), "price": decimal_text(price),
            "fee": decimal_text(fee), "currency": event.order_fee.value.currency}).encode())

    def to_dict(self):
        return _decode(self.canonical_bytes)

    @property
    def identity(self):
        row = self.to_dict()
        return row["native_id"], row["event_id"]


class DeferredReceipts:
    """Bounded immutable queue; duplicate/conflicting callbacks are atomic."""
    def __init__(self):
        self._rows = []

    @property
    def snapshots(self):
        return tuple(self._rows)

    def append(self, receipt):
        if type(receipt) is not ReceiptSnapshot:
            raise ObservationError("deferred queue requires validated immutable snapshot")
        checked = ReceiptSnapshot(receipt.canonical_bytes)
        prior = next((row for row in self._rows if row.identity == checked.identity), None)
        if prior is not None:
            if prior != checked:
                raise ObservationError("conflicting deferred receipt identity")
            return
        if len(self._rows) >= MAX_DEFERRED_EVENTS:
            raise ObservationError("deferred receipt capacity exceeded")
        self._rows.append(checked)

    def discard_first(self):
        del self._rows[0]


def failure_diagnostics(stage, error, bridge, deferred, *, algorithm=None):
    """Export only bounded local identity/class labels, not exception messages."""
    if stage not in {"initialize", "on_data", "on_order_event", "fill_model", "on_end_of_algorithm"}:
        raise ObservationError("unsupported native failure stage")
    bindings = dict(bridge._bindings) if bridge is not None else {}
    pending = sorted(bridge._pending) if bridge is not None else []
    cancels = sorted(bridge._cancels) if bridge is not None else []
    if len(bindings) > 64 or len(pending) > 64 or len(cancels) > 64:
        raise ObservationError("native failure identity capacity exceeded")
    account, unavailable = {}, []
    for name in ("quantity", "immediate_cash", "raw_mark", "whole_account_nav"):
        try:
            portfolio = algorithm.portfolio
            security = algorithm._gdr_security
            value = {"quantity": lambda: portfolio[algorithm.symbol].quantity,
                     "immediate_cash": lambda: portfolio.cash, "raw_mark": lambda: security.price,
                     "whole_account_nav": lambda: portfolio.total_portfolio_value}[name]()
            parsed = to_decimal(value)
            if len(parsed.as_tuple().digits) > 64 or abs(parsed.as_tuple().exponent) > 64:
                raise ObservationError("failed observation exceeds bound")
            account[name] = decimal_text(parsed)
        except Exception:
            account[name] = None
            unavailable.append(name)
    return {"stage": stage, "error_type": _text(f"{type(error).__module__}.{type(error).__qualname__}"),
            "bindings": bindings, "pending_orders": pending, "pending_cancels": cancels,
            "deferred_receipts": [list(row.identity) for row in deferred.snapshots] if deferred is not None else [],
            "trace_head_sha256": bridge.protocol_trace()["head_sha256"] if bridge is not None else None,
            "failed_account_observation": account, "unavailable_account_observations": unavailable,
            "native_binding_verified": False, "empirical_readiness": False}


def validate_native_metadata(metadata, trace):
    """Bind supplied observation rows to the supplied transcript, not its origin.

    Hash custody/authenticated retrieval and economic replay are separate gates.
    This check cannot turn invented matching observations into native evidence.
    """
    if type(metadata) is not dict or type(trace) is not dict:
        raise ObservationError("native metadata and transcript require objects")
    body = _decode(canonical_json(metadata).encode())
    status = body.get("status")
    expected = {"status", "valuation_schema", "valuation_rows", "observations",
                "terminal" if status == "complete" else "diagnostics"}
    if status not in {"complete", "failed"} or set(body) != expected:
        raise ObservationError("native metadata requires exact complete/failed schema")
    if body["valuation_schema"] != "gdr-native-price-nav-v1" or type(body["valuation_rows"]) is not list:
        raise ObservationError("native valuation sequence schema differs")
    if type(trace.get("records")) is not list or len(trace["records"]) > 1024 or any(
            type(row) is not dict or type(row.get("kind")) is not str or type(row.get("payload")) is not dict for row in trace["records"]):
        raise ObservationError("bounded native transcript records required")
    checkpoints = [row["payload"] for row in trace["records"] if row["kind"] == "account_checkpoint"]
    rows = body["valuation_rows"]
    if len(rows) != len(checkpoints) or len(rows) > 372 or (status == "complete" and len(rows) != 372):
        raise ObservationError("native valuation/checkpoint sequence incomplete")
    for index, (row, checkpoint) in enumerate(zip(rows, checkpoints)):
        if not {"before_frame_index", "quantity", "immediate_cash"} <= set(checkpoint):
            raise ObservationError("native checkpoint fields missing")
        if (type(row) is not list or len(row) != 3 or type(row[0]) is not int or row[0] != index
                or type(checkpoint["before_frame_index"]) is not int or checkpoint["before_frame_index"] != index):
            raise ObservationError("native valuation/checkpoint order differs")
        for field in (row[1], row[2], checkpoint["quantity"], checkpoint["immediate_cash"]):
            if type(field) is not str or len(field) > 128 or decimal_text(to_decimal(field)) != field:
                raise ObservationError("native valuation requires canonical decimal text")
        if tuple(row) != valuation_checkpoint(index, quantity=checkpoint["quantity"],
                cash=checkpoint["immediate_cash"], price=row[1], nav=row[2]):
            raise ObservationError("native valuation projection differs")
    observations = body["observations"]
    if observations is None:
        if status != "failed":
            raise ObservationError("completed native observations missing")
    else:
        _validate_runtime_projection(observations)
    if status == "complete":
        terminal = body["terminal"]
        if type(terminal) is not dict or set(terminal) != {"native_quantity", "native_cash", "native_price", "native_nav"}:
            raise ObservationError("native terminal account schema differs")
        for field in terminal.values():
            if type(field) is not str or len(field) > 128 or decimal_text(to_decimal(field)) != field:
                raise ObservationError("native terminal requires canonical decimal text")
        if terminal["native_quantity"] != "0" or terminal["native_cash"] != checkpoints[-1]["immediate_cash"]:
            raise ObservationError("native terminal differs from final checkpoint")
        valuation_checkpoint(371, quantity=terminal["native_quantity"], cash=terminal["native_cash"],
                             price=terminal["native_price"], nav=terminal["native_nav"])
    else:
        diagnostic = body["diagnostics"]
        if type(diagnostic) is not dict or set(diagnostic) != {"stage", "error_type", "bindings", "pending_orders",
                "pending_cancels", "deferred_receipts", "trace_head_sha256", "failed_account_observation",
                "unavailable_account_observations", "native_binding_verified", "empirical_readiness"}:
            raise ObservationError("native failed diagnostic schema differs")
        if diagnostic["stage"] not in {"initialize", "on_data", "on_order_event", "fill_model", "on_end_of_algorithm"}:
            raise ObservationError("native failure stage differs")
        _text(diagnostic["error_type"])
        if (diagnostic["trace_head_sha256"] != trace["head_sha256"] or diagnostic["native_binding_verified"] is not False
                or diagnostic["empirical_readiness"] is not False):
            raise ObservationError("native failed diagnostic head/verification differs")
        if type(diagnostic["bindings"]) is not dict or len(diagnostic["bindings"]) > 64:
            raise ObservationError("native diagnostic bindings exceed bound")
        for order, native_id in diagnostic["bindings"].items():
            _text(order, limit=128)
            if type(native_id) is not int or not 1 <= native_id <= MAX_NATIVE_ID:
                raise ObservationError("native diagnostic binding ID differs")
        for name in ("pending_orders", "pending_cancels", "deferred_receipts"):
            value = diagnostic[name]
            if type(value) is not list or len(value) > 64:
                raise ObservationError("native diagnostic pending identities exceed bound")
            for item in value:
                if name == "deferred_receipts":
                    if type(item) is not list or len(item) != 2 or any(type(n) is not int or not 0 <= n <= MAX_NATIVE_ID for n in item) or item[0] == 0:
                        raise ObservationError("native diagnostic receipt ID differs")
                else:
                    _text(item, limit=128)
        account = diagnostic["failed_account_observation"]
        names = {"quantity", "immediate_cash", "raw_mark", "whole_account_nav"}
        if type(account) is not dict or set(account) != names:
            raise ObservationError("native failed account observation fields differ")
        unavailable = []
        for name in ("quantity", "immediate_cash", "raw_mark", "whole_account_nav"):
            value = account[name]
            if value is None:
                unavailable.append(name)
            elif type(value) is not str or len(value) > 128 or decimal_text(to_decimal(value)) != value:
                raise ObservationError("native failed account observation malformed")
        if diagnostic["unavailable_account_observations"] != unavailable:
            raise ObservationError("native failed account absence projection differs")
    return body


def _validate_runtime_projection(row):
    fields = {"schema", "python_implementation", "python_version", "pythonnet_version", "symbol", "timezone",
              "objects", "missing", "configuration_verified", "native_binding_verified", "settlement_parity_verified",
              "empirical_readiness", "cloud_completion_verified"}
    if type(row) is not dict or set(row) != fields or row["schema"] != "gdr-native-runtime-observation-v1" or row["symbol"] != "SYN-GDR":
        raise ObservationError("native runtime projection schema differs")
    for key in ("configuration_verified", "native_binding_verified", "settlement_parity_verified", "empirical_readiness", "cloud_completion_verified"):
        if row[key] is not False:
            raise ObservationError("native observations cannot assert verification")
    for key in ("python_implementation", "python_version"):
        _text(row[key])
    if row["pythonnet_version"] is not None:
        _text(row["pythonnet_version"])
    if row["timezone"] is not None and row["timezone"] not in {"UTC", "Etc/UTC"}:
        raise ObservationError("native runtime timezone differs")
    objects = row["objects"]
    if type(objects) is not dict or set(objects) != {"algorithm", "security", "fill_model", "fee_model", "settlement_model"}:
        raise ObservationError("native observed object set differs")
    missing = []
    accepted = {"fill_model": {"GuidanceReceiptFillModel", "FillModelPythonWrapper"},
                "fee_model": {"ConstantFeeModel"}, "settlement_model": {"ImmediateSettlementModel"}}
    for name, labels in objects.items():
        if type(labels) is not dict or set(labels) != {"python_type", "native_type", "assembly", "assembly_version"}:
            raise ObservationError("native observed labels differ")
        for label in labels.values():
            if label is not None:
                _text(label)
        native = labels["native_type"]
        if name in accepted:
            if native is not None and native.rsplit(".", 1)[-1] not in accepted[name]:
                raise ObservationError("native observed configured model differs")
            if native is None:
                missing.append(name + "_native_type")
    if row["timezone"] is None:
        missing.append("timezone")
    if objects["algorithm"]["assembly_version"] is None:
        missing.append("algorithm_assembly_version")
    if row["pythonnet_version"] is None:
        missing.append("pythonnet_version")
    if type(row["missing"]) is not list or row["missing"] != sorted(missing):
        raise ObservationError("native missing-label projection differs")
