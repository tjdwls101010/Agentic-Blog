"""Anchored parsers for JSON response envelopes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .errors import EnvelopeParseError


@dataclass(frozen=True)
class SearchPage:
    """Raw page data from the section search endpoint."""

    items: tuple[dict[str, Any], ...]
    total_count: int
    page_per_count: int
    display_info: dict[str, Any]


@dataclass(frozen=True)
class BuddyPage:
    """Raw page data from the public buddies endpoint."""

    items: tuple[dict[str, Any], ...]
    current_page: int
    total_page_count: int
    #: Neighbours a logged-out reader can actually enumerate. Distinct from
    #: ``totalMyBuddyCount``, which counts every neighbour including undisclosed ones and
    #: is routinely far larger — 248 vs 1 on one measured blog, 1,908 vs 0 on another.
    public_buddy_count: int = 0


@dataclass(frozen=True)
class CommentsInfo:
    """Measured metadata from the mobile comments-info endpoint."""

    blog_no: int
    post_title: str
    total_count: int


@dataclass(frozen=True)
class CommentPage:
    """Measured CBOX counts and unmodified top-level comment cards."""

    items: tuple[dict[str, Any], ...]
    comment_count: int
    reply_count: int
    total_count: int
    current_page: int
    total_pages: int


_CBOX_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+0900\Z")


def _drift(path: str, expected: str) -> EnvelopeParseError:
    return EnvelopeParseError(f"response envelope drift at {path}: expected {expected}")


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _drift(path, "an integer")
    return value


def _non_negative_integer(value: object, path: str) -> int:
    value = _integer(value, path)
    if value < 0:
        raise _drift(path, "a non-negative integer")
    return value


def _positive_integer(value: object, path: str) -> int:
    value = _integer(value, path)
    if value < 1:
        raise _drift(path, "a positive integer")
    return value


def parse_search_page(payload: object) -> SearchPage:
    """Extract one SearchList.naver page without normalizing its items."""
    if not isinstance(payload, dict):
        raise _drift("response", "an object")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise _drift("response.result", "an object")

    display_info = result.get("searchDisplayInfo")
    if not isinstance(display_info, dict):
        raise _drift("response.result.searchDisplayInfo", "an object")

    search_list = result.get("searchList")
    if not isinstance(search_list, list):
        raise _drift("response.result.searchList", "a list")
    for index, item in enumerate(search_list):
        if not isinstance(item, dict):
            raise _drift(f"response.result.searchList[{index}]", "an object")

    return SearchPage(
        items=tuple(search_list),
        total_count=_non_negative_integer(result.get("totalCount"), "response.result.totalCount"),
        page_per_count=_positive_integer(
            result.get("pagePerCount"), "response.result.pagePerCount"
        ),
        display_info=display_info,
    )


_POST_LIST_KEYS = {
    "chronological": "items",
    "notice": "noticePostViewList",
    "popular": "popularPostList",
}


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _drift(path, "an object")
    return value


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise _drift(path, "a list")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise _drift(path, "a string")
    return value


def _non_empty_string(value: object, path: str) -> str:
    value = _string(value, path)
    if not value.strip():
        raise _drift(path, "a non-empty string")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise _drift(path, "a boolean")
    return value


def _nullable_non_negative_integer(value: object, path: str) -> None:
    if value is not None:
        _non_negative_integer(value, path)


def _nullable_string(value: object, path: str) -> None:
    if value is not None:
        _string(value, path)


def _nullable_count(value: object, path: str) -> None:
    if value is not None:
        _non_negative_integer(value, path)


def _nullable_play_time(value: object, path: str) -> None:
    """A thumbnail's play length: seconds as an integer on video, null on stills."""
    if value is None or isinstance(value, str):
        return
    _non_negative_integer(value, path)


def _success_result(payload: object) -> dict[str, Any]:
    response = _object(payload, "response")
    _boolean(response.get("isSuccess"), "response.isSuccess")
    if response["isSuccess"] is not True:
        raise _drift("response.isSuccess", "true")
    return _object(response.get("result"), "response.result")


def _validate_mobile_post(
    node: dict[str, Any],
    path: str,
    *,
    full: bool,
    kind: Literal["chronological", "notice", "popular"] = "chronological",
) -> None:
    # Only the chronological card names its blog with `domainIdOrBlogId`. Notice and popular cards
    # are separate upstream shapes that carry `blogId` instead and leave `domainIdOrBlogId` null.
    if kind == "chronological":
        _non_negative_integer(node.get("logNo"), f"{path}.logNo")
        _non_negative_integer(node.get("blogNo"), f"{path}.blogNo")
        _non_empty_string(node.get("domainIdOrBlogId"), f"{path}.domainIdOrBlogId")
    else:
        _non_empty_string(node.get("blogId"), f"{path}.blogId")
        _non_negative_integer(node.get("logNo"), f"{path}.logNo")
        if kind == "notice":
            _non_negative_integer(node.get("blogNo"), f"{path}.blogNo")
    _string(node.get("titleWithInspectMessage"), f"{path}.titleWithInspectMessage")
    _nullable_string(node.get("thumbnailUrl"), f"{path}.thumbnailUrl")
    if not full:
        return
    for name in ("briefContents", "categoryName"):
        _nullable_string(node.get(name), f"{path}.{name}")
    _non_negative_integer(node.get("smartEditorVersion"), f"{path}.smartEditorVersion")
    if kind == "popular":
        _nullable_non_negative_integer(node.get("categoryNo"), f"{path}.categoryNo")
    else:
        _non_negative_integer(node.get("categoryNo"), f"{path}.categoryNo")
    _nullable_non_negative_integer(node.get("addDate"), f"{path}.addDate")
    for name in ("commentCnt", "sympathyCnt", "shareCnt", "thumbnailCount"):
        _nullable_count(node.get(name), f"{path}.{name}")
    thumbnails = _list(node.get("thumbnailList"), f"{path}.thumbnailList")
    for index, value in enumerate(thumbnails):
        thumbnail_path = f"{path}.thumbnailList[{index}]"
        thumbnail = _object(value, thumbnail_path)
        for name in ("type", "encodedThumbnailUrl", "videoAniThumbnailUrl"):
            _string(thumbnail.get(name), f"{thumbnail_path}.{name}")
        if "videoPlayTime" not in thumbnail:
            raise _drift(f"{thumbnail_path}.videoPlayTime", "a string, an integer, or null")
        _nullable_play_time(thumbnail["videoPlayTime"], f"{thumbnail_path}.videoPlayTime")
        for name in ("isPortraitThumbnail", "videoThumbnail", "vrthumbnail"):
            _boolean(thumbnail.get(name), f"{thumbnail_path}.{name}")
    for name in ("allOpenPost", "buddyOpen", "bothBuddyOpen", "notOpen"):
        _boolean(node.get(name), f"{path}.{name}")


def parse_mobile_search_page(payload: object) -> tuple[dict[str, Any], ...]:
    """Extract one m.blog search page's cards without normalizing them.

    Covers all three mobile search surfaces. Global post search and in-blog search name the
    array ``list``; tag search names it ``items``.

    This returns cards and nothing else **on purpose.** The envelope also carries
    ``totalCount`` and ``totalPage``, and on the global search those read 12,356,134 and
    411,872 while paging in fact dies at 1,000 — the figures size the corpus and drift
    between pages. Not surfacing them is what stops a caller from paginating on a lie.
    """
    result = _success_result(payload)
    if "list" in result:
        cards, name = result["list"], "list"
    elif "items" in result:
        cards, name = result["items"], "items"
    else:
        raise _drift("response.result.list", "a list")
    if not isinstance(cards, list):
        raise _drift(f"response.result.{name}", "a list")
    for index, item in enumerate(cards):
        item_path = f"response.result.{name}[{index}]"
        node = _object(item, item_path)
        _non_empty_string(node.get("blogId"), f"{item_path}.blogId")
        _non_negative_integer(node.get("logNo"), f"{item_path}.logNo")
        _string(node.get("title"), f"{item_path}.title")
        _nullable_string(node.get("thumbnailUrl"), f"{item_path}.thumbnailUrl")
        _nullable_non_negative_integer(node.get("addDate"), f"{item_path}.addDate")
        for count_name in ("commentCount", "sympathyCount"):
            _nullable_count(node.get(count_name), f"{item_path}.{count_name}")
    return tuple(cards)


def parse_blog_post_count(payload: object) -> int:
    """Extract a blog's own post total from a CategoryList response.

    ``parse_category_list`` has always validated this field and then dropped it, which is
    why ``Blog.post_count`` shipped permanently null.
    """
    result = _success_result(payload)
    return _non_negative_integer(result.get("mylogPostCount"), "response.result.mylogPostCount")


def parse_category_list(payload: object) -> tuple[dict[str, Any], ...]:
    """Extract and flatten non-separator categories from a CategoryList response."""
    result = _success_result(payload)
    categories = _list(result.get("mylogCategoryList"), "response.result.mylogCategoryList")
    _list(result.get("memologCategoryList"), "response.result.memologCategoryList")
    _non_negative_integer(result.get("mylogPostCount"), "response.result.mylogPostCount")
    _non_negative_integer(result.get("memologPostCount"), "response.result.memologPostCount")
    flattened: list[dict[str, Any]] = []

    for index, value in enumerate(categories):
        node_path = f"response.result.mylogCategoryList[{index}]"
        node = _object(value, node_path)
        _string(node.get("categoryType"), f"{node_path}.categoryType")
        _boolean(node.get("divisionLine"), f"{node_path}.divisionLine")
        _boolean(node.get("childCategory"), f"{node_path}.childCategory")
        if node["categoryType"] == "S" or node["divisionLine"]:
            continue
        _non_negative_integer(node.get("categoryNo"), f"{node_path}.categoryNo")
        _string(node.get("categoryName"), f"{node_path}.categoryName")
        _nullable_count(node.get("postCnt"), f"{node_path}.postCnt")
        _boolean(node.get("openYN"), f"{node_path}.openYN")
        parent_no = node.get("parentCategoryNo")
        if parent_no is not None:
            _non_negative_integer(parent_no, f"{node_path}.parentCategoryNo")
        flattened.append(node)
    category_ids = [str(node["categoryNo"]) for node in flattened]
    if len(category_ids) != len(set(category_ids)):
        raise _drift("response.result.mylogCategoryList", "unique categoryNo values")
    parents = {
        str(node["categoryNo"]): (
            str(node["parentCategoryNo"]) if node.get("parentCategoryNo") is not None else None
        )
        for node in flattened
    }
    for category_no, parent_no in parents.items():
        seen = {category_no}
        while parent_no is not None:
            if parent_no not in parents:
                raise _drift(
                    "response.result.mylogCategoryList",
                    "parentCategoryNo values linked to listed categories",
                )
            if parent_no in seen:
                raise _drift("response.result.mylogCategoryList", "an acyclic category tree")
            seen.add(parent_no)
            parent_no = parents[parent_no]
    return tuple(flattened)


def parse_post_list(
    payload: object, *, kind: Literal["chronological", "notice", "popular"] = "chronological"
) -> tuple[dict[str, Any], ...]:
    """Extract one mobile post-list variant without trusting its totalCount."""
    if kind not in _POST_LIST_KEYS:
        raise ValueError(f"unsupported post list kind: {kind}")
    result = _success_result(payload)
    key = _POST_LIST_KEYS[kind]
    items = _list(result.get(key), f"response.result.{key}")
    if kind == "chronological":
        _non_negative_integer(result.get("categoryNo"), "response.result.categoryNo")
        _string(result.get("categoryName"), "response.result.categoryName")
        _positive_integer(result.get("page"), "response.result.page")
        _non_negative_integer(result.get("totalCount"), "response.result.totalCount")
    for index, value in enumerate(items):
        path = f"response.result.{key}[{index}]"
        _validate_mobile_post(
            _object(value, path),
            path,
            full=kind in ("chronological", "popular"),
            kind=kind,
        )
    return tuple(items)


def parse_buddies(payload: object) -> BuddyPage:
    """Extract one public buddy page while retaining raw buddy cards and update labels."""
    result = _success_result(payload)
    _non_empty_string(result.get("blogId"), "response.result.blogId")
    _string(result.get("nickName"), "response.result.nickName")
    _non_negative_integer(result.get("totalMyBuddyCount"), "response.result.totalMyBuddyCount")
    public_buddy_count = _non_negative_integer(
        result.get("totalPublicBuddyCount"), "response.result.totalPublicBuddyCount"
    )
    total_page_count = _non_negative_integer(
        result.get("totalPageCount"), "response.result.totalPageCount"
    )
    current_page = _positive_integer(result.get("currentPage"), "response.result.currentPage")
    buddies = _list(result.get("buddyList"), "response.result.buddyList")
    if total_page_count == 0:
        if current_page != 1:
            raise _drift("response.result.currentPage", "1 when totalPageCount is zero")
        if buddies:
            raise _drift("response.result.buddyList", "an empty list when totalPageCount is zero")
    elif current_page > total_page_count:
        raise _drift("response.result.currentPage", "not exceed totalPageCount")
    for index, value in enumerate(buddies):
        path = f"response.result.buddyList[{index}]"
        node = _object(value, path)
        _non_empty_string(node.get("blogId"), f"{path}.blogId")
        for name in ("blogName", "nickName", "linkUrl", "blogProfileImage", "updateTime"):
            _string(node.get(name), f"{path}.{name}")
        _non_negative_integer(node.get("blogNo"), f"{path}.blogNo")
    return BuddyPage(
        items=tuple(buddies),
        current_page=current_page,
        total_page_count=total_page_count,
        public_buddy_count=public_buddy_count,
    )


def parse_directory_list(payload: object) -> tuple[dict[str, Any], ...]:
    """Extract flattened directory topics with their containing group name."""
    response = _object(payload, "response")
    groups = _list(response.get("result"), "response.result")
    topics: list[dict[str, Any]] = []
    for group_index, value in enumerate(groups):
        path = f"response.result[{group_index}]"
        group = _object(value, path)
        group_name = _string(group.get("name"), f"{path}.name")
        entries = _list(group.get("directoryList"), f"{path}.directoryList")
        for index, entry in enumerate(entries):
            entry_path = f"{path}.directoryList[{index}]"
            topic = _object(entry, entry_path)
            _string(topic.get("name"), f"{entry_path}.name")
            _positive_integer(topic.get("sortNo"), f"{entry_path}.sortNo")
            _non_negative_integer(topic.get("seq"), f"{entry_path}.seq")
            topics.append({**topic, "groupName": group_name})
    return tuple(topics)


def parse_directory_posts(payload: object, *, top: bool = False) -> tuple[dict[str, Any], ...]:
    """Extract one measured directory post-list response variant."""
    response = _object(payload, "response")
    if top:
        posts = _list(response.get("result"), "response.result")
        post_list_path = "response.result"
    else:
        result = _object(response.get("result"), "response.result")
        _non_negative_integer(result.get("totalCount"), "response.result.totalCount")
        posts = _list(result.get("postList"), "response.result.postList")
        post_list_path = "response.result.postList"
    for index, value in enumerate(posts):
        path = f"{post_list_path}[{index}]"
        node = _object(value, path)
        _non_empty_string(node.get("domainIdOrBlogId"), f"{path}.domainIdOrBlogId")
        _non_negative_integer(node.get("blogNo"), f"{path}.blogNo")
        _non_negative_integer(node.get("logNo"), f"{path}.logNo")
        for name in ("nickname", "title", "postUrl", "briefContents", "profileImage"):
            _string(node.get(name), f"{path}.{name}")
        if top:
            _non_negative_integer(node.get("directorySeq"), f"{path}.directorySeq")
            _string(node.get("thumbnailUrl"), f"{path}.thumbnailUrl")
            _string(node.get("gdid"), f"{path}.gdid")
            _boolean(node.get("isMarketPost"), f"{path}.isMarketPost")
        else:
            _string(node.get("blogUrl"), f"{path}.blogUrl")
    return tuple(posts)


def parse_comments_info(payload: object) -> CommentsInfo:
    """Extract measured blog, post-title, and total-comment metadata from comments-info."""
    response = _object(payload, "response")
    _boolean(response.get("isSuccess"), "response.isSuccess")
    if response["isSuccess"] is not True:
        raise _drift("response.isSuccess", "true")
    result = _object(response.get("result"), "response.result")
    blog_no = _non_negative_integer(result.get("blogNo"), "response.result.blogNo")
    post_title = _string(result.get("postTitle"), "response.result.postTitle")
    total_count = _non_negative_integer(result.get("totalCount"), "response.result.totalCount")
    for name in ("availableCommentWrite", "memoLog", "postOpenWithCategoryOpenYn"):
        _boolean(result.get(name), f"response.result.{name}")
    return CommentsInfo(blog_no=blog_no, post_title=post_title, total_count=total_count)


def _cbox_timestamp(value: object, path: str) -> None:
    timestamp = _string(value, path)
    if not _CBOX_TIMESTAMP.fullmatch(timestamp):
        raise _drift(path, "an ISO-8601 +0900 timestamp")
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError as error:
        raise _drift(path, "an ISO-8601 +0900 timestamp") from error


def _validate_cbox_card(
    value: object,
    path: str,
    *,
    parent_comment_no: str | None,
    parent_reply_level: int | None,
    seen_comment_nos: set[str],
) -> tuple[int, int]:
    """Validate one nested or flat CBOX card and return its visible totals."""
    card = _object(value, path)
    comment_no = _non_empty_string(card.get("commentNo"), f"{path}.commentNo")
    if comment_no in seen_comment_nos:
        raise _drift(f"{path}.commentNo", "a unique commentNo")
    seen_comment_nos.add(comment_no)
    card_parent = _non_empty_string(card.get("parentCommentNo"), f"{path}.parentCommentNo")
    reply_level = _positive_integer(card.get("replyLevel"), f"{path}.replyLevel")
    if parent_comment_no is None:
        if card_parent == comment_no:
            if reply_level != 1:
                raise _drift(f"{path}.replyLevel", "1 for a top-level comment")
        elif reply_level < 2:
            raise _drift(f"{path}.replyLevel", "2 or greater for a flat reply")
    else:
        if card_parent != parent_comment_no:
            raise _drift(f"{path}.parentCommentNo", "the containing commentNo")
        if reply_level != parent_reply_level + 1:
            raise _drift(f"{path}.replyLevel", "one greater than the containing replyLevel")

    for name in ("contents", "userName", "profileUserId", "userProfileImage"):
        _string(card.get(name), f"{path}.{name}")
    _nullable_string(card.get("maskedUserName"), f"{path}.maskedUserName")
    for name in ("regTime", "modTime"):
        _cbox_timestamp(card.get(name), f"{path}.{name}")
    for name in ("sympathyCount", "antipathyCount", "status"):
        _non_negative_integer(card.get(name), f"{path}.{name}")
    for name in ("best", "deleted", "secret"):
        _boolean(card.get(name), f"{path}.{name}")
    _string(card.get("commentType"), f"{path}.commentType")
    _nullable_string(card.get("stickerId"), f"{path}.stickerId")

    image_value = card.get("imageList")
    images = [] if image_value is None else _list(image_value, f"{path}.imageList")
    for index, image_value in enumerate(images):
        image_path = f"{path}.imageList[{index}]"
        image = _object(image_value, image_path)
        # CBOX serves some attachments with `imageUrl` null and the CDN address under `url`.
        _nullable_string(image.get("imageUrl"), f"{image_path}.imageUrl")
        _nullable_string(image.get("url"), f"{image_path}.url")
        _non_negative_integer(image.get("width"), f"{image_path}.width")
        _non_negative_integer(image.get("height"), f"{image_path}.height")

    reply_count = _non_negative_integer(card.get("replyCount"), f"{path}.replyCount")
    reply_value = card.get("replyList")
    if reply_value is None:
        replies: list[object] = []
    else:
        replies = _list(reply_value, f"{path}.replyList")
        if reply_count != len(replies):
            raise _drift(f"{path}.replyCount", "the number of nested replyList entries")

    comment_total = 1
    reply_total = 0
    for index, reply in enumerate(replies):
        child_comments, child_replies = _validate_cbox_card(
            reply,
            f"{path}.replyList[{index}]",
            parent_comment_no=comment_no,
            parent_reply_level=reply_level,
            seen_comment_nos=seen_comment_nos,
        )
        comment_total += child_comments
        reply_total += 1 + child_replies
    return comment_total, reply_total


def parse_cbox_list(payload: object) -> CommentPage:
    """Extract a strict plain-JSON CBOX comment page without normalizing its cards."""
    response = _object(payload, "response")
    _boolean(response.get("success"), "response.success")
    if response["success"] is not True:
        raise _drift("response.success", "true")
    code = response.get("code")
    if code not in (1000, "1000"):
        raise _drift("response.code", '1000 or "1000"')

    result = _object(response.get("result"), "response.result")
    count = _object(result.get("count"), "response.result.count")
    comment_count = _non_negative_integer(count.get("comment"), "response.result.count.comment")
    reply_count = _non_negative_integer(count.get("reply"), "response.result.count.reply")
    total_count = _non_negative_integer(count.get("total"), "response.result.count.total")
    if total_count != comment_count + reply_count:
        raise _drift("response.result.count.total", "comment count plus reply count")

    page_model = _object(result.get("pageModel"), "response.result.pageModel")
    current_page = _positive_integer(page_model.get("page"), "response.result.pageModel.page")
    page_size = _positive_integer(page_model.get("pageSize"), "response.result.pageModel.pageSize")
    total_pages = _positive_integer(
        page_model.get("totalPages"), "response.result.pageModel.totalPages"
    )
    if current_page > total_pages:
        raise _drift("response.result.pageModel.page", "no greater than totalPages")

    items = _list(result.get("commentList"), "response.result.commentList")
    if len(items) > page_size:
        raise _drift("response.result.commentList", "no more than pageSize entries")
    seen_comment_nos: set[str] = set()
    for index, item in enumerate(items):
        _validate_cbox_card(
            item,
            f"response.result.commentList[{index}]",
            parent_comment_no=None,
            parent_reply_level=None,
            seen_comment_nos=seen_comment_nos,
        )
    return CommentPage(
        items=tuple(items),
        comment_count=comment_count,
        reply_count=reply_count,
        total_count=total_count,
        current_page=current_page,
        total_pages=total_pages,
    )
