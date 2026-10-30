import random
import re
import sqlite3
import string
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

app = FastAPI()

DB_PATH = "urls.db"
RESERVED_CODES = {"stats", "health", "docs", "redoc", "shorten", "links"}
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,20}$")

RATE_LIMIT = 10          # 每个时间窗口内允许的最多请求数
RATE_WINDOW = 60         # 时间窗口长度（秒）
request_log = defaultdict(deque)  # IP -> 最近的请求时间戳

def check_rate_limit(ip):
    now = time.time()
    timestamps = request_log[ip]
    # 去掉窗口之外的旧记录
    while timestamps and timestamps[0] <= now - RATE_WINDOW:
        timestamps.popleft()
    if len(timestamps) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    timestamps.append(now)

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
        # 迁移：旧的数据库没有 expires_at 这一列，需要补上
        columns = [row[1] for row in conn.execute("PRAGMA table_info(urls)")]
        if "expires_at" not in columns:
            conn.execute("ALTER TABLE urls ADD COLUMN expires_at TEXT")

init_db()

class URLRequest(BaseModel):
    url: str
    custom_code: Optional[str] = None
    expires_in_days: Optional[int] = None

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
def shorten_url(body: URLRequest, request: Request):
    check_rate_limit(request.client.host)

    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    expires_at = None
    if body.expires_in_days is not None:
        if not 1 <= body.expires_in_days <= 365:
            raise HTTPException(status_code=400, detail="expires_in_days must be between 1 and 365")
        expires_at = (datetime.now() + timedelta(days=body.expires_in_days)).isoformat()

    with get_conn() as conn:
        if body.custom_code:
            code = body.custom_code
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
            "INSERT INTO urls (code, url, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (code, body.url, datetime.now().isoformat(), expires_at),
        )

    return {
        "short_code": code,
        "short_url": f"http://127.0.0.1:8000/{code}",
        "expires_at": expires_at,
    }

@app.get("/links")
def list_links():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT code, url, created_at, clicks, expires_at FROM urls ORDER BY clicks DESC"
        ).fetchall()
    return [
        {
            "short_code": row[0],
            "original_url": row[1],
            "created_at": row[2],
            "clicks": row[3],
            "expires_at": row[4],
        }
        for row in rows
    ]

@app.get("/stats/{code}")
def get_stats(code: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT code, url, created_at, clicks, expires_at FROM urls WHERE code = ?", (code,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Short link not found")
    return {
        "short_code": row[0],
        "original_url": row[1],
        "created_at": row[2],
        "clicks": row[3],
        "expires_at": row[4],
    }

@app.get("/{code}")
def redirect(code: str):
    with get_conn() as conn:
        row = conn.execute("SELECT url, expires_at FROM urls WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Short link not found")
        url, expires_at = row
        if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
            raise HTTPException(status_code=410, detail="This short link has expired")
        conn.execute("UPDATE urls SET clicks = clicks + 1 WHERE code = ?", (code,))
    return RedirectResponse(url)

@app.delete("/{code}")
def delete_link(code: str):
    with get_conn() as conn:
        if not code_exists(conn, code):
            raise HTTPException(status_code=404, detail="Short link not found")
        conn.execute("DELETE FROM urls WHERE code = ?", (code,))
    return {"message": f"Short link '{code}' deleted"}