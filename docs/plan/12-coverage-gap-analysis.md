# Coverage gap analysis — what a person does on Naver Blog, and what this tool can do

**Session:** 2026-07-25, planning only. No package or skill code was changed.
**Inputs:** `11-coverage-goal.md` (the goal statement), `02-recon-findings.md` §3.3 (the
unimplemented-endpoint list this started from), `scratch/sweep/` (the sweep harness).
**Outputs:** this document, plus `13-build-spec.md` for the arc that implements the agreed scope.

Everything below marked ✅ was checked live and anonymously during this session — no cookie jar, no
login, fresh `httpx` GETs with a plausible `Referer`. Endpoint signatures were **read out of the
JavaScript bundles**, not guessed; §1.4 records why that mattered. Anything not actually checked is
marked ❓ and says so in words, because an unverified row that looks like a verified one is worse
than no row.

---

## 1. Re-verification of the shipped package (goal §2단계)

### 1.1 Method

The previous arc's sweep used 30 blogs. Re-running it unchanged would re-test the same variation and
find the same nothing, so this pass built a **disjoint** sample: 13 directory topics that the first
sample did not use, 5 new search terms, and an explicit exclusion of all 68 blog ids in the first
pool. `scratch/sweep/assemble2.py` produced 87 fresh blogs; `sweep2.py` swept a stratified 32 of
them across 7 command shapes.

The goal statement warned that exit codes are not enough — two of the previous arc's six defects
exited 0 with wrong data. So `sweep2.py` additionally re-requests each listing with `--raw` and
diffs the parsed fields against the upstream object they came from. The point is **provenance, not
equality**: `_search_visibility` was previously right by accident because three fields it checks
were all absent, and only the raw object shows that a value rests on nothing.

### 1.2 Result: 224/224 exit 0

| command shape | exit 0 |
|---|---|
| `blog` | 32/32 |
| `posts` | 32/32 |
| `posts --sort popular` | 32/32 |
| `posts --notices` | 32/32 |
| `posts --query` | 32/32 |
| `buddies` | 32/32 |
| `post` | 32/32 |

The v0.1.1/v0.1.2 fixes hold on blogs they were never tested against. Ordinary-and-not-a-defect
outcomes, recorded so a future sweep does not re-investigate them: `buddies` empty on 13/32 and
`posts --notices` empty on 17/32 are both normal (a blog with no public neighbours, a blog with no
pinned notice).

### 1.3 One real defect: two schema fields that are permanently null

**`Blog.post_count` and `Blog.buddy_count` are null in 32/32 runs — and in every output of every
command, always, by construction.**

`Blog` has exactly two constructors, `build_search_blog` (model.py:458) and `build_buddy_blog`
(model.py:912). Neither assigns either field, and nothing else builds a `Blog`. The values are not
merely missing on some blogs; they cannot ever be populated.

The data is available and the package already reads it:

| field | live source | measured | already validated at |
|---|---|---|---|
| `post_count` | `category-list` → `mylogPostCount` | 15 / 4,517 / 1,189 | `parse.py:230` |
| `buddy_count` | `public-buddies` → `totalPublicBuddyCount` | 4,982 / 1 / 0 | `parse.py:304` |

Both are validated on the way in and then dropped. `agentic-blog schema` promises "Number of posts"
and "Number of public neighbours" to anyone reading the published contract, and delivers null.

This is the same defect *class* the previous arc paid for — exit 0, output structurally valid, value
wrong — and it is the reason this pass diffed against raw instead of watching return codes.

**Note on `buddy_count`'s meaning.** `public-buddies` returns two different totals and they diverge
sharply: `znogi` reports `totalMyBuddyCount: 248` against `totalPublicBuddyCount: 1`; `honeybi_0405`
reports 1,908 against 0. Decided this session: **`buddy_count` = `totalPublicBuddyCount`**, because
that is the number of neighbours an anonymous reader can actually enumerate, so the field agrees
with what the `buddies` command returns instead of contradicting it. A blog with many neighbours and
`buddy_count: 0` is therefore expected output, not a bug — see `13-build-spec.md` §3.2.

### 1.4 Two findings that were my measurement error, not package defects

Recorded because the goal statement asks for exactly this discipline, and because both are the
failure mode it warned about, reproduced inside the verification harness itself.

**`posts --query` did not fail 32/32.** The sweep invoked it as `posts <id> --query 리뷰 --raw`, and
the CLI rejected that with `--query does not support --raw` — correct behaviour, clearly worded, and
my harness's error. Re-run correctly: **32/32 exit 0**, no flags, and the query term appears in
title or brief on 155/158 items. The 3 misses are Naver's own in-blog search matching body text the
listing does not show, which is a property of Naver's index, not of the parser.

**`title_markup_not_stripped` was a false positive.** The check flagged any title where raw and
parsed both contain `<`. Every one of the 5 hits was a Korean title using angle brackets as
quotation marks — `더현대서울 ALT.1 <뱅크시: still here> 전시회 후기`. Parsed equals raw; the parser is
correct and stripping here would corrupt real titles. This is precisely the goal statement's
"엄격함 + 좁은 표본 = 자해", committed by the checker rather than the parser.

### 1.5 `post.created_at` null rate, finally quantified

The sweep showed `post.created_at` null on 25/32, which looks alarming against a schema that
promises a timestamp. It is **sampling, not drift**: the sweep reads each blog's *newest* post,
which is exactly where Naver renders a relative label ("7시간 전").

Split by post age over 16 blogs:

| post read | `created_at` present |
|---|---|
| newest post | 3/16 |
| 30th-newest post | **16/16** |

So B9 in the harness spec is right and now has a number attached: the relative label is a property
of recency, the listing surfaces always carry an exact time, and reading an older post returns one
too. No change needed; this belongs in the skill as a fact, and it is now measured rather than
asserted.

---

## 2. Gap analysis (goal §1단계)

### 2.1 What a person actually does, and whether the tool can

Enumerated from the reading surfaces of Naver Blog — search, a blog, a post, the directory, and the
neighbour graph. Writing actions are excluded by D1/D2 and are not counted as gaps.

| # | 사람이 하는 일 | 익명? | 지금 | 비고 |
|---|---|---|---|---|
| 1 | 키워드로 글 검색 | ✅ | `search --type post` | |
| 2 | 키워드로 블로그 검색 | ✅ | `search --type blog` | |
| 3 | 닉네임·아이디로 사람 찾기 | ✅ | `search --type id` | |
| 4 | 정확도/최신순 정렬 | ✅ | `--sort` | |
| 5 | 검색 기간 지정 | ✅ | `--since` / `--until` | 서버가 실제로 거름 (23,042 vs 12M) |
| 6 | **내돈내산 글만 보기** | ✅ | ❌ | **채택** — §2.2 |
| 7 | **태그로 글 찾기** | ✅ | ❌ | **채택** — §2.2 |
| 8 | 연관 검색어 보기 | ✅ | ❌ | 보류 — §2.3 |
| 9 | 이미지로 검색 | ✅ | ❌ | 보류 |
| 10 | 블로그 카테고리 트리 보기 | ✅ | `blog` | |
| 11 | 블로그 글 목록 보기 | ✅ | `posts` | |
| 12 | 카테고리별 글 보기 | ✅ | `posts --category` | |
| 13 | 블로그 인기글 보기 | ✅ | `posts --sort popular` | |
| 14 | 공지 보기 | ✅ | `posts --notices` | |
| 15 | **블로그 안에서 검색** | ✅ | `posts --query` (HTML) | **채택** — JSON 이관, §2.2 |
| 16 | 블로그 안에서 태그로 찾기 | ✅ | ❌ | 보류 — `/search/tag` 200 확인 |
| 17 | 글 본문 읽기 | ✅ | `post` | |
| 18 | 댓글·답글 읽기 | ✅ | `post` | |
| 19 | 이웃 목록 보기 | ✅ | `buddies` | |
| 20 | 주제 목록 보기 | ✅ | `topics` | |
| 21 | 주제별 글 보기 | ✅ | `topic` | |
| 22 | 주제 인기글 보기 | ✅ | `topic --top` | |
| 23 | 요즘 인기 주제 보기 | ✅ | ❌ | 보류 — §2.3 |
| 24 | 이달의 블로그·에디터픽·테마 | ✅ | ❌ | 보류 — §2.3 |
| 25 | 공식블로그 목록 | ✅ | ❌ | 보류 — 18,315개 / 7 카테고리 |
| 26 | 모먼트(짧은 영상) 보기 | ✅ | ❌ | 보류 |
| 27 | 글의 해시태그 보기 | ❓ | ❌ | **미확인** — §2.5 |
| 28 | 시리즈(연재) 보기 | ❓ | ❌ | **미확인** — 엔드포인트 없음 |
| 29 | 이웃새글 피드 | 🔒 | — | 로그인, D1/D2로 범위 밖 |
| 30 | 안부글 | 🔒 | — | §2.4 |
| 31 | 방문자수 | 🔒 | — | §2.4 |
| 32 | 좋아요 누른 사람 보기 | 🔒 | — | §2.4 — 카운트만 옴 |
| 33 | 글·댓글 쓰기, 이웃 추가 | 🔒 | — | D1/D2, 영구 범위 밖 |

### 2.2 채택 — 세 조건이 모두 강한 것 (goal §1단계 판정 기준)

**내돈내산 필터.** `isBuyWithMyOwnMoney=true`. 에어팟 검색 기준 1,178,608 → **3,397**, 상위 결과가
전부 다른 글로 바뀝니다. 스킬의 `description`이 "내돈내산"을 트리거 문구로 이미 내걸고 있는데
그 요청을 받아도 지금은 일반 검색으로 처리하는 것 말고 할 수 있는 게 없습니다. (a)(b)(c) 모두 강함.

**태그 검색.** `/api/tags/search/post` 1,432,156건, `/api/tags/related`로 연관 태그 10개.
태그는 네이버 블로그에서 사람이 실제로 누르는 1차 내비게이션 표면입니다. (a)(b)(c) 모두 강함.

**블로그 내 검색 JSON 이관.** 새 기능이 아니라 **기존 프리미티브의 기반 교체**입니다. 현재는
`blog.naver.com/PostSearchList.naver` HTML을 긁어 `logNo` 10개를 뽑고 다시 hydrate합니다.
`/api/blogs/{blogId}/search/post`는 페이지당 20개를, 진짜 `totalCount`/`totalPage`와 함께,
**이미 채워진 항목으로** 돌려줍니다(`title`, `contents`, `addDate`, `categoryName`, `commentCount`,
`sympathyCount`, `thumbnailUrl`) — hydrate 호출이 통째로 사라집니다. recon Q-4가 "네이버 템플릿
변경이 필드가 아니라 *프리미티브 자체*를 깨뜨리는 유일한 지점"으로 지목한 코드가 바로 여기입니다.

### 2.3 보류 — 익명 가능하지만 이번에 안 만드는 것

전부 라이브 확인됐고 시그니처도 기록돼 있으니, 다음 아크에서 다시 발견할 필요가 없습니다.

| 표면 | 엔드포인트 | 확인된 내용 |
|---|---|---|
| 오늘의 인기 주제 | `TodayHotTopicList`, `HotTopicKeywordList`, `HotTopicList?keywordSeq=` | 키워드 5~7개 + 각 키워드의 글 목록 |
| 연관 검색어 | `RelatedKeywordList?keyword=` | 14개 |
| 인기 키워드 | `/api/v1/popular-keywords` | 12개 + `keywordDate` |
| 이달의 블로그 | `ThisMonthDirectoryList`, `ThisMonthDirectoryBlogList?year=&month=` | 주제 3개, 각 블로그+최근글. **현재 콘텐츠로 살아있음** |
| 에디터 추천 | `EditorPickList?year=&month=` | 살아있음 |
| 테마 추천 | `ThemeGroupList`, `ThemeList?year=&month=` | 살아있음 (미술 이야기, 뜨개질, 코딩 배우기) |
| 공식 블로그 | `OfficialBlogCategoryList`, `OfficialBlogList?categoryNo=&pageNo=` | 18,315개 / 916페이지 / 7 카테고리 |
| 블로그 내 태그 검색 | `/api/blogs/{id}/search/tag?query=` | 200, 라우트 유효 |
| 검색 버티컬 | `search/v1/{image,moment,product-post}` | 48M / 139K / 471 |
| 모먼트 | `api-moment.blog.naver.com/blogs/{id}/moments`, `/moments/recent` | 전역 328,018 |
| 블로그 신원 | `api-blog.blog.naver.com/blogs/{id}` | `introduce` 포함, `post_count`는 **없음** |

`year`/`month`에 대한 주의: 최신 기간보다 미래·근접 값을 넣으면 전부 최신 회차를 돌려주고,
과거 값(2020-03 등)은 실제 그 회차를 돌려줍니다. 파라미터가 무시되는 게 아니라 상한에서 잘립니다.

### 2.4 익명 불가로 확정 — 다시 시도하지 말 것

측정된 실패 모양까지 적어 둡니다. 추측이 아니라 관측입니다.

| 표면 | 결과 |
|---|---|
| `/api/blogs/{id}/buddies/total-count` | **403** `not_blog_owner` — 이웃 총계는 소유자 전용. `public-buddies`의 총계를 쓸 것 |
| `ChallengeCategoryList` | `notlogined` |
| `PowerBlogList` | `{code: "error"}` — 파워블로그 제도 폐지. `PowerBlogDirectoryList`는 응답하지만 짝이 죽어 무의미 |
| `RookieList?year=&month=` | 2026-07 / 2026-06 / 2025-03 / 2020-03 **전부 빈 목록** — 사실상 죽은 기능 |
| `/posts/{logNo}/sympathy-users` | 200이지만 `sympathyUserViewList: []` — 총계(244)만 오고 **명단은 익명에 안 줌**. 그래프 간선으로 못 씀 |
| 안부글 `GuestBookList.naver` | m 302 → 오류 페이지, PC 404 |
| 방문자수 `NVisitorgp4Ajax.naver` | **204**, 본문 없음 |
| recon §3.3의 로그인 목록 | `BuddyPostList`, `NewsList`, `MyTraceList`, `BlogNotificationList`, `BuddyList` — 변동 없음 |

### 2.5 미확인 — 모른다고 적어 두는 것

- **글의 해시태그.** 모바일 글 HTML(`m.blog.naver.com/{id}/{logNo}`)에 태그가 **없습니다.** 잡히는
  `tagName` 7건은 전부 네이버 DOM 스크립트지 블로그 태그가 아닙니다. 273KB·661KB 두 문서에서
  `post_tag`/`TagView` 클래스 0건. 태그를 다는 글인데도 그렇습니다 — `tags/search/post`가 반환한
  글조차 그 글 HTML에는 태그 마크업이 없었습니다. PC 페이지나 별도 호출이 필요할 수 있으나
  **확인하지 않았습니다.** 태그 검색(§2.2)과는 별개 문제입니다.
- **시리즈(연재).** section 번들·모바일 번들 어느 쪽에도 엔드포인트가 없습니다. 기능이 없는 건지
  다른 경로인지 **판정 못 했습니다.**

---

## 3. "100점"의 정의 — 측정 가능한 체크리스트 (goal §"100점")

"완벽하게"는 판정 불가라 목표가 될 수 없다는 지적에 따라, 숫자로 채운 표입니다.
왼쪽이 이번 세션에 측정된 값, 오른쪽이 합의된 범위를 구현한 뒤 만족해야 할 값입니다.

| 지표 | 지금 (2026-07-25 측정) | 이 아크 완료 시 |
|---|---|---|
| 사람이 하는 행동 (열거된 총계) | 33 | 33 |
| — 로그인 필요라 영구 범위 밖 (D1/D2) | 5 | 5 |
| — 익명 가능 여부 미확인 | 2 | 2 (해시태그·시리즈, 판정 시도) |
| — **익명 가능** | **26** | 26 |
| — 그중 도구가 커버 | **17 / 26 (65%)** | **19 / 26 (73%)** |
| — 익명 가능한데 아직 안 만든 것 | 9 | 7 (전부 §2.3에 시그니처 기록됨) |
| 라이브 스윕 (명령 × 블로그) | **224 / 224 exit 0** (32 블로그 × 7) | 새 표본으로 재스윕, 신규 명령 포함 |
| exit 0인데 데이터가 틀린 결함 | **1** (`post_count`/`buddy_count` 영구 null) | **0** |
| HTML 스크래핑에 의존하는 프리미티브 | 2 (`posts --query`, `post` 본문) | 1 (`post` 본문만 — 대체 없음) |
| E2E 시나리오 | 10 통과 / 1 손으로 대조 | 10 + 신규 3, 손 대조 **4 이상** |

커버율이 65% → 73%로만 오르는 것은 의도된 것입니다. 보류한 7개는 (a)(b)(c) 중
"사람이 자주 쓰는가"가 약하다고 판단된 것들이고, 목표 문서가 "갭이 여러 개면 전부 만들지 말고
우선순위를 물어라"라고 지시한 대로 물어서 정한 결과입니다. 숫자를 올리려고 만드는 것은
이 프로젝트가 피해 온 실패 모양입니다.

---

## 4. 합의된 범위

이번 세션에 물어서 정한 것 (goal §"물어봐라"):

1. **범위** — 온미션 3개만: 내돈내산 필터, 태그 검색, 블로그 내 검색 JSON 이관.
2. **`buddy_count`** — `totalPublicBuddyCount`(공개 이웃 수). §1.3 참조.
3. **블로그 내 검색** — HTML 폴백 없이 JSON으로 완전 이관.
4. **인터페이스** — 새 명령 없이 기존 `search`에 플래그 추가.

구현 명세는 `13-build-spec.md`. **이번 세션에서 패키지·스킬 코드는 건드리지 않았습니다.**

## 5. 재현 방법

```
.venv/bin/python3 scratch/sweep/assemble2.py   # 87개 신규 블로그 (기존 68개 제외)
.venv/bin/python3 scratch/sweep/sweep2.py      # 32 블로그 × 7 명령 + raw 대조
.venv/bin/python3 scratch/sweep/sweep2b.py     # --query 재실행, created_at 연령별, 이웃 총계
```

`scratch/`는 `.gitignore`에 있어 이 스크립트들은 **저장소에 커밋되지 않습니다** — 첫 아크의
`sweep.py`와 같은 취급입니다. 로컬에 남아 있고, 없으면 `assemble2.py`의 `TOPIC_SEQS`/`SEARCH_TERMS`를
바꿔 다시 만들면 됩니다.

엔드포인트 탐침 스크립트는 세션 스크래치패드에 있었고 저장소에 넣지 않았습니다. 시그니처는
`13-build-spec.md` §2에 전부 옮겨 적었으니 번들을 다시 캐지 않아도 됩니다.
