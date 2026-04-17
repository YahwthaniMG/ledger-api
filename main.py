import os
import re
import time
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
QUERY_TIMEOUT_MS = 5000

# Logger para queries rechazadas
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("ledger.security")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Ledger API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        options=f"-c statement_timeout={QUERY_TIMEOUT_MS}",
    )


class QueryRequest(BaseModel):
    sql: str


@app.get("/health")
@limiter.limit("30/minute")
def health(request: Request):
    try:
        conn = get_connection()
        conn.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}


@app.get("/tables")
@limiter.limit("30/minute")
def tables(request: Request):
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
@limiter.limit("30/minute")
def execute_query(request: Request, body: QueryRequest):
    is_valid, message = validate_query(body.sql)
    if not is_valid:
        logger.warning(
            "REJECTED | ip=%s | reason=%s | sql=%s",
            get_remote_address(request),
            message,
            body.sql[:120],
        )
        return {"status": "error", "message": message, "columns": [], "rows": []}

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SET statement_timeout = {QUERY_TIMEOUT_MS}")
        cursor.execute(body.sql)

        if body.sql.strip().upper().startswith("SELECT"):
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

    except psycopg2.errors.QueryCanceled:
        logger.warning(
            "TIMEOUT | ip=%s | sql=%s", get_remote_address(request), body.sql[:120]
        )
        return {
            "status": "error",
            "message": f"Query cancelada: excedio el limite de {QUERY_TIMEOUT_MS}ms",
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
