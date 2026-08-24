USE LifeOSDB;
GO

/*
    LifeOS Phase 6.1 — AI Notes complete schema

    This script is intentionally idempotent:
    - creates the Phase 6 note tables when they do not exist,
    - adds the user-friendly insights_json column to existing installations,
    - creates the required indexes only when missing.
*/

IF OBJECT_ID('dbo.notes', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.notes
    (
        id INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_notes PRIMARY KEY,
        user_id INT NOT NULL,
        project_id INT NULL,
        title NVARCHAR(255) NOT NULL,
        content NVARCHAR(MAX) NOT NULL,
        note_type NVARCHAR(50) NOT NULL
            CONSTRAINT DF_notes_note_type DEFAULT 'Quick Note',
        is_pinned BIT NOT NULL
            CONSTRAINT DF_notes_is_pinned DEFAULT 0,
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_notes_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL
            CONSTRAINT DF_notes_updated_at DEFAULT SYSUTCDATETIME(),

        CONSTRAINT FK_notes_user
            FOREIGN KEY (user_id) REFERENCES dbo.users(id),
        CONSTRAINT FK_notes_project
            FOREIGN KEY (project_id) REFERENCES dbo.projects(id)
    );

    PRINT 'Created dbo.notes.';
END;
GO

IF OBJECT_ID('dbo.note_ai_analyses', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.note_ai_analyses
    (
        id INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_note_ai_analyses PRIMARY KEY,
        note_id INT NOT NULL,
        user_id INT NOT NULL,
        provider NVARCHAR(30) NOT NULL,
        model NVARCHAR(100) NOT NULL,
        status NVARCHAR(20) NOT NULL
            CONSTRAINT DF_note_ai_analyses_status DEFAULT 'Completed',
        summary NVARCHAR(MAX) NULL,
        tags_json NVARCHAR(MAX) NULL,
        deadlines_json NVARCHAR(MAX) NULL,
        decisions_json NVARCHAR(MAX) NULL,
        questions_json NVARCHAR(MAX) NULL,
        insights_json NVARCHAR(MAX) NULL,
        error_message NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_note_ai_analyses_created_at DEFAULT SYSUTCDATETIME(),

        CONSTRAINT FK_note_ai_analyses_note
            FOREIGN KEY (note_id) REFERENCES dbo.notes(id),
        CONSTRAINT FK_note_ai_analyses_user
            FOREIGN KEY (user_id) REFERENCES dbo.users(id),
        CONSTRAINT CK_note_ai_analyses_status
            CHECK (status IN ('Pending', 'Completed', 'Failed'))
    );

    PRINT 'Created dbo.note_ai_analyses.';
END;
GO

IF COL_LENGTH('dbo.note_ai_analyses', 'insights_json') IS NULL
BEGIN
    ALTER TABLE dbo.note_ai_analyses
        ADD insights_json NVARCHAR(MAX) NULL;

    PRINT 'Added dbo.note_ai_analyses.insights_json.';
END;
GO

IF OBJECT_ID('dbo.ai_task_suggestions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ai_task_suggestions
    (
        id INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ai_task_suggestions PRIMARY KEY,
        analysis_id INT NOT NULL,
        note_id INT NOT NULL,
        title NVARCHAR(255) NOT NULL,
        description NVARCHAR(MAX) NULL,
        priority NVARCHAR(20) NOT NULL
            CONSTRAINT DF_ai_task_suggestions_priority DEFAULT 'Medium',
        deadline DATE NULL,
        status NVARCHAR(20) NOT NULL
            CONSTRAINT DF_ai_task_suggestions_status DEFAULT 'Pending',
        created_task_id INT NULL,
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_ai_task_suggestions_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL
            CONSTRAINT DF_ai_task_suggestions_updated_at DEFAULT SYSUTCDATETIME(),

        CONSTRAINT FK_ai_task_suggestions_analysis
            FOREIGN KEY (analysis_id) REFERENCES dbo.note_ai_analyses(id),
        CONSTRAINT FK_ai_task_suggestions_note
            FOREIGN KEY (note_id) REFERENCES dbo.notes(id),
        CONSTRAINT FK_ai_task_suggestions_created_task
            FOREIGN KEY (created_task_id) REFERENCES dbo.tasks(id),
        CONSTRAINT CK_ai_task_suggestions_priority
            CHECK (priority IN ('Low', 'Medium', 'High')),
        CONSTRAINT CK_ai_task_suggestions_status
            CHECK (status IN ('Pending', 'Approved', 'Rejected'))
    );

    PRINT 'Created dbo.ai_task_suggestions.';
END;
GO

IF OBJECT_ID('dbo.note_ai_questions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.note_ai_questions
    (
        id INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_note_ai_questions PRIMARY KEY,
        note_id INT NOT NULL,
        analysis_id INT NULL,
        user_id INT NOT NULL,
        question NVARCHAR(MAX) NOT NULL,
        answer NVARCHAR(MAX) NULL,
        provider NVARCHAR(30) NOT NULL,
        model NVARCHAR(100) NOT NULL,
        status NVARCHAR(20) NOT NULL
            CONSTRAINT DF_note_ai_questions_status DEFAULT 'Completed',
        error_message NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_note_ai_questions_created_at DEFAULT SYSUTCDATETIME(),

        CONSTRAINT FK_note_ai_questions_note
            FOREIGN KEY (note_id) REFERENCES dbo.notes(id),
        CONSTRAINT FK_note_ai_questions_analysis
            FOREIGN KEY (analysis_id) REFERENCES dbo.note_ai_analyses(id),
        CONSTRAINT FK_note_ai_questions_user
            FOREIGN KEY (user_id) REFERENCES dbo.users(id),
        CONSTRAINT CK_note_ai_questions_status
            CHECK (status IN ('Pending', 'Completed', 'Failed'))
    );

    PRINT 'Created dbo.note_ai_questions.';
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_notes_user_id' AND object_id = OBJECT_ID('dbo.notes')
)
    CREATE INDEX IX_notes_user_id ON dbo.notes(user_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_notes_project_id' AND object_id = OBJECT_ID('dbo.notes')
)
    CREATE INDEX IX_notes_project_id ON dbo.notes(project_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_notes_updated_at' AND object_id = OBJECT_ID('dbo.notes')
)
    CREATE INDEX IX_notes_updated_at ON dbo.notes(updated_at DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_note_ai_analyses_note_id' AND object_id = OBJECT_ID('dbo.note_ai_analyses')
)
    CREATE INDEX IX_note_ai_analyses_note_id ON dbo.note_ai_analyses(note_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_note_ai_analyses_user_id' AND object_id = OBJECT_ID('dbo.note_ai_analyses')
)
    CREATE INDEX IX_note_ai_analyses_user_id ON dbo.note_ai_analyses(user_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_ai_task_suggestions_note_id' AND object_id = OBJECT_ID('dbo.ai_task_suggestions')
)
    CREATE INDEX IX_ai_task_suggestions_note_id ON dbo.ai_task_suggestions(note_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_ai_task_suggestions_analysis_id' AND object_id = OBJECT_ID('dbo.ai_task_suggestions')
)
    CREATE INDEX IX_ai_task_suggestions_analysis_id ON dbo.ai_task_suggestions(analysis_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_note_ai_questions_note_id' AND object_id = OBJECT_ID('dbo.note_ai_questions')
)
    CREATE INDEX IX_note_ai_questions_note_id ON dbo.note_ai_questions(note_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_note_ai_questions_user_id' AND object_id = OBJECT_ID('dbo.note_ai_questions')
)
    CREATE INDEX IX_note_ai_questions_user_id ON dbo.note_ai_questions(user_id);
GO

PRINT 'LifeOS Phase 6.1 AI Notes schema is ready.';
GO
