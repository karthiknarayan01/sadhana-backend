from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from ingest.mapping import INDEX_MAPPING
from ingest.schema import ShlokaEntry


def ensure_index(client: Elasticsearch, index: str) -> None:
    if not client.indices.exists(index=index):
        client.indices.create(index=index, **INDEX_MAPPING)


def index_entries(client: Elasticsearch, index: str, entries: list[ShlokaEntry]) -> int:
    # _id = the entry's own slug, so re-running ingestion after editing a
    # YAML file upserts rather than duplicates.
    actions = (
        {"_index": index, "_id": entry.id, "_source": entry.to_es_document()}
        for entry in entries
    )
    success, _errors = bulk(client, actions)
    return success
