"""Execution exception hierarchy.

GR-1A extraction. Lives in the kernel because every kernel module raises
these; keeping them in the facade would force kernel -> facade back-imports
and a package cycle. Re-exported from ``assistant.execution_service`` so
existing callers are unaffected.
"""
from __future__ import annotations


class ProposalExecutionError(RuntimeError):
    pass


class _ProposalClaimLostError(ProposalExecutionError):
    """The worker's pre-broker claim was revoked before its next transition."""


class PolicyOverridableBlockError(ProposalExecutionError):
    """Raised instead of a plain ProposalExecutionError when EVERY
    violation on the rejected validation is override-eligible (see
    risk.execution_gate.ValidationResult.overridable_violations) -- the
    proposal is left in POLICY_OVERRIDE_AVAILABLE (not BLOCKED, which is
    terminal) so a caller can re-invoke with override_policy_violations=
    True to proceed. `overridable_violations` is always the complete
    violations list here, since a mix of overridable and non-overridable
    violations always raises the plain ProposalExecutionError instead.

    `conditions_changed` (GPT review, 2026-07-30): True only when the
    caller DID pass override_policy_violations=True, a PRIOR reviewed-
    override record existed for this proposal, and the current
    violations no longer match that prior record -- i.e. the human's
    earlier review no longer describes what would actually be overridden
    right now. False for an ordinary first-time presentation (nothing to
    compare against yet) and for a plain non-override check. Callers
    (CLI, UI) should show a distinctly different message in this case --
    "the conditions changed, review again" rather than "every violation
    is override-eligible, rerun with --override"."""

    def __init__(self, message: str, overridable_violations: list[str], conditions_changed: bool = False):
        super().__init__(message)
        self.overridable_violations = overridable_violations
        self.conditions_changed = conditions_changed
