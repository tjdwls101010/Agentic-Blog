"""Shared fixture helper for synthetic offline test data."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> object:
    """Load a UTF-8 JSON fixture by single filename."""
    if (
        not isinstance(name, str)
        or "/" in name
        or "\\" in name
        or "\x00" in name
        or Path(name).name != name
        or name in {"", ".", ".."}
    ):
        raise ValueError(f"invalid fixture filename: {name!r}")
    fixture_root = FIXTURES.resolve()
    fixture_path = (fixture_root / name).resolve()
    if fixture_path.parent != fixture_root:
        raise ValueError(f"invalid fixture filename: {name!r}")
    return json.loads(fixture_path.read_text(encoding="utf-8"))
