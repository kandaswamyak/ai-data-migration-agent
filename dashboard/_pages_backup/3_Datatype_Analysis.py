import sys
import os
import json

# ============================================================
# Project path
# ============================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ============================================================
# Imports
# ============================================================

import streamlit as st
import pandas as pd

from agents.datatype_agent import DatatypeAnalysisAgent


# ============================================================
# Page Configuration
# ============================================================

st.set_page_config(
    page_title="AI Datatype Analysis",
    page_icon="🤖",
    layout="wide"
)


# ============================================================
# Title
# ============================================================

st.title("🤖 AI Datatype Analysis")

st.write(
    "AI analyzes source database datatypes and recommends "
    "the safest Azure SQL Database datatype while preserving "
    "length, precision and scale."
)


# ============================================================
# Get Source Type
# ============================================================

source_type = st.session_state.get(
    "source_type",
    None
)

if source_type is None:

    st.warning(
        "Please connect to a source database first "
        "(Step 1)."
    )

    st.stop()


st.info(
    f"**Source:** {source_type} "
    f"→ **Target:** Azure SQL Database"
)


# ============================================================
# Metadata File Locations
# ============================================================

SQL_SERVER_METADATA = os.path.join(
    PROJECT_ROOT,
    "data",
    "metadata.json"
)

ORACLE_METADATA = os.path.join(
    PROJECT_ROOT,
    "data",
    "oracle_metadata.json"
)


# ============================================================
# Load Metadata
# ============================================================

def load_metadata():

    """
    Load metadata based on selected source.

    Priority:
        1. Session state schema (from Step 2 discovery) - always fresh
        2. Fallback to JSON files on disk
    """

    # --------------------------------------------------------
    # Priority 1: Use session state schema (fresh from Step 2)
    # --------------------------------------------------------

    if "schema" in st.session_state:
        schema_df = st.session_state["schema"]

        if schema_df is not None and len(schema_df) > 0:
            # Convert DataFrame to dict format expected by analysis
            # Group by TABLE_NAME
            metadata = {}

            # Normalize column names to uppercase
            df = schema_df.copy()
            df.columns = [c.upper() for c in df.columns]

            # Map standardized column names to what analysis expects
            col_map = {
                "SOURCE_LENGTH": "DATA_LENGTH",
                "SOURCE_PRECISION": "DATA_PRECISION",
                "SOURCE_SCALE": "DATA_SCALE",
            }
            df = df.rename(columns={
                k: v for k, v in col_map.items()
                if k in df.columns
            })

            for table in df["TABLE_NAME"].unique():
                table_df = df[df["TABLE_NAME"] == table]
                # Convert NaN to None for JSON compatibility
                table_df = table_df.astype(object).where(
                    pd.notna(table_df), None
                )
                metadata[table] = table_df.to_dict(orient="records")

            return metadata

    # --------------------------------------------------------
    # Priority 2: Fallback to JSON files on disk
    # --------------------------------------------------------

    # --------------------------------------------------------
    # SQL Server
    # --------------------------------------------------------

    if source_type == "SQL Server":

        if not os.path.exists(
            SQL_SERVER_METADATA
        ):

            st.error(
                "SQL Server metadata not found."
            )

            st.info(
                "Please run Schema Discovery "
                "(Step 2) first."
            )

            st.stop()

        try:

            with open(
                SQL_SERVER_METADATA,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

        except Exception as e:

            st.error(
                f"Unable to read SQL Server metadata: {e}"
            )

            st.stop()

    # --------------------------------------------------------
    # Oracle Simulator
    # --------------------------------------------------------

    elif source_type in ("Oracle", "Oracle (Real)", "Oracle (Simulator)"):

        if not os.path.exists(
            ORACLE_METADATA
        ):

            st.error(
                "Oracle metadata not found."
            )

            st.info(
                "Please check "
                "data/oracle_metadata.json."
            )

            st.stop()

        try:

            with open(
                ORACLE_METADATA,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

        except Exception as e:

            st.error(
                f"Unable to read Oracle metadata: {e}"
            )

            st.stop()

    # --------------------------------------------------------
    # Unsupported source
    # --------------------------------------------------------

    st.error(
        f"Unsupported source type: {source_type}"
    )

    st.stop()


# ============================================================
# Initialize AI Agent
# ============================================================

try:

    agent = DatatypeAnalysisAgent()

    st.success(
        "🤖 AI Engine: Azure OpenAI Connected"
    )

except Exception as e:

    st.error(
        "AI Agent configuration error"
    )

    st.code(
        str(e),
        language="text"
    )

    st.info(
        "Please check config/.env and verify "
        "Azure OpenAI configuration."
    )

    st.stop()


# ============================================================
# Build SQL Server Source Metadata
# ============================================================

def build_sqlserver_source_column(
    table_name,
    column
):

    return {

        # Source information
        "source_database": "SQL Server",

        # Table / Column
        "table_name": table_name,

        "column_name":
            column.get(
                "COLUMN_NAME",
                ""
            ),

        # Raw datatype
        "data_type":
            column.get(
                "DATA_TYPE",
                ""
            ),

        # Complete datatype
        "full_data_type":
            column.get(
                "FULL_DATA_TYPE",
                column.get(
                    "DATA_TYPE",
                    ""
                )
            ),

        # Length
        "length":
            column.get(
                "SOURCE_LENGTH",
                column.get(
                    "CHARACTER_MAXIMUM_LENGTH"
                )
            ),

        # Precision
        "precision":
            column.get(
                "SOURCE_PRECISION",
                column.get(
                    "NUMERIC_PRECISION"
                )
            ),

        # Scale
        "scale":
            column.get(
                "SOURCE_SCALE",
                column.get(
                    "NUMERIC_SCALE"
                )
            ),

        # Nullable
        "nullable":
            column.get(
                "IS_NULLABLE",
                "YES"
            )
    }


# ============================================================
# Build Oracle Source Metadata
# ============================================================

def build_oracle_source_column(
    table_name,
    column
):

    return {

        # Source information
        "source_database": "Oracle",

        # Table / Column
        "table_name": table_name,

        "column_name":
            column.get(
                "COLUMN_NAME",
                ""
            ),

        # Raw datatype
        "data_type":
            column.get(
                "DATA_TYPE",
                ""
            ),

        # Oracle complete datatype
        "full_data_type":
            build_oracle_full_type(
                column
            ),

        # Oracle length
        "length":
            column.get(
                "DATA_LENGTH"
            ),

        # Oracle precision
        "precision":
            column.get(
                "DATA_PRECISION"
            ),

        # Oracle scale
        "scale":
            column.get(
                "DATA_SCALE"
            ),

        # Nullable
        "nullable":
            column.get(
                "NULLABLE",
                "Y"
            )
    }


# ============================================================
# Oracle Full Datatype
# ============================================================

def build_oracle_full_type(column):

    dtype = column.get(
        "DATA_TYPE",
        ""
    )

    if dtype is None:
        return ""

    dtype = str(
        dtype
    ).upper().strip()

    length = column.get(
        "DATA_LENGTH"
    )

    precision = column.get(
        "DATA_PRECISION"
    )

    scale = column.get(
        "DATA_SCALE"
    )

    # --------------------------------------------------------
    # VARCHAR2 / CHAR
    # --------------------------------------------------------

    if dtype in (
        "VARCHAR2",
        "CHAR",
        "NVARCHAR2"
    ):

        if pd.notna(length):

            try:

                return (
                    f"{dtype}"
                    f"({int(float(length))})"
                )

            except (
                ValueError,
                TypeError
            ):

                return dtype

        return dtype

    # --------------------------------------------------------
    # NUMBER
    # --------------------------------------------------------

    if dtype == "NUMBER":

        if (
            pd.notna(precision)
            and
            pd.notna(scale)
        ):

            try:

                return (
                    f"NUMBER"
                    f"({int(float(precision))},"
                    f"{int(float(scale))})"
                )

            except (
                ValueError,
                TypeError
            ):

                return dtype

        if pd.notna(precision):

            try:

                return (
                    f"NUMBER"
                    f"({int(float(precision))})"
                )

            except (
                ValueError,
                TypeError
            ):

                return dtype

        return dtype

    return dtype


# ============================================================
# Run AI Analysis
# ============================================================

if st.button(
    "🚀 Run AI Datatype Analysis",
    type="primary"
):

    # --------------------------------------------------------
    # Load metadata
    # --------------------------------------------------------

    schema = load_metadata()

    if not schema:

        st.warning(
            "No metadata found."
        )

        st.stop()

    # --------------------------------------------------------
    # Flatten metadata
    # --------------------------------------------------------

    all_columns = []

    for table_name, columns in schema.items():

        # Protect against unexpected metadata
        if not isinstance(columns, list):

            st.warning(
                f"Skipping {table_name}: "
                "metadata format is invalid."
            )

            continue

        for column in columns:

            all_columns.append(
                (
                    table_name,
                    column
                )
            )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    total = len(
        all_columns
    )

    if total == 0:

        st.warning(
            "No columns found in metadata."
        )

        st.stop()

    st.info(
        f"Found **{total} columns** "
        f"for AI datatype analysis."
    )

    # --------------------------------------------------------
    # Progress
    # --------------------------------------------------------

    progress = st.progress(0)

    status_text = st.empty()

    results = []

    # ========================================================
    # Process every column
    # ========================================================

    for index, (
        table_name,
        column
    ) in enumerate(all_columns):

        column_name = column.get(
            "COLUMN_NAME",
            ""
        )

        status_text.write(
            f"Analyzing "
            f"**{table_name}.{column_name}**..."
        )

        # ----------------------------------------------------
        # Build source object
        # ----------------------------------------------------

        if source_type == "SQL Server":

            source_column = (
                build_sqlserver_source_column(
                    table_name,
                    column
                )
            )

        elif source_type in ("Oracle", "Oracle (Real)", "Oracle (Simulator)"):

            source_column = (
                build_oracle_source_column(
                    table_name,
                    column
                )
            )

        else:

            source_column = {}

        # ----------------------------------------------------
        # AI Analysis
        # ----------------------------------------------------

        try:

            analysis = agent.analyze(
                source_column
            )

            # -----------------------------------------------
            # Build result
            # -----------------------------------------------

            result = {

                "table":
                    table_name,

                "column":
                    column_name,

                # Source
                "source":
                    analysis.get(
                        "source_type",
                        source_column.get(
                            "full_data_type",
                            source_column.get(
                                "data_type",
                                ""
                            )
                        )
                    ),

                # Target
                "target":
                    analysis.get(
                        "target_type",
                        ""
                    ),

                # Length
                "source_length":
                    analysis.get(
                        "source_length"
                    ),

                "target_length":
                    analysis.get(
                        "target_length"
                    ),

                # Precision
                "source_precision":
                    analysis.get(
                        "source_precision"
                    ),

                "target_precision":
                    analysis.get(
                        "target_precision"
                    ),

                # Scale
                "source_scale":
                    analysis.get(
                        "source_scale"
                    ),

                "target_scale":
                    analysis.get(
                        "target_scale"
                    ),

                # Analysis
                "status":
                    analysis.get(
                        "status",
                        "Review"
                    ),

                "risk":
                    analysis.get(
                        "risk",
                        "Medium"
                    ),

                "confidence":
                    analysis.get(
                        "confidence",
                        0
                    ),

                "difference":
                    analysis.get(
                        "datatype_difference",
                        ""
                    ),

                "reason":
                    analysis.get(
                        "reason",
                        ""
                    ),

                "recommendation":
                    analysis.get(
                        "recommendation",
                        ""
                    ),

                # Technical debugging
                "error":
                    ""
            }

            results.append(
                result
            )

        # ----------------------------------------------------
        # AI Error
        # ----------------------------------------------------

        except Exception as e:

            error_message = str(e)

            # Show actual error immediately
            st.error(
                f"❌ AI analysis failed for "
                f"{table_name}.{column_name}"
            )

            with st.expander(
                "View technical error"
            ):

                st.code(
                    error_message,
                    language="text"
                )

                st.write(
                    "**Source metadata sent to AI:**"
                )

                st.json(
                    source_column
                )

            results.append({

                "table":
                    table_name,

                "column":
                    column_name,

                "source":
                    source_column.get(
                        "full_data_type",
                        source_column.get(
                            "data_type",
                            ""
                        )
                    ),

                "target":
                    "AI ERROR",

                "source_length":
                    source_column.get(
                        "length"
                    ),

                "target_length":
                    None,

                "source_precision":
                    source_column.get(
                        "precision"
                    ),

                "target_precision":
                    None,

                "source_scale":
                    source_column.get(
                        "scale"
                    ),

                "target_scale":
                    None,

                "status":
                    "AI Error",

                "risk":
                    "Unknown",

                "confidence":
                    0,

                "difference":
                    "",

                "reason":
                    error_message,

                "recommendation":
                    "Fix AI configuration/API "
                    "before continuing.",

                "error":
                    error_message
            })

        # ----------------------------------------------------
        # Progress
        # ----------------------------------------------------

        progress.progress(
            (index + 1) / total
        )

    # --------------------------------------------------------
    # Finish
    # --------------------------------------------------------

    status_text.success(
        "AI datatype analysis completed."
    )

    st.session_state[
        "datatype_analysis"
    ] = pd.DataFrame(
        results
    )

    st.success(
        "✅ AI datatype analysis completed."
    )


# ============================================================
# Display Results
# ============================================================

if (
    "datatype_analysis"
    in st.session_state
):

    df = st.session_state[
        "datatype_analysis"
    ]

    st.subheader(
        f"AI Analysis: "
        f"{source_type} → Azure SQL"
    )

    # ========================================================
    # Metrics
    # ========================================================

    total = len(df)

    compatible = len(
        df[
            df["status"]
            == "Compatible"
        ]
    )

    review = len(
        df[
            df["status"]
            == "Review"
        ]
    )

    warning = len(
        df[
            df["status"]
            == "Warning"
        ]
    )

    high_risk = len(
        df[
            df["status"]
            == "High Risk"
        ]
    )

    ai_errors = len(
        df[
            df["status"]
            == "AI Error"
        ]
    )

    # --------------------------------------------------------
    # Metrics
    # --------------------------------------------------------

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric(
        "Columns",
        total
    )

    c2.metric(
        "✅ Compatible",
        compatible
    )

    c3.metric(
        "🔍 Review",
        review
    )

    c4.metric(
        "⚠️ Warning",
        warning
    )

    c5.metric(
        "❌ High Risk",
        high_risk
    )

    c6.metric(
        "🤖 AI Errors",
        ai_errors
    )

    st.divider()

    # ========================================================
    # Summary Table
    # ========================================================

    st.subheader(
        "Datatype Comparison"
    )

    # ====================================================
    # Fill target_length for numeric types with P:x S:y
    # so the display is not blank
    # ====================================================

    numeric_targets = (
        "NUMERIC", "DECIMAL", "BIGINT", "INT",
        "SMALLINT", "TINYINT", "FLOAT", "REAL",
        "DATETIME2", "DATE", "TIME"
    )

    for idx, row in df.iterrows():
        target = str(row.get("target", "")).upper().strip()
        if target in numeric_targets and (
            row.get("target_length") is None
            or str(row.get("target_length")) == "None"
        ):
            t_prec = row.get("target_precision")
            t_scale = row.get("target_scale")
            if t_prec is not None and str(t_prec) != "None":
                if t_scale is not None and str(t_scale) != "None":
                    df.at[idx, "target_length"] = f"P:{t_prec} S:{t_scale}"
                else:
                    df.at[idx, "target_length"] = f"P:{t_prec}"
            elif target in ("BIGINT", "INT", "SMALLINT", "TINYINT"):
                df.at[idx, "target_length"] = "Fixed"
            elif target in ("DATETIME2", "DATE", "TIME"):
                df.at[idx, "target_length"] = "Fixed"

    display_columns = [

        "table",
        "column",

        "source",
        "target",

        "source_length",
        "target_length",

        "source_precision",
        "target_precision",

        "source_scale",
        "target_scale",

        "status",
        "risk",
        "confidence"
    ]

    # Protect against missing columns
    available_columns = [
        col
        for col in display_columns
        if col in df.columns
    ]

    st.dataframe(
        df[
            available_columns
        ],
        use_container_width=True,
        hide_index=True
    )

    # ========================================================
    # Compatibility Summary & Issues Report
    # ========================================================

    st.divider()
    st.subheader("📊 Compatibility Summary")

    # Categorize results
    compatible_df = df[df["status"].str.lower() == "compatible"]
    attention_df = df[df["status"].str.lower().isin([
        "requires review", "attention", "warning",
        "partially compatible", "review"
    ])]
    incompatible_df = df[df["status"].str.lower().isin([
        "incompatible", "not compatible", "unsupported",
        "high risk", "data loss"
    ])]

    # If no explicit incompatible status, check by risk level
    if len(attention_df) == 0 and len(incompatible_df) == 0:
        attention_df = df[df["risk"].str.lower().isin(["medium", "moderate"])]
        incompatible_df = df[df["risk"].str.lower() == "high"]

    # Also catch low confidence as needing attention
    low_confidence = df[
        (df["confidence"].apply(
            lambda x: float(x) if x is not None and str(x) not in ("None", "") else 1.0
        ) < 1.0)
        & (~df.index.isin(incompatible_df.index))
        & (~df.index.isin(attention_df.index))
    ]
    attention_df = pd.concat([attention_df, low_confidence]).drop_duplicates()

    # Also flag known problematic Oracle types regardless of AI status
    problematic_types = [
        "LONG RAW", "LONG", "XMLTYPE", "BFILE",
        "INTERVAL", "INTERVAL DAY", "INTERVAL YEAR",
        "ROWID", "UROWID", "NCLOB"
    ]
    problematic_mask = df["source"].apply(
        lambda x: any(pt in str(x).upper() for pt in problematic_types)
    )
    problematic_df = df[problematic_mask & (~df.index.isin(incompatible_df.index)) & (~df.index.isin(attention_df.index))]
    attention_df = pd.concat([attention_df, problematic_df]).drop_duplicates()

    # Recalculate compatible as everything NOT in attention or incompatible
    flagged_indices = set(attention_df.index.tolist() + incompatible_df.index.tolist())
    compatible_df = df[~df.index.isin(flagged_indices)]

    # Display counts
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "✅ Compatible",
            f"{len(compatible_df)} columns",
        )

    with col2:
        st.metric(
            "⚠️ Requires Attention",
            f"{len(attention_df)} columns",
        )

    with col3:
        st.metric(
            "🔴 Incompatible / High Risk",
            f"{len(incompatible_df)} columns",
        )

    # --------------------------------------------------------
    # Issues & Recommended Solutions table
    # --------------------------------------------------------

    issues_df = pd.concat([incompatible_df, attention_df]).drop_duplicates()

    if len(issues_df) > 0:

        st.divider()
        st.subheader("⚠️ Incompatible Columns — AI Conversion & Human Review")

        st.write("---")
        st.write("**Workflow:** Incompatible → AI Conversion/Transformation → Human Review → Approve/Reject")

        st.write(
            "The following columns need review before migration. "
            "The AI has suggested solutions — please **Accept**, "
            "**Override**, or **Flag for manual review**."
        )

        # Build solutions table
        solution_rows = []

        for _, row in issues_df.iterrows():
            source_type = row.get("source", "")
            target_type = row.get("target", "")
            risk = row.get("risk", "")
            status = row.get("status", "")
            confidence = row.get("confidence", "")

            # Determine issue description
            issue = ""
            if str(source_type).upper() in ("LONG RAW", "LONG"):
                issue = "Deprecated Oracle type — no direct equivalent"
            elif str(source_type).upper() == "XMLTYPE":
                issue = "Azure SQL XML has size/feature limitations"
            elif "INTERVAL" in str(source_type).upper():
                issue = "No direct INTERVAL equivalent in Azure SQL"
            elif str(source_type).upper() in ("BFILE", "BFILENAME"):
                issue = "File pointer — no equivalent in Azure SQL"
            elif str(source_type).upper() == "CLOB":
                issue = "May exceed NVARCHAR(4000) limit"
            elif float(confidence) < 0.9 if confidence else False:
                issue = f"Low confidence mapping ({confidence})"
            else:
                issue = f"Risk: {risk} — review recommended"

            solution_rows.append({
                "Table": row.get("table", ""),
                "Column": row.get("column", ""),
                "Source Type": source_type,
                "Issue": issue,
                "Recommended Solution": target_type,
                "Risk": risk,
                "Status": f"🔴 {status}" if risk.lower() == "high" else f"⚠️ {status}",
            })

        solutions = pd.DataFrame(solution_rows)

        st.dataframe(
            solutions,
            use_container_width=True,
            hide_index=True
        )

        # ====================================================
        # Human Review: Accept / Override / Reject per column
        # ====================================================

        st.divider()
        st.subheader("👤 Human Review — Decision Required")

        st.write(
            "For each incompatible column, choose an action:"
        )

        # Initialize review decisions in session state
        if "review_decisions" not in st.session_state:
            st.session_state["review_decisions"] = {}

        for idx, row in issues_df.iterrows():
            table_col = f"{row.get('table', '')}.{row.get('column', '')}"
            source = row.get("source", "")
            target = row.get("target", "")

            with st.expander(
                f"🔸 {table_col} — `{source}` → `{target}`",
                expanded=True
            ):
                col1, col2, col3 = st.columns([2, 2, 2])

                with col1:
                    st.write(f"**Source Type:** `{source}`")
                    st.write(f"**Risk:** {row.get('risk', '')}")

                with col2:
                    st.write(f"**AI Recommended:** `{target}`")
                    st.write(f"**Confidence:** {row.get('confidence', '')}")

                with col3:
                    decision = st.radio(
                        "Action",
                        ["✅ Accept AI Solution", "🔄 Override", "❌ Reject (Skip)"],
                        key=f"decision_{table_col}",
                        index=0
                    )

                    if "Override" in decision:
                        override_type = st.text_input(
                            "Enter target type:",
                            value=target,
                            key=f"override_{table_col}"
                        )
                        st.session_state["review_decisions"][table_col] = {
                            "action": "override",
                            "target_type": override_type
                        }
                    elif "Accept" in decision:
                        st.session_state["review_decisions"][table_col] = {
                            "action": "accept",
                            "target_type": target
                        }
                    else:
                        st.session_state["review_decisions"][table_col] = {
                            "action": "reject",
                            "target_type": None
                        }

        # ====================================================
        # Confirm & Proceed button
        # ====================================================

        st.divider()

        decisions = st.session_state.get("review_decisions", {})
        accepted = sum(1 for d in decisions.values() if d["action"] in ("accept", "override"))
        rejected = sum(1 for d in decisions.values() if d["action"] == "reject")

        st.write(f"**Decisions:** ✅ Accepted/Overridden: {accepted} | ❌ Rejected: {rejected}")

        if st.button("✅ Confirm Decisions & Proceed to Step 4"):
            # Apply overrides to the datatype_analysis dataframe
            analysis_df = st.session_state["datatype_analysis"].copy()

            for table_col, decision in decisions.items():
                parts = table_col.split(".", 1)
                if len(parts) == 2:
                    table, column = parts
                    mask = (analysis_df["table"] == table) & (analysis_df["column"] == column)

                    if decision["action"] == "override":
                        analysis_df.loc[mask, "target"] = decision["target_type"]
                        analysis_df.loc[mask, "status"] = "Overridden"
                    elif decision["action"] == "reject":
                        analysis_df.loc[mask, "status"] = "Rejected — Excluded"

            st.session_state["datatype_analysis"] = analysis_df
            st.session_state["review_complete"] = True
            st.success(
                "✅ Review complete! Decisions saved. "
                "Proceed to **Step 4 (AI Mapping)**."
            )

    else:
        st.success(
            "🎉 **All columns are compatible!** "
            "No issues detected — direct mapping to Step 4."
        )
        st.session_state["review_complete"] = True

    st.divider()

    # ========================================================
    # Detailed AI Recommendations
    # ========================================================

    st.subheader(
        "🔎 AI Recommendation Details"
    )

    for _, row in df.iterrows():

        status = row.get(
            "status",
            ""
        )

        table = row.get(
            "table",
            ""
        )

        column = row.get(
            "column",
            ""
        )

        with st.expander(
            f"{table} → {column} "
            f"[{status}]"
        ):

            col1, col2 = st.columns(2)

            # ------------------------------------------------
            # Left
            # ------------------------------------------------

            with col1:

                st.write(
                    f"**Source:** "
                    f"{row.get('source', '')}"
                )

                st.write(
                    f"**Target:** "
                    f"{row.get('target', '')}"
                )

                st.write(
                    f"**Status:** "
                    f"{row.get('status', '')}"
                )

                st.write(
                    f"**Risk:** "
                    f"{row.get('risk', '')}"
                )

                st.write(
                    f"**Confidence:** "
                    f"{row.get('confidence', 0)}%"
                )

            # ------------------------------------------------
            # Right
            # ------------------------------------------------

            with col2:

                st.write(
                    "**Datatype Difference**"
                )

                st.write(
                    row.get(
                        "difference",
                        ""
                    )
                )

                st.write(
                    "**Reason**"
                )

                st.write(
                    row.get(
                        "reason",
                        ""
                    )
                )

                st.write(
                    "**Recommendation**"
                )

                st.write(
                    row.get(
                        "recommendation",
                        ""
                    )
                )

            # ------------------------------------------------
            # Technical error
            # ------------------------------------------------

            if status == "AI Error":

                st.error(
                    "AI analysis failed for "
                    "this column."
                )

                st.code(
                    row.get(
                        "error",
                        row.get(
                            "reason",
                            ""
                        )
                    ),
                    language="text"
                )

    st.divider()

    # ========================================================
    # Download
    # ========================================================

    csv = df.to_csv(
        index=False
    )

    st.download_button(
        label="📥 Download AI Analysis (CSV)",
        data=csv,
        file_name="ai_datatype_analysis.csv",
        mime="text/csv"
    )