"""Pure aggregate ambient-delisting diagnostics for the cap-selected study.

The runtime, not this helper, must capture typed native event/order states,
pre/post-parent quantities and both native clock classifications. A known
window is outside only when its independently normalized clock is outside
the inclusive 09:20--09:35 execution window. This module never derives a clock,
reads a security/order, swallows a parent exception, or changes economics.

Every event is classified exactly once as ambient, nonambient or unknown.
Any unknown observation takes priority over a known disqualifier. Ambient
requires recognized type, known phase, both clocks outside, flat before/after
and no fill, target, open/historical order or native delisting ticket. Source
identity and row/clock values are deliberately absent from aggregate output.
The earlier executed source/audits are neither imported nor retro-accepted.
"""
from __future__ import annotations

from collections.abc import Mapping


MAX_EVENTS = 10000
AUDIT_KEYS = (
    "total", "type_warning", "type_final", "type_unknown",
    "phase_warmup", "phase_evaluation", "phase_outside", "phase_unknown",
    "receipt_inside", "receipt_outside", "receipt_unknown",
    "event_inside", "event_outside", "event_unknown",
    "ambient", "nonambient", "observation_unknown",
    "held_before", "held_after", "quantity_unknown", "ever_filled", "targeted",
    "open_order", "ever_ordered", "native_ticket", "history_unknown", "ticket_unknown",
)
OBSERVATION_KEYS = (
    "type", "phase", "receipt_window", "event_window", "held_before", "held_after",
    "ever_filled", "targeted", "open_order", "ever_ordered", "native_ticket", "history_unknown",
)
_FLAGS = ("held_before", "held_after", "ever_filled", "targeted", "open_order",
          "ever_ordered", "native_ticket")
_UNKNOWN_COUNTS = ("type_unknown", "phase_unknown", "receipt_unknown", "event_unknown",
                   "quantity_unknown", "history_unknown", "ticket_unknown")
_DISQUALIFIER_COUNTS = (*_FLAGS, "receipt_inside", "event_inside")
_PARTITIONS = (
    ("type_warning", "type_final", "type_unknown"),
    ("phase_warmup", "phase_evaluation", "phase_outside", "phase_unknown"),
    ("receipt_inside", "receipt_outside", "receipt_unknown"),
    ("event_inside", "event_outside", "event_unknown"),
    ("ambient", "nonambient", "observation_unknown"),
)


class CapObserverError(ValueError):
    """A closed aggregate or explicit observation contract was refused."""


def empty_audit():
    """Return a fresh all-zero closed aggregate; no implicit state or I/O."""
    return {key: 0 for key in AUDIT_KEYS}


def _validate_counts(audit, expected_total=None):
    if not isinstance(audit, Mapping) or set(audit) != set(AUDIT_KEYS):
        raise CapObserverError("observer audit has unknown or missing fields")
    if any(type(value) is not int or not 0 <= value <= MAX_EVENTS for value in audit.values()):
        raise CapObserverError("observer counts must be bounded nonnegative integers")
    total = audit["total"]
    if expected_total is not None:
        if type(expected_total) is not int or not 0 <= expected_total <= MAX_EVENTS:
            raise CapObserverError("expected event total must be a bounded integer")
        if total != expected_total:
            raise CapObserverError("observer event total does not match native total")
    if any(value > total for value in audit.values()):
        raise CapObserverError("observer marginal count exceeds total")
    if any(sum(audit[key] for key in group) != total for group in _PARTITIONS):
        raise CapObserverError("observer event partitions do not match total")
    unknown = audit["observation_unknown"]
    if any(audit[key] > unknown for key in _UNKNOWN_COUNTS):
        raise CapObserverError("unknown observation was omitted from classification")
    disqualified = audit["nonambient"] + unknown
    if any(audit[key] > disqualified for key in _DISQUALIFIER_COUNTS):
        raise CapObserverError("known disqualifier was admitted as ambient")
    if audit["ticket_unknown"] + audit["native_ticket"] > total:
        raise CapObserverError("native ticket true and unknown counts overlap")
    ambient = audit["ambient"]
    if (ambient > audit["type_warning"] + audit["type_final"]
            or ambient > total - audit["phase_unknown"]
            or ambient > audit["receipt_outside"]
            or ambient > audit["event_outside"]
            or any(ambient > total - audit[key] for key in
                   (*_FLAGS, "quantity_unknown", "history_unknown", "ticket_unknown"))):
        raise CapObserverError("ambient marginal proof is inconsistent")


def validate_audit(audit, expected_total):
    """Validate strict counts and return whether every event is known ambient.

    Malformed/mismatched aggregates raise CapObserverError. A valid aggregate
    with a nonambient or unknown event returns False. A verified zero-event
    aggregate qualifies only when all fields are zero. Count consistency is
    not independent proof that the runtime actually observed native states.
    """
    if type(expected_total) is not int or not 0 <= expected_total <= MAX_EVENTS:
        raise CapObserverError("expected event total must be a bounded integer")
    _validate_counts(audit, expected_total)
    return audit["ambient"] == audit["total"]


def _validate_observation(observation):
    if not isinstance(observation, Mapping) or set(observation) != set(OBSERVATION_KEYS):
        raise CapObserverError("observer event has unknown or missing fields")
    domains = {
        "type": ("warning", "final", "unknown"),
        "phase": ("warmup", "evaluation", "outside", "unknown"),
        "receipt_window": ("inside", "outside", "unknown"),
        "event_window": ("inside", "outside", "unknown"),
    }
    if any(type(observation[key]) is not str or observation[key] not in domain
           for key, domain in domains.items()):
        raise CapObserverError("observer classification is not explicit")
    if any(value is not None and type(value) is not bool
           for value in (observation[key] for key in _FLAGS)):
        raise CapObserverError("observer flags must be explicit boolean or unknown")
    if type(observation["history_unknown"]) is not bool:
        raise CapObserverError("observer history flag must be explicit boolean")


def _is_unknown(observation):
    return (
        observation["type"] == "unknown"
        or observation["phase"] == "unknown"
        or observation["receipt_window"] == "unknown"
        or observation["event_window"] == "unknown"
        or any(observation[key] is None for key in _FLAGS)
        or observation["history_unknown"]
    )


def _is_ambient(observation):
    return (
        observation["type"] in ("warning", "final")
        and observation["phase"] != "unknown"
        and observation["receipt_window"] == "outside"
        and observation["event_window"] == "outside"
        and all(observation[key] is False for key in _FLAGS)
        and observation["history_unknown"] is False
    )


def record_event(audit, observation):
    """Return a new closed aggregate; never mutate caller audit or observation.

    Unknown quantities, tickets and history retain separate counters while
    observation_unknown counts their union once per event. History is unknown
    when explicitly flagged or either ever-filled/ever-ordered field is None.
    The caller must invoke its original parent regardless of observation
    errors; this pure helper has no parent handler or exception-recovery hook.
    """
    _validate_counts(audit)
    _validate_observation(observation)
    if audit["total"] == MAX_EVENTS:
        raise CapObserverError("observer event count bound reached")
    updated = dict(audit)
    updated["total"] += 1
    updated["type_" + observation["type"]] += 1
    updated["phase_" + observation["phase"]] += 1
    updated["receipt_" + observation["receipt_window"]] += 1
    updated["event_" + observation["event_window"]] += 1
    for key in _FLAGS:
        updated[key] += int(observation[key] is True)
    updated["quantity_unknown"] += int(
        observation["held_before"] is None or observation["held_after"] is None)
    updated["ticket_unknown"] += int(observation["native_ticket"] is None)
    updated["history_unknown"] += int(
        observation["history_unknown"] or observation["ever_filled"] is None
        or observation["ever_ordered"] is None)
    if _is_unknown(observation):
        category = "observation_unknown"
    elif _is_ambient(observation):
        category = "ambient"
    else:
        category = "nonambient"
    updated[category] += 1
    _validate_counts(updated)
    return updated
