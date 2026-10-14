"""INACTIVE invocation bytes: paste only after external durable one-shot start.

The exact committed cell is a separate source image. The supervisor supplies
the separate, hash-bound control-input cell as _SDK_METADATA_CONTROL. This file
does not embed its own hash or a future receipt hash, avoiding circular lineage.
This is an explicit execution cell, not an importable library or startup hook.
Never import/run it locally or repeat it after a kernel reset.
"""
_SDK_METADATA_OBSERVATION = inspect_loaded_sdk_once(
    registration_raw=_SDK_METADATA_CONTROL["registration_raw"],
    registration_sha256=_SDK_METADATA_CONTROL["registration_sha256"],
    start_raw=_SDK_METADATA_CONTROL["start_raw"],
    start_sha256=_SDK_METADATA_CONTROL["start_sha256"],
    execution_source_sha256=_SDK_METADATA_CONTROL["execution_source_sha256"],
)
print(_raw(_SDK_METADATA_OBSERVATION).decode("ascii"))

