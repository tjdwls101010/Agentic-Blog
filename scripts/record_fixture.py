#!/usr/bin/env python3
"""Capture one approved anonymous read response into gitignored ``scratch/``."""

from __future__ import annotations

import argparse
import html
import os
import re
import stat
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Timer
from urllib.parse import quote, unquote_to_bytes, urlsplit, urlunsplit

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRATCH_DIR = PROJECT_ROOT / "scratch"
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600
MAX_CAPTURE_BYTES = 2 * 1024 * 1024
CAPTURE_DEADLINE_SECONDS = 20.0
_ALLOWED_HOSTS = frozenset(
    {"blog.naver.com", "m.blog.naver.com", "section.blog.naver.com", "apis.naver.com"}
)
_FORBIDDEN_WORDS = frozenset(
    {
        "authorization",
        "cookie",
        "create",
        "delete",
        "modify",
        "password",
        "save",
        "secret",
        "session",
        "telemetry",
        "token",
        "tracking",
        "upload",
        "view_log",
        "web_naver_view_log_json",
        "write",
    }
)
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.raw\.(?:json|html)")
_HEADERS = {
    "Referer": "https://blog.naver.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}
_WARNING = "WARNING: raw captures may contain PII. Never commit or copy them into tests/fixtures/."


class CaptureError(ValueError):
    """Raised when a requested capture violates recorder safety rules."""


@dataclass(frozen=True)
class Destination:
    filename: str
    path: Path


def _require_flag(name: str) -> int:
    flag = getattr(os, name, 0)
    if not flag:
        raise CaptureError(f"platform lacks required {name}")
    return flag


def _decode_component(value: str) -> str:
    current = value
    for _ in range(3):
        if "%" in current:
            if re.search(r"%(?![0-9A-Fa-f]{2})", current):
                raise CaptureError("URL contains malformed percent encoding")
            try:
                decoded = unquote_to_bytes(current).decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise CaptureError("URL contains invalid UTF-8 encoding") from exc
        else:
            decoded = current
        decoded = html.unescape(decoded)
        if decoded == current:
            return decoded
        current = decoded
    if "%" in current or html.unescape(current) != current:
        raise CaptureError("URL encoding is nested or ambiguous")
    return current


def _safe_query(query: str) -> dict[str, str]:
    if not query:
        return {}
    pairs: dict[str, str] = {}
    for item in query.split("&"):
        if not item:
            raise CaptureError("URL query contains an empty component")
        raw_key, separator, raw_value = item.partition("=")
        if not separator:
            raise CaptureError("URL query must use key=value components")
        key, value = _decode_component(raw_key), _decode_component(raw_value)
        if (
            not key
            or key in pairs
            or any(word in key.lower() for word in _FORBIDDEN_WORDS)
            or any(character in key + value for character in "&=#?")
        ):
            raise CaptureError("URL query is ambiguous or contains credentials or action semantics")
        pairs[key] = value
    return pairs


def _positive_number(value: str, maximum: int | None = None) -> bool:
    if not re.fullmatch(r"[1-9][0-9]{0,9}", value):
        return False
    return maximum is None or int(value) <= maximum


def _nonnegative_number(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{1,10}", value))


def _valid_date(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _approved_path(host: str, path: str, query: dict[str, str]) -> bool:
    section_schemas: dict[str, tuple[frozenset[str], frozenset[str]]] = {
        "/ajax/SearchList.naver": (
            frozenset(
                {
                    "type",
                    "keyword",
                    "orderBy",
                    "startDate",
                    "endDate",
                    "currentPage",
                    "countPerPage",
                }
            ),
            frozenset({"type", "keyword"}),
        ),
        "/ajax/DirectoryList.naver": (frozenset(), frozenset()),
        "/ajax/DirectoryPostList.naver": (
            frozenset({"directorySeq", "pageNo"}),
            frozenset({"directorySeq", "pageNo"}),
        ),
        "/ajax/DirectoryTopPostList.naver": (
            frozenset({"directorySeq"}),
            frozenset({"directorySeq"}),
        ),
    }
    if host == "section.blog.naver.com":
        allowed, required = section_schemas.get(path, (frozenset({"__invalid__"}), frozenset()))
        if not required <= query.keys() or not query.keys() <= allowed:
            return False
        if path == "/ajax/SearchList.naver":
            search_type = query["type"]
            if not query["keyword"] or search_type not in {"post", "blog", "id"}:
                return False
            if search_type == "id" and ({"orderBy", "startDate", "endDate"} & query.keys()):
                return False
            if search_type == "blog" and ({"startDate", "endDate"} & query.keys()):
                return False
            if "orderBy" in query and query["orderBy"] not in {"sim", "date"}:
                return False
            if any(
                not _valid_date(query[name]) for name in {"startDate", "endDate"} & query.keys()
            ):
                return False
            if {"startDate", "endDate"} <= query.keys() and query["startDate"] > query["endDate"]:
                return False
            return all(
                _positive_number(query[name])
                for name in {"currentPage", "countPerPage"} & query.keys()
            )
        if path == "/ajax/DirectoryPostList.naver":
            return all(_positive_number(query[name]) for name in ("directorySeq", "pageNo"))
        if path == "/ajax/DirectoryTopPostList.naver":
            return _positive_number(query["directorySeq"])
        return True
    if host == "blog.naver.com":
        return (
            path == "/PostSearchList.naver"
            and set(query) == {"blogId", "SearchText", "orderBy", "currentPage"}
            and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", query["blogId"]))
            and query["orderBy"] == "recentdate"
            and _positive_number(query["currentPage"])
        )
    if host == "apis.naver.com":
        if path != "/commentBox/cbox/web_naver_list_json.json" or set(query) != {
            "ticket",
            "pool",
            "objectId",
            "groupId",
            "templateId",
            "lang",
            "country",
            "_cv",
            "pageType",
            "listType",
            "page",
            "pageSize",
            "indexSize",
            "replyPageSize",
            "followSize",
            "initialize",
            "useAltSort",
            "userType",
            "categoryId",
            "sort",
        }:
            return False
        object_id = re.fullmatch(r"([1-9][0-9]{0,9})_201_([1-9][0-9]{0,9})", query["objectId"])
        return (
            object_id is not None
            and query["groupId"] == object_id.group(1)
            and query["ticket"] == "blog"
            and query["pool"] == "blogid"
            and query["templateId"] == "default"
            and query["lang"] == "ko"
            and query["country"] == query["_cv"] == query["userType"] == query["categoryId"] == ""
            and query["pageType"] == "more"
            and query["listType"] == "OBJECT"
            and query["indexSize"] == "10"
            and query["replyPageSize"] == "10"
            and query["followSize"] == "5"
            and query["initialize"] == query["useAltSort"] == "true"
            and query["sort"] in {"NEW", "FAVORITE"}
            and _positive_number(query["page"])
            and _positive_number(query["pageSize"])
        )
    if host == "m.blog.naver.com":
        blog_id = r"[A-Za-z0-9_-]{1,100}"
        if re.fullmatch(rf"/api/blogs/{blog_id}/category-list", path):
            return not query
        if re.fullmatch(rf"/api/blogs/{blog_id}/post-list", path):
            return (
                set(query) == {"categoryNo", "itemCount", "page"}
                and _nonnegative_number(query["categoryNo"])
                and _positive_number(query["itemCount"], 30)
                and _positive_number(query["page"])
            )
        if re.fullmatch(rf"/api/blogs/{blog_id}/(?:notice-post-list|popular-post-list)", path):
            return not query
        if re.fullmatch(rf"/api/blogs/{blog_id}/public-buddies", path):
            return set(query) == {"pageNo"} and _positive_number(query["pageNo"])
        if re.fullmatch(rf"/api/blogs/{blog_id}/posts/[1-9][0-9]{{0,9}}/comments-info", path):
            return not query
        return bool(re.fullmatch(rf"/{blog_id}/[1-9][0-9]{{0,9}}", path) and not query)
    return False


def _validate_url(url: str) -> str:
    if (
        not isinstance(url, str)
        or not url
        or any(character.isspace() or ord(character) < 32 for character in url)
    ):
        raise CaptureError("URL must not contain whitespace or control characters")
    rendered = re.sub(
        r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z]+;)",
        lambda match: html.unescape(match.group(0)),
        url,
    )
    parsed = urlsplit(rendered)
    if (
        parsed.scheme.lower() != "https"
        or parsed.username
        or parsed.password
        or parsed.port
        or not parsed.hostname
        or parsed.fragment
    ):
        raise CaptureError(
            "URL must be an anonymous HTTPS URL without credentials, a port, or a fragment"
        )
    host = _decode_component(parsed.hostname).lower().rstrip(".")
    if host not in _ALLOWED_HOSTS:
        raise CaptureError("URL host is not an approved anonymous read host")
    path = _decode_component(parsed.path)
    query = _safe_query(parsed.query)
    if (
        not path.startswith("/")
        or "//" in path
        or any(word in path.lower() for word in _FORBIDDEN_WORDS)
        or not _approved_path(host, path, query)
    ):
        raise CaptureError("URL is not an approved anonymous read endpoint")
    rendered_query = "&".join(
        f"{quote(key, safe='')}={quote(value, safe='')}" for key, value in query.items()
    )
    return urlunsplit(("https", host, quote(path, safe="/-._~"), rendered_query, ""))


def _destination(output: str) -> Destination:
    requested = Path(output)
    if requested.is_absolute() or requested.parts[:1] != ("scratch",) or len(requested.parts) != 2:
        raise CaptureError("output must be exactly scratch/NAME.raw.json or scratch/NAME.raw.html")
    filename = requested.name
    if not _NAME_RE.fullmatch(filename) or ".." in filename:
        raise CaptureError("output filename must be a safe raw JSON or HTML filename")
    return Destination(filename, SCRATCH_DIR / filename)


def _open_scratch() -> int:
    try:
        SCRATCH_DIR.mkdir(mode=_DIRECTORY_MODE)
    except FileExistsError:
        pass
    except OSError as exc:
        raise CaptureError("scratch directory could not be created safely") from exc
    flags = os.O_RDONLY | _require_flag("O_DIRECTORY") | _require_flag("O_NOFOLLOW")
    try:
        descriptor = os.open(SCRATCH_DIR, flags)
    except OSError as exc:
        raise CaptureError("scratch must be a real directory, not a symlink") from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise CaptureError("scratch must be a real directory, not a symlink")
    try:
        os.fchmod(descriptor, _DIRECTORY_MODE)
    except OSError as exc:
        os.close(descriptor)
        raise CaptureError("scratch directory permissions could not be secured") from exc
    return descriptor


def _write_capture(destination: Destination, chunks: Iterable[bytes], deadline: float) -> Path:
    if time.monotonic() >= deadline:
        raise CaptureError("capture exceeded total deadline")
    directory_descriptor = _open_scratch()
    descriptor = -1
    created = False
    completed = False
    try:
        if time.monotonic() >= deadline:
            raise CaptureError("capture exceeded total deadline")
        descriptor = os.open(
            destination.filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _require_flag("O_NOFOLLOW"),
            _FILE_MODE,
            dir_fd=directory_descriptor,
        )
        created = True
        os.fchmod(descriptor, _FILE_MODE)
        total = 0
        for chunk in chunks:
            if time.monotonic() >= deadline:
                raise CaptureError("capture exceeded total deadline")
            total += len(chunk)
            if total > MAX_CAPTURE_BYTES:
                raise CaptureError("capture exceeds maximum size")
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short capture write")
                view = view[written:]
        if time.monotonic() >= deadline:
            raise CaptureError("capture exceeded total deadline")
        os.fsync(descriptor)
        if time.monotonic() >= deadline:
            raise CaptureError("capture exceeded total deadline")
        completed = True
    except FileExistsError as exc:
        raise CaptureError("output already exists; refusing to overwrite it") from exc
    except OSError as exc:
        raise CaptureError("output could not be written safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            if created and not completed:
                try:
                    os.unlink(destination.filename, dir_fd=directory_descriptor)
                except OSError as exc:
                    raise CaptureError("partial capture could not be removed") from exc
        finally:
            os.close(directory_descriptor)
    return destination.path


def _deadline_error(exc: BaseException, host: str, path: str) -> CaptureError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else "unknown"
        return CaptureError(f"HTTP status {status} from {host}{path}")
    return CaptureError(f"{type(exc).__name__} from {host}{path}")


def record(url: str, output: str) -> Path:
    """Fetch one approved read URL and exclusively write its bounded body under scratch/."""
    safe_url = _validate_url(url)
    destination = _destination(output)
    parsed = urlsplit(safe_url)
    deadline = time.monotonic() + CAPTURE_DEADLINE_SECONDS
    client = httpx.Client(
        headers=_HEADERS, follow_redirects=False, cookies=None, timeout=CAPTURE_DEADLINE_SECONDS
    )
    timer = Timer(CAPTURE_DEADLINE_SECONDS, client.close)
    try:
        timer.start()
        with client:
            with client.stream("GET", safe_url) as response:
                response.raise_for_status()
                if response.headers.get("set-cookie"):
                    raise CaptureError(
                        "response set cookies; refusing to store a session-bearing capture"
                    )
                return _write_capture(destination, response.iter_bytes(), deadline)
    except CaptureError:
        raise
    except httpx.HTTPError as exc:
        if time.monotonic() >= deadline:
            raise CaptureError("capture exceeded total deadline") from exc
        raise _deadline_error(exc, parsed.hostname or "unknown", parsed.path) from exc
    finally:
        timer.cancel()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one anonymous Naver read response into scratch/."
    )
    parser.add_argument("url", help="approved HTTPS read URL")
    parser.add_argument(
        "output", help="explicit output: scratch/NAME.raw.json or scratch/NAME.raw.html"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(_WARNING, file=sys.stderr)
    try:
        destination = record(args.url, args.output)
    except (CaptureError, httpx.HTTPError) as exc:
        print(f"record_fixture: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
