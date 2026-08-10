/* LifeOS Step 12 — Project-wide multi-document RAG
   Use only if Alembic migration cannot be run. Do not run both. */

IF OBJECT_ID(N'dbo.project_questions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.project_questions (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        project_id INT NOT NULL,
        user_id INT NOT NULL,
        question NVARCHAR(2000) NOT NULL,
        answer NVARCHAR(MAX) NULL,
        sources_json NVARCHAR(MAX) NULL,
        provider NVARCHAR(30) NOT NULL,
        model NVARCHAR(100) NOT NULL,
        status NVARCHAR(20) NOT NULL,
        source_fingerprint NVARCHAR(64) NULL,
        error_message NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_project_questions_project
            FOREIGN KEY (project_id) REFERENCES dbo.projects(id),
        CONSTRAINT FK_project_questions_user
            FOREIGN KEY (user_id) REFERENCES dbo.users(id)
    );

    CREATE INDEX ix_project_questions_project_id
        ON dbo.project_questions(project_id);
    CREATE INDEX ix_project_questions_user_id
        ON dbo.project_questions(user_id);
    CREATE INDEX ix_project_questions_status
        ON dbo.project_questions(status);
END;
