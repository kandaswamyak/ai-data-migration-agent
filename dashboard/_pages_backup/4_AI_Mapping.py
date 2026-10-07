import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import pandas as pd
from agents.mapping_agent import MappingAgent


st.title("🗺️ AI Source-to-Target Mapping")

st.write(
    "AI generates column-level mapping rules from source (Oracle) "
    "to target (Azure SQL), including transformation type and risk level."
)

# ============================================================
# Check prerequisites
# ============================================================

source_type = st.session_state.get("source_type", None)

if source_type is None:
    st.warning("Please connect to a source database first (Step 1).")
    st.stop()

# Check for datatype analysis results (Step 3)
if "datatype_analysis" not in st.session_state:
    st.warning("Please run Datatype Analysis first (Step 3).")
    st.stop()

# Check that human review is complete (if there were incompatible columns)
if not st.session_state.get("review_complete", False):
    st.warning(
        "⚠️ Please complete the **Human Review** in Step 3 before proceeding. "
        "Incompatible columns need Accept/Override/Reject decisions."
    )
    st.stop()

st.info(f"**Source:** {source_type} → **Target:** Azure SQL Database")

# ============================================================
# Initialize Mapping Agent
# ============================================================

agent = MappingAgent(source_db="Oracle", target_db="Azure SQL")

# ============================================================
# Generate Mapping
# ============================================================

if st.button("🚀 Generate Mapping"):

    with st.spinner("AI is generating source-to-target mappings..."):

        # Get analysis results from Step 3
        analysis_df = st.session_state["datatype_analysis"]

        # Exclude rejected columns (user chose to skip them)
        analysis_df = analysis_df[
            analysis_df["status"] != "Rejected — Excluded"
        ].copy()

        # Convert DataFrame to list of dicts with keys MappingAgent expects
        results = []
        for _, row in analysis_df.iterrows():
            results.append({
                "table": row.get("table", ""),
                "column": row.get("column", ""),
                "source_type": row.get("source", ""),
                "target_type": row.get("target", ""),
                "source_length": row.get("source_length", None),
                "target_length": row.get("target_length", None),
                "source_precision": row.get("source_precision", None),
                "target_precision": row.get("target_precision", None),
                "source_scale": row.get("source_scale", None),
                "target_scale": row.get("target_scale", None),
                "status": row.get("status", ""),
                "risk": row.get("risk", ""),
                "confidence": row.get("confidence", 1.0),
                "nullable": row.get("nullable", "Y"),
            })

        mappings = agent.generate_mapping(results)

        st.session_state["mappings"] = mappings

        # Save to file
        agent.save_mappings(mappings)

        st.success(f"✅ Mapping generated — {len(mappings)} columns mapped.")


# ============================================================
# Display Mappings
# ============================================================

if "mappings" in st.session_state:

    mappings = st.session_state["mappings"]

    # Summary metrics
    summary = agent.get_approval_summary(mappings)

    st.divider()
    st.subheader("📊 Mapping Summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Mappings", summary["total"])
    col2.metric("✅ Approved", summary["approved"])
    col3.metric("⏳ Pending", summary["pending"])

    # Count by transformation type
    transformations = {}
    for m in mappings:
        t = m.get("transformation", "Direct")
        transformations[t] = transformations.get(t, 0) + 1

    with col4:
        if "Manual Override Required" in transformations:
            st.metric("🔴 Needs Override", transformations["Manual Override Required"])
        elif "Review Required" in transformations:
            st.metric("⚠️ Needs Review", transformations["Review Required"])
        else:
            st.metric("🟢 All Direct", transformations.get("Direct", 0))

    # ========================================================
    # Mapping Table
    # ========================================================

    st.divider()
    st.subheader("🗺️ Source → Target Mapping")

    df = pd.DataFrame(mappings)

    display_columns = [
        "source_table", "source_column", "source_type",
        "target_table", "target_column", "target_type",
        "transformation", "risk", "confidence", "approved"
    ]

    # Only show columns that exist
    available_columns = [col for col in display_columns if col in df.columns]

    display_df = df[available_columns].copy()

    # Format confidence as percentage
    if "confidence" in display_df.columns:
        display_df["confidence"] = display_df["confidence"].apply(
            lambda x: f"{float(x)*100:.0f}%" if x is not None and str(x) != "None" else "N/A"
        )

    # Format approved as emoji
    if "approved" in display_df.columns:
        display_df["approved"] = display_df["approved"].apply(
            lambda x: "✅" if x else "⏳"
        )

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ========================================================
    # Transformation Breakdown
    # ========================================================

    st.divider()
    st.subheader("🔄 Transformation Breakdown")

    for trans_type, count in sorted(transformations.items()):
        if trans_type == "Direct":
            st.write(f"✅ **{trans_type}:** {count} columns — no conversion needed")
        elif trans_type == "Type Conversion":
            st.write(f"🔄 **{trans_type}:** {count} columns — automatic type cast")
        elif trans_type == "Review Required":
            st.write(f"⚠️ **{trans_type}:** {count} columns — human review recommended")
        elif trans_type == "Manual Override Required":
            st.write(f"🔴 **{trans_type}:** {count} columns — cannot auto-map, needs manual decision")
        else:
            st.write(f"ℹ️ **{trans_type}:** {count} columns")

    # ========================================================
    # Columns requiring attention
    # ========================================================

    needs_attention = [m for m in mappings if m.get("transformation") != "Direct"]

    if needs_attention:
        st.divider()
        st.subheader("⚠️ Columns Requiring Attention")

        for m in needs_attention:
            with st.expander(
                f"🔸 {m['source_table']}.{m['source_column']} — {m['transformation']}"
            ):
                col1, col2 = st.columns(2)

                with col1:
                    st.write(f"**Source:** `{m['source_type']}`")
                    st.write(f"**Table:** `{m['source_table']}`")
                    st.write(f"**Risk:** {m['risk']}")

                with col2:
                    st.write(f"**Target:** `{m['target_type']}`")
                    st.write(f"**Transformation:** {m['transformation']}")
                    st.write(f"**Confidence:** {float(m.get('confidence', 0))*100:.0f}%")

                if m['risk'] == "High":
                    st.warning(
                        "⚠️ This mapping has HIGH risk. Consider manual override "
                        "in Step 6 (Human Approval)."
                    )

    # ========================================================
    # Approve All button
    # ========================================================

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("✅ Approve All Mappings"):
            st.session_state["mappings"] = agent.approve_all(mappings)
            agent.save_mappings(st.session_state["mappings"])
            st.success("All mappings approved! Proceed to Step 5 (SQL Generation).")
            st.rerun()

    with col2:
        if st.button("✅ Approve Compatible Only"):
            for i, m in enumerate(mappings):
                if m.get("transformation") == "Direct":
                    mappings[i]["approved"] = True
            st.session_state["mappings"] = mappings
            agent.save_mappings(mappings)
            st.success("Compatible mappings approved. Review flagged items in Step 6.")
            st.rerun()
