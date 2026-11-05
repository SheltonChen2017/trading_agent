"""Pure six-cell successor of the frozen comparison and plain R298 checkpoint.

Inputs must already be authenticated in the current process. No file, credential,
provider, Object Store or QC operation is performed. The separately selected
host-generator pin belongs to this family manifest, never an existing R298
profile. Fresh operational source admission remains the caller's responsibility.
"""
from __future__ import annotations

import dataclasses
import json
import os
import threading
import weakref
from types import SimpleNamespace

from . import newrule_comparison_submission as predecessor
from . import newrule_plain_projection as bridge


SCHEMA = "arv2-newrule-plain-comparison-family-v1"
CELL_SCHEMA = "arv2-newrule-plain-comparison-projection-v1"
BRIDGE_SCHEMA = "arv2-newrule-plain-comparison-source-bridge-v1"
HOST_SOURCE_NAME = "newrule_plain_comparison.py"
FAMILY_SHA256 = bridge.parent.FAMILY
CELLS = (("R298", 6, 0), ("R299", 6, 100), ("R300", 6, 200),
         ("R301", 8, 0), ("R302", 8, 100), ("R303", 8, 200))
PARENT_PINS = (
    ("b27e40dc4ae9e71b308d6eccd0fdaf83220be9157021c265a32c71e6f8b7a09b", "f67148cd717e207be9d44f088749c0443bb696d9c4f38f512eb6cbf483fd9662"),
    ("3957b3c19905608f40ffb40f808ef7410d7867ef3a0a49943de4249a80d66b0e", "db15f37b4f428cfc7f8ff98918abcc8170af61c3d0da3689798b38fbeb6755f7"),
    ("21bc95bc9752a6b90589e84eec40c42fe9c26d23bb8ce87ad996808c6ce2d6a3", "19c7372420c0ebf19ea6dca84eca7daad99edf867f11ab478efeada9addc56ba"),
    ("9c412c4fa972076283b178f9ba93cf95303d48aa6d4056dc3b37efd5d2673f4c", "e92f99b369325788f89c516001d189dcddecb335ff22fe4f1ebb51fbeb857370"),
    ("951c9c7ff889c622d01a62ad2aaef8705c02ab021c5e12e67007efa81f666d90", "421726e5bb888dd4f193edd575115fcad26bb335a54b09543c0b442fc536f224"),
    ("ab1f8e895e114f9f375cfa5d300c13dd3a544cbbb8c7635ee694e3fe1c6bf150", "3145f92263561669e865ab3cd8856d988ba2dc2b49171c69bd30e329926ebb6b"),
)
NEW_SOURCE_PINS = {
    "newrule_plain_transport.py": "4cf351095015fddb7a463692f6d789917d229966772e04a60de0c804ed965f5a",
    "newrule_plain_input_runtime.py": "bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f",
    "newrule_plain_projection.py": "a0152d0d4109584312ee1e5a2f91cc03bf97cbab6b0e2525dd4f968fa9bd9927",
}
PLAIN_PACKAGE_SHA256 = "1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2"
PLAIN_ACTIVATION = ("arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/transport-manifest.json",
    "ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b", 5901)
PLAIN_PROOF_SHA256 = "95405d1b569d4bfeeb6c6d87fdb430f2fd27b8b7a31d6dcde7f82276d9903cd1"
R298_PROFILE_SHA256 = "89d6ac9bb0f1be8bd8f307f0b00d5725620e33b402fecb7ee2ff06daecc2106e"
R298_PROJECTION_SHA256 = "9dde39783bcb401d1f36aeb5beb1b1983882250b0472c2afd22dca1408c2a5f5"
FALSE_FLAGS = dict(bridge.FALSE_FLAGS, family_complete=False, family_comparable=False)
_AUTHORITIES = {}
_LOCK = threading.RLock()


class PlainComparisonError(ValueError):
    """Finite in-memory binding failure; no source or private row is rendered."""


def require(value, code):
    if not value:
        raise PlainComparisonError(code)


canonical = bridge.canonical
sha = bridge.sha


def _input_authority(value):
    """Check an existing capability without replaying its filesystem reader."""
    require(type(value) is predecessor.october.OctoberOrderInputPackage, "input_type")
    package = value.package
    compact = predecessor.compact
    require(type(package) is compact.AcceptedRiskPreliminaryPackage, "input_type")
    with compact._AUTHORITY_LOCK:
        authority = compact._AUTHORITIES.get(id(package))
    require(authority is not None and authority[0]() is package
        and authority[1] == compact._package_fingerprint(package)
        and authority[2] == os.getpid(), "input_authority")
    require(package.package_sha256 == bridge.parent.PACKAGE
        and package.source_disposition_sha256 == bridge.parent.LINEAGE
        and type(value.lineage_bytes) is bytes and sha(value.lineage_bytes) == bridge.parent.LINEAGE
        and type(value.lineage_sha256) is str and value.lineage_sha256 == bridge.parent.LINEAGE,
        "input_identity")
    lineage = json.loads(value.lineage_bytes)
    require(canonical(lineage) == value.lineage_bytes
        and type(value.decision_cutoff_session) is str and value.decision_cutoff_session == "2026-10-12"
        and type(value.final_execution_session) is str and value.final_execution_session == "2026-10-13",
        "input_identity")
    for name in ("recovered_tail_contribution_count", "fresh_contribution_count"):
        count = getattr(value, name)
        require(type(count) is int and count >= 0 and type(lineage.get(name)) is int
            and count == lineage[name], "input_identity")


def _parent_family(value, october_input):
    require(type(value) is predecessor.FamilyPlan and value._input is october_input,
        "parent_family_type")
    authority = predecessor._PLANS.get(id(value))
    require(authority is not None and authority[0]() is value
        and authority[1] == predecessor._fingerprint(value), "parent_family_authority")
    _input_authority(october_input)
    require(type(value.family_sha256) is str and value.family_sha256 == FAMILY_SHA256
        and sha(value.record_bytes) == FAMILY_SHA256 and len(value._projections) == 6,
        "parent_family_pin")
    record = json.loads(value.record_bytes)
    require(predecessor._canonical(record) == value.record_bytes
        and type(record.get("cells")) is list and len(record["cells"]) == 6,
        "parent_family_record")
    for index, ((candidate, size, arm), pins) in enumerate(zip(CELLS, PARENT_PINS, strict=True)):
        projected = value._projections[index]
        public = projected.to_record()
        profile = json.loads(projected.profile_bytes)
        require(projected.projection_sha256 == sha(projected.record_bytes) == pins[1]
            and profile["profile_sha256"] == public["profile_sha256"] == pins[0]
            and bridge.frozen.targets.canonical(profile) == projected.profile_bytes
            and profile["package_sha256"] == bridge.parent.PACKAGE
            and profile["lineage_sha256"] == bridge.parent.LINEAGE
            and profile["source_pins"] == bridge.parent.SOURCE_PINS
            and type(profile["universe_count"]) is int and profile["universe_count"] == size
            and type(profile["ar_percent"]) is int and profile["ar_percent"] == arm
            and record["cells"][index]["candidate_id"] == candidate
            and record["cells"][index]["projection_sha256"] == pins[1]
            and record["cells"][index]["profile_sha256"] == pins[0]
            and record["cells"][index]["source_files"] == public["source_files"]
            and tuple(item.project_path for item in projected.source_files) == bridge.parent.FILE_NAMES,
            "parent_cell_binding")
    return record


@dataclasses.dataclass(frozen=True, slots=True)
class PlainCell:
    candidate_id: str
    universe_count: int
    ar_percent: int
    projection_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_files: tuple = dataclasses.field(repr=False)

    def to_record(self):
        require(sha(self.record_bytes) == self.projection_sha256, "cell_changed")
        record, profile = json.loads(self.record_bytes), json.loads(self.profile_bytes)
        require(canonical(profile) == self.profile_bytes
            and record["candidate_id"] == self.candidate_id
            and record["profile_sha256"] == profile["profile_sha256"]
            and type(self.universe_count) is int and profile["universe_count"] == self.universe_count
            and type(self.ar_percent) is int and profile["ar_percent"] == self.ar_percent
            and record["source_files"] == [item.to_record() for item in self.source_files], "cell_changed")
        return record


@dataclasses.dataclass(frozen=True, slots=True)
class SpecificationCell:
    candidate_id: str
    universe_count: int
    ar_percent: int
    projection_sha256: str
    # R298's prior full checkpoint contains private-authenticated metadata.
    # Its fixed projection pin and generated public source are bound here;
    # the actual builder must additionally authenticate that original record.
    projection_record_bytes: bytes | None = dataclasses.field(repr=False)
    profile_bytes: bytes = dataclasses.field(repr=False)
    source_files: tuple = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class PlainSpecification:
    specification_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    cells: tuple = dataclasses.field(repr=False)

    def to_record(self):
        require(sha(self.record_bytes) == self.specification_sha256, "specification_changed")
        return json.loads(self.record_bytes)


def _public_sources(sources, expected_host_source_pins):
    expected_names = set(bridge.parent.SOURCE_PINS) | set(NEW_SOURCE_PINS) | {HOST_SOURCE_NAME}
    require(type(sources) is dict and set(sources) == expected_names
        and type(expected_host_source_pins) is dict
        and set(expected_host_source_pins) == {HOST_SOURCE_NAME}, "source_inventory")
    pins = {**bridge.parent.SOURCE_PINS, **NEW_SOURCE_PINS,
        HOST_SOURCE_NAME: bridge._hash(expected_host_source_pins[HOST_SOURCE_NAME])}
    for name, pin in pins.items():
        raw = sources[name]
        require(type(raw) is bytes and 0 < len(raw) <= 100000 and raw.isascii()
            and sha(raw) == pin, "source_pin")
    bridge._loader_shape(sources[bridge.LOADER_NAME])


def public_specification(*, sources, expected_host_source_pins):
    """Derive proposed public sources before outcomes, without input admission.

    Supply the thirteen fixed predecessor sources, three frozen plain sources
    and this host generator as bytes. No filesystem or private package is read.
    The exact historical R298 projection pin is a checkpoint reference, not a
    newly authenticated source admission or reconstruction of its full record.
    """
    _public_sources(sources, expected_host_source_pins)
    axis = bridge.frozen.october._sessions()
    old_sources = {name: sources[name] for name in bridge.parent.SOURCE_PINS}
    activation = SimpleNamespace(object_store_key=PLAIN_ACTIVATION[0],
        content_sha256=PLAIN_ACTIVATION[1], byte_count=PLAIN_ACTIVATION[2])
    old_activation = SimpleNamespace(object_store_key=bridge.parent.ACTIVATION[0],
        content_sha256=bridge.parent.ACTIVATION[1], byte_count=bridge.parent.ACTIVATION[2])
    loader = bridge.frozen.normalize(sources[bridge.LOADER_NAME], bridge.INPUT_NAME)
    bridge.frozen.audit(bridge.INPUT_NAME, loader)
    cells, geometry_hashes = [], set()
    for (candidate, size, arm), pins in zip(CELLS, PARENT_PINS, strict=True):
        old_profile = bridge.frozen.runtime.make_profile(axis, package_sha256=bridge.parent.PACKAGE,
            lineage_sha256=bridge.parent.LINEAGE, universe_count=size, ar_percent=arm,
            source_pins=dict(bridge.parent.SOURCE_PINS))
        old = bridge.frozen.render_projection(profile=old_profile, activation=old_activation, sources=old_sources)
        require(old_profile["profile_sha256"] == pins[0] and old.projection_sha256 == pins[1], "parent_cell_binding")
        profile = bridge.frozen.runtime.make_profile(axis, package_sha256=PLAIN_PACKAGE_SHA256,
            lineage_sha256=bridge.parent.LINEAGE, universe_count=size, ar_percent=arm,
            source_pins={**bridge.parent.SOURCE_PINS, **NEW_SOURCE_PINS})
        require(bridge._economic_profile(profile) == bridge._economic_profile(old_profile), "economic_profile_changed")
        old_files = {item.project_path: item.source_bytes for item in old.source_files}
        main = bridge.frozen.normalize(bridge.frozen.main_source(profile, activation, sources[bridge.TEMPLATE_NAME]), "main.py")
        require(bridge._main_shape(main) == bridge._main_shape(old_files["main.py"]), "main_semantics_changed")
        bridge.frozen.audit("main.py", main)
        files = tuple(bridge.frozen.SourceFile(name, main if name == "main.py" else
            loader if name == bridge.INPUT_NAME else old_files[name]) for name in bridge.parent.FILE_NAMES)
        geometry = sha(predecessor._canonical({key: profile[key] for key in (
            "session_axis_sha256", "session_count", "evaluation_sessions", "decision_sessions", "clock", "terminal")}))
        geometry_hashes.add(geometry)
        record = {"schema": CELL_SCHEMA, "candidate_id": candidate,
            "economic_candidate_id": profile["candidate_id"], "profile_sha256": profile["profile_sha256"],
            "parent_family_sha256": FAMILY_SHA256, "parent_projection_sha256": pins[1],
            "parent_profile_sha256": pins[0], "package_sha256": PLAIN_PACKAGE_SHA256,
            "lineage_sha256": bridge.parent.LINEAGE, "parent_proof_sha256": PLAIN_PROOF_SHA256,
            "activation_manifest_key": PLAIN_ACTIVATION[0], "activation_manifest_sha256": PLAIN_ACTIVATION[1],
            "activation_manifest_byte_count": PLAIN_ACTIVATION[2],
            "economic_profile_sha256": sha(canonical(bridge._economic_profile(profile))),
            "source_files": [item.to_record() for item in files], **FALSE_FLAGS}
        raw = canonical(record)
        if candidate == "R298":
            require(profile["profile_sha256"] == R298_PROFILE_SHA256, "r298_changed")
        cells.append(SpecificationCell(candidate, size, arm,
            R298_PROJECTION_SHA256 if candidate == "R298" else sha(raw),
            None if candidate == "R298" else raw, canonical(profile), files))
    require(len(geometry_hashes) == 1, "geometry")
    common = tuple(name for name in bridge.parent.FILE_NAMES if name != "main.py")
    require(len(common) == 10 and all(tuple((item.project_path, item.source_bytes) for item in cell.source_files
        if item.project_path in common) == tuple((item.project_path, item.source_bytes) for item in cells[0].source_files
        if item.project_path in common) for cell in cells), "common_sources")
    record = {"schema": "arv2-newrule-plain-comparison-public-specification-v1",
        "parent_family_sha256": FAMILY_SHA256, "package_sha256": PLAIN_PACKAGE_SHA256,
        "lineage_sha256": bridge.parent.LINEAGE, "parent_proof_sha256": PLAIN_PROOF_SHA256,
        "activation_manifest_key": PLAIN_ACTIVATION[0], "activation_manifest_sha256": PLAIN_ACTIVATION[1],
        "activation_manifest_byte_count": PLAIN_ACTIVATION[2],
        "host_source_pins": dict(expected_host_source_pins),
        "unchanged_cloud_files_across_cells": list(common),
        "r298_projection_record_requires_authenticated_checkpoint": True,
        "cells": [{"candidate_id": cell.candidate_id, "universe_count": cell.universe_count,
            "ar_percent": cell.ar_percent, "profile_sha256": json.loads(cell.profile_bytes)["profile_sha256"],
            "projection_sha256": cell.projection_sha256, "evaluation_geometry_sha256": next(iter(geometry_hashes)),
            "source_files": [item.to_record() for item in cell.source_files]} for cell in cells], **FALSE_FLAGS}
    raw = canonical(record)
    require(len(raw) <= 512 * 1024, "family_bound")
    return PlainSpecification(sha(raw), raw, tuple(cells))


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PlainComparison:
    family_sha256: str
    record_bytes: bytes = dataclasses.field(repr=False)
    cells: tuple = dataclasses.field(repr=False)
    _parent: object = dataclasses.field(repr=False)
    _transport: object = dataclasses.field(repr=False)

    def to_record(self):
        return require_plain_comparison(self)


def _fingerprint(value):
    require(type(value) is PlainComparison and type(value.family_sha256) is str
        and type(value.record_bytes) is bytes and type(value.cells) is tuple and len(value.cells) == 6,
        "family_type")
    rows = []
    for cell in value.cells:
        require(type(cell) is PlainCell and type(cell.candidate_id) is str
            and type(cell.universe_count) is int and type(cell.ar_percent) is int
            and type(cell.projection_sha256) is str and type(cell.record_bytes) is bytes
            and type(cell.profile_bytes) is bytes and type(cell.source_files) is tuple
            and all(type(item) is bridge.frozen.SourceFile and type(item.project_path) is str
                and type(item.source_bytes) is bytes for item in cell.source_files), "family_type")
        rows.append((cell.candidate_id, cell.universe_count, cell.ar_percent, cell.projection_sha256,
            cell.record_bytes, cell.profile_bytes,
            tuple((item.project_path, item.source_bytes) for item in cell.source_files)))
    return (value.family_sha256, value.record_bytes, id(value._parent), id(value._transport), tuple(rows))


def require_plain_comparison(value, expected_family_sha256=None):
    fingerprint = _fingerprint(value)
    with _LOCK:
        authority = _AUTHORITIES.get(id(value))
    require(authority is not None and authority[0]() is value
        and authority[1] == fingerprint and authority[2] == os.getpid(), "family_authority")
    _parent_family(value._parent, value._parent._input)
    bridge.transport.require_plain_transport(value._transport)
    require(sha(value.record_bytes) == value.family_sha256, "family_hash")
    if expected_family_sha256 is not None:
        require(bridge._hash(expected_family_sha256) == value.family_sha256, "family_pin")
    return json.loads(value.record_bytes)


def _forget(identity, reference):
    with _LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            del _AUTHORITIES[identity]


def build_plain_comparison(october_input, frozen_family, plain_transport, *, sources,
                           expected_host_source_pins):
    """Bind six in-memory arms, preserving the existing R298 checkpoint exactly.

    ``sources`` contains the seventeen public inputs used by the specification.
    This host generator's externally selected pin is retained only in the family.
    Returned bytes contain public code and metadata, never licensed data rows.
    """
    old_record = _parent_family(frozen_family, october_input)
    specification = public_specification(sources=sources, expected_host_source_pins=expected_host_source_pins)
    original_sources = {name: sources[name] for name in bridge.SOURCE_NAMES}
    _, inventory = bridge._plain_binding(plain_transport)
    require(plain_transport.package_sha256 == PLAIN_PACKAGE_SHA256
        and plain_transport.parent_proof_sha256 == PLAIN_PROOF_SHA256
        and (plain_transport.activation_manifest_key, plain_transport.activation_manifest_sha256,
            plain_transport.activation_manifest_byte_count) == PLAIN_ACTIVATION, "plain_checkpoint")
    first = bridge.build_plain_projection(frozen_family._projections[0], plain_transport,
        sources=original_sources, expected_new_source_pins=dict(NEW_SOURCE_PINS))
    require(first.projection_sha256 == R298_PROJECTION_SHA256, "r298_changed")
    cells = []
    for index, (selected, previous) in enumerate(zip(specification.cells, frozen_family._projections, strict=True)):
        if index == 0:
            record_bytes, files = first.record_bytes, first.source_files
            require(first.profile_bytes == selected.profile_bytes
                and first.source_files == selected.source_files, "r298_changed")
        else:
            old_files = {item.project_path: item.source_bytes for item in previous.source_files}
            record_bytes, files = selected.projection_record_bytes, selected.source_files
            require(all(item.source_bytes == old_files[item.project_path] for item in files
                if item.project_path not in ("main.py", bridge.INPUT_NAME)), "unchanged_sources")
        require(sha(record_bytes) == selected.projection_sha256, "specification_mismatch")
        cells.append(PlainCell(selected.candidate_id, selected.universe_count, selected.ar_percent,
            sha(record_bytes), record_bytes, selected.profile_bytes, files))
    common = tuple(name for name in bridge.parent.FILE_NAMES if name != "main.py")
    require(len(common) == 10 and all(tuple((item.project_path, item.source_bytes) for item in cell.source_files
        if item.project_path in common) == tuple((item.project_path, item.source_bytes) for item in cells[0].source_files
        if item.project_path in common) for cell in cells), "common_sources")
    geometry = old_record["cells"][0]["evaluation_geometry_sha256"]
    require(all(row["evaluation_geometry_sha256"] == geometry for row in old_record["cells"]), "geometry")
    record = {"schema": SCHEMA, "parent_family_sha256": FAMILY_SHA256,
        "public_specification_sha256": specification.specification_sha256,
        "package_sha256": plain_transport.package_sha256, "lineage_sha256": bridge.parent.LINEAGE,
        "parent_proof_sha256": plain_transport.parent_proof_sha256,
        "activation_manifest_key": plain_transport.activation_manifest_key,
        "activation_manifest_sha256": plain_transport.activation_manifest_sha256,
        "activation_manifest_byte_count": plain_transport.activation_manifest_byte_count,
        "upload_inventory": inventory, "upload_inventory_sha256": sha(canonical(inventory)),
        "total_upload_byte_count": plain_transport.total_upload_byte_count,
        "host_source_pins": dict(expected_host_source_pins), "unchanged_cloud_files_across_cells": list(common),
        "existing_r298_source_reused_exactly": True,
        "cells": [{"candidate_id": cell.candidate_id, "universe_count": cell.universe_count,
            "ar_percent": cell.ar_percent, "profile_sha256": json.loads(cell.profile_bytes)["profile_sha256"],
            "projection_sha256": cell.projection_sha256, "evaluation_geometry_sha256": geometry,
            "source_files": [item.to_record() for item in cell.source_files]} for cell in cells], **FALSE_FLAGS}
    raw = canonical(record)
    require(len(raw) <= 512 * 1024, "family_bound")
    result = PlainComparison(sha(raw), raw, tuple(cells), frozen_family, plain_transport)
    identity = id(result)
    reference = weakref.ref(result, lambda ref: _forget(identity, ref))
    with _LOCK:
        _AUTHORITIES[identity] = (reference, _fingerprint(result), os.getpid())
    require_plain_comparison(result)
    return result
