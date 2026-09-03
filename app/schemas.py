from typing import Literal

from pydantic import BaseModel


class Highlight(BaseModel):
    name: list[str] = []
    content: list[str] = []


class SearchResult(BaseModel):
    id: str
    category: str
    languages_available: list[str]
    name: dict[str, str]
    content: dict[str, str]
    meaning: dict[str, str] = {}
    highlight: Highlight
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    has_more: bool


# Anonymous, aggregate-only app usage — no user/device identifier of any
# kind, ever (see app/analytics.py). "feature_time" = seconds a tab was
# visible (feature is the tab name); "search_performed" = one per search
# that actually returned to the user (client-reported, not derived from
# server request logs, so retries/failures don't inflate it).
class UsageEvent(BaseModel):
    event: Literal["feature_time", "search_performed"]
    feature: str | None = None
    seconds: int | None = None


class UsageEventBatch(BaseModel):
    events: list[UsageEvent]
