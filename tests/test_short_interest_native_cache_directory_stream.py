"""Concurrent cache custody regressions; fabricated protected files only."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "si_cache_fd_regression_fixture",
    ROOT / "tests/test_short_interest_native_anchor_cache_capture.py",
)
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)
m = f.m

@pytest.mark.skipif(sys.platform != "darwin", reason="protected macOS directory FD runtime")
def test_concurrent_source_custody_never_reuses_directory_stream(monkeypatch, tmp_path):
    root, plan, matrix, archives, summary, calls, guard = f.fixture(monkeypatch, tmp_path)
    f.register(monkeypatch, m.write_cache(root, runtime_head=f.CREATOR, actual_remote=f.REMOTE))
    with m.load_registered_cache(root, runtime_head=f.CURRENT, actual_remote=f.REMOTE) as loaded:
        retained = loaded._anchor[1][0]._anchor[0][0][1]
        original = os.listdir
        barrier, lock = threading.Barrier(8), threading.Lock()
        simultaneous, reused, observed = set(), [], []
        def scanning(descriptor):
            assert type(descriptor) is int
            with lock:
                if descriptor in simultaneous:
                    reused.append(descriptor)
                simultaneous.add(descriptor)
                observed.append(descriptor)
            barrier.wait(timeout=10)
            try:
                return original(descriptor)
            finally:
                barrier.wait(timeout=10)
                with lock:
                    simultaneous.discard(descriptor)
        errors = []
        with monkeypatch.context() as patch:
            patch.setattr(m.os, "listdir", scanning)
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(loaded.source_custody) for _ in range(8)]
                for future in futures:
                    try:
                        future.result()
                    except m.contract.AnchorCacheRefusal as error:
                        errors.append(type(error).__name__)
        assert not reused and len(set(observed)) == 8 and retained not in observed, (
            "concurrent custody reused the retained directory stream; os.dup is not a fresh stream"
        )
        assert not errors
        # Fresh independent scans must not weaken the exact-five requirement.
        f.protected(root / m.TARGET / "unbound.private.bin", b"fabricated")
        with pytest.raises(m.contract.AnchorCacheRefusal, match="exact_five_file"):
            loaded.source_custody()

@pytest.mark.skipif(sys.platform != "darwin", reason="protected macOS directory FD runtime")
def test_failed_inventory_scan_closes_only_fresh_open_and_keeps_boundaries(monkeypatch, tmp_path):
    path = tmp_path.resolve()
    path.chmod(0o700)
    retained = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    original_open, original_close = os.open, os.close
    opened, closed, boundaries = [], [], []
    def opening(name, flags, *args, **kwargs):
        descriptor = original_open(name, flags, *args, **kwargs)
        opened.append((name, flags, kwargs.get("dir_fd"), descriptor))
        return descriptor
    def closing(descriptor):
        closed.append(descriptor)
        return original_close(descriptor)
    def failing(descriptor):
        assert descriptor != retained
        raise OSError("fabricated local listing failure")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(m.os, "open", opening)
            patch.setattr(m.os, "close", closing)
            patch.setattr(m.os, "listdir", failing)
            with pytest.raises(OSError, match="fabricated local"):
                m._inventory_names(retained, boundary=lambda: boundaries.append(1))
        assert len(opened) == 1 and opened[0][0] == "." and opened[0][2] == retained
        assert opened[0][1] & os.O_NOFOLLOW and opened[0][1] & os.O_DIRECTORY
        assert closed == [opened[0][3]] and len(boundaries) == 2
        os.fstat(retained)
        with pytest.raises(OSError):
            os.fstat(opened[0][3])
    finally:
        original_close(retained)
