# Build spec — the agreed scope

**Status:** approved this session (2026-07-25), **not implemented**. The arc after this one builds it.
**Scope decided in:** `12-coverage-gap-analysis.md` §4.
**Rule that governs every line below:** 바뀐 줄은 전부 이 문서의 항목으로 추적돼야 합니다.

Three items, and nothing else:

1. `search --self-purchased` — 내돈내산 필터
2. `search --type tag` — 태그 검색
3. `posts --query` — HTML 스크래핑 → JSON 이관

Plus one defect fix that the re-verification sweep found (`12-…` §1.3), because shipping a coverage
release on top of two permanently-null schema fields would be indefensible.

---

## 1. The backend decision, and the evidence for it

The 내돈내산 필터와 태그 검색은 `m.blog.naver.com/api/search/*`에만 있고, 지금 `search`는
`section.blog.naver.com/ajax/SearchList.naver`를 씁니다. 어느 쪽을 쓸지 측정해서 정했습니다.

| 측정 | section | mobile v1 |
|---|---|---|
| 같은 질의·정렬의 결과 집합 | — | **상위 20개 전부 동일, 4개 질의 모두 20/20** |
| 페이지당 상한 | 30 | 30 (동일) |
| **실제로 꺼낼 수 있는 글 수** | **1,000** | **1,000 (동일)** |
| `totalCount` | 1000 (정직한 상한) | 12,356,134 (§1.1 참조) |
| 채울 수 있는 `Post` 필드 | 9 | **14** |
| `--since`/`--until` | 동작 | 동작 |
| 내돈내산 / 태그 | 없음 | 있음 |
| 닉네임(id) 검색 | 있음 | **없음** |

**결정:**

- **`--type post` → mobile v1으로 이관.** 결과 순위가 바뀌지 않는 것이 확인됐고(20/20 × 4),
  깊이 상한도 같으며, 필드가 5개 더 채워지고, 새 기능 두 개가 같은 백엔드에 있습니다.
- **`--type blog` → section 유지.** 이관하면 안 됩니다. mobile `v2/blog`는 **다른 코퍼스**입니다:
  같은 질의에 section 15,441건 / mobile 5,611건이고 상위 5개 중 1개만 겹칩니다. 게다가 mobile 항목엔
  `blogDesc`가 없어 **지금 채워지고 있는 `Blog.description`이 null로 퇴행합니다.**
- **`--type id` → section 유지.** mobile에 대응물이 아예 없습니다.

한 명령이 두 백엔드를 쓰게 되지만, 그 경계가 `--type`이라 조건이 하나뿐이고 사용자에게도
"글 검색"과 "블로그·사람 검색"이라는 자연스러운 경계와 일치합니다.

### 1.1 반드시 기록할 함정 — mobile의 `totalCount`는 페이지 수가 아닙니다

`section`은 어떤 질의에도 `totalCount: 1000`을 돌려주고, 실제로 34페이지(=1,000건)에서 끝납니다.
`mobile`은 `totalCount: 12356134`, `totalPage: 411872`를 돌려주지만 **34페이지에서 10건, 40페이지에서
0건으로 똑같이 끝납니다.** 게다가 그 값은 페이지마다 흔들립니다(12356134 → 12356156 → 12356157).

즉 mobile의 `totalCount`/`totalPage`는 **코퍼스 규모 추정치**지 페이지네이션 경계가 아닙니다.
이걸 믿고 도는 코드는 411,872페이지를 향해 헛돕니다. recon 함정 #5(`post-list.totalCount`가 0이라
못 쓴다)와 같은 계열이고, 이번 건이 더 위험합니다 — **0은 의심을 사지만 12,356,134는 사지 않습니다.**

구현 규칙: **`totalCount`/`totalPage`를 페이지네이션 판단에 쓰지 마라.** 기존 방식대로
"요청한 것보다 적게 온 페이지"에서 멈춥니다. 두 값은 `--raw`에만 남기고 `Post`로 승격하지 않습니다.

### 1.2 `Referer`가 403을 가릅니다 (UA 아님)

| 헤더 | 결과 |
|---|---|
| 모바일 UA + Referer | 200 |
| **데스크톱 UA + Referer** | **200** |
| 모바일 UA, Referer 없음 | **403** |
| **Referer만** | **200** |

recon 함정 #11("Referer는 모든 호스트에서 필수")이 이 호스트에도 그대로 적용되고, **UA는 무관**합니다.
`client.py`가 이미 호스트별 Referer를 붙이므로 새 기제는 필요 없습니다. UA 선택으로 이 403을
디버깅하려는 다음 세션을 막기 위해 적어 둡니다.

---

## 2. 엔드포인트 시그니처 (번들에서 추출, 라이브 검증 완료)

번들을 다시 캘 필요가 없도록 그대로 옮깁니다.

### 2.1 글·태그 검색 — `m.blog.naver.com`

```
GET /api/search/v1/{post|tag}
    ?keyword=<UTF-8>
    &sortType={sim|date}
    &page=<1-based>
    &itemCount=<n>              # ≤ 30
    &startDate=YYYY-MM-DD       # optional
    &endDate=YYYY-MM-DD         # optional
    &isBuyWithMyOwnMoney=true   # optional, post only
```

봉투: `{"isSuccess":true,"result":{ "list":[...], "currentPage", "totalCount", "totalPage",
"searchType", "sortType", "hasBuyWithMyOwnMoneyPost", "authUrlType", "isValidList", ... }}`

`list[]` 항목 (검증됨): `blogId`, `blogNo`, `logNo`, `url`, `title`, `content`, `addDate`(epoch ms),
`blogName`, `nickname`, `categoryName`, `commentCount`, `sympathyCount`, `thumbnailUrl`,
`thumbnailCount`, `isMarketPost`, `isThisDayPost`, **`isBuyWithMyOwnMoney`**, `product`,
`isCommentVisible`, `isSympathyVisible`, `profileImageURL`.

- `title`·`content`에 **`<em class="highlight">…</em>`** 가 박혀 옵니다. section의
  `<strong class="search_keyword">`와 **태그가 다릅니다** — 기존 스트리퍼가 그대로 듣지 않습니다.
  파서는 두 형태를 모두 벗겨야 합니다.
- `periodType`은 **보내지 마세요.** 번들이 안 보냅니다. UI 전용 개념이고 실제 파라미터는
  `startDate`/`endDate`입니다. 넣어도 결과가 안 변하는 것을 확인했습니다(12,087,040 동일).

`--type tag`는 `/api/search/v1/tag`로도, `/api/tags/search/post`로도 갈 수 있습니다. **전자를 쓰세요** —
`search`의 다른 타입과 같은 봉투·같은 파라미터·같은 정렬이라 코드 경로가 하나로 유지됩니다.
(`/api/tags/search/post`는 `page`/`itemCount`에 별도 봉투를 쓰고 `items[]` 키가 다릅니다.)

### 2.2 블로그 내 검색 — `m.blog.naver.com`

```
GET /api/blogs/{blogId}/search/post
    ?query=<UTF-8>              # NOT "keyword" — keyword sends HTTP 500
    &sortType={sim|date}
    &page=<1-based>
    &startDate=YYYY-MM-DD       # optional
    &endDate=YYYY-MM-DD         # optional
```

경로 마지막 마디는 **`post`** 입니다. 번들의 열거형이 `IN_BLOG_POST:"inBlogPost"`라 그걸 넣기 쉬운데,
**`inBlogPost`은 302로 오류 페이지에 떨어집니다.** 그건 UI 모드 이름이지 경로가 아닙니다.
파라미터 이름도 전역 검색과 달라서 `query`이며 `keyword`를 보내면 **500**입니다. 둘 다 실제로 밟아 봤습니다.

봉투: `{"isSuccess":true,"result":{"list":[...], "currentPage","totalCount","totalPage",
"searchType","sortType","isValidList","authUrlType","query","adult","suicideWord","adultUser"}}`

`list[]` 항목: `blogId`, `blogNo`, `logNo`, `title`, `contents`, `addDate`, `categoryName`,
`commentCount`, `sympathyCount`, `thumbnailUrl`, `thumbnailCount`, `isMemo`,
`isCommentVisible`, `isSympathyVisible`. 페이지당 **20건**.

`/search/tag`도 유효한 라우트지만(200 확인) 이번 범위 밖입니다.

### 2.3 이번에 안 쓰는, 그러나 확인된 것

`/api/tags/related?query=` — 연관 태그 10개. 이번 범위에서 제외됐고 시그니처만 남깁니다.
나머지 보류 표면은 `12-…` §2.3에 있습니다.

---

## 3. 패키지 변경

### 3.1 `search`

| 변경 | 내용 |
|---|---|
| `--type` | `post`·`blog`·`id`에 **`tag` 추가** (4개) |
| `--self-purchased` | 새 불리언 플래그. **`--type post`에서만** 유효 |
| 백엔드 | `--type post`·`tag` → mobile v1 / `--type blog`·`id` → section (§1) |

`--self-purchased`를 `--type blog`·`id`·`tag`와 함께 주면 거부합니다 — `--query`가 `--raw`를 거부하는
방식과 같은, 이미 이 CLI에 있는 관용구입니다.

**출력 변화 (필드 추가 없음).** `--type post` 결과에서 지금 항상 null인
`blog_no`·`category_name`·`comment_count`·`like_count`·`thumbnail_url`이 **값을 갖게 됩니다.**
스키마에 필드가 추가되거나 타입이 바뀌지는 않고, 이미 문서화된 약속("Number of comments" 등)이
비로소 지켜지는 것입니다. 다만 배포된 패키지의 관측 가능한 동작 변화이므로 **마이너 범프**로 내고
릴리즈 노트에 명시합니다. 구현 세션에서 이 항목만 따로 확인받으세요.

### 3.2 결함 수정 — 영구 null인 두 필드 (`12-…` §1.3)

| 필드 | 출처 | 비고 |
|---|---|---|
| `Blog.post_count` | `category-list` → `mylogPostCount` | `parse.py:230`이 이미 검증만 하고 버리는 값 |
| `Blog.buddy_count` | `public-buddies` → **`totalPublicBuddyCount`** | 이번 세션에 합의됨 |

`buddy_count`는 **공개 이웃 수**입니다. `totalMyBuddyCount`(전체 이웃)와 크게 다르며
(znogi 1 vs 248, honeybi_0405 0 vs 1,908), 공개 쪽을 고른 이유는 그것이 `buddies` 명령이 실제로
열거할 수 있는 수와 일치해서 필드와 명령이 서로를 반박하지 않기 때문입니다.

**따라서 이웃이 많은 블로그가 `buddy_count: 0`으로 나오는 것은 정상 출력입니다.** 스킬이 이걸
"이웃 없는 블로그"로 읽으면 안 됩니다 — 공개하지 않았을 뿐입니다. 테스트와 스킬 양쪽에 못 박으세요.

`post_count`를 채우려면 `blog` 명령이 이미 부르는 `category-list` 응답만 있으면 되고 추가 요청이
없습니다. `buddy_count`는 `public-buddies` 1회가 필요합니다 — `blog`가 지금 그걸 안 부르므로
**요청이 1건 늘어납니다.** 예산(100)에 영향이 있으니 구현 시 기억하세요.

### 3.3 `posts --query` — JSON 이관

`_fetch_post_search`(retrieve.py:478)를 §2.2 엔드포인트로 교체합니다. 폴백은 두지 않습니다(합의됨).

없어지는 것: `endpoints.post_search_list`, `parse.parse_post_search`, 그리고 HTML에서 `logNo`를
뽑아 다시 hydrate하던 단계 전체.

얻는 것:

- 페이지당 10 → **20건**
- **hydrate 왕복 제거** → 같은 결과에 요청 수가 줄고 예산에 덜 걸립니다
- 지금 null인 `blog_no`·`category_name`·`comment_count`·`like_count`·`thumbnail_url`이 채워집니다
- `--sort`를 `sim`·`date` 둘 다 받을 수 있게 됩니다 (HTML은 `recentdate` 하나뿐이었습니다)
- HTML 템플릿 변경에 프리미티브가 통째로 깨지던 위험 소멸 (recon Q-4)

`--query`는 이제 **`--raw`를 허용합니다** (합의됨). upstream JSON 객체가 생겼으므로 금지할 이유가
사라졌고, 다른 목록 명령과 동작이 같아집니다. `retrieve.py:559`의 거부 분기를 제거하세요.

### 3.4 손대지 말 것

인증 계층(D1/D2), `Agentic Blog/CLAUDE.md`, 요청 안 한 리팩터링, `popular` 카드(감사 완료·깨끗함),
그리고 exit 2 — 이 패키지엔 없습니다.

---

## 4. 테스트

**픽스처는 실제 캡처에서 만드세요.** 지난 아크에 손으로 쓴 notice 픽스처가 라이브가 보내지 않는
모양을 인코딩해서 파서와 픽스처가 서로 동의하고 현실과 불일치했습니다. 787개 테스트가 초록인 채로
`posts`가 30개 블로그 중 21개에서 죽었습니다.

- 새 엔드포인트 3종의 픽스처는 §2의 호출을 실제로 쳐서 저장한 응답으로 만듭니다.
- `search --type post`의 section↔mobile **동치 테스트**: 같은 질의에 두 백엔드의 `(blog_id, log_no)`
  집합이 같은지. 이번 세션에 4개 질의로 확인한 성질이고, 회귀로 굳혀 둘 값어치가 있습니다.
- `totalCount`/`totalPage`를 페이지네이션에 **쓰지 않는다**는 것을 검증하는 테스트:
  `totalPage: 411872`를 주는 픽스처에서도 짧은 페이지에서 멈춰야 합니다. §1.1이 이 테스트의 이유입니다.
- `buddy_count: 0`인데 `totalMyBuddyCount`가 큰 케이스 (honeybi_0405가 실물 예시).
- 하이라이트 스트리퍼가 `<em class="highlight">`와 `<strong class="search_keyword">`를 **모두** 벗기는지.
- **제목의 `< >`를 건드리지 않는지.** `MMCA 서울 <이것은 개념미술이 (아니)다> 전시회 후기`가 그대로
  나와야 합니다. 이번 세션에 제 검사기가 이걸 오탐했습니다 (`12-…` §1.4).

**릴리즈 전 재스윕.** 또 새로운 블로그 표본으로 돌리세요. `blogs2.json`에 안 쓴 55개가 남아 있고,
`assemble2.py`의 `TOPIC_SEQS`/`SEARCH_TERMS`를 바꾸면 더 뽑힙니다. 파서를 조일 때는
"드리프트"인지 "아직 못 본 정상 케이스"인지 먼저 물으세요 — 지난 아크에 날짜 추출을 엄격하게
만들었다가 "7시간 전"이라는 **정상 데이터**에서 명령이 죽었고 재스윕이 릴리즈 직전에 잡았습니다.

---

## 5. 스킬 변경

**레일이 아니라 원칙으로.** 규칙은 작성자가 열거한 경우만 커버하고 16번째에서 부러집니다.

### 5.1 B16을 고쳐야 합니다 — 사실이 바뀌었습니다

현재 스킬은 **"네이버는 `is_ad` 필드를 발행하지 않으며 판단이 유일한 도구"**라고 말합니다.
그 절반이 이제 틀렸습니다. 검색 항목마다 `isBuyWithMyOwnMoney`와 `isMarketPost`가 옵니다.

정확한 새 사실은 이렇습니다:

- 네이버는 여전히 **광고 플래그를 발행하지 않습니다.**
- `isBuyWithMyOwnMoney`는 **블로거의 자기 신고**입니다. 협찬이 아니라는 **보증이 아니고**,
  이 값이 없다고 협찬이라는 뜻도 아닙니다.
- 관측 근거: 필터를 켠 결과 중에 제목·본문 어디에도 "내돈내산"이라는 글자가 없는 글이 있었고
  (`hee__e__`), 그런데도 `isBuyWithMyOwnMoney: true`였습니다. 텍스트 매칭이 아니라 구조화된
  신고 값이라는 뜻입니다.

따라서 스킬은 `--self-purchased` 결과를 **"광고 없는 글"로 제시하면 안 됩니다.** "블로거가 자비
구매라고 스스로 밝힌 글"이 정확한 표현이고, B16의 판단 의무는 그대로 남습니다 — 좁아진 표본에
적용될 뿐입니다. 이 구분이 무너지면 모델은 검증되지 않은 것을 검증된 것처럼 말하게 됩니다.

### 5.2 나머지

- `--type tag`가 언제 `--type post`보다 나은지: 태그는 글쓴이가 **스스로 분류한** 축이라
  본문 전문 검색보다 정밀하고 재현율은 낮습니다. 어느 쪽을 고를지는 모델이 판단할 문제이고,
  스킬은 그 성질만 알려주고 규칙을 강요하지 않습니다.
- `posts --query`가 더 싸졌다는 것(hydrate 왕복 소멸). B12의 선호 이유가 강화됩니다.
- `buddy_count: 0`이 "이웃 없음"이 아니라 "공개 안 함"이라는 것 (§3.2).
- **1,000건 천장** (§1.1). 사람이 "다 모아줘"라고 할 때 도달 가능한 상한이고, 스킬은 자기가
  가져온 표본의 모양을 밝혀야 합니다 — B15의 "표집된 답을 완전한 답으로 제시하면 틀린 것"에
  실제 숫자가 붙는 자리입니다.
- **`catalog`/`schema`를 산문으로 옮겨 적지 마세요** (B3). 플래그가 늘었다고 스킬에 목록을
  쓰기 시작하면 다음 릴리즈에서 틀립니다.

### 5.3 E2E — `validate_harness.py` 통과는 작동한다는 뜻이 아닙니다

기존 10개 + 신규 3개, **가져온 파일과 손으로 대조**합니다. 답변의 유창함은 통과 기준이 아닙니다.

| # | 시나리오 | 손 대조로 확인할 것 |
|---|---|---|
| 11 | 내돈내산 후기 요청 | 모델이 `--self-purchased`를 쓰는가, 그리고 결과를 **"광고 없음"이 아니라 "자기 신고"로** 말하는가. §5.1이 깨지면 여기서만 보입니다 |
| 12 | 태그 기반 탐색 | `--type tag`와 `--type post`의 차이를 이해하고 고르는가, 아니면 기계적으로 하나만 쓰는가 |
| 13 | 블로그 내 검색 후 본문 | `posts --query` → `post` 연결에서 **`brief`를 `body`인 척** 하지 않는가 (지난 아크 최대 실패 모드, 유창하고 자기일관적이라 오프라인에선 안 보임) |

---

## 6. 릴리즈

패키지 코드가 바뀌므로 릴리즈까지 갑니다. **태그만으론 부족합니다** — `publish.yml`이
`release: published`에 걸려 있어서 GitHub Release를 만들어야 PyPI에 올라갑니다.
스킬은 버전을 하드코딩하지 않으며 앞으로도 그러면 안 됩니다(PyPI simple index와 대조하는 방식이
이런 릴리즈를 가로질러 스킬을 옳게 유지하는 기제입니다).

브랜치 → PR → 머지, 지난 아크와 동일합니다.
