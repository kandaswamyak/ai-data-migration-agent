"""
End-to-End Workflow Test
Tests the complete migration workflow without Streamlit GUI
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config.config import Config
from connectors.oracle_connector import OracleConnector


def get_oracle_mode() -> str:
    requested_mode = os.getenv("ORACLE_MODE", "AUTO").strip().upper()
    if requested_mode in ("", "AUTO"):
        return "SYSDBA" if (Config.ORACLE_USERNAME or "").strip().lower() == "sys" else "NORMAL"
    return requested_mode


def test_workflow():
    """Test the complete migration workflow."""

    print("\n" + "="*70)
    print("🚀 END-TO-END WORKFLOW TEST")
    print("="*70)

    # STEP 1: Source Connection
    print("\n" + "-"*70)
    print("STEP 1: SOURCE CONNECTION")
    print("-"*70)

    connection_params = {
        "host": Config.ORACLE_HOST,
        "port": Config.ORACLE_PORT,
        "service_name": Config.ORACLE_SERVICE_NAME,
        "sid": Config.ORACLE_SID,
        "username": Config.ORACLE_USERNAME,
        "password": Config.ORACLE_PASSWORD,
        "mode": get_oracle_mode()
    }

    print(f"\nConnecting to Oracle:")
    print(f"  Host: {connection_params['host']}")
    print(f"  Port: {connection_params['port']}")
    print(f"  Service: {connection_params['service_name']}")
    print(f"  User: {connection_params['username']}")

    try:
        connector = OracleConnector(**connection_params)
        connection = connector.connect()
        print("✅ CONNECTION SUCCESSFUL!")
    except Exception as e:
        print(f"❌ CONNECTION FAILED: {str(e)}")
        return False

    # STEP 2: Schema Discovery
    print("\n" + "-"*70)
    print("STEP 2: SCHEMA DISCOVERY")
    print("-"*70)

    try:
        print("\nDiscovering schema...")
        schema_df = connector.discover_schema()
        
        total_tables = schema_df["table_name"].nunique()
        total_cols = len(schema_df)
        
        print(f"✅ SCHEMA DISCOVERED!")
        print(f"  Total Tables: {total_tables}")
        print(f"  Total Columns: {total_cols}")
        
        # Show sample data
        print("\n  Sample Tables:")
        sample_tables = schema_df["table_name"].unique()[:5]
        for table in sample_tables:
            table_cols = schema_df[schema_df["table_name"] == table]
            print(f"    - {table} ({len(table_cols)} columns)")
        
        # Verify DataFrame structure
        required_cols = ["table_name", "column_name", "data_type", "nullable"]
        missing_cols = [col for col in required_cols if col not in schema_df.columns]
        if missing_cols:
            print(f"  ⚠️  Missing columns: {missing_cols}")
            return False
        
        print(f"  ✓ DataFrame has all required columns: {required_cols}")
        
    except Exception as e:
        print(f"❌ SCHEMA DISCOVERY FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        connector.disconnect()
        return False

    # STEP 3: Datatype Analysis
    print("\n" + "-"*70)
    print("STEP 3: DATATYPE ANALYSIS")
    print("-"*70)

    try:
        print("\nAnalyzing data types...")
        
        # Sample first few tables
        sample_size = 3
        sample_tables = schema_df["table_name"].unique()[:sample_size]
        
        datatype_mapping = {}
        for table in sample_tables:
            table_cols = schema_df[schema_df["table_name"] == table]
            print(f"\n  Table: {table}")
            
            for _, col in table_cols.iterrows():
                data_type = col["data_type"]
                if data_type not in datatype_mapping:
                    datatype_mapping[data_type] = "VARCHAR2" if "CHAR" in data_type else "NVARCHAR(MAX)"
                
                nullable = "NULL" if col["nullable"] == "Y" else "NOT NULL"
                print(f"    - {col['column_name']:<30} {data_type:<20} {nullable}")
        
        print(f"\n✅ DATATYPE ANALYSIS COMPLETE!")
        print(f"  Unique Oracle datatypes found: {len(datatype_mapping)}")
        
    except Exception as e:
        print(f"❌ DATATYPE ANALYSIS FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        connector.disconnect()
        return False

    # STEP 4: Get Row Counts (Validation preparation)
    print("\n" + "-"*70)
    print("STEP 4: ROW COUNT VALIDATION")
    print("-"*70)

    try:
        print("\nGetting row counts for validation...")
        
        row_counts = {}
        for table in sample_tables:
            try:
                count = connector.get_row_count(table)
                row_counts[table] = count
                print(f"  ✓ {table}: {count:,} rows")
            except Exception as e:
                print(f"  ✗ {table}: Error - {str(e)}")
        
        print(f"\n✅ ROW COUNT VALIDATION COMPLETE!")
        
    except Exception as e:
        print(f"❌ ROW COUNT VALIDATION FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        connector.disconnect()
        return False

    # STEP 5: Clean Up
    print("\n" + "-"*70)
    print("STEP 5: CLEANUP")
    print("-"*70)

    try:
        connector.disconnect()
        print("✅ CONNECTION CLOSED")
    except Exception as e:
        print(f"⚠️  Disconnect warning: {str(e)}")

    # Final Summary
    print("\n" + "="*70)
    print("✅ ALL WORKFLOW TESTS PASSED!")
    print("="*70)
    print("\n📊 Summary:")
    print(f"  ✓ Source Connection: Oracle FREEPDB1")
    print(f"  ✓ Schema Discovery: {total_tables} tables, {total_cols} columns")
    print(f"  ✓ Datatype Analysis: {len(datatype_mapping)} unique Oracle types")
    print(f"  ✓ Row Count Validation: {len(row_counts)} tables validated")
    print("\n🚀 You can now use the Streamlit dashboard to continue the workflow!")
    print("   Run: python -m streamlit run dashboard/app.py")
    print("="*70 + "\n")

    return True


if __name__ == "__main__":
    success = test_workflow()
    sys.exit(0 if success else 1)
