/* Step 14 — Document versioning
   Manual SQL Server fallback only.
   Do NOT run this after Alembic revision 20260811_0002 succeeds.
*/

CREATE TABLE document_version_families (
    id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    project_id INT NOT NULL,
    user_id INT NOT NULL,
    name NVARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,

    CONSTRAINT fk_document_version_families_project
        FOREIGN KEY (project_id)
        REFERENCES projects(id)
        ON DELETE NO ACTION,

    CONSTRAINT fk_document_version_families_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE NO ACTION
);

CREATE INDEX ix_document_version_families_project_id
    ON document_version_families(project_id);

CREATE INDEX ix_document_version_families_user_id
    ON document_version_families(user_id);

ALTER TABLE documents
    ADD version_family_id INT NULL,
        version_number INT NULL,
        is_current_version BIT NOT NULL
            CONSTRAINT df_documents_is_current_version DEFAULT 1,
        version_change_json NVARCHAR(MAX) NULL,
        superseded_at DATETIME NULL;

ALTER TABLE documents
    ADD CONSTRAINT fk_documents_version_family
        FOREIGN KEY (version_family_id)
        REFERENCES document_version_families(id)
        ON DELETE NO ACTION;

CREATE INDEX ix_documents_version_family_id
    ON documents(version_family_id);

CREATE INDEX ix_documents_is_current_version
    ON documents(is_current_version);

CREATE INDEX ix_documents_version_family_current
    ON documents(
        version_family_id,
        is_current_version,
        version_number
    );
