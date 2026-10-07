"""
AI Source-to-Target Mapping Agent (Phase 4)

Maps source columns to target columns with AI-powered recommendations.
Uses datatype analysis results as foundation.
AI provides intelligent naming, transformation suggestions, and reasoning.
"""

import json
import os
from agents.ai_engine import get_ai_engine


class MappingAgent:

    def __init__(self, source_db="Oracle", target_db="Azure SQL"):
        self.source_db = source_db
        self.target_db = target_db
        self.ai = get_ai_engine()

    def generate_mapping(self, analysis_results):
        """
        Generate source-to-target mapping from datatype analysis results.
        Uses AI for intelligent mapping when available, falls back to rules.
        """

        # Try AI-powered batch mapping first
        if self.ai:
            try:
                return self._ai_generate_mapping(analysis_results)
            except Exception as e:
                print(f"AI mapping failed, falling back to rules: {e}")

        # Fallback: rule-based mapping
        return self._rule_based_mapping(analysis_results)

    def _ai_generate_mapping(self, analysis_results):
        """Use AI to generate intelligent column mappings."""

        # Build a concise representation for the AI
        columns_info = []
        for row in analysis_results:
            columns_info.append({
                "table": row.get("table", ""),
                "column": row.get("column", ""),
                "source_type": row.get("source_type", ""),
                "target_type": row.get("target_type", ""),
                "status": row.get("status", ""),
                "risk": row.get("risk", ""),
                "confidence": row.get("confidence", 1.0),
            })

        prompt = f"""You are an expert database migration architect mapping {self.source_db} to {self.target_db}.

Given the following source columns and their AI-analyzed target types, generate the complete mapping.

SOURCE COLUMNS:
{json.dumps(columns_info, indent=2)}

For each column, provide:
1. target_table: Same as source (for POC)
2. target_column: Suggested Azure SQL column name (use original name but you may suggest improvements)
3. target_type: Use the pre-analyzed target_type
4. transformation: One of "Direct", "Type Conversion", "Review Required", "Manual Override Required"
5. reasoning: Brief explanation of the mapping decision
6. nullable: "Y" or "N" based on best practice

Return a JSON array of objects with these fields:
[
  {{
    "source_table": "",
    "source_column": "",
    "source_type": "",
    "target_schema": "dbo",
    "target_table": "",
    "target_column": "",
    "target_type": "",
    "nullable": "Y",
    "status": "",
    "risk": "",
    "confidence": 0.0,
    "transformation": "",
    "reasoning": "",
    "approved": false
  }}
]

Return ONLY valid JSON array. No markdown, no explanation outside the JSON."""

        result = self.ai.call_json(
            prompt,
            system_message="You are a database migration mapping expert. Return only valid JSON."
        )

        # Validate we got a list
        if isinstance(result, list) and len(result) > 0:
            return result
        elif isinstance(result, dict) and "error" not in result:
            return [result]
        else:
            # AI failed, fall back
            raise ValueError(f"AI returned unexpected format: {type(result)}")

    def _rule_based_mapping(self, analysis_results):
        """Fallback: Generate mappings using rules (no AI)."""

        mappings = []

        for row in analysis_results:
            mapping = {
                "source_table": row.get("table", ""),
                "source_column": row.get("column", ""),
                "source_type": row.get("source_type", ""),
                "target_schema": "dbo",
                "target_table": row.get("table", ""),
                "target_column": row.get("column", ""),
                "target_type": row.get("target_type", ""),
                "nullable": row.get("nullable", "Y"),
                "status": row.get("status", ""),
                "risk": row.get("risk", ""),
                "confidence": row.get("confidence", 1.0),
                "transformation": self._get_transformation(row),
                "reasoning": self._get_reasoning(row),
                "approved": False
            }
            mappings.append(mapping)

        return mappings

    def _get_transformation(self, row):
        """Determine what type of transformation is needed."""

        status = row.get("status", "")
        risk = row.get("risk", "")

        if status == "Compatible" and risk == "Low":
            return "Direct"
        if status == "Warning" and risk == "Low":
            return "Type Conversion"
        if risk == "Medium":
            return "Review Required"
        if risk == "High":
            return "Manual Override Required"
        return "Direct"

    def _get_reasoning(self, row):
        """Generate reasoning for the mapping."""

        source = row.get("source_type", "")
        target = row.get("target_type", "")
        risk = row.get("risk", "")

        if risk == "Low":
            return f"{source} maps directly to {target} with no data loss."
        elif risk == "Medium":
            return f"{source} → {target}: Review precision/length preservation."
        elif risk == "High":
            return f"{source} has no direct equivalent. {target} is closest match but may lose data."
        return f"Standard mapping: {source} → {target}"

    def save_mappings(self, mappings, file_path="data/mappings.json"):
        """Save mappings to JSON file."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(mappings, f, indent=4)
        return file_path

    def load_mappings(self, file_path="data/mappings.json"):
        """Load mappings from JSON file."""
        with open(file_path, "r") as f:
            return json.load(f)

    def approve_mapping(self, mappings, index):
        """Mark a specific mapping as approved."""
        if 0 <= index < len(mappings):
            mappings[index]["approved"] = True
        return mappings

    def approve_all(self, mappings):
        """Mark all mappings as approved."""
        for mapping in mappings:
            mapping["approved"] = True
        return mappings

    def get_approval_summary(self, mappings):
        """Get summary of approval status."""
        total = len(mappings)
        approved = sum(1 for m in mappings if m.get("approved", False))
        pending = total - approved
        return {
            "total": total,
            "approved": approved,
            "pending": pending,
            "ready_for_migration": approved == total
        }
