"""Observe one explicitly supplied producer without exposing its payload.

This is a caller instrument, not a production capture entry point. Importing
or executing this module invokes no producer. The caller supplies its own
zero-argument operation and remains responsible for a justified prospective
protocol, source pins, rights, host controls, and an external process deadline.
There is no adapter default, provider dispatch, artifact reader, retry or CLI.

The observation describes only this Python invocation. A producer return is
not authenticated publication, a successful source receipt, or permission for
a later reader. In particular, this cannot reconstruct R287's lost exception
or renew that spent invocation. The opaque producer result is returned
separately; callers must never print or serialize the entire returned tuple.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, cast

from scripts.arv2_massive_capture_failure import classify_capture_failure


FailureCode = Literal[
    "credential", "unsafe_configuration", "network_request", "http_status",
    "response_schema", "persistence_publication", "unknown", "invalid_callback",
]
TerminalState = Literal["not_invoked", "producer_raised", "producer_returned"]
_CLASSIFIED_FAILURE_CODES = frozenset({
    "credential", "unsafe_configuration", "network_request", "http_status",
    "response_schema", "persistence_publication", "unknown",
})


@dataclass(frozen=True, slots=True)
class CaptureObservation:
    """Finite redacted invocation evidence, not capture/authentication evidence.

    A callback may fail before or after any provider contact. Neither this
    observer nor the finite classifier counts requests, so the count is always
    unavailable, even for a producer return. Public construction does not
    authenticate an operation; the invariant checks only keep this shape honest.
    """

    capture_invoked: bool
    producer_return_received: bool
    terminal_state: TerminalState
    failure_code: FailureCode | None
    provider_request_count: None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if (
            type(self.capture_invoked) is not bool
            or type(self.producer_return_received) is not bool
            or type(self.terminal_state) is not str
            or (self.failure_code is not None and type(self.failure_code) is not str)
        ):
            raise ValueError("capture observation shape is invalid")
        if self.terminal_state == "not_invoked":
            valid = (
                not self.capture_invoked and not self.producer_return_received
                and self.failure_code == "invalid_callback"
            )
        elif self.terminal_state == "producer_raised":
            valid = (
                self.capture_invoked and not self.producer_return_received
                and self.failure_code in _CLASSIFIED_FAILURE_CODES
            )
        elif self.terminal_state == "producer_returned":
            valid = (
                self.capture_invoked and self.producer_return_received
                and self.failure_code is None
            )
        else:
            valid = False
        if not valid:
            raise ValueError("capture observation state is inconsistent")


def observe_capture_once(producer: object) -> tuple[CaptureObservation, object | None]:
    """Invoke one supplied callable once, retaining only a finite observation.

    ``callable`` is a shallow call-surface check, not signature inspection,
    callback authentication or authorization. A callable requiring arguments
    is invoked once and its TypeError is observed as an unknown refusal.
    BaseException interruptions are terminal observations, not successful
    returns or retry directions. No result inspection or exception rendering
    occurs. The second tuple item is opaque and separate from the observation;
    ``producer_return_received`` distinguishes a genuine None return from failure.
    """
    if not callable(producer):
        return CaptureObservation(False, False, "not_invoked", "invalid_callback"), None
    try:
        returned = cast(Callable[[], object], producer)()
    except BaseException as exc:
        # A failure in diagnostic classification must not replace the original
        # finite failure observation with another exception or leak its details.
        try:
            code = classify_capture_failure(exc)
        except BaseException:
            code = "unknown"
        if type(code) is not str or code not in _CLASSIFIED_FAILURE_CODES:
            code = "unknown"
        return (
            CaptureObservation(True, False, "producer_raised", cast(FailureCode, code)),
            None,
        )
    return CaptureObservation(True, True, "producer_returned", None), returned


__all__ = ["CaptureObservation", "observe_capture_once"]
