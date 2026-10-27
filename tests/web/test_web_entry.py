from fastapi import FastAPI

def test_vercel_entrypoint_exposes_app():
    # Vercel은 루트 index.py의 FastAPI 인스턴스 `app`을 자동 감지한다 (결정기록 013)
    import index
    assert isinstance(index.app, FastAPI)
