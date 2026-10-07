import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from agents.sql_generator import SQLGenerator


st.title("SQL / DDL Generator")

st.write("Generate CREATE TABLE DDL for Azure SQL based on approved mappings.")

if "mappings" not in st.session_state:
    st.warning("Please generate mappings first (Step 4).")
    st.stop()

generator = SQLGenerator(target_db="Azure SQL")

if st.button("Generate DDL"):

    with st.spinner("Generating DDL..."):

        mappings = st.session_state["mappings"]
        ddl_statements = generator.generate_ddl(mappings)

        st.session_state["ddl_statements"] = ddl_statements

        # Save DDL
        generator.save_ddl(ddl_statements)

        st.success("DDL generated successfully.")


if "ddl_statements" in st.session_state:

    ddl_statements = st.session_state["ddl_statements"]

    summary = generator.generate_summary(ddl_statements)

    st.metric("Tables", summary["total_tables"])
    st.caption(f"Target: {summary['target']}")
    st.caption(f"Status: {summary['status']}")

    st.divider()

    st.subheader("Generated DDL")

    for i, ddl in enumerate(ddl_statements):
        st.code(ddl, language="sql")

    st.divider()

    # Download DDL
    full_ddl = "\n\n".join(ddl_statements)
    st.download_button(
        label="📥 Download DDL (.sql)",
        data=full_ddl,
        file_name="migration_ddl.sql",
        mime="text/plain"
    )

    st.divider()

    st.warning("⚠️ This DDL has NOT been executed. Proceed to Human Approval (Step 6).")
