"""
Azure SQL Database Connector

Connects to Azure SQL Database as a SOURCE for migration.
Reuses the same T-SQL discovery queries as SQL Server connector
since Azure SQL Database is T-SQL compatible.

Connection uses pyodbc with ODBC Driver 18 and SQL authentication
(username/password), which is required for Azure SQL.
"""

import pyodbc
import os


class AzureSQLConnector:
    """Connect to Azure SQL Database and retrieve metadata for migration."""

    def __init__(self, server, database, username, password):
        """
        Initialize Azure SQL connector.

        Args:
            server: Azure SQL server (e.g. myserver.database.windows.net)
            database: Database name
            username: SQL auth username
            password: SQL auth password
        """
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.connection = None

    def connect(self, attempts=3):
        """
        Establish connection to Azure SQL Database.
        Uses SQL authentication with retry for transient Azure errors.

        Returns:
            pyodbc.Connection object
        """
        server = str(self.server or "").strip()
        if not server.lower().startswith("tcp:"):
            server = f"tcp:{server}"
        if "," not in server:
            server = f"{server},1433"

        connection_string = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
            "Connection Timeout=30;"
        )

        last_err = None
        for attempt in range(1, attempts + 1):
            try:
                self.connection = pyodbc.connect(connection_string)
                return self.connection
            except pyodbc.Error as e:
                last_err = e
                if attempt < attempts:
                    import time
                    time.sleep(1)
        raise Exception(f"Azure SQL connection failed after {attempts} attempts: {last_err}")

    def disconnect(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def _get_connection(self):
        """Get existing connection or raise error."""
        if not self.connection:
            raise Exception("Not connected to Azure SQL Database")
        return self.connection

    def discover_tables(self):
        """Get list of all base tables."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
        )
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return tables

    def discover_schema(self):
        """
        Discover database schema (tables, columns, data types).

        Returns:
            List of dicts with keys matching Oracle connector format:
            table_name, column_name, data_type, data_length, data_precision,
            data_scale, nullable, ordinal_position
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                c.TABLE_NAME AS table_name,
                c.COLUMN_NAME AS column_name,
                c.DATA_TYPE AS data_type,
                c.CHARACTER_MAXIMUM_LENGTH AS data_length,
                c.NUMERIC_PRECISION AS data_precision,
                c.NUMERIC_SCALE AS data_scale,
                c.IS_NULLABLE AS nullable,
                c.ORDINAL_POSITION AS ordinal_position
            FROM INFORMATION_SCHEMA.COLUMNS c
            JOIN INFORMATION_SCHEMA.TABLES t
              ON t.TABLE_NAME = c.TABLE_NAME
             AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
            WHERE t.TABLE_TYPE = 'BASE TABLE'
            ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
        """)
        schema = []
        for row in cursor.fetchall():
            schema.append({
                "table_name": row[0].lower(),
                "column_name": row[1].lower(),
                "data_type": row[2].lower(),
                "data_length": row[3],
                "data_precision": row[4],
                "data_scale": row[5],
                "nullable": "Y" if row[6] == "YES" else "N",
                "ordinal_position": row[7],
            })
        cursor.close()
        return schema

    def discover_views(self):
        """Discover views with their definitions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.TABLE_NAME,
                   OBJECT_DEFINITION(OBJECT_ID(v.TABLE_SCHEMA + '.' + v.TABLE_NAME)) AS view_def
            FROM INFORMATION_SCHEMA.VIEWS v
            ORDER BY v.TABLE_NAME
        """)
        views = []
        for row in cursor.fetchall():
            views.append({
                "name": row[0],
                "type": "VIEW",
                "status": "VALID",
                "last_ddl_time": None,
                "source_code": row[1] or ""
            })
        cursor.close()
        return views

    def discover_procedures(self):
        """Discover stored procedures and functions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.name,
                   CASE WHEN o.type_desc = 'SQL_STORED_PROCEDURE' THEN 'PROCEDURE'
                        WHEN o.type_desc LIKE '%FUNCTION%' THEN 'FUNCTION'
                        ELSE o.type_desc END AS obj_type,
                   o.modify_date,
                   OBJECT_DEFINITION(o.object_id) AS source_code
            FROM sys.objects o
            WHERE o.type IN ('P', 'FN', 'IF', 'TF')
              AND o.is_ms_shipped = 0
            ORDER BY o.name
        """)
        procs = []
        for row in cursor.fetchall():
            procs.append({
                "name": row[0],
                "type": row[1],
                "status": "VALID",
                "last_ddl_time": row[2].isoformat() if row[2] else None,
                "source_code": row[3] or ""
            })
        cursor.close()
        return procs

    def discover_triggers(self):
        """Discover triggers with their definitions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.name AS trigger_name,
                   OBJECT_NAME(t.parent_id) AS table_name,
                   t.is_disabled,
                   t.modify_date,
                   OBJECT_DEFINITION(t.object_id) AS source_code,
                   te.type_desc AS event_type
            FROM sys.triggers t
            LEFT JOIN sys.trigger_events te ON te.object_id = t.object_id
            WHERE t.is_ms_shipped = 0
              AND t.parent_class = 1
            ORDER BY t.name
        """)
        triggers = []
        seen = set()
        for row in cursor.fetchall():
            trig_name = row[0]
            if trig_name in seen:
                for tr in triggers:
                    if tr["name"] == trig_name:
                        tr["triggering_event"] += ", " + (row[5] or "")
                continue
            seen.add(trig_name)
            triggers.append({
                "name": trig_name,
                "type": "TRIGGER",
                "trigger_type": "DML",
                "triggering_event": row[5] or "",
                "table_name": row[1],
                "status": "DISABLED" if row[2] else "ENABLED",
                "last_ddl_time": row[3].isoformat() if row[3] else None,
                "source_code": row[4] or ""
            })
        cursor.close()
        return triggers

    def discover_sequences(self):
        """Discover sequences."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT s.name, s.minimum_value, s.maximum_value,
                       s.increment, s.is_cycling, s.cache_size,
                       s.current_value
                FROM sys.sequences s
                WHERE s.is_ms_shipped = 0
                ORDER BY s.name
            """)
            sequences = []
            for row in cursor.fetchall():
                sequences.append({
                    "name": row[0],
                    "type": "SEQUENCE",
                    "min_value": row[1],
                    "max_value": row[2],
                    "increment_by": row[3],
                    "cycle_flag": "Y" if row[4] else "N",
                    "order_flag": "N",
                    "cache_size": row[5],
                    "last_number": row[6],
                })
            cursor.close()
            return sequences
        except Exception:
            cursor.close()
            return []

    def discover_all_objects(self):
        """Discover ALL schema objects for a complete inventory."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                CASE
                    WHEN type_desc = 'USER_TABLE' THEN 'TABLE'
                    WHEN type_desc = 'VIEW' THEN 'VIEW'
                    WHEN type_desc = 'SQL_STORED_PROCEDURE' THEN 'PROCEDURE'
                    WHEN type_desc LIKE '%FUNCTION%' THEN 'FUNCTION'
                    WHEN type_desc = 'SQL_TRIGGER' THEN 'TRIGGER'
                    WHEN type_desc = 'SYNONYM' THEN 'SYNONYM'
                    ELSE type_desc
                END AS obj_type,
                name,
                modify_date
            FROM sys.objects
            WHERE is_ms_shipped = 0
              AND type IN ('U', 'V', 'P', 'FN', 'IF', 'TF', 'TR', 'SN')
            ORDER BY obj_type, name
        """)
        inventory = {}
        for row in cursor.fetchall():
            obj_type = row[0]
            if obj_type not in inventory:
                inventory[obj_type] = []
            inventory[obj_type].append({
                "name": row[1],
                "type": obj_type,
                "status": "VALID",
                "last_ddl_time": row[2].isoformat() if row[2] else None,
            })
        cursor.close()

        # Also add sequences
        try:
            cursor2 = conn.cursor()
            cursor2.execute("""
                SELECT name, modify_date FROM sys.sequences
                WHERE is_ms_shipped = 0 ORDER BY name
            """)
            seq_list = []
            for row in cursor2.fetchall():
                seq_list.append({
                    "name": row[0], "type": "SEQUENCE",
                    "status": "VALID",
                    "last_ddl_time": row[1].isoformat() if row[1] else None,
                })
            if seq_list:
                inventory["SEQUENCE"] = seq_list
            cursor2.close()
        except Exception:
            pass

        summary = {
            "total_objects": sum(len(v) for v in inventory.values()),
            "object_counts": {k: len(v) for k, v in inventory.items()},
            "objects": inventory,
        }
        return summary
