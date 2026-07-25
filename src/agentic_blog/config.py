"""Runtime defaults, storage paths, and request-rate guardrails."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import platformdirs

APP_NAME = "agentic-blog"
ENV_DATA_DIR = "AGENTIC_BLOG_DATA_DIR"

#: This floor applies regardless of whether a value comes from the CLI or library API.
MIN_REQUEST_PAUSE_SECONDS = 0.5
DEFAULT_REQUEST_PAUSE_SECONDS = MIN_REQUEST_PAUSE_SECONDS

#: Bound a run before it becomes an accidental bulk collection job.
DEFAULT_MAX_REQUESTS = 100

DEFAULT_USER_AGENT_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_USER_AGENT_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"
)


def data_dir(*, data_dir_override: str | Path | None = None) -> Path:
    """Resolve the application data directory without creating it."""
    if data_dir_override is not None:
        return Path(data_dir_override)
    if env_override := os.environ.get(ENV_DATA_DIR):
        return Path(env_override)
    return Path(platformdirs.user_data_dir(APP_NAME))


def default_output_dir(*, data_dir_override: str | Path | None = None) -> Path:
    """Resolve the output directory outside the working tree."""
    return data_dir(data_dir_override=data_dir_override) / "output"


def clamp_request_pause(request_pause_seconds: float) -> float:
    """Return a request pause no lower than the mandatory rate floor."""
    if request_pause_seconds >= MIN_REQUEST_PAUSE_SECONDS:
        return request_pause_seconds
    print(
        f"agentic-blog: request pause {request_pause_seconds}s raised to "
        f"{MIN_REQUEST_PAUSE_SECONDS}s (non-bypassable minimum)",
        file=sys.stderr,
    )
    return MIN_REQUEST_PAUSE_SECONDS
