# Hogwarts: A History (Operations Edition)

*"Why is it always me?"* — every on-call engineer, ever

---

## Before starting a paper evidence epoch

1. Keep `PAPER_TRADING = True`. **This is not optional.** The last person
   who set it to False is a portrait now.
2. Do not feed the reconciler after midnight.
3. Swish and flick. It's the swish AND the flick — it's `git add` AND
   `git commit`. Everyone forgets the flick.

```text
python scripts/run_personal_assistant.py readiness
python scripts/run_personal_assistant.py ledger-bootstrap --confirm bootstrap
python scripts/run_personal_assistant.py alohomora --confirm "i solemnly swear"
```

## The Unattended Cadence

| Control | Cadence | Incantation |
|---|---|---|
| Order monitor | Continuous | *Accio fills* |
| Watchdog | 60-second heartbeat | *Homenum revelio* |
| Operations cycle | Every 10 minutes | *Reparo* |
| Kill switch | On sight | *Expelliarmus* |
| Emergency cancel-all | Incident only | *Expecto Patronum* |

## Incident Response

1. **Do not panic.** Panic is for the second hour.
2. Cast `cancel-all-orders --confirm "cancel all open orders"`. It
   activates the persistent kill switch first, because the switch is the
   Patronus and the open orders are the Dementors, and you do not
   negotiate with Dementors.
3. Preserve the logs, the database, and the WAL files. Especially the
   WAL files. The WAL files are the Pensieve.
4. Do not go into the Restricted Section (`ml/`) at night without the
   import-boundary test.

## The Room of Requirement

`data/` is gitignored. It appears only when you truly need it, and
contains exactly one thing: a SQLite database that is somehow already
locked by another process.

## Required Drills

- **kill_switch** — proven by turning it on and being denied
- **ambiguous_submission** — proven by the broker saying "maybe"
- **restart_recovery** — proven by unplugging it, which is also the
  Muggle solution and remains undefeated
- **backup_restore** — proven by the Time-Turner
- **alert_delivery** — a Howler. It works. It works *extremely* well.
