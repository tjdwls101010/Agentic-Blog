import argparse
import json
from datetime import UTC, datetime

import pytest

import agentic_blog.cli as cli
from agentic_blog import __version__
from agentic_blog.errors import EXIT_CODES, RateLimitedError, exit_code_for
from agentic_blog.model import Blog, Category, Post, Topic
from agentic_blog.retrieve import RetrieveResult


def _post(log_no="1"):
    return {
        "logNo": int(log_no),
        "blogNo": 1,
        "blogId": "blog",
        "title": "한국어 제목",
        "content": "한국어 요약",
        "addDate": 1_700_000_000_000,
    }


def _page(items):
    """One m.blog search page — the envelope `search` (and `--type post`) now reads."""
    return {
        "isSuccess": True,
        "result": {
            "list": items,
            "currentPage": 1,
            "totalCount": 12_356_134,
            "totalPage": 411_872,
        },
    }


class FakeClient:
    def __init__(self):
        self.requests_made = 0
        self.remaining_requests = 1
        self.specs = []
        self.close_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.close_calls += 1

    def get_json(self, spec):
        self.requests_made += 1
        self.remaining_requests -= 1
        self.specs.append(spec)
        return _page([_post()])


def test_version_exits_successfully(capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(["--version"])
    assert raised.value.code == 0
    assert capsys.readouterr().out == f"agentic-blog {__version__}\n"


def test_catalog_stays_derived_from_handlers_and_parser():
    catalog = cli.build_catalog()
    catalog_commands = {command["name"]: command for command in catalog["commands"]}
    parser_commands = next(
        action.choices
        for action in cli.build_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )

    expected_commands = {
        "catalog",
        "schema",
        "search",
        "blog",
        "post",
        "posts",
        "buddies",
        "topics",
        "topic",
    }
    assert set(catalog_commands) == set(parser_commands) == set(cli._HANDLERS) == expected_commands
    assert set(catalog_commands) == set(cli._COMMAND_OUTPUT)
    assert catalog_commands["search"]["output"] == "Post | Blog (depends on --type)"
    assert {argument["name"] for argument in catalog_commands["search"]["arguments"]} >= {
        "query",
        "search_type",
        "sort",
        "since",
        "until",
        "format",
        "output",
        "limit",
        "raw",
    }
    assert catalog["exit_codes"] == {str(code): text for code, text in EXIT_CODES.items()}
    argument_names = {argument["name"] for argument in catalog_commands["search"]["arguments"]}
    assert {"no_redact", "verbose"} <= argument_names
    blog_flags = {
        flag for argument in catalog_commands["blog"]["arguments"] for flag in argument["flags"]
    }
    topics_flags = {
        flag for argument in catalog_commands["topics"]["arguments"] for flag in argument["flags"]
    }
    assert "--raw" in blog_flags
    assert "--limit" not in blog_flags
    assert {"--limit", "--raw"}.isdisjoint(topics_flags)
    posts_flags = {
        flag for argument in catalog_commands["posts"]["arguments"] for flag in argument["flags"]
    }
    assert {"--raw", "--tag"} <= posts_flags
    assert catalog_commands["catalog"]["arguments"] == []


def test_catalog_is_json_without_optional_flags(capsys):
    assert cli.main(["catalog"]) == 0
    output = capsys.readouterr()

    assert json.loads(output.out) == cli.build_catalog()
    assert output.err == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["search", " ", "--output", "unused.json"],
        ["search", "q", "--since", "2026-7-01"],
        ["search", "q", "--until", "20260701"],
        ["search", "q", "--since", "2026-07-02", "--until", "2026-07-01"],
    ],
)
def test_search_rejects_invalid_grammar_as_usage_errors(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)

    assert raised.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_search_writes_utf8_json_to_explicit_path_and_keeps_stdout_empty(
    monkeypatch, capsys, tmp_path
):
    fake = FakeClient()
    monkeypatch.setattr(cli, "ReadClient", lambda: fake)
    output = tmp_path / "결과.json"

    assert cli.main(["search", "커피", "--output", str(output), "--raw"]) == 0

    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert "1 posts" in stderr
    assert "stop reason: no_next_page" in stderr
    assert str(output) in stderr
    assert "한국어 제목" in output.read_text(encoding="utf-8")
    assert "\\u" not in output.read_text(encoding="utf-8")
    assert json.loads(output.read_text(encoding="utf-8"))[0]["raw"] == _post()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("under_score", "under-score"),
        ("mixed_한국어---ABC123!", "mixed-한국어-ABC123"),
        ("!___---", "search"),
        ("한국어", "한국어"),
    ],
)
def test_default_output_identifier_normalization(value, expected):
    assert cli._safe_identifier(value) == expected


@pytest.mark.parametrize("identifier", ["a" * 500, "한국어" * 200])
def test_default_output_filename_has_portable_byte_length(monkeypatch, tmp_path, identifier):
    monkeypatch.setattr(cli, "default_output_dir", lambda **kwargs: tmp_path)

    path = cli._output_path(
        argparse.Namespace(
            command="search", output=None, format="ndjson", data_dir=None, query=identifier
        )
    )

    assert len(path.name.encode("utf-8")) <= cli._COMPONENT_BYTE_LIMIT


@pytest.mark.parametrize("shared_prefix", ["a" * 500, "한국어" * 200])
def test_truncated_default_identifiers_include_stable_distinct_digests(shared_prefix):
    first = cli._safe_identifier(f"{shared_prefix}one", max_bytes=100)
    second = cli._safe_identifier(f"{shared_prefix}two", max_bytes=100)

    assert first == cli._safe_identifier(f"{shared_prefix}one", max_bytes=100)
    assert first != second
    assert len(first.rsplit("-", 1)[-1]) == cli._TRUNCATION_DIGEST_LENGTH


def test_search_default_path_is_data_dir_scoped_and_korean_safe(monkeypatch, capsys, tmp_path):
    fake = FakeClient()
    monkeypatch.setattr(cli, "ReadClient", lambda: fake)
    output_dir = tmp_path / "output"
    monkeypatch.setattr(cli, "default_output_dir", lambda **kwargs: output_dir)

    assert cli.main(["search", "한국어 커피", "--format", "ndjson"]) == 0

    stdout, stderr = capsys.readouterr()
    files = list(output_dir.glob("search-한국어-커피-*.ndjson"))
    assert stdout == ""
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["log_no"] == "1"
    assert record["title"] == "한국어 제목"
    assert "raw" not in record
    assert "Saved to" in stderr


def test_search_default_path_honors_data_dir(monkeypatch, tmp_path):
    def output_dir(*, data_dir_override):
        assert data_dir_override == tmp_path / "data"
        return tmp_path / "scoped-output"

    monkeypatch.setattr(cli, "default_output_dir", output_dir)
    monkeypatch.setattr(cli, "ReadClient", FakeClient)

    assert cli.main(["search", "coffee", "--data-dir", str(tmp_path / "data")]) == 0
    assert len(list((tmp_path / "scoped-output").glob("search-coffee-*.json"))) == 1


@pytest.mark.parametrize(
    ("hostile", "escaped"),
    [
        ("\x80", "\\x80"),
        ("\u202e", "\\u202e"),
        ("\u200d", "\\u200d"),
        ("\n", "\\x0a"),
        ("\x1b", "\\x1b"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ],
)
def test_search_writes_empty_output_and_escapes_hostile_explicit_paths(
    monkeypatch, capsys, tmp_path, hostile, escaped
):
    class EmptyClient(FakeClient):
        def get_json(self, spec):
            self.requests_made += 1
            self.remaining_requests -= 1
            return _page([])

    monkeypatch.setattr(cli, "ReadClient", EmptyClient)
    output = tmp_path / f"결과{hostile}name.json"

    assert cli.main(["search", "coffee", "--output", str(output)]) == 0

    _, stderr = capsys.readouterr()
    assert json.loads(output.read_text(encoding="utf-8")) == []
    assert f"결과{hostile}name.json" not in stderr
    assert escaped in stderr
    assert "결과" in stderr


def test_search_default_path_remains_control_safe(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "ReadClient", FakeClient)
    output_dir = tmp_path / "defaults"
    monkeypatch.setattr(cli, "default_output_dir", lambda **kwargs: output_dir)

    assert cli.main(["search", "\x1b[31m\ncoffee"]) == 0

    capsys.readouterr()
    default_path = next(output_dir.iterdir())
    assert all(ord(character) >= 32 and ord(character) != 127 for character in default_path.name)


def test_search_write_failures_propagate(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "ReadClient", FakeClient)
    monkeypatch.setattr(
        cli, "_write_results", lambda *args: (_ for _ in ()).throw(OSError("disk full"))
    )

    with pytest.raises(OSError, match="disk full"):
        cli.main(["search", "coffee", "--output", str(tmp_path / "result.json")])


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "q", "--type", "id", "--sort", "sim"],
        ["search", "q", "--type", "id", "--since", "2026-07-01"],
        ["search", "q", "--type", "blog", "--until", "2026-07-01"],
        ["search", "q", "--limit", "-1"],
    ],
)
def test_search_invalid_combinations_are_usage_errors(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_usage_errors_leave_exit_two_unassigned(capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main([])
    assert raised.value.code == 1
    assert 2 not in EXIT_CODES
    assert "required: command" in capsys.readouterr().err


def test_search_malformed_card_exits_four_with_a_redacted_typed_diagnostic(monkeypatch, capsys):
    class MalformedClient(FakeClient):
        def get_json(self, spec):
            self.requests_made += 1
            self.remaining_requests -= 1
            self.specs.append(spec)
            return _page([{**_post(), "title": {"email": "secret@example.com"}}])

    monkeypatch.setattr(cli, "ReadClient", MalformedClient)

    assert cli.main(["search", "coffee", "--verbose"]) == 4

    stderr = capsys.readouterr().err
    assert stderr.startswith(
        "EnvelopeParseError: response envelope drift at response.result.list[0]"
    )
    assert "secret@example.com" not in stderr


def test_typed_errors_keep_the_documented_exit_code(monkeypatch, capsys):
    error = RateLimitedError("blocked")
    monkeypatch.setitem(cli._HANDLERS, "catalog", lambda args: (_ for _ in ()).throw(error))

    assert exit_code_for(error) == 3
    assert cli.main(["catalog"]) == 3
    assert capsys.readouterr().err == "blocked\n"


@pytest.mark.parametrize(
    ("argv", "retrieval_name"),
    [
        (["search", "query"], "search"),
        (["blog", "blog-id"], "fetch_blog"),
        (["post", "blog-id", "1"], "fetch_post"),
        (["posts", "blog-id"], "fetch_posts"),
        (["buddies", "blog-id"], "fetch_buddies"),
        (["topics"], "fetch_topics"),
        (["topic", "9"], "fetch_topic"),
    ],
)
def test_network_handlers_close_owned_clients_on_success_and_typed_error(
    monkeypatch, tmp_path, argv, retrieval_name
):
    success_client = FakeClient()
    monkeypatch.setattr(cli, "ReadClient", lambda: success_client)
    monkeypatch.setattr(
        cli,
        retrieval_name,
        lambda *args, **kwargs: RetrieveResult([], "no_matches", requests_made=0),
    )

    output = tmp_path / "result.json"
    assert cli.main([*argv, "--output", str(output)]) == 0
    assert success_client.requests_made == 0
    assert success_client.close_calls == 1

    error_client = FakeClient()
    monkeypatch.setattr(cli, "ReadClient", lambda: error_client)

    def fail(*args, **kwargs):
        raise RateLimitedError("blocked")

    monkeypatch.setattr(cli, retrieval_name, fail)
    assert cli.main([*argv, "--output", str(output)]) == 3
    assert error_client.requests_made == 0
    assert error_client.close_calls == 1


def test_read_diagnostic_flags_are_truthful(monkeypatch, capsys):
    error = RateLimitedError(
        "blocked https://blogimgs.pstatic.net/image.jpg?signature=synthetic-secret"
    )
    monkeypatch.setitem(cli._HANDLERS, "search", lambda args: (_ for _ in ()).throw(error))

    assert cli.main(["search", "q"]) == 3
    assert capsys.readouterr().err == "blocked https://blogimgs.pstatic.net/image.jpg\n"

    assert cli.main(["search", "q", "--no-redact"]) == 3
    unredacted = capsys.readouterr().err
    assert "WARNING: --no-redact" in unredacted
    assert "signature=synthetic-secret" in unredacted

    assert cli.main(["search", "q", "--verbose"]) == 3
    assert capsys.readouterr().err.startswith("RateLimitedError: blocked ")


def test_internal_handler_defects_propagate(monkeypatch):
    monkeypatch.setitem(
        cli._HANDLERS, "catalog", lambda args: (_ for _ in ()).throw(RuntimeError("defect"))
    )
    with pytest.raises(RuntimeError, match="defect"):
        cli.main(["catalog"])


@pytest.mark.parametrize(
    "argv",
    [
        ["posts", "blog", "--query", "later-phase", "--category", "1"],
        ["posts", "blog", "--category", "-1"],
        ["posts", "blog", "--notices", "--sort", "popular"],
        ["blog", "blog", "--limit", "1"],
        ["topics", "--limit", "1"],
        ["topics", "--raw"],
        ["topic", "5", "--top", "--query", "later-phase"],
    ],
)
def test_phase3_cli_rejects_unsupported_or_incompatible_grammar(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)

    assert raised.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_posts_query_still_rejects_incompatible_grammar_before_client_creation(monkeypatch):
    monkeypatch.setattr(
        cli,
        "ReadClient",
        lambda: pytest.fail("query grammar validation must run before client creation"),
    )

    with pytest.raises(SystemExit) as raised:
        cli.main(["posts", "blog", "--query", "coffee", "--notices"])

    assert raised.value.code == 1


def test_phase3_commands_are_catalogued_with_concrete_output_types():
    commands = {command["name"]: command["output"] for command in cli.build_catalog()["commands"]}

    assert {name: commands[name] for name in ("blog", "posts", "buddies", "topics", "topic")} == {
        "blog": "Blog",
        "posts": "Post",
        "buddies": "Blog",
        "topics": "Topic",
        "topic": "Post",
    }


@pytest.mark.parametrize(
    (
        "argv",
        "retrieval_name",
        "expected_args",
        "expected_kwargs",
        "item",
        "stop_reason",
        "noun",
        "range_text",
    ),
    [
        (
            ["blog", "blog-id", "--raw"],
            "fetch_blog",
            ("blog-id",),
            {"raw": True},
            Blog(
                blog_id="blog-id",
                categories=[Category(category_no="7", name="Category")],
            ),
            "single_target",
            "blogs",
            "n/a..n/a",
        ),
        (
            ["posts", "blog-id", "--category", "7", "--limit", "3", "--raw"],
            "fetch_posts",
            ("blog-id",),
            {
                "category": 7,
                "sort": "recent",
                "notices": False,
                "query": None,
                "tag": None,
                "limit": 3,
                "raw": True,
            },
            Post(
                log_no="1",
                blog_id="blog-id",
                blog_no="2",
                title="Recent",
                created_at=datetime(2026, 7, 1, tzinfo=UTC),
            ),
            "no_next_page",
            "posts",
            "2026-07-01T00:00:00+00:00..2026-07-01T00:00:00+00:00",
        ),
        (
            ["posts", "blog-id", "--sort", "popular", "--limit", "2", "--raw"],
            "fetch_posts",
            ("blog-id",),
            {
                "category": 0,
                "sort": "popular",
                "notices": False,
                "query": None,
                "tag": None,
                "limit": 2,
                "raw": True,
            },
            Post(
                log_no="2",
                blog_id="blog-id",
                blog_no="2",
                title="Popular",
                created_at=datetime(2026, 7, 2, tzinfo=UTC),
            ),
            "no_next_page",
            "posts",
            "2026-07-02T00:00:00+00:00..2026-07-02T00:00:00+00:00",
        ),
        (
            ["posts", "blog-id", "--notices", "--limit", "1", "--raw"],
            "fetch_posts",
            ("blog-id",),
            {
                "category": 0,
                "sort": "recent",
                "notices": True,
                "query": None,
                "tag": None,
                "limit": 1,
                "raw": True,
            },
            Post(
                log_no="3",
                blog_id="blog-id",
                blog_no="2",
                title="Notice",
                created_at=datetime(2026, 7, 3, tzinfo=UTC),
            ),
            "no_next_page",
            "posts",
            "2026-07-03T00:00:00+00:00..2026-07-03T00:00:00+00:00",
        ),
        (
            ["buddies", "blog-id", "--limit", "2", "--raw"],
            "fetch_buddies",
            ("blog-id",),
            {"limit": 2, "raw": True},
            Blog(blog_id="buddy-id", blog_name="Buddy"),
            "no_next_page",
            "blogs",
            "n/a..n/a",
        ),
        (
            ["topics"],
            "fetch_topics",
            (),
            {},
            Topic(seq="9", name="Topic", group_name="Group"),
            "single_target",
            "topics",
            "n/a..n/a",
        ),
        (
            ["topic", "9", "--limit", "2", "--raw"],
            "fetch_topic",
            ("9",),
            {"top": False, "limit": 2, "raw": True},
            Post(
                log_no="4",
                blog_id="blog-id",
                blog_no="2",
                title="Chronological",
                created_at=datetime(2026, 7, 4, tzinfo=UTC),
            ),
            "no_next_page",
            "posts",
            "2026-07-04T00:00:00+00:00..2026-07-04T00:00:00+00:00",
        ),
        (
            ["topic", "9", "--top", "--limit", "2", "--raw"],
            "fetch_topic",
            ("9",),
            {"top": True, "limit": 2, "raw": True},
            Post(
                log_no="5",
                blog_id="blog-id",
                blog_no="2",
                title="Top",
                created_at=datetime(2026, 7, 5, tzinfo=UTC),
            ),
            "no_next_page",
            "posts",
            "2026-07-05T00:00:00+00:00..2026-07-05T00:00:00+00:00",
        ),
    ],
)
def test_phase3_handlers_forward_arguments_and_write_schema_objects(
    monkeypatch,
    capsys,
    tmp_path,
    argv,
    retrieval_name,
    expected_args,
    expected_kwargs,
    item,
    stop_reason,
    noun,
    range_text,
):
    client = FakeClient()
    calls = []

    def retrieve(received_client, *received_args, **received_kwargs):
        calls.append((received_client, received_args, received_kwargs))
        return RetrieveResult([item], stop_reason, requests_made=1)

    output = tmp_path / "result\x1b.json"
    monkeypatch.setattr(cli, "ReadClient", lambda: client)
    monkeypatch.setattr(cli, retrieval_name, retrieve)

    assert cli.main([*argv, "--output", str(output)]) == 0

    stdout, stderr = capsys.readouterr()
    assert calls == [(client, expected_args, expected_kwargs)]
    assert json.loads(output.read_text(encoding="utf-8")) == [item.to_dict()]
    assert stdout == ""
    escaped_output = str(output).replace(chr(27), "\\x1b")
    assert stderr == (
        f"1 {noun}, range {range_text}, stop reason: {stop_reason}. Saved to {escaped_output}\n"
    )
    assert stderr.count("\n") == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["post", "https://blog.naver.com/blog/1", "--comment-limit", "-1"],
        ["posts", "blog", "--query", "q", "--sort", "popular"],
        ["posts", "blog", "--query", "q", "--category", "1"],
    ],
)
def test_phase4_cli_rejects_invalid_post_and_query_combinations(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)

    assert raised.value.code == 1
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["posts", "blog", "--tag", ""],
        ["posts", "blog", "--tag", "coffee", "--query", "tea"],
        ["posts", "blog", "--tag", "coffee", "--category", "1"],
        ["posts", "blog", "--tag", "coffee", "--sort", "popular"],
        ["posts", "blog", "--tag", "coffee", "--notices"],
    ],
)
def test_posts_tag_rejects_every_incompatible_listing_flag_before_client_creation(
    argv, monkeypatch, capsys
):
    monkeypatch.setattr(
        cli,
        "ReadClient",
        lambda: pytest.fail("tag grammar validation must run before client creation"),
    )

    with pytest.raises(SystemExit) as raised:
        cli.main(argv)

    assert raised.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_posts_tag_handler_forwards_the_tag_without_a_sort_control(
    monkeypatch, capsys, tmp_path
) -> None:
    client = FakeClient()
    calls = []

    def retrieve(received_client, *received_args, **received_kwargs):
        calls.append((received_client, received_args, received_kwargs))
        return RetrieveResult([], "no_matches", requests_made=1)

    output = tmp_path / "tag.json"
    monkeypatch.setattr(cli, "ReadClient", lambda: client)
    monkeypatch.setattr(cli, "fetch_posts", retrieve)

    assert cli.main(["posts", "blog", "--tag", "coffee", "--output", str(output)]) == 0
    assert calls == [
        (
            client,
            ("blog",),
            {
                "category": 0,
                "sort": "recent",
                "notices": False,
                "query": None,
                "tag": "coffee",
                "limit": None,
                "raw": False,
            },
        )
    ]
    assert json.loads(output.read_text()) == []
    assert "0 posts" in capsys.readouterr().err


def test_phase4_post_handler_accepts_two_tokens_and_forwards_comment_options(
    monkeypatch, capsys, tmp_path
):
    client = FakeClient()
    calls = []
    item = Post(log_no="1", blog_id="blog", title="Post", comments=[])

    def retrieve(received_client, *received_args, **received_kwargs):
        calls.append((received_client, received_args, received_kwargs))
        return RetrieveResult([item], "single_target", requests_made=2)

    output = tmp_path / "post.json"
    monkeypatch.setattr(cli, "ReadClient", lambda: client)
    monkeypatch.setattr(cli, "fetch_post", retrieve)

    assert (
        cli.main(
            [
                "post",
                "blog",
                "1",
                "--no-comments",
                "--comment-sort",
                "favorite",
                "--comment-limit",
                "2",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert calls == [
        (
            client,
            ("blog", "1"),
            {"comments": False, "comment_sort": "favorite", "comment_limit": 2},
        )
    ]
    assert json.loads(output.read_text(encoding="utf-8")) == [item.to_dict()]
    assert "1 posts" in capsys.readouterr().err
