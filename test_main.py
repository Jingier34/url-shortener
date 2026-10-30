import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 每个测试用一个临时的空数据库，不影响真实的 urls.db
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "test.db"))
    main.init_db()
    main.request_log.clear()
    return TestClient(main.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_shorten_generates_random_code(client):
    response = client.post("/shorten", json={"url": "https://www.google.com"})
    assert response.status_code == 200
    assert len(response.json()["short_code"]) == 6


def test_shorten_rejects_invalid_url(client):
    response = client.post("/shorten", json={"url": "google.com"})
    assert response.status_code == 400


def test_redirect(client):
    code = client.post("/shorten", json={"url": "https://www.google.com"}).json()["short_code"]
    response = client.get(f"/{code}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://www.google.com"


def test_redirect_unknown_code(client):
    response = client.get("/abc123", follow_redirects=False)
    assert response.status_code == 404


def test_click_counting(client):
    code = client.post("/shorten", json={"url": "https://www.google.com"}).json()["short_code"]
    for _ in range(3):
        client.get(f"/{code}", follow_redirects=False)
    stats = client.get(f"/stats/{code}").json()
    assert stats["clicks"] == 3


def test_stats_unknown_code(client):
    response = client.get("/stats/abc123")
    assert response.status_code == 404


def test_custom_code(client):
    response = client.post("/shorten", json={"url": "https://www.github.com", "custom_code": "my-github"})
    assert response.status_code == 200
    assert response.json()["short_code"] == "my-github"


def test_custom_code_duplicate(client):
    payload = {"url": "https://www.github.com", "custom_code": "my-github"}
    client.post("/shorten", json=payload)
    response = client.post("/shorten", json=payload)
    assert response.status_code == 409


def test_custom_code_invalid_format(client):
    response = client.post("/shorten", json={"url": "https://www.github.com", "custom_code": "a b"})
    assert response.status_code == 400


def test_custom_code_reserved(client):
    response = client.post("/shorten", json={"url": "https://www.github.com", "custom_code": "stats"})
    assert response.status_code == 400


def test_expiration_is_set(client):
    response = client.post("/shorten", json={"url": "https://www.google.com", "expires_in_days": 7})
    assert response.status_code == 200
    assert response.json()["expires_at"] is not None


def test_expired_link_returns_410(client):
    code = client.post("/shorten", json={"url": "https://www.google.com", "expires_in_days": 1}).json()["short_code"]
    # 直接把过期时间改成过去，模拟链接已经过期
    with main.get_conn() as conn:
        conn.execute("UPDATE urls SET expires_at = ? WHERE code = ?", ("2020-01-01T00:00:00", code))
    response = client.get(f"/{code}", follow_redirects=False)
    assert response.status_code == 410


def test_invalid_expiration_days(client):
    response = client.post("/shorten", json={"url": "https://www.google.com", "expires_in_days": 0})
    assert response.status_code == 400


def test_delete_link(client):
    code = client.post("/shorten", json={"url": "https://www.google.com"}).json()["short_code"]
    response = client.delete(f"/{code}")
    assert response.status_code == 200
    assert client.get(f"/{code}", follow_redirects=False).status_code == 404


def test_delete_unknown_link(client):
    response = client.delete("/abc123")
    assert response.status_code == 404


def test_list_links_sorted_by_clicks(client):
    code_a = client.post("/shorten", json={"url": "https://www.google.com"}).json()["short_code"]
    code_b = client.post("/shorten", json={"url": "https://www.github.com"}).json()["short_code"]
    for _ in range(2):
        client.get(f"/{code_b}", follow_redirects=False)
    links = client.get("/links").json()
    assert len(links) == 2
    assert links[0]["short_code"] == code_b
    assert links[1]["short_code"] == code_a


def test_list_links_empty(client):
    response = client.get("/links")
    assert response.status_code == 200
    assert response.json() == []


def test_rate_limit(client):
    for _ in range(main.RATE_LIMIT):
        response = client.post("/shorten", json={"url": "https://www.google.com"})
        assert response.status_code == 200
    response = client.post("/shorten", json={"url": "https://www.google.com"})
    assert response.status_code == 429