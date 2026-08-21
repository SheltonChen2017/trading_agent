# Independent review — ACER capability-checker completion

Date: 2026-08-21

Reviewer: Codex

Implementation branch: `origin/user/claude/acer-capability-cr-20260821`

Exact reviewed head: `6fc00409249da1d0a4acf23c704f8381e550e5d9`

Base and merge-base: `22519833ec9e5af9333fd1235d7140e4077c215b`

Review branch: `codex/review-acer-capability-completion-20260821`

## Outcome

**Accepted after correction.** The counter-review accurately reproduced and
accepted the preceding Codex findings. Its follow-up implementation correctly
added earnings surprise, but its claim that the ACER-2 data-requirement set
was now complete remained false. The corrected checker contains twelve
requirements and still refuses execution: on this isolated tree, one is
available, six are unavailable, five are unmeasured, eleven block, and
`acer2_runnable=false`.

No vendor API, licensed row, credential, price/outcome join, backtest,
research look, broker, scheduled task, operational database, deployment, or
trading surface was accessed or changed.

## Exact range and commit dispositions

Ordered range `2251983..6fc0040`:

| Commit | Disposition | Review |
|---|---|---|
| `ff8ba6b078dec303e2e4705b4d4a68e8f54b3b5b` | **Accepted** | The prior three findings are reproduced honestly, the method error in the first probe is retained, and the counter-review ledger is complete. Its statement that CCCR-001 was fixed is assessed against the next commit. |
| `6fc00409249da1d0a4acf23c704f8381e550e5d9` | **Accepted after correction** | The earnings-surprise requirement and blocking status are correct, but the asserted complete checklist omitted other frozen inputs and incorrectly treated size as derivable from prices alone. Correction `14a3a83` closes the false-completeness direction. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|---|
| ACERCCR-001 | P2 | Corrected | `6fc0040` | `research/acer/capability.py:68`; `tests/test_acer_capability.py:154` | The checker called an eight-item list the complete ACER-2 requirement set. It omitted the normalized ratings corpus, point-in-time security-type/primary-listing eligibility, point-in-time corporate actions for total-return outcomes, and point-in-time shares outstanding for the size control. It also classified size among controls covered by prices. A future caller could therefore receive `acer2_runnable=true` while lacking a core signal input or frozen universe, outcome, and control inputs. | ACER-0A.7 freezes size as **log market cap** and the outcome as split/dividend-adjusted total return. ACER-0A.10 requires authoritative historical security type and primary listing. The committed event backbone is ACER's signal input. On the submitted tree the new regression imports failed because all four checks were absent. | The module's summary promises completeness and is an execution-readiness gate. An omitted requirement is treated as satisfied, the dangerous failure direction, even though today's unrelated blockers keep the current result red. | `14a3a83` adds four independent blocking requirements and checks, removes size from the price-only group, preserves licensed-row-free operation, and adds absence mutations that require every new check to fail closed. | Red: focused collection failed importing `check_point_in_time_corporate_actions` on the submitted implementation. Green: 24 capability tests and 107 focused ACER tests pass after correction; each new source-disappearance mutation returns `unavailable` and blocking. |

No P0, P1, or P3 finding was identified in this exact range.

## Generalized review

The review compared the checklist against the frozen control, universe, and
outcome contracts rather than checking only the newly mentioned earnings
field. That exposed the same mirror-direction class as the earlier reviews:
the exact-set guard was sound, but the set it guarded still encoded omissions
as satisfaction. The correction keeps each independently removable data
dependency as its own finding. Code presence remains `unmeasured`, never
`available`; no credential or licensed row is used as capability evidence.

Databento remains a candidate audit gate, not an adopted source. The checker
still blocks on it and on the production point-in-time bar path. ACER-2 is not
authorized or runnable, and no milestone completes.

## Validation

- Red reproduction: the submitted implementation failed collection when the
  regression imported the absent corporate-action check.
- Corrected capability suite: **24 passed**.
- Capability plus adjacent ACER backbone: **107 passed**.
- Active-document plus focused ACER set: **154 passed**.
- Complete repository suite: **4,481 passed, 0 failed, 25 dependency warnings**
  in 740.68 seconds on Python 3.13.14.
- `compileall -q` over application, research, scripts, and tests passed.
- Active-document guards were rerun after inserting final counts. `git diff
  --check`, staged-content inspection, ordered-commit inspection, narrow secret
  scan, exact Claude remote-head recheck, clean final status, and shared-checkout
  branch/HEAD invariance also passed before the one final push.
