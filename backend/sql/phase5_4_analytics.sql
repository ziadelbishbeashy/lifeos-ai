/* =========================================================
   LifeOS AI - Phase 5.4 Analytics Dashboard
   SQL Server migration

   Adds an accurate completion timestamp for task analytics.
   Run this script before starting the updated Flask project.
   ========================================================= */

IF COL_LENGTH('dbo.tasks', 'completed_at') IS NULL
BEGIN
    ALTER TABLE dbo.tasks
    ADD completed_at DATETIME2 NULL;
END;
GO

/*
   Existing completed tasks did not previously store a completion date.
   Their created_at value is used as a one-time historical approximation.
   New task completions are timestamped accurately by Flask.
*/
UPDATE dbo.tasks
SET completed_at = COALESCE(completed_at, created_at, SYSDATETIME())
WHERE status = 'Completed'
  AND completed_at IS NULL;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_tasks_completed_at'
      AND object_id = OBJECT_ID('dbo.tasks')
)
BEGIN
    CREATE INDEX IX_tasks_completed_at
    ON dbo.tasks (completed_at);
END;
GO
