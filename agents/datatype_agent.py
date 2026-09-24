import json
import os

from openai import AzureOpenAI
from dotenv import load_dotenv


load_dotenv("config/.env")


class DatatypeAnalysisAgent:

    def __init__(self):

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv(
            "AZURE_OPENAI_API_VERSION",
            "2024-10-21"
        )

        self.deployment = os.getenv(
            "AZURE_OPENAI_DEPLOYMENT"
        )

        if not endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT is not configured."
            )

        if not api_key:
            raise ValueError(
                "AZURE_OPENAI_API_KEY is not configured."
            )

        if not self.deployment:
            raise ValueError(
                "AZURE_OPENAI_DEPLOYMENT is not configured."
            )

        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version
        )

    def analyze(self, source_column):

        prompt = f"""
You are an expert database migration architect.

Analyze the following source database column.

SOURCE DATABASE:
{source_column.get("source_database")}

TABLE:
{source_column.get("table_name")}

COLUMN:
{source_column.get("column_name")}

SOURCE DATA TYPE:
{source_column.get("data_type")}

SOURCE LENGTH:
{source_column.get("length")}

SOURCE PRECISION:
{source_column.get("precision")}

SOURCE SCALE:
{source_column.get("scale")}

NULLABLE:
{source_column.get("nullable")}

TARGET DATABASE:
Azure SQL Database

Your task:

1. Recommend the safest Azure SQL datatype.
2. Preserve source character length wherever possible.
3. Preserve numeric precision and scale wherever possible.
4. Never reduce length, precision or scale without identifying the risk.
5. Identify possible data loss.
6. Explain the datatype difference.
7. Provide a confidence score.
8. Return ONLY valid JSON.

Return exactly this structure:

{{
    "source_type": "",
    "source_length": null,
    "source_precision": null,
    "source_scale": null,

    "target_type": "",
    "target_length": null,
    "target_precision": null,
    "target_scale": null,

    "status": "",
    "risk": "",
    "confidence": 0,

    "datatype_difference": "",
    "reason": "",
    "recommendation": ""
}}

Allowed status values:

Compatible
Review
Warning
High Risk

Allowed risk values:

Low
Medium
High
"""

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a database migration "
                        "and datatype compatibility expert."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0
        )

        content = response.choices[0].message.content

        # Remove markdown code fences if the model adds them
        content = content.replace("```json", "")
        content = content.replace("```", "")
        content = content.strip()

        return json.loads(content)
