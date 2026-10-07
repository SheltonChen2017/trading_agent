# Guidance Revision Drift — offline engineering candidate

GDR-0A plus ENG-1 through ENG-6 are implemented for independent review. This
is **invented-data software**, not a completed research study or deployable
QuantConnect strategy. Original GDR-0 review/freeze and GDR-1..GDR-6 research,
data, cloud and operating gates remain closed. The original plan/PDF and
proposed parameter hash are unchanged.

The package imports only the Python standard library, its own modules and the
unchanged product-neutral `data.hashing` / `data.financial_primitives` helpers.
It has no provider, outcome-fetch, SDK, broker, operator-database, scheduler or
live-assistant integration. No other lane's budget or permissions are inherited.

## Implemented surfaces

| Increment | Modules | Bounded behavior |
|---|---|---|
| GDR-0A | `contracts`, `formulas`, `readiness` | Pinned unreviewed proposal/source hashes, strict JSON, exact range arithmetic, always-blocked external readiness |
| ENG-1/2 | `events`, `archive` | Synthetic normalized guidance, immutable version/receipt chain, immediate same-FY comparable predecessor, bootstrap/edit/conflict/correction/withdrawal replay and risk invalidation |
| ENG-3 | `timing`, `universe`, `assessment` | Explicit schedule identity, prior-session 18:00 New York cutoff, D+3 through E+2 opportunities, 20-session history, dated mapping/listing eligibility and exact ranking |
| ENG-4 | `simulation` | Incremental orders, quote-side fills, partial-fill capacity, fees, cash reservations, cancellation acknowledgment/races, settlement, stops, time exits, trims and bounded corporate actions |
| ENG-5 | `qc_adapter` | Strict paired raw quote/trade snapshots mapped into the local order engine; no LEAN deployment or SDK bridge |
| ENG-6 | `controls`, `artifacts`, `comparison`, `reporting`, `fixtures`, `scenario` | Separate base/stress lineage, local content-addressed reports, matched synthetic SYN-SPY tranches, complete paired NAV diagnostics and built-in end-to-end run |

Positive entries require a predecessor captured before publication. Later
comparable cuts reduce risk when known even if the original raise was received
late. Metadata edits do not create fresh events; conflicts quarantine issuers;
corrections/withdrawals conservatively invalidate affected candidates. Evidence
publication must precede the cutoff strictly; receipt/ingestion may equal it.
Known future reference/bar versions are sliced out before selection. The
assessment cannot skip an earlier eligible opportunity to choose a later price.

Orders use exact money, explicit synthetic settlement sessions and next-data
execution. A cancel request keeps cash reserved until an explicit terminal
acknowledgment. A higher-priority risk exit can amend a carried partial trim's
remaining size, preserving prior fills and cumulative order fees. Missing
historical valuations/calendar observations remain completion blockers after
liquidation. New positions require fresh quotes for existing holdings.

The matched comparator is also order-based: one entry order per actual source
fill, then tranche exits sized by the actual strategy exit fraction. It keeps
idle cash, fees, receivables, whole-share residuals and permanent timing,
funding, underfill and excess-rounding mismatch flags. These are local modeled
fills, not verified SPY/QC executions. Reporting requires the explicit expected
calendar and retains missing NAV values; it does not provide a confidence
interval, power test, alpha claim or promotion decision.

## Commands (Python 3.12+)

Run only from the dedicated worktree root:

```text
python -B -m research.guidance_revision_drift show-candidate
python -B -m research.guidance_revision_drift preflight
python -B -m research.guidance_revision_drift adapter-manifest
python -B -m research.guidance_revision_drift synthetic-demo
python -B -m research.guidance_revision_drift synthetic-demo --output-dir /absolute/existing/owned-directory
```

The demo uses only its built-in invented 2025 corpus and explicit 93-session
schedule. It accepts no external input file. Base and stress each simulate an
entry, 20-session-interval exit, settlement and the entire paired daily NAV
calendar. The schedule is a test fixture, **not an audited NYSE calendar**.

`show-candidate`, `adapter-manifest` and a successful demo exit 0, which means
only that the local command completed. `preflight` deliberately exits 2 with
`status=blocked`. Invalid/missing candidate or source files exit 1, as does a
failed demo/export. Unsupported commands/flags exit 2. No command downloads,
captures data, launches QC or accesses an account. All commands verify the
original candidate and planning source hashes first.

Without `--output-dir`, the demo prints JSON and writes no report file. With
the flag, the directory must already exist and be owner-controlled. The command
prints a receipt for a `<SHA-256>.json` report, never overwrites differing
content, and is idempotent for identical bytes. Publication uses a flushed
private staging file and atomic no-overwrite hard link. Process interruption
cannot publish partial content; power-loss durability is **not** guaranteed
(directory fsync is not implemented). This is logical content-addressed
immutability and tamper detection, not an authorization registry, anti-rollback
root or adversarial-directory security boundary.

## Integrity and limits

Canonical identity hashes UTF-8 JSON without a trailing newline. Source hashes
cover bytes, with a narrowly scoped LF rule for the original Markdown. Strict
decoders reject duplicate keys, floats, nonfinite numbers, unknown contract
fields and forged authority. Candidate JSON/local artifacts are limited to
64 KiB; planning sources to 1 MiB. Regular-file readers refuse symlink/nonregular
leaves and recheck descriptor identity/type/size. The in-memory event archive
allows 256 observations / 8 MiB; archives larger than 64 KiB cannot use this
small report publisher.

Fixture epochs bind actual code-file bytes, candidate, corpus and schedule.
Start/terminal base/stress receipts are separate and hash-linked. The ledger
is a bounded immutable value exported with a report, not a crash-recoverable
global research-look registry. It always records zero empirical looks/QC
attempts. New source/code hashes mean a new fixture epoch, not permission to
observe outcomes. There is no caller-supplied approval/PIT override.

Unsupported: real vendor payload normalization/PIT audit; source and QC
processing rights; audited historical identifier/calendar/terminal coverage;
fractional split cash-in-lieu and noncash mergers; comparator corporate
actions; production restart/reconciliation; LEAN/QC compilation or completion;
statistical allocation/power/confirmation; paper/live operation. Supported
synthetic corporate actions are whole-share splits, explicit dividend
receivables and supplied terminal cash or a visible unresolved terminal state.
Adapter fields were checked against official [US-equity data documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/handling-data)
and [fill-model concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts)
on 2026-10-07; this is documentation alignment, not cloud parity.

## Focused validation and handoff

Tests are stdlib `unittest.TestCase` modules and remain pytest-discoverable.
Use named module patterns for relevant focused checks, for example:

```text
python -m unittest discover -s tests/guidance_revision_drift -p test_simulation.py -v
python -m unittest discover -s tests/guidance_revision_drift -p test_scenario.py -v
python -m unittest discover -s tests/guidance_revision_drift -p test_boundaries.py -v
```

These offline tests do not require operator state. Do not bypass the normal
pytest isolation guards for application tests. Codex does not run a complete
lane/repository suite here; Claude performs the full lane suite during the
independent review. Author/subagent QA is not that review. Windows and cloud
execution have not been verified.

Exact scope, commit dispositions, checks, corrected findings and next action:
`docs/Strategy Description/GUIDANCE_REVISION_DRIFT_IMPLEMENTATION_RECORD.md`.
The Action Plan owns sequencing and `docs/SESSION_HANDOFF.md` owns the generic
cross-computer handoff. Stop at the published batch for Claude review; no next
data/outcome/operational milestone starts automatically.
