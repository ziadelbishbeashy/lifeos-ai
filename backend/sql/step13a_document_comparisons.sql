/* Step 13A — Document comparison foundation
   Manual SQL Server fallback only.
   Do NOT run this after the Alembic migration succeeds.
*/

CREATE TABLE document_comparisons (
    id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    user_id INT NOT NULL,
    document_a_id INT NOT NULL,
    document_b_id INT NOT NULL,
    summary NVARCHAR(MAX) NULL,
    findings_json NVARCHAR(MAX) NULL,
    provider NVARCHAR(30) NOT NULL,
    model NVARCHAR(100) NOT NULL,
    status NVARCHAR(20) NOT NULL,
    source_fingerprint NVARCHAR(64) NULL,
    error_message NVARCHAR(MAX) NULL,
    created_at DATETIME NOT NULL,

    CONSTRAINT ck_document_comparisons_distinct_documents
        CHECK (document_a_id <> document_b_id),

    CONSTRAINT fk_document_comparisons_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    -- SQL Server multiple-cascade-path protection:
    CONSTRAINT fk_document_comparisons_document_a
        FOREIGN KEY (document_a_id)
        REFERENCES documents(id)
        ON DELETE NO ACTION,

    CONSTRAINT fk_document_comparisons_document_b
        FOREIGN KEY (document_b_id)
        REFERENCES documents(id)
        ON DELETE NO ACTION
);

CREATE INDEX ix_document_comparisons_user_id
    ON document_comparisons(user_id);

CREATE INDEX ix_document_comparisons_document_a_id
    ON document_comparisons(document_a_id);

CREATE INDEX ix_document_comparisons_document_b_id
    ON document_comparisons(document_b_id);

CREATE INDEX ix_document_comparisons_status
    ON document_comparisons(status);

CREATE INDEX ix_document_comparisons_reuse
    ON document_comparisons(
        user_id,
        document_a_id,
        document_b_id,
        status,
        source_fingerprint
    );
