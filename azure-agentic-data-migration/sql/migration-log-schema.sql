/*******************************************************************************
 * migration-log-schema.sql
 *
 * DDL for Migration Tracking Tables — Azure SQL Database
 *
 * PURPOSE:
 *   Create the control / audit tables that the agentic migration system
 *   uses to record plans, approvals, executions, validations, and audit
 *   events.  All tables live in the [migration] schema.
 *
 * STATUS LIFECYCLE:
 *   DRAFT → ANALYZING → AWAITING_APPROVAL → APPROVED → DRY_RUN
 *        → READY_FOR_EXECUTION → RUNNING → COMPLETED | FAILED
 *        → VALIDATION_FAILED
 *   (CANCELLED can occur from any pre-RUNNING state)
 *
 * COMPATIBILITY: Azure SQL Database / SQL Server 2016+
 ******************************************************************************/

-- Create a dedicated schema to isolate migration-tracking objects
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'migration')
    EXEC('CREATE SCHEMA [migration];');
GO

-- ============================================================================
-- 1. migration_plans
-- ============================================================================
IF OBJECT_ID(N'migration.migration_plans', N'U') IS NULL
BEGIN
    CREATE TABLE [migration].[migration_plans]
    (
        [id]            UNIQUEIDENTIFIER NOT NULL
                        CONSTRAINT [DF_migration_plans_id] DEFAULT (NEWSEQUENTIALID()),
        [source_db]     NVARCHAR(256)    NOT NULL,
        [target_db]     NVARCHAR(256)    NOT NULL,
        [status]        NVARCHAR(30)     NOT NULL
                        CONSTRAINT [DF_migration_plans_status] DEFAULT (N'DRAFT'),
        [risk_level]    NVARCHAR(10)     NOT NULL
                        CONSTRAINT [DF_migration_plans_risk] DEFAULT (N'LOW'),
        [created_at]    DATETIME2(3)     NOT NULL
                        CONSTRAINT [DF_migration_plans_created] DEFAULT (SYSUTCDATETIME()),
        [updated_at]    DATETIME2(3)     NOT NULL
                        CONSTRAINT [DF_migration_plans_updated] DEFAULT (SYSUTCDATETIME()),
        [created_by]    NVARCHAR(128)    NOT NULL,
        [plan_json]     NVARCHAR(MAX)    NOT NULL
                        CONSTRAINT [CK_migration_plans_json] CHECK (ISJSON([plan_json]) = 1),

        CONSTRAINT [PK_migration_plans]
            PRIMARY KEY CLUSTERED ([id]),

        CONSTRAINT [CK_migration_plans_status] CHECK (
            [status] IN (
                N'DRAFT', N'ANALYZING', N'AWAITING_APPROVAL', N'APPROVED',
                N'DRY_RUN', N'READY_FOR_EXECUTION', N'RUNNING',
                N'COMPLETED', N'FAILED', N'CANCELLED', N'VALIDATION_FAILED'
            )
        ),
        CONSTRAINT [CK_migration_plans_risk] CHECK (
            [risk_level] IN (N'LOW', N'MEDIUM', N'HIGH', N'CRITICAL')
        )
    );
END
GO

-- Index for status-based queries
CREATE NONCLUSTERED INDEX [IX_migration_plans_status]
    ON [migration].[migration_plans] ([status])
    INCLUDE ([source_db], [target_db], [risk_level])
    WHERE [status] NOT IN (N'COMPLETED', N'CANCELLED');
GO


-- ============================================================================
-- 2. migration_approvals
-- ============================================================================
IF OBJECT_ID(N'migration.migration_approvals', N'U') IS NULL
BEGIN
    CREATE TABLE [migration].[migration_approvals]
    (
        [id]            UNIQUEIDENTIFIER NOT NULL
                        CONSTRAINT [DF_migration_approvals_id] DEFAULT (NEWSEQUENTIALID()),
        [plan_id]       UNIQUEIDENTIFIER NOT NULL,
        [approver]      NVARCHAR(256)    NOT NULL,
        [decision]      NVARCHAR(20)     NOT NULL,
        [reason]        NVARCHAR(2000)   NULL,
        [approved_at]   DATETIME2(3)     NOT NULL
                        CONSTRAINT [DF_migration_approvals_at] DEFAULT (SYSUTCDATETIME()),

        CONSTRAINT [PK_migration_approvals]
            PRIMARY KEY CLUSTERED ([id]),

        CONSTRAINT [FK_migration_approvals_plan]
            FOREIGN KEY ([plan_id])
            REFERENCES [migration].[migration_plans] ([id])
            ON DELETE CASCADE,

        CONSTRAINT [CK_migration_approvals_decision] CHECK (
            [decision] IN (N'APPROVED', N'REJECTED', N'NEEDS_CHANGES')
        )
    );
END
GO

CREATE NONCLUSTERED INDEX [IX_migration_approvals_plan]
    ON [migration].[migration_approvals] ([plan_id])
    INCLUDE ([decision], [approver]);
GO


-- ============================================================================
-- 3. migration_executions
-- ============================================================================
IF OBJECT_ID(N'migration.migration_executions', N'U') IS NULL
BEGIN
    CREATE TABLE [migration].[migration_executions]
    (
        [id]              UNIQUEIDENTIFIER NOT NULL
                          CONSTRAINT [DF_migration_executions_id] DEFAULT (NEWSEQUENTIALID()),
        [plan_id]         UNIQUEIDENTIFIER NOT NULL,
        [pipeline_run_id] NVARCHAR(256)    NULL,       -- ADF pipeline run ID
        [status]          NVARCHAR(30)     NOT NULL
                          CONSTRAINT [DF_migration_executions_status] DEFAULT (N'RUNNING'),
        [started_at]      DATETIME2(3)     NOT NULL
                          CONSTRAINT [DF_migration_executions_start] DEFAULT (SYSUTCDATETIME()),
        [completed_at]    DATETIME2(3)     NULL,
        [rows_copied]     BIGINT           NULL,
        [error_message]   NVARCHAR(MAX)    NULL,

        CONSTRAINT [PK_migration_executions]
            PRIMARY KEY CLUSTERED ([id]),

        CONSTRAINT [FK_migration_executions_plan]
            FOREIGN KEY ([plan_id])
            REFERENCES [migration].[migration_plans] ([id])
            ON DELETE CASCADE,

        CONSTRAINT [CK_migration_executions_status] CHECK (
            [status] IN (
                N'RUNNING', N'COMPLETED', N'FAILED', N'CANCELLED',
                N'DRY_RUN', N'VALIDATION_FAILED'
            )
        )
    );
END
GO

CREATE NONCLUSTERED INDEX [IX_migration_executions_plan]
    ON [migration].[migration_executions] ([plan_id])
    INCLUDE ([status], [started_at]);
GO

CREATE NONCLUSTERED INDEX [IX_migration_executions_status]
    ON [migration].[migration_executions] ([status])
    WHERE [status] IN (N'RUNNING', N'DRY_RUN');
GO


-- ============================================================================
-- 4. migration_validations
-- ============================================================================
IF OBJECT_ID(N'migration.migration_validations', N'U') IS NULL
BEGIN
    CREATE TABLE [migration].[migration_validations]
    (
        [id]             UNIQUEIDENTIFIER NOT NULL
                         CONSTRAINT [DF_migration_validations_id] DEFAULT (NEWSEQUENTIALID()),
        [execution_id]   UNIQUEIDENTIFIER NOT NULL,
        [table_name]     NVARCHAR(256)    NOT NULL,
        [check_type]     NVARCHAR(50)     NOT NULL,
        [source_value]   NVARCHAR(MAX)    NULL,
        [target_value]   NVARCHAR(MAX)    NULL,
        [passed]         BIT              NOT NULL,
        [details]        NVARCHAR(MAX)    NULL,

        CONSTRAINT [PK_migration_validations]
            PRIMARY KEY CLUSTERED ([id]),

        CONSTRAINT [FK_migration_validations_exec]
            FOREIGN KEY ([execution_id])
            REFERENCES [migration].[migration_executions] ([id])
            ON DELETE CASCADE,

        CONSTRAINT [CK_migration_validations_type] CHECK (
            [check_type] IN (
                N'ROW_COUNT', N'NULL_COUNT', N'DUPLICATE_CHECK',
                N'TRUNCATION_CHECK', N'OVERFLOW_CHECK', N'SCALE_LOSS_CHECK',
                N'MIN_MAX_AVG', N'STRING_LENGTH', N'CHECKSUM',
                N'REFERENTIAL_INTEGRITY', N'SCHEMA_COMPARE', N'CUSTOM'
            )
        )
    );
END
GO

CREATE NONCLUSTERED INDEX [IX_migration_validations_exec]
    ON [migration].[migration_validations] ([execution_id])
    INCLUDE ([table_name], [check_type], [passed]);
GO

CREATE NONCLUSTERED INDEX [IX_migration_validations_failed]
    ON [migration].[migration_validations] ([passed])
    WHERE [passed] = 0;
GO


-- ============================================================================
-- 5. migration_audit_log
-- ============================================================================
IF OBJECT_ID(N'migration.migration_audit_log', N'U') IS NULL
BEGIN
    CREATE TABLE [migration].[migration_audit_log]
    (
        [id]          BIGINT IDENTITY(1,1) NOT NULL,
        [plan_id]     UNIQUEIDENTIFIER     NULL,       -- NULL for system events
        [action]      NVARCHAR(100)        NOT NULL,
        [actor]       NVARCHAR(256)        NOT NULL,
        [timestamp]   DATETIME2(3)         NOT NULL
                      CONSTRAINT [DF_migration_audit_ts] DEFAULT (SYSUTCDATETIME()),
        [details]     NVARCHAR(MAX)        NULL,

        CONSTRAINT [PK_migration_audit_log]
            PRIMARY KEY CLUSTERED ([id]),

        CONSTRAINT [FK_migration_audit_plan]
            FOREIGN KEY ([plan_id])
            REFERENCES [migration].[migration_plans] ([id])
            ON DELETE SET NULL
    );
END
GO

CREATE NONCLUSTERED INDEX [IX_migration_audit_plan]
    ON [migration].[migration_audit_log] ([plan_id])
    INCLUDE ([action], [actor], [timestamp]);
GO

CREATE NONCLUSTERED INDEX [IX_migration_audit_timestamp]
    ON [migration].[migration_audit_log] ([timestamp] DESC)
    INCLUDE ([plan_id], [action], [actor]);
GO


-- ============================================================================
-- HELPER: Stored Procedure to Record an Audit Entry
-- ============================================================================
CREATE OR ALTER PROCEDURE [migration].[usp_RecordAuditEntry]
    @PlanId   UNIQUEIDENTIFIER,
    @Action   NVARCHAR(100),
    @Actor    NVARCHAR(256),
    @Details  NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO [migration].[migration_audit_log]
        ([plan_id], [action], [actor], [details])
    VALUES
        (@PlanId, @Action, @Actor, @Details);
END
GO


-- ============================================================================
-- HELPER: Stored Procedure to Transition Plan Status
-- ============================================================================
CREATE OR ALTER PROCEDURE [migration].[usp_TransitionPlanStatus]
    @PlanId    UNIQUEIDENTIFIER,
    @NewStatus NVARCHAR(30),
    @Actor     NVARCHAR(256)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @OldStatus NVARCHAR(30);

    SELECT @OldStatus = [status]
    FROM [migration].[migration_plans]
    WHERE [id] = @PlanId;

    IF @OldStatus IS NULL
    BEGIN
        RAISERROR('Plan %s not found.', 16, 1, @PlanId);
        RETURN;
    END

    -- Guard: prevent invalid transitions
    IF @NewStatus = N'CANCELLED'
       AND @OldStatus IN (N'RUNNING', N'COMPLETED', N'FAILED', N'VALIDATION_FAILED')
    BEGIN
        RAISERROR('Cannot cancel a plan in status %s.', 16, 1, @OldStatus);
        RETURN;
    END

    UPDATE [migration].[migration_plans]
    SET [status]     = @NewStatus,
        [updated_at] = SYSUTCDATETIME()
    WHERE [id] = @PlanId;

    EXEC [migration].[usp_RecordAuditEntry]
        @PlanId  = @PlanId,
        @Action  = N'STATUS_TRANSITION',
        @Actor   = @Actor,
        @Details = @OldStatus;      -- record the previous status
END
GO


-- ============================================================================
-- SEED: Insert a sample audit entry so we can verify deployment
-- ============================================================================
INSERT INTO [migration].[migration_audit_log]
    ([plan_id], [action], [actor], [details])
VALUES
    (NULL, N'SCHEMA_DEPLOYED', SUSER_SNAME(), N'Migration tracking schema created successfully.');
GO

PRINT '=== migration-log-schema.sql deployed successfully ===';
GO
