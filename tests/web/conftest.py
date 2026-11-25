"""화면 테스트 공용 fixture: 로컬 정적 서버(public/)와 Playwright 브라우저(계획 2차 Task 6에서 test_ui_flow.py에서 옮김)."""
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PUBLIC = Path(__file__).resolve().parents[2] / "public"


class _Handler(SimpleHTTPRequestHandler):
    # 윈도 레지스트리의 MIME 값에 휘둘리지 않게 고정(JS 모듈은 JavaScript 형식이어야 불러와짐)
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".svg": "image/svg+xml", ".woff2": "font/woff2"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def playwright():
    with sync_playwright() as p:   # 한 스레드에 하나만 열 수 있어 브라우저들이 함께 쓴다
        yield p


@pytest.fixture(scope="module")
def browser(playwright):
    b = playwright.chromium.launch()
    yield b
    b.close()
