"""Command-line interface for the implemented anonymous read surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .client import ReadClient
from .config import default_output_dir
from .errors import EXIT_CODES, AgenticBlogError, exit_code_for
from .model import Blog, Category, Comment, Media, Post, Topic, json_schema, schema_fields
from .redact import redact_diagnostic
from .retrieve import (
    fetch_blog,
    fetch_buddies,
    fetch_post,
    fetch_posts,
    fetch_topic,
    fetch_topics,
    search,
)

CATALOG_VERSION = 1
_COMPONENT_BYTE_LIMIT = 240
_TRUNCATION_DIGEST_LENGTH = 12
_COMMAND_OUTPUT = {
    "catalog": None,
    "schema": None,
    "search": "Post | Blog (depends on --type)",
    "post": "Post",
    "blog": "Blog",
    "posts": "Post",
    "buddies": "Blog",
    "topics": "Topic",
    "topic": "Post",
}


class _ArgumentParser(argparse.ArgumentParser):
    """Keep exit 2 unassigned by turning parser errors into exit 1."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {redact_diagnostic(message)}\n")


class _StoreExplicit(argparse.Action):
    """Store an option while retaining whether the caller supplied it."""

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        setattr(namespace, self.dest, values)
        setattr(namespace, f"{self.dest}_supplied", True)


def _date_arg(value: str) -> date:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD") from error


def _add_common_read_flags(
    parser: argparse.ArgumentParser, *, limit: bool = True, raw: bool = True
) -> None:
    parser.add_argument("--format", choices=("json", "ndjson"), default="json")
    parser.add_argument("--output", type=Path)
    if limit:
        parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--data-dir", type=Path)
    if raw:
        parser.add_argument("--raw", action="store_true")
    parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Do not redact diagnostic messages.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Include the error class in diagnostics.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the live parser from which the catalog is derived."""
    parser = _ArgumentParser(
        prog="agentic-blog",
        description="Read-only Naver Blog crawler.",
    )
    parser.add_argument("--version", action="version", version=f"agentic-blog {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("catalog", help="Emit the CLI catalog as JSON (offline).")

    schema_parser = subparsers.add_parser(
        "schema", help="Print the generated output schema (offline)."
    )
    schema_parser.add_argument(
        "--json", action="store_true", help="Emit JSON Schema draft 2020-12."
    )

    search_parser = subparsers.add_parser("search", help="Search Naver Blog posts or blogs.")
    search_parser.add_argument("query")
    search_parser.add_argument(
        "--type", dest="search_type", choices=("post", "blog", "id"), default="post"
    )
    search_parser.add_argument(
        "--sort", choices=("sim", "date"), default="sim", action=_StoreExplicit
    )
    search_parser.set_defaults(sort_supplied=False)
    search_parser.add_argument("--since", type=_date_arg, help="Server-side lower date bound.")
    search_parser.add_argument("--until", type=_date_arg, help="Server-side upper date bound.")
    _add_common_read_flags(search_parser)

    blog_parser = subparsers.add_parser("blog", help="Read one blog's public category tree.")
    blog_parser.add_argument("blog_id")
    _add_common_read_flags(blog_parser, limit=False)
    post_parser = subparsers.add_parser("post", help="Read one public post and its comments.")
    post_parser.add_argument("post_ref")
    post_parser.add_argument("log_no", nargs="?")
    post_parser.add_argument("--no-comments", dest="comments", action="store_false")
    post_parser.set_defaults(comments=True)
    post_parser.add_argument("--comment-sort", choices=("new", "favorite"), default="new")
    post_parser.add_argument("--comment-limit", type=int, default=None)
    _add_common_read_flags(post_parser, limit=False, raw=False)

    posts_parser = subparsers.add_parser("posts", help="Read public posts from one blog.")
    posts_parser.add_argument("blog_id")
    posts_parser.add_argument("--category", type=int, default=0)
    posts_parser.add_argument("--sort", choices=("recent", "popular"), default="recent")
    posts_parser.add_argument("--notices", action="store_true")
    posts_parser.add_argument("--query")
    _add_common_read_flags(posts_parser)

    buddies_parser = subparsers.add_parser("buddies", help="Read one blog's public buddies.")
    buddies_parser.add_argument("blog_id")
    _add_common_read_flags(buddies_parser)

    topics_parser = subparsers.add_parser("topics", help="Read the public directory topics.")
    _add_common_read_flags(topics_parser, limit=False, raw=False)

    topic_parser = subparsers.add_parser("topic", help="Read posts from one directory topic.")
    topic_parser.add_argument("directory_seq")
    topic_parser.add_argument("--top", action="store_true")
    _add_common_read_flags(topic_parser)
    return parser


def _argument_type(action: argparse.Action) -> str:
    if isinstance(action, argparse._StoreTrueAction | argparse._StoreFalseAction):
        return "boolean"
    if action.type is None:
        return "string"
    if isinstance(action.type, str):
        return action.type
    return getattr(action.type, "__name__", type(action.type).__name__)


def _argument_catalog(parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    arguments = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        arguments.append(
            {
                "name": action.dest,
                "flags": list(action.option_strings),
                "positional": not action.option_strings,
                "required": action.required,
                "default": action.default,
                "type": _argument_type(action),
                "choices": list(action.choices) if action.choices else None,
                "is_flag": isinstance(
                    action, argparse._StoreTrueAction | argparse._StoreFalseAction
                ),
                "help": action.help,
            }
        )
    return arguments


def build_catalog() -> dict[str, Any]:
    """Return a catalog derived from the parser and canonical error mapping."""
    parser = build_parser()
    action = next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction))
    summaries = {choice.dest: choice.help or "" for choice in action._choices_actions}
    commands = [
        {
            "name": name,
            "help": subparser.description or summaries.get(name, ""),
            "output": _COMMAND_OUTPUT.get(name),
            "arguments": _argument_catalog(subparser),
        }
        for name, subparser in action.choices.items()
    ]
    return {
        "catalog_version": CATALOG_VERSION,
        "package": "agentic-blog",
        "command": "agentic-blog",
        "version": __version__,
        "commands": commands,
        "exit_codes": {str(code): description for code, description in EXIT_CODES.items()},
        "output_schema": "agentic-blog schema --json",
    }


def _print_schema_fields() -> None:
    for model in (Post, Blog, Topic, Comment, Media, Category):
        print(f"{model.__name__}:")
        for field in schema_fields(model):
            print(f"  {field['name']} : {field['type']}")
            print(f"      {field['description']}")
        print()


def _cmd_catalog(args: argparse.Namespace) -> int:
    del args
    print(json.dumps(build_catalog(), ensure_ascii=False, indent=2))
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(json_schema(), ensure_ascii=False, indent=2))
    else:
        _print_schema_fields()
    return 0


def _safe_identifier(value: str, *, max_bytes: int | None = None) -> str:
    stem = "".join(character if character.isalnum() else "-" for character in value)
    stem = re.sub(r"-+", "-", stem).strip("-") or "search"
    if max_bytes is None or len(stem.encode("utf-8")) <= max_bytes:
        return stem

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:_TRUNCATION_DIGEST_LENGTH]
    suffix = f"-{digest}"
    retained = []
    used_bytes = 0
    for character in stem:
        character_bytes = len(character.encode("utf-8"))
        if used_bytes + character_bytes > max_bytes - len(suffix):
            break
        retained.append(character)
        used_bytes += character_bytes
    return f"{''.join(retained).rstrip('-')}{suffix}"


def _output_path(args: argparse.Namespace) -> Path:
    if args.output is not None:
        return args.output
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    extension = "ndjson" if args.format == "ndjson" else "json"
    identifier = (
        getattr(args, "query", None)
        or getattr(args, "blog_id", None)
        or getattr(args, "directory_seq", None)
        or args.command
    )
    identifier_bytes = _COMPONENT_BYTE_LIMIT - len(
        f"{args.command}--{timestamp}.{extension}".encode()
    )
    safe_identifier = _safe_identifier(identifier, max_bytes=identifier_bytes)
    return default_output_dir(data_dir_override=args.data_dir) / (
        f"{args.command}-{safe_identifier}-{timestamp}.{extension}"
    )


def _write_results(path: Path, items: list[Post | Blog | Topic], output_format: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [item.to_dict() for item in items]
    with path.open("w", encoding="utf-8", newline="\n") as output:
        if output_format == "ndjson":
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False))
                output.write("\n")
        else:
            json.dump(records, output, ensure_ascii=False, indent=2)
            output.write("\n")


def _summary_path(path: Path) -> str:
    def escape(character: str) -> str:
        codepoint = ord(character)
        if unicodedata.category(character) in {"Cc", "Cf"} or character in "\u2028\u2029":
            if codepoint <= 0xFF:
                return f"\\x{codepoint:02x}"
            if codepoint <= 0xFFFF:
                return f"\\u{codepoint:04x}"
            return f"\\U{codepoint:08x}"
        return character

    return "".join(escape(character) for character in str(path))


def _write_command_result(args: argparse.Namespace, result, noun: str) -> int:
    path = _output_path(args)
    _write_results(path, result.items, args.format)
    dates = [item.created_at for item in result.items if isinstance(item, Post) and item.created_at]
    range_text = f"{min(dates).isoformat()}..{max(dates).isoformat()}" if dates else "n/a..n/a"
    print(
        f"{len(result.items)} {noun}, range {range_text}, stop reason: {result.stop_reason}. "
        f"Saved to {_summary_path(path)}",
        file=sys.stderr,
    )
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    with ReadClient() as client:
        return _write_command_result(
            args,
            search(
                client,
                args.query,
                search_type=args.search_type,
                sort=args.sort if args.search_type != "id" else None,
                since=args.since,
                until=args.until,
                limit=args.limit,
                raw=args.raw,
            ),
            "posts" if args.search_type == "post" else "blogs",
        )


def _cmd_blog(args: argparse.Namespace) -> int:
    with ReadClient() as client:
        return _write_command_result(args, fetch_blog(client, args.blog_id, raw=args.raw), "blogs")


def _cmd_post(args: argparse.Namespace) -> int:
    with ReadClient() as client:
        return _write_command_result(
            args,
            fetch_post(
                client,
                args.post_ref,
                args.log_no,
                comments=args.comments,
                comment_sort=args.comment_sort,
                comment_limit=args.comment_limit,
            ),
            "posts",
        )


def _cmd_posts(args: argparse.Namespace) -> int:
    with ReadClient() as client:
        return _write_command_result(
            args,
            fetch_posts(
                client,
                args.blog_id,
                category=args.category,
                sort=args.sort,
                notices=args.notices,
                query=args.query,
                limit=args.limit,
                raw=args.raw,
            ),
            "posts",
        )


def _cmd_buddies(args: argparse.Namespace) -> int:
    with ReadClient() as client:
        return _write_command_result(
            args, fetch_buddies(client, args.blog_id, limit=args.limit, raw=args.raw), "blogs"
        )


def _cmd_topics(args: argparse.Namespace) -> int:
    with ReadClient() as client:
        return _write_command_result(args, fetch_topics(client), "topics")


def _cmd_topic(args: argparse.Namespace) -> int:
    with ReadClient() as client:
        return _write_command_result(
            args,
            fetch_topic(client, args.directory_seq, top=args.top, limit=args.limit, raw=args.raw),
            "posts",
        )


_HANDLERS = {
    "catalog": _cmd_catalog,
    "schema": _cmd_schema,
    "search": _cmd_search,
    "blog": _cmd_blog,
    "post": _cmd_post,
    "posts": _cmd_posts,
    "buddies": _cmd_buddies,
    "topics": _cmd_topics,
    "topic": _cmd_topic,
}


def _validate_read_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if hasattr(args, "limit") and args.limit is not None and args.limit < 0:
        parser.error("--limit must be a non-negative integer")
    if args.command == "post":
        if args.comment_limit is not None and args.comment_limit < 0:
            parser.error("--comment-limit must be a non-negative integer")
        return
    if args.command != "search":
        if args.command == "posts":
            if args.category < 0:
                parser.error("--category must be a non-negative integer")
            if args.notices and args.sort != "recent":
                parser.error("--notices does not support --sort popular")
            if (args.notices or args.sort == "popular") and args.category != 0:
                parser.error("--category is not supported with --notices or --sort popular")
            if args.query is not None:
                if not args.query.strip():
                    parser.error("--query must be non-empty")
                if args.category != 0:
                    parser.error("--query does not support --category")
                if args.sort != "recent":
                    parser.error("--query does not support --sort popular")
                if args.notices:
                    parser.error("--query does not support --notices")
                if args.raw:
                    parser.error("--query does not support --raw")
        return
    if not args.query.strip():
        parser.error("query must be non-empty")
    if args.since is not None and args.until is not None and args.since > args.until:
        parser.error("--since must not be later than --until")
    if args.search_type == "id" and (
        args.sort_supplied or args.since is not None or args.until is not None
    ):
        parser.error("--sort, --since, and --until are not supported for --type id")
    if args.search_type != "post" and (args.since is not None or args.until is not None):
        parser.error("--since and --until are only supported for --type post")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return its exit status for console-script use."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_read_args(parser, args)
    if getattr(args, "no_redact", False):
        print("WARNING: --no-redact disables diagnostic redaction.", file=sys.stderr)
    try:
        return _HANDLERS[args.command](args)
    except AgenticBlogError as error:
        message = error.diagnostic_message(
            redact=not getattr(args, "no_redact", False),
            max_length=4096 if getattr(args, "verbose", False) else 240,
        )
        if getattr(args, "verbose", False):
            message = f"{type(error).__name__}: {message}"
        print(message, file=sys.stderr)
        return exit_code_for(error)
