import pyodbc


class SQLServerConnector:

    def __init__(self, server, database):
        self.server = server
        self.database = database
        self.connection = None

    def connect(self):
        connection_string = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            "Trusted_Connection=yes;"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
        )
        self.connection = pyodbc.connect(connection_string)
        return self.connection

    def disconnect(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def _get_connection(self):
        """Get existing connection or raise error."""
        if not self.connection:
            raise Exception("Not connected to SQL Server database")
        return self.connection

    def discover_tables(self):
        """
        Get list of all base tables.

        Returns:
            List of table names
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
        )
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return tables

    def discover_views(self):
        """
        Discover views with their definitions.

        Returns:
            List of dicts with keys: name, type, status, source_code
        """
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
        """
        Discover stored procedures and functions.

        Returns:
            List of dicts with keys: name, type, status, last_ddl_time, source_code
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.name,
                   o.type_desc,
                   CASE WHEN o.type_desc = 'SQL_STORED_PROCEDURE' THEN 'PROCEDURE'
                        WHEN o.type_desc = 'SQL_SCALAR_FUNCTION' THEN 'FUNCTION'
                        WHEN o.type_desc = 'SQL_TABLE_VALUED_FUNCTION' THEN 'FUNCTION'
                        WHEN o.type_desc = 'SQL_INLINE_TABLE_VALUED_FUNCTION' THEN 'FUNCTION'
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
                "type": row[2],
                "status": "VALID",
                "last_ddl_time": row[3].isoformat() if row[3] else None,
                "source_code": row[4] or ""
            })
        cursor.close()
        return procs

    def discover_triggers(self):
        """
        Discover triggers with their definitions.

        Returns:
            List of dicts with keys: name, type, table_name, triggering_event,
            trigger_type, status, last_ddl_time, source_code
        """
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
                # Merge multiple events for same trigger
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
        """
        Discover sequences (SQL Server 2012+).

        Returns:
            List of dicts with keys: name, type, min_value, max_value,
            increment_by, cycle_flag, cache_size, last_number
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT s.name, s.minimum_value, s.maximum_value,
                       s.increment, s.is_cycling, s.cache_size,
                       s.current_value, s.start_value
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
        """
        Discover ALL schema objects at once for a complete inventory.

        Returns:
            Dict with total_objects, object_counts, and objects by type.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                CASE
                    WHEN type_desc = 'USER_TABLE' THEN 'TABLE'
                    WHEN type_desc = 'VIEW' THEN 'VIEW'
                    WHEN type_desc = 'SQL_STORED_PROCEDURE' THEN 'PROCEDURE'
                    WHEN type_desc IN ('SQL_SCALAR_FUNCTION', 'SQL_TABLE_VALUED_FUNCTION',
                                       'SQL_INLINE_TABLE_VALUED_FUNCTION') THEN 'FUNCTION'
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

        # Also add sequences (separate catalog view)
        try:
            cursor2 = conn.cursor()
            cursor2.execute("""
                SELECT name, modify_date
                FROM sys.sequences
                WHERE is_ms_shipped = 0
                ORDER BY name
            """)
            seq_list = []
            for row in cursor2.fetchall():
                seq_list.append({
                    "name": row[0],
                    "type": "SEQUENCE",
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
