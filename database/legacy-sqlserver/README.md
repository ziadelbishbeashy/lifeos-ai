# Legacy SQL Server transition

Existing developer databases can temporarily remain on SQL Server by setting:

```env
DB_BACKEND=legacy_sqlserver
```

and installing:

```powershell
pip install -r requirements-legacy-sqlserver.txt
```

No new feature should add SQL Server-specific SQL or migration constructs.
