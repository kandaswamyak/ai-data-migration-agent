"""Migration Agent utilities.

Provides light-weight execution planning utilities for approved mappings.
"""

from collections import defaultdict
from typing import Dict, List, Any


class MigrationAgent:
    """Build and return a deterministic migration execution plan."""

    def execute_migration(self, approved_mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a table-wise migration plan from approved mappings.

        This method does not execute database operations directly. It validates
        approved mappings and returns a stable execution plan and summary that
        callers can use in migration pipelines.
        """
        if not approved_mappings:
            return {
                "success": False,
                "message": "No approved mappings provided.",
                "tables": [],
                "columns": 0,
                "plan": [],
            }

        plan_by_table = defaultdict(list)
        skipped = []

        for idx, mapping in enumerate(approved_mappings):
            if not mapping.get("approved", True):
                skipped.append({"index": idx, "reason": "not approved"})
                continue

            source_table = str(mapping.get("source_table", "")).strip()
            source_column = str(mapping.get("source_column", "")).strip()
            target_table = str(mapping.get("target_table", "")).strip()
            target_column = str(mapping.get("target_column", "")).strip()

            if not (source_table and source_column and target_table and target_column):
                skipped.append({"index": idx, "reason": "missing table/column metadata"})
                continue

            plan_by_table[target_table.upper()].append({
                "source_table": source_table.upper(),
                "source_column": source_column.upper(),
                "target_table": target_table.upper(),
                "target_column": target_column.upper(),
                "target_type": mapping.get("target_type", ""),
                "risk": mapping.get("risk", "Low"),
                "transformation": mapping.get("transformation", "Direct"),
            })

        ordered_tables = sorted(plan_by_table.keys())
        execution_plan = [{"table": table, "columns": plan_by_table[table]} for table in ordered_tables]
        total_columns = sum(len(item["columns"]) for item in execution_plan)

        return {
            "success": True,
            "message": "Migration plan generated.",
            "tables": len(execution_plan),
            "columns": total_columns,
            "skipped": skipped,
            "plan": execution_plan,
        }
