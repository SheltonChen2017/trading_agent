"""Offline forward-vintage receipt preparation; never a paper-confirmation run.

``build`` reads an existing, externally SHA-pinned Massive capture and writes
one private, content-addressed development-quality receipt. ``compare`` reads
two externally pinned receipts for the same exact event-date window and emits
only counts. Neither command fetches provider data or contacts QuantConnect.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2.canonical import CanonicalEvidenceError
from research.analyst_revisions_v2 import forward_data_quality as quality
from scripts import capture_arv2_massive as capture


DEFAULT_OUTPUT_ROOT = (
    ROOT / "artifacts" / "analyst_revisions_v2" / "forward_data_quality"
)


def build_receipt(
    artifact_path: Path,
    expected_manifest_sha256: str,
    *,
    first_event_date: str,
    last_event_date: str,
    expected_transport: str = capture.PRODUCTION_TRANSPORT,
) -> tuple[bytes, str]:
    """Compose the pure receipt derivation with the authenticated capture bridge."""

    def visit_authenticated_pages(visit_page):
        return capture._visit_authenticated_massive_capture_pages_for_bridge(
            Path(artifact_path),
            expected_transport=expected_transport,
            visit_page=visit_page,
        )

    return quality.build_receipt_from_authenticated_pages(
        visit_authenticated_pages,
        expected_manifest_sha256,
        first_event_date=first_event_date,
        last_event_date=last_event_date,
        expected_transport=expected_transport,
    )


def publish_receipt(payload: bytes, expected_sha256: str, output_root: Path) -> Path:
    """Write once inside the private artifact tree; never replace old bytes."""
    quality._require_receipt(payload, expected_sha256)
    root = Path(output_root).absolute()
    capture._require_operational_artifact_scope(root)
    _, descriptor = capture._open_directory_path(
        root, create=True, name="forward quality receipt root"
    )
    try:
        name = f"forward-quality-{expected_sha256}.json"
        capture._exclusive_private_write_at(
            descriptor, name, payload, "forward quality receipt"
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return root / name


def _read_pinned_receipt(path: Path, expected_sha256: str) -> bytes:
    quality.require_sha256(expected_sha256, "external forward receipt pin")
    candidate = Path(path).absolute()
    if candidate.name != f"forward-quality-{expected_sha256}.json":
        raise quality.ForwardDataQualityError("forward receipt filename is not pinned")
    capture._require_operational_artifact_scope(candidate.parent)
    _, descriptor = capture._open_directory_path(
        candidate.parent, create=False, name="forward receipt directory"
    )
    try:
        payload, _ = capture._read_and_pin_private_regular_at(
            descriptor,
            candidate.name,
            maximum_bytes=quality.MAX_RECEIPT_BYTES,
            name="forward receipt",
        )
    finally:
        os.close(descriptor)
    quality._require_receipt(payload, expected_sha256)
    return payload


def main(
    argv: list[str] | None = None,
    *,
    _expected_transport: str = capture.PRODUCTION_TRANSPORT,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="publish one development-only receipt")
    build.add_argument("--capture-path", type=Path, required=True)
    build.add_argument("--capture-manifest-sha256", required=True)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    compare = commands.add_parser("compare", help="count same-ID changes between pinned receipts")
    compare.add_argument("--before-path", type=Path, required=True)
    compare.add_argument("--before-sha256", required=True)
    compare.add_argument("--after-path", type=Path, required=True)
    compare.add_argument("--after-sha256", required=True)
    for command in (build, compare):
        command.add_argument("--first-event-date", required=True)
        command.add_argument("--last-event-date", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            payload, digest = build_receipt(
                args.capture_path,
                args.capture_manifest_sha256,
                first_event_date=args.first_event_date,
                last_event_date=args.last_event_date,
                expected_transport=_expected_transport,
            )
            path = publish_receipt(payload, digest, args.output_root)
            receipt = quality._require_receipt(payload, digest)
            result = {
                "purpose": quality.PURPOSE,
                "receipt_path": str(path),
                "receipt_sha256": digest,
                "capture_manifest_sha256": receipt["capture_manifest_sha256"],
                "source_row_count": receipt["source_row_count"],
                "role_event_counts": {
                    role["role"]: len(role["events"]) for role in receipt["roles"]
                },
            }
        else:
            before = _read_pinned_receipt(args.before_path, args.before_sha256)
            after = _read_pinned_receipt(args.after_path, args.after_sha256)
            result = quality.compare_receipts(
                before, args.before_sha256, after, args.after_sha256
            )
            old_window = quality._require_receipt(before, args.before_sha256)
            if (
                old_window["first_event_date"] != args.first_event_date
                or old_window["last_event_date"] != args.last_event_date
            ):
                raise quality.ForwardDataQualityError("comparison window does not match exact request")
    except (CanonicalEvidenceError, quality.ForwardDataQualityError,
            capture.MassiveCaptureError, OSError, ValueError):
        print("REFUSED: forward data-quality authentication failed", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
