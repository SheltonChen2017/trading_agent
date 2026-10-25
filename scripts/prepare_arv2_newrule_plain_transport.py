"""One offline plain-data preparation; never credentials, QC, upload or launch.

Run only under the separately recorded native network/write-denied command.
The exclusive claim precedes private input reads. A failed/ambiguous claim is
spent. Only metadata is retained; later consumers must freshly authenticate
their bytes against this preparation's externally frozen identities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import types

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_newrule_comparison as frozen

SOURCE = ROOT / 'scripts/prepare_arv2_newrule_plain_transport.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_plain_transport/R322-20261025-A'
SCHEMA = 'arv2-newrule-plain-preparation-v1'
DEADLINE_SECONDS = 180
MAX_FILE = 128 * 1024
NEW_PINS = {
    'newrule_plain_transport.py': '4cf351095015fddb7a463692f6d789917d229966772e04a60de0c804ed965f5a',
    'newrule_plain_input_runtime.py': 'bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f',
    'newrule_plain_projection.py': 'a0152d0d4109584312ee1e5a2f91cc03bf97cbab6b0e2525dd4f968fa9bd9927',
}
ADDITIONAL_PINS = {
    'scripts/run_arv2_newrule_comparison.py': '533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05',
    'scripts/arv2_r298_recovery_evidence.py': 'dc41adea9285671d2c39a1ee0afbfa517a3641d9fdaa49a2ea77cc44c4d759d3',
}
FALSE_FLAGS = ('qc_contact', 'provider_contact', 'strategy_launch', 'point_in_time_proven',
               'formal_forward_ready', 'paper_or_live_ready')
STAGES = ('preflight', 'claiming', 'source_authentication', 'plain_conversion',
          'projection', 'publication', 'complete')
FAILURES = ('preflight', 'source_pin', 'host', 'git_state', 'claim', 'control',
            'control_changed', 'bound', 'json', 'deadline', 'plain_refused',
            'projection_refused', 'source_refused', 'os_error', 'unknown_exception')


class Refused(ValueError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('ascii') + b'\n'
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refused('json') from None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'source_pin')
    return value


def metadata(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, 'st_flags', None))


def parse(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'json')
            out[key] = value
        return out
    require(type(raw) is bytes and 0 < len(raw) <= MAX_FILE, 'bound')
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('json') from None
    require(type(value) is dict and canonical(value) == raw, 'json')
    return value


class Store:
    """New fixed private leaf with exclusive, retained claim/report descriptors."""

    def __init__(self):
        self.chain, self.files, self.fd = [], [], None
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        require(here != CONTROL, 'claim')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                info = os.fstat(fd)
                self.chain.append((info.st_dev, info.st_ino))
            self.fd = fd
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for _, fd, _ in self.files:
            os.close(fd)
        os.close(self.fd)

    def verify(self):
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part, identity in zip(CONTROL.parts[1:], self.chain):
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                info = os.fstat(fd)
                require((info.st_dev, info.st_ino) == identity, 'control_changed')
            held, named = os.fstat(self.fd), os.fstat(fd)
            names = os.listdir(fd)
            require(metadata(held) == metadata(named) and held.st_uid == os.getuid()
                    and stat.S_IMODE(held.st_mode) == 0o700
                    and set(names) == {name for name, _, _ in self.files}
                    and held.st_nlink == 2 + len(names), 'control')
            for name, leaf, baseline in self.files:
                require(metadata(os.fstat(leaf)) == baseline
                        == metadata(os.stat(name, dir_fd=fd, follow_symlinks=False)), 'control_changed')
            require(metadata(named) == metadata(os.fstat(fd)), 'control_changed')
        finally:
            os.close(fd)

    def write(self, name, value):
        self.verify()
        require(name in ('claim.json', 'report.json') and name not in {row[0] for row in self.files}, 'control')
        raw = canonical(value)
        require(type(value) is dict and 0 < len(raw) <= MAX_FILE, 'bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                require(count > 0, 'control')
                view = view[count:]
            os.fsync(fd)
            os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                    and info.st_uid == os.getuid() and info.st_nlink == 1
                    and info.st_size == len(raw), 'control')
            os.lseek(fd, 0, os.SEEK_SET)
            reread = bytearray()
            while len(reread) <= len(raw):
                piece = os.read(fd, min(65536, len(raw) + 1 - len(reread)))
                if not piece:
                    break
                reread.extend(piece)
            require(bytes(reread) == raw and parse(bytes(reread)) == value
                    and metadata(info) == metadata(os.fstat(fd)), 'control_changed')
            self.files.append((name, fd, metadata(info)))
        except BaseException:
            os.close(fd)
            raise
        self.verify()
        return {'sha256': sha(raw), 'byte_count': len(raw)}


def selected_pins():
    return {**dict(frozen.SOURCE_PINS), **ADDITIONAL_PINS,
            **{'research/analyst_revisions_v2_qc/' + name: pin for name, pin in NEW_PINS.items()}}


def profile():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': frozen.BRANCH,
            'python': str(frozen.PYTHON), 'control': str(CONTROL),
            'source_package_sha256': frozen.PACKAGE_SHA256,
            'source_lineage_sha256': frozen.LINEAGE_SHA256,
            'source_pins': selected_pins(), 'deadline_seconds': DEADLINE_SECONDS,
            'max_report_bytes': MAX_FILE, 'max_plain_bytes': 44 * 1024 * 1024,
            'attempt_consumed_at_exclusive_claim': True,
            **dict.fromkeys(FALSE_FLAGS, False)}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
            'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile()))}


def preflight(args, deadline):
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
            and Path(sys.executable) == frozen.PYTHON and Path.cwd() == ROOT
            and ROOT.resolve() == ROOT and Path(__file__).absolute() == SOURCE, 'host')
    require('pytest' not in sys.modules and 'PYTEST_CURRENT_TEST' not in os.environ, 'preflight')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head), 'git_state')
    digest(args.caller_sha256)
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
                              (['branch', '--show-current'], frozen.BRANCH),
                              (['rev-parse', 'HEAD'], args.expected_head),
                              (['status', '--porcelain'], '')):
        result = subprocess.run(['git', *command], cwd=ROOT, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=min(3, frozen.helpers._remaining(deadline)))
        require(result.returncode == 0 and not result.stderr
                and result.stdout.decode('ascii').strip() == expected, 'git_state')
    for relative, pin in selected_pins().items():
        require(frozen.helpers._source_digest(ROOT / relative) == digest(pin), 'source_pin')
    require(frozen.helpers._source_digest(SOURCE) == args.caller_sha256, 'source_pin')
    frozen.helpers._remaining(deadline)


def construct(deadline):
    from scripts import arv2_r298_recovery_evidence as evidence
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    from research.analyst_revisions_v2_qc import newrule_plain_transport as transport
    from research.analyst_revisions_v2_qc import newrule_plain_projection as projection
    value = frozen.prepared_input.october.load_october_order_input_package(frozen.PACKAGE,
        expected_package_sha256=frozen.PACKAGE_SHA256, lineage_path=frozen.LINEAGE,
        expected_lineage_sha256=frozen.LINEAGE_SHA256)
    package = old._input(value)
    frozen.helpers._remaining(deadline)
    plain = transport.build_plain_transport(package, expected_package_sha256=frozen.PACKAGE_SHA256,
                                            expected_lineage_sha256=frozen.LINEAGE_SHA256)
    parent = evidence.reconstruct_projection()
    names = (*NEW_PINS, 'accepted_risk_six_universe_order_qc_projection.py')
    sources = {name: (evidence.SOURCE_ROOT / name).read_bytes() for name in names}
    projected = projection.build_plain_projection(parent, plain, sources=sources,
                                                   expected_new_source_pins=dict(NEW_PINS))
    frozen.helpers._remaining(deadline)
    return plain, projected


def finite(error):
    if type(error) is Refused and len(error.args) == 1 and type(error.args[0]) is str and error.args[0] in FAILURES:
        return error.args[0]
    if type(error) is frozen.helpers.Deadline:
        return 'deadline'
    # Exact known classes only; never format opaque exception objects.
    # A failed preflight must not import the very module whose pin failed.
    for name, class_name, label in (
        ('newrule_plain_transport', 'PlainTransportError', 'plain_refused'),
        ('newrule_plain_projection', 'PlainProjectionError', 'projection_refused')):
        module = sys.modules.get('research.analyst_revisions_v2_qc.' + name)
        if type(module) is types.ModuleType and type(error) is vars(module).get(class_name):
            return label
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


SUMMARY_HASHES = ('package_sha256', 'projection_sha256', 'profile_sha256',
                  'activation_sha256', 'parent_proof_sha256')


def summary(plain, projected):
    return {'package_sha256': plain.package_sha256,
            'projection_sha256': projected.projection_sha256,
            'profile_sha256': json.loads(projected.profile_bytes)['profile_sha256'],
            'activation_sha256': plain.activation_manifest_sha256,
            'parent_proof_sha256': plain.parent_proof_sha256,
            'object_count': len(plain.upload_objects),
            'total_byte_count': plain.total_upload_byte_count}


def validate_output(raw, *, actual_exit, expected_binding):
    """Validate externally captured finite stdout; never reopen an artifact.

    Exit is the invoking process's observed exit, not inferred from report text.
    This validates preparation evidence, never storage or QC admission.
    """
    require(type(actual_exit) is int and actual_exit in (0, 2)
            and type(raw) is bytes and 0 < len(raw) <= 4096
            and raw.endswith(b'\n\n'), 'bound')
    value = parse(raw[:-1])
    require(type(expected_binding) is dict
            and set(expected_binding) == {'schema', 'expected_head', 'caller_sha256', 'profile_sha256'}
            and expected_binding['schema'] == SCHEMA
            and all(value.get(key) == item for key, item in expected_binding.items()), 'preflight')
    require(set(value) == set(expected_binding) | {'complete', 'failure_code', 'report',
                    'attempt_consumed', 'summary', *FALSE_FLAGS}
            and type(value['complete']) is bool and value['attempt_consumed'] is True
            and all(value[key] is False for key in FALSE_FLAGS), 'json')
    require(type(value['report']) is dict and set(value['report']) == {'sha256', 'byte_count'}
            and type(value['report']['byte_count']) is int
            and 0 < value['report']['byte_count'] <= MAX_FILE, 'bound')
    digest(value['report']['sha256'])
    if value['complete']:
        require(actual_exit == 0 and value['failure_code'] is None, 'preflight')
        item = value['summary']
        require(type(item) is dict and set(item) == {*SUMMARY_HASHES, 'object_count', 'total_byte_count'}, 'json')
        for key in SUMMARY_HASHES:
            digest(item[key])
        require(type(item['object_count']) is int and 6 <= item['object_count'] <= 96
                and type(item['total_byte_count']) is int
                and 0 < item['total_byte_count'] <= 44 * 1024 * 1024, 'bound')
    else:
        require(actual_exit == 2 and value['summary'] is None
                and type(value['failure_code']) is str and value['failure_code'] in FAILURES, 'json')
    return value


def run(args):
    deadline, stage = time.monotonic() + DEADLINE_SECONDS, 'preflight'
    try:
        with frozen.helpers._alarm(deadline):
            preflight(args, deadline)
            stage = 'claiming'
            with Store() as store:
                store.write('claim.json', {**binding(args), 'attempt_consumed': True,
                            **dict.fromkeys(FALSE_FLAGS, False)})
                stage = 'source_authentication'
                try:
                    plain, projected = construct(deadline)
                    result = {'complete': True, 'failure_code': None,
                              'transport': plain.to_record(), 'projection': projected.to_record()}
                    safe_summary = summary(plain, projected)
                except BaseException as error:
                    result = {'complete': False, 'failure_code': finite(error)}
                    safe_summary = None
                stage = 'publication'
                report = {**binding(args), **result, 'attempt_consumed': True,
                          **dict.fromkeys(FALSE_FLAGS, False)}
                pin = store.write('report.json', report)
                # A successful report alone is never authority: require this actual exit.
                preflight(args, deadline)
                store.verify()
                envelope = {**binding(args), 'complete': result['complete'],
                            'failure_code': result['failure_code'], 'report': pin,
                            'summary': safe_summary, 'attempt_consumed': True,
                            **dict.fromkeys(FALSE_FLAGS, False)}
                raw = canonical(envelope)
                require(len(raw) <= 4096, 'bound')
                print(raw.decode('ascii'))
                return 0 if result['complete'] else 2
    except BaseException as error:
        print(canonical({'schema': SCHEMA, 'complete': False, 'stage': stage,
                         'failure_code': finite(error), 'attempt_consumed': None,
                         **dict.fromkeys(FALSE_FLAGS, False)}).decode('ascii'))
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
