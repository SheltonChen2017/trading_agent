"""Analyst Revisions V2 contract and synthetic-formula layer.

This package is intentionally separate from :mod:`research.acer`. ACER is
legacy V1 capture evidence and is never reinterpreted as a V2 event. Nothing
in this package imports prices, outcomes, backtests, brokers, proposals, or
execution code; real-outcome access remains blocked behind the reviewed
preregistration gate.
"""

CANONICAL_EVENT_SCHEMA = "arv2-canonical-event-v1"
DATASET_SCHEMA = "arv2-event-dataset-v1"
