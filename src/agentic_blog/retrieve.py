"""Bounded, eager orchestration for anonymous search reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from . import endpoints, parse
from .body import parse_post_body, parse_post_search
from .errors import EnvelopeParseError, NotFoundError
from .identifiers import PostRef, parse_post_ref
from .model import (
    Blog,
    Comment,
    Post,
    Topic,
    build_buddy_blog,
    build_category,
    build_comment,
    build_directory_post,
    build_mobile_post,
    build_search_blog,
    build_search_id,
    build_search_post,
    build_topic,
)

SearchItem = Post | Blog
RetrieveItem = Post | Blog | Topic
StopReason = Literal["limit_reached", "no_next_page", "no_matches", "max_requests", "single_target"]


class SearchClient(Protocol):
    """Minimum request-accounting interface required by search."""

    requests_made: int
    remaining_requests: int

    def get_json(self, spec: endpoints.RequestSpec) -> dict[str, object]: ...
    def get_text(self, spec: endpoints.RequestSpec) -> str: ...


@dataclass
class RetrieveResult:
    """Normalized eager results and the reason pagination stopped."""

    items: list[RetrieveItem]
    stop_reason: StopReason
    requests_made: int


def _validate_limit(limit: int | None) -> None:
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
        raise ValueError("limit must be a non-negative integer")


def _validate_dates(since: date | None, until: date | None) -> None:
    if since is not None and (not isinstance(since, date) or isinstance(since, datetime)):
        raise ValueError("since must be a date")
    if until is not None and (not isinstance(until, date) or isinstance(until, datetime)):
        raise ValueError("until must be a date")
    if since is not None and until is not None and since > until:
        raise ValueError("since must not be later than until")


def _counter(client: object, name: str) -> int:
    value = getattr(client, name, None)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"client {name} must be a non-negative integer")
    return value


def _client_counters(client: object) -> tuple[int, int]:
    return _counter(client, "requests_made"), _counter(client, "remaining_requests")


def _result(
    items: list[RetrieveItem], stop_reason: StopReason, starting_requests: int, client: object
) -> RetrieveResult:
    requests_made, _ = _client_counters(client)
    return RetrieveResult(items, stop_reason, requests_made - starting_requests)


def _identity(item: SearchItem) -> tuple[str, str] | str:
    if isinstance(item, Post):
        return item.blog_id, item.log_no
    return item.blog_id


def _build_search_card(
    build: Callable[..., SearchItem],
    node: dict[str, Any],
    *,
    path: str,
    captured_at: datetime,
    include_raw: bool,
) -> SearchItem:
    """Normalize one externally supplied section-search card."""
    try:
        return build(node, captured_at=captured_at, include_raw=include_raw)
    except (TypeError, ValueError, KeyError) as error:
        raise EnvelopeParseError(
            f"response envelope drift at {path}: expected a valid section-search card"
        ) from error


def search(
    client: SearchClient,
    query: str,
    *,
    search_type: str = "post",
    sort: str | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Return one bounded, deduplicated section-search result set.

    Date bounds are sent to Naver in the request; this layer never filters them
    from returned records.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty")
    if search_type not in {"post", "blog", "id"}:
        raise ValueError("search_type must be one of post, blog, id")
    if sort not in {None, "sim", "date"}:
        raise ValueError("sort must be one of sim, date")
    if search_type == "id" and (sort is not None or since is not None or until is not None):
        raise ValueError("sort and date bounds are not supported for id searches")
    if search_type != "post" and (since is not None or until is not None):
        raise ValueError("date bounds are only supported for post searches")
    _validate_limit(limit)
    _validate_dates(since, until)
    if not callable(getattr(client, "get_json", None)):
        raise ValueError("client must provide get_json")

    starting_requests, _ = _client_counters(client)
    if limit == 0:
        return _result([], "limit_reached", starting_requests, client)

    count_per_page = 7 if search_type == "post" else 10
    effective_sort = sort or "sim"
    build = {
        "post": build_search_post,
        "blog": build_search_blog,
        "id": build_search_id,
    }[search_type]
    items: list[SearchItem] = []
    seen: set[tuple[str, str] | str] = set()
    page_number = 1

    while True:
        _, remaining_requests = _client_counters(client)
        if remaining_requests == 0:
            return _result(items, "max_requests", starting_requests, client)
        spec = endpoints.search_list(
            query,
            search_type=search_type,
            sort=effective_sort if search_type != "id" else None,
            page=page_number,
            count_per_page=count_per_page,
            since=since.isoformat() if since is not None else None,
            until=until.isoformat() if until is not None else None,
        )
        requests_before, remaining_before = _client_counters(client)
        page = parse.parse_search_page(client.get_json(spec))
        requests_after, _ = _client_counters(client)
        if requests_after != requests_before + 1:
            raise ValueError("client requests_made must advance by one per request")
        if _counter(client, "remaining_requests") != remaining_before - 1:
            raise ValueError("client remaining_requests must decrease by one per request")
        if not page.items:
            return _result(
                items,
                "no_matches" if not items else "no_next_page",
                starting_requests,
                client,
            )

        for index, node in enumerate(page.items):
            item = _build_search_card(
                build,
                node,
                path=f"response.result.searchList[{index}]",
                captured_at=datetime.now(UTC),
                include_raw=raw,
            )
            key = _identity(item)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
            if limit is not None and len(items) == limit:
                if len(page.items) >= count_per_page:
                    return _result(items, "limit_reached", starting_requests, client)
                for tail_index, tail_node in enumerate(page.items[index + 1 :], start=index + 1):
                    tail_item = _build_search_card(
                        build,
                        tail_node,
                        path=f"response.result.searchList[{tail_index}]",
                        captured_at=datetime.now(UTC),
                        include_raw=raw,
                    )
                    if _identity(tail_item) not in seen:
                        return _result(items, "limit_reached", starting_requests, client)
                return _result(items, "no_next_page", starting_requests, client)

        if len(page.items) < count_per_page:
            return _result(items, "no_next_page", starting_requests, client)
        page_number += 1


def _request(client: SearchClient, spec: endpoints.RequestSpec) -> object:
    if not callable(getattr(client, "get_json", None)):
        raise ValueError("client must provide get_json")
    requests_before, remaining_before = _client_counters(client)
    payload = client.get_json(spec)
    if _counter(client, "requests_made") != requests_before + 1:
        raise ValueError("client requests_made must advance by one per request")
    if _counter(client, "remaining_requests") != remaining_before - 1:
        raise ValueError("client remaining_requests must decrease by one per request")
    return payload


def _request_text(client: SearchClient, spec: endpoints.RequestSpec) -> str:
    if not callable(getattr(client, "get_text", None)):
        raise ValueError("client must provide get_text")
    requests_before, remaining_before = _client_counters(client)
    payload = client.get_text(spec)
    if _counter(client, "requests_made") != requests_before + 1:
        raise ValueError("client requests_made must advance by one per request")
    if _counter(client, "remaining_requests") != remaining_before - 1:
        raise ValueError("client remaining_requests must decrease by one per request")
    if not isinstance(payload, str):
        raise ValueError("client get_text must return a string")
    return payload


def _can_request(client: SearchClient) -> bool:
    _, remaining_requests = _client_counters(client)
    return remaining_requests > 0


def _validate_category(category: int) -> None:
    if not isinstance(category, int) or isinstance(category, bool) or category < 0:
        raise ValueError("category must be a non-negative integer")


def fetch_blog(client: SearchClient, blog_id: str, *, raw: bool = False) -> RetrieveResult:
    """Return one measured public blog profile and its category tree."""
    starting_requests, remaining_requests = _client_counters(client)
    if remaining_requests < 2:
        return _result([], "max_requests", starting_requests, client)

    profile_page = parse.parse_search_page(
        _request(
            client,
            endpoints.search_list(blog_id, search_type="id", page=1, count_per_page=10),
        )
    )
    for index, node in enumerate(profile_page.items):
        profile = _build_search_card(
            build_search_id,
            node,
            path=f"response.result.searchList[{index}]",
            captured_at=datetime.now(UTC),
            include_raw=raw,
        )
        if profile.blog_id == blog_id:
            blog = profile
            break
    else:
        raise NotFoundError(f"blog not found: {blog_id}")
    blog.categories = [
        build_category(node)
        for node in parse.parse_category_list(_request(client, endpoints.category_list(blog_id)))
    ]
    return _result([blog], "single_target", starting_requests, client)


@dataclass
class _CommentGraph:
    """First-seen CBOX cards with recursively merged cross-page descendants."""

    nodes: dict[str, dict[str, Any]]
    expected_replies: dict[str, int]
    order: list[str]

    def __init__(self) -> None:
        self.nodes = {}
        self.expected_replies = {}
        self.order = []

    def add(self, cards: tuple[dict[str, Any], ...]) -> None:
        def collect(card: dict[str, Any]) -> None:
            comment_no = str(card["commentNo"])
            identity = (
                str(card["parentCommentNo"]),
                int(card["replyLevel"]),
                int(card["replyCount"]),
            )
            existing = self.nodes.get(comment_no)
            if existing is None:
                clone = dict(card)
                clone["replyList"] = []
                clone["replyCount"] = 0
                self.nodes[comment_no] = clone
                self.expected_replies[comment_no] = identity[2]
                self.order.append(comment_no)
            elif identity != (
                str(existing["parentCommentNo"]),
                int(existing["replyLevel"]),
                self.expected_replies[comment_no],
            ):
                raise EnvelopeParseError(
                    f"CBOX structural identity conflicts for comment {comment_no}"
                )
            for reply in card.get("replyList") or []:
                collect(reply)

        for card in cards:
            collect(card)

    def _linked(self, *, allow_orphans: bool = False) -> tuple[list[str], dict[str, list[str]]]:
        roots: list[str] = []
        children = {comment_no: [] for comment_no in self.order}
        for comment_no in self.order:
            card = self.nodes[comment_no]
            parent_no = str(card["parentCommentNo"])
            reply_level = int(card["replyLevel"])
            if parent_no == comment_no:
                if reply_level != 1:
                    raise EnvelopeParseError(
                        f"CBOX root reply level is invalid for comment {comment_no}"
                    )
                roots.append(comment_no)
                continue
            parent = self.nodes.get(parent_no)
            if parent is None:
                if allow_orphans:
                    continue
                raise EnvelopeParseError(f"CBOX reply has no parent: {comment_no}")
            if reply_level != int(parent["replyLevel"]) + 1:
                raise EnvelopeParseError(f"CBOX reply level is invalid for comment {comment_no}")
            children[parent_no].append(comment_no)
        return roots, children

    def comments(self, limit: int | None, *, complete: bool) -> list[Comment]:
        roots, children = self._linked(allow_orphans=not complete or limit is not None)
        selected = roots if limit is None else roots[:limit]

        def build(comment_no: str) -> dict[str, Any]:
            card = dict(self.nodes[comment_no])
            replies = [build(reply_no) for reply_no in children[comment_no]]
            if complete and len(replies) != self.expected_replies[comment_no]:
                raise EnvelopeParseError(f"CBOX reply count is incomplete for comment {comment_no}")
            card["replyList"] = replies
            card["replyCount"] = len(replies)
            return card

        return [build_comment(build(comment_no)) for comment_no in selected]

    def selected_complete(self, limit: int) -> bool:
        roots, children = self._linked(allow_orphans=True)
        if len(roots) < limit:
            return False

        def complete(comment_no: str) -> bool:
            replies = children[comment_no]
            return len(replies) == self.expected_replies[comment_no] and all(
                complete(reply_no) for reply_no in replies
            )

        return all(complete(comment_no) for comment_no in roots[:limit])

    def validate_complete(self) -> None:
        _, children = self._linked()
        for comment_no, replies in children.items():
            if len(replies) != self.expected_replies[comment_no]:
                raise EnvelopeParseError(f"CBOX reply count is incomplete for comment {comment_no}")

    def counts(self) -> tuple[int, int, int]:
        roots, _ = self._linked()
        comment_count = len(roots)
        reply_count = len(self.nodes) - comment_count
        return comment_count, reply_count, len(self.nodes)


def fetch_post(
    client: SearchClient,
    post: str | PostRef,
    log_no: str | int | None = None,
    *,
    comments: bool = True,
    comment_sort: str = "new",
    comment_limit: int | None = None,
) -> RetrieveResult:
    """Return one public post with its rendered body and optionally its comment tree."""
    post_ref = parse_post_ref(post, log_no)
    if not isinstance(comments, bool):
        raise ValueError("comments must be a boolean")
    if comment_sort not in {"new", "favorite"}:
        raise ValueError("comment_sort must be one of new, favorite")
    _validate_limit(comment_limit)

    starting_requests, remaining_requests = _client_counters(client)
    if remaining_requests < 2:
        return _result([], "max_requests", starting_requests, client)

    body = parse_post_body(_request_text(client, endpoints.post_html(post_ref)))
    info = parse.parse_comments_info(_request(client, endpoints.comments_info(post_ref)))
    result_post = Post(
        log_no=post_ref.log_no,
        blog_id=post_ref.blog_id,
        blog_no=str(info.blog_no),
        url=f"https://blog.naver.com/{post_ref.blog_id}/{post_ref.log_no}",
        title=info.post_title,
        body=body.markdown,
        created_at=body.created_at,
        comment_count=info.total_count,
        media=list(body.media),
        comments=None if not comments else [],
        captured_at=datetime.now(UTC),
    )
    if not comments or info.total_count == 0 or comment_limit == 0:
        return _result([result_post], "single_target", starting_requests, client)

    graph = _CommentGraph()
    page_number = 1
    page_size = 10
    while True:
        if not _can_request(client):
            result_post.comments = graph.comments(comment_limit, complete=False)
            return _result([result_post], "max_requests", starting_requests, client)
        page = parse.parse_cbox_list(
            _request(
                client,
                endpoints.cbox_list(
                    info.blog_no,
                    post_ref.log_no,
                    page=page_number,
                    page_size=page_size,
                    sort="NEW" if comment_sort == "new" else "FAVORITE",
                ),
            )
        )
        if page.current_page != page_number:
            raise EnvelopeParseError("CBOX current page must match the requested page")
        if page.total_count != info.total_count:
            raise EnvelopeParseError("CBOX total count must match comments-info total count")
        if page_number == 1:
            expected_counts = (page.comment_count, page.reply_count, page.total_count)
            expected_total_pages = page.total_pages
        elif (page.comment_count, page.reply_count, page.total_count) != expected_counts:
            raise EnvelopeParseError("CBOX counts must be consistent across pages")
        elif page.total_pages != expected_total_pages:
            raise EnvelopeParseError("CBOX total pages must be consistent across pages")
        graph.add(page.items)
        if (
            comment_limit is not None
            and page.current_page < page.total_pages
            and graph.selected_complete(comment_limit)
        ):
            result_post.comments = graph.comments(comment_limit, complete=True)
            return _result([result_post], "single_target", starting_requests, client)
        if page.current_page >= page.total_pages:
            graph.validate_complete()
            comment_count, reply_count, total_count = graph.counts()
            if (comment_count, reply_count, total_count) != expected_counts:
                raise EnvelopeParseError("CBOX assembled counts must match measured counts")
            result_post.comments = graph.comments(comment_limit, complete=True)
            return _result([result_post], "single_target", starting_requests, client)
        page_number += 1


def _fetch_post_search(
    client: SearchClient,
    blog_id: str,
    query: str,
    *,
    limit: int | None,
) -> RetrieveResult:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty")
    _validate_limit(limit)
    starting_requests, _ = _client_counters(client)
    if limit == 0:
        return _result([], "limit_reached", starting_requests, client)

    items: list[RetrieveItem] = []
    seen: set[tuple[str, str]] = set()
    page_number = 1
    page_size = 10
    while True:
        if not _can_request(client):
            return _result(items, "max_requests", starting_requests, client)
        cards = parse_post_search(
            _request_text(client, endpoints.post_search_list(blog_id, query, page=page_number))
        )
        for card in cards:
            key = (card.blog_id, card.log_no)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                Post(
                    log_no=card.log_no,
                    blog_id=card.blog_id,
                    url=f"https://blog.naver.com/{card.blog_id}/{card.log_no}",
                    title=card.title,
                    brief=card.brief,
                    created_at=card.created_at,
                    captured_at=datetime.now(UTC),
                )
            )
            if limit is not None and len(items) == limit:
                return _result(items, "limit_reached", starting_requests, client)
        if len(cards) < page_size:
            return _result(
                items,
                "no_matches" if not items else "no_next_page",
                starting_requests,
                client,
            )
        page_number += 1


def fetch_posts(
    client: SearchClient,
    blog_id: str,
    *,
    category: int = 0,
    sort: str = "recent",
    notices: bool = False,
    query: str | None = None,
    limit: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Return bounded public blog post listings without trusting totalCount."""
    _validate_category(category)
    _validate_limit(limit)
    if sort not in {"recent", "popular"}:
        raise ValueError("sort must be one of recent, popular")
    if notices and sort != "recent":
        raise ValueError("notices do not support popular sort")
    if (notices or sort == "popular") and category != 0:
        raise ValueError("notices and popular sort do not support category")
    if query is not None:
        if category != 0:
            raise ValueError("query does not support category")
        if sort != "recent":
            raise ValueError("query does not support popular sort")
        if notices:
            raise ValueError("query does not support notices")
        if raw:
            raise ValueError("query does not support raw")
        return _fetch_post_search(client, blog_id, query, limit=limit)
    starting_requests, _ = _client_counters(client)
    if limit == 0:
        return _result([], "limit_reached", starting_requests, client)

    page_number = 1
    page_size = 24
    items: list[RetrieveItem] = []
    seen: set[tuple[str, str]] = set()
    kind = "notice" if notices else "popular" if sort == "popular" else "chronological"

    while True:
        if not _can_request(client):
            return _result(items, "max_requests", starting_requests, client)
        nodes = parse.parse_post_list(
            _request(
                client,
                endpoints.post_list(
                    blog_id,
                    category_no=category,
                    item_count=page_size,
                    page=page_number,
                    sort=sort,
                    notices=notices,
                ),
            ),
            kind=kind,
        )
        for index, node in enumerate(nodes):
            item = build_mobile_post(
                node,
                captured_at=datetime.now(UTC),
                kind=kind,
                include_raw=raw,
                is_notice=notices,
            )
            key = (item.blog_id, item.log_no)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
            if limit is not None and len(items) == limit:
                if kind != "chronological":
                    for tail_node in nodes[index + 1 :]:
                        tail_item = build_mobile_post(
                            tail_node,
                            captured_at=datetime.now(UTC),
                            kind=kind,
                            include_raw=raw,
                            is_notice=notices,
                        )
                        if (tail_item.blog_id, tail_item.log_no) not in seen:
                            return _result(items, "limit_reached", starting_requests, client)
                    return _result(items, "no_next_page", starting_requests, client)
                if len(nodes) >= page_size:
                    return _result(items, "limit_reached", starting_requests, client)
                for tail_node in nodes[index + 1 :]:
                    tail_item = build_mobile_post(
                        tail_node,
                        captured_at=datetime.now(UTC),
                        kind=kind,
                        include_raw=raw,
                        is_notice=notices,
                    )
                    if (tail_item.blog_id, tail_item.log_no) not in seen:
                        return _result(items, "limit_reached", starting_requests, client)
                return _result(items, "no_next_page", starting_requests, client)
        if kind != "chronological" or len(nodes) < page_size:
            return _result(
                items,
                "no_matches" if not items else "no_next_page",
                starting_requests,
                client,
            )
        page_number += 1


def fetch_topics(client: SearchClient) -> RetrieveResult:
    """Return the complete public directory topic tree in one request."""
    starting_requests, _ = _client_counters(client)
    if not _can_request(client):
        return _result([], "max_requests", starting_requests, client)
    items: list[RetrieveItem] = []
    seen: set[str] = set()
    for node in parse.parse_directory_list(_request(client, endpoints.directory_list())):
        item = build_topic(node)
        if item.seq in seen:
            continue
        seen.add(item.seq)
        items.append(item)
    return _result(items, "single_target", starting_requests, client)


def fetch_topic(
    client: SearchClient,
    directory_seq: str | int,
    *,
    top: bool = False,
    limit: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Return bounded chronological or one-shot top posts for one directory topic."""
    _validate_limit(limit)
    starting_requests, _ = _client_counters(client)
    if limit == 0:
        return _result([], "limit_reached", starting_requests, client)

    page_number = 1
    page_size = 24
    items: list[RetrieveItem] = []
    seen: set[tuple[str, str]] = set()
    while True:
        if not _can_request(client):
            return _result(items, "max_requests", starting_requests, client)
        spec = (
            endpoints.directory_top_post_list(directory_seq)
            if top
            else endpoints.directory_post_list(directory_seq, page=page_number)
        )
        nodes = parse.parse_directory_posts(_request(client, spec), top=top)
        for index, node in enumerate(nodes):
            item = build_directory_post(node, captured_at=datetime.now(UTC), include_raw=raw)
            key = (item.blog_id, item.log_no)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
            if limit is not None and len(items) == limit:
                if top:
                    for tail_node in nodes[index + 1 :]:
                        tail_item = build_directory_post(
                            tail_node, captured_at=datetime.now(UTC), include_raw=raw
                        )
                        if (tail_item.blog_id, tail_item.log_no) not in seen:
                            return _result(items, "limit_reached", starting_requests, client)
                    return _result(items, "no_next_page", starting_requests, client)
                if len(nodes) >= page_size:
                    return _result(items, "limit_reached", starting_requests, client)
                for tail_node in nodes[index + 1 :]:
                    tail_item = build_directory_post(
                        tail_node, captured_at=datetime.now(UTC), include_raw=raw
                    )
                    if (tail_item.blog_id, tail_item.log_no) not in seen:
                        return _result(items, "limit_reached", starting_requests, client)
                return _result(items, "no_next_page", starting_requests, client)
        if top or len(nodes) < page_size:
            return _result(
                items,
                "no_matches" if not items else "no_next_page",
                starting_requests,
                client,
            )
        page_number += 1


def fetch_buddies(
    client: SearchClient,
    blog_id: str,
    *,
    limit: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Return bounded public buddies using the server's reliable page count."""
    _validate_limit(limit)
    starting_requests, _ = _client_counters(client)
    if limit == 0:
        return _result([], "limit_reached", starting_requests, client)

    items: list[RetrieveItem] = []
    seen: set[str] = set()
    page_number = 1
    while True:
        if not _can_request(client):
            return _result(items, "max_requests", starting_requests, client)
        page = parse.parse_buddies(
            _request(client, endpoints.public_buddies(blog_id, page=page_number))
        )
        for index, node in enumerate(page.items):
            item = build_buddy_blog(node, captured_at=datetime.now(UTC), include_raw=raw)
            if item.blog_id in seen:
                continue
            seen.add(item.blog_id)
            items.append(item)
            if limit is not None and len(items) == limit:
                for tail_node in page.items[index + 1 :]:
                    tail_item = build_buddy_blog(
                        tail_node, captured_at=datetime.now(UTC), include_raw=raw
                    )
                    if tail_item.blog_id not in seen:
                        return _result(items, "limit_reached", starting_requests, client)
                if page.current_page < page.total_page_count:
                    return _result(items, "limit_reached", starting_requests, client)
                return _result(items, "no_next_page", starting_requests, client)
        if page.current_page >= page.total_page_count:
            return _result(
                items,
                "no_matches" if not items else "no_next_page",
                starting_requests,
                client,
            )
        page_number = page.current_page + 1
