"""Exact fresh, counts-only diagnosis of the retained first Sharadar response.

No provider, credential, QC or outcome opener. A fresh exclusive private read
claim precedes the single licensed wire read. This is not source admission.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path
import stat
import subprocess

from research.target_price_revisions_qc import extended_source_capture as capture

OPERATION = "TPR-EXT26-CAPTURE-DIAGNOSTIC-20261010-001"
SOURCE = "research/target_price_revisions_qc/extended_capture_diagnostic.py"
WIRE = "request.0387.wire.csv"
WIRE_SHA = "10e4412848bf6c917b2f22657a3203e204bf77925c2f422f50c4d4a983ecf45a"
WIRE_BYTES = 451756
INDEX_SHA = "701ab0f2e9e61d1db1f53b7d274bf70429f84b565a9fff8c56d1ced13b73e82c"
OWNER_SHA = "fcbf682e1cf8d9c0649f49128b1e37fc8f7b31ae75fb5a7c672a6d354d549c31"


def diagnose(payload):
    """Pure schema/page/order counts; never return a native identifier or row."""
    if type(payload) is not bytes or not 0 < len(payload) <= 4 * 1024**2:
        raise ValueError("diagnostic wire bound refused")
    rows = csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
    header = next(rows)
    required = set(capture.CSV_FIELDS["tickers"]) - {"figi"}
    result = {"schema": "tpr-ext26-csv-diagnostic-v1", "required_fields_present": required <= set(header),
        "unique_header": len(header) == len(set(header)), "header_columns": len(header),
        "row_count": 0, "row_width_failures": 0, "ticker_sort_descents": 0,
        "rows_above_registered_page_limit": 0, "original_projection_accepted": False,
        "closed_projection_refusal": None, "point_in_time_data": False,
        "source_input_admitted": False, "outcome_reads": 0, "quantconnect_attempts": 0}
    previous = None
    for values in rows:
        result["row_count"] += 1
        if result["row_count"] > 640000:
            raise ValueError("diagnostic row bound refused")
        if len(values) != len(header):
            result["row_width_failures"] += 1
            continue
        native = dict(zip(header, values))
        ticker = native.get("ticker")
        if ticker is not None:
            if previous is not None and ticker < previous:
                result["ticker_sort_descents"] += 1
            previous = ticker
    result["rows_above_registered_page_limit"] = max(0, result["row_count"] - 10000)
    try:
        capture._csv_projection(payload, "tickers", {})
        result["original_projection_accepted"] = True
    except capture.CaptureError as error:
        allowed = {"capture CSV structural schema refused", "capture CSV sorting refused"}
        result["closed_projection_refusal"] = str(error) if str(error) in allowed else "unclassified_closed_refusal"
    return result


def _read(directory, name, size, sha):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size != size):
            raise ValueError("diagnostic private custody refused")
        chunks, remaining = [], size
        while remaining:
            piece = os.read(fd, min(1048576, remaining))
            if not piece: raise ValueError("diagnostic truncated wire refused")
            chunks.append(piece); remaining -= len(piece)
        payload, after = b"".join(chunks), os.fstat(fd)
        stable = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_nlink','st_mode','st_uid')
        if any(getattr(before,key)!=getattr(after,key) for key in stable) or hashlib.sha256(payload).hexdigest() != sha:
            raise ValueError("diagnostic private bytes changed")
        return payload
    finally:
        os.close(fd)


def run():
    if Path.cwd() != capture.LANE_ROOT or Path.cwd().resolve() != capture.LANE_ROOT:
        raise ValueError("diagnostic physical lane refused")
    def git(*args):
        return subprocess.run(["git", *args], cwd=capture.LANE_ROOT, capture_output=True, check=True, timeout=5).stdout
    if git("rev-parse", "--show-toplevel").decode().strip() != str(capture.LANE_ROOT) or git("branch", "--show-current").decode().strip() != capture.LANE_BRANCH:
        raise ValueError("diagnostic Git lane refused")
    head = git("rev-parse", "HEAD").decode().strip(); git("status", "--short")
    paths = (SOURCE, *capture.SOURCE_PATHS)
    hashes = {}
    for relative in paths:
        raw = capture._read_source(relative)
        if raw != git("show", head + ":" + relative):
            raise ValueError("diagnostic committed closure refused")
        hashes[relative] = hashlib.sha256(raw).hexdigest()
    if git("rev-parse", "HEAD").decode().strip() != head:
        raise ValueError("diagnostic HEAD changed")
    directory = capture._private_directory(capture.PRIVATE_ROOT, "production")
    try:
        plan = {"schema": "tpr-ext26-capture-diagnostic-plan-v1", "operation_id": OPERATION,
            "git_sha": head, "source_hashes": hashes, "owner_instruction_sha256": OWNER_SHA,
            "created_utc": datetime.now(timezone.utc).isoformat(), "wire_file": WIRE,
            "wire_sha256": WIRE_SHA, "wire_bytes": WIRE_BYTES, "capture_index_sha256": INDEX_SHA,
            "scope": "one retained first Sharadar wire; schema/count/order diagnosis only",
            "max_rows": 640000, "outcome_reads": 0, "quantconnect_attempts": 0,
            "provider_requests": 0, "source_input_admitted": False}
        capture._claim(directory, OPERATION + ".read.spent.json", plan)
        # Exclusive claim exists before even the licensed CSV wire is opened.
        report = {**diagnose(_read(directory, WIRE, WIRE_BYTES, WIRE_SHA)), "operation_id": OPERATION,
            "scope_spent": True, "git_sha": head, "wire_sha256": WIRE_SHA, "capture_index_sha256": INDEX_SHA}
        capture._publish(directory, OPERATION + ".completed.json", report)
        return report
    finally:
        os.close(directory)


def main():
    try:
        result = run()
    except Exception:
        result = {"status": "refused_or_unknown", "automatic_retry": False}
        print(capture._canonical(result).decode(), end="")
        return 1
    print(capture._canonical(result).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
