"""
AI Report Generator Agent (Phase 9)

Generates executive-level migration reports using AI.
Summarizes the entire migration lifecycle with recommendations.
"""

import json
from datetime import datetime
from agents.ai_engine import get_ai_engine


class ReportAgent:
    """AI-powered migration report generator."""

    def __init__(self):
        self.ai = get_ai_engine()

    def generate_executive_summary(self, migration_context: dict) -> str:
        """
        Generate an AI-powered executive summary of the migration.

        Args:
            migration_context: Dict with all migration state data

        Returns:
            Markdown-formatted executive summary string
        """

        if not self.ai:
            return self._fallback_summary(migration_context)

        try:
            return self._ai_summary(migration_context)
        except Exception as e:
            print(f"AI report generation failed: {e}")
            return self._fallback_summary(migration_context)

    def _ai_summary(self, ctx: dict) -> str:
        """Generate AI-powered executive summary."""

        # Build context
        context_parts = []
        context_parts.append(f"Migration Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        context_parts.append(f"Source: {ctx.get('source_type', 'Oracle')} Database")
        context_parts.append(f"Target: Azure SQL Database")

        # Schema info
        schema = ctx.get("schema")
        if schema is not None:
            if hasattr(schema, "__len__"):
                context_parts.append(f"Total columns discovered: {len(schema)}")

        # Mappings
        mappings = ctx.get("mappings", [])
        if mappings:
            tables = set(m.get("source_table", "") for m in mappings)
            context_parts.append(f"Tables migrated: {len(tables)} ({', '.join(tables)})")
            context_parts.append(f"Columns mapped: {len(mappings)}")

            high_risk = sum(1 for m in mappings if m.get("risk") == "High")
            medium_risk = sum(1 for m in mappings if m.get("risk") == "Medium")
            low_risk = sum(1 for m in mappings if m.get("risk") == "Low")
            context_parts.append(f"Risk profile: {low_risk} Low, {medium_risk} Medium, {high_risk} High")

            # Type conversions
            conversions = []
            for m in mappings:
                if m.get("source_type") != m.get("target_type"):
                    conversions.append(f"{m.get('source_type')} -> {m.get('target_type')}")
            if conversions:
                context_parts.append(f"Type conversions: {', '.join(set(conversions))}")

        # DDL
        ddl = ctx.get("ddl_statements", [])
        if ddl:
            context_parts.append(f"DDL statements generated: {len(ddl)}")

        # Migration and validation
        if ctx.get("migration_executed"):
            context_parts.append("Migration status: EXECUTED")
        if ctx.get("validation_complete"):
            context_parts.append("Validation: ALL CHECKS PASSED")

        prompt = f"""You are a data migration consultant writing an executive summary report.

MIGRATION DETAILS:
{chr(10).join(context_parts)}

Write a professional executive summary (300-400 words) that includes:
1. **Overview** - What was migrated and why
2. **Scope** - Tables, columns, type conversions performed
3. **Risk Assessment** - Summary of risks identified and how they were handled
4. **Validation Results** - Confirmation of data integrity
5. **Recommendations** - Next steps for production migration

Format in markdown. Be professional and concise. This is for C-level stakeholders."""

        return self.ai.call(
            prompt,
            system_message="You are a senior data migration consultant. Write professional, concise executive reports.",
            temperature=0.3
        )

    def _fallback_summary(self, ctx: dict) -> str:
        """Generate a rule-based summary without AI."""

        mappings = ctx.get("mappings", [])
        tables = set(m.get("source_table", "") for m in mappings) if mappings else set()

        lines = [
            "## Executive Migration Summary\n",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Source:** {ctx.get('source_type', 'Oracle')} Database",
            f"**Target:** Azure SQL Database",
            "",
            "### Scope",
            f"- Tables migrated: {len(tables)}",
            f"- Columns mapped: {len(mappings)}",
            "",
            "### Risk Profile",
        ]

        if mappings:
            high = sum(1 for m in mappings if m.get("risk") == "High")
            medium = sum(1 for m in mappings if m.get("risk") == "Medium")
            low = sum(1 for m in mappings if m.get("risk") == "Low")
            lines.append(f"- Low Risk: {low} columns")
            lines.append(f"- Medium Risk: {medium} columns")
            lines.append(f"- High Risk: {high} columns")
        else:
            lines.append("- No mappings available")

        lines.append("")
        lines.append("### Validation")
        if ctx.get("validation_complete"):
            lines.append("- All validation checks PASSED")
        else:
            lines.append("- Validation pending")

        lines.append("")
        lines.append("### Recommendations")
        lines.append("1. Review VARCHAR2 to NVARCHAR conversions for Unicode requirements.")
        lines.append("2. Validate Oracle DATE to DATETIME2 time precision.")
        lines.append("3. Verify CLOB to NVARCHAR(MAX) data size limits.")
        lines.append("4. Confirm NUMBER precision/scale mappings with business owners.")
        lines.append("5. Run performance benchmarks on Azure SQL target.")

        return "\n".join(lines)

    def generate_recommendations(self, mappings: list) -> list:
        """Generate AI-powered recommendations list."""

        if not self.ai or not mappings:
            return [
                "Review VARCHAR2 to NVARCHAR conversions for Unicode requirements.",
                "Validate Oracle DATE to DATETIME2 time precision.",
                "Verify CLOB to NVARCHAR(MAX) data size limits.",
                "Confirm NUMBER precision/scale mappings with business owners.",
                "Run performance benchmarks on Azure SQL target.",
            ]

        try:
            prompt = f"""Given these migration mappings, provide 5 specific actionable recommendations
for production migration. Focus on data integrity, performance, and risk mitigation.

MAPPINGS SUMMARY:
- Total columns: {len(mappings)}
- High risk: {sum(1 for m in mappings if m.get('risk') == 'High')}
- Type conversions: {sum(1 for m in mappings if m.get('transformation') != 'Direct')}

Return as a JSON array of strings. Each string is one recommendation."""

            result = self.ai.call_json(prompt)
            if isinstance(result, list):
                return result
        except Exception:
            pass

        return [
            "Review all type conversions for data loss potential.",
            "Run parallel load testing on Azure SQL target.",
            "Implement CDC for incremental sync during cutover.",
            "Validate application compatibility with new data types.",
            "Set up monitoring and alerting post-migration.",
        ]
