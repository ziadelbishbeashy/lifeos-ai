# Neon deployment target

Use two connection URLs in hosted environments:

- `DATABASE_URL` — normal application runtime URL (pooler URL when appropriate).
- `DATABASE_DIRECT_URL` — direct PostgreSQL URL for migrations/admin operations.

Secrets belong only in backend/deployment environment variables. Never expose a
Neon password in `frontend/` or a `VITE_*` variable.

Recommended environments:

1. local PostgreSQL
2. Neon development
3. Neon staging
4. Neon production

Do not put real production data into feature branches.
