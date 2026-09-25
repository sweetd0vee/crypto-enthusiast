from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_healthz_ok(monkeypatch) -> None:
    async def ok() -> None:
        return None

    monkeypatch.setattr("app.main.ping_db", ok)
    monkeypatch.setattr("app.main.ping_redis", ok)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthz_unavailable_when_store_fails(monkeypatch) -> None:
    async def fail() -> None:
        raise ConnectionError("down")

    async def ok() -> None:
        return None

    monkeypatch.setattr("app.main.ping_db", fail)
    monkeypatch.setattr("app.main.ping_redis", ok)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 503
    assert response.json()["error"] == "unavailable"
