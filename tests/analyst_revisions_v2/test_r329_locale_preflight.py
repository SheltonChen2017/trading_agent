"""Prospective locale correction; never dispatches an operational A/B caller."""
import json
import os
import subprocess
import sys

import pytest

from scripts import arv2_r329_bounded_process as process


def test_injected_lc_ctype_refuses_before_source_or_child(monkeypatch):
    policy = '(version 1)(allow default)(deny network*)(deny process-exec (literal "/usr/bin/security"))'
    spec = {'schema': process.SCHEMA, 'operation': 'stage', 'expected_head': 'a'*40,
        'caller_sha256': 'a'*64, 'profile_sha256': 'b'*64, 'native_policy': policy,
        'native_policy_sha256': process.sha(policy.encode()), 'extra_args': []}
    monkeypatch.setattr(os, 'environ', {'PATH': '/usr/bin:/bin', 'LC_CTYPE': 'UTF-8',
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        'TMPDIR': str(process.ROOT / '.pytest_cache/r329-root/tmp'),
        'PYTHONPYCACHEPREFIX': str(process.ROOT / '.pytest_cache/r329-root/pycache')})
    monkeypatch.setattr(os, 'open', lambda *a, **kw: pytest.fail('source open'))
    monkeypatch.setattr(process, 'collect', lambda *a, **kw: pytest.fail('dispatch'))
    with pytest.raises(process.Refused):
        process.run(spec, process.sha(process.canonical(spec)))


def test_explicit_c_locale_prevents_python_environment_injection():
    environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'TMPDIR': str(process.ROOT / '.pytest_cache/r329-root/tmp'),
        'PYTHONPYCACHEPREFIX': str(process.ROOT / '.pytest_cache/r329-root/pycache')}
    result = subprocess.run([sys.executable, '-B', '-c',
        'import json,os;print(json.dumps({"names":sorted(os.environ),"locale":os.environ.get("LC_ALL")}))'], cwd=process.ROOT,
        env=environment, stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0 and not result.stderr
    value = json.loads(result.stdout)
    assert value['locale'] == 'C'
    names = value['names']
    assert 'LC_ALL' in names and 'LC_CTYPE' not in names
    assert set(names) <= set(environment) | {'__CF_USER_TEXT_ENCODING'}
