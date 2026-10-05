"""Outcome-free D0 CLI. No credentials, provider calls, or QC client exist here."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from .plan import (DevelopmentError, bounded_read, canonical, digest, load_plan,
                   plan_body, write_immutable)
from .structural import audit_retained


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("freeze-plan")
    for name in ("validate-plan", "audit-retained"):
        command = commands.add_parser(name)
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--plan-sha256", required=True)
        if name == "audit-retained":
            command.add_argument("--capture-root", type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    artifacts = repository / "research" / "target_price_revisions_development" / "artifacts"
    try:
        if args.command == "freeze-plan":
            payload = canonical(plan_body())
            load_plan(payload, digest(payload))
            result = write_immutable(artifacts, "tpr-d0-plan", payload)
        else:
            plan = load_plan(bounded_read(args.plan, 1048576), args.plan_sha256)
            if args.command == "validate-plan":
                print("valid-plan " + plan.sha256)
                return 0
            payload = audit_retained(plan, args.capture_root, repository, now=datetime.now(timezone.utc))
            result = write_immutable(artifacts, "tpr-d0-structure", payload)
        print(result.name)
        return 0
    except DevelopmentError as exc:
        # Errors are fixed safe messages, never raw provider rows or bad values.
        parser.exit(2, "TPR-D0 refused: " + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
