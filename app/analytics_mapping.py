"""Elasticsearch index mapping for usage_events — anonymous, aggregate-only
app usage data (see app/schemas.py's UsageEvent). No user/device identifier
of any kind is ever stored here, by design — there's nothing here to key a
mapping change around beyond the event's own shape.
"""

USAGE_EVENTS_MAPPING = {
    "mappings": {
        "properties": {
            "event": {"type": "keyword"},
            "feature": {"type": "keyword"},
            "seconds": {"type": "integer"},
            # Server-assigned at write time (see app/analytics.py), not
            # client-supplied — a phone's clock isn't trustworthy enough to
            # aggregate "requests per day" against.
            "received_at": {"type": "date"},
        }
    }
}
