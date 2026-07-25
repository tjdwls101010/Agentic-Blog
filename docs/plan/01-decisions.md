# Decision Log

Decisions agreed with the user during the 2026-07-25 planning interview (Korean), most via
explicit AskUserQuestion. Each records the choice **and the reasoning**, so the implementer can
re-derive intent for cases the plan didn't enumerate. Load-bearing overrides are marked.

Several decisions were **made after live recon changed the facts** — where that happened, the
superseded reasoning is preserved rather than deleted, so a future session doesn't re-litigate it.

---

### D1 — Anonymous only: no login, no account, no credentials

**Choice (user, AskUserQuestion):** v1 is **logged-out only**. No `login` command, no credential
store, no `session.json`, no cookie jar, no account of any kind.

**Why:** recon proved every public surface reads cleanly with zero cookies. The three
login-requiring surfaces — neighbour-only (이웃공개/서로이웃공개) posts, the 이웃새글 feed, and
personal notifications — are a small slice, and buying them costs an entire credential subsystem
plus per-user account risk. The stated goal is a package other people can install and run; anything
requiring each user to have and risk a Naver account defeats that. Anonymous also means **zero
account-ban risk** and **no credential PII to protect**.

**Status: VERIFIED**, not assumed — see `02-recon-findings.md` §1.

**Consequence (load-bearing):** `auth.py`, `session.py`, `docids.py`, `transaction.py`,
`_stealth_init.js`, `scrapling`, Playwright, and the `[browser]` optional extra **must not exist
in this project.** Do not port them from a sibling out of habit. Also: neighbour-only posts must
be *surfaced with their visibility flag*, never silently dropped, so the caller can tell "no such
post" from "you can't see this one" (`post-list` exposes `buddyOpen` / `bothBuddyOpen` / `notOpen`).

### D2 — Transport: pure `httpx`. No browser at runtime, ever.

**Choice:** every request in the shipped package is a plain `httpx` GET. There is no browser in
the dependency tree, no headless fallback, and no `[browser]` extra.

**Why:** unlike Reddit — where the browser is the only thing that carries anti-bot clearance —
Naver serves these endpoints to ordinary HTTP clients. Recon ran several hundred `curl` requests
without a single block. Adding a browser would trade the project's single largest advantage
(instant install, millisecond reads, nothing to provision) for nothing.

**Required on every request:** a `Referer` header and an ordinary browser `User-Agent`. These are
not evasion; they are what the endpoints require to serve their normal response. **Do not add
TLS-fingerprint impersonation** (`curl_cffi`, `tls-client`) or any other technique whose purpose
is to defeat bot detection — nothing in recon suggested it is needed, and it is not something this
project will ship.

**Note on recon tooling:** a headless Playwright capture *was* used during planning to observe two
lazily-loaded requests (comments, neighbours). That was a **discovery tool**, not a runtime
dependency — both endpoints were re-verified with pure `curl` afterwards, and neither the browser
nor Playwright appears anywhere in the shipped package.

### D3 — Command surface: 7 read primitives + 2 offline meta commands

**Choice (user, revised upward mid-interview):**
`search`, `blog`, `posts`, `post`, `topics`, `topic`, `buddies`, plus `catalog` and `schema`.

**Why:** the goal is Claude navigating Naver Blog like a person, and these are the seven moves a
person actually makes. The user initially chose a 7-command core that **excluded `buddies`**,
because at that point the neighbour endpoint was an unresolved recon gate. Recon then found
`/api/blogs/{id}/public-buddies` and verified it with pure `curl`, so the risk disappeared and the
user added it. **`buddies` is the only way to answer "what is this blogger's circle reading?"** —
all four siblings ship a followers/following equivalent, and the comment-author chain
(`profileUserId`) is a poor substitute because it only reaches people who happened to comment.

**Explicitly folded in rather than given their own commands:** the blog's popular posts and notice
posts become `posts --sort popular` / `--notices` rather than separate commands, because they are
variants of the same listing with the same output object.

### D4 — Post bodies extracted to lightweight Markdown, with a parallel `media[]`

**Choice (user, AskUserQuestion with previews):** the body becomes a Markdown-ish `body` string —
`> ` for quotations, `![caption](url)` for images, `[title](url)` for link cards, `---` for
horizontal rules — with images and videos **also** collected into a structured `media[]` array.

**Rejected:** (a) flat plain text, which loses the quote/body distinction and drops link cards
entirely; (b) emitting both a `text` string *and* a full `blocks[]` tree, which doubles output size
and forces Claude to decide which representation to read on every single post.

**Why:** SmartEditor ONE tells us each block's type, so throwing that away is a strict loss —
and Markdown is the one structured form Claude can read *and quote from* without a second parsing
step. `media[]` exists because "what images are in this post" is a question the prose form answers
badly.

### D5 — Comments are a v1 requirement, and the gate is now closed

**Choice (user, AskUserQuestion):** `post` returns the body **and** the full comment thread,
including nested replies. Comments are not deferred and not behind a flag.

**Why:** on Naver Blog the comment thread is half the conversation, and `profileUserId` on each
comment is a **direct edge into another blog** — exactly the multi-hop chaining this project exists
for.

**Status when the decision was taken:** an open gate (eight blind parameter guesses all returned
`code: 3300`). **Status now: SOLVED and curl-verified.** The two things that made it unguessable
are recorded in `02-recon-findings.md` §6 and must be carried into the code as commented
constants: `pool=blogid` (not `cbox5`/`cbox9`) and `objectId = {blogNo}_201_{logNo}` — a literal,
undocumented `201` between the two ids.

**Do not call `web_naver_view_log_json.json`.** The site fires it alongside the list call; it is a
telemetry beacon, not a read.

### D6 — Rate floor: non-bypassable **0.5s** between requests

**Choice (user):** `MIN_REQUEST_PAUSE_SECONDS = 0.5`, clamped in code regardless of any flag, env
var, or library entry point, with a stderr note when a lower value is raised.

**Why:** there is **no account to ban** (D1), so the only exposure is an IP-level block, and Naver
exposes no `x-ratelimit-*` headers to pace against. 0.5s matches `agentic-x`'s floor and keeps
realistic work — walk a category tree, read ten posts — at human-ish speed rather than
conspicuously fast. The siblings' 1.0s exists because a *banned account* is unrecoverable; that
stake doesn't apply here.

**This is a policy choice, not a measured constraint** — recon hit no throttling at all. Phase 0
Q-1 must confirm nothing blocks over a sustained run and record what a block actually looks like,
so the error mapping is real rather than assumed.

### D7 — HTML parsing: `lxml`, and emphatically **not** crawl4ai

**Choice (user, AskUserQuestion):** `lxml` for the post-body and in-blog-search HTML.

**Rejected — crawl4ai** (the user asked about it explicitly):
1. **Dependency regression.** crawl4ai is Playwright-based and pulls litellm, nltk, pillow, numpy.
   The project's single largest advantage is "no browser, pure `httpx`, instant install" (D2);
   adopting crawl4ai to parse one field would destroy it.
2. **Worse output.** crawl4ai's value is inferring content from pages whose structure is *unknown*.
   We know Naver's structure exactly — the `se-*` component classes name each block's type. Generic
   extraction would flatten captions, quotations, link cards and place-maps into undifferentiated
   text, and its pruning filters can drop short paragraphs outright.
3. **Wrong project.** Generic page extraction is `Ultra Fetch`'s job. Pulling it in here dissolves
   the boundary between the two.

**Rejected — stdlib `html.parser` only:** no CSS selectors means hand-rolling the SmartEditor ONE
walk, which is *more* code and more breakage points than `lxml` — the opposite of CLAUDE.md's
minimum-code principle.

`selectolax` was considered (faster, smaller) and passed over: smaller ecosystem, narrower selector
support, and no precedent in the sibling projects.

### D8 — In-blog post search ships in v1, via the one HTML endpoint

**Choice (user, AskUserQuestion):** `posts <blogId> --query <q>` is in v1, implemented against
`blog.naver.com/PostSearchList.naver` (server-rendered HTML, 10 results per page).

**Why:** "what has this blog written about X" is one of the most common things a person does on a
Naver blog. Without it, Claude has to pull hundreds of posts and filter client-side, which blows
the request budget on exactly the queries users ask most.

**Rejected:** (a) deferring to v1.1 — leaves a hole in the primitive set; (b) routing through
`section` search and filtering by `blogId` — that only finds posts ranked highly enough to surface
in a global search, so it silently returns nothing for most blogs.

**Trap to encode (load-bearing):** passing `searchText`/`keyword` to `/api/blogs/{id}/post-list`
returns HTTP 200 with the **unfiltered** list. It looks like a successful search and is not one.
Never implement in-blog search that way; add a regression test asserting it isn't.

**Honesty requirement:** this is the only primitive whose *existence* depends on an HTML template.
Document that plainly, and make it fail as a typed drift error rather than silently returning
nothing (Phase 0, Q-4).

### D9 — Search source: `section.blog.naver.com` internal JSON. Not the official Open API.

**Choice (assistant recommendation after recon, accepted by user):** search is served exclusively
by `section.blog.naver.com/ajax/SearchList.naver`.

**Rejected — Naver's official Open API** (`openapi.naver.com/v1/search/blog.json`). Unlike Reddit's
approval-gated Data API this one is genuinely available — self-service registration, free, ~25,000
calls/day, clean ToS. It was rejected anyway, for two reasons:
1. **It breaks distributability.** Every user would have to register and supply their own
   `Client ID`/`Secret`. "Install and read" (D1's whole point) becomes "install, register an
   application, configure credentials, then read."
2. **It returns far less.** Five fields (`title`, `link`, `description`, `bloggername`, `postdate`)
   — no comment count, no like count, no category, no thumbnail, no topic classification, and
   **no blog-search or nickname-search type at all**, so `search --type blog|id` would be
   impossible.

**Residual value:** if Naver ever hardens the `section` endpoints, the official API is a known
fallback for `--type post` only. Keep the search function's signature independent of its transport
so that swap stays cheap.

**Consequence:** this places the project in the **same ToS-gray position as all four siblings** —
see D13.

### D10 — Python `>=3.11`

**Choice (user):** raise the committed `requires-python` from `>=3.9` to `>=3.11`.

**Why:** matches all four siblings, so their code can be referenced directly; allows `X | None`
unions and exception groups; and lets `scripts/check_tag_version.py` use stdlib `tomllib` instead
of adding a `tomli` dependency.

### D11 — Output model: file + one-line stderr summary; Claude reads the file

**Choice:** every read command writes results to a `--output` path (default: a timestamped file
under the platform data dir, **never cwd/repo**) and prints only a one-line summary to stderr.
`--format json` (array) or `ndjson`.

**Why:** proven across all four siblings. It hands context control to Claude — *it* decides how
much of the file to `Read` — and keeps third-party PII out of the repo. This matters more here
than in the siblings: a single Naver blog post body can be tens of kilobytes of Markdown, so
dumping results to stdout would be actively hostile to the caller's context window.

### D12 — English artifacts

**Choice:** SKILL.md, code, comments, docstrings, README, wiki, CLI output — all English. The
planning interview is Korean, and the *data* is overwhelmingly Korean, but the **artifacts** are
English. **Why:** matches all four siblings; most stable substrate for skill-triggering and
technical vocabulary.

**Naver-specific caveat:** everything must be UTF-8 clean end to end. Titles, bodies, comments,
category names and nicknames are Korean; JSON output must be written with `ensure_ascii=False`,
and the code must never assume ASCII when truncating, slugifying an output filename, or measuring
a summary's length.

### D13 — ToS / PII posture: same strength as the siblings; say so plainly

**Choice (user, AskUserQuestion):** keep the siblings' full-strength `DISCLAIMER.md`, minus only
the account-ban section, which genuinely does not apply (D1).

**What it must say, unsoftened:** this tool reads Naver Blog through endpoints Naver publishes for
its own front end, not through a sanctioned integration; Naver's terms restrict automated
collection; users accept the consequences (IP blocks, terms termination); no commercial use and no
bulk/ML-training dataset construction.

**Do not weaken this to "it's just public data."** Naver Blog is a **high-PII medium** — real
names, faces, workplaces, children, home neighbourhoods, daily routines — and `buddies` +
`posts` + comment authors together make aggregation across a person's social circle trivial. The
third-party-PII discipline is therefore not boilerplate here: temp paths never the repo, never
`git add` a capture, fixtures are hand-authored synthetic skeletons, a CI/pre-commit PII scanner,
and redaction on every diagnostic surface (never the output file itself).

### D14 — Naming triple, and the skill is called `naver-blog`

**Choice:** PyPI dist `agentic-blog`; import package `agentic_blog`; console command
`agentic-blog`; env override `AGENTIC_BLOG_DATA_DIR` (with a matching `--data-dir` flag).
`__version__` lives in `src/agentic_blog/__init__.py`, gated three ways (tag == `pyproject` ==
source) at release by `scripts/check_tag_version.py`.

**Note the departure from the siblings:** they use `*_PROFILE_DIR` and a `--profile` flag because
they store per-account credential profiles. **This project has no profiles and no credentials**
(D1), so a `--profile` flag would be a meaningless knob and `PROFILE_DIR` would name something that
doesn't exist. The only thing under the data dir is `output/`. Do not port `--profile`.

**The skill, however, is `naver-blog`** (`.claude/skills/naver-blog/SKILL.md`) — deliberately not
matching the package name. **Why:** a skill's directory name and description are how Claude decides
whether to load it. "blog" is a generic English word that also means Tistory, Velog, Medium,
WordPress and every personal site; a skill named `blog` would be reached for on questions this tool
cannot answer. `naver-blog` names the actual capability.

### D15 — The skill is a later, separate session

**Choice:** build the package first, publish to PyPI, **then** build
`.claude/skills/naver-blog/SKILL.md` in a fresh session using the `harness-creator` skill. It wraps
the *installed* CLI and points at its `catalog`/`schema`, not at a repo checkout. See
`07-skill-plan.md`.

**Why:** mirrors the sibling workflow; keeps the package correct before wrapping it.

---

## Superseded reasoning (kept for the record — do not re-litigate)

**"Comments may not be reachable."** During the interview, comments were an open gate and the plan
contemplated a fallback (parsing the comment HTML page) or deferral to v1.1. **Closed:** the CBOX
JSON API works anonymously over pure `curl`; there is no fallback path and no deferral. See §6 of
the recon findings.

**"`buddies` is too risky for v1."** The neighbour list was excluded from the first command-surface
answer because `/api/blogs/{id}/buddies` returned HTTP 500 under every guessed parameter set.
**Closed:** the correct endpoint is `public-buddies?pageNo=`, verified with pure `curl` against a
blog with 4,982 neighbours across 100 pages.

**"Use Claude in Chrome (profile `rararat`) to find the best search approach."** The Chrome
extension blocked all `naver.com` navigation ("site not allowed due to safety restrictions"), so
the question was answered a different and better way: mining the site's own AngularJS bundles for
every `/ajax/*` call site with its exact parameter object, then verifying live. **That technique is
the one to repeat when these endpoints rot** — it is strictly more complete than network
observation, which only shows requests that happened to fire.

---

## Open questions for Phase 0 of the implementation session

All data-layer unknowns were closed during planning. What remains is measurement — full detail in
`02-recon-findings.md` §11:

- **Q-1 — Rate-limit reality.** No rate-limit headers exist and nothing blocked during recon.
  Confirm the 0.5s floor survives a sustained run and capture what a block actually looks like.
- **Q-2 — Legacy-editor coverage.** Two editor generations were measured; Naver has shipped more
  over ~20 years. Sample across a wide date range and confirm the fallback degrades to readable
  text rather than throwing.
- **Q-3 — Unavailable-target shapes.** Capture exact anonymous responses for a deleted post, a
  private blog, a neighbour-only post, a suspended blog, and a nonexistent `blogId`.
- **Q-4 — In-blog search HTML stability.** Decide how `PostSearchList.naver` extraction fails: a
  typed drift error, or a documented degradation.
- **Q-5 — `orderBy` vocabulary.** `sim`/`date` confirmed for search, `recentdate` for in-blog
  search. Confirm the full accepted set rather than assuming symmetry.
