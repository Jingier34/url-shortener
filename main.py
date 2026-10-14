import random
import sqlite3
import string
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

app = FastAPI()

DB_PATH = "urls.db"

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

def generate_code(length=6):
    chars = string.ascii_letters + string.digits
    with get_conn() as conn:
        while True:
            code = "".join(random.choices(chars, k=length))
            exists = conn.execute("SELECT 1 FROM urls WHERE code = ?", (code,)).fetchone()
            if not exists:
                return code

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/shorten")
def shorten_url(request: URLRequest):
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    code = generate_code()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO urls (code, url, created_at) VALUES (?, ?, ?)",
            (code, request.url, datetime.now().isoformat()),
        )
    return {"short_code": code, "short_url": f"http://127.0.0.1:8000/{code}"}

@app.get("/{code}")
def redirect(code: str):
    with get_conn() as conn:
        row = conn.execute("SELECT url FROM urls WHERE code = ?", (code,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Short link not found")
    return RedirectResponse(row[0])