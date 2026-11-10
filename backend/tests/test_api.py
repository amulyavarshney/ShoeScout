import uuid


async def test_session_and_typed_search(client):
    r = await client.post("/api/v1/sessions", json={})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert r.json()["mode"] == "mock"  # T15
    r = await client.post(f"/api/v1/sessions/{sid}/messages", json={"text": "red shoes", "turn_id": str(uuid.uuid4())})
    assert r.status_code == 200
    body = r.json()
    assert body["is_demo"] is True and 3 <= len(body["products"]) <= 5
    assert all(p["in_stock"] for p in body["products"])


async def test_error_envelope(client):
    r = await client.post("/api/v1/sessions/nope/messages", json={"text": "x", "turn_id": "t"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "SESSION_NOT_FOUND"


async def test_product_search_and_detail(client):
    r = await client.get("/api/v1/products/search", params={"brand": "Nike", "color": "red"})
    assert r.status_code == 200 and r.json()["route"] == "attribute"
    pid = r.json()["products"][0]["product_id"]
    d = await client.get(f"/api/v1/products/{pid}")
    assert d.status_code == 200 and d.json()["colorways"]
    vid = d.json()["colorways"][0]["variants"][0]["variant_id"]
    a = await client.get(f"/api/v1/variants/{vid}/availability")
    assert a.status_code == 200 and a.json()["location_known"] is False
    assert all(s["distance_km"] is None for s in a.json()["stores"])


async def test_admin_requires_auth_and_keys_are_masked(client):
    assert (await client.get("/api/v1/admin/providers")).status_code == 401
    r = await client.post("/api/v1/admin/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    r = await client.post("/api/v1/admin/login", json={"username": "admin", "password": "test-password-123"})
    assert r.status_code == 200
    csrf = r.json()["csrf"]
    # CSRF required on mutations
    r = await client.put("/api/v1/admin/providers/openai/key", json={"api_key": "sk-test-secret-key-0123456789abcdef"})
    assert r.status_code == 403
    secret = "sk-test-secret-key-0123456789abcdef"
    r = await client.put("/api/v1/admin/providers/openai/key", json={"api_key": secret}, headers={"x-csrf-token": csrf})
    assert r.status_code == 200
    body = r.text
    assert secret not in body and r.json()["last4"] == "cdef" and r.json()["source"] == "settings"  # T16
    r = await client.get("/api/v1/admin/providers")
    assert secret not in r.text
    # encrypted at rest
    from sqlalchemy import select

    from app.db import ProviderCredential, get_sessionmaker
    async with get_sessionmaker()() as db:
        cred = (await db.execute(select(ProviderCredential).where(ProviderCredential.provider == "openai"))).scalar_one()
        assert secret not in cred.ciphertext
    # settings version bumps on key change (T17)
    v1 = (await client.get("/api/v1/admin/settings")).json()["config_version"]
    r = await client.delete("/api/v1/admin/providers/openai/key", headers={"x-csrf-token": csrf})
    assert r.status_code == 204
    v2 = (await client.get("/api/v1/admin/settings")).json()["config_version"]
    assert v2 > v1
    # shopper-facing config never includes keys
    pub = await client.get("/api/v1/config/public")
    assert "key" not in pub.text.lower() or "api_key" not in pub.text


async def test_location_consent_and_privacy(client):
    r = await client.post("/api/v1/sessions", json={})
    sid = r.json()["session_id"]
    r = await client.post(f"/api/v1/sessions/{sid}/location/consent", json={"postcode": "ZZ99 9ZZ"})
    assert r.status_code == 422
    r = await client.post(f"/api/v1/sessions/{sid}/location/consent", json={"latitude": 51.5, "longitude": -0.1})
    assert r.status_code == 200 and r.json()["location_token"].startswith("loc_")
    s = await client.get(f"/api/v1/sessions/{sid}")
    assert s.json()["location_known"] is True and "51.5" not in s.text
