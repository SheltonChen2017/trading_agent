"""Invented subprocess bytes only; never read the actual macOS Keychain."""
from dataclasses import FrozenInstanceError
import os
import subprocess
import sys
import time

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: Keychain credential custody requires POSIX process isolation; Windows port deferred",
                allow_module_level=True)

from research import insider_buying_keychain_credentials as m


TOKEN = "invented_keychain_token_1234"
PAIRS = {"fmp": ("trading-agent-fmp", "fmp"),
         "sharadar": ("trading-agent-sharadar", "sharadar"),
         "massive": ("trading-agent-massive", "massive"),
         "eodhd": ("trading-agent-eodhd", "eodhd")}


def factory_for(raw=TOKEN.encode() + b"\n", *, exit_code=0, script=None, calls=None, processes=None):
    code = script or ("import os, sys; os.write(1, " + repr(raw) + "); "
                      "os.write(2, b'invented-private-error'); sys.exit(" + str(exit_code) + ")")
    def factory(argv, **kwargs):
        if calls is not None:
            calls.append((argv, dict(kwargs)))
        process = subprocess.Popen((sys.executable, "-I", "-S", "-B", "-c", code), **kwargs)
        if processes is not None:
            processes.append(process)
        return process
    return factory


@pytest.mark.parametrize("provider", tuple(PAIRS))
def test_exact_pair_and_secret_only_in_returned_value(provider, monkeypatch, capsys):
    monkeypatch.setenv("SHARADAR_API_KEY", "ambient-secret-never-inherited")
    calls, processes = [], []
    result = m.read_keychain_credential(provider, _process_factory=factory_for(calls=calls, processes=processes))
    assert result.provider == provider and result.value == TOKEN and result.fixture_only is True
    assert len(calls) == 1
    argv, options = calls[0]
    service, account = PAIRS[provider]
    assert argv == ("/usr/bin/security", "find-generic-password", "-s", service, "-a", account, "-w")
    assert options == {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
                       "stderr": subprocess.DEVNULL, "shell": False,
                       "env": {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                       "close_fds": True, "bufsize": 0, "start_new_session": True}
    assert TOKEN not in repr(result) + str(result) + repr(calls)
    assert "ambient-secret-never-inherited" not in repr(calls)
    assert capsys.readouterr() == ("", "")
    assert processes[0].poll() == 0 and processes[0].stdout.closed


def test_allowlist_and_result_are_immutable():
    assert dict(m.KEYCHAIN_ITEMS) == PAIRS
    with pytest.raises(TypeError):
        m.KEYCHAIN_ITEMS["eodhd"] = ("evil", "evil")
    result = m.read_keychain_credential("eodhd", _process_factory=factory_for())
    with pytest.raises(FrozenInstanceError):
        result.value = "replacement"


@pytest.mark.parametrize("provider", [None, True, 1, [], {}, "EODHD", "eodhd ", "evil-secret", "eodhd\nsecret"])
def test_unknown_pair_refuses_before_spawn(provider):
    with pytest.raises(m.KeychainCredentialError, match="^keychain_provider_refused$"):
        m.read_keychain_credential(provider, _process_factory=lambda *a, **k: pytest.fail("spawned"))


@pytest.mark.parametrize("raw", [b"", b"\n", b"\r\n", b"secret with space", b"secret\tvalue", b"secret\rvalue",
                               b"secret\nvalue", b"secret\x00value", b"secret\x7fvalue", b"\xffsecret",
                               b"secret\n\n", b"test-api-key", b"TEST-API-KEY\n"])
def test_invalid_keychain_bytes_refuse_without_echo(raw, capsys):
    with pytest.raises(m.KeychainCredentialError, match="^keychain_credential_refused$") as caught:
        m.read_keychain_credential("sharadar", _process_factory=factory_for(raw))
    assert "secret" not in str(caught.value)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("raw", [b"a", b"a\n", b"a" * 4096, b"a" * 4096 + b"\n", b"abc:+/=="])
def test_valid_boundary_and_printable_keys(raw):
    result = m.read_keychain_credential("fmp", _process_factory=factory_for(raw))
    assert result.value.encode() == raw.removesuffix(b"\n")


@pytest.mark.parametrize("raw", [b"a" * 4097, b"a" * 4097 + b"\n", b"a" * 8192])
def test_output_length_refuses_before_unbounded_accumulation(raw):
    expected = "keychain_credential_refused" if len(raw) == 4097 else "keychain_output_oversized"
    processes = []
    with pytest.raises(m.KeychainCredentialError, match="^" + expected + "$"):
        m.read_keychain_credential("massive", _process_factory=factory_for(raw, processes=processes))
    assert processes[0].poll() is not None and processes[0].stdout.closed


@pytest.mark.parametrize("exit_code,disposition", [(44, "keychain_item_missing"),
                         (36, "keychain_access_unavailable"), (51, "keychain_access_unavailable"),
                         (128, "keychain_access_unavailable"), (1, "keychain_read_refused"),
                         (2, "keychain_read_refused"), (255, "keychain_read_refused")])
def test_exit_disposition_discards_any_output(exit_code, disposition, capsys):
    with pytest.raises(m.KeychainCredentialError, match="^" + disposition + "$"):
        m.read_keychain_credential("eodhd", _process_factory=factory_for(exit_code=exit_code))
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("script", ["import time; time.sleep(10)",
                    "import os, time; os.close(1); time.sleep(10)",
                    "import os, time; os.write(1,b'partial'); time.sleep(10)"])
def test_timeout_covers_pipe_read_and_wait_and_reaps_child(monkeypatch, script):
    monkeypatch.setattr(m, "TIMEOUT_SECONDS", 0.10)
    processes = []
    started = time.monotonic()
    with pytest.raises(m.KeychainCredentialError, match="^keychain_read_timeout$"):
        m.read_keychain_credential("eodhd", _process_factory=factory_for(script=script, processes=processes))
    assert time.monotonic() - started < 2
    assert processes[0].poll() is not None and processes[0].stdout.closed


def test_continuous_oversized_writer_is_stopped(monkeypatch):
    monkeypatch.setattr(m, "TIMEOUT_SECONDS", 1)
    processes = []
    script = "import os\nwhile True: os.write(1,b'a'*8192)"
    with pytest.raises(m.KeychainCredentialError, match="^keychain_output_oversized$"):
        m.read_keychain_credential("eodhd", _process_factory=factory_for(script=script, processes=processes))
    assert processes[0].poll() is not None and processes[0].stdout.closed


def test_timeout_stops_descendant_that_holds_pipe(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "TIMEOUT_SECONDS", 0.15)
    descendant = tmp_path / "invented-descendant-pid"
    script = ("import os, time\nchild=os.fork()\nif child==0: time.sleep(10)\n"
              "else:\n open(" + repr(str(descendant)) + ", 'w').write(str(child))\n os._exit(0)")
    processes = []
    with pytest.raises(m.KeychainCredentialError, match="^keychain_read_timeout$"):
        m.read_keychain_credential("eodhd", _process_factory=factory_for(script=script, processes=processes))
    # The process leader exited but its descendant must not keep running.
    pid = int(descendant.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        os.kill(pid, 9)
        pytest.fail("isolated descendant survived timeout cleanup")
    assert processes[0].stdout.closed


def test_actual_keychain_is_macos_only(monkeypatch):
    monkeypatch.setattr(m.sys, "platform", "win32")
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: pytest.fail("actual Keychain"))
    with pytest.raises(m.KeychainCredentialError, match="^macos_keychain_required$"):
        m.read_keychain_credential("eodhd")


@pytest.mark.parametrize("bad_factory", [False, 1, "secret", []])
def test_noncallable_fixture_factory_refuses(bad_factory):
    with pytest.raises(m.KeychainCredentialError, match="^keychain_process_factory_refused$"):
        m.read_keychain_credential("eodhd", _process_factory=bad_factory)


@pytest.mark.parametrize("exception", [OSError("secret"), ValueError("secret"), subprocess.SubprocessError("secret")])
def test_spawn_failure_is_sanitized(exception, capsys):
    def refuse(*args, **kwargs):
        raise exception
    with pytest.raises(m.KeychainCredentialError, match="^keychain_operation_refused$") as caught:
        m.read_keychain_credential("eodhd", _process_factory=refuse)
    assert "secret" not in str(caught.value)
    assert capsys.readouterr() == ("", "")


def test_missing_stdout_or_wrong_process_object_refuses():
    with pytest.raises(m.KeychainCredentialError, match="^keychain_process_refused$"):
        m.read_keychain_credential("eodhd", _process_factory=lambda *a, **k: object())


@pytest.mark.parametrize("exception", [RuntimeError("invented-secret-from-factory"),
                                      m.KeychainCredentialError("invented-secret-from-factory")])
def test_unexpected_or_reconstructed_error_cannot_echo(exception):
    def refuse(*args, **kwargs):
        raise exception
    with pytest.raises(m.KeychainCredentialError, match="^keychain_operation_refused$") as caught:
        m.read_keychain_credential("eodhd", _process_factory=refuse)
    assert "invented-secret" not in str(caught.value)
