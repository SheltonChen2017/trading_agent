"""Offline Git checkout controls for the frozen Insider QC source bytes.

This validates checkout behavior, not QC execution or POSIX custody support.
Temporary repositories have no remote and do not inherit global Git settings.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = "research/insider_buying_qc_stock_order_study.py"
SOURCE = ROOT / SOURCE_PATH
ATTRIBUTES = ROOT / "research" / ".gitattributes"
FROZEN_SHA256 = "c80ff4f585d59d1b8e4ecd0d6199605fee727de9df0a13b74e987fe4d2819f87"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkout(tmp_path: Path, attributes: bytes) -> tuple[bytes, bytes]:
    git = shutil.which("git")
    assert git is not None, "Git is required to verify checkout semantics"
    # Normalize only this test's captured input, then verify the external frozen
    # pin. Production consumers must still reject nonidentical working bytes.
    frozen = SOURCE.read_bytes().replace(b"\r\n", b"\n")
    assert _sha(frozen) == FROZEN_SHA256
    repository = tmp_path / "repository"
    repository.mkdir()
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        if name in os.environ
    }
    environment.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    })

    def run(*arguments: str) -> None:
        result = subprocess.run(
            [git, *arguments], cwd=repository, env=environment,
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (arguments, result.stderr)

    run("init", "--quiet")
    run("config", "core.autocrlf", "true")
    run("config", "core.eol", "crlf")
    run("config", "core.longpaths", "true")
    run("config", "core.attributesFile", os.devnull)
    research = repository / "research"
    research.mkdir()
    (research / ".gitattributes").write_bytes(attributes)
    (repository / SOURCE_PATH).write_bytes(frozen)
    # The exact Insider rule must not change a sibling lane's checkout policy.
    sibling = research / "unrelated_lane.py"
    sibling.write_bytes(b"# invented sibling\nvalue = 1\n")
    run("add", "--", "research")
    output = tmp_path / "materialized"
    output.mkdir()
    run("checkout-index", "--all", "--prefix=" + str(output) + os.sep)
    return (output / SOURCE_PATH).read_bytes(), (output / "research" / sibling.name).read_bytes()


def test_working_candidate_is_the_exact_frozen_source() -> None:
    assert _sha(SOURCE.read_bytes()) == FROZEN_SHA256


def test_windows_style_checkout_preserves_insider_pin_and_sibling_policy(tmp_path: Path) -> None:
    candidate, sibling = _checkout(tmp_path, ATTRIBUTES.read_bytes())
    assert _sha(candidate) == FROZEN_SHA256
    assert b"\r" not in candidate
    assert sibling == b"# invented sibling\r\nvalue = 1\r\n"


@pytest.mark.parametrize("removed_policy", (b"", b"/unrelated_lane.py text eol=lf\n"))
def test_missing_or_wrong_file_rule_recreates_the_byte_pin_failure(tmp_path: Path, removed_policy: bytes) -> None:
    candidate, _ = _checkout(tmp_path, removed_policy)
    assert b"\r\n" in candidate
    assert _sha(candidate) != FROZEN_SHA256
