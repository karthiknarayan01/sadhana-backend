from elasticsearch import AsyncElasticsearch
from elasticsearch import ConnectionError as ESConnectionError

from app.config import settings
from app.schemas import Highlight, SearchResult

# Search always happens against the English name/content fields only (the
# spec: users type in English regardless of which language they want to
# *read* results in) — the other languages on each document are returned
# unindexed, for the client to switch to locally. See ingest/schema.py for
# the document shape this query assumes.
_SEARCH_FIELDS = ["name.english^3", "content.english"]
MAX_QUERY_LENGTH = 200


class SearchUnavailableError(Exception):
    """Raised when Elasticsearch itself can't be reached — translated to a
    503 at the API layer (see main.py), not a 500: this is the backing
    store being down, not a bug in this service.
    """


def build_client() -> AsyncElasticsearch:
    return AsyncElasticsearch(
        settings.es_host,
        api_key=settings.es_api_key,
    )


async def search_shlokas(
    client: AsyncElasticsearch, query: str, *, size: int = 10
) -> list[SearchResult]:
    query = query.strip()[:MAX_QUERY_LENGTH]
    if not query:
        return []

    try:
        response = await client.search(
            index=settings.es_index,
            size=size,
            query={
                "multi_match": {
                    "query": query,
                    "fields": _SEARCH_FIELDS,
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            highlight={"fields": {"name.english": {}, "content.english": {}}},
        )
    except ESConnectionError as exc:
        raise SearchUnavailableError(str(exc)) from exc

    return [_to_result(hit) for hit in response["hits"]["hits"]]


def _to_result(hit: dict) -> SearchResult:
    source = hit["_source"]
    highlight = hit.get("highlight", {})
    return SearchResult(
        id=hit["_id"],
        category=source["category"],
        languages_available=source["languages_available"],
        name=source["name"],
        content=source["content"],
        highlight=Highlight(
            name=highlight.get("name.english", []),
            content=highlight.get("content.english", []),
        ),
        score=hit.get("_score") or 0.0,
    )
