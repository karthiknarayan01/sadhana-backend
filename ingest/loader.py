from pathlib import Path

import yaml
from pydantic import ValidationError

from ingest.schema import ShlokaEntry


class ContentValidationError(Exception):
    """Every file's error is collected before raising, so a batch-vet run
    (see --dry-run) reports everything wrong at once instead of stopping at
    the first bad file.
    """

    def __init__(self, errors: dict[Path, Exception]) -> None:
        self.errors = errors
        summary = "\n".join(f"  {path}: {err}" for path, err in errors.items())
        super().__init__(f"{len(errors)} file(s) failed validation:\n{summary}")


def load_content_dir(content_dir: Path) -> list[ShlokaEntry]:
    entries: list[ShlokaEntry] = []
    errors: dict[Path, Exception] = {}

    for path in sorted(content_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text())
            entries.append(ShlokaEntry.model_validate(raw))
        except (ValidationError, yaml.YAMLError) as exc:
            errors[path] = exc

    if errors:
        raise ContentValidationError(errors)
    return entries
