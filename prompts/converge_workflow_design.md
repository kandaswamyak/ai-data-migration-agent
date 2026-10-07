# Converge Workflow Design — Oracle → Azure SQL Migration (with HITL approval gates)

## Why the current single-agent workflow can't pause

The failing run asked "Do you approve these mappings?" then continued on its own.
Root cause: a **single agent node** running the whole pipeline has no mechanism to
block on human input. A system prompt that says "STOP and WAIT" is only a request —
the model can (and did) ignore it and self-continue. **A pause must be a workflow
structure, not a prompt instruction.**

The fix: split the one agent into THREE agent nodes, with a real **human-approval
node** between them. The approval node is what renders Approve/Reject and blocks the
run until a human clicks — the agent never controls that transition, so it cannot
self-approve.

## Target workflow structure

```
┌─────────────────────────────────────────────┐
│ Agent Node A — ANALYZE                        │
│   Steps 1–3:                                  │
│     extract_oracle_schema                     │
│     map_data_types                            │
│     detect_schema_drift                       │
│   Ends by presenting the mapping summary.     │
└───────────────────┬───────────────────────────┘
                    ▼
┌─────────────────────────────────────────────┐
│ HUMAN APPROVAL NODE #1  — "Approve mappings?" │
│   Renders Approve / Reject (+ comments).      │
│   BLOCKS the workflow until a human clicks.   │
│   Reject → route back to Node A (or end).     │
└───────────────────┬───────────────────────────┘
                    ▼ (only on Approve)
┌─────────────────────────────────────────────┐
│ Agent Node B — GENERATE DDL                   │
│   Step 5: generate_migration_script           │
│   Presents CREATE/ALTER/NO_CHANGE actions.    │
└───────────────────┬───────────────────────────┘
                    ▼
┌─────────────────────────────────────────────┐
│ HUMAN APPROVAL NODE #2  — "Approve scripts?"  │
│   Renders Approve / Reject (+ comments).      │
│   BLOCKS until a human clicks.                │
│   Reject → route back to Node B (or end).     │
└───────────────────┬───────────────────────────┘
                    ▼ (only on Approve)
┌─────────────────────────────────────────────┐
│ Agent Node C — EXECUTE                        │
│   Step 7: execute_data_migration              │
│           {"migration_mode":"incremental"}    │
│   Step 8: validate_data_integrity             │
│   Step 9: generate_migration_report           │
└─────────────────────────────────────────────┘
```

## Node-by-node prompts (each node gets ONLY its slice)

Keep the shared header from `converge_agent_system_prompt.md` (the "NOT in simulator
mode / halt-on-error" block) in EVERY agent node, then give each node only its steps:

**Agent Node A (ANALYZE):**
> Call these tools in order, each with no arguments: `extract_oracle_schema`,
> `map_data_types`, `detect_schema_drift`. Report each tool's returned JSON. After
> `detect_schema_drift`, present a concise mapping + drift summary and STOP. Do not
> attempt any approval or further tools — the workflow handles approval next.

**Human Approval Node #1:**
> Prompt/label: "Do you approve these mappings to proceed to DDL generation?"
> Buttons: Approve → Node B; Reject → back to Node A (or terminate).

**Agent Node B (DDL):**
> Call `generate_migration_script` with no arguments. Report the CREATE/ALTER/NO_CHANGE
> actions for tables and code objects. STOP.

**Human Approval Node #2:**
> Prompt/label: "Do you approve these scripts to execute the migration?"
> Buttons: Approve → Node C; Reject → back to Node B (or terminate).

**Agent Node C (EXECUTE):**
> Call in order: `execute_data_migration` with {"migration_mode":"incremental"},
> then `validate_data_integrity` (no args), then `generate_migration_report` (no args).
> Report each tool's output. Include "Code objects deployed: N views, M procedures".

## How to build it in Converge (generic steps)

1. Open the `oracle-azure-sql-migration` workflow in the Converge builder.
2. Replace the single agent node with **Agent Node A** (paste the shared header +
   Node A steps). Point it at the same MCP tool connection.
3. Add a **Human Approval / Human-in-the-loop node** after A. Set its question to
   "Do you approve these mappings?" Configure Approve → next, Reject → back to A.
   (Look for a node type named "Human Approval", "Human Input", "Wait for Approval",
   or "Manual Gate" — this is the element that renders Approve/Reject and blocks.)
4. Add **Agent Node B**, then a second **Human Approval node**, then **Agent Node C**,
   wiring Approve paths forward and Reject paths back as shown.
5. Ensure ALL three agent nodes use the SAME MCP tool connection and the anti-simulation
   header, so state carries across nodes (the server holds pipeline state between calls).

## If Converge has NO human-approval node type

Then true blocking isn't available in the workflow engine, and the reliable fallback is
to run the pipeline in **two or three separate workflow invocations** triggered by a
human:
- Invocation 1: run Node A (analyze). Human reviews the output.
- Human manually starts Invocation 2: run Node B (DDL). Human reviews.
- Human manually starts Invocation 3: run Node C (execute/validate/report).
This makes the human the transition between phases — the only guaranteed gate when the
engine can't block.

## What is NOT the fix (avoid)
- A `/api/approve` route + HTML widget in the Flask app: the agent runs inside Converge,
  not in the Flask page, so Converge never renders that widget. It would sit unused.
- Stronger "STOP and WAIT" prompt wording alone: cannot enforce a pause; the model
  ignored it in testing.
