/*******************************************************************************
 * target-metadata.sql
 * 
 * Azure SQL Database — Target Metadata Discovery Queries
 * 
 * PURPOSE:
 *   Read structural metadata from the Azure SQL Database target so the
 *   migration agent can compare source and target schemas, identify gaps,
 *   and generate DDL/mapping recommendations.
 *
 * USAGE:
 *   Replace @SchemaName with the target schema (default 'dbo').
 *   Each query is self-contained and can be executed independently.
 *
 * COMPATIBILITY: Azure SQL Database / SQL Server 2016+
 ******************************************************************************/

-- ============================================================================
-- 1. LIST ALL USER TABLES IN THE TARGET SCHEMA
-- ============================================================================
DECLARE @SchemaName NVARCHAR(128) = N'dbo';   -- << parameterise

SELECT
    t.TABLE_CATALOG       AS [DatabaseName],
    t.TABLE_SCHEMA        AS [SchemaName],
    t.TABLE_NAME          AS [TableName],
    t.TABLE_TYPE          AS [TableType],
    p.[RowCount]          AS [ApproxRowCount],
    CAST(
        (SUM(a.total_pages) * 8.0) / 1024 AS DECIMAL(18,2)
    )                     AS [TotalSizeMB]
FROM INFORMATION_SCHEMA.TABLES AS t
INNER JOIN sys.tables AS st
    ON  st.name       = t.TABLE_NAME
    AND SCHEMA_NAME(st.schema_id) = t.TABLE_SCHEMA
INNER JOIN sys.indexes AS i
    ON  i.object_id = st.object_id
    AND i.index_id  <= 1                      -- heap or clustered
INNER JOIN sys.partitions AS p
    ON  p.object_id  = i.object_id
    AND p.index_id   = i.index_id
INNER JOIN sys.allocation_units AS a
    ON  a.container_id = p.partition_id
WHERE t.TABLE_SCHEMA = @SchemaName
  AND t.TABLE_TYPE   = 'BASE TABLE'
GROUP BY
    t.TABLE_CATALOG,
    t.TABLE_SCHEMA,
    t.TABLE_NAME,
    t.TABLE_TYPE,
    p.[rows]
ORDER BY t.TABLE_NAME;
GO


-- ============================================================================
-- 2. LIST ALL COLUMNS WITH DATA-TYPE DETAILS
-- ============================================================================
DECLARE @SchemaName NVARCHAR(128) = N'dbo';

SELECT
    c.TABLE_SCHEMA                          AS [SchemaName],
    c.TABLE_NAME                            AS [TableName],
    c.ORDINAL_POSITION                      AS [OrdinalPosition],
    c.COLUMN_NAME                           AS [ColumnName],
    c.DATA_TYPE                             AS [DataType],
    c.CHARACTER_MAXIMUM_LENGTH              AS [MaxLength],
    c.NUMERIC_PRECISION                     AS [NumericPrecision],
    c.NUMERIC_SCALE                         AS [NumericScale],
    c.DATETIME_PRECISION                    AS [DateTimePrecision],
    c.IS_NULLABLE                           AS [IsNullable],
    c.COLUMN_DEFAULT                        AS [DefaultValue],
    COLUMNPROPERTY(
        OBJECT_ID(QUOTENAME(c.TABLE_SCHEMA) + '.' + QUOTENAME(c.TABLE_NAME)),
        c.COLUMN_NAME,
        'IsIdentity'
    )                                       AS [IsIdentity],
    COLUMNPROPERTY(
        OBJECT_ID(QUOTENAME(c.TABLE_SCHEMA) + '.' + QUOTENAME(c.TABLE_NAME)),
        c.COLUMN_NAME,
        'IsComputed'
    )                                       AS [IsComputed]
FROM INFORMATION_SCHEMA.COLUMNS AS c
INNER JOIN INFORMATION_SCHEMA.TABLES AS t
    ON  t.TABLE_SCHEMA = c.TABLE_SCHEMA
    AND t.TABLE_NAME   = c.TABLE_NAME
    AND t.TABLE_TYPE   = 'BASE TABLE'
WHERE c.TABLE_SCHEMA = @SchemaName
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
GO


-- ============================================================================
-- 3. LIST ALL TABLE CONSTRAINTS (PK, UNIQUE, FOREIGN KEY, CHECK)
-- ============================================================================
DECLARE @SchemaName NVARCHAR(128) = N'dbo';

SELECT
    tc.TABLE_SCHEMA       AS [SchemaName],
    tc.TABLE_NAME         AS [TableName],
    tc.CONSTRAINT_NAME    AS [ConstraintName],
    tc.CONSTRAINT_TYPE    AS [ConstraintType],
    STRING_AGG(kcu.COLUMN_NAME, ', ')
        WITHIN GROUP (ORDER BY kcu.ORDINAL_POSITION)
                          AS [Columns]
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
    ON  kcu.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
    AND kcu.CONSTRAINT_NAME   = tc.CONSTRAINT_NAME
    AND kcu.TABLE_NAME        = tc.TABLE_NAME
WHERE tc.TABLE_SCHEMA = @SchemaName
GROUP BY
    tc.TABLE_SCHEMA,
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_TYPE;
GO


-- ============================================================================
-- 4. FOREIGN KEY DETAILS (referencing → referenced)
-- ============================================================================
DECLARE @SchemaName NVARCHAR(128) = N'dbo';

SELECT
    fk.name                                      AS [ForeignKeyName],
    SCHEMA_NAME(tp.schema_id)                    AS [ParentSchema],
    tp.name                                      AS [ParentTable],
    STRING_AGG(cp.name, ', ')
        WITHIN GROUP (ORDER BY fkc.constraint_column_id)
                                                 AS [ParentColumns],
    SCHEMA_NAME(tr.schema_id)                    AS [ReferencedSchema],
    tr.name                                      AS [ReferencedTable],
    STRING_AGG(cr.name, ', ')
        WITHIN GROUP (ORDER BY fkc.constraint_column_id)
                                                 AS [ReferencedColumns],
    fk.delete_referential_action_desc            AS [OnDelete],
    fk.update_referential_action_desc            AS [OnUpdate]
FROM sys.foreign_keys AS fk
INNER JOIN sys.foreign_key_columns AS fkc
    ON  fkc.constraint_object_id = fk.object_id
INNER JOIN sys.tables AS tp
    ON  tp.object_id = fk.parent_object_id
INNER JOIN sys.columns AS cp
    ON  cp.object_id  = fkc.parent_object_id
    AND cp.column_id  = fkc.parent_column_id
INNER JOIN sys.tables AS tr
    ON  tr.object_id = fk.referenced_object_id
INNER JOIN sys.columns AS cr
    ON  cr.object_id  = fkc.referenced_object_id
    AND cr.column_id  = fkc.referenced_column_id
WHERE SCHEMA_NAME(tp.schema_id) = @SchemaName
GROUP BY
    fk.name,
    tp.schema_id, tp.name,
    tr.schema_id, tr.name,
    fk.delete_referential_action_desc,
    fk.update_referential_action_desc
ORDER BY tp.name, fk.name;
GO


-- ============================================================================
-- 5. LIST ALL INDEXES (clustered, non-clustered, unique, filtered)
-- ============================================================================
DECLARE @SchemaName NVARCHAR(128) = N'dbo';

SELECT
    SCHEMA_NAME(t.schema_id)                     AS [SchemaName],
    t.name                                       AS [TableName],
    i.name                                       AS [IndexName],
    i.type_desc                                  AS [IndexType],
    i.is_unique                                  AS [IsUnique],
    i.is_primary_key                             AS [IsPrimaryKey],
    i.is_unique_constraint                       AS [IsUniqueConstraint],
    i.has_filter                                 AS [HasFilter],
    i.filter_definition                          AS [FilterDefinition],
    STRING_AGG(
        c.name + CASE WHEN ic.is_descending_key = 1 THEN ' DESC' ELSE ' ASC' END,
        ', '
    ) WITHIN GROUP (ORDER BY ic.key_ordinal)     AS [KeyColumns],
    STRING_AGG(
        CASE WHEN ic.is_included_column = 1 THEN c.name END,
        ', '
    ) WITHIN GROUP (ORDER BY ic.key_ordinal)     AS [IncludedColumns]
FROM sys.indexes AS i
INNER JOIN sys.tables AS t
    ON t.object_id = i.object_id
INNER JOIN sys.index_columns AS ic
    ON  ic.object_id = i.object_id
    AND ic.index_id  = i.index_id
INNER JOIN sys.columns AS c
    ON  c.object_id = ic.object_id
    AND c.column_id = ic.column_id
WHERE SCHEMA_NAME(t.schema_id) = @SchemaName
  AND i.type > 0                                  -- exclude heaps
GROUP BY
    t.schema_id, t.name,
    i.name, i.type_desc, i.is_unique,
    i.is_primary_key, i.is_unique_constraint,
    i.has_filter, i.filter_definition
ORDER BY t.name, i.name;
GO


-- ============================================================================
-- 6. KEY COLUMN USAGE — which columns participate in which constraints
-- ============================================================================
DECLARE @SchemaName NVARCHAR(128) = N'dbo';

SELECT
    kcu.TABLE_SCHEMA        AS [SchemaName],
    kcu.TABLE_NAME          AS [TableName],
    kcu.CONSTRAINT_NAME     AS [ConstraintName],
    kcu.COLUMN_NAME         AS [ColumnName],
    kcu.ORDINAL_POSITION    AS [OrdinalPosition],
    tc.CONSTRAINT_TYPE      AS [ConstraintType]
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
INNER JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
    ON  tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
    AND tc.CONSTRAINT_NAME   = kcu.CONSTRAINT_NAME
    AND tc.TABLE_NAME        = kcu.TABLE_NAME
WHERE kcu.TABLE_SCHEMA = @SchemaName
ORDER BY kcu.TABLE_NAME, kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
GO


-- ============================================================================
-- 7. EXTENDED PROPERTIES (descriptions / comments on tables and columns)
-- ============================================================================
DECLARE @SchemaName NVARCHAR(128) = N'dbo';

SELECT
    SCHEMA_NAME(t.schema_id)    AS [SchemaName],
    t.name                      AS [TableName],
    c.name                      AS [ColumnName],   -- NULL for table-level
    ep.name                     AS [PropertyName],
    CAST(ep.value AS NVARCHAR(4000)) AS [PropertyValue]
FROM sys.extended_properties AS ep
INNER JOIN sys.tables AS t
    ON  t.object_id = ep.major_id
LEFT JOIN sys.columns AS c
    ON  c.object_id = ep.major_id
    AND c.column_id = ep.minor_id
WHERE SCHEMA_NAME(t.schema_id) = @SchemaName
  AND ep.class = 1                               -- OBJECT_OR_COLUMN
ORDER BY t.name, c.name;
GO
