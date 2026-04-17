# Ledger API

REST API proxy para el sistema Ledger Workbench. Recibe instrucciones SQL desde
la interfaz, las valida y las ejecuta contra una base de datos PostgreSQL en Supabase.

## Stack

- Python + FastAPI
- psycopg2 (driver PostgreSQL)
- slowapi (rate limiting)
- Desplegado en Render

## Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Verifica conectividad con la base de datos |
| GET | `/tables` | Lista las tablas disponibles en el schema público |
| POST | `/query` | Recibe, valida y ejecuta una instrucción SQL |

### Ejemplo de request

```http
POST /query
Content-Type: application/json

{
  "sql": "SELECT * FROM clientes LIMIT 5;"
}
```

### Ejemplo de response

```json
{
  "status": "success",
  "message": "5 fila(s) encontradas",
  "columns": ["id", "nombre", "email"],
  "rows": [
    { "id": "f009b168...", "nombre": "Ana Torres", "email": "ana.torres@mail.com" }
  ]
}
```

## Seguridad

- Whitelist de comandos: solo `SELECT`, `INSERT`, `UPDATE`, `DELETE`
- Patrones prohibidos: `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `GRANT`, `EXEC`, `--`, `/*`
- Rate limiting: 30 requests por minuto por IP (responde `429` al superarlo)
- Query timeout: 5,000ms via `SET statement_timeout` en sesión PostgreSQL
- Logs de auditoría: queries rechazadas y timeouts registrados en Render Logs

## Instalación local

```bash
git clone https://github.com/YahwthaniMG/ledger-api
cd ledger-api
pip install -r requirements.txt
```

Crea un archivo `.env` en la raíz:
```
DATABASE_URL=postgresql://[usuario]:[password]@[host]:[puerto]/postgres
```
Corre el servidor:

```bash
uvicorn main:app --reload
```

El API queda disponible en `http://127.0.0.1:8000`.
La documentación interactiva en `http://127.0.0.1:8000/docs`.

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `DATABASE_URL` | Connection string de PostgreSQL (Supabase Transaction Pooler, puerto 6543) |

## Estructura del proyecto 
```
ledger-api/
├── main.py            # Aplicacion FastAPI completa
├── requirements.txt   # Dependencias
└── .env               # Variables de entorno (no incluido en el repo)
```

## Deployment

El proyecto se despliega en Render como Web Service con las siguientes configuraciones:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port 10000`
- Variable de entorno `DATABASE_URL` configurada en el dashboard de Render
