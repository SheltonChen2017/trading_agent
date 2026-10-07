# Guidance Revision Drift - offline GDR-0A candidate

This package is research-owned and has no provider, outcome, QC, broker,
operator-database, scheduler or order integration. A formula pass is not a
point-in-time event, eligible security, trade proposal or authorization.

The first bounded implementation provides:

- the versioned proposed parameter inventory in `specs/gdr0a.draft.json`;
- a strict, duplicate-key/no-float JSON decoder, one pinned candidate identity
  and immutable canonical bytes (fresh deep projections on every read);
- source-document integrity checks against the delivered Markdown and PDF;
- a read-only readiness report that cannot accept caller-supplied approval;
- exact midpoint/cross-multiplied range arithmetic and display-only ratios;
- synthetic behavior, tamper, decimal-context and dependency-boundary tests.

Hashes establish consistency, not trust or permission. This is a draft
contract, not a general-purpose authorization framework. There is no way to
turn a gate on with a CLI flag or by putting `reviewed=true` in a payload.
Later accepted contracts require a separately reviewed implementation and
their own explicit owner/source/outcome authority.

## Commands (Python 3.12+)

Run from the dedicated worktree root:

```text
python -m research.guidance_revision_drift show-candidate
python -m research.guidance_revision_drift preflight
```

`show-candidate` exits 0 when the draft and its source files are intact.
`preflight` deliberately exits 2 and prints `status=blocked` while listing
all unresolved decisions and zero external authorities. An invalid/missing
candidate or mismatched source document exits 1. Unknown commands are refused
by the argument parser. Neither command can download, collect, simulate orders
or launch QuantConnect. A success exit for inspection is not research approval.

Input reads reject symlink/nonregular leaf files, cap candidate JSON at 64 KiB
and each planning source at 1 MiB, and recheck descriptor identity/type/size
after opening. Planning sources are read only to verify their byte hashes.

Canonical identity hashes canonical UTF-8 JSON **without** a trailing newline,
using the existing product-neutral `data.hashing` helper. Source file hashes
are byte hashes; the Markdown has a narrowly scoped LF rule for Windows.
Semantic candidate changes, unknown/missing fields and forged status values
are refused even if the caller recomputes another hash. Formatting/key order
alone does not change semantic identity.

## Focused validation

The tests use `unittest.TestCase` and remain pytest-discoverable. To run only
the offline contract, readiness and boundary checks (not a complete lane or
repository suite):

```text
python -m unittest discover -s tests/guidance_revision_drift -p test_contracts.py -v
python -m unittest discover -s tests/guidance_revision_drift -p test_readiness.py -v
python -m unittest discover -s tests/guidance_revision_drift -p test_boundaries.py -v
python -m unittest discover -s tests/guidance_revision_drift -p test_formulas.py -v
```

Do not infer research evidence from synthetic tests. Do not skip normal
operator-state isolation when running the repository's existing pytest tests;
those require the pinned application dependencies, unlike these stdlib-only
modules. The owner has not requested a complete lane/repository suite.

The active bounded scope and exact branch/worktree are recorded in
`docs/Strategy Description/GUIDANCE_REVISION_DRIFT_IMPLEMENTATION_RECORD.md`.
The original 2026-10-06 plan/PDF remain the unmodified design snapshot; current
implementation status is in the lane record, Action Plan and Session Handoff.
