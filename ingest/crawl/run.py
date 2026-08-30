"""Local-only CLI — run by hand from your own machine (never deployed, never
run by anything Anthropic-operated). Crawls a public-domain Sanskrit source
and stages the results as ShlokaEntry YAML files for human review, *before*
any of it reaches ingest/run.py's validate+index step. Never talks to
Elasticsearch directly and never writes into content/shlokas/ directly —
see content/shlokas_staging/.

Deliberately source-agnostic and capped per run (see --max-entries): project
policy is not to bulk-scrape any single site (see README's "Content
sourcing"), so this is meant to be run a few times against different
sources for modest amounts each, not once against one site for everything
it has. vignanam.org is deliberately not a supported --source — its
robots.txt explicitly disallows ClaudeBot/anthropic-ai.

Only the Sanskrit (content.devanagari) is ever read from the source;
content.english is produced locally via mechanical transliteration
(to_plain_english in common.py) — same sounds, different alphabet, not a
translation. meaning.* is always left empty; add it by hand afterwards if
you want one, same as every hand-written entry in content/shlokas/.

Examples:

    uv run python -m ingest.crawl.run --source wikisource \\
        --category स्तोत्राणि --category-label stotram \\
        --max-entries 30 --contact-email you@example.com

    uv run python -m ingest.crawl.run --source sanskritdocuments \\
        --category-path /sanskrit/stotra/ --category-label stotram \\
        --max-entries 30 --contact-email you@example.com

After it finishes: check a few files in content/shlokas_staging/ — that
content.devanagari is real verse text (not a scraped nav fragment) and
content.english reads as sensible phonetic transliteration — then move the
ones you want into content/shlokas/ and run ingest/run.py as usual.
"""

import argparse
import sys
from pathlib import Path

from ingest.crawl import sanskritdocuments_source, wikisource_source
from ingest.crawl.common import PoliteSession, build_name, slugify, to_plain_english, write_entry
from ingest.schema import ShlokaEntry, SourceAttribution


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", choices=["wikisource", "sanskritdocuments"], required=True)
    parser.add_argument("--category", help="Wikisource category name, e.g. स्तोत्राणि (no 'Category:' prefix)")
    parser.add_argument("--category-path", help="sanskritdocuments.org index path, e.g. /sanskrit/stotra/")
    parser.add_argument("--category-label", required=True, help="Value for the entry's `category` field")
    parser.add_argument(
        "--max-entries", type=int, default=30, help="Cap per run — keep this modest (default: 30)"
    )
    parser.add_argument("--out-dir", type=Path, default=Path("content/shlokas_staging"))
    parser.add_argument(
        "--contact-email", required=True, help="Sent in the User-Agent header, per each site's own etiquette"
    )
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    args = parser.parse_args()

    session = PoliteSession(args.contact_email, args.delay_seconds)

    if args.source == "wikisource":
        if not args.category:
            parser.error("--source wikisource requires --category")
        records = wikisource_source.crawl(session, args.category, args.max_entries)
    else:
        if not args.category_path:
            parser.error("--source sanskritdocuments requires --category-path")
        records = sanskritdocuments_source.crawl(session, args.category_path, args.max_entries)

    written = 0
    skipped = 0
    # Seeded from whatever's already in --out-dir, not just this invocation's
    # own records — a crawl script that runs this CLI once per category (see
    # ingest/crawl/README or the shell scripts that drive it) would otherwise
    # have each invocation's collision-avoidance blind to every other
    # invocation's output, letting two categories silently overwrite each
    # other's same-titled entry via the final `mv` into content/shlokas/.
    args.out_dir.mkdir(parents=True, exist_ok=True)
    seen_ids: set[str] = {p.stem for p in args.out_dir.glob("*.yaml")}

    for record in records:
        name = build_name(record["title_devanagari"], record["title_raw"])
        base_id = slugify(name["english"]) or "entry"
        entry_id, suffix = base_id, 2
        while entry_id in seen_ids:
            entry_id = f"{base_id}-{suffix}"
            suffix += 1
        seen_ids.add(entry_id)

        try:
            entry = ShlokaEntry(
                id=entry_id,
                category=args.category_label,
                name=name,
                content={
                    "english": to_plain_english(record["content_devanagari"]),
                    "devanagari": record["content_devanagari"],
                },
                meaning={},
                source_attribution=SourceAttribution(
                    text_source=f"{record['text_source_label']} — {record['source_url']}",
                    translation_source=None,
                    license="public_domain",
                ),
            )
        except Exception as exc:  # noqa: BLE001 - one bad record shouldn't kill the whole run
            print(f"skip {entry_id}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        path = write_entry(entry, args.out_dir)
        print(f"staged {path}")
        written += 1

    print(f"\n{written} staged in {args.out_dir}, {skipped} skipped.")
    print("Review before merging into content/shlokas/, then run ingest/run.py as usual.")


if __name__ == "__main__":
    main()
