from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app.es_client import SearchUnavailableError, build_client, search_shlokas
from app.schemas import SearchResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One client for the app's lifetime, not one per request — the
    # underlying elastic_transport connection pool is meant to be reused.
    app.state.es_client = build_client()
    try:
        yield
    finally:
        await app.state.es_client.close()


app = FastAPI(title="Sadhana Search API", lifespan=lifespan)


def get_es_client(request: Request) -> AsyncElasticsearch:
    return request.app.state.es_client


@app.exception_handler(SearchUnavailableError)
async def search_unavailable_handler(
    request: Request, exc: SearchUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=503, content={"detail": "search is temporarily unavailable"}
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    client: AsyncElasticsearch = Depends(get_es_client),
) -> SearchResponse:
    results = await search_shlokas(client, q)
    return SearchResponse(results=results)
