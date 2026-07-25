"""Pure request builders for Naver Blog read endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from .errors import InvalidIdentifierError
from .identifiers import BlogRef, PostRef, parse_blog_ref, parse_directory_seq, parse_post_ref

SECTION = "https://section.blog.naver.com/ajax/"
SECTION_SEARCH_LIST = f"{SECTION}SearchList.naver"
SECTION_DIRECTORY_LIST = f"{SECTION}DirectoryList.naver"
SECTION_DIRECTORY_POST_LIST = f"{SECTION}DirectoryPostList.naver"
SECTION_DIRECTORY_TOP_POST_LIST = f"{SECTION}DirectoryTopPostList.naver"

MOBILE = "https://m.blog.naver.com/api/blogs/"
MOBILE_HTML = "https://m.blog.naver.com/"
MOBILE_SEARCH_POST = "https://m.blog.naver.com/api/search/v1/post"
MOBILE_TAG_SEARCH = "https://m.blog.naver.com/api/tags/search/post"
CBOX = "https://apis.naver.com/commentBox/cbox/"
CBOX_LIST = f"{CBOX}web_naver_list_json.json"
CBOX_POOL = "blogid"  # Other guessed pools return code 3300.
CBOX_OBJECT_ID = "{blog_no}_201_{log_no}"  # Literal 201 is undocumented; recon §6.
POST_LIST_MAX_ITEM_COUNT = 30  # 31+ -> param_is_invalidate
SEARCH_MAX_ITEM_COUNT = 30  # Both search hosts return the default page above this.

#: Both search hosts stop yielding at 1,000 posts however deep you page. The mobile
#: envelope nonetheless reports totalCount in the millions and totalPage in the hundreds
#: of thousands, and those figures drift between pages — they size the corpus, they do not
#: bound pagination. Never drive paging from them; stop on a short page. See plan doc 13 §1.1.
SEARCH_RESULT_CEILING = 1000

_SEARCH_TYPES = frozenset({"post", "blog", "id"})  # section only; tag lives on the mobile host
_SEARCH_SORTS = frozenset({"sim", "date"})


class _SortOmitted:
    """Sentinel that distinguishes an omitted sort from an explicit value."""


_SORT_OMITTED = _SortOmitted()


@dataclass(frozen=True)
class RequestSpec:
    """One read-only HTTP request, without transport behavior."""

    url: str
    params: Mapping[str, str | int | bool | None]

    def __post_init__(self) -> None:
        if not isinstance(self.params, Mapping):
            raise TypeError("params must be a mapping")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


def search_list(
    query: str,
    *,
    search_type: str = "post",
    sort: str | None | _SortOmitted = _SORT_OMITTED,
    page: int = 1,
    count_per_page: int = 7,
    since: str | None = None,
    until: str | None = None,
) -> RequestSpec:
    """Build a SECTION ``SearchList.naver`` request."""
    query = _required_text(query, "search query")
    if not isinstance(search_type, str) or search_type not in _SEARCH_TYPES:
        raise InvalidIdentifierError("invalid search type")
    _positive_int(page, "page")
    _positive_int(count_per_page, "count per page")
    if sort is _SORT_OMITTED:
        sort = None if search_type == "id" else "sim"
    elif sort is not None and not isinstance(sort, str):
        raise InvalidIdentifierError("invalid search sort")
    _date_bound(since, "since")
    _date_bound(until, "until")
    if search_type == "id":
        if sort is not None:
            raise InvalidIdentifierError("id search does not support sort")
        if since is not None or until is not None:
            raise InvalidIdentifierError("id search does not support date bounds")
    else:
        if sort is not None and sort not in _SEARCH_SORTS:
            raise InvalidIdentifierError("invalid search sort")
        if search_type == "blog" and (since is not None or until is not None):
            raise InvalidIdentifierError("blog search does not support date bounds")
    if since is not None and until is not None and since > until:
        raise InvalidIdentifierError("since must not be after until")

    params: dict[str, str | int | bool | None] = {
        "type": search_type,
        "keyword": query,
    }
    if sort is not None:
        params["orderBy"] = sort
    if since is not None:
        params["startDate"] = since
    if until is not None:
        params["endDate"] = until
    params["currentPage"] = page
    params["countPerPage"] = count_per_page
    return RequestSpec(url=SECTION_SEARCH_LIST, params=params)


def category_list(blog_id: str | BlogRef) -> RequestSpec:
    """Build a MOBILE ``category-list`` request."""
    return RequestSpec(url=_mobile_url(blog_id, "category-list"), params={})


def chronological_post_list(
    blog_id: str | BlogRef,
    *,
    category_no: int = 0,
    item_count: int = 24,
    page: int = 1,
) -> RequestSpec:
    """Build a MOBILE chronological ``post-list`` request."""
    _nonnegative_int(category_no, "category number")
    _positive_int(item_count, "item count")
    _positive_int(page, "page")
    return RequestSpec(
        url=_mobile_url(blog_id, "post-list"),
        params={
            "categoryNo": category_no,
            "itemCount": min(item_count, POST_LIST_MAX_ITEM_COUNT),
            "page": page,
        },
    )


def notice_post_list(blog_id: str | BlogRef) -> RequestSpec:
    """Build a MOBILE ``notice-post-list`` request."""
    return RequestSpec(url=_mobile_url(blog_id, "notice-post-list"), params={})


def popular_post_list(blog_id: str | BlogRef) -> RequestSpec:
    """Build a MOBILE ``popular-post-list`` request."""
    return RequestSpec(url=_mobile_url(blog_id, "popular-post-list"), params={})


def post_list(
    blog_id: str | BlogRef,
    *,
    category_no: int = 0,
    item_count: int = 24,
    page: int = 1,
    sort: str = "recent",
    notices: bool = False,
) -> RequestSpec:
    """Build the selected posts-list variant without silently dropping options."""
    if not isinstance(sort, str) or sort not in {"recent", "popular"}:
        raise InvalidIdentifierError("invalid post sort")
    if not isinstance(notices, bool):
        raise InvalidIdentifierError("notices must be a boolean")
    _nonnegative_int(category_no, "category number")
    _positive_int(item_count, "item count")
    _positive_int(page, "page")
    if notices:
        if sort != "recent":
            raise InvalidIdentifierError("notices do not support popular sort")
        if category_no != 0 or item_count != 24 or page != 1:
            raise InvalidIdentifierError("notices do not support pagination or category")
        return notice_post_list(blog_id)
    if sort == "popular":
        if category_no != 0 or item_count != 24 or page != 1:
            raise InvalidIdentifierError("popular sort does not support pagination or category")
        return popular_post_list(blog_id)
    return chronological_post_list(
        blog_id,
        category_no=category_no,
        item_count=item_count,
        page=page,
    )


def public_buddies(blog_id: str | BlogRef, *, page: int = 1) -> RequestSpec:
    """Build a MOBILE ``public-buddies`` request."""
    _positive_int(page, "page")
    return RequestSpec(
        url=_mobile_url(blog_id, "public-buddies"),
        params={"pageNo": page},
    )


def directory_list() -> RequestSpec:
    """Build a SECTION ``DirectoryList.naver`` request."""
    return RequestSpec(url=SECTION_DIRECTORY_LIST, params={})


def directory_post_list(directory_seq: str | int, *, page: int = 1) -> RequestSpec:
    """Build a SECTION ``DirectoryPostList.naver`` request."""
    _positive_int(page, "page")
    return RequestSpec(
        url=SECTION_DIRECTORY_POST_LIST,
        params={"directorySeq": parse_directory_seq(directory_seq), "pageNo": page},
    )


def directory_top_post_list(directory_seq: str | int) -> RequestSpec:
    """Build a SECTION ``DirectoryTopPostList.naver`` request."""
    return RequestSpec(
        url=SECTION_DIRECTORY_TOP_POST_LIST,
        params={"directorySeq": parse_directory_seq(directory_seq)},
    )


def post_html(blog_id: str | BlogRef | PostRef, log_no: str | int | None = None) -> RequestSpec:
    """Build the MOBILE HTML post request."""
    post_ref = parse_post_ref(blog_id, log_no)
    _positive_decimal(post_ref.log_no, "post log number")
    return RequestSpec(url=f"{MOBILE_HTML}{post_ref.blog_id}/{post_ref.log_no}", params={})


def comments_info(blog_id: str | BlogRef | PostRef, log_no: str | int | None = None) -> RequestSpec:
    """Build the MOBILE ``comments-info`` request."""
    post_ref = parse_post_ref(blog_id, log_no)
    _positive_decimal(post_ref.log_no, "post log number")
    return RequestSpec(
        url=_mobile_url(post_ref.blog_id, f"posts/{post_ref.log_no}/comments-info"),
        params={},
    )


def cbox_list(
    blog_no: str | int,
    log_no: str | int,
    *,
    page: int = 1,
    page_size: int = 10,
    sort: str = "NEW",
) -> RequestSpec:
    """Build the CBOX plain-JSON comment-list request."""
    blog_no = _positive_decimal(blog_no, "blog number")
    log_no = _positive_decimal(log_no, "post log number")
    _positive_int(page, "page")
    _positive_int(page_size, "page size")
    if not isinstance(sort, str) or sort not in {"NEW", "FAVORITE"}:
        raise InvalidIdentifierError("invalid comment sort")
    return RequestSpec(
        url=CBOX_LIST,
        params={
            "ticket": "blog",
            "pool": CBOX_POOL,
            "objectId": CBOX_OBJECT_ID.format(blog_no=blog_no, log_no=log_no),
            "groupId": blog_no,
            "templateId": "default",
            "lang": "ko",
            "country": "",
            "_cv": "",
            "pageType": "more",
            "listType": "OBJECT",
            "page": page,
            "pageSize": page_size,
            "indexSize": 10,
            "replyPageSize": 10,
            "followSize": 5,
            "initialize": True,
            "useAltSort": True,
            "userType": "",
            "categoryId": "",
            "sort": sort,
        },
    )


def mobile_search_post(
    query: str,
    *,
    sort: str = "sim",
    page: int = 1,
    item_count: int = SEARCH_MAX_ITEM_COUNT,
    since: str | None = None,
    until: str | None = None,
    self_purchased: bool = False,
) -> RequestSpec:
    """Build a mobile ``/api/search/v1/post`` request.

    ``periodType`` is deliberately absent: the site's own bundle never sends it, and
    passing it changes nothing. ``startDate``/``endDate`` are the real date bounds.
    """
    query = _required_text(query, "search query")
    if not isinstance(sort, str) or sort not in _SEARCH_SORTS:
        raise InvalidIdentifierError("invalid search sort")
    _positive_int(page, "page")
    _search_item_count(item_count)
    _date_bound(since, "since")
    _date_bound(until, "until")
    if since is not None and until is not None and since > until:
        raise InvalidIdentifierError("since must not be after until")
    if not isinstance(self_purchased, bool):
        raise InvalidIdentifierError("self_purchased must be a boolean")

    params: dict[str, str | int | bool | None] = {
        "keyword": query,
        "sortType": sort,
        "page": page,
        "itemCount": item_count,
    }
    if since is not None:
        params["startDate"] = since
    if until is not None:
        params["endDate"] = until
    if self_purchased:
        params["isBuyWithMyOwnMoney"] = "true"
    return RequestSpec(url=MOBILE_SEARCH_POST, params=params)


def mobile_tag_search(
    query: str,
    *,
    page: int = 1,
    item_count: int = SEARCH_MAX_ITEM_COUNT,
) -> RequestSpec:
    """Build a mobile ``/api/tags/search/post`` request.

    Not ``/api/search/v1/tag``: that one answers with tag *groups*
    (``{postCount, tag, blogs:[...]}``), which are not posts. This one is a flat post list.
    """
    query = _required_text(query, "search query")
    _positive_int(page, "page")
    _search_item_count(item_count)
    return RequestSpec(
        url=MOBILE_TAG_SEARCH,
        params={"query": query, "page": page, "itemCount": item_count},
    )


def in_blog_search(
    blog_id: str | BlogRef,
    query: str,
    *,
    sort: str = "sim",
    page: int = 1,
) -> RequestSpec:
    """Build a mobile in-blog post-search request.

    Two names here resist guessing and were both measured: the trailing path segment is
    ``post`` — the bundle's ``inBlogPost`` enum value is a UI mode name and redirects to an
    error page — and the term parameter is ``query``; sending ``keyword`` returns HTTP 500.
    """
    query = _required_text(query, "search query")
    if not isinstance(sort, str) or sort not in _SEARCH_SORTS:
        raise InvalidIdentifierError("invalid in-blog search sort")
    _positive_int(page, "page")
    return RequestSpec(
        url=_mobile_url(blog_id, "search/post"),
        params={"query": query, "sortType": sort, "page": page},
    )


def _search_item_count(value: object) -> None:
    _positive_int(value, "item count")
    if isinstance(value, int) and value > SEARCH_MAX_ITEM_COUNT:
        raise InvalidIdentifierError("item count must not exceed 30")


def _mobile_url(blog_id: str | BlogRef, endpoint: str) -> str:
    return f"{MOBILE}{parse_blog_ref(blog_id).blog_id}/{endpoint}"


def _nonnegative_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidIdentifierError(f"{label} must be non-negative")


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidIdentifierError(f"{label} is empty")
    return value


def _positive_decimal(value: object, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise InvalidIdentifierError(f"invalid {label}")
    text = str(value)
    if not text.isascii() or not text.isdecimal() or int(text) < 1:
        raise InvalidIdentifierError(f"invalid {label}")
    return text


def _positive_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidIdentifierError(f"{label} must be positive")


def _date_bound(value: str | None, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise InvalidIdentifierError(f"{label} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise InvalidIdentifierError(f"{label} must be YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise InvalidIdentifierError(f"{label} must be YYYY-MM-DD")
