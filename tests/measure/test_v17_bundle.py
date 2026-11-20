import os

import pytest

from ingest.clean import clean_text
from ingest.page_marker import strip_page_marker, strip_plain_page
from ingest.plaintext import PlainPage, clean_plain_page, markdown_to_plain
from measure.v17_bundle import (MANUAL_ID_BASE, BundleChunk, build_bundle, bundle_exists, chunk_plain_800,
                                load_guide_chunks, manual_pages_from_pypdfium2, manual_pages_from_tool, store_bundle)

PROD_MAX_ID = 335  # 2026-11-16 운영 chunks.id 최대(사용자 결정 절)
GUIDES = [BundleChunk(299, "guide-a", None, "가이드 본문 하나"), BundleChunk(300, "guide-b", None, "가이드 본문 둘")]


def pages(doc_char: str) -> list[tuple[int, PlainPage]]:
    # 800자를 넘는 쪽(여러 조각)과 짧은 쪽을 섞는다. 쪽마다 글자가 달라 부분 글자 검사가 쪽을 가려낸다
    return [(3, PlainPage("".join(f"{doc_char}3-{i:04d} " for i in range(200)), [])),
            (4, PlainPage(f"{doc_char} 짧은 쪽", [])),
            (7, PlainPage("".join(f"{doc_char}7-{i:04d} " for i in range(150)), []))]


MANUALS = {"manual-z": pages("Z"), "manual-a": pages("A")}


def test_manual_chunks_stay_in_page():
    bundle = build_bundle("t", MANUALS, chunk_plain_800, guides=GUIDES)
    manual = [c for c in bundle if c.id >= MANUAL_ID_BASE]
    assert len(manual) > len(MANUALS) * 3  # 긴 쪽이 여러 조각으로 나뉨
    for c in manual:
        text = dict(MANUALS[c.doc_id])[c.page].text
        assert c.content and c.content in text


def test_manual_chunk_ids_follow_doc_id_order_then_chunker_order():
    bundle = build_bundle("t", MANUALS, chunk_plain_800, guides=GUIDES)
    manual = [c for c in bundle if c.id >= MANUAL_ID_BASE]
    expected = [("manual-a", p, t) for p, t in chunk_plain_800(MANUALS["manual-a"])] + \
               [("manual-z", p, t) for p, t in chunk_plain_800(MANUALS["manual-z"])]
    assert [(c.doc_id, c.page, c.content) for c in manual] == expected
    assert [c.id for c in manual] == list(range(MANUAL_ID_BASE, MANUAL_ID_BASE + len(manual)))
    assert bundle[len(manual):] == GUIDES  # 가이드는 뒤에 그대로


def test_bundle_ids_do_not_collide():
    assert MANUAL_ID_BASE > PROD_MAX_ID
    bundle = build_bundle("t", MANUALS, chunk_plain_800, guides=GUIDES)
    ids = [c.id for c in bundle]
    assert len(ids) == len(set(ids))
    assert all(c.id >= MANUAL_ID_BASE for c in bundle if c.doc_id.startswith("manual"))


def test_guide_with_manual_range_id_is_rejected():
    with pytest.raises(ValueError):
        build_bundle("t", MANUALS, chunk_plain_800, guides=[BundleChunk(MANUAL_ID_BASE, "guide-a", None, "x")])


def test_chunk_plain_800_is_chunk_pages_on_text():
    from ingest.chunk import chunk_pages
    pp = pages("Q")
    assert chunk_plain_800(pp) == chunk_pages([(p, x.text) for p, x in pp], max_chars=800, overlap=100)


def test_manual_pages_from_pypdfium2_cleans_then_strips_marker():
    raw = {"manual-a": [(12, "12\n세탁조   청소  안내\n"), (13, "본문\n13")]}
    out = manual_pages_from_pypdfium2(raw)
    assert out == {"manual-a": [(p, PlainPage(strip_page_marker(clean_text(t), p)[0], [])) for p, t in raw["manual-a"]]}


def test_manual_pages_from_tool_converts_cleans_then_strips_with_tail():
    md = {"manual-a": [(5, "# 제목\n\n**본문** 글\n\n5"), (6, "6 한국어\n\n## 둘째\n글")]}
    out = manual_pages_from_tool(md)
    expected = [(p, strip_plain_page(clean_plain_page(markdown_to_plain(t)), p, check_tail=True)[0]) for p, t in md["manual-a"]]
    assert out == {"manual-a": expected}


# ── store_bundle (가짜 conn·embed) ──
class FakeConn:
    """psycopg 기본(autocommit 아님)의 트랜잭션 상태를 흉내 낸다.
    밖에서 execute하면 암묵 트랜잭션이 열리고(commit·rollback 전까지), 그때 transaction()은 SAVEPOINT가 된다."""
    def __init__(self, existing=False):
        self.log, self.existing, self.open, self.block, self.committed = [], existing, False, None, []
        self.rowcount, self._one = 0, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def transaction(self):
        conn = self

        class Tx:
            def __enter__(self):
                conn.block = "savepoint" if conn.open else "real"
                conn.open, conn._pending = True, []
                return self

            def __exit__(self, exc_type, *a):
                kind, conn.block = conn.block, None
                if kind == "real":
                    conn.open = False
                    if exc_type is None:
                        conn.committed += conn._pending
                return False
        return Tx()

    def cursor(self):
        return self

    def commit(self):
        self.log.append(("commit", None, None))
        self.open = False

    def rollback(self):
        self.log.append(("rollback", None, None))
        self.open = False

    def execute(self, sql, params=None):
        self.open = True
        self.log.append(("execute", sql, params))
        if self.block:
            self._pending.append(sql)
        if "SELECT 1" in sql:
            self._one = (1,) if self.existing else None
        elif "FROM chunks" in sql:
            self.rowcount = len(params[1])
        return self

    def executemany(self, sql, rows):
        rows = list(rows)
        self.open = True
        self.log.append(("executemany", sql, rows))
        if self.block:
            self._pending.append(sql)
        self.rowcount = len(rows)

    def fetchone(self):
        return self._one


class FakeEmbed:
    def __init__(self, conn=None):
        self.calls, self.conn, self.open_during = [], conn, []

    def __call__(self, texts):
        self.calls.append(list(texts))
        self.open_during.append(self.conn.open if self.conn else None)
        return [[float(i)] for i in range(len(texts))]


def bundle():
    return build_bundle("t", MANUALS, chunk_plain_800, guides=GUIDES)


def test_store_embeds_manual_contents_exactly_and_never_guides():
    chunks, embed, conn = bundle(), FakeEmbed(), FakeConn()
    n = store_bundle("t", chunks, apply=True, conn=conn, embed=embed)
    manual = [c for c in chunks if c.id >= MANUAL_ID_BASE]
    assert embed.calls == [[c.content for c in manual]]  # 한 번에, 순서·글자 그대로(아무것도 붙이지 않음)
    assert not any(g.content in t for g in GUIDES for t in embed.calls[0])
    inserted = next(rows for kind, sql, rows in conn.log if kind == "executemany")
    assert inserted == [("t", c.id, c.doc_id, c.page, c.content, [float(i)]) for i, c in enumerate(manual)]
    copy_sql, copy_params = next((sql, p) for kind, sql, p in conn.log if kind == "execute" and sql and "FROM chunks" in sql)
    assert "INSERT INTO bundle_chunks" in copy_sql and copy_params == ("t", [299, 300])
    assert n == len(manual) + len(GUIDES)


def test_store_dry_run_touches_neither_api_nor_db():
    chunks, embed, conn = bundle(), FakeEmbed(), FakeConn()
    n = store_bundle("t", chunks, apply=False, conn=conn, embed=embed)
    assert n == sum(len(c.content) for c in chunks if c.id >= MANUAL_ID_BASE)
    assert embed.calls == [] and conn.log == []


def test_store_stops_if_bundle_already_exists():
    embed, conn = FakeEmbed(), FakeConn(existing=True)
    with pytest.raises(RuntimeError):
        store_bundle("t", bundle(), apply=True, conn=conn, embed=embed)
    assert embed.calls == []  # 임베딩 비용을 쓰기 전에 멈춘다
    assert not any(kind == "executemany" or "INSERT" in (sql or "") for kind, sql, _ in conn.log)


def test_store_inserts_in_real_transaction_and_embeds_outside_any_transaction():
    conn = FakeConn()
    embed = FakeEmbed(conn)
    store_bundle("t", bundle(), apply=True, conn=conn, embed=embed)
    assert embed.open_during == [False]  # 임베딩 중에는 열린 DB 트랜잭션이 없다
    inserts = [sql for kind, sql, _ in conn.log if sql and "INSERT" in sql]
    assert len(inserts) == 2 and conn.committed == inserts  # 넣기는 SAVEPOINT가 아닌 진짜 트랜잭션에서 커밋까지 끝난다
    assert conn.open is False


def test_bundle_exists():
    assert bundle_exists(FakeConn(existing=True), "t") is True
    assert bundle_exists(FakeConn(existing=False), "t") is False


# ── 통합(실제 Neon 조회만, 쓰기·임베딩 없음) ──
@pytest.fixture(scope="module")
def conn():
    from ingest.__main__ import load_env
    load_env()  # 로컬 .env의 접속 주소를 읽는다(값은 출력하지 않음)
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL이 없으면 Neon 테스트를 건너뛴다")
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.core.db import get_conn
    with get_conn() as c:
        yield c


def stored_bundles(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT bundle FROM bundle_chunks ORDER BY bundle").fetchall()]


@pytest.mark.integration
def test_guide_chunks_identical_to_production(conn):
    prod = conn.execute("""SELECT id, doc_id, page, content FROM chunks
                           WHERE doc_id IN (SELECT id FROM documents WHERE doc_type = 'guide') ORDER BY id""").fetchall()
    guides = [c for c in build_bundle("t", {}, chunk_plain_800, guides=load_guide_chunks(conn)) if c.id < MANUAL_ID_BASE]
    assert [(c.id, c.doc_id, c.page, c.content) for c in guides] == [tuple(r) for r in prod]
    assert {299, 300} <= {c.id for c in guides}
    from measure.emb_large import BUNDLE_EMBED, text_mismatches
    for name in stored_bundles(conn):  # 저장된 벌이 없으면 이 부분만 건너뛴다
        if name in BUNDLE_EMBED:  # 다시 임베딩한 벌(v1.9, 사용자 승인 2026-11-20): 글·쪽·문서·번호가 운영과 같음만 본다
            assert text_mismatches(conn, name) == [], name
            continue
        stored = {r[0] for r in conn.execute("SELECT id FROM bundle_chunks WHERE bundle = %s AND id < %s",
                                              (name, MANUAL_ID_BASE)).fetchall()}
        assert stored == {r[0] for r in prod}, name
        diff = conn.execute(
            """SELECT b.id FROM bundle_chunks b LEFT JOIN chunks c ON c.id = b.id
               WHERE b.bundle = %s AND b.id < %s AND (c.id IS NULL OR b.doc_id IS DISTINCT FROM c.doc_id
                 OR b.page IS DISTINCT FROM c.page OR b.content IS DISTINCT FROM c.content
                 OR b.embedding::text IS DISTINCT FROM c.embedding::text)""", (name, MANUAL_ID_BASE)).fetchall()
        assert diff == [], name


@pytest.mark.integration
def test_bundle_diag_ids_in_bundle(conn):
    from app.ask.routes import diagnostic_pages
    from app.catalog.registry import load_models
    from app.retrieval.search import fetch_manual_pages
    names = stored_bundles(conn)
    if not names:
        pytest.skip("저장된 실험 조각 한 벌이 없음")
    from measure.emb_large import BUNDLE_EMBED
    for name in names:
        ids = {r[0] for r in conn.execute("SELECT id FROM bundle_chunks WHERE bundle = %s", (name,)).fetchall()}
        for m in load_models():
            got = fetch_manual_pages(conn, m["id"], diagnostic_pages(m), bundle=name)
            assert {c.id for c in got} <= ids, (name, m["id"])
            # 다시 임베딩한 벌은 운영 번호를 그대로 쓰므로 1,000,000 이상 조건을 뺀다(v1.9, 사용자 승인 2026-11-20)
            assert name in BUNDLE_EMBED or all(c.id >= MANUAL_ID_BASE for c in got), (name, m["id"])
