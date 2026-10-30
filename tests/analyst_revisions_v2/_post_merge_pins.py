"""Post-merge view of spent callers' source pins (section 330, ARV2R328-007).

The approved EOF merge (ARV2R323-002, ARV2CR325-002) changed exactly the two
R298 sources listed in Codex's post-merge manifest. Spent callers keep their
historical pins unchanged; their closure tests compare the current tree with
that manifest's exact replacement pin. Nothing is refreshed from disk, and any
other drift still fails.
"""
from scripts import arv2_r298_post_merge_source_pins as manifest

_REPLACED = {(path, old): new for path, old, new in manifest.REPLACEMENTS}


def current_pin(name, pin):
    """Return the pin the current tree must match for one historical entry."""
    return _REPLACED.get((str(name), pin), pin)
