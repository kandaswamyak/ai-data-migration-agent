"""
AI Chat Agent for the Migration Dashboard (Powers the Agent Chat panel)

Provides intelligent answers about the current migration state.
Knows about tables, columns, mappings, risks, and validation results.
"""

import json
from agents.ai_engine import get_ai_engine


class ChatAgent:
    """AI-powered chat assistant for the migration dashboard."""

    def __init__(self):
        self.ai = get_ai_engine()
        self.conversation_history = []

    def ask(self, question: str, migration_context: dict = None) -> str:
        """
        Answer a user question about the migration.

        Args:
            question: User's question
            migration_context: Dict with current migration state from session_state
                Keys may include: source_type, schema, datatype_analysis,
                mappings, ddl_statements, migration_executed, validation_complete

        Returns:
            AI-generated answer string. Returns a helpful fallback if AI unavailable.
        """
        if not self.ai:
            return self._fallback_response(question, migration_context)

        # Build context summary for the AI
        context_summary = self._build_context_summary(migration_context or {})

        system_message = """You are an AI assistant embedded in a Data Migration Dashboard.
You help users understand their Oracle → Azure SQL migration status.

You have access to the current migration state (provided in the user message).
Answer questions concisely and helpfully. If asked about something not yet done,
explain what step needs to be completed first.

Be specific with numbers, table names, and column details when available.
Format responses with markdown for readability."""

        prompt = f"""CURRENT MIGRATION STATE:
{context_summary}

USER QUESTION:
{question}"""

        try:
            # Keep conversation context
            self.conversation_history.append({"role": "user", "content": prompt})

            response = self.ai.call(
                prompt,
                system_message=system_message,
                temperature=0.3
            )

            self.conversation_history.append({"role": "assistant", "content": response})
            return response

        except Exception as e:
            return f"⚠️ AI is temporarily unavailable. Error: {str(e)}\n\n{self._fallback_response(question, migration_context)}"

    def _build_context_summary(self, ctx: dict) -> str:
        """Build a concise summary of current migration state for the AI."""

        parts = []

        # Source info
        source_type = ctx.get("source_type", "Not connected")
        parts.append(f"Source Database: {source_type}")

        # Schema info
        schema = ctx.get("schema")
        if schema is not None:
            if hasattr(schema, "to_dict"):
                schema_data = schema.to_dict("records")
            elif isinstance(schema, list):
                schema_data = schema
            else:
                schema_data = []

            if schema_data:
                tables = set(r.get("TABLE_NAME", r.get("table_name", "")) for r in schema_data)
                parts.append(f"Tables Discovered: {len(tables)} ({', '.join(list(tables)[:10])})")
                parts.append(f"Total Columns: {len(schema_data)}")

        # Datatype analysis
        analysis = ctx.get("datatype_analysis")
        if analysis is not None:
            if hasattr(analysis, "to_dict"):
                analysis_data = analysis.to_dict("records")
            elif isinstance(analysis, list):
                analysis_data = analysis
            else:
                analysis_data = []

            if analysis_data:
                statuses = {}
                risks = {}
                for row in analysis_data:
                    s = row.get("status", "Unknown")
                    r = row.get("risk", "Unknown")
                    statuses[s] = statuses.get(s, 0) + 1
                    risks[r] = risks.get(r, 0) + 1
                parts.append(f"Datatype Analysis Complete: {len(analysis_data)} columns analyzed")
                parts.append(f"  Status breakdown: {json.dumps(statuses)}")
                parts.append(f"  Risk breakdown: {json.dumps(risks)}")

        # Mappings
        mappings = ctx.get("mappings")
        if mappings:
            total = len(mappings)
            approved = sum(1 for m in mappings if m.get("approved", False))
            high_risk = [m for m in mappings if m.get("risk") == "High"]
            parts.append(f"Mappings: {total} total, {approved} approved, {total - approved} pending")
            if high_risk:
                hr_cols = [f"{m.get('source_table')}.{m.get('source_column')}" for m in high_risk[:5]]
                parts.append(f"  High-risk columns: {', '.join(hr_cols)}")

        # DDL
        ddl = ctx.get("ddl_statements")
        if ddl:
            parts.append(f"DDL Generated: {len(ddl)} CREATE TABLE statements")

        # Migration status
        if ctx.get("migration_executed"):
            parts.append("Migration: EXECUTED ✓")

        # Validation
        if ctx.get("validation_complete"):
            parts.append("Validation: ALL PASSED ✓")

        if not parts:
            parts.append("No migration steps completed yet. Please start with Step 1 (Source Connection).")

        return "\n".join(parts)

    def _fallback_response(self, question: str, ctx: dict = None) -> str:
        """Provide basic answers without AI."""

        q = question.lower()

        if not ctx:
            return "No migration data available yet. Please start with Step 1 (Source Connection)."

        if "status" in q or "progress" in q:
            steps_done = []
            if ctx.get("source_type"):
                steps_done.append("✅ Source Connected")
            if ctx.get("schema") is not None:
                steps_done.append("✅ Schema Discovered")
            if ctx.get("datatype_analysis") is not None:
                steps_done.append("✅ Datatypes Analyzed")
            if ctx.get("mappings"):
                steps_done.append("✅ Mappings Generated")
            if ctx.get("ddl_statements"):
                steps_done.append("✅ DDL Generated")
            if ctx.get("migration_executed"):
                steps_done.append("✅ Migration Executed")
            if ctx.get("validation_complete"):
                steps_done.append("✅ Validation Complete")
            return "**Migration Progress:**\n" + "\n".join(steps_done) if steps_done else "No steps completed yet."

        if "risk" in q or "high risk" in q:
            mappings = ctx.get("mappings", [])
            high_risk = [m for m in mappings if m.get("risk") == "High"]
            if high_risk:
                lines = [f"**{len(high_risk)} High-Risk Columns:**"]
                for m in high_risk[:10]:
                    lines.append(f"- {m.get('source_table')}.{m.get('source_column')}: {m.get('source_type')} → {m.get('target_type')}")
                return "\n".join(lines)
            return "No high-risk columns identified."

        if "table" in q:
            mappings = ctx.get("mappings", [])
            tables = set(m.get("source_table", "") for m in mappings)
            return f"**Tables in migration:** {', '.join(tables)}" if tables else "No tables mapped yet."

        return "I can answer questions about your migration status, risks, tables, and mappings. Try asking about 'status', 'risks', or 'tables'."

    def reset(self):
        """Clear conversation history."""
        self.conversation_history = []
