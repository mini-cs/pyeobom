"""1차 /api/ask 동시 요청 응답 시간 측정(미리보기 전용, AI 비용 있음).

실행 전에 docs/평가/baseline-v1.md 비용 장부에 예상 비용을 적고 check_budget을 통과해야 한다.
측정 전에 질문 2개로 서버를 깨운다(결과 제외). v1.5 측정도 같은 절차.
[앞 대화 1개: LOCUST_HISTORY_CSV=evaluation/results/<새 세트 결과>.csv] locust -f measure/locustfile.py --headless -u 5 -r 1 -t 1m --host <미리보기 주소> --csv measure/out/locust
- 보호 우회 값은 .env의 VERCEL_AUTOMATION_BYPASS_SECRET에서 읽어 헤더로만 보낸다(주소 쿼리 사용 안 함, 출력 안 함).
"""
import os
import random
from pathlib import Path

from locust import HttpUser, between, events, task
import requests  # locust(gevent 패치) 다음에 불러와야 한다

from ingest.__main__ import load_env
from measure.load_common import answer_failure, assert_not_production, bypass_headers, followup_pool, question_pool, warm_up

load_env()
ROOT = Path(__file__).resolve().parent.parent
# LOCUST_HISTORY_CSV를 주면 앞 대화 1개를 붙인 이어지는 질문(새 세트 결과), 없으면 1차 질문(앞 대화 없음)
_HISTORY_CSV = os.environ.get("LOCUST_HISTORY_CSV")
POOL = followup_pool(str(ROOT / _HISTORY_CSV)) if _HISTORY_CSV else question_pool(str(ROOT / "evaluation" / "questions.csv"))


@events.test_start.add_listener
def _refuse_production_then_warm_up(environment, **kwargs):
    assert_not_production(environment.host or "")
    # 질문 2개로 서버를 깨운다. Locust 통계 밖에서 보내므로 결과에 섞이지 않는다
    headers = bypass_headers(os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET"))

    def post(body):
        resp = requests.post(f"{environment.host}/api/ask", json=body, headers=headers, timeout=60, allow_redirects=False)
        if reason := answer_failure(resp.status_code, resp.text):
            raise RuntimeError(f"깨우기 실패: {reason}")

    warm_up(post, POOL)


class AskUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        assert_not_production(self.host)
        self.client.headers.update(bypass_headers(os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")))

    @task
    def ask(self):
        with self.client.post("/api/ask", json=random.choice(POOL), name="/api/ask", timeout=30,
                              allow_redirects=False, catch_response=True) as resp:
            if reason := answer_failure(resp.status_code, resp.text):
                resp.failure(reason)
