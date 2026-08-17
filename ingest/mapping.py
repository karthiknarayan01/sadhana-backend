"""Elasticsearch index mapping for the shlokas index.

Only name.english and content.english are indexed/analyzed — search always
happens in English regardless of display language (see app/es_client.py).
Every other language field is `index: false` (still returned in `_source`,
just excluded from search) via a dynamic template, so a new language never
needs a mapping change here.

The custom analyzer folds diacritics (asciifolding, so "sri" matches "śrī" —
IAST transliteration is full of them) and deliberately has no English
stemmer, which would mangle Sanskrit-derived terms.
"""

INDEX_MAPPING = {
    "settings": {
        "analysis": {
            "analyzer": {
                "sanskrit_english": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"],
                }
            }
        }
    },
    "mappings": {
        "dynamic_templates": [
            {
                "non_english_localized_text": {
                    "path_match": "*.*",
                    "path_unmatch": ["name.english", "content.english"],
                    "match_mapping_type": "string",
                    "mapping": {"type": "text", "index": False},
                }
            }
        ],
        "properties": {
            "id": {"type": "keyword"},
            "category": {"type": "keyword"},
            "languages_available": {"type": "keyword"},
            "source_attribution": {
                "properties": {
                    "text_source": {"type": "keyword", "index": False},
                    "translation_source": {"type": "keyword", "index": False},
                    "license": {"type": "keyword"},
                }
            },
            "name": {
                "properties": {
                    "english": {"type": "text", "analyzer": "sanskrit_english"},
                }
            },
            "content": {
                "properties": {
                    "english": {"type": "text", "analyzer": "sanskrit_english"},
                }
            },
        },
    },
}
