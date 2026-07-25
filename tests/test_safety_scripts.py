from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pii = _module("check_fixtures_pii", "check_fixtures_pii.py")
recorder = _module("record_fixture", "record_fixture.py")


def test_scanner_fails_closed_for_missing_and_empty_corpora(tmp_path: Path) -> None:
    assert pii.scan_fixtures(tmp_path / "missing") == ["fixtures: unsafe-corpus"]
    assert pii.scan_fixtures(tmp_path) == ["fixtures: unsafe-corpus"]


def test_scanner_rejects_symlink_and_detects_encoded_structural_pii(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "outside.json"
    target.write_text('{"phone": "01012345678"}', encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    assert pii.scan_file(link) == ["link.json: unsafe-file"]

    fixture = tmp_path / "encoded.json"
    fixture.write_text(
        (
            '{"apiKey": "ignored", "text": "010%2D1234%2D5678 //evil.example", '
            '"url": "https&#58;//evil.example"}'
        ),
        encoding="utf-8",
    )
    findings = pii.scan_file(fixture)
    assert "encoded.json: credential-key" in findings
    assert "encoded.json: phone" in findings
    assert "encoded.json: forbidden-host" in findings
    original_read = pii._read_fixture

    def replace_before_open(directory_fd: int, path: Path, initial: os.stat_result) -> str:
        path.write_text('{"changed": true}', encoding="utf-8")
        return original_read(directory_fd, path, initial)

    monkeypatch.setattr(pii, "_read_fixture", replace_before_open)
    assert pii.scan_file(fixture) == ["encoded.json: unsafe-file"]


def test_scanner_limits_boolean_secret_exemption_to_comment_cards(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text('{"secret": true}', encoding="utf-8")
    comment = tmp_path / "comment.json"
    comment.write_text(
        '{"commentNo":"1","parentCommentNo":"1","replyLevel":1,"secret":true}',
        encoding="utf-8",
    )

    assert pii.scan_file(unsafe) == ["unsafe.json: credential-key"]
    assert pii.scan_file(comment) == []


def test_scanner_refuses_missing_nofollow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = tmp_path / "safe.json"
    fixture.write_text("{}", encoding="utf-8")
    monkeypatch.delattr(pii.os, "O_NOFOLLOW", raising=False)
    assert pii.scan_fixtures(tmp_path) == ["fixtures: unsafe-corpus"]


@pytest.mark.parametrize(
    "url",
    [
        "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=synthetic&orderBy=date&startDate=2026-01-01&endDate=2026-01-31&currentPage=1&countPerPage=7",
        "https://section.blog.naver.com/ajax/DirectoryList.naver",
        "https://section.blog.naver.com/ajax/DirectoryPostList.naver?directorySeq=1&pageNo=1",
        "https://section.blog.naver.com/ajax/DirectoryTopPostList.naver?directorySeq=1",
        "https://m.blog.naver.com/api/blogs/synthetic_alice/category-list",
        "https://m.blog.naver.com/api/blogs/synthetic_alice/post-list?categoryNo=0&itemCount=30&page=1",
        "https://m.blog.naver.com/api/blogs/synthetic_alice/public-buddies?pageNo=1",
        "https://m.blog.naver.com/api/blogs/synthetic_alice/posts/1/comments-info",
        "https://m.blog.naver.com/synthetic_alice/1",
        "https://blog.naver.com/PostSearchList.naver?blogId=synthetic_alice&SearchText=synthetic&orderBy=recentdate&currentPage=1",
    ],
)
def test_recorder_accepts_only_documented_read_shapes(url: str) -> None:
    assert recorder._validate_url(url).startswith("https://")


@pytest.mark.parametrize(
    "url",
    [
        "https://section.blog.naver.com/ajax/SearchList.naver?type=post",
        "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x&type=blog",
        "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x&unknown=y",
        "https://section.blog.naver.com/ajax/SearchList.naver?type=%2574elemetry&keyword=x",
        "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x%26token%3Dy",
        "https://m.blog.naver.com/synthetic_alice/post-list?pageNo=1",
        "https://m.blog.naver.com/api/blogs/synthetic_alice/post-list?categoryNo=0&itemCount=30&page=1&token=x",
        "https://m.blog.naver.com/api/blogs/synthetic_alice/1?x=y",
        "https://section.blog.naver.com//ajax/SearchList.naver?type=post&keyword=x",
        "https://evil.example/ajax/SearchList.naver?type=post&keyword=x",
    ],
)
def test_recorder_rejects_encoded_or_action_url_bypasses(url: str) -> None:
    with pytest.raises(recorder.CaptureError):
        recorder._validate_url(url)


def test_recorder_refuses_scratch_symlink_and_missing_nofollow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    scratch = tmp_path / "scratch"
    scratch.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(recorder, "SCRATCH_DIR", scratch)
    with pytest.raises(recorder.CaptureError):
        recorder._open_scratch()
    monkeypatch.delattr(recorder.os, "O_NOFOLLOW", raising=False)
    with pytest.raises(recorder.CaptureError):
        recorder._open_scratch()


def test_bounded_write_fsyncs_and_removes_partial_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(recorder, "SCRATCH_DIR", tmp_path / "scratch")
    destination = recorder._destination("scratch/capture.raw.json")
    fsync_calls: list[int] = []
    monkeypatch.setattr(recorder.os, "fsync", lambda descriptor: fsync_calls.append(descriptor))
    assert (
        recorder._write_capture(destination, [b"ok"], recorder.time.monotonic() + 1)
        == destination.path
    )
    assert destination.path.read_bytes() == b"ok"
    assert fsync_calls

    partial = recorder._destination("scratch/partial.raw.json")
    original_max_capture_bytes = recorder.MAX_CAPTURE_BYTES
    monkeypatch.setattr(recorder, "MAX_CAPTURE_BYTES", 1)
    with pytest.raises(recorder.CaptureError):
        recorder._write_capture(partial, [b"too large"], recorder.time.monotonic() + 1)
    assert not partial.path.exists()

    expired = recorder._destination("scratch/expired.raw.json")
    with pytest.raises(recorder.CaptureError):
        recorder._write_capture(expired, [b"data"], recorder.time.monotonic() - 1)
    assert not expired.path.exists()

    monkeypatch.setattr(recorder, "MAX_CAPTURE_BYTES", original_max_capture_bytes)
    fsync_failure = recorder._destination("scratch/fsync.raw.json")
    fsync_failure_calls: list[int] = []

    def failing_fsync(descriptor: int) -> None:
        fsync_failure_calls.append(descriptor)
        raise OSError("no sync")

    monkeypatch.setattr(recorder.os, "fsync", failing_fsync)
    with pytest.raises(recorder.CaptureError):
        recorder._write_capture(fsync_failure, [b"data"], recorder.time.monotonic() + 1)
    assert fsync_failure_calls
    assert not fsync_failure.path.exists()
    eof_expired = recorder._destination("scratch/eof-expired.raw.json")
    clock = [0.0]

    def eof_after_chunk():
        yield b"data"
        clock[0] = 2.0

    monkeypatch.setattr(recorder.time, "monotonic", lambda: clock[0])
    with pytest.raises(recorder.CaptureError, match="deadline"):
        recorder._write_capture(eof_expired, eof_after_chunk(), 1.0)
    assert not eof_expired.path.exists()

    fsync_expired = recorder._destination("scratch/fsync-expired.raw.json")
    clock[0] = 0.0

    def expire_during_fsync(descriptor: int) -> None:
        clock[0] = 2.0

    monkeypatch.setattr(recorder.os, "fsync", expire_during_fsync)
    with pytest.raises(recorder.CaptureError, match="deadline"):
        recorder._write_capture(fsync_expired, [b"data"], 1.0)
    assert not fsync_expired.path.exists()


def test_record_rejects_redirects_and_cookies_before_creating_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(recorder, "SCRATCH_DIR", tmp_path / "scratch")

    class Response:
        headers = {"set-cookie": "session=x"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            raise recorder.httpx.HTTPStatusError("redirect", request=None, response=None)

        def iter_bytes(self):
            return iter((b"unexpected",))

    class Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def close(self):
            return None

        def stream(self, method, url):
            assert method == "GET"
            assert self.kwargs["follow_redirects"] is False
            return Response()

    monkeypatch.setattr(recorder.httpx, "Client", Client)
    with pytest.raises(recorder.CaptureError):
        recorder.record(
            "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x",
            "scratch/redirect.raw.json",
        )
    assert not (tmp_path / "scratch" / "redirect.raw.json").exists()

    class CookieResponse(Response):
        def raise_for_status(self):
            return None

    class CookieClient(Client):
        def stream(self, method, url):
            return CookieResponse()

    monkeypatch.setattr(recorder.httpx, "Client", CookieClient)
    with pytest.raises(recorder.CaptureError):
        recorder.record(
            "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x",
            "scratch/cookie.raw.json",
        )
    assert not (tmp_path / "scratch" / "cookie.raw.json").exists()


def test_scanner_checks_json_keys_names_and_budgets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    keyed = tmp_path / "keyed.json"
    keyed.write_text('{"https://evil.example": "ok"}', encoding="utf-8")
    assert "keyed.json: forbidden-host" in pii.scan_file(keyed)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"safe": 1, "safe": 2}', encoding="utf-8")
    assert pii.scan_file(duplicate) == ["duplicate.json: invalid-json"]

    safe_html = tmp_path / "safe.html"
    safe_html.write_text('<span class="nickname">김테스트</span>', encoding="utf-8")
    assert pii.scan_file(safe_html) == []
    risky_html = tmp_path / "risky.html"
    risky_html.write_text('<span class="nickname">김민수</span>', encoding="utf-8")
    assert pii.scan_file(risky_html) == ["risky.html: korean-name"]

    monkeypatch.setattr(pii, "MAX_NESTING_DEPTH", 1)
    nested = tmp_path / "nested.json"
    nested.write_text('{"a": {"b": {"c": 1}}}', encoding="utf-8")
    assert pii.scan_file(nested) == ["nested.json: unsafe-file"]

    unsupported = tmp_path / "unsupported"
    unsupported.mkdir()
    (unsupported / "nested").mkdir()
    (unsupported / "nested" / "nested.json").write_text("{}", encoding="utf-8")
    assert pii.scan_fixtures(unsupported) == ["fixtures: unsafe-corpus"]
    nested_html = tmp_path / "nested.html"
    nested_html.write_text(
        '<div class="displayName"><strong>&#44608;민수</strong></div>',
        encoding="utf-8",
    )
    assert pii.scan_file(nested_html) == ["nested.html: korean-name"]
    synthetic_html = tmp_path / "synthetic.html"
    synthetic_html.write_text(
        '<div id="writer_name"><em>김테스트</em></div>',
        encoding="utf-8",
    )
    assert pii.scan_file(synthetic_html) == []
    attribute_html = tmp_path / "attribute.html"
    attribute_html.write_text('<span authorName="김민수"></span>', encoding="utf-8")
    assert pii.scan_file(attribute_html) == ["attribute.html: korean-name"]


def test_scanner_rejects_html_node_count_over_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pii, "MAX_HTML_NODES", 1)
    html_file = tmp_path / "too-many-nodes.html"
    html_file.write_text("<span></span><span></span>", encoding="utf-8")
    assert pii.scan_file(html_file) == ["too-many-nodes.html: unsafe-file"]


def test_scanner_rejects_html_nesting_over_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pii, "MAX_HTML_DEPTH", 1)
    html_file = tmp_path / "too-deep.html"
    html_file.write_text("<span><em>text</em></span>", encoding="utf-8")
    assert pii.scan_file(html_file) == ["too-deep.html: unsafe-file"]


def test_scanner_rejects_decoded_html_text_bytes_over_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pii, "MAX_HTML_TEXT_BYTES", 2)
    html_file = tmp_path / "too-much-decoded-text.html"
    html_file.write_text("<span>&#44032;</span>", encoding="utf-8")
    assert pii.scan_file(html_file) == ["too-much-decoded-text.html: unsafe-file"]


def test_recorder_cli_diagnostics_omit_url_sentinel(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "DO-NOT-PRINT-QUERY-VALUE"

    def fail(url: str, output: str) -> Path:
        raise recorder.CaptureError(f"failed {url}")

    monkeypatch.setattr(recorder, "record", fail)
    assert (
        recorder.main(
            [
                f"https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword={sentinel}",
                "scratch/sentinel.raw.json",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert sentinel not in captured.err
    assert "CaptureError" in captured.err


def test_recorder_accepts_exact_cbox_schema_and_rejects_missing_member() -> None:
    query = (
        "ticket=blog&pool=blogid&objectId=1_201_2&groupId=1&templateId=default&lang=ko"
        "&country=&_cv=&pageType=more&listType=OBJECT&page=1&pageSize=10&indexSize=10"
        "&replyPageSize=10&followSize=5&initialize=true&useAltSort=true&userType="
        "&categoryId=&sort=NEW"
    )
    url = f"https://apis.naver.com/commentBox/cbox/web_naver_list_json.json?{query}"
    assert recorder._validate_url(url).startswith("https://apis.naver.com/")
    with pytest.raises(recorder.CaptureError):
        recorder._validate_url(url.replace("&followSize=5", ""))


def test_scanner_item_and_byte_budgets_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pii, "MAX_FIXTURE_ITEMS", 2)
    items = tmp_path / "items.json"
    items.write_text("[1, 2]", encoding="utf-8")
    assert pii.scan_file(items) == ["items.json: unsafe-file"]

    monkeypatch.setattr(pii, "MAX_FIXTURE_BYTES", 1)
    bytes_file = tmp_path / "bytes.json"
    bytes_file.write_text("{}", encoding="utf-8")
    assert pii.scan_file(bytes_file) == ["bytes.json: unsafe-file"]

    monkeypatch.setattr(pii, "MAX_FIXTURE_BYTES", 100)
    monkeypatch.setattr(pii, "MAX_CORPUS_BYTES", 3)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.json").write_text("{}", encoding="utf-8")
    (corpus / "b.json").write_text("{}", encoding="utf-8")
    assert pii.scan_fixtures(corpus) == ["fixtures: unsafe-corpus"]
    monkeypatch.setattr(pii, "MAX_FIXTURE_COUNT", 1)
    count_limited = tmp_path / "count-limited"
    count_limited.mkdir()
    (count_limited / "a.json").write_text("{}", encoding="utf-8")
    (count_limited / "b.json").write_text("{}", encoding="utf-8")
    assert pii.scan_fixtures(count_limited) == ["fixtures: unsafe-corpus"]

    stat_error = tmp_path / "stat-error"
    stat_error.mkdir()
    (stat_error / "a.json").write_text("{}", encoding="utf-8")
    original_stat = pii.os.stat

    def failing_stat(path, *args, **kwargs):
        if path == "a.json":
            raise OSError("DO-NOT-PRINT-STAT-SENTINEL")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(pii.os, "stat", failing_stat)
    findings = pii.scan_fixtures(stat_error)
    assert findings == ["fixtures: unsafe-corpus"]
    assert "DO-NOT-PRINT-STAT-SENTINEL" not in "\n".join(findings)


def test_record_deadline_closes_delayed_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recorder, "CAPTURE_DEADLINE_SECONDS", 0.01)
    closed = False

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def close(self):
            nonlocal closed
            closed = True

        def stream(self, method, url):
            for _ in range(20):
                if closed:
                    break
                recorder.time.sleep(0.001)
            raise recorder.httpx.ReadTimeout("deadline")

    monkeypatch.setattr(recorder.httpx, "Client", Client)
    with pytest.raises(recorder.CaptureError, match="deadline"):
        recorder.record(
            "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x",
            "scratch/transport.raw.json",
        )
    assert closed


def test_record_deadline_closes_transport_and_removes_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(recorder, "SCRATCH_DIR", tmp_path / "scratch")
    monkeypatch.setattr(recorder, "CAPTURE_DEADLINE_SECONDS", 0.01)
    closed = False

    class Response:
        headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield b"partial"
            for _ in range(20):
                if closed:
                    break
                recorder.time.sleep(0.001)
            raise recorder.httpx.ReadTimeout("deadline")

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def close(self):
            nonlocal closed
            closed = True

        def stream(self, method, url):
            return Response()

    monkeypatch.setattr(recorder.httpx, "Client", Client)
    with pytest.raises(recorder.CaptureError, match="deadline"):
        recorder.record(
            "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x",
            "scratch/deadline.raw.json",
        )
    assert closed
    assert not (tmp_path / "scratch" / "deadline.raw.json").exists()

    class BoundedResponse(Response):
        def iter_bytes(self):
            yield b"partial"
            recorder.time.sleep(0.02)
            raise recorder.httpx.ReadTimeout("deadline")

    class BoundedClient(Client):
        def stream(self, method, url):
            return BoundedResponse()

    monkeypatch.setattr(recorder.httpx, "Client", BoundedClient)
    with pytest.raises(recorder.CaptureError, match="deadline"):
        recorder.record(
            "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x",
            "scratch/bounded-deadline.raw.json",
        )
    assert not (tmp_path / "scratch" / "bounded-deadline.raw.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("ticket", "other"),
        ("pool", "other"),
        ("objectId", "1_202_2"),
        ("groupId", "2"),
        ("templateId", "other"),
        ("lang", "en"),
        ("country", "KR"),
        ("_cv", "1"),
        ("pageType", "list"),
        ("listType", "LIST"),
        ("page", "0"),
        ("pageSize", "0"),
        ("indexSize", "9"),
        ("replyPageSize", "9"),
        ("followSize", "4"),
        ("initialize", "false"),
        ("useAltSort", "false"),
        ("userType", "member"),
        ("categoryId", "1"),
        ("sort", "OLD"),
    ],
)
def test_recorder_rejects_cbox_value_mutations(field: str, value: str) -> None:
    query = {
        "ticket": "blog",
        "pool": "blogid",
        "objectId": "1_201_2",
        "groupId": "1",
        "templateId": "default",
        "lang": "ko",
        "country": "",
        "_cv": "",
        "pageType": "more",
        "listType": "OBJECT",
        "page": "1",
        "pageSize": "10",
        "indexSize": "10",
        "replyPageSize": "10",
        "followSize": "5",
        "initialize": "true",
        "useAltSort": "true",
        "userType": "",
        "categoryId": "",
        "sort": "NEW",
    }
    query[field] = value
    url = "https://apis.naver.com/commentBox/cbox/web_naver_list_json.json?" + "&".join(
        f"{key}={value}" for key, value in query.items()
    )
    with pytest.raises(recorder.CaptureError):
        recorder._validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x&orderBy=recentdate",
        "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x&startDate=2026-02-30",
        "https://section.blog.naver.com/ajax/SearchList.naver?type=post&keyword=x&currentPage=0",
        "https://section.blog.naver.com/ajax/DirectoryPostList.naver?directorySeq=0&pageNo=1",
        "https://m.blog.naver.com/api/blogs/synthetic/post-list?categoryNo=0&itemCount=31&page=1",
        "https://m.blog.naver.com/api/blogs/synthetic/public-buddies?pageNo=0",
    ],
)
def test_recorder_rejects_query_value_boundaries(url: str) -> None:
    with pytest.raises(recorder.CaptureError):
        recorder._validate_url(url)
