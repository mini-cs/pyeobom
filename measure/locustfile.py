"""1차 /api/ask 동시 요청 응답 시간 측정(미리보기 전용, AI 비용 있음).

실행 전에 docs/평가/baseline-v1.md 비용 장부에 예상 비용을 적고 check_budget을 통과해야 한다.
locust -f measure/locustfile.py --headless -u 5 -r 1 -t 1m --host <미리보기 주소> --csv measure/out/locust
- 보호 우회 값은 .env의 VERCEL_AUTOMATION_BYPASS_SECRET에서 읽어 헤더로만 보낸다(주소 쿼리 사용 안 함, 출력 안 함).
"""
import os
import random
from pathlib import Path

from locust import HttpUser, between, events, task

from ingest.__main__ import load_env
from measure.load_common import assert_not_production, bypass_headers, question_pool

load_env()
POOL = question_pool(str(Path(__file__).resolve().parent.parent / "evaluation" / "questions.csv"))


@events.test_start.add_listener
def _refuse_production(environment, **kwargs):
    assert_not_production(environment.host or "")


class AskUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        assert_not_production(self.host)
        self.client.headers.update(bypass_headers(os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")))

    @task
    def ask(self):
        self.client.post("/api/ask", json=random.choice(POOL), name="/api/ask", timeout=30)
