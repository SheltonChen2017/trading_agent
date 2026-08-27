"""Report issuer-identity ambiguity across a verified ACER ratings snapshot.

Structural measurement only: it reads a hash-verified snapshot, normalizes it,
and reports which tickers carry evidence that a raw-ticker join would be
unsafe. It makes no network call, joins no price or outcome, ranks nothing,
and consumes no research look.

The written artifact is bound to the exact code commit that produced it, so
re-running after **any** later commit — including a documentation-only one
that cannot affect the measurement — produces different bytes and the
immutable write refuses rather than overwrites. That refusal is correct but
easy to misread as corruption, so give each run its own output path. The
measurement's true content identity is ``identity_assessments_sha256``, which
stays stable across commits that do not change the assessment.

Usage:
    python scripts/report_acer_identity.py <snapshot_dir>
    python scripts/report_acer_identity.py <snapshot_dir> --show 40
    python scripts/report_acer_identity.py <snapshot_dir> --diagnostic-flags out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:  # direct `python scripts/...` invocation
    sys.path.insert(0, str(REPO_ROOT))

from data.runtime_identity import RuntimeIdentityError, current_commit  # noqa: E402
from ml.hashing import canonical_json  # noqa: E402
from ml.immutable_io import (  # noqa: E402
    ImmutableFileConflictError,
    publish_immutable_bytes,
)
from research.acer.dataset import build_identity, validate_identity_record  # noqa: E402
from research.acer.identity import (  # noqa: E402
    assess_identities,
    build_diagnostic_report,
    diagnostic_flagged_tickers,
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
        "--diagnostic-flags",
        type=Path,
        default=None,
        help=(
            "write a lineage-bound JSON diagnostic flag set; this is a lower "
            "bound, never an allowlist"
        ),
    )
    args = parser.parse_args(argv)

    try:
        code_commit = current_commit(require_clean=True, repository=REPO_ROOT)
    except RuntimeIdentityError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        rows, manifest_hash = load_verified_snapshot(args.snapshot)
    except SnapshotError as exc:
        raise SystemExit(str(exc)) from exc

    events, refusals = normalize_rows(rows)
    normalized_identity, event_bytes, refusal_bytes = build_identity(
        events,
        refusals,
        source_snapshot_name=args.snapshot.name,
        source_manifest_sha256=manifest_hash,
    )
    validated_identity = validate_identity_record(
        normalized_identity,
        events_bytes=event_bytes,
        refusals_bytes=refusal_bytes,
    )
    identities = assess_identities(events)
    report = build_diagnostic_report(
        identities,
        code_commit=code_commit,
        normalized_dataset_identity=validated_identity,
    )
    try:
        current_commit(
            require_clean=True,
            repository=REPO_ROOT,
            expected_commit=code_commit,
        )
    except RuntimeIdentityError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(report, indent=2, sort_keys=True))

    flagged = [item for item in identities if item.has_ambiguity_evidence]
    flagged.sort(key=lambda item: (-item.event_count, item.ticker))
    if args.show > 0 and flagged:
        print(f"\nmost active name-flagged tickers (top {min(args.show, len(flagged))}):")
        for item in flagged[: args.show]:
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

    if args.diagnostic_flags is not None:
        flags = diagnostic_flagged_tickers(identities)
        artifact = {
            **report,
            "kind": "acer-issuer-identity-diagnostic-flags",
            "flagged_tickers": list(flags),
        }
        try:
            publish_immutable_bytes(
                args.diagnostic_flags,
                (canonical_json(artifact) + "\n").encode("utf-8"),
            )
        except ImmutableFileConflictError as exc:
            raise SystemExit(
                f"REFUSED: diagnostic output already contains different bytes: {exc}"
            ) from exc
        print(
            f"\ndiagnostic flag set written: {len(flags)} tickers -> "
            f"{args.diagnostic_flags}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
