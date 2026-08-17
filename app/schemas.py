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
