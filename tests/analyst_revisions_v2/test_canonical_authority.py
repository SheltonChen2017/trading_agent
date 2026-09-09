from __future__ import annotations

from types import MappingProxyType

from research.analyst_revisions_v2.canonical import (
    capture_frozen_container_authority,
    frozen_container_authority_is_current,
)


class _BackingDictLeak:
    def __init__(self) -> None:
        self.value: object | None = None

    def __eq__(self, other: object) -> bool:
        self.value = other
        return False


class _SplitView:
    def __init__(self, original: MappingProxyType) -> None:
        self.original = original
        self.calls: list[str] = []

    def __getitem__(self, key: str) -> object:
        self.calls.append("getitem")
        if key == "orders":
            return True
        return self.original[key]

    def __iter__(self):
        self.calls.append("iter")
        return iter(self.original)

    def __len__(self) -> int:
        self.calls.append("len")
        return len(self.original)

    def items(self):
        self.calls.append("items")
        return self.original.items()


def _leak_backing_dict(proxy: MappingProxyType) -> dict[str, object]:
    leak = _BackingDictLeak()
    assert (proxy == leak) is False
    assert type(leak.value) is dict
    return leak.value


def test_descendant_identity_check_precedes_hostile_proxy_traversal():
    capabilities = MappingProxyType({"orders": False})
    root = MappingProxyType({"capabilities": capabilities})
    authority = capture_frozen_container_authority((root,))
    backing = _leak_backing_dict(root)
    split_view = _SplitView(capabilities)
    backing["capabilities"] = MappingProxyType(split_view)

    assert frozen_container_authority_is_current((root,), authority) is False
    assert split_view.calls == []


def test_descendant_removal_and_equivalent_replacement_are_not_current():
    nested = ("one", "two")
    root = MappingProxyType({"nested": nested})
    authority = capture_frozen_container_authority((root,))
    backing = _leak_backing_dict(root)

    backing["nested"] = tuple(["one", "two"])
    assert frozen_container_authority_is_current((root,), authority) is False

    backing["nested"] = None
    assert frozen_container_authority_is_current((root,), authority) is False


def test_trusted_container_cannot_be_rewired_into_a_former_scalar_slot():
    root = MappingProxyType({"value": "safe"})
    authority = capture_frozen_container_authority((root,))
    backing = _leak_backing_dict(root)

    backing["value"] = root
    assert frozen_container_authority_is_current((root,), authority) is False


def test_retained_descendants_cannot_swap_slots_while_remaining_reachable():
    left = MappingProxyType({"side": "left"})
    right = MappingProxyType({"side": "right"})
    root = MappingProxyType({"left": left, "right": right})
    authority = capture_frozen_container_authority((root,))
    backing = _leak_backing_dict(root)

    backing["left"], backing["right"] = right, left
    assert frozen_container_authority_is_current((root,), authority) is False


def test_exact_captured_container_graph_remains_current():
    shared = MappingProxyType({"orders": False})
    root = MappingProxyType({"left": (shared,), "right": shared})
    authority = capture_frozen_container_authority((root,))

    assert frozen_container_authority_is_current((root,), authority) is True
