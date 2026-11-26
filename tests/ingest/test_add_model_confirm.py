"""확인 질문 실행·판정지·합격 판정·체크리스트(계획 2차 Task 9). 실제 Neon·OpenAI는 부르지 않는다(가짜 Deps, 비용 0).
질문 처리는 /api/ask 라우트 함수를 그대로 거친다(2026-11-26 사용자 보충 2). 전 측정 파일의 내용은 쓰지 않는다."""
import csv
import hashlib
import json

import pytest

import app.ask.routes as ask_routes
from app.answer.check import GUIDE_WARNING
from app.ask.service import Deps
from app.core.config import Settings
from app.retrieval.search import Chunk
from ingest import add_model
from tests.ingest.db_rule import assert_no_ai_while_open

MODEL = "washer-test-x1"
SETTINGS = Settings(openai_api_key="", database_url="", openai_embed_model="text-embedding-3-small",
                    openai_chat_model="gpt-6-luna", embed_dim=1536)
CHUNKS = [Chunk(1, "manual-test-x1", "manual", "테스트 설명서", "https://example.com/m", 3, "세탁조 청소는 통세척 코스로 해요.", 0.1),
          Chunk(2, "guide-test-x1", "guide", "테스트 가이드", "https://example.com/g", None, "4E가 뜨면 급수를 확인해요.", 0.2)]
FOUND = json.dumps({"found": True, "answer": "통세척 코스로 청소해요.",
                    "citations": [{"chunk_id": 1, "quote": "통세척 코스"}, {"chunk_id": 2, "quote": "급수를 확인"}]})
NOT_FOUND = json.dumps({"found": False})
JUDGE_COLUMNS = ["qid", "질문", "답", "인용 쪽", "verdict", "borderline", "worse_verdict", "메모"]
# 가짜 확인 질문 10개(설명서 30쪽 기준 앞·중간·뒤 사용법 3·3·2개 + 에러 코드 2개). validate_confirm_set 문제 0개
ROWS = [("q1", "사용법", "통세척은 어떻게 하나요?", "2", "manual"), ("q2", "사용법", "문이 안 열려요", "5", "manual"),
        ("q3", "사용법", "세제는 어디에 넣나요?", "8", "manual"), ("q4", "사용법", "울 코스는 언제 쓰나요?", "12", "manual"),
        ("q5", "사용법", "헹굼만 할 수 있나요?", "15", "manual"), ("q6", "사용법", "예약은 어떻게 하나요?", "18", "manual"),
        ("q7", "사용법", "배수 필터 청소 방법", "22", "manual"), ("q8", "사용법", "수평은 어떻게 맞추나요?", "25", "manual"),
        ("q9", "에러 코드", "4E가 떠요", "26", "guide:guide-test-x1"), ("q10", "에러 코드", "5E가 떠요", "26", "guide:guide-test-x1")]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """가짜 Deps(검색은 열기·닫기, 임베딩·답변은 ai를 적음), 임시 장부·결과 폴더, 확인 질문 파일."""
    events, seen = [], {"embedded": [], "prompts": []}
    replies = {}

    def factory():
        def embed_query(q):
            events.append("ai")
            seen["embedded"].append(q)
            return [0.0]

        def search(model_id, vec, q, k):
            events.append("open")
            events.append("close")
            return CHUNKS

        def complete(messages):
            events.append("ai")
            text = json.dumps(messages, ensure_ascii=False)
            seen["prompts"].append(text)
            return next((r for key, r in replies.items() if key in text), FOUND)
        return Deps(embed_query=embed_query, search=search, complete=complete, supported_ids={MODEL},
                    official_url=lambda m: "https://example.com/support", brand=lambda m: "삼성")  # 4E·5E는 삼성 코드
    monkeypatch.setattr(ask_routes, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(add_model, "LEDGER", tmp_path / "ledger.csv")
    monkeypatch.setattr(add_model, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(add_model, "JUDGE_DIR", tmp_path / "judge")
    monkeypatch.setattr(add_model, "load_env", lambda: None)
    (tmp_path / "ledger.csv").write_text("date,item,estimate_usd,actual_usd,note\n2026-11-26,앞,0.5,,\n", encoding="utf-8")
    questions = tmp_path / "confirm.csv"
    with questions.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["qid", "kind", "question", "expected_pages", "source"])
        w.writerows(ROWS)
    sha = hashlib.sha256(questions.read_bytes()).hexdigest()
    return {"events": events, "seen": seen, "replies": replies, "factory": factory, "questions": questions,
            "sha": sha, "tmp": tmp_path}


def _run(env, **kw):
    args = dict(expect_sha256=env["sha"], label="after", estimate_usd=0.01, page_count=30, deps_factory=env["factory"])
    return add_model.run_confirm(MODEL, str(env["questions"]), **{**args, **kw})


def _read(path, encoding="utf-8-sig"):  # 결과 CSV는 evaluation/results 관례대로 BOM 있는 UTF-8
    with open(path, encoding=encoding, newline="") as f:
        return list(csv.DictReader(f))


def test_run_confirm_follows_db_rule(env):
    _run(env)
    assert env["events"].count("open") == 10 and env["events"].count("ai") == 20  # 질문마다 임베딩·검색·답변
    assert_no_ai_while_open(env["events"])


def test_confirm_refuses_hash_mismatch(env):
    with pytest.raises(ValueError, match="해시"):
        _run(env, expect_sha256="0" * 64)
    assert env["events"] == [] and not (env["tmp"] / "results").exists() and not (env["tmp"] / "judge").exists()


def test_confirm_refuses_over_budget(env):
    with pytest.raises(ValueError, match="장부"):
        _run(env, estimate_usd=0.51)  # 0.5 + 0.51 > 1달러
    assert env["events"] == [] and not (env["tmp"] / "results").exists()


def test_confirm_writes_results_without_calling_network(env):
    env["replies"]["5E가 떠요"] = NOT_FOUND
    path = _run(env)
    assert path == env["tmp"] / "results" / f"phase2-{MODEL}-after.csv"
    results = _read(path)
    assert [r["qid"] for r in results] == [r[0] for r in ROWS]
    assert list(results[0]) == ["qid", "질문", "답", "인용 쪽", "found", "error_code", "ms"]
    # 판정지: 전 측정과 같은 8열, BOM 있는 UTF-8, 줄 끝 LF, 판정 칸은 비움(사람이 채움)
    judge_path = env["tmp"] / "judge" / f"{MODEL}-after-judge.csv"
    raw = judge_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw
    judge = _read(judge_path, "utf-8-sig")
    assert list(judge[0]) == JUDGE_COLUMNS and len(judge) == 10
    assert all(r["verdict"] == r["borderline"] == r["worse_verdict"] == r["메모"] == "" for r in judge)
    # 화면 규칙: 답 + (안내) 참고 경고, 인용 쪽 = 접힌 줄 글자 / 찾지 못함이면 (링크) 줄과 "없음"
    q1, q10 = judge[0], judge[9]
    assert q1["답"] == f"통세척 코스로 청소해요.\n(안내) 참고 {GUIDE_WARNING}"
    assert q1["인용 쪽"] == "근거 보기 · 사용설명서 3쪽 · 공식 해결 가이드 1개"
    assert q10["답"].endswith("\n(링크) 공식 고객센터에서 찾아보기") and q10["인용 쪽"] == "없음"
    assert results[9]["found"] == "False" and results[0]["found"] == "True"
    # 판정 입력 파일(git 밖): 질문별 인용문과 쪽(전 측정의 펼친 캡처 대신)
    md = (env["tmp"] / "judge" / f"{MODEL}-after-judge-input.md").read_text(encoding="utf-8")
    assert "## q1" in md and "사용설명서 3쪽" in md and "> 통세척 코스" in md and "공식 해결 가이드: 테스트 가이드" in md
    # 같은 이름으로 다시 돌리면 덮어쓰지 않는다(측정 결과 보호)
    with pytest.raises(ValueError, match="이미"):
        _run(env)


def test_confirm_goes_through_ask_route_processing(env):
    """새 대화로 /api/ask를 부를 때와 같은 처리: 개인정보 가리기(임베딩·답변 AI에는 가린 질문만), 오류는 error_code로."""
    rows = list(ROWS)
    rows[0] = ("q1", "사용법", "010-1234-5678로 연락 주세요. 통세척은 어떻게 하나요?", "2", "manual")
    rows[1] = ("q2", "사용법", "가" * 501, "5", "manual")  # 질문 길이 상한(500) 넘음 → 라우트가 오류 응답으로
    with env["questions"].open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["qid", "kind", "question", "expected_pages", "source"])
        w.writerows(rows)
    path = _run(env, expect_sha256=hashlib.sha256(env["questions"].read_bytes()).hexdigest())
    results = _read(path)
    assert all("010-1234-5678" not in t for t in env["seen"]["embedded"] + env["seen"]["prompts"])
    assert "010-1234-5678" not in results[0]["질문"]
    assert results[1]["error_code"] and results[1]["found"] == "" and results[1]["인용 쪽"] == "없음"
    assert len(env["seen"]["embedded"]) == 9  # 오류 질문은 AI를 부르지 않음


def test_verdict_prints_pass_and_032_note(tmp_path, capsys):
    judge = tmp_path / "judge.csv"
    rows = [[f"q{i}", "질문", "답", "없음", "정답", "no", "", ""] for i in range(1, 9)]
    rows += [["q9", "질문", "답", "없음", "찾지 못함", "no", "", "다른 코드 절차(설명서와 가이드)"],
             ["q10", "질문", "답", "없음", "오답", "no", "", ""]]
    with judge.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(JUDGE_COLUMNS)
        w.writerows(rows)
    add_model.main(["verdict", "--judge", str(judge)])
    out = capsys.readouterr().out
    assert "합격" in out and "정답 8" in out and "환각 0" in out
    assert "결정기록 032 근거로 기록" in out
    rows[0][4] = "환각"
    with judge.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(JUDGE_COLUMNS)
        w.writerows(rows)
    add_model.main(["verdict", "--judge", str(judge)])
    assert "미달" in capsys.readouterr().out


def test_checklist_order(capsys):
    add_model.main(["checklist", "--model-id", MODEL])
    out = capsys.readouterr().out
    steps = ["add_model draft", "add_model check", "add_model ingest", "add_model link-guide", "add_model confirm",
             "예시 질문 화면 확인", "사람 판정", "add_model verdict", "PR 병합", "운영 화면", "추가됨"]
    positions = [out.index(s) for s in steps]
    assert positions == sorted(positions), out
    assert MODEL in out and out.index("합격") < out.index("추가됨")
