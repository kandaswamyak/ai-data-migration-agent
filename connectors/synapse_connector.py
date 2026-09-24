"""Azure Synapse SQL connector."""

import os
from typing import Optional


class SynapseConnector:
    """Connect to Azure Synapse dedicated/serverless SQL endpoint via ODBC."""

    def __init__(
        self,
        server: Optional[str] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: Optional[str] = None,
    ):
        self.server = server or os.getenv("SYNAPSE_SERVER", "")
        self.database = database or os.getenv("SYNAPSE_DATABASE", "")
        self.username = username or os.getenv("SYNAPSE_USERNAME", "")
        self.password = password or os.getenv("SYNAPSE_PASSWORD", "")
        self.driver = driver or os.getenv("SYNAPSE_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
        self.connection = None

    def connect(self):
        """Open Synapse SQL connection and validate with SELECT 1."""
        if not (self.server and self.database and self.username and self.password):
            raise ValueError("Synapse connection settings are incomplete. Set server/database/username/password.")

        try:
            import pyodbc
        except Exception as ex:
            raise ImportError("pyodbc is not installed. Install with: pip install pyodbc") from ex

        conn_str = (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            "Encrypt=yes;TrustServerCertificate=no;"
        )

        self.connection = pyodbc.connect(conn_str)
        cur = self.connection.cursor()
        try:
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            cur.close()
        return self.connection

    def disconnect(self):
        """Close Synapse connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
