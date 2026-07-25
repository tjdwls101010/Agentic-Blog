"""Strict lxml extractors for Naver Blog HTML responses."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from lxml import etree
from lxml import html as lxml_html

from .errors import BodyParseError
from .model import Media

__all__ = ["BodyResult", "PostSearchCard", "parse_post_body", "parse_post_search"]


@dataclass(frozen=True)
class BodyResult:
    """Rendered post body, its embedded media in document order, and its publish time."""

    markdown: str
    media: tuple[Media, ...]
    created_at: datetime | None = None


@dataclass(frozen=True)
class PostSearchCard:
    """One anchored PostSearchList.naver result before model normalization."""

    blog_id: str
    log_no: str
    url: str
    title: str
    brief: str | None
    created_at: datetime | None


_CLASS = "concat(' ', normalize-space(@class), ' ')"
_SPACE = re.compile(r"[\t \r\f\v]+")
_DATE = re.compile(r"^(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\.?$")
_DATETIME = re.compile(
    r"^(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\.?\s+(\d{1,2}):(\d{2})$"
)

# Naver renders every HTML timestamp as Korean wall-clock with no offset attached. Left naive,
# these are serialized as if they were UTC (see model._iso_utc) and land nine hours early.
KST = timezone(timedelta(hours=9))

# Recent posts are labelled relatively instead of with a date: "방금 전", "7시간 전", "어제".
_RELATIVE_DATE = re.compile(r"(?:전|어제|오늘)$")


def _class(name: str) -> str:
    return f"contains({_CLASS}, ' {name} ')"


def _drift(expected: str) -> BodyParseError:
    return BodyParseError(f"HTML template drift: expected {expected}")


def _document(source: str) -> etree._Element:
    if not isinstance(source, str):
        raise BodyParseError("HTML response must be text")
    try:
        return lxml_html.fromstring(source)
    except (etree.ParserError, ValueError) as error:
        raise BodyParseError("HTML response could not be parsed") from error


def _has_class(node: etree._Element, name: str) -> bool:
    return name in (node.get("class") or "").split()


def _node_text(node: etree._Element) -> str:
    """Return visible-ish text while retaining line breaks represented by ``br``."""
    parts: list[str] = []

    def walk(current: etree._Element) -> None:
        if current.text:
            parts.append(current.text)
        for child in current:
            if child.tag == "br":
                parts.append("\n")
            elif isinstance(child.tag, str):
                walk(child)
            # Comments and processing instructions render nothing. SmartEditor ONE wraps its text
            # modules in literal `<!-- SE-TEXT { -->` markers, and lxml exposes a comment's body as
            # `.text`, so walking into them leaks editor scaffolding into the rendered output.
            if child.tail:
                parts.append(child.tail)

    walk(node)
    lines = [_SPACE.sub(" ", line).strip() for line in "".join(parts).splitlines()]
    return "\n".join(line for line in lines if line)


def _markdown_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace(">", "\\>")


def _first_text(node: etree._Element, class_name: str) -> str | None:
    found = node.xpath(f".//*[{_class(class_name)}]")
    for item in found:
        value = _node_text(item)
        if value:
            return value
    return None


def _integer_attribute(node: etree._Element, name: str) -> int | None:
    value = node.get(name)
    if value is None or not value.isdecimal():
        return None
    return int(value)


def _image_blocks(node: etree._Element, media: list[Media]) -> list[str]:
    blocks: list[str] = []
    for image in node.xpath("self::img | .//img"):
        url = image.get("data-lazy-src") or image.get("src")
        if not url:
            continue
        caption = _first_text(node, "se-caption") or image.get("alt") or None
        media.append(
            Media(
                kind="photo",
                url=url,
                caption=caption,
                width=_integer_attribute(image, "width"),
                height=_integer_attribute(image, "height"),
            )
        )
        alt = _markdown_text(caption or "image")
        blocks.append(f"![{alt}]({url})")
    return blocks


def _top_level_components(container: etree._Element) -> list[etree._Element]:
    components = container.xpath(f".//*[{_class('se-component')}]")
    return [
        component
        for component in components
        if not any(
            ancestor is not container and _has_class(ancestor, "se-component")
            for ancestor in component.iterancestors()
        )
    ]


def _se_one(container: etree._Element) -> BodyResult:
    media: list[Media] = []
    blocks: list[str] = []
    meaningful = False
    for component in _top_level_components(container):
        if _has_class(component, "se-text"):
            paragraphs = component.xpath(f".//*[{_class('se-text-paragraph')}]")
            values = [_node_text(paragraph) for paragraph in paragraphs]
            text = "\n\n".join(_markdown_text(value) for value in values if value)
            if text:
                blocks.append(text)
                meaningful = True
        elif _has_class(component, "se-image"):
            image_blocks = _image_blocks(component, media)
            if image_blocks:
                blocks.extend(image_blocks)
                meaningful = True
        elif _has_class(component, "se-quotation"):
            text = _node_text(component)
            if text:
                blocks.append("\n".join(f"> {_markdown_text(line)}" for line in text.splitlines()))
                meaningful = True
        elif _has_class(component, "se-oglink"):
            links = component.xpath(".//a[@href]")
            if links:
                url = links[0].get("href")
                title = _node_text(links[0]) or _first_text(component, "se-oglink-title")
                if url and title:
                    blocks.append(f"[{_markdown_text(title)}]({url})")
                    meaningful = True
        elif _has_class(component, "se-placesMap"):
            links = component.xpath(".//a[@href]")
            title = _first_text(component, "se-place-title") or _node_text(component)
            if title:
                if links and links[0].get("href"):
                    blocks.append(f"[{_markdown_text(title)}]({links[0].get('href')})")
                else:
                    blocks.append(_markdown_text(title))
                meaningful = True
        elif _has_class(component, "se-horizontalLine"):
            blocks.append("---")
    if not meaningful:
        raise _drift("non-empty SmartEditor ONE components")
    return BodyResult(markdown="\n\n".join(blocks), media=tuple(media))


def _legacy(container: etree._Element) -> BodyResult:
    media: list[Media] = []
    blocks: list[str] = []
    # Paragraphs own their descendant images; remaining images are emitted at their DOM position.
    for node in container.iterdescendants():
        if node.tag == "p":
            text = _node_text(node)
            if text:
                blocks.append(_markdown_text(text))
            blocks.extend(_image_blocks(node, media))
        elif node.tag == "img" and not any(
            ancestor.tag == "p" for ancestor in node.iterancestors()
        ):
            blocks.extend(_image_blocks(node, media))
    if not blocks:
        raise _drift("non-empty legacy post content")
    return BodyResult(markdown="\n\n".join(blocks), media=tuple(media))


def parse_post_body(source: str) -> BodyResult:
    """Parse one measured SmartEditor ONE or legacy post document."""
    document = _document(source)
    created_at = _body_date(document)
    containers = document.xpath(f"descendant-or-self::*[{_class('se-main-container')}]")
    for container in containers:
        if _top_level_components(container):
            result = _se_one(container)
            return replace(result, created_at=created_at)
    legacy = document.xpath(
        f"descendant-or-self::div[@id = 'viewTypeSelector' and {_class('post_ct')}]"
    )
    if legacy:
        return replace(_legacy(legacy[0]), created_at=created_at)
    raise _drift("a SmartEditor ONE container with components or div.post_ct#viewTypeSelector")


def _search_container(document: etree._Element) -> etree._Element | None:
    candidates = document.xpath(
        "descendant-or-self::*["
        f"@id = 'postSearchList' or @id = 'post-area' or {_class('post_search_list')} "
        f"or {_class('post-search-list')}"
        "]"
    )
    return candidates[0] if len(candidates) == 1 else None


def _korean_wall_clock(value: str, expected: str) -> datetime:
    """Parse a Naver-rendered date as the Korean wall-clock time it actually is."""
    match = _DATETIME.fullmatch(value) or _DATE.fullmatch(value)
    if match is None:
        raise _drift(expected)
    try:
        return datetime(*(int(part) for part in match.groups()), tzinfo=KST)
    except ValueError as error:
        raise _drift("a valid post date") from error


def _card_date(node: etree._Element) -> datetime | None:
    dates = node.xpath(
        f".//*[{_class('date')} or {_class('txt_date')} or {_class('post_date')} "
        f"or {_class('eng')}]"
    )
    if not dates:
        return None
    return _korean_wall_clock(
        _node_text(dates[0]), "a YYYY. M. D. or YYYY/MM/DD HH:MM post-result date"
    )


def _body_date(document: etree._Element) -> datetime | None:
    """Extract a post's own publish time from the rendered page, when it states one.

    Naver labels recent posts relatively -- "7시간 전", "방금 전", "어제" -- with no absolute time
    behind the label. Those carry a rounded interval, not a timestamp, so they are reported as no
    publish time rather than converted: turning "7시간 전" into an instant invents precision the
    page never gave, and the listing surfaces (`search`, `posts`) expose an exact `addDate` for the
    same post anyway. Text that is neither form is still treated as template drift.
    """
    for node in document.xpath(
        f"descendant-or-self::*[{_class('blog_date')} or {_class('se_publishDate')} "
        f"or {_class('_postAddDate')}]"
    ):
        value = _node_text(node)
        if not value:
            continue
        if _RELATIVE_DATE.search(value):
            return None
        return _korean_wall_clock(value, "a YYYY. M. D. HH:MM post publish date")
    return None


def _post_link(node: etree._Element) -> tuple[str, str, str] | None:
    for anchor in node.xpath(".//a[@href] | self::a[@href]"):
        url = anchor.get("href")
        if not url:
            continue
        split = urlsplit(url)
        query = parse_qs(split.query)
        blog_id = query.get("blogId", [None])[0]
        log_no = query.get("logNo", [None])[0]
        if blog_id is None:
            path_parts = [part for part in split.path.split("/") if part]
            if path_parts and path_parts[0] != "PostView.naver":
                blog_id = path_parts[0]
        if blog_id and log_no:
            return blog_id, log_no, url
    return None


def _live_search_cards(container: etree._Element) -> list[etree._Element]:
    title_links = container.xpath(f".//a[{_class('s_link')} and contains(@href, 'logNo=')]")
    cards: list[etree._Element] = []
    for link in title_links:
        card = next(
            (
                ancestor
                for ancestor in link.iterancestors("table")
                if len(ancestor.xpath("./tr")) >= 2
            ),
            None,
        )
        if card is None:
            raise _drift("a two-row legacy in-blog search result card")
        cards.append(card)
    return cards


def parse_post_search(source: str) -> tuple[PostSearchCard, ...]:
    """Extract only anchored in-blog search result cards from PostSearchList.naver."""
    container = _search_container(_document(source))
    if container is None:
        raise _drift("one PostSearchList.naver result container")

    live_variant = container.get("id") == "post-area"
    cards = _live_search_cards(container) if live_variant else container.xpath("./ul/li | .//ul/li")
    if not cards:
        empty = container.xpath(
            f".//*[{_class('no_result')} or {_class('no_data')} or {_class('search_none')}]"
        )
        has_measured_empty = any(
            "검색결과가 없습니다" in _node_text(node)
            for node in (empty or container.xpath(".//strong"))
        )
        if has_measured_empty:
            return ()
        raise _drift("post result cards or the explicit empty-result marker")

    results: list[PostSearchCard] = []
    for card in cards:
        link = _post_link(card)
        if link is None:
            raise _drift("an anchored post result link with blogId and logNo")
        blog_id, log_no, url = link
        if live_variant:
            title_node = card.xpath(f".//a[{_class('s_link')} and contains(@href, 'logNo=')]")
            rows = card.xpath("./tr")
            brief = _node_text(rows[1]) if len(rows) >= 2 else None
        else:
            title_node = card.xpath(
                f".//*[{_class('title')} or {_class('tit_post')} or {_class('title_post')}]"
            )
            brief_node = card.xpath(
                f".//*[{_class('brief')} or {_class('desc')} or {_class('txt')}]"
            )
            brief = _node_text(brief_node[0]) if brief_node else None
        title = _node_text(title_node[0]) if title_node else ""
        if not title:
            raise _drift("a non-empty post-result title")
        results.append(PostSearchCard(blog_id, log_no, url, title, brief or None, _card_date(card)))
    return tuple(results)
