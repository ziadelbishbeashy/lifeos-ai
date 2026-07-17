USE LifeOSDB;
GO

IF OBJECT_ID(N'dbo.users', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.users
    (
        id INT IDENTITY(1,1) NOT NULL,
        name NVARCHAR(120) NOT NULL,
        email NVARCHAR(255) NOT NULL,
        password_hash NVARCHAR(255) NOT NULL,
        created_at DATETIME NOT NULL
            CONSTRAINT DF_users_created_at DEFAULT GETUTCDATE(),
        CONSTRAINT PK_users PRIMARY KEY (id),
        CONSTRAINT UQ_users_email UNIQUE (email)
    );
END;
GO

IF COL_LENGTH('dbo.projects', 'user_id') IS NULL
BEGIN
    ALTER TABLE dbo.projects ADD user_id INT NULL;
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_projects_users'
)
BEGIN
    ALTER TABLE dbo.projects
    ADD CONSTRAINT FK_projects_users
        FOREIGN KEY (user_id) REFERENCES dbo.users(id);
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_projects_user_id'
      AND object_id = OBJECT_ID('dbo.projects')
)
BEGIN
    CREATE INDEX IX_projects_user_id ON dbo.projects(user_id);
END;
GO
