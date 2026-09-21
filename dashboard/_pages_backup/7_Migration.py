import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from agents.mapping_agent import MappingAgent


st.title("Migration Execution")

st.write("Execute the approved migration plan against Azure SQL.")

if "mappings" not in st.session_state:
    st.warning("Please generate and approve mappings first (Steps 4-6).")
    st.stop()

agent = MappingAgent(source_db="Oracle", target_db="Azure SQL")
mappings = st.session_state["mappings"]
summary = agent.get_approval_summary(mappings)

if not summary["ready_for_migration"]:
    st.error(
        f"❌ Cannot proceed. {summary['pending']} mapping(s) not yet approved. "
        "Go to Step 6 — Human Approval."
    )
    st.stop()

st.success(f"✅ All {summary['total']} mappings approved.")

st.divider()

st.subheader("Migration Target")
st.write("**Target:** Azure SQL Database")

st.divider()

st.warning(
    "⚠️ **POC Mode**: Migration execution requires Azure SQL connection.\n\n"
    "Once configured, clicking 'Execute Migration' will:\n"
    "1. Connect to Azure SQL\n"
    "2. Execute DDL (CREATE TABLE)\n"
    "3. Migrate sample data\n"
    "4. Proceed to Validation (Step 8)"
)

# Placeholder for actual execution
if st.button("Execute Migration (Dry Run)"):
    with st.spinner("Simulating migration..."):
        import time
        time.sleep(2)

        st.session_state["migration_executed"] = True
        st.success("✅ Dry run complete. DDL would be executed against Azure SQL.")

        st.json({
            "tables_created": summary["total"],
            "target": "Azure SQL",
            "mode": "Dry Run",
            "status": "Success"
        })
