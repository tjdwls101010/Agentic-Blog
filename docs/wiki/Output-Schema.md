# Output Schema

Every read command writes a list of normalized records to a file. The command-specific result type is documented in the [CLI Reference](CLI-Reference.md). Identifiers that may exceed JavaScript-safe numeric precision are serialized as strings. For the live machine-readable contract, run `agentic-blog schema --json`.

## Encodings

`--format json` writes one UTF-8 JSON array. `--format ndjson` writes the same records as one JSON object per UTF-8 line, without an enclosing array. Both retain Korean and other non-ASCII text directly. The top-level schema accepts an array of `Post`, `Blog`, or `Topic`; an individual NDJSON line is one of those objects.

Fields shown as nullable are emitted with `null` when unavailable. Fields not marked nullable are always emitted. The sole exception is `raw`: it is omitted entirely unless the command supports and receives `--raw`.

## Timestamps and normalization

`created_at` and `captured_at` are strings in ISO-8601 UTC form ending in `Z`, with optional fractional seconds, or `null` where the field is nullable. `created_at` is Naver's source event time; `captured_at` is the collection time and is not a publication time. Search epoch-millisecond and CBOX `+0900` source timestamps are normalized to UTC. Values that lack an absolute timestamp are not guessed.

Search highlight markup is removed from normalized display text. Source IDs remain strings. A listing record is not a full post: only `post` attempts body extraction and comments.

## Top-level models

### `Post`

Produced by `search --type post`, `post`, `posts`, and `topic`.

| Field | Type | Notes |
| --- | --- | --- |
| `log_no` | string | Post identifier. |
| `blog_id` | string | Owning blog identifier. |
| `blog_no` | string or null | Numeric blog identifier when supplied. |
| `url` | string | Canonical post URL. |
| `title` | string | Post title. |
| `brief` | string or null | Naver listing summary; not a post-body substitute. |
| `body` | string or null | Rendered Markdown body; populated only by `post`. |
| `tags` | array of string or null | Hashtags the post carries; populated only by `post`. `null` means nothing fetched them, an empty array means the post carries none. |
| `created_at` | string or null | Normalized creation time. |
| `blog_name` | string or null | Display name. |
| `nickname` | string or null | Author nickname. |
| `category_no` | string or null | Category identifier. |
| `category_name` | string or null | Category display name. |
| `comment_count` | integer or null | Source comment count. |
| `like_count` | integer or null | Naver sympathy count. |
| `share_count` | integer or null | Share count. |
| `thumbnail_url` | string or null | Thumbnail URL. |
| `media` | array of `Media` or null | Body-extracted attachments; null when no body extraction occurred. |
| `editor_version` | string or null | Naver editor version. |
| `visibility` | `public`, `buddy`, `both_buddy`, `private`, or null | Source visibility value where available. It does not grant access. |
| `is_notice` | boolean | Whether this listing is a notice. |
| `comments` | array of `Comment` or null | `post` comment tree; null for listings or `--no-comments`. |
| `captured_at` | string or null | Collection time. |
| `raw` | object, omitted unless opted in | Raw upstream post node; available only on supported commands. |

### `Blog`

Produced by `search --type blog`, `search --type id`, `blog`, and `buddies`.

| Field | Type | Notes |
| --- | --- | --- |
| `blog_id` | string | Blog identifier. |
| `blog_no` | string | Numeric blog identifier as a string. |
| `blog_name` | string or null | Display name. |
| `nickname` | string or null | Owner nickname. |
| `description` | string or null | Blog description. |
| `profile_image_url` | string or null | Profile image URL. |
| `url` | string or null | Canonical blog URL. |
| `buddy_count` | integer or null | Neighbours the blog **publicly discloses**, from `blog`. Naver keeps a second, usually far larger total visible only to the owner — one measured blog publishes 0 of its 1,908 — so `0` means "does not publish a neighbour list", not "has no neighbours". Null when the request budget stopped before this could be read. |
| `post_count` | integer or null | The blog's own post total, from `blog`. |
| `categories` | array of `Category` or null | Full category tree from `blog`; null elsewhere. |
| `captured_at` | string or null | Collection time. |
| `raw` | object, omitted unless opted in | Raw upstream blog node; available only on supported commands. |

### `Topic`

Produced by `topics`.

| Field | Type | Notes |
| --- | --- | --- |
| `seq` | string | Directory topic identifier; pass it to `topic`. |
| `name` | string | Topic name. |
| `group_name` | string or null | Containing directory group. |

`Topic` has no `raw` field; `topics --raw` is not accepted.

## Nested models

### `Comment`

`Post.comments` contains top-level comments. Each top-level item has `parent_comment_no: null`, `is_reply: false`, and `depth: 0`. Replies are recursively embedded in the parent `replies` array; a reply has its parent ID, `is_reply: true`, and a positive depth. `--comment-limit` limits top-level roots, not individual descendants.

| Field | Type |
| --- | --- |
| `comment_no` | string |
| `parent_comment_no` | string or null |
| `is_reply` | boolean |
| `depth` | integer |
| `text` | string or null |
| `author_name` | string or null |
| `author_blog_id` | string or null |
| `author_profile_image_url` | string or null |
| `created_at` | string or null |
| `like_count` | integer or null |
| `dislike_count` | integer or null |
| `is_best` | boolean |
| `is_deleted` | boolean |
| `is_secret` | boolean |
| `sticker_id` | string or null |
| `image_urls` | array of string |
| `replies` | array of `Comment` |

The tree is the normalized returned comment structure, not an assertion that every public or non-public reply is observable anonymously.

### `Media`

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | `photo`, `video`, `sticker`, or `unknown` | Attachment kind. |
| `url` | string or null | Attachment URL. |
| `thumbnail_url` | string or null | Attachment thumbnail URL. |
| `caption` | string or null | Attachment caption. |
| `width` | integer or null | Pixel width. |
| `height` | integer or null | Pixel height. |

### `Category`

| Field | Type | Notes |
| --- | --- | --- |
| `category_no` | string | Category identifier. |
| `parent_category_no` | string or null | Parent identifier. |
| `name` | string | Display name. |
| `post_count` | integer or null | Source count. |
| `is_open` | boolean | Public visibility indicator. |

## Raw opt-in

`--raw` attaches the original upstream node as `raw` for the commands that support it: `search`, `blog`, `posts`, `buddies`, and `topic`. It is not produced by default, and output serialization otherwise uses only the normalized model fields above. Raw data can contain fields outside this stable schema and can increase privacy, retention, and compatibility risk; protect it as described in [Security and Privacy](Security-and-Privacy.md#local-output-and-raw-data).

## Known upstream fields this schema does not expose

There is **no view-count field**. The popular listing (`posts --sort popular`) is the one surface
where Naver supplies a real one — `viewCount`, an integer, present on all 250 cards sampled across
25 blogs, ranging from about 3,900 to 52,700. Every other listing carries `readCount` and it is
always null.

It is deliberately not normalized: a field that only one of seven commands can populate would be
null on nearly every `Post` the CLI emits, and `--sort popular` already answers "which posts are
popular" with an ordering. If you need the magnitude rather than the rank, read it from the raw
node:

```bash
agentic-blog posts <blog-id> --sort popular --raw --output /tmp/popular.json
# each item's raw.viewCount holds the count
```

Treat it as upstream data outside the stable schema, with the same cautions as any other `raw`
field.

## Generated schema and catalog

`agentic-blog schema --json` emits draft 2020-12 JSON Schema generated from the actual serialization methods. It includes `$defs` for `Post`, `Blog`, `Topic`, `Comment`, `Media`, and `Category`, marks always-present fields as required, and disallows additional properties in those model objects. Use it rather than copying this page into a validator.

`agentic-blog catalog` emits the current parser-derived command/flag catalog, its output types, and exit codes. It is the companion discovery interface when integrating with the CLI; see [CLI Reference](CLI-Reference.md#offline-commands).
