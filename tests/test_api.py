from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_travel_design_draft() -> None:
    response = client.post(
        "/ai/travel-design/draft",
        json={
            "region_id": 10,
            "region_name": "공주",
            "days": 2,
            "budget": 300000,
            "people_count": 2,
            "companion_type": "FRIEND",
            "style_tags": ["힐링", "역사"],
            "local_contribution_enabled": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan_summary"]["region_name"] == "공주"
    assert len(body["itinerary_days"]) == 2


def test_travel_design_schema_endpoints() -> None:
    request_schema = client.get("/schemas/travel-design/request")
    response_schema = client.get("/schemas/travel-design/response")

    assert request_schema.status_code == 200
    assert response_schema.status_code == 200
    assert request_schema.json()["title"] == "TravelDesignRequest"
    assert response_schema.json()["title"] == "TravelDesignResponse"
