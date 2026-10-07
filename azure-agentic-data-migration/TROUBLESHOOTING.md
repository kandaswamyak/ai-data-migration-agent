# 🔧 Azure Agentic Data Migration — Troubleshooting Guide

> **Version:** 1.0 · **Last Updated:** 2026-09-03  
> **Audience:** Developers, DevOps engineers, DBAs, and support staff  
> **Prerequisite:** Familiarity with the architecture in [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Table of Contents

1. [Quick Diagnostic Checklist](#1-quick-diagnostic-checklist)
2. [Agent Not Responding](#2-agent-not-responding)
3. [Schema Discovery Failures](#3-schema-discovery-failures)
4. [ADF Pipeline Failures](#4-adf-pipeline-failures)
5. [Logic Apps Failures](#5-logic-apps-failures)
6. [Oracle Connectivity Issues](#6-oracle-connectivity-issues)
7. [SQL Server Connectivity Issues](#7-sql-server-connectivity-issues)
8. [Azure SQL Target Issues](#8-azure-sql-target-issues)
9. [Approval Workflow Issues](#9-approval-workflow-issues)
10. [Validation Failures](#10-validation-failures)
11. [Key Vault Access Denied](#11-key-vault-access-denied)
12. [Managed Identity Issues](#12-managed-identity-issues)
13. [Self-Hosted Integration Runtime Issues](#13-self-hosted-integration-runtime-issues)
14. [Network & Private Endpoint Issues](#14-network--private-endpoint-issues)
15. [Performance Issues](#15-performance-issues)
16. [Checking Logs in Application Insights](#16-checking-logs-in-application-insights)
17. [Emergency Procedures](#17-emergency-procedures)
18. [Support Escalation](#18-support-escalation)

---

## 1. Quick Diagnostic Checklist

Before diving into specific issues, run through this rapid assessment:

| Check | Command / Action | Expected |
|-------|-----------------|----------|
| SHIR status | ADF Portal → Manage → Integration Runtimes | 🟢 Running |
| Logic Apps status | Azure Portal → each Logic App → Overview | 🟢 Running |
| Key Vault access | `az keyvault secret show --vault-name kv-migration-poc --name oracle-host` | Returns value |
| ADF linked services | ADF Studio → Manage → Linked Services → Test Connection | ✅ Connected |
| Azure SQL reachable | `sqlcmd` or Azure Data Studio → connect to `sql-migration-poc` | Connected |
| Agent responsive | AI Foundry Playground → send "hello" | Agent replies |
| VPN status (if used) | `az network vpn-connection show --name conn-onprem ...` | Connected |
| Source DB reachable from SHIR | RDP to SHIR VM → `tnsping` (Oracle) or `sqlcmd` (SQL Server) | Success |

---

## 2. Agent Not Responding

### Symptom
The agent in AI Foundry Playground does not respond, responds with errors, or the conversation seems stuck.

### Possible Causes & Solutions

#### 2.1 Model Deployment Issue

**Check:**
```bash
az cognitiveservices account deployment show \
  --name oai-migration-poc \
  --resource-group rg-data-migration-poc \
  --deployment-name gpt-41-migration \
  --query provisioningState -o tsv
```

**Expected:** `Succeeded`

**If failed:**
- Verify your Azure OpenAI quota includes GPT-4.1 in the selected region
- Check region availability: GPT-4.1 is available in East US 2, West US 3, Sweden Central
- Submit a quota increase request if needed

#### 2.2 Agent Configuration Issue

**Check in AI Foundry Portal:**
1. Navigate to your project → Agents → `data-migration-agent`
2. Verify the model deployment is selected (`gpt-41-migration`)
3. Verify system instructions are not empty
4. Verify tools (function definitions) are configured — should see 5 tools

**Fix:** Re-upload system instructions and tool definitions per Section 12 of DEPLOYMENT.md.

#### 2.3 Token Quota Exceeded

**Symptoms:** Agent returns `429 Too Many Requests` or "Rate limit exceeded"

**Check:**
```bash
az cognitiveservices account show \
  --name oai-migration-poc \
  --resource-group rg-data-migration-poc \
  --query "properties.quotaLimit"
```

**Fix:**
- Wait 60 seconds and retry (rate limits reset per minute)
- Increase the TPM (Tokens Per Minute) allocation:
  ```bash
  az cognitiveservices account deployment create \
    --name oai-migration-poc \
    --resource-group rg-data-migration-poc \
    --deployment-name gpt-41-migration \
    --model-name gpt-4.1 \
    --model-version "2025-04-14" \
    --model-format OpenAI \
    --sku-capacity 120 \
    --sku-name Standard
  ```

#### 2.4 Tool Calling Failures

**Symptom:** Agent says it's calling a tool but nothing happens, or returns a generic error.

**Check:**
1. Verify Logic App HTTP trigger URLs in Key Vault are not `PLACEHOLDER`
2. Test a Logic App trigger URL directly:
   ```bash
   curl -X POST "<logic-app-url>" \
     -H "Content-Type: application/json" \
     -d '{"jobId":"test-123","sourceType":"Oracle"}'
   ```
3. Check Logic App run history for incoming requests

**Fix:** Update Key Vault secrets with actual Logic App trigger URLs (see DEPLOYMENT.md Section 11.8).

---

## 3. Schema Discovery Failures

### 3.1 "No tables found" or Empty Schema

**Possible causes:**
- Wrong schema/owner filter specified
- Service account lacks `SELECT` privileges on the catalog views
- Database is empty

**Diagnosis — Oracle:**
```sql
-- Run on the Oracle source (as the migration user)
SELECT COUNT(*) FROM ALL_TAB_COLUMNS WHERE OWNER = 'HR';
-- If 0: the user doesn't have access to this schema

-- Check what schemas the user can see:
SELECT DISTINCT OWNER FROM ALL_TAB_COLUMNS ORDER BY OWNER;
```

**Diagnosis — SQL Server:**
```sql
-- Run on the SQL Server source
SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_CATALOG = 'MigrationDemo';
```

**Fix:**
- Grant `SELECT_CATALOG_ROLE` (Oracle) or `db_datareader` (SQL Server) to the migration account
- Verify the schema name is correct (case-sensitive in Oracle)

### 3.2 Discovery Times Out

**Symptom:** Logic App or ADF pipeline times out during schema discovery.

**Possible causes:**
- Very large database with thousands of tables
- Slow network connection to on-prem
- SHIR VM is overloaded

**Fix:**
- Use the `schemaFilter` parameter to discover one schema at a time
- Increase the Logic App timeout (default: 120 seconds → increase to 300 seconds)
- Check SHIR VM CPU/memory — scale up if needed

### 3.3 "ORA-12514: TNS:listener does not currently know of service requested"

**Cause:** Wrong Oracle service name.

**Fix:**
```bash
# From the SHIR VM, list available services:
tnsping <oracle-host>:1521

# Or query the listener:
lsnrctl status
```
Common service names: `ORCL`, `FREEPDB1`, `XE`, `XEPDB1`. Update the Key Vault secret `oracle-service-name`.

---

## 4. ADF Pipeline Failures

### 4.1 Checking Pipeline Run Status

```bash
# List recent failed pipeline runs
az datafactory pipeline-run query-by-factory \
  --resource-group rg-data-migration-poc \
  --factory-name adf-migration-poc \
  --last-updated-after "2026-09-01T00:00:00Z" \
  --filters operand="Status" operator="Equals" values="Failed"
```

**Or in ADF Studio:** Monitor → Pipeline Runs → filter by "Failed"

### 4.2 "UserErrorInvalidDataTypeInSource"

**Cause:** ADF cannot handle a specific source data type.

**Common culprits:**
- Oracle `XMLTYPE` — not supported by ADF Oracle connector
- Oracle `SDO_GEOMETRY` — spatial types need special handling
- SQL Server `geography`/`geometry` — not directly copyable

**Fix:**
- Exclude unsupported columns from the migration
- Create a source query that casts unsupported types:
  ```sql
  SELECT CAST(xml_col AS CLOB) AS xml_col, ... FROM source_table
  ```

### 4.3 "IntegrationRuntimeNotAvailable"

**Cause:** Self-Hosted Integration Runtime is offline.

**Check:**
```bash
az datafactory integration-runtime show \
  --resource-group rg-data-migration-poc \
  --factory-name adf-migration-poc \
  --integration-runtime-name ir-onprem-shir \
  --query state -o tsv
```

**Expected:** `Online`

**Fix:**
1. RDP into the SHIR VM
2. Open **Integration Runtime Configuration Manager**
3. Check status — if "Disconnected":
   ```powershell
   # Restart the SHIR service
   Restart-Service DIAHostService
   ```
4. If still offline, re-register with a new authentication key:
   ```bash
   az datafactory integration-runtime list-auth-key \
     --resource-group rg-data-migration-poc \
     --factory-name adf-migration-poc \
     --integration-runtime-name ir-onprem-shir
   ```

### 4.4 "CopyActivity Failed: Timeout"

**Cause:** Large table copy exceeded the default timeout.

**Fix:**
- Increase the activity timeout in the ADF pipeline (Settings → Timeout)
- For very large tables (>10M rows), enable partitioned copy:
  - Use physical partitions (Oracle) or dynamic range partitioning
  - Set `parallelCopies: 8` in the copy activity settings

### 4.5 "MappingColumn not found in source"

**Cause:** Column name mismatch between source schema and ADF dataset.

**Fix:**
- Verify column names haven't changed since schema discovery
- Re-run schema discovery
- Check for case sensitivity (Oracle columns are uppercase by default)

### 4.6 Data Truncation Errors

**Symptom:** `String or binary data would be truncated`

**Cause:** Source column contains data larger than the target column can hold.

**Fix:**
- Check the source data:
  ```sql
  -- Oracle
  SELECT MAX(LENGTH(column_name)) FROM schema.table_name;
  
  -- SQL Server
  SELECT MAX(LEN(column_name)) FROM dbo.table_name;
  ```
- Increase the target column size in the DDL (e.g., `NVARCHAR(100)` → `NVARCHAR(255)`)
- Ask the agent to regenerate the plan with: "Increase the size of [column] to NVARCHAR(500)"

---

## 5. Logic Apps Failures

### 5.1 Checking Logic App Run History

**Azure Portal:** Navigate to Logic App → Overview → **Run history**

Each run shows:
- Trigger status
- Each action's status (✅ Succeeded, ❌ Failed, ⏭️ Skipped)
- Input/output for each action
- Error messages

### 5.2 "Unauthorized" on HTTP Trigger

**Cause:** The trigger URL has expired or the SAS token is invalid.

**Fix:**
1. Get a new trigger URL from Logic App → Workflows → workflow → Overview → Trigger URL
2. Update the Key Vault secret with the new URL:
   ```bash
   az keyvault secret set --vault-name kv-migration-poc \
     --name "logic-app-schema-discovery-url" \
     --value "<new-trigger-url>"
   ```

### 5.3 "ActionFailed: AzureDataFactory CreatePipelineRun"

**Cause:** Logic App cannot trigger ADF pipeline.

**Check managed identity permissions:**
```bash
# Get Logic App's managed identity
MI_ID=$(az functionapp identity show --name logic-schema-discovery \
  --resource-group rg-data-migration-poc --query principalId -o tsv)

# Check role assignments
az role assignment list --assignee $MI_ID --output table
```

**Expected:** Should have "Data Factory Contributor" on the ADF resource.

**Fix:**
```bash
ADF_ID=$(az datafactory show --name adf-migration-poc \
  --resource-group rg-data-migration-poc --query id -o tsv)

az role assignment create \
  --assignee-object-id $MI_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Data Factory Contributor" \
  --scope $ADF_ID
```

### 5.4 "ActionFailed: SQL Insert Row"

**Cause:** Logic App cannot write to Azure SQL metadata database.

**Check:**
1. Verify the SQL connector in the Logic App uses managed identity
2. Verify the managed identity has `db_datawriter` role in the metadata DB:
   ```sql
   USE [sqldb-migration-metadata];
   SELECT dp.name, dp.type_desc, r.name AS role_name
   FROM sys.database_principals dp
   JOIN sys.database_role_members drm ON dp.principal_id = drm.member_principal_id
   JOIN sys.database_principals r ON drm.role_principal_id = r.principal_id
   WHERE dp.name = 'logic-schema-discovery';
   ```

**Fix:** Re-run the SQL commands from DEPLOYMENT.md Section 7.4.

### 5.5 Logic App Runs but Returns Empty Response

**Check:** Open the Logic App run → inspect each action's output. Look for:
- Empty ADF pipeline output (schema discovery returned no data)
- AI response parsing failure (Migration Plan Logic App)
- SQL query returning empty results

**Fix:** Add **Compose** actions after each step to log intermediate data for debugging.

### 5.6 "Workflow Run Exceeded Maximum Duration"

**Cause:** The Logic App run exceeded the maximum allowed duration (default: 90 days for Standard, but individual actions have shorter limits).

**Fix:**
- For long-running ADF pipelines: increase the **Until** loop timeout
- For approval workflows: the 72-hour timeout is expected — configure accordingly
- Break very long operations into smaller chunks

---

## 6. Oracle Connectivity Issues

### 6.1 "ORA-12170: TNS:Connect timeout occurred"

**Cause:** Network cannot reach the Oracle server.

**Diagnosis from SHIR VM:**
```powershell
# Test basic connectivity
Test-NetConnection -ComputerName <oracle-host> -Port 1521

# Test TNS
tnsping <oracle-host>:1521/FREEPDB1
```

**Fix:**
- Verify VPN is connected (if using VPN):
  ```bash
  az network vpn-connection show --name conn-onprem \
    --resource-group rg-data-migration-poc --query connectionStatus -o tsv
  ```
- Check NSG rules allow outbound traffic on port 1521 from `snet-shir`
- Verify Oracle listener is running on the source server:
  ```bash
  # On the Oracle server
  lsnrctl status
  ```
- Check Oracle firewall allows inbound on port 1521 from the SHIR VM's IP range

### 6.2 "ORA-01017: invalid username/password"

**Fix:**
1. Verify credentials in Key Vault:
   ```bash
   az keyvault secret show --vault-name kv-migration-poc --name oracle-username --query value -o tsv
   az keyvault secret show --vault-name kv-migration-poc --name oracle-password --query value -o tsv
   ```
2. Test credentials directly from the SHIR VM:
   ```bash
   sqlplus <username>/<password>@<host>:1521/FREEPDB1
   ```
3. Update secrets if incorrect:
   ```bash
   az keyvault secret set --vault-name kv-migration-poc \
     --name oracle-password --value "<correct-password>"
   ```

### 6.3 "ORA-28000: the account is locked"

**Cause:** Too many failed login attempts locked the Oracle account.

**Fix (on the Oracle server):**
```sql
ALTER USER migration_user ACCOUNT UNLOCK;
-- Optionally reset password:
ALTER USER migration_user IDENTIFIED BY <new-password>;
```
Then update the Key Vault secret.

### 6.4 "ORA-00942: table or view does not exist"

**Cause:** The migration user doesn't have `SELECT` privileges on the tables.

**Fix:**
```sql
-- Grant read access on all tables in the schema
GRANT SELECT ANY TABLE TO migration_user;
-- Or for specific tables:
GRANT SELECT ON hr.employees TO migration_user;
```

### 6.5 Oracle Instant Client Not Found on SHIR VM

**Symptom:** ADF shows "Oracle client not found" or "OCI library not loaded"

**Fix:**
1. RDP into the SHIR VM
2. Verify Oracle Instant Client is installed:
   ```powershell
   dir C:\oracle\instantclient_21_x\oci.dll
   ```
3. Verify PATH includes the Instant Client directory:
   ```powershell
   $env:PATH -split ';' | Select-String -Pattern "oracle"
   ```
4. If missing, install Oracle Instant Client:
   - Download from [Oracle](https://www.oracle.com/database/technologies/instant-client/winx64-64-downloads.html)
   - Extract Basic + ODBC packages to `C:\oracle\instantclient_21_x`
   - Add to PATH and restart SHIR service

---

## 7. SQL Server Connectivity Issues

### 7.1 "Cannot connect to SQL Server"

**Diagnosis from SHIR VM:**
```powershell
# Test TCP connectivity
Test-NetConnection -ComputerName <sqlserver-host> -Port 1433

# Test with sqlcmd
sqlcmd -S <sqlserver-host>,1433 -U <user> -P <password> -Q "SELECT 1"
```

**Common fixes:**
- Enable TCP/IP protocol in SQL Server Configuration Manager
- Open port 1433 in Windows Firewall on the SQL Server host
- If using named instances, enable SQL Server Browser service and open UDP 1434

### 7.2 "Login failed for user"

**Fix:**
1. Verify SQL Server authentication mode (Mixed mode required for SQL auth)
2. Test credentials directly
3. Update Key Vault secrets if needed

### 7.3 "Named Pipes Provider: Could not open a connection"

**Cause:** Named Pipes is being used instead of TCP/IP.

**Fix:** Ensure the connection string in Key Vault uses TCP:
```
Server=tcp:<host>,1433;Database=MigrationDemo;User Id=<user>;Password=[REDACTED_PASSWORD]
```
Note the `tcp:` prefix.

---

## 8. Azure SQL Target Issues

### 8.1 "Cannot connect to Azure SQL Database"

**Check:**
```bash
# Verify server exists
az sql server show --name sql-migration-poc \
  --resource-group rg-data-migration-poc --query fullyQualifiedDomainName -o tsv

# Check firewall (if public access is allowed for testing)
az sql server firewall-rule list \
  --server sql-migration-poc \
  --resource-group rg-data-migration-poc
```

**If using private endpoints:**
- Verify DNS resolves to the private IP:
  ```bash
  nslookup sql-migration-poc.database.windows.net
  # Should return a 10.0.2.x address, not a public IP
  ```
- Verify the private endpoint is in "Succeeded" state:
  ```bash
  az network private-endpoint show --name pe-sql-migration \
    --resource-group rg-data-migration-poc --query provisioningState -o tsv
  ```

### 8.2 "The server principal is not able to access the database"

**Cause:** Managed identity is not created as a database user.

**Fix:** Run the SQL from DEPLOYMENT.md Section 7.4 to create users for each managed identity.

### 8.3 "Cannot insert duplicate key" / Primary Key Violations

**Cause:** Re-running migration on a table that already has data.

**Fix options:**
1. **Truncate and reload:**
   ```sql
   TRUNCATE TABLE [dbo].[EMPLOYEES];
   ```
2. **Drop and recreate:**
   ```sql
   DROP TABLE IF EXISTS [dbo].[EMPLOYEES];
   ```
   Then re-run migration with `executeDDL: true`
3. **Use merge/upsert** (requires custom ADF pipeline modification)

### 8.4 "Database size limit reached"

**Fix:**
```bash
# Check current size
az sql db show --server sql-migration-poc --name sqldb-migration-target \
  --resource-group rg-data-migration-poc --query "maxSizeBytes" -o tsv

# Increase max size
az sql db update --server sql-migration-poc --name sqldb-migration-target \
  --resource-group rg-data-migration-poc --max-size 250GB
```

### 8.5 "DTU/vCore limit reached" (Performance Throttling)

**Symptom:** Inserts are extremely slow, or you see `RESOURCE_SEMAPHORE` waits.

**Fix:**
```bash
# Scale up temporarily during migration
az sql db update --server sql-migration-poc --name sqldb-migration-target \
  --resource-group rg-data-migration-poc --service-objective GP_Gen5_8

# Scale back down after migration
az sql db update --server sql-migration-poc --name sqldb-migration-target \
  --resource-group rg-data-migration-poc --service-objective GP_Gen5_4
```

---

## 9. Approval Workflow Issues

### 9.1 Approver Never Receives Email

**Check Logic App run:**
1. Open `logic-approval-workflow` → Run history
2. Find the run → check if the "Send approval email" action succeeded
3. Check the output for the recipient email address

**Common fixes:**
- Verify the email address is correct
- Check the approver's spam/junk folder
- If using Office 365 connector: verify the Logic App has an authorized O365 connection
- If using Teams: verify the Teams connector is authorized and the user exists

### 9.2 Approval Email Sent but Response Not Received

**Check:**
1. In Logic App run history, check if the "Wait for response" action is still "Running"
2. The approval may still be pending — check with the approver
3. The approval link may have expired (if using custom expiry)

**Fix:**
- Ask the approver to click the button in the email/Teams card again
- If the link expired, cancel the job and resend the approval

### 9.3 Approval Times Out (72 Hours)

**Expected behavior:** After 72 hours without a response, the workflow sets status to `ApprovalTimedOut`.

**Fix:**
- Tell the agent: "Resend the approval for job [job-id] to admin@contoso.com"
- Or send to a different approver
- To change the timeout: modify the `Until` or `Wait for approval` action timeout in the Logic App designer

### 9.4 Approval Received but Agent Doesn't Know

**Cause:** The approval Logic App completed but the agent hasn't checked.

**Fix:** Tell the agent: "Check the approval status for job [job-id]"

The agent will query the metadata database and see the updated status.

---

## 10. Validation Failures

### 10.1 Row Count Mismatch

**Symptom:** Source has 1,000 rows but target has 995 rows.

**Diagnosis:**
```sql
-- Check for rows that failed during copy
-- Look at ADF copy activity output for "rowsSkipped" or "errors"

-- Check source for rows that might fail type conversion
-- Oracle example: find dates that don't fit DATETIME2 range
SELECT * FROM hr.employees 
WHERE hire_date < DATE '0001-01-01' OR hire_date > DATE '9999-12-31';
```

**Fix:**
- Check ADF pipeline's copy activity → "Error file" settings (if configured)
- Look for data quality issues (NULLs in NOT NULL columns, truncation, etc.)
- Re-run the copy for the specific table after fixing source data issues

### 10.2 Null Distribution Mismatch

**Cause:** Data type conversion changed NULL handling (e.g., empty string vs NULL).

**Diagnosis:**
```sql
-- Compare NULL counts
-- Source (Oracle)
SELECT COUNT(*) - COUNT(commission_pct) AS null_count FROM hr.employees;

-- Target (Azure SQL)
SELECT COUNT(*) - COUNT(COMMISSION_PCT) AS null_count FROM dbo.EMPLOYEES;
```

**Fix:** Usually indicates a data conversion issue. Check if Oracle empty strings (`''`) are being treated differently than SQL Server/Azure SQL NULLs.

### 10.3 Schema Comparison Failure

**Symptom:** Target column type doesn't match the plan.

**Diagnosis:**
```sql
-- Check target table structure
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'EMPLOYEES' AND TABLE_SCHEMA = 'dbo'
ORDER BY ORDINAL_POSITION;

-- Compare against the plan in metadata DB
SELECT TargetColumn, TargetDataType
FROM dbo.SchemaMappings
WHERE JobId = '<job-id>' AND TargetTable = 'EMPLOYEES';
```

**Fix:** If the table was created manually or by a different process, drop and let the agent recreate it.

### 10.4 Sample Data Mismatch

**Common causes:**
- Character encoding differences (Oracle AL32UTF8 vs Azure SQL UTF-16)
- Date format differences (Oracle NLS settings)
- Floating point rounding

**Fix:** Check specific mismatched rows and determine if the difference is acceptable (e.g., `0.30000000000000004` vs `0.3` is a float precision issue, not a real error).

---

## 11. Key Vault Access Denied

### 11.1 "Caller is not authorized to perform action on resource"

**Symptom:** `403 Forbidden` when a service tries to read a Key Vault secret.

**Diagnosis:**
```bash
# Check who's trying to access
az keyvault show --name kv-migration-poc --resource-group rg-data-migration-poc \
  --query "properties.enableRbacAuthorization" -o tsv
# Should be: true

# List role assignments on Key Vault
az role assignment list \
  --scope $(az keyvault show --name kv-migration-poc \
    --resource-group rg-data-migration-poc --query id -o tsv) \
  --output table
```

**Fix:** Assign `Key Vault Secrets User` role to the failing service's managed identity:
```bash
az role assignment create \
  --assignee-object-id <managed-identity-principal-id> \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope $(az keyvault show --name kv-migration-poc \
    --resource-group rg-data-migration-poc --query id -o tsv)
```

### 11.2 "SecretNotFound"

**Cause:** The secret name doesn't exist in Key Vault.

**Check:**
```bash
az keyvault secret list --vault-name kv-migration-poc --query "[].name" -o table
```

**Fix:** Create the missing secret per DEPLOYMENT.md Section 6.2.

### 11.3 "SecretDisabled"

**Cause:** The secret has been disabled or has expired.

**Fix:**
```bash
# Re-enable the secret
az keyvault secret set-attributes \
  --vault-name kv-migration-poc \
  --name <secret-name> \
  --enabled true
```

### 11.4 Key Vault Firewall Blocking Access

**Symptom:** Services inside VNet can't reach Key Vault.

**Check:**
```bash
az keyvault show --name kv-migration-poc \
  --resource-group rg-data-migration-poc \
  --query "properties.networkAcls" -o json
```

**Fix:**
- If using private endpoints: verify DNS resolution and private endpoint status
- If using service endpoints: add the VNet subnets:
  ```bash
  az keyvault network-rule add \
    --name kv-migration-poc \
    --resource-group rg-data-migration-poc \
    --vnet-name vnet-migration \
    --subnet snet-logic-apps
  ```
- For testing: temporarily allow all networks (not for production):
  ```bash
  az keyvault update --name kv-migration-poc \
    --resource-group rg-data-migration-poc \
    --default-action Allow
  ```

---

## 12. Managed Identity Issues

### 12.1 "AADSTS700016: Application not found"

**Cause:** The managed identity doesn't exist or isn't properly registered.

**Check:**
```bash
# Verify managed identity exists for each resource
az datafactory show --name adf-migration-poc \
  --resource-group rg-data-migration-poc \
  --query identity

az functionapp identity show --name logic-schema-discovery \
  --resource-group rg-data-migration-poc
```

**Fix:** Re-enable system-assigned identity:
```bash
az functionapp identity assign --name logic-schema-discovery \
  --resource-group rg-data-migration-poc
```

### 12.2 "Login failed for user '<token-identified principal>'"

**Cause:** Managed identity not added as a user in Azure SQL Database.

**Fix:** Connect to the database as an admin and run:
```sql
CREATE USER [logic-schema-discovery] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datawriter ADD MEMBER [logic-schema-discovery];
ALTER ROLE db_datareader ADD MEMBER [logic-schema-discovery];
```

### 12.3 RBAC Propagation Delay

**Symptom:** Role assignment created but access still denied.

**Cause:** RBAC changes can take up to 5 minutes to propagate in Azure.

**Fix:** Wait 5 minutes and retry. If still failing after 10 minutes, verify the assignment:
```bash
az role assignment list --assignee <principal-id> --output table
```

### 12.4 Wrong Managed Identity Principal ID

**Symptom:** Role assignment exists but doesn't match the resource.

**Diagnosis:**
```bash
# Get the actual principal ID of the Logic App
ACTUAL_ID=$(az functionapp identity show --name logic-schema-discovery \
  --resource-group rg-data-migration-poc --query principalId -o tsv)
echo "Logic App MI: $ACTUAL_ID"

# Check the role assignment
az role assignment list \
  --scope <resource-scope> \
  --query "[?principalId=='$ACTUAL_ID']" \
  --output table
```

**Fix:** Delete the incorrect assignment and create a new one with the correct principal ID.

---

## 13. Self-Hosted Integration Runtime Issues

### 13.1 SHIR Shows "Offline" or "Disconnected"

**Diagnosis (RDP into SHIR VM):**
1. Open **Integration Runtime Configuration Manager** (system tray icon)
2. Check status tab
3. Check **Diagnostics** tab → run self-test

**Common fixes:**
```powershell
# Restart the SHIR service
Restart-Service DIAHostService

# Check if the service is running
Get-Service DIAHostService

# Check Windows Event Log for errors
Get-EventLog -LogName Application -Source "Microsoft Integration Runtime" -Newest 20
```

### 13.2 "Not enough resources on the node"

**Cause:** SHIR VM is running out of CPU or memory.

**Check:**
```powershell
# Check resource usage
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10
Get-Counter '\Processor(_Total)\% Processor Time'
```

**Fix:**
- Scale up the VM: `Standard_D4s_v5` → `Standard_D8s_v5`
- Reduce `parallelCopies` in ADF copy activities
- Add a second SHIR node for HA

### 13.3 "TLS/SSL connection could not be established"

**Cause:** Outdated TLS version or missing certificates.

**Fix:**
```powershell
# Ensure TLS 1.2 is enabled
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Registry fix for persistent TLS 1.2
New-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\.NETFramework\v4.0.30319' -Name 'SchUseStrongCrypto' -Value 1 -PropertyType DWord -Force
New-ItemProperty -Path 'HKLM:\SOFTWARE\Wow6432Node\Microsoft\.NETFramework\v4.0.30319' -Name 'SchUseStrongCrypto' -Value 1 -PropertyType DWord -Force

Restart-Service DIAHostService
```

### 13.4 SHIR Auto-Update Failures

**Symptom:** SHIR shows "Update available" but auto-update fails.

**Fix:**
1. Disable auto-update temporarily
2. Download the latest SHIR manually from the Microsoft download center
3. Install the update manually on the VM
4. Re-enable auto-update

---

## 14. Network & Private Endpoint Issues

### 14.1 DNS Resolution Fails for Private Endpoints

**Symptom:** `sql-migration-poc.database.windows.net` resolves to a public IP instead of `10.0.2.x`.

**Check:**
```bash
# From inside the VNet (SHIR VM or Logic App)
nslookup sql-migration-poc.database.windows.net
# Should return: 10.0.2.x (private IP)

# If it returns a public IP, the Private DNS Zone isn't configured
```

**Fix:**
1. Verify the Private DNS Zone exists:
   ```bash
   az network private-dns zone show \
     --resource-group rg-data-migration-poc \
     --name privatelink.database.windows.net
   ```
2. Verify the VNet link:
   ```bash
   az network private-dns link vnet list \
     --resource-group rg-data-migration-poc \
     --zone-name privatelink.database.windows.net -o table
   ```
3. Verify the DNS zone group on the private endpoint:
   ```bash
   az network private-endpoint dns-zone-group list \
     --endpoint-name pe-sql-migration \
     --resource-group rg-data-migration-poc -o table
   ```

### 14.2 VPN Connection Drops

**Check:**
```bash
az network vpn-connection show --name conn-onprem \
  --resource-group rg-data-migration-poc \
  --query "{status:connectionStatus, egress:egressBytesTransferred, ingress:ingressBytesTransferred}"
```

**Fix:**
- Verify the shared key matches on both sides
- Check the on-premises VPN device logs
- Restart the VPN connection:
  ```bash
  az network vpn-connection update --name conn-onprem \
    --resource-group rg-data-migration-poc --set routingWeight=0
  # Wait 30 seconds
  az network vpn-connection update --name conn-onprem \
    --resource-group rg-data-migration-poc --set routingWeight=10
  ```

### 14.3 NSG Blocking Traffic

**Diagnosis:**
```bash
# Check effective NSG rules for the SHIR subnet
az network nic list-effective-nsg \
  --resource-group rg-data-migration-poc \
  --name <shir-vm-nic-name> -o table
```

**Check NSG flow logs:**
```kql
// In Log Analytics
AzureNetworkAnalytics_CL
| where FlowStatus_s == "D"  // Denied
| where SrcIP_s contains "10.0.3"  // SHIR subnet
| project TimeGenerated, SrcIP_s, DestIP_s, DestPort_d, FlowStatus_s
```

---

## 15. Performance Issues

### 15.1 Slow Data Copy

**Diagnosis checklist:**

| Check | How | Fix |
|-------|-----|-----|
| Network bandwidth | `iperf3` between SHIR and Oracle | Use VPN or ExpressRoute with higher bandwidth |
| ADF parallelism | Copy activity → Settings → `parallelCopies` | Increase to 4–8 |
| Source DB load | Check Oracle AWR / SQL Server DMVs | Schedule migration during off-peak |
| Target throttling | Azure SQL → Metrics → DTU/CPU % | Scale up target temporarily |
| SHIR VM resources | Task Manager on SHIR VM | Scale up VM |
| Table size | No index on source table | Add index on PK for efficient reads |

### 15.2 Logic App Execution Slow

**Fix:**
- Enable **stateless workflows** for non-critical Logic Apps (schema discovery, validation)
- Use **parallel execution** in ForEach loops (set concurrency in the ForEach action settings)
- Cache Key Vault lookups using variables instead of re-reading for each action

### 15.3 GPT-4.1 Response Slow

**Symptom:** Migration plan generation takes >60 seconds.

**Fix:**
- Reduce the prompt size (summarize schema instead of passing all columns)
- Use structured output format to reduce token generation
- Increase TPM capacity on the deployment

---

## 16. Checking Logs in Application Insights

### 16.1 Accessing Application Insights

1. **Azure Portal** → `appi-migration-poc` → **Logs**
2. Or via **Log Analytics Workspace** → `law-migration-poc` → **Logs**

### 16.2 Useful KQL Queries

**Find all Logic App failures in the last 24 hours:**
```kql
AppRequests
| where TimeGenerated > ago(24h)
| where Success == false
| project TimeGenerated, Name, ResultCode, DurationMs, 
    OperationId, AppRoleName
| order by TimeGenerated desc
```

**ADF pipeline execution summary:**
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.DATAFACTORY"
| where Category == "PipelineRuns"
| where TimeGenerated > ago(7d)
| summarize TotalRuns = count(), 
    SuccessRuns = countif(status_s == "Succeeded"),
    FailedRuns = countif(status_s == "Failed")
    by pipelineName_s
| order by FailedRuns desc
```

**ADF copy activity details (rows copied, duration):**
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.DATAFACTORY"
| where Category == "ActivityRuns"
| where activityType_s == "Copy"
| where TimeGenerated > ago(24h)
| project TimeGenerated, pipelineName_s, activityName_s, status_s,
    output_rowsCopied_d, output_rowsRead_d,
    output_throughput_d, output_copyDuration_d
| order by TimeGenerated desc
```

**Key Vault access audit (who accessed what):**
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where TimeGenerated > ago(24h)
| project TimeGenerated, OperationName, 
    identity_claim_upn_s, CallerIPAddress,
    id_s, ResultType, ResultSignature
| order by TimeGenerated desc
```

**Find Logic App workflow errors with details:**
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.WEB"
| where Category == "WorkflowRuntime"
| where status_s == "Failed"
| where TimeGenerated > ago(24h)
| project TimeGenerated, resource_workflowName_s, 
    resource_actionName_s, error_code_s, error_message_s
| order by TimeGenerated desc
```

**Azure SQL query performance:**
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.SQL"
| where Category == "QueryStoreRuntimeStatistics"
| where TimeGenerated > ago(1h)
| project TimeGenerated, query_hash_s, 
    avg_duration_d, execution_count_d, avg_cpu_time_d
| order by avg_duration_d desc
| take 20
```

**End-to-end migration timeline (correlate across services):**
```kql
// Join ADF pipeline runs with Logic App invocations
let adfRuns = AzureDiagnostics
| where ResourceProvider == "MICROSOFT.DATAFACTORY"
| where Category == "PipelineRuns"
| where TimeGenerated > ago(24h)
| project AdfTime=TimeGenerated, Pipeline=pipelineName_s, 
    AdfStatus=status_s, AdfDuration=durationInMs_d;
let logicRuns = AppRequests
| where TimeGenerated > ago(24h)
| where AppRoleName contains "logic-"
| project LogicTime=TimeGenerated, LogicApp=AppRoleName, 
    LogicStatus=Success, LogicDuration=DurationMs;
adfRuns | union logicRuns
| order by AdfTime asc, LogicTime asc
```

### 16.3 Creating a Monitoring Dashboard

1. In Azure Portal → **Dashboard** → **+ New dashboard**
2. Add tiles:
   - **ADF pipeline success/failure** (Metrics chart)
   - **Logic App run history** (Metrics chart)
   - **Azure SQL DTU usage** (Metrics chart)
   - **Key Vault operations** (Log Analytics query)
   - **Application Insights live metrics** (Live metrics tile)
3. Pin your favorite KQL queries as tiles

### 16.4 Setting Up Alerts

```bash
# Alert when any migration pipeline fails
az monitor metrics alert create \
  --name "alert-migration-pipeline-failure" \
  --resource-group rg-data-migration-poc \
  --scopes $(az datafactory show --name adf-migration-poc \
    --resource-group rg-data-migration-poc --query id -o tsv) \
  --condition "total PipelineFailedRuns > 0" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --severity 1 \
  --description "Migration pipeline failed — immediate attention required"

# Alert when Azure SQL DTU is consistently high
az monitor metrics alert create \
  --name "alert-sql-high-dtu" \
  --resource-group rg-data-migration-poc \
  --scopes $(az sql db show --server sql-migration-poc \
    --name sqldb-migration-target --resource-group rg-data-migration-poc --query id -o tsv) \
  --condition "avg dtu_consumption_percent > 90" \
  --window-size 15m \
  --evaluation-frequency 5m \
  --severity 2 \
  --description "Azure SQL target database DTU usage is critically high"
```

---

## 17. Emergency Procedures

### 17.1 Stop a Running Migration Immediately

```bash
# Cancel all running ADF pipeline runs
az datafactory pipeline-run query-by-factory \
  --resource-group rg-data-migration-poc \
  --factory-name adf-migration-poc \
  --last-updated-after "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  --filters operand="Status" operator="Equals" values="InProgress" \
  --output json | jq -r '.value[].runId' | while read RUN_ID; do
    az datafactory pipeline-run cancel \
      --resource-group rg-data-migration-poc \
      --factory-name adf-migration-poc \
      --run-id "$RUN_ID"
    echo "Cancelled: $RUN_ID"
  done
```

### 17.2 Roll Back Target Database

```sql
-- Option 1: Drop all migrated tables (CAUTION)
-- List tables created by the migration
SELECT TABLE_SCHEMA, TABLE_NAME 
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_TYPE = 'BASE TABLE';

-- Drop individually
DROP TABLE IF EXISTS [dbo].[EMPLOYEES];
DROP TABLE IF EXISTS [dbo].[DEPARTMENTS];
-- ... etc.

-- Option 2: Restore from Point-in-Time
-- Use Azure Portal → SQL Database → Restore → select time before migration
```

```bash
# Restore Azure SQL to a point before migration
az sql db restore \
  --dest-name sqldb-migration-target-restored \
  --name sqldb-migration-target \
  --server sql-migration-poc \
  --resource-group rg-data-migration-poc \
  --time "2026-09-03T12:00:00Z"
```

### 17.3 Reset Migration Metadata

```sql
-- Reset a specific job to allow re-execution
UPDATE dbo.MigrationJobs 
SET Status = 'Approved', 
    CompletedAt = NULL, 
    ErrorMessage = NULL,
    UpdatedAt = SYSUTCDATETIME()
WHERE JobId = '<job-id>';

-- Clean up associated records for a re-run
DELETE FROM dbo.MigrationLog WHERE JobId = '<job-id>';
DELETE FROM dbo.ValidationResults WHERE JobId = '<job-id>';
```

---

## 18. Support Escalation

### Severity Levels

| Level | Description | Response Time | Example |
|-------|-----------|---------------|---------|
| **Sev 1** | Migration blocked, data at risk | Immediate | ADF writing corrupted data, Azure SQL down |
| **Sev 2** | Migration failing, workaround available | 4 hours | Pipeline timeout, retryable error |
| **Sev 3** | Non-blocking issue | 24 hours | Validation warning, performance concern |
| **Sev 4** | Question or enhancement | 72 hours | Feature request, documentation gap |

### Escalation Path

1. **Self-service:** This troubleshooting guide + Application Insights logs
2. **Team lead:** Review migration metadata DB + ADF pipeline logs
3. **Azure Support:** For platform-level issues (ADF connector bugs, Azure SQL outages)
   - Portal: [Azure Support Request](https://portal.azure.com/#blade/Microsoft_Azure_Support/HelpAndSupportBlade)
4. **Microsoft Account Team:** For quota increases, preview features

### Information to Gather Before Escalating

| Item | How to Get It |
|------|--------------|
| Job ID | From the agent conversation or metadata DB |
| ADF pipeline run ID | ADF Studio → Monitor → Pipeline Runs → Run ID |
| Logic App run ID | Logic App → Run history → Run ID |
| Error message (exact) | From agent conversation, ADF output, or Logic App action output |
| Timestamp (UTC) | When the error occurred |
| Application Insights correlation ID | From log queries (OperationId) |
| SHIR diagnostic report | Integration Runtime Config Manager → Diagnostics → Send Logs |

---

> **Related documentation:**
> - [DEPLOYMENT.md](DEPLOYMENT.md) — Full deployment guide
> - [USER_GUIDE.md](USER_GUIDE.md) — End-user conversation guide
> - [Azure Data Factory troubleshooting](https://learn.microsoft.com/en-us/azure/data-factory/data-factory-troubleshoot-guide)
> - [Logic Apps troubleshooting](https://learn.microsoft.com/en-us/azure/logic-apps/logic-apps-diagnosing-failures)
> - [Azure SQL connectivity troubleshooting](https://learn.microsoft.com/en-us/azure/azure-sql/database/troubleshoot-common-errors-issues)
