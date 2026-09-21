import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import streamlit as st
import pandas as pd
from agents.schema_agent import SchemaAgent
from connectors.oracle_connector import OracleConnector


st.title("Schema Discovery")

source_type = st.session_state.get("source_type", None)

if source_type is None:
    st.warning("Please connect to a source database first (Step 1).")
    st.stop()

st.divider()

if source_type == "SQL Server":

    if "server" not in st.session_state:
        st.warning("Please connect to SQL Server first (Step 1).")
        st.stop()

    server = st.session_state["server"]
    database = st.session_state["database"]

    st.write(f"**Source:** SQL Server → `{server}` / `{database}`")

    agent = SchemaAgent(server, database, source_type="SQL Server")

    if st.button("Discover Schema"):

        with st.spinner("Reading database schema..."):

            schema_df = agent.discover_schema()

            total_cols = len(schema_df)
            total_tables = schema_df["TABLE_NAME"].nunique()

            st.success(f"✅ Schema discovered — {total_tables} tables, {total_cols} columns.")

            # Display with full type info
            display_df = schema_df[[
                "TABLE_NAME", "COLUMN_NAME", "FULL_DATA_TYPE", "IS_NULLABLE"
            ]].copy()
            display_df.columns = ["Table", "Column", "Data Type", "Nullable"]

            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.session_state["schema"] = schema_df


elif source_type == "Oracle (Real)":

    if "oracle_host" not in st.session_state:
        st.warning("Please connect to Oracle first (Step 1).")
        st.stop()

    st.write("**Source:** Oracle (Real)")
    st.write(f"**Service:** {st.session_state.get('oracle_connection_service', '')}")

    if st.button("Discover Schema"):

        with st.spinner("Discovering Oracle schema..."):

            try:
                # Use SchemaAgent for consistent output format
                oracle_config = {
                    "host": st.session_state["oracle_host"],
                    "port": st.session_state["oracle_port"],
                    "service_name": st.session_state["oracle_service"],
                    "sid": st.session_state["oracle_sid"],
                    "username": st.session_state["oracle_user"],
                    "password": st.session_state["oracle_pass"],
                    "mode": st.session_state.get("oracle_mode", "NORMAL"),
                }

                agent = SchemaAgent(
                    source_type="Oracle (Real)",
                    oracle_config=oracle_config
                )

                schema_df = agent.discover_schema()

                total_tables = schema_df["TABLE_NAME"].nunique()
                total_cols = len(schema_df)

                st.success(f"✅ Schema discovered — {total_tables} tables, {total_cols} columns.")

                # Display with full type info (standardized columns)
                display_df = schema_df[[
                    "TABLE_NAME", "COLUMN_NAME", "FULL_DATA_TYPE", "IS_NULLABLE"
                ]].copy()
                display_df.columns = ["Table", "Column", "Data Type", "Nullable"]

                st.dataframe(display_df, use_container_width=True, hide_index=True)

                st.session_state["schema"] = schema_df

            except Exception as e:
                st.error(f"Failed to discover schema: {str(e)}")
                st.info("💡 Try going back to Step 1 and reconnecting to Oracle.")


elif source_type == "Oracle (Simulator)":

    st.write("**Source:** Oracle (Simulator)")

    if "oracle_schema" not in st.session_state:
        st.warning("Please load Oracle schema first (Step 1).")
        st.stop()

    if st.button("Display Schema"):

        with st.spinner("Processing Oracle simulator schema..."):

            # Use SchemaAgent for consistent output format
            agent = SchemaAgent(source_type="Oracle (Simulator)")

            schema_df = agent.discover_schema()

            total_tables = schema_df["TABLE_NAME"].nunique()
            total_cols = len(schema_df)

            st.success(f"✅ Schema discovered — {total_tables} tables, {total_cols} columns.")

            # Display with full type info (standardized columns)
            display_df = schema_df[[
                "TABLE_NAME", "COLUMN_NAME", "FULL_DATA_TYPE", "IS_NULLABLE"
            ]].copy()
            display_df.columns = ["Table", "Column", "Data Type", "Nullable"]

            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.session_state["schema"] = schema_df
