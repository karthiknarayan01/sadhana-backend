"""Shared helpers for the source crawlers in ingest/crawl/ — local-only
tools you run by hand to stage scraped Sanskrit text as ShlokaEntry YAML
files under content/shlokas_staging/, for human review *before* any of it
reaches ingest/run.py's validate+index step. See ingest/crawl/run.py.
"""

import re
import time
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from indic_transliteration import sanscript

from ingest.schema import ShlokaEntry

DEVANAGARI_RUN = re.compile(r"[ऀ-ॿ][ऀ-ॿ\s]*[ऀ-ॿ]")
MIN_RUN_LENGTH = 20

# IAST -> a plain-ASCII phonetic rendering, matching the style already used
# by hand-written entries in content/shlokas/ (e.g. "aham brahmasmi", not
# "ahaṃ brahmāsmi"). The ES analyzer asciifolds at search time regardless
# (see ingest/mapping.py), so this is about matching the existing dataset's
# look, not search correctness.
_DIACRITIC_FOLD = {
    "ā": "a", "ī": "i", "ū": "u", "ṛ": "ri", "ṝ": "ri", "ḷ": "li", "ḹ": "li",
    "ṃ": "m", "ṁ": "m", "ḥ": "h", "ṅ": "n", "ñ": "n", "ṇ": "n",
    "ṭ": "t", "ḍ": "d", "ś": "sh", "ṣ": "sh", "’": "",
}


def to_plain_english(devanagari_text: str) -> str:
    """Devanagari -> phonetic, diacritic-free Roman text — a mechanical
    transliteration (same sounds, different alphabet), not a translation.
    Deliberately does not attempt to render meaning.
    """
    iast = sanscript.transliterate(devanagari_text, sanscript.DEVANAGARI, sanscript.IAST)
    for src, dst in _DIACRITIC_FOLD.items():
        iast = iast.replace(src, dst).replace(src.upper(), dst.capitalize())
    return re.sub(r"\s+", " ", iast).strip()


def build_name(title_devanagari: str, title_raw: str) -> dict[str, str]:
    """title_devanagari may be empty or a failed ITRANS->Devanagari guess
    (sanskritdocuments.org link text isn't always clean ITRANS) — fall back
    to the raw title as `english` only, which still satisfies the schema.
    """
    if title_devanagari and any("ऀ" <= ch <= "ॿ" for ch in title_devanagari):
        return {"english": to_plain_english(title_devanagari), "devanagari": title_devanagari}
    return {"english": re.sub(r"\s+", " ", title_raw).strip()}


def slugify(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def largest_devanagari_run(html: str) -> str | None:
    """Pulls the single largest contiguous block of Devanagari-script text
    out of a page's rendered HTML. This is the mechanism that keeps English
    prose (translations, editorial notes, site navigation) out of what gets
    staged — it structurally cannot select non-Devanagari text.
    """
    text = BeautifulSoup(html, "html.parser").get_text(" ")
    runs = [re.sub(r"\s+", " ", m.group()).strip() for m in DEVANAGARI_RUN.finditer(text)]
    runs = [r for r in runs if len(r) >= MIN_RUN_LENGTH]
    return max(runs, key=len) if runs else None


class PoliteSession:
    """A requests.Session that identifies itself honestly (not spoofed as a
    browser, and not as ClaudeBot/anthropic-ai — this script runs as your
    own process, under your own network identity, not Anthropic's) and
    enforces a minimum delay between requests.
    """

    def __init__(self, contact_email: str, delay_seconds: float = 1.0):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            f"SadhanaShlokaCrawler/1.0 (personal, non-commercial project; contact: {contact_email})"
        )
        self._delay = delay_seconds
        self._last_request = 0.0

    def get(self, url: str, **kwargs) -> requests.Response:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        response = self._session.get(url, timeout=30, **kwargs)
        self._last_request = time.monotonic()
        response.raise_for_status()
        return response


def write_entry(entry: ShlokaEntry, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{entry.id}.yaml"
    path.write_text(
        yaml.safe_dump(
            entry.model_dump(exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
    )
    return path
