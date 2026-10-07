import pandas as pd
import json
import os

from connectors.sqlserver_connector import SQLServerConnector
from connectors.oracle_connector import OracleConnector


class SchemaAgent:

    def __init__(self, server=None, database=None, source_type="SQL Server", oracle_config=None):
        """
        Initialize SchemaAgent.

        Args:
            server: SQL Server hostname (for SQL Server source)
            database: SQL Server database name (for SQL Server source)
            source_type: "SQL Server" or "Oracle"
            oracle_config: Dict with Oracle connection params:
                {host, port, service_name, sid, username, password, mode, thick_mode, lib_dir}
        """
        self.server = server
        self.database = database
        self.source_type = source_type
        self.oracle_config = oracle_config or {}

    # ============================================================
    # Safe integer conversion
    # ============================================================

    @staticmethod
    def safe_int(value):
        """
        Safely convert SQL metadata values to integer.

        Handles:
            None
            NaN
            pandas NA
            empty strings
            'nan'
            numeric strings
            floats
        """

        if value is None:
            return None

        # Handle pandas NaN / NA
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        # Handle string values
        if isinstance(value, str):

            value = value.strip()

            if value == "":
                return None

            if value.lower() in ("nan", "none", "null"):
                return None

        # Convert safely
        try:
            number = float(value)

            # Explicit NaN check
            if pd.isna(number):
                return None

            return int(number)

        except (ValueError, TypeError, OverflowError):
            return None

    # ============================================================
    # Build complete datatype (SQL Server)
    # ============================================================

    @classmethod
    def build_full_type(cls, row):

        dtype = row.get("DATA_TYPE")

        # --------------------------------------------------------
        # Handle NULL datatype
        # --------------------------------------------------------

        if dtype is None:
            return ""

        try:
            if pd.isna(dtype):
                return ""
        except (TypeError, ValueError):
            pass

        dtype = str(dtype).upper().strip()

        # --------------------------------------------------------
        # Get metadata
        # --------------------------------------------------------

        char_len = cls.safe_int(
            row.get("CHARACTER_MAXIMUM_LENGTH")
        )

        num_prec = cls.safe_int(
            row.get("NUMERIC_PRECISION")
        )

        num_scale = cls.safe_int(
            row.get("NUMERIC_SCALE")
        )

        # ========================================================
        # Character types
        # ========================================================

        if dtype in (
            "VARCHAR",
            "CHAR",
            "NVARCHAR",
            "NCHAR"
        ):

            if char_len is None:
                return dtype

            # SQL Server uses -1 for MAX
            if char_len == -1:
                return f"{dtype}(MAX)"

            return f"{dtype}({char_len})"

        # ========================================================
        # Decimal / Numeric
        # ========================================================

        if dtype in (
            "DECIMAL",
            "NUMERIC"
        ):

            if num_prec is not None and num_scale is not None:

                return (
                    f"{dtype}"
                    f"({num_prec},{num_scale})"
                )

            if num_prec is not None:

                return (
                    f"{dtype}"
                    f"({num_prec})"
                )

            return dtype

        # ========================================================
        # Binary types
        # ========================================================

        if dtype in (
            "VARBINARY",
            "BINARY"
        ):

            if char_len is None:
                return dtype

            if char_len == -1:
                return f"{dtype}(MAX)"

            return f"{dtype}({char_len})"

        # ========================================================
        # Other datatypes
        # ========================================================

        return dtype

    # ============================================================
    # Build complete datatype (Oracle)
    # ============================================================

    @classmethod
    def build_oracle_full_type(cls, row):
        """
        Build full Oracle data type string from metadata.

        Args:
            row: Dict or Series with DATA_TYPE, DATA_LENGTH,
                 DATA_PRECISION, DATA_SCALE

        Returns:
            Full type string e.g. "VARCHAR2(100)", "NUMBER(10,2)"
        """
        dtype = row.get("DATA_TYPE")

        if dtype is None:
            return ""

        try:
            if pd.isna(dtype):
                return ""
        except (TypeError, ValueError):
            pass

        dtype = str(dtype).upper().strip()

        length = cls.safe_int(row.get("DATA_LENGTH"))
        precision = cls.safe_int(row.get("DATA_PRECISION"))
        scale = cls.safe_int(row.get("DATA_SCALE"))

        # Character types: VARCHAR2, CHAR, NVARCHAR2, NCHAR, RAW
        if dtype in ("VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR", "RAW"):
            if length is not None:
                return f"{dtype}({length})"
            return dtype

        # NUMBER with precision and scale
        if dtype == "NUMBER":
            if precision is not None and scale is not None:
                return f"{dtype}({precision},{scale})"
            if precision is not None:
                return f"{dtype}({precision})"
            return dtype

        # FLOAT with precision
        if dtype == "FLOAT":
            if precision is not None:
                return f"{dtype}({precision})"
            return dtype

        # TIMESTAMP types with precision
        if dtype.startswith("TIMESTAMP"):
            if precision is not None:
                return f"{dtype}({precision})"
            return dtype

        # All other types (DATE, CLOB, BLOB, LONG, etc.)
        return dtype

    # ============================================================
    # Schema Discovery
    # ============================================================

    def discover_schema(self, schema_owner=None):
        """
        Discover schema from the configured source database.

        Args:
            schema_owner: (Oracle only) Schema/owner to query.
                         If None, uses current user's objects.

        Returns:
            DataFrame with standardized columns:
                TABLE_NAME, COLUMN_NAME, DATA_TYPE, FULL_DATA_TYPE,
                IS_NULLABLE, ORDINAL_POSITION,
                SOURCE_LENGTH, SOURCE_PRECISION, SOURCE_SCALE
        """
        if self.source_type == "SQL Server":
            return self._discover_sqlserver_schema()
        elif self.source_type in ("Oracle (Real)", "Oracle"):
            return self._discover_oracle_schema(schema_owner)
        else:
            raise ValueError(f"Unsupported source type: {self.source_type}")

    # ============================================================
    # SQL Server Schema Discovery
    # ============================================================

    def _discover_sqlserver_schema(self):

        connector = SQLServerConnector(
            self.server,
            self.database
        )

        conn = connector.connect()

        try:

            query = """
            SELECT
                TABLE_SCHEMA,
                TABLE_NAME,
                COLUMN_NAME,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                IS_NULLABLE,
                ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
            ORDER BY
                TABLE_NAME,
                ORDINAL_POSITION
            """

            df = pd.read_sql(query, conn)

            # ====================================================
            # Build complete datatype
            # ====================================================

            df["FULL_DATA_TYPE"] = df.apply(
                self.build_full_type,
                axis=1
            )

            # ====================================================
            # Add normalized metadata for AI
            # ====================================================

            df["SOURCE_LENGTH"] = df[
                "CHARACTER_MAXIMUM_LENGTH"
            ].apply(self.safe_int)

            df["SOURCE_PRECISION"] = df[
                "NUMERIC_PRECISION"
            ].apply(self.safe_int)

            df["SOURCE_SCALE"] = df[
                "NUMERIC_SCALE"
            ].apply(self.safe_int)

            # ====================================================
            # Export metadata
            #
            # IMPORTANT:
            # Convert NaN -> None before JSON export
            # ====================================================

            metadata_df = df.astype(object).where(
                pd.notna(df),
                None
            )

            metadata = {}

            for table in metadata_df[
                "TABLE_NAME"
            ].unique():

                table_df = metadata_df[
                    metadata_df["TABLE_NAME"] == table
                ]

                metadata[table] = table_df.to_dict(
                    orient="records"
                )

            # ====================================================
            # Create data directory
            # ====================================================

            data_dir = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "data"
                )
            )

            os.makedirs(
                data_dir,
                exist_ok=True
            )

            metadata_file = os.path.join(
                data_dir,
                "metadata.json"
            )

            # ====================================================
            # Save metadata
            # ====================================================

            with open(
                metadata_file,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    metadata,
                    f,
                    indent=4,
                    ensure_ascii=False
                )

            return df

        finally:

            conn.close()

    # ============================================================
    # Oracle Schema Discovery (Real Database)
    # ============================================================

    def _discover_oracle_schema(self, schema_owner=None):
        """
        Discover schema from a real Oracle database and return
        standardized DataFrame matching the SQL Server format.
        """
        connector = OracleConnector(
            host=self.oracle_config.get("host", "localhost"),
            port=self.oracle_config.get("port", 1521),
            service_name=self.oracle_config.get("service_name"),
            sid=self.oracle_config.get("sid"),
            username=self.oracle_config.get("username", ""),
            password=self.oracle_config.get("password", ""),
            mode=self.oracle_config.get("mode", "NORMAL"),
            thick_mode=self.oracle_config.get("thick_mode", False),
            lib_dir=self.oracle_config.get("lib_dir")
        )

        connector.connect()

        try:
            # Use the Oracle connector's discover_schema
            raw_df = connector.discover_schema(schema_owner)

            # Standardize column names to uppercase (match SQL Server format)
            df = pd.DataFrame({
                "TABLE_NAME": raw_df["table_name"].str.upper(),
                "COLUMN_NAME": raw_df["column_name"].str.upper(),
                "DATA_TYPE": raw_df["data_type"].str.upper(),
                "DATA_LENGTH": raw_df["data_length"],
                "DATA_PRECISION": raw_df["data_precision"],
                "DATA_SCALE": raw_df["data_scale"],
                "IS_NULLABLE": raw_df["nullable"],
                "ORDINAL_POSITION": raw_df["ordinal_position"],
            })

            # Build FULL_DATA_TYPE for Oracle
            df["FULL_DATA_TYPE"] = df.apply(
                self.build_oracle_full_type,
                axis=1
            )

            # Add normalized metadata for AI
            df["SOURCE_LENGTH"] = df["DATA_LENGTH"].apply(self.safe_int)
            df["SOURCE_PRECISION"] = df["DATA_PRECISION"].apply(self.safe_int)
            df["SOURCE_SCALE"] = df["DATA_SCALE"].apply(self.safe_int)

            # Export metadata to JSON
            self._export_oracle_metadata(df)

            return df

        finally:
            connector.disconnect()

    # ============================================================
    # Export Oracle metadata to JSON
    # ============================================================

    def _export_oracle_metadata(self, df):
        """Export Oracle schema metadata to JSON in standardized format."""
        data_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "data"
            )
        )

        os.makedirs(data_dir, exist_ok=True)

        # Convert NaN -> None before JSON export
        metadata_df = df.astype(object).where(
            pd.notna(df),
            None
        )

        metadata = {}
        for table in metadata_df["TABLE_NAME"].unique():
            table_df = metadata_df[
                metadata_df["TABLE_NAME"] == table
            ]
            metadata[table] = table_df.to_dict(orient="records")

        metadata_file = os.path.join(data_dir, "metadata.json")

        with open(
            metadata_file,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                metadata,
                f,
                indent=4,
                ensure_ascii=False
            )

    # ============================================================
    # Discover Tables
    # ============================================================

    def discover_tables(self):
        """
        Get list of tables from the configured source.

        Returns:
            DataFrame with TABLE_NAME column
        """
        if self.source_type == "SQL Server":
            return self._discover_sqlserver_tables()
        elif self.source_type in ("Oracle (Real)", "Oracle"):
            return self._discover_oracle_tables()
        else:
            raise ValueError(f"Unsupported source type: {self.source_type}")

    def _discover_sqlserver_tables(self):

        connector = SQLServerConnector(
            self.server,
            self.database
        )

        conn = connector.connect()

        try:

            query = """
            SELECT
                TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
            """

            tables = pd.read_sql(
                query,
                conn
            )

            return tables

        finally:

            conn.close()

    def _discover_oracle_tables(self):
        """Get tables from real Oracle database."""
        connector = OracleConnector(
            host=self.oracle_config.get("host", "localhost"),
            port=self.oracle_config.get("port", 1521),
            service_name=self.oracle_config.get("service_name"),
            sid=self.oracle_config.get("sid"),
            username=self.oracle_config.get("username", ""),
            password=self.oracle_config.get("password", ""),
            mode=self.oracle_config.get("mode", "NORMAL"),
            thick_mode=self.oracle_config.get("thick_mode", False),
            lib_dir=self.oracle_config.get("lib_dir")
        )

        connector.connect()

        try:
            tables = connector.discover_tables()
            return pd.DataFrame({"TABLE_NAME": tables})
        finally:
            connector.disconnect()
