# Security — Azure Agentic Data Migration

This document covers the security architecture, credential management, identity configuration, network isolation, and audit practices for the Azure Agentic Data Migration solution.

> ⚠️ **Critical Rule:** Never place real secrets — connection strings, passwords, API keys, SAS tokens, or certificates — in prompts, JSON templates, Markdown files, Bicep parameters, Logic App definitions, ADF pipeline JSON, source code, or Git repositories. All secrets must live in Azure Key Vault and be referenced by URI at runtime.

---

## Table of Contents

- [Security Principles](#security-principles)
- [Key Vault Setup](#key-vault-setup)
- [Managed Identity Configuration](#managed-identity-configuration)
- [Entra ID RBAC Roles](#entra-id-rbac-roles)
- [Network Security](#network-security)
- [Secret Rotation](#secret-rotation)
- [Audit Logging](#audit-logging)
- [Agent-Specific Security](#agent-specific-security)
- [Data Protection](#data-protection)
- [Compliance Checklist](#compliance-checklist)

---

## Security Principles

This solution follows these security principles:

| # | Principle | Implementation |
|---|-----------|---------------|
| 1 | **Zero secrets in code** | All credentials in Key Vault; referenced by URI |
| 2 | **Managed identity everywhere** | No service principal secrets; system-assigned MI for each service |
| 3 | **Least privilege** | Each service gets only the RBAC roles it needs |
| 4 | **Network isolation** | Private endpoints for all data-plane operations |
| 5 | **Encryption at rest and in transit** | TLS 1.2+ in transit; AES-256 at rest (platform default) |
| 6 | **Audit everything** | All secret access, approval decisions, and data movements logged |
| 7 | **Human in the loop** | No data migration without explicit human approval |
| 8 | **Secrets never in LLM context** | Agent system prompt and tool responses never contain credentials |

---

## Key Vault Setup

### Key Vault Instance

Deploy a dedicated Key Vault for this solution:

```bash
az keyvault create \
  --name kv-datamigration \
  --resource-group rg-data-migration \
  --location eastus2 \
  --sku standard \
  --enable-rbac-authorization true \
  --enable-purge-protection true \
  --retention-days 90
```

**Key settings:**
- `--enable-rbac-authorization true` — Use Entra ID RBAC instead of vault access policies
- `--enable-purge-protection true` — Prevent permanent deletion of secrets
- `--retention-days 90` — Soft-deleted secrets retained for 90 days

### Secrets Inventory

Store the following secrets in Key Vault:

| Secret Name | Description | Used By | Example Format |
|-------------|-------------|---------|----------------|
| `oracle-connection-string` | Oracle source database connection string | ADF Linked Service | `Host=<host>;Port=1521;Service Name=<svc>;User Id=<user>;Password=<pwd>` |
| `oracle-username` | Oracle database username (if not in conn string) | ADF Linked Service | `MIGRATION_READ_USER` |
| `oracle-password` | Oracle database password | ADF Linked Service | (password value) |
| `sqlserver-connection-string` | SQL Server source connection string | ADF Linked Service | `Server=<host>;Database=<db>;User Id=<user>;Password=<pwd>;Encrypt=True` |
| `azuresql-connection-string` | Azure SQL target connection string | Logic App SQL Connector | `Server=<server>.database.windows.net;Database=<db>;...` |
| `azure-openai-api-key` | Azure OpenAI API key | AI Foundry Agent | (API key value) |
| `azure-openai-endpoint` | Azure OpenAI endpoint URL | AI Foundry Agent | `https://<instance>.openai.azure.com/` |
| `adf-self-hosted-ir-key` | Self-Hosted Integration Runtime auth key | IR installation | (auto-generated key) |
| `power-automate-callback-url` | Power Automate flow trigger URL | Approval Logic App | `https://prod-xx.westus.logic.azure.com/...` |
| `storage-account-key` | Blob Storage access key (if not using MI) | ADF, Logic Apps | (storage key) |

### Populating Secrets

Use the Azure CLI to set secrets (run from a secure workstation, not from CI/CD):

```bash
# Oracle connection
az keyvault secret set \
  --vault-name kv-datamigration \
  --name "oracle-connection-string" \
  --value "Host=oracle-prod.internal.corp;Port=1521;Service Name=HRDB;User Id=MIGRATION_READ;Password=REPLACE_ME"

# SQL Server connection
az keyvault secret set \
  --vault-name kv-datamigration \
  --name "sqlserver-connection-string" \
  --value "Server=sqlserver-prod.internal.corp;Database=AdventureWorks;User Id=mig_reader;Password=REPLACE_ME;Encrypt=True;TrustServerCertificate=False"

# Azure SQL target
az keyvault secret set \
  --vault-name kv-datamigration \
  --name "azuresql-connection-string" \
  --value "Server=sql-datamigration.database.windows.net;Database=TargetDB;Authentication=Active Directory Managed Identity"

# Azure OpenAI
az keyvault secret set \
  --vault-name kv-datamigration \
  --name "azure-openai-api-key" \
  --value "REPLACE_WITH_ACTUAL_KEY"
```

> ⚠️ Replace `REPLACE_ME` and `REPLACE_WITH_ACTUAL_KEY` with actual values. **Never commit actual credentials to this file or any file in the repository.**

### Key Vault References in ADF Linked Services

ADF Linked Services reference Key Vault secrets by URI — no credentials stored in the ADF JSON definition:

```json
{
    "name": "ls_oracle_source",
    "properties": {
        "type": "Oracle",
        "typeProperties": {
            "connectionString": {
                "type": "AzureKeyVaultSecret",
                "store": {
                    "referenceName": "ls_keyvault",
                    "type": "LinkedServiceReference"
                },
                "secretName": "oracle-connection-string"
            }
        },
        "connectVia": {
            "referenceName": "SelfHostedIR",
            "type": "IntegrationRuntimeReference"
        }
    }
}
```

### Key Vault References in Logic Apps

Logic Apps access Key Vault via the built-in Key Vault connector:

```json
{
    "Get_Oracle_Connection_String": {
        "type": "ApiConnection",
        "inputs": {
            "host": {
                "connection": {
                    "name": "@parameters('$connections')['keyvault']['connectionId']"
                }
            },
            "method": "get",
            "path": "/secrets/@{encodeURIComponent('oracle-connection-string')}/value"
        }
    }
}
```

---

## Managed Identity Configuration

### System-Assigned Managed Identities

Each Azure service uses a **system-assigned managed identity** for authentication to other services:

| Service | Managed Identity | Authenticates To |
|---------|-----------------|-----------------|
| Azure Data Factory | System-assigned MI | Key Vault, Blob Storage, Azure SQL |
| Logic Apps (each workflow) | System-assigned MI | Key Vault, ADF REST API, Azure SQL, Blob Storage |
| Azure SQL Database | System-assigned MI | Entra ID (for contained database users) |
| AI Foundry Agent Service | System-assigned MI | Azure OpenAI |

### Enabling Managed Identity

#### Azure Data Factory

```bash
# Enable system-assigned MI (enabled by default on creation)
az datafactory update \
  --resource-group rg-data-migration \
  --factory-name adf-datamigration \
  --identity-type SystemAssigned
```

#### Logic Apps

```bash
# Enable system-assigned MI for a Logic App
az logic workflow identity assign \
  --resource-group rg-data-migration \
  --name la-schema-discovery \
  --system-assigned
```

#### Grant Key Vault Access to Managed Identities

```bash
# Get ADF managed identity object ID
ADF_MI=$(az datafactory show \
  --resource-group rg-data-migration \
  --factory-name adf-datamigration \
  --query identity.principalId -o tsv)

# Grant Key Vault Secrets User role
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee-object-id $ADF_MI \
  --assignee-principal-type ServicePrincipal \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-data-migration/providers/Microsoft.KeyVault/vaults/kv-datamigration
```

Repeat for each Logic App managed identity.

### Azure SQL — Managed Identity Authentication

For the target Azure SQL Database, create a contained database user for each managed identity:

```sql
-- Connect to the target Azure SQL Database as admin
-- Create contained database user for ADF
CREATE USER [adf-datamigration] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [adf-datamigration];
ALTER ROLE db_datawriter ADD MEMBER [adf-datamigration];
ALTER ROLE db_ddladmin ADD MEMBER [adf-datamigration];

-- Create contained database user for Logic Apps (DDL execution)
CREATE USER [la-ddl-execution] FROM EXTERNAL PROVIDER;
ALTER ROLE db_ddladmin ADD MEMBER [la-ddl-execution];
ALTER ROLE db_datareader ADD MEMBER [la-ddl-execution];

-- Create contained database user for Logic Apps (validation)
CREATE USER [la-validation] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [la-validation];
```

---

## Entra ID RBAC Roles

### Role Assignments

| Principal | Entra ID Role / Custom Role | Scope | Purpose |
|-----------|----------------------------|-------|---------|
| **ADF Managed Identity** | Key Vault Secrets User | Key Vault | Read connection strings |
| **ADF Managed Identity** | Storage Blob Data Contributor | Storage Account | Write metadata/artifacts to Blob |
| **Logic App (Schema Discovery)** | Key Vault Secrets User | Key Vault | Read connection strings |
| **Logic App (Schema Discovery)** | Data Factory Contributor | ADF | Trigger and monitor pipelines |
| **Logic App (Schema Discovery)** | Storage Blob Data Reader | Storage Account | Read metadata output |
| **Logic App (DDL Execution)** | Key Vault Secrets User | Key Vault | Read Azure SQL connection |
| **Logic App (Approval)** | Storage Table Data Contributor | Storage Account | Read/write approval records |
| **Logic App (ADF Trigger)** | Data Factory Contributor | ADF | Create pipeline runs |
| **Logic App (Validation)** | Key Vault Secrets User | Key Vault | Read connection strings |
| **Agent MI** | Cognitive Services OpenAI User | Azure OpenAI | Call GPT-4.1 model |
| **Migration Operators** (Entra Group) | Reader | Resource Group | View all resources |
| **Migration Operators** (Entra Group) | Logic App Operator | Logic Apps | View run history |
| **Migration Approvers** (Entra Group) | Custom: Migration Approver | Logic App (Approval) | Submit approval decisions |
| **Platform Admins** (Entra Group) | Contributor | Resource Group | Full management |

### Custom Role: Migration Approver

```json
{
    "Name": "Migration Approver",
    "Description": "Can approve or reject data migration requests via the approval API",
    "Actions": [
        "Microsoft.Logic/workflows/triggers/listCallbackUrl/action",
        "Microsoft.Logic/workflows/runs/read"
    ],
    "NotActions": [],
    "DataActions": [
        "Microsoft.Storage/storageAccounts/tableServices/tables/entities/read",
        "Microsoft.Storage/storageAccounts/tableServices/tables/entities/write"
    ],
    "NotDataActions": [],
    "AssignableScopes": [
        "/subscriptions/<subscription-id>/resourceGroups/rg-data-migration"
    ]
}
```

### Entra ID Security Groups

Create these Entra ID security groups:

```bash
# Migration operators — can view resources and logs
az ad group create \
  --display-name "sg-migration-operators" \
  --mail-nickname "sg-migration-operators"

# Migration approvers — can approve/reject migrations
az ad group create \
  --display-name "sg-migration-approvers" \
  --mail-nickname "sg-migration-approvers"

# Platform admins — full control
az ad group create \
  --display-name "sg-migration-admins" \
  --mail-nickname "sg-migration-admins"
```

---

## Network Security

### Private Endpoints

Deploy private endpoints for all services that handle sensitive data:

| Service | Private Endpoint Name | Subnet | DNS Zone |
|---------|----------------------|--------|----------|
| Azure SQL Database | `pe-azuresql` | `snet-data` | `privatelink.database.windows.net` |
| Azure Key Vault | `pe-keyvault` | `snet-security` | `privatelink.vaultcore.azure.net` |
| Azure Blob Storage | `pe-storage-blob` | `snet-data` | `privatelink.blob.core.windows.net` |
| Azure Table Storage | `pe-storage-table` | `snet-data` | `privatelink.table.core.windows.net` |
| Azure Data Factory | `pe-adf` | `snet-integration` | `privatelink.datafactory.azure.net` |

### Deploy Private Endpoint (Example — Azure SQL)

```bash
az network private-endpoint create \
  --name pe-azuresql \
  --resource-group rg-data-migration \
  --vnet-name vnet-migration \
  --subnet snet-data \
  --private-connection-resource-id /subscriptions/<sub>/resourceGroups/rg-data-migration/providers/Microsoft.Sql/servers/sql-datamigration \
  --group-id sqlServer \
  --connection-name pec-azuresql
```

### Disable Public Access

After private endpoints are configured, disable public network access:

```bash
# Azure SQL
az sql server update \
  --name sql-datamigration \
  --resource-group rg-data-migration \
  --public-network-access Disabled

# Key Vault
az keyvault update \
  --name kv-datamigration \
  --resource-group rg-data-migration \
  --public-network-access Disabled

# Storage Account
az storage account update \
  --name stmigrationartifacts \
  --resource-group rg-data-migration \
  --public-network-access Disabled
```

### Self-Hosted Integration Runtime Network Requirements

The Self-Hosted IR on the on-premises machine requires:

| Direction | Protocol | Port | Destination | Purpose |
|-----------|----------|------|-------------|---------|
| Outbound | HTTPS | 443 | `*.servicebus.windows.net` | ADF communication relay |
| Outbound | HTTPS | 443 | `*.core.windows.net` | Blob Storage (metadata, artifacts) |
| Outbound | HTTPS | 443 | `download.microsoft.com` | IR auto-update |
| Inbound | TCP | 1521 | Oracle DB host | Oracle database access |
| Inbound | TCP | 1433 | SQL Server host | SQL Server database access |

> **No inbound ports from Azure are required.** The Self-Hosted IR establishes outbound connections to Azure Service Bus relay.

### Network Security Groups (NSGs)

```bash
# Allow only Self-Hosted IR subnet to reach source databases
az network nsg rule create \
  --resource-group rg-onprem-network \
  --nsg-name nsg-databases \
  --name allow-shir-oracle \
  --priority 100 \
  --source-address-prefixes 10.0.1.0/24 \
  --destination-port-ranges 1521 \
  --protocol TCP \
  --access Allow
```

---

## Secret Rotation

### Rotation Strategy

| Secret | Rotation Frequency | Rotation Method | Notes |
|--------|--------------------|-----------------|-------|
| Oracle password | 90 days | Manual (DBA coordination) | Requires ADF linked service reconnect test |
| SQL Server password | 90 days | Manual (DBA coordination) | Requires ADF linked service reconnect test |
| Azure SQL connection | N/A (managed identity) | Automatic | No password to rotate |
| Azure OpenAI API key | 180 days | Regenerate in Azure Portal | Update Key Vault secret, no service restart needed |
| Storage account key | 90 days | Key rotation via Azure CLI | ADF and Logic Apps pick up new key from Key Vault |
| Self-Hosted IR key | On compromise only | Regenerate in ADF portal | Requires IR re-registration |

### Automated Rotation for Storage Account Keys

```bash
# Rotate primary key
az storage account keys renew \
  --account-name stmigrationartifacts \
  --resource-group rg-data-migration \
  --key primary

# Update Key Vault with new key
NEW_KEY=$(az storage account keys list \
  --account-name stmigrationartifacts \
  --resource-group rg-data-migration \
  --query "[0].value" -o tsv)

az keyvault secret set \
  --vault-name kv-datamigration \
  --name "storage-account-key" \
  --value "$NEW_KEY"
```

### Key Vault Rotation Alerts

Configure alerts when secrets approach expiration:

```bash
# Set expiry on a secret
az keyvault secret set-attributes \
  --vault-name kv-datamigration \
  --name "oracle-password" \
  --expires "2025-06-01T00:00:00Z"
```

Enable Key Vault event notifications to trigger rotation reminders via Event Grid → Logic App → Teams/Email.

---

## Audit Logging

### What Gets Logged

| Event Category | Log Source | Retention | Key Fields |
|----------------|------------|-----------|------------|
| Secret access | Key Vault Diagnostic Logs | 90 days | Caller identity, secret name, operation, timestamp |
| Secret denied access | Key Vault Diagnostic Logs | 90 days | Caller identity, error code |
| Approval decisions | Azure Table Storage + Logic App run history | 365 days | Migration ID, approver, decision, timestamp, comments |
| DDL execution | Logic App run history + Azure SQL audit logs | 90 days | DDL statement hash, tables created, errors |
| Data movement | ADF pipeline run logs | 90 days | Source/target tables, rows copied, duration, errors |
| Agent conversations | AI Foundry Diagnostic Logs | 30 days | Thread ID, tool calls, token usage |
| Login attempts | Entra ID sign-in logs | 30 days | User, IP, success/failure |
| Network access | NSG flow logs | 30 days | Source/dest IP, port, action |

### Enable Diagnostic Logging

#### Key Vault

```bash
az monitor diagnostic-settings create \
  --name kv-diagnostics \
  --resource /subscriptions/<sub>/resourceGroups/rg-data-migration/providers/Microsoft.KeyVault/vaults/kv-datamigration \
  --workspace /subscriptions/<sub>/resourceGroups/rg-data-migration/providers/Microsoft.OperationalInsights/workspaces/law-migration \
  --logs '[{"category": "AuditEvent", "enabled": true, "retentionPolicy": {"enabled": true, "days": 90}}]'
```

#### Azure SQL Database

```bash
# Enable Azure SQL auditing to Log Analytics
az sql server audit-policy update \
  --resource-group rg-data-migration \
  --name sql-datamigration \
  --state Enabled \
  --lats Enabled \
  --lawri /subscriptions/<sub>/resourceGroups/rg-data-migration/providers/Microsoft.OperationalInsights/workspaces/law-migration
```

#### Azure Data Factory

```bash
az monitor diagnostic-settings create \
  --name adf-diagnostics \
  --resource /subscriptions/<sub>/resourceGroups/rg-data-migration/providers/Microsoft.DataFactory/factories/adf-datamigration \
  --workspace /subscriptions/<sub>/resourceGroups/rg-data-migration/providers/Microsoft.OperationalInsights/workspaces/law-migration \
  --logs '[{"category": "PipelineRuns", "enabled": true}, {"category": "ActivityRuns", "enabled": true}, {"category": "TriggerRuns", "enabled": true}]'
```

### Audit Queries (KQL)

#### Who accessed Key Vault secrets in the last 24 hours?

```kusto
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where OperationName == "SecretGet"
| where TimeGenerated > ago(24h)
| project TimeGenerated, CallerIPAddress, identity_claim_upn_s, id_s, ResultType
| order by TimeGenerated desc
```

#### Were any Key Vault access attempts denied?

```kusto
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where ResultType != "Success"
| where TimeGenerated > ago(7d)
| project TimeGenerated, OperationName, CallerIPAddress, identity_claim_upn_s, ResultType, ResultDescription
| order by TimeGenerated desc
```

#### What ADF pipelines ran and what was their status?

```kusto
ADFPipelineRun
| where TimeGenerated > ago(24h)
| project TimeGenerated, PipelineName, Status, RunStart, RunEnd, DurationInMs, Parameters
| order by TimeGenerated desc
```

---

## Agent-Specific Security

### Secrets Never Enter the LLM Context

The agent's tool calls follow this pattern to ensure secrets never appear in conversation:

```
1. Agent calls tool: discover_source_schema(source_type="oracle", schema_name="HR")
2. Logic App reads connection string from Key Vault (secret stays in Logic App runtime)
3. Logic App triggers ADF pipeline (ADF reads credentials from Key Vault linked service)
4. ADF connects to Oracle, queries metadata
5. ADF writes metadata JSON to Blob Storage
6. Logic App reads metadata JSON from Blob
7. Logic App returns metadata JSON to agent (no credentials in response)
```

At no point does the Oracle connection string, password, or any credential appear in:
- The agent's system prompt
- The tool call parameters
- The tool call response
- The conversation thread messages

### System Prompt Security Rules

The agent's system prompt includes explicit security instructions:

```
SECURITY RULES:
1. NEVER ask the user for database passwords, connection strings, or API keys
2. NEVER include credentials in your messages or tool call parameters
3. If a tool call fails due to authentication, tell the user to check Key Vault configuration
4. NEVER log, echo, or display connection strings returned by any tool
5. If a user provides a password in chat, warn them and advise using Key Vault instead
6. NEVER generate DDL that contains hardcoded passwords or connection information
7. All connection details are managed by Key Vault — you do not need them
```

### Tool Response Sanitization

Logic Apps sanitize tool responses before returning them to the agent:

- Connection strings are **never** included in Logic App HTTP responses
- Error messages from Azure SQL or ADF that might contain connection details are **redacted**
- Only metadata (table names, column names, data types) flows back to the agent

---

## Data Protection

### Encryption at Rest

| Service | Encryption | Key Management |
|---------|-----------|----------------|
| Azure SQL Database | TDE (Transparent Data Encryption) | Platform-managed keys (default) |
| Azure Blob Storage | AES-256 | Platform-managed keys (default) |
| Azure Key Vault | HSM-backed encryption | Platform-managed keys |
| Azure Table Storage | AES-256 | Platform-managed keys |
| AI Foundry conversation store | AES-256 | Platform-managed keys |

For production, consider **customer-managed keys (CMK)** for Azure SQL and Blob Storage.

### Encryption in Transit

| Connection | Protocol | Minimum Version |
|-----------|----------|-----------------|
| User → AI Foundry | HTTPS | TLS 1.2 |
| Agent → Logic Apps | HTTPS | TLS 1.2 |
| Logic Apps → Azure SQL | TDS over TLS | TLS 1.2 |
| Logic Apps → Key Vault | HTTPS | TLS 1.2 |
| ADF → Oracle (via SHIR) | Oracle Net (encrypted) | TLS 1.2 (configurable) |
| ADF → SQL Server (via SHIR) | TDS over TLS | TLS 1.2 |
| ADF → Azure SQL | TDS over TLS | TLS 1.2 |
| Self-Hosted IR → Azure | HTTPS | TLS 1.2 |

### Data Classification

| Data Category | Classification | Handling |
|---------------|---------------|----------|
| Source database credentials | **Confidential** | Key Vault only; never in logs, prompts, or code |
| Source schema metadata | **Internal** | Stored in Blob Storage; accessible to agent |
| Source table data (in transit) | **Per-data-owner classification** | Encrypted in transit; ADF handles |
| Migration DDL scripts | **Internal** | Stored in Blob Storage; reviewed by approver |
| Migration reports | **Internal** | Stored in Blob Storage; shared with operators |
| Approval decisions | **Internal** | Stored in Table Storage; audit logged |
| Agent conversation threads | **Internal** | Stored in AI Foundry; diagnostic logged |

---

## Compliance Checklist

Use this checklist before going to production:

### Secrets Management
- [ ] All credentials stored in Key Vault (no secrets in code, config, or prompts)
- [ ] Key Vault RBAC enabled (not access policies)
- [ ] Purge protection enabled on Key Vault
- [ ] Secret expiry dates configured
- [ ] Rotation schedule documented and calendared

### Identity
- [ ] System-assigned managed identity enabled on ADF, Logic Apps
- [ ] Azure SQL contained database users created for each managed identity
- [ ] No service principal secrets — managed identity only
- [ ] Entra ID security groups created for operators, approvers, admins
- [ ] Custom RBAC role for Migration Approver deployed

### Network
- [ ] Private endpoints deployed for Azure SQL, Key Vault, Blob Storage, ADF
- [ ] Public network access disabled on Azure SQL, Key Vault, Blob Storage
- [ ] Self-Hosted IR network requirements documented and firewall rules created
- [ ] NSG rules restrict source database access to SHIR subnet only
- [ ] DNS private zones configured for private endpoint resolution

### Logging
- [ ] Key Vault diagnostic logs enabled (AuditEvent category)
- [ ] ADF diagnostic logs enabled (PipelineRuns, ActivityRuns)
- [ ] Azure SQL auditing enabled to Log Analytics
- [ ] Logic App run history retention configured
- [ ] AI Foundry diagnostic logs enabled
- [ ] Alert rules created for denied Key Vault access and pipeline failures

### Agent Security
- [ ] Agent system prompt includes security rules (never ask for/display credentials)
- [ ] Logic App responses sanitized (no connection strings in HTTP responses)
- [ ] Tool call parameters do not include credentials
- [ ] Conversation threads do not persist after migration completion (or retention policy set)

### Data Protection
- [ ] TDE enabled on Azure SQL Database
- [ ] TLS 1.2 enforced on all connections
- [ ] Oracle Net encryption configured on Self-Hosted IR
- [ ] Customer-managed keys evaluated (for production)

---

## Related Documents

- [README.md](README.md) — Project overview, getting started, configuration
- [ARCHITECTURE.md](ARCHITECTURE.md) — Detailed architecture, data flows, and state machine
