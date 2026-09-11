/* =========================================================
   LifeOS AI — Phase 5.0 Task Logic Upgrade
   Run this once on your SQL Server database before testing
   the updated Phase 5 files.

   Goal:
   - tasks.user_id owns every task directly.
   - tasks.project_id becomes optional.
   - project_id NULL means General Workspace Task.
   ========================================================= */

/* 1) Add user_id if it does not exist yet. */
IF COL_LENGTH('tasks', 'user_id') IS NULL
BEGIN
    ALTER TABLE tasks ADD user_id INT NULL;
END;
GO

/* 2) Backfill existing project tasks with their project owner. */
UPDATE t
SET t.user_id = p.user_id
FROM tasks AS t
INNER JOIN projects AS p
    ON t.project_id = p.id
WHERE t.user_id IS NULL;
GO

/* 3) Make user_id required after backfill. */
IF EXISTS (
    SELECT 1
    FROM tasks
    WHERE user_id IS NULL
)
BEGIN
    RAISERROR('Some tasks still have NULL user_id. Fix them before continuing.', 16, 1);
END;
GO

ALTER TABLE tasks ALTER COLUMN user_id INT NOT NULL;
GO

/* 4) Make project_id optional for general workspace tasks. */
ALTER TABLE tasks ALTER COLUMN project_id INT NULL;
GO

/* 5) Add the user foreign key if it does not exist. */
IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'fk_tasks_users_user_id'
)
BEGIN
    ALTER TABLE tasks
    ADD CONSTRAINT fk_tasks_users_user_id
    FOREIGN KEY (user_id) REFERENCES users(id);
END;
GO

/* 6) Add helpful indexes if they do not exist. */
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'ix_tasks_user_id'
      AND object_id = OBJECT_ID('tasks')
)
BEGIN
    CREATE INDEX ix_tasks_user_id ON tasks(user_id);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'ix_tasks_project_id'
      AND object_id = OBJECT_ID('tasks')
)
BEGIN
    CREATE INDEX ix_tasks_project_id ON tasks(project_id);
END;
GO
