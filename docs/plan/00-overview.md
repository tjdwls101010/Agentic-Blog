# Agentic Blog — Plan Overview

> Planning session: 2026-07-25 (Korean interview, English artifacts). This directory is the
> full, self-contained plan for a **separate implementation session**. Read it in order:
> `00` (this) → `01-decisions` → `02-recon-findings` → `03-architecture` → `04-cli-spec` →
> `05-testing-and-ci` → `06-implementation-phases` → `07-skill-plan` → `IMPLEMENTATION-KICKOFF`.

## What this is

A read-only **Naver Blog** reader: **no account, no login, no API key, no browser** — install it
and search blogs and posts, walk into a blog, read its category tree, list and search its posts,
read a post's body and full comment thread, browse Naver's topic directories, and follow the
neighbour (이웃) graph. Output is clean, schema'd JSON written to a file.

It is the fifth sibling of an existing family:

- `Agentic Facebook` (`agentic-facebook`, PyPI `agentic-facebook`)
- `Agentic X` (`agentic-x`, PyPI `agentic-twitter`)
- `Agentic Threads` (`agentic-threads`, PyPI `agentic-threads`)
- `Agentic Reddit` (`agentic-reddit`, PyPI `agentic-reddit`) — in progress
- **`Agentic Blog` (`agentic-blog`, PyPI `agentic-blog`)** ← this project

Each is a **CLI of single-target primitives** plus a **Claude Code skill** that chains those
primitives to answer multi-hop questions. The CLI does fast structured retrieval; the *skill*
(i.e. Claude) does the navigation reasoning.

**The end goal, stated by the user:** Claude should use Naver Blog *the way a person does* —
search `section.blog.naver.com` for a topic or a blogger, click into a blog, look at how its
categories are organised, search within it, read a post properly, read what the commenters said,
and follow an interesting commenter or neighbour to the next blog. That is why v1 ships the full
primitive set (D3) rather than an MVP subset: the value is in the *chaining*, and a missing
primitive silently amputates a whole class of question. There is deliberately no `crawl` command
— the chaining is the skill's job, not a batch flag's.

## Why a CLI and not browser-use / WebFetch

- **WebFetch / WebSearch**: only surfaces the sliver of Naver Blog that portals index, with no
  schema — and Naver Blog is notoriously under-indexed outside Naver's own search.
- **browser-use (visual)**: slow (screenshot-observe loops) and can't return clean, structured
  title/author/date/category/comment fields.
- **This CLI**: hits Naver's own JSON backends and returns a defined schema in milliseconds per
  request. LLMs are language machines; hand them language-shaped data.

## The central finding (recon-proven, see `02-recon-findings.md`)

**Naver Blog has the easiest access story of the whole family — by a wide margin.** Live recon on
2026-07-25 established, with pure `curl` and no cookies at all:

1. **Public content is fully readable logged out.** No login, no account, no credentials, no
   session file, no cookie jar.
2. **There is no anti-bot wall on plain HTTP.** Unlike Reddit (403 + JS challenge from any IP),
   ordinary `curl` with a normal `User-Agent` and a `Referer` header gets clean JSON. **No browser
   is needed at runtime, ever.**
3. **There are no rotating request tokens.** No `fb_dtsg`/`lsd` (Facebook/Threads), no
   `x-client-transaction-id` (X), no `doc_id` registry to re-anchor. Nothing rots on Meta's or
   X's release cadence.
4. **Two clean JSON backends cover almost everything**: `section.blog.naver.com/ajax/*` for
   search and topic discovery, and a modern REST API at `m.blog.naver.com/api/blogs/{blogId}/*`
   for per-blog data.

**Consequence — the architecture:** this is the **simplest sibling to build and the most robust
to operate**. `login.py`, `session.py`, `auth.py`, `docids.py`, `transaction.py`, `_stealth_init.js`,
`scrapling`, Playwright, and the entire `[browser]` extra **do not exist in this project.** The
runtime dependency set is `httpx` + `platformdirs` + `lxml`.

**The one complication:** post *bodies* are HTML, not JSON — the first time in this family. But
the structure is well-defined (SmartEditor ONE components, keyed by a `smartEditorVersion` field
the list API hands you *before* you fetch), so this is a bounded, Naver-specific parser, not a
generic-readability gamble (D7).

## Goals (v1)

1. Read primitives, all writing schema'd JSON to a file:
   `search <query>` (`--type post|blog|id`), `blog <blogId>`, `posts <blogId>`
   (`--category`, `--query`), `post <url|logNo>` (body **and** full comment tree),
   `topics`, `topic <seq>`, `buddies <blogId>`.
2. `catalog` (self-describing CLI, generated from the parser) + `schema` (output object schema,
   generated from the model).
3. Post bodies extracted to **lightweight Markdown** with a parallel `media[]` array, across both
   measured editor generations (D4).
4. Non-bypassable **0.5s** inter-request rate floor. PII discipline. Typed errors + an exit-code
   contract.
5. Ship to PyPI via GitHub Actions Trusted Publishing — **already configured and proven**: repo
   `tjdwls101010/Agentic-Blog`, workflow `publish.yml`, environment `pypi`; `0.0.1` is already
   published.

## Non-goals (v1) — agreed explicitly, do not build these

- **No writes** — no posting, commenting, liking (공감), neighbour-adding, or guestbook. Read-only.
  Anonymous access makes these impossible anyway.
- **No login-gated features** — no 이웃새글 feed, no neighbour-only (이웃공개/서로이웃공개) posts,
  no 내소식, no visitor statistics. These are the direct consequence of D1.
- **No other Naver services** — no 카페, 지식iN, 뉴스, 포스트, 쇼핑, 플레이스. Blog only.
- **No `crawl` / batch / daemon** — single-target primitives only; chaining is the skill's job.
- **No official Naver Open API path** — rejected with reasons in D15.
- **No `readCount`** in the schema's promises — measured `null` for anonymous readers.
- **The Claude skill is built in a later session**, after the package is on PyPI
  (see `07-skill-plan.md`), using the `harness-creator` skill.

## Recon status: all load-bearing gates closed

| Question | Status |
|---|---|
| Anonymous (logged-out) reads work? | ✅ **PASS** — every v1 endpoint verified with pure `curl`, no cookies |
| Anti-bot wall on plain HTTP? | ✅ **None** |
| Search endpoint + params | ✅ Extracted from the site's own JS bundle, then verified live |
| Search supports server-side date bounds? | ✅ **Yes** — better than every sibling |
| Category tree | ✅ `/api/blogs/{id}/category-list`, parent/child + post counts |
| Post list + pagination | ✅ `/api/blogs/{id}/post-list`, **`itemCount` ≤ 30** |
| Comments (the hard gate) | ✅ Solved — `objectId = {blogNo}_201_{logNo}`, `pool=blogid` |
| Comment reply tree | ✅ Nested in the same response, no second call |
| Neighbour graph | ✅ `/api/blogs/{id}/public-buddies?pageNo=` |
| In-blog post search | ✅ HTML path (`PostSearchList.naver`, 10 results/page) |
| Post body structure | ✅ Two editor branches measured, selectable via `smartEditorVersion` |

What remains for Phase 0 is **measurement, not discovery** — rate-limit behaviour, legacy-editor
coverage breadth, and unavailable-target response shapes. See `02-recon-findings.md` §11.

## Success criteria

Every implementation phase in `06-implementation-phases.md` carries an explicit verify gate. The
package is "done" for v1 when: all read primitives return schema-valid JSON anonymously; unit
tests are green offline (no network in CI); the wheel installs and runs with no browser anywhere;
and `agentic-blog` publishes to PyPI on a GitHub Release.

## Repo / PyPI facts (verified 2026-07-25)

| Item | Value |
|---|---|
| GitHub | `https://github.com/tjdwls101010/Agentic-Blog` (branch `main`) |
| PyPI dist | `agentic-blog` (`0.0.1` placeholder already published) |
| Publish workflow | `.github/workflows/publish.yml`, `on: release: published`, environment `pypi`, Trusted Publishing (OIDC). **Keep this filename and environment name.** Two hardening items in `05`: pin `pypa/gh-action-pypi-publish` to a commit SHA, and add the `check_tag_version.py` gate. |
| Already on `main` | `pyproject.toml` (`0.0.1`, `requires-python >=3.9` — **raise to `>=3.11` per D10**), `src/agentic_blog/__init__.py`, `LICENSE`, `README.md`, `.gitignore`, `publish.yml` |
