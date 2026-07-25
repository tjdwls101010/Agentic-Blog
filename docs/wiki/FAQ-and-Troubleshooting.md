# FAQ and Troubleshooting

This page covers the implemented anonymous read surface. Start with [CLI Reference](CLI-Reference.md) for syntax, [Output Schema](Output-Schema.md) for result fields, and [Security and Privacy](Security-and-Privacy.md) before retaining or sharing output.

## Is this a logged-in Naver client?

No. It has no credentials, cookies, browser profile, session, or login command. It reads only the anonymously accessible public surface. It cannot publish, comment, like, follow, manage an account, or retrieve content merely because a caller knows its URL.

## Why is a target unavailable or why did I get exit code 5?

The requested blog or post may not exist, or it may not be available to an anonymous reader. That includes restricted visibility and other unavailable states. The project deliberately uses only conservatively measured response signatures. It does **not** claim a precise private/buddy/deleted/suspended classification when the anonymous response does not safely establish one.

Do not retry with credentials, cookies, or browser state: those are outside this project's boundary. Confirm the target manually only when you have a legitimate reason, then accept the anonymous result as unavailable.

## What does “Naver response structure changed” mean (exit code 4)?

A JSON envelope or HTML structure no longer matched the parser's expected shape. This is typed drift: the upstream interface may have changed, returned a new valid shape, or delivered unexpected content. It is not proof that the target is private or missing.

Capture no live payload in the repository. Report the command form, exit code, date, and minimal redacted structural facts through the project's security/reporting process. Maintain synthetic fixtures for any regression test. See [Security and Privacy](Security-and-Privacy.md#diagnostics-and-redaction).

## Why did `posts --query` behave differently from `search`?

`search` uses Naver's Blog section search and can search posts, blogs, or IDs. `posts BLOG_ID --query TEXT` is a blog-local search backed by an HTML response. It produces listing-shaped `Post` records and has different supported combinations: it cannot be combined with `--category` other than the default, `--sort popular`, or `--notices`.

Because the local search is HTML-backed, a template change can produce exit code 4 even while a section search succeeds.

## Why are `body`, `comments`, or other fields `null`?

Listings do not contain a complete post body or comment thread, so `search`, `posts`, and `topic` emit `body: null` and `comments: null`. `post` obtains the rendered Markdown body and requests comments by default. `post --no-comments` intentionally leaves `comments` as `null`.

Other nullable fields are absent from the measured source response or are not meaningful on that command's surface. `null` means unavailable, not zero, false, or an empty string. See [Output Schema](Output-Schema.md#timestamps-and-normalization).

## How are comments represented?

`post` emits top-level comments in `comments`. Replies are recursive objects in each comment's `replies` array. A top-level comment has `parent_comment_no: null`, `is_reply: false`, and `depth: 0`; replies have a parent ID and positive depth. `--comment-sort new|favorite` chooses the requested source ordering.

`--comment-limit N` limits top-level comment roots, not every nested reply. `--comment-limit 0` makes no comment-page requests and returns an empty comments array when comments are otherwise enabled. Anonymous output is only what the returned public comment surface provides; it is not evidence that no other comments exist.

## Why did a command stop at `max_requests`?

Each client has a default 100-request budget and every request has a non-bypassable 0.5-second minimum pause. `max_requests` means another request would exceed that budget. Any already collected records are still written, and the command exits successfully because the partial result is explicit in the summary.

Narrow the request, use `--limit`, or begin a separate, proportionate run later. Do not implement retry loops, identity rotation, or attempts to bypass rate controls. See [Security and Privacy](Security-and-Privacy.md#pacing-and-request-budgets).

## What do the other stop reasons mean?

- `limit_reached`: the requested result limit stopped collection, including `--limit 0` before a request.
- `no_next_page`: a nonempty listing reached its observed end.
- `no_matches`: a search/listing yielded no records; this is not an error.
- `single_target`: a fixed target/tree operation completed.

There is no implemented `since_crossed` stop reason. Search dates are server-side bounds. HTTP 429 is an exit-code-3 error, not a stop reason. See [CLI Reference](CLI-Reference.md#stop-reasons).

## Why is the result file not printed to stdout?

Post bodies and comment trees can be large. Read commands write a JSON array or NDJSON file and send only a one-line summary to stderr. Use `--output PATH` to choose the file, or `--format ndjson` for line-oriented processing. `catalog` and `schema` are the exceptions: they print their offline metadata/schema to stdout.

Default output is outside the repository and current directory. It is still local personal data and must be protected accordingly.

## Should I use `json` or `ndjson`?

Use `json` (the default) when a consumer expects one array. Use `ndjson` when records should be processed independently, one object per line. Both are UTF-8 and preserve non-ASCII text. Neither changes the object schema. See [Output Schema](Output-Schema.md#encodings).

## Why are IDs strings rather than numbers?

Post, blog, category, topic, and comment identifiers may be large numeric-looking values. They are serialized as strings to avoid precision loss in JSON consumers. Do not coerce them to floating-point numbers or assume numeric ordering.

## How do I discover the current commands or validate output?

Run `agentic-blog catalog` for the parser-derived command and flag catalog. Run `agentic-blog schema --json` for the generated draft 2020-12 schema. These offline commands reflect the current implementation and are safer than hard-coding a copied command list or schema.

## Can I enable raw output to debug a problem?

Only use `--raw` when strictly necessary, and only for commands that support it: `search`, `blog`, `posts`, `buddies`, and `topic`. It is omitted by default and can preserve extra upstream public fields. Do not commit, publish, or casually share raw output. `post` and `topics` reject `--raw`.
