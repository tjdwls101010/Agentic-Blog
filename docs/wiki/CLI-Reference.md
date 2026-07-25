# CLI Reference

`agentic-blog` is a read-only command-line client for Naver Blog's anonymously readable surface. Read commands write UTF-8 result files; their one-line progress/result summary is written to stderr. See [Output Schema](Output-Schema.md) for the records in those files and [Security and Privacy](Security-and-Privacy.md) for operating limits.

## Common read-command flags

| Flag | Meaning |
| --- | --- |
| `--format {json,ndjson}` | Output encoding; default `json`. |
| `--output PATH` | Result-file path. Parent directories are created. |
| `--data-dir PATH` | Base directory used only when deriving the default output path. |
| `--limit N` | Non-negative maximum result count, where supported. |
| `--raw` | Include the raw upstream object where supported. This is an explicit diagnostic/data-retention opt-in. |
| `--no-redact` | Disable default diagnostic-message redaction for this command; result files are unchanged. |
| `-v`, `--verbose` | Prefix typed failures with their error class and allow a longer diagnostic. |

Without `--output`, files are placed in `agentic-blog/output` under the platform user-data directory (or `AGENTIC_BLOG_DATA_DIR`, or `--data-dir`) and named `<command>-<safe-identifier>-<UTC timestamp>.<json|ndjson>`. The identifier retains non-ASCII letters; punctuation is normalized for a path component.

`--limit` is available on `search`, `posts`, `buddies`, and `topic`. `--raw` is available on `search`, `blog`, `posts`, `buddies`, and `topic`; it is not implemented for `post` or `topics`.

## Offline commands

### `agentic-blog --version`

Prints the package version and exits. It does not read Naver.

### `agentic-blog catalog`

Prints a JSON catalog generated from the live parser, including commands, argument defaults and choices, output type, and the canonical exit-code mapping. This command is offline and writes to stdout.

### `agentic-blog schema [--json]`

Prints the generated output schema without network access. With `--json`, it emits JSON Schema draft 2020-12; without it, it prints readable field/type/description entries. See [Output Schema](Output-Schema.md#generated-schema-and-catalog).

There are no `login`, `setup`, `status`, `doctor`, profile, credential, or browser-state commands.

## Read commands

### `search QUERY`

Searches the Naver Blog section index. `QUERY` must contain non-whitespace text.

| Flag | Meaning |
| --- | --- |
| `--type {post,blog,id}` | Search surface; default `post`. `post` emits `Post`; `blog` and `id` emit `Blog`. `id` searches nickname/blog ID. |
| `--sort {sim,date}` | Section-search order; default `sim`. |
| `--since YYYY-MM-DD` | Server-side lower date bound, post search only. |
| `--until YYYY-MM-DD` | Server-side upper date bound, post search only. |

`--since` may not be later than `--until`. `--since` and `--until` are invalid except with `--type post`. Supplying `--sort`, `--since`, or `--until` with `--type id` is invalid, even when the sort value is the default. Date filtering is sent to Naver; the client does not locally infer or repair dates.

### `blog BLOG_ID`

Reads one public blog profile and category tree, producing one `Blog` record. It has no `--limit`; `categories` is populated on a successful full blog read.

### `post POST_REF [LOG_NO]`

Reads one public post, its rendered Markdown body, and comments by default, producing one `Post` record.

`POST_REF` may be a `blog.naver.com/<id>/<logNo>` or `m.blog.naver.com/...` URL, a `PostView.naver?blogId=…&logNo=…` URL, or a blog ID when `LOG_NO` is supplied separately. A bare post number is not sufficient because post numbers are only unique within a blog.

| Flag | Meaning |
| --- | --- |
| `--no-comments` | Skip comment-page reads; `comments` is `null`. |
| `--comment-sort {new,favorite}` | Comment order requested from Naver; default `new`. |
| `--comment-limit N` | Non-negative maximum number of top-level comment roots. Replies attached to selected roots remain nested. |

`post` has no `--format`-independent stdout payload: the record is still written through the common output mechanism. It does not implement `--raw` or `--limit`.

### `posts BLOG_ID`

Lists a blog's public posts. These are listing-shaped `Post` records: `brief` may be present, while `body` and `comments` are `null`.

| Flag | Meaning |
| --- | --- |
| `--category N` | Non-negative category number; default `0` (all). |
| `--sort {recent,popular}` | Listing order; default `recent`. |
| `--notices` | List pinned notice posts instead of the chronological list. |
| `--query TEXT` | Search posts within this blog using Naver's HTML-backed in-blog search. Text must be non-empty after trimming. |

`--notices` cannot be combined with `--sort popular`; neither `--notices` nor `--sort popular` can be combined with nonzero `--category`. `--query` cannot be combined with nonzero `--category`, `--sort popular`, or `--notices`. In-blog search is an HTML response parsed into listing records, not the section-search API.

### `buddies BLOG_ID`

Lists the target blog's public neighbours as `Blog` records. It only reflects the anonymous public-buddy surface.

### `topics`

Reads the public directory topic tree in one request and emits `Topic` records. It has neither `--limit` nor `--raw`.

### `topic DIRECTORY_SEQ`

Lists `Post` records for one directory topic. Use a `seq` returned by `topics`.

| Flag | Meaning |
| --- | --- |
| `--top` | Use the topic's one-shot top-post listing instead of chronological pages. |

## Formats and summaries

`json` is one JSON array. `ndjson` is one JSON object per line, with no enclosing array. Both use UTF-8 and preserve non-ASCII text (`ensure_ascii=False`). A successful read prints this stderr summary shape:

```text
N posts|blogs|topics, range oldest..newest, stop reason: REASON. Saved to PATH
```

The range is computed from non-null `Post.created_at` values only; commands with no such values report `n/a..n/a`. Control characters in the displayed path are escaped in the summary only; the actual path is unchanged.

## Stop reasons

| Reason | Meaning |
| --- | --- |
| `limit_reached` | A requested nonzero limit stopped collection only after another distinct record was observed; a full page alone means another page may exist. A zero limit stops before requests. |
| `no_next_page` | The observed page/list was exhausted after at least one result. |
| `no_matches` | A search/listing yielded no results. This is successful execution. |
| `max_requests` | The client request budget prevented another request. Results collected so far are still written. |
| `single_target` | A fixed single-target/tree operation completed, including `post`, `blog`, and `topics`. |

No `since_crossed` or normal-path `rate_limited` stop reason is implemented. Server date bounds are not locally paginated, and HTTP 429 is an error.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Successful command, including zero matches, exhausted pages, or a limit/budget stop. |
| 1 | Usage error, invalid identifier, or other unexpected `AgenticBlogError`. Parser errors intentionally use 1. |
| 3 | Naver rate-limited the request (HTTP 429). |
| 4 | An expected Naver JSON envelope or HTML structure no longer matches the parser. |
| 5 | A measured missing target or an anonymously unavailable target. |

Exit code 2 is deliberately unassigned. An unhandled non-project exception is not a documented CLI contract.
