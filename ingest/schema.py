from typing import Literal

from pydantic import BaseModel, field_validator

# Every ingested entry's provenance is a conscious, recorded decision, not
# something that can be silently skipped — see ShlokaEntry.source_attribution
# below, which is a required field. "original_translation" covers a
# translation produced fresh for this project (and labeled as such) rather
# than copied from an uncredited third-party source — see the project
# README's content-sourcing notes for why this matters.
License = Literal["public_domain", "cc_by", "cc_by_sa", "original_translation"]


class SourceAttribution(BaseModel):
    text_source: str
    translation_source: str | None = None
    license: License


class ShlokaEntry(BaseModel):
    """One shloka/stotra, mirroring the Elasticsearch document shape (see
    mapping.py) — one YAML file per entry under content/shlokas/.
    `content.*` (the shloka rendered in different scripts) and `meaning.*`
    (an explanatory translation) are kept separate deliberately: `meaning`
    is where the copyright judgment call actually matters (original creative
    prose), `content` in a non-English script is much lower-risk — keeping
    them apart means the license decision in source_attribution can be
    reasoned about per-field, not forced to the whole document.
    """

    id: str
    category: str
    name: dict[str, str]
    content: dict[str, str]
    meaning: dict[str, str] = {}
    source_attribution: SourceAttribution

    @field_validator("name", "content")
    @classmethod
    def _requires_english(cls, value: dict[str, str], info) -> dict[str, str]:
        if "english" not in value:
            raise ValueError(
                f"{info.field_name} must include an 'english' entry — "
                "search only ever queries English, regardless of display language"
            )
        return value

    @property
    def languages_available(self) -> list[str]:
        return sorted(set(self.name) | set(self.content))

    def to_es_document(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "name": self.name,
            "content": self.content,
            "meaning": self.meaning,
            "source_attribution": self.source_attribution.model_dump(),
            "languages_available": self.languages_available,
        }
