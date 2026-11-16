"""v1.6 "찾지 못함" 원인 조사 도구(docs/평가/v16-not-found.md).

답변 AI 출력을 app/answer/check.py와 같은 순서로 분류하고, 인용마다 따로 판정한다.
서비스 코드는 바꾸지 않고 감싸기만 한다. 설명서 본문과 AI 원래 출력은 measure/out/v16-not-found/(git 제외)에만 저장한다.
"""
import csv
import datetime
import json
import re
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

from app.answer.check import MAX_QUOTE, parse_and_verify
from app.answer.prompting import build_messages

PASS, JSON_ERROR, FOUND_FALSE, EMPTY = "통과", "JSON 오류", "found false", "답·인용 비어 있음"
UNRETRIEVED, BAD_QUOTE, NOT_IN_CHUNK = "검색 안 된 chunk_id", "인용 비어 있음·150자 초과", "인용이 조각에 없음"
HEAD = 20  # "본문 맨 앞 쪽 표시": 앞 20자 안


def _num(page: int) -> str:
    return rf"(?<!\d){page}(?!\d)"


def _squash(text: str) -> str:
    return " ".join(text.split())


def page_marker(content: str, page: int | None) -> bool:
    return page is not None and re.search(_num(page), content[:HEAD]) is not None


def marker_shape(content: str, page: int | None) -> str | None:
    if not page_marker(content, page):
        return None
    head = content[:HEAD]
    if re.search(rf"한국어\s+{_num(page)}", head):
        return "한국어 N"
    if re.search(rf"{_num(page)}\s+한국어", head):
        return "N 한국어"
    return "그 밖"


def strip_page_marker(content: str, page: int | None) -> tuple[str, str]:
    """본문 맨 앞에서 쪽 번호 끝까지와 바로 뒤 공백·줄바꿈을 지운다. (남은 본문, 지운 글자)"""
    m = re.search(_num(page), content[:HEAD]) if page is not None else None
    if not m:
        return content, ""
    end = m.end()
    while end < len(content) and content[end].isspace():
        end += 1
    return content[end:], content[:end]


def _judge(item, by_id: dict, chunks: list) -> dict:
    if not isinstance(item, dict):
        return {"chunk_id": None, "alone_ok": False, "alone_reason": JSON_ERROR}
    cid, quote = item.get("chunk_id"), item.get("quote")
    chunk = by_id.get(cid)
    if chunk is None:  # check.py 54줄: 검색된 조각 번호가 아님
        quote_in = []
        if isinstance(quote, str) and quote.strip():
            quote_in = [{"id": c.id, "page": c.page, "id_is_page": c.page == cid, "page_marker": page_marker(c.content, c.page)}
                        for c in chunks if _squash(quote) in _squash(c.content)]
        return {"chunk_id": cid, "alone_ok": False, "alone_reason": UNRETRIEVED, "quote_in": quote_in,
                "page_with_marker": any(q["id_is_page"] and q["page_marker"] for q in quote_in)}
    if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE:
        reason = BAD_QUOTE
    elif _squash(quote) not in _squash(chunk.content):
        reason = NOT_IN_CHUNK
    else:
        reason = PASS
    return {"chunk_id": cid, "alone_ok": reason == PASS, "alone_reason": reason}


def classify(raw: str, chunks: list) -> dict:
    """check.py parse_and_verify와 같은 순서로 처음 걸린 검사(reason)와 인용별 판정(citations)."""
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"reason": JSON_ERROR, "citations": []}
    if not isinstance(data, dict) or not isinstance(data.get("found"), bool):
        return {"reason": JSON_ERROR, "citations": []}
    if not data["found"]:
        return {"reason": FOUND_FALSE, "citations": []}
    answer, cited = data.get("answer"), data.get("citations")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(cited, list) or not cited:
        return {"reason": EMPTY, "citations": []}
    by_id = {c.id: c for c in chunks}
    cites = [_judge(item, by_id, chunks) for item in cited]
    return {"reason": next((c["alone_reason"] for c in cites if not c["alone_ok"]), PASS), "citations": cites}


def ask_fixed(question: str, chunks: list, complete, prompt_version: str, classify_chunks: list | None = None) -> dict:
    """service.py 77~85줄과 같은 흐름(같은 messages로 최대 2번)을 고정 조각으로. 모든 출력을 남긴다.

    classify_chunks: 분류·쪽 대조에 쓸 조각(태그의 page만 비운 실험에서 원래 쪽으로 대조하려고)
    """
    messages = build_messages(question, chunks, prompt_version)
    outputs, classes, result = [], [], None
    for _ in range(2):
        raw = complete(messages)
        outputs.append(raw)
        classes.append(classify(raw, classify_chunks or chunks))
        result = parse_and_verify(raw, chunks)
        if result:
            break
    return {"outputs": outputs, "classes": classes, "found": bool(result and result.found)}


def capture_deps(deps, rec: dict):
    """answer_question에 넘길 Deps를 감싸 답변 AI 출력·답변 AI에 간 조각·바꾸기 결과를 rec에 모은다."""
    rec.update(outputs=[], chunks=[], rewrite=None)

    def search(*args):
        found = deps.search(*args)
        rec["chunks"] = list(found)
        return found

    def diagnostic(model_id):
        extra = deps.diagnostic(model_id)
        seen = {c.id for c in rec["chunks"]}
        rec["chunks"] += [c for c in extra if c.id not in seen]  # service.py 72~74줄과 같은 덧붙임
        return extra

    def complete(messages):
        raw = deps.complete(messages)
        rec["outputs"].append(raw)
        return raw

    def rewrite(question, history):
        rec["rewrite"] = deps.rewrite(question, history)
        return rec["rewrite"]

    return replace(deps, search=search, diagnostic=diagnostic, complete=complete, rewrite=rewrite)


def verdict(n: int, k: int, ratio: float) -> str:
    """실행 전 확정 문턱: 3건 미만이면 판단 불가, k/n이 ratio 이상이면 지지됨."""
    if n < 3:
        return "판단 불가"
    return "지지됨" if k / n >= ratio else "지지 안 됨"


def _failed(cls: dict) -> bool:  # parse_and_verify가 None인 출력(found false는 떨어짐이 아님)
    return cls["reason"] not in (PASS, FOUND_FALSE)


def stage3_judgments(items: list[dict]) -> dict:
    """3단계 판정 ①~④(docs/평가/v16-not-found.md "1~4단계 판단 기준")."""
    def rule(n_list, k_list, ratio):
        return {"n": len(n_list), "k": len(k_list), "verdict": verdict(len(n_list), len(k_list), ratio)}

    has_unretrieved = lambda cls: any(c["alone_reason"] == UNRETRIEVED for c in cls["citations"])
    nf = [i for i in items if i["answerable"] and not i["error"] and i["found"] is False]
    twice = [i for i in nf if len(i["classes"]) == 2 and all(map(_failed, i["classes"])) and any(map(has_unretrieved, i["classes"]))]
    cites = [c for i in items for cls in i["classes"] for c in cls["citations"] if c["alone_reason"] == UNRETRIEVED]
    first = [i for i in items if i["classes"] and _failed(i["classes"][0])]
    same = [i for i in first if len(i["classes"]) == 2 and i["classes"][1]["reason"] == i["classes"][0]["reason"]]
    dropped = [cls for i in items for cls in i["classes"] if _failed(cls)]
    return {"①": rule(nf, twice, 0.5),
            "②": rule(cites, [c for c in cites if c["page_with_marker"]], 0.8),
            "③": rule(first, same, 2 / 3),
            "④": rule(dropped, [cls for cls in dropped if any(c["alone_ok"] for c in cls["citations"])], 0.5)}


BULLETS = "•·-"


def _bare(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace() and ch not in BULLETS)


def expected_hit(expected_ref: str, chunks: list[dict]) -> str:
    """기대 근거(manual:쪽·guide:문서·chunk:번호) 중 하나라도 검색 조각(ref·id)과 맞으면 검색됨."""
    refs = [r for r in expected_ref.split("|") if r]
    have = {c["ref"] for c in chunks} | {f"chunk:{c['id']}" for c in chunks}
    if any(r in have for r in refs):
        return "검색됨"
    if not refs or any(r.split(":")[0] not in ("manual", "guide", "chunk") for r in refs):
        return "판단 불가"
    return "검색 안 됨"


def quote_places(quote: str, chunks: list) -> dict:
    """인용 글이 그대로 있는 조각 번호: ㉠ check.py와 같은 공백 정리, ㉡ 공백·줄바꿈·글머리 기호를 모두 지움."""
    return {"㉠": [c.id for c in chunks if _squash(quote) in _squash(c.content)],
            "㉡": [c.id for c in chunks if _bare(quote) in _bare(c.content)]}


# ── 실행(로컬): python -m measure.v16_not_found stage1|stage2|stage4|stage3 ──
# stage1은 DB 조회(SELECT)만, 나머지는 AI를 부른다(장부 check_budget을 먼저 통과한 뒤 실행). 결과는 OUT에만 쓴다.

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "measure" / "out" / "v16-not-found"
CHUNK_SQL = """SELECT c.id, c.doc_id, d.doc_type, d.title, d.source_url, c.page, c.content, 0.0
FROM chunks c JOIN documents d ON d.id = c.doc_id"""


def _chunk_info(c) -> dict:
    return {"id": c.id, "ref": c.ref, "page": c.page, "page_marker": page_marker(c.content, c.page)}


def _save(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("저장:", path.relative_to(ROOT), flush=True)


def _open_sets() -> dict[str, list[dict]]:
    from evaluation.followups import load_followups
    from measure.search_eval import read_cases
    with (ROOT / "evaluation" / "questions.csv").open(encoding="utf-8-sig", newline="") as f:
        questions = list(csv.DictReader(f))
    return {"questions": questions, "paraphrase_dev": read_cases(ROOT / "evaluation" / "paraphrase_dev.csv"),
            "followups": load_followups(ROOT / "evaluation" / "followups.csv")}


def answerable(case: dict) -> bool:
    return case["expected_found"] == "true" and case.get("type") != "trap"


def _all_chunks(conn):
    from app.retrieval.search import Chunk
    return [Chunk(*row) for row in conn.execute(CHUNK_SQL).fetchall()]


def stage1() -> None:
    from app.core.db import get_conn
    with get_conn() as conn:
        chunks = _all_chunks(conn)
        doc_models = conn.execute("SELECT doc_id, model_id FROM document_models").fetchall()
    stats: dict = {}
    for c in chunks:
        key = f"{c.doc_id} {'쪽 없음' if c.page is None else ('홀수' if c.page % 2 else '짝수')}"
        s = stats.setdefault(key, Counter())
        s["조각"] += 1
        if page_marker(c.content, c.page):
            s["맨 앞 쪽 표시"] += 1
            s[marker_shape(c.content, c.page)] += 1
    p73 = [_chunk_info(c) for c in chunks if c.doc_id == "manual-samsung-wd90h25" and c.page == 73]
    by_model: dict = {}
    for doc_id, model_id in doc_models:
        by_model.setdefault(model_id, set()).add(doc_id)
    expected: dict = {}
    for cases in _open_sets().values():
        for case in cases:
            docs = by_model.get(case["model_id"], set())
            for ref in filter(None, case["expected_ref"].split("|")):
                kind, _, val = ref.partition(":")
                for c in chunks:
                    if ((kind == "manual" and c.doc_type == "manual" and c.doc_id in docs and c.page == int(val))
                            or (kind == "guide" and c.doc_id == val) or (kind == "chunk" and c.id == int(val))):
                        expected[c.id] = c
    exp = {"조각": len(expected), "맨 앞 쪽 표시": sum(page_marker(c.content, c.page) for c in expected.values())}
    result = {"docs": {k: dict(v) for k, v in sorted(stats.items())}, "samsung_p73": p73, "expected_chunks": exp}
    print(json.dumps(result, ensure_ascii=False, indent=1))
    _save("stage1", result)


def _settings_record(settings) -> dict:
    from evaluation.run_config import differences, run_settings
    return {"settings": run_settings(settings), "differences": differences(settings), "force_fail": settings.force_fail}


def _check_outputs(outputs: list[str], chunks: list) -> list[dict]:
    classes = [classify(raw, chunks) for raw in outputs]
    for raw, cls in zip(outputs, classes):  # 자체 확인: 분류가 서비스 검증과 어긋나면 멈춘다
        assert (cls["reason"] in (PASS, FOUND_FALSE)) is (parse_and_verify(raw, chunks) is not None), cls
    return classes


def _has55(classes: list[dict]) -> bool:
    return any(c["chunk_id"] == 55 for cls in classes for c in cls["citations"])


def stage2() -> None:
    from app.answer.llm import complete_json
    from app.core.config import get_settings
    from app.core.db import get_conn
    src = json.loads((ROOT / "measure" / "out" / "v15-ui" / "5c-재현-2026-11-11.json").read_text(encoding="utf-8"))
    saved = src["raw"][0]["chunks"]
    ids = [c["id"] for c in saved]
    assert ids == [105, 62, 78, 83, 109], ids
    with get_conn() as conn:
        rows = {c.id: c for c in _all_chunks(conn) if c.id in ids}
    assert all(rows[c["id"]].content == c["content"] for c in saved), "11/11 저장 본문과 DB 본문이 다름"
    chunks = [replace(rows[c["id"]], score=c["score"]) for c in saved]
    settings = get_settings()
    assert not settings.force_fail
    usage: dict = {}
    complete = lambda m: complete_json(m, settings, usage=usage)
    i83 = ids.index(83)
    stripped, removed = strip_page_marker(chunks[i83].content, 55)
    no_marker = chunks[:i83] + [replace(chunks[i83], content=stripped)] + chunks[i83 + 1:]
    no_page = chunks[:i83] + [replace(chunks[i83], page=None)] + chunks[i83 + 1:]
    variants = {"가": (chunks, None), "나": (no_marker, None), "다": (no_page, chunks)}
    result = {"question": src["question"], "chunk_ids": ids, "removed": removed, "removed_len": len(removed),
              "run": _settings_record(settings), "variants": {}}
    for name, (given, original) in variants.items():
        runs = []
        for i in range(3):
            r = ask_fixed(src["question"], given, complete, settings.prompt_version, classify_chunks=original)
            _check_outputs(r["outputs"], original or given)
            runs.append(r | {"has55": _has55(r["classes"])})
            print(name, i + 1, [c["reason"] for c in r["classes"]], "55" if runs[-1]["has55"] else "", flush=True)
        result["variants"][name] = {"runs": runs, "count55": sum(r["has55"] for r in runs)}
    result["usage"] = usage
    result["answer_calls"] = sum(len(r["outputs"]) for v in result["variants"].values() for r in v["runs"])
    _save("stage2", result)


def _ask_case(answer_question, get_deps, settings, model_id, question, history=None) -> dict:
    from app.core.errors import AppError
    rec: dict = {}
    deps = get_deps()
    try:
        resp = answer_question(model_id, question, capture_deps(deps, rec), settings, debug=True, history=history)
    except AppError as e:
        resp = {"error_code": e.code}
    classes = _check_outputs(rec.get("outputs", []), rec.get("chunks", []))
    if "error_code" not in resp:
        assert [c.id for c in rec["chunks"]] == resp["retrieved_chunk_ids"]
    rw = rec.get("rewrite")
    return {"model_id": model_id, "question": question, "history": history or [], "resp": resp,
            "rewrite": None if rw is None else {"text": rw.text, "used": rw.used, "reason": rw.reason},
            "chunks": [_chunk_info(c) for c in rec.get("chunks", [])], "outputs": rec.get("outputs", []), "classes": classes,
            "found": resp.get("found"), "error": resp.get("error_code", ""), "usage": dict(deps.timings)}


def _service():
    from app.ask.routes import get_deps
    from app.ask.service import answer_question
    from app.core.config import get_settings
    settings = get_settings()
    assert not settings.force_fail
    return answer_question, get_deps, settings


def stage4() -> None:
    answer_question, get_deps, settings = _service()
    src = json.loads((OUT / "user-test-C-dry-history.json").read_text(encoding="utf-8"))
    runs = []
    for i in range(3):
        r = _ask_case(answer_question, get_deps, settings, src["model_id"], src["question"], src["history"])
        runs.append(r)
        print(i + 1, r["rewrite"] and r["rewrite"]["reason"], [c["reason"] for c in r["classes"]], r["found"], r["error"], flush=True)
    _save("stage4", {"run": _settings_record(settings), "runs": runs})


def stage3() -> None:
    from evaluation.followups import run_all
    answer_question, get_deps, settings = _service()
    sets = _open_sets()
    items = []
    for name in ("questions", "paraphrase_dev"):
        for case in sets[name]:
            r = _ask_case(answer_question, get_deps, settings, case["model_id"], case["question"])
            items.append({"set": name, "id": case["id"], "answerable": answerable(case)} | r)
            print(name, case["id"], [c["reason"] for c in r["classes"]], r["found"], r["error"], flush=True)
    captured = []

    def client(model_id, question, history):  # 기존 이어지는 질문 평가(run_all)와 같은 방식, 턴 순서대로 불린다
        captured.append(_ask_case(answer_question, get_deps, settings, model_id, question, history))
        return captured[-1]["resp"]

    rows = run_all(sets["followups"], client)
    by_key = {(t["dialog_id"], t["turn"]): t for t in sets["followups"]}
    for row, r in zip(rows, captured, strict=True):
        case = by_key[(row["dialog_id"], str(row["turn"]))]
        assert case["question"] == r["question"]
        items.append({"set": "followups", "id": f"{row['dialog_id']}-{row['turn']}", "answerable": answerable(case)} | r)
        print("followups", items[-1]["id"], [c["reason"] for c in r["classes"]], r["found"], r["error"], flush=True)
    _save("stage3", {"run": _settings_record(settings), "items": items})


def _previous_runs(set_name: str, case: dict) -> list[dict]:
    """evaluation/results/에서 같은 번호·같은 질문 글이 있는 실행의 찾음 여부(이어지는 질문 결과는 번호 체계가 달라 해당 없음)."""
    runs = []
    for path in sorted((ROOT / "evaluation" / "results").glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("id") == case["id"] and row.get("question") == case["question"]:
                    runs.append({"file": path.name, "method": row.get("method", ""),
                                 "found": row.get("got_found", row.get("found", ""))})
    return runs


def stage5() -> None:
    """3단계 결과의 찾지 못함 11건 나누기와 인용 대조(AI 호출 없음, DB는 SELECT만)."""
    from app.core.db import get_conn
    stage3_path = sorted(OUT.glob("stage3-2*.json"))[-1]
    items = json.loads(stage3_path.read_text(encoding="utf-8"))["items"]
    with get_conn() as conn:
        by_id = {c.id: c for c in _all_chunks(conn)}
    cases = {(name, c.get("id") or f"{c['dialog_id']}-{c['turn']}"): c for name, cs in _open_sets().items() for c in cs}
    rows, quotes, md = [], [], ["# 5단계 채팅 Claude 대조용 (설명서 본문 포함, git 제외)", "", f"원본: {stage3_path.name}", ""]
    for it in items:
        if not (it["answerable"] and not it["error"] and it["found"] is False):
            continue
        case, top = cases[(it["set"], it["id"])], it["chunks"][:5]
        hit = expected_hit(case["expected_ref"], top)
        rows.append({"set": it["set"], "id": it["id"], "model_id": it["model_id"], "question": it["question"],
                     "rewritten": it["resp"].get("rewritten_question"), "expected_ref": case["expected_ref"], "chunks": top,
                     "extra_chunks": len(it["chunks"]) - len(top), "reasons": [c["reason"] for c in it["classes"]],
                     "hit": hit, "previous": _previous_runs(it["set"], case)})
        if hit == "검색됨":
            md += [f"## {it['id']} ({it['set']}, {it['model_id']})", f"- 질문: {it['question']}",
                   f"- 바꾼 질문: {it['resp'].get('rewritten_question') or '없음'}", f"- 기대 근거: {case['expected_ref']}", ""]
            for c in top:
                md += [f"### 조각 {c['id']} ({c['ref']}, 쪽 표시 {'있음' if c['page_marker'] else '없음'})", "", "```",
                       by_id[c["id"]].content, "```", ""]
    md += ["# 인용 대조 (\"인용이 조각에 없음\" 출력)", ""]
    for it in items:
        top = [by_id[c["id"]] for c in it["chunks"][:5]]
        for n, (raw, cls) in enumerate(zip(it["outputs"], it["classes"]), 1):
            if cls["reason"] != NOT_IN_CHUNK:
                continue
            md += [f"## {it['id']} 출력 {n}", ""]
            for k, item in enumerate(json.loads(raw)["citations"], 1):
                places = quote_places(item["quote"], top)
                quotes.append({"id": it["id"], "output": n, "cite": k, "chunk_id": item["chunk_id"],
                               "quote_len": len(item["quote"]), "alone": cls["citations"][k - 1]["alone_reason"]} | places)
                cited = by_id.get(item["chunk_id"])
                md += [f"### 인용 {k}: chunk_id {item['chunk_id']} (㉠ {places['㉠']} ㉡ {places['㉡']})", "", "인용 글:", "```",
                       item["quote"], "```", f"조각 {item['chunk_id']} 본문:", "```",
                       cited.content if cited else "(DB에 없는 번호)", "```", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stage5-대조용.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"rows": rows, "quotes": quotes}, ensure_ascii=False, indent=1))
    _save("stage5", {"stage3": stage3_path.name, "rows": rows, "quotes": quotes})


def main() -> None:
    from ingest.__main__ import load_env
    load_env()
    {"stage1": stage1, "stage2": stage2, "stage4": stage4, "stage3": stage3, "stage5": stage5}[sys.argv[1]]()


if __name__ == "__main__":
    main()
