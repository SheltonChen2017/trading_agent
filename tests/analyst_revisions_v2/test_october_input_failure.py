"""Static source inventory and synthetic exception-only classifier checks."""

import ast
import hashlib
import json
from pathlib import Path
import sys
from types import MappingProxyType

import pytest

from scripts import arv2_october_input_failure as subject

ROOT = Path(__file__).resolve().parents[2]


def _exception(cls, *args):
    # No source operation or special publication constructor is executed.
    value = BaseException.__new__(cls)
    BaseException.__init__(value, *args)
    return value


def _inventory(path):
    tree = ast.parse(path.read_bytes())
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)
               and (node.name.endswith("Error") or node.name.endswith("CapacityRefusal"))}
    helpers = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ("_refuse", "_fail"):
            targets = {child.exc.func.id for child in ast.walk(node)
                       if isinstance(child, ast.Raise) and isinstance(child.exc, ast.Call)
                       and isinstance(child.exc.func, ast.Name) and child.exc.func.id in classes}
            assert len(targets) == 1
            helpers[node.name] = targets.pop()
    inventory = {name: set() for name in classes}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args:
            target = helpers.get(node.func.id, node.func.id)
            if (target in classes and isinstance(node.args[0], ast.Constant)
                    and type(node.args[0].value) is str):
                inventory[target].add(node.args[0].value)
    return {name: sorted(values) for name, values in sorted(inventory.items())}


@pytest.mark.parametrize("path", tuple(subject.SOURCE_PINS))
def test_inventory_matches_exact_source_pins_and_all_audited_literal_sites(path):
    payload = (ROOT / path).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == subject.SOURCE_PINS[path]
    actual = _inventory(ROOT / path)
    declared = {name: sorted(literals) for _cls, _label, source, name, literals in subject._TYPE_ROWS if source == path}
    assert actual == declared
    canonical = json.dumps(actual, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    assert hashlib.sha256(canonical).hexdigest() == subject.SOURCE_INVENTORY_SHA256[path]


CASES = tuple((cls, label, text, code) for cls, label, _path, _name, literals in subject._TYPE_ROWS
              for text, code in literals.items())


@pytest.mark.parametrize("cls,label,text,code", CASES, ids=[code for _, _, _, code in CASES])
def test_every_literal_has_exact_class_dispatch_and_precomputed_public_code(cls, label, text, code):
    assert subject.classify_failure(_exception(cls, text)) == (label, code)
    assert code == label + ":literal_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    assert len(text) <= subject.MAX_ARGUMENT_CHARACTERS
    assert text not in code


@pytest.mark.parametrize("row", subject._TYPE_ROWS, ids=[row[1] for row in subject._TYPE_ROWS])
@pytest.mark.parametrize("arguments", [(), ("UNKNOWN PRIVATE ROW",), (None,), (42,),
                                       ("one", "two"), ("x" * 513,)])
def test_known_exact_type_unknown_payload_remains_finite(row, arguments):
    cls, label, *_ = row
    assert subject.classify_failure(_exception(cls, *arguments)) == (label, "unknown")


def test_inventory_classes_and_public_codes_are_complete_distinct_and_immutable():
    assert len(subject.SOURCE_PINS) == len(subject.SOURCE_INVENTORY_SHA256) == 9
    assert len(subject._TYPE_ROWS) == 16
    assert len(CASES) == 650
    assert len({row[0] for row in subject._TYPE_ROWS}) == len(subject._TYPE_ROWS)
    assert len({row[1] for row in subject._TYPE_ROWS}) == len(subject._TYPE_ROWS)
    assert len({code for _, _, _, code in CASES}) == len(CASES)
    assert type(subject.SOURCE_PINS) is MappingProxyType
    assert type(subject.SOURCE_INVENTORY_SHA256) is MappingProxyType
    for _cls, _label, _path, _name, literals in subject._TYPE_ROWS:
        assert type(literals) is MappingProxyType
        assert tuple(literals) == tuple(sorted(literals))
    assert "assistant.dispatch_fence" not in sys.modules


def test_capacity_and_publication_subclasses_are_not_coerced_to_parent_type():
    selected = [row for row in subject._TYPE_ROWS if "capacity" in row[1] or "publication" in row[1]]
    assert len(selected) == 7
    for cls, label, _path, _name, literals in selected:
        if literals:
            text = next(iter(literals))
            assert subject.classify_failure(_exception(cls, text))[0] == label


def test_unregistered_subclass_and_hostile_metaclass_never_invoke_hooks():
    calls = []
    class HostileMeta(type):
        def __hash__(self):
            calls.append("hash")
            raise AssertionError("metaclass hash")
        def __eq__(self, other):
            calls.append("eq")
            raise AssertionError("metaclass eq")
    base = subject._TYPE_ROWS[0][0]
    class Derived(base, metaclass=HostileMeta):
        def __getattribute__(self, name):
            calls.append("getattribute")
            raise AssertionError("exception attribute")
        def __str__(self):
            calls.append("str")
            raise AssertionError("exception str")
        def __repr__(self):
            calls.append("repr")
            raise AssertionError("exception repr")
    assert subject.classify_failure(_exception(Derived, "private")) is None
    assert calls == []


def test_opaque_args_and_string_subclasses_are_not_hash_rendered_or_compared():
    class Opaque:
        def __str__(self):
            pytest.fail("opaque str")
        def __repr__(self):
            pytest.fail("opaque repr")
        def __hash__(self):
            pytest.fail("opaque hash")
        def __eq__(self, other):
            pytest.fail("opaque eq")
    class Text(str):
        def __hash__(self):
            pytest.fail("subclass hash")
        def __len__(self):
            pytest.fail("subclass len")
        def __eq__(self, other):
            pytest.fail("subclass eq")
    for cls, label, _path, _name, literals in subject._TYPE_ROWS:
        for payload in (Opaque(), Text(next(iter(literals), "unknown"))):
            assert subject.classify_failure(_exception(cls, payload)) == (label, "unknown")


def test_oversize_refuses_before_literal_lookup(monkeypatch):
    cls, label, path, name, _literals = subject._TYPE_ROWS[0]
    class NoLookup:
        def get(self, *_args):
            pytest.fail("oversize lookup")
    monkeypatch.setattr(subject, "_TYPE_ROWS", ((cls, label, path, name, NoLookup()),))
    assert subject.classify_failure(_exception(cls, "x" * 513)) == (label, "unknown")


def test_exact_exception_args_descriptor_bypasses_monkeypatched_attribute_hook(monkeypatch):
    cls, label, _path, _name, literals = subject._TYPE_ROWS[0]
    text = next(iter(literals))
    value = _exception(cls, text)
    def refuse(*_args):
        pytest.fail("exception getattr")
    monkeypatch.setattr(cls, "__getattribute__", refuse)
    assert subject.classify_failure(value) == (label, literals[text])


def test_unknown_builtins_are_left_for_separate_finite_fallback():
    for exc in (ValueError("private"), OSError("private"), RuntimeError("private"), KeyboardInterrupt()):
        assert subject.classify_failure(exc) is None


def test_runtime_classifier_has_no_hashing_rendering_io_or_dynamic_inventory():
    tree = ast.parse((ROOT / "scripts/arv2_october_input_failure.py").read_bytes())
    runtime = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "classify_failure")
    calls = [node.func for node in ast.walk(runtime) if isinstance(node, ast.Call)]
    assert {node.id for node in calls if isinstance(node, ast.Name)} == {"type", "len"}
    assert {node.attr for node in calls if isinstance(node, ast.Attribute)} == {"__get__", "get"}
    assert not any(isinstance(node, ast.JoinedStr) for node in ast.walk(runtime))


def test_codes_identify_public_literal_only_not_an_authenticated_cause():
    cls, label, _path, _name, literals = subject._TYPE_ROWS[0]
    text = next(iter(literals))
    # Same literal category with arbitrary private chained cause remains finite.
    exc = _exception(cls, text)
    exc.__cause__ = RuntimeError("PRIVATE TOKEN ROW PATH")
    assert subject.classify_failure(exc) == (label, literals[text])
