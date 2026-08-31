"""Target Price Revisions research contracts.

This package is a target-owned, outcome-free namespace.  TPR-0A freezes the
algorithm and policy parent; a separately reviewed structural child must bind
the declared empirical values after TPR-1/2 and before any outcome can become
reachable.  Nothing here grants provider, research-look, QC, broker, or order
authority.
"""

# TPR-CCR5-001: tracked LF migration marker for existing Windows worktrees.

ALGORITHM_SPEC_SCHEMA = "tpr-round0a-algorithm-preregistration-v1"
STRUCTURAL_BINDING_SCHEMA = "tpr-structural-bindings-v1"
FAMILY_ID = "tpr-target-price-revision-v1"
PRIMARY_CELL_ID = "tpr-stock-primary-20d"
PRIMARY_LOOK_ID = "tpr-look-stock-primary-001"
