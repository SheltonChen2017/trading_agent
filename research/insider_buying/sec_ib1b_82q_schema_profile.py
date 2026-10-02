"""Offline, header-only schema profile for the 82 retained quarterly ZIPs.

All eight TSV first lines were inspected read-only in each retained archive:
SUBMISSION has one header through 2022Q4 and one from 2023Q1; the other
seven headers are unchanged. This extends only the *schema ranges* of the
previously pinned two-quarter pilot profile. It does not validate any row,
source-row key uniqueness, SEC origin, complete filing, acceptance time,
canonical identity, outcome, QuantConnect, or trading authority. No I/O is
performed by this module.
"""

from __future__ import annotations

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    SecBulkParsedSnapshotError,
    SecTsvSchemaProfile,
    SecTsvSchemaVariant,
)
from research.insider_buying.sec_bulk_snapshot import ALLOWED_SEC_TABLES
from research.insider_buying.sec_ib1b_pilot_profile import approved_ib1b_schema_profile


_PROFILE_ID = "IB1B-retained-2006Q1-2026Q2-observed-headers-v1"
RETAINED_82Q_SCHEMA_PROFILE_SHA256 = (
    "ee2f201362d4002a70819e4d7123eea300aafddb8820c6a0ab9761b0ed8cdd41"
)
_OBSERVED_HEADER_SHA256 = {
    "SUBMISSION.tsv": (
        "7500cd2ad9bac8264c6b1397eef0ba6141ea0738403a914f0d4e74657f92086d",
        "fc8c3f66d6e259fb7826fbe46cee2d6baaff49786f9b7c6a400c092f9b67cc6d",
    ),
    "REPORTINGOWNER.tsv": (
        "4b712596920a4e3b5a504c18ab233c858d9f3d701c5ddd3393a11b2c7854c4b7",
    ),
    "NONDERIV_TRANS.tsv": (
        "26483a4ee2354b1a5ccc663eb3185d08a10c17f172b541dd6e0a55d4c216c290",
    ),
    "NONDERIV_HOLDING.tsv": (
        "c1e6af74144f525da37766116a2ade6b045bb53d39f016cdabe1ba6942b54474",
    ),
    "DERIV_TRANS.tsv": (
        "0f8d910f6f5e29851f07126d2bfaaaa9ba5efedd14841a80868409cf667dd6b1",
    ),
    "DERIV_HOLDING.tsv": (
        "c77b4c43ad560d5b44c474149522be592fd3e3c8bf85c91579db95cc57b39784",
    ),
    "FOOTNOTES.tsv": (
        "4be9ffe6da5173b50125082dac0890f87bc25f2150010d06bbb7532604281aeb",
    ),
    "OWNER_SIGNATURE.tsv": (
        "dd9b7eb67a150e5244d4d46db94f15006301bc91cd0676d888879f08ce0eae73",
    ),
}
_PERIODS = tuple(
    (year, quarter)
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)


class Retained82qSchemaProfileError(ValueError):
    """The header-only profile no longer matches the retained observation."""


def _build_profile() -> SecTsvSchemaProfile:
    pilot = approved_ib1b_schema_profile()
    variants: list[SecTsvSchemaVariant] = []
    for item in pilot.variants:
        if item.table_name == "SUBMISSION.tsv":
            if (item.valid_from_year, item.valid_from_quarter) == (2022, 4):
                start, end = (2006, 1), (2022, 4)
            elif (item.valid_from_year, item.valid_from_quarter) == (2023, 1):
                start, end = (2023, 1), (2026, 2)
            else:
                raise Retained82qSchemaProfileError(
                    "REFUSED: unexpected pilot SUBMISSION schema range"
                )
        else:
            if (
                (item.valid_from_year, item.valid_from_quarter) != (2022, 4)
                or (item.valid_through_year, item.valid_through_quarter) != (2023, 1)
            ):
                raise Retained82qSchemaProfileError(
                    "REFUSED: unexpected pilot non-SUBMISSION schema range"
                )
            start, end = (2006, 1), (2026, 2)
        variants.append(
            SecTsvSchemaVariant(
                schema_id=(
                    "IB1B-retained-82Q-"
                    f"{item.table_name.removesuffix('.tsv')}-{start[0]}Q{start[1]}-"
                    f"{end[0]}Q{end[1]}-v1"
                ),
                table_name=item.table_name,
                headers=item.headers,
                source_row_key_headers=item.source_row_key_headers,
                valid_from_year=start[0],
                valid_from_quarter=start[1],
                valid_through_year=end[0],
                valid_through_quarter=end[1],
            )
        )
    return SecTsvSchemaProfile(_PROFILE_ID, tuple(variants))


def verify_retained_82q_schema_profile(profile: object) -> None:
    """Refuse any policy or header drift; never claim row or provenance proof."""
    if (
        type(profile) is not SecTsvSchemaProfile
        or type(profile.profile_id) is not str
        or profile.profile_id != _PROFILE_ID
        or type(profile.variants) is not tuple
        or len(profile.variants) != 9
        or any(type(item) is not SecTsvSchemaVariant for item in profile.variants)
    ):
        raise Retained82qSchemaProfileError(
            "REFUSED: retained 82-quarter profile shape or identity changed"
        )
    try:
        profile.__post_init__()
        if hash_payload(profile.to_payload()) != RETAINED_82Q_SCHEMA_PROFILE_SHA256:
            raise Retained82qSchemaProfileError(
                "REFUSED: retained 82-quarter profile fingerprint changed"
            )
        if tuple(dict.fromkeys(item.table_name for item in profile.variants)) != ALLOWED_SEC_TABLES:
            raise Retained82qSchemaProfileError(
                "REFUSED: retained 82-quarter table inventory changed"
            )
        for year, quarter in _PERIODS:
            for table in ALLOWED_SEC_TABLES:
                variant = profile.variant_for(table, year, quarter)
                if type(variant.headers) is not tuple or any(
                    type(header) is not str for header in variant.headers
                ):
                    raise Retained82qSchemaProfileError(
                        "REFUSED: retained 82-quarter header types changed"
                    )
                line = ("\t".join(variant.headers) + "\n").encode("ascii")
                digest = hash_bytes(line)
                observed = _OBSERVED_HEADER_SHA256[table]
                expected = observed[0 if (year, quarter) <= (2022, 4) else 1] if (
                    table == "SUBMISSION.tsv"
                ) else observed[0]
                if digest != expected:
                    raise Retained82qSchemaProfileError(
                        "REFUSED: retained 82-quarter header observation changed"
                    )
    except (SecBulkParsedSnapshotError, UnicodeError, AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, Retained82qSchemaProfileError):
            raise
        raise Retained82qSchemaProfileError(
            "REFUSED: retained 82-quarter profile is malformed"
        ) from exc


def build_retained_82q_schema_profile_candidate() -> SecTsvSchemaProfile:
    """Return a fresh unreviewed header-only profile with no outcome authority."""
    profile = _build_profile()
    verify_retained_82q_schema_profile(profile)
    return profile


__all__ = [
    "RETAINED_82Q_SCHEMA_PROFILE_SHA256",
    "Retained82qSchemaProfileError",
    "build_retained_82q_schema_profile_candidate",
    "verify_retained_82q_schema_profile",
]
