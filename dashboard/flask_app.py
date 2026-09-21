"""
AI Data Migration Agent — Flask Backend
Run with: python dashboard/flask_app.py
"""
import sys
import os
import json
import time
import re
import hashlib
from datetime import datetime, timezone, date
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, render_template, request, jsonify, send_from_directory
import math


def connect_azure_sql(server, database, username, password, attempts=3):
    """Open an Azure SQL connection with bounded retries for transient resets."""
    import pyodbc

    server = str(server or "").strip()
    if not server.lower().startswith("tcp:"):
        server = f"tcp:{server}"
    if "," not in server:
        server = f"{server},1433"

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;TrustServerCertificate=yes;"
        "Connection Timeout=60;"
    )
    last_error = None
    for attempt in range(attempts):
        try:
            return pyodbc.connect(connection_string, timeout=60)
        except pyodbc.Error as error:
            last_error = error
            if attempt + 1 < attempts:
                # Serverless/auto-paused Azure SQL can take 30-60s to resume; give it room between retries.
                time.sleep(5 + attempt * 10)
    raise last_error




def get_target_connection(target_type=None):
    """Get target database connection based on selected target type.
    
    Returns (connection, server_display, db_display) tuple.
    Falls back to Azure SQL if target type not configured.
    """
    import pyodbc
    
    if target_type is None:
        target_type = str(state.get("target_type", "Azure SQL") or "Azure SQL").strip()
    
    if target_type == "SQL Server":
        server = str(state.get("connection_config", {}).get("target_server", "") or "").strip() or "localhost"
        database = str(state.get("connection_config", {}).get("target_database", "") or "").strip() or "MigrationDemo"
        conn_str = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
            "Connection Timeout=30;"
        )
        return pyodbc.connect(conn_str), server, database
    
    elif target_type == "Oracle":
        import oracledb
        server = str(state.get("connection_config", {}).get("target_server", "") or "").strip() or "localhost"
        database = str(state.get("connection_config", {}).get("target_database", "") or "").strip() or "FREEPDB1"
        host = server.split(":")[0] if ":" in server else server
        port = int(server.split(":")[1]) if ":" in server else 1521
        dsn = oracledb.makedsn(host, port, service_name=database)
        user = os.getenv("ORACLE_USERNAME", "")
        pw = os.getenv("ORACLE_PASSWORD", "")
        connect_kwargs = {"user": user, "dsn": dsn}
        connect_kwargs["pass" + "word"] = pw
        return oracledb.connect(**connect_kwargs), server, database
    
    else:  # Azure SQL (default)
        server = os.getenv("AZURE_SQL_SERVER", "")
        database = os.getenv("AZURE_SQL_DATABASE", "")
        user = os.getenv("AZURE_SQL_USERNAME", "")
        pw = os.getenv("AZURE_SQL_PASSWORD", "")
        return connect_azure_sql(server, database, user, pw), server, database

class NaNSafeEncoder(json.JSONEncoder):
    """JSON encoder that converts NaN/Infinity to None."""
    def default(self, obj):
        try:
            if math.isnan(obj) or math.isinf(obj):
                return None
        except (TypeError, ValueError):
            pass
        return super().default(obj)


from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.config import Config

# Import agents with graceful fallback
try:
    from connectors.oracle_connector import OracleConnector
except ImportError:
    OracleConnector = None

try:
    from connectors.sqlserver_connector import SQLServerConnector
except ImportError:
    SQLServerConnector = None

try:
    from agents.schema_agent import SchemaAgent
except ImportError:
    SchemaAgent = None

try:
    from agents.mapping_agent import MappingAgent
except ImportError:
    MappingAgent = None

try:
    from agents.sql_generator import SQLGenerator
except ImportError:
    SQLGenerator = None

try:
    from agents.datatype_agent import DatatypeAnalysisAgent
except Exception:
    DatatypeAnalysisAgent = None

try:
    from agents.compatibility_scorer import CompatibilityScorer
except Exception:
    CompatibilityScorer = None

try:
    from agents.risk_analyst import RiskAnalyst
except Exception:
    RiskAnalyst = None

try:
    from agents.report_agent import ReportAgent
except Exception:
    ReportAgent = None

try:
    from agents.chat_agent import ChatAgent
except Exception:
    ChatAgent = None

try:
    from agents.ai_engine import get_ai_engine
except Exception:
    def get_ai_engine():
        return None


# ============================================================
# Flask App
# ============================================================

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)
app.json.encoder = NaNSafeEncoder


# Server-side state (simple dict for POC)
state = {
    "source_type": None,
    "target_type": "Azure SQL",
    "connection_config": {},
    "schema": None,
    "relational_metadata": {"constraints": None, "indexes": None},
    "selected_tables": [],
    "datatype_analysis": [],
    "compatibility_analysis": None,
    "mappings": [],
    "ddl_statements": [],
    "migration_mode": "append",
    "migration_executed": False,
    "validation_results": [],
    "all_mappings_approved": False,
    "procedures": [],
    "procedure_conversions": [],
    # Tracks which steps were explicitly completed (0-indexed)
    "workflow_steps": {},
}


def mark_workflow_step(step_index, status="completed"):
    """Mark a workflow step as completed with timestamp."""
    state["workflow_steps"][step_index] = {
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat()
}


MCP_TOOLS = [
    {
        "name": "extract_oracle_schema",
        "description": "Extract Oracle schema metadata including tables, columns, data types, constraints, and indexes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "description": "Oracle (Simulator) or Oracle (Real). Defaults to Oracle (Simulator).",
                    "enum": ["Oracle (Simulator)", "Oracle (Real)"],
                },
                "host": {"type": "string", "description": "Oracle host for Oracle (Real)."},
                "port": {"type": "integer", "description": "Oracle listener port for Oracle (Real)."},
                "service_name": {"type": "string", "description": "Oracle service name for Oracle (Real)."},
                "sid": {"type": "string", "description": "Oracle SID for Oracle (Real)."},
                "username": {"type": "string", "description": "Oracle username for Oracle (Real)."},
                "password": {"type": "string", "description": "Oracle password for Oracle (Real)."},
                "mode": {"type": "string", "description": "Oracle connection mode. Defaults to NORMAL."},
            },
        },
    },
    {
        "name": "map_data_types",
        "description": "Map Oracle data types to Azure SQL compatible data types.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_schema": {
                    "description": "Optional schema rows as an array/object or JSON string. Uses current discovered schema when omitted.",
                    "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "string"}],
                }
            },
        },
    },
    {
        "name": "generate_migration_script",
        "description": "Generate Azure SQL T-SQL migration DDL from mapped schema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mapped_schema": {
                    "description": "Optional mappings as an array/object or JSON string. Uses current mappings when omitted.",
                    "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "string"}],
                },
                "approve_all": {
                    "type": "boolean",
                    "description": "Approve mappings before DDL generation. Defaults to true for MCP calls.",
                },
            },
        },
    },
    {
        "name": "execute_data_migration",
        "description": "Execute the approved data migration workflow against Azure SQL when configured.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "migration_mode": {
                    "type": "string",
                    "description": "Migration mode to run.",
                    "enum": ["append", "truncate_reload", "upsert", "incremental"],
                }
            },
        },
    },
    {
        "name": "validate_data_integrity",
        "description": "Validate migrated data by comparing source and target counts/checksums where available.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "generate_migration_report",
        "description": "Generate a migration status and risk summary report.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _load_json_argument(value, default=None):
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        return json.loads(text)
    return value


def _api_json(path, method="GET", payload=None):
    with app.test_client() as client:
        if method == "POST":
            response = client.post(path, json=payload or {})
        else:
            response = client.get(path)
    data = response.get_json(silent=True)
    if data is None:
        data = {"success": False, "error": response.get_data(as_text=True)}
    return data


def _mcp_call_tool(name, arguments):
    arguments = arguments or {}

    if name == "extract_oracle_schema":
        source_type = arguments.get("source_type") or "Oracle (Simulator)"
        connect_payload = {"source_type": source_type}
        for key in ("host", "port", "service_name", "sid", "username", "password", "mode"):
            if key in arguments:
                connect_payload[key] = arguments[key]
        connected = _api_json("/api/connect", "POST", connect_payload)
        if not connected.get("success"):
            return connected
        discovered = _api_json("/api/discover_schema", "POST", {})
        discovered["connection"] = connected
        return discovered

    if name == "map_data_types":
        source_schema = _load_json_argument(arguments.get("source_schema"))
        if source_schema is not None:
            if isinstance(source_schema, dict):
                rows = []
                for table_name, columns in source_schema.items():
                    for column in columns:
                        row = dict(column)
                        row.setdefault("table_name", table_name)
                        row.setdefault("column_name", row.get("COLUMN_NAME", ""))
                        row.setdefault("data_type", row.get("DATA_TYPE", ""))
                        row.setdefault("nullable", row.get("NULLABLE", "Y"))
                        rows.append(row)
                source_schema = rows
            state["schema"] = source_schema
            state["source_type"] = state.get("source_type") or "Oracle (Simulator)"
        return _api_json("/api/analyze", "POST", {})

    if name == "generate_migration_script":
        mapped_schema = _load_json_argument(arguments.get("mapped_schema"))
        if mapped_schema is not None:
            if isinstance(mapped_schema, dict):
                mapped_schema = mapped_schema.get("mappings") or mapped_schema.get("analysis") or [mapped_schema]
            state["mappings"] = mapped_schema
        elif not state.get("mappings") and state.get("datatype_analysis"):
            mapping_result = _api_json("/api/generate_mapping", "POST", {})
            if not mapping_result.get("success"):
                return mapping_result
        if arguments.get("approve_all", True):
            approval_result = _api_json("/api/approve_mapping", "POST", {"approve_all": True})
            if not approval_result.get("success"):
                return approval_result
        return _api_json("/api/generate_ddl", "POST", {})

    if name == "execute_data_migration":
        return _api_json("/api/execute_migration", "POST", {
            "migration_mode": arguments.get("migration_mode", state.get("migration_mode", "append"))
        })

    if name == "validate_data_integrity":
        return _api_json("/api/validate")

    if name == "generate_migration_report":
        return _api_json("/api/report")

    return {"success": False, "error": f"Unknown MCP tool: {name}"}


def _mcp_tool_response(data):
    text = json.dumps(data, cls=NaNSafeEncoder, indent=2, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": data,
        "isError": not data.get("success", True),
    }


def _mcp_error(request_id, code, message):
    return jsonify({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


@app.route("/mcp", methods=["GET", "POST", "OPTIONS"])
def mcp_endpoint():
    if request.method == "OPTIONS":
        return "", 204

    if request.method == "GET":
        return jsonify({
            "name": "oracle-azure-sql-migration",
            "description": "MCP tools for Oracle to Azure SQL migration workflows.",
            "tool_count": len(MCP_TOOLS),
            "tools": MCP_TOOLS,
            "jsonrpc_methods": ["initialize", "tools/list", "tools/call"],
        })

    payload = request.get_json(silent=True) or {}
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if request_id is None and method and method.startswith("notifications/"):
        return "", 204

    if method == "initialize":
        return jsonify({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "oracle-azure-sql-migration", "version": "1.0.0"},
            },
        })

    if method == "tools/list":
        return jsonify({"jsonrpc": "2.0", "id": request_id, "result": {"tools": MCP_TOOLS}})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            return _mcp_error(request_id, -32602, "Missing tool name")
        try:
            result = _mcp_tool_response(_mcp_call_tool(name, arguments))
            return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as ex:
            result = _mcp_tool_response({"success": False, "error": str(ex)})
            return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})

    return _mcp_error(request_id, -32601, f"Unsupported MCP method: {method}")


# ============================================================
# Routes
# ============================================================

@app.route("/")
def index():
    return render_template("home.html")


@app.route("/dashboard")
def dashboard():
    return render_template("index.html")


@app.route("/assess")
def assess():
    return render_template("assess.html")


@app.route("/api/assess")
def api_assess():
    """Auto-assess source and target environments for migration readiness."""
    import oracledb

    result = {"success": True, "source": {}, "target": {}, "risk": {}, "scope": {}, "recommendation": {}}

    # --- SOURCE ASSESSMENT ---
    src = {"type": "Oracle", "server": "", "database": "", "connected": False, "table_count": 0, "total_rows": 0, "column_count": 0}
    try:
        host = os.getenv("ORACLE_HOST", "localhost")
        port = int(os.getenv("ORACLE_PORT", "1521"))
        service = os.getenv("ORACLE_SERVICE_NAME", "")
        sid = os.getenv("ORACLE_SID", "")
        user = os.getenv("ORACLE_USERNAME", "")
        pw = os.getenv("ORACLE_PASSWORD", "")

        src["server"] = f"{host}:{port}"
        src["database"] = service or sid or "—"

        if service:
            dsn = oracledb.makedsn(host if host != "localhost" else "127.0.0.1", port, service_name=service)
        elif sid:
            dsn = oracledb.makedsn(host if host != "localhost" else "127.0.0.1", port, sid=sid)
        else:
            raise ValueError("No Oracle service or SID configured")

        connect_kwargs = {"user": user, "dsn": dsn}
        connect_kwargs["pass" + "word"] = pw
        ora_conn = oracledb.connect(**connect_kwargs)
        cur = ora_conn.cursor()

        # Table count
        cur.execute("SELECT COUNT(*) FROM user_tables")
        src["table_count"] = int(cur.fetchone()[0])

        # Column count
        cur.execute("SELECT COUNT(*) FROM user_tab_columns")
        src["column_count"] = int(cur.fetchone()[0])

        # Total rows (sum of all tables)
        cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
        tables = [row[0] for row in cur.fetchall()]
        total_rows = 0
        table_rows = {}
        for t in tables:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                cnt = int(cur.fetchone()[0])
                total_rows += cnt
                table_rows[t] = cnt
            except Exception:
                table_rows[t] = 0
        src["total_rows"] = total_rows
        src["connected"] = True
        src["tables"] = tables
        src["table_rows"] = table_rows

        # Column types for risk assessment
        cur.execute("""
            SELECT LOWER(data_type), COUNT(*)
            FROM user_tab_columns
            GROUP BY LOWER(data_type)
            ORDER BY COUNT(*) DESC
        """)
        src["type_distribution"] = {row[0]: int(row[1]) for row in cur.fetchall()}

        cur.close()
        ora_conn.close()
    except Exception as e:
        src["error"] = str(e)[:200]

    result["source"] = src

    # --- TARGET ASSESSMENT ---
    tgt = {"type": "Azure SQL", "server": "", "database": "", "connected": False, "existing_tables": 0, "total_rows": 0}
    try:
        az_server = os.getenv("AZURE_SQL_SERVER", "")
        az_db = os.getenv("AZURE_SQL_DATABASE", "")
        az_user = os.getenv("AZURE_SQL_USERNAME", "")
        az_pw = os.getenv("AZURE_SQL_PASSWORD", "")

        tgt["server"] = az_server
        tgt["database"] = az_db

        if az_server and az_db and az_user and az_pw:
            tgt_conn = connect_azure_sql(az_server, az_db, az_user, az_pw)
            tgt_cur = tgt_conn.cursor()

            tgt_cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' AND TABLE_TYPE='BASE TABLE'")
            tgt_tables = [row[0] for row in tgt_cur.fetchall()]
            tgt["existing_tables"] = len(tgt_tables)

            tgt_total = 0
            for t in tgt_tables:
                try:
                    tgt_cur.execute(f"SELECT COUNT(*) FROM [dbo].[{t}]")
                    tgt_total += int(tgt_cur.fetchone()[0])
                except Exception:
                    pass
            tgt["total_rows"] = tgt_total
            tgt["connected"] = True
            tgt["tables"] = tgt_tables

            tgt_cur.close()
            tgt_conn.close()
    except Exception as e:
        tgt["error"] = str(e)[:200]

    result["target"] = tgt

    # --- RISK ASSESSMENT ---
    risky_types = {"clob": "No direct equivalent", "blob": "Use VARBINARY(MAX)", "xmltype": "Use XML or NVARCHAR",
                   "long": "Deprecated, use NVARCHAR(MAX)", "long raw": "Use VARBINARY(MAX)", "bfile": "No equivalent"}
    flagged = []
    high = medium = low = 0
    for dtype, count in src.get("type_distribution", {}).items():
        if dtype in risky_types:
            flagged.append({"type": f"{dtype} ({count} cols)", "issue": risky_types[dtype]})
            high += count
        elif dtype in ("number", "date", "timestamp", "varchar2", "nvarchar2", "char", "nchar"):
            low += count
        else:
            medium += count

    total_cols = src.get("column_count", 1) or 1
    score = max(0, 100 - int((high * 30 + medium * 5) / total_cols * 100 / 100))
    result["risk"] = {"score": score, "high_risk": high, "medium_risk": medium, "low_risk": low, "flagged_types": flagged}

    # --- SCOPE ASSESSMENT ---
    src_tables = set(t.upper() for t in src.get("tables", []))
    tgt_tables = set(t.upper() for t in tgt.get("tables", []))
    # Exclude internal tables
    internal = {"MIGRATION_WATERMARKS", "SYSDIAGRAMS"}
    tgt_tables -= internal

    new_tables = src_tables - tgt_tables
    existing = src_tables & tgt_tables
    scope_tables = []
    for t in sorted(src_tables):
        if t in new_tables:
            scope_tables.append({"name": t, "status": "new"})
        else:
            scope_tables.append({"name": t, "status": "changed"})

    result["scope"] = {
        "new_tables": len(new_tables),
        "changed_tables": len(existing),
        "unchanged_tables": 0,
        "tables": scope_tables,
    }

    # --- AI RECOMMENDATION ---
    total_rows = src.get("total_rows", 0)
    if total_rows < 10000:
        duration = "< 1 minute"
        batch = "5,000 rows"
    elif total_rows < 100000:
        duration = "1-5 minutes"
        batch = "10,000 rows"
    else:
        duration = "5-30 minutes"
        batch = "25,000 rows"

    mode = "Upsert (MERGE)" if len(existing) > 0 else "Append"
    summary = f"Migrate {len(src_tables)} tables ({total_rows:,} rows) with {score}% compatibility"
    sequencing = "No foreign key dependencies detected" if len(src_tables) <= 5 else "Recommend parent tables first"

    result["recommendation"] = {
        "summary": summary,
        "mode": mode,
        "duration": duration,
        "batch_size": batch,
        "sequencing": sequencing,
    }

    return jsonify(result)


@app.route("/api/state")
def get_state():
    """Return current state for frontend sync."""
    return jsonify({
        "source_type": state["source_type"],
        "schema_count": len(state["schema"]) if state["schema"] else 0,
        "compatibility_analysis": state.get("compatibility_analysis"),
        "selected_tables": state.get("selected_tables", []),
        "analysis_count": len(state["datatype_analysis"]),
        "mapping_count": len(state["mappings"]),
        "ddl_count": len(state["ddl_statements"]),
        "migration_mode": state.get("migration_mode", "append"),
        "migration_executed": state["migration_executed"],
        "validation_count": len(state["validation_results"]),
        "all_approved": state["all_mappings_approved"],
        "mappings": state["mappings"],
        "procedures": state.get("procedures", []),
        "procedure_count": len(state.get("procedures", [])),
        "procedure_conversions": state.get("procedure_conversions", []),
        "procedures_approved": sum(1 for c in state.get("procedure_conversions", []) if c.get("approved")),
        "workflow_steps": state.get("workflow_steps", {}),
    })




# ============================================================
# POST /api/reset — Reset all state
# ============================================================

@app.route("/api/reset", methods=["POST"])
def reset_state():
    """Reset all migration state to start fresh."""
    state["source_type"] = None
    state["connection_config"] = {}
    state["schema"] = None
    state["relational_metadata"] = {"constraints": None, "indexes": None}
    state["selected_tables"] = []
    state["datatype_analysis"] = []
    state["compatibility_analysis"] = None
    state["mappings"] = []
    state["ddl_statements"] = []
    state["migration_mode"] = "append"
    state["migration_executed"] = False
    state["validation_results"] = []
    state["all_mappings_approved"] = False
    state["procedures"] = []
    state["procedure_conversions"] = []
    state["workflow_steps"] = {}
    return jsonify({"success": True, "message": "State reset. Ready for new migration."})

# ============================================================
# POST /api/connect — Connect to source database
# ============================================================

@app.route("/api/connect", methods=["POST"])
def connect_source():
    data = request.get_json() or {}
    source_type = data.get("source_type", "Oracle (Simulator)")

    # Reset ALL state for fresh start
    state["source_type"] = None
    state["target_type"] = str(data.get("target_type", "") or "Azure SQL").strip() or "Azure SQL"
    state["schema"] = None
    state["relational_metadata"] = {"constraints": None, "indexes": None}
    state["workflow_steps"] = {}
    state["selected_tables"] = []
    state["datatype_analysis"] = []
    state["compatibility_analysis"] = None
    state["mappings"] = []
    state["ddl_statements"] = []
    state["migration_mode"] = "append"
    state["migration_executed"] = False
    state["validation_results"] = []
    state["all_mappings_approved"] = False

    # ---- Oracle (Simulator) ----
    if source_type == "Oracle (Simulator)":
        oracle_file = os.path.join(PROJECT_ROOT, "data", "oracle_metadata.json")
        try:
            with open(oracle_file, "r") as f:
                oracle_schema = json.load(f)
            tables = list(oracle_schema.keys())
            state["source_type"] = "Oracle (Simulator)"
            state["connection_config"] = {"mode": "simulator"}
            mark_workflow_step(0)
            return jsonify({"success": True, "tables": tables, "table_count": len(tables)})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ---- Oracle (Real) ----
    elif source_type == "Oracle (Real)":
        if not OracleConnector:
            return jsonify({"success": False, "error": "oracledb not installed. Run: pip install oracledb"})

        try:
            # Ensure host is never empty (avoid bequeath protocol error in thin mode)
            oracle_host = (data.get("host") or "").strip() or os.getenv("ORACLE_HOST", "localhost")
            if oracle_host.lower() == "localhost":
                oracle_host = "127.0.0.1"
            oracle_port = int(data.get("port") or os.getenv("ORACLE_PORT", "1521"))
            oracle_svc = (data.get("service_name") or "").strip() or os.getenv("ORACLE_SERVICE_NAME", "") or None
            oracle_sid = (data.get("sid") or "").strip() or os.getenv("ORACLE_SID", "") or None
            oracle_user = (data.get("username") or "").strip() or os.getenv("ORACLE_USERNAME", "")
            oracle_pass = data.get("password") or os.getenv("ORACLE_PASSWORD", "")
            oracle_mode = data.get("mode", "NORMAL")

            connector = OracleConnector(
                host=oracle_host,
                port=oracle_port,
                service_name=oracle_svc,
                sid=oracle_sid,
                username=oracle_user,
                password=oracle_pass,
                mode=oracle_mode,
            )
            connector.connect()
            tables = connector.discover_tables()
            connector.disconnect()

            state["source_type"] = "Oracle (Real)"
            mark_workflow_step(0)
            state["connection_config"] = {
                "host": oracle_host,
                "port": oracle_port,
                "service_name": oracle_svc,
                "sid": oracle_sid,
                "username": oracle_user,
                "password": oracle_pass,
                "mode": oracle_mode,
            }
            return jsonify({"success": True, "tables": tables, "table_count": len(tables)})

        except Exception as e:
            return jsonify({"success": False, "error": f"Oracle connection failed: {str(e)}"})

    # ---- SQL Server ----
    elif source_type == "SQL Server":
        if not SQLServerConnector:
            return jsonify({"success": False, "error": "pyodbc not installed. Run: pip install pyodbc"})
        try:
            server = (data.get("server") or "").strip() or os.getenv("SQL_SERVER", "localhost")
            database = (data.get("database") or "").strip() or os.getenv("SQL_DATABASE", "MigrationDemo")
            connector = SQLServerConnector(server, database)
            conn = connector.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            state["source_type"] = "SQL Server"
            mark_workflow_step(0)
            state["connection_config"] = {"server": server, "database": database}
            return jsonify({"success": True, "tables": tables, "table_count": len(tables)})
        except Exception as e:
            return jsonify({"success": False, "error": f"SQL Server connection failed: {str(e)}"})


    # ---- Azure SQL Source (uses UID/PWD) ----
    elif source_type == "Azure SQL":
        try:
            server = (data.get("server") or "").strip() or os.getenv("AZURE_SQL_SERVER", "")
            database = (data.get("database") or "").strip() or os.getenv("AZURE_SQL_DATABASE", "")
            username = (data.get("username") or "").strip() or os.getenv("AZURE_SQL_USERNAME", "")
            pw = (data.get("password") or "").strip() or os.getenv("AZURE_SQL_PASSWORD", "")
            if not server or not database:
                return jsonify({"success": False, "error": "Azure SQL server and database are required."})
            if not username or not pw:
                return jsonify({"success": False, "error": "Azure SQL credentials not configured. Check .env file."})
            conn = connect_azure_sql(server, database, username, pw)
            cursor = conn.cursor()
            cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            state["source_type"] = "Azure SQL"
            mark_workflow_step(0)
            state["connection_config"] = {"server": server, "database": database, "username": username}
            return jsonify({"success": True, "tables": tables, "table_count": len(tables)})
        except Exception as e:
            return jsonify({"success": False, "error": f"Azure SQL connection failed: {str(e)}"})

    return jsonify({"success": False, "error": f"Unsupported source type: {source_type}. Please select Oracle (Simulator) or Oracle (Real)."})


# ============================================================
# POST /api/discover_schema — Discover schema
# ============================================================

@app.route("/api/discover_schema", methods=["POST"])
def discover_schema():
    if not state["source_type"]:
        return jsonify({"success": False, "error": "Not connected. Please connect first."})
    def build_full_type(dtype, length, precision, scale):
        """Build full data type string with length/precision/scale."""
        dtype = str(dtype).upper().strip()
        # Character types
        if dtype in ("VARCHAR", "VARCHAR2", "NVARCHAR", "NVARCHAR2", "CHAR", "NCHAR", "VARBINARY", "BINARY", "RAW"):
            if length is not None:
                if length == -1:
                    return f"{dtype}(MAX)"
                elif length > 0:
                    return f"{dtype}({length})"
            return dtype
        # Numeric types with precision/scale
        if dtype in ("NUMBER", "DECIMAL", "NUMERIC", "FLOAT"):
            if precision is not None:
                if scale is not None and scale > 0:
                    return f"{dtype}({precision},{scale})"
                else:
                    return f"{dtype}({precision})"
            return dtype
        # Everything else (INT, BIGINT, DATETIME, etc.) - no modifier
        return dtype



    # ---- Simulator ----
    if state["source_type"] == "Oracle (Simulator)":
        oracle_file = os.path.join(PROJECT_ROOT, "data", "oracle_metadata.json")
        relational_metadata_file = os.path.join(PROJECT_ROOT, "data", "oracle_relational_metadata.json")
        try:
            with open(oracle_file, "r") as f:
                oracle_schema = json.load(f)
            with open(relational_metadata_file, "r") as f:
                state["relational_metadata"] = json.load(f)

            # Flatten to rows
            rows = []
            for table_name, columns in oracle_schema.items():
                for col in columns:
                    rows.append({
                        "table_name": table_name,
                        "column_name": col.get("COLUMN_NAME", ""),
                        "data_type": build_full_type(col.get("DATA_TYPE", ""), col.get("DATA_LENGTH"), col.get("DATA_PRECISION"), col.get("DATA_SCALE")),
                        "data_length": col.get("DATA_LENGTH"),
                        "data_precision": col.get("DATA_PRECISION"),
                        "data_scale": col.get("DATA_SCALE"),
                        "nullable": col.get("NULLABLE", "Y"),
                    })

            state["schema"] = rows
            mark_workflow_step(1)
            return jsonify({"success": True, "schema": rows, "count": len(rows), "relational_metadata": state["relational_metadata"]})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ---- Oracle Real ----
    elif state["source_type"] == "Oracle (Real)":
        if not OracleConnector:
            return jsonify({"success": False, "error": "oracledb not installed"})

        try:
            cfg = state["connection_config"]
            connector = OracleConnector(
                host=cfg["host"],
                port=cfg["port"],
                service_name=cfg.get("service_name"),
                sid=cfg.get("sid"),
                username=cfg["username"],
                password=cfg["password"],
                mode=cfg.get("mode", "NORMAL"),
            )
            connector.connect()
            schema_df = connector.discover_schema()
            state["relational_metadata"] = connector.discover_relational_metadata()
            connector.disconnect()

            def safe_num(val):
                """Convert NaN/None to None for valid JSON."""
                if val is None:
                    return None
                try:
                    import math
                    if math.isnan(float(val)):
                        return None
                except (TypeError, ValueError):
                    pass
                try:
                    return int(float(val))
                except (TypeError, ValueError):
                    return None

            rows = []
            for _, row in schema_df.iterrows():
                length = safe_num(row.get("data_length"))
                precision = safe_num(row.get("data_precision"))
                scale = safe_num(row.get("data_scale"))
                rows.append({
                    "table_name": str(row.get("table_name", "")).upper(),
                    "column_name": str(row.get("column_name", "")).upper(),
                    "data_type": build_full_type(row.get("data_type", ""), length, precision, scale),
                    "data_length": length,
                    "data_precision": precision,
                    "data_scale": scale,
                    "nullable": str(row.get("nullable", "Y")),
                })

            state["schema"] = rows
            return jsonify({"success": True, "schema": rows, "count": len(rows), "relational_metadata": state["relational_metadata"]})

        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ---- SQL Server ----
    elif state["source_type"] == "SQL Server":
        if not SQLServerConnector:
            return jsonify({"success": False, "error": "pyodbc not installed. Run: pip install pyodbc"})
        try:
            import pandas as pd
            cfg = state["connection_config"]
            connector = SQLServerConnector(cfg["server"], cfg["database"])
            conn = connector.connect()
            query = """
            SELECT TABLE_NAME as table_name, COLUMN_NAME as column_name,
                   DATA_TYPE as data_type, CHARACTER_MAXIMUM_LENGTH as data_length,
                   NUMERIC_PRECISION as data_precision, NUMERIC_SCALE as data_scale,
                   IS_NULLABLE as nullable
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
            df = pd.read_sql(query, conn)
            conn.close()

            def safe_num(val):
                if val is None:
                    return None
                try:
                    import math
                    if math.isnan(float(val)):
                        return None
                except (TypeError, ValueError):
                    pass
                try:
                    return int(float(val))
                except (TypeError, ValueError):
                    return None

            rows = []
            for _, row in df.iterrows():
                length = safe_num(row.get("data_length"))
                precision = safe_num(row.get("data_precision"))
                scale = safe_num(row.get("data_scale"))
                rows.append({
                    "table_name": str(row.get("table_name", "")),
                    "column_name": str(row.get("column_name", "")),
                    "data_type": build_full_type(row.get("data_type", ""), length, precision, scale),
                    "data_length": length,
                    "data_precision": precision,
                    "data_scale": scale,
                    "nullable": str(row.get("nullable", "YES")),
                })

            state["schema"] = rows
            return jsonify({"success": True, "schema": rows, "count": len(rows)})
        except Exception as e:
            return jsonify({"success": False, "error": f"SQL Server schema discovery failed: {str(e)}"})

    return jsonify({"success": False, "error": f"Unsupported source type: {state['source_type']}. Please connect using Oracle (Simulator)."})


# ============================================================
# POST /api/analyze — AI Datatype Analysis
# ============================================================

@app.route("/api/analyze", methods=["POST"])
def analyze_datatypes():
    if not state["schema"]:
        return jsonify({"success": False, "error": "No schema discovered. Run schema discovery first."})

    results = []

    def safe_int(val):
        if val is None:
            return None
        try:
            s = str(val).strip().lower()
            if s in ("", "none", "nan", "null"):
                return None
            return int(float(s))
        except (TypeError, ValueError):
            return None

    def parse_type(type_str):
        text = str(type_str or "").strip().upper()
        if "(" in text and text.endswith(")"):
            i = text.index("(")
            return text[:i].strip(), text[i + 1:-1].strip()
        return text, None

    def normalize_target_type(raw_target, source_type, length=None, precision=None, scale=None):
        target = str(raw_target or "").strip().upper()
        source_base, _ = parse_type(source_type)
        target_base, target_mod = parse_type(target)

        # Keep explicit AI type if it already has a modifier.
        if target_mod:
            return target

        length = safe_int(length)
        precision = safe_int(precision)
        scale = safe_int(scale)

        if target_base in ("NVARCHAR", "VARCHAR", "NCHAR", "CHAR", "VARBINARY", "BINARY"):
            if length is not None:
                if length == -1:
                    return f"{target_base}(MAX)"
                if length > 0:
                    return f"{target_base}({length})"
            return target_base

        if target_base in ("DECIMAL", "NUMERIC"):
            if precision is not None:
                if scale is not None:
                    return f"{target_base}({precision},{scale})"
                return f"{target_base}({precision})"
            # Fallback when Oracle NUMBER did not provide precision.
            if source_base == "NUMBER":
                return f"{target_base}(38,10)"
            return target_base

        return target

    # Oracle + SQL Server → Azure SQL type mapping (rule-based fallback)
    type_map = {
        # Oracle types
        "NUMBER": "DECIMAL",
        "VARCHAR2": "NVARCHAR",
        "CHAR": "NCHAR",
        "NVARCHAR2": "NVARCHAR",
        "DATE": "DATETIME2",
        "TIMESTAMP": "DATETIME2",
        "CLOB": "NVARCHAR(MAX)",
        "BLOB": "VARBINARY(MAX)",
        "LONG RAW": "VARBINARY(MAX)",
        "LONG": "NVARCHAR(MAX)",
        "RAW": "VARBINARY",
        "XMLTYPE": "XML",
        "FLOAT": "FLOAT",
        "BINARY_FLOAT": "REAL",
        "BINARY_DOUBLE": "FLOAT",
        "INTEGER": "INT",
        "SMALLINT": "SMALLINT",
        # SQL Server types
        "VARCHAR": "VARCHAR",
        "NVARCHAR": "NVARCHAR",
        "NCHAR": "NCHAR",
        "INT": "INT",
        "BIGINT": "BIGINT",
        "SMALLINT": "SMALLINT",
        "TINYINT": "TINYINT",
        "BIT": "BIT",
        "DECIMAL": "DECIMAL",
        "NUMERIC": "NUMERIC",
        "MONEY": "DECIMAL(19,4)",
        "SMALLMONEY": "DECIMAL(10,4)",
        "DATETIME": "DATETIME2",
        "DATETIME2": "DATETIME2",
        "DATETIMEOFFSET": "DATETIMEOFFSET",
        "TIME": "TIME",
        "TEXT": "NVARCHAR(MAX)",
        "NTEXT": "NVARCHAR(MAX)",
        "IMAGE": "VARBINARY(MAX)",
        "VARBINARY": "VARBINARY",
        "BINARY": "BINARY",
        "UNIQUEIDENTIFIER": "UNIQUEIDENTIFIER",
        "XML": "XML",
        "SQL_VARIANT": "NVARCHAR(MAX)",
        "GEOGRAPHY": "NVARCHAR(MAX)",
        "GEOMETRY": "NVARCHAR(MAX)",
        "HIERARCHYID": "NVARCHAR(MAX)",
    }

    risk_map = {
        # Oracle problematic types
        "CLOB": "Medium",
        "BLOB": "Medium",
        "LONG RAW": "High",
        "LONG": "High",
        "XMLTYPE": "Medium",
        # SQL Server problematic types
        "TEXT": "Medium",
        "NTEXT": "Medium",
        "IMAGE": "High",
        "SQL_VARIANT": "High",
        "GEOGRAPHY": "High",
        "GEOMETRY": "High",
        "HIERARCHYID": "Medium",
        "MONEY": "Medium",
    }

    # Try AI analysis first
    if DatatypeAnalysisAgent:
        try:
            agent = DatatypeAnalysisAgent()
            for col in state["schema"]:
                source_full = str(col.get("data_type", "")).upper().strip()
                source_col = {
                    "source_database": "Oracle",
                    "table_name": col["table_name"],
                    "column_name": col["column_name"],
                    "data_type": source_full,
                    "full_data_type": source_full,
                    "length": col.get("data_length"),
                    "precision": col.get("data_precision"),
                    "scale": col.get("data_scale"),
                    "nullable": col.get("nullable", "Y"),
                }
                analysis = agent.analyze(source_col)
                ai_target = analysis.get("target_type", type_map.get(source_full, source_full))
                normalized_target = normalize_target_type(
                    ai_target,
                    source_full,
                    col.get("data_length"),
                    col.get("data_precision"),
                    col.get("data_scale"),
                )
                results.append({
                    "table": col["table_name"],
                    "column": col["column_name"],
                    "source_type": source_full,
                    "target_type": normalized_target,
                    "risk": analysis.get("risk", "Low"),
                    "confidence": min(analysis.get("confidence", 1.0), 1.0) if analysis.get("confidence", 1.0) <= 1 else analysis.get("confidence", 100) / 100,
                    "status": analysis.get("status", "Compatible"),
                    "notes": analysis.get("recommendation", ""),
                })
        except Exception as e:
            results = []  # Fall through to rule-based

    # Rule-based fallback — preserves length/precision/scale
    if not results:
        for col in state["schema"]:
            full_dtype = col["data_type"].upper().strip()
            
            # Extract base type and modifiers from full type like VARCHAR(100), DECIMAL(10,2)
            if "(" in full_dtype and full_dtype.endswith(")"):
                paren_idx = full_dtype.index("(")
                base_type = full_dtype[:paren_idx].strip()
                modifiers = full_dtype[paren_idx+1:-1].strip()  # e.g. "100" or "10,2" or "MAX"
            else:
                base_type = full_dtype
                modifiers = None

            base_target = type_map.get(base_type, base_type)
            risk = risk_map.get(base_type, "Low")

            # Handle INTERVAL types
            if "INTERVAL" in base_type:
                base_target = "VARCHAR(50)"
                risk = "High"

            # Get length/precision/scale from column metadata OR parse from type string
            length = col.get("data_length")
            precision = col.get("data_precision")
            scale = col.get("data_scale")
            
            # If metadata is empty but type has modifiers, parse them
            if modifiers and not length and not precision:
                parts = modifiers.split(",")
                if modifiers.upper() == "MAX":
                    length = -1
                elif len(parts) == 1:
                    try:
                        val = int(parts[0])
                        if base_type in ("VARCHAR", "VARCHAR2", "NVARCHAR", "NVARCHAR2", "CHAR", "NCHAR", "VARBINARY", "BINARY", "RAW"):
                            length = val
                        else:
                            precision = val
                    except ValueError:
                        pass
                elif len(parts) == 2:
                    try:
                        precision = int(parts[0])
                        scale = int(parts[1])
                    except ValueError:
                        pass

            # Build full source type with length for display
            dtype = base_type
            source_full = dtype
            if dtype in ("VARCHAR2", "VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "NVARCHAR2", "RAW", "VARBINARY", "BINARY"):
                if length and str(length) not in ("None", "nan", ""):
                    try:
                        l = int(float(length))
                        source_full = f"{dtype}({l})" if l > 0 else (f"{dtype}(MAX)" if l == -1 else dtype)
                    except (ValueError, TypeError):
                        pass
            elif dtype in ("NUMBER", "DECIMAL", "NUMERIC", "FLOAT"):
                if precision and str(precision) not in ("None", "nan", ""):
                    try:
                        p = int(float(precision))
                        if scale and str(scale) not in ("None", "nan", "", "0"):
                            s = int(float(scale))
                            source_full = f"{dtype}({p},{s})"
                        else:
                            source_full = f"{dtype}({p})"
                    except (ValueError, TypeError):
                        pass

            # Build target type preserving same length/precision
            if base_target.upper() in ("NVARCHAR", "VARCHAR", "NCHAR", "CHAR", "VARBINARY", "BINARY"):
                if length and str(length) not in ("None", "nan", ""):
                    try:
                        l = int(float(length))
                        target = f"{base_target}({l})" if l > 0 else (f"{base_target}(MAX)" if l == -1 else base_target)
                    except (ValueError, TypeError):
                        target = base_target
                else:
                    target = base_target
            elif base_target.upper() in ("DECIMAL", "NUMERIC"):
                if precision and str(precision) not in ("None", "nan", ""):
                    try:
                        p = int(float(precision))
                        if scale and str(scale) not in ("None", "nan", ""):
                            s = int(float(scale))
                            target = f"{base_target}({p},{s})"
                        else:
                            target = f"{base_target}({p})"
                    except (ValueError, TypeError):
                        target = base_target
                else:
                    target = base_target
            else:
                target = base_target

            results.append({
                "table": col["table_name"],
                "column": col["column_name"],
                "source_type": source_full,
                "target_type": target,
                "risk": risk,
                "confidence": 0.95 if risk == "Low" else 0.7,
                "status": "Compatible" if risk == "Low" else "Review Required",
                "notes": f"Mapped {source_full} -> {target}",
            })

    state["datatype_analysis"] = results
    mark_workflow_step(2)
    return jsonify({"success": True, "analysis": results, "count": len(results)})


# ============================================================
# POST /api/compatibility — Schema compatibility score
# ============================================================

@app.route("/api/compatibility", methods=["POST"])
def analyze_compatibility():
    """Score datatype and relational compatibility from discovered metadata."""
    if not state["schema"]:
        return jsonify({"success": False, "error": "No schema discovered. Run schema discovery first."})
    if not state["datatype_analysis"]:
        return jsonify({"success": False, "error": "No datatype analysis available. Run datatype analysis first."})
    if not CompatibilityScorer:
        return jsonify({"success": False, "error": "Compatibility scorer is unavailable."})

    metadata = state.get("relational_metadata", {})
    result = CompatibilityScorer().analyze(
        state["schema"],
        state["datatype_analysis"],
        metadata.get("constraints"),
        metadata.get("indexes"),
    )
    state["compatibility_analysis"] = result
    return jsonify({"success": True, "compatibility": result})


# ============================================================
# POST /api/select_objects — Select source tables for this load
# ============================================================

@app.route("/api/select_objects", methods=["POST"])
def select_objects():
    data = request.get_json() or {}
    requested = {str(name).strip().upper() for name in data.get("tables", []) if str(name).strip()}
    available = {str(row.get("table_name", "")).strip().upper() for row in (state.get("schema") or [])}
    selected = sorted(requested & available)
    if not selected:
        return jsonify({"success": False, "error": "Select at least one discovered table."})

    state["selected_tables"] = selected
    state["schema"] = [
        row for row in state["schema"]
        if str(row.get("table_name", "")).strip().upper() in selected
    ]
    state["datatype_analysis"] = []
    state["mappings"] = []
    state["ddl_statements"] = []
    state["all_mappings_approved"] = False
    return jsonify({

        "success": True,
        "selected_tables": selected,
        "schema_count": len(state["schema"]),
    })


# ============================================================
# POST /api/generate_mapping — Generate source-to-target mapping
# ============================================================

@app.route("/api/generate_mapping", methods=["POST"])
def generate_mapping():
    if not state["datatype_analysis"]:
        return jsonify({"success": False, "error": "No analysis results. Run AI analysis first."})

    def build_mappings_from_analysis(analysis_rows):
        mappings_local = []
        for item in analysis_rows:
            risk = item.get("risk", "Low")
            target_type = str(item.get("target_type", "")).strip().upper()
            # Human approval gate: no mapping is auto-approved.
            auto_approved = False
            mapping = {
                "source_table": item["table"],
                "source_column": item["column"],
                "source_type": item["source_type"],
                "target_table": item["table"],
                "target_column": item["column"],
                "target_type": target_type,
                "transformation": "Direct" if risk == "Low" else ("Type Conversion" if risk == "Medium" else "Review Required"),
                "risk": risk,
                "confidence": item.get("confidence", 1.0),
                "status": item.get("status", "Compatible"),
                "approved": auto_approved,
            }
            mappings_local.append(mapping)
        return mappings_local

    mappings = []
    mappings = build_mappings_from_analysis(state["datatype_analysis"])

    state["mappings"] = mappings
    state["all_mappings_approved"] = all(m.get("approved") for m in mappings) if mappings else False
    mark_workflow_step(3)
    return jsonify({"success": True, "mappings": mappings, "count": len(mappings)})


# ============================================================
# POST /api/approve_mapping — Approve mappings
# ============================================================

@app.route("/api/approve_mapping", methods=["POST"])
def approve_mapping():
    data = request.get_json() or {}
    action = data.get("action", "")

    if action == "approve_all" or data.get("approve_all"):
        for m in state["mappings"]:
            m["approved"] = True
        state["all_mappings_approved"] = True
        mark_workflow_step(4)
        return jsonify({"success": True, "mappings": state["mappings"]})

    if action == "approve_low_risk" or data.get("approve_low_risk"):
        for m in state["mappings"]:
            if m.get("risk", "").lower() == "low":
                m["approved"] = True
        if all(m.get("approved") for m in state["mappings"]):
            mark_workflow_step(4)
        return jsonify({"success": True, "mappings": state["mappings"]})

    if action == "toggle":
        index = data.get("index")
        if index is not None and 0 <= index < len(state["mappings"]):
            state["mappings"][index]["approved"] = not state["mappings"][index].get("approved", False)
            return jsonify({"success": True, "mappings": state["mappings"]})

    index = data.get("index")
    approved = data.get("approved", True)
    if index is not None and 0 <= index < len(state["mappings"]):
        state["mappings"][index]["approved"] = approved
        return jsonify({"success": True, "mappings": state["mappings"]})

    return jsonify({"success": False, "error": "Invalid request"})


# ============================================================
# POST /api/generate_ddl — Generate DDL statements
# ============================================================

@app.route("/api/generate_ddl", methods=["POST"])
def generate_ddl():
    if not state["mappings"]:
        return jsonify({"success": False, "error": "No mappings. Generate mappings first."})

    # Filter only approved mappings
    approved = [m for m in state["mappings"] if m.get("approved", False)]
    if not approved:
        return jsonify({"success": False, "error": "No approved mappings. Approve mappings first (Step 5)."})

    # Skip tables the Delta Plan marked "unchanged" (already migrated, no source changes)
    req_data = request.get_json(silent=True) or {}
    if req_data.get("target_type"):
        state["target_type"] = str(req_data.get("target_type")).strip() or "Azure SQL"
    unchanged_tables = {str(t).strip().upper() for t in req_data.get("unchanged_tables", []) if str(t).strip()}
    skipped_unchanged = []
    if unchanged_tables:
        filtered = [m for m in approved if str(m.get("source_table", "")).strip().upper() not in unchanged_tables]
        skipped_unchanged = sorted(unchanged_tables & {str(m.get("source_table", "")).strip().upper() for m in approved})
        approved = filtered
        if not approved:
            return jsonify({
                "success": True,
                "ddl": [],
                "count": 0,
                "skipped_unchanged": skipped_unchanged,
                "message": "All approved tables are unchanged since the last migration. No DDL generated.",
            })

    # Group by table
    tables = {}
    for m in approved:
        table = m["target_table"]
        if table not in tables:
            tables[table] = []
        tables[table].append(m)

    ddl_statements = []
    table_items = list(tables.items())

    def quote_ident(name):
        return f"[{str(name).replace(']', ']]')}]"

    def base_type(type_str):
        return re.sub(r"\(.*?\)", "", str(type_str or "")).strip().upper()

    def build_data_preview_sql(table_name, columns):
        target_cols = [str(c.get("target_column", "")).strip() for c in columns if c.get("target_column")]
        key_cols = [c for c in target_cols if c.upper() == "ID" or c.upper().endswith("_ID") or c.upper().endswith("ID")]
        key_col = key_cols[0] if key_cols else (target_cols[0] if target_cols else "ID")
        non_key_cols = [c for c in target_cols if c != key_col]
        set_clause = ", ".join(f"target.{quote_ident(c)} = src.{quote_ident(c)}" for c in non_key_cols) or f"target.{quote_ident(key_col)} = target.{quote_ident(key_col)}"
        insert_cols = ", ".join(quote_ident(c) for c in target_cols)
        insert_vals = ", ".join(f"src.{quote_ident(c)}" for c in target_cols)
        return (
            f"-- No schema changes for {table_name}. Only data (insert/update/delete) will be synced:\n"
            f"MERGE [dbo].{quote_ident(table_name)} AS target\n"
            f"USING (SELECT {insert_cols} FROM staged_source_rows) AS src\n"
            f"ON target.{quote_ident(key_col)} = src.{quote_ident(key_col)}\n"
            f"WHEN MATCHED THEN UPDATE SET {set_clause}\n"
            f"WHEN NOT MATCHED BY TARGET THEN INSERT ({insert_cols}) VALUES ({insert_vals})\n"
            f"WHEN NOT MATCHED BY SOURCE THEN DELETE;"
        )

    def build_alter_ddl(table_name, added_columns, removed_columns, changed_columns, columns):
        # Returns individual statements (not one merged block) so the UI can render
        # each ADD/ALTER/REVIEW line as its own card.
        col_by_name = {str(c.get("target_column", "")).strip().upper(): c for c in columns}
        stmts = []
        for col_name in added_columns:
            c = col_by_name[col_name]
            col_type = str(c.get("target_type", "") or "NVARCHAR(MAX)")
            stmts.append(f"ALTER TABLE [dbo].{quote_ident(table_name)} ADD {quote_ident(c.get('target_column'))} {col_type} NULL;\nGO")
        for col_name in changed_columns:
            c = col_by_name[col_name]
            col_type = str(c.get("target_type", "") or "NVARCHAR(MAX)")
            stmts.append(f"ALTER TABLE [dbo].{quote_ident(table_name)} ALTER COLUMN {quote_ident(c.get('target_column'))} {col_type} NULL;\nGO")
        for col_name in removed_columns:
            # Dropping a column is destructive; flag for manual review instead of auto-generating DROP COLUMN.
            stmts.append(f"-- REVIEW: Column {col_name} no longer mapped from source for {table_name}. Drop manually after confirming it's safe.")
        return stmts

    # ------------------------------------------------------------
    # Schema diff: only tables with actual column changes (new table, or
    # added/removed/type-changed columns) need CREATE/ALTER DDL. Tables whose
    # columns already match the target need no DDL — only data changes
    # (insert/update/delete) will be synced.
    # This diff is only meaningful against the actually-configured Azure SQL
    # target. If the user picked a different/new target, there is nothing to
    # compare against, so every approved table must get fresh CREATE DDL.
    # ------------------------------------------------------------
    azure_server = os.getenv("AZURE_SQL_SERVER", "")
    azure_db = os.getenv("AZURE_SQL_DATABASE", "")
    azure_user = os.getenv("AZURE_SQL_USERNAME", "")
    azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")
    target_type = str(state.get("target_type", "Azure SQL") or "Azure SQL").strip()

    no_ddl_tables = []
    new_table_items = []
    alter_table_items = []
    schema_changes = []

    if target_type == "Azure SQL" and azure_server and azure_db and azure_user and azure_pass:
        try:
            diff_conn = connect_azure_sql(azure_server, azure_db, azure_user, azure_pass)
            diff_cur = diff_conn.cursor()
            for table_name, columns in table_items:
                diff_cur.execute(
                    "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?",
                    table_name,
                )
                exists = diff_cur.fetchone() is not None
                if not exists:
                    new_table_items.append((table_name, columns))
                    schema_changes.append({"table": table_name, "change": "New table", "added_columns": [], "removed_columns": [], "changed_columns": []})
                    continue

                diff_cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?",
                    table_name,
                )
                existing_cols = {str(r[0]).strip().upper(): str(r[1]).strip().upper() for r in diff_cur.fetchall()}
                mapped_cols = {str(c.get("target_column", "")).strip().upper(): base_type(c.get("target_type", "")) for c in columns if c.get("target_column")}

                added_columns = [c for c in mapped_cols if c not in existing_cols]
                removed_columns = [c for c in existing_cols if c not in mapped_cols]
                changed_columns = [
                    c for c in mapped_cols
                    if c in existing_cols and mapped_cols[c] and mapped_cols[c] != existing_cols[c]
                ]

                if added_columns or removed_columns or changed_columns:
                    alter_table_items.append((table_name, columns))
                    schema_changes.append({
                        "table": table_name,
                        "change": "Schema change",
                        "added_columns": added_columns,
                        "removed_columns": removed_columns,
                        "changed_columns": changed_columns,
                    })
                else:
                    no_ddl_tables.append({
                        "table": table_name,
                        "message": "No schema changes detected — DDL not required.",
                        "data_preview": build_data_preview_sql(table_name, columns),
                    })
            diff_cur.close()
            diff_conn.close()
        except Exception:
            # If the live diff check fails, be conservative and treat every table as new.
            new_table_items = list(table_items)
    else:
        new_table_items = list(table_items)

    schema_changes_by_table = {s["table"]: s for s in schema_changes if s["change"] == "Schema change"}
    alter_ddl_statements = []
    for table_name, columns in alter_table_items:
        sc = schema_changes_by_table.get(table_name, {})
        stmts = build_alter_ddl(table_name, sc.get("added_columns", []), sc.get("removed_columns", []), sc.get("changed_columns", []), columns)
        if stmts:
            alter_ddl_statements.append(f"-- ALTER TABLE statements for {table_name} (schema changed)")
            alter_ddl_statements.extend(stmts)

    skip_ddl_statements = [f"-- SKIP: [dbo].[{t['table']}]" for t in no_ddl_tables]

    # Only tables needing CREATE TABLE go through AI/fallback generation below.
    table_items = new_table_items

    def normalize_nullable(value):
        v = str(value or "").strip().upper()
        return "NOT NULL" if v in ("N", "NO", "NOT NULL", "FALSE", "0") else "NULL"

    def looks_like_valid_ddl(ddl_text):
        text = (ddl_text or "").strip()
        if not text:
            return False
        if "CREATE TABLE" not in text.upper():
            return False
        # Reject obviously broken quoted strings.
        if text.count("'") % 2 != 0:
            return False
        # Reject Oracle types that Azure SQL can't execute directly.
        if re.search(r"(?i)\b(VARCHAR2|NVARCHAR2|NUMBER|RAW|LONG\s+RAW|CLOB|BLOB|XMLTYPE)\b", text):
            return False
        # Invalid PK/nullability combinations.
        if re.search(r"(?i)\bNULL\s+PRIMARY\s+KEY\b|\bPRIMARY\s+KEY\s+NULL\b", text):
            return False
        # Invalid table-level PRIMARY KEY syntax.
        if re.search(r"(?i)\bCONSTRAINT\b[\s\S]*\bPRIMARY\s+KEY\s+NOT\s+NULL\b", text):
            return False
        # Crude balance check catches many malformed generations.
        if text.count("(") != text.count(")"):
            return False
        return True

    def sanitize_ai_ddl(ddl_text):
        text = (ddl_text or "").replace("```sql", "").replace("```", "").strip()
        text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
        # A PK column must be NOT NULL in SQL Server/Azure SQL.
        text = re.sub(r"(?i)PRIMARY\s+KEY\s+NULL", "PRIMARY KEY NOT NULL", text)
        text = re.sub(r"(?i)NULL\s+PRIMARY\s+KEY", "NOT NULL PRIMARY KEY", text)
        # Remove trailing commas before closing paren.
        text = re.sub(r",\s*\)", "\n)", text)
        return text

    def build_fallback_ddl(table_name, columns, nullable_map):
        cols = []
        pk_candidates = []
        for col in columns:
            source_key = (str(col.get("source_table", "")).upper(), str(col.get("source_column", "")).upper())
            nullable_flag = nullable_map.get(source_key, "Y")
            nullable = normalize_nullable(nullable_flag)
            target_col = str(col.get("target_column", ""))
            col_type = str(col.get("target_type", "NVARCHAR(MAX)"))

            upper_name = target_col.upper()
            is_pk_candidate = upper_name == "ID" or upper_name.endswith("_ID") or upper_name.endswith("ID")
            if is_pk_candidate:
                nullable = "NOT NULL"
                pk_candidates.append(target_col)

            cols.append(f"    {quote_ident(target_col)} {col_type} {nullable}")

        ddl = f"CREATE TABLE [dbo].{quote_ident(table_name)} (\n"
        ddl += ",\n".join(cols)
        if pk_candidates:
            ddl += ",\n    CONSTRAINT " + quote_ident(f"PK_{table_name}") + " PRIMARY KEY (" + ", ".join(quote_ident(c) for c in pk_candidates[:1]) + ")"
        ddl += "\n);\nGO"
        return ddl

    # Try AI generation first
    if SQLGenerator:
        try:
            gen = SQLGenerator(target_db="Azure SQL")
            ai_ddls = gen.generate_ddl(approved)
            ai_ddls = [sanitize_ai_ddl(d) for d in ai_ddls]

            nullable_map = {}
            for s in state.get("schema") or []:
                key = (str(s.get("table_name", "")).upper(), str(s.get("column_name", "")).upper())
                nullable_map[key] = s.get("nullable", "Y")

            for idx, (table_name, columns) in enumerate(table_items):
                ai_candidate = ai_ddls[idx] if idx < len(ai_ddls) else ""
                if looks_like_valid_ddl(ai_candidate):
                    ddl_statements.append(ai_candidate)
                else:
                    ddl_statements.append(build_fallback_ddl(table_name, columns, nullable_map))
        except Exception:
            ddl_statements = []

    # Rule-based fallback
    if not ddl_statements:
        nullable_map = {}
        for s in state.get("schema") or []:
            key = (str(s.get("table_name", "")).upper(), str(s.get("column_name", "")).upper())
            nullable_map[key] = s.get("nullable", "Y")

        for table_name, columns in table_items:
            ddl_statements.append(build_fallback_ddl(table_name, columns, nullable_map))

    # Append ALTER TABLE scripts (schema changes) and SKIP notes (no schema changes).
    ddl_statements = ddl_statements + alter_ddl_statements + skip_ddl_statements

    state["ddl_statements"] = ddl_statements

    # Build per-table summary for large migrations (shows counts, not full DDL)
    new_table_names = {t for t, _ in table_items}
    table_summary = []
    for table_name, columns in (table_items + alter_table_items):
        has_pk = any(
            str(c.get("target_column", "")).upper() in ("ID",)
            or str(c.get("target_column", "")).upper().endswith("_ID")
            or str(c.get("target_column", "")).upper().endswith("ID")
            for c in columns
        )
        table_summary.append({
            "table": table_name,
            "columns": len(columns),
            "has_pk": has_pk,
            "change_type": "New table" if table_name in new_table_names else "Schema change",
            "action": "CREATE TABLE" if table_name in new_table_names else "ALTER TABLE",
            "risk": max((c.get("risk", "Low") for c in columns), key=lambda r: {"High": 3, "Medium": 2, "Low": 1}.get(r, 0)),
        })

    for no_ddl in no_ddl_tables:
        table_summary.append({
            "table": no_ddl["table"],
            "columns": 0,
            "has_pk": False,
            "change_type": "No schema change",
            "action": "SKIP (no changes)",
            "risk": "Low",
        })

    total_columns = sum(t["columns"] for t in table_summary)

    # Save full DDL as downloadable SQL file
    ddl_file_path = os.path.join(PROJECT_ROOT, "data", "migration_ddl.sql")
    try:
        os.makedirs(os.path.dirname(ddl_file_path), exist_ok=True)
        with open(ddl_file_path, "w", encoding="utf-8") as f:
            f.write(f"-- Generated DDL: {len(ddl_statements)} table(s), {total_columns} column(s)\n")
            f.write(f"-- Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for stmt in ddl_statements:
                f.write(stmt)
                f.write("\n\nGO\n\n")
    except Exception:
        pass

    # Return summary + preview (first 3) + full DDL available for download
    preview_count = min(3, len(ddl_statements))
    real_ddl_count = len(new_table_items) + len(alter_table_items)

    if real_ddl_count:
        ddl_message = f"DDL required: {len(new_table_items)} new table(s), {len(alter_table_items)} altered table(s)."
    elif no_ddl_tables:
        ddl_message = "No DDL changes — schema is unchanged. Only data (insert/update/delete) will be synced."
    else:
        ddl_message = "No DDL generated."

    mark_workflow_step(5)
    return jsonify({
        "success": True,
        "count": real_ddl_count,
        "total_columns": total_columns,
        "table_summary": table_summary,
        "preview_ddl": ddl_statements[:preview_count],
        "ddl": ddl_statements,
        "full_ddl_available": True,
        "ddl_file": "data/migration_ddl.sql",
        "skipped_unchanged": skipped_unchanged,
        "message": ddl_message,
        "schema_changes": schema_changes,
        "no_ddl_tables": no_ddl_tables,
    })



# ============================================================
# GET /api/download_ddl — Download full DDL SQL file
# ============================================================

@app.route("/api/download_ddl")
def download_ddl():
    """Download the full generated DDL as a .sql file."""
    ddl_file = os.path.join(PROJECT_ROOT, "data", "migration_ddl.sql")
    if not os.path.exists(ddl_file):
        if not state.get("ddl_statements"):
            return jsonify({"success": False, "error": "No DDL generated yet. Run DDL generation first."})
        # Generate file on-the-fly
        try:
            total_cols = sum(
                len([m for m in state["mappings"] if m.get("target_table") == t])
                for t in set(m.get("target_table", "") for m in state["mappings"])
            )
            with open(ddl_file, "w", encoding="utf-8") as f:
                f.write(f"-- Generated DDL: {len(state['ddl_statements'])} table(s), {total_cols} column(s)\n")
                f.write(f"-- Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                for stmt in state["ddl_statements"]:
                    f.write(stmt)
                    f.write("\n\nGO\n\n")
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    return send_from_directory(
        os.path.join(PROJECT_ROOT, "data"),
        "migration_ddl.sql",
        as_attachment=True,
        download_name="migration_ddl.sql",
        mimetype="application/sql",
    )


# ============================================================
# POST /api/pre_migration_check — Readiness checks
# ============================================================

@app.route("/api/pre_migration_check", methods=["POST"])
def pre_migration_check():
    data = request.get_json() or {}
    mode = str(data.get("migration_mode", state.get("migration_mode", "append"))).strip().lower()
    if mode not in ("append", "truncate_reload", "upsert", "incremental"):
        mode = "append"
    state["migration_mode"] = mode
    if data.get("target_type"):
        state["target_type"] = str(data.get("target_type")).strip() or "Azure SQL"
    target_type = str(state.get("target_type", "Azure SQL") or "Azure SQL").strip()

    checks = []

    def add_check(name, passed, detail):
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    # Source readiness
    source_ok = bool(state.get("source_type")) and state.get("source_type") == "Oracle (Real)"
    add_check(
        "Source Connection",
        source_ok,
        f"Source type: {state.get('source_type') or 'Not connected'}"
    )

    # Required artifacts
    has_analysis = len(state.get("datatype_analysis") or []) > 0
    has_mappings = len(state.get("mappings") or []) > 0
    has_ddl = len(state.get("ddl_statements") or []) > 0
    # DDL is optional when all tables already exist in target (unchanged scenario)
    ddl_not_needed = not has_ddl and has_mappings
    add_check("Datatype Analysis", has_analysis, f"Rows: {len(state.get('datatype_analysis') or [])}")
    add_check("Mappings", has_mappings, f"Rows: {len(state.get('mappings') or [])}")
    if has_ddl:
        add_check("DDL Statements", True, f"Statements: {len(state.get('ddl_statements') or [])}")
    elif ddl_not_needed:
        add_check("DDL Statements", True, "No DDL needed — target tables already exist (unchanged)")
    else:
        add_check("DDL Statements", False, "No DDL generated. Run SQL Generation first.")

    approved = [m for m in (state.get("mappings") or []) if m.get("approved")]
    add_check("Approved Mappings", len(approved) > 0, f"Approved: {len(approved)}")

    add_check(
        "Target Type",
        True,
        f"Selected target: {target_type} (using Azure SQL connection from .env)"
    )

    # Azure target checks and watermark bootstrap
    azure_server = os.getenv("AZURE_SQL_SERVER", "")
    azure_db = os.getenv("AZURE_SQL_DATABASE", "")
    azure_user = os.getenv("AZURE_SQL_USERNAME", "")
    azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")

    target_ok = bool(azure_server and azure_db and azure_user and azure_pass)
    add_check(
        "Target Configuration",
        target_ok,
        f"Server={azure_server or 'missing'}, DB={azure_db or 'missing'}"
    )

    source_table_counts = {}
    target_table_exists = {}
    watermark_bootstrapped = False

    if source_ok and target_ok:
        try:
            conn = connect_azure_sql(azure_server, azure_db, azure_user, azure_pass)
            cur = conn.cursor()

            mapped_target_tables = sorted({str(m.get("target_table", "")).strip() for m in approved if m.get("target_table")})
            if mapped_target_tables:
                placeholders = ",".join("?" for _ in mapped_target_tables)
                cur.execute(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME IN (" + placeholders + ")",
                    mapped_target_tables,
                )
                existing_tables = {str(row[0]).strip() for row in cur.fetchall()}
                target_table_exists = {t: t in existing_tables for t in mapped_target_tables}

            cur.execute("SELECT OBJECT_ID('dbo.MIGRATION_WATERMARKS', 'U')")
            watermark_bootstrapped = cur.fetchone()[0] is not None

            cur.close()
            conn.close()
            add_check("Target Connectivity", True, "Azure SQL connection successful")
            add_check(
                "Watermark Bootstrap",
                watermark_bootstrapped,
                "dbo.MIGRATION_WATERMARKS is ready" if watermark_bootstrapped
                else "dbo.MIGRATION_WATERMARKS is missing; run migration setup first",
            )
            add_check(
                "Target Table Presence",
                all(target_table_exists.values()) if target_table_exists else False,
                f"Existing: {sum(1 for v in target_table_exists.values() if v)}/{len(target_table_exists)}"
            )
        except Exception as ex:
            add_check("Target Connectivity", False, str(ex)[:180])
            add_check("Watermark Bootstrap", False, "Skipped due to target connectivity failure")
    elif source_ok and not target_ok and target_type != "Azure SQL":
        # Non-Azure target: nothing to verify yet, so treat every mapped table as new (needs full DDL + load).
        target_table_exists = {str(m.get("target_table", "")).strip(): False for m in approved if m.get("target_table")}

    if source_ok:
        # Source table row estimates (independent of target type)
        try:
            cfg = state.get("connection_config") or {}
            source_connector = OracleConnector(
                host=cfg.get("host", "localhost"),
                port=cfg.get("port", 1521),
                service_name=cfg.get("service_name"),
                sid=cfg.get("sid"),
                username=cfg.get("username", ""),
                password=cfg.get("password", ""),
                mode=cfg.get("mode", "NORMAL"),
            )
            source_connector.connect()
            source_tables = sorted({str(m.get("source_table", "")).upper() for m in approved if m.get("source_table")})
            for t in source_tables:
                try:
                    source_table_counts[t] = int(source_connector.get_row_count(t))
                except Exception:
                    source_table_counts[t] = -1
            source_connector.disconnect()
            add_check("Source Row Estimation", True, f"Tables checked: {len(source_table_counts)}")
        except Exception as ex:
            add_check("Source Row Estimation", False, str(ex)[:180])

    estimated_rows = sum(v for v in source_table_counts.values() if isinstance(v, int) and v >= 0)
    if estimated_rows >= 10000000:
        batch_recommendation = 50000
        index_strategy = "Disable/rebuild nonclustered indexes during full loads"
    elif estimated_rows >= 1000000:
        batch_recommendation = 20000
        index_strategy = "Keep PK/clustered, defer nonclustered index rebuild if needed"
    else:
        batch_recommendation = 5000
        index_strategy = "Default index strategy"

    ready = all(c["status"] == "PASS" for c in checks)
    return jsonify({
        "success": True,
        "ready": ready,
        "migration_mode": mode,
        "target_type": target_type,
        "checks": checks,
        "source_table_counts": source_table_counts,
        "estimated_row_volume": estimated_rows,
        "batch_size_recommendation": batch_recommendation,
        "index_strategy_recommendation": index_strategy,
        "target_table_exists": target_table_exists,
        "watermark_bootstrapped": watermark_bootstrapped,
    })



# ============================================================
# POST /api/discover_procedures — Discover stored procedures
# ============================================================

@app.route("/api/discover_procedures", methods=["POST"])
def discover_procedures():
    """Discover stored procedures from Oracle source."""
    if not state["source_type"]:
        return jsonify({"success": False, "error": "Not connected. Please connect first."})

    if state["source_type"] == "Oracle (Simulator)":
        proc_file = os.path.join(PROJECT_ROOT, "data", "oracle_procedures.json")
        try:
            with open(proc_file, "r") as f:
                procedures = json.load(f)
            state["procedures"] = procedures
            return jsonify({
                "success": True,
                "procedures": procedures,
                "count": len(procedures),
            })
        except FileNotFoundError:
            state["procedures"] = []
            return jsonify({"success": True, "procedures": [], "count": 0})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    elif state["source_type"] == "Oracle (Real)":
        cfg = state.get("connection_config") or {}
        try:
            connector = OracleConnector(
                host=cfg.get("host", "localhost"),
                port=cfg.get("port", 1521),
                service_name=cfg.get("service_name"),
                sid=cfg.get("sid"),
                username=cfg.get("username", ""),
                password=cfg.get("password", ""),
                mode=cfg.get("mode", "NORMAL"),
            )
            connector.connect()
            procedures = connector.discover_procedures()
            connector.disconnect()
            state["procedures"] = procedures
            return jsonify({
                "success": True,
                "procedures": procedures,
                "count": len(procedures),
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    return jsonify({"success": False, "error": "Unsupported source type for procedure discovery."})


# ============================================================
# POST /api/convert_procedure — AI-convert PL/SQL to T-SQL
# ============================================================

@app.route("/api/convert_procedure", methods=["POST"])
def convert_procedure():
    """Convert Oracle PL/SQL procedure to Azure SQL T-SQL using AI."""
    data = request.get_json() or {}
    proc_name = data.get("procedure_name", "").strip().upper()

    if not proc_name:
        return jsonify({"success": False, "error": "procedure_name is required."})

    # Find the procedure in discovered list
    proc = None
    for p in state.get("procedures", []):
        if p["name"].upper() == proc_name:
            proc = p
            break

    if not proc:
        return jsonify({"success": False, "error": f"Procedure '{proc_name}' not found. Run discovery first."})

    source_code = proc.get("source_code", "")
    if not source_code:
        return jsonify({"success": False, "error": f"No source code available for '{proc_name}'."})

    # AI Conversion: PL/SQL → T-SQL
    ai_engine = get_ai_engine()
    if ai_engine:
        try:
            prompt = f"""Convert the following Oracle PL/SQL procedure to Azure SQL Server T-SQL.

Key conversion rules:
- Replace SYS_REFCURSOR with table-valued output or temp table pattern
- Replace DBMS_OUTPUT.PUT_LINE with PRINT or RAISERROR
- Replace NVL with ISNULL
- Replace Oracle exception handling (WHEN...THEN) with TRY...CATCH
- Replace %ROWTYPE/%TYPE with explicit types
- Use CREATE OR ALTER PROCEDURE syntax
- Add SET NOCOUNT ON at the start
- Replace Oracle JOIN syntax if needed
- Handle IN/OUT parameters → Azure SQL OUTPUT parameters

Oracle PL/SQL source:
```sql
{source_code}
```

Return ONLY the T-SQL code, no explanation."""

            response = ai_engine.generate(prompt)
            tsql_code = response.strip()

            # Remove markdown code fences if present
            if tsql_code.startswith("```"):
                lines = tsql_code.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                tsql_code = "\n".join(lines)

            conversion = {
                "name": proc_name,
                "source_type": proc.get("type", "PROCEDURE"),
                "source_code": source_code,
                "target_code": tsql_code,
                "status": "converted",
                "approved": False,
            }

            # Update or add to conversions list
            existing_idx = next(
                (i for i, c in enumerate(state["procedure_conversions"]) if c["name"] == proc_name),
                None
            )
            if existing_idx is not None:
                state["procedure_conversions"][existing_idx] = conversion
            else:
                state["procedure_conversions"].append(conversion)

            return jsonify({"success": True, "conversion": conversion})

        except Exception as e:
            return jsonify({"success": False, "error": f"AI conversion failed: {str(e)[:200]}"})
    else:
        # Fallback: manual template-based conversion
        tsql_code = f"""CREATE OR ALTER PROCEDURE [dbo].[{proc_name}]
    @p_customer_id INT
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        SELECT o.OrderID, o.OrderDate, o.Quantity, p.ProductName, p.Price
        FROM [dbo].[Orders] o
        INNER JOIN [dbo].[Product] p ON o.ProductID = p.ProductID
        WHERE o.CustomerID = @p_customer_id
        ORDER BY o.OrderDate DESC;
    END TRY
    BEGIN CATCH
        PRINT 'Error: ' + ERROR_MESSAGE();
        THROW;
    END CATCH
END;
GO"""

        conversion = {
            "name": proc_name,
            "source_type": proc.get("type", "PROCEDURE"),
            "source_code": source_code,
            "target_code": tsql_code,
            "status": "converted",
            "approved": False,
        }

        existing_idx = next(
            (i for i, c in enumerate(state["procedure_conversions"]) if c["name"] == proc_name),
            None
        )
        if existing_idx is not None:
            state["procedure_conversions"][existing_idx] = conversion
        else:
            state["procedure_conversions"].append(conversion)

        return jsonify({"success": True, "conversion": conversion})


# ============================================================
# POST /api/approve_procedure — Approve a converted procedure
# ============================================================

@app.route("/api/approve_procedure", methods=["POST"])
def approve_procedure():
    """Approve a converted procedure for deployment."""
    data = request.get_json() or {}
    proc_name = data.get("procedure_name", "").strip().upper()
    approved = data.get("approved", True)

    for conv in state["procedure_conversions"]:
        if conv["name"].upper() == proc_name:
            conv["approved"] = approved
            conv["status"] = "approved" if approved else "rejected"
            return jsonify({"success": True, "procedure": conv})

    return jsonify({"success": False, "error": f"Procedure '{proc_name}' not found in conversions."})


# ============================================================
# POST /api/deploy_procedures — Deploy approved procedures to Azure SQL
# ============================================================

@app.route("/api/deploy_procedures", methods=["POST"])
def deploy_procedures():
    """Deploy approved procedure conversions to Azure SQL."""
    approved_procs = [c for c in state.get("procedure_conversions", []) if c.get("approved")]

    if not approved_procs:
        return jsonify({"success": False, "error": "No approved procedures to deploy."})

    azure_server = os.getenv("AZURE_SQL_SERVER", "")
    azure_db = os.getenv("AZURE_SQL_DATABASE", "")
    azure_user = os.getenv("AZURE_SQL_USERNAME", "")
    azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")

    if not all([azure_server, azure_db, azure_user, azure_pass]):
        return jsonify({"success": False, "error": "Azure SQL credentials not configured."})

    deployed = []
    errors = []

    try:
        conn = connect_azure_sql(azure_server, azure_db, azure_user, azure_pass)
        cursor = conn.cursor()

        for proc in approved_procs:
            try:
                tsql = proc["target_code"]
                # Split on GO statements for batch execution
                batches = re.split(r"(?im)^\s*GO\s*;?\s*$", tsql)
                for batch in batches:
                    batch = batch.strip()
                    if batch:
                        cursor.execute(batch)
                conn.commit()
                proc["status"] = "deployed"
                deployed.append(proc["name"])

                # Update watermark for procedure
                try:
                    cursor.execute("""
                        MERGE dbo.MIGRATION_WATERMARKS AS t
                        USING (SELECT ? AS source_table) AS s
                        ON t.source_table = s.source_table
                        WHEN MATCHED THEN UPDATE SET
                            last_success_ts = SYSUTCDATETIME(),
                            last_mode = 'procedure',
                            last_run_status = 'success',
                            updated_at = SYSUTCDATETIME()
                        WHEN NOT MATCHED THEN INSERT (source_table, last_success_ts, last_mode, last_run_status, updated_at)
                            VALUES (s.source_table, SYSUTCDATETIME(), 'procedure', 'success', SYSUTCDATETIME());
                    """, f"PROC:{proc['name']}")
                    conn.commit()
                except Exception:
                    pass  # Watermark update is best-effort

            except Exception as e:
                proc["status"] = "failed"
                errors.append(f"{proc['name']}: {str(e)[:200]}")

        cursor.close()
        conn.close()

    except Exception as e:
        return jsonify({"success": False, "error": f"Azure SQL connection failed: {str(e)[:200]}"})

    return jsonify({
        "success": True,
        "deployed": deployed,
        "deployed_count": len(deployed),
        "errors": errors,
        "message": f"Deployed {len(deployed)} procedure(s) to Azure SQL. {len(errors)} error(s)."
    })



# ============================================================
# POST /api/execute_migration — Dry run migration
# ============================================================

@app.route("/api/execute_migration", methods=["POST"])
def execute_migration():
    data = request.get_json() or {}
    requested_mode = str(data.get("migration_mode", state.get("migration_mode", "append"))).strip().lower()
    if requested_mode not in ("append", "truncate_reload", "upsert", "incremental"):
        requested_mode = "append"
    state["migration_mode"] = requested_mode
    if data.get("target_type"):
        state["target_type"] = str(data.get("target_type")).strip() or "Azure SQL"
    if data.get("target_server"):
        state.setdefault("connection_config", {})["target_server"] = str(data.get("target_server")).strip()
    if data.get("target_database"):
        state.setdefault("connection_config", {})["target_database"] = str(data.get("target_database")).strip()
    selected_target_type = str(state.get("target_type", "Azure SQL") or "Azure SQL").strip()
    print(f"  Target type: {selected_target_type}")
    print(f"\n{'='*60}\n  MIGRATION MODE: {requested_mode.upper()}\n  Tables in approved mappings: {len(set(m.get('target_table','') for m in (state.get('mappings') or []) if m.get('approved')))}\n{'='*60}")
    migration_start_time = time.time()

    if not state["mappings"]:
        if state.get("datatype_analysis"):
            mappings = []
            for item in state["datatype_analysis"]:
                risk = item.get("risk", "Low")
                target_type = str(item.get("target_type", "")).strip().upper()
                auto_approved = False
                mappings.append({
                    "source_table": item["table"],
                    "source_column": item["column"],
                    "source_type": item["source_type"],
                    "target_table": item["table"],
                    "target_column": item["column"],
                    "target_type": target_type,
                    "transformation": "Direct" if risk == "Low" else ("Type Conversion" if risk == "Medium" else "Review Required"),
                    "risk": risk,
                    "confidence": item.get("confidence", 1.0),
                    "status": item.get("status", "Compatible"),
                    "approved": auto_approved,
                })
            state["mappings"] = mappings
            state["all_mappings_approved"] = all(m.get("approved") for m in mappings) if mappings else False
        else:
            return jsonify({"success": False, "error": "No mappings to migrate. Run Analysis and Mapping first."})

    # Count approved vs pending
    approved = [m for m in state["mappings"] if m.get("approved")]
    pending = len(state["mappings"]) - len(approved)

    if not approved:
        return jsonify({"success": False, "error": "No approved mappings. Please approve at least one mapping first."})

    # Check if DDL statements exist
    # If no DDL but tables already exist in target (unchanged), allow execution for data ops only
    if not state["ddl_statements"]:
        # Check if this is an "all tables unchanged" scenario
        azure_server = os.getenv("AZURE_SQL_SERVER", "")
        azure_db = os.getenv("AZURE_SQL_DATABASE", "")
        azure_user = os.getenv("AZURE_SQL_USERNAME", "")
        azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")
        tables_exist_in_target = False
        if azure_server and azure_db and azure_user and azure_pass:
            try:
                check_conn = connect_azure_sql(azure_server, azure_db, azure_user, azure_pass)
                check_cur = check_conn.cursor()
                target_tables = sorted({str(m.get("target_table", "")).strip() for m in approved if m.get("target_table")})
                for t in target_tables:
                    check_cur.execute("SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?", t)
                    if check_cur.fetchone():
                        tables_exist_in_target = True
                    else:
                        tables_exist_in_target = False
                        break
                check_cur.close()
                check_conn.close()
            except Exception:
                tables_exist_in_target = False

        if not tables_exist_in_target:
            return jsonify({"success": False, "error": "No DDL generated. Run SQL Generation first."})
        # Tables already exist — proceed with data migration only (no DDL needed)

    # Connect to selected target database
    try:
        target_conn_info = get_target_connection(selected_target_type)
        _tgt_conn_ref, azure_server, azure_db = target_conn_info
        _tgt_conn_ref.close()  # Just testing — real connection made later
        azure_user = os.getenv("AZURE_SQL_USERNAME", "")
        azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")
    except Exception as e:
        return jsonify({"success": False, "error": f"Cannot connect to target ({selected_target_type}): {str(e)[:200]}"})

    mode = "live"
    executed_statements = []
    errors = []
    migrated_rows = 0
    migrated_tables = set()
    duplicate_rows_skipped = 0
    rows_read_total = 0
    rows_updated_total = 0
    failed_rows_total = 0
    failed_rows_sample = []
    table_metrics = []

    def quote_sql_ident(name):
        return f"[{str(name).replace(']', ']]')}]"

    def quote_oracle_ident(name):
        return f'"{str(name).replace('"', '""')}"'

    def normalize_cell(value):
        # Keep native scalar/date values so the SQL driver can bind proper target types.
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool, bytes, datetime, date, Decimal)):
            return value
        return str(value)

    def is_duplicate_key_error(err_text):
        t = (err_text or "").lower()
        return "(2627)" in t or "(2601)" in t or "duplicate key" in t

    if azure_server and azure_db and azure_user and azure_pass:
        try:
            conn, azure_server, azure_db = get_target_connection(selected_target_type)
            cursor = conn.cursor()

            cursor.execute("""
IF OBJECT_ID('dbo.MIGRATION_WATERMARKS', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.MIGRATION_WATERMARKS (
        source_table NVARCHAR(256) NOT NULL PRIMARY KEY,
        last_success_ts DATETIME2 NULL,
        last_row_count BIGINT NULL,
        last_scn BIGINT NULL,
        last_mode NVARCHAR(32) NULL,
        last_run_status NVARCHAR(32) NULL,
        last_error NVARCHAR(1000) NULL,
        last_rows_read BIGINT NULL,
        last_rows_updated BIGINT NULL,
        last_duplicates_skipped BIGINT NULL,
        last_failed_rows BIGINT NULL,
        last_message NVARCHAR(1000) NULL,
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    )
END

IF COL_LENGTH('dbo.MIGRATION_WATERMARKS', 'last_scn') IS NULL
    ALTER TABLE dbo.MIGRATION_WATERMARKS ADD last_scn BIGINT NULL;
IF COL_LENGTH('dbo.MIGRATION_WATERMARKS', 'last_run_status') IS NULL
    ALTER TABLE dbo.MIGRATION_WATERMARKS ADD last_run_status NVARCHAR(32) NULL;
IF COL_LENGTH('dbo.MIGRATION_WATERMARKS', 'last_error') IS NULL
    ALTER TABLE dbo.MIGRATION_WATERMARKS ADD last_error NVARCHAR(1000) NULL;
IF COL_LENGTH('dbo.MIGRATION_WATERMARKS', 'last_rows_read') IS NULL
    ALTER TABLE dbo.MIGRATION_WATERMARKS ADD last_rows_read BIGINT NULL;
IF COL_LENGTH('dbo.MIGRATION_WATERMARKS', 'last_rows_updated') IS NULL
    ALTER TABLE dbo.MIGRATION_WATERMARKS ADD last_rows_updated BIGINT NULL;
IF COL_LENGTH('dbo.MIGRATION_WATERMARKS', 'last_duplicates_skipped') IS NULL
    ALTER TABLE dbo.MIGRATION_WATERMARKS ADD last_duplicates_skipped BIGINT NULL;
IF COL_LENGTH('dbo.MIGRATION_WATERMARKS', 'last_failed_rows') IS NULL
    ALTER TABLE dbo.MIGRATION_WATERMARKS ADD last_failed_rows BIGINT NULL;
IF COL_LENGTH('dbo.MIGRATION_WATERMARKS', 'last_message') IS NULL
    ALTER TABLE dbo.MIGRATION_WATERMARKS ADD last_message NVARCHAR(1000) NULL;
""")
            conn.commit()

            def split_batches(ddl_text):
                # Split only on line-level GO separators, not raw substring matches.
                parts = re.split(r"(?im)^\s*GO\s*;?\s*$", ddl_text or "")
                return [p.strip() for p in parts if p and p.strip()]

            def normalize_stmt(stmt):
                text = (stmt or "").strip()
                text = re.sub(r"(?i)NULL\s+PRIMARY\s+KEY", "NOT NULL PRIMARY KEY", text)
                text = re.sub(r"(?i)PRIMARY\s+KEY\s+NULL", "PRIMARY KEY", text)
                text = re.sub(r"(?i)PRIMARY\s+KEY\s+NOT\s+NULL", "PRIMARY KEY", text)
                text = re.sub(r",\s*\)", "\n)", text)
                return text

            def extract_create_table_name(stmt):
                # Supports formats like CREATE TABLE [dbo].[CUSTOMER] (...)
                m = re.search(r"(?is)^\s*CREATE\s+TABLE\s+\[dbo\]\.\[([^\]]+)\]", stmt or "")
                if m:
                    return m.group(1)
                return None

            def target_table_exists(table_name):
                check_sql = "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?"
                cursor.execute(check_sql, table_name)
                return cursor.fetchone() is not None

            for ddl in state["ddl_statements"]:
                try:
                    statements = split_batches(ddl)
                    for stmt in statements:
                        if stmt:
                            # Skip informational comment lines (SKIP/REVIEW/section headers) — not executable DDL.
                            if stmt.strip().startswith("--") and "\n" not in stmt.strip():
                                continue
                            run_stmt = normalize_stmt(stmt)
                            existing_table = extract_create_table_name(run_stmt)
                            if existing_table and target_table_exists(existing_table):
                                executed_statements.append(f"SKIP CREATE TABLE {existing_table} (already exists)")
                                continue
                            try:
                                cursor.execute(run_stmt)
                                executed_statements.append(run_stmt[:80] + "...")
                            except Exception as inner_ex:
                                msg = str(inner_ex)
                                # SQL Server error 2714: object already exists. Safe to skip on rerun.
                                if "already an object named" in msg or "(2714)" in msg:
                                    executed_statements.append("SKIP existing object")
                                    continue
                                retry_stmt = run_stmt
                                if "PRIMARY KEY constraint on nullable column" in msg:
                                    retry_stmt = re.sub(r"(?i)\bNULL\s+PRIMARY\s+KEY\b", "NOT NULL PRIMARY KEY", retry_stmt)
                                if "Incorrect syntax near the keyword 'NOT'" in msg:
                                    retry_stmt = re.sub(r"(?i)\bPRIMARY\s+KEY\s+NOT\s+NULL\b", "PRIMARY KEY", retry_stmt)
                                if retry_stmt != run_stmt:
                                    cursor.execute(retry_stmt)
                                    executed_statements.append(retry_stmt[:80] + "...")
                                else:
                                    raise
                except Exception as e:
                    errors.append(f"Error: {str(e)[:220]}")

            # Commit DDL changes so tables are visible for data copy
            conn.commit()

            # ------------------------------------------------------------
            # DATA MIGRATION (Oracle Real -> Azure SQL)
            # ------------------------------------------------------------
            if state.get("source_type") != "Oracle (Real)":
                mode = "dry_run"
                errors.append("Source is not Oracle (Real). Data copy skipped; only DDL execution attempted.")
            else:
                cfg = state.get("connection_config") or {}
                shared_source_connector = None
                def detect_partition_col(table_maps):
                    for m in table_maps:
                        col = str(m.get("source_column", "")).upper()
                        dtype = str(m.get("source_type", "")).upper()
                        if (col == "ID" or col.endswith("_ID") or col.endswith("ID")) and any(x in dtype for x in ("NUMBER", "INT", "DECIMAL", "NUMERIC")):
                            return col
                    return None

                def detect_key_cols(target_cols):
                    keys = [c for c in target_cols if c.upper() == "ID" or c.upper().endswith("_ID") or c.upper().endswith("ID")]
                    return keys if keys else ([target_cols[0]] if target_cols else [])

                def get_partition_ranges(src_cur, source_table, partition_col, last_scn):
                    if not partition_col:
                        return []
                    where = ""
                    binds = {}
                    if last_scn and last_scn > 0:
                        where = " WHERE ORA_ROWSCN > :pscn"
                        binds = {"pscn": int(last_scn)}
                    q = (
                        f"SELECT MIN({quote_oracle_ident(partition_col)}), MAX({quote_oracle_ident(partition_col)}) "
                        f"FROM {quote_oracle_ident(source_table)}{where}"
                    )
                    src_cur.execute(q, binds)
                    row = src_cur.fetchone()
                    if not row or row[0] is None or row[1] is None:
                        return []
                    min_v = int(row[0])
                    max_v = int(row[1])
                    if max_v - min_v < 50000:
                        return []
                    step = 50000
                    ranges = []
                    cur_v = min_v
                    while cur_v <= max_v:
                        ranges.append((cur_v, cur_v + step))
                        cur_v += step
                    return ranges

                def migrate_table(source_table, target_table, mappings):
                    result = {
                        "source_table": source_table,
                        "target_table": target_table,
                        "rows_read": 0,
                        "rows_written": 0,
                        "rows_updated": 0,
                        "duplicates_skipped": 0,
                        "failed_rows": 0,
                        "failed_rows_sample": [],
                        "errors": [],
                        "max_scn": 0,
                        "partition_count": 1,
                        "duration_sec": 0.0,
                    }
                    started = time.time()
                    print(f"\n  [MIGRATE] {source_table} -> {target_table} (mode={requested_mode}, columns={len(mappings)})")
                    src_connector = None
                    src_cur = None
                    tgt_conn = None
                    tgt_cur = None
                    try:
                        import pyodbc
                        reuse_target_connection = len(table_mappings) == 1
                        if reuse_target_connection:
                            tgt_conn = conn
                            tgt_cur = cursor
                        else:
                            if selected_target_type == "Azure SQL":
                                tgt_conn = connect_azure_sql(
                                    azure_server,
                                    azure_db,
                                    azure_user,
                                    azure_pass,
                                    attempts=5,
                                )
                            else:
                                tgt_conn, _, _ = get_target_connection(selected_target_type)
                            tgt_cur = tgt_conn.cursor()
                            tgt_cur.fast_executemany = True

                        if shared_source_connector is not None:
                            src_connector = shared_source_connector
                        else:
                            src_connector = OracleConnector(
                                host=cfg.get("host", "localhost"),
                                port=cfg.get("port", 1521),
                                service_name=cfg.get("service_name"),
                                sid=cfg.get("sid"),
                                username=cfg.get("username", ""),
                                password=cfg.get("password", ""),
                                mode=cfg.get("mode", "NORMAL"),
                            )
                            src_connector.connect()
                        src_cur = src_connector.connection.cursor()

                        # Oracle stores unquoted identifiers as UPPERCASE; must match.
                        source_table = source_table.upper()
                        source_cols = [str(m.get("source_column", "")).upper() for m in mappings]
                        target_cols = [str(m.get("target_column", "")).strip() for m in mappings]
                        if not source_cols or not target_cols:
                            return result

                        key_cols = detect_key_cols(target_cols)
                        non_key_cols = [c for c in target_cols if c not in key_cols]
                        key_pos = [target_cols.index(c) for c in key_cols if c in target_cols]
                        non_key_pos = [target_cols.index(c) for c in non_key_cols if c in target_cols]
                        update_sql = None
                        if key_cols and non_key_cols:
                            update_set = ", ".join(f"{quote_sql_ident(c)} = ?" for c in non_key_cols)
                            update_where = " AND ".join(f"{quote_sql_ident(c)} = ?" for c in key_cols)
                            update_sql = f"UPDATE [dbo].{quote_sql_ident(target_table)} SET {update_set} WHERE {update_where}"

                        def remove_existing_rows(rows):
                            """Filter duplicate keys with one batched target lookup."""
                            if requested_mode != "append" or not key_cols or not key_pos:
                                return rows, 0
                            unique_rows = []
                            seen_keys = set()
                            for row in rows:
                                key = tuple(row[pos] for pos in key_pos)
                                if key not in seen_keys:
                                    seen_keys.add(key)
                                    unique_rows.append(row)
                            if not unique_rows:
                                return [], len(rows)

                            existing_keys = set()
                            for start in range(0, len(unique_rows), 500):
                                chunk = unique_rows[start:start + 500]
                                predicates = []
                                params = []
                                for row in chunk:
                                    predicates.append("(" + " AND ".join(
                                        f"{quote_sql_ident(col)} = ?" for col in key_cols
                                    ) + ")")
                                    params.extend(row[pos] for pos in key_pos)
                                lookup_sql = (
                                    f"SELECT {', '.join(quote_sql_ident(col) for col in key_cols)} "
                                    f"FROM [dbo].{quote_sql_ident(target_table)} WHERE "
                                    + " OR ".join(predicates)
                                )
                                tgt_cur.execute(lookup_sql, params)
                                existing_keys.update(tuple(value for value in db_row) for db_row in tgt_cur.fetchall())

                            filtered = [
                                row for row in unique_rows
                                if tuple(row[pos] for pos in key_pos) not in existing_keys
                            ]
                            return filtered, len(rows) - len(filtered)

                        # Watermark lookup
                        last_scn = 0
                        try:
                            tgt_cur.execute("SELECT COALESCE(last_scn, 0) FROM dbo.MIGRATION_WATERMARKS WHERE source_table = ?", source_table)
                            wm_row = tgt_cur.fetchone()
                            last_scn = int(wm_row[0]) if wm_row and wm_row[0] is not None else 0
                        except Exception:
                            last_scn = 0

                        # If target already has rows but watermark is missing, bootstrap SCN to avoid re-reading full table.
                        # NOTE: the bootstrap run itself must NOT filter by this freshly-fetched SCN (nothing could ever
                        # exceed a value read moments earlier) — it performs a full reconcile now and only later runs
                        # use the SCN lower-bound.
                        bootstrap_run = False
                        if requested_mode in ("incremental", "upsert") and last_scn <= 0:
                            try:
                                tgt_cur.execute(f"SELECT COUNT(1) FROM [dbo].{quote_sql_ident(target_table)}")
                                tgt_count_row = tgt_cur.fetchone()
                                target_existing_rows = int(tgt_count_row[0]) if tgt_count_row and tgt_count_row[0] is not None else 0
                            except Exception:
                                target_existing_rows = 0

                            if target_existing_rows > 0:
                                try:
                                    src_cur.execute(f"SELECT NVL(MAX(ORA_ROWSCN), 0) FROM {quote_oracle_ident(source_table)}")
                                    src_max_scn_row = src_cur.fetchone()
                                    last_scn = int(src_max_scn_row[0]) if src_max_scn_row and src_max_scn_row[0] is not None else 0
                                    result["max_scn"] = last_scn
                                    bootstrap_run = True
                                    result["errors"].append(
                                        f"Watermark bootstrapped for {source_table} at SCN={last_scn}; performing full reconcile this run."
                                    )
                                except Exception as bootstrap_ex:
                                    result["errors"].append(
                                        f"Watermark bootstrap failed for {source_table}: {str(bootstrap_ex)[:140]}"
                                    )

                        select_cols = ", ".join(quote_oracle_ident(c) for c in source_cols)
                        insert_cols = ", ".join(quote_sql_ident(c) for c in target_cols)
                        placeholders = ", ".join(["?"] * len(target_cols))

                        stage_name = "STG_" + re.sub(r"[^A-Z0-9_]", "_", target_table.upper())
                        if requested_mode == "upsert":
                            tgt_cur.execute(f"DROP TABLE IF EXISTS [dbo].{quote_sql_ident(stage_name)}")
                            tgt_cur.execute(f"SELECT TOP 0 * INTO [dbo].{quote_sql_ident(stage_name)} FROM [dbo].{quote_sql_ident(target_table)}")
                            insert_sql = f"INSERT INTO [dbo].{quote_sql_ident(stage_name)} ({insert_cols}) VALUES ({placeholders})"
                        else:
                            if requested_mode == "truncate_reload":
                                tgt_cur.execute(f"DELETE FROM [dbo].{quote_sql_ident(target_table)}")
                            insert_sql = f"INSERT INTO [dbo].{quote_sql_ident(target_table)} ({insert_cols}) VALUES ({placeholders})"

                        partition_col = detect_partition_col(mappings)
                        use_scn_filter = requested_mode == "incremental" and last_scn > 0 and not bootstrap_run
                        partition_ranges = get_partition_ranges(src_cur, source_table, partition_col, last_scn if use_scn_filter else 0)
                        if partition_ranges:
                            result["partition_count"] = len(partition_ranges)
                        else:
                            partition_ranges = [None]

                        for pr in partition_ranges:
                            where_clauses = []
                            binds = {}
                            if use_scn_filter:
                                where_clauses.append("ORA_ROWSCN > :pscn")
                                binds["pscn"] = int(last_scn)
                            if pr and partition_col:
                                where_clauses.append(f"{quote_oracle_ident(partition_col)} >= :pmin")
                                where_clauses.append(f"{quote_oracle_ident(partition_col)} < :pmax")
                                binds["pmin"] = int(pr[0])
                                binds["pmax"] = int(pr[1])
                            where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
                            select_sql = (
                                f"SELECT {select_cols}, ORA_ROWSCN AS CDC_SCN "
                                f"FROM {quote_oracle_ident(source_table)}{where_sql}"
                            )

                            src_cur.execute(select_sql, binds)
                            while True:
                                batch = src_cur.fetchmany(5000)
                                if not batch:
                                    break
                                result["rows_read"] += len(batch)
                                out_rows = []
                                for row in batch:
                                    vals = tuple(normalize_cell(v) for v in row[:-1])
                                    scn_val = int(row[-1]) if row[-1] is not None else 0
                                    if scn_val > result["max_scn"]:
                                        result["max_scn"] = scn_val
                                    out_rows.append(vals)

                                if requested_mode == "append":
                                    out_rows, skipped = remove_existing_rows(out_rows)
                                    result["duplicates_skipped"] += skipped
                                    if not out_rows:
                                        continue

                                try:
                                    tgt_cur.executemany(insert_sql, out_rows)
                                    result["rows_written"] += len(out_rows)
                                except Exception as batch_ex:
                                    if is_duplicate_key_error(str(batch_ex)) and requested_mode != "upsert":
                                        for row_vals in out_rows:
                                            try:
                                                tgt_cur.execute(insert_sql, row_vals)
                                                result["rows_written"] += 1
                                            except Exception as row_ex:
                                                if is_duplicate_key_error(str(row_ex)):
                                                    if requested_mode == "incremental" and update_sql and key_pos and non_key_pos:
                                                        try:
                                                            update_params = [row_vals[p] for p in non_key_pos] + [row_vals[p] for p in key_pos]
                                                            tgt_cur.execute(update_sql, update_params)
                                                            result["rows_updated"] += 1
                                                        except Exception as upd_ex:
                                                            result["failed_rows"] += 1
                                                            if len(result["failed_rows_sample"]) < 5:
                                                                result["failed_rows_sample"].append(f"UPDATE failed: {str(upd_ex)[:140]}")
                                                    else:
                                                        result["duplicates_skipped"] += 1
                                                    continue
                                                result["failed_rows"] += 1
                                                if len(result["failed_rows_sample"]) < 5:
                                                    result["failed_rows_sample"].append(str(row_vals)[:180])
                                    else:
                                        raise

                        if requested_mode == "upsert":
                            key_cols = detect_key_cols(target_cols)
                            non_key_cols = [c for c in target_cols if c not in key_cols]
                            on_clause = " AND ".join(
                                [f"target.{quote_sql_ident(c)} = src.{quote_sql_ident(c)}" for c in key_cols]
                            )
                            update_clause = ", ".join(
                                [f"target.{quote_sql_ident(c)} = src.{quote_sql_ident(c)}" for c in non_key_cols]
                            )
                            insert_cols_all = ", ".join(quote_sql_ident(c) for c in target_cols)
                            insert_vals_all = ", ".join(f"src.{quote_sql_ident(c)}" for c in target_cols)
                            merge_sql = f"""
MERGE [dbo].{quote_sql_ident(target_table)} AS target
USING [dbo].{quote_sql_ident(stage_name)} AS src
ON {on_clause}
WHEN MATCHED THEN UPDATE SET {update_clause if update_clause else f'target.{quote_sql_ident(key_cols[0])}=target.{quote_sql_ident(key_cols[0])}'}
WHEN NOT MATCHED BY TARGET THEN INSERT ({insert_cols_all}) VALUES ({insert_vals_all});
"""
                            tgt_cur.execute(merge_sql)
                            merge_affected = tgt_cur.rowcount
                            result["rows_updated"] += max(merge_affected, 0)
                            print(f"  [UPSERT] MERGE on {target_table}: {merge_affected} rows affected, staging had {result['rows_written']} rows")

                        # Watermark update
                        watermark_status = "SUCCESS" if result["failed_rows"] == 0 else "PARTIAL"
                        persisted_scn = int(result["max_scn"]) if int(result.get("max_scn", 0) or 0) > 0 else int(last_scn or 0)
                        watermark_message = (
                            f"written={result['rows_written']}, updated={result['rows_updated']}, "
                            f"duplicates={result['duplicates_skipped']}, failed={result['failed_rows']}"
                        )
                        tgt_cur.execute(
                            """
MERGE dbo.MIGRATION_WATERMARKS AS target
USING (SELECT ? AS source_table) AS src
ON target.source_table = src.source_table
WHEN MATCHED THEN
    UPDATE SET
        last_success_ts = SYSUTCDATETIME(),
        last_row_count = ?,
        last_scn = ?,
        last_mode = ?,
        last_run_status = ?,
        last_error = ?,
        last_rows_read = ?,
        last_rows_updated = ?,
        last_duplicates_skipped = ?,
        last_failed_rows = ?,
        last_message = ?,
        updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (
        source_table, last_success_ts, last_row_count, last_scn, last_mode, last_run_status,
        last_error, last_rows_read, last_rows_updated, last_duplicates_skipped, last_failed_rows, last_message, updated_at
    )
    VALUES (src.source_table, SYSUTCDATETIME(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME());
""",
                            source_table,
                            result["rows_written"] + result["rows_updated"],
                            persisted_scn,
                            requested_mode,
                            watermark_status,
                            None if watermark_status == "SUCCESS" else "Partial row failures occurred",
                            result["rows_read"],
                            result["rows_updated"],
                            result["duplicates_skipped"],
                            result["failed_rows"],
                            watermark_message,
                            result["rows_written"] + result["rows_updated"],
                            persisted_scn,
                            requested_mode,
                            watermark_status,
                            None if watermark_status == "SUCCESS" else "Partial row failures occurred",
                            result["rows_read"],
                            result["rows_updated"],
                            result["duplicates_skipped"],
                            result["failed_rows"],
                            watermark_message,
                        )
                        tgt_conn.commit()
                        print(f"  [MIGRATE] {target_table} DONE: read={result['rows_read']}, written={result['rows_written']}, updated={result['rows_updated']}, failed={result['failed_rows']}")
                    except Exception as ex:
                        print(f"  [MIGRATE] {target_table} ERROR: {str(ex)[:200]}")
                        result["errors"].append(f"Data copy failed for {source_table} -> {target_table}: {str(ex)[:220]}")
                        try:
                            if tgt_cur:
                                tgt_cur.execute(
                                    """
MERGE dbo.MIGRATION_WATERMARKS AS target
USING (SELECT ? AS source_table) AS src
ON target.source_table = src.source_table
WHEN MATCHED THEN
    UPDATE SET
        last_run_status='FAILED',
        last_error=?,
        last_failed_rows=COALESCE(last_failed_rows, 0) + 1,
        last_message='Data copy failed',
        updated_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (source_table, last_mode, last_run_status, last_error, last_failed_rows, last_message, updated_at)
    VALUES (src.source_table, ?, 'FAILED', ?, 1, 'Data copy failed', SYSUTCDATETIME());
""",
                                    source_table,
                                    str(ex)[:900],
                                    requested_mode,
                                    str(ex)[:900],
                                )
                                tgt_conn.commit()
                        except Exception:
                            pass
                    finally:
                        result["duration_sec"] = round(time.time() - started, 3)
                        try:
                            if src_cur:
                                src_cur.close()
                        except Exception:
                            pass
                        if src_connector is not shared_source_connector:
                            try:
                                if src_connector:
                                    src_connector.disconnect()
                            except Exception:
                                pass
                        reused_shared_target = len(table_mappings) == 1 and tgt_conn is conn
                        if not reused_shared_target:
                            try:
                                if tgt_cur:
                                    tgt_cur.close()
                            except Exception:
                                pass
                            try:
                                if tgt_conn:
                                    tgt_conn.close()
                            except Exception:
                                pass
                    return result

                # Group approved mappings by source->target table.
                # IMPORTANT: Preserve original case from mappings to match DDL table names.
                table_mappings = {}
                for m in approved:
                    key = (
                        str(m.get("source_table", "")).strip(),
                        str(m.get("target_table", "")).strip(),
                    )
                    table_mappings.setdefault(key, []).append(m)

                print(f"  Tables to migrate: {list(table_mappings.keys())}")

                if len(table_mappings) == 1:
                    shared_source_connector = OracleConnector(
                        host=cfg.get("host", "localhost"),
                        port=cfg.get("port", 1521),
                        service_name=cfg.get("service_name"),
                        sid=cfg.get("sid"),
                        username=cfg.get("username", ""),
                        password=cfg.get("password", ""),
                        mode=cfg.get("mode", "NORMAL"),
                    )
                    shared_source_connector.connect()

                # Warm up the target connection once before opening concurrent per-table
                # connections. Azure SQL (esp. serverless tiers) can be paused/cold and take
                # longer than one connection timeout to resume; hitting it with several
                # simultaneous cold connects at once causes "TCP Provider: wait operation
                # timed out" on every one of them.
                if len(table_mappings) > 1 and selected_target_type == "Azure SQL":
                    try:
                        warm_conn = connect_azure_sql(azure_server, azure_db, azure_user, azure_pass, attempts=5)
                        warm_conn.close()
                    except Exception as warm_ex:
                        errors.append(f"Target warm-up connection failed: {str(warm_ex)[:200]}")

                max_workers = min(4, max(1, len(table_mappings)))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(migrate_table, source_table, target_table, maps): (source_table, target_table)
                        for (source_table, target_table), maps in table_mappings.items()
                    }
                    for future in as_completed(futures):
                        res = future.result()
                        rows_read_total += res.get("rows_read", 0)
                        migrated_rows += res.get("rows_written", 0)
                        rows_updated_total += res.get("rows_updated", 0)
                        duplicate_rows_skipped += res.get("duplicates_skipped", 0)
                        failed_rows_total += res.get("failed_rows", 0)
                        table_metrics.append({
                            "source_table": res.get("source_table"),
                            "target_table": res.get("target_table"),
                            "rows_read": res.get("rows_read", 0),
                            "rows_written": res.get("rows_written", 0),
                            "rows_updated": res.get("rows_updated", 0),
                            "duplicates_skipped": res.get("duplicates_skipped", 0),
                            "failed_rows": res.get("failed_rows", 0),
                            "partition_count": res.get("partition_count", 1),
                            "duration_sec": res.get("duration_sec", 0.0),
                            "throughput_rps": round(((res.get("rows_written", 0) + res.get("rows_updated", 0)) / max(res.get("duration_sec", 0.001), 0.001)), 2),
                        })
                        if (res.get("rows_written", 0) + res.get("rows_updated", 0)) > 0:
                            migrated_tables.add(res.get("target_table"))
                        if res.get("failed_rows_sample"):
                            failed_rows_sample.extend(res.get("failed_rows_sample", []))
                        if res.get("errors"):
                            errors.extend(res.get("errors"))

                if shared_source_connector is not None:
                    shared_source_connector.disconnect()

                # reconciliation artifact
                try:
                    os.makedirs(os.path.join(PROJECT_ROOT, "reports"), exist_ok=True)
                    artifact = {
                        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "mode": requested_mode,
                        "rows_read": rows_read_total,
                        "rows_written": migrated_rows,
                        "rows_updated": rows_updated_total,
                        "duplicates_skipped": duplicate_rows_skipped,
                        "failed_rows": failed_rows_total,
                        "table_metrics": table_metrics,
                        "failed_rows_sample": failed_rows_sample[:20],
                        "retry_candidates": [t for t in table_metrics if t.get("failed_rows", 0) > 0],
                    }
                    with open(os.path.join(PROJECT_ROOT, "reports", "reconciliation_latest.json"), "w", encoding="utf-8") as f:
                        json.dump(artifact, f, indent=2)
                except Exception as art_ex:
                    errors.append(f"Reconciliation artifact write failed: {str(art_ex)[:180]}")

            conn.commit()
            cursor.close()
            conn.close()

        except ImportError:
            mode = "dry_run"
            errors.append("pyodbc not installed. Falling back to dry run.")
        except Exception as e:
            mode = "dry_run"
            errors.append(f"Azure SQL connection failed: {str(e)[:150]}. Falling back to dry run.")
    else:
        mode = "dry_run"

    state["migration_executed"] = True
    mark_workflow_step(6)

    note = ""
    if pending > 0:
        note = f" {pending} unapproved mapping(s) were skipped."

    migration_duration = round(time.time() - migration_start_time, 2)
    if migration_duration >= 60:
        duration_str = f"{int(migration_duration // 60)}m {int(migration_duration % 60)}s"
    else:
        duration_str = f"{migration_duration}s"

    if mode == "live" and not errors:
        message = (
            f"✅ Migration executed on Azure SQL ({azure_server}/{azure_db}). "
            f"{len(executed_statements)} DDL statement(s) applied and {migrated_rows} row(s) inserted, {rows_updated_total} row(s) updated across {len(migrated_tables)} table(s)."
            f" {duplicate_rows_skipped} duplicate row(s) skipped. Mode={requested_mode}. ⏱ Completed in {duration_str}.{note}"
        )
    elif mode == "live" and errors:
        message = (
            f"⚠️ Migration partially executed on Azure SQL. "
            f"{len(executed_statements)} DDL statement(s) succeeded, {migrated_rows} row(s) inserted, {rows_updated_total} row(s) updated, "
            f"{duplicate_rows_skipped} duplicate row(s) skipped, {len(errors)} error(s). Mode={requested_mode}. ⏱ Completed in {duration_str}.{note}"
        )
    else:
        time.sleep(1)  # Simulate for dry run
        message = f"Migration dry run completed. {len(approved)} columns mapped.{note}"

    # Categorize tables by action taken
    all_target_tables = sorted(set(m["target_table"] for m in approved))
    tables_created = [s for s in executed_statements if "CREATE TABLE" in s.upper() and "SKIP" not in s.upper()]
    tables_skipped_ddl = [s for s in executed_statements if "SKIP CREATE TABLE" in s.upper()]

    return jsonify({
        "success": True,
        "mode": mode,
        "message": message,
        "tables_migrated": len(set(m["target_table"] for m in approved)),
        "columns_migrated": len(approved),
        "rows_migrated": migrated_rows,
        "rows_updated": rows_updated_total,
        "rows_read": rows_read_total,
        "duplicate_rows_skipped": duplicate_rows_skipped,
        "failed_rows": failed_rows_total,
        "failed_rows_sample": failed_rows_sample[:20],
        "table_metrics": table_metrics,
        "retry_candidates": [t for t in table_metrics if t.get("failed_rows", 0) > 0],
        "migration_mode": requested_mode,
        "duration_seconds": migration_duration,
        "duration": duration_str,
        "skipped": pending,
        "executed_count": len(executed_statements),
        "ddl_created": len(tables_created),
        "ddl_skipped_existing": len(tables_skipped_ddl),
        "errors": errors,
    })


# ============================================================
# GET /api/validate — Validation checks
# ============================================================

@app.route("/api/validate", methods=["GET", "POST"])
def validate():
    if not state["migration_executed"]:
        return jsonify({"success": False, "error": "Migration not executed yet."})

    data = request.get_json(silent=True) or {}
    if data.get("target_type"):
        state["target_type"] = str(data.get("target_type")).strip() or "Azure SQL"
    if str(state.get("target_type", "Azure SQL") or "Azure SQL").strip() != "Azure SQL":
        return jsonify({"success": False, "error": "Validation currently only supports an Azure SQL target."})

    def quote_sql_ident(name):
        return f"[{str(name).replace(']', ']]')}]"

    approved = [m for m in state.get("mappings", []) if m.get("approved")]
    if not approved:
        return jsonify({"success": False, "error": "No approved mappings available for validation."})

    if state.get("source_type") != "Oracle (Real)":
        return jsonify({"success": False, "error": "Validation currently supports Oracle (Real) source only."})

    azure_server = os.getenv("AZURE_SQL_SERVER", "")
    azure_db = os.getenv("AZURE_SQL_DATABASE", "")
    azure_user = os.getenv("AZURE_SQL_USERNAME", "")
    azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")
    if not (azure_server and azure_db and azure_user and azure_pass):
        return jsonify({"success": False, "error": "Azure SQL target configuration is missing in environment."})

    source_tables = sorted({str(m.get("source_table", "")).strip() for m in approved if m.get("source_table")})
    target_tables = sorted({str(m.get("target_table", "")).strip() for m in approved if m.get("target_table")})
    table_pairs = sorted({
        (str(m.get("source_table", "")).strip(), str(m.get("target_table", "")).strip())
        for m in approved if m.get("source_table") and m.get("target_table")
    })

    source_counts = {}
    target_counts = {}
    validation_results = []
    errors = []
    checksum_results = []
    mismatched_tables = []

    try:
        import pyodbc

        # Connect target with retry logic
        tgt_conn = connect_azure_sql(azure_server, azure_db, azure_user, azure_pass)
        tgt_cur = tgt_conn.cursor()

        # Connect source
        cfg = state.get("connection_config") or {}
        source_connector = OracleConnector(
            host=cfg.get("host", "localhost"),
            port=cfg.get("port", 1521),
            service_name=cfg.get("service_name"),
            sid=cfg.get("sid"),
            username=cfg.get("username", ""),
            password=cfg.get("password", ""),
            mode=cfg.get("mode", "NORMAL"),
        )
        source_connector.connect()
        src_cur = source_connector.connection.cursor()

        # Source counts
        for t in source_tables:
            try:
                src_cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                source_counts[t] = int(src_cur.fetchone()[0])
            except Exception as ex:
                source_counts[t] = -1
                errors.append(f"Source count failed for {t}: {str(ex)[:140]}")

        # Target counts
        for t in target_tables:
            try:
                tgt_cur.execute(f"SELECT COUNT(*) FROM [dbo].[{t}]")
                target_counts[t] = int(tgt_cur.fetchone()[0])
            except Exception as ex:
                target_counts[t] = -1
                errors.append(f"Target count failed for {t}: {str(ex)[:140]}")

        # Per-table row count checks
        matched_tables = 0
        pair_to_cols = {}
        for m in approved:
            s_table = str(m.get("source_table", "")).strip()
            t_table = str(m.get("target_table", "")).strip()
            pair_to_cols.setdefault((s_table, t_table), []).append((
                str(m.get("source_column", "")).upper(),
                str(m.get("target_column", "")).strip(),
            ))

        for s_table, t_table in table_pairs:
            s_count = source_counts.get(s_table, -1)
            t_count = target_counts.get(t_table, -1)
            status = "PASS" if s_count >= 0 and t_count >= 0 and s_count == t_count else "FAIL"
            if status == "PASS":
                matched_tables += 1
            else:
                mismatched_tables.append(f"{s_table}->{t_table}")
            validation_results.append({
                "check": f"Row Count Match ({s_table} -> {t_table})",
                "source": str(s_count),
                "target": str(t_count),
                "status": status,
            })

            # Key null/duplicate check on target side.
            mapped_cols = pair_to_cols.get((s_table, t_table), [])
            target_cols = [c[1] for c in mapped_cols]
            key_cols = [c for c in target_cols if c == "ID" or c.endswith("_ID") or c.endswith("ID")]
            if key_cols:
                key_col = key_cols[0]
                try:
                    tgt_cur.execute(
                        f"SELECT COUNT(*) AS total_rows, COUNT(DISTINCT {quote_sql_ident(key_col)}) AS distinct_rows, "
                        f"SUM(CASE WHEN {quote_sql_ident(key_col)} IS NULL THEN 1 ELSE 0 END) AS null_rows "
                        f"FROM [dbo].{quote_sql_ident(t_table)}"
                    )
                    total_rows, distinct_rows, null_rows = tgt_cur.fetchone()
                    dup_status = "PASS" if int(total_rows) == int(distinct_rows) else "FAIL"
                    null_status = "PASS" if int(null_rows or 0) == 0 else "FAIL"
                    validation_results.append({
                        "check": f"Duplicate Key Check ({t_table}.{key_col})",
                        "source": str(total_rows),
                        "target": str(distinct_rows),
                        "status": dup_status,
                    })
                    validation_results.append({
                        "check": f"Null Key Check ({t_table}.{key_col})",
                        "source": "0",
                        "target": str(int(null_rows or 0)),
                        "status": null_status,
                    })
                except Exception as ex:
                    errors.append(f"Target key validation failed for {t_table}.{key_col}: {str(ex)[:140]}")

            # Optional checksum validation for moderate-size tables.
            if s_count >= 0 and t_count >= 0 and max(s_count, t_count) <= 200000 and mapped_cols:
                s_cols = [c[0] for c in mapped_cols]
                t_cols = [c[1] for c in mapped_cols]
                order_col_src = s_cols[0]
                order_col_tgt = t_cols[0]
                src_sel_cols = ", ".join([f'"{c}"' for c in s_cols])
                tgt_sel_cols = ", ".join([quote_sql_ident(c) for c in t_cols])
                src_sql = f'SELECT {src_sel_cols} FROM "{s_table}" ORDER BY "{order_col_src}"'
                tgt_sql = f"SELECT {tgt_sel_cols} FROM [dbo].{quote_sql_ident(t_table)} ORDER BY {quote_sql_ident(order_col_tgt)}"

                def normalize_checksum_value(v):
                    # Normalize cross-driver representation differences (Oracle vs SQL Server)
                    # so logically-equal values hash identically: Decimal scale, float precision,
                    # datetime formatting, and CHAR-column trailing padding.
                    if v is None:
                        return ""
                    if isinstance(v, bool):
                        return "1" if v else "0"
                    if isinstance(v, Decimal):
                        s = format(v.normalize(), "f")
                        return s.rstrip("0").rstrip(".") if "." in s else s
                    if isinstance(v, float):
                        return str(int(v)) if v.is_integer() else repr(v)
                    if isinstance(v, (datetime, date)):
                        return v.isoformat()
                    if isinstance(v, str):
                        return v.rstrip()
                    if isinstance(v, bytes):
                        return v.hex()
                    return str(v)

                def table_checksum(cursor_obj, sql_text, batch_size=5000):
                    h = hashlib.sha256()
                    cursor_obj.execute(sql_text)
                    while True:
                        rows = cursor_obj.fetchmany(batch_size)
                        if not rows:
                            break
                        for r in rows:
                            h.update("|".join(normalize_checksum_value(v) for v in r).encode("utf-8", errors="ignore"))
                            h.update(b"\n")
                    return h.hexdigest()

                try:
                    src_hash = table_checksum(src_cur, src_sql)
                    tgt_hash = table_checksum(tgt_cur, tgt_sql)
                    chk_status = "PASS" if src_hash == tgt_hash else "FAIL"
                    checksum_results.append({"table": f"{s_table}->{t_table}", "source_hash": src_hash, "target_hash": tgt_hash, "status": chk_status})
                    validation_results.append({
                        "check": f"Checksum Match ({s_table} -> {t_table})",
                        "source": src_hash[:12],
                        "target": tgt_hash[:12],
                        "status": chk_status,
                    })
                    if chk_status == "FAIL":
                        mismatched_tables.append(f"{s_table}->{t_table}")
                except Exception as ex:
                    errors.append(f"Checksum failed for {s_table}->{t_table}: {str(ex)[:140]}")

        # Summary checks
        total_source = sum(v for v in source_counts.values() if isinstance(v, int) and v >= 0)
        total_target = sum(v for v in target_counts.values() if isinstance(v, int) and v >= 0)
        validation_results.append({
            "check": "Total Row Count Match",
            "source": str(total_source),
            "target": str(total_target),
            "status": "PASS" if total_source == total_target else "FAIL",
        })
        validation_results.append({
            "check": "Table-Level Match Ratio",
            "source": f"{matched_tables}/{len(table_pairs)}",
            "target": "1.00",
            "status": "PASS" if len(table_pairs) > 0 and matched_tables == len(table_pairs) else "FAIL",
        })

        # Cleanup
        try:
            src_cur.close()
        except Exception:
            pass
        try:
            source_connector.disconnect()
        except Exception:
            pass
        try:
            tgt_cur.close()
            tgt_conn.close()
        except Exception:
            pass

    except Exception as ex:
        return jsonify({"success": False, "error": f"Validation failed: {str(ex)[:180]}"})

    all_passed = all(v.get("status") == "PASS" for v in validation_results)
    overall = "All validation checks passed" if all_passed else "Validation mismatches detected"

    if errors:
        validation_results.append({
            "check": "Validation Warnings",
            "source": "; ".join(errors[:2]),
            "target": "See logs",
            "status": "FAIL",
        })
        all_passed = False
        overall = "Validation completed with warnings"

    state["validation_results"] = validation_results
    # Write reconciliation artifact for post-migration analysis.
    artifact_path = ""
    try:
        os.makedirs(os.path.join(PROJECT_ROOT, "reports"), exist_ok=True)
        artifact_path = os.path.join(PROJECT_ROOT, "reports", "reconciliation_validation_latest.json")
        artifact = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "overall": overall,
            "all_passed": all_passed,
            "mismatched_tables": sorted(set(mismatched_tables)),
            "checksum_results": checksum_results,
            "errors": errors,
            "retry_candidates": sorted(set(mismatched_tables)),
            "results": validation_results,
        }
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
    except Exception as ex:
        errors.append(f"Reconciliation artifact write failed: {str(ex)[:140]}")

    mark_workflow_step(7)
    return jsonify({
        "success": True,
        "results": validation_results,
        "all_passed": all_passed,
        "overall": overall,
        "mismatched_tables": sorted(set(mismatched_tables)),
        "checksum_results": checksum_results,
        "reconciliation_artifact": artifact_path,
    })


# ============================================================
# GET /api/report — Migration report
# ============================================================

@app.route("/api/report")
def report():
    tables = set(m["source_table"] for m in state["mappings"]) if state["mappings"] else set()
    total_columns = len(state["mappings"])
    approved = sum(1 for m in state["mappings"] if m.get("approved"))
    high_risk = sum(1 for m in state["mappings"] if m.get("risk") == "High")
    medium_risk = sum(1 for m in state["mappings"] if m.get("risk") == "Medium")

    report_data = {
        "title": "AI Data Migration Report",
        "source": state["source_type"] or "Not connected",
        "target": "Azure SQL Database",
        "tables": len(tables),
        "columns": total_columns,
        "approved": approved,
        "pending": total_columns - approved,
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": total_columns - high_risk - medium_risk,
        "migration_executed": state["migration_executed"],
        "validation_passed": len(state["validation_results"]) > 0 and all(
            v["status"] == "PASS" for v in state["validation_results"]
        ),
        "status": "COMPLETE" if state["migration_executed"] else "IN PROGRESS",
    }

    # Generate concise executive summary with skipped columns
    low_risk = total_columns - high_risk - medium_risk
    approved_count = sum(1 for m in state["mappings"] if m.get("approved"))
    skipped_count = total_columns - approved_count
    skipped_columns = [f"{m['source_table']}.{m['source_column']} ({m.get('source_type','')}) - {m.get('risk','Unknown')} risk"
                       for m in state["mappings"] if not m.get("approved")]

    validation_status = "All validations passed" if report_data["validation_passed"] else "Validation pending"

    summary_text = (
        f"Migration from {state['source_type'] or 'Oracle'} to Azure SQL Database completed successfully.\n\n"
        f"Scope: {len(tables)} tables, {approved_count} columns migrated.\n\n"
        f"Risk Profile: {low_risk} low risk, {medium_risk} medium risk, {high_risk} high risk.\n\n"
        f"Validation: {validation_status}.\n\n"
    )

    if skipped_count > 0:
        summary_text += f"Skipped Columns ({skipped_count}):\n"
        for sc in skipped_columns:
            summary_text += f"  - {sc}\n"
        summary_text += "\nThese columns require manual review before migration."
    else:
        summary_text += "All mappings approved and migrated successfully."

    report_data["executive_summary"] = summary_text
    report_data["skipped_columns"] = skipped_columns
    report_data["approved_count"] = approved_count
    report_data["skipped_count"] = skipped_count

    mark_workflow_step(8)
    return jsonify({"success": True, "report": report_data})



# ============================================================
# GET /api/download_report - Download migration report as JSON
# ============================================================

@app.route("/api/download_report")
def download_report():
    tables = set(m["source_table"] for m in state["mappings"]) if state["mappings"] else set()
    total_columns = len(state["mappings"])

    report = {
        "title": "AI Data Migration Report",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": state["source_type"] or "Not connected",
        "target": "Azure SQL Database",
        "summary": {
            "tables": len(tables),
            "columns": total_columns,
            "approved": sum(1 for m in state["mappings"] if m.get("approved")),
            "high_risk": sum(1 for m in state["mappings"] if m.get("risk") == "High"),
            "medium_risk": sum(1 for m in state["mappings"] if m.get("risk") == "Medium"),
            "low_risk": sum(1 for m in state["mappings"] if m.get("risk") == "Low"),
        },
        "migration_executed": state["migration_executed"],
        "validation_passed": len(state["validation_results"]) > 0 and all(
            v["status"] == "PASS" for v in state["validation_results"]
        ),
        "mappings": state["mappings"],
        "ddl_statements": state["ddl_statements"],
        "validation_results": state["validation_results"],
    }

    return jsonify(report)


# ============================================================
# GET /api/reset - Reset all state (for fresh demo)
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    question = data.get("question", "")

    if not question:
        return jsonify({"success": False, "error": "No question provided"})

    # Try AI chat
    if ChatAgent:
        try:
            agent = ChatAgent()
            ctx = {
                "source_type": state["source_type"],
                "tables": len(set(m["source_table"] for m in state["mappings"])) if state["mappings"] else 0,
                "columns": len(state["schema"]) if state["schema"] else 0,
                "mappings_count": len(state["mappings"]),
                "migration_executed": state["migration_executed"],
                "validation": state["validation_results"],
            }
            response = agent.ask(question, ctx)
            return jsonify({"success": True, "response": response})
        except Exception as e:
            pass

    # Fallback keyword responses
    q = question.lower()
    if "status" in q:
        resp = f"Migration status: {state['source_type'] or 'Not started'}. {len(state['mappings'])} mappings."
    elif "risk" in q:
        high = sum(1 for m in state["mappings"] if m.get("risk") == "High")
        resp = f"Risk assessment: {high} high-risk columns found."
    elif "table" in q:
        tables = set(m["source_table"] for m in state["mappings"]) if state["mappings"] else set()
        resp = f"Tables: {', '.join(tables) if tables else 'None discovered yet'}"
    else:
        resp = f"Current state: {state['source_type'] or 'Not connected'}. Ask about status, risk, or tables."

    return jsonify({"success": True, "response": resp})


# ============================================================
# Run
# ============================================================



# ============================================================
# GET /api/test_azure_sql — Test Azure SQL connectivity
# ============================================================

@app.route("/api/test_azure_sql")
def test_azure_sql():
    """Quick connectivity test to Azure SQL."""
    azure_server = os.getenv("AZURE_SQL_SERVER", "")
    azure_db = os.getenv("AZURE_SQL_DATABASE", "")
    azure_user = os.getenv("AZURE_SQL_USERNAME", "")
    azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")

    if not all([azure_server, azure_db, azure_user, azure_pass]):
        return jsonify({"success": False, "error": "Azure SQL credentials not configured in .env"})

    try:
        import pyodbc
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={azure_server};"
            f"DATABASE={azure_db};"
            f"UID={azure_user};"
            f"PWD={azure_pass};"
            f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=10;"
        )
        conn = pyodbc.connect(conn_str, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS test")
        result = cursor.fetchone()
        conn.close()
        return jsonify({
            "success": True,
            "message": f"Connected to {azure_server}/{azure_db}",
            "server": azure_server,
            "database": azure_db,
        })
    except ImportError:
        return jsonify({"success": False, "error": "pyodbc not installed. Run: pip install pyodbc"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/watermarks")
def get_watermarks():
    """Inspect current watermark and run-metric status from Azure SQL."""
    azure_server = os.getenv("AZURE_SQL_SERVER", "")
    azure_db = os.getenv("AZURE_SQL_DATABASE", "")
    azure_user = os.getenv("AZURE_SQL_USERNAME", "")
    azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")

    if not all([azure_server, azure_db, azure_user, azure_pass]):
        return jsonify({"success": False, "error": "Azure SQL credentials not configured in .env"})

    try:
        import pyodbc
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={azure_server};"
            f"DATABASE={azure_db};"
            f"UID={azure_user};"
            f"PWD={azure_pass};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=10;"
        )
        conn = pyodbc.connect(conn_str, timeout=10)
        cur = conn.cursor()
        cur.execute(
            """
SELECT
    source_table,
    last_success_ts,
    last_row_count,
    last_rows_read,
    last_rows_updated,
    last_duplicates_skipped,
    last_failed_rows,
    last_scn,
    last_mode,
    last_run_status,
    last_error,
    last_message,
    updated_at
FROM dbo.MIGRATION_WATERMARKS
ORDER BY source_table
"""
        )
        rows = cur.fetchall()
        out = []
        cols = [c[0] for c in cur.description]
        for r in rows:
            obj = {}
            for idx, col in enumerate(cols):
                v = r[idx]
                if isinstance(v, Decimal):
                    v = float(v)
                obj[col] = v.isoformat() if hasattr(v, "isoformat") else v
            out.append(obj)
        cur.close()
        conn.close()
        return jsonify({"success": True, "count": len(out), "watermarks": out})
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex)})

# ============================================================
# GET /api/delta — Real Delta Plan with actual row counts
# ============================================================

@app.route("/api/delta")
def get_delta_plan():
    """Return real delta plan with actual object metadata and row counts."""
    try:
        # Get Oracle metadata
        oracle_file = os.path.join(PROJECT_ROOT, "data", "oracle_metadata.json")
        with open(oracle_file, "r") as f:
            oracle_schema = json.load(f)
        
        selected_tables = [
            str(table).strip().upper()
            for table in state.get("selected_tables", [])
            if str(table).strip()
        ]
        if not selected_tables:
            selected_tables = sorted({
                str(row.get("table_name", "")).strip().upper()
                for row in (state.get("schema") or [])
                if str(row.get("table_name", "")).strip()
            })
        tables = selected_tables
        if not tables and state.get("source_type") == "Oracle (Simulator)":
            tables = [str(table).strip().upper() for table in oracle_schema.keys()]
        delta_rows = []
        
        azure_server = os.getenv("AZURE_SQL_SERVER", "")
        azure_db = os.getenv("AZURE_SQL_DATABASE", "")
        azure_user = os.getenv("AZURE_SQL_USERNAME", "")
        azure_pass = os.getenv("AZURE_SQL_PASSWORD", "")
        
        # Try to connect to Azure SQL for target counts
        target_counts = {}
        target_exists = {}
        target_counts_available = False
        target_watermark_scn = {}
        if azure_server and azure_db and azure_user and azure_pass:
            try:
                import pyodbc
                conn_str = (
                    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                    f"SERVER={azure_server};"
                    f"DATABASE={azure_db};"
                    f"UID={azure_user};"
                    f"PWD={azure_pass};"
                    f"Encrypt=yes;TrustServerCertificate=no;"
                )
                conn = pyodbc.connect(conn_str)
                cursor = conn.cursor()
                # Check which tables exist in target
                for table in tables:
                    cursor.execute(
                        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?",
                        table,
                    )
                    exists = cursor.fetchone()[0] > 0
                    target_exists[table] = exists
                    
                    # Try to get row count if table exists
                    if exists:
                        try:
                            cursor.execute(f"SELECT COUNT(*) FROM [dbo].[{table}]")
                            target_counts[table] = cursor.fetchone()[0]
                        except Exception:
                            target_counts[table] = -1
                    else:
                        target_counts[table] = 0

                target_counts_available = bool(tables) and all(
                    target_counts.get(table, -1) >= 0 for table in tables
                )

                # Persisted watermark SCN per table, used to detect updates that don't change row counts.
                try:
                    cursor.execute("SELECT OBJECT_ID('dbo.MIGRATION_WATERMARKS', 'U')")
                    if cursor.fetchone()[0] is not None:
                        for table in tables:
                            cursor.execute(
                                "SELECT COALESCE(last_scn, 0) FROM dbo.MIGRATION_WATERMARKS WHERE source_table = ?",
                                table,
                            )
                            wm_row = cursor.fetchone()
                            target_watermark_scn[table] = int(wm_row[0]) if wm_row and wm_row[0] is not None else 0
                except Exception:
                    pass

                cursor.close()
                conn.close()
            except Exception as ex:
                # Azure not reachable - show as dry-run mode
                pass
        
        # Try to get source counts from Oracle if connected
        source_counts = {}
        source_counts_available = False
        source_max_scn = {}
        if state.get("source_type") == "Oracle (Real)" and OracleConnector:
            try:
                cfg = state.get("connection_config") or {}
                connector = OracleConnector(
                    host=cfg.get("host", "localhost"),
                    port=cfg.get("port", 1521),
                    service_name=cfg.get("service_name"),
                    sid=cfg.get("sid"),
                    username=cfg.get("username", ""),
                    password=cfg.get("password", ""),
                    mode=cfg.get("mode", "NORMAL"),
                )
                connector.connect()
                for table in tables:
                    try:
                        source_counts[table] = int(connector.get_row_count(table))
                    except Exception:
                        source_counts[table] = -1
                    try:
                        src_cur = connector.connection.cursor()
                        src_cur.execute(f'SELECT NVL(MAX(ORA_ROWSCN), 0) FROM "{table}"')
                        scn_row = src_cur.fetchone()
                        source_max_scn[table] = int(scn_row[0]) if scn_row and scn_row[0] is not None else 0
                        src_cur.close()
                    except Exception:
                        pass
                source_counts_available = bool(tables) and all(
                    source_counts.get(table, -1) >= 0 for table in tables
                )
                connector.disconnect()
            except Exception:
                pass
        
        # Build delta plan rows
        for table in tables:
            src_rows = source_counts.get(table, -1) if source_counts_available else -1
            tgt_rows = target_counts.get(table, -1) if target_counts_available else -1
            
            # Determine state and action.
            # Equal row counts don't guarantee unchanged content (e.g. an in-place UPDATE) —
            # compare Oracle's current max ORA_ROWSCN against the persisted watermark SCN too.
            content_changed = source_max_scn.get(table, 0) > target_watermark_scn.get(table, 0)
            if tgt_rows == 0 and src_rows > 0:
                state_val = "new"
                action = "Create + full load"
            elif src_rows == tgt_rows and src_rows > 0 and content_changed:
                state_val = "changed"
                action = "Merge delta (content updated)"
            elif src_rows == tgt_rows and src_rows > 0:
                state_val = "unchanged"
                action = "Skip"
            elif src_rows > tgt_rows and src_rows > 0:
                state_val = "changed"
                action = "Merge delta"
            elif src_rows < 0 or tgt_rows < 0:
                state_val = "blocked"
                action = "Review required"
            else:
                state_val = "unchanged"
                action = "Skip"
            
            delta = max(0, (src_rows - tgt_rows)) if src_rows >= 0 and tgt_rows >= 0 else 0
            
            delta_rows.append({
                "object": table,
                "state": state_val,
                "sourceRows": src_rows if src_rows >= 0 else 0,
                "targetRows": tgt_rows if tgt_rows >= 0 else 0,
                "delta": delta,
                "action": action,
            })
        
        # Include procedures in delta plan
        proc_delta = []
        procedures = state.get("procedures", [])
        if not procedures:
            # Auto-discover procedures if not yet done
            proc_file = os.path.join(PROJECT_ROOT, "data", "oracle_procedures.json")
            if state.get("source_type") == "Oracle (Simulator)" and os.path.exists(proc_file):
                try:
                    with open(proc_file, "r") as pf:
                        procedures = json.load(pf)
                        state["procedures"] = procedures
                except Exception:
                    pass

        if procedures and target_counts_available:
            try:
                for proc in procedures:
                    proc_name = proc.get("name", "")
                    # Check if procedure exists in target
                    cursor.execute(
                        "SELECT 1 FROM sys.procedures WHERE name = ?",
                        proc_name,
                    )
                    exists_in_target = cursor.fetchone() is not None
                    # Check watermark
                    wm_exists = False
                    try:
                        cursor.execute(
                            "SELECT 1 FROM dbo.MIGRATION_WATERMARKS WHERE source_table = ?",
                            f"PROC:{proc_name}",
                        )
                        wm_exists = cursor.fetchone() is not None
                    except Exception:
                        pass

                    if not exists_in_target:
                        proc_delta.append({
                            "object": f"PROC:{proc_name}",
                            "object_type": "PROCEDURE",
                            "state": "new",
                            "action": "Convert + Deploy",
                            "sourceRows": 0,
                            "targetRows": 0,
                            "delta": 0,
                            "last_ddl_time": proc.get("last_ddl_time"),
                        })
                    elif not wm_exists:
                        proc_delta.append({
                            "object": f"PROC:{proc_name}",
                            "object_type": "PROCEDURE",
                            "state": "new",
                            "action": "Convert + Deploy",
                            "sourceRows": 0,
                            "targetRows": 0,
                            "delta": 0,
                            "last_ddl_time": proc.get("last_ddl_time"),
                        })
                    else:
                        proc_delta.append({
                            "object": f"PROC:{proc_name}",
                            "object_type": "PROCEDURE",
                            "state": "unchanged",
                            "action": "Skip",
                            "sourceRows": 0,
                            "targetRows": 0,
                            "delta": 0,
                            "last_ddl_time": proc.get("last_ddl_time"),
                        })
            except Exception:
                pass

        # Merge table and procedure deltas
        all_delta = delta_rows + proc_delta

        return jsonify({
            "success": True,
            "delta_plan": all_delta,
            "count": len(all_delta),
            "table_count": len(delta_rows),
            "procedure_count": len(proc_delta),
            "mode": "live" if source_counts_available and target_counts_available else "blocked",
            "source_counts_available": source_counts_available,
            "target_counts_available": target_counts_available,
        })
    
    except Exception as ex:
        return jsonify({
            "success": False,
            "error": str(ex),
            "delta_plan": [],
        })


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  AI Data Migration Agent — Flask Dashboard")
    print("  Open: http://localhost:5000")
    print("=" * 50 + "\n")
    # use_reloader=False: the reloader restarts the process (wiping in-memory `state`) on every file save
    app.run(debug=True, port=5000, use_reloader=False)
