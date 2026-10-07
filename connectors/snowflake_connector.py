"""Snowflake database connector."""

import os
from typing import Optional, Dict, Any


class SnowflakeConnector:
    """Connect to Snowflake and validate connectivity."""

    def __init__(
        self,
        account: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        warehouse: Optional[str] = None,
        database: Optional[str] = None,
        schema: Optional[str] = None,
        role: Optional[str] = None,
    ):
        self.account = account or os.getenv("SNOWFLAKE_ACCOUNT", "")
        self.user = user or os.getenv("SNOWFLAKE_USER", "")
        self.password = password or os.getenv("SNOWFLAKE_PASSWORD", "")
        self.warehouse = warehouse or os.getenv("SNOWFLAKE_WAREHOUSE", "")
        self.database = database or os.getenv("SNOWFLAKE_DATABASE", "")
        self.schema = schema or os.getenv("SNOWFLAKE_SCHEMA", "")
        self.role = role or os.getenv("SNOWFLAKE_ROLE", "")
        self.connection = None

    def _build_connect_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "account": self.account,
            "user": self.user,
            "password": self.password,
        }
        if self.warehouse:
            kwargs["warehouse"] = self.warehouse
        if self.database:
            kwargs["database"] = self.database
        if self.schema:
            kwargs["schema"] = self.schema
        if self.role:
            kwargs["role"] = self.role
        return kwargs

    def connect(self):
        """Open a Snowflake connection and validate with SELECT 1."""
        if not (self.account and self.user and self.password):
            raise ValueError("Snowflake credentials are incomplete. Set account/user/password.")

        try:
            import snowflake.connector  # type: ignore
        except Exception as ex:
            raise ImportError(
                "snowflake-connector-python is not installed. "
                "Install with: pip install snowflake-connector-python"
            ) from ex

        self.connection = snowflake.connector.connect(**self._build_connect_kwargs())
        cur = self.connection.cursor()
        try:
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            cur.close()
        return self.connection

    def disconnect(self):
        """Close Snowflake connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
