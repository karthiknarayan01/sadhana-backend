from elasticsearch import AsyncElasticsearch
from elasticsearch import ConnectionError as ESConnectionError

from app.config import settings
from app.schemas import Highlight, SearchResult

# Search always happens against the English name/content fields only (the
# spec: users type in English regardless of which language they want to
# *read* results in) — the other languages on each document are returned
# unindexed, for the client to switch to locally. tags (source-provided
# deity/genre keywords, e.g. "durgA, devii, stotra" — see ingest/schema.py)
# get a middling boost: more curated-relevant than a random content match,
# but a title match is still the strongest signal something's the right
# document.
_SEARCH_FIELDS = ["name.english^3", "tags^2", "content.english"]
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
    client: AsyncElasticsearch, query: str, *, page: int = 0
) -> tuple[list[SearchResult], bool]:
    """Page size is always settings.search_page_size — page is the only
    thing the caller controls (see app/main.py's /search). Returns
    (results, has_more) rather than a bare list so the client knows
    whether to bother asking for the next page.
    """
    query = query.strip()[:MAX_QUERY_LENGTH]
    if not query:
        return [], False

    from_ = page * settings.search_page_size
    try:
        response = await client.search(
            index=settings.es_index,
            from_=from_,
            size=settings.search_page_size,
            query={
                "function_score": {
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": _SEARCH_FIELDS,
                            "type": "best_fields",
                            "fuzziness": "AUTO",
                            # Default multi_match is effectively OR across
                            # query terms — "rudra namakam" would happily
                            # rank a rudra-only or namakam-only document
                            # highly, not just ones actually about both.
                            # "2<75%": queries of 2 terms or fewer need
                            # every term to match; longer queries only need
                            # 75%, so an extra stray/misspelled word doesn't
                            # zero out an otherwise-good match.
                            "minimum_should_match": "2<75%",
                        }
                    },
                    # `priority` (see ingest/schema.py) marks entries whose
                    # name matches vignanam.org's curated prayer index — a
                    # soft relevance boost, not a filter: a strong match on
                    # a non-priority document can still outrank a weak
                    # priority match, this only tips ties and near-ties.
                    "functions": [{"filter": {"term": {"priority": True}}, "weight": 1.5}],
                    "boost_mode": "multiply",
                }
            },
            highlight={"fields": {"name.english": {}, "content.english": {}}},
        )
    except ESConnectionError as exc:
        raise SearchUnavailableError(str(exc)) from exc

    results = [_to_result(hit) for hit in response["hits"]["hits"]]
    total = response["hits"]["total"]["value"]
    has_more = from_ + len(results) < total
    return results, has_more


def _to_result(hit: dict) -> SearchResult:
    source = hit["_source"]
    highlight = hit.get("highlight", {})
    return SearchResult(
        id=hit["_id"],
        category=source["category"],
        languages_available=source["languages_available"],
        name=source["name"],
        content=source["content"],
        meaning=source.get("meaning", {}),
        highlight=Highlight(
            name=highlight.get("name.english", []),
            content=highlight.get("content.english", []),
        ),
        score=hit.get("_score") or 0.0,
    )
