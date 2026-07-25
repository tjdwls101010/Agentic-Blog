"""Strict normalization for Naver Blog identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import SplitResult, parse_qs, urlsplit

from .errors import InvalidIdentifierError

_BLOG_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,29}\Z", re.ASCII)
_DECIMAL_RE = re.compile(r"[0-9]+\Z", re.ASCII)
_BLOG_HOSTS = frozenset({"blog.naver.com", "m.blog.naver.com"})


def _invalid(value: object, kind: str) -> InvalidIdentifierError:
    return InvalidIdentifierError(f"invalid {kind}: {value!r}")


def _blog_id(value: object) -> str:
    # An all-numeric id is a real blog id, not a mistyped blogNo. `8892050` answers on
    # category-list, post-list, public-buddies and in-blog search, and its posts render at
    # m.blog.naver.com/8892050/{logNo}. Rejecting the shape made every such blog unreadable —
    # they turn up in ordinary search results, so the tool simply could not follow its own output.
    if not isinstance(value, str) or _BLOG_ID_RE.fullmatch(value) is None:
        raise _invalid(value, "blog id")
    return value


def _decimal(value: object, kind: str) -> str:
    if isinstance(value, bool):
        raise _invalid(value, kind)
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise _invalid(value, kind)
    return value


@dataclass(frozen=True, slots=True)
class BlogRef:
    """A normalized Naver Blog identifier."""

    blog_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "blog_id", _blog_id(self.blog_id))


@dataclass(frozen=True, slots=True)
class PostRef:
    """A normalized Naver Blog post identifier."""

    blog_id: str
    log_no: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "blog_id", _blog_id(self.blog_id))
        object.__setattr__(self, "log_no", _decimal(self.log_no, "post log number"))


def _naver_url(value: str) -> SplitResult:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        is_plain_host = parsed.username is None and parsed.password is None and parsed.port is None
    except ValueError as error:
        raise _invalid(value, "Naver Blog URL") from error
    if parsed.scheme not in {"http", "https"} or hostname not in _BLOG_HOSTS or not is_plain_host:
        raise _invalid(value, "Naver Blog URL")
    return parsed


def _path_parts(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def parse_blog_ref(value: str | BlogRef) -> BlogRef:
    """Parse a bare blog id or a one-part Naver Blog URL."""
    if isinstance(value, BlogRef):
        return value
    if not isinstance(value, str):
        raise _invalid(value, "blog reference")

    candidate = value.strip()
    if "://" not in candidate:
        return BlogRef(candidate)

    parsed = _naver_url(candidate)
    parts = _path_parts(parsed.path)
    if len(parts) != 1 or parsed.query or parsed.fragment:
        raise _invalid(value, "blog reference")
    return BlogRef(parts[0])


def parse_post_ref(value: str | PostRef | BlogRef, log_no: str | int | None = None) -> PostRef:
    """Parse a Naver post URL or a blog id and per-blog log number."""
    if isinstance(value, PostRef):
        if log_no is not None:
            raise _invalid(log_no, "post log number")
        return value
    if log_no is not None:
        blog_ref = parse_blog_ref(value) if not isinstance(value, BlogRef) else value
        return PostRef(blog_ref.blog_id, _decimal(log_no, "post log number"))
    if not isinstance(value, str):
        raise _invalid(value, "post reference")

    candidate = value.strip()
    if "://" not in candidate:
        raise _invalid(value, "post reference")

    parsed = _naver_url(candidate)
    parts = _path_parts(parsed.path)
    if parts == ["PostView.naver"]:
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        except ValueError as error:
            raise _invalid(value, "post reference") from error
        if (
            set(query) - {"blogId", "logNo", "modal"}
            or any(len(values) != 1 for values in query.values())
            or "blogId" not in query
            or "logNo" not in query
            or parsed.fragment
        ):
            raise _invalid(value, "post reference")
        return PostRef(query["blogId"][0], query["logNo"][0])
    if len(parts) == 2 and not parsed.query and not parsed.fragment:
        return PostRef(parts[0], parts[1])
    raise _invalid(value, "post reference")


def parse_directory_seq(value: str | int) -> int:
    """Parse a positive numeric Naver directory sequence."""
    sequence = _decimal(value, "directory sequence")
    if int(sequence) <= 0:
        raise _invalid(value, "directory sequence")
    return int(sequence)
