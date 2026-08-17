from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch
from httpx import ASGITransport, AsyncClient
from testcontainers.community.elasticsearch import ElasticSearchContainer

from app.main import app, get_es_client


@pytest.fixture(scope="session")
def es_container() -> Generator[ElasticSearchContainer, None, None]:
    with ElasticSearchContainer("elasticsearch:8.15.0") as container:
        yield container


@pytest.fixture(scope="session")
def es_url(es_container: ElasticSearchContainer) -> str:
    host = es_container.get_container_host_ip()
    port = es_container.get_exposed_port(es_container.port)
    return f"http://{host}:{port}"


@pytest_asyncio.fixture
async def es_client(es_url: str) -> AsyncGenerator[AsyncElasticsearch, None]:
    client = AsyncElasticsearch(es_url)
    try:
        yield client
    finally:
        await client.close()


@pytest_asyncio.fixture
async def client(es_client: AsyncElasticsearch) -> AsyncGenerator[AsyncClient, None]:
    # Overrides the app's own ES client dependency rather than relying on
    # its lifespan (which httpx's ASGITransport doesn't trigger) — same
    # spirit as the sibling backend's app.dependency_overrides usage.
    app.dependency_overrides[get_es_client] = lambda: es_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
