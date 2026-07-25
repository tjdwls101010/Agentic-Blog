# Architecture

## Naming triple + layout

- PyPI distribution: **`agentic-blog`** (already claimed; `0.0.1` published)
- Import package: **`agentic_blog`** (`src/`-layout)
- Console script: **`agentic-blog`** → `agentic_blog.cli:main`
- Build backend: `hatchling`. Python **`>=3.11`** (raise from the committed `>=3.9`, D10).
  License MIT. `Development Status :: 3 - Alpha`.
- `__version__` in `src/agentic_blog/__init__.py`, gated against the git tag at release.

## Module structure (`src/agentic_blog/`)

Shaped after `agentic-x` / `agentic-threads`, **with the entire authentication half deleted.**
There is no `auth.py`, no `session.py`, no `docids.py`, no `gql.py`, no `transaction.py`, and no
`_stealth_init.js`. If you find yourself creating one of those, stop and re-read D1.

| Module | Responsibility |
|---|---|
| `__init__.py` | `__version__`, package docstring. No eager heavy imports. |
| `config.py` | Paths (`platformdirs.user_data_dir("agentic-blog")`), `MIN_REQUEST_PAUSE_SECONDS = 0.5` + `clamp_request_pause`, `DEFAULT_MAX_REQUESTS`, `DEFAULT_USER_AGENT_*`, env override `AGENTIC_BLOG_DATA_DIR`. |
| `errors.py` | Typed hierarchy under `AgenticBlogError` + the single exit-code table (see `04-cli-spec.md`). |
| `identifiers.py` | Normalise every way a caller can name a thing: `blogId`, `blog.naver.com/<id>`, `m.blog.naver.com/<id>`, `blog.naver.com/<id>/<logNo>`, `PostView.naver?blogId=…&logNo=…`, a bare `logNo`, a `directorySeq`. Returns typed `BlogRef` / `PostRef`. Rejects anything else with `InvalidIdentifierError`. |
| `endpoints.py` | URL constants and per-endpoint parameter builders for all three hosts (§ below). One function per endpoint, no request logic. This is the file that changes when Naver moves something. |
| `client.py` | `ReadClient` over `httpx`: per-host default headers (`Referer` is mandatory), `_throttle` enforcing the 0.5s floor on **every** request regardless of entry point, the `)]}',` XSSI strip, envelope-level error mapping, and a per-run request budget. |
| `parse.py` | Pure envelope walks — one anchored extractor per endpoint. Raises `EnvelopeParseError` (→ exit 4) on structural failure. **No HTML here** (that is `body.py`). |
| `body.py` | The only HTML code. `lxml`-based: SmartEditor ONE component walk over `.se-main-container`, legacy fallback over `div.post_ct`, and the `PostSearchList.naver` result extractor. Produces Markdown + `media[]`. |
| `model.py` | `Post` / `Blog` / `Comment` / `Media` / `Category` / `Topic` dataclasses + `to_dict()`; `FIELD_DESCRIPTIONS`; `schema_fields()` anchored on `to_dict()`; `json_schema()` (draft 2020-12); `build_*` normalizers. |
| `retrieve.py` | Pagination orchestrators with the stop-reason vocabulary: `search`, `fetch_blog`, `fetch_posts`, `fetch_post`, `fetch_topics`, `fetch_topic`, `fetch_buddies`. Returns bounded, eager result objects. |
| `redact.py` | Scrub diagnostics only — never the output file. Truncate free text, strip signing query-strings from `pstatic.net` CDN URLs. |
| `cli.py` | argparse parser, subcommand handlers, `_HANDLERS` dispatch, exit-code contract, `catalog` (from the live parser) + `schema` (from the model). |
| `__main__.py` | `python -m agentic_blog`. |

### What deliberately does not exist

`login`, `setup`, `status`, `doctor`, and `--profile`. The siblings have all five because they
carry credentials that expire, browsers that must be provisioned, and rotating ids that drift.
**None of those failure modes exist here** — there is nothing to log into, nothing to install,
nothing to re-anchor. A `doctor` command whose only possible output is "the network works" is
noise. If a future change reintroduces stateful setup, reintroduce the command then.

## The three hosts (see `02-recon-findings.md` for verified signatures)

`endpoints.py` groups by host because the header requirements and envelope shapes differ:

| Group | Base | Envelope | Default UA |
|---|---|---|---|
| `SECTION` | `https://section.blog.naver.com/ajax/` | `)]}',` prefix, then `{"result":{...}}` | desktop Chrome |
| `MOBILE` | `https://m.blog.naver.com/api/blogs/{blogId}/` | `{"isSuccess":bool,"result"\|"error":{...}}` | iPhone Safari |
| `CBOX` | `https://apis.naver.com/commentBox/cbox/` | `{"success":bool,"code":int,"result":{...}}` | desktop Chrome |
| `LEGACY` | `https://blog.naver.com/` | HTML | desktop Chrome |

**Three constants that are not derivable and must carry an explanatory comment in the source:**

```python
CBOX_POOL = "blogid"          # NOT cbox5/cbox9 — those return code 3300
CBOX_OBJECT_ID = "{blog_no}_201_{log_no}"   # the literal 201 is undocumented; see 02 §6
POST_LIST_MAX_ITEM_COUNT = 30 # 31+ -> param_is_invalidate
```

## Storage (`platformdirs.user_data_dir("agentic-blog")`)

```
<data dir>/output/     # default output dir — never cwd, never the repo
```

That is the whole tree. There is no `profiles/`, no `browsers/`, no `session.json`, and no
mode-0600 secret file, because there are no secrets. Env override: `AGENTIC_BLOG_DATA_DIR`
(or `--data-dir`).

## Data model (output schema)

Six object types. Three are top-level (a read command emits an array of one of these); three are
nested.

**`Post`** — emitted by `search --type post`, `posts`, `topic`, and `post`:
`log_no` (string, the dedup key), `blog_id`, `blog_no`, `url`, `title`, `brief` (Naver's own
summary — present in listings, absent from `post`), `body` (Markdown, **only populated by the
`post` command**; `null` in listings), `created_at` (ISO-8601 UTC `Z` or null), `blog_name`,
`nickname`, `category_no`, `category_name`, `comment_count`, `like_count` (공감/`sympathyCnt`),
`share_count`, `thumbnail_url`, `media[]` (`Media`), `editor_version`, `visibility`
(`public` | `buddy` | `both_buddy` | `private`), `is_notice`, `comments[]` (`Comment`, **only
populated by `post`**), `captured_at` (when *you* scraped — not an event time), `raw` (only with
`--raw`).

**`Blog`** — emitted by `blog`, `search --type blog|id`, and `buddies`:
`blog_id`, `blog_no`, `blog_name`, `nickname`, `description`, `profile_image_url`, `url`,
`buddy_count`, `post_count`, `categories[]` (`Category`, **only populated by `blog`**),
`captured_at`, `raw`.

**`Topic`** — emitted by `topics`: `seq` (the `directorySeq`), `name`, `group_name`.

**`Comment`** (nested in `Post.comments`): `comment_no`, `parent_comment_no`, `is_reply`, `depth`,
`text`, `author_name`, `author_blog_id` (from `profileUserId` — **the navigational edge**),
`author_profile_image_url`, `created_at`, `like_count`, `dislike_count`, `is_best`, `is_deleted`,
`is_secret`, `sticker_id`, `image_urls[]`, `replies[]` (recursive `Comment`).

**`Media`** (nested in `Post.media`): `kind` (`photo` | `video` | `sticker` | `unknown`), `url`,
`caption`, `width`, `height`.

**`Category`** (nested in `Blog.categories`): `category_no`, `parent_category_no`, `name`,
`post_count`, `is_open`.

Schema is **generated from the code** (`schema_fields()` anchored on `to_dict()` output,
`json_schema()` draft 2020-12), never hand-written — so `agentic-blog schema --json` cannot drift.
`test_model.py` validates repository synthetic fixtures against the generated schema with a
format-aware draft 2020-12 validator. Live checks assert shapes only and persist no captures,
consistent with the privacy policy.

### Normalisation rules the model owns

These exist because the upstream data is inconsistent in ways a caller should never see:

1. **Three timestamp formats collapse to one.** `addDate` is epoch **milliseconds**; CBOX
   `regTime` is ISO-8601 with a `+0900` offset; `public-buddies.updateTime` is a **humanised
   Korean relative string** (`"8분 전"`) that carries no absolute time. The first two become
   ISO-8601 UTC `Z`. The third **must not be guessed into a timestamp** — pass it through as
   `update_label` or drop it, and say which in the field description.
2. **Search responses contain markup.** `title`, `blogName` and `contents` come back wrapping
   matches in `<strong class="search_keyword">…</strong>`. Strip it in the builder; the raw string
   is not display text.
3. **Separator rows are not categories.** `category-list` entries with `categoryType == "S"` /
   `divisionLine == true` are cosmetic dividers with `postCnt: 0`. Filter them out.
4. **Ids are strings.** `logNo`, `blogNo` and `commentNo` are large decimal integers; serialise as
   strings so no JSON consumer rounds them.
5. **`readCount` is not modelled.** Measured `null` for anonymous readers — a field that is always
   null is worse than absent, because it implies the data exists.

## The three invariants to preserve

1. **Everything derived, never transcribed.** `catalog` comes from the live argparse parser,
   the schema from `to_dict()`-anchored descriptions, exit codes from one table in `errors.py`.
   `test_cli.py` asserts non-drift: every handler appears in the catalog and declares its output
   object.
2. **Non-bypassable rate floor + single redaction path.** The 0.5s clamp applies on every request
   regardless of entry point; every diagnostic surface routes through `redact`, and the output file
   never does.
3. **HTML stays in `body.py`.** `parse.py` handles JSON envelopes only. When a Naver template
   change breaks something, exactly one file is suspect — and the blast radius of the project's one
   fragile dependency stays visible in the module layout.
