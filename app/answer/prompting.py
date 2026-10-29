from pathlib import Path

from app.retrieval.search import Chunk

PROMPTS = Path(__file__).parent / "prompts"


def _data(text: str) -> str:
    # 질문·조각은 데이터로만 다룬다: 태그를 닫고 지시를 끼워 넣지 못하게 꺾쇠를 바꾼다
    return text.replace("<", "‹").replace(">", "›")


def build_messages(question: str, chunks: list[Chunk], version: str) -> list[dict]:
    system = (PROMPTS / f"answer_{version}.txt").read_text(encoding="utf-8")
    parts = [
        f'<chunk chunk_id="{c.id}" doc_type="{c.doc_type}" title="{_data(c.title)}" page="{c.page if c.page is not None else ""}">\n'
        f"{_data(c.content)}\n</chunk>"
        for c in chunks
    ]
    user = "<chunks>\n" + "\n".join(parts) + "\n</chunks>\n<question>" + _data(question) + "</question>"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
