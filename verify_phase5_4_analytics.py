from pathlib import Path
import py_compile


REQUIRED_FILES = [
    "routes/analytics_routes.py",
    "services/analytics_service.py",
    "templates/analytics.html",
    "static/js/analytics.js",
    "sql/phase5_4_analytics.sql",
]

PYTHON_FILES = [
    "app.py",
    "models.py",
    "routes/analytics_routes.py",
    "routes/task_routes.py",
    "routes/focus_routes.py",
    "services/analytics_service.py",
    "services/notification_service.py",
]


def main():
    failed = False

    for filename in REQUIRED_FILES:
        exists = Path(filename).exists()
        print(f"{'PASS' if exists else 'FAIL'}  {filename}")
        failed = failed or not exists

    for filename in PYTHON_FILES:
        try:
            py_compile.compile(filename, doraise=True)
            print(f"PASS  Python syntax: {filename}")
        except Exception as error:
            failed = True
            print(f"FAIL  Python syntax: {filename} -> {error}")

    if failed:
        raise SystemExit(1)

    print("\nPhase 5.4 Analytics files are synchronized.")
    print("Remember to run sql/phase5_4_analytics.sql before python app.py.")


if __name__ == "__main__":
    main()
