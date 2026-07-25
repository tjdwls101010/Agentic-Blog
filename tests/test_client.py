from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from threading import Event, Lock, Thread

import httpx
import pytest

from agentic_blog import config
from agentic_blog.client import ReadClient
from agentic_blog.endpoints import RequestSpec
from agentic_blog.errors import (
    AgenticBlogError,
    EnvelopeParseError,
    NotFoundError,
    RateLimitedError,
)
from agentic_blog.redact import redact_diagnostic, redact_url


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


class CoordinatedClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.first_sleep_entered = Event()
        self.release_first_sleep = Event()
        self.second_sleep_entered = Event()
        self.release_second_sleep = Event()
        self._lock = Lock()

    def clock(self) -> float:
        with self._lock:
            return self.now

    def sleep(self, delay: float) -> None:
        with self._lock:
            self.sleeps.append(delay)
            sleep_number = len(self.sleeps)
        if sleep_number == 1:
            self.first_sleep_entered.set()
            assert self.release_first_sleep.wait(timeout=1)
        elif sleep_number == 2:
            self.second_sleep_entered.set()
            assert self.release_second_sleep.wait(timeout=1)
        with self._lock:
            self.now += delay


_HELPER_CLIENTS: list[ReadClient] = []


@pytest.fixture(autouse=True)
def _close_helper_clients() -> Iterator[None]:
    yield
    while _HELPER_CLIENTS:
        _HELPER_CLIENTS.pop().close()


def _client(handler, *, clock: FakeClock | None = None, max_requests: int = 10) -> ReadClient:
    clock = clock or FakeClock()
    client = ReadClient(
        httpx.MockTransport(handler),
        request_pause=0,
        max_requests=max_requests,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    _HELPER_CLIENTS.append(client)
    return client


def test_close_closes_an_internally_constructed_client() -> None:
    client = ReadClient()

    owned_client = client._client
    client.close()

    assert owned_client.is_closed


def test_close_closes_its_wrapper_without_closing_an_injected_transport() -> None:
    class CallerTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.close_calls = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if self.close_calls:
                raise AssertionError("caller transport was closed")
            return httpx.Response(200, json={})

        def close(self) -> None:
            self.close_calls += 1

    transport = CallerTransport()
    client = ReadClient(transport)
    owned_client = client._client

    client.close()

    assert owned_client.is_closed
    assert transport.close_calls == 0
    response = transport.handle_request(httpx.Request("GET", "https://example.com/"))
    assert response.status_code == 200


def test_context_manager_closes_an_internally_constructed_client() -> None:
    with ReadClient() as client:
        owned_client = client._client
        assert not owned_client.is_closed

    assert owned_client.is_closed


def test_close_is_idempotent_for_an_internally_constructed_client(monkeypatch) -> None:
    class OwnedClient:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    owned_client = OwnedClient()
    monkeypatch.setattr("agentic_blog.client.httpx.Client", lambda **kwargs: owned_client)
    client = ReadClient()

    client.close()
    client.close()

    assert owned_client.close_calls == 1


def test_post_close_get_json_rejects_before_mutating_state() -> None:
    requests: list[httpx.Request] = []
    clock = FakeClock()
    client = ReadClient(
        httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={})
        ),
        request_pause=0,
        max_requests=1,
        clock=clock.clock,
        sleep=clock.sleep,
    )

    client.close()

    with pytest.raises(AgenticBlogError, match="client is closed"):
        client.get_json(RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {}))

    assert requests == []
    assert client.requests_made == 0
    assert clock.sleeps == []


def test_close_waits_for_an_admitted_owned_request_before_closing_transport(monkeypatch) -> None:
    request_started = Event()
    release_request = Event()
    close_returned = Event()

    def handler(request: httpx.Request) -> httpx.Response:
        request_started.set()
        assert release_request.wait(timeout=1)
        return httpx.Response(200, json={})

    owned_client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("agentic_blog.client.httpx.Client", lambda **kwargs: owned_client)
    clock = FakeClock()
    client = ReadClient(request_pause=0, clock=clock.clock, sleep=clock.sleep)
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})
    request = Thread(target=client.get_json, args=(spec,))
    request.start()
    assert request_started.wait(timeout=1)

    def close() -> None:
        client.close()
        close_returned.set()

    closing = Thread(target=close)
    closing.start()
    assert not close_returned.wait(timeout=0.1)
    assert not owned_client.is_closed
    assert client._closed
    with pytest.raises(AgenticBlogError, match="client is closed"):
        client.get_json(spec)
    assert client.requests_made == 1

    release_request.set()
    request.join(timeout=1)
    closing.join(timeout=1)

    assert not request.is_alive()
    assert not closing.is_alive()
    assert close_returned.is_set()
    assert owned_client.is_closed


def test_concurrent_calls_admit_only_one_request_with_a_budget_of_one() -> None:
    clock = CoordinatedClock()
    requests: list[httpx.Request] = []
    client = ReadClient(
        httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={})
        ),
        request_pause=0,
        max_requests=1,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})
    failures: list[Exception] = []

    def request() -> None:
        try:
            client.get_json(spec)
        except Exception as exc:
            failures.append(exc)

    first = Thread(target=request)
    first.start()
    assert clock.first_sleep_entered.wait(timeout=1)
    second = Thread(target=request)
    second.start()
    assert not clock.second_sleep_entered.wait(timeout=0.1)
    clock.release_first_sleep.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(requests) == 1
    assert client.requests_made == 1
    assert len(failures) == 1
    assert str(failures[0]) == "request budget exhausted (1 requests)"


def test_concurrent_request_starts_are_separated_by_the_request_pause() -> None:
    clock = CoordinatedClock()
    start_times: list[float] = []
    first_transport_started = Event()

    def handler(request: httpx.Request) -> httpx.Response:
        start_times.append(clock.clock())
        if len(start_times) == 1:
            first_transport_started.set()
        return httpx.Response(200, json={})

    client = ReadClient(
        httpx.MockTransport(handler),
        request_pause=0,
        max_requests=2,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})

    first = Thread(target=client.get_json, args=(spec,))
    first.start()
    assert clock.first_sleep_entered.wait(timeout=1)
    second = Thread(target=client.get_json, args=(spec,))
    second.start()
    assert not clock.second_sleep_entered.wait(timeout=0.1)

    clock.release_first_sleep.set()
    assert first_transport_started.wait(timeout=1)
    assert clock.second_sleep_entered.wait(timeout=1)
    clock.release_second_sleep.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert start_times == pytest.approx(
        [config.MIN_REQUEST_PAUSE_SECONDS, 2 * config.MIN_REQUEST_PAUSE_SECONDS]
    )


@pytest.mark.parametrize(
    ("url", "headers"),
    [
        (
            "https://section.blog.naver.com/endpoint",
            {
                "host": "section.blog.naver.com",
                "referer": "https://section.blog.naver.com/",
                "user-agent": config.DEFAULT_USER_AGENT_DESKTOP,
            },
        ),
        (
            "https://m.blog.naver.com/endpoint",
            {
                "host": "m.blog.naver.com",
                "referer": "https://m.blog.naver.com/",
                "user-agent": config.DEFAULT_USER_AGENT_MOBILE,
            },
        ),
        (
            "https://apis.naver.com/endpoint",
            {
                "host": "apis.naver.com",
                "referer": "https://m.blog.naver.com/",
                "user-agent": config.DEFAULT_USER_AGENT_DESKTOP,
            },
        ),
        (
            "https://blog.naver.com/endpoint",
            {
                "host": "blog.naver.com",
                "referer": "https://blog.naver.com/",
                "user-agent": config.DEFAULT_USER_AGENT_DESKTOP,
            },
        ),
    ],
)
@pytest.mark.parametrize("response_kind", ["json", "text"])
def test_transport_sees_only_complete_endpoint_headers(
    url: str, headers: dict[str, str], response_kind: str
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if response_kind == "json" and request.url.host == "section.blog.naver.com":
            return httpx.Response(200, content=b")]}',\n{}")
        if response_kind == "json":
            return httpx.Response(200, json={})
        return httpx.Response(200, text="ok")

    client = _client(handler)

    if response_kind == "json":
        assert client.get_json(RequestSpec(url, {})) == {}
    else:
        assert client.get_text(RequestSpec(url, {})) == "ok"

    assert dict(requests[0].headers) == headers


def test_client_injection_is_rejected_before_credential_hook_can_run() -> None:
    def add_credentials(request: httpx.Request) -> None:
        request.headers["Authorization"] = "Bearer injected-secret"

    with httpx.Client(event_hooks={"request": [add_credentials]}) as injected_client:
        with pytest.raises(TypeError, match="unexpected keyword argument 'client'"):
            ReadClient(client=injected_client)


def test_concurrent_get_json_requests_never_send_cookie_state() -> None:
    requests: list[httpx.Request] = []
    requests_lock = Lock()
    concurrent_requests_started = Event()
    release_concurrent_requests = Event()

    def handler(request: httpx.Request) -> httpx.Response:
        with requests_lock:
            requests.append(request)
            request_number = len(requests)
            if request_number == 3:
                concurrent_requests_started.set()
        if request_number > 1:
            assert release_concurrent_requests.wait(timeout=1)
        response_headers = {"Set-Cookie": "response=value; Path=/"} if request_number == 1 else {}
        return httpx.Response(200, json={}, headers=response_headers)

    clock = FakeClock()
    client = ReadClient(
        httpx.MockTransport(handler),
        request_pause=0,
        max_requests=3,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})

    assert client.get_json(spec) == {}
    first = Thread(target=client.get_json, args=(spec,))
    second = Thread(target=client.get_json, args=(spec,))
    first.start()
    second.start()
    assert concurrent_requests_started.wait(timeout=1)
    release_concurrent_requests.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(requests) == 3
    assert [request.headers.get("cookie") for request in requests] == [None, None, None]


def test_get_text_returns_html_without_json_processing_and_decodes_korean_utf8() -> None:
    body = (
        b")]}',\n<html><body>"
        b"\xec\x95\x88\xeb\x85\x95\xed\x95\x98\xec\x84\xb8\xec\x9a\x94"
        b"</body></html>"
    )
    client = _client(
        lambda request: httpx.Response(
            200, content=body, headers={"Content-Type": "text/html; charset=utf-8"}
        )
    )

    assert (
        client.get_text(RequestSpec("https://section.blog.naver.com/PostList.naver", {}))
        == ")]}',\n<html><body>안녕하세요</body></html>"
    )


def test_get_text_uses_the_existing_not_found_and_non_200_mappings() -> None:
    not_found = _client(
        lambda request: httpx.Response(404, json={"error": {"code": "not_exist_post"}})
    )
    unexpected = _client(lambda request: httpx.Response(500, content=b"<html>error</html>"))
    spec = RequestSpec("https://m.blog.naver.com/post", {})

    with pytest.raises(NotFoundError):
        not_found.get_text(spec)
    with pytest.raises(AgenticBlogError, match="HTTP 500"):
        unexpected.get_text(spec)


def test_get_text_does_not_follow_redirects() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.host != "m.blog.naver.com":
            raise AssertionError("redirect was followed")
        return httpx.Response(302, headers={"Location": "https://external.example/landing"})

    clock = FakeClock()
    client = ReadClient(
        httpx.MockTransport(handler),
        request_pause=0,
        clock=clock.clock,
        sleep=clock.sleep,
    )

    with pytest.raises(AgenticBlogError, match="HTTP 302"):
        client.get_text(RequestSpec("https://m.blog.naver.com/post", {}))

    assert requests == ["https://m.blog.naver.com/post"]


def test_get_text_shares_json_budget_pacing_and_request_counter() -> None:
    clock = FakeClock()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={})
        return httpx.Response(200, content=b"<html>post</html>")

    client = _client(handler, clock=clock, max_requests=2)
    json_spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})
    html_spec = RequestSpec("https://m.blog.naver.com/post", {})

    assert client.get_json(json_spec) == {}
    clock.now += 0.2
    assert client.get_text(html_spec) == "<html>post</html>"
    with pytest.raises(AgenticBlogError, match="budget exhausted"):
        client.get_text(html_spec)

    assert len(requests) == 2
    assert client.requests_made == 2
    assert client.remaining_requests == 0
    assert clock.sleeps == pytest.approx([0.5, 0.3])


@pytest.mark.parametrize(
    "location",
    ["http://external.example/landing", "https://external.example/landing"],
    ids=["external-http", "non-naver"],
)
def test_get_json_does_not_follow_redirects(location: str) -> None:
    clock = FakeClock()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.host != "m.blog.naver.com":
            raise AssertionError("redirect was followed")
        return httpx.Response(302, headers={"Location": location})

    client = ReadClient(
        httpx.MockTransport(handler),
        request_pause=0,
        clock=clock.clock,
        sleep=clock.sleep,
    )

    with pytest.raises(AgenticBlogError, match="HTTP 302"):
        client.get_json(RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {}))

    assert requests == ["https://m.blog.naver.com/api/blogs/example/category-list"]


def test_pacing_clamps_the_first_and_later_requests() -> None:
    clock = FakeClock()
    client = _client(lambda request: httpx.Response(200, json={}), clock=clock)
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})

    client.get_json(spec)
    clock.now += 0.2
    client.get_json(spec)

    assert clock.sleeps == pytest.approx([0.5, 0.3])
    client.request_pause = 0
    assert client.request_pause == config.MIN_REQUEST_PAUSE_SECONDS


def test_pacing_does_not_require_clock_advance_when_no_wait_is_needed() -> None:
    clock = FakeClock()
    client = _client(lambda request: httpx.Response(200, json={}), clock=clock)
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})

    client.get_json(spec)
    clock.now += client.request_pause
    client.get_json(spec)

    assert clock.sleeps == pytest.approx([config.MIN_REQUEST_PAUSE_SECONDS])


def test_pacing_rejects_a_backward_monotonic_clock() -> None:
    clock = FakeClock()
    requests: list[httpx.Request] = []
    client = _client(
        lambda request: requests.append(request) or httpx.Response(200, json={}),
        clock=clock,
    )
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})

    client.get_json(spec)
    clock.now = 0.0

    with pytest.raises(AgenticBlogError, match="monotonic clock moved backwards"):
        client.get_json(spec)

    assert len(requests) == 1
    assert clock.sleeps == [config.MIN_REQUEST_PAUSE_SECONDS]
    assert client.requests_made == 1


@pytest.mark.parametrize(
    "clock_output",
    [float("inf"), float("-inf"), float("nan"), True, None, "not-a-number"],
    ids=["positive-infinity", "negative-infinity", "nan", "boolean", "none", "string"],
)
def test_pacing_rejects_invalid_monotonic_clock_outputs(clock_output: object) -> None:
    requests: list[httpx.Request] = []
    client = ReadClient(
        httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={})
        ),
        request_pause=0,
        clock=lambda: clock_output,  # type: ignore[return-value]
        sleep=lambda delay: None,
    )

    with pytest.raises(AgenticBlogError, match="monotonic clock returned an invalid value"):
        client.get_json(RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {}))

    assert requests == []
    assert client.requests_made == 0


def test_budget_is_non_bypassable_and_counts_attempted_requests() -> None:
    client = _client(lambda request: httpx.Response(200, json={}), max_requests=1)
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})

    client.get_json(spec)
    with pytest.raises(AgenticBlogError, match="budget exhausted"):
        client.get_json(spec)
    assert client.requests_made == 1
    assert client.remaining_requests == 0


def test_429_exposes_parseable_retry_after() -> None:
    client = _client(lambda request: httpx.Response(429, headers={"Retry-After": "2.5"}))

    with pytest.raises(RateLimitedError) as raised:
        client.get_json(RequestSpec("https://section.blog.naver.com/ajax/SearchList.naver", {}))

    assert raised.value.retry_after == 2.5


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"isSuccess": False, "error": {"code": "blog_id_invalidate"}}),
        (404, {"error": {"code": "not_exist_post"}}),
    ],
)
def test_only_measured_nonexistent_envelopes_map_to_not_found(status: int, body: dict) -> None:
    client = _client(lambda request: httpx.Response(status, json=body))

    with pytest.raises(NotFoundError):
        client.get_json(RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {}))


def test_malformed_and_nonobject_json_are_envelope_errors() -> None:
    malformed = _client(lambda request: httpx.Response(200, content=b"nope"))
    nonobject = _client(lambda request: httpx.Response(200, content=b"[]"))
    spec = RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {})

    with pytest.raises(EnvelopeParseError, match="malformed JSON"):
        malformed.get_json(spec)
    with pytest.raises(EnvelopeParseError, match="non-object"):
        nonobject.get_json(spec)


def test_transport_failure_does_not_leak_url_or_query_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret diagnostic", request=request)

    client = _client(handler)
    spec = RequestSpec(
        "https://m.blog.naver.com/api/blogs/example/category-list",
        {"keyword": "sensitive-value"},
    )

    with pytest.raises(AgenticBlogError) as raised:
        client.get_json(spec)

    assert "ConnectError" in str(raised.value)
    assert "secret diagnostic" not in str(raised.value)
    assert "sensitive-value" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_diagnostics_strip_pstatic_queries_before_truncating_free_text() -> None:
    signed_url = "https://postfiles.pstatic.net/image.jpg?Signature=secret&expires=123"
    message = f"response: {signed_url} {'x' * 300}"

    assert redact_url(signed_url) == "https://postfiles.pstatic.net/image.jpg"
    assert redact_url("https://example.com/image.jpg?token=kept") == (
        "https://example.com/image.jpg?token=kept"
    )
    assert "secret" not in redact_diagnostic(message)
    assert len(redact_diagnostic(message)) <= 240

    error = AgenticBlogError(message)
    assert "secret" not in str(error)
    assert error.diagnostic_message(redact=False) == message


@pytest.mark.parametrize(
    "url",
    [
        "http://m.blog.naver.com/api/blogs/example/category-list",
        "https://user@m.blog.naver.com/api/blogs/example/category-list",
        "https://m.blog.naver.com:444/api/blogs/example/category-list",
        "https://m.blog.naver.com.evil.example/api/blogs/example/category-list",
        "https://m.blog.naver.com./api/blogs/example/category-list",
    ],
)
def test_rejected_authorities_consume_no_budget_pacing_or_transport(url: str) -> None:
    clock = FakeClock()
    requests: list[httpx.Request] = []
    client = _client(
        lambda request: requests.append(request) or httpx.Response(200, json={}),
        clock=clock,
        max_requests=0,
    )

    with pytest.raises(ValueError, match="supported HTTPS Naver URL"):
        client.get_json(RequestSpec(url, {}))

    assert clock.sleeps == []
    assert requests == []
    assert client.requests_made == 0


def test_request_budget_state_is_read_only_without_duplicate_aliases() -> None:
    client = _client(lambda request: httpx.Response(200, json={}), max_requests=3)

    assert client.max_requests == 3
    assert client.requests_made == 0
    assert not hasattr(client, "min_pause")
    assert not hasattr(client, "request_count")
    with pytest.raises(AttributeError):
        client.max_requests = 4  # type: ignore[misc]
    with pytest.raises(AttributeError):
        client.requests_made = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_requests": True}, "max_requests must be a non-negative integer"),
        ({"max_requests": 1.0}, "max_requests must be a non-negative integer"),
        ({"max_requests": -1}, "max_requests must be a non-negative integer"),
        ({"request_pause": True}, "request_pause must be a finite number"),
        ({"request_pause": "0.5"}, "request_pause must be a finite number"),
        ({"request_pause": float("nan")}, "request_pause must be a finite number"),
    ],
)
def test_client_rejects_non_scalar_or_invalid_limits(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        ReadClient(**kwargs)


def test_throttle_rejects_a_sleeper_that_does_not_advance_monotonic_time() -> None:
    clock = FakeClock()
    requests: list[httpx.Request] = []
    client = ReadClient(
        httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={})
        ),
        request_pause=0,
        clock=clock.clock,
        sleep=lambda delay: clock.sleeps.append(delay),
    )

    with pytest.raises(AgenticBlogError, match="did not advance monotonic time"):
        client.get_json(RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {}))

    assert clock.sleeps == [config.MIN_REQUEST_PAUSE_SECONDS]
    assert requests == []
    assert client.requests_made == 0


def test_429_parses_http_date_retry_after() -> None:
    retry_at = datetime.now(UTC) + timedelta(seconds=30)
    client = _client(
        lambda request: httpx.Response(
            429, headers={"Retry-After": format_datetime(retry_at, usegmt=True)}
        )
    )

    with pytest.raises(RateLimitedError) as raised:
        client.get_json(RequestSpec("https://section.blog.naver.com/ajax/SearchList.naver", {}))

    assert 0 < raised.value.retry_after <= 30


@pytest.mark.parametrize("status", [400, 404, 500])
def test_non_200_decode_failures_do_not_replace_http_status(status: int) -> None:
    client = _client(lambda request: httpx.Response(status, content=b"\xff"))

    with pytest.raises(AgenticBlogError, match=rf"HTTP {status}"):
        client.get_json(RequestSpec("https://m.blog.naver.com/api/blogs/example/category-list", {}))


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('<script>location.href="MobileErrorView.naver?errorType=noPost";</script>', True),
        ('<script>location.href="MobileErrorView.naver?errorType=other";</script>', False),
        ('<script>location.href="MobileErrorView.naver?errorType=noPost&extra=1";</script>', False),
        ('<script>location.replace("MobileErrorView.naver?errorType=noPost");</script>', False),
        ("MobileErrorView.naver?errorType=noPost", False),
    ],
)
def test_mobile_no_post_redirect_requires_the_exact_measured_structure(
    body: str, expected: bool
) -> None:
    client = _client(lambda request: httpx.Response(404, content=body.encode()))

    if expected:
        with pytest.raises(NotFoundError):
            client.get_json(RequestSpec("https://m.blog.naver.com/post", {}))
    else:
        with pytest.raises(AgenticBlogError, match="HTTP 404"):
            client.get_json(RequestSpec("https://m.blog.naver.com/post", {}))
