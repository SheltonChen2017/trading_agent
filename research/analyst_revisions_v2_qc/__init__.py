"""QC-facing composition for Analyst Revisions V2.

This package sits outside the outcome-free ``analyst_revisions_v2`` package.
It may implement deterministic backtest arithmetic and exact in-memory
synthetic layout contracts, but it has no provider, credential, real
QuantConnect runtime transport, result, deployment, order, or trading
capability. Engine/Object Store transport is added only after the separately
reviewed production-input and one-shot evaluation gates are bound.
"""
