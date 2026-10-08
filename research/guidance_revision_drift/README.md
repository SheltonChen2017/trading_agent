# Guidance Revision Drift — offline engineering candidate

GDR-0A plus ENG-1 through ENG-26 are implemented as offline review candidates. This
is **invented-data software**, not a completed research study or deployable
QuantConnect strategy. Original GDR-0 review/freeze and GDR-1..GDR-6 research,
data, cloud and operating gates remain closed. The original plan/PDF and
proposed parameter hash are unchanged.

The offline core imports only the Python standard library, its own modules and the
unchanged product-neutral `data.hashing` / `data.financial_primitives` helpers.
It has no provider, outcome-fetch, broker, operator-database, scheduler or
live-assistant integration. The isolated `lean/main.py` source imports the
LEAN SDK; the offline core never imports it. No SDK/native/cloud run has been
verified. No other lane's budget or permissions are inherited.

## Implemented surfaces

| Increment | Modules | Bounded behavior |
|---|---|---|
| GDR-0A | `contracts`, `formulas`, `readiness` | Pinned unreviewed proposal/source hashes, strict JSON, exact range arithmetic, always-blocked external readiness |
| ENG-1/2 | `events`, `archive` | Synthetic normalized guidance, immutable version/receipt chain, immediate same-FY comparable predecessor, bootstrap/edit/conflict/correction/withdrawal replay and risk invalidation |
| ENG-3 | `timing`, `universe`, `assessment` | Explicit schedule identity, prior-session 18:00 New York cutoff, D+3 through E+2 opportunities, 20-session history, dated mapping/listing eligibility and exact ranking |
| ENG-4 | `simulation` | Incremental orders, quote-side fills, partial-fill capacity, fees, cash reservations, cancellation acknowledgment/races, settlement, stops, time exits, trims and bounded corporate actions |
| ENG-5 | `qc_adapter` | Strict paired raw quote/trade snapshots mapped into the local order engine; no LEAN deployment or SDK bridge |
| ENG-6 | `controls`, `artifacts`, `comparison`, `reporting`, `fixtures`, `scenario` | Separate base/stress lineage, local content-addressed reports, matched synthetic SYN-SPY tranches, complete paired NAV diagnostics and built-in end-to-end run |
| ENG-7 | `specification` | Executable proposed semantics, unchanged pins and unresolved owner/rights matrix |
| ENG-8/9 | `vendor_payloads`, `lineage` | Public-schema-shaped synthetic payloads, explicit missing semantics, exact units, raw provenance, receipt-order/as-of correction/withdrawal replay |
| ENG-10/11 | `market_inputs`, `corporate_actions`, `comparison` | Dated permanent IDs, calendar-bound raw quote/trade inputs, freshness, atomic paired whole-share/cash accounting and explicit unsupported terminal parity |
| ENG-12/13 | `persistence`, `recovery` | Local no-overwrite command journal, durable publication/checkpoints, fresh-engine replay and pending-order/cancel/reservation reconciliation |
| ENG-14 | `lean_bridge`, `lean/main.py` | Actual order-based algorithm source and strict native receipt protocol; local Python callback tests, no installed SDK or cloud-parity claim |
| ENG-15 | `integration` | Stitched invented provider-to-market-to-paired-order journal/restart scenarios, stress and refusal checks |
| ENG-16 | `release` | Actual source/candidate/contract/calendar/engine fingerprints, reproducible report verification, always-blocked launch preflight |
| ENG-17/18/19 | `lean/main.py`, `lean_bridge` | Zero-fee native control receipts, requested cancellation-pending protocol and strict multiday reader; primary-source-aligned shim regressions, not native execution |
| ENG-20 | `integration` | Receipt-ordered as-of archive ingestion at the first existing 10:00 decision after validation, including nighttime/weekend receipts and exact-redelivery deduplication |
| ENG-21 | `release` | Separate portable content identity and exact interpreter-bound artifact identity; neither grants runtime parity |
| ENG-22/23 | `bundle` | Deterministic source/sidecar ZIP, explicit inventory, current-source/retained-anchor verification and no-overwrite publication; never extracted or executed |
| ENG-24 | `lean_bridge` | Bounded hash-linked callback protocol trace, exact duplicate idempotency and atomic capacity refusal |
| ENG-25/26 | CLI, `release` | Local preparation/verification commands, explicit offline/native/empirical readiness separation and rebuilt review release |

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
python -B -m research.guidance_revision_drift review-release
python -B -m research.guidance_revision_drift launch-preflight
python -B -m research.guidance_revision_drift prepare-bundle --output-dir /absolute/existing/owned-directory
python -B -m research.guidance_revision_drift verify-bundle --bundle-file /absolute/bundle.zip --expected-sha256 RETAINED_SHA256
python -B -m research.guidance_revision_drift synthetic-demo --output-dir /absolute/existing/owned-directory
```

The demo uses only its built-in invented 2025 corpus and explicit 93-session
schedule. It accepts no external input file. Base and stress each simulate an
entry, 20-session-interval exit, settlement and the entire paired daily NAV
calendar. The schedule is a test fixture, **not an audited NYSE calendar**.

`show-candidate`, `adapter-manifest`, a successful demo, release or bundle operation exit 0,
which means only that the local command completed. `preflight` and
`launch-preflight` deliberately exit 2 with
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

Bundle preparation is separate from report publication. It contains only the
explicitly inventoried lane Python source, neutral helpers, candidate and exact
invented sidecar, in repository-relative layout. The 4 MiB bounded ZIP uses
stored members, fixed metadata and canonical inventory. Verification needs a
caller-retained archive hash and reconstructs every member from current source;
it rejects extras, duplicates, altered source, compression and unsafe paths.
It never extracts or imports archive code. Publication flushes the file and
directory and never overwrites; ambiguous post-publication failures are reported
as such. This does not guarantee durability on every platform/filesystem.
Planning documents and SDK/runtime dependencies are not included. Do not treat
the source bundle as an automatically deployable QC project.

Release v2 records the source bundle hash and two identities: portable content
and interpreter environment. `verify_release` still requires exact bytes from
a reconstruction, including Python implementation/version. The separate
`verify_release_content` requires both retained artifact and portable hashes,
reconstructs content, and permits differences **only** in those two interpreter
labels; changed engine settings, source, inputs, economics and gates refuse.
Environment differences remain explicit, and runtime parity stays false. Older
content-addressed releases are retained as historical epochs, not silently
rewritten to match changed source.

Fixture epochs bind actual code-file bytes, candidate, corpus and schedule.
Start/terminal base/stress receipts are separate and hash-linked. The ledger
is a bounded immutable value exported with a report, not a crash-recoverable
global research-look registry. It always records zero empirical looks/QC
attempts. New source/code hashes mean a new fixture epoch, not permission to
observe outcomes. There is no caller-supplied approval/PIT override.

The vendor-shaped decoder follows the public [Massive guidance schema](https://massive.com/docs/rest/partners/benzinga/corporate-guidance),
but accepts only invented SYN identities and 2024–2025 observations. Public
fields do not establish units, publication timezone, immutable provider
versions/receipts or correction semantics: explicit synthetic context supplies
them, with no evidence claim. Previous-value fields are never captured priors.
Exact redelivery retains its first clocks; conflicting identity remaps block
replay rather than silently changing the security.

`LocalJournal` is separate from the small report publisher: it fsyncs content
and directory entries, publishes immutable numbered hash-chain records without
overwrite, and detects stale writers. Ambiguous post-publication errors require
reload. Recovery replays allowed public commands from pinned genesis; it does
not deserialize private snapshots. Caller-retained hashes detect truncation
relative to those anchors, not malicious rollback without an external trust
root. This is a bounded research journal, not a broker or operator database.

Unsupported: real vendor ingestion/PIT audit; source and QC
processing rights; audited historical identifier/calendar/terminal coverage;
fractional split cash-in-lieu and noncash mergers; source-terminal comparator
exit-schedule parity; production restart/reconciliation; LEAN/QC runtime compilation or completion;
statistical allocation/power/confirmation; paper/live operation. Supported
synthetic corporate actions include whole-share splits, explicit dividend
receivables and supplied terminal cash or a visible unresolved terminal state.
Source terminal events never invent a matched SPY sale: the comparator retains
its position and permanent named parity blocker. Native algorithm limitations,
later authorized packaging and the three-attempt/Mia rule are in `lean/README.md`.
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
The owner's 2026-10-07 decision makes this lane record the handoff for both
agents; root Action Plan and Session Handoff remain frozen. Stop at the
published batch for Claude review; no next
data/outcome/operational milestone starts automatically.
