"""Public-source-only OFF preparation; never a QC or private-evidence command.

Run from the clean designated lane with ``python -m
research.target_price_revisions_qc.extended_off_recovery_cli``. Output is an
inert manifest on stdout. No file is written, permit minted, native adapter
enabled or external resource checked. The recorded owner text is provenance,
not machine-authenticated authority or a later resource-release instruction.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import MappingProxyType

ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions')
BRANCH = 'codex/strategy-target-price-revisions'
PREFIX = 'research/target_price_revisions_qc/'
WITNESS_PATHS = frozenset(PREFIX + name for name in (
    'extended_refusal_witness_controller_successor.py',
    'extended_refusal_witness_runtime_successor.py',
    'extended_refusal_witness_read_design.py',
    'extended_refusal_witness_context_successor.py',
    'extended_refusal_witness_program_successor.py'))
CONTINUATION_PATHS = frozenset(PREFIX + name for name in (
    'extended_native.py', 'extended_core.py', 'extended_runtime_successor.py',
    'extended_compressed_store.py',
    'extended_metrics.py', 'extended_operations.py', 'extended_evidence.py',
    'extended_calendar.json', 'extended_study_freeze.json',
    'extended_source_bundle_completion.json'))
PRODUCER_PATHS = frozenset(PREFIX + name for name in (
    'extended_off_attempt_continuation.py', 'extended_off_recovery_preparation.py',
    'extended_off_recovery_cli.py'))
PUBLIC_LIMITS = MappingProxyType({**dict.fromkeys(WITNESS_PATHS | CONTINUATION_PATHS | PRODUCER_PATHS, 65536),
    PREFIX + 'extended_operations.py': 131072,
    PREFIX + 'extended_study_freeze.json': 16384,
    PREFIX + 'extended_source_bundle_completion.json': 1048576})
PUBLIC_PATHS = frozenset(PUBLIC_LIMITS)
OWNER_INSTRUCTION = (
    "stop the monitor\n"
    "qc/safari is not available at this point.another lane is using it. \n\n"
    "so, build whatever is needed until the last step before qc/safari setup. skip claude review\n"
    "push once when done\n"
    "sync the lane, and counter review claude's changes\n"
    "continue building to the last step before qc. skip claude review for now"
).encode('utf-8')


class PreparationCLIRefusal(ValueError):
    """Fixed refusal without Git output, filenames or underlying exceptions."""


def _fail():
    raise PreparationCLIRefusal('offline OFF preparation refused; no QC or private read attempted') from None


def _git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, stdin=subprocess.DEVNULL,
        capture_output=True, timeout=10, check=False)
    if result.returncode != 0 or len(result.stdout) > 4096:
        _fail()
    try:
        return result.stdout.decode('utf-8').rstrip('\n')
    except UnicodeError:
        _fail()


def observe_repository():
    """Real local observation only; does not fetch or consult any remote ref."""
    if Path(os.path.realpath('.')) != ROOT:
        _fail()
    top = _git('rev-parse', '--show-toplevel')
    branch = _git('branch', '--show-current')
    head = _git('rev-parse', 'HEAD')
    status = _git('status', '--porcelain=v1', '--untracked-files=all')
    if top != str(ROOT) or branch != BRANCH or status:
        _fail()
    return {'physical_root': str(ROOT), 'git_toplevel': top, 'branch': branch,
        'git_head': head, 'status_short': status}


def _public_read(relative, maximum):
    """Read only the fixed public closure through a pinned descriptor chain.

    Pin the physical cwd, then open every relative directory and the leaf with
    no-follow. Revalidate each parent/name identity before and after the read.
    Leaf-only O_NOFOLLOW would still follow a swapped ancestor into a private
    directory. These local checks do not prove Windows ACL or native custody.
    """
    if (type(relative) is not str or relative not in PUBLIC_LIMITS
            or type(maximum) is not int or maximum != PUBLIC_LIMITS[relative]):
        _fail()
    if Path(os.path.realpath('.')) != ROOT:
        _fail()
    fds, links = [], []
    failure = None
    raw = None
    def retain(error):
        nonlocal failure
        if (failure is None or not isinstance(failure, KeyboardInterrupt)
                and (isinstance(error, KeyboardInterrupt)
                    or isinstance(failure, Exception) and not isinstance(error, Exception))):
            failure = error
    def identity(item):
        return item.st_dev, item.st_ino
    def check_chain():
        root_info = os.fstat(fds[0])
        named_root = os.stat(ROOT, follow_symlinks=False)
        if (not stat.S_ISDIR(named_root.st_mode) or identity(root_info) != identity(named_root)
                or Path(os.path.realpath('.')) != ROOT):
            _fail()
        for parent, name, child in links:
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(named.st_mode) or identity(named) != identity(os.fstat(child)):
                _fail()
    try:
        root_fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(root_fd)
        check_chain()
        parent = root_fd
        parts = relative.split('/')
        for name in parts[:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            fds.append(child)
            links.append((parent, name, child))
            check_chain()
            parent = child
        check_chain()
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        fds.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
            _fail()
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(named.st_mode) or identity(named) != identity(before):
            _fail()
        check_chain()
        raw = os.read(fd, maximum + 1)
        after = os.fstat(fd)
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        file_identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns, item.st_nlink)
        if (not stat.S_ISREG(named.st_mode) or len(raw) != before.st_size
                or file_identity(before) != file_identity(after) or file_identity(after) != file_identity(named)):
            _fail()
        check_chain()
    except BaseException as error:
        retain(error)
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except BaseException as error:
                retain(error)
    if failure is not None:
        if isinstance(failure, KeyboardInterrupt):
            raise KeyboardInterrupt('offline public read cancelled') from None
        if not isinstance(failure, Exception):
            raise PreparationCLIStopped('offline public read stopped') from None
        _fail()
    return raw


class PreparationCLIStopped(BaseException):
    """Body-free nonordinary stop; never demoted by descriptor cleanup."""


def build_preparation():
    """Verify before/after public reads; no callback can assert a clean tree."""
    before = observe_repository()
    from . import extended_off_recovery_preparation as preparation
    from . import extended_off_attempt_continuation as continuation
    if (set(preparation.SOURCE_SHA256) != WITNESS_PATHS
            or set(continuation.SOURCE_PINS) != CONTINUATION_PATHS):
        _fail()
    sources = {}
    for relative in sorted(PUBLIC_PATHS):
        if observe_repository() != before:
            _fail()
        sources[relative] = _public_read(relative, PUBLIC_LIMITS[relative])
    witness = preparation.prepare_off_recovery({name: sources[name] for name in WITNESS_PATHS},
        repository_observation=before, owner_instruction=OWNER_INSTRUCTION)
    for relative, expected_hash in continuation.SOURCE_PINS.items():
        if hashlib.sha256(sources[relative]).hexdigest() != expected_hash:
            _fail()
    files, template_raw = continuation.prepare_off_source_bundle(attempt=4,
        completion_bundle_raw=sources[PREFIX + 'extended_source_bundle_completion.json'])
    template = json.loads(template_raw)
    if (template['attempt'] != 4 or template['reservation_sha256'] is not None
            or template['source_hashes'] != {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
            or any(template[key] is not False for key in ('native_permission', 'qc_setup_complete',
                'old_effect_controllers_extended', 'first_refusal_repaired', 'strategy_economics_changed'))
            or template['accepted_metrics'] is not None):
        _fail()
    # Rendered candidate source is kept in memory only. Return its digest report,
    # not code, an allocated look/operation or a claim that the defect is fixed.
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(sources.items())}
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    result = {'schema': 'tpr-ext26-off-pre-qc-bundle-v1', 'mode': 'offline_prepared_native_setup_pending',
        'repository_observation': before, 'owner_instruction_sha256': hashlib.sha256(OWNER_INSTRUCTION).hexdigest(),
        'public_source_hashes': hashes, 'public_source_closure_sha256': hashlib.sha256(canonical(hashes)).hexdigest(),
        'witness_preparation': witness, 'attempt_source_template': template,
        'pending_native': dict(witness['pending_native']), 'authority_granted': False,
        'ready_for_dispatch': False, 'native_binding_proven': False,
        'native_tool_authenticated': False, 'source_units_accepted': False, 'diagnosis_sufficient': False,
        'off_baseline_valid': False, 'on_launch_authorized': False,
        'new_jobs': 0, 'new_codex_attempts': 0, 'new_looks': 0}
    # Re-read the fixed closure, not just Git's stat cache, before reporting.
    for relative, raw in sources.items():
        if observe_repository() != before or _public_read(relative, PUBLIC_LIMITS[relative]) != raw:
            _fail()
    if observe_repository() != before:
        _fail()
    return {**result, 'preparation_sha256': hashlib.sha256(canonical(result)).hexdigest()}


def main(argv=None):
    if (sys.argv[1:] if argv is None else argv):
        print('offline OFF preparation accepts no arguments', file=sys.stderr)
        return 2
    try:
        result = build_preparation()
        print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
        return 0
    except KeyboardInterrupt:
        raise
    except Exception:
        print('offline OFF preparation refused; no QC or private read attempted', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
