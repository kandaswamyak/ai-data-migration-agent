#!/usr/bin/env python
"""Quick test of Oracle schema detection via SchemaAgent"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config.config import Config
from agents.schema_agent import SchemaAgent

print("Testing Oracle Schema Detection via SchemaAgent...\n")

# ============================================================
# Test 1: Oracle (Real) via SchemaAgent
# ============================================================
print("=" * 50)
print("TEST 1: Oracle (Real) Schema Discovery")
print("=" * 50)

try:
    oracle_config = {
        "host": Config.ORACLE_HOST,
        "port": Config.ORACLE_PORT,
        "service_name": Config.ORACLE_SERVICE_NAME,
        "sid": Config.ORACLE_SID,
        "username": Config.ORACLE_USERNAME,
        "password": Config.ORACLE_PASSWORD,
        "mode": "SYSDBA",
        "thick_mode": Config.ORACLE_THICK_MODE,
        "lib_dir": Config.ORACLE_CLIENT_LIB_DIR if Config.ORACLE_CLIENT_LIB_DIR else None,
    }

    agent = SchemaAgent(
        source_type="Oracle (Real)",
        oracle_config=oracle_config
    )

    print("✓ SchemaAgent created for Oracle (Real)")
    print("✓ Discovering schema...")

    schema_df = agent.discover_schema()
    print(f"✓ Schema discovered: {len(schema_df)} rows\n")

    print("Columns in DataFrame:")
    print(f"  {list(schema_df.columns)}\n")

    print("First 5 rows:")
    print(schema_df.head().to_string())

    print("\n✓ FULL_DATA_TYPE column present:", "FULL_DATA_TYPE" in schema_df.columns)
    print("✓ TABLE_NAME column present:", "TABLE_NAME" in schema_df.columns)
    print("✓ IS_NULLABLE column present:", "IS_NULLABLE" in schema_df.columns)

    print("\n✓ SUCCESS: Oracle (Real) schema detection is working!")

except Exception as e:
    print(f"✗ Oracle (Real) test failed: {str(e)}")
    import traceback
    traceback.print_exc()

# ============================================================
# Test 2: Oracle (Simulator) via SchemaAgent
# ============================================================
print("\n" + "=" * 50)
print("TEST 2: Oracle (Simulator) Schema Discovery")
print("=" * 50)

try:
    agent = SchemaAgent(source_type="Oracle (Simulator)")

    print("✓ SchemaAgent created for Oracle (Simulator)")
    print("✓ Discovering schema...")

    schema_df = agent.discover_schema()
    print(f"✓ Schema discovered: {len(schema_df)} rows\n")

    print("Columns in DataFrame:")
    print(f"  {list(schema_df.columns)}\n")

    print("All rows:")
    print(schema_df.to_string())

    print("\n✓ FULL_DATA_TYPE column present:", "FULL_DATA_TYPE" in schema_df.columns)
    print("✓ TABLE_NAME column present:", "TABLE_NAME" in schema_df.columns)
    print("✓ IS_NULLABLE column present:", "IS_NULLABLE" in schema_df.columns)

    # Verify FULL_DATA_TYPE values
    print("\nFULL_DATA_TYPE values:")
    for _, row in schema_df.iterrows():
        print(f"  {row['TABLE_NAME']}.{row['COLUMN_NAME']} → {row['FULL_DATA_TYPE']}")

    print("\n✓ SUCCESS: Oracle (Simulator) schema detection is working!")

except Exception as e:
    print(f"✗ Oracle (Simulator) test failed: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
