"""v1.97 임베딩 large 다시 해 보기: 4단계(확인용 세트 + 30문항 + 이어지는 질문) 코드.

설계 `docs/superpowers/specs/2026-11-23-embedding-large-retry-design.md` 6·11절, 계획 Task 1.
CLI: python -m measure.emb_retry open <commit> | search-test --test-set <path> | followups --label <label>
     | time-summary <결과 CSV들> | blind-regression --label <label> --date <날짜>
- 확인용 세트는 열기 파일(결정기록 041 커밋 해시)이 있을 때만 읽는다
- 화면에는 파일 경로와 시간 숫자만 찍는다(시간 선을 커밋하기 전에 찾은 수·5위 안·답이 보이지 않게, 설계 5-2의 2)
"""
import csv
import datetime
import hashlib
import io
import json
import math
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from evaluation.followups import run_dialog
from measure.stage2 import cost_usd, method_order, parse_result_row

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out" / "emb-retry"
OPEN_FILE = OUT / "stage4-open.json"
BACKUP = ROOT / "measure" / "out" / "v17-rollout-backup" / "chunks-manual.jsonl"
BACKUP_SHA256 = "ba8433aa9fce8ea6d5c5b1e1004801215c745c9074ad5e9c0a790d373e85bbcb"
BASE, CAND = "m0", "emb_large"
FU_COLUMNS = ["dialog_id", "turn", "type", "model_id", "method", "question", "expected_ref", "expected_found", "found", "answer",
              "cited_refs", "retrieved_refs", "retrieved_chunk_ids", "rewritten_question", "rewrite_ms", "latency_ms", "llm_ms",
              "input_tokens", "output_tokens", "cost_usd", "rule_blocked", "error", "human_verdict"]
ADR041 = "docs/결정기록/041-임베딩-large-다시-측정-전-결정.md"
LABELS = {"정답", "정답(경계)", "오답", "오답(경계)", "환각", "환각(경계)"}  # ⑰이 받는 판정 이름(사용자 결정)
RESULT_SETS = {(s, r) for s in ("test", "q30", "fu") for r in ("r1", "r2")}  # 시간·비용을 세는 범위(설계 5-3의 1)
RESULT_NAME = re.compile(r"emb-retry-(test|q30|fu)-(r\d+)-\d{4}-\d{2}-\d{2}\.csv")


# ── 4단계 열기 파일 ──
def _full_commit(commit: str, repo: Path) -> str:
    """저장소에 있는 커밋이면 40자 해시, 없으면 멈춤."""
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"저장소 기록에 없는 커밋이라 멈춤: {commit}")
    return r.stdout.strip()


def _require_041(full: str, repo: Path) -> None:
    """그 커밋에 결정기록 041이 들어 있어야 한다(041 앞 커밋으로 확인용을 열지 않게)."""
    if subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{full}:{ADR041}"], capture_output=True).returncode != 0:
        raise SystemExit(f"그 커밋에 결정기록 041이 없어 멈춤: {full}")


def write_open_file(commit: str, path: Path = OPEN_FILE) -> Path:
    if path.exists():
        raise SystemExit(f"열기 파일이 이미 있어 멈춤(덮어쓰지 않음): {path}")
    full = _full_commit(commit, ROOT)
    _require_041(full, ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump({"decision_record": "041", "commit": full,
                   "written_at": datetime.datetime.now().isoformat(timespec="seconds")}, f, ensure_ascii=False)
    return path


def require_open_file(path: Path = OPEN_FILE, *, repo: Path = ROOT) -> dict:
    """확인용 세트를 읽기 전 관문: 파일이 있고, 041 커밋이 저장소에 있고 HEAD의 조상일 때만 통과."""
    if not path.exists():
        raise SystemExit(f"4단계 열기 파일이 없어 확인용 세트를 열지 않음: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("decision_record") != "041":
        raise SystemExit("열기 파일의 결정기록이 041이 아니라 멈춤")
    commit = str(data.get("commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit(f"열기 파일의 커밋이 40자 해시가 아니라 멈춤: {commit}")
    full = _full_commit(commit, repo)
    _require_041(full, repo)
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", full, "HEAD"]).returncode != 0:
        raise SystemExit(f"열기 파일의 커밋이 HEAD의 조상이 아니라 멈춤: {full}")
    return data


# ── 옛 조각 번호 → 쪽(결정기록 033, 설계 6절 준비 2) ──
def load_backup_pages(path: Path = BACKUP, sha256: str = BACKUP_SHA256) -> dict[int, tuple[str, int]]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise SystemExit(f"백업 파일 해시가 달라 멈춤: {path.name}")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    return {r["id"]: (r["doc_id"], r["page"]) for r in rows}


def old_chunk_refs_to_pages(refs: str, backup: dict[int, tuple[str, int]]) -> tuple[str, int]:
    """chunk:<1~297>(옛 설명서 조각)만 manual:<쪽>으로. 가이드 번호(298~335)·manual:·guide:는 그대로. 겹치면 처음 것만.
    그 밖의 chunk: 글(0, 336 이상, 숫자가 아닌 것)과 백업에 없는 번호는 멈춘다."""
    out, converted = [], 0
    for ref in (r.strip() for r in refs.split("|") if r.strip()):
        if ref.startswith("chunk:"):
            m = re.fullmatch(r"chunk:(\d+)", ref)
            if not m or not 1 <= int(m[1]) <= 335:
                raise SystemExit(f"옛 설명서(1~297)·가이드(298~335) 밖의 조각 번호라 멈춤: {ref}")
            if int(m[1]) <= 297:
                if int(m[1]) not in backup:
                    raise SystemExit(f"백업에 없는 옛 조각 번호라 멈춤: {ref}")
                ref, converted = f"manual:{backup[int(m[1])][1]}", converted + 1
        if ref not in out:
            out.append(ref)
    return "|".join(out), converted


def build_test_set(sealed: Path, new_rows: list[dict], split_json: Path, backup: dict, out: Path, *,
                   open_file: Path = OPEN_FILE, repo: Path = ROOT) -> dict:
    """봉인된 지난 문장(해시 확인) + 새 문장을 합치고 기대 근거의 옛 조각 번호를 쪽으로 바꿔 out에 쓴다(설계 6절 준비 4·5).
    열기 파일이 있어야 하고, id가 겹치거나 함정·기대 근거가 맞지 않으면(함정에 근거 있음, 함정 아닌데 근거 없음) 멈춘다."""
    require_open_file(open_file, repo=repo)
    if out.exists():
        raise SystemExit(f"합친 확인용 파일이 이미 있어 멈춤: {out}")
    raw = sealed.read_bytes()
    if hashlib.sha256(raw).hexdigest() != json.loads(split_json.read_text(encoding="utf-8"))["test_sha256"]:
        raise SystemExit("봉인된 확인용 파일 해시가 paraphrase_split.json과 달라 멈춤")
    lines = raw.decode("utf-8-sig").splitlines(keepends=True)
    comments = [line for line in lines if line.startswith("#")]
    reader = csv.DictReader(line for line in lines if not line.startswith("#"))
    rows = list(reader)
    if bad := [r.get("id") for r in new_rows if list(r) != reader.fieldnames]:
        raise SystemExit(f"새 문장의 열이 봉인 파일과 달라 멈춤: {bad}")
    ids = [r["id"] for r in rows + new_rows]
    if dup := sorted({i for i in ids if ids.count(i) > 1}):
        raise SystemExit(f"id가 겹쳐 멈춤: {dup}")
    merged, converted_rows = [], 0
    for r in rows + new_rows:
        ref, n = old_chunk_refs_to_pages(r["expected_ref"], backup)
        merged.append(r | {"expected_ref": ref})
        converted_rows += n > 0
    # 검색은 기대 근거가 빈 행만 함정으로 빼므로(run_eval), 함정 여부와 근거 유무가 어긋나면 5위 안 분모가 틀어진다
    if bad := [r["id"] for r in merged if r["type"].startswith("trap") == bool(r["expected_ref"])]:
        raise SystemExit(f"함정인데 기대 근거가 있거나, 함정이 아닌데 기대 근거가 없어 멈춤: {bad}")
    buf = io.StringIO()
    buf.writelines(c.rstrip("\r\n") + "\n" for c in comments)
    w = csv.DictWriter(buf, fieldnames=reader.fieldnames, lineterminator="\n")
    w.writeheader()
    w.writerows(merged)
    data = buf.getvalue().encode("utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("xb") as f:
        f.write(data)
    return {"rows": len(merged), "sha256": hashlib.sha256(data).hexdigest(), "converted_rows": converted_rows}


# ── 이어지는 질문: 같은 실행 안에서 방법 번갈아 ──
def run_followups_same_run(methods: list[str], label: str, *, client_for: Callable[[str], Callable],
                           rows: list[dict]) -> list[dict]:
    """대화 i마다 method_order(methods, i) 순서로, 방법마다 대화 전체를 그 방법의 client로 돈다(앞 대화는 그 방법의 답만).

    client(model_id, question, history) → answer_question(debug) 응답 + 답변 토큰(input_tokens·output_tokens)과
    질문 바꾸기 토큰(rewrite_input_tokens·rewrite_output_tokens), 오류면 {"error_code": …}. label은 결과 파일 이름용(CLI)."""
    dialogs: dict[str, list[dict]] = {}
    for row in rows:
        dialogs.setdefault(row["dialog_id"], []).append(row)
    out = []
    for i, turns in enumerate(dialogs.values()):
        for m in method_order(methods, i):
            client, resps = client_for(m), []
            results = run_dialog(turns, lambda mid, q, h: resps.append(client(mid, q, h)) or resps[-1])
            for t, r, resp in zip(turns, results, resps, strict=True):
                inp = sum(resp.get(k, 0) for k in ("input_tokens", "rewrite_input_tokens", "refine_input_tokens"))
                outp = sum(resp.get(k, 0) for k in ("output_tokens", "rewrite_output_tokens", "refine_output_tokens"))
                out.append({k: t.get(k, "") for k in ("dialog_id", "turn", "type", "model_id")} | {
                    "method": m, "question": t["question"], "expected_ref": t["expected_ref"],
                    "expected_found": t["expected_found"], "found": r.found, "answer": r.answer,
                    "cited_refs": "|".join(r.cited_refs), "retrieved_refs": "|".join(r.retrieved_refs),
                    "retrieved_chunk_ids": "|".join(map(str, r.retrieved_chunk_ids)),
                    "rewritten_question": r.rewritten_question or "", "rewrite_ms": r.rewrite_ms, "latency_ms": r.ms,
                    "llm_ms": resp.get("llm_ms"), "input_tokens": inp, "output_tokens": outp, "cost_usd": cost_usd(inp, outp),
                    "rule_blocked": not r.error and resp.get("embed_ms") == 0 and resp.get("llm_ms") == 0,
                    "error": r.error, "human_verdict": ""})
    return out


# ── 시간·비용 집계(설계 5-2의 1, 5-3의 1·2) ──
def _num(v):
    return None if v is None or v == "" else float(v)


def _mean(xs):
    return round(sum(xs) / len(xs), 1) if xs else None


def _diff(a, b):
    return None if a is None or b is None else round(b - a, 1)


def _time_stats(rows: list[dict], base: str, cand: str) -> dict:
    lat = {base: [], cand: []}
    non_llm = {base: [], cand: []}
    role = {base: "base", cand: "cand"}
    excluded = {k: {"error": 0, "rule_blocked": 0, "no_latency": 0} for k in role.values()}
    for r in rows:
        p = parse_result_row(r)
        if p["method"] not in lat:
            continue
        why = ("error" if str(r.get("error") or "") else "rule_blocked" if p["rule_blocked"]
               else "no_latency" if p["latency_ms"] is None else None)
        if why:
            excluded[role[p["method"]]][why] += 1
            continue
        lat[p["method"]].append(p["latency_ms"])
        if (llm := _num(r.get("llm_ms"))) is not None:
            non_llm[p["method"]].append(p["latency_ms"] - llm)
    b, c, bn, cn = _mean(lat[base]), _mean(lat[cand]), _mean(non_llm[base]), _mean(non_llm[cand])
    return {"n": {"base": len(lat[base]), "cand": len(lat[cand])}, "base_ms": b, "cand_ms": c, "diff_ms": _diff(b, c),
            "base_non_llm_ms": bn, "cand_non_llm_ms": cn, "diff_non_llm_ms": _diff(bn, cn), "excluded": excluded}


def time_summary(rows_by_set: dict[str, list[dict]], base: str = BASE, cand: str = CAND) -> dict:
    """세트별과 pooled(모든 행을 합친 평균), 회차별과 all. 오류·규칙으로 막힌 행·시간 빈 행은 뺀다. 찾은 수·적중은 넣지 않는다."""
    scopes = dict(rows_by_set) | {"pooled": [r for rows in rows_by_set.values() for r in rows]}
    runs = sorted({r.get("run") for rows in rows_by_set.values() for r in rows} - {None})
    return {name: {run: _time_stats([r for r in rows if r.get("run") == run], base, cand) for run in runs}
            | {"all": _time_stats(rows, base, cand)} for name, rows in scopes.items()}


def _cost_ratio(rows: list[dict], base: str, cand: str) -> float | None:
    per_q = {}
    for m in (base, cand):
        costs = [parse_result_row(r)["cost_usd"] for r in rows if r["method"] == m]
        per_q[m] = sum(costs) / len(costs) if costs else None
    return round(per_q[cand] / per_q[base], 4) if per_q[base] and per_q[cand] is not None else None


def cost_summary(rows_by_set: dict[str, list[dict]], base: str = BASE, cand: str = CAND) -> dict:
    """ratio = 후보 질문당 비용 ÷ 운영(두 회차 합침). 오류 행이 있으면 오류 행을 뺀 비율도(결정기록 039 덧붙임 1)."""
    scopes = dict(rows_by_set) | {"pooled": [r for rows in rows_by_set.values() for r in rows]}
    out = {}
    for name, rows in scopes.items():
        out[name] = {"ratio": _cost_ratio(rows, base, cand)}
        if any(str(r.get("error") or "") for r in rows):
            out[name]["ratio_without_errors"] = _cost_ratio([r for r in rows if not str(r.get("error") or "")], base, cand)
    return out


def split_by_method(rows_by_run: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """같은 실행 CSV(방법 열)를 "<회차 이름>-<방법>"으로 나눈다(v17_blind4.build_sheet 입력)."""
    out: dict[str, list[dict]] = {}
    for run, rows in rows_by_run.items():
        for r in rows:
            out.setdefault(f"{run}-{r['method']}", []).append(r)
    return out


# ── 판정 집계(⑰)와 B-3(설계 6절) ──
def rule17(verdicts: list[str]) -> str:
    """모든 회차 정답이면 정답, 한 회차라도 환각이면 환각, 그 밖은 오답. (경계)는 같은 종류로 센다(환각(경계)도 환각).
    LABELS 밖의 글(빈칸 포함)이 있으면 멈춤."""
    if not verdicts or any(v not in LABELS for v in verdicts):
        raise ValueError(f"판정 이름이 정답·오답·환각(경계 포함)이 아님: {verdicts}")
    kinds = [v.removesuffix("(경계)") for v in verdicts]
    if "환각" in kinds:
        return "환각"
    return "정답" if all(k == "정답" for k in kinds) else "오답"


def b3(test_hit5: dict, test17: dict, q30_17: dict, fu17: dict, cost: dict, time: dict, line: dict) -> dict:
    """설계 6절 B-3 여섯 줄. test17·q30_17·fu17 = {방법: {"정답": n, "환각": n}}, cost = cost_summary, time = time_summary."""
    base, cand = test_hit5["production"], test_hit5[CAND]
    if base["denominator"] != cand["denominator"]:
        raise SystemExit(f"확인용 검색 분모가 두 벌에서 달라 멈춤: {base['denominator']} · {cand['denominator']}")
    need = math.ceil(0.10 * base["denominator"])  # 10%p를 실제 검색 분모의 문장 수로 올림
    t = time["pooled"]["all"]
    ratios = [v for k, v in cost["pooled"].items() if k.startswith("ratio")]
    gap = lambda s: s[CAND]["정답"] - s[BASE]["정답"]
    lines = {
        "test_hit5": {"ok": cand["hit5"] - base["hit5"] >= need,
                      "detail": {"base": base["hit5"], "cand": cand["hit5"], "denominator": base["denominator"], "need": need}},
        "test_verdict": {"ok": gap(test17) > 0 and test17[CAND]["환각"] == 0, "detail": test17},
        "q30_verdict": {"ok": gap(q30_17) >= -2 and q30_17[CAND]["환각"] == 0, "detail": q30_17},
        "fu_verdict": {"ok": gap(fu17) >= -1 and fu17[CAND]["환각"] == 0, "detail": fu17},
        "cost": {"ok": all(r is not None and r <= 1.5 for r in ratios), "detail": cost["pooled"]},
        "time": {"ok": t["diff_ms"] is not None and t["diff_ms"] <= line["total_ms"]
                 and (line.get("non_llm_ms") is None
                      or (t["diff_non_llm_ms"] is not None and t["diff_non_llm_ms"] <= line["non_llm_ms"])),
                 "detail": {"diff_ms": t["diff_ms"], "diff_non_llm_ms": t["diff_non_llm_ms"], "line": line}},
    }
    return lines | {"all_ok": all(v["ok"] for v in lines.values())}


# ── CLI ──
def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def _production_settings():
    from ingest.__main__ import load_env
    load_env()
    from app.core.config import get_settings
    from evaluation.run_config import warn_if_different
    settings = get_settings()
    if warn_if_different(settings):
        raise SystemExit("운영 기본값과 다른 설정이라 멈춤")
    if settings.search_mode != "vector":
        raise SystemExit("벡터 검색(search_mode=vector)에서만 써서 멈춤")
    return settings


def search_test(test_set: Path) -> Path:
    """확인용 검색(5위 안): 운영과 임베딩 large를 한 실행 안에서. 결과는 OUT/stage4-search(git 밖), 화면에는 경로만."""
    require_open_file(OPEN_FILE)
    out = OUT / "stage4-search"
    if out.exists():
        raise SystemExit(f"확인용 검색 결과 폴더가 이미 있어 멈춤(다시 돌리지 않음): {out}")
    settings = _production_settings()
    from app.ask.routes import get_deps
    from app.catalog.registry import load_models
    from app.core.db import get_conn
    from measure.emb_large import embed_for, write_outputs
    from measure.search_eval import bundle_fns, read_cases
    from measure.v17_stage1 import measure_sets
    models = {m["id"]: m for m in load_models()}
    deps = get_deps()
    fns = lambda b: (deps.search, deps.diagnostic) if b is None else bundle_fns(b, models, get_conn)
    summary, rows = measure_sets({"test": read_cases(test_set)}, [None, CAND], deps.embed_query, fns, top_k=settings.top_k,
                                 embed_for=embed_for, depth=100)
    return write_outputs(out, "emb-retry", "stage4-search", rows, summary, settings)


def followups(label: str) -> Path:
    """이어지는 질문 31턴을 운영과 임베딩 large로 같은 실행 안에서. 결과 CSV 경로만 돌려준다."""
    import dataclasses
    settings = _production_settings()
    today = datetime.date.today().isoformat()
    out = ROOT / "evaluation" / "results" / f"{label}-{today}.csv"
    if out.exists():
        raise SystemExit(f"결과 파일이 이미 있어 멈춤(다시 돌리지 않음): {out.name}")
    from app.ask.routes import get_deps
    from app.ask.service import answer_question
    from app.catalog.registry import load_models
    from app.core.db import get_conn
    from app.core.errors import AppError
    from evaluation.followups import load_followups
    from evaluation.run_config import write_settings
    from measure.v17_answer import bundle_deps
    models = {m["id"]: m for m in load_models()}
    bundle_deps(get_deps(), CAND, models, get_conn)  # 저장 안 된 한 벌이면 AI를 부르기 전에 멈춤

    def client_for(method):
        def client(model_id, question, history):
            deps = bundle_deps(get_deps(), None if method == BASE else method, models, get_conn)
            usage = {"rewrite_input_tokens": 0, "rewrite_output_tokens": 0}
            rewrite = deps.rewrite

            def counted_rewrite(q, h):
                r = rewrite(q, h)
                usage["rewrite_input_tokens"] += r.usage.get("input_tokens", 0)
                usage["rewrite_output_tokens"] += r.usage.get("output_tokens", 0)
                return r
            deps = dataclasses.replace(deps, rewrite=counted_rewrite)
            try:
                resp = answer_question(model_id, question, deps, settings, debug=True, history=history)
            except AppError as e:
                return {"error_code": e.code}
            return resp | usage | {"input_tokens": deps.timings.get("input_tokens", 0),
                                   "output_tokens": deps.timings.get("output_tokens", 0)}
        return client

    rows = run_followups_same_run([BASE, CAND], label, client_for=client_for,
                                  rows=load_followups(ROOT / "evaluation" / "followups.csv"))
    with out.open("x", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FU_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    write_settings(out, settings, label, experiment={"search_methods": {BASE: "운영", CAND: "임베딩 large"}, "same_run": True})
    return out


def read_results(paths: list[Path]) -> dict[str, list[dict]]:
    """emb-retry-<세트>-r<n>-<날짜>.csv들을 세트별로, 행에 run(r<n>)을 붙여."""
    out: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for p in paths:
        m = RESULT_NAME.fullmatch(p.name)
        if not m:
            raise SystemExit(f"결과 파일 이름이 emb-retry-<test|q30|fu>-r<n>-<날짜>.csv가 아니라 멈춤: {p.name}")
        if (m[1], m[2]) in seen:
            raise SystemExit(f"같은 세트·회차 파일이 두 번 들어와 멈춤: {m[1]} {m[2]}")
        seen.add((m[1], m[2]))
        out.setdefault(m[1], []).extend(r | {"run": m[2]} for r in _read_csv(p))
    if seen != RESULT_SETS:
        raise SystemExit(f"세 세트 × 두 회차(6개)가 정확히 있어야 함: 빠짐 {sorted(RESULT_SETS - seen)}, 남음 {sorted(seen - RESULT_SETS)}")
    return out


def blind_regression(label: str, date: str) -> tuple[Path, str]:
    """30문항·이어지는 질문 두 회차를 방법별로 나눠 가린 판정지 한 장(⑳ 입력). 판정지·대응표는 git 밖, 대응표 해시를 돌려준다."""
    import random

    from measure.v17_blind4 import build_sheet
    res = ROOT / "evaluation" / "results"
    sets = {s: {f"{label}-{s}-{r}-{date}": _read_csv(res / f"{label}-{s}-{r}-{date}.csv") for r in ("r1", "r2")}
            for s in ("q30", "fu")}
    sheet_path, key_path = OUT / f"{label}-regression-blind-sheet.md", OUT / f"{label}-regression-blind-key.json"
    if sheet_path.exists() or key_path.exists():
        raise SystemExit("판정지 또는 대응표가 이미 있어 멈춤(덮어쓰지 않음)")
    text, key = build_sheet(split_by_method(sets["q30"]), split_by_method(sets["fu"]), random.SystemRandom(), label)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet_path.write_text(text, encoding="utf-8")
    data = json.dumps(key, ensure_ascii=False, indent=1).encode("utf-8")
    key_path.write_bytes(data)  # 판정 후 공개
    return sheet_path, hashlib.sha256(data).hexdigest()


USAGE = ("사용법: python -m measure.emb_retry open <commit> | search-test --test-set <path> | followups --label <label> "
         "| time-summary <결과 CSV들> | blind-regression --label <label> --date <날짜>")


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    cmd, rest = (args[0], args[1:]) if args else ("", [])
    if cmd == "open" and len(rest) == 1:
        print(write_open_file(rest[0]))
    elif cmd == "search-test" and rest[:1] == ["--test-set"] and len(rest) == 2:
        print(search_test(Path(rest[1])))
    elif cmd == "followups" and rest[:1] == ["--label"] and len(rest) == 2:
        print(followups(rest[1]))
    elif cmd == "time-summary" and rest:
        print(json.dumps(time_summary(read_results([Path(p) for p in rest])), ensure_ascii=False, indent=1))
    elif cmd == "blind-regression" and rest[0::2] == ["--label", "--date"] and len(rest) == 4:
        sheet, key_sha = blind_regression(rest[1], rest[3])
        print(sheet, "대응표 SHA-256", key_sha)
    else:
        raise SystemExit(USAGE)


if __name__ == "__main__":
    main()
