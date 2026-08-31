"""sanskritdocuments.org adapter. Reads each document's .itx source file
(linked from its .html page, same path with the extension swapped) rather
than scraping the rendered HTML page.

This matters for two reasons, found by comparing the two: the HTML page
routinely splits a single stotra's text across several disconnected
Devanagari runs (per-verse <p>/<span> wrapping, footnote markers), and an
earlier version of this crawler that kept only the largest such run was
silently dropping real verses — confirmed on Durga Suktam, which started at
verse 5 with the first four missing, and found to be routine: ~95% of a
150-entry sample had more than one run. The .itx file has no such
fragmentation. It also carries a structured header (title, category tags,
attribution) that the rendered page doesn't expose at all — see
`% Category` in a sample file, which becomes this adapter's `tags`.

.itx documents are ITRANS-encoded plain text wrapped in a thin, fairly
consistent LaTeX-like markup (a fixed preamble before \\begin{document}, a
handful of formatting macros inside, a near-constant attribution footer).
_parse_itx strips that; see its docstring for what it does and does not
handle — it is not a full LaTeX parser, and rare documents that mix English
editorial prose into the body (rather than keeping it in the footer) will
carry a little of that prose through. That's a known, accepted trade-off:
still far more complete than the HTML-scraping approach it replaces.
"""

import re
import sys
from collections.abc import Iterator
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from indic_transliteration import sanscript

from ingest.crawl.common import PoliteSession

BASE_URL = "https://sanskritdocuments.org"

# Generic index-page links (alternate-format/"plain text" mirrors, itx
# downloads, etc.) that match the /doc_*.html link pattern but aren't a
# stotra's own title — e.g. a "text" link next to a document's real entry.
_NON_TITLE_LINK_TEXT = {"text", "txt", "itx", "pdf", "here", "html", "link"}

# Attribution/footer lines that mark "the real text is over" — whichever of
# these appears first in the body is the cut point. Order doesn't matter;
# the earliest match wins regardless of which marker it is. svararahitam
# ("without accents") isn't attribution — some accented Vedic texts repeat
# their entire body a second time with the accent marks stripped, for
# chanters who don't need them. Redundant for us either way: our own
# to_plain_english already strips accent marks from the (single) copy we
# keep, so cutting here just avoids storing and indexing the same text
# twice.
_FOOTER_MARKERS = (
    "\\medskip\\hrule\\obeylines",
    "Please send corrections",
    "Encoded by",
    "Encoded and proofread",
    "Transliterated by",
    "Proofread by",
    "Input by",
    "Scanned by",
    "svararahitam",
)

_HEADER_LINE = re.compile(r"%\s*([A-Za-z][A-Za-z \-]*?)\s*:\s*(.*)")
_TITLE_MACRO_LINE = re.compile(r"^\\(engtitle|itxtitle|endtitles)\b")
_CROSS_REFERENCE_LINE = re.compile(r"^See\s.+\sin a separate file\.?$", re.IGNORECASE)

# A handful of documents tack on an English paragraph explaining the text
# (ritual context, a word's meaning) after the real content ends but before
# any _FOOTER_MARKERS phrase — e.g. "...ArAtrikam samAptam || 7|| ##
# Night ritual. Atharvaveda Parishishta/Appendix 7 ... the word ArAtrikam
# means...". No single marker phrase catches all of these, but the prose
# itself is a reliable enough tell: real ITRANS practically never spells
# out an unbroken run of common English function words, so a line
# containing several is almost certainly commentary, not verse.
_ENGLISH_STOPWORDS = {
    "the", "is", "was", "were", "this", "that", "which", "and", "of", "in",
    "to", "for", "with", "from", "by", "on", "as", "at",
}
_WORD = re.compile(r"[a-zA-Z']+")


def _looks_like_english_prose(line: str) -> bool:
    words = (w.lower() for w in _WORD.findall(line))
    return sum(1 for w in words if w in _ENGLISH_STOPWORDS) >= 3
# Vedic accent escapes (\' \` \" mark pitch, not real characters) drop
# entirely; every other backslash-escaped symbol (verse/citation separators
# like "63\-1" or "1\.001\.01", a literal underscore as "major\_works",
# etc. — checked against a real sample rather than guessed, but each escape
# found was a new one, so this is deliberately general rather than an
# enumerated whitelist) keeps the symbol, drops just the backslash. Both
# patterns are single backslash + one non-letter, which ITRANS itself never
# produces, so neither can collide with real transliterated text — order
# matters: accent escapes must be stripped first, or this general pass
# would keep their mark characters instead of dropping them too.
_ACCENT_ESCAPE = re.compile(r"\\['`\"]")
_PUNCT_ESCAPE = re.compile(r"\\([^a-zA-Z])")
_LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+\*?")


def _is_junk_title(text: str) -> bool:
    """Some index entries' visible link text is just a footnote/version
    marker (e.g. "1", "2") rather than the document's actual title — the
    real title lives only in the URL in those cases.

    Link text on these category pages is normally genuine Devanagari, not
    Latin/ITRANS — checking for Latin letters alone (an earlier version of
    this function) flagged nearly every real title as junk, discarding the
    actual page-native title in favor of a cruder title reconstructed from
    the URL slug (see _title_from_url) for almost every entry. Only treat a
    title as junk when it has neither Devanagari nor Latin letters at all.
    """
    stripped = text.strip()
    has_script = any("ऀ" <= ch <= "ॿ" for ch in stripped) or bool(re.search(r"[a-zA-Z]", stripped))
    return len(stripped) < 3 or not has_script


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


def _parse_itx(raw: str) -> tuple[dict[str, str], str]:
    """(header metadata, cleaned ITRANS body). Not a full LaTeX parser —
    handles this corpus's actual conventions (verified against real files,
    not the spec): a leading "% key : value" comment block; a preamble
    before \\begin{document} that's dropped wholesale (pure markup, no
    content); a body that's cut at the first attribution/footer marker
    (_FOOTER_MARKERS) since real verse text never contains those phrases;
    title macros, "See X in a separate file" cross-references, and lines
    that look like English commentary (_looks_like_english_prose) dropped
    line-by-line; inline accent escapes (\\' \\` for Vedic pitch marks) and
    the {\\m+} doubling notation stripped down to their base letters; any
    remaining bare LaTeX command token swept up as a catch-all.
    """
    lines = raw.splitlines()

    meta: dict[str, str] = {}
    header_end = 0
    while header_end < len(lines) and lines[header_end].strip().startswith("%"):
        match = _HEADER_LINE.match(lines[header_end])
        if match:
            meta[match.group(1).strip().lower()] = match.group(2).strip()
        header_end += 1

    text = "\n".join(lines[header_end:])
    doc_match = re.search(r"\\begin\{document\}(.*?)(\\end\{document\}|\Z)", text, re.DOTALL)
    body = doc_match.group(1) if doc_match else text

    cut = len(body)
    for marker in _FOOTER_MARKERS:
        idx = body.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    body = body[:cut]

    kept_lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _TITLE_MACRO_LINE.match(stripped) or _CROSS_REFERENCE_LINE.match(stripped):
            continue
        if _looks_like_english_prose(stripped):
            continue
        kept_lines.append(stripped)
    joined = " ".join(kept_lines)

    joined = joined.replace("{\\m+}", "")
    joined = _ACCENT_ESCAPE.sub("", joined)
    joined = _PUNCT_ESCAPE.sub(r"\1", joined)
    joined = joined.replace("##", " ")
    joined = _LATEX_COMMAND.sub(" ", joined)
    joined = re.sub(r"[{}]", "", joined)
    return meta, re.sub(r"\s+", " ", joined).strip()


def fetch_itx(session: PoliteSession, doc_url: str) -> tuple[dict[str, str], str] | None:
    itx_url = re.sub(r"\.html$", ".itx", doc_url)
    try:
        raw = session.get(itx_url).text
    except requests.RequestException as exc:
        print(f"skip {itx_url}: {exc}", file=sys.stderr)
        return None
    meta, itrans_body = _parse_itx(raw)
    if len(itrans_body) < 20:
        return None
    try:
        devanagari = sanscript.transliterate(itrans_body, sanscript.ITRANS, sanscript.DEVANAGARI)
    except Exception as exc:
        print(f"skip {itx_url}: ITRANS->Devanagari failed: {exc}", file=sys.stderr)
        return None
    return meta, devanagari


def crawl(session: PoliteSession, category_path: str, limit: int) -> Iterator[dict]:
    for title_raw, url in list_category_docs(session, category_path, limit):
        result = fetch_itx(session, url)
        if result is None:
            continue
        meta, content_devanagari = result
        if _is_junk_title(title_raw):
            title_raw = _title_from_url(url)
        try:
            title_devanagari = sanscript.transliterate(title_raw, sanscript.ITRANS, sanscript.DEVANAGARI)
        except Exception:
            title_devanagari = ""
        # The header shares the body's escaping conventions (e.g.
        # "major\_works" for a literal underscore) — same cleanup.
        tags = [
            _PUNCT_ESCAPE.sub(r"\1", t.strip())
            for t in meta.get("category", "").split(",")
            if t.strip()
        ]
        yield {
            "title_devanagari": title_devanagari,
            "title_raw": title_raw,
            "content_devanagari": content_devanagari,
            "source_url": url,
            "text_source_label": "sanskritdocuments.org",
            "tags": tags,
        }
