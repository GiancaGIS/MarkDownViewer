from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSettings

try:
    from .config import MARKDOWN_SUFFIXES
except ImportError:
    from config import MARKDOWN_SUFFIXES

@dataclass(frozen=True)
class SearchHit:
    path: Path
    line_number: int
    snippet: str


def as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def settings_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, tuple):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x for x in value.split("||") if x.strip()]
    return []


def save_settings_list(settings: QSettings, key: str, values: list[str]) -> None:
    # QSettings serializes Python lists differently across backends; a string is predictable.
    settings.setValue(key, "||".join(values))


def coerce_splitter_sizes(value, expected: int) -> list[int] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        try:
            sizes = [int(x) for x in value]
            return sizes if len(sizes) == expected else None
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        numbers = [int(x) for x in re.findall(r"\d+", value)]
        return numbers[:expected] if len(numbers) >= expected else None
    return None


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def is_markdown_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in MARKDOWN_SUFFIXES

