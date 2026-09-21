"""
Oracle Database Connection Test

Tests connectivity to Oracle database using credentials from .env
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
    """Pick a safe Oracle auth mode based on env and username."""
    requested_mode = os.getenv("ORACLE_MODE", "AUTO").strip().upper()
    if requested_mode in ("", "AUTO"):
        return "SYSDBA" if (Config.ORACLE_USERNAME or "").strip().lower() == "sys" else "NORMAL"
    return requested_mode


def test_oracle_connection():
    """Test Oracle database connection."""

    print("\n" + "="*60)
    print("🔶 ORACLE DATABASE CONNECTION TEST")
    print("="*60)

    print("\n📋 Configuration:")
    print(f"  Host:           {Config.ORACLE_HOST}")
    print(f"  Port:           {Config.ORACLE_PORT}")
    print(f"  Service Name:   {Config.ORACLE_SERVICE_NAME}")
    print(f"  SID:            {Config.ORACLE_SID}")
    print(f"  Username:       {Config.ORACLE_USERNAME}")
    print(f"  Mode:           {get_oracle_mode()}")
    print(f"  Thick Mode:     {Config.ORACLE_THICK_MODE}")
    print(f"  Use Simulator:  {Config.ORACLE_USE_SIMULATOR}")

    if Config.ORACLE_USE_SIMULATOR:
        print("\n⚠️  SIMULATOR MODE ENABLED - Using mock data only")
        print("   Set ORACLE_USE_SIMULATOR=false in .env to connect to real database\n")
        return

    print("\n⏳ Attempting connection...")

    try:
        connector = OracleConnector(
            host=Config.ORACLE_HOST,
            port=Config.ORACLE_PORT,
            service_name=Config.ORACLE_SERVICE_NAME if Config.ORACLE_SERVICE_NAME else None,
            sid=Config.ORACLE_SID if Config.ORACLE_SID else None,
            username=Config.ORACLE_USERNAME,
            password=Config.ORACLE_PASSWORD,
            mode=get_oracle_mode(),
            thick_mode=Config.ORACLE_THICK_MODE,
            lib_dir=Config.ORACLE_CLIENT_LIB_DIR if Config.ORACLE_CLIENT_LIB_DIR else None
        )

        connection = connector.connect()
        print("✅ CONNECTION SUCCESSFUL!")

        # Test: Get list of tables
        print("\n📊 Discovering schema...")
        tables = connector.discover_tables()
        print(f"✅ Found {len(tables)} tables:")

        for table in tables[:10]:  # Show first 10
            print(f"   - {table}")

        if len(tables) > 10:
            print(f"   ... and {len(tables) - 10} more")

        # Test: Get schema for first table
        if tables:
            first_table = tables[0]
            print(f"\n🔍 Schema for table '{first_table}':")

            schema = connector.get_table_structure(first_table)
            for col in schema["columns"]:
                nullable = "NULL" if col["nullable"] == "Y" else "NOT NULL"
                print(f"   - {col['column_name']:<30} {col['data_type']:<15} {nullable}")

            # Get row count
            try:
                row_count = connector.get_row_count(first_table)
                print(f"\n📈 Row count: {row_count:,}")
            except Exception as e:
                print(f"\n⚠️  Could not get row count: {str(e)}")

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\n🚀 You can now run the Streamlit dashboard:")
        print("   streamlit run dashboard/app.py")
        print("="*60 + "\n")

        connector.disconnect()

    except Exception as e:
        print(f"\n❌ CONNECTION FAILED!")
        print(f"Error: {str(e)}")
        print("\n" + "="*60)
        print("🔧 TROUBLESHOOTING STEPS:")
        print("="*60)
        print("""
1. Verify Oracle database is running:
   - Check if listener is active (lsnrctl status)
   - Check if database is open (sqlplus / as sysdba)

2. Verify .env credentials:
   - Open .env file and confirm ORACLE_* settings
   - Ensure password matches your Oracle installation

3. Verify network connectivity:
   - Test: ping localhost
   - Test: tnsping FREEPDB (or your service name)

4. For Oracle AI Database 26ai Free:
   - Default service: FREEPDB
   - Default port: 1521
   - Admin password: (what you set during installation)

5. Check Python oracle client:
   - Run: python -c "import oracledb; print(oracledb.clientversion())"
   - Should return Oracle client version

6. For thick mode issues:
   - Set ORACLE_THICK_MODE=false (default, recommended)
   - Thin mode doesn't require Oracle client libraries
        """)
        print("="*60 + "\n")


if __name__ == "__main__":
    test_oracle_connection()
