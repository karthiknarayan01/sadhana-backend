import pytest
from elasticsearch import AsyncElasticsearch
from httpx import AsyncClient

from app.analytics import USAGE_EVENTS_INDEX


@pytest.fixture(autouse=True)
async def clean_usage_index(es_client: AsyncElasticsearch):
    if await es_client.indices.exists(index=USAGE_EVENTS_INDEX):
        await es_client.indices.delete(index=USAGE_EVENTS_INDEX)


async def test_events_are_recorded(client: AsyncClient, es_client: AsyncElasticsearch) -> None:
    response = await client.post(
        "/events",
        json={
            "events": [
                {"event": "feature_time", "feature": "meditate", "seconds": 185},
                {"event": "search_performed"},
            ]
        },
    )
    assert response.status_code == 202

    await es_client.indices.refresh(index=USAGE_EVENTS_INDEX)
    docs = await es_client.search(index=USAGE_EVENTS_INDEX, size=10)
    sources = [hit["_source"] for hit in docs["hits"]["hits"]]

    assert len(sources) == 2
    feature_time = next(s for s in sources if s["event"] == "feature_time")
    assert feature_time["feature"] == "meditate"
    assert feature_time["seconds"] == 185
    assert "received_at" in feature_time

    search_event = next(s for s in sources if s["event"] == "search_performed")
    assert search_event["feature"] is None


async def test_an_empty_batch_is_a_no_op(client: AsyncClient) -> None:
    response = await client.post("/events", json={"events": []})
    assert response.status_code == 202


async def test_an_unknown_event_type_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/events", json={"events": [{"event": "not_a_real_event"}]})
    assert response.status_code == 422
