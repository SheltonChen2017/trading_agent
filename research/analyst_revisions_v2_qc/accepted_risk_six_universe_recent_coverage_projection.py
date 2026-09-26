"""Recent, count-only coverage diagnosis; historical source stays untouched.

The source is composed from the authenticated recent closure and exact edits
to the existing coverage diagnostic. No prices, orders or returns are read.
"""

import dataclasses
import hashlib
from pathlib import Path

from . import accepted_risk_six_universe_coverage_qc_projection as _old
from . import accepted_risk_six_universe_coverage_qc_runtime as _runtime
from . import accepted_risk_six_universe_order_tilt_recent_qc_projection as _recent


PROJECTION_SCHEMA = "arv2-six-universe-recent-coverage-projection-v2"
PROFILE_SCHEMA = "arv2-six-universe-recent-coverage-profile-v2"
PROFILE_ID = "arv2-six-universe-recent-coverage-counts-v2"
META_SCHEMA = "arv2-six-universe-recent-coverage-meta-v2"
SLEEVE_SCHEMA = "arv2-six-universe-recent-coverage-sleeve-v2"
MAPPING_FLOORS = (50, 60, 70, 80, 90)
CAP_FLOORS = (50, 60, 70, 80, 90)
WEIGHT_FLOORS = (25, 50, 75, 95)
GRID_AXES = {
    "mapping_percent": list(MAPPING_FLOORS),
    "cap_percent": list(CAP_FLOORS),
    "weight_percent": list(WEIGHT_FLOORS),
    "order": "mapping_then_cap_then_weight",
    "maximum_weight_percent": 105,
    "minimum_eligible_member_count": 5,
}


def _replace(source, old, new):
    if source.count(old) != 1:
        raise _old.SixUniverseCoverageQcProjectionError(
            "recent coverage source anchor changed"
        )
    return source.replace(old, new, 1)


def require_recent_coverage_profile():
    profile = _runtime.require_six_universe_coverage_profile()
    profile.pop("profile_sha256")
    profile.update({
        "schema": PROFILE_SCHEMA, "profile_id": PROFILE_ID,
        "evaluation_start_session": _recent.EVALUATION_START_SESSION,
        "evaluation_end_session": _recent.EVALUATION_END_SESSION,
        "decision_count": _recent.EXPECTED_DECISION_COUNT,
        "terminal_date": "2026-09-26", "candidate_grid_axes": GRID_AXES,
        "unmapped_positive_cap_count": True,
    })
    return {**profile, "profile_sha256": hashlib.sha256(_old._canonical(profile)).hexdigest()}


def _runtime_source():
    source = Path(_runtime.__file__).read_text(encoding="ascii")
    replacements = (
        ('PROFILE_SCHEMA = "arv2-six-universe-coverage-profile-v1"', f'PROFILE_SCHEMA = {PROFILE_SCHEMA!r}'),
        ('META_SCHEMA = "arv2-six-universe-coverage-meta-v1"', f'META_SCHEMA = {META_SCHEMA!r}'),
        ('SLEEVE_SCHEMA = "arv2-six-universe-coverage-sleeve-v1"', f'SLEEVE_SCHEMA = {SLEEVE_SCHEMA!r}'),
        ('EVALUATION_START_SESSION = "2021-01-04"', 'EVALUATION_START_SESSION = "2025-08-01"'),
        ('EVALUATION_END_SESSION = "2025-12-31"', 'EVALUATION_END_SESSION = "2026-09-25"'),
        ('EXPECTED_DECISION_COUNT = 261', 'EXPECTED_DECISION_COUNT = 61'),
        ('YEARS = (2021, 2022, 2023, 2024, 2025)', 'YEARS = (2025, 2026)'),
        ('"profile_id": "arv2-six-universe-coverage-counts-v1",', f'"profile_id": {PROFILE_ID!r},'),
        ('decisions[-1] != "2025-12-29"', 'decisions[-1] != "2026-09-21"'),
        ('if self._algorithm.time.date().isoformat() != EVALUATION_END_SESSION:',
         'if (self._algorithm.time.date().isoformat() != "2026-09-26"\n'
         '            or (self._algorithm.time.hour, self._algorithm.time.minute,\n'
         '                self._algorithm.time.second, self._algorithm.time.microsecond) != (0, 0, 0, 0)):'),
        ('    return {**seed, "profile_sha256": _sha(seed)}',
         '    seed.update({"terminal_date": "2026-09-26", "candidate_grid_axes": ' + repr(GRID_AXES) + ', "unmapped_positive_cap_count": True})\n    return {**seed, "profile_sha256": _sha(seed)}'),
        ('"reported_weight_bins": {"lt_95": 0, "in_95_105": 0, "gt_105": 0},',
         '"reported_weight_bins": {"lt_95": 0, "in_95_105": 0, "gt_105": 0},\n'
         '        "ratio_extrema": [None] * 6,\n'
         '        "unmapped_positive_cap_member_count_sum": 0,\n'
         '        "eligible_member_count_ge5_count": 0,\n'
         '        "eligible_member_count_ge10_count": 0,\n'
         '        "candidate_joint_counts": [0] * 100,'),
        ('"mapped_pit_cap_missing_member_count_sum": 0,\n        }',
         '"mapped_pit_cap_missing_member_count_sum": 0,\n'
         '            "unmapped_positive_cap_member_count_sum": 0,\n'
         '            "eligible_member_count": 0,\n        }'),
        ('result["unmapped_figi_member_count_sum"] += 1',
         'result["unmapped_figi_member_count_sum"] += 1\n'
         '                result["unmapped_positive_cap_member_count_sum"] += int(sid in caps)'),
        ('elif sid not in caps:\n                result["mapped_pit_cap_missing_member_count_sum"] += 1',
         'elif sid not in caps:\n                result["mapped_pit_cap_missing_member_count_sum"] += 1\n'
         '            else:\n                result["eligible_member_count"] += 1'),
        ('    counts["reported_weight_bins"][weight_bin] += 1',
         '    counts["reported_weight_bins"][weight_bin] += 1\n'
         '    _record_recent_counts(counts, measurement)'),
        ('def _counts_record(counts):\n    return {\n        name: _decimal_text(value) if type(value) is Decimal else value\n        for name, value in counts.items()\n    }',
         'def _counts_record(counts, *, grid=True):\n'
         '    result = {name: _decimal_text(value) if type(value) is Decimal else value\n'
         '              for name, value in counts.items() if grid or name != "candidate_joint_counts"}\n'
         '    result["ratio_extrema"] = [None if value is None else _decimal_text(value)\n'
         '                               for value in counts["ratio_extrema"]]\n'
         '    return result'),
        ('{"year": year, **_counts_record(counts[year])}', '{"year": year, **_counts_record(counts[year], grid=False)}'),
        ('"symbol_resolution_sha256": self._resolution.resolution_sha256,',
         '"symbol_resolution_sha256": self._resolution.resolution_sha256,\n'
         '            "resolver_counts": {"input": self._resolution.input_row_count,\n'
         '                                "resolved": self._resolution.resolved_count,\n'
         '                                "refused": self._resolution.named_refusal_count},\n'
         '            "resolver_refusal_reasons": {reason: sum(row["reason"] == reason for row in self._resolution.named_refusals)\n'
         '                for reason in sorted({row["reason"] for row in self._resolution.named_refusals})},\n'
         '            "candidate_grid_axes": ' + repr(GRID_AXES) + ','),
    )
    for old, new in replacements:
        source = _replace(source, old, new)
    helper = '''
def _record_recent_counts(counts, measurement):
    coverage = measurement["coverage"]
    values = (coverage.mapping_ratio, coverage.cap_weight_coverage_ratio,
              coverage.total_reported_weight)
    for index, value in enumerate(values):
        low, high = index * 2, index * 2 + 1
        if counts["ratio_extrema"][low] is None or value < counts["ratio_extrema"][low]:
            counts["ratio_extrema"][low] = value
        if counts["ratio_extrema"][high] is None or value > counts["ratio_extrema"][high]:
            counts["ratio_extrema"][high] = value
    eligible = measurement["eligible_member_count"]
    counts["unmapped_positive_cap_member_count_sum"] += measurement["unmapped_positive_cap_member_count_sum"]
    counts["eligible_member_count_ge5_count"] += int(eligible >= 5)
    counts["eligible_member_count_ge10_count"] += int(eligible >= 10)
    index = 0
    for mapping in (50, 60, 70, 80, 90):
        for cap in (50, 60, 70, 80, 90):
            for weight in (25, 50, 75, 95):
                passes = (eligible >= 5 and values[0] >= Decimal(mapping) / 100
                          and values[1] >= Decimal(cap) / 100
                          and Decimal(weight) / 100 <= values[2] <= Decimal("1.05"))
                counts["candidate_joint_counts"][index] += int(passes)
                index += 1

'''
    return _replace(source, "def _counts_record(counts, *, grid=True):", helper + "def _counts_record(counts, *, grid=True):").encode("ascii")


def _main_source(activation):
    source = _old._main_source(activation).decode("ascii")
    source = _replace(source, "self.set_start_date(2020, 11, 1)", "self.set_start_date(2025, 7, 24)")
    source = _replace(source, "self.set_end_date(2025, 12, 30)", "self.set_end_date(2026, 9, 25)")
    source = _replace(source,
        "        # The frozen coverage census pins on_end_of_algorithm to the session\n"
        "        # 2025-12-31 (EVALUATION_END_SESSION), so the end date must be the\n"
        "        # prior trading day, 2025-12-30, to land the termination clock on it.",
        "        # Recent counts include every decision through 2026-09-21.\n"
        "        # Ending on September 25 pins the terminal clock to September 26.")
    return source.encode("ascii")


def build_recent_coverage_projection(prior_package, latest_package):
    recent = _recent.build_corrected_short_window_tilt_projection(prior_package, latest_package, 100)
    by_path = {item.project_path: item for item in recent.source_files}
    files = [_old._source_file(path, by_path[path].source_bytes) for path in _old._SOURCE_PATHS[:-1]]
    files.append(_old._source_file(_old._SOURCE_PATHS[-1], _runtime_source()))
    activation = latest_package.upload_objects[-1]
    files.append(_old._source_file("main.py", _main_source(activation)))
    files = tuple(sorted(files, key=lambda item: item.project_path))
    total = sum(item.byte_count for item in files)
    if total > _old.MAXIMUM_TOTAL_SOURCE_BYTES:
        raise _old.SixUniverseCoverageQcProjectionError("recent coverage closure exceeded bound")
    profile = require_recent_coverage_profile()
    projection = _old.SixUniverseCoverageQcProjection(
        PROJECTION_SCHEMA, "pending", "0" * 64, PROFILE_ID, profile["profile_sha256"],
        recent.package_id, recent.package_sha256, recent.package_lineage_sha256,
        recent.activation_manifest_key, recent.activation_manifest_sha256,
        recent.activation_manifest_byte_count, files, total,
        _runtime.expected_custom_summary_statistic_names(),
    )
    semantic = {key: value for key, value in projection.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_old._canonical(semantic)).hexdigest()
    return dataclasses.replace(projection, projection_sha256=digest,
        projection_id="arv2-six-universe-recent-coverage-projection-" + digest[:24])
