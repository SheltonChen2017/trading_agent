"""Synthetic checks for the retained 82-quarter, header-only IB-1B profile."""

from dataclasses import replace

import pytest

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.sec_bulk_snapshot import ALLOWED_SEC_TABLES
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    RETAINED_82Q_SCHEMA_PROFILE_SHA256,
    Retained82qSchemaProfileError,
    build_retained_82q_schema_profile_candidate,
    verify_retained_82q_schema_profile,
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


def _periods():
    return tuple(
        (year, quarter)
        for year in range(2006, 2027)
        for quarter in range(1, 5)
        if (year, quarter) <= (2026, 2)
    )


def test_retained_profile_covers_every_table_and_quarter_with_observed_header_hash():
    profile = build_retained_82q_schema_profile_candidate()
    assert len(_periods()) == 82
    assert len(profile.variants) == 9
    assert tuple(dict.fromkeys(item.table_name for item in profile.variants)) == ALLOWED_SEC_TABLES
    assert hash_payload(profile.to_payload()) == RETAINED_82Q_SCHEMA_PROFILE_SHA256
    for year, quarter in _periods():
        for table in ALLOWED_SEC_TABLES:
            variant = profile.variant_for(table, year, quarter)
            digest = hash_bytes(("\t".join(variant.headers) + "\n").encode("ascii"))
            observed = _OBSERVED_HEADER_SHA256[table]
            if table == "SUBMISSION.tsv":
                assert digest == observed[0 if (year, quarter) <= (2022, 4) else 1]
            else:
                assert digest == observed[0]
    assert profile.variant_for("NONDERIV_TRANS.tsv", 2006, 1).source_row_key_headers == (
        "NONDERIV_TRANS_SK",
    )
    assert profile.variant_for("DERIV_TRANS.tsv", 2026, 2).source_row_key_headers == (
        "DERIV_TRANS_SK",
    )


@pytest.mark.parametrize("index", (0, 1, 2, 8))
def test_changed_header_or_range_cannot_retain_approved_profile_label(index):
    profile = build_retained_82q_schema_profile_candidate()
    variant = profile.variants[index]
    if index in (0, 1):
        changed = replace(variant, headers=variant.headers + ("INVENTED_COLUMN",))
    else:
        changed = replace(variant, valid_through_year=2025)
    variants = list(profile.variants)
    variants[index] = changed
    with pytest.raises(Retained82qSchemaProfileError, match="REFUSED"):
        verify_retained_82q_schema_profile(replace(profile, variants=tuple(variants)))


def test_profile_type_and_id_are_exact():
    profile = build_retained_82q_schema_profile_candidate()
    with pytest.raises(Retained82qSchemaProfileError, match="REFUSED"):
        verify_retained_82q_schema_profile(object())
    with pytest.raises(Retained82qSchemaProfileError, match="REFUSED"):
        verify_retained_82q_schema_profile(replace(profile, profile_id="unreviewed"))


def test_profile_is_noncanonical_and_has_no_acquisition_surface():
    module = __import__(
        "research.insider_buying.sec_ib1b_82q_schema_profile", fromlist=["__all__"]
    )
    assert module.__all__ == [
        "RETAINED_82Q_SCHEMA_PROFILE_SHA256",
        "Retained82qSchemaProfileError",
        "build_retained_82q_schema_profile_candidate",
        "verify_retained_82q_schema_profile",
    ]
    assert not hasattr(module, "run")
    assert not hasattr(module, "download")
