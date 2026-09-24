import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import streamlit as st
from dotenv import load_dotenv
from connectors.sqlserver_connector import SQLServerConnector
from connectors.oracle_connector import OracleConnector
from config.config import Config

# Load environment variables
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


# ============================================================
# Helper: Clear downstream session state when source changes
# ============================================================

def clear_downstream_state():
    """Clear schema, analysis, and mapping data from previous source."""
    keys_to_clear = [
        "schema",
        "datatype_analysis",
        "datatype_results",
        "analysis_results",
        "mappings",
        "mapping_results",
        "ddl_results",
        "migration_results",
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]


st.title("Source Database Connection")

# Source selection
source_type = st.selectbox(
    "Select Source Database",
    ["SQL Server", "Oracle (Real)", "Oracle (Simulator)"]
)

st.divider()

if source_type == "SQL Server":

    server = st.text_input("SQL Server", "localhost")
    database = st.text_input("Database", "MigrationDemo")

    if st.button("Connect"):

        try:
            conn = SQLServerConnector(server, database).connect()

            st.success("✅ Connected to SQL Server Successfully")

            clear_downstream_state()
            st.session_state["server"] = server
            st.session_state["database"] = database
            st.session_state["source_type"] = "SQL Server"

            conn.close()

        except Exception as e:
            st.error(str(e))


elif source_type == "Oracle (Real)":

    st.info(
        "🔶 **Real Oracle Database Connection**\n\n"
        "Connect to an actual Oracle database instance.\n"
        "Credentials from `.env` will be used or configure manually."
    )

    st.subheader("Oracle Connection Details")

    # Get values from .env, fallback to Config
    default_host = os.getenv("ORACLE_HOST", Config.ORACLE_HOST)
    default_port = int(os.getenv("ORACLE_PORT", Config.ORACLE_PORT))
    default_service = os.getenv("ORACLE_SERVICE_NAME", Config.ORACLE_SERVICE_NAME)
    default_sid = os.getenv("ORACLE_SID", Config.ORACLE_SID)
    default_user = os.getenv("ORACLE_USERNAME", Config.ORACLE_USERNAME)
    default_pass = os.getenv("ORACLE_PASSWORD", Config.ORACLE_PASSWORD)

    col1, col2 = st.columns(2)

    with col1:
        host = st.text_input("Host", value=default_host)
        port = st.number_input("Port", value=default_port, min_value=1, max_value=65535)

    with col2:
        service_name = st.text_input("Service Name", value=default_service)
        sid = st.text_input("SID (optional)", value=default_sid)

    st.subheader("Credentials")

    col1, col2 = st.columns(2)

    with col1:
        username = st.text_input("Username", value=default_user)

    with col2:
        password = st.text_input("Password", type="password", value=default_pass)

    # Auto-detect connection mode: only SYS uses SYSDBA
    connection_mode = st.selectbox(
        "Connection Mode",
        ["NORMAL", "SYSDBA"],
        index=0 if username.lower() != "sys" else 1,
        help="Use NORMAL for regular users (e.g. poc_migration). Use SYSDBA only for sys."
    )

    if st.button("Connect to Real Oracle"):

        try:
            with st.spinner("Connecting to Oracle database..."):

                connector = OracleConnector(
                    host=host,
                    port=port,
                    service_name=service_name if service_name else None,
                    sid=sid if sid else None,
                    username=username,
                    password=password,
                    mode=connection_mode,
                    thick_mode=Config.ORACLE_THICK_MODE,
                    lib_dir=Config.ORACLE_CLIENT_LIB_DIR if Config.ORACLE_CLIENT_LIB_DIR else None
                )

                connection = connector.connect()

                # Discover tables
                tables = connector.discover_tables()

                st.success(f"✅ Connected to Oracle Successfully!")
                st.write(f"📊 **Database:** {service_name or sid}")
                st.write(f"👤 **Schema:** {username}")
                st.write(f"📋 **Tables found:** {len(tables)}")

                if tables:
                    st.write("**Tables:**")
                    for t in tables:
                        st.write(f"  - `{t}`")

                # Store connection parameters (not the connector object - it's not pickleable)
                clear_downstream_state()
                st.session_state["source_type"] = "Oracle (Real)"
                st.session_state["oracle_host"] = host
                st.session_state["oracle_port"] = port
                st.session_state["oracle_service"] = service_name if service_name else None
                st.session_state["oracle_sid"] = sid if sid else None
                st.session_state["oracle_user"] = username
                st.session_state["oracle_pass"] = password
                st.session_state["oracle_mode"] = connection_mode
                st.session_state["oracle_tables"] = tables
                st.session_state["oracle_connection_service"] = service_name or sid

                st.info("✅ Ready for Schema Discovery (Step 2)")

                # Close the connection - it will be recreated when needed
                connector.disconnect()


        except Exception as e:
            st.error(f"❌ Connection failed: {str(e)}")
            st.warning("Make sure Oracle database is running and credentials are correct.")


elif source_type == "Oracle (Simulator)":

    st.info(
        "🔶 Oracle Simulator Mode\n\n"
        "Using simulated Oracle metadata from `data/oracle_metadata.json`. "
        "This represents a realistic Oracle schema for POC purposes."
    )

    oracle_file = os.path.join(PROJECT_ROOT, "data", "oracle_metadata.json")

    if st.button("Load Oracle Schema"):

        try:
            with open(oracle_file, "r") as f:
                oracle_schema = json.load(f)

            tables = list(oracle_schema.keys())
            total_columns = sum(len(cols) for cols in oracle_schema.values())

            st.success("✅ Oracle Simulator Connected")

            st.write(f"**Tables found:** {len(tables)}")
            st.write(f"**Total columns:** {total_columns}")

            for table in tables:
                st.write(f"- `{table}` ({len(oracle_schema[table])} columns)")

            clear_downstream_state()
            st.session_state["source_type"] = "Oracle (Simulator)"
            st.session_state["oracle_schema"] = oracle_schema

        except Exception as e:
            st.error(f"Failed to load Oracle metadata: {e}")


# Show connection status
st.divider()

if "source_type" in st.session_state:
    st.subheader("Connection Status")

    if st.session_state["source_type"] == "SQL Server":
        st.write(f"🟢 **Source:** SQL Server")
        st.write(f"**Server:** {st.session_state.get('server', '')}")
        st.write(f"**Database:** {st.session_state.get('database', '')}")

    elif st.session_state["source_type"] == "Oracle (Real)":
        st.write(f"🟠 **Source:** Oracle (Real)")
        st.write(f"**Host:** {st.session_state.get('oracle_host', '')}")
        st.write(f"**Schema:** {st.session_state.get('oracle_user', '')}")
        st.write(f"**Service/SID:** {st.session_state.get('oracle_connection_service', '')}")
        st.write(f"**Mode:** {st.session_state.get('oracle_mode', 'NORMAL')}")
        st.write(f"**Tables:** {len(st.session_state.get('oracle_tables', []))}")

    elif st.session_state["source_type"] == "Oracle (Simulator)":
        st.write(f"🟠 **Source:** Oracle (Simulator)")
        st.write(f"**Mode:** Simulated metadata")
        st.write(f"**Tables:** {len(st.session_state.get('oracle_schema', {}))}")
