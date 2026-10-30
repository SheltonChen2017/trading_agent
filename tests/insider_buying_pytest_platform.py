"""Explicit Insider test collection support without changing frozen images.

Run from the lane root with ``python tests/insider_buying_pytest_platform.py
<focused pytest arguments>``. The normal shared pytest
configuration is unchanged. This is collection policy, not a Windows custody
port: on hosts without fcntl only the 17 exact byte-frozen POSIX test images are
ignored. Their hashes must still match; supported POSIX hosts select them all.
No acquisition, credentials, private inputs, or custody root is executed here.
The caller must still apply the required native isolation for running tests.
"""
from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import re
import sys
from types import MappingProxyType

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Exact pre-review images, also bound by the unchanged production custody fronts.
FROZEN_POSIX_TEST_SHA256 = MappingProxyType({'tests/test_insider_buying_pilot_sec_roster.py': '914fb29161d87c5553be4b3bc1546356e57908afff3dd31e089589e68c2f83aa',
 'tests/test_insider_buying_sec_feed_compact_capture_v1_review.py': 'd35f0f20a8fc0e72c12d7f286cf85d856f7fe4868447052ec9cc5a99ead63f32',
 'tests/test_insider_buying_sec_feed_compact_members_v1.py': '8f1619084ada77eb12165f6875643f6814902ca2ec2efc29e4213a9c06b3a1ea',
 'tests/test_insider_buying_sec_feed_compact_members_v1_review.py': 'c9ef1c02577da1efaf50f765249b0898d329634ff706a4b126ee1c1e7ed13951',
 'tests/test_insider_buying_sec_feed_format_v3.py': '4057b4764abdaae73bbe822aa5ec992d1db2922b4fce294b308f57743bfebb45',
 'tests/test_insider_buying_sec_feed_nc_route_v1.py': '430453b568a9034aba08475a8eb8e05d7c87e1cc48ed79dafb38761c6ab212eb',
 'tests/test_insider_buying_sec_feed_nc_route_v1_review.py': 'b76815992a26b3f5c4816213a70c8ee21590ad09296692e7d3fc137402e070c0',
 'tests/test_insider_buying_sec_feed_nc_source_binding_v1.py': 'a3f724d471ccc10a7c6718a860a1bc86a73e84e1debe94ee1340e95f13ddb457',
 'tests/test_insider_buying_sec_feed_prefix_capture_v1.py': '00f1eae23b522cc806729912210c41199bfbd6ada925e8d749a8dc2ff9de08f6',
 'tests/test_insider_buying_sec_feed_prefix_capture_v1_review.py': '075799f50570e79b832585e944e57d07cbc06df56b4a3793b5e9ebc1b0792727',
 'tests/test_insider_buying_sec_feed_prefix_format_v1.py': '371c8163f3ddfdec650ecafc7455948bbdfd68ac60d63b468f4c0bb031c54fe0',
 'tests/test_insider_buying_sec_feed_prefix_format_v1_review.py': 'bffac22873a10f2a41cbda4e827dded44bf3c7b2f29ad22d3fc80fc96af38050',
 'tests/test_insider_buying_sec_feed_prefix_nc_observe_v1.py': '7fb1bd8ea5626595defdb2ad7ec94dd14d5008b98cafef7ce156a560028da107',
 'tests/test_insider_buying_sec_feed_prefix_shape_runner_v1.py': 'db1591265cc04351e8bc966f3eab29f24cb18c004321989f8665d9f87ea7f609',
 'tests/test_insider_buying_sec_feed_prefix_shape_runner_v1_review.py': '6b496f5edaf28803aecb879f28a121be938863d897f8451f2db1c4b88437e82f',
 'tests/test_insider_buying_sec_feed_prefix_shape_v1.py': '67b7b2923a487cd9de557038c7da4032ece254c3d8262a3518546af901fca6d4',
 'tests/test_insider_buying_sec_feed_prefix_shape_v1_review.py': 'e89588779f44038aa09eb8fa5dd957b612adfb038fdace388057de2999c5d498'} )
_EXPECTED_PATHS = frozenset(FROZEN_POSIX_TEST_SHA256)


def _validate_contract(pins):
    if not isinstance(pins, (dict, type(FROZEN_POSIX_TEST_SHA256))) or set(pins) != _EXPECTED_PATHS:
        raise pytest.UsageError("Insider frozen POSIX test scope changed")
    for relative, digest in pins.items():
        if (not isinstance(relative, str) or Path(relative).parts != ("tests", Path(relative).name)
                or not re.fullmatch(r"test_insider_buying_[a-z0-9_]+\.py", Path(relative).name)
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise pytest.UsageError("Insider frozen POSIX test contract malformed")


def _validate_frozen_images(root=ROOT, pins=FROZEN_POSIX_TEST_SHA256):
    _validate_contract(pins)
    root = Path(root).resolve()
    for relative, digest in pins.items():
        path = root / relative
        try:
            valid = (not path.is_symlink() and path.resolve() == root / relative
                     and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest)
        except OSError:
            valid = False
        if not valid:
            raise pytest.UsageError("Insider frozen POSIX test image changed: " + relative)


def _fcntl_available():
    try:
        importlib.import_module("fcntl")
    except ModuleNotFoundError as error:
        if error.name != "fcntl":
            raise
        return False
    return True


def _skip_frozen_path(collection_path, *, missing_fcntl):
    if type(missing_fcntl) is not bool:
        raise pytest.UsageError("Insider platform decision must be an exact boolean")
    if not missing_fcntl:
        return None
    path = Path(collection_path)
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        return None
    if relative not in FROZEN_POSIX_TEST_SHA256:
        return None
    # Reject changed bytes even if this helper is invoked without session setup.
    _validate_frozen_images()
    return True


def pytest_configure(config):
    _validate_frozen_images()


def pytest_ignore_collect(collection_path, config):
    return _skip_frozen_path(collection_path, missing_fcntl=not _fcntl_available())


class _FrozenUnsupportedHost(pytest.Module):
    def collect(self):
        pytest.skip("IBWIN-CR01: byte-frozen POSIX custody image; Windows custody port deferred",
                    allow_module_level=True)


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path, parent):
    # Explicit file arguments bypass pytest_ignore_collect. Stop before their
    # ordinary Module collector can import a frozen POSIX image as well.
    if _skip_frozen_path(module_path, missing_fcntl=not _fcntl_available()):
        return _FrozenUnsupportedHost.from_parent(parent, path=module_path)
    return None


def main(arguments=None):
    if Path.cwd().resolve() != ROOT:
        raise SystemExit("Run the Insider test launcher from its lane root")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return pytest.main(sys.argv[1:] if arguments is None else arguments,
                       plugins=[sys.modules[__name__]])


if __name__ == "__main__":
    raise SystemExit(main())
