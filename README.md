# AI Data Migration Agent

An intelligent, end-to-end database migration solution that automates the complete migration lifecycle from **Oracle → Azure SQL**. Built by DXC Technology, it leverages AI (Azure OpenAI GPT-4o-mini) orchestrated through a **LangGraph** workflow to eliminate manual effort, reduce human error, and accelerate migration timelines.

> © 2026 DXC Technology Company. All rights reserved. — DXC Internal

---

## 🚀 Overview

The AI Data Migration Agent automates database migration discovery, analysis, mapping, execution, validation, and reporting. It combines a **multi-agent AI framework** with **human-in-the-loop** approval gates to deliver fast, governed, and low-risk migrations.

**Key capabilities:**
- End-to-end migration: Oracle → Azure SQL
- AI-powered datatype analysis with confidence scores
- Automated DDL/DML generation for Azure SQL
- Human-in-the-loop approval gates
- 9-phase LangGraph orchestration
- Real-time Flask dashboard
- AI-generated executive reports (PDF)
- Full audit trail, lineage, and drift detection

---

## 🧩 Features

| Phase | Feature | Description |
|:--|:--|:--|
| 1 | **Connect** | Connect to Oracle source and Azure SQL target |
| 2 | **Discover** | Discover schemas, tables, columns, and relationships |
| 3 | **Analyze** | Analyze datatypes and compatibility with confidence scores |
| 4 | **Map** | AI generates source→target mappings |
| 5 | **Approve** | Human reviews and approves mappings (human-in-the-loop) |
| 6 | **Generate** | Generate DDL/DML migration scripts |
| 7 | **Migrate** | Execute migration (full / incremental) |
| 8 | **Validate** | Validate data integrity and quality (12 checks) |
| 9 | **Report** | Generate migration report and executive summary (PDF) |

---

## 🏗️ Architecture

A multi-agent AI framework orchestrated by LangGraph:

- **AI Engine (GPT-4o-mini):** Multi-agent layer
  - Schema Agent → Datatype Agent → Mapping Agent → SQL Generator Agent → Validation Agent
- **Migration Studio (Control Plane):** Connection Manager, Metadata Store, Approval Center, Execution Manager, Monitoring & Alerts, Reporting
- **Data & Integration Layer:** Secure Connectivity (VPN, Private Link, TLS), Data Extractors, Data Loaders, Audit & Lineage, File Storage
- **Cross-Cutting Concerns:** Security (RBAC, Vault, Secrets), Observability, Resilience, Scalability, Governance, Cost Optimization

```
Oracle Source  →  AI Engine (GPT-4o-mini + LangGraph)  →  Migration Studio  →  Azure SQL Target
```

---

## ✅ Data Validation (Phase 8)

The agent runs **12 automated validation checks**:

1. Row Count
2. PK Null (source + target)
3. PK Duplicate (source + target)
4. NULL Count per Column
5. Column Count
6. Distinct Values
7. MIN / MAX
8. SUM (numeric columns)
9. String Length MAX
10. Checksum
11. Rejected Rows
12. Per-Table Status (composite)

Validation results are cached to `reports/reconciliation_validation_latest.json`.

---

## 🧰 Technology Stack

| Layer | Technologies |
|:--|:--|
| **AI / Orchestration** | Azure OpenAI (GPT-4o-mini), LangGraph, LangChain |
| **Language** | Python |
| **UI / Dashboard** | Flask, Streamlit |
| **Database Connectivity** | pyodbc (Azure SQL), oracledb (Oracle), SQLAlchemy |
| **Data Processing** | pandas |
| **Reporting** | ReportLab (PDF) |
| **Access / Tunneling** | Azure devtunnel |
| **Config** | python-dotenv |

---

## 📦 Installation

### Prerequisites
- Python 3.10+
- Oracle client access (source database)
- Azure SQL target database
- Azure OpenAI API key (GPT-4o-mini deployment)

### Setup

```bash
# 1. Clone / open the project
cd ai-data-migration-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables (.env)
#    - Azure OpenAI API key & endpoint
#    - Oracle connection details
#    - Azure SQL connection details
```

> See `ORACLE_SETUP.md` and `ORACLE_CONFIGURATION.md` for Oracle connection setup.

---

## ▶️ Usage

### Run the Flask dashboard
```bash
python main.py
```

### Or run the Streamlit dashboard
```bash
streamlit run dashboard/app.py
```

Then open the dashboard in your browser and step through the 9-phase migration workflow: **Connect → Discover → Analyze → Map → Approve → Generate → Migrate → Validate → Report.**

---

## 📁 Project Structure

```
ai-data-migration-agent/
├── agents/              # Multi-agent AI framework (schema, datatype, mapping, SQL, validation)
├── connectors/          # Oracle, SQL Server & Azure SQL connectors
├── workflows/           # LangGraph orchestration (9-phase workflow)
├── dashboard/           # Streamlit dashboard
├── config/              # Configuration
├── prompts/             # LLM prompts
├── data/                # Working data
├── reports/             # Generated reports & validation artifacts
├── main.py              # Flask app entry point
├── requirements.txt     # Python dependencies
├── ORACLE_SETUP.md      # Oracle setup guide
└── ORACLE_CONFIGURATION.md
```

---

## 🔒 Security & Governance

- RBAC, Vault, and secrets management
- Secure connectivity (VPN, Private Link, TLS encryption)
- Full audit trail and data lineage tracking
- Real-time drift detection
- Compliance and governance policies

---

## 📄 License

© 2026 DXC Technology Company. All rights reserved. — DXC Internal
