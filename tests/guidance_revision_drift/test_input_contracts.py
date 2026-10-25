"""Structural input primitives never relax exact decimal or custody boundaries."""
from __future__ import annotations

from decimal import Decimal, localcontext
import unittest
from unittest.mock import patch

from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, decode_object, digest, identifier, keys, utc,
)


class InputContractTests(unittest.TestCase):
    def test_provider_numeric_tokens_are_exact_under_hostile_context(self):
        with localcontext() as ctx:
            ctx.prec = 2
            result = decode_object(b'{"price":1.234567890123456789,"ns":1750000000000000001}', provider_numbers=True)
            self.assertEqual(result["price"], Decimal("1.234567890123456789"))
            self.assertEqual(result["ns"], 1750000000000000001)
            self.assertEqual(amount("1.234567890123456789"), result["price"])
        self.assertIs(type(result["price"]), Decimal)

    def test_strict_json_rejects_aliases_nonfinite_duplicates_and_limits(self):
        for raw in (b"", b"[]", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}',
                    b'{"x":Infinity}', b'{"x":1.1}', b'{"x":'+ b'9'*66 + b'}'):
            with self.subTest(raw=raw[:40]), self.assertRaises(InputError):
                decode_object(raw)
        for raw in (b'{"x":1e9999999999999999999999999}', b'{"x":1e-9999}', b'{"x":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(InputError):
                decode_object(raw, provider_numbers=True)
        for raw, maximum, mode in ((bytearray(b"{}"), 100, False), (b"{}", True, False),
                                   (b"{}", 1, False), (b"{}", 100, 1)):
            with self.subTest(maximum=maximum), self.assertRaises(InputError):
                decode_object(raw, maximum, provider_numbers=mode)

    def test_exact_amount_types_precision_sign_and_projection(self):
        for value in (True, 1.2, None, " 1", "1e2", "+1", "01", "NaN", Decimal("Infinity"),
                      Decimal("1e-33"), Decimal("9"*65), 10**65, 10**5000):
            with self.subTest(value=value), self.assertRaises(InputError):
                amount(value)
        self.assertEqual(amount("-1.5"), Decimal("-1.5"))
        with self.assertRaises(InputError):
            amount("-1", nonnegative=True)
        with self.assertRaises(InputError):
            amount("0", positive=True)
        for body in ({"v": 1.1}, {"v": Decimal("1.1")}, {True: "v"}):
            with self.subTest(body=body), self.assertRaises(InputError):
                canonical_bytes(body)
        self.assertEqual(canonical_bytes({"v": "1.1", "n": 2}), b'{"n":2,"v":"1.1"}')

    def test_dates_ids_and_digests_refuse_bad_inputs_without_echo(self):
        self.assertEqual(utc("2025-01-02T03:04:05.123456Z").microsecond, 123456)
        self.assertEqual(day("2025-01-02").isoformat(), "2025-01-02")
        for clock in ("2025-01-02T03:04:05", "2025-01-02T03:04:05+00:00", "2025-02-30T00:00:00Z", True):
            with self.subTest(clock=clock), self.assertRaises(InputError):
                utc(clock)
        for value in ("2025-1-1", "2025-02-30", True):
            with self.subTest(value=value), self.assertRaises(InputError):
                day(value)
        self.assertEqual(identifier("TEST-I:1"), "TEST-I:1")
        for value in ("SECRET?bad", "../source", "é", "x" * 129, True):
            with self.subTest(value=value), self.assertRaises(InputError) as caught:
                identifier(value)
            self.assertNotIn("SECRET", str(caught.exception))
        for value in ("A"*64, "0"*63, True):
            with self.assertRaises(InputError):
                digest(value)
        self.assertEqual(digest("0"*64), "0"*64)
        with self.assertRaises(InputError):
            keys({"a": 1, "extra": True}, {"a"})

    def test_primitives_have_no_side_effect_seams(self):
        with patch("builtins.open", side_effect=AssertionError("file forbidden")), \
             patch("os.getenv", side_effect=AssertionError("environment forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("process forbidden")):
            self.assertEqual(decode_object(canonical_bytes({"value": "1.20"})), {"value": "1.20"})


if __name__ == "__main__":
    unittest.main()
