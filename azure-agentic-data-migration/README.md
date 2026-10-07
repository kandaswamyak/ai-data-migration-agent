# Azure Agentic Data Migration

**Low-Code Database Migration Using Azure AI Foundry Agent Service**

Migrate Oracle and SQL Server databases to Azure SQL Database through a conversational AI agent — no custom Python code, no LangChain, no open-source frameworks. This solution is built entirely on Azure managed services: Azure AI Foundry Agent Service provides the reasoning engine, Azure Data Factory moves the data, Logic Apps orchestrate workflows and approvals, and Azure OpenAI GPT-4.1 handles schema analysis, risk assessment, and DDL generation.

> **Status:** Proof of Concept (POC) — not production-hardened.

---

## Table of Contents

- [What This Solution Does](#what-this-solution-does)
- [Why an Agent?](#why-an-agent)
- [Azure Services Used](#azure-services-used)
- [What the Agent Does](#what-the-agent-does)
- [What the LLM Does](#what-the-llm-does)
- [What Logic Apps and Data Factory Do](#what-logic-apps-and-data-factory-do)
- [How Human Approval Works](#how-human-approval-works)
- [Dry Run vs Real Migration](#dry-run-vs-real-migration)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Known Limitations](#known-limitations)
- [Contributing](#contributing)

---

## What This Solution Does

This POC demonstrates an **AI-driven database migration pipeline** that replaces manual migration playbooks with a conversational agent. A user describes what they want to migrate in plain English, and the agent:

1. **Discovers** source schemas from Oracle or SQL Server via Azure Data Factory metadata queries
2. **Analyzes** datatypes and identifies compatibility risks (Oracle `NUMBER(38)` → Azure SQL `decimal(38,0)`, `CLOB` → `nvarchar(max)`, etc.)
3. **Generates** column-level source-to-target mappings with confidence scores
4. **Produces** migration DDL — `CREATE TABLE`, `ALTER TABLE`, index scripts — tuned for Azure SQL
5. **Requests human approval** before touching any target database
6. **Executes** the migration through Azure Data Factory pipelines (or dry-runs it first)
7. **Validates** results — row counts, checksums, null checks, duplicate detection
8. **Reports** on the outcome with a structured migration summary

All of this happens without writing Python, deploying containers, or managing a web server. The "application" is an Azure AI Foundry agent with tool definitions, orchestrated by Logic Apps.

---

## Why an Agent?

The word **"agent"** in this project refers specifically to an **Azure AI Foundry Agent Service agent** — a managed resource on Azure that:

- Has a **system prompt** defining its role (database migration specialist)
- Can call **tools** (functions) that you define — in this case, tools backed by Logic Apps HTTP triggers and Azure Data Factory REST APIs
- **Reasons** about which tool to call next based on the conversation and the current migration state
- Maintains a **conversation thread** so it remembers what schemas it discovered, what mappings it proposed, and what the human approved

This is not a chatbot. It is a **task-completion agent** — it has a goal (migrate database X to Azure SQL) and a set of capabilities (13+ tools) to achieve that goal. The LLM inside the agent decides the execution order, handles errors, and explains its reasoning.

### What Makes This "Agentic"

| Traditional Pipeline | Agentic Approach |
|---------------------|------------------|
| Fixed DAG of steps | Agent decides next step based on context |
| Fails on unexpected schema | Agent reasons about edge cases, proposes alternatives |
| Static configuration files | Natural language instructions |
| Manual rollback decisions | Agent explains failure and recommends recovery |
| One pipeline per source type | Same agent handles Oracle and SQL Server |

---

## Azure Services Used

| Service | Role | Why This Service |
|---------|------|-----------------|
| **Azure AI Foundry Agent Service** | Hosts the migration agent, manages threads, executes tool calls | Managed agent runtime — no infrastructure to operate |
| **Azure OpenAI GPT-4.1** | LLM backbone for the agent | Best-in-class reasoning for schema analysis and DDL generation |
| **Azure Data Factory (ADF)** | Connects to source databases, moves data to Azure SQL | Enterprise data movement with 100+ connectors, Self-Hosted IR |
| **Logic Apps (Consumption)** | Orchestrates multi-step workflows, handles approvals, calls ADF REST APIs | Low-code workflow engine with built-in connectors |
| **Azure SQL Database** | Migration target database | Managed relational database, T-SQL compatible |
| **Azure Key Vault** | Stores all secrets — connection strings, API keys, credentials | Zero secrets in code, templates, or prompts |
| **Azure Monitor / App Insights** | Logs agent activity, ADF pipeline runs, Logic App executions | Unified observability across all components |
| **Entra ID (Azure AD)** | Authentication and RBAC for all services | Managed identity eliminates credential management |
| **Power Automate** | Human approval workflows with Outlook/Teams integration | Familiar approval UX for non-technical stakeholders |
| **Azure Blob Storage** | Stages migration artifacts — DDL scripts, mapping JSON, reports | Durable artifact storage between agent tool calls |

---

## What the Agent Does

The **Azure Data Migration Agent** is a single agent deployed on Azure AI Foundry Agent Service. It has a system prompt that defines its persona and 13+ tools it can call.

### Agent Identity

```
Name:   Azure Data Migration Agent
Model:  gpt-4.1 (Azure OpenAI deployment)
Role:   Database migration specialist for Oracle/SQL Server → Azure SQL
```

### Agent Tools (13+)

These are the tools registered with the agent. Each tool maps to a Logic App HTTP trigger or an ADF REST endpoint:

| # | Tool Name | Backed By | What It Does |
|---|-----------|-----------|-------------|
| 1 | `discover_source_schema` | ADF + Logic App | Queries source DB metadata (tables, columns, types, keys, indexes) |
| 2 | `analyze_datatypes` | GPT-4.1 (agent-internal) | Maps source types to Azure SQL equivalents, flags risks |
| 3 | `generate_mappings` | GPT-4.1 (agent-internal) | Produces column-level source → target mapping JSON |
| 4 | `assess_migration_risk` | GPT-4.1 (agent-internal) | Rates overall risk (Low/Medium/High), lists specific concerns |
| 5 | `generate_ddl` | GPT-4.1 (agent-internal) | Creates T-SQL DDL for target schema |
| 6 | `validate_ddl` | Logic App → Azure SQL | Parses generated DDL against target DB without executing |
| 7 | `request_human_approval` | Logic App → Power Automate | Sends approval request with risk summary and DDL preview |
| 8 | `check_approval_status` | Logic App | Polls approval status (PENDING / APPROVED / REJECTED) |
| 9 | `execute_ddl` | Logic App → Azure SQL | Runs approved DDL on target database |
| 10 | `trigger_adf_pipeline` | Logic App → ADF REST API | Starts data copy pipeline with parameterized source/target |
| 11 | `monitor_pipeline_run` | Logic App → ADF REST API | Checks ADF pipeline run status |
| 12 | `validate_migration` | Logic App → Azure SQL | Runs row count, checksum, null, and duplicate checks |
| 13 | `generate_report` | GPT-4.1 (agent-internal) | Summarizes migration outcome in structured markdown |

### How the Agent Decides What to Do

The agent does **not** follow a hardcoded sequence. The LLM reasons about the current state and decides which tool to call next. For example:

- If the user says *"Migrate the HR schema from Oracle to Azure SQL"*, the agent calls `discover_source_schema` first.
- If `discover_source_schema` returns 47 tables, the agent might say *"I found 47 tables in the HR schema. Shall I analyze all of them or a subset?"*
- If DDL validation fails, the agent reads the error, fixes the DDL, and retries — without human intervention.
- If risk assessment returns HIGH, the agent warns the human before requesting approval.

---

## What the LLM Does

Azure OpenAI GPT-4.1 is the reasoning engine inside the agent. It is responsible for:

### Schema Analysis and Mapping
- Reads source metadata (Oracle `ALL_TAB_COLUMNS` / SQL Server `INFORMATION_SCHEMA.COLUMNS`)
- Maps each source datatype to the best Azure SQL equivalent
- Assigns confidence scores (0.0–1.0) per column mapping
- Flags transformations: `Direct` | `Type Conversion` | `Data Transform` | `Manual Review`

### Risk Assessment
- Evaluates each mapping for data loss risk
- Identifies high-risk patterns: precision loss (`NUMBER(38)` → `decimal`), encoding issues (`NCLOB`), unsupported types (`XMLTYPE`, `SDO_GEOMETRY`)
- Produces a GO / CAUTION / STOP recommendation

### DDL Generation
- Generates `CREATE TABLE` statements with proper Azure SQL syntax
- Handles: primary keys, foreign keys, indexes, default values, `NOT NULL` constraints
- Converts Oracle-specific syntax (sequences → `IDENTITY`, `SYSDATE` → `GETDATE()`)

### Migration Planning
- Determines table execution order based on foreign key dependencies
- Estimates data volumes and recommends batch sizes for ADF
- Suggests parallel copy degree for large tables

### Error Explanation
- When ADF pipelines fail, the agent reads error messages and explains them in plain English
- Recommends corrective actions (e.g., *"Column EMPLOYEE_PHOTO is BLOB type — ADF Binary copy activity needed instead of tabular copy"*)

> **Important:** The LLM never touches your data directly. It reasons about metadata and generates SQL/configuration. Azure Data Factory handles all actual data movement.

---

## What Logic Apps and Data Factory Do

### Logic Apps — The Orchestration Layer

Logic Apps serve as the **glue** between the AI agent and Azure infrastructure:

```
Agent tool call  →  Logic App HTTP trigger  →  Execute action  →  Return result to agent
```

Each agent tool maps to a Logic App workflow:

- **Schema Discovery Logic App** — Triggers an ADF pipeline that queries source metadata, waits for completion, reads output from Blob Storage, returns JSON to the agent
- **Approval Logic App** — Receives approval request from agent, stores it in Azure Table Storage, triggers Power Automate flow, exposes a REST endpoint for status polling
- **DDL Execution Logic App** — Takes DDL SQL from agent, connects to Azure SQL via managed identity, executes DDL, returns success/error
- **ADF Trigger Logic App** — Calls ADF REST API to start a parameterized Copy Data pipeline, returns the pipeline run ID
- **Validation Logic App** — Runs validation queries on both source and target, compares row counts and checksums

### Azure Data Factory — The Data Movement Engine

ADF handles all actual data connectivity and movement:

- **Self-Hosted Integration Runtime** — Installed on-premises to reach Oracle and SQL Server instances behind firewalls
- **Linked Services** — Connection configurations for Oracle, SQL Server, and Azure SQL (credentials from Key Vault)
- **Parameterized Pipelines** — A single Copy Data pipeline accepts source table, target table, column mappings, and batch size as parameters
- **Metadata Pipelines** — Dedicated pipelines that query `ALL_TAB_COLUMNS`, `ALL_CONSTRAINTS`, `INFORMATION_SCHEMA` and write results to Blob Storage

---

## How Human Approval Works

No migration runs without explicit human approval. Two approval paths are supported:

### Path 1: Power Automate Approval (Recommended)

```
Agent calls request_human_approval
    → Logic App stores request in Azure Table Storage
    → Logic App triggers Power Automate flow
    → Power Automate sends Outlook/Teams approval
    → Approver clicks Approve or Reject
    → Power Automate calls Logic App callback URL
    → Agent polls check_approval_status → APPROVED
    → Agent proceeds with DDL execution
```

**What the approver sees:**
- Migration summary (source → target)
- Table and column counts
- Risk assessment (Low/Medium/High)
- Full DDL preview
- List of high-risk columns with explanations
- Approve / Reject buttons with optional comments

### Path 2: REST API Endpoint

For automated pipelines or custom UIs, the approval Logic App exposes a REST endpoint:

```
POST https://<logic-app>.azurewebsites.net/api/approve/{migration-id}
Authorization: Bearer <entra-id-token>
Content-Type: application/json

{
    "decision": "APPROVED",
    "approver": "jane.doe@contoso.com",
    "comments": "Reviewed DDL and risk assessment. Proceed."
}
```

The agent detects the approval on its next `check_approval_status` poll and proceeds.

### Approval State Machine

```
PENDING  ──→  APPROVED  ──→  (Agent proceeds to execute)
   │
   └──→  REJECTED  ──→  (Agent explains rejection and asks for guidance)
```

---

## Dry Run vs Real Migration

### Dry Run (Default)

A dry run executes the **entire migration lifecycle** except actual data movement:

```
✅  Schema discovery         — real metadata from source DB
✅  Datatype analysis         — real LLM analysis
✅  Mapping generation        — real mappings
✅  Risk assessment           — real risk analysis
✅  DDL generation            — real T-SQL
✅  DDL validation            — parsed against target DB (no execution)
✅  Human approval            — real approval flow
❌  DDL execution             — SKIPPED (logged only)
❌  ADF data copy             — SKIPPED (logged only)
❌  Post-migration validation — SKIPPED (no data to validate)
✅  Report generation         — full report with "DRY RUN" watermark
```

**To trigger a dry run**, tell the agent:
> *"Run a dry run migration of the HR schema from Oracle to Azure SQL"*

Or set the `dry_run` parameter in the agent configuration:
```json
{
    "migration_mode": "dry_run"
}
```

### Real Migration

A real migration executes everything including DDL and data movement:

> *"Execute the migration of the HR schema from Oracle to Azure SQL"*

Or:
```json
{
    "migration_mode": "execute"
}
```

> ⚠️ **Real migrations require human approval.** The agent will not skip the approval step regardless of the migration mode.

---

## Getting Started

### Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure Subscription | With permissions to create AI Foundry, ADF, Logic Apps, Azure SQL, Key Vault |
| Azure AI Foundry | Agent Service enabled (preview) |
| Azure OpenAI | GPT-4.1 model deployed |
| Source Database | Oracle 12c+ or SQL Server 2016+ accessible via Self-Hosted IR |
| Target Database | Azure SQL Database (provisioned) |
| Azure CLI | v2.60+ |
| Entra ID | App registrations for agent and approval flow |

### Deployment Steps

1. **Deploy infrastructure** — Use the Bicep templates in `infra/`:
   ```bash
   az deployment group create \
     --resource-group rg-data-migration \
     --template-file infra/main.bicep \
     --parameters infra/parameters.json
   ```

2. **Configure Key Vault secrets** — See [SECURITY.md](SECURITY.md) for the full list:
   ```bash
   az keyvault secret set --vault-name kv-datamigration \
     --name "oracle-connection-string" \
     --value "<your-connection-string>"
   ```

3. **Import Logic App workflows** — Deploy the JSON definitions from `logic-apps/`:
   ```bash
   az logic workflow create \
     --resource-group rg-data-migration \
     --name la-schema-discovery \
     --definition logic-apps/schema-discovery.json
   ```

4. **Import ADF pipelines** — Deploy ARM templates from `adf-pipelines/`:
   ```bash
   az datafactory pipeline create \
     --resource-group rg-data-migration \
     --factory-name adf-datamigration \
     --name pl-copy-data \
     --pipeline @adf-pipelines/copy-data-pipeline.json
   ```

5. **Create the agent** — Register the agent in Azure AI Foundry with the system prompt and tool definitions from `agent-config/`.

6. **Test with a dry run** — Start a conversation with the agent and request a dry run.

---

## Project Structure

```
azure-agentic-data-migration/
│
├── README.md                        # This file
├── ARCHITECTURE.md                  # Detailed architecture documentation
├── SECURITY.md                      # Security configuration guide
│
├── agent-config/                    # Azure AI Foundry Agent configuration
│   ├── system-prompt.md             # Agent system prompt
│   ├── tool-definitions.json        # Agent tool schemas (OpenAPI-style)
│   └── agent-settings.json          # Model deployment, temperature, etc.
│
├── logic-apps/                      # Logic App workflow definitions (JSON)
│   ├── schema-discovery.json        # Source schema metadata extraction
│   ├── approval-workflow.json       # Human approval via Power Automate
│   ├── ddl-execution.json           # Execute DDL on Azure SQL
│   ├── adf-trigger.json             # Trigger ADF pipeline runs
│   ├── pipeline-monitor.json        # Poll ADF pipeline status
│   └── validation.json              # Post-migration validation queries
│
├── adf-pipelines/                   # Azure Data Factory ARM templates
│   ├── copy-data-pipeline.json      # Parameterized Copy Data pipeline
│   ├── metadata-pipeline.json       # Source metadata extraction pipeline
│   └── linked-services/             # ADF Linked Service definitions
│       ├── oracle-linked-service.json
│       ├── sqlserver-linked-service.json
│       └── azuresql-linked-service.json
│
├── infra/                           # Bicep / ARM infrastructure templates
│   ├── main.bicep                   # Main deployment orchestration
│   ├── parameters.json              # Deployment parameters
│   ├── modules/
│   │   ├── keyvault.bicep           # Key Vault with access policies
│   │   ├── adf.bicep                # Data Factory with managed identity
│   │   ├── logicapps.bicep          # Logic App definitions
│   │   ├── azuresql.bicep           # Azure SQL Database
│   │   ├── storage.bicep            # Blob Storage for artifacts
│   │   └── monitoring.bicep         # App Insights + Log Analytics
│   └── scripts/
│       └── seed-keyvault.sh         # Populate Key Vault secrets
│
├── schemas/                         # JSON Schema definitions
│   ├── migration-request.schema.json
│   ├── mapping-output.schema.json
│   ├── approval-request.schema.json
│   └── validation-report.schema.json
│
├── samples/                         # Sample payloads and test data
│   ├── oracle-hr-metadata.json      # Sample Oracle HR schema metadata
│   ├── sqlserver-adventureworks.json # Sample SQL Server metadata
│   ├── sample-mapping-output.json   # Example agent mapping output
│   └── sample-approval-request.json # Example approval payload
│
└── sql/                             # Reference SQL scripts
    ├── oracle-metadata-query.sql    # Query to extract Oracle schema metadata
    ├── sqlserver-metadata-query.sql # Query to extract SQL Server metadata
    └── validation-queries.sql       # Post-migration validation queries
```

---

## Configuration

### Agent Configuration (`agent-config/agent-settings.json`)

```json
{
    "agent_name": "Azure Data Migration Agent",
    "model_deployment": "gpt-4.1",
    "temperature": 0.1,
    "max_tokens": 16000,
    "tool_choice": "auto",
    "migration_defaults": {
        "migration_mode": "dry_run",
        "batch_size": 10000,
        "parallel_copy_degree": 4,
        "approval_timeout_hours": 72,
        "validation_checks": ["row_count", "checksum", "null_count", "duplicate_check"]
    }
}
```

### Environment Variables

All secrets are stored in Key Vault. These environment variables point to the vault:

| Variable | Description |
|----------|-------------|
| `AZURE_KEYVAULT_NAME` | Key Vault instance name |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_RESOURCE_GROUP` | Resource group name |
| `ADF_FACTORY_NAME` | Azure Data Factory instance name |
| `AI_FOUNDRY_ENDPOINT` | Azure AI Foundry endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | GPT-4.1 deployment name |

> ⚠️ **Never place secrets directly in configuration files, prompts, JSON templates, or environment variables.** Always reference Key Vault. See [SECURITY.md](SECURITY.md).

---

## Known Limitations

This is a **proof of concept**. The following limitations apply:

### Scope
- **Two source types only:** Oracle 12c+ and SQL Server 2016+. No MySQL, PostgreSQL, DB2, etc.
- **Single target:** Azure SQL Database only. No Azure Synapse, Cosmos DB, or Fabric.
- **Schema-level migration:** Migrates tables, columns, primary keys, foreign keys, and indexes. Does not migrate stored procedures, triggers, views, sequences (as objects), or synonyms.

### Agent Behavior
- **Single-threaded conversation:** One migration per agent thread. Parallel migrations require separate threads.
- **No persistent memory across threads:** Each conversation starts fresh. The agent does not remember previous migrations.
- **Token limits:** Very large schemas (500+ tables) may exceed context windows. Chunk into multiple requests.
- **Non-deterministic:** LLM outputs may vary across runs. DDL should always be reviewed by a human.

### Data Movement
- **ADF Copy Activity limitations:** BLOB/CLOB columns require Binary copy mode. Large LOBs may need staged copy.
- **No CDC / incremental sync:** Full-table copy only. No change data capture support.
- **No data transformation:** Column-level type mapping only. No row-level ETL logic (use ADF Mapping Data Flows for that).

### Security
- **POC-level authentication:** Uses connection strings stored in Key Vault. Production should use managed identity end-to-end.
- **No network isolation in default deployment:** Private endpoints must be configured manually. See [SECURITY.md](SECURITY.md).

### Operational
- **No automated rollback:** The agent can explain failures but does not automatically drop created tables or restore state.
- **No migration scheduling:** Migrations run on-demand. No built-in support for maintenance window scheduling.
- **No multi-environment promotion:** No dev → staging → prod pipeline. Single environment per deployment.

---

## Contributing

This is an internal POC. To contribute:

1. Fork the repository
2. Create a feature branch (`feature/your-feature`)
3. Submit a pull request with a clear description
4. Ensure all Logic App and ADF templates are valid JSON
5. Update documentation for any new agent tools

---

## License

Internal use only. Not licensed for external distribution.

---

## Related Documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — Detailed architecture, data flows, and state machine
- [SECURITY.md](SECURITY.md) — Security configuration, Key Vault setup, RBAC, network isolation
