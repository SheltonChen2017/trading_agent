"""Claude section 369 review: the Insider platform helper on autocrlf hosts.

The helper's 17 pins are LF Git blobs, but it only skips anything on a host
without fcntl, and the recorded Windows host checks tests/ out with
core.autocrlf=true. The helper must accept exactly that conversion of the
pinned blobs and still refuse every other byte change.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "insider_buying_pytest_platform_crlf_review", ROOT / "tests" / "insider_buying_pytest_platform.py",
)
assert _spec is not None and _spec.loader is not None
helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helper)


def _copy(tmp_path, transform):
    for relative in helper.FROZEN_POSIX_TEST_SHA256:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        target.write_bytes(transform(relative, raw))
    return tmp_path


def test_autocrlf_checkout_of_the_exact_pins_is_accepted(tmp_path):
    root = _copy(tmp_path, lambda _relative, raw: raw.replace(b"\n", b"\r\n"))
    assert all(b"\r\n" in (root / relative).read_bytes() for relative in helper.FROZEN_POSIX_TEST_SHA256)
    helper._validate_frozen_images(root=root)


def test_exact_lf_images_are_still_accepted(tmp_path):
    helper._validate_frozen_images(root=_copy(tmp_path, lambda _relative, raw: raw))


@pytest.mark.parametrize("source_crlf", (False, True))
def test_autocrlf_fixture_accepts_lf_and_crlf_source_checkouts(tmp_path, monkeypatch, source_crlf):
    source = tmp_path / "source"
    for relative in helper.FROZEN_POSIX_TEST_SHA256:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        target.write_bytes(raw.replace(b"\n", b"\r\n") if source_crlf else raw)
    monkeypatch.setitem(globals(), "ROOT", source)
    copied = _copy(tmp_path / "copied", lambda _relative, raw: raw.replace(b"\n", b"\r\n"))
    assert all(b"\r\r\n" not in (copied / relative).read_bytes()
               for relative in helper.FROZEN_POSIX_TEST_SHA256)
    helper._validate_frozen_images(root=copied)


@pytest.mark.parametrize("fault", ("crlf-plus-edit", "lone-cr", "doubled-cr"))
def test_line_ending_tolerance_does_not_hide_a_changed_image(tmp_path, fault):
    victim = sorted(helper.FROZEN_POSIX_TEST_SHA256)[0]

    def transform(relative, raw):
        crlf = raw.replace(b"\n", b"\r\n")
        if relative != victim:
            return crlf
        if fault == "crlf-plus-edit":
            return crlf + b"# changed\r\n"
        if fault == "lone-cr":
            return raw.replace(b"\n", b"\r", 1)
        return crlf.replace(b"\r\n", b"\r\r\n", 1)

    with pytest.raises(pytest.UsageError, match="image changed: " + victim):
        helper._validate_frozen_images(root=_copy(tmp_path, transform))
