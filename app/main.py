from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
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

# Elasticsearch refuses from+size beyond index.max_result_window (default
# 10,000) with a 400, rather than just returning nothing — bounding `page`
# here means a stray/malicious page number gets a clean 422 from FastAPI's
# own validation instead of an ES error leaking through.
_MAX_PAGE = (10_000 // settings.search_page_size) - 1

# Wildcard is safe here specifically because this endpoint takes no
# credentials/cookies and returns nothing user-specific — a public,
# read-only search API with no per-caller state to leak. Without this, the
# Flutter *web* build's browser fetch calls are silently blocked by the
# browser's same-origin policy (Android/iOS are unaffected — CORS is a
# browser-only mechanism, invisible on native).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


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
    page: int = Query(0, ge=0, le=_MAX_PAGE),
    client: AsyncElasticsearch = Depends(get_es_client),
) -> SearchResponse:
    results, has_more = await search_shlokas(client, q, page=page)
    return SearchResponse(results=results, has_more=has_more)
