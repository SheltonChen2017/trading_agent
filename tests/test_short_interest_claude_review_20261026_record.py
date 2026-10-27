"""Counter-review record and fabricated early-refusal regression; no source I/O."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

RECORD = Path(__file__).resolve().parents[1] / "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md"
LOCAL = "## 126. Owner-resumed offline custody repair and last-pre-QC build"
CLAUDE = "## 126. Claude independent review — 2026-10-26 UTC"
CURRENT = "## 127. Codex lane synchronization and counter-review"


def _sha(block):
    return hashlib.sha256((block.rstrip() + "\n").encode()).hexdigest()


def test_both_concurrent_section126_histories_are_preserved_exactly():
    text = RECORD.read_text(encoding="utf-8")
    assert text.index(LOCAL) < text.index(CLAUDE) < text.index(CURRENT)
    local = text[text.index(LOCAL):text.index(CLAUDE)]
    reviewed = text[text.index(CLAUDE):text.index(CURRENT)]
    assert _sha(local) == "c50de43584f63787ddaaf40ebb2086ac6e2485a0c9b6e7863cf890db39091b80"
    assert _sha(reviewed) == "ca65d99691e8bf621558c2b3bb77dc1f19520efce99c636b15e49cbbae95425f"


def test_latest_owner_resource_pause_and_reservation_limit_remain_current():
    text = RECORD.read_text(encoding="utf-8")
    header = " ".join(text.split("Current publication rule", 1)[0].split())
    for value in ("84005", "4GiB", "2036", "QUANTCONNECT PAUSED BY OWNER",
                  "CAPACITY/METADATA", "QC LAUNCH ATTEMPTS0"):
        assert value in header
    current = text.split(CURRENT, 1)[1]
    assert "SI-CCR-20261026-001" in current
    assert "e92e8ab7876e17c039950be26a033309b6ac727f" in current
    assert "20c49ac0fad5eddba251478406dd7af5a04093f0" in current


def test_permanent_full_page_arithmetic_does_not_enlarge_any_budget():
    assert 84005 == 13992 + 67885 + 133 * 16
    assert 67885 == 132 * 512 + 301
    assert (4 * 1024 ** 3 - 23452681) // (2 * 1024 ** 2) == 2036


@pytest.mark.parametrize("missing", ["uid", "nofollow", "nonposix"])
def test_real_cache_constructor_refuses_unsupported_host_before_boundary_or_io(monkeypatch, missing):
    # These imports themselves have POSIX-only dependencies. On this Mac,
    # exercise the ORIGINAL guard with fabricated missing host capabilities;
    # this is not an execution on Windows or a Windows ACL-parity claim.
    pytest.importorskip("resource", reason="protected runtime imports POSIX resource")
    from scripts import capture_short_interest_native_anchor_cache as cache
    from scripts import qualify_finra_short_interest as platform
    fake = SimpleNamespace(name="posix", getuid=lambda: 1000, O_NOFOLLOW=1, O_NONBLOCK=4)
    if missing == "uid": del fake.getuid
    elif missing == "nofollow": del fake.O_NOFOLLOW
    else: fake.name = "nt"
    calls = []
    def denied(*args, **kwargs):
        raise AssertionError("fabricated protected I/O must not be reached")
    with monkeypatch.context() as patch:
        patch.setattr(platform, "os", fake)
        patch.setattr(Path, "resolve", denied)
        patch.setattr(cache.os, "open", denied)
        with pytest.raises(platform.CapturePlatformRefusal, match="protected_capture_platform_unavailable"):
            cache.HeldFiles((Path("/fabricated/not-read"),), protected=True,
                boundary=lambda: calls.append("boundary"))
    assert calls == []
