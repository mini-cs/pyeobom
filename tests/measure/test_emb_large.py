"""임베딩 모델 바꾸기(v1.9) Task 2: 벌마다 질문 임베딩, 후보 조각 다시 임베딩 저장, 순위 구간."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.ask.service import Deps
from measure import emb_large as el
from measure import v17_answer
from measure import v17_stage1 as s1
from measure.search_eval import run_eval
from measure.v17_bundle import BundleChunk


def _cases():
    return {"dev": [{"id": "a", "model_id": "m", "question": "같은 질문", "expected_ref": "x:1"}],
            "q30": [{"id": "b", "model_id": "m", "question": "같은 질문", "expected_ref": "x:1"},
                    {"id": "c", "model_id": "m", "question": "다른 질문", "expected_ref": "x:1"}]}


def test_measure_sets_uses_embed_for_per_bundle():
    small_calls, large_calls, seen = [], [], []

    def small(q):
        small_calls.append(q)
        return [0.0, float(len(small_calls))]

    def large(q):
        large_calls.append(q)
        return [1.0, float(len(large_calls))]

    def fns(name):
        def search(m, vec, text, k):
            seen.append((name, vec[0]))
            return [SimpleNamespace(id=1, ref="x:1")]
        return search, lambda m: []

    embed_for = lambda b, base: large if b == "emb_large" else base
    s1.measure_sets(_cases(), [None, "emb_large"], small, fns, top_k=5, embed_for=embed_for)
    # 질문 글자마다 모델별 한 번씩(두 벌이 한 캐시를 공유하면 large가 불리지 않는다, Review Focus 3)
    assert sorted(small_calls) == sorted(large_calls) == ["같은 질문", "다른 질문"]
    assert {v for n, v in seen if n is None} == {0.0} and {v for n, v in seen if n == "emb_large"} == {1.0}


def _deps():
    return Deps(embed_query=lambda q: [0.0], search=lambda *a: [], complete=lambda m: "", supported_ids={"m"},
                official_url=lambda m: "")


def test_bundle_deps_swaps_embed_for_emb_large(monkeypatch):
    monkeypatch.setattr(v17_answer, "bundle_fns", lambda b, models, gc: ((lambda *a: []), (lambda m: [])))
    base = _deps()
    got = v17_answer.bundle_deps(base, "emb_large", {}, None)
    assert got.embed_query is el.embed_for("emb_large", base.embed_query) and got.embed_query is not base.embed_query


def test_bundle_deps_keeps_embed_for_other_bundles(monkeypatch):
    monkeypatch.setattr(v17_answer, "bundle_fns", lambda b, models, gc: ((lambda *a: []), (lambda m: [])))
    base = _deps()
    assert v17_answer.bundle_deps(base, "strip_800", {}, None).embed_query is base.embed_query
    assert v17_answer.bundle_deps(base, None, {}, None) is base


class FakeConn:
    def __init__(self):
        self.inserted, self.committed = [], 0

    def commit(self):
        self.committed += 1

    @contextmanager
    def transaction(self):
        yield

    @contextmanager
    def cursor(self):
        yield SimpleNamespace(executemany=lambda sql, rows: self.inserted.append((sql, list(rows))))


CHUNKS = [BundleChunk(299, "guide-a", None, "가이드 본문"), BundleChunk(336, "manual-x", 3, "설명서 본문")]


def test_store_reembedded_refuses_existing_bundle(monkeypatch):
    monkeypatch.setattr(el, "bundle_exists", lambda conn, name: True)
    conn = FakeConn()
    with pytest.raises(SystemExit):
        el.store_reembedded("emb_large", CHUNKS, el.CANDIDATE, conn=conn, embed=lambda *a, **k: [[0.0]] * 2)
    assert conn.inserted == []


def test_store_reembedded_sends_spec_to_embed(monkeypatch):
    monkeypatch.setattr(el, "bundle_exists", lambda conn, name: False)
    calls, conn = [], FakeConn()

    def embed(texts, *, model, dimensions):
        calls.append((list(texts), model, dimensions))
        return [[float(i)] for i in range(len(texts))]

    n = el.store_reembedded("emb_large", CHUNKS, el.CANDIDATE, conn=conn, embed=embed)
    assert calls == [(["가이드 본문", "설명서 본문"], "text-embedding-3-large", 1536)]  # 본문 그대로, 가이드도
    (sql, rows), = conn.inserted
    assert "INSERT INTO bundle_chunks" in sql
    assert rows == [("emb_large", 299, "guide-a", None, "가이드 본문", [0.0]), ("emb_large", 336, "manual-x", 3, "설명서 본문", [1.0])]
    assert n == 2


def test_store_reembedded_inserts_nothing_when_embed_fails(monkeypatch):
    monkeypatch.setattr(el, "bundle_exists", lambda conn, name: False)
    conn = FakeConn()

    def embed(texts, *, model, dimensions):
        raise RuntimeError("API 오류")

    with pytest.raises(RuntimeError):
        el.store_reembedded("emb_large", CHUNKS, el.CANDIDATE, conn=conn, embed=embed)
    assert conn.inserted == []


def test_rank_buckets_edges():
    got = el.rank_buckets([5, 6, 20, 21, 50, 100, 101, None])
    assert got == {"1-5": 1, "6-10": 1, "11-20": 1, "21-30": 1, "31-50": 1, "51-100": 1, "100+": 2}


def test_run_eval_depth_finds_rank_beyond_20():
    results = [SimpleNamespace(id=i, ref=f"manual:{i}") for i in range(1, 41)]
    case = {"id": "q01", "model_id": "m", "question": "질문", "expected_ref": "manual:30"}
    args = ([case], lambda q: [0.0], lambda m, v, t, k: results[:k], lambda m: [])
    assert run_eval(*args)[0]["rank"] is None
    assert run_eval(*args, depth=100)[0]["rank"] == 30


def test_embed_for_same_spec_same_function():
    base = lambda q: [0.0]
    assert el.embed_for("emb_large", base) is el.embed_for("emb_large", base)
    assert el.embed_for(None, base) is base and el.embed_for("strip_800", base) is base
