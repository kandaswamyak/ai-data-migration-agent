-- Converted procedure DDL: 5 procedure(s)
-- Generated at: 2026-09-30 15:24:44

-- Procedure: GET_EMPLOYEE_SUMMARY
CREATE OR ALTER PROCEDURE get_employee_summary
    @p_dept_id INT,
    @p_summary NVARCHAR(4000) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @v_count INT;
    DECLARE @v_total_sal MONEY;
    DECLARE @v_run_date NVARCHAR(20);

    BEGIN TRY
        SET @v_run_date = CONVERT(NVARCHAR(20), GETDATE(), 23); -- 'YYYY-MM-DD'

        SELECT
            @v_count = COUNT(*),
            @v_total_sal = ISNULL(SUM(salary), 0)
        FROM employees
        WHERE department_id = @p_dept_id;

        SET @p_summary = 'Dept ' + CAST(@p_dept_id AS NVARCHAR(10))
                       + ' has ' + CAST(@v_count AS NVARCHAR(10)) + ' employee(s), total salary '
                       + ISNULL(CAST(@v_total_sal AS NVARCHAR(50)), '0')
                       + ' as of ' + @v_run_date;
    END TRY
    BEGIN CATCH
        PRINT 'Error occurred: ' + ERROR_MESSAGE();
        SET @p_summary = NULL;
    END CATCH
END;

GO

-- Procedure: VW_CUSTOMER_CONTACT
CREATE OR ALTER VIEW dbo.VW_CUSTOMER_CONTACT AS
SELECT CUSTOMER_ID, CUSTOMER_NAME, EMAIL, CITY
FROM dbo.CUSTOMER;

GO

-- Procedure: VW_DEPT_SALARY_SUMMARY
CREATE OR ALTER VIEW dbo.VW_DEPT_SALARY_SUMMARY AS
SELECT DEPARTMENT_ID,
       COUNT(*)              AS EMPLOYEE_COUNT,
       SUM(SALARY)           AS TOTAL_SALARY,
       AVG(SALARY)           AS AVG_SALARY,
       MAX(SALARY)           AS MAX_SALARY
FROM dbo.EMPLOYEES
GROUP BY DEPARTMENT_ID;

GO

-- Procedure: VW_TOP_EARNERS
CREATE OR ALTER VIEW dbo.VW_TOP_EARNERS AS
SELECT TOP 10 EMPLOYEE_ID,
       ISNULL(FIRST_NAME, 'UNKNOWN') + ' ' + ISNULL(LAST_NAME, '') AS FULL_NAME,
       DEPARTMENT_ID,
       FORMAT(SALARY, 'N2') AS SALARY_LABEL,
       RANK() OVER (PARTITION BY DEPARTMENT_ID ORDER BY SALARY DESC) AS DEPT_SALARY_RANK
FROM dbo.EMPLOYEES;

GO

-- Procedure: V_EMPLOYEE_DEPT_SUMMARY
CREATE OR ALTER VIEW dbo.V_EMPLOYEE_DEPT_SUMMARY AS
SELECT
    e.employee_id,
    e.full_name,
    e.department_id,
    e.salary_label,
    e.dept_salary_rank,
    d.employee_count,
    d.total_salary,
    d.avg_salary,
    d.max_salary
FROM (
        -- per-employee ranking within department
        SELECT
            employee_id,
            ISNULL(first_name, 'UNKNOWN') + ' ' + ISNULL(last_name, '') AS full_name,
            department_id,
            FORMAT(salary, 'N2') AS salary_label,
            RANK() OVER (PARTITION BY department_id ORDER BY salary DESC) AS dept_salary_rank
        FROM dbo.employees
     ) e
JOIN (
        -- per-department salary aggregates
        SELECT
            department_id,
            COUNT(*) AS employee_count,
            SUM(salary) AS total_salary,
            AVG(salary) AS avg_salary,
            MAX(salary) AS max_salary
        FROM dbo.employees
        GROUP BY department_id
     ) d
  ON d.department_id = e.department_id;

GO

