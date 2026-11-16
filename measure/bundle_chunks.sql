-- v1.7 실험 조각(계획 2026-11-16-v17-extraction-chunking-plan Task 5, 사용자 결정 2026-11-16). 운영 표(chunks)는 건드리지 않는다.
-- 한 벌(bundle)마다 설명서 조각(경계·본문·쪽이 운영과 다를 수 있음)과 운영 가이드 조각 복사본(번호·본문·쪽·임베딩 그대로)을 담는다.
-- chunks를 참조하지 않는다: ingest/load.py는 documents를 ON CONFLICT DO UPDATE로 고쳐 쓰고 chunks·document_models만 지우므로,
-- 문서를 다시 넣어도 이 표의 행은 지워지지 않고 다시 넣기도 막히지 않는다.
-- 지우기(실행 전 사용자 확인): 한 벌만 DELETE FROM bundle_chunks WHERE bundle = '<이름>'; 계획 종료·미채택 시 DROP TABLE bundle_chunks;
CREATE TABLE IF NOT EXISTS bundle_chunks (
  bundle     TEXT    NOT NULL,                       -- 실험 조각 한 벌 이름(코드 식별자)
  id         BIGINT  NOT NULL,                       -- 가이드 조각은 운영 번호 그대로, 설명서 조각은 1,000,000부터
  doc_id     TEXT    NOT NULL REFERENCES documents(id),
  page       INTEGER,
  content    TEXT    NOT NULL,
  embedding  VECTOR(1536) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (bundle, id)
);
CREATE INDEX IF NOT EXISTS bundle_chunks_bundle_doc ON bundle_chunks (bundle, doc_id);
