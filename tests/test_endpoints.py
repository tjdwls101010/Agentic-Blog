import inspect
from collections.abc import Mapping
from dataclasses import FrozenInstanceError

import pytest

import agentic_blog.endpoints as endpoints
from agentic_blog.endpoints import (
    BLOG_TAG_LIST_INFO,
    CBOX_OBJECT_ID,
    CBOX_POOL,
    MOBILE,
    POST_LIST_MAX_ITEM_COUNT,
    SECTION,
    SECTION_DIRECTORY_LIST,
    SECTION_DIRECTORY_POST_LIST,
    SECTION_DIRECTORY_TOP_POST_LIST,
    SECTION_SEARCH_LIST,
    RequestSpec,
    category_list,
    cbox_list,
    chronological_post_list,
    comments_info,
    directory_list,
    directory_post_list,
    directory_top_post_list,
    in_blog_search,
    in_blog_tag_search,
    mobile_search_post,
    mobile_tag_search,
    notice_post_list,
    popular_post_list,
    post_html,
    post_list,
    post_tags,
    public_buddies,
    search_list,
)
from agentic_blog.errors import InvalidIdentifierError


def test_section_constants_describe_the_search_endpoint():
    assert SECTION == "https://section.blog.naver.com/ajax/"
    assert SECTION_SEARCH_LIST == "https://section.blog.naver.com/ajax/SearchList.naver"


def test_id_search_omits_unsupported_sort_and_date_parameters():
    request = search_list(
        "synthetic_alice",
        search_type="id",
        sort=None,
        page=1,
        count_per_page=10,
    )

    assert request.url == SECTION_SEARCH_LIST
    assert request.params == {
        "type": "id",
        "keyword": "synthetic_alice",
        "currentPage": 1,
        "countPerPage": 10,
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"search_type": "id", "sort": "sim"}, "id search does not support sort"),
        (
            {"search_type": "id", "sort": None, "since": "2026-07-01"},
            "id search does not support date bounds",
        ),
        (
            {"search_type": "id", "sort": None, "until": "2026-07-25"},
            "id search does not support date bounds",
        ),
        (
            {"search_type": "blog", "since": "2026-07-01"},
            "blog search does not support date bounds",
        ),
        ({"search_type": "post", "since": "2026-02-30"}, "since must be YYYY-MM-DD"),
        (
            {"search_type": "post", "since": "2026-07-25", "until": "2026-07-01"},
            "since must not be after until",
        ),
        ({"search_type": "post", "page": 0}, "page must be positive"),
        ({"search_type": "post", "count_per_page": 0}, "count per page must be positive"),
    ],
)
def test_search_list_rejects_invalid_type_specific_parameters(kwargs, message):
    with pytest.raises(InvalidIdentifierError, match=message):
        search_list("query", **kwargs)


def test_request_spec_is_frozen_and_params_are_defensive_and_immutable():
    source = {"keyword": "original"}
    request = RequestSpec("https://section.blog.naver.com/ajax/SearchList.naver", source)
    source["keyword"] = "changed"

    assert isinstance(request.params, Mapping)
    assert request.params == {"keyword": "original"}
    with pytest.raises(TypeError):
        request.params["keyword"] = "replacement"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        request.url = "https://example.com/"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"query": ""}, "search query is empty"),
        ({"query": "   "}, "search query is empty"),
        ({"query": 1}, "search query is empty"),
        ({"search_type": 1}, "invalid search type"),
        ({"search_type": True}, "invalid search type"),
        ({"sort": 1}, "invalid search sort"),
        ({"sort": True}, "invalid search sort"),
        ({"page": True}, "page must be positive"),
        ({"page": 0}, "page must be positive"),
        ({"page": -1}, "page must be positive"),
        ({"page": 1.0}, "page must be positive"),
        ({"count_per_page": True}, "count per page must be positive"),
        ({"count_per_page": 0}, "count per page must be positive"),
        ({"count_per_page": -1}, "count per page must be positive"),
        ({"count_per_page": 1.0}, "count per page must be positive"),
        ({"since": 1}, "since must be YYYY-MM-DD"),
        ({"until": True}, "until must be YYYY-MM-DD"),
        ({"since": ""}, "since must be YYYY-MM-DD"),
        ({"until": ""}, "until must be YYYY-MM-DD"),
    ],
)
def test_search_list_rejects_invalid_scalar_values(kwargs, message):
    query = kwargs.pop("query", "query")
    with pytest.raises(InvalidIdentifierError, match=message):
        search_list(query, **kwargs)


def test_phase3_builders_use_only_measured_mobile_and_section_endpoints():
    blog_id = "synthetic_alice"

    assert MOBILE == "https://m.blog.naver.com/api/blogs/"
    assert category_list(blog_id) == RequestSpec(
        "https://m.blog.naver.com/api/blogs/synthetic_alice/category-list", {}
    )
    assert chronological_post_list(blog_id, category_no=7, item_count=24, page=2) == RequestSpec(
        "https://m.blog.naver.com/api/blogs/synthetic_alice/post-list",
        {"categoryNo": 7, "itemCount": 24, "page": 2},
    )
    assert notice_post_list(blog_id) == RequestSpec(
        "https://m.blog.naver.com/api/blogs/synthetic_alice/notice-post-list", {}
    )
    assert popular_post_list(blog_id) == RequestSpec(
        "https://m.blog.naver.com/api/blogs/synthetic_alice/popular-post-list", {}
    )
    assert public_buddies(blog_id, page=3) == RequestSpec(
        "https://m.blog.naver.com/api/blogs/synthetic_alice/public-buddies", {"pageNo": 3}
    )
    assert directory_list() == RequestSpec(SECTION_DIRECTORY_LIST, {})
    assert directory_post_list("5", page=2) == RequestSpec(
        SECTION_DIRECTORY_POST_LIST, {"directorySeq": 5, "pageNo": 2}
    )
    assert directory_top_post_list(5) == RequestSpec(
        SECTION_DIRECTORY_TOP_POST_LIST, {"directorySeq": 5}
    )


def test_post_list_dispatches_sort_and_notices_without_ignored_parameters():
    assert post_list("synthetic_alice", sort="popular") == popular_post_list("synthetic_alice")
    assert post_list("synthetic_alice", notices=True) == notice_post_list("synthetic_alice")
    assert post_list("synthetic_alice", category_no=2, item_count=12, page=3) == (
        chronological_post_list("synthetic_alice", category_no=2, item_count=12, page=3)
    )


@pytest.mark.parametrize("item_count", [31, 50, 1_000])
def test_post_list_item_count_is_clamped_before_it_can_reach_the_server(item_count):
    request = post_list("synthetic_alice", item_count=item_count)

    assert POST_LIST_MAX_ITEM_COUNT == 30
    assert request.params["itemCount"] == 30
    assert (
        max(
            post_list("synthetic_alice", item_count=count).params["itemCount"]
            for count in (1, 24, 30, 31, 50, 1_000)
        )
        == 30
    )


@pytest.mark.parametrize(
    ("builder", "args", "kwargs"),
    [
        (category_list, ("1",), {}),
        (chronological_post_list, ("bad/id",), {}),
        (chronological_post_list, ("synthetic_alice",), {"category_no": -1}),
        (chronological_post_list, ("synthetic_alice",), {"category_no": True}),
        (chronological_post_list, ("synthetic_alice",), {"item_count": 0}),
        (chronological_post_list, ("synthetic_alice",), {"page": 0}),
        (public_buddies, ("synthetic_alice",), {"page": True}),
        (directory_post_list, (0,), {}),
        (directory_post_list, (1,), {"page": 0}),
        (directory_top_post_list, ("not-a-number",), {}),
        (post_list, ("synthetic_alice",), {"sort": "date"}),
        (post_list, ("synthetic_alice",), {"notices": 1}),
        (post_list, ("synthetic_alice",), {"sort": "popular", "notices": True}),
        (post_list, ("synthetic_alice",), {"sort": "popular", "page": 2}),
        (post_list, ("synthetic_alice",), {"notices": True, "category_no": 1}),
    ],
)
def test_phase3_builders_reject_invalid_boundaries_and_unsupported_combinations(
    builder, args, kwargs
):
    with pytest.raises(InvalidIdentifierError):
        builder(*args, **kwargs)


def test_phase3_request_specs_are_immutable_and_exclude_telemetry_endpoints():
    request = chronological_post_list("synthetic_alice", item_count=31)
    all_urls = {
        category_list("synthetic_alice").url,
        request.url,
        notice_post_list("synthetic_alice").url,
        popular_post_list("synthetic_alice").url,
        public_buddies("synthetic_alice").url,
        directory_list().url,
        directory_post_list(5).url,
        directory_top_post_list(5).url,
    }

    with pytest.raises(TypeError):
        request.params["itemCount"] = 1  # type: ignore[index]
    assert all("web_naver_view_log_json.json" not in url for url in all_urls)
    assert all("telemetry" not in url for url in all_urls)


def test_phase4_constants_preserve_non_derivable_cbox_contract():
    assert CBOX_POOL == "blogid"
    assert CBOX_OBJECT_ID == "{blog_no}_201_{log_no}"
    assert CBOX_OBJECT_ID.format(blog_no=20001, log_no=10001) == "20001_201_10001"


def test_post_tags_normalizes_a_post_url_into_the_measured_pc_host_request():
    request = post_tags("https://blog.naver.com/synthetic_alice/10001")

    assert request == RequestSpec(
        BLOG_TAG_LIST_INFO,
        {"blogId": "synthetic_alice", "logNo": "10001", "viewType": "S"},
    )


def test_in_blog_tag_search_omits_the_sort_parameter_the_endpoint_ignores():
    request = in_blog_tag_search("synthetic_alice", "coffee", page=2)

    assert request == RequestSpec(
        "https://m.blog.naver.com/api/blogs/synthetic_alice/search/tag",
        {"query": "coffee", "page": 2},
    )
    assert "sortType" not in request.params


@pytest.mark.parametrize(
    ("builder", "args", "kwargs"),
    [
        (post_html, ("synthetic_alice", 0), {}),
        (comments_info, ("synthetic_alice", 0), {}),
        (cbox_list, (0, 10001), {}),
        (cbox_list, (20001, 0), {}),
        (cbox_list, (20001, 10001), {"page": 0}),
        (cbox_list, (20001, 10001), {"page_size": 0}),
        (cbox_list, (20001, 10001), {"sort": "recent"}),
        (in_blog_search, ("synthetic_alice", ""), {}),
        (in_blog_search, ("synthetic_alice", "query"), {"page": 0}),
        (in_blog_search, ("synthetic_alice", "query"), {"sort": "recentdate"}),
        (in_blog_tag_search, ("synthetic_alice", ""), {}),
        (in_blog_tag_search, ("synthetic_alice", "query"), {"page": 0}),
        (mobile_search_post, ("",), {}),
        (mobile_search_post, ("query",), {"sort": "relevance"}),
        (mobile_search_post, ("query",), {"page": 0}),
        (mobile_search_post, ("query",), {"item_count": 31}),
        (mobile_search_post, ("query",), {"since": "2026-01-02", "until": "2026-01-01"}),
        (mobile_tag_search, ("",), {}),
        (mobile_tag_search, ("query",), {"item_count": 31}),
    ],
)
def test_phase4_builders_reject_invalid_identifiers_pages_counts_and_sorts(builder, args, kwargs):
    with pytest.raises(InvalidIdentifierError):
        builder(*args, **kwargs)


def test_endpoints_source_has_no_telemetry_builder():
    assert "web_naver_view_log_json.json" not in inspect.getsource(endpoints)
