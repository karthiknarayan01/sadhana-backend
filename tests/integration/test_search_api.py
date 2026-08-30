import pytest
from elasticsearch import AsyncElasticsearch
from httpx import AsyncClient

from app.config import settings
from ingest.mapping import INDEX_MAPPING

INDEX = "shlokas"  # matches Settings.es_index's default

ARGALA_DOC = {
    "id": "argala-stotram",
    "category": "stotram",
    "name": {"english": "Argala Stotram", "devanagari": "अर्गला स्तोत्रम्"},
    "content": {
        "english": "Om namaste sharvamangale shive sarvartha sadhike",
        "devanagari": "ॐ नमस्ते शर्वमङ्गले शिवे सर्वार्थ साधिके",
    },
    "meaning": {"english": "A hymn invoking the Goddess for auspiciousness and protection."},
    "source_attribution": {"text_source": "test fixture", "license": "public_domain"},
    "languages_available": ["english", "devanagari"],
}


@pytest.fixture(autouse=True)
async def seed_index(es_client: AsyncElasticsearch):
    if await es_client.indices.exists(index=INDEX):
        await es_client.indices.delete(index=INDEX)
    await es_client.indices.create(index=INDEX, **INDEX_MAPPING)
    await es_client.index(index=INDEX, id=ARGALA_DOC["id"], document=ARGALA_DOC, refresh=True)


async def test_search_matches_by_name(client: AsyncClient) -> None:
    response = await client.get("/search", params={"q": "Argala"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["id"] == "argala-stotram"


async def test_search_matches_by_content_fragment(client: AsyncClient) -> None:
    # A user may only remember body text, not the title — this is the
    # scenario that drove searching content.english too, not just name.
    response = await client.get("/search", params={"q": "sharvamangale"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["id"] == "argala-stotram"


async def test_search_response_includes_every_language_for_client_side_switching(
    client: AsyncClient,
) -> None:
    response = await client.get("/search", params={"q": "Argala"})
    result = response.json()["results"][0]
    assert set(result["languages_available"]) == {"english", "devanagari"}
    assert result["content"]["devanagari"] == ARGALA_DOC["content"]["devanagari"]
    assert result["name"]["devanagari"] == ARGALA_DOC["name"]["devanagari"]


async def test_search_response_includes_the_meaning(client: AsyncClient) -> None:
    # meaning is deliberately never searched/highlighted (see mapping.py's
    # dynamic template) but must still round-trip to the client — it's the
    # field the copyright-aware content pipeline exists to isolate, not one
    # to silently drop.
    response = await client.get("/search", params={"q": "Argala"})
    result = response.json()["results"][0]
    assert result["meaning"] == ARGALA_DOC["meaning"]


async def test_search_highlights_the_matched_fragment(client: AsyncClient) -> None:
    response = await client.get("/search", params={"q": "sharvamangale"})
    highlight = response.json()["results"][0]["highlight"]
    assert any("sharvamangale" in fragment.lower() for fragment in highlight["content"])


async def test_search_with_no_match_returns_empty_results(client: AsyncClient) -> None:
    response = await client.get("/search", params={"q": "completely unrelated gibberish xyz"})
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_requires_a_query_param(client: AsyncClient) -> None:
    response = await client.get("/search")
    assert response.status_code == 422


async def test_search_rejects_a_negative_page(client: AsyncClient) -> None:
    response = await client.get("/search", params={"q": "Argala", "page": -1})
    assert response.status_code == 422


async def _seed_many(es_client: AsyncElasticsearch, count: int) -> None:
    for i in range(count):
        doc = {
            "id": f"paginated-doc-{i}",
            "category": "stotram",
            "name": {"english": f"Paginated Doc {i}"},
            "content": {"english": "paginationfixtureterm"},
            "meaning": {},
            "source_attribution": {"text_source": "test fixture", "license": "public_domain"},
            "languages_available": ["english"],
        }
        await es_client.index(index=INDEX, id=doc["id"], document=doc)
    await es_client.indices.refresh(index=INDEX)


async def test_search_first_page_reports_has_more_when_more_exist(
    client: AsyncClient, es_client: AsyncElasticsearch
) -> None:
    await _seed_many(es_client, settings.search_page_size + 1)
    response = await client.get("/search", params={"q": "paginationfixtureterm"})
    body = response.json()
    assert len(body["results"]) == settings.search_page_size
    assert body["has_more"] is True


async def test_search_second_page_returns_the_remainder(
    client: AsyncClient, es_client: AsyncElasticsearch
) -> None:
    await _seed_many(es_client, settings.search_page_size + 1)
    first_page = await client.get("/search", params={"q": "paginationfixtureterm"})
    second_page = await client.get("/search", params={"q": "paginationfixtureterm", "page": 1})
    second_body = second_page.json()

    assert len(second_body["results"]) == 1
    assert second_body["has_more"] is False
    first_ids = {r["id"] for r in first_page.json()["results"]}
    second_ids = {r["id"] for r in second_body["results"]}
    assert first_ids.isdisjoint(second_ids)


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_cors_allows_browser_clients_from_any_origin(client: AsyncClient) -> None:
    # The Flutter *web* build calls this API from a browser tab, which
    # enforces the same-origin policy client-side — httpx has no such
    # restriction, so this only exercises the real behavior if an Origin
    # header is sent, same as a real browser fetch would send.
    response = await client.get("/search", params={"q": "Argala"}, headers={"Origin": "https://example.com"})
    assert response.headers["access-control-allow-origin"] == "*"
