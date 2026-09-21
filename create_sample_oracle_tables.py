"""
Create Sample Oracle Test Tables with Data

This script creates sample tables in Oracle for testing the migration pipeline.
Run with: python create_sample_oracle_tables.py
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from config.config import Config
from connectors.oracle_connector import OracleConnector


def get_oracle_mode() -> str:
    requested_mode = os.getenv("ORACLE_MODE", "AUTO").strip().upper()
    if requested_mode in ("", "AUTO"):
        return "SYSDBA" if (Config.ORACLE_USERNAME or "").strip().lower() == "sys" else "NORMAL"
    return requested_mode

def create_sample_tables():
    """Create sample Oracle tables for testing."""
    
    print("\n" + "="*70)
    print("🔷 CREATING SAMPLE ORACLE TABLES FOR TESTING")
    print("="*70)
    
    try:
        # Connect to Oracle
        connector = OracleConnector(
            host=Config.ORACLE_HOST,
            port=Config.ORACLE_PORT,
            service_name=Config.ORACLE_SERVICE_NAME,
            username=Config.ORACLE_USERNAME,
            password=Config.ORACLE_PASSWORD,
            mode=get_oracle_mode()
        )
        
        conn = connector.connect()
        cursor = conn.cursor()
        
        print("\n✅ Connected to Oracle Database")
        
        # Drop existing tables if they exist
        print("\n🔄 Cleaning up existing test tables...")
        try:
            cursor.execute("DROP TABLE ORDERS")
            cursor.execute("DROP TABLE PRODUCT")
            cursor.execute("DROP TABLE CUSTOMER")
            conn.commit()
            print("   Dropped existing tables")
        except:
            pass
        
        # Create CUSTOMER table
        print("\n📝 Creating CUSTOMER table...")
        cursor.execute("""
            CREATE TABLE CUSTOMER (
                CUSTOMER_ID NUMBER(10) PRIMARY KEY,
                CUSTOMER_NAME VARCHAR2(100) NOT NULL,
                EMAIL VARCHAR2(100),
                CITY VARCHAR2(50),
                CREATED_DATE DATE NOT NULL
            )
        """)
        
        # Create PRODUCT table
        print("📝 Creating PRODUCT table...")
        cursor.execute("""
            CREATE TABLE PRODUCT (
                PRODUCT_ID NUMBER(10) PRIMARY KEY,
                PRODUCT_NAME VARCHAR2(100),
                CATEGORY VARCHAR2(50),
                PRICE NUMBER(10,2),
                HIGH_PRECISION_VALUE NUMBER(38,20)
            )
        """)
        
        # Create ORDERS table
        print("📝 Creating ORDERS table...")
        cursor.execute("""
            CREATE TABLE ORDERS (
                ORDER_ID NUMBER(10) PRIMARY KEY,
                CUSTOMER_ID NUMBER(10) NOT NULL,
                PRODUCT_ID NUMBER(10) NOT NULL,
                ORDER_DATE DATE,
                QUANTITY NUMBER(5),
                TOTAL_AMOUNT NUMBER(12,2),
                FOREIGN KEY (CUSTOMER_ID) REFERENCES CUSTOMER(CUSTOMER_ID),
                FOREIGN KEY (PRODUCT_ID) REFERENCES PRODUCT(PRODUCT_ID)
            )
        """)
        
        conn.commit()
        print("\n✅ Tables created successfully!")
        
        # Insert sample data
        print("\n📊 Inserting sample data...")
        
        # Customer data
        customers = [
            (1, 'John Doe', 'john@example.com', 'New York'),
            (2, 'Jane Smith', 'jane@example.com', 'London'),
            (3, 'Bob Johnson', 'bob@example.com', 'Sydney'),
            (4, 'Alice Williams', 'alice@example.com', 'Toronto'),
            (5, 'Charlie Brown', 'charlie@example.com', 'Berlin'),
        ]
        
        for cust in customers:
            cursor.execute(
                "INSERT INTO CUSTOMER (CUSTOMER_ID, CUSTOMER_NAME, EMAIL, CITY, CREATED_DATE) "
                "VALUES (:1, :2, :3, :4, SYSDATE)",
                cust
            )
        
        # Product data
        products = [
            (101, 'Laptop', 'Electronics', 999.99, 999.123456789012345678),
            (102, 'Mouse', 'Electronics', 29.99, 29.987654321098765432),
            (103, 'Keyboard', 'Electronics', 79.99, 79.456789012345678901),
            (104, 'Monitor', 'Electronics', 299.99, 299.555555555555555555),
            (105, 'Headphones', 'Audio', 149.99, 149.999999999999999999),
        ]
        
        for prod in products:
            cursor.execute(
                "INSERT INTO PRODUCT (PRODUCT_ID, PRODUCT_NAME, CATEGORY, PRICE, HIGH_PRECISION_VALUE) "
                "VALUES (:1, :2, :3, :4, :5)",
                prod
            )
        
        # Orders data
        orders = [
            (1001, 1, 101, 1, 999.99),
            (1002, 2, 102, 2, 59.98),
            (1003, 3, 103, 1, 79.99),
            (1004, 1, 104, 1, 299.99),
            (1005, 4, 105, 3, 449.97),
            (1006, 5, 101, 1, 999.99),
            (1007, 2, 103, 2, 159.98),
            (1008, 3, 102, 5, 149.95),
        ]
        
        for order in orders:
            cursor.execute(
                "INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, PRODUCT_ID, ORDER_DATE, QUANTITY, TOTAL_AMOUNT) "
                "VALUES (:1, :2, :3, SYSDATE, :4, :5)",
                order
            )
        
        conn.commit()
        print("✅ Sample data inserted!")
        
        # Verify data
        print("\n📋 Verifying sample data...")
        
        cursor.execute("SELECT COUNT(*) FROM CUSTOMER")
        cust_count = cursor.fetchone()[0]
        print(f"   CUSTOMER rows: {cust_count}")
        
        cursor.execute("SELECT COUNT(*) FROM PRODUCT")
        prod_count = cursor.fetchone()[0]
        print(f"   PRODUCT rows: {prod_count}")
        
        cursor.execute("SELECT COUNT(*) FROM ORDERS")
        order_count = cursor.fetchone()[0]
        print(f"   ORDERS rows: {order_count}")
        
        # Display sample rows
        print("\n📊 Sample CUSTOMER data:")
        cursor.execute("SELECT CUSTOMER_ID, CUSTOMER_NAME, EMAIL, CITY FROM CUSTOMER WHERE ROWNUM <= 3")
        for row in cursor.fetchall():
            print(f"   {row}")
        
        print("\n📊 Sample PRODUCT data:")
        cursor.execute("SELECT PRODUCT_ID, PRODUCT_NAME, CATEGORY, PRICE FROM PRODUCT WHERE ROWNUM <= 3")
        for row in cursor.fetchall():
            print(f"   {row}")
        
        print("\n📊 Sample ORDERS data:")
        cursor.execute("SELECT ORDER_ID, CUSTOMER_ID, PRODUCT_ID, QUANTITY, TOTAL_AMOUNT FROM ORDERS WHERE ROWNUM <= 3")
        for row in cursor.fetchall():
            print(f"   {row}")
        
        cursor.close()
        connector.disconnect()
        
        print("\n" + "="*70)
        print("✅ SAMPLE TABLES CREATED SUCCESSFULLY!")
        print("="*70)
        print("\nYou can now use these tables in the migration pipeline:")
        print("  • CUSTOMER (5 rows)")
        print("  • PRODUCT (5 rows)")
        print("  • ORDERS (8 rows)")
        print("\nNext steps:")
        print("  1. Go to Step 1: Source Connection")
        print("  2. Select 'Oracle (Real)'")
        print("  3. Connect to Oracle")
        print("  4. Go to Step 2: Schema Discovery")
        print("="*70)
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    success = create_sample_tables()
    sys.exit(0 if success else 1)
