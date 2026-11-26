"""모델 추가 도구(2차 Task 8): python -m ingest.add_model <check|draft|codes|ingest|link-guide|remove> …

- 운영자 PC에서 돈다. 질문·답변 코드(app/ask·retrieval·answer)는 가져다 쓰기만 한다(Global 1).
- DB 연결은 DB 작업 직전에 열고 바로 닫는다. AI 호출·파일 처리 동안 쥐지 않는다(Global 8).
- 가이드는 다시 적재하지 않고 document_models에 한 줄만 넣는다(Global 9).
- remove --yes는 사용자 확인 뒤에만 붙인다(CLAUDE.md 데이터 삭제).
"""
import argparse
import csv
import hashlib
import io
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

from ingest.__main__ import ingest_document, load_env
from ingest.clean import clean_text
from ingest.load import ROOT
from ingest.page_marker import count_remaining_markers, strip_page_marker
from ingest.pdf import extract_pages

DOCUMENTS = ROOT / "data" / "documents.json"
MODELS = ROOT / "data" / "models.json"
LEDGER = ROOT / "evaluation" / "phase2" / "ledger.csv"
RESULTS_DIR = ROOT / "evaluation" / "results"  # 결과 CSV(질문·답·인용 쪽·found·시간)
JUDGE_DIR = ROOT / "measure" / "out" / "phase2"  # 판정지·판정 입력(설명서 글이 들어갈 수 있어 git 밖)
JUDGE_COLUMNS = ("qid", "질문", "답", "인용 쪽", "verdict", "borderline", "worse_verdict", "메모")  # 전 측정 판정지와 같음
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")  # 파일 이름에 들어가는 모델 id·label(경로 글자 막기)
CAP_USD = 1.0  # 2차 장부 상한(Global 10)
MIN_CHARS = 30  # 공백을 뺀 글자가 이보다 적으면 글자 없는 쪽(Claude 판단)
APPLIANCES = ("washer", "dryer", "aircon")  # Global 5
GUIDE_DOCS = "doc_id IN (SELECT id FROM documents WHERE doc_type = 'guide')"  # 가이드 문서와의 연결만(고정 SQL 조각)
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")  # 스프레드시트가 수식으로 읽는 첫 글자(OWASP CSV Injection)


def _get_conn():
    from app.core.db import get_conn  # load_env 뒤에 설정을 읽게 한다
    return get_conn()


# ── 검사 ──
def check_document(doc: dict, *, extract=extract_pages) -> dict:
    """글자 없는 PDF(30자 미만 쪽이 절반 넘음)와 남은 쪽 표시(적재와 같은 지우기 뒤)를 본다(설계 9.2)."""
    pages = extract(str(ROOT / doc["file"]))
    empty = [page for page, text in pages if len(re.sub(r"\s", "", text)) < MIN_CHARS]
    remaining = []
    for page, text in pages:  # 적재(ingest/load.py)와 같은 흐름으로 지운 뒤 센다
        count = count_remaining_markers(strip_page_marker(clean_text(text), page)[0], page)
        if count:
            remaining.append((page, count))
    ok = bool(pages) and len(empty) * 2 <= len(pages) and not remaining
    return {"pages": len(pages), "text_pages": len(pages) - len(empty), "empty_pages": empty,
            "remaining_markers": remaining, "ok": ok}


def error_code_candidates(doc: dict, *, extract=extract_pages) -> list[str]:
    """설명서 글에서 코드처럼 생긴 글자(4E·DE·CH10)를 처음 나온 순서로. 사람이 error_codes.json을 채울 때 본다."""
    from app.retrieval.search import extract_code_tokens  # 질문의 코드 뽑기와 같은 규칙(가져다 쓰기만)
    found = []
    for _, text in extract(str(ROOT / doc["file"])):
        found += [t for t in extract_code_tokens(text) if t not in found]
    return found


# ── 초안 ──
def draft_entries(*, doc_id, model_id, brand, appliance, title, source_url, pdf, codes: list[str], fetched_at,
                  name, scope_note, model_name_hint) -> tuple[dict, dict]:
    """documents.json·models.json 항목 초안. 사람이 정할 값(name·scope_note·model_name_hint)은 인자로 받아
    자리 표시 글자를 남기지 않는다. 진단 쪽(diagnostic_refs)은 빈 목록으로 시작한다."""
    if not (NAME_RE.fullmatch(doc_id) and NAME_RE.fullmatch(model_id)):
        raise ValueError("문서·모델 id는 영문 소문자·숫자·하이픈만")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fetched_at):
        raise ValueError("fetched_at은 YYYY-MM-DD")
    date.fromisoformat(fetched_at)  # 없는 날짜(13월 등)면 ValueError
    if doc_id in {d["id"] for d in _load(DOCUMENTS)}:
        raise ValueError(f"이미 있는 문서 id: {doc_id}")
    if model_id in {m["id"] for m in _load(MODELS)}:
        raise ValueError(f"이미 있는 모델 id: {model_id}")
    if appliance not in APPLIANCES:
        raise ValueError(f"가전 종류는 {', '.join(APPLIANCES)} 중 하나: {appliance}")
    if not source_url.startswith("https://"):
        raise ValueError("source_url은 https://로 시작해야 해요")
    if not name or "(" in name:
        raise ValueError("name은 코드 없는 이름(괄호 없음)")
    if not codes:
        raise ValueError("모델 코드가 하나 이상 있어야 해요")
    doc = {"id": doc_id, "doc_type": "manual", "title": title, "source_url": source_url, "scope_note": scope_note,
           "model_ids": [model_id], "file": pdf, "fetched_at": fetched_at}
    model = {"id": model_id, "brand": brand, "appliance": appliance, "model_name": " / ".join(codes),
             "display_name": f"{name} ({'·'.join(codes)})", "name": name, "model_codes": list(codes),
             "official_url": source_url, "model_name_hint": model_name_hint, "diagnostic_refs": []}
    return doc, model


def _load(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_documents(docs: list[dict]) -> str:
    """documents.json 모양 그대로(항목마다 한 줄에 한 필드, 목록은 한 줄)."""
    def block(d):
        return "  {\n" + ",\n".join(f"    {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
                                     for k, v in d.items()) + "\n  }"
    return "[\n" + ",\n".join(block(d) for d in docs) + "\n]\n"


def dump_models(models: list[dict]) -> str:
    return json.dumps(models, ensure_ascii=False, indent=2) + "\n"


def _write(path: Path, text: str) -> None:
    newline = "\r\n" if b"\r\n" in Path(path).read_bytes() else "\n"  # 작업 폴더의 줄 끝을 지킨다(autocrlf)
    Path(path).write_text(text, encoding="utf-8", newline=newline)


def write_documents(docs: list[dict], path: Path = DOCUMENTS) -> None:
    _write(path, dump_documents(docs))


def write_entries(doc: dict, model: dict, *, documents_path: Path = DOCUMENTS, models_path: Path = MODELS) -> None:
    write_documents(_load(documents_path) + [doc], documents_path)
    _write(models_path, dump_models(_load(models_path) + [model]))


# ── 가이드 연결 ──
def link_guide(guide_id: str, model_id: str, *, connect=_get_conn, documents_path: Path = DOCUMENTS) -> bool:
    """document_models에 한 줄만(조각은 안 건드림, Global 9) + documents.json 그 가이드의 model_ids. 새로 넣었으면 True."""
    docs = _load(documents_path)
    guide = next((d for d in docs if d["id"] == guide_id), None)
    if not guide or guide["doc_type"] != "guide":
        raise ValueError(f"documents.json의 가이드가 아님: {guide_id}")
    if model_id not in {m["id"] for m in _load(MODELS)}:
        raise ValueError(f"models.json에 없는 모델: {model_id}")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO document_models (doc_id, model_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (guide_id, model_id))
        inserted = cur.rowcount == 1
    if model_id not in guide["model_ids"]:  # 연결을 닫은 뒤에 파일을 쓴다
        guide["model_ids"].append(model_id)
        write_documents(docs, documents_path)
    return inserted


# ── 되돌리기 ──
def remove_model_data(doc_id: str, model_id: str, *, connect=_get_conn, yes: bool = False) -> dict:
    """지울 개수를 세어 돌려주고, yes=True일 때만 그 문서의 chunks·document_models·documents 행과
    그 모델의 가이드 연결 행(가이드 문서와의 연결만)을 한 트랜잭션으로 지운다. bundle_chunks·다른 문서는 안 건드린다(설계 9.3-12).
    그 모델이 아직 models.json에 있거나, DB에 없는 문서·가이드·연결 안 된 모델·다른 모델도 쓰는 설명서면 거절한다."""
    if model_id in {m["id"] for m in _load(MODELS)}:
        raise ValueError(f"{model_id}가 아직 data/models.json에 있어요. models.json에서 빼는 PR을 병합한 뒤에 지워요(Task 10 Step 1)")
    with connect() as conn, conn.cursor() as cur:
        def one(sql, params=()):
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else None

        doc_type = one("SELECT doc_type FROM documents WHERE id = %s", (doc_id,))
        if doc_type is None:
            raise ValueError(f"DB에 없는 문서예요(id를 확인하세요): {doc_id}")
        if doc_type != "manual":
            raise ValueError(f"설명서만 되돌려요(가이드는 지우지 않음, Global 9): {doc_id}")
        if not one("SELECT count(*) FROM document_models WHERE doc_id = %s AND model_id = %s", (doc_id, model_id)):
            raise ValueError(f"문서와 모델이 연결돼 있지 않아요: {doc_id} · {model_id}")
        others = one("SELECT count(*) FROM document_models WHERE doc_id = %s AND model_id <> %s", (doc_id, model_id))
        if others:
            raise ValueError(f"이 설명서는 다른 모델 {others}개에도 연결돼 있어 지우지 않아요: {doc_id}")
        has_bundle = one("SELECT to_regclass('bundle_chunks')") is not None
        has_variants = one("SELECT to_regclass('chunk_variants')") is not None
        out = {"doc_id": doc_id, "model_id": model_id, "documents": 1,
               "chunks": one("SELECT count(*) FROM chunks WHERE doc_id = %s", (doc_id,)),
               "document_models": one("SELECT count(*) FROM document_models WHERE doc_id = %s", (doc_id,)),
               "guide_links": one(f"SELECT count(*) FROM document_models WHERE model_id = %s AND {GUIDE_DOCS}", (model_id,)),
               # 실험 조각이 이 문서를 참조하면 documents 행을 지울 수 없다(외래 키). 세기만 하고 건드리지 않는다
               "bundle_chunks": one("SELECT count(*) FROM bundle_chunks WHERE doc_id = %s", (doc_id,)) if has_bundle else 0,
               # 실험 색인은 chunks를 ON DELETE CASCADE로 참조해 함께 지워진다(measure/chunk_variants.sql)
               "chunk_variants": one("SELECT count(*) FROM chunk_variants v JOIN chunks c ON c.id = v.chunk_id "
                                     "WHERE c.doc_id = %s", (doc_id,)) if has_variants else 0,
               "deleted": False}
        if not yes:
            return out
        if out["bundle_chunks"]:
            raise ValueError(f"bundle_chunks에 이 문서 행이 {out['bundle_chunks']}개 있어 지우지 않아요(실험 조각은 따로 정리)")
        with conn.transaction():
            cur.execute(f"DELETE FROM document_models WHERE model_id = %s AND {GUIDE_DOCS}", (model_id,))
            cur.execute("DELETE FROM document_models WHERE doc_id = %s", (doc_id,))
            cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        return {**out, "deleted": True}


# ── 적재 ──
def require_production(settings) -> None:
    """운영 그대로 설정(evaluation/run_config.PRODUCTION)이 아니면 멈춘다. 경고만 하고 계속하지 않는다(Global 1)."""
    from evaluation.run_config import differences
    diffs = differences(settings)
    if diffs:
        raise ValueError("운영 그대로 설정이 아니라 멈춰요(.env 확인): " + ", ".join(diffs))


def ingest_manual(doc_id: str, *, yes: bool = False, connect=_get_conn) -> dict:
    """설명서만 적재한다(가이드는 다시 적재하지 않음, Global 9). 이미 DB에 있는 문서는 다시 넣으면 조각을 지우고
    새로 넣으므로(데이터 삭제) yes=True일 때만. 있는지 보는 연결은 짧게 열고 닫은 뒤 임베딩한다(Global 8)."""
    from app.core.config import get_settings
    require_production(get_settings())
    doc = _doc(doc_id)
    if doc["doc_type"] != "manual":
        raise ValueError(f"가이드는 다시 적재하지 않아요(Global 9, link-guide로 연결만): {doc_id}")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM documents WHERE id = %s", (doc_id,))
        exists = cur.fetchone() is not None
    if exists and not yes:
        raise ValueError(f"이미 DB에 있는 문서예요. 다시 넣으면 조각을 지우고 새로 넣어요(사용자 확인 뒤 --yes): {doc_id}")
    return ingest_document(doc_id, connect=connect)


def csv_cell(value):
    """스프레드시트가 수식으로 읽지 않게 = + - @ 탭 CR로 시작하는 글자 앞에 '를 붙인다(판정 입력 md는 원문 그대로)."""
    return "'" + value if isinstance(value, str) and value.startswith(FORMULA_START) else value


# ── 확인 질문(Task 9) ──
def _ask_route(model_id: str, question: str, deps) -> dict:
    """새 대화(앞 대화 없음)로 /api/ask를 부를 때와 같은 처리: 라우트 함수를 그대로 부른다(본문 검사·오류 응답 포함)."""
    from app.ask.routes import AskBody, ask
    out = ask(AskBody(model_id=model_id, question=question), debug=False, deps=deps)
    return out if isinstance(out, dict) else json.loads(out.body)  # 오류면 {"error_code", "message"}


def _groups(citations: list) -> list[dict]:
    """public/js/evidence.js groupCitations와 같다: 설명서는 쪽별, 가이드는 제목별, 처음 나온 순서."""
    groups = {}
    for c in (c for c in citations if isinstance(c, dict)):
        manual = c.get("doc_type") == "manual"
        key = f"manual:{c.get('page')}" if manual else f"guide:{c.get('title')}"
        g = groups.setdefault(key, {"doc_type": "manual" if manual else "guide", "page": c.get("page"),
                                    "title": str(c.get("title") or ""), "quotes": []})
        g["quotes"].append(str(c.get("quote") or ""))
    return list(groups.values())


def screen_text(resp: dict) -> tuple[str, str]:
    """(답 칸, 인용 쪽 칸) — 화면이 그리는 글자 그대로(store.js 답 종류, app.js answerBody, evidence.js 라벨·경고)."""
    if "error_code" in resp:
        return resp.get("message", ""), "없음"
    if resp.get("reason") == "other_brand":
        return f"(안내) 모델 안내 {resp['answer']}", "없음"
    if resp.get("found") is not True:
        return f"{resp['answer']}\n(링크) 공식 고객센터에서 찾아보기", "없음"
    citations = resp.get("citations") or []
    groups = _groups(citations)
    if not groups:
        return resp["answer"], "없음"
    warns = list(dict.fromkeys(c["warning"] for c in citations
                               if isinstance(c, dict) and isinstance(c.get("warning"), str) and c["warning"].strip()))
    pages = sorted(g["page"] for g in groups if g["doc_type"] == "manual" and isinstance(g["page"], int))
    guides = sum(g["doc_type"] == "guide" for g in groups)
    label = " · ".join(["근거 보기"] + ([f"사용설명서 {'·'.join(map(str, pages))}쪽"] if pages else [])
                       + ([f"공식 해결 가이드 {guides}개"] if guides else []))
    return "\n".join([resp["answer"]] + [f"(안내) 참고 {w}" for w in warns]), label


def _evidence_md(resp: dict) -> list[str]:
    lines = []
    for g in _groups(resp.get("citations") or []) if resp.get("found") is True else []:
        head = f"사용설명서 {g['page']}쪽 · {g['title']}" if g["doc_type"] == "manual" else f"공식 해결 가이드: {g['title']}"
        lines += [f"### {head}"] + ["> " + line for q in g["quotes"] for line in q.splitlines() or [""]] + [""]
    return lines or ["(근거 없음)", ""]


def _write_results(path: Path, done: list) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # evaluation/results 관례(BOM·CRLF)
        w = csv.writer(f)
        w.writerow(["qid", "질문", "답", "인용 쪽", "found", "error_code", "ms"])
        for r, resp, ms in done:
            text, cited = screen_text(resp)
            w.writerow([csv_cell(v) for v in (r["qid"], resp.get("question_masked", r["question"]), text, cited,
                                               resp.get("found", ""), resp.get("error_code", ""), ms)])


def _manual_page_count(model_id: str) -> int:
    doc = next((d for d in _load(DOCUMENTS) if d["doc_type"] == "manual" and model_id in d["model_ids"]), None)
    if not doc:
        raise ValueError(f"documents.json에 이 모델의 설명서가 없어요: {model_id}")
    return len(extract_pages(str(ROOT / doc["file"])))


def run_confirm(model_id: str, questions_path: str, *, expect_sha256: str, label: str, estimate_usd: float,
                page_count: int | None = None, answer=None, deps_factory=None) -> Path:
    """확인 질문 10개를 새 대화로 차례로 묻고 결과 CSV·판정지·판정 입력 파일을 쓴다. 결과 CSV 경로를 돌려준다.
    파일 해시가 다르거나, 질문 세트 검사·장부 상한을 못 넘거나, 같은 이름의 결과가 있으면 묻지 않는다.
    DB 연결은 get_deps의 검색이 그때그때 열고 닫는다(Global 8)."""
    from evaluation.phase2_verdict import validate_confirm_set
    from measure.budget import check_budget
    from app.ask import routes
    from evaluation.run_config import write_settings
    if not (NAME_RE.fullmatch(model_id) and NAME_RE.fullmatch(label)):
        raise ValueError("모델 id·label은 영문 소문자·숫자·하이픈만")
    settings = routes.get_settings()  # 라우트가 쓰는 것과 같은 설정
    require_production(settings)
    raw = Path(questions_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expect_sha256.lower():
        raise ValueError("확인 질문 파일 해시가 기록과 달라요")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    problems = validate_confirm_set(rows, page_count or _manual_page_count(model_id))
    if problems:
        raise ValueError("확인 질문 세트 검사 실패: " + "; ".join(problems))
    if estimate_usd <= 0 or not check_budget(_ledger_rows(LEDGER), estimate_usd, cap_usd=CAP_USD):
        raise ValueError(f"장부 상한 {CAP_USD}달러를 넘거나 예상 비용이 없어 묻지 않아요")
    results = Path(RESULTS_DIR) / f"phase2-{model_id}-{label}.csv"
    judge = Path(JUDGE_DIR) / f"{model_id}-{label}-judge.csv"
    judge_md = Path(JUDGE_DIR) / f"{model_id}-{label}-judge-input.md"
    if any(p.exists() for p in (results, results.with_suffix(".settings.json"), judge, judge_md)):
        raise ValueError(f"이미 같은 이름의 결과가 있어요(덮어쓰지 않음): {model_id}-{label}")
    if deps_factory is None:
        from app.ask.routes import get_deps as deps_factory
    answer = answer or _ask_route

    done = []
    for r in rows:
        start = time.perf_counter()
        resp = answer(model_id, r["question"], deps_factory())  # 질문마다 새 deps(라우트가 요청마다 만드는 것과 같음)
        ms = int((time.perf_counter() - start) * 1000)
        done.append((r, resp, ms))
        if "error_code" in resp:  # 오류 규칙(2026-11-26 사용자 결정): 하나라도 나면 더 묻지 않고 판정지도 만들지 않음
            break

    results.parent.mkdir(parents=True, exist_ok=True)
    errors = [resp["error_code"] for _, resp, _ in done if "error_code" in resp]
    if errors:
        failed = results.with_name(f"phase2-{model_id}-{label}-failed-{datetime.now():%Y%m%d-%H%M%S}.csv")
        _write_results(failed, done)
        write_settings(failed, settings, label)
        qid = done[-1][0]["qid"]
        raise ValueError(f"확인 질문 {qid}에서 오류 {', '.join(errors)} → 판정지를 만들지 않고 멈췄어요. 부분 결과 {failed.name}. "
                         "같은 label로 다시 실행할 수 있어요(다시 돌리기 1번에 세지 않음, 개발일지에 오류 종류·횟수를 기록)")
    _write_results(results, done)
    write_settings(results, settings, label)  # 그때 설정(키·접속 주소 없음)을 결과 옆에
    judge.parent.mkdir(parents=True, exist_ok=True)
    with judge.open("w", encoding="utf-8-sig", newline="") as f:  # 전 측정 판정지와 같은 8열·BOM·LF
        w = csv.writer(f, lineterminator="\n")
        w.writerow(JUDGE_COLUMNS)
        for r, resp, _ in done:
            text, cited = screen_text(resp)
            w.writerow([csv_cell(v) for v in (r["qid"], resp.get("question_masked", r["question"]), text, cited)]
                       + ["", "", "", ""])
    md = [f"# {model_id} {label} 판정 입력", "", "질문별 답과 인용문·쪽(전 측정의 근거 펼친 캡처 대신). 판정은 판정지 CSV에 적는다.", ""]
    for r, resp, _ in done:
        text, cited = screen_text(resp)
        md += [f"## {r['qid']}", f"질문: {resp.get('question_masked', r['question'])}", "답:", text,
               f"인용 쪽: {cited}", "근거:", ""] + _evidence_md(resp)
    judge_md.write_text("\n".join(md), encoding="utf-8", newline="\n")
    return results


def verdict_lines(judge_path: str) -> list[str]:
    """판정지 CSV → passes() 결과와 리포트에 붙일 한 줄. 메모에 "다른 코드 절차"가 있으면 결정기록 032 줄도."""
    from evaluation.phase2_verdict import VERDICTS, passes
    with open(judge_path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["qid"].startswith("q")]
    ok, d = passes(rows)
    counts = "·".join(f"{v} {sum(r['verdict'] == v for r in rows)}" for v in VERDICTS)
    borderline = sum(r["borderline"] == "yes" for r in rows)
    lines = [f"{'합격' if ok else '미달'}: 정답 {d['correct']}·환각 {d['hallucination']}"
             f"(경계를 나쁜 쪽으로: 정답 {d['correct_worst']}·환각 {d['hallucination_worst']})",
             f"리포트: 확인 질문 {len(rows)}개 사람 판정 — {counts}, 경계 {borderline}개 → "
             f"{'합격' if ok else '미달'}(합격선 정답 8개 이상·환각 0)"]
    other = [r["qid"] for r in rows if "다른 코드 절차" in r.get("메모", "")]
    if other:
        lines.append(f"결정기록 032 근거로 기록: {', '.join(other)}(다시 정하기는 2차 뒤)")
    return lines


def checklist_lines(model_id: str, doc_id: str = "<문서 id>") -> list[str]:
    """설계 8.3 순서: 적재 → 로컬 확인 질문 → 합격 → PR 병합·운영 화면 확인 → 그 뒤에만 "추가됨"."""
    cmd = "python -m ingest.add_model"
    steps = [
        "장부(evaluation/phase2/ledger.csv)에 적재·확인 질문 예상 비용 적기",
        f"{cmd} draft --doc-id {doc_id} --model-id {model_id} … --write",
        f"{cmd} check --doc-id {doc_id}",
        f"{cmd} ingest --doc-id {doc_id} --estimate-usd <예상 비용>",
        f"{cmd} link-guide --guide-id <가이드 id> --model-id {model_id}",
        f"{cmd} confirm --model-id {model_id} --questions <확인 질문 파일> --sha256 <기록한 해시> --label after --estimate-usd <예상 비용>",
        "예시 질문 화면 확인: 로컬 화면에서 예시 질문을 질문마다 새 대화로 묻고 답을 봄(판정하지 않음, 사람 단계)",
        f"사람 판정: measure/out/phase2/{model_id}-after-judge.csv의 verdict·borderline·worse_verdict·메모(설명서 원문 대조)",
        f"{cmd} verdict --judge measure/out/phase2/{model_id}-after-judge.csv",
        "합격이면 PR 병합(미달이면 models.json을 배포하지 않음, Global 4)",
        f"운영 화면에서 {model_id}가 보이는지 확인",
        "그 뒤에만 요청 상태를 \"추가됨\"으로(Supabase 표 화면)",
    ]
    return [f"{i}. {s}" for i, s in enumerate(steps, 1)]


# ── 명령 ──
def _ledger_rows(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return [{**r, "estimate_usd": float(r["estimate_usd"] or 0)} for r in csv.DictReader(f)]


def _doc(doc_id: str) -> dict:
    docs = {d["id"]: d for d in _load(DOCUMENTS)}
    if doc_id not in docs:
        raise SystemExit(f"documents.json에 없는 문서: {doc_id}")
    return docs[doc_id]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m ingest.add_model")
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd in ("check", "codes"):
        sub.add_parser(cmd).add_argument("--doc-id", required=True)
    d = sub.add_parser("draft")
    for arg in ("doc-id", "model-id", "brand", "appliance", "title", "source-url", "pdf", "codes", "fetched-at",
                "name", "scope-note", "model-name-hint"):
        d.add_argument(f"--{arg}", required=True)
    d.add_argument("--write", action="store_true", help="documents.json·models.json 끝에 덧붙인다")
    i = sub.add_parser("ingest")
    i.add_argument("--doc-id", required=True)
    i.add_argument("--estimate-usd", type=float, required=True, help="장부(evaluation/phase2/ledger.csv)에 적은 예상 비용")
    i.add_argument("--yes", action="store_true", help="이미 DB에 있는 문서를 지우고 다시 넣을 때(사용자 확인 뒤에만)")
    g = sub.add_parser("link-guide")
    g.add_argument("--guide-id", required=True)
    g.add_argument("--model-id", required=True)
    r = sub.add_parser("remove")
    r.add_argument("--doc-id", required=True)
    r.add_argument("--model-id", required=True)
    r.add_argument("--yes", action="store_true", help="사용자 확인 뒤에만")
    c = sub.add_parser("confirm")
    for arg in ("model-id", "questions", "sha256", "label"):
        c.add_argument(f"--{arg}", required=True)
    c.add_argument("--estimate-usd", type=float, required=True, help="장부에 적은 예상 비용")
    v = sub.add_parser("verdict")
    v.add_argument("--judge", required=True, help="사람이 판정을 채운 판정지 CSV")
    k = sub.add_parser("checklist")
    k.add_argument("--model-id", required=True)
    k.add_argument("--doc-id", default="<문서 id>")
    a = p.parse_args(argv)

    if a.cmd == "verdict":
        print("\n".join(verdict_lines(a.judge)))
        return
    if a.cmd == "checklist":
        print("\n".join(checklist_lines(a.model_id, a.doc_id)))
        return
    if a.cmd == "confirm":
        load_env()
        try:
            path = run_confirm(a.model_id, a.questions, expect_sha256=a.sha256, label=a.label, estimate_usd=a.estimate_usd)
        except ValueError as e:
            raise SystemExit(str(e)) from None
        print(f"결과 {path.relative_to(ROOT)} · 판정지 measure/out/phase2/{a.model_id}-{a.label}-judge.csv")
        return

    if a.cmd == "check":
        result = check_document(_doc(a.doc_id))
        print(json.dumps(result, ensure_ascii=False))
        if not result["ok"]:
            raise SystemExit(1)
    elif a.cmd == "codes":
        print("\n".join(error_code_candidates(_doc(a.doc_id))))
    elif a.cmd == "draft":
        doc, model = draft_entries(doc_id=a.doc_id, model_id=a.model_id, brand=a.brand, appliance=a.appliance,
                                   title=a.title, source_url=a.source_url, pdf=a.pdf,
                                   codes=[c.strip() for c in a.codes.split(",") if c.strip()], fetched_at=a.fetched_at,
                                   name=a.name, scope_note=a.scope_note, model_name_hint=a.model_name_hint)
        print(json.dumps({"document": doc, "model": model}, ensure_ascii=False, indent=2))
        if a.write:
            write_entries(doc, model)
    elif a.cmd == "ingest":
        from measure.budget import check_budget
        if a.estimate_usd <= 0 or not check_budget(_ledger_rows(LEDGER), a.estimate_usd, cap_usd=CAP_USD):
            raise SystemExit(f"장부 상한 {CAP_USD}달러를 넘거나 예상 비용이 없어 적재하지 않아요")
        load_env()
        try:
            print(json.dumps(ingest_manual(a.doc_id, yes=a.yes), ensure_ascii=False))
        except ValueError as e:
            raise SystemExit(str(e)) from None
    else:
        load_env()
        if a.cmd == "link-guide":
            print("새로 연결함" if link_guide(a.guide_id, a.model_id) else "이미 연결돼 있음")
        else:
            out = remove_model_data(a.doc_id, a.model_id, yes=a.yes)
            print(json.dumps(out, ensure_ascii=False))
            if not a.yes:
                print("지우지 않았어요. 개수를 확인하고 사용자 확인 뒤에 --yes를 붙여 다시 실행하세요")


if __name__ == "__main__":
    main()
