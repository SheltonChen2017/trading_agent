"""Read-only vendor audit of the Benzinga analyst-ratings feed via Massive.

Owner-authorized 2026-08-20 (ACER-1 vendor half). This script performs NO
backtest and joins NO prices: it downloads the raw ratings-action history into
an immutable, hashed snapshot and reports structural facts about it. Under the
project's look-accounting rules this is a data audit, not a research look.

Safety and provenance rules enforced here:

- The API key is read from the MASSIVE_API_KEY environment variable (falling
  back to the Windows per-user registry scope so a long-lived shell that
  predates the variable still works). It is never printed, never written to
  any file, and stripped from any recorded URL.
- Snapshots are written under ``artifacts/`` (gitignored, AP-2) in a
  timestamped directory. An existing snapshot directory is REFUSED, never
  overwritten: restatement measurement (snapshot A vs B) requires that
  earlier snapshots survive byte-for-byte.
- Every page is stored as raw response bytes with a SHA-256 recorded in a
  manifest, so the analysis is reproducible from the snapshot alone and a
  later snapshot B can be diffed by Benzinga's stable ``benzinga_id``.
- Pagination is partitioned by calendar year and each partition must
  terminate naturally (a page without ``next_url``). A partition that ends
  any other way marks the snapshot INCOMPLETE in the manifest; analysis of an
  incomplete snapshot is refused unless ``--allow-incomplete`` is passed.

Usage:
    python scripts/audit_benzinga_ratings.py download
    python scripts/audit_benzinga_ratings.py analyse <snapshot_dir>
    python scripts/audit_benzinga_ratings.py compare <snapshot_a> <snapshot_b>
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from research.acer.snapshot import SnapshotError, load_verified_rows

BASE = "https://api.massive.com"
RATINGS = "/benzinga/v1/ratings"
PAGE_LIMIT = 1000
REQUEST_PAUSE_SECONDS = 0.15
MAX_RETRIES = 5

# Delisted / bankrupt / acquired / renamed probe set (owner instruction 2).
# Chosen to span delisting years 2016-2024 and every removal mechanism.
DELISTED_PROBES = [
    # bankruptcies (old symbol, OTC successor where one traded)
    "SIVB", "SIVBQ",   # Silicon Valley Bank, 2023
    "FRC", "FRCB",     # First Republic, 2023
    "BBBY", "BBBYQ",   # Bed Bath & Beyond, 2023
    "SBNY",            # Signature Bank, 2023
    "SHLD", "SHLDQ",   # Sears, 2018
    "YELL", "YELLQ",   # Yellow Corp, 2023
    "WE",              # WeWork, bankrupt 2023
    "RAD",             # Rite Aid, bankrupt 2023
    # acquisitions
    "LNKD",            # LinkedIn -> Microsoft, 2016
    "YHOO",            # Yahoo -> Verizon, 2017
    "TWTR",            # Twitter -> private, 2022
    "ATVI",            # Activision -> Microsoft, 2023
    "CELG",            # Celgene -> BMS, 2019
    "ALXN",            # Alexion -> AstraZeneca, 2021
    "XLNX",            # Xilinx -> AMD, 2022
    "MXIM",            # Maxim -> Analog Devices, 2021
    "CTXS",            # Citrix -> private, 2022
    "ZNGA",            # Zynga -> Take-Two, 2022
    "VMW",             # VMware -> Broadcom, 2023
    "SGEN",            # Seagen -> Pfizer, 2023
    "MON",             # Monsanto -> Bayer, 2018
    "WFM",             # Whole Foods -> Amazon, 2017
    "BRCM",            # Broadcom -> Avago, 2016
    "EMC",             # EMC -> Dell, 2016
    "HOT",             # Starwood -> Marriott, 2016
    # renames (old symbol should hold the pre-rename history)
    "FB",              # -> META, 2022
    "ANTM",            # -> ELV, 2022
    "FISV",            # -> FI, 2023
]

RATING_FIELDS_FOR_MISSINGNESS = ("previous_rating", "time", "firm", "rating")
ISSUER_IDENTITY_FIELDS = ("isin", "exchange", "company_name", "ticker")


def _api_key() -> str:
    key = os.environ.get("MASSIVE_API_KEY")
    if not key and sys.platform == "win32":
        try:  # a shell older than the variable: read the per-user scope
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                key = winreg.QueryValueEx(h, "MASSIVE_API_KEY")[0]
        except OSError:
            key = None
    if not key:
        raise SystemExit(
            "MASSIVE_API_KEY is not set (checked process env and the Windows "
            "user scope). Refusing to run without it."
        )
    return key


def _strip_key(url: str) -> str:
    """Defensively remove any credential-looking query parameter."""
    return re.sub(r"([?&])(apiKey|apikey|api_key|token)=[^&]*", r"\1\2=REDACTED", url)


def _get(session: requests.Session, url: str, params: dict | None = None) -> requests.Response:
    for attempt in range(MAX_RETRIES):
        response = session.get(url, params=params, timeout=60)
        if response.status_code == 429:
            wait = 2.0 * (attempt + 1)
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError(f"rate-limited {MAX_RETRIES} times at {_strip_key(url)}")


def download(out_root: Path) -> Path:
    key = _api_key()
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {key}"

    started = dt.datetime.now(dt.timezone.utc)
    snapshot_id = "benzinga-ratings-" + started.strftime("%Y%m%dT%H%M%SZ")
    snap = out_root / snapshot_id
    if snap.exists():
        raise SystemExit(f"REFUSED: snapshot dir already exists: {snap}")
    raw = snap / "raw"
    raw.mkdir(parents=True)

    manifest: dict = {
        "snapshot_id": snapshot_id,
        "endpoint": BASE + RATINGS,
        "page_limit": PAGE_LIMIT,
        "started_utc": started.isoformat(),
        "partitions": [],
        "complete": True,
    }

    this_year = dt.date.today().year
    for year in range(2010, this_year + 1):
        params = {
            "date.gte": f"{year}-01-01",
            "date.lte": f"{year}-12-31",
            "limit": PAGE_LIMIT,
            "sort": "date.asc",
        }
        page = 0
        rows = 0
        url: str | None = BASE + RATINGS
        terminated_naturally = False
        pages: list[dict] = []
        while url is not None:
            response = _get(session, url, params=params if page == 0 else None)
            payload = response.content
            digest = hashlib.sha256(payload).hexdigest()
            fname = f"{year}-p{page:04d}.json"
            (raw / fname).write_bytes(payload)
            body = json.loads(payload)
            results = body.get("results") or []
            rows += len(results)
            pages.append(
                {
                    "file": fname,
                    "sha256": digest,
                    "rows": len(results),
                    "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "url": _strip_key(response.url),
                }
            )
            next_url = body.get("next_url")
            if not next_url:
                terminated_naturally = True
                url = None
            else:
                url = next_url
                page += 1
                time.sleep(REQUEST_PAUSE_SECONDS)
        manifest["partitions"].append(
            {
                "year": year,
                "pages": pages,
                "rows": rows,
                "terminated_naturally": terminated_naturally,
            }
        )
        if not terminated_naturally:
            manifest["complete"] = False
        print(f"{year}: {rows} rows in {len(pages)} page(s)", flush=True)

    manifest["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode()
    (snap / "manifest.json").write_bytes(manifest_bytes)
    (snap / "manifest.sha256").write_text(
        hashlib.sha256(manifest_bytes).hexdigest() + "\n", encoding="utf-8"
    )
    print(f"snapshot: {snap}")
    print(f"complete: {manifest['complete']}")
    return snap


def _load_rows(snap: Path, allow_incomplete: bool) -> list[dict]:
    """Load and verify a snapshot, converting refusals to CLI exits.

    The verification rules themselves live in ``research.acer.snapshot``,
    which is the single authoritative implementation shared with the ACER
    backbone. Keeping two copies would let the audit tool and the dataset
    builder disagree about which snapshots are trustworthy, which is exactly
    the kind of drift this repository's consolidation rule exists to stop.
    """
    try:
        return load_verified_rows(snap, allow_incomplete)
    except SnapshotError as exc:
        raise SystemExit(str(exc)) from exc


def _parse_action_date(value: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_last_updated(value: object) -> dt.datetime | None:
    """Parse documented ISO values, plus legacy forms defensively.

    Snapshot A's 587,046 ``last_updated`` values are all ISO-8601 ``Z``
    (measured 2026-08-20); the legacy branches are defensive coverage for
    future payload changes, not a format observed in this delivery.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _last_updated_date_facts(rows: list[dict]) -> collections.Counter:
    """Return date-level update facts without inventing a timezone."""
    facts = collections.Counter()
    for row in rows:
        action_date = _parse_action_date(row.get("date"))
        updated = _parse_last_updated(row.get("last_updated"))
        if action_date is None:
            facts["invalid_action_date"] += 1
            continue
        if updated is None:
            facts["missing_or_invalid_last_updated"] += 1
            continue
        facts["parsed"] += 1
        gap_days = (updated.date() - action_date).days
        if gap_days < 0:
            facts["before_action_date"] += 1
        elif gap_days == 0:
            facts["same_action_date"] += 1
        else:
            facts["after_action_date"] += 1
        if gap_days > 90:
            facts["more_than_90_days_after"] += 1
    return facts


def analyse(snap: Path, allow_incomplete: bool) -> None:
    rows = _load_rows(snap, allow_incomplete)
    print(f"total rows: {len(rows)}")
    if not rows:
        return

    dates = sorted(r.get("date") or "" for r in rows if r.get("date"))
    print(f"earliest action date: {dates[0]}")
    print(f"latest action date:   {dates[-1]}")

    by_year: dict[str, dict] = collections.defaultdict(
        lambda: {"rows": 0, "tickers": set(), "firms": set()}
    )
    missing = collections.Counter()
    ids = collections.Counter()
    inconsistent_transitions = 0
    self_transitions = 0
    hour_hist = collections.Counter()

    for r in rows:
        year = (r.get("date") or "????")[:4]
        bucket = by_year[year]
        bucket["rows"] += 1
        if r.get("ticker"):
            bucket["tickers"].add(r["ticker"])
        if r.get("firm"):
            bucket["firms"].add(r["firm"])
        for field in (*RATING_FIELDS_FOR_MISSINGNESS, *ISSUER_IDENTITY_FIELDS):
            value = r.get(field)
            if value is None or value == "":
                missing[field] += 1
        rid = r.get("benzinga_id")
        if rid:
            ids[rid] += 1
        else:
            missing["benzinga_id"] += 1
        action = (r.get("rating_action") or "").lower()
        prev, curr = r.get("previous_rating"), r.get("rating")
        if prev and curr and prev == curr and action in ("upgrades", "downgrades"):
            inconsistent_transitions += 1
        if prev and curr and prev == curr:
            self_transitions += 1
        t = r.get("time") or ""
        if re.match(r"^\d{2}:\d{2}", t):
            hour_hist[int(t[:2])] += 1

    print("\nyear  rows      tickers  firms")
    for year in sorted(by_year):
        b = by_year[year]
        print(f"{year}  {b['rows']:>8}  {len(b['tickers']):>7}  {len(b['firms']):>5}")

    print("\nmissingness (of", len(rows), "rows):")
    for field in (
        *RATING_FIELDS_FOR_MISSINGNESS,
        *ISSUER_IDENTITY_FIELDS,
        "benzinga_id",
    ):
        n = missing[field]
        print(f"  {field:<16} {n:>8}  ({n / len(rows):.2%})")

    duplicates = {k: v for k, v in ids.items() if v > 1}
    print(f"\nduplicate benzinga_id values: {len(duplicates)}")
    for k, v in list(sorted(duplicates.items()))[:10]:
        print(f"  {k}: {v} occurrences")
    print(f"self-transitions (previous_rating == rating): {self_transitions}")
    print(
        "inconsistent transitions (equal ratings but action says up/downgrade): "
        f"{inconsistent_transitions}"
    )

    print("\ntime-of-day histogram (hour -> rows), for timezone inference:")
    for hour in sorted(hour_hist):
        print(f"  {hour:02d}h {hour_hist[hour]:>8}")
    update_facts = _last_updated_date_facts(rows)
    print("\nlast_updated date integrity (timezone-neutral):")
    for label in (
        "parsed",
        "missing_or_invalid_last_updated",
        "invalid_action_date",
        "before_action_date",
        "same_action_date",
        "after_action_date",
        "more_than_90_days_after",
    ):
        print(f"  {label:<31} {update_facts[label]:>8}")

    print("\ndelisted/renamed probe coverage (rows in snapshot, last action date):")
    probe_rows: dict[str, list[str]] = {p: [] for p in DELISTED_PROBES}
    for r in rows:
        t = r.get("ticker")
        if t in probe_rows:
            probe_rows[t].append(r.get("date") or "")
    for probe in DELISTED_PROBES:
        found = sorted(d for d in probe_rows[probe] if d)
        if found:
            print(f"  {probe:<6} {len(found):>6} rows  {found[0]} .. {found[-1]}")
        else:
            print(f"  {probe:<6}      0 rows  ABSENT")


def compare(snap_a: Path, snap_b: Path, allow_incomplete: bool) -> None:
    """Restatement measurement: diff two snapshots by stable benzinga_id."""
    def keyed(snap: Path) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for index, r in enumerate(_load_rows(snap, allow_incomplete)):
            rid = r.get("benzinga_id")
            if not isinstance(rid, str) or not rid.strip():
                raise SystemExit(
                    f"REFUSED: snapshot {snap} row {index} has no benzinga_id"
                )
            if rid in out:
                raise SystemExit(
                    f"REFUSED: snapshot {snap} has duplicate benzinga_id {rid}"
                )
            out[rid] = r
        return out

    a, b = keyed(snap_a), keyed(snap_b)
    added = sorted(set(b) - set(a))
    deleted = sorted(set(a) - set(b))
    modified = []
    for rid in set(a) & set(b):
        if a[rid] != b[rid]:
            changed = sorted(
                k for k in set(a[rid]) | set(b[rid]) if a[rid].get(k) != b[rid].get(k)
            )
            modified.append((rid, changed))
    print(f"A rows: {len(a)}   B rows: {len(b)}")
    print(f"added in B:    {len(added)}")
    print(f"deleted in B:  {len(deleted)}")
    print(f"modified:      {len(modified)}")
    for rid, changed in modified[:20]:
        print(f"  {rid}: fields {changed}")
    if deleted[:10]:
        print("first deleted ids:", deleted[:10])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download")
    d.add_argument("--out", default="artifacts/benzinga_audit")
    a = sub.add_parser("analyse")
    a.add_argument("snapshot")
    a.add_argument("--allow-incomplete", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("snapshot_a")
    c.add_argument("snapshot_b")
    c.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    if args.cmd == "download":
        download(Path(args.out))
    elif args.cmd == "analyse":
        analyse(Path(args.snapshot), args.allow_incomplete)
    else:
        compare(Path(args.snapshot_a), Path(args.snapshot_b), args.allow_incomplete)


if __name__ == "__main__":
    main()
