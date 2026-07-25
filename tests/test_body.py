"""Synthetic contracts for the package's only HTML parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from agentic_blog.body import KST, parse_post_body
from agentic_blog.errors import BodyParseError

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_se_one_body_preserves_component_order_and_lazy_image() -> None:
    result = parse_post_body(_fixture("body_se_one.html"))

    assert result.markdown == (
        "첫 문단 \\[대괄호\\] \\> 기호\n\n둘째 문단\n\n"
        "![이미지 설명](https://example.invalid/lazy.jpg)\n\n"
        "> 인용 첫줄\n> 인용 둘째줄\n\n"
        "[외부 글](https://example.invalid/article)\n\n"
        "[서울 카페](https://map.example.invalid/place)\n\n---"
    )
    assert [item.to_dict() for item in result.media] == [
        {
            "kind": "photo",
            "url": "https://example.invalid/lazy.jpg",
            "caption": "이미지 설명",
            "width": 640,
            "height": 480,
        }
    ]


def test_parse_legacy_body_handles_paragraphs_breaks_and_images() -> None:
    result = parse_post_body(_fixture("body_legacy.html"))

    assert result.markdown == (
        "첫 문단\n줄바꿈\n\n![레거시 이미지](https://example.invalid/legacy.jpg)\n\n마지막 문단"
    )
    assert [item.url for item in result.media] == ["https://example.invalid/legacy.jpg"]


@pytest.mark.parametrize(
    "source",
    [
        "<div class='se-main-container'><div class='se-text'>not a component</div></div>",
        "<div id='viewTypeSelector' class='post_ct'></div>",
        "<div class='unrelated'>body</div>",
    ],
)
def test_parse_post_body_rejects_near_misses_and_empty_content(source: str) -> None:
    with pytest.raises(BodyParseError):
        parse_post_body(source)


def test_parse_post_body_does_not_duplicate_nested_component_content() -> None:
    source = """
    <div class='se-main-container'>
      <div class='se-component se-text'><div class='se-text-paragraph'>밖</div>
        <div class='se-component se-image'><img src='https://example.invalid/nested.jpg'></div>
      </div>
    </div>
    """
    result = parse_post_body(source)

    assert result.markdown == "밖"
    assert result.media == ()


def test_editor_comment_markers_never_reach_the_rendered_body() -> None:
    """SmartEditor ONE wraps text modules in literal `<!-- SE-TEXT { -->` HTML comments.

    lxml exposes a comment's body as its `.text`, so a text walk that descends into comment nodes
    emits editor scaffolding as if it were the author's writing. Reproduced on 12 of 30 live posts.
    """
    source = """
    <div class="se-main-container">
      <div class="se-component se-quotation">
        <blockquote class="se-quotation-container">
          <div class="se-module se-module-text se-quote"><!-- SE-TEXT -->
            <p class="se-text-paragraph">인용문</p>
          <!-- } SE-TEXT --></div>
        </blockquote>
      </div>
    </div>
    """

    result = parse_post_body(source)

    assert result.markdown == "> 인용문"
    assert "SE-TEXT" not in result.markdown


def test_post_body_publish_time_is_read_as_korean_wall_clock() -> None:
    """`.blog_date` renders KST with no offset; left naive it serializes nine hours early."""
    source = """
    <div>
      <span class="blog_date">2026. 7. 13. 15:38</span>
      <div class="se-main-container">
        <div class="se-component se-text">
          <p class="se-text-paragraph">본문</p>
        </div>
      </div>
    </div>
    """

    result = parse_post_body(source)

    assert result.created_at == datetime(2026, 7, 13, 15, 38, tzinfo=KST)
    assert result.created_at.utcoffset() is not None


def test_post_body_without_a_rendered_date_reports_no_publish_time() -> None:
    result = parse_post_body(_fixture("body_se_one.html"))

    assert result.created_at is None


@pytest.mark.parametrize("label", ["7시간 전", "방금 전", "3분 전", "어제", "오늘"])
def test_relatively_labelled_posts_report_no_publish_time(label: str) -> None:
    """Naver labels recent posts relatively; a rounded interval is not a timestamp."""
    source = f"""
    <div>
      <span class="blog_date">{label}</span>
      <div class="se-main-container">
        <div class="se-component se-text"><p class="se-text-paragraph">본문</p></div>
      </div>
    </div>
    """

    assert parse_post_body(source).created_at is None


def test_an_unrecognized_publish_date_is_still_treated_as_drift() -> None:
    source = """
    <div>
      <span class="blog_date">last Tuesday</span>
      <div class="se-main-container">
        <div class="se-component se-text"><p class="se-text-paragraph">본문</p></div>
      </div>
    </div>
    """

    with pytest.raises(BodyParseError):
        parse_post_body(source)
