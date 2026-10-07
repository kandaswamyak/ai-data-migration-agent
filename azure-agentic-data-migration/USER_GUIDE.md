# 📘 Azure Agentic Data Migration — User Guide

> **Version:** 1.0 · **Last Updated:** 2026-09-03  
> **Audience:** Database administrators, migration engineers, project leads, and anyone running a migration  
> **Prerequisite:** The environment must be deployed per [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Table of Contents

1. [What Is the Migration Agent?](#1-what-is-the-migration-agent)
2. [Getting Started — Starting a Conversation](#2-getting-started--starting-a-conversation)
3. [Providing Source & Target Details](#3-providing-source--target-details)
4. [Schema Discovery](#4-schema-discovery)
5. [Understanding the Migration Plan](#5-understanding-the-migration-plan)
6. [Reviewing & Approving a Migration](#6-reviewing--approving-a-migration)
7. [Migration Execution](#7-migration-execution)
8. [Monitoring Progress](#8-monitoring-progress)
9. [Reading Validation Reports](#9-reading-validation-reports)
10. [Handling Errors](#10-handling-errors)
11. [Cancelling a Migration](#11-cancelling-a-migration)
12. [Sample Conversation Flows](#12-sample-conversation-flows)
13. [Frequently Asked Questions](#13-frequently-asked-questions)
14. [Glossary](#14-glossary)

---

## 1. What Is the Migration Agent?

The **Data Migration Agent** is an AI-powered assistant that guides you through migrating databases from **Oracle** or **SQL Server** to **Azure SQL Database**. Instead of writing scripts, configuring pipelines manually, or memorizing data type mappings, you simply have a conversation.

### What the Agent Does

| Step | What Happens | Your Role |
|------|-------------|-----------|
| 🔍 **Schema Discovery** | Agent connects to your source database and catalogs all tables, columns, data types, keys | Provide connection details |
| 📋 **Migration Planning** | AI generates column-level type mappings, DDL statements, batch strategy | Review the plan |
| ✅ **Approval** | Agent sends the plan to a designated approver via email or Teams | Approve or reject |
| 🚀 **Execution** | Agent creates target tables in Azure SQL and copies data via ADF pipelines | Monitor progress |
| 📊 **Validation** | Agent runs row counts, null checks, sample comparisons, schema verification | Review the report |

### What the Agent Does NOT Do

- ❌ Modify your source database (it only reads)
- ❌ Execute anything without your approval
- ❌ Store your passwords (all credentials live in Azure Key Vault)
- ❌ Handle application code changes or stored procedure migration (schema + data only)

---

## 2. Getting Started — Starting a Conversation

### Access the Agent

The migration agent is available through:

| Channel | How to Access |
|---------|---------------|
| **AI Foundry Playground** | [ai.azure.com](https://ai.azure.com) → Your project → Agents → `data-migration-agent` → Open in Playground |
| **Microsoft Teams** (if configured) | Search for "Data Migration Agent" in Teams chat |
| **Custom Web App** (if deployed) | Navigate to the web app URL provided by your admin |

### Start the Conversation

Simply greet the agent and state your need:

```
You: Hi, I need to migrate a database to Azure SQL.
```

The agent will respond with a friendly greeting and ask for details:

```
Agent: Hello! I'd be happy to help you migrate your database to Azure SQL Database.

To get started, I need a few details about your source database:

1. **Database type**: Is it Oracle or SQL Server?
2. **Host/IP**: What is the hostname or IP address of the database server?
3. **Database name**: What is the database name (SQL Server) or service name (Oracle)?
4. **Schema**: Which schema(s) would you like to migrate? (e.g., HR, dbo, SALES)

Please provide these details and I'll begin the discovery process!
```

---

## 3. Providing Source & Target Details

### What You Need to Provide

| Detail | Oracle Example | SQL Server Example |
|--------|---------------|-------------------|
| **Database type** | Oracle | SQL Server |
| **Host** | `10.0.10.50` or `oracle-prod.internal.corp` | `10.0.10.60` or `sqlserver-prod.internal.corp` |
| **Database/Service** | `FREEPDB1` or `ORCL` | `MigrationDemo` or `AdventureWorks` |
| **Schema (optional)** | `HR`, `SALES`, `OE` | `dbo`, `HumanResources`, `Sales` |

### How to Provide Details

You can provide details in any natural format. The agent understands all of these:

**Structured format:**
```
Source type: Oracle
Host: 10.0.10.50
Service: FREEPDB1
Schema: HR
```

**Conversational format:**
```
I want to migrate the HR schema from our Oracle server at 10.0.10.50, 
service name FREEPDB1, to Azure SQL.
```

**Single line:**
```
Migrate Oracle HR schema from 10.0.10.50/FREEPDB1 to Azure SQL.
```

### What About the Target?

You don't need to specify target details — the agent automatically uses the pre-configured Azure SQL Database target (`sqldb-migration-target`). If your environment has multiple targets, your admin will configure them.

### Security Note

> ⚠️ **You never need to provide passwords.** All connection credentials are securely stored in Azure Key Vault. The agent uses managed identities — no passwords pass through the conversation.

---

## 4. Schema Discovery

### What Happens During Discovery

When you provide source details, the agent:

1. Creates a unique **Job ID** (UUID) to track your migration
2. Calls the **Schema Discovery** tool
3. Connects to your source database via Azure Data Factory (through the Self-Hosted Integration Runtime)
4. Queries the database catalog to find all tables, columns, data types, keys, and constraints
5. Stores the results in the migration metadata database
6. Presents the findings to you

### What You'll See

The agent presents discovered schema in a formatted table:

```
Agent: I've discovered the following schema for the HR schema on Oracle (FREEPDB1):

📊 **Schema Discovery Results — Job: a1b2c3d4-...**

| # | Table | Columns | Rows (est.) | Primary Key |
|---|-------|---------|-------------|-------------|
| 1 | EMPLOYEES | 11 | 107 | EMPLOYEE_ID |
| 2 | DEPARTMENTS | 4 | 27 | DEPARTMENT_ID |
| 3 | JOBS | 4 | 19 | JOB_ID |
| 4 | LOCATIONS | 6 | 23 | LOCATION_ID |
| 5 | COUNTRIES | 3 | 25 | COUNTRY_ID |
| 6 | REGIONS | 2 | 4 | REGION_ID |
| 7 | JOB_HISTORY | 5 | 10 | (EMPLOYEE_ID, START_DATE) |

**Total:** 7 tables, 35 columns

Would you like me to generate a migration plan for all 7 tables, or would you 
like to select specific tables?
```

### Selecting Specific Tables

You can migrate all tables or pick specific ones:

**All tables:**
```
You: Generate a plan for all tables.
```

**Specific tables:**
```
You: Just migrate EMPLOYEES, DEPARTMENTS, and JOBS.
```

**Exclude tables:**
```
You: Migrate everything except JOB_HISTORY.
```

---

## 5. Understanding the Migration Plan

### What the Plan Contains

After discovery, the agent generates a detailed migration plan using AI. The plan includes:

1. **Column-level type mappings** — How each Oracle/SQL Server data type maps to Azure SQL
2. **DDL statements** — `CREATE TABLE` scripts for the target database
3. **Complexity assessment** — Simple, moderate, or complex per table
4. **Migration strategy** — Batch size, parallelism, estimated duration
5. **Potential issues** — Data type conversion warnings, precision loss risks

### Reading the Plan

The agent presents the plan in an easy-to-read format:

```
Agent: Here is the migration plan for Job a1b2c3d4-...

## 📋 Migration Plan

### Type Mappings

| Source Table | Source Column | Oracle Type | → Azure SQL Type | Confidence | Notes |
|-------------|-------------|-------------|-------------------|------------|-------|
| EMPLOYEES | EMPLOYEE_ID | NUMBER(6,0) | INT | 99% | Direct mapping |
| EMPLOYEES | FIRST_NAME | VARCHAR2(20) | NVARCHAR(20) | 98% | Unicode-safe |
| EMPLOYEES | LAST_NAME | VARCHAR2(25) | NVARCHAR(25) | 98% | Unicode-safe |
| EMPLOYEES | EMAIL | VARCHAR2(25) | NVARCHAR(25) | 98% | |
| EMPLOYEES | HIRE_DATE | DATE | DATETIME2(0) | 95% | Oracle DATE includes time |
| EMPLOYEES | SALARY | NUMBER(8,2) | DECIMAL(8,2) | 99% | Exact precision |
| EMPLOYEES | COMMISSION_PCT | NUMBER(2,2) | DECIMAL(2,2) | 99% | Nullable |

### DDL Preview (EMPLOYEES)

```sql
CREATE TABLE [dbo].[EMPLOYEES] (
    [EMPLOYEE_ID]    INT           NOT NULL,
    [FIRST_NAME]     NVARCHAR(20)  NULL,
    [LAST_NAME]      NVARCHAR(25)  NOT NULL,
    [EMAIL]          NVARCHAR(25)  NOT NULL,
    [PHONE_NUMBER]   NVARCHAR(20)  NULL,
    [HIRE_DATE]      DATETIME2(0)  NOT NULL,
    [JOB_ID]         NVARCHAR(10)  NOT NULL,
    [SALARY]         DECIMAL(8,2)  NULL,
    [COMMISSION_PCT] DECIMAL(2,2)  NULL,
    [MANAGER_ID]     INT           NULL,
    [DEPARTMENT_ID]  INT           NULL,
    CONSTRAINT [PK_EMPLOYEES] PRIMARY KEY ([EMPLOYEE_ID])
);
```

### Complexity Assessment

| Table | Complexity | Estimated Rows | Est. Duration |
|-------|-----------|---------------|---------------|
| EMPLOYEES | Simple | 107 | <1 min |
| DEPARTMENTS | Simple | 27 | <1 min |
| JOBS | Simple | 19 | <1 min |
| LOCATIONS | Simple | 23 | <1 min |

### Strategy
- **Batch size:** 10,000 rows per batch
- **Parallel tables:** 4 concurrent
- **Estimated total time:** ~5 minutes
```

### Understanding Confidence Scores

| Confidence | Meaning |
|-----------|---------|
| **95–100%** | Direct or well-known mapping. No risk of data loss. |
| **80–94%** | Good mapping with minor considerations (e.g., precision adjustment). |
| **60–79%** | Requires attention — possible truncation or behavior difference. |
| **<60%** | Manual review recommended — complex type with no direct equivalent. |

### Common Type Mapping Highlights

| Oracle Type | Azure SQL Type | Notes |
|------------|---------------|-------|
| `NUMBER(p,s)` | `DECIMAL(p,s)` or `INT`/`BIGINT` | INT if scale=0 and precision≤10 |
| `VARCHAR2(n)` | `NVARCHAR(n)` | Unicode-safe default |
| `DATE` | `DATETIME2(0)` | Oracle DATE includes time component |
| `CLOB` | `NVARCHAR(MAX)` | Up to 2 GB |
| `BLOB` | `VARBINARY(MAX)` | Binary large object |
| `TIMESTAMP` | `DATETIME2(7)` | Fractional seconds preserved |
| `RAW(n)` | `VARBINARY(n)` | Binary data |

---

## 6. Reviewing & Approving a Migration

### Reviewing the Plan

After the agent presents the plan, you have several options:

**✅ Approve as-is:**
```
You: The plan looks good. Let's proceed with approval.
```

**✏️ Request changes:**
```
You: Can you change HIRE_DATE to DATE instead of DATETIME2? 
     Also, use VARCHAR instead of NVARCHAR for EMAIL.
```

**❓ Ask questions:**
```
You: Why did you choose NVARCHAR instead of VARCHAR for the text columns?
```

**🔄 Regenerate with preferences:**
```
You: Regenerate the plan but use VARCHAR for all text columns 
     and keep Oracle NUMBER as NUMERIC instead of INT.
```

### Triggering the Approval Workflow

Once you're satisfied with the plan, tell the agent to send it for approval:

```
You: Send the plan for approval to admin@contoso.com
```

The agent will:
1. Call the approval workflow
2. The approver receives an **email** or **Teams adaptive card** containing:
   - Migration summary (source → target)
   - Table count and estimated duration
   - Key type mapping highlights
   - **Approve** and **Reject** buttons

### What the Approver Sees

**Email format:**
```
Subject: Migration Approval Required — Job a1b2c3d4-...

Migration Plan Summary
━━━━━━━━━━━━━━━━━━━━━
Source: Oracle (HR schema) at 10.0.10.50/FREEPDB1
Target: Azure SQL Database (sqldb-migration-target)
Tables: 7
Estimated Duration: ~5 minutes
Requested by: user@contoso.com

[Approve]  [Reject]
```

**Teams adaptive card:**
A rich card with the same information plus inline table preview, with Approve/Reject buttons.

### Approval Outcomes

| Outcome | What Happens |
|---------|-------------|
| **Approved** | Agent is notified and proceeds to execution (with your confirmation) |
| **Rejected** | Agent informs you with the rejection reason; you can revise and resubmit |
| **Timed out** (72 hours) | Agent informs you; you can resend the approval request |

### After Approval

```
Agent: ✅ Great news! Your migration plan has been approved by admin@contoso.com 
       at 2026-09-03 14:32 UTC.

       Shall I proceed with executing the migration? This will:
       1. Create 7 target tables in Azure SQL
       2. Copy all data from Oracle to Azure SQL
       
       Type "yes" to proceed or "no" to cancel.
```

---

## 7. Migration Execution

### Starting the Migration

After approval, confirm to the agent:

```
You: Yes, execute the migration.
```

### What Happens During Execution

1. **DDL Phase:** Target tables are created in Azure SQL Database
2. **Data Copy Phase:** Azure Data Factory pipelines copy data table-by-table
3. **Logging:** Every step is logged in the metadata database

### Execution Progress

The agent provides real-time updates:

```
Agent: 🚀 Migration execution started for Job a1b2c3d4-...

       Phase 1: Creating target tables...
       ✅ EMPLOYEES — table created
       ✅ DEPARTMENTS — table created
       ✅ JOBS — table created
       ✅ LOCATIONS — table created
       ✅ COUNTRIES — table created
       ✅ REGIONS — table created
       ✅ JOB_HISTORY — table created
       
       Phase 2: Copying data...
       ✅ EMPLOYEES — 107 rows copied (2.1s)
       ✅ DEPARTMENTS — 27 rows copied (1.4s)
       ✅ JOBS — 19 rows copied (1.2s)
       ✅ LOCATIONS — 23 rows copied (1.3s)
       ✅ COUNTRIES — 25 rows copied (1.2s)
       ✅ REGIONS — 4 rows copied (0.9s)
       ✅ JOB_HISTORY — 10 rows copied (1.1s)
       
       ✅ **Migration Complete!**
       Total: 7/7 tables migrated, 215 rows copied, duration: 48 seconds
       
       Would you like me to run validation checks?
```

### Partial Failures

If some tables fail, the agent reports clearly:

```
Agent: ⚠️ Migration completed with issues.

       ✅ Succeeded: 6/7 tables (205 rows)
       ❌ Failed: 1 table
       
       | Table | Status | Error |
       |-------|--------|-------|
       | JOB_HISTORY | ❌ Failed | Composite PK constraint violation |
       
       The other 6 tables migrated successfully. 
       Would you like me to:
       1. Retry the failed table
       2. Skip it and proceed to validation
       3. Investigate the error
```

---

## 8. Monitoring Progress

### During Migration

You can ask the agent about status at any time:

```
You: What's the current status of my migration?
```

```
Agent: Here's the current status of Job a1b2c3d4-...

       | Metric | Value |
       |--------|-------|
       | Status | Executing |
       | Tables completed | 4 of 7 |
       | Rows copied so far | 176 |
       | Current table | COUNTRIES |
       | Elapsed time | 32 seconds |
       | Estimated remaining | ~15 seconds |
```

### Checking Past Migrations

```
You: Show me the status of all my recent migrations.
```

```
Agent: Here are your recent migration jobs:

       | Job ID | Source | Status | Tables | Created |
       |--------|--------|--------|--------|---------|
       | a1b2c3d4-... | Oracle HR | ✅ Validated | 7 | Sep 3, 14:00 |
       | e5f6g7h8-... | SQL Server MigrationDemo | ⏳ Awaiting Approval | 12 | Sep 2, 10:30 |
       | i9j0k1l2-... | Oracle SALES | ❌ Failed | 15 | Sep 1, 09:15 |
```

### Azure Portal Monitoring

For detailed pipeline monitoring, you can also check:

1. **Azure Data Factory** → Monitor → Pipeline runs
2. **Logic Apps** → Overview → Run history
3. **Application Insights** → Logs (KQL queries)
4. **Azure SQL** → Query `dbo.MigrationLog` for detailed step-by-step logs

---

## 9. Reading Validation Reports

### Triggering Validation

After migration completes, the agent will ask to run validation. You can also request it explicitly:

```
You: Run full validation on the migration.
```

Or request specific checks:

```
You: Just run row count and schema comparison checks.
```

### Validation Check Types

| Check Type | What It Does |
|-----------|-------------|
| **RowCount** | Compares row counts between source and target for each table |
| **NullCheck** | Compares NULL value distributions per column |
| **SampleData** | Compares first 10 rows of each table |
| **SchemaCompare** | Verifies target table structure matches the migration plan |
| **Checksum** | Computes hash-based comparison (for supported column types) |

### Reading the Report

```
Agent: 📊 **Validation Report — Job a1b2c3d4-...**

       Overall: ✅ **PASSED** (28/28 checks passed)

       ### Row Count Validation
       | Table | Source | Target | Match |
       |-------|--------|--------|-------|
       | EMPLOYEES | 107 | 107 | ✅ |
       | DEPARTMENTS | 27 | 27 | ✅ |
       | JOBS | 19 | 19 | ✅ |
       | LOCATIONS | 23 | 23 | ✅ |
       | COUNTRIES | 25 | 25 | ✅ |
       | REGIONS | 4 | 4 | ✅ |
       | JOB_HISTORY | 10 | 10 | ✅ |

       ### Schema Comparison
       | Table | Columns Match | Types Match | Keys Match |
       |-------|--------------|-------------|------------|
       | EMPLOYEES | ✅ 11/11 | ✅ 11/11 | ✅ PK |
       | DEPARTMENTS | ✅ 4/4 | ✅ 4/4 | ✅ PK |
       | ... | ... | ... | ... |

       ### Null Distribution Check
       All columns: ✅ NULL counts match between source and target.

       ### Sample Data Comparison
       First 10 rows of each table: ✅ All values match.

       ─────────────────────────────────
       Migration validated successfully!
       Your data is ready in Azure SQL Database.
```

### When Validation Fails

```
Agent: 📊 **Validation Report — Job a1b2c3d4-...**

       Overall: ⚠️ **PARTIAL PASS** (26/28 checks passed, 2 failed)

       ### Failures:
       | Table | Check | Source | Target | Issue |
       |-------|-------|--------|--------|-------|
       | EMPLOYEES | RowCount | 107 | 105 | ❌ 2 rows missing |
       | EMPLOYEES | NullCheck (COMMISSION_PCT) | 72 nulls | 70 nulls | ❌ Mismatch |

       ### Recommended Actions:
       1. Check if EMPLOYEES has rows with special characters that failed during copy
       2. Review ADF pipeline logs for EMPLOYEES table copy activity
       3. Consider re-running the EMPLOYEES table migration

       Would you like me to investigate the EMPLOYEES table failure?
```

---

## 10. Handling Errors

### Common Error Messages and What To Do

#### "Source database is not reachable"

```
Agent: ❌ Error: Unable to connect to the source database at 10.0.10.50.
       
       Possible causes:
       • The database server is down or unreachable
       • The Self-Hosted Integration Runtime VM is not running
       • Firewall rules are blocking port 1521 (Oracle) or 1433 (SQL Server)
       
       Please check with your DBA or network team and try again.
```

**What to do:** Verify the source database is running and the SHIR VM can reach it. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

#### "Approval timed out"

```
Agent: ⚠️ The approval request for Job a1b2c3d4-... has timed out after 72 hours.
       
       Would you like me to:
       1. Resend the approval to the same approver
       2. Send to a different approver
       3. Cancel the migration
```

**What to do:** Resend to the same or a different approver.

#### "Pipeline execution failed"

```
Agent: ❌ Data copy failed for table EMPLOYEES.
       Error: "The column 'HIRE_DATE' cannot be converted from 'DATE' to 'DATETIME2'."
       
       This may be due to a date value outside the DATETIME2 range (e.g., year 0001).
       
       Would you like me to:
       1. Investigate the problematic rows
       2. Retry with a different type mapping
       3. Skip this table and continue with others
```

**What to do:** Follow the agent's suggestions. Most errors are recoverable.

### Asking the Agent for Help

You can always ask the agent to explain or investigate:

```
You: What went wrong with the EMPLOYEES table?
You: Can you check the pipeline logs for the last failure?
You: How do I fix a type conversion error?
```

---

## 11. Cancelling a Migration

### Before Execution

If you haven't started execution yet, simply tell the agent:

```
You: Cancel this migration.
```

```
Agent: Migration Job a1b2c3d4-... has been cancelled. 
       No changes were made to the target database.
       The job status has been updated to "Cancelled" in the metadata.
```

### During Execution

If migration is in progress:

```
You: Stop the migration immediately.
```

```
Agent: ⚠️ I'm cancelling the in-progress migration for Job a1b2c3d4-...

       Note: Tables that have already been fully copied will remain in the target 
       database. Tables currently being copied will be stopped.
       
       | Table | Status |
       |-------|--------|
       | EMPLOYEES | ✅ Completed (will remain) |
       | DEPARTMENTS | ✅ Completed (will remain) |
       | JOBS | 🔄 Copying... → ❌ Cancelled |
       | LOCATIONS | ⏸️ Not started |
       
       Would you like me to:
       1. Clean up (drop the target tables that were created)
       2. Keep the completed tables and resume later
       3. Leave everything as-is
```

### After Execution (Rollback)

```
You: I need to roll back the migration. Drop all the target tables.
```

```
Agent: I'll clean up the target tables for Job a1b2c3d4-...
       
       ⚠️ This will permanently delete the following tables from Azure SQL:
       - dbo.EMPLOYEES (107 rows)
       - dbo.DEPARTMENTS (27 rows)
       - dbo.JOBS (19 rows)
       - dbo.LOCATIONS (23 rows)
       
       Are you sure? Type "yes, drop all" to confirm.
```

---

## 12. Sample Conversation Flows

### Flow 1: Complete Oracle Migration (Happy Path)

```
You:    Hi, I need to migrate our HR Oracle database to Azure SQL.

Agent:  Hello! I'd be happy to help. Please provide:
        1. Host/IP of the Oracle server
        2. Service name
        3. Schema to migrate

You:    Host: 10.0.10.50, Service: FREEPDB1, Schema: HR

Agent:  Starting schema discovery for Oracle HR at 10.0.10.50/FREEPDB1...
        [calls discover_schema]
        
        Found 7 tables with 35 columns. [shows table]
        Generate a migration plan for all tables?

You:    Yes, generate a plan for all tables.

Agent:  [calls generate_migration_plan]
        Here's the migration plan: [shows type mappings, DDL, strategy]
        Would you like to proceed with approval?

You:    Looks good. Send for approval to dba-lead@contoso.com.

Agent:  [calls request_approval]
        Approval request sent to dba-lead@contoso.com. I'll let you know 
        when they respond.

        ... [approver clicks Approve] ...

Agent:  ✅ Approved by dba-lead@contoso.com! Execute now?

You:    Yes, go ahead.

Agent:  [calls execute_migration]
        Migration complete! 7 tables, 215 rows. Run validation?

You:    Yes, full validation.

Agent:  [calls validate_and_report]
        ✅ All 28 checks passed. Your data is ready in Azure SQL!
```

### Flow 2: SQL Server Migration with Table Selection

```
You:    I want to migrate selected tables from SQL Server to Azure SQL.

Agent:  Sure! What are the source details?

You:    SQL Server at sqlprod01.internal.corp, database MigrationDemo, dbo schema.

Agent:  [discovers 25 tables in dbo schema]
        Found 25 tables. Which would you like to migrate?

You:    Just Customers, Orders, OrderDetails, and Products.

Agent:  [generates plan for 4 tables]
        Plan ready. NVARCHAR(MAX) columns detected in OrderDetails.Notes.
        Recommend NVARCHAR(MAX) → NVARCHAR(MAX) (1:1 mapping). Proceed?

You:    Yes, that's fine. Send to my manager (mgr@contoso.com) for approval.

Agent:  [sends approval] Done. Waiting for approval...
```

### Flow 3: Migration with Errors and Recovery

```
You:    Migrate Oracle SALES schema from 10.0.10.100/ORCL.

Agent:  [discovers schema — 15 tables found]

You:    Generate plan and send to approver approver@company.com.

Agent:  [generates plan, sends approval, gets approved]
        Approved. Execute?

You:    Execute now.

Agent:  Executing... 
        ✅ 13/15 tables completed.
        ❌ SALES_ARCHIVE — timeout (table has 50M rows)
        ❌ PRODUCT_IMAGES — BLOB column exceeds ADF batch size
        
        Would you like to retry with adjusted settings?

You:    Retry SALES_ARCHIVE with a larger timeout and smaller batch size.

Agent:  Retrying SALES_ARCHIVE with batch size 5000, timeout 2 hours...
        ✅ SALES_ARCHIVE — 50,000,000 rows copied (47 minutes)
        
        For PRODUCT_IMAGES, I recommend enabling staging in ADF. Retry?

You:    Yes, retry with staging.

Agent:  ✅ PRODUCT_IMAGES — 12,500 rows copied (3 minutes)
        All 15 tables migrated. Run validation?
```

### Flow 4: Asking Questions Mid-Flow

```
You:    Why did you map Oracle NUMBER(10,0) to BIGINT instead of INT?

Agent:  Good question! Oracle NUMBER(10,0) can hold values up to 10^10 
        (10 billion), which exceeds the INT range (max ~2.1 billion). 
        BIGINT supports up to ~9.2 × 10^18, which safely covers the range.
        
        If you're certain the values won't exceed 2,147,483,647, 
        I can change it to INT. Would you like me to adjust?

You:    No, BIGINT is fine. Continue.
```

---

## 13. Frequently Asked Questions

### General

**Q: Can I migrate multiple schemas in one job?**  
A: Currently, each migration job handles one schema at a time. Start a new conversation (or a new job within the same conversation) for additional schemas.

**Q: Can I migrate from Oracle and SQL Server in the same session?**  
A: Yes! Each migration gets its own Job ID. You can start a second migration after the first one completes.

**Q: Does the agent modify my source database?**  
A: No. The agent only performs `SELECT` operations on the source. No writes, deletes, or schema changes.

**Q: How long does a typical migration take?**  
A: It depends on data volume:
- Small (< 1 GB, < 50 tables): 5–15 minutes
- Medium (1–10 GB, 50–200 tables): 30–90 minutes  
- Large (10–100 GB, 200+ tables): 2–8 hours

**Q: Can I schedule a migration to run overnight?**  
A: Not currently. Migrations are triggered conversationally. For scheduled migrations, ask your admin about configuring ADF triggers directly.

### Data Types

**Q: Will I lose precision on Oracle NUMBER columns?**  
A: The agent maps `NUMBER(p,s)` to `DECIMAL(p,s)` in Azure SQL, preserving precision. `NUMBER` without precision (floating point) maps to `FLOAT(53)`.

**Q: What happens to Oracle CLOB columns?**  
A: `CLOB` maps to `NVARCHAR(MAX)` (up to 2 GB). Very large CLOBs may need staging enabled in ADF.

**Q: Are Oracle sequences migrated?**  
A: No. Sequences are not migrated. The agent focuses on tables and data. You'll need to create `IDENTITY` columns or sequences manually in Azure SQL.

### Security

**Q: Can I see what the agent is doing behind the scenes?**  
A: Yes. All actions are logged in the metadata database (`dbo.MigrationLog`). You can also check ADF pipeline runs and Logic App run history in the Azure Portal.

**Q: Who can approve migrations?**  
A: Anyone with an email address or Teams account that can receive the approval request. Access to the Azure environment is not required for the approver.

**Q: Is data encrypted during transfer?**  
A: Yes. ADF uses TLS encryption in transit. Azure SQL uses Transparent Data Encryption (TDE) at rest. VPN/ExpressRoute adds network-level encryption.

### Troubleshooting

**Q: The agent seems stuck — what do I do?**  
A: Try:
1. Ask "What is the current status?" to prompt a status check
2. Wait 2–3 minutes (some operations take time)
3. If still stuck, start a new conversation and reference your Job ID

**Q: Can I retry a failed migration?**  
A: Yes. Tell the agent: "Retry the migration for job [your-job-id]" or "Retry the failed tables."

---

## 14. Glossary

| Term | Definition |
|------|-----------|
| **Agent** | The AI-powered migration assistant (Azure AI Foundry Agent Service + GPT-4.1) |
| **ADF** | Azure Data Factory — the managed data movement service that copies data |
| **DDL** | Data Definition Language — SQL statements like `CREATE TABLE`, `ALTER TABLE` |
| **DML** | Data Manipulation Language — SQL statements like `INSERT`, `UPDATE`, `DELETE` |
| **Job ID** | A unique UUID assigned to each migration. Used to track all steps. |
| **Logic App** | Azure Logic Apps — workflow automation that orchestrates the migration steps |
| **Managed Identity** | Azure Entra ID identity assigned to a resource for passwordless authentication |
| **Key Vault** | Azure Key Vault — secure storage for secrets, keys, and certificates |
| **Schema** | The structure of a database: tables, columns, data types, constraints |
| **SHIR** | Self-Hosted Integration Runtime — a bridge between on-prem databases and Azure |
| **Validation** | Post-migration checks to verify data integrity (row counts, checksums, etc.) |
| **Migration Plan** | The AI-generated blueprint for migration: type mappings, DDL, strategy |
| **Approval Workflow** | The step where a designated person reviews and approves the migration plan |
| **Type Mapping** | The conversion of source data types (e.g., Oracle `NUMBER`) to target types (e.g., Azure SQL `DECIMAL`) |
| **PITR** | Point-in-Time Restore — Azure SQL backup that lets you restore to any second within the retention window |

---

> **Need help?** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed error resolution.  
> **Deploying?** See [DEPLOYMENT.md](DEPLOYMENT.md) for setup instructions.
