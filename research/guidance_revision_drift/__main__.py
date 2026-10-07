"""Local contract inspection only: no launch, download, capture or order command."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from data.hashing import canonical_json
from research.guidance_revision_drift.contracts import (
    CandidateError,
    load_candidate,
    verify_source_documents,
)
from research.guidance_revision_drift.readiness import preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("show-candidate", "preflight"))
    args = parser.parse_args(argv)
    try:
        candidate = load_candidate()
        verify_source_documents(candidate, Path(__file__).resolve().parents[2])
        if args.command == "show-candidate":
            print(canonical_json(candidate.to_dict()))
            return 0
        print(canonical_json(preflight(candidate).to_dict()))
        # A valid inspection must not look like approval to a shell caller.
        return 2
    except CandidateError as exc:
        print(canonical_json({"status": "invalid_candidate", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
