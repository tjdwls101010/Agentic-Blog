# Skill session — kickoff

**Read this first.** It is the entry point for the session that builds the `naver-blog` skill.
Planned 2026-07-25 with `harness-creator`, against the **live, released `agentic-blog` 0.1.0**.

Companion documents, in the order you will need them:

| Doc | Phase | What it holds |
|---|---|---|
| this file | — | decisions, phase order, verify gates, what changed since `07-skill-plan.md` |
| `09-package-defects.md` | 1 | four confirmed defects, the live sweep protocol, fixtures, the v0.1.1 release |
| `10-skill-spec.md` | 2–3 | the SKILL.md specification, a full draft, E2E scenarios, the git procedure |

**This arc is complete** — package v0.1.2 on PyPI, skill merged (PR #5), all ten E2E scenarios
passing. The next arc, taking the tool from seven working commands to covering how people actually
use Naver Blog, starts at `11-coverage-goal.md`.

`07-skill-plan.md` is **superseded**. It was written before the package existed and several of its
factual claims turned out to be wrong; it now carries a banner listing the corrections. Do not
build from it.

---

## 1. What is being built, and why it is not just a command list

`agentic-blog` is the hand; this skill is the head. The CLI ships **single-target primitives and
deliberately no `crawl` command** (D3) — deciding which blog to open next, which commenter is worth
following, and when you have enough is exactly the judgment the skill exists to supply.

> The CLI retrieves. **You navigate.**

If the finished SKILL.md reads as "here are seven commands, good luck," it has failed. The catalog
already lists the commands, generated from the argument parser, and it cannot drift the way a copy
in prose can.

**Write principles, not rails.** This was the user's explicit correction during planning, and it
governs every line of the deliverable. A rule tells the model what to do and snaps on the first
case its author did not enumerate; a principle explains the shape of the domain so the model
re-derives the right move in cases nobody listed. Concretely, for this skill:

> **Rail:** "Disclose it when you filter out sponsored posts."
> **Principle:** "Naver Blog's review corpus is saturated with 협찬/체험단 content and Naver exposes
> no `is_ad` field — check the schema, there is none. Judgment is the only instrument available,
> and a judgment the reader cannot see is a judgment they cannot check."

The rail covers the one case it names. The principle also gets the model to the right behaviour on
a blog that is 90% 체험단, on a post whose disclosure is one line of fine print at the bottom, and
on a query where every result is sponsored and filtering would leave nothing — none of which the
rail mentions.

The litmus test for every line you are about to write: *given only the why I supplied, could the
model re-derive this and handle the case I forgot?* If no, it is a rail. Cut it or give it its
reason.

## 2. Decisions (agreed with the user, 2026-07-25)

Each records the choice **and the reasoning**, so you can re-derive intent for cases this plan did
not enumerate.

### S1 — The skill lives in this repo only

`Agentic Blog/.claude/skills/naver-blog/SKILL.md`. No symlink into `~/.claude/skills/`, no copy at
the workspace root.

**Why:** consistency with the four siblings, which all keep their skill inside their own repo, and
the skill stays version-locked to the package it documents.

**Known consequence, accepted by the user:** skills in a repo's `.claude/skills/` are
**directory-scoped** — they load only when the session is working under that directory. A user
asking "네이버 블로그에서 후기 찾아줘" from an unrelated project will not get this skill. This was
raised explicitly during planning and the user chose repo-only anyway. Do not "helpfully" add a
symlink; if the limitation becomes painful it is a separate decision about all five siblings at
once, not something to fix asymmetrically here.

### S2 — Deliverables: the skill, the spec, and a package fix pass. Not CLAUDE.md.

In scope: `SKILL.md`, `.claude/harness-spec.md` (mandatory under `harness-creator`), and the
package defect fixes described in `09-package-defects.md`.

Out of scope: `Agentic Blog/CLAUDE.md`. It is currently a verbatim copy of the generic root
`Agentic Crawler/CLAUDE.md` with nothing project-specific in it, and `07-skill-plan.md` recommended
extending it. **The user declined**, choosing the leaner scope. Leave it alone.

### S3 — Fix the package first, ship v0.1.1, then build the skill on top

Phase order is 1 → 2 → 3 (§3 below). Two pull requests.

**Why:** live verification during planning found that `posts` fails on 7 of 8 real blogs and that
single-post reads never return a timestamp. Two of the skill's headline navigation chains are
broken at the source. A skill written over that would fail in practice no matter how well authored,
and its E2E run would be blocked immediately.

### S4 — Find the rest of the defects before fixing, with a live sweep

7 commands × ~30 real blogs, roughly 300 requests, about five minutes at the 0.5s floor. Protocol
in `09-package-defects.md` §2.

**Why:** the four known defects were found in about thirty minutes of unsystematic poking, and they
share one root cause — a strict parser validated only against a narrow fixture corpus, so ordinary
Naver variation reads as "drift." That generator is still running; more defects of the same shape
almost certainly exist. Finding them before the fix pass means one release instead of three.

Precedent for the volume: Phase 0 recon already ran 355 anonymous serialized requests against these
hosts with no throttling observed (`02-recon-findings.md` §12.7).

### S5 — E2E is live and full-scenario

Real Korean prompts against the real network in a fresh session, not fixtures. Scenarios in
`10-skill-spec.md` §6.

**Why:** the failure this skill most needs to be protected against — answering from `brief` while
presenting it as the post's content — is invisible to any offline test. It only shows up when a
model actually navigates.

### S6 — Unobserved territory gets labelled as unobserved

For neighbour-only (이웃공개) posts, deleted posts, private blogs, and suspended blogs, SKILL.md
says what is known and explicitly says the rest has never been observed.

**Why:** recon spent 355 requests across 12 Korean and English search terms hunting for a specimen
of any of these four classes and **found none** (`02-recon-findings.md` §12.7 Q-3). The package
therefore never maps them — `TargetUnavailableError` is defined and never raised, which is
discipline, not an oversight. A skill that invents a diagnosis here would teach the model to state
a confident falsehood at exactly the moment a user is confused.

### S7 — Git: branch → PR → merge. One release, for the package fix only.

PR #1 (package fix) is tagged `v0.1.1` and published to PyPI, because a body-parser and listing fix
is something users feel. PR #2 (skill) gets no release — the skill is not part of the PyPI
distribution. A CHANGELOG line for the skill is enough.

## 3. Phase order and verify gates

Each phase has a gate. Do not start the next phase until its predecessor's gate is green.

```
Phase 1 — Package: sweep, fix, release              (09-package-defects.md)
  1.1 Live sweep, 7 commands x ~30 blogs      -> verify: defect inventory written to
                                                 scratch/sweep/ with a raw response saved
                                                 for every distinct failure signature
  1.2 Fix every confirmed defect              -> verify: pytest green, and each fix has a
                                                 regression test built from a real captured
                                                 response, not a hand-written fixture
  1.3 Re-run the sweep on the fixed build     -> verify: zero unexpected non-zero exits
  1.4 CHANGELOG, version bump, PR, merge,     -> verify: `pip index`/simple index shows
      tag v0.1.1, publish                        0.1.1; a clean-venv install of 0.1.1 runs
                                                 `posts` on three sweep blogs at exit 0

Phase 2 — Skill: generate                           (10-skill-spec.md §1-5)
  2.1 Re-verify every factual claim in the      -> verify: the claims table in 10-skill-spec.md
      draft against the installed 0.1.1            §3 is re-checked line by line and annotated
  2.2 Write SKILL.md                            -> verify: validate_harness.py exits 0
  2.3 Write .claude/harness-spec.md             -> verify: validate_harness.py reports no drift
  2.4 Re-read `description` against
      harness-creator's triggering guidance      -> verify: near-misses present, intent-level
                                                 triggers present, under 1,536 chars

Phase 3 — Verify and ship                           (10-skill-spec.md §6-7)
  3.1 Live E2E, fresh session, Korean prompts   -> verify: every scenario's pass criteria met
  3.2 Fix what E2E surfaced, re-run             -> verify: re-run is clean
  3.3 CHANGELOG line, PR, merge. No release.    -> verify: PR merged, main green
```

## 4. What changed since `07-skill-plan.md`

That document was written during package planning, before any code existed. Live verification on
2026-07-25 contradicted several of its claims. Recorded here so nobody re-derives them.

**Wrong, do not carry forward:**

- *"`count.comment` excludes replies; `count.total` includes them."* No such fields exist. The real
  shape is `Post.comment_count` plus a nested `Comment.replies[]`. There is a genuine trap here, but
  it is a different one — see `10-skill-spec.md` §3.
- *"`buddies` returns `updateTime` as a string like `8분 전`."* The `Blog` model has no such field.
- *"Exit 5 with 'neighbour-only' is a normal outcome."* `TargetUnavailableError` is never raised
  anywhere in the source. Exit 5 in practice means not-found. What a neighbour-only post read
  actually does is **unobserved** — see S6.

**Right, and worth keeping:**

- The skill name `naver-blog`, and the reasoning for it (D14): "blog" is a generic English word
  covering Tistory, Velog, Medium and every personal site online, so a skill named `blog` would be
  reached for constantly on questions this tool cannot answer.
- "No setup, ever" deserves its own section *because* the sibling skills all open with an
  authentication dance, and a model that has seen those will hunt for one here and waste turns.
- `brief`-versus-`body` is the single most likely failure mode of this skill.
- The category tree is the best one-shot summary of a Naver blog.
- Sponsored content is pervasive and structurally unflagged.

**Missing entirely, and important:**

- `stop_reason` and the 100-request-per-invocation budget were not mentioned at all.
- Output is a **bare JSON array** with no envelope — even single-target reads return a
  one-element list.
- Exit code **2 is unassigned** in this package, unlike every sibling.

## 5. Standing rules for the implementing session

1. **Verify before you write.** Every factual claim that lands in SKILL.md is checked against the
   installed CLI first. This is not ceremony: the superseded plan's three wrong traps would each
   have shipped as confident prose, and a model reading SKILL.md has no way to know it is being
   lied to. `10-skill-spec.md` §3 is a table built for exactly this — re-run it, annotate it.
2. **`brief` is not `body`.** It is worth stating twice because it is the failure that would make
   this skill worse than useless: a plausible summary of a truncated teaser, presented as the post.
3. **Do not port sibling machinery.** No login, no session, no cookie jar, no browser, no
   `[browser]` extra, no doc-id registry, no exit-2 handling. D1 and D2 are load-bearing and this
   is the one sibling with no auth layer at all.
4. **Ask before widening scope.** The user chose a lean deliverable twice during planning
   (declining CLAUDE.md, declining the /tmp rule). If Phase 1 uncovers something that looks like it
   wants a bigger fix, surface it rather than absorbing it.
