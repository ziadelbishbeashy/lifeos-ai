$ErrorActionPreference = "Stop"

Push-Location "$PSScriptRoot\..\backend"
try {
    python -m py_compile app.py config.py database.py extensions.py lifeos\application.py lifeos\core\config.py lifeos\core\database.py lifeos\core\extensions.py lifeos\api\v1\routes.py
    python scripts\check_postgres_portability.py
    python -m pytest
}
finally {
    Pop-Location
}
