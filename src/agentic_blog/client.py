"""Paced anonymous HTTP reads for Naver's public JSON endpoints."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Condition, Lock
from typing import TypeVar
from urllib.parse import urlsplit

import httpx

from . import config, errors
from .endpoints import RequestSpec

_T = TypeVar("_T")

_SECTION_HOST = "section.blog.naver.com"
_MOBILE_HOST = "m.blog.naver.com"
_CBOX_HOST = "apis.naver.com"
_LEGACY_HOST = "blog.naver.com"
_XSSI_PREFIX = ")]}',"
_MOBILE_NO_POST_REDIRECT = re.compile(
    r'^\s*<script>\s*location\.href\s*=\s*["\']MobileErrorView\.naver'
    r'\?errorType=noPost["\'];?\s*</script>\s*$'
)


class _NonClosingTransport(httpx.BaseTransport):
    """Delegate requests without taking ownership of the caller's transport."""

    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._transport.handle_request(request)

    def close(self) -> None:
        pass


class ReadClient:
    """A request-budgeted, anonymous client for Naver's public read endpoints."""

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        *,
        request_pause: float | None = None,
        max_requests: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        pause = config.DEFAULT_REQUEST_PAUSE_SECONDS if request_pause is None else request_pause
        self._request_pause = _validated_request_pause(pause)
        maximum = config.DEFAULT_MAX_REQUESTS if max_requests is None else max_requests
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
            raise ValueError("max_requests must be a non-negative integer")
        self._max_requests = maximum
        if transport is not None and not isinstance(transport, httpx.BaseTransport):
            raise TypeError("transport must be an httpx.BaseTransport")

        self._client = httpx.Client(
            transport=_NonClosingTransport(transport) if transport is not None else None,
            follow_redirects=False,
        )
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None
        self._requests_made = 0
        self._closed = False
        self._state_lock = Lock()
        self._state_changed = Condition(self._state_lock)
        self._active_operations = 0
        self._closing = False

    def close(self) -> None:
        """Close the internally constructed HTTP client."""
        with self._state_changed:
            if self._closed:
                while self._closing:
                    self._state_changed.wait()
                return
            self._closed = True
            self._closing = True
            while self._active_operations:
                self._state_changed.wait()
            owned_client = self._client
        try:
            owned_client.close()
        finally:
            with self._state_changed:
                self._closing = False
                self._state_changed.notify_all()

    def __enter__(self) -> ReadClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def request_pause(self) -> float:
        """The effective pause, never lower than the package-wide safety floor."""
        return self._request_pause

    @request_pause.setter
    def request_pause(self, value: float) -> None:
        self._request_pause = _validated_request_pause(value)

    @property
    def max_requests(self) -> int:
        """Maximum number of requests this client may make."""
        return self._max_requests

    @property
    def requests_made(self) -> int:
        """Number of budgeted requests attempted in this client lifetime."""
        return self._requests_made

    @property
    def remaining_requests(self) -> int:
        """Number of requests still available in this client's lifetime budget."""
        return max(0, self.max_requests - self.requests_made)

    def get_json(self, spec: RequestSpec) -> dict[str, object]:
        """GET a request specification and return its raw JSON object envelope."""
        return self._request(spec, self._response_json)

    def get_text(self, spec: RequestSpec) -> str:
        """GET a request specification and return its response text."""
        return self._request(spec, self._response_text)

    def _request(
        self,
        spec: RequestSpec,
        response_handler: Callable[[httpx.Response, bool], _T],
    ) -> _T:
        with self._state_changed:
            if self._closed:
                raise errors.AgenticBlogError("client is closed")
            headers, is_section = _headers_for(spec.url)
            if self._requests_made >= self._max_requests:
                raise errors.AgenticBlogError(
                    f"request budget exhausted ({self._max_requests} requests)"
                )
            self._throttle()
            self._requests_made += 1
            self._active_operations += 1
        try:
            try:
                request = httpx.Request("GET", spec.url, params=spec.params, headers=headers)
                response = self._client.send(request, auth=None, follow_redirects=False)
            except httpx.HTTPError as exc:
                error_name = type(exc).__name__
            else:
                return response_handler(response, is_section)
            raise errors.AgenticBlogError(f"Naver request failed: {error_name}")
        finally:
            with self._state_changed:
                self._active_operations -= 1
                self._state_changed.notify_all()

    def _throttle(self) -> None:
        """Enforce the floor before the first and every later request."""
        now = _monotonic_now(self._clock)
        if self._last_request_at is not None and now < self._last_request_at:
            raise errors.AgenticBlogError("monotonic clock moved backwards")
        delay = self.request_pause
        if self._last_request_at is not None:
            delay = max(0.0, delay - (now - self._last_request_at))
        if delay > 0:
            self._sleep(delay)
            after_sleep = _monotonic_now(self._clock)
            if after_sleep <= now or after_sleep - now < delay:
                raise errors.AgenticBlogError(
                    "request sleeper did not advance monotonic time by the required pause"
                )
            self._last_request_at = after_sleep
        else:
            self._last_request_at = now

    def _response_json(self, response: httpx.Response, is_section: bool) -> dict[str, object]:
        self._raise_for_response_status(response)
        body = _decode_body(response)
        if is_section and body.startswith(_XSSI_PREFIX):
            body = body[len(_XSSI_PREFIX) :].lstrip("\r\n")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise errors.EnvelopeParseError("Naver returned malformed JSON") from exc
        if not isinstance(parsed, dict):
            raise errors.EnvelopeParseError("Naver returned a non-object JSON envelope")
        return parsed

    @staticmethod
    def _response_text(response: httpx.Response, _: bool) -> str:
        ReadClient._raise_for_response_status(response)
        return response.text

    @staticmethod
    def _raise_for_response_status(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise errors.RateLimitedError(retry_after=_retry_after(response.headers))
        if response.status_code in {400, 404}:
            try:
                body = _decode_body(response)
            except errors.EnvelopeParseError:
                body = None
            # Phase 0 measured only these exact nonexistent-target envelopes. Do not infer
            # private, neighbour-only, deleted, or suspended target states from other shapes.
            if body is not None and _is_measured_not_found(response.status_code, body):
                raise errors.NotFoundError(
                    "Naver reported that the requested blog or post does not exist"
                )
        if response.status_code != 200:
            raise errors.AgenticBlogError(f"Naver returned unexpected HTTP {response.status_code}")


def _headers_for(url: str) -> tuple[dict[str, str], bool]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError("RequestSpec URL must be a supported HTTPS Naver URL") from None
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ValueError("RequestSpec URL must be a supported HTTPS Naver URL")

    host = parsed.hostname
    if host == _SECTION_HOST:
        return (
            {
                "Referer": "https://section.blog.naver.com/",
                "User-Agent": config.DEFAULT_USER_AGENT_DESKTOP,
            },
            True,
        )
    if host == _MOBILE_HOST:
        return (
            {
                "Referer": "https://m.blog.naver.com/",
                "User-Agent": config.DEFAULT_USER_AGENT_MOBILE,
            },
            False,
        )
    if host == _CBOX_HOST:
        return (
            {
                "Referer": "https://m.blog.naver.com/",
                "User-Agent": config.DEFAULT_USER_AGENT_DESKTOP,
            },
            False,
        )
    if host == _LEGACY_HOST:
        return (
            {
                "Referer": "https://blog.naver.com/",
                "User-Agent": config.DEFAULT_USER_AGENT_DESKTOP,
            },
            False,
        )
    raise ValueError("RequestSpec URL must be a supported HTTPS Naver URL")


def _decode_body(response: httpx.Response) -> str:
    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise errors.EnvelopeParseError("Naver returned a non-UTF-8 JSON envelope") from exc


def _is_measured_not_found(status_code: int, body: str) -> bool:
    if status_code == 404 and _MOBILE_NO_POST_REDIRECT.fullmatch(body):
        return True
    if status_code not in {400, 404}:
        return False
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, Mapping):
        return False
    error = parsed.get("error")
    if not isinstance(error, Mapping):
        return False
    code = error.get("code")
    return (
        status_code == 400 and parsed.get("isSuccess") is False and code == "blog_id_invalidate"
    ) or (status_code == 404 and code == "not_exist_post")


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = (retry_at - datetime.now(UTC)).total_seconds()
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


def _validated_request_pause(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("request_pause must be a finite number")
    return config.clamp_request_pause(float(value))


def _monotonic_now(clock: Callable[[], float]) -> float:
    now = clock()
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        raise errors.AgenticBlogError("monotonic clock returned an invalid value")
    return float(now)
