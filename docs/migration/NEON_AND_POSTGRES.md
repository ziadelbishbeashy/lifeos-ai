# PostgreSQL / Neon migration strategy

The current project history was built against SQL Server, and several historical
Alembic revisions contain `mssql` types/defaults. That migration history is kept
for auditability but is not portable enough to replay on a clean Neon database.

## Safe migration

1. Keep the current SQL Server database untouched as a rollback source.
2. Prove the current SQLAlchemy model schema on disposable PostgreSQL.
3. Freeze a **new PostgreSQL baseline** that represents the current schema.
4. Export/transform only the application data that needs to survive.
5. Import it into PostgreSQL and verify record counts/relationships.
6. Run the full integration/RAG suite against PostgreSQL.
7. Repeat against Neon staging.
8. Cut production only after staging passes.

Do not combine data migration, model redesign, OCR and React feature rewrites in
a single cutover.
