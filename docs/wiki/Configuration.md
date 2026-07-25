# Configuration

Agentic Blog has no account, profile, login, session, cookie import, or browser
configuration. Every CLI read uses anonymous requests to Naver's public
surfaces. There is no `login`, `setup`, `status`, or browser-automation command.

See [Installation](Installation.md) to install the CLI and [Quick Start](Quick-Start.md)
for the read workflow.

## Data and output locations

Without an override, application data is rooted at
`platformdirs.user_data_dir("agentic-blog")`. Default result files are placed
under its `output/` subdirectory, not in the current directory or repository.

Two supported overrides select the application-data root:

| Override | Scope | Effect |
|---|---|---|
| `--data-dir PATH` | One read command | Uses `PATH/output/` for an automatically named result file. |
| `AGENTIC_BLOG_DATA_DIR` | Process environment | Uses its value as the data root unless `--data-dir` is supplied. |

`--output PATH` selects the complete destination path for that command and
takes precedence over automatic output naming. Parent directories are created
when results are written.

For example, keep automatic outputs in a dedicated local directory:

```bash
AGENTIC_BLOG_DATA_DIR="$HOME/agentic-blog-data" \
  agentic-blog search "서울 카페" --limit 10
```

Or choose a single result file directly:

```bash
agentic-blog search "서울 카페" --limit 10 --output results/seoul-cafes.json
```

Automatically named files use the command, a safe identifier, a UTC timestamp,
and `.json` or `.ndjson` extension. JSON uses UTF-8 with Korean text preserved;
`--format ndjson` writes one object per line.

## CLI controls

The CLI deliberately exposes focused result controls rather than a general
crawl mode:

| Need | Supported control |
|---|---|
| Cap list results | `--limit N` on `search`, `posts`, `buddies`, and `topic` |
| Bound post-search time | `search --type post --since YYYY-MM-DD --until YYYY-MM-DD` |
| Choose search ordering | `search --sort sim` or `search --sort date` |
| Limit post comments | `post --comment-limit N` |
| Skip comment reads | `post --no-comments` |
| Choose comment order | `post --comment-sort new` or `post --comment-sort favorite` |
| Choose output encoding | `--format json` or `--format ndjson` |

All numeric limits must be non-negative. Date bounds are server-side and apply
only to `search --type post`; `--type id` does not accept sort or date bounds.
The command parser rejects incompatible `posts` combinations, including
`--query` with a category, popular sort, notices, or `--tag`; and `--tag` with a
category, popular sort, notices, or `--query`.

There is no CLI flag or environment variable for request pacing, request budget,
or HTTP timeout. Do not infer such controls from sibling projects.

## Library-client pacing and request budget

For Python callers using the package API, `ReadClient` accepts `request_pause`
and `max_requests` constructor arguments. The default pause is 0.5 seconds, and
the same 0.5-second floor is enforced when a smaller library value is supplied.
The default budget is 100 attempted requests per client lifetime. A budget of
zero permits no requests. The CLI creates a default client for each invocation,
so these constructor settings are not CLI configuration.

## Diagnostic data

`--raw` includes the preserved upstream object for `search`, `blog`, `posts`,
`buddies`, and `topic`, including `posts --query` and `posts --tag` results. The
`post` and `topics` commands reject the flag. Treat raw data as diagnostic output,
choose an explicit local `--output` path, and do not assume that it is a stable public
schema. Use `agentic-blog schema --json` to inspect the supported structured output
schema offline.
