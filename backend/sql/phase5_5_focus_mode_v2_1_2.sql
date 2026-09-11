/* ================================================================
   LifeOS AI — Focus Studio v2.1 + v2.2
   SQL Server migration

   Run after:
     1) phase5_5_focus_mode.sql
     2) phase5_5_focus_mode_v2.sql
   ================================================================ */

SET XACT_ABORT ON;
GO

/* ---------- Focus session phase/cycle recovery fields ---------- */
IF COL_LENGTH('dbo.focus_sessions', 'phase_elapsed_seconds') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions
    ADD phase_elapsed_seconds INT NOT NULL
        CONSTRAINT DF_focus_sessions_phase_elapsed_seconds DEFAULT (0) WITH VALUES;
END;
GO

IF COL_LENGTH('dbo.focus_sessions', 'phase_started_at') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions ADD phase_started_at DATETIME2 NULL;
END;
GO

IF COL_LENGTH('dbo.focus_sessions', 'auto_start_breaks') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions
    ADD auto_start_breaks BIT NOT NULL
        CONSTRAINT DF_focus_sessions_auto_start_breaks DEFAULT (0) WITH VALUES;
END;
GO

IF COL_LENGTH('dbo.focus_sessions', 'auto_start_focus') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions
    ADD auto_start_focus BIT NOT NULL
        CONSTRAINT DF_focus_sessions_auto_start_focus DEFAULT (0) WITH VALUES;
END;
GO

IF COL_LENGTH('dbo.focus_sessions', 'ambient_sound') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions
    ADD ambient_sound NVARCHAR(30) NOT NULL
        CONSTRAINT DF_focus_sessions_ambient_sound DEFAULT (N'none') WITH VALUES;
END;
GO

IF COL_LENGTH('dbo.focus_sessions', 'ambient_theme') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions
    ADD ambient_theme NVARCHAR(30) NOT NULL
        CONSTRAINT DF_focus_sessions_ambient_theme DEFAULT (N'midnight') WITH VALUES;
END;
GO

/* Recover the phase clock for a session that was already running. */
UPDATE dbo.focus_sessions
SET phase_started_at = started_at
WHERE status = N'running'
  AND phase_started_at IS NULL
  AND started_at IS NOT NULL;
GO

/* v2.0 stored a paused block in elapsed_seconds. Move it into the new
   current-phase field so an existing paused session resumes accurately. */
UPDATE dbo.focus_sessions
SET phase_elapsed_seconds = elapsed_seconds,
    elapsed_seconds = 0
WHERE status = N'paused'
  AND current_phase = N'focus'
  AND phase_elapsed_seconds = 0
  AND elapsed_seconds > 0;
GO

/* ---------- Distraction inbox ---------- */
IF OBJECT_ID('dbo.focus_distractions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.focus_distractions (
        id INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_focus_distractions PRIMARY KEY,
        session_id INT NOT NULL,
        user_id INT NOT NULL,
        content NVARCHAR(500) NOT NULL,
        captured_at DATETIME2 NOT NULL
            CONSTRAINT DF_focus_distractions_captured_at DEFAULT (SYSUTCDATETIME()),
        converted_task_id INT NULL,

        CONSTRAINT FK_focus_distractions_session
            FOREIGN KEY (session_id) REFERENCES dbo.focus_sessions(id)
            ON DELETE CASCADE,
        CONSTRAINT FK_focus_distractions_user
            FOREIGN KEY (user_id) REFERENCES dbo.users(id),
        CONSTRAINT FK_focus_distractions_task
            FOREIGN KEY (converted_task_id) REFERENCES dbo.tasks(id)
            ON DELETE SET NULL
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_focus_distractions_session_id'
      AND object_id = OBJECT_ID('dbo.focus_distractions')
)
BEGIN
    CREATE INDEX IX_focus_distractions_session_id
        ON dbo.focus_distractions(session_id);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_focus_distractions_user_id'
      AND object_id = OBJECT_ID('dbo.focus_distractions')
)
BEGIN
    CREATE INDEX IX_focus_distractions_user_id
        ON dbo.focus_distractions(user_id);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_focus_distractions_converted_task_id'
      AND object_id = OBJECT_ID('dbo.focus_distractions')
)
BEGIN
    CREATE INDEX IX_focus_distractions_converted_task_id
        ON dbo.focus_distractions(converted_task_id);
END;
GO

/* ---------- User focus preferences ---------- */
IF OBJECT_ID('dbo.focus_preferences', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.focus_preferences (
        id INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_focus_preferences PRIMARY KEY,
        user_id INT NOT NULL,
        daily_focus_goal INT NOT NULL
            CONSTRAINT DF_focus_preferences_daily_goal DEFAULT (120),
        default_method NVARCHAR(30) NOT NULL
            CONSTRAINT DF_focus_preferences_method DEFAULT (N'pomodoro'),
        default_cycles INT NOT NULL
            CONSTRAINT DF_focus_preferences_cycles DEFAULT (1),
        default_sound NVARCHAR(30) NOT NULL
            CONSTRAINT DF_focus_preferences_sound DEFAULT (N'none'),
        default_theme NVARCHAR(30) NOT NULL
            CONSTRAINT DF_focus_preferences_theme DEFAULT (N'midnight'),
        auto_start_breaks BIT NOT NULL
            CONSTRAINT DF_focus_preferences_auto_breaks DEFAULT (0),
        auto_start_focus BIT NOT NULL
            CONSTRAINT DF_focus_preferences_auto_focus DEFAULT (0),
        show_coach_prompts BIT NOT NULL
            CONSTRAINT DF_focus_preferences_coach DEFAULT (1),
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_focus_preferences_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2 NOT NULL
            CONSTRAINT DF_focus_preferences_updated DEFAULT (SYSUTCDATETIME()),

        CONSTRAINT UQ_focus_preferences_user UNIQUE (user_id),
        CONSTRAINT FK_focus_preferences_user
            FOREIGN KEY (user_id) REFERENCES dbo.users(id)
            ON DELETE CASCADE
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_focus_preferences_user_id'
      AND object_id = OBJECT_ID('dbo.focus_preferences')
)
BEGIN
    CREATE UNIQUE INDEX IX_focus_preferences_user_id
        ON dbo.focus_preferences(user_id);
END;
GO

PRINT 'Focus Studio v2.1 + v2.2 migration completed successfully.';
GO
