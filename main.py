import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="Ledger API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

ALLOWED_COMMANDS = {"SELECT", "INSERT", "UPDATE", "DELETE"}

FORBIDDEN_PATTERNS = [
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bEXEC\b",
    r"--",
    r"/\*",
]


def validate_query(sql: str):
    sql_clean = sql.strip().upper()
    if not sql_clean:
        return False, "La query no puede estar vacia"
    first_word = sql_clean.split()[0]
    if first_word not in ALLOWED_COMMANDS:
        return (
            False,
            f"Comando '{first_word}' no permitido. Solo: {', '.join(ALLOWED_COMMANDS)}",
        )
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, sql_clean):
            return False, f"Patron no permitido detectado: {pattern}"
    return True, "OK"


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


class QueryRequest(BaseModel):
    sql: str


@app.get("/health")
def health():
    try:
        conn = get_connection()
        conn.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}


@app.get("/tables")
def tables():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        )
        result = [row["table_name"] for row in cursor.fetchall()]
        conn.close()
        return {"status": "ok", "tables": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/query")
def execute_query(request: QueryRequest):
    is_valid, message = validate_query(request.sql)
    if not is_valid:
        return {"status": "error", "message": message, "columns": [], "rows": []}

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(request.sql)

        if request.sql.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return {
                "status": "success",
                "message": f"{len(rows)} fila(s) encontradas",
                "columns": columns,
                "rows": [dict(row) for row in rows],
            }
        else:
            conn.commit()
            return {
                "status": "success",
                "message": f"{cursor.rowcount} fila(s) afectadas",
                "columns": [],
                "rows": [],
            }

    except psycopg2.Error as e:
        return {
            "status": "error",
            "message": f"Error de base de datos: {e.pgerror}",
            "columns": [],
            "rows": [],
        }
    finally:
        if conn:
            conn.close()
