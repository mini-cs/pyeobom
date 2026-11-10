-- 검색 개선 실험 색인(계획 2026-11-09-search-paraphrase-plan Task 3). 운영 표(chunks)는 건드리지 않는다.
-- Neon SQL Editor에서 한 번 실행한다(사용자). 운영 chunks.id = bigint(BIGSERIAL)라 chunk_id도 BIGINT.
-- ON DELETE CASCADE: python -m ingest가 문서의 조각을 지우고 다시 넣을 때 막히지 않게 한다(그 문서의 실험 행은 다시 만든다).
-- 지우기(실행 전 사용자 확인): 한 방법만 DELETE FROM chunk_variants WHERE variant = '<이름>'; 계획 종료·미채택 시 DROP TABLE chunk_variants;
CREATE TABLE IF NOT EXISTS chunk_variants (
  id         BIGSERIAL PRIMARY KEY,
  chunk_id   BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  variant    TEXT NOT NULL,          -- 'm1_title'(M1: 제목+조각) | 'm2_question'(M2: 만든 질문 1개)
  text       TEXT NOT NULL,
  embedding  VECTOR(1536) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chunk_variants_variant_chunk ON chunk_variants (variant, chunk_id);
