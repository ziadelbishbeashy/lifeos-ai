# LifeOS Ask Prompt + Backend/Database Security Hardening

Apply after:
1. `lifeos-ai-ask-reasoning-i9-security-patch.zip`
2. `lifeos-ai-ask-reasoning-test-hotfix.zip`

No database migration. Expected Alembic head remains `20260906_0001`.
No `frontend/public` content.

## Ask LifeOS reasoning prompt

- Treats workspace context as evidence, not the answer.
- Explicitly separates workspace facts, workspace inferences, recommendations, and general/domain knowledge.
- Adds deterministic advisory lenses for technical architecture, debugging, prioritization, decisions, and planning.
- Requires a useful conclusion beyond context paraphrasing.
- Allows domain expertise for recommendations while preserving strict grounding for LifeOS facts.
- Preserves paragraphs/bullets in the user-facing answer.
- Applies the same trust philosophy to the I19 agent reasoner.
- Never permits the reasoner to write to the DB or bypass I9.

## I9 security hardening

- Keeps the signed, owner-bound priority envelope from the prior patch.
- Reuses identical pending proposals to reduce replay/double-click duplication.
- Makes confirmation acquisition atomic with a conditional DB UPDATE so only one concurrent worker can execute a proposal.
- Rechecks action allowlist and `requires_confirmation` at confirmation time.

## Backend/request hardening

- Regenerates the session on login/register by clearing the old session before authentication.
- Clears the full session on logout.
- Frontend resets the CSRF token after auth session rotation.
- Rejects TRACE requests.
- Validates client-supplied request IDs before reflecting them to logs/headers.
- Adds host allowlisting support.
- Adds same-origin/Fetch Metadata checks for unsafe `/api/` requests as defense-in-depth on top of Flask-WTF CSRF.
- Adds a smaller JSON API body limit independent of document upload size.
- Adds partial CSP, CORP, X-Permitted-Cross-Domain-Policies, no-store/noindex controls for private surfaces.
- Proxy headers are trusted only when explicitly enabled.

## Database/production hardening

- Encrypts SQL Server transport by default.
- Production requires server certificate verification for SQL Server when used.
- Production DB transport validation requires PostgreSQL TLS (`sslmode=require`, `verify-ca`, or `verify-full`) or encrypted/certificate-verified MSSQL when the temporary Postgres requirement is disabled.
- Production fails closed if DEBUG, AUTO_CREATE_DB, CSRF, secure cookies, HTTPS PUBLIC_BASE_URL, strong SECRET_KEY, or DB TLS requirements are unsafe.
- Ownerless legacy projects cannot be silently auto-claimed in production.
- Adds a static gate against obvious f-string SQL execution in runtime code.
- Adds a static gate requiring authentication on every private v1 API route.
- Adds a static gate ensuring AI reasoning services never acquire direct DB write access.

## New/updated env values

Development defaults are documented in `backend/.env.example`:

```env
REMEMBER_COOKIE_DAYS=14
MAX_API_JSON_KB=256
ALLOWED_HOSTS=127.0.0.1,localhost
TRUST_PROXY_HEADERS=false
ALLOW_LEGACY_PROJECT_AUTO_CLAIM=true
DB_ENCRYPT=true
DB_TRUST_SERVER_CERTIFICATE=true
REQUIRE_DATABASE_TLS_IN_PRODUCTION=true
```

For production, use HTTPS, a strong random SECRET_KEY, explicit hostnames, and certificate-verified DB TLS. Do not copy the development `DB_TRUST_SERVER_CERTIFICATE=true` value into production.

## Verification

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest tests\test_ask_lifeos_reasoning_i9_upgrade.py -q
py -3.11 -m pytest tests\test_security.py -q
py -3.11 -m pytest tests\test_production_security_config.py -q
py -3.11 -m pytest tests\test_security_source_gates.py -q
py -3.11 -m pytest tests\test_auth_service.py -q
py -3.11 -m pytest -q

cd ..\frontend
npm run build
npm run css:check
```

The sandbox used to build this patch did not have Flask installed, so the real pytest suite could not execute here. Python syntax compilation and the dependency-free static security gates passed.
