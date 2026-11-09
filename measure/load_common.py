"""Locust 부하 측정 공용 함수(미리보기 전용, 운영 주소 차단)."""
import csv
import json
from urllib.parse import urlparse

PRODUCTION_HOST = "pyeobom.vercel.app"
BYPASS_HEADER = "x-vercel-protection-bypass"  # Vercel 공식 문서 "Protection Bypass for Automation"(헤더 방식)


def question_pool(csv_path: str) -> list[dict]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        return [{"model_id": r["model_id"], "question": r["question"]}
                for r in csv.DictReader(f) if r["expected_found"] == "true"]


def bypass_headers(secret: str | None) -> dict:
    return {BYPASS_HEADER: secret} if secret else {}


def assert_not_production(url: str) -> None:
    host = urlparse(url if "//" in url else f"//{url}").hostname
    if host == PRODUCTION_HOST:
        raise ValueError("부하 측정은 운영 주소로 보내지 않는다(미리보기 주소만)")


def warm_up(post, pool: list[dict], n: int = 2) -> None:
    # 측정 전 서버·DB를 깨운다(결과에서 제외). post는 질문 하나를 보내는 함수
    for body in pool[:n]:
        post(body)


def answer_failure(status: int, body: str) -> str | None:
    # 리다이렉트를 따라간 로그인 화면 같은 200도 성공으로 세지 않도록 답 JSON인지 본다. 실패 이유만 돌려준다
    if status != 200:
        return f"HTTP {status}"
    try:
        if "found" in json.loads(body):
            return None
    except (ValueError, TypeError):
        pass
    return "답 JSON이 아님: " + " ".join(body[:60].split())
