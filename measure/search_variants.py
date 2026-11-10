"""검색 개선 실험 색인 만들기(계획 2026-11-09-search-paraphrase-plan). 운영 표(chunks)는 읽기만 하고 chunk_variants에만 넣는다.

M1(Task 4): 조각 앞에 "모델 · 문서 제목 · 장 이름 · 쪽 소제목" 한 줄을 붙여 다시 임베딩한다.
- 장 이름: 쪽 첫 두 줄 중 쪽 번호가 붙은 머리글("사용하기 15", "16 사용하기"). 삼성은 머리글이 "18 한국어"라 그 위 줄이 장 이름
- 소제목: 머리글 다음 6줄 안의 첫 제목형 줄(2~30자, 글머리표·번호·주의 표시로 시작하지 않고, 문장처럼 끝나지 않음)
- 쪽의 첫 조각에서 뽑아 그 쪽의 모든 조각에 쓴다. 없으면 앞쪽 값을 이어받는다(장이 바뀌면 소제목은 이어받지 않음). 가이드는 모델·문서 제목만

사용법: python -m measure.search_variants m1            (미리보기: 쪽별 제목을 measure/out/에 쓰고 끝)
        python -m measure.search_variants m1 --apply    (임베딩해서 chunk_variants에 넣음. 이미 행이 있으면 멈춤 — 지우기는 사용자 확인)
        python -m measure.search_variants m2 --sample   (M2 시험 생성: 문서 5개에서 조각 1개씩, 결과는 measure/out/m2-sample.json, DB에 넣지 않음)
        python -m measure.search_variants m3 --draft    (M3 용어 사전 초안: 설명서마다 기능 이름 뽑기 → 평소 표현, 결과는 measure/out/m3-terms-draft.json)
        python -m measure.search_variants m3 --reduce   (규칙 ① 이름 종류 분류로 줄이기 + ③ 겹친 표현 지우기, 검토표 measure/out/m3-terms-reduced.md)
"""
import argparse
import csv
import json
import random
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
M2_PROMPT = (Path(__file__).resolve().parent / "prompts" / "m2_questions_v2.txt").read_text(encoding="utf-8")  # v1은 기록용
M2_FORMAT = {"type": "json_schema", "name": "questions", "strict": True,
             "schema": {"type": "object", "required": ["items"], "additionalProperties": False, "properties": {"items": {
                 "type": "array", "items": {"type": "object", "required": ["question", "evidence"], "additionalProperties": False,
                                            "properties": {"question": {"type": "string"}, "evidence": {"type": "string"}}}}}}}
_ASKS_NUMBER = re.compile(r"몇|며칠")
_SKIP_START = re.compile(r"^([•\-–※*·→]|\d|[a-z]\s|[①-⑳]|\(|주의|경고|참고|알아두기)")
_SENTENCE_END = re.compile(r"([.:?!]|요|다|[을를이가은는에의로와과고며서면])$")


def page_heading(page: int, text: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    section, start = None, 0
    for i, line in enumerate(lines[:2]):
        m = re.fullmatch(rf"{page}\s+(.+)|(.+?)\s+{page}", line)
        if m:
            name = (m[1] or m[2]).strip()
            section = (lines[0] if i == 1 else None) if name == "한국어" else name
            start = i + 1
            break
    sub = next((line for line in lines[start:start + 6] if 2 <= len(line) <= 30 and line != section
                and not _SKIP_START.match(line) and ". " not in line and not _SENTENCE_END.search(line)), None)
    return section, sub


def doc_headings(pages: list[tuple[int, str]]) -> dict[int, tuple[str | None, str | None]]:
    """(쪽, 그 쪽 첫 조각) → 쪽별 (장 이름, 소제목). 없는 값은 앞쪽에서 이어받는다"""
    out, prev = {}, (None, None)
    for page, text in sorted(pages):
        section, sub = page_heading(page, text)
        same_section = section in (None, prev[0])
        section = section or prev[0]
        sub = sub or (prev[1] if same_section else None)
        out[page] = prev = (section, sub)
    return out


def m1_text(model_names: list[str], doc_title: str, heading: tuple[str | None, str | None], content: str) -> str:
    return " · ".join([", ".join(model_names), doc_title, *[h for h in heading if h]]) + "\n" + content


def build_m1(conn, display_names: dict[str, str]) -> list[dict]:
    rows = conn.execute("""SELECT c.id, c.doc_id, d.title, c.page, c.content,
                                  (SELECT array_agg(model_id ORDER BY model_id) FROM document_models WHERE doc_id = c.doc_id)
                           FROM chunks c JOIN documents d ON d.id = c.doc_id ORDER BY c.doc_id, c.page, c.id""").fetchall()
    first_of_page = {}
    for cid, doc_id, _, page, content, _ in rows:
        if page is not None:
            first_of_page.setdefault((doc_id, page), content)
    headings = {}
    for doc_id in {d for d, _ in first_of_page}:
        for page, h in doc_headings([(p, t) for (d, p), t in first_of_page.items() if d == doc_id]).items():
            headings[(doc_id, page)] = h
    out = []
    for cid, doc_id, title, page, content, models in rows:
        text = m1_text([display_names[m] for m in models], title, headings.get((doc_id, page), (None, None)), content)
        out.append({"chunk_id": cid, "doc_id": doc_id, "page": page, "title": text.split("\n", 1)[0], "text": text})
    return out


def build_m2_messages(model_names: list[str], doc_title: str, page: int | None, content: str) -> list[dict]:
    body = content.replace("<", "〈").replace(">", "〉")  # 조각 안 꺾쇠로 구분 표시를 흉내 내지 못하게
    where = f"{page}쪽" if page is not None else "에러 가이드"
    return [{"role": "system", "content": M2_PROMPT},
            {"role": "user", "content": f"모델: {', '.join(model_names)}\n문서: {doc_title} ({where})\n<조각>\n{body}\n</조각>"}]


def check_items(items: list[dict], chunk: str, max_n: int = 5, max_len: int = 60) -> tuple[list[dict], list[dict]]:
    """근거 문장이 조각에 그대로 있는 질문만 남긴다(공백·줄바꿈 차이는 무시). 버린 질문은 이유와 함께 돌려준다"""
    flat = lambda t: " ".join(t.split())
    body, kept, dropped = flat(chunk), [], []
    for it in items:
        q, e = it["question"].strip(), flat(it["evidence"])
        reason = ("근거 없음" if not e else "근거가 조각에 없음" if e not in body
                  else "숫자를 묻는데 근거에 숫자 없음" if _ASKS_NUMBER.search(q) and not re.search(r"\d", e)
                  else "60자 초과" if not q or len(q) > max_len
                  else "중복" if q in {k["question"] for k in kept}
                  else "5개 초과" if len(kept) >= max_n else None)
        (dropped if reason else kept).append({"question": q, "evidence": e} | ({"reason": reason} if reason else {}))
    return kept, dropped


def sample_chunks(rows: list[dict], doc_ids: list[str], seed: int) -> list[dict]:
    """문서마다 조각 1개(시드 고정). 질문 품질을 훑어보는 시험 생성용"""
    rng = random.Random(seed)
    return [rng.choice([r for r in rows if r["doc_id"] == d]) for d in doc_ids]


# ── M3 용어 사전(Task 6): 설명서에서 기능 이름을 뽑고, 이름마다 평소 표현을 만든다(사용자 검토 전 초안) ──
M3_PROMPTS = {k: (Path(__file__).resolve().parent / "prompts" / f"m3_{k}_v1.txt").read_text(encoding="utf-8")
              for k in ("extract", "expand", "classify")}
M3_KINDS = ["기능", "관리 작업", "부품", "화면 표시", "일반어", "기타"]
M3_KEEP = {"기능", "관리 작업", "미분류"}  # 규칙 ①: 기능·코스·모드·관리 작업만(미분류는 사용자 검토로 남김)
M3_FORMATS = {
    "classify": {"type": "json_schema", "name": "kinds", "strict": True,
                 "schema": {"type": "object", "required": ["items"], "additionalProperties": False, "properties": {"items": {
                     "type": "array", "items": {"type": "object", "required": ["name", "kind"], "additionalProperties": False,
                                                "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": M3_KINDS}}}}}}},
    "extract": {"type": "json_schema", "name": "names", "strict": True,
                "schema": {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"}}},
                           "required": ["names"], "additionalProperties": False}},
    "expand": {"type": "json_schema", "name": "terms", "strict": True,
               "schema": {"type": "object", "required": ["terms"], "additionalProperties": False, "properties": {"terms": {
                   "type": "array", "items": {"type": "object", "required": ["name", "expressions"], "additionalProperties": False,
                                              "properties": {"name": {"type": "string"},
                                                             "expressions": {"type": "array", "items": {"type": "string"}}}}}}}},
}


def batch_texts(texts: list[str], max_chars: int) -> list[str]:
    batches, cur = [], []
    for t in texts:
        if cur and len("\n".join(cur + [t])) > max_chars:
            batches.append("\n".join(cur))
            cur = []
        cur.append(t)
    return batches + (["\n".join(cur)] if cur else [])


def merge_names(lists: list[list[str]]) -> list[str]:
    out = []
    for names in lists:
        for n in (x.strip() for x in names):
            if 2 <= len(n) <= 20 and n not in out:
                out.append(n)
    return out


def parse_terms(raw: str, names: list[str], max_n: int = 5) -> dict[str, list[str]]:
    """받은 이름마다 표현 목록(이름과 띄어쓰기만 다른 말·중복·2~12자 밖은 뺌). 목록 밖 이름은 버리고, 빠진 이름은 빈 목록"""
    got = {t["name"].strip(): t["expressions"] for t in json.loads(raw)["terms"]}
    out = {}
    for name in names:
        exprs = []
        for e in (x.strip() for x in got.get(name, [])):
            if 2 <= len(e) <= 12 and e.replace(" ", "") != name.replace(" ", "") and e not in exprs:
                exprs.append(e)
        out[name] = exprs[:max_n]
    return out


def parse_kinds(raw: str, names: list[str]) -> dict[str, str]:
    got = {it["name"].strip(): it["kind"] for it in json.loads(raw)["items"]}
    return {n: got.get(n, "미분류") for n in names}


def keep_by_kind(terms: dict[str, list[str]], kinds: dict[str, str]) -> tuple[dict, dict]:
    kept = {n: e for n, e in terms.items() if kinds.get(n, "미분류") in M3_KEEP}
    return kept, {n: kinds[n] for n in terms if n not in kept}


def drop_wide_expressions(terms: dict[str, list[str]], max_names: int = 2) -> tuple[dict, dict]:
    """규칙 ③: 같은 표현이 기능 이름 3개 이상에 붙으면 그 표현을 모두에서 지운다(2개 이하는 둔다)"""
    owners = {}
    for n, exprs in terms.items():
        for e in exprs:
            owners.setdefault(e, []).append(n)
    wide = {e: ns for e, ns in owners.items() if len(ns) > max_names}
    return {n: [e for e in exprs if e not in wide] for n, exprs in terms.items()}, wide


def build_m3_messages(kind: str, model_name: str, material: str) -> list[dict]:
    body = material.replace("<", "〈").replace(">", "〉")
    return [{"role": "system", "content": M3_PROMPTS[kind]},
            {"role": "user", "content": f"모델: {model_name}\n<자료>\n{body}\n</자료>"}]


def m3_draft(names: dict[str, str]) -> None:
    import openai

    from app.core.config import get_settings
    from app.core.db import get_conn

    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=1)
    usage = {"input_tokens": 0, "output_tokens": 0}

    def call(kind: str, model_name: str, material: str) -> str:
        resp = client.responses.create(model=settings.openai_chat_model, reasoning={"effort": settings.reasoning_effort},
                                       max_output_tokens=4000, text={"format": M3_FORMATS[kind]},
                                       input=build_m3_messages(kind, model_name, material))
        for k in usage:
            usage[k] += getattr(resp.usage, k)
        return resp.output_text

    with get_conn() as conn:
        manuals = conn.execute("""SELECT d.id, dm.model_id FROM documents d JOIN document_models dm ON dm.doc_id = d.id
                                  WHERE d.doc_type = 'manual' ORDER BY d.id""").fetchall()
        texts = {doc: [t for (t,) in conn.execute("SELECT content FROM chunks WHERE doc_id = %s ORDER BY page, id", (doc,))]
                 for doc, _ in manuals}
    draft = {}
    for doc, model_id in manuals:
        found = merge_names([json.loads(call("extract", names[model_id], b))["names"] for b in batch_texts(texts[doc], 8000)])
        terms = {}
        for i in range(0, len(found), 40):  # 이름 40개씩 표현 만들기
            terms |= parse_terms(call("expand", names[model_id], "\n".join(found[i:i + 40])), found[i:i + 40])
        draft[model_id] = terms
        print(model_id, "기능 이름", len(found), flush=True)
    OUT.mkdir(exist_ok=True)
    path = OUT / "m3-terms-draft.json"  # 사용자 검토 전 초안
    path.write_text(json.dumps({"model": settings.openai_chat_model, "usage": usage, "terms": draft},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{path} usage={usage}")


def m3_reduce(names: dict[str, str]) -> None:
    """초안(m3-terms-draft.json)의 이름을 AI로 종류 분류 → 규칙 ① 이름 줄이기 → 규칙 ③ 겹친 표현 지우기 → 검토용 표"""
    import openai

    from app.core.config import get_settings

    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=1)
    draft = json.loads((OUT / "m3-terms-draft.json").read_text(encoding="utf-8"))["terms"]
    usage, result, lines = {"input_tokens": 0, "output_tokens": 0}, {}, []
    for model_id, terms in draft.items():
        all_names, kinds = list(terms), {}
        for i in range(0, len(all_names), 60):  # 이름 60개씩 분류
            part = all_names[i:i + 60]
            resp = client.responses.create(model=settings.openai_chat_model, reasoning={"effort": settings.reasoning_effort},
                                           max_output_tokens=4000, text={"format": M3_FORMATS["classify"]},
                                           input=build_m3_messages("classify", names[model_id], "\n".join(part)))
            for k in usage:
                usage[k] += getattr(resp.usage, k)
            kinds |= parse_kinds(resp.output_text, part)
        kept, removed = keep_by_kind(terms, kinds)
        kept, wide = drop_wide_expressions(kept)
        result[model_id] = {"kept": kept, "kinds": {n: kinds[n] for n in kept}, "removed": removed, "wide_expressions": wide}
        print(model_id, "남김", len(kept), "지움", len(removed), "겹쳐서 지운 표현", len(wide), flush=True)
        lines += [f"\n## {names[model_id]} (`{model_id}`) — 남김 {len(kept)} / 지움 {len(removed)}\n",
                  "| 기능 이름 | 종류 | 표현 |", "|---|---|---|"]
        lines += [f"| {n} | {kinds[n]} | {' · '.join(e) or '-'} |" for n, e in kept.items()]
        if wide:
            lines += ["", "겹쳐서 지운 표현(이름 3개 이상): " + "; ".join(f"{e} ({', '.join(ns)})" for e, ns in wide.items())]
        lines += ["", "AI가 지운 이름: " + ", ".join(f"{n}({k})" for n, k in removed.items())]
    (OUT / "m3-terms-reduced.json").write_text(json.dumps({"usage": usage, "models": result}, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
    (OUT / "m3-terms-reduced.md").write_text("# M3 용어 사전 줄인 목록 (사용자 검토용)\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUT / 'm3-terms-reduced.md'} usage={usage}")


M2_SAMPLE_DOCS = ["manual-lg-fx25", "manual-samsung-wd90h25", "manual-lg-sq06fa1wds", "guide-lg-drum-errors", "guide-samsung-drum-5c"]
M2_SEED = 20261110


def m2_sample(names: dict[str, str]) -> None:
    import openai

    from app.core.config import get_settings
    from app.core.db import get_conn

    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key, timeout=30, max_retries=1)
    with get_conn() as conn:
        rows = build_m1(conn, names)
        models = dict(conn.execute("SELECT doc_id, array_agg(model_id ORDER BY model_id) FROM document_models GROUP BY doc_id").fetchall())
        titles = dict(conn.execute("SELECT id, title FROM documents").fetchall())
    out, usage = [], {"input_tokens": 0, "output_tokens": 0}
    for r in sample_chunks(rows, M2_SAMPLE_DOCS, M2_SEED):
        content = r["text"].split("\n", 1)[1]
        resp = client.responses.create(model=settings.openai_chat_model, reasoning={"effort": settings.reasoning_effort},
                                       max_output_tokens=1000, text={"format": M2_FORMAT},
                                       input=build_m2_messages([names[m] for m in models[r["doc_id"]]], titles[r["doc_id"]], r["page"], content))
        for k in usage:
            usage[k] += getattr(resp.usage, k)
        kept, dropped = check_items(json.loads(resp.output_text)["items"], content)
        out.append({"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "page": r["page"], "title": r["title"],
                    "chunk": content, "questions": kept, "dropped": dropped})
    OUT.mkdir(exist_ok=True)
    path = OUT / "m2-sample.json"  # 조각 본문이 들어 있어 저장소 밖에만 둔다
    path.write_text(json.dumps({"model": settings.openai_chat_model, "reasoning": settings.reasoning_effort,
                                "usage": usage, "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{path} usage={usage}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=["m1", "m2", "m3"])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--reduce", action="store_true")
    args = ap.parse_args()

    from ingest.__main__ import load_env
    load_env()
    from app.catalog.registry import load_models
    from app.core.db import get_conn
    from app.retrieval.embeddings import embed_texts

    names = {m["id"]: m["display_name"] for m in load_models()}
    if args.variant == "m2":
        return m2_sample(names) if args.sample else print("M2 전체 생성은 시험 생성 검토 후에 만든다")
    if args.variant == "m3":
        if args.reduce:
            return m3_reduce(names)
        return m3_draft(names) if args.draft else print("M3는 초안(--draft)·줄이기(--reduce)만. 사용자 검토 후 질문 넓히기 함수를 만든다")
    with get_conn() as conn:
        rows = build_m1(conn, names)
        OUT.mkdir(exist_ok=True)
        out = OUT / "m1-titles.csv"  # 제목만(본문 없음)
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["doc_id", "page", "title"])
            w.writerows(sorted({(r["doc_id"], r["page"] or 0, r["title"]) for r in rows}, key=lambda x: (x[0], x[1])))
        print(f"조각 {len(rows)}개, 쪽별 제목 {out}")
        if not args.apply:
            return
        if conn.execute("SELECT count(*) FROM chunk_variants WHERE variant = 'm1_title'").fetchone()[0]:
            raise SystemExit("m1_title 행이 이미 있어 멈춤(지우기는 사용자 확인 후)")
        vectors = embed_texts([r["text"] for r in rows])
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO chunk_variants (chunk_id, variant, text, embedding) VALUES (%s, 'm1_title', %s, %s::vector)",
                            [(r["chunk_id"], r["text"], v) for r, v in zip(rows, vectors)])
        print(f"m1_title {len(rows)}행 넣음")


if __name__ == "__main__":
    main()
