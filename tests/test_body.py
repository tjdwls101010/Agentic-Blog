"""Synthetic contracts for the package's only HTML parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from agentic_blog.body import parse_post_body, parse_post_search
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


def test_parse_post_search_extracts_only_anchored_cards() -> None:
    source = """
    <div id='postSearchList'><ul>
      <li>
        <a href='https://blog.naver.com/PostView.naver?blogId=synthetic_alice&amp;logNo=17'>링크</a>
        <strong class='title'>첫 <em>제목</em></strong>
        <p class='brief'>짧은 소개</p><span class='date'>2026. 7. 25.</span>
      </li>
      <li>
        <a href='/PostView.naver?blogId=synthetic_alice&amp;logNo=18'>링크</a>
        <strong class='title'>둘째 제목</strong><span class='date'>2026. 7. 24.</span>
      </li>
    </ul></div>
    """

    assert parse_post_search(source) == (
        parse_post_search(source)[0].__class__(
            blog_id="synthetic_alice",
            log_no="17",
            url="https://blog.naver.com/PostView.naver?blogId=synthetic_alice&logNo=17",
            title="첫 제목",
            brief="짧은 소개",
            created_at=datetime(2026, 7, 25),
        ),
        parse_post_search(source)[1].__class__(
            blog_id="synthetic_alice",
            log_no="18",
            url="/PostView.naver?blogId=synthetic_alice&logNo=18",
            title="둘째 제목",
            brief=None,
            created_at=datetime(2026, 7, 24),
        ),
    )


def test_parse_post_search_extracts_measured_legacy_table_variant() -> None:
    source = """
    <div id='post-area'>
      <table><tr><td><table><tr><td>
        <a class='s_link'
           href='https://blog.naver.com/synthetic_alice?Redirect=Log&amp;logNo=19'>
          표 기반 제목
        </a>
      </td><td class='eng'>2026/07/25 12:34</td></tr>
      <tr><td>표 기반 소개</td></tr></table></td></tr></table>
    </div>
    """

    (card,) = parse_post_search(source)

    assert (card.blog_id, card.log_no) == ("synthetic_alice", "19")
    assert card.title == "표 기반 제목"
    assert card.brief == "표 기반 소개"
    assert card.created_at == datetime(2026, 7, 25, 12, 34)


def test_parse_post_search_allows_only_explicit_empty_marker() -> None:
    assert (
        parse_post_search(
            "<div id='postSearchList'><p class='no_result'>검색결과가 없습니다</p></div>"
        )
        == ()
    )
    assert (
        parse_post_search("<div id='post-area'><strong>검색결과가 없습니다.</strong></div>") == ()
    )
    with pytest.raises(BodyParseError):
        parse_post_search("<div id='postSearchList'><ul></ul></div>")
    with pytest.raises(BodyParseError):
        parse_post_search("<div id='postSearchList'><ul><li>not linked</li></ul></div>")
