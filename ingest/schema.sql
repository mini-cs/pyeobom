-- Neon SQL Editor에서 한 번 실행한다 (기획서 5.6, 결정기록 017: text-embedding-3-small = 1536차원)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  id          TEXT PRIMARY KEY,
  doc_type    TEXT NOT NULL CHECK (doc_type IN ('manual', 'guide')),
  title       TEXT NOT NULL,
  source_url  TEXT NOT NULL,
  scope_note  TEXT NOT NULL,
  fetched_at  DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS document_models (
  doc_id    TEXT NOT NULL REFERENCES documents(id),
  model_id  TEXT NOT NULL,
  PRIMARY KEY (doc_id, model_id)
);

CREATE TABLE IF NOT EXISTS chunks (
  id         BIGSERIAL PRIMARY KEY,
  doc_id     TEXT NOT NULL REFERENCES documents(id),
  page       INTEGER,
  content    TEXT NOT NULL,
  embedding  VECTOR(1536) NOT NULL
);
