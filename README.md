# URL Shortener

A URL shortening service built with FastAPI and SQLite. Create short links, track clicks, set custom codes and expiration dates, all through a REST API or a simple web interface.

## Features

- Generate random 6-character short codes, or choose a custom code
- Redirect short links to their original URLs
- Track click counts and view link statistics
- Optional link expiration (1-365 days); expired links return 410 Gone
- Input validation for URLs, custom code format, reserved words, and duplicates
- Persistent storage with SQLite, including automatic schema migration
- Web frontend for creating links and checking stats
- Automated test suite (14 tests) using isolated temporary databases

## Tech Stack

Python, FastAPI, SQLite, Pydantic, pytest

## Setup

```bash
git clone https://github.com/Jingier34/url-shortener.git
cd url-shortener
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/ for the web interface, or http://127.0.0.1:8000/docs for the interactive API docs.

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/shorten` | Create a short link. Body: `url` (required), `custom_code` (optional), `expires_in_days` (optional) |
| GET | `/{code}` | Redirect to the original URL |
| GET | `/stats/{code}` | Get the original URL, creation time, click count, and expiration |
| GET | `/health` | Health check |

### Example

```bash
curl -X POST http://127.0.0.1:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.github.com", "custom_code": "my-github", "expires_in_days": 30}'
```

## Running Tests

```bash
pytest test_main.py -v
```