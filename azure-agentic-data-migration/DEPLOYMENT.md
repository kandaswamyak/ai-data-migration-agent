# 🚀 Azure Agentic Data Migration — Deployment Guide

> **Version:** 1.0 · **Last Updated:** 2026-09-03  
> **Scope:** End-to-end deployment of the low-code/no-Python agentic data migration POC  
> **Target audience:** Cloud engineers, Azure administrators, migration leads

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites & Required Azure Resources](#2-prerequisites--required-azure-resources)
3. [Required Permissions & RBAC](#3-required-permissions--rbac)
4. [Resource Group & Networking Foundation](#4-resource-group--networking-foundation)
5. [Azure OpenAI / AI Foundry — Model Deployment](#5-azure-openai--ai-foundry--model-deployment)
6. [Azure Key Vault Setup](#6-azure-key-vault-setup)
7. [Managed Identity Configuration](#7-managed-identity-configuration)
8. [Azure SQL Database — Target Setup](#8-azure-sql-database--target-setup)
9. [Private Connectivity for Oracle & SQL Server](#9-private-connectivity-for-oracle--sql-server)
10. [Azure Data Factory & Self-Hosted Integration Runtime](#10-azure-data-factory--self-hosted-integration-runtime)
11. [Logic Apps Deployment — 5 Workflow Apps](#11-logic-apps-deployment--5-workflow-apps)
12. [AI Foundry Agent Configuration](#12-ai-foundry-agent-configuration)
13. [Application Insights & Monitoring](#13-application-insights--monitoring)
14. [Test Migration — Step-by-Step Dry Run](#14-test-migration--step-by-step-dry-run)
15. [Production Readiness Checklist](#15-production-readiness-checklist)
16. [Appendix: Resource Naming Conventions](#16-appendix-resource-naming-conventions)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         USER / TEAMS CHAT                           │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │  Conversational interface
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│              AZURE AI FOUNDRY AGENT SERVICE                         │
│  ┌────────────────────────────────────────────────────┐             │
│  │  Migration Agent (GPT-4.1)                         │             │
│  │  • System prompt: migration-agent-instructions.md  │             │
│  │  • Tools: 5 Logic Apps (HTTP-triggered)            │             │
│  │  • File search: mapping rules, type matrices       │             │
│  └────────────────────────────────────────────────────┘             │
└────────────┬───────────┬───────────┬──────────┬─────────────────────┘
             │           │           │          │
     ┌───────▼──┐  ┌─────▼────┐  ┌──▼───┐  ┌──▼──────────┐
     │ Logic App│  │Logic App │  │Logic │  │ Logic App   │
     │ Schema   │  │Migration │  │App   │  │ Validation  │
     │ Discovery│  │Plan Gen  │  │Approve│ │ & Reporting │
     └────┬─────┘  └────┬─────┘  └──┬───┘  └──┬──────────┘
          │              │           │          │
          ▼              ▼           ▼          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    AZURE DATA FACTORY                                │
│  • Self-Hosted Integration Runtime → Oracle / SQL Server on-prem    │
│  • Copy Activities, Data Flows, Schema Introspection                │
│  • Linked Services → Oracle, SQL Server, Azure SQL                  │
└──────────────────────────────────────────────────────────────────────┘
          │                                          │
          ▼                                          ▼
┌─────────────────┐                     ┌─────────────────────┐
│  Oracle DB      │                     │  Azure SQL Database  │
│  (on-premises)  │                     │  (migration target)  │
└─────────────────┘                     └─────────────────────┘
          │
┌─────────────────┐
│  SQL Server     │
│  (on-premises)  │
└─────────────────┘
```

**Key principle:** Zero custom Python. All orchestration is handled by Azure managed services — the AI Foundry agent reasons and delegates to Logic Apps, which orchestrate ADF pipelines, approval workflows, and validation queries.

---

## 2. Prerequisites & Required Azure Resources

### 2.1 Azure Subscription Requirements

| Requirement | Detail |
|-------------|--------|
| Subscription type | Pay-As-You-Go, Enterprise Agreement, or CSP |
| Region | **East US 2** or **West US 3** (GPT-4.1 availability) |
| Quota | Verify quota for Azure OpenAI GPT-4.1 tokens |
| Spending limit | Remove spending limit for production workloads |

### 2.2 Required Azure Resources

| # | Resource | SKU / Tier Recommendation | Purpose |
|---|----------|---------------------------|---------|
| 1 | **Resource Group** | — | `rg-data-migration-poc` — contains all resources |
| 2 | **Azure AI Foundry Hub** | Standard | AI project hub for agent management |
| 3 | **Azure AI Foundry Project** | Standard | Project within the hub for agent + model |
| 4 | **Azure OpenAI Service** | Standard S0 | GPT-4.1 model deployment |
| 5 | **Azure AI Agent Service** | Standard (within Foundry) | Hosts the migration agent |
| 6 | **Azure Key Vault** | Standard | Secrets: connection strings, API keys |
| 7 | **Azure Data Factory** | V2 | Data movement + schema introspection |
| 8 | **Self-Hosted Integration Runtime** | — (VM-based) | Connectivity to on-prem Oracle/SQL Server |
| 9 | **Azure SQL Database** | General Purpose, 4 vCores | Migration target database |
| 10 | **Azure SQL — Migration Metadata DB** | Basic (5 DTU) | Stores migration plans, status, audit logs |
| 11 | **Logic App (Standard)** — ×5 | WS1 (Workflow Standard) | Orchestration workflows |
| 12 | **Application Insights** | Per-GB ingestion | Logging, tracing, alerting |
| 13 | **Log Analytics Workspace** | Per-GB | Backing store for App Insights + diagnostics |
| 14 | **Virtual Network** | — | Network isolation, private endpoints |
| 15 | **VPN Gateway / ExpressRoute** | VpnGw1 / Standard | On-prem connectivity (if applicable) |
| 16 | **Storage Account** | Standard LRS, StorageV2 | ADF staging, Logic Apps backing storage |
| 17 | **Managed Identity** | System-assigned (per resource) | Passwordless auth across services |

### 2.3 On-Premises Requirements

| Component | Requirement |
|-----------|-------------|
| Oracle Database | 11g R2+ / 12c / 19c / 21c / 23ai / 26ai Free |
| SQL Server | 2016+ (any edition) |
| Self-Hosted IR VM | Windows Server 2019+, 4+ vCPU, 16 GB RAM, .NET 4.7.2+ |
| Network | Outbound HTTPS (443) to Azure; inbound not required |
| Oracle client | Oracle Instant Client or full client on SHIR VM |
| ODBC/OLEDB drivers | Microsoft OLE DB Driver for SQL Server on SHIR VM |

### 2.4 Estimated Monthly Cost (POC)

| Resource | Estimated Cost/Month |
|----------|---------------------|
| Azure OpenAI (GPT-4.1, ~100K tokens/day) | ~$50–$150 |
| Azure SQL (GP 4 vCores) | ~$370 |
| Azure SQL (Basic 5 DTU — metadata) | ~$5 |
| Data Factory (50 activity runs/day) | ~$25 |
| Logic Apps Standard (WS1) | ~$175 |
| VPN Gateway (VpnGw1) | ~$140 |
| Key Vault (Standard, <10K operations) | ~$1 |
| Storage Account (<10 GB) | ~$2 |
| Application Insights (<5 GB/month) | ~$12 |
| SHIR VM (D4s_v5 — if Azure-hosted) | ~$140 |
| **Total (POC estimate)** | **~$920–$1,020/month** |

---

## 3. Required Permissions & RBAC

### 3.1 Entra ID Roles (for the Deploying User)

| Role | Scope | Purpose |
|------|-------|---------|
| **Global Administrator** or **Application Administrator** | Tenant | Register managed identities, app registrations |
| **Owner** or **Contributor** | Subscription / Resource Group | Create and configure all Azure resources |
| **Key Vault Administrator** | Key Vault | Manage secrets, access policies |
| **Cognitive Services Contributor** | Azure OpenAI resource | Deploy models, manage agent |
| **User Access Administrator** | Resource Group | Assign RBAC roles to managed identities |

### 3.2 Azure RBAC Assignments (Post-Deployment)

| Principal (Managed Identity of…) | Role | Scope | Purpose |
|----------------------------------|------|-------|---------|
| Data Factory | **Key Vault Secrets User** | Key Vault | Read connection strings |
| Data Factory | **Storage Blob Data Contributor** | Storage Account | Staging area access |
| Logic App — Schema Discovery | **Data Factory Contributor** | ADF | Trigger pipelines |
| Logic App — Schema Discovery | **Key Vault Secrets User** | Key Vault | Read secrets |
| Logic App — Migration Plan | **Key Vault Secrets User** | Key Vault | Read secrets |
| Logic App — Migration Plan | **Cognitive Services OpenAI User** | OpenAI resource | Call GPT-4.1 for plan generation |
| Logic App — Migration Executor | **Data Factory Contributor** | ADF | Trigger copy pipelines |
| Logic App — Migration Executor | **Key Vault Secrets User** | Key Vault | Read secrets |
| Logic App — Approval | **Key Vault Secrets User** | Key Vault | Read secrets |
| Logic App — Validation | **SQL DB Contributor** | Azure SQL | Run validation queries |
| Logic App — Validation | **Key Vault Secrets User** | Key Vault | Read secrets |
| AI Foundry Agent (MI) | **Cognitive Services OpenAI User** | OpenAI resource | Invoke GPT-4.1 |
| AI Foundry Agent (MI) | **Key Vault Secrets User** | Key Vault | Read API keys |

### 3.3 Database-Level Permissions

| Database | User/Principal | Permissions |
|----------|---------------|-------------|
| Oracle (source) | Migration service account | `SELECT ANY TABLE`, `SELECT_CATALOG_ROLE` |
| SQL Server (source) | Migration service account | `db_datareader` on target databases |
| Azure SQL (target) | ADF Managed Identity | `db_owner` (for DDL + DML during migration) |
| Azure SQL (metadata) | Logic App Managed Identities | `db_datareader`, `db_datawriter` |

### 3.4 Verifying Role Assignments

```bash
# List all role assignments in the resource group
az role assignment list \
  --resource-group rg-data-migration-poc \
  --output table

# Verify a specific managed identity's roles
az role assignment list \
  --assignee <principal-id> \
  --output table
```

---

## 4. Resource Group & Networking Foundation

### 4.1 Create the Resource Group

```bash
az group create \
  --name rg-data-migration-poc \
  --location eastus2 \
  --tags project=agentic-migration environment=poc owner=<your-alias>
```

### 4.2 Create the Virtual Network

```bash
az network vnet create \
  --resource-group rg-data-migration-poc \
  --name vnet-migration \
  --address-prefix 10.0.0.0/16 \
  --subnet-name snet-default \
  --subnet-prefix 10.0.1.0/24

# Subnet for Private Endpoints
az network vnet subnet create \
  --resource-group rg-data-migration-poc \
  --vnet-name vnet-migration \
  --name snet-private-endpoints \
  --address-prefix 10.0.2.0/24 \
  --disable-private-endpoint-network-policies true

# Subnet for Self-Hosted Integration Runtime VM
az network vnet subnet create \
  --resource-group rg-data-migration-poc \
  --vnet-name vnet-migration \
  --name snet-shir \
  --address-prefix 10.0.3.0/24

# Subnet for Logic Apps (VNet-integrated)
az network vnet subnet create \
  --resource-group rg-data-migration-poc \
  --vnet-name vnet-migration \
  --name snet-logic-apps \
  --address-prefix 10.0.4.0/24 \
  --delegations Microsoft.Web/serverFarms
```

### 4.3 Create Network Security Groups

```bash
# NSG for SHIR subnet
az network nsg create \
  --resource-group rg-data-migration-poc \
  --name nsg-shir

az network nsg rule create \
  --resource-group rg-data-migration-poc \
  --nsg-name nsg-shir \
  --name Allow-HTTPS-Outbound \
  --priority 100 \
  --direction Outbound \
  --access Allow \
  --protocol Tcp \
  --destination-port-ranges 443

az network vnet subnet update \
  --resource-group rg-data-migration-poc \
  --vnet-name vnet-migration \
  --name snet-shir \
  --network-security-group nsg-shir

# NSG for Private Endpoints subnet
az network nsg create \
  --resource-group rg-data-migration-poc \
  --name nsg-private-endpoints

az network vnet subnet update \
  --resource-group rg-data-migration-poc \
  --vnet-name vnet-migration \
  --name snet-private-endpoints \
  --network-security-group nsg-private-endpoints
```

### 4.4 Create Log Analytics Workspace

```bash
az monitor log-analytics workspace create \
  --resource-group rg-data-migration-poc \
  --workspace-name law-migration-poc \
  --location eastus2 \
  --retention-time 90
```

### 4.5 Create Application Insights

```bash
az monitor app-insights component create \
  --app appi-migration-poc \
  --location eastus2 \
  --resource-group rg-data-migration-poc \
  --workspace law-migration-poc \
  --kind web
```

### 4.6 Create Storage Account

```bash
az storage account create \
  --name stmigrationpoc \
  --resource-group rg-data-migration-poc \
  --location eastus2 \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false
```

---

## 5. Azure OpenAI / AI Foundry — Model Deployment

### 5.1 Create Azure OpenAI Resource

```bash
az cognitiveservices account create \
  --name oai-migration-poc \
  --resource-group rg-data-migration-poc \
  --kind OpenAI \
  --sku S0 \
  --location eastus2 \
  --custom-domain oai-migration-poc \
  --yes
```

### 5.2 Deploy GPT-4.1 Model

```bash
az cognitiveservices account deployment create \
  --name oai-migration-poc \
  --resource-group rg-data-migration-poc \
  --deployment-name gpt-41-migration \
  --model-name gpt-4.1 \
  --model-version "2025-04-14" \
  --model-format OpenAI \
  --sku-capacity 80 \
  --sku-name Standard
```

> **Why GPT-4.1?** It provides the best function-calling accuracy, long-context reasoning (1M tokens), and structured output for migration plan generation. It excels at multi-step tool orchestration required by the agent.

### 5.3 Create AI Foundry Hub & Project

1. Navigate to [Azure AI Foundry Portal](https://ai.azure.com)
2. Click **+ New hub** → select your subscription and `rg-data-migration-poc`
3. Configure the hub:
   - **Name:** `aih-migration-poc`
   - **Region:** East US 2
   - **Storage account:** select `stmigrationpoc`
   - **Key Vault:** select `kv-migration-poc`
   - **Application Insights:** select `appi-migration-poc`
4. Connect your existing Azure OpenAI resource (`oai-migration-poc`)
5. Create a **Project** inside the hub: `aiproj-migration-poc`
6. Verify the GPT-4.1 deployment appears under **Models + endpoints**

### 5.4 Verify Model Deployment

```bash
# Check deployment status
az cognitiveservices account deployment show \
  --name oai-migration-poc \
  --resource-group rg-data-migration-poc \
  --deployment-name gpt-41-migration

# Quick API test
curl -X POST "https://oai-migration-poc.openai.azure.com/openai/deployments/gpt-41-migration/chat/completions?api-version=2025-01-01-preview" \
  -H "Content-Type: application/json" \
  -H "api-key: $(az cognitiveservices account keys list --name oai-migration-poc --resource-group rg-data-migration-poc --query key1 -o tsv)" \
  -d '{"messages":[{"role":"user","content":"Say hello"}],"max_tokens":50}'
```

---

## 6. Azure Key Vault Setup

### 6.1 Create Key Vault

```bash
az keyvault create \
  --name kv-migration-poc \
  --resource-group rg-data-migration-poc \
  --location eastus2 \
  --sku standard \
  --enable-rbac-authorization true \
  --enable-purge-protection true \
  --enable-soft-delete true \
  --retention-days 90
```

### 6.2 Store All Required Secrets

```bash
# ── Oracle Source Connection ──
az keyvault secret set --vault-name kv-migration-poc \
  --name "oracle-host" --value "<oracle-server-ip-or-hostname>"

az keyvault secret set --vault-name kv-migration-poc \
  --name "oracle-port" --value "1521"

az keyvault secret set --vault-name kv-migration-poc \
  --name "oracle-service-name" --value "FREEPDB1"

az keyvault secret set --vault-name kv-migration-poc \
  --name "oracle-username" --value "<oracle-migration-user>"

az keyvault secret set --vault-name kv-migration-poc \
  --name "oracle-password" --value "<oracle-password>"

az keyvault secret set --vault-name kv-migration-poc \
  --name "oracle-connection-string" \
  --value "Host=<host>;Port=1521;SID=FREE;User Id=<user>;Password=<password>"

# ── SQL Server Source Connection ──
az keyvault secret set --vault-name kv-migration-poc \
  --name "sqlserver-host" --value "<sqlserver-hostname>"

az keyvault secret set --vault-name kv-migration-poc \
  --name "sqlserver-port" --value "1433"

az keyvault secret set --vault-name kv-migration-poc \
  --name "sqlserver-database" --value "MigrationDemo"

az keyvault secret set --vault-name kv-migration-poc \
  --name "sqlserver-username" --value "<sqlserver-user>"

az keyvault secret set --vault-name kv-migration-poc \
  --name "sqlserver-password" --value "<sqlserver-password>"

az keyvault secret set --vault-name kv-migration-poc \
  --name "sqlserver-connection-string" \
  --value "Server=<host>,1433;Database=MigrationDemo;User Id=<user>;Password=<password>;Encrypt=true;TrustServerCertificate=true"

# ── Azure SQL Target Connection ──
az keyvault secret set --vault-name kv-migration-poc \
  --name "azuresql-server" --value "sql-migration-poc.database.windows.net"

az keyvault secret set --vault-name kv-migration-poc \
  --name "azuresql-database" --value "sqldb-migration-target"

az keyvault secret set --vault-name kv-migration-poc \
  --name "azuresql-connection-string" \
  --value "Server=tcp:sql-migration-poc.database.windows.net,1433;Database=sqldb-migration-target;Authentication=Active Directory Managed Identity;Encrypt=true;"

# ── Azure SQL Metadata DB ──
az keyvault secret set --vault-name kv-migration-poc \
  --name "azuresql-metadata-connection-string" \
  --value "Server=tcp:sql-migration-poc.database.windows.net,1433;Database=sqldb-migration-metadata;Authentication=Active Directory Managed Identity;Encrypt=true;"

# ── Azure OpenAI ──
az keyvault secret set --vault-name kv-migration-poc \
  --name "openai-api-key" \
  --value "$(az cognitiveservices account keys list --name oai-migration-poc --resource-group rg-data-migration-poc --query key1 -o tsv)"

az keyvault secret set --vault-name kv-migration-poc \
  --name "openai-endpoint" \
  --value "https://oai-migration-poc.openai.azure.com/"

# ── ADF Resource ID ──
az keyvault secret set --vault-name kv-migration-poc \
  --name "adf-resource-id" \
  --value "/subscriptions/<sub-id>/resourceGroups/rg-data-migration-poc/providers/Microsoft.DataFactory/factories/adf-migration-poc"

# ── Logic Apps Callback URLs (populated after deployment — see Section 11) ──
az keyvault secret set --vault-name kv-migration-poc \
  --name "logic-app-schema-discovery-url" --value "PLACEHOLDER"
az keyvault secret set --vault-name kv-migration-poc \
  --name "logic-app-migration-plan-url" --value "PLACEHOLDER"
az keyvault secret set --vault-name kv-migration-poc \
  --name "logic-app-approval-url" --value "PLACEHOLDER"
az keyvault secret set --vault-name kv-migration-poc \
  --name "logic-app-migration-executor-url" --value "PLACEHOLDER"
az keyvault secret set --vault-name kv-migration-poc \
  --name "logic-app-validation-url" --value "PLACEHOLDER"
```

### 6.3 Secret Inventory

| Secret Name | Description | Source |
|-------------|-------------|--------|
| `oracle-host` | Oracle server hostname/IP | On-prem DBA |
| `oracle-port` | Oracle listener port (default 1521) | On-prem DBA |
| `oracle-service-name` | Oracle service name (e.g., FREEPDB1) | On-prem DBA |
| `oracle-username` | Oracle migration service account | On-prem DBA |
| `oracle-password` | Oracle service account password | On-prem DBA |
| `oracle-connection-string` | Full Oracle connection string | Generated |
| `sqlserver-host` | SQL Server hostname | On-prem DBA |
| `sqlserver-port` | SQL Server port (default 1433) | On-prem DBA |
| `sqlserver-database` | Source database name | On-prem DBA |
| `sqlserver-username` | SQL Server migration account | On-prem DBA |
| `sqlserver-password` | SQL Server account password | On-prem DBA |
| `sqlserver-connection-string` | Full SQL Server connection string | Generated |
| `azuresql-server` | Azure SQL server FQDN | Azure Portal |
| `azuresql-database` | Target database name | Azure Portal |
| `azuresql-connection-string` | Azure SQL with MI auth | Generated |
| `azuresql-metadata-connection-string` | Metadata DB with MI auth | Generated |
| `openai-api-key` | Azure OpenAI API key | Azure Portal |
| `openai-endpoint` | Azure OpenAI endpoint URL | Azure Portal |
| `adf-resource-id` | ADF full resource ID | Azure Portal |
| `logic-app-*-url` | Logic App HTTP trigger URLs (×5) | Post-deployment |

### 6.4 Private Endpoint for Key Vault

```bash
az network private-endpoint create \
  --name pe-kv-migration \
  --resource-group rg-data-migration-poc \
  --vnet-name vnet-migration \
  --subnet snet-private-endpoints \
  --private-connection-resource-id $(az keyvault show --name kv-migration-poc --resource-group rg-data-migration-poc --query id -o tsv) \
  --group-id vault \
  --connection-name pec-kv-migration

az network private-dns zone create \
  --resource-group rg-data-migration-poc \
  --name privatelink.vaultcore.azure.net

az network private-dns link vnet create \
  --resource-group rg-data-migration-poc \
  --zone-name privatelink.vaultcore.azure.net \
  --name link-kv-migration \
  --virtual-network vnet-migration \
  --registration-enabled false
```

---

## 7. Managed Identity Configuration

### 7.1 Why Managed Identities?

Every service-to-service call in this architecture uses **system-assigned managed identities** — no passwords stored in code, no credential rotation burden, and full Entra ID audit trail.

### 7.2 Enable System-Assigned MI on Each Resource

Managed identities are enabled during resource creation. For existing resources:

```bash
# Azure Data Factory — enabled during creation, verify:
az datafactory show \
  --resource-group rg-data-migration-poc \
  --factory-name adf-migration-poc \
  --query identity

# Logic Apps (Standard) — enabled by default on creation, verify:
for APP_NAME in logic-schema-discovery logic-migration-plan logic-approval-workflow logic-migration-executor logic-validation-report; do
  echo "=== $APP_NAME ==="
  az functionapp identity show \
    --name $APP_NAME \
    --resource-group rg-data-migration-poc \
    --query principalId -o tsv
done
```

### 7.3 RBAC Role Assignments

```bash
# ── Retrieve Principal IDs ──
ADF_PRINCIPAL=$(az datafactory show --name adf-migration-poc \
  --resource-group rg-data-migration-poc --query identity.principalId -o tsv)

LA_SCHEMA=$(az functionapp identity show --name logic-schema-discovery \
  --resource-group rg-data-migration-poc --query principalId -o tsv)
LA_PLAN=$(az functionapp identity show --name logic-migration-plan \
  --resource-group rg-data-migration-poc --query principalId -o tsv)
LA_APPROVAL=$(az functionapp identity show --name logic-approval-workflow \
  --resource-group rg-data-migration-poc --query principalId -o tsv)
LA_EXECUTOR=$(az functionapp identity show --name logic-migration-executor \
  --resource-group rg-data-migration-poc --query principalId -o tsv)
LA_VALIDATION=$(az functionapp identity show --name logic-validation-report \
  --resource-group rg-data-migration-poc --query principalId -o tsv)

# ── Retrieve Resource IDs ──
KV_ID=$(az keyvault show --name kv-migration-poc \
  --resource-group rg-data-migration-poc --query id -o tsv)
ADF_ID=$(az datafactory show --name adf-migration-poc \
  --resource-group rg-data-migration-poc --query id -o tsv)
SQL_ID=$(az sql server show --name sql-migration-poc \
  --resource-group rg-data-migration-poc --query id -o tsv)
STORAGE_ID=$(az storage account show --name stmigrationpoc \
  --resource-group rg-data-migration-poc --query id -o tsv)
OAI_ID=$(az cognitiveservices account show --name oai-migration-poc \
  --resource-group rg-data-migration-poc --query id -o tsv)

# ── Key Vault Secrets User → All services ──
for PRINCIPAL in $ADF_PRINCIPAL $LA_SCHEMA $LA_PLAN $LA_APPROVAL $LA_EXECUTOR $LA_VALIDATION; do
  az role assignment create \
    --assignee-object-id $PRINCIPAL \
    --assignee-principal-type ServicePrincipal \
    --role "Key Vault Secrets User" \
    --scope $KV_ID
done

# ── Data Factory Contributor → Logic Apps that trigger pipelines ──
for PRINCIPAL in $LA_SCHEMA $LA_EXECUTOR; do
  az role assignment create \
    --assignee-object-id $PRINCIPAL \
    --assignee-principal-type ServicePrincipal \
    --role "Data Factory Contributor" \
    --scope $ADF_ID
done

# ── Storage Blob Data Contributor → ADF ──
az role assignment create \
  --assignee-object-id $ADF_PRINCIPAL \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope $STORAGE_ID

# ── SQL DB Contributor → Validation Logic App ──
az role assignment create \
  --assignee-object-id $LA_VALIDATION \
  --assignee-principal-type ServicePrincipal \
  --role "SQL DB Contributor" \
  --scope $SQL_ID

# ── Cognitive Services OpenAI User → Migration Plan Logic App ──
az role assignment create \
  --assignee-object-id $LA_PLAN \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope $OAI_ID
```

### 7.4 Azure SQL — Add Managed Identities as Database Users

Connect to Azure SQL (via SSMS, Azure Data Studio, or `sqlcmd`) and run:

```sql
-- ════════════════════════════════════════════
-- TARGET DATABASE: sqldb-migration-target
-- ════════════════════════════════════════════
USE [sqldb-migration-target];

CREATE USER [adf-migration-poc] FROM EXTERNAL PROVIDER;
ALTER ROLE db_owner ADD MEMBER [adf-migration-poc];

CREATE USER [logic-validation-report] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [logic-validation-report];
GO

-- ════════════════════════════════════════════
-- METADATA DATABASE: sqldb-migration-metadata
-- ════════════════════════════════════════════
USE [sqldb-migration-metadata];

CREATE USER [logic-schema-discovery] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datawriter ADD MEMBER [logic-schema-discovery];
ALTER ROLE db_datareader ADD MEMBER [logic-schema-discovery];

CREATE USER [logic-migration-plan] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datawriter ADD MEMBER [logic-migration-plan];
ALTER ROLE db_datareader ADD MEMBER [logic-migration-plan];

CREATE USER [logic-migration-executor] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datawriter ADD MEMBER [logic-migration-executor];
ALTER ROLE db_datareader ADD MEMBER [logic-migration-executor];

CREATE USER [logic-approval-workflow] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datawriter ADD MEMBER [logic-approval-workflow];
ALTER ROLE db_datareader ADD MEMBER [logic-approval-workflow];

CREATE USER [logic-validation-report] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datawriter ADD MEMBER [logic-validation-report];
ALTER ROLE db_datareader ADD MEMBER [logic-validation-report];
GO
```

---

## 8. Azure SQL Database — Target Setup

### 8.1 Create the Azure SQL Server

```bash
az sql server create \
  --name sql-migration-poc \
  --resource-group rg-data-migration-poc \
  --location eastus2 \
  --enable-ad-only-auth \
  --external-admin-principal-type User \
  --external-admin-name "<your-entra-admin-upn>" \
  --external-admin-sid "<your-entra-admin-object-id>"
```

### 8.2 Create Target Database

```bash
az sql db create \
  --resource-group rg-data-migration-poc \
  --server sql-migration-poc \
  --name sqldb-migration-target \
  --service-objective GP_Gen5_4 \
  --max-size 100GB \
  --zone-redundant false \
  --backup-storage-redundancy Local
```

### 8.3 Create Metadata Database

```bash
az sql db create \
  --resource-group rg-data-migration-poc \
  --server sql-migration-poc \
  --name sqldb-migration-metadata \
  --service-objective Basic \
  --max-size 2GB
```

### 8.4 Initialize Metadata Schema

Connect to `sqldb-migration-metadata` and run:

```sql
-- ════════════════════════════════════════════
-- MIGRATION METADATA SCHEMA
-- ════════════════════════════════════════════

-- Migration jobs tracking
CREATE TABLE dbo.MigrationJobs (
    JobId          UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    SourceType     NVARCHAR(50)     NOT NULL,  -- 'Oracle' or 'SQLServer'
    SourceHost     NVARCHAR(255)    NOT NULL,
    SourceDatabase NVARCHAR(255)    NOT NULL,
    TargetDatabase NVARCHAR(255)    NOT NULL,
    Status         NVARCHAR(50)     NOT NULL DEFAULT 'Pending',
        -- Pending → SchemaDiscovered → PlanGenerated → AwaitingApproval
        -- → Approved → Executing → Completed → Validated
        -- or → Rejected / Failed / PartialFailure / Cancelled
    CreatedAt      DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt      DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CreatedBy      NVARCHAR(255)    NULL,
    MigrationPlan  NVARCHAR(MAX)    NULL,  -- JSON document
    ApprovalStatus NVARCHAR(50)     NULL,
    ApprovedBy     NVARCHAR(255)    NULL,
    ApprovedAt     DATETIME2        NULL,
    CompletedAt    DATETIME2        NULL,
    ErrorMessage   NVARCHAR(MAX)    NULL
);

-- Schema discovery results
CREATE TABLE dbo.DiscoveredSchemas (
    SchemaId       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    JobId          UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.MigrationJobs(JobId),
    SourceSchema   NVARCHAR(255)    NOT NULL,
    TableName      NVARCHAR(255)    NOT NULL,
    ColumnName     NVARCHAR(255)    NOT NULL,
    SourceDataType NVARCHAR(255)    NOT NULL,
    IsNullable     BIT              NOT NULL,
    MaxLength      INT              NULL,
    NumericPrecision INT            NULL,
    NumericScale   INT              NULL,
    IsPrimaryKey   BIT              NOT NULL DEFAULT 0,
    ForeignKeyRef  NVARCHAR(500)    NULL,
    DiscoveredAt   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME()
);

-- AI-generated mapping decisions
CREATE TABLE dbo.SchemaMappings (
    MappingId        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    JobId            UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.MigrationJobs(JobId),
    SourceSchema     NVARCHAR(255)    NOT NULL,
    SourceTable      NVARCHAR(255)    NOT NULL,
    SourceColumn     NVARCHAR(255)    NOT NULL,
    SourceDataType   NVARCHAR(255)    NOT NULL,
    TargetSchema     NVARCHAR(255)    NOT NULL DEFAULT 'dbo',
    TargetTable      NVARCHAR(255)    NOT NULL,
    TargetColumn     NVARCHAR(255)    NOT NULL,
    TargetDataType   NVARCHAR(255)    NOT NULL,
    MappingConfidence DECIMAL(5,2)    NULL,  -- 0.00 to 100.00
    MappingNotes     NVARCHAR(MAX)    NULL,
    DDLStatement     NVARCHAR(MAX)    NULL,
    CreatedAt        DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME()
);

-- Post-migration validation results
CREATE TABLE dbo.ValidationResults (
    ValidationId   UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    JobId          UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.MigrationJobs(JobId),
    TableName      NVARCHAR(255)    NOT NULL,
    CheckType      NVARCHAR(100)    NOT NULL,
        -- 'RowCount', 'Checksum', 'SampleData', 'NullCheck', 'SchemaCompare'
    SourceValue    NVARCHAR(MAX)    NULL,
    TargetValue    NVARCHAR(MAX)    NULL,
    IsMatch        BIT              NOT NULL,
    Details        NVARCHAR(MAX)    NULL,
    ValidatedAt    DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME()
);

-- Detailed migration execution log
CREATE TABLE dbo.MigrationLog (
    LogId          BIGINT IDENTITY(1,1) PRIMARY KEY,
    JobId          UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.MigrationJobs(JobId),
    StepName       NVARCHAR(255)    NOT NULL,
    Status         NVARCHAR(50)     NOT NULL,  -- 'Started','Completed','Failed'
    Message        NVARCHAR(MAX)    NULL,
    DurationMs     BIGINT           NULL,
    RowsAffected   BIGINT           NULL,
    AdfPipelineRunId NVARCHAR(255)  NULL,
    LoggedAt       DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME()
);

-- ── Indexes ──
CREATE INDEX IX_DiscoveredSchemas_JobId ON dbo.DiscoveredSchemas(JobId);
CREATE INDEX IX_SchemaMappings_JobId ON dbo.SchemaMappings(JobId);
CREATE INDEX IX_ValidationResults_JobId ON dbo.ValidationResults(JobId);
CREATE INDEX IX_MigrationLog_JobId ON dbo.MigrationLog(JobId);
CREATE INDEX IX_MigrationJobs_Status ON dbo.MigrationJobs(Status);
CREATE INDEX IX_MigrationLog_StepStatus ON dbo.MigrationLog(StepName, Status);
GO

PRINT 'Metadata schema initialized successfully.';
```

### 8.5 Private Endpoint for Azure SQL

```bash
az network private-endpoint create \
  --name pe-sql-migration \
  --resource-group rg-data-migration-poc \
  --vnet-name vnet-migration \
  --subnet snet-private-endpoints \
  --private-connection-resource-id $(az sql server show --name sql-migration-poc \
    --resource-group rg-data-migration-poc --query id -o tsv) \
  --group-id sqlServer \
  --connection-name pec-sql-migration

az network private-dns zone create \
  --resource-group rg-data-migration-poc \
  --name privatelink.database.windows.net

az network private-dns link vnet create \
  --resource-group rg-data-migration-poc \
  --zone-name privatelink.database.windows.net \
  --name link-sql-migration \
  --virtual-network vnet-migration \
  --registration-enabled false

az network private-endpoint dns-zone-group create \
  --resource-group rg-data-migration-poc \
  --endpoint-name pe-sql-migration \
  --name sqlZoneGroup \
  --private-dns-zone privatelink.database.windows.net \
  --zone-name privatelink.database.windows.net
```

### 8.6 Disable Public Network Access

```bash
az sql server update \
  --name sql-migration-poc \
  --resource-group rg-data-migration-poc \
  --set publicNetworkAccess="Disabled"
```

---

## 9. Private Connectivity for Oracle & SQL Server

### 9.1 Connectivity Options

| Option | Best For | Latency | Cost |
|--------|----------|---------|------|
| **Site-to-Site VPN** | POC, small migrations | 10–50 ms | ~$140/mo (VpnGw1) |
| **Azure ExpressRoute** | Production, large data volumes | 1–5 ms | ~$300+/mo |
| **SHIR only** (public internet) | Quick POC, encrypted tunnel | Variable | VM cost only |

> **For POC:** A Site-to-Site VPN is recommended. For quick testing, the Self-Hosted Integration Runtime creates its own encrypted outbound tunnel and does not require VPN — it only needs outbound HTTPS (443) to Azure.

### 9.2 VPN Gateway Setup (Recommended for POC)

```bash
# Public IP for VPN Gateway
az network public-ip create \
  --name pip-vpn-gateway \
  --resource-group rg-data-migration-poc \
  --allocation-method Static \
  --sku Standard

# Gateway subnet (required name: GatewaySubnet)
az network vnet subnet create \
  --resource-group rg-data-migration-poc \
  --vnet-name vnet-migration \
  --name GatewaySubnet \
  --address-prefix 10.0.255.0/27

# Create VPN Gateway (takes 30–45 minutes)
az network vnet-gateway create \
  --name vpng-migration \
  --resource-group rg-data-migration-poc \
  --vnet vnet-migration \
  --gateway-type Vpn \
  --sku VpnGw1 \
  --vpn-type RouteBased \
  --public-ip-address pip-vpn-gateway \
  --no-wait

# Local Network Gateway (represents your on-prem network)
az network local-gateway create \
  --name lgw-onprem \
  --resource-group rg-data-migration-poc \
  --gateway-ip-address <your-onprem-public-ip> \
  --local-address-prefixes <onprem-cidr-e.g.-192.168.0.0/16>

# Wait for VPN Gateway to finish, then create connection
az network vpn-connection create \
  --name conn-onprem \
  --resource-group rg-data-migration-poc \
  --vnet-gateway1 vpng-migration \
  --local-gateway2 lgw-onprem \
  --shared-key <your-shared-key> \
  --connection-protocol IKEv2
```

### 9.3 Verify VPN Connectivity

```bash
# Check connection status
az network vpn-connection show \
  --name conn-onprem \
  --resource-group rg-data-migration-poc \
  --query connectionStatus -o tsv
# Expected: "Connected"
```

### 9.4 Network Security Group Rules for SHIR Subnet

```bash
# Allow Oracle traffic from SHIR → on-prem Oracle
az network nsg rule create \
  --resource-group rg-data-migration-poc \
  --nsg-name nsg-shir \
  --name Allow-Oracle-1521 \
  --priority 110 \
  --direction Outbound \
  --access Allow \
  --protocol Tcp \
  --destination-port-ranges 1521 \
  --destination-address-prefixes <oracle-server-ip>/32

# Allow SQL Server traffic from SHIR → on-prem SQL Server
az network nsg rule create \
  --resource-group rg-data-migration-poc \
  --nsg-name nsg-shir \
  --name Allow-SQLServer-1433 \
  --priority 120 \
  --direction Outbound \
  --access Allow \
  --protocol Tcp \
  --destination-port-ranges 1433 \
  --destination-address-prefixes <sqlserver-ip>/32

# Allow Azure Service Bus (required by SHIR for relay)
az network nsg rule create \
  --resource-group rg-data-migration-poc \
  --nsg-name nsg-shir \
  --name Allow-ServiceBus-443 \
  --priority 130 \
  --direction Outbound \
  --access Allow \
  --protocol Tcp \
  --destination-port-ranges 443 \
  --destination-address-prefixes ServiceBus
```

---

## 10. Azure Data Factory & Self-Hosted Integration Runtime

### 10.1 Create Data Factory

```bash
az datafactory create \
  --resource-group rg-data-migration-poc \
  --factory-name adf-migration-poc \
  --location eastus2 \
  --identity-type SystemAssigned
```

### 10.2 Create Self-Hosted Integration Runtime

```bash
# Create the IR definition in ADF
az datafactory integration-runtime self-hosted create \
  --resource-group rg-data-migration-poc \
  --factory-name adf-migration-poc \
  --integration-runtime-name ir-onprem-shir

# Retrieve authentication keys (save these — needed for VM registration)
az datafactory integration-runtime list-auth-key \
  --resource-group rg-data-migration-poc \
  --factory-name adf-migration-poc \
  --integration-runtime-name ir-onprem-shir
```

### 10.3 SHIR VM Requirements

| Spec | Minimum | Recommended |
|------|---------|-------------|
| OS | Windows Server 2019 | Windows Server 2022 |
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB |
| Disk | 80 GB SSD | 128 GB SSD |
| .NET | 4.7.2+ | 4.8.1 |
| Network | Outbound HTTPS to Azure | Outbound HTTPS + VPN |

### 10.4 Provision SHIR VM (Azure-Hosted Option)

```bash
az vm create \
  --resource-group rg-data-migration-poc \
  --name vm-shir-01 \
  --image MicrosoftWindowsServer:WindowsServer:2022-datacenter-g2:latest \
  --size Standard_D4s_v5 \
  --vnet-name vnet-migration \
  --subnet snet-shir \
  --nsg nsg-shir \
  --admin-username shiradmin \
  --admin-password "<strong-password>" \
  --public-ip-address "" \
  --os-disk-size-gb 128
```

### 10.5 Install SHIR on the VM

RDP into `vm-shir-01` and perform:

1. **Download** the Self-Hosted Integration Runtime installer:
   ```
   https://www.microsoft.com/en-us/download/details.aspx?id=39717
   ```

2. **Install** and **register** using the authentication key from step 10.2

3. **Install Oracle Instant Client** on the SHIR VM:
   ```powershell
   # Download Oracle Instant Client (Basic + ODBC) from:
   # https://www.oracle.com/database/technologies/instant-client/winx64-64-downloads.html
   # Extract to C:\oracle\instantclient_21_x

   [Environment]::SetEnvironmentVariable("PATH",
     $env:PATH + ";C:\oracle\instantclient_21_x", "Machine")
   [Environment]::SetEnvironmentVariable("TNS_ADMIN",
     "C:\oracle\instantclient_21_x\network\admin", "Machine")
   ```

4. **Install SQL Server OLE DB driver**:
   ```powershell
   # Download from: https://go.microsoft.com/fwlink/?linkid=2249006
   # Install "Microsoft OLE DB Driver 19 for SQL Server"
   ```

5. **Restart** the Integration Runtime Service:
   ```powershell
   Restart-Service DIAHostService
   ```

6. **Verify** in ADF Portal → Manage → Integration Runtimes:
   - Status should show **Running** with a green check

### 10.6 Create ADF Linked Services

Navigate to ADF Studio → Manage → Linked Services → **+ New**:

**Key Vault Linked Service** (create this first):

| Setting | Value |
|---------|-------|
| Name | `ls_keyvault` |
| Type | Azure Key Vault |
| Base URL | `https://kv-migration-poc.vault.azure.net/` |
| Authentication | System-assigned managed identity |

**Oracle Linked Service:**

| Setting | Value |
|---------|-------|
| Name | `ls_oracle_source` |
| Type | Oracle |
| Connection string | Reference: `ls_keyvault` → Secret: `oracle-connection-string` |
| Integration Runtime | `ir-onprem-shir` |

**SQL Server Linked Service:**

| Setting | Value |
|---------|-------|
| Name | `ls_sqlserver_source` |
| Type | SQL Server |
| Connection string | Reference: `ls_keyvault` → Secret: `sqlserver-connection-string` |
| Integration Runtime | `ir-onprem-shir` |

**Azure SQL — Target:**

| Setting | Value |
|---------|-------|
| Name | `ls_azuresql_target` |
| Type | Azure SQL Database |
| Connection string | Reference: `ls_keyvault` → Secret: `azuresql-connection-string` |
| Integration Runtime | AutoResolveIntegrationRuntime |

**Azure SQL — Metadata:**

| Setting | Value |
|---------|-------|
| Name | `ls_azuresql_metadata` |
| Type | Azure SQL Database |
| Connection string | Reference: `ls_keyvault` → Secret: `azuresql-metadata-connection-string` |
| Integration Runtime | AutoResolveIntegrationRuntime |

### 10.7 Test All Linked Services

In ADF Studio, click **Test connection** on each linked service. All must show ✅ **Connection successful**.

### 10.8 Create ADF Pipelines

Create these parameterized pipelines in ADF Studio:

| Pipeline Name | Purpose | Key Parameters |
|--------------|---------|----------------|
| `pl_schema_discovery_oracle` | Introspect Oracle ALL_TAB_COLUMNS | `schemaName`, `jobId` |
| `pl_schema_discovery_sqlserver` | Introspect SQL Server INFORMATION_SCHEMA | `databaseName`, `schemaName`, `jobId` |
| `pl_copy_table_oracle` | Copy single table Oracle → Azure SQL | `sourceSchema`, `sourceTable`, `targetSchema`, `targetTable`, `jobId` |
| `pl_copy_table_sqlserver` | Copy single table SQL Server → Azure SQL | `sourceSchema`, `sourceTable`, `targetSchema`, `targetTable`, `jobId` |
| `pl_migrate_batch` | Orchestrate batch table copy (ForEach) | `jobId`, `tables` (JSON array) |
| `pl_validate_rowcounts` | Compare row counts source vs target | `jobId`, `tables` (JSON array) |
| `pl_execute_ddl` | Run DDL statements on Azure SQL target | `ddlStatements` (JSON array) |

---

## 11. Logic Apps Deployment — 5 Workflow Apps

### 11.1 Overview

| # | Logic App Name | Trigger | Purpose |
|---|---------------|---------|---------|
| 1 | `logic-schema-discovery` | HTTP POST | Discover source schema via ADF, store in metadata DB |
| 2 | `logic-migration-plan` | HTTP POST | Generate migration plan using AI + metadata |
| 3 | `logic-approval-workflow` | HTTP POST | Send approval email/Teams, await response |
| 4 | `logic-migration-executor` | HTTP POST | Execute approved migration via ADF pipelines |
| 5 | `logic-validation-report` | HTTP POST | Run validation checks, generate report |

### 11.2 Create Logic App Infrastructure

```bash
# Storage account for Logic Apps
az storage account create \
  --name stlogicmigrationpoc \
  --resource-group rg-data-migration-poc \
  --location eastus2 \
  --sku Standard_LRS

# App Service Plan (Workflow Standard)
az appservice plan create \
  --name asp-logic-migration \
  --resource-group rg-data-migration-poc \
  --location eastus2 \
  --sku WS1 \
  --is-linux false

# Create each Logic App (Standard)
for APP_NAME in logic-schema-discovery logic-migration-plan \
  logic-approval-workflow logic-migration-executor logic-validation-report; do
  az logicapp create \
    --name $APP_NAME \
    --resource-group rg-data-migration-poc \
    --plan asp-logic-migration \
    --storage-account stlogicmigrationpoc \
    --assign-identity [system]
  echo "Created: $APP_NAME"
done
```

### 11.3 Logic App #1 — Schema Discovery (`logic-schema-discovery`)

**Trigger:** HTTP POST  
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "jobId":        { "type": "string" },
    "sourceType":   { "type": "string", "enum": ["Oracle", "SQLServer"] },
    "sourceHost":   { "type": "string" },
    "sourceDatabase": { "type": "string" },
    "schemaFilter": { "type": "string" }
  },
  "required": ["jobId", "sourceType"]
}
```

**Workflow steps (build in Logic Apps Designer):**

1. **When a HTTP request is received** — POST with the schema above
2. **Initialize variable** — `pipelineName` (String)
3. **Condition:** `sourceType` equals `Oracle`
   - **True:** Set `pipelineName` = `pl_schema_discovery_oracle`
   - **False:** Set `pipelineName` = `pl_schema_discovery_sqlserver`
4. **Create pipeline run** (ADF connector) — trigger `pipelineName` with parameters `{schemaName, jobId}`
5. **Until loop** — poll `Get pipeline run` every 30 seconds until status ∈ `{Succeeded, Failed, Cancelled}`
6. **Condition:** Pipeline succeeded?
   - **True:**
     - **Get pipeline output** (Lookup activity results)
     - **For each** discovered column → **Insert row** into `dbo.DiscoveredSchemas` (SQL connector)
     - **Execute SQL** → `UPDATE dbo.MigrationJobs SET Status='SchemaDiscovered', UpdatedAt=SYSUTCDATETIME() WHERE JobId=@jobId`
     - **Response** → HTTP 200 with schema summary JSON
   - **False:**
     - **Execute SQL** → `UPDATE dbo.MigrationJobs SET Status='Failed', ErrorMessage=@errorMsg WHERE JobId=@jobId`
     - **Response** → HTTP 500 with error details

### 11.4 Logic App #2 — Migration Plan Generation (`logic-migration-plan`)

**Trigger:** HTTP POST  
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "jobId":        { "type": "string" },
    "sourceType":   { "type": "string" },
    "selectedTables": { "type": "array", "items": { "type": "string" } },
    "userPreferences": { "type": "string" }
  },
  "required": ["jobId", "sourceType"]
}
```

**Workflow steps:**

1. **When a HTTP request is received** — POST
2. **Execute SQL query** → `SELECT * FROM dbo.DiscoveredSchemas WHERE JobId=@jobId`
3. **Compose** — Build the AI prompt:
   - Include all discovered column metadata
   - Include source type (Oracle/SQL Server)
   - Include data type mapping rules
   - Include user preferences
4. **HTTP action** — POST to Azure OpenAI:
   ```
   POST https://oai-migration-poc.openai.azure.com/openai/deployments/gpt-41-migration/chat/completions?api-version=2025-01-01-preview
   ```
   - Headers: `api-key` from Key Vault, `Content-Type: application/json`
   - Body: System prompt + discovered schema + user preferences
   - Request: Generate column mappings, DDL, complexity score, batch strategy
5. **Parse JSON** — Extract AI response (mappings array, DDL statements)
6. **For each** mapping → **Insert row** into `dbo.SchemaMappings`
7. **Execute SQL** → Update `dbo.MigrationJobs` with plan JSON, set status `PlanGenerated`
8. **Response** → HTTP 200 with migration plan summary

### 11.5 Logic App #3 — Approval Workflow (`logic-approval-workflow`)

**Trigger:** HTTP POST  
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "jobId":            { "type": "string" },
    "approverEmail":    { "type": "string" },
    "migrationSummary": { "type": "string" }
  },
  "required": ["jobId", "approverEmail"]
}
```

**Workflow steps:**

1. **When a HTTP request is received** — POST
2. **Execute SQL** → Retrieve migration plan from `dbo.MigrationJobs`
3. **Execute SQL** → `UPDATE dbo.MigrationJobs SET Status='AwaitingApproval' WHERE JobId=@jobId`
4. **Send approval email** (Office 365 Outlook connector) or **Post adaptive card and wait for response** (Microsoft Teams connector):
   - To: `approverEmail`
   - Subject: `Migration Approval Required — Job @{jobId}`
   - Body: Formatted migration summary with table mappings
   - Options: **Approve** / **Reject**
5. **Condition:** Response is "Approve"?
   - **True:**
     - `UPDATE dbo.MigrationJobs SET ApprovalStatus='Approved', ApprovedBy=@approver, ApprovedAt=SYSUTCDATETIME(), Status='Approved' WHERE JobId=@jobId`
     - **Response** → `{"approved": true, "approvedBy": "...", "approvedAt": "..."}`
   - **False:**
     - `UPDATE dbo.MigrationJobs SET ApprovalStatus='Rejected', Status='Rejected' WHERE JobId=@jobId`
     - **Response** → `{"approved": false, "reason": "Rejected by approver"}`
6. **Timeout** (72 hours): Update status to `ApprovalTimedOut`

### 11.6 Logic App #4 — Migration Executor (`logic-migration-executor`)

**Trigger:** HTTP POST  
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "jobId":      { "type": "string" },
    "sourceType": { "type": "string", "enum": ["Oracle", "SQLServer"] },
    "executeDDL": { "type": "boolean" },
    "tables": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "sourceSchema": { "type": "string" },
          "sourceTable":  { "type": "string" },
          "targetSchema": { "type": "string" },
          "targetTable":  { "type": "string" }
        }
      }
    }
  },
  "required": ["jobId", "sourceType", "tables"]
}
```

**Workflow steps:**

1. **When a HTTP request is received** — POST
2. **Execute SQL** → Verify `Status='Approved'` for this JobId (guard rail)
3. **Execute SQL** → `UPDATE dbo.MigrationJobs SET Status='Executing' WHERE JobId=@jobId`
4. **Condition:** `executeDDL` is true?
   - **True:**
     - **Execute SQL** → Retrieve DDL from `dbo.SchemaMappings`
     - **Create pipeline run** → `pl_execute_ddl` with DDL statements
     - Wait for completion
     - Log to `dbo.MigrationLog` (step: "DDL Execution")
5. **For each** table (parallel degree: 4):
   a. **Insert** into `dbo.MigrationLog` — step started
   b. **Create pipeline run** (ADF) → `pl_copy_table_oracle` or `pl_copy_table_sqlserver`
   c. **Until loop** — poll pipeline status every 30 seconds
   d. **Insert** into `dbo.MigrationLog` — step completed/failed with row count + duration
6. **Compose** — Aggregate results (success count, failure count, total rows)
7. **Execute SQL** → Update job status:
   - All succeeded → `Completed`
   - Some failed → `PartialFailure`
   - All failed → `Failed`
8. **Response** → HTTP 200 with execution summary

### 11.7 Logic App #5 — Validation & Report (`logic-validation-report`)

**Trigger:** HTTP POST  
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "jobId": { "type": "string" },
    "validationTypes": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["RowCount", "Checksum", "SampleData", "NullCheck", "SchemaCompare"]
      }
    }
  },
  "required": ["jobId"]
}
```

**Workflow steps:**

1. **When a HTTP request is received** — POST
2. **Execute SQL** → Get table mappings from `dbo.SchemaMappings WHERE JobId=@jobId`
3. **For each** table:
   a. **Row count check:**
      - ADF Lookup on source: `SELECT COUNT(*) FROM {sourceTable}`
      - SQL query on target: `SELECT COUNT(*) FROM {targetTable}`
      - Compare and insert into `dbo.ValidationResults`
   b. **Null check:**
      - Query null counts per column on source and target
      - Compare distributions
   c. **Sample data:**
      - Query TOP 10 from source and target
      - Compare for consistency
   d. **Schema compare:**
      - Compare target table structure vs planned DDL
4. **Compose** — Build validation report JSON:
   ```json
   {
     "jobId": "...",
     "totalTables": 12,
     "passed": 11,
     "failed": 1,
     "checks": [...]
   }
   ```
5. **Execute SQL** → Update `dbo.MigrationJobs SET Status='Validated'`
6. **Response** → HTTP 200 with full validation report

### 11.8 Retrieve and Store Logic App Trigger URLs

After deploying all workflows:

```bash
# Retrieve trigger URLs
for APP_NAME in logic-schema-discovery logic-migration-plan \
  logic-approval-workflow logic-migration-executor logic-validation-report; do
  echo "=== $APP_NAME ==="
  # Get the workflow trigger callback URL from the portal or via REST API
  # Store in Key Vault:
  # az keyvault secret set --vault-name kv-migration-poc \
  #   --name "logic-app-${APP_NAME#logic-}-url" --value "<callback-url>"
done
```

> **Important:** After deploying each Logic App workflow in the designer and saving, navigate to the workflow's **Overview** → copy the **Workflow URL** (the HTTP trigger URL). Update the corresponding Key Vault secret with the real URL.

---

## 12. AI Foundry Agent Configuration

### 12.1 Create the Agent in Azure AI Foundry Portal

1. Open [Azure AI Foundry Portal](https://ai.azure.com) → select project `aiproj-migration-poc`
2. Navigate to **Agents** (left sidebar) → **+ New agent**
3. Configure:

| Setting | Value |
|---------|-------|
| Agent name | `data-migration-agent` |
| Model deployment | `gpt-41-migration` (your GPT-4.1 deployment) |
| Temperature | `0.1` (low for deterministic tool calling) |
| Top-p | `0.95` |
| Max response tokens | `4096` |

### 12.2 Agent System Instructions

Paste or upload the following as the agent's system prompt:

```markdown
You are an AI Data Migration Agent that helps users migrate databases from Oracle or
SQL Server to Azure SQL Database. You operate within a fully managed Azure environment
using Azure Data Factory, Logic Apps, and Azure SQL.

## Your Capabilities
You can perform the following actions by calling your tools:
1. **discover_schema** — Analyze source database tables, columns, data types, and relationships
2. **generate_migration_plan** — Create a detailed migration plan with type mappings and DDL
3. **request_approval** — Send the migration plan for human approval before execution
4. **execute_migration** — Run the approved migration (DDL creation + data copy via ADF)
5. **validate_and_report** — Verify data integrity and generate a validation report

## Conversation Flow
1. Greet the user and ask about their migration needs
2. Collect source details: type (Oracle/SQL Server), host, database/service, schema
3. Run schema discovery and present findings in a formatted table
4. Generate and present the migration plan with type mappings
5. Ask the user to review the plan — if they approve, request an approver email
6. Trigger the approval workflow
7. Once approved, execute the migration
8. Run validation and present the final report
9. Ask if they need anything else

## Rules
- ALWAYS discover schema before generating a plan
- ALWAYS get approval before executing migration
- NEVER skip validation after migration
- Present information in clear, formatted markdown tables
- Generate a unique jobId (UUID) at the start of each migration conversation
- If an error occurs, explain it in plain language and suggest next steps
- For Oracle sources: handle NUMBER, VARCHAR2, DATE, CLOB, BLOB, TIMESTAMP, RAW, etc.
- For SQL Server sources: handle NVARCHAR(MAX), DATETIME2, UNIQUEIDENTIFIER, etc.
- Always confirm the user's intent before destructive operations
```

### 12.3 Configure Agent Tools (Function Calling)

Add 5 tools. Each tool maps to one Logic App HTTP trigger. The agent calls these as functions — the AI Foundry runtime sends the HTTP request to the Logic App URL stored in Key Vault.

**Tool 1: `discover_schema`**
```json
{
  "type": "function",
  "function": {
    "name": "discover_schema",
    "description": "Discovers the schema of the source database — all tables, columns, data types, primary keys, and foreign keys. Call this first before generating a migration plan.",
    "parameters": {
      "type": "object",
      "properties": {
        "jobId": {
          "type": "string",
          "description": "Unique migration job identifier (UUID format)"
        },
        "sourceType": {
          "type": "string",
          "enum": ["Oracle", "SQLServer"],
          "description": "Type of source database"
        },
        "sourceHost": {
          "type": "string",
          "description": "Hostname or IP of the source database server"
        },
        "sourceDatabase": {
          "type": "string",
          "description": "Name of the source database (SQL Server) or Oracle service name"
        },
        "schemaFilter": {
          "type": "string",
          "description": "Optional schema/owner filter (e.g., 'HR' for Oracle, 'dbo' for SQL Server)"
        }
      },
      "required": ["jobId", "sourceType", "sourceHost", "sourceDatabase"]
    }
  }
}
```

**Tool 2: `generate_migration_plan`**
```json
{
  "type": "function",
  "function": {
    "name": "generate_migration_plan",
    "description": "Generates a detailed migration plan including column-level type mappings, DDL CREATE TABLE statements for Azure SQL, complexity scoring, and batch strategy. Requires schema discovery to have been completed first.",
    "parameters": {
      "type": "object",
      "properties": {
        "jobId": {
          "type": "string",
          "description": "Migration job identifier from the discovery step"
        },
        "sourceType": {
          "type": "string",
          "enum": ["Oracle", "SQLServer"],
          "description": "Type of source database"
        },
        "selectedTables": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Tables to include (empty array = all discovered tables)"
        },
        "userPreferences": {
          "type": "string",
          "description": "Special instructions (e.g., 'use NVARCHAR for all text columns', 'partition large tables')"
        }
      },
      "required": ["jobId", "sourceType"]
    }
  }
}
```

**Tool 3: `request_approval`**
```json
{
  "type": "function",
  "function": {
    "name": "request_approval",
    "description": "Sends the migration plan to an approver via email or Teams for review. Migration cannot proceed without explicit approval. Returns the approval decision.",
    "parameters": {
      "type": "object",
      "properties": {
        "jobId": {
          "type": "string",
          "description": "Migration job identifier"
        },
        "approverEmail": {
          "type": "string",
          "description": "Email address of the person who should approve the migration"
        },
        "migrationSummary": {
          "type": "string",
          "description": "Human-readable summary of the migration plan for the approver to review"
        }
      },
      "required": ["jobId", "approverEmail"]
    }
  }
}
```

**Tool 4: `execute_migration`**
```json
{
  "type": "function",
  "function": {
    "name": "execute_migration",
    "description": "Executes the approved migration plan: creates target tables in Azure SQL (DDL) and copies data from source using ADF pipelines. Only call after approval has been received.",
    "parameters": {
      "type": "object",
      "properties": {
        "jobId": {
          "type": "string",
          "description": "Migration job identifier"
        },
        "sourceType": {
          "type": "string",
          "enum": ["Oracle", "SQLServer"],
          "description": "Type of source database"
        },
        "executeDDL": {
          "type": "boolean",
          "description": "True to create target tables (first run). False if tables already exist."
        },
        "tables": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "sourceSchema": { "type": "string" },
              "sourceTable":  { "type": "string" },
              "targetSchema": { "type": "string" },
              "targetTable":  { "type": "string" }
            },
            "required": ["sourceSchema", "sourceTable", "targetSchema", "targetTable"]
          },
          "description": "Table mapping list for migration"
        }
      },
      "required": ["jobId", "sourceType", "tables"]
    }
  }
}
```

**Tool 5: `validate_and_report`**
```json
{
  "type": "function",
  "function": {
    "name": "validate_and_report",
    "description": "Runs post-migration validation checks and generates a detailed report. Checks include row counts, null distributions, sample data comparison, and schema verification.",
    "parameters": {
      "type": "object",
      "properties": {
        "jobId": {
          "type": "string",
          "description": "Migration job identifier"
        },
        "validationTypes": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": ["RowCount", "Checksum", "SampleData", "NullCheck", "SchemaCompare"]
          },
          "description": "Validation check types to run (default: all types)"
        }
      },
      "required": ["jobId"]
    }
  }
}
```

### 12.4 Upload Reference Files (File Search / Knowledge)

In the Agent configuration, upload these as knowledge files:

| File | Description |
|------|-------------|
| `oracle-to-azuresql-type-mapping.md` | Oracle → Azure SQL data type conversion matrix with precision handling |
| `sqlserver-to-azuresql-type-mapping.md` | SQL Server → Azure SQL type mapping (largely 1:1 with exceptions) |
| `migration-best-practices.md` | Batch sizes, parallelism, large table handling, LOB columns |
| `common-migration-issues.md` | Known pitfalls: Oracle DATE vs DATETIME2, NUMBER precision, CLOB handling |

### 12.5 Test the Agent

In the AI Foundry portal Playground, open the agent and verify:

```
You: Hello! I need to migrate an Oracle database to Azure SQL.

Agent: I'd be happy to help you migrate your Oracle database to Azure SQL Database!
       To get started, I'll need a few details about your source database:
       1. **Host**: What is the hostname or IP address of your Oracle server?
       2. **Service Name**: What is the Oracle service name (e.g., ORCL, FREEPDB1)?
       3. **Schema**: Which schema would you like to migrate (e.g., HR, SALES)?
       ...
```

---

## 13. Application Insights & Monitoring

### 13.1 Enable Diagnostic Settings on All Resources

```bash
# ── ADF Diagnostics ──
az monitor diagnostic-settings create \
  --name diag-adf \
  --resource $(az datafactory show --name adf-migration-poc \
    --resource-group rg-data-migration-poc --query id -o tsv) \
  --workspace law-migration-poc \
  --logs '[
    {"category":"PipelineRuns","enabled":true},
    {"category":"ActivityRuns","enabled":true},
    {"category":"TriggerRuns","enabled":true}
  ]'

# ── Azure SQL Diagnostics ──
az monitor diagnostic-settings create \
  --name diag-sql-target \
  --resource $(az sql db show --server sql-migration-poc \
    --name sqldb-migration-target --resource-group rg-data-migration-poc --query id -o tsv) \
  --workspace law-migration-poc \
  --logs '[
    {"category":"SQLInsights","enabled":true},
    {"category":"QueryStoreRuntimeStatistics","enabled":true},
    {"category":"Errors","enabled":true}
  ]'

# ── Key Vault Diagnostics ──
az monitor diagnostic-settings create \
  --name diag-kv \
  --resource $(az keyvault show --name kv-migration-poc \
    --resource-group rg-data-migration-poc --query id -o tsv) \
  --workspace law-migration-poc \
  --logs '[{"category":"AuditEvent","enabled":true}]'
```

### 13.2 Connect Logic Apps to Application Insights

For each Logic App, add these Application Settings:

| Setting | Value |
|---------|-------|
| `APPINSIGHTS_INSTRUMENTATIONKEY` | `<instrumentation-key-from-appi-migration-poc>` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | `<connection-string-from-appi-migration-poc>` |

```bash
APPI_CONN=$(az monitor app-insights component show \
  --app appi-migration-poc --resource-group rg-data-migration-poc \
  --query connectionString -o tsv)

APPI_KEY=$(az monitor app-insights component show \
  --app appi-migration-poc --resource-group rg-data-migration-poc \
  --query instrumentationKey -o tsv)

for APP_NAME in logic-schema-discovery logic-migration-plan \
  logic-approval-workflow logic-migration-executor logic-validation-report; do
  az functionapp config appsettings set \
    --name $APP_NAME \
    --resource-group rg-data-migration-poc \
    --settings \
      APPINSIGHTS_INSTRUMENTATIONKEY=$APPI_KEY \
      APPLICATIONINSIGHTS_CONNECTION_STRING="$APPI_CONN"
done
```

### 13.3 Create Alert Rules

```bash
# Alert: ADF pipeline failure
az monitor metrics alert create \
  --name "alert-adf-pipeline-failure" \
  --resource-group rg-data-migration-poc \
  --scopes $(az datafactory show --name adf-migration-poc \
    --resource-group rg-data-migration-poc --query id -o tsv) \
  --condition "total PipelineFailedRuns > 0" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --severity 2 \
  --description "ADF pipeline failed during migration"

# Alert: Logic App workflow failure (each app)
for APP_NAME in logic-schema-discovery logic-migration-plan \
  logic-approval-workflow logic-migration-executor logic-validation-report; do
  az monitor metrics alert create \
    --name "alert-${APP_NAME}-failure" \
    --resource-group rg-data-migration-poc \
    --scopes $(az functionapp show --name $APP_NAME \
      --resource-group rg-data-migration-poc --query id -o tsv) \
    --condition "total WorkflowRunsFailure > 0" \
    --window-size 5m \
    --severity 2 \
    --description "Logic App workflow failure: $APP_NAME"
done
```

### 13.4 Useful KQL Queries

```kql
// Migration pipeline durations
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.DATAFACTORY"
| where Category == "PipelineRuns"
| project TimeGenerated, pipelineName_s, status_s, 
    durationInMs_d / 1000 as DurationSeconds
| order by TimeGenerated desc

// Logic App failures
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.WEB"
| where status_s == "Failed"
| project TimeGenerated, resource_workflowName_s, error_message_s
| order by TimeGenerated desc

// Key Vault access audit
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where OperationName contains "SecretGet"
| project TimeGenerated, CallerIPAddress, identity_claim_upn_s, 
    id_s, ResultType
| order by TimeGenerated desc
```

---

## 14. Test Migration — Step-by-Step Dry Run

### 14.1 Pre-Flight Checklist

Run through every item before testing:

- [ ] Self-Hosted IR VM is running and shows **Connected** in ADF Portal
- [ ] All 5 Logic Apps show **Running** status in Azure Portal
- [ ] Key Vault secrets are populated with real values (no `PLACEHOLDER` remaining)
- [ ] ADF linked services all show ✅ **Connection successful** when tested
- [ ] Azure SQL metadata DB has the schema tables created (Section 8.4)
- [ ] Agent is deployed and responsive in AI Foundry Playground
- [ ] Oracle or SQL Server source is accessible from the SHIR VM
- [ ] Logic App HTTP trigger URLs are stored in Key Vault
- [ ] RBAC role assignments are in place (verify with `az role assignment list`)
- [ ] Database users created in Azure SQL for all managed identities

### 14.2 Step 1 — Test Connectivity

```bash
# Test from SHIR VM (RDP in):

# Oracle connectivity
tnsping <oracle-host>:1521/FREEPDB1

# SQL Server connectivity
sqlcmd -S <sqlserver-host>,1433 -U <user> -P <password> -Q "SELECT @@VERSION"

# ADF linked service tests (via portal):
# ADF Studio → Manage → Linked Services → Test Connection (each one)
```

### 14.3 Step 2 — Test Schema Discovery via Agent

Open the AI Foundry Agent Playground and send:

```
I need to migrate an Oracle database to Azure SQL.
Host: 10.0.10.50
Service: FREEPDB1
Schema: HR
```

**✅ Expected behavior:**
1. Agent generates a UUID job ID
2. Agent calls `discover_schema` tool
3. Logic App `logic-schema-discovery` fires → triggers ADF pipeline
4. ADF pipeline queries Oracle `ALL_TAB_COLUMNS` for the HR schema
5. Results stored in `dbo.DiscoveredSchemas`
6. Agent presents a formatted table of discovered tables and columns

**🔍 Verify in metadata DB:**
```sql
SELECT TOP 20 * FROM dbo.DiscoveredSchemas ORDER BY DiscoveredAt DESC;
SELECT * FROM dbo.MigrationJobs WHERE Status = 'SchemaDiscovered';
```

### 14.4 Step 3 — Test Migration Plan Generation

Continue the conversation:

```
Generate a migration plan for all discovered tables.
```

**✅ Expected behavior:**
1. Agent calls `generate_migration_plan`
2. Logic App queries schema, calls GPT-4.1, generates mappings
3. Agent presents: type mappings, DDL preview, complexity score

### 14.5 Step 4 — Test Approval Workflow

```
The plan looks good. Please send it for approval to admin@contoso.com.
```

**✅ Expected behavior:**
1. Agent calls `request_approval`
2. Approver receives email or Teams adaptive card
3. Approver clicks **Approve**
4. Agent confirms approval received

### 14.6 Step 5 — Test Migration Execution

```
Approval received. Please execute the migration now.
```

**✅ Expected behavior:**
1. Agent calls `execute_migration` with `executeDDL: true` and table list
2. DDL runs on Azure SQL target
3. ADF copy pipelines execute for each table
4. Agent reports progress and final result

### 14.7 Step 6 — Test Validation

```
Run full validation on the migration.
```

**✅ Expected behavior:**
1. Agent calls `validate_and_report` with all validation types
2. Row counts, null checks, schema comparisons run
3. Agent presents a pass/fail report per table

### 14.8 Verify End-to-End Results

```sql
-- Check job status
SELECT JobId, SourceType, Status, ApprovalStatus, CreatedAt, CompletedAt
FROM dbo.MigrationJobs
ORDER BY CreatedAt DESC;

-- Check validation results
SELECT TableName, CheckType, IsMatch, SourceValue, TargetValue
FROM dbo.ValidationResults
WHERE JobId = '<your-job-id>'
ORDER BY TableName, CheckType;

-- Check execution log
SELECT StepName, Status, RowsAffected, DurationMs
FROM dbo.MigrationLog
WHERE JobId = '<your-job-id>'
ORDER BY LoggedAt;
```

---

## 15. Production Readiness Checklist

### 🔒 Security

- [ ] Azure SQL firewall denies all public access (private endpoint only)
- [ ] Key Vault has RBAC enabled (no legacy access policies)
- [ ] Key Vault has purge protection and soft-delete enabled
- [ ] All Logic App HTTP triggers use Azure AD authentication or SAS token validation
- [ ] Self-Hosted IR VM is patched, hardened, and on a restricted subnet
- [ ] Oracle/SQL Server service accounts use minimum required privileges (read-only)
- [ ] Network security groups restrict traffic to only required ports and IPs
- [ ] All managed identities use least-privilege RBAC roles
- [ ] Diagnostic and audit logs flow to Log Analytics (verify data is arriving)
- [ ] No secrets are stored in Logic App definitions or ADF pipeline parameters
- [ ] Storage account has `allowBlobPublicAccess: false`

### ⚡ Reliability

- [ ] Azure SQL configured with appropriate backup (PITR 7+ days + LTR for production)
- [ ] Logic Apps App Service Plan is WS1+ (not Consumption tier)
- [ ] ADF self-hosted IR has 2+ nodes for high availability
- [ ] VPN Gateway or ExpressRoute has redundant connections
- [ ] Alert rules configured for all pipeline and workflow failures
- [ ] Metadata DB has sufficient capacity for concurrent migration jobs
- [ ] Logic App timeout values are appropriate (approval: 72h, execution: per-table)

### 🚀 Performance

- [ ] ADF copy activities use appropriate parallelism (`parallelCopies: 4–8`)
- [ ] Azure SQL target is General Purpose 4+ vCores (scale up for large migrations)
- [ ] SHIR VM has adequate CPU/RAM for concurrent copy activities (8 vCPU / 16 GB)
- [ ] Oracle source tables have indexes on primary keys (for efficient reads)
- [ ] Large tables (>10M rows) configured with partitioned copy in ADF
- [ ] Staging area enabled in ADF for PolyBase-optimized bulk loads

### 📋 Operational

- [ ] Migration runbook documented and reviewed by operations team
- [ ] Rollback procedure documented (drop target tables, reset metadata, rerun)
- [ ] Key Vault secret rotation schedule defined (90-day cycle)
- [ ] Monitoring dashboard created in Azure Portal (pin key metrics)
- [ ] Support escalation path documented
- [ ] Migration SLA defined (e.g., <4 hours for ≤100 tables)
- [ ] Agent conversation logs retained for audit
- [ ] Post-migration cleanup checklist (remove temp staging data, revoke elevated access)

---

## 16. Appendix: Resource Naming Conventions

| Resource Type | Pattern | Example |
|--------------|---------|---------|
| Resource Group | `rg-{project}-{env}` | `rg-data-migration-poc` |
| AI Foundry Hub | `aih-{project}-{env}` | `aih-migration-poc` |
| AI Foundry Project | `aiproj-{project}-{env}` | `aiproj-migration-poc` |
| Azure OpenAI | `oai-{project}-{env}` | `oai-migration-poc` |
| Key Vault | `kv-{project}-{env}` | `kv-migration-poc` |
| Data Factory | `adf-{project}-{env}` | `adf-migration-poc` |
| Azure SQL Server | `sql-{project}-{env}` | `sql-migration-poc` |
| Azure SQL Database | `sqldb-{purpose}` | `sqldb-migration-target` |
| Logic App | `logic-{workflow-name}` | `logic-schema-discovery` |
| App Service Plan | `asp-{purpose}` | `asp-logic-migration` |
| VNet | `vnet-{project}` | `vnet-migration` |
| Subnet | `snet-{purpose}` | `snet-private-endpoints` |
| Storage Account | `st{project}{env}` (no hyphens) | `stmigrationpoc` |
| App Insights | `appi-{project}-{env}` | `appi-migration-poc` |
| Log Analytics | `law-{project}-{env}` | `law-migration-poc` |
| VPN Gateway | `vpng-{project}` | `vpng-migration` |
| Private Endpoint | `pe-{resource}-{service}` | `pe-sql-migration` |
| NSG | `nsg-{subnet}` | `nsg-shir` |
| VM | `vm-{purpose}-{number}` | `vm-shir-01` |
| Integration Runtime | `ir-{purpose}` | `ir-onprem-shir` |

---

> **Next steps:**
> - [USER_GUIDE.md](USER_GUIDE.md) — How to interact with the migration agent
> - [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Resolving common issues
