USE LifeOSDB;
GO

/* =========================================================
   PHASE 5.1 PROFESSIONAL NOTIFICATIONS
   Adds:
   - notification_preferences
   - custom reminder fields on tasks
   - richer email log fields
   ========================================================= */

IF OBJECT_ID('dbo.notification_preferences', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.notification_preferences (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        user_id INT NOT NULL,
        email_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_email_enabled DEFAULT 1,
        task_reminders_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_task_reminders_enabled DEFAULT 1,
        custom_task_reminders_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_custom_task_reminders_enabled DEFAULT 1,
        overdue_alerts_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_overdue_alerts_enabled DEFAULT 1,
        project_deadline_alerts_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_project_deadline_alerts_enabled DEFAULT 1,
        project_risk_alerts_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_project_risk_alerts_enabled DEFAULT 1,
        daily_checkup_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_daily_checkup_enabled DEFAULT 0,
        weekly_summary_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_weekly_summary_enabled DEFAULT 0,
        monthly_analytics_enabled BIT NOT NULL CONSTRAINT DF_notification_preferences_monthly_analytics_enabled DEFAULT 0,
        task_reminder_days_before INT NOT NULL CONSTRAINT DF_notification_preferences_task_days_before DEFAULT 1,
        project_reminder_days_before INT NOT NULL CONSTRAINT DF_notification_preferences_project_days_before DEFAULT 3,
        daily_checkup_time TIME NOT NULL CONSTRAINT DF_notification_preferences_daily_time DEFAULT '08:00',
        weekly_summary_day INT NOT NULL CONSTRAINT DF_notification_preferences_weekly_day DEFAULT 6,
        weekly_summary_time TIME NOT NULL CONSTRAINT DF_notification_preferences_weekly_time DEFAULT '18:00',
        monthly_report_day INT NOT NULL CONSTRAINT DF_notification_preferences_monthly_day DEFAULT 1,
        monthly_report_time TIME NOT NULL CONSTRAINT DF_notification_preferences_monthly_time DEFAULT '08:00',
        quiet_hours_start TIME NULL,
        quiet_hours_end TIME NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_notification_preferences_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_notification_preferences_updated_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_notification_preferences_user_id'
      AND object_id = OBJECT_ID('dbo.notification_preferences')
)
BEGIN
    CREATE UNIQUE INDEX UX_notification_preferences_user_id
    ON dbo.notification_preferences(user_id);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_notification_preferences_users_user_id'
)
BEGIN
    ALTER TABLE dbo.notification_preferences
    ADD CONSTRAINT FK_notification_preferences_users_user_id
    FOREIGN KEY (user_id)
    REFERENCES dbo.users(id);
END;
GO

INSERT INTO dbo.notification_preferences (user_id)
SELECT u.id
FROM dbo.users u
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.notification_preferences p
    WHERE p.user_id = u.id
);
GO

IF COL_LENGTH('dbo.tasks', 'reminder_enabled') IS NULL
BEGIN
    ALTER TABLE dbo.tasks
    ADD reminder_enabled BIT NOT NULL
        CONSTRAINT DF_tasks_reminder_enabled DEFAULT 0;
END;
GO

IF COL_LENGTH('dbo.tasks', 'reminder_type') IS NULL
BEGIN
    ALTER TABLE dbo.tasks
    ADD reminder_type NVARCHAR(50) NOT NULL
        CONSTRAINT DF_tasks_reminder_type DEFAULT 'none';
END;
GO

IF COL_LENGTH('dbo.tasks', 'reminder_datetime') IS NULL
BEGIN
    ALTER TABLE dbo.tasks
    ADD reminder_datetime DATETIME2 NULL;
END;
GO

IF COL_LENGTH('dbo.tasks', 'last_reminder_sent_at') IS NULL
BEGIN
    ALTER TABLE dbo.tasks
    ADD last_reminder_sent_at DATETIME2 NULL;
END;
GO


IF OBJECT_ID('dbo.email_notification_logs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.email_notification_logs (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        user_id INT NOT NULL,
        task_id INT NULL,
        project_id INT NULL,
        notification_type NVARCHAR(80) NOT NULL,
        sent_to NVARCHAR(255) NOT NULL,
        subject NVARCHAR(255) NULL,
        status NVARCHAR(50) NOT NULL CONSTRAINT DF_email_notification_logs_status_new DEFAULT 'sent',
        error_message NVARCHAR(MAX) NULL,
        unique_key NVARCHAR(255) NOT NULL,
        sent_at DATETIME2 NOT NULL CONSTRAINT DF_email_notification_logs_sent_at_new DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'project_id') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs
    ADD project_id INT NULL;
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'subject') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs
    ADD subject NVARCHAR(255) NULL;
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'status') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs
    ADD status NVARCHAR(50) NOT NULL
        CONSTRAINT DF_email_notification_logs_status DEFAULT 'sent';
END;
GO

IF COL_LENGTH('dbo.email_notification_logs', 'error_message') IS NULL
BEGIN
    ALTER TABLE dbo.email_notification_logs
    ADD error_message NVARCHAR(MAX) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_email_notification_logs_projects_project_id'
)
BEGIN
    ALTER TABLE dbo.email_notification_logs
    ADD CONSTRAINT FK_email_notification_logs_projects_project_id
    FOREIGN KEY (project_id)
    REFERENCES dbo.projects(id);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_email_notification_logs_project_id'
      AND object_id = OBJECT_ID('dbo.email_notification_logs')
)
BEGIN
    CREATE INDEX IX_email_notification_logs_project_id
    ON dbo.email_notification_logs(project_id);
END;
GO

SELECT
    (SELECT COUNT(*) FROM dbo.notification_preferences) AS notification_preferences,
    (SELECT COUNT(*) FROM dbo.email_notification_logs) AS email_logs;
GO

-- Extra safety if this file is run without the older Phase 5.1 SQL file.
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
