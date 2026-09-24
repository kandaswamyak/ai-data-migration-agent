import unittest
import math
from decimal import Decimal
from datetime import datetime, date

from dashboard.flask_app import (
    normalize_azure_sql_type,
    normalize_migration_cell,
    sanitize_azure_sql_ddl_types,
)


class FlaskMigrationSanitizationTests(unittest.TestCase):

    def test_sanitizes_oracle_timestamp_with_time_zone_for_azure_sql(self):
        ddl = (
            "[CREATED_TZ] TIMESTAMP(6) WITH TIME ZONE NULL, "
            "[CREATED_LOCAL_TZ] TIMESTAMP(6) WITH LOCAL TIME ZONE NULL"
        )

        sanitized = sanitize_azure_sql_ddl_types(ddl)

        self.assertNotIn("WITH TIME ZONE", sanitized.upper())
        self.assertNotIn("WITH LOCAL TIME ZONE", sanitized.upper())
        self.assertEqual(sanitized.count("DATETIMEOFFSET(7)"), 2)

    def test_normalizes_target_type_from_oracle_timestamp_with_time_zone(self):
        self.assertEqual(
            normalize_azure_sql_type("TIMESTAMP(6) WITH TIME ZONE", "TIMESTAMP(6) WITH TIME ZONE"),
            "DATETIMEOFFSET(7)",
        )

    def test_normalizes_object_with_invalid_str_returning_bytes(self):
        class BrokenString:
            def __str__(self):
                return b"raw-bytes"

            def __bytes__(self):
                return b"raw-bytes"

        self.assertEqual(normalize_migration_cell(BrokenString()), b"raw-bytes")

    # ---- New tests for ODBC 22018 fix ----

    def test_normalizes_nan_float_to_none(self):
        self.assertIsNone(normalize_migration_cell(float("nan")))

    def test_normalizes_inf_float_to_none(self):
        self.assertIsNone(normalize_migration_cell(float("inf")))

    def test_normalizes_neg_inf_float_to_none(self):
        self.assertIsNone(normalize_migration_cell(float("-inf")))

    def test_preserves_normal_float(self):
        self.assertEqual(normalize_migration_cell(3.14), 3.14)

    def test_normalizes_nan_decimal_to_none(self):
        self.assertIsNone(normalize_migration_cell(Decimal("NaN")))

    def test_normalizes_inf_decimal_to_none(self):
        self.assertIsNone(normalize_migration_cell(Decimal("Infinity")))

    def test_preserves_normal_decimal(self):
        val = Decimal("12345.67")
        self.assertEqual(normalize_migration_cell(val), val)

    def test_extreme_decimal_over_38_digits_converted_to_float(self):
        # 39 digits → exceeds SQL DECIMAL(38) → should become float
        val = Decimal("1" * 39)
        result = normalize_migration_cell(val)
        self.assertIsInstance(result, float)

    def test_bytes_stays_bytes_for_varbinary(self):
        val = b"\x00\x11\x22\x33"
        result = normalize_migration_cell(val)
        self.assertIsInstance(result, bytes)
        self.assertEqual(result, val)

    def test_bytearray_becomes_bytes(self):
        val = bytearray(b"\xAA\xBB")
        result = normalize_migration_cell(val)
        self.assertIsInstance(result, bytes)

    def test_lob_object_read(self):
        """Simulates cx_Oracle LOB object with .read() method."""
        class FakeLOB:
            def read(self):
                return "CLOB text content"
        self.assertEqual(normalize_migration_cell(FakeLOB()), "CLOB text content")

    def test_lob_binary_read(self):
        class FakeBLOB:
            def read(self):
                return b"\x48\x65\x6C\x6C\x6F"
        result = normalize_migration_cell(FakeBLOB())
        self.assertIsInstance(result, bytes)

    def test_interval_object_becomes_string(self):
        class FakeIntervalYM:
            __name__ = "IntervalYM"
            def __str__(self):
                return "+02-06"
        # Rename the class so type_name check works
        FakeIntervalYM.__name__ = "IntervalYM"
        self.assertEqual(normalize_migration_cell(FakeIntervalYM()), "+02-06")

    def test_preserves_datetime(self):
        val = datetime(2026, 9, 19, 10, 30, 45)
        self.assertEqual(normalize_migration_cell(val), val)


if __name__ == "__main__":
    unittest.main()
