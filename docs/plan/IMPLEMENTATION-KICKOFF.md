# Implementation kickoff prompt (paste into a fresh session)

Open a new Claude Code session **in the `Agentic Blog` repo** and paste the box below.

---

```
agentic-blog v0.1 (네이버 블로그 리더)를 구현해줘. 이건 구현 세션이야 (계획은 지난 세션에 끝났고, 계획과 구현을 분리하기 위한 것).

먼저 계획 문서를 순서대로 정독해 (docs/plan/):
- 00-overview.md              ← 목적/비목적, "5형제 중 가장 쉬운 접근" 핵심
- 01-decisions.md             ← 사용자와 합의된 결정 로그 (D1~D15) + 뒤집힌 가정들
- 02-recon-findings.md        ← 라이브 리콘 실측 (엔드포인트·파라미터·envelope·함정 12개)
- 03-architecture.md          ← 모듈 구조, 네이밍, 저장소, 데이터 모델/스키마
- 04-cli-spec.md              ← 전체 명령 표면, 플래그, exit code, 출력 계약
- 05-testing-and-ci.md        ← 테스트/픽스처/CI/배포/PII 규율
- 06-implementation-phases.md ← verify 게이트가 달린 단계별 로드맵 (메인)
- 07-skill-plan.md            ← 스킬은 PyPI 배포 후 별도 세션 (지금 X)

배경 한 줄: agentic-blog은 형제 도구 agentic-facebook / agentic-x(agentic-twitter) / agentic-threads / agentic-reddit의 다섯째다. 그런데 **접근 방식이 형제 넷과 근본적으로 다르다** — 네이버 블로그는 로그인 없이, 쿠키 없이, 브라우저 없이, 회전하는 토큰 없이 순수 httpx로 깨끗한 JSON이 나온다. 리콘에서 전부 실측 검증됐다.

반드시 지킬 제약 (CLAUDE.md + 형제 규율 + D1):
- 최소 코드, 수술적 변경, 투기적 추상화·미요청 기능 금지. 비목표(쓰기 작업 전부, 로그인 필요 기능 전부, 네이버 타 서비스, crawl/배치/데몬)는 만들지 마.
- **인증 계층을 만들지 마.** auth.py / session.py / docids.py / transaction.py / _stealth_init.js / scrapling / playwright / [browser] 익스트라 — 전부 없다. 형제 코드를 습관적으로 복사하다가 만들게 되면 멈추고 D1을 다시 읽어.
- **login / setup / status / doctor 명령 없음, --profile 플래그 없음.** 상태가 없으니 설정할 것도 진단할 것도 없다.
- 런타임 의존성은 정확히 3개: httpx, platformdirs, lxml. 4번째가 필요해 보이면 먼저 물어봐.
- rate floor 0.5s (non-bypassable), 단일 타깃 프리미티브만.
- HTML은 body.py에만. parse.py는 JSON 전용.
- 파생 불가능한 상수 3개는 반드시 "왜"를 주석으로 달아: CBOX_POOL="blogid", objectId="{blog_no}_201_{log_no}" (가운데 201은 문서화되지 않은 리터럴), POST_LIST_MAX_ITEM_COUNT=30.
- web_naver_view_log_json.json 은 절대 호출하지 마 (텔레메트리 비콘).
- UTF-8: ensure_ascii=False, 출력 파일명 한글 안전, 자르거나 길이 잴 때 ASCII 가정 금지.
- PII: scratch/, *.raw.*, output/ gitignore. 픽스처는 **합성 한국어**로 직접 작성(실제 캡처를 마스킹하는 걸로는 부족). live 테스트는 shape만 검증, 내용 검증 금지.
- DISCLAIMER 톤 약화 금지. 산출물은 전부 영어(코드/주석/README/CLI 출력) — 데이터는 한국어지만.

진행 방식 (각 Phase의 verify 게이트를 통과할 때까지 loop):
0) 02-recon-findings.md §9 표를 재검증하고 §11의 Q-1~Q-5(레이트리밋 실측, 구 에디터 커버리지, 접근불가 응답 shape, 인블로그 검색 HTML 실패 처리, orderBy 어휘)를 닫아. 결과는 §12로 **덧붙여** (2026-07-25 실측을 덮어쓰지 마 — 날짜가 찍힌 기록이 나중에 드리프트를 잡아준다).
1) 스캐폴드 + 패키징 + 오프라인 명령(catalog/schema) + CI + publish.yml 하드닝(SHA 핀 + 버전 게이트).
2) 클라이언트 + 엔드포인트 + 수직 슬라이스 하나(search --type post|blog|id)를 라이브로 관통.
3) 블로그 표면(blog / posts / buddies / topics / topic).
4) 본문 + 댓글(post) + 블로그 내 검색(posts --query).
5) 하드닝 + 문서 + 버전.
6) PR → main 머지 → GitHub Release(→ publish.yml → PyPI Trusted Publishing). 설치 검증.
7) 스킬은 별도 세션(07-skill-plan.md).

시작 전에: 계획 문서를 읽고 → Phase 0 실행 계획을 짧게 제시하고 진행. 계획을 벗어나는 스코프 변경이 필요하면 먼저 물어봐.
```

---

**Notes for you (not part of the paste):**

- Repo is `github.com/tjdwls101010/Agentic-Blog` (branch `main`). It already contains
  `pyproject.toml` (**`0.0.1`, `requires-python >=3.9` — both need changing**),
  `src/agentic_blog/__init__.py`, `LICENSE`, `README.md`, `.gitignore`, and
  `.github/workflows/publish.yml`.
- **PyPI Trusted Publishing is already configured and proven** — `agentic-blog 0.0.1` was published
  through it (workflow `publish.yml`, environment `pypi`). Keep both names. The two hardening items
  are in `05-testing-and-ci.md`.
- **Naming triple**: dist `agentic-blog` / import `agentic_blog` / command `agentic-blog`. Env
  override `AGENTIC_BLOG_DATA_DIR` (**not** `_PROFILE_DIR` — there are no profiles).
- **The repo's `CLAUDE.md` is a verbatim copy of the generic root one** (`AGENTS.md` is a symlink to
  it), so it carries the four general coding guidelines and nothing project-specific. Project rules
  live in this plan, not in `CLAUDE.md`, until the skill session extends it (`07-skill-plan.md`).
- **Test blogs used during recon** (all public, all read-only): `znogi` (rich SmartEditor ONE posts,
  42-comment thread), `lee_haimin`, `peopleteria` (4,982 neighbours, pre-2015 legacy-editor posts —
  the best legacy-parser test case).
- The recon technique that found everything, for when these endpoints rot: **mine the site's own JS
  bundles**. `section.blog.naver.com`'s `NgAppBundle1/2` contain every `/ajax/*.naver` call site with
  its exact parameter object. For lazily-loaded requests (comments, neighbours) a headless capture
  was needed — but both were re-verified with pure `curl` afterwards, and **no browser belongs in
  the shipped package**.
- Library docs cached locally at `../.tmp/docs_scrapling/` and `../.tmp/docs_crawl4ai/` are **not
  relevant to this project** — neither library is a dependency. crawl4ai was explicitly evaluated
  and rejected (D7); don't reach for it when the body parser gets fiddly.
- If the repo venv lacks the package or has a stale console-script shebang, run as
  `PYTHONPATH=src .venv/bin/python -m agentic_blog.cli …`, and `git commit --no-verify` if the
  pre-commit hook can't launch (same workarounds as the four siblings).
