"""Product-neutral evidence maturity labels.

These labels are the vocabulary this project's evidence discipline is built
on, so their definitions live with them. SEP1R-001: the SEP-1 extraction moved
the enum here and shortened the docstring to "labels describe research
maturity", which left every member undefined. An undefined `CONFIRMED` is not
a neutral loss — it is what lets a finding be labelled confirmed on weaker
grounds than the label has ever meant here.

Status is attached per **claim**, never per strategy. One strategy routinely
carries two different statuses at once: the SOXX/SOXL rotation's
drawdown-reduction claim is CONFIRMED (it survived every check run against
it), while its "beats buy-and-hold on CAGR" claim is REJECTED (it failed once
realistic taxes were modelled). Labelling the strategy rather than the claim
would have to pick one, and either choice would be false.

These labels describe research maturity only. None of them grants production,
proposal, or execution authority.
"""
from enum import Enum


class EvidenceStatus(str, Enum):
    """How much evidence supports one claim. See the module docstring."""

    # passed out-of-sample + all bootstrap layers + realistic execution/tax
    CONFIRMED = "confirmed"
    # positive result, hasn't cleared every check yet
    PROMISING_UNCONFIRMED = "promising_unconfirmed"
    # pattern noticed, not yet tested rigorously
    EXPLORATORY = "exploratory"
    # failed confirmation, look-ahead correction, or tax/cost modeling
    REJECTED = "rejected"
    # data missing/stale/not yet integrated
    UNAVAILABLE = "unavailable"
