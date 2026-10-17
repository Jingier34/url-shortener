import random
import re
import sqlite3
import string
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

app = FastAPI()

DB_PATH = "urls.db"
RESERVED_CODES = {"stats", "health", "docs", "redoc", "shorten"}
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,20}$")

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                code TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                created_at TEXT NOT NULL,
                clicks INTEGER DEFAULT 0
            )
        """)

init_db()

class URLRequest(BaseModel):
    url: str
    custom_code: Optional[str] = None

def code_exists(conn, code):
    return conn.execute("SELECT 1 FROM urls WHERE code = ?", (code,)).fetchone() is not None

def generate_code(conn, length=6):
    chars = string.ascii_letters + string.digits
    while True:
        code = "".join(random.choices(chars, k=length))
        if not code_exists(conn, code):
            return code

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/shorten")
def shorten_url(request: URLRequest):
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    with get_conn() as conn:
        if request.custom_code:
            code = request.custom_code
            if not CODE_PATTERN.match(code):
                raise HTTPException(
                    status_code=400,
                    detail="Custom code must be 3-20 characters: letters, digits, '-' or '_'",
                )
            if code.lower() in RESERVED_CODES:
                raise HTTPException(status_code=400, detail="This code is reserved")
            if code_exists(conn, code):
                raise HTTPException(status_code=409, detail="This code is already taken")
        else:
            code = generate_code(conn)

        conn.execute(
            "INSERT INTO urls (code, url, created_at) VALUES (?, ?, ?)",
            (code, request.url, datetime.now().isoformat()),
        )

    return {"short_code": code, "short_url": f"http://127.0.0.1:8000/{code}"}

@app.get("/stats/{code}")
def get_stats(code: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT code, url, created_at, clicks FROM urls WHERE code = ?", (code,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Short link not found")
    return {
        "short_code": row[0],
        "original_url": row[1],
        "created_at": row[2],
        "clicks": row[3],
    }

@app.get("/{code}")
def redirect(code: str):
    with get_conn() as conn:
        row = conn.execute("SELECT url FROM urls WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Short link not found")
        conn.execute("UPDATE urls SET clicks = clicks + 1 WHERE code = ?", (code,))
    return RedirectResponse(row[0])