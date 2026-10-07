"""
AI Risk Analyst Agent (Phase 6 - Human Approval Support)

Generates natural language risk summaries to help humans make approval decisions.
"""

import json
from agents.ai_engine import get_ai_engine


class RiskAnalyst:
    """AI-powered risk assessment for migration approval."""

    def __init__(self):
        self.ai = get_ai_engine()

    def generate_risk_summary(self, mappings: list) -> str:
        """
        Generate an AI-powered risk summary for the migration.

        Args:
            mappings: List of mapping dicts with risk, status, transformation fields

        Returns:
            Natural language risk assessment string (markdown formatted)
        """

        if not mappings:
            return "No mappings available for risk assessment."

        # Try AI
        if self.ai:
            try:
                return self._ai_risk_summary(mappings)
            except Exception as e:
                print(f"AI risk analysis failed: {e}")

        # Fallback
        return self._rule_based_summary(mappings)

    def _ai_risk_summary(self, mappings: list) -> str:
        """Use AI to generate risk summary."""

        # Prepare concise mapping data
        summary_data = []
        for m in mappings:
            summary_data.append({
                "table": m.get("source_table", ""),
                "column": m.get("source_column", ""),
                "source_type": m.get("source_type", ""),
                "target_type": m.get("target_type", ""),
                "risk": m.get("risk", "Low"),
                "transformation": m.get("transformation", "Direct"),
                "confidence": m.get("confidence", 1.0),
            })

        prompt = f"""You are a data migration risk analyst. Review the following column mappings
from Oracle to Azure SQL and provide a concise risk assessment for the approver.

MAPPINGS:
{json.dumps(summary_data, indent=2)}

Provide:
1. An overall risk rating (Low / Medium / High)
2. Count of columns by risk level
3. Specific concerns for any High or Medium risk columns (mention table.column names)
4. Key recommendations before approval
5. A clear GO / CAUTION / STOP recommendation

Format your response in markdown with headers. Keep it concise (max 200 words)."""

        return self.ai.call(
            prompt,
            system_message="You are a database migration risk analyst. Be concise and actionable.",
            temperature=0.2
        )

    def _rule_based_summary(self, mappings: list) -> str:
        """Fallback rule-based risk summary."""

        total = len(mappings)
        high = [m for m in mappings if m.get("risk") == "High"]
        medium = [m for m in mappings if m.get("risk") == "Medium"]
        low = [m for m in mappings if m.get("risk") == "Low"]

        lines = ["### Migration Risk Assessment\n"]
        lines.append(f"**Total Columns:** {total}")
        lines.append(f"- Low Risk: {len(low)}")
        lines.append(f"- Medium Risk: {len(medium)}")
        lines.append(f"- High Risk: {len(high)}")
        lines.append("")

        if high:
            lines.append("#### High-Risk Columns:")
            for m in high[:5]:
                lines.append(
                    f"- **{m.get('source_table')}.{m.get('source_column')}**: "
                    f"`{m.get('source_type')}` -> `{m.get('target_type')}` - "
                    f"{m.get('transformation', 'Unknown')}"
                )
            lines.append("")

        if medium:
            lines.append("#### Medium-Risk Columns:")
            for m in medium[:5]:
                lines.append(
                    f"- **{m.get('source_table')}.{m.get('source_column')}**: "
                    f"`{m.get('source_type')}` -> `{m.get('target_type')}`"
                )
            lines.append("")

        # Recommendation
        if high:
            lines.append("**Recommendation:** CAUTION - Review high-risk columns before approval.")
        elif medium:
            lines.append("**Recommendation:** PROCEED WITH REVIEW - Check medium-risk conversions.")
        else:
            lines.append("**Recommendation:** GO - All mappings are low-risk.")

        return "\n".join(lines)
