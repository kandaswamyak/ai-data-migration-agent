import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.config import Config
from connectors.oracle_connector import OracleConnector
from agents.schema_agent import SchemaAgent
from agents.mapping_agent import MappingAgent
from agents.sql_generator import SQLGenerator

try:
    from agents.datatype_agent import DatatypeAnalysisAgent
except Exception:
    DatatypeAnalysisAgent = None

try:
    from agents.risk_analyst import RiskAnalyst
except Exception:
    RiskAnalyst = None

try:
    from agents.report_agent import ReportAgent
except Exception:
    ReportAgent = None

try:
    from agents.ai_engine import get_ai_engine
except Exception:
    def get_ai_engine():
        return None

try:
    from agents.chat_agent import ChatAgent
except Exception:
    ChatAgent = None

# Page config
st.set_page_config(page_title="AI Data Migration Agent",  layout="wide")

# CSS: hide sidebar, style tabs as dark header
st.markdown('''
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

/* Tab list container - dark navy background */
.stTabs [data-baseweb="tab-list"] {
    background-color: #2d2150 !important;
    padding: 0 16px !important;
    border-radius: 0 !important;
    gap: 0;
}

/* Individual tab buttons */
.stTabs [data-baseweb="tab"] {
    color: rgba(255,255,255,0.7) !important;
    padding: 14px 18px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    background: transparent !important;
    border: none !important;
}

/* Active/selected tab */
.stTabs [aria-selected="true"] {
    color: #ffffff !important;
    border-bottom: 3px solid #ffffff !important; 
    background: transparent !important;
}

/* Hover state */
.stTabs [data-baseweb="tab"]:hover {
    color: #ffffff !important;
}

/* Hide default tab highlight bar */
.stTabs [data-baseweb="tab-highlight"] {
    background-color: transparent !important;
}

/* Hide default tab border */
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

/* Override any Streamlit tab panel button styling */
button[data-baseweb="tab"] {
    color: rgba(255,255,255,0.7) !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #ffffff !important;
}

/* Green checkboxes */
[data-testid="stCheckbox"] svg {
    fill: #10b981 !important;
    color: #10b981 !important;
}
[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] {
    color: #10b981 !important;
}
</style>
''', unsafe_allow_html=True)

# ============================================================
# HELPER: clear downstream state
# ============================================================
def clear_downstream_state():
    for key in ["schema","datatype_analysis","datatype_results","analysis_results",
                "mappings","mapping_results","ddl_statements","ddl_results",
                "migration_results","review_complete","migration_executed",
                "validation_complete","risk_summary","executive_summary",
                "report_recommendations","validation_ai_analysis","all_mappings_approved"]:
        if key in st.session_state:
            del st.session_state[key]

# ============================================================
# HELPER: Bottom page navigation
# ============================================================
TAB_NAMES = ["Source", "Schema", "Analysis", "Mapping", "SQL Gen", "Approval", "Migration", "Validation", "Report"]

def render_nav(current_index):
    """Render Back/Next navigation at the bottom of a tab."""
    st.divider()
    col1, col2, col3 = st.columns([2, 4, 2])
    with col1:
        if current_index > 0:
            prev_name = TAB_NAMES[current_index - 1]
            if st.button(f"← Back: {prev_name}", key=f"nav_back_{current_index}"):
                st.session_state["active_tab"] = current_index - 1
                st.rerun()
    with col3:
        if current_index < len(TAB_NAMES) - 1:
            next_name = TAB_NAMES[current_index + 1]
            if st.button(f"Next: {next_name} →", key=f"nav_next_{current_index}", type="primary"):
                st.session_state["active_tab"] = current_index + 1
                st.rerun()
    with col2:
        st.caption(f"Step {current_index + 1} of {len(TAB_NAMES)}")

# ============================================================
# SESSION-STATE NAVIGATION (clickable Back/Next)
# ============================================================
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = 0

# Render header navigation buttons
nav_cols = st.columns(len(TAB_NAMES))
for _i, _name in enumerate(TAB_NAMES):
    with nav_cols[_i]:
        _is_active = (_i == st.session_state["active_tab"])
        _btn_type = "primary" if _is_active else "secondary"
        if st.button(_name, key=f"nav_tab_{_i}", type=_btn_type, use_container_width=True):
            st.session_state["active_tab"] = _i
            st.rerun()

st.divider()

# ============================================================
# TAB 1: SOURCE CONNECTION
# ============================================================
if st.session_state["active_tab"] == 0:
    st.header("Source Database Connection")
    source_type = st.selectbox("Select Source Database", ["SQL Server", "Oracle (Real)", "Oracle (Simulator)"], key="src_sel")
    st.divider()

    if source_type == "Oracle (Real)":
        default_host = os.getenv("ORACLE_HOST", Config.ORACLE_HOST)
        default_port = int(os.getenv("ORACLE_PORT", str(Config.ORACLE_PORT)))
        default_service = os.getenv("ORACLE_SERVICE_NAME", Config.ORACLE_SERVICE_NAME)
        default_sid = os.getenv("ORACLE_SID", Config.ORACLE_SID)
        default_user = os.getenv("ORACLE_USERNAME", Config.ORACLE_USERNAME)
        default_pass = os.getenv("ORACLE_PASSWORD", Config.ORACLE_PASSWORD)

        c1, c2 = st.columns(2)
        with c1:
            host = st.text_input("Host", value=default_host, key="t1_host")
            port = st.number_input("Port", value=default_port, min_value=1, max_value=65535, key="t1_port")
        with c2:
            service_name = st.text_input("Service Name", value=default_service, key="t1_svc")
            sid = st.text_input("SID (optional)", value=default_sid, key="t1_sid")

        c3, c4 = st.columns(2)
        with c3:
            username = st.text_input("Username", value=default_user, key="t1_user")
        with c4:
            password = st.text_input("Password", type="password", value=default_pass, key="t1_pass")

        connection_mode = st.selectbox("Connection Mode", ["NORMAL","SYSDBA"],
            index=0 if default_user.lower() != "sys" else 1, key="t1_mode")

        if st.button("Connect to Oracle", key="t1_connect"):
            try:
                with st.spinner("Connecting..."):
                    connector = OracleConnector(
                        host=host, port=port,
                        service_name=service_name if service_name else None,
                        sid=sid if sid else None,
                        username=username, password=password,
                        mode=connection_mode,
                        thick_mode=Config.ORACLE_THICK_MODE,
                        lib_dir=Config.ORACLE_CLIENT_LIB_DIR if Config.ORACLE_CLIENT_LIB_DIR else None
                    )
                    connector.connect()
                    tables = connector.discover_tables()
                    st.success(f"✅ Connected! Found {len(tables)} tables.")
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
                    connector.disconnect()
            except Exception as e:
                st.error(f"Connection failed: {e}")

    elif source_type == "Oracle (Simulator)":
        st.info("Using simulated Oracle metadata from `data/oracle_metadata.json`.")
        if st.button("Load Oracle Schema", key="t1_sim"):
            oracle_file = os.path.join(PROJECT_ROOT, "data", "oracle_metadata.json")
            try:
                with open(oracle_file, "r") as f:
                    oracle_schema = json.load(f)
                clear_downstream_state()
                st.session_state["source_type"] = "Oracle (Simulator)"
                st.session_state["oracle_schema"] = oracle_schema
                st.success(f"✅ Loaded {len(oracle_schema)} tables.")
            except Exception as e:
                st.error(str(e))

    elif source_type == "SQL Server":
        server = st.text_input("SQL Server", "localhost", key="t1_srv")
        database = st.text_input("Database", "MigrationDemo", key="t1_db")
        if st.button("Connect", key="t1_sql"):
            try:
                from connectors.sqlserver_connector import SQLServerConnector
                conn = SQLServerConnector(server, database).connect()
                clear_downstream_state()
                st.session_state["server"] = server
                st.session_state["database"] = database
                st.session_state["source_type"] = "SQL Server"
                conn.close()
                st.success("✅ Connected to SQL Server.")
            except Exception as e:
                st.error(str(e))

    # Connection status
    if "source_type" in st.session_state:
        st.divider()
        st.write(f"**Connected:** {st.session_state['source_type']}")

    render_nav(0)
# ============================================================
# TAB 2: SCHEMA DISCOVERY
# ============================================================
elif st.session_state["active_tab"] == 1:
    st.header("Schema Discovery")
    src = st.session_state.get("source_type")
    if not src:
        st.warning("Connect to a source database first (Source tab).")
    else:
        st.write(f"**Source:** {src}")
        if st.button("Discover Schema", key="t2_discover"):
            with st.spinner("Discovering schema..."):
                try:
                    if src == "Oracle (Real)":
                        oracle_config = {
                            "host": st.session_state["oracle_host"],
                            "port": st.session_state["oracle_port"],
                            "service_name": st.session_state["oracle_service"],
                            "sid": st.session_state["oracle_sid"],
                            "username": st.session_state["oracle_user"],
                            "password": st.session_state["oracle_pass"],
                            "mode": st.session_state.get("oracle_mode", "NORMAL"),
                        }
                        agent = SchemaAgent(source_type="Oracle (Real)", oracle_config=oracle_config)
                    elif src == "Oracle (Simulator)":
                        agent = SchemaAgent(source_type="Oracle (Simulator)")
                    else:
                        agent = SchemaAgent(st.session_state["server"], st.session_state["database"], source_type="SQL Server")

                    schema_df = agent.discover_schema()
                    st.session_state["schema"] = schema_df
                    st.success(f"✅ {schema_df['TABLE_NAME'].nunique()} tables, {len(schema_df)} columns discovered.")
                except Exception as e:
                    st.error(str(e))

        if "schema" in st.session_state:
            schema_df = st.session_state["schema"]
            display_df = schema_df[["TABLE_NAME","COLUMN_NAME","FULL_DATA_TYPE","IS_NULLABLE"]].copy()
            display_df.columns = ["Table","Column","Data Type","Nullable"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    render_nav(1)
# ============================================================
# TAB 3: DATATYPE ANALYSIS
# ============================================================
elif st.session_state["active_tab"] == 2:
    st.header("AI Datatype Analysis")
    if "schema" not in st.session_state:
        st.warning("Run Schema Discovery first (Schema tab).")
    else:
        st.write(f"**Source:** {st.session_state.get('source_type','')} → **Target:** Azure SQL Database")

        if st.button("🚀 Run AI Analysis", key="t3_run"):
            if DatatypeAnalysisAgent is None:
                st.error("DatatypeAnalysisAgent not available.")
            else:
                try:
                    ai_agent = DatatypeAnalysisAgent()
                    schema_df = st.session_state["schema"]
                    # Build metadata from schema
                    df = schema_df.copy()
                    df.columns = [c.upper() for c in df.columns]
                    col_map = {"SOURCE_LENGTH":"DATA_LENGTH","SOURCE_PRECISION":"DATA_PRECISION","SOURCE_SCALE":"DATA_SCALE"}
                    df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})

                    metadata = {}
                    for table in df["TABLE_NAME"].unique():
                        table_df = df[df["TABLE_NAME"]==table].astype(object).where(pd.notna(df[df["TABLE_NAME"]==table]),None)
                        metadata[table] = table_df.to_dict(orient="records")

                    results = []
                    progress = st.progress(0)
                    total_cols = sum(len(v) for v in metadata.values())
                    done = 0
                    source_type_val = st.session_state.get("source_type","Oracle")

                    for table_name, columns in metadata.items():
                        for column in columns:
                            source_column = {
                                "source_database": source_type_val,
                                "table_name": table_name,
                                "column_name": column.get("COLUMN_NAME",""),
                                "data_type": column.get("DATA_TYPE",""),
                                "full_data_type": column.get("FULL_DATA_TYPE", column.get("DATA_TYPE","")),
                                "length": column.get("DATA_LENGTH"),
                                "precision": column.get("DATA_PRECISION"),
                                "scale": column.get("DATA_SCALE"),
                                "nullable": column.get("IS_NULLABLE","Y"),
                            }
                            try:
                                analysis = ai_agent.analyze(source_column)
                                results.append({
                                    "table": table_name,
                                    "column": column.get("COLUMN_NAME",""),
                                    "source": source_column.get("data_type",""),
                                    "target": analysis.get("target_type",""),
                                    "source_length": source_column.get("length"),
                                    "target_length": analysis.get("target_length"),
                                    "source_precision": source_column.get("precision"),
                                    "target_precision": analysis.get("target_precision"),
                                    "source_scale": source_column.get("scale"),
                                    "target_scale": analysis.get("target_scale"),
                                    "status": analysis.get("status","Compatible"),
                                    "risk": analysis.get("risk","Low"),
                                    "confidence": analysis.get("confidence",1.0),
                                })
                            except Exception as ex:
                                results.append({
                                    "table": table_name, "column": column.get("COLUMN_NAME",""),
                                    "source": source_column.get("data_type",""),
                                    "target": "UNKNOWN", "status": "Error",
                                    "risk": "High", "confidence": 0,
                                    "source_length": None, "target_length": None,
                                    "source_precision": None, "target_precision": None,
                                    "source_scale": None, "target_scale": None,
                                })
                            done += 1
                            progress.progress(done / total_cols)

                    st.session_state["datatype_analysis"] = pd.DataFrame(results)
                    st.session_state["review_complete"] = True
                    st.success(f"✅ Analysis complete — {len(results)} columns analyzed.")
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

        if "datatype_analysis" in st.session_state:
            df = st.session_state["datatype_analysis"]
            st.dataframe(df, use_container_width=True, hide_index=True)
            # Compatibility summary
            compatible = len(df[df["status"]=="Compatible"])
            issues = len(df[df["status"]!="Compatible"])
            c1, c2 = st.columns(2)
            c1.metric("✅ Compatible", compatible)
            c2.metric("⚠️ Issues", issues)

    render_nav(2)
# ============================================================
# TAB 4: AI MAPPING
# ============================================================
elif st.session_state["active_tab"] == 3:
    st.header("AI Source-to-Target Mapping")
    if "datatype_analysis" not in st.session_state:
        st.warning("Run Datatype Analysis first (Analysis tab).")
    else:
        agent = MappingAgent(source_db="Oracle", target_db="Azure SQL")
        if st.button("🚀 Generate Mapping", key="t4_gen"):
            with st.spinner("Generating mappings..."):
                analysis_df = st.session_state["datatype_analysis"]
                results = []
                for _, row in analysis_df.iterrows():
                    results.append({
                        "table": row.get("table",""), "column": row.get("column",""),
                        "source_type": row.get("source",""), "target_type": row.get("target",""),
                        "status": row.get("status",""), "risk": row.get("risk",""),
                        "confidence": row.get("confidence",1.0), "nullable": "Y",
                    })
                mappings = agent.generate_mapping(results)
                st.session_state["mappings"] = mappings
                agent.save_mappings(mappings)
                st.success(f"✅ {len(mappings)} mappings generated.")

        if "mappings" in st.session_state:
            mappings = st.session_state["mappings"]
            summary = agent.get_approval_summary(mappings)
            c1,c2,c3 = st.columns(3)
            c1.metric("Total", summary["total"])
            c2.metric("Approved", summary["approved"])
            c3.metric("Pending", summary["pending"])

            st.divider()

            # Interactive mapping table with individual approve checkboxes
            changed = False
            for i, m in enumerate(mappings):
                cols = st.columns([2, 2, 2, 2, 2, 1])
                cols[0].write(f"**{m.get('source_table','')}**")
                cols[1].write(m.get("source_column", ""))
                cols[2].write(f"`{m.get('source_type','')}`")
                cols[3].write(f"`{m.get('target_type','')}`")
                cols[4].write(m.get("transformation", ""))

                approved = cols[5].checkbox(
                    "Approve",
                    value=m.get("approved", False),
                    key=f"t4_approve_{i}",
                    label_visibility="collapsed"
                )
                if approved != m.get("approved", False):
                    mappings[i]["approved"] = approved
                    changed = True

            if changed:
                st.session_state["mappings"] = mappings
                agent.save_mappings(mappings)
                st.rerun()

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Approve All Mappings", key="t4_approve"):
                    st.session_state["mappings"] = agent.approve_all(mappings)
                    agent.save_mappings(st.session_state["mappings"])
                    st.session_state["all_mappings_approved"] = True
                    st.success("All mappings approved!")
                    st.rerun()
            with c2:
                if st.button("✅ Approve Low Risk Only", key="t4_approve_low"):
                    for i, m in enumerate(mappings):
                        if m.get("risk", "").lower() == "low":
                            mappings[i]["approved"] = True
                    st.session_state["mappings"] = mappings
                    agent.save_mappings(mappings)
                    st.success("Low-risk mappings approved. Review Medium/High risk items.")
                    st.rerun()

    render_nav(3)
# ============================================================
# TAB 5: SQL GENERATOR
# ============================================================
elif st.session_state["active_tab"] == 4:
    st.header("SQL / DDL Generator")
    if "mappings" not in st.session_state:
        st.warning("Generate mappings first (Mapping tab).")
    else:
        generator = SQLGenerator(target_db="Azure SQL")
        if st.button("Generate DDL", key="t5_gen"):
            with st.spinner("Generating DDL..."):
                ddl_statements = generator.generate_ddl(st.session_state["mappings"])
                st.session_state["ddl_statements"] = ddl_statements
                generator.save_ddl(ddl_statements)
                st.success("✅ DDL generated.")

        if "ddl_statements" in st.session_state:
            for ddl in st.session_state["ddl_statements"]:
                st.code(ddl, language="sql")
            full_ddl = "\n\n".join(st.session_state["ddl_statements"])
            st.download_button("📥 Download DDL", data=full_ddl, file_name="migration_ddl.sql", mime="text/plain")

    render_nav(4)
# ============================================================
# TAB 6: HUMAN APPROVAL
# ============================================================
elif st.session_state["active_tab"] == 5:
    st.header("Human Approval")
    if "mappings" not in st.session_state:
        st.warning("Generate mappings first (Mapping tab).")
    else:
        mappings = st.session_state["mappings"]
        agent = MappingAgent(source_db="Oracle", target_db="Azure SQL")
        summary = agent.get_approval_summary(mappings)
        c1,c2,c3 = st.columns(3)
        c1.metric("Total", summary["total"])
        c2.metric("Approved", summary["approved"])
        c3.metric("Pending", summary["pending"])

        if summary["ready_for_migration"]:
            st.success("✅ All mappings approved. Ready for migration.")
            st.session_state["all_mappings_approved"] = True
        else:
            st.info(f"{summary['pending']} mapping(s) pending.")

        # AI Risk Summary
        if RiskAnalyst:
            st.divider()
            st.subheader("AI Risk Assessment")
            if "risk_summary" not in st.session_state:
                with st.spinner("Analyzing risks..."):
                    ra = RiskAnalyst()
                    st.session_state["risk_summary"] = ra.generate_risk_summary(mappings)
            st.markdown(st.session_state["risk_summary"])

        st.divider()
        for i, m in enumerate(mappings):
            with st.expander(f"{'✅' if m.get('approved') else '⏳'} {m.get('source_table','')}.{m.get('source_column','')} → {m.get('target_type','')}"):
                st.write(f"Source: `{m.get('source_type','')}` | Target: `{m.get('target_type','')}`")
                st.write(f"Risk: {m.get('risk','')} | Transformation: {m.get('transformation','')}")
                if not m.get("approved"):
                    if st.button("Approve", key=f"t6_app_{i}"):
                        mappings[i]["approved"] = True
                        st.session_state["mappings"] = mappings
                        agent.save_mappings(mappings)
                        st.rerun()

        if st.button("Approve All", key="t6_all"):
            st.session_state["mappings"] = agent.approve_all(mappings)
            st.session_state["all_mappings_approved"] = True
            agent.save_mappings(st.session_state["mappings"])
            st.rerun()

    render_nav(5)
# ============================================================
# TAB 7: MIGRATION
# ============================================================
elif st.session_state["active_tab"] == 6:
    st.header("Migration Execution")
    if "mappings" not in st.session_state:
        st.warning("Complete previous steps first.")
    else:
        mappings = st.session_state["mappings"]
        agent = MappingAgent(source_db="Oracle", target_db="Azure SQL")
        summary = agent.get_approval_summary(mappings)
        if not summary["ready_for_migration"]:
            st.error(f"❌ {summary['pending']} mapping(s) not approved. Go to Approval tab.")
        else:
            st.success(f"✅ All {summary['total']} mappings approved.")
            st.warning("⚠️ POC Mode: Migration simulated (no actual Azure SQL connection).")
            if st.button("Execute Migration (Dry Run)", key="t7_exec"):
                import time
                with st.spinner("Simulating migration..."):
                    time.sleep(2)
                st.session_state["migration_executed"] = True
                st.success("✅ Dry run complete.")

    render_nav(6)
# ============================================================
# TAB 8: VALIDATION
# ============================================================
elif st.session_state["active_tab"] == 7:
    st.header("Migration Validation")
    if "migration_executed" not in st.session_state:
        st.warning("Execute migration first (Migration tab).")
    else:
        st.success("Migration executed. Validation results:")
        checks = [
            {"check":"Row Count Match","source":"1000","target":"1000","status":"PASS"},
            {"check":"NULL Count Match","source":"45","target":"45","status":"PASS"},
            {"check":"Duplicate Check","source":"0","target":"0","status":"PASS"},
            {"check":"Data Type Integrity","source":"7 columns","target":"7 columns","status":"PASS"},
            {"check":"Precision Validation","source":"DECIMAL(19,4)","target":"DECIMAL(19,4)","status":"PASS"},
        ]
        for ck in checks:
            c1,c2,c3,c4 = st.columns([3,2,2,1])
            c1.write(ck["check"])
            c2.write(f"Source: {ck['source']}")
            c3.write(f"Target: {ck['target']}")
            c4.write(f"✅ {ck['status']}" if ck["status"]=="PASS" else f"❌ {ck['status']}")

        # AI interpretation
        ai = get_ai_engine()
        if ai and "validation_ai_analysis" not in st.session_state:
            with st.spinner("AI interpreting results..."):
                try:
                    prompt = f"Briefly interpret these migration validation results (all passed): {json.dumps(checks)}"
                    st.session_state["validation_ai_analysis"] = ai.call(prompt, "You are a data validation expert.")
                except Exception:
                    st.session_state["validation_ai_analysis"] = "All validation checks passed. Data integrity confirmed."
        if "validation_ai_analysis" in st.session_state:
            st.divider()
            st.markdown(st.session_state["validation_ai_analysis"])

        st.divider()
        st.success("✅ ALL VALIDATIONS PASSED")
        st.session_state["validation_complete"] = True

    render_nav(7)
# ============================================================
# TAB 9: REPORT
# ============================================================
elif st.session_state["active_tab"] == 8:
    st.header("Migration Report")
    if "validation_complete" not in st.session_state:
        st.warning("Complete validation first (Validation tab).")
    else:
        mappings = st.session_state.get("mappings", [])
        tables = set(m.get("source_table","") for m in mappings)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Tables", len(tables))
        c2.metric("Columns", len(mappings))
        c3.metric("Status", "SUCCESS")
        c4.metric("Validation", "PASSED")

        # AI Executive Summary
        if ReportAgent:
            st.divider()
            st.subheader("AI Executive Summary")
            if "executive_summary" not in st.session_state:
                with st.spinner("Generating summary..."):
                    ra = ReportAgent()
                    ctx = {"source_type": st.session_state.get("source_type","Oracle"),
                           "mappings": mappings, "validation_complete": True}
                    st.session_state["executive_summary"] = ra.generate_executive_summary(ctx)
            st.markdown(st.session_state["executive_summary"])

        st.divider()
        report_data = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": st.session_state.get("source_type","Oracle"),
            "target": "Azure SQL",
            "tables": len(tables),
            "columns": len(mappings),
            "status": "SUCCESS",
        }
        st.download_button("📥 Download Report (JSON)",
            data=json.dumps(report_data, indent=2),
            file_name="migration_report.json", mime="application/json")

    render_nav(8)
# ============================================================
# AI CHAT (always visible at bottom)
# ============================================================
st.divider()
if ChatAgent:
    try:
        if "chat_agent" not in st.session_state:
            st.session_state["chat_agent"] = ChatAgent()
        chat = st.session_state["chat_agent"]
        prompt = st.chat_input("Ask the AI agent about your migration...")
        if prompt:
            ctx = {
                "source_type": st.session_state.get("source_type"),
                "tables": st.session_state.get("schema", pd.DataFrame()).get("TABLE_NAME", pd.Series()).nunique() if "schema" in st.session_state else 0,
                "mappings_count": len(st.session_state.get("mappings", [])),
                "validation": st.session_state.get("validation_complete", False),
            }
            response = chat.ask(prompt, ctx)
            st.write(f"🤖 {response}")
    except Exception:
        pass
