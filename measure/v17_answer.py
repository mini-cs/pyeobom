"""v1.7 Task 9: 실험 조각 한 벌로 서비스 흐름 전체를 돌린다.

answer_question은 deps.search·deps.diagnostic이 돌려준 조각 본문으로 프롬프트를 만들고 인용을 검사하므로,
이 두 함수만 한 벌 것으로 바꾸면 검색·진단 안내 쪽·프롬프트·인용 검사·이어지는 질문 턴이 모두 그 한 벌을 쓴다(운영 코드 그대로).
"""
import dataclasses
from collections.abc import Callable

from app.ask.service import Deps
from measure.search_eval import bundle_fns


def bundle_deps(deps: Deps, bundle: str | None, models: dict[str, dict], get_conn: Callable) -> Deps:
    """bundle이 None이면 deps 그대로. 저장 안 된 이름·빈 이름이면 bundle_fns가 멈춘다"""
    if bundle is None:
        return deps
    search, diagnostic = bundle_fns(bundle, models, get_conn)
    return dataclasses.replace(deps, search=search, diagnostic=diagnostic)
