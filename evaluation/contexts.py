"""평가 실행 중 답변 AI에 넘긴 조각 본문을 모은다(--save-contexts, DeepEval 채점용).

모은 본문은 설명서 원문이라 저장소에 넣지 않는다(.gitignore: evaluation/results/*-contexts.json).
"""
from dataclasses import replace

from app.ask.service import Deps


def capture_contexts(deps: Deps, store: list[str]) -> Deps:
    seen: set[int] = set()

    def keep(chunks):
        for c in chunks:
            if c.id not in seen:
                seen.add(c.id)
                store.append(c.content)
        return chunks

    return replace(deps, search=lambda *a: keep(deps.search(*a)), diagnostic=lambda m: keep(deps.diagnostic(m)))
