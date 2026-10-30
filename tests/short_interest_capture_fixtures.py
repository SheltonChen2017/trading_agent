"""An explicit host-capability seam for fabricated capture contract tests.

Never use this fixture on protected-filesystem or real-host boundary tests.
It changes only the SI preflight's OS binding, not the process OS or any
ownership, permission, publication, budget, credential or transport helper.
"""
import os

import pytest

from scripts import qualify_finra_short_interest as base_capture


class _FabricatedCapabilities:
    name = "posix"
    O_NOFOLLOW = 1
    O_NONBLOCK = 2

    @staticmethod
    def getuid():
        # Not Windows st_uid=0: accidental protected-I/O reach still refuses.
        return 1000

    def __getattr__(self, name):
        return getattr(os, name)


@pytest.fixture
def portable_capture_platform(monkeypatch, request):
    assert request.node.get_closest_marker("skipif") is None, (
        "the capability seam cannot be used by a protected-filesystem test"
    )
    monkeypatch.setattr(base_capture, "os", _FabricatedCapabilities())
