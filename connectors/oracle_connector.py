"""
Oracle Database Connector

Supports both thin and thick client modes for Oracle database connectivity.
Uses python-oracledb (recommended) for modern connections.
"""

import oracledb
import json
import os
from typing import Optional, Dict, List
import pandas as pd


class OracleConnector:
    """Connect to Oracle database and retrieve metadata."""

    def __init__(
        self,
        host: str,
        port: int = 1521,
        service_name: Optional[str] = None,
        sid: Optional[str] = None,
        username: str = "sys",
        password: str = "",
        mode: str = "AUTO",
        thick_mode: bool = False,
        lib_dir: Optional[str] = None
    ):
        """
        Initialize Oracle Connector.

        Args:
            host: Oracle server hostname/IP
            port: Oracle listener port (default 1521)
            service_name: Oracle service name (preferred over SID)
            sid: Oracle SID (fallback if service_name not provided)
            username: Database username
            password: Database password
            mode: Connection mode - "NORMAL", "SYSDBA", or "SYSOPER"
            thick_mode: Use thick client (requires Oracle client libraries)
            lib_dir: Path to Oracle client libraries (for thick mode)

        Raises:
            ValueError: If neither service_name nor sid provided
        """
        # Clean up empty strings to None
        service_name = service_name if service_name and service_name.strip() else None
        sid = sid if sid and sid.strip() else None
        
        # Clean up empty strings to None
        service_name = service_name if service_name and service_name.strip() else None
        sid = sid if sid and sid.strip() else None
        
        if not service_name and not sid:
            raise ValueError("Either 'service_name' or 'sid' must be provided")

        self.host = host
        self.port = port
        self.service_name = service_name
        self.sid = sid
        self.username = username
        self.password = password
        self.mode = self._resolve_mode(mode, username)
        self.thick_mode = thick_mode
        self.lib_dir = lib_dir
        self.connection = None

    @staticmethod
    def _resolve_mode(mode: Optional[str], username: str) -> str:
        """Resolve Oracle auth mode with sensible defaults.

        AUTO/empty mode picks SYSDBA only for SYS user, else NORMAL.
        """
        requested = (mode or "").strip().upper()
        if requested in ("", "AUTO"):
            return "SYSDBA" if (username or "").strip().lower() == "sys" else "NORMAL"
        return requested

    def connect(self) -> oracledb.Connection:
        """
        Establish connection to Oracle database.

        Returns:
            oracledb.Connection object

        Raises:
            oracledb.DatabaseError: Connection failed
        """
        try:
            # Initialize thick mode if requested
            if self.thick_mode and self.lib_dir:
                oracledb.init_oracle_client(lib_dir=self.lib_dir)

            # Ensure host is set (avoid bequeath protocol in thin mode)
            host = self.host if self.host and self.host.strip() else "localhost"
            port = self.port if self.port else 1521

            # Build connection string using explicit TCP format
            if self.service_name:
                dsn = oracledb.makedsn(
                    host=host,
                    port=port,
                    service_name=self.service_name
                )
            else:
                dsn = oracledb.makedsn(
                    host=host,
                    port=port,
                    sid=self.sid
                )

            # Map connection mode
            mode_map = {
                "NORMAL": oracledb.AUTH_MODE_DEFAULT,
                "SYSDBA": oracledb.AUTH_MODE_SYSDBA,
                "SYSOPER": oracledb.AUTH_MODE_SYSOPER
            }
            auth_mode = mode_map.get(self.mode.upper(), oracledb.AUTH_MODE_DEFAULT)

            # Create connection
            self.connection = oracledb.connect(
                user=self.username,
                password=self.password,
                dsn=dsn,
                mode=auth_mode
            )

            return self.connection

        except oracledb.DatabaseError as e:
            raise Exception(f"Oracle connection failed: {str(e)}")

    def disconnect(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def discover_schema(self, schema: Optional[str] = None) -> pd.DataFrame:
        """
        Discover database schema (tables, columns, data types).

        Args:
            schema: Schema/owner name (default: current user)

        Returns:
            DataFrame with columns: table_name, column_name, data_type, etc.
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        query = """
        SELECT
            LOWER(t.table_name) as table_name,
            LOWER(c.column_name) as column_name,
            LOWER(c.data_type) as data_type,
            c.data_length,
            c.data_precision,
            c.data_scale,
            c.nullable,
            c.column_id as ordinal_position
        FROM
            user_tables t
            JOIN user_tab_columns c ON t.table_name = c.table_name
        """

        if schema:
            query = query.replace("user_tables", "all_tables")
            query = query.replace("user_tab_columns", "all_tab_columns")
            query += f" WHERE t.owner = '{schema.upper()}'"
        else:
            query += " ORDER BY table_name, column_id"

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            
            # Get all rows
            rows = cursor.fetchall()
            cursor.close()
            
            # Create DataFrame with proper column names
            df = pd.DataFrame(
                rows,
                columns=[
                    "table_name", "column_name", "data_type",
                    "data_length", "data_precision", "data_scale",
                    "nullable", "ordinal_position"
                ]
            )
            
            return df
        except Exception as e:
            raise Exception(f"Schema discovery failed: {str(e)}")

    def discover_relational_metadata(self, schema: Optional[str] = None) -> Dict:
        """Discover primary keys, foreign keys, and indexes for compatibility analysis."""
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        if schema:
            owner_filter = " WHERE c.owner = :owner"
            constraint_query = """
                SELECT c.constraint_name, c.constraint_type, c.table_name,
                       cc.column_name, cc.position, r.table_name,
                       rcc.column_name
                FROM all_constraints c
                JOIN all_cons_columns cc
                  ON cc.owner = c.owner AND cc.constraint_name = c.constraint_name
                LEFT JOIN all_constraints r
                  ON r.owner = c.r_owner AND r.constraint_name = c.r_constraint_name
                LEFT JOIN all_cons_columns rcc
                  ON rcc.owner = r.owner AND rcc.constraint_name = r.constraint_name
                 AND rcc.position = cc.position
            """ + owner_filter + " AND c.constraint_type IN ('P', 'R') ORDER BY c.table_name, c.constraint_name, cc.position"
            index_query = """
                SELECT i.index_name, i.table_name, i.uniqueness,
                       ic.column_name, ic.column_position
                FROM all_indexes i
                JOIN all_ind_columns ic
                  ON ic.index_owner = i.owner AND ic.index_name = i.index_name
                 AND ic.table_name = i.table_name
                WHERE i.owner = :owner
                ORDER BY i.table_name, i.index_name, ic.column_position
            """
            params = {"owner": schema.upper()}
        else:
            constraint_query = """
                SELECT c.constraint_name, c.constraint_type, c.table_name,
                       cc.column_name, cc.position, r.table_name,
                       rcc.column_name
                FROM user_constraints c
                JOIN user_cons_columns cc ON cc.constraint_name = c.constraint_name
                LEFT JOIN user_constraints r ON r.constraint_name = c.r_constraint_name
                LEFT JOIN user_cons_columns rcc
                  ON rcc.constraint_name = r.constraint_name AND rcc.position = cc.position
                WHERE c.constraint_type IN ('P', 'R')
                ORDER BY c.table_name, c.constraint_name, cc.position
            """
            index_query = """
                SELECT i.index_name, i.table_name, i.uniqueness,
                       ic.column_name, ic.column_position
                FROM user_indexes i
                JOIN user_ind_columns ic
                  ON ic.index_name = i.index_name AND ic.table_name = i.table_name
                ORDER BY i.table_name, i.index_name, ic.column_position
            """
            params = {}

        cursor = self.connection.cursor()
        try:
            cursor.execute(constraint_query, params)
            constraints = [
                {
                    "constraint_name": row[0],
                    "constraint_type": row[1],
                    "table_name": row[2],
                    "column_name": row[3],
                    "position": row[4],
                    "referenced_table": row[5],
                    "referenced_column": row[6],
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(index_query, params)
            indexes = [
                {
                    "index_name": row[0],
                    "table_name": row[1],
                    "uniqueness": row[2],
                    "column_name": row[3],
                    "position": row[4],
                }
                for row in cursor.fetchall()
            ]
            return {"constraints": constraints, "indexes": indexes}
        except Exception as e:
            raise Exception(f"Relational metadata discovery failed: {str(e)}")
        finally:
            cursor.close()

    def discover_tables(self, schema: Optional[str] = None) -> List[str]:
        """
        Get list of all tables in the database.

        Args:
            schema: Schema/owner name (default: current user)

        Returns:
            List of table names
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        if schema:
            query = f"SELECT table_name FROM all_tables WHERE owner = '{schema.upper()}' ORDER BY table_name"
        else:
            query = "SELECT table_name FROM user_tables ORDER BY table_name"

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return tables
        except Exception as e:
            raise Exception(f"Table discovery failed: {str(e)}")

    def get_table_structure(self, table_name: str) -> Dict:
        """
        Get detailed structure of a specific table.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary with table structure metadata
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        query = f"""
        SELECT
            LOWER(column_name) as column_name,
            LOWER(data_type) as data_type,
            data_length,
            data_precision,
            data_scale,
            nullable,
            column_id
        FROM
            user_tab_columns
        WHERE
            table_name = '{table_name.upper()}'
        ORDER BY
            column_id
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            
            # Create DataFrame with explicit column names
            df = pd.DataFrame(
                rows,
                columns=[
                    "column_name", "data_type", "data_length",
                    "data_precision", "data_scale", "nullable", "column_id"
                ]
            )
            
            structure = {
                "table_name": table_name.upper(),
                "columns": df.to_dict("records")
            }
            return structure
        except Exception as e:
            raise Exception(f"Failed to get table structure: {str(e)}")

    def get_row_count(self, table_name: str) -> int:
        """Get row count for a table."""
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        # Escape table names with special characters using double quotes
        safe_table_name = f'"{table_name.upper()}"' if any(c in table_name for c in ['$', '_', '-']) else table_name.upper()
        query = f"SELECT COUNT(*) FROM {safe_table_name}"

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            count = cursor.fetchone()[0]
            cursor.close()
            return count
        except Exception as e:
            raise Exception(f"Failed to get row count: {str(e)}")

    def export_metadata_to_json(
        self,
        output_path: str,
        schema: Optional[str] = None
    ):
        """
        Export schema metadata to JSON file.

        Args:
            output_path: Path where to save JSON file
            schema: Schema to export (default: current user)
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        try:
            tables = self.discover_tables(schema)
            metadata = {}

            for table in tables:
                metadata[table] = self.get_table_structure(table)["columns"]

            with open(output_path, "w") as f:
                json.dump(metadata, f, indent=2)

            print(f"✅ Metadata exported to {output_path}")

        except Exception as e:
            raise Exception(f"Metadata export failed: {str(e)}")

    def discover_procedures(self, schema: Optional[str] = None) -> List[Dict]:
        """
        Discover stored procedures and functions from Oracle source.
        Returns procedure name, type, last DDL time, and source code.

        Args:
            schema: Schema/owner name (default: current user)

        Returns:
            List of dicts with keys: name, type, status, last_ddl_time, source_code
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        cursor = self.connection.cursor()

        # Get procedure/function metadata
        if schema:
            obj_query = """
                SELECT object_name, object_type, status, last_ddl_time
                FROM all_objects
                WHERE owner = :owner
                  AND object_type IN ('PROCEDURE', 'FUNCTION')
                ORDER BY object_name
            """
            src_query = """
                SELECT name, type, line, text
                FROM all_source
                WHERE owner = :owner
                  AND type IN ('PROCEDURE', 'FUNCTION')
                ORDER BY name, type, line
            """
            params = {"owner": schema.upper()}
        else:
            obj_query = """
                SELECT object_name, object_type, status, last_ddl_time
                FROM user_objects
                WHERE object_type IN ('PROCEDURE', 'FUNCTION')
                ORDER BY object_name
            """
            src_query = """
                SELECT name, type, line, text
                FROM user_source
                WHERE type IN ('PROCEDURE', 'FUNCTION')
                ORDER BY name, type, line
            """
            params = {}

        try:
            # Get object list with metadata
            cursor.execute(obj_query, params)
            objects = {}
            for row in cursor.fetchall():
                objects[row[0]] = {
                    "name": row[0],
                    "type": row[1],
                    "status": row[2],
                    "last_ddl_time": row[3].isoformat() if row[3] else None,
                    "source_code": ""
                }

            # Get source code
            cursor.execute(src_query, params)
            source_lines = {}
            for row in cursor.fetchall():
                key = row[0]  # name
                if key not in source_lines:
                    source_lines[key] = []
                source_lines[key].append(row[3])  # text

            # Combine source lines into full source code
            for name, lines in source_lines.items():
                if name in objects:
                    objects[name]["source_code"] = "".join(lines)

            cursor.close()
            return list(objects.values())

        except Exception as e:
            cursor.close()
            raise Exception(f"Procedure discovery failed: {str(e)}")

    def get_procedure_source(self, procedure_name: str, schema: Optional[str] = None) -> str:
        """Get the full source code of a specific procedure."""
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        cursor = self.connection.cursor()
        if schema:
            query = """
                SELECT text FROM all_source
                WHERE owner = :owner AND name = :name
                ORDER BY line
            """
            params = {"owner": schema.upper(), "name": procedure_name.upper()}
        else:
            query = """
                SELECT text FROM user_source
                WHERE name = :name
                ORDER BY line
            """
            params = {"name": procedure_name.upper()}

        cursor.execute(query, params)
        lines = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return "".join(lines)

    def discover_views(self, schema: Optional[str] = None) -> List[Dict]:
        """
        Discover views from Oracle source.
        Returns view name, status, and view definition (SQL text).

        Args:
            schema: Schema/owner name (default: current user)

        Returns:
            List of dicts with keys: name, type, status, last_ddl_time, source_code
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        cursor = self.connection.cursor()

        if schema:
            obj_query = """
                SELECT object_name, object_type, status, last_ddl_time
                FROM all_objects
                WHERE owner = :owner
                  AND object_type = 'VIEW'
                ORDER BY object_name
            """
            view_query = """
                SELECT view_name, text
                FROM all_views
                WHERE owner = :owner
                ORDER BY view_name
            """
            params = {"owner": schema.upper()}
        else:
            obj_query = """
                SELECT object_name, object_type, status, last_ddl_time
                FROM user_objects
                WHERE object_type = 'VIEW'
                ORDER BY object_name
            """
            view_query = """
                SELECT view_name, text
                FROM user_views
                ORDER BY view_name
            """
            params = {}

        try:
            # Get object metadata (status, last_ddl_time)
            cursor.execute(obj_query, params)
            objects = {}
            for row in cursor.fetchall():
                objects[row[0]] = {
                    "name": row[0],
                    "type": "VIEW",
                    "status": row[2],
                    "last_ddl_time": row[3].isoformat() if row[3] else None,
                    "source_code": ""
                }

            # Get view definitions
            cursor.execute(view_query, params)
            for row in cursor.fetchall():
                view_name = row[0]
                view_text = row[1]
                # Handle CLOB - read if necessary
                if hasattr(view_text, 'read'):
                    view_text = view_text.read()
                if view_name in objects:
                    objects[view_name]["source_code"] = view_text or ""
                else:
                    objects[view_name] = {
                        "name": view_name,
                        "type": "VIEW",
                        "status": "VALID",
                        "last_ddl_time": None,
                        "source_code": view_text or ""
                    }

            cursor.close()
            return list(objects.values())

        except Exception as e:
            cursor.close()
            raise Exception(f"View discovery failed: {str(e)}")

    def discover_triggers(self, schema: Optional[str] = None) -> List[Dict]:
        """
        Discover triggers from Oracle source.
        Returns trigger name, type, table, event, timing, status, and source body.

        Args:
            schema: Schema/owner name (default: current user)

        Returns:
            List of dicts with keys: name, type, table_name, triggering_event,
            trigger_type, status, last_ddl_time, source_code
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        cursor = self.connection.cursor()

        if schema:
            trigger_query = """
                SELECT t.trigger_name, t.trigger_type, t.triggering_event,
                       t.table_name, t.status, t.trigger_body,
                       o.last_ddl_time
                FROM all_triggers t
                LEFT JOIN all_objects o
                  ON o.owner = t.owner AND o.object_name = t.trigger_name
                  AND o.object_type = 'TRIGGER'
                WHERE t.owner = :owner
                ORDER BY t.trigger_name
            """
            params = {"owner": schema.upper()}
        else:
            trigger_query = """
                SELECT t.trigger_name, t.trigger_type, t.triggering_event,
                       t.table_name, t.status, t.trigger_body,
                       o.last_ddl_time
                FROM user_triggers t
                LEFT JOIN user_objects o
                  ON o.object_name = t.trigger_name
                  AND o.object_type = 'TRIGGER'
                ORDER BY t.trigger_name
            """
            params = {}

        try:
            cursor.execute(trigger_query, params)
            triggers = []
            for row in cursor.fetchall():
                trigger_body = row[5]
                if hasattr(trigger_body, 'read'):
                    trigger_body = trigger_body.read()
                triggers.append({
                    "name": row[0],
                    "type": "TRIGGER",
                    "trigger_type": row[1],       # BEFORE EACH ROW, AFTER STATEMENT, etc.
                    "triggering_event": row[2],    # INSERT, UPDATE, DELETE
                    "table_name": row[3],
                    "status": row[4],              # ENABLED / DISABLED
                    "last_ddl_time": row[6].isoformat() if row[6] else None,
                    "source_code": trigger_body or ""
                })

            cursor.close()
            return triggers

        except Exception as e:
            cursor.close()
            raise Exception(f"Trigger discovery failed: {str(e)}")

    def discover_sequences(self, schema: Optional[str] = None) -> List[Dict]:
        """
        Discover sequences from Oracle source.
        Returns sequence name and all properties needed to recreate in Azure SQL.

        Args:
            schema: Schema/owner name (default: current user)

        Returns:
            List of dicts with keys: name, type, min_value, max_value,
            increment_by, cycle_flag, order_flag, cache_size, last_number
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        cursor = self.connection.cursor()

        if schema:
            seq_query = """
                SELECT sequence_name, min_value, max_value, increment_by,
                       cycle_flag, order_flag, cache_size, last_number
                FROM all_sequences
                WHERE sequence_owner = :owner
                ORDER BY sequence_name
            """
            params = {"owner": schema.upper()}
        else:
            seq_query = """
                SELECT sequence_name, min_value, max_value, increment_by,
                       cycle_flag, order_flag, cache_size, last_number
                FROM user_sequences
                ORDER BY sequence_name
            """
            params = {}

        try:
            cursor.execute(seq_query, params)
            sequences = []
            for row in cursor.fetchall():
                sequences.append({
                    "name": row[0],
                    "type": "SEQUENCE",
                    "min_value": row[1],
                    "max_value": row[2],
                    "increment_by": row[3],
                    "cycle_flag": row[4],    # Y or N
                    "order_flag": row[5],    # Y or N
                    "cache_size": row[6],
                    "last_number": row[7],
                })

            cursor.close()
            return sequences

        except Exception as e:
            cursor.close()
            raise Exception(f"Sequence discovery failed: {str(e)}")

    def discover_all_objects(self, schema: Optional[str] = None) -> Dict:
        """
        Discover ALL schema objects at once for a complete inventory.
        Returns a summary dict with counts and lists for each object type.

        Args:
            schema: Schema/owner name (default: current user)

        Returns:
            Dict with keys: tables, views, procedures, functions, triggers,
            sequences, packages, synonyms, materialized_views, and their counts.
        """
        if not self.connection:
            raise Exception("Not connected to Oracle database")

        cursor = self.connection.cursor()

        if schema:
            query = """
                SELECT object_type, object_name, status, last_ddl_time
                FROM all_objects
                WHERE owner = :owner
                  AND object_type IN (
                    'TABLE', 'VIEW', 'PROCEDURE', 'FUNCTION',
                    'TRIGGER', 'SEQUENCE', 'PACKAGE', 'PACKAGE BODY',
                    'SYNONYM', 'MATERIALIZED VIEW', 'TYPE', 'INDEX'
                  )
                ORDER BY object_type, object_name
            """
            params = {"owner": schema.upper()}
        else:
            query = """
                SELECT object_type, object_name, status, last_ddl_time
                FROM user_objects
                WHERE object_type IN (
                    'TABLE', 'VIEW', 'PROCEDURE', 'FUNCTION',
                    'TRIGGER', 'SEQUENCE', 'PACKAGE', 'PACKAGE BODY',
                    'SYNONYM', 'MATERIALIZED VIEW', 'TYPE', 'INDEX'
                )
                ORDER BY object_type, object_name
            """
            params = {}

        try:
            cursor.execute(query, params)
            inventory = {}
            for row in cursor.fetchall():
                obj_type = row[0]
                if obj_type not in inventory:
                    inventory[obj_type] = []
                inventory[obj_type].append({
                    "name": row[1],
                    "type": obj_type,
                    "status": row[2],
                    "last_ddl_time": row[3].isoformat() if row[3] else None,
                })

            cursor.close()

            # Build summary
            summary = {
                "total_objects": sum(len(v) for v in inventory.values()),
                "object_counts": {k: len(v) for k, v in inventory.items()},
                "objects": inventory,
            }
            return summary

        except Exception as e:
            cursor.close()
            raise Exception(f"Full object discovery failed: {str(e)}")

