"""Product-neutral evidence maturity labels."""
from enum import Enum


class EvidenceStatus(str, Enum):
    """How much evidence supports one claim, not an entire strategy.

    One strategy may carry different statuses for different claims. These
    labels describe research maturity only and grant no production authority.
    """

    CONFIRMED = "confirmed"
    PROMISING_UNCONFIRMED = "promising_unconfirmed"
    EXPLORATORY = "exploratory"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
