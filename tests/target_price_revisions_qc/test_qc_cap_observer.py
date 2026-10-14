"""Synthetic closed-schema ambient-delisting observer proofs; no native I/O."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.target_price_revisions_qc import cap_observer as o


FLAGS = ("held_before", "held_after", "ever_filled", "targeted", "open_order",
         "ever_ordered", "native_ticket")


def event(**changed):
    value = {"type": "warning", "phase": "evaluation", "receipt_window": "outside",
             "event_window": "outside", **{key: False for key in FLAGS},
             "history_unknown": False}
    value.update(changed)
    return value


def ambient_audit(total=1):
    value = o.empty_audit()
    for key in ("total", "type_warning", "phase_evaluation", "receipt_outside",
                "event_outside", "ambient"):
        value[key] = total
    return value


def test_empty_audit_is_closed_fresh_zero_and_qualifies_exact_zero():
    first, second = o.empty_audit(), o.empty_audit()
    assert first is not second
    assert first == second
    assert tuple(first) == o.AUDIT_KEYS
    assert all(type(value) is int and value == 0 for value in first.values())
    assert o.validate_audit(first, 0) is True
    first["total"] = 1
    assert second["total"] == 0
    with pytest.raises(o.CapObserverError):
        o.validate_audit(first, 1)


@pytest.mark.parametrize("kind", ["warning", "final"])
@pytest.mark.parametrize("phase", ["warmup", "evaluation", "outside"])
def test_only_known_flat_orderless_historyless_outside_event_is_ambient(kind, phase):
    result = o.record_event(o.empty_audit(), event(type=kind, phase=phase))
    assert result["total"] == result["ambient"] == 1
    assert result["type_" + kind] == result["phase_" + phase] == 1
    assert result["receipt_outside"] == result["event_outside"] == 1
    assert result["nonambient"] == result["observation_unknown"] == 0
    assert o.validate_audit(result, 1) is True


@pytest.mark.parametrize("flag", FLAGS)
def test_every_known_positive_flag_disqualifies_ambient_without_losing_flag(flag):
    result = o.record_event(o.empty_audit(), event(**{flag: True}))
    assert result[flag] == 1
    assert result["nonambient"] == result["total"] == 1
    assert result["ambient"] == result["observation_unknown"] == 0
    assert o.validate_audit(result, 1) is False


def test_full_order_history_disqualifies_even_when_no_open_order():
    result = o.record_event(o.empty_audit(), event(ever_ordered=True, open_order=False))
    assert result["ever_ordered"] == 1
    assert result["open_order"] == 0
    assert result["ambient"] == 0
    assert result["nonambient"] == 1
    assert o.validate_audit(result, 1) is False


@pytest.mark.parametrize("window", ["receipt_window", "event_window"])
def test_either_known_execution_window_disqualifies(window):
    result = o.record_event(o.empty_audit(), event(**{window: "inside"}))
    prefix = "receipt" if window == "receipt_window" else "event"
    assert result[prefix + "_inside"] == 1
    assert result["ambient"] == 0
    assert result["nonambient"] == 1
    assert result["observation_unknown"] == 0
    assert o.validate_audit(result, 1) is False


@pytest.mark.parametrize("flag", FLAGS)
def test_each_unavailable_flag_is_unknown_not_coerced_false(flag):
    result = o.record_event(o.empty_audit(), event(**{flag: None}))
    assert result[flag] == 0
    assert result["observation_unknown"] == result["total"] == 1
    assert result["ambient"] == result["nonambient"] == 0
    assert result["quantity_unknown"] == int(flag in ("held_before", "held_after"))
    assert result["history_unknown"] == int(flag in ("ever_filled", "ever_ordered"))
    assert result["ticket_unknown"] == int(flag == "native_ticket")
    assert o.validate_audit(result, 1) is False


@pytest.mark.parametrize("key,prefix", [("type", "type"), ("phase", "phase"),
    ("receipt_window", "receipt"), ("event_window", "event")])
def test_unknown_classification_is_explicit_once_per_event(key, prefix):
    result = o.record_event(o.empty_audit(), event(**{key: "unknown"}))
    assert result[prefix + "_unknown"] == 1
    assert result["observation_unknown"] == 1
    assert result["ambient"] == result["nonambient"] == 0
    assert o.validate_audit(result, 1) is False


def test_many_unknowns_and_known_disqualifiers_preserve_overlaps_not_event_duplicates():
    result = o.record_event(o.empty_audit(), event(type="unknown", phase="unknown",
        receipt_window="unknown", event_window="unknown", held_before=None, held_after=None,
        ever_filled=None, ever_ordered=None, native_ticket=None, targeted=True, open_order=True,
        history_unknown=True))
    assert result["total"] == result["observation_unknown"] == 1
    assert result["ambient"] == result["nonambient"] == 0
    assert result["targeted"] == result["open_order"] == 1
    assert result["quantity_unknown"] == result["ticket_unknown"] == result["history_unknown"] == 1
    assert sum(result[key] for key in ("ambient", "nonambient", "observation_unknown")) == 1
    assert o.validate_audit(result, 1) is False


def test_unknown_priority_over_known_positive_flag():
    result = o.record_event(o.empty_audit(), event(targeted=None, held_before=True))
    assert result["held_before"] == 1
    assert result["observation_unknown"] == 1
    assert result["nonambient"] == result["ambient"] == 0
    assert o.validate_audit(result, 1) is False


def test_persistent_unknown_fill_history_stays_unknown_even_when_current_flags_false():
    result = o.record_event(o.empty_audit(), event(history_unknown=True))
    assert result["history_unknown"] == 1
    assert result["observation_unknown"] == 1
    assert result["ambient"] == result["nonambient"] == 0
    assert o.validate_audit(result, 1) is False


def test_history_flag_and_known_ever_filled_can_overlap():
    result = o.record_event(o.empty_audit(), event(history_unknown=True, ever_filled=True))
    assert result["ever_filled"] == result["history_unknown"] == result["observation_unknown"] == 1
    assert o.validate_audit(result, 1) is False


def test_cumulative_partitions_validate_and_caller_inputs_are_not_mutated():
    original = o.empty_audit()
    observations = [event(), event(type="final", held_after=True), event(targeted=None)]
    before = deepcopy((original, observations))
    result = original
    for observation in observations:
        result = o.record_event(result, observation)
    assert (original, observations) == before
    assert result["total"] == 3
    assert result["ambient"] == result["nonambient"] == result["observation_unknown"] == 1
    assert result["type_warning"] == 2 and result["type_final"] == 1
    assert o.validate_audit(result, 3) is False


@pytest.mark.parametrize("value", [True, False, None, -1, 10001, 1.0, "1"])
def test_expected_total_requires_exact_bounded_integer(value):
    with pytest.raises(o.CapObserverError):
        o.validate_audit(o.empty_audit(), value)


def test_observed_count_must_match_independent_native_delisting_total():
    with pytest.raises(o.CapObserverError):
        o.validate_audit(ambient_audit(), 2)


@pytest.mark.parametrize("value", [True, False, None, -1, 10001, 1.0, "1"])
def test_each_aggregate_count_is_strict_int_not_boolean(value):
    for key in o.AUDIT_KEYS:
        audit = ambient_audit()
        audit[key] = value
        with pytest.raises(o.CapObserverError):
            o.validate_audit(audit, 1)


@pytest.mark.parametrize("key", ["type_warning", "phase_evaluation", "receipt_outside",
                                    "event_outside", "ambient"])
def test_every_event_partition_is_required(key):
    audit = ambient_audit()
    audit[key] = 0
    with pytest.raises(o.CapObserverError):
        o.validate_audit(audit, 1)


@pytest.mark.parametrize("key", ["held_before", "held_after", "ever_filled", "targeted",
    "open_order", "ever_ordered", "native_ticket", "quantity_unknown", "history_unknown",
    "ticket_unknown"])
def test_ambient_aggregate_cannot_hide_disqualifying_or_unknown_marginal(key):
    audit = ambient_audit()
    audit[key] = 1
    with pytest.raises(o.CapObserverError):
        o.validate_audit(audit, 1)


def test_native_ticket_true_and_unknown_counts_cannot_overlap():
    audit = o.record_event(o.empty_audit(), event(native_ticket=None))
    audit["native_ticket"] = 1
    with pytest.raises(o.CapObserverError):
        o.validate_audit(audit, 1)


def test_closed_audit_and_event_schema_cannot_carry_identifiers_or_clock_rows():
    for key in ("security_id", "ticker", "event_utc", "rows", "unknown_total"):
        audit = ambient_audit()
        audit[key] = "PRIVATE-ROW"
        with pytest.raises(o.CapObserverError, match="unknown or missing") as error:
            o.validate_audit(audit, 1)
        assert "PRIVATE-ROW" not in str(error.value)
        observation = event(**{key: "PRIVATE-ROW"})
        with pytest.raises(o.CapObserverError, match="unknown or missing"):
            o.record_event(o.empty_audit(), observation)
    for key in o.OBSERVATION_KEYS:
        observation = event()
        del observation[key]
        with pytest.raises(o.CapObserverError):
            o.record_event(o.empty_audit(), observation)
    for key in o.AUDIT_KEYS:
        audit = ambient_audit()
        del audit[key]
        with pytest.raises(o.CapObserverError):
            o.validate_audit(audit, 1)


@pytest.mark.parametrize("value", [0, 1, "false", [], {}, datetime(2025, 1, 1, tzinfo=timezone.utc)])
def test_observation_flags_are_not_coerced(value):
    for key in FLAGS:
        with pytest.raises(o.CapObserverError):
            o.record_event(o.empty_audit(), event(**{key: value}))
    with pytest.raises(o.CapObserverError):
        o.record_event(o.empty_audit(), event(history_unknown=value))


def test_history_unknown_flag_cannot_be_none():
    with pytest.raises(o.CapObserverError):
        o.record_event(o.empty_audit(), event(history_unknown=None))


@pytest.mark.parametrize("key", ["type", "phase", "receipt_window", "event_window"])
@pytest.mark.parametrize("value", [None, True, 0, "OUTSIDE", "", [], {}])
def test_clock_and_enum_classifications_are_closed_explicit_strings(key, value):
    with pytest.raises(o.CapObserverError):
        o.record_event(o.empty_audit(), event(**{key: value}))


def test_maximum_count_is_accepted_but_increment_refused_without_overflow():
    audit = ambient_audit(10000)
    assert o.validate_audit(audit, 10000) is True
    before = deepcopy(audit)
    with pytest.raises(o.CapObserverError, match="count bound"):
        o.record_event(audit, event())
    assert audit == before


def test_invalid_prior_audit_is_refused_instead_of_repaired_during_recording():
    audit = ambient_audit()
    audit["open_order"] = 1
    with pytest.raises(o.CapObserverError):
        o.record_event(audit, event())


def test_pure_module_import_boundary_has_no_lean_provider_runtime_or_file_reads():
    source = Path(o.__file__).read_text()
    tree = ast.parse(source)
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    assert imports == {"__future__", "collections.abc"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in {"open", "eval", "exec", "__import__"}
                   for node in ast.walk(tree))
