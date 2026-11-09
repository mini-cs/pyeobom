"""근거 관련성(Contextual Relevancy) 0.297 원인 조사 집계(조사 전용, 서비스 코드는 바꾸지 않음).

DeepEval 4.3.3의 근거 관련성 판정은 조각마다 여러 문장(statement)에 yes/no를 매기는 **문장 단위**다.
조각 안에 관련(yes) 문장이 하나라도 있으면 그 조각을 "관련 있음"으로 본다.
"""


def count_relevant_chunks(deepeval_record: dict) -> int:
    return sum(1 for chunk in deepeval_record["contextual_relevancy_verdicts"]
               if any(str(v["verdict"]).lower() == "yes" for v in chunk))


def _refs(text: str) -> list[str]:
    return [r for r in (text or "").split("|") if r]


def hit_rate(rows: list[dict]) -> float:
    """기대 근거가 인용 또는 검색 상위 5개에 있는 행의 비율(기대 근거가 없는 행은 제외)."""
    scored = [r for r in rows if _refs(r["expected_ref"])]
    hits = [r for r in scored
            if set(_refs(r["expected_ref"])) & (set(_refs(r["cited_refs"])) | set(_refs(r["retrieved_refs"])[:5]))]
    return len(hits) / len(scored) if scored else 0.0


def refs_by_content(conn, contents: list[str]) -> dict[str, str]:
    """조각 본문 → 근거 표기(manual:쪽 / guide:문서). 새 세트 결과 CSV에 검색 순위 열이 없어 저장된 본문으로 복원한다(조회만)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT c.content, d.doc_type, c.doc_id, c.page FROM chunks c JOIN documents d ON d.id = c.doc_id
                       WHERE c.content = ANY(%s)""", (list(set(contents)),))
        return {content: (f"manual:{page}" if doc_type == "manual" else f"guide:{doc_id}")
                for content, doc_type, doc_id, page in cur.fetchall()}


def main() -> None:
    """python -m measure.cr_investigation <새 세트 결과 CSV> <contexts JSON> <DeepEval 근거 관련성 기록 JSON...>"""
    import csv
    import json
    import statistics
    import sys

    from ingest.__main__ import load_env
    load_env()
    from app.core.db import get_conn

    csv_path, ctx_path, *verdict_paths = sys.argv[1:]
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    contexts = json.loads(open(ctx_path, encoding="utf-8").read())
    records = {r["id"]: r for p in verdict_paths for r in json.loads(open(p, encoding="utf-8").read())}
    with get_conn() as conn:
        ref_of = refs_by_content(conn, [c for cs in contexts.values() for c in cs])
    table = []
    for r in rows:
        key = f"{r['dialog_id']}-{r['turn']}"
        retrieved = [ref_of.get(c, "?") for c in contexts.get(key, [])]
        rec = records.get(key)
        table.append({"id": key, "type": r["type"], "first": r["turn"] == "1", "expected_ref": r["expected_ref"],
                      "cited_refs": r["cited_refs"], "retrieved_refs": "|".join(retrieved),
                      "relevant": count_relevant_chunks(rec) if rec else None, "cr": rec["contextual_relevancy"] if rec else None})
    for t in table:
        t["hit"] = hit_rate([t]) == 1.0 if [x for x in t["expected_ref"].split("|") if x] else None
        print(f"{t['id']}|{t['type']}|기대 {t['expected_ref'] or '-'}|인용 {t['cited_refs'] or '-'}|검색 {t['retrieved_refs']}|적중 {t['hit']}|관련 조각 {t['relevant']}|CR {t['cr']}")
    for name, group in (("1번째 턴", [t for t in table if t["first"]]), ("이어지는 턴", [t for t in table if not t["first"]])):
        rel = [t["relevant"] for t in group if t["relevant"] is not None]
        cr = [t["cr"] for t in group if t["cr"] is not None]
        print(name, {"턴": len(group), "관련 조각 수 채점 턴": len(rel), "중앙값": statistics.median(rel) if rel else None,
                     "평균": round(statistics.mean(rel), 2) if rel else None, "CR 평균": round(statistics.mean(cr), 3) if cr else None,
                     "적중률": round(hit_rate(group), 3), "적중 분모": sum(1 for t in group if t["hit"] is not None)})
    print("검색 조각 복원 실패(?):", sum(t["retrieved_refs"].count("?") for t in table))


if __name__ == "__main__":
    main()
