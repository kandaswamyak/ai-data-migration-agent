# Architecture — Azure Agentic Data Migration

This document describes the architecture of the Azure Agentic Data Migration solution — a low-code, fully managed approach to migrating Oracle and SQL Server databases to Azure SQL Database using Azure AI Foundry Agent Service.

---

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Component Descriptions](#component-descriptions)
- [Data Flow](#data-flow)
- [Agent Architecture](#agent-architecture)
- [Migration Lifecycle (16 Steps)](#migration-lifecycle-16-steps)
- [State Machine](#state-machine)
- [Logic App Workflows](#logic-app-workflows)
- [Azure Data Factory Pipelines](#azure-data-factory-pipelines)
- [Security Architecture](#security-architecture)
- [Networking](#networking)
- [Monitoring and Observability](#monitoring-and-observability)
- [Failure Handling](#failure-handling)
- [Scalability Considerations](#scalability-considerations)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER / APPROVER                                │
│                                                                             │
│    Chat UI  ◄──────────────────────────────────────────────────────────►    │
│    (Foundry Playground /                           Power Automate           │
│     Custom App /                                   Outlook / Teams          │
│     REST API)                                      Approval Cards           │
└──────┬──────────────────────────────────────────────────────┬───────────────┘
       │  Conversation Thread (REST API)                      │  Approval Callback
       ▼                                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     AZURE AI FOUNDRY AGENT SERVICE                           │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  Azure Data Migration Agent                                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────────┐ │  │
│  │  │ System Prompt │  │ GPT-4.1 LLM  │  │ Tool Definitions (13+)     │ │  │
│  │  │ (Persona +   │  │ (Reasoning   │  │ • discover_source_schema   │ │  │
│  │  │  Instructions)│  │  Engine)     │  │ • analyze_datatypes        │ │  │
│  │  └──────────────┘  └──────────────┘  │ • generate_mappings        │ │  │
│  │                                       │ • assess_migration_risk    │ │  │
│  │  ┌──────────────────────────────┐    │ • generate_ddl             │ │  │
│  │  │ Conversation Thread Manager  │    │ • validate_ddl             │ │  │
│  │  │ (State across turns)         │    │ • request_human_approval   │ │  │
│  │  └──────────────────────────────┘    │ • check_approval_status    │ │  │
│  │                                       │ • execute_ddl              │ │  │
│  │                                       │ • trigger_adf_pipeline     │ │  │
│  │                                       │ • monitor_pipeline_run     │ │  │
│  │                                       │ • validate_migration       │ │  │
│  │                                       │ • generate_report          │ │  │
│  │                                       └─────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │  Tool Calls (HTTP)
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         LOGIC APPS (Consumption)                             │
│                                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────┐ ┌──────────────────┐  │
│  │ Schema       │ │ Approval     │ │ DDL           │ │ ADF Trigger      │  │
│  │ Discovery    │ │ Workflow     │ │ Execution     │ │ & Monitor        │  │
│  └──────┬───────┘ └──────┬───────┘ └───────┬───────┘ └────────┬─────────┘  │
│         │                │                  │                  │            │
│  ┌──────┴───────┐ ┌──────┴───────┐ ┌───────┴───────┐ ┌───────┴──────────┐ │
│  │ Validation   │ │ Report       │ │ Pipeline      │ │ Error Handler    │ │
│  │ Queries      │ │ Storage      │ │ Monitor       │ │                  │ │
│  └──────────────┘ └──────────────┘ └───────────────┘ └──────────────────┘  │
└───────────────┬──────────────────────────┬───────────────────────────────────┘
                │                          │
                ▼                          ▼
┌───────────────────────────┐  ┌───────────────────────────────────────────────┐
│  AZURE DATA FACTORY       │  │  AZURE SQL DATABASE (Target)                  │
│                           │  │                                               │
│  ┌─────────────────────┐  │  │  ┌──────────────┐  ┌────────────────────┐    │
│  │ Copy Data Pipeline  │──┼──┼─►│ Target Tables │  │ Validation Views   │    │
│  │ (Parameterized)     │  │  │  └──────────────┘  └────────────────────┘    │
│  └─────────────────────┘  │  │                                               │
│  ┌─────────────────────┐  │  └───────────────────────────────────────────────┘
│  │ Metadata Pipeline   │  │
│  └──────────┬──────────┘  │
│             │             │
│  ┌──────────▼──────────┐  │
│  │ Self-Hosted IR      │  │          ┌─────────────────────────────────┐
│  │ (On-Prem Gateway)   │──┼─────────►│  SOURCE DATABASES               │
│  └─────────────────────┘  │          │  • Oracle 12c+ (On-Prem/IaaS)  │
│                           │          │  • SQL Server 2016+ (On-Prem)   │
│  ┌─────────────────────┐  │          └─────────────────────────────────┘
│  │ Linked Services     │  │
│  │ (Key Vault refs)    │  │
│  └─────────────────────┘  │
└───────────────────────────┘

SUPPORTING SERVICES:

┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ Azure Key    │  │ Entra ID     │  │ Azure Blob      │  │ Azure Monitor /  │
│ Vault        │  │ (Managed     │  │ Storage         │  │ App Insights     │
│ (Secrets)    │  │  Identity)   │  │ (Artifacts)     │  │ (Logs/Metrics)   │
└──────────────┘  └──────────────┘  └─────────────────┘  └──────────────────┘
```

---

## Component Descriptions

### Azure AI Foundry Agent Service

The **managed runtime** for the migration agent. Provides:

- **Agent registration** — Define agent name, system prompt, model, tools, and parameters
- **Thread management** — Each migration is a conversation thread with full message history
- **Tool execution** — Agent Service calls your tool endpoints when the LLM decides to invoke a tool
- **Token management** — Handles context window limits, message truncation, and tool result injection

The agent is created via the AI Foundry SDK or REST API. No custom server is deployed.

### Azure OpenAI GPT-4.1

The **LLM backbone** powering the agent's reasoning. Deployed as a model deployment within Azure OpenAI Service. Used for:

- Understanding the user's migration request (intent parsing)
- Analyzing source schema metadata and identifying compatibility issues
- Generating column-level mappings with confidence scores and risk ratings
- Producing T-SQL DDL statements tuned for Azure SQL Database
- Reasoning about errors and recommending corrective actions
- Generating human-readable migration reports

**Configuration:** Temperature 0.1 (low randomness for deterministic DDL), max tokens 16,000.

### Azure Data Factory (ADF)

The **data movement engine**. Responsible for:

- Connecting to on-premises Oracle and SQL Server via Self-Hosted Integration Runtime
- Running metadata extraction queries against source databases
- Executing parameterized Copy Data pipelines to move table data to Azure SQL
- Providing pipeline run status via REST API (polled by Logic Apps)

ADF never receives prompts or LLM-generated content directly. It receives structured parameters: source table name, target table name, column list, batch size.

### Logic Apps (Consumption)

The **orchestration glue** between the agent and Azure infrastructure. Each Logic App:

- Exposes an **HTTP trigger** endpoint that the agent calls as a tool
- Executes one or more actions (call ADF REST API, run SQL query, read Blob, trigger Power Automate)
- Returns a **structured JSON response** to the agent

Logic Apps run serverless (Consumption plan) — no infrastructure to manage, billed per execution.

### Azure SQL Database

The **migration target**. A managed relational database that receives:

- DDL scripts (CREATE TABLE, ALTER TABLE, CREATE INDEX) from the DDL Execution Logic App
- Table data from ADF Copy Data pipelines
- Validation queries from the Validation Logic App

### Azure Key Vault

Centralized **secret management**. Stores:

- Oracle connection strings
- SQL Server connection strings
- Azure SQL Database connection strings
- Azure OpenAI API keys
- ADF linked service credentials
- Logic App connector credentials

All services access secrets via managed identity — no credentials in code or configuration.

### Azure Monitor / Application Insights

Unified **observability** across all components:

- Agent conversation logs (via AI Foundry diagnostics)
- Logic App run history and failure alerts
- ADF pipeline run metrics and durations
- Azure SQL query performance
- Custom migration metrics (tables migrated, rows copied, validation results)

### Entra ID (Azure AD)

**Identity and access management** for the entire solution:

- Managed identities for ADF, Logic Apps, and the agent
- RBAC roles controlling who can approve migrations, trigger pipelines, or view logs
- App registrations for custom clients accessing the agent REST API

### Power Automate

**Human approval** workflow engine:

- Receives approval requests from the Approval Logic App
- Sends rich approval cards to Outlook and Teams
- Captures approver decision and comments
- Calls the Logic App callback URL with the result

### Azure Blob Storage

**Artifact storage** between agent tool calls:

- Source metadata JSON files (output of metadata pipelines)
- Generated DDL scripts
- Mapping JSON documents
- Migration reports
- Validation result files

---

## Data Flow

### End-to-End Data Flow

```
1. User  ──[natural language]──►  AI Foundry Agent
2. Agent ──[tool: discover_source_schema]──►  Logic App  ──►  ADF Metadata Pipeline
3. ADF   ──[Self-Hosted IR]──►  Oracle/SQL Server  ──[metadata]──►  Blob Storage
4. Logic App  ──[read blob]──►  Agent  (schema JSON)
5. Agent ──[LLM reasoning]──►  Mappings + Risk + DDL  (internal — no tool call)
6. Agent ──[tool: request_human_approval]──►  Logic App  ──►  Power Automate  ──►  Approver
7. Approver  ──[Approve]──►  Power Automate  ──►  Logic App Callback
8. Agent ──[tool: check_approval_status]──►  Logic App  ──►  APPROVED
9. Agent ──[tool: execute_ddl]──►  Logic App  ──►  Azure SQL  (CREATE TABLE)
10. Agent ──[tool: trigger_adf_pipeline]──►  Logic App  ──►  ADF  ──►  Copy Data
11. ADF  ──[Self-Hosted IR]──►  Oracle/SQL Server  ──[data]──►  Azure SQL
12. Agent ──[tool: monitor_pipeline_run]──►  Logic App  ──►  ADF  ──►  COMPLETED
13. Agent ──[tool: validate_migration]──►  Logic App  ──►  Azure SQL  (row counts, checksums)
14. Agent ──[LLM reasoning]──►  Migration Report  (internal)
15. Agent ──[response]──►  User
```

### What Flows Where

| Data Type | From | To | Transport |
|-----------|------|----|-----------|
| Natural language request | User | Agent | AI Foundry REST API / Chat UI |
| Source schema metadata | Oracle / SQL Server | Blob Storage | ADF via Self-Hosted IR |
| Schema metadata JSON | Blob Storage | Agent | Logic App HTTP response |
| Column-level mappings | Agent (LLM) | Agent thread | Internal (no external call) |
| Risk assessment | Agent (LLM) | Agent thread | Internal (no external call) |
| T-SQL DDL | Agent (LLM) | Azure SQL | Logic App → Azure SQL connector |
| Approval request | Agent | Approver | Logic App → Power Automate → Outlook/Teams |
| Approval decision | Approver | Agent | Power Automate → Logic App → Agent poll |
| Table data | Oracle / SQL Server | Azure SQL | ADF Copy Data via Self-Hosted IR |
| Validation results | Azure SQL | Agent | Logic App → SQL query → HTTP response |
| Migration report | Agent (LLM) | User | AI Foundry REST API / Chat UI |

---

## Agent Architecture

### Single Agent Design

This solution uses a **single agent** — the **Azure Data Migration Agent** — rather than a multi-agent swarm. Rationale:

- **Simplicity** — One agent, one conversation thread, one state machine
- **Context continuity** — The agent maintains full context across all 16 lifecycle steps
- **Debuggability** — Every decision is visible in a single conversation thread
- **Azure AI Foundry constraint** — Agent Service manages one agent per thread; multi-agent requires custom orchestration

### Agent System Prompt (Summary)

The agent's system prompt defines:

```
ROLE:       Database Migration Specialist
EXPERTISE:  Oracle → Azure SQL, SQL Server → Azure SQL
TOOLS:      13 registered tools (see tool table)
BEHAVIOR:
  - Always discover schema before analyzing
  - Always assess risk before requesting approval
  - Never execute DDL without human approval
  - Explain every decision to the user
  - On error, diagnose and suggest remediation
  - Default to dry-run mode unless explicitly told to execute
CONSTRAINTS:
  - Never fabricate schema metadata — always call discover_source_schema
  - Never skip human approval
  - Never place secrets in conversation messages
  - Token limit awareness — chunk large schemas across multiple tool calls
```

### Tool Registration (OpenAPI-Style)

Each tool is registered with the agent using a function definition:

```json
{
    "type": "function",
    "function": {
        "name": "discover_source_schema",
        "description": "Discover tables, columns, data types, primary keys, foreign keys, and indexes from the source database. Returns JSON metadata.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "enum": ["oracle", "sqlserver"],
                    "description": "Source database type"
                },
                "schema_name": {
                    "type": "string",
                    "description": "Schema/owner name to discover (e.g., 'HR', 'dbo')"
                },
                "table_filter": {
                    "type": "string",
                    "description": "Optional wildcard filter for table names (e.g., 'EMP%')"
                }
            },
            "required": ["source_type", "schema_name"]
        }
    }
}
```

### Tool Execution Flow

```
1. LLM decides to call a tool based on conversation context
2. Agent Service extracts tool name + parameters from LLM output
3. Agent Service sends HTTP POST to the tool's Logic App endpoint
4. Logic App executes workflow (ADF call, SQL query, approval trigger, etc.)
5. Logic App returns JSON response
6. Agent Service injects tool result into conversation thread
7. LLM reads tool result and decides next action
```

---

## Migration Lifecycle (16 Steps)

The full migration lifecycle consists of 16 steps. The agent executes them in order, but may skip, retry, or loop based on context.

| Step | Name | Tool Used | LLM Involved | Description |
|------|------|-----------|--------------|-------------|
| 1 | **Request Understanding** | — | ✅ | Agent parses user's natural language request |
| 2 | **Source Identification** | — | ✅ | Agent identifies source type (Oracle/SQL Server) and schema |
| 3 | **Schema Discovery** | `discover_source_schema` | ❌ | ADF queries source metadata, returns JSON |
| 4 | **Schema Presentation** | — | ✅ | Agent summarizes discovered schema for the user |
| 5 | **Datatype Analysis** | `analyze_datatypes` | ✅ | LLM maps source types to Azure SQL equivalents |
| 6 | **Mapping Generation** | `generate_mappings` | ✅ | LLM produces column-level mappings with confidence |
| 7 | **Risk Assessment** | `assess_migration_risk` | ✅ | LLM evaluates risk per column and overall |
| 8 | **DDL Generation** | `generate_ddl` | ✅ | LLM generates CREATE TABLE, indexes, constraints |
| 9 | **DDL Validation** | `validate_ddl` | ❌ | Logic App parses DDL against target DB (no execute) |
| 10 | **DDL Correction** | — | ✅ | If validation fails, LLM fixes DDL and retries step 9 |
| 11 | **Approval Request** | `request_human_approval` | ❌ | Logic App sends approval with risk summary + DDL preview |
| 12 | **Approval Polling** | `check_approval_status` | ❌ | Agent polls until APPROVED / REJECTED |
| 13 | **DDL Execution** | `execute_ddl` | ❌ | Logic App runs DDL on Azure SQL (skipped in dry run) |
| 14 | **Data Migration** | `trigger_adf_pipeline` + `monitor_pipeline_run` | ❌ | ADF copies data (skipped in dry run) |
| 15 | **Post-Migration Validation** | `validate_migration` | ❌ | Logic App runs validation queries |
| 16 | **Report & Error Explanation** | `generate_report` | ✅ | LLM generates final report; explains any errors |

### Step Dependencies

```
1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 ──→ 10 (if validation fails, loop to 9)
                                    └──→ 11 → 12 ──→ 13 → 14 → 15 → 16
                                                  └──→ 16 (if rejected)
```

---

## State Machine

Each migration has a state that tracks its position in the lifecycle. The state is maintained in the agent's conversation thread and in Azure Table Storage (for the approval Logic App).

### States

```
                                    ┌──────────────┐
                                    │    DRAFT     │
                                    │  (Step 1-2)  │
                                    └──────┬───────┘
                                           │ User confirms scope
                                           ▼
                                    ┌──────────────┐
                                    │  ANALYZING   │
                                    │  (Step 3-8)  │
                                    └──────┬───────┘
                                           │ DDL validated
                                           ▼
                                ┌────────────────────┐
                                │ AWAITING_APPROVAL  │
                                │    (Step 11-12)    │
                                └──────┬─────┬───────┘
                          Approved │         │ Rejected
                                   ▼         ▼
                            ┌──────────┐  ┌───────────┐
                            │ APPROVED │  │ CANCELLED │
                            └────┬─────┘  └───────────┘
                                 │
                     ┌───────────┴────────────┐
                     │                        │
              dry_run = true          dry_run = false
                     │                        │
                     ▼                        ▼
              ┌──────────┐           ┌─────────────────┐
              │ DRY_RUN  │           │ READY_FOR_EXEC  │
              │(Skip 13-15)│          │    (Step 13)     │
              └────┬─────┘           └────────┬────────┘
                   │                          │ DDL executed
                   │                          ▼
                   │                   ┌──────────┐
                   │                   │ RUNNING  │
                   │                   │(Step 14) │
                   │                   └────┬─────┘
                   │                        │
                   │          ┌─────────────┼──────────────┐
                   │          │             │              │
                   │          ▼             ▼              ▼
                   │   ┌───────────┐ ┌──────────┐ ┌──────────────────┐
                   │   │ COMPLETED │ │  FAILED  │ │ VALIDATION_FAILED│
                   │   │ (Step 16) │ │ (Step 16)│ │    (Step 16)     │
                   │   └───────────┘ └──────────┘ └──────────────────┘
                   │          ▲
                   └──────────┘
                  (report generated)
```

### State Definitions

| State | Description | Entry Condition | Exit Condition |
|-------|-------------|-----------------|----------------|
| `DRAFT` | Migration request received, scope being clarified | User sends initial request | User confirms scope |
| `ANALYZING` | Schema discovery, mapping, risk assessment, DDL generation | Scope confirmed | DDL validated successfully |
| `AWAITING_APPROVAL` | Approval request sent, waiting for human decision | DDL validated | Approval received or rejected |
| `APPROVED` | Human approved the migration | Approver clicks Approve | Agent proceeds to execution |
| `DRY_RUN` | Dry run mode — skip execution, generate report | Approved + dry_run=true | Report generated |
| `READY_FOR_EXECUTION` | DDL about to be executed on target | Approved + dry_run=false | DDL execution complete |
| `RUNNING` | ADF pipeline copying data | DDL executed | Pipeline completes |
| `COMPLETED` | Migration and validation successful | Validation passes | Terminal |
| `FAILED` | ADF pipeline or DDL execution failed | Error during execution | Terminal (retry possible) |
| `VALIDATION_FAILED` | Data migrated but validation checks failed | Validation fails | Terminal (investigate) |
| `CANCELLED` | Human rejected the migration | Approver clicks Reject | Terminal |

---

## Logic App Workflows

### Schema Discovery Logic App

```
Trigger:  HTTP POST from Agent Service
Input:    { source_type, schema_name, table_filter }
Actions:
  1. Read Key Vault secret for source connection string
  2. Trigger ADF metadata pipeline (REST API call)
  3. Wait for pipeline completion (polling loop, 30s interval, 10min timeout)
  4. Read metadata JSON from Blob Storage
  5. Return JSON to agent
Output:   { tables: [...], columns: [...], keys: [...], indexes: [...] }
```

### Approval Workflow Logic App

```
Trigger:  HTTP POST from Agent Service
Input:    { migration_id, summary, risk_assessment, ddl_preview, tables, columns }
Actions:
  1. Store approval request in Azure Table Storage (status: PENDING)
  2. Trigger Power Automate flow via HTTP connector
  3. Return { migration_id, status: "PENDING", poll_url: "..." }

Callback endpoint (separate trigger):
  Input:  { migration_id, decision, approver, comments }
  Action: Update Table Storage record to APPROVED or REJECTED
```

### DDL Execution Logic App

```
Trigger:  HTTP POST from Agent Service
Input:    { ddl_sql, target_database, dry_run }
Actions:
  1. If dry_run=true, parse DDL with SET PARSEONLY ON, return parse result
  2. If dry_run=false, execute DDL via Azure SQL connector (managed identity)
  3. Return { success, tables_created, errors }
```

### ADF Trigger Logic App

```
Trigger:  HTTP POST from Agent Service
Input:    { pipeline_name, source_table, target_table, column_mappings, batch_size }
Actions:
  1. Call ADF REST API: POST /pipelines/{name}/createRun
  2. Return { run_id, status: "InProgress" }
```

### Pipeline Monitor Logic App

```
Trigger:  HTTP POST from Agent Service
Input:    { run_id }
Actions:
  1. Call ADF REST API: GET /pipelineruns/{run_id}
  2. Return { run_id, status, duration, rows_copied, errors }
```

### Validation Logic App

```
Trigger:  HTTP POST from Agent Service
Input:    { source_type, source_table, target_table, checks: [...] }
Actions:
  1. Run source row count query (via ADF or direct connection)
  2. Run target row count query (Azure SQL connector)
  3. Run checksum comparison (if supported)
  4. Run null count comparison
  5. Run duplicate detection on target
  6. Return { validation_result, checks: [...], pass: true/false }
```

---

## Azure Data Factory Pipelines

### Metadata Pipeline (`pl-metadata-extract`)

Extracts schema metadata from source databases:

```
Pipeline Parameters:
  - source_type: "oracle" | "sqlserver"
  - schema_name: string
  - table_filter: string (optional)
  - output_blob_path: string

Activities:
  1. If Expression: source_type == "oracle"
     → Lookup: SELECT * FROM ALL_TAB_COLUMNS WHERE OWNER = @schema_name
     → Lookup: SELECT * FROM ALL_CONSTRAINTS WHERE OWNER = @schema_name
     → Lookup: SELECT * FROM ALL_IND_COLUMNS WHERE INDEX_OWNER = @schema_name
  2. If Expression: source_type == "sqlserver"
     → Lookup: SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @schema_name
     → Lookup: SELECT * FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS ...
     → Lookup: SELECT * FROM sys.indexes ...
  3. Copy: Write combined JSON to Blob Storage at @output_blob_path
```

> **Note:** ADF Lookup activity has a 5,000-row limit. For schemas with more than 5,000 columns, use Stored Procedure activity to write metadata to a staging table, then use Copy activity to export to Blob.

### Copy Data Pipeline (`pl-copy-data`)

Parameterized pipeline for table-level data copy:

```
Pipeline Parameters:
  - source_type: "oracle" | "sqlserver"
  - source_schema: string
  - source_table: string
  - target_schema: string (default "dbo")
  - target_table: string
  - column_mappings: JSON array
  - batch_size: int (default 10000)
  - parallel_degree: int (default 4)

Activities:
  1. Copy Data Activity:
     - Source: Parameterized Oracle/SQL Server dataset
     - Sink: Azure SQL Database dataset
     - Column Mapping: From @column_mappings parameter
     - Settings: writeBatchSize = @batch_size, parallelCopies = @parallel_degree
     - Fault tolerance: Skip incompatible rows (log to Blob Storage)
```

---

## Security Architecture

> Full details in [SECURITY.md](SECURITY.md).

### Identity Model

```
┌─────────────────────────────────────────────────────────────────┐
│                     ENTRA ID (Azure AD)                         │
│                                                                 │
│  ┌───────────────┐  ┌──────────────┐  ┌───────────────────────┐│
│  │ System-Assigned│  │ User-Assigned│  │ App Registrations     ││
│  │ Managed ID     │  │ Managed ID   │  │ (Custom clients)     ││
│  │ • ADF          │  │ • Shared MI  │  │ • Agent Chat UI      ││
│  │ • Logic Apps   │  │   for agent  │  │ • Approval REST API  ││
│  │ • Azure SQL    │  │              │  │                       ││
│  └───────────────┘  └──────────────┘  └───────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Secret Access Pattern

```
Service  ──[managed identity]──►  Key Vault  ──[secret]──►  Connection String
```

No service stores credentials locally. All credentials are retrieved at runtime from Key Vault using managed identity.

### RBAC Roles

| Principal | Role | Scope |
|-----------|------|-------|
| ADF Managed Identity | Key Vault Secrets User | Key Vault |
| ADF Managed Identity | Storage Blob Data Contributor | Blob Storage |
| Logic Apps Managed Identity | Key Vault Secrets User | Key Vault |
| Logic Apps Managed Identity | Data Factory Contributor | ADF |
| Logic Apps Managed Identity | SQL DB Contributor | Azure SQL |
| Agent Managed Identity | Cognitive Services User | Azure OpenAI |
| Migration Approvers (Entra Group) | Custom Approval Role | Logic App |
| Migration Operators (Entra Group) | Reader | All resources |

---

## Networking

### On-Premises Connectivity

```
┌──────────────────────┐          ┌─────────────────────────────┐
│  On-Premises Network │          │  Azure Virtual Network       │
│                      │          │                              │
│  ┌────────────────┐  │  ExpressRoute   ┌──────────────────┐  │
│  │ Oracle DB      │  │  or VPN   │     │ Private Endpoints │  │
│  │ SQL Server     │◄─┼──────────┼────►│ • Azure SQL      │  │
│  └────────────────┘  │          │     │ • Key Vault       │  │
│                      │          │     │ • Blob Storage    │  │
│  ┌────────────────┐  │          │     │ • ADF             │  │
│  │ Self-Hosted IR │  │          │     └──────────────────┘  │
│  │ (ADF Gateway)  │──┼──────────┼────►                       │
│  └────────────────┘  │          │                              │
└──────────────────────┘          └─────────────────────────────┘
```

### Self-Hosted Integration Runtime

The **Self-Hosted IR** is a Windows service installed on a machine inside the on-premises network. It:

- Establishes an outbound HTTPS connection to Azure Data Factory (no inbound ports required)
- Proxies ADF Lookup and Copy Data activities to on-prem Oracle and SQL Server
- Encrypts data in transit (TLS 1.2+)
- Supports high availability with multiple nodes

### Private Endpoints (Recommended for Production)

| Service | Private Endpoint | Purpose |
|---------|-----------------|---------|
| Azure SQL Database | `pe-azuresql` | Eliminates public internet access to target DB |
| Azure Key Vault | `pe-keyvault` | Secrets never traverse public internet |
| Azure Blob Storage | `pe-storage` | Metadata and artifact storage stays private |
| Azure Data Factory | `pe-adf` | ADF management plane stays private |

---

## Monitoring and Observability

### Unified Dashboard

All components log to a single **Log Analytics Workspace**. Application Insights provides:

| Signal | Source | Metric |
|--------|--------|--------|
| Agent conversations | AI Foundry Diagnostics | Requests, tokens, tool calls, latency |
| Tool call success/failure | Logic App run history | Success rate, duration, error codes |
| Pipeline runs | ADF monitoring | Status, duration, rows copied, throughput |
| DDL execution | Logic App → Azure SQL | Success/failure, execution time |
| Validation results | Logic App → Azure SQL | Pass/fail, row count deltas |
| Approval latency | Logic App → Table Storage | Time from request to decision |
| Secret access | Key Vault diagnostics | Access attempts, denied requests |

### Alerts (Recommended)

| Alert | Condition | Action |
|-------|-----------|--------|
| Pipeline failure | ADF pipeline status = Failed | Email + Teams notification |
| Approval timeout | Approval pending > 72 hours | Reminder to approver |
| Validation mismatch | Row count delta > 0 | Email to migration operator |
| Agent error rate | Tool call failure rate > 10% | PagerDuty / Teams alert |
| Key Vault denied access | Access denied events > 0 | Security team notification |

---

## Failure Handling

### Tool Call Failures

When a Logic App returns an error, the agent:

1. Reads the error message from the HTTP response
2. Uses the LLM to diagnose the root cause
3. Explains the failure to the user in plain English
4. Suggests remediation steps
5. Retries if the error is transient (e.g., HTTP 429, timeout)

### DDL Validation Failures

If `validate_ddl` returns syntax errors:

1. Agent reads the T-SQL error messages
2. LLM identifies the problematic DDL statements
3. LLM regenerates corrected DDL
4. Agent calls `validate_ddl` again (max 3 retries)
5. If still failing, agent presents errors to user and asks for guidance

### ADF Pipeline Failures

If `monitor_pipeline_run` returns FAILED:

1. Agent reads the ADF error details (error code, message, affected rows)
2. LLM categorizes the failure: connectivity, data type mismatch, permission, timeout
3. Agent explains the failure and recommends action
4. Agent does **not** automatically retry data movement — this requires explicit user instruction

### State Recovery

On conversation resumption, the agent can:

- Check the last known state in the conversation thread
- Resume from the last successful step
- Re-check approval status if it was pending
- Re-poll ADF pipeline if it was running

---

## Scalability Considerations

| Dimension | POC Limit | Production Path |
|-----------|-----------|-----------------|
| Tables per migration | ~50 | Chunk into multiple agent threads |
| Columns per table | ~200 (context window) | Summarize + paginate |
| Data volume per table | Limited by ADF Copy Activity | Enable staged copy with Blob intermediate |
| Concurrent migrations | 1 per thread | Multiple threads, shared ADF |
| Approval throughput | 1 approver | Power Automate multi-stage approval |
| Schema size (metadata) | ~5,000 columns (ADF Lookup limit) | Stored Procedure + staging table pattern |

---

## Related Documents

- [README.md](README.md) — Project overview, getting started, configuration
- [SECURITY.md](SECURITY.md) — Security configuration, Key Vault setup, RBAC, network isolation
