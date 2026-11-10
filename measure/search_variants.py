"""검색 개선 실험 색인 만들기(계획 2026-11-09-search-paraphrase-plan). 운영 표(chunks)는 읽기만 하고 chunk_variants에만 넣는다.

M1(Task 4): 조각 앞에 "모델 · 문서 제목 · 장 이름 · 쪽 소제목" 한 줄을 붙여 다시 임베딩한다.
- 장 이름: 쪽 첫 두 줄 중 쪽 번호가 붙은 머리글("사용하기 15", "16 사용하기"). 삼성은 머리글이 "18 한국어"라 그 위 줄이 장 이름
- 소제목: 머리글 다음 6줄 안의 첫 제목형 줄(2~30자, 글머리표·번호·주의 표시로 시작하지 않고, 문장처럼 끝나지 않음)
- 쪽의 첫 조각에서 뽑아 그 쪽의 모든 조각에 쓴다. 없으면 앞쪽 값을 이어받는다(장이 바뀌면 소제목은 이어받지 않음). 가이드는 모델·문서 제목만

사용법: python -m measure.search_variants m1            (미리보기: 쪽별 제목을 measure/out/에 쓰고 끝)
        python -m measure.search_variants m1 --apply    (임베딩해서 chunk_variants에 넣음. 이미 행이 있으면 멈춤 — 지우기는 사용자 확인)
        python -m measure.search_variants m2 --sample   (M2 시험 생성: 문서 5개에서 조각 1개씩, 결과는 measure/out/m2-sample.json, DB에 넣지 않음)
"""
import argparse
import csv
import json
import random
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
M2_PROMPT = (Path(__file__).resolve().parent / "prompts" / "m2_questions_v1.txt").read_text(encoding="utf-8")
M2_FORMAT = {"type": "json_schema", "name": "questions", "strict": True,
             "schema": {"type": "object", "properties": {"questions": {"type": "array", "items": {"type": "string"}}},
                        "required": ["questions"], "additionalProperties": False}}
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


def parse_questions(raw: str, max_n: int = 5, max_len: int = 60) -> list[str]:
    out = []
    for q in json.loads(raw)["questions"]:
        q = q.strip()
        if q and len(q) <= max_len and q not in out:
            out.append(q)
    return out[:max_n]


def sample_chunks(rows: list[dict], doc_ids: list[str], seed: int) -> list[dict]:
    """문서마다 조각 1개(시드 고정). 질문 품질을 훑어보는 시험 생성용"""
    rng = random.Random(seed)
    return [rng.choice([r for r in rows if r["doc_id"] == d]) for d in doc_ids]


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
                                       max_output_tokens=600, text={"format": M2_FORMAT},
                                       input=build_m2_messages([names[m] for m in models[r["doc_id"]]], titles[r["doc_id"]], r["page"], content))
        for k in usage:
            usage[k] += getattr(resp.usage, k)
        out.append({"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "page": r["page"], "title": r["title"],
                    "chunk": content, "questions": parse_questions(resp.output_text)})
    OUT.mkdir(exist_ok=True)
    path = OUT / "m2-sample.json"  # 조각 본문이 들어 있어 저장소 밖에만 둔다
    path.write_text(json.dumps({"model": settings.openai_chat_model, "reasoning": settings.reasoning_effort,
                                "usage": usage, "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{path} usage={usage}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=["m1", "m2"])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()

    from ingest.__main__ import load_env
    load_env()
    from app.catalog.registry import load_models
    from app.core.db import get_conn
    from app.retrieval.embeddings import embed_texts

    names = {m["id"]: m["display_name"] for m in load_models()}
    if args.variant == "m2":
        return m2_sample(names) if args.sample else print("M2 전체 생성은 시험 생성 검토 후에 만든다")
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
