# Build spec — the tag loop, and the body the parser was throwing away

**Session:** 2026-07-26. Measured live and anonymously before anything was written.
**Inputs:** `12-coverage-gap-analysis.md` (the deferred list and the two unverified rows),
`14-coverage-arc-results.md` (what 0.2.0/0.2.1 shipped), plus an independent second-model review
of the package and of the skill.
**Output:** the scope below, shipped as **v0.3.0**.

Everything marked ✅ was measured this session. Counts are from real responses, not estimates.

---

## 1. What this arc found

Two threads. The first is a coverage question the last arc left open. The second is a defect
class the last arc's own discipline predicts, found in the primitive that matters most.

### 1.1 The tag loop was left half-open ✅

0.2.0 shipped `search --type tag`, so Claude can find posts *by* a tag. Nothing in the package
can report the tags a post *carries* — `Post` has no such field — so the loop that makes tags
useful for navigation stops after one hop. You can enter the tag graph; you cannot move through it.

`12-…` §2.5 recorded this as **unverified**, having found no tag markup in two mobile post
documents and said so rather than guessing. That observation was correct and the conclusion drawn
from it was too narrow: the tags are not in the post HTML because they are served **separately**.

`https://blog.naver.com/BlogTagListInfo.naver?blogId=&logNo=&viewType=S` answers anonymously.

| measurement | result |
|---|---|
| posts sampled (directory topics 20, tag search 12, post search 20) | 52 |
| HTTP 200 | **52 / 52** |
| envelope key set identical | 52 / 52 — `{taglist}`, entries `{msg, logno, tagName, encTagName}` |
| posts carrying at least one tag | **52 / 52** |
| tags per post | 1–30, commonly 7–15 |
| `logno` disagreeing with the request | 0 |
| double-encoded or malformed `tagName` | 0 |

Boundaries measured, not assumed: one post per call (a comma-joined `logNo` returns `{}`, not a
multi-post answer, so this cannot be batched); an all-digit blog id works; a nonexistent `logNo`
returns `{"taglist": []}` rather than an error; a nonexistent blog returns 404 HTML; the mobile
host 302s, so this is a PC-host call and the only one in the package.

### 1.2 `posts --query` has a tag-shaped sibling ✅

`/api/blogs/{blogId}/search/tag` — row 16 of `12-…` §2.1, recorded there as "200, route valid"
and nothing more. Measured properly this session, it returns the **same envelope and the same 23
item keys** as the in-blog post search that `posts --query` already uses. `parse_mobile_search_page`
and `build_mobile_search_post` need no change.

Two behaviours that differ from its sibling and would otherwise have been assumed:

- **Page size is 30, not 20.** Measured across three pages on `naver_diary`.
- **`sortType` is ignored.** Sending `sim`, sending `date`, and sending nothing all return
  `sortType: "date"`. Offering a sort flag here would be offering a control that does nothing.

`totalPage` is also wrong in a way worth recording: 318 results reported `totalPage: 16`, which is
318/20 — computed against a page size the endpoint does not use. The package's standing rule of
stopping on a short page rather than on a reported total is what makes that harmless.

### 1.3 `post` returns an incomplete body on most real posts ✅

`body.py:_se_one` handles six SmartEditor ONE component families and **silently skips every other
one**. Because any one supported component sets `meaningful`, the command exits 0 and writes a body
that reads as complete.

54 posts, drawn from six directory topics and three searches:

| component family | occurrences | handled |
|---|---|---|
| `se-text` | 1185 | ✅ |
| `se-image` | 984 | ✅ |
| `se-quotation` | 130 | ✅ |
| `se-horizontalLine` | 113 | ✅ |
| `se-sticker` | 90 | ❌ |
| `se-imageStrip` | 90 | ❌ |
| `se-oglink` | 46 | ✅ |
| `se-placesMap` | 37 | ✅ |
| `se-video` | 24 | ❌ |
| `se-imageGroup` | 22 | ❌ |
| `se-sectionTitle` | 20 | ❌ |
| `se-table` | 15 | ❌ |
| `se-oembed` | 9 | ❌ |
| `se-material` | 5 | ❌ |
| `se-custom` | 2 | ❌ |
| `se-wrappingParagraph` | 1 | ❌ |

**43 of 54 posts (80%) contain at least one dropped family.**

The loss is not uniform, and saying so precisely matters more than the headline:

- **Prose is close to intact.** Text lost per post measured 0, 22, 34, and 71 characters on four
  worked examples — headings and table cells, not paragraphs. `se-text` carries the writing, so
  the skill's `brief`-versus-`body` guidance is not undermined.
- **The media inventory is materially wrong.** `madeathome` reported 38 images and dropped 28.
  `0613hottehotte` reported 70 and dropped 24. Roughly a third of a photo-heavy post's images are
  absent from both `media[]` and the rendered body.
- **`Media.kind` promises two values the package cannot produce.** The schema publishes
  `photo | video | sticker | unknown`; `_image_blocks` is the only producer and always writes
  `photo`. **`video` and `sticker` are unreachable.** This is the same defect class as
  `Blog.post_count` in 0.2.0 — a published contract that no code path can satisfy — and it is
  found here by the same method, reading what the builders can actually assign.

DOM shapes measured so the fix does not have to guess:

| family | where its content lives |
|---|---|
| `se-imageStrip`, `se-imageGroup` | ordinary `<img data-lazy-src>` — the existing image extractor works unchanged |
| `se-sticker` | one `<img src="…storep-phinf…">` |
| `se-table`, `se-sectionTitle`, `se-material`, `se-custom`, `se-wrappingParagraph` | visible text, and for `se-material` an `<a href>` and a thumbnail |
| `se-video`, `se-oembed` | **no `img`, no `iframe`, no visible text** — a JSON blob in `<script class="__se_module_data" data-module="{…}">` carrying `thumbnail`/`thumbnailUrl`, `mediaMeta.title`, `inputUrl` |

### 1.4 Three fields validated and then dropped ✅

The failure mode `12-…` §1.3 named and 0.2.0 fixed, still present in three more places.

- **`topic --top` drops `thumbnail_url`.** `parse.py:423` requires `thumbnailUrl` on every top
  card; `build_directory_post` never assigns it. Measured: 5 of 5 cards returned
  `thumbnail_url: null` with the URL plainly present under `--raw`.
- **Notice cards are consumed without being validated.** `parse_post_list` passes notices through
  `_validate_mobile_post(full=False)`, which stops after title and thumbnail, yet
  `build_mobile_post` then reads `commentCount` and `_notice_visibility` reads `postOpenType`.
  If Naver renames either, every notice quietly reports `comment_count: null` and
  `visibility: null` instead of raising drift. 0.1.2 fixed *reading the right field names*; it did
  not put those names behind the validator.

### 1.5 `blog <URL>` reports a blog that exists as not found ✅

```
agentic-blog blog https://blog.naver.com/i9yaaa_    → exit 5, "blog not found: https://blog.naver.com/i9yaaa_"
agentic-blog posts https://blog.naver.com/i9yaaa_   → exit 0, works
agentic-blog post  https://blog.naver.com/i9yaaa_/224357887887 → exit 0, works
agentic-blog buddies https://blog.naver.com/i9yaaa_ → exit 0, works
```

`fetch_blog` passes its argument to `search_list` as a **search keyword** and then compares the
returned `blog_id` against that same raw string, so it never routes through `parse_blog_ref` — the
normalizer every other command reaches via `_mobile_url`. Three commands accept a URL and one
denies the blog exists.

This is worse than an inconvenience. The skill's own trigger text is "when they hand over a
blog.naver.com or m.blog.naver.com URL"; the most natural first call on a pasted URL is `blog`,
and its answer is a confident, wrong exit 5.

### 1.6 A stop reason that reports completion it did not achieve ✅

`fetch_blog` returns early when fewer than two requests remain. Given **exactly** two, it spends
both on the profile and the category tree, skips the buddy count, and returns `single_target` —
the reason that means "there was one thing and I got it". `buddy_count` is null because the budget
ran out, and nothing in the result says so. Reachable from the library, not from the CLI, whose
budget is 100.

---

## 2. Scope

Adopted, with the reason each one clears the bar this project has used since `12-…` §2.2 —
anonymous, actually used by people, and **changes the answer**:

| # | change | why it is in |
|---|---|---|
| 1 | `Post.tags`, populated by `post` | The only way to learn a post's tags. Closes the loop `--type tag` opened. Measured available on 52/52 |
| 2 | `posts --tag TAG` | The in-blog tag axis, mirroring `--query`. Same parser, no new shapes |
| 3 | `_se_one` stops discarding unknown components | The primary primitive returns incomplete content on 80% of posts |
| 4 | `se-sticker`, `se-video`, `se-oembed` produce `Media` | Makes two published `Media.kind` values reachable instead of decorative |
| 5 | `topic --top` reports `thumbnail_url` | Validated, then dropped |
| 6 | Notice `commentCount` / `postOpenType` validated | Consumed without validation; silent null on drift |
| 7 | `blog` accepts the URLs every sibling command accepts | Exit 5 on a blog that exists |
| 8 | `fetch_blog` reports `max_requests` when the budget truncated it | A stop reason that overstates what it did |

**Design decision on #3.** The fix is not a longer list of families. Naver adds components, and a
list only ever describes the ones that existed when it was written — the loss is silent either way.
An unrecognized `se-component` instead contributes **its visible text and its images**, generically.
That recovers imageStrip, imageGroup, sticker, table, sectionTitle, material, custom and
wrappingParagraph with no family-specific code, and it makes the next family Naver ships arrive
partially rather than vanish. Only `se-video` and `se-oembed` need their own handling, because
their content is in a `data-module` JSON attribute with no visible text or `img` to fall back to.

**Design decision on #2.** No `--sort`. The endpoint returns `date` whatever is sent; a flag that
is silently ignored is worse than an absent one. Page size is 30, measured, not the sibling's 20.

**Design decision on #1.** `tags` is `null` when not fetched and `[]` when the post carries none —
the same distinction `buddy_count` already draws between "unavailable" and "zero". It costs one
request, taken from the same budget and yielding to it, exactly as `fetch_blog`'s buddy count does.

### Deferred, and why

The seven surfaces `12-…` §2.3 recorded were **re-probed live this session and all 13 endpoints
still answer 200** (today's hot topics, hot-topic keywords, popular keywords, related keywords,
this-month blogs, editor picks, themes, official blogs, related tags, tag groups). They stay
deferred. Their signatures are in `12-…` §2.3 and are still accurate.

The reason is unchanged and is not a shortage of time: on the (a)(b)(c) test they are strong on
"anonymous" and weak on "changes the answer". `topic --top` already answers "what is being read in
this subject"; Claude can generate related Korean keywords without Naver's help; the curation
surfaces answer a question users rarely ask. Building them would raise a coverage percentage and
little else, which is the failure shape this project has avoided since `11-…`.

**Series (연재)** stays unverified. Neither `/api/blogs/{id}/series` nor
`/api/blogs/{id}/posts/{logNo}/series` exists — both fall through to Naver's error page — and no
endpoint appears in the bundles. Recording it as unresolved rather than as absent.

## 3. The checklist

Left column measured at the start of the session, middle predicted before implementation, right
measured after — including from a clean PyPI install of the published 0.3.0.

| 지표 | 아크 시작 | 예상 | **아크 완료 (실측)** |
|---|---|---|---|
| 사람이 하는 행동 (열거) | 33 | 33 | 33 |
| — 로그인 필요, 영구 범위 밖 | 5 | 5 | 5 |
| — 익명 가능 여부 미확인 | 2 | 1 | **1** (해시태그 해결, 시리즈 남음) |
| — 익명 가능 | 26 | 27 | **27** |
| — 도구가 커버 | 19 / 26 (73%) | 22 / 27 (81%) | **22 / 27 (81%)** |
| exit 0인데 데이터가 틀린 결함 | 4 | 0 | **0** |
| 스키마가 약속하고 못 내주는 값 | 2 (`Media.kind`) | 0 | **0** — 네 종류 모두 실물에서 생성 확인 |
| 컴포넌트를 조용히 버리는 글 | 43 / 54 (80%) | 0 / 54 | **0** — 실측 손실과 복구가 정확히 일치 (38→66 등) |
| 오프라인 테스트 | 808 | 늘어남 | **854** (+46, 신규 28개는 규칙마다 이름을 가짐) |
| 라이브 스윕 | — | 신규 표본 | **275 / 278** (30 신규 블로그 × 9 + 전역 8) |
| **스윕이 잡은 신규 결함** | — | — | **1** (`updateTime` null — 모든 이전 릴리즈에 존재) |
| **적대적 diff 리뷰가 잡은 결함** | — | — | **3** (§4 참조) |
| 릴리즈 후 PyPI 클린 설치 검증 | — | — | **통과** |

두 개의 "예상 밖" 행이 이 아크에서 가장 값어치 있는 부분입니다. 스윕과 적대적 리뷰가 없었다면
네 건이 그대로 나갔고, 그중 하나는 이 diff가 다른 함수에서 고치고 있던 결함을 새 코드에서 재현한
것이었습니다.

## 4. What the pre-release sweep found

30 fresh blogs × 9 command shapes plus the 8 global surfaces — **275 / 278 exit 0**.

Verified by value rather than by exit code, because two of this project's shipped defects exited 0:
`post` fetched tags on 30/30; `blog` resolved from a URL on 29/29; `topic --top` returned a thumbnail
on 5/5; the body parser produced 705 photo, 27 sticker and 9 video media, so all three kinds are
reachable in the field and not only in a fixture; 34 notice cards passed the new validation with no
null visibility.

**The sweep refined one number the spec had overstated.** §1.1 measured 52/52 posts carrying at least
one tag. On the fresh sample it was 28/30, so the honest combined figure is **80 of 82**, and a post
with no tags at all is a real if uncommon answer. `tags: []` therefore has to mean something, which
is why it is distinguished from `null` rather than collapsed into it. Correcting this is the same
discipline `12-…` §1.4 recorded: a narrow sample plus a confident claim is how this project has hurt
itself before.

**It also found a defect older than this arc, in the third command shape it touched.**

`public-buddies` returns `updateTime: null` for a neighbour with nothing to show — 2 of 34 buddies on
`seok9c`, both blogs with no visible posts. `parse_buddies` requires it to be a string, so the read
raises drift and exits 4. That kills **three** commands on that blog: `buddies`, and `blog` in both
its bare-id and URL spellings, because 0.2.0 made `blog` read this endpoint for `buddy_count` and so
widened the blast radius of any drift here without anyone noticing.

The field is a **display label** ("26.07.25.") and nothing consumes it — `build_buddy_blog`'s own
docstring says it drops it. So this is the mirror image of §1.4's defect class: not a value validated
and then discarded, but a value *discarded* and yet validated more strictly than the data supports.
It is fixed by accepting the measured null while still rejecting a non-string, and it ships in this
release: 1 blog in 30 is not an edge case, and it fails three commands at once.

### 4.1 What the adversarial review of the finished diff found

A second model was given the completed diff and asked to **break it**, not to approve it. Three of
its four findings were real, and one of them is the most instructive thing in this arc.

**It found the diff reproducing the very defect it was fixing.** Item 8 changed `fetch_blog` to stop
reporting `single_target` when the budget had truncated it. The new tag fetch in `fetch_post`, written
in the same pass, did exactly what item 8 was removing: fetched tags only if a request remained, then
returned `single_target` regardless. Worse, a test had been written asserting that stop reason, so the
defect was locked in by something that looked like coverage. Two functions, one session, opposite
behaviour — which is what a checklist of fixes cannot catch and an adversary reading for a *class* of
error can.

**It found a wrong value dressed as a right one.** The video handler emitted
`Media(kind="video", url=<thumbnail JPEG>)`. `Media.url` is published as the attachment URL, so a
consumer would have fetched a still image expecting a video. The module genuinely carries no player
URL, so the honest answer was neither to invent one nor to discard the thumbnail: `Media` gained a
`thumbnail_url`, and `url` is null. That also gave `se-oembed` somewhere honest to go — reported as
`unknown`, because an oembed can be a video, a post, or a map and the module does not say which,
which makes all four published `MediaKind` values reachable for the first time.

**It found a caption attached to an image it did not belong to.** The image extractor resolved each
caption over the whole component, which is correct when a component holds one image and wrong for the
multi-image strips the new fallback started passing it — and the fallback also printed caption text
as prose before the image printed it again. Small in practice (33 multi-image components measured, 32
with no caption at all), and still a wrong value.

**Its fourth finding was disproved by measurement**, and recording that matters as much as the
others: it argued a component carrying two family classes would be matched by the first branch and
lose its images. Checked against real markup — **387 of 387 components carry exactly one family
class**, so the branch chain is sound and hardening it would have added code for a shape Naver does
not produce.

## 5. Reproducing

Probe and sweep scripts ran from the session scratchpad and are not committed, matching how
`sweep.py`/`sweep2.py`/`sweep3.py` were handled in earlier arcs. Every number above is stated with
the sample that produced it so a re-run can disagree with it.
