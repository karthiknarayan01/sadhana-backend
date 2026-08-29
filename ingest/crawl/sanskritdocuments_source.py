"""sanskritdocuments.org adapter. Its per-document pages under /doc_*/ are
Devanagari-only with no on-page English translation (confirmed by fetching
a sample page before writing this — unlike vignanam.org's paired
Sanskrit+translation layout), so a plain Devanagari-run extraction is enough
to guarantee no translation prose ever gets pulled in. Index-page link text
is in a loose ITRANS-like scheme rather than Devanagari or plain English
(e.g. "akhilANDeshvarIstotram"), so titles get a best-effort ITRANS ->
Devanagari pass; see common.build_name for the fallback when that fails.
"""

import re
import sys
from collections.abc import Iterator
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from indic_transliteration import sanscript

from ingest.crawl.common import PoliteSession, largest_devanagari_run

BASE_URL = "https://sanskritdocuments.org"

# Generic index-page links (alternate-format/"plain text" mirrors, itx
# downloads, etc.) that match the /doc_*.html link pattern but aren't a
# stotra's own title — e.g. a "text" link next to a document's real entry.
_NON_TITLE_LINK_TEXT = {"text", "txt", "itx", "pdf", "here", "html", "link"}


def _is_junk_title(text: str) -> bool:
    """Some index entries' visible link text is just a footnote/version
    marker (e.g. "1", "2") rather than the document's actual title — the
    real title lives only in the URL in those cases.
    """
    return len(text.strip()) < 3 or not re.search(r"[a-zA-Z]", text)


def _title_from_url(url: str) -> str:
    # Not camelCase-split: ITRANS itself uses capitals mid-word constantly
    # (e.g. "uchChiShTa"), so splitting on case would shred real titles —
    # just clean up the filename, don't try to re-segment it.
    stem = url.rsplit("/", 1)[-1].removesuffix(".html")
    return re.sub(r"(?<=[a-zA-Z])(\d+)$", r" \1", stem.replace("_", " ")).strip()


def list_category_docs(session: PoliteSession, category_path: str, limit: int) -> list[tuple[str, str]]:
    index_url = urljoin(BASE_URL, category_path)
    html = session.get(index_url).text
    soup = BeautifulSoup(html, "html.parser")
    docs: list[tuple[str, str]] = []
    for a in soup.select("a[href]"):
        href = a["href"]
        text = a.get_text(strip=True)
        if href.endswith(".html") and "/doc_" in href and text.lower() not in _NON_TITLE_LINK_TEXT:
            docs.append((text, urljoin(BASE_URL, href)))
        if len(docs) >= limit:
            break
    return docs


def fetch_devanagari(session: PoliteSession, doc_url: str) -> str | None:
    try:
        html = session.get(doc_url).text
    except requests.RequestException as exc:
        print(f"skip {doc_url}: {exc}", file=sys.stderr)
        return None
    return largest_devanagari_run(html)


def crawl(session: PoliteSession, category_path: str, limit: int) -> Iterator[dict]:
    for title_raw, url in list_category_docs(session, category_path, limit):
        content = fetch_devanagari(session, url)
        if content is None:
            continue
        if _is_junk_title(title_raw):
            title_raw = _title_from_url(url)
        try:
            title_devanagari = sanscript.transliterate(title_raw, sanscript.ITRANS, sanscript.DEVANAGARI)
        except Exception:
            title_devanagari = ""
        yield {
            "title_devanagari": title_devanagari,
            "title_raw": title_raw,
            "content_devanagari": content,
            "source_url": url,
            "text_source_label": "sanskritdocuments.org",
        }
