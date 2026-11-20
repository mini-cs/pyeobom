from openai import OpenAI

from app.core.config import get_settings

BATCH = 100  # 한 요청에 보낼 조각 수


def embed_texts(texts: list[str], client=None, *, model: str | None = None, dimensions: int | None = None) -> list[list[float]]:
    """model·dimensions가 None이면 설정값. 최종 dimensions가 None이면 요청에 그 키를 넣지 않는다(지금 운영 요청 그대로)."""
    settings = get_settings()
    client = client or OpenAI(api_key=settings.openai_api_key, timeout=20)
    model = model or settings.openai_embed_model
    dimensions = dimensions if dimensions is not None else settings.openai_embed_dimensions
    extra = {} if dimensions is None else {"dimensions": dimensions}
    vectors = []
    for i in range(0, len(texts), BATCH):
        resp = client.embeddings.create(model=model, input=texts[i:i + BATCH], **extra)
        vectors += [d.embedding for d in resp.data]
    return vectors


def embed_query(text: str, client=None, *, model: str | None = None, dimensions: int | None = None) -> list[float]:
    return embed_texts([text], client, model=model, dimensions=dimensions)[0]
