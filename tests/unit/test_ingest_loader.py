from pathlib import Path

import pytest
import yaml

from ingest.loader import ContentValidationError, load_content_dir

VALID_ENTRY = {
    "id": "test-entry",
    "category": "stotram",
    "name": {"english": "Test Entry"},
    "content": {"english": "Test content"},
    "source_attribution": {"text_source": "test", "license": "public_domain"},
}


def _write(dir_path: Path, filename: str, data: dict) -> None:
    (dir_path / filename).write_text(yaml.safe_dump(data))


def test_loads_every_valid_file_in_the_directory(tmp_path: Path) -> None:
    _write(tmp_path, "a.yaml", VALID_ENTRY)
    _write(tmp_path, "b.yaml", {**VALID_ENTRY, "id": "another-entry"})

    entries = load_content_dir(tmp_path)

    assert {e.id for e in entries} == {"test-entry", "another-entry"}


def test_empty_directory_yields_no_entries(tmp_path: Path) -> None:
    assert load_content_dir(tmp_path) == []


def test_a_single_invalid_file_fails_the_whole_batch_with_a_clear_error(tmp_path: Path) -> None:
    _write(tmp_path, "good.yaml", VALID_ENTRY)
    invalid = {k: v for k, v in VALID_ENTRY.items() if k != "source_attribution"}
    _write(tmp_path, "missing-license.yaml", invalid)

    with pytest.raises(ContentValidationError) as exc_info:
        load_content_dir(tmp_path)

    assert "missing-license.yaml" in str(exc_info.value)


def test_reports_every_bad_file_in_one_pass_not_just_the_first(tmp_path: Path) -> None:
    invalid = {k: v for k, v in VALID_ENTRY.items() if k != "source_attribution"}
    _write(tmp_path, "bad-one.yaml", invalid)
    _write(tmp_path, "bad-two.yaml", invalid)

    with pytest.raises(ContentValidationError) as exc_info:
        load_content_dir(tmp_path)

    assert len(exc_info.value.errors) == 2
