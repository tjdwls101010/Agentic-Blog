#!/usr/bin/env python3
"""Reject structural signs of real data in committed synthetic fixtures."""

from __future__ import annotations

import html
import json
import math
import os
import re
import stat
import sys
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
CATEGORY_ORDER = (
    "unsafe-corpus",
    "unsafe-file",
    "invalid-json",
    "credential-key",
    "email",
    "phone",
    "forbidden-host",
    "real-capture-marker",
    "high-entropy-token",
    "korean-name",
)
MAX_FIXTURE_BYTES = 2 * 1024 * 1024
MAX_CORPUS_BYTES = 8 * 1024 * 1024
MAX_FIXTURE_COUNT = 10_000
MAX_FIXTURE_ITEMS = 10_000
MAX_NESTING_DEPTH = 32
MAX_HTML_NODES = 10_000
MAX_HTML_TEXT_BYTES = 256 * 1024
MAX_HTML_DEPTH = 64
_NAME_KEYS = frozenset(
    {
        "author",
        "author_name",
        "blog_name",
        "display_name",
        "name",
        "nickname",
        "profile_name",
        "user_name",
        "username",
        "writer",
        "writer_name",
    }
)
_SYNTHETIC_KOREAN_NAMES = frozenset(
    {
        "가나다",
        "가상사용자",
        "김테스트",
        "샘플사용자",
        "예시사용자",
        "테스트",
        "합성사용자",
        "홍길동",
    }
)
_ALLOWED_HOSTS = frozenset({"example.invalid", "pstatic.net"})
_REAL_CAPTURE_MARKERS = frozenset(
    {"jsessionid", "nid_aut", "nid_ses", "set-cookie", "web_naver_view_log_json"}
)
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}(?![A-Za-z0-9.\-])"
)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?82[- .]?)?01[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)")
_URL_RE = re.compile(r"(?i)(?:https?|wss?)://[^\s\"'<>]+|//[^\s\"'<>]+")
_BARE_HOST_RE = re.compile(r"(?i)^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\.?$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}(?:\.[A-Za-z0-9_\-]{8,})?\b")
_KOREAN_NAME_RE = re.compile(r"^[가-힣]{2,4}$")


class CorpusError(OSError):
    """The committed fixture corpus could not be safely scanned."""


class DuplicateJsonMemberError(ValueError):
    """JSON object contains a duplicate member name."""


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonMemberError
        result[key] = value
    return result


def _require_flag(name: str) -> int:
    flag = getattr(os, name, 0)
    if not flag:
        raise CorpusError(f"platform lacks required {name}")
    return flag


def _key_words(key: str) -> tuple[str, ...]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return tuple(part for part in re.split(r"[^a-z0-9]+", separated.lower()) if part)


def _normalised_key(key: str) -> str:
    return "_".join(_key_words(key))


def _credential_shaped_key(key: str) -> bool:
    words = _key_words(key)
    joined = "".join(words)
    return (
        any(
            word
            in {
                "authorization",
                "bearer",
                "cookie",
                "csrf",
                "password",
                "private",
                "secret",
                "session",
                "token",
            }
            for word in words
        )
        or any(
            term in joined
            for term in ("accesstoken", "apikey", "clientsecret", "privatekey", "sessionid")
        )
        or ({"api", "key"} <= set(words))
    )


def _allowed_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    hostname = hostname.lower().rstrip(".")
    return (
        hostname in _ALLOWED_HOSTS
        or hostname.endswith(".example.invalid")
        or hostname.endswith(".pstatic.net")
    )


def _decoded_variants(value: str) -> tuple[str, ...]:
    variants = [value]
    current = value
    for _ in range(3):
        decoded = html.unescape(unquote(current))
        if decoded == current:
            break
        variants.append(decoded)
        current = decoded
    return tuple(variants)


def _forbidden_host(value: str) -> bool:
    for candidate in _decoded_variants(value):
        for match in _URL_RE.finditer(candidate):
            url = match.group(0)
            if url.startswith("//"):
                url = f"https:{url}"
            try:
                hostname = urlsplit(url).hostname
            except ValueError:
                return True
            if not _allowed_host(hostname):
                return True
        stripped = candidate.strip().rstrip("/.")
        if _BARE_HOST_RE.fullmatch(stripped) and not _allowed_host(stripped):
            return True
    return False


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for character in value:
        counts[character] = counts.get(character, 0) + 1
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def _looks_like_token(value: str) -> bool:
    if _JWT_RE.search(value):
        return True
    for match in _TOKEN_RE.finditer(value):
        candidate = match.group(0)
        classes = sum(
            (
                any(char.islower() for char in candidate),
                any(char.isupper() for char in candidate),
                any(char.isdigit() for char in candidate),
                any(char in "+/=_-" for char in candidate),
            )
        )
        if classes >= 3 and shannon_entropy(candidate) >= 4.0:
            return True
    return False


def _is_name_key(key: str) -> bool:
    normalised = _normalised_key(key)
    return normalised in _NAME_KEYS or normalised in {name.replace("_", "") for name in _NAME_KEYS}


def _risky_korean_name(key: str, value: str) -> bool:
    return (
        _is_name_key(key)
        and bool(_KOREAN_NAME_RE.fullmatch(value))
        and value not in _SYNTHETIC_KOREAN_NAMES
    )


def _scan(value: object, categories: set[str], key: str = "", depth: int = 0) -> int:
    if depth > MAX_NESTING_DEPTH:
        raise CorpusError("fixture nesting exceeds budget")
    if isinstance(value, Mapping):
        items = 1
        is_comment_card = {
            "commentNo",
            "parentCommentNo",
            "replyLevel",
        } <= set(value)
        for child_key, child_value in value.items():
            key_text = str(child_key)
            lower_key = key_text.lower()
            is_comment_visibility_flag = (
                is_comment_card and lower_key == "secret" and isinstance(child_value, bool)
            )
            if _credential_shaped_key(key_text) and not is_comment_visibility_flag:
                categories.add("credential-key")
            if any(marker in lower_key for marker in _REAL_CAPTURE_MARKERS):
                categories.add("real-capture-marker")
            items += _scan(key_text, categories, key, depth + 1)
            items += _scan(child_value, categories, key_text, depth + 1)
            if items > MAX_FIXTURE_ITEMS:
                raise CorpusError("fixture item count exceeds budget")
        return items
    if isinstance(value, list):
        items = 1
        for item in value:
            items += _scan(item, categories, key, depth + 1)
            if items > MAX_FIXTURE_ITEMS:
                raise CorpusError("fixture item count exceeds budget")
        return items
    if not isinstance(value, str):
        return 1
    for candidate in _decoded_variants(value):
        lower_value = candidate.lower()
        if _EMAIL_RE.search(candidate):
            categories.add("email")
        if _PHONE_RE.search(candidate):
            categories.add("phone")
        if _forbidden_host(candidate):
            categories.add("forbidden-host")
        if any(marker in lower_value for marker in _REAL_CAPTURE_MARKERS):
            categories.add("real-capture-marker")
        if _looks_like_token(candidate):
            categories.add("high-entropy-token")
    if _risky_korean_name(key, value):
        categories.add("korean-name")
    return 1


class _NameHtmlParser(HTMLParser):
    def __init__(self, categories: set[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.categories = categories
        self.depth = 0
        self.nodes = 0
        self.text_bytes = 0
        self.name_text: list[list[str] | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        self.depth += 1
        if self.nodes > MAX_HTML_NODES or self.depth > MAX_HTML_DEPTH:
            raise CorpusError("HTML structure exceeds budget")
        values = [(key, value or "") for key, value in attrs]
        for key, value in values:
            if _is_name_key(key) and _risky_korean_name(key, value.strip()):
                self.categories.add("korean-name")
        marked = any(
            key.lower() in {"class", "id", "name"}
            and any(_is_name_key(part) for part in value.split())
            for key, value in values
        )
        self.name_text.append([] if marked else None)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        self.text_bytes += len(data.encode("utf-8"))
        if self.text_bytes > MAX_HTML_TEXT_BYTES:
            raise CorpusError("HTML text exceeds budget")
        for text in self.name_text:
            if text is not None:
                text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.name_text:
            return
        text = self.name_text.pop()
        self.depth -= 1
        if text is not None and _risky_korean_name("name", "".join(text).strip()):
            self.categories.add("korean-name")

    def close(self) -> None:
        super().close()
        while self.name_text:
            text = self.name_text.pop()
            self.depth -= 1
            if text is not None and _risky_korean_name("name", "".join(text).strip()):
                self.categories.add("korean-name")


def _scan_html_names(contents: str, categories: set[str]) -> None:
    parser = _NameHtmlParser(categories)
    parser.feed(contents)
    parser.close()


def _diagnostics(path: Path, categories: set[str]) -> list[str]:
    return [f"{path.name}: {category}" for category in CATEGORY_ORDER if category in categories]


def _safe_directory(directory: Path) -> int:
    flags = os.O_RDONLY | _require_flag("O_DIRECTORY") | _require_flag("O_NOFOLLOW")
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        raise CorpusError("fixture corpus is inaccessible or unsafe") from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise CorpusError("fixture corpus is not a directory")
    return descriptor


def _read_fixture(directory_fd: int, path: Path, initial: os.stat_result) -> str:
    descriptor = -1
    try:
        descriptor = os.open(
            path.name, os.O_RDONLY | _require_flag("O_NOFOLLOW"), dir_fd=directory_fd
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ) != (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns):
            raise CorpusError("fixture changed while scanning")
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            contents = stream.read()
        current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
            initial.st_dev,
            initial.st_ino,
            initial.st_size,
            initial.st_mtime_ns,
        ):
            raise CorpusError("fixture changed while scanning")
        return contents
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def scan_file(path: Path) -> list[str]:
    """Scan one fixture, refusing symlinks, non-regular files, and races."""
    path = Path(path)
    try:
        directory_fd = _safe_directory(path.parent)
        try:
            initial = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(initial.st_mode) or initial.st_size > MAX_FIXTURE_BYTES:
                return _diagnostics(path, {"unsafe-file"})
            contents = _read_fixture(directory_fd, path, initial)
        finally:
            os.close(directory_fd)
    except (CorpusError, OSError, UnicodeError):
        return _diagnostics(path, {"unsafe-file"})
    if path.suffix == ".json":
        try:
            payload = json.loads(contents, object_pairs_hook=_json_object)
        except (DuplicateJsonMemberError, json.JSONDecodeError, RecursionError):
            return _diagnostics(path, {"invalid-json"})
    else:
        payload = contents
    categories: set[str] = set()
    try:
        _scan(payload, categories)
        if path.suffix == ".html":
            _scan_html_names(contents, categories)
    except CorpusError:
        return _diagnostics(path, {"unsafe-file"})
    return _diagnostics(path, categories)


def fixture_paths(directory: Path | None = None) -> tuple[Path, ...]:
    """Return one safe, deterministic direct enumeration of the fixture corpus."""
    root = FIXTURES_DIR if directory is None else Path(directory)
    descriptor = _safe_directory(root)
    try:
        names: list[str] = []
        try:
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    names.append(entry.name)
                    if len(names) > MAX_FIXTURE_COUNT:
                        raise CorpusError("fixture corpus exceeds count budget")
            if not names:
                raise CorpusError("fixture corpus is empty")
            names.sort()
            paths: list[Path] = []
            total_bytes = 0
            for name in names:
                initial = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if (
                    not name.endswith((".json", ".html"))
                    or not stat.S_ISREG(initial.st_mode)
                    or initial.st_size > MAX_FIXTURE_BYTES
                ):
                    raise CorpusError("fixture corpus contains an unsupported entry")
                total_bytes += initial.st_size
                if total_bytes > MAX_CORPUS_BYTES:
                    raise CorpusError("fixture corpus exceeds byte budget")
                paths.append(root / name)
            return tuple(paths)
        except OSError as exc:
            raise CorpusError("fixture corpus is inaccessible or unsafe") from exc
    finally:
        os.close(descriptor)


def scan_fixtures(directory: Path | None = None) -> list[str]:
    try:
        paths = fixture_paths(directory)
    except CorpusError:
        return ["fixtures: unsafe-corpus"]
    return [finding for path in paths for finding in scan_file(path)]


def main() -> int:
    findings = scan_fixtures()
    if findings:
        print("Fixture PII scan FAILED:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "Diagnostics omit candidate values; inspect the named category locally.",
            file=sys.stderr,
        )
        return 1
    print("Fixture PII scan OK; human review remains required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
