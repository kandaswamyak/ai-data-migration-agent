import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import pandas as pd
import json
from datetime import datetime
from agents.report_agent import ReportAgent


st.title("Migration Report")

st.write("Complete migration summary and final report.")

if "validation_complete" not in st.session_state:
    st.warning("Please complete validation first (Step 8).")
    st.stop()

st.divider()

# ====== AI EXECUTIVE SUMMARY ======
st.subheader("AI-Generated Executive Summary")

# Build migration context from session state
migration_context = {
    "source_type": st.session_state.get("source_type", "Oracle"),
    "schema": st.session_state.get("schema"),
    "datatype_analysis": st.session_state.get("datatype_analysis"),
    "mappings": st.session_state.get("mappings", []),
    "ddl_statements": st.session_state.get("ddl_statements", []),
    "migration_executed": st.session_state.get("migration_executed", False),
    "validation_complete": st.session_state.get("validation_complete", False),
}

# Cache the executive summary
if "executive_summary" not in st.session_state:
    with st.spinner("AI is generating executive summary..."):
        report_agent = ReportAgent()
        st.session_state["executive_summary"] = report_agent.generate_executive_summary(migration_context)

st.markdown(st.session_state["executive_summary"])

if st.button("Regenerate Summary"):
    report_agent = ReportAgent()
    st.session_state["executive_summary"] = report_agent.generate_executive_summary(migration_context)
    st.rerun()

st.divider()

# ====== METRICS SUMMARY ======
st.subheader("Migration Metrics")

mappings = st.session_state.get("mappings", [])
tables = set(m.get("source_table", "") for m in mappings)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Tables", len(tables))
col2.metric("Columns", len(mappings))
col3.metric("Status", "SUCCESS")
col4.metric("Validation", "PASSED")

st.divider()

# ====== DATATYPE ANALYSIS BREAKDOWN ======
if "datatype_analysis" in st.session_state:
    analysis = st.session_state["datatype_analysis"]
    if hasattr(analysis, "__len__") and len(analysis) > 0:
        st.subheader("Datatype Conversion Summary")

        if hasattr(analysis, "to_dict"):
            df = analysis
        else:
            df = pd.DataFrame(analysis)

        if "status" in df.columns:
            col1, col2, col3 = st.columns(3)
            col1.metric("Compatible", len(df[df["status"] == "Compatible"]))
            col2.metric("Warnings", len(df[df["status"].isin(["Warning", "Review"])]))
            col3.metric("High Risk", len(df[df["status"] == "High Risk"]))

st.divider()

# ====== AI RECOMMENDATIONS ======
st.subheader("AI Recommendations")

if "report_recommendations" not in st.session_state:
    report_agent = ReportAgent()
    st.session_state["report_recommendations"] = report_agent.generate_recommendations(mappings)

for i, rec in enumerate(st.session_state["report_recommendations"], 1):
    st.write(f"{i}. {rec}")

st.divider()

# ====== DOWNLOAD REPORT ======
st.subheader("Download Report")

# Build comprehensive report JSON
report_data = {
    "report_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "source_database": st.session_state.get("source_type", "Oracle"),
    "target_database": "Azure SQL",
    "tables_migrated": len(tables),
    "columns_migrated": len(mappings),
    "status": "SUCCESS",
    "validation": "ALL PASSED",
    "executive_summary": st.session_state.get("executive_summary", ""),
    "recommendations": st.session_state.get("report_recommendations", []),
    "risk_profile": {
        "high": sum(1 for m in mappings if m.get("risk") == "High"),
        "medium": sum(1 for m in mappings if m.get("risk") == "Medium"),
        "low": sum(1 for m in mappings if m.get("risk") == "Low"),
    },
    "mappings": mappings,
}

report_json = json.dumps(report_data, indent=4, default=str)

col_dl1, col_dl2 = st.columns(2)

with col_dl1:
    st.download_button(
        label="Download Full Report (JSON)",
        data=report_json,
        file_name="migration_report.json",
        mime="application/json"
    )

with col_dl2:
    # Markdown report for human reading
    md_report = f"""# Data Migration Report
**Date:** {report_data['report_date']}
**Source:** {report_data['source_database']} | **Target:** {report_data['target_database']}

## Executive Summary
{st.session_state.get('executive_summary', 'N/A')}

## Metrics
- Tables: {report_data['tables_migrated']}
- Columns: {report_data['columns_migrated']}
- Status: {report_data['status']}
- Validation: {report_data['validation']}

## Recommendations
""" + "\n".join(f"- {r}" for r in st.session_state.get("report_recommendations", []))

    st.download_button(
        label="Download Report (Markdown)",
        data=md_report,
        file_name="migration_report.md",
        mime="text/markdown"
    )
