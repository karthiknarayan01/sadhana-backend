"""Sanskrit Wikisource (sa.wikisource.org) adapter — reads Devanagari verse
text via the public MediaWiki API for pages in a given category. Wikisource
exists specifically to host proofread public-domain source texts, so license
is hardcoded to "public_domain" here; this adapter never touches a
translation (Wikisource's Sanskrit-language wiki doesn't carry English
translations inline) or any commentary outside the page's Devanagari runs.
"""

import sys
from collections.abc import Iterator

import requests

from ingest.crawl.common import PoliteSession, devanagari_content

API_URL = "https://sa.wikisource.org/w/api.php"
PAGE_URL = "https://sa.wikisource.org/wiki/{}"


def list_category_pages(session: PoliteSession, category: str, limit: int) -> list[str]:
    titles: list[str] = []
    cmcontinue = None
    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": min(50, limit - len(titles)),
            "cmnamespace": 0,
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = session.get(API_URL, params=params).json()
        titles.extend(m["title"] for m in data.get("query", {}).get("categorymembers", []))
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return titles[:limit]


def fetch_devanagari(session: PoliteSession, title: str) -> str | None:
    params = {"action": "parse", "page": title, "prop": "text", "format": "json", "formatversion": 2}
    try:
        data = session.get(API_URL, params=params).json()
    except requests.RequestException as exc:
        print(f"skip {title}: {exc}", file=sys.stderr)
        return None
    if "error" in data:
        return None
    return devanagari_content(data["parse"]["text"])


def crawl(session: PoliteSession, category: str, limit: int) -> Iterator[dict]:
    for title in list_category_pages(session, category, limit):
        content = fetch_devanagari(session, title)
        if content is None:
            continue
        yield {
            "title_devanagari": title,
            "title_raw": title,
            "content_devanagari": content,
            "source_url": PAGE_URL.format(title.replace(" ", "_")),
            "text_source_label": "Sanskrit Wikisource",
        }
