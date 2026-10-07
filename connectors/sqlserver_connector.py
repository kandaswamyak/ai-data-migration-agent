import pyodbc


class SQLServerConnector:
    """Connect to a source SQL Server database and retrieve data/metadata.

    Mirrors the shape the migration engine expects from OracleConnector:
    a `connection` attribute set after connect(), plus connect()/disconnect().
    """

    def __init__(self, server, database, username=None, password=None):
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.connection = None

    def _connection_string(self):
        base = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
        )
        if self.username:
            # SQL authentication
            base += f"UID={self.username};PWD={self.password or ''};"
        else:
            # Windows / integrated authentication
            base += "Trusted_Connection=yes;"
        return base

    def connect(self):
        """Open a connection, store it on self.connection, and return it."""
        conn = pyodbc.connect(self._connection_string())
        self.connection = conn
        return conn

    def disconnect(self):
        """Close the connection if open (safe to call multiple times)."""
        try:
            if self.connection is not None:
                self.connection.close()
        except Exception:
            pass
        finally:
            self.connection = None

    def get_row_count(self, table_name, schema="dbo"):
        """Return the row count for a table (bracket-quoted, case preserved)."""
        if not self.connection:
            raise Exception("Not connected to SQL Server database")

        def _q(name):
            return "[" + str(name).replace("]", "]]") + "]"

        cur = self.connection.cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM {_q(schema)}.{_q(table_name)}")
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        finally:
            cur.close()
