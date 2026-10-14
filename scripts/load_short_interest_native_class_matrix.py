"""Read the exact saved private source matrix without recapture or new authority.

Root previously authenticated the complete raw chain and applied the frozen
factory. These registered byte pins retain that custody; a saved True flag is
not new proof of a raw chain, source coverage, identity or backtest readiness.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_population_class_matrix as matrix
from scripts.qualify_finra_short_interest import CaptureRefusal, _require_capture_platform
from scripts.qualify_sharadar_companion import _guard
from scripts.qualify_short_interest_action_supplement import _clock, _protected_bytes, _parse_receipt

SOURCE = Path('artifacts/short_interest/native_class_matrix/native-matrix-source-20261014T000048Z')
SOURCE_HEAD = '11d6b300b6737ead079a3a0532b5bfdd693600c5'
SOURCE_PROTOCOL_SHA256 = '073309abf2967fe91b82ff25a4bce54e37dc5fc130e30979902ce32af19007ba'
SOURCE_POLICY_SHA256 = 'feb174469faad72df8b73bb76d825195a5374ef67100a89a95184eb4d08e5436'
MATRIX_SHA256 = 'e570c5b658668f0f9ab087dabbd968d4460294287eba1406ae203882144bc49e'
MODULE_PATH = 'research/short_interest_etf/native_population_class_matrix.py'
HISTORICAL_MODULE_SHA256 = '769d892d9547a746e9e0d3073de8eeed32832481559efdb21b6bc9a888ec25a3'
SOURCE_START = '2026-10-14T00:07:41.209664Z'
SOURCE_COMPLETED = '2026-10-14T00:08:24.753782Z'
SOURCE_MANIFEST_PAYLOAD_SHA256 = '9ab92d072078fc35113f44e96850703558f9709cbf9717301dea8cfc0d98af6e'
SOURCE_PINS = {
    'budget_bytes_sha256': 'a7e5bf8d6d24da777df373f8da2d7f736d98022ce8b53185c726944642dc49cb',
    'child_run': 'artifacts/short_interest/native_population_continuation/native-population-continuation-20261014T000048Z',
    'inventory_sha256': '79560955f5d67927dd9a60803f6ba7fd707ce1e615dcbb45873104392f7bd4e7',
    'report_bytes_sha256': '3b03b5dd3c4526f63b4c8f158e3c779408196c6ea5aec2689721aafd48685416',
    'source_head': SOURCE_HEAD,
}
FILE_PINS = {
    'protocol.private.json': 'd17c61e19b639ec2cfc0c5fac95905aa2e1878eecd53f1f0e6e2a47909b21bc1',
    'started.json': 'b4743537933232c00de94cdb620aa5e3e7c65d6d10f08b137a9c2d48cc680ed3',
    'header.private.json': '149d6a72cf44232f92819041a819c46c35bb69170583c8627e72ed310005ce5e',
    'queries.private.bin': '48aed606d7e768042fa548c0e9de68421de82b15bb2c03f421062b08453792e0',
    'refusals.private.bin': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'completed.json': '1493b6afd72cadc5751cb1b0f4c1ff09bdb9c7ebdcaf266e6bafd74806ca6039',
}
LIMITS = {'protocol.private.json': 65536, 'started.json': 65536, 'completed.json': 65536,
          'header.private.json': 4 * 1024 * 1024,
          'queries.private.bin': 96 * 50000 * 16, 'refusals.private.bin': 96 * 50000 * 24}
COUNTERS = ('provider_requests', 'credential_reads', 'outcome_looks', 'qc_attempts')


class SavedNativeMatrixRefusal(CaptureRefusal):
    pass


def _require(value, code):
    if not value:
        raise SavedNativeMatrixRefusal(code)


def _read(root, path, maximum, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    return _protected_bytes(path, maximum)


def _closed(receipt):
    _require(type(receipt) is dict and all(type(receipt.get(key)) is int and receipt[key] == 0
             for key in COUNTERS), 'saved_matrix_closed_counters')
    _require('backtest_result_exists' not in receipt or receipt['backtest_result_exists'] is False,
             'saved_matrix_no_backtest_claim')


def _policy_definitions(raw):
    tree = ast.parse(raw)
    found = {node.name: ast.dump(node, include_attributes=False) for node in tree.body
             if type(node) is ast.FunctionDef and node.name in {'matrix_policy', '_authority'}}
    _require(set(found) == {'matrix_policy', '_authority'}, 'saved_matrix_historical_policy_definitions')
    return found


def _historical_policy(root, *, head, remote):
    """Authenticate the real historical module, not invented receipt metadata."""
    _require_capture_platform()
    _guard(root, head, remote)
    result = subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE_HEAD, head],
                            cwd=root, capture_output=True, check=False)
    _require(result.returncode == 0, 'saved_matrix_source_not_lane_ancestor')
    _guard(root, head, remote)
    result = subprocess.run(['git', 'show', SOURCE_HEAD + ':' + MODULE_PATH], cwd=root,
                            capture_output=True, check=False)
    _require(result.returncode == 0 and type(result.stdout) is bytes
             and hash_bytes(result.stdout) == HISTORICAL_MODULE_SHA256, 'saved_matrix_historical_module_bytes')
    _guard(root, head, remote)
    current = (root / MODULE_PATH).read_bytes()
    _require(_policy_definitions(current) == _policy_definitions(result.stdout),
             'saved_matrix_historical_policy_changed')
    policy = matrix.matrix_policy()
    _require(hash_payload(policy) == SOURCE_POLICY_SHA256, 'saved_matrix_historical_policy_digest')
    return policy


def load_matrix(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    policy = _historical_policy(root, head=head, remote=remote)
    directory = root / SOURCE
    _guard(root, head, remote)
    _require({path.name for path in directory.iterdir()} == set(FILE_PINS), 'saved_matrix_exact_six_file_inventory')
    files = {}
    for name, digest in FILE_PINS.items():
        raw = _read(root, directory / name, LIMITS[name], head=head, remote=remote)
        _require(type(raw) is bytes and hash_bytes(raw) == digest, 'saved_matrix_registered_file_bytes')
        files[name] = raw
    protocol, start, end = (_parse_receipt(files[name]) for name in
                           ('protocol.private.json', 'started.json', 'completed.json'))
    _closed(protocol)
    _closed(start)
    _closed(end)
    _require(protocol.get('schema') == 'si-native-full-population-matrix-offline-v1'
             and protocol.get('code_head') == SOURCE_HEAD and hash_payload(protocol) == SOURCE_PROTOCOL_SHA256
             and protocol.get('matrix_policy_sha256') == SOURCE_POLICY_SHA256
             and canonical_json(protocol.get('matrix_policy')) == canonical_json(policy)
             and canonical_json(protocol.get('source_pins')) == canonical_json(SOURCE_PINS),
             'saved_matrix_offline_protocol_binding')
    _require(start.get('schema') == 'si-native-full-population-matrix-start-v1'
             and start.get('code_head') == SOURCE_HEAD and start.get('protocol_sha256') == SOURCE_PROTOCOL_SHA256
             and start.get('started_at') == SOURCE_START, 'saved_matrix_start_binding')
    _require(end.get('schema') == 'si-native-full-population-matrix-complete-v1'
             and end.get('status') == 'private_source_matrix_complete' and end.get('code_head') == SOURCE_HEAD
             and end.get('protocol_sha256') == SOURCE_PROTOCOL_SHA256
             and end.get('completed_at') == SOURCE_COMPLETED and end.get('backtest_result_exists') is False,
             'saved_matrix_completion_binding')
    _require(_clock(SOURCE_START) <= _clock(SOURCE_COMPLETED), 'saved_matrix_completion_chronology')
    header = _parse_receipt(files['header.private.json'])
    _require(header.get('source_manifest_bytes_sha256') == SOURCE_PINS['report_bytes_sha256']
             and header.get('source_manifest_payload_sha256') == SOURCE_MANIFEST_PAYLOAD_SHA256
             and header.get('format_policy_sha256') == SOURCE_POLICY_SHA256,
             'saved_matrix_source_manifest_binding')
    _guard(root, head, remote)
    rebuilt = matrix.rebuild_native_population_class_matrix(files['header.private.json'], files['queries.private.bin'],
              files['refusals.private.bin'], MATRIX_SHA256)
    _require(type(rebuilt) is matrix.NativePopulationClassMatrix and rebuilt.sha256 == MATRIX_SHA256,
             'saved_matrix_exact_rebuilt_seal')
    _guard(root, head, remote)
    return rebuilt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--expected-remote', required=True)
    args = parser.parse_args(argv)
    try:
        loaded = load_matrix(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, matrix.NativePopulationMatrixError, ValueError, TypeError, OSError, KeyError):
        print(json.dumps({'status': 'saved_matrix_reload_refused', 'provider_requests': 0,
                          'credential_reads': 0, 'outcome_looks': 0, 'qc_attempts': 0,
                          'backtest_result_exists': False}, sort_keys=True))
        return 2
    print(json.dumps({'status': 'private_saved_matrix_reload_complete', 'matrix_sha256': loaded.sha256,
                      'provider_requests': 0, 'credential_reads': 0, 'outcome_looks': 0,
                      'qc_attempts': 0, 'backtest_result_exists': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
