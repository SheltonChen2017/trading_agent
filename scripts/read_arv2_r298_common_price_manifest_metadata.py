"""One fixed AR manifest read to reconstruct externally pinned public metadata.

This reader never replays the AR operation or reads its report, claim, catalog,
shards, AP inputs, or genuine package. Success reproduces the original metadata
stdout exactly; it grants no source, price, QC transfer or trading admission.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from types import SimpleNamespace

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import prepare_arv2_r298_common_price_sidecar_v2 as ar
from scripts import arv2_r298_ar_retained_binding as anchor
from scripts import arv2_r298_fixed_data_guard as guard_module

SOURCE = ROOT / 'scripts/read_arv2_r298_common_price_manifest_metadata.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AS'
SCHEMA = 'arv2-r298-fixed-AR-manifest-metadata-reconstruction-as-v1'
PYTHON, admitted, environment = ar.PYTHON, ar.admitted, ar.environment
canonical, sha, pin, metadata = ar.canonical, ar.sha, ar.pin, ar.metadata
SECONDS, MAX_OUTPUT = 30, 128 * 1024
AR_SHA256 = '25eec980ccc9dcf9b6e15c7618597bfe050954bd160be6b32f07452e7ed96edc'
FACT_SHA256 = '1c1b2c6729826bd821dafa6d0af70bb406400eb17fc285d05393cb3f37ee19a5'
NEW_PINS = {
    'scripts/prepare_arv2_r298_common_price_sidecar_v2.py': AR_SHA256,
    'scripts/arv2_r298_ar_retained_binding.py': '152213d23bc2188b8dabe6ce2ca8192eabcbecf5f61f87c012738944b0ac1a62',
    'scripts/arv2_r298_fixed_data_guard.py': '00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145'}
FINITE = frozenset(('host','arguments','environment','git_state','source_pin','source_binding',
    'deadline','claim_spent','output_changed','output_security','output_write','output_bound',
    'manifest','reconstruction','actual_proof','os_error','unknown')) | frozenset(
        'guard_' + code for code in guard_module.FINITE)


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is guard_module.Refused: return 'guard_' + guard_module.finite(error)
    if type(error) is environment.EnvironmentRefused: return 'environment'
    if type(error) is admitted.helpers.Deadline: return 'deadline'
    if isinstance(error, OSError): return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= SECONDS, 'deadline')
    return deadline - time.monotonic()


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def retained_context():
    value = anchor.observed_fact()
    require(sha(canonical(value)) == FACT_SHA256
        and anchor.profile_record()['observed_fact_sha256'] == FACT_SHA256, 'source_binding')
    require(value['binding'] == {'schema': ar.SCHEMA,
        'expected_head':'e7f81cddcffd5de82b88095ccdc5493d2a892f7e',
        'caller_sha256':AR_SHA256,
        'profile_sha256':'ff9479819fddba92fcc8b14bf4299aa1c41d435433f624e01c8f7b215e4e611d'}, 'source_binding')
    for role in ('producer','validator'):
        actual = value[role]
        try: ar.ap.public_transport._actual_metadata(actual)
        except BaseException: raise Refused('actual_proof') from None
        require(type(actual['actual_exit']) is int and actual['actual_exit'] == 0
            and actual['bound'] is None and actual['spawn_observed'] is True
            and actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == sha(b'')
            and actual['stdout_bytes'] == 28655 and actual['stdout_sha256']
            == '5c0a070c1d2f03e4a78adb9400db8a94c4d11b334e1a777a7f0fb65a281bc52b', 'actual_proof')
    require(value['technical_sidecar_producer_and_native_validation_passed'] is True
        and value['tool_output_truncated'] is True and value['complete_original_payload_retained'] is False,
        'source_binding')
    for field in ('new_operation_or_read_granted','QC_transfer_granted','price_input_admitted',
            'complete_required_price_coverage_proven','point_in_time_proven','formal_forward_ready','paper_or_live_ready'):
        require(value[field] is False,'source_binding')
    ar.codec.validate_summary(value['codec_summary'])
    ar.source_guard.validate_receipt(value['source_guard_receipt'], ar.anchor.data_plan())
    return value


def data_plan():
    manifest_pin = retained_context()['codec_summary']['manifest_pin']
    return guard_module.checked_plan({'ar_manifest': {
        'relative_path':'artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AR/manifest-private.json',
        **manifest_pin}})


def pins():
    values = ar.pins()
    for name, value in NEW_PINS.items():
        require(_hash(value) and (name not in values or values[name] == value),'source_pin')
        values[name] = value
    return values


def profile_record():
    retained_context()
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),
        'control':str(CONTROL),'python':str(PYTHON),'source_pins':pins(),'seconds':SECONDS,
        'maximum_output_bytes':MAX_OUTPUT,'retained_fact_sha256':FACT_SHA256,'data_plan':data_plan(),
        'source_read_schedule':guard_module.profile_record(data_plan()),
        'purpose':'recover_truncated_public_AR_metadata_by_exact_deterministic_manifest_reconstruction',
        'exclusive_claim_before_manifest_read':True,'byte_pin_before_JSON':True,
        'source_guard_normal_return_before_emission':True,'original_report_and_stdout_pins_both_required':True,
        'success_stdout_is_exact_original_AR_payload':True,'no_AR_operation_or_control_replay':True,
        'original_actual_zero_and_native_validation_required':True,
        'deadline_uninterruptible_IO_host_suspension_qualification':True,
        'old_report_control_catalog_shards_AP_and_genuine_input_read':False,
        'QC_transfer_granted':False,'price_input_admitted':False,'provider_contact':False,
        'credential_access':False,'point_in_time_proven':False,'formal_forward_ready':False,'paper_or_live_ready':False}


def binding(args):
    return {'schema':SCHEMA,'expected_head':args.expected_head,'caller_sha256':args.caller_sha256,
        'profile_sha256':args.profile_sha256}


def preflight(args, deadline):
    require(not admitted.v5._under_test() and sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3,13) and Path(sys.executable) == PYTHON
        and Path.cwd() == ROOT and ROOT.resolve() == ROOT and Path(__file__).absolute() == SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256),'arguments')
    ar._credential_free(); environment._require_environment(); retained_context()
    for cmd, expected in ((['rev-parse','--show-toplevel'],str(ROOT)),
            (['branch','--show-current'],admitted.frozen.BRANCH),(['rev-parse','HEAD'],args.expected_head),
            (['status','--porcelain'],'')):
        require(admitted.v5._git(cmd,deadline).decode('ascii').strip() == expected,'git_state')
    for name, expected in pins().items(): require(sha((ROOT/name).read_bytes()) == expected,'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256
        and sha(admitted.v5._git(['cat-file','blob',args.expected_head+':'+SOURCE.relative_to(ROOT).as_posix()],
            deadline,256*1024)) == args.caller_sha256
        and sha(canonical(profile_record())) == args.profile_sha256,'source_pin')
    remaining(deadline)


def native_profile():
    value = '(version 1)(allow default)(deny network*)'
    value += ''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value += '(deny process-exec (literal "/usr/bin/security"))'
    value += ('(deny file-write* (require-all '
        f'(require-not (subpath "{ROOT / ".pytest_cache"}"))(require-not (literal "/dev/null"))'
        f'(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))))')
    # Pure policy builder only: no genuine package allowance and no old control subtree.
    paths = [ROOT/row['relative_path'] for row in data_plan().values()] + [CONTROL.parent]
    policy = ar.ap.previous._artifact_policy(paths, package=None)
    needle = f'(require-all (subpath "{ROOT / "artifacts"}")'
    require(policy.count(needle) == 1,'source_binding')
    return value + policy.replace(needle,needle+f' (require-not (subpath "{CONTROL}"))',1)


def _security(fd):
    try: return ar.ap.security.snapshot(fd)
    except ar.ap.security.Refusal: raise Refused('output_security') from None


class Store:
    """Two small own files held by original descriptors; no source permission."""
    def __init__(self):
        self.fd, self.chain, self.files = None, [], {}
        fd = os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for index, part in enumerate(CONTROL.parts[1:],1):
                here = Path(*CONTROL.parts[:index+1])
                if here in (CONTROL.parent,CONTROL):
                    try: os.mkdir(part,0o700,dir_fd=fd); os.fsync(fd)
                    except FileExistsError: require(here != CONTROL,'claim_spent')
                nxt = os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd); fd = nxt; self.chain.append((os.fstat(fd).st_dev,os.fstat(fd).st_ino))
            self.fd, self.security = fd, _security(fd); self.verify()
        except BaseException: os.close(fd); raise

    def __enter__(self): return self

    def __exit__(self,*_):
        failed = False
        for row in self.files.values():
            try: os.close(row['fd'])
            except OSError: failed = True
        try: os.close(self.fd)
        except OSError: failed = True
        require(not failed,'output_changed')

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            info = os.fstat(other)
            require(chain == tuple(self.chain) and metadata(info) == metadata(os.fstat(self.fd))
                and _security(self.fd) == self.security and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_uid == os.getuid() and set(os.listdir(other)) == set(self.files),'output_changed')
            for name,row in self.files.items():
                named = os.stat(name,dir_fd=other,follow_symlinks=False)
                require(metadata(named) == row['metadata'] == metadata(os.fstat(row['fd']))
                    and stat.S_ISREG(named.st_mode) and named.st_uid == os.getuid()
                    and named.st_nlink == 1 and stat.S_IMODE(named.st_mode) == 0o600
                    and _security(row['fd']) == row['security'],'output_changed')
        finally: os.close(other)

    def write(self,name,raw):
        self.verify()
        require(name in ('claim.json','result-metadata.json') and name not in self.files
            and len(self.files)<2 and type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT,'output_bound')
        fd = os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        self.files[name] = {'fd':fd,'metadata':metadata(os.fstat(fd)),'security':_security(fd)}
        ar._write(fd,raw); os.fsync(self.fd)
        self.files[name]['metadata'] = metadata(os.fstat(fd)); self.verify()
        reread = os.pread(fd,len(raw)+1,0)
        require(reread == raw,'output_write'); self.verify(); return pin(raw)


def reconstruct(manifest_raw):
    """Pure reconstruction; input bytes were separately authenticated by caller."""
    context = retained_context(); complete = context['codec_summary']
    require(type(manifest_raw) is bytes and pin(manifest_raw) == complete['manifest_pin'],'manifest')
    try: manifest = ar.fmt.loads(manifest_raw,ar.fmt.MAX_MANIFEST_BYTES); ar.fmt.validate_manifest(manifest)
    except BaseException: raise Refused('manifest') from None
    descriptor = ar._manifest_descriptor(manifest)
    receipt = {'schema':ar.SCHEMA+'-output-receipt','catalog_pin':manifest['catalog_pin'],
        'manifest_pin':pin(manifest_raw),'month_pins':[{'byte_count':row['byte_count'],'sha256':row['sha256']}
            for row in manifest['months']],**context['output_metrics']}
    result = {'schema':ar.SCHEMA,'input_binding':ar.source_context()['source_summary']['input_binding'],
        'source_guard_receipt':context['source_guard_receipt'],'codec_summary':complete,
        'manifest_descriptor':descriptor,'output_receipt':receipt,'source_guards_normal_return':True,
        'genuine_input_unchanged':True,'AP_fact_sha256':ar.fmt.AP_FACT_SHA256,
        'AP_source_sha256':ar.fmt.AP_SOURCE_SHA256,'AP_authentication_sha256':ar.fmt.AP_AUTH_SHA256,
        'post_checks_complete':True,**ar.FALSE_FLAGS}
    args = SimpleNamespace(**{key:value for key,value in context['binding'].items() if key!='schema'})
    ar.validate_result(result,args)
    report_raw = canonical({**context['binding'],'result':result})
    require(pin(report_raw) == context['report'],'reconstruction')
    raw = canonical({'binding':context['binding'],'outcome':{'result':result,'report':pin(report_raw)}})+b'\n'
    require(pin(raw) == {'byte_count':context['producer']['stdout_bytes'],
        'sha256':context['producer']['stdout_sha256']}
        == {'byte_count':context['validator']['stdout_bytes'],'sha256':context['validator']['stdout_sha256']},
        'reconstruction')
    ar.validate_output(raw,0,args)
    return raw


def run(args,deadline):
    with Store() as store:
        store.write('claim.json',canonical(binding(args)))
        with guard_module.FixedDataGuard(data_plan(),deadline=deadline) as guard:
            raw = guard.read_all_once()['ar_manifest']; recovered = reconstruct(raw)
            guard.verify(); guard_module.validate_receipt(guard.receipt(),data_plan())
        # No source read or parser occurs beyond this normal-return boundary.
        remaining(deadline); preflight(args,deadline); environment.require_safe_environment(); store.verify()
        store.write('result-metadata.json',canonical({'schema':SCHEMA+'-result',
            'reconstructed_stdout_pin':pin(recovered),'retained_fact_sha256':FACT_SHA256,
            'source_guard_normal_return':True,'original_AR_replayed':False,
            'QC_transfer_granted':False,'price_input_admitted':False}))
        store.verify()
    remaining(deadline)
    return recovered


def failure(args,error):
    return {'schema':SCHEMA+'-failure','binding':binding(args),'failure_code':finite(error),
        'allocation_unknown':True,'original_AR_replayed':False,'QC_transfer_granted':False,
        'price_input_admitted':False,'point_in_time_proven':False,'paper_or_live_ready':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head',required=True);parser.add_argument('--caller-sha256',required=True)
    parser.add_argument('--profile-sha256',required=True);args=parser.parse_args(argv)
    deadline=time.monotonic()+SECONDS
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline);environment._bootstrap_cli_logging();raw=run(args,deadline)
            require(type(raw) is bytes and len(raw)<=MAX_OUTPUT,'output_bound')
            sys.stdout.buffer.write(raw);return 0
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure(args,error))+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
