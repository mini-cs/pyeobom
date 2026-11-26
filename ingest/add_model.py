"""모델 추가 도구(2차 Task 8): python -m ingest.add_model <check|draft|codes|ingest|link-guide|remove> …

- 운영자 PC에서 돈다. 질문·답변 코드(app/ask·retrieval·answer)는 가져다 쓰기만 한다(Global 1).
- DB 연결은 DB 작업 직전에 열고 바로 닫는다. AI 호출·파일 처리 동안 쥐지 않는다(Global 8).
- 가이드는 다시 적재하지 않고 document_models에 한 줄만 넣는다(Global 9).
- remove --yes는 사용자 확인 뒤에만 붙인다(CLAUDE.md 데이터 삭제).
"""
import argparse
import csv
import json
import re
from pathlib import Path

from ingest.__main__ import ingest_document, load_env
from ingest.clean import clean_text
from ingest.load import ROOT
from ingest.page_marker import count_remaining_markers, strip_page_marker
from ingest.pdf import extract_pages

DOCUMENTS = ROOT / "data" / "documents.json"
MODELS = ROOT / "data" / "models.json"
LEDGER = ROOT / "evaluation" / "phase2" / "ledger.csv"
CAP_USD = 1.0  # 2차 장부 상한(Global 10)
MIN_CHARS = 30  # 공백을 뺀 글자가 이보다 적으면 글자 없는 쪽(Claude 판단)
APPLIANCES = ("washer", "dryer", "aircon")  # Global 5


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
    그 모델의 가이드 연결 행을 한 트랜잭션으로 지운다. bundle_chunks·다른 문서는 안 건드린다(설계 9.3-12)."""
    with connect() as conn, conn.cursor() as cur:
        def one(sql, params=()):
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else None

        doc_type = one("SELECT doc_type FROM documents WHERE id = %s", (doc_id,))
        if doc_type not in (None, "manual"):
            raise ValueError(f"설명서만 되돌려요(가이드는 지우지 않음, Global 9): {doc_id}")
        if doc_type and not one("SELECT count(*) FROM document_models WHERE doc_id = %s AND model_id = %s",
                                (doc_id, model_id)):
            raise ValueError(f"문서와 모델이 연결돼 있지 않아요: {doc_id} · {model_id}")
        has_bundle = one("SELECT to_regclass('bundle_chunks')") is not None
        out = {"doc_id": doc_id, "model_id": model_id, "documents": 1 if doc_type else 0,
               "chunks": one("SELECT count(*) FROM chunks WHERE doc_id = %s", (doc_id,)),
               "document_models": one("SELECT count(*) FROM document_models WHERE doc_id = %s", (doc_id,)),
               "guide_links": one("SELECT count(*) FROM document_models WHERE model_id = %s AND doc_id <> %s",
                                  (model_id, doc_id)),
               # 실험 조각이 이 문서를 참조하면 documents 행을 지울 수 없다(외래 키). 세기만 하고 건드리지 않는다
               "bundle_chunks": one("SELECT count(*) FROM bundle_chunks WHERE doc_id = %s", (doc_id,)) if has_bundle else 0,
               "deleted": False}
        if not yes:
            return out
        if out["bundle_chunks"]:
            raise ValueError(f"bundle_chunks에 이 문서 행이 {out['bundle_chunks']}개 있어 지우지 않아요(실험 조각은 따로 정리)")
        with conn.transaction():
            cur.execute("DELETE FROM document_models WHERE doc_id = %s OR model_id = %s", (doc_id, model_id))
            cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        return {**out, "deleted": True}


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
    g = sub.add_parser("link-guide")
    g.add_argument("--guide-id", required=True)
    g.add_argument("--model-id", required=True)
    r = sub.add_parser("remove")
    r.add_argument("--doc-id", required=True)
    r.add_argument("--model-id", required=True)
    r.add_argument("--yes", action="store_true", help="사용자 확인 뒤에만")
    a = p.parse_args(argv)

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
        print(json.dumps(ingest_document(a.doc_id), ensure_ascii=False))
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
