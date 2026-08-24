/* LifeOS AI - Phase 5.5 Focus Mode (SQL Server) */

IF OBJECT_ID('focus_sessions', 'U') IS NULL
BEGIN
    CREATE TABLE focus_sessions (
        id INT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL,
        task_id INT NULL,
        title NVARCHAR(200) NOT NULL,
        planned_minutes INT NOT NULL CONSTRAINT DF_focus_planned DEFAULT 25,
        actual_minutes INT NOT NULL CONSTRAINT DF_focus_actual DEFAULT 0,
        elapsed_seconds INT NOT NULL CONSTRAINT DF_focus_elapsed DEFAULT 0,
        status NVARCHAR(30) NOT NULL CONSTRAINT DF_focus_status DEFAULT 'running',
        distraction_count INT NOT NULL CONSTRAINT DF_focus_distractions DEFAULT 0,
        notes NVARCHAR(MAX) NULL,
        started_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_focus_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_focus_sessions_users FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT FK_focus_sessions_tasks FOREIGN KEY (task_id) REFERENCES tasks(id)
    );

    CREATE INDEX IX_focus_sessions_user_id ON focus_sessions(user_id);
    CREATE INDEX IX_focus_sessions_task_id ON focus_sessions(task_id);
    CREATE INDEX IX_focus_sessions_status ON focus_sessions(status);
END;
