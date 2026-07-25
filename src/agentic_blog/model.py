"""Stable output objects and serialization-driven JSON Schema."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from html import unescape
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints


def _iso_utc(value: datetime | None) -> str | None:
    """Serialize a datetime as an ISO-8601 UTC value with a ``Z`` suffix."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


MediaKind = Literal["photo", "video", "sticker", "unknown"]
PostVisibility = Literal["public", "buddy", "both_buddy", "private"]


@dataclass
class Media:
    """One attachment embedded in a post body."""

    kind: MediaKind = "unknown"
    url: str | None = None
    caption: str | None = None
    width: int | None = None
    height: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in get_args(MediaKind):
            raise ValueError(f"Unsupported media kind: {self.kind}")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "url": self.url,
            "caption": self.caption,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class Category:
    """One blog category."""

    category_no: str = ""
    parent_category_no: str | None = None
    name: str = ""
    post_count: int | None = None
    is_open: bool = False

    def __post_init__(self) -> None:
        self.category_no = str(self.category_no)
        if self.parent_category_no is not None:
            self.parent_category_no = str(self.parent_category_no)

    def to_dict(self) -> dict[str, object]:
        return {
            "category_no": str(self.category_no),
            "parent_category_no": (
                str(self.parent_category_no) if self.parent_category_no is not None else None
            ),
            "name": self.name,
            "post_count": self.post_count,
            "is_open": self.is_open,
        }


@dataclass
class Comment:
    """One comment, including its nested replies."""

    comment_no: str = ""
    parent_comment_no: str | None = None
    is_reply: bool = False
    depth: int = 0
    text: str | None = None
    author_name: str | None = None
    author_blog_id: str | None = None
    author_profile_image_url: str | None = None
    created_at: datetime | None = None
    like_count: int | None = None
    dislike_count: int | None = None
    is_best: bool = False
    is_deleted: bool = False
    is_secret: bool = False
    sticker_id: str | None = None
    image_urls: list[str] = field(default_factory=list)
    replies: list[Comment] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.comment_no = str(self.comment_no)
        if self.parent_comment_no is not None:
            self.parent_comment_no = str(self.parent_comment_no)
        if self.author_blog_id is not None:
            self.author_blog_id = str(self.author_blog_id)
        if self.sticker_id is not None:
            self.sticker_id = str(self.sticker_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "comment_no": str(self.comment_no),
            "parent_comment_no": (
                str(self.parent_comment_no) if self.parent_comment_no is not None else None
            ),
            "is_reply": self.is_reply,
            "depth": self.depth,
            "text": self.text,
            "author_name": self.author_name,
            "author_blog_id": str(self.author_blog_id) if self.author_blog_id is not None else None,
            "author_profile_image_url": self.author_profile_image_url,
            "created_at": _iso_utc(self.created_at),
            "like_count": self.like_count,
            "dislike_count": self.dislike_count,
            "is_best": self.is_best,
            "is_deleted": self.is_deleted,
            "is_secret": self.is_secret,
            "sticker_id": str(self.sticker_id) if self.sticker_id is not None else None,
            "image_urls": self.image_urls,
            "replies": [reply.to_dict() for reply in self.replies],
        }


@dataclass
class Post:
    """A Naver blog post."""

    log_no: str = ""
    blog_id: str = ""
    blog_no: str | None = None
    url: str = ""
    title: str = ""
    brief: str | None = None
    body: str | None = None
    created_at: datetime | None = None
    blog_name: str | None = None
    nickname: str | None = None
    category_no: str | None = None
    category_name: str | None = None
    comment_count: int | None = None
    like_count: int | None = None
    share_count: int | None = None
    thumbnail_url: str | None = None
    media: list[Media] | None = None
    editor_version: str | None = None
    visibility: PostVisibility | None = None
    is_notice: bool = False
    comments: list[Comment] | None = None
    captured_at: datetime | None = None
    raw: dict[str, Any] | None = field(default=None, metadata={"omit_none": True})

    def __post_init__(self) -> None:
        self.log_no = str(self.log_no)
        self.blog_id = str(self.blog_id)
        if self.blog_no is not None:
            self.blog_no = str(self.blog_no)
        if self.category_no is not None:
            self.category_no = str(self.category_no)
        if self.raw is not None and not isinstance(self.raw, dict):
            raise TypeError("raw must be an object")
        if self.visibility is not None and self.visibility not in get_args(PostVisibility):
            raise ValueError(f"Unsupported post visibility: {self.visibility}")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "log_no": str(self.log_no),
            "blog_id": str(self.blog_id),
            "blog_no": str(self.blog_no) if self.blog_no is not None else None,
            "url": self.url,
            "title": self.title,
            "brief": self.brief,
            "body": self.body,
            "created_at": _iso_utc(self.created_at),
            "blog_name": self.blog_name,
            "nickname": self.nickname,
            "category_no": str(self.category_no) if self.category_no is not None else None,
            "category_name": self.category_name,
            "comment_count": self.comment_count,
            "like_count": self.like_count,
            "share_count": self.share_count,
            "thumbnail_url": self.thumbnail_url,
            "media": [item.to_dict() for item in self.media] if self.media is not None else None,
            "editor_version": self.editor_version,
            "visibility": self.visibility,
            "is_notice": self.is_notice,
            "comments": [comment.to_dict() for comment in self.comments]
            if self.comments is not None
            else None,
            "captured_at": _iso_utc(self.captured_at),
        }
        if self.raw is not None:
            result["raw"] = self.raw
        return result


@dataclass
class Blog:
    """A Naver blog profile."""

    blog_id: str = ""
    blog_no: str = ""
    blog_name: str | None = None
    nickname: str | None = None
    description: str | None = None
    profile_image_url: str | None = None
    url: str | None = None
    buddy_count: int | None = None
    post_count: int | None = None
    categories: list[Category] | None = None
    captured_at: datetime | None = None
    raw: dict[str, Any] | None = field(default=None, metadata={"omit_none": True})

    def __post_init__(self) -> None:
        self.blog_id = str(self.blog_id)
        self.blog_no = str(self.blog_no)
        if self.raw is not None and not isinstance(self.raw, dict):
            raise TypeError("raw must be an object")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "blog_id": str(self.blog_id),
            "blog_no": str(self.blog_no),
            "blog_name": self.blog_name,
            "nickname": self.nickname,
            "description": self.description,
            "profile_image_url": self.profile_image_url,
            "url": self.url,
            "buddy_count": self.buddy_count,
            "post_count": self.post_count,
            "categories": [category.to_dict() for category in self.categories]
            if self.categories is not None
            else None,
            "captured_at": _iso_utc(self.captured_at),
        }
        if self.raw is not None:
            result["raw"] = self.raw
        return result


_STRONG_TAG = re.compile(
    r"""<strong\b(?P<attributes>(?:[^>"']+|"[^"]*"|'[^']*')*)>(?P<content>.*?)</strong\s*>""",
    re.IGNORECASE | re.DOTALL,
)
_INTEGER_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_COUNT_TEXT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SEARCH_MISSING = object()


def _search_nullable_string(value: object | None) -> str | None:
    """Return a nullable search display-text or URL value."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("search display text and URLs must be strings or null")
    return value


def _search_text(value: object | None) -> str | None:
    """Remove search highlight markup and decode display-text entities."""
    value = _search_nullable_string(value)
    if value is None:
        return None

    def remove_highlight(match: re.Match[str]) -> str:
        classes = _strong_class(match["attributes"])
        return (
            match["content"]
            if classes is not None and "search_keyword" in classes.split()
            else match[0]
        )

    return unescape(_STRONG_TAG.sub(remove_highlight, value))


def _strong_class(attributes: str) -> str | None:
    """Return the real class attribute from a quote-aware strong start tag."""
    index = 0
    while index < len(attributes):
        while index < len(attributes) and attributes[index].isspace():
            index += 1
        name_start = index
        while (
            index < len(attributes)
            and not attributes[index].isspace()
            and attributes[index] not in "=/"
        ):
            index += 1
        name = attributes[name_start:index]
        while index < len(attributes) and attributes[index].isspace():
            index += 1
        if not name:
            index += 1
            continue
        if index == len(attributes) or attributes[index] != "=":
            continue
        index += 1
        while index < len(attributes) and attributes[index].isspace():
            index += 1
        if index < len(attributes) and attributes[index] in "'\"":
            quote = attributes[index]
            index += 1
            value_start = index
            index = attributes.find(quote, index)
            if index == -1:
                return None
            value = attributes[value_start:index]
            index += 1
        else:
            value_start = index
            while index < len(attributes) and not attributes[index].isspace():
                index += 1
            value = attributes[value_start:index]
        if name.lower() == "class":
            return value
    return None


def _search_id(value: object = _SEARCH_MISSING) -> str:
    """Return a search identifier without risking numeric precision loss."""
    if value is _SEARCH_MISSING:
        return ""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError("search identifier must be a string or integer")
    return str(value)


def _search_required_id(value: object = _SEARCH_MISSING, *, name: str) -> str:
    """Return a required search identity without allowing empty values."""
    if value is _SEARCH_MISSING:
        raise KeyError(f"missing required search {name}")
    identifier = _search_id(value)
    if not identifier:
        raise ValueError(f"search {name} must not be empty")
    return identifier


def _search_count(value: object | None) -> int | None:
    """Return a non-negative search count from its measured scalar shapes."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("search count must be an integer or integer string")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("search count must not be negative")
        return value
    if isinstance(value, str) and _COUNT_TEXT.fullmatch(value):
        return int(value)
    raise TypeError("search count must be an integer or integer string")


def _search_created_at(value: object | None) -> datetime | None:
    """Convert the search API's epoch-millisecond ``addDate`` to UTC."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("addDate must be an integer or integer string")
    if isinstance(value, int):
        milliseconds = value
    elif isinstance(value, str) and _INTEGER_TEXT.fullmatch(value):
        milliseconds = int(value)
    else:
        raise TypeError("addDate must be an integer or integer string")
    try:
        return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError("addDate is outside the supported timestamp range") from error


def _search_flag(node: dict[str, Any], name: str) -> bool:
    value = node.get(name, False)
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _search_visibility(node: dict[str, Any]) -> PostVisibility:
    not_open = _search_flag(node, "notOpen")
    both_buddy_open = _search_flag(node, "bothBuddyOpen")
    buddy_open = _search_flag(node, "buddyOpen")
    if not_open:
        return "private"
    if both_buddy_open:
        return "both_buddy"
    if buddy_open:
        return "buddy"
    return "public"


def build_search_post(
    node: dict[str, Any], *, captured_at: datetime, include_raw: bool = False
) -> Post:
    """Build a listing-only ``Post`` from one section-search post node."""
    blog_id = _search_required_id(node.get("domainIdOrBlogId", _SEARCH_MISSING), name="blog id")
    log_no = _search_required_id(node.get("logNo", _SEARCH_MISSING), name="log number")
    return Post(
        log_no=log_no,
        blog_id=blog_id,
        blog_no=_search_id(node["blogNo"]) if node.get("blogNo") is not None else None,
        url=f"https://blog.naver.com/{blog_id}/{log_no}",
        title=_search_text(node.get("title")) or "",
        brief=_search_text(node.get("contents")),
        created_at=_search_created_at(node.get("addDate")),
        blog_name=_search_text(node.get("blogName")),
        nickname=_search_text(node.get("nickName")),
        category_no=(
            _search_id(node["categoryNo"]) if node.get("categoryNo") is not None else None
        ),
        category_name=_search_text(node.get("categoryName")),
        comment_count=_search_count(node.get("commentCnt")),
        like_count=_search_count(node.get("sympathyCnt")),
        share_count=_search_count(node.get("shareCnt")),
        thumbnail_url=_search_nullable_string(node.get("thumbnailUrl")),
        editor_version=(
            _search_id(node["smartEditorVersion"])
            if node.get("smartEditorVersion") is not None
            else None
        ),
        visibility=_search_visibility(node),
        is_notice=_search_flag(node, "isNotice"),
        captured_at=captured_at,
        raw=node if include_raw else None,
    )


def build_search_blog(
    node: dict[str, Any], *, captured_at: datetime, include_raw: bool = False
) -> Blog:
    """Build a ``Blog`` from one section-search blog node."""
    blog_id = _search_required_id(node.get("domainIdOrBlogId", _SEARCH_MISSING), name="blog id")
    return Blog(
        blog_id=blog_id,
        blog_no=_search_id(node.get("blogNo", _SEARCH_MISSING)),
        blog_name=_search_text(node.get("blogName")),
        nickname=_search_text(node.get("nickName")),
        description=_search_text(node.get("blogDesc")),
        profile_image_url=_search_nullable_string(node.get("profileImgUrl")),
        url=f"https://blog.naver.com/{blog_id}",
        captured_at=captured_at,
        raw=node if include_raw else None,
    )


def build_search_id(
    node: dict[str, Any], *, captured_at: datetime, include_raw: bool = False
) -> Blog:
    """Build a ``Blog`` from one section-search nickname or ID node."""
    return build_search_blog(node, captured_at=captured_at, include_raw=include_raw)


@dataclass
class Topic:
    """One Naver directory topic."""

    seq: str = ""
    name: str = ""
    group_name: str | None = None

    def __post_init__(self) -> None:
        self.seq = str(self.seq)

    def to_dict(self) -> dict[str, object]:
        return {"seq": str(self.seq), "name": self.name, "group_name": self.group_name}


FIELD_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "Post": {
        "log_no": "Post identifier, serialized as a string.",
        "blog_id": "Blog identifier.",
        "blog_no": (
            "Numeric blog identifier, serialized as a string when supplied by the source, or null."
        ),
        "url": "Canonical post URL.",
        "title": "Post title.",
        "brief": "Listing summary supplied by Naver.",
        "body": "Post body rendered as Markdown; unavailable in listings.",
        "created_at": "Post creation time as ISO-8601 UTC, or null.",
        "blog_name": "Blog display name.",
        "nickname": "Blog author nickname.",
        "category_no": "Category identifier, serialized as a string, or null.",
        "category_name": "Category display name.",
        "comment_count": "Number of comments.",
        "like_count": "Number of Naver sympathy reactions.",
        "share_count": "Number of shares.",
        "thumbnail_url": "Post thumbnail URL.",
        "media": (
            "Media attachments extracted from the post body, or null when body extraction "
            "was not performed."
        ),
        "editor_version": "Naver editor version.",
        "visibility": "Post visibility: public, buddy, both_buddy, or private.",
        "is_notice": "Whether this is a pinned notice post.",
        "comments": "Comment thread; unavailable in listings or when comments are skipped.",
        "captured_at": "Collection time as ISO-8601 UTC, or null.",
        "raw": "Optional raw upstream post object, emitted only when requested.",
    },
    "Blog": {
        "blog_id": "Blog identifier.",
        "blog_no": "Numeric blog identifier, serialized as a string.",
        "blog_name": "Blog display name.",
        "nickname": "Blog owner nickname.",
        "description": "Blog description.",
        "profile_image_url": "Blog profile image URL.",
        "url": "Canonical blog URL.",
        "buddy_count": "Number of public neighbours.",
        "post_count": "Number of posts.",
        "categories": "Blog category tree; unavailable outside a full blog read.",
        "captured_at": "Collection time as ISO-8601 UTC, or null.",
        "raw": "Optional raw upstream blog object, emitted only when requested.",
    },
    "Topic": {
        "seq": "Directory topic identifier, serialized as a string.",
        "name": "Topic name.",
        "group_name": "Containing topic group name.",
    },
    "Comment": {
        "comment_no": "Comment identifier, serialized as a string.",
        "parent_comment_no": "Parent comment identifier, serialized as a string, or null.",
        "is_reply": "Whether this comment replies to another comment.",
        "depth": "Reply nesting depth.",
        "text": "Comment text.",
        "author_name": "Comment author display name.",
        "author_blog_id": "Comment author blog identifier.",
        "author_profile_image_url": "Comment author profile image URL.",
        "created_at": "Comment creation time as ISO-8601 UTC, or null.",
        "like_count": "Number of likes.",
        "dislike_count": "Number of dislikes.",
        "is_best": "Whether Naver marked the comment as best.",
        "is_deleted": "Whether the comment was deleted.",
        "is_secret": "Whether the comment is secret.",
        "sticker_id": "Comment sticker identifier.",
        "image_urls": "Image URLs attached to the comment.",
        "replies": "Nested replies to this comment.",
    },
    "Media": {
        "kind": "Attachment kind: photo, video, sticker, or unknown.",
        "url": "Attachment URL.",
        "caption": "Attachment caption.",
        "width": "Attachment width in pixels.",
        "height": "Attachment height in pixels.",
    },
    "Category": {
        "category_no": "Category identifier, serialized as a string.",
        "parent_category_no": "Parent category identifier, serialized as a string, or null.",
        "name": "Category name.",
        "post_count": "Number of posts in the category.",
        "is_open": "Whether the category is publicly visible.",
    },
}

_MODEL_TYPES = (Post, Blog, Topic, Comment, Media, Category)


def _schema_sample(model: type[object]) -> dict[str, object]:
    """Serialize a populated synthetic instance for schema field discovery."""
    if model is Post:
        return Post(
            log_no="post-id",
            blog_id="blog-id",
            blog_no="blog-no",
            url="https://example.test/posts/post-id",
            title="Post title",
            brief="Post summary",
            body="Post body",
            created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            blog_name="Blog name",
            nickname="Author",
            category_no="category-id",
            category_name="Category name",
            comment_count=1,
            like_count=2,
            share_count=3,
            thumbnail_url="https://example.test/thumbnail.jpg",
            media=[
                Media(
                    kind="photo",
                    url="https://example.test/media.jpg",
                    caption="Caption",
                    width=1,
                    height=2,
                )
            ],
            editor_version="3",
            visibility="public",
            is_notice=True,
            comments=[
                Comment(
                    comment_no="comment-id",
                    parent_comment_no="parent-comment-id",
                    is_reply=True,
                    depth=1,
                    text="Comment text",
                    author_name="Commenter",
                    author_blog_id="commenter-id",
                    author_profile_image_url="https://example.test/profile.jpg",
                    created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
                    like_count=1,
                    dislike_count=2,
                    is_best=True,
                    is_deleted=True,
                    is_secret=True,
                    sticker_id="sticker-id",
                    image_urls=["https://example.test/comment.jpg"],
                    replies=[],
                )
            ],
            captured_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            raw={"source": "synthetic"},
        ).to_dict()
    if model is Blog:
        return Blog(
            blog_id="blog-id",
            blog_no="blog-no",
            blog_name="Blog name",
            nickname="Author",
            description="Blog description",
            profile_image_url="https://example.test/profile.jpg",
            url="https://example.test/blogs/blog-id",
            buddy_count=1,
            post_count=2,
            categories=[
                Category(
                    category_no="category-id",
                    parent_category_no="parent-category-id",
                    name="Category name",
                    post_count=3,
                    is_open=True,
                )
            ],
            captured_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            raw={"source": "synthetic"},
        ).to_dict()
    if model is Topic:
        return Topic(seq="topic-id", name="Topic name", group_name="Topic group").to_dict()
    if model is Comment:
        return Comment(
            comment_no="comment-id",
            parent_comment_no="parent-comment-id",
            is_reply=True,
            depth=1,
            text="Comment text",
            author_name="Commenter",
            author_blog_id="commenter-id",
            author_profile_image_url="https://example.test/profile.jpg",
            created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            like_count=1,
            dislike_count=2,
            is_best=True,
            is_deleted=True,
            is_secret=True,
            sticker_id="sticker-id",
            image_urls=["https://example.test/comment.jpg"],
            replies=[],
        ).to_dict()
    if model is Media:
        return Media(
            kind="photo",
            url="https://example.test/media.jpg",
            caption="Caption",
            width=1,
            height=2,
        ).to_dict()
    if model is Category:
        return Category(
            category_no="category-id",
            parent_category_no="parent-category-id",
            name="Category name",
            post_count=1,
            is_open=True,
        ).to_dict()
    raise TypeError(f"Unsupported schema model: {model!r}")


def _type_name(annotation: object) -> str:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return " | ".join(_type_name(item) for item in get_args(annotation))
    if origin is Literal:
        return "enum"
    if origin is list:
        return f"array<{_type_name(get_args(annotation)[0])}>"
    if origin is dict:
        return "object"
    if annotation is datetime:
        return "string"
    if annotation is Any:
        return "object"
    return getattr(annotation, "__name__", str(annotation)).lower()


def _wire_annotation(annotation: object, metadata: Any) -> object:
    if metadata.get("omit_none"):
        return next(item for item in get_args(annotation) if item is not type(None))
    return annotation


def schema_fields(model: type[object] = Post) -> list[dict[str, object]]:
    """Return fields in the exact order emitted by a model's ``to_dict()`` method."""
    sample = _schema_sample(model)
    descriptions = FIELD_DESCRIPTIONS[model.__name__]
    model_fields = {model_field.name: model_field for model_field in fields(model)}
    hints = get_type_hints(model)
    serialized_names = list(sample)
    return [
        {
            "name": name,
            "type": _type_name(_wire_annotation(hints[name], model_fields[name].metadata)),
            "description": descriptions[name],
            "always_present": not model_fields[name].metadata.get("omit_none", False),
        }
        for name in serialized_names
    ]


def _annotation_schema(annotation: object) -> dict[str, object]:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        options = [_annotation_schema(item) for item in get_args(annotation)]
        return {"anyOf": options}
    if origin is Literal:
        return {"type": "string", "enum": list(get_args(annotation))}
    if origin is list:
        return {"type": "array", "items": _annotation_schema(get_args(annotation)[0])}
    if origin is dict:
        return {"type": "object"}
    if annotation is str or annotation is datetime:
        schema: dict[str, object] = {"type": "string"}
        if annotation is datetime:
            schema["format"] = "date-time"
            schema["pattern"] = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
        return schema
    if annotation is int:
        return {"type": "integer"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is type(None):
        return {"type": "null"}
    if annotation is Any:
        return {"type": "object"}
    if annotation in _MODEL_TYPES:
        return {"$ref": f"#/$defs/{annotation.__name__}"}
    raise TypeError(f"Unsupported model annotation: {annotation!r}")


def _object_schema(model: type[object]) -> dict[str, object]:
    field_specs = schema_fields(model)
    hints = get_type_hints(model)
    model_fields = {model_field.name: model_field for model_field in fields(model)}
    return {
        "type": "object",
        "description": f"One {model.__name__} object.",
        "properties": {
            field["name"]: {
                **_annotation_schema(
                    _wire_annotation(hints[field["name"]], model_fields[field["name"]].metadata)
                ),
                "description": field["description"],
            }
            for field in field_specs
        },
        "required": [field["name"] for field in field_specs if field["always_present"]],
        "additionalProperties": False,
    }


def json_schema() -> dict[str, object]:
    """Return the generated read-command JSON Schema using draft 2020-12."""
    definitions = {model.__name__: _object_schema(model) for model in _MODEL_TYPES}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Read command output",
        "anyOf": [
            {
                "type": "array",
                "items": {"$ref": f"#/$defs/{model.__name__}"},
            }
            for model in (Post, Blog, Topic)
        ],
        "$defs": definitions,
    }


def _phase3_required_id(node: dict[str, Any], name: str) -> str:
    return _search_required_id(node.get(name, _SEARCH_MISSING), name=name)


def _phase3_editor_version(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("smartEditorVersion must be a non-negative integer or null")
    if value < 0:
        raise ValueError("smartEditorVersion must be a non-negative integer or null")
    return str(value)


def _phase3_string(node: dict[str, Any], name: str, *, nullable: bool = False) -> str | None:
    value = node.get(name)
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string" + (" or null" if nullable else ""))
    return value


def build_category(node: dict[str, Any]) -> Category:
    """Build a Category from one non-separator mobile category node."""
    category_no = _phase3_required_id(node, "categoryNo")
    parent = node.get("parentCategoryNo")
    if parent is not None:
        parent = _search_id(parent)
    post_count = _search_count(node.get("postCnt"))
    is_open = node.get("openYN")
    if not isinstance(is_open, bool):
        raise TypeError("openYN must be a boolean")
    return Category(
        category_no=category_no,
        parent_category_no=parent,
        name=_phase3_string(node, "categoryName") or "",
        post_count=post_count,
        is_open=is_open,
    )


def build_mobile_post(
    node: dict[str, Any],
    *,
    captured_at: datetime,
    kind: Literal["chronological", "notice", "popular"],
    include_raw: bool = False,
    is_notice: bool = False,
) -> Post:
    """Build a Post from one explicitly identified mobile list-card variant."""
    if kind in {"chronological", "notice"}:
        blog_id = _phase3_required_id(node, "domainIdOrBlogId")
        blog_no = _phase3_required_id(node, "blogNo")
    elif kind == "popular":
        blog_id = _phase3_required_id(node, "blogId")
        blog_no = (
            None
            if node.get("blogNo", _SEARCH_MISSING) is _SEARCH_MISSING
            else _phase3_required_id(node, "blogNo")
        )
    else:
        raise ValueError(f"unsupported mobile post kind: {kind}")
    log_no = _phase3_required_id(node, "logNo")
    return Post(
        log_no=log_no,
        blog_id=blog_id,
        blog_no=blog_no,
        url=f"https://blog.naver.com/{blog_id}/{log_no}",
        title=_search_text(_phase3_string(node, "titleWithInspectMessage")) or "",
        brief=_search_text(_phase3_string(node, "briefContents", nullable=True)),
        created_at=_search_created_at(node.get("addDate")),
        category_no=(
            _search_id(node["categoryNo"]) if node.get("categoryNo") is not None else None
        ),
        category_name=_search_text(_phase3_string(node, "categoryName", nullable=True)),
        comment_count=_search_count(node.get("commentCnt")),
        like_count=_search_count(node.get("sympathyCnt")),
        share_count=_search_count(node.get("shareCnt")),
        thumbnail_url=_phase3_string(node, "thumbnailUrl", nullable=True),
        editor_version=_phase3_editor_version(node.get("smartEditorVersion")),
        visibility=_search_visibility(node),
        is_notice=is_notice,
        captured_at=captured_at,
        raw=node if include_raw else None,
    )


def build_buddy_blog(
    node: dict[str, Any], *, captured_at: datetime, include_raw: bool = False
) -> Blog:
    """Build a Blog from a public-buddy card, dropping its display-only update label."""
    blog_id = _phase3_required_id(node, "blogId")
    return Blog(
        blog_id=blog_id,
        blog_no=_phase3_required_id(node, "blogNo"),
        blog_name=_phase3_string(node, "blogName"),
        nickname=_phase3_string(node, "nickName"),
        profile_image_url=_phase3_string(node, "blogProfileImage"),
        url=_phase3_string(node, "linkUrl"),
        captured_at=captured_at,
        raw=node if include_raw else None,
    )


def build_topic(node: dict[str, Any]) -> Topic:
    """Build a Topic from a directory-list entry enriched with its group name."""
    return Topic(
        seq=_phase3_required_id(node, "seq"),
        name=_phase3_string(node, "name") or "",
        group_name=_phase3_string(node, "groupName"),
    )


def build_directory_post(
    node: dict[str, Any], *, captured_at: datetime, include_raw: bool = False
) -> Post:
    """Build a Post from a DirectoryPostList or DirectoryTopPostList card."""
    blog_id = _phase3_required_id(node, "domainIdOrBlogId")
    log_no = _phase3_required_id(node, "logNo")
    return Post(
        log_no=log_no,
        blog_id=blog_id,
        blog_no=_phase3_required_id(node, "blogNo"),
        url=_phase3_string(node, "postUrl") or "",
        title=_search_text(_phase3_string(node, "title")) or "",
        brief=_search_text(_phase3_string(node, "briefContents")) or "",
        nickname=_phase3_string(node, "nickname"),
        captured_at=captured_at,
        raw=node if include_raw else None,
    )


_COMMENT_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+0900\Z")


def _comment_string(node: dict[str, Any], name: str, *, nullable: bool = False) -> str | None:
    value = node.get(name)
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string" + (" or null" if nullable else ""))
    return value


def _comment_non_negative_integer(node: dict[str, Any], name: str) -> int:
    value = node.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{name} must be a non-negative integer")
    return value


def _comment_timestamp(node: dict[str, Any], name: str) -> datetime:
    value = _comment_string(node, name)
    assert value is not None
    if not _COMMENT_TIMESTAMP.fullmatch(value):
        raise ValueError(f"{name} must be an ISO-8601 +0900 timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z").astimezone(UTC)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 +0900 timestamp") from error


def build_comment(node: dict[str, Any]) -> Comment:
    """Build a normalized recursive Comment tree from one validated CBOX card."""
    seen_comment_nos: set[str] = set()

    def build(
        card: object,
        *,
        parent_comment_no: str | None,
        parent_reply_level: int | None,
    ) -> Comment:
        if not isinstance(card, dict):
            raise TypeError("comment card must be an object")
        comment_no = _comment_string(card, "commentNo")
        assert comment_no is not None
        if not comment_no:
            raise ValueError("commentNo must not be empty")
        if comment_no in seen_comment_nos:
            raise ValueError("commentNo values must be unique")
        seen_comment_nos.add(comment_no)
        source_parent = _comment_string(card, "parentCommentNo")
        assert source_parent is not None
        reply_level = _comment_non_negative_integer(card, "replyLevel")
        if reply_level < 1:
            raise ValueError("replyLevel must be positive")
        if parent_comment_no is None:
            if source_parent != comment_no or reply_level != 1:
                raise ValueError("top-level comment identity is inconsistent")
            normalized_parent = None
            is_reply = False
            depth = 0
        else:
            if source_parent != parent_comment_no or reply_level != parent_reply_level + 1:
                raise ValueError("reply comment identity is inconsistent")
            normalized_parent = parent_comment_no
            is_reply = True
            depth = reply_level - 1

        reply_list = card.get("replyList")
        if not isinstance(reply_list, list):
            raise TypeError("replyList must be a list")
        if _comment_non_negative_integer(card, "replyCount") != len(reply_list):
            raise ValueError("replyCount must match replyList")
        best = card.get("best")
        deleted = card.get("deleted")
        secret = card.get("secret")
        if not all(isinstance(value, bool) for value in (best, deleted, secret)):
            raise TypeError("best, deleted, and secret must be booleans")
        images = card.get("imageList") or []
        if not isinstance(images, list):
            raise TypeError("imageList must be a list or null")
        image_urls: list[str] = []
        for image in images:
            if not isinstance(image, dict):
                raise TypeError("imageList entries must be objects")
            image_url = _comment_string(image, "imageUrl")
            assert image_url is not None
            _comment_non_negative_integer(image, "width")
            _comment_non_negative_integer(image, "height")
            image_urls.append(image_url)

        return Comment(
            comment_no=comment_no,
            parent_comment_no=normalized_parent,
            is_reply=is_reply,
            depth=depth,
            text=_comment_string(card, "contents"),
            author_name=_comment_string(card, "userName"),
            author_blog_id=_comment_string(card, "profileUserId"),
            author_profile_image_url=_comment_string(card, "userProfileImage"),
            created_at=_comment_timestamp(card, "regTime"),
            like_count=_comment_non_negative_integer(card, "sympathyCount"),
            dislike_count=_comment_non_negative_integer(card, "antipathyCount"),
            is_best=best,
            is_deleted=deleted,
            is_secret=secret,
            sticker_id=_comment_string(card, "stickerId", nullable=True) or None,
            image_urls=image_urls,
            replies=[
                build(
                    reply,
                    parent_comment_no=comment_no,
                    parent_reply_level=reply_level,
                )
                for reply in reply_list
            ],
        )

    return build(node, parent_comment_no=None, parent_reply_level=None)
