"""ACER data backbone: verified vendor snapshot -> canonical event dataset.

This package is data plumbing for the Analyst-Consensus ETF Rotation program
(`docs/ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md`). It carries no
research authority whatsoever:

- it contains no signal definition, rating-scale mapping, threshold, or gate,
  all of which are ACER-0 specification decisions the owner has not made;
- it never joins an event to a price, return, or outcome, so running it is
  not a research look and produces no `R-nnn` ledger entry; and
- it grants no execution or proposal authority, in LEAN or anywhere else.

`tests/test_acer_normalization.py` pins those boundaries by AST so they
cannot erode by accident.
"""
