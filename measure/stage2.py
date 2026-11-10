"""검색 개선 2단계(계획 Task 7): 검색 방식만 다르게 해서 같은 실행 안에서 답변까지 돌려 비교한다.

사용법: python -m measure.stage2 evaluation/paraphrase_dev.csv --methods m0 m2 m12 --label stage2-pdev
- 답변 모델·프롬프트·진단 규칙은 운영 그대로(answer_question), 검색만 방법별(M0 운영, M2·조합은 실험 색인)
- 문장마다 방법 순서를 돌려 실행한다(시간대 차이가 한 방법에 몰리지 않게)
- 질문당 비용(답변 모델 토큰 × 단가)과 응답 시간(규칙으로 막힌 응답 제외)을 방법별로 집계한다
- 결과: evaluation/results/<label>-<날짜>.csv(+ .settings.json의 experiment에 검색 방식), 사람 판정 목록 measure/out/<label>-judgment.md
- 확인용 P 세트는 넣지 않는다(3단계 전까지 봉인)
"""
import argparse
import csv
import dataclasses
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICE_IN, PRICE_OUT = 0.10, 0.50  # 답변 모델 gpt-6-luna 1M 토큰당 달러(장부와 같은 단가). 임베딩은 방법마다 1회로 같아 뺌
COLUMNS = ["id", "card", "method", "type", "question", "expected_ref", "found", "answer", "cited_refs", "retrieved_refs",
           "diagnostic_added", "latency_ms", "llm_ms", "input_tokens", "output_tokens", "cost_usd", "rule_blocked", "error",
           "human_verdict"]


# 판정지에 적을 원문 확인(사실만, 사용자 요청 2026-11-10). 인용은 150자 이내
_C312 = ("가이드 조각 312(세탁통과 배수 호스 녹이기)에 \"세탁통에 50~60ºC 정도의 따뜻한 물을 부은 다음, 세탁기 문(도어)을 닫고 "
         "1~2시간 정도 배수펌프 내부가 녹기를 기다려주세요\"가 있음(붓는 곳은 세탁통). 조각 300에는 50~60℃·1~2시간 내용이 없음"
         "(수건 5분, 급수 호스는 50ºC 이하 물)")
BLIND_NOTES = {"p01-1": _C312, "p01-2": _C312}


def with_search(deps, search):
    return dataclasses.replace(deps, search=search)


def method_order(methods: list[str], i: int) -> list[str]:
    k = i % len(methods)
    return methods[k:] + methods[:k]


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return round((input_tokens * PRICE_IN + output_tokens * PRICE_OUT) / 1_000_000, 7)


def summarize_methods(rows: list[dict]) -> dict:
    out = {}
    for m in dict.fromkeys(r["method"] for r in rows):
        rs = [r for r in rows if r["method"] == m]
        lat = [r["latency_ms"] for r in rs if not r["rule_blocked"] and r["latency_ms"] is not None]
        out[m] = {"n": len(rs), "found": sum(1 for r in rs if r["found"]),
                  "latency_avg_ms": round(sum(lat) / len(lat)) if lat else 0,
                  "cost_per_q_usd": round(sum(r["cost_usd"] for r in rs) / len(rs), 7)}
    return out


def judgment_rows(rows: list[dict], methods: list[str]) -> list[dict]:
    """문장마다 방법별 답을 나란히. 앞 방법과 답이 글자까지 같으면 *_same_as에 그 방법(판정을 이어받음)"""
    out = []
    for qid in dict.fromkeys(r["id"] for r in rows):
        ans = {r["method"]: r["answer"] for r in rows if r["id"] == qid}
        j = {"id": qid} | {m: ans.get(m, "") for m in methods}
        for i, m in enumerate(methods[1:], 1):
            j[f"{m}_same_as"] = next((p for p in methods[:i] if ans.get(p) == ans.get(m)), "")
        out.append(j)
    return out


def blind_sheet(rows: list[dict], rng) -> tuple[list[dict], list[dict]]:
    """방법 이름을 가린 판정지: 문장마다 서로 다른 답만 섞어 무작위 번호를 붙인다. key는 (문장, 방법) → 번호(판정 후 공개)"""
    ids = list(dict.fromkeys(r["id"] for r in rows))
    uniq = {i: list(dict.fromkeys(r["answer"] for r in rows if r["id"] == i)) for i in ids}
    numbers = iter(rng.sample(range(100, 1000), sum(len(v) for v in uniq.values())))
    sheet, no_of = [], {}
    for i in ids:
        texts = uniq[i][:]
        rng.shuffle(texts)
        answers = [{"no": next(numbers), "text": t} for t in texts]
        no_of |= {(i, a["text"]): a["no"] for a in answers}
        sheet.append({"id": i, "answers": answers})
    return sheet, [{"id": r["id"], "method": r["method"], "no": no_of[(r["id"], r["answer"])]} for r in rows]


BLIND_HEADER = """# 2단계 사람 판정지 (방법 이름 가림, 2026-11-10)

판정 기준(측정 전 확정, 2026-11-10):
- 근거에 없는 조치가 섞이면 **환각**
- 근거는 있지만 질문 상황과 맞지 않으면 **오답**
- 핵심 조치 일부만 있으면 **정답**
- "설명서에 없다"고 했는데 실제로 있으면 **오답**
- 함정에 찾지 못함이면 **정답**(B 기준)

답 번호는 무작위이고 문장마다 순서를 섞었다. 글자까지 같은 답은 한 번만 적었다(같은 번호가 여러 방법의 답).
"찾지 못함" = "설명서에서 찾지 못했어요. 공식 고객센터에 문의해 보세요."
"""


def write_blind(result_csv: Path, notes: dict[str, str]) -> Path:
    import json
    import random

    with open(result_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    sheet, key = blind_sheet(rows, random.SystemRandom())
    first = {r["id"]: r for r in rows}
    lines = [BLIND_HEADER]
    for s in sheet:
        r = first[s["id"]]
        refs = r["expected_ref"].replace("manual:", "").replace("|", "·") or "-"
        lines += [f"## {s['id']}{' (함정)' if r['type'] == 'trap' else ''}", f"- 질문: {r['question']}", f"- 정답 쪽: {refs}"]
        if s["id"] in notes:
            lines.append(f"- 원문 확인(사실): {notes[s['id']]}")
        lines += [f"- **답 {a['no']}**: {a['text'].replace(chr(10), ' ')}  → 판정: " for a in s["answers"]] + [""]
    out = ROOT / "measure" / "out"
    (out / "stage2-blind-sheet.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "stage2-blind-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")  # 판정 후 공개
    return out / "stage2-blind-sheet.md"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--methods", nargs="+", default=["m0", "m2", "m12"])
    ap.add_argument("--label")
    ap.add_argument("--blind", action="store_true", help="cases 자리에 2단계 결과 CSV를 주면 방법 이름을 가린 판정지를 만든다")
    args = ap.parse_args()
    if args.blind:
        return print(write_blind(Path(args.cases), BLIND_NOTES))
    if not args.label:
        raise SystemExit("--label이 필요하다")
    if "test" in Path(args.cases).name:
        raise SystemExit("확인용 P 세트는 3단계 전까지 열지 않는다")

    from ingest.__main__ import load_env
    load_env()
    from app.ask.routes import get_deps
    from app.ask.service import answer_question
    from app.core.config import get_settings
    from app.core.db import get_conn
    from app.core.errors import AppError
    from app.retrieval.search import search_vector
    from evaluation.run_config import warn_if_different, write_settings
    from measure.search_eval import METHODS, method_fns, read_cases

    settings = get_settings()
    if warn_if_different(settings):
        raise SystemExit("운영 기본값과 다른 설정이라 멈춤")

    def variant_search(model_id, vec, text, k, variant):
        with get_conn() as conn:  # 운영 검색처럼 호출마다 접속(시간 비교를 같게)
            return search_vector(conn, model_id, vec, k, variant=variant)

    cases = read_cases(args.cases)
    rows = []
    for i, case in enumerate(cases):
        for m in method_order(args.methods, i):
            deps = get_deps()
            search, _ = method_fns(m, deps.search, variant_search, {})
            deps = with_search(deps, search)
            try:
                resp, err = answer_question(case["model_id"], case["question"], deps, settings, debug=True), ""
            except AppError as e:
                resp, err = {}, e.code
            inp, outp = deps.timings.get("input_tokens", 0), deps.timings.get("output_tokens", 0)
            rows.append({"id": case["id"], "card": case["card"], "method": m, "type": case["type"], "question": case["question"],
                         "expected_ref": case["expected_ref"], "found": resp.get("found"), "answer": resp.get("answer", err),
                         "cited_refs": "|".join(resp.get("cited_refs", [])), "retrieved_refs": "|".join(resp.get("retrieved_refs", [])),
                         "diagnostic_added": resp.get("diagnostic_added"), "latency_ms": resp.get("latency_ms"), "llm_ms": resp.get("llm_ms"),
                         "input_tokens": inp, "output_tokens": outp, "cost_usd": cost_usd(inp, outp),
                         "rule_blocked": bool(resp) and resp.get("embed_ms") == 0 and resp.get("llm_ms") == 0, "error": err,
                         "human_verdict": ""})
            print(case["id"], m, resp.get("found"), resp.get("latency_ms"), "|".join(resp.get("cited_refs", [])), err, flush=True)

    today = datetime.date.today().isoformat()
    out = ROOT / "evaluation" / "results" / f"{args.label}-{today}.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    summary = summarize_methods(rows)
    write_settings(out, settings, args.label, experiment={"search_methods": {m: METHODS[m] for m in args.methods},
                                                          "same_run": True, "summary": summary})
    lines = [f"# 2단계 사람 판정 목록 ({args.label}, {today})", "",
             "같은 문장의 답이 앞 방법과 글자까지 같으면 '같음'으로 표시(판정을 이어받음). 함정은 B 기준(지어내지 않고 없다고 밝히면 정답).", "",
             "| id | 질문 | " + " | ".join(args.methods) + " |", "|---|---|" + "---|" * len(args.methods)]
    by_id = {c["id"]: c for c in cases}
    for j in judgment_rows(rows, args.methods):
        cells = []
        for k, m in enumerate(args.methods):
            same = j.get(f"{m}_same_as") if k else ""
            cells.append(f"({same}와 같음)" if same else j[m].replace("\n", " ").replace("|", "/"))
        trap = " (함정)" if by_id[j["id"]]["type"] == "trap" else ""
        lines.append(f"| {j['id']}{trap} | {by_id[j['id']]['question']} | " + " | ".join(cells) + " |")
    (ROOT / "measure" / "out").mkdir(exist_ok=True)
    (ROOT / "measure" / "out" / f"{args.label}-judgment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary, "csv:", out.name)


if __name__ == "__main__":
    main()
