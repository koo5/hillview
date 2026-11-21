"""Search contract without a database or a live geocoder."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import places_routes

app = FastAPI()
app.include_router(places_routes.router)

PLACE = {
    "place_id": 42, "name": "Praha", "display_name": "Praha, Česko",
    "lat": "50.0875", "lon": "14.4213",
    "boundingbox": ["49.94", "50.18", "14.22", "14.71"],
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NOMINATIM_URL", "https://geocoder.example/osm/")
    with patch.object(places_routes.general_rate_limiter, "enforce_rate_limit", new=AsyncMock()):
        yield TestClient(app)


@pytest.fixture
def geocoder():
    with patch.object(places_routes.httpx, "AsyncClient") as factory:
        mock = factory.return_value.__aenter__.return_value
        mock.get = AsyncMock(return_value=httpx.Response(
            200, json=[PLACE], request=httpx.Request("GET", "https://geocoder.example/osm/search"),
        ))
        yield mock


def test_search_uses_configured_geocoder_and_normalizes_results(client, geocoder):
    response = client.get("/api/places/search", params={"q": " Praha "})
    assert response.status_code == 200
    assert response.json() == [{
        "id": "42", "name": "Praha", "display_name": "Praha, Česko",
        "lat": 50.0875, "lon": 14.4213, "bounds": [49.94, 50.18, 14.22, 14.71],
    }]
    args, kwargs = geocoder.get.call_args
    assert args == ("https://geocoder.example/osm/search",)
    assert kwargs["params"] == {"q": "Praha", "format": "jsonv2", "limit": 10}
    assert "hillview" in kwargs["headers"]["User-Agent"]
    assert response.headers["cache-control"] == "public, max-age=300"


@pytest.mark.parametrize("query", ["", "a", "   ", "x" * 201])
def test_rejects_short_or_excessive_query_before_calling_geocoder(client, geocoder, query):
    assert client.get("/api/places/search", params={"q": query}).status_code == 422
    geocoder.get.assert_not_called()


@pytest.mark.parametrize("bounds", [None, [], ["NaN", 50, 14, 15], [51, 50, 14, 15]])
def test_bad_or_missing_extent_keeps_point_result(client, geocoder, bounds):
    geocoder.get.return_value = httpx.Response(
        200, json=[{**PLACE, "name": "", "boundingbox": bounds}],
        request=httpx.Request("GET", "https://geocoder.example/search"),
    )
    result = client.get("/api/places/search", params={"q": "Praha"}).json()[0]
    assert result["name"] == "Praha"
    assert result["bounds"] is None


@pytest.mark.parametrize("data", [{"error": "bad query"}, [None], [{**PLACE, "lat": "NaN"}], [{**PLACE, "lon": "181"}]])
def test_invalid_upstream_result_is_a_gateway_error(client, geocoder, data):
    geocoder.get.return_value = httpx.Response(
        200, json=data, request=httpx.Request("GET", "https://geocoder.example/search"),
    )
    assert client.get("/api/places/search", params={"q": "Praha"}).status_code == 502


@pytest.mark.parametrize("failure, status", [
    (httpx.ReadTimeout("slow"), 504),
    (httpx.ConnectError("unavailable"), 502),
])
def test_upstream_failure_is_retryable_error(client, geocoder, failure, status):
    geocoder.get.side_effect = failure
    response = client.get("/api/places/search", params={"q": "Praha"})
    assert response.status_code == status
    assert "cache-control" not in response.headers


def test_empty_results_are_successful(client, geocoder):
    geocoder.get.return_value = httpx.Response(
        200, json=[], request=httpx.Request("GET", "https://geocoder.example/search"),
    )
    assert client.get("/api/places/search", params={"q": "nowhere"}).json() == []
