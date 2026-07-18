USE LifeOSDB;
GO

IF OBJECT_ID('dbo.email_notification_logs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.email_notification_logs (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        user_id INT NOT NULL,
        task_id INT NULL,
        notification_type NVARCHAR(80) NOT NULL,
        sent_to NVARCHAR(255) NOT NULL,
        unique_key NVARCHAR(255) NOT NULL,
        sent_at DATETIME2 NOT NULL CONSTRAINT DF_email_notification_logs_sent_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'user_id') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs ADD user_id INT NULL;
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'task_id') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs ADD task_id INT NULL;
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'notification_type') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs ADD notification_type NVARCHAR(80) NULL;
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'sent_to') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs ADD sent_to NVARCHAR(255) NULL;
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'unique_key') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs ADD unique_key NVARCHAR(255) NULL;
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'sent_at') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs ADD sent_at DATETIME2 NULL;
END;
GO

UPDATE dbo.email_notification_logs
SET notification_type = 'unknown'
WHERE notification_type IS NULL;
GO

UPDATE dbo.email_notification_logs
SET sent_to = 'unknown'
WHERE sent_to IS NULL;
GO

UPDATE dbo.email_notification_logs
SET unique_key = CONCAT('legacy_', id)
WHERE unique_key IS NULL;
GO

UPDATE dbo.email_notification_logs
SET sent_at = SYSUTCDATETIME()
WHERE sent_at IS NULL;
GO

ALTER TABLE dbo.email_notification_logs ALTER COLUMN user_id INT NOT NULL;
GO

ALTER TABLE dbo.email_notification_logs ALTER COLUMN notification_type NVARCHAR(80) NOT NULL;
GO

ALTER TABLE dbo.email_notification_logs ALTER COLUMN sent_to NVARCHAR(255) NOT NULL;
GO

ALTER TABLE dbo.email_notification_logs ALTER COLUMN unique_key NVARCHAR(255) NOT NULL;
GO

ALTER TABLE dbo.email_notification_logs ALTER COLUMN sent_at DATETIME2 NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_email_notification_logs_users_user_id'
)
BEGIN
    ALTER TABLE dbo.email_notification_logs
    ADD CONSTRAINT FK_email_notification_logs_users_user_id
    FOREIGN KEY (user_id)
    REFERENCES dbo.users(id);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_email_notification_logs_tasks_task_id'
)
BEGIN
    ALTER TABLE dbo.email_notification_logs
    ADD CONSTRAINT FK_email_notification_logs_tasks_task_id
    FOREIGN KEY (task_id)
    REFERENCES dbo.tasks(id);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_email_notification_logs_unique_key'
      AND object_id = OBJECT_ID('dbo.email_notification_logs')
)
BEGIN
    CREATE UNIQUE INDEX UX_email_notification_logs_unique_key
    ON dbo.email_notification_logs(unique_key);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_email_notification_logs_user_id'
      AND object_id = OBJECT_ID('dbo.email_notification_logs')
)
BEGIN
    CREATE INDEX IX_email_notification_logs_user_id
    ON dbo.email_notification_logs(user_id);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_email_notification_logs_task_id'
      AND object_id = OBJECT_ID('dbo.email_notification_logs')
)
BEGIN
    CREATE INDEX IX_email_notification_logs_task_id
    ON dbo.email_notification_logs(task_id);
END;
GO

SELECT
    COUNT(*) AS total_email_notification_logs
FROM dbo.email_notification_logs;
GO
