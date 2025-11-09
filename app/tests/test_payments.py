from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_payment():
    resp = client.post("/payments", json={"amount_cents": 1000, "currency": "USD"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount_cents"] == 1000
    assert "id" in data
