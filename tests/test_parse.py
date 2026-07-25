"""Tests for strict, JSON-only section search envelope parsing."""

from __future__ import annotations

import re
from copy import deepcopy

import pytest
from conftest import load_fixture

from agentic_blog.errors import EnvelopeParseError
from agentic_blog.parse import (
    BuddyPage,
    CommentPage,
    CommentsInfo,
    parse_buddies,
    parse_category_list,
    parse_cbox_list,
    parse_comments_info,
    parse_directory_list,
    parse_directory_posts,
    parse_post_list,
    parse_search_page,
)


@pytest.mark.parametrize(
    ("fixture_name", "expected_id", "expected_page_per_count"),
    [
        ("search_post.json", "synthetic_alice", 7),
        ("search_blog.json", "synthetic_alice", 10),
        ("search_id.json", "synthetic_bora", 10),
    ],
)
def test_parse_search_page_returns_raw_items(
    fixture_name: str, expected_id: str, expected_page_per_count: int
) -> None:
    page = parse_search_page(load_fixture(fixture_name))

    assert page.items[0]["domainIdOrBlogId"] == expected_id
    assert page.total_count == 1
    assert page.page_per_count == expected_page_per_count
    assert isinstance(page.display_info, dict)


def test_parse_search_page_allows_empty_list_and_login_hint() -> None:
    payload = load_fixture("search_post.json")
    assert isinstance(payload, dict)
    payload = deepcopy(payload)
    payload["result"]["searchList"] = []
    payload["result"]["totalCount"] = 0

    page = parse_search_page(payload)

    assert page.items == ()
    assert page.display_info["authUrlType"] == "LOGIN"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "response envelope drift at response: expected an object"),
        ({"result": None}, "response envelope drift at response.result: expected an object"),
        (
            {"result": {"searchDisplayInfo": None, "searchList": []}},
            "response envelope drift at response.result.searchDisplayInfo: expected an object",
        ),
        (
            {"result": {"searchDisplayInfo": {}, "searchList": None}},
            "response envelope drift at response.result.searchList: expected a list",
        ),
        (
            {"result": {"searchDisplayInfo": {}, "searchList": [None]}},
            "response envelope drift at response.result.searchList[0]: expected an object",
        ),
        (
            {
                "result": {
                    "searchDisplayInfo": {},
                    "searchList": [],
                    "totalCount": None,
                    "pagePerCount": 7,
                }
            },
            "response envelope drift at response.result.totalCount: expected an integer",
        ),
        (
            {
                "result": {
                    "searchDisplayInfo": {},
                    "searchList": [],
                    "totalCount": 0,
                    "pagePerCount": None,
                }
            },
            "response envelope drift at response.result.pagePerCount: expected an integer",
        ),
    ],
)
def test_parse_search_page_rejects_null_and_shape_drift(payload: object, message: str) -> None:
    with pytest.raises(EnvelopeParseError, match=f"^{re.escape(message)}$"):
        parse_search_page(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "totalCount",
            -1,
            "response envelope drift at response.result.totalCount: "
            "expected a non-negative integer",
        ),
        (
            "pagePerCount",
            0,
            "response envelope drift at response.result.pagePerCount: expected a positive integer",
        ),
        (
            "pagePerCount",
            -1,
            "response envelope drift at response.result.pagePerCount: expected a positive integer",
        ),
        (
            "totalCount",
            True,
            "response envelope drift at response.result.totalCount: expected an integer",
        ),
        (
            "pagePerCount",
            False,
            "response envelope drift at response.result.pagePerCount: expected an integer",
        ),
    ],
)
def test_parse_search_page_rejects_invalid_pagination_counts(
    field: str, value: object, message: str
) -> None:
    payload = {
        "result": {
            "searchDisplayInfo": {},
            "searchList": [],
            "totalCount": 0,
            "pagePerCount": 1,
        }
    }
    payload["result"][field] = value

    with pytest.raises(EnvelopeParseError, match=f"^{re.escape(message)}$"):
        parse_search_page(payload)


@pytest.mark.parametrize(
    ("surface", "parser", "kwargs"),
    [
        ("category_list", parse_category_list, {}),
        ("post_list", parse_post_list, {}),
        ("notice_post_list", parse_post_list, {"kind": "notice"}),
        ("popular_post_list", parse_post_list, {"kind": "popular"}),
        ("directory_list", parse_directory_list, {}),
        ("directory_post_list", parse_directory_posts, {}),
        ("directory_top_post_list", parse_directory_posts, {"top": True}),
    ],
)
def test_phase3_fixture_envelopes_have_exact_normalized_cardinality(
    surface: str, parser, kwargs: dict[str, object]
) -> None:
    fixture = load_fixture("phase3.json")

    assert len(parser(fixture[surface], **kwargs)) == 1


@pytest.mark.parametrize(
    ("top", "surface", "message"),
    [
        (
            False,
            "directory_top_post_list",
            "response envelope drift at response.result: expected an object",
        ),
        (
            True,
            "directory_post_list",
            "response envelope drift at response.result: expected a list",
        ),
    ],
)
def test_directory_post_parser_rejects_variant_envelope_confusion(
    top: bool, surface: str, message: str
) -> None:
    fixture = load_fixture("phase3.json")

    with pytest.raises(EnvelopeParseError, match=f"^{re.escape(message)}$"):
        parse_directory_posts(fixture[surface], top=top)


@pytest.mark.parametrize(
    ("field", "value", "path"),
    [
        ("directorySeq", -1, "response.result[0].directorySeq"),
        ("thumbnailUrl", None, "response.result[0].thumbnailUrl"),
        ("gdid", None, "response.result[0].gdid"),
        ("isMarketPost", None, "response.result[0].isMarketPost"),
    ],
)
def test_directory_top_post_parser_rejects_missing_top_card_fields(
    field: str, value: object, path: str
) -> None:
    payload = deepcopy(load_fixture("phase3.json")["directory_top_post_list"])
    payload["result"][0][field] = value

    with pytest.raises(EnvelopeParseError, match=re.escape(path)):
        parse_directory_posts(payload, top=True)


def test_parse_buddies_returns_page_metadata_and_raw_items() -> None:
    fixture = load_fixture("phase3.json")

    page = parse_buddies(fixture["public_buddies"])

    assert isinstance(page, BuddyPage)
    assert page.current_page == page.total_page_count == 1
    assert isinstance(page.items, tuple)
    assert isinstance(page.items[0], dict)
    assert page.items[0]["blogId"] == "synthetic_bob"
    assert page.items[0]["updateTime"] == "8 minutes ago"


@pytest.mark.parametrize("value", [None, True, -1, 1.0, "20002", [], {}])
def test_parse_buddies_rejects_non_numeric_blog_number(value: object) -> None:
    payload = deepcopy(load_fixture("phase3.json")["public_buddies"])
    payload["result"]["buddyList"][0]["blogNo"] = value

    with pytest.raises(EnvelopeParseError, match=re.escape("response.result.buddyList[0].blogNo")):
        parse_buddies(payload)


def test_parse_buddies_accepts_an_empty_zero_total_page() -> None:
    payload = deepcopy(load_fixture("phase3.json")["public_buddies"])
    payload["result"]["totalPageCount"] = 0
    payload["result"]["currentPage"] = 1
    payload["result"]["buddyList"] = []

    page = parse_buddies(payload)

    assert page.items == ()
    assert page.current_page == 1
    assert page.total_page_count == 0


@pytest.mark.parametrize(
    ("total_page_count", "current_page", "buddy_list", "path"),
    [
        (-1, 1, [], "response.result.totalPageCount"),
        (1, 0, [], "response.result.currentPage"),
        (2, 3, [], "response.result.currentPage"),
        (0, 2, [], "response.result.currentPage"),
        (0, 1, [{"blogId": "unexpected"}], "response.result.buddyList"),
    ],
)
def test_parse_buddies_rejects_inconsistent_pagination_metadata(
    total_page_count: int, current_page: int, buddy_list: list[object], path: str
) -> None:
    payload = deepcopy(load_fixture("phase3.json")["public_buddies"])
    payload["result"]["totalPageCount"] = total_page_count
    payload["result"]["currentPage"] = current_page
    payload["result"]["buddyList"] = buddy_list

    with pytest.raises(EnvelopeParseError, match=re.escape(path)):
        parse_buddies(payload)


def test_phase3_category_parser_filters_separators_and_uses_flat_parent_links() -> None:
    fixture = load_fixture("phase3.json")
    payload = deepcopy(fixture["category_list"])
    root = payload["result"]["mylogCategoryList"][0]
    payload["result"]["mylogCategoryList"].extend(
        [
            {
                **root,
                "categoryNo": 8,
                "categoryName": "Child",
                "parentCategoryNo": 7,
                "childCategory": False,
            },
            {"categoryType": "S", "divisionLine": False, "childCategory": False},
        ]
    )

    categories = parse_category_list(payload)

    assert [(item["categoryNo"], item["parentCategoryNo"]) for item in categories] == [
        (7, None),
        (8, 7),
    ]


@pytest.mark.parametrize("child_category", [[], None, 0, "false"])
def test_phase3_category_parser_rejects_non_boolean_child_category(child_category: object) -> None:
    fixture = load_fixture("phase3.json")
    payload = deepcopy(fixture["category_list"])
    payload["result"]["mylogCategoryList"][0]["childCategory"] = child_category

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.mylogCategoryList[0].childCategory"),
    ):
        parse_category_list(payload)


@pytest.mark.parametrize(
    ("surface", "mutate", "path"),
    [
        (
            "post_list",
            lambda payload: payload["result"]["items"][0].__setitem__("logNo", False),
            "response.result.items[0].logNo",
        ),
        (
            "public_buddies",
            lambda payload: payload["result"]["buddyList"].__setitem__(0, None),
            "response.result.buddyList[0]",
        ),
        (
            "directory_list",
            lambda payload: payload["result"][0]["directoryList"][0].__setitem__("seq", None),
            "response.result[0].directoryList[0].seq",
        ),
    ],
)
def test_phase3_parsers_fail_closed_with_path_specific_errors(surface, mutate, path: str) -> None:
    fixture = load_fixture("phase3.json")
    payload = deepcopy(fixture[surface])
    mutate(payload)
    parser = {
        "post_list": parse_post_list,
        "public_buddies": parse_buddies,
        "directory_list": parse_directory_list,
    }[surface]

    with pytest.raises(EnvelopeParseError, match=re.escape(path)):
        parser(payload)


def test_phase3_post_parser_accepts_measured_integer_editor_version() -> None:
    fixture = load_fixture("phase3.json")

    posts = parse_post_list(fixture["post_list"])

    assert posts[0]["smartEditorVersion"] == 4
    assert posts[0]["thumbnailList"] == [
        {
            "type": "IMAGE",
            "encodedThumbnailUrl": "https://media.example.invalid/posts/10001.jpg",
            "videoAniThumbnailUrl": "",
            "videoPlayTime": None,
            "isPortraitThumbnail": False,
            "videoThumbnail": False,
            "vrthumbnail": False,
        }
    ]


def test_phase3_popular_post_parser_preserves_measured_identity_shape() -> None:
    fixture = load_fixture("phase3.json")

    posts = parse_post_list(fixture["popular_post_list"], kind="popular")

    assert posts[0]["blogId"] == "synthetic_alice"
    assert posts[0]["logNo"] == 10003
    assert "blogNo" not in posts[0]
    assert "domainIdOrBlogId" not in posts[0]
    assert posts[0]["smartEditorVersion"] == 4
    assert isinstance(posts[0]["thumbnailList"][0], dict)


@pytest.mark.parametrize(
    ("remove", "value"),
    [
        (True, None),
        (False, None),
        (False, ""),
        (False, " \t"),
        (False, 20001),
        (False, False),
        (False, 1.0),
        (False, []),
        (False, {}),
    ],
)
def test_phase3_popular_post_parser_rejects_missing_or_malformed_blog_id(
    remove: bool, value: object
) -> None:
    fixture = load_fixture("phase3.json")
    payload = deepcopy(fixture["popular_post_list"])
    card = payload["result"]["popularPostList"][0]
    if remove:
        del card["blogId"]
    else:
        card["blogId"] = value

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.popularPostList[0].blogId"),
    ):
        parse_post_list(payload, kind="popular")


@pytest.mark.parametrize("value", [None, "10003", "", False, 1.0, -1, [], {}])
def test_phase3_popular_post_parser_rejects_invalid_numeric_log_no(value: object) -> None:
    payload = deepcopy(load_fixture("phase3.json")["popular_post_list"])
    payload["result"]["popularPostList"][0]["logNo"] = value

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.popularPostList[0].logNo"),
    ):
        parse_post_list(payload, kind="popular")


@pytest.mark.parametrize("field", ["logNo", "blogNo", "categoryNo"])
@pytest.mark.parametrize("value", [None, True, 1.0, -1, "10001", "", [], {}])
def test_phase3_chronological_post_parser_rejects_non_numeric_identity_fields(
    field: str, value: object
) -> None:
    payload = deepcopy(load_fixture("phase3.json")["post_list"])
    payload["result"]["items"][0][field] = value

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape(f"response.result.items[0].{field}"),
    ):
        parse_post_list(payload)


@pytest.mark.parametrize("value", [None, "", " \t", True, 1.0, -1, 10001, [], {}])
def test_phase3_chronological_post_parser_rejects_non_text_blog_id(value: object) -> None:
    payload = deepcopy(load_fixture("phase3.json")["post_list"])
    payload["result"]["items"][0]["domainIdOrBlogId"] = value

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.items[0].domainIdOrBlogId"),
    ):
        parse_post_list(payload)


@pytest.mark.parametrize("kind", ["chronological", "popular"])
@pytest.mark.parametrize("value", [None, True, 4.0, [], {}, -1, "4", "ONE"])
def test_phase3_full_post_parser_rejects_null_or_invalid_editor_versions(
    kind: str, value: object
) -> None:
    surface = "post_list" if kind == "chronological" else "popular_post_list"
    key = "items" if kind == "chronological" else "popularPostList"
    payload = deepcopy(load_fixture("phase3.json")[surface])
    payload["result"][key][0]["smartEditorVersion"] = value

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape(f"response.result.{key}[0].smartEditorVersion"),
    ):
        parse_post_list(payload, kind=kind)


@pytest.mark.parametrize("kind", ["chronological", "popular"])
def test_phase3_full_post_parser_rejects_missing_editor_version(kind: str) -> None:
    surface = "post_list" if kind == "chronological" else "popular_post_list"
    key = "items" if kind == "chronological" else "popularPostList"
    payload = deepcopy(load_fixture("phase3.json")[surface])
    del payload["result"][key][0]["smartEditorVersion"]

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape(f"response.result.{key}[0].smartEditorVersion"),
    ):
        parse_post_list(payload, kind=kind)


def test_phase3_chronological_post_parser_rejects_popular_card_shape() -> None:
    fixture = load_fixture("phase3.json")
    payload = deepcopy(fixture["post_list"])
    payload["result"]["items"] = deepcopy(fixture["popular_post_list"]["result"]["popularPostList"])

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.items[0].blogNo"),
    ):
        parse_post_list(payload)


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (
            lambda thumbnail: thumbnail.__setitem__("type", None),
            "response.result.items[0].thumbnailList[0].type",
        ),
        (
            lambda thumbnail: thumbnail.__delitem__("encodedThumbnailUrl"),
            "response.result.items[0].thumbnailList[0].encodedThumbnailUrl",
        ),
        (
            lambda thumbnail: thumbnail.__setitem__("videoAniThumbnailUrl", False),
            "response.result.items[0].thumbnailList[0].videoAniThumbnailUrl",
        ),
        (
            lambda thumbnail: thumbnail.__setitem__("videoPlayTime", []),
            "response.result.items[0].thumbnailList[0].videoPlayTime",
        ),
        (
            lambda thumbnail: thumbnail.__setitem__("isPortraitThumbnail", "false"),
            "response.result.items[0].thumbnailList[0].isPortraitThumbnail",
        ),
        (
            lambda thumbnail: thumbnail.__setitem__("videoThumbnail", 0),
            "response.result.items[0].thumbnailList[0].videoThumbnail",
        ),
        (
            lambda thumbnail: thumbnail.__setitem__("vrthumbnail", "true"),
            "response.result.items[0].thumbnailList[0].vrthumbnail",
        ),
    ],
)
def test_phase3_post_parser_rejects_malformed_thumbnail_object_fields(mutate, path: str) -> None:
    fixture = load_fixture("phase3.json")
    payload = deepcopy(fixture["post_list"])
    mutate(payload["result"]["items"][0]["thumbnailList"][0])

    with pytest.raises(EnvelopeParseError, match=re.escape(path)):
        parse_post_list(payload)


@pytest.mark.parametrize("value", ["https://media.example.invalid/posts/10001.jpg", None, []])
def test_phase3_post_parser_rejects_non_object_thumbnail_entries(value: object) -> None:
    fixture = load_fixture("phase3.json")
    payload = deepcopy(fixture["post_list"])
    payload["result"]["items"][0]["thumbnailList"] = [value]

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.items[0].thumbnailList[0]"),
    ):
        parse_post_list(payload)


@pytest.mark.parametrize("value", [None, True, -1, "1"])
def test_directory_post_parser_requires_non_negative_total_count(value: object) -> None:
    payload = deepcopy(load_fixture("phase3.json")["directory_post_list"])
    payload["result"]["totalCount"] = value

    with pytest.raises(EnvelopeParseError, match=re.escape("response.result.totalCount")):
        parse_directory_posts(payload)


def test_directory_post_parser_rejects_missing_total_count() -> None:
    payload = deepcopy(load_fixture("phase3.json")["directory_post_list"])
    del payload["result"]["totalCount"]

    with pytest.raises(EnvelopeParseError, match=re.escape("response.result.totalCount")):
        parse_directory_posts(payload)


@pytest.mark.parametrize("top", [False, True])
@pytest.mark.parametrize("field", ["logNo", "blogNo"])
@pytest.mark.parametrize("value", [None, True, 1.0, -1, "10001", "", [], {}])
def test_directory_post_parser_rejects_non_numeric_identity_fields(
    top: bool, field: str, value: object
) -> None:
    surface = "directory_top_post_list" if top else "directory_post_list"
    payload = deepcopy(load_fixture("phase3.json")[surface])
    card = payload["result"][0] if top else payload["result"]["postList"][0]
    card[field] = value
    path = f"response.result{'[0]' if top else '.postList[0]'}.{field}"

    with pytest.raises(EnvelopeParseError, match=re.escape(path)):
        parse_directory_posts(payload, top=top)


@pytest.mark.parametrize("top", [False, True])
@pytest.mark.parametrize("value", [None, "", " \t", True, 1.0, -1, 10001, [], {}])
def test_directory_post_parser_rejects_non_text_blog_id(top: bool, value: object) -> None:
    surface = "directory_top_post_list" if top else "directory_post_list"
    payload = deepcopy(load_fixture("phase3.json")[surface])
    card = payload["result"][0] if top else payload["result"]["postList"][0]
    card["domainIdOrBlogId"] = value
    path = f"response.result{'[0]' if top else '.postList[0]'}.domainIdOrBlogId"

    with pytest.raises(EnvelopeParseError, match=re.escape(path)):
        parse_directory_posts(payload, top=top)


def test_phase3_category_parser_rejects_duplicate_orphaned_and_cyclic_tree_links() -> None:
    fixture = load_fixture("phase3.json")
    duplicate = deepcopy(fixture["category_list"])
    duplicate["result"]["mylogCategoryList"].append(
        {**duplicate["result"]["mylogCategoryList"][0], "childCategory": False}
    )
    with pytest.raises(EnvelopeParseError, match="unique categoryNo"):
        parse_category_list(duplicate)

    orphaned = deepcopy(fixture["category_list"])
    orphaned["result"]["mylogCategoryList"][0]["parentCategoryNo"] = 99
    with pytest.raises(EnvelopeParseError, match="parentCategoryNo"):
        parse_category_list(orphaned)
    cyclic = deepcopy(fixture["category_list"])
    root = cyclic["result"]["mylogCategoryList"][0]
    cyclic["result"]["mylogCategoryList"].extend(
        [{**root, "categoryNo": 8, "parentCategoryNo": 7, "childCategory": False}]
    )
    root["parentCategoryNo"] = 8
    with pytest.raises(EnvelopeParseError, match="acyclic category tree"):
        parse_category_list(cyclic)


def test_phase4_parsers_return_measured_immutable_metadata_and_raw_cards() -> None:
    fixture = load_fixture("phase4.json")

    info = parse_comments_info(fixture["comments_info"])
    page = parse_cbox_list(fixture["cbox_list"])

    assert isinstance(info, CommentsInfo)
    assert (info.blog_no, info.post_title, info.total_count) == (20001, "합성 댓글 예시", 3)
    assert isinstance(page, CommentPage)
    assert (page.comment_count, page.reply_count, page.total_count) == (2, 1, 3)
    assert page.items == tuple(fixture["cbox_list"]["result"]["commentList"])


@pytest.mark.parametrize(
    ("surface", "mutate", "path"),
    [
        (
            "comments_info",
            lambda payload: payload.__setitem__("isSuccess", False),
            "response.isSuccess",
        ),
        (
            "comments_info",
            lambda payload: payload["result"].pop("postTitle"),
            "response.result.postTitle",
        ),
        (
            "comments_info",
            lambda payload: payload["result"].__setitem__("postTitle", None),
            "response.result.postTitle",
        ),
        (
            "comments_info",
            lambda payload: payload["result"].__setitem__("postTitle", 123),
            "response.result.postTitle",
        ),
        (
            "cbox_list",
            lambda payload: payload.__setitem__("code", 1001),
            "response.code",
        ),
        (
            "cbox_list",
            lambda payload: payload["result"]["count"].__setitem__("total", 2),
            "response.result.count.total",
        ),
        (
            "cbox_list",
            lambda payload: payload["result"]["commentList"][0].__setitem__("replyCount", 0),
            "response.result.commentList[0].replyCount",
        ),
        (
            "cbox_list",
            lambda payload: payload["result"]["commentList"][0]["replyList"][0].__setitem__(
                "parentCommentNo", "wrong"
            ),
            "response.result.commentList[0].replyList[0].parentCommentNo",
        ),
        (
            "cbox_list",
            lambda payload: payload["result"]["commentList"][0].__setitem__(
                "regTime", "2026-07-25T10:00:00Z"
            ),
            "response.result.commentList[0].regTime",
        ),
        (
            "cbox_list",
            lambda payload: payload["result"]["commentList"][0].__setitem__("profileUserId", None),
            "response.result.commentList[0].profileUserId",
        ),
    ],
)
def test_phase4_parsers_fail_closed_on_envelope_and_tree_drift(surface, mutate, path: str) -> None:
    payload = deepcopy(load_fixture("phase4.json")[surface])
    mutate(payload)
    parser = parse_comments_info if surface == "comments_info" else parse_cbox_list

    with pytest.raises(EnvelopeParseError, match=re.escape(path)):
        parser(payload)
