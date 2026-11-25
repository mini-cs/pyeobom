"""요청 표 model_requests의 RLS·제약을 실제 Supabase에 대고 확인한다(계획 Task 4, OpenAI 비용 0).

- 시험 사용자는 관리 API(비밀 키)로 만든다: POST /auth/v1/admin/generate_link(type magiclink)가 메일을 보내지 않고
  hashed_token을 돌려주고, POST /auth/v1/verify(token_hash, type email)가 그것을 세션으로 바꾼다(supabase/auth README·verify.go).
- 새 키(sb_publishable_·sb_secret_)는 JWT가 아니므로 apikey 헤더에만 넣고, Authorization에는 사용자 토큰만 넣는다
  (Supabase 문서 "API keys > Known limitations").
- 시험 이메일은 누가 봐도 가짜인 example.com 주소. 끝나면 이 테스트가 만든 사용자만 지운다(요청은 on delete cascade로 함께 지워짐).
"""
import json
import os
import uuid
from pathlib import Path

import httpx
import pytest

from ingest.__main__ import load_env

pytestmark = pytest.mark.integration

CASES = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "model_key_cases.json").read_text(encoding="utf-8"))
TABLE = "/rest/v1/model_requests"


@pytest.fixture(scope="module")
def env():
    load_env()  # 로컬 .env를 읽는다(값은 출력하지 않음)
    names = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY")
    if not all(os.environ.get(n) for n in names):
        pytest.skip("SUPABASE_URL·SUPABASE_ANON_KEY·SUPABASE_SERVICE_KEY가 없으면 RLS 테스트를 건너뛴다")
    return {n: os.environ[n] for n in names}


@pytest.fixture(scope="module")
def new_user(env):
    """가짜 시험 사용자를 만들고 그 사용자의 공개 키 + 토큰 클라이언트를 돌려준다. 끝나면 만든 사용자만 지운다."""
    admin = httpx.Client(base_url=env["SUPABASE_URL"], headers={"apikey": env["SUPABASE_SERVICE_KEY"]}, timeout=30)
    created: list[str] = []
    clients: list[httpx.Client] = []

    def make() -> tuple[str, httpx.Client]:
        email = f"fake-rls-{uuid.uuid4().hex[:12]}@example.com"
        r = admin.post("/auth/v1/admin/generate_link", json={"type": "magiclink", "email": email})
        assert r.status_code == 200, f"generate_link {r.status_code}"
        link = r.json()
        user_id = link.get("id") or link.get("user", {}).get("id")
        assert user_id, "generate_link 응답에 사용자 id가 없음"
        created.append(user_id)  # 세션 받기가 실패해도 지울 수 있게 먼저 적는다
        r = httpx.post(f"{env['SUPABASE_URL']}/auth/v1/verify", headers={"apikey": env["SUPABASE_ANON_KEY"]},
                       json={"type": "email", "token_hash": link["hashed_token"]}, timeout=30)
        assert r.status_code == 200, f"verify {r.status_code}"
        token = r.json()["access_token"]
        client = httpx.Client(base_url=env["SUPABASE_URL"], timeout=30, headers={
            "apikey": env["SUPABASE_ANON_KEY"], "Authorization": f"Bearer {token}", "Prefer": "return=representation"})
        clients.append(client)
        return user_id, client

    yield make
    for c in clients:
        c.close()
    failed = [uid for uid in created if admin.delete(f"/auth/v1/admin/users/{uid}").status_code not in (200, 204)]
    admin.close()
    assert not failed, f"시험 사용자 {len(failed)}명을 지우지 못함(대시보드에서 fake-rls-로 찾아 지운다)"


def request_body(model_text: str, **extra) -> dict:
    return {"category": "washer", "brand": "테스트", "model_text": model_text} | extra


def insert_ok(client: httpx.Client, model_text: str) -> dict:
    r = client.post(TABLE, json=request_body(model_text))
    assert r.status_code == 201, f"요청 넣기 {r.status_code}: {r.text[:200]}"
    return r.json()[0]


def own_rows(client: httpx.Client) -> list[dict]:
    r = client.get(TABLE, params={"select": "*"})
    assert r.status_code == 200, f"요청 읽기 {r.status_code}: {r.text[:200]}"
    return r.json()


@pytest.fixture(scope="module")
def user_a(new_user):
    return new_user()


@pytest.fixture(scope="module")
def user_b(new_user):
    return new_user()


def test_user_sees_only_own_requests(user_a, user_b):
    a_id, a = user_a
    b_id, b = user_b
    mine = insert_ok(a, "RLS-A-1")
    theirs = insert_ok(b, "RLS-B-1")
    rows = own_rows(a)
    assert {r["user_id"] for r in rows} == {a_id}
    assert mine["id"] in {r["id"] for r in rows}
    assert theirs["id"] not in {r["id"] for r in rows}


def test_user_cannot_update_or_delete(user_a):
    _, a = user_a
    row = insert_ok(a, "RLS-A-2")
    a.patch(TABLE, params={"id": f"eq.{row['id']}"}, json={"status": "추가됨", "model_id": "fake-model"})
    a.delete(TABLE, params={"id": f"eq.{row['id']}"})
    # 정책이 없어서든 권한이 없어서든 "거부됨"만 확인한다(덧붙임 A-1): 행이 그대로 남아 있어야 한다
    after = [r for r in own_rows(a) if r["id"] == row["id"]]
    assert len(after) == 1
    assert after[0]["status"] == "대기" and after[0]["model_id"] is None


def test_insert_with_status_added_is_rejected(user_a):
    _, a = user_a
    insert_ok(a, "RLS-A-3")  # 같은 사용자의 정상 요청은 들어간다(표가 없어서 거부되는 것과 구별)
    r = a.post(TABLE, json=request_body("RLS-A-4", status="추가됨", model_id="fake-model"))
    assert r.status_code >= 400


def test_duplicate_model_key_is_rejected(user_b):
    _, b = user_b
    insert_ok(b, "RLS-DUP-9")
    r = b.post(TABLE, json=request_body("rls dup.9"))  # 정규화하면 같은 RLSDUP9
    assert r.status_code == 409 and r.json()["code"] == "23505"   # 화면 "이미 요청하셨어요"가 기대는 값(db.md)


def test_sixth_request_in_24h_is_rejected(new_user):
    _, c = new_user()
    for i in range(5):
        insert_ok(c, f"RLS-LIMIT-{i}")
    r = c.post(TABLE, json=request_body("RLS-LIMIT-5"))
    assert r.status_code == 400 and r.json()["code"] == "P0001"   # 하루 제한 트리거(db.md)


def test_model_key_matches_cases_live(new_user):
    # 하루 5개 제한이 있어 사례 5개마다 새 사용자로 넣는다(사례끼리 정규화 값은 모두 다름)
    keys = [c["key"] for c in CASES]
    assert len(set(keys)) == len(keys)
    got = {}
    for start in range(0, len(CASES), 5):
        _, client = new_user()
        for case in CASES[start:start + 5]:
            got[case["input"]] = insert_ok(client, case["input"])["model_key"]
    assert got == {c["input"]: c["key"] for c in CASES}



def test_insert_for_other_user_is_rejected(user_a, user_b):
    # 다른 사람 user_id로 넣기: user_id 열에는 넣기 권한이 없어 거절(42501, 로그인 상태 403)
    _, a = user_a
    b_id, b = user_b
    r = a.post(TABLE, json=request_body("RLS-OTHER-1", user_id=b_id))
    assert r.status_code == 403 and r.json()["code"] == "42501"
    assert "RLS-OTHER-1" not in {row["model_text"] for row in own_rows(b)}


def test_anon_cannot_read_requests(env):
    # 로그인 없이(공개 키만) 읽기: anon에는 권한이 없어 거절(42501, 로그인 전 401)
    r = httpx.get(f"{env['SUPABASE_URL']}{TABLE}", params={"select": "*"},
                  headers={"apikey": env["SUPABASE_ANON_KEY"]}, timeout=30)
    assert r.status_code == 401 and r.json()["code"] == "42501"
