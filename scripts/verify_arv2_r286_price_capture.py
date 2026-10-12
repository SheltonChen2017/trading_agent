"""Once-only R286 output receipt check; no source admission or native ACL policy."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time
from datetime import datetime, timezone

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
PARENT = ROOT / 'artifacts/analyst_revisions_v2/sharadar_price_capture'
SESSION = '2026-10-09'
CUTOFF = datetime(2026, 10, 12, 13, 20, tzinfo=timezone.utc)
TRANSPORT = 'sharadar_raw_close_direct_https_owned_session'
FILES = {'stocks.csv': 1048576, 'funds.csv': 1048576,
         'manifest.json': 32768, 'manifest.sha256': 65}
PINS = {
    'scripts/capture_arv2_sharadar_prices.py': 'e33ba763d1c4d8249ebbf8d8e77a5d91069f9f9bf533fb3eee34114157badf9a',
    'scripts/capture_arv2_sharadar.py': '17e516b4cc721c7f97c4690f54dfcc9d2d11d8cebd413100f2e2ffa68e663ca2',
    'research/analyst_revisions_v2/canonical.py': 'c1d1d1aab633b16868fccc371de7c4cf4f3a692943e04a8d785109110e17ae6e',
}
HASH = re.compile(r'[0-9a-f]{64}\Z')
LEAF = re.compile(r'arv2-sharadar-prices-[0-9]{8}T[0-9]{12}Z\Z')
STAMP = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z')


class Refusal(ValueError):
    pass


def require(value):
    if not value:
        raise Refusal('fresh price receipt refused')


def utc(value):
    require(type(value) is str and STAMP.fullmatch(value) is not None)
    try:
        return datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError:
        raise Refusal('fresh price receipt refused') from None


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def meta(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, 'st_flags', 0))


def ancestor(info):
    return meta(info)[:5]


def regular(info, maximum):
    require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_uid == os.getuid() and info.st_nlink == 1
            and 0 < info.st_size <= maximum)


@contextlib.contextmanager
def budget():
    # Cooperative signal and elapsed-return checks, not hard native interruption.
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0))
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise Refusal('fresh price receipt refused')
    deadline = time.monotonic() + 15
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 15)
    try:
        yield
        require(time.monotonic() < deadline)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def check_code():
    for relative, expected in PINS.items():
        path = ROOT / relative
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 2097152)
            raw = bytearray()
            while len(raw) <= 2097152:
                chunk = os.read(fd, min(65536, 2097153 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            require(len(raw) == before.st_size and len(raw) <= 2097152
                    and meta(os.fstat(fd)) == meta(before)
                    and meta(os.stat(path, follow_symlinks=False)) == meta(before)
                    and hashlib.sha256(raw).hexdigest() == expected)
        finally:
            os.close(fd)


def module():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import scripts.capture_arv2_sharadar_prices as adapter
    require(Path(adapter.__file__).absolute() == ROOT / 'scripts/capture_arv2_sharadar_prices.py')
    require(Path(adapter.source.__file__).absolute() == ROOT / 'scripts/capture_arv2_sharadar.py')
    return adapter


class Envelope:
    def __init__(self, path):
        self.path = path
        self.stack = contextlib.ExitStack()
        self.chain = []
        self.leaves = []

    def own(self, descriptor):
        self.stack.callback(os.close, descriptor)
        return descriptor

    def __enter__(self):
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
            fd = self.own(os.open('/', flags))
            self.chain.append((None, fd, ancestor(os.fstat(fd))))
            current = Path('/')
            for part in self.path.parts[1:]:
                fd = self.own(os.open(part, flags, dir_fd=fd))
                current /= part
                info = os.fstat(fd)
                require(stat.S_ISDIR(info.st_mode))
                if current in (PARENT, self.path):
                    require(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid())
                self.chain.append((part, fd, ancestor(info)))
            self.directory = fd
            self.directory_meta = meta(os.fstat(fd))
            self.inventory()
            for name, maximum in sorted(FILES.items()):
                child = self.own(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                        dir_fd=fd))
                info = os.fstat(child)
                regular(info, maximum)
                require(meta(os.stat(name, dir_fd=fd, follow_symlinks=False)) == meta(info))
                self.leaves.append((name, child, meta(info), maximum))
            self.recheck()
            return self
        except BaseException:
            self.stack.close()
            raise

    def inventory(self):
        names = os.listdir(self.directory)
        require(len(names) == 4 and set(names) == set(FILES))

    def recheck(self):
        for index, (part, fd, original) in enumerate(self.chain):
            require(ancestor(os.fstat(fd)) == original)
            if index:
                named = os.stat(part, dir_fd=self.chain[index - 1][1], follow_symlinks=False)
                require(ancestor(named) == original)
        require(meta(os.fstat(self.directory)) == self.directory_meta)
        for name, fd, original, maximum in self.leaves:
            held = os.fstat(fd)
            named = os.stat(name, dir_fd=self.directory, follow_symlinks=False)
            regular(held, maximum)
            regular(named, maximum)
            require(meta(held) == original and meta(named) == original)
        self.inventory()

    def __exit__(self, *_):
        self.stack.close()


def verify(artifact, manifest_hash, capture_hash, started, ended, capture_exit):
    # All argument checks precede imports, code pin reads, or capture opens.
    require(type(artifact) is str and type(manifest_hash) is str and type(capture_hash) is str)
    require(HASH.fullmatch(manifest_hash) is not None and HASH.fullmatch(capture_hash) is not None)
    path = Path(artifact)
    require(path.is_absolute() and str(path) == artifact and '..' not in path.parts
            and path.parent == PARENT and LEAF.fullmatch(path.name) is not None)
    require(type(capture_exit) is int and capture_exit == 0)
    beginning, ending = utc(started), utc(ended)
    read_start = now()
    require(beginning <= ending <= read_start < CUTOFF)
    with budget():
        check_code()
        adapter = module()
        with Envelope(path) as envelope:
            loaded = adapter.load_sharadar_price_capture(path, expected_manifest_sha256=manifest_hash)
            require(type(loaded) is adapter.LoadedSharadarPriceCapture)
            require(loaded.artifact_path == path and loaded.manifest_sha256 == manifest_hash
                    and loaded.capture_sha256 == capture_hash and loaded.close_session == SESSION
                    and loaded.capture_transport == TRANSPORT)
            require(tuple((row.role, row.csv_file, row.row_count) for row in loaded.responses)
                    == (('stocks', 'stocks.csv', 1), ('funds', 'funds.csv', 6)))
            require(type(loaded.responses) is tuple and all(
                type(row) is adapter.PriceCsvBinding and type(row.row_count) is int
                and type(row.csv_byte_count) is int and 0 < row.csv_byte_count <= 1048576
                and type(row.csv_sha256) is str and HASH.fullmatch(row.csv_sha256) is not None
                for row in loaded.responses))
            source_start, source_end = utc(loaded.capture_started_at), utc(loaded.capture_completed_at)
            require(beginning <= source_start <= source_end <= ending < CUTOFF)
            envelope.recheck()
            check_code()
            envelope.recheck()
            read_end = now()
            require(read_start <= read_end < CUTOFF)
            result = {
                'manifest_sha256': manifest_hash, 'capture_sha256': capture_hash,
                'close_session': SESSION, 'stock_rows': 1, 'fund_rows': 6,
                'responses': [{'role': row.role, 'csv_file': row.csv_file,
                               'csv_sha256': row.csv_sha256, 'csv_byte_count': row.csv_byte_count,
                               'row_count': row.row_count} for row in loaded.responses],
                'file_count': 4, 'capture_started_at': loaded.capture_started_at,
                'capture_completed_at': loaded.capture_completed_at,
                'invocation_started_at': started, 'invocation_successful_end': ended,
                'read_started_at': stamp(read_start), 'read_completed_at': stamp(read_end),
                'readback_authenticated': True,
                'native_acl_xattr_authenticated': False, 'continuous_stability_proven': False,
                'signed_clock_authenticated': False, **{flag: False for flag in adapter.FALSE_FLAGS},
            }
    final_end = now()
    require(read_end <= final_end < CUTOFF)
    result['read_completed_at'] = stamp(final_end)
    return result


def main(argv=None):
    try:
        values = list(sys.argv[1:] if argv is None else argv)
        names = ('--artifact', '--manifest-sha256', '--capture-sha256',
                 '--started-at', '--ended-at', '--capture-exit')
        require(len(values) == 12 and tuple(values[::2]) == names and values[-1] == '0')
        result = verify(*values[1:-1:2], 0)
        print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
        return 0
    except BaseException:
        print('fresh price receipt refused', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
