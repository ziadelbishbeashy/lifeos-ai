# V-SPACE Authentication V1 — Dual Mail Provider Edition

This supersedes both earlier Authentication V1 ZIPs. It keeps the full Authentication V1 feature set and makes transactional email provider-neutral.

## Mail behavior
- Development default: `MAIL_PROVIDER=smtp`
- Production: `MAIL_PROVIDER=sender` (enforced by production config validation)
- Authentication code calls one `send_email(...)` adapter; reset/verification logic does not know which provider is active.
- SMTP credentials and Sender API tokens stay backend-only.

### Local SMTP example
```env
MAIL_PROVIDER=smtp
MAIL_FROM_NAME=V-SPACE
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-development-email@gmail.com
MAIL_PASSWORD=your-google-app-password
MAIL_DEFAULT_SENDER=your-development-email@gmail.com
MAIL_TIMEOUT_SECONDS=20
```
For Gmail, use a Google App Password, never the normal Google account password.

### Production Sender example
```env
MAIL_PROVIDER=sender
SENDER_API_TOKEN=
SENDER_FROM_EMAIL=security@yourdomain.com
SENDER_FROM_NAME=V-SPACE
SENDER_TIMEOUT_SECONDS=15
```
Production intentionally fails closed unless `MAIL_PROVIDER=sender` and Sender credentials are present.

## Security
- SMTP uses STARTTLS when `MAIL_USE_TLS=true`.
- Sender uses its fixed official HTTPS transactional endpoint.
- Provider secrets never go to React/browser storage.
- Provider error bodies are not returned to users.
- Password reset / verification tokens remain hashed, expiring and single-use.
- Session hardening from Authentication V1 is unchanged.

## Migration
No additional migration. Authentication head remains:
`20260912_0003`

## Validation
```powershell
cd backend
py -3.11 -m pip install -r requirements.txt
py -3.11 -m pytest -q tests/test_sender_email_service.py tests/test_auth.py tests/test_auth_service.py tests/test_authentication_v1.py tests/test_production_security_config.py
py -3.11 -m pytest -q
py -3.11 -m alembic -c migrations/alembic.ini upgrade head
py -3.11 -m alembic -c migrations/alembic.ini current
```
Expected head: `20260912_0003 (head)`

Frontend:
```powershell
cd ..\frontend
npm run build
npm run css:check
```
