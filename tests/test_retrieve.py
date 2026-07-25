import json
import re
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

import pytest

import agentic_blog.retrieve as retrieve
from agentic_blog.errors import EnvelopeParseError, NotFoundError
from agentic_blog.retrieve import (
    fetch_blog,
    fetch_buddies,
    fetch_post,
    fetch_posts,
    fetch_topic,
    fetch_topics,
    search,
)

PHASE3 = json.loads((Path(__file__).parent / "fixtures" / "phase3.json").read_text())
PHASE4 = json.loads((Path(__file__).parent / "fixtures" / "phase4.json").read_text())
BODY = (Path(__file__).parent / "fixtures" / "body_se_one.html").read_text()


class FakeClient:
    def __init__(self, pages, *, remaining_requests=100):
        self.pages = iter(pages)
        self.specs = []
        self.requests_made = 0
        self.remaining_requests = remaining_requests

    def get_json(self, spec):
        self.specs.append(spec)
        self.requests_made += 1
        self.remaining_requests -= 1
        return next(self.pages)

    def get_text(self, spec):
        self.specs.append(spec)
        self.requests_made += 1
        self.remaining_requests -= 1
        return next(self.pages)


def post(log_no, blog_id="blog"):
    return {
        "logNo": log_no,
        "blogNo": "1",
        "domainIdOrBlogId": blog_id,
        "title": f"post {log_no}",
        "addDate": 1_700_000_000_000,
    }


MOBILE_PAGE_SIZE = 30
IN_BLOG_PAGE_SIZE = 20


def mpost(log_no, blog_id="blog"):
    """One m.blog search card."""
    return {
        "logNo": int(log_no),
        "blogId": blog_id,
        "title": f"post {log_no}",
        "content": "",
        "addDate": 1_700_000_000_000,
    }


def mpage(items):
    """One m.blog search page, carrying the totals the live host actually reports.

    totalCount and totalPage are deliberately the measured, misleading values: the host
    advertises millions of results across hundreds of thousands of pages and then stops
    answering after 1,000. Every test using this page therefore also proves that paging
    is driven by page length rather than by either total.
    """
    return {
        "isSuccess": True,
        "result": {
            "list": items,
            "currentPage": 1,
            "totalCount": 12_356_134,
            "totalPage": 411_872,
        },
    }


def page(items, *, count=7):
    return {
        "result": {
            "searchDisplayInfo": {},
            "searchList": items,
            "totalCount": len(items),
            "pagePerCount": count,
        }
    }


def buddy_card(blog_id):
    card = deepcopy(PHASE3["public_buddies"]["result"]["buddyList"][0])
    card["blogId"] = blog_id
    card["blogName"] = f"{blog_id} blog"
    card["nickName"] = blog_id
    card["linkUrl"] = f"https://example.invalid/{blog_id}"
    card["blogNo"] = sum(ord(character) for character in blog_id)
    return card


def buddy_page(cards, *, current_page, total_page_count):
    payload = deepcopy(PHASE3["public_buddies"])
    payload["result"]["currentPage"] = current_page
    payload["result"]["totalPageCount"] = total_page_count
    payload["result"]["buddyList"] = cards
    return payload


def test_search_paginates_deduplicates_and_stops_on_short_page():
    client = FakeClient(
        [
            mpage([mpost(value) for value in range(MOBILE_PAGE_SIZE)]),
            mpage([mpost(MOBILE_PAGE_SIZE - 1), mpost(MOBILE_PAGE_SIZE)]),
        ]
    )

    result = search(client, "coffee")

    assert [item.log_no for item in result.items] == [
        str(value) for value in range(MOBILE_PAGE_SIZE + 1)
    ]
    assert result.stop_reason == "no_next_page"
    assert [spec.params["page"] for spec in client.specs] == [1, 2]


def test_search_limit_and_zero_limit_are_bounded():
    client = FakeClient([mpage([mpost(value) for value in range(MOBILE_PAGE_SIZE)])])

    result = search(client, "coffee", limit=2)
    zero = search(FakeClient([]), "coffee", limit=0)

    assert len(result.items) == 2
    assert result.stop_reason == "limit_reached"
    assert len(client.specs) == 1
    assert zero.items == []
    assert zero.stop_reason == "limit_reached"
    assert zero.requests_made == 0


def test_search_reports_limit_reached_only_when_pagination_can_continue():
    full_page = search(
        FakeClient([mpage([mpost(value) for value in range(MOBILE_PAGE_SIZE)])]),
        "coffee",
        limit=MOBILE_PAGE_SIZE,
    )
    short_page = search(FakeClient([mpage([mpost(1), mpost(2)])]), "coffee", limit=2)

    assert full_page.stop_reason == "limit_reached"
    assert short_page.stop_reason == "no_next_page"


def test_search_reports_no_next_page_for_a_duplicate_short_page_tail():
    client = FakeClient([mpage([mpost(1), mpost(2), mpost(1)])])

    result = search(client, "coffee", limit=2)

    assert [item.log_no for item in result.items] == ["1", "2"]
    assert result.stop_reason == "no_next_page"
    assert result.requests_made == 1


def test_search_reports_limit_reached_for_an_unseen_short_page_tail():
    client = FakeClient([mpage([mpost(1), mpost(2), mpost(3)])])

    result = search(client, "coffee", limit=2)

    assert [item.log_no for item in result.items] == ["1", "2"]
    assert result.stop_reason == "limit_reached"
    assert result.requests_made == 1


def test_search_reports_budget_exhaustion_after_a_full_page():
    result = search(
        FakeClient(
            [mpage([mpost(value) for value in range(MOBILE_PAGE_SIZE)])], remaining_requests=1
        ),
        "coffee",
    )

    assert result.stop_reason == "max_requests"
    assert result.requests_made == 1


def test_search_uses_a_per_search_request_delta_for_reused_clients():
    client = FakeClient([mpage([mpost(1)]), mpage([mpost(2)])])
    client.requests_made = 12
    client.remaining_requests = 8

    first = search(client, "coffee")
    second = search(client, "tea")

    assert first.requests_made == second.requests_made == 1


@pytest.mark.parametrize("counter", [True, -1, 1.0, None])
def test_search_rejects_malformed_client_counters(counter):
    client = FakeClient([])
    client.requests_made = counter

    with pytest.raises(ValueError, match="requests_made"):
        search(client, "coffee")


def test_search_rejects_clients_without_the_required_request_method():
    class MissingMethodClient:
        requests_made = 0
        remaining_requests = 1

    with pytest.raises(ValueError, match="provide get_json"):
        search(MissingMethodClient(), "coffee")


def test_search_rejects_client_counters_that_do_not_track_each_request():
    class StaleCounterClient(FakeClient):
        def get_json(self, spec):
            self.specs.append(spec)
            return next(self.pages)

    with pytest.raises(ValueError, match="advance by one"):
        search(StaleCounterClient([mpage([mpost(1)])]), "coffee")


def test_search_propagates_client_dependency_errors():
    class FailingClient(FakeClient):
        def get_json(self, spec):
            raise RuntimeError("transport defect")

    with pytest.raises(RuntimeError, match="transport defect"):
        search(FailingClient([]), "coffee")


def test_search_rejects_malformed_remaining_request_counter():
    client = FakeClient([])
    client.remaining_requests = True

    with pytest.raises(ValueError, match="remaining_requests"):
        search(client, "coffee")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"since": datetime(2026, 7, 1)}, "since must be a date"),
        ({"until": datetime(2026, 7, 1)}, "until must be a date"),
        ({"since": date(2026, 7, 2), "until": date(2026, 7, 1)}, "not be later"),
    ],
)
def test_search_rejects_datetime_and_reversed_date_bounds(kwargs, message):
    with pytest.raises(ValueError, match=message):
        search(FakeClient([]), "coffee", **kwargs)


def test_search_stops_before_a_client_budget_is_exceeded():
    result = search(FakeClient([], remaining_requests=0), "coffee")

    assert result.items == []
    assert result.stop_reason == "max_requests"
    assert result.requests_made == 0


def test_search_reports_no_matches():
    result = search(FakeClient([mpage([])]), "coffee")

    assert result.items == []
    assert result.stop_reason == "no_matches"


def test_search_builds_blogs_for_blog_and_id_types():
    node = {
        "blogNo": "1",
        "domainIdOrBlogId": "blog",
        "blogName": "Blog",
        "nickName": "Author",
    }

    blog_client = FakeClient([page([node], count=10)])
    id_client = FakeClient([page([node], count=10)])

    blog_result = search(blog_client, "blog", search_type="blog", sort="date")
    id_result = search(id_client, "blog", search_type="id")

    assert blog_result.items[0].blog_id == "blog"
    assert id_result.items[0].blog_id == "blog"
    assert blog_client.specs[0].params["orderBy"] == "date"
    assert "orderBy" not in id_client.specs[0].params


@pytest.mark.parametrize(
    ("search_type", "node"),
    [
        (
            "blog",
            {
                "blogNo": "1",
                "domainIdOrBlogId": "",
                "blogName": "Blog",
                "nickName": "Author",
            },
        ),
        (
            "id",
            {
                "blogNo": True,
                "domainIdOrBlogId": "blog",
                "blogName": "Blog",
                "nickName": "Author",
            },
        ),
    ],
)
def test_search_normalizes_malformed_section_cards(search_type, node):
    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.searchList[0]"),
    ):
        search(
            FakeClient([page([node], count=10)]),
            "coffee",
            search_type=search_type,
        )


def test_search_normalizes_malformed_mobile_cards():
    with pytest.raises(EnvelopeParseError, match=re.escape("response.result.list[0]")):
        search(FakeClient([mpage([{"logNo": 1, "blogId": "blog", "title": []}])]), "coffee")


def test_search_normalizes_malformed_tail_card_inspection():
    malformed_tail = mpost(2)
    malformed_tail["commentCount"] = -1

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.list[1]"),
    ):
        search(FakeClient([mpage([mpost(1), malformed_tail])]), "coffee", limit=1)


def test_search_does_not_mask_internal_builder_defects(monkeypatch):
    def broken_builder(*args, **kwargs):
        raise AssertionError("builder invariant")

    monkeypatch.setattr(retrieve, "build_mobile_search_post", broken_builder)

    with pytest.raises(AssertionError, match="builder invariant"):
        search(FakeClient([mpage([mpost(1)])]), "coffee")


def test_fetch_blog_normalizes_identity_cards_before_exact_match():
    malformed_identity = {
        "blogNo": "1",
        "domainIdOrBlogId": True,
        "blogName": "Blog",
        "nickName": "Author",
    }

    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.searchList[0]"),
    ):
        fetch_blog(FakeClient([page([malformed_identity], count=10)]), "missing")


def test_search_propagates_dates_to_the_server_without_filtering():
    client = FakeClient([mpage([mpost(1)])])

    result = search(client, "coffee", since=date(2026, 7, 1), until=date(2026, 7, 2), raw=True)

    assert result.items[0].raw == mpost(1)
    assert client.specs[0].params["startDate"] == "2026-07-01"
    assert client.specs[0].params["endDate"] == "2026-07-02"
    assert client.specs[0].params["sortType"] == "sim"
    assert "periodType" not in client.specs[0].params


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"search_type": "id", "sort": "sim"}, "id searches"),
        ({"search_type": "blog", "since": date(2026, 7, 1)}, "post searches"),
        ({"limit": -1}, "non-negative"),
    ],
)
def test_search_rejects_invalid_combinations(kwargs, message):
    with pytest.raises(ValueError, match=message):
        search(FakeClient([]), "coffee", **kwargs)


def test_phase3_single_target_and_listing_surfaces_use_their_endpoint_contracts():
    profile_node = {
        "blogNo": "20001",
        "domainIdOrBlogId": "synthetic_alice",
        "blogName": "Synthetic Alice",
        "nickName": "Synthetic Alice",
    }
    blog = fetch_blog(
        FakeClient(
            [page([profile_node], count=10), PHASE3["category_list"], PHASE3["public_buddies"]]
        ),
        "synthetic_alice",
    )
    posts = fetch_posts(FakeClient([PHASE3["post_list"]]), "synthetic_alice", category=7)
    topics = fetch_topics(FakeClient([PHASE3["directory_list"]]))
    chronological_client = FakeClient([PHASE3["directory_post_list"]])
    top_client = FakeClient([PHASE3["directory_top_post_list"]])
    chronological = fetch_topic(chronological_client, 5)
    top = fetch_topic(top_client, 5, top=True)

    assert blog.stop_reason == topics.stop_reason == "single_target"
    assert blog.items[0].categories[0].category_no == "7"
    assert posts.items[0].log_no == "10001"
    assert chronological.items[0].log_no == "10001"
    assert chronological.stop_reason == top.stop_reason == "no_next_page"
    assert chronological_client.specs[0].url.endswith("DirectoryPostList.naver")
    assert top_client.specs[0].url.endswith("DirectoryTopPostList.naver")
    assert top.items[0].log_no == "10003"


def test_fetch_topic_rejects_variant_envelope_confusion() -> None:
    with pytest.raises(EnvelopeParseError, match="response.result"):
        fetch_topic(FakeClient([PHASE3["directory_top_post_list"]]), 5)
    with pytest.raises(EnvelopeParseError, match="response.result"):
        fetch_topic(FakeClient([PHASE3["directory_post_list"]]), 5, top=True)


def test_fetch_topic_top_honors_its_limit_deterministically() -> None:
    result = fetch_topic(FakeClient([PHASE3["directory_top_post_list"]]), 5, top=True, limit=1)
    zero = fetch_topic(FakeClient([]), 5, top=True, limit=0)

    assert [item.log_no for item in result.items] == ["10003"]
    assert result.stop_reason == "no_next_page"
    assert zero.items == []
    assert zero.stop_reason == "limit_reached"
    assert zero.requests_made == 0


def test_fetch_posts_normalizes_and_deduplicates_popular_cards() -> None:
    payload = deepcopy(PHASE3["popular_post_list"])
    popular_cards = payload["result"]["popularPostList"]
    popular_cards.append(deepcopy(popular_cards[0]))

    result = fetch_posts(FakeClient([payload]), "synthetic_alice", sort="popular", raw=True)

    assert len(result.items) == 1
    assert result.items[0].blog_id == "synthetic_alice"
    assert result.items[0].log_no == "10003"
    assert result.items[0].blog_no is None
    assert result.items[0].url == "https://blog.naver.com/synthetic_alice/10003"
    assert result.items[0].raw == popular_cards[0]
    assert result.items[0].media is None


def test_fetch_buddies_crosses_pages_deduplicates_and_honors_limit() -> None:
    client = FakeClient(
        [
            buddy_page(
                [buddy_card("bob"), buddy_card("alice")], current_page=1, total_page_count=2
            ),
            buddy_page(
                [buddy_card("alice"), buddy_card("cara")], current_page=2, total_page_count=2
            ),
        ]
    )

    result = fetch_buddies(client, "synthetic_alice", limit=3)

    assert [item.blog_id for item in result.items] == ["bob", "alice", "cara"]
    assert result.stop_reason == "no_next_page"
    assert [spec.params["pageNo"] for spec in client.specs] == [1, 2]


def test_fetch_buddies_stops_when_request_budget_is_exhausted() -> None:
    client = FakeClient(
        [buddy_page([buddy_card("bob")], current_page=1, total_page_count=2)],
        remaining_requests=1,
    )

    result = fetch_buddies(client, "synthetic_alice")

    assert [item.blog_id for item in result.items] == ["bob"]
    assert result.stop_reason == "max_requests"
    assert result.requests_made == 1


def test_fetch_posts_popular_rejects_variant_confusion_and_malformed_identities():
    malformed_popular = deepcopy(PHASE3["popular_post_list"])
    malformed_popular["result"]["popularPostList"][0]["blogId"] = ""

    with pytest.raises(EnvelopeParseError, match="popularPostList"):
        fetch_posts(FakeClient([PHASE3["post_list"]]), "synthetic_alice", sort="popular")
    with pytest.raises(
        EnvelopeParseError,
        match=re.escape("response.result.popularPostList[0].blogId"),
    ):
        fetch_posts(FakeClient([malformed_popular]), "synthetic_alice", sort="popular")


def test_posts_rejects_unavailable_variant_combinations():
    with pytest.raises(ValueError, match="popular"):
        fetch_posts(FakeClient([]), "blog", notices=True, sort="popular")
    with pytest.raises(ValueError, match="category"):
        fetch_posts(FakeClient([]), "blog", category=1, sort="popular")


def test_fetch_blog_composes_exact_id_profile_categories_and_raw_in_two_requests():
    profile_node = {
        "blogNo": "20001",
        "domainIdOrBlogId": "synthetic_alice",
        "blogName": "Synthetic Alice",
        "nickName": "Synthetic Alice",
        "blogDesc": "Measured profile",
    }
    client = FakeClient(
        [page([profile_node], count=10), PHASE3["category_list"], PHASE3["public_buddies"]]
    )
    client.requests_made = 12
    client.remaining_requests = 8

    result = fetch_blog(client, "synthetic_alice", raw=True)

    assert result.stop_reason == "single_target"
    assert result.requests_made == 3
    assert result.items[0].blog_id == "synthetic_alice"
    assert result.items[0].categories[0].category_no == "7"
    assert result.items[0].raw == profile_node
    # Both were validated on the way in and then dropped before 0.2.0.
    assert result.items[0].post_count == PHASE3["category_list"]["result"]["mylogPostCount"]
    assert (
        result.items[0].buddy_count
        == PHASE3["public_buddies"]["result"]["totalPublicBuddyCount"]
    )
    assert client.specs[0].params == {
        "type": "id",
        "keyword": "synthetic_alice",
        "currentPage": 1,
        "countPerPage": 10,
    }
    assert client.specs[1].url.endswith("/synthetic_alice/category-list")
    assert client.specs[2].url.endswith("/synthetic_alice/public-buddies")


def test_fetch_blog_reserves_the_profile_and_category_budget_and_rejects_non_matches():
    budget_result = fetch_blog(FakeClient([], remaining_requests=1), "synthetic_alice")
    miss_client = FakeClient([page([], count=10)])

    assert budget_result.items == []
    assert budget_result.stop_reason == "max_requests"
    assert budget_result.requests_made == 0
    with pytest.raises(NotFoundError, match="blog not found"):
        fetch_blog(miss_client, "synthetic_alice")
    assert miss_client.requests_made == 1


def test_listing_limits_use_source_specific_continuation_evidence():
    duplicate_tail = deepcopy(PHASE3["post_list"])
    duplicate_cards = duplicate_tail["result"]["items"]
    second_card = deepcopy(duplicate_cards[0])
    second_card["logNo"] = 10002
    duplicate_cards[:] = [duplicate_cards[0], second_card, deepcopy(duplicate_cards[0])]

    full_page = deepcopy(PHASE3["post_list"])
    full_cards = full_page["result"]["items"]
    source_card = deepcopy(full_cards[0])
    full_cards[:] = []
    for log_no in range(24):
        card = deepcopy(source_card)
        card["logNo"] = log_no
        full_cards.append(card)
    full_page["result"]["totalCount"] = 0

    popular = fetch_posts(
        FakeClient([PHASE3["popular_post_list"]]),
        "synthetic_alice",
        sort="popular",
        limit=1,
    )
    notices = fetch_posts(
        FakeClient([PHASE3["notice_post_list"]]),
        "synthetic_alice",
        notices=True,
        limit=1,
    )
    chronological_duplicate_tail = fetch_posts(
        FakeClient([duplicate_tail]), "synthetic_alice", limit=2
    )
    chronological_full_page = fetch_posts(FakeClient([full_page]), "synthetic_alice", limit=24)

    assert popular.stop_reason == "no_next_page"
    assert notices.stop_reason == "no_next_page"
    assert chronological_duplicate_tail.stop_reason == "no_next_page"
    assert chronological_full_page.stop_reason == "limit_reached"
    assert chronological_full_page.requests_made == 1


def test_fetch_topics_deduplicates_normalized_sequences_without_changing_single_target():
    payload = deepcopy(PHASE3["directory_list"])
    duplicate = deepcopy(payload["result"][0]["directoryList"][0])
    duplicate["seq"] = 5
    payload["result"][0]["directoryList"].append(duplicate)

    result = fetch_topics(FakeClient([payload]))

    assert [item.seq for item in result.items] == ["5"]
    assert result.stop_reason == "single_target"


def test_fetch_topic_deduplicates_across_pages():
    first_page = deepcopy(PHASE3["directory_post_list"])
    cards = first_page["result"]["postList"]
    source_card = deepcopy(cards[0])
    cards[:] = []
    for log_no in range(24):
        card = deepcopy(source_card)
        card["logNo"] = log_no
        cards.append(card)

    second_page = deepcopy(PHASE3["directory_post_list"])
    second_cards = second_page["result"]["postList"]
    duplicate = deepcopy(source_card)
    duplicate["logNo"] = 23
    new_card = deepcopy(source_card)
    new_card["logNo"] = 24
    second_cards[:] = [duplicate, new_card]

    client = FakeClient([first_page, second_page])
    result = fetch_topic(client, 5)

    assert [item.log_no for item in result.items] == [str(value) for value in range(25)]
    assert result.stop_reason == "no_next_page"
    assert [spec.params["pageNo"] for spec in client.specs] == [1, 2]


def test_fetch_post_composes_body_comments_and_never_requests_telemetry():
    client = FakeClient([BODY, PHASE4["comments_info"], PHASE4["cbox_list"]])

    result = fetch_post(client, "https://m.blog.naver.com/synthetic_alice/10001")

    post = result.items[0]
    assert result.stop_reason == "single_target"
    assert result.requests_made == 3
    assert post.url == "https://blog.naver.com/synthetic_alice/10001"
    assert post.title == "합성 댓글 예시"
    assert post.body
    assert [comment.comment_no for comment in post.comments] == ["90001", "90003"]
    assert post.comments[0].replies[0].comment_no == "90002"
    assert [spec.url for spec in client.specs] == [
        "https://m.blog.naver.com/synthetic_alice/10001",
        "https://m.blog.naver.com/api/blogs/synthetic_alice/posts/10001/comments-info",
        "https://apis.naver.com/commentBox/cbox/web_naver_list_json.json",
    ]
    assert all("telemetry" not in spec.url for spec in client.specs)


def test_fetch_post_rebuilds_measured_flat_cbox_pages_into_a_tree():
    root = deepcopy(PHASE4["cbox_list"]["result"]["commentList"][0])
    reply = root.pop("replyList")[0]
    root["replyList"] = None
    first_page = deepcopy(PHASE4["cbox_list"])
    second_page = deepcopy(PHASE4["cbox_list"])
    for page, number, card in ((first_page, 1, root), (second_page, 2, reply)):
        page["result"]["count"] = {"comment": 1, "reply": 1, "total": 2}
        page["result"]["pageModel"] = {"page": number, "pageSize": 1, "totalPages": 2}
        page["result"]["commentList"] = [card]

    info = deepcopy(PHASE4["comments_info"])
    info["result"]["totalCount"] = 2
    result = fetch_post(
        FakeClient([BODY, info, first_page, second_page]),
        "synthetic_alice",
        10001,
    )

    assert len(result.items[0].comments) == 1
    assert result.items[0].comments[0].replies[0].comment_no == "90002"
    assert result.requests_made == 4


def _flat_cbox_page(cards, *, page, total_pages, count):
    payload = deepcopy(PHASE4["cbox_list"])
    payload["result"]["count"] = count
    payload["result"]["pageModel"] = {
        "page": page,
        "pageSize": len(cards),
        "totalPages": total_pages,
    }
    payload["result"]["commentList"] = cards
    return payload


def test_fetch_post_comment_limit_waits_for_later_page_replies():
    root = deepcopy(PHASE4["cbox_list"]["result"]["commentList"][0])
    reply = root.pop("replyList")[0]
    root["replyList"] = None
    other_root = deepcopy(PHASE4["cbox_list"]["result"]["commentList"][1])
    count = {"comment": 2, "reply": 1, "total": 3}
    first_page = _flat_cbox_page([root, other_root], page=1, total_pages=2, count=count)
    second_page = _flat_cbox_page([reply], page=2, total_pages=2, count=count)

    result = fetch_post(
        FakeClient([BODY, PHASE4["comments_info"], first_page, second_page]),
        "synthetic_alice",
        10001,
        comment_limit=1,
    )

    assert result.requests_made == 4
    assert [comment.comment_no for comment in result.items[0].comments] == ["90001"]
    assert result.items[0].comments[0].replies[0].comment_no == "90002"


def test_fetch_post_rejects_orphan_reply_on_terminal_completion():
    root = deepcopy(PHASE4["cbox_list"]["result"]["commentList"][0])
    reply = root.pop("replyList")[0]
    reply["replyList"] = None
    info = deepcopy(PHASE4["comments_info"])
    info["result"]["totalCount"] = 2
    orphan_page = _flat_cbox_page(
        [reply],
        page=1,
        total_pages=1,
        count={"comment": 1, "reply": 1, "total": 2},
    )

    with pytest.raises(EnvelopeParseError, match="has no parent"):
        fetch_post(FakeClient([BODY, info, orphan_page]), "synthetic_alice", 10001)


def test_fetch_post_rejects_comments_info_and_cbox_count_mismatch():
    mismatch_page = deepcopy(PHASE4["cbox_list"])
    mismatch_page["result"]["count"] = {"comment": 1, "reply": 1, "total": 2}

    with pytest.raises(EnvelopeParseError, match="comments-info"):
        fetch_post(
            FakeClient([BODY, PHASE4["comments_info"], mismatch_page]),
            "synthetic_alice",
            10001,
        )


def test_fetch_post_rejects_inconsistent_cbox_page_count():
    root = deepcopy(PHASE4["cbox_list"]["result"]["commentList"][0])
    reply = root.pop("replyList")[0]
    root["replyList"] = None
    info = deepcopy(PHASE4["comments_info"])
    info["result"]["totalCount"] = 2
    count = {"comment": 1, "reply": 1, "total": 2}
    first_page = _flat_cbox_page([root], page=1, total_pages=2, count=count)
    second_page = _flat_cbox_page([reply], page=2, total_pages=3, count=count)

    with pytest.raises(EnvelopeParseError, match="total pages"):
        fetch_post(FakeClient([BODY, info, first_page, second_page]), "synthetic_alice", 10001)


def test_fetch_post_returns_partial_comment_tree_only_for_max_requests():
    root = deepcopy(PHASE4["cbox_list"]["result"]["commentList"][0])
    root["replyList"] = None
    partial_page = _flat_cbox_page(
        [root],
        page=1,
        total_pages=2,
        count={"comment": 2, "reply": 1, "total": 3},
    )

    result = fetch_post(
        FakeClient([BODY, PHASE4["comments_info"], partial_page], remaining_requests=3),
        "synthetic_alice",
        10001,
    )

    assert result.stop_reason == "max_requests"
    assert result.items[0].comments[0].replies == []


def _cbox_card(comment_no, *, parent_comment_no=None, reply_level=1, reply_count=0, replies=None):
    card = deepcopy(PHASE4["cbox_list"]["result"]["commentList"][0])
    card["commentNo"] = comment_no
    card["parentCommentNo"] = parent_comment_no or comment_no
    card["replyLevel"] = reply_level
    card["replyCount"] = reply_count
    card["replyList"] = replies
    return card


def _comments_info(total):
    info = deepcopy(PHASE4["comments_info"])
    info["result"]["totalCount"] = total
    return info


def test_fetch_post_waits_for_a_later_page_grandchild_before_limiting_roots():
    grandchild = _cbox_card("90004", parent_comment_no="90002", reply_level=3)
    child = _cbox_card(
        "90002", parent_comment_no="90001", reply_level=2, reply_count=1, replies=None
    )
    root = _cbox_card("90001", reply_count=1, replies=[child])
    count = {"comment": 1, "reply": 2, "total": 3}
    first_page = _flat_cbox_page([root], page=1, total_pages=2, count=count)
    second_page = _flat_cbox_page([grandchild], page=2, total_pages=2, count=count)

    result = fetch_post(
        FakeClient([BODY, _comments_info(3), first_page, second_page]),
        "synthetic_alice",
        10001,
        comment_limit=1,
    )

    assert result.requests_made == 4
    assert result.items[0].comments[0].replies[0].replies[0].comment_no == "90004"


def test_fetch_post_stops_early_for_a_recursively_complete_selected_root():
    child = _cbox_card("90002", parent_comment_no="90001", reply_level=2)
    root = _cbox_card("90001", reply_count=1, replies=[child])
    count = {"comment": 2, "reply": 1, "total": 3}
    first_page = _flat_cbox_page([root], page=1, total_pages=2, count=count)

    result = fetch_post(
        FakeClient([BODY, _comments_info(3), first_page]),
        "synthetic_alice",
        10001,
        comment_limit=1,
    )

    assert result.stop_reason == "single_target"
    assert result.requests_made == 3
    assert result.items[0].comments[0].replies[0].comment_no == "90002"


def test_fetch_post_allows_unresolved_unselected_replies_before_early_limit_completion():
    root = _cbox_card("90001")
    unresolved_reply = _cbox_card("90003", parent_comment_no="90002", reply_level=2)
    count = {"comment": 2, "reply": 1, "total": 3}
    first_page = _flat_cbox_page([root, unresolved_reply], page=1, total_pages=2, count=count)

    result = fetch_post(
        FakeClient([BODY, _comments_info(3), first_page]),
        "synthetic_alice",
        10001,
        comment_limit=1,
    )

    assert result.stop_reason == "single_target"
    assert result.requests_made == 3
    assert [comment.comment_no for comment in result.items[0].comments] == ["90001"]


def test_fetch_post_rejects_equal_total_with_wrong_root_reply_categories():
    root = _cbox_card("90001", reply_count=1)
    child = _cbox_card("90002", parent_comment_no="90001", reply_level=2)
    wrong_count = {"comment": 2, "reply": 0, "total": 2}
    malformed_page = _flat_cbox_page([root, child], page=1, total_pages=1, count=wrong_count)

    with pytest.raises(EnvelopeParseError, match="assembled counts"):
        fetch_post(FakeClient([BODY, _comments_info(2), malformed_page]), "synthetic_alice", 10001)


def test_fetch_post_rejects_cross_page_reply_level_drift_as_an_envelope_error():
    root = _cbox_card("90001", reply_count=1)
    invalid_child = _cbox_card("90002", parent_comment_no="90001", reply_level=3)
    count = {"comment": 1, "reply": 1, "total": 2}
    first_page = _flat_cbox_page([root], page=1, total_pages=2, count=count)
    second_page = _flat_cbox_page([invalid_child], page=2, total_pages=2, count=count)

    with pytest.raises(EnvelopeParseError, match="reply level"):
        fetch_post(
            FakeClient([BODY, _comments_info(2), first_page, second_page]),
            "synthetic_alice",
            10001,
        )


def test_fetch_post_merges_flat_first_and_nested_later_descendants():
    child = _cbox_card("90002", parent_comment_no="90001", reply_level=2)
    flat_root = _cbox_card("90001", reply_count=1)
    nested_root = _cbox_card("90001", reply_count=1, replies=[child])
    count = {"comment": 1, "reply": 1, "total": 2}
    first_page = _flat_cbox_page([flat_root], page=1, total_pages=2, count=count)
    second_page = _flat_cbox_page([nested_root], page=2, total_pages=2, count=count)

    result = fetch_post(
        FakeClient([BODY, _comments_info(2), first_page, second_page]),
        "synthetic_alice",
        10001,
    )

    assert result.items[0].comments[0].replies[0].comment_no == "90002"


def test_fetch_post_keeps_nested_first_flat_later_root_order_and_deduplicates():
    child = _cbox_card("90002", parent_comment_no="90001", reply_level=2)
    root_one = _cbox_card("90001", reply_count=1, replies=[child])
    root_two = _cbox_card("90003")
    duplicate_child = _cbox_card("90002", parent_comment_no="90001", reply_level=2)
    count = {"comment": 2, "reply": 1, "total": 3}
    first_page = _flat_cbox_page([root_one], page=1, total_pages=2, count=count)
    second_page = _flat_cbox_page([duplicate_child, root_two], page=2, total_pages=2, count=count)

    result = fetch_post(
        FakeClient([BODY, _comments_info(3), first_page, second_page]),
        "synthetic_alice",
        10001,
    )

    assert [comment.comment_no for comment in result.items[0].comments] == ["90001", "90003"]
    assert [reply.comment_no for reply in result.items[0].comments[0].replies] == ["90002"]


def test_fetch_post_rejects_duplicate_structural_identity_conflicts():
    first_root = _cbox_card("90001", reply_count=0)
    conflicting_root = _cbox_card("90001", reply_count=1)
    count = {"comment": 1, "reply": 0, "total": 1}
    first_page = _flat_cbox_page([first_root], page=1, total_pages=2, count=count)
    second_page = _flat_cbox_page([conflicting_root], page=2, total_pages=2, count=count)

    with pytest.raises(EnvelopeParseError, match="structural identity"):
        fetch_post(
            FakeClient([BODY, _comments_info(1), first_page, second_page]),
            "synthetic_alice",
            10001,
        )


def test_fetch_post_uses_favorite_cbox_sort_and_deduplicates_cross_page_cards():
    root = _cbox_card("90001")
    duplicate_root = _cbox_card("90001")
    other_root = _cbox_card("90003")
    count = {"comment": 2, "reply": 0, "total": 2}
    first_page = _flat_cbox_page([root], page=1, total_pages=2, count=count)
    second_page = _flat_cbox_page([duplicate_root, other_root], page=2, total_pages=2, count=count)

    client = FakeClient([BODY, _comments_info(2), first_page, second_page])
    result = fetch_post(client, "synthetic_alice", 10001, comment_sort="favorite")

    assert [comment.comment_no for comment in result.items[0].comments] == ["90001", "90003"]
    assert [spec.params["sort"] for spec in client.specs[2:]] == ["FAVORITE", "FAVORITE"]


def test_fetch_post_omits_cbox_for_no_comments_zero_limit_and_reserved_budget():
    no_comments = fetch_post(
        FakeClient([BODY, PHASE4["comments_info"]]), "synthetic_alice", 10001, comments=False
    )
    zero_limit = fetch_post(
        FakeClient([BODY, PHASE4["comments_info"]]), "synthetic_alice", 10001, comment_limit=0
    )
    zero_info = deepcopy(PHASE4["comments_info"])
    zero_info["result"]["totalCount"] = 0
    zero_total = fetch_post(FakeClient([BODY, zero_info]), "synthetic_alice", 10001)
    budget = fetch_post(FakeClient([], remaining_requests=1), "synthetic_alice", 10001)

    assert no_comments.items[0].comments is None
    assert zero_limit.items[0].comments == []
    assert zero_total.items[0].comments == []
    assert no_comments.requests_made == zero_limit.requests_made == zero_total.requests_made == 2
    assert budget.items == []
    assert budget.stop_reason == "max_requests"
    assert budget.requests_made == 0


def _post_search_html(log_nos):
    cards = "".join(
        f'<li><a href="https://blog.naver.com/PostView.naver?blogId=blog&logNo={log_no}">'
        f'<span class="title">post {log_no}</span></a><span class="brief">brief</span></li>'
        for log_no in log_nos
    )
    return f'<div id="postSearchList"><ul>{cards}</ul></div>'


def test_fetch_posts_query_uses_the_mobile_json_search_and_deduplicates_pages():
    client = FakeClient(
        [
            mpage([mpost(value) for value in range(IN_BLOG_PAGE_SIZE)]),
            mpage([mpost(IN_BLOG_PAGE_SIZE - 1), mpost(IN_BLOG_PAGE_SIZE)]),
        ]
    )

    result = fetch_posts(client, "blog", query="coffee")

    assert [item.log_no for item in result.items] == [
        str(value) for value in range(IN_BLOG_PAGE_SIZE + 1)
    ]
    assert result.stop_reason == "no_next_page"
    assert [spec.url for spec in client.specs] == [
        "https://m.blog.naver.com/api/blogs/blog/search/post",
        "https://m.blog.naver.com/api/blogs/blog/search/post",
    ]
    assert [spec.params["page"] for spec in client.specs] == [1, 2]
    # `query`, not `keyword` — the host answers 500 to the latter.
    assert client.specs[0].params["query"] == "coffee"


def test_fetch_posts_query_supports_raw_now_that_the_source_is_json():
    client = FakeClient([mpage([mpost(1)])])

    result = fetch_posts(client, "blog", query="coffee", raw=True)

    assert result.items[0].raw == mpost(1)


@pytest.mark.parametrize(
    "kwargs", [{"query": "q", "category": 1}, {"query": "q", "sort": "popular"}]
)
def test_fetch_posts_query_rejects_listing_variants(kwargs):
    with pytest.raises(ValueError, match="query"):
        fetch_posts(FakeClient([]), "blog", **kwargs)


def test_mobile_search_ignores_the_totals_that_overstate_reachable_depth():
    """The live host reports millions of results, then stops answering after 1,000.

    A short page is the only honest end-of-results signal here. If paging ever consulted
    totalPage, this run would demand 411,872 pages and exhaust the request budget instead
    of returning after two.
    """
    client = FakeClient(
        [
            mpage([mpost(value) for value in range(MOBILE_PAGE_SIZE)]),
            mpage([mpost(MOBILE_PAGE_SIZE)]),
        ]
    )

    result = search(client, "coffee")

    assert result.stop_reason == "no_next_page"
    assert len(client.specs) == 2
    assert len(result.items) == MOBILE_PAGE_SIZE + 1


def test_search_routes_each_type_to_the_host_that_can_answer_it():
    post_client = FakeClient([mpage([mpost(1)])])
    tag_client = FakeClient([mpage([mpost(1)])])
    blog_client = FakeClient([page([{"blogNo": "1", "domainIdOrBlogId": "blog"}], count=10)])

    search(post_client, "coffee")
    search(tag_client, "coffee", search_type="tag")
    search(blog_client, "coffee", search_type="blog")

    assert post_client.specs[0].url == "https://m.blog.naver.com/api/search/v1/post"
    assert tag_client.specs[0].url == "https://m.blog.naver.com/api/tags/search/post"
    # Section keeps blog search: the mobile blog index is a different, smaller corpus and
    # its card carries no description.
    assert blog_client.specs[0].url.endswith("SearchList.naver")


def test_self_purchased_is_sent_only_when_asked_and_only_for_posts():
    on = FakeClient([mpage([mpost(1)])])
    off = FakeClient([mpage([mpost(1)])])

    search(on, "airpods", self_purchased=True)
    search(off, "airpods")

    assert on.specs[0].params["isBuyWithMyOwnMoney"] == "true"
    assert "isBuyWithMyOwnMoney" not in off.specs[0].params

    with pytest.raises(ValueError, match="only supported for post searches"):
        search(FakeClient([]), "airpods", search_type="tag", self_purchased=True)


def test_fetch_blog_reports_undisclosed_neighbours_as_zero_not_as_unavailable():
    """A blog with many neighbours and none disclosed is a real 0, not a missing value.

    Measured live: one blog reports 1,908 neighbours of which 0 are public. Reading that as
    "no neighbours" would be wrong, and reading it as "field unavailable" would be too.
    """
    profile_node = {
        "blogNo": "20001",
        "domainIdOrBlogId": "synthetic_alice",
        "blogName": "Synthetic Alice",
        "nickName": "Synthetic Alice",
    }
    buddies = deepcopy(PHASE3["public_buddies"])
    buddies["result"]["totalMyBuddyCount"] = 1908
    buddies["result"]["totalPublicBuddyCount"] = 0
    buddies["result"]["totalPageCount"] = 0
    buddies["result"]["currentPage"] = 1
    buddies["result"]["buddyList"] = []

    result = fetch_blog(
        FakeClient([page([profile_node], count=10), PHASE3["category_list"], buddies]),
        "synthetic_alice",
    )

    assert result.items[0].buddy_count == 0


def test_fetch_blog_leaves_buddy_count_unset_rather_than_failing_on_a_spent_budget():
    profile_node = {
        "blogNo": "20001",
        "domainIdOrBlogId": "synthetic_alice",
        "blogName": "Synthetic Alice",
        "nickName": "Synthetic Alice",
    }
    client = FakeClient(
        [page([profile_node], count=10), PHASE3["category_list"]], remaining_requests=2
    )

    result = fetch_blog(client, "synthetic_alice")

    assert result.items[0].post_count is not None
    assert result.items[0].buddy_count is None
    assert len(client.specs) == 2
