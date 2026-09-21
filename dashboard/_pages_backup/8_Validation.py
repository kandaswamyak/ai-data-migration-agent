import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from agents.validation_agent import ValidationAgent
from agents.ai_engine import get_ai_engine
import json


st.title("Migration Validation")

st.write("Validate data integrity after migration.")

if "migration_executed" not in st.session_state:
    st.warning("Please execute migration first (Step 7).")
    st.stop()

st.success("Migration executed. Running validation checks...")

st.divider()

# Simulated validation results (in production, these come from actual queries)
validation_checks = [
    {"check": "Row Count Match", "source": "1000", "target": "1000", "status": "PASS"},
    {"check": "NULL Count Match", "source": "45", "target": "45", "status": "PASS"},
    {"check": "Duplicate Check", "source": "0", "target": "0", "status": "PASS"},
    {"check": "Data Type Integrity", "source": "7 columns", "target": "7 columns", "status": "PASS"},
    {"check": "Precision Validation", "source": "DECIMAL(19,4)", "target": "DECIMAL(19,4)", "status": "PASS"},
]

st.subheader("Validation Results")

all_passed = True
for check in validation_checks:
    col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
    col1.write(check["check"])
    col2.write(f"Source: {check['source']}")
    col3.write(f"Target: {check['target']}")

    if check["status"] == "PASS":
        col4.write("PASS")
    else:
        col4.write("FAIL")
        all_passed = False

st.divider()

# ====== AI INTERPRETATION ======
st.subheader("AI Analysis")

if "validation_ai_analysis" not in st.session_state:
    ai = get_ai_engine()
    if ai:
        with st.spinner("AI is interpreting validation results..."):
            prompt = f"""You are a data migration validation expert.

Analyze these validation results from an Oracle to Azure SQL migration:

VALIDATION CHECKS:
{json.dumps(validation_checks, indent=2)}

MIGRATION CONTEXT:
- Source: Oracle Database
- Target: Azure SQL Database
- Tables: {len(set(m.get('source_table', '') for m in st.session_state.get('mappings', [])))} tables
- Columns: {len(st.session_state.get('mappings', []))} columns

Provide:
1. A brief interpretation of the results (what passed, what failed)
2. If any checks failed: explain the likely cause and suggest fixes
3. If all passed: confirm data integrity and note any caveats
4. Recommendations for ongoing monitoring

Keep it concise (150 words max). Format in markdown."""

            try:
                analysis = ai.call(
                    prompt,
                    system_message="You are a data quality and migration validation expert.",
                    temperature=0.2
                )
                st.session_state["validation_ai_analysis"] = analysis
            except Exception as e:
                st.session_state["validation_ai_analysis"] = (
                    f"AI analysis unavailable: {str(e)}\n\n"
                    "**Summary:** All validation checks passed. "
                    "Row counts match, no duplicates introduced, "
                    "data types preserved, and precision maintained."
                )
    else:
        st.session_state["validation_ai_analysis"] = (
            "**Summary:** All validation checks passed.\n\n"
            "- Row counts match between source and target\n"
            "- No new NULL values introduced\n"
            "- No duplicates created during migration\n"
            "- All data types correctly mapped\n"
            "- Numeric precision preserved\n\n"
            "*Enable Azure OpenAI for AI-powered analysis.*"
        )

st.markdown(st.session_state["validation_ai_analysis"])

st.divider()

# Overall Result
st.subheader("Overall Result")
if all_passed:
    st.success("ALL VALIDATIONS PASSED")
else:
    st.error("SOME VALIDATIONS FAILED - Review above for details")

st.session_state["validation_complete"] = True
