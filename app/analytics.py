"""Records anonymous usage events — see app/schemas.py's UsageEvent.

Fire-and-forget by design, both here and on the client (see sadhana-app's
analytics_service.dart): a lost or failed batch just slightly undercounts a
chart nobody's staring at in real time, so this never raises past
app/main.py's /events handler, which always reports success to the app
regardless of whether the write actually landed.
"""

from datetime import UTC, datetime

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.analytics_mapping import USAGE_EVENTS_MAPPING
from app.schemas import UsageEvent

USAGE_EVENTS_INDEX = "usage_events"


async def ensure_usage_index(client: AsyncElasticsearch) -> None:
    if not await client.indices.exists(index=USAGE_EVENTS_INDEX):
        await client.indices.create(index=USAGE_EVENTS_INDEX, **USAGE_EVENTS_MAPPING)


async def record_events(client: AsyncElasticsearch, events: list[UsageEvent]) -> None:
    if not events:
        return
    await ensure_usage_index(client)
    received_at = datetime.now(UTC).isoformat()
    actions = (
        {"_index": USAGE_EVENTS_INDEX, "_source": {**event.model_dump(), "received_at": received_at}}
        for event in events
    )
    await async_bulk(client, actions)
