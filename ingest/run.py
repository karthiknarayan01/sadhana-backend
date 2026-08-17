"""Local-only CLI — validates and indexes shloka content into Elasticsearch.
Never deployed; run by hand from a developer machine.

    uv run python -m ingest.run --content-dir content/shlokas --dry-run
    uv run python -m ingest.run --content-dir content/shlokas --es-host http://localhost:9200
"""

import argparse
import sys
from pathlib import Path

from elasticsearch import Elasticsearch

from ingest.indexer import ensure_index, index_entries
from ingest.loader import ContentValidationError, load_content_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-dir", type=Path, default=Path("content/shlokas"))
    parser.add_argument("--es-host", default="http://localhost:9200")
    parser.add_argument("--es-api-key", default=None)
    parser.add_argument("--index", default="shlokas")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the content directory only; don't touch Elasticsearch.",
    )
    args = parser.parse_args()

    try:
        entries = load_content_dir(args.content_dir)
    except ContentValidationError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    print(f"Validated {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}.")

    if args.dry_run:
        return

    client = Elasticsearch(args.es_host, api_key=args.es_api_key)
    ensure_index(client, args.index)
    count = index_entries(client, args.index, entries)
    print(f"Indexed {count} document(s) into '{args.index}'.")


if __name__ == "__main__":
    main()
