# Phase 2–3 — The `naver-blog` skill

## 1. Identity

```
Agentic Blog/.claude/skills/naver-blog/SKILL.md
```

Single file. **No `references/`, no `scripts/`.**

The split axis for progressive disclosure is *invocation pattern, not volume*: a second file earns
its place only when the model picks exactly one branch per invocation, the way a skill covering
three cloud providers earns `references/{aws,gcp,azure}.md`. Nothing here branches — every
invocation needs the navigation judgment, the data-shape traps, and the failure handling together.
Splitting by length would hand a future invocation a routing decision that buys it nothing and
occasionally makes it read the wrong file, or miss that a file exists at all. If the draft feels
long, cut content; do not shard it.

**Directory name is the interface.** `naver-blog` is what makes it `/naver-blog`; the frontmatter
`name` is only a display label. The reasoning for the name (D14) still holds: "blog" is a generic
English word covering Tistory, Velog, brunch, Medium, WordPress and every personal site online, so
a skill directory named `blog` would be reached for constantly on questions this tool cannot answer.

**Language: English**, matching all three sibling skills. The example user phrasings inside the
description stay Korean, because that is what users actually type.

## 2. Frontmatter

`description` is the **entire** trigger mechanism. A "when to use this skill" section in the body
does nothing — the body only loads after the trigger decision has already been made. Everything
triggering-relevant goes here, triggering-critical clause first, and the whole thing is truncated
at 1,536 characters in the listing.

Two properties this draft is built around. First, current models **under-trigger** — they skip a
skill that would have helped more often than they load one that turns out unneeded — and the costs
are asymmetric: a needless load costs a little context, a missed load costs the entire skill. So it
leans deliberately toward firing. Second, the `NOT` clauses are load-bearing rather than decorative:
Korean speakers say "블로그" for Tistory just as readily, and "네이버" covers six other products, so
without boundary language this description would quietly steal triggers it cannot serve.

```yaml
---
name: Naver Blog retrieval
description: Read Naver Blog (네이버 블로그) with the agentic-blog CLI — search posts and blogs, open a blog's category tree, list or search one blog's own posts, read a post's full body and its comment thread, browse the directory's topics, and walk the neighbour (이웃) graph — then chain those to answer multi-hop questions. Use whenever the user wants something off Naver Blog, however they phrase it: "네이버 블로그에서 X 찾아줘", "이 블로그 글 읽어줘", "X 후기 좀 모아줘", "이 블로거가 X에 대해 뭐라고 썼어?", "이 사람 주변에선 무슨 얘기해?", "요즘 블로그에서 뭐가 인기야?", or when they hand over a blog.naver.com or m.blog.naver.com URL. Also use when the user wants Korean first-hand opinion — 후기, 리뷰, 방문기, 내돈내산 — about a product, place, restaurant, or trip and has not named a source, because Naver Blog is where that lives. NOT for other blog platforms: Tistory, Velog, brunch, Medium, WordPress, Substack. NOT for other Naver services — 카페, 지식iN, 뉴스, 포스트, 쇼핑, 플레이스 are different products with no tool here. NOT for developing, testing, or releasing the agentic-blog package itself, which is ordinary repo work.
allowed-tools: Bash(agentic-blog:*), Bash(uv:*), Bash(pipx:*), Bash(curl:*), Read
---
```

Notes on the choices:

- The **"Korean first-hand opinion"** clause is the one addition over the superseded draft, and it
  is the most valuable line in the description. It fires on intent rather than keyword: a user
  asking "이 식당 진짜 괜찮아?" never says "네이버 블로그", but that is exactly where the answer is.
- `allowed-tools` mirrors the siblings and covers what the body actually calls: the CLI itself,
  the two install paths, `curl` for the PyPI version check, and `Read` for the output files.
- **Do not set `disable-model-invocation`** — this skill is pure retrieval with no side effects, so
  there is nothing the user needs to time themselves.
- Re-read this description against `harness-creator`'s `references/skills.md` before shipping, and
  read it against the three sibling descriptions to confirm none of them are competing for the same
  request.

## 3. Verified facts — re-check this table before writing a word

Everything below was confirmed live against **0.1.0** on 2026-07-25. The right-hand column flags
what the Phase 1 fixes will change. **Re-run each row against the installed 0.1.1 and annotate it**
— the superseded `07-skill-plan.md` shipped three confident, wrong traps, and a model reading
SKILL.md has no way to detect that it is being lied to.

| # | Verified fact | How it was confirmed | After v0.1.1 |
|---|---|---|---|
| 1 | 9 commands: `catalog`, `schema` (offline) + `search`, `blog`, `post`, `posts`, `buddies`, `topics`, `topic` | `--help`, `catalog` | same |
| 2 | Output is a **bare JSON array** — no envelope, no `items` wrapper. Single-target reads return a one-element list | every command | same |
| 3 | stderr summary: `N <noun>, range A..B, stop reason: R. Saved to PATH`. Nothing useful on stdout | `cli.py:312` + observed | same |
| 4 | `stop_reason` ∈ `limit_reached`, `no_next_page`, `no_matches`, `max_requests`, `single_target` | `retrieve.py:32` | same |
| 5 | Exit codes 0 / 1 / 3 / 4 / 5. **Exit 2 is unassigned** — unlike every sibling | `errors.py` `_EXIT_CODE_SPEC` | same |
| 6 | 0.5s floor between requests, in code, un-bypassable | `config.py:15`; recon measured 0.500028s | same |
| 7 | **100 requests per invocation**, then `stop_reason: max_requests` | `config.py` `DEFAULT_MAX_REQUESTS` | same |
| 8 | No `login` / `setup` / `status` / `doctor`. No credentials anywhere | `--help` | same |
| 9 | Listings populate `brief` and leave `body` null; only `post` fetches real text | `search`, `posts --query` | same |
| 10 | `comment_count` is the **true total** (35) while `comments[]` holds only what you fetched (3, under `--comment-limit 3`) | live | same |
| 11 | `visibility` is populated in listings (`"public"`) and **null on single `post` reads** | 5 of 5 posts | **re-check** |
| 12 | `captured_at` is when *you* scraped, not when anything happened | schema | same |
| 13 | `Comment.author_blog_id` is a direct edge into that commenter's own blog | schema | same |
| 14 | `blog <id>` returns the category tree: `category_no`, `parent_category_no`, `name`, `post_count`, `is_open` (12 nodes for `leehazang`) | live | same |
| 15 | `Blog.post_count` and `Blog.buddy_count` are **null even from `blog`** — the per-category `post_count` is where the real numbers are | live | same |
| 16 | `buddies` returning 0 with `no_matches` is **normal**, not an error — many blogs expose no public neighbour list | `leehazang` | same |
| 17 | `posts --query` rejects `--raw` ("--query does not support --raw"), `--category`, and `--sort popular` | CLI error; `retrieve.py:550` | same |
| 18 | `search --type` is `post` \| `blog` \| `id`; **both `blog` and `id` emit `Blog` objects** | live | same |
| 19 | `topics` returns 32 topics with `seq`, `name`, `group_name` | live | same |
| 20 | `media[]` is extracted from the body — 19 items on one ordinary post | live | same |
| 21 | `post` takes a URL, or `blog_id` and `log_no` as two positionals | `catalog` | same |
| 22 | Single `post` reads return `created_at: null` | 5 of 5 | **FIXED — rewrite** |
| 23 | `posts` exits 4 on blogs containing video | 7 of 8 blogs | **FIXED — rewrite** |
| 24 | `posts --query` stamps KST with `Z` (9h off) | live cross-check | **FIXED — rewrite** |
| 25 | `body` leaks `> SE-TEXT { … } SE-TEXT` editor markers | 2 of 4 posts | **FIXED — rewrite** |

Rows 22–25 exist so you can confirm the fixes actually landed in the installed build. If any of
them still reproduces against 0.1.1, Phase 1 is not done — go back, do not document the bug as a
trap.

## 4. What the body must carry, and why

Order matters: a long body buries its own key instructions where attention thins, so the two things
most likely to be got wrong (`brief` vs `body`, and what the counts mean) sit early rather than in
a trailing "gotchas" section.

**1. Opening — the division of labour.** The CLI retrieves; the model navigates. State it as a
positive instruction, not an apology for a missing `crawl`.

**2. Get the tool, and get the current one.** `agentic-blog --version` against the PyPI **simple
index** (the JSON endpoint lags minutes behind a release and will report the previous version).
Read the installed version from `--version`, never from `catalog` — `--version` has existed in
every release, whereas reading it out of a table-of-contents command can crash on exactly the old
installs the check exists to catch.

There is a **genuine difference from the siblings here and the skill should say it.** Those
packages track rotating server tokens, so being a release behind can mean being broken. This
package has no rotating tokens and no moving authentication; a stale install mostly degrades
gracefully. But 0.1.0 specifically is the exception — its `posts` command fails on most blogs — so
the check is worth doing once at the start. Give the model the shape of the risk rather than
inheriting the siblings' urgency wholesale.

**3. No setup. Ever.** No `login`, no `setup`, no browser, no account, no API key, no cookie. `pip
install` and read. This needs saying *because* every sibling skill opens with an authentication
dance, so a model that has seen one will hunt for the equivalent here and waste turns finding
nothing.

**4. Ask `catalog` and `schema`, don't trust this file.** Both are generated from the code, so they
are correct for the version actually installed. A command table copied into SKILL.md silently
describes the wrong version the moment the package updates — and the model would trust the copy
over the truth. Anything needed to *call* a command comes from the catalog. What SKILL.md carries
is only what the catalog cannot: how to decide what to call, and how to read what comes back.

**5. Reading the output.** Results go to a **file**; stderr gets one summary line; stdout has
nothing useful. Always pass `--output` with a path you chose. The payload is a **bare JSON array**
even for single-target reads — a model expecting `{"items": [...]}` will index into nothing. Post
bodies run to tens of KB, so `Read` with an offset and limit rather than swallowing one whole.

**6. `brief` is not `body`.** The single most likely failure of this skill. Listing commands
populate `brief` — Naver's own truncated teaser, often with `...` mid-sentence — and leave `body`
null. Only `post` fetches real text. Answering from `brief` produces a fluent, plausible summary of
a teaser, presented as the post's content, and nothing about the output announces the substitution.

**7. Counts and flags say less than they look like they do.**
- `comment_count` is the discussion's true size; `comments[]` is only what this call fetched.
  Reporting the array's length as the number of comments understates it, silently, by however much
  `--comment-limit` cut off.
- `visibility` arrives on listings, not on single `post` reads — so a post you fetched directly
  carries no visibility signal at all, and its absence is not evidence of anything.
- `captured_at` is when *you* scraped. Sorting or deduping by it produces an ordering that means
  nothing; `created_at` is the real time and it can be null.
- `Blog.post_count` and `Blog.buddy_count` are null even from `blog`. The per-category `post_count`
  in the tree is where real numbers live.

**8. Navigation — the reason this file exists.** Two questions place any command: *what handle do
you already hold*, and *how narrow is what it returns*. Prefer the command whose handle you have,
and among those the narrowest. Then the handles themselves — these are what make chaining possible:

- a post's `blog_id` → `blog`, `posts`, `buddies`
- a post's `blog_id` + `log_no` → `post`
- a comment's `author_blog_id` → that commenter's own blog. **This is the edge from a post to the
  community around it**, and it is not obvious from the schema.
- a `Topic`'s `seq` → `topic`

Give 4–5 worked chains, each naming the *judgment* at the hop rather than just the commands:

- **"X 후기 찾아줘"** — `search --type post`, then `post` the two or three most promising. The
  judgment is which ones are worth spending a read on.
- **"이 블로거 어떤 사람이야?"** — `blog` first. The **category tree is the best single summary of a
  Naver blog**: its shape and per-category post counts describe what someone actually writes about
  far faster than reading their posts does. Reading posts first is the expensive way to learn what
  one call already told you.
- **"이 블로그에서 X에 대해 쓴 글"** — `posts --query`. Pulling the whole post list and filtering by
  hand burns the request budget on the question users ask most often.
- **"이 글 반응 어때?"** — `post` returns body and comment tree in one call. The thread is often
  more informative than the post.
- **"이 사람 주변 사람들은 무슨 얘기해?"** — `buddies`, then `posts` on a few. Note that an empty
  `buddies` result is normal; many blogs simply do not expose a public neighbour list.

**9. `stop_reason` — is this the answer or part of it?** `no_next_page` / `no_matches` /
`single_target` mean the data is complete for what was asked. `limit_reached` means your own
`--limit` stopped it. `max_requests` means the 100-request budget stopped it, not the data — the
result is a fragment and reporting it as complete is simply wrong.

**10. What a chain costs, and why bounding it is correctness rather than courtesy.** Every hop is a
real request at a 0.5s floor with 100 per invocation. A three-blog sweep with comment threads is
fine; a thirty-blog sweep is a minute of wall clock and should be announced before it starts, not
discovered by the user afterwards. The second half matters more than the pacing: **report the shape
of what you actually did.** A chain that sampled 5 of 60 neighbours but presents itself as "what the
neighbours think" is a wrong answer wearing a confident summary.

**11. Sponsored content — a domain fact, not a rule.** Naver Blog's review corpus is saturated with
협찬 / 체험단 / 광고 posts, and **Naver exposes no `is_ad` field** — check the schema, there is
none, because Naver does not reliably publish one. So judgment is the only instrument available,
and a judgment the reader cannot see is a judgment they cannot check. Signals worth weighing before
spending a `post` call: disclosure language in the body, a category tree that is entirely product
reviews, a suspiciously uniform posting cadence. State the principle once, make it concrete with
two or three signals, and stop — do not enumerate a rule per case.

**12. When something fails.** `catalog` prints what each exit code *means*; SKILL.md says what to
*do*, and the theme is that most failures here are informative rather than transient, so retrying
the same command is rarely the fix.

- **1** — usage error or an invalid identifier. An `invalid choice` specifically means an
  out-of-date install: upgrade, never work around it.
- **3** — HTTP 429. Stop that line of work rather than looping. Recon ran 355 serialized requests
  without seeing one, so a 429 is a real signal about volume, not noise.
- **4** — the response structure changed. No self-heal exists in this package (there is no browser
  and no doc-id registry to re-anchor, unlike the siblings), so the fix ships as a release: upgrade,
  or tell the user it needs a newer version.
- **5** — the target does not exist.
- **There is no exit 2.** Say so explicitly. Every sibling uses exit 2 for an auth failure, and a
  model carrying that habit will misread something here.

**13. The honest edge — what nobody has observed.** Neighbour-only (이웃공개 / 서로이웃공개) posts,
deleted posts, private blogs, and suspended blogs. What is known: listings carry a `visibility` of
`buddy` or `both_buddy`, and a post so marked is very likely unreadable anonymously. What is *not*
known: what actually happens when you try — recon spent 355 requests across 12 Korean and English
search terms hunting for a specimen of any of these four classes and found none, so the package
deliberately never mapped them. Tell the model to report an odd failure on such a post as what it
is rather than inventing a diagnosis, and that an anonymous reader genuinely cannot see 이웃공개
content, which is a fact about the post and not a malfunction to apologise for.

**14. What does not exist.** No writes of any kind — the CLI cannot post, comment, follow, or like,
so do not offer. No `crawl`. And keep captures out of the repo: **this project tracks `.json` test
fixtures, so `.gitignore` will not catch a scrape saved into the working tree**, and a scrape
committed to a repo outlives the question it was collected for.

## 5. What must NOT go in

- **A command/flag table.** That is `catalog`'s job and a copy drifts.
- **Any sibling's authentication machinery** — login, session, cookies, checkpoints, ban risk,
  throwaway accounts, `doctor --refresh`. None of it exists here. D1 and D2 are load-bearing.
- **A hard `/tmp` rule.** The siblings force it because they scrape logged-in data — follower
  lists, signed CDN URLs — where the user plausibly becomes a data controller. This package makes
  anonymous, public-only reads: everything it fetches is what any person sees in a logged-out
  browser. Inheriting that urgency here would be a rule with no derivation behind it. The narrow,
  real risk is §4.14's "do not commit captures," which is one line.
- **Prescribed `--limit` numbers.** A number carried over from an example is a number nobody chose.
  Size each one from the question being asked.
- **Anything a capable model already knows.** No general advice about summarizing well, citing
  sources, or writing clean output. What earns tokens here is what the model cannot derive: the
  data-shape traps, the cost model, and the domain's sponsorship problem.

## 6. E2E — live, fresh session, real prompts

Run in a **fresh session** with the working directory inside `Agentic Blog/` (the skill is
directory-scoped — see S1), against **0.1.1 installed from PyPI**, not the repo checkout.

Each scenario names what actually distinguishes pass from fail. "It answered" is not a criterion —
several of these fail in ways that produce a fluent, confident, wrong answer.

| # | Prompt | Passes only if |
|---|---|---|
| 1 | "네이버 블로그에서 제주도 3박4일 여행 후기 찾아서 괜찮은 거 두 개 요약해줘" | Skill triggers. Runs `search` then `post`. **The summary contains detail present only in `body`, not in `brief`** — check this by hand against the fetched file. Any 협찬 filtering is disclosed with its reason. |
| 2 | "blog.naver.com/leehazang 이 블로거 어떤 사람이야?" | Calls `blog` first and reasons from the category tree, rather than paging through `posts` to infer the same thing at ~10× the cost. |
| 3 | "leehazang 블로그에서 제주도 얘기한 글만 찾아줘" | Uses `posts --query`. Does **not** pull the full list and filter in-model. |
| 4 | "이 글 반응 어때? <a post URL with 30+ comments>" | Reports the discussion size from `comment_count`, not from `len(comments)`. If it fetched a subset, it says so. |
| 5 | "이 블로거 주변 사람들은 무슨 얘기해? <blog URL>" | States the fan-out bound **before** starting, then reports the scope it actually covered. On an empty `buddies` result, reports "no public neighbour list" rather than an error. |
| 6 | "요즘 블로그에서 여행 쪽 뭐가 인기야?" | `topics` → `topic --top`. Does not substitute a plain `search`. |
| 7 | "이 식당 진짜 괜찮아? <식당 이름>" (never says "네이버" or "블로그") | **The skill triggers at all** — this is the intent-level trigger clause from §2 doing its job. |
| 8 | "티스토리에서 X 찾아줘" | Skill either does not fire, or fires and immediately says this tool only reads Naver Blog. It must not silently search Naver Blog and present the result as if it were Tistory. |
| 9 | "blog.naver.com/이런블로그없음123456 읽어줘" | Reports not-found once. Does not retry, and does not invent a reason. |
| 10 | With **0.1.0 deliberately installed**: any scenario above | Notices the version gap, says so in one line, upgrades, then proceeds. |

Scenario 1 is the important one — it is the `brief`/`body` failure, and it is invisible to any
offline test. Verify it by reading the fetched JSON yourself, not by trusting the answer's fluency.

Scenario 7 is the trigger test. If it fails, the description needs work, not the body — the body
never loaded.

`harness-creator` ships `scripts/run_e2e.py` for driving these headlessly. Its permission handling
(`--isolate` plus `--dangerously-skip-permissions`) is a documented best guess rather than something
empirically confirmed, so read `references/e2e-testing.md` before the first run and say so to the
user rather than presenting a headless pass as authoritative.

## 7. Ship it

1. `.claude/harness-spec.md` — the record of what was generated and why. Mandatory under
   `harness-creator`; `validate_harness.py`'s drift check compares it against what is on disk.
2. `python "/Users/seongjin/.claude/skills/harness-creator/scripts/validate_harness.py" --path .` →
   **exit 0, zero errors.** Not finished until it does.
3. Re-read the `description` against `harness-creator`'s `references/skills.md` triggering guidance
   and against the three sibling descriptions, checking for competition.
4. A `CHANGELOG.md` line under Unreleased. **No version bump, no tag, no release** — the skill is
   not part of the PyPI distribution (S7).
5. Branch → PR → merge.

### Definition of done

- `posts` runs at exit 0 on the blogs from `09-package-defects.md` §1A, from a clean install of
  0.1.1 off PyPI.
- Every row of §3 re-verified against 0.1.1 and annotated; rows 22–25 confirmed fixed.
- `validate_harness.py` exits 0.
- All ten E2E scenarios pass, scenario 1 checked by hand against the fetched file.
- Both PRs merged, `main` green, `v0.1.1` visible on the PyPI simple index.
