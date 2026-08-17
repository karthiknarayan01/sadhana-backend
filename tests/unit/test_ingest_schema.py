import pytest
from pydantic import ValidationError

from ingest.schema import ShlokaEntry

VALID = {
    "id": "argala-stotram",
    "category": "stotram",
    "name": {"english": "Argala Stotram", "telugu": "అర్గళా స్తోత్రం"},
    "content": {"english": "Om namaste...", "telugu": "ఓం నమస్తే..."},
    "source_attribution": {"text_source": "test", "license": "public_domain"},
}


def test_valid_entry_parses() -> None:
    entry = ShlokaEntry.model_validate(VALID)
    assert entry.id == "argala-stotram"
    assert entry.source_attribution.license == "public_domain"


def test_missing_source_attribution_is_rejected() -> None:
    payload = {k: v for k, v in VALID.items() if k != "source_attribution"}
    with pytest.raises(ValidationError):
        ShlokaEntry.model_validate(payload)


def test_missing_license_is_rejected() -> None:
    payload = {**VALID, "source_attribution": {"text_source": "test"}}
    with pytest.raises(ValidationError):
        ShlokaEntry.model_validate(payload)


def test_unknown_license_value_is_rejected() -> None:
    payload = {**VALID, "source_attribution": {"text_source": "test", "license": "all_rights_reserved"}}
    with pytest.raises(ValidationError):
        ShlokaEntry.model_validate(payload)


@pytest.mark.parametrize("field", ["name", "content"])
def test_missing_english_is_rejected(field: str) -> None:
    payload = {**VALID, field: {"telugu": "..."}}
    with pytest.raises(ValidationError, match="english"):
        ShlokaEntry.model_validate(payload)


def test_languages_available_is_the_union_of_name_and_content_languages() -> None:
    entry = ShlokaEntry.model_validate(
        {
            **VALID,
            "name": {"english": "...", "telugu": "..."},
            "content": {"english": "...", "hindi": "..."},
        }
    )
    assert entry.languages_available == ["english", "hindi", "telugu"]


def test_to_es_document_shape() -> None:
    entry = ShlokaEntry.model_validate(VALID)
    doc = entry.to_es_document()
    assert doc["id"] == "argala-stotram"
    assert doc["languages_available"] == ["english", "telugu"]
    assert doc["source_attribution"]["license"] == "public_domain"
    assert doc["meaning"] == {}
