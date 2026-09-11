/* LifeOS Step 9 — Document findings to confirmed tasks
   SQL Server safety script for environments where Alembic is not used directly.
   Prefer: python -m flask --app app db upgrade
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF COL_LENGTH('dbo.tasks', 'tags') IS NULL
BEGIN
    ALTER TABLE dbo.tasks
        ADD tags NVARCHAR(500) NULL;
END;

IF COL_LENGTH('dbo.document_task_suggestions', 'tags') IS NULL
BEGIN
    ALTER TABLE dbo.document_task_suggestions
        ADD tags NVARCHAR(500) NULL;
END;

COMMIT TRANSACTION;
