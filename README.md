# Agentic Blog

Agentic Blog is a small, read-only command-line reader for **public Naver Blog** content. It is designed for focused retrieval: search public blogs and posts, inspect a blog and its category tree, list posts, read a post body and comments, browse topics, and view public buddies (neighbours).

It is anonymous by design. There is no account, login, API key, browser, cookie jar, profile, session, `setup`, `status`, or `doctor` command. The package uses plain HTTPS requests to Naver's public surfaces and does not attempt to access private or neighbour-only content.

> **Read [DISCLAIMER.md](DISCLAIMER.md) before use.** This is an unofficial tool. Public availability does not remove your responsibility to use the service and retrieved data lawfully and respectfully.

## Install

Requires Python 3.11 or newer.

```bash
python -m pip install .
agentic-blog --version
```

Install a reviewed wheel with `python -m pip install /path/to/agentic_blog-0.1.0-py3-none-any.whl`.
This release-ready worktree does not claim that version 0.1.0 has been published to PyPI.

The runtime dependency set is intentionally limited to `httpx`, `platformdirs`, and `lxml`. No browser dependency or optional browser extra is provided.

## Quick start

Search public posts and save up to five results:

```bash
agentic-blog search "커피" --limit 5
```

The command writes UTF-8 JSON to the default data directory and prints a one-line save summary to stderr. To choose the destination explicitly:

```bash
agentic-blog search "커피" --limit 5 --output ./coffee.json
```

Use a search result's blog ID to inspect a blog, then list its posts:

```bash
agentic-blog blog example_blog --output ./blog.json
agentic-blog posts example_blog --limit 10 --output ./posts.json
```

Read a public post and its comments:

```bash
agentic-blog post "https://blog.naver.com/example_blog/123456789" --output ./post.json
```

`post` also accepts an `m.blog.naver.com` URL, a `PostView.naver?blogId=...&logNo=...` URL, or a two-part reference:

```bash
agentic-blog post example_blog 123456789 --no-comments --output ./post.json
```

See the [installation guide](docs/wiki/Installation.md), [quick start](docs/wiki/Quick-Start.md), and [CLI reference](docs/wiki/CLI-Reference.md) for fuller examples.

## Commands

Run `agentic-blog <command> --help` for parser-level help. `agentic-blog catalog` emits a
machine-readable JSON description of the installed CLI; `agentic-blog schema` prints its model
fields, while `agentic-blog schema --json` emits JSON Schema draft 2020-12. Both meta commands are
offline and write to stdout.

### Read commands

| Command | Purpose | Command-specific options |
| --- | --- | --- |
| `search <query>` | Search public Naver Blog posts, blogs, people, or tags. | `--type {post,blog,id,tag}` (default `post`); `--self-purchased` (내돈내산, `--type post` only); `--sort {sim,date}` (default `sim`); `--since YYYY-MM-DD`; `--until YYYY-MM-DD` |
| `blog <blog_id>` | Read one public blog profile and category tree. | — |
| `posts <blog_id>` | List public posts from a blog. | `--category N` (default `0`, all); `--sort {recent,popular}` (default `recent`); `--notices`; `--query TEXT`; `--tag TEXT` |
| `post <url-or-blog_id> [log_no]` | Read one public post body, its tags, and by default its full comment thread. | `--no-comments`; `--comment-sort {new,favorite}` (default `new`); `--comment-limit N` |
| `buddies <blog_id>` | List a blog's public buddies/neighbours. | — |
| `topics` | Read Naver's public blog topic tree. | — |
| `topic <directory_seq>` | List posts in a public topic. | `--top` |

All read commands accept `--format {json,ndjson}` (default `json`), `--output PATH`,
`--data-dir PATH`, `--no-redact`, and `-v/--verbose`. Diagnostic redaction is enabled by
default; `--no-redact` explicitly disables it for error messages only, never result files, and
verbose diagnostics include the typed error class. `--limit N` applies to `search`, `posts`,
`buddies`, and `topic`; it must be non-negative. `--raw` is accepted only by `search`, `blog`,
`posts`, `buddies`, and `topic`. Neither `post` nor `topics` accepts `--raw`.

Important combinations are validated as usage errors:

- Search date bounds are server-side and available only with `search --type post`. `--type id` accepts neither `--sort` nor date bounds.
- `posts --query` cannot be combined with `--category`, `--sort popular`, `--notices`, or `--tag`; its text must not be empty.
- `posts --tag` cannot be combined with `--category`, `--sort popular`, `--notices`, or `--query`; its text must not be empty. It accepts no sort of its own, because Naver's in-blog tag search ignores one and always answers in date order.
- `posts --notices` cannot be combined with `--sort popular`, `--category`, `--query`, or `--tag`.
- A bare post number is not enough: provide a Naver post URL or both `<blog_id> <log_no>`.

`blog`, `posts`, `buddies`, and `post` all accept a `blog.naver.com` or `m.blog.naver.com` URL in place of a bare blog ID.

## Output and storage

Read commands write an array of schema-shaped objects to a file, never the retrieved content to stdout. Their stderr summary reports the item count, date range when available, stop reason, and saved path. JSON output is indented UTF-8 with `ensure_ascii=False`, preserving Korean text. NDJSON writes one UTF-8 JSON object per line.

Without `--output`, files are written beneath the platform user-data directory:

```text
<platform user data>/agentic-blog/output/
```

Names include the command, a Unicode-safe identifier, UTC timestamp, and `.json` or `.ndjson` extension. Use `--data-dir PATH` to choose the application data directory for one command, or set `AGENTIC_BLOG_DATA_DIR` for the process. `--output PATH` takes precedence for the output file itself.

The output schema is generated from the installed models. Use:

```bash
agentic-blog schema --json
```

For schema and record guidance, see [Output Schema](docs/wiki/Output-Schema.md).

## Budgets and pacing

Every client enforces a non-bypassable **0.5-second minimum pause** between requests. Each command run has a default budget of **100 requests**, preventing accidental bulk collection. Pagination stops on the requested limit, a natural end, an empty search, or the request budget. `search --type post` sends `--since` and `--until` as server-side filters; they do not create a local date-boundary stop reason. The stderr summary identifies the stop reason.

There is intentionally no bulk crawl, daemon, batch mode, `--profile`, or `--wait-on-limit` flag. Compose small commands instead of attempting broad collection.

## Chaining focused reads

Agentic Blog's commands are single-target primitives. A typical bounded investigation is:

1. `search` for a topic, blog name, or ID.
2. `blog` to inspect a selected public blog's profile and category tree.
3. `posts` or `posts --query` to narrow to relevant public posts.
4. `post` to read a selected body and comments.
5. `buddies` to follow only public neighbour links, or `topics` then `topic` to change discovery paths.

Save each result and pass only the identifiers needed to the next command. Do not treat chaining as authorization to collect a social graph or archive a service.

## Limitations and exit codes

Only content that Naver makes readable to anonymous visitors is in scope. Private blogs, neighbour-only posts, deleted posts, suspended blogs, login-gated feeds, notifications, visitor statistics, and write actions are unavailable. The tool does not post, comment, like, add neighbours, or bypass access controls. Naver may change its public response or HTML structure; update the package rather than relying on a broken parser.

| Exit code | Meaning |
| --- | --- |
| 0 | Successful result, including zero matches or a normal pagination stop. |
| 1 | Usage error, invalid identifier, or unexpected failure. |
| 3 | Naver blocked or throttled the request. |
| 4 | Naver's response or expected HTML structure changed. Upgrade or report the drift. |
| 5 | The target does not exist or cannot be read anonymously. |

Exit code 2 is intentionally unassigned; it is not an authentication state.

## Privacy and responsible use

Public content can still contain personal data. Keep outputs local, collect the minimum needed, avoid publishing or redistributing retrieved personal information, and delete outputs when no longer needed. Diagnostic raw output can expose more upstream fields; use it only for local troubleshooting and handle it with particular care.

Repository fixtures are synthetic and PII-free. Do not commit real captures, cookies, browser state, session data, credentials, or output files. Read [SECURITY.md](SECURITY.md), [DISCLAIMER.md](DISCLAIMER.md), and the [Security and Privacy guide](docs/wiki/Security-and-Privacy.md).

## Contributing and policies

Contributions are welcome under [CONTRIBUTING.md](CONTRIBUTING.md). Please follow the [Code of Conduct](CODE_OF_CONDUCT.md), report vulnerabilities through [SECURITY.md](SECURITY.md), and review the [FAQ and troubleshooting guide](docs/wiki/FAQ-and-Troubleshooting.md).

## License

[MIT](LICENSE)
