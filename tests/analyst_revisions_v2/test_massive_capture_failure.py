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


def test_nonexception_class_attribute_is_never_consulted():
    class HostileNonexception:
        @property
        def __class__(self):
            raise AssertionError("nonexception class lookup forbidden")

    assert diagnostic.classify_capture_failure(HostileNonexception()) == "unknown"


def test_nonexception_cannot_impersonate_an_exception_with_class_attribute():
    calls = []

    class Impersonator:
        @property
        def __class__(self):
            calls.append("class lookup")
            return MassiveCaptureError

    assert diagnostic.classify_capture_failure(Impersonator()) == "unknown"
    assert calls == []


def test_class_metadata_descriptor_is_not_invoked():
    class HostileDescriptor:
        def __get__(self, instance, owner):
            raise AssertionError("class metadata descriptor forbidden")

    class Child(MassiveCaptureError):
        __module__ = HostileDescriptor()

    assert diagnostic.classify_capture_failure(Child("capture publication failed")) == "unknown"


def test_metaclass_metadata_descriptor_is_not_invoked():
    class HostileMeta(type):
        @property
        def __module__(cls):
            raise AssertionError("metaclass metadata descriptor forbidden")

    class Child(MassiveCaptureError, metaclass=HostileMeta):
        __module__ = "scripts.capture_arv2_massive"
        __qualname__ = "MassiveCaptureError"

    # Read the true built-in metadata, not the metaclass's property. This
    # remains metadata matching, deliberately not authenticated class identity.
    assert diagnostic.classify_capture_failure(Child("capture publication failed")) == "persistence_publication"


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


def _adapter_tree():
    # Only committed public source is inspected. No adapter invocation,
    # artifact, credential, provider or process is needed for reachability.
    source = Path(__file__).resolve().parents[2] / "scripts" / "capture_arv2_massive.py"
    return ast.parse(source.read_text())


def _capture_error_arguments(tree):
    return [node.exc.args[0] for node in ast.walk(tree)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "MassiveCaptureError"
            and len(node.exc.args) == 1]


def test_every_adapter_literal_refusal_is_classified():
    literal_messages = {argument.value for argument in _capture_error_arguments(_adapter_tree())
                        if isinstance(argument, ast.Constant)
                        and type(argument.value) is str}
    assert len(literal_messages) == 145
    for message in sorted(literal_messages):
        assert diagnostic.classify_capture_failure(MassiveCaptureError(message)) != "unknown", message


def _literal_call_names(tree, helper, argument_position, keyword="name"):
    names = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == helper):
            continue
        value = next((item.value for item in node.keywords if item.arg == keyword), None)
        if value is None and len(node.args) > argument_position:
            value = node.args[argument_position]
        if isinstance(value, ast.Constant) and type(value.value) is str:
            names.add(value.value)
    return names


def _name_templates(function):
    templates = set()
    for argument in _capture_error_arguments(function):
        if not isinstance(argument, ast.JoinedStr):
            continue
        pieces = []
        for value in argument.values:
            if isinstance(value, ast.Constant) and type(value.value) is str:
                pieces.append(value.value)
            elif (isinstance(value, ast.FormattedValue)
                  and isinstance(value.value, ast.Name)
                  and value.value.id == "name"
                  and value.conversion == -1 and value.format_spec is None):
                pieces.append("{name}")
            else:
                raise AssertionError("unreviewed formatted refusal shape")
        templates.add("".join(pieces))
    return templates


def _assert_forwarded_name(function, helper, argument_position):
    calls = [node for node in ast.walk(function)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == helper]
    assert calls
    for call in calls:
        value = next((item.value for item in call.keywords if item.arg == "name"), None)
        if value is None:
            value = call.args[argument_position]
        assert isinstance(value, ast.Name) and value.id == "name"


def test_every_allowlist_entry_has_a_literal_or_audited_formatted_source():
    tree = _adapter_tree()
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    literal_messages = {argument.value for argument in _capture_error_arguments(tree)
                        if isinstance(argument, ast.Constant) and type(argument.value) is str}

    # Exhaustive evidence for the sixteen retained name-formatted labels.
    # Names are required at actual helper call sites; forwarding chains are
    # checked rather than assuming arbitrary name/template combinations work.
    assert "artifact root" in _literal_call_names(tree, "_open_directory_path", 0)
    _assert_forwarded_name(functions["_open_directory_path"],
                           "_require_private_directory_metadata", 1)
    manifest_names = {"capture manifest", "capture manifest digest"}
    assert manifest_names <= _literal_call_names(tree, "_exclusive_private_write_at", 3)
    _assert_forwarded_name(functions["_exclusive_private_write_at"], "_write_all", 2)
    sync_names = {"capture staging artifact", "capture root publication", "capture root rollback"}
    assert sync_names <= _literal_call_names(tree, "_fsync_fd", 1)
    reviewed_cases = (
        ("_require_private_directory_metadata", "artifact root",
         "{name} must be an owner-held private 0700 directory"),
        ("_open_directory_path", "artifact root",
         "{name} must not traverse a link and must be a directory"),
        ("_open_directory_path", "artifact root", "{name} root directory is unavailable"),
        ("_open_directory_path", "artifact root", "{name} is unavailable"),
        ("_open_directory_path", "artifact root", "{name} could not be prepared safely"),
        *(("_fsync_fd", name, "{name} directory sync failed") for name in sorted(sync_names)),
        *((helper, name, template) for name in sorted(manifest_names)
          for helper, template in (
              ("_exclusive_private_write_at", "{name} could not be created"),
              ("_exclusive_private_write_at", "{name} could not be durably written"),
              ("_write_all", "{name} write failed"),
              ("_write_all", "{name} write stalled"),
          )),
    )
    formatted_messages = set()
    for helper, name, template in reviewed_cases:
        assert template in _name_templates(functions[helper])
        formatted_messages.add(template.format(name=name))
    assert len(formatted_messages) == 16

    # Request/session-boundary exception names are deliberately finite; this
    # template can describe preparation, iteration or close, not just contact.
    sanitizer = functions["_sanitized_provider_failure"]
    returns = [node.value for node in ast.walk(sanitizer) if isinstance(node, ast.Return)]
    expected_template = ast.parse('f"{type(exc).__name__}: provider request failed; details redacted"', mode="eval").body
    assert len(returns) == 1 and ast.dump(returns[0]) == ast.dump(expected_template)
    assert any(isinstance(argument, ast.Call) and isinstance(argument.func, ast.Name)
               and argument.func.id == "_sanitized_provider_failure"
               for argument in _capture_error_arguments(tree))
    network_names = {
        "Timeout", "ConnectTimeout", "ReadTimeout", "ConnectionError", "SSLError",
        "ProxyError", "RequestException", "ChunkedEncodingError", "ContentDecodingError",
        "OSError", "RuntimeError", "AttributeError", "TypeError", "ValueError",
    }
    network_messages = {name + ": provider request failed; details redacted" for name in network_names}
    assert len(network_messages) == 14
    labels = {message for _, group in diagnostic._GROUPS for message in group}
    assert labels == literal_messages | formatted_messages | network_messages
    assert len(labels) == 175


def test_utility_has_no_imports_or_io_and_does_not_render_exception():
    # An import-free helper is the boundary being asserted, so inspect syntax
    # directly without importing an additional runtime or support plugin.
    tree = ast.parse(Path(diagnostic.__file__).read_text())
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree))
    names = {node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not names & {"str", "repr", "print", "open", "eval", "exec", "compile", "__import__"}


def test_same_name_class_from_another_module_is_unknown():
    # Section 291: only the production import name is recognized. A class that
    # merely shares the name and an allowlisted message must stay unknown.
    class MassiveCaptureError(Exception):
        pass

    # Match the production qualified name exactly so that only the module
    # comparison can distinguish this class from the real one.
    MassiveCaptureError.__qualname__ = "MassiveCaptureError"
    assert MassiveCaptureError.__module__ != "scripts.capture_arv2_massive"
    assert diagnostic.classify_capture_failure(
        MassiveCaptureError("capture publication failed")) == "unknown"


def test_overlong_message_is_unknown_before_inventory_lookup(monkeypatch):
    # Section 291: the 200-character bound precedes membership, so even an
    # allowlisted overlong message is never compared against the inventory.
    bounded = "x" * 200
    overlong = "x" * 201
    monkeypatch.setattr(diagnostic, "_GROUPS",
                        (("unsafe_configuration", (bounded, overlong)),) + diagnostic._GROUPS)
    assert diagnostic.classify_capture_failure(MassiveCaptureError(bounded)) == "unsafe_configuration"
    assert diagnostic.classify_capture_failure(MassiveCaptureError(overlong)) == "unknown"
