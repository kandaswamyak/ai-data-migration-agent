"""
Shared AI Engine for all Migration Agents.

Provides a unified interface to Azure OpenAI. All agents use this
instead of creating their own AzureOpenAI clients.
"""

import json
import os

from openai import AzureOpenAI
from dotenv import load_dotenv

# Load .env from both possible locations (project root and config/)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(_project_root, "config", ".env"))

# Also try project root .env (overrides if vars exist in both)
load_dotenv(os.path.join(_project_root, ".env"))


class AIEngine:
    """Shared Azure OpenAI client for all migration agents."""

    _instance = None  # Singleton

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is not configured.")
        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY is not configured.")

        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        self._initialized = True

    def call(self, prompt: str, system_message: str = "", temperature: float = 0) -> str:
        """
        Call Azure OpenAI and return the raw text response.

        Args:
            prompt: User message
            system_message: System instruction (optional)
            temperature: 0 = deterministic, 1 = creative

        Returns:
            The assistant's text response (stripped of markdown fences).
        """
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=temperature,
        )

        content = response.choices[0].message.content

        # Strip markdown code fences if present
        content = content.replace("```json", "").replace("```sql", "").replace("```", "")
        return content.strip()

    def call_json(self, prompt: str, system_message: str = "", temperature: float = 0) -> dict:
        """
        Call Azure OpenAI and parse the response as JSON.

        Returns:
            Parsed dict/list. Returns {"error": "..."} on parse failure.
        """
        text = self.call(prompt, system_message, temperature)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            # Try array
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {"error": "Failed to parse AI response", "raw": text[:500]}

    def is_available(self) -> bool:
        """Check if the AI engine is properly configured."""
        try:
            return bool(self.client and self.deployment)
        except Exception:
            return False


def get_ai_engine() -> AIEngine:
    """Get or create the shared AI engine instance. Returns None if not configured."""
    try:
        return AIEngine()
    except (ValueError, Exception):
        return None
