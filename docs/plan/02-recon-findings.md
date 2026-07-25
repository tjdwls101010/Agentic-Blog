# Recon Findings — Naver Blog

> **All measurements below were taken live on 2026-07-25** against real public blogs
> (`znogi`, `lee_haimin`, `peopleteria`) using plain `curl` and, where a request had to be
> observed rather than guessed, a headless Playwright capture. **Every endpoint marked ✅ was
> re-verified with pure `curl`, no cookies, no login, no browser.**
>
> Two discovery techniques did the heavy lifting and are worth reusing when this rots:
> 1. **Mining the site's own JS bundles.** `section.blog.naver.com` is an AngularJS app; its
>    `NgAppBundle1`/`NgAppBundle2` contain every `/ajax/*.naver` call site *with the exact
>    parameter object*. That is strictly better than network observation, which only shows the
>    requests that happened to fire.
> 2. **Headless network capture** for the two endpoints the bundles didn't reveal (the comment
>    box and the buddy list), both of which are lazily loaded.

---

## 1. The headline finding

**Naver Blog has the easiest access story of the whole family — by a wide margin.**

| | Facebook | X | Threads | Reddit | **Naver Blog** |
|---|---|---|---|---|---|
| Login required | yes | yes | yes | no | **no** |
| Credentials stored | yes | yes | yes | none | **none** |
| Browser needed at runtime | fallback | login only | login only | **always** (anti-bot) | **never** |
| Anti-bot wall on plain HTTP | — | — | — | **yes (403)** | **no** |
| Rotating request tokens | `fb_dtsg`/`lsd` | txid | `doc_id` | — | **none** |
| Backend returns clean JSON | yes | yes | yes | yes | **yes, except post body** |

There is **no `login` command, no `setup` command, no session file, no cookie jar, no
`scrapling`, no Playwright, and no `_stealth_init.js` in this project.** The runtime dependency
set is `httpx` + `platformdirs` + `lxml`. A user runs `pip install agentic-blog` and immediately
reads.

The single complication is that **post bodies are HTML, not JSON** (§5). Everything else —
search, blog metadata, category trees, post lists, comments, the neighbor graph, topic
directories — is served as structured JSON.

---

## 2. Two API families

Naver Blog is not one backend. Three hosts matter:

| Host | Style | Used for |
|---|---|---|
| `section.blog.naver.com/ajax/*.naver` | Legacy AngularJS endpoints. Responses are prefixed with the XSSI guard `)]}',` which **must be stripped before `json.loads`** | Search (post/blog/id), topic directories, editor picks, ranked-blog lists |
| `m.blog.naver.com/api/blogs/{blogId}/*` | Modern REST JSON, envelope `{"isSuccess":bool,"result":{...}}` or `{"isSuccess":false,"error":{...}}` | Category tree, post list, popular/notice posts, neighbor list, comment bootstrap |
| `apis.naver.com/commentBox/cbox/*` | Naver's shared comment platform (CBOX) | Comments and replies |

**Required header on every request: `Referer`.** Requests without a plausible Naver `Referer`
are refused or degraded. `User-Agent` should be an ordinary browser string; the mobile REST API
is happiest with an iPhone Safari UA and `section.blog` with a desktop Chrome UA. No other
header, cookie, or token is needed anywhere.

---

## 3. `section.blog.naver.com/ajax/*` — search and discovery ✅

Parameter signatures below were extracted verbatim from `NgAppBundle1/2`, then verified live.

### 3.1 `SearchList.naver` — the search primitive ✅

```
GET /ajax/SearchList.naver
    ?type={post|blog|id}
    &keyword=<UTF-8 urlencoded>
    &orderBy={sim|date}        # post/blog only
    &startDate=YYYY-MM-DD      # post only, optional
    &endDate=YYYY-MM-DD        # post only, optional
    &currentPage=<1-based>
    &countPerPage=<n>          # site defaults: post 7, blog 10
```

**There are three search types, not two.** The bundle exposes
`getSectionSearchPostList` / `getSectionSearchBlogList` / `getSectionSearchNickAndIdList`:

| `type` | Returns | Verified fields on each item |
|---|---|---|
| `post` | Individual posts | `domainIdOrBlogId`, `logNo`, `postUrl`, `title`, `contents`, `addDate` (epoch ms), `blogName`, `nickName`, `gdid` |
| `blog` | Whole blogs | `blogNo`, `domainIdOrBlogId`, `blogName`, `nickName`, `blogDesc`, `profileImgUrl` |
| `id` | Nicknames / blog IDs | same shape as `blog` — this is the "find the person" search |

**Server-side date filtering works.** `startDate`/`endDate` with `orderBy=date` returned only
in-range results (verified 2026-07-01..2026-07-10). This is a genuine improvement over the
siblings, all of which filter dates client-side — **do not reimplement client-side date
filtering for `type=post`.**

**Keyword highlighting is embedded in the response.** `title`, `blogName`, and `contents` come
back containing `<strong class="search_keyword">…</strong>` around matched terms. The parser
**must strip these tags** before populating the model; the raw string is not display text.

Envelope: `{"result":{"searchDisplayInfo":{...},"searchList":[...],"totalCount":n,"pagePerCount":n}}`.
`searchDisplayInfo.authUrlType == "LOGIN"` appears even on successful anonymous responses — it is
the site's own login-CTA hint and **must not be read as an auth error**.

### 3.2 Topic directories ✅

```
GET /ajax/DirectoryList.naver                              # no params -> full topic tree
GET /ajax/DirectoryPostList.naver?directorySeq=<n>&pageNo=<n>
GET /ajax/DirectoryTopPostList.naver?directorySeq=<n>      # the topic's top posts
```

`DirectoryList` returns a **list of groups**, each `{name, directoryList:[{name, sortNo, seq}]}`
— e.g. group "엔터테인먼트·예술" containing `문학·책(seq 5)`, `영화(6)`, `미술·디자인(8)`, …
`seq` is the `directorySeq` used by the other two calls. `DirectoryPostList` items carry
`domainIdOrBlogId`, `blogNo`, `nickname`, `blogUrl`, `logNo`, `title`, `postUrl`,
`briefContents`, `profileImage`.

### 3.3 Other endpoints present in the bundle (not required for v1)

`RelatedKeywordList.naver?keyword=` (related search terms), `PowerBlogList`, `RookieList`,
`OfficialBlogList`, `ThisMonthDirectoryBlogList`, `EditorPickList`, `ThemeList`,
`HotTopicKeywordList`, `TodayHotTopicList`, `HotTopicChallengeList`.

Endpoints requiring login (**out of scope**, listed so nobody wastes time on them):
`BuddyPostList` (이웃새글 feed), `NewsList`, `MyTraceList`, `BlogNotificationList`,
`BuddyList` (*your own* neighbours — note this is a different call from `public-buddies` in §4.4),
`BuddyAddAsync`/`BuddyRemoveAsync` (writes).

---

## 4. `m.blog.naver.com/api/blogs/{blogId}/*` — per-blog REST ✅

Envelope is always `{"isSuccess": true, "result": {...}}`, or on failure
`{"isSuccess": false, "error": {"code": "...", "message": "...", "details": "..."}}`.
Observed error codes: `param_is_invalidate`, `error`.

### 4.1 `category-list` ✅

```
GET /api/blogs/{blogId}/category-list
```

Returns `{mylogCategoryList, memologCategoryList, mylogPostCount, memologPostCount}`. Each
category: `categoryNo`, `categoryName`, `parentCategoryNo` (null at root — **this is what makes
it a tree**), `postCnt`, `openYN`, `categoryType` (`B` = normal, `S` = separator),
`divisionLine`, `childCategory`, `directorySeq`, `categoryBlocked`.

Rows with `categoryType == "S"` / `divisionLine == true` are **visual separators, not
categories** (they have `postCnt: 0` and a cosmetic name like `구분선`) and must be filtered out.

### 4.2 `post-list` — the workhorse ✅

```
GET /api/blogs/{blogId}/post-list?categoryNo=<n>&itemCount=<n>&page=<1-based>
```

`categoryNo=0` means all posts. **`itemCount` has a hard server-side maximum of 30** —
measured: 5/10/24/25/30 succeed, 31/50/100 return `param_is_invalidate`. The site itself uses 24.
The pagination layer must clamp to 30 and page, never request more.

Per item (verified): `logNo`, `blogNo`, `domainIdOrBlogId`, `titleWithInspectMessage` (the title,
already Unicode-decoded), `briefContents` (summary), `addDate` (**epoch milliseconds**),
`categoryNo`, `categoryName`, `commentCnt`, `sympathyCnt` (공감/likes), `shareCnt`,
`thumbnailUrl`, `thumbnailList[]`, `thumbnailCount`, `smartEditorVersion` (see §5),
`readCount` (**observed always `null` anonymously — do not promise it**), `openGraphLink`,
`placeName`, `searchYn`, `postBlocked`, and the visibility flags
`allOpenPost` / `buddyOpen` / `bothBuddyOpen` / `notOpen`.

**`result.totalCount` was observed as `0` even on blogs with thousands of posts** — it is not a
usable total. Paginate until a page returns fewer items than requested; do not trust `totalCount`.

The visibility flags are how a logged-out reader detects neighbor-only posts. Surface them; do
not silently drop such entries.

### 4.3 Post-adjacent lists ✅

```
GET /api/blogs/{blogId}/notice-post-list        # pinned notices; {"noticePostViewList":[...]}
GET /api/blogs/{blogId}/popular-post-list       # the blog's own popular posts
GET /api/blogs/{blogId}/popular-post-block-list
GET /api/blogs/{blogId}/talktalk-account
```

### 4.4 `public-buddies` — the neighbour graph ✅

```
GET /api/blogs/{blogId}/public-buddies?pageNo=<1-based>
```

Discovered by capturing `m.blog.naver.com/BuddyList.naver?blogId=…`; **verified afterwards with
pure `curl`.** Returns `blogId`, `nickName`, `totalMyBuddyCount`, `totalPublicBuddyCount`,
`totalPageCount`, `currentPage`, and `buddyList[]` where each entry is
`{blogId, blogName, nickName, linkUrl, blogProfileImage, blogNo, updateTime}`.

Measured on `peopleteria`: 4,982 neighbours across `totalPageCount: 100`. **Here `totalPageCount`
*is* reliable** (unlike `post-list`'s `totalCount`). `updateTime` is a **humanised Korean relative
string** (`"8분 전"`), not a timestamp — it cannot be parsed into an absolute date and should be
passed through verbatim or dropped.

`/api/blogs/{blogId}/buddies` also exists but returns HTTP 500 with the normal error envelope for
every parameter set tried; `public-buddies` is the correct call.

---

## 5. Post bodies — the one HTML surface

There is no JSON endpoint for post content. `GET https://m.blog.naver.com/{blogId}/{logNo}`
returns a server-rendered HTML document (~120–670 KB).

**`post-list` tells you which parser to use before you fetch**, via `smartEditorVersion`. Two
branches were measured:

| Editor | Container | Structure |
|---|---|---|
| SmartEditor ONE (`smartEditorVersion: 4`) | `div.se-main-container` | Component-based: `div.se-component.se-text`, `.se-image`, `.se-quotation`, `.se-oglink`, `.se-placesMap`, `.se-horizontalLine`, … Each component is preceded by `<script type="text/data" class="__se_module_data" data-module-v2='{"type":"v2_text","id":"SE-…","data":{"ctype":"text"}}'>` |
| Legacy (older versions) | `div.post_ct#viewTypeSelector` | Raw legacy HTML — `<p>` with inline styles, `__se_component_area`, no component classes and **no `__se_module_data` markers at all** |

Measured on `znogi/224356289619` (SE ONE): 189 `__se_module_data` markers — 102 `se-image`,
87 `se-text`, 1 `se-document`. Measured on `peopleteria/220108382928` (legacy): zero markers,
body inside `div.post_ct`.

**The `data-module-v2` attribute is a type marker only — it does not contain the content.** The
text lives in the rendered HTML. So extraction is a DOM walk over `.se-main-container`'s children
dispatching on the `se-*` class, with a legacy fallback that flattens `div.post_ct`. This is
~150 lines of Naver-specific code and is *more* accurate than any generic readability extractor,
because the component classes tell us exactly what each block is.

Images use lazy-loading attributes (`data-lazy-src`) rather than a populated `src`; read both.

---

## 6. Comments (CBOX) ✅ — the hardest gate, now closed

This was the only endpoint that resisted guessing. Eight parameter combinations were tried
blind and all returned `code: 3300, "서비스 정책에 의해 사용이 제한되었습니다"`. A headless capture
of `m.blog.naver.com/PostView.naver?blogId=…&logNo=…&modal=comment` revealed why: **two guesses
were wrong at once.**

```
GET https://apis.naver.com/commentBox/cbox/web_naver_list_json.json
    ?ticket=blog
    &pool=blogid                            # NOT cbox5 / cbox9
    &objectId={blogNo}_201_{logNo}          # the literal "201" in the middle
    &groupId={blogNo}
    &templateId=default&lang=ko&country=&_cv=
    &pageType=more&listType=OBJECT
    &page=1&pageSize=<n>&indexSize=10&replyPageSize=10&followSize=5
    &initialize=true&useAltSort=true&userType=&categoryId=
    &sort={NEW|FAVORITE}
```

`objectId` embeds a constant `201` between the numeric blog id and the post id. That single
undocumented literal is why every blind attempt failed — **record it, it is not derivable.**

Note the path is `web_naver_list_json.json` (plain JSON). `web_naver_list_jsonp.json` and
`web_neo_list_jsonp.json` also exist and return JSONP; prefer the plain-JSON form so no callback
stripping is needed. `web_naver_view_log_json.json` is a **telemetry beacon** the site fires
alongside the list call — **do not send it.**

### 6.1 Getting `blogNo`

Two sources, both anonymous:

```
GET /api/blogs/{blogId}/posts/{logNo}/comments-info
    -> {"isSuccess":true,"result":{"blogNo":164888122,"postTitle":"…","totalCount":0,
        "availableCommentWrite":false,"memoLog":false,"postOpenWithCategoryOpenYn":true}}
```

or read `blogNo` straight off any `post-list` item. Prefer `post-list` when the post is already
being listed — it saves a request.

### 6.2 Verified response

Against `znogi/224356289619` (`objectId=19866795_201_224356289619`), pure `curl`, no cookies:
`success: true`, `code: 1000`, `count: {comment: 25, reply: 17, total: 42}`.

Per comment: `commentNo`, `parentCommentNo`, `replyLevel`, `replyCount`, `replyList[]` (nested —
**the reply tree comes back inside the same response, no second call needed**), `contents`,
`userName`, `maskedUserName`, `profileUserId`, `userProfileImage`, `regTime`/`modTime`
(**ISO-8601 with `+0900` offset — unlike every other Naver timestamp here, which is epoch ms**),
`sympathyCount`, `antipathyCount`, `status`, `best`, `commentType`, `stickerId`, `imageList[]`.

`parentCommentNo == commentNo` marks a top-level comment.

**`profileUserId` is the navigational payoff**: it is the commenter's own blog id, so a comment
thread is a set of edges into other blogs — exactly the multi-hop chaining this project exists
for.

---

## 7. In-blog post search — HTML only

No JSON endpoint exists. `PostSearchListAsync.naver` and `SearchPostListAsync.naver` both 404;
`m.blog.naver.com/SearchList.naver` redirects to a not-found page; passing `searchText`/`keyword`
to `post-list` is silently ignored (it returns the unfiltered list, which is a **dangerous
false positive** — the response looks successful).

The working path is the PC page, which is server-rendered:

```
GET https://blog.naver.com/PostSearchList.naver?blogId={id}&SearchText={q}&orderBy=recentdate&currentPage=1
```

Verified: HTTP 200, ~150 KB, **10 `logNo`s per page**. Note the capitalised `SearchText`.
Extract the `logNo` set from the HTML, then hydrate through the JSON APIs.

---

## 8. Likes (공감)

```
GET https://apis.naver.com/blogserver/like/v1/search/contents
    ?pool=blogid&suppress_response_codes=true
    &q=BLOG[{blogId}_{logNo},{blogId}_{logNo},…]      # batched, JSONP
    &isDuplication=false&cssIds=MULTI_MOBILE,BLOG_MOBILE&displayId=BLOG
```

Not needed for v1: `post-list` already returns `sympathyCnt` per post, without a second request.
Recorded only so a future session doesn't rediscover it.

---

## 9. Consolidated endpoint table

| Purpose | Endpoint | Status |
|---|---|---|
| Post search | `section /ajax/SearchList.naver?type=post` | ✅ curl-verified |
| Blog search | `section /ajax/SearchList.naver?type=blog` | ✅ curl-verified |
| Nickname/ID search | `section /ajax/SearchList.naver?type=id` | ✅ curl-verified |
| Topic tree | `section /ajax/DirectoryList.naver` | ✅ curl-verified |
| Topic posts | `section /ajax/DirectoryPostList.naver` | ✅ curl-verified |
| Topic top posts | `section /ajax/DirectoryTopPostList.naver` | ✅ bundle-confirmed |
| Category tree | `m /api/blogs/{id}/category-list` | ✅ curl-verified |
| Post list | `m /api/blogs/{id}/post-list` | ✅ curl-verified (itemCount ≤ 30) |
| Notice posts | `m /api/blogs/{id}/notice-post-list` | ✅ curl-verified |
| Popular posts | `m /api/blogs/{id}/popular-post-list` | ✅ curl-verified |
| Neighbours | `m /api/blogs/{id}/public-buddies?pageNo=` | ✅ curl-verified |
| Comment bootstrap | `m /api/blogs/{id}/posts/{logNo}/comments-info` | ✅ curl-verified |
| Comments + replies | `apis /commentBox/cbox/web_naver_list_json.json` | ✅ curl-verified |
| Post body | `m /{id}/{logNo}` (HTML) | ✅ structure measured, 2 branches |
| In-blog search | `blog /PostSearchList.naver` (HTML) | ✅ 200, 10 logNo/page |

---

## 10. Traps to carry into implementation

1. **`)]}',` XSSI prefix** on every `section.blog` response — strip before parsing.
2. **`objectId` = `{blogNo}_201_{logNo}`** — the `201` is a magic constant.
3. **`pool=blogid`**, not `cbox5`/`cbox9`.
4. **`itemCount` ≤ 30** on `post-list`; 31+ is a hard error.
5. **`post-list.totalCount` is `0` and unusable.** `public-buddies.totalPageCount` *is* usable.
6. **Search results contain `<strong class="search_keyword">` markup** — strip it.
7. **`searchDisplayInfo.authUrlType == "LOGIN"` is not an error.**
8. **Passing a search term to `post-list` silently returns unfiltered results** — never treat it
   as in-blog search.
9. **Mixed timestamp formats**: `addDate` is epoch ms; CBOX `regTime` is ISO-8601 `+0900`;
   `public-buddies.updateTime` is a Korean relative string. Normalise all three deliberately.
10. **`readCount` is `null` anonymously.** Do not put a view count in the schema's promises.
11. **`Referer` is mandatory** on every host.
12. **Never call `web_naver_view_log_json.json`** — it is a tracking beacon, not a read.

---

## 11. Open items for Phase 0 of the implementation session

Everything load-bearing is closed. What remains is measurement, not discovery:

- **Q-1 — Rate limits.** No `x-ratelimit-*` headers are exposed on any of these hosts, and no
  throttling was hit during recon (a few hundred requests). The floor is therefore a policy
  choice, not a measured constraint. Confirm nothing blocks at the chosen floor over a sustained
  run, and record what a block actually looks like (status, body) so the error mapping is real
  rather than assumed.
- **Q-2 — Legacy-editor body coverage.** Two editor generations were measured. Naver has shipped
  more than two over ~20 years. Sample posts across a wide date range and confirm the fallback
  branch degrades to readable text rather than throwing.
- **Q-3 — Unavailable-target shapes.** Capture the exact anonymous responses for: a deleted post,
  a private blog, a neighbour-only post, a suspended blog, and a nonexistent `blogId`, so the
  not-found / unavailable errors map to real signatures instead of guesses.
- **Q-4 — In-blog search HTML stability.** The `PostSearchList.naver` extraction is the only
  place where a Naver template change breaks a *primitive* rather than a field. Decide how it
  fails: a typed drift error, or a documented degradation.
- **Q-5 — `orderBy` values.** `sim` and `date` are confirmed for search; `recentdate` is used by
  in-blog search. Confirm the full accepted set rather than assuming symmetry.

## 12. Phase 0 results — 2026-07-25

**Method.** This is an append-only recheck of §§3–9; it does not replace the
2026-07-25 observations above. Requests were anonymous fresh HTTP GETs with no cookie jar,
a plausible Naver `Referer`, and an ordinary desktop Chrome (`section`/PC) or iPhone Safari
(`m`) `User-Agent`. No telemetry endpoint was called. No raw response body is committed;
the gitignored `scratch/phase0/` holds only local measurement summaries.

### 12.1 Endpoint-table recheck

All 15 rows in §9 returned HTTP 200 with their documented top-level shape: the six
`section` calls returned their `result` JSON envelope; the six per-blog REST calls returned
`{"isSuccess": true, "result": ...}`; CBOX returned plain JSON with `success`, `code`, and
`result`; and the two body/search routes returned HTML. The topic-top call, previously only
bundle-confirmed, returned the same `section` JSON shape. Representative result shapes were
also rechecked: `category-list` exposed the four documented category/count keys,
`post-list` exposed `categoryNo`, `categoryName`, `items`, `page`, and `totalCount`,
`notice-post-list` exposed `noticePostViewList`, `popular-post-list` exposed
`popularPostList`, `public-buddies` exposed paging plus `buddyList`, and `comments-info`
exposed `blogNo` and comment availability/count metadata. The HTML post and in-blog search
pages were 671,558 and 151,017 bytes respectively; the latter contained `logNo` references
rather than a JSON envelope.

### 12.2 Q-1 — bounded rate-limit measurement

**Confirmed:** 30 requests were issued at a measured minimum 0.500-second interval
(14.796 seconds from first start to last completion): 10 each to
`section.blog.naver.com`, `m.blog.naver.com`, and `apis.naver.com`. All 30 returned HTTP
200; none included `Retry-After`; no response was a block page or a changed error shape.
This deliberately capped run is evidence only for this small, serialized anonymous sample,
not a claim that a larger run cannot throttle.

**Negative result / policy:** no non-429 throttle signature was observed. HTTP 429 still maps
to `RateLimitedError` by contract; no additional status/body signature can be asserted yet.
Retain the 0.5-second floor, and require measured evidence before classifying any other
response as a rate-limit failure rather than a transport or target error.

### 12.3 Q-2 — editor/body coverage

**Confirmed:** public `section` date-filtered search supplied one post from each of 2005,
2010, 2015, and 2020; each body fetched HTTP 200. DOM extraction from
`div.post_ct#viewTypeSelector` produced non-empty readable text of 1,285, 4,249, 1,918,
and 4,927 characters respectively. The 2005/2010/2015 samples had no
`se-main-container` and no `__se_module_data` marker. The 2020 sample had both
`se-main-container` and legacy `post_ct`, but zero module markers. The previously measured
SE ONE post remains the only sampled `smartEditorVersion: 4` case and had 189 markers;
the legacy samples exposed no version through this search surface.

**Parser implication:** selector presence alone is not a safe editor discriminator.
Use the SE component walk only when the post-list editor metadata and/or actual SE component
markers establish that branch; otherwise flatten the legacy `post_ct` fallback. The fallback
has now been shown to yield text across four sampled years, but this is not exhaustive of
all historical templates.

### 12.4 Q-3 — unavailable-target signatures

**Confirmed:** a synthetic nonexistent `blogId` on `category-list` returned HTTP 400,
`{"isSuccess":false,"error":{...}}`, with `error.code == "blog_id_invalidate"`. A nonexistent
`logNo` on the real public `znogi` blog returned HTTP 404 from `comments-info` with
`error.code == "not_exist_post"`; its mobile body route also returned HTTP 404 and only a
redirect script to `MobileErrorView.naver?errorType=noPost`.

**Typed policy:** map the observed nonexistent blog and post signatures to
`NotFoundError`; do not infer that every HTTP 400 or 404 is not-found. Preserve an otherwise
successful `post-list` visibility flag (`buddyOpen`, `bothBuddyOpen`, or `notOpen`) and map
a subsequent anonymous access denial to `TargetUnavailableError`, rather than collapsing it
to not-found.

**Not fully sampled:** no deleted, private, suspended, or neighbour-only public target was
available from the plan's public examples. The first pages (30 entries each) of `znogi`,
`peopleteria`, and `lee_haimin` contained no neighbour-only flag. No shape is claimed for
those target classes.

### 12.5 Q-4 — in-blog-search drift policy

**Confirmed:** `PostSearchList.naver` with `SearchText`, `orderBy=recentdate`, and a public
blog returned HTTP 200 HTML containing extractable `logNo` references. This is still an HTML
contract, not proof of permanent template stability.

**Required failure policy:** extraction must require the expected result structure and at
least one `logNo` for a non-empty rendered result. If that structure is absent or parsing
fails, it must raise typed `BodyParseError` (exit 4); it must never return a silent empty
search result. A genuine, structurally recognized zero-result page remains an empty result.

### 12.6 Q-5 — `orderBy` vocabulary

**Confirmed semantic values:** for section post search, `sim` and `date` returned distinct
three-result orderings. `recentdate` returned the same ordering as `date`, while `accuracy`
returned the same ordering as `sim`; because the server returned HTTP 200 for every tested
string, those two are aliases or silent fallbacks, not independently confirmed vocabulary.
Expose only canonical `sim` and `date` for section search.

For in-blog HTML search, `recentdate` and `sim` returned distinct result orderings.
`date` returned the same ordering as `recentdate`, so it is likewise an alias or fallback,
not a separately confirmed semantic option. Expose only canonical `recentdate` and `sim`
for in-blog search; do not assume the two endpoint families are symmetric.

**Measurement limits:** this tested four section values (`sim`, `date`, `recentdate`,
`accuracy`) and three in-blog values (`recentdate`, `sim`, `date`) against one public query.
HTTP 200 alone is not acceptance evidence where the server silently chooses a default.

### 12.7 Supplemental Phase 0 evidence — 2026-07-25

**Method and handling.** This dated supplement preserves the earlier §12 record. All requests
were anonymous GETs with no cookie jar, credentials, browser automation, telemetry calls, or
writes. Only aggregate status/envelope/marker data is recorded here; request URLs, target
identifiers, titles, and response bodies remain uncommitted in gitignored `scratch/phase0/`.

#### Q-1 — sustained serialized measurement

**Confirmed:** 360 requests were serialized across the three documented read hosts: 120 each to
`section.blog.naver.com`, `m.blog.naver.com`, and `apis.naver.com`. The scheduled global floor was
0.500 seconds between request starts; the measured minimum start interval was 0.500028 seconds
(the maximum was 1.276027 seconds). The run took 182.661 seconds from first start through final
completion, with a 182.491-second first-to-last-start span. Every host returned 120 HTTP 200
responses. No host returned `Retry-After`, a non-200 response, or a sampled non-200 block-body
marker.

**Conservative mapping and limit:** this closes the prior small-sample limitation for a
few-hundred-request, serialized anonymous run at the 0.5-second floor. It does not establish a
quota, a higher safe rate, a per-IP policy, or a block signature: no throttle was observed.
HTTP 429 remains the only evidenced rate-limit status mapping; do not classify another status or
body as throttling without a later observation.

#### Q-3 — bounded public unavailable-target search

**Search method:** 12 public search terms covering Korean and English neighbour-only, private,
closure/deletion, suspension, and withdrawal wording were queried through public `SearchList`
twice: `type=blog` (up to three results per term) and `type=post` (up to three results per term).
All 24 search requests returned HTTP 200. The blog pass yielded 35 unique public candidates:
each candidate's `category-list` and first `post-list` page returned HTTP 200 with
`isSuccess: true`; none of the returned post items had a true `buddyOpen`, `bothBuddyOpen`, or
`notOpen` flag. The post pass yielded 32 distinct public search links; every corresponding
`comments-info` response returned HTTP 200 with `isSuccess: true`. Thus this bounded stale-link
check found no deleted target and the list scan found no neighbour-only target.

**Exact observed signatures remain limited to the earlier records:** nonexistent blog:
HTTP 400, `isSuccess: false`, `error.code: blog_id_invalidate`; nonexistent post:
HTTP 404, `error.code: not_exist_post`, with the mobile route's `errorType=noPost` redirect
marker. These are `NotFoundError` signatures only. A successful list visibility flag remains
evidence of potential neighbour-only visibility, not an anonymous access-denial signature.

**Unresolved after the bounded search:** deleted post, private blog, suspended blog, and
neighbour-only post. No public non-sensitive target for any of those four classes was found in
the 126 Q-3 requests above, so no class-specific status, envelope, redirect, or typed mapping is
asserted. Preserve these classes as `TargetUnavailableError` only after a future measured
anonymous denial signature; do not infer them from generic 4xx responses.
