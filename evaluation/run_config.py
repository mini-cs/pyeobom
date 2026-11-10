"""평가·측정 실행의 실제 설정을 기록하고, 운영 기본값과 다르면 알린다(로컬 .env 실험 설정이 섞이는 것 방지)."""
import datetime
import json
from dataclasses import asdict
from pathlib import Path

# 운영 기본값(결정기록 015 최종 설정, 023 바꾸기 설정). 바뀌면 여기와 결정기록을 함께 고친다
PRODUCTION = {
    "search_mode": "vector",
    "top_k": 5,
    "openai_chat_model": "gpt-6-luna",
    "reasoning_effort": "low",
    "prompt_version": "v1",
    "rewrite_model": "gpt-6-luna",
    "rewrite_reasoning_effort": "none",
    "rewrite_max_output_tokens": 300,
}
RECORDED = list(PRODUCTION) + ["openai_embed_model", "max_output_tokens", "rewrite_timeout_s", "max_question_len"]


def run_settings(settings) -> dict:
    data = asdict(settings)
    return {k: data[k] for k in RECORDED}  # 키·접속 주소는 넣지 않는다


def differences(settings) -> list[str]:
    s = run_settings(settings)
    return [f"{k}={s[k]} (운영 {v})" for k, v in PRODUCTION.items() if s[k] != v]


def write_settings(result_path: str | Path, settings, label: str, experiment: dict | None = None) -> Path:
    """experiment: 실험 색인·질문 넓히기처럼 운영 설정 밖의 실험 내용(검색 개선 계획 1-5)"""
    path = Path(result_path).with_suffix(".settings.json")
    path.write_text(json.dumps({"label": label, "time": datetime.datetime.now().isoformat(timespec="seconds"),
                                "settings": run_settings(settings), "differences": differences(settings)}
                               | ({"experiment": experiment} if experiment else {}),
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def warn_if_different(settings) -> list[str]:
    diffs = differences(settings)
    if diffs:
        print("⚠ 운영 기본값과 다른 설정으로 실행합니다: " + ", ".join(diffs), flush=True)
    return diffs
