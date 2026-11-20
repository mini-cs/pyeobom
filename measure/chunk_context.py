"""조각 설명 붙이기(v1.95): 운영 조각과 원본 짝짓기, 설명 쓰기·표본, 실험 벌(ctx_small) 저장·대조·측정, 응답 시간 쌍.

설계 `docs/superpowers/specs/2026-11-20-chunk-context-design.md`, 계획 Task 2.
CLI: python -m measure.chunk_context estimate | describe | sample | store | verify | measure [--out 폴더]
     | latency <r1 CSV> <r2 CSV> | check-ingest
설명서 글·조각 글·설명 글은 출력하지 않는다(수·길이·해시만). 표본 파일만 git 밖 OUT에 글을 담는다.
"""
import csv
import dataclasses
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from functools import partial
from pathlib import Path

from ingest.describe import (CANDIDATE_CONTEXT, DESC_PATH, MAX_DESC_LEN, MAX_OUTPUT_TOKENS, ContextItem, ContextSpec,
                             MissingDescriptions, build_prompt, context_items, describe_all, describe_chunk,
                             embedding_input, prompt_sha256, record_key, stored_key)
from ingest.load import ROOT
from measure.emb_large import EmbedSpec, production_chunks, store_reembedded, text_mismatches
from measure.stage2 import PRICE_IN, PRICE_OUT
from measure.v17_bundle import BundleChunk

BUNDLE = "ctx_small"
SMALL = EmbedSpec("text-embedding-3-small", None)  # 운영과 같은 모델, dimensions 없음
OUT = ROOT / "measure" / "out" / "chunk-context"
SAMPLE_SEED = 20261121  # 결정기록 037
PRICE_SMALL_PER_CHAR = 2e-8  # 0.02달러/100만 토큰, 글자 = 토큰 가정
USAGE = ("사용법: python -m measure.chunk_context estimate | describe [--limit N] | sample | store | verify | measure [--out 폴더]"
         " | latency <r1 CSV> <r2 CSV> | check-ingest")


def production_items(conn, docs: list[dict], models: dict[str, dict]) -> list[tuple[BundleChunk, ContextItem]]:
    """운영 조각(id 순)을 문서마다 원본 파일에서 다시 자른 조각과 (쪽, 본문) 순서대로 짝짓는다(DB 읽기만).
    하나라도 다르거나 DB에만·파일에만 있는 문서가 있으면 멈춘다(엉뚱한 쪽 글로 설명을 쓰지 않게)."""
    prod = production_chunks(conn)
    by_doc: dict[str, list[BundleChunk]] = defaultdict(list)
    for c in prod:
        by_doc[c.doc_id].append(c)
    file_ids = [d["id"] for d in docs]
    if only_db := sorted(set(by_doc) - set(file_ids)):
        raise SystemExit(f"운영 DB에만 있는 문서라 멈춤: {only_db}")
    if only_file := [i for i in file_ids if i not in by_doc]:
        raise SystemExit(f"원본 파일에만 있는 문서라 멈춤: {only_file}")
    item_of: dict[int, ContextItem] = {}
    for d in docs:
        items, chunks = context_items(d, models), by_doc[d["id"]]
        differ = sum((i.page, i.content) != (c.page, c.content) for i, c in zip(items, chunks)) + abs(len(items) - len(chunks))
        if differ:  # 메시지에 본문 글자는 넣지 않는다
            raise SystemExit(f"원본에서 다시 자른 조각이 운영과 달라 멈춤: {d['id']} (원본 {len(items)}개, 운영 {len(chunks)}개, "
                             f"다른 자리 {differ}개)")
        item_of |= {c.id: dataclasses.replace(i, chunk_id=c.id) for i, c in zip(items, chunks)}
    return [(c, item_of[c.id]) for c in prod]


def estimate_describe(items: list[ContextItem]) -> dict:
    """설명 쓰기 비용 상한 어림: 요청문 글자(= 입력 토큰 가정) + 조각마다 출력 상한(추론 토큰 포함)."""
    chars = sum(len(build_prompt(i)) for i in items)
    cost = chars * PRICE_IN / 1e6 + len(items) * MAX_OUTPUT_TOKENS * PRICE_OUT / 1e6
    return {"items": len(items), "input_chars": chars, "cost_usd": cost}


def unsupported_tokens(description: str, item: ContextItem) -> list[str]:
    """설명 속 숫자·영문·코드 중 글·조각·문서 이름에 없는 것(대소문자 무시, 중복 제거, 나온 순서). 자동 검사용."""
    hay = "\n".join((item.source, item.content, item.doc_label)).lower()
    out: list[str] = []
    for t in re.findall(r"[0-9A-Za-z]+(?:[.,][0-9]+)?", description):
        if t.lower() not in hay and t not in out:
            out.append(t)
    return out


def sample_items(pairs: list[tuple[BundleChunk, ContextItem]], n: int = 20, seed: int = SAMPLE_SEED) -> list[int]:
    return sorted(random.Random(seed).sample([c.id for c, _ in pairs], n))


def store_contextual(conn, pairs: list[tuple[BundleChunk, ContextItem]], descriptions: list[str]) -> int:
    if len(descriptions) != len(pairs) or not all(descriptions):
        raise SystemExit(f"설명이 빠진 조각이 있어 멈춤(조각 {len(pairs)}개, 설명 {sum(map(bool, descriptions))}개)")
    chunks = [c for c, _ in pairs]
    return store_reembedded(BUNDLE, chunks, SMALL, conn=conn,
                            inputs=[embedding_input(d, c.content) for d, c in zip(descriptions, chunks)])


def describe_report(items: list[ContextItem], path: Path = DESC_PATH) -> dict:
    """설명 파일에서 items의 모든 기록(실패 줄 포함)을 모아 수·토큰·실제 비용·길이·해시를 센다. 설명 글은 넣지 않는다."""
    psha = prompt_sha256()
    keys = list(dict.fromkeys(record_key(i, CANDIDATE_CONTEXT, psha) for i in items))
    recs: dict[tuple, list[dict]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        r = json.loads(line)
        recs[stored_key(r)].append(r)
    ok = {k: next(r["description"] for r in recs[k] if r["description"]) for k in keys if any(r["description"] for r in recs[k])}
    descs = [(ok[k], i) for i in items if (k := record_key(i, CANDIDATE_CONTEXT, psha)) in ok]
    mine = [r for k in keys for r in recs[k]]  # 이 조각들의 모든 시도(두 번 실패한 줄 포함)
    tin, tout = sum(r["input_tokens"] for r in mine), sum(r["output_tokens"] for r in mine)
    lens = [len(d) for d, _ in descs]
    return {"items": len(items), "described": len(descs), "failed": len(items) - len(descs),
            "calls": sum(r["attempts"] for r in mine), "retried": sum(sum(r["attempts"] for r in recs[k]) > 1 for k in keys),
            "empty": sum(not d for d, _ in descs), "over_150": sum(n > MAX_DESC_LEN for n in lens),
            "input_tokens": tin, "output_tokens": tout, "cost_usd": (tin * PRICE_IN + tout * PRICE_OUT) / 1e6,
            "len_min": min(lens, default=None), "len_avg": round(sum(lens) / len(lens), 1) if lens else None,
            "len_max": max(lens, default=None),
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
            "flagged": sum(bool(unsupported_tokens(d, i)) for d, i in descs)}


def run_describe(pairs, *, limit: int | None = None, path: Path = DESC_PATH, call=describe_chunk, report=print) -> dict:
    """운영 조각 id 순 앞 limit개(없으면 전부)의 설명을 쓰고 출력한다. 이미 쓴 조각은 부르지 않는다.
    빠진 조각이 있으면 출력(실패 수·실패 시도 포함 토큰·실제 비용)을 먼저 내고 멈춘다."""
    items = [i for _, i in pairs][:limit]
    try:
        describe_all(items, CANDIDATE_CONTEXT, path=path, call=call)
    except MissingDescriptions:
        report(describe_report(items, path))
        raise
    got = describe_report(items, path)
    report(got)
    return got


def write_sample(pairs, descs: list[str]) -> dict:
    """표본 20개 + 자동 검사에 걸린 조각을 git 밖 파일에(글·조각·설명 포함, 게시하지 않음). 반환은 수와 id만."""
    ids = sample_items(pairs)
    flagged = [c.id for (c, i), d in zip(pairs, descs) if unsupported_tokens(d, i)]
    lines = ["# 조각 설명 표본 대조(v1.95, git 밖, 게시 금지)", "",
             f"표본 {len(ids)}개(시드 {SAMPLE_SEED}) + 자동 검사에 걸린 표본 밖 조각 {len(set(flagged) - set(ids))}개", ""]
    for (c, i), d in zip(pairs, descs):
        if c.id not in ids and c.id not in flagged:
            continue
        kind = "표본" if c.id in ids else "자동 검사"
        lines += [f"## 조각 {c.id} ({kind}) — {c.doc_id}, 쪽 {c.page if c.page is not None else '-'}",
                  f"- 설명: {d}", f"- 걸린 토큰: {', '.join(unsupported_tokens(d, i)) or '없음'}", "",
                  "### 조각", "", c.content, "", "### 글", "", i.source, ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sample-20.md").write_text("\n".join(lines), encoding="utf-8")
    return {"sample": ids, "flagged": flagged, "path": str(OUT / "sample-20.md")}


def latency_report(paths: list[Path]) -> dict:
    from measure.stage2 import paired_latency, parse_result_row, summarize_methods
    if len({p.stem for p in paths}) != len(paths):  # 회차(run)를 파일 이름으로 가르므로 같으면 회차가 합쳐진다(검토 M3)
        raise SystemExit("회차 CSV 이름이 같아 멈춤(파일 이름이 회차 이름)")
    rows = []
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows += [parse_result_row(r) | {"run": p.stem} for r in csv.DictReader(f)]
    def per_q(method):
        costs = [r["cost_usd"] for r in rows if r["method"] == method]
        return sum(costs) / len(costs)
    return {"summary": summarize_methods(rows), "latency": paired_latency(rows, "m0", BUNDLE),
            "cost_ratio": per_q(BUNDLE) / per_q("m0")}  # 후보 ÷ 운영, 두 회차 합친 질문당 비용(검토 M5)


def check_ingest(conn, docs: list[dict], models: dict[str, dict], settings) -> dict:
    """반영 뒤 적재(설정 켜짐)가 store와 글자까지 같은 임베딩 입력을 만들고 새로 쓸 설명이 0개인지. AI 호출·DB 쓰기 없음."""
    from ingest.describe import ingest_texts
    from ingest.load import chunks_with_sources
    if ContextSpec(settings.chunk_context_model, settings.chunk_context_reasoning_effort) != CANDIDATE_CONTEXT:
        raise SystemExit("조각 설명 설정이 측정한 설명 모델·추론과 달라 멈춤")
    pairs = production_items(conn, docs, models)
    descs = describe_all([i for _, i in pairs], CANDIDATE_CONTEXT, allow_new=False)  # 빠지면 MissingDescriptions
    want: dict[str, list[str]] = defaultdict(list)
    for (c, _), d in zip(pairs, descs):
        want[c.doc_id].append(embedding_input(d, c.content))
    bad = [d["id"] for d in docs
           if ingest_texts(d, chunks_with_sources(d)[0], settings, models, describe=partial(describe_all, allow_new=False))
           != want[d["id"]]]
    if bad:
        raise SystemExit(f"적재 임베딩 입력이 측정한 입력과 달라 멈춤: {bad}")
    return {"docs": len(docs), "inputs": len(pairs), "new_descriptions": 0, "mismatched_docs": 0}


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "latency" and len(args) == 3:
        return print(json.dumps(latency_report([Path(a) for a in args[1:]]), ensure_ascii=False))
    if cmd == "measure":
        out = args[2] if args[1:2] == ["--out"] and len(args) == 3 else "ctx-stage1" if len(args) == 1 else None
        if out is None:
            raise SystemExit(USAGE)
        from measure.emb_large import measure
        return measure(out, bundle=BUNDLE, out_root=OUT, label_prefix="ctx")  # measure/out/chunk-context/<out>/, 라벨 ctx-
    limit = None
    if cmd == "describe" and len(args) == 3 and args[1] == "--limit" and args[2].isdigit() and int(args[2]) > 0:
        limit, args = int(args[2]), args[:1]  # 조각 id 순 앞 N개만(Task 3: --limit 1로 기록 형식·토큰 먼저 확인)
    if len(args) != 1 or cmd not in ("estimate", "describe", "sample", "store", "verify", "check-ingest"):
        raise SystemExit(USAGE)

    from ingest.__main__ import load_env
    load_env()
    from app.catalog.registry import load_models
    from app.core.config import get_settings
    from app.core.db import get_conn
    from ingest.load import load_documents
    docs, models = load_documents(), {m["id"]: m for m in load_models()}
    with get_conn() as conn:
        if cmd == "verify":
            bad = text_mismatches(conn, BUNDLE)
            if bad:
                raise SystemExit(f"운영과 글·쪽·문서·번호가 다른 id가 있어 멈춤: {bad[:20]} (모두 {len(bad)}개)")
            return print({"bundle": BUNDLE, "mismatches": 0})
        if cmd == "check-ingest":
            return print(check_ingest(conn, docs, models, get_settings()))
        pairs = production_items(conn, docs, models)
        items = [i for _, i in pairs]
        if cmd == "estimate":
            chars = sum(len(c.content) for c, _ in pairs)
            embed = (len(pairs) * (MAX_DESC_LEN + 1) + chars) * PRICE_SMALL_PER_CHAR  # 설명 150자 + 줄바꿈 가정
            return print({"chunks": len(pairs), "content_chars": chars, "describe": estimate_describe(items),
                          "embed_cost_usd": round(embed, 6)})
        if cmd == "describe":
            run_describe(pairs, limit=limit)  # 빠지면 출력 뒤 MissingDescriptions(멈춤)
            return
        descs = describe_all(items, CANDIDATE_CONTEXT, allow_new=False)  # 아래는 설명을 새로 쓰지 않는다
        if cmd == "sample":
            return print(write_sample(pairs, descs))
        n = store_contextual(conn, pairs, descs)  # store
        print({"bundle": BUNDLE, "rows": n})


if __name__ == "__main__":
    main()
