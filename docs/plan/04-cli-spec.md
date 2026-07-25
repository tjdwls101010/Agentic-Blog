# CLI Specification

`prog = agentic-blog`. stdlib `argparse`. `main(argv)` → `build_parser().parse_args()` → dispatch
via `_HANDLERS`. Subparsers `required=True`. Global `--version`. Custom `_ArgumentParser.error()`
exits **1** (not argparse's 2 — exit 2 is reserved, see the table below).

## Commands

### Offline meta commands (no network, no setup)

- **`catalog`** — machine-readable description of the whole CLI, generated from the parser.
  Flag: `--json` (no-op; always JSON).
- **`schema`** — the output object schema. Flag: `--json` (JSON Schema draft 2020-12).

There is **no `login`, `setup`, `status`, or `doctor`.** See `03-architecture.md` — nothing is
stateful, so there is nothing to configure or diagnose.

### Read primitives (write JSON to a file; one-line stderr summary)

- **`search <query>`** — Naver's blog-section search.
  `--type {post,blog,id}` (default `post`), `--sort {sim,date}` (default `sim`),
  `--since YYYY-MM-DD`, `--until YYYY-MM-DD` (**server-side**, `--type post` only).
  → `Post` for `post`; `Blog` for `blog` and `id`.

  The three types are genuinely different searches: `post` finds individual articles, `blog` finds
  blogs by name/description, `id` finds people by nickname or blog id. `--sort` and the date
  bounds are rejected with a usage error for `--type id`.

- **`blog <blogId>`** — one blog: profile plus its full category tree. **No pagination**, one
  object out. → `Blog` (with `categories[]` populated).

- **`posts <blogId>`** — that blog's posts. `--category N` (default 0 = all),
  `--query <text>` (in-blog search — **HTML-backed, see D8**), `--sort {recent,popular}`
  (default `recent`), `--notices` (return the pinned notice posts instead). → `Post`
  (listing shape: `brief` populated, `body` and `comments` null).

  `--query` and `--category` are mutually exclusive: in-blog search has no category filter.
  `--query` and `--sort popular` are likewise mutually exclusive.

- **`post <url|logNo>`** — one post: **body and full comment thread, both by default.**
  `--no-comments` skips the comment requests. `--comment-sort {new,favorite}` (default `new`),
  `--comment-limit N`. Accepts a `blog.naver.com/<id>/<logNo>` or `m.blog.naver.com/...` URL, a
  `PostView.naver?blogId=…&logNo=…` URL, or `<blogId> <logNo>` as two arguments. → `Post`
  (with `body` and `comments[]` populated).

  A bare `logNo` with no blog id is a usage error — Naver post ids are only unique per blog.

- **`topics`** — Naver's blog topic (디렉토리) tree. No target, no pagination. → `Topic`.

- **`topic <seq>`** — posts under one topic. `--top` returns the topic's top posts instead of the
  chronological listing. `<seq>` is a `directorySeq` from `topics`. → `Post`.

- **`buddies <blogId>`** — that blog's public neighbours (이웃). → `Blog`.

### Common read flags (shared argparse group)

`--format {json,ndjson}` (default `json`), `--output PATH`, `--limit N` (default unbounded),
`--data-dir PATH`, `--raw`, `--no-redact`, `-v/--verbose`.

`--output` default naming: `<command>-<safe_identifier>-<YYYYMMDDTHHMMSSffffffZ>.<json|ndjson>`
under `<platform user data>/agentic-blog/output/`. Non-alphanumeric runs in the identifier become
`-`; **the identifier is Korean-safe** — do not ASCII-strip it into emptiness, transliterate or
percent-encode as needed and always leave a non-empty stem.

There is **no `--profile`** (no credentials exist) and **no `--wait-on-limit`** (no rate-limit
headers exist to wait on).

## Output contract

- Read commands write to a **file**; only a one-line summary hits **stderr**; nothing useful goes
  to stdout. This matters more here than in the siblings — one Naver post body can be tens of KB
  of Markdown, and dumping that to stdout would be hostile to the caller's context.
- JSON is written with `ensure_ascii=False`, UTF-8, so Korean text stays readable in the file.
- Summary format: `"{N} posts, range {oldest}..{newest}, stop reason: {reason}. Saved to {path}"`
  (`{N} blogs, …` / `{N} topics, …` for the other output objects).
- `--raw` attaches the raw upstream node per object (redacted unless `--no-redact`, which prints a
  warning). Debug only.
- Only in summaries, C0/DEL characters in the output path are rendered as `\xNN`; the real
  filesystem path is unchanged.

## `stop_reason` vocabulary (in the stderr summary)

- `limit_reached` — `--limit` stopped it; there is more.
- `no_next_page` — genuinely the end (a page returned fewer items than requested).
- `no_matches` — a search with zero hits (real; report as such, do not treat as an error).
- `since_crossed` — the `--since` boundary was reached.
- `max_requests` — stopped by the per-run request budget.
- `single_target` — the command returns exactly one object and does not paginate
  (`blog`, `post`, `topics`).

Note there is **no `rate_limited`** stop reason in the normal path: Naver exposes no rate-limit
headers, so a block arrives as an HTTP error, not as a countable budget. If Phase 0 Q-1 discovers
a real throttling signature, add it then — with the measured evidence recorded.

## Exit-code contract (single source in `errors.py`; asserted by `test_cli.py`)

| Code | Meaning |
|---|---|
| 0 | success (limit met / date window reached / listing exhausted / zero matches) |
| 1 | usage error, invalid identifier, or unexpected failure |
| 3 | blocked or throttled by Naver (HTTP 429, or the block signature found in Phase 0 Q-1) |
| 4 | Naver's response no longer matches expectations — envelope parse failure, or the post-body / in-blog-search HTML structure changed. Fix: upgrade. |
| 5 | target blog or post does not exist, is private, is neighbour-only, or was deleted |

**Exit 2 is deliberately unassigned.** In every sibling it means "not logged in / session
expired," and that state cannot occur here. Leaving the number unused — rather than recycling it —
keeps the family's exit codes readable side by side and means a `2` from this tool is
unambiguously a bug, not a re-purposed condition.

There is no exit 7 (`--since` unconfirmed): date filtering is **server-side** here
(`02-recon-findings.md` §3.1), so a `--since` request either returns in-range results or fails
outright.

## Typed errors (`errors.py`, base `AgenticBlogError`)

- `InvalidIdentifierError` (→1) — unparseable blog id, post URL, or `directorySeq`.
- `RateLimitedError` (→3) — HTTP 429 or a confirmed block signature.
- `EnvelopeParseError` (→4) — a JSON envelope no longer has its anchored path.
- `BodyParseError` (→4) — neither the SmartEditor ONE container nor the legacy container was found
  in a post's HTML. Distinct from `EnvelopeParseError` so the failing layer is obvious from the
  message alone.
- `NotFoundError` (→5) — no such blog / post / topic.
- `TargetUnavailableError` (→5) — it exists but is not readable anonymously: private blog,
  neighbour-only post, deleted post, suspended blog. **Must carry which of those it is**, from the
  visibility flags, so the caller can distinguish "gone" from "not for you."

`TargetUnavailableError` is the one the skill will hit most often and is the most useful to get
right. A neighbour-only post is a *normal* outcome for an anonymous reader, not a malfunction; the
message must say so plainly rather than reading like a bug.

## `catalog`

`build_catalog()` reflects over `build_parser()._actions` →
`{catalog_version, package, command, version, commands[], exit_codes{}, output_schema}`. Each
command carries `name`, `help`, `output` (`Post` / `Blog` / `Topic` / `None` from a
`_COMMAND_OUTPUT` map), and `arguments[]` (flags / types / defaults / choices).

`test_cli.py` asserts every `_HANDLERS` command appears in the catalog and every read command
declares its output object — the anti-drift gate that lets the skill trust `catalog` instead of
hard-coding a command list.
