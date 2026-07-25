from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from datetime import UTC, datetime, timedelta, timezone
from typing import get_args

import jsonschema
import pytest
from conftest import load_fixture

from agentic_blog.model import (
    FIELD_DESCRIPTIONS,
    Blog,
    Category,
    Comment,
    Media,
    MediaKind,
    Post,
    PostVisibility,
    Topic,
    _schema_sample,
    build_buddy_blog,
    build_category,
    build_comment,
    build_directory_post,
    build_mobile_post,
    build_search_blog,
    build_search_id,
    build_search_post,
    build_topic,
    json_schema,
    schema_fields,
)
from agentic_blog.parse import (
    parse_buddies,
    parse_category_list,
    parse_cbox_list,
    parse_directory_list,
    parse_directory_posts,
    parse_post_list,
    parse_search_page,
)

_CAPTURED_AT = datetime(2026, 7, 25, 12, 30, 45, tzinfo=UTC)


def test_post_serialization_uses_stable_json_values() -> None:
    post = Post(
        log_no=987654321012345678,
        blog_id="한글블로그",
        blog_no=123456789012345678,
        url="https://blog.naver.com/한글블로그/987654321012345678",
        title="안녕하세요, 서울",
        brief="한국어 요약",
        body="본문",
        created_at=datetime(2026, 7, 25, 21, 30, 45, tzinfo=timezone(timedelta(hours=9))),
        category_no=42,
        media=[Media(kind="photo", url="https://example.test/사진.jpg", caption="풍경")],
        comments=[],
        captured_at=_CAPTURED_AT,
    )

    assert post.to_dict() == {
        "log_no": "987654321012345678",
        "blog_id": "한글블로그",
        "blog_no": "123456789012345678",
        "url": "https://blog.naver.com/한글블로그/987654321012345678",
        "title": "안녕하세요, 서울",
        "brief": "한국어 요약",
        "body": "본문",
        "created_at": "2026-07-25T12:30:45Z",
        "blog_name": None,
        "nickname": None,
        "category_no": "42",
        "category_name": None,
        "comment_count": None,
        "like_count": None,
        "share_count": None,
        "thumbnail_url": None,
        "media": [
            {
                "kind": "photo",
                "url": "https://example.test/사진.jpg",
                "caption": "풍경",
                "width": None,
                "height": None,
            }
        ],
        "editor_version": None,
        "visibility": None,
        "is_notice": False,
        "comments": [],
        "captured_at": "2026-07-25T12:30:45Z",
    }
    assert Post().to_dict()["blog_no"] is None
    assert Post().to_dict()["media"] is None


def test_ids_are_strings_and_raw_is_opt_in() -> None:
    category = Category(category_no=100000000000000001, parent_category_no=99)
    comment = Comment(comment_no=200000000000000001, parent_comment_no=200000000000000000)
    blog = Blog(blog_no=300000000000000001)
    topic = Topic(seq=400000000000000001)

    assert category.to_dict()["category_no"] == "100000000000000001"
    assert category.to_dict()["parent_category_no"] == "99"
    assert comment.to_dict()["comment_no"] == "200000000000000001"
    assert comment.to_dict()["parent_comment_no"] == "200000000000000000"
    assert blog.to_dict()["blog_no"] == "300000000000000001"
    assert topic.to_dict()["seq"] == "400000000000000001"
    assert "raw" not in Post().to_dict()
    assert Post(raw={"logNo": 1}).to_dict()["raw"] == {"logNo": 1}
    post = Post(log_no=10, blog_id=20, blog_no=30, category_no=40)
    comment = Comment(comment_no=50, parent_comment_no=60, author_blog_id=70, sticker_id=80)
    assert (post.log_no, post.blog_id, post.blog_no, post.category_no) == ("10", "20", "30", "40")
    assert (
        comment.comment_no,
        comment.parent_comment_no,
        comment.author_blog_id,
        comment.sticker_id,
    ) == (
        "50",
        "60",
        "70",
        "80",
    )
    assert Blog(blog_id=90, blog_no=100).blog_id == "90"
    assert Blog(blog_id=90, blog_no=100).blog_no == "100"
    assert Topic(seq=110).seq == "110"


def test_search_post_builder_normalizes_listing_values() -> None:
    node = {
        "domainIdOrBlogId": "한글블로그",
        "blogNo": 123456789012345678,
        "logNo": 987654321012345678,
        "title": '<strong class="search_keyword">서울</strong> &amp; 카페',
        "contents": '좋은 <strong class="search_keyword">커피</strong> &quot;한 잔&quot;',
        "addDate": 1_753_445_445_000,
        "blogName": '<strong class="search_keyword">한글</strong> 블로그',
        "nickName": "작성자",
        "commentCnt": 2,
        "sympathyCnt": 3,
        "shareCnt": 4,
        "thumbnailUrl": "https://example.test/thumbnail.jpg",
        "smartEditorVersion": 4,
        "bothBuddyOpen": True,
    }

    post = build_search_post(node, captured_at=_CAPTURED_AT)

    assert post.to_dict() == {
        **Post(
            log_no="987654321012345678",
            blog_id="한글블로그",
            blog_no="123456789012345678",
            url="https://blog.naver.com/한글블로그/987654321012345678",
            title="서울 & 카페",
            brief='좋은 커피 "한 잔"',
            created_at=datetime(2025, 7, 25, 12, 10, 45, tzinfo=UTC),
            blog_name="한글 블로그",
            nickname="작성자",
            comment_count=2,
            like_count=3,
            share_count=4,
            thumbnail_url="https://example.test/thumbnail.jpg",
            editor_version="4",
            visibility="both_buddy",
            captured_at=_CAPTURED_AT,
        ).to_dict(),
    }
    assert "raw" not in post.to_dict()
    missing_blog_no = deepcopy(node)
    del missing_blog_no["blogNo"]
    nullable_post = build_search_post(missing_blog_no, captured_at=_CAPTURED_AT)
    assert nullable_post.blog_no is None
    assert nullable_post.to_dict()["blog_no"] is None
    assert nullable_post.media is None
    jsonschema.Draft202012Validator(json_schema()["$defs"]["Post"]).validate(post.to_dict())


def test_search_blog_and_id_builders_keep_their_distinct_search_shapes() -> None:
    blog_node = {
        "domainIdOrBlogId": "search-blog",
        "blogNo": 123456789012345678,
        "blogName": '<strong class="search_keyword">검색</strong> 블로그',
        "nickName": "닉네임",
        "blogDesc": "한국어 &amp; 설명",
        "profileImgUrl": "https://example.test/profile.jpg",
    }
    id_node = {
        **blog_node,
        "domainIdOrBlogId": "search-id",
        "blogName": '<strong class="search_keyword">아이디</strong>',
    }

    blog = build_search_blog(blog_node, captured_at=_CAPTURED_AT, include_raw=True)
    by_id = build_search_id(id_node, captured_at=_CAPTURED_AT)

    assert blog.to_dict() == {
        "blog_id": "search-blog",
        "blog_no": "123456789012345678",
        "blog_name": "검색 블로그",
        "nickname": "닉네임",
        "description": "한국어 & 설명",
        "profile_image_url": "https://example.test/profile.jpg",
        "url": "https://blog.naver.com/search-blog",
        "buddy_count": None,
        "post_count": None,
        "categories": None,
        "captured_at": "2026-07-25T12:30:45Z",
        "raw": blog_node,
    }
    assert by_id.to_dict()["blog_id"] == "search-id"
    assert by_id.to_dict()["blog_name"] == "아이디"
    assert by_id.to_dict()["url"] == "https://blog.naver.com/search-id"
    assert "raw" not in by_id.to_dict()
    jsonschema.Draft202012Validator(json_schema()["$defs"]["Blog"]).validate(blog.to_dict())
    jsonschema.Draft202012Validator(json_schema()["$defs"]["Blog"]).validate(by_id.to_dict())


@pytest.mark.parametrize(
    ("fixture_name", "builder", "definition"),
    [
        ("search_post.json", build_search_post, "Post"),
        ("search_blog.json", build_search_blog, "Blog"),
        ("search_id.json", build_search_id, "Blog"),
    ],
)
def test_synthetic_search_fixture_normalizers_conform_to_generated_schema(
    fixture_name: str, builder, definition: str
) -> None:
    page = parse_search_page(load_fixture(fixture_name))
    validator = jsonschema.Draft202012Validator(
        json_schema()["$defs"][definition],
        format_checker=jsonschema.FormatChecker(),
    )

    for node in page.items:
        validator.validate(builder(node, captured_at=_CAPTURED_AT).to_dict())


@pytest.mark.parametrize(
    ("flags", "visibility"),
    [
        ({}, "public"),
        ({"buddyOpen": True}, "buddy"),
        ({"bothBuddyOpen": True}, "both_buddy"),
        ({"notOpen": True}, "private"),
        ({"notOpen": True, "bothBuddyOpen": True, "buddyOpen": True}, "private"),
    ],
)
def test_search_post_builder_maps_every_visibility_branch(
    flags: dict[str, bool], visibility: PostVisibility
) -> None:
    post = build_search_post(
        {
            "domainIdOrBlogId": "search-blog",
            "logNo": "10001",
            "blogNo": "20001",
            "addDate": "1753445445000",
            **flags,
        },
        captured_at=_CAPTURED_AT,
    )

    assert post.visibility == visibility
    jsonschema.Draft202012Validator(json_schema()["$defs"]["Post"]).validate(post.to_dict())


@pytest.mark.parametrize(
    ("category_no", "category_name", "is_notice"),
    [(123, "일상", True), (None, None, False)],
)
def test_search_post_builder_maps_category_and_notice_fields(
    category_no: int | None, category_name: str | None, is_notice: bool
) -> None:
    post = build_search_post(
        {
            "domainIdOrBlogId": "search-blog",
            "logNo": "10001",
            "blogNo": "20001",
            "addDate": 1_753_445_445_000,
            "categoryNo": category_no,
            "categoryName": category_name,
            "isNotice": is_notice,
            "commentCnt": "2",
            "sympathyCnt": "3",
            "shareCnt": "4",
        },
        captured_at=_CAPTURED_AT,
    )

    assert post.category_no == (str(category_no) if category_no is not None else None)
    assert post.category_name == category_name
    assert post.is_notice is is_notice
    assert (post.comment_count, post.like_count, post.share_count) == (2, 3, 4)
    jsonschema.Draft202012Validator(json_schema()["$defs"]["Post"]).validate(post.to_dict())


@pytest.mark.parametrize(
    ("add_date", "expected"),
    [(None, None), ("1753445445000", datetime(2025, 7, 25, 12, 10, 45, tzinfo=UTC))],
)
def test_search_post_builder_accepts_null_and_integer_timestamps(
    add_date: str | None, expected: datetime | None
) -> None:
    post = build_search_post(
        {
            "domainIdOrBlogId": "search-blog",
            "blogNo": "20001",
            "logNo": "10001",
            "addDate": add_date,
        },
        captured_at=_CAPTURED_AT,
    )

    assert post.created_at == expected
    jsonschema.Draft202012Validator(json_schema()["$defs"]["Post"]).validate(post.to_dict())


@pytest.mark.parametrize("add_date", [True, 1.5, "1753445445000.0", "not-a-timestamp", {}])
def test_search_post_builder_rejects_invalid_timestamps(add_date: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_search_post(
            {
                "domainIdOrBlogId": "search-blog",
                "blogNo": "20001",
                "logNo": "10001",
                "addDate": add_date,
            },
            captured_at=_CAPTURED_AT,
        )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ('<strong class="search_keyword featured">서울</strong>', "서울"),
        ("<strong data-kind='highlight' class='featured search_keyword'>서울</strong>", "서울"),
        ("<strong class=search_keyword>서울</strong>", "서울"),
        ('<strong class="featured">서울</strong>', '<strong class="featured">서울</strong>'),
        (
            '<strong class="search_keyword_extra">서울</strong>',
            '<strong class="search_keyword_extra">서울</strong>',
        ),
        (
            '<strong data-class="search_keyword">서울</strong>',
            '<strong data-class="search_keyword">서울</strong>',
        ),
        (
            '<strong data-kind="class=search_keyword">서울</strong>',
            '<strong data-kind="class=search_keyword">서울</strong>',
        ),
        (
            '<strong data-note="not a class=search_keyword >">서울</strong>',
            '<strong data-note="not a class=search_keyword >">서울</strong>',
        ),
        ('<strong data-note="a > b" class="search_keyword">서울</strong>', "서울"),
        ('<strong hidden class="search_keyword">서울</strong>', "서울"),
    ],
)
def test_search_post_builder_only_strips_search_keyword_class_token(
    title: str, expected: str
) -> None:
    post = build_search_post(
        {"domainIdOrBlogId": "search-blog", "blogNo": "20001", "logNo": "10001", "title": title},
        captured_at=_CAPTURED_AT,
    )

    assert post.title == expected
    jsonschema.Draft202012Validator(json_schema()["$defs"]["Post"]).validate(post.to_dict())


@pytest.mark.parametrize(
    ("builder", "node", "definition"),
    [
        (
            build_search_post,
            {"domainIdOrBlogId": "search-post", "blogNo": "20001", "logNo": "10001"},
            "Post",
        ),
        (build_search_blog, {"domainIdOrBlogId": "search-blog"}, "Blog"),
        (build_search_id, {"domainIdOrBlogId": "search-id"}, "Blog"),
    ],
)
@pytest.mark.parametrize("include_raw", [False, True])
def test_search_builders_schema_validate_with_raw_opt_in(
    builder, node: dict[str, object], definition: str, include_raw: bool
) -> None:
    result = builder(node, captured_at=_CAPTURED_AT, include_raw=include_raw)
    payload = result.to_dict()

    assert ("raw" in payload) is include_raw
    if include_raw:
        assert payload["raw"] == node
    jsonschema.Draft202012Validator(json_schema()["$defs"][definition]).validate(payload)


@pytest.mark.parametrize(
    ("builder", "node", "definition"),
    [
        (
            build_search_post,
            {
                "domainIdOrBlogId": "search-post",
                "logNo": "10001",
                "blogNo": "20001",
                "title": '<strong class="search_keyword">제목</strong>',
                "contents": "요약 &amp; 내용",
                "blogName": "블로그",
                "nickName": "작성자",
                "categoryName": "카테고리",
                "thumbnailUrl": "https://example.test/thumbnail.jpg",
            },
            "Post",
        ),
        (
            build_search_blog,
            {
                "domainIdOrBlogId": "search-blog",
                "blogName": "블로그",
                "nickName": "작성자",
                "blogDesc": "설명 &amp; 내용",
                "profileImgUrl": "https://example.test/profile.jpg",
            },
            "Blog",
        ),
        (
            build_search_id,
            {
                "domainIdOrBlogId": "search-id",
                "blogName": "블로그",
                "nickName": "작성자",
                "blogDesc": "설명 &amp; 내용",
                "profileImgUrl": "https://example.test/profile.jpg",
            },
            "Blog",
        ),
    ],
)
def test_search_builders_accept_string_display_text_and_urls(
    builder, node: dict[str, object], definition: str
) -> None:
    result = builder(node, captured_at=_CAPTURED_AT)

    jsonschema.Draft202012Validator(json_schema()["$defs"][definition]).validate(result.to_dict())


@pytest.mark.parametrize(
    ("builder", "field"),
    [
        *(
            (build_search_post, field)
            for field in (
                "title",
                "contents",
                "blogName",
                "nickName",
                "categoryName",
                "thumbnailUrl",
            )
        ),
        *(
            (builder, field)
            for builder in (build_search_blog, build_search_id)
            for field in ("blogName", "nickName", "blogDesc", "profileImgUrl")
        ),
    ],
)
@pytest.mark.parametrize("value", [[], {}, True, 1, 1.5])
def test_search_builders_reject_non_string_display_text_and_urls(
    builder, field: str, value: object
) -> None:
    node: dict[str, object] = {"domainIdOrBlogId": "search-blog", field: value}
    if builder is build_search_post:
        node["logNo"] = "10001"
        node["blogNo"] = "20001"

    with pytest.raises(TypeError):
        builder(node, captured_at=_CAPTURED_AT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("domainIdOrBlogId", True),
        ("logNo", 1.5),
        ("logNo", None),
        ("blogNo", {}),
        ("categoryNo", False),
        ("smartEditorVersion", []),
        ("commentCnt", True),
        ("sympathyCnt", 1.5),
        ("shareCnt", "1.5"),
        ("notOpen", 1),
        ("bothBuddyOpen", "true"),
        ("buddyOpen", None),
        ("isNotice", "yes"),
    ],
)
def test_search_post_builder_rejects_malformed_scalars(field: str, value: object) -> None:
    node: dict[str, object] = {
        "domainIdOrBlogId": "search-blog",
        "logNo": "10001",
        "blogNo": "20001",
        field: value,
    }

    with pytest.raises((TypeError, ValueError)):
        build_search_post(node, captured_at=_CAPTURED_AT)


@pytest.mark.parametrize(
    ("builder", "node"),
    [
        (build_search_blog, {"domainIdOrBlogId": True}),
        (build_search_blog, {"domainIdOrBlogId": None}),
        (build_search_blog, {"domainIdOrBlogId": "search-blog", "blogNo": 1.5}),
        (build_search_id, {"domainIdOrBlogId": []}),
        (build_search_id, {"domainIdOrBlogId": "search-id", "blogNo": False}),
    ],
)
def test_search_blog_and_id_builders_reject_malformed_identifiers(builder, node) -> None:
    with pytest.raises(TypeError):
        builder(node, captured_at=_CAPTURED_AT)


@pytest.mark.parametrize(
    ("builder", "node"),
    [
        (build_search_post, {"logNo": "10001"}),
        (build_search_post, {"domainIdOrBlogId": "search-post"}),
        (build_search_blog, {}),
        (build_search_id, {}),
    ],
)
def test_search_builders_reject_missing_required_identities(builder, node) -> None:
    with pytest.raises(KeyError):
        builder(node, captured_at=_CAPTURED_AT)


@pytest.mark.parametrize(
    ("builder", "node"),
    [
        (build_search_post, {"domainIdOrBlogId": "", "logNo": "10001"}),
        (build_search_post, {"domainIdOrBlogId": "search-post", "logNo": ""}),
        (build_search_blog, {"domainIdOrBlogId": ""}),
        (build_search_id, {"domainIdOrBlogId": ""}),
    ],
)
def test_search_builders_reject_empty_required_identities(builder, node) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        builder(node, captured_at=_CAPTURED_AT)


@pytest.mark.parametrize(
    ("builder", "node"),
    [
        (build_search_post, {"domainIdOrBlogId": [], "logNo": "10001"}),
        (build_search_post, {"domainIdOrBlogId": "search-post", "logNo": True}),
        (build_search_blog, {"domainIdOrBlogId": 1.5}),
        (build_search_id, {"domainIdOrBlogId": None}),
    ],
)
def test_search_builders_reject_malformed_required_identities(builder, node) -> None:
    with pytest.raises(TypeError):
        builder(node, captured_at=_CAPTURED_AT)


def test_recursive_comments_serialize_without_dataclass_conversion() -> None:
    reply = Comment(comment_no=2, parent_comment_no=1, is_reply=True, depth=1, text="답글")
    root = Comment(comment_no=1, depth=0, text="댓글", replies=[reply])

    assert root.to_dict()["replies"] == [
        {
            "comment_no": "2",
            "parent_comment_no": "1",
            "is_reply": True,
            "depth": 1,
            "text": "답글",
            "author_name": None,
            "author_blog_id": None,
            "author_profile_image_url": None,
            "created_at": None,
            "like_count": None,
            "dislike_count": None,
            "is_best": False,
            "is_deleted": False,
            "is_secret": False,
            "sticker_id": None,
            "image_urls": [],
            "replies": [],
        }
    ]


def test_field_descriptions_cover_every_serialized_field() -> None:
    for model in (Post, Blog, Topic, Comment, Media, Category):
        names = [field["name"] for field in schema_fields(model)]
        assert set(names) == set(FIELD_DESCRIPTIONS[model.__name__])
        assert all(FIELD_DESCRIPTIONS[model.__name__][name] for name in names)


@pytest.mark.parametrize("model", [Post, Blog, Topic, Comment, Media, Category])
def test_schema_fields_are_anchored_to_populated_serialization(model) -> None:
    representative = _schema_sample(model)
    field_specs = schema_fields(model)
    schema_names = [field["name"] for field in field_specs]
    optional_names = {field["name"] for field in field_specs if not field["always_present"]}
    declared_optional_names = {
        dataclass_field.name
        for dataclass_field in fields(model)
        if dataclass_field.metadata.get("omit_none")
    }

    assert schema_names == list(representative)
    assert optional_names == declared_optional_names
    assert optional_names <= representative.keys()
    assert set(representative) - set(model().to_dict()) == optional_names


def test_generated_json_schema_is_valid_and_accepts_read_command_outputs() -> None:
    schema = json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    post = Post(
        log_no=1,
        blog_id="테스트",
        blog_no=2,
        url="https://blog.naver.com/테스트/1",
        title="한국어 제목",
        body="한국어 본문",
        media=[Media(kind="photo", url="https://example.test/한글.jpg")],
        comments=[Comment(comment_no=3, text="좋은 글입니다")],
        captured_at=_CAPTURED_AT,
    ).to_dict()
    blog = Blog(blog_id="테스트", blog_no=2, blog_name="테스트 블로그").to_dict()
    topic = Topic(seq="1", name="테스트", group_name="테스트 그룹").to_dict()

    validator.validate([])
    validator.validate([post])
    validator.validate([blog])
    validator.validate([topic])
    with pytest.raises(jsonschema.ValidationError):
        validator.validate([post, blog])
    with pytest.raises(jsonschema.ValidationError):
        validator.validate([{**post, "unexpected": True}])
    assert schema["$defs"]["Post"]["properties"]["media"]["anyOf"] == [
        {"type": "array", "items": {"$ref": "#/$defs/Media"}},
        {"type": "null"},
    ]
    assert schema["$defs"]["Post"]["properties"]["blog_no"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert schema["$defs"]["Post"]["properties"]["comments"]["anyOf"][0]["items"] == {
        "$ref": "#/$defs/Comment"
    }


@pytest.mark.parametrize("model", [Post, Blog, Topic, Comment, Media, Category])
def test_every_model_wire_schema_rejects_missing_and_extra_properties(model) -> None:
    schema = json_schema()
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    payload = model().to_dict()
    object_schema = schema["$defs"][model.__name__]

    object_validator = validator.evolve(schema=object_schema)
    object_validator.validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        object_validator.validate({**payload, "unexpected": True})
    missing = dict(payload)
    missing.pop(object_schema["required"][0])
    with pytest.raises(jsonschema.ValidationError):
        object_validator.validate(missing)


def test_schema_rejects_invalid_enums_timestamps_and_raw_values() -> None:
    schema = json_schema()
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

    media = Media().to_dict()
    media["kind"] = "audio"
    media_validator = validator.evolve(schema=schema["$defs"]["Media"])
    with pytest.raises(jsonschema.ValidationError):
        media_validator.validate(media)
    with pytest.raises(ValueError, match="Unsupported media kind"):
        Media(kind="audio")

    post = Post(visibility="public", created_at=_CAPTURED_AT).to_dict()
    post["visibility"] = "friends"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate([post])
    post["visibility"] = "public"
    post["created_at"] = "not-a-timestamp"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate([post])
    with pytest.raises(ValueError, match="Unsupported post visibility"):
        Post(visibility="friends")

    for model in (Post, Blog):
        payload = model(raw={"source": "upstream"}).to_dict()
        model_validator = validator.evolve(schema=schema["$defs"][model.__name__])
        model_validator.validate(payload)
        payload["raw"] = None
        with pytest.raises(jsonschema.ValidationError):
            model_validator.validate(payload)
        with pytest.raises(TypeError, match="raw must be an object"):
            model(raw=[])


def test_schema_emits_exact_enum_constraints() -> None:
    schema = json_schema()

    assert schema["$defs"]["Media"]["properties"]["kind"]["enum"] == list(get_args(MediaKind))
    assert schema["$defs"]["Post"]["properties"]["visibility"]["anyOf"][0]["enum"] == list(
        get_args(PostVisibility)
    )


@pytest.mark.parametrize("kind", get_args(MediaKind))
def test_media_kind_members_serialize_and_validate(kind) -> None:
    schema = json_schema()
    payload = Media(kind=kind).to_dict()

    assert payload["kind"] == kind
    jsonschema.Draft202012Validator(schema["$defs"]["Media"]).validate(payload)


@pytest.mark.parametrize("visibility", get_args(PostVisibility))
def test_post_visibility_members_serialize_and_validate(visibility) -> None:
    schema = json_schema()
    payload = Post(visibility=visibility).to_dict()

    assert payload["visibility"] == visibility
    jsonschema.Draft202012Validator(schema["$defs"]["Post"]).validate(payload)


def test_phase3_builders_normalize_fixture_surfaces_to_generated_schema() -> None:
    fixture = load_fixture("phase3.json")
    schema = json_schema()
    validators = {
        name: jsonschema.Draft202012Validator(schema["$defs"][name])
        for name in ("Post", "Blog", "Category", "Topic")
    }
    categories = [build_category(node) for node in parse_category_list(fixture["category_list"])]
    chronological = [
        build_mobile_post(node, captured_at=_CAPTURED_AT, kind="chronological")
        for node in parse_post_list(fixture["post_list"])
    ]
    notices = [
        build_mobile_post(node, captured_at=_CAPTURED_AT, kind="notice", is_notice=True)
        for node in parse_post_list(fixture["notice_post_list"], kind="notice")
    ]
    popular = [
        build_mobile_post(node, captured_at=_CAPTURED_AT, kind="popular")
        for node in parse_post_list(fixture["popular_post_list"], kind="popular")
    ]
    buddies = [
        build_buddy_blog(node, captured_at=_CAPTURED_AT)
        for node in parse_buddies(fixture["public_buddies"]).items
    ]
    topics = [build_topic(node) for node in parse_directory_list(fixture["directory_list"])]
    directory_nodes = [
        *parse_directory_posts(fixture["directory_post_list"]),
        *parse_directory_posts(fixture["directory_top_post_list"], top=True),
    ]
    directory_posts = [
        build_directory_post(node, captured_at=_CAPTURED_AT) for node in directory_nodes
    ]

    for category in categories:
        validators["Category"].validate(category.to_dict())
    for post in [*chronological, *notices, *popular, *directory_posts]:
        validators["Post"].validate(post.to_dict())
    for buddy in buddies:
        validators["Blog"].validate(buddy.to_dict())
    for topic in topics:
        validators["Topic"].validate(topic.to_dict())

    assert notices[0].is_notice is True
    assert chronological[0].created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert buddies[0].to_dict()["description"] is None
    assert topics[0].to_dict() == {
        "seq": "5",
        "name": "Synthetic Topic",
        "group_name": "Synthetic Group",
    }
    assert all(post.thumbnail_url is None for post in directory_posts)
    assert all(
        post.media is None for post in [*chronological, *notices, *popular, *directory_posts]
    )
    assert (chronological[0].log_no, chronological[0].blog_id, chronological[0].blog_no) == (
        "10001",
        "synthetic_alice",
        "20001",
    )
    assert chronological[0].category_no == "7"
    assert (directory_posts[0].log_no, directory_posts[0].blog_id, directory_posts[0].blog_no) == (
        "10001",
        "synthetic_alice",
        "20001",
    )
    assert all(
        isinstance(value, str)
        for post in [*chronological, *notices, *popular, *directory_posts]
        for value in (post.log_no, post.blog_id, post.blog_no, post.category_no)
        if value is not None
    )


def test_phase3_popular_mobile_post_uses_its_card_identity() -> None:
    fixture = load_fixture("phase3.json")
    node = parse_post_list(fixture["popular_post_list"], kind="popular")[0]

    post = build_mobile_post(node, captured_at=_CAPTURED_AT, kind="popular", include_raw=True)

    assert post.blog_id == "synthetic_alice"
    assert post.log_no == "10003"
    assert post.blog_no is None
    assert post.url == "https://blog.naver.com/synthetic_alice/10003"
    assert post.raw == node
    assert post.to_dict()["media"] is None
    observed_node = {**node, "blogNo": 20001}
    observed_post = build_mobile_post(observed_node, captured_at=_CAPTURED_AT, kind="popular")
    assert observed_post.blog_no == "20001"


def test_phase3_mobile_post_rejects_variant_confusion_and_malformed_identities() -> None:
    fixture = load_fixture("phase3.json")
    chronological = fixture["post_list"]["result"]["items"][0]
    popular = fixture["popular_post_list"]["result"]["popularPostList"][0]
    malformed_chronological = deepcopy(chronological)
    del malformed_chronological["blogNo"]
    malformed_popular = deepcopy(popular)
    malformed_popular["blogId"] = ""
    missing_popular_log_no = deepcopy(popular)
    del missing_popular_log_no["logNo"]

    with pytest.raises(KeyError, match="blogId"):
        build_mobile_post(chronological, captured_at=_CAPTURED_AT, kind="popular")
    with pytest.raises(KeyError, match="domainIdOrBlogId"):
        build_mobile_post(popular, captured_at=_CAPTURED_AT, kind="chronological")
    with pytest.raises(KeyError, match="blogNo"):
        build_mobile_post(malformed_chronological, captured_at=_CAPTURED_AT, kind="chronological")
    with pytest.raises(KeyError, match="logNo"):
        build_mobile_post(missing_popular_log_no, captured_at=_CAPTURED_AT, kind="popular")
    with pytest.raises(ValueError, match="blogId"):
        build_mobile_post(malformed_popular, captured_at=_CAPTURED_AT, kind="popular")


def test_phase3_mobile_post_normalizes_measured_integer_editor_version() -> None:
    fixture = load_fixture("phase3.json")
    node = fixture["post_list"]["result"]["items"][0]

    post = build_mobile_post(node, captured_at=_CAPTURED_AT, kind="chronological")

    assert post.to_dict()["editor_version"] == "4"


@pytest.mark.parametrize("value", [True, 4.0, [], {}, -1, "4", "ONE"])
def test_phase3_mobile_post_rejects_invalid_editor_versions(value: object) -> None:
    fixture = load_fixture("phase3.json")
    node = deepcopy(fixture["post_list"]["result"]["items"][0])
    node["smartEditorVersion"] = value

    with pytest.raises((TypeError, ValueError), match="smartEditorVersion"):
        build_mobile_post(node, captured_at=_CAPTURED_AT, kind="chronological")


def test_phase4_build_comment_normalizes_fixture_tree_and_serializes_to_schema() -> None:
    page = parse_cbox_list(load_fixture("phase4.json")["cbox_list"])
    comments = [build_comment(card) for card in page.items]

    assert [
        (comment.comment_no, comment.parent_comment_no, comment.depth) for comment in comments
    ] == [
        ("90001", None, 0),
        ("90003", None, 0),
    ]
    reply = comments[0].replies[0]
    assert (reply.comment_no, reply.parent_comment_no, reply.is_reply, reply.depth) == (
        "90002",
        "90001",
        True,
        1,
    )
    assert comments[0].author_blog_id == "synthetic_alice"
    assert reply.author_blog_id == "synthetic_bob"
    assert comments[0].created_at == datetime(2026, 7, 25, 1, 0, tzinfo=UTC)
    assert comments[0].sticker_id == "synthetic-sticker-1"
    assert comments[0].image_urls == [
        "https://media.example.invalid/comments/synthetic-image-1.jpg"
    ]
    validator = jsonschema.Draft202012Validator(
        {"$ref": "#/$defs/Comment", "$defs": json_schema()["$defs"]}
    )
    for comment in comments:
        validator.validate(comment.to_dict())


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda card: card.__setitem__("parentCommentNo", "wrong"),
            "top-level comment identity",
        ),
        (
            lambda card: card["replyList"][0].__setitem__("replyLevel", 1),
            "reply comment identity",
        ),
        (
            lambda card: card.__setitem__("regTime", "2026-07-25T10:00:00Z"),
            "ISO-8601",
        ),
    ],
)
def test_phase4_build_comment_rejects_invalid_tree_and_timestamps(mutate, error: str) -> None:
    card = deepcopy(load_fixture("phase4.json")["cbox_list"]["result"]["commentList"][0])
    mutate(card)

    with pytest.raises((TypeError, ValueError), match=error):
        build_comment(card)


def test_phase4_build_comment_maps_only_explicit_deleted_and_secret_markers() -> None:
    card = deepcopy(load_fixture("phase4.json")["cbox_list"]["result"]["commentList"][0])
    card["deleted"] = True
    card["secret"] = True

    comment = build_comment(card)

    assert comment.is_deleted is True
    assert comment.is_secret is True
