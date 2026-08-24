/* ================================================================
   LifeOS AI — Phase 5.5 Minimal Focus Mode
   SQL Server migration (safe to run after the basic OR v2 migrations)
   ================================================================ */

SET XACT_ABORT ON;
GO

IF COL_LENGTH('dbo.focus_sessions', 'goal') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions ADD goal NVARCHAR(MAX) NULL;
END;
GO

IF COL_LENGTH('dbo.focus_sessions', 'goal_result') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions ADD goal_result NVARCHAR(20) NULL;
END;
GO

IF COL_LENGTH('dbo.focus_sessions', 'focus_rating') IS NULL
BEGIN
    ALTER TABLE dbo.focus_sessions ADD focus_rating INT NULL;
END;
GO

IF OBJECT_ID('dbo.focus_distractions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.focus_distractions (
        id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_focus_distractions PRIMARY KEY,
        session_id INT NOT NULL,
        user_id INT NOT NULL,
        content NVARCHAR(500) NOT NULL,
        captured_at DATETIME2 NOT NULL CONSTRAINT DF_focus_distractions_captured_at DEFAULT (SYSUTCDATETIME()),
        converted_task_id INT NULL,
        CONSTRAINT FK_focus_distractions_session FOREIGN KEY (session_id) REFERENCES dbo.focus_sessions(id),
        CONSTRAINT FK_focus_distractions_user FOREIGN KEY (user_id) REFERENCES dbo.users(id),
        CONSTRAINT FK_focus_distractions_task FOREIGN KEY (converted_task_id) REFERENCES dbo.tasks(id)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_focus_distractions_session_id'
      AND object_id = OBJECT_ID('dbo.focus_distractions')
)
BEGIN
    CREATE INDEX IX_focus_distractions_session_id ON dbo.focus_distractions(session_id);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_focus_distractions_user_id'
      AND object_id = OBJECT_ID('dbo.focus_distractions')
)
BEGIN
    CREATE INDEX IX_focus_distractions_user_id ON dbo.focus_distractions(user_id);
END;
GO

PRINT 'Minimal Focus Mode migration completed successfully.';
GO
