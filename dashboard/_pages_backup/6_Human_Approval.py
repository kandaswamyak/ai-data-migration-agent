import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import pandas as pd
from agents.mapping_agent import MappingAgent
from agents.risk_analyst import RiskAnalyst


st.title("Human Approval")

st.write("Review and approve AI-recommended mappings before migration.")

if "mappings" not in st.session_state:
    st.warning("Please generate mappings first (Step 4).")
    st.stop()

agent = MappingAgent(source_db="Oracle", target_db="Azure SQL")
mappings = st.session_state["mappings"]

# Summary
summary = agent.get_approval_summary(mappings)

col1, col2, col3 = st.columns(3)
col1.metric("Total", summary["total"])
col2.metric("Approved", summary["approved"])
col3.metric("Pending", summary["pending"])

if summary["ready_for_migration"]:
    st.success("All mappings approved. Ready for migration.")
else:
    st.info(f"{summary['pending']} mapping(s) pending approval.")

st.divider()

# ====== AI RISK SUMMARY ======
st.subheader("AI Risk Assessment")

# Cache the risk summary so it doesn't re-generate on every rerun
if "risk_summary" not in st.session_state:
    with st.spinner("AI is analyzing migration risks..."):
        risk_agent = RiskAnalyst()
        st.session_state["risk_summary"] = risk_agent.generate_risk_summary(mappings)

st.markdown(st.session_state["risk_summary"])

if st.button("Regenerate Risk Analysis"):
    risk_agent = RiskAnalyst()
    st.session_state["risk_summary"] = risk_agent.generate_risk_summary(mappings)
    st.rerun()

st.divider()

# Review each mapping
st.subheader("Review Mappings")

for i, mapping in enumerate(mappings):

    status_icon = "+" if mapping.get("approved") else "-"
    risk_color = {"Low": "L", "Medium": "M", "High": "H"}.get(mapping.get("risk", ""), "?")

    with st.expander(
        f"{'[APPROVED]' if mapping.get('approved') else '[PENDING]'} "
        f"{mapping.get('source_table', '')}.{mapping.get('source_column', '')} "
        f"-> {mapping.get('target_type', '')} [Risk: {risk_color}]"
    ):

        col_a, col_b = st.columns(2)

        with col_a:
            st.write("**Source**")
            st.write(f"Table: `{mapping.get('source_table', '')}`")
            st.write(f"Column: `{mapping.get('source_column', '')}`")
            st.write(f"Type: `{mapping.get('source_type', '')}`")

        with col_b:
            st.write("**Target (Azure SQL)**")
            st.write(f"Table: `{mapping.get('target_table', '')}`")
            st.write(f"Column: `{mapping.get('target_column', '')}`")
            st.write(f"Type: `{mapping.get('target_type', '')}`")

        conf = mapping.get("confidence", 0)
        if isinstance(conf, (int, float)):
            conf_pct = f"{conf * 100:.0f}%" if conf <= 1 else f"{conf:.0f}%"
        else:
            conf_pct = str(conf)

        st.write(f"**Risk:** {mapping.get('risk', 'Unknown')} | **Confidence:** {conf_pct}")
        st.write(f"**Transformation:** {mapping.get('transformation', 'Direct')}")

        # Show AI reasoning if available
        reasoning = mapping.get("reasoning", "")
        if reasoning:
            st.info(f"**AI Reasoning:** {reasoning}")

        if not mapping.get("approved"):
            if st.button(f"Approve", key=f"approve_{i}"):
                mappings[i]["approved"] = True
                st.session_state["mappings"] = mappings
                agent.save_mappings(mappings)
                st.rerun()

st.divider()

# Bulk actions
col_x, col_y = st.columns(2)

with col_x:
    if st.button("Approve All"):
        mappings = agent.approve_all(mappings)
        st.session_state["mappings"] = mappings
        st.session_state["all_mappings_approved"] = True
        agent.save_mappings(mappings)
        st.rerun()

with col_y:
    if summary["ready_for_migration"]:
        st.session_state["all_mappings_approved"] = True
        st.success("Proceed to Migration (Step 7)")
