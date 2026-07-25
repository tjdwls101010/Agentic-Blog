# Next arc — coverage goal

**What this is.** A ready-to-paste goal statement for the session that takes the package and skill
from "works well for seven commands" to "covers how people actually use Naver Blog."

**How to use it.** Copy the fenced block below verbatim into a fresh session. It is written to be
self-contained: it carries the starting facts, the process lessons this project paid for, and the
gates, so the session does not rediscover them.

**Why it is planning-only.** `docs/plan/02-recon-findings.md` §3.3 alone lists nine unimplemented
anonymous endpoints, and a real gap analysis will find more. Deciding scope and priority is its own
job; the arc after this one implements whatever gets agreed. The previous arc used the same split
and it worked.

**Status of the previous arc, for context:** package v0.1.2 on PyPI, skill merged (PR #5), all ten
E2E scenarios passing. See `08-skill-session-kickoff.md` → `09-package-defects.md` →
`10-skill-spec.md`.

---

```
# 목표

`agentic-blog` 패키지와 `naver-blog` 스킬을, **사람이 네이버 블로그를 쓰는 방식을 클로드가
그대로 할 수 있는** 수준까지 끌어올린다. 패키지는 수단이고 스킬이 목적이다 — 어떤 결정이든
"이게 클로드의 네이버 블로그 사용 능력을 실제로 늘리나?"로 판단해라.

## 이번 세션은 "계획만" 한다

지난번처럼 계획 세션과 구현 세션을 분리한다. 한 세션에서 둘 다 하면 양쪽 다 부실해진다.
산출물은 `Agentic Blog/docs/plan/`에 저장하고, 구현은 다음 세션에서 한다.
계획이 확정되기 전에 코드를 고치지 마라.

## 시작 상태 (재발견하지 마라)

- 패키지 `agentic-blog` **v0.1.2** PyPI 배포됨. 스킬은 `.claude/skills/naver-blog/SKILL.md`.
- 현재 명령 7개: `search`, `blog`, `posts`, `post`, `buddies`, `topics`, `topic` (+ `catalog`, `schema`).
- `docs/plan/08~10`이 직전 작업 기록. `07-skill-plan.md`는 superseded.
- 라이브 스윕 스크립트가 `scratch/sweep/`에 있다. 7개 명령 × 블로그 30개 = 210런. 재사용해라.
- `popular` 카드는 이미 감사했고 **깨끗하다.** 다시 하지 마라.
- `notice` 카드만 스키마가 달랐고 v0.1.2에서 고쳤다.

## 1단계 — 갭 분석 (이번 세션의 핵심)

**"사람이 네이버 블로그에서 하는 일" 전체를 나열하고, 각각에 대해 이 도구가 할 수 있는지
없는지 판정해라.** 내 추측을 받아쓰지 말고 직접 확인해라.

출발점은 이미 저장소에 있다. `docs/plan/02-recon-findings.md` §3.3이 **JS 번들에서 발견됐지만
v1에 구현 안 한 익명 접근 가능 엔드포인트**를 나열한다:

  RelatedKeywordList (연관 검색어), PowerBlogList, RookieList, OfficialBlogList,
  ThisMonthDirectoryBlogList (이달의 블로그), EditorPickList, ThemeList,
  HotTopicKeywordList, TodayHotTopicList, HotTopicChallengeList

같은 문서가 **로그인 필요라서 범위 밖**인 것도 나열한다 (BuddyPostList=이웃새글, NewsList,
MyTraceList, BlogNotificationList, BuddyList, 그리고 모든 쓰기). D1/D2가 load-bearing이니
이건 건드리지 마라 — 익명 전용이 이 패키지의 최대 강점이다.

이 목록 밖에도 있을 수 있다. 태그 페이지, 시리즈/연재, 모먼트, 블로그 내 태그 목록,
검색 필터 옵션 같은 것들은 **직접 확인해라.** 실제로 브라우저에서 사람이 뭘 클릭하는지
생각하고, 그 요청이 익명으로 되는지 curl로 검증해라. 검증 안 된 건 "미확인"이라고 표시해라.

각 갭에 대해 판정해라: (a) 익명 접근 가능한가 (b) 사람이 실제로 자주 쓰는가
(c) 없으면 스킬이 못 답하는 질문이 뭔가. **셋 다 강한 것만 구현 후보다.**

## 2단계 — 현재 패키지 품질 재검증

새 기능을 얹기 전에 지금 것이 튼튼한지 확인해라. 지난 세션에서 라이브 스윕이 프로덕션
결함 8개를 찾았고, 그 전까지 테스트 787개는 전부 통과하고 있었다.

- 스윕을 다시 돌려라. 이번엔 블로그 샘플을 **다르게** 뽑아라 (같은 30개는 같은 결함만 본다).
- exit 코드만 보지 마라. 지난번 결함 중 둘은 exit 0이면서 데이터가 틀렸다.

## 반드시 지킬 원칙 (지난 세션에서 실제로 데인 것들)

**픽스처만으로 검증된 파서는 검증된 게 아니다.** 이 패키지의 테스트는 네트워크를 안 탄다.
그래서 `posts`가 실제 블로그 30개 중 21개에서 죽는데도 787개 테스트가 초록이었다. 손으로
쓴 픽스처는 작성자의 가정을 인코딩하는데, 틀리는 건 정확히 그 가정이다. 픽스처는 **실제
캡처에서** 만들어라.

**엄격함 + 좁은 표본 = 자해.** 지난 세션에 내가 직접 저질렀다. 포스트 날짜 추출을 엄격하게
만들었더니 네이버가 최근 글에 렌더링하는 "7시간 전" 같은 **정상 데이터**에서 명령이 죽었다.
재스윕이 릴리즈 전에 잡았다. 파서를 조일 때는 조이는 대상이 "드리프트"인지 "내가 아직 못
본 정상 케이스"인지 먼저 물어라. 모르면 raise 대신 null이 대개 정직하다.

**우연히 맞는 값을 조심해라.** `_search_visibility`는 플래그 3개를 검사하고 `return "public"`
으로 끝난다. 공지 카드는 그 플래그가 **하나도 없어서** 없는 필드 3개 덕에 public으로 나오고
있었다. 값은 맞는데 근거가 없었다. 이런 건 스윕의 exit 코드 검사로는 절대 안 잡힌다.

**스킬은 레일이 아니라 원칙으로 써라.** 규칙은 작성자가 열거한 경우만 커버하고 16번째
케이스에서 부러진다. 도메인이 어떻게 생겼는지 설명하고 모델이 스스로 도출하게 해라.
지난 E2E에서 이게 증명됐다: `posts --query`를 *왜* 선호하는지만 알려줬더니, 모델이 그걸 쓰고
→ 예산에 걸리고 → 네이버 자체 검색의 오탐을 발견하고 → 전체 목록으로 폴백하고 → 이유를
공개했다. "전체 목록 절대 금지"라는 레일이었다면 더 나쁜 답을 강요했을 것이다.

**E2E가 아니면 못 잡는 게 있다.** `validate_harness.py` 통과는 스킬이 *작동한다*는 뜻이
아니다. 지난번 10개 시나리오가 잡은 것: 트리거 발동, near-miss 배제, 그리고 `brief`(네이버
요약)로 답하고 `body`인 척하는 실패 — 이건 유창하고 자기일관적이라 오프라인에선 안 보인다.
새 명령을 추가하면 그 명령의 E2E 시나리오도 추가해라. 답변의 유창함을 통과 기준으로 삼지 말고,
**가져온 파일과 손으로 대조해라.**

## "100점"의 정의 (측정 가능하게 만들어라)

"완벽하게"는 판정 불가라 목표가 될 수 없다. 이번 세션에서 아래를 채운 체크리스트를
계획서에 만들어라:

- 사람이 하는 행동 N개 중 M개를 도구가 커버한다 → N과 M을 실제 숫자로 채워라
- 커버 못 하는 것 각각에 대해: 익명 불가라서인가, 아직 안 만들어서인가
- 라이브 스윕 통과율 (명령 × 블로그)
- E2E 시나리오 통과 수, 그중 손으로 대조한 것 수

## 물어봐라 (혼자 정하지 마라)

- **출력 스키마 변경**은 배포된 패키지의 공개 계약이다. 필드 추가/변경 전에 물어라.
  (참고: `viewCount`는 이미 검토했고 "추가 안 함"으로 결정됐다. `docs/wiki/Output-Schema.md` 참조.)
- **명령 추가**는 스킬의 트리거 표면과 catalog를 바꾼다. 어떤 걸 만들지 목록으로 합의해라.
- 갭이 여러 개면 **전부 만들지 말고** 우선순위를 물어라. 나는 일관되게 린한 쪽을 택해왔다.
- 조금이라도 헷갈리면 AskUserQuestion을 써라. 수십 개도 좋다. 추정해서 만들었다가
  나중에 문제가 생기는 게 훨씬 비싸다.

## 하지 말 것

- 인증 계층 추가 (D1/D2가 load-bearing). 로그인/세션/쿠키/브라우저 전부 금지.
  이 패키지엔 exit 2도 없다 — 형제 스킬의 습관을 가져오지 마라.
- `Agentic Blog/CLAUDE.md` 확장 (이미 검토했고 린한 범위로 결정됨)
- 요청 안 한 리팩터링. 바뀐 줄은 전부 목표로 추적돼야 한다.
- 계획 확정 전 구현

## 마무리

깃 처리는 지난 세션과 동일하게: 브랜치 → PR → 머지. 패키지 코드가 바뀌면 릴리즈까지
(태그만으론 부족하다 — `publish.yml`이 `release: published`에 걸려 있어서 GitHub Release를
만들어야 PyPI에 올라간다). 스킬만 바뀌면 릴리즈 없이 머지.
```
