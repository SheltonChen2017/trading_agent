from __future__ import annotations

import pandas as pd
import pytest

from ml.transforms import (
    TransformError,
    add_cross_sectional_transforms,
    apply_training_standardizer,
    fit_training_standardizer,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "as_of_session": [
                "2026-01-02",
                "2026-01-02",
                "2026-01-02",
                "2026-01-05",
                "2026-01-05",
                "2026-01-05",
            ],
            "ticker": ["AAA", "BBB", "CCC", "AAA", "BBB", "CCC"],
            "momentum": [1.0, 2.0, 100.0, 3.0, 4.0, 5.0],
        }
    )


def test_cross_sectional_transforms_are_computed_within_each_session():
    result = add_cross_sectional_transforms(_frame(), ["momentum"])

    first_session = result[result["as_of_session"] == "2026-01-02"]
    assert first_session["momentum__xs_percentile"].tolist() == pytest.approx(
        [1 / 3, 2 / 3, 1.0]
    )
    assert first_session["momentum__xs_robust_z"].iloc[1] == pytest.approx(0.0)
    second_session = result[result["as_of_session"] == "2026-01-05"]
    assert second_session["momentum__xs_percentile"].tolist() == pytest.approx(
        [1 / 3, 2 / 3, 1.0]
    )


def test_zero_cross_sectional_dispersion_yields_missing_robust_z_not_infinity():
    frame = _frame()
    frame.loc[:2, "momentum"] = 7.0
    result = add_cross_sectional_transforms(frame, ["momentum"])
    assert result.loc[:2, "momentum__xs_robust_z"].isna().all()


def test_standardizer_fits_only_explicit_training_rows():
    frame = _frame()
    training_indices = (0, 1, 3, 4)
    standardizer = fit_training_standardizer(
        frame, ["momentum"], train_row_indices=training_indices
    )

    assert standardizer.means["momentum"] == pytest.approx(2.5)
    original_scale = standardizer.scales["momentum"]

    # Validation-only outliers must not alter learned parameters.
    mutated = frame.copy()
    mutated.loc[[2, 5], "momentum"] = [1e9, -1e9]
    refit = fit_training_standardizer(
        mutated, ["momentum"], train_row_indices=training_indices
    )
    assert refit.means == standardizer.means
    assert refit.scales == standardizer.scales

    transformed = apply_training_standardizer(mutated, standardizer)
    assert transformed.loc[0, "momentum__standardized"] == pytest.approx(
        (1.0 - 2.5) / original_scale
    )


def test_standardizer_rejects_infinite_feature_values():
    frame = _frame()
    frame.loc[0, "momentum"] = float("inf")
    with pytest.raises(TransformError, match="infinity"):
        fit_training_standardizer(frame, ["momentum"], train_row_indices=(0, 1))


def test_transforms_reject_duplicate_point_in_time_keys():
    frame = pd.concat([_frame(), _frame().iloc[:1]], ignore_index=True)
    with pytest.raises(TransformError, match="duplicate"):
        add_cross_sectional_transforms(frame, ["momentum"])
