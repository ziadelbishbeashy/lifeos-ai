import os
from urllib.parse import quote_plus
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()


def get_database_uri():
    server = os.getenv("DB_SERVER", "localhost")
    database = os.getenv("DB_NAME", "LifeOSDB")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Trusted_Connection=yes;"
        f"TrustServerCertificate=yes;"
    )

    return "mssql+pyodbc:///?odbc_connect=" + quote_plus(connection_string)