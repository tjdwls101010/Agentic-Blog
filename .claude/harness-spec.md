# Harness Spec — agentic-blog

## Context

Python 3.11+ package (`agentic-blog`, CLI `agentic-blog`, PyPI dist `agentic-blog`), hatchling
build, pytest + ruff, single maintainer. Published to PyPI; **v0.1.1 and v0.1.2 shipped 2026-07-25**
as part of this same pass (see "Phase 1" below). This repo carries a `CLAUDE.md`, but it is a verbatim copy of
the workspace-root general coding guidelines with nothing project-specific in it — extending it was
proposed during planning and **the user declined**, choosing the leaner scope. No `.claude/`
directory existed before this pass. Planning interview in Korean; generated harness in English,
matching the four sibling skills and all CLI output.

**Sibling precedent.** `Agentic Blog` is the fifth of five sibling scrapers (Facebook, X, Threads,
Reddit). `agentic-threads`'s `threads/SKILL.md` is the closest structural template. The critical
divergence is that **this sibling has no authentication layer at all** — no login, session, cookie
jar, browser, or token registry — which deletes roughly half of what a sibling skill spends its
words on, and makes several of their reflexes actively wrong here (most sharply: there is no exit
code 2).

## Goals

Let Claude read Naver Blog through the published `agentic-blog` CLI and **chain the primitives
itself**. The CLI ships single-target reads and no `crawl` command by design (D3), so deciding which
blog to open next is the skill's entire reason to exist.

The skill must NOT restate the CLI's flags — `agentic-blog catalog` is generated from the argument
parser and is correct for whatever version is installed, so a copy in prose would describe the wrong
version the moment the package updates.

The `description` must trigger on any "get something off Naver Blog" phrasing including a bare
`blog.naver.com` URL, **and** on the intent-level case where a user wants Korean first-hand opinion
(후기/리뷰/방문기/내돈내산) without naming a source. It must correctly **not** trigger on three
near-misses: other blog platforms (Korean speakers say "블로그" for Tistory just as readily), other
Naver products (카페/지식iN/뉴스/포스트/쇼핑/플레이스), and developing the package itself.

## Behavior inventory

| id | behavior/knowledge/constraint | layer | component | status |
|----|-------------------------------|-------|-----------|--------|
| B1 | Check installed version against the PyPI **simple index** at task start; if behind, announce + upgrade. Reason is parser fixes, not rotating tokens | skill | naver-blog | generated |
| B2 | **There is no setup** — no login/session/browser/account. Stated explicitly because every sibling opens with an auth dance | skill | naver-blog | generated |
| B3 | `catalog` / `schema` are the flag and output contracts; never restate them in prose | skill | naver-blog | generated |
| B4 | Every read writes a JSON **file**; stdout carries nothing. Always pass `--output`, then `Read` | skill | naver-blog | generated |
| B5 | Output is a **bare JSON array** — no envelope; single-target reads return a one-element list | skill | naver-blog | generated |
| B6 | **`brief` is not `body`** — listings populate `brief` and null `body`; only `post` fetches real text. The skill's primary failure mode | skill | naver-blog | generated |
| B7 | `comment_count` is the true total; `comments[]` is only what this call fetched | skill | naver-blog | generated |
| B8 | `visibility` arrives on listings, never on a single `post` read | skill | naver-blog | generated |
| B9 | `created_at` is null on `post` when Naver labelled the post relatively ("7시간 전"); the listing surfaces carry an exact time | skill | naver-blog | generated |
| B10 | Handles for chaining; `author_blog_id` is the edge from a post into the commenter's blog; a `log_no` alone is not a post reference | skill | naver-blog | generated |
| B11 | The **category tree is a blog's best one-shot summary** — `blog` before `posts` | skill | naver-blog | generated |
| B12 | `posts --query` for in-blog search, rather than listing everything and filtering in-model | skill | naver-blog | generated |
| B13 | Empty `buddies` is ordinary, not an error | skill | naver-blog | generated |
| B14 | `stop_reason` semantics; `max_requests` means partial, not finished | skill | naver-blog | generated |
| B15 | Cost model: 0.5s floor, 100-request budget. Bound fan-out **and report the shape actually covered** — a sampled answer presented as complete is wrong | skill | naver-blog | generated |
| B16 | Sponsored content is pervasive and **Naver publishes no `is_ad` field**. It does publish the opposite claim — `isBuyWithMyOwnMoney`, surfaced as `search --self-purchased` — but that is the **blogger's self-declaration**, so it narrows the pool without cleaning it, and its absence means almost nothing. Judgment stays the instrument, and an invisible judgment is uncheckable | skill | naver-blog | generated |
| B20 | `buddy_count` counts only **disclosed** neighbours; `0` means "publishes no list", not "has none" — Naver's private total is routinely orders of magnitude larger | skill | naver-blog | generated |
| B21 | `--type tag` and `--type post` index different things: full text finds mentions, tags find posts an author considered to be *about* the term. Neither dominates | skill | naver-blog | generated |
| B22 | Naver's search stops answering after ~1,000 posts per query whatever total it reports, so `no_next_page` on a broad query is not "you have them all" | skill | naver-blog | generated |
| B17 | Exit-code handling; **there is no exit 2**, unlike every sibling | skill | naver-blog | generated |
| B18 | The unobserved region (이웃공개 / deleted / private / suspended) is labelled unobserved rather than diagnosed | skill | naver-blog | generated |
| B19 | No writes exist; no `crawl`; keep captures out of the repo because it tracks `.json` fixtures | skill | naver-blog | generated |

## Layer routing

Everything routed to **one skill**. Nothing here earned a hook, an agent, a workflow, a rule, or a
CLAUDE.md line:

- **No hooks or permissions.** A hook buys a deterministic guarantee prose cannot give. There is no
  "this must never happen" in a read-only, anonymous, side-effect-free tool. The one candidate — a
  guard against committing a real capture — is already covered by `scripts/check_fixtures_pii.py`
  in pre-commit plus `.gitignore`'s `scratch/`. Inventing one to round out the harness is the exact
  failure `harness-creator` warns about.
- **No agents.** No context-hungry, read-heavy role whose conclusion alone matters back in the main
  thread; retrieval results are the deliverable.
- **No workflows.** The fan-out shape here is different every time (how many blogs, how deep, which
  hops), which is precisely the case where a fixed script becomes a flexibility tax and
  natural-language guidance wins.
- **No `.claude/rules/`.** Nothing is scoped to one part of the tree.
- **No CLAUDE.md changes.** Proposed and declined by the user (see Context).

**Consciously accepted limitation:** a skill in a repo's `.claude/skills/` is directory-scoped — it
loads only when the session is working under that directory, so it will not fire for a user asking
about Naver Blog from an unrelated project. This was raised explicitly during planning; the user
chose repo-only for consistency with the four siblings. Fixing it asymmetrically for one of five is
worse than the limitation. If it becomes painful, it is one decision about all five siblings.

## Components

| path | kind | purpose |
|---|---|---|
| `.claude/skills/naver-blog/SKILL.md` | skill | the whole harness (see inventory) |
| `.claude/harness-spec.md` | spec | this file |

Single file, **no `references/` and no `scripts/`**. The split axis for progressive disclosure is
invocation pattern, not volume: a second file earns its place only when the model picks exactly one
branch per invocation. Nothing here branches — every invocation needs the navigation judgment, the
data-shape traps, and the failure handling together. Splitting on length alone would hand a future
invocation a routing decision that buys it nothing and occasionally makes it read the wrong file.

## Phase 1 — the package fixes this skill depends on

Planning verified the released 0.1.0 against live Naver and found four defects; a 210-run sweep
(7 command shapes × 30 stratified blogs) found two more and quantified all of them. **Three of the
seven read commands were failing on the majority of ordinary blogs**, including both hops of the
skill's most common chain. That work shipped as **v0.1.1** before the skill was written.

| command | 0.1.0 | 0.1.1 |
|---|---|---|
| `posts` | 9/30 | 30/30 |
| `posts --sort popular` | 17/30 | 30/30 |
| `posts --notices` | 16/30 | 30/30 |
| `post` | 28/30 | 30/30 |

Shared root cause: a strict validator — correct policy — exercised only against a narrow synthetic
fixture corpus, so ordinary Naver variation was indistinguishable from real drift. The 768-test
suite made no network calls. The synthetic notice fixture had been hand-authored to a shape the live
API never sends, so fixture and parser agreed with each other and disagreed with reality.

Detail in `docs/plan/09-package-defects.md`; sweep protocol reproducible via `scratch/sweep/`.

**v0.1.2** then closed the one gap v0.1.1 deliberately left open and flagged rather than absorbed:
the notice card spells its comment total `commentCount`, and states its visibility as
`postOpenType` rather than through the `buddyOpen`-family flags every other listing uses — so
notice visibility had been correct only because `_search_visibility` fell through to its default on
three absent fields.

**The skill hardcodes no version**, and must not start to: it reads `--version` and compares against
the PyPI simple index, which is what keeps it correct across releases like these two.

## Validation

- 25-row claims table in `docs/plan/10-skill-spec.md` §3, re-verified row by row against a clean
  install of 0.1.1 from PyPI before SKILL.md was written.
- `validate_harness.py` exits 0.
- Ten live E2E scenarios (`docs/plan/10-skill-spec.md` §6), run against 0.1.1 from PyPI. Scenario 1
  (`brief` vs `body`) is checked by hand against the fetched file, because a wrong answer there is
  fluent and self-consistent.

## Change history

- **2026-07-25** — Initial pass. Planning (PR #3) → package fixes and v0.1.1 (PR #4) → this skill
  (PR #5) → notice-card fields and v0.1.2 (PR #6). Supersedes `docs/plan/07-skill-plan.md`, which
  carried three factual claims that live checks disproved. Skill unchanged by v0.1.2; only this
  spec's Context and Phase 1 sections were updated, since the skill states no version.

- **2026-07-25 (planning, no components changed)** — Coverage arc, planning half. A second live
  sweep against a **disjoint** 32-blog sample (`docs/plan/12-coverage-gap-analysis.md`) returned
  224/224 exit 0 on v0.1.2 and found one real defect: `Blog.post_count` and `Blog.buddy_count` are
  null by construction — neither `Blog` constructor assigns them — while `parse.py` already
  validates both upstream values and discards them. A gap analysis then enumerated 33 reading
  behaviours and put anonymous coverage at **17/26**. Agreed scope for the implementation arc is in
  `docs/plan/13-build-spec.md`: 내돈내산 filter, tag search, and a JSON migration of in-blog search.

  **B16 must be corrected when the skill is next edited.** It states Naver publishes no `is_ad`
  field and that judgment is the only instrument. The first half still holds — there is no ad flag.
  The second is now wrong: every search item carries `isBuyWithMyOwnMoney` and `isMarketPost`.
  `isBuyWithMyOwnMoney` is the blogger's **self-declaration**, not a sponsorship guarantee (a
  filtered result was observed carrying `true` with no "내돈내산" text anywhere in it, so it is a
  structured field rather than text matching). The skill must not present that filter as "ad-free".
  Rationale and wording in `13-build-spec.md` §5.1. **The skill file was deliberately not edited
  this session** — this arc was planning-only, and the correction ships with the commands that make
  the flag reachable.

- **2026-07-25 (implementation)** — Built the agreed scope and released **v0.2.0**: `search
  --self-purchased`, `search --type tag`, `posts --query` migrated off HTML scraping to Naver's
  in-blog search API, and the two permanently-null `Blog` fields repaired. B16 corrected as planned
  above; B20–B22 added for the facts the new surfaces introduce. The skill still hardcodes no
  version.

  One planning error surfaced during implementation and is worth keeping: `13-build-spec.md` §2.1
  specified `/api/search/v1/tag` for tag search on the strength of its envelope matching. Building
  the fixture from a real capture showed the envelope matches but the **items do not** — that
  endpoint returns tag *groups* (`{postCount, tag, blogs:[…]}`), not posts, and its nested cards use
  a third highlight class (`<em class="srch">`). `--type tag` ships against `/api/tags/search/post`,
  which is genuinely a flat post list. Verifying an envelope is not verifying a payload.

  The pre-release sweep also caught a crash present in **every prior release**: Naver truncates
  `briefContents` mid-emoji, leaving an unpaired surrogate that cannot be UTF-8 encoded, so
  `posts`/`blog` aborted with `UnicodeEncodeError` on 3 of 30 blogs. Fixed at the two text
  normalizers. It was outside the agreed scope, and shipping a coverage release over a known crash
  on ordinary data was not defensible.
