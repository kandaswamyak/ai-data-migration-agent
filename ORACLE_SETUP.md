# Oracle Database Configuration Guide

## ✅ Current Setup Status

Your Oracle AI Database 26ai Free installation is ready to configure!

### Credentials Configured
- **Username:** `sys` (Admin account)
- **Password:** `Sai99sai`
- **Service Name:** `FREEPDB` (Free edition PDB)
- **Port:** `1521` (Default listener)
- **Connection String:** `localhost:1521/FREEPDB`

---

## 🚀 Quick Start

### Step 1: Test Oracle Connection

Run the connection test to verify everything works:

```bash
python test_oracle_connection.py
```

**Expected output:**
```
✅ CONNECTION SUCCESSFUL!
📊 Discovering schema...
✅ Found X tables:
   - (your tables here)
```

### Step 2: Launch Dashboard

Once connection test passes:

```bash
streamlit run dashboard/app.py
```

### Step 3: Select Oracle Source

1. Go to **Step 1: Source Connection** page
2. Select **"Oracle (Real)"** from dropdown
3. Review pre-filled credentials from `.env`
4. Click **"Connect to Real Oracle"**

---

## 📋 Configuration Files

### `.env` - Connection Credentials

Located at project root. Contains:

```env
ORACLE_HOST=localhost
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=FREEPDB
ORACLE_USERNAME=sys
ORACLE_PASSWORD=Sai99sai
ORACLE_THICK_MODE=false
ORACLE_USE_SIMULATOR=false
```

**⚠️ Security Warning:**
- Never commit `.env` to version control (already in `.gitignore`)
- Use strong passwords in production
- Consider using Azure Key Vault for production deployments

### `config/config.py` - Application Config

Automatically loads from `.env` via `os.getenv()`:

```python
Config.ORACLE_HOST        # localhost
Config.ORACLE_PORT        # 1521
Config.ORACLE_SERVICE_NAME # FREEPDB
Config.ORACLE_USERNAME    # sys
Config.ORACLE_PASSWORD    # Sai99sai
```

### `connectors/oracle_connector.py` - Driver

Python library: **oracledb** (Oracle's recommended thin client)

Features:
- ✅ No Oracle client libraries required (thin mode)
- ✅ Modern async support
- ✅ Type hints for IDE support
- ✅ Connection pooling ready

---

## 🔧 Connection Methods

### Method 1: Service Name (Recommended)

```python
OracleConnector(
    host="localhost",
    port=1521,
    service_name="FREEPDB",  # ← Use this for Oracle 12c+
    username="sys",
    password="Sai99sai"
)
```

### Method 2: SID (Legacy)

```python
OracleConnector(
    host="localhost",
    port=1521,
    sid="FREE",  # ← Old connection method
    username="sys",
    password="Sai99sai"
)
```

### Method 3: TNS Entry

```python
# If using tnsnames.ora file:
service_name = "FREEPDB_TNS"  # Defined in tnsnames.ora
```

---

## ✨ Key Features Unlocked

Once connected, you can:

### 1. **Schema Discovery**
   - Auto-discover all tables in Oracle
   - Capture column names, data types, nullability
   - Export to JSON for analysis

### 2. **Data Type Mapping**
   - Map Oracle types to Azure SQL types
   - Handle precision/scale conversions
   - Detect compatibility issues

### 3. **SQL Generation**
   - Generate CREATE TABLE DDL for Azure SQL
   - Apply data type transformations
   - Preserve constraints & nullability

### 4. **Migration Preview**
   - See generated SQL before execution
   - Validate mapping rules
   - Get risk assessment

---

## 🐛 Troubleshooting

### Error: "Oracle connection failed"

**Check 1: Is Oracle Running?**
```bash
# Windows Command Line
oradim -list

# Or check listener
lsnrctl status
```

**Check 2: Verify Credentials**
- Username: `sys` (requires SYSDBA role)
- Password: Must match what you set during Oracle installation
- Service: `FREEPDB` for Oracle AI Database 26ai Free

**Check 3: Network Connectivity**
```bash
# Test localhost
ping localhost

# Test Oracle port
netstat -an | find "1521"
```

**Check 4: Oracle Client**
```bash
# Verify oracledb installation
python -c "import oracledb; print(oracledb.clientversion())"
```

### Error: "ORA-01031: insufficient privileges"

**Solution:** Use `sys` account with correct connection mode:
```python
OracleConnector(
    username="sys",
    password="Sai99sai",
    # Not needed for thin mode - relies on sys privileges
)
```

### Error: "Service name not found"

**Solution:** Use correct service name for your Oracle version:
- **Oracle 26ai Free:** `FREEPDB` ✅
- **Oracle 23ai Free:** `FREE` or `FREEPDB`
- **Oracle 21c XE:** `XE`

---

## 📊 Common Scenarios

### Scenario 1: First-Time Setup

```bash
# 1. Verify .env has correct credentials
cat .env | grep ORACLE

# 2. Test connection
python test_oracle_connection.py

# 3. If successful, launch dashboard
streamlit run dashboard/app.py

# 4. Go to Step 1: Source Connection
# 5. Select "Oracle (Real)" and connect
```

### Scenario 2: Multiple Oracle Instances

Edit `.env` to connect to different instances:

```env
# Production Oracle
ORACLE_HOST=prod-oracle.example.com
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=PRODDB
ORACLE_USERNAME=migration_user
ORACLE_PASSWORD=secure_password
```

### Scenario 3: Using Different Schema

Modify `connectors/oracle_connector.py` discovery queries:

```python
def discover_schema(self, schema: Optional[str] = None) -> pd.DataFrame:
    # Pass schema name to restrict discovery
    tables = self.discover_tables(schema="HR")  # Only HR schema
```

---

## 🔐 Production Deployment Checklist

- [ ] Use service account (not `sys` for normal operations)
- [ ] Store credentials in Azure Key Vault
- [ ] Enable SSL/TLS for connections
- [ ] Use connection pooling for performance
- [ ] Set up audit logging for migrations
- [ ] Test on staging database first
- [ ] Configure database backups
- [ ] Set up monitoring/alerting

---

## 📚 Additional Resources

### Oracle Database References
- [Oracle python-oracledb Documentation](https://python-oracledb.readthedocs.io/)
- [Oracle Database 26c Free Documentation](https://docs.oracle.com/en/database/)
- [Oracle AI Database 26ai Free Release Notes](https://docs.oracle.com/en/database/oracle/oracle-database/26/releasenotes/)

### Data Migration Best Practices
- Validate schema before migration
- Test data type conversions
- Perform pilot migration to Azure SQL
- Set up validation checks post-migration
- Document all transformations

---

## ✅ Next Steps

1. **Test Connection:** `python test_oracle_connection.py`
2. **Launch Dashboard:** `streamlit run dashboard/app.py`
3. **Step 1:** Connect to Oracle (Real) using credentials
4. **Step 2:** Discover schema and review tables
5. **Step 3:** Analyze data types (AI-powered optional)
6. **Step 4:** Map columns to target Azure SQL types
7. **Step 5:** Generate CREATE TABLE DDL
8. **Step 6:** Get human approval
9. **Step 7:** Execute migration
10. **Step 8:** Validate data integrity
11. **Step 9:** Generate migration report

---

**Questions?** Check the `.env` configuration or review `connectors/oracle_connector.py` for connection details.
