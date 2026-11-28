# 2차 Task 11 ③ Supabase 깨우기 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vercel Cron이 하루 3번 `GET /api/wake`를 부르면 서버가 Supabase 요청 표를 1줄 읽어, 무료 프로젝트가 활동 부족으로 멈추지 않게 한다.

**Architecture:** `app/wake/`에 두 파일 — `ping.py`(Supabase REST 1줄 읽기, 실패는 `WakeError(이유)`)와 `routes.py`(`CRON_SECRET` 확인 뒤에만 ping을 스레드에서 부름). 알림 주소(`app/notify/`)와 같은 방식(비밀 값 비교 `hmac.compare_digest`, 의존성 주입으로 테스트에서 가짜 ping). `vercel.json`에 `crons` 3개.

**Tech Stack:** FastAPI, httpx, pytest(TestClient), Vercel Cron(Hobby).

**Spec:** `docs/superpowers/specs/2026-11-28-supabase-wake-design.md`

**브랜치:** `feat/phase2-supabase-wake`(최신 `main` bdf532a 이후), PR 하나. **병합은 사용자가 Vercel에 `CRON_SECRET`을 넣은 뒤**(배포가 만들어질 때의 값을 씀).

## Global Constraints

- 질문·답변(`/api/ask`)·알림(`/api/notify`)·화면(`public/`) 동작은 바꾸지 않는다
- `CRON_SECRET`·Supabase 키·Supabase 주소·응답 본문을 응답·로그·커밋·PR·보고에 넣지 않는다
- `CRON_SECRET`이 비면 모든 요청 401. 401일 때 Supabase를 부르지 않는다
- Supabase 요청: `GET {SUPABASE_URL}/rest/v1/model_requests`, params `{"select": "id", "limit": "1"}`, headers `{"apikey": <SUPABASE_SERVICE_KEY>}`(Authorization 머리글 없음), timeout 10초. 읽기만, 결과는 버림
- 응답: 성공 200 `{"ok": true}` / 인증 실패 401 `{"error_code": "UNAUTHORIZED", "message": "인증이 필요해요"}` / ping 실패 502 `{"error_code": "WAKE_FAILED", "message": "깨우지 못했어요", "reason": "<이유>"}`. 이유는 `not_configured` · `rest_<상태숫자>` · `<httpx 예외 클래스 이름>`만
- 로그: 성공 `wake: result=ok`, 실패 `wake 실패: reason=<이유>`, 인증 실패 `wake: result=unauthorized`(머리글 값 없음)
- Cron 시각(UTC): `"23 1 * * *"`, `"23 9 * * *"`, `"23 17 * * *"` — 셋 다 `"path": "/api/wake"`. Hobby는 하루 1번·한 시간 안 어느 때
- 환경 변수 이름 `CRON_SECRET`(설정 칸 `cron_secret`, 기본 `""`, 읽을 때 앞뒤 빈칸·줄바꿈을 뗌 `.strip()`). `.env.example`에는 이름만
- 테스트 값은 누가 봐도 가짜(`https://fake-project.supabase.co`, `sb_secret_fake-server-key`, `fake-cron-secret-0123456789abcdef`). 메일 주소를 쓰면 `example.com`만
- 테스트 먼저 커밋 → 구현 커밋, 커밋 형식·push 전 점검은 CLAUDE.md

## Review Focus

1. Vercel이 보내는 머리글과 글자 하나라도 다르면(접두어 `Bearer ` 빠짐, 소문자 `bearer`, 빈칸 두 개, 값 뒤에 글자 더함) → 401이고 Supabase는 안 부른다. Task 1 `test_rejects_missing_or_wrong_authorization`. 반대로 사용자가 Vercel에 값을 붙여 넣을 때 앞뒤 빈칸·줄바꿈이 섞이면(Vercel 문서가 경고함) 머리글 쪽은 HTTP가 앞뒤 빈칸을 떼므로 늘 401이 됨 → 설정 값은 앞뒤 빈칸을 떼고 비교. Task 1 `test_secret_with_surrounding_spaces_in_env_still_matches`
2. `CRON_SECRET`을 Vercel에 넣지 않은 채 배포됐을 때 → 빈 `Bearer `도 401(누구나 Supabase를 부를 수 없음). Task 1 `test_rejects_when_cron_secret_not_configured`
3. Supabase가 멈췄거나 느릴 때(5xx·시간 초과) → 502와 이유 코드만, 키·주소가 응답·로그에 없음. Task 1 `test_ping_failure_returns_502_reason_only`·`test_logs_never_contain_secrets`
4. 누군가 POST로 부르거나 주소 끝에 `/`를 붙일 때 → POST는 405, Cron 경로는 `/api/wake` 그대로(이동 응답이 나오면 Cron은 따라가지 않음). Task 1 `test_post_not_allowed`·Task 2 경로 확인
5. Cron 식이 하루 두 번 이상 돌게 잘못 적히면 Hobby 배포가 실패함 → 세 식 모두 분·시가 숫자 하나씩이고 나머지는 `*`. Task 2 `test_vercel_json_has_three_daily_wake_crons`

---

### Task 0: 설계·계획 커밋

- [ ] **Step 1:** `git switch main && git pull && git switch -c feat/phase2-supabase-wake`. `docs/Claude outputs/phase2/supabase-wake/`의 `spec.md`·`plan.md`를 `docs/superpowers/specs/2026-11-28-supabase-wake-design.md`·`docs/superpowers/plans/2026-11-28-supabase-wake-plan.md`로 그대로 복사(SHA-256은 지시 블록 값과 대조) → 커밋 `docs(docs): Supabase 깨우기 설계·계획 추가`

### Task 1: `/api/wake` 주소

**Files:**
- Create: `app/wake/__init__.py`(빈 파일), `app/wake/ping.py`, `app/wake/routes.py`
- Modify: `app/core/config.py`(설정 칸 `cron_secret`, `env("CRON_SECRET", "")`), `app/web.py`(`app.include_router(wake_router)`)
- Test: `tests/wake/test_wake.py`

**Interfaces (Produces):**
- `app.wake.ping.WakeError(Exception)` — `str(e)`가 이유 코드
- `app.wake.ping.ping_supabase(*, get=httpx.get) -> None` — 설정이 비면 `WakeError("not_configured")`(get 안 부름), httpx 예외면 `WakeError(<예외 클래스 이름>)`, 200이 아니면 `WakeError(f"rest_{status}")`
- `app.wake.routes.router`(`GET /api/wake`), `app.wake.routes.get_wake_ping() -> Callable[[], None]`(기본 `ping_supabase`, 테스트에서 덮어씀)

- [ ] **Step 1: 실패하는 테스트 쓰기** — `tests/wake/test_wake.py`

```python
"""Supabase 깨우기 /api/wake(2차 Task 11 ③). Supabase는 가짜 get·가짜 ping으로 바꿔 네트워크 0. 값은 모두 가짜."""
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.wake.ping import WakeError, ping_supabase
from app.wake.routes import get_wake_ping
from app.web import create_app

URL = "https://fake-project.supabase.co"
KEY = "sb_secret_fake-server-key"
SECRET = "fake-cron-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch):
    for k, v in {"SUPABASE_URL": URL, "SUPABASE_SERVICE_KEY": KEY, "CRON_SECRET": SECRET}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def wake():
    calls, state = [], {"fail": None}

    def ping():
        calls.append(1)
        if state["fail"]:
            raise state["fail"]

    app = create_app()
    app.dependency_overrides[get_wake_ping] = lambda: ping
    return TestClient(app), calls, state


def call(client, auth=f"Bearer {SECRET}"):
    return client.get("/api/wake", headers={} if auth is None else {"Authorization": auth})


def test_rejects_missing_or_wrong_authorization(wake):
    client, calls, _ = wake
    for auth in (None, "", "Bearer wrong", SECRET, f"bearer {SECRET}", f"Bearer  {SECRET}", f"Bearer {SECRET}x"):
        res = call(client, auth)
        assert res.status_code == 401
        assert res.json()["error_code"] == "UNAUTHORIZED"
    assert calls == []


def test_rejects_when_cron_secret_not_configured(wake, monkeypatch):
    client, calls, _ = wake
    monkeypatch.setenv("CRON_SECRET", "")
    get_settings.cache_clear()
    assert call(client, "Bearer ").status_code == 401
    assert call(client).status_code == 401
    assert calls == []


def test_pings_supabase_and_returns_ok(wake):
    client, calls, _ = wake
    res = call(client)
    assert res.status_code == 200 and res.json() == {"ok": True}
    assert calls == [1]


def test_ping_failure_returns_502_reason_only(wake):
    client, calls, state = wake
    state["fail"] = WakeError("rest_503")
    res = call(client)
    assert res.status_code == 502
    assert res.json() == {"error_code": "WAKE_FAILED", "message": "깨우지 못했어요", "reason": "rest_503"}
    assert all(s not in res.text for s in (SECRET, KEY, URL))


def test_logs_never_contain_secrets(wake, caplog):
    client, _, state = wake
    caplog.set_level(logging.INFO)
    call(client)
    call(client, "Bearer wrong")
    state["fail"] = WakeError("ConnectTimeout")
    call(client)
    assert "wake: result=ok" in caplog.text and "wake 실패: reason=ConnectTimeout" in caplog.text
    assert "wake: result=unauthorized" in caplog.text
    assert all(s not in caplog.text for s in (SECRET, KEY, URL, "Bearer"))


def test_secret_with_surrounding_spaces_in_env_still_matches(wake, monkeypatch):
    client, calls, _ = wake
    monkeypatch.setenv("CRON_SECRET", f" {SECRET}\n")
    get_settings.cache_clear()
    assert call(client).status_code == 200
    assert calls == [1]


def test_post_not_allowed(wake):
    client, calls, _ = wake
    assert client.post("/api/wake", headers={"Authorization": f"Bearer {SECRET}"}).status_code == 405
    assert calls == []


def response(status, data):
    return httpx.Response(status, json=data, request=httpx.Request("GET", f"{URL}/rest/v1/model_requests"))


def test_ping_reads_one_row_with_secret_key_on_apikey_only():
    seen = {}

    def get(url, **kwargs):
        seen.update(url=url, **kwargs)
        return response(200, [{"id": 1}])

    assert ping_supabase(get=get) is None
    assert seen["url"] == f"{URL}/rest/v1/model_requests"
    assert seen["params"] == {"select": "id", "limit": "1"}
    assert seen["headers"] == {"apikey": KEY}
    assert seen["timeout"] == 10


@pytest.mark.parametrize("status", [401, 500, 503])
def test_ping_raises_rest_status(status):
    with pytest.raises(WakeError, match=f"^rest_{status}$"):
        ping_supabase(get=lambda url, **kw: response(status, {"message": "fake"}))


def test_ping_raises_exception_name_on_http_error():
    def get(url, **kwargs):
        raise httpx.ConnectTimeout("fake timeout", request=httpx.Request("GET", url))

    with pytest.raises(WakeError, match="^ConnectTimeout$"):
        ping_supabase(get=get)


def test_ping_not_configured_does_not_call(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")
    get_settings.cache_clear()
    called = []
    with pytest.raises(WakeError, match="^not_configured$"):
        ping_supabase(get=lambda url, **kw: called.append(1))
    assert called == []
```

- [ ] **Step 2: 실패 확인** — Run: `pytest tests/wake/test_wake.py -v` / Expected: 불러오기 실패(`app.wake` 없음)
- [ ] **Step 3: 테스트 커밋** `test(request): Supabase 깨우기 주소 테스트 추가 (실패 확인)`
- [ ] **Step 4: 구현** — 위 Interfaces와 Global Constraints대로. `routes.py`의 인증은 `hmac.compare_digest(given.encode(), f"Bearer {secret}".encode())`이고 `secret`이 비면 거절(알림 주소 `_authorized`와 같은 모양). ping은 `run_in_threadpool`로 부름. `config.py` 설정 칸에 한 줄 설명(운영 Vercel Production에만, Vercel Cron이 Authorization 머리글로 보냄)
- [ ] **Step 5: 통과 확인** — Run: `pytest tests/wake/test_wake.py -v` / Expected: 13 PASS(테스트 함수 11개, parametrize 3건 포함 13건)
- [ ] **Step 6: 구현 커밋** `feat(request): Supabase 깨우기 주소 /api/wake`

### Task 2: Cron 등록과 기록

**Files:**
- Modify: `vercel.json`(`"crons"` 3개 추가, 기존 `framework`·`regions` 그대로), `.env.example`(`CRON_SECRET=` + 주석 한 줄: Supabase 깨우기 /api/wake 인증, 운영 Vercel Production에만, 로컬은 비워 둠), `CLAUDE.md` 폴더 구조(`app/wake/         Supabase 깨우기 (/api/wake, Vercel Cron 하루 3번)` 한 줄), `db.md`(새 절 "Supabase 깨우기 (Task 11 ③)": 왜·동작·Cron 시각·`CRON_SECRET`·한계 — 설계 "동작"·"한계" 요약)
- Test: `tests/web/test_web_entry.py`

- [ ] **Step 1: 실패하는 테스트 쓰기** — `tests/web/test_web_entry.py`에 추가

```python
def test_vercel_json_has_three_daily_wake_crons():
    # Hobby는 작업마다 하루 1번(두 번 이상 도는 식은 배포 실패). 2차 Task 11 ③ Supabase 깨우기
    import json
    from pathlib import Path
    config = json.loads((Path(__file__).resolve().parents[2] / "vercel.json").read_text(encoding="utf-8"))
    crons = config["crons"]
    assert [c["path"] for c in crons] == ["/api/wake"] * 3
    hours = []
    for c in crons:
        minute, hour, dom, month, dow = c["schedule"].split()
        assert minute.isdigit() and 1 <= int(minute) <= 59
        assert hour.isdigit() and (dom, month, dow) == ("*", "*", "*")
        hours.append(int(hour))
    assert hours == [1, 9, 17]
```

- [ ] **Step 2: 실패 확인** — Run: `pytest tests/web/test_web_entry.py -v` / Expected: 새 테스트 FAIL(KeyError `crons`), 기존 2개 PASS
- [ ] **Step 3: 테스트 커밋** `test(web): Vercel Cron 깨우기 3개 테스트 추가 (실패 확인)`
- [ ] **Step 4:** `vercel.json`에 Global Constraints의 세 식 추가, `.env.example`·`CLAUDE.md`·`db.md` 고치기
- [ ] **Step 5: 통과 확인** — Run: `pytest tests/web/test_web_entry.py -v` / Expected: 3 PASS
- [ ] **Step 6: 구현 커밋** `feat(web): Vercel Cron으로 하루 3번 Supabase 깨우기`

### Task 3: 확인·기록·PR

- [ ] **Step 1:** `pytest -v -m "not integration"` 실패 0, `node --test "tests/web/js/*.test.mjs"` 실패 0(화면 안 바뀜 확인)
- [ ] **Step 2:** 보안 점검 — 프로젝트 스킬 security-audit를 바뀐 파일만 보는 guidance 모드로(CLAUDE.md "스킬"). 확인된 취약점이 있으면 고치기 전에 멈춰 보고
- [ ] **Step 3:** 개발일지 `docs/개발일지/2026-11-28.md`(새 파일)에 절 하나(원문은 지시 블록, `<…>` 자리만 실제 값으로)
- [ ] **Step 4:** 커밋 → push 전 점검(CLAUDE.md 기준) → push → PR(양식, 본문에 "병합 전 사용자가 Vercel Production에 CRON_SECRET을 넣어야 함" 한 줄) → 보고하고 멈춤

### Task 4: 병합 뒤 확인 (사용자가 CRON_SECRET을 넣고 병합 지시를 준 뒤)

- [ ] **Step 1:** 운영 배포 Ready 뒤 `curl -s -o /dev/null -w "%{http_code}" https://pyeobom.help/api/wake` → `401`, `-H "Authorization: Bearer wrong"`도 `401`(값을 출력하지 않음)
- [ ] **Step 2:** Vercel 대시보드 프로젝트 → Schedules → Cron Jobs 탭에 `/api/wake` 3개가 보이는지(Vercel CLI로 확인할 수 있으면 CLI로, 아니면 사용자에게 화면 확인 부탁). 첫 실행 기록(정한 시각의 한 시간 안)이 200인지
- [ ] **Step 3:** 채팅 Claude가 Supabase 로그에서 그 시각의 `model_requests` 읽기를 확인(읽기만)
