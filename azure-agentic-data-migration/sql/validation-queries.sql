/*******************************************************************************
 * validation-queries.sql
 *
 * Post-Migration Validation Queries
 *
 * PURPOSE:
 *   A library of parameterised T-SQL queries the migration agent uses to
 *   compare source and target data after a migration execution.  Each query
 *   returns a structured result the agent records in migration_validations.
 *
 * PARAMETERS (replace before execution):
 *   @SourceTable  — fully-qualified source table   e.g. [HR].[EMPLOYEES]
 *   @TargetTable  — fully-qualified target table   e.g. [dbo].[EMPLOYEES]
 *   @ColumnName   — column under inspection
 *   @SchemaName   — target schema (default 'dbo')
 *
 * COMPATIBILITY: Azure SQL Database / SQL Server 2016+
 ******************************************************************************/


-- ============================================================================
-- 1. ROW COUNT COMPARISON (source vs target)
-- ============================================================================
/*
   Run once on source, once on target; the agent compares the two counts.
   The linked-server variant below works when both are accessible from the
   same session; otherwise execute individually and compare in the agent.
*/

-- Target row count
DECLARE @TargetTable NVARCHAR(256) = N'[dbo].[EMPLOYEES]';

DECLARE @sql NVARCHAR(MAX) = N'SELECT COUNT_BIG(*) AS [RowCount] FROM ' + @TargetTable;
EXEC sp_executesql @sql;
GO

-- Side-by-side via linked server (optional — requires linked server setup)
/*
DECLARE @SourceTable NVARCHAR(256) = N'[ORACLE_LINK].[HR].[EMPLOYEES]';
DECLARE @TargetTable NVARCHAR(256) = N'[dbo].[EMPLOYEES]';

DECLARE @sql NVARCHAR(MAX) = N'
SELECT
    ''SOURCE'' AS [Side], COUNT_BIG(*) AS [RowCount] FROM ' + @SourceTable + '
UNION ALL
SELECT
    ''TARGET'' AS [Side], COUNT_BIG(*) AS [RowCount] FROM ' + @TargetTable + ';';
EXEC sp_executesql @sql;
*/
GO


-- ============================================================================
-- 2. NULL COUNT PER COLUMN
-- ============================================================================
DECLARE @SchemaName  NVARCHAR(128) = N'dbo';
DECLARE @TableName   NVARCHAR(128) = N'EMPLOYEES';

DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql = @sql +
    'SELECT ' +
    '''' + c.COLUMN_NAME + ''' AS [ColumnName], ' +
    'SUM(CASE WHEN ' + QUOTENAME(c.COLUMN_NAME) + ' IS NULL THEN 1 ELSE 0 END) AS [NullCount], ' +
    'COUNT_BIG(*) AS [TotalRows] ' +
    'FROM ' + QUOTENAME(@SchemaName) + '.' + QUOTENAME(@TableName) +
    ' UNION ALL '
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_SCHEMA = @SchemaName
  AND c.TABLE_NAME   = @TableName
ORDER BY c.ORDINAL_POSITION;

-- Remove trailing UNION ALL
SET @sql = LEFT(@sql, LEN(@sql) - 10);

IF LEN(@sql) > 0
    EXEC sp_executesql @sql;
GO


-- ============================================================================
-- 3. DUPLICATE DETECTION (based on primary key or unique columns)
-- ============================================================================
/*
   Replace @KeyColumns with the comma-separated PK/unique columns.
*/
DECLARE @SchemaName NVARCHAR(128) = N'dbo';
DECLARE @TableName  NVARCHAR(128) = N'EMPLOYEES';
DECLARE @KeyColumns NVARCHAR(512) = N'EMPLOYEE_ID';  -- comma-separated

DECLARE @sql NVARCHAR(MAX) = N'
SELECT ' + @KeyColumns + ', COUNT(*) AS [DuplicateCount]
FROM '  + QUOTENAME(@SchemaName) + '.' + QUOTENAME(@TableName) + '
GROUP BY ' + @KeyColumns + '
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC;';

EXEC sp_executesql @sql;
GO


-- ============================================================================
-- 4. DATA-TYPE CONVERSION VERIFICATION — Truncation & Overflow Checks
-- ============================================================================
/*
   4a. String truncation: find rows where the actual length in the source
       exceeds the target column's CHARACTER_MAXIMUM_LENGTH.
*/
DECLARE @SchemaName  NVARCHAR(128) = N'dbo';
DECLARE @TableName   NVARCHAR(128) = N'EMPLOYEES';
DECLARE @ColumnName  NVARCHAR(128) = N'FIRST_NAME';

-- Get the max length defined in the target
DECLARE @MaxLen INT;
SELECT @MaxLen = CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = @SchemaName
  AND TABLE_NAME   = @TableName
  AND COLUMN_NAME  = @ColumnName;

-- Find values that would be truncated
DECLARE @sql NVARCHAR(MAX) = N'
SELECT
    ''' + @ColumnName + '''     AS [ColumnName],
    '   + CAST(@MaxLen AS NVARCHAR(10)) + ' AS [TargetMaxLength],
    MAX(LEN(' + QUOTENAME(@ColumnName) + ')) AS [ActualMaxLength],
    SUM(CASE WHEN LEN(' + QUOTENAME(@ColumnName) + ') > ' + CAST(@MaxLen AS NVARCHAR(10)) + ' THEN 1 ELSE 0 END) AS [TruncatedRows]
FROM ' + QUOTENAME(@SchemaName) + '.' + QUOTENAME(@TableName) + ';';

EXEC sp_executesql @sql;
GO

/*
   4b. Numeric overflow: find rows where values exceed the target precision.
       Example: source NUMBER(18,4) → target DECIMAL(10,2).
*/
DECLARE @SchemaName  NVARCHAR(128) = N'dbo';
DECLARE @TableName   NVARCHAR(128) = N'EMPLOYEES';
DECLARE @ColumnName  NVARCHAR(128) = N'SALARY';
DECLARE @TargetPrecision INT = 10;
DECLARE @TargetScale     INT = 2;

DECLARE @MaxIntegerDigits INT = @TargetPrecision - @TargetScale;
DECLARE @MaxAbsValue NVARCHAR(50) = REPLICATE('9', @MaxIntegerDigits)
    + '.' + REPLICATE('9', @TargetScale);

DECLARE @sql NVARCHAR(MAX) = N'
SELECT
    ''' + @ColumnName + '''            AS [ColumnName],
    ' + CAST(@TargetPrecision AS NVARCHAR(5)) + ' AS [TargetPrecision],
    ' + CAST(@TargetScale     AS NVARCHAR(5)) + ' AS [TargetScale],
    SUM(CASE WHEN ABS(' + QUOTENAME(@ColumnName) + ') > ' + @MaxAbsValue + ' THEN 1 ELSE 0 END) AS [OverflowRows],
    SUM(CASE WHEN ' + QUOTENAME(@ColumnName) + ' <> ROUND(' + QUOTENAME(@ColumnName) + ', ' + CAST(@TargetScale AS NVARCHAR(5)) + ') THEN 1 ELSE 0 END) AS [ScaleLossRows]
FROM ' + QUOTENAME(@SchemaName) + '.' + QUOTENAME(@TableName) + '
WHERE ' + QUOTENAME(@ColumnName) + ' IS NOT NULL;';

EXEC sp_executesql @sql;
GO


-- ============================================================================
-- 5. MIN / MAX / AVG FOR NUMERIC COLUMNS
-- ============================================================================
DECLARE @SchemaName  NVARCHAR(128) = N'dbo';
DECLARE @TableName   NVARCHAR(128) = N'EMPLOYEES';

DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql = @sql +
    'SELECT ' +
    '''' + c.COLUMN_NAME + ''' AS [ColumnName], ' +
    'MIN(' + QUOTENAME(c.COLUMN_NAME) + ') AS [MinValue], ' +
    'MAX(' + QUOTENAME(c.COLUMN_NAME) + ') AS [MaxValue], ' +
    'AVG(CAST(' + QUOTENAME(c.COLUMN_NAME) + ' AS FLOAT)) AS [AvgValue] ' +
    'FROM ' + QUOTENAME(@SchemaName) + '.' + QUOTENAME(@TableName) +
    ' UNION ALL '
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_SCHEMA = @SchemaName
  AND c.TABLE_NAME   = @TableName
  AND c.DATA_TYPE IN (
      'int','bigint','smallint','tinyint',
      'decimal','numeric','float','real',
      'money','smallmoney'
  )
ORDER BY c.ORDINAL_POSITION;

-- Remove trailing UNION ALL
SET @sql = LEFT(@sql, LEN(@sql) - 10);

IF LEN(@sql) > 0
    EXEC sp_executesql @sql;
GO


-- ============================================================================
-- 6. LENGTH CHECK FOR STRING (CHAR/VARCHAR/NCHAR/NVARCHAR) COLUMNS
-- ============================================================================
DECLARE @SchemaName  NVARCHAR(128) = N'dbo';
DECLARE @TableName   NVARCHAR(128) = N'EMPLOYEES';

DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql = @sql +
    'SELECT ' +
    '''' + c.COLUMN_NAME + ''' AS [ColumnName], ' +
    CAST(ISNULL(c.CHARACTER_MAXIMUM_LENGTH, -1) AS NVARCHAR(10)) + ' AS [DefinedMaxLength], ' +
    'MIN(LEN(' + QUOTENAME(c.COLUMN_NAME) + ')) AS [ActualMinLength], ' +
    'MAX(LEN(' + QUOTENAME(c.COLUMN_NAME) + ')) AS [ActualMaxLength], ' +
    'AVG(CAST(LEN(' + QUOTENAME(c.COLUMN_NAME) + ') AS FLOAT)) AS [AvgLength] ' +
    'FROM ' + QUOTENAME(@SchemaName) + '.' + QUOTENAME(@TableName) +
    ' UNION ALL '
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_SCHEMA = @SchemaName
  AND c.TABLE_NAME   = @TableName
  AND c.DATA_TYPE IN ('char','varchar','nchar','nvarchar')
ORDER BY c.ORDINAL_POSITION;

SET @sql = LEFT(@sql, LEN(@sql) - 10);

IF LEN(@sql) > 0
    EXEC sp_executesql @sql;
GO


-- ============================================================================
-- 7. CHECKSUM COMPARISON (lightweight hash-based row integrity)
-- ============================================================================
/*
   Compute a table-level aggregate hash and compare across source & target.
   Use HASHBYTES for more reliability; CHECKSUM_AGG for speed.
*/
DECLARE @SchemaName NVARCHAR(128) = N'dbo';
DECLARE @TableName  NVARCHAR(128) = N'EMPLOYEES';

DECLARE @sql NVARCHAR(MAX) = N'
SELECT
    ''' + @TableName + ''' AS [TableName],
    CHECKSUM_AGG(CHECKSUM(*)) AS [TableChecksum]
FROM ' + QUOTENAME(@SchemaName) + '.' + QUOTENAME(@TableName) + ';';

EXEC sp_executesql @sql;
GO


-- ============================================================================
-- 8. REFERENTIAL INTEGRITY — orphaned foreign-key rows in target
-- ============================================================================
DECLARE @SchemaName NVARCHAR(128) = N'dbo';

SELECT
    fk.name                     AS [ForeignKey],
    OBJECT_NAME(fk.parent_object_id)     AS [ChildTable],
    cp.name                     AS [ChildColumn],
    OBJECT_NAME(fk.referenced_object_id) AS [ParentTable],
    cr.name                     AS [ParentColumn]
INTO #FKList
FROM sys.foreign_keys AS fk
INNER JOIN sys.foreign_key_columns AS fkc
    ON fkc.constraint_object_id = fk.object_id
INNER JOIN sys.columns AS cp
    ON cp.object_id = fkc.parent_object_id AND cp.column_id = fkc.parent_column_id
INNER JOIN sys.columns AS cr
    ON cr.object_id = fkc.referenced_object_id AND cr.column_id = fkc.referenced_column_id
WHERE SCHEMA_NAME(fk.schema_id) = @SchemaName;

-- For each FK, find orphaned rows
DECLARE @fkSql NVARCHAR(MAX) = N'';

SELECT @fkSql = @fkSql +
    'SELECT ''' + ForeignKey + ''' AS [ForeignKey], COUNT(*) AS [OrphanCount] ' +
    'FROM ' + QUOTENAME(@SchemaName) + '.' + QUOTENAME(ChildTable) + ' AS c ' +
    'LEFT JOIN ' + QUOTENAME(@SchemaName) + '.' + QUOTENAME(ParentTable) + ' AS p ' +
    '  ON c.' + QUOTENAME(ChildColumn) + ' = p.' + QUOTENAME(ParentColumn) + ' ' +
    'WHERE p.' + QUOTENAME(ParentColumn) + ' IS NULL ' +
    '  AND c.' + QUOTENAME(ChildColumn) + ' IS NOT NULL ' +
    'UNION ALL '
FROM #FKList;

IF LEN(@fkSql) > 10
BEGIN
    SET @fkSql = LEFT(@fkSql, LEN(@fkSql) - 10);
    EXEC sp_executesql @fkSql;
END

DROP TABLE IF EXISTS #FKList;
GO
