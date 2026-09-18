# 🔷 Oracle Database Configuration Guide

## ✅ Status: Oracle Connection Ready!

Your Oracle AI Database 26ai Free Edition is now configured and ready for data migration.

---

## 📋 Current Configuration

**File:** `.env`

```
ORACLE_HOST=localhost
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=FREEPDB1
ORACLE_SID=FREE
ORACLE_USERNAME=sys
ORACLE_PASSWORD=Sai99sai
ORACLE_THICK_MODE=false
ORACLE_USE_SIMULATOR=false
```

---

## 🚀 Quick Start

### 1. Test Connection
```bash
python test_oracle_connection.py
```

Expected output:
```
✅ CONNECTION SUCCESSFUL!
✅ Found XXXX tables
```

### 2. Start the Dashboard
```bash
streamlit run dashboard/app.py
```

### 3. Select Data Source
In the dashboard:
1. Go to **Step 1: Source Connection**
2. Select **"Oracle (Real)"**
3. Click **"Connect to Real Oracle"**
4. Proceed to schema discovery

---

## 📊 What You Can Do Now

### Phase 1-3: Discovery & Analysis
- ✅ **Schema Discovery** — Discover all tables and columns from your Oracle database
- ✅ **Data Type Analysis** — Analyze data types and compatibility
- ✅ **Automatic Mapping** — AI-powered table/column mapping to Azure SQL

### Phase 4-6: Planning & Approval
- ✅ **AI Mapping** — Intelligent schema mapping suggestions
- ✅ **SQL Generation** — Auto-generate Azure SQL DDL statements
- ✅ **Human Approval** — Review and approve migrations before execution

### Phase 7-9: Execution & Validation
- ✅ **Migration Execution** — Execute approved migrations
- ✅ **Data Validation** — Verify data integrity after migration
- ✅ **Report Generation** — Generate detailed migration reports

---

## 🔧 Troubleshooting

### Connection Issues

**Error: "Service not registered with listener"**
- Check service name in `.env` (try: FREEPDB, FREEPDB1, or FREE)
- Verify listener is running: `lsnrctl status`

**Error: "Connection as SYS should be as SYSDBA"**
- ✅ This is now handled automatically with mode="SYSDBA"

**Error: "Cannot connect to database"**
- Verify Oracle database is running
- Check firewall (port 1521 must be open)
- Verify host and port are correct

### Quick Diagnostics
```bash
# Check Oracle client version
python -c "import oracledb; print(oracledb.clientversion())"

# Test connection manually
python test_oracle_connection.py
```

---

## 📁 Related Files

| File | Purpose |
|------|---------|
| `.env` | Configuration with Oracle credentials |
| `connectors/oracle_connector.py` | Oracle database connector class |
| `test_oracle_connection.py` | Connection test script |
| `dashboard/pages/1_Source_Connection.py` | Streamlit connection UI |
| `config/config.py` | Application configuration |

---

## 🔐 Security Notes

⚠️ **Important:**
- `.env` file contains credentials — never commit to version control
- Add `.env` to `.gitignore` (already configured)
- Consider using Azure Key Vault for production

---

## 🎯 Next Steps

1. ✅ **Test Oracle connection** → `python test_oracle_connection.py`
2. ✅ **Start dashboard** → `streamlit run dashboard/app.py`
3. ✅ **Discover schema** → Use Step 2: Schema Discovery
4. ✅ **Analyze data types** → Use Step 3: Datatype Analysis
5. ✅ **Generate mappings** → Use Step 4: AI Mapping
6. ✅ **Review & approve** → Use Step 6: Human Approval
7. ✅ **Execute migration** → Use Step 7: Migration
8. ✅ **Validate data** → Use Step 8: Validation
9. ✅ **Generate report** → Use Step 9: Report

---

## 📞 Support Resources

- [Oracle oracledb Documentation](https://python-oracledb.readthedocs.io/)
- [Oracle Database 26ai Free Edition](https://www.oracle.com/database/free/)
- [Azure SQL Migration Guide](https://learn.microsoft.com/en-us/azure/azure-sql/migration-guides/)

---

**Last Updated:** 2026-08-10  
**Status:** ✅ Ready for Production
