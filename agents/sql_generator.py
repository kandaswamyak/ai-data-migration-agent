"""
AI-Powered SQL/DDL Generator Agent (Phase 5)

Generates CREATE TABLE DDL for Azure SQL based on approved mappings.
Uses AI to produce optimized DDL with indexes, constraints, and comments.
Falls back to rule-based generation if AI is unavailable.
"""

import json
import os
from agents.ai_engine import get_ai_engine


class SQLGenerator:

    def __init__(self, target_db="Azure SQL"):
        self.target_db = target_db
        self.ai = get_ai_engine()

    def generate_ddl(self, mappings):
        """
        Generate CREATE TABLE DDL from mappings.
        Uses AI for optimized DDL when available.
        """

        # Group by target table
        tables = {}
        for mapping in mappings:
            table = mapping.get("target_table", "UNKNOWN")
            if table not in tables:
                tables[table] = []
            tables[table].append(mapping)

        # Try AI generation
        if self.ai:
            try:
                return self._ai_generate_ddl(tables)
            except Exception as e:
                print(f"AI DDL generation failed, falling back to rules: {e}")

        # Fallback: rule-based
        return self._rule_based_ddl(tables)

    def _ai_generate_ddl(self, tables):
        """Use AI to generate optimized DDL."""

        ddl_statements = []

        for table_name, columns in tables.items():
            schema = columns[0].get("target_schema", "dbo")

            # Build column info for AI
            col_info = []
            for col in columns:
                col_info.append({
                    "name": col.get("target_column", ""),
                    "type": col.get("target_type", ""),
                    "nullable": col.get("nullable", "Y"),
                    "source_column": col.get("source_column", ""),
                    "source_type": col.get("source_type", ""),
                    "transformation": col.get("transformation", "Direct"),
                })

            prompt = f"""You are an Azure SQL Database expert.

Generate an optimized CREATE TABLE DDL statement for Azure SQL Database.

TABLE: [{schema}].[{table_name}]

COLUMNS:
{json.dumps(col_info, indent=2)}

Requirements:
1. Use proper Azure SQL syntax
2. Add a clustered index hint as a comment if you can identify a likely primary key
3. Add inline comments for any column that required type conversion
4. Use proper NULL/NOT NULL constraints
5. If a column name suggests it's a primary key (ID, _ID, _KEY), add PRIMARY KEY constraint
6. Add a header comment with the source table info
7. Do NOT add indexes as separate statements — only inline constraints

Return ONLY the SQL DDL statement. No markdown fences, no explanation."""

            ddl = self.ai.call(
                prompt,
                system_message="You are an Azure SQL DDL generation expert. Return only valid SQL."
            )

            # Clean up any remaining markdown
            ddl = ddl.replace("```sql", "").replace("```", "").strip()
            ddl_statements.append(ddl)

        return ddl_statements

    def _rule_based_ddl(self, tables):
        """Fallback: Generate DDL using templates."""

        ddl_statements = []

        for table_name, columns in tables.items():
            schema = columns[0].get("target_schema", "dbo")
            ddl = self._generate_create_table(schema, table_name, columns)
            ddl_statements.append(ddl)

        return ddl_statements

    def _generate_create_table(self, schema, table_name, columns):
        """Generate a single CREATE TABLE statement (rule-based)."""

        lines = []
        lines.append(f"-- Generated DDL for [{schema}].[{table_name}]")
        lines.append(f"CREATE TABLE [{schema}].[{table_name}]")
        lines.append("(")

        col_defs = []
        for col in columns:
            nullable = "NULL" if col.get("nullable", "Y") == "Y" else "NOT NULL"
            col_def = f"    [{col.get('target_column', '')}] {col.get('target_type', '')} {nullable}"
            col_defs.append(col_def)

        lines.append(",\n".join(col_defs))
        lines.append(");")

        return "\n".join(lines)

    def save_ddl(self, ddl_statements, file_path="data/migration_ddl.sql"):
        """Save DDL to a SQL file."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            for stmt in ddl_statements:
                f.write(stmt)
                f.write("\n\nGO\n\n")
        return file_path

    def generate_summary(self, ddl_statements):
        """Generate a human-readable summary."""
        return {
            "total_tables": len(ddl_statements),
            "status": "Generated - Pending Approval",
            "target": self.target_db,
            "ai_powered": self.ai is not None,
        }
