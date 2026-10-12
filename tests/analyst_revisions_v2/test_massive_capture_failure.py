"""Synthetic failure labels only: no provider or private artifact access."""

import ast
from pathlib import Path

import pytest

from scripts import arv2_massive_capture_failure as diagnostic
from scripts.capture_arv2_massive import MassiveCaptureError


@pytest.mark.parametrize("message, expected", (
    ("MASSIVE_API_KEY is unavailable or malformed; refusing provider access", "credential"),
    ("spooled capture configuration is not reviewed", "unsafe_configuration"),
    ("artifact root must be an owner-held private 0700 directory", "unsafe_configuration"),
    ("provider next_url contains credential material", "unsafe_configuration"),
    ("ReadTimeout: provider request failed; details redacted", "network_request"),
    ("ConnectionError: provider request failed; details redacted", "network_request"),
    ("RuntimeError: provider request failed; details redacted", "network_request"),
    ("provider returned a non-success HTTP status", "http_status"),
    ("provider response status is not exact OK", "response_schema"),
    ("provider response is not strict JSON", "response_schema"),
    ("provider response exceeded the byte limit", "response_schema"),
    ("capture chronology is reversed", "response_schema"),
    ("capture publication failed", "persistence_publication"),
    ("capture publication state is ambiguous after rollback sync failure", "persistence_publication"),
    ("timestamped capture staging could not be created", "persistence_publication"),
    ("artifact root could not be prepared safely", "persistence_publication"),
))
def test_exact_known_production_refusal_messages(message, expected):
    assert diagnostic.classify_capture_failure(MassiveCaptureError(message)) == expected


@pytest.mark.parametrize("message", (
    "Bearer SECRET-EXAMPLE-ONLY",
    "https://api.massive.com/path?apiKey=SECRET-EXAMPLE-ONLY",
    '{"results":[{"ticker":"PRIVATE-EXAMPLE","rating":"PRIVATE"}]}',
    "SECRET-EXAMPLE-ONLY: provider request failed; details redacted",
    "provider returned a non-success HTTP status SECRET-EXAMPLE-ONLY",
    "provider returned a non-success HTTP status\n",
    "HTTPError: provider request failed; details redacted",
    "secret-example" * 1000,
    "",
))
def test_unknown_or_altered_messages_never_escape(message, capsys):
    assert diagnostic.classify_capture_failure(MassiveCaptureError(message)) == "unknown"
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("args", ((), ("one", "two"), (object(),), (42,), (b"secret",)))
def test_nonexact_argument_shapes_are_unknown(args):
    assert diagnostic.classify_capture_failure(MassiveCaptureError(*args)) == "unknown"


@pytest.mark.parametrize("kind", (ValueError, RuntimeError, OSError, TimeoutError, SystemExit))
def test_known_text_in_other_exception_types_is_not_classified(kind):
    exc = kind("provider returned a non-success HTTP status")
    assert diagnostic.classify_capture_failure(exc) == "unknown"


def test_hostile_exception_rendering_and_instance_attributes_are_never_used():
    class Hostile(MassiveCaptureError):
        def __str__(self):
            raise AssertionError("exception rendering forbidden")

        def __repr__(self):
            raise AssertionError("exception rendering forbidden")

        def __getattribute__(self, name):
            raise AssertionError("instance attribute access forbidden")

    # Match the recognized metadata to exercise the argument read, not just
    # the unknown-class fast path. This is not type-authentication evidence.
    Hostile.__module__ = "scripts.capture_arv2_massive"
    Hostile.__qualname__ = "MassiveCaptureError"
    exc = Hostile("provider returned a non-success HTTP status")
    assert diagnostic.classify_capture_failure(exc) == "http_status"


def test_str_subclasses_are_not_compared_or_rendered():
    class HostileText(str):
        def __eq__(self, other):
            raise AssertionError("subclass comparison forbidden")

        def __str__(self):
            raise AssertionError("subclass rendering forbidden")

    exc = MassiveCaptureError(HostileText("provider returned a non-success HTTP status"))
    assert diagnostic.classify_capture_failure(exc) == "unknown"


def test_cause_and_context_are_ignored():
    exc = MassiveCaptureError("provider response is not strict JSON")
    exc.__cause__ = ValueError("secret example")
    exc.__context__ = ValueError("private rows example")
    assert diagnostic.classify_capture_failure(exc) == "response_schema"


def test_malformed_class_metadata_is_not_compared_or_rendered():
    class HostileMetadata:
        def __eq__(self, other):
            raise AssertionError("metadata comparison forbidden")

        def __ne__(self, other):
            raise AssertionError("metadata comparison forbidden")

    class Child(MassiveCaptureError):
        pass

    Child.__module__ = HostileMetadata()
    assert diagnostic.classify_capture_failure(Child("capture publication failed")) == "unknown"


def test_subclasses_and_nonexceptions_are_unknown():
    class Child(MassiveCaptureError):
        pass

    assert diagnostic.classify_capture_failure(Child("capture publication failed")) == "unknown"
    assert diagnostic.classify_capture_failure(object()) == "unknown"


def test_allowlist_has_unique_messages_and_only_finite_static_codes():
    codes = {"credential", "unsafe_configuration", "network_request", "http_status",
             "response_schema", "persistence_publication"}
    assert {code for code, _ in diagnostic._GROUPS} == codes
    messages = [message for _, group in diagnostic._GROUPS for message in group]
    assert len(messages) == len(set(messages))
    for code, group in diagnostic._GROUPS:
        for message in group:
            assert diagnostic.classify_capture_failure(MassiveCaptureError(message)) == code


def test_utility_has_no_imports_or_io_and_does_not_render_exception():
    # An import-free helper is the boundary being asserted, so inspect syntax
    # directly without importing an additional runtime or support plugin.
    tree = ast.parse(Path(diagnostic.__file__).read_text())
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree))
    names = {node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not names & {"str", "repr", "print", "open", "eval", "exec", "compile", "__import__"}
