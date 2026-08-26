"""ACER data backbone: verified vendor snapshot -> canonical event dataset.

This package is reusable data plumbing for the Analyst Revisions V2 program
(`docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md`). It
was built under the archived ACER V1 plan and carries no
research authority whatsoever:

- it contains no signal definition, rating-scale mapping, threshold, or gate,
  all of which are V2 specification and implementation decisions;
- it never joins an event to a price, return, or outcome, so running it is
  not a research look and produces no `R-nnn` ledger entry; and
- it grants no execution or proposal authority, in LEAN or anywhere else.

`tests/test_acer_normalization.py` pins those boundaries by AST so they
cannot erode by accident.
"""
