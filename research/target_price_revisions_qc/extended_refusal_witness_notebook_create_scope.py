"""One bounded Mia UI custody holder, never a QC launch or native data reader.

The human-facing task is the separately frozen public prompt. This holder
retains fresh claim/access/result custody and owns only its own lock. It
does not prove genuine Mia tool execution, native timing or source accounting.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys

from research.target_price_revisions_qc import extended_mia_capture as m

OPERATION = "TPR-EXT26-MIA-WITNESS-NOTEBOOK-CREATE-20261022-001"
PREREG = "research/target_price_revisions_qc/extended_refusal_witness_notebook_create_20261022.json"
PREREG_SHA = "d439555e255928b41769a91f7c93c2d202025bbd024733d805e8abe388d3f077"


def main():
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    m._guard(head)
    self_path = "research/target_price_revisions_qc/extended_refusal_witness_notebook_create_scope.py"
    self_raw = Path(self_path).read_bytes()
    self_frozen = subprocess.run(["git", "show", head + ":" + self_path], capture_output=True, check=True, timeout=5).stdout
    if self_raw != self_frozen:
        raise ValueError("public native-read holder source refused")
    raw = Path(PREREG).read_bytes()
    frozen = subprocess.run(["git", "show", head + ":" + PREREG], capture_output=True, check=True, timeout=5).stdout
    if raw != frozen or hashlib.sha256(raw).hexdigest() != PREREG_SHA:
        raise ValueError("public native-read scope refused")
    prereg = json.loads(raw)
    created = datetime.now(timezone.utc)
    expires = min(created + timedelta(seconds=600), datetime.fromisoformat(prereg["deadline_utc"].replace("Z", "+00:00")))
    if expires <= created:
        raise ValueError("public native-read scope expired")
    plan = {
        "operation_id": OPERATION, "git_head": head, "created_utc": created.isoformat(),
        "expires_utc": expires.isoformat(), "project_id": 37650980,
        "job_id": "3bcfc642896ea36e26b5cbca2988220c", "prereg_sha256": PREREG_SHA,
        "prompt_sha256": hashlib.sha256(prereg["prompt"].encode()).hexdigest(),
        "empty_notebook_sha256": hashlib.sha256(prereg["empty_notebook"].encode()).hexdigest(), "max_ax": 16, "max_screenshots": 4,
        "holder_sha256": hashlib.sha256(self_raw).hexdigest(),
        "max_own_route_actions": 12, "messages": 1, "new_own_chats": 1, "max_emitted_control_crops": 4, "max_metadata_inventories": 1,
        "max_native_contains": 0, "max_native_reads": 0, "max_new_notebook_creations": 1, "max_project_metadata_reads": 1, "max_exact_file_existence_checks": 1, "max_native_bytes_after_allocation": 4096,
        "source_edits": 0, "notebook_creation_or_execution": 0, "mode_changes": 0,
        "compiles": 0, "jobs": 0, "global_object_enumeration": False, "raw_external_export": False,
        "native_custody_established_by_holder": False, "automatic_retry": False,
    }
    directory = m.files._directory(m.PRIVATE_ROOT, private=True)
    lock = None
    try:
        m._publish(directory, OPERATION + ".claim.spent.json", m.e.canonical(plan))
        lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        access = m._publish(directory, OPERATION + ".access.json", m.e.canonical(plan))
        print(json.dumps({"status": "READY_FOR_BOUNDED_MIA_UI", "operation_id": OPERATION, "access": access,
            "expires_utc": expires.isoformat(), "prompt_sha256": plan["prompt_sha256"]}), flush=True)
        remaining = (expires - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0 or not select.select([sys.stdin], [], [], remaining)[0]:
            response = {"status": "EXPIRED_UNCERTAIN", "deliberate_messages": 0}
        else:
            line = sys.stdin.readline(16385)
            if not line.endswith("\n") or len(line.encode()) > 16384:
                raise ValueError("body-free native-read UI result refused")
            response = json.loads(line)
            if type(response) is not dict or len(response) > 24:
                raise ValueError("body-free native-read UI result refused")
        m._guard(head)
        response.update(operation_id=OPERATION, ended_utc=datetime.now(timezone.utc).isoformat(),
            new_codex_attempts=0, new_looks=0, native_acceptance=False)
        encoded = m.e.canonical(response)
        if len(encoded) > 16384:
            raise ValueError("body-free native-read UI result refused")
        receipt = m._publish(directory, OPERATION + ".result.json", encoded)
        print(json.dumps({"status": "CLOSED_BOUNDED_MIA_UI", "result": receipt}), flush=True)
    finally:
        if lock is not None:
            try:
                actual, owned = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False), os.fstat(lock)
                if (actual.st_dev, actual.st_ino) == (owned.st_dev, owned.st_ino):
                    os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError:
                pass
            finally:
                os.close(lock)
        os.close(directory)


if __name__ == "__main__":
    main()
