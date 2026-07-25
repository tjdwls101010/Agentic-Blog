# Phase 1 — Package defects, the live sweep, and v0.1.1

All four defects below were **reproduced live against the released 0.1.0** on 2026-07-25. Every
claim here carries its evidence; none of it is inferred from reading code alone.

The whole phase exists because of one structural fact, which matters more than any individual
defect: **the parser is strict by design, and it was validated only against a narrow fixture
corpus.** Strictness is correct — D-level policy is that a structural surprise must raise a typed
error rather than silently return an empty result, because a scraper that quietly returns nothing
is worse than one that fails loudly. But strictness plus a thin sample means *ordinary Naver
variation is indistinguishable from real drift*. `videoPlayTime` being an integer on video
thumbnails is not drift; it is a completely normal case the fixtures never captured. That generator
is still running, which is the entire argument for §2's sweep.

The test suite is 768 tests and **none of them touch the network** — that is why all four shipped.

---

## 1. The four confirmed defects

### A — `posts` crashes with exit 4 on most real blogs  🔴 severe

**Symptom**

```
$ agentic-blog posts leehazang --limit 5
response envelope drift at response.result.items[7].thumbnailList[28].videoPlayTime: expected a string
$ echo $?
4
```

**Prevalence: 7 of 8 blogs tested.** Failed: `leehazang`, `ssobell`, `lovedk06`, `mongmonge77`,
`kimyk5088`, `zltm31`, `jsy1182`. Passed: `wowjejusi` (an institutional blog that happens to post
no video).

**Root cause** — `parse.py:195-203`. The validator requires `videoPlayTime` to be a string or null
and calls `_nullable_string` on it. Naver returns an **integer** — the video's play time in
seconds.

Captured directly from `https://m.blog.naver.com/api/blogs/leehazang/post-list`, one 24-item page:

| `videoPlayTime` type | count | sample |
|---|---|---|
| `NoneType` | 904 | `None` |
| `int` | 1 | `34` |

So an image thumbnail carries null and a video thumbnail carries a number. Any blog that has ever
posted a video within its recent listing window dies.

**Why this is the worst of the four:** `posts` is the second hop of the skill's most common chain —
"이 블로거 어떤 사람이야?" is `blog` → `posts`. With `posts` down on 7/8 blogs, that chain does not
work at all.

**Fix direction:** accept the integer. Resist the urge to make the field `Any`; the point of the
strict validator is to keep catching genuine drift. Model what Naver actually sends — a nullable
number, possibly also a string on some surface you have not sampled yet — and let the sweep in §2
tell you which. Decide deliberately whether the value is worth surfacing on `Media` at all, or
whether it should simply be validated and dropped; it is currently not in the output schema.

**Look for siblings of this bug in the same pass.** The failure is "a numeric field validated as a
string," and there is no reason to think `videoPlayTime` is the only one.

### B — `posts --query` reports KST as UTC (9 hours off)  🔴 severe

**Symptom** — the same post, via two paths:

| path | `created_at` |
|---|---|
| `search "제주도 3박4일 여행 후기"` | `2026-07-13T06:38:00Z` |
| `posts leehazang --query "제주"` | `2026-07-13T15:38:00Z` |

Both for `log_no` `224345205796`. Exactly +9h — the KST offset.

**Which one is right:** the search path. Its raw upstream field is `addDate = 1783924680000`
(epoch milliseconds), which is unambiguously `2026-07-13T06:38:00Z`, i.e. 15:38 KST. Confirmed by
re-running `search` with `--raw` and reading `raw["addDate"]`.

So `posts --query` is emitting **Korean wall-clock time stamped with a `Z` suffix**.

**Root cause** — the in-blog search path goes through `body.py`'s `parse_post_search`
(`retrieve.py:499`), which reads the date out of rendered HTML. That HTML shows KST. The value is
never localized before being treated as UTC. Contrast `model.py:_search_created_at`, which converts
epoch-ms correctly, and `model.py:943 _comment_timestamp`, which parses `%z` and calls
`.astimezone(UTC)` — both of those are right.

**Why it is severe rather than cosmetic:** it is silent. Nothing looks wrong. A model comparing or
sorting dates across the two paths gets a consistent-looking answer that is nine hours wrong, and
any "was this before or after X" reasoning can flip.

**Fix direction:** parse the HTML date as `Asia/Seoul` and convert to UTC, matching what
`_comment_timestamp` already does. Add a regression test that asserts the two paths agree for one
known post.

**While you are here:** `posts --query` also emitted a naive datetime in its stderr range line
(`2026-06-13T11:29:00`, no offset) where `search` emitted an aware one (`+00:00`). Same root cause;
check that the fix covers the summary line too.

### C — Single `post` reads never return a timestamp  🔴 severe

**Symptom:** `created_at` is `null` on **5 of 5** single-post reads
(`leehazang/224345205796`, `lovedk06/224345295706`, `mongmonge77/224340088833`,
`ssobell/224335336528`, plus one repeat).

**Root cause** — `body.py:36` declares `created_at: datetime | None` on the parsed body result, and
the mobile HTML path never populates it. `model.py:833 build_mobile_post` reads
`_search_created_at(node.get("addDate"))`, which is correct for the listing surface but there is no
`addDate` on the single-post HTML fetch.

**Why it matters:** `post` is the command that returns the actual content, so it is the one whose
result gets quoted to the user. "When was this written?" is among the most ordinary follow-up
questions there is, and every date-scoped judgment about a post — is this review still current, did
this predate the renovation — has nothing to work with.

**Fix direction:** the publication time is present in the post HTML (`se_publishDate` / the
`.blog_date` element, depending on editor version — confirm against real captures, both SmartEditor
ONE and older `viewTypeSelector` posts). Extract it, treat it as KST, convert to UTC. Same
timezone discipline as defect B — do these two together, they are one habit.

### D — Editor markers leak into `body`  🟡 moderate

**Symptom:** post bodies contain the SmartEditor quotation component's internal delimiters:

```
> SE-TEXT { 제주 서쪽 3박4일 코스, 4일차
> } SE-TEXT
```

**Prevalence: 2 of 4 posts tested** (`leehazang/224345205796` — 2 occurrences,
`lovedk06/224345295706` — 2 occurrences).

**Root cause** — `body.py:156-160`. The `se-quotation` branch takes `_node_text(component)`
wholesale and prefixes `> `. For at least one quotation style, that node's text includes the
literal `SE-TEXT { … } SE-TEXT` scaffolding.

**Why it matters here more than it looks:** the skill's core instruction is going to be "answer
from `body`, never from `brief`." If `body` is polluted with editor internals, the model either
quotes garbage to the user or spends judgment cleaning up what the parser should have handled. This
is the defect most directly downstream of the skill's main instruction.

**Fix direction:** extract only the quotation's actual text nodes rather than the whole subtree.
Check the other component branches for the same over-broad `_node_text` pattern —
`se-placesMap` (line 170) uses the same fallback and may have an equivalent problem.

---

## 2. The live sweep — find the rest before fixing

**Agreed shape: 7 commands × ~30 blogs, roughly 300 requests, about five minutes.**

Precedent for the volume: Phase 0 recon ran 355 anonymous serialized requests across these three
hosts and measured a minimum start interval of 0.500028s with **zero** throttling, no `Retry-After`,
and 120/120 HTTP 200 per host (`02-recon-findings.md` §12.7 Q-1). This sweep is smaller than what
has already been done safely.

### Choosing the 30 blogs

Diversity is the whole point — a homogeneous sample reproduces the fixture problem at larger scale.
Draw them so the set spans:

- **Content type**: video-heavy, photo-heavy, text-heavy, link/map-heavy (맛집 posts are dense with
  `se-placesMap`)
- **Editor version**: SmartEditor ONE and older posts (`viewTypeSelector`) — defect C's fix depends
  on both
- **Scale**: tiny personal blogs through institutional ones with thousands of posts
- **Category**: 여행, 맛집, 육아, IT, 도서, 공공기관 — the directory `topics` command gives you 32
  topic seqs, which is a ready-made stratifier
- **Neighbour graph**: at least a few with public 이웃 lists, since `buddies` returned
  `no_matches` on the first blog tried

Use `search --type blog` and `topic <seq> --top` to assemble the list rather than hand-picking;
hand-picking reproduces your own bias.

### What to run and what to record

Every command against every blog, with a small `--limit`:
`blog`, `posts`, `posts --sort popular`, `posts --notices`, `posts --query <term>`, `buddies`,
`post <one log_no from that blog>`. Plus `search` across the three `--type` values and `topics` /
`topic --top` once each.

For every non-zero exit, **save the raw upstream response** — that capture is the regression test's
input, and it is the thing you cannot get back later once Naver's data moves. Write to
`scratch/sweep/`, which is gitignored.

Also record, for zero-exit runs, anything that looks *structurally* surprising even though it
parsed: nulls where you expected values, a `stop_reason` you did not anticipate, counts that
disagree. Defect C exits 0 — a sweep that only watches exit codes would never have found it.

### The fixture question

`scripts/record_fixture.py` exists; use it. Two constraints that are not negotiable:

1. **`scripts/check_fixtures_pii.py` runs in pre-commit.** Real captures carry real people's
   nicknames, comment text, and profile URLs. Run it before committing anything and expect it to
   reject material you will need to scrub.
2. **A regression test built from a real capture is worth several hand-written ones.** The reason
   all four defects shipped is that hand-authored fixtures encode the author's assumption about the
   shape, which is precisely the assumption that was wrong. Derive the fixture from the captured
   response.

### Gate

The sweep is done when you have a written defect inventory in `scratch/sweep/` with a saved raw
response for every distinct failure signature. Then fix, then **re-run the same sweep against the
fixed build** and expect zero unexpected non-zero exits.

## 3. Shipping v0.1.1

1. Fixes and their regression tests on one branch. Full `pytest` green, `ruff` clean, pre-commit
   passing.
2. `CHANGELOG.md` — a Fixed section naming each defect in user-facing terms. "`posts` no longer
   fails on blogs containing videos" is the sentence a user needs; "accept int `videoPlayTime`" is
   not.
3. Version bump in `pyproject.toml`. `scripts/check_tag_version.py` enforces tag/version agreement —
   it is wired into the release workflow, so a mismatch fails the publish rather than shipping
   wrong metadata.
4. PR, review, merge to `main`.
5. Tag `v0.1.1`, push the tag, let the GitHub Actions workflow publish to PyPI.
6. **Verify the release before building anything on it.** Read the version from the *simple index*,
   not the JSON endpoint — the JSON endpoint can lag minutes behind a publish and will tell you the
   release did not land when it did:

   ```bash
   curl -s https://pypi.org/simple/agentic-blog/ \
     | grep -oE 'agentic[_-]blog-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/.*-//' | sort -V | tail -1
   ```

7. Install 0.1.1 into a **clean** virtualenv — not the repo's `.venv`, which resolves to the local
   checkout and will happily hide a packaging mistake — and run `posts` against three of the blogs
   that failed in §1A. All three must exit 0.

Only then start Phase 2.
