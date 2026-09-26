"""Isolating tests for the separately frozen six-universe recent window."""

import copy

import pytest

from research.analyst_revisions_v2_qc import six_universe_cap90_submission as cap90
from tests.analyst_revisions_v2 import test_qc_six_universe_settlement_submission as legacy


GEOMETRY = ("2025-08-01", "2026-09-25", 290, 61)


def _recent_base_aggregate():
    aggregate, _candidate = legacy._aggregate("R195")
    aggregate["account"].update({
        "first_observation_session": GEOMETRY[0],
        "last_observation_session": GEOMETRY[1],
        "observation_count": GEOMETRY[2],
    })
    aggregate["execution"]["decision_count"] = GEOMETRY[3]
    for row in aggregate["sleeve_diagnostics"]["rows"]:
        row[2] = GEOMETRY[3]
    aggregate["fallback_counts"] = {
        key: (6 * GEOMETRY[3] if index == 0 else 0)
        for index, key in enumerate(aggregate["fallback_counts"])
    }
    return {key: aggregate[key] for key in cap90._AGGREGATE_FIELDS}


def test_recent_geometry_is_separate_from_unchanged_default():
    aggregate = _recent_base_aggregate()
    projected = cap90._project_aggregate(aggregate, expected_geometry=GEOMETRY)
    assert projected["account"]["observation_count"] == 290
    assert projected["account"]["first_observation_session"] == GEOMETRY[0]
    assert projected["account"]["last_observation_session"] == GEOMETRY[1]
    with pytest.raises(cap90.Cap90QcSubmissionError, match="nested aggregate"):
        cap90._project_aggregate(aggregate)
    prior_aggregate, _candidate = legacy._aggregate("R195")
    old_base = {key: prior_aggregate[key] for key in cap90._AGGREGATE_FIELDS}
    assert cap90._project_aggregate(old_base)["account"]["observation_count"] == 1255
    with pytest.raises(cap90.Cap90QcSubmissionError, match="nested aggregate"):
        cap90._project_aggregate(old_base, expected_geometry=GEOMETRY)


@pytest.mark.parametrize("geometry", (
    ("2025-08-01", "2026-09-25", 289, 61),
    ("2025-08-01", "2026-09-24", 290, 61),
    ("2025-08-01", "2026-09-25", 290, True),
    ["2025-08-01", "2026-09-25", 290, 61],
    ("2025-08-01", "2026-09-25", 290),
))
def test_recent_geometry_cannot_be_caller_authored(geometry):
    with pytest.raises(cap90.Cap90QcSubmissionError, match="authorized literal window"):
        cap90._project_aggregate(_recent_base_aggregate(), expected_geometry=geometry)


@pytest.mark.parametrize("defect", (
    "first", "last", "observations", "decisions", "sleeve_decisions", "fallback_census",
))
def test_recent_geometry_reader_isolates_each_required_census(defect):
    aggregate = copy.deepcopy(_recent_base_aggregate())
    if defect == "first":
        aggregate["account"]["first_observation_session"] = "2021-01-04"
    elif defect == "last":
        aggregate["account"]["last_observation_session"] = "2025-12-31"
    elif defect == "observations":
        aggregate["account"]["observation_count"] = 289
    elif defect == "decisions":
        aggregate["execution"]["decision_count"] = 60
    elif defect == "sleeve_decisions":
        aggregate["sleeve_diagnostics"]["rows"][0][2] = 60
    elif defect == "fallback_census":
        key = next(iter(aggregate["fallback_counts"]))
        aggregate["fallback_counts"][key] -= 1
    with pytest.raises(cap90.Cap90QcSubmissionError):
        cap90._project_aggregate(aggregate, expected_geometry=GEOMETRY)
