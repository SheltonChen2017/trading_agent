"""Fabricated prospective scope only; no credentials, HTTP or QC job."""
from pathlib import Path

import pytest

from data.hashing import hash_bytes
from scripts import read_short_interest_qc_engine_metadata as metadata


def test_runtime_cannot_rebind_registered_source_to_another_HEAD(monkeypatch, tmp_path):
    monkeypatch.setattr(metadata, "ROOT", tmp_path)
    monkeypatch.setattr(metadata, "PARENT", Path("scope"))
    monkeypatch.setattr(metadata, "_guard_lane", lambda *_args: None)
    monkeypatch.setattr(metadata, "_guard_remote", lambda *_args: None)
    observed = []
    monkeypatch.setattr(metadata, "capture_one", lambda *_args, **kwargs: observed.append(kwargs))
    registration = {
        "protocol": metadata.metadata_protocol(),
        "source_sha256": hash_bytes(Path(metadata.__file__).read_bytes()),
        "decision_id": "SI-DEC-FABRICATED-37",
        "registered_head": "a" * 40,
        "registered_remote": "b" * 40,
    }
    with pytest.raises(metadata.MetadataRefusal, match="protocol_refused"):
        metadata.run_metadata_observation(expected_head="c" * 40,
            expected_remote="b" * 40, frozen=registration, timestamp=1234567890)
    assert observed == []
    assert not (tmp_path / "scope").exists()
