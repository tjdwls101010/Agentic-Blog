# Implementation Phases (with verify gates)

Ordered; loop each phase until its verify gate passes. Prefer many small green steps over one big
one. **No account is needed for any of this** — every phase can be verified anonymously.

---

## Phase 0 — Re-verify recon, then close the five measurement questions

The endpoint discovery in `02-recon-findings.md` was done on 2026-07-25 and every ✅ entry was
confirmed with pure `curl`. Start by **re-running the consolidated endpoint table (§9)** to confirm
nothing moved, then answer the five open questions in §11. These are measurements, not discovery —
none of them can block the architecture, but each one turns a guess in the error mapping into a
fact.

- **Q-1 — Rate-limit reality.** Sustain a run at the 0.5s floor (a few hundred requests across all
  three hosts) and record whether anything throttles, and if so what it looks like: status code,
  body, whether a `Retry-After` appears, and whether it is per-host. Feed the result into
  `RateLimitedError` and the exit-3 mapping. **If nothing blocks, say so explicitly in the code
  comment** — an unexercised error path should be labelled as such, not presented as measured.
- **Q-2 — Legacy-editor coverage.** Sample posts across a wide date range (2005 → today) and across
  several blogs. Confirm `body.py`'s fallback degrades to readable text rather than raising. Record
  the `smartEditorVersion` values actually observed.
- **Q-3 — Unavailable-target shapes.** Capture the exact anonymous responses for: a deleted post, a
  private blog, a neighbour-only post, a suspended blog, a nonexistent `blogId`, and a nonexistent
  `logNo` on a real blog. These become the `NotFoundError` / `TargetUnavailableError` signatures.
- **Q-4 — In-blog search HTML stability.** Decide and implement how `PostSearchList.naver`
  extraction fails when the template changes: a typed `BodyParseError` (exit 4), not a silent
  empty result.
- **Q-5 — `orderBy` vocabulary.** Confirm the accepted values for section search and for in-blog
  search rather than assuming the two are symmetric.

**Verify:** every row of §9 still returns its documented shape; Q-1 through Q-5 each have a written
answer committed into `02-recon-findings.md` (append a §12 "Phase 0 results" rather than editing the
2026-07-25 measurements in place — the dated record is what makes drift detectable later); raw
captures stay in gitignored `scratch/` and nothing account-linked or personal is committed.

## Phase 1 — Scaffold, packaging, offline commands

Amend the existing `pyproject.toml` (version → `0.1.0`, `requires-python` → `>=3.11`, add the three
dependencies, add `[project.scripts]`). Create `src/agentic_blog/` skeleton: `config.py` (paths +
0.5s floor), `errors.py` (typed hierarchy + the single exit-code table), `identifiers.py`. Implement
`catalog` + `schema` end-to-end against a stubbed `model.py`. Set up `ci.yml`, harden `publish.yml`
(SHA-pin + version gate, `05`), `.pre-commit-config.yaml`, `scripts/`, `.gitignore`.

**Verify:** `agentic-blog --version / --help / catalog / schema / schema --json` all work with no
network; `ruff` clean; the sdist-first build-and-smoke job is green on both OS legs;
`test_identifiers.py` and `test_cli.py`'s catalog gate are green.

## Phase 2 — Client + endpoints + one vertical slice (`search`)

`client.py` (per-host headers with the mandatory `Referer`, `_throttle`, XSSI strip, envelope error
mapping, request budget), `endpoints.py` (the `SECTION` group), `parse.py` (search envelopes),
`model.py` (`Post` / `Blog` + `to_dict` + generated schema), `retrieve.py` (`search` with
pagination), and the `search` subcommand with all three `--type` values.

Do the whole vertical slice before widening. Getting `search --type post|blog|id`, the XSSI strip,
the `<strong class="search_keyword">` stripping, the epoch-ms timestamp normalisation, and the
schema generation right once means the remaining commands are mechanical.

**Verify:** `agentic-blog search "커피" --type post --limit 20 --output /tmp/s.json` writes
schema-valid `Post` JSON with readable Korean (`ensure_ascii=False`); `--type blog` and `--type id`
emit `Blog`; `--since`/`--until` visibly narrow the result set (server-side, `02` §3.1); the 0.5s
floor is observed; `jsonschema` validates the output. Unit tests for endpoints/client/parse/model
green.

## Phase 3 — Per-blog surface (`blog`, `posts`, `buddies`, `topics`, `topic`)

Add the `MOBILE` endpoint group and the remaining `SECTION` endpoints. `blog` (profile +
`category-list` with separator filtering), `posts` (`post-list` with `itemCount` clamped to 30,
`--category`, `--sort popular`, `--notices`), `buddies` (`public-buddies`, paginating on
`totalPageCount`), `topics` (`DirectoryList`), `topic` (`DirectoryPostList`, `--top`).

**Two traps to encode here, both silent-failure shaped:**
`post-list`'s `totalCount` is `0` even on blogs with thousands of posts — paginate until a short
page, never trust that field. And `itemCount=31` is a hard error, so the clamp belongs in
`endpoints.py`, not in a caller's argument default where a future call site can bypass it.

**Verify:** each command returns schema-valid output from live requests with the correct
`stop_reason`; `blog` returns a category tree whose `parent_category_no` links resolve and whose
separator rows are gone; `posts --category N` genuinely narrows; `buddies` paginates past page 1 on
a blog with thousands of neighbours; `topic` `seq` values from `topics` all resolve. Fixture-driven
unit tests for every endpoint green.

## Phase 4 — Post bodies and comments (`post`)

`body.py` — the only HTML in the project. SmartEditor ONE component walk over `.se-main-container`
dispatching on the `se-*` class, the legacy `div.post_ct` fallback, `data-lazy-src` image handling,
Markdown emission plus the parallel `media[]`. Then the `CBOX` endpoint group: `comments-info` for
`blog_no`, then `web_naver_list_json.json` with `pool=blogid` and
`objectId = {blog_no}_201_{log_no}`, building the nested `Comment` tree from `replyList` /
`parentCommentNo` / `replyLevel`. Then the `post` subcommand, and `posts --query` against
`PostSearchList.naver`.

Carry the three non-derivable constants into the source **with the comment explaining why**
(`03-architecture.md`). Someone will eventually try to "clean up" a literal `201`; the comment is
what stops them. And **never call `web_naver_view_log_json.json`** — it is a telemetry beacon the
site fires alongside the list request, not a read.

**Verify:** `agentic-blog post https://blog.naver.com/<id>/<logNo>` returns a Markdown body that
reads correctly for both a SmartEditor ONE post and a pre-2015 legacy post, with `media[]`
populated; the comment tree matches the post's visible comment and reply counts, including nested
replies, with `author_blog_id` populated so the chain to the next blog exists; `--no-comments`
issues no CBOX requests; `posts --query` returns only matching posts and demonstrably does **not**
go through `post-list`. `test_body.py` green including the `BodyParseError` case.

## Phase 5 — Hardening, docs, release prep

`redact.py` wired to every diagnostic surface. `TargetUnavailableError` distinguishing private /
neighbour-only / deleted / suspended from Q-3's captured signatures. Write `README.md`,
`CHANGELOG.md` (Keep-a-Changelog), `DISCLAIMER.md` (**tone not weakened**, D13),
`SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `docs/wiki/` mirroring the sibling set.
Bump to `0.1.0` in both `pyproject.toml` and `__init__.py`.

**Verify:** the full offline suite is green across all three `lint-and-test` legs; the sdist-first
smoke is green on both OS legs; a broad **live e2e pass** exercises every command and every flag
against public blogs (documented, outputs deleted, no PII committed); a neighbour-only post and a
nonexistent blog both exit 5 with a message that says which; both version declarations read
`0.1.0`. No tag is created in this phase.

## Phase 6 — Publish

Open the release PR and merge it to `main` before tagging. After the merge:

```bash
git fetch --tags origin refs/heads/main:refs/remotes/origin/main &&
MERGED_MAIN=$(git rev-parse origin/main) &&
git tag -a v0.1.0 "$MERGED_MAIN" -m "v0.1.0" &&
test "$(git rev-parse 'v0.1.0^{commit}')" = "$MERGED_MAIN" &&
git push origin refs/tags/v0.1.0 &&
gh release create v0.1.0 --verify-tag --generate-notes --title "v0.1.0"
```

This ordering makes the tag resolve to merged `main` and verifies it before the push and before the
GitHub **Release** triggers `publish.yml`.

**Verify:** after the Release publishes, run the clean-install gate on a clean machine state —

```bash
uv tool install agentic-blog &&
agentic-blog --version &&                       # -> 0.1.0
agentic-blog search "커피" --type post --limit 3 &&
agentic-blog post "https://blog.naver.com/<id>/<logNo>"
```

This is the whole first-run story: install, then read. **If it needs any step in between, something
went wrong** — there is no `setup`, no `login`, and no browser to provision, and that is the
property most worth protecting in this package.

## Phase 7 — The Claude skill (SEPARATE later session)

Not part of the package build. See `07-skill-plan.md`.

---

## Hard constraints (do not violate — from CLAUDE.md + the siblings + D1)

- **Minimum code, surgical changes, no speculative abstractions or unrequested features.** The
  agreed non-goals — writes, login-gated features, other Naver services, `crawl`/batch/daemon —
  are not to be built.
- **No `auth.py`, `session.py`, `docids.py`, `transaction.py`, `_stealth_init.js`, `scrapling`,
  Playwright, or a `[browser]` extra.** Three runtime dependencies: `httpx`, `platformdirs`,
  `lxml`. If a fourth seems necessary, ask first.
- **No `login` / `setup` / `status` / `doctor` commands, and no `--profile` flag.** Nothing is
  stateful.
- **0.5s rate floor is non-bypassable**; single-target primitives only.
- **HTML stays in `body.py`.** `parse.py` is JSON-only.
- **PII**: `scratch/`, `*.raw.*`, `output/` gitignored; fixtures synthetic and PII-scanned; live
  tests assert shapes, never content; never commit a real capture.
- **UTF-8 everywhere**: `ensure_ascii=False`, Korean-safe output filenames, no ASCII assumptions
  when truncating or measuring.
- **DISCLAIMER tone not weakened.**
- **Artifacts in English** (code, comments, docs, CLI output) even though the data is Korean.
- If a scope change beyond this plan seems needed, **ask first.**
