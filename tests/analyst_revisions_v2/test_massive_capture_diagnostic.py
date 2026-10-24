"""Synthetic observation seams only; no provider or private artifact access."""
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, asdict
import json
from pathlib import Path

import pytest

from scripts import arv2_massive_capture_diagnostic as diagnostic
from scripts.capture_arv2_massive import MassiveCaptureError


def _assert_record(observation, *, invoked, returned, terminal, code):
    assert asdict(observation) == {
        "capture_invoked": invoked,
        "producer_return_received": returned,
        "terminal_state": terminal,
        "failure_code": code,
        "provider_request_count": None,
    }


@pytest.mark.parametrize("message, expected", (
    ("MASSIVE_API_KEY is unavailable or malformed; refusing provider access", "credential"),
    ("spooled capture configuration is not reviewed", "unsafe_configuration"),
    ("ReadTimeout: provider request failed; details redacted", "network_request"),
    ("provider returned a non-success HTTP status", "http_status"),
    ("provider response is not strict JSON", "response_schema"),
    ("capture publication failed", "persistence_publication"),
    ("SECRET-EXAMPLE-ONLY provider data", "unknown"),
))
def test_producer_refusal_is_observed_once_without_retry(message, expected, capsys):
    calls = []

    def producer():
        calls.append("called")
        raise MassiveCaptureError(message)

    observation, returned = diagnostic.observe_capture_once(producer)
    assert calls == ["called"]
    assert returned is None
    _assert_record(observation, invoked=True, returned=False,
                   terminal="producer_raised", code=expected)
    assert capsys.readouterr() == ("", "")


def test_opaque_producer_return_is_separate_and_never_rendered(capsys):
    class PrivatePayload:
        def __getattribute__(self, name):
            raise AssertionError("private payload inspection forbidden")

        def __repr__(self):
            raise AssertionError("private payload rendering forbidden")

        def __str__(self):
            raise AssertionError("private payload rendering forbidden")

    payload = PrivatePayload()
    calls = []

    def producer():
        calls.append("called")
        return payload

    observation, returned = diagnostic.observe_capture_once(producer)
    assert calls == ["called"]
    assert returned is payload
    _assert_record(observation, invoked=True, returned=True,
                   terminal="producer_returned", code=None)
    assert "producer_returned" in repr(observation)
    assert json.loads(json.dumps(asdict(observation))) == asdict(observation)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("returned", (None, False, 0, "not-a-capture", {"private": "synthetic"}))
def test_return_is_not_validated_or_misrepresented_as_publication(returned):
    observation, raw = diagnostic.observe_capture_once(lambda: returned)
    assert raw is returned
    _assert_record(observation, invoked=True, returned=True,
                   terminal="producer_returned", code=None)
    assert set(asdict(observation)) == {
        "capture_invoked", "producer_return_received", "terminal_state",
        "failure_code", "provider_request_count",
    }


@pytest.mark.parametrize("producer", (None, False, 0, "private callback text", object()))
def test_noncallable_is_a_bounded_preinvocation_refusal(producer, capsys):
    observation, returned = diagnostic.observe_capture_once(producer)
    assert returned is None
    _assert_record(observation, invoked=False, returned=False,
                   terminal="not_invoked", code="invalid_callback")
    assert capsys.readouterr() == ("", "")


def test_noncallable_attributes_and_rendering_are_not_inspected():
    class Hostile:
        def __getattribute__(self, name):
            raise AssertionError("callback attribute inspection forbidden")

        def __repr__(self):
            raise AssertionError("callback rendering forbidden")

        def __str__(self):
            raise AssertionError("callback rendering forbidden")

    observation, returned = diagnostic.observe_capture_once(Hostile())
    assert returned is None
    _assert_record(observation, invoked=False, returned=False,
                   terminal="not_invoked", code="invalid_callback")


def test_callable_check_does_not_authenticate_or_inspect_a_signature():
    calls = []

    class NeedsArgument:
        def __getattribute__(self, name):
            raise AssertionError("callback metadata inspection forbidden")

        def __call__(self, required):
            calls.append("body")
            return required

    observation, returned = diagnostic.observe_capture_once(NeedsArgument())
    assert calls == []
    assert returned is None
    _assert_record(observation, invoked=True, returned=False,
                   terminal="producer_raised", code="unknown")


@pytest.mark.parametrize("kind", (KeyboardInterrupt, SystemExit, GeneratorExit, ValueError,
                                  RuntimeError, TimeoutError))
def test_interruptions_and_foreign_failures_are_terminal_unknown(kind, capsys):
    calls = []

    def producer():
        calls.append("called")
        raise kind("SECRET-EXAMPLE-ONLY")

    observation, returned = diagnostic.observe_capture_once(producer)
    assert calls == ["called"]
    assert returned is None
    _assert_record(observation, invoked=True, returned=False,
                   terminal="producer_raised", code="unknown")
    assert capsys.readouterr() == ("", "")


def test_exception_rendering_attributes_cause_and_context_are_not_used(capsys):
    class Hostile(MassiveCaptureError):
        def __getattribute__(self, name):
            raise AssertionError("exception attribute inspection forbidden")

        def __repr__(self):
            raise AssertionError("exception rendering forbidden")

        def __str__(self):
            raise AssertionError("exception rendering forbidden")

    # Matching class metadata is not class authentication, exactly as in the
    # classifier contract. The observation exposes no raw class information.
    Hostile.__module__ = "scripts.capture_arv2_massive"
    Hostile.__qualname__ = "MassiveCaptureError"
    exc = Hostile("provider returned a non-success HTTP status")
    exc.__cause__ = RuntimeError("private synthetic cause")
    exc.__context__ = RuntimeError("private synthetic context")
    calls = []

    def producer():
        calls.append("called")
        raise exc

    observation, returned = diagnostic.observe_capture_once(producer)
    assert calls == ["called"]
    assert returned is None
    _assert_record(observation, invoked=True, returned=False,
                   terminal="producer_raised", code="http_status")
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("classification", ("private synthetic message", 42, None, object()))
def test_classifier_cannot_add_unbounded_observation_values(monkeypatch, classification):
    monkeypatch.setattr(diagnostic, "classify_capture_failure", lambda exc: classification)

    def producer():
        raise MassiveCaptureError("capture publication failed")

    observation, returned = diagnostic.observe_capture_once(producer)
    assert returned is None
    _assert_record(observation, invoked=True, returned=False,
                   terminal="producer_raised", code="unknown")


def test_classifier_failure_retains_original_finite_non_success(monkeypatch):
    def classifier(exc):
        raise KeyboardInterrupt("private synthetic classifier failure")

    monkeypatch.setattr(diagnostic, "classify_capture_failure", classifier)

    def producer():
        raise MassiveCaptureError("capture publication failed")

    observation, returned = diagnostic.observe_capture_once(producer)
    assert returned is None
    _assert_record(observation, invoked=True, returned=False,
                   terminal="producer_raised", code="unknown")


def test_classifier_string_subclass_is_not_compared_or_rendered(monkeypatch):
    class HostileText(str):
        def __hash__(self):
            raise AssertionError("classification subclass hashing forbidden")

        def __eq__(self, other):
            raise AssertionError("classification subclass comparison forbidden")

    monkeypatch.setattr(diagnostic, "classify_capture_failure",
                        lambda exc: HostileText("http_status"))

    def producer():
        raise MassiveCaptureError("capture publication failed")

    observation, returned = diagnostic.observe_capture_once(producer)
    assert returned is None
    _assert_record(observation, invoked=True, returned=False,
                   terminal="producer_raised", code="unknown")


def test_terminal_state_string_subclass_is_not_compared():
    class HostileTerminal(str):
        def __eq__(self, other):
            raise AssertionError("terminal subclass comparison forbidden")

    with pytest.raises(ValueError, match="capture observation shape"):
        diagnostic.CaptureObservation(True, True,
                                      HostileTerminal("producer_returned"), None)


def test_observation_is_frozen_and_never_claims_a_request_count():
    observation, returned = diagnostic.observe_capture_once(lambda: object())
    with pytest.raises(FrozenInstanceError):
        observation.capture_invoked = False
    with pytest.raises(FrozenInstanceError):
        observation.provider_request_count = 0
    with pytest.raises(TypeError):
        diagnostic.CaptureObservation(True, True, "producer_returned", None,
                                      provider_request_count=0)
    assert returned is not None
    assert observation.provider_request_count is None


@pytest.mark.parametrize("args", (
    (1, True, "producer_returned", None),
    (True, 1, "producer_returned", None),
    (True, True, 42, None),
    (True, False, "producer_raised", object()),
    (True, True, "authenticated_capture", None),
    (False, False, "not_invoked", None),
    (True, False, "not_invoked", "invalid_callback"),
    (True, True, "producer_raised", "unknown"),
    (True, False, "producer_raised", "invalid_callback"),
    (True, False, "producer_raised", None),
    (False, True, "producer_returned", None),
    (True, True, "producer_returned", "unknown"),
))
def test_observation_rejects_inconsistent_or_nonexact_shapes(args):
    with pytest.raises(ValueError, match="capture observation"):
        diagnostic.CaptureObservation(*args)


def test_module_has_no_production_dispatch_or_io_dependencies():
    tree = ast.parse(Path(diagnostic.__file__).read_text(encoding="utf-8"))
    imports = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imports == {
        "__future__", "dataclasses", "typing", "scripts.arv2_massive_capture_failure",
    }
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    names = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not names & {
        "print", "str", "repr", "open", "eval", "exec", "compile", "__import__",
        "capture_massive_history", "load_massive_capture_artifact",
    }
    assert not any(isinstance(node, ast.If) for node in tree.body)
    assert "main" not in {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "observe_capture_once")
    assert all(arg is None for arg in function.args.kw_defaults)
    assert function.args.defaults == []
