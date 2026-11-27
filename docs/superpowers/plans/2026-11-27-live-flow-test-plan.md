# 2차 Task 11 ② 실제 흐름 테스트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 운영 주소에서 실제 메일 코드로 A·B가 로그인해, A의 요청이 A의 "내 요청"에만 보이고 B에게는 안 보이는지 자동으로 확인하고, 주소를 가린 영상을 남긴다.

**Architecture:** 메일 고르기·코드 뽑기·가리기 같은 순수 함수는 `tests/e2e/live_mail.py`(기본 테스트로 확인). 실제 흐름은 `tests/e2e/test_request_flow_live.py` 하나(`integration`): Playwright(파이썬 sync)로 화면을 움직이고, httpx로 Resend 받기 API에서 코드를 읽고, 끝나면 Supabase 관리 API로 이 실행이 만든 계정만 지운다.

**Tech Stack:** pytest, playwright 1.64.1(파이썬), httpx 0.28.1, Resend Receiving API, Supabase Auth Admin API.

**Spec:** `docs/superpowers/specs/2026-11-27-live-flow-test-design.md`

**브랜치:** `feat/phase2-live-flow-test`(최신 `main` e080f2a 이후에서), PR 하나.

## 계획 작성 중 확인한 것 (2026-11-27, 채팅 Claude)

- Resend 문서(List / Retrieve received email) 다시 확인: 목록 응답은 `{"object":"list","has_more":…,"data":[…]}`, 각 메일의 `to`는 **배열**, `created_at`은 ISO UTC(`2026-10-09T14:37:40.951Z` 꼴). `limit`은 최대 100. 목록에 `to`·`start_date` 거르기 값이 있지만 쓰지 않는다(받기 주소를 URL에 넣지 않으려고, 이 받기 도메인은 시험 메일만 받으므로 `limit=100` 한 번이면 충분). 상세 응답의 `text`는 없으면 `null`
- Supabase 관리 사용자 목록: `GET /auth/v1/admin/users?page=1&per_page=1000`, 응답 `{"users":[…]}`(저장소 `public/vendor/supabase.js` 2.119.2의 `listUsers` 요청 모양과 Supabase JS 문서로 확인)
- 하루 요청 제한은 사용자당 24시간 5개(`supabase/schema.sql`), 같은 사람·같은 모델은 `model_requests_user_model_key_unique` → 같은 모델 두 번째 요청은 `23505` → `이미 요청하셨어요`
- 요청이 성공하면 앱이 폼을 비우고 같은 화면에 완료 문구를 띄운다(`public/app.js` 제출 처리). 그래서 방어 ①은 같은 화면에서 다시 입력한다
- `tests/`에는 `__init__.py`가 없고 `from tests.ingest.db_rule import …`처럼 바로 불러온다(같은 방식, `__init__.py` 만들지 않음)
- 메일 HTML에는 코드 말고도 숫자 덩어리(색 값 `#333333`, 링크 안 토큰)가 있을 수 있다. 메일 템플릿 본문은 저장소에 없어 확인하지 못함 → 코드 뽑기는 `text`를 먼저 쓰고, 태그·링크를 지운 뒤, 앞뒤가 영문·숫자·밑줄·`#`가 아닌 6~10자리만 본다(한글은 붙어 있어도 됨: `코드는482913입니다`)
- 실패 출력에 비밀이 섞이는 길: pytest 단정문은 식 안의 값을 보여 주고, httpx 예외 문구에는 URL(user_id 포함)이 들어간다 → 흐름 전체를 한 번 감싸 실패 문구에서 비밀 글자를 가린 뒤 `pytest.fail(…, pytrace=False)`로 알린다. 단정문 식에는 개수·참거짓만 둔다
- `docs/Claude outputs/`는 `.gitignore`에 있다(영상이 git에 안 들어감)

## Global Constraints

- 앱 코드(`public/`·`app/`)는 바꾸지 않는다. 질문하지 않는다(OpenAI 0원)
- 받기 주소·받기 도메인·키·인증 코드·user_id를 print·로그·실패 문구·커밋·PR·보고에 넣지 않는다. 메일이 보이는 요소(`#request-email`·`#drawer-email`·`#login-sent-email`·`#switch-current-email`·`#login-email`)를 확인 대상으로 쓰지 않는다. Playwright trace·실패 사진은 쓰지 않는다. httpx 로그는 WARNING 위만
- 우회 머리글(`x-vercel-protection-bypass`)은 대상 주소(`E2E_BASE_URL`)로 가는 요청에만 붙인다(Supabase·Resend로 보내지 않음). `extra_http_headers`는 모든 곳으로 가므로 쓰지 않는다
- 정리는 이 실행의 두 받기 주소로 만든 계정만 지운다. 하나라도 못 지우면 테스트 실패
- 로컬 `.env` 새 이름: `RESEND_RECEIVING_API_KEY`, `RESEND_RECEIVING_DOMAIN`, `E2E_BASE_URL`(비면 `https://pyeobom.help`). `.env.example`에는 이름만(값 없음). `VERCEL_AUTOMATION_BYPASS_SECRET`은 이미 있음
- 문구(앱 원문 그대로): `요청을 받았어요. 추가되면 메일로 알려 드릴게요.` / `이미 요청하셨어요` / `내 요청 1건` / `대기` / `코드가 맞지 않아요. 다시 확인해 주세요` / `아직 요청이 없어요`
- 돌리는 횟수: 한 번. 실패하면 원인을 보고하고 멈춘다(다시 돌리기는 사용자 확인 뒤). Resend 약 5통
- 시간대: 파일 이름 등 한국 시각은 `timezone(timedelta(hours=9))`(Windows에 시간대 자료가 없을 수 있어 `zoneinfo` 안 씀)
- 테스트 먼저 커밋 → 구현 커밋, 커밋 형식·push 전 점검은 CLAUDE.md

## Review Focus

1. 코드 메일이 늦게 오거나 지난 실행 메일이 목록에 남아 있을 때 → 이번 실행 받기 주소(무작위)로, 시작 2분 전 이후에 온 메일만 고른다. Task 1 `test_pick_mail_*`
2. 메일 본문에 다른 숫자(연도·색 값·링크 토큰)가 섞일 때 → 태그·링크를 지우고, 앞뒤가 영문·숫자·밑줄·`#`가 아닌 6~10자리만 코드로 본다. Task 1 `test_extract_code_*`
3. 실패 문구에 비밀이 섞일 때 → `scrub`로 가린 뒤 `pytrace=False`로 알림. Task 1 `test_scrub_*`, Task 2 감싸기
4. 중간에 실패해 B 계정이 코드 단계에서만 만들어졌을 때 → 정리가 받기 주소로 계정을 찾아 지운다. Task 2 정리를 `finally`에서
5. 녹화 영상에 받기 주소가 보일 때 → 모든 문서에 가리는 스타일을 넣고, 채팅 Claude가 영상 장면으로 확인한다. Task 2 가리기 + Task 3
6. B의 첫 화면에서 "요약 줄 없음"이 읽기가 끝나기 전에 통과해 버릴 때 → `model_requests` 읽기 응답을 기다린 뒤 숨김을 확인. Task 2 9번

---

### Task 0: 설계·계획 커밋

- [ ] **Step 1:** `git switch main && git pull && git switch -c feat/phase2-live-flow-test`. `docs/Claude outputs/phase2/live-flow-test/`의 `spec.md`·`plan.md`를 `docs/superpowers/specs/2026-11-27-live-flow-test-design.md`·`docs/superpowers/plans/2026-11-27-live-flow-test-plan.md`로 그대로 복사(SHA-256은 지시 블록 값과 대조) → 커밋 `docs(docs): 실제 흐름 테스트 설계·계획 추가`

### Task 1: 순수 함수 (`tests/e2e/live_mail.py`)

**Files:**
- Create: `tests/e2e/live_mail.py`
- Test: `tests/e2e/test_live_mail.py`(기본 실행에 들어감, 실제 연결 없음)

**Interfaces (Produces):**
- `make_address(role: str, domain: str) -> str` — `e2e-<role>-<secrets.token_hex(4)>@<domain 소문자>`(전부 소문자)
- `extract_code(text: str | None) -> str | None` — `<style>`·`<script>` 덩어리와 모든 태그를 빈칸으로, `http(s)://…` 링크를 지운 뒤, 앞뒤가 영문·숫자·밑줄·`#`이 아닌(`[A-Za-z0-9_#]` 기준, 한글은 붙어 있어도 됨) 6~10자리 숫자(`[0-9]`) 중 첫 번째
- `parse_time(value: str) -> datetime` — Resend `created_at`(ISO, `Z`)을 시간대 있는 datetime으로
- `pick_mail(items: list[dict], address: str, since: datetime) -> str | None` — `to` 배열에 `address`가 있고(대소문자 무시) `created_at >= since`인 것 중 가장 늦게 온 메일의 `id`
- `scrub(text: str, secrets: list[str | None]) -> str` — 비어 있지 않은 각 비밀 글자를(대소문자 무시) `<가림>`으로

- [ ] **Step 1: 실패하는 테스트 쓰기**

```python
import re
from datetime import datetime, timezone

from tests.e2e.live_mail import extract_code, make_address, parse_time, pick_mail, scrub

SINCE = datetime(2026, 11, 27, 7, 0, 0, tzinfo=timezone.utc)


def test_make_address_is_new_lowercase_each_time():
    a1, a2 = make_address("a", "Fake.Test"), make_address("a", "Fake.Test")
    assert re.fullmatch(r"e2e-a-[0-9a-f]{8}@fake\.test", a1)
    assert a1 != a2


def test_extract_code_takes_six_to_ten_digits_only():
    assert extract_code("2026년 11월 펴봄 로그인 코드: 482913 (1시간 안에 입력)") == "482913"
    assert extract_code("코드 12345678") == "12345678"
    assert extract_code("코드는482913입니다") == "482913"
    assert extract_code("12345 은 너무 짧고 12345678901 은 너무 길어요") is None
    assert extract_code(None) is None


def test_extract_code_ignores_colors_links_and_attributes_in_html():
    html = ('<style>p{color:#333333}</style><p style="color:#111111">코드</p>'
            '<a href="https://fake.test/verify?token=9876543210abc">열기</a> https://fake.test/1234567 '
            '<strong>482913</strong>')
    assert extract_code(html) == "482913"


def test_parse_time_accepts_resend_iso_form():
    assert parse_time("2026-11-27T07:00:05.123Z") == datetime(2026, 11, 27, 7, 0, 5, 123000, tzinfo=timezone.utc)


def test_pick_mail_only_this_address_after_start():
    items = [
        {"id": "old", "to": ["e2e-a-aaaa@fake.test"], "created_at": "2026-11-27T06:59:59.000Z"},
        {"id": "other", "to": ["e2e-b-bbbb@fake.test"], "created_at": "2026-11-27T07:00:10.000Z"},
        {"id": "new1", "to": ["E2E-A-AAAA@fake.test"], "created_at": "2026-11-27T07:00:05.000Z"},
        {"id": "new2", "to": ["e2e-a-aaaa@fake.test"], "created_at": "2026-11-27T07:00:20.000Z"},
    ]
    assert pick_mail(items, "e2e-a-aaaa@fake.test", SINCE) == "new2"
    assert pick_mail(items, "e2e-c-cccc@fake.test", SINCE) is None


def test_scrub_hides_every_secret_case_insensitively():
    text = "to E2E-A-aaaa@fake.test code 482913 at fake.test"
    out = scrub(text, ["e2e-a-aaaa@fake.test", "482913", "fake.test", None, ""])
    assert "fake.test" not in out.lower() and "482913" not in out
    assert out.count("<가림>") >= 3
```

- [ ] **Step 2: 실패 확인** — Run: `pytest tests/e2e/test_live_mail.py -v` / Expected: 불러오기 실패(모듈 없음)
- [ ] **Step 3: 테스트 커밋** `test(request): 실제 흐름 테스트용 메일 고르기·코드 뽑기·가리기 테스트 추가 (실패 확인)`
- [ ] **Step 4: 위 Interfaces대로 구현**(`scrub`은 긴 비밀부터 바꿔 주소 안의 도메인이 먼저 바뀌어 주소가 남는 일이 없게)
- [ ] **Step 5: 통과 확인** — Run: `pytest tests/e2e/test_live_mail.py -v` / Expected: 6 PASS
- [ ] **Step 6: 구현 커밋** `feat(request): 실제 흐름 테스트용 메일 고르기·코드 뽑기·가리기 함수`

### Task 2: 실제 흐름 테스트 (`tests/e2e/test_request_flow_live.py`)

**Files:**
- Create: `tests/e2e/test_request_flow_live.py`(`pytestmark = pytest.mark.integration`)
- Modify: `pytest.ini`(`integration: 실제 외부 서비스(OpenAI·Neon·Supabase·Resend)에 연결하는 테스트 (기본 실행에서 제외)`), `.env.example`(새 이름 세 개, 값 없음, 한 줄 설명 주석: 실제 흐름 테스트 전용, 로컬에만, Vercel에 넣지 않음)

**Interfaces (Consumes):** Task 1의 다섯 함수, `ingest.__main__.load_env`(값 출력 없음). 화면 조작은 `tests/web/test_ui_request.py`의 `go_model_screen`·`login_sheet`·`drawer_row`와 같은 방법(역할·이름으로 찾기)을 쓰되, 그 파일을 불러오지 않고 이 파일 안에 둔다(가짜 서버 설정이 딸려 오지 않게)

**구성(이 순서, 테스트 함수 하나 `test_live_request_flow_and_rls`):**

1. 설정: `load_env()` 뒤 `RESEND_RECEIVING_API_KEY`·`RESEND_RECEIVING_DOMAIN`·`SUPABASE_URL`·`SUPABASE_SERVICE_KEY` 중 하나라도 없으면 `pytest.skip`(이름만 말함). `logging.getLogger("httpx").setLevel(logging.WARNING)`. 대상 = `E2E_BASE_URL` 또는 `https://pyeobom.help`(끝 `/` 없앰). 받기 주소 A·B = `make_address("a"|"b", 도메인)`. `since` = 지금(UTC) − 2분. 비밀 목록 = [주소 A, 주소 B, 도메인, 받기 키, 서비스 키, 우회 값] + 읽은 코드(읽을 때마다 더함)
2. 브라우저: 기존 `tests/web/conftest.py`처럼 `sync_playwright()`로 chromium. `new_context(viewport=390×844, record_video_dir=<저장소>/docs/Claude outputs/phase2/e2e/, record_video_size=390×844)`(폴더 없으면 만듦). trace 안 씀. `VERCEL_AUTOMATION_BYPASS_SECRET`이 있으면 `context.route(f"{대상}/**", …)`에서 그 요청에만 `x-vercel-protection-bypass`·`x-vercel-set-bypass-cookie: true`를 더해 `continue_`
3. 가리기: `context.add_init_script`로 모든 문서에 아래 스타일을 넣는다(`document.readyState`가 loading이면 DOMContentLoaded에, 아니면 바로, `document.head || document.documentElement`에 붙임)

```css
#login-email, #login-code, #login-sent-email, #request-email, #drawer-email, #switch-current-email {
  color: transparent !important; -webkit-text-fill-color: transparent !important;
  text-shadow: none !important; caret-color: transparent !important;
}
```

4. 코드 기다리기 `wait_code(address)`: httpx로 `GET https://api.resend.com/emails/receiving?limit=100`(Authorization: Bearer 받기 키)를 2초마다, 최대 90초. 응답 `data`에 `pick_mail(…, address, since)`가 id를 주면 `GET https://api.resend.com/emails/receiving/{id}`의 `text`로 `extract_code`, 없으면 `html`로. 코드를 비밀 목록에 더해 돌려준다. 90초가 지나면 "코드 메일이 90초 안에 오지 않음(A|B)", 메일은 왔는데 코드가 없으면 "메일에서 코드를 찾지 못함(A|B)"로 실패(본문·주소 없이). 응답이 200이 아니면 상태 숫자만
5. A: `page.goto(대상)` → [시작하기] → [건조기](exact) → [내 모델이 없어요] → 로그인 시트(`dialog` 이름 "로그인")의 "이메일" 칸에 A 주소 → [코드 보내기] → `wait_code(A)` → "인증 코드" 칸 → [확인] → 시트 닫힘 → 제목 `내 모델 요청하기` → "브랜드" `가짜브랜드`, "모델명" `E2E-<UTC %m%d%H%M%S>` → [요청하기] → `#request-done`에 완료 문구
6. 방어 ①: 같은 화면에서 같은 브랜드·모델명을 다시 입력 → [요청하기] → `#request-error`에 `이미 요청하셨어요`
7. A의 "내 요청": `page.goto(대상)` → `#landing-requests`가 보이고 `내 요청 1건` → 누름 → `#requests-list` 안 `.request-item`이 1개, 그 줄에 `가짜브랜드 E2E-…`와 `대기`
8. 로그아웃·B 로그인: [지난 대화] → `#drawer .drawer-account`의 [로그아웃] → 같은 줄 [로그인] 보임 → 그 [로그인] → 로그인 시트 "이메일"에 B 주소 → [코드 보내기] → `wait_code(B)`로 진짜 코드를 읽어 둔 뒤, 마지막 자리를 `(n+1)%10`으로 바꾼 코드를 먼저 넣고 [확인] → `#login-code-error`에 `코드가 맞지 않아요. 다시 확인해 주세요`(방어 ②) → 칸을 비우고 진짜 코드 → [확인] → 시트 닫힘
9. B: `page.expect_response`로 `/rest/v1/model_requests` 응답을 기다리며 `page.goto(대상)` → `#landing-requests` 숨김 → `page.goto(f"{대상}/#requests")` → `#requests-empty`에 `아직 요청이 없어요`, `.request-item` 0개
10. 감싸기·정리: 5~9를 `try`로 감싸 실패하면 `(단계 이름, 예외 종류, scrub(예외 문구 앞 500자))`를 남긴다. `finally`에서 ① `context.close()`·`browser.close()`로 영상 저장 → 파일 이름을 `live-flow-<한국 시각 %Y%m%d-%H%M>.webm`로 ② 관리 API `GET {SUPABASE_URL}/auth/v1/admin/users?page=1&per_page=1000`(헤더는 `apikey`에 서비스 키만: 새 비밀 키는 JWT가 아니라 `Authorization`에 넣지 않음, `test_rls_live.py`와 같음) 응답 `users`에서 이메일이 두 주소와 같은(대소문자 무시) 사용자를 찾아 `DELETE /auth/v1/admin/users/{id}` → 찾은 수·지운 수만 센다. 마지막에: 흐름 실패가 있으면 `pytest.fail("<단계> 단계 실패: <종류> <가린 문구> / 정리 지움 n/m", pytrace=False)`, 흐름은 성공인데 정리 실패(지운 수 < 찾은 수, 또는 찾은 수 ≠ 2)면 `pytest.fail("정리: 지움 n/m", pytrace=False)`

- [ ] **Step 1: 테스트 파일 쓰기**(위 구성 그대로) + `pytest.ini`·`.env.example` 고치기
- [ ] **Step 2: 기본 실행에 안 들어가는지 확인** — Run: `pytest -m "not integration" -q` / Expected: 실패 0, 새 integration 테스트는 deselected
- [ ] **Step 3: 커밋** `test(request): 실제 메일 코드 로그인·요청·RLS 흐름 테스트 추가`
- [ ] **Step 4: 설정 확인(값 출력 없이)** — `python -c "from ingest.__main__ import load_env; import os; load_env(); print({n: bool(os.environ.get(n)) for n in ['RESEND_RECEIVING_API_KEY','RESEND_RECEIVING_DOMAIN','SUPABASE_URL','SUPABASE_SERVICE_KEY']})"` / 하나라도 False면 실행하지 않고 멈춰 보고(U10 대기)
- [ ] **Step 5: 한 번 실행** — Run: `pytest tests/e2e/test_request_flow_live.py -m integration -v` / Expected: 1 passed. 실패하면 다시 돌리지 말고 실패 줄(가린 그대로)과 정리 결과(`n/m`)를 보고하고 멈춤

### Task 3: 확인·기록·PR

- [ ] **Step 1:** `pytest -v -m "not integration"` 실패 0, `node --test "tests/web/js/*.test.mjs"` 실패 0(앱 코드 안 바꿈 확인)
- [ ] **Step 2:** 영상 파일 이름·길이(초)·크기를 보고(채팅 Claude가 장면을 뽑아 주소가 안 보이는지 확인할 때까지 시연 영상에 쓰지 않음)
- [ ] **Step 3:** 개발일지 `docs/개발일지/2026-11-27.md` 끝에 절 하나(원문은 지시 블록, `<…>` 자리만 실제 값으로)
- [ ] **Step 4:** 커밋 → push 전 점검(CLAUDE.md 기준 + 받기 도메인 글자가 더한 줄·PR 본문에 0개인지 셈, 값은 출력하지 않고 개수만) → push → PR(양식) → 보고하고 멈춤(병합은 채팅 Claude 대조·영상 확인 뒤)
