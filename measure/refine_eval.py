"""첫 질문 다듬기(v1.96) 측정: 0단계 미리 보기, 1단계 검색만(운영·후보 한 실행), 3단계 시간·비용 판정.

설계 `docs/superpowers/specs/2026-11-23-first-question-refine-design.md` 6절, 계획 Task 2.
CLI: python -m measure.refine_eval preview | stage1 [--out 폴더] | report <r1 CSV> <r2 CSV>
- 후보는 운영 코드(refine_question·search_vectors)에 다듬기 모델만 끼운다. 운영 설정(REFINE_MODEL 비어 있음)으로만 돈다
- 원자료는 measure/out/refine/(git 밖). 확인용 세트는 열지 않는다
"""
import csv
import dataclasses
import hashlib
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from app.answer.refine import PROMPT_SHA256, RefineResult, refine_question
from app.core.brand_guard import guard_message
from app.input_guard.pii import mask_pii
from app.retrieval.search import needs_diagnostic
from measure.retrieval_probe import expected_rank
from measure.stage2 import ROOT, cost_usd, paired_latency, parse_result_row, summarize_methods

METHOD = "q_refine"
CANDIDATE_MODEL = "gpt-6-luna"
OUT = ROOT / "measure" / "out" / "refine"
PREVIEW = ROOT / "measure" / "refine_preview.csv"
PREVIEW_SHA256 = "10af0c4f2901cf4d4ca7c8b1ea213f75c60e9d5416971be3535af0c9cc70021c"  # 측정 전 고정(결정기록 039)
LIMIT_MS = 1500  # B-2 응답 시간(사용자 결정 +1.5초)이자 0단계 멈춤 기준
USAGE = "사용법: python -m measure.refine_eval preview | stage1 [--out 폴더] | report <r1 CSV> <r2 CSV>"


def candidate_refine(models: dict[str, dict], settings) -> Callable[[str, str], RefineResult]:
    """운영 get_deps와 같은 연결에 다듬기 모델만 후보로(추론·시간 제한·토큰은 설정의 운영 기본값)."""
    return lambda q, m: refine_question(q, models[m]["name"], CANDIDATE_MODEL, settings)


def with_candidate(deps, models: dict[str, dict], settings):
    return dataclasses.replace(deps, refine=candidate_refine(models, settings))


def code_tokens(text: str) -> list[str]:
    """에러 코드·숫자·영문 모델명 후보. 가린 개인정보 자리(*가 든 말·[이메일])는 뺀다."""
    return list(dict.fromkeys(re.findall(r"[0-9A-Za-z]+", re.sub(r"\S*\*\S*|\[[^\]]*\]", " ", text))))


def missing_tokens(question: str, refined: str) -> list[str]:
    return [t for t in code_tokens(question) if t.lower() not in refined.lower()]


def new_tokens(question: str, refined: str) -> list[str]:
    return [t for t in code_tokens(refined) if t.lower() not in question.lower()]


def run_preview(cases: list[dict], refine: Callable[[str, str], RefineResult], *,
                timer: Callable[[], float] = time.perf_counter) -> tuple[dict, list[dict]]:
    """문장마다 가린 질문을 한 번 다듬는다(다시 돌리지 않음). (요약, 행)"""
    rows = []
    for c in cases:
        q = mask_pii(c["question"])[0]
        t = timer()
        r = refine(q, c["model_id"])
        ms = round((timer() - t) * 1000)
        rows.append({"id": c["id"], "model_id": c["model_id"], "question_masked": q, "refined": r.text if r.used else "",
                     "reason": r.reason, "refine_ms": ms, "missing": missing_tokens(q, r.text), "new": new_tokens(q, r.text),
                     "input_tokens": r.usage.get("input_tokens", 0), "output_tokens": r.usage.get("output_tokens", 0)})
    ms = [r["refine_ms"] for r in rows]
    tin, tout = sum(r["input_tokens"] for r in rows), sum(r["output_tokens"] for r in rows)
    summary = {"n": len(rows), "reasons": dict(Counter(r["reason"] for r in rows)),
               "missing": {r["id"]: r["missing"] for r in rows if r["missing"]},
               "new": {r["id"]: r["new"] for r in rows if r["new"]},
               "refine_ms_avg": round(sum(ms) / len(ms)) if ms else 0, "refine_ms_max": max(ms, default=0),
               "input_tokens": tin, "output_tokens": tout, "cost_usd": cost_usd(tin, tout)}
    summary["stop"] = (["missing_tokens"] if summary["missing"] else []) + (
        ["refine_avg_over_1500ms"] if summary["refine_ms_avg"] > LIMIT_MS else [])
    return summary, rows


def refine_rows(cases: list[dict], refine: Callable, embed: Callable, embed_queries: Callable, search: Callable,
                search_queries: Callable, diagnostic: Callable, *, brand: Callable[[str], str], top_k: int = 5,
                depth: int = 100) -> list[dict]:
    """run_eval과 같은 행 + 다듬기 열. 문장마다 다듬기 1회. 다듬은 문장이 쓰이면 두 질문 검색, 아니면 운영과 같은 검색.
    다듬은 문장이 다른 브랜드 검사에 걸리면 운영 서비스처럼 버린다(guard_message). 진단 판단은 원래 질문."""
    rows = []
    for c in cases:
        refs = [r for r in c["expected_ref"].split("|") if r]
        if not refs:
            continue
        query = mask_pii(c["question"])[0]
        t = time.perf_counter()
        r = refine(query, c["model_id"])
        refine_ms = round((time.perf_counter() - t) * 1000)
        if r.used and guard_message(r.text, brand(c["model_id"])):
            r = RefineResult(query, False, "other_brand", r.usage)
        if r.used:
            chunks = search_queries(c["model_id"], embed_queries([query, r.text]), depth)
        else:
            chunks = search(c["model_id"], embed(query), query, depth)
        top = chunks[:top_k]
        extra = [d for d in diagnostic(c["model_id"]) if d.id not in {x.id for x in top}] if needs_diagnostic(query, top) else []
        diag = [d.ref for d in extra]
        rank = expected_rank(chunks, refs, depth)
        rows.append({"id": c["id"], "model_id": c["model_id"], "expected_ref": c["expected_ref"], "rank": rank,
                     "top5": "|".join(x.ref for x in top), "diag": "|".join(diag),
                     "top5_ids": "|".join(str(x.id) for x in top), "diag_ids": "|".join(str(d.id) for d in extra),
                     "hit5_or_diag": bool(rank and rank <= top_k) or any(x in diag for x in refs),
                     "refined": r.text if r.used else "", "refine_reason": r.reason, "refine_ms": refine_ms,
                     "input_tokens": r.usage.get("input_tokens", 0), "output_tokens": r.usage.get("output_tokens", 0)})
    return rows


def measure_stage1(out_name: str = "stage1") -> dict:
    """운영(measure_sets, 1~20위를 fable-stage1과 대조)과 후보(refine_rows)를 한 실행 안에서 잰다."""
    from ingest.__main__ import load_env
    load_env()
    from app.ask.routes import get_deps
    from app.catalog.registry import load_models
    from app.core.config import get_settings
    from evaluation.run_config import warn_if_different, write_settings
    from measure.emb_large import _production_rank_mismatches, rank_buckets
    from measure.fable_split import b1_pass
    from measure.search_eval import read_cases
    from measure.v17_stage1 import SETS, guard_cases_path, measure_sets

    settings = get_settings()
    if warn_if_different(settings):
        raise SystemExit("운영 기본값과 다른 설정이라 멈춤")
    if settings.search_mode != "vector":
        raise SystemExit("벡터 검색(search_mode=vector)에서만 써서 멈춤")
    for p in SETS.values():
        guard_cases_path(p)
    models = {m["id"]: m for m in load_models()}
    deps = get_deps()
    cases = {k: read_cases(ROOT / p) for k, p in SETS.items()}
    summary, rows = measure_sets(cases, [None], deps.embed_query, lambda b: (deps.search, deps.diagnostic),
                                 top_k=settings.top_k, depth=100)
    if bad := _production_rank_mismatches(rows):
        raise SystemExit(f"운영 벌 1~20위가 2026-11-20 1단계와 달라 멈춤: {bad}")
    refine = candidate_refine(models, settings)
    for set_name, cs in cases.items():
        r = refine_rows(cs, refine, deps.embed_query, deps.embed_queries, deps.search, deps.search_queries, deps.diagnostic,
                        brand=deps.brand, top_k=settings.top_k, depth=100)
        rows[(set_name, METHOD)] = r
        summary[set_name][METHOD] = {"hit5": sum(bool(x["rank"] and x["rank"] <= settings.top_k) for x in r),
                                     "denominator": len(r), "hit5_or_diag": sum(x["hit5_or_diag"] for x in r)}
    summary["b1_pass"] = b1_pass(summary, METHOD)
    out = OUT / out_name
    out.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, dict] = {}
    experiment = {"method": METHOD, "model": CANDIDATE_MODEL, "prompt_sha256": PROMPT_SHA256, "depth": 100}
    for (set_name, b), r in rows.items():
        name = b or "production"
        path = out / f"{set_name}-{name}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(r[0]))
            w.writeheader()
            w.writerows(r)
        write_settings(path, settings, f"refine-{out_name}-{set_name}", experiment=experiment | {"set": set_name, "bundle": name})
        buckets.setdefault(set_name, {})[name] = rank_buckets([x["rank"] for x in r])
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "buckets.json").write_text(json.dumps(buckets, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def latency_b2(rows: list[dict], base: str = "m0", cand: str = METHOD, limit_ms: int = LIMIT_MS) -> dict:
    """B-2 응답 시간(설계 6절): 두 회차를 합친 전체 답 평균 차이(후보 − 운영) ≤ limit_ms. 쌍 차이는 기록용."""
    p = paired_latency(rows, base, cand)
    return p | {"basis": "all", "diff_ms": p["all_diff_ms"], "pass": p["all_diff_ms"] is not None and p["all_diff_ms"] <= limit_ms}


def stage3_report(paths: list[Path]) -> dict:
    if len({p.stem for p in paths}) != len(paths):  # 회차(run)를 파일 이름으로 가르므로 같으면 회차가 합쳐진다
        raise SystemExit("회차 CSV 이름이 같아 멈춤(파일 이름이 회차 이름)")
    rows = []
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows += [parse_result_row(r) | {"run": p.stem} for r in csv.DictReader(f)]

    def per_q(method):
        costs = [r["cost_usd"] for r in rows if r["method"] == method]
        return sum(costs) / len(costs)
    cand = [r for r in rows if r["method"] == METHOD]
    ms = [float(r["refine_ms"]) for r in cand if r.get("refine_ms") not in (None, "")]
    return {"summary": summarize_methods(rows), "latency": latency_b2(rows), "cost_ratio": per_q(METHOD) / per_q("m0"),
            "refine": {"ms_avg": round(sum(ms) / len(ms)) if ms else None,
                       "reasons": dict(Counter(r.get("refine_reason") or "" for r in cand))}}


def _preview() -> None:
    if hashlib.sha256(PREVIEW.read_bytes()).hexdigest() != PREVIEW_SHA256:
        raise SystemExit("미리 보기 문장 파일이 고정한 해시와 달라 멈춤")
    from ingest.__main__ import load_env
    load_env()
    from app.catalog.registry import load_models
    from app.core.config import get_settings
    from evaluation.run_config import warn_if_different
    from measure.search_eval import read_cases

    settings = get_settings()
    if warn_if_different(settings):
        raise SystemExit("운영 기본값과 다른 설정이라 멈춤")
    models = {m["id"]: m for m in load_models()}
    summary, rows = run_preview(read_cases(PREVIEW), candidate_refine(models, settings))
    OUT.mkdir(parents=True, exist_ok=True)
    cell = lambda v: (", ".join(v) if isinstance(v, list) else str(v)).replace("|", "/")
    lines = [f"# 첫 질문 다듬기 0단계 미리 보기 (모델 {CANDIDATE_MODEL}, 요청문 {PROMPT_SHA256[:8]}…, 평가 세트 아님)", "",
             "| id | 가린 질문 | 다듬은 문장 | 이유 | ms | 빠진 토큰 | 새 토큰 |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {cell(r['question_masked'])} | {cell(r['refined'])} | {r['reason']} | {r['refine_ms']} | "
              f"{cell(r['missing'])} | {cell(r['new'])} |" for r in rows]
    lines += ["", "```json", json.dumps(summary, ensure_ascii=False, indent=1), "```"]
    (OUT / "preview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    args = sys.argv[1:]
    if args == ["preview"]:
        return _preview()
    if args[:1] == ["stage1"]:
        out = args[2] if args[1:2] == ["--out"] and len(args) == 3 else "stage1" if len(args) == 1 else None
        if out is None:
            raise SystemExit(USAGE)
        return print(json.dumps(measure_stage1(out), ensure_ascii=False))
    if args[:1] == ["report"] and len(args) == 3:
        return print(json.dumps(stage3_report([Path(a) for a in args[1:]]), ensure_ascii=False, indent=1))
    raise SystemExit(USAGE)


if __name__ == "__main__":
    main()
