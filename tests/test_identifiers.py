import pytest
from conftest import load_fixture

from agentic_blog.errors import (
    EXIT_CODES,
    AgenticBlogError,
    BodyParseError,
    EnvelopeParseError,
    InvalidIdentifierError,
    NotFoundError,
    RateLimitedError,
    TargetUnavailableError,
    exit_code_for,
)
from agentic_blog.identifiers import (
    BlogRef,
    PostRef,
    parse_blog_ref,
    parse_directory_seq,
    parse_post_ref,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("synthetic_alice", BlogRef("synthetic_alice")),
        ("https://blog.naver.com/synthetic_alice", BlogRef("synthetic_alice")),
        ("https://m.blog.naver.com/synthetic_alice", BlogRef("synthetic_alice")),
    ],
)
def test_parse_blog_ref_accepts_documented_spellings(value, expected):
    assert parse_blog_ref(value) == expected


@pytest.mark.parametrize(
    ("value", "log_no", "expected"),
    [
        (
            "https://blog.naver.com/synthetic_alice/123456789",
            None,
            PostRef("synthetic_alice", "123456789"),
        ),
        (
            "https://m.blog.naver.com/synthetic_alice/123456789",
            None,
            PostRef("synthetic_alice", "123456789"),
        ),
        (
            "https://blog.naver.com/PostView.naver?blogId=synthetic_alice&logNo=123456789",
            None,
            PostRef("synthetic_alice", "123456789"),
        ),
        ("synthetic_alice", "123456789", PostRef("synthetic_alice", "123456789")),
    ],
)
def test_parse_post_ref_accepts_documented_spellings(value, log_no, expected):
    assert parse_post_ref(value, log_no) == expected


@pytest.mark.parametrize(
    "value",
    [
        "123456789",
        "https://example.com/synthetic_alice",
        "https://example.com/synthetic_alice/123456789",
        "https://blog.naver.com/synthetic_alice/not-a-log-no",
        "https://blog.naver.com/PostView.naver?blogId=synthetic_alice",
    ],
)
def test_parse_post_ref_rejects_bare_log_numbers_and_invalid_references(value):
    with pytest.raises(InvalidIdentifierError):
        parse_post_ref(value)


@pytest.mark.parametrize(
    "value",
    ["https://example.com/synthetic_alice", "https://blog.naver.com/synthetic_alice/123456789"],
)
def test_parse_blog_ref_rejects_non_blog_references(value):
    with pytest.raises(InvalidIdentifierError):
        parse_blog_ref(value)


@pytest.mark.parametrize(("value", "expected"), [("1", 1), (123, 123), ("123456789", 123456789)])
def test_parse_directory_seq_accepts_positive_decimal_values(value, expected):
    assert parse_directory_seq(value) == expected


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "topic", ""])
def test_parse_directory_seq_rejects_invalid_values(value):
    with pytest.raises(InvalidIdentifierError):
        parse_directory_seq(value)


@pytest.mark.parametrize(
    ("parser", "value"),
    [
        (parse_blog_ref, "https://[::1"),
        (parse_blog_ref, "https://blog.naver.com：443/synthetic_alice"),
        (parse_blog_ref, "https://blog.naver.com.evil.example/synthetic_alice"),
        (parse_post_ref, "https://attacker@blog.naver.com/synthetic_alice/123456789"),
        (parse_post_ref, "https://blog.naver.com:invalid/synthetic_alice/123456789"),
    ],
)
def test_url_authority_parser_failures_are_typed(parser, value):
    with pytest.raises(InvalidIdentifierError):
        parser(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://blog.naver.com/PostView.naver?blogId=synthetic_alice&blogId=other&logNo=123",
        "https://blog.naver.com/PostView.naver?blogId=synthetic_alice&logNo=123&logNo=456",
        "https://blog.naver.com/PostView.naver?blogId=synthetic_alice&logNo=123&modal=x&modal=y",
        "https://blog.naver.com/PostView.naver?blogId=synthetic_alice&logNo=123&",
    ],
)
def test_parse_post_ref_rejects_ambiguous_postview_queries(value):
    with pytest.raises(InvalidIdentifierError):
        parse_post_ref(value)


def test_parse_post_ref_rejects_conflicting_explicit_log_number():
    with pytest.raises(InvalidIdentifierError):
        parse_post_ref(PostRef("synthetic_alice", "123"), "456")


@pytest.mark.parametrize(
    ("parser", "value"),
    [(parse_blog_ref, 123), (parse_post_ref, 123), (parse_directory_seq, True)],
)
def test_identifier_type_errors_are_typed(parser, value):
    with pytest.raises(InvalidIdentifierError):
        parser(value)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (AgenticBlogError(), 1),
        (InvalidIdentifierError(), 1),
        (RateLimitedError(), 3),
        (EnvelopeParseError(), 4),
        (BodyParseError(), 4),
        (NotFoundError(), 5),
        (TargetUnavailableError("private"), 5),
    ],
)
def test_every_typed_error_has_an_exit_code_in_the_exported_table(error, code):
    assert exit_code_for(error) == code
    assert code in EXIT_CODES


def test_exit_code_table_preserves_the_documented_unassigned_code():
    assert EXIT_CODES == {
        0: "success",
        1: "usage error, invalid identifier, or unexpected failure",
        3: "blocked or throttled by Naver",
        4: "Naver response structure changed",
        5: "target does not exist or is unavailable anonymously",
    }
    assert 2 not in EXIT_CODES


@pytest.mark.parametrize(
    "name",
    [
        "../outside.json",
        "nested/fixture.json",
        r"nested\fixture.json",
        "/tmp/fixture.json",
        "",
        ".",
        None,
    ],
)
def test_load_fixture_rejects_paths_and_non_filenames(name):
    with pytest.raises(ValueError):
        load_fixture(name)
