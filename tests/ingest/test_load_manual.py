import ingest.load as load
from ingest.load import build_chunks

MANUAL = {"id": "manual-sample", "doc_type": "manual", "title": "샘플 설명서", "file": "unused.pdf"}


def _fake_pages(monkeypatch, pages):
    monkeypatch.setattr(load, "extract_pages", lambda path: pages)


def test_manual_chunks_drop_leading_page_marker(monkeypatch):
    _fake_pages(monkeypatch, [(3, "3\n세탁조 청소는 한 달에 한 번 하세요."), (4, "한국어 4\n배수 필터를 확인하세요.")])
    chunks, dropped = build_chunks(MANUAL)
    assert dropped == 0
    assert [(p, t) for p, t in chunks] == [(3, "세탁조 청소는 한 달에 한 번 하세요."), (4, "배수 필터를 확인하세요.")]


def test_manual_chunks_keep_page_number_outside_front_window(monkeypatch):
    body = "물 온도는 40도 이하로 맞추고 세제는 적정량만 넣으세요 5"
    _fake_pages(monkeypatch, [(5, body)])
    chunks, _ = build_chunks(MANUAL)
    assert chunks == [(5, body)]  # 끝 검사는 하지 않는다(측정한 strip_800과 같음)
