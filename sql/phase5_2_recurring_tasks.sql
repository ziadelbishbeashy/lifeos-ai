/* LifeOS AI - Phase 5.2 Recurring Tasks (SQL Server)
   Run this entire file in SQL Server Management Studio.
*/

IF COL_LENGTH('tasks', 'is_recurring') IS NULL
    ALTER TABLE tasks ADD is_recurring BIT NOT NULL CONSTRAINT DF_tasks_is_recurring DEFAULT 0;
GO

IF COL_LENGTH('tasks', 'recurrence_type') IS NULL
    ALTER TABLE tasks ADD recurrence_type NVARCHAR(30) NOT NULL CONSTRAINT DF_tasks_recurrence_type DEFAULT 'none';
GO

IF COL_LENGTH('tasks', 'recurrence_interval') IS NULL
    ALTER TABLE tasks ADD recurrence_interval INT NOT NULL CONSTRAINT DF_tasks_recurrence_interval DEFAULT 1;
GO

IF COL_LENGTH('tasks', 'recurrence_end_date') IS NULL
    ALTER TABLE tasks ADD recurrence_end_date DATE NULL;
GO

IF COL_LENGTH('tasks', 'recurrence_parent_id') IS NULL
    ALTER TABLE tasks ADD recurrence_parent_id INT NULL;
GO

IF COL_LENGTH('tasks', 'recurrence_series_id') IS NULL
    ALTER TABLE tasks ADD recurrence_series_id INT NULL;
GO

IF COL_LENGTH('tasks', 'next_occurrence_date') IS NULL
    ALTER TABLE tasks ADD next_occurrence_date DATE NULL;
GO

IF COL_LENGTH('tasks', 'last_generated_at') IS NULL
    ALTER TABLE tasks ADD last_generated_at DATETIME2 NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_tasks_recurrence_parent'
)
BEGIN
    ALTER TABLE tasks
    ADD CONSTRAINT FK_tasks_recurrence_parent
    FOREIGN KEY (recurrence_parent_id) REFERENCES tasks(id);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_tasks_recurrence_parent_id'
      AND object_id = OBJECT_ID('tasks')
)
    CREATE INDEX IX_tasks_recurrence_parent_id ON tasks(recurrence_parent_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_tasks_recurrence_series_id'
      AND object_id = OBJECT_ID('tasks')
)
    CREATE INDEX IX_tasks_recurrence_series_id ON tasks(recurrence_series_id);
GO
