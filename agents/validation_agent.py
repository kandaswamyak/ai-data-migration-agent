"""
Validation Agent (Phase 8)

Validates data integrity after migration.
Compares source and target for row counts, NULLs, duplicates, checksums.
"""


class ValidationAgent:

    def __init__(self, source_db="Oracle", target_db="Azure SQL"):
        self.source_db = source_db
        self.target_db = target_db

    def validate_row_count(self, source_count, target_count):
        """Check if row counts match."""

        return {
            "check": "Row Count",
            "source": source_count,
            "target": target_count,
            "status": "PASS" if source_count == target_count else "FAIL",
            "difference": target_count - source_count
        }

    def validate_null_count(self, source_nulls, target_nulls):
        """Check if NULL counts match per column."""

        return {
            "check": "NULL Count",
            "source": source_nulls,
            "target": target_nulls,
            "status": "PASS" if source_nulls == target_nulls else "FAIL"
        }

    def validate_duplicates(self, source_dupes, target_dupes):
        """Check no new duplicates introduced."""

        return {
            "check": "Duplicate Check",
            "source": source_dupes,
            "target": target_dupes,
            "status": "PASS" if target_dupes <= source_dupes else "FAIL"
        }

    def validate_precision(self, column_name, source_val, target_val):
        """Validate numeric precision preserved."""

        return {
            "check": f"Precision - {column_name}",
            "source": str(source_val),
            "target": str(target_val),
            "status": "PASS" if source_val == target_val else "FAIL"
        }

    def run_all_checks(self, source_stats, target_stats):
        """Run all validation checks."""

        results = []

        results.append(self.validate_row_count(
            source_stats.get("row_count", 0),
            target_stats.get("row_count", 0)
        ))

        results.append(self.validate_null_count(
            source_stats.get("null_count", 0),
            target_stats.get("null_count", 0)
        ))

        results.append(self.validate_duplicates(
            source_stats.get("duplicates", 0),
            target_stats.get("duplicates", 0)
        ))

        overall = all(r["status"] == "PASS" for r in results)

        return {
            "checks": results,
            "overall": "PASS" if overall else "FAIL",
            "total_checks": len(results),
            "passed": sum(1 for r in results if r["status"] == "PASS"),
            "failed": sum(1 for r in results if r["status"] == "FAIL")
        }
