"""Shared, packaged catalogs for account emails, errors, and onboarding."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

LOCALES = Path(__file__).parent / "locales"
LANGUAGES = json.loads((LOCALES / "languages.json").read_text("utf-8"))
Language = Literal[tuple(LANGUAGES)]
DEFAULT_LANGUAGE: Language = "en"


@lru_cache
def catalog(language: Language = DEFAULT_LANGUAGE) -> dict[str, str]:
    language = language if language in LANGUAGES else DEFAULT_LANGUAGE
    return json.loads((LOCALES / f"{language}.json").read_text("utf-8"))


def translate(key: str, language: Language = DEFAULT_LANGUAGE, **values: object) -> str:
    template = catalog(language).get(key, catalog().get(key, catalog()["common.unavailable"]))
    return template.replace("''", "'").format_map(values)


class LocalizedText(str):
    """Retain a stable key while keeping the existing English API detail compatible."""

    key: str
    values: dict[str, object]

    def __new__(cls, key: str, **values: object):
        result = super().__new__(cls, translate(key, **values))
        result.key = key
        result.values = values
        return result


def localized(key: str, **values: object) -> LocalizedText:
    return LocalizedText(key, **values)


def parameters(values: dict[str, object]) -> dict[str, object]:
    return {
        name: {"key": value.key, "values": parameters(value.values)}
        if isinstance(value, LocalizedText)
        else value
        for name, value in values.items()
    }


def error_detail(error: Exception) -> LocalizedText:
    if error.args and isinstance(error.args[0], LocalizedText):
        return error.args[0]
    return localized("api.unavailable")
