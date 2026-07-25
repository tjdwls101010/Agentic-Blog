# The Claude Skill — plan for a later session

**Do not build this during the package implementation session.** Build the package, ship it to
PyPI, then open a fresh session, load the `harness-creator` skill, and build the skill against the
*installed* CLI (D15).

Target: `Agentic Blog/.claude/skills/naver-blog/SKILL.md`.

## Why it is called `naver-blog`, not `blog`

A skill's directory name and `description` are the only things Claude sees when deciding whether
to load it. "blog" is a generic English word covering Tistory, Velog, Medium, WordPress, Substack
and every personal site on the internet — a skill named `blog` would be reached for constantly on
questions this tool cannot answer, and each of those is a wasted load plus a confused attempt.
`naver-blog` names the actual capability. (D14.)

## The division of labour this skill exists to enforce

The CLI is **single-target primitives with no `crawl` command**. That is deliberate and the skill
must state it as a positive instruction, not an apology:

> The CLI retrieves. **You navigate.** Deciding which blog to open next, which commenter is worth
> following, and when you have enough is the reason this skill exists.

If the skill reads as "here are seven commands, good luck," it has failed. What makes it worth its
tokens is the **navigation playbook** below — the chains a person actually runs — plus the traps
that only show up in practice.

## Draft `description` (the trigger surface)

The description must fire on the many ways a Korean-speaking user asks for this, and must
*exclude* the near-misses. Draft, to be refined with `harness-creator`'s guidance:

> Read Naver Blog (네이버 블로그) via the `agentic-blog` CLI — search posts, blogs, or bloggers on
> section.blog.naver.com; open a blog and its category tree; list or search that blog's posts; read
> a post's full body and comment thread; browse topic directories; and walk the neighbour (이웃)
> graph — then chain those to answer multi-hop questions. Use whenever the user wants something off
> Naver Blog, however they phrase it: "네이버 블로그에서 X 찾아줘", "이 블로그 글 읽어줘", "블로그
> 후기 좀 모아줘", "이 블로거가 X에 대해 뭐라고 썼어?", or when they hand over a `blog.naver.com`
> or `m.blog.naver.com` URL. NOT for other blog platforms (Tistory, Velog, Medium, WordPress,
> brunch) — this tool only reads Naver Blog. NOT for other Naver services: 카페, 지식iN, 뉴스,
> 포스트, 쇼핑, 플레이스 are different products with no tool here. NOT for developing or testing the
> `agentic-blog` package itself (that is ordinary repo work).

The three `NOT` clauses are load-bearing. The first two are the near-misses most likely to fire:
Korean users say "블로그" for Tistory too, and "네이버" for six other products.

## Structure

Mirror the sibling skills, with sections in this order:

1. **Get the tool, and get the current one.** `agentic-blog --version` against the PyPI simple
   index, upgrade if behind, say so in one line. Read the version from `--version`, not from
   `catalog` — `--version` has existed in every release. Read PyPI's version from the **simple
   index**, not the JSON endpoint, which can lag minutes behind a release.

   **One genuine difference from the siblings here, and the skill should say it:** those packages
   track rotating server tokens, so being a release behind can mean being *broken*. This package
   has no rotating tokens — the only things that ship as a release are body-parser fixes for a
   Naver template change and new commands. So the upgrade check is worth doing once at the start,
   but a stale install degrades gracefully rather than failing outright. Don't let the skill inherit
   the siblings' urgency about it.

2. **No setup. Ever.** Explicitly: there is no `login`, no `setup`, no browser, no account, no API
   key. `pip install` (or `uv tool install`) and read. This needs saying *because* the sibling
   skills all begin with an authentication dance, and a model that has seen those will look for one
   here and waste turns.

3. **Ask `catalog` and `schema` rather than trusting this document.** Both are generated from the
   code and cannot drift; a command list hard-coded into SKILL.md can.

4. **The navigation playbook** — the core section, below.

5. **Reading the output.** Every read command writes a file and prints one summary line to stderr.
   Post bodies are Markdown and can be tens of KB, so `Read` the file with an offset/limit rather
   than swallowing it whole. Decide what you need before you fetch.

6. **When something fails.** The exit-code table, and specifically: **exit 5 with "neighbour-only"
   is a normal outcome, not a malfunction.** An anonymous reader genuinely cannot see 이웃공개
   posts, and the right response is to tell the user that, not to retry or apologise.

7. **What not to do.** No writes exist (the CLI cannot post, comment, or like — don't offer). No
   `crawl`. Don't fan out across dozens of blogs without saying what you're about to do.

## The navigation playbook (the reason the skill exists)

These are the chains a person actually runs. Each names the commands and, more importantly, the
*judgment* at each hop.

**"네이버 블로그에서 X 후기 찾아줘"** — `search "X" --type post --sort sim`. Then read the two or
three most promising with `post`. Judgment: Naver Blog is saturated with 협찬/광고 posts. Signals
worth weighing before spending a `post` call: a body that discloses sponsorship, a blog whose
categories are all product reviews, a suspiciously uniform posting cadence. **Say what you filtered
and why** — silently dropping half the results makes the answer unauditable.

**"이 블로거 어떤 사람이야?"** — `blog <id>` for the category tree, then `posts <id> --limit 20`.
Judgment: the *category tree is the best single summary of a Naver blog* — its shape and post
counts tell you what the person actually writes about far faster than reading posts does. Read it
first.

**"이 블로그에서 X에 대해 쓴 글"** — `posts <id> --query "X"`. Do **not** pull the whole post list
and filter yourself; that burns the request budget on exactly the question users ask most.

**"이 사람 주변 사람들은 무슨 얘기해?"** — `buddies <id>`, pick a handful, `posts` each.
Judgment: bound the fan-out *before* starting and state the bound. A blog can have thousands of
neighbours; "I'll look at five" is a fine answer, "I read 4,982 blogs" is not a real one.

**"이 글 반응이 어때?"** — `post <url>` returns body and the full comment tree in one call.
Judgment: the comment thread is often more informative than the post. `author_blog_id` on each
comment is a **direct edge into that commenter's blog** — that is how you get from a post to the
community around it.

**"요즘 X 분야 블로그 뭐가 인기야?"** — `topics` to find the `seq`, then `topic <seq> --top`.

**Cross-cutting judgment the skill must state:** every hop costs a request at a 0.5s floor. A
three-blog sweep with comment threads is fine; a thirty-blog sweep is a minute of wall clock and
should be announced, not discovered by the user.

## Traps to carry into SKILL.md

These are the things a capable model would not derive, so they are the content actually worth the
tokens:

- **`brief` is not `body`.** Listing commands (`search`, `posts`, `topic`) populate `brief`
  (Naver's own truncated summary) and leave `body` null. Only `post` fetches the real text.
  Answering from `brief` and presenting it as the post's content is the single most likely failure
  mode of this skill.
- **A `logNo` alone is not a post reference.** Post ids are unique per blog, not globally. Always
  carry the blog id with it.
- **`visibility` is real.** A post marked `buddy` / `both_buddy` appears in listings but its body
  cannot be read anonymously. Report that as a fact about the post, not as an error.
- **Comment counts and reply counts are separate.** `count.comment` excludes replies;
  `count.total` includes them. Quoting the wrong one misstates how much discussion there was.
- **Korean relative timestamps.** `buddies` returns `updateTime` as a string like `"8분 전"` with no
  absolute time behind it. Don't convert it into a date.
- **Sponsored content is pervasive and rarely flagged structurally.** There is no `is_ad` field
  because Naver doesn't expose one reliably. Judgment, disclosed, is the only tool.

## Harness scope for that session

The skill is the deliverable; keep the rest minimal. Likely also worth generating:

- `Agentic Blog/CLAUDE.md` — the repo has one, but it is a **verbatim copy of the generic root
  `Agentic Crawler/CLAUDE.md`** (the four general coding guidelines) with nothing project-specific
  in it. Extend it, don't replace it: what the package is, the three runtime dependencies and why
  the list must stay short, "no auth layer exists — don't add one," the 0.5s floor, the PII rules,
  and where `docs/plan/` lives. Keep it under ~40 added lines — it is paid on every request.
- `.claude/harness-spec.md` — written by `harness-creator` as the record of what was generated.

**Probably not worth generating:** hooks, agents, or workflows. Nothing in this project needs a
deterministic guarantee that prose can't provide, and inventing one to fill out the harness is the
exact failure `harness-creator` warns about. Revisit only if a real "this must never happen"
appears — a plausible candidate is a pre-commit guard against committing a real capture, but that
is already covered by `scripts/check_fixtures_pii.py` plus `.gitignore`.

## Verify gate for the skill session

- `validate_harness.py` exits 0 with no errors.
- The `description` is checked against `harness-creator`'s triggering guidance, including the
  near-miss exclusions above.
- An end-to-end trial in a fresh session: a Korean prompt like
  *"네이버 블로그에서 제주도 3박4일 여행 후기 찾아서 괜찮은 거 두 개 요약해줘"* triggers the skill,
  installs or upgrades the CLI, runs `search` → `post`, discloses any 협찬 filtering, and answers
  from `body` rather than `brief`.
