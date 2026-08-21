"""Report issuer-identity ambiguity across a verified ACER ratings snapshot.

Structural measurement only: it reads a hash-verified snapshot, normalizes it,
and reports which tickers carry evidence that a raw-ticker join would be
unsafe. It makes no network call, joins no price or outcome, ranks nothing,
and consumes no research look.

Usage:
    python scripts/report_acer_identity.py <snapshot_dir>
    python scripts/report_acer_identity.py <snapshot_dir> --show 40
    python scripts/report_acer_identity.py <snapshot_dir> --refusal-list out.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:  # direct `python scripts/...` invocation
    sys.path.insert(0, str(REPO_ROOT))

from research.acer.identity import (  # noqa: E402
    ambiguous_tickers,
    assess_identities,
    summarize_identities,
)
from research.acer.normalize import normalize_rows  # noqa: E402
from research.acer.snapshot import SnapshotError, load_verified_snapshot  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="verified snapshot directory")
    parser.add_argument(
        "--show",
        type=int,
        default=25,
        help="how many ambiguous tickers to print in detail (default 25)",
    )
    parser.add_argument(
        "--refusal-list",
        type=Path,
        default=None,
        help="write the ambiguous-ticker refusal set to this file, one per line",
    )
    args = parser.parse_args(argv)

    try:
        rows, _ = load_verified_snapshot(args.snapshot)
    except SnapshotError as exc:
        raise SystemExit(str(exc)) from exc

    events, _ = normalize_rows(rows)
    identities = assess_identities(events)
    report = summarize_identities(identities)
    print(json.dumps(report, indent=2, sort_keys=True))

    ambiguous = [item for item in identities if item.is_ambiguous]
    ambiguous.sort(key=lambda item: (-item.event_count, item.ticker))
    if args.show > 0 and ambiguous:
        print(f"\nmost active ambiguous tickers (top {min(args.show, len(ambiguous))}):")
        for item in ambiguous[: args.show]:
            names = " | ".join(
                f"{era.company_name} [{era.first_action_date}..{era.last_action_date}]"
                for era in item.name_eras
            )
            gap = "" if item.max_era_gap_days is None else f" gap={item.max_era_gap_days}d"
            print(f"  {item.ticker:<8} {item.event_count:>5} events{gap}")
            print(f"      reasons: {', '.join(item.reasons)}")
            print(f"      eras: {names or '(none named)'}")
            if item.shared_names_with:
                print(f"      shares a name with: {', '.join(item.shared_names_with)}")

    if args.refusal_list is not None:
        refusals = ambiguous_tickers(identities)
        args.refusal_list.write_text(
            "\n".join(refusals) + ("\n" if refusals else ""), encoding="utf-8"
        )
        print(f"\nrefusal set written: {len(refusals)} tickers -> {args.refusal_list}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
