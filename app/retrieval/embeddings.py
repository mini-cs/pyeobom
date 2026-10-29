from openai import OpenAI

from app.core.config import get_settings

BATCH = 100  # 한 요청에 보낼 조각 수


def embed_texts(texts: list[str], client=None) -> list[list[float]]:
    settings = get_settings()
    client = client or OpenAI(api_key=settings.openai_api_key, timeout=20)
    vectors = []
    for i in range(0, len(texts), BATCH):
        resp = client.embeddings.create(model=settings.openai_embed_model, input=texts[i:i + BATCH])
        vectors += [d.embedding for d in resp.data]
    return vectors


def embed_query(text: str, client=None) -> list[float]:
    return embed_texts([text], client)[0]
