import random
import string

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

app = FastAPI()

url_store = {}

class URLRequest(BaseModel):
    url: str

def generate_code(length=6):
    chars = string.ascii_letters + string.digits
    while True:
        code = "".join(random.choices(chars, k=length))
        if code not in url_store:
            return code

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/shorten")
def shorten_url(request: URLRequest):
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    code = generate_code()
    url_store[code] = request.url
    return {"short_code": code, "short_url": f"http://127.0.0.1:8000/{code}"}

@app.get("/{code}")
def redirect(code: str):
    if code not in url_store:
        raise HTTPException(status_code=404, detail="Short link not found")
    return RedirectResponse(url_store[code])