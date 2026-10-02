"""Owner-signature-gated private-file loader for a reviewed C2 package."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from research.analyst_revisions_v2.artifact_io import (
    ArtifactIOError,
    read_stable_regular,
)
from research.analyst_revisions_v2.preopen_control_acquisition import (
    PreopenControlAcquisitionReceipt,
)
from research.analyst_revisions_v2 import production_evidence_acquisition as core
from research.analyst_revisions_v2.production_evidence_acquisition import (
    MAX_PACKAGE_BYTES,
    MAX_REVIEW_PIN_BYTES,
    ProductionEvidenceAcquisitionError,
    ProductionEvidenceAcquisitionReceipt,
    require_production_evidence_acquisition_receipt,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    ProductionEvidenceAuthority,
)
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_production_evidence_review_owner_signature,
)


class ProductionEvidenceAcquisitionIoError(ValueError):
    """A private package or its review pin was unsafe or changed."""


def _private_regular(
    path: Path,
    *,
    name: str,
    maximum_bytes: int,
) -> tuple[Path, bytes]:
    try:
        resolved, payload = read_stable_regular(
            path,
            name=name,
            maximum_bytes=maximum_bytes,
        )
        metadata = os.stat(resolved, follow_symlinks=False)
    except (ArtifactIOError, OSError) as exc:
        raise ProductionEvidenceAcquisitionIoError(
            f"{name} is not a stable private regular file"
        ) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or (
            os.name != "nt"
            and (
                stat.S_IMODE(metadata.st_mode) != 0o600
                or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
            )
        )
    ):
        raise ProductionEvidenceAcquisitionIoError(
            f"{name} ownership, link count, or private mode changed"
        )
    return resolved, payload


def _load_physically_reviewed_production_evidence_receipt_implementation(
    *,
    authority: ProductionEvidenceAuthority,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    package_path: Path,
    external_review_pin_path: Path,
    owner_signature: OwnerSignatureAuthority,
    require_owner_signature,
) -> tuple[
    ProductionEvidenceAuthority,
    PreopenControlAcquisitionReceipt,
    bytes,
    bytes,
]:
    """Read, parse, cross-bind, and authenticate one physical C2 package."""

    package_resolved, package_bytes = _private_regular(
        package_path,
        name="production evidence package",
        maximum_bytes=MAX_PACKAGE_BYTES,
    )
    pin_resolved, pin_bytes = _private_regular(
        external_review_pin_path,
        name="production evidence external review pin",
        maximum_bytes=MAX_REVIEW_PIN_BYTES,
    )
    if package_resolved == pin_resolved:
        raise ProductionEvidenceAcquisitionIoError(
            "production evidence package and review pin must be distinct files"
    )
    try:
        require_owner_signature(owner_signature, authority_payload=pin_bytes)
        package_after_path, package_after = _private_regular(
            package_resolved,
            name="production evidence package",
            maximum_bytes=MAX_PACKAGE_BYTES,
        )
        pin_after_path, pin_after = _private_regular(
            pin_resolved,
            name="production evidence external review pin",
            maximum_bytes=MAX_REVIEW_PIN_BYTES,
        )
        if (
            package_after_path != package_resolved
            or pin_after_path != pin_resolved
            or package_after != package_bytes
            or pin_after != pin_bytes
        ):
            raise ProductionEvidenceAcquisitionIoError(
                "production evidence package or review pin changed after authentication"
            )
        return (
            authority,
            preopen_acquisition_receipt,
            package_bytes,
            pin_bytes,
        )
    except (
        ArtifactIOError,
        OwnerSignatureAuthorityError,
        ProductionEvidenceAcquisitionError,
    ) as exc:
        raise ProductionEvidenceAcquisitionIoError(
            "production evidence package failed physical authentication"
        ) from exc


def _make_physical_production_evidence_loader(
    implementation,
    owner_signature_requirer,
):
    receipt_minter = None
    loader_guard = None
    module_globals = globals()
    system_module = sys
    module_registry = system_module.modules
    module_name = __name__
    registered_module = module_registry.get(module_name)
    getpid = os.getpid
    authority_pid = getpid()
    exact_type = type
    exact_tuple = tuple
    any_true = any
    length = len
    read_vars = vars
    zip_strict = zip
    string_type = str
    missing = object()
    error_type = ProductionEvidenceAcquisitionIoError
    production_error_type = ProductionEvidenceAcquisitionError
    import inspect
    import json as json_dependency

    currentframe = inspect.currentframe
    function_type = exact_type(lambda: None)
    module_type = exact_type(system_module)
    static_method_type = staticmethod
    class_method_type = classmethod
    property_type = property
    guarded_classes = (
        json_dependency.JSONDecoder,
        json_dependency.JSONEncoder,
    )
    excluded_names = ("_seal_production_evidence_physical_loader",)

    def non_dunder_names() -> tuple[str, ...]:
        keys = exact_tuple(module_globals)
        if any_true(exact_type(name) is not string_type for name in keys):
            raise error_type(
                "production evidence physical loader global census changed"
            )
        return exact_tuple(
            name
            for name in keys
            if not name.startswith("__") and name not in excluded_names
        )

    def dependency_snapshot(roots):
        pending = list(roots)
        pending_classes = []
        seen: tuple[object, ...] = ()
        seen_classes: tuple[object, ...] = ()
        functions = []
        classes = []
        module_attributes = []
        while pending or pending_classes:
            if not pending:
                value_class = pending_classes.pop()
                if any_true(value_class is item for item in seen_classes):
                    continue
                seen_classes = (*seen_classes, value_class)
                class_namespace = read_vars(value_class)
                class_names = exact_tuple(class_namespace)
                class_bindings = exact_tuple(
                    (name, class_namespace[name]) for name in class_names
                )
                classes.append((value_class, class_names, class_bindings))
                for _name, attribute in class_bindings:
                    if exact_type(attribute) is function_type:
                        pending.append(attribute)
                    elif exact_type(attribute) in (
                        static_method_type,
                        class_method_type,
                    ):
                        pending.append(attribute.__func__)
                    elif exact_type(attribute) is property_type:
                        pending.extend(
                            item
                            for item in (
                                attribute.fget,
                                attribute.fset,
                                attribute.fdel,
                            )
                            if exact_type(item) is function_type
                        )
                continue
            function = pending.pop()
            if (
                function
                is load_physically_reviewed_production_evidence_receipt
                or exact_type(function) is not function_type
                or any_true(
                function is item for item in seen
                )
            ):
                continue
            seen = (*seen, function)
            code = function.__code__
            function_globals = function.__globals__
            names = exact_tuple(code.co_names)
            closure = function.__closure__ or ()
            closure_values = exact_tuple(cell.cell_contents for cell in closure)
            builtin_namespace = function.__builtins__
            builtin_mapping = (
                builtin_namespace
                if exact_type(builtin_namespace) is dict
                else read_vars(builtin_namespace)
            )
            global_bindings = exact_tuple(
                (name, function_globals.get(name, missing)) for name in names
            )
            builtin_bindings = exact_tuple(
                (name, builtin_mapping.get(name, missing))
                for name, value in global_bindings
                if value is missing
            )
            functions.append((
                function,
                code,
                function_globals,
                exact_tuple(code.co_freevars),
                closure_values,
                builtin_namespace,
                builtin_mapping,
                global_bindings,
                builtin_bindings,
            ))
            for _name, value in global_bindings:
                if exact_type(value) is function_type:
                    pending.append(value)
                elif exact_type(value) is module_type:
                    namespace = read_vars(value)
                    for name in names:
                        if name not in namespace:
                            continue
                        attribute = namespace[name]
                        module_attributes.append(
                            (value, namespace, name, attribute)
                        )
                        if exact_type(attribute) is function_type:
                            pending.append(attribute)
                        elif any_true(
                            attribute is item for item in guarded_classes
                        ):
                            pending_classes.append(attribute)
                elif any_true(value is item for item in guarded_classes):
                    pending_classes.append(value)
            pending.extend(
                value
                for value in closure_values
                if exact_type(value) is function_type
            )
            pending_classes.extend(
                value
                for value in closure_values
                if any_true(value is item for item in guarded_classes)
            )
        return (
            exact_tuple(functions),
            exact_tuple(classes),
            exact_tuple(module_attributes),
        )

    def load_physically_reviewed_production_evidence_receipt(
        *,
        authority: ProductionEvidenceAuthority,
        preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
        package_path: Path,
        external_review_pin_path: Path,
        owner_signature: OwnerSignatureAuthority,
    ) -> ProductionEvidenceAcquisitionReceipt:
        if loader_guard is None:
            raise error_type(
                "production evidence physical loader authority is not sealed"
            )
        loader_guard()
        verified = implementation(
            authority=authority,
            preopen_acquisition_receipt=preopen_acquisition_receipt,
            package_path=package_path,
            external_review_pin_path=external_review_pin_path,
            owner_signature=owner_signature,
            require_owner_signature=owner_signature_requirer,
        )
        if receipt_minter is None:
            raise error_type(
                "production evidence receipt authority is not installed"
            )
        try:
            return receipt_minter(
                authority=verified[0],
                preopen_acquisition_receipt=verified[1],
                package_bytes=verified[2],
                review_pin_bytes=verified[3],
            )
        except production_error_type as exc:
            raise error_type(
                "production evidence package failed physical authentication"
            ) from exc

    def bind_receipt_minter(value) -> None:
        nonlocal receipt_minter
        if receipt_minter is not None or exact_type(value) is not exact_type(
            load_physically_reviewed_production_evidence_receipt
        ):
            raise error_type(
                "production evidence receipt authority binding changed"
            )
        receipt_minter = value

    def seal_loader() -> None:
        nonlocal loader_guard
        if loader_guard is not None or receipt_minter is None:
            raise error_type("production evidence physical loader seal changed")
        if (
            system_module.modules is not module_registry
            or module_registry.get(module_name) is not registered_module
            or registered_module is None
            or read_vars(registered_module) is not module_globals
        ):
            raise error_type("production evidence physical loader module changed")
        expected_names = non_dunder_names()
        expected_globals = exact_tuple(
            (name, exact_type(module_globals[name]), module_globals[name])
            for name in expected_names
        )
        expected_code = (
            load_physically_reviewed_production_evidence_receipt.__code__
        )
        (
            expected_dependencies,
            expected_classes,
            expected_module_attributes,
        ) = dependency_snapshot((
                implementation,
                owner_signature_requirer,
                receipt_minter,
            ))
        expected_freevars: tuple[str, ...] = ()
        expected_bindings: tuple[tuple[str, object], ...] = ()

        def require_loader_authority() -> None:
            frame = currentframe()
            caller = None if frame is None else frame.f_back
            caller_globals = None if caller is None else caller.f_globals
            caller_code = None if caller is None else caller.f_code
            caller_locals = {} if caller is None else caller.f_locals
            if (
                getpid() != authority_pid
                or system_module.modules is not module_registry
                or module_registry.get(module_name) is not registered_module
                or read_vars(registered_module) is not module_globals
                or caller_globals is not module_globals
                or caller_code is not expected_code
                or module_globals.get(
                    "load_physically_reviewed_production_evidence_receipt",
                    missing,
                )
                is not load_physically_reviewed_production_evidence_receipt
                or exact_tuple(caller_code.co_freevars) != expected_freevars
                or any_true(
                    caller_locals.get(name, missing) is not expected
                    for name, expected in expected_bindings
                )
                or non_dunder_names() != expected_names
                or any_true(
                    exact_type(module_globals.get(name, missing))
                    is not expected_type
                    or module_globals.get(name, missing) is not expected
                    for name, expected_type, expected in expected_globals
                )
                or any_true(
                    exact_type(function) is not function_type
                    or function.__code__ is not code
                    or function.__globals__ is not function_globals
                    or exact_tuple(code.co_freevars) != freevars
                    or length(function.__closure__ or ())
                    != length(closure_values)
                    or any_true(
                        cell.cell_contents is not expected
                        for cell, expected in zip_strict(
                            function.__closure__ or (),
                            closure_values,
                            strict=True,
                        )
                    )
                    or function.__builtins__ is not builtin_namespace
                    or (
                        builtin_mapping is not builtin_namespace
                        and read_vars(builtin_namespace) is not builtin_mapping
                    )
                    or any_true(
                        function_globals.get(name, missing) is not expected
                        for name, expected in global_bindings
                    )
                    or any_true(
                        builtin_mapping.get(name, missing) is not expected
                        for name, expected in builtin_bindings
                    )
                    for (
                        function,
                        code,
                        function_globals,
                        freevars,
                        closure_values,
                        builtin_namespace,
                        builtin_mapping,
                        global_bindings,
                        builtin_bindings,
                    ) in expected_dependencies
                )
                or any_true(
                    read_vars(namespace) is not mapping
                    or mapping.get(name, missing) is not expected
                    for namespace, mapping, name, expected
                    in expected_module_attributes
                )
                or any_true(
                    exact_tuple(read_vars(value_class)) != class_names
                    or any_true(
                        read_vars(value_class).get(name, missing) is not expected
                        for name, expected in class_bindings
                    )
                    for value_class, class_names, class_bindings
                    in expected_classes
                )
            ):
                raise error_type(
                    "production evidence physical loader authority changed"
                )
            del caller
            del frame

        loader_guard = require_loader_authority
        expected_freevars = exact_tuple(expected_code.co_freevars)
        expected_bindings = exact_tuple(
            (name, cell.cell_contents)
            for name, cell in zip_strict(
                expected_freevars,
                load_physically_reviewed_production_evidence_receipt.__closure__
                or (),
                strict=True,
            )
        )

    return (
        load_physically_reviewed_production_evidence_receipt,
        bind_receipt_minter,
        seal_loader,
    )


(
    load_physically_reviewed_production_evidence_receipt,
    _bind_production_receipt_minter,
    _seal_production_evidence_physical_loader,
) = _make_physical_production_evidence_loader(
    _load_physically_reviewed_production_evidence_receipt_implementation,
    require_production_evidence_review_owner_signature,
)
_production_receipt_minter = core._claim_production_evidence_receipt_minter(
    load_physically_reviewed_production_evidence_receipt
)
_bind_production_receipt_minter(_production_receipt_minter)
del _make_physical_production_evidence_loader
del _bind_production_receipt_minter
del _load_physically_reviewed_production_evidence_receipt_implementation
del _production_receipt_minter
del require_production_evidence_review_owner_signature


__all__ = [
    "ProductionEvidenceAcquisitionIoError",
    "load_physically_reviewed_production_evidence_receipt",
]
_seal_production_evidence_physical_loader()
del _seal_production_evidence_physical_loader
