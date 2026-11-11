import urllib.request

from measure.a11y import STATES, fake_reply, serve_public, summarize, summarize_violations


def test_summarize_violations_counts_by_impact():
    results = {"violations": [
        {"id": "color-contrast", "impact": "serious", "nodes": [{}]},
        {"id": "region", "impact": "minor", "nodes": [{}]},
    ]}
    summary = summarize_violations(results)
    assert summary["total"] == 2
    assert summary["by_impact"] == {"critical": 0, "serious": 1, "moderate": 0, "minor": 1}
    assert summary["rules"] == ["color-contrast", "region"]


def test_summarize_violations_empty():
    summary = summarize_violations({"violations": []})
    assert summary["total"] == 0
    assert summary["rules"] == []


def test_states_are_plan_condition_4_list():
    # 계획 3 채택 조건 4의 상태 목록 그대로(순서 포함): 랜딩 2, 카테고리, 모델 2, 채팅 8, 서랍, 전체 삭제 확인.
    # 그 뒤에 2026-11-11 근거 접기 확인용 2개(근거 펼침, 공식 링크 표시)를 덧붙인다(조건 4의 15개는 그대로)
    assert list(STATES) == [
        "landing-empty", "landing-recent", "category", "model-washer", "model-aircon",
        "chat-empty", "chat-loading", "chat-answer", "chat-followup", "chat-not-found", "chat-other-brand",
        "chat-error", "chat-save-failed", "drawer", "delete-all-confirm",
        "chat-evidence-open", "chat-doc-links",
    ]


def test_summarize_adds_incomplete_count_and_rules():
    results = {"violations": [{"id": "region", "impact": "minor"}],
               "incomplete": [{"id": "color-contrast", "impact": "serious"}, {"id": "aria-hidden-focus", "impact": None}]}
    summary = summarize(results)
    assert summary["total"] == 1 and summary["rules"] == ["region"]
    assert summary["incomplete"] == 2
    assert summary["incomplete_rules"] == ["color-contrast", "aria-hidden-focus"]


def test_fake_replies_have_screen_answer_shape():
    # 화면(app.js isAnswer)이 답으로 받는 모양: answer·question_masked가 글자이고 error_code가 없다
    for kind in ("found", "not_found", "other_brand"):
        status, body = fake_reply(kind, "측정용 질문입니다")
        assert status == 200 and "error_code" not in body, kind
        assert isinstance(body["answer"], str) and body["question_masked"] == "측정용 질문입니다", kind
    assert fake_reply("found", "q")[1]["found"] is True and fake_reply("found", "q")[1]["citations"]
    assert fake_reply("not_found", "q")[1]["found"] is False
    assert fake_reply("other_brand", "q")[1]["reason"] == "other_brand"
    status, body = fake_reply("error", "q")
    assert status == 504 and body["error_code"] == "AI_TIMEOUT"


def test_local_server_serves_public_with_module_mime():
    with serve_public() as base:
        with urllib.request.urlopen(f"{base}/app.js") as res:
            assert res.headers["Content-Type"].startswith("text/javascript")   # JS 모듈은 JavaScript 형식이어야 불러와짐
        with urllib.request.urlopen(f"{base}/") as res:
            assert "펴봄" in res.read().decode("utf-8")


def test_context_headers_send_bypass_only_to_remote_url():
    # 미리보기는 배포 보호가 있어 우회 헤더가 필요하고, 로컬 정적 서버에는 보내지 않는다(Task 8)
    from measure.a11y import context_headers
    assert context_headers(None, "가짜값") == {}
    assert context_headers("https://preview.example.vercel.app", "가짜값") == {"x-vercel-protection-bypass": "가짜값"}
    assert context_headers("https://preview.example.vercel.app", None) == {}
